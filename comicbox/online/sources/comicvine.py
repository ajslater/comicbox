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
from comicbox.online.profile import Candidate, CandidateSummary
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

        kwargs: dict[str, Any] = {
            "api_key": self._credentials.api_key,
            "cache": self._get_cache(),
            "user_agent": f"{PACKAGE_NAME}/{VERSION}",
        }
        if self._credentials.url:
            kwargs["base_url"] = self._credentials.url
        return Comicvine(**kwargs)

    @with_retry()
    def get(self, issue_id: int) -> dict[str, Any]:
        """Fetch one ComicVine issue by id; return its model dump."""
        session = self._get_session()
        issue = session.get_issue(issue_id)
        return issue.model_dump(mode="json")

    def _build_search_params(self, profile: ComicProfile) -> dict[str, Any]:
        """Build a CV `filter` string from the profile."""
        clauses: list[str] = []
        if profile.series:
            clauses.append(f"name:{profile.series}")
        if profile.issue:
            clauses.append(f"issue_number:{profile.issue}")
        # CV uses a date range filter; cover_date single value isn't supported.
        if profile.year is not None:
            clauses.append(f"cover_date:{profile.year}-01-01|{profile.year}-12-31")
        if not clauses:
            return {}
        return {"filter": ",".join(clauses)}

    def _to_candidate(self, basic_issue: Any) -> Candidate:
        """Map simyan's `BasicIssue` to a Candidate."""
        volume = basic_issue.volume
        image = basic_issue.image
        cover_year = basic_issue.cover_date.year if basic_issue.cover_date else None
        thumb = str(image.thumb_url) if image and image.thumb_url else None
        site_url = str(basic_issue.site_url) if basic_issue.site_url else ""
        summary = CandidateSummary(
            series=volume.name or "" if volume else "",
            issue=basic_issue.number or "",
            year=cover_year,
            publisher=None,  # BasicIssue from search doesn't include publisher
            page_count=None,
            cover_url=thumb,
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

    @with_retry()
    def search(self, profile: ComicProfile) -> list[Candidate]:
        """Search ComicVine and return ranked-stage candidates."""
        params = self._build_search_params(profile)
        if not params:
            logger.debug(
                f"online {self.name}: no search criteria from profile, skipping"
            )
            return []
        session = self._get_session()
        try:
            results = session.list_issues(params=params)
        except Exception as exc:
            logger.warning(f"online {self.name}: search failed: {exc}")
            raise
        return [self._to_candidate(r) for r in results]


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
