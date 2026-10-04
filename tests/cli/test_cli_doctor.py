"""
``comicbox doctor`` through the real CLI entry point.

The doctor is a special first argument, as in picopt, not a subcommand:
`cli.main` sniffs it before building the normal run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from comicbox import cli, doctor, logger
from comicbox.doctor.result import CheckResult, Status

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """Point loguru back at stdout; the doctor bound it to the captured one."""
    try:
        yield
    finally:
        logger._initialized_key = None
        logger.init_logging()


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    """Run the CLI; return its exit code and its stdout and stderr, unwrapped."""
    code = 0
    try:
        cli.main(("comicbox", *argv))
    except SystemExit as exc:
        code = int(exc.code or 0)
    captured = capsys.readouterr()
    return code, " ".join(captured.out.split()), captured.err


def _stub_checks(monkeypatch: pytest.MonkeyPatch, *rows: CheckResult) -> None:
    monkeypatch.setattr(doctor, "_checks", lambda: (("S", "stub", lambda _ctx: rows),))


_MISSING = CheckResult(
    "Archives", "CBR", Status.MISSING, detail="no RAR tool", fix="brew install rar"
)
_WARN = CheckResult("Config", "unknown key", Status.WARN, detail="geneal is ignored")


def test_doctor_dispatches(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, "doctor")
    assert out.startswith("comicbox doctor comicbox ")
    for section in ("Archives", "Config", "Online", "Python packages"):
        assert section in out
    assert code in (0, 1)


def test_healthy_exits_zero(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_checks(monkeypatch, CheckResult("Archives", "CBZ", Status.OK))
    code, out, _ = _run(capsys, "doctor")
    assert code == 0
    assert out.endswith("✓ 0 problems")


def test_missing_row_exits_one(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_checks(monkeypatch, _MISSING)
    code, out, _ = _run(capsys, "doctor")
    assert code == 1
    assert "→ brew install rar" in out


def test_problems_only(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """-q keeps the failure and its fix, drops the WARN row, keeps the counts."""
    _stub_checks(monkeypatch, _MISSING, _WARN)
    full_code, _, _ = _run(capsys, "doctor")
    code, out, _ = _run(capsys, "doctor", "-q")
    assert code == full_code == 1
    assert "✗ MISSING CBR" in out
    assert "→ brew install rar" in out
    assert "geneal" not in out
    assert out.endswith("✗ 1 problem · 1 warning")


def test_healthy_problems_only_prints_one_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_checks(monkeypatch, CheckResult("Archives", "CBZ", Status.OK))
    assert _run(capsys, "doctor", "-q")[:2] == (0, "✓ 0 problems")


def test_problems_flag_stays_out_of_a_normal_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, _, err = _run(capsys, "-q")
    assert code == 2
    assert "unrecognized arguments: -q" in err


@pytest.mark.parametrize("flag", ["--config", "-c"])
def test_bad_cli_config_is_misconfigured(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, flag: str
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("comicbox:\n  general: [\n")
    code, out, _ = _run(capsys, "doctor", flag, str(bad))
    assert code == 1
    assert "✗ MISCONFIGURED --config" in out
    assert "bad.yaml" in out


def test_missing_cli_config_is_a_row_not_a_traceback(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code, out, err = _run(capsys, "doctor", "--config", str(tmp_path / "gone.yaml"))
    assert code == 1
    assert "✗ MISCONFIGURED --config" in out
    assert "not found" in out
    assert "Traceback" not in out + err


def test_good_cli_config_feeds_the_later_checks(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Its online.auth key is the one the Online section checks."""
    good = tmp_path / "good.yaml"
    good.write_text(
        "comicbox:\n  online:\n    auth:\n      metron: {key: tok3n-value}\n"
    )
    _, out, _ = _run(capsys, "doctor", "--config", str(good))
    assert "✓ OK --config" in out
    assert "✓ OK metron key key from" in out
    assert "tok3n-value" not in out


def test_broken_user_config_renders_a_report(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A run would skip it with one warning; the doctor reports it."""
    (tmp_path / "config.yaml").write_text("comicbox: [\n")
    code, out, err = _run(capsys, "doctor")
    assert code == 1
    assert "✗ MISCONFIGURED user config" in out
    assert "Traceback" not in out + err


def test_paths_are_ignored_with_a_warning(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_checks(monkeypatch, CheckResult("Archives", "CBZ", Status.OK))
    code, _, err = _run(capsys, "doctor", "a.cbz", "b.cbr")
    assert code == 0
    assert "ignoring 2 path(s)" in err


def test_dot_slash_doctor_is_a_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """A comic file named doctor is reachable, as ./doctor."""
    seen = []

    class FakeRunner:
        failure_count = 0

        def __init__(self, args: Namespace) -> None:
            seen.append(args.comicbox.paths)

        def run(self) -> None:
            pass

    def no_doctor(*_args: object) -> int:
        reason = "dispatched to the doctor"
        raise AssertionError(reason)

    monkeypatch.setattr(cli, "Runner", FakeRunner)
    monkeypatch.setattr(doctor, "main", no_doctor)
    cli.main(("comicbox", "./doctor"))
    assert seen == [["./doctor"]]


def test_doctor_help_names_doctor_mode(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, "doctor", "--help")
    assert code == 0
    assert out.startswith("Usage: comicbox doctor")
    assert "--problems" in out
