"""Merge Metadata Methods."""

from collections.abc import Iterable, Mapping
from datetime import date
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from comicbox.box.online_lookup import ONLINE_SOURCE_BY_NAME, ComicboxOnlineLookup
from comicbox.config.settings import MergeMode
from comicbox.enums.comicbox import IdSources
from comicbox.formats.comicbox.schema import (
    COVER_DATE_KEY,
    DATE_KEY,
    DAY_KEY,
    IDENTIFIERS_KEY,
    MONTH_KEY,
    PARTIAL_COVER_DATE_KEY,
    YEAR_KEY,
    ComicboxSchemaMixin,
)
from comicbox.formats.sources import MetadataSources
from comicbox.merge import AdditiveMerger, Merger, ReplaceMerger, UpdateMerger

if TYPE_CHECKING:
    from comicbox.formats import MetadataFormats

# Map the public MergeMode enum onto the existing merger classes. The
# three modes correspond 1:1; see MergeMode docstring for semantics.
_MERGER_BY_MODE: dict[MergeMode, type[Merger]] = {
    MergeMode.ADDITIVE: AdditiveMerger,
    MergeMode.UPDATE: UpdateMerger,
    MergeMode.REPLACE: ReplaceMerger,
}

# Sources whose metadata the caller supplied to *this* run: the write
# API's patch, `-m` on the command line, `--import` files, and the
# config's own metadata block. `write.merge_mode` describes how that
# supplied metadata overlays the comic's existing tags, so it applies to
# exactly these. Everything else — the archive's own files, its comment,
# its filename, an online lookup's answer — is metadata comicbox
# discovered, and discovery is always accumulated additively.
_PATCH_SOURCES = frozenset(
    {
        MetadataSources.CONFIG,
        MetadataSources.CLI,
        MetadataSources.IMPORT_FILE,
        MetadataSources.API,
    }
)

_ONLINE_SOURCES = frozenset(ONLINE_SOURCE_BY_NAME.values())

# Each online source's own key under `identifiers`. IdSources() fails at
# import if a source name ever stops being an identifier key.
_OWN_ID_KEY: MappingProxyType[MetadataSources, str] = MappingProxyType(
    {source: IdSources(name).value for name, source in ONLINE_SOURCE_BY_NAME.items()}
)


def _rank_online_sources(run_order: Iterable[str]) -> tuple[MetadataSources, ...]:
    """
    Order every source for the merge, the online ones by run order.

    Each source overlays the ones merged before it, so the first source
    in the run order goes last and wins every single-valued tag the
    online sources disagree on; lists and keyed tags still combine. An
    online source with answers that the run order leaves out ranks below
    every listed one, in enum order. Every other source keeps its place,
    and the online sources keep their slots in the enum among them.
    """
    listed = tuple(
        dict.fromkeys(
            ONLINE_SOURCE_BY_NAME[name]
            for name in run_order
            if name in ONLINE_SOURCE_BY_NAME
        )
    )
    unlisted = (
        src for src in MetadataSources if src in _ONLINE_SOURCES and src not in listed
    )
    ranked = iter((*unlisted, *reversed(listed)))
    return tuple(
        next(ranked) if src in _ONLINE_SOURCES else src for src in MetadataSources
    )


def _cross_references(
    source: MetadataSources, self_identified: frozenset[str]
) -> frozenset[str]:
    """Name the ids ``source`` gives for other online sources that gave their own."""
    if (own := _OWN_ID_KEY.get(source)) is None:
        return frozenset()
    return self_identified - {own}


def _without_ids(sub_md: Mapping[str, Any], keys: frozenset[str]) -> Mapping[str, Any]:
    """Drop these keys from a source's identifiers, leaving the rest as given."""
    identifiers = sub_md.get(IDENTIFIERS_KEY)
    if not isinstance(identifiers, Mapping) or not keys & identifiers.keys():
        return sub_md
    kept = {key: value for key, value in identifiers.items() if key not in keys}
    return {**sub_md, IDENTIFIERS_KEY: kept}


_DATE_PART_KEYS = (YEAR_KEY, MONTH_KEY, DAY_KEY)


def _named_parts(date_md: Mapping[str, Any]) -> dict[str, Any]:
    """Name the year, month and day a source's date gives, from either form."""
    parts: dict[str, Any] = {}
    if isinstance(cover_date := date_md.get(COVER_DATE_KEY), date):
        parts = dict(
            zip(
                _DATE_PART_KEYS,
                (cover_date.year, cover_date.month, cover_date.day),
                strict=True,
            )
        )
    parts.update(
        {
            key: value
            for key in _DATE_PART_KEYS
            if (value := date_md.get(key)) is not None
        }
    )
    return parts


def _states_a_cover_date(date_md: Mapping[str, Any]) -> bool:
    """Tell whether a source's date states a cover date, whole or partial."""
    return isinstance(date_md.get(COVER_DATE_KEY), date) or bool(
        date_md.get(PARTIAL_COVER_DATE_KEY)
    )


def _drop_a_contradicted_date(
    merged: dict[str, Any], incoming: Mapping[str, Any]
) -> None:
    """
    Drop the date below where a higher source's cover date contradicts it.

    Merged part by part, a higher source's ``2006-07`` cover date kept a
    lower 1950-11-01's day, or its cover date, which the computed date then
    rebuilt; and a lower source's year, month and day outranked a higher
    one's cover date. A cover date is one fact: where it disagrees with the
    date below on any part both name, that date's cover date and parts go,
    and the higher one stands alone. Where they agree, the lower one's other
    parts stay, so a day only it knows is kept. A higher source that gives
    only separate parts (a year, a month, a day) overrides those parts and
    leaves the others. A store date is not part of it.
    """
    old = merged.get(DATE_KEY)
    new = incoming.get(DATE_KEY)
    if not isinstance(old, dict) or not isinstance(new, Mapping):
        return
    if not _states_a_cover_date(new):
        return
    below = _named_parts(old)
    if any(
        key in below and below[key] != part for key, part in _named_parts(new).items()
    ):
        for key in (*_DATE_PART_KEYS, COVER_DATE_KEY):
            old.pop(key, None)


def merge_source(
    merged: dict[str, Any], incoming: Mapping[str, Any], merger: type[Merger]
) -> None:
    """Merge one source's metadata over the sources below it."""
    _drop_a_contradicted_date(merged, incoming)
    merger.merge(merged, incoming)
    if isinstance(merged_date := merged.get(DATE_KEY), dict):
        # The source's own mark that it stated a cover date has done its work.
        merged_date.pop(PARTIAL_COVER_DATE_KEY, None)


class ComicboxMerge(ComicboxOnlineLookup):
    """Merge Metadata Methods."""

    @staticmethod
    def _order_normalized_md_by_format(
        source: MetadataSources, normalized_md_list: tuple
    ) -> list:
        """
        Order one source's normalized metadatas by format precedence.

        Declared-first wins, so the buckets are seeded in reverse and the
        highest-precedence format is merged last. A format the source
        doesn't declare gets a bucket of its own at the end: the public
        `add_metadata(md, fmt=...)` accepts any format, including the
        online ones no source lists, and a fixed-key lookup raised
        KeyError on all of them. Same for the `fmt is None` bucket, which
        used to be dropped outright.
        """
        format_dict: dict[MetadataFormats | None, list] = {
            fmt: [] for fmt in reversed(source.value.formats)
        }
        for loaded in normalized_md_list:
            format_dict.setdefault(loaded.fmt, []).append(loaded.metadata)
        return [md for md_list in format_dict.values() for md in md_list]

    def _merge_metadata_by_source(
        self,
        source: MetadataSources,
        merged_sub_md: dict,
        merger: type[Merger],
        dropped_ids: frozenset[str],
    ) -> None:
        """Merge one source's metadatas into the accumulator, format order."""
        normalized_md_list = self.get_normalized_metadata(source)
        if not normalized_md_list:
            return
        for normalized_md in self._order_normalized_md_by_format(
            source, normalized_md_list
        ):
            if sub_md := normalized_md.get(ComicboxSchemaMixin.ROOT_TAG):
                merge_source(merged_sub_md, _without_ids(sub_md, dropped_ids), merger)

    def _self_identified_online_sources(self) -> frozenset[str]:
        """Name the online sources whose own answer carries their own id."""
        found: set[str] = set()
        for source, own in _OWN_ID_KEY.items():
            for loaded in self.get_normalized_metadata(source) or ():
                sub_md = loaded.metadata.get(ComicboxSchemaMixin.ROOT_TAG) or {}
                if own in (sub_md.get(IDENTIFIERS_KEY) or {}):
                    found.add(own)
        return frozenset(found)

    def _merger_for_source(self, source: MetadataSources) -> type[Merger]:
        """
        Cross-source reads are additive; only a patch honors ``merge_mode``.

        Selecting every source's merger from ``write.merge_mode`` made a
        plain read depend on write settings — `to_dict()` returned
        different metadata under a non-default mode — and under `update`
        it was lossy: `dict.update` at the root meant the last source
        carrying a key dropped every earlier source's contribution to it
        wholesale.
        """
        if source in _PATCH_SOURCES:
            return _MERGER_BY_MODE[self._config.write.merge_mode]
        return AdditiveMerger

    def _set_merged_metadata(self) -> None:
        """Overlay the metadatas in precedence order."""
        # An explicit read.merge_order is the whole order. Unset, it is
        # the MetadataSources enum order with the online sources ranked
        # by run order, so the first-listed online source wins.
        merged_sub_md: dict = {}
        sources = self._config.read.merge_order or _rank_online_sources(
            self._online_run_order(self._config.online)
        )
        # Whatever the order, an online source is the authority on its own
        # id: Metron's cv_id, a cross-reference that can go stale, gives
        # way to Comic Vine's own id when Comic Vine answered too, and
        # still fills the gap when it did not. Patches are untouched.
        self_identified = self._self_identified_online_sources()
        for source in sources:
            self._merge_metadata_by_source(
                source,
                merged_sub_md,
                self._merger_for_source(source),
                _cross_references(source, self_identified),
            )
        self._merged_metadata = MappingProxyType(
            {ComicboxSchemaMixin.ROOT_TAG: merged_sub_md}
        )

    def get_merged_metadata(self) -> MappingProxyType:
        """Get merged normalized metadata."""
        if not self._merged_metadata:
            self.run_online_lookup()
            self._set_merged_metadata()
        return self._merged_metadata
