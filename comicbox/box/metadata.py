"""Get Metadata mixin."""

from types import MappingProxyType

from comicbox.box.archive import archive_close
from comicbox.box.computed import ComicboxComputedMixin
from comicbox.dict_funcs import sort_dict
from comicbox.schemas.comicbox_mixin import ROOT_TAG
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comicbox_yaml import ComicboxYamlTransform


class ComicboxMetadataMixin(ComicboxComputedMixin):
    """Get Metadata mixin."""

    def _set_metadata(self):
        # collect metadata
        computed_merged_metadata = self.get_computed_merged_metadata()
        if not computed_merged_metadata:
            computed_merged_metadata = {ROOT_TAG: {}}
        self._metadata = MappingProxyType(sort_dict(computed_merged_metadata))

    def _get_metadata(self) -> MappingProxyType:
        """Return the metadata from the archive."""
        if not self._metadata:
            self._set_metadata()
        return self._metadata

    @archive_close
    def get_metadata(self) -> MappingProxyType:
        """Return the metadata from the archive."""
        return self._get_metadata()

    def _to_dict(
        self,
        transform_class: type[BaseTransform] = ComicboxYamlTransform,
    ):
        # Get schema instance.
        schema = transform_class.SCHEMA_CLASS(path=self._path)

        # Get transformed md
        transform = transform_class(self._path)
        md = self._get_metadata()
        md = transform.from_comicbox(md)

        return schema, md

    @archive_close
    def to_dict(
        self,
        transform_class: type[BaseTransform] = ComicboxYamlTransform,
        **kwargs,
    ) -> dict:
        """Get merged metadata as a dict."""
        schema, md = self._to_dict(transform_class)
        return dict(schema.dump(md, **kwargs))

    @archive_close
    def to_string(
        self,
        transform_class: type[BaseTransform] = ComicboxYamlTransform,
        **kwargs,
    ) -> str:
        """Get mergeesized metadata as a string."""
        schema, md = self._to_dict(transform_class)
        return schema.dumps(md, **kwargs)
