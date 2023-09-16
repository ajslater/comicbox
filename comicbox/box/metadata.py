"""Get Metadata mixin."""
from typing import Optional

from comicbox.box.archive import archive_close
from comicbox.box.computed import ComicboxComputedMixin
from comicbox.schemas.base import sort_dict
from comicbox.schemas.comicbox_base import ComicboxBaseSchema, SchemaConfig
from comicbox.schemas.yaml import ComicboxYamlSchema


class ComicboxMetadataMixin(ComicboxComputedMixin):
    """Get Metadata mixin."""

    def _set_metadata(self):
        # collect metadata
        computed_synthed_metadata = self.get_computed_synthed_metadata()
        self._metadata = sort_dict(computed_synthed_metadata)

    def _get_metadata(self) -> dict:
        """Return the metadata from the archive."""
        if not self._metadata:
            self._set_metadata()
        return self._metadata

    @archive_close
    def get_metadata(self) -> dict:
        """Return the metadata from the archive."""
        return self._get_metadata()

    @archive_close
    def to_dict(
        self,
        schema_class: type[ComicboxBaseSchema] = ComicboxYamlSchema,
        dump_config: Optional[SchemaConfig] = None,
        **kwargs
    ):
        """Get synthesized metadata as a dict."""
        md = self._get_metadata()
        schema = schema_class(self._path, dump_config)
        return schema.dump(md, **kwargs)

    @archive_close
    def to_string(
        self,
        schema_class: type[ComicboxBaseSchema] = ComicboxYamlSchema,
        dump_config: Optional[SchemaConfig] = None,
        **kwargs
    ):
        """Get synthesized metadata as a string."""
        md = self._get_metadata()
        schema = schema_class(self._path, dump_config)
        return schema.dumps(md, **kwargs)
