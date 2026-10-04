"""What a doctor check reports: one row per thing checked."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Status(StrEnum):
    """How one dependency or setting checked out."""

    OK = "OK"
    #: Works, but something about it deserves a look.
    WARN = "WARN"
    #: Optional and not set up.
    OFF = "OFF"
    MISSING = "MISSING"
    WRONG_VERSION = "WRONG VERSION"
    MISCONFIGURED = "MISCONFIGURED"
    #: The check itself couldn't finish: the probe crashed.
    ERROR = "ERROR"

    @property
    def is_failure(self) -> bool:
        """Whether this status means something comicbox needs is broken."""
        return self in _FAILURES


_FAILURES = frozenset(
    {Status.MISSING, Status.WRONG_VERSION, Status.MISCONFIGURED, Status.ERROR}
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    """
    One row of the report.

    ``found`` is what was found: a version, a tool, or a path. A ``Path``
    renders as a path. ``fix`` is a one-line hint for anything not OK.
    None of these ever carry a secret value.
    """

    section: str
    name: str
    status: Status
    found: str | Path = ""
    detail: str = ""
    fix: str = ""


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Every row the checks produced, plus the host they ran on."""

    #: comicbox version, Python, platform: information only.
    header: tuple[str, ...]
    results: tuple[CheckResult, ...]

    @property
    def exit_code(self) -> int:
        """1 if anything comicbox needs is broken, else 0."""
        return int(any(result.status.is_failure for result in self.results))


def short_path(path: str | Path) -> str:
    """Abbreviate the home directory to ``~`` for display."""
    path = Path(path)
    try:
        return str(Path("~") / path.relative_to(Path.home()))
    except (ValueError, RuntimeError):  # not under home, or no home at all
        return str(path)
