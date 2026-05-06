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

from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar

from glom import glom
from loguru import logger

from comicbox.box.normalize import ComicboxNormalize
from comicbox.online.sources.metron import MetronOnlineSource
from comicbox.sources import MetadataSources

if TYPE_CHECKING:
    from comicbox.config.settings import OnlineSettings
    from comicbox.online.sources.base import OnlineSource


# Source factories let tests substitute mocks without monkey-patching imports.
OnlineSourceFactory = "Callable[[Any, OnlineSettings], OnlineSource]"


_DEFAULT_SOURCE_FACTORIES: MappingProxyType[str, Any] = MappingProxyType(
    {
        "metron": MetronOnlineSource,
        # M6 adds: "comicvine": ComicVineOnlineSource,
    }
)

# Online MetadataSources entries. Used to skip self when checking for existing
# identifiers under `--ignore-existing`.
_ONLINE_SOURCE_ENUMS: frozenset[MetadataSources] = frozenset(
    {MetadataSources.METRON_API, MetadataSources.COMICVINE_API}
)


class ComicboxOnlineLookup(ComicboxNormalize):
    """Pulls online metadata into the source pool before merge runs."""

    # Class-level so tests can override (and per-instance attrs override that).
    _ONLINE_SOURCE_FACTORIES: ClassVar[MappingProxyType[str, Any]] = (
        _DEFAULT_SOURCE_FACTORIES
    )

    def _online_lookup_already_done(self) -> bool:
        return getattr(self, "_online_lookup_done_flag", False)

    def _mark_online_lookup_done(self) -> None:
        self._online_lookup_done_flag = True

    def _build_active_online_sources(self) -> list[OnlineSource]:
        """Resolve which configured online sources participate in this run."""
        online: OnlineSettings = self._config.online
        selected = online.selected_sources
        active: list[OnlineSource] = []
        for name, factory in self._ONLINE_SOURCE_FACTORIES.items():
            if selected is not None and name not in selected:
                continue
            creds = online.sources.get(name)
            if not creds:
                continue
            source = factory(creds, online)
            if not source.is_configured():
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

    def _fetch_explicit_id(
        self, source: OnlineSource, issue_id: int
    ) -> None:
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

    def _lookup_one_source(self, source: OnlineSource) -> None:
        explicit_ids = self._config.online.explicit_ids
        issue_id = explicit_ids.get(source.name)
        if issue_id is None:
            # M2 only runs the explicit-id path. M3 adds search.
            return
        if self._config.online.ignore_existing and self._has_existing_identifier(
            source.name
        ):
            logger.info(
                f"online {source.name}: --ignore-existing skipping "
                f"(already has {source.name} id)"
            )
            return
        self._fetch_explicit_id(source, issue_id)

    def run_online_lookup(self) -> None:
        """Idempotent: populate online MetadataSources once per box instance."""
        if self._online_lookup_already_done():
            return
        self._mark_online_lookup_done()
        if not self._config.online.enabled:
            return
        for source in self._build_active_online_sources():
            self._lookup_one_source(source)
