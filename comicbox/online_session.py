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
from comicbox.events import FileError, PromptDeferred, PromptResolvedFromCache

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


@dataclass(frozen=True, slots=True)
class _CachedResolution:
    """A previously-handled prompt's outcome, keyed by series-level fingerprint."""

    action: str
    payload: int | str | None
    # For "choose", the candidate's volume_id at the time the user picked.
    # We re-map to whichever candidate in the new prompt shares it.
    chosen_volume_id: int | None = None


@dataclass(frozen=True, slots=True)
class DeferredPrompt:
    """
    A prompt the session skipped under defer_prompts mode.

    Captures everything Codex needs to render the prompt later in a
    review-tagging UI: the file it came from, source, candidates, mode
    context, and the fingerprint used to key the dedup cache. Codex
    feeds the user's resolution back via :meth:`OnlineSession.preload_resolution`.
    """

    path: Path | None
    source: str
    fingerprint: str
    profile_summary: dict[str, Any]
    candidates: tuple[Candidate, ...]
    mode: SessionMode
    unattended: bool


# --- session ---------------------------------------------------------------


class OnlineSession:
    """
    Codex-friendly façade over Comicbox's online lookup.

    Construction validates per-source credentials and pre-computes the
    ComicboxSettings layer that each per-file Comicbox instance will see.
    Mutable state — ``mode``, ``unattended``, the cancel token — lives on
    the instance and may be updated from any thread.
    """

    def __init__(  # noqa: PLR0913
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
        defer_prompts: bool = False,
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
        self._defer_prompts = defer_prompts

        # Cancel token. Set when cancel() is called; checked between files
        # in tag_many(). Not propagated mid-file — the in-flight per-file
        # lookup runs to completion before the batch stops.
        self._cancel = threading.Event()
        self._state_lock = threading.Lock()

        # Prompt-dedup cache. Keyed by fingerprint of (source, normalized
        # series, sorted distinct candidate volume_ids); the stored entry
        # is the PromptResponse the handler returned the first time we
        # saw this fingerprint. For "choose" actions we also record the
        # candidate's volume_id so we can re-map the index when the new
        # prompt's candidate list is ordered differently. Per-session,
        # in-memory only — disk persistence is out of scope for v1.
        self._prompt_cache: dict[str, _CachedResolution] = {}
        self._prompt_cache_lock = threading.Lock()

        # Defer-prompts queue. When ``defer_prompts`` is set, the bridged
        # selector skips the user's PromptHandler and queues the prompt
        # here instead. Codex's flow: drain via ``deferred_prompts()`` at
        # end-of-batch, present in a review UI, then seed resolutions
        # back via ``preload_resolution()`` and re-run the affected files.
        self._deferred: list[DeferredPrompt] = []
        self._deferred_lock = threading.Lock()

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

    # -- deferred prompts ---------------------------------------------------

    @property
    def defer_prompts(self) -> bool:
        """Whether the session is currently in defer-prompts mode."""
        return self._defer_prompts

    def set_defer_prompts(self, *, defer: bool) -> None:
        """Toggle defer-prompts mode for subsequent file lookups."""
        self._defer_prompts = defer

    def deferred_prompts(self) -> tuple[DeferredPrompt, ...]:
        """Snapshot the queued deferred prompts. Codex's review-UI input."""
        with self._deferred_lock:
            return tuple(self._deferred)

    def clear_deferred_prompts(self) -> None:
        """Drop the deferred-prompt queue without resolving them."""
        with self._deferred_lock:
            self._deferred.clear()

    def preload_resolution(
        self,
        fingerprint: str,
        *,
        action: Literal["choose", "skip", "manual"],
        payload: int | str | None = None,
        chosen_volume_id: int | None = None,
    ) -> None:
        """
        Seed the dedup cache so a re-run auto-resolves the fingerprint.

        Codex's defer-mode flow: drain ``deferred_prompts()`` after the
        batch, present them in a review UI, call ``preload_resolution()``
        for each one the user resolves, then re-tag the affected files
        (with defer_prompts toggled off if desired). The cache hit fires
        the same way it does for in-batch dedup.
        """
        entry = _CachedResolution(
            action=action, payload=payload, chosen_volume_id=chosen_volume_id
        )
        with self._prompt_cache_lock:
            self._prompt_cache[fingerprint] = entry

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
            # Bridge the selector when we have a handler OR when defer
            # mode is on — defer mode produces no handler call but still
            # needs to intercept the prompt to queue it.
            if self._prompt_handler is not None or self._defer_prompts:
                cb.set_online_selector(self._bridged_selector())
            if self._on_event is not None:
                cb.set_event_handler(self._on_event)
            cb.run_online_lookup()
            payload = cb.to_dict()
        return payload.get("comicbox", {}) if isinstance(payload, dict) else {}

    def _bridged_selector(self) -> Callable[..., SelectorResult]:
        """
        Adapt the user's PromptHandler into a SelectorCallback.

        Translates Comicbox's positional SelectorCallback signature into
        a Codex-facing OnlinePrompt / PromptResponse pair. Consults the
        per-session prompt cache first; on cache miss falls through to
        defer-mode (queue + skip) or the user's handler, depending on
        ``defer_prompts``. Resolutions from the handler path are stored
        for next time.
        """
        handler = self._prompt_handler

        def _selector(
            profile: ComicProfile,
            candidates: Sequence[Candidate],
            ctx: SelectorContext,
        ) -> SelectorResult:
            cand_tuple = tuple(candidates)
            fingerprint = _prompt_fingerprint(ctx.source, profile, cand_tuple)
            cached = self._lookup_cached_prompt(fingerprint, cand_tuple)
            if cached is not None:
                if self._on_event is not None:
                    self._on_event(
                        PromptResolvedFromCache(
                            path=ctx.file_path,
                            source=ctx.source,
                            prompt_id=f"{ctx.source}:{id(candidates)}",
                            action=cached[0],
                            fingerprint=fingerprint,
                        )
                    )
                return cached
            if self._defer_prompts:
                self._defer_prompt(fingerprint, profile, cand_tuple, ctx)
                return ("skip", None)
            if handler is None:
                msg = (
                    "OnlineSession has no PromptHandler and defer_prompts "
                    "is disabled; cannot resolve an ambiguous match"
                )
                raise RuntimeError(msg)
            prompt = OnlinePrompt(
                path=ctx.file_path,
                source=ctx.source,
                profile_summary=_summarise_profile(profile),
                candidates=cand_tuple,
                mode=self.mode,
                unattended=self.unattended,
            )
            response = handler.request(prompt)
            self._store_prompt_resolution(fingerprint, response, cand_tuple)
            return (response.action, response.payload)

        return _selector

    def _defer_prompt(
        self,
        fingerprint: str,
        profile: ComicProfile,
        candidates: tuple[Candidate, ...],
        ctx: SelectorContext,
    ) -> None:
        """Queue this prompt for later resolution and emit PromptDeferred."""
        deferred = DeferredPrompt(
            path=ctx.file_path,
            source=ctx.source,
            fingerprint=fingerprint,
            profile_summary=_summarise_profile(profile),
            candidates=candidates,
            mode=self.mode,
            unattended=self.unattended,
        )
        with self._deferred_lock:
            self._deferred.append(deferred)
        if self._on_event is not None:
            self._on_event(
                PromptDeferred(
                    path=ctx.file_path,
                    source=ctx.source,
                    prompt_id=f"{ctx.source}:{id(candidates)}",
                    fingerprint=fingerprint,
                    n_candidates=len(candidates),
                )
            )

    def _lookup_cached_prompt(
        self, fingerprint: str, candidates: tuple[Candidate, ...]
    ) -> SelectorResult | None:
        """
        Match a fingerprint against the cache and re-map the choice.

        For ``choose`` we re-map the cached volume_id to whichever candidate
        in this prompt's list shares it. If no candidate matches, treat
        this as a cache miss and let the handler fire fresh.
        """
        with self._prompt_cache_lock:
            cached = self._prompt_cache.get(fingerprint)
        if cached is None:
            return None
        if cached.action != "choose":
            return (cached.action, cached.payload)
        if cached.chosen_volume_id is None:
            return None
        for i, cand in enumerate(candidates):
            if cand.volume_id is not None and cand.volume_id == cached.chosen_volume_id:
                return ("choose", i)
        return None

    def _store_prompt_resolution(
        self,
        fingerprint: str,
        response: PromptResponse,
        candidates: tuple[Candidate, ...],
    ) -> None:
        """Cache a fresh resolution under its fingerprint."""
        chosen_volume_id: int | None = None
        if response.action == "choose" and isinstance(response.payload, int):
            try:
                chosen_volume_id = candidates[response.payload].volume_id
            except IndexError:
                chosen_volume_id = None
        # Session-level actions (set_unattended / set_policy / abort) are
        # not cached: they apply once, not as a deferred decision.
        if response.action in {"set_unattended", "set_policy", "abort"}:
            return
        entry = _CachedResolution(
            action=response.action,
            payload=response.payload,
            chosen_volume_id=chosen_volume_id,
        )
        with self._prompt_cache_lock:
            self._prompt_cache[fingerprint] = entry

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


def _prompt_fingerprint(
    source: str, profile: ComicProfile, candidates: tuple[Candidate, ...]
) -> str:
    """
    Build a deterministic key identifying the disambiguation question.

    Composed of the source name, series-level profile fields, and the sorted
    set of candidate volume_ids. Different issues of the same series collapse
    to the same fingerprint because their candidate volume_ids match —
    enabling the cache to auto-apply the user's prior series choice to
    every subsequent issue of that run.
    """
    series = (profile.series or "").strip().lower()
    publisher = (profile.publisher or "").strip().lower()
    volume_ids = tuple(
        sorted({c.volume_id for c in candidates if c.volume_id is not None})
    )
    # Fall back to candidate issue_ids when no volume_id is present (some
    # sources don't expose one) — this gives a strictly stricter
    # fingerprint, equivalent to "same exact candidate list."
    if not volume_ids:
        volume_ids = tuple(sorted(c.issue_id for c in candidates))
    parts = (source, series, str(profile.year or ""), publisher, repr(volume_ids))
    return "|".join(parts)
