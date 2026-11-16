"""
``comicbox rl search`` and ``comicbox rl fetch``, with no network.

URLs and the catalog go through httpx.MockTransport; Metron through the
fake requests adapter, so the real mokkari stack runs.
"""

from __future__ import annotations

import os
import signal
import threading
import time
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from comicbox import cli, logger
from comicbox.config import get_config
from comicbox.config.online.settings import OnlineSourceCredentials
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.metron_api.online_source import MetronOnlineSource
from comicbox.readinglists import cli as readinglist_cli
from comicbox.readinglists import load, loads
from comicbox.readinglists.cli import online as readinglist_online
from tests.const import TEST_FILES_DIR
from tests.util.metron_transport import (
    BURST_HEADERS,
    Reply,
    install,
    issue_page,
    reading_list_detail,
    reading_list_item,
    reading_list_row,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    import requests

_CBL = (TEST_FILES_DIR / "readinglists" / "cbl" / "common.cbl").read_bytes()
_URL = "https://lists.example/civil-war.cbl"
_CATALOG_PATH = "Marvel/Events/CBRO/[Marvel] Example Event (WEB-CBRO).cbl"
_TREE = {
    "sha": "root",
    "truncated": False,
    "tree": [{"path": _CATALOG_PATH, "type": "blob", "sha": "abc", "size": 10}],
}


def _web(request: httpx.Request) -> httpx.Response:
    """Serve one list by URL, GitHub's tree and its raw file."""
    url = request.url
    if url.host == "api.github.com":
        return httpx.Response(200, json=_TREE, headers={"ETag": '"v1"'})
    if url.host == "raw.githubusercontent.com" or str(url) == _URL:
        return httpx.Response(200, content=_CBL)
    if url.path == "/civil-war.cbl":
        return httpx.Response(200, content=_CBL)
    if url.path == "/broken.cbl":
        return httpx.Response(200, content=b"<ReadingList><Name>")
    return httpx.Response(404)


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """Point loguru back at stdout; the command bound it to the captured one."""
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


@pytest.fixture(autouse=True)
def web(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Give every session the CLI opens the fake web; record its requests."""
    requests_made: list[httpx.Request] = []
    opened = readinglist_online.open_session

    def handler(request: httpx.Request) -> httpx.Response:
        requests_made.append(request)
        return _web(request)

    def open_on_fake_web(run: Any) -> Any:
        session = opened(run)
        session._transport = httpx.MockTransport(handler)
        return session

    monkeypatch.setattr(readinglist_online, "open_session", open_on_fake_web)
    return requests_made


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    """Run the CLI; return its exit code, its stdout raw, its stderr unwrapped."""
    code = 0
    try:
        cli.main(("comicbox", "rl", *argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, captured.out, " ".join(captured.err.split())


def _metron(replies: Callable[[requests.PreparedRequest], Reply]) -> None:
    """Mount a fake transport on the shared session the CLI will use."""
    online = get_config().online
    session = MetronOnlineSource(OnlineSourceCredentials("t"), online).session()
    install(session, replies)


def _metron_list(request: requests.PreparedRequest) -> Reply:
    if (request.url or "").rstrip("/").endswith("items"):
        return Reply(issue_page([reading_list_item(1, 1), reading_list_item(2, 2)]))
    return Reply(reading_list_detail())


# ----------------------------------------------------------------- fetch


def test_fetch_a_url_writes_only_the_list_to_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(capsys, "fetch", _URL)

    assert code == 0
    result = loads(out)
    assert result.reading_list["name"] == "[Marvel] Civil War (Hand Written)"
    assert result.reading_list["sources"][0]["kind"] == "url"
    assert f"Fetching url {_URL}" in err


def test_fetch_to_a_file_in_another_format(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    output = tmp_path / "civil-war.json"

    code, out, err = _run(capsys, "fetch", "--to", "json-cbl", "-o", str(output), _URL)

    assert code == 0
    assert out == ""
    assert load(output).fmt is not None
    assert "written as json-cbl" in err


def test_fetch_does_not_write_over_a_file(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, web: list[httpx.Request]
) -> None:
    output = tmp_path / "taken.yaml"
    output.write_text("mine")

    code, out, err = _run(capsys, "fetch", "-o", str(output), _URL)

    assert code == 1
    assert "exists; --overwrite replaces it" in err
    assert output.read_text() == "mine"
    assert web == []  # Refused before fetching anything.
    assert out == ""


def test_fetch_overwrite_replaces_a_file(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    output = tmp_path / "taken.yaml"
    output.write_text("mine")

    code, _, _ = _run(capsys, "fetch", "--overwrite", "-o", str(output), _URL)

    assert code == 0
    assert load(output).reading_list["name"] == "[Marvel] Civil War (Hand Written)"


def test_fetch_a_404_is_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(capsys, "fetch", "https://lists.example/missing.cbl")

    assert code == 1
    assert out == ""
    assert "HTTP 404 Not Found." in err
    assert "Traceback" not in err


def test_fetch_from_the_catalog(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, "fetch", f"catalog:{_CATALOG_PATH}")

    assert code == 0
    (source,) = loads(out).reading_list["sources"]
    assert source["kind"] == "catalog"
    assert source["key"] == _CATALOG_PATH
    assert source["curator"] == "cbro"


def test_fetch_a_metron_list_with_progress(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _metron(_metron_list)

    code, out, err = _run(capsys, "fetch", "--auth", "metron:t", "metron:1")

    assert code == 0
    reading_list = loads(out).reading_list
    assert reading_list["sources"][0]["kind"] == "metron-list"
    assert len(reading_list["entries"]) == 2
    assert "Fetching metron-list 1..." in err
    assert "2 of 2 entries" in err


def test_fetch_metron_without_a_token_says_how_to_give_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(capsys, "fetch", "metron:1")

    assert code == 1
    assert out == ""
    assert "Metron needs an API token: pass --auth metron:TOKEN" in err
    assert "Traceback" not in err


@pytest.mark.parametrize(
    "spec", ["metron:x", "metron-arc:", "catalog:", "ftp://lists.example/a.cbl", "1"]
)
def test_fetch_refuses_what_it_cannot_fetch(
    capsys: pytest.CaptureFixture[str], spec: str
) -> None:
    code, _, err = _run(capsys, "fetch", spec)

    assert code == 2
    assert "give metron:ID, metron-arc:ID, catalog:PATH or an http(s) URL" in err


def test_quiet_fetch_prints_no_progress(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = _run(capsys, "-Q", "fetch", _URL)

    assert code == 0
    assert "Fetching" not in err


def test_the_cache_options_reach_the_settings(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    cache_dir = tmp_path / "elsewhere"

    code, _, _ = _run(
        capsys, "search", "--cache-dir", str(cache_dir), "catalog", "example"
    )

    assert code == 0
    assert list(cache_dir.glob("readinglists_catalog_*.json"))


# ---------------------------------------------------------------- search


def test_search_the_catalog(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, "search", "catalog", "example", "event")

    assert code == 0
    assert _CATALOG_PATH in " ".join(out.split())


def test_a_search_that_finds_nothing_says_so_on_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(capsys, "search", "catalog", "crisis")

    assert code == 0
    assert out == ""
    assert "No catalog lists match 'crisis'." in err


def test_search_metron(capsys: pytest.CaptureFixture[str]) -> None:
    _metron(lambda _request: Reply(issue_page([reading_list_row(7)])))

    code, out, _ = _run(capsys, "search", "--auth", "metron:t", "metron", "civil")

    assert code == 0
    row = " ".join(out.split())
    assert "7 Civil War Event cbro curator" in row


# ---------------------------------------------------------------- Ctrl-C


def _interrupt_soon() -> None:
    threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGINT)).start()


def test_ctrl_c_cancels_the_fetch(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first Ctrl-C cancels the session; the fetch stops and says so."""
    saw_cancel = threading.Event()

    def wait_for_cancel(session: Any, _target: str) -> None:
        _interrupt_soon()
        if not session.cancelled.wait(10):
            reason = "never cancelled"
            raise AssertionError(reason)
        saw_cancel.set()
        session.check_cancelled()

    fetchers = {**readinglist_online._FETCHERS, "url": wait_for_cancel}
    monkeypatch.setattr(readinglist_online, "_FETCHERS", MappingProxyType(fetchers))

    code, out, err = _run(capsys, "fetch", _URL)

    assert saw_cancel.is_set()
    assert code == readinglist_cli.EXIT_CANCELLED
    assert out == ""
    assert "Cancelling before the next request" in err
    assert err.endswith("Cancelled.")


def test_a_second_ctrl_c_quits_at_once(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fetch that will not stop is left behind on the second Ctrl-C."""
    release = threading.Event()

    def stuck(session: Any, _target: str) -> None:
        _interrupt_soon()
        session.cancelled.wait(10)
        _interrupt_soon()
        release.wait(10)
        reason = "left behind"
        raise OnlineLookupAbortedError(reason)

    fetchers = {**readinglist_online._FETCHERS, "url": stuck}
    monkeypatch.setattr(readinglist_online, "_FETCHERS", MappingProxyType(fetchers))

    try:
        code, _, err = _run(capsys, "fetch", _URL)
    finally:
        release.set()

    assert code == readinglist_cli.EXIT_CANCELLED
    assert err.endswith("Cancelled.")


# -------------------------------------- one line for every failure (E6)


def test_a_non_ascii_digit_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    """'²' is a digit to isdigit, and int() refuses it."""
    code, _, err = _run(capsys, "fetch", "metron:²")

    assert code == 2
    assert "Traceback" not in err


def test_a_missing_config_file_is_one_line(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    missing = tmp_path / "nonexistent.yaml"

    code, out, err = _run(capsys, "fetch", _URL, "-c", str(missing))

    assert code == 1
    assert out == ""
    assert "nonexistent.yaml could not be read" in err
    assert "Traceback" not in err


def test_a_spent_quota_is_an_error_not_a_cancel(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Metron says the day's quota is gone: exit 1 with why, not 130."""
    spent = {**BURST_HEADERS, "X-RateLimit-Sustained-Remaining": "0"}

    def answer(request: requests.PreparedRequest) -> Reply:
        if (request.url or "").rstrip("/").endswith("items"):
            return Reply(issue_page([reading_list_item(1, 1)]))
        return Reply(reading_list_detail(), headers=spent)

    _metron(answer)

    code, out, err = _run(capsys, "fetch", "--auth", "metron:t", "metron:1")

    assert code == 1
    assert out == ""
    assert "daily API request quota exhausted" in err
    assert "Cancelled." not in err


def test_ctrl_c_during_the_last_request_writes_nothing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """
    Write nothing when the last page arrives after Ctrl-C.

    The real fetch, not one that waits for the cancel.
    """

    def answer(request: requests.PreparedRequest) -> Reply:
        if (request.url or "").rstrip("/").endswith("items"):
            os.kill(os.getpid(), signal.SIGINT)
            time.sleep(0.3)
            return Reply(issue_page([reading_list_item(1, 1)]))
        return Reply(reading_list_detail())

    _metron(answer)
    output = tmp_path / "list.yaml"

    code, out, err = _run(
        capsys, "fetch", "--auth", "metron:t", "-o", str(output), "metron:1"
    )

    assert code == readinglist_cli.EXIT_CANCELLED
    assert not output.exists()
    assert out == ""
    assert err.endswith("Cancelled.")


def test_output_onto_a_directory_names_it(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code, _, err = _run(capsys, "fetch", "--overwrite", "-o", str(tmp_path), _URL)

    assert code == 1
    assert f"{tmp_path}: is a directory" in err
    assert ".tmp" not in err


def test_a_download_that_will_not_read_names_its_url(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, _, err = _run(capsys, "fetch", "https://lists.example/broken.cbl")

    assert code == 1
    assert "https://lists.example/broken.cbl: Not valid XML" in err


# ---------------------------------------- credentials in a URL (E7)


@pytest.mark.parametrize("path", ["/civil-war.cbl", "/missing.cbl"])
def test_the_cli_never_prints_a_urls_credentials(
    capsys: pytest.CaptureFixture[str], path: str
) -> None:
    url = f"https://user:secret@lists.example{path}?token=abc"

    _, out, err = _run(capsys, "fetch", url)

    assert "secret" not in out + err
    assert f"https://lists.example{path}?token=abc" in out + err
