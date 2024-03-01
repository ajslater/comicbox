"""Test CLI metadata parsing."""

from argparse import Namespace
from io import StringIO
from pathlib import Path
from types import MappingProxyType

from comicbox.fields.enum import PageTypeEnum
from comicbox.schemas.comicbox_mixin import ROOT_TAG
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.schemas.yaml import YamlRenderModule
from comicbox.transforms.comicbox_yaml import ComicboxYamlTransform
from tests.const import (
    TEST_DATETIME,
    TEST_DTTM_STR,
    TEST_METADATA_DIR,
    TEST_READ_NOTES,
)
from tests.util import TestParser, create_write_dict, create_write_metadata, get_tmp_dir

TEST_FILES_PATH = Path("tests/test_files")
FN = "yaml.cbz"
TMP_DIR = get_tmp_dir(__file__)
TEST_EXPORT_PATH = TMP_DIR / ComicboxYamlSchema.FILENAME
YAML_PATH = TEST_METADATA_DIR / ComicboxYamlSchema.FILENAME

READ_CONFIG = Namespace(comicbox=Namespace(read=["yaml"], compute_pages=False))
WRITE_CONFIG = Namespace(
    comicbox=Namespace(write=["yaml"], read=["yaml"], compute_pages=False)
)
READ_METADATA = MappingProxyType(
    {
        ROOT_TAG: {
            "ext": "cbz",
            "identifiers": {
                "comicvine": {
                    "nss": "4000-145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "imprint": "TestImprint",
            "notes": TEST_READ_NOTES,
            "publisher": "TestPub",
            "series": {"name": "empty"},
            "story_arcs": {"d": 1, "e": 3, "f": 5},
            "tags": {"a", "b", "c"},
            "page_count": 36,
            "pages": [
                {"index": 0, "page_type": PageTypeEnum.FRONT_COVER, "size": 429985},
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
            "tagger": "comicbox dev",
            "updated_at": TEST_DATETIME,
        }
    }
)
WRITE_METADATA = create_write_metadata(READ_METADATA)
READ_YAML_DICT = MappingProxyType(
    {
        ComicboxYamlSchema.ROOT_TAGS[0]: {
            "ext": "cbz",
            "identifiers": {
                "comicvine": {
                    "nss": "4000-145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "imprint": "TestImprint",
            "notes": TEST_READ_NOTES,
            "page_count": 36,
            "pages": [
                {
                    "index": 0,
                    "page_type": PageTypeEnum.FRONT_COVER.value,
                    "size": 429985,
                },
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
            "publisher": "TestPub",
            "series": {"name": "empty"},
            "story_arcs": {"d": 1, "e": 3, "f": 5},
            "tagger": "comicbox dev",
            "tags": ["a", "b", "c"],
            "updated_at": TEST_DTTM_STR,
        }
    }
)
WRITE_YAML_DICT = create_write_dict(READ_YAML_DICT, ComicboxYamlSchema, "notes")

yaml = YamlRenderModule.get_write_yaml()
with StringIO() as buf:
    yaml.dump(dict(READ_YAML_DICT), buf)
    READ_YAML_STR = buf.getvalue()
with StringIO() as buf:
    yaml.dump(dict(WRITE_YAML_DICT), buf)
    WRITE_YAML_STR = buf.getvalue()


YAML_TESTER = TestParser(
    ComicboxYamlTransform,
    FN,
    READ_METADATA,
    READ_YAML_DICT,
    READ_YAML_STR,
    READ_CONFIG,
    WRITE_CONFIG,
    WRITE_METADATA,
    WRITE_YAML_DICT,
    WRITE_YAML_STR,
)


def test_yaml_from_metadata():
    """Test assign metadata."""
    YAML_TESTER.test_from_metadata()


def test_yaml_from_dict():
    """Test native dict import from comicbox.schemas."""
    YAML_TESTER.test_from_dict()


def test_yaml_from_string():
    """Test metadata import from string."""
    YAML_TESTER.test_from_string()


def test_yaml_from_file():
    """Test metadata import from file."""
    YAML_TESTER.test_from_file()


def test_yaml_to_dict():
    """Test metadata export to dict."""
    YAML_TESTER.test_to_dict()


def test_yaml_to_string():
    """Test metadata export to string."""
    YAML_TESTER.test_to_string()


def test_yaml_to_file():
    """Test metadata export to file."""
    YAML_TESTER.test_to_file(export_fn="comicbox-write.yaml")


def test_yaml_read():
    """Test read from file."""
    YAML_TESTER.test_md_read(page_count=36)


def test_yaml_write():
    """Test write to file."""
    YAML_TESTER.test_md_write(page_count=36)
