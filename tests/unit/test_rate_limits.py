"""Per-source rate-limit override + retry-after honor tests."""

from __future__ import annotations

from argparse import Namespace
from typing import TYPE_CHECKING

import pytest

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

if TYPE_CHECKING:
    from pathlib import Path

# ----------------------------------------------------- bucket builders


def test_metron_bucket_returns_none_without_overrides(tmp_path: Path) -> None:
    """No overrides → upstream library default in use."""
    db = tmp_path / "metron_rl.sqlite"
    assert build_metron_bucket(None, db) is None
    assert build_metron_bucket(OnlineSourceLimits(), db) is None


def test_metron_bucket_built_when_per_minute_set(tmp_path: Path) -> None:
    """Any override triggers a custom bucket persisted at db_path."""
    db = tmp_path / "metron_rl.sqlite"
    bucket = build_metron_bucket(OnlineSourceLimits(per_minute=30), db)
    assert bucket is not None
    # The bucket must persist at the supplied path, not a fresh tempfile.
    assert db.exists()


def test_metron_bucket_built_when_per_day_set(tmp_path: Path) -> None:
    bucket = build_metron_bucket(
        OnlineSourceLimits(per_day=10_000), tmp_path / "m.sqlite"
    )
    assert bucket is not None


def test_comicvine_limiter_always_built(tmp_path: Path) -> None:
    """
    Unlike Metron, ComicVine always gets our own bounded limiter.

    simyan's default limiter blocks indefinitely on an hourly-cap hit; we
    always wrap it so the wait is bounded (see `_BoundedComicVineLimiter`).
    """
    db = tmp_path / "cv_rl.sqlite"
    assert build_comicvine_limiter(None, db) is not None
    assert build_comicvine_limiter(OnlineSourceLimits(), db) is not None
    # The bucket must persist at the supplied path, not a fresh tempfile.
    assert db.exists()


def test_comicvine_limiter_built_when_per_second_set(tmp_path: Path) -> None:
    limiter = build_comicvine_limiter(
        OnlineSourceLimits(per_second=2), tmp_path / "cv.sqlite"
    )
    assert limiter is not None


def test_comicvine_limiter_built_when_per_hour_set(tmp_path: Path) -> None:
    limiter = build_comicvine_limiter(
        OnlineSourceLimits(per_hour=500), tmp_path / "cv.sqlite"
    )
    assert limiter is not None


def test_comicvine_limiter_raises_instead_of_blocking_on_cap(tmp_path: Path) -> None:
    """
    A wait longer than the ceiling becomes a RateLimitError, not an endless block.

    Build the bounded limiter directly with a tiny ceiling over a
    1-per-hour bucket: the first acquire takes the slot, the second would
    have to wait ~1 hour for simyan's default limiter — ours raises
    RateLimitError within the ceiling instead, so comicbox's retry layer
    (which keys on the `RateLimitError` type name) can own the wait.
    """
    import time

    from pyrate_limiter import Duration, Rate, SQLiteBucket
    from simyan.errors import RateLimitError

    from comicbox.formats.base.online.rate_limits import (
        _bounded_comicvine_limiter_cls,
    )

    limiter_cls = _bounded_comicvine_limiter_cls()
    bucket = SQLiteBucket.init_from_file(
        [Rate(1, Duration.HOUR)], db_path=str(tmp_path / "cap.sqlite")
    )
    limiter = limiter_cls(bucket, wait_ceiling_s=0.2)

    assert limiter.try_acquire("x") is True  # first slot, no wait
    start = time.monotonic()
    with pytest.raises(RateLimitError):
        limiter.try_acquire("x")  # would wait ~1h; raises within the ceiling
    # Proves it didn't actually block for the hour — bailed near the ceiling.
    assert time.monotonic() - start < 5.0


def test_comicvine_limiter_absorbs_short_pacing_wait(tmp_path: Path) -> None:
    """
    A wait under the ceiling is absorbed in-limiter, not raised.

    Two quick calls against a 2/sec bucket both fit inside the window, so
    no RateLimitError is raised — normal pacing is untouched.
    """
    from pyrate_limiter import Duration, Rate, SQLiteBucket

    from comicbox.formats.base.online.rate_limits import (
        _bounded_comicvine_limiter_cls,
    )

    limiter_cls = _bounded_comicvine_limiter_cls()
    bucket = SQLiteBucket.init_from_file(
        [Rate(2, Duration.SECOND)], db_path=str(tmp_path / "pace.sqlite")
    )
    limiter = limiter_cls(bucket, wait_ceiling_s=5.0)
    assert limiter.try_acquire("x") is True
    assert limiter.try_acquire("x") is True


def test_override_buckets_memoized_across_session_builds(tmp_path: Path) -> None:
    """
    Same (db_path, limits) → the same bucket object, not a fresh empty one.

    Sessions are rebuilt per API call and sources per file; without
    memoization every call started a brand-new bucket and the configured
    override never accumulated state — it limited nothing.
    """
    db = tmp_path / "memo_rl.sqlite"
    limits = OnlineSourceLimits(per_minute=30)
    first = build_metron_bucket(limits, db)
    second = build_metron_bucket(OnlineSourceLimits(per_minute=30), db)
    assert first is second
    # Different limits → a distinct bucket.
    third = build_metron_bucket(OnlineSourceLimits(per_minute=10), db)
    assert third is not first

    cv_limits = OnlineSourceLimits(per_hour=500)
    cv_db = tmp_path / "memo_cv.sqlite"
    assert build_comicvine_limiter(cv_limits, cv_db) is build_comicvine_limiter(
        cv_limits, cv_db
    )


def test_documented_defaults_match_upstream() -> None:
    """
    Sanity check: our citation constants match the upstream libraries.

    If this fails, either the upstream library bumped its constant (rare —
    it happens when the API itself loosens limits) or we picked the wrong
    number when first writing this module. Either way the README and
    rate_limits.py docstrings need a look.
    """
    from mokkari.session import (
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
