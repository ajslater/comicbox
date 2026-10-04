"""The doctor's report rendering: colored status, plain text on request."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from comicbox.doctor.render import render_report
from comicbox.doctor.result import CheckResult, DoctorReport, Status

_GREEN = "\x1b[32m"
_BOLD_RED = "\x1b[1;31m"
_DIM = "\x1b[2m"

_REPORT = DoctorReport(
    header=("comicbox 9.9.9", "Python 3.14.0"),
    results=(
        CheckResult("Archives", "CBZ", Status.OK, "zipremove 0.10.0", "deflate"),
        CheckResult(
            "Archives",
            "CBR",
            Status.MISSING,
            "rarfile 4.5",
            "no RAR tool found",
            fix="brew install rar",
        ),
        CheckResult(
            "Config",
            "user config",
            Status.OK,
            Path("/comics/tagging [digital].yaml"),
            "parsed [ok]",
        ),
        CheckResult("Online", "comicvine", Status.OFF, detail="no credentials"),
        CheckResult("Online", "metron", Status.WARN, detail="user/pass auth"),
    ),
)


def _render(
    report: DoctorReport = _REPORT, *, theme: str | None = None, problems: bool = False
) -> str:
    console = Console(
        file=StringIO(),
        record=True,
        force_terminal=True,
        color_system="truecolor",
        width=120,
        highlight=False,
    )
    render_report(report, theme=theme, problems_only=problems, console=console)
    return console.export_text(styles=True)


def test_status_colors() -> None:
    out = _render()
    assert f"{_GREEN}✓ OK" in out
    assert f"{_BOLD_RED}✗ MISSING" in out
    assert f"{_DIM}→ brew install rar" in out


def test_theme_none_is_plain_text() -> None:
    out = _render(theme="none")
    assert "\x1b[" not in out
    assert "✗ MISSING" in out
    assert "→ brew install rar" in out


def test_brackets_render_verbatim() -> None:
    """Paths and messages carry brackets that markup would swallow."""
    out = _render(theme="none")
    assert "/comics/tagging [digital].yaml" in out
    assert "parsed [ok]" in out


def test_summary_keeps_every_count() -> None:
    out = _render(theme="none")
    assert out.rstrip().endswith("✗ 1 problem · 1 warning · 1 off")


def test_problems_only_shows_failures_and_their_fixes() -> None:
    out = _render(theme="none", problems=True)
    assert "✗ MISSING" in out
    assert "→ brew install rar" in out
    for hidden in ("CBZ", "user config", "metron", "comicvine", "comicbox 9.9.9"):
        assert hidden not in out
    # Sections left empty are dropped.
    assert "Config" not in out
    assert "Online" not in out
    # The summary still counts what -q hid.
    assert out.rstrip().endswith("✗ 1 problem · 1 warning · 1 off")


def test_healthy_problems_only_is_one_line() -> None:
    healthy = DoctorReport(
        header=("comicbox 9.9.9",),
        results=(CheckResult("Archives", "CBZ", Status.OK),),
    )
    assert _render(healthy, theme="none", problems=True).strip() == "✓ 0 problems"
    assert f"{_GREEN}✓ 0 problems" in _render(healthy, problems=True)
