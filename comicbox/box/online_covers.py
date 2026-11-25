"""
Cover-hash resources for online matching, and the search by cover.

The matcher scores a candidate partly on how close its cover looks to the
comic's own, which needs two things a `Comicbox` has to own for its whole
lifetime: a sqlite cache of URL to perceptual hash, and a bounded HTTP
pool to fetch the covers that miss it. Both are expensive to build and
must be closed, so they live on the box rather than being rebuilt per
candidate. A source that can search by cover is asked here too, with the
comic's own cover hashes; the lookup flow decides what to do with a match.

Split out of `online_lookup` because the dependency runs one way — the
lookup flow reaches down here for a hash and nothing here calls back — and
because `close()` belongs with the resources it releases.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from operator import itemgetter
from typing import TYPE_CHECKING

from loguru import logger

from comicbox.box.normalize import ComicboxNormalize
from comicbox.exceptions import OnlineLookupAbortedError

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Sequence

    from comicbox.config.online.settings import OnlineSettings
    from comicbox.formats.base.online.cover_hash import (
        CoverFetchPool,
        CoverHashUrlCache,
        SearchHash,
    )
    from comicbox.formats.base.online.matcher import CoverMatch, Resolution
    from comicbox.formats.base.online.profile import Candidate, ComicProfile
    from comicbox.formats.base.online.sources.base import OnlineSource


@dataclass(frozen=True, slots=True)
class CoverSearchResult:
    """What a search by cover found."""

    # The match the verdict accepted, if any.
    match: CoverMatch | None = None
    # Every row worth offering in a prompt, closest cover first: those whose
    # series agrees with the comic's (all of them, under a pinned series),
    # each at its closest distance across the hashes tried.
    candidates: tuple[Candidate, ...] = ()


def _keep_closest(
    closest: dict[int, tuple[int, Candidate]],
    ranked: Sequence[tuple[int, Candidate]],
) -> None:
    """Record each ranked row at the smallest distance any hash gave it."""
    for bits, candidate in ranked:
        seen = closest.get(candidate.issue_id)
        if seen is None or bits < seen[0]:
            closest[candidate.issue_id] = (bits, candidate)


def _offered(
    closest: dict[int, tuple[int, Candidate]],
    profile: ComicProfile,
    *,
    series_pinned: bool,
) -> tuple[Candidate, ...]:
    """
    Return the rows a prompt may offer, closest cover first.

    Rows from an unrelated series are mostly the same issue number with a
    cover a few bits away, so offering them would turn a comic Metron
    doesn't have into a prompt of wrong issues.
    """
    from comicbox.formats.base.online.signals import series_words_agree

    return tuple(
        candidate
        for _, candidate in sorted(closest.values(), key=itemgetter(0))
        if series_pinned or series_words_agree(profile.series, candidate.summary.series)
    )


class ComicboxOnlineCovers(ComicboxNormalize):
    """Owns the box-lifetime cover-hash cache and download pool."""

    # Lazily built, released by `close`. Declared here rather than in
    # __init__ because the box's mixin chain shares one constructor.
    _cover_hash_url_cache: CoverHashUrlCache | None = None
    _cover_fetch_pool: CoverFetchPool | None = None
    _local_cover_phash_computed: bool = False
    _local_cover_phash_value: str | None = None
    # None until computed; an empty tuple means there is no usable cover.
    _local_cover_search_hashes_value: tuple[SearchHash, ...] | None = None

    def _get_cover_hash_cache(self) -> CoverHashUrlCache | None:
        """
        Lazily open the shared cover-hash sqlite cache; None when caching is OFF.

        One connection for the box's lifetime (see `CoverHashUrlCache`),
        so a top-K batch costs one query in and one transaction out
        instead of two connections per candidate.
        """
        from comicbox.config.online.settings import CacheMode

        if self._config.online.cache.mode is CacheMode.OFF:
            return None
        if self._cover_hash_url_cache is None:
            from comicbox.formats.base.online.cover_hash import CoverHashUrlCache

            cache_dir = self._config.online.cache.dir
            if cache_dir is None:
                from platformdirs import user_cache_path

                cache_dir = user_cache_path("comicbox") / "online"
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._cover_hash_url_cache = CoverHashUrlCache(
                cache_dir / "cover_hashes.sqlite"
            )
        return self._cover_hash_url_cache

    def _get_cover_fetch_pool(self) -> CoverFetchPool:
        """Lazily build the bounded download pool; one httpx client per box."""
        if self._cover_fetch_pool is None:
            from comicbox.formats.base.online.cover_hash import CoverFetchPool

            self._cover_fetch_pool = CoverFetchPool()
        return self._cover_fetch_pool

    def _candidate_cover_hash_batch_fetcher(
        self, urls: Sequence[str]
    ) -> dict[str, str]:
        """
        Resolve many candidate cover URLs to pHashes in one pass.

        Used by the matcher for sources that don't ship a precomputed
        hash (ComicVine, GCD). Cache lookups collapse into a single
        query; the remaining misses download concurrently over one
        shared HTTP client and are written back in one transaction.
        URLs that fail to download or hash are simply absent from the
        result — the matcher reads that as "no cover signal".
        """
        wanted = [u for u in dict.fromkeys(urls) if u]
        if not wanted:
            return {}
        cache = self._get_cover_hash_cache()
        resolved = cache.get_many(wanted) if cache is not None else {}
        missing = [u for u in wanted if u not in resolved]
        if not missing:
            return resolved
        fetched = self._get_cover_fetch_pool().fetch_hashes(missing)
        if cache is not None and fetched:
            cache.set_many(fetched.items())
        resolved.update(fetched)
        return resolved

    def _candidate_cover_hash_fetcher(self, url: str) -> str | None:
        """
        Download a candidate cover from URL and return its pHash, with caching.

        The single-URL entry point, kept for callers that resolve one
        candidate at a time; the matcher's hot path goes through
        `_candidate_cover_hash_batch_fetcher` instead.
        """
        if not url:
            return None
        return self._candidate_cover_hash_batch_fetcher((url,)).get(url)

    def _close_cover_hash_resources(self) -> None:
        """Release the cover-hash sqlite connection and HTTP client."""
        if self._cover_hash_url_cache is not None:
            self._cover_hash_url_cache.close()
            self._cover_hash_url_cache = None
        if self._cover_fetch_pool is not None:
            self._cover_fetch_pool.close()
            self._cover_fetch_pool = None

    @override
    def close(self) -> None:
        """Close the archive, then release online-lookup resources."""
        try:
            super().close()
        finally:
            self._close_cover_hash_resources()

    def _read_local_cover(self) -> bytes | None:
        """Read the comic's cover image, or None when there isn't one."""
        try:
            return self.get_cover_page(pdf_format="pixmap", skip_metadata=True) or None  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[missing-attribute]
        except Exception as exc:
            logger.debug(f"local cover: fetch failed: {exc}")
            return None

    def _local_cover_search_hashes(self) -> tuple[SearchHash, ...]:
        """
        Compute the hashes to search for this comic by cover, once per box.

        Separate from `_local_cover_phash`, which the matcher compares
        candidates against: these are uprighted and split for spreads
        (`search_hashes`), and are only worth reading the cover for when a
        source can search by cover at all.
        """
        if self._local_cover_search_hashes_value is not None:
            return self._local_cover_search_hashes_value
        hashes: tuple[SearchHash, ...] = ()
        if cover_bytes := self._read_local_cover():
            try:
                from comicbox.formats.base.online.cover_hash import search_hashes

                hashes = search_hashes(cover_bytes)
            except Exception as exc:
                logger.warning(f"local cover: search hashes failed: {exc}")
        self._local_cover_search_hashes_value = hashes
        return hashes

    def _cover_search(
        self, source: OnlineSource, profile: ComicProfile, *, series_pinned: bool
    ) -> CoverSearchResult:
        """
        Search ``source`` by this comic's cover.

        Each search hash is tried in turn (`search_hashes`: a spread's
        halves before the whole) until one search's closest result passes
        `cover_verdict`. One request per hash tried, so one for most
        comics, and none when the source can't search by cover, the
        profile can't narrow the query, or there is no cover to hash.

        The result carries the accepted match, if any, and the rows worth
        offering if the comic ends at a prompt. A failed search ends the
        cover search, not the lookup, keeping the rows found before it. An
        abort is re-raised, since it ends the lookup.
        """
        # Read structurally, as the lookup reads `search_skip_reason`: a
        # source is whatever implements search() and friends.
        can_search = getattr(source, "can_search_by_cover", None)
        if can_search is None or not can_search(profile):
            return CoverSearchResult()
        from comicbox.formats.base.online.matcher import (
            cover_verdict,
            rank_by_cover_distance,
        )

        closest: dict[int, tuple[int, Candidate]] = {}
        match: CoverMatch | None = None
        for search_hash in self._local_cover_search_hashes():
            try:
                rows = source.search_by_cover(profile, search_hash.phash)
            except OnlineLookupAbortedError:
                raise
            except Exception as exc:
                logger.warning(f"online {source.name}: cover search failed: {exc}")
                break
            ranked = rank_by_cover_distance(search_hash.phash, rows)
            logger.debug(
                f"online {source.name}: cover search by the {search_hash.part}: "
                f"closest distances {[bits for bits, _ in ranked[:3]]}"
            )
            _keep_closest(closest, ranked)
            match = cover_verdict(
                ranked, search_hash.accept_bits, profile, series_pinned=series_pinned
            )
            if match is not None:
                logger.info(
                    f"online {source.name}: cover match id={match.candidate.issue_id} "
                    f"on the {search_hash.part} at {match.bits} bits "
                    f"(next {match.runner_up_bits})"
                )
                break
        return CoverSearchResult(
            match, _offered(closest, profile, series_pinned=series_pinned)
        )

    @staticmethod
    def _cover_match_may_seed_cache(
        profile: ComicProfile, candidate: Candidate
    ) -> bool:
        """
        Whether a cover match's series is safe to cache under this profile.

        Only when the two names are the same name: the same distinctive
        words (`series_words`), so case, accents, punctuation and stop words
        don't matter ("Ardent" is "The Ardent"). A cover match only
        needs the names to share a word, and caching what "Star Drifters" turned
        out to be (*The Book of Boba Fett*) would tag the next "Star Drifters
        #5", from any Star Drifters series, as Boba Fett #5 without a search.
        """
        from comicbox.formats.base.online.signals import series_words

        words = series_words(profile.series or "")
        return bool(words) and words == series_words(candidate.summary.series)

    def _rank_candidates(
        self,
        profile: ComicProfile,
        source_name: str,
        candidates: list[Candidate],
        online: OnlineSettings,
    ) -> list[Candidate]:
        """Score and sort candidates under this source's thresholds."""
        from comicbox.config.online.settings import (
            resolve_auto_threshold,
            resolve_disambiguation_margin,
            resolve_min_confidence,
        )
        from comicbox.formats.base.online.matcher import OnlineMatcher

        return OnlineMatcher().rank(
            profile,
            candidates,
            local_hash_provider=self._local_cover_phash,
            candidate_hash_batch_fetcher=self._candidate_cover_hash_batch_fetcher,
            threshold=resolve_auto_threshold(online, source_name),
            min_confidence=resolve_min_confidence(online, source_name),
            disambiguation_margin=resolve_disambiguation_margin(online, source_name),
        )

    def _cover_prompt(
        self,
        profile: ComicProfile,
        source_name: str,
        online: OnlineSettings,
        candidates: list[Candidate],
        cover: CoverSearchResult,
    ) -> Resolution:
        """
        Build the prompt over the name search's rows and the cover rows.

        The union is ranked by the matcher like any candidate set, which
        hashes the cover rows for free (each carries its cover hash). A
        prompt re-resolved after a session change reads the list as ranked,
        so the matcher's order stands. The one exception is the cover
        verdict's match, which leads: it is here under ``ask``, where every
        other mode would have written it, or when its fetch failed. Under
        ``--prompts never`` the prompt is a skip.
        """
        from comicbox.config.online.settings import Prompts
        from comicbox.formats.base.online.matcher import Resolution, ResolutionKind

        listed = {c.issue_id for c in candidates}
        pool = [*candidates, *(c for c in cover.candidates if c.issue_id not in listed)]
        ranked = self._rank_candidates(profile, source_name, pool, online)
        if cover.match is not None:
            chosen_id = cover.match.candidate.issue_id
            ranked.sort(key=lambda c: c.issue_id != chosen_id)
        kind = (
            ResolutionKind.SKIP
            if online.lookup.prompts is Prompts.NEVER
            else ResolutionKind.PROMPT
        )
        logger.info(
            f"online {source_name}: offering {len(ranked)} candidates, "
            f"{len(pool) - len(candidates)} of them from the cover search"
        )
        return Resolution(kind, None, tuple(ranked))

    def _local_cover_phash(self) -> str | None:
        """Compute the comic's pHash on demand, cached on the box instance."""
        if self._local_cover_phash_computed:
            return self._local_cover_phash_value
        self._local_cover_phash_computed = True
        cover_bytes = self._read_local_cover()
        if not cover_bytes:
            return None
        try:
            from comicbox.formats.base.online.cover_hash import compute_phash

            self._local_cover_phash_value = compute_phash(cover_bytes)
        except Exception as exc:
            logger.warning(f"local cover: pHash failed: {exc}")
        return self._local_cover_phash_value
