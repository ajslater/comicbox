"""
Metron API source via mokkari.

M2 wires the `--id metron:N` path: instantiate a session with credentials
from the resolution chain, fetch one issue by id, dump the Pydantic model
to a plain dict, and hand it back to `ComicboxOnlineLookup` for transform
and merge. M3 adds search.
"""

from __future__ import annotations

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
    from mokkari.session import Session

    from comicbox.online.profile import ComicProfile


class MetronOnlineSource(OnlineSource):
    """Wraps mokkari for the Metron API."""

    name: ClassVar[str] = "metron"
    metadata_source: ClassVar[MetadataSources] = MetadataSources.METRON_API
    metadata_format: ClassVar[MetadataFormats] = MetadataFormats.METRON_API

    def is_configured(self) -> bool:
        """Metron requires both username and password."""
        return bool(self._credentials.username and self._credentials.password)

    def _get_cache(self) -> Any:
        if not self._settings.cache_enabled:
            return None
        from mokkari.sqlite_cache import SqliteCache

        cache_path = self.cache_db_path()
        if self._settings.refresh_cache and cache_path.exists():
            cache_path.unlink()
            logger.debug(f"refresh-cache: removed {cache_path}")
        ttl = self._settings.cache_ttl
        expire = int(ttl.total_seconds()) if ttl.total_seconds() > 0 else None
        return SqliteCache(db_name=str(cache_path), expire=expire)

    def _get_session(self) -> Session:
        from mokkari import api

        return api(
            username=self._credentials.username,
            passwd=self._credentials.password,
            cache=self._get_cache(),
            user_agent=f"{PACKAGE_NAME}/{VERSION}",
        )

    @with_retry()
    def get(self, issue_id: int) -> dict[str, Any]:
        """Fetch one Metron issue by id; return its model dump."""
        session = self._get_session()
        issue = session.issue(issue_id)
        return issue.model_dump(mode="json")

    # Limit how many candidate series to expand into issue queries; each
    # series → one extra `issues_list` API call.
    _MAX_SERIES_PER_SEARCH: ClassVar[int] = 20

    def _build_issue_params(
        self, profile: ComicProfile, series_id: int
    ) -> dict[str, Any]:
        """Build the `issues_list` params filtering on a resolved series id."""
        params: dict[str, Any] = {"series": series_id}
        # Strip leading zeros — Metron stores `number` without padding.
        if number := strip_issue_leading_zeros(profile.issue):
            params["number"] = number
        if profile.year is not None:
            params["cover_year"] = profile.year
        return params

    def _to_candidate(
        self, base_issue: Any, series_name: str | None = None
    ) -> Candidate:
        """
        Map a mokkari `BaseIssue` to a Candidate.

        ``series_name`` overrides the issue's series field when supplied — the
        two-step search has already resolved the series so we use its
        canonical name, since `BaseIssue.series` is sparse.
        """
        cover_year = base_issue.cover_date.year if base_issue.cover_date else None
        image_url = str(base_issue.image) if base_issue.image else None
        # `BaseIssue.series` may be a nested object or absent depending on
        # the endpoint. Prefer the resolved name passed in by `search`.
        bi_series = getattr(base_issue, "series", None)
        series = (
            series_name
            or (getattr(bi_series, "name", None) if bi_series is not None else None)
            or ""
        )
        summary = CandidateSummary(
            series=series,
            issue=base_issue.number,
            year=cover_year,
            publisher=None,  # BaseIssue from search omits publisher
            page_count=None,
            cover_url=image_url,
            variant_label=None,
        )
        return Candidate(
            source=self.name,
            issue_id=base_issue.id,
            summary=summary,
            url=str(base_issue.resource_url)
            if hasattr(base_issue, "resource_url") and base_issue.resource_url
            else "",
            precomputed_cover_hash=getattr(base_issue, "cover_hash", None) or None,
        )

    @with_retry()
    def search(self, profile: ComicProfile) -> list[Candidate]:
        """
        Search Metron for candidate issues matching the profile.

        The canonical two-step:

        1. ``series_list({"name": profile.series})`` — Metron's name filter
           is icontains+unaccent and splits on whitespace (AND-of-terms),
           so it tolerates case, accents, and word-order quirks.
        2. For each matched series, ``issues_list({"series": id, "number":
           N, "cover_year": Y})`` — issue lookup constrained by the
           resolved series id. Metron's `issue.number` is unpadded, so we
           strip leading zeros on the way in.

        The earlier single-call form passed `series_name` directly to
        ``issues_list``, which Metron does accept (icontains too) but it's
        an undocumented mokkari parameter and the two-step is what
        metron-tagger uses.
        """
        if not profile.series:
            logger.debug(
                f"online {self.name}: no series in profile; cannot search Metron "
                "(use --id metron:<id> for direct lookup)"
            )
            return []
        session = self._get_session()
        try:
            series_results = session.series_list(params={"name": profile.series})
        except Exception as exc:
            logger.warning(f"online {self.name}: series search failed: {exc}")
            raise
        if not series_results:
            logger.info(f"online {self.name}: no series match {profile.series!r}")
            return []
        series_results = list(series_results)[: self._MAX_SERIES_PER_SEARCH]
        sample_size = 5
        sample = ", ".join(
            f"{getattr(s, 'display_name', None) or s.name} ({s.id})"
            for s in series_results[:sample_size]
        )
        if len(series_results) > sample_size:
            sample += " ..."
        logger.debug(
            f"online {self.name}: {len(series_results)} candidate series for "
            f"{profile.series!r}: {sample}"
        )

        candidates: list[Candidate] = []
        for series in series_results:
            params = self._build_issue_params(profile, series.id)
            try:
                issues = session.issues_list(params=params)
            except Exception as exc:
                logger.warning(
                    f"online {self.name}: issue-list for series {series.id} "
                    f"({series.name!r}) failed: {exc}"
                )
                continue
            candidates.extend(self._to_candidate(i, series.name) for i in issues)
        return candidates
