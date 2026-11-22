"""
VerseDB API transform.

Converts a VerseDB issue-detail ``data`` object (the server's JSON, as the
`versedb_api.client` adapter returns it) into the comicbox internal schema.
Same explicit-Python, block-tuple style as `ComicVineApiTransform`: the
detail already nests the series, publisher, imprint, credits, characters,
teams, arcs and universes, so one dict carries everything.

VerseDB's web pages need the issue's exact slug, so the issue's real link
is written to ``urls``; its identifier holds only the id and derives no
link of its own (see the versedb.com entry in `identifiers.identifiers`).
"""

from __future__ import annotations

import re
import sys
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from comicbox.enums.comicbox import (
    MangaEnum,
    ReadingDirectionEnum,
    SeriesStatusEnum,
)
from comicbox.enums.metroninfo import MetronFormatEnum
from comicbox.formats.base.online.sanitize import strip_html
from comicbox.formats.base.online.transform_helpers import (
    alt_names_to_cb,
    build_identifier,
    credits_to_cb,
    named_block,
    named_dict,
    named_dict_with_id,
)
from comicbox.formats.base.schemas.cache import get_schema
from comicbox.formats.base.transforms.base import BaseTransform
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema
from comicbox.formats.versedb_api.schema import VerseDBApiSchema

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Mapping

_VERSEDB: Final = "versedb"
WEBSITE: Final = "https://versedb.com"

# VerseDB spells it the American way; comicbox's status enum doesn't.
_STATUS_SPELLINGS: Final = MappingProxyType(
    {"Canceled": SeriesStatusEnum.CANCELLED.value}
)

# The series' physical format, which names a MetronInfo Series/Format
# outright when it is a collected one. "Standard", "Deluxe" and "Other" say
# nothing about publication format, so they fall through to the type.
_PHYSICAL_FORMATS: Final = MappingProxyType(
    {
        "TPB": MetronFormatEnum.TRADE_PAPERBACK.value,
        "Hardcover": MetronFormatEnum.HARDCOVER.value,
        "Omnibus": MetronFormatEnum.OMNIBUS.value,
    }
)

# The series' publication type. "collected_edition" and "special" have no
# MetronInfo value of their own, so they are dropped rather than guessed:
# MetronInfo would reject a raw one.
_PUBLICATION_TYPES: Final = MappingProxyType(
    {
        "regular_series": MetronFormatEnum.SINGLE_ISSUE.value,
        "limited_series": MetronFormatEnum.LIMITED_SERIES.value,
        "one_shot": MetronFormatEnum.ONE_SHOT.value,
        "graphic_novel": MetronFormatEnum.GRAPHIC_NOVEL.value,
        "graphic_novel_series": MetronFormatEnum.GRAPHIC_NOVEL.value,
    }
)

# VerseDB gives an ISO 4217 currency; comicbox keys prices by ISO 3166
# country. EUR is deliberately absent: VerseDB lists eurozone editions from
# several countries, so it names no one country. An unmapped currency keeps
# its price under the empty key.
_CURRENCY_TO_COUNTRY: Final = MappingProxyType(
    {
        "AUD": "AU",
        "BRL": "BR",
        "CAD": "CA",
        "CHF": "CH",
        "CNY": "CN",
        "DKK": "DK",
        "GBP": "GB",
        "INR": "IN",
        "JPY": "JP",
        "KRW": "KR",
        "MXN": "MX",
        "NOK": "NO",
        "NZD": "NZ",
        "PLN": "PL",
        "SEK": "SE",
        "USD": "US",
    }
)

_LOCATION_SPLIT_RE: Final = re.compile(r"\s*[;,]\s*")


def issue_url(issue_id: Any, slug: str | None) -> str | None:
    """Build the issue's versedb.com link, which needs its exact slug."""
    if issue_id is None or not slug:
        return None
    return f"{WEBSITE}/issue/{issue_id}/{slug}"


def _build_identifiers(issue: Mapping[str, Any]) -> dict[str, dict]:
    identifiers: dict[str, dict] = {}
    if (versedb_id := issue.get("id")) is not None:
        identifiers[_VERSEDB] = build_identifier(_VERSEDB, "issue", versedb_id)
    for source in ("isbn", "upc"):
        if value := issue.get(source):
            identifiers[source] = build_identifier(source, "issue", value)
    return identifiers


def _build_series(series: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if name := series.get("name"):
        out["name"] = name
    for key in ("start_year", "end_year"):
        if (year := series.get(key)) is not None:
            out[key] = year
    if status := series.get("status"):
        out["status"] = _STATUS_SPELLINGS.get(status, status)
    if (series_id := series.get("id")) is not None:
        out["identifiers"] = {_VERSEDB: build_identifier(_VERSEDB, "series", series_id)}
    if alt_names := alt_names_to_cb(series.get("aliases"), series.get("name")):
        out["alternative_names"] = alt_names
    return out


def _build_volume(series: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if (number := series.get("volume_number")) is not None:
        out["number"] = int(number)
    if count := series.get("cached_issues_count"):
        out["issue_count"] = count
    return out


def _build_original_format(series: Mapping[str, Any]) -> str | None:
    """Prefer a collected physical format; else map the publication type."""
    return _PHYSICAL_FORMATS.get(series.get("format") or "") or _PUBLICATION_TYPES.get(
        series.get("publication_type") or ""
    )


def _build_manga(series: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """
    Mark manga as manga, read right to left.

    Only a ``manga`` medium is marked. Anything else is left unset rather
    than written as No: VerseDB's other media (manhwa, bande dessinée) are
    no evidence either way, and MangaField would coerce an unknown to No.
    """
    if series.get("medium") != "manga":
        return None, None
    return MangaEnum.YES.value, ReadingDirectionEnum.RTL.value


def _build_date(issue: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for src_key, dst_key in (
        ("cover_date", "cover_date"),
        ("release_date", "store_date"),
    ):
        if value := issue.get(src_key):
            out[dst_key] = value
    return out


def _build_issue_block(issue: Mapping[str, Any]) -> dict[str, Any]:
    if number := issue.get("issue_number"):
        return {"name": str(number)}
    return {}


def _build_cover_image(issue: Mapping[str, Any]) -> str | None:
    images = issue.get("images") or {}
    return images.get("cover_lg") or issue.get("cover_url") or None


def _build_prices(issue: Mapping[str, Any]) -> dict[str, Any]:
    price = issue.get("price")
    if price is None or price == "":
        return {}
    currency = (issue.get("currency_code") or "").upper()
    return {_CURRENCY_TO_COUNTRY.get(currency, ""): price}


def _decimal(value: Any) -> Decimal | None:
    """VerseDB sends ratings as strings ("4.50") or numbers."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _build_community_rating(issue: Mapping[str, Any]) -> dict[str, Any]:
    """
    VerseDB rates 0 to 5, comicbox's own scale; 0 means nobody rated it.

    Its series rows report an unrated series as "0.00", so an average of
    zero is read as no rating rather than as the worst one.
    """
    average = _decimal(issue.get("average_rating"))
    if not average:
        return {}
    out: dict[str, Any] = {"average_rating": average}
    if count := issue.get("review_count"):
        out["rating_count"] = count
    return out


def _build_locations(issue: Mapping[str, Any]) -> dict[str, dict]:
    """VerseDB's locations are one free-text field, not a list."""
    raw = issue.get("locations") or ""
    return {name: {} for name in _LOCATION_SPLIT_RE.split(raw) if name}


def _build_imprint(issue: Mapping[str, Any], series: Mapping[str, Any]) -> Any:
    return named_block(issue, "imprint") or named_block(series, "imprint")


def _build_urls(issue: Mapping[str, Any]) -> list[str]:
    url = issue_url(issue.get("id"), issue.get("slug"))
    return [url] if url else []


def _build_collections(issue: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    return (
        (
            "characters",
            named_dict_with_id(issue.get("characters"), _VERSEDB, "character"),
        ),
        ("teams", named_dict_with_id(issue.get("teams"), _VERSEDB, "team")),
        ("arcs", named_dict_with_id(issue.get("story_arcs"), _VERSEDB, "arc")),
        ("universes", named_dict_with_id(issue.get("universes"), _VERSEDB, "universe")),
        ("locations", _build_locations(issue)),
        (
            "credits",
            # One row per creator and role; credits_to_cb gathers the
            # roles under each creator.
            credits_to_cb(
                issue.get("creators"),
                creator_key="name",
                role_key="role",
                role_is_string=True,
                source=_VERSEDB,
            ),
        ),
    )


def _to_comicbox_dict(issue: Mapping[str, Any]) -> dict[str, Any]:
    """
    Build the comicbox internal dict from a VerseDB issue detail.

    Each entry in `blocks` is `(target_key, value)`. Empty values are
    skipped so the result carries only fields VerseDB actually provided.
    """
    series = issue.get("series") or {}
    manga, reading_direction = _build_manga(series)
    blocks: tuple[tuple[str, Any], ...] = (
        ("issue", _build_issue_block(issue)),
        ("title", issue.get("name")),
        ("date", _build_date(issue)),
        ("cover_image", _build_cover_image(issue)),
        ("page_count", issue.get("page_count")),
        ("summary", strip_html(issue.get("solicitation"))),
        ("age_rating", issue.get("content_rating_label")),
        ("community_rating", _build_community_rating(issue)),
        ("language", series.get("language")),
        ("original_format", _build_original_format(series)),
        ("manga", manga),
        ("reading_direction", reading_direction),
        ("series", _build_series(series)),
        ("volume", _build_volume(series)),
        ("publisher", named_block(issue, "publisher")),
        ("imprint", _build_imprint(issue, series)),
        ("genres", named_dict(series.get("genres"))),
        ("prices", _build_prices(issue)),
        *_build_collections(issue),
        ("identifiers", _build_identifiers(issue)),
        ("urls", _build_urls(issue)),
    )
    return {key: value for key, value in blocks if value}


class VerseDBApiTransform(BaseTransform):
    """VerseDB issue detail → comicbox internal schema."""

    SCHEMA_CLASS = VerseDBApiSchema
    SPECS_TO = MappingProxyType({})  # not used; we override to_comicbox
    SPECS_FROM = MappingProxyType({})

    @override
    def to_comicbox(self, data: Mapping) -> MappingProxyType:
        """Convert a VerseDB issue detail into a validated comicbox dict."""
        issue_data = data.get(VerseDBApiSchema.ROOT_TAG) or data
        if not issue_data:
            return MappingProxyType({})

        wrapped = {ComicboxSchemaMixin.ROOT_TAG: _to_comicbox_dict(issue_data)}
        schema = get_schema(ComicboxYamlSchema, path=self._path)
        loaded: dict = schema.load(wrapped)  # pyright: ignore[reportAssignmentType]
        return MappingProxyType(loaded)
