"""
`MetronOnlineSource.get()` adds the full series' detail to the issue.

Drives a real mokkari Session, with a real `SqliteCache`, against a fake
transport, so the "one extra request per distinct series" claim rests on
mokkari's own response cache rather than on a fake's bookkeeping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger
from mokkari.sqlite_cache import SqliteCache

from comicbox.config.online.settings import OnlineSettings, OnlineSourceCredentials
from comicbox.enums.comicbox import SeriesStatusEnum
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.base.online.rate_gate import RateGate
from comicbox.formats.metron_api.online_source import MetronOnlineSource
from comicbox.formats.metron_api.paced_session import build_paced_session
from comicbox.formats.metron_api.transform import MetronApiTransform
from tests.util.metron_transport import (
    FakeAdapter,
    Reply,
    install,
    issue_detail,
    series_detail,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    import requests

_SERIES_ID = 7


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Any]:
    """Yield a paced mokkari Session with a response cache; close it after."""
    cache = SqliteCache(db_name=str(tmp_path / "metron.db"))
    session = build_paced_session(
        RateGate(default_limit=1000), api_token="t", cache=cache
    )
    yield session
    session.close()
    cache.con.close()


def _route(series_reply: Reply) -> Callable[[requests.PreparedRequest], Reply]:
    """Answer `/series/<id>/` with ``series_reply`` and issues by their id."""

    def reply(request: requests.PreparedRequest) -> Reply:
        url = request.url or ""
        if f"/series/{_SERIES_ID}/" in url:
            return series_reply
        issue_id = int(url.rstrip("/").rsplit("/", 1)[-1])
        return Reply(issue_detail(issue_id, _SERIES_ID))

    return reply


def _source(
    monkeypatch: pytest.MonkeyPatch, session: Any, series_reply: Reply
) -> tuple[MetronOnlineSource, FakeAdapter, list[float]]:
    """Build a source on ``session``; return it, its transport and its sleeps."""
    src = MetronOnlineSource(OnlineSourceCredentials(key="t"), OnlineSettings())
    monkeypatch.setattr(src, "_get_session", lambda: session)
    sleeps: list[float] = []
    src.retry_sleep = sleeps.append
    return src, install(session, _route(series_reply)), sleeps


def _paths(adapter: FakeAdapter) -> list[str]:
    return [url.split("/api", 1)[-1] for url in adapter.urls]


def test_get_fetches_each_series_once(
    monkeypatch: pytest.MonkeyPatch, session: Any
) -> None:
    """Two issues of one series cost one `series(id)` request between them."""
    src, adapter, _ = _source(monkeypatch, session, Reply(series_detail(_SERIES_ID)))

    first = src.get(1)
    second = src.get(2)

    assert _paths(adapter) == ["/issue/1/", f"/series/{_SERIES_ID}/", "/issue/2/"]
    for payload in (first, second):
        series = payload["series"]
        assert series["year_end"] == 2021
        assert series["status"] == "Completed"
        assert series["desc"] == "<p>The whole run.</p>"
        assert series["issue_count"] == 12


def test_get_series_detail_reaches_comicbox(
    monkeypatch: pytest.MonkeyPatch, session: Any
) -> None:
    """The injected detail survives the transform into the comicbox schema."""
    src, _, _ = _source(monkeypatch, session, Reply(series_detail(_SERIES_ID)))

    cb = dict(MetronApiTransform().to_comicbox({"metron_api": src.get(1)}))["comicbox"]

    assert cb["series"]["start_year"] == 2020
    assert cb["series"]["end_year"] == 2021
    assert cb["series"]["status"] == SeriesStatusEnum.COMPLETED
    assert cb["series"]["summary"] == "The whole run."
    assert cb["volume"]["issue_count"] == 12
    assert cb["original_format"] == "Single Issue"


def test_get_survives_a_failing_series_fetch(
    monkeypatch: pytest.MonkeyPatch, session: Any
) -> None:
    """A series failure costs only the series detail, not the issue."""
    src, adapter, sleeps = _source(
        monkeypatch, session, Reply({"detail": "boom"}, status_code=500)
    )
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        payload = src.get(1)
    finally:
        logger.remove(handler_id)

    assert payload["id"] == 1
    assert not {"year_end", "status", "desc", "issue_count"} & payload["series"].keys()
    # The tight series budget: one retry, then give up.
    series_path = f"/series/{_SERIES_ID}/"
    assert _paths(adapter) == ["/issue/1/", series_path, series_path]
    assert len(sleeps) == 1
    assert any(f"series({_SERIES_ID}) failed" in message for message in messages)


def test_get_propagates_an_abort_during_the_series_fetch(
    monkeypatch: pytest.MonkeyPatch, session: Any
) -> None:
    """An abort ends the lookup; it is not swallowed as a series failure."""
    src, _, _ = _source(
        monkeypatch, session, Reply({"detail": "boom"}, status_code=500)
    )

    def abort(_seconds: float) -> None:
        msg = "cancelled"
        raise OnlineLookupAbortedError(msg)

    src.retry_sleep = abort

    with pytest.raises(OnlineLookupAbortedError):
        src.get(1)
