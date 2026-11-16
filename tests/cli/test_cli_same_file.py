"""A file a run reaches by several paths is processed once (B8)."""

from __future__ import annotations

import contextlib
import shutil
from typing import TYPE_CHECKING

import pytest

from comicbox import cli, logger
from tests.const import CIX_CBT_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


def _run(*argv: str) -> None:
    with contextlib.suppress(SystemExit):
        cli.main(("comicbox", *argv))


def _listing(directory: Path) -> list[tuple[str, bool]]:
    return sorted((path.name, path.is_symlink()) for path in directory.iterdir())


@pytest.mark.parametrize("jobs", ["1", "2"])
def test_a_link_and_its_file_are_converted_once_through_the_file(
    tmp_path: Path, jobs: str
) -> None:
    """Both were converted, and --delete-orig deleted the link and kept the file."""
    real = tmp_path / "real.cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, real)
    (tmp_path / "link.cbt").symlink_to("real.cbt")

    _run("-j", jobs, "-r", "--cbz", "--delete-orig", str(tmp_path))

    assert _listing(tmp_path) == [("link.cbt", True), ("real.cbz", False)]


def test_two_hard_links_are_converted_once(tmp_path: Path) -> None:
    real = tmp_path / "a.cbt"
    shutil.copy(CIX_CBT_SOURCE_PATH, real)
    (tmp_path / "b.cbt").hardlink_to(real)

    _run("-r", "--cbz", str(tmp_path))

    assert [name for name, _ in _listing(tmp_path)] == ["a.cbt", "a.cbz", "b.cbt"]


def test_a_single_symlink_path_behaves_as_before(tmp_path: Path) -> None:
    """Only the link is in the run, so it is the path processed."""
    shutil.copy(CIX_CBT_SOURCE_PATH, tmp_path / "real.cbt")
    (tmp_path / "link.cbt").symlink_to("real.cbt")

    _run("--cbz", str(tmp_path / "link.cbt"))

    assert (tmp_path / "link.cbz").is_file()
