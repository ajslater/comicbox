"""CLI flag parsing tests for online tagging options (v5)."""

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
    assert args.general.dry_run is True


def test_dry_run_long_flag() -> None:
    args = _parse("--dry-run")
    assert args.general.dry_run is True


def test_auth_warns_on_pass_field(capsys: pytest.CaptureFixture[str]) -> None:
    """`--auth metron:pass=secret` warns that passwords leak into shell history."""
    args = _parse("--auth", "metron:pass=secret")
    assert args.auth == ["metron:pass=secret"]
    captured = capsys.readouterr()
    assert "shell history" in captured.err


def test_auth_no_warning_on_user_field(capsys: pytest.CaptureFixture[str]) -> None:
    """`--auth metron:user=alice` does not warn."""
    args = _parse("--auth", "metron:user=alice")
    assert args.auth == ["metron:user=alice"]
    captured = capsys.readouterr()
    assert "shell history" not in captured.err


def test_id_with_multiple_paths_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        get_args(["comicbox", "--id", "metron:42", "a.cbz", "b.cbz"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "--id requires exactly one" in captured.err


def test_id_with_single_path_ok() -> None:
    args = get_args(["comicbox", "--id", "metron:42", "single.cbz"])
    post_process_args(args)  # idempotent — no raise.


def test_jobs_flag() -> None:
    args = _parse("-j", "4")
    assert args.general.jobs == 4


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
