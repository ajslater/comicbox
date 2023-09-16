"""Test CLI metadata parsing."""
from argparse import Namespace
from pprint import pprint
from types import MappingProxyType

from deepdiff.diff import DeepDiff

from comicbox import cli
from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.schemas.cli import CLISchema
from tests.const import (
    CBZ_MULTI_SOURCE_PATH,
    CIX_CBI_CBR_SOURCE_PATH,
    EMPTY_CBZ_SOURCE_PATH,
    TEST_METADATA_DIR,
)
from tests.util import get_tmp_dir, my_cleanup, my_setup

READ_CONFIG = Namespace(comicbox=Namespace(read=["cli"]))
READ_CONFIG_IGNORE_FN = Namespace(comicbox=Namespace(read_ignore=["fn"]))
WRITE_CONFIG = Namespace(comicbox=Namespace(write=["cli"], read=["cli"]))
METADATA = MappingProxyType(
    {
        "ext": "cbz",
        "imprint": "TestImprint",
        "publisher": "TestPub",
        "series": "empty",
        "story_arcs": {"d": 1, "e": 3, "f": 5},
        "tagger": "comicbox dev",
        "tags": {"a", "b", "c"},
        "page_count": 0,
    }
)
EMPTY_MD = MappingProxyType({})
CLI_METADATA_ARGS = (
    "comicbox",
    "-m",
    "Tags: 'a, b, c',Publisher: TestPub,story_arcs: {d: 1,e: 3,f: 5}",
    "-m",
    "Imprint: TestImprint",
)
CLI_DICT = MappingProxyType(
    {
        "comicbox": {
            "ext": "cbz",
            "imprint": "TestImprint",
            "publisher": "TestPub",
            "series": "empty",
            "story_arcs": {"d": 1, "e": 3, "f": 5},
            "tags": ["a", "b", "c"],
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

TEST_EXPORT_PATH = TMP_DIR / CLISchema.FILENAME
CLI_PATH = TEST_METADATA_DIR / CLISchema.FILENAME


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
    md = MappingProxyType(md)  # type:ignore
    pprint(md)

    args = (
        *CLI_METADATA_ARGS,
        "-w",
        "cr",
        str(TMP_PATH),
    )
    print(" ".join(args))
    cli.main(args)

    with Comicbox(TMP_PATH) as car:
        md = car.get_metadata()
    md.pop("notes", None)
    md.pop("updated_at", None)
    md = MappingProxyType(md)  # type: ignore
    pprint(METADATA)
    pprint(md)

    diff = DeepDiff(METADATA, md, ignore_order=True)
    pprint(diff)
    assert md == METADATA
    _cleanup()


def test_cli_action_cbz():
    """Test the cbz and delete-orig options."""
    _setup(CIX_CBI_CBR_SOURCE_PATH)
    with Comicbox(TMP_CBR_PATH) as car:
        old_md = car.get_metadata()
    old_md.pop("notes", None)
    old_md.pop("updated_at", None)
    old_md = MappingProxyType(old_md)  # type: ignore
    pprint(old_md)

    _setup(CIX_CBI_CBR_SOURCE_PATH)
    cli.main(("comicbox", "--cbz", "--delete-orig", str(TMP_CBR_PATH)))
    assert not TMP_CBR_PATH.exists()

    with Comicbox(TMP_CBZ_PATH) as car:
        new_md = car.get_metadata()
    assert new_md["ext"] == "cbz"
    new_md["ext"] = "cbr"
    new_md.pop("notes", None)
    new_md.pop("updated_at", None)
    new_md = MappingProxyType(new_md)  # type: ignore
    pprint(new_md)

    diff = DeepDiff(old_md, new_md)
    pprint(diff)

    assert not diff
    _cleanup()


def test_cli_action_delete_tags():
    """Test delete_tags action."""
    _setup(CBZ_MULTI_SOURCE_PATH)
    config = get_config(READ_CONFIG_IGNORE_FN)
    with Comicbox(TMP_MULTI_PATH, config=config) as car:
        old_md = car.get_metadata()
    old_md.pop("notes", None)
    old_md = MappingProxyType(old_md)
    pprint(old_md)
    assert old_md

    cli.main(("comicbox", "--delete-tags", str(TMP_MULTI_PATH)))

    with Comicbox(TMP_MULTI_PATH, config=config) as car:
        new_md = car.get_metadata()
    new_md.pop("notes", None)
    new_md = MappingProxyType(new_md)
    pprint(new_md)
    diff = DeepDiff(EMPTY_MD, new_md)
    print(diff)
    assert not diff
    _cleanup()
