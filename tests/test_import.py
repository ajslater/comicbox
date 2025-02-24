"""Tests for writing."""

from argparse import Namespace
from datetime import date, datetime
from decimal import Decimal
from pprint import pprint
from types import MappingProxyType

import pytest
from deepdiff.diff import DeepDiff

from comicbox.box import Comicbox
from comicbox.fields.enum_fields import ReadingDirectionEnum
from tests.const import (
    EMPTY_CBZ_SOURCE_PATH,
    TEST_METADATA_DIR,
)

FNS = MappingProxyType(
    {
        "comet.xml": {
            "age_rating": "Teen",
            "characters": {"Captain Science": {}, "Gordon Dane": {}},
            "credits": {
                "Joe Orlando": {"roles": {"writer": {}}},
                "Wally Wood": {"roles": {"penciller": {}}},
            },
            "cover_image": "CaptainScience#1_01.jpg",
            "date": date(1950, 12, 1),
            "ext": "cbz",
            "genres": {"Science Fiction": {}},
            "identifiers": {
                "comicvine": {
                    "nss": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "last_mark": 12,
            "original_format": "Comic",
            "page_count": 0,
            "prices": {"": Decimal("0.10")},
            "publisher": {"name": "Bell Features"},
            "reading_direction": ReadingDirectionEnum.LTR,
            "reprints": [
                {"issue": "001", "series": {"name": "Captain Science Alternate"}}
            ],
            "rights": "Copyright (c) 1950 Bell Features",
            "series": {"name": "Captain Science"},
            "stories": {"The Beginning": {}},
            "summary": "A long example description",
            "volume": {"number": 1},
        },
        "comic-book-info.json": {
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Penciller": {}}},
            },
            "country": "US",
            "ext": "cbz",
            "genres": {"Science Fiction": {}},
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "month": 11,
            "page_count": 0,
            "publisher": {"name": "Youthful Adventure Stories"},
            "series": {"name": "Captain Science", "volume_count": 1},
            "stories": {"The Beginning": {}},
            "updated_at": datetime(1970, 1, 1, 0, 0),
            "volume": {"issue_count": 7, "number": 1950},
            "year": 1950,
        },
        "comicbox-filename.txt": {
            "series": {"name": "Captain Science"},
            "issue": "001",
            "issue_number": Decimal("1"),
            "year": 1950,
            "stories": {"The Beginning - nothing": {}},
            "ext": "cbz",
            "page_count": 0,
        },
        "comicbox.json": {
            "credits": {
                "Joe Orlando": {"roles": {"writer": {}}},
                "Wally Wood": {"roles": {"penciller": {}}},
            },
            "country": "US",
            "day": 1,
            "ext": "cbz",
            "genres": {"Science Fiction": {}},
            "identifiers": {
                "comicvine": {
                    "nss": "145269",
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
            "publisher": {"name": "Youthful Adventure Stories"},
            "series": {"name": "Captain Science"},
            "stories": {"The Beginning": {}},
            "tagger": "comicbox dev",
            "updated_at": datetime(1970, 1, 1, 0, 0),
            "volume": {"issue_count": 7, "number": 1950},
            "year": 1950,
        },
        "comicbox.yaml": {
            "ext": "cbz",
            "identifiers": {
                "comicvine": {
                    "nss": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "imprint": {"name": "TestImprint"},
            "notes": "Tagged with comicbox dev on "
            "1970-01-01T00:00:00 [Issue ID 145269] "
            "[CVDB145269]",
            "page_count": 0,
            "publisher": {"name": "TestPub"},
            "series": {"name": "empty"},
            "story_arcs": {"d": {"number": 1}, "e": {"number": 3}, "f": {"number": 5}},
            "tagger": "comicbox dev",
            "tags": {"a": {}, "b": {}, "c": {}},
            "updated_at": datetime(1970, 1, 1, 0, 0),
        },
        "comicinfo.xml": {
            "age_rating": "Teen",
            "characters": {"Captain Science": {}, "Gordon Dane": {}},
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Inker": {}, "Penciller": {}}},
            },
            "day": 1,
            "ext": "cbz",
            "genres": {"Science Fiction": {}},
            "identifiers": {
                "comicvine": {
                    "nss": "145269",
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
            "publisher": {"name": "Youthful Adventure Stories"},
            "reprints": [
                {"issue": "001", "series": {"name": "Captain Science Alternate"}}
            ],
            "series": {"name": "Captain Science"},
            "stories": {"The Beginning": {}, "The End": {}},
            "story_arcs": {"Captain Arc": {"number": 4}, "Other Arc": {"number": 2}},
            "tagger": "comicbox dev",
            "updated_at": datetime(1970, 1, 1, 0, 0),
            "volume": {"issue_count": 7, "number": 1950},
            "year": 1950,
        },
        "comicinfo-metron-origin.xml": {
            "characters": {"Captain Science": {}, "Gordon Dane": {}},
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Inker": {}, "Penciller": {}}},
            },
            "day": 1,
            "ext": "cbz",
            "genres": {"Science Fiction": {}},
            "identifiers": {
                "comicvine": {
                    "nss": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                },
                "metron": {
                    "nss": "99999",
                    "url": "https://metron.cloud/issue/99999",
                },
            },
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "month": 11,
            "notes": "Tagged with Comictagger on "
            "1970-01-01T00:00:00 using info from Metron [Issue ID 145269] "
            "[CVDB145269]",
            "page_count": 0,
            "publisher": {"name": "Youthful Adventure Stories"},
            "reprints": [
                {"issue": "001", "series": {"name": "Captain Science Alternate"}}
            ],
            "series": {"name": "Captain Science"},
            "stories": {"The Beginning": {}},
            "story_arcs": {"Captain Arc": {"number": 4}, "Other Arc": {"number": 2}},
            "tagger": "Comictagger",
            "updated_at": datetime(1970, 1, 1, 0, 0),
            "volume": {"issue_count": 7, "number": 1950},
            "year": 1950,
        },
        "comictagger.json": {
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Penciller": {}}},
            },
            "country": "US",
            "day": 1,
            "ext": "cbz",
            "genres": {"Science Fiction": {}},
            "identifiers": {
                "comicvine": {
                    "nss": "145269",
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
            "publisher": {"name": "Youthful Adventure Stories"},
            "series": {"name": "Captain Science"},
            "stories": {"The Beginning": {}},
            "tagger": "comicbox dev",
            "updated_at": datetime(1970, 1, 1, 0, 0),
            "volume": {"issue_count": 7, "number": 1950},
            "year": 1950,
        },
        "metroninfo.xml": {
            "age_rating": "Teen Plus",
            "characters": {"Captain Science": {}, "Gordon Dane": {}},
            "collection_title": "Omnibus",
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Inker": {}, "Penciller": {}}},
            },
            "date": date(1950, 11, 1),
            "ext": "cbz",
            "genres": {"Science Fiction": {}},
            "identifier_primary_source": {
                "nid": "metron",
                "url": "https://metron.cloud/",
            },
            "identifiers": {
                "comicvine": {
                    "nss": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                },
                "isbn": {
                    "nss": "123-456789-0123",
                    "url": "https://isbndb.com/book/123-456789-0123",
                },
                "metron": {"nss": "999999", "url": "https://metron.cloud/issue/999999"},
                "upc": {"nss": "12345", "url": "https://barcodelookup.com/12345"},
            },
            "imprint": {
                "identifiers": {
                    "metron": {"nss": "222", "url": "https://metron.cloud/imprint/222"}
                },
                "name": "Youthful Imprint",
            },
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "notes": "Tagged with comicbox dev on 1970-01-01T00:00:00 [Issue ID 145269] urn:comicvine:145269 urn:isbn:123-456789-0123 urn:upc:12345 urn:metron:999999",
            "original_format": "Single Issue",
            "page_count": 0,
            "prices": {
                "GB": Decimal("0.50"),
                "US": Decimal("1.25"),
            },
            "publisher": {
                "identifiers": {
                    "metron": {"nss": "11", "url": "https://metron.cloud/publisher/11"}
                },
                "name": "Youthful Adventure Stories",
            },
            "reprints": [
                {"language": "es", "series": {"name": "Capitán Ciencia"}},
                {"series": {"name": "Captain Science Alternate"}, "issue": "001"},
            ],
            "series": {
                "identifiers": {
                    "metron": {"nss": "2222", "url": "https://metron.cloud/series/2222"}
                },
                "name": "Captain Science",
                "sort_name": "Captain Science",
                "start_year": 1950,
                "volume_count": 1,
            },
            "stories": {
                "Captain Lost": {
                    "identifiers": {
                        "metron": {
                            "nss": "5555",
                            "url": "https://metron.cloud/story/5555",
                        }
                    },
                },
                "Science is Good": {},
            },
            "story_arcs": {"Captain Arc": {"number": 4}, "Other Arc": {"number": 2}},
            "tagger": "comicbox dev",
            "universes": {"Mirror": {"designation": "4242"}},
            "updated_at": datetime(1970, 1, 1, 0, 0),
            "volume": {"issue_count": 10, "name": "NineteenFifty", "number": 1950},
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
