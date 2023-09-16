"""Parsing methods."""
from collections.abc import Mapping
from dataclasses import dataclass
from logging import getLogger
from typing import Optional

from comicbox.box.synth import ComicboxSynthMixin
from comicbox.sources import MetadataSources, SourceFrom

LOG = getLogger(__name__)


@dataclass
class ParsedMetadata:
    """Parsed or Loaded metadata."""

    metadata: Mapping
    path: Optional[str] = None


class ComicboxParseLoadMixin(ComicboxSynthMixin):
    """Parsing methods."""

    def _call_load(
        self, schema_class, source_md
    ) -> tuple[Optional[Mapping], Optional[Mapping]]:
        """Load string or dict."""
        schema = schema_class(self._path)
        if isinstance(source_md, (str, bytes)):
            return schema.loads(source_md)
        return None, schema.load(source_md)

    def _load_unknown_metadata(
        self, label, source_md
    ) -> tuple[Optional[Mapping], Optional[Mapping]]:
        """Parse import data string from file trying many different file schemas."""
        success_parsed_md = None
        success_md = None
        for source in MetadataSources:
            if source.value.from_archive == SourceFrom.OTHER:
                continue
            try:
                schema_class = source.value.schema_class
                success_parsed_md, success_md = self._call_load(schema_class, source_md)
                if success_md:
                    LOG.debug(f"Parsed {label} with {schema_class.__name__}")
                    break
            except Exception as exc:
                LOG.debug(exc)
        if not success_md:
            reason = f"Unable to load {label}."
            raise ValueError(reason)
        return success_parsed_md, success_md

    def _load_schema_metadata(
        self, source_data
    ) -> tuple[Optional[Mapping], Optional[Mapping]]:
        """Parse one dict or string of metadata."""
        parsed_md, loaded_md = self._call_load(
            source_data.schema_class, source_data.metadata
        )
        # if loaded_md:
        return parsed_md, loaded_md
        # return None, None

    def _load_metadata(self, source, source_data):
        try:
            if source_data.metadata:
                if source_data.schema_class:
                    parsed_md, md = self._load_schema_metadata(source_data)
                else:
                    parsed_md, md = self._load_unknown_metadata(
                        source.value.label, source_data.metadata
                    )
                return parsed_md, md
        except Exception:
            name = source.value.schema_class.__name__
            LOG.exception(
                f"{self._path}: Unable to load {source.value.label}:{name} metadata"
            )
        return None, None

    def _set_loaded_metadata(self, source):
        source_metadata = self.get_source_metadata(source)
        if not source_metadata:
            return
        # Also populate the parsed_list
        parsed_list = []
        loaded_list = []
        for source_data in source_metadata:
            (
                parsed_md,
                md,
            ) = self._load_metadata(source, source_data)
            if parsed_md:
                parsed_list.append(ParsedMetadata(parsed_md, source_data.path))
            if md:
                loaded_list.append(ParsedMetadata(md, source_data.path))

        if loaded_list:
            if source not in self._loaded:
                self._loaded[source] = ()
            self._loaded[source] += tuple(loaded_list)
        if parsed_list:
            if source not in self._parsed:
                self._parsed[source] = ()
            self._parsed[source] += tuple(parsed_list)

    def get_parsed_metadata(self, source):
        """Get parsed metadata by key."""
        try:
            if source not in self._parsed:
                self._set_loaded_metadata(source)
            return self._parsed.get(source)
        except Exception as exc:
            LOG.warning(f"{self._path} Parsing or Loading {source.value.label}: {exc}")

    def get_loaded_metadata(self, source):
        """Get loaded metadata by key."""
        try:
            if source not in self._loaded:
                self._set_loaded_metadata(source)
            return self._loaded.get(source)
        except Exception as exc:
            LOG.warning(f"{self._path} Parsing or Loading {source.value.label}: {exc}")

    def _get_loaded_synthed_metadata(self):
        """Overlay the metadatas in precedence order."""
        # order of the md list is very important, lowest to highest
        # precedence.
        loaded_synthed_md = {}
        for source in MetadataSources:
            if parsed_md_list := self.get_loaded_metadata(source):
                self.synth_metadata_list(parsed_md_list, loaded_synthed_md)

        return loaded_synthed_md

    def get_loaded_synthed_metadata(self):
        """Get Synthed parsed metadata."""
        if not self._loaded_synth_metadata:
            self._loaded_synth_metadata = self._get_loaded_synthed_metadata()
        return self._loaded_synth_metadata
