"""Tests for OnlineSession scaffolding — validation, mode mapping, dispatch."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from comicbox.config import get_config
from comicbox.config.online.settings import Effort, MatchMode, Prompts
from comicbox.online_session import (
    OnlineConfigurationError,
    OnlineCredentials,
    OnlinePrompt,
    OnlineSession,
    PromptResponse,
    SourceAttribution,
    source_attribution,
)
from tests.util.online_session import SkipHandler

VALID_METRON = OnlineCredentials(metron_key="k")
VALID_COMICVINE = OnlineCredentials(comicvine_key="k")
VALID_BOTH = OnlineCredentials(metron_key="k", comicvine_key="k")
VALID_VERSEDB = OnlineCredentials(versedb_key="versedb-token")


# --- validation ---------------------------------------------------------------


def test_construct_with_valid_creds() -> None:
    """Construction works when every enabled source has its required fields."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert session.match is MatchMode.AUTO
    assert session.prompts is Prompts.ASK
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


def test_rejects_non_enum_match() -> None:
    with pytest.raises(OnlineConfigurationError, match="must be a MatchMode"):
        OnlineSession(
            sources={"metron"},
            credentials=VALID_METRON,
            match="normal",  # pyright: ignore[reportArgumentType], # ty: ignore[invalid-argument-type]
        )


def test_rejects_ask_match_without_a_prompt_resolver() -> None:
    """ASK prompts for every match, so it needs somewhere to send them."""
    with pytest.raises(
        OnlineConfigurationError,
        match="no prompt_handler is set and defer_prompts is off",
    ):
        OnlineSession(
            sources={"metron"},
            credentials=VALID_METRON,
            match=MatchMode.ASK,
        )


def test_accepts_ask_match_with_a_prompt_handler() -> None:
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID_METRON,
        match=MatchMode.ASK,
        prompt_handler=SkipHandler(),
    )
    assert session.match is MatchMode.ASK


def test_accepts_ask_match_with_deferred_prompts() -> None:
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID_METRON,
        match=MatchMode.ASK,
        defer_prompts=True,
    )
    assert session.match is MatchMode.ASK


# --- pinned ids ---------------------------------------------------------------


def test_ids_default_to_empty() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert session._build_config().online.lookup.ids == {}


def test_ids_propagate_to_lookup_settings() -> None:
    """A pinned id per source reaches the per-file lookup settings."""
    session = OnlineSession(
        sources=("metron", "comicvine"),
        ids={"metron": 123},
        credentials=VALID_BOTH,
    )
    cfg = session._build_config()
    assert cfg.online.lookup.ids == {"metron": 123}
    # The unpinned source still runs; it just has no id to fetch.
    assert cfg.online.lookup.sources == ("metron", "comicvine")


def test_rejects_ids_for_a_source_not_in_the_session() -> None:
    with pytest.raises(OnlineConfigurationError, match="not in this session"):
        OnlineSession(
            sources=("metron",), ids={"comicvine": 456}, credentials=VALID_METRON
        )


# --- mode propagation ---------------------------------------------------------


@pytest.mark.parametrize(
    "match",
    [MatchMode.CAREFUL, MatchMode.AUTO, MatchMode.EAGER],
)
def test_match_propagates_to_match_setting(match: MatchMode) -> None:
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID_METRON,
        match=match,
    )
    assert session._settings.online.lookup.match is match


def test_prompts_propagates_to_prompts_setting() -> None:
    session = OnlineSession(
        sources={"metron"}, credentials=VALID_METRON, prompts=Prompts.NEVER
    )
    assert session._settings.online.lookup.prompts == Prompts.NEVER


def _live_lookup(session: OnlineSession):
    """Resolve what a box spawned by this session would look up under now."""
    return session._state.overlay(session._settings.online).lookup


def test_set_match_changes_subsequent_lookups() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert _live_lookup(session).match == MatchMode.AUTO
    session.set_match(MatchMode.EAGER)
    assert _live_lookup(session).match == MatchMode.EAGER


def test_set_match_ask_needs_a_prompt_resolver() -> None:
    """set_match applies the constructor's ASK rule to the live resolvers."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    with pytest.raises(OnlineConfigurationError, match="defer_prompts is off"):
        session.set_match(MatchMode.ASK)
    assert _live_lookup(session).match is MatchMode.AUTO
    session.set_defer_prompts(defer=True)
    session.set_match(MatchMode.ASK)
    assert _live_lookup(session).match is MatchMode.ASK


def test_set_match_ask_accepted_with_a_prompt_handler() -> None:
    session = OnlineSession(
        sources={"metron"}, credentials=VALID_METRON, prompt_handler=SkipHandler()
    )
    session.set_match(MatchMode.ASK)
    assert _live_lookup(session).match is MatchMode.ASK


def test_set_defer_prompts_off_leaves_an_ask_match_alone() -> None:
    """The toggle is not a second gate; a missing resolver surfaces at prompt time."""
    session = OnlineSession(
        sources={"metron"},
        credentials=VALID_METRON,
        match=MatchMode.ASK,
        defer_prompts=True,
    )
    session.set_defer_prompts(defer=False)
    assert session.defer_prompts is False
    assert session.match is MatchMode.ASK


def test_set_prompts_changes_subsequent_lookups() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    assert _live_lookup(session).prompts == Prompts.ASK
    session.set_prompts(Prompts.NEVER)
    assert _live_lookup(session).prompts == Prompts.NEVER
    session.set_prompts(Prompts.ASK)
    assert _live_lookup(session).prompts == Prompts.ASK


# --- credential propagation ---------------------------------------------------


def test_credentials_propagate_into_settings() -> None:
    creds = OnlineCredentials(
        metron_key="metron-token",
        metron_url="https://m",
        comicvine_key="cv-key",
        comicvine_url="https://cv",
    )
    session = OnlineSession(sources={"metron", "comicvine"}, credentials=creds)
    cfg = session._build_config()
    m = cfg.online.auth.sources["metron"]
    assert m.key == "metron-token"
    assert m.url == "https://m"
    cv = cfg.online.auth.sources["comicvine"]
    assert cv.key == "cv-key"
    assert cv.url == "https://cv"


def test_only_enabled_sources_appear_in_auth() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    cfg = session._build_config()
    assert "metron" in cfg.online.auth.sources
    assert "comicvine" not in cfg.online.auth.sources


def test_supplied_config_is_the_base_the_session_layers_over() -> None:
    """Settings an embedder passes in survive into every per-file config."""
    base = get_config()
    cache = replace(base.online.cache, dir=Path("/tmp/codex-cache"))
    tuning = replace(base.online.tuning, effort=Effort.THOROUGH)
    supplied = replace(base, online=replace(base.online, cache=cache, tuning=tuning))

    session = OnlineSession(
        sources={"metron"}, credentials=VALID_METRON, config=supplied
    )

    cfg = session._build_config()
    assert cfg.online.cache.dir == Path("/tmp/codex-cache")
    assert cfg.online.tuning.effort is Effort.THOROUGH
    # The session's own preferences still win over what it was handed.
    assert cfg.online.lookup.sources == ("metron",)
    assert cfg.online.lookup.enabled is True


def test_supplied_config_skips_the_settings_read(monkeypatch) -> None:
    """A caller with settings in hand pays no config-file or env read."""

    def _fail() -> None:
        msg = "get_config() should not be called when config= is supplied"
        raise AssertionError(msg)

    monkeypatch.setattr("comicbox.online_session.get_config", _fail)
    session = OnlineSession(
        sources={"metron"}, credentials=VALID_METRON, config=get_config()
    )
    assert session._build_config().online.lookup.sources == ("metron",)


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
    from comicbox.exceptions import OnlineLookupAbortedError

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


def test_an_abort_keeps_its_reason(tmp_path, monkeypatch) -> None:
    """
    The caller can tell a quota stop from a pause it asked for.

    Both end a run as a stream of cancelled results, so without the reason
    an embedding application has to scrape the log to learn that the day's
    API budget ran out rather than that a user pressed pause.
    """
    from comicbox.exceptions import OnlineLookupAbortedError

    reason = "online: daily API request quota exhausted"
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)

    def raise_abort(self, path):
        raise OnlineLookupAbortedError(reason)

    monkeypatch.setattr(OnlineSession, "_run_one", raise_abort)
    list(session.tag_many([tmp_path / "f0.cbz"]))

    assert session.abort_reason == reason


def test_a_plain_cancel_has_no_abort_reason() -> None:
    """A caller's own pause needs no explanation."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)

    session.cancel()

    assert session.cancelled is True
    assert session.abort_reason is None


def test_a_cancel_that_ends_a_waiting_lookup_names_the_wait(
    tmp_path, monkeypatch
) -> None:
    """A cancel caught at a lookup's wait reads as that wait's abort."""
    import threading

    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    waiting = threading.Event()

    def wait_to_retry(self, _path):
        waiting.set()
        self._retry_sleep_wait(30)

    monkeypatch.setattr(OnlineSession, "_run_one", wait_to_retry)
    results = []
    worker = threading.Thread(
        target=lambda: results.append(session.tag(tmp_path / "f0.cbz"))
    )
    worker.start()
    assert waiting.wait(10)
    session.cancel()
    worker.join(10)

    assert results[0].cancelled
    assert session.abort_reason == "online: session cancelled during retry wait"


def test_tag_takes_a_str_path(tmp_path, monkeypatch) -> None:
    """tag() and tag_many() take a str as preload_resolution does."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    seen = []

    def run_one(self, path):
        seen.append(path)
        return {}, False

    monkeypatch.setattr(OnlineSession, "_run_one", run_one)
    name = str(tmp_path / "Foo 001.cbz")
    one = session.tag(name)
    (many,) = session.tag_many([name])

    assert seen == [Path(name), Path(name)]
    assert all(isinstance(path, Path) for path in seen)
    assert one.path == many.path == Path(name)
    assert one.error is None
    assert many.error is None


def test_a_manual_preload_refuses_an_empty_path() -> None:
    """An empty path is the current directory, which no comic is tagged as."""
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    with pytest.raises(ValueError, match="path"):
        session.preload_resolution("fp", action="manual", payload=1, path="")


def test_retry_sleep_wait_aborts_when_cancelled() -> None:
    """The wired retry sleep aborts the in-flight lookup on cancel()."""
    from comicbox.exceptions import OnlineLookupAbortedError

    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    session.cancel()
    with pytest.raises(OnlineLookupAbortedError):
        session._retry_sleep_wait(0.01)


def test_retry_sleep_wait_passes_when_not_cancelled() -> None:
    session = OnlineSession(sources={"metron"}, credentials=VALID_METRON)
    session._retry_sleep_wait(0.001)  # waits out the delay, no exception


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


# --- VerseDB ------------------------------------------------------------------


def test_versedb_is_a_known_source() -> None:
    session = OnlineSession(sources=("versedb",), credentials=VALID_VERSEDB)
    assert session.rate_limit_status() == {"versedb": {}}


def test_rejects_versedb_without_a_token() -> None:
    with pytest.raises(OnlineConfigurationError, match="versedb requires versedb_key"):
        OnlineSession(sources=("versedb",), credentials=VALID_METRON)


def test_the_default_sources_do_not_need_a_versedb_token() -> None:
    """Existing callers name no VerseDB token and must keep validating."""
    OnlineSession(credentials=VALID_BOTH)


def test_versedb_credentials_propagate_into_settings() -> None:
    creds = OnlineCredentials(versedb_key="versedb-token", versedb_url="https://v")
    cfg = OnlineSession(sources=("versedb",), credentials=creds)._build_config()
    v = cfg.online.auth.sources["versedb"]
    assert (v.key, v.url) == ("versedb-token", "https://v")
    assert set(cfg.online.auth.sources) == {"versedb"}


def test_versedb_rate_limit_status_reads_the_shared_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from comicbox.formats.versedb_api import online_source as versedb

    window = {"hour": {"limit": 300, "remaining": 12, "reset_epoch": None}}
    calls: list[tuple] = []

    def status(token: str | None, base_url: str | None = None) -> dict:
        calls.append((token, base_url))
        return window

    monkeypatch.setattr(versedb, "shared_client_rate_limit_status", status)
    session = OnlineSession(sources=("versedb",), credentials=VALID_VERSEDB)
    assert session.rate_limit_status() == {"versedb": window}
    assert calls == [("versedb-token", None)]


def test_close_releases_versedb_too(monkeypatch: pytest.MonkeyPatch) -> None:
    from comicbox.formats.versedb_api import online_source as versedb

    closed: list[bool] = []
    monkeypatch.setattr(versedb, "close_shared_sessions", lambda: closed.append(True))
    OnlineSession(sources=("versedb",), credentials=VALID_VERSEDB).close()
    assert closed == [True]


def test_source_attribution_for_a_frontend() -> None:
    """Codex looks the credit up by the name `OnlinePrompt.source` carries."""
    credit = source_attribution("versedb")
    assert credit == SourceAttribution(
        text="Data from VerseDB", url="https://versedb.com"
    )
    assert source_attribution("metron") is None
    assert source_attribution("comicvine") is None


def test_a_pinned_versedb_id_tags_a_comic_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The whole stack on a recorded response: one request, the id and its link.

    The real SDK parses the response, the transform maps it and the merge
    lays it over the comic's own tags, with no ResourceWarning on close.
    """
    import shutil
    import warnings

    from comicbox.formats.versedb_api.online_source import VerseDBOnlineSource
    from tests.util.versedb_transport import VerseDBTransport

    transport = VerseDBTransport()
    monkeypatch.setattr(VerseDBOnlineSource, "http_transport", transport.transport)
    comic = tmp_path / "comic.cbz"
    shutil.copy(Path("tests/files/Captain Science #001.cbz"), comic)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        with OnlineSession(
            sources=("versedb",),
            ids={"versedb": 1215061},
            credentials=VALID_VERSEDB,
            prompts=Prompts.NEVER,
        ) as session:
            result = session.tag(comic)
            budget = session.rate_limit_status()
    assert (result.matched, result.error) == (True, None)
    assert transport.paths == ["/api/v1/issues/1215061"]
    tags = result.tags or {}
    assert tags["identifiers"]["versedb"] == {"key": "1215061"}
    assert (
        "https://versedb.com/issue/1215061/absolute-bladehawk-2024-24" in tags["urls"]
    )
    assert tags["series"]["name"] == "Absolute Bladehawk"
    assert budget == {
        "versedb": {"hour": {"limit": 300, "remaining": 299, "reset_epoch": None}}
    }
    assert not [w for w in caught if issubclass(w.category, ResourceWarning)]
