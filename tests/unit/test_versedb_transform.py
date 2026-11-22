"""VerseDBApiTransform field-mapping tests, on real recorded payloads."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from comicbox.box import Comicbox
from comicbox.enums.comicbox import MangaEnum, ReadingDirectionEnum, SeriesStatusEnum
from comicbox.formats import MetadataFormats
from comicbox.formats.versedb_api.transform import VerseDBApiTransform, issue_url

FIXTURES = Path(__file__).parent.parent / "files" / "versedb"


def _issue(name: str) -> dict[str, Any]:
    """Load the issue-detail ``data`` object of one recorded response."""
    return json.loads((FIXTURES / f"{name}.json").read_text())["data"]


def _transform(issue: dict[str, Any]) -> dict[str, Any]:
    result = VerseDBApiTransform().to_comicbox({"versedb_api": issue})
    return dict(result["comicbox"])


_REGULAR_CORE: dict[str, Any] = {
    "issue": {"name": "24"},
    "date": {"cover_date": date(2026, 11, 1), "store_date": date(2026, 9, 23)},
    "page_count": 32,
    "age_rating": "Teen Plus",
    "language": "en",
    "prices": {"US": Decimal("4.99")},
    "publisher": {"name": "DC Comics"},
    "imprint": {"name": "Absolute Universe"},
    "genres": {"Superhero": {}},
}


def test_regular_issue_core_fields() -> None:
    cb = _transform(_issue("issue_regular"))
    assert {key: cb.get(key) for key in _REGULAR_CORE} == _REGULAR_CORE
    assert cb["summary"].startswith("WITHOUT THE BADGE")
    assert cb["cover_image"].endswith("cover_lg.webp")


def test_regular_issue_invents_nothing() -> None:
    """The issue has no name and no rating: neither is made up."""
    cb = _transform(_issue("issue_regular"))
    assert "title" not in cb
    assert "community_rating" not in cb


def test_regular_issue_series_and_volume() -> None:
    cb = _transform(_issue("issue_regular"))
    assert cb["series"] == {
        "name": "Absolute Batman",
        "start_year": 2024,
        "status": SeriesStatusEnum.ONGOING,
        "identifiers": {"versedb": {"key": "139382"}},
    }
    assert cb["volume"] == {"number": 1, "issue_count": 27}
    # regular_series in a Standard format reads as single issues.
    assert cb["original_format"] == "Single Issue"
    assert "manga" not in cb
    assert "reading_direction" not in cb


def test_identifiers_and_the_real_link() -> None:
    """The id is a key; the link written is the real, slugged one."""
    cb = _transform(_issue("issue_regular"))
    assert cb["identifiers"] == {
        "versedb": {"key": "1215061"},
        "upc": {"key": "76194138584602411"},
    }
    assert cb["urls"] == ["https://versedb.com/issue/1215061/absolute-batman-2024-24"]


def test_credits_carry_versedb_ids_and_roles() -> None:
    people = _transform(_issue("issue_regular"))["credits"]
    dragotta = people["Nick Dragotta"]
    assert dragotta["identifiers"] == {"versedb": {"key": "5396"}}
    assert "Cover" in dragotta["roles"]


def test_credits_gather_one_creators_rows() -> None:
    """VerseDB lists one row per creator and role; comicbox keeps one creator."""
    issue = _issue("issue_regular")
    issue["creators"] = [
        {**issue["creators"][0], "role": "Writer"},
        {**issue["creators"][0], "role": "Artist"},
    ]
    people = _transform(issue)["credits"]
    assert list(people) == ["Nick Dragotta"]
    assert set(people["Nick Dragotta"]["roles"]) == {"Writer", "Artist"}


def test_named_collections_carry_versedb_ids() -> None:
    cb = _transform(_issue("issue_regular"))
    barbara = cb["characters"]["Barbara Gordon (Earth Alpha)"]
    assert barbara == {"identifiers": {"versedb": {"key": "184284"}}}
    universe = cb["universes"]["Absolute Universe (Earth-Alpha)"]
    assert universe["identifiers"] == {"versedb": {"key": "43"}}


def test_manga_volume() -> None:
    cb = _transform(_issue("issue_manga"))
    assert cb["manga"] == MangaEnum.YES
    assert cb["reading_direction"] == ReadingDirectionEnum.RTL
    assert cb["title"] == "Volume 14"
    assert cb["identifiers"]["isbn"] == {"key": "9798888779958"}
    # No format and no publication type: nothing is guessed.
    assert "original_format" not in cb


def test_collected_edition() -> None:
    cb = _transform(_issue("issue_collected"))
    assert cb["original_format"] == "Trade Paperback"
    assert cb["volume"]["number"] == 2
    # An empty solicitation is no summary.
    assert "summary" not in cb


def test_canceled_is_spelled_cancelled() -> None:
    issue = _issue("issue_regular")
    issue["series"]["status"] = "Canceled"
    assert _transform(issue)["series"]["status"] is SeriesStatusEnum.CANCELLED


@pytest.mark.parametrize(
    ("average", "count", "expected"),
    [
        ("4.50", 12, {"average_rating": Decimal("4.5"), "rating_count": 12}),
        (3.0, None, {"average_rating": Decimal("3.0")}),
        ("0.00", 0, None),
        (None, None, None),
    ],
)
def test_community_rating(average: Any, count: Any, expected: Any) -> None:
    """VerseDB rates 0-5 like comicbox; zero means unrated."""
    issue = _issue("issue_regular")
    issue["average_rating"] = average
    issue["review_count"] = count
    assert _transform(issue).get("community_rating") == expected


@pytest.mark.parametrize(
    ("currency", "country"),
    [("CAD", "CA"), ("GBP", "GB"), ("EUR", ""), ("XYZ", ""), (None, "")],
)
def test_price_is_keyed_by_country(currency: str | None, country: str) -> None:
    issue = _issue("issue_regular")
    issue["currency_code"] = currency
    assert _transform(issue)["prices"] == {country: Decimal("4.99")}


def test_locations_split_free_text() -> None:
    issue = _issue("issue_regular")
    issue["locations"] = "Gotham City; Arkham Asylum, Wayne Manor"
    assert _transform(issue)["locations"] == {
        "Gotham City": {},
        "Arkham Asylum": {},
        "Wayne Manor": {},
    }


def test_imprint_falls_back_to_the_series() -> None:
    issue = _issue("issue_regular")
    issue["imprint"] = None
    assert _transform(issue)["imprint"] == {"name": "Absolute Universe"}


def test_no_slug_writes_no_link() -> None:
    issue = _issue("issue_regular")
    issue["slug"] = None
    assert "urls" not in _transform(issue)
    assert issue_url(1, None) is None
    assert issue_url(None, "x") is None


def test_empty_input_is_empty() -> None:
    assert dict(VerseDBApiTransform().to_comicbox({})) == {}


@pytest.mark.parametrize(
    "fmt", [MetadataFormats.COMIC_INFO, MetadataFormats.METRON_INFO]
)
def test_id_and_link_survive_a_written_file(fmt: MetadataFormats) -> None:
    """
    Write the tags, read them back: the id and its real link both survive.

    MetronInfo's ``<IDS>`` can't name VerseDB, so the id comes back out of
    the link, which is why the link has to be the real one.
    """
    link = "https://versedb.com/issue/1215061/absolute-batman-2024-24"
    with Comicbox() as car:
        car.add_metadata(
            {"versedb_api": _issue("issue_regular")}, MetadataFormats.VERSEDB_API
        )
        written = car.to_string(fmt)
    with Comicbox(metadata=written, fmt=fmt) as car:
        md = car.to_dict()["comicbox"]
    assert md["identifiers"]["versedb"] == {"key": "1215061"}
    assert link in md["urls"]
    assert not [url for url in md["urls"] if "versedb" in url and url != link]
