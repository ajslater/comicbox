"""
A mistyped ``--auth`` entry never reaches the output, at any log level.

Its value is a token. Run and doctor alike report the error with the
entry's position and what is valid, so nothing typed after the source
name, nor an unknown source name, is printed or logged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from loguru import logger as loguru_logger

from comicbox import cli
from comicbox import logger as comicbox_logger

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_ENTRIES = (
    "comicvine:FAKE-TOKEN-0000==",
    "comicvine:kye=FAKE-TOKEN-0000",
    "FAKE-TOKEN-0000:x",
    "FAKE-TOKEN-0000",
)
_LEVELS = ("TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL")


@pytest.fixture
def logged(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """
    Every loguru message at every level, whatever level the run asks for.

    The doctor's init_logging would replace this sink with its own, so it
    is held off: nothing logged anywhere escapes the check.
    """
    monkeypatch.setattr(comicbox_logger, "init_logging", lambda *_a, **_k: None)
    messages: list[str] = []
    sink = loguru_logger.add(messages.append, level=0, format="{message}")
    try:
        yield messages
    finally:
        loguru_logger.remove(sink)


def _run(*argv: str) -> int:
    try:
        cli.main(("comicbox", *argv))
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


@pytest.mark.parametrize("level", _LEVELS)
@pytest.mark.parametrize("entry", _ENTRIES)
@pytest.mark.parametrize("doctor", [False, True])
def test_no_part_of_a_mistyped_auth_entry_is_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    logged: list[str],
    level: str,
    entry: str,
    *,
    doctor: bool,
) -> None:
    monkeypatch.setenv("COMICBOX_GENERAL__LOGLEVEL", level)
    argv = (
        ("doctor", "--auth", entry)
        if doctor
        else (
            "--auth",
            entry,
            "-p",
            str(tmp_path / "x.cbz"),
        )
    )
    assert _run(*argv) == 1
    captured = capsys.readouterr()
    output = "\n".join((captured.out, captured.err, *logged)).lower()
    assert "--auth entry 1" in " ".join(output.split())
    assert "fake-token" not in output
