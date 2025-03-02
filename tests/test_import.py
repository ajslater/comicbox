"""Tests for writing."""

from argparse import Namespace
from datetime import date, datetime
from decimal import Decimal
from pprint import pprint
from types import MappingProxyType

import pytest
from dateutil.tz.tz import tzoffset, tzutc
from deepdiff.diff import DeepDiff

from comicbox.box import Comicbox
from comicbox.fields.enum_fields import ReadingDirectionEnum
from tests.const import (
    EMPTY_CBZ_SOURCE_PATH,
    TEST_METADATA_DIR,
)
from tests.util import compare_export, get_tmp_dir

_TMP_DIR = get_tmp_dir(__file__)


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
        "comic-book-info-example.json": {
            "country": "US",
            "credits": {
                "Gibbons, Dave": {"roles": {"Artist": {}, "Letterer": {}}},
                "Gibbons, John": {"roles": {"Colorer": {}}},
                "Kesel, Barbara": {"roles": {"Editor": {}}},
                "Moore, Alan": {"roles": {"Writer": {}}},
                "Wein, Len": {"roles": {"Editor": {}}},
            },
            "ext": "cbz",
            "genres": {"Superhero": {}},
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "month": 9,
            "page_count": 0,
            "publisher": {"name": "DC Comics"},
            "series": {"name": "Watchmen", "volume_count": 1},
            "stories": {"At Midnight, All the Agents": {}},
            "summary": "Tales of the Black Freighter...",
            "updated_at": datetime(2009, 10, 25, 14, 51, 31, tzinfo=tzutc()),
            "volume": {"issue_count": 12, "number": 1},
            "year": 1986,
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
            "arcs": {"d": {"number": 1}, "e": {"number": 3}, "f": {"number": 5}},
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
            "tagger": "comicbox dev",
            "tags": {"a": {}, "b": {}, "c": {}},
            "updated_at": datetime(1970, 1, 1, 0, 0),
        },
        "comicinfo.xml": {
            "age_rating": "Teen",
            "arcs": {"Captain Arc": {"number": 4}, "Other Arc": {"number": 2}},
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
            "tagger": "comicbox dev",
            "updated_at": datetime(1970, 1, 1, 0, 0),
            "volume": {"issue_count": 7, "number": 1950},
            "year": 1950,
        },
        "comicinfo-metron-origin.xml": {
            "arcs": {"Captain Arc": {"number": 4}, "Other Arc": {"number": 2}},
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
            "identifier_primary_source": {
                "nid": "comicvine",
                "url": "https://comicvine.gamespot.com/",
            },
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
            "arcs": {"Captain Arc": {"number": 4}, "Other Arc": {"number": 2}},
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
            "tagger": "comicbox dev",
            "universes": {"Mirror": {"designation": "4242"}},
            "updated_at": datetime(1970, 1, 1, 0, 0),
            "volume": {"issue_count": 10, "number": 1950, "number_to": 1952},
        },
        # https://github.com/Metron-Project/metroninfo/blob/master/tests/test_files/v1.0/valid.xml
        "metroninfo-v1.0-valid.xml": {
            "age_rating": "Everyone",
            "arcs": {
                "Origin": {
                    "identifiers": {
                        "metron": {
                            "nss": "78945",
                            "url": "https://metron.cloud/arc/78945",
                        }
                    },
                    "number": 1,
                },
                "The New 52!": {},
            },
            "characters": {
                "Aquaman": {
                    "identifiers": {
                        "metron": {
                            "nss": "45678",
                            "url": "https://metron.cloud/character/45678",
                        }
                    }
                },
                "Barry Allen": {},
                "Batman": {},
                "Cyborg": {},
                "Deadman": {},
                "Hal Jordan": {},
                "Hawkman": {},
                "Mera": {},
                "Pandora": {},
                "Ray Palmer": {},
                "Superman": {},
                "Wonder Woman": {},
            },
            "credits": {
                "Alex Sinclair": {"roles": {"Colorist": {}, "Cover": {}}},
                "Dan DiDio": {"roles": {"Publisher": {}}},
                "David Finch": {"roles": {"Cover": {}}},
                "Eddie Berganza": {"roles": {"Editor": {}}},
                "Geoff Johns": {
                    "roles": {
                        "Writer": {
                            "identifiers": {
                                "metron": {
                                    "nss": "32165",
                                    "url": "https://metron.cloud/role/32165",
                                }
                            }
                        }
                    }
                },
                "Jim Lee": {"roles": {"Cover": {}, "Penciller": {}}},
                "Pat Brosseau": {"roles": {"Letterer": {}}},
                "Rex Ogle": {"roles": {"Associate Editor": {}}},
                "Richard Friend": {"roles": {"Cover": {}}},
                "Scott Williams": {"roles": {"Cover": {}, "Inker": {}}},
            },
            "date": date(2011, 10, 1),
            "ext": "cbz",
            "genres": {
                "Crime": {},
                "Foo Bar": {},
                "Super-Hero": {
                    "identifiers": {
                        "metron": {
                            "nss": "98745",
                            "url": "https://metron.cloud/genre/98745",
                        }
                    }
                },
            },
            "identifier_primary_source": {
                "nid": "metron",
                "url": "https://metron.cloud/",
            },
            "identifiers": {
                "comicvine": {
                    "nss": "12345",
                    "url": "https://comicvine.gamespot.com/c/4000-12345/",
                },
                "grandcomicsdatabase": {
                    "nss": "543",
                    "url": "https://comics.org/issue/543/",
                },
                "isbn": {
                    "nss": "1234567890123",
                    "url": "https://isbndb.com/book/1234567890123",
                },
                "metron": {"nss": "290431", "url": "https://metron.cloud/issue/290431"},
                "upc": {
                    "nss": "76194130593600111",
                    "url": "https://barcodelookup.com/76194130593600111",
                },
            },
            "imprint": {
                "identifiers": {
                    "metron": {
                        "nss": "1234",
                        "url": "https://metron.cloud/imprint/1234",
                    }
                },
                "name": "Vertigo",
            },
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "locations": {
                "Gotham City": {
                    "identifiers": {
                        "metron": {
                            "nss": "12389",
                            "url": "https://metron.cloud/location/12389",
                        }
                    }
                },
                "Metropolis": {},
            },
            "notes": "Nothing really to say.",
            "original_format": "Single Issue",
            "page_count": 0,
            "prices": {"GB": Decimal("1.51"), "US": Decimal("3.99")},
            "publisher": {
                "identifiers": {
                    "metron": {
                        "nss": "12345",
                        "url": "https://metron.cloud/publisher/12345",
                    }
                },
                "name": "DC Comics",
            },
            "reprints": [
                {
                    "identifiers": {
                        "metron": {
                            "nss": "65498",
                            "url": "https://metron.cloud/reprint/65498",
                        }
                    },
                    "issue": "002",
                    "series": {"name": "Foo Bar"},
                },
                {"series": {"name": "Foo"}},
                {"language": "de", "series": {"name": "Hüsker Dü"}},
            ],
            "series": {
                "identifiers": {
                    "metron": {
                        "nss": "65478",
                        "url": "https://metron.cloud/series/65478",
                    }
                },
                "name": "Justice League",
                "sort_name": "Justice League",
                "start_year": 1970,
                "volume_count": 3,
            },
            "store_date": date(2011, 8, 31),
            "stories": {
                "Justice League, Part One": {
                    "identifiers": {
                        "metron": {"nss": "12", "url": "https://metron.cloud/story/12"}
                    }
                },
                "Justice League, Part Two": {},
            },
            "summary": "In a universe where superheroes are strange and new, Batman has discovered a dark evil that requires him to unite the World Greatest Heroes!",
            "tags": {
                "Bar": {},
                "Foo": {
                    "identifiers": {
                        "metron": {
                            "nss": "78945",
                            "url": "https://metron.cloud/tag/78945",
                        }
                    }
                },
            },
            "teams": {
                "Justice League": {
                    "identifiers": {
                        "metron": {
                            "nss": "49948",
                            "url": "https://metron.cloud/team/49948",
                        }
                    }
                },
                "Parademons": {},
            },
            "universes": {
                "ABC": {
                    "designation": "Earth 25",
                    "identifiers": {
                        "metron": {
                            "nss": "24",
                            "url": "https://metron.cloud/universe/24",
                        }
                    },
                },
                "Amalgam": {},
            },
            "updated_at": datetime(
                2023, 5, 31, 9, 0, 46, 300882, tzinfo=tzoffset(None, -14400)
            ),
            "volume": {"issue_count": 60, "number": 2},
        },
        "pdf.xml": {
            "credits": {"Jon Osterman": {"roles": {"Writer": {}}}},
            "ext": "cbz",
            "genres": {"Science Fiction": {}},
            "notes": "Tagged with comicbox dev on 1970-01-01T00:00:00",
            "page_count": 0,
            "publisher": {"name": "SmallPub"},
            "scan_info": "Pages",
            "series": {"name": "test pdf"},
            "stories": {"the tangle of their lives": {}},
            "tagger": "comicbox dev",
            "tags": {"d": {}, "e": {}, "f": {}},
            "updated_at": datetime(1970, 1, 1, 0, 0),
        },
    }
)

_FORMAT_MAP = MappingProxyType(
    {
        "comet.xml": "comet",
        "comic-book-info.json": "cbi",
        "comicbox-filename.txt": "fn",
        "comicbox.json": "json",
        "comicbox.yaml": "yaml",
        "comicinfo.xml": "cix",
        "comicinfo-metron-origin.xml": "cix",
        "comictagger.json": "ct",
        "metroninfo.xml": "metron",
        "metroninfo-v1.0-valid.xml": "metron",
    }
)

_REGULAR_FN = MappingProxyType(
    {"cix": "ComicInfo.xml", "metron": "MetronInfo.xml", "fn": "comicbox-filename.txt"}
)


@pytest.mark.parametrize("fn", FNS)
def test_import(fn):
    """Test importing metadata files."""
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


# TODO Activate
@pytest.mark.parametrize("fn", FNS)
def deactivated_test_export(fn):
    """Test exporting metadata files."""
    fmt = _FORMAT_MAP[fn]
    if fmt == "fn":
        # no export file possible
        return
    test_md = MappingProxyType({"comicbox": FNS[fn]})
    formats = (fmt,)
    cns = Namespace(metadata=test_md, dest_path=str(_TMP_DIR), export=formats)
    config = Namespace(comicbox=cns)
    _TMP_DIR.mkdir(exist_ok=True)
    with Comicbox("", config=config) as car:
        car.export_files()

    tmp_fn = _REGULAR_FN.get(fmt, fn)
    tmp_path = _TMP_DIR / tmp_fn
    compare_export(TEST_METADATA_DIR, tmp_path, fmt)
    tmp_path.unlink()
