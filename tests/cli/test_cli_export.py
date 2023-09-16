"""Test CLI extract actions."""
from pprint import pprint

from deepdiff.diff import DeepDiff
from ruamel.yaml import YAML

from comicbox import cli
from comicbox.schemas.comicbox_base import NOTES_KEY, UPDATED_AT_KEY
from tests.const import (
    EXPORT_SOURCE_PATH,
    TEST_EXPORT_DIR,
)
from tests.util import (
    compare_files,
    get_tmp_dir,
    my_cleanup,
    my_setup,
)

TMP_DIR = get_tmp_dir(__file__)


def load_cli_and_compare_dicts(path_a, path_b):
    """Compare cli strings all on one line."""
    yaml = YAML()
    with path_a.open("r") as file_a, path_b.open("r") as file_b:
        dict_a = yaml.load(file_a)
        dict_b = yaml.load(file_b)
    dict_a["comicbox"].pop(UPDATED_AT_KEY, None)
    dict_b["comicbox"].pop(UPDATED_AT_KEY, None)
    dict_a["comicbox"].pop(NOTES_KEY, None)
    dict_b["comicbox"].pop(NOTES_KEY, None)

    pprint(dict_a)
    pprint(dict_b)
    diff = DeepDiff(dict_a, dict_b)
    pprint(diff)
    return diff


def _test_cli_action_export_util(path, args):
    """Test cli metadata write to file."""
    my_setup(TMP_DIR)

    cli.main(
        (
            "comicbox",
            "-d",
            str(TMP_DIR),
            *args,
            str(path),
        )
    )

    list_dir = sorted(TMP_DIR.iterdir())
    print("LIST DIR")
    for fn in list_dir:
        print(fn)
    formats = args[1].split(",")
    assert len(list_dir) == len(formats)
    print("TEST FILES:")
    for fn in list_dir:
        test_path = TEST_EXPORT_DIR / fn.name
        print(fn.name)
        if fn.name == "comicbox-cli.yaml":
            assert not load_cli_and_compare_dicts(test_path, fn)
        else:
            assert compare_files(
                test_path,
                fn,
                ignore_last_modified=True,
                ignore_notes=True,
                ignore_updated_at=True,
            )
    my_cleanup(TMP_DIR)


def test_cli_action_export():
    """Test cli metadata write to file."""
    formats = "comet,cbi,cli,json,yaml,cix,ct,pdf"
    _test_cli_action_export_util(EXPORT_SOURCE_PATH, ("-x", formats))
