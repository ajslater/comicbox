"""
Metron API source via mokkari.

M2 wires the `--id metron:N` path: instantiate a session with credentials
from the resolution chain, fetch one issue by id, dump the Pydantic model
to a plain dict, and hand it back to `ComicboxOnlineLookup` for transform
and merge. Search and ranking land in M3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from loguru import logger

from comicbox.formats import MetadataFormats
from comicbox.online.retry import with_retry
from comicbox.online.sources.base import OnlineSource
from comicbox.sources import MetadataSources
from comicbox.version import PACKAGE_NAME, VERSION

if TYPE_CHECKING:
    from mokkari.session import Session


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
