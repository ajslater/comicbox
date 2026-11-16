"""
A deprecated format key still works, says so, and is not advertised.

cbl for ComicBookInfo goes in comicbox 6.0: CBL is a ComicRack reading
list, which ``comicbox rl`` reads and writes as ``cbl``.
"""

from argparse import Namespace

from loguru import logger

from comicbox.cli.epilog import _get_help_format_table
from comicbox.config import get_config
from comicbox.config.formats import DEPRECATED_FORMAT_KEYS
from comicbox.config.settings import ComicboxSettings
from comicbox.formats import MetadataFormats
from comicbox.readinglists.cli.comics import _FORMAT_KEYS


def _config_and_warnings(key: str) -> tuple[ComicboxSettings, list[str]]:
    messages: list[str] = []
    handler = logger.add(messages.append, level="WARNING", format="{message}")
    try:
        config = get_config(
            Namespace(
                comicbox=Namespace(
                    read=Namespace(formats=[key]),
                    write=Namespace(formats=[key]),
                    convert=Namespace(export_formats=[key]),
                )
            )
        )
    finally:
        logger.remove(handler)
    return config, messages


def test_cbl_still_means_comic_book_info() -> None:
    config, messages = _config_and_warnings("cbl")
    expected = frozenset({MetadataFormats.COMIC_BOOK_INFO})
    assert config.read.formats == expected
    assert config.write.formats == expected
    assert config.convert.export_formats == expected
    deprecations = [message for message in messages if "deprecated" in message]
    # One per action that named it, each naming the key to use.
    assert len(deprecations) == 3
    assert all("'cbi'" in message and "6.0" in message for message in deprecations)


def test_cbi_does_not_warn() -> None:
    _, messages = _config_and_warnings("cbi")
    assert not [message for message in messages if "deprecated" in message]


def test_help_table_leaves_deprecated_keys_out() -> None:
    table = _get_help_format_table()
    (keys_column,) = (column for column in table.columns if column.header == "Keys")
    listed = {key for cell in keys_column.cells for key in str(cell).split(", ")}
    assert "cbi" in listed
    assert not listed & DEPRECATED_FORMAT_KEYS.keys()


def test_write_arcs_takes_no_deprecated_key() -> None:
    """In comicbox rl, cbl is a reading list, never ComicBookInfo."""
    assert "cbi" in _FORMAT_KEYS
    assert not _FORMAT_KEYS.keys() & DEPRECATED_FORMAT_KEYS.keys()
