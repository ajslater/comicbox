"""
Python packages: comicbox's own requirements against what's installed.

The pins come from the installed distribution's metadata, never from a
hardcoded list, so the doctor can't drift from ``pyproject.toml``. uv's
editable dev install ships that metadata too.
"""

from __future__ import annotations

import json
import platform
import sys
from contextlib import suppress
from functools import cache
from importlib.metadata import PackageNotFoundError, distribution, requires, version
from pathlib import Path
from typing import TYPE_CHECKING

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

from comicbox.doctor.result import CheckResult, Status
from comicbox.version import PACKAGE_NAME

if TYPE_CHECKING:
    from collections.abc import Iterator

    from comicbox.doctor.context import Check, DoctorContext

SECTION = "Python packages"
PDF_DIST = "comicbox-pdffile"


def dist_version(name: str) -> str:
    """Return an installed distribution's version, or "" if it's absent."""
    try:
        return version(name)
    except PackageNotFoundError:
        return ""


@cache
def _requirements() -> tuple[Requirement, ...]:
    """Parse comicbox's declared requirements. Raises if the metadata is gone."""
    return tuple(Requirement(raw) for raw in requires(PACKAGE_NAME) or ())


def pinned(name: str) -> str:
    """Return ``name`` with comicbox's pin, e.g. ``py7zr~=1.1.0``, for fix hints."""
    target = canonicalize_name(name)
    try:
        requirements = _requirements()
    except PackageNotFoundError:
        return name
    for req in requirements:
        if canonicalize_name(req.name) == target:
            return f"{req.name}{req.specifier}"
    return name


def reinstall_hint(name: str) -> str:
    """Return the pip command that reinstalls ``name`` at comicbox's pin."""
    return f"pip install --force-reinstall '{pinned(name)}'"


def _check_requirement(req: Requirement) -> CheckResult | None:
    """Return a failure row for one requirement, or None if it's satisfied."""
    installed = dist_version(req.name)
    spec = f"{req.name}{req.specifier}"
    if not installed:
        return CheckResult(
            SECTION,
            req.name,
            Status.MISSING,
            detail=f"comicbox requires {spec}",
            fix=f"pip install '{spec}'",
        )
    if not req.specifier.contains(installed, prereleases=True):
        return CheckResult(
            SECTION,
            req.name,
            Status.WRONG_VERSION,
            found=installed,
            detail=f"comicbox requires {spec}",
            fix=f"pip install '{spec}'",
        )
    return None


def check_requirements(_ctx: DoctorContext) -> Iterator[CheckResult]:
    """
    Check every base requirement's installed version against its pin.

    Extras are left to their feature row (the PDF row checks
    comicbox-pdffile), so one problem never counts twice. A broken
    transitive dependency surfaces in the feature rows as an import error
    naming the module, which says more than a version would.
    """
    try:
        requirements = _requirements()
    except PackageNotFoundError:
        yield CheckResult(
            SECTION,
            PACKAGE_NAME,
            Status.WARN,
            detail="comicbox metadata unavailable: pins not checked",
            fix=f"reinstall comicbox: pip install --force-reinstall {PACKAGE_NAME}",
        )
        return
    env = {"extra": ""}
    satisfied = 0
    for req in requirements:
        if req.marker is not None and not req.marker.evaluate(env):
            continue
        if failure := _check_requirement(req):
            yield failure
        else:
            satisfied += 1
    if satisfied:
        yield CheckResult(
            SECTION,
            "requirements",
            Status.OK,
            detail=f"{satisfied} satisfied",
        )


CHECKS: tuple[Check, ...] = ((SECTION, "requirements", check_requirements),)


def _install_kind() -> str:
    """Say whether comicbox runs from a wheel or an editable source checkout."""
    try:
        direct_url = distribution(PACKAGE_NAME).read_text("direct_url.json")
    except PackageNotFoundError:
        return "not installed"
    # PEP 610: an editable install records itself in direct_url.json.
    with suppress(ValueError, AttributeError):
        if json.loads(direct_url or "{}").get("dir_info", {}).get("editable"):
            return "source checkout"
    return ""


def _python() -> str:
    """Python's version, flagged when it misses comicbox's requires-python."""
    running = platform.python_version()
    try:
        requires_python = distribution(PACKAGE_NAME).metadata["Requires-Python"]
    except (PackageNotFoundError, KeyError):
        requires_python = None
    if requires_python and running not in SpecifierSet(requires_python):
        return f"Python {running} (comicbox requires {requires_python})"
    return f"Python {running}"


def host_header() -> tuple[str, ...]:
    """Describe the host: comicbox, Python and the platform it runs on."""
    comicbox = f"comicbox {dist_version(PACKAGE_NAME) or 'unknown version'}"
    if kind := _install_kind():
        comicbox += f" ({kind})"
    parts = [comicbox, _python(), platform.platform(terse=True)]
    if sys.platform == "linux" and Path("/.dockerenv").exists():
        parts.append("Docker")
    return tuple(parts)
