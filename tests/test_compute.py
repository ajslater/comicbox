"""Test getting pages."""

from argparse import Namespace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any
from unittest.mock import patch
from zipfile import ZipFile

from dateutil.tz import tzutc

from comicbox.box import Comicbox
from comicbox.enums.comicinfo import ComicInfoPageTypeEnum
from comicbox.formats import MetadataFormats
from comicbox.formats.comic_info.schema import ComicInfoSchema
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
from tests.const import PRINT_CONFIG, TEST_FILES_DIR, TEST_METADATA_DIR
from tests.util import assert_diff

DATE_FROM_NOTES_IMPORT = TEST_METADATA_DIR / "comicinfo-notes-date.xml"
DATE_FROM_NOTES_MD = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "date": {
                "cover_date": date(2025, 4, 11),
                "year": 2025,
                "month": 4,
                "day": 11,
            },
            "identifiers": {
                "comicvine": {
                    "key": "145269",
                }
            },
            "notes": "Tagged with comicbox dev on 1970-01-01T00:00:00Z [Issue ID 145269] [CVDB145269] [RELDATE:2025-04-11]",
            "urls": ["https://comicvine.gamespot.com/c/4000-145269/"],
            "tagger": "comicbox dev",
            "updated_at": datetime(1970, 1, 1, 0, 0, tzinfo=tzutc()),
        },
    }
)


def test_compute_date_from_notes() -> None:
    """Test getting the cover image."""
    config = Namespace(
        comicbox=Namespace(convert=Namespace(import_paths=(DATE_FROM_NOTES_IMPORT,)))
    )
    with Comicbox(config=config) as car:
        md = car.get_internal_metadata()
    assert_diff(DATE_FROM_NOTES_MD, md)


IDS_FROM_TAGS_IMPORT = TEST_METADATA_DIR / "comicinfo-ids-from-tags.xml"
IDS_FROM_TAGS_MD = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "identifiers": {
                "comicvine": {
                    "key": "1234",
                },
                "metron": {
                    "key": "9999",
                },
            },
            "urls": [
                "https://comicvine.gamespot.com/c/4000-1234/",
                "https://metron.cloud/issue/9999",
            ],
            "tags": {"urn:metron:9999": {}, "CVDB1234": {}},
        },
    }
)


def test_compute_ids_from_tags() -> None:
    """Test computing identifiers from tags."""
    config = Namespace(
        comicbox=Namespace(
            print=Namespace(phases="snmcp"),
            convert=Namespace(import_paths=(IDS_FROM_TAGS_IMPORT,)),
        )
    )
    with Comicbox(config=config) as car:
        md = car.get_internal_metadata()

    assert_diff(IDS_FROM_TAGS_MD, md)


PREFIXED_KEYS_YAML = """
comicbox:
  identifiers:
    comicvine:
      key: "series:160294"
    grandcomicsdatabase:
      key: "series:999"
    leagueofcomicgeeks:
      key: "series:178012"
    metron:
      key: "series:5678"
  series:
    name: Foo
    identifiers:
      comicvine:
        key: "4050-160294"
"""
_CV_SERIES_IDENTIFIER = {
    "key": "160294",
    "id_type": "series",
}
PREFIXED_KEYS_MD = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "identifiers": {
                "comicvine": _CV_SERIES_IDENTIFIER,
                "grandcomicsdatabase": {
                    "key": "999",
                    "id_type": "series",
                },
                "leagueofcomicgeeks": {
                    "key": "178012",
                    "id_type": "series",
                },
                "metron": {
                    "key": "5678",
                    "id_type": "series",
                },
            },
            "urls": [
                "https://comicvine.gamespot.com/c/4050-160294/",
                "https://comics.org/series/999/",
                "https://leagueofcomicgeeks.com/comics/series/178012/s",
                "https://metron.cloud/series/5678",
            ],
            "series": {
                "name": "Foo",
                # The series id sits in a series, so its type is implied.
                "identifiers": {"comicvine": {"key": "160294"}},
            },
        },
    }
)


def test_compute_type_prefixed_identifier_keys() -> None:
    """Hand-tagged 'series:' prefixed keys normalize and get series urls."""
    with Comicbox() as car:
        car.add_metadata(PREFIXED_KEYS_YAML, MetadataFormats.COMICBOX_YAML)
        md = car.get_internal_metadata()
    assert_diff(PREFIXED_KEYS_MD, md)


MULTI_URN_NOTES_YAML = """
comicbox:
  notes: "urn:comicvine:issue:145269 urn:metron:issue:999999"
"""
MULTI_URN_NOTES_MD = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "identifiers": {
                "comicvine": {
                    "key": "145269",
                },
                "metron": {
                    "key": "999999",
                },
            },
            "urls": [
                "https://comicvine.gamespot.com/c/4000-145269/",
                "https://metron.cloud/issue/999999",
            ],
            "notes": "urn:comicvine:issue:145269 urn:metron:issue:999999",
        },
    }
)


def test_compute_all_urns_from_notes() -> None:
    """Every urn in a notes field becomes an identifier, not just the first."""
    with Comicbox() as car:
        car.add_metadata(MULTI_URN_NOTES_YAML, MetadataFormats.COMICBOX_YAML)
        md = car.get_internal_metadata()
    assert_diff(MULTI_URN_NOTES_MD, md)


PUNCTUATED_URN_NOTES_YAML = """
comicbox:
  notes: "Read urn:metron:issue:2002, then the next one."
"""


def test_compute_urn_in_a_sentence_keeps_its_punctuation_out() -> None:
    """A urn ends with its key, not at the next space."""
    with Comicbox() as car:
        car.add_metadata(PUNCTUATED_URN_NOTES_YAML, MetadataFormats.COMICBOX_YAML)
        md = car.get_internal_metadata()
    identifiers = md[ComicboxSchemaMixin.ROOT_TAG]["identifiers"]
    assert identifiers["metron"]["key"] == "2002"


SOURCE_TYPE_KEY_TAG_XML = (
    '<?xml version="1.0"?><ComicInfo>'
    "<Tags>leagueofcomicgeeks:series:178012</Tags>"
    "</ComicInfo>"
)
SOURCE_TYPE_KEY_TAG_MD = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "identifiers": {
                "leagueofcomicgeeks": {
                    "key": "178012",
                    "id_type": "series",
                },
            },
            "urls": ["https://leagueofcomicgeeks.com/comics/series/178012/s"],
            "tags": {"leagueofcomicgeeks:series:178012": {}},
        },
    }
)


def test_compute_ids_from_source_type_key_tag() -> None:
    """A 'source:type:key' tag keeps its id number and typed url."""
    with Comicbox() as car:
        car.add_metadata(SOURCE_TYPE_KEY_TAG_XML, MetadataFormats.COMIC_INFO)
        md = car.get_internal_metadata()
    assert_diff(SOURCE_TYPE_KEY_TAG_MD, md)


ISSUE_NAME_ONLY_MD = MappingProxyType(
    {ComicInfoSchema.ROOT_TAG: {"Number": "1234SUFFIX"}}
)
ISSUE_WITH_PARTS = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "issue": {"name": "1234SUFFIX", "number": Decimal(1234), "suffix": "SUFFIX"}
        }
    }
)


def test_compute_issue_suffix() -> None:
    """Test computing identifiers from tags."""
    with Comicbox(
        metadata=ISSUE_NAME_ONLY_MD,
        fmt=MetadataFormats.COMIC_INFO,
        config=PRINT_CONFIG,
    ) as car:
        md = car.get_internal_metadata()

    assert_diff(ISSUE_WITH_PARTS, md)


ISSUE_PARTS_ONLY_MD = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "issue": {"number": Decimal(1234), "suffix": "SUFFIX"}
        }
    }
)


def test_compute_issue_name() -> None:
    """Test computing identifiers from tags."""
    with Comicbox(
        metadata=ISSUE_PARTS_ONLY_MD,
        fmt=MetadataFormats.COMICBOX_JSON,
        config=PRINT_CONFIG,
    ) as car:
        md = car.get_internal_metadata()

    assert_diff(ISSUE_WITH_PARTS, md)


ISSUE_SUFFIX_NO_NUMBER_YAML = """
comicbox:
  issue:
    name: "1234AU"
    suffix: "AU"
"""


def test_compute_issue_number_from_name_with_a_suffix() -> None:
    """A named issue that states a suffix but no number still gets a number."""
    with Comicbox() as car:
        car.add_metadata(ISSUE_SUFFIX_NO_NUMBER_YAML, MetadataFormats.COMICBOX_YAML)
        md = car.get_internal_metadata()
    issue = md[ComicboxSchemaMixin.ROOT_TAG]["issue"]
    assert issue["number"] == Decimal(1234)
    assert issue["suffix"] == "AU"
    assert issue["name"] == "1234AU"


IMPOSSIBLE_DAY_YAML = """
comicbox:
  date:
    year: 2020
    month: 2
    day: 30
"""
IMPOSSIBLE_DAY_MD = MappingProxyType(
    {ComicboxSchemaMixin.ROOT_TAG: {"date": {"year": 2020, "month": 2}}}
)


def test_compute_deletes_impossible_date_parts() -> None:
    """A day that cannot exist is dropped, not merely flagged."""
    with Comicbox() as car:
        car.add_metadata(IMPOSSIBLE_DAY_YAML, MetadataFormats.COMICBOX_YAML)
        md = car.get_internal_metadata()
        dumped = car.to_dict()
    assert_diff(IMPOSSIBLE_DAY_MD, md)
    date_dict = dumped[ComicboxSchemaMixin.ROOT_TAG]["date"]
    assert "day" not in date_dict
    assert "cover_date" not in date_dict


def _notes_md(notes: str) -> dict:
    """Read one notes string through the computed pipeline."""
    yaml = f'comicbox:\n  notes: "{notes}"\n'
    with Comicbox() as car:
        car.add_metadata(yaml, MetadataFormats.COMICBOX_YAML)
        md = car.get_internal_metadata()
    return dict(md[ComicboxSchemaMixin.ROOT_TAG])


# ComicTagger writes the source it used between the tagger and the timestamp,
# and most of the sources comicbox knows are named with more than one word.
COMICTAGGER_NOTES_TMPL = (
    "Tagged with ComicTagger 1.3.2a5 using info from {origin} "
    "on 2022-04-16 15:52:26. [Issue ID 140529]"
)


def test_compute_notes_multi_word_origin() -> None:
    """A multi-word source name in a ComicTagger stamp names its source."""
    for origin, id_source in (
        ("Comic Vine", "comicvine"),
        ("Grand Comics Database", "grandcomicsdatabase"),
        ("League of Comic Geeks", "leagueofcomicgeeks"),
        ("Metron", "metron"),
    ):
        md = _notes_md(COMICTAGGER_NOTES_TMPL.format(origin=origin))
        assert md["identifiers"] == {id_source: {"key": "140529"}}, origin


def test_compute_notes_origin_is_case_insensitive() -> None:
    """Source names are matched the way every other alias lookup matches."""
    md = _notes_md(COMICTAGGER_NOTES_TMPL.format(origin="comic vine"))
    assert md["identifiers"] == {"comicvine": {"key": "140529"}}


def test_compute_notes_unknown_origin_names_no_source() -> None:
    """An unrecognized source is not quietly filed under the default one."""
    md = _notes_md(COMICTAGGER_NOTES_TMPL.format(origin="Nonesuch"))
    assert "identifiers" not in md


def test_compute_notes_unparsable_updated_at_is_not_written() -> None:
    """A timestamp the pattern admits but no parser accepts is skipped."""
    md = _notes_md("Tagged with ComicTagger on 2020-19-19 12:00:00")
    assert md["tagger"] == "ComicTagger"
    assert "updated_at" not in md


# Everything the notes parser can read, in one string: a tagger, a timestamp,
# a ComicTagger origin + issue id, a bracketed identifier, a urn, a RELDATE
# and a url.
ROUND_TRIP_NOTES = (
    "Tagged with ComicTagger 1.3.2a5 using info from Grand Comics Database "
    "on 2022-04-16 15:52:26. [Issue ID 555] [CVDB140529] urn:metron:issue:999 "
    "[RELDATE:2025-04-11] see https://leagueofcomicgeeks.com/comic/1234/x too."
)
ROUND_TRIP_YAML = f'comicbox:\n  notes: "{ROUND_TRIP_NOTES}"\n'
STAMP_CONFIG = Namespace(
    comicbox=Namespace(
        write=Namespace(stamp=True), general=Namespace(tagger="comicbox test")
    )
)


def test_compute_notes_survive_the_tagger_stamp() -> None:
    """
    Everything the notes parser reads survives the stamp that replaces notes.

    The stamp rebuilds the notes text from the structured fields, so the text
    itself changes. What must not change is the data: see the audit in the
    comicbox.box.computed.notes module docstring for each difference and why
    it is a difference in spelling rather than a loss.
    """
    with Comicbox(config=STAMP_CONFIG) as car:
        car.add_metadata(ROUND_TRIP_YAML, MetadataFormats.COMICBOX_YAML)
        md = dict(car.get_internal_metadata()[ComicboxSchemaMixin.ROOT_TAG])

    # Every id the notes named, from all three of its grammars.
    assert md["identifiers"] == {
        "grandcomicsdatabase": {"key": "555"},
        "comicvine": {"key": "140529"},
        "metron": {"key": "999"},
        "leagueofcomicgeeks": {"key": "1234"},
    }
    # The url the prose carried, kept before the stamp overwrote the prose.
    assert "https://leagueofcomicgeeks.com/comic/1234/x" in md["urls"]
    # RELDATE, as a real date rather than a bracketed word.
    assert md["date"]["cover_date"] == date(2025, 4, 11)
    # The stamp is comicbox's own; it replaces the tagger it read.
    assert md["tagger"] == "comicbox test"
    # Every identifier comes back out of the rewritten notes as a urn.
    notes = md["notes"]
    for urn in (
        "urn:comicvine:140529",
        "urn:grandcomicsdatabase:555",
        "urn:leagueofcomicgeeks:1234",
        "urn:metron:999",
    ):
        assert urn in notes, urn
    assert notes.startswith("Tagged with comicbox test on ")


def _one_image_cbz(tmp_path: Path, count: int) -> Path:
    """Build a cbz of real images and nothing else, so pages compute fresh."""
    images = sorted((TEST_FILES_DIR / "Captain Science 001").glob("*.jpg"))[:count]
    archive_path = tmp_path / "computed-pages.cbz"
    with ZipFile(archive_path, "w") as zf:
        for image in images:
            zf.write(image, image.name)
    return archive_path


PAGES_CONFIG = Namespace(comicbox=Namespace(compute=Namespace(pages=True)))


def test_compute_pages_without_a_first_page(tmp_path: Path) -> None:
    """A missing page 0 marks the first page present, and never aborts."""
    archive_path = _one_image_cbz(tmp_path, 3)
    with Comicbox(archive_path, config=PAGES_CONFIG) as car:
        real_get_info_size = car._get_info_size
        skipped = []

        def sizeless_first_image(info: Any) -> int | None:
            filename = car._get_info_fn(info)
            if car.IMAGE_EXT_RE.search(filename) is not None and not skipped:
                skipped.append(filename)
                return None
            return real_get_info_size(info)

        with patch.object(car, "_get_info_size", sizeless_first_image):
            car._dict_formats = frozenset({MetadataFormats.COMIC_INFO})
            md = dict(car.get_internal_metadata()[ComicboxSchemaMixin.ROOT_TAG])

    pages = md["pages"]
    assert 0 not in pages
    assert pages[min(pages)]["page_type"] == ComicInfoPageTypeEnum.FRONT_COVER
    # The rest of the computed pass ran instead of being aborted by the
    # missing page.
    assert md["page_count"] == 3
