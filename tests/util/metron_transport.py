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
from typing import TYPE_CHECKING, Any, TypeVar

import requests
from requests.adapters import BaseAdapter
from requests.structures import CaseInsensitiveDict
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
    rows: list[dict[str, Any]], next_page: str | None = None
) -> dict[str, Any]:
    """Wrap issue rows in mokkari's paginated list envelope."""
    return {
        "count": len(rows),
        "next": next_page,
        "previous": None,
        "results": rows,
    }
