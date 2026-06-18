"""Tests for OnlineSession defer-prompts mode."""

from __future__ import annotations

from comicbox.events import PromptDeferred, PromptResolvedFromCache
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    ComicProfile,
)
from comicbox.online_session import (
    OnlineCredentials,
    OnlinePrompt,
    OnlineSession,
    PromptResponse,
)

VALID = OnlineCredentials(metron_user="u", metron_password="p")


def _ctx(source: str = "metron"):
    from comicbox.config import get_config
    from comicbox.formats.base.online.selector import SelectorContext

    return SelectorContext(
        file_path=None, source=source, settings=get_config(), triggered_hashing=False
    )


def _cand(issue_id: int, volume_id: int | None) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=issue_id,
        summary=CandidateSummary(
            series="S",
            issue=str(issue_id),
            year=2020,
            publisher="P",
            page_count=24,
            cover_url=None,
            variant_label=None,
        ),
        volume_id=volume_id,
    )


def test_defer_mode_queues_prompt_and_returns_skip() -> None:
    """Under defer_prompts, the selector queues + returns ('skip', None)."""
    session = OnlineSession(sources={"metron"}, credentials=VALID, defer_prompts=True)
    selector = session._bridged_selector()
    profile = ComicProfile(series="Spider-Man", year=2020, publisher="Marvel")
    candidates = (_cand(1, 100), _cand(2, 200))

    result = selector(profile, candidates, _ctx())

    assert result == ("skip", None)
    deferred = session.deferred_prompts()
    assert len(deferred) == 1
    d = deferred[0]
    assert d.source == "metron"
    assert d.candidates == candidates
    assert d.profile_summary["series"] == "Spider-Man"
    assert d.fingerprint  # non-empty


def test_defer_mode_emits_prompt_deferred_event() -> None:
    """PromptDeferred event fires on each queue, with fingerprint + n_candidates."""
    events: list = []
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID,
        defer_prompts=True,
        on_event=events.append,
    )
    selector = session._bridged_selector()
    profile = ComicProfile(series="Batman", year=2018, publisher="DC")
    candidates = (_cand(10, 999),)

    selector(profile, candidates, _ctx())

    deferred_events = [e for e in events if isinstance(e, PromptDeferred)]
    assert len(deferred_events) == 1
    assert deferred_events[0].source == "metron"
    assert deferred_events[0].n_candidates == 1
    assert deferred_events[0].fingerprint


def test_defer_mode_works_without_prompt_handler() -> None:
    """Defer mode does not require a PromptHandler — that's its whole point."""
    session = OnlineSession(sources={"metron"}, credentials=VALID, defer_prompts=True)
    assert session._prompt_handler is None
    selector = session._bridged_selector()
    selector(
        ComicProfile(series="S", year=2020, publisher="P"),
        (_cand(1, 100),),
        _ctx(),
    )
    assert len(session.deferred_prompts()) == 1


def test_preload_resolution_seeds_cache_for_re_run() -> None:
    """preload_resolution() makes the next prompt with that fingerprint cache-hit."""
    session = OnlineSession(sources={"metron"}, credentials=VALID, defer_prompts=True)
    selector = session._bridged_selector()
    profile = ComicProfile(series="S", year=2020, publisher="P")
    candidates = (_cand(1, 100), _cand(2, 200))

    # First pass: deferred.
    selector(profile, candidates, _ctx())
    deferred = session.deferred_prompts()
    fingerprint = deferred[0].fingerprint

    # Codex resolves it: user picked volume_id 100.
    session.preload_resolution(
        fingerprint, action="choose", payload=0, chosen_volume_id=100
    )

    # Re-run: should cache-hit and return ("choose", 0).
    result = selector(profile, candidates, _ctx())
    assert result == ("choose", 0)


def test_preload_resolution_remaps_index_on_re_run() -> None:
    """preload_resolution with chosen_volume_id maps to the new candidate index."""
    session = OnlineSession(sources={"metron"}, credentials=VALID, defer_prompts=True)
    selector = session._bridged_selector()
    profile = ComicProfile(series="S", year=2020, publisher="P")

    # First pass: vol 100 at index 0.
    selector(profile, (_cand(1, 100), _cand(2, 200)), _ctx())
    fp = session.deferred_prompts()[0].fingerprint
    session.preload_resolution(fp, action="choose", payload=0, chosen_volume_id=100)

    # Re-run with candidates re-ordered — vol 100 is now at index 1.
    result = selector(profile, (_cand(3, 200), _cand(4, 100)), _ctx())
    assert result == ("choose", 1)


def test_clear_deferred_prompts_empties_queue() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID, defer_prompts=True)
    selector = session._bridged_selector()
    selector(
        ComicProfile(series="S", year=2020, publisher="P"),
        (_cand(1, 100),),
        _ctx(),
    )
    assert len(session.deferred_prompts()) == 1
    session.clear_deferred_prompts()
    assert session.deferred_prompts() == ()


def test_set_defer_prompts_toggles_at_runtime() -> None:
    """set_defer_prompts(defer=False) restores normal handler invocation."""
    seen: list[OnlinePrompt] = []

    class _H:
        def request(self, prompt: OnlinePrompt) -> PromptResponse:
            seen.append(prompt)
            return PromptResponse(action="skip")

    session = OnlineSession(
        sources={"metron"},
        credentials=VALID,
        prompt_handler=_H(),
        defer_prompts=True,
    )
    selector = session._bridged_selector()
    profile = ComicProfile(series="Spider-Man", year=2020, publisher="Marvel")
    cands = (_cand(1, 100),)

    # Defer-mode: handler not called.
    selector(profile, cands, _ctx())
    assert seen == []
    assert len(session.deferred_prompts()) == 1

    # Toggle off, different fingerprint to avoid cache.
    session.set_defer_prompts(defer=False)
    selector(ComicProfile(series="Batman"), cands, _ctx())
    assert len(seen) == 1


def test_dedup_still_short_circuits_in_defer_mode() -> None:
    """Cache hits still work in defer mode — no double-queueing on the second call."""
    events: list = []
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID,
        defer_prompts=True,
        on_event=events.append,
    )
    selector = session._bridged_selector()
    profile = ComicProfile(series="S", year=2020, publisher="P")
    cands = (_cand(1, 100),)

    selector(profile, cands, _ctx())
    fp = session.deferred_prompts()[0].fingerprint
    session.preload_resolution(fp, action="skip", payload=None)

    # Second call with same fingerprint must hit the cache, not queue again.
    selector(profile, cands, _ctx())

    deferred_events = [e for e in events if isinstance(e, PromptDeferred)]
    cache_events = [e for e in events if isinstance(e, PromptResolvedFromCache)]
    assert len(deferred_events) == 1
    assert len(cache_events) == 1
    # Queue size unchanged — only one entry total.
    assert len(session.deferred_prompts()) == 1
