"""Tests for OnlineSession scaffolding — validation, mode mapping, dispatch."""

from __future__ import annotations

import pytest

from comicbox.config.settings import MatchMode, Prompts
from comicbox.online_session import (
    OnlineConfigurationError,
    OnlineCredentials,
    OnlinePrompt,
    OnlineSession,
    PromptResponse,
)

VALID_METRON = OnlineCredentials(metron_user="u", metron_password="p")
VALID_COMICVINE = OnlineCredentials(comicvine_key="k")
VALID_BOTH = OnlineCredentials(metron_user="u", metron_password="p", comicvine_key="k")


# --- validation ---------------------------------------------------------------


def test_construct_with_valid_creds() -> None:
    """Construction works when every enabled source has its required fields."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert session.mode is MatchMode.AUTO
    assert session.unattended is False
    assert session.cancelled is False


def test_rejects_unknown_source() -> None:
    with pytest.raises(OnlineConfigurationError, match="Unknown online sources"):
        OnlineSession(sources={"mystery"}, credentials=VALID_BOTH)


def test_rejects_empty_sources() -> None:
    with pytest.raises(OnlineConfigurationError, match="at least one source"):
        OnlineSession(sources=set(), credentials=VALID_BOTH)


def test_rejects_metron_without_creds() -> None:
    with pytest.raises(OnlineConfigurationError, match="metron requires"):
        OnlineSession(sources={"metron"}, credentials=OnlineCredentials())


def test_rejects_comicvine_without_key() -> None:
    with pytest.raises(OnlineConfigurationError, match="comicvine requires"):
        OnlineSession(sources={"comicvine"}, credentials=VALID_METRON)


def test_rejects_non_enum_mode() -> None:
    with pytest.raises(OnlineConfigurationError, match="must be a MatchMode"):
        OnlineSession(
            sources={"metron"},
            credentials=VALID_METRON,
            mode="normal",  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
        )


def test_rejects_ask_mode() -> None:
    with pytest.raises(OnlineConfigurationError, match=r"MatchMode\.ASK"):
        OnlineSession(
            sources={"metron"},
            credentials=VALID_METRON,
            mode=MatchMode.ASK,
        )


# --- mode propagation ---------------------------------------------------------


@pytest.mark.parametrize(
    "mode",
    [MatchMode.CAREFUL, MatchMode.AUTO, MatchMode.EAGER],
)
def test_mode_propagates_to_match_setting(mode: MatchMode) -> None:
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID_METRON,
        mode=mode,
    )
    cfg = session._build_config()
    assert cfg.online.lookup.match is mode


def test_unattended_maps_to_prompts_never() -> None:
    session = OnlineSession(
        sources={"metron"}, credentials=VALID_METRON, unattended=True
    )
    cfg = session._build_config()
    assert cfg.online.lookup.prompts == Prompts.NEVER


def test_set_mode_changes_subsequent_config() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert session._build_config().online.lookup.match == MatchMode.AUTO
    session.set_mode(MatchMode.EAGER)
    assert session._build_config().online.lookup.match == MatchMode.EAGER


def test_set_unattended_changes_subsequent_config() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert session._build_config().online.lookup.prompts == Prompts.ASK
    session.set_unattended(unattended=True)
    assert session._build_config().online.lookup.prompts == Prompts.NEVER


# --- credential propagation ---------------------------------------------------


def test_credentials_propagate_into_settings() -> None:
    creds = OnlineCredentials(
        metron_user="alice",
        metron_password="secret",
        metron_url="https://m",
        comicvine_key="cv-key",
        comicvine_url="https://cv",
    )
    session = OnlineSession(sources={"metron", "comicvine"}, credentials=creds)
    cfg = session._build_config()
    m = cfg.online.auth.sources["metron"]
    assert m.user == "alice"
    assert m.password == "secret"
    assert m.url == "https://m"
    cv = cfg.online.auth.sources["comicvine"]
    assert cv.key == "cv-key"
    assert cv.url == "https://cv"


def test_only_enabled_sources_appear_in_auth() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    cfg = session._build_config()
    assert "metron" in cfg.online.auth.sources
    assert "comicvine" not in cfg.online.auth.sources


# --- cancellation -------------------------------------------------------------


def test_cancel_skips_subsequent_files(tmp_path) -> None:
    """tag_many() yields cancelled OnlineResults for paths after cancel()."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    fake_paths = [tmp_path / f"f{i}.cbz" for i in range(3)]
    session.cancel()
    results = list(session.tag_many(fake_paths))
    assert len(results) == 3
    assert all(r.cancelled for r in results)
    assert all(r.tags is None for r in results)


def test_abort_from_lookup_cancels_the_batch(tmp_path, monkeypatch) -> None:
    """An 'abort' answer aborts the entire run, not just the current file."""
    from comicbox.box.online_lookup import OnlineLookupAbortedError

    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)

    def raise_abort(self, path):
        msg = "online: aborted by user from prompt"
        raise OnlineLookupAbortedError(msg)

    monkeypatch.setattr(OnlineSession, "_run_one", raise_abort)
    paths = [tmp_path / f"f{i}.cbz" for i in range(3)]
    results = list(session.tag_many(paths))
    assert len(results) == 3
    # The aborting file and every later file come back cancelled, not errored.
    assert all(r.cancelled for r in results)
    assert all(r.error is None for r in results)
    assert session.cancelled is True


def test_retry_sleep_wait_aborts_when_cancelled() -> None:
    """The wired retry sleep aborts the in-flight lookup on cancel()."""
    from comicbox.box.online_lookup import OnlineLookupAbortedError

    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    session.cancel()
    with pytest.raises(OnlineLookupAbortedError):
        session._retry_sleep_wait(0.01)


def test_retry_sleep_wait_passes_when_not_cancelled() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    session._retry_sleep_wait(0.001)  # waits out the delay, no exception


# --- session-level prompt actions ----------------------------------------------


def test_set_policy_via_handler_persists_across_files() -> None:
    """A handler's set_policy must outlive the in-flight file's config."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    session._sync_session_state(PromptResponse(action="set_policy", payload="eager"))
    assert session.mode is MatchMode.EAGER
    assert session._build_config().online.lookup.match == MatchMode.EAGER


def test_set_unattended_via_handler_persists_across_files() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    session._sync_session_state(PromptResponse(action="set_unattended", payload=None))
    assert session.unattended is True
    assert session._build_config().online.lookup.prompts == Prompts.NEVER


def test_sync_session_state_ignores_malformed_or_ask_policy() -> None:
    """Bad payloads and ASK (rejected by set_mode) must not raise or stick."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    session._sync_session_state(PromptResponse(action="set_policy", payload="bogus"))
    assert session.mode is MatchMode.AUTO
    session._sync_session_state(PromptResponse(action="set_policy", payload="ask"))
    assert session.mode is MatchMode.AUTO
    session._sync_session_state(PromptResponse(action="choose", payload=0))
    assert session.mode is MatchMode.AUTO


# --- prompt-handler bridging --------------------------------------------------


def test_prompt_handler_protocol_compiles() -> None:
    """A minimal handler instance satisfies the Protocol structurally."""

    class _H:
        def request(self, prompt: OnlinePrompt) -> PromptResponse:
            return PromptResponse(action="skip", payload=None)

    # No assertion needed — type compatibility is checked at construction.
    OnlineSession(
        sources={"metron"},
        credentials=VALID_METRON,
        prompt_handler=_H(),
    )


def test_batched_prompt_handler_protocol_recognized() -> None:
    """BatchedPromptHandler is runtime-checkable; an implementer matches."""
    from comicbox.online_session import BatchedPromptHandler

    class _BH:
        def request(self, prompt: OnlinePrompt) -> PromptResponse:
            return PromptResponse(action="skip")

        def request_many(self, prompts):
            return [PromptResponse(action="skip") for _ in prompts]

    handler = _BH()
    assert isinstance(handler, BatchedPromptHandler)
    # Still accepted by OnlineSession via the base PromptHandler shape.
    OnlineSession(sources={"metron"}, credentials=VALID_METRON, prompt_handler=handler)


# --- matched contract ----------------------------------------------------------


class _FakeBox:
    """Stand-in for Comicbox recording the wiring _run_one performs."""

    last: _FakeBox | None = None

    def __init__(self, path, config=None) -> None:
        self.selector = None
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

    def set_retry_sleep(self, sleep) -> None:
        pass

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
    session.preload_resolution("metron|x|2026||(1,)", action="manual", payload="m:1")
    session.tag(tmp_path / "f.cbz")
    assert fake_box.last.selector is not None  # cache non-empty — installed


# --- rate-limit status stub ---------------------------------------------------


def test_rate_limit_status_stub_returns_known_sources() -> None:
    """v1 stub: returns an empty bucket per enabled source."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    status = session.rate_limit_status()
    assert set(status) == {"metron"}
