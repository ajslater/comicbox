"""Comicbox CLI transform to and from Comicbox format."""

from comicbox.schemas.comicbox_cli import ComicboxCLISchema
from comicbox.transforms.comicbox_yaml import ComicboxYamlTransform


class ComicboxCLITransform(ComicboxYamlTransform):
    """Comicbox CLI transform."""

    SCHEMA_CLASS = ComicboxCLISchema
