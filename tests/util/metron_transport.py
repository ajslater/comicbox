"""
A fake `requests` transport adapter for driving a real mokkari Session.

mokkari 4.8.0 sends through a pooled `requests.Session` held at
``Session._http``, so patching ``mokkari.session.requests.request``
intercepts nothing any more. Mounting an adapter instead keeps the whole
real stack in the test: `requests.Session.send` still runs, so the
response hook comicbox installs fires, mokkari's cookie policy applies,
and the connection pool behaves as it does in production.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any, TypeVar

import requests
from requests.adapters import BaseAdapter
from requests.structures import CaseInsensitiveDict

if sys.version_info >= (3, 12):
    from typing import override  # pyright: ignore[reportUnreachable]
else:
    from typing_extensions import override


if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_AdapterT = TypeVar("_AdapterT", bound=BaseAdapter)

BURST_HEADERS = {
    "X-RateLimit-Burst-Limit": "20",
    "X-RateLimit-Burst-Remaining": "19",
    "X-RateLimit-Sustained-Limit": "5000",
    "X-RateLimit-Sustained-Remaining": "4999",
}


class Reply:
    """One canned answer: a response to build, or an exception to raise."""

    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        """Answer with ``payload``/``status_code``, or raise ``error``."""
        self.payload = {} if payload is None else payload
        self.status_code = status_code
        self.headers = dict(BURST_HEADERS if headers is None else headers)
        self.error = error


def connection_error(message: str = "down") -> Reply:
    """Build a reply that fails in transport, producing no response."""
    return Reply(error=requests.exceptions.ConnectionError(message))


class FakeAdapter(BaseAdapter):
    """Answers every request from a queue of `Reply` objects."""

    def __init__(self, replies: list[Reply] | Callable[[Any], Reply]) -> None:
        """Answer from a queue, or from a callable handed each request."""
        super().__init__()
        self._replies = replies
        self.urls: list[str] = []

    @override
    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: Any = None,
        verify: bool | str = True,
        cert: Any = None,
        proxies: Mapping[str, str] | None = None,
    ) -> requests.Response:
        """Return a real Response, or raise the reply's error."""
        # requests calls adapter.send(request, **kwargs) with these exact
        # keyword names, so the signature has to carry them; a fake
        # transport has no use for any of them.
        del stream, timeout, verify, cert, proxies
        url = request.url or ""
        self.urls.append(url)
        reply = (
            self._replies.pop(0)
            if isinstance(self._replies, list)
            else self._replies(request)
        )
        if reply.error is not None:
            raise reply.error
        response = requests.Response()
        response.status_code = reply.status_code
        response.headers = CaseInsensitiveDict(reply.headers)
        response._content = json.dumps(reply.payload).encode()
        response.encoding = "utf-8"
        response.url = url
        response.request = request
        return response

    @override
    def close(self) -> None:
        """Nothing to release."""


def mount(session: Any, adapter: _AdapterT) -> _AdapterT:
    """Mount ``adapter`` on a mokkari Session's pooled http session."""
    for prefix in ("https://", "http://"):
        session._http.mount(prefix, adapter)
    return adapter


def install(session: Any, replies: list[Reply] | Callable[[Any], Reply]) -> FakeAdapter:
    """Mount a fresh `FakeAdapter` answering ``replies``; return it."""
    return mount(session, FakeAdapter(replies))


def issue_row(issue_id: int) -> dict[str, Any]:
    """Build a BaseIssue payload with every field mokkari requires."""
    return {
        "id": issue_id,
        "number": str(issue_id),
        "cover_date": "2020-01-01",
        "modified": "2020-01-01T00:00:00-05:00",
        "issue_name": f"Test #{issue_id}",
        "series": {
            "id": 7,
            "name": "Test Series",
            "volume": 1,
            "year_began": 2020,
        },
    }


def issue_page(
    rows: list[dict[str, Any]],
    next_page: str | None = None,
    count: int | None = None,
    previous_page: str | None = None,
) -> dict[str, Any]:
    """
    Wrap rows in mokkari's paginated list envelope.

    ``count`` is the whole list's length, as Metron sends it on every
    page; it defaults to this page's.
    """
    return {
        "count": len(rows) if count is None else count,
        "next": next_page,
        "previous": previous_page,
        "results": rows,
    }


def issue_detail(issue_id: int, series_id: int = 7) -> dict[str, Any]:
    """Build an `issue(id)` payload with every field mokkari's Issue requires."""
    return {
        "id": issue_id,
        "publisher": {"id": 1, "name": "Test Publisher"},
        "series": {
            "id": series_id,
            "name": "Test Series",
            "sort_name": "Test Series",
            "volume": 1,
            "year_began": 2020,
            "series_type": {"id": 13, "name": "Single Issue"},
        },
        "number": str(issue_id),
        "alt_number": "",
        "title": "",
        "name": [],
        "cover_date": "2020-01-01",
        "price_currency": "USD",
        "rating": {"id": 1, "name": "Everyone"},
        "sku": "",
        "isbn": "",
        "upc": "",
        "desc": "",
        "rating_count": 0,
        "resource_url": f"https://metron.cloud/issue/test-{issue_id}/",
        "modified": "2020-01-01T00:00:00-05:00",
    }


def series_detail(series_id: int = 7) -> dict[str, Any]:
    """Build a `series(id)` payload with every field mokkari's Series requires."""
    return {
        "id": series_id,
        "name": "Test Series",
        "sort_name": "Test Series",
        "volume": 1,
        "series_type": {"id": 13, "name": "Single Issue"},
        "status": "Completed",
        "publisher": {"id": 1, "name": "Test Publisher"},
        "year_began": 2020,
        "year_end": 2021,
        "desc": "<p>The whole run.</p>",
        "issue_count": 12,
        "resource_url": f"https://metron.cloud/series/test-{series_id}/",
        "modified": "2020-01-01T00:00:00-05:00",
    }


_MODIFIED = "2024-05-01T12:00:00-04:00"
_LIST_SERIES = {"id": 7, "name": "Civil War", "volume": 1, "year_began": 2006}


def reading_list_detail(list_id: int = 1, **fields: Any) -> dict[str, Any]:
    """Build a `reading_list(id)` payload; ``fields`` override any key."""
    return {
        "id": list_id,
        "user": {"id": 3, "username": "curator"},
        "name": "Civil War",
        "slug": "civil-war",
        "desc": "<p>The <b>Superhuman Registration Act</b> divides them.</p>",
        "list_type": "Event",
        "is_private": False,
        "attribution_source": "CBRO",
        "attribution_url": "https://www.comicbookreadingorders.com/marvel/events/civil-war/",
        "previous": None,
        "next": None,
        "average_rating": 4.5,
        "rating_count": 2,
        "items_url": f"https://metron.cloud/api/reading_list/{list_id}/items/",
        "resource_url": f"https://metron.cloud/reading-lists/{list_id}/",
        "modified": _MODIFIED,
        **fields,
    }


def reading_list_item(
    issue_id: int, order: int | None = None, issue_type: str = "Core"
) -> dict[str, Any]:
    """Build one `reading_list_items` row, its item id the issue's."""
    return {
        "id": issue_id,
        "issue": {
            "id": issue_id,
            "series": _LIST_SERIES,
            "number": str(issue_id),
            "cover_date": "2006-07-01",
            "store_date": "2006-05-03",
            "cv_id": 1000 + issue_id,
            "gcd_id": None,
            "modified": _MODIFIED,
        },
        "order": order,
        "issue_type": issue_type,
    }


def reading_list_row(list_id: int = 1, **fields: Any) -> dict[str, Any]:
    """Build one `reading_lists_list` row; ``fields`` override any key."""
    return {
        "id": list_id,
        "name": "Civil War",
        "slug": "civil-war",
        "user": {"id": 3, "username": "curator"},
        "list_type": "Event",
        "is_private": False,
        "attribution_source": "CBRO",
        "average_rating": 4.5,
        "rating_count": 2,
        "modified": _MODIFIED,
        **fields,
    }


def arc_detail(arc_id: int = 5, **fields: Any) -> dict[str, Any]:
    """Build an `arc(id)` payload; ``fields`` override any key."""
    return {
        "id": arc_id,
        "name": "Civil War",
        "modified": _MODIFIED,
        "desc": "<p>Hero against hero.</p>",
        "image": None,
        "cv_id": 40000,
        "gcd_id": None,
        "resource_url": f"https://metron.cloud/arc/civil-war-{arc_id}/",
        "attribution": [],
        **fields,
    }
