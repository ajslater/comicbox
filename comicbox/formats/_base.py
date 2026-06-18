"""Base types for format-package declarations."""

from dataclasses import dataclass
from types import MappingProxyType

from comicbox.formats.base.schemas.base import BaseSchema
from comicbox.formats.base.transforms.base import BaseTransform
from comicbox.validate.base import BaseValidator


@dataclass(frozen=True, slots=True)
class MetadataFormat:
    """
    Metadata format attributes.

    Frozen like its FormatRegistration sibling: these become enum values,
    so mutability would make them unhashable (CPython falls back to a
    linear value scan) and would let runtime mutation silently
    desynchronize derived snapshots like sources._ANY_FORMATS.
    """

    label: str
    config_keys: frozenset
    filename: str
    transform_class: type[BaseTransform]
    has_pages: bool = False
    lexer: str = "yaml"
    enabled: bool = True

    @property
    def schema_class(self) -> type[BaseSchema]:
        """The transform's schema class (call sites use fmt.value.schema_class)."""
        return self.transform_class.SCHEMA_CLASS


@dataclass(frozen=True, slots=True)
class OnlineSourceCliInfo:
    """
    User-facing description of an online source for CLI help.

    Pure data — no imports or class references, safe to declare at
    module-load time without triggering the formats-package cycle that
    the heavier OnlineSource class would.
    """

    short_name: str  # As used in `--online <name>` and credentials config.
    credentials: str  # What credentials are required (free-form text).
    id_form: str  # Accepted `--id` forms.
    website: str


@dataclass(frozen=True, slots=True)
class FormatRegistration:
    """
    Self-contained declaration of a metadata format's wiring.

    Each format package exports a `REGISTRATION: FormatRegistration` from
    its `__init__.py`. The central `comicbox.formats` package and
    `comicbox.formats.sources` module read from this instance to assemble the
    `MetadataFormats` and `MetadataSources` enums.
    """

    format: MetadataFormat
    sources: MappingProxyType[str, int]
    validator: BaseValidator | None = None
    has_tags_without_ids: bool = False
    is_online: bool = False
    cli_info: OnlineSourceCliInfo | None = None
