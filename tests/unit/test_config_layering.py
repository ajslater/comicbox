"""Layering / priority tests for get_config()."""

from argparse import Namespace

from comicbox.config import get_config


def test_default_no_args() -> None:
    """No args => the bundled config_default.yaml drives the result."""
    cfg = get_config()
    assert cfg.compute_pages is False  # default


def test_namespace_overrides_default() -> None:
    """Namespace args override config_default.yaml."""
    cfg = get_config(Namespace(comicbox=Namespace(compute_pages=True)))
    assert cfg.compute_pages is True


def test_mapping_overrides_default() -> None:
    """
    Mapping args must land at top priority — same as Namespace.

    Regression: read_config_sources used to call config.add() for the
    Mapping branch, which puts the source at the BOTTOM of the priority
    stack — below config_default.yaml — so user overrides were silently
    ignored. Must use config.set().
    """
    cfg = get_config({"comicbox": {"compute_pages": True}})
    assert cfg.compute_pages is True


def test_mapping_and_namespace_agree() -> None:
    """Same overrides via Mapping and Namespace produce equivalent settings."""
    via_map = get_config({"comicbox": {"compute_pages": True, "dry_run": True}})
    via_ns = get_config(Namespace(comicbox=Namespace(compute_pages=True, dry_run=True)))
    assert via_map.compute_pages == via_ns.compute_pages is True
    assert via_map.dry_run == via_ns.dry_run is True
