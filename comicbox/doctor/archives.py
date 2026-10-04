"""
Archives: can this host read and write each comic archive format.

Every probe imports its library inside the function. Reading a CBZ must
never load rarfile or py7zr, and the doctor shares that contract: a
broken import becomes a row here, not a crash at import time.
"""

from __future__ import annotations

import shutil
import sys
import tarfile
import zipfile
from functools import partial
from importlib import import_module
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from comicbox.doctor.packages import PDF_DIST, dist_version, pinned, reinstall_hint
from comicbox.doctor.result import CheckResult, Status

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

    from comicbox.doctor.context import Check, DoctorContext

SECTION = "Archives"

# Codec → the stdlib module that provides it. A Python built without one
# of these libraries can still open archives, just not members compressed
# with that codec.
_ZIP_CODECS = MappingProxyType({"bz2": "bz2", "lzma": "lzma"})
_TAR_CODEC_MODULES = MappingProxyType(
    {"gz": "zlib", "bz2": "bz2", "xz": "lzma", "zst": "compression.zstd"}
)
_ZSTD_MODULES = ("compression.zstd", "backports.zstd")
_BROTLI_MODULES = ("brotli", "brotlicffi")

# rarfile's tool attributes, in the order its tool_setup() tries them.
_RAR_TOOLS = MappingProxyType(
    {
        "UNRAR_TOOL": "UNRAR_CONFIG",
        "UNAR_TOOL": "UNAR_CONFIG",
        "SEVENZIP_TOOL": "SEVENZIP_CONFIG",
        "SEVENZIP2_TOOL": "SEVENZIP2_CONFIG",
        "BSDTAR_TOOL": "BSDTAR_CONFIG",
    }
)
_RAR_CRYPTO = MappingProxyType({1: "cryptography", 2: "pycryptodome"})

_BREW = "brew"
_APT = "apt"
_DNF = "dnf"
_UNRAR_HINTS = MappingProxyType(
    {
        _BREW: "brew install rar",
        _APT: "apt install unrar (Debian: enable non-free)",
        _DNF: "dnf install unrar (from RPM Fusion nonfree)",
    }
)
_UNRAR_HINT_DEFAULT = "install RARLAB unrar on PATH: https://www.rarlab.com"


def _detect_pkg_manager() -> str:
    """Name the system package manager the install hints should use."""
    if sys.platform == "darwin":
        return _BREW
    if sys.platform != "linux":
        return ""
    try:
        os_release = Path("/etc/os-release").read_text().lower()
    except OSError:
        return ""
    if "debian" in os_release or "ubuntu" in os_release:
        return _APT
    if any(name in os_release for name in ("fedora", "rhel", "centos")):
        return _DNF
    return ""


def unrar_hint() -> str:
    """How to install RARLAB unrar here."""
    return _UNRAR_HINTS.get(_detect_pkg_manager(), _UNRAR_HINT_DEFAULT)


def _importable(*modules: str) -> bool:
    """Whether any one of ``modules`` imports."""
    for module in modules:
        try:
            import_module(module)
        except ImportError:
            continue
        return True
    return False


_row = partial(CheckResult, SECTION)


def _missing_codecs_row(name: str, missing: list[str], what: str) -> CheckResult:
    codecs = " ".join(missing)
    return _row(
        name,
        Status.WARN,
        detail=f"no {codecs}: {what} compressed with it can't be read",
        fix=f"use a Python built with {codecs}",
    )


def check_cbz(_ctx: DoctorContext) -> Iterator[CheckResult]:
    """Zip needs zlib to write, and zipremove's remove/repack to rewrite tags."""
    if not _importable("zlib"):
        yield _row(
            "CBZ",
            Status.MISSING,
            detail="no zlib: CBZs can't be written",
            fix="use a Python built with zlib",
        )
        return
    from zipremove import ZipFile

    found = f"zipremove {dist_version('zipremove')}"
    if lacking := [name for name in ("remove", "repack") if not hasattr(ZipFile, name)]:
        yield _row(
            "CBZ",
            Status.WRONG_VERSION,
            found=found,
            detail=f"zipremove lacks {', '.join(lacking)}: tags can't be rewritten",
            fix=f"pip install '{pinned('zipremove')}'",
        )
        return
    codecs = dict(_ZIP_CODECS)
    if hasattr(zipfile, "ZIP_ZSTANDARD"):  # Python 3.14+
        codecs["zstd"] = "compression.zstd"
    missing = [codec for codec, module in codecs.items() if not _importable(module)]
    if missing:
        yield _missing_codecs_row("CBZ", missing, "members")
    present = [codec for codec in codecs if codec not in missing]
    yield _row("CBZ", Status.OK, found=found, detail=" ".join(["deflate", *present]))


def _rar_tools_passing(rarfile: ModuleType) -> list[str]:
    """Every RAR tool on PATH that passes rarfile's own version check."""
    passing = []
    for tool_attr, config_attr in _RAR_TOOLS.items():
        tool: str = getattr(rarfile, tool_attr)
        if (
            shutil.which(tool)
            and rarfile.ToolSetup(getattr(rarfile, config_attr)).check()
        ):
            passing.append(tool)
    return passing


def _rar_effective_tool(rarfile: ModuleType) -> str:
    """Return the tool rarfile picks for extraction, or "" when none works."""
    try:
        setup = rarfile.tool_setup(force=True)
    except rarfile.RarCannotExec:
        return ""
    return getattr(rarfile, setup.setup["open_cmd"][0])


def check_cbr(_ctx: DoctorContext) -> Iterator[CheckResult]:
    """
    Extract a real compressed member with whichever tool rarfile picks.

    Passing rarfile's version check proves little: rarfile 4.5's bsdtar
    backend can't extract anything, and 7-Zip builds without the RAR
    codec say "Unsupported Method". Only the probe answers the question.
    """
    from comicbox._rar import import_rarfile, rar_unsupported_reason

    rarfile = import_rarfile()
    found = f"rarfile {rarfile.__version__}"
    effective = _rar_effective_tool(rarfile)
    passing = _rar_tools_passing(rarfile)
    reason = rar_unsupported_reason()
    if not reason:
        crypto = _RAR_CRYPTO.get(getattr(rarfile, "_have_crypto", 0), "none")
        yield _row(
            "CBR",
            Status.OK,
            found=found,
            detail=f"via {effective} · probe read OK · crypto: {crypto}",
        )
    elif passing:
        yield _row(
            "CBR",
            Status.MISCONFIGURED,
            found=found,
            detail=f"{', '.join(passing)} can't extract RAR: {reason}",
            fix=unrar_hint(),
        )
    else:
        yield _row(
            "CBR",
            Status.MISSING,
            found=found,
            detail=f"no RAR tool found: {reason}",
            fix=unrar_hint(),
        )


def check_cb7(_ctx: DoctorContext) -> Iterator[CheckResult]:
    """py7zr and the optional codecs it reaches for."""
    try:
        import py7zr
    except ImportError as exc:
        yield _row(
            "CB7",
            Status.MISSING,
            detail=f"can't import {exc.name or 'py7zr'}: {exc}",
            fix=reinstall_hint("py7zr"),
        )
        return
    codecs = {"brotli": _BROTLI_MODULES, "zstd": _ZSTD_MODULES}
    missing = [codec for codec, modules in codecs.items() if not _importable(*modules)]
    if missing:
        yield _missing_codecs_row("CB7", missing, "archives")
    present = [codec for codec in codecs if codec not in missing]
    yield _row(
        "CB7",
        Status.OK,
        found=f"py7zr {py7zr.__version__}",
        detail=" ".join([*present, "ppmd bcj"]) + " · BCJ2 unsupported",
    )


def check_cbt(_ctx: DoctorContext) -> Iterator[CheckResult]:
    """Every compressed tar flavor this Python's tarfile can open."""
    codecs = [codec for codec in tarfile.TarFile.OPEN_METH if codec != "tar"]
    missing = [
        codec
        for codec in codecs
        if not _importable(_TAR_CODEC_MODULES.get(codec, codec))
    ]
    if missing:
        yield _missing_codecs_row("CBT", missing, "tarballs")
    present = [codec for codec in codecs if codec not in missing]
    yield _row("CBT", Status.OK, detail=" ".join(present))


def _pdf_import_failure(exc: Exception) -> CheckResult:
    """Build the row for an installed pdffile that won't import."""
    if isinstance(exc, ModuleNotFoundError):
        return _row(
            "PDF",
            Status.MISSING,
            detail=f"can't import {exc.name}: {exc}",
            fix=reinstall_hint(PDF_DIST),
        )
    return _row(
        "PDF",
        Status.MISCONFIGURED,
        detail=f"pdffile fails to import: {exc!r}",
        fix=reinstall_hint(PDF_DIST),
    )


def check_pdf(_ctx: DoctorContext) -> Iterator[CheckResult]:
    """Check the optional PDF extra: absent is fine, installed but broken is not."""
    installed = dist_version(PDF_DIST)
    if not installed:
        yield _row(
            "PDF",
            Status.OFF,
            detail=f"{PDF_DIST} not installed",
            fix="pip install 'comicbox[pdf]'",
        )
        return
    found = f"{PDF_DIST} {installed}"
    from packaging.requirements import Requirement

    req = Requirement(pinned(PDF_DIST))
    if req.specifier and not req.specifier.contains(installed, prereleases=True):
        yield _row(
            "PDF",
            Status.WRONG_VERSION,
            found=found,
            detail=f"comicbox requires {req}",
            fix=f"pip install '{req}'",
        )
        return
    from comicbox._pdf import PDF_ENABLED

    if not PDF_ENABLED:
        # _pdf.py swallowed the error at import time. A failed import isn't
        # cached in sys.modules, so importing again raises it again.
        try:
            import_module("pdffile")
        except Exception as exc:  # _pdf.py catches the same
            yield _pdf_import_failure(exc)
            return
    import pymupdf

    yield _row(
        "PDF",
        Status.OK,
        found=found,
        detail=f"pymupdf {dist_version('pymupdf')} · MuPDF {pymupdf.VersionFitz}",
    )


CHECKS: tuple[Check, ...] = (
    (SECTION, "CBZ", check_cbz),
    (SECTION, "CBR", check_cbr),
    (SECTION, "CB7", check_cb7),
    (SECTION, "CBT", check_cbt),
    (SECTION, "PDF", check_pdf),
)
