"""Get Metadata mixin."""

from collections.abc import MutableMapping
from types import MappingProxyType

from glom import Assign, Delete, glom
from loguru import logger

from comicbox.box.archive import archive_close
from comicbox.box.computed import ComicboxComputed
from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox import ComicboxSchemaMixin


class ComicboxMetadata(ComicboxComputed):
    """Get Metadata mixin."""

    def _set_computed_merged_metadata_delete(self, merged_md):
        """Delete keys with glom."""
        sub_data = merged_md.get(ComicboxSchemaMixin.ROOT_TAG)
        for key_path in sorted(self._config.delete_keys):
            try:
                delete = Delete(key_path, ignore_missing=True)
                glom(sub_data, delete)
            except Exception as exc:
                logger.warning(f"Could not delete key path {key_path}: {exc}")

    def _set_computed_merged_metadata(self):
        merged_md = self.get_merged_metadata()
        computed_md = self.get_computed_metadata()
        merged_md = dict(merged_md)

        for computed_data in computed_md:
            computed_sub_data = computed_data.metadata.get(ComicboxSchemaMixin.ROOT_TAG)
            if computed_sub_data and computed_data.merger:
                computed_data.merger.merge(
                    merged_md,
                    computed_data.metadata,
                )
        self._set_computed_merged_metadata_delete(merged_md)
        self._metadata = MappingProxyType(merged_md)

    def _get_metadata(self) -> MappingProxyType:
        """Return the metadata from the archive."""
        if not self._metadata:
            self._set_computed_merged_metadata()
        return self._metadata

    @archive_close
    def get_metadata(self) -> MappingProxyType:
        """Return the metadata from the archive."""
        return self._get_metadata()

    def _embed_metadata(
        self, fmt: MetadataFormats, denormalized_metadata: MutableMapping, schema_class
    ):
        """Serialize metadata in the given format into a tag."""
        if not schema_class.EMBED_KEYPATH:
            return

        embedded_transform = fmt.value.transform_class(self._path)
        embedded_schema = embedded_transform.SCHEMA_CLASS()
        metadata = self._get_metadata()
        if (md := embedded_transform.from_comicbox(metadata)) and (
            embedded_value := embedded_schema.dumps(md)
        ):
            assign = Assign(
                schema_class.EMBED_KEYPATH,
                embedded_value,
                missing=dict,
            )
            glom(denormalized_metadata, assign)

    def _to_dict(
        self,
        fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
        embed_fmt: MetadataFormats | None = None,
    ):
        # Get schema instance.
        schema_class = fmt.value.schema_class
        schema = schema_class(path=self._path)

        # Get transformed md
        transform = fmt.value.transform_class(self._path)
        md = self._get_metadata()
        md = transform.from_comicbox(md)

        if embed_fmt:
            md = dict(md)
            self._embed_metadata(embed_fmt, md, schema_class)

        return schema, MappingProxyType(md)

    @archive_close
    def to_dict(
        self,
        fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
        embed_fmt: MetadataFormats | None = None,
        **kwargs,
    ) -> dict:
        """Get merged metadata as a dict."""
        schema, md = self._to_dict(fmt, embed_fmt)
        dump = schema.dump(md, **kwargs)
        return dict(dump)  # pyright:ignore[reportArgumentType, reportCallIssue]

    @archive_close
    def to_string(
        self,
        fmt: MetadataFormats = MetadataFormats.COMICBOX_YAML,
        embed_fmt: MetadataFormats | None = None,
        **kwargs,
    ) -> str:
        """Get mergeesized metadata as a string."""
        schema, md = self._to_dict(fmt, embed_fmt)
        return schema.dumps(md, **kwargs)
