"""merge_order resolution tests."""

import pytest

from comicbox.config import get_config
from comicbox.formats.sources import MetadataSources


def test_merge_order_default_is_none() -> None:
    """Without configuration the dataclass field is None (use enum order)."""
    cfg = get_config()
    assert cfg.merge_order is None


def test_merge_order_explicit_list_resolves_to_enum_members() -> None:
    cfg = get_config(
        {
            "comicbox": {
                "merge_order": [
                    "ARCHIVE_FILE",
                    "METRON_API",
                    "COMICVINE_API",
                    "CLI",
                ],
            }
        }
    )
    assert cfg.merge_order is not None
    assert cfg.merge_order[0] is MetadataSources.ARCHIVE_FILE
    assert cfg.merge_order[1] is MetadataSources.METRON_API
    assert cfg.merge_order[2] is MetadataSources.COMICVINE_API
    assert cfg.merge_order[3] is MetadataSources.CLI


def test_merge_order_appends_missing_members() -> None:
    """Members absent from a user list get appended at the end."""
    cfg = get_config({"comicbox": {"merge_order": ["ARCHIVE_FILE", "CLI"]}})
    assert cfg.merge_order is not None
    # The two we listed first.
    assert cfg.merge_order[0] is MetadataSources.ARCHIVE_FILE
    assert cfg.merge_order[1] is MetadataSources.CLI
    # All MetadataSources members appear exactly once.
    assert set(cfg.merge_order) == set(MetadataSources)
    assert len(cfg.merge_order) == len(list(MetadataSources))


def test_merge_order_duplicate_raises() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        get_config({"comicbox": {"merge_order": ["ARCHIVE_FILE", "ARCHIVE_FILE"]}})


def test_merge_order_unknown_source_skipped() -> None:
    """Unknown source names are warn-and-skip, not fatal."""
    cfg = get_config({"comicbox": {"merge_order": ["ARCHIVE_FILE", "MADE_UP_SOURCE"]}})
    assert cfg.merge_order is not None
    assert MetadataSources.ARCHIVE_FILE in cfg.merge_order
    # Missing members appended at the end so no source is dropped.
    assert set(cfg.merge_order) == set(MetadataSources)


def test_metadata_sources_enum_position() -> None:
    """Online sources sit between ARCHIVE_FILE and IMPORT_FILE per Phase 3."""
    members = list(MetadataSources)
    archive_idx = members.index(MetadataSources.ARCHIVE_FILE)
    metron_idx = members.index(MetadataSources.METRON_API)
    comicvine_idx = members.index(MetadataSources.COMICVINE_API)
    import_idx = members.index(MetadataSources.IMPORT_FILE)

    assert archive_idx < metron_idx < comicvine_idx < import_idx


def test_legacy_nested_removed() -> None:
    """LEGACY_NESTED is gone."""
    assert "LEGACY_NESTED" not in MetadataSources.__members__
