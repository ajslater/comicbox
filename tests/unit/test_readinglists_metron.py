"""
Metron reading lists and arcs, through the real mokkari stack.

The shared paced session is built exactly as tagging builds it, response
cache and rate gate included; only its transport is fake.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

import pytest
from requests import exceptions as requests_exceptions

from comicbox.config.online.settings import OnlineAuthSettings, OnlineSourceCredentials
from comicbox.events import (
    Event,
    ReadingListFetchFinished,
    ReadingListFetchProgress,
    ReadingListFetchStarted,
)
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.metron_api import online_source as metron
from comicbox.formats.metron_api.online_source import MetronOnlineSource
from comicbox.online_session import OnlineCredentials
from comicbox.readinglists import (
    MetronListSummary,
    ReadingListFetchError,
    ReadingListSession,
)
from tests.util.metron_transport import (
    FakeAdapter,
    Reply,
    arc_detail,
    connection_error,
    install,
    issue_page,
    issue_row,
    reading_list_detail,
    reading_list_item,
    reading_list_row,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    import requests

    from comicbox.formats.base.online.rate_gate import RateGate

_TOKEN = "t"
_API = "https://metron.cloud/api"
_ITEMS = f"{_API}/reading_list/1/items/"
_NOT_FOUND = Reply({"detail": "Not found."}, status_code=404)


def _routes(routes: Mapping[str, Reply]) -> Callable[[requests.PreparedRequest], Reply]:
    """Answer each path, with its query, from ``routes``; anything else 404s."""

    def reply(request: requests.PreparedRequest) -> Reply:
        url = urlsplit(request.url or "")
        path = url.path.removeprefix("/api")
        return routes.get(f"{path}?{url.query}" if url.query else path, _NOT_FOUND)

    return reply


def _three_pages() -> dict[str, Reply]:
    """Serve a list of five items over three pages; item 4 has no order."""
    rows = [
        [reading_list_item(1, 1), reading_list_item(2, 2)],
        [reading_list_item(3, 3), reading_list_item(4, None)],
        [reading_list_item(5, 4)],
    ]
    return {
        "/reading_list/1/": Reply(reading_list_detail()),
        "/reading_list/1/items/": Reply(issue_page(rows[0], f"{_ITEMS}?page=2", 5)),
        "/reading_list/1/items/?page=2": Reply(
            issue_page(rows[1], f"{_ITEMS}?page=3", 5, _ITEMS)
        ),
        "/reading_list/1/items/?page=3": Reply(
            issue_page(rows[2], None, 5, f"{_ITEMS}?page=2")
        ),
    }


def _unrouted(request: requests.PreparedRequest) -> Reply:
    reason = f"a request no fake answers: {request.url}"
    raise AssertionError(reason)


@pytest.fixture(autouse=True)
def route_new_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[requests.PreparedRequest], Reply]], None]:
    """
    Mount a fake transport on every mokkari session built here.

    A request no test routed fails the test instead of reaching Metron.
    The returned setter routes the sessions built after it.
    """
    from comicbox.formats.metron_api import paced_session

    router: list[Callable[[requests.PreparedRequest], Reply]] = [_unrouted]
    build = paced_session.build_paced_session

    def routed(request: requests.PreparedRequest) -> Reply:
        return router[0](request)

    def build_routed(gate: Any, **kwargs: Any) -> Any:
        built = build(gate, **kwargs)
        install(built, routed)
        return built

    monkeypatch.setattr(paced_session, "build_paced_session", build_routed)

    def route(replies: Callable[[requests.PreparedRequest], Reply]) -> None:
        router[0] = replies

    return route


@pytest.fixture
def events() -> list[Event]:
    return []


@pytest.fixture
def session(events: list[Event]) -> Iterator[ReadingListSession]:
    credentials = OnlineCredentials(metron_key=_TOKEN)
    with ReadingListSession(credentials=credentials, on_event=events.append) as rl:
        yield rl


def _shared_source(session: ReadingListSession) -> MetronOnlineSource:
    return MetronOnlineSource(
        OnlineSourceCredentials(key=_TOKEN), session.settings.online
    )


def _serve(session: ReadingListSession, routes: Mapping[str, Reply]) -> FakeAdapter:
    """Mount a fake transport on the token's shared mokkari session."""
    return install(_shared_source(session).session(), _routes(routes))


def _gate(session: ReadingListSession) -> RateGate:
    gate = _shared_source(session)._gate()
    assert gate is not None
    return gate


def _paths(adapter: FakeAdapter) -> list[str]:
    return [url.removeprefix(_API) for url in adapter.urls]


def _keys(result: Any) -> list[str]:
    return [entry["identifiers"]["metron"]["key"] for entry in result["entries"]]


# ----------------------------------------------------------------- lists


def test_items_arrive_in_pages_with_progress(
    session: ReadingListSession, events: list[Event]
) -> None:
    adapter = _serve(session, _three_pages())

    result = session.fetch_metron_list(1)

    assert result is not None
    assert _paths(adapter) == [
        "/reading_list/1/",
        "/reading_list/1/items/",
        "/reading_list/1/items/?page=2",
        "/reading_list/1/items/?page=3",
    ]
    progress = [
        (e.index, e.total) for e in events if type(e) is ReadingListFetchProgress
    ]
    assert progress == [(2, 5), (4, 5), (5, 5)]
    assert type(events[0]) is ReadingListFetchStarted
    assert type(events[-1]) is ReadingListFetchFinished
    assert events[0] == ReadingListFetchStarted(source="metron-list", key="1")


def test_items_run_in_order_with_unordered_items_last(
    session: ReadingListSession,
) -> None:
    _serve(session, _three_pages())

    result = session.fetch_metron_list(1)

    assert result is not None
    assert _keys(result.reading_list) == ["1", "2", "3", "5", "4"]


def test_a_list_maps_to_the_model(session: ReadingListSession) -> None:
    routes = _three_pages()
    routes["/reading_list/1/"] = Reply(
        reading_list_detail(
            previous={"id": 9, "name": "House of Q"},
            next={"id": 11, "name": "World War Hurler"},
        )
    )
    _serve(session, routes)

    result = session.fetch_metron_list(1)

    assert result is not None
    assert result.fmt is None
    assert result.warnings == ()
    reading_list = dict(result.reading_list)
    entries = reading_list.pop("entries")
    assert reading_list == {
        "name": "Crimson Tide",
        "description": "The Superhuman Registration Act divides them.",
        "list_type": "event",
        "ordered": True,
        "sources": [
            {
                "kind": "metron-list",
                "key": "1",
                "url": "https://metron.cloud/reading-lists/1/",
                "revision": "2024-05-01T12:00:00-04:00",
                "curator": "cbro",
                "curator_url": "https://www.comicbookreadingorders.com/marvel/events/crimson-tide/",
            }
        ],
        "previous": {"name": "House of Q", "kind": "metron-list", "key": "9"},
        "next": {"name": "World War Hurler", "kind": "metron-list", "key": "11"},
    }
    assert entries[0] == {
        "series": {
            "name": "Crimson Tide",
            "start_year": 2006,
            "identifiers": {"metron": {"key": "7"}},
        },
        "volume": {"number": 1},
        "issue": {"name": "1"},
        "date": {
            "cover_date": datetime(2006, 7, 1, tzinfo=UTC).date(),
            "store_date": datetime(2006, 5, 3, tzinfo=UTC).date(),
        },
        "identifiers": {"metron": {"key": "1"}, "comicvine": {"key": "1001"}},
        "entry_type": "core",
    }


def test_a_private_list_says_so(session: ReadingListSession) -> None:
    routes = _three_pages()
    routes["/reading_list/1/"] = Reply(reading_list_detail(is_private=True))
    _serve(session, routes)

    result = session.fetch_metron_list(1)

    assert result is not None
    assert result.reading_list["private"] is True


def test_a_public_list_has_no_private_key(session: ReadingListSession) -> None:
    _serve(session, _three_pages())

    result = session.fetch_metron_list(1)

    assert result is not None
    assert "private" not in result.reading_list


def test_a_list_without_attribution_has_no_curator(
    session: ReadingListSession,
) -> None:
    routes = _three_pages()
    routes["/reading_list/1/"] = Reply(
        reading_list_detail(attribution_source="", attribution_url="")
    )
    _serve(session, routes)

    result = session.fetch_metron_list(1)

    assert result is not None
    (source,) = result.reading_list["sources"]
    assert "curator" not in source
    assert "curator_url" not in source


def test_an_unchanged_list_fetches_no_items(
    session: ReadingListSession, events: list[Event]
) -> None:
    adapter = _serve(session, {"/reading_list/1/": Reply(status_code=304)})

    result = session.fetch_metron_list(
        1, if_modified_since=datetime(2024, 6, 1, tzinfo=UTC)
    )

    assert result is None
    assert _paths(adapter) == ["/reading_list/1/"]
    assert [type(event) for event in events] == [
        ReadingListFetchStarted,
        ReadingListFetchFinished,
    ]


def test_a_second_fetch_is_served_from_the_cache(session: ReadingListSession) -> None:
    """The shared session's response cache serves lists too: no progress."""
    adapter = _serve(session, _three_pages())
    first = session.fetch_metron_list(1)
    requests_made = len(adapter.urls)

    second = session.fetch_metron_list(1)

    assert second == first
    assert len(adapter.urls) == requests_made


# ------------------------------------------------------------------ arcs


def test_an_arc_is_an_unordered_story_list(session: ReadingListSession) -> None:
    adapter = _serve(
        session,
        {
            "/arc/5/": Reply(arc_detail()),
            "/arc/5/issue_list/": Reply(issue_page([issue_row(1), issue_row(2)])),
        },
    )

    result = session.fetch_metron_arc(5)

    assert result is not None
    assert _paths(adapter) == ["/arc/5/", "/arc/5/issue_list/"]
    reading_list = result.reading_list
    assert reading_list["name"] == "Crimson Tide"
    assert reading_list["description"] == "Hero against hero."
    assert reading_list["list_type"] == "story"
    assert reading_list["ordered"] is False
    assert reading_list["sources"] == [
        {
            "kind": "metron-arc",
            "key": "5",
            "url": "https://metron.cloud/arc/crimson-tide-5/",
            "revision": "2024-05-01T12:00:00-04:00",
        },
        {"kind": "comicvine-arc", "key": "40000"},
    ]
    # Metron ids only: an arc's issue list carries no others (F8).
    assert [entry["identifiers"] for entry in reading_list["entries"]] == [
        {"metron": {"key": "1"}},
        {"metron": {"key": "2"}},
    ]
    assert result.warnings == ()


def test_an_arc_without_a_comic_vine_id_has_one_source(
    session: ReadingListSession,
) -> None:
    _serve(
        session,
        {
            "/arc/5/": Reply(arc_detail(cv_id=None)),
            "/arc/5/issue_list/": Reply(issue_page([issue_row(1)])),
        },
    )

    result = session.fetch_metron_arc(5)

    assert result is not None
    assert [source["kind"] for source in result.reading_list["sources"]] == [
        "metron-arc"
    ]


def test_an_unchanged_arc_fetches_no_issues(session: ReadingListSession) -> None:
    adapter = _serve(session, {"/arc/5/": Reply(status_code=304)})

    assert (
        session.fetch_metron_arc(5, if_modified_since=datetime(2024, 6, 1, tzinfo=UTC))
        is None
    )
    assert _paths(adapter) == ["/arc/5/"]


# ---------------------------------------------------------------- search


def test_search_sends_mokkari_filter_names(session: ReadingListSession) -> None:
    seen: list[str] = []

    def answer(request: requests.PreparedRequest) -> Reply:
        seen.append(request.url or "")
        return Reply(issue_page([reading_list_row(1), reading_list_row(2)]))

    install(_shared_source(session).session(), answer)

    found = session.search_metron(
        name="crimson tide",
        curator="cbro",
        username="curator",
        modified_since=datetime(2024, 1, 1, tzinfo=UTC),
    )

    (url,) = seen
    assert urlsplit(url).path == "/api/reading_list/"
    assert parse_qs(urlsplit(url).query) == {
        "name": ["crimson tide"],
        "attribution_source": ["CBRO"],
        "username": ["curator"],
        "modified_gt": ["2024-01-01T00:00:00+00:00"],
    }
    assert [summary.id for summary in found] == [1, 2]
    assert found[0] == MetronListSummary(
        id=1,
        name="Crimson Tide",
        list_type="Event",
        private=False,
        curator="cbro",
        username="curator",
        rating=4.5,
        rating_count=2,
        modified=found[0].modified,
    )


# ---------------------------------------------------------------- cancel


def test_a_cancel_between_pages_stops_the_fetch(
    session: ReadingListSession, events: list[Event]
) -> None:
    """The first page's progress cancels; the second page is never sent."""
    adapter = _serve(session, _three_pages())

    def cancel_on_progress(event: Event) -> None:
        events.append(event)
        if type(event) is ReadingListFetchProgress:
            session.cancel()

    session._on_event = cancel_on_progress

    with pytest.raises(OnlineLookupAbortedError):
        session.fetch_metron_list(1)

    assert _paths(adapter) == ["/reading_list/1/", "/reading_list/1/items/"]
    assert _gate(session)._in_flight == 0
    assert type(events[-1]) is ReadingListFetchFinished


def test_a_cancel_during_the_gate_wait_releases_the_slot(
    session: ReadingListSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cancel that arrives while a send waits at the gate frees its slot."""
    adapter = _serve(session, _three_pages())
    gate = _gate(session)
    acquire = gate.acquire

    def acquire_then_cancel(abort: Callable[[], bool] | None = None) -> float:
        admitted = acquire(abort)
        session.cancel()
        return admitted

    monkeypatch.setattr(gate, "acquire", acquire_then_cancel)

    with pytest.raises(OnlineLookupAbortedError):
        session.fetch_metron_list(1)

    assert adapter.urls == []
    assert gate._in_flight == 0
    # Nothing was sent, so nothing is counted and no slot is held.
    assert gate.stats().sends == 0
    assert not gate._slots


def test_a_cancel_inside_a_gate_wait_is_not_sat_out(
    session: ReadingListSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A4: a cancel sent while a send waited at a full gate waited up to a minute."""
    adapter = _serve(session, _three_pages())
    gate = _gate(session)
    gate.observe(burst_limit=1, burst_remaining=1)
    gate.acquire()  # spend the window's only slot
    gate.release()
    acquire = gate.acquire
    entered = threading.Event()

    def acquire_once_entered(abort: Callable[[], bool] | None = None) -> float:
        entered.set()
        return acquire(abort)

    monkeypatch.setattr(gate, "acquire", acquire_once_entered)
    raised: list[OnlineLookupAbortedError] = []

    def fetch() -> None:
        try:
            session.fetch_metron_list(1)
        except OnlineLookupAbortedError as exc:
            raised.append(exc)

    worker = threading.Thread(target=fetch, daemon=True)
    worker.start()
    assert entered.wait(5)
    session.cancel()
    worker.join(5)

    assert not worker.is_alive()
    assert len(raised) == 1
    assert adapter.urls == []
    assert gate._in_flight == 0
    assert gate.stats().sends == 1


def test_a_cancelled_session_sends_nothing(session: ReadingListSession) -> None:
    adapter = _serve(session, _three_pages())
    session.cancel()

    with pytest.raises(OnlineLookupAbortedError):
        session.fetch_metron_list(1)
    with pytest.raises(OnlineLookupAbortedError):
        session.search_metron(name="x")

    assert adapter.urls == []


# ---------------------------------------------------------------- errors


@pytest.mark.parametrize(
    "call",
    [
        lambda rl: rl.fetch_metron_list(1),
        lambda rl: rl.fetch_metron_arc(5),
        lambda rl: rl.search_metron(name="x"),
    ],
    ids=["list", "arc", "search"],
)
def test_no_token_raises_before_any_request(
    call: Callable[[ReadingListSession], Any],
) -> None:
    """Nothing is built or sent, and no fetch is said to have begun."""
    events: list[Event] = []
    with (
        ReadingListSession(on_event=events.append) as rl,
        pytest.raises(ReadingListFetchError, match="Metron needs an API token"),
    ):
        call(rl)
    assert metron._session_cache == {}
    assert events == []


def test_the_config_token_is_used_without_credentials() -> None:
    with ReadingListSession() as rl:
        online = rl.settings.online
        auth = OnlineAuthSettings(sources={"metron": OnlineSourceCredentials(_TOKEN)})
        rl._settings = replace(rl.settings, online=replace(online, auth=auth))
        adapter = _serve(rl, _three_pages())

        assert rl.fetch_metron_list(1) is not None
        assert len(adapter.urls) == 4


def test_a_missing_list_is_one_fetch_error(session: ReadingListSession) -> None:
    _serve(session, {})

    with pytest.raises(ReadingListFetchError) as caught:
        session.fetch_metron_list(9)

    assert str(caught.value) == "Metron reading list 9: HTTP 404 Not Found."


def test_a_refused_token_says_why(session: ReadingListSession) -> None:
    refused = Reply({"detail": "Invalid token."}, status_code=401)
    _serve(session, {"/reading_list/1/": refused})

    with pytest.raises(ReadingListFetchError) as caught:
        session.fetch_metron_list(1)

    assert str(caught.value) == (
        "Metron reading list 1: HTTP 401 Unauthorized: Invalid token."
    )


@pytest.mark.parametrize(
    ("status", "message"),
    [(520, "HTTP 520."), (404, "HTTP 404 Not Found.")],
)
def test_a_status_with_or_without_a_phrase_is_one_fetch_error(
    session: ReadingListSession, status: int, message: str
) -> None:
    # 520 is no HTTPStatus member; ``status in HTTPStatus`` raised TypeError
    # on Python 3.11 instead of giving the fetch error.
    _serve(session, {"/reading_list/1/": Reply({}, status_code=status)})

    with pytest.raises(ReadingListFetchError) as caught:
        session.fetch_metron_list(1)

    assert str(caught.value) == f"Metron reading list 1: {message}"


def test_a_connection_failure_is_one_fetch_error(session: ReadingListSession) -> None:
    install(_shared_source(session).session(), [connection_error("refused")])

    with pytest.raises(ReadingListFetchError, match=r"^Metron reading list 1: ") as e:
        session.fetch_metron_list(1)

    assert "\n" not in str(e.value)


# ------------------------------------------------- a changed list (E1)


class _Changing:
    """
    A Metron whose list and arc gain an issue at a known time.

    It honours If-Modified-Since, as Metron does, so a conditional fetch of
    the old version gets a 304 and one of the new version does not.
    """

    _BEFORE = "2024-05-01T12:00:00-04:00"
    _AFTER = "2024-06-01T12:00:00-04:00"

    def __init__(self) -> None:
        self.changed = False
        self.paths: list[tuple[str, bool]] = []

    @property
    def modified(self) -> str:
        return self._AFTER if self.changed else self._BEFORE

    def _issues(self) -> list[int]:
        return [1, 2, 3] if self.changed else [1, 2]

    def _unchanged_since(self, request: requests.PreparedRequest) -> bool:
        from email.utils import parsedate_to_datetime

        since = request.headers.get("If-Modified-Since")
        if not isinstance(since, str):
            return False
        return datetime.fromisoformat(self.modified) <= parsedate_to_datetime(since)

    def __call__(self, request: requests.PreparedRequest) -> Reply:
        path = urlsplit(request.url or "").path.removeprefix("/api")
        self.paths.append((path, "If-Modified-Since" in request.headers))
        if path in {"/reading_list/1/", "/arc/5/"} and self._unchanged_since(request):
            return Reply(status_code=304)
        match path:
            case "/reading_list/1/":
                return Reply(reading_list_detail(modified=self.modified))
            case "/reading_list/1/items/":
                rows = [reading_list_item(n, n) for n in self._issues()]
                return Reply(issue_page(rows))
            case "/arc/5/":
                return Reply(arc_detail(modified=self.modified))
            case "/arc/5/issue_list/":
                return Reply(issue_page([issue_row(n) for n in self._issues()]))
            case _:
                return _NOT_FOUND


_SINCE = datetime(2024, 5, 2, tzinfo=UTC)


@pytest.mark.parametrize(
    ("fetch", "header_path", "items_path"),
    [
        (
            lambda rl, since: rl.fetch_metron_list(1, if_modified_since=since),
            "/reading_list/1/",
            "/reading_list/1/items/",
        ),
        (
            lambda rl, since: rl.fetch_metron_arc(5, if_modified_since=since),
            "/arc/5/",
            "/arc/5/issue_list/",
        ),
    ],
    ids=["list", "arc"],
)
def test_a_changed_list_comes_with_its_new_items(
    session: ReadingListSession,
    route_new_sessions: Callable[[Any], None],
    fetch: Callable[[ReadingListSession, datetime | None], Any],
    header_path: str,
    items_path: str,
) -> None:
    """
    A list found changed never pairs its new header with cached items.

    The first fetch warms the cache. After the change, a conditional fetch
    gets the new header and all three issues from Metron; a plain fetch
    after that is served whole from the cache, so the cache was left fresh.
    """
    metron = _Changing()
    route_new_sessions(metron)
    install(_shared_source(session).session(), metron)
    assert _keys(fetch(session, None).reading_list) == ["1", "2"]
    assert fetch(session, _SINCE) is None  # Unchanged: a 304, no items.
    metron.changed = True
    metron.paths.clear()

    changed = fetch(session, _SINCE)

    assert changed is not None
    assert _keys(changed.reading_list) == ["1", "2", "3"]
    revision = changed.reading_list["sources"][0]["revision"]
    assert revision == "2024-06-01T12:00:00-04:00"
    assert metron.paths == [
        (header_path, True),
        (header_path, False),
        (items_path, False),
    ]
    metron.paths.clear()
    cached = fetch(session, None)
    assert metron.paths == []
    assert _keys(cached.reading_list) == ["1", "2", "3"]
    assert cached.reading_list["sources"][0]["revision"] == revision


def test_a_changed_list_shares_the_gate(
    session: ReadingListSession, route_new_sessions: Callable[[Any], None]
) -> None:
    """The refetch queues at the token's gate and leaves nothing in flight."""
    metron = _Changing()
    route_new_sessions(metron)
    install(_shared_source(session).session(), metron)
    session.fetch_metron_list(1)
    metron.changed = True
    gate = _gate(session)
    sends = gate.stats().sends

    session.fetch_metron_list(1, if_modified_since=_SINCE)

    assert gate.stats().sends == sends + 3
    assert gate._in_flight == 0


# ------------------------------------------- every failure (R2-E E6)


@pytest.mark.parametrize(
    "error",
    [
        requests_exceptions.ChunkedEncodingError("broken chunk"),
        requests_exceptions.ContentDecodingError("bad gzip"),
        requests_exceptions.TooManyRedirects("loop"),
    ],
    ids=["chunked", "decoding", "redirects"],
)
def test_a_transport_error_is_one_fetch_error(
    session: ReadingListSession, error: Exception
) -> None:
    install(_shared_source(session).session(), [Reply(error=error)])

    with pytest.raises(ReadingListFetchError, match=r"^Metron reading list 1: ") as e:
        session.fetch_metron_list(1)

    assert "\n" not in str(e.value)


def test_a_cancel_during_the_last_request_returns_no_list(
    session: ReadingListSession,
) -> None:
    """The last page arrives after the cancel; the list is not returned."""
    routes = _three_pages()
    last = routes["/reading_list/1/items/?page=3"]

    def cancel_then_answer(request: requests.PreparedRequest) -> Reply:
        if (request.url or "").endswith("?page=3"):
            session.cancel()
            return last
        return _routes(routes)(request)

    install(_shared_source(session).session(), cancel_then_answer)

    with pytest.raises(OnlineLookupAbortedError):
        session.fetch_metron_list(1)
