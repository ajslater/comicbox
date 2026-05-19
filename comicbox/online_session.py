"""
OnlineSession — Codex-facing API for batch online metadata tagging.

Wraps the existing Comicbox.run_online_lookup() per-file flow with a
Codex-friendly surface:

- Per-source credential validation up front (fail-fast).
- Mode aliases (strict / normal / fast / unattended) → the internal
  MatchMode + Prompts enums.
- One programmatic PromptHandler per session that the matcher calls
  whenever it would otherwise hit the CLI questionary prompt.
- Event stream via on_event= for UI feedback.
- Cancellation token: callers stop the batch between files.

The internal matcher / selector / rate-limit machinery is untouched;
this module is a façade.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeAlias

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.config.settings import (
    MatchMode,
    OnlineAuthSettings,
    OnlineLookupSettings,
    OnlineSourceCredentials,
    Prompts,
)
from comicbox.events import FileError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence
    from pathlib import Path

    from comicbox.config.settings import ComicboxSettings
    from comicbox.events import EventHandler
    from comicbox.formats.base.online.profile import Candidate, ComicProfile
    from comicbox.formats.base.online.selector import SelectorContext, SelectorResult


# --- public types -----------------------------------------------------------


SessionMode: TypeAlias = Literal["strict", "normal", "fast"]
SourceName: TypeAlias = Literal["metron", "comicvine"]

_KNOWN_SOURCES: frozenset[str] = frozenset({"metron", "comicvine"})

_MODE_TO_MATCH_MODE: dict[str, MatchMode] = {
    "strict": MatchMode.CAREFUL,
    "normal": MatchMode.AUTO,
    "fast": MatchMode.EAGER,
}


class OnlineConfigurationError(Exception):
    """Raised when OnlineSession inputs are inconsistent or incomplete."""


@dataclass(frozen=True, slots=True)
class OnlineCredentials:
    """Credentials for the online sources Codex may enable."""

    metron_user: str | None = None
    metron_password: str | None = None
    metron_url: str | None = None
    comicvine_key: str | None = None
    comicvine_url: str | None = None


@dataclass(frozen=True, slots=True)
class OnlinePrompt:
    """
    Codex-facing handoff for an ambiguous match.

    The PromptHandler receives one of these and returns a PromptResponse.
    """

    path: Path | None
    source: str
    profile_summary: dict[str, Any]
    candidates: tuple[Candidate, ...]
    mode: SessionMode
    unattended: bool


@dataclass(frozen=True, slots=True)
class PromptResponse:
    """
    Codex-side decision for one prompt.

    ``action`` mirrors :data:`SelectorAction`; ``payload`` is the index for
    ``choose``, the ``"<source>:<id>"`` string for ``manual``, the new mode
    string for ``set_policy``, or ``None`` otherwise.
    """

    action: Literal["choose", "skip", "manual", "abort", "set_unattended", "set_policy"]
    payload: int | str | None = None


class PromptHandler(Protocol):
    """
    Codex's prompt-resolution callback.

    Single-prompt form. A batched form (``request_many``) is planned but
    not exposed in v1 — see plan §3.4.
    """

    def request(self, prompt: OnlinePrompt) -> PromptResponse:
        """Resolve one prompt; return the chosen action/payload."""
        ...


@dataclass(frozen=True, slots=True)
class OnlineResult:
    """Per-file outcome of an online tagging call."""

    path: Path
    tags: dict[str, Any] | None = None
    error: BaseException | None = None
    cancelled: bool = False


# --- session ---------------------------------------------------------------


class OnlineSession:
    """
    Codex-friendly façade over Comicbox's online lookup.

    Construction validates per-source credentials and pre-computes the
    ComicboxSettings layer that each per-file Comicbox instance will see.
    Mutable state — ``mode``, ``unattended``, the cancel token — lives on
    the instance and may be updated from any thread.
    """

    def __init__(
        self,
        *,
        sources: Iterable[str] = ("metron", "comicvine"),
        credentials: OnlineCredentials | None = None,
        mode: SessionMode = "normal",
        unattended: bool = False,
        prompt_handler: PromptHandler | None = None,
        on_event: EventHandler | None = None,
        rematch: bool = False,
        all_sources: bool = False,
    ) -> None:
        """Validate inputs, build per-session state. See class docstring."""
        self._sources = frozenset(sources)
        self._validate_sources(self._sources)
        self._credentials = credentials or OnlineCredentials()
        self._validate_credentials(self._sources, self._credentials)
        self._mode: SessionMode = self._validate_mode(mode)
        self._unattended = unattended
        self._prompt_handler = prompt_handler
        self._on_event = on_event
        self._rematch = rematch
        self._all_sources = all_sources

        # Cancel token. Set when cancel() is called; checked between files
        # in tag_many(). Not propagated mid-file — the in-flight per-file
        # lookup runs to completion before the batch stops.
        self._cancel = threading.Event()
        self._state_lock = threading.Lock()

    # -- mutable session state ----------------------------------------------

    @property
    def mode(self) -> SessionMode:
        """Current session mode (read-only; mutate via set_mode())."""
        with self._state_lock:
            return self._mode

    @property
    def unattended(self) -> bool:
        """Current session unattended flag."""
        with self._state_lock:
            return self._unattended

    def set_mode(self, mode: SessionMode) -> None:
        """Change the session mode for subsequent file lookups."""
        validated = self._validate_mode(mode)
        with self._state_lock:
            self._mode = validated

    def set_unattended(self, *, unattended: bool) -> None:
        """Toggle the unattended flag for subsequent file lookups."""
        with self._state_lock:
            self._unattended = unattended

    def cancel(self) -> None:
        """Stop accepting new files. In-flight lookup runs to completion."""
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        """Whether cancel() has been called."""
        return self._cancel.is_set()

    # -- rate limits --------------------------------------------------------

    def rate_limit_status(self) -> dict[str, dict[str, Any]]:
        """
        Snapshot of each enabled source's current rate-limit budget.

        v1 stub: returns an empty dict for every enabled source. The
        wiring to mokkari / simyan rate-limit buckets lands in the
        follow-up commit (see plan §3.5 / §3.6).
        """
        return {name: {} for name in self._sources}

    # -- per-file tagging ---------------------------------------------------

    def tag(self, path: Path) -> OnlineResult:
        """Tag one file synchronously."""
        if self._cancel.is_set():
            return OnlineResult(path=path, cancelled=True)
        try:
            tags = self._run_one(path)
        except Exception as exc:
            if self._on_event is not None:
                self._on_event(FileError(path=path, error=str(exc)))
            return OnlineResult(path=path, error=exc)
        return OnlineResult(path=path, tags=tags)

    def tag_many(self, paths: Iterable[Path]) -> Iterator[OnlineResult]:
        """Tag many files sequentially. Stops accepting new ones on cancel."""
        for path in paths:
            if self._cancel.is_set():
                yield OnlineResult(path=path, cancelled=True)
                continue
            yield self.tag(path)

    # -- internals ----------------------------------------------------------

    def _run_one(self, path: Path) -> dict[str, Any]:
        config = self._build_config()
        with Comicbox(path, config=config) as cb:
            if self._prompt_handler is not None:
                cb.set_online_selector(self._bridged_selector())
            cb.run_online_lookup()
            payload = cb.to_dict()
        return payload.get("comicbox", {}) if isinstance(payload, dict) else {}

    def _bridged_selector(self) -> Callable[..., SelectorResult]:
        """
        Adapt the user's PromptHandler into a SelectorCallback.

        Translates Comicbox's positional SelectorCallback signature into
        a Codex-facing OnlinePrompt / PromptResponse pair.
        """
        handler = self._prompt_handler
        if handler is None:  # pragma: no cover — guarded at call site
            msg = "PromptHandler is required"
            raise RuntimeError(msg)

        def _selector(
            profile: ComicProfile,
            candidates: Sequence[Candidate],
            ctx: SelectorContext,
        ) -> SelectorResult:
            prompt = OnlinePrompt(
                path=ctx.file_path,
                source=ctx.source,
                profile_summary=_summarise_profile(profile),
                candidates=tuple(candidates),
                mode=self.mode,
                unattended=self.unattended,
            )
            response = handler.request(prompt)
            return (response.action, response.payload)

        return _selector

    def _build_config(self) -> ComicboxSettings:
        """
        Build a ComicboxSettings from the session's tagging preferences.

        Layered as ``replace`` over the default settings rather than fed
        through ``get_config(Namespace(...))`` because some of the fields
        we need to set (``enabled``, ``sources``, per-source auth dict)
        live on runtime-only fields the CLI namespace parser ignores.
        """
        base = get_config()
        new_lookup = OnlineLookupSettings(
            enabled=True,
            sources=frozenset(self._sources),
            match=_MODE_TO_MATCH_MODE[self.mode],
            prompts=Prompts.NEVER if self.unattended else Prompts.ASK,
            rematch=self._rematch,
            all_sources=self._all_sources,
        )
        new_auth = OnlineAuthSettings(sources=self._build_auth_sources())
        new_online = replace(base.online, lookup=new_lookup, auth=new_auth)
        return replace(base, online=new_online)

    def _build_auth_sources(self) -> dict[str, OnlineSourceCredentials]:
        creds = self._credentials
        result: dict[str, OnlineSourceCredentials] = {}
        if "metron" in self._sources:
            result["metron"] = OnlineSourceCredentials(
                user=creds.metron_user,
                password=creds.metron_password,
                url=creds.metron_url,
            )
        if "comicvine" in self._sources:
            result["comicvine"] = OnlineSourceCredentials(
                key=creds.comicvine_key,
                url=creds.comicvine_url,
            )
        return result

    # -- validation ---------------------------------------------------------

    @staticmethod
    def _validate_sources(sources: frozenset[str]) -> None:
        if not sources:
            msg = "OnlineSession requires at least one source"
            raise OnlineConfigurationError(msg)
        unknown = sources - _KNOWN_SOURCES
        if unknown:
            msg = (
                f"Unknown online sources: {sorted(unknown)}. "
                f"Expected a subset of {sorted(_KNOWN_SOURCES)}."
            )
            raise OnlineConfigurationError(msg)

    @staticmethod
    def _validate_credentials(
        sources: frozenset[str], creds: OnlineCredentials
    ) -> None:
        missing: list[str] = []
        if "metron" in sources and not (creds.metron_user and creds.metron_password):
            missing.append("metron requires metron_user and metron_password")
        if "comicvine" in sources and not creds.comicvine_key:
            missing.append("comicvine requires comicvine_key")
        if missing:
            msg = "Missing credentials for enabled online source(s):\n  " + "\n  ".join(
                missing
            )
            raise OnlineConfigurationError(msg)

    @staticmethod
    def _validate_mode(mode: SessionMode) -> SessionMode:
        if mode not in _MODE_TO_MATCH_MODE:
            msg = (
                f"Unknown mode {mode!r}. Expected one of {sorted(_MODE_TO_MATCH_MODE)}."
            )
            raise OnlineConfigurationError(msg)
        return mode


def _summarise_profile(profile: ComicProfile) -> dict[str, Any]:
    """Pluck the user-displayable fields off a ComicProfile."""
    fields_of_interest = (
        "series",
        "volume",
        "issue",
        "year",
        "publisher",
        "filename",
    )
    return {f: getattr(profile, f, None) for f in fields_of_interest}
