"""
The optional pdffile extra can be absent or broken without breaking comicbox.

``comicbox._pdf`` caught only ImportError, but pymupdf asserts at import
that its libmupdf is the version it was built against, so a mismatched
install raised AssertionError out of ``import comicbox.box`` and took
CBZ, CBR and everything else down with PDF. ``is_pdf_supported()`` also
answered from ``sys.modules``, which disagrees with ``PDF_ENABLED``
whenever pdffile imported but comicbox's guard rejected it.
"""

from __future__ import annotations

import subprocess
import sys
from types import ModuleType
from typing import TYPE_CHECKING

from comicbox import _pdf
from comicbox.box import Comicbox

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_PROBE = (
    "import sys\n"
    "sys.path.insert(0, {path!r})\n"
    "{setup}\n"
    "import comicbox.box\n"
    "from comicbox._pdf import PDF_ENABLED\n"
    "print('PDF_ENABLED', PDF_ENABLED, comicbox.box.Comicbox.is_pdf_supported())\n"
)


def _import_with(
    tmp_path: Path, setup: str = "", pdffile_src: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Import comicbox.box in a fresh interpreter with a fake pdffile."""
    if pdffile_src is not None:
        (tmp_path / "pdffile.py").write_text(pdffile_src)
    code = _PROBE.format(path=str(tmp_path), setup=setup)
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, check=False, text=True
    )


def test_broken_pdffile_does_not_break_comicbox(tmp_path: Path) -> None:
    """A pymupdf version assert disables PDF and says why."""
    proc = _import_with(
        tmp_path,
        pdffile_src="raise AssertionError('libmupdf 1.26 != 1.28')\n",
    )
    assert proc.returncode == 0, proc.stderr
    assert "PDF_ENABLED False False" in proc.stdout
    assert "PDF support disabled" in proc.stderr
    assert "libmupdf 1.26 != 1.28" in proc.stderr


def test_pdffile_missing_its_own_dependency_warns(tmp_path: Path) -> None:
    """Installed but unimportable is broken, not absent."""
    proc = _import_with(tmp_path, pdffile_src="import no_such_pymupdf\n")
    assert proc.returncode == 0, proc.stderr
    assert "PDF_ENABLED False False" in proc.stdout
    assert "PDF support disabled" in proc.stderr


def test_absent_pdffile_is_quiet(tmp_path: Path) -> None:
    """Not installing the extra is a choice, not a fault."""
    proc = _import_with(tmp_path, setup="sys.modules['pdffile'] = None")
    assert proc.returncode == 0, proc.stderr
    assert "PDF_ENABLED False False" in proc.stdout
    assert "PDF support disabled" not in proc.stderr


def test_is_pdf_supported_follows_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Having pdffile in sys.modules is not support.

    An embedding app (Codex imports pdffile itself) or an old pdffile
    without PageFormat leaves the module loaded while the guard says no.
    """
    assert Comicbox.is_pdf_supported() is _pdf.PDF_ENABLED
    monkeypatch.setattr("comicbox.box.init.PDF_ENABLED", False)
    monkeypatch.setitem(sys.modules, "pdffile", ModuleType("pdffile"))
    assert not Comicbox.is_pdf_supported()
