"""Merge Metadata Methods."""

from types import MappingProxyType

from comicbox.box.normalize import ComicboxNormalize
from comicbox.merge import AdditiveMerger, Merger, UpdateMerger
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.sources import MetadataSources


class ComicboxMerge(ComicboxNormalize):
    """Merge Metadata Methods."""

    def _merge_metadata_by_source(
        self, source: MetadataSources, merged_md: dict, merger: type[Merger]
    ):
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

    def _set_merged_metadata(self):
        """Overlay the metadatas in precedence order."""
        # Order the md list by source precedence
        merged_md = {ComicboxSchemaMixin.ROOT_TAG: {}}
        merger = UpdateMerger if self._config.replace_metadata else AdditiveMerger
        for source in MetadataSources:
            self._merge_metadata_by_source(source, merged_md, merger)
        self._merged_metadata = MappingProxyType(merged_md)

    def get_merged_metadata(self):
        """Get merged normalized metadata."""
        if not self._merged_metadata:
            self._set_merged_metadata()
        return self._merged_metadata
