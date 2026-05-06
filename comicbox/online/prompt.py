"""
Default CLI selector — a `questionary`-based interactive prompt.

Used when no programmatic selector is registered and stdin is a TTY.
Falls back to a plain `input()` loop in non-TTY environments and when
`questionary` import fails.

Layout matches the Phase 4 spec:

  Ambiguous match for <file>
    Existing: series=<...> issue=#<...> year=<...> publisher=<...>

    1. <series> #<issue> (<year>)         score=<X> [<source>:<id>]
       publisher=<...>, pages=<...>, cover_date=<...>
       <url>
    ...

    s. Skip this file
    m. Enter ID manually
    q. Abort entire run

Display rules:
- Top 9 candidates max.
- `cover_score` shown in parens after `score` when hashing was invoked.
- Honors `--terse` / `-Q` quiet by trimming auxiliary lines.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from comicbox.online.profile import Candidate, ComicProfile
    from comicbox.online.selector import SelectorContext, SelectorResult


_MAX_DISPLAYED = 9


def _format_candidate_line(idx: int, c: Candidate) -> str:
    parts = [f"{idx}. {c.summary.series} #{c.summary.issue}"]
    if c.summary.year:
        parts.append(f"({c.summary.year})")
    parts.append(f"  score={c.score:.2f}")
    if c.cover_score is not None:
        parts[-1] += f" (cov={c.cover_score:.2f})"
    parts.append(f"[{c.source}:{c.issue_id}]")
    return " ".join(parts)


def _format_aux_lines(c: Candidate) -> list[str]:
    aux: list[str] = []
    detail_parts: list[str] = []
    if c.summary.publisher:
        detail_parts.append(f"publisher={c.summary.publisher!r}")
    if c.summary.page_count is not None:
        detail_parts.append(f"pages={c.summary.page_count}")
    if c.summary.year is not None:
        detail_parts.append(f"year={c.summary.year}")
    if detail_parts:
        aux.append("   " + ", ".join(detail_parts))
    if c.url:
        aux.append(f"   {c.url}")
    return aux


def _build_lines(
    profile: ComicProfile,
    candidates: Sequence[Candidate],
    file_path: object,
    *,
    terse: bool,
) -> list[str]:
    head = ["", f"Ambiguous match for {file_path}" if file_path else "Ambiguous match"]
    if profile.series or profile.issue or profile.year or profile.publisher:
        head.append(
            f"  Existing: series={profile.series!r} issue=#{profile.issue} "
            f"year={profile.year} publisher={profile.publisher!r}"
        )
    head.append("")
    body: list[str] = []
    for i, c in enumerate(candidates[:_MAX_DISPLAYED], start=1):
        body.append("  " + _format_candidate_line(i, c))
        if not terse:
            body.extend(_format_aux_lines(c))
    body.extend(
        [
            "",
            "  s. Skip this file",
            "  m. Enter ID manually",
            "  q. Abort entire run",
        ]
    )
    return head + body


def _interpret(
    raw: str,
    candidates_count: int,
) -> SelectorResult | None:
    """Parse the user's reply into a SelectorResult, or None if invalid."""
    s = raw.strip().lower()
    if not s:
        return None
    if s in {"s", "skip"}:
        return ("skip", None)
    if s in {"q", "quit", "abort"}:
        return ("abort", None)
    if s in {"m", "manual"}:
        return ("manual", "")  # caller re-prompts for the id
    if s.isdigit():
        idx = int(s)
        if 1 <= idx <= candidates_count:
            return ("choose", idx - 1)
    return None


def _read_input(message: str) -> str:
    """Read one line from stdin; never returns None."""
    try:
        return input(message)
    except EOFError:
        return ""


def _ask_manual_id(default_source: str) -> str | None:
    raw = _read_input(f"Enter <source>:<id> (default source={default_source}): ").strip()
    if not raw:
        return None
    return raw if ":" in raw else f"{default_source}:{raw}"


def _is_tty() -> bool:
    return sys.stdin is not None and sys.stdin.isatty()


def cli_selector(
    profile: ComicProfile,
    candidates: Sequence[Candidate],
    ctx: SelectorContext,
) -> SelectorResult:
    """
    Default CLI prompt selector.

    Uses `questionary.select` when available + TTY; falls back to a
    plain `input()` loop otherwise. Loops on `m` until the user enters
    a valid id or skips/aborts.
    """
    settings = ctx.settings
    terse = bool(getattr(settings, "quiet", 0))

    while True:
        for line in _build_lines(profile, candidates, ctx.file_path, terse=terse):
            print(line)  # noqa: T201
        if _is_tty():
            try:
                import questionary

                raw = questionary.text("Choose:").ask()
            except (ImportError, KeyboardInterrupt):
                return ("abort", None)
            if raw is None:
                return ("abort", None)
        else:
            raw = _read_input("Choose: ")
        result = _interpret(raw, len(candidates[:_MAX_DISPLAYED]))
        if result is None:
            print(f"  unrecognized: {raw!r}")  # noqa: T201
            continue
        if result[0] == "manual" and not result[1]:
            manual = _ask_manual_id(ctx.source)
            if not manual:
                continue
            return ("manual", manual)
        return result
