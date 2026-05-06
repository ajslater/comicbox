"""CLI flag parsing tests for online tagging options and the dry-run rename."""

from argparse import Namespace

import pytest

from comicbox.cli import get_args, post_process_args


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
    assert args.dry_run is True


def test_dry_run_long_flag() -> None:
    args = _parse("--dry-run")
    assert args.dry_run is True


def test_y_alias_still_sets_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    """-y is the deprecation-warned alias kept through the 4.x series."""
    args = _parse("-y")
    assert args.dry_run is True
    captured = capsys.readouterr()
    assert "deprecated" in captured.err.lower()


def test_api_password_warns(capsys: pytest.CaptureFixture[str]) -> None:
    args = _parse("--api-password", "metron:secret")
    assert args.api_passwords == ["metron:secret"]
    captured = capsys.readouterr()
    assert "shell history" in captured.err


def test_id_with_multiple_paths_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = get_args(["comicbox", "--id", "metron:42", "a.cbz", "b.cbz"])
    with pytest.raises(SystemExit) as exc_info:
        post_process_args(args)
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "--id requires exactly one" in captured.err


def test_id_with_single_path_ok() -> None:
    args = get_args(["comicbox", "--id", "metron:42", "single.cbz"])
    post_process_args(args)  # no raise


def test_jobs_flag() -> None:
    args = _parse("-j", "4")
    assert args.jobs == 4


def test_confidence_threshold_flag() -> None:
    args = _parse("--confidence-threshold", "0.9")
    assert args.confidence_threshold == 0.9


def test_no_cache_flag() -> None:
    args = _parse("--no-cache")
    assert args.no_cache is True


def test_refresh_cache_flag() -> None:
    args = _parse("--refresh-cache")
    assert args.refresh_cache is True
