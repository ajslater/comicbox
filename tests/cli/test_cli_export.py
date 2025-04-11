"""Test CLI extract actions."""

from comicbox import cli
from tests.const import (
    EXPORT_SOURCE_PATH,
    TEST_EXPORT_DIR,
)
from tests.util import (
    compare_export,
    get_tmp_dir,
    my_cleanup,
    my_setup,
)

_TMP_DIR = get_tmp_dir(__file__)
_FORMATS = "comet,comicbookinfo,cli,json,yaml,comicinfo,comictagger,pdf,metroninfo"


def _test_cli_action_export_util(path, args):
    """Test cli metadata write to file."""
    my_setup(_TMP_DIR)

    cli.main(
        (
            "comicbox",
            "-d",
            str(_TMP_DIR),
            *args,
            str(path),
        )
    )

    list_dir = sorted(_TMP_DIR.iterdir())
    formats = args[1].split(",")
    if len(list_dir) != len(formats):
        for fn in list_dir:
            print(fn)  # noqa: T201
    assert len(list_dir) == len(formats)
    for fn in list_dir:
        compare_export(TEST_EXPORT_DIR, fn)
    my_cleanup(_TMP_DIR)


def test_cli_action_export():
    """Test cli metadata write to file."""
    _test_cli_action_export_util(EXPORT_SOURCE_PATH, ("-x", _FORMATS))
