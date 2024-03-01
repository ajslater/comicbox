"""Parsing methods."""

from collections.abc import Mapping
from dataclasses import dataclass
from logging import DEBUG, WARNING, getLogger
from traceback import format_exc
from types import MappingProxyType

from comicbox.box.init import SourceData
from comicbox.box.merge import ComicboxMergeMixin
from comicbox.sources import MetadataSources, SourceFrom
from comicbox.transforms.base import BaseTransform

LOG = getLogger(__name__)


@dataclass
class LoadedMetadata(SourceData):
    """Loaded metadata."""

    metadata: Mapping  # type: ignore


class ComicboxLoadMixin(ComicboxMergeMixin):
    """Parsing methods."""

    def _call_load(self, schema_class, source_md) -> Mapping | None:
        """Load string or dict."""
        schema = schema_class(path=self._path)
        if isinstance(source_md, str | bytes):
            return schema.loads(source_md)
        return schema.load(source_md)

    def _except_on_load(self, source, exc, level=WARNING):
        """When loading fails warn or give stack trace in debug."""
        name = source.value.transform_class.SCHEMA_CLASS.__name__
        LOG.log(
            level,
            f"{self._path}: Unable to load {source.value.label}:{name} metadata: {exc}",
        )
        if LOG.getEffectiveLevel() == DEBUG:
            LOG.debug(format_exc())

    def _load_unknown_metadata(
        self, label, source_md
    ) -> tuple[Mapping | None, type[BaseTransform] | None]:
        """Parse import data string from file trying many different file schemas."""
        success_md = None
        transform_class = None
        for source in reversed(MetadataSources):
            if source.value.from_archive == SourceFrom.OTHER:
                continue
            try:
                schema_class = source.value.transform_class.SCHEMA_CLASS
                success_md = self._call_load(schema_class, source_md)
                if success_md:
                    LOG.debug(f"Parsed {label} with {schema_class.__name__}")
                    transform_class = source.value.transform_class
                    break
            except Exception as exc:
                self._except_on_load(source, exc, level=DEBUG)
        if not success_md:
            reason = f"Unable to load {label}."
            raise ValueError(reason)
        return success_md, transform_class

    def _load_metadata(self, source, source_data):
        try:
            if source_data.metadata:
                if source_data.transform_class:
                    transform_class = source_data.transform_class
                    md = self._call_load(
                        transform_class.SCHEMA_CLASS, source_data.metadata
                    )
                else:
                    md, transform_class = self._load_unknown_metadata(
                        source.value.label, source_data.metadata
                    )
                if md and transform_class:
                    return MappingProxyType(md), transform_class
        except Exception as exc:
            self._except_on_load(source, exc)
        return None, None

    def _set_loaded_metadata(self, source):
        source_metadata = self.get_source_metadata(source)
        if not source_metadata:
            return
        # Also populate the parsed_list
        loaded_list = []
        for source_data in source_metadata:
            md, transform_class = self._load_metadata(source, source_data)
            if md:
                loaded_list.append(
                    LoadedMetadata(md, transform_class, source_data.path)
                )
        if loaded_list:
            if source not in self._loaded:
                self._loaded[source] = ()
            self._loaded[source] += tuple(loaded_list)

    def get_loaded_metadata(self, source):
        """Get loaded metadata by key."""
        try:
            if source not in self._loaded:
                self._set_loaded_metadata(source)
            return self._loaded.get(source)
        except Exception as exc:
            LOG.warning(f"{self._path} Parsing or Loading {source.value.label}: {exc}")
