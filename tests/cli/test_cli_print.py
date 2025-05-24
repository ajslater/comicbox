"""Test CLI metadata parsing."""

import sys
from io import StringIO
from types import MappingProxyType

from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarint import ScalarInt

from comicbox import cli
from comicbox.schemas.comicbox.cli import ComicboxCLISchema
from comicbox.schemas.yaml import YamlRenderModule
from tests.const import CIX_CBI_CBR_SOURCE_PATH, EMPTY_CBZ_SOURCE_PATH, TEST_FILES_DIR
from tests.util import assert_diff, assert_diff_strings

CLI_METADATA_ARGS = (
    "comicbox",
    "-m",
    "Tags: 'a, b, c',Publisher: TestPub,StoryArc: 'd,e,f', StoryArcNumber: '1,3,5'",
    "-m",
    "imprint: TestImprint",
)
CLI_DICT = MappingProxyType(
    {
        ComicboxCLISchema.ROOT_TAG: {
            "arcs": {"d": {"number": 1}, "e": {"number": 3}, "f": {"number": 5}},
            "ext": "cbz",
            "imprint": {"name": "TestImprint"},
            "page_count": 0,
            "publisher": {"name": "TestPub"},
            "series": {"name": "empty"},
            "tags": {"a": {}, "b": {}, "c": {}},
        }
    }
)


def _get_output(args):
    old_stdout = sys.stdout
    output = ""
    try:
        output_buf = StringIO()
        sys.stdout = output_buf

        cli.main(args)

        output = output_buf.getvalue()
    finally:
        sys.stdout = old_stdout
    return output


FILETYPE_OUTPUT = """
════════════════════════════════════════════════════════════════════════════════
tests/files/empty.cbz
CBZ
"""


def test_cli_filetype():
    """Test filetype action."""
    args = ("comicbox", "-P", "t", "-t", "none", str(EMPTY_CBZ_SOURCE_PATH))
    output = "\n" + _get_output(args)
    assert output == FILETYPE_OUTPUT


SOURCE_OUTPUT = """
════════════════════════════════════════════════════════════════════════════════
tests/files/empty.cbz
────────────────────────────────────────────────────────────────────────────────
Source Filename tests/files/empty.cbz as Filename
empty.cbz
"""


def test_cli_source():
    """Test print source action."""
    args = ("comicbox", "-P", "s", "-t", "none", str(EMPTY_CBZ_SOURCE_PATH))
    output = _get_output(args)
    output = "\n" + output
    assert_diff_strings(SOURCE_OUTPUT, output)


LOADED_OUTPUT = """
════════════════════════════════════════════════════════════════════════════════
tests/files/empty.cbz
────────────────────────────────────────────────────────────────────────────────
Loaded Filename tests/files/empty.cbz as Filename
comicfn2dict:
  ext: cbz
  series: empty
"""


def test_cli_loaded():
    """Test print loaded action."""
    args = ("comicbox", "-P", "l", "-t", "none", str(EMPTY_CBZ_SOURCE_PATH))
    output = _get_output(args)
    output = "\n" + output
    assert_diff_strings(LOADED_OUTPUT, output)


def _ruamel_to_dict(yaml_dict):
    """Not a airtight transform but works for these tests."""
    result = {}
    for key in yaml_dict:
        value = yaml_dict[key]
        if isinstance(value, CommentedMap):
            value = _ruamel_to_dict(value)
        elif isinstance(value, list):
            new_value = []
            for e in value:
                new_e = _ruamel_to_dict(e) if isinstance(e, CommentedMap) else e
                new_value.append(new_e)
            value = new_value
        elif isinstance(value, ScalarInt):
            value = int(value)

        result[key] = value
    return result


def test_cli_print():
    """Simple cli metadata print test."""
    args = (*CLI_METADATA_ARGS, "-p", "-t", "none", str(EMPTY_CBZ_SOURCE_PATH))
    cli.main((*CLI_METADATA_ARGS, "-p", "-P", "slncmd"))
    output = _get_output(args)
    output = output.split("\n", 4)[4]  # remove first four lines
    yaml = YamlRenderModule._get_write_yaml()  # noqa: SLF001
    loaded = yaml.load(output)
    output_dict = _ruamel_to_dict(loaded)
    output_dict = MappingProxyType(output_dict)
    assert_diff(CLI_DICT, output_dict)


LIST_OUTPUT = """
════════════════════════════════════════════════════════════════════════════════
tests/files/Captain Science #001-cix-cbi.cbr
┏━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Page ┃ Archive Path                                ┃
┡━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│   0  │ Captain Science 001/CaptainScience#1_01.jpg │
│   1  │ Captain Science 001/CaptainScience#1_02.jpg │
│   2  │ Captain Science 001/CaptainScience#1_03.jpg │
│   3  │ Captain Science 001/CaptainScience#1_04.jpg │
│   4  │ Captain Science 001/CaptainScience#1_05.jpg │
│   5  │ Captain Science 001/CaptainScience#1_06.jpg │
│   6  │ Captain Science 001/CaptainScience#1_07.jpg │
│   7  │ Captain Science 001/CaptainScience#1_08.jpg │
│   8  │ Captain Science 001/CaptainScience#1_09.jpg │
│   9  │ Captain Science 001/CaptainScience#1_10.jpg │
│  10  │ Captain Science 001/CaptainScience#1_11.jpg │
│  11  │ Captain Science 001/CaptainScience#1_12.jpg │
│  12  │ Captain Science 001/CaptainScience#1_13.jpg │
│  13  │ Captain Science 001/CaptainScience#1_14.jpg │
│  14  │ Captain Science 001/CaptainScience#1_15.jpg │
│  15  │ Captain Science 001/CaptainScience#1_16.jpg │
│  16  │ Captain Science 001/CaptainScience#1_17.jpg │
│  17  │ Captain Science 001/CaptainScience#1_18.jpg │
│  18  │ Captain Science 001/CaptainScience#1_19.jpg │
│  19  │ Captain Science 001/CaptainScience#1_20.jpg │
│  20  │ Captain Science 001/CaptainScience#1_21.jpg │
│  21  │ Captain Science 001/CaptainScience#1_22.jpg │
│  22  │ Captain Science 001/CaptainScience#1_23.jpg │
│  23  │ Captain Science 001/CaptainScience#1_24.jpg │
│  24  │ Captain Science 001/CaptainScience#1_25.jpg │
│  25  │ Captain Science 001/CaptainScience#1_26.jpg │
│  26  │ Captain Science 001/CaptainScience#1_27.jpg │
│  27  │ Captain Science 001/CaptainScience#1_28.jpg │
│  28  │ Captain Science 001/CaptainScience#1_29.jpg │
│  29  │ Captain Science 001/CaptainScience#1_30.jpg │
│  30  │ Captain Science 001/CaptainScience#1_31.jpg │
│  31  │ Captain Science 001/CaptainScience#1_32.jpg │
│  32  │ Captain Science 001/CaptainScience#1_33.jpg │
│  33  │ Captain Science 001/CaptainScience#1_34.jpg │
│  34  │ Captain Science 001/CaptainScience#1_35.jpg │
│  35  │ Captain Science 001/CaptainScience#1_36.jpg │
│      │ comicinfo.xml                               │
└──────┴─────────────────────────────────────────────┘
"""


def test_cli_print_contents():
    """Test list contents."""
    args = ("comicbox", "-P", "f", "-t", "none", str(CIX_CBI_CBR_SOURCE_PATH))
    output = _get_output(args)
    output = "\n" + output
    assert_diff_strings(LIST_OUTPUT, output)


LIST_RECURSE_OUPUT_PATH = TEST_FILES_DIR / "list_recurse_output.txt"


def test_cli_print_list_recurse():
    """Test recursion."""
    args = ("comicbox", "--recurse", "-l", str(TEST_FILES_DIR))
    output = _get_output(args)
    check_output = LIST_RECURSE_OUPUT_PATH.read_text()
    assert_diff_strings(check_output, output)
