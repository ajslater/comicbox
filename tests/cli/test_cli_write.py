"""Test CLI metadata parsing."""

from argparse import Namespace
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType

from comicbox import cli
from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.formats import MetadataFormats
from comicbox.schemas.comicbox.cli import ComicboxCLISchema
from tests.const import (
    CBZ_MULTI_SOURCE_PATH,
    CIX_CBI_CBR_SOURCE_PATH,
    EMPTY_CBZ_SOURCE_PATH,
    TEST_METADATA_DIR,
)
from tests.util import assert_diff, get_tmp_dir, my_cleanup, my_setup

READ_CONFIG = Namespace(comicbox=Namespace(read=["cli"]))
READ_CONFIG_IGNORE_FN = Namespace(comicbox=Namespace(read_ignore=["fn"], print="sp"))
WRITE_CONFIG = Namespace(comicbox=Namespace(write=["cli"], read=["cli"]))
METADATA = MappingProxyType(
    {
        ComicboxCLISchema.ROOT_TAG: {
            "arcs": {"d": {"number": 1}, "e": {"number": 3}, "f": {"number": 5}},
            "ext": "cbz",
            "imprint": {"name": "TestImprint"},
            "publisher": {"name": "TestPub"},
            "series": {"name": "empty"},
            "tagger": "comicbox dev",
            "tags": {"a": {}, "b": {}, "c": {}},
            "page_count": 0,
        }
    }
)
EMPTY_MD = MappingProxyType({ComicboxCLISchema.ROOT_TAG: {}})
CLI_METADATA_ARGS = (
    "comicbox",
    "-m",
    "tags: {a: {}, b: {},c: {}}, publisher: {name: TestPub}, arcs: {d: {number: 1},e: {number: 3},f: {number: 5}}",
    "-m",
    "imprint: {name: TestImprint}",
)
CLI_DICT = MappingProxyType(
    {
        ComicboxCLISchema.ROOT_TAG: {
            "arcs": {"d": 1, "e": 3, "f": 5},
            "ext": "cbz",
            "imprint": {"name": "TestImprint"},
            "publisher": {"name": "TestPub"},
            "series": "empty",
            "tags": {"a": {}, "b": {}, "c": {}},
            "page_count": 0,
        }
    }
)
MD_ARGS = ("-m", "publisher: 'Galactic Press'")
DELETE_ALL_TAGS_ARGS = ("--delete-all-tags", "-w", "cix")
ADDED_MD = MappingProxyType(
    {
        ComicboxCLISchema.ROOT_TAG: {
            "publisher": {"name": "Galactic Press"},
            "page_count": 0,
        }
    }
)

# PATHS
TMP_DIR = get_tmp_dir(__file__)
TMP_PATH = TMP_DIR / EMPTY_CBZ_SOURCE_PATH.name
TMP_CBR_PATH = TMP_DIR / CIX_CBI_CBR_SOURCE_PATH.name
TMP_CBZ_PATH = TMP_CBR_PATH.with_suffix(".cbz")
TMP_MULTI_PATH = TMP_DIR / CBZ_MULTI_SOURCE_PATH.name

TEST_EXPORT_PATH = TMP_DIR / MetadataFormats.COMICBOX_CLI_YAML.value.filename
CLI_PATH = TEST_METADATA_DIR / MetadataFormats.COMICBOX_CLI_YAML.value.filename
METADATA_REPLACE = MappingProxyType(
    {
        ComicboxCLISchema.ROOT_TAG: {
            **METADATA[ComicboxCLISchema.ROOT_TAG],
            "tags": {"d": {}, "e": {}, "f": {}},
            "title": "bozo_title",
            "stories": {"bozo_title": {}},
        }
    }
)
DELETE_KEYS_MD = MappingProxyType(
    {
        "comicbox": {
            "arcs": {
                "Other Arc": {"number": 2},
                "e": {"number": 1},
                "f": {"number": 3},
                "g": {"number": 5},
                "h": {"number": 7},
                "i": {"number": 11},
                "j": {"number": 13},
            },
            "characters": {"COMET": {}, "Captain Science": {}, "Gordon Dane": {}},
            "date": {
                "cover_date": date(591, 11, 1),
                "month": 11,
                "year": 591,
                "day": 1,
            },
            "genres": {
                "Comic Info Genre": {},
                "Science Fiction": {},
                "comicbox Genre": {},
            },
            "identifiers": {
                "comicvine": {
                    "key": "145269",
                    "url": "https://comicvine.gamespot.com/captain-science-1/4000-145269/",
                }
            },
            "imprint": {"name": "CLIImprint"},
            "issue": {
                "name": "001",
                "number": Decimal("1"),
            },
            "language": "en",
            "notes": (
                "Tagged with comicbox dev on "
                "1970-01-01T00:00:00Z [Issue ID 145269] "
                "[CVDB145269]"
            ),
            "original_format": "Comic",
            "page_count": 0,
            "publisher": {"name": "Galactic Press"},
            "reprints": [{"issue": "001"}],
            "stories": {"The Beginning COMET": {}},
            "summary": "A long example description",
            "tagger": "comicbox dev",
            "tags": {"a": {}, "b": {}, "c": {}},
            "title": "The Beginning COMET",
            "updated_at": datetime(1970, 1, 1, 0, 0),  # noqa: DTZ001
            "volume": {"issue_count": 77, "number": 999},
        }
    }
)


def _setup(source_path=EMPTY_CBZ_SOURCE_PATH):
    """Set up tmp file."""
    my_setup(TMP_DIR, source_path)


def _cleanup():
    """Clean up tmp dir."""
    my_cleanup(TMP_DIR)


def test_cli_action_write():
    """Test cli metadata write to file."""
    _setup()
    with Comicbox(TMP_PATH) as car:
        md = car.get_metadata()
    md = MappingProxyType(md)

    args = (*CLI_METADATA_ARGS, "-w", "cr", str(TMP_PATH), "-P", "sld")
    cli.main(args)

    with Comicbox(TMP_PATH) as car:
        md = car.get_metadata()
    md[ComicboxCLISchema.ROOT_TAG].pop("notes", None)
    md[ComicboxCLISchema.ROOT_TAG].pop("updated_at", None)
    md = MappingProxyType(md)
    assert_diff(METADATA, md)
    _cleanup()


def test_cli_action_write_replace():
    """Test cli metadata write to file."""
    _setup()
    with Comicbox(TMP_PATH) as car:
        md = car.get_metadata()
    md = MappingProxyType(md)

    args = (
        *CLI_METADATA_ARGS,
        "-w",
        "cr",
        "-m",
        "tags: {d: {},e: {},f: {}}",
        "-m",
        "{ title: bozo_title }",
        "-R",
        str(TMP_PATH),
        "-P",
        "nmcp",
    )
    cli.main(args)

    with Comicbox(TMP_PATH) as car:
        md = car.get_metadata()
    md[ComicboxCLISchema.ROOT_TAG].pop("notes", None)
    md[ComicboxCLISchema.ROOT_TAG].pop("updated_at", None)
    md = MappingProxyType(md)
    assert_diff(METADATA_REPLACE, md)
    _cleanup()


def test_cli_action_cbz():
    """Test the cbz and delete-orig options."""
    _setup(CIX_CBI_CBR_SOURCE_PATH)
    with Comicbox(TMP_CBR_PATH) as car:
        old_md = car.get_metadata()
    old_md[ComicboxCLISchema.ROOT_TAG].pop("notes", None)
    old_md[ComicboxCLISchema.ROOT_TAG].pop("updated_at", None)
    old_md = MappingProxyType(old_md)

    _setup(CIX_CBI_CBR_SOURCE_PATH)
    cli.main((ComicboxCLISchema.ROOT_TAG, "--cbz", "--delete-orig", str(TMP_CBR_PATH)))
    assert not TMP_CBR_PATH.exists()

    with Comicbox(TMP_CBZ_PATH) as car:
        new_md = car.get_metadata()
    assert new_md[ComicboxCLISchema.ROOT_TAG]["ext"] == "cbz"
    new_md[ComicboxCLISchema.ROOT_TAG]["ext"] = "cbr"
    new_md[ComicboxCLISchema.ROOT_TAG].pop("notes", None)
    new_md[ComicboxCLISchema.ROOT_TAG].pop("updated_at", None)
    new_md = MappingProxyType(new_md)
    assert_diff(old_md, new_md)
    _cleanup()


def test_cli_action_delete_all_tags():
    """Test delete_tags action."""
    _setup(CBZ_MULTI_SOURCE_PATH)
    config = get_config(READ_CONFIG_IGNORE_FN)
    with Comicbox(TMP_MULTI_PATH, config=config) as car:
        # car.print_out() debug
        old_md = car.get_metadata()
    old_md[ComicboxCLISchema.ROOT_TAG].pop("notes", None)
    old_md = MappingProxyType(old_md)
    assert old_md

    args = (ComicboxCLISchema.ROOT_TAG, str(TMP_MULTI_PATH), *DELETE_ALL_TAGS_ARGS)
    cli.main(args)

    with Comicbox(TMP_MULTI_PATH, config=config) as car:
        new_md = car.get_metadata()
    new_md = MappingProxyType(new_md)
    assert_diff(EMPTY_MD, new_md)
    _cleanup()


def test_cli_action_delete_tags_add_metadata():
    """Test delete_tags action."""
    _setup(CBZ_MULTI_SOURCE_PATH)
    config = get_config(READ_CONFIG_IGNORE_FN)
    with Comicbox(TMP_MULTI_PATH, config=config) as car:
        old_md = car.get_metadata()
    old_md[ComicboxCLISchema.ROOT_TAG].pop("notes", None)
    old_md = MappingProxyType(old_md)
    assert old_md

    cli.main((ComicboxCLISchema.ROOT_TAG, str(TMP_MULTI_PATH), *DELETE_ALL_TAGS_ARGS))
    cli.main(
        (
            ComicboxCLISchema.ROOT_TAG,
            str(TMP_MULTI_PATH),
            *MD_ARGS,
            "-w",
            "cix",
            "-r",
            "cix,cli",
            "-GN",
            "-pP",
            "sncd",
        )
    )

    with Comicbox(TMP_MULTI_PATH, config=READ_CONFIG_IGNORE_FN) as car:
        car.print_out()
        new_md = car.get_metadata()

    new_md = MappingProxyType(new_md)
    assert_diff(ADDED_MD, new_md)
    _cleanup()


def test_cli_action_delete_keys():
    """Test delete_tags action."""
    _setup(CBZ_MULTI_SOURCE_PATH)
    config = get_config(READ_CONFIG_IGNORE_FN)
    with Comicbox(TMP_MULTI_PATH, config=config) as car:
        old_md = car.get_metadata()
    old_md[ComicboxCLISchema.ROOT_TAG].pop("notes", None)
    old_md = MappingProxyType(old_md)
    assert old_md

    cli.main(
        (
            ComicboxCLISchema.ROOT_TAG,
            str(TMP_MULTI_PATH),
            *MD_ARGS,
            "--delete-keys",
            "age_rating,arcs.Captain Arc,credits.Joe Orlando CBI.roles,credits.Wally Wood CBI.roles,pages,series,reprints.0.series",
            "-w",
            "cix",
            "-GN",
            "-pP",
            "mcd",
        )
    )

    with Comicbox(TMP_MULTI_PATH, config=READ_CONFIG_IGNORE_FN) as car:
        new_md = car.get_metadata()

    new_md = MappingProxyType(new_md)
    assert_diff(DELETE_KEYS_MD, new_md)
    _cleanup()
