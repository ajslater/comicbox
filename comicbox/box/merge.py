"""Merge Metadata Methods."""

from types import MappingProxyType
from typing import TYPE_CHECKING

from comicbox.box.online_lookup import ComicboxOnlineLookup
from comicbox.config.settings import MergeMode
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
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
        self, source: MetadataSources, merged_sub_md: dict, merger: type[Merger]
    ) -> None:
        """Merge one source's metadatas into the accumulator, format order."""
        normalized_md_list = self.get_normalized_metadata(source)
        if not normalized_md_list:
            return
        for normalized_md in self._order_normalized_md_by_format(
            source, normalized_md_list
        ):
            if sub_md := normalized_md.get(ComicboxSchemaMixin.ROOT_TAG):
                merger.merge(merged_sub_md, sub_md)

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
        # Order the md list by source precedence (config-overridable;
        # falls back to the MetadataSources enum order when unset).
        merged_sub_md: dict = {}
        sources = self._config.read.merge_order or MetadataSources
        for source in sources:
            self._merge_metadata_by_source(
                source, merged_sub_md, self._merger_for_source(source)
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
