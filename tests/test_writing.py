"""Tests for writing."""

from argparse import Namespace
from decimal import Decimal
from types import MappingProxyType

from comicbox.box import Comicbox
from comicbox.fields.enum_fields import PageTypeEnum
from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox import ComicboxSchemaMixin
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
        ComicboxSchemaMixin.ROOT_TAG: {
            "credits": {
                "Joe Orlando": {"roles": {"Writer": {}}},
                "Wally Wood": {"roles": {"Penciller": {}}},
            },
            "ext": "cbz",
            "genres": {"Science Fiction": {}},
            "issue": {
                "name": "1",
                "number": Decimal("1"),
            },
            "language": "en",
            "date": {
                "month": 11,
                "year": 1950,
            },
            "notes": f"Tagged with comicbox dev on {TEST_DTTM_STR}",
            "page_count": 36,
            "pages": {
                0: {"size": 429985, "page_type": PageTypeEnum.FRONT_COVER},
                1: {"size": 332936},
                2: {"size": 458657},
                3: {"size": 450456},
                4: {"size": 436648},
                5: {"size": 443725},
                6: {"size": 469526},
                7: {"size": 429811},
                8: {"size": 445513},
                9: {"size": 446292},
                10: {"size": 458589},
                11: {"size": 417623},
                12: {"size": 445302},
                13: {"size": 413271},
                14: {"size": 434201},
                15: {"size": 439049},
                16: {"size": 485957},
                17: {"size": 388379},
                18: {"size": 368138},
                19: {"size": 427874},
                20: {"size": 422522},
                21: {"size": 442529},
                22: {"size": 423785},
                23: {"size": 427980},
                24: {"size": 445631},
                25: {"size": 413615},
                26: {"size": 417605},
                27: {"size": 439120},
                28: {"size": 451598},
                29: {"size": 451550},
                30: {"size": 438346},
                31: {"size": 454914},
                32: {"size": 428461},
                33: {"size": 438091},
                34: {"size": 353013},
                35: {"size": 340840},
            },
            "publisher": {"name": "Youthful Adventure Stories"},
            "series": {"name": "Captain Science"},
            "stories": {"The Beginning": {}},
            "volume": {"number": 1950, "issue_count": 7},
            "tagger": "comicbox dev",
            "tags": {"a": {}, "b": {}, "c": {}},
            "title": "The Beginning",
            "updated_at": TEST_DATETIME,
        }
    }
)
TAGS_SOURCE = MappingProxyType(
    {ComicboxSchemaMixin.ROOT_TAG: {"tags": {"a": {}, "b": {}, "c": {}}}}
)


def test_convert_to_cbz_and_cbi_to_cix():
    """Test converting cbr to cbz and writing cbi info as cix."""
    my_setup(TMP_DIR, CBI_CBR_SOURCE_PATH)

    # read and write
    # inject tags.
    with Comicbox(OLD_TEST_CBR_PATH, config=WRITE_CONFIG) as car:
        car.add_metadata(TAGS_SOURCE, MetadataFormats.COMICBOX_JSON)
        car.dump()

    # test
    read_metadata(
        NEW_TEST_CBZ_PATH,
        METADATA,
        READ_CONFIG_EMPTY,
        ignore_updated_at=True,
        ignore_notes=True,
    )

    my_cleanup(TMP_DIR)
