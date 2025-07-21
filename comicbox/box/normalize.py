"""Normalize schemas to Comicbox Schema."""

from types import MappingProxyType

from loguru import logger

from comicbox.box.load import ComicboxLoad, LoadedMetadata


class ComicboxNormalize(ComicboxLoad):
    """Normalize schemas to Comicbox Schema."""

    def _normalize_metadata(self, source, loaded_data):
        if not loaded_data.metadata:
            return None
        transform_class = loaded_data.fmt.value.transform_class
        try:
            transform = transform_class(self._path)
            return transform.to_comicbox(loaded_data.metadata)
        except Exception:
            reason = (
                f"{self._path}: Unable to normalize"
                f" {source.value.label}:{transform_class} metadata"
            )
            logger.exception(reason)

    def _set_normalized_metadata(self, source):
        loaded_metadata_list = self.get_loaded_metadata(source)
        if not loaded_metadata_list:
            return
        normalized_list = []
        for loaded_data in loaded_metadata_list:
            normalized_md = self._normalize_metadata(source, loaded_data)
            if normalized_md:
                normalized_md = MappingProxyType(normalized_md)
                loaded_md = LoadedMetadata(
                    normalized_md,
                    loaded_data.path,
                    loaded_data.fmt,
                    loaded_data.from_archive,
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
            logger.exception(f"{self._path} Normalizing {source.value.label}")
