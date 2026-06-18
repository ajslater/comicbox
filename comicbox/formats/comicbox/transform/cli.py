"""Comicbox CLI transform to and from Comicbox format."""

from comicbox.formats.comicbox.schema.cli import ComicboxCLISchema
from comicbox.formats.comicbox.transform.yaml import ComicboxYamlTransform


class ComicboxCLITransform(ComicboxYamlTransform):
    """Comicbox CLI transform."""

    SCHEMA_CLASS = ComicboxCLISchema
