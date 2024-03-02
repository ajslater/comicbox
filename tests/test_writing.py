"""Tests for writing."""

from argparse import Namespace
from decimal import Decimal
from pprint import pprint
from types import MappingProxyType

from comicbox.box import Comicbox
from comicbox.fields.enum import PageTypeEnum
from comicbox.schemas.comicbox_mixin import ROOT_TAG
from comicbox.transforms.comicbox_json import ComicboxJsonTransform
from tests.const import (
    CBI_CBR_FN,
    CBI_CBR_SOURCE_PATH,
    READ_CONFIG_EMPTY,
    TEST_DATETIME,
    TEST_DTTM_STR,
)

from .util import get_tmp_dir, my_cleanup, my_setup, read_metadata

TMP_DIR = get_tmp_dir(__file__)
OLD_TEST_CBR_PATH = TMP_DIR / CBI_CBR_FN
NEW_TEST_CBZ_PATH = OLD_TEST_CBR_PATH.with_suffix(".cbz")
WRITE_CONFIG = Namespace(comicbox=Namespace(write=["cix"]))
METADATA = MappingProxyType(
    {
        ROOT_TAG: {
            "contributors": {
                "penciller": {"Wally Wood"},
                "writer": {"Joe Orlando"},
            },
            "country": "US",
            "ext": "cbz",
            "genres": {"Science Fiction"},
            "issue": "1",
            "issue_number": Decimal("1"),
            "language": "en",
            "month": 11,
            "notes": f"Tagged with comicbox dev on {TEST_DTTM_STR}",
            "page_count": 36,
            "pages": [
                {"index": 0, "size": 429985, "page_type": PageTypeEnum.FRONT_COVER},
                {"index": 1, "size": 332936},
                {"index": 2, "size": 458657},
                {"index": 3, "size": 450456},
                {"index": 4, "size": 436648},
                {"index": 5, "size": 443725},
                {"index": 6, "size": 469526},
                {"index": 7, "size": 429811},
                {"index": 8, "size": 445513},
                {"index": 9, "size": 446292},
                {"index": 10, "size": 458589},
                {"index": 11, "size": 417623},
                {"index": 12, "size": 445302},
                {"index": 13, "size": 413271},
                {"index": 14, "size": 434201},
                {"index": 15, "size": 439049},
                {"index": 16, "size": 485957},
                {"index": 17, "size": 388379},
                {"index": 18, "size": 368138},
                {"index": 19, "size": 427874},
                {"index": 20, "size": 422522},
                {"index": 21, "size": 442529},
                {"index": 22, "size": 423785},
                {"index": 23, "size": 427980},
                {"index": 24, "size": 445631},
                {"index": 25, "size": 413615},
                {"index": 26, "size": 417605},
                {"index": 27, "size": 439120},
                {"index": 28, "size": 451598},
                {"index": 29, "size": 451550},
                {"index": 30, "size": 438346},
                {"index": 31, "size": 454914},
                {"index": 32, "size": 428461},
                {"index": 33, "size": 438091},
                {"index": 34, "size": 353013},
                {"index": 35, "size": 340840},
            ],
            "publisher": "Youthful Adventure Stories",
            "series": {"name": "Captain Science"},
            "title": "The Beginning",
            "volume": {"name": 1950, "issue_count": 7},
            "year": 1950,
            "tagger": "comicbox dev",
            "tags": {"a", "b", "c"},
            "updated_at": TEST_DATETIME,
        }
    }
)
TAGS_SOURCE = MappingProxyType({ROOT_TAG: {"tags": {"a", "b", "c"}}})


def test_convert_to_cbz_and_cbi_to_cix():
    """Test converting cbr to cbz and writing cbi info as cix."""
    my_setup(TMP_DIR, CBI_CBR_SOURCE_PATH)

    with Comicbox(OLD_TEST_CBR_PATH, config=READ_CONFIG_EMPTY) as car:
        pprint(car.get_metadata())

    # read and write
    # inject tags.
    with Comicbox(OLD_TEST_CBR_PATH, config=WRITE_CONFIG) as car:
        car.add_source(TAGS_SOURCE, ComicboxJsonTransform)
        # car._print_computed(ComicboxJsonSchema(path=OLD_TEST_CBR_PATH))
        car.write()

    # test
    read_metadata(
        NEW_TEST_CBZ_PATH,
        METADATA,
        READ_CONFIG_EMPTY,
        ignore_updated_at=True,
        ignore_notes=True,
    )

    my_cleanup(TMP_DIR)
