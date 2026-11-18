"""
The doctor's Config section.

Each of these is a finding a run only logs once and carries on past: a
skipped user config, a dropped key, an ignored env var. The suite's
conftest points ``COMICBOXDIR`` at ``tmp_path``, so ``tmp_path /
"config.yaml"`` is the user config here.
"""

from __future__ import annotations

from argparse import Namespace
from typing import TYPE_CHECKING

from comicbox.cli.parser import build_parser
from comicbox.doctor import settings
from comicbox.doctor.context import DoctorContext
from comicbox.doctor.result import Status

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from comicbox.doctor.result import CheckResult


def _ctx(*argv: str) -> DoctorContext:
    return DoctorContext(Namespace(comicbox=build_parser().parse_args(argv)))


def _config_rows(ctx: DoctorContext) -> list[CheckResult]:
    return [row for _, _, check in settings.CHECKS for row in check(ctx)]


def _user_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


def test_no_user_config_is_fine(tmp_path: Path) -> None:
    ctx = _ctx()
    rows = _config_rows(ctx)
    assert [(row.name, row.status) for row in rows] == [
        ("user config", Status.OK),
        ("values", Status.OK),
    ]
    assert rows[0].found == tmp_path / "config.yaml"
    assert rows[0].detail.startswith("none; defaults apply")
    assert ctx.settings is not None


def test_bad_yaml_names_the_file(tmp_path: Path) -> None:
    """A run skips it with one warning and carries on with none of its settings."""
    path = _user_config(tmp_path, "comicbox:\n  general:\n    recurse: [\n")
    ctx = _ctx()
    user, values = _config_rows(ctx)
    assert user.status is Status.MISCONFIGURED
    assert user.found == path
    assert user.detail.startswith("skipped:")
    assert "line" in user.detail
    # The run goes on with the defaults, and so does the doctor.
    assert values.status is Status.OK
    assert ctx.settings is not None


def test_unknown_keys_warn_with_a_suggestion(tmp_path: Path) -> None:
    path = _user_config(
        tmp_path,
        "comicbox:\n"
        "  geneal: {}\n"
        "  online:\n"
        "    auth:\n"
        "      metrn: {}\n"
        "    tuning:\n"
        "      per_source:\n"
        "        comicvin: {effort: minimal}\n",
    )
    rows = [row for row in _config_rows(_ctx()) if row.name == "unknown key"]
    assert {row.detail for row in rows} == {
        "geneal is ignored",
        "online.auth.metrn is ignored",
        "online.tuning.per_source.comicvin is ignored",
    }
    assert all(row.status is Status.WARN and row.found == path for row in rows)
    fixes = {row.fix for row in rows}
    assert "did you mean online.auth.metron?" in fixes
    assert "did you mean general?" in fixes


def test_unknown_key_inside_per_source_warns(tmp_path: Path) -> None:
    """
    Confuse type-checks a per-source block but drops keys it doesn't know.

    So a typo there validates fine and does nothing; only the doctor says so.
    """
    _user_config(
        tmp_path,
        "comicbox:\n  online:\n    tuning:\n      per_source:\n"
        "        metron: {effor: minimal, rate_limit: {per_minit: 10}}\n",
    )
    rows = _config_rows(_ctx())
    warns = [row for row in rows if row.status is Status.WARN]
    assert [(row.detail, row.fix) for row in warns] == [
        (
            "online.tuning.per_source.metron.effor is ignored",
            "did you mean online.tuning.per_source.metron.effort?",
        ),
        (
            "online.tuning.per_source.metron.rate_limit.per_minit is ignored",
            "did you mean online.tuning.per_source.metron.rate_limit.per_minute?",
        ),
    ]
    (values,) = [row for row in rows if row.name == "values"]
    assert values.status is Status.OK


def test_bad_value_inside_per_source_is_misconfigured(tmp_path: Path) -> None:
    """The template does check the types of the keys it knows."""
    _user_config(
        tmp_path,
        "comicbox:\n  online:\n    tuning:\n      per_source:\n"
        "        metron: {auto_threshold: high}\n",
    )
    ctx = _ctx()
    (values,) = [row for row in _config_rows(ctx) if row.name == "values"]
    assert values.status is Status.MISCONFIGURED
    assert "auto_threshold" in values.detail
    assert ctx.settings is None


def test_settings_a_run_reads_are_not_unknown(tmp_path: Path) -> None:
    """Metadata keys are data, and the CLI shorthands work from a file too."""
    _user_config(
        tmp_path,
        "comicbox:\n"
        "  general:\n"
        "    quiet: 1\n"
        "    metadata: {series: Foo, publisher: Bar}\n"
        "  print: {version: true}\n"
        "  online:\n"
        "    tuning:\n"
        "      per_source:\n"
        "        metron: {auto_threshold: 0.9}\n",
    )
    rows = _config_rows(_ctx())
    assert all(row.status is Status.OK for row in rows), rows


def test_type_error_is_misconfigured(tmp_path: Path) -> None:
    _user_config(tmp_path, "comicbox:\n  general:\n    jobs: lots\n")
    ctx = _ctx()
    (values,) = [row for row in _config_rows(ctx) if row.name == "values"]
    assert values.status is Status.MISCONFIGURED
    assert "comicbox.general.jobs" in values.detail
    assert ctx.settings is None


def test_legacy_env_var_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMICBOX_METRON_KEY", "s3cr3t-token")
    rows = [row for row in _config_rows(_ctx()) if row.status is Status.WARN]
    assert [(row.name, row.found, row.fix) for row in rows] == [
        (
            "env var",
            "COMICBOX_METRON_KEY",
            "rename it COMICBOX_ONLINE__AUTH__METRON__KEY",
        )
    ]
    assert all("s3cr3t-token" not in str(row) for row in rows)


def test_unknown_env_var_key_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMICBOX_ONLINE__AUTH__METRON__TOKEN", "abc123")
    (row,) = [row for row in _config_rows(_ctx()) if row.status is Status.WARN]
    assert row.name == "unknown key"
    assert row.found == "env COMICBOX_ONLINE__AUTH__METRON__TOKEN"
    assert row.detail == "online.auth.metron.token is ignored"


def test_config_env_var_loads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMICBOX_GENERAL__CONFIG", "/somewhere.yaml")
    (row,) = [row for row in _config_rows(_ctx()) if row.status is Status.WARN]
    assert row.found == "COMICBOX_GENERAL__CONFIG"
    assert row.fix == "pass --config PATH instead"


def test_cli_config_file_is_checked_first(tmp_path: Path) -> None:
    path = tmp_path / "tagging [digital].yaml"
    path.write_text("comicbox:\n  general:\n    recurse: true\n")
    ctx = _ctx("--config", str(path))
    rows = _config_rows(ctx)
    assert [(row.name, row.status) for row in rows] == [
        ("--config", Status.OK),
        ("user config", Status.OK),
        ("values", Status.OK),
    ]
    assert rows[0].found == path
    assert ctx.settings is not None
    assert ctx.settings.general.recurse is True


def test_missing_cli_config_is_one_row(tmp_path: Path) -> None:
    """A run exits on it; the doctor reports it once and carries on."""
    ctx = _ctx("-c", str(tmp_path / "missing.yaml"))
    rows = _config_rows(ctx)
    assert [(row.name, row.status) for row in rows] == [
        ("--config", Status.MISCONFIGURED),
        ("user config", Status.OK),
    ]
    assert rows[0].detail == "not found"
    assert ctx.settings is None
