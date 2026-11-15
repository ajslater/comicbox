"""Fetching a reading list from a URL, through httpx.MockTransport."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from comicbox.events import (
    Event,
    ReadingListFetchFinished,
    ReadingListFetchStarted,
)
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.readinglists import (
    ReadingListFetchError,
    ReadingListFormats,
    ReadingListSession,
)
from comicbox.readinglists.session import ReadingListSession as SessionClass
from tests.const import TEST_FILES_DIR

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

READING_LISTS_DIR = TEST_FILES_DIR / "readinglists"
_FILES = {
    "civil-war.yaml": ReadingListFormats.YAML,
    "cbl/startyear-source.cbl": ReadingListFormats.CBL,
    "json-cbl/minimal.json": ReadingListFormats.JSON_CBL,
}
_BASE = "https://lists.example"


def _serve(request: httpx.Request) -> httpx.Response:
    path = request.url.path.lstrip("/")
    if path == "moved":
        return httpx.Response(302, headers={"Location": f"{_BASE}/civil-war.yaml"})
    if path == "elsewhere":
        return httpx.Response(302, headers={"Location": "ftp://lists.example/x"})
    if path == "native.json":
        return httpx.Response(200, content=b'{"reading_list": {"name": "Native"}}')
    if (file := READING_LISTS_DIR / path).is_file():
        return httpx.Response(200, content=file.read_bytes(), headers={"ETag": '"v1"'})
    return httpx.Response(404)


@pytest.fixture
def events() -> list[Event]:
    return []


@pytest.fixture
def session(events: list[Event]) -> Iterator[ReadingListSession]:
    with ReadingListSession(on_event=events.append) as session:
        session._transport = httpx.MockTransport(_serve)
        yield session


@pytest.mark.parametrize(("path", "fmt"), list(_FILES.items()))
def test_each_format_is_detected(
    session: ReadingListSession, path: str, fmt: ReadingListFormats
) -> None:
    result = session.fetch_url(f"{_BASE}/{path}")
    assert result.fmt is fmt
    assert result.reading_list["entries"]


def test_native_json_is_detected(session: ReadingListSession) -> None:
    result = session.fetch_url(f"{_BASE}/native.json")
    assert result.fmt is ReadingListFormats.JSON
    assert result.reading_list["sources"] == [
        {
            "kind": "url",
            "key": f"{_BASE}/native.json",
            "url": f"{_BASE}/native.json",
            "revision": result.reading_list["sources"][0]["revision"],
        }
    ]


def test_the_url_source_takes_the_file_source_place(
    session: ReadingListSession,
) -> None:
    """A CBL's own source names its curator; the fetch says where it was."""
    url = f"{_BASE}/cbl/startyear-source.cbl"
    result = session.fetch_url(url)
    assert result.reading_list["sources"] == [
        {"kind": "url", "key": url, "url": url, "revision": '"v1"', "curator": "CBRO"}
    ]


def test_a_redirect_is_followed(session: ReadingListSession) -> None:
    result = session.fetch_url(f"{_BASE}/moved")
    assert result.reading_list["name"] == "Civil War"


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://lists.example/a.cbl", "lists.example/a.cbl"],
)
def test_other_schemes_are_refused(session: ReadingListSession, url: str) -> None:
    with pytest.raises(ReadingListFetchError, match="Only http and https"):
        session.fetch_url(url)


def test_a_redirect_to_another_scheme_is_refused(session: ReadingListSession) -> None:
    with pytest.raises(ReadingListFetchError):
        session.fetch_url(f"{_BASE}/elsewhere")


def test_a_404_is_a_fetch_error(session: ReadingListSession) -> None:
    with pytest.raises(ReadingListFetchError, match="HTTP 404 Not Found"):
        session.fetch_url(f"{_BASE}/missing.cbl")


def test_a_network_failure_is_a_fetch_error(session: ReadingListSession) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        reason = "connection refused"
        raise httpx.ConnectError(reason, request=request)

    session._transport = httpx.MockTransport(refuse)
    with pytest.raises(ReadingListFetchError, match="connection refused"):
        session.fetch_url(f"{_BASE}/civil-war.yaml")


def _session_with(
    handler: Callable[[httpx.Request], httpx.Response], max_bytes: int
) -> ReadingListSession:
    from dataclasses import replace

    session = ReadingListSession()
    settings = session.settings
    session._settings = replace(
        settings,
        readinglists=replace(settings.readinglists, max_download_bytes=max_bytes),
    )
    session._transport = httpx.MockTransport(handler)
    return session


def test_the_size_cap_by_content_length() -> None:
    def big(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 2000)

    with (
        _session_with(big, 1000) as session,
        pytest.raises(ReadingListFetchError, match="1,000-byte download limit"),
    ):
        session.fetch_url(f"{_BASE}/big.yaml")


def test_the_size_cap_while_streaming() -> None:
    """A server that sends no length is cut off as the body passes the cap."""
    sent = []

    def endless(_request: httpx.Request) -> httpx.Response:
        def chunks() -> Iterator[bytes]:
            for _ in range(100):
                sent.append(1)
                yield b"x" * 100

        return httpx.Response(200, content=chunks())

    with (
        _session_with(endless, 1000) as session,
        pytest.raises(ReadingListFetchError, match="download limit"),
    ):
        session.fetch_url(f"{_BASE}/endless.yaml")
    assert len(sent) < 100


def test_events_start_and_finish(
    session: ReadingListSession, events: list[Event]
) -> None:
    session.fetch_url(f"{_BASE}/civil-war.yaml")
    with pytest.raises(ReadingListFetchError):
        session.fetch_url(f"{_BASE}/missing.cbl")
    assert [type(event) for event in events] == [
        ReadingListFetchStarted,
        ReadingListFetchFinished,
        ReadingListFetchStarted,
        ReadingListFetchFinished,
    ]
    assert events[0] == ReadingListFetchStarted(
        source="url", key=f"{_BASE}/civil-war.yaml"
    )


def test_a_cancelled_session_fetches_nothing(session: ReadingListSession) -> None:
    requests = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _serve(request)

    session._transport = httpx.MockTransport(record)
    session.cancel()
    with pytest.raises(OnlineLookupAbortedError):
        session.fetch_url(f"{_BASE}/civil-war.yaml")
    assert requests == []


def test_close_closes_the_client() -> None:
    session = SessionClass()
    session._transport = httpx.MockTransport(_serve)
    client = session.http()
    session.close()
    assert client.is_closed
