"""Base types for format-package declarations."""

from dataclasses import dataclass
from types import MappingProxyType

from comicbox.box.validate.base import BaseValidator
from comicbox.transforms.base import BaseTransform


@dataclass
class MetadataFormat:
    """Metadata format attributes."""

    label: str
    config_keys: frozenset
    filename: str
    transform_class: type[BaseTransform]
    has_pages: bool = False
    lexer: str = "yaml"
    enabled: bool = True

    def __post_init__(self) -> None:
        """Hoist the schema class."""
        self.schema_class = self.transform_class.SCHEMA_CLASS  # pyright: ignore[reportUninitializedInstanceVariable]


@dataclass(frozen=True, slots=True)
class FormatRegistration:
    """
    Self-contained declaration of a metadata format's wiring.

    Each format package exports a `REGISTRATION: FormatRegistration` from
    its `__init__.py`. The central `comicbox.formats` package and
    `comicbox.sources` module read from this instance to assemble the
    `MetadataFormats` and `MetadataSources` enums.
    """

    format: MetadataFormat
    sources: MappingProxyType[str, int]
    validator: BaseValidator | None = None
    has_tags_without_ids: bool = False
