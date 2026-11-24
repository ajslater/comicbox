"""
An `httpx.MockTransport` that serves recorded VerseDB responses.

The real `versedb` SDK sends through it, so its strict parsing runs in
every test: a fixture missing a key the SDK requires fails here the way a
real response would. The payloads are the recorded ones in
``tests/files/versedb/``, never hand-built objects.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

FIXTURES = Path(__file__).parent.parent / "files" / "versedb"

RATE_HEADERS: Mapping[str, str] = {
    "X-RateLimit-Limit": "300",
    "X-RateLimit-Remaining": "299",
    "Cache-Control": "no-cache, private",
}

_ISSUE_PATH_RE = re.compile(r"^/api/v1/issues/(\d+)$")


def fixture(name: str) -> dict[str, Any]:
    """Load one recorded response body."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


@dataclass
class Reply:
    """One canned answer: a JSON payload or raw body, a status and headers."""

    payload: Any = None
    status: int = 200
    headers: Mapping[str, str] = field(default_factory=lambda: dict(RATE_HEADERS))
    body: bytes | None = None

    def response(self) -> httpx.Response:
        """Build the httpx response."""
        if self.body is not None:
            return httpx.Response(self.status, content=self.body, headers=self.headers)
        return httpx.Response(self.status, json=self.payload, headers=self.headers)


def _issues_in(request: httpx.Request) -> dict[str, Any]:
    """Cut the recorded issue list to the series the request names, as the server does."""
    payload = fixture("list_issues")
    wanted = {
        int(sid) for sid in request.url.params.get("series_ids", "").split(",") if sid
    }
    if wanted:
        payload["data"] = [row for row in payload["data"] if row["series_id"] in wanted]
        payload["meta"]["total"] = len(payload["data"])
    return payload


def recorded_reply(request: httpx.Request) -> Reply:
    """
    Answer a request from the recordings, by path.

    Issue 999999999 is the recorded 404; every other issue id gets the
    regular issue's detail with its id swapped in.
    """
    path = request.url.path
    if path == "/api/v1/series":
        return Reply(fixture("series_search"))
    if path == "/api/v1/issues":
        return Reply(_issues_in(request))
    if match := _ISSUE_PATH_RE.match(path):
        issue_id = int(match.group(1))
        if issue_id == 999999999:
            return Reply(fixture("issue_missing"), status=404)
        payload = fixture("issue_regular")
        payload["data"]["id"] = issue_id
        return Reply(payload)
    return Reply({"message": "Not Found"}, status=404)


class VerseDBTransport:
    """Answers every request through ``reply_for``, and keeps each request."""

    def __init__(
        self, reply_for: Callable[[httpx.Request], Reply] = recorded_reply
    ) -> None:
        """Answer with ``reply_for(request)``; the recordings by default."""
        self.reply_for = reply_for
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.reply_for(request).response()

    def params(self, index: int = -1) -> dict[str, str]:
        """Return the query parameters of one request, the last by default."""
        return dict(self.requests[index].url.params)

    @property
    def paths(self) -> list[str]:
        """Every request's path, in order."""
        return [request.url.path for request in self.requests]
