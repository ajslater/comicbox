"""
RAR support is probed by extracting a member, not by finding a binary.

rarfile picks the first tool whose version check passes, and that check
is no evidence the tool can extract anything: rarfile 4.5's bsdtar
command line opens a file named ``--``, and 7-Zip builds without the RAR
codec answer "Unsupported Method". ``is_unrar_supported()`` used to look
for ``unrar`` on PATH instead, and a missing or broken tool surfaced as a
raw ``RarCannotExec`` / ``BadRarFile`` traceback rather than the
``UnsupportedArchiveTypeError`` every caller already handles.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest
import rarfile

from comicbox import _rar
from comicbox._rar import rar_unsupported_reason
from comicbox.box import Comicbox
from comicbox.box.archive.archive import Archive
from comicbox.exceptions import UnsupportedArchiveTypeError
from tests.const import CIX_CBI_CBR_SOURCE_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _fresh_probe() -> Iterator[None]:
    """Run each test against an unprobed, unconfigured rarfile."""
    rar_unsupported_reason.cache_clear()
    saved_setup = rarfile.CURRENT_SETUP
    rarfile.CURRENT_SETUP = None
    yield
    rar_unsupported_reason.cache_clear()
    rarfile.CURRENT_SETUP = saved_setup


def _no_tool(monkeypatch: pytest.MonkeyPatch, *, unrar_on_path: bool) -> None:
    """Make rarfile find no working tool, as on a host with none installed."""

    def tool_setup(*_args: object, **_kwargs: object) -> None:
        reason = "Cannot find working tool"
        raise rarfile.RarCannotExec(reason)

    monkeypatch.setattr(rarfile, "tool_setup", tool_setup)
    which = "/usr/bin/unrar" if unrar_on_path else None
    monkeypatch.setattr(shutil, "which", lambda _name: which)


def test_probe_member_is_compressed() -> None:
    """
    A stored probe would pass with no tool at all.

    rarfile reads stored members itself; only a compressed one makes it
    shell out to the tool under test.
    """
    with rarfile.RarFile(_rar._TOOL_PROBE_PATH) as archive:
        info = archive.getinfo(_rar._TOOL_PROBE_MEMBER)
    assert info.compress_type != rarfile.RAR_M0


def test_supported_with_a_working_tool() -> None:
    """The suite's hosts have unrar, so the probe extracts and passes."""
    assert rar_unsupported_reason() == ""
    assert Comicbox.is_unrar_supported()
    assert Comicbox.check_unrar_executable()


def test_no_tool_is_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_tool(monkeypatch, unrar_on_path=False)
    assert rar_unsupported_reason() == "'unrar' not on path"
    assert not Comicbox.is_unrar_supported()
    with pytest.raises(UnsupportedArchiveTypeError, match="'unrar' not on path"):
        Comicbox.check_unrar_executable()


def test_unrar_that_cannot_extract_is_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Present on PATH is not the same as working."""
    _no_tool(monkeypatch, unrar_on_path=True)
    assert rar_unsupported_reason().startswith("'unrar' cannot extract")
    assert not Comicbox.is_unrar_supported()


@pytest.mark.skipif(not shutil.which("bsdtar"), reason="bsdtar not installed")
def test_bsdtar_fallback_is_unsupported() -> None:
    """
    Bsdtar passes rarfile's tool check but extracts nothing.

    It is on every macOS host, so trusting the check would report every
    Mac as RAR-capable and Codex would import CBRs that all fail to read.
    """
    rarfile.CURRENT_SETUP = rarfile.ToolSetup(rarfile.BSDTAR_CONFIG)
    assert rar_unsupported_reason()


def test_read_without_tool_raises_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RarCannotExec from a member read becomes UnsupportedArchiveTypeError."""
    with Comicbox(CIX_CBI_CBR_SOURCE_PATH) as car:
        _no_tool(monkeypatch, unrar_on_path=False)
        with pytest.raises(UnsupportedArchiveTypeError) as exc_info:
            car.get_page_by_index(0)
    assert isinstance(exc_info.value.__cause__, rarfile.RarCannotExec)


def test_open_without_tool_raises_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Opening is mapped too.

    rarfile decompresses a RAR3 archive comment while constructing the
    RarFile, so the tool can be missing before any member is read.
    """

    def needs_tool(*_args: object, **_kwargs: object) -> None:
        reason = "Cannot find working tool"
        raise rarfile.RarCannotExec(reason)

    with Comicbox(CIX_CBI_CBR_SOURCE_PATH) as car:
        _no_tool(monkeypatch, unrar_on_path=False)
        car._archive = None
        car._archive_cls = needs_tool
        car._namelist = None
        with pytest.raises(UnsupportedArchiveTypeError):
            car.namelist()


def test_corrupt_member_with_working_tool_is_not_masked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BadRarFile on a host whose tool works is a bad archive; say so."""

    def corrupt(*_args: object, **_kwargs: object) -> bytes:
        reason = "Failed the read enough data"
        raise rarfile.BadRarFile(reason)

    monkeypatch.setattr(Archive, "read", corrupt)
    with Comicbox(CIX_CBI_CBR_SOURCE_PATH) as car, pytest.raises(rarfile.BadRarFile):
        car.get_page_by_index(0)
