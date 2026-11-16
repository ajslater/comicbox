"""Reading-list identity: issue parsing and entry keys."""

from decimal import Decimal
from typing import Any

import pytest

from comicbox.readinglists import (
    ParsedIssue,
    entry_keys,
    normalize_series,
    parse_issue,
)
from tests.unit.test_parse_issue import ISSUES

_SUFFIXES = {
    "4AU": ParsedIssue("4AU", Decimal(4), "AU"),
    "#004AU": ParsedIssue("4AU", Decimal(4), "AU"),
    "1.MU": ParsedIssue("1.MU", Decimal(1), "MU"),
    "½": ParsedIssue(".5", Decimal("0.5"), ""),
    "1 1/2": ParsedIssue("1.5", Decimal("1.5"), ""),
    "Annual": ParsedIssue("Annual", None, "Annual"),
    "": ParsedIssue("", None, ""),
}


@pytest.mark.parametrize(
    ("text", "name"),
    [(text, name) for name, texts in ISSUES.items() for text in texts],
)
def test_parse_issue_normalizes_like_comicbox(text: str, name: str) -> None:
    assert parse_issue(text).name == name


@pytest.mark.parametrize(("text", "expected"), list(_SUFFIXES.items()))
def test_parse_issue_suffixes(text: str, expected: ParsedIssue) -> None:
    assert parse_issue(text) == expected


def _entry(**fields: Any) -> dict[str, Any]:
    return {
        "series": {"name": "Civil War", "start_year": 2006},
        "issue": {"name": "1"},
        **fields,
    }


def _ids(entry: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [key for key in entry_keys(entry) if key[0] == "id"]


def _name_keys(entry: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [key for key in entry_keys(entry) if key[0] == "name"]


def test_ids_come_in_rank_order() -> None:
    entry = _entry(
        identifiers={
            "grandcomicsdatabase": {"key": "7"},
            "comicvine": {"key": "105747"},
            "metron": {"key": "31562"},
        }
    )
    assert entry_keys(entry) == (
        ("id", "metron", "31562"),
        ("id", "comicvine", "105747"),
        ("id", "grandcomicsdatabase", "7"),
        ("name", "civil war", 2006, Decimal(1), ""),
    )


def test_ids_of_other_types_are_ignored() -> None:
    entry = _entry(
        series={
            "name": "Civil War",
            "start_year": 2006,
            "identifiers": {"comicvine": {"key": "18023"}},
        },
        identifiers={
            "metron": {"key": "9", "id_type": "series"},
            "comicvine": {"key": "105747", "id_type": "issue"},
            "unknowndb": {"key": "3"},
        },
    )
    assert _ids(entry) == [("id", "comicvine", "105747")]


@pytest.mark.parametrize(
    ("source", "key", "expected"),
    [
        ("isbn", "978-0-7851-2179-0", "9780785121790"),
        ("asin", "B00ABC1234", "B00ABC1234"),
        ("upc", "759606054213", None),
        ("upc", "75960605421300111", "75960605421300111"),
        ("upc", "7 59606 05421 3 00111", "75960605421300111"),
        ("gtin", "0759606054213", None),
        ("gtin", "075960605421300111", "075960605421300111"),
    ],
)
def test_barcodes(source: str, key: str, expected: str | None) -> None:
    """An ISBN names one book; a UPC names one issue only with its supplement."""
    ids = _ids(_entry(identifiers={source: {"key": key}}))
    assert ids == ([("id", source, expected)] if expected else [])


def test_whole_and_decimal_numbers_agree() -> None:
    assert _name_keys(_entry(issue={"name": "3"})) == _name_keys(
        _entry(issue={"name": "3.0"})
    )
    assert _name_keys(_entry(issue={"name": "#003"})) == _name_keys(
        _entry(issue={"number": Decimal(3)})
    )


def test_suffix_is_case_folded() -> None:
    assert _name_keys(_entry(issue={"name": "4AU"})) == _name_keys(
        _entry(issue={"name": "4au"})
    )
    assert _name_keys(_entry(issue={"name": "4AU"})) != _name_keys(
        _entry(issue={"name": "4"})
    )


@pytest.mark.parametrize(
    "entry",
    [
        {"series": {"name": "Civil War"}, "issue": {"name": "1"}},
        {"series": {"name": "!!!", "start_year": 2006}, "issue": {"name": "1"}},
        {"series": {"name": "Civil War", "start_year": 2006}},
        {"issue": {"name": "1"}, "volume": {"number": 2006}},
    ],
    ids=["no-year-or-volume", "empty-name", "no-issue", "no-series"],
)
def test_no_name_key(entry: dict[str, Any]) -> None:
    """Without a discriminator, a name and number join by id only."""
    assert _name_keys(entry) == []


def test_start_year_and_year_volume_share_a_name_key() -> None:
    """Metron gives a start year; ComicTagger puts the year in the volume."""
    metron_style = {
        "series": {"name": "Civil War", "start_year": 2006},
        "volume": {"number": 1},
        "issue": {"name": "1"},
    }
    comictagger_style = {
        "series": {"name": "Civil War"},
        "volume": {"number": 2006},
        "issue": {"name": "1"},
    }
    assert _name_keys(metron_style) == _name_keys(comictagger_style)


def test_volume_number_alone_does_not_meet_a_start_year() -> None:
    """
    A small volume number cannot be told from a year without another fact.

    The pair below may well be the same issue, but only ids can say so.
    """
    metron_style = {
        "series": {"name": "Civil War", "start_year": 2006},
        "issue": {"name": "1"},
    }
    volume_only = {
        "series": {"name": "Civil War"},
        "volume": {"number": 1},
        "issue": {"name": "1"},
    }
    assert _name_keys(volume_only)
    assert _name_keys(metron_style) != _name_keys(volume_only)


@pytest.mark.parametrize(
    ("name", "normalized"),
    [
        ("Pokémon", "pokemon"),
        ("ワンピース", "ワンピース"),
        ("ガンダム", "ガンダム"),
        ("Ελληνικά", "ελληνικα"),
        ("Crème Brûlée", "creme brulee"),
        ("Æon Flux", "æon flux"),
        ("Batman Vol. 2", "batman"),
        ("The Amazing Spider-Man (Volume 3)", "the amazing spider man"),
    ],
)
def test_normalize_series_reads_every_script(name: str, normalized: str) -> None:
    assert normalize_series(name) == normalized


def test_a_non_latin_series_has_a_name_key() -> None:
    entry = {
        "series": {"name": "ワンピース", "start_year": 1997},
        "issue": {"name": "1"},
    }
    assert _name_keys(entry)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("-1", ParsedIssue("-1", Decimal(-1), "")),
        ("-01", ParsedIssue("-01", Decimal(-1), "")),
        ("-1A", ParsedIssue("-1A", Decimal(-1), "A")),
        ("-", ParsedIssue("-", None, "-")),
    ],
)
def test_minus_one_is_a_number(text: str, expected: ParsedIssue) -> None:
    assert parse_issue(text) == expected


def test_minus_one_by_name_or_number_is_one_key() -> None:
    assert _name_keys(_entry(issue={"name": "-1"})) == _name_keys(
        _entry(issue={"number": Decimal(-1)})
    )
    assert _name_keys(_entry(issue={"name": "-1"})) != _name_keys(
        _entry(issue={"name": "1"})
    )


def test_kana_voicing_is_part_of_the_letter() -> None:
    """パ, バ and ハ are three syllables; accents on Latin letters fold."""
    assert len({normalize_series(name) for name in ("パン", "バン", "ハン")}) == 3
    assert normalize_series("Pokémon") == normalize_series("Pokemon")
