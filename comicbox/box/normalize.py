"""Normalize schemas to Comicbox Schema."""

from logging import getLogger
from types import MappingProxyType

from comicbox.box.load import ComicboxLoadMixin, LoadedMetadata
from comicbox.sources import MetadataSources

LOG = getLogger(__name__)


class ComicboxNormalizeMixin(ComicboxLoadMixin):
    """Normalize schemas to Comicbox Schema."""

    def _normalize_metadata(self, source, loaded_data):
        if not loaded_data.metadata:
            return None
        transform_class = loaded_data.transform_class
        try:
            transform = transform_class(self._path)
            return transform.to_comicbox(loaded_data.metadata)
        except Exception:
            LOG.exception(
                f"{self._path}: Unable to normalize"
                f" {source.value.label}:{transform_class} metadata"
            )

    def _set_normalized_metadata(self, source):
        loaded_metadata_list = self.get_loaded_metadata(source)
        if not loaded_metadata_list:
            return
        normalized_list = []
        for loaded_data in loaded_metadata_list:
            normalized_md = self._normalize_metadata(source, loaded_data)
            if normalized_md:
                normalized_md = MappingProxyType(normalized_md)
                schema_class = loaded_data.transform_class.SCHEMA_CLASS
                loaded_md = LoadedMetadata(
                    normalized_md, schema_class, loaded_data.path
                )
                normalized_list.append(loaded_md)

        if normalized_list:
            if source not in self._normalized:
                self._normalized[source] = ()
            self._normalized[source] = (*self._normalized[source], *normalized_list)

    def get_normalized_metadata(self, source):
        """Get normalized metadata by source key."""
        try:
            if source not in self._normalized:
                self._set_normalized_metadata(source)
            return self._normalized.get(source)
        except Exception:
            LOG.exception(f"{self._path} Normalizing {source.value.label}")

    def _get_merged_metadata(self):
        """Overlay the metadatas in precedence order."""
        # order of the md list is very important, lowest to highest
        # precedence.
        merged_md = {}
        for source in MetadataSources:
            if normalized_md_list := self.get_normalized_metadata(source):
                self.merge_metadata_list(normalized_md_list, merged_md)
        if merged_md:
            return MappingProxyType(merged_md)
        return None

    def get_merged_metadata(self):
        """Get merged normalized metadata."""
        if not self._merged_metadata and (md := self._get_merged_metadata()):
            self._merged_metadata = md
        return self._merged_metadata
