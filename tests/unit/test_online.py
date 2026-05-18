"""Online credentials / settings resolution tests (v5)."""

from argparse import Namespace

import pytest

from comicbox.config import get_config
from comicbox.config.settings import CacheMode, Effort, MatchMode, Prompts
from comicbox.formats.base.online.cli_overrides import CliOverrides
from comicbox.formats.base.online.credentials import resolve_credentials
from comicbox.formats.base.online.env import (
    parse_bool,
    read_credential_env,
    read_online_env,
)

# ------------------------------------------------------------------ env helpers


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("0", False),
        ("true", True),
        ("FALSE", False),
        ("Yes", True),
        ("no", False),
        ("on", True),
        ("Off", False),
        (" 1 ", True),
        ("maybe", None),
        ("", None),
    ],
)
def test_parse_bool(raw: str, expected: bool | None) -> None:
    assert parse_bool(raw) is expected


def test_read_credential_env_picks_up_known_sources() -> None:
    env = {
        "COMICBOX_METRON_USER": "alice",
        "COMICBOX_METRON_PASS": "secret",
        "COMICBOX_COMICVINE_KEY": "key123",
        "COMICBOX_UNKNOWN_FIELD": "ignored",
        "OTHER_VAR": "ignored",
    }
    assert read_credential_env(env) == {
        "metron": {"user": "alice", "pass": "secret"},
        "comicvine": {"key": "key123"},
    }


def test_read_credential_env_empty() -> None:
    assert read_credential_env({}) == {}


def test_read_online_env_parses_typed_values() -> None:
    env = {
        "COMICBOX_ONLINE_MATCH": "eager",
        "COMICBOX_ONLINE_PROMPTS": "never",
        "COMICBOX_ONLINE_REMATCH": "true",
        "COMICBOX_ONLINE_ALL_SOURCES": "0",
        "COMICBOX_ONLINE_AUTO_THRESHOLD": "0.92",
        "COMICBOX_ONLINE_EFFORT": "thorough",
        "COMICBOX_ONLINE_CACHE": "refresh",
        "COMICBOX_ONLINE_CACHE_DIR": "/tmp/cb",
        "COMICBOX_ONLINE_CACHE_TTL": "24h",
        "COMICBOX_ONLINE_RETRY_BUDGET": "8",
    }
    parsed = read_online_env(env)
    assert parsed == {
        "match": "eager",
        "prompts": "never",
        "rematch": True,
        "all_sources": False,
        "auto_threshold": 0.92,
        "effort": "thorough",
        "cache": "refresh",
        "cache_dir": "/tmp/cb",
        "cache_ttl": "24h",
        "retry_budget": 8,
    }


def test_read_online_env_drops_unparseable() -> None:
    env = {
        "COMICBOX_ONLINE_AUTO_THRESHOLD": "not-a-float",
        "COMICBOX_ONLINE_RETRY_BUDGET": "not-an-int",
        "COMICBOX_ONLINE_REMATCH": "maybe",
    }
    assert read_online_env(env) == {}


# ------------------------------------------------------------- CLI overrides


def test_cli_overrides_from_auth_list_parses_field_value_pairs() -> None:
    overrides = CliOverrides.from_auth_list(
        [
            "comicvine:key=abc",
            "metron:user=bob",
            "metron:pass=secret",
            "metron:url=https://metron.local",
        ]
    )
    assert overrides.per_source["comicvine"]["key"] == "abc"
    assert overrides.per_source["metron"]["user"] == "bob"
    assert overrides.per_source["metron"]["pass"] == "secret"
    assert overrides.per_source["metron"]["url"] == "https://metron.local"


def test_cli_overrides_unknown_source_errors() -> None:
    with pytest.raises(ValueError, match="unknown source"):
        CliOverrides.from_auth_list(["nosuch:key=xyz"])


def test_cli_overrides_unknown_field_errors() -> None:
    with pytest.raises(ValueError, match="unknown field"):
        CliOverrides.from_auth_list(["metron:badfield=xyz"])


def test_cli_overrides_bad_syntax_errors() -> None:
    with pytest.raises(ValueError, match=r"<source>:<field>=<value>"):
        CliOverrides.from_auth_list(["nodelimiter"])


# ----------------------------------------------- credential resolution chain


def test_resolve_credentials_cli_beats_env_beats_config() -> None:
    creds = resolve_credentials(
        config_creds={
            "metron": {
                "user": "config_user",
                "pass": "config_pw",
                "url": "config_url",
            }
        },
        cli_overrides=CliOverrides.from_auth_list(["metron:user=cli_user"]),
        env={"COMICBOX_METRON_PASS": "env_pw"},
        use_keyring=False,
    )
    assert creds["metron"].user == "cli_user"  # CLI wins
    assert creds["metron"].password == "env_pw"  # env beats config
    assert creds["metron"].url == "config_url"  # config when nothing higher


def test_resolve_credentials_returns_all_sources() -> None:
    creds = resolve_credentials(config_creds={}, env={}, use_keyring=False)
    assert set(creds.keys()) == {"metron", "comicvine"}
    assert creds["metron"].user is None
    assert creds["comicvine"].key is None


# --------------------------------------------------------- full config flow


def test_online_disabled_by_default() -> None:
    cfg = get_config()
    assert cfg.online.lookup.enabled is False
    assert cfg.online.lookup.sources is None


def test_online_enabled_via_cli_namespace() -> None:
    cli = Namespace(online_sources=["all"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.enabled is True
    assert cfg.online.lookup.sources is None


def test_online_filter_via_cli() -> None:
    cli = Namespace(online_sources=["metron"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.enabled is True
    assert cfg.online.lookup.sources == frozenset({"metron"})


def test_explicit_id_parses() -> None:
    cli = Namespace(explicit_ids=["metron:42"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.ids == {"metron": 42}


def test_explicit_id_unknown_source_errors() -> None:
    cli = Namespace(explicit_ids=["nope:1"])
    with pytest.raises(ValueError, match="unknown source"):
        get_config(Namespace(comicbox=cli))


def test_explicit_id_non_numeric_errors() -> None:
    cli = Namespace(explicit_ids=["metron:abc"])
    with pytest.raises(ValueError, match="non-numeric"):
        get_config(Namespace(comicbox=cli))


def test_cache_off_via_cli() -> None:
    cli = Namespace(online_sources=["all"], cache="off")
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.cache.mode is CacheMode.OFF


def test_cache_refresh_via_cli() -> None:
    cli = Namespace(online_sources=["all"], cache="refresh")
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.cache.mode is CacheMode.REFRESH


def test_auto_threshold_cli_override() -> None:
    cli = Namespace(online_sources=["all"], auto_threshold=0.85)
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.tuning.auto_threshold == 0.85


# --------------------------------------- match / prompts / effort scheme


def test_match_default_is_auto() -> None:
    cli = Namespace(online_sources=["all"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.match is MatchMode.AUTO
    assert cfg.online.lookup.prompts is Prompts.ASK


def test_match_global_cli_override() -> None:
    cli = Namespace(online_sources=["all"], match="eager")
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.match is MatchMode.EAGER


def test_match_unknown_name_errors() -> None:
    cli = Namespace(online_sources=["all"], match="bogus")
    with pytest.raises(ValueError, match="--match: unknown name"):
        get_config(Namespace(comicbox=cli))


def test_prompts_never_via_cli() -> None:
    cli = Namespace(online_sources=["all"], prompts="never")
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.prompts is Prompts.NEVER


def test_effort_via_cli() -> None:
    cli = Namespace(online_sources=["all"], effort="thorough")
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.tuning.effort is Effort.THOROUGH


def test_explicit_id_implicitly_activates_online() -> None:
    """`--id comicvine:42` alone should enable online for ComicVine."""
    cli = Namespace(explicit_ids=["comicvine:42"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.enabled is True
    assert cfg.online.lookup.sources == frozenset({"comicvine"})
    assert cfg.online.lookup.ids == {"comicvine": 42}


def test_explicit_id_union_with_online_filter() -> None:
    """--id comicvine:42 --online metron → both sources active."""
    cli = Namespace(
        online_sources=["metron"],
        explicit_ids=["comicvine:42"],
    )
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.enabled is True
    assert cfg.online.lookup.sources == frozenset({"metron", "comicvine"})


def test_explicit_id_with_online_all_keeps_all() -> None:
    """--id comicvine:42 --online all keeps `all` (None) sentinel."""
    cli = Namespace(
        online_sources=["all"],
        explicit_ids=["comicvine:42"],
    )
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.enabled is True
    assert cfg.online.lookup.sources is None


def test_explicit_id_comicvine_accepts_4000_prefix() -> None:
    """--id comicvine:4000-12345 normalizes to bare integer 12345."""
    cli = Namespace(explicit_ids=["comicvine:4000-12345"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.ids == {"comicvine": 12345}


def test_explicit_id_comicvine_rejects_other_resource_types() -> None:
    """--id comicvine:4005-N (volume) errors; we only support issues."""
    cli = Namespace(explicit_ids=["comicvine:4005-12345"])
    with pytest.raises(ValueError, match="resource type 4005"):
        get_config(Namespace(comicbox=cli))


def test_explicit_id_metron_does_not_strip_prefix() -> None:
    """`metron:12-345` should still error since metron uses bare ints."""
    cli = Namespace(explicit_ids=["metron:12-345"])
    with pytest.raises(ValueError, match="non-numeric"):
        get_config(Namespace(comicbox=cli))
