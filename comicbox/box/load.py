"""Parsing methods."""

from collections.abc import Mapping
from dataclasses import dataclass
from logging import DEBUG, WARNING
from pathlib import Path
from traceback import format_exc
from types import MappingProxyType

from glom import Assign, glom
from loguru import logger
from ruamel.yaml import YAML
from simplejson.errors import JSONDecodeError

from comicbox.box.init import SourceData
from comicbox.box.sources import ComicboxSources
from comicbox.fields.collection_fields import EmbeddedStringSetField
from comicbox.formats import MetadataFormats
from comicbox.sources import MetadataSources


@dataclass
class LoadedMetadata:
    """Loaded Metadata."""

    metadata: Mapping
    path: Path | None = None
    fmt: MetadataFormats | None = None
    from_archive: bool = False


class ComicboxLoad(ComicboxSources):
    """Parsing methods."""

    def _load_cli_yaml(self, fmt, schema, source_md):
        result = {}
        try:
            md = YAML().load(source_md) if isinstance(source_md, str) else source_md
            result = schema.load(md)
            if not result:
                # try a wrapped version
                key_path = fmt.value.schema_class.ROOT_KEYPATH
                assign = Assign(key_path, md, missing=dict)
                wrapped_md = glom({}, assign)
                result = schema.load(wrapped_md)
        except Exception as exc:
            logger.debug(
                f'Attempt to load CLI Metadata as {fmt.value.label} "{source_md}": {exc}'
            )
        return result

    def _call_load(
        self, source: MetadataSources, fmt: MetadataFormats, source_md
    ) -> Mapping | None:
        """Load string or dict."""
        schema_class = fmt.value.schema_class
        schema = schema_class(path=self._path)
        if source == MetadataSources.CLI:
            return self._load_cli_yaml(fmt, schema, source_md)

        if isinstance(source_md, str | bytes):
            return schema.loads(source_md)  # pyright: ignore[reportReturnType]

        return schema.load(source_md)  # pyright: ignore[reportReturnType]

    @staticmethod
    def _is_comment_not_json(source, exc):
        """Is this an archive comment and not JSON."""
        return (
            source == MetadataSources.ARCHIVE_COMMENT
            and isinstance(exc, JSONDecodeError)
            and exc.pos == 0
            and exc.lineno == 1
            and exc.colno == 1
        )

    def _except_on_load(
        self,
        source: MetadataSources,
        fmt: MetadataFormats | None,
        exc: Exception,
        level=WARNING,
    ):
        """When loading fails warn or give stack trace in debug."""
        name = fmt.value.schema_class.__name__ if fmt else "Unknown Schema"
        if self._is_comment_not_json(source, exc):
            # Demote not json as json to debug warning because there are so many
            # archive comments that are not intended to be CBI
            logger.debug(f"{self._path}: {name} metadata is not JSON: {exc}")
            return

        logger.log(
            level,
            f"{self._path}: Unable to load {source.value.label}:{name} metadata: {exc}",
        )
        logger.opt(lazy=True).trace("{e}", e=format_exc())

    def _load_unknown_metadata(
        self, source: MetadataSources, data
    ) -> tuple[Mapping | None, MetadataFormats | None]:
        """Parse import data string from file trying many different file schemas."""
        success_md = None
        fmt = None
        for fmt in source.value.formats:
            if not fmt.value.enabled:
                continue
            try:
                if (success_md := self._call_load(source, fmt, data)) and glom(
                    success_md, fmt.value.schema_class.ROOT_KEYPATH
                ):
                    logger.debug(f"Parsed {source.value.label} with {fmt.value.label}")
                    break
            except Exception as exc:
                self._except_on_load(source, fmt, exc, level=DEBUG)
        if not success_md:
            reason = f"Unable to load {source.value.label}."
            raise ValueError(reason)
        return success_md, fmt

    def _load_metadata(
        self, source: MetadataSources, source_data: SourceData | None
    ) -> tuple[MappingProxyType | None, MetadataFormats | None]:
        if not source_data:
            return None, None
        fmt = source_data.fmt
        try:
            if fmt:
                md = self._call_load(source, fmt, source_data.data)
            else:
                md, fmt = self._load_unknown_metadata(source, source_data.data)
            if md and fmt:
                schema_class = fmt.value.schema_class
                embedded_source = glom(md, schema_class.EMBED_KEYPATH, default=None)
                if EmbeddedStringSetField.is_embedded_metadata(embedded_source):
                    self.add_source(MetadataSources.EMBEDDED, embedded_source)
                return MappingProxyType(md), fmt
        except Exception as exc:
            self._except_on_load(source, fmt, exc)
        return None, None

    def _set_loaded_metadata(self, source):
        source_metadata = self.get_source_metadata(source)
        if not source_metadata:
            return
        # Also populate the parsed_list
        loaded_list = []
        for source_data in source_metadata:
            md, fmt = self._load_metadata(source, source_data)
            if md:
                loaded_md = LoadedMetadata(
                    md, source_data.path, fmt, source_data.from_archive
                )
                loaded_list.append(loaded_md)

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
            logger.warning(
                f"{self._path} Parsing or Loading {source.value.label}: {exc}"
            )
