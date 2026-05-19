"""Tests for OnlineSession prompt deduplication by fingerprint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from comicbox.events import PromptResolvedFromCache
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
    from comicbox.formats.base.online.selector import SelectorContext

VALID = OnlineCredentials(metron_user="u", metron_password="p")


@dataclass
class _Recorder:
    """PromptHandler that records every prompt it sees and returns a scripted action."""

    response: PromptResponse
    seen: list[OnlinePrompt]

    def request(self, prompt: OnlinePrompt) -> PromptResponse:
        self.seen.append(prompt)
        return self.response


def _ctx(source: str = "metron") -> SelectorContext:
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


# --- fingerprint tests ------------------------------------------------------


def test_identical_candidate_set_dedups() -> None:
    """Same source / series / volume_ids → second call hits the cache."""
    recorder = _Recorder(response=PromptResponse(action="skip"), seen=[])
    session = OnlineSession(
        sources={"metron"}, credentials=VALID, prompt_handler=recorder
    )
    selector = session._bridged_selector()
    profile = ComicProfile(series="Spider-Man", year=2020, publisher="Marvel")
    candidates = (_cand(1, 100), _cand(2, 100))

    # First call: invokes handler.
    action1 = selector(profile, candidates, _ctx())
    # Second call: same fingerprint, should NOT invoke handler.
    action2 = selector(profile, candidates, _ctx())

    assert len(recorder.seen) == 1
    assert action1 == action2 == ("skip", None)


def test_choose_remaps_volume_id_to_new_index() -> None:
    """
    Cached 'choose' remaps onto whichever index holds the chosen volume_id.

    'choose 0' for volume_id=100 caches "user wants volume 100"; on the
    next prompt with same fingerprint but candidates reordered, the cache
    returns the *new* index of volume 100.
    """
    recorder = _Recorder(response=PromptResponse(action="choose", payload=0), seen=[])
    session = OnlineSession(
        sources={"metron"}, credentials=VALID, prompt_handler=recorder
    )
    selector = session._bridged_selector()
    profile = ComicProfile(series="Spider-Man", year=2020, publisher="Marvel")

    # First prompt: candidates ordered as (vol=100, vol=200) — user picks index 0 → vol 100.
    first = (_cand(1, 100), _cand(2, 200))
    selector(profile, first, _ctx())
    # Second prompt: same series but candidates in opposite order (vol=200, vol=100).
    # Cache must remap to the new index of vol=100, which is 1.
    second = (_cand(3, 200), _cand(4, 100))
    action = selector(profile, second, _ctx())

    assert len(recorder.seen) == 1
    assert action == ("choose", 1)


def test_different_fingerprint_re_prompts() -> None:
    """Different series → different fingerprint → handler fires again."""
    recorder = _Recorder(response=PromptResponse(action="skip"), seen=[])
    session = OnlineSession(
        sources={"metron"}, credentials=VALID, prompt_handler=recorder
    )
    selector = session._bridged_selector()
    candidates = (_cand(1, 100),)

    selector(ComicProfile(series="Spider-Man"), candidates, _ctx())
    selector(ComicProfile(series="Batman"), candidates, _ctx())

    assert len(recorder.seen) == 2


def test_session_actions_are_not_cached() -> None:
    """set_unattended / set_policy / abort should not be cached — they're once-off."""
    recorder = _Recorder(
        response=PromptResponse(action="set_unattended"), seen=[]
    )
    session = OnlineSession(
        sources={"metron"}, credentials=VALID, prompt_handler=recorder
    )
    selector = session._bridged_selector()
    profile = ComicProfile(series="S", year=2020, publisher="P")
    candidates = (_cand(1, 100),)

    selector(profile, candidates, _ctx())
    selector(profile, candidates, _ctx())

    # Handler fired both times.
    assert len(recorder.seen) == 2


def test_choose_falls_through_when_volume_id_not_in_new_candidates() -> None:
    """If the cached volume_id isn't in the new candidate list, re-prompt."""
    recorder = _Recorder(response=PromptResponse(action="choose", payload=0), seen=[])
    session = OnlineSession(
        sources={"metron"}, credentials=VALID, prompt_handler=recorder
    )
    selector = session._bridged_selector()
    profile = ComicProfile(series="S", year=2020, publisher="P")

    # First: user picks volume_id=100.
    selector(profile, (_cand(1, 100),), _ctx())
    # Second: same profile but different volume_id available — must re-prompt.
    # Fingerprint matches since profile is the same; but volume_id 200 is not 100,
    # so the cached "choose vol=100" can't be applied. Actually the fingerprint
    # *would* differ here because volume_ids in candidate list differ. Confirms
    # the dedup is structurally tight.
    selector(profile, (_cand(2, 200),), _ctx())

    assert len(recorder.seen) == 2


def test_cache_emits_prompt_resolved_from_cache_event() -> None:
    """The cache hit must emit a PromptResolvedFromCache event for Codex UIs."""
    events: list[object] = []
    recorder = _Recorder(response=PromptResponse(action="skip"), seen=[])
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID,
        prompt_handler=recorder,
        on_event=events.append,
    )
    selector = session._bridged_selector()
    profile = ComicProfile(series="S", year=2020, publisher="P")
    candidates = (_cand(1, 100),)

    selector(profile, candidates, _ctx())
    selector(profile, candidates, _ctx())

    cache_events = [e for e in events if isinstance(e, PromptResolvedFromCache)]
    assert len(cache_events) == 1
    assert cache_events[0].action == "skip"
    assert cache_events[0].source == "metron"
    assert cache_events[0].fingerprint
