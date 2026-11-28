"""Tests for OnlineSession running lookups through the box it opens per file."""

from __future__ import annotations

import sys
from dataclasses import replace
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest

from comicbox.box import Comicbox
from comicbox.box.online_lookup import ComicboxOnlineLookup
from comicbox.config.online.settings import MatchMode, Prompts
from comicbox.formats import MetadataFormats
from comicbox.formats.sources import MetadataSources
from comicbox.online_session import (
    OnlineConfigurationError,
    OnlineCredentials,
    OnlinePrompt,
    OnlineSession,
    PromptResponse,
)
from tests.util.online_matcher import make_candidate
from tests.util.online_session import SkipHandler

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from comicbox.formats.base.online.profile import Candidate

VALID_METRON = OnlineCredentials(metron_key="k")


# --- session-level prompt actions ----------------------------------------------
#
# The box applies these to the OnlineSessionState the session shares with
# it, so these go through the box's real `_apply_session_action` rather
# than a session-side mirror of it.


def _apply_via_box(
    session: OnlineSession, action: str, payload: int | str | None
) -> bool:
    """Run one selector action through the box that the session would spawn."""
    cb = Comicbox(config=session._settings)
    cb.set_online_session_state(session._state)
    return cb._apply_session_action("metron", action, payload)


def test_set_policy_via_handler_persists_across_files() -> None:
    """A handler's set_policy must outlive the in-flight file."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert _apply_via_box(session, "set_policy", "eager") is True
    assert session.match is MatchMode.EAGER


def test_set_prompts_via_handler_persists_across_files() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert _apply_via_box(session, "set_prompts", "never") is True
    assert session.prompts is Prompts.NEVER


def test_set_prompts_via_handler_is_reversible() -> None:
    """The action names its new value, so it goes back the way it came."""
    session = OnlineSession(
        sources={"metron"}, credentials=VALID_METRON, prompts=Prompts.NEVER
    )
    assert _apply_via_box(session, "set_prompts", "ask") is True
    assert session.prompts is Prompts.ASK


def test_set_policy_ask_persists() -> None:
    """ASK sticks when a selector asks for it, even where set_match would refuse."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert _apply_via_box(session, "set_policy", "ask") is True
    assert session.match is MatchMode.ASK
    with pytest.raises(OnlineConfigurationError):
        session.set_match(MatchMode.ASK)


def test_malformed_set_policy_declines_and_leaves_match() -> None:
    """Bad payloads are declined, loudly, and don't move the session."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert _apply_via_box(session, "set_policy", "bogus") is False
    assert session.match is MatchMode.AUTO
    assert _apply_via_box(session, "set_policy", 7) is False
    assert session.match is MatchMode.AUTO


def test_malformed_set_prompts_declines_and_leaves_prompts() -> None:
    """set_prompts validates its payload the same way set_policy does."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert _apply_via_box(session, "set_prompts", "bogus") is False
    assert session.prompts is Prompts.ASK
    assert _apply_via_box(session, "set_prompts", None) is False
    assert session.prompts is Prompts.ASK


# --- matched contract ----------------------------------------------------------


class _FakeBox:
    """Stand-in for Comicbox recording the wiring _run_one performs."""

    last: _FakeBox | None = None

    def __init__(self, path, config=None) -> None:
        self.selector = None
        self.session_state = None
        self.cluster_size = None
        self.won = type(self).next_won
        type(self).last = self

    next_won = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def set_online_selector(self, selector) -> None:
        self.selector = selector

    def set_event_handler(self, handler) -> None:
        pass

    def set_series_cache(self, cache) -> None:
        pass

    def set_series_cluster_size(self, size) -> None:
        self.cluster_size = size

    def set_retry_sleep(self, sleep) -> None:
        pass

    def set_online_session_state(self, state) -> None:
        self.session_state = state

    def run_online_lookup(self) -> bool:
        return self.won

    def to_dict(self) -> dict:
        return {"comicbox": {"series": "Existing Series"}}


@pytest.fixture
def fake_box(monkeypatch):
    import comicbox.online_session as mod

    monkeypatch.setattr(mod, "Comicbox", _FakeBox)
    _FakeBox.last = None
    _FakeBox.next_won = False
    return _FakeBox


def test_box_shares_the_session_state(tmp_path, fake_box) -> None:
    """The box gets the session's own state object, not a copy of it."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    session.tag(tmp_path / "f.cbz")
    assert fake_box.last.session_state is session._state


def test_unmatched_lookup_yields_matched_false(tmp_path, fake_box) -> None:
    """A lookup that applied nothing still carries tags but matched=False."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    result = session.tag(tmp_path / "f.cbz")
    assert result.error is None
    assert result.tags  # merged existing metadata is still returned
    assert result.matched is False


def test_matched_lookup_yields_matched_true(tmp_path, fake_box) -> None:
    fake_box.next_won = True
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    result = session.tag(tmp_path / "f.cbz")
    assert result.matched is True


def test_preloaded_resolution_installs_selector(tmp_path, fake_box) -> None:
    """A preload-only replay session (no handler, defer off) bridges the selector."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    session.tag(tmp_path / "f.cbz")
    assert fake_box.last is not None
    assert fake_box.last.selector is None  # nothing to consult — not installed
    session.preload_resolution(
        "metron|x|2026||(1,)", action="manual", payload="m:1", path=tmp_path / "f.cbz"
    )
    session.tag(tmp_path / "f.cbz")
    assert fake_box.last.selector is not None  # cache non-empty — installed


# --- ASK through the matcher ---------------------------------------------------
#
# A real box and matcher over a fake Metron whose one candidate is a sure
# thing. AUTO writes it unasked; ASK makes it the handler's call.

_PROFILE_METADATA = MappingProxyType(
    {
        "comicbox": {
            "series": {"name": "Foo Comics"},
            "issue": {"name": "5"},
            "date": {"year": 2020},
            "publisher": {"name": "Quality Comics"},
            "page_count": 24,
        }
    }
)


class _ConfidentMetron:
    """Fake source whose single candidate matches the profile exactly."""

    name = "metron"
    metadata_source = MetadataSources.METRON_API
    metadata_format = MetadataFormats.METRON_API

    def __init__(self, credentials, settings) -> None:
        self.get_calls: list[int] = []

    def is_configured(self) -> bool:
        return True

    def get(self, issue_id: int) -> dict:
        self.get_calls.append(issue_id)
        return {
            "id": issue_id,
            "number": "5",
            "cover_date": "2020-04-01",
            "modified": "2020-04-02T12:00:00Z",
            "publisher": {"id": 1, "name": "Quality Comics"},
            "series": {"id": 1, "name": "Foo Comics", "year_began": 2020, "volume": 1},
        }

    def search(self, profile) -> list[Candidate]:
        return [make_candidate(issue_id=101)]

    def enrich_prompt_candidates(self, candidates) -> tuple[Candidate, ...]:
        return tuple(candidates)


@pytest.fixture
def confident_metron(monkeypatch) -> list[_ConfidentMetron]:
    instances: list[_ConfidentMetron] = []

    def factory(creds, settings):
        src = _ConfidentMetron(creds, settings)
        instances.append(src)
        return src

    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType({"metron": factory}),
    )

    # The session opens a box on its file; hand the box the profile as
    # supplied metadata instead, so no archive is needed.
    def pathless_box(path, config):
        general = replace(config.general, metadata=_PROFILE_METADATA)
        return Comicbox(config=replace(config, general=general))

    monkeypatch.setattr("comicbox.online_session.Comicbox", pathless_box)
    return instances


def test_auto_writes_a_confident_match_unasked(tmp_path, confident_metron) -> None:
    handler = SkipHandler()
    session = OnlineSession(
        sources={"metron"}, credentials=VALID_METRON, prompt_handler=handler
    )
    result = session.tag(tmp_path / "f.cbz")
    assert result.error is None
    assert result.matched is True
    assert confident_metron[0].get_calls == [101]
    assert handler.prompts == []


def test_ask_prompts_a_confident_match_through_the_handler(
    tmp_path, confident_metron
) -> None:
    """Under ASK the sure thing is the handler's call, not the matcher's."""
    handler = SkipHandler()
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID_METRON,
        match=MatchMode.ASK,
        prompt_handler=handler,
    )
    result = session.tag(tmp_path / "f.cbz")
    assert result.error is None
    assert result.matched is False
    assert confident_metron[0].get_calls == []
    (prompt,) = handler.prompts
    assert prompt.match is MatchMode.ASK
    assert [c.issue_id for c in prompt.candidates] == [101]


def test_ask_defers_a_confident_match(tmp_path, confident_metron) -> None:
    """With deferred prompts, ASK queues the sure thing for review instead."""
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID_METRON,
        match=MatchMode.ASK,
        defer_prompts=True,
    )
    result = session.tag(tmp_path / "f.cbz")
    assert result.error is None
    assert result.matched is False
    assert confident_metron[0].get_calls == []
    (deferred,) = session.deferred_prompts()
    assert deferred.match is MatchMode.ASK
    assert [c.issue_id for c in deferred.candidates] == [101]


# --- a manual issue id answers one comic, end to end (A4 / F2) ----------------


class _SeriesMetron(_ConfidentMetron):
    """Offers two volumes' issue of the comic's own number, every time."""

    @override
    def search(self, profile) -> list[Candidate]:
        number = profile.issue
        return [
            make_candidate(issue_id=int(number) * 10 + 1, issue=number, volume_id=42),
            make_candidate(issue_id=int(number) * 10 + 2, issue=number, volume_id=43),
        ]


@pytest.fixture
def series_metron(monkeypatch) -> list[_SeriesMetron]:
    instances: list[_SeriesMetron] = []

    def factory(creds, settings):
        src = _SeriesMetron(creds, settings)
        instances.append(src)
        return src

    monkeypatch.setattr(
        ComicboxOnlineLookup,
        "_ONLINE_SOURCE_FACTORIES",
        MappingProxyType({"metron": factory}),
    )
    return instances


def _issue(tmp_path, number: int):
    from tests.util.comics import make_comic

    return make_comic(
        tmp_path / f"Foo Comics #00{number} (2020).cbz",
        series="Foo Comics",
        number=str(number),
        cover_date="2020-01-01",
    )


class _ManualOnceHandler:
    """Answers the first prompt with a typed issue id and skips the rest."""

    def __init__(self) -> None:
        self.asked: list[str | None] = []

    def request(self, prompt: OnlinePrompt) -> PromptResponse:
        self.asked.append(prompt.profile_summary["issue"])
        if len(self.asked) == 1:
            return PromptResponse("manual", "metron:111")
        return PromptResponse("skip", None)


def test_a_manual_id_tags_only_its_own_comic_through_tag_many(
    tmp_path, series_metron
) -> None:
    """
    Two issues of one series, both prompting with the same volumes.

    The handler types issue 111 for #1. #2 must be asked about itself,
    not be tagged with #1's issue.
    """
    paths = [_issue(tmp_path, 1), _issue(tmp_path, 2)]
    handler = _ManualOnceHandler()
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID_METRON,
        match=MatchMode.ASK,
        prompt_handler=handler,
    )

    results = {r.path.name: r for r in session.tag_many(paths)}

    assert handler.asked == ["1", "2"]
    assert [call for source in series_metron for call in source.get_calls] == [111]
    assert results["Foo Comics #001 (2020).cbz"].matched is True
    assert results["Foo Comics #002 (2020).cbz"].matched is False


def test_a_manual_preload_takes_a_str_path(tmp_path, series_metron) -> None:
    """F2: a str path was stored as given and never matched the box's Path."""
    path = _issue(tmp_path, 1)
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID_METRON,
        match=MatchMode.ASK,
        defer_prompts=True,
    )
    session.tag(path)
    (deferred,) = session.deferred_prompts()
    session.clear_deferred_prompts()

    session.preload_resolution(
        deferred.fingerprint, action="manual", payload="metron:111", path=str(path)
    )
    result = session.tag(path)

    assert session.deferred_prompts() == ()
    assert [call for source in series_metron for call in source.get_calls] == [111]
    assert result.matched is True
