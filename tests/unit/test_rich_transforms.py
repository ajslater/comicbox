"""Rich-mapping tests for MetronApiTransform and ComicVineApiTransform."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from comicbox.formats.base.online.sanitize import strip_html
from comicbox.formats.base.online.transform_helpers import (
    alt_names_to_reprints,
    build_identifier,
    credits_to_cb,
    named_dict,
    named_dict_with_id,
    parse_creator_roles,
    reprints_to_cb,
    split_aliases,
)
from comicbox.formats.comicvine_api.transform import ComicVineApiTransform
from comicbox.formats.metron_api.transform import MetronApiTransform

# ----------------------------------------------------- sanitize


def test_strip_html_strips_inline_tags() -> None:
    assert strip_html("<b>bold</b> and <i>italic</i>") == "bold and italic"


def test_strip_html_preserves_paragraph_breaks() -> None:
    out = strip_html("<p>First</p><p>Second</p>")
    assert out == "First\n\nSecond"


def test_strip_html_drops_dangerous() -> None:
    out = strip_html("<script>alert(1)</script>Safe")
    assert out is not None
    assert "alert" not in out
    assert "Safe" in out


def test_strip_html_handles_none_and_empty() -> None:
    assert strip_html(None) is None
    assert strip_html("") == ""


# ----------------------------------------------------- helpers


def test_named_dict() -> None:
    items = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}, {"id": 3, "name": ""}]
    assert named_dict(items) == {"A": {}, "B": {}}


def test_named_dict_with_id_carries_identifiers() -> None:
    out = named_dict_with_id(
        [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        source="metron",
        id_type="character",
    )
    assert out["Alice"]["identifiers"]["metron"]["key"] == "1"
    assert out["Bob"]["identifiers"]["metron"]["key"] == "2"


def test_build_identifier_includes_url_when_known_source() -> None:
    out = build_identifier("metron", "issue", 42)
    assert out["key"] == "42"
    # metron is in IDENTIFIER_PARTS_MAP so a URL is built.
    assert out.get("url", "").startswith("http")


def test_parse_creator_roles_splits_comma_string() -> None:
    assert parse_creator_roles("writer, penciler, inker") == [
        "writer",
        "penciler",
        "inker",
    ]
    assert parse_creator_roles("writer") == ["writer"]
    assert parse_creator_roles("") == []
    assert parse_creator_roles(None) == []


def test_split_aliases() -> None:
    """ComicVine returns volume aliases newline-separated."""
    assert split_aliases("A\n\n B \nC") == ["A", "B", "C"]
    assert split_aliases("") == []
    assert split_aliases(None) == []


def test_alt_names_to_reprints_dedups_and_skips_primary() -> None:
    out = alt_names_to_reprints(
        ["Alt One", "alt one", " Foo Comics ", "", None], "Foo Comics"
    )
    # Case-insensitive dupe collapses to the first spelling; the name
    # matching the primary series is not a reprint of itself.
    assert out == [{"series": {"name": "Alt One"}}]


def test_alt_names_to_reprints_without_primary_name() -> None:
    assert alt_names_to_reprints(["Alt One"], None) == [{"series": {"name": "Alt One"}}]
    assert alt_names_to_reprints(None, "Foo Comics") == []


def test_credits_to_cb_string_role_form() -> None:
    """ComicVine creators carry roles as a comma-string."""
    out = credits_to_cb(
        [{"id": 1, "name": "Alan Moore", "roles": "writer, plot"}],
        creator_key="name",
        role_key="roles",
        role_is_string=True,
        source="comicvine",
    )
    assert "Alan Moore" in out
    assert set(out["Alan Moore"]["roles"]) == {"writer", "plot"}
    assert out["Alan Moore"]["identifiers"]["comicvine"]["key"] == "1"


def test_credits_to_cb_list_role_form() -> None:
    """Mokkari credits carry roles as a list of {id, name} dicts."""
    out = credits_to_cb(
        [
            {
                "id": 41,
                "creator": "Alan Moore",
                "role": [{"id": 1, "name": "Writer"}, {"id": 2, "name": "Plot"}],
            }
        ],
        creator_key="creator",
        role_key="role",
        role_is_string=False,
        source="metron",
    )
    assert set(out["Alan Moore"]["roles"]) == {"Writer", "Plot"}
    assert out["Alan Moore"]["identifiers"]["metron"]["key"] == "41"


def test_reprints_to_cb_keeps_id_and_issue() -> None:
    out = reprints_to_cb(
        [{"id": 5001, "issue": "Foo #5"}],
        source="metron",
    )
    assert len(out) == 1
    assert out[0]["issue"] == "Foo #5"
    assert out[0]["identifiers"]["metron"]["key"] == "5001"


# ----------------------------------------------------- Metron transform


_METRON_FIXTURE = {
    "metron_api": {
        "id": 42,
        "number": "5",
        "alt_number": "a",
        "cover_date": "2020-04-01",
        "store_date": "2020-04-15",
        "image": "https://m.example.com/c.jpg",
        "modified": "2020-04-02T12:00:00Z",
        "page_count": 24,
        "desc": "<p>A <em>short</em> description.</p>",
        "rating": {"id": 3, "name": "Teen"},
        "average_rating": "4.5",
        "rating_count": 25,
        "publisher": {"id": 1, "name": "Quality Comics"},
        "imprint": {"id": 2, "name": "Vertigo"},
        "series": {
            "id": 100,
            "name": "Foo Comics",
            "sort_name": "Foo Comics",
            "volume": 1,
            "year_began": 2018,
            "genres": [{"id": 1, "name": "Superhero"}],
            "alt_names": ["Fu Comics"],
        },
        "story_titles": ["Title One", "Title Two"],
        "isbn": "978-1234",
        "upc": "00001",
        "characters": [{"id": 11, "name": "Alice"}, {"id": 12, "name": "Bob"}],
        "teams": [{"id": 21, "name": "X-Team"}],
        "arcs": [{"id": 31, "name": "Arc A"}],
        "credits": [
            {
                "id": 41,
                "creator": "Alan Moore",
                "role": [{"id": 1, "name": "Writer"}],
            }
        ],
        "reprints": [{"id": 5001, "issue": "Foo Comics #5"}],
        "cv_id": 99,
        "gcd_id": 88,
    }
}


_METRON_CB: dict[str, Any] = dict(MetronApiTransform().to_comicbox(_METRON_FIXTURE))[
    "comicbox"
]


def test_metron_issue_block() -> None:
    assert _METRON_CB["issue"]["name"] == "5"
    assert "suffix" not in _METRON_CB["issue"]
    assert _METRON_CB["alternative_issue"]["name"] == "a"


def test_metron_community_rating() -> None:
    assert _METRON_CB["community_rating"] == {
        "average_rating": Decimal("4.5"),
        "rating_count": 25,
    }


def test_metron_dates() -> None:
    assert _METRON_CB["date"]["cover_date"].isoformat() == "2020-04-01"
    assert _METRON_CB["date"]["store_date"].isoformat() == "2020-04-15"


def test_metron_publishing_tags() -> None:
    assert _METRON_CB["series"]["name"] == "Foo Comics"
    assert _METRON_CB["series"]["start_year"] == 2018
    assert _METRON_CB["series"]["sort_name"] == "Foo Comics"
    assert _METRON_CB["volume"]["number"] == 1
    assert _METRON_CB["publisher"]["name"] == "Quality Comics"
    assert _METRON_CB["imprint"]["name"] == "Vertigo"


def test_metron_summary_sanitized() -> None:
    assert _METRON_CB["summary"] == "A short description."


def test_metron_age_rating() -> None:
    assert _METRON_CB["age_rating"] == "Teen"


def test_metron_collections() -> None:
    assert set(_METRON_CB["characters"]) == {"Alice", "Bob"}
    assert set(_METRON_CB["teams"]) == {"X-Team"}
    assert set(_METRON_CB["arcs"]) == {"Arc A"}
    assert set(_METRON_CB["genres"]) == {"Superhero"}


def test_metron_arc_identifier_url() -> None:
    """Metron arcs carry an arc-typed identifier url, not an empty one."""
    arc_identifier = _METRON_CB["arcs"]["Arc A"]["identifiers"]["metron"]
    assert arc_identifier["key"] == "31"
    assert arc_identifier["url"] == "https://metron.cloud/arc/31"


def test_metron_credits() -> None:
    assert "Alan Moore" in _METRON_CB["credits"]
    assert "Writer" in _METRON_CB["credits"]["Alan Moore"]["roles"]


def test_metron_stories() -> None:
    assert set(_METRON_CB["stories"]) == {"Title One", "Title Two"}


def test_metron_identifiers_cross_sourced() -> None:
    ids = _METRON_CB["identifiers"]
    assert ids["metron"]["key"] == "42"
    assert ids["comicvine"]["key"] == "99"
    assert ids["grandcomicsdatabase"]["key"] == "88"
    assert ids["isbn"]["key"] == "978-1234"


def test_metron_reprints() -> None:
    reprints = _METRON_CB["reprints"]
    assert reprints[0]["issue"] == "Foo Comics #5"
    # The series' alternative names follow the real reprints.
    assert {"series": {"name": "Fu Comics"}} in reprints


def test_metron_cover_image() -> None:
    assert _METRON_CB["cover_image"] == "https://m.example.com/c.jpg"


def test_metron_page_count() -> None:
    assert _METRON_CB["page_count"] == 24


def test_metron_handles_minimal_input() -> None:
    """Issue with just id+number+date+modified survives."""
    minimal = {
        "metron_api": {
            "id": 1,
            "number": "1",
            "cover_date": "2020-01-01",
            "modified": "2020-01-01T00:00:00Z",
        }
    }
    cb = dict(MetronApiTransform().to_comicbox(minimal))["comicbox"]
    assert cb["issue"]["name"] == "1"
    assert "summary" not in cb  # desc was missing


# ----------------------------------------------------- ComicVine transform


_CV_FIXTURE = {
    "comicvine_api": {
        "id": 92734,
        "name": "Behold...The Eye!",
        "number": "7",
        "cover_date": "1952-08-01",
        "store_date": "1952-08-15",
        "date_last_updated": "2020-04-02T12:00:00Z",
        "description": "<p>The exciting tale of...</p><p>And another paragraph.</p>",
        "image": {
            "thumbnail": "http://t.example.com/t.jpg",
            "medium_url": "http://t.example.com/m.jpg",
            "original_url": "http://t.example.com/o.jpg",
        },
        "volume": {"id": 12345, "name": "G.I. Joe"},
        # Publisher is injected by `ComicVineOnlineSource.get()` after a
        # secondary `get_volume(volume.id)` call.
        "publisher": {"id": 31, "name": "Ziff-Davis"},
        "characters": [{"id": 1, "name": "G.I. Joe"}],
        "story_arcs": [{"id": 9, "name": "Yarn Patrol"}],
        "creators": [
            {"id": 100, "name": "Bob Powell", "roles": "writer, penciler, inker"},
        ],
        "locations": [{"id": 200, "name": "Korea"}],
    }
}


_CV_CB: dict[str, Any] = dict(ComicVineApiTransform().to_comicbox(_CV_FIXTURE))[
    "comicbox"
]


def test_comicvine_issue_and_title() -> None:
    assert _CV_CB["issue"]["name"] == "7"
    assert _CV_CB["title"] == "Behold...The Eye!"


def test_comicvine_volume_renamed_to_series() -> None:
    assert _CV_CB["series"]["name"] == "G.I. Joe"
    assert _CV_CB["series"]["identifiers"]["comicvine"]["key"] == "12345"


def test_comicvine_publisher_mapped() -> None:
    """`publisher` injected by get(volume) flows through to the comicbox dict."""
    assert _CV_CB["publisher"]["name"] == "Ziff-Davis"


def test_comicvine_summary_sanitized() -> None:
    # nh3 strips the <p> tags but leaves newlines between paragraphs.
    s = _CV_CB["summary"]
    assert s.startswith("The exciting tale of")
    assert "<p>" not in s


def test_comicvine_cover_image_prefers_medium() -> None:
    assert _CV_CB["cover_image"] == "http://t.example.com/m.jpg"


def test_comicvine_collections() -> None:
    assert set(_CV_CB["characters"]) == {"G.I. Joe"}
    assert set(_CV_CB["arcs"]) == {"Yarn Patrol"}
    assert set(_CV_CB["locations"]) == {"Korea"}


def test_comicvine_arc_identifier_url() -> None:
    """ComicVine story arcs carry the 4045 arc-typed identifier url."""
    arc_identifier = _CV_CB["arcs"]["Yarn Patrol"]["identifiers"]["comicvine"]
    assert arc_identifier["key"] == "9"
    assert arc_identifier["url"] == "https://comicvine.gamespot.com/c/4045-9/"


def test_comicvine_credits_string_roles() -> None:
    bp = _CV_CB["credits"]["Bob Powell"]
    # Roles come back title-cased from the schema's RoleField.
    roles = {r.lower() for r in bp["roles"]}
    assert {"writer", "penciler", "inker"} <= roles


def test_comicvine_identifiers() -> None:
    assert _CV_CB["identifiers"]["comicvine"]["key"] == "92734"


def test_comicvine_dates() -> None:
    assert "cover_date" in _CV_CB["date"]
    assert "store_date" in _CV_CB["date"]


def test_comicvine_volume_aliases_to_reprints() -> None:
    """CV's newline-separated volume aliases become alternate-series reprints."""
    payload = {
        "comicvine_api": {
            "id": 1,
            "number": "1",
            "cover_date": "2020-01-01",
            "date_last_updated": "2020-01-01T00:00:00Z",
            "image": {"medium_url": "http://x"},
            "volume": {
                "id": 1,
                "name": "Foo Comics",
                "aliases": "Alias One\nfoo comics\n\n Alias Two ",
            },
        }
    }
    cb = dict(ComicVineApiTransform().to_comicbox(payload))["comicbox"]
    # Blank segment dropped; the alias equal to the volume name dropped.
    assert cb["reprints"] == [
        {"series": {"name": "Alias One"}},
        {"series": {"name": "Alias Two"}},
    ]


def test_comicvine_without_aliases_emits_no_reprints() -> None:
    assert "reprints" not in _CV_CB


def test_comicvine_handles_minimal_input() -> None:
    minimal = {
        "comicvine_api": {
            "id": 1,
            "number": "1",
            "cover_date": "2020-01-01",
            "date_last_updated": "2020-01-01T00:00:00Z",
            "image": {"medium_url": "http://x"},
            "volume": {"id": 1, "name": "S"},
        }
    }
    cb = dict(ComicVineApiTransform().to_comicbox(minimal))["comicbox"]
    assert cb["issue"]["name"] == "1"
    assert cb["series"]["name"] == "S"
