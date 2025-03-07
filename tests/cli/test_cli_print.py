"""Test CLI metadata parsing."""

import sys
from io import StringIO
from pprint import pprint
from types import MappingProxyType

from deepdiff.diff import DeepDiff

from comicbox import cli
from comicbox.schemas.comicbox_mixin import ROOT_TAG
from comicbox.schemas.yaml import YamlRenderModule
from tests.const import CIX_CBI_CBR_SOURCE_PATH, EMPTY_CBZ_SOURCE_PATH
from tests.util import diff_strings

CLI_METADATA_ARGS = (
    ROOT_TAG,
    "-m",
    "Tags: 'a, b, c',Publisher: TestPub,story_arcs: {d: 1,e: 3,f: 5}",
    "-m",
    "Imprint: TestImprint",
)
CLI_DICT = MappingProxyType(
    {
        ROOT_TAG: {
            "ext": "cbz",
            "imprint": "TestImprint",
            "page_count": 0,
            "publisher": "TestPub",
            "series": {"name": "empty"},
            "story_arcs": {"d": 1, "e": 3, "f": 5},
            "tags": ["a", "b", "c"],
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

    print(" ".join(args))
    print(output)
    print("---=---")
    return output


FILETYPE_OUTPUT = """
===== tests/test_files/empty.cbz ===============================================
CBZ
"""


def test_cli_filetype():
    """Test filetype action."""
    args = (ROOT_TAG, "-P", "t", str(EMPTY_CBZ_SOURCE_PATH))
    output = "\n" + _get_output(args)
    assert output == FILETYPE_OUTPUT


SOURCE_OUTPUT = """
===== tests/test_files/empty.cbz ===============================================
----- Source Filename tests/test_files/empty.cbz -------------------------------
empty.cbz
"""


def test_cli_source():
    """Test print source action."""
    args = (ROOT_TAG, "-P", "s", str(EMPTY_CBZ_SOURCE_PATH))
    output = _get_output(args)
    output = "\n" + output
    print(SOURCE_OUTPUT)
    diff_strings(SOURCE_OUTPUT, output)
    assert output == SOURCE_OUTPUT


LOADED_OUTPUT = """
===== tests/test_files/empty.cbz ===============================================
----- Loaded Filename tests/test_files/empty.cbz -------------------------------
comicbox:
  ext: cbz
  series: empty
"""


def test_cli_loaded():
    """Test print loaded action."""
    args = (ROOT_TAG, "-P", "l", str(EMPTY_CBZ_SOURCE_PATH))
    output = _get_output(args)
    output = "\n" + output
    print(LOADED_OUTPUT)
    print(output)
    print(len(LOADED_OUTPUT), len(output))
    diff_strings(LOADED_OUTPUT, output)
    assert output == LOADED_OUTPUT


def test_cli_print():
    """Simple cli metadata print test."""
    args = (*CLI_METADATA_ARGS, "-p", str(EMPTY_CBZ_SOURCE_PATH))
    cli.main((*CLI_METADATA_ARGS, "-p", "-P", "slncmd"))
    output = _get_output(args)
    output = output.split("\n", 1)[1]  # remove first line

    yaml = YamlRenderModule.get_write_yaml(dfs=False)
    output_dict = yaml.load(output)
    output_dict[ROOT_TAG] = dict(output_dict[ROOT_TAG])
    output_dict[ROOT_TAG]["story_arcs"] = dict(output_dict[ROOT_TAG]["story_arcs"])
    output_dict = MappingProxyType(output_dict)
    diff = DeepDiff(CLI_DICT, output_dict, ignore_order=True)
    pprint(CLI_DICT)
    pprint(output_dict)
    pprint(diff)

    assert output_dict == CLI_DICT


LIST_OUTPUT = """
===== tests/test_files/Captain Science #001-cix-cbi.cbr ========================
Page	Archive Path
  0	Captain Science 001/CaptainScience#1_01.jpg
  1	Captain Science 001/CaptainScience#1_02.jpg
  2	Captain Science 001/CaptainScience#1_03.jpg
  3	Captain Science 001/CaptainScience#1_04.jpg
  4	Captain Science 001/CaptainScience#1_05.jpg
  5	Captain Science 001/CaptainScience#1_06.jpg
  6	Captain Science 001/CaptainScience#1_07.jpg
  7	Captain Science 001/CaptainScience#1_08.jpg
  8	Captain Science 001/CaptainScience#1_09.jpg
  9	Captain Science 001/CaptainScience#1_10.jpg
 10	Captain Science 001/CaptainScience#1_11.jpg
 11	Captain Science 001/CaptainScience#1_12.jpg
 12	Captain Science 001/CaptainScience#1_13.jpg
 13	Captain Science 001/CaptainScience#1_14.jpg
 14	Captain Science 001/CaptainScience#1_15.jpg
 15	Captain Science 001/CaptainScience#1_16.jpg
 16	Captain Science 001/CaptainScience#1_17.jpg
 17	Captain Science 001/CaptainScience#1_18.jpg
 18	Captain Science 001/CaptainScience#1_19.jpg
 19	Captain Science 001/CaptainScience#1_20.jpg
 20	Captain Science 001/CaptainScience#1_21.jpg
 21	Captain Science 001/CaptainScience#1_22.jpg
 22	Captain Science 001/CaptainScience#1_23.jpg
 23	Captain Science 001/CaptainScience#1_24.jpg
 24	Captain Science 001/CaptainScience#1_25.jpg
 25	Captain Science 001/CaptainScience#1_26.jpg
 26	Captain Science 001/CaptainScience#1_27.jpg
 27	Captain Science 001/CaptainScience#1_28.jpg
 28	Captain Science 001/CaptainScience#1_29.jpg
 29	Captain Science 001/CaptainScience#1_30.jpg
 30	Captain Science 001/CaptainScience#1_31.jpg
 31	Captain Science 001/CaptainScience#1_32.jpg
 32	Captain Science 001/CaptainScience#1_33.jpg
 33	Captain Science 001/CaptainScience#1_34.jpg
 34	Captain Science 001/CaptainScience#1_35.jpg
 35	Captain Science 001/CaptainScience#1_36.jpg
   	comicinfo.xml
"""  # noqa: E101


def test_cli_print_contents():
    """Test list contents."""
    args = (ROOT_TAG, "-P", "f", str(CIX_CBI_CBR_SOURCE_PATH))
    output = _get_output(args)
    output = "\n" + output
    print(LIST_OUTPUT)
    diff_strings(LIST_OUTPUT, output)
    assert output == LIST_OUTPUT
