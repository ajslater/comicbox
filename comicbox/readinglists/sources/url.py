"""
Fetch a reading list from a URL, streamed and bounded.

A body is read raw and capped on the wire; a gzip or deflate body is
inflated here, never past the cap, and any other encoding is refused. So a
few kilobytes that would inflate to gigabytes cost no more memory than the
cap. A whole download has a deadline, and a cancel is honoured between
chunks.
"""

from __future__ import annotations

import time
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING, Final
from urllib.parse import urlsplit

from comicbox.exceptions import OnlineLookupAbortedError, ReadingListFetchError
from comicbox.readinglists.changes import quote_value

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    import httpx

_SCHEMES = frozenset({"http", "https"})
_ETAG = "etag"
_LAST_MODIFIED = "last-modified"
_CONTENT_LENGTH = "content-length"
_CONTENT_ENCODING = "content-encoding"
# The encodings inflated here, by zlib window bits. Advertised alone, so a
# server has no reason to send another.
_ACCEPT_ENCODING = "gzip, deflate"
_IDENTITY = frozenset({"", "identity"})
_WINDOW_BITS: Final = {
    "gzip": zlib.MAX_WBITS | 16,
    "x-gzip": zlib.MAX_WBITS | 16,
    "deflate": zlib.MAX_WBITS,
}
# Some servers send "deflate" without its zlib wrapper.
_RAW_DEFLATE_BITS = -zlib.MAX_WBITS
# The longest one download may take, beside the per-read timeout: a server
# dripping a byte at a time never trips that.
DEADLINE_SECONDS = 120.0


class HttpStatusError(ReadingListFetchError):
    """A fetch the server answered with an error status."""

    def __init__(self, url: str, response: httpx.Response) -> None:
        """Name the URL and the status; keep the status and headers."""
        self.status = response.status_code
        self.headers: Mapping[str, str] = response.headers
        super().__init__(f"{url}: HTTP {self.status} {response.reason_phrase}.")


@dataclass(frozen=True, slots=True)
class Download:
    """A fetched body, with the status and headers it came with."""

    status: int
    headers: Mapping[str, str]
    body: bytes

    @property
    def not_modified(self) -> bool:
        """Whether a conditional request found nothing new."""
        return self.status == HTTPStatus.NOT_MODIFIED

    @property
    def revision(self) -> str:
        """Name the version fetched: its ETag, its date, or when it was fetched."""
        return (
            self.headers.get(_ETAG)
            or self.headers.get(_LAST_MODIFIED)
            or datetime.now(tz=UTC).isoformat(timespec="seconds")
        )


def check_url(url: str) -> str:
    """Refuse anything but an http or https URL."""
    if urlsplit(url).scheme.lower() not in _SCHEMES:
        reason = f"Only http and https URLs can be fetched: {url}"
        raise ReadingListFetchError(reason)
    return url


def _over_limit(url: str, max_bytes: int) -> ReadingListFetchError:
    reason = f"{url} is larger than the {max_bytes:,}-byte download limit."
    return ReadingListFetchError(reason)


class _Inflater:
    """Inflate a gzip or deflate body, never more than asked for at once."""

    def __init__(self, url: str, encoding: str) -> None:
        self._url = url
        self._encoding = encoding
        self._bits = _WINDOW_BITS[encoding]
        self._zlib = zlib.decompressobj(self._bits)
        self._started = False

    def _corrupt(self, exc: zlib.error) -> ReadingListFetchError:
        reason = f"{self._url}: its {self._encoding} body is corrupt: {exc}"
        return ReadingListFetchError(reason)

    def inflate(self, data: bytes, limit: int) -> bytes:
        """Inflate up to ``limit`` bytes; input that would pass it waits."""
        try:
            out = self._zlib.decompress(data, limit)
        except zlib.error as exc:
            if self._started or self._bits != zlib.MAX_WBITS:
                raise self._corrupt(exc) from exc
            # The first chunk of a "deflate" body with no zlib header.
            self._bits = _RAW_DEFLATE_BITS
            self._zlib = zlib.decompressobj(self._bits)
            return self.inflate(data, limit)
        self._started = True
        return out

    @property
    def pending(self) -> bytes:
        """Input not yet inflated because the output reached its limit."""
        return self._zlib.unconsumed_tail


class _BoundedBody:
    """Read one response's body within the cap, the deadline and a cancel."""

    def __init__(
        self,
        response: httpx.Response,
        url: str,
        max_bytes: int,
        cancelled: Callable[[], bool] | None,
    ) -> None:
        self._response = response
        self._url = url
        self._max = max_bytes
        self._cancelled = cancelled
        self._deadline = time.monotonic() + DEADLINE_SECONDS
        encoding = response.headers.get(_CONTENT_ENCODING, "").strip().lower()
        if encoding not in _IDENTITY and encoding not in _WINDOW_BITS:
            reason = (
                f"{url}: sent in the {quote_value(encoding)} encoding,"
                " which comicbox does not read."
            )
            raise ReadingListFetchError(reason)
        self._inflater = None if encoding in _IDENTITY else _Inflater(url, encoding)
        self._body = bytearray()

    def _check(self) -> None:
        if self._cancelled is not None and self._cancelled():
            reason = "Reading-list fetch cancelled."
            raise OnlineLookupAbortedError(reason)
        if time.monotonic() > self._deadline:
            reason = f"{self._url} took longer than {DEADLINE_SECONDS:.0f} seconds."
            raise ReadingListFetchError(reason)

    def _add(self, data: bytes) -> None:
        if self._inflater is None:
            self._body += data
        else:
            # One byte past the room left is enough to know it is too big.
            while data:
                self._body += self._inflater.inflate(
                    data, self._max - len(self._body) + 1
                )
                if len(self._body) > self._max:
                    break
                data = self._inflater.pending
        if len(self._body) > self._max:
            raise _over_limit(self._url, self._max)

    def read(self) -> bytes:
        """Read the whole body, or raise as soon as it cannot be had."""
        length = self._response.headers.get(_CONTENT_LENGTH, "")
        if length.isdigit() and int(length) > self._max:
            raise _over_limit(self._url, self._max)
        self._check()
        if self._response.is_stream_consumed:
            # Only a transport that answers from memory hands over a body
            # already read; it is in memory whatever is done here.
            body = self._response.content
            if len(body) > self._max:
                raise _over_limit(self._url, self._max)
            return body
        wire = 0
        # No chunk size: a chunk is whatever arrived, so a slow server is
        # checked on between every read.
        for chunk in self._response.iter_raw():
            self._check()
            wire += len(chunk)
            if wire > self._max:
                raise _over_limit(self._url, self._max)
            self._add(chunk)
        return bytes(self._body)


def download(
    client: httpx.Client,
    url: str,
    max_bytes: int,
    headers: Mapping[str, str] | None = None,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> Download:
    """
    Download a URL's body, sending ``headers`` with the request.

    Redirects are followed, but only to http and https. A 304 comes back
    with an empty body. An error status raises ``HttpStatusError``; a
    network failure, a body over ``max_bytes`` in either its sent or its
    inflated size, an encoding other than gzip or deflate, or a download
    past ``DEADLINE_SECONDS``, ``ReadingListFetchError``. ``cancelled`` is
    asked between chunks; when it says yes, ``OnlineLookupAbortedError``.
    """
    import httpx

    check_url(url)
    request_headers = {**(headers or {}), "Accept-Encoding": _ACCEPT_ENCODING}
    try:
        with client.stream("GET", url, headers=request_headers) as response:
            check_url(str(response.url))
            if response.is_error:
                raise HttpStatusError(url, response)
            body = (
                b""
                if response.status_code == HTTPStatus.NOT_MODIFIED
                else _BoundedBody(response, url, max_bytes, cancelled).read()
            )
            return Download(response.status_code, response.headers, body)
    except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError) as exc:
        # InvalidURL is not an HTTPError: a URL with a newline, a bad host
        # name, or a redirect to one, such as "javascript:...".
        reason = f"Cannot fetch {url}: {exc}"
        raise ReadingListFetchError(reason) from exc


def fetch(
    client: httpx.Client,
    url: str,
    max_bytes: int,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[bytes, str]:
    """Download a URL's body and a revision for it, as ``download`` does."""
    fetched = download(client, url, max_bytes, cancelled=cancelled)
    return fetched.body, fetched.revision
