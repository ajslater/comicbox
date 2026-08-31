"""Online credentials / settings resolution tests (v4)."""

from argparse import Namespace

import pytest

from comicbox.config import get_config
from comicbox.config.settings import CacheMode, Effort, MatchMode, Prompts
from comicbox.formats.base.online.cli_overrides import CliOverrides
from comicbox.formats.base.online.credentials import resolve_credentials

# ------------------------------------------------------------- CLI overrides


def test_cli_overrides_from_auth_list_parses_field_value_pairs() -> None:
    overrides = CliOverrides.from_auth_list(
        [
            "comicvine:key=abc",
            "metron:user=bob",
            "metron:pass=secret",
            "metron:key=token123",
            "metron:url=https://metron.local",
        ]
    )
    assert overrides.per_source["comicvine"]["key"] == "abc"
    assert overrides.per_source["metron"]["user"] == "bob"
    assert overrides.per_source["metron"]["pass"] == "secret"
    assert overrides.per_source["metron"]["key"] == "token123"
    assert overrides.per_source["metron"]["url"] == "https://metron.local"


def test_cli_overrides_unknown_source_errors() -> None:
    with pytest.raises(ValueError, match="unknown source"):
        CliOverrides.from_auth_list(["nosuch:key=xyz"])


def test_cli_overrides_unknown_field_errors() -> None:
    with pytest.raises(ValueError, match="unknown field"):
        CliOverrides.from_auth_list(["metron:badfield=xyz"])


def test_cli_overrides_bad_syntax_errors() -> None:
    with pytest.raises(ValueError, match=r"<source>:<token>"):
        CliOverrides.from_auth_list(["nodelimiter"])


def test_cli_overrides_bare_value_is_the_api_token() -> None:
    """`<source>:<token>` needs no field name — the token is the common case."""
    overrides = CliOverrides.from_auth_list(["metron:token123", "comicvine:ABCD1234"])
    assert overrides.per_source["metron"]["key"] == "token123"
    assert overrides.per_source["comicvine"]["key"] == "ABCD1234"


def test_cli_overrides_bare_and_named_forms_agree() -> None:
    """The undocumented `key=` form is still accepted and means the same thing."""
    bare = CliOverrides.from_auth_list(["metron:token123"])
    named = CliOverrides.from_auth_list(["metron:key=token123"])
    assert bare.per_source == named.per_source


def test_cli_overrides_bare_token_alongside_named_fields() -> None:
    overrides = CliOverrides.from_auth_list(
        ["metron:token123", "metron:url=https://metron.local"]
    )
    assert overrides.per_source["metron"] == {
        "key": "token123",
        "url": "https://metron.local",
    }


def test_cli_overrides_empty_value_errors() -> None:
    """A bare `<source>:` is a typo, not a request to blank the token."""
    with pytest.raises(ValueError, match="empty value"):
        CliOverrides.from_auth_list(["metron:"])


# ----------------------------------------------- credential resolution chain


def test_resolve_credentials_cli_beats_config() -> None:
    """
    CLI wins per field; everything else comes from the config view.

    Env vars reach this through that view rather than a separate layer —
    ``test_config_env_tree`` covers that route end to end.
    """
    creds = resolve_credentials(
        config_creds={
            "metron": {
                "user": "config_user",
                "pass": "config_pw",
                "url": "config_url",
            }
        },
        cli_overrides=CliOverrides.from_auth_list(["metron:user=cli_user"]),
        use_keyring=False,
    )
    assert creds["metron"].user == "cli_user"  # CLI wins
    assert creds["metron"].password == "config_pw"  # config where CLI is silent
    assert creds["metron"].url == "config_url"


def test_resolve_credentials_metron_token_follows_the_chain() -> None:
    """Metron's API token resolves through the same CLI > config chain."""
    config_creds = {"metron": {"key": "config_token"}}
    creds = resolve_credentials(
        config_creds=config_creds,
        cli_overrides=CliOverrides.from_auth_list(["metron:key=cli_token"]),
        use_keyring=False,
    )
    assert creds["metron"].key == "cli_token"  # CLI wins
    creds = resolve_credentials(config_creds=config_creds, use_keyring=False)
    assert creds["metron"].key == "config_token"


def test_resolve_credentials_returns_all_sources() -> None:
    creds = resolve_credentials(config_creds={}, use_keyring=False)
    assert set(creds.keys()) == {"metron", "comicvine"}
    assert creds["metron"].user is None
    assert creds["comicvine"].key is None


def test_credentials_repr_redacts_secrets() -> None:
    """repr() must never expose password or api key — log-safety invariant."""
    from comicbox.config.settings import OnlineSourceCredentials

    creds = OnlineSourceCredentials(
        user="ajslater",
        password="hunter2",
        key="sk_live_abc123def456",
        url="https://example.com",
    )
    rendered = repr(creds)
    assert "hunter2" not in rendered
    assert "sk_live_abc123def456" not in rendered
    assert "***" in rendered
    # Non-secret fields stay visible for debugging.
    assert "ajslater" in rendered
    assert "https://example.com" in rendered


def test_credentials_repr_shows_none_for_unset_secrets() -> None:
    """An unset secret renders as None, distinct from a redacted '***'."""
    from comicbox.config.settings import OnlineSourceCredentials

    creds = OnlineSourceCredentials(user="ajslater")
    rendered = repr(creds)
    assert "password=None" in rendered
    assert "key=None" in rendered
    assert "***" not in rendered


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
    assert cfg.online.lookup.sources == ("metron",)


def test_online_sources_cli_order_is_preserved() -> None:
    """--online list order is run priority; comicvine-first survives."""
    cli = Namespace(online_sources=["comicvine", "metron"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.sources == ("comicvine", "metron")


def test_online_sources_env_sets_durable_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sources env var orders sources without enabling lookups."""
    monkeypatch.setenv("COMICBOX_ONLINE__LOOKUP__SOURCES", "comicvine, metron")
    cfg = get_config()
    assert cfg.online.lookup.sources == ("comicvine", "metron")
    assert cfg.online.lookup.enabled is False


def test_online_cli_all_overrides_durable_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--online all means every configured source, not the env/file list."""
    monkeypatch.setenv("COMICBOX_ONLINE__LOOKUP__SOURCES", "comicvine")
    cli = Namespace(online_sources=["all"])
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.enabled is True
    assert cfg.online.lookup.sources is None


def test_online_sources_unknown_names_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    An unknown source name aborts instead of being dropped.

    Dropping was silent in both directions: a mixed list quietly
    narrowed (asking for comicvine + gcd got only comicvine), and an
    all-unknown list left the empty ALL_SOURCES sentinel behind, which
    widened the run to every source. See
    tests/unit/test_config_online_sources.py.
    """
    monkeypatch.setenv("COMICBOX_ONLINE__LOOKUP__SOURCES", "comicvine,grand_comics_db")
    with pytest.raises(ValueError, match="unknown source"):
        get_config()


def test_first_wins_defaults_true() -> None:
    cfg = get_config()
    assert cfg.online.lookup.first_wins is True


def test_all_sources_flag_inverts_first_wins() -> None:
    cli = Namespace(online_sources=["all"], all_sources=True)
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.first_wins is False


def test_first_wins_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMICBOX_ONLINE__LOOKUP__FIRST_WINS", "false")
    cfg = get_config()
    assert cfg.online.lookup.first_wins is False


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
    assert cfg.online.lookup.sources == ("comicvine",)
    assert cfg.online.lookup.ids == {"comicvine": 42}


def test_explicit_id_union_with_online_filter() -> None:
    """--id comicvine:42 --online metron → both sources active."""
    cli = Namespace(
        online_sources=["metron"],
        explicit_ids=["comicvine:42"],
    )
    cfg = get_config(Namespace(comicbox=cli))
    assert cfg.online.lookup.enabled is True
    assert cfg.online.lookup.sources == ("metron", "comicvine")


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
