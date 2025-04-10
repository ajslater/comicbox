"""Test getting pages."""

from argparse import Namespace
from datetime import date, datetime
from types import MappingProxyType

from dateutil.tz import tzutc

from comicbox.box import Comicbox
from tests.const import TEST_METADATA_DIR
from tests.util import assert_diff

DATE_FROM_NOTES_IMPORT = TEST_METADATA_DIR / "comicinfo-notes-date.xml"
DATE_FROM_NOTES_MD = MappingProxyType(
    {
        "comicbox": {
            "date": {
                "cover_date": date(2025, 4, 11),
                "year": 2025,
                "month": 4,
                "day": 11,
            },
            "identifiers": {
                "comicvine": {
                    "nss": "145269",
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
        "comicbox": {
            "identifiers": {
                "comicvine": {
                    "nss": "1234",
                    "url": "https://comicvine.gamespot.com/c/4000-1234/",
                },
                "metron": {
                    "nss": "9999",
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
