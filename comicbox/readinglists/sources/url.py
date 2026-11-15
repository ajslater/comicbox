"""Fetch a reading list from a URL, streamed and size-capped."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from comicbox.exceptions import ReadingListFetchError

if TYPE_CHECKING:
    from collections.abc import Mapping

    import httpx

_SCHEMES = frozenset({"http", "https"})
_ETAG = "etag"
_LAST_MODIFIED = "last-modified"
_CONTENT_LENGTH = "content-length"


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


def _read_capped(response: httpx.Response, url: str, max_bytes: int) -> bytes:
    """Read the body, stopping as soon as it passes the cap."""
    length = response.headers.get(_CONTENT_LENGTH, "")
    if length.isdigit() and int(length) > max_bytes:
        raise _over_limit(url, max_bytes)
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > max_bytes:
            raise _over_limit(url, max_bytes)
        chunks.append(chunk)
    return b"".join(chunks)


def download(
    client: httpx.Client,
    url: str,
    max_bytes: int,
    headers: Mapping[str, str] | None = None,
) -> Download:
    """
    Download a URL's body, sending ``headers`` with the request.

    Redirects are followed, but only to http and https. A 304 comes back
    with an empty body. An error status raises ``HttpStatusError``; a
    network failure or a body over ``max_bytes``, ``ReadingListFetchError``.
    """
    import httpx

    check_url(url)
    try:
        with client.stream("GET", url, headers=headers) as response:
            check_url(str(response.url))
            if response.is_error:
                raise HttpStatusError(url, response)
            body = (
                b""
                if response.status_code == HTTPStatus.NOT_MODIFIED
                else _read_capped(response, url, max_bytes)
            )
            return Download(response.status_code, response.headers, body)
    except httpx.HTTPError as exc:
        reason = f"Cannot fetch {url}: {exc}"
        raise ReadingListFetchError(reason) from exc


def fetch(client: httpx.Client, url: str, max_bytes: int) -> tuple[bytes, str]:
    """Download a URL's body and a revision for it, as ``download`` does."""
    fetched = download(client, url, max_bytes)
    return fetched.body, fetched.revision
