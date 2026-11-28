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

import os
import shutil
import subprocess
import sys
from types import ModuleType
from typing import TYPE_CHECKING

from comicbox import _pdf
from comicbox.box import Comicbox
from tests.const import TEST_FILES_DIR

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
    monkeypatch.setattr("comicbox.box.init.pdf_enabled", lambda: False)
    monkeypatch.setitem(sys.modules, "pdffile", ModuleType("pdffile"))
    assert not Comicbox.is_pdf_supported()


# -- Lazy import ------------------------------------------------------------
#
# Importing pdffile loads pymupdf, about half a second, and every comicbox
# process paid it at `import comicbox.box`, PDF or not. The guard above now
# runs at the first question about PDF support instead.

_LOADED_PROBE = (
    "import sys\n"
    "{code}\n"
    "print('LOADED', sorted(m for m in ('pdffile', 'pymupdf') if m in sys.modules))\n"
)
_CBZ = "Captain Science #001-cix.cbz"


def _loaded_after(tmp_path: Path, code: str) -> str:
    """Run code in a fresh interpreter and report which PDF modules it loaded."""
    env = {
        **os.environ,
        "COMICBOXDIR": str(tmp_path / "config"),
        "COMICBOX_ONLINE__CACHE__DIR": str(tmp_path / "cache"),
    }
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _LOADED_PROBE.format(code=code)],
        capture_output=True,
        check=False,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _main(*args: str) -> str:
    return (
        "from comicbox.cli import main\n"
        "try:\n"
        f"    main({['comicbox', *args]!r})\n"
        "except SystemExit as exc:\n"
        "    assert not exc.code, exc.code\n"
    )


def test_importing_the_box_leaves_pdffile_unloaded(tmp_path: Path) -> None:
    out = _loaded_after(tmp_path, "import comicbox.box")
    assert "LOADED []" in out


def test_version_leaves_pdffile_unloaded(tmp_path: Path) -> None:
    out = _loaded_after(tmp_path, _main("-v"))
    assert "LOADED []" in out


def test_reading_a_cbz_leaves_pdffile_unloaded(tmp_path: Path) -> None:
    path = tmp_path / _CBZ
    shutil.copy(TEST_FILES_DIR / _CBZ, path)
    out = _loaded_after(tmp_path, _main("-p", str(path)))
    assert "Captain Science" in out
    assert "LOADED []" in out


def test_asking_about_pdf_support_loads_pdffile(tmp_path: Path) -> None:
    """The contract codex relies on: the answer comes from a real import."""
    code = "import comicbox.box\nprint('SUPPORTED', comicbox.box.Comicbox.is_pdf_supported())"
    out = _loaded_after(tmp_path, code)
    assert "SUPPORTED True" in out
    assert "LOADED ['pdffile', 'pymupdf']" in out


def test_page_format_values_match_pdffile() -> None:
    """The values are written out so the config can name them without pdffile."""
    from pdffile import PageFormat

    assert tuple(e.value for e in PageFormat) == _pdf.PAGE_FORMAT_VALUES


def test_help_without_pdffile_says_so(tmp_path: Path) -> None:
    """The help's note is decided as help renders, not as the parser is built."""
    code = "sys.modules['pdffile'] = None\n" + _main("-h")
    out = _loaded_after(tmp_path, code)
    assert "not installed with PDF support" in out
    assert "--pdf-pages MODE" not in out


def test_help_with_pdffile_offers_pdf_pages(tmp_path: Path) -> None:
    out = _loaded_after(tmp_path, _main("-h"))
    assert "not installed with PDF support" not in out
    assert "--pdf-pages MODE" in out


_RACE = (
    "import sys, threading\n"
    "sys.path.insert(0, {path!r})\n"
    "{setup}\n"
    "from loguru import logger\n"
    "warnings = []\n"
    "logger.remove()\n"
    "logger.add(warnings.append, level='WARNING', format='{{message}}')\n"
    "from comicbox import _pdf\n"
    "barrier = threading.Barrier(16)\n"
    "def ask():\n"
    "    barrier.wait()\n"
    "    _pdf.get_pdffile()\n"
    "threads = [threading.Thread(target=ask) for _ in range(16)]\n"
    "for thread in threads:\n"
    "    thread.start()\n"
    "for thread in threads:\n"
    "    thread.join()\n"
    "print('WARNINGS', sum('PDF support disabled' in w for w in warnings))\n"
)


def test_a_broken_pdffile_warns_once_however_many_threads_ask(tmp_path: Path) -> None:
    """The first question is answered once, not once per thread that asks it."""
    (tmp_path / "pdffile.py").write_text(
        "import time\ntime.sleep(0.05)\nraise AssertionError('libmupdf 1.26 != 1.28')\n"
    )
    code = _RACE.format(path=str(tmp_path), setup="")
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, check=False, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert "WARNINGS 1\n" in proc.stdout, proc.stdout


def test_a_pdffile_module_without_a_spec_does_not_break_the_import(
    tmp_path: Path,
) -> None:
    """A bare module in sys.modules, as test stubs leave, counts as installed."""
    code = (
        "import sys, types\n"
        "sys.modules['pdffile'] = types.ModuleType('pdffile')\n"
        "from comicbox import _pdf\n"
        "print('INSTALLED', _pdf.PDF_INSTALLED, 'ENABLED', _pdf.PDF_ENABLED)\n"
    )
    out = _loaded_after(tmp_path, code)
    assert "INSTALLED True ENABLED False" in out
