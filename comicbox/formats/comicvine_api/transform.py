"""
ComicVine API transform.

Converts a simyan `Issue.model_dump(mode="json")` dict into the
comicbox internal schema. Same explicit-Python style as
`MetronApiTransform` — the source dict has shapes that don't fit the
key-rename ``MetaSpec`` pattern (creators with comma-string roles,
volume that means series, HTML in description).
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from comicbox.formats.base.online.sanitize import strip_html
from comicbox.formats.base.online.transform_helpers import (
    alt_names_to_cb,
    build_identifier,
    credits_to_cb,
    named_block,
    named_dict,
    named_dict_with_id,
    split_aliases,
)
from comicbox.formats.base.schemas.cache import get_schema
from comicbox.formats.base.transforms.base import BaseTransform
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema
from comicbox.formats.comicvine_api.schema import ComicVineApiSchema

if TYPE_CHECKING:
    from collections.abc import Mapping

_CV = "comicvine"

# `image` order of preference for the stored cover_image (largest →
# smallest, picking the first available). Hashing uses thumbnail
# elsewhere; here we pick a higher-quality URL for archival.
_COVER_IMAGE_PREFERENCE = (
    "medium_url",
    "screen_url",
    "super_url",
    "original_url",
    "small_url",
    "thumbnail",
)


def _pick_cover_image(image: Mapping[str, Any] | None) -> str | None:
    if not image:
        return None
    for key in _COVER_IMAGE_PREFERENCE:
        if url := image.get(key):
            return str(url)
    return None


def _build_identifiers(issue: Mapping[str, Any]) -> dict[str, dict]:
    identifiers: dict[str, dict] = {}
    if (cv_id := issue.get("id")) is not None:
        identifiers[_CV] = build_identifier(_CV, "issue", cv_id)
    return identifiers


def _build_series(issue: Mapping[str, Any]) -> dict[str, Any]:
    """ComicVine's `volume` is what comicbox calls a series."""
    vol = issue.get("volume") or {}
    out: dict[str, Any] = {}
    if name := vol.get("name"):
        out["name"] = name
    if (vid := vol.get("id")) is not None:
        out["identifiers"] = {_CV: build_identifier(_CV, "series", vid)}
    # volume.aliases, start_year and description are injected by
    # ComicVineOnlineSource.get() from the volume it already fetches. The
    # aliases are other names for this series, not reprints of this issue.
    if alt_names := alt_names_to_cb(split_aliases(vol.get("aliases")), vol.get("name")):
        out["alternative_names"] = alt_names
    if (start_year := vol.get("start_year")) is not None:
        out["start_year"] = start_year
    if summary := strip_html(vol.get("description")):
        out["summary"] = summary
    return out


def _build_volume(issue: Mapping[str, Any]) -> dict[str, Any]:
    """CV's volume issue count, injected by `ComicVineOnlineSource.get()`."""
    vol = issue.get("volume") or {}
    if (count := vol.get("issue_count")) is not None:
        return {"issue_count": count}
    return {}


def _build_tags(issue: Mapping[str, Any]) -> dict[str, dict]:
    """
    Concepts and objects → tags.

    Concepts keep their CV id. Objects carry none: CV's object type has no
    comicbox identifier type. A name in both keeps the concept's id.
    """
    return {
        **named_dict(issue.get("objects")),
        **named_dict_with_id(issue.get("concepts"), _CV, "tag"),
    }


def _build_date(issue: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("cover_date", "store_date"):
        if val := issue.get(key):
            out[key] = val
    return out


def _build_issue_block(issue: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if number := issue.get("number"):
        out["name"] = str(number)
    return out


def _to_comicbox_dict(issue: Mapping[str, Any]) -> dict[str, Any]:
    """
    Build the comicbox internal dict from a simyan Issue dict.

    Each entry in `blocks` is `(target_key, value)`. Empty values
    (None, "", {}, [], 0) are skipped so the resulting dict carries
    only fields the upstream actually provided.
    """
    blocks: tuple[tuple[str, Any], ...] = (
        ("issue", _build_issue_block(issue)),
        ("title", issue.get("name")),
        ("date", _build_date(issue)),
        ("cover_image", _pick_cover_image(issue.get("image"))),
        ("updated_at", issue.get("date_last_updated")),
        ("summary", strip_html(issue.get("description"))),
        # Publishing — CV's `volume` is comicbox's `series`.
        ("series", _build_series(issue)),
        ("volume", _build_volume(issue)),
        # `publisher` is injected by `ComicVineOnlineSource.get()` after a
        # secondary `get_volume(volume.id)` call — CV's issue endpoint
        # doesn't include publisher inline.
        ("publisher", named_block(issue, "publisher")),
        # Collections
        ("characters", named_dict_with_id(issue.get("characters"), _CV, "character")),
        ("teams", named_dict_with_id(issue.get("teams"), _CV, "team")),
        ("arcs", named_dict_with_id(issue.get("story_arcs"), _CV, "arc")),
        ("locations", named_dict_with_id(issue.get("locations"), _CV, "location")),
        ("tags", _build_tags(issue)),
        # Credits — CV stores roles as a comma-separated string per creator.
        (
            "credits",
            credits_to_cb(
                issue.get("creators"),
                creator_key="name",
                role_key="roles",
                role_is_string=True,
                source=_CV,
            ),
        ),
        # Reprints — the volume's alternative names.
        # Top-level identifiers (just the CV issue id; volume id lives on series).
        ("identifiers", _build_identifiers(issue)),
    )
    return {key: value for key, value in blocks if value}


class ComicVineApiTransform(BaseTransform):
    """Simyan `Issue` → comicbox internal schema."""

    SCHEMA_CLASS = ComicVineApiSchema
    SPECS_TO = MappingProxyType({})  # not used; we override to_comicbox
    SPECS_FROM = MappingProxyType({})

    @override
    def to_comicbox(self, data: Mapping) -> MappingProxyType:
        """Convert a simyan Issue dict into a validated comicbox dict."""
        issue_data = data.get(ComicVineApiSchema.ROOT_TAG) or data
        if not issue_data:
            return MappingProxyType({})

        wrapped = {ComicboxSchemaMixin.ROOT_TAG: _to_comicbox_dict(issue_data)}
        schema = get_schema(ComicboxYamlSchema, path=self._path)
        loaded: dict = schema.load(wrapped)  # pyright: ignore[reportAssignmentType]
        return MappingProxyType(loaded)
