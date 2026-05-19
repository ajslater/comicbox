"""Merge Metadata Methods."""

from types import MappingProxyType

from comicbox.box.online_lookup import ComicboxOnlineLookup
from comicbox.config.settings import WriteMode
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
from comicbox.formats.sources import MetadataSources
from comicbox.merge import AdditiveMerger, Merger, ReplaceMerger, UpdateMerger

# Map the public WriteMode enum onto the existing merger classes. The
# three modes correspond 1:1; see WriteMode docstring for semantics.
_MERGER_BY_MODE: dict[WriteMode, type[Merger]] = {
    WriteMode.ADDITIVE: AdditiveMerger,
    WriteMode.UPDATE: UpdateMerger,
    WriteMode.REPLACE: ReplaceMerger,
}


class ComicboxMerge(ComicboxOnlineLookup):
    """Merge Metadata Methods."""

    def _merge_metadata_by_source(
        self, source: MetadataSources, merged_md: dict, merger: type[Merger]
    ) -> None:
        """Order the source md list by format precedence."""
        format_dict = {}
        # Set the format dict order to be the one declared in source.formats
        for fmt in reversed(source.value.formats):
            format_dict[fmt] = []
        if normalized_md_list := self.get_normalized_metadata(source):
            # load the mds into the format dict by format.
            for loaded in normalized_md_list:
                format_dict[loaded.fmt] += [loaded.metadata]
            # load the mds into the source list in format order.
            for format_normalized_md_list in format_dict.values():
                for normalized_md in format_normalized_md_list:
                    merger.merge(merged_md, normalized_md)

    def _resolve_merger(self) -> type[Merger]:
        """
        Pick the merger class for this write based on WriteSettings.

        ``write.mode`` is the authoritative knob; the legacy ``write.replace``
        bool is honored as a back-compat alias for ``mode=update`` when the
        caller didn't set mode explicitly.
        """
        write = self._config.write
        mode = write.mode
        if mode is WriteMode.ADDITIVE and write.replace:
            # Caller used the legacy bool; preserve its historical
            # UpdateMerger semantics.
            mode = WriteMode.UPDATE
        return _MERGER_BY_MODE[mode]

    def _set_merged_metadata(self) -> None:
        """Overlay the metadatas in precedence order."""
        # Order the md list by source precedence (config-overridable;
        # falls back to the MetadataSources enum order when unset).
        merged_md = {ComicboxSchemaMixin.ROOT_TAG: {}}
        merger = self._resolve_merger()
        sources = self._config.read.merge_order or MetadataSources
        for source in sources:
            self._merge_metadata_by_source(source, merged_md, merger)
        self._merged_metadata = MappingProxyType(merged_md)

    def get_merged_metadata(self) -> MappingProxyType:
        """Get merged normalized metadata."""
        if not self._merged_metadata:
            self.run_online_lookup()
            self._set_merged_metadata()
        return self._merged_metadata
