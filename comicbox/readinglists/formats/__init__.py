"""
Reading-list format packages.

Each package exports a registration: a ``ReadingListFormat``. The registry
assembles the ``ReadingListFormats`` enum from them. These are the file
formats only; Metron and ComicVine are sources with builders, not formats,
since nothing can be written to them.
"""

from dataclasses import dataclass

from comicbox.formats.base.schemas.base import BaseSchema
from comicbox.readinglists.transform import ReadingListTransform
from comicbox.validate.spec import ValidatorSpec


@dataclass(frozen=True, slots=True)
class ReadingListFormat:
    """
    A reading-list file format.

    Frozen because it is an enum value. ``tokens`` are the names the CLI and
    the API accept for it, unique across formats. ``validator_spec`` names a
    schema file under ``comicbox/schemas/``, built only when something
    validates.
    """

    label: str
    tokens: frozenset[str]
    suffix: str
    transform_class: type[ReadingListTransform]
    lexer: str = "yaml"
    validator_spec: ValidatorSpec | None = None

    @property
    def schema_class(self) -> type[BaseSchema]:
        """The transform's schema class."""
        return self.transform_class.SCHEMA_CLASS
