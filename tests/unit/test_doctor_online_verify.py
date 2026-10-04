"""
``comicbox doctor --online``: one live request per configured source.

The transport is faked below ``requests``, so mokkari's and simyan's own
error handling (``ApiError`` chaining, ``RateLimitError``, the response
hook that spots a missing ``X-RateLimit-*`` header) runs for real and no
socket ever opens.
"""

from __future__ import annotations

import json
import time
from argparse import Namespace
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest
import requests
from requests.adapters import HTTPAdapter
from requests.structures import CaseInsensitiveDict

from comicbox import doctor, logger, version
from comicbox.cli.parser import build_parser
from comicbox.doctor import run_checks
from comicbox.doctor.result import Status
from comicbox.formats.comicvine_api import online_source as comicvine
from comicbox.formats.metron_api import online_source as metron

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

    from comicbox.doctor.result import CheckResult, DoctorReport

_METRON_TOKEN = "metron-token-0123456789"
_CV_KEY = "comicvine-key-abcdef"
_AUTH = ("--auth", f"metron:{_METRON_TOKEN}", "--auth", f"comicvine:{_CV_KEY}")

_RESET = str(int(time.time()) + 60)
_METRON_HEADERS = {
    "Content-Type": "application/json",
    "X-RateLimit-Burst-Limit": "60",
    "X-RateLimit-Burst-Remaining": "59",
    "X-RateLimit-Burst-Reset": _RESET,
    "X-RateLimit-Sustained-Limit": "5000",
    "X-RateLimit-Sustained-Remaining": "4990",
    "X-RateLimit-Sustained-Reset": _RESET,
}
_METRON_OK = {"count": 1, "next": None, "previous": None, "results": []}
_CV_OK = {
    "error": "OK",
    "limit": 1,
    "offset": 0,
    "number_of_page_results": 1,
    "number_of_total_results": 1,
    "status_code": 1,
    "results": [
        {
            "api_detail_url": "https://comicvine.gamespot.com/api/origin/4030-1/",
            "id": 1,
            "name": "Mutant",
            "site_detail_url": "https://comicvine.gamespot.com/mutant/4030-1/",
        }
    ],
    "version": "1.0",
}


class _Transport:
    """Answers every request by host; records what was sent."""

    def __init__(self) -> None:
        self.sent: list[requests.PreparedRequest] = []
        self.replies: dict[str, Any] = {}

    def reply(
        self,
        host: str,
        status: int = 200,
        body: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.replies[host] = (status, body, headers or {})

    def send(
        self, _adapter: HTTPAdapter, request: requests.PreparedRequest, **_kwargs: Any
    ) -> requests.Response:
        self.sent.append(request)
        host = urlsplit(request.url or "").hostname or ""
        reply = self.replies[host]
        if isinstance(reply, Exception):
            raise reply
        status, body, headers = reply
        response = requests.Response()
        response.status_code = status
        response.headers = CaseInsensitiveDict(headers)
        response._content = (
            body if isinstance(body, bytes) else json.dumps(body).encode()
        )
        response.encoding = "utf-8"
        response.url = request.url or ""
        response.request = request
        return response


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> _Transport:
    fake = _Transport()
    fake.reply("metron.cloud", body=_METRON_OK, headers=_METRON_HEADERS)
    fake.reply("comicvine.gamespot.com", body=_CV_OK)

    def send(
        adapter: HTTPAdapter, request: requests.PreparedRequest, **kwargs: Any
    ) -> requests.Response:
        return fake.send(adapter, request, **kwargs)

    monkeypatch.setattr(HTTPAdapter, "send", send)
    return fake


@pytest.fixture
def _restore_logging() -> Iterator[None]:
    """
    Point loguru back at the real stdout once capsys has let go of it.

    `doctor.main` binds loguru to whatever stdout is, here capsys's buffer.
    """
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


def _report(*online: str, argv: tuple[str, ...] = _AUTH) -> DoctorReport:
    args = Namespace(comicbox=build_parser().parse_args(argv))
    return run_checks(args, online_sources=online)


def _row(report: DoctorReport, name: str) -> CheckResult:
    return next(row for row in report.results if row.name == name)


def test_offline_by_default(transport: _Transport) -> None:
    report = _report()
    assert transport.sent == []
    for name in ("metron", "comicvine"):
        assert _row(report, name).detail.endswith(
            "unverified: add --online all (1 API request)"
        )


def test_all_verifies_every_configured_source(transport: _Transport) -> None:
    report = _report("all")
    hosts = [urlsplit(sent.url or "").hostname or "" for sent in transport.sent]
    assert sorted(hosts) == ["comicvine.gamespot.com", "metron.cloud"]
    metron_row = _row(report, "metron")
    assert metron_row.status is Status.OK
    assert metron_row.detail == (
        "key from --auth · verified · burst 59/60, daily 4990/5000 left"
    )
    comicvine_row = _row(report, "comicvine")
    assert comicvine_row.status is Status.OK
    assert comicvine_row.detail.startswith(
        "key from --auth · verified · origins 199/200"
    )


def test_only_the_named_source_is_verified(transport: _Transport) -> None:
    report = _report("metron")
    assert len(transport.sent) == 1
    assert "verified" in _row(report, "metron").detail
    assert _row(report, "comicvine").detail.endswith("(1 API request)")


def test_an_unconfigured_source_is_never_sent_a_request(
    transport: _Transport,
) -> None:
    report = _report("all", argv=("--auth", f"metron:{_METRON_TOKEN}"))
    assert len(transport.sent) == 1
    assert _row(report, "comicvine").status is Status.OFF


def test_the_probe_is_uncached_and_unshared(
    transport: _Transport, tmp_path: Path
) -> None:
    """A cached answer would hide a revoked key; a shared session might carry one."""
    _report("all")
    _report("all")
    assert len(transport.sent) == 4
    assert metron._session_cache == {}
    assert comicvine._session_cache == {}
    assert not (tmp_path / "online-cache" / "metron_cache.sqlite").exists()


@pytest.mark.parametrize(
    ("host", "status", "body", "expected"),
    [
        ("metron.cloud", 401, {"detail": "Invalid token."}, Status.MISCONFIGURED),
        ("metron.cloud", 403, {"detail": "Forbidden."}, Status.MISCONFIGURED),
        ("metron.cloud", 429, {"detail": "Request was throttled."}, Status.WARN),
        ("metron.cloud", 502, {"detail": "Bad gateway."}, Status.ERROR),
        (
            "comicvine.gamespot.com",
            401,
            {"error": "Invalid API Key"},
            Status.MISCONFIGURED,
        ),
        ("comicvine.gamespot.com", 420, {"error": "Rate limited"}, Status.WARN),
        ("comicvine.gamespot.com", 503, {"error": "Down"}, Status.ERROR),
    ],
)
def test_probe_failures(
    transport: _Transport, host: str, status: int, body: Any, expected: Status
) -> None:
    headers = _METRON_HEADERS if host == "metron.cloud" else {}
    transport.reply(host, status, body, {**headers, "Retry-After": "30"})
    name = "metron" if host == "metron.cloud" else "comicvine"
    row = _row(_report(name), name)
    assert row.status is expected
    assert "verify failed" in row.detail
    assert row.fix


def test_connection_error_is_an_error(transport: _Transport) -> None:
    """The message carries the key in its URL; the report doesn't."""
    url = f"https://comicvine.gamespot.com/api/origins/?api_key={_CV_KEY}"
    transport.replies["comicvine.gamespot.com"] = requests.ConnectionError(
        f"Max retries exceeded with url: {url}"
    )
    transport.replies["metron.cloud"] = requests.ConnectionError("Network unreachable")
    report = _report("all")
    for name in ("metron", "comicvine"):
        row = _row(report, name)
        assert row.status is Status.ERROR
        assert row.fix == "check the network, then try again"
    assert _CV_KEY not in str(report)


def test_missing_rate_limit_headers_warn(transport: _Transport) -> None:
    """A bot-check page answers 200 HTML with none of Metron's headers."""
    transport.reply(
        "metron.cloud",
        body=b"<html>Making sure you're not a bot!</html>",
        headers={"Content-Type": "text/html"},
    )
    row = _row(_report("metron"), "metron")
    assert row.status is Status.WARN
    assert "without rate-limit headers" in row.detail


def test_a_spent_local_bucket_sends_nothing(
    transport: _Transport, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Send nothing: simyan would block for twice its timeout for a slot."""
    spent = {"origins": {"limit": 200, "remaining": 0, "reset_epoch": None}}
    monkeypatch.setattr(comicvine, "shared_client_rate_limit_status", lambda _s: spent)
    row = _row(_report("comicvine"), "comicvine")
    assert transport.sent == []
    assert row.status is Status.WARN
    assert "origins budget is spent" in row.detail


@pytest.mark.usefixtures("_restore_logging")
def test_cli_probe_names_itself_in_the_user_agent(
    transport: _Transport,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Metron's operators can tell the doctor's request from a tagging run's."""
    for name in ("_ua_entry_point", "_ua_jobs", "_ua_client"):
        monkeypatch.setattr(version, name, getattr(version, name))
    assert doctor.main([*_AUTH, "--online", "metron"]) == 0
    (sent,) = transport.sent
    assert "(cli; doctor)" in str(sent.headers["User-Agent"])
    assert "verified" in capsys.readouterr().out
