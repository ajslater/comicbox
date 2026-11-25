"""The `versedb` SDK adapter: status mapping, cooldown, cache, budget, drift."""

from __future__ import annotations

import time
from datetime import timedelta
from typing import TYPE_CHECKING

import httpx
import pytest

from comicbox.formats.base.online import outcome_stats
from comicbox.formats.versedb_api.cache import ResponseCache
from comicbox.formats.versedb_api.client import (
    USED_KEYWORDS,
    VerseDBAuthError,
    VerseDBClient,
    VerseDBNotFoundError,
    VerseDBQuotaError,
    VerseDBRateLimitError,
    VerseDBResponseError,
    VerseDBServerError,
    endpoint_keywords,
)
from tests.util.versedb_transport import Reply, VerseDBTransport, fixture

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path


@pytest.fixture
def make_client() -> Iterator[Callable[..., tuple[VerseDBClient, VerseDBTransport]]]:
    """Build clients on a mock transport, and close every one afterwards."""
    clients: list[VerseDBClient] = []

    def _make(
        reply_for: Callable[[httpx.Request], Reply] | None = None,
        cache: ResponseCache | None = None,
    ) -> tuple[VerseDBClient, VerseDBTransport]:
        transport = (
            VerseDBTransport() if reply_for is None else VerseDBTransport(reply_for)
        )
        client = VerseDBClient(
            "token", user_agent="test", cache=cache, transport=transport.transport
        )
        clients.append(client)
        return client, transport

    yield _make
    for client in clients:
        client.close()


def _always(reply: Reply) -> Callable[[httpx.Request], Reply]:
    return lambda _request: reply


def test_issue_returns_the_servers_json(make_client) -> None:
    client, transport = make_client()
    payload = client.issue(1215061)
    assert payload["data"]["id"] == 1215061
    assert transport.paths == ["/api/v1/issues/1215061"]


def test_requests_carry_the_token_user_agent_and_accept(make_client) -> None:
    client, transport = make_client()
    client.issue(1)
    headers = transport.requests[0].headers
    assert headers["authorization"] == "Bearer token"
    assert headers["user-agent"] == "test"
    assert headers["accept"] == "application/json"


def test_list_issues_sends_one_call_for_many_series(make_client) -> None:
    client, transport = make_client()
    client.list_issues((165850, 139382, 139382), "1")
    assert transport.params() == {
        "series_ids": "139382,165850",
        "include": "series",
        "limit": "100",
        "page": "1",
        "q": "1",
    }


def test_list_issues_without_a_number_sends_no_q(make_client) -> None:
    client, transport = make_client()
    client.list_issues((139382,))
    assert "q" not in transport.params()


def test_search_series_caps_the_page_size(make_client) -> None:
    client, transport = make_client()
    client.search_series("Absolute Bladehawk", 500)
    assert transport.params() == {"q": "Absolute Bladehawk", "limit": "50"}


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, VerseDBAuthError),
        (403, VerseDBAuthError),
        (404, VerseDBNotFoundError),
        (500, VerseDBServerError),
        (503, VerseDBServerError),
        (418, VerseDBResponseError),
    ],
)
def test_status_maps_to_an_exception(
    make_client, status: int, error: type[Exception]
) -> None:
    client, _ = make_client(_always(Reply({"message": "x"}, status=status)))
    with pytest.raises(error):
        client.issue(1)


def test_the_recorded_404_parses_and_maps(make_client) -> None:
    client, _ = make_client()
    with pytest.raises(VerseDBNotFoundError):
        client.issue(999999999)


def test_429_carries_retry_after_and_starts_a_cooldown(make_client) -> None:
    reply = Reply(
        {"message": "Too Many Attempts."},
        status=429,
        headers={
            "Retry-After": "120",
            "X-RateLimit-Limit": "300",
            "X-RateLimit-Remaining": "0",
        },
    )
    client, transport = make_client(_always(reply))
    with pytest.raises(VerseDBRateLimitError) as exc_info:
        client.issue(1)
    assert exc_info.value.retry_after == 120.0
    # The cooldown refuses without sending: one request, not two.
    with pytest.raises(VerseDBRateLimitError) as again:
        client.issue(2)
    assert len(transport.requests) == 1
    assert again.value.retry_after is not None
    assert 0 < again.value.retry_after <= 120.0


def test_429_without_retry_after_still_cools_down(make_client) -> None:
    client, transport = make_client(_always(Reply({"message": "x"}, status=429)))
    with pytest.raises(VerseDBRateLimitError) as exc_info:
        client.issue(1)
    # No hint: the retry layer falls back to its own schedule.
    assert exc_info.value.retry_after is None
    with pytest.raises(VerseDBRateLimitError):
        client.issue(1)
    assert len(transport.requests) == 1


def test_a_non_json_429_still_maps_by_status(make_client) -> None:
    """
    The SDK's parse of a non-JSON error body raises before it returns.

    The response hook kept the status, so the 429 and its Retry-After
    survive instead of turning into an unparsable-response error.
    """
    reply = Reply(status=429, body=b"Too Many Attempts.", headers={"Retry-After": "5"})
    client, _ = make_client(_always(reply))
    with pytest.raises(VerseDBRateLimitError) as exc_info:
        client.issue(1)
    assert exc_info.value.retry_after == 5.0


def test_a_200_the_sdk_cannot_parse_says_the_package_may_be_behind(make_client) -> None:
    payload = fixture("issue_regular")
    del payload["data"]["slug"]
    client, _ = make_client(_always(Reply(payload)))
    with pytest.raises(VerseDBResponseError, match="versedb package may be behind"):
        client.issue(1)


def test_cooldown_lapses(make_client, monkeypatch: pytest.MonkeyPatch) -> None:
    replies = iter((Reply({"message": "x"}, status=429, headers={"Retry-After": "1"}),))
    client, transport = make_client(
        lambda _request: next(replies, None) or Reply(fixture("issue_regular"))
    )
    with pytest.raises(VerseDBRateLimitError):
        client.issue(1)
    later = time.monotonic() + 2
    monkeypatch.setattr(
        "comicbox.formats.versedb_api.client.time.monotonic", lambda: later
    )
    assert client.issue(1)["data"]
    assert len(transport.requests) == 2


def test_rate_limit_status_reads_the_last_headers(make_client) -> None:
    headers = {"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "287"}
    client, _ = make_client(_always(Reply(fixture("issue_regular"), headers=headers)))
    assert client.rate_limit_status() == {}
    client.issue(1)
    assert client.rate_limit_status() == {
        "hour": {"limit": 300, "remaining": 287, "reset_epoch": None}
    }


def test_probe_is_uncached_and_returns_the_budget(make_client, tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite", timedelta(days=1))
    client, transport = make_client(cache=cache)
    assert client.probe()["hour"]["limit"] == 300
    client.probe()
    assert len(transport.requests) == 2
    assert transport.params() == {"limit": "1"}


def test_a_cached_response_spends_no_request(make_client, tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite", timedelta(days=1))
    client, transport = make_client(cache=cache)
    first = client.issue(1215061)
    second = client.issue(1215061)
    assert first == second
    assert len(transport.requests) == 1


def test_errors_are_not_cached(make_client, tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite", timedelta(days=1))
    client, transport = make_client(cache=cache)
    for _ in range(2):
        with pytest.raises(VerseDBNotFoundError):
            client.issue(999999999)
    assert len(transport.requests) == 2


def test_no_store_is_respected(make_client, tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite", timedelta(days=1))
    reply = Reply(fixture("issue_regular"), headers={"Cache-Control": "no-store"})
    client, transport = make_client(_always(reply), cache=cache)
    client.issue(1)
    client.issue(1)
    assert len(transport.requests) == 2


def test_close_closes_the_cache_too(make_client, tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite", timedelta(days=1))
    client, _ = make_client(cache=cache)
    client.close()
    assert client.closed
    client.close()  # twice is fine


def test_a_headerless_answer_is_counted() -> None:
    """VerseDB's API sends X-RateLimit-* on its 200s; a bare one came from elsewhere."""
    outcome_stats.reset()
    transport = VerseDBTransport(_always(Reply(fixture("issue_regular"), headers={})))
    client = VerseDBClient("t", user_agent="t", transport=transport.transport)
    try:
        client.issue(1)
    finally:
        client.close()
    assert outcome_stats.api_snapshot()["versedb"].unthrottled == {200: 1}


def test_an_unauthenticated_401_is_not_counted_as_unthrottled() -> None:
    outcome_stats.reset()
    transport = VerseDBTransport(
        _always(Reply({"message": "Unauthenticated."}, 401, {}))
    )
    client = VerseDBClient("t", user_agent="t", transport=transport.transport)
    try:
        with pytest.raises(VerseDBAuthError):
            client.issue(1)
    finally:
        client.close()
    assert not outcome_stats.api_snapshot()["versedb"].unthrottled


def test_sdk_endpoints_still_take_the_keywords_comicbox_passes() -> None:
    """
    Drift guard: the SDK is generated and renames follow its summaries.

    A regeneration that renames a function or a keyword fails here, at
    dependency-update time, instead of in a user's tagging run.
    """
    available = endpoint_keywords()
    for name, used in USED_KEYWORDS.items():
        assert used <= available[name], (name, sorted(used - available[name]))


def test_a_failing_cache_still_returns_the_fetched_payload(
    make_client, tmp_path: Path
) -> None:
    """The 200 already paid for is returned; nothing is sent twice."""
    cache = ResponseCache(tmp_path / "c.sqlite", timedelta(days=1))
    client, transport = make_client(cache=cache)
    # Every read and write now fails, as on a locked or full disk.
    cache._conn.close()
    assert client.issue(1215061)["data"]["id"] == 1215061
    assert len(transport.requests) == 1


def test_a_corrupt_cached_body_is_a_miss(make_client, tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite", timedelta(days=1))
    client, transport = make_client(cache=cache)
    client.issue(1)
    for key in [row[0] for row in cache._conn.execute("SELECT key FROM responses")]:
        cache.set(key, b"{not json")
    assert client.issue(1)["data"]["id"] == 1
    assert len(transport.requests) == 2


def test_a_retry_after_past_the_ceiling_stops_asking(make_client) -> None:
    """
    A daily-cap 429 (hours of Retry-After) is not a wait worth retrying.

    The retry layer would sleep its one-hour ceiling, be refused again, and
    give up, and so would every comic after. Instead VerseDB stops being
    asked, without sleeping, until the wait has passed.
    """
    reply = Reply(
        {"message": "Too Many Attempts."}, status=429, headers={"Retry-After": "18000"}
    )
    client, transport = make_client(_always(reply))
    with pytest.raises(VerseDBQuotaError, match="request limit is reached") as exc_info:
        client.issue(1)
    assert exc_info.value.resume_at > time.time() + 17000
    with pytest.raises(VerseDBQuotaError):
        client.issue(2)
    assert len(transport.requests) == 1


def test_a_retry_after_within_the_ceiling_is_still_a_rate_limit(make_client) -> None:
    reply = Reply({"message": "x"}, status=429, headers={"Retry-After": "600"})
    client, _ = make_client(_always(reply))
    with pytest.raises(VerseDBRateLimitError):
        client.issue(1)


def test_request_counts_name_the_endpoint_not_the_issue(make_client) -> None:
    """A batch of fetches is one summary line, not one per comic."""
    outcome_stats.reset()
    client, _ = make_client()
    client.issue(1)
    client.issue(2)
    client.search_series("Absolute Bladehawk", 10)
    client.list_issues((139382,), "1")
    assert outcome_stats.api_snapshot()["versedb"].requests == {
        "issues": 2,
        "series_list": 1,
        "issues_list": 1,
    }


def test_a_send_with_no_response_counts_as_a_connection_failure() -> None:
    outcome_stats.reset()

    def refuse(request: httpx.Request) -> httpx.Response:
        msg = "refused"
        raise httpx.ConnectError(msg, request=request)

    client = VerseDBClient("t", user_agent="t", transport=httpx.MockTransport(refuse))
    try:
        with pytest.raises(httpx.ConnectError):
            client.issue(1)
    finally:
        client.close()
    assert outcome_stats.api_snapshot()["versedb"].connection_failures == 1


def test_an_empty_answer_is_cached_for_a_day_only(
    make_client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """So a series or issue VerseDB adds tomorrow is found tomorrow."""
    monkeypatch.setattr("comicbox.formats.versedb_api.cache.time.time", lambda: 1000.0)
    cache = ResponseCache(tmp_path / "c.sqlite", timedelta(0))
    empty = fixture("series_search")
    empty["data"] = []
    client, transport = make_client(_always(Reply(empty)), cache=cache)
    client.search_series("Nonesuch", 10)
    client.search_series("Nonesuch", 10)
    assert len(transport.requests) == 1
    monkeypatch.setattr(
        "comicbox.formats.versedb_api.cache.time.time", lambda: 1000.0 + 86_401
    )
    client.search_series("Nonesuch", 10)
    assert len(transport.requests) == 2


def test_the_cache_key_carries_the_base_url(tmp_path: Path) -> None:
    """Every credential set shares the file, so another server's answer is a miss."""
    transport = VerseDBTransport()
    clients = [
        VerseDBClient(
            "t",
            user_agent="t",
            base_url=base_url,
            cache=ResponseCache(tmp_path / "c.sqlite", timedelta(days=1)),
            transport=transport.transport,
        )
        for base_url in ("https://versedb.com", "https://staging.versedb.example")
    ]
    try:
        for client in clients:
            client.issue(1)
    finally:
        for client in clients:
            client.close()
    assert len(transport.requests) == 2


def test_a_bare_403_is_named_as_refused_in_front_of_the_api() -> None:
    """Behind Cloudflare, a 403 without VerseDB's headers is not the token's fault."""
    outcome_stats.reset()
    transport = VerseDBTransport(_always(Reply({"message": "x"}, 403, {})))
    client = VerseDBClient("t", user_agent="t", transport=transport.transport)
    try:
        with pytest.raises(VerseDBAuthError, match="proxy or bot check"):
            client.issue(1)
    finally:
        client.close()
    assert outcome_stats.api_snapshot()["versedb"].unthrottled == {403: 1}


def test_a_403_from_the_api_names_the_token_scope(make_client) -> None:
    client, _ = make_client(
        _always(Reply({"message": "This action is unauthorized."}, 403))
    )
    with pytest.raises(VerseDBAuthError, match="lack a scope"):
        client.issue(1)
