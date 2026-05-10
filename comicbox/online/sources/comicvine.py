"""
ComicVine API source via simyan.

Wraps simyan's `Comicvine` client. simyan ships its own SQLite-backed
rate-limit bucket (1/sec, 200/hr) and response cache; we configure both
through `online.cache_dir` and `cache_ttl`.

ComicVine candidates do *not* arrive with a precomputed cover hash, so
the matcher's hashing path downloads the candidate's `image.thumb_url`
when needed. Downloaded hashes are cached in
`${cache_dir}/cover_hashes.sqlite` keyed by URL.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any, ClassVar

from loguru import logger

from comicbox.formats import MetadataFormats
from comicbox.online.profile import (
    Candidate,
    CandidateSummary,
    strip_issue_leading_zeros,
)
from comicbox.online.retry import with_retry
from comicbox.online.sources.base import OnlineSource
from comicbox.sources import MetadataSources
from comicbox.version import PACKAGE_NAME, VERSION

if TYPE_CHECKING:
    from simyan.comicvine import Comicvine

    from comicbox.online.profile import ComicProfile


class ComicVineOnlineSource(OnlineSource):
    """Wraps simyan for the ComicVine API."""

    name: ClassVar[str] = "comicvine"
    metadata_source: ClassVar[MetadataSources] = MetadataSources.COMICVINE_API
    metadata_format: ClassVar[MetadataFormats] = MetadataFormats.COMICVINE_API

    def is_configured(self) -> bool:
        """ComicVine requires an api_key."""
        return bool(self._credentials.api_key)

    def _get_cache(self) -> Any:
        if not self._settings.cache_enabled:
            return None
        from simyan.cache.sqlite_cache import SQLiteCache

        cache_path = self.cache_db_path()
        if self._settings.refresh_cache and cache_path.exists():
            cache_path.unlink()
            logger.debug(f"refresh-cache: removed {cache_path}")
        ttl = self._settings.cache_ttl
        expiry = ttl if ttl.total_seconds() > 0 else None
        return SQLiteCache(path=cache_path, expiry=expiry)

    def _get_session(self) -> Comicvine:
        from simyan.comicvine import Comicvine

        from comicbox.online.rate_limits import build_comicvine_limiter

        kwargs: dict[str, Any] = {
            "api_key": self._credentials.api_key,
            "cache": self._get_cache(),
            "user_agent": f"{PACKAGE_NAME}/{VERSION}",
        }
        if self._credentials.url:
            kwargs["base_url"] = self._credentials.url
        limiter = build_comicvine_limiter(self._settings.source_limits.get(self.name))
        if limiter is not None:
            kwargs["limiter"] = limiter
        return Comicvine(**kwargs)

    @with_retry()
    def get(self, issue_id: int) -> dict[str, Any]:
        """
        Fetch one ComicVine issue by id; return its model dump.

        CV's issue endpoint does NOT include the publisher inline —
        `Issue.volume` is a bare `GenericEntry`. We chase one extra
        request to ``get_volume(volume.id)`` to pull
        ``Volume.publisher`` and inject it under a top-level ``publisher``
        key for the transform to pick up. simyan's response cache is
        URL-keyed, so this is "+1 API call per unique volume" rather
        than per issue — successive issues from the same volume are free.
        """
        session = self._get_session()
        issue = session.get_issue(issue_id)
        dump: dict[str, Any] = issue.model_dump(mode="json")
        # `issue.volume` is a GenericEntry with id; fetch the full volume
        # to get its publisher. Best-effort — log and continue on failure.
        volume_id = (issue.volume.id if issue.volume else None) or (
            (dump.get("volume") or {}).get("id")
        )
        if volume_id is not None:
            try:
                volume = session.get_volume(int(volume_id))
            except Exception as exc:
                logger.warning(
                    f"online {self.name}: get_volume({volume_id}) failed; "
                    f"publisher will be missing from this issue: {exc}"
                )
            else:
                if volume.publisher is not None:
                    dump["publisher"] = volume.publisher.model_dump(mode="json")
        return dump

    # Limit how many candidate volumes to expand into issue queries; each
    # volume → one extra `list_issues` API call under CV's 1/sec rate limit.
    _MAX_VOLUMES_PER_SEARCH: ClassVar[int] = 20

    # ComicVine `Images` field names from smallest to largest.
    # `thumbnail` is sufficient for pHash; the rest are fallbacks for
    # records where a particular size is missing.
    _COVER_URL_PREFERENCE: ClassVar[tuple[str, ...]] = (
        "thumbnail",
        "small_url",
        "medium_url",
        "screen_url",
        "super_url",
        "original_url",
    )

    @classmethod
    def _pick_cover_url(cls, image: Any) -> str | None:
        if image is None:
            return None
        for attr in cls._COVER_URL_PREFERENCE:
            url = getattr(image, attr, None)
            if url:
                return str(url)
        return None

    def _to_candidate(
        self, basic_issue: Any, volume_name: str | None = None
    ) -> Candidate:
        """
        Map simyan's `BasicIssue` to a Candidate.

        ``volume_name`` overrides the series field when supplied — the
        two-step search has already resolved the volume so we use its
        canonical name even if `basic_issue.volume.name` is sparse.
        """
        bi_volume = basic_issue.volume
        series = volume_name or (bi_volume.name if bi_volume else "") or ""
        cover_year = basic_issue.cover_date.year if basic_issue.cover_date else None
        cover_url = self._pick_cover_url(basic_issue.image)
        site_url = str(basic_issue.site_url) if basic_issue.site_url else ""
        summary = CandidateSummary(
            series=series,
            issue=basic_issue.number or "",
            year=cover_year,
            publisher=None,  # BasicIssue from search doesn't include publisher
            page_count=None,
            cover_url=cover_url,
            variant_label=None,
        )
        return Candidate(
            source=self.name,
            issue_id=basic_issue.id,
            summary=summary,
            url=site_url,
            # ComicVine doesn't expose a precomputed pHash; matcher will
            # download and hash on demand if needed.
            precomputed_cover_hash=None,
        )

    # Cover-date window applied around `profile.year` when filtering
    # CV's per-volume issue lookup. ±2 years gives the year-only matcher
    # a small slop budget without admitting wholly-wrong-volume matches
    # that score well on every other signal.
    _COVER_DATE_WINDOW_YEARS: ClassVar[int] = 2

    def _list_issues_by_volume(
        self,
        session: Any,
        volume_id: int,
        issue_number: str | None,
        volume_name: str | None = None,
        *,
        year: int | None = None,
    ) -> list[Candidate]:
        """
        Run a single ``list_issues`` call constrained by volume id.

        Used both by the fast path (`--series-id comicvine:<id>`) and by
        each iteration of the discovery two-step. ``volume_name`` is set
        on the returned candidates' summary when available.

        ``year``, when supplied, narrows results to a ±_COVER_DATE_WINDOW_YEARS
        window around it via CV's ``cover_date:Y0-01-01|Y1-12-31``
        filter syntax. Cover-date drift is rarely more than ±1 year so a
        2-year slop is generous; this prevents wrong-volume picks (e.g.
        a 1986 series matching a 2005 collected edition with the same
        issue number) from polluting the candidate set in the first place.
        """
        issue_filter = [f"volume:{volume_id}"]
        if issue_number:
            issue_filter.append(f"issue_number:{issue_number}")
        if year is not None:
            window = self._COVER_DATE_WINDOW_YEARS
            issue_filter.append(
                f"cover_date:{year - window}-01-01|{year + window}-12-31"
            )
        issues = session.list_issues(params={"filter": ",".join(issue_filter)})
        return [self._to_candidate(i, volume_name) for i in issues]

    @with_retry()
    def search(self, profile: ComicProfile) -> list[Candidate]:
        """
        Search ComicVine for candidate issues matching the profile.

        ComicVine's ``list_issues`` filter has no series/volume-name field —
        its `name:` filter matches the *issue's* title, which is rarely
        useful. So we do the canonical two-step:

        1. Full-text-search for volumes matching the series name. (The
           ``list_volumes`` filter `name:` is strict and trips on
           punctuation: "GI Joe" vs "G.I. Joe". Full-text search is
           more permissive.)
        2. For each volume, ``list_issues`` filtered by ``volume:VOL_ID``
           and ``issue_number:N`` → candidate issues for that volume.

        ``--series-id comicvine:<id>`` short-circuits step 1 and runs
        only step 2 against the supplied volume id.

        Volume `start_year` is intentionally NOT used as a filter — a
        comic dated 2020 can be issue #100 of a series that started in
        1963. But ``profile.year`` IS used as a per-issue ``cover_date``
        window (±2 years), to keep wrong-volume candidates with the
        same issue number out of the candidate set entirely. If the
        year filter returns empty (CV has issues with missing
        cover_date), we retry once without the year filter.
        """
        session = self._get_session()
        issue_number = strip_issue_leading_zeros(profile.issue)
        year = profile.year
        # Fast path: --series-id comicvine:<id> skips the volume search and
        # goes straight to a single list_issues call constrained by that
        # volume id, saving the discovery API call.
        explicit_sid = self._settings.explicit_series_ids.get(self.name)
        if explicit_sid is not None:
            try:
                return self._list_with_year_retry(
                    session, explicit_sid, issue_number, None, year=year
                )
            except Exception as exc:
                logger.warning(
                    f"online {self.name}: issue-list for volume {explicit_sid} "
                    f"failed: {exc}"
                )
                raise

        if not profile.series:
            logger.debug(
                f"online {self.name}: no series in profile; cannot search CV "
                "(use --id comicvine:<id> for direct lookup, or "
                "--series-id comicvine:<id>)"
            )
            return []
        from simyan.comicvine import ComicvineResource

        try:
            volumes = session.search(
                resource=ComicvineResource.VOLUME,
                query=profile.series,
                max_results=self._MAX_VOLUMES_PER_SEARCH,
            )
        except Exception as exc:
            logger.warning(f"online {self.name}: volume search failed: {exc}")
            raise
        if not volumes:
            logger.info(
                f"online {self.name}: no volumes match series {profile.series!r}"
            )
            return []
        sample_size = 5
        sample = ", ".join(f"{v.name} ({v.id})" for v in volumes[:sample_size])
        if len(volumes) > sample_size:
            sample += " ..."
        logger.debug(
            f"online {self.name}: {len(volumes)} candidate volumes for "
            f"series={profile.series!r}: {sample}"
        )

        candidates: list[Candidate] = []
        for vol in volumes:
            try:
                candidates.extend(
                    self._list_with_year_retry(
                        session, vol.id, issue_number, vol.name, year=year
                    )
                )
            except Exception as exc:
                logger.warning(
                    f"online {self.name}: issue-list for volume {vol.id} "
                    f"({vol.name!r}) failed: {exc}"
                )
                continue
        return candidates

    def _list_with_year_retry(
        self,
        session: Any,
        volume_id: int,
        issue_number: str | None,
        volume_name: str | None,
        *,
        year: int | None,
    ) -> list[Candidate]:
        """
        Per-volume issue lookup with a year-window filter and one fallback.

        Tries `cover_date:Y±2` first (cuts out wrong-volume candidates).
        If that returns empty AND a year was supplied, retries without
        the year filter — cover_date can be missing on CV issues, and
        we'd rather see *something* and let the matcher score it than
        wrongly drop the right answer.
        """
        candidates = self._list_issues_by_volume(
            session, volume_id, issue_number, volume_name, year=year
        )
        if candidates or year is None:
            return candidates
        return self._list_issues_by_volume(
            session, volume_id, issue_number, volume_name, year=None
        )


# ----------------------------------------------------- cover-hash URL cache


class CoverHashUrlCache:
    """Tiny SQLite cache mapping cover URLs to their pHash strings."""

    def __init__(self, db_path: Any) -> None:
        """Open / create the sqlite cache file at `db_path`."""
        self._db_path = str(db_path)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cover_hashes "
                "(url TEXT PRIMARY KEY, phash TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def get(self, url: str) -> str | None:
        """Return the cached pHash for a cover URL, or None if absent."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT phash FROM cover_hashes WHERE url = ?", (url,)
            ).fetchone()
        return row[0] if row else None

    def set(self, url: str, phash: str) -> None:
        """Store a pHash for a cover URL, overwriting any previous value."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cover_hashes(url, phash) VALUES (?, ?)",
                (url, phash),
            )
