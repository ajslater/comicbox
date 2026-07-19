"""Per-source rate-limit override + retry-after honor tests."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import replace

import pytest

from comicbox.config import get_config
from comicbox.config.settings import (
    CacheMode,
    OnlineCacheSettings,
    OnlineSettings,
    OnlineSourceCredentials,
    OnlineSourceLimits,
    OnlineSourceTuning,
    OnlineTuningSettings,
)
from comicbox.formats.base.online.rate_limits import (
    COMICVINE_DEFAULT_PER_HOUR,
    COMICVINE_DEFAULT_PER_SECOND,
    METRON_DEFAULT_PER_MINUTE,
)
from comicbox.formats.metron_api import online_source as metron_online_source
from comicbox.formats.metron_api.online_source import MetronOnlineSource


def test_documented_defaults_match_upstream() -> None:
    """
    Sanity check: our citation constants match the upstream libraries.

    Metron's burst limit (20/min) is fixed for every user, so it's still
    pinned here, but mokkari>=4.0.1 no longer exports it as an importable
    constant — it reads the actual limit off `X-RateLimit-*` response
    headers instead of hardcoding one (same for the daily sustained limit,
    which varies per OpenCollective donor tier and isn't citable at all
    anymore). So this can only be a literal pin, not a cross-check against
    mokkari's source — if Metron's policy ever changes, rate_limits.py
    needs a manual look.
    """
    assert METRON_DEFAULT_PER_MINUTE == 20
    # simyan 3.x hardcodes its rates as literals in Comicvine.__init__ with
    # no importable constant; pin the documented numbers it ships with.
    assert COMICVINE_DEFAULT_PER_SECOND == 1
    assert COMICVINE_DEFAULT_PER_HOUR == 200


# ------------------------------------------------- shared mokkari session


class _FakeMokkariSession:
    """Stands in for mokkari's `Session`; records the kwargs it was built with."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


def _fake_mokkari_api(**kwargs: object) -> _FakeMokkariSession:
    return _FakeMokkariSession(**kwargs)


@pytest.fixture(autouse=True)
def clear_session_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets its own empty module-level session cache."""
    monkeypatch.setattr(metron_online_source, "_session_cache", {})


@pytest.fixture(autouse=True)
def clear_warn_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset warn_once dedup state so warning asserts aren't order-dependent."""
    from comicbox.formats.base.online import warn_once

    monkeypatch.setattr(warn_once, "_seen", set())


def _make_metron_source(
    monkeypatch: pytest.MonkeyPatch,
    *,
    user: str = "u",
    password: str = "p",  # noqa: S107
    settings: OnlineSettings | None = None,
) -> MetronOnlineSource:
    """
    Build a source whose `_build_session` never touches a real cache file.

    `_build_session` calls `_get_cache()` regardless of the fake `mokkari.api`
    below, which would otherwise open a real `SqliteCache` against the
    user's actual `~/.cache/comicbox/online/` directory.
    """
    monkeypatch.setattr("mokkari.api", _fake_mokkari_api)
    off_cache = OnlineCacheSettings(mode=CacheMode.OFF)
    settings = (
        replace(settings, cache=off_cache)
        if settings
        else OnlineSettings(cache=off_cache)
    )
    creds = OnlineSourceCredentials(user=user, password=password)
    return MetronOnlineSource(creds, settings)


def test_get_session_shares_one_client_for_same_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Two sources built with the same credentials share one mokkari Session.

    Sources are rebuilt per file; without sharing, every file's `Session`
    would start with a blank `rate_limit_status` and never see another
    worker's rate-limit state (see `MetronOnlineSource._get_session`) —
    the whole point of running `Runner._run_parallel`'s batch as threads
    rather than processes.
    """
    src_a = _make_metron_source(monkeypatch)
    src_b = _make_metron_source(monkeypatch)
    assert src_a._get_session() is src_b._get_session()


def test_get_session_builds_distinct_clients_for_different_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src_a = _make_metron_source(monkeypatch, user="u1", password="p1")
    src_b = _make_metron_source(monkeypatch, user="u2", password="p2")
    assert src_a._get_session() is not src_b._get_session()


def test_get_session_memoizes_per_instance_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second call on the same source instance doesn't re-hit the shared cache."""
    src = _make_metron_source(monkeypatch)
    first = src._get_session()
    assert src._get_session() is first


def test_metron_rate_limit_override_warns_and_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """per_minute/per_day overrides can't flow into mokkari>=4.0.1 — warn."""
    from loguru import logger as loguru_logger

    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    try:
        tuning = OnlineTuningSettings(
            per_source={
                "metron": OnlineSourceTuning(
                    rate_limit=OnlineSourceLimits(per_minute=30)
                )
            }
        )
        settings = OnlineSettings(tuning=tuning)
        session = _make_metron_source(monkeypatch, settings=settings)._get_session()
    finally:
        loguru_logger.remove(handler_id)
    assert any("ignored" in message for message in messages)
    # The "ignored" half: the override must not flow into the session —
    # mokkari's api() factory takes exactly these four kwargs, no rate
    # or bucket argument.
    assert isinstance(session, _FakeMokkariSession)
    assert set(session.kwargs) == {"username", "passwd", "cache", "user_agent"}


def test_no_metron_rate_limit_override_no_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from loguru import logger as loguru_logger

    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    try:
        _make_metron_source(monkeypatch)._get_session()
    finally:
        loguru_logger.remove(handler_id)
    assert not any("ignored" in message for message in messages)


def test_metron_override_warning_fires_once_per_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warn_once dedups the ignored-override warning across per-file sources."""
    from loguru import logger as loguru_logger

    tuning = OnlineTuningSettings(
        per_source={
            "metron": OnlineSourceTuning(rate_limit=OnlineSourceLimits(per_minute=30))
        }
    )
    settings = OnlineSettings(tuning=tuning)
    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    try:
        _make_metron_source(monkeypatch, settings=settings)._get_session()
        _make_metron_source(monkeypatch, settings=settings)._get_session()
    finally:
        loguru_logger.remove(handler_id)
    assert sum("ignored" in message for message in messages) == 1


def test_shared_session_warns_on_divergent_cache_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    First build wins.

    A same-credential source with different cache settings reuses the
    existing session but says so once.
    """
    from datetime import timedelta

    from loguru import logger as loguru_logger

    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    try:
        first = _make_metron_source(monkeypatch)
        session = first._get_session()
        divergent_settings = OnlineSettings(
            cache=OnlineCacheSettings(mode=CacheMode.ON, ttl=timedelta(days=1))
        )
        creds = OnlineSourceCredentials(user="u", password="p")
        divergent = MetronOnlineSource(creds, divergent_settings)
        assert divergent._get_session() is session
    finally:
        loguru_logger.remove(handler_id)
    assert sum("reusing the existing shared" in m for m in messages) == 1


# -------------------------------------------------- config-resolution flow


def test_no_rate_limit_overrides_yields_empty_per_source() -> None:
    cfg = get_config(Namespace(comicbox=Namespace()))
    assert cfg.online.tuning.per_source == {}


def test_metron_rate_limit_override_via_config() -> None:
    """A nested config block reaches OnlineTuningSettings.per_source[<src>].rate_limit."""
    cfg = get_config(
        {
            "comicbox": {
                "online": {
                    "tuning": {
                        "per_source": {
                            "metron": {
                                "rate_limit": {"per_minute": 30, "per_day": 6000}
                            }
                        }
                    }
                }
            }
        }
    )
    metron = cfg.online.tuning.per_source["metron"]
    assert metron.rate_limit.per_minute == 30
    assert metron.rate_limit.per_day == 6000


def test_comicvine_rate_limit_override_via_config() -> None:
    cfg = get_config(
        {
            "comicbox": {
                "online": {
                    "tuning": {
                        "per_source": {
                            "comicvine": {
                                "rate_limit": {"per_second": 2, "per_hour": 500}
                            }
                        }
                    }
                }
            }
        }
    )
    cv = cfg.online.tuning.per_source["comicvine"]
    assert cv.rate_limit.per_second == 2
    assert cv.rate_limit.per_hour == 500


def test_partial_rate_limit_override() -> None:
    """Per-day-only override carries through; per-minute stays None."""
    cfg = get_config(
        {
            "comicbox": {
                "online": {
                    "tuning": {
                        "per_source": {"metron": {"rate_limit": {"per_day": 10_000}}}
                    }
                }
            }
        }
    )
    metron = cfg.online.tuning.per_source["metron"]
    assert metron.rate_limit.per_day == 10_000
    assert metron.rate_limit.per_minute is None


# ----------------------------------------------------- with_retry retry_after


def test_with_retry_honors_long_retry_after() -> None:
    """A server hint of 300s is honored, not capped at our 60s schedule."""
    from comicbox.formats.base.online.retry import with_retry

    # mokkari-style RateLimitError with retry_after attribute.
    class FakeRateLimitError(Exception):
        def __init__(self, retry_after: float) -> None:
            super().__init__(f"retry after {retry_after}")
            self.retry_after = retry_after

    # Override the type-name check by naming the class accordingly.
    FakeRateLimitError.__name__ = "RateLimitError"

    sleeps: list[float] = []
    call_count = {"n": 0}

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    @with_retry(max_retries=2, sleep=fake_sleep)
    def flaky() -> str:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise FakeRateLimitError(retry_after=300.0)
        return "ok"

    result = flaky()
    assert result == "ok"
    assert sleeps == [300.0]  # exact server hint, NOT clamped to 60s


def test_with_retry_clamps_excessive_retry_after() -> None:
    """A wildly-large hint (e.g. 1 day) is clamped to the 1-hour ceiling."""
    from comicbox.formats.base.online.retry import with_retry

    class FakeRateLimitError(Exception):
        def __init__(self) -> None:
            super().__init__("nope")
            self.retry_after = 86_400.0  # 1 day

    FakeRateLimitError.__name__ = "RateLimitError"

    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    @with_retry(max_retries=1, sleep=fake_sleep)
    def flaky() -> str:
        if not sleeps:
            raise FakeRateLimitError
        return "ok"

    flaky()
    assert sleeps == [3600.0]  # clamped to 1-hour ceiling


def test_with_retry_no_hint_uses_short_backoff() -> None:
    """Without a server hint, fall back to the short exponential schedule."""
    from comicbox.formats.base.online.retry import with_retry

    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    call_count = {"n": 0}

    @with_retry(max_retries=2, sleep=fake_sleep)
    def flaky() -> str:
        call_count["n"] += 1
        if call_count["n"] < 3:
            msg = "transient"
            raise RuntimeError(msg)
        return "ok"

    flaky()
    # 1, 2 — exponential; never reaches the 60s cap.
    assert sleeps == [1.0, 2.0]
