"""Test getting pages."""

from argparse import Namespace
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType

from dateutil.tz import tzutc

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.schemas.comictagger import ComictaggerSchema
from tests.const import TEST_METADATA_DIR
from tests.util import assert_diff

PRINT_CONFIG = get_config(
    Namespace(
        comicbox=Namespace(
            print="snmcp",
        )
    )
)


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
                    "id_key": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "notes": "Tagged with comicbox dev on 1970-01-01T00:00:00Z [Issue ID 145269] [CVDB145269] [RELDATE:2025-04-11]",
            "tagger": "comicbox dev",
            "updated_at": datetime(1970, 1, 1, 0, 0, tzinfo=tzutc()),
        },
    }
)


def test_compute_date_from_notes():
    """Test getting the cover image."""
    config = Namespace(comicbox=Namespace(import_paths=(DATE_FROM_NOTES_IMPORT,)))
    with Comicbox(config=config) as car:
        md = car.get_metadata()
    assert_diff(DATE_FROM_NOTES_MD, md)


IDS_FROM_TAGS_IMPORT = TEST_METADATA_DIR / "comicinfo-ids-from-tags.xml"
IDS_FROM_TAGS_MD = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "identifiers": {
                "comicvine": {
                    "id_key": "1234",
                    "url": "https://comicvine.gamespot.com/c/4000-1234/",
                },
                "metron": {
                    "id_key": "9999",
                    "url": "https://metron.cloud/issue/9999",
                },
            },
            "tags": {"urn:metron:9999": {}, "CVDB1234": {}},
        },
    }
)


def test_compute_ids_from_tags():
    """Test computing identifiers from tags."""
    config = Namespace(
        comicbox=Namespace(import_paths=(IDS_FROM_TAGS_IMPORT,), print="snmcp")
    )
    with Comicbox(config=config) as car:
        md = car.get_metadata()

    assert_diff(IDS_FROM_TAGS_MD, md)


ISSUE_NAME_ONLY_MD = MappingProxyType(
    {ComictaggerSchema.ROOT_TAG: {"issue": "1234SUFFIX"}}
)
ISSUE_WITH_PARTS = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "issue": {"name": "1234SUFFIX", "number": Decimal(1234), "suffix": "SUFFIX"}
        }
    }
)


def test_compute_issue_suffix():
    """Test computing identifiers from tags."""
    with Comicbox(
        metadata=ISSUE_NAME_ONLY_MD,
        fmt=MetadataFormats.COMICTAGGER,
        config=PRINT_CONFIG,
    ) as car:
        md = car.get_metadata()

    assert_diff(ISSUE_WITH_PARTS, md)


ISSUE_PARTS_ONLY_MD = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "issue": {"number": Decimal(1234), "suffix": "SUFFIX"}
        }
    }
)


def test_compute_issue_name():
    """Test computing identifiers from tags."""
    with Comicbox(
        metadata=ISSUE_PARTS_ONLY_MD,
        fmt=MetadataFormats.COMICBOX_JSON,
        config=PRINT_CONFIG,
    ) as car:
        md = car.get_metadata()

    assert_diff(ISSUE_WITH_PARTS, md)


UNKNOWN_URLS = MappingProxyType(
    {
        ComictaggerSchema.ROOT_TAG: {
            "web_link": "http://foo.bar,https://google.com,https://bar.ct/?attr=1#tag"
        }
    }
)

IDENTIFIERS_FROM_URLS = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "identifiers": {
                "bar.ct": {
                    "id_key": "?attr=1#tag",
                    "url": "https://bar.ct/?attr=1#tag",
                },
                "foo.bar": {"url": "http://foo.bar"},
                "google.com": {"url": "https://google.com"},
            }
        }
    }
)


def test_other_urls():
    """Test non known id_source urls."""
    with Comicbox(
        metadata=UNKNOWN_URLS,
        fmt=MetadataFormats.COMICTAGGER,
        config=PRINT_CONFIG,
    ) as car:
        md = car.get_metadata()

    assert_diff(IDENTIFIERS_FROM_URLS, md)
