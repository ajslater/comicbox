"""
A plain name or number loads as its object (B16).

v2.0.0 made series, volume, publisher and imprint objects and said, in its
NEWS, that "named or numbered types ... may also be parse[d] by their simple
name instead of requiring a complex object". ``SimpleNamedNestedField``'s
branch for that never ran: the nested schema read a plain value as ``{}``
without an error, so the union never tried the plain field, and the value
was dropped with no log line.
"""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import pytest
from loguru import logger

from comicbox.box import Comicbox
from comicbox.formats.comicbox.schema.yaml import ComicboxYamlSchema
from comicbox.write import write_metadata
from tests.const import TEST_FILES_DIR

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_PLAIN_YAML = """\
comicbox:
  series: Civil War
  volume: 2006
  publisher: Marvel
  imprint: Icon
"""
_LOADED = {
    "series": {"name": "Civil War"},
    "volume": {"number": 2006},
    "publisher": {"name": "Marvel"},
    "imprint": {"name": "Icon"},
}


def _load(text: str) -> dict[str, Any]:
    loaded = ComicboxYamlSchema(path="comic.cbz").loads(text)
    assert isinstance(loaded, Mapping)
    return dict(loaded["comicbox"])


def _tags(path: Path) -> dict[str, Any]:
    with Comicbox(path) as box:
        return dict(box.to_dict()["comicbox"])


def _comic(path: Path, name: str, data: str) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("page-0.jpg", b"not-a-real-jpeg")
        archive.writestr(name, data)
    return path


def test_a_comics_yaml_loads_plain_names_and_numbers(tmp_path: Path) -> None:
    path = _comic(tmp_path / "comic.cbz", "comicbox.yaml", _PLAIN_YAML)

    tags = _tags(path)

    assert {key: tags.get(key) for key in _LOADED} == _LOADED


def test_a_number_written_as_a_string_loads(tmp_path: Path) -> None:
    data = json.dumps({"comicbox": {"volume": "2006", "series": "Civil War"}})
    path = _comic(tmp_path / "comic.cbz", "comicbox.json", data)

    tags = _tags(path)

    assert tags["volume"] == {"number": 2006}
    assert tags["series"] == {"name": "Civil War"}


def test_a_library_patch_with_plain_names_is_written(tmp_path: Path) -> None:
    """The whole patch failed to load, and the write wrote none of it."""
    path = tmp_path / "comic.cbz"
    shutil.copy(TEST_FILES_DIR / "empty.cbz", path)
    patch = {"series": "Civil War", "volume": 2006, "imprint": "Icon"}

    result = write_metadata(path, patch, formats=["COMIC_INFO"])

    assert result.written, result.error
    tags = _tags(path)
    assert tags["series"]["name"] == "Civil War"
    assert tags["volume"] == {"number": 2006}
    assert tags["imprint"] == {"name": "Icon"}


def test_the_object_forms_load_as_before() -> None:
    text = "comicbox: {series: {name: X, start_year: 2006}, volume: {number: 3}}"

    assert _load(text) == {
        "series": {"name": "X", "start_year": 2006},
        "volume": {"number": 3},
    }


@pytest.fixture
def warnings(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    handler_id = logger.add(caplog.handler, level=0)
    caplog.set_level(logging.WARNING)
    try:
        yield caplog
    finally:
        logger.remove(handler_id)


def test_an_invalid_plain_value_is_logged_as_dropped(
    warnings: pytest.LogCaptureFixture,
) -> None:
    loaded = _load("comicbox: {volume: abc, series: [a, b], publisher: Marvel}")

    assert loaded == {"publisher": {"name": "Marvel"}}
    messages = "\n".join(record.getMessage() for record in warnings.records)
    assert "Dropped invalid metadata: volume='abc'" in messages
    assert "Dropped invalid metadata: series=['a', 'b']" in messages
