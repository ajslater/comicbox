"""
Set-like config fields accept set / frozenset / tuple / list, but not Mapping.

The five fields `read`, `write`, `export`, `delete_keys`, `read_ignore` and
the special `print` field all hold a frozenset post-compute. The template
accepts any non-mapping container as input; `_build_settings` normalizes
into the right immutable type.
"""

from argparse import Namespace

import pytest

from comicbox.config import get_config
from comicbox.formats import MetadataFormats


@pytest.mark.parametrize(
    "value",
    [
        ["cix"],
        ("cix",),
        {"cix"},
        frozenset({"cix"}),
    ],
    ids=["list", "tuple", "set", "frozenset"],
)
def test_read_write_export_accept_any_container(value: object) -> None:
    """read/write/export accept any non-mapping container of config keys."""
    cfg = get_config(
        Namespace(comicbox=Namespace(read=value, write=value, export=value))
    )
    assert cfg.read == frozenset({MetadataFormats.COMIC_INFO})
    assert cfg.write == frozenset({MetadataFormats.COMIC_INFO})
    assert cfg.export == frozenset({MetadataFormats.COMIC_INFO})


@pytest.mark.parametrize(
    "value",
    [
        ["notes", "tagger"],
        ("notes", "tagger"),
        {"notes", "tagger"},
        frozenset({"notes", "tagger"}),
    ],
    ids=["list", "tuple", "set", "frozenset"],
)
def test_delete_keys_accepts_any_container(value: object) -> None:
    """delete_keys accepts any non-mapping container of keypaths."""
    cfg = get_config(Namespace(comicbox=Namespace(delete_keys=value)))
    assert cfg.delete_keys == frozenset({"notes", "tagger"})


def test_read_rejects_mapping() -> None:
    """
    Dict iteration yields keys, which would silently accept dict input.

    Reject mapping explicitly so callers get a clear error rather than
    surprising "the keys became my read formats" behavior.
    """
    with pytest.raises(Exception, match="non-mapping"):
        get_config(Namespace(comicbox=Namespace(read={"cix": True})))


@pytest.mark.parametrize(
    "value",
    [
        "snmcp",
        ["s", "n", "m", "c", "p"],
        ("s", "n", "m", "c", "p"),
        {"s", "n", "m", "c", "p"},
        frozenset({"s", "n", "m", "c", "p"}),
    ],
    ids=["str", "list", "tuple", "set", "frozenset"],
)
def test_print_accepts_str_or_container(value: object) -> None:
    """Print accepts a phase-char string OR any iterable of phase chars."""
    from comicbox.print import PrintPhases

    cfg = get_config(Namespace(comicbox=Namespace(print=value)))
    assert cfg.print == frozenset(
        {
            PrintPhases.SOURCE,
            PrintPhases.NORMALIZED,
            PrintPhases.MERGED,
            PrintPhases.COMPUTED,
            PrintPhases.METADATA,
        }
    )
