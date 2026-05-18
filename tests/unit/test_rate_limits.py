"""Per-source rate-limit override + retry-after honor tests."""

from __future__ import annotations

from argparse import Namespace

from comicbox.config import get_config
from comicbox.config.settings import OnlineSourceLimits
from comicbox.formats.base.online.rate_limits import (
    COMICVINE_DEFAULT_PER_HOUR,
    COMICVINE_DEFAULT_PER_SECOND,
    METRON_DEFAULT_PER_DAY,
    METRON_DEFAULT_PER_MINUTE,
    build_comicvine_limiter,
    build_metron_bucket,
)

# ----------------------------------------------------- bucket builders


def test_metron_bucket_returns_none_without_overrides() -> None:
    """No overrides → upstream library default in use."""
    assert build_metron_bucket(None) is None
    assert build_metron_bucket(OnlineSourceLimits()) is None


def test_metron_bucket_built_when_per_minute_set() -> None:
    """Any override triggers a custom bucket."""
    bucket = build_metron_bucket(OnlineSourceLimits(per_minute=30))
    assert bucket is not None


def test_metron_bucket_built_when_per_day_set() -> None:
    bucket = build_metron_bucket(OnlineSourceLimits(per_day=10_000))
    assert bucket is not None


def test_comicvine_limiter_returns_none_without_overrides() -> None:
    assert build_comicvine_limiter(None) is None
    assert build_comicvine_limiter(OnlineSourceLimits()) is None


def test_comicvine_limiter_built_when_per_second_set() -> None:
    limiter = build_comicvine_limiter(OnlineSourceLimits(per_second=2))
    assert limiter is not None


def test_comicvine_limiter_built_when_per_hour_set() -> None:
    limiter = build_comicvine_limiter(OnlineSourceLimits(per_hour=500))
    assert limiter is not None


def test_documented_defaults_match_upstream() -> None:
    """
    Sanity check: our citation constants match the upstream libraries.

    If this fails, either the upstream library bumped its constant (rare —
    it happens when the API itself loosens limits) or we picked the wrong
    number when first writing this module. Either way the README and
    rate_limits.py docstrings need a look.
    """
    from mokkari.session import (  # type: ignore[import-untyped]
        METRON_DAY_RATE_LIMIT,
        METRON_MINUTE_RATE_LIMIT,
    )

    assert METRON_DEFAULT_PER_MINUTE == METRON_MINUTE_RATE_LIMIT
    assert METRON_DEFAULT_PER_DAY == METRON_DAY_RATE_LIMIT
    # simyan exposes its rates inside the bucket; we sanity-check the
    # documented numbers stayed at 1/sec and 200/hr.
    assert COMICVINE_DEFAULT_PER_SECOND == 1
    assert COMICVINE_DEFAULT_PER_HOUR == 200


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
