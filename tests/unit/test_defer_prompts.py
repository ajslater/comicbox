"""Tests for OnlineSession defer-prompts mode."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

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

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

VALID = OnlineCredentials(metron_key="k")


def _ctx(
    source: str = "metron",
    enrich: Callable[[Sequence[Candidate]], tuple[Candidate, ...]] = tuple,
    file_path: Path | None = None,
):
    from comicbox.config import get_config
    from comicbox.formats.base.online.selector import SelectorContext

    return SelectorContext(
        file_path=file_path,
        source=source,
        settings=get_config(),
        triggered_hashing=False,
        enrich_candidates=enrich,
    )


class _Enricher:
    """Stand-in for a source's hook: tags every summary, counts its calls."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, candidates) -> tuple[Candidate, ...]:
        self.calls += 1
        return tuple(
            replace(c, summary=replace(c.summary, series_type="Trade Paperback"))
            for c in candidates
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
    profile = ComicProfile(series="Snail-Man", year=2020, publisher="Marvel")
    candidates = (_cand(1, 100), _cand(2, 200))

    result = selector(profile, candidates, _ctx())

    assert result == ("skip", None)
    deferred = session.deferred_prompts()
    assert len(deferred) == 1
    d = deferred[0]
    assert d.source == "metron"
    assert d.candidates == candidates
    assert d.profile_summary["series"] == "Snail-Man"
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
    profile = ComicProfile(series="Bladehawk", year=2018, publisher="DC")
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
    profile = ComicProfile(series="Snail-Man", year=2020, publisher="Marvel")
    cands = (_cand(1, 100),)

    # Defer-mode: handler not called.
    selector(profile, cands, _ctx())
    assert seen == []
    assert len(session.deferred_prompts()) == 1

    # Toggle off, different fingerprint to avoid cache.
    session.set_defer_prompts(defer=False)
    selector(ComicProfile(series="Bladehawk"), cands, _ctx())
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


def test_a_deferred_prompt_holds_enriched_candidates() -> None:
    """What the embedder shows is what the source's hook added."""
    session = OnlineSession(sources={"metron"}, credentials=VALID, defer_prompts=True)
    selector = session._bridged_selector()
    enrich = _Enricher()
    cands = (_cand(1, 100), _cand(2, 200))

    selector(ComicProfile(series="S", year=2020), cands, _ctx(enrich=enrich))

    [deferred] = session.deferred_prompts()
    assert enrich.calls == 1
    assert [c.summary.series_type for c in deferred.candidates] == [
        "Trade Paperback",
        "Trade Paperback",
    ]
    # Enrichment touches display fields only; the fingerprint keys on ids.
    assert [c.volume_id for c in deferred.candidates] == [100, 200]


def test_a_shown_prompt_holds_enriched_candidates() -> None:
    seen: list[OnlinePrompt] = []

    class _H:
        def request(self, prompt: OnlinePrompt) -> PromptResponse:
            seen.append(prompt)
            return PromptResponse(action="skip")

    session = OnlineSession(sources={"metron"}, credentials=VALID, prompt_handler=_H())
    selector = session._bridged_selector()

    selector(ComicProfile(series="S"), (_cand(1, 100),), _ctx(enrich=_Enricher()))

    [prompt] = seen
    assert prompt.candidates[0].summary.series_type == "Trade Paperback"


def test_a_prompt_answered_from_cache_spends_nothing_on_enrichment() -> None:
    """Codex's re-run after a pick must not repeat the series lookups."""
    session = OnlineSession(sources={"metron"}, credentials=VALID, defer_prompts=True)
    selector = session._bridged_selector()
    profile = ComicProfile(series="S", year=2020, publisher="P")
    cands = (_cand(1, 100), _cand(2, 200))
    selector(profile, cands, _ctx())
    fingerprint = session.deferred_prompts()[0].fingerprint
    session.preload_resolution(
        fingerprint, action="choose", payload=0, chosen_volume_id=100
    )
    enrich = _Enricher()

    result = selector(profile, cands, _ctx(enrich=enrich))

    assert result == ("choose", 0)
    assert enrich.calls == 0


# --- a manual issue id belongs to one file ------------------------------------
#
# Every issue of a series shares a prompt fingerprint, so anything cached
# under it replays onto the next issue. A volume pick ("choose") and a
# "skip" are series decisions; a typed issue id is not.


class _Recorder:
    """PromptHandler that answers from a script and records each prompt."""

    def __init__(self, *responses: PromptResponse) -> None:
        self._responses = list(responses)
        self.issues: list[str | None] = []

    def request(self, prompt: OnlinePrompt) -> PromptResponse:
        self.issues.append(prompt.profile_summary["issue"])
        return self._responses.pop(0)


def _series_issue(number: str) -> tuple[ComicProfile, tuple[Candidate, ...]]:
    """One issue of a series whose prompt offers the same two volumes."""
    profile = ComicProfile(series="S", issue=number, year=2020, publisher="P")
    base = int(number) * 10
    return profile, (_cand(base + 1, 100), _cand(base + 2, 200))


def test_a_manual_answer_is_asked_again_for_the_next_issue() -> None:
    """A manual id typed for #1 is not replayed onto #2 of the same series."""
    handler = _Recorder(
        PromptResponse("manual", "metron:111"),
        PromptResponse("manual", "metron:222"),
    )
    session = OnlineSession(
        sources={"metron"}, credentials=VALID, prompt_handler=handler
    )
    selector = session._bridged_selector()

    first = selector(*_series_issue("1"), _ctx(file_path=Path("1.cbz")))
    second = selector(*_series_issue("2"), _ctx(file_path=Path("2.cbz")))

    assert handler.issues == ["1", "2"]
    assert first == ("manual", "metron:111")
    assert second == ("manual", "metron:222")


def test_a_chosen_volume_replays_onto_the_next_issue() -> None:
    """A volume pick still answers every later issue of the series."""
    handler = _Recorder(PromptResponse("choose", 1))
    session = OnlineSession(
        sources={"metron"}, credentials=VALID, prompt_handler=handler
    )
    selector = session._bridged_selector()
    selector(*_series_issue("1"), _ctx())

    # #2's candidates offer the same volumes in the other order.
    profile, (vol_100, vol_200) = _series_issue("2")
    result = selector(profile, (vol_200, vol_100), _ctx())

    assert handler.issues == ["1"]
    assert result == ("choose", 0)  # volume 200, wherever it now sits


def test_a_skip_replays_onto_the_next_issue() -> None:
    handler = _Recorder(PromptResponse("skip", None))
    session = OnlineSession(
        sources={"metron"}, credentials=VALID, prompt_handler=handler
    )
    selector = session._bridged_selector()
    selector(*_series_issue("1"), _ctx())

    result = selector(*_series_issue("2"), _ctx())

    assert handler.issues == ["1"]
    assert result == ("skip", None)


def test_a_manual_preload_answers_only_its_own_file() -> None:
    """A per-file manual preload resolves that file; a sibling is deferred."""
    session = OnlineSession(sources={"metron"}, credentials=VALID, defer_prompts=True)
    selector = session._bridged_selector()
    selector(*_series_issue("1"), _ctx(file_path=Path("1.cbz")))
    fingerprint = session.deferred_prompts()[0].fingerprint
    session.clear_deferred_prompts()

    session.preload_resolution(
        fingerprint, action="manual", payload="metron:111", path=Path("1.cbz")
    )

    own = selector(*_series_issue("1"), _ctx(file_path=Path("1.cbz")))
    sibling = selector(*_series_issue("2"), _ctx(file_path=Path("2.cbz")))

    assert own == ("manual", "metron:111")
    assert sibling == ("skip", None)
    assert [d.path for d in session.deferred_prompts()] == [Path("2.cbz")]


def test_a_manual_preload_without_a_file_is_refused() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID, defer_prompts=True)
    with pytest.raises(ValueError, match="path"):
        session.preload_resolution("fp", action="manual", payload="metron:111")


def test_a_series_preload_with_a_file_is_refused() -> None:
    """A path keys a manual preload only; a series answer takes none."""
    session = OnlineSession(sources={"metron"}, credentials=VALID, defer_prompts=True)
    with pytest.raises(ValueError, match="manual"):
        session.preload_resolution(
            "fp", action="skip", payload=None, path=Path("1.cbz")
        )


def test_a_series_choice_and_a_files_manual_preload_coexist() -> None:
    """The per-file manual wins for its file; the series choice answers the rest."""
    handler = _Recorder(PromptResponse("choose", 1))
    session = OnlineSession(
        sources={"metron"}, credentials=VALID, prompt_handler=handler
    )
    selector = session._bridged_selector()
    selector(*_series_issue("1"), _ctx(file_path=Path("1.cbz")))
    fingerprint = _prompt_fingerprint_of("2")

    session.preload_resolution(
        fingerprint, action="manual", payload="metron:222", path=Path("2.cbz")
    )

    assert selector(*_series_issue("2"), _ctx(file_path=Path("2.cbz"))) == (
        "manual",
        "metron:222",
    )
    assert selector(*_series_issue("3"), _ctx(file_path=Path("3.cbz"))) == (
        "choose",
        1,
    )
    assert handler.issues == ["1"]


def _prompt_fingerprint_of(number: str) -> str:
    from comicbox.online_session import _prompt_fingerprint

    profile, candidates = _series_issue(number)
    return _prompt_fingerprint("metron", profile, candidates)
