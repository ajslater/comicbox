"""
Comic Vine story arcs as reading lists.

Most tests fake simyan's ``Comicvine`` (``tests.util.comicvine_fake``), so
the shared-client path runs as it does for tagging. The last section runs
the real simyan stack over a fake HTTP transport, for what only it decides:
how the id filter goes out, and what a missing arc's 200 looks like.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from io import BytesIO
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from mokkari.schemas.arc import Arc
from mokkari.schemas.issue import BaseIssue
from requests.adapters import HTTPAdapter
from requests.structures import CaseInsensitiveDict
from simyan.errors import AuthenticationError, RateLimitError, ServiceError
from urllib3.response import HTTPResponse

from comicbox.config.online.settings import OnlineAuthSettings, OnlineSourceCredentials
from comicbox.events import (
    Event,
    ReadingListFetchFinished,
    ReadingListFetchProgress,
    ReadingListFetchStarted,
)
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.comicvine_api import online_source as comicvine
from comicbox.formats.comicvine_api.online_source import ComicVineOnlineSource
from comicbox.online_session import OnlineCredentials
from comicbox.readinglists import (
    ReadingListFetchError,
    ReadingListSession,
    combine,
    dumps,
    loads,
)
from comicbox.readinglists.formats.metron_api import reading_list_from_metron_arc
from comicbox.readinglists.registry import get_format
from comicbox.validate.spec import build_validator
from tests.util import metron_transport
from tests.util.comicvine_fake import (
    FakeComicvine,
    arc_row,
    install,
    issue_row,
    volume_row,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_KEY = "k"


@pytest.fixture
def cv(monkeypatch: pytest.MonkeyPatch) -> FakeComicvine:
    return install(monkeypatch)


@pytest.fixture
def events() -> list[Event]:
    return []


@pytest.fixture
def session(events: list[Event]) -> Iterator[ReadingListSession]:
    credentials = OnlineCredentials(comicvine_key=_KEY)
    with ReadingListSession(credentials=credentials, on_event=events.append) as rl:
        yield rl


def _crimson_tide(cv: FakeComicvine) -> None:
    """Serve an arc of two issues in one volume."""
    cv.serve(arc_row([1, 2]), [issue_row(1), issue_row(2)], [volume_row(7)])


def _keys(reading_list: dict[str, Any]) -> list[str]:
    return [
        entry["identifiers"]["comicvine"]["key"] for entry in reading_list["entries"]
    ]


# ------------------------------------------------------------------ arcs


def test_an_arc_is_an_unordered_story_list(
    session: ReadingListSession, cv: FakeComicvine
) -> None:
    _crimson_tide(cv)

    reading_list = session.fetch_comicvine_arc(12).reading_list

    assert reading_list["name"] == "Crimson Tide"
    assert reading_list["description"] == "Hero against hero."
    assert reading_list["list_type"] == "story"
    assert reading_list["ordered"] is False
    assert reading_list["sources"] == [
        {
            "kind": "comicvine-arc",
            "key": "12",
            "url": "https://comicvine.gamespot.com/crimson-tide/4045-12/",
            "revision": "2024-05-01T12:00:00",
        }
    ]


def test_an_arc_is_three_calls_from_started_to_finished(
    session: ReadingListSession, cv: FakeComicvine, events: list[Event]
) -> None:
    """The arc, its issues and their volumes; with no format, and no warning."""
    _crimson_tide(cv)

    result = session.fetch_comicvine_arc(12)

    assert result.fmt is None
    assert result.warnings == ()
    assert cv.calls == [
        ("get_story_arc", 12),
        ("list_issues", "id:1|2", 2),
        ("list_volumes", "id:7", 1),
    ]
    assert events[0] == ReadingListFetchStarted(source="comicvine-arc", key="12")
    assert type(events[-1]) is ReadingListFetchFinished


def test_enriched_entries_carry_series_number_dates_and_ids(
    session: ReadingListSession, cv: FakeComicvine
) -> None:
    _crimson_tide(cv)

    entry = session.fetch_comicvine_arc(12).reading_list["entries"][0]

    # The story title is nowhere: an entry has no place for one.
    assert entry == {
        "series": {
            "name": "Crimson Tide",
            "start_year": 2006,
            "identifiers": {"comicvine": {"key": "7"}},
        },
        "issue": {"name": "1"},
        "date": {"cover_date": date(2006, 7, 1), "store_date": date(2006, 5, 3)},
        "identifiers": {"comicvine": {"key": "1"}},
    }


def test_an_issue_no_row_came_for_keeps_its_entry(
    session: ReadingListSession, cv: FakeComicvine
) -> None:
    cv.serve(arc_row([1, 2, 3]), [issue_row(1), issue_row(3)], [volume_row(7)])

    entries = session.fetch_comicvine_arc(12).reading_list["entries"]

    assert _keys({"entries": entries}) == ["1", "2", "3"]
    assert entries[1] == {"identifiers": {"comicvine": {"key": "2"}}}


def test_a_volume_no_row_came_for_names_the_series_from_the_issue(
    session: ReadingListSession, cv: FakeComicvine
) -> None:
    cv.serve(arc_row([1]), [issue_row(1, volume_id=8, volume_name="Front Line")])

    entry = session.fetch_comicvine_arc(12).reading_list["entries"][0]

    assert entry["series"] == {
        "name": "Front Line",
        "identifiers": {"comicvine": {"key": "8"}},
    }


def test_an_arc_with_no_description_takes_its_deck(
    session: ReadingListSession, cv: FakeComicvine
) -> None:
    cv.serve(arc_row([], description=None))

    reading_list = session.fetch_comicvine_arc(12).reading_list

    assert reading_list["description"] == "Heroes fight."
    assert cv.calls == [("get_story_arc", 12)]


def test_issues_and_volumes_go_a_hundred_a_call(
    session: ReadingListSession, cv: FakeComicvine, events: list[Event]
) -> None:
    """250 issues in 250 volumes: one arc call, three of each kind."""
    ids = list(range(1, 251))
    cv.serve(
        arc_row(ids),
        [issue_row(id_, volume_id=1000 + id_) for id_ in ids],
        [volume_row(1000 + id_) for id_ in ids],
    )

    result = session.fetch_comicvine_arc(12)

    def id_filter(values: range) -> str:
        return "id:" + "|".join(str(value) for value in values)

    assert cv.calls == [
        ("get_story_arc", 12),
        ("list_issues", id_filter(range(1, 101)), 100),
        ("list_issues", id_filter(range(101, 201)), 100),
        ("list_issues", id_filter(range(201, 251)), 50),
        ("list_volumes", id_filter(range(1001, 1101)), 100),
        ("list_volumes", id_filter(range(1101, 1201)), 100),
        ("list_volumes", id_filter(range(1201, 1251)), 50),
    ]
    progress = [
        (event.index, event.total)
        for event in events
        if type(event) is ReadingListFetchProgress
    ]
    assert progress == [(100, 250), (200, 250), (250, 250)]
    assert len(result.reading_list["entries"]) == 250


def test_an_issue_listed_twice_is_asked_for_once(
    session: ReadingListSession, cv: FakeComicvine
) -> None:
    cv.serve(arc_row([1, 2, 1]), [issue_row(1), issue_row(2)], [volume_row(7)])

    session.fetch_comicvine_arc(12)

    assert ("list_issues", "id:1|2", 2) in cv.calls


def test_the_list_round_trips_and_validates(
    session: ReadingListSession, cv: FakeComicvine
) -> None:
    cv.serve(arc_row([1, 2, 3]), [issue_row(1), issue_row(3)], [volume_row(7)])
    reading_list = session.fetch_comicvine_arc(12).reading_list

    text = dumps(reading_list, "json")
    spec = get_format("json").value.validator_spec
    assert spec is not None
    build_validator(spec).validate(text)
    assert loads(text).reading_list == reading_list
    assert loads(dumps(reading_list, "yaml")).reading_list == reading_list


def test_combine_links_it_with_the_metron_arc_by_name_number_and_start_year(
    session: ReadingListSession, cv: FakeComicvine
) -> None:
    """
    Metron's arc carries Metron ids alone, so only the descriptions can join.

    With no cover dates here, the year is the start year the volume call
    gave: without that call these rows join nothing.
    """

    def undated(issue_id: int) -> dict[str, Any]:
        return issue_row(
            issue_id, volume_name="Test Series", cover_date=None, store_date=None
        )

    cv.serve(
        arc_row([101, 102]),
        [undated(101), undated(102)],
        [volume_row(7, name="Test Series", start_year="2020")],
    )
    comic_vine = session.fetch_comicvine_arc(12).reading_list
    rows = [metron_transport.issue_row(1), metron_transport.issue_row(2)]
    rows[0]["number"], rows[1]["number"] = "101", "102"
    metron = reading_list_from_metron_arc(
        Arc.model_validate(metron_transport.arc_detail()),
        [BaseIssue.model_validate(row) for row in rows],
    ).reading_list

    combined = combine([metron, comic_vine]).reading_list

    assert [entry["identifiers"] for entry in combined["entries"]] == [
        {"comicvine": {"key": "101"}, "metron": {"key": "1"}},
        {"comicvine": {"key": "102"}, "metron": {"key": "2"}},
    ]


# --------------------------------------------------------- the shared client


def test_the_fetch_shares_taggings_client_and_leaves_it_open(
    session: ReadingListSession, cv: FakeComicvine
) -> None:
    _crimson_tide(cv)
    tagging = ComicVineOnlineSource(
        OnlineSourceCredentials(key=_KEY), session.settings.online
    )
    client = tagging._get_session()

    session.fetch_comicvine_arc(12)
    session.close()

    assert client is cv
    assert cv.built == 1
    assert cv.closed == 0


# ---------------------------------------------------------------- cancels


def test_a_cancel_between_calls_stops_the_fetch(
    session: ReadingListSession, cv: FakeComicvine
) -> None:
    _crimson_tide(cv)

    def cancel_after_the_arc(method: str) -> None:
        if method == "get_story_arc":
            session.cancel()

    cv.before = cancel_after_the_arc

    with pytest.raises(OnlineLookupAbortedError):
        session.fetch_comicvine_arc(12)
    assert cv.calls == [("get_story_arc", 12)]


def test_a_cancel_during_the_last_call_returns_no_list(
    session: ReadingListSession, cv: FakeComicvine
) -> None:
    _crimson_tide(cv)

    def cancel_during_volumes(method: str) -> None:
        if method == "list_volumes":
            session.cancel()

    cv.before = cancel_during_volumes

    with pytest.raises(OnlineLookupAbortedError):
        session.fetch_comicvine_arc(12)
    assert [call[0] for call in cv.calls][-1] == "list_volumes"


def test_a_cancelled_session_sends_nothing(
    session: ReadingListSession, cv: FakeComicvine
) -> None:
    _crimson_tide(cv)
    session.cancel()

    with pytest.raises(OnlineLookupAbortedError):
        session.fetch_comicvine_arc(12)
    assert cv.calls == []


# ------------------------------------------------------------------ errors


def test_no_key_fails_before_any_call(cv: FakeComicvine) -> None:
    """Nothing is built or sent, and no fetch is said to have begun."""
    events: list[Event] = []
    with (
        ReadingListSession(on_event=events.append) as rl,
        pytest.raises(ReadingListFetchError) as caught,
    ):
        rl.fetch_comicvine_arc(12)

    assert str(caught.value) == (
        "Comic Vine needs an API key: pass --auth comicvine:KEY, or set"
        " online.auth.comicvine.key in the config or"
        " COMICBOX_ONLINE__AUTH__COMICVINE__KEY in the environment."
    )
    assert cv.built == 0
    assert comicvine._sessions.keys() == ()
    assert events == []


def test_the_config_key_is_used_without_credentials(cv: FakeComicvine) -> None:
    _crimson_tide(cv)
    with ReadingListSession() as rl:
        online = rl.settings.online
        auth = OnlineAuthSettings(sources={"comicvine": OnlineSourceCredentials(_KEY)})
        rl._settings = replace(rl.settings, online=replace(online, auth=auth))

        assert _keys(rl.fetch_comicvine_arc(12).reading_list) == ["1", "2"]


def test_a_missing_arc_says_so(session: ReadingListSession, cv: FakeComicvine) -> None:
    with pytest.raises(ReadingListFetchError) as caught:
        session.fetch_comicvine_arc(99)

    assert str(caught.value) == "Comic Vine arc 99: not found."


@pytest.mark.parametrize(
    ("method", "error", "message"),
    [
        (
            "get_story_arc",
            AuthenticationError("Invalid API Key"),
            "Comic Vine refused the API key.",
        ),
        ("get_story_arc", RateLimitError(None), "Comic Vine's rate limit is reached."),
        ("list_issues", RateLimitError("Rate Limit Exceeded"), "Rate Limit Exceeded."),
        (
            "list_volumes",
            ServiceError("Unable to connect to 'https://comicvine.gamespot.com/api'"),
            "Unable to connect to 'https://comicvine.gamespot.com/api'.",
        ),
        ("get_story_arc", ServiceError(None), "Comic Vine gave no reason."),
    ],
    ids=["refused-key", "rate-limited", "rate-limited-later", "no-connection", "none"],
)
def test_a_failed_call_is_one_fetch_error_naming_the_arc(
    session: ReadingListSession,
    cv: FakeComicvine,
    method: str,
    error: Exception,
    message: str,
) -> None:
    _crimson_tide(cv)
    cv.fail[method] = error

    with pytest.raises(ReadingListFetchError) as caught:
        session.fetch_comicvine_arc(12)

    assert str(caught.value) == f"Comic Vine arc 12: {message}"
    assert caught.value.__cause__ is error


def test_a_spent_hourly_budget_fails_at_once_saying_when_it_frees(
    session: ReadingListSession, cv: FakeComicvine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The arc is fetched; the issue call, whose pool is spent, is never sent."""
    _crimson_tide(cv)
    reset = datetime(2026, 11, 16, 15, 4, tzinfo=UTC).timestamp()
    spent = {"issues": {"limit": 200, "remaining": 0, "reset_epoch": reset}}
    monkeypatch.setattr(comicvine, "shared_client_rate_limit_status", lambda _s: spent)

    with pytest.raises(ReadingListFetchError) as caught:
        session.fetch_comicvine_arc(12)

    at = datetime.fromtimestamp(reset, tz=UTC).astimezone()
    assert str(caught.value) == (
        f"Comic Vine arc 12: the hourly issues budget is spent;"
        f" a call frees at {at:%H:%M}."
    )
    assert cv.calls == [("get_story_arc", 12)]


# ------------------------------------------------- the real simyan stack


class _Transport:
    """Answer every request with one Comic Vine body; record the URLs."""

    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body
        self.urls: list[str] = []

    def send(
        self, _adapter: HTTPAdapter, request: requests.PreparedRequest, **_kwargs: Any
    ) -> requests.Response:
        url = request.url or ""
        self.urls.append(url)
        content = json.dumps(self.body).encode()
        headers = {"Content-Type": "application/json"}
        response = requests.Response()
        response.status_code = 200
        response.headers = CaseInsensitiveDict(headers)
        response._content = content
        response.encoding = "utf-8"
        response.url = url
        response.request = request
        # The response cache stores what urllib3 would have read.
        response.raw = HTTPResponse(
            body=BytesIO(content),
            headers=headers,
            status=200,
            preload_content=False,
            request_url=url,
        )
        return response


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[Any], _Transport]]:
    """Put a fake transport under every requests session; close the clients."""

    def serve(body: dict[str, Any]) -> _Transport:
        transport = _Transport(body)

        def send(
            adapter: HTTPAdapter, request: requests.PreparedRequest, **kwargs: Any
        ) -> requests.Response:
            return transport.send(adapter, request, **kwargs)

        monkeypatch.setattr(HTTPAdapter, "send", send)
        return transport

    yield serve
    comicvine.close_shared_sessions()


def _page(results: Any) -> dict[str, Any]:
    total = len(results) if isinstance(results, list) else 1
    return {
        "error": "OK",
        "limit": 100,
        "offset": 0,
        "number_of_page_results": total,
        "number_of_total_results": total,
        "status_code": 1,
        "results": results,
        "version": "1.0",
    }


def test_the_id_filter_goes_out_as_the_other_filters_do(
    session: ReadingListSession, wire: Callable[[Any], _Transport]
) -> None:
    """Requests escapes ``|`` as it escapes the ``:`` tagging's filters use."""
    transport = wire(_page([issue_row(1), issue_row(2)]))
    source = ComicVineOnlineSource(
        OnlineSourceCredentials(key=_KEY), session.settings.online
    )

    issues = source.issues_by_id([1, 2])

    assert [issue.id for issue in issues] == [1, 2]
    assert len(transport.urls) == 1
    url = urlsplit(transport.urls[0])
    assert url.path == "/api/issues/"
    assert "filter=id%3A1%7C2" in url.query
    assert parse_qs(url.query)["filter"] == ["id:1|2"]


def test_a_missing_arc_is_comic_vines_200_with_status_101(
    session: ReadingListSession, wire: Callable[[Any], _Transport]
) -> None:
    body = {**_page([]), "error": "Object Not Found", "status_code": 101}
    transport = wire(body)

    with pytest.raises(ReadingListFetchError) as caught:
        session.fetch_comicvine_arc(99)

    assert str(caught.value) == "Comic Vine arc 99: not found."
    assert urlsplit(transport.urls[0]).path == "/api/story_arc/4045-99/"
