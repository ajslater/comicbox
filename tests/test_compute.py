"""Test getting pages."""

from argparse import Namespace
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType

from dateutil.tz import tzutc

from comicbox.box import Comicbox
from comicbox.formats import MetadataFormats
from comicbox.formats.comic_info.schema import ComicInfoSchema
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
from tests.const import PRINT_CONFIG, TEST_METADATA_DIR
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
}
PREFIXED_KEYS_MD = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "identifiers": {
                "comicvine": _CV_SERIES_IDENTIFIER,
                "grandcomicsdatabase": {
                    "key": "999",
                },
                "leagueofcomicgeeks": {
                    "key": "178012",
                },
                "metron": {
                    "key": "5678",
                },
            },
            "series": {
                "name": "Foo",
                "identifiers": {"comicvine": _CV_SERIES_IDENTIFIER},
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
                },
            },
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
