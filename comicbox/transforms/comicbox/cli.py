"""Comicbox CLI transform to and from Comicbox format."""

from comicbox.schemas.comicbox.cli import ComicboxCLISchema
from comicbox.transforms.comicbox.yaml import ComicboxYamlTransform


class ComicboxCLITransform(ComicboxYamlTransform):
    """Comicbox CLI transform."""

    SCHEMA_CLASS = ComicboxCLISchema
