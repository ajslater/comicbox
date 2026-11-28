"""CLI flag parsing tests for online tagging options (v4)."""

import shutil
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from comicbox.cli import get_args, main
from comicbox.run import Runner
from tests.const import CIX_CBZ_SOURCE_PATH


def _parse(*flags: str) -> Namespace:
    return get_args(["comicbox", *flags, "test.cbz"])


def test_online_requires_value() -> None:
    """`--online` with no value at all errors via argparse."""
    with pytest.raises(SystemExit):
        get_args(["comicbox", "--online"])


def test_online_all_sentinel() -> None:
    args = _parse("--online", "all")
    assert args.online_sources == ["all"]


def test_online_csv() -> None:
    args = _parse("--online", "metron,comicvine")
    assert args.online_sources == ["metron", "comicvine"]


def test_id_repeatable() -> None:
    args = _parse("--id", "metron:42", "--id", "comicvine:1234")
    assert args.explicit_ids == ["metron:42", "comicvine:1234"]


def test_dry_run_short_flag_is_n() -> None:
    args = _parse("-n")
    assert getattr(args, "general.dry_run") is True


def test_dry_run_long_flag() -> None:
    args = _parse("--dry-run")
    assert getattr(args, "general.dry_run") is True


def test_auth_is_repeatable() -> None:
    """Each `--auth` is collected raw; `CliOverrides` validates them."""
    args = _parse("--auth", "metron:TOKEN", "--auth", "comicvine:url=https://cv")
    assert args.auth == ["metron:TOKEN", "comicvine:url=https://cv"]


def test_id_with_multiple_paths_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        get_args(["comicbox", "--id", "metron:42", "a.cbz", "b.cbz"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "--id requires exactly one" in captured.err


@pytest.mark.parametrize("jobs", ["1", "2"])
def test_id_with_directory_of_several_comics_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    jobs: str,
) -> None:
    """
    The runtime --id refusal is a usage error, like the parse-time one.

    It printed a bare yellow line and exited 1, while two typed paths got
    the parser's `comicbox: error:` line and exit 2.
    """
    # argparse names the program from argv[0], which is pytest's here.
    monkeypatch.setattr("sys.argv", ["comicbox"])
    comics = tmp_path / "comics"
    comics.mkdir()
    for index in range(2):
        shutil.copy(CIX_CBZ_SOURCE_PATH, comics / f"comic_{index}.cbz")
    seen: list[Path] = []
    with (
        patch.object(Runner, "run_on_file", lambda _self, path: seen.append(path)),
        pytest.raises(SystemExit) as exc_info,
    ):
        main(["comicbox", "-r", "-j", jobs, "--id", "metron:123", str(comics)])
    assert exc_info.value.code == 2  # noqa: PLR2004
    captured = capsys.readouterr()
    assert "comicbox: error: --id requires exactly one comic, 2 found" in captured.err
    assert seen == []


def test_other_configuration_error_exits_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A ConfigurationError that is not a usage error keeps exit status 1."""
    from comicbox.exceptions import ConfigurationError

    def _raise(_self: Runner) -> None:
        reason = "bad value"
        raise ConfigurationError(reason)

    with patch.object(Runner, "run", _raise), pytest.raises(SystemExit) as exc_info:
        main(["comicbox", "single.cbz"])
    assert exc_info.value.code == 1
    assert "error:" not in capsys.readouterr().err


def test_id_with_single_path_ok() -> None:
    args = get_args(["comicbox", "--id", "metron:42", "single.cbz"])
    assert args.explicit_ids == ["metron:42"]


def test_jobs_flag() -> None:
    args = _parse("-j", "4")
    assert getattr(args, "general.jobs") == 4


def test_auto_threshold_flag() -> None:
    args = _parse("--auto-threshold", "0.9")
    assert args.auto_threshold == 0.9


def test_match_flag() -> None:
    args = _parse("--match", "eager")
    assert args.match == "eager"


def test_match_rejects_unknown_choice() -> None:
    with pytest.raises(SystemExit):
        get_args(["comicbox", "--match", "bogus", "test.cbz"])


def test_prompts_never_flag() -> None:
    args = _parse("--prompts", "never")
    assert args.prompts == "never"


def test_cache_off_flag() -> None:
    args = _parse("--cache", "off")
    assert args.cache == "off"


def test_cache_refresh_flag() -> None:
    args = _parse("--cache", "refresh")
    assert args.cache == "refresh"


def test_rematch_flag() -> None:
    args = _parse("--rematch")
    assert args.rematch is True


def test_all_sources_flag() -> None:
    args = _parse("--all-sources")
    assert args.all_sources is True


def test_effort_flag() -> None:
    args = _parse("--effort", "thorough")
    assert args.effort == "thorough"
