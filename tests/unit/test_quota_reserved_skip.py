"""
A search the quota reserve stopped is reported as a skip, not a miss.

Near the end of the day's API budget the Metron source stops starting new
searches so what is left finishes comics that already matched. It returns no
candidates to say so, which is indistinguishable from "the database has
nothing for this comic" — and those two call for opposite handling. A comic
nobody looked at should be tried again tomorrow; one that genuinely missed
should not. So the source records why, and the lookup emits ``Skipped`` with
``SKIP_QUOTA_RESERVED`` instead of silently reporting a miss.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from comicbox.config.online.settings import OnlineSettings, OnlineSourceCredentials
from comicbox.events import SKIP_MATCHER_DECLINED, SKIP_QUOTA_RESERVED
from comicbox.formats.base.online.profile import ComicProfile
from comicbox.formats.base.online.rate_gate import RateGate
from comicbox.formats.metron_api.online_source import MetronOnlineSource

if TYPE_CHECKING:
    import pytest

_SUSTAINED_LIMIT = 5000
# Below the gate's reserve: enough to finish matched comics, not to start new
# searches.
_AT_THE_RESERVE = 5


def _source(monkeypatch: pytest.MonkeyPatch, gate: RateGate | None) -> Any:
    creds = OnlineSourceCredentials(user="u", password="p")
    src = MetronOnlineSource(creds, OnlineSettings())
    monkeypatch.setattr(src, "_gate", lambda: gate)
    return src


def _spent_gate() -> RateGate:
    gate = RateGate(default_limit=20)
    gate.observe(
        burst_limit=20,
        burst_remaining=20,
        sustained_limit=_SUSTAINED_LIMIT,
        sustained_remaining=_AT_THE_RESERVE,
    )
    return gate


def test_the_reserve_stops_the_search_and_says_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = _source(monkeypatch, _spent_gate())

    candidates = src.search(ComicProfile(series="Captain Science", issue="1"))

    assert candidates == []
    assert src.search_skip_reason == SKIP_QUOTA_RESERVED


def test_a_healthy_budget_records_no_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """A source that actually searched must not claim it was skipped."""
    gate = RateGate(default_limit=20)
    gate.observe(
        burst_limit=20,
        burst_remaining=20,
        sustained_limit=_SUSTAINED_LIMIT,
        sustained_remaining=_SUSTAINED_LIMIT,
    )
    src = _source(monkeypatch, gate)
    # No series and no explicit id: returns [] without spending a request.
    monkeypatch.setattr(src, "_get_session", lambda: None)

    assert src.search(ComicProfile()) == []
    assert src.search_skip_reason is None


def test_the_reason_never_outlives_its_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stale reason would mislabel the next comic's honest miss."""
    src = _source(monkeypatch, _spent_gate())
    src.search(ComicProfile(series="Captain Science", issue="1"))
    assert src.search_skip_reason == SKIP_QUOTA_RESERVED

    src.reset_search_skip_reason()

    assert src.search_skip_reason is None


def test_the_two_skip_reasons_are_distinct() -> None:
    """Consumers switch on these, so they must never collapse."""
    assert SKIP_QUOTA_RESERVED != SKIP_MATCHER_DECLINED
