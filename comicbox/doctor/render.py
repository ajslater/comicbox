"""
Print a `DoctorReport` in color.

Status colors are fixed, so red and green mean the same thing in every
theme. Section headers and paths come from comicbox's own print theme
(``general.theme``), so the report matches ``comicbox -p``; a theme of
``none`` prints plain text.

Every cell is a `Text` with a `Style`, never markup: paths and error
messages carry brackets (``[digital]``) that markup would swallow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.rule import Rule
from rich.style import Style
from rich.table import Table
from rich.text import Text

from comicbox.box.print import ComicboxStyle, resolve_style_name
from comicbox.doctor.result import Status, short_path

if TYPE_CHECKING:
    from collections.abc import Sequence

    from comicbox.doctor.result import CheckResult, DoctorReport

_GLYPHS = {
    Status.OK: "✓",
    Status.WARN: "!",
    Status.OFF: "\N{EN DASH}",
}
_FAILURE_GLYPH = "✗"
# Wider found cells fold rather than crowd out the notes.
_MAX_FOUND_WIDTH = 32
_FOUND_SHARE = 3  # of the console width, at most
_RED = Style(color="red", bold=True)


@dataclass(frozen=True, slots=True)
class _Palette:
    """Every style the report uses. All empty for plain text."""

    status: dict[Status, Style] = field(default_factory=dict)
    section: Style = field(default_factory=Style)
    name: Style = field(default_factory=Style)
    version: Style = field(default_factory=Style)
    path: Style = field(default_factory=Style)
    error: Style = field(default_factory=Style)
    hint: Style = field(default_factory=Style)
    header: Style = field(default_factory=Style)
    host: Style = field(default_factory=Style)
    green: Style = field(default_factory=Style)
    yellow: Style = field(default_factory=Style)
    cyan: Style = field(default_factory=Style)
    red: Style = field(default_factory=Style)


def _palette(theme: str | None) -> _Palette:
    style_name = resolve_style_name(theme)
    if not style_name:
        return _Palette()
    comicbox = ComicboxStyle(style_name)
    return _Palette(
        status={
            Status.OK: Style(color="green"),
            Status.WARN: Style(color="yellow"),
            Status.OFF: Style(color="cyan"),
            Status.MISSING: _RED,
            Status.WRONG_VERSION: _RED,
            Status.MISCONFIGURED: _RED,
            Status.ERROR: Style(color="white", bgcolor="red", bold=True),
        },
        section=comicbox.section_header,
        name=Style(color="cyan", bold=True),
        version=Style(bold=True),
        path=comicbox.path,
        error=Style(color="red"),
        hint=Style(dim=True),
        header=comicbox.section_header + Style(bold=True),
        host=Style(dim=True),
        green=Style(color="green"),
        yellow=Style(color="yellow"),
        cyan=Style(color="cyan"),
        red=_RED,
    )


def _found_text(found: str | Path) -> str:
    return short_path(found) if isinstance(found, Path) else found


def _status_label(status: Status) -> str:
    return f"{_GLYPHS.get(status, _FAILURE_GLYPH)} {status}"


def _widths(rows: Sequence[CheckResult], console: Console) -> tuple[int, int, int]:
    """Column widths shared by every section, so the sections line up."""
    found = max((len(_found_text(row.found)) for row in rows), default=1)
    found_cap = min(_MAX_FOUND_WIDTH, console.width // _FOUND_SHARE)
    return (
        max((len(_status_label(row.status)) for row in rows), default=1),
        max((len(row.name) for row in rows), default=1),
        max(1, min(found, found_cap)),
    )


def _section(
    console: Console,
    title: str,
    rows: Sequence[CheckResult],
    palette: _Palette,
    widths: tuple[int, int, int],
) -> None:
    console.print()
    console.print(
        Rule(Text(title, style=palette.section), align="left", style=palette.section)
    )
    status_width, name_width, found_width = widths
    table = Table(box=None, show_header=False, padding=(0, 1), pad_edge=False)
    table.add_column(width=status_width, no_wrap=True)
    table.add_column(width=name_width, no_wrap=True)
    table.add_column(width=found_width, overflow="fold")
    table.add_column(overflow="fold")
    for row in rows:
        found_style = palette.path if isinstance(row.found, Path) else palette.version
        notes_style = palette.error if row.status is Status.ERROR else Style()
        table.add_row(
            Text(
                _status_label(row.status), style=palette.status.get(row.status, Style())
            ),
            Text(row.name, style=palette.name),
            Text(_found_text(row.found), style=found_style),
            Text(row.detail, style=notes_style),
        )
        if row.fix and row.status is not Status.OK:
            table.add_row("", "", "", Text(f"→ {row.fix}", style=palette.hint))
    console.print(table)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _summary(report: DoctorReport, palette: _Palette) -> Text:
    """``✓ 0 problems · 1 warning · 2 off``, with the counts -q hides kept."""
    statuses = [row.status for row in report.results]
    problems = sum(status.is_failure for status in statuses)
    warnings = statuses.count(Status.WARN)
    off = statuses.count(Status.OFF)
    summary = Text()
    if problems:
        summary.append(f"{_FAILURE_GLYPH} {_plural(problems, 'problem')}", palette.red)
    else:
        summary.append(f"{_GLYPHS[Status.OK]} 0 problems", palette.green)
    if warnings:
        summary.append(" · ")
        summary.append(_plural(warnings, "warning"), palette.yellow)
    if off:
        summary.append(" · ")
        summary.append(f"{off} off", palette.cyan)
    return summary


def render_report(
    report: DoctorReport,
    *,
    theme: str | None = None,
    problems_only: bool = False,
    console: Console | None = None,
) -> None:
    """
    Print the report: a header, one table per section, and a summary.

    ``problems_only`` (``-q``) keeps just the failures and their fixes,
    drops the sections left empty and the header, and keeps the summary,
    so a healthy run prints one line.
    """
    palette = _palette(theme)
    if console is None:
        # No auto-highlighting: it would recolor numbers and paths.
        console = Console(highlight=False)
    rows = [row for row in report.results if row.status.is_failure or not problems_only]
    widths = _widths(rows, console)
    if not problems_only:
        header = Text("comicbox doctor", style=palette.header)
        header.append("   " + " · ".join(report.header), style=palette.host)
        console.print(header)
    for title, section_rows in groupby(rows, key=lambda row: row.section):
        _section(console, title, list(section_rows), palette, widths)
    if rows or not problems_only:
        console.print()
    console.print(_summary(report, palette))
