"""A lifetime in the config may be a number, as the warning suggests."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from loguru import logger

from comicbox.config import get_config

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def warnings() -> Iterator[list[str]]:
    messages: list[str] = []
    handler = logger.add(
        lambda message: messages.append(message.rstrip("\n")),
        level="WARNING",
        format="{message}",
    )
    yield messages
    logger.remove(handler)


def _config(tmp_path: Path, body: str) -> None:
    """Write the user config; conftest points COMICBOXDIR at tmp_path."""
    (tmp_path / "config.yaml").write_text(f"comicbox:\n{body}")


@pytest.mark.parametrize(
    ("value", "lifetime"),
    [("0", timedelta(0)), ("3600", timedelta(hours=1)), ("'4h'", timedelta(hours=4))],
)
def test_the_cache_ttl_may_be_a_number(
    tmp_path: Path, value: str, lifetime: timedelta
) -> None:
    """A bare 0 was "must be a string", and the whole config was refused."""
    _config(tmp_path, f"  online:\n    cache:\n      ttl: {value}\n")
    assert get_config().online.cache.ttl == lifetime


def test_the_catalog_ttl_may_be_a_number(tmp_path: Path) -> None:
    _config(tmp_path, "  readinglists:\n    catalog_ttl: 0\n    catalog_ref: dev\n")
    settings = get_config().readinglists
    assert settings.catalog_ttl == timedelta(0)
    assert settings.catalog_ref == "dev"


@pytest.mark.parametrize("value", ["-5", "true"])
def test_a_number_that_is_no_lifetime_warns_and_defaults(
    tmp_path: Path, warnings: list[str], value: str
) -> None:
    _config(tmp_path, f"  online:\n    cache:\n      ttl: {value}\n")
    assert get_config().online.cache.ttl == timedelta(days=7)
    assert any(message.startswith("unparsable cache.ttl") for message in warnings)


_FORMS = "(use forms like 7d, 24h, 60m, or 0)"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "  online:\n    cache:\n      ttl: soon\n",
            f"unparsable cache.ttl 'soon', defaulting to 7d {_FORMS}",
        ),
        (
            "  readinglists:\n    catalog_ttl: soon\n",
            f"unparsable readinglists.catalog_ttl 'soon', defaulting to 4h {_FORMS}",
        ),
    ],
    ids=["cache", "catalog"],
)
def test_the_fallback_warning_names_the_default_as_the_config_does(
    tmp_path: Path, warnings: list[str], body: str, message: str
) -> None:
    """It said "defaulting to 1w" after the lifetime parser was shared."""
    _config(tmp_path, body)
    get_config()
    assert message in warnings
