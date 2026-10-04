"""
``comicbox doctor``: report on everything outside comicbox that it depends on.

Each check reports rows: OK, WARN, OFF (optional, not set up), MISSING,
WRONG VERSION, MISCONFIGURED or ERROR, with a one-line fix for anything
that isn't OK. Any failure makes the exit code 1, so ``comicbox doctor
-q`` doubles as a Docker or CI health check.

`run_checks` is the library API: it returns the rows as data and prints
nothing. `main` is ``comicbox doctor``.

Offline and read-only, apart from confuse creating the config directory,
which every run does too.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from dataclasses import replace
from typing import TYPE_CHECKING

from comicbox.doctor.context import DoctorContext
from comicbox.doctor.result import CheckResult, DoctorReport, Status

if TYPE_CHECKING:
    from argparse import ArgumentParser
    from collections.abc import Iterable, Sequence

    from comicbox.doctor.context import Check

__all__ = ("CheckResult", "DoctorReport", "Status", "main", "run_checks")

_REDACTED = "***"
# Below this, a string is too short to scrub safely from free text.
_MIN_SECRET_LEN = 4
_QUIET_CRITICAL = 5


def _checks() -> tuple[Check, ...]:
    """Every check, in report order."""
    from comicbox.doctor import archives, images, online, packages, settings

    return (
        *archives.CHECKS,
        *images.CHECKS,
        *settings.CHECKS,
        *online.CHECKS,
        *packages.CHECKS,
    )


def _run_check(ctx: DoctorContext, check: Check) -> list[CheckResult]:
    """Run one check; a crash becomes one ERROR row and hides nothing else."""
    section, name, run = check
    rows: list[CheckResult] = []
    try:
        for row in run(ctx):
            rows.append(row)  # noqa: PERF402 - keeps the rows yielded before a crash
    except Exception as exc:  # reported as the row
        rows.append(
            CheckResult(
                section, name, Status.ERROR, detail=f"{type(exc).__name__}: {exc}"
            )
        )
    return rows


def _secrets(ctx: DoctorContext) -> tuple[str, ...]:
    """Every resolved password and key, longest first."""
    if ctx.settings is None:
        return ()
    values = {
        value
        for creds in ctx.settings.online.auth.sources.values()
        for value in (creds.password, creds.key)
        if value and len(value) >= _MIN_SECRET_LEN
    }
    return tuple(sorted(values, key=len, reverse=True))


def _redact(
    rows: Iterable[CheckResult], secrets: Sequence[str]
) -> tuple[CheckResult, ...]:
    """
    Scrub any secret from the rows' text.

    The checks never put one there, but an exception message is free
    text. This is the backstop.
    """
    if not secrets:
        return tuple(rows)
    out = []
    for row in rows:
        detail, fix = row.detail, row.fix
        for secret in secrets:
            detail = detail.replace(secret, _REDACTED)
            fix = fix.replace(secret, _REDACTED)
        out.append(replace(row, detail=detail, fix=fix))
    return tuple(out)


def _run(ctx: DoctorContext) -> DoctorReport:
    from comicbox.doctor.packages import host_header

    rows = [row for check in _checks() for row in _run_check(ctx, check)]
    return DoctorReport(header=host_header(), results=_redact(rows, _secrets(ctx)))


def run_checks(args: Namespace | None = None) -> DoctorReport:
    """
    Check comicbox's external dependencies and config.

    ``args`` is what a run would get, ``Namespace(comicbox=...)``, so the
    report describes the config that run would see. None checks the
    environment and config files alone.
    """
    return _run(DoctorContext(args) if args is not None else DoctorContext())


def _build_parser() -> ArgumentParser:
    """Build the normal parser, so every flag means what it does in a run, plus -q."""
    from comicbox.cli.parser import build_parser

    parser = build_parser(prog="comicbox doctor")
    parser.add_argument(
        "-q",
        "--problems",
        action="store_true",
        dest="problems",
        help="Show only the problems, with their fixes, and the summary.",
    )
    return parser


def _hold_logging(cns: Namespace) -> None:
    """
    Keep log lines out of the middle of the report.

    The checks turn what would be warnings into rows. ``-Q`` still means
    what it always does, so five of them silence errors too.
    """
    from comicbox.logger import init_logging

    quiet = getattr(cns, "general.quiet", None) or 0
    init_logging("CRITICAL" if quiet >= _QUIET_CRITICAL else "ERROR")


def main(params: Sequence[str]) -> int:
    """Run ``comicbox doctor`` on the args after ``doctor``; return the exit code."""
    from comicbox.doctor.render import render_report

    cns = _build_parser().parse_args(params)
    # Not a setting: keep it out of the config tree.
    problems_only = vars(cns).pop("problems")
    if cns.paths:
        sys.stderr.write(
            f"comicbox doctor: ignoring {len(cns.paths)} path(s); "
            "the doctor reads no comics.\n"
        )
        cns.paths = []
    _hold_logging(cns)
    ctx = DoctorContext(Namespace(comicbox=cns))
    report = _run(ctx)
    theme = ctx.settings.general.theme if ctx.settings else None
    render_report(report, theme=theme, problems_only=problems_only)
    return report.exit_code
