"""
Unknown online source names must fail loudly, not widen the run.

Regression: ``_normalize_sources`` warned about unknown names and
dropped them. When *every* name was unknown the survivors were the
empty tuple — which is the ``ALL_SOURCES`` sentinel meaning "query every
configured source". So ``--online metrn`` (a typo) didn't narrow the run
to Metron, it silently broadened it to Metron *and* Comic Vine, burning
API budget on a source the user never named. The same collapse applied
to the env and config-file layers.
"""

from __future__ import annotations

from argparse import Namespace

import pytest

from comicbox.cli import get_args
from comicbox.config import get_config
from comicbox.formats.base.online import SOURCE_NAMES


def _settings_for_online(value: str):
    return get_config(Namespace(comicbox=get_args(("comicbox", "-o", value, "x.cbz"))))


@pytest.mark.parametrize(
    "value",
    ["bogus", "metrn", "bogus,nonsense", "metron,bogus", "bogus,metron"],
)
def test_unknown_cli_source_raises(value: str) -> None:
    """Any unknown name in ``--online`` aborts, even alongside a valid one."""
    with pytest.raises(ValueError, match="unknown source"):
        _settings_for_online(value)


def test_unknown_source_error_names_the_flag_and_the_valid_set() -> None:
    """The message has to be actionable: what was wrong, what's allowed."""
    with pytest.raises(ValueError, match="unknown source") as exc_info:
        _settings_for_online("metrn")
    message = str(exc_info.value)
    assert "--online" in message
    assert "metrn" in message
    for name in SOURCE_NAMES:
        assert name in message


def test_known_source_selects_only_that_source() -> None:
    """The whole point of naming a source: nothing else runs."""
    settings = _settings_for_online("metron")
    assert settings.online.lookup.enabled is True
    assert settings.online.lookup.sources == ("metron",)


def test_all_sentinel_still_selects_everything() -> None:
    """``--online all`` keeps meaning "every configured source"."""
    settings = _settings_for_online("all")
    assert settings.online.lookup.enabled is True
    # None / the empty ALL_SOURCES tuple both mean "every source".
    assert not settings.online.lookup.sources


def test_empty_source_list_still_selects_everything() -> None:
    """An empty value names nothing, so it keeps meaning "every source"."""
    settings = _settings_for_online("")
    assert settings.online.lookup.enabled is True
    assert not settings.online.lookup.sources


def test_unknown_env_source_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """The env layer collapses the same way; it has to raise too."""
    monkeypatch.setenv("COMICBOX_ONLINE_SOURCES", "bogus")
    with pytest.raises(ValueError, match="unknown source"):
        get_config(Namespace(comicbox=get_args(("comicbox", "-o", "x.cbz"))))


def test_unknown_config_file_source_raises() -> None:
    """So does a stale ``online.lookup.sources`` key in a config file."""
    with pytest.raises(ValueError, match="unknown source"):
        get_config({"comicbox": {"online": {"lookup": {"sources": ["bogus"]}}}})
