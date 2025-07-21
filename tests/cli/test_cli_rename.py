"""Test CLI extract actions."""

from comicbox import cli
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
            "comicbox",
            "--rename",
            str(TMP_PATH),
        )
    )

    list_dir = sorted(TMP_DIR.iterdir())
    name = list_dir[0].name
    if name != RENAMED_NAME:
        for fn in list_dir:
            print(fn)  # noqa: T201
    assert name == RENAMED_NAME
    _cleanup()
