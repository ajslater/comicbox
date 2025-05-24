"""Test CLI metadata parsing."""

from argparse import Namespace
from io import StringIO
from types import MappingProxyType

from comicbox.fields.enum_fields import PageTypeEnum
from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox import ComicboxSchemaMixin
from comicbox.schemas.comicbox.yaml import ComicboxYamlSchema
from comicbox.schemas.yaml import YamlRenderModule
from tests.const import (
    TEST_DATETIME,
    TEST_DTTM_STR,
    TEST_METADATA_DIR,
    TEST_READ_NOTES,
)
from tests.util import TestParser, create_write_dict, create_write_metadata, get_tmp_dir

FN = "yaml.cbz"
TMP_DIR = get_tmp_dir(__file__)
TEST_EXPORT_PATH = TMP_DIR / MetadataFormats.COMICBOX_CLI_YAML.value.filename
YAML_PATH = TEST_METADATA_DIR / MetadataFormats.COMICBOX_CLI_YAML.value.filename

READ_CONFIG = Namespace(comicbox=Namespace(read=("fn", "yaml")))
WRITE_CONFIG = Namespace(comicbox=Namespace(write=["yaml"], read=("fn", "yaml")))
READ_METADATA = MappingProxyType(
    {
        ComicboxSchemaMixin.ROOT_TAG: {
            "arcs": {"d": {"number": 1}, "e": {"number": 3}, "f": {"number": 5}},
            "identifiers": {
                "comicvine": {
                    "key": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "imprint": {"name": "TestImprint"},
            "notes": TEST_READ_NOTES,
            "publisher": {"name": "TestPub"},
            "series": {"name": "empty"},
            "tags": {"a": {}, "b": {}, "c": {}},
            "page_count": 36,
            "pages": {
                0: {"page_type": PageTypeEnum.FRONT_COVER, "size": 429985},
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
            "tagger": "comicbox dev",
            "updated_at": TEST_DATETIME,
        }
    }
)
WRITE_METADATA = create_write_metadata(READ_METADATA)
READ_YAML_DICT = MappingProxyType(
    {
        ComicboxYamlSchema.ROOT_TAG: {
            "arcs": {"d": {"number": 1}, "e": {"number": 3}, "f": {"number": 5}},
            "identifiers": {
                "comicvine": {
                    "key": "145269",
                    "url": "https://comicvine.gamespot.com/c/4000-145269/",
                }
            },
            "imprint": {"name": "TestImprint"},
            "notes": TEST_READ_NOTES,
            "page_count": 36,
            "pages": {
                0: {
                    "page_type": PageTypeEnum.FRONT_COVER.value,
                    "size": 429985,
                },
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
            "publisher": {"name": "TestPub"},
            "series": {"name": "empty"},
            "tagger": "comicbox dev",
            "tags": {"a": {}, "b": {}, "c": {}},
            "updated_at": TEST_DTTM_STR,
        }
    }
)
WRITE_YAML_DICT = create_write_dict(READ_YAML_DICT, ComicboxYamlSchema, "notes")

yaml = YamlRenderModule._get_write_yaml()  # noqa: SLF001
with StringIO() as buf:
    yaml.dump(dict(READ_YAML_DICT), buf)
    READ_YAML_STR = buf.getvalue()
with StringIO() as buf:
    yaml.dump(dict(WRITE_YAML_DICT), buf)
    WRITE_YAML_STR = buf.getvalue()


YAML_TESTER = TestParser(
    MetadataFormats.COMICBOX_YAML,
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
    YAML_TESTER.test_from_file(page_count=0)


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
    YAML_TESTER.test_md_read(page_count=0)


def test_yaml_write():
    """Test write to file."""
    YAML_TESTER.test_md_write(page_count=0)
