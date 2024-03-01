"""Tests for writing."""

from argparse import Namespace
from datetime import date, datetime
from decimal import Decimal
from pprint import pprint
from types import MappingProxyType

import pytest
from deepdiff.diff import DeepDiff

from comicbox.box import Comicbox
from comicbox.fields.enum import ReadingDirectionEnum
from tests.const import (
    EMPTY_CBZ_SOURCE_PATH,
    TEST_METADATA_DIR,
)

FNS = MappingProxyType(
    {
        "comet.xml": {
            "age_rating": "Teen",
            "characters": {"Captain Science", "Gordon Dane"},
            "contributors": {"penciller": {"Wally Wood"}, "writer": {"Joe Orlando"}},
            "cover_image": "CaptainScience#1_01.jpg",
            "date": date(1950, 12, 1),
            "ext": "cbz",
            "genres": {"Science Fiction"},
            "identifiers": {
                "comicvine": {
                    "nss": "4000-145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "last_mark": 12,
            "original_format": "Comic",
            "page_count": 0,
            "price": Decimal("0.10"),
            "publisher": "Bell Features",
            "reading_direction": ReadingDirectionEnum.LTR,
            "reprints": [
                {"issue": "001", "series": {"name": "Captain Science " "Alternate"}}
            ],
            "rights": "Copyright (c) 1950 Bell Features",
            "series": {"name": "Captain Science"},
            "summary": "A long example description",
            "title": "The Beginning",
            "volume": {"name": 1},
        },
        "comic-book-info.json": {
            "contributors": {"penciller": {"Wally Wood"}, "writer": {"Joe Orlando"}},
            "country": "US",
            "ext": "cbz",
            "genres": {"Science Fiction"},
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "month": 11,
            "page_count": 0,
            "publisher": "Youthful Adventure Stories",
            "series": {"name": "Captain Science", "volume_count": 1},
            "title": "The Beginning",
            "updated_at": datetime(1970, 1, 1, 0, 0),
            "volume": {"issue_count": 7, "name": 1950},
            "year": 1950,
        },
        "comicbox-filename.txt": {
            "series": {"name": "Captain Science"},
            "issue": "001",
            "issue_number": Decimal("1"),
            "year": 1950,
            "title": "The Beginning - nothing",
            "ext": "cbz",
            "page_count": 0,
        },
        "comicbox.json": {
            "contributors": {"penciller": {"Wally Wood"}, "writer": {"Joe Orlando"}},
            "country": "US",
            "day": 1,
            "ext": "cbz",
            "genres": {"Science Fiction"},
            "identifiers": {
                "comicvine": {
                    "nss": "4000-145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "month": 11,
            "notes": "Tagged with comicbox dev on "
            "1970-01-01T00:00:00 [Issue ID 145269] "
            "[CVDB145269]",
            "page_count": 0,
            "publisher": "Youthful Adventure Stories",
            "series": {"name": "Captain Science"},
            "tagger": "comicbox dev",
            "title": "The Beginning",
            "updated_at": datetime(1970, 1, 1, 0, 0),
            "volume": {"issue_count": 7, "name": 1950},
            "year": 1950,
        },
        "comicbox.yaml": {
            "ext": "cbz",
            "identifiers": {
                "comicvine": {
                    "nss": "4000-145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "imprint": "TestImprint",
            "notes": "Tagged with comicbox dev on "
            "1970-01-01T00:00:00 [Issue ID 145269] "
            "[CVDB145269]",
            "page_count": 0,
            "publisher": "TestPub",
            "series": {"name": "empty"},
            "story_arcs": {"d": 1, "e": 3, "f": 5},
            "tagger": "comicbox dev",
            "tags": {"a", "c", "b"},
            "updated_at": datetime(1970, 1, 1, 0, 0),
        },
        "comicinfo.xml": {
            "characters": {"Captain Science", "Gordon Dane"},
            "contributors": {
                "inker": {"Wally Wood"},
                "penciller": {"Wally Wood"},
                "writer": {"Joe Orlando"},
            },
            "day": 1,
            "ext": "cbz",
            "genres": {"Science Fiction"},
            "identifiers": {
                "comicvine": {
                    "nss": "4000-145269",
                    "url": "https://comicvine.gamespot.com/captain-science-1/4000-145269/",
                }
            },
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "month": 11,
            "notes": "Tagged with comicbox dev on "
            "1970-01-01T00:00:00 [Issue ID 145269] "
            "[CVDB145269]",
            "page_count": 0,
            "publisher": "Youthful Adventure Stories",
            "reprints": [
                {"issue": "001", "series": {"name": "Captain Science " "Alternate"}}
            ],
            "series": {"name": "Captain Science"},
            "story_arcs": {"Captain Arc": 4, "Other Arc": 2},
            "tagger": "comicbox dev",
            "title": "The Beginning",
            "updated_at": datetime(1970, 1, 1, 0, 0),
            "volume": {"issue_count": 7, "name": 1950},
            "year": 1950,
        },
        "comictagger.json": {
            "contributors": {"penciller": {"Wally Wood"}, "writer": {"Joe Orlando"}},
            "country": "US",
            "day": 1,
            "ext": "cbz",
            "genres": {"Science Fiction"},
            "identifiers": {
                "comicvine": {
                    "nss": "4000-145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "month": 11,
            "notes": "Tagged with comicbox dev on "
            "1970-01-01T00:00:00 [Issue ID 145269] "
            "[CVDB145269]",
            "page_count": 0,
            "publisher": "Youthful Adventure Stories",
            "series": {"name": "Captain Science"},
            "tagger": "comicbox dev",
            "title": "The Beginning",
            "updated_at": datetime(1970, 1, 1, 0, 0),
            "volume": {"issue_count": 7, "name": 1950},
            "year": 1950,
        },
    }
)


@pytest.mark.parametrize("fn", FNS)
def test_import(fn):
    """Test converting cbr to cbz and writing cbi info as cix."""
    test_md = MappingProxyType({"comicbox": FNS[fn]})
    import_path = TEST_METADATA_DIR / fn
    cns = Namespace(import_paths=[import_path])
    config = Namespace(comicbox=cns)
    with Comicbox(EMPTY_CBZ_SOURCE_PATH, config=config) as car:
        md = car.get_metadata()

    diff = DeepDiff(test_md, md)
    pprint(test_md)
    pprint(md)
    print(diff)
    assert not diff
