"""Online credentials / settings resolution tests."""

from argparse import Namespace

import pytest

from comicbox.config import get_config
from comicbox.online.cli_overrides import CliOverrides
from comicbox.online.credentials import resolve_credentials
from comicbox.online.env import parse_bool, read_credential_env, read_policy_env

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
        "COMICBOX_METRON_USERNAME": "alice",
        "COMICBOX_METRON_PASSWORD": "secret",
        "COMICBOX_COMICVINE_API_KEY": "key123",
        "COMICBOX_UNKNOWN_FIELD": "ignored",
        "OTHER_VAR": "ignored",
    }
    assert read_credential_env(env) == {
        "metron": {"username": "alice", "password": "secret"},
        "comicvine": {"api_key": "key123"},
    }


def test_read_credential_env_empty() -> None:
    assert read_credential_env({}) == {}


def test_read_policy_env_parses_typed_values() -> None:
    env = {
        "COMICBOX_ONLINE_ACCEPT_ONLY": "true",
        "COMICBOX_ONLINE_SKIP_MULTIPLE": "0",
        "COMICBOX_ONLINE_CONFIDENCE_THRESHOLD": "0.92",
        "COMICBOX_ONLINE_CACHE_TTL": "24h",
        "COMICBOX_ONLINE_CACHE_DIR": "/tmp/cb",
        "COMICBOX_ONLINE_RETRY_BUDGET": "8",
    }
    parsed = read_policy_env(env)
    assert parsed == {
        "accept_only": True,
        "skip_multiple": False,
        "confidence_threshold": 0.92,
        "cache_ttl": "24h",
        "cache_dir": "/tmp/cb",
        "retry_budget": 8,
    }


def test_read_policy_env_drops_unparseable() -> None:
    env = {
        "COMICBOX_ONLINE_CONFIDENCE_THRESHOLD": "not-a-float",
        "COMICBOX_ONLINE_RETRY_BUDGET": "not-an-int",
        "COMICBOX_ONLINE_ACCEPT_ONLY": "maybe",
    }
    assert read_policy_env(env) == {}


# ------------------------------------------------------------- CLI overrides


def test_cli_overrides_parse_db_value_pairs() -> None:
    overrides = CliOverrides.from_cli(
        api_keys=["comicvine:abc"],
        api_users=["metron:bob"],
        api_passwords=["metron:secret"],
        api_urls=["metron:https://metron.local"],
    )
    assert overrides.per_source["comicvine"]["api_key"] == "abc"
    assert overrides.per_source["metron"]["username"] == "bob"
    assert overrides.per_source["metron"]["password"] == "secret"
    assert overrides.per_source["metron"]["url"] == "https://metron.local"


def test_cli_overrides_unknown_source_errors() -> None:
    with pytest.raises(ValueError, match="unknown online source"):
        CliOverrides.from_cli(api_keys=["nosuch:xyz"])


def test_cli_overrides_missing_separator_errors() -> None:
    with pytest.raises(ValueError, match="DB:VALUE"):
        CliOverrides.from_cli(api_keys=["no_colon_here"])


# ----------------------------------------------- credential resolution chain


def test_resolve_credentials_cli_beats_env_beats_config() -> None:
    creds = resolve_credentials(
        config_creds={
            "metron": {
                "username": "config_user",
                "password": "config_pw",
                "url": "config_url",
            }
        },
        cli_overrides=CliOverrides.from_cli(api_users=["metron:cli_user"]),
        env={"COMICBOX_METRON_PASSWORD": "env_pw"},
        use_keyring=False,
    )
    assert creds["metron"].username == "cli_user"  # CLI wins
    assert creds["metron"].password == "env_pw"  # env beats config
    assert creds["metron"].url == "config_url"  # config when nothing higher


def test_resolve_credentials_returns_all_sources() -> None:
    creds = resolve_credentials(config_creds={}, env={}, use_keyring=False)
    assert set(creds.keys()) == {"metron", "comicvine"}
    assert creds["metron"].username is None
    assert creds["comicvine"].api_key is None


# --------------------------------------------------------- full config flow


def test_online_disabled_by_default() -> None:
    cfg = get_config()
    assert cfg.online.enabled is False
    assert cfg.online.selected_sources is None


def test_online_enabled_via_cli_namespace() -> None:
    cli = Namespace(online_sources=["all"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.enabled is True
    assert cfg.online.selected_sources is None


def test_online_filter_via_cli() -> None:
    cli = Namespace(online_sources=["metron"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.enabled is True
    assert cfg.online.selected_sources == frozenset({"metron"})


def test_explicit_id_parses() -> None:
    cli = Namespace(explicit_ids=["metron:42"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.explicit_ids == {"metron": 42}


def test_explicit_id_unknown_source_errors() -> None:
    cli = Namespace(explicit_ids=["nope:1"])
    with pytest.raises(ValueError, match="unknown source"):
        get_config(Namespace(comicbox=cli))


def test_explicit_id_non_numeric_errors() -> None:
    cli = Namespace(explicit_ids=["metron:abc"])
    with pytest.raises(ValueError, match="non-numeric"):
        get_config(Namespace(comicbox=cli))


def test_no_cache_overrides_cache_enabled() -> None:
    cli = Namespace(online_sources=["all"], no_cache=True)
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.cache_enabled is False


def test_refresh_cache_flag_runtime_only() -> None:
    cli = Namespace(online_sources=["all"], refresh_cache=True)
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.refresh_cache is True


def test_confidence_threshold_cli_override() -> None:
    cli = Namespace(online_sources=["all"], confidence_threshold=0.95)
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.confidence_threshold == 0.95


def test_explicit_id_implicitly_activates_online() -> None:
    """`--id comicvine:42` alone should enable online for ComicVine."""
    cli = Namespace(explicit_ids=["comicvine:42"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.enabled is True
    assert cfg.online.selected_sources == frozenset({"comicvine"})
    assert cfg.online.explicit_ids == {"comicvine": 42}


def test_explicit_id_union_with_online_filter() -> None:
    """--id comicvine:42 --online metron → both sources active."""
    cli = Namespace(
        online_sources=["metron"],
        explicit_ids=["comicvine:42"],
    )
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.enabled is True
    assert cfg.online.selected_sources == frozenset({"metron", "comicvine"})


def test_explicit_id_with_online_all_keeps_all() -> None:
    """--id comicvine:42 --online all keeps `all` (None) sentinel."""
    cli = Namespace(
        online_sources=["all"],
        explicit_ids=["comicvine:42"],
    )
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.enabled is True
    assert cfg.online.selected_sources is None


def test_explicit_id_comicvine_accepts_4000_prefix() -> None:
    """--id comicvine:4000-12345 normalizes to bare integer 12345."""
    cli = Namespace(explicit_ids=["comicvine:4000-12345"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.explicit_ids == {"comicvine": 12345}


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
