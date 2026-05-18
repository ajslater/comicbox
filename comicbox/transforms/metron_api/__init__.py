"""
Metron API transform.

Converts a mokkari `Issue.model_dump(mode="json")` dict into the
comicbox internal schema. The conversion is explicit Python rather
than the spec-driven ``MetaSpec`` machinery used by the older XML
transforms — the source dict has irregular shapes (lists of nested
objects, role lists, cross-source ids) that don't fit the simple
key-rename pattern, and inline conversion is easier to follow than
fighting glom.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema
from comicbox.online.sanitize import strip_html
from comicbox.online.transform_helpers import (
    build_identifier,
    credits_to_cb,
    named_block,
    named_dict,
    named_dict_with_id,
    reprints_to_cb,
)
from comicbox.schemas.cache import get_schema
from comicbox.schemas.metron_api import MetronApiSchema
from comicbox.transforms.base import BaseTransform

if TYPE_CHECKING:
    from collections.abc import Mapping

_METRON = "metron"


def _build_identifiers(issue: Mapping[str, Any]) -> dict[str, dict]:
    """
    Build the top-level `identifiers` dict from an issue's id fields.

    Metron's Issue carries its own id plus cross-references to ComicVine
    (`cv_id`) and Grand Comics Database (`gcd_id`). We surface all three
    plus ISBN/UPC when present.
    """
    identifiers: dict[str, dict] = {}
    if (mid := issue.get("id")) is not None:
        identifiers[_METRON] = build_identifier(_METRON, "issue", mid)
    if (cv := issue.get("cv_id")) is not None:
        identifiers["comicvine"] = build_identifier("comicvine", "issue", cv)
    if (gcd := issue.get("gcd_id")) is not None:
        identifiers["grandcomicsdatabase"] = build_identifier(
            "grandcomicsdatabase", "issue", gcd
        )
    if isbn := issue.get("isbn"):
        identifiers["isbn"] = build_identifier("isbn", "issue", isbn)
    if upc := issue.get("upc"):
        identifiers["upc"] = build_identifier("upc", "issue", upc)
    return identifiers


def _build_series(issue: Mapping[str, Any]) -> dict[str, Any]:
    """Build comicbox's `series` block from the Issue's nested IssueSeries."""
    s = issue.get("series") or {}
    out: dict[str, Any] = {}
    if name := s.get("name"):
        out["name"] = name
    if sort_name := s.get("sort_name"):
        out["sort_name"] = sort_name
    if (year := s.get("year_began")) is not None:
        out["start_year"] = year
    if (sid := s.get("id")) is not None:
        out["identifiers"] = {_METRON: build_identifier(_METRON, "series", sid)}
    return out


def _build_volume(issue: Mapping[str, Any]) -> dict[str, Any]:
    """`volume.number` from the IssueSeries.volume integer."""
    s = issue.get("series") or {}
    if (vol := s.get("volume")) is not None:
        return {"number": int(vol)}
    return {}


def _build_date(issue: Mapping[str, Any]) -> dict[str, Any]:
    """Map cover_date / store_date into comicbox's date block."""
    out: dict[str, Any] = {}
    for src_key, dst_key in (
        ("cover_date", "cover_date"),
        ("store_date", "store_date"),
    ):
        if val := issue.get(src_key):
            out[dst_key] = val
    return out


def _build_issue_block(issue: Mapping[str, Any]) -> dict[str, Any]:
    """Build comicbox's `issue` block with name + suffix from alt_number."""
    out: dict[str, Any] = {}
    if number := issue.get("number"):
        out["name"] = str(number)
    if alt := issue.get("alt_number"):
        out["suffix"] = str(alt)
    return out


def _build_prices(issue: Mapping[str, Any]) -> dict[str, Any]:
    """Single price → keyed by ISO currency code (or empty key fallback)."""
    price = issue.get("price")
    if price is None or price == "":
        return {}
    currency = issue.get("price_currency") or ""
    return {currency: price}


def _build_stories(issue: Mapping[str, Any]) -> dict[str, dict]:
    """story_titles[] → comicbox stories."""
    titles = issue.get("story_titles") or []
    return {str(t): {} for t in titles if t}


def _build_age_rating(issue: Mapping[str, Any]) -> str | None:
    """Pick rating.name off the nested rating dict."""
    rating = issue.get("rating") or {}
    return rating.get("name")


def _to_comicbox_dict(issue: Mapping[str, Any]) -> dict[str, Any]:
    """
    Build the comicbox internal dict from a mokkari Issue dict.

    Each entry in `blocks` is `(target_key, value)`. Empty values
    (None, "", {}, [], 0) are skipped so the resulting dict carries
    only fields the upstream actually provided.
    """
    series_genres = (issue.get("series") or {}).get("genres")
    blocks: tuple[tuple[str, Any], ...] = (
        # Scalars / single-source nested
        ("issue", _build_issue_block(issue)),
        ("date", _build_date(issue)),
        ("cover_image", issue.get("image")),
        ("updated_at", issue.get("modified")),
        ("page_count", issue.get("page_count")),
        ("collection_title", issue.get("collection_title")),
        ("summary", strip_html(issue.get("desc"))),
        ("age_rating", _build_age_rating(issue)),
        # Publishing
        ("series", _build_series(issue)),
        ("volume", _build_volume(issue)),
        ("publisher", named_block(issue, "publisher")),
        ("imprint", named_block(issue, "imprint")),
        # Prices / Stories
        ("prices", _build_prices(issue)),
        ("stories", _build_stories(issue)),
        # Collections (named dicts)
        (
            "characters",
            named_dict_with_id(issue.get("characters"), _METRON, "character"),
        ),
        ("teams", named_dict_with_id(issue.get("teams"), _METRON, "team")),
        ("arcs", named_dict_with_id(issue.get("arcs"), _METRON, "story_arc")),
        ("universes", named_dict_with_id(issue.get("universes"), _METRON, "universe")),
        ("genres", named_dict(series_genres)),
        # Credits (list of {id, creator, role: [{name},...]})
        (
            "credits",
            credits_to_cb(
                issue.get("credits"),
                creator_key="creator",
                role_key="role",
                role_is_string=False,
                source=_METRON,
            ),
        ),
        # Reprints
        ("reprints", reprints_to_cb(issue.get("reprints"), source=_METRON)),
        # Top-level identifiers
        ("identifiers", _build_identifiers(issue)),
    )
    return {key: value for key, value in blocks if value}


class MetronApiTransform(BaseTransform):
    """Mokkari `Issue` → comicbox internal schema."""

    SCHEMA_CLASS = MetronApiSchema
    SPECS_TO = MappingProxyType({})  # not used; we override to_comicbox
    SPECS_FROM = MappingProxyType({})

    @override
    def to_comicbox(self, data: Mapping) -> MappingProxyType:
        """Convert a mokkari Issue dict into a validated comicbox dict."""
        # Source data arrives wrapped under the schema's ROOT_TAG.
        issue_data = data.get(MetronApiSchema.ROOT_TAG) or data
        if not issue_data:
            return MappingProxyType({})

        wrapped = {ComicboxSchemaMixin.ROOT_TAG: _to_comicbox_dict(issue_data)}
        schema = get_schema(ComicboxYamlSchema, path=self._path)
        loaded: dict = schema.load(wrapped)  # pyright: ignore[reportAssignmentType]
        return MappingProxyType(loaded)
