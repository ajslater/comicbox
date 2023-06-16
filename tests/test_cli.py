"""Test CLI metadata parsing."""
import shutil
import sys
from io import StringIO
from pathlib import Path

from deepdiff.diff import DeepDiff

from comicbox import cli
from comicbox.comic_archive import ComicArchive

CLI_MD = {
    "cover_image": None,
    "ext": "cbz",
    "page_count": 0,
    "series": "empty",
    "tags": frozenset(["a", "b", "c"]),
    "publisher": "TestPub",
    "story_arcs": {"d": 1, "e": 3, "f": 5},
    "imprint": "TestImprint",
}
FN = "empty.cbz"
TEST_PATH = Path("tests/test_files") / FN
TMP_DIR = Path("/tmp/test_cli_metadata")  # noqa: S108
TMP_PATH = TMP_DIR / FN


def test_read_cli_metadata():
    """Simple cli metadata print test."""
    old_stdout = sys.stdout
    output = ""
    try:
        output_buf = StringIO()
        sys.stdout = output_buf

        cli.main(
            (
                "comicbox",
                "-m",
                "Tags=a,b,c;Publisher=TestPub;StoryArc=d:1,e:3,f:5",
                "-m",
                "imprint=TestImprint",
                "-p",
                str(TEST_PATH),
            )
        )

        output = output_buf.getvalue()
    finally:
        sys.stdout = old_stdout

    output = output.strip().replace("\n", "")
    print(f"{output=}")

    output_dict = eval(output)
    diff = DeepDiff(CLI_MD, output_dict, ignore_order=True)
    print(f"{diff=}")

    assert output_dict == CLI_MD


def setup():
    """Set up tmp file."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(TEST_PATH, TMP_PATH)


def cleanup():
    """Clean up tmp dir."""
    shutil.rmtree(TMP_PATH, ignore_errors=True)


def test_write_cli_metadata():
    """Test cli metadata write to file."""
    setup()

    cli.main(
        (
            "comicbox",
            "-m",
            "Tags=a,b,c;Publisher=TestPub;StoryArc=d:1,e:3,f:5",
            "-m",
            "imprint=TestImprint",
            "-w",
            "cr",
            str(TMP_PATH),
        )
    )

    car = ComicArchive(TMP_PATH)
    md = car.get_metadata()

    diff = DeepDiff(CLI_MD, md, ignore_order=True)
    print(f"{diff=}")
    assert md == CLI_MD

    cleanup()
