"""
OnlineSource abstract base class.

Each concrete subclass wraps one upstream API client (mokkari, simyan, …)
behind a uniform contract the lookup mixin can drive.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from platformdirs import user_cache_path

if TYPE_CHECKING:
    from comicbox.config.settings import OnlineSettings, OnlineSourceCredentials
    from comicbox.formats import MetadataFormats
    from comicbox.sources import MetadataSources


class OnlineSource(ABC):
    """
    Contract every online provider must implement.

    Subclasses set the three `ClassVar` identifiers below and implement
    `is_configured`, `get`, and (in M3 onward) `search`.
    """

    name: ClassVar[str]
    metadata_source: ClassVar[MetadataSources]
    metadata_format: ClassVar[MetadataFormats]

    def __init__(
        self,
        credentials: OnlineSourceCredentials,
        settings: OnlineSettings,
    ) -> None:
        """Store refs needed for client construction."""
        self._credentials = credentials
        self._settings = settings

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the source has every credential it needs."""

    @abstractmethod
    def get(self, issue_id: int) -> dict[str, Any]:
        """
        Fetch a full issue record by upstream id, return as a plain dict.

        The shape is whatever the upstream library returns post-`model_dump`
        (or equivalent). Comicbox's per-source transform converts it to the
        internal schema.
        """

    def cache_db_path(self, suffix: str = "cache") -> Path:
        """
        Resolve the cache sqlite path for this source.

        Honours `online.cache_dir` when set; otherwise uses the platformdirs
        user cache path for comicbox. Creates the parent directory.
        """
        cache_dir = self._settings.cache_dir
        if cache_dir is None:
            cache_dir = user_cache_path("comicbox") / "online"
        cache_dir = Path(cache_dir).expanduser()
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{self.name}_{suffix}.sqlite"
