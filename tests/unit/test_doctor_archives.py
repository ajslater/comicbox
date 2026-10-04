"""
The doctor's Archives section.

The RAR states are the ones users hit: a tool that passes rarfile's
version check but can't extract (bsdtar, a codec-less 7zz) has to read
differently from no tool at all.
"""

from __future__ import annotations

import shutil
import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import rarfile

from comicbox import _pdf, _rar
from comicbox.doctor import archives
from comicbox.doctor.context import DoctorContext
from comicbox.doctor.result import Status

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from comicbox.doctor.result import CheckResult


# Held here: the suite's own monkeypatch is undone after this file's fixture.
_PROBE = _rar.rar_unsupported_reason


@pytest.fixture(autouse=True)
def _fresh_rarfile() -> Iterator[None]:
    """Clear the cached probe, and restore the tool the doctor re-picks."""
    _PROBE.cache_clear()
    saved_setup = rarfile.CURRENT_SETUP
    yield
    _PROBE.cache_clear()
    rarfile.CURRENT_SETUP = saved_setup


def _rows(check: Callable[[DoctorContext], Iterator[CheckResult]]) -> list[CheckResult]:
    return list(check(DoctorContext()))


def _one(check: Callable[[DoctorContext], Iterator[CheckResult]]) -> CheckResult:
    rows = _rows(check)
    assert len(rows) == 1, rows
    return rows[0]


def _fail_imports(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Make `import_module` fail for these modules, as a Python built without them."""

    def fake(name: str, package: str | None = None) -> object:
        if name in names:
            raise ModuleNotFoundError(name=name)
        return import_module(name, package)

    monkeypatch.setattr(archives, "import_module", fake)


# -- CBR ------------------------------------------------------------------


def test_cbr_real_probe_reads_the_fixture() -> None:
    """Read the real fixture. Unrar is already a test requirement."""
    row = _one(archives.check_cbr)
    assert row.status is Status.OK
    assert row.found == f"rarfile {rarfile.__version__}"
    assert "via unrar" in row.detail
    assert "probe read OK" in row.detail


def _rar_host(
    monkeypatch: pytest.MonkeyPatch, *, passing: set[str], reason: str
) -> None:
    """Fake which tools pass rarfile's check, and what the probe says."""
    monkeypatch.setattr(shutil, "which", lambda tool: f"/usr/bin/{tool}")

    def check(self: rarfile.ToolSetup) -> bool:
        return rarfile.ToolSetup.get_cmdline(self, "check_cmd", None)[0] in passing

    monkeypatch.setattr(rarfile.ToolSetup, "check", check)
    monkeypatch.setattr(_rar, "rar_unsupported_reason", lambda: reason)


def test_cbr_tool_that_cannot_extract_is_misconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _rar_host(
        monkeypatch,
        passing={"7zz", "bsdtar"},
        reason="'unrar' not on path",
    )
    row = _one(archives.check_cbr)
    assert row.status is Status.MISCONFIGURED
    assert row.detail.startswith("7zz, bsdtar can't extract RAR")
    assert row.fix == archives.unrar_hint()


def test_cbr_no_tool_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _rar_host(monkeypatch, passing=set(), reason="'unrar' not on path")
    row = _one(archives.check_cbr)
    assert row.status is Status.MISSING
    assert row.detail.startswith("no RAR tool found")
    assert row.fix == archives.unrar_hint()


def test_cbr_counts_as_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """The README lists CBR as a core format, so its absence fails the run."""
    _rar_host(monkeypatch, passing=set(), reason="'unrar' not on path")
    assert _one(archives.check_cbr).status.is_failure


@pytest.mark.parametrize(
    ("platform", "os_release", "hint"),
    [
        ("darwin", "", "brew install rar"),
        ("linux", 'ID=debian\nNAME="Debian"', "apt install unrar"),
        ("linux", "ID=fedora", "dnf install unrar"),
        ("win32", "", "install RARLAB unrar"),
    ],
)
def test_unrar_hint_per_package_manager(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    os_release: str,
    hint: str,
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(Path, "read_text", lambda _self, *_args, **_kwargs: os_release)
    assert archives.unrar_hint().startswith(hint)


# -- CBZ, CB7, CBT --------------------------------------------------------


def test_cbz_ok() -> None:
    row = _one(archives.check_cbz)
    assert row.status is Status.OK
    assert str(row.found).startswith("zipremove ")
    assert row.detail.startswith("deflate bz2 lzma")


def test_cbz_missing_codec_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    _fail_imports(monkeypatch, "bz2")
    rows = _rows(archives.check_cbz)
    assert [row.status for row in rows] == [Status.WARN, Status.OK]
    assert rows[0].detail.startswith("no bz2:")
    assert "bz2" not in rows[1].detail


def test_cbz_without_zlib_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _fail_imports(monkeypatch, "zlib")
    assert _one(archives.check_cbz).status is Status.MISSING


def test_cbz_old_zipremove_is_wrong_version(monkeypatch: pytest.MonkeyPatch) -> None:
    import zipremove

    class OldZipFile:
        pass

    monkeypatch.setattr(zipremove, "ZipFile", OldZipFile)
    row = _one(archives.check_cbz)
    assert row.status is Status.WRONG_VERSION
    assert "remove, repack" in row.detail


def test_cb7_ok() -> None:
    row = _one(archives.check_cb7)
    assert row.status is Status.OK
    assert "BCJ2 unsupported" in row.detail


def test_cb7_import_error_names_the_missing_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken transitive dependency is named, not just py7zr."""
    for name in [name for name in sys.modules if name.split(".")[0] == "py7zr"]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "pyppmd", None)
    row = _one(archives.check_cb7)
    assert row.status is Status.MISSING
    assert row.detail.startswith("can't import pyppmd")
    assert row.fix.startswith("pip install --force-reinstall 'py7zr")


def test_cb7_without_brotli_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    _fail_imports(monkeypatch, "brotli", "brotlicffi")
    rows = _rows(archives.check_cb7)
    assert [row.status for row in rows] == [Status.WARN, Status.OK]
    assert rows[0].detail.startswith("no brotli:")


def test_cbt_lists_the_tarfile_codecs() -> None:
    row = _one(archives.check_cbt)
    assert row.status is Status.OK
    assert row.detail.split()[:3] == ["gz", "bz2", "xz"]


def test_cbt_missing_codec_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    _fail_imports(monkeypatch, "lzma")
    rows = _rows(archives.check_cbt)
    assert [row.status for row in rows] == [Status.WARN, Status.OK]
    assert rows[0].detail.startswith("no xz:")


# -- PDF ------------------------------------------------------------------


def test_pdf_absent_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archives, "dist_version", lambda _name: "")
    row = _one(archives.check_pdf)
    assert row.status is Status.OFF
    assert not row.status.is_failure
    assert row.fix == "pip install 'comicbox[pdf]'"


def test_pdf_installed_is_ok() -> None:
    row = _one(archives.check_pdf)
    assert row.status is Status.OK
    assert str(row.found).startswith("comicbox-pdffile ")
    assert "MuPDF" in row.detail


def test_pdf_wrong_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archives, "dist_version", lambda _name: "0.9.0")
    row = _one(archives.check_pdf)
    assert row.status is Status.WRONG_VERSION
    assert row.detail.startswith("comicbox requires comicbox-pdffile")


def test_pdf_broken_install_carries_the_real_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    _pdf.py swallowed it at import time; the doctor re-raises it for the row.

    pymupdf asserts at import that its libmupdf is the one it was built
    against, which is not an ImportError.
    """
    monkeypatch.setattr(_pdf, "PDF_ENABLED", False)

    def fake(name: str, package: str | None = None) -> object:
        if name == "pdffile":
            reason = "libmupdf 1.26 != 1.28 [mismatch]"
            raise RuntimeError(reason)
        return import_module(name, package)

    monkeypatch.setattr(archives, "import_module", fake)
    row = _one(archives.check_pdf)
    assert row.status is Status.MISCONFIGURED
    assert "libmupdf 1.26 != 1.28 [mismatch]" in row.detail
    assert row.fix.startswith("pip install --force-reinstall 'comicbox-pdffile")


def test_pdf_missing_dependency_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_pdf, "PDF_ENABLED", False)
    _fail_imports(monkeypatch, "pdffile")
    row = _one(archives.check_pdf)
    assert row.status is Status.MISSING
    assert row.detail.startswith("can't import pdffile")
