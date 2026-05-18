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
    o. Session options ...
    q. Abort entire run

Display rules:
- Top 9 candidates max.
- `cover_score` shown in parens after `score` when hashing was invoked.
- Honors `--terse` / `-Q` quiet by trimming auxiliary lines.

Session options (nested under `o`) let the user switch the rest of
this run to unattended mode or change the match policy
(always-prompt / strict / normal / eager). These exist as flat
SelectorResult actions in the API but are tucked behind a submenu
in the CLI so the primary prompt stays uncluttered.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from comicbox.formats.base.online.profile import Candidate, ComicProfile
    from comicbox.formats.base.online.selector import SelectorContext, SelectorResult


_MAX_DISPLAYED = 9

_POLICY_CHOICES: tuple[tuple[str, str], ...] = (
    ("1", "always-prompt"),
    ("2", "strict"),
    ("3", "normal"),
    ("4", "eager"),
)


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
            "  o. Session options ...",
            "  q. Abort entire run",
        ]
    )
    return head + body


_OPTIONS_SENTINEL = "__options__"

_TOP_LEVEL_REPLIES: dict[str, SelectorResult | str] = {
    "s": ("skip", None),
    "skip": ("skip", None),
    "q": ("abort", None),
    "quit": ("abort", None),
    "abort": ("abort", None),
    "m": ("manual", ""),  # caller re-prompts for the id
    "manual": ("manual", ""),
    "o": _OPTIONS_SENTINEL,
    "options": _OPTIONS_SENTINEL,
}


def _interpret(
    raw: str,
    candidates_count: int,
) -> SelectorResult | str | None:
    """
    Parse the user's reply.

    Returns a `SelectorResult` for terminal actions, the
    `_OPTIONS_SENTINEL` string when the user wants the session-options
    submenu, or `None` for an unrecognized input.
    """
    s = raw.strip().lower()
    if not s:
        return None
    if (action := _TOP_LEVEL_REPLIES.get(s)) is not None:
        return action
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
    raw = _read_input(
        f"Enter <source>:<id> (default source={default_source}): "
    ).strip()
    if not raw:
        return None
    return raw if ":" in raw else f"{default_source}:{raw}"


def _is_tty() -> bool:
    return sys.stdin is not None and sys.stdin.isatty()


def _build_options_lines() -> list[str]:
    return [
        "",
        "  Session options (apply to all remaining files in this run):",
        "    u. Unattended — skip any remaining prompts",
        "    p. Change match policy ...",
        "    b. Back",
    ]


def _build_policy_lines() -> list[str]:
    lines = ["", "  Match policy:"]
    lines.extend(f"    {key}. {name}" for key, name in _POLICY_CHOICES)
    lines.append("    b. Back")
    return lines


def _prompt_line(message: str) -> str | None:
    """Prompt the user once; return None if the user aborts."""
    if _is_tty():
        try:
            import questionary

            return questionary.text(message).ask()
        except (ImportError, KeyboardInterrupt):
            return None
    return _read_input(message + " ")


def _ask_policy_choice() -> SelectorResult | None:
    """Show the policy submenu. Return a SelectorResult or None for back."""
    policy_keys = {key for key, _ in _POLICY_CHOICES}
    policy_names = {name for _, name in _POLICY_CHOICES}
    while True:
        for line in _build_policy_lines():
            print(line)  # noqa: T201
        raw = _prompt_line("Policy:")
        if raw is None:
            return ("abort", None)
        s = raw.strip().lower()
        if s in {"b", "back", ""}:
            return None
        if s in policy_keys:
            for key, name in _POLICY_CHOICES:
                if key == s:
                    return ("set_policy", name)
        if s in policy_names:
            return ("set_policy", s)
        print(f"  unrecognized: {raw!r}")  # noqa: T201


def _ask_session_options() -> SelectorResult | None:
    """Show the session-options submenu. Return a SelectorResult or None for back."""
    while True:
        for line in _build_options_lines():
            print(line)  # noqa: T201
        raw = _prompt_line("Option:")
        if raw is None:
            return ("abort", None)
        s = raw.strip().lower()
        if s in {"b", "back", ""}:
            return None
        if s in {"u", "unattended"}:
            return ("set_unattended", None)
        if s in {"p", "policy"}:
            sub = _ask_policy_choice()
            if sub is not None:
                return sub
            continue
        print(f"  unrecognized: {raw!r}")  # noqa: T201


def cli_selector(
    profile: ComicProfile,
    candidates: Sequence[Candidate],
    ctx: SelectorContext,
) -> SelectorResult:
    """
    Default CLI prompt selector.

    Uses `questionary.select` when available + TTY; falls back to a
    plain `input()` loop otherwise. Loops on `m` and `o` (session
    options submenu) until the user enters a valid id, skips, or
    aborts.
    """
    settings = ctx.settings
    terse = bool(getattr(settings, "quiet", 0))

    while True:
        for line in _build_lines(profile, candidates, ctx.file_path, terse=terse):
            print(line)  # noqa: T201
        raw = _prompt_line("Choose:")
        if raw is None:
            return ("abort", None)
        result = _interpret(raw, len(candidates[:_MAX_DISPLAYED]))
        if result is None:
            print(f"  unrecognized: {raw!r}")  # noqa: T201
            continue
        if result == _OPTIONS_SENTINEL:
            sub = _ask_session_options()
            if sub is None:
                continue  # back to the main menu
            return sub
        if isinstance(result, tuple):
            if result[0] == "manual" and not result[1]:
                manual = _ask_manual_id(ctx.source)
                if not manual:
                    continue
                return ("manual", manual)
            return result
