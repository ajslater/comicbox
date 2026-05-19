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
    assert session.mode == "normal"
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


def test_rejects_unknown_mode() -> None:
    with pytest.raises(OnlineConfigurationError, match="Unknown mode"):
        OnlineSession(
            sources={"metron"},
            credentials=VALID_METRON,
            mode="aggressive",  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
        )


# --- mode + alias mapping -----------------------------------------------------


@pytest.mark.parametrize(
    ("session_mode", "expected_match"),
    [
        ("strict", MatchMode.CAREFUL),
        ("normal", MatchMode.AUTO),
        ("fast", MatchMode.EAGER),
    ],
)
def test_mode_maps_to_match_mode(session_mode: str, expected_match: MatchMode) -> None:
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID_METRON,
        mode=session_mode,  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
    )
    cfg = session._build_config()
    assert cfg.online.lookup.match == expected_match


def test_unattended_maps_to_prompts_never() -> None:
    session = OnlineSession(
        sources={"metron"}, credentials=VALID_METRON, unattended=True
    )
    cfg = session._build_config()
    assert cfg.online.lookup.prompts == Prompts.NEVER


def test_set_mode_changes_subsequent_config() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert session._build_config().online.lookup.match == MatchMode.AUTO
    session.set_mode("fast")
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


# --- rate-limit status stub ---------------------------------------------------


def test_rate_limit_status_stub_returns_known_sources() -> None:
    """v1 stub: returns an empty bucket per enabled source."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    status = session.rate_limit_status()
    assert set(status) == {"metron"}
