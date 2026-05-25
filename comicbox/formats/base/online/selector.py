"""
SelectorCallback API for ambiguous-match resolution.

A `SelectorCallback` receives a profile and a list of ranked
`Candidate`s and returns one of:

- `("choose", index)` — pick the i-th candidate.
- `("skip", None)` — drop this file silently.
- `("manual", "<source>:<id>")` — re-tag from an explicit id; falls
  through to the explicit-id code path.
- `("abort", None)` — abort the entire run.
- `("set_unattended", None)` — switch the rest of the session to
  unattended mode. The box re-resolves the current candidates (which
  collapses to SKIP under unattended) without auto-writing this
  prompt's selection.
- `("set_policy", "<name>")` — switch the rest of the session's match
  policy to one of `ask | careful | auto | eager` (a
  :class:`MatchMode` value). The box re-resolves the current
  candidates under the new policy; if the new policy auto-writes,
  the current candidate set's top is written; otherwise the user is
  re-prompted (or the run goes silent under unattended).

The `set_*` actions are flat in the API so programmatic callers
(codex, library consumers) can drive session state from one return
value. The default CLI selector hides them under a nested "Options"
menu to keep the top-level prompt uncluttered.

Comicbox ships a default CLI implementation in `prompt.py` (uses
`questionary`). Programmatic callers (codex, library users) provide
their own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from comicbox.config.settings import ComicboxSettings
    from comicbox.formats.base.online.profile import Candidate, ComicProfile


SelectorAction: TypeAlias = Literal[
    "choose",
    "skip",
    "manual",
    "abort",
    "set_unattended",
    "set_policy",
]
SelectorResult: TypeAlias = tuple[SelectorAction, "int | str | None"]


@dataclass(frozen=True, slots=True)
class SelectorContext:
    """Context passed alongside the candidates to a selector callback."""

    file_path: Path | None
    source: str
    settings: ComicboxSettings
    triggered_hashing: bool


SelectorCallback: TypeAlias = (
    "Callable[[ComicProfile, Sequence[Candidate], SelectorContext], SelectorResult]"
)
