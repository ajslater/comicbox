"""
The doctor's Online section, offline.

A credential row names the layer that supplied each field and never its
value. The suite's conftest points ``COMICBOXDIR`` at ``tmp_path`` and
strips every ``COMICBOX_*`` env var, so each test sets up its own layers.
"""

from __future__ import annotations

import os
import socket
from argparse import Namespace
from io import StringIO
from typing import TYPE_CHECKING

import keyring
from keyring.backends import fail
from rich.console import Console

from comicbox.cli.parser import build_parser
from comicbox.doctor import _run, online, settings
from comicbox.doctor.context import DoctorContext
from comicbox.doctor.render import render_report
from comicbox.doctor.result import Status
from comicbox.formats.base.online import credentials
from comicbox.formats.comicvine_api import online_source as comicvine

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from comicbox.doctor.result import CheckResult

_METRON_TOKEN = "metron-token-0123456789"
_CV_KEY = "comicvine-key-abcdef"
_PASSWORD = "hunter2-password"
# Every configured source's row ends with this until --online verifies it.
_UNVERIFIED = " · unverified: add --online all (1 API request)"


def _ctx(*argv: str) -> DoctorContext:
    """Build a context whose settings loaded, as the Config section leaves it."""
    ctx = DoctorContext(Namespace(comicbox=build_parser().parse_args(argv)))
    list(settings.check_values(ctx))
    assert ctx.settings is not None
    return ctx


def _rows(*argv: str) -> list[CheckResult]:
    ctx = _ctx(*argv)
    return [row for _, _, check in online.CHECKS for row in check(ctx)]


def _source(rows: list[CheckResult], name: str) -> list[CheckResult]:
    return [row for row in rows if row.name == name]


def _user_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


def test_unconfigured_sources_are_off() -> None:
    rows = _rows()
    for name in ("metron", "comicvine"):
        (row,) = _source(rows, name)
        assert row.status is Status.OFF
        assert not row.status.is_failure
        assert row.fix == (
            f"--auth {name}:KEY or COMICBOX_ONLINE__AUTH__{name.upper()}__KEY"
        )


def test_provenance_flag_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMICBOX_ONLINE__AUTH__COMICVINE__KEY", _CV_KEY)
    rows = _rows("--auth", f"metron:{_METRON_TOKEN}")
    (metron,) = _source(rows, "metron")
    assert (metron.status, metron.found, metron.detail) == (
        Status.OK,
        "key",
        "key from --auth" + _UNVERIFIED,
    )
    (comicvine,) = _source(rows, "comicvine")
    assert comicvine.detail == (
        "key from env COMICBOX_ONLINE__AUTH__COMICVINE__KEY" + _UNVERIFIED
    )


def test_provenance_config_files(tmp_path: Path) -> None:
    """The --config file wins over the user config, as in a run."""
    user = _user_config(
        tmp_path,
        "comicbox:\n  online:\n    auth:\n"
        f"      metron: {{key: {_METRON_TOKEN}}}\n"
        f"      comicvine: {{key: {_CV_KEY}}}\n",
    )
    cli_config = tmp_path / "tagging.yaml"
    cli_config.write_text(
        f"comicbox:\n  online:\n    auth:\n      comicvine: {{key: other-{_CV_KEY}}}\n"
    )
    rows = _rows("-c", str(cli_config))
    assert _source(rows, "metron")[0].detail == f"key from {user}" + _UNVERIFIED
    assert _source(rows, "comicvine")[0].detail == (
        f"key from {cli_config}" + _UNVERIFIED
    )


class _UsableKeyring:
    """
    A backend outside keyring's null modules.

    The host's real backend can't stand in: a headless Linux CI runner
    has none, and the doctor rightly reports that instead.
    """

    name = "usable Keyring"
    priority = 1


def test_provenance_keyring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A user with no pass sends comicbox to the keyring, as a run does."""
    looked_up = []

    def fake_keyring(source: str, username: str | None) -> str:
        looked_up.append((source, username))
        return _PASSWORD

    monkeypatch.setattr(credentials, "_try_keyring", fake_keyring)
    monkeypatch.setattr(keyring, "get_keyring", _UsableKeyring)
    _user_config(
        tmp_path, "comicbox:\n  online:\n    auth:\n      metron: {user: aj}\n"
    )
    rows = _rows()
    metron = _source(rows, "metron")
    assert metron[0].status is Status.OK
    assert metron[0].found == "user, pass"
    assert metron[0].detail == (
        f"user from {tmp_path / 'config.yaml'} · pass from keyring" + _UNVERIFIED
    )
    # Basic auth still works, but is deprecated.
    assert metron[1].status is Status.WARN
    assert metron[1].detail == "user/pass auth is deprecated"
    (keyring_row,) = _source(rows, "keyring")
    assert "consulted for metron" in keyring_row.detail
    # Loading the config asked once; the doctor never asks again itself.
    assert looked_up == [("metron", "aj")]


def test_null_keyring_warns_only_when_needed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keyring, "get_keyring", fail.Keyring)
    (row,) = _source(_rows(), "keyring")
    assert row.status is Status.OK
    monkeypatch.setattr(credentials, "_try_keyring", lambda *_args: None)
    _user_config(
        tmp_path, "comicbox:\n  online:\n    auth:\n      metron: {user: aj}\n"
    )
    (row,) = _source(_rows(), "keyring")
    assert row.status is Status.WARN
    assert row.detail == "no usable backend, but metron has a user and no pass"


def test_comicvine_budget_comes_from_the_bucket_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read-only: no client, no request, just the rate-limit file."""
    windows = {
        "search": {"limit": 200, "remaining": 199, "reset_epoch": None},
        "issues": {"limit": 200, "remaining": 180, "reset_epoch": None},
    }
    monkeypatch.setattr(
        comicvine, "shared_client_rate_limit_status", lambda _s: windows
    )
    (row,) = _source(_rows("--auth", f"comicvine:{_CV_KEY}"), "comicvine")
    assert row.detail == "key from --auth · issues 180/200 left this hour" + _UNVERIFIED
    full = {"search": {"limit": 200, "remaining": 200, "reset_epoch": None}}
    monkeypatch.setattr(comicvine, "shared_client_rate_limit_status", lambda _s: full)
    (row,) = _source(_rows("--auth", f"comicvine:{_CV_KEY}"), "comicvine")
    assert row.detail == (
        "key from --auth · 200/200 left this hour in every pool" + _UNVERIFIED
    )


def test_metron_url_and_comicvine_trailing_slash_warn() -> None:
    rows = _rows(
        "--auth",
        f"metron:{_METRON_TOKEN}",
        "--auth",
        "metron:url=https://metron.example/api",
        "--auth",
        f"comicvine:{_CV_KEY}",
        "--auth",
        "comicvine:url=https://comicvine.example/api/",
    )
    metron_warn = _source(rows, "metron")[1]
    assert metron_warn.status is Status.WARN
    assert metron_warn.detail.startswith("url is ignored")
    comicvine_warn = _source(rows, "comicvine")[1]
    assert comicvine_warn.status is Status.WARN
    assert comicvine_warn.detail == "url ends in /: requests go to //"


def test_unloaded_config_skips_the_online_checks() -> None:
    ctx = DoctorContext()
    rows = [row for _, _, check in online.CHECKS for row in check(ctx)]
    assert [(row.name, row.status) for row in rows] == [("sources", Status.WARN)]


def test_cache_dir_not_created_yet(tmp_path: Path) -> None:
    cache_dir = tmp_path / "not" / "yet"
    (row,) = _source(_rows("--cache-dir", str(cache_dir)), "cache")
    assert row.status is Status.OK
    assert row.found == cache_dir
    assert row.detail.startswith("not created yet · parent writable")
    # Checking it didn't create it.
    assert not cache_dir.exists()


def test_unwritable_cache_dir_is_misconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "access", lambda *_args, **_kwargs: False)
    (row,) = _source(_rows("--cache-dir", str(tmp_path)), "cache")
    assert row.status is Status.MISCONFIGURED
    assert row.fix == "point --cache-dir or online.cache.dir somewhere writable"


def test_proxy_vars_are_named_not_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    proxy = "http://user:proxy-secret@proxy.example:3128"
    monkeypatch.setenv("HTTPS_PROXY", proxy)
    monkeypatch.setenv("no_proxy", "localhost")
    (row,) = _source(_rows(), "proxy")
    assert row.detail == "set: HTTPS_PROXY, no_proxy"
    assert "proxy-secret" not in str(row)


def _all_secret_layers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Namespace:
    monkeypatch.setenv("COMICBOX_ONLINE__AUTH__COMICVINE__KEY", _CV_KEY)
    monkeypatch.setattr(credentials, "_try_keyring", lambda *_args: _PASSWORD)
    _user_config(
        tmp_path, "comicbox:\n  online:\n    auth:\n      metron: {user: aj}\n"
    )
    argv = ("--auth", f"metron:{_METRON_TOKEN}")
    return Namespace(comicbox=build_parser().parse_args(argv))


def test_no_socket_opens_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configured sources and all, the offline doctor never touches the network."""

    def no_network(*_args: object, **_kwargs: object) -> None:
        reason = "the offline doctor opened a socket"
        raise AssertionError(reason)

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    report = _run(DoctorContext(_all_secret_layers(tmp_path, monkeypatch)))
    assert [row for row in report.results if row.status is Status.ERROR] == []
    assert {row.name: row.status for row in report.results}["metron"] is Status.OK


def test_no_secret_value_is_rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _run(DoctorContext(_all_secret_layers(tmp_path, monkeypatch)))
    console = Console(file=StringIO(), record=True, width=200)
    render_report(report, console=console)
    out = console.export_text()
    assert "metron" in out
    for secret in (_METRON_TOKEN, _CV_KEY, _PASSWORD):
        assert secret not in out


def test_secrets_in_a_crash_message_are_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception message is free text; the runner scrubs it as a backstop."""

    def leaky(_ctx: DoctorContext) -> list[CheckResult]:
        reason = f"GET /api/?api_key={_CV_KEY} failed"
        raise RuntimeError(reason)

    monkeypatch.setattr(
        online, "CHECKS", (*online.CHECKS, (online.SECTION, "leaky", leaky))
    )
    report = _run(DoctorContext(_all_secret_layers(tmp_path, monkeypatch)))
    (row,) = [row for row in report.results if row.name == "leaky"]
    assert row.status is Status.ERROR
    assert row.detail == "RuntimeError: GET /api/?api_key=*** failed"
