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

    def _build_search_params(self, profile: ComicProfile) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if profile.series:
            params["series_name"] = profile.series
        # Strip leading zeros — Metron stores `number` without padding.
        if number := strip_issue_leading_zeros(profile.issue):
            params["number"] = number
        if profile.year is not None:
            params["cover_year"] = profile.year
        return params

    def _to_candidate(self, base_issue: Any) -> Candidate:
        """Map a mokkari `BaseIssue` to a Candidate."""
        series = base_issue.series
        cover_year = base_issue.cover_date.year if base_issue.cover_date else None
        image_url = str(base_issue.image) if base_issue.image else None
        summary = CandidateSummary(
            series=series.name,
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
        """Search Metron for candidates matching the profile."""
        params = self._build_search_params(profile)
        if not params:
            logger.debug(
                f"online {self.name}: no search criteria from profile, skipping"
            )
            return []
        session = self._get_session()
        try:
            results = session.issues_list(params=params)
        except Exception as exc:
            logger.warning(f"online {self.name}: search failed: {exc}")
            raise
        return [self._to_candidate(r) for r in results]
