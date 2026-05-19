"""
Online metadata lookup mixin.

Sits between `ComicboxNormalize` and `ComicboxMerge` in the box chain.
For M2 the only path implemented is ``--id <db>:<id>`` — exact-issue
fetch. Search and ranking land in M3.

The mixin runs once per box instance, gated on
``settings.online.lookup.enabled``. For each active source (one whose
required credentials resolve and whose name is in
``selected_sources`` if that filter is set), it:

1. Checks ``--ignore-existing`` against any source data already
   carrying an identifier from this source's name (we don't re-tag if
   the user has already done so, even from a different source).
2. Calls ``source.get(issue_id)`` for every ``explicit_id`` mapped to
   that source.
3. Wraps the response under the schema's root tag and pushes it via
   ``add_source(source.metadata_source, ...)`` so the existing load
   → normalize → merge pipeline picks it up.
"""

from __future__ import annotations

import sys
import threading
from dataclasses import replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar

from glom import glom
from loguru import logger

from comicbox.box.normalize import ComicboxNormalize
from comicbox.config.settings import MatchMode, Prompts
from comicbox.events import (
    AutoWritten,
    FileFinished,
    NoMatch,
    PromptQueued,
    PromptResolved,
    SearchCompleted,
    SearchStarted,
    SeriesIdentified,
    Skipped,
)
from comicbox.formats import FORMAT_REGISTRATIONS
from comicbox.formats.base.online import outcome_stats
from comicbox.formats.base.online.matcher import (
    OnlineMatcher,
    Resolution,
    ResolutionKind,
)
from comicbox.formats.base.online.profile import (
    ComicProfile,
    parse_issue_int,
    parse_year,
    strip_issue_leading_zeros,
)
from comicbox.formats.base.online.prompt import cli_selector
from comicbox.formats.base.online.selector import SelectorContext
from comicbox.formats.comicvine_api.online_source import ComicVineOnlineSource
from comicbox.formats.metron_api.online_source import MetronOnlineSource
from comicbox.formats.sources import MetadataSources

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from comicbox.config.settings import OnlineSettings
    from comicbox.events import Event, EventHandler
    from comicbox.formats.base.online.profile import Candidate
    from comicbox.formats.base.online.selector import SelectorCallback, SelectorResult
    from comicbox.formats.base.online.sources.base import OnlineSource
    from comicbox.formats.comicvine_api.online_source import CoverHashUrlCache


class OnlineLookupAbortedError(Exception):
    """Raised when the selector callback returns ('abort', None)."""


# Source factories let tests substitute mocks without monkey-patching imports.
OnlineSourceFactory = "Callable[[Any, OnlineSettings], OnlineSource]"


# Short-name → OnlineSource class. Kept centralized rather than declared
# in each format's REGISTRATION because each OnlineSource subclass imports
# from `comicbox.formats` at module level (ClassVar = MetadataFormats.X) —
# pulling those imports into the FormatRegistration declaration creates
# a load-time cycle through the formats package init. Revisit if those
# ClassVars are restructured to defer the enum lookup.
_DEFAULT_SOURCE_FACTORIES: MappingProxyType[str, Any] = MappingProxyType(
    {
        "metron": MetronOnlineSource,
        "comicvine": ComicVineOnlineSource,
    }
)


def _online_source_enums() -> frozenset[MetadataSources]:
    """
    Derive the set of online MetadataSources from per-format REGISTRATIONs.

    Used to skip self when checking for existing identifiers under
    `--ignore-existing`.
    """
    online_source_names = {
        source_name
        for registration in FORMAT_REGISTRATIONS.values()
        if registration.is_online
        for source_name in registration.sources
    }
    return frozenset(MetadataSources[name] for name in online_source_names)


_ONLINE_SOURCE_ENUMS: frozenset[MetadataSources] = _online_source_enums()


class _NoTtyHintGuard:
    """One-shot guard for the no-TTY hint, lock-protected for `-j N` runs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._shown = False

    def maybe_log(self, *, has_callback: bool) -> None:
        """
        Log the hint at most once per process if conditions warrant.

        Programmatic library callers (codex, etc.) typically register a
        selector callback before invoking the lookup; their presence
        silences the hint because they have a way to handle prompts.
        """
        if has_callback:
            return
        try:
            is_tty = sys.stdin.isatty()
        except (AttributeError, ValueError):
            # Closed stdin or unusual stream — treat as no TTY.
            is_tty = False
        if is_tty:
            return
        with self._lock:
            if self._shown:
                return
            self._shown = True
        logger.info(
            "online: no TTY detected and no prompt callback registered; "
            "pass --unattended if you don't expect to see prompts "
            "(interactive mode without a TTY will hang on the first "
            "PROMPT decision)."
        )


_no_tty_hint = _NoTtyHintGuard()


def _series_fingerprint(profile: ComicProfile) -> str:
    """
    Deterministic series-level key for the series-cache (plan §3.10).

    Profile-only, computed BEFORE we have candidates — distinct from the
    step-6 prompt-cache fingerprint which incorporates candidate
    volume_ids. Same series across different issues collapses to the
    same string here.
    """
    series = (profile.series or "").strip().lower()
    publisher = (profile.publisher or "").strip().lower()
    year = str(profile.year or "")
    return f"{series}|{year}|{publisher}"


def _resolve_volume(md: dict) -> int | None:
    """
    Extract `comicbox.volume.number` as an int, defensively.

    Rejects 4-digit year-shaped values (1900-2100). The
    [ComicInfo.xml convention](https://anansi-project.github.io/docs/comicinfo/documentation#volume)
    of using the year-of-first-issue as the volume number is widespread
    (comictagger writes it that way), but Metron's `series_volume`
    filter expects an ordinal (1, 2, 3 — "Vol. N of M"). Sending the
    year as `series_volume` matches no issues and wastes API budget on
    the drop-volume retry.

    A real volume "Vol. 2019 of 9999" doesn't exist in the wild —
    real ordinal volumes are well under 50 in practice. Treating
    1900-2100 as "year masquerading as volume" is safe and matches the
    failure mode we actually see.
    """
    raw = glom(md, "comicbox.volume.number", default=None)
    if raw is None:
        return None
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    if 1900 <= v <= 2100:  # noqa: PLR2004 — year range, not a magic threshold
        return None
    return v


def _detect_cv_id_disagreement(
    metron_md: dict | None, cv_md: dict | None
) -> tuple[str, str] | None:
    """
    Compare the ComicVine identifier each source contributed.

    Metron's `cv_id` field flows into its merged metadata as
    `comicbox.identifiers.comicvine.key`; CV's own issue id flows in
    under the same path from the CV-sourced data. When both are set and
    disagree, one of them is wrong (Metron's `cv_id` field is a
    cross-reference that goes stale; our CV match could also have hit
    the wrong volume). Return ``(metron_cv_id, cv_cv_id)`` so the
    caller can log it; return None for "no disagreement to report"
    (either source missing, either id missing, or they match).
    """
    if not metron_md or not cv_md:
        return None
    metron_key = glom(metron_md, "comicbox.identifiers.comicvine.key", default=None)
    cv_key = glom(cv_md, "comicbox.identifiers.comicvine.key", default=None)
    if metron_key is None or cv_key is None:
        return None
    metron_str = str(metron_key)
    cv_str = str(cv_key)
    if metron_str == cv_str:
        return None
    return (metron_str, cv_str)


def _accumulate_profile_fields(fields: dict[str, Any], md: dict) -> None:
    """First-wins accumulation of profile fields across normalized sources."""
    if "series" not in fields and (v := glom(md, "comicbox.series.name", default=None)):
        fields["series"] = v
    if "issue" not in fields and (v := glom(md, "comicbox.issue.name", default=None)):
        fields["issue"] = v
    if "year" not in fields:
        raw_year = glom(md, "comicbox.date.year", default=None) or glom(
            md, "comicbox.date.cover_date", default=None
        )
        if (parsed := parse_year(raw_year)) is not None:
            fields["year"] = parsed
    if "publisher" not in fields and (
        v := glom(md, "comicbox.publisher.name", default=None)
    ):
        fields["publisher"] = v
    if "page_count" not in fields and (
        v := glom(md, "comicbox.page_count", default=None)
    ):
        fields["page_count"] = v
    if "volume" not in fields and (v := _resolve_volume(md)) is not None:
        fields["volume"] = v


class ComicboxOnlineLookup(ComicboxNormalize):
    """Pulls online metadata into the source pool before merge runs."""

    # Class-level so tests can override (and per-instance attrs override that).
    _ONLINE_SOURCE_FACTORIES: ClassVar[MappingProxyType[str, Any]] = (
        _DEFAULT_SOURCE_FACTORIES
    )

    # Process-wide lock around the selector callback. Under `-j N` parallel
    # batch runs we serialise prompts so output stays readable and the user
    # can see which file is being asked about.
    _PROMPT_LOCK: ClassVar[threading.Lock] = threading.Lock()

    # Per-instance selector override; falls back to the default CLI prompt.
    _online_selector: SelectorCallback | None = None

    # Per-instance event handler; emits SearchStarted / AutoWritten / etc.
    # for callers driving online lookup programmatically (OnlineSession).
    _event_handler: EventHandler | None = None

    # Per-instance series cache (series-first batching, plan §3.10). When
    # set, the matcher consults it before the cold-path search: a cache
    # hit triggers source.lookup_issue(volume_id, number) instead. The
    # cache key is (source_name, series_fingerprint); the value is the
    # resolved volume_id. Populated on each cold-path acceptance using
    # ``setdefault`` so the first writer wins — falsy-group collisions
    # don't get to overwrite the original.
    _series_cache: MutableMapping[tuple[str, str], int] | None = None

    _online_lookup_done_flag: bool = False
    _cover_hash_url_cache: CoverHashUrlCache | None = None
    _local_cover_phash_computed: bool = False
    _local_cover_phash_value: str | None = None

    def set_online_selector(self, selector: SelectorCallback | None) -> None:
        """Register a programmatic selector callback (codex / library users)."""
        self._online_selector = selector

    def set_event_handler(self, handler: EventHandler | None) -> None:
        """Register an event-stream callback for online-lookup progress."""
        self._event_handler = handler

    def set_series_cache(
        self, cache: MutableMapping[tuple[str, str], int] | None
    ) -> None:
        """Register a session-level series cache for series-first batching."""
        self._series_cache = cache

    def _emit(self, event: Event) -> None:
        """No-op if no handler is registered, else forward the event."""
        if self._event_handler is not None:
            self._event_handler(event)

    def _online_lookup_already_done(self) -> bool:
        return self._online_lookup_done_flag

    def _mark_online_lookup_done(self) -> None:
        self._online_lookup_done_flag = True

    def _warn_unconfigured_source(self, name: str) -> None:
        """
        Loud warning when a user-requested source can't run for credential reasons.

        Quiet skip when the source was only included via the `all` sentinel
        — in that case we don't know the user wanted this specific source.
        """
        online = self._config.online
        explicit_id = online.lookup.ids.get(name)
        if explicit_id is not None:
            logger.warning(
                f"online: --id {name}:{explicit_id} requested but {name} is "
                f"not configured (missing credentials); skipping"
            )
            return
        explicit_sid = online.lookup.series_ids.get(name)
        if explicit_sid is not None:
            logger.warning(
                f"online: --series-id {name}:{explicit_sid} requested but "
                f"{name} is not configured (missing credentials); skipping"
            )
            return
        # Was the source named explicitly via `--online <list>`? selected
        # is None for the `all` sentinel; only warn for explicit lists.
        if online.lookup.sources is not None and name in online.lookup.sources:
            logger.warning(
                f"online: --online {name} requested but {name} is not "
                f"configured (missing credentials); skipping"
            )

    def _build_active_online_sources(self) -> list[OnlineSource]:
        """Resolve which configured online sources participate in this run."""
        online: OnlineSettings = self._config.online
        selected = online.lookup.sources
        active: list[OnlineSource] = []
        for name, factory in self._ONLINE_SOURCE_FACTORIES.items():
            if selected is not None and name not in selected:
                continue
            creds = online.auth.sources.get(name)
            if creds is None:
                self._warn_unconfigured_source(name)
                continue
            source = factory(creds, online)
            if not source.is_configured():
                self._warn_unconfigured_source(name)
                continue
            active.append(source)
        return active

    def _has_existing_identifier(self, source_name: str) -> bool:
        """Return True if any non-online source's data already has this source's id."""
        keypath = f"comicbox.identifiers.{source_name}"
        for src in MetadataSources:
            if src in _ONLINE_SOURCE_ENUMS:
                continue
            normalized = self.get_normalized_metadata(src)
            if not normalized:
                continue
            for loaded in normalized:
                if glom(dict(loaded.metadata), keypath, default=None):
                    return True
        return False

    def _stored_identifier(self, source_name: str) -> int | None:
        """
        Return the upstream issue id for `source_name` stored on the comic, if any.

        Scans every non-online normalized source for
        ``comicbox.identifiers.<source_name>.key`` and returns the first
        value that parses as an int. Used to drive a fast `source.get(id)`
        refresh in lieu of a full search when the comic was previously
        tagged. Returns None when no parseable stored id is found.
        """
        keypath = f"comicbox.identifiers.{source_name}.key"
        for src in MetadataSources:
            if src in _ONLINE_SOURCE_ENUMS:
                continue
            normalized = self.get_normalized_metadata(src)
            if not normalized:
                continue
            for loaded in normalized:
                raw = glom(dict(loaded.metadata), keypath, default=None)
                if raw is None:
                    continue
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    continue
        return None

    def _wrap_payload(self, source: OnlineSource, payload: dict[str, Any]) -> dict:
        """Wrap raw API response under the format's ROOT_TAG for schema.load."""
        schema_class = source.metadata_format.value.schema_class
        return {schema_class.ROOT_TAG: payload}

    def _fetch_explicit_id(self, source: OnlineSource, issue_id: int) -> None:
        try:
            payload = source.get(issue_id)
        except Exception as exc:
            logger.warning(
                f"online {source.name}: fetch by id={issue_id} failed: {exc}"
            )
            return
        wrapped = self._wrap_payload(source, payload)
        self.add_source(
            source.metadata_source,
            wrapped,
            fmt=source.metadata_format,
        )
        logger.debug(f"online {source.name}: added id={issue_id}")

    def _build_profile(self) -> ComicProfile:
        """Read the non-online merged-so-far metadata into a ComicProfile."""
        # Collect from non-online normalized sources, first-wins.
        fields: dict[str, Any] = {}
        for src in MetadataSources:
            if src in _ONLINE_SOURCE_ENUMS:
                continue
            normalized = self.get_normalized_metadata(src)
            if not normalized:
                continue
            for loaded in normalized:
                _accumulate_profile_fields(fields, dict(loaded.metadata))
        return ComicProfile(
            series=fields.get("series"),
            issue=fields.get("issue"),
            issue_int=parse_issue_int(fields.get("issue")),
            year=fields.get("year"),
            publisher=fields.get("publisher"),
            page_count=fields.get("page_count"),
            volume=fields.get("volume"),
        )

    def _accept_candidate(self, source: OnlineSource, candidate: Candidate) -> None:
        """Fetch the full record for an accepted candidate and inject it."""
        self._fetch_explicit_id(source, candidate.issue_id)
        self._maybe_populate_series_cache(source, candidate)

    def _maybe_populate_series_cache(
        self, source: OnlineSource, candidate: Candidate
    ) -> None:
        """
        Cache the resolved series volume_id on cold-path acceptance.

        First-writer-wins: a falsy-group collision (two unrelated comics
        that happened to share a series fingerprint) can't overwrite an
        already-resolved entry. Fires ``SeriesIdentified`` only on first
        population for this fingerprint. Locking — when needed for
        concurrent callers — is the OnlineSession's responsibility; the
        cache passed in here can be a thread-safe wrapper.
        """
        if self._series_cache is None or candidate.volume_id is None:
            return
        fingerprint = _series_fingerprint(self._build_profile())
        key = (source.name, fingerprint)
        if key in self._series_cache:
            return
        self._series_cache[key] = candidate.volume_id
        self._emit(
            SeriesIdentified(
                path=getattr(self, "_path", None),
                source=source.name,
                series_fingerprint=fingerprint,
                volume_id=candidate.volume_id,
            )
        )

    def _candidate_cover_hash_fetcher(self, url: str) -> str | None:
        """
        Download a candidate cover from URL and return its pHash, with caching.

        Used by the matcher for sources that don't ship a precomputed hash
        (ComicVine, GCD). Local writes go through the shared
        cover-hashes sqlite cache.
        """
        from comicbox.formats.base.online.cover_hash import compute_phash
        from comicbox.formats.comicvine_api.online_source import (
            CoverHashUrlCache,
        )

        if not url:
            return None

        cache = self._cover_hash_url_cache
        if cache is None:
            cache_dir = self._config.online.cache.dir
            if cache_dir is None:
                from platformdirs import user_cache_path

                cache_dir = user_cache_path("comicbox") / "online"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache = CoverHashUrlCache(cache_dir / "cover_hashes.sqlite")
            self._cover_hash_url_cache = cache

        from comicbox.config.settings import CacheMode

        if self._config.online.cache.mode is CacheMode.OFF:
            cache = None
        if cache is not None and (cached := cache.get(url)):
            return cached

        try:
            import httpx

            response = httpx.get(url, timeout=15.0, follow_redirects=True)
            response.raise_for_status()
        except Exception as exc:
            logger.warning(f"online: cover download failed ({url}): {exc}")
            return None

        try:
            phash = compute_phash(response.content)
        except Exception as exc:
            logger.warning(f"online: cover pHash failed ({url}): {exc}")
            return None

        if cache is not None:
            cache.set(url, phash)
        return phash

    def _local_cover_phash(self) -> str | None:
        """Compute the comic's pHash on demand, cached on the box instance."""
        if self._local_cover_phash_computed:
            return self._local_cover_phash_value
        self._local_cover_phash_computed = True
        try:
            cover_bytes = self.get_cover_page(skip_metadata=True)  # pyright: ignore[reportAttributeAccessIssue], # ty: ignore[unresolved-attribute]
        except Exception as exc:
            logger.debug(f"local cover: fetch failed: {exc}")
            return None
        if not cover_bytes:
            return None
        try:
            from comicbox.formats.base.online.cover_hash import compute_phash

            self._local_cover_phash_value = compute_phash(cover_bytes)
        except Exception as exc:
            logger.warning(f"local cover: pHash failed: {exc}")
        return self._local_cover_phash_value

    def _resolve_with_matcher(
        self, source_name: str, candidates: list[Candidate]
    ) -> Resolution:
        from comicbox.config.settings import (
            resolve_auto_threshold,
            resolve_disambiguation_margin,
            resolve_min_confidence,
        )

        online = self._config.online
        threshold = resolve_auto_threshold(online, source_name)
        min_conf = resolve_min_confidence(online, source_name)
        margin = resolve_disambiguation_margin(online, source_name)
        matcher = OnlineMatcher()
        ranked = matcher.rank(
            self._build_profile(),
            candidates,
            local_hash_provider=self._local_cover_phash,
            candidate_hash_fetcher=self._candidate_cover_hash_fetcher,
            threshold=threshold,
            min_confidence=min_conf,
            disambiguation_margin=margin,
        )
        return matcher.resolve(ranked, online, source_name)

    def _selector_for_run(self) -> SelectorCallback:
        return self._online_selector or cli_selector

    def _apply_session_lookup_override(self, **changes: Any) -> None:
        """
        Mutate the shared ``OnlineLookupSettings`` in place for session changes.

        Used for ``set_unattended`` / ``set_policy`` from the prompt path.
        The dataclasses are frozen, but the box's config is shared by
        reference across all Comicbox instances spawned from the same
        Runner. Replacing the nested slot via ``object.__setattr__``
        propagates the change to every in-flight worker thread without
        breaking the dataclass invariants for other callers.
        """
        new_lookup = replace(self._config.online.lookup, **changes)
        new_online = replace(self._config.online, lookup=new_lookup)
        object.__setattr__(self._config, "online", new_online)

    def _handle_prompt(
        self, source: OnlineSource, candidates: tuple[Candidate, ...]
    ) -> None:
        """
        Drive the selector callback for the PROMPT case.

        Acquires the class-level `_PROMPT_LOCK` around the selector call
        so concurrent worker threads (when `-j N > 1`) don't garble each
        other's prompts. Re-resolves and re-prompts when the selector
        requests a session-level setting change (`set_unattended` /
        `set_policy`) so the new setting takes effect on the current
        candidate set immediately.
        """
        current = candidates
        path = getattr(self, "_path", None)
        prompt_id = f"{source.name}:{id(candidates)}"
        while True:
            self._emit(
                PromptQueued(
                    path=path,
                    source=source.name,
                    prompt_id=prompt_id,
                    n_candidates=len(current),
                )
            )
            result = self._invoke_selector(source, current)
            action, payload = result
            self._emit(
                PromptResolved(
                    path=path,
                    source=source.name,
                    prompt_id=prompt_id,
                    action=action,
                )
            )
            if action in {"set_unattended", "set_policy"}:
                if not self._apply_session_action(source, action, payload):
                    return
                resolution = self._resolve_existing(source.name, list(current))
                if self._dispatch_resolution(source, resolution):
                    return
                current = resolution.candidates
                continue
            self._dispatch_terminal_prompt_action(source, current, action, payload)
            return

    def _invoke_selector(
        self, source: OnlineSource, candidates: tuple[Candidate, ...]
    ) -> SelectorResult:
        selector = self._selector_for_run()
        ctx = SelectorContext(
            file_path=getattr(self, "_path", None),
            source=source.name,
            settings=self._config,
            triggered_hashing=any(c.cover_score is not None for c in candidates),
        )
        with type(self)._PROMPT_LOCK:  # noqa: SLF001 — class-level lock by design
            return selector(self._build_profile(), candidates, ctx)

    def _apply_session_action(
        self, source: OnlineSource, action: str, payload: int | str | None
    ) -> bool:
        """
        Apply a `set_unattended` / `set_policy` action to the session.

        Returns True on success, False if the payload was malformed (in
        which case the prompt has been recorded as declined and the
        caller should bail out).
        """
        if action == "set_unattended":
            self._apply_session_lookup_override(prompts=Prompts.NEVER)
            logger.info(f"online {source.name}: session set to unattended via prompt")
            return True
        if not isinstance(payload, str):
            logger.warning(
                f"online {source.name}: set_policy requires a policy name; "
                f"got {payload!r}"
            )
            outcome_stats.record_prompt_declined(source.name)
            return False
        try:
            new_match = MatchMode(payload)
        except ValueError:
            logger.warning(
                f"online {source.name}: unknown match mode {payload!r}; "
                "expected one of ask | careful | auto | eager"
            )
            outcome_stats.record_prompt_declined(source.name)
            return False
        self._apply_session_lookup_override(match=new_match)
        logger.info(
            f"online {source.name}: session match mode set to {new_match.value} via prompt"
        )
        return True

    def _resolve_existing(
        self, source_name: str, ranked: list[Candidate]
    ) -> Resolution:
        """Re-apply policy to an already-ranked candidate list."""
        return OnlineMatcher().resolve(ranked, self._config.online, source_name)

    def _dispatch_resolution(
        self, source: OnlineSource, resolution: Resolution
    ) -> bool:
        """
        Handle a fresh resolution after a session change.

        Returns True when the resolution was terminal (auto-write, skip,
        no-match) and the prompt loop should exit. Returns False when the
        resolution is still PROMPT and the caller should loop.
        """
        if resolution.kind is ResolutionKind.AUTO_WRITE and resolution.chosen:
            logger.info(
                f"online {source.name}: auto-writing "
                f"id={resolution.chosen.issue_id} "
                f"(score={resolution.chosen.score:.2f}) after session change"
            )
            outcome_stats.record_auto_write(source.name)
            self._accept_candidate(source, resolution.chosen)
            return True
        if resolution.kind is ResolutionKind.SKIP:
            logger.info(f"online {source.name}: skipped after session change")
            outcome_stats.record_skip(source.name)
            return True
        if resolution.kind is ResolutionKind.NO_MATCH:
            logger.info(f"online {source.name}: no match after session change")
            outcome_stats.record_no_match(source.name)
            return True
        return False

    def _dispatch_terminal_prompt_action(
        self,
        source: OnlineSource,
        candidates: tuple[Candidate, ...],
        action: str,
        payload: int | str | None,
    ) -> None:
        if action == "choose" and isinstance(payload, int):
            chosen = candidates[payload]
            logger.info(f"online {source.name}: prompt-chose id={chosen.issue_id}")
            outcome_stats.record_prompt_accepted(source.name)
            self._accept_candidate(source, chosen)
            return
        if action == "manual" and isinstance(payload, str):
            try:
                src_name, _, raw_id = payload.partition(":")
                issue_id = int(raw_id)
            except ValueError:
                logger.warning(f"online: manual id {payload!r} is not <source>:<int>")
                outcome_stats.record_prompt_declined(source.name)
                return
            if src_name.strip().lower() != source.name:
                logger.warning(
                    f"online {source.name}: manual id {payload!r} routes to "
                    f"a different source; skipping"
                )
                outcome_stats.record_prompt_declined(source.name)
                return
            outcome_stats.record_prompt_accepted(source.name)
            self._fetch_explicit_id(source, issue_id)
            return
        if action == "abort":
            reason = "online: aborted by user from prompt"
            raise OnlineLookupAbortedError(reason)
        logger.info(f"online {source.name}: skipped via prompt")
        outcome_stats.record_prompt_declined(source.name)

    def _search_path(self, source: OnlineSource) -> None:
        """Search → rank → resolve → fetch on accept."""
        profile = self._build_profile()
        path = getattr(self, "_path", None)
        if not (profile.series or profile.issue or profile.year):
            logger.warning(
                f"online {source.name}: no search criteria — couldn't extract "
                "series, issue#, or year from the comic's metadata or "
                f"filename. Use --id {source.name}:<issue_id> to tag by id."
            )
            return
        # Show what's actually sent: leading zeros stripped from issue#.
        search_issue = strip_issue_leading_zeros(profile.issue)
        criteria_summary = (
            f"series={profile.series!r} issue={search_issue!r} year={profile.year}"
        )
        logger.info(f"online {source.name}: searching with {criteria_summary}")
        self._emit(SearchStarted(path=path, source=source.name))
        try:
            candidates = source.search(profile)
        except Exception as exc:
            logger.warning(f"online {source.name}: search failed: {exc}")
            return
        top_score = candidates[0].score if candidates else None
        self._emit(
            SearchCompleted(
                path=path,
                source=source.name,
                n_candidates=len(candidates),
                top_score=top_score,
            )
        )
        if not candidates:
            logger.info(
                f"online {source.name}: 0 candidates for {criteria_summary} "
                "(no matching issues in the database)"
            )
            return
        resolution = self._resolve_with_matcher(source.name, candidates)
        if resolution.kind is ResolutionKind.AUTO_WRITE and resolution.chosen:
            logger.info(
                f"online {source.name}: auto-writing "
                f"id={resolution.chosen.issue_id} "
                f"(score={resolution.chosen.score:.2f})"
            )
            outcome_stats.record_auto_write(source.name)
            self._accept_candidate(source, resolution.chosen)
            self._emit(
                AutoWritten(
                    path=path,
                    source=source.name,
                    candidate_summary=str(resolution.chosen.issue_id),
                )
            )
            return
        if resolution.kind is ResolutionKind.NO_MATCH:
            logger.info(f"online {source.name}: no match cleared min_confidence")
            outcome_stats.record_no_match(source.name)
            self._emit(NoMatch(path=path, source=source.name))
            return
        if resolution.kind is ResolutionKind.SKIP:
            top = resolution.candidates[0].score if resolution.candidates else 0
            logger.info(
                f"online {source.name}: skipped (matcher declined; top={top:.2f})"
            )
            outcome_stats.record_skip(source.name)
            self._emit(
                Skipped(path=path, source=source.name, reason="matcher_declined")
            )
            return
        # ResolutionKind.PROMPT — invoke the selector callback.
        self._handle_prompt(source, resolution.candidates)

    def _lookup_one_source(self, source: OnlineSource) -> bool:
        """
        Drive the lookup for one source; return True iff the source "won".

        A win is any of: explicit-id fetch, --ignore-existing skip on a
        pre-tagged file, stored-id refresh, or an accepted search result.
        The win signal feeds the first-wins early-exit in `run_online_lookup`.
        """
        online = self._config.online
        # Explicit --id is the strongest user signal. It overrides
        # --rematch and the stored-id fast path.
        explicit_ids = online.lookup.ids
        issue_id = explicit_ids.get(source.name)
        if issue_id is not None:
            outcome_stats.record_explicit_id(source.name)
            self._fetch_explicit_id(source, issue_id)
            return True

        # Fast refresh: a stored upstream id from a prior tag lets us
        # call source.get(id) instead of walking the full search path.
        # ``--rematch`` suppresses the fast path so users can re-evaluate
        # a stale/wrong stored id.
        if not online.lookup.rematch:
            stored_id = self._stored_identifier(source.name)
            if stored_id is not None:
                logger.info(
                    f"online {source.name}: refreshing via stored id={stored_id}"
                )
                self._fetch_explicit_id(source, stored_id)
                return True

        # Series-first batching fast path (plan §3.10). When the session
        # has cached a resolved volume_id for this comic's series
        # fingerprint, skip the expensive search and ask the source
        # directly for "issue N in volume V." --rematch bypasses this
        # path too (consistent with its "don't trust prior verdict"
        # intent).
        if not online.lookup.rematch and self._try_series_cache_lookup(source):
            return True

        before = len(self._sources.get(source.metadata_source) or ())
        self._search_path(source)
        after = len(self._sources.get(source.metadata_source) or ())
        return after > before

    def _try_series_cache_lookup(self, source: OnlineSource) -> bool:  # noqa: PLR0911
        """
        Attempt the volume-scoped issue lookup; return True on hit + accept.

        Cache miss, source-side failure, or a stale-cache "issue not in
        this volume" response → return False so the caller falls through
        to the cold-path search. The cache entry is left alone in that
        case (first-writer-wins).
        """
        if self._series_cache is None:
            return False
        profile = self._build_profile()
        if not profile.series:
            return False
        key = (source.name, _series_fingerprint(profile))
        volume_id = self._series_cache.get(key)
        if volume_id is None:
            return False
        try:
            candidate = source.lookup_issue(volume_id, profile.issue)
        except NotImplementedError:
            # Source hasn't implemented the fast path — fall through.
            return False
        except Exception as exc:
            logger.warning(
                f"online {source.name}: series-cache lookup_issue "
                f"(volume_id={volume_id}, number={profile.issue!r}) "
                f"failed: {exc}; falling back to search"
            )
            return False
        if candidate is None:
            logger.info(
                f"online {source.name}: cached volume_id={volume_id} "
                f"returned no match for issue#={profile.issue!r}; "
                "falling back to search (cache entry preserved)"
            )
            return False
        logger.info(
            f"online {source.name}: series-cache hit; accepted "
            f"id={candidate.issue_id} via volume_id={volume_id}"
        )
        outcome_stats.record_auto_write(source.name)
        path = getattr(self, "_path", None)
        self._emit(
            AutoWritten(
                path=path,
                source=source.name,
                candidate_summary=str(candidate.issue_id),
            )
        )
        self._accept_candidate(source, candidate)
        return True

    def _first_normalized(self, src: MetadataSources) -> dict | None:
        """First normalized metadata dict from `src`, or None if unset."""
        normalized = self.get_normalized_metadata(src)
        if not normalized:
            return None
        for loaded in normalized:
            md = dict(loaded.metadata)
            if md:
                return md
        return None

    def _cross_source_cv_id_check(self) -> None:
        """
        Warn when Metron's stored `cv_id` and our CV match disagree.

        Runs once per box after both online sources have been queried.
        The check looks at the per-source normalized metadata (still
        distinguishable here, before the box-level merge collapses the
        two `comicbox.identifiers.comicvine.key` values into one). We
        don't decide which is right — just surface the disagreement so
        the user sees it before accepting.
        """
        metron_md = self._first_normalized(MetadataSources.METRON_API)
        cv_md = self._first_normalized(MetadataSources.COMICVINE_API)
        disagreement = _detect_cv_id_disagreement(metron_md, cv_md)
        if disagreement is None:
            return
        metron_id, cv_id = disagreement
        logger.warning(
            f"online: cross-source ComicVine id disagreement — Metron "
            f"stored cv_id={metron_id} but our independent ComicVine "
            f"match returned id={cv_id}. One of the two sources has the "
            f"wrong identifier; review before accepting."
        )

    def run_online_lookup(self) -> None:
        """Idempotent: populate online MetadataSources once per box instance."""
        if self._online_lookup_already_done():
            return
        self._mark_online_lookup_done()
        online = self._config.online
        path = getattr(self, "_path", None)
        if not online.lookup.enabled:
            return
        if online.lookup.prompts is not Prompts.NEVER:
            _no_tty_hint.maybe_log(has_callback=self._online_selector is not None)
        won_any = False
        for source in self._build_active_online_sources():
            # Explicit per-source flags always run — first-wins must not
            # silently drop a source the user named on the CLI.
            has_explicit = (
                source.name in online.lookup.ids
                or source.name in online.lookup.series_ids
            )
            if won_any and not online.lookup.all_sources and not has_explicit:
                logger.info(
                    f"online {source.name}: skipped (first-wins satisfied; "
                    f"use --tag-all-sources to query every source)"
                )
                continue
            if self._lookup_one_source(source):
                won_any = True
        self._cross_source_cv_id_check()
        self._emit(
            FileFinished(path=path, outcome="written" if won_any else "no_change")
        )
