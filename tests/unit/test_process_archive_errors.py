"""
A backend that can't import must not abort a batch read.

``_collect_result`` names its expected errors with ``except
_archive_errors()``, which imports py7zr and rarfile lazily -- inside the
``except`` clause. With either broken, any archive error at all (a corrupt
CBZ) was replaced by an ImportError that escaped and ended the batch.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import BadZipFile

import pytest
from loguru import logger

from comicbox.process import _archive_errors, _collect_result

if TYPE_CHECKING:
    from collections.abc import Iterator


class _CorruptFuture:
    """A completed future whose file turned out to be a corrupt zip."""

    def result(self) -> None:
        reason = "File is not a zip file"
        raise BadZipFile(reason)


@pytest.fixture
def _uncached_errors() -> Iterator[None]:
    _archive_errors.cache_clear()
    yield
    _archive_errors.cache_clear()


@pytest.mark.usefixtures("_uncached_errors")
@pytest.mark.parametrize("module", ["py7zr.exceptions", "rarfile"])
def test_broken_backend_does_not_mask_archive_error(
    monkeypatch: pytest.MonkeyPatch, module: str
) -> None:
    monkeypatch.setitem(sys.modules, module, None)
    _result, exc, pool_broken = _collect_result(
        _CorruptFuture(), Path("corrupt.cbz"), logger
    )
    assert isinstance(exc, BadZipFile)
    assert not pool_broken
