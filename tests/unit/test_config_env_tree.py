"""
Env vars reach every config key through one mechanism.

There used to be two systems: confuse's ``set_env()``, which mounted at
the configuration root while the whole tree hangs off the ``comicbox``
key (so it read nothing anyone would plausibly type), and a bespoke
parser covering a hand-listed subset of online keys. Mounting the
EnvSource on the tree instead makes every template key settable by
construction, which is what these tests pin — including against a
confuse upgrade quietly changing EnvSource semantics.
"""

from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from confuse import ConfigError
from loguru import logger as loguru_logger

from comicbox.config import get_config
from comicbox.config.online.settings import CacheMode
from comicbox.config.read import _LEGACY_ENV_VARS


@pytest.fixture
def alt_config(tmp_path: Path) -> Path:
    """Write a config file setting keys the env vars below also set."""
    path = tmp_path / "alt.yaml"
    path.write_text(
        "comicbox:\n"
        "  general:\n"
        "    jobs: 7\n"
        "  online:\n"
        "    tuning:\n"
        "      auto_threshold: 0.11\n"
    )
    return path


def test_general_bool_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A plain template key is env-settable with no bespoke parsing."""
    monkeypatch.setenv("COMICBOX_GENERAL__RECURSE", "true")
    assert get_config().general.recurse is True


def test_yaml_scalar_typing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Values type like the YAML layer: ints int, floats float."""
    monkeypatch.setenv("COMICBOX_GENERAL__JOBS", "4")
    monkeypatch.setenv("COMICBOX_ONLINE__TUNING__AUTO_THRESHOLD", "0.8")
    settings = get_config()
    assert settings.general.jobs == 4
    assert settings.online.tuning.auto_threshold == 0.8


def test_deep_online_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """The online block is reachable at full depth, cache and tuning alike."""
    monkeypatch.setenv("COMICBOX_ONLINE__CACHE__MODE", "refresh")
    monkeypatch.setenv("COMICBOX_ONLINE__TUNING__RETRY_BUDGET", "9")
    settings = get_config()
    assert settings.online.cache.mode is CacheMode.REFRESH
    assert settings.online.tuning.retry_budget == 9


def test_credentials_arrive_through_the_config_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Auth env vars reach credential resolution via the tree.

    ``resolve_credentials`` no longer reads the environment itself; this
    is the route that replaced its env layer.
    """
    monkeypatch.setenv("COMICBOX_ONLINE__AUTH__METRON__KEY", "env-token")
    assert get_config().online.auth.sources["metron"].key == "env-token"


def test_env_beats_the_config_file(
    monkeypatch: pytest.MonkeyPatch, alt_config: Path
) -> None:
    """Env sits above the -c file, for tree keys and online keys alike."""
    monkeypatch.setenv("COMICBOX_GENERAL__JOBS", "2")
    monkeypatch.setenv("COMICBOX_ONLINE__TUNING__AUTO_THRESHOLD", "0.99")
    cns = Namespace(**{"general.config": str(alt_config)})
    settings = get_config(Namespace(comicbox=cns))
    assert settings.general.jobs == 2
    assert settings.online.tuning.auto_threshold == 0.99


def test_cli_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI still outranks the environment."""
    monkeypatch.setenv("COMICBOX_GENERAL__JOBS", "2")
    cns = Namespace(**{"general.jobs": 6})
    assert get_config(Namespace(comicbox=cns)).general.jobs == 6


def test_indexed_list_form(monkeypatch: pytest.MonkeyPatch) -> None:
    """Container keys take EnvSource's indexed form."""
    monkeypatch.setenv("COMICBOX_READ__FORMATS__0", "cix")
    formats = get_config().read.formats
    assert len(formats) == 1
    assert next(iter(formats)).value.filename == "ComicInfo.xml"


def test_csv_sources_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """online.lookup.sources also accepts a comma-separated string."""
    monkeypatch.setenv("COMICBOX_ONLINE__LOOKUP__SOURCES", "comicvine,metron")
    assert get_config().online.lookup.sources == ("comicvine", "metron")


def test_unparseable_value_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    A bad env value raises instead of being dropped.

    The bespoke reader silently discarded values it couldn't parse, so a
    typo'd knob looked exactly like an unset one.
    """
    monkeypatch.setenv("COMICBOX_GENERAL__JOBS", "banana")
    with pytest.raises(ConfigError):
        get_config()


def test_legacy_names_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    """A retired flat env var says what replaced it rather than doing nothing."""
    monkeypatch.setenv("COMICBOX_METRON_KEY", "stale")
    messages: list[str] = []
    handler_id = loguru_logger.add(messages.append, level="WARNING", format="{message}")
    try:
        get_config()
    finally:
        loguru_logger.remove(handler_id)
    rendered = "\n".join(messages)
    assert "COMICBOX_METRON_KEY" in rendered
    assert "COMICBOX_ONLINE__AUTH__METRON__KEY" in rendered


def test_every_legacy_name_maps_to_a_live_var() -> None:
    """The rename table can't point at a spelling the mount won't read."""
    for old, new in _LEGACY_ENV_VARS.items():
        assert new.startswith("COMICBOX_")
        assert "__" in new, f"{old} maps to {new}, which isn't a tree path"


def _write_formats(config: Any) -> set[str]:
    return {fmt.name for fmt in config.write.formats}


def _read_formats(config: Any) -> set[str]:
    return {fmt.name for fmt in config.read.formats}


def _export_formats(config: Any) -> set[str]:
    return {fmt.name for fmt in config.convert.export_formats}


@pytest.mark.parametrize(
    ("variable", "value", "read", "expected"),
    [
        # Split on commas, as the CLI's -w, -f, --read-except, -e and -D are.
        ("COMICBOX_WRITE__FORMATS", "cix", _write_formats, {"COMIC_INFO"}),
        (
            "COMICBOX_WRITE__FORMATS",
            "cix, mi",
            _write_formats,
            {"COMIC_INFO", "METRON_INFO"},
        ),
        ("COMICBOX_READ__FORMATS", "cix", _read_formats, {"COMIC_INFO"}),
        (
            "COMICBOX_CONVERT__EXPORT_FORMATS",
            "cix,mi",
            _export_formats,
            {"COMIC_INFO", "METRON_INFO"},
        ),
        (
            "COMICBOX_GENERAL__DELETE_KEYS",
            "summary,notes",
            lambda config: config.general.delete_keys,
            frozenset({"summary", "notes"}),
        ),
        # Whole, as the CLI's -m and -i take each value.
        (
            "COMICBOX_GENERAL__METADATA_CLI",
            "{summary: x, notes: y}",
            lambda config: config.general.metadata_cli,
            ("{summary: x, notes: y}",),
        ),
        (
            "COMICBOX_CONVERT__IMPORT_PATHS",
            "a,b.json",
            lambda config: config.convert.import_paths,
            (Path("a,b.json"),),
        ),
    ],
)
def test_a_plain_string_at_a_list_setting_is_that_list(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
    read: Callable[[Any], Any],
    expected: Any,
) -> None:
    """B4: COMICBOX_WRITE__FORMATS=cix was read as c, i and x."""
    monkeypatch.setenv(variable, value)
    assert read(get_config(None)) == expected


def test_a_setting_that_takes_a_string_keeps_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Print phases are a string of letters, not a comma-separated list."""
    monkeypatch.setenv("COMICBOX_PRINT__PHASES", "ns")
    assert {phase.name for phase in get_config(None).print.phases} == {
        "NORMALIZED",
        "SOURCE",
    }
