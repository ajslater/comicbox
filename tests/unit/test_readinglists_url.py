"""Fetching a reading list from a URL, through httpx.MockTransport."""

from __future__ import annotations

import threading
import time
import tracemalloc
import zlib
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
    ReadingListFormatError,
    ReadingListFormats,
    ReadingListSession,
)
from comicbox.readinglists.session import ReadingListSession as SessionClass
from comicbox.readinglists.sources import url as url_source
from tests.const import TEST_FILES_DIR

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

READING_LISTS_DIR = TEST_FILES_DIR / "readinglists"
_FILES = {
    "crimson-tide.yaml": ReadingListFormats.YAML,
    "cbl/startyear-source.cbl": ReadingListFormats.CBL,
    "json-cbl/minimal.json": ReadingListFormats.JSON_CBL,
}
_BASE = "https://lists.example"


def _serve(request: httpx.Request) -> httpx.Response:
    path = request.url.path.lstrip("/")
    if path == "moved":
        return httpx.Response(302, headers={"Location": f"{_BASE}/crimson-tide.yaml"})
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
    assert result.reading_list["name"] == "Crimson Tide"


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
        session.fetch_url(f"{_BASE}/crimson-tide.yaml")


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
    session.fetch_url(f"{_BASE}/crimson-tide.yaml")
    with pytest.raises(ReadingListFetchError):
        session.fetch_url(f"{_BASE}/missing.cbl")
    assert [type(event) for event in events] == [
        ReadingListFetchStarted,
        ReadingListFetchFinished,
        ReadingListFetchStarted,
        ReadingListFetchFinished,
    ]
    assert events[0] == ReadingListFetchStarted(
        source="url", key=f"{_BASE}/crimson-tide.yaml"
    )


def test_a_cancelled_session_fetches_nothing(session: ReadingListSession) -> None:
    requests = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _serve(request)

    session._transport = httpx.MockTransport(record)
    session.cancel()
    with pytest.raises(OnlineLookupAbortedError):
        session.fetch_url(f"{_BASE}/crimson-tide.yaml")
    assert requests == []


def test_close_closes_the_client() -> None:
    session = SessionClass()
    session._transport = httpx.MockTransport(_serve)
    client = session.http()
    session.close()
    assert client.is_closed


# ------------------------------------------- bounded downloads (R2-E E2)

_LIST = (READING_LISTS_DIR / "crimson-tide.yaml").read_bytes()


def _compress(data: bytes, wbits: int) -> bytes:
    packer = zlib.compressobj(9, zlib.DEFLATED, wbits)
    return packer.compress(data) + packer.flush()


def _zeros_gzip(size: int) -> bytes:
    """Gzip ``size`` zero bytes without ever holding them."""
    packer = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16)
    block = bytes(1 << 20)
    parts = [packer.compress(block) for _ in range(size >> 20)]
    return b"".join(parts) + packer.flush()


class _Streamed:
    """Answer with a streamed body, as a real server does; keep the requests."""

    def __init__(self, body: bytes | Iterator[bytes], encoding: str | None = None):
        self._body = body
        self._encoding = encoding
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        chunks = iter([self._body]) if isinstance(self._body, bytes) else self._body
        headers = {"Content-Encoding": self._encoding} if self._encoding else {}
        return httpx.Response(200, content=chunks, headers=headers)


@pytest.mark.parametrize(
    ("encoding", "wbits"),
    [("gzip", zlib.MAX_WBITS | 16), ("deflate", zlib.MAX_WBITS), ("deflate", -15)],
    ids=["gzip", "zlib-deflate", "raw-deflate"],
)
def test_a_compressed_list_is_inflated(encoding: str, wbits: int) -> None:
    answer = _Streamed(_compress(_LIST, wbits), encoding)
    with _session_with(answer, 1 << 20) as session:
        result = session.fetch_url(f"{_BASE}/crimson-tide.yaml")

    assert result.reading_list["name"] == "Crimson Tide"
    (request,) = answer.seen
    assert request.headers["Accept-Encoding"] == "gzip, deflate"


def test_a_gzip_bomb_fails_without_being_held() -> None:
    """64 MiB of zeros in 64 KiB: the cap fires before it is inflated."""
    bomb = _zeros_gzip(64 << 20)
    assert len(bomb) < 1 << 17
    tracemalloc.start()
    try:
        with (
            _session_with(_Streamed(bomb, "gzip"), 1 << 20) as session,
            pytest.raises(ReadingListFetchError, match="download limit"),
        ):
            session.fetch_url(f"{_BASE}/bomb.yaml")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 16 << 20


@pytest.mark.parametrize("encoding", ["br", "zstd", "compress", "gzip, br"])
def test_other_encodings_are_refused(encoding: str) -> None:
    with (
        _session_with(_Streamed(b"anything", encoding), 1 << 20) as session,
        pytest.raises(ReadingListFetchError, match="encoding, which comicbox"),
    ):
        session.fetch_url(f"{_BASE}/list.yaml")


def test_a_corrupt_gzip_body_is_one_error() -> None:
    corrupt = _compress(_LIST, zlib.MAX_WBITS | 16)[:20] + b"\xff" * 40
    with (
        _session_with(_Streamed(corrupt, "gzip"), 1 << 20) as session,
        pytest.raises(ReadingListFetchError, match="gzip body is corrupt"),
    ):
        session.fetch_url(f"{_BASE}/list.yaml")


def _cut_short(data: bytes, wbits: int) -> bytes:
    """Compress ``data`` and flush partway, never finishing the stream."""
    packer = zlib.compressobj(9, zlib.DEFLATED, wbits)
    return packer.compress(data) + packer.flush(zlib.Z_FULL_FLUSH)


@pytest.mark.parametrize(
    ("encoding", "wbits"),
    [("gzip", zlib.MAX_WBITS | 16), ("deflate", zlib.MAX_WBITS), ("deflate", -15)],
    ids=["gzip", "zlib-deflate", "raw-deflate"],
)
def test_a_compressed_body_cut_short_is_refused(encoding: str, wbits: int) -> None:
    """A close-delimited body that ends before its stream does is not whole."""
    with (
        _session_with(
            _Streamed(_cut_short(_LIST, wbits), encoding), 1 << 20
        ) as session,
        pytest.raises(ReadingListFetchError, match=f"{encoding} body ends early"),
    ):
        session.fetch_url(f"{_BASE}/list.yaml")


def _drip(seconds: float = 10.0) -> Iterator[bytes]:
    """Send a byte every 50 ms, as a server stalling a client does."""
    for _ in range(int(seconds / 0.05)):
        time.sleep(0.05)
        yield b"x"


def test_a_dripping_download_is_cancelled_promptly() -> None:
    with _session_with(_Streamed(_drip()), 1 << 20) as session:
        threading.Timer(0.2, session.cancel).start()
        started = time.monotonic()
        with pytest.raises(OnlineLookupAbortedError):
            session.fetch_url(f"{_BASE}/drip.yaml")
    assert time.monotonic() - started < 2


def test_a_dripping_download_stops_at_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(url_source, "DEADLINE_SECONDS", 0.3)
    with _session_with(_Streamed(_drip()), 1 << 20) as session:
        started = time.monotonic()
        with pytest.raises(ReadingListFetchError, match="took longer than"):
            session.fetch_url(f"{_BASE}/drip.yaml")
    assert time.monotonic() - started < 2


# ------------------------------------------- every failure (R2-E E6)


def _redirect_to_javascript(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/js":
        return httpx.Response(302, headers={"Location": "javascript:alert(1)"})
    return _serve(request)


@pytest.mark.parametrize(
    "url",
    [
        f"{_BASE}/js",
        f"{_BASE}/a\nb.yaml",
        "https://☃.example/list.yaml",
    ],
    ids=["javascript-redirect", "newline", "bad-host"],
)
def test_an_invalid_url_is_a_fetch_error(url: str) -> None:
    with ReadingListSession() as session:
        session._transport = httpx.MockTransport(_redirect_to_javascript)
        with pytest.raises(ReadingListFetchError, match="Cannot fetch"):
            session.fetch_url(url)


def test_a_download_that_will_not_read_names_its_url(
    session: ReadingListSession,
) -> None:
    session._transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, content=b"<ReadingList><Name>")
    )
    with pytest.raises(
        ReadingListFormatError, match=rf"^{_BASE}/broken\.cbl: Not valid XML"
    ):
        session.fetch_url(f"{_BASE}/broken.cbl")


def test_a_cancel_while_the_body_arrives_returns_no_list() -> None:
    """The server answers in full after the cancel; nothing is returned."""
    with ReadingListSession() as session:

        def cancel_then_answer(request: httpx.Request) -> httpx.Response:
            session.cancel()
            return _serve(request)

        session._transport = httpx.MockTransport(cancel_then_answer)
        with pytest.raises(OnlineLookupAbortedError):
            session.fetch_url(f"{_BASE}/crimson-tide.yaml")


# ---------------------------------------- credentials in a URL (R2-E E7)

_SECRET_URL = "https://user:secret@lists.example/crimson-tide.yaml?token=abc"
_SHOWN_URL = "https://lists.example/crimson-tide.yaml?token=abc"


def test_a_urls_credentials_are_sent_and_never_recorded(
    events: list[Event],
) -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _serve(request)

    with ReadingListSession(on_event=events.append) as session:
        session._transport = httpx.MockTransport(answer)
        result = session.fetch_url(_SECRET_URL)

    (request,) = seen
    assert request.headers["Authorization"] == "Basic dXNlcjpzZWNyZXQ="
    (source,) = (
        item for item in result.reading_list["sources"] if item["kind"] == "url"
    )
    assert source["key"] == source["url"] == _SHOWN_URL
    fetch_events = (ReadingListFetchStarted, ReadingListFetchFinished)
    keys = {event.key for event in events if isinstance(event, fetch_events)}
    assert keys == {_SHOWN_URL}
    assert "secret" not in repr(result)


@pytest.mark.parametrize(
    ("path", "status"), [("/missing.yaml", 404), ("/crimson-tide.yaml", 200)]
)
def test_an_error_never_shows_a_urls_credentials(path: str, status: int) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if status == 200:
            reason = "connection reset by peer"
            raise httpx.ReadError(reason, request=request)
        return httpx.Response(status)

    with ReadingListSession() as session:
        session._transport = httpx.MockTransport(answer)
        with pytest.raises(ReadingListFetchError) as caught:
            session.fetch_url(f"https://user:secret@lists.example{path}?token=abc")

    message = str(caught.value)
    assert "secret" not in message
    assert "user:" not in message
    assert f"https://lists.example{path}?token=abc" in message


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        (_SECRET_URL, _SHOWN_URL),
        ("https://user@lists.example:8080/a", "https://lists.example:8080/a"),
        ("https://lists.example/a?user=x@y", "https://lists.example/a?user=x@y"),
        ("https://a:b@[broken/x", "https://[broken/x"),
    ],
)
def test_without_userinfo(url: str, shown: str) -> None:
    assert url_source.without_userinfo(url) == shown
