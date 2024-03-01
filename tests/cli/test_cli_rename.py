"""Test CLI extract actions."""

from comicbox import cli
from comicbox.schemas.comicbox_mixin import ROOT_TAG
from tests.const import EXPORT_SOURCE_PATH
from tests.util import get_tmp_dir, my_cleanup, my_setup

TMP_DIR = get_tmp_dir(__file__)
TMP_PATH = TMP_DIR / EXPORT_SOURCE_PATH.name

RENAMED_NAME = "Captain Science v1950 #001 (of 007) (1950) The Beginning.cbz"


def _setup():
    """Set up tmp file."""
    my_setup(TMP_DIR, EXPORT_SOURCE_PATH)


def _cleanup():
    """Clean up tmp dir."""
    my_cleanup(TMP_DIR)


def test_cli_action_rename():
    """Test cli metadata write to file."""
    _setup()

    cli.main(
        (
            ROOT_TAG,
            "--rename",
            str(TMP_PATH),
        )
    )

    list_dir = sorted(TMP_DIR.iterdir())
    print("LIST DIR:")
    for fn in list_dir:
        print(fn)
    name = list_dir[0].name
    assert name == RENAMED_NAME
    _cleanup()
