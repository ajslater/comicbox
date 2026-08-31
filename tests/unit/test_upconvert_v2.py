"""Comicbox v2.0 documents read into the v3.0 shape."""

from typing import Any

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.comicbox.schema.upconvert import upconvert_v2
from tests.const import TEST_METADATA_DIR


def _up(sub_data: dict[str, Any]) -> dict:
    return upconvert_v2({"comicbox": sub_data})["comicbox"]


def test_removed_fields_are_dropped() -> None:
    """Two fields that mapped to no format are gone."""
    out = _up({"critical_rating": 5.0, "alternate_images": ["a.jxl"], "title": "T"})
    assert out == {"title": "T"}


def test_identifier_urls_move_to_the_urls_list() -> None:
    """A url stored inside an identifier becomes a url."""
    out = _up(
        {
            "identifiers": {
                "comicvine": {
                    "key": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            }
        }
    )
    assert out["identifiers"] == {"comicvine": {"key": "145269"}}
    assert out["urls"] == ["https://comicvine.gamespot.com/c/4000-145269/"]


def test_nested_identifier_urls_move_too() -> None:
    """Every entity's identifiers are converted, not just the top level."""
    out = _up(
        {
            "series": {
                "name": "S",
                "identifiers": {"metron": {"key": "1", "url": "https://a.test/1"}},
            },
            "characters": {
                "Bob": {
                    "identifiers": {"metron": {"key": "2", "url": "https://a.test/2"}}
                }
            },
            "credits": {
                "Ann": {
                    "roles": {
                        "Writer": {
                            "identifiers": {
                                "metron": {"key": "3", "url": "https://a.test/3"}
                            }
                        }
                    }
                }
            },
        }
    )
    assert out["series"]["identifiers"]["metron"] == {"key": "1"}
    assert out["characters"]["Bob"]["identifiers"]["metron"] == {"key": "2"}
    roles = out["credits"]["Ann"]["roles"]
    assert roles["Writer"]["identifiers"]["metron"] == {"key": "3"}
    assert out["urls"] == ["https://a.test/1", "https://a.test/2", "https://a.test/3"]


def test_hostname_identifiers_are_dropped_but_their_urls_kept() -> None:
    """v2 minted an identifier per unknown hostname; nothing could use it."""
    out = _up({"identifiers": {"bar.foo": {"url": "https://bar.foo"}}})
    assert not out.get("identifiers")
    assert out["urls"] == ["https://bar.foo"]


def test_primary_source_collapses_to_a_string() -> None:
    """Its url was synthesized from the source, never read from a file."""
    out = _up(
        {
            "identifier_primary_source": {
                "source": "metron",
                "url": "https://metron.cloud/",
            }
        }
    )
    assert out["primary_id_source"] == "metron"
    assert "identifier_primary_source" not in out


def test_credit_primaries_fold_onto_the_role() -> None:
    """The flat map named a role and a person; the flag belongs to both."""
    out = _up(
        {
            "credits": {
                "Ann": {"roles": {"Writer": {}, "Inker": {}}},
                "Bob": {"roles": {"Inker": {}}},
            },
            "credit_primaries": {"Writer": "Ann"},
        }
    )
    roles = out["credits"]["Ann"]["roles"]
    assert roles["Writer"]["primary"] is True
    # Being the primary Writer never made Ann the primary Inker.
    assert "primary" not in roles["Inker"]
    assert "primary" not in out["credits"]["Bob"]["roles"]["Inker"]
    assert "credit_primaries" not in out


def test_manga_splits_from_reading_direction() -> None:
    """The compound value carried two facts."""
    out = _up({"manga": "YesAndRightToLeft"})
    assert out["manga"] == "Yes"
    assert out["reading_direction"] == "rtl"


def test_manga_does_not_overwrite_a_stated_reading_direction() -> None:
    """A direction the document stated wins."""
    out = _up({"manga": "YesAndRightToLeft", "reading_direction": "ltr"})
    assert out["reading_direction"] == "ltr"


def test_a_structured_reprint_gains_a_name() -> None:
    """v3 stores a reprint under the name it goes by."""
    out = _up(
        {
            "reprints": [
                {"series": {"name": "Captain Science Alternate"}, "issue": "001"}
            ]
        }
    )
    assert out["reprints"][0]["name"] == "Captain Science Alternate #001"


def test_converting_twice_changes_nothing() -> None:
    """Every rule is guarded, so this runs on v3 documents harmlessly."""
    v2 = {
        "identifiers": {"comicvine": {"key": "1", "url": "https://a.test/1"}},
        "identifier_primary_source": {"source": "comicvine"},
        "credits": {"Ann": {"roles": {"Writer": {}}}},
        "credit_primaries": {"Writer": "Ann"},
        "manga": "YesAndRightToLeft",
    }
    once = _up(v2)
    twice = _up(dict(once))
    assert once == twice


def test_a_document_without_the_root_is_untouched() -> None:
    """Nothing to convert, nothing to break."""
    assert upconvert_v2({"other": 1}) == {"other": 1}
    assert upconvert_v2(None) is None


def test_a_v2_document_loads_through_the_whole_pipeline() -> None:
    """A frozen v2.0 file reads as v3, end to end."""
    src = (TEST_METADATA_DIR / "comicbox-v2.yaml").read_text()
    with Comicbox() as car:
        car.add_metadata(src, MetadataFormats.COMICBOX_YAML)
        sub_md = dict(car.to_dict().get("comicbox", {}))

    assert "critical_rating" not in sub_md
    assert "alternate_images" not in sub_md
    assert "credit_primaries" not in sub_md
    assert "identifier_primary_source" not in sub_md

    assert sub_md["identifiers"]["comicvine"] == {"key": "145269"}
    assert sub_md["primary_id_source"] == "comicvine"
    assert (
        "https://comicvine.gamespot.com/captain-science-1/4000-145269/"
        in sub_md["urls"]
    )
    assert sub_md["credits"]["Joe Orlando"]["roles"]["Writer"]["primary"] is True
    assert sub_md["manga"] == "Yes"
    assert sub_md["reading_direction"] == "rtl"
    assert sub_md["reprints"][0]["name"] == "Captain Science Alternate #001"
