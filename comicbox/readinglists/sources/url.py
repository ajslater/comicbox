"""Fetch a reading list from a URL, streamed and size-capped."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from comicbox.exceptions import ReadingListFetchError

if TYPE_CHECKING:
    import httpx

_SCHEMES = frozenset({"http", "https"})
_ETAG = "etag"
_LAST_MODIFIED = "last-modified"
_CONTENT_LENGTH = "content-length"


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


def _revision(response: httpx.Response) -> str:
    """Name the version fetched: its ETag, its date, or when it was fetched."""
    headers = response.headers
    return (
        headers.get(_ETAG)
        or headers.get(_LAST_MODIFIED)
        or datetime.now(tz=UTC).isoformat(timespec="seconds")
    )


def fetch(client: httpx.Client, url: str, max_bytes: int) -> tuple[bytes, str]:
    """
    Download a URL's body and a revision for it.

    Redirects are followed, but only to http and https. An HTTP error, a
    network failure or a body over ``max_bytes`` raises
    ``ReadingListFetchError``.
    """
    import httpx

    check_url(url)
    try:
        with client.stream("GET", url) as response:
            check_url(str(response.url))
            if response.is_error:
                reason = f"{url}: HTTP {response.status_code} {response.reason_phrase}."
                raise ReadingListFetchError(reason)
            return _read_capped(response, url, max_bytes), _revision(response)
    except httpx.HTTPError as exc:
        reason = f"Cannot fetch {url}: {exc}"
        raise ReadingListFetchError(reason) from exc
