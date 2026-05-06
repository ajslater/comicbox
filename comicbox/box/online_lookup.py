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
from comicbox.online.matcher import OnlineMatcher, Resolution, ResolutionKind
from comicbox.online.profile import ComicProfile, parse_issue_int, parse_year
from comicbox.online.sources.metron import MetronOnlineSource
from comicbox.sources import MetadataSources

if TYPE_CHECKING:
    from comicbox.config.settings import OnlineSettings
    from comicbox.online.profile import Candidate
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

    def _build_profile(self) -> ComicProfile:
        """Read the non-online merged-so-far metadata into a ComicProfile."""
        # Collect from non-online normalized sources, first-wins.
        series: str | None = None
        issue: str | None = None
        year: int | None = None
        publisher: str | None = None
        page_count: int | None = None
        for src in MetadataSources:
            if src in _ONLINE_SOURCE_ENUMS:
                continue
            normalized = self.get_normalized_metadata(src)
            if not normalized:
                continue
            for loaded in normalized:
                md = dict(loaded.metadata)
                if series is None:
                    series = glom(md, "comicbox.series.name", default=None)
                if issue is None:
                    issue = glom(md, "comicbox.issue.name", default=None)
                if year is None:
                    raw_year = glom(md, "comicbox.date.year", default=None) or glom(
                        md, "comicbox.date.cover_date", default=None
                    )
                    year = parse_year(raw_year)
                if publisher is None:
                    publisher = glom(md, "comicbox.publisher.name", default=None)
                if page_count is None:
                    page_count = glom(md, "comicbox.page_count", default=None)
        return ComicProfile(
            series=series,
            issue=issue,
            issue_int=parse_issue_int(issue),
            year=year,
            publisher=publisher,
            page_count=page_count,
        )

    def _accept_candidate(
        self, source: OnlineSource, candidate: Candidate
    ) -> None:
        """Fetch the full record for an accepted candidate and inject it."""
        self._fetch_explicit_id(source, candidate.issue_id)

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
        self, candidates: list[Candidate]
    ) -> Resolution:
        matcher = OnlineMatcher()
        ranked = matcher.rank(
            self._build_profile(),
            candidates,
            local_hash_provider=self._local_cover_phash,
            threshold=self._config.online.confidence_threshold,
        )
        return matcher.resolve(ranked, self._config.online)

    def _search_path(self, source: OnlineSource) -> None:
        """Search → rank → resolve → fetch on accept."""
        profile = self._build_profile()
        try:
            candidates = source.search(profile)
        except Exception as exc:
            logger.warning(f"online {source.name}: search failed: {exc}")
            return
        if not candidates:
            logger.info(f"online {source.name}: no candidates returned for profile")
            return
        resolution = self._resolve_with_matcher(candidates)
        if resolution.kind is ResolutionKind.AUTO_WRITE and resolution.chosen:
            logger.info(
                f"online {source.name}: auto-writing "
                f"id={resolution.chosen.issue_id} "
                f"(score={resolution.chosen.score:.2f})"
            )
            self._accept_candidate(source, resolution.chosen)
            return
        if resolution.kind is ResolutionKind.NO_MATCH:
            logger.info(f"online {source.name}: no match cleared min_confidence")
            return
        if resolution.kind is ResolutionKind.SKIP:
            top_score = resolution.candidates[0].score if resolution.candidates else 0
            logger.info(
                f"online {source.name}: skip-multiple, top={top_score:.2f}"
            )
            return
        # ResolutionKind.PROMPT — interactive UX lands in M5.
        reason = (
            f"online {source.name}: ambiguous match (top_score="
            f"{resolution.candidates[0].score:.2f}); interactive prompt is M5"
        )
        raise NotImplementedError(reason)

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
            self._fetch_explicit_id(source, issue_id)
            return
        self._search_path(source)

    def run_online_lookup(self) -> None:
        """Idempotent: populate online MetadataSources once per box instance."""
        if self._online_lookup_already_done():
            return
        self._mark_online_lookup_done()
        if not self._config.online.enabled:
            return
        for source in self._build_active_online_sources():
            self._lookup_one_source(source)
