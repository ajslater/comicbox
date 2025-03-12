"""Merge Metadata Methods."""

from types import MappingProxyType

from comicbox.box.normalize import ComicboxNormalizeMixin
from comicbox.schemas.merge import merge_metadata_list
from comicbox.sources import MetadataSources


class ComicboxMergeMixin(ComicboxNormalizeMixin):
    """Merge Metadata Methods."""

    def _get_merged_metadata_by_source(self, source: MetadataSources):
        """Order the source md list by format precedence."""
        source_md_list = []
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
                source_md_list.extend(format_normalized_md_list)
        return source_md_list

    def _set_merged_metadata(self):
        """Overlay the metadatas in precedence order."""
        # Order the md list by source precedence
        md_list = []
        for source in MetadataSources:
            source_md_list = self._get_merged_metadata_by_source(source)
            md_list.extend(source_md_list)

        merged_md = merge_metadata_list(md_list, self._config)
        if merged_md:
            self._merged_metadata = MappingProxyType(merged_md)

    def get_merged_metadata(self):
        """Get merged normalized metadata."""
        if not self._merged_metadata:
            self._set_merged_metadata()
        return self._merged_metadata
