"""Test CLI metadata parsing."""

from argparse import Namespace
from types import MappingProxyType

from comicbox.config import get_config
from comicbox.enums.comicinfo import ComicInfoPageTypeEnum
from comicbox.formats import MetadataFormats
from comicbox.formats.base.schemas.yaml import YamlRenderModule
from comicbox.formats.comicbox.schema import ComicboxSchemaMixin
from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema
from tests.const import (
    TEST_DATETIME,
    TEST_METADATA_DIR,
    TEST_READ_NOTES,
)
from tests.util import TestParser, create_write_dict, create_write_metadata, get_tmp_dir

FN = "yaml.cbz"
TMP_DIR = get_tmp_dir(__file__)
TEST_EXPORT_PATH = TMP_DIR / MetadataFormats.COMICBOX_CLI_YAML.value.filename
YAML_PATH = TEST_METADATA_DIR / MetadataFormats.COMICBOX_CLI_YAML.value.filename
YAML_NOTES = TEST_READ_NOTES + " urn:comicvine:issue:145269"

READ_CONFIG = get_config(
    Namespace(comicbox=Namespace(read=Namespace(formats=("yaml",))))
)
WRITE_CONFIG = get_config(
    Namespace(
        comicbox=Namespace(
            read=Namespace(formats=("yaml",)), write=Namespace(formats=["yaml"])
        )
    )
)
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
            "notes": YAML_NOTES,
            "publisher": {"name": "TestPub"},
            "series": {"name": "empty"},
            "tags": {"a": {}, "b": {}, "c": {}},
            "page_count": 5,
            "pages": {
                0: {"page_type": ComicInfoPageTypeEnum.FRONT_COVER, "size": 4542},
                1: {"size": 4065},
                2: {"size": 4081},
                3: {"size": 4157},
                4: {"size": 4108},
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
            "notes": YAML_NOTES,
            "page_count": 5,
            "pages": {
                0: {
                    "page_type": ComicInfoPageTypeEnum.FRONT_COVER.value,
                    "size": 4542,
                },
                1: {"size": 4065},
                2: {"size": 4081},
                3: {"size": 4157},
                4: {"size": 4108},
            },
            "publisher": {"name": "TestPub"},
            "series": {"name": "empty"},
            "tagger": "comicbox dev",
            "tags": {"a": {}, "b": {}, "c": {}},
            "updated_at": TEST_DATETIME,
        }
    }
)
WRITE_YAML_DICT = create_write_dict(READ_YAML_DICT, ComicboxYamlSchema, "notes")

WRITE_YAML_STR = YamlRenderModule.dumps(WRITE_YAML_DICT)
READ_YAML_STR = YamlRenderModule.dumps(READ_YAML_DICT)

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


def test_yaml_from_metadata() -> None:
    """Test assign metadata."""
    YAML_TESTER.test_from_metadata()


def test_yaml_from_dict() -> None:
    """Test native dict import from comicbox.formats.base.schemas."""
    YAML_TESTER.test_from_dict()


def test_yaml_from_string() -> None:
    """Test metadata import from string."""
    YAML_TESTER.test_from_string()


def test_yaml_from_file() -> None:
    """Test metadata import from file."""
    YAML_TESTER.test_from_file(page_count=0)


def test_yaml_to_dict() -> None:
    """Test metadata export to dict."""
    YAML_TESTER.test_to_dict()


def test_yaml_to_string() -> None:
    """Test metadata export to string."""
    YAML_TESTER.test_to_string()


def test_yaml_to_file() -> None:
    """Test metadata export to file."""
    YAML_TESTER.test_to_file(export_fn="comicbox-write.yaml")


def test_yaml_read() -> None:
    """Test read from file."""
    YAML_TESTER.test_md_read(page_count=0)


def test_yaml_write() -> None:
    """Test write to file."""
    YAML_TESTER.test_md_write(page_count=0)
