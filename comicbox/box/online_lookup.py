"""
Online metadata lookup mixin.

Sits between `ComicboxNormalize` and `ComicboxMerge` in the box chain.
For M2 the only path implemented is ``--id <db>:<id>`` — exact-issue
fetch. Search and ranking land in M3.

The mixin runs once per box instance, gated on
``settings.online.enabled``. For each active source (one whose
required credentials resolve and whose name is in
``selected_sources`` if that filter is set), it:

1. Checks ``--ignore-existing`` against any source data already
   carrying an identifier from this source's name (we don't re-tag if
   the user has already done so, even from a different source).
2. Calls ``source.get(issue_id)`` for every ``explicit_id`` mapped to
   that source.
3. Wraps the response under the schema's root tag and pushes it via
   ``add_source(source.metadata_source, ...)`` so the existing load
   → normalize → merge pipeline picks it up.
"""

from __future__ import annotations

import sys
import threading
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar

from glom import glom
from loguru import logger

from comicbox.box.normalize import ComicboxNormalize
from comicbox.online import outcome_stats
from comicbox.online.matcher import OnlineMatcher, Resolution, ResolutionKind
from comicbox.online.profile import (
    ComicProfile,
    parse_issue_int,
    parse_year,
    strip_issue_leading_zeros,
)
from comicbox.online.prompt import cli_selector
from comicbox.online.selector import SelectorContext
from comicbox.online.sources.comicvine import ComicVineOnlineSource
from comicbox.online.sources.metron import MetronOnlineSource
from comicbox.sources import MetadataSources

if TYPE_CHECKING:
    from comicbox.config.settings import OnlineSettings
    from comicbox.online.profile import Candidate
    from comicbox.online.selector import SelectorCallback
    from comicbox.online.sources.base import OnlineSource


class OnlineLookupAbortedError(Exception):
    """Raised when the selector callback returns ('abort', None)."""


# Source factories let tests substitute mocks without monkey-patching imports.
OnlineSourceFactory = "Callable[[Any, OnlineSettings], OnlineSource]"


_DEFAULT_SOURCE_FACTORIES: MappingProxyType[str, Any] = MappingProxyType(
    {
        "metron": MetronOnlineSource,
        "comicvine": ComicVineOnlineSource,
    }
)

# Online MetadataSources entries. Used to skip self when checking for existing
# identifiers under `--ignore-existing`.
_ONLINE_SOURCE_ENUMS: frozenset[MetadataSources] = frozenset(
    {MetadataSources.METRON_API, MetadataSources.COMICVINE_API}
)


class _NoTtyHintGuard:
    """One-shot guard for the no-TTY hint, lock-protected for `-j N` runs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._shown = False

    def maybe_log(self, *, has_callback: bool) -> None:
        """
        Log the hint at most once per process if conditions warrant.

        Programmatic library callers (codex, etc.) typically register a
        selector callback before invoking the lookup; their presence
        silences the hint because they have a way to handle prompts.
        """
        if has_callback:
            return
        try:
            is_tty = sys.stdin.isatty()
        except (AttributeError, ValueError):
            # Closed stdin or unusual stream — treat as no TTY.
            is_tty = False
        if is_tty:
            return
        with self._lock:
            if self._shown:
                return
            self._shown = True
        logger.info(
            "online: no TTY detected and no prompt callback registered; "
            "pass --unattended if you don't expect to see prompts "
            "(interactive mode without a TTY will hang on the first "
            "PROMPT decision)."
        )


_no_tty_hint = _NoTtyHintGuard()


def _resolve_volume(md: dict) -> int | None:
    """Extract `comicbox.volume.number` as an int, defensively."""
    raw = glom(md, "comicbox.volume.number", default=None)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _detect_cv_id_disagreement(
    metron_md: dict | None, cv_md: dict | None
) -> tuple[str, str] | None:
    """
    Compare the ComicVine identifier each source contributed.

    Metron's `cv_id` field flows into its merged metadata as
    `comicbox.identifiers.comicvine.key`; CV's own issue id flows in
    under the same path from the CV-sourced data. When both are set and
    disagree, one of them is wrong (Metron's `cv_id` field is a
    cross-reference that goes stale; our CV match could also have hit
    the wrong volume). Return ``(metron_cv_id, cv_cv_id)`` so the
    caller can log it; return None for "no disagreement to report"
    (either source missing, either id missing, or they match).
    """
    if not metron_md or not cv_md:
        return None
    metron_key = glom(metron_md, "comicbox.identifiers.comicvine.key", default=None)
    cv_key = glom(cv_md, "comicbox.identifiers.comicvine.key", default=None)
    if metron_key is None or cv_key is None:
        return None
    metron_str = str(metron_key)
    cv_str = str(cv_key)
    if metron_str == cv_str:
        return None
    return (metron_str, cv_str)


def _accumulate_profile_fields(fields: dict[str, Any], md: dict) -> None:
    """First-wins accumulation of profile fields across normalized sources."""
    if "series" not in fields and (v := glom(md, "comicbox.series.name", default=None)):
        fields["series"] = v
    if "issue" not in fields and (v := glom(md, "comicbox.issue.name", default=None)):
        fields["issue"] = v
    if "year" not in fields:
        raw_year = glom(md, "comicbox.date.year", default=None) or glom(
            md, "comicbox.date.cover_date", default=None
        )
        if (parsed := parse_year(raw_year)) is not None:
            fields["year"] = parsed
    if "publisher" not in fields and (
        v := glom(md, "comicbox.publisher.name", default=None)
    ):
        fields["publisher"] = v
    if "page_count" not in fields and (
        v := glom(md, "comicbox.page_count", default=None)
    ):
        fields["page_count"] = v
    if "volume" not in fields and (v := _resolve_volume(md)) is not None:
        fields["volume"] = v


class ComicboxOnlineLookup(ComicboxNormalize):
    """Pulls online metadata into the source pool before merge runs."""

    # Class-level so tests can override (and per-instance attrs override that).
    _ONLINE_SOURCE_FACTORIES: ClassVar[MappingProxyType[str, Any]] = (
        _DEFAULT_SOURCE_FACTORIES
    )

    # Process-wide lock around the selector callback. Under `-j N` parallel
    # batch runs we serialise prompts so output stays readable and the user
    # can see which file is being asked about.
    _PROMPT_LOCK: ClassVar[threading.Lock] = threading.Lock()

    # Per-instance selector override; falls back to the default CLI prompt.
    _online_selector: SelectorCallback | None = None

    def set_online_selector(self, selector: SelectorCallback | None) -> None:
        """Register a programmatic selector callback (codex / library users)."""
        self._online_selector = selector

    def _online_lookup_already_done(self) -> bool:
        return getattr(self, "_online_lookup_done_flag", False)

    def _mark_online_lookup_done(self) -> None:
        self._online_lookup_done_flag = True

    def _warn_unconfigured_source(self, name: str) -> None:
        """
        Loud warning when a user-requested source can't run for credential reasons.

        Quiet skip when the source was only included via the `all` sentinel
        — in that case we don't know the user wanted this specific source.
        """
        online = self._config.online
        explicit_id = online.explicit_ids.get(name)
        if explicit_id is not None:
            logger.warning(
                f"online: --id {name}:{explicit_id} requested but {name} is "
                f"not configured (missing credentials); skipping"
            )
            return
        explicit_sid = online.explicit_series_ids.get(name)
        if explicit_sid is not None:
            logger.warning(
                f"online: --series-id {name}:{explicit_sid} requested but "
                f"{name} is not configured (missing credentials); skipping"
            )
            return
        # Was the source named explicitly via `--online <list>`? selected
        # is None for the `all` sentinel; only warn for explicit lists.
        if online.selected_sources is not None and name in online.selected_sources:
            logger.warning(
                f"online: --online {name} requested but {name} is not "
                f"configured (missing credentials); skipping"
            )

    def _build_active_online_sources(self) -> list[OnlineSource]:
        """Resolve which configured online sources participate in this run."""
        online: OnlineSettings = self._config.online
        selected = online.selected_sources
        active: list[OnlineSource] = []
        for name, factory in self._ONLINE_SOURCE_FACTORIES.items():
            if selected is not None and name not in selected:
                continue
            creds = online.sources.get(name)
            if creds is None:
                self._warn_unconfigured_source(name)
                continue
            source = factory(creds, online)
            if not source.is_configured():
                self._warn_unconfigured_source(name)
                continue
            active.append(source)
        return active

    def _has_existing_identifier(self, source_name: str) -> bool:
        """Return True if any non-online source's data already has this source's id."""
        keypath = f"comicbox.identifiers.{source_name}"
        for src in MetadataSources:
            if src in _ONLINE_SOURCE_ENUMS:
                continue
            normalized = self.get_normalized_metadata(src)
            if not normalized:
                continue
            for loaded in normalized:
                if glom(dict(loaded.metadata), keypath, default=None):
                    return True
        return False

    def _wrap_payload(self, source: OnlineSource, payload: dict[str, Any]) -> dict:
        """Wrap raw API response under the format's ROOT_TAG for schema.load."""
        schema_class = source.metadata_format.value.schema_class
        return {schema_class.ROOT_TAG: payload}

    def _fetch_explicit_id(self, source: OnlineSource, issue_id: int) -> None:
        try:
            payload = source.get(issue_id)
        except Exception as exc:
            logger.warning(
                f"online {source.name}: fetch by id={issue_id} failed: {exc}"
            )
            return
        wrapped = self._wrap_payload(source, payload)
        self.add_source(
            source.metadata_source,
            wrapped,
            fmt=source.metadata_format,
        )
        logger.debug(f"online {source.name}: added id={issue_id}")

    def _build_profile(self) -> ComicProfile:
        """Read the non-online merged-so-far metadata into a ComicProfile."""
        # Collect from non-online normalized sources, first-wins.
        fields: dict[str, Any] = {}
        for src in MetadataSources:
            if src in _ONLINE_SOURCE_ENUMS:
                continue
            normalized = self.get_normalized_metadata(src)
            if not normalized:
                continue
            for loaded in normalized:
                _accumulate_profile_fields(fields, dict(loaded.metadata))
        return ComicProfile(
            series=fields.get("series"),
            issue=fields.get("issue"),
            issue_int=parse_issue_int(fields.get("issue")),
            year=fields.get("year"),
            publisher=fields.get("publisher"),
            page_count=fields.get("page_count"),
            volume=fields.get("volume"),
        )

    def _accept_candidate(self, source: OnlineSource, candidate: Candidate) -> None:
        """Fetch the full record for an accepted candidate and inject it."""
        self._fetch_explicit_id(source, candidate.issue_id)

    def _candidate_cover_hash_fetcher(self, url: str) -> str | None:
        """
        Download a candidate cover from URL and return its pHash, with caching.

        Used by the matcher for sources that don't ship a precomputed hash
        (ComicVine, GCD). Local writes go through the shared
        cover-hashes sqlite cache.
        """
        from comicbox.online.cover_hash import compute_phash
        from comicbox.online.sources.comicvine import (
            CoverHashUrlCache,
        )

        if not url:
            return None

        cache = getattr(self, "_cover_hash_url_cache", None)
        if cache is None:
            cache_dir = self._config.online.cache_dir
            if cache_dir is None:
                from platformdirs import user_cache_path

                cache_dir = user_cache_path("comicbox") / "online"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache = CoverHashUrlCache(cache_dir / "cover_hashes.sqlite")
            self._cover_hash_url_cache = cache

        if not self._config.online.cache_enabled:
            cache = None
        if cache is not None and (cached := cache.get(url)):
            return cached

        try:
            import httpx

            response = httpx.get(url, timeout=15.0, follow_redirects=True)
            response.raise_for_status()
        except Exception as exc:
            logger.warning(f"online: cover download failed ({url}): {exc}")
            return None

        try:
            phash = compute_phash(response.content)
        except Exception as exc:
            logger.warning(f"online: cover pHash failed ({url}): {exc}")
            return None

        if cache is not None:
            cache.set(url, phash)
        return phash

    def _local_cover_phash(self) -> str | None:
        """Compute the comic's pHash on demand, cached on the box instance."""
        cached = getattr(self, "_local_cover_phash_value", "<unset>")
        if cached != "<unset>":
            return cached
        try:
            cover_bytes = self.get_cover_page(skip_metadata=True)
        except Exception as exc:
            logger.debug(f"local cover: fetch failed: {exc}")
            self._local_cover_phash_value = None
            return None
        if not cover_bytes:
            self._local_cover_phash_value = None
            return None
        try:
            from comicbox.online.cover_hash import compute_phash

            self._local_cover_phash_value = compute_phash(cover_bytes)
        except Exception as exc:
            logger.warning(f"local cover: pHash failed: {exc}")
            self._local_cover_phash_value = None
        return self._local_cover_phash_value

    def _resolve_with_matcher(
        self, source_name: str, candidates: list[Candidate]
    ) -> Resolution:
        from comicbox.config.settings import (
            resolve_confidence_threshold,
            resolve_disambiguation_margin,
            resolve_min_confidence,
        )

        online = self._config.online
        threshold = resolve_confidence_threshold(online, source_name)
        min_conf = resolve_min_confidence(online, source_name)
        margin = resolve_disambiguation_margin(online, source_name)
        matcher = OnlineMatcher()
        ranked = matcher.rank(
            self._build_profile(),
            candidates,
            local_hash_provider=self._local_cover_phash,
            candidate_hash_fetcher=self._candidate_cover_hash_fetcher,
            threshold=threshold,
            min_confidence=min_conf,
            disambiguation_margin=margin,
        )
        return matcher.resolve(ranked, online, source_name)

    def _selector_for_run(self) -> SelectorCallback:
        return self._online_selector or cli_selector

    def _handle_prompt(
        self, source: OnlineSource, candidates: tuple[Candidate, ...]
    ) -> None:
        """
        Drive the selector callback for the PROMPT case.

        Acquires the class-level `_PROMPT_LOCK` around the selector call
        so concurrent worker threads (when `-j N > 1`) don't garble each
        other's prompts.
        """
        selector = self._selector_for_run()
        ctx = SelectorContext(
            file_path=getattr(self, "_path", None),
            source=source.name,
            settings=self._config,
            triggered_hashing=any(c.cover_score is not None for c in candidates),
        )
        with type(self)._PROMPT_LOCK:  # noqa: SLF001 — class-level lock by design
            result = selector(self._build_profile(), candidates, ctx)
        action, payload = result
        if action == "choose" and isinstance(payload, int):
            chosen = candidates[payload]
            logger.info(f"online {source.name}: prompt-chose id={chosen.issue_id}")
            outcome_stats.record_prompt_accepted(source.name)
            self._accept_candidate(source, chosen)
            return
        if action == "manual" and isinstance(payload, str):
            try:
                src_name, _, raw_id = payload.partition(":")
                issue_id = int(raw_id)
            except ValueError:
                logger.warning(f"online: manual id {payload!r} is not <source>:<int>")
                outcome_stats.record_prompt_declined(source.name)
                return
            if src_name.strip().lower() != source.name:
                logger.warning(
                    f"online {source.name}: manual id {payload!r} routes to "
                    f"a different source; skipping"
                )
                outcome_stats.record_prompt_declined(source.name)
                return
            outcome_stats.record_prompt_accepted(source.name)
            self._fetch_explicit_id(source, issue_id)
            return
        if action == "abort":
            reason = "online: aborted by user from prompt"
            raise OnlineLookupAbortedError(reason)
        logger.info(f"online {source.name}: skipped via prompt")
        outcome_stats.record_prompt_declined(source.name)

    def _search_path(self, source: OnlineSource) -> None:
        """Search → rank → resolve → fetch on accept."""
        profile = self._build_profile()
        if not (profile.series or profile.issue or profile.year):
            logger.warning(
                f"online {source.name}: no search criteria — couldn't extract "
                "series, issue#, or year from the comic's metadata or "
                f"filename. Use --id {source.name}:<issue_id> to tag by id."
            )
            return
        # Show what's actually sent: leading zeros stripped from issue#.
        search_issue = strip_issue_leading_zeros(profile.issue)
        criteria_summary = (
            f"series={profile.series!r} issue={search_issue!r} year={profile.year}"
        )
        logger.info(f"online {source.name}: searching with {criteria_summary}")
        try:
            candidates = source.search(profile)
        except Exception as exc:
            logger.warning(f"online {source.name}: search failed: {exc}")
            return
        if not candidates:
            logger.info(
                f"online {source.name}: 0 candidates for {criteria_summary} "
                "(no matching issues in the database)"
            )
            return
        resolution = self._resolve_with_matcher(source.name, candidates)
        if resolution.kind is ResolutionKind.AUTO_WRITE and resolution.chosen:
            logger.info(
                f"online {source.name}: auto-writing "
                f"id={resolution.chosen.issue_id} "
                f"(score={resolution.chosen.score:.2f})"
            )
            outcome_stats.record_auto_write(source.name)
            self._accept_candidate(source, resolution.chosen)
            return
        if resolution.kind is ResolutionKind.NO_MATCH:
            logger.info(f"online {source.name}: no match cleared min_confidence")
            outcome_stats.record_no_match(source.name)
            return
        if resolution.kind is ResolutionKind.SKIP:
            top_score = resolution.candidates[0].score if resolution.candidates else 0
            logger.info(
                f"online {source.name}: skipped (matcher declined; top={top_score:.2f})"
            )
            outcome_stats.record_skip(source.name)
            return
        # ResolutionKind.PROMPT — invoke the selector callback.
        self._handle_prompt(source, resolution.candidates)

    def _lookup_one_source(self, source: OnlineSource) -> None:
        if self._config.online.ignore_existing and self._has_existing_identifier(
            source.name
        ):
            logger.info(
                f"online {source.name}: --ignore-existing skipping "
                f"(already has {source.name} id)"
            )
            return
        explicit_ids = self._config.online.explicit_ids
        issue_id = explicit_ids.get(source.name)
        if issue_id is not None:
            outcome_stats.record_explicit_id(source.name)
            self._fetch_explicit_id(source, issue_id)
            return
        self._search_path(source)

    def _first_normalized(self, src: MetadataSources) -> dict | None:
        """First normalized metadata dict from `src`, or None if unset."""
        normalized = self.get_normalized_metadata(src)
        if not normalized:
            return None
        for loaded in normalized:
            md = dict(loaded.metadata)
            if md:
                return md
        return None

    def _cross_source_cv_id_check(self) -> None:
        """
        Warn when Metron's stored `cv_id` and our CV match disagree.

        Runs once per box after both online sources have been queried.
        The check looks at the per-source normalized metadata (still
        distinguishable here, before the box-level merge collapses the
        two `comicbox.identifiers.comicvine.key` values into one). We
        don't decide which is right — just surface the disagreement so
        the user sees it before accepting.
        """
        metron_md = self._first_normalized(MetadataSources.METRON_API)
        cv_md = self._first_normalized(MetadataSources.COMICVINE_API)
        disagreement = _detect_cv_id_disagreement(metron_md, cv_md)
        if disagreement is None:
            return
        metron_id, cv_id = disagreement
        logger.warning(
            f"online: cross-source ComicVine id disagreement — Metron "
            f"stored cv_id={metron_id} but our independent ComicVine "
            f"match returned id={cv_id}. One of the two sources has the "
            f"wrong identifier; review before accepting."
        )

    def run_online_lookup(self) -> None:
        """Idempotent: populate online MetadataSources once per box instance."""
        if self._online_lookup_already_done():
            return
        self._mark_online_lookup_done()
        if not self._config.online.enabled:
            return
        if not self._config.online.unattended:
            _no_tty_hint.maybe_log(has_callback=self._online_selector is not None)
        for source in self._build_active_online_sources():
            self._lookup_one_source(source)
        self._cross_source_cv_id_check()
