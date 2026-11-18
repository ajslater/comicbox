"""
The Metron cover-hash search module on its own.

`cover_search` stands in for a mokkari method, so it is driven through a
real mokkari Session over a fake transport, and the query string checked
is the one mokkari sends. It has to stay liftable into mokkari, so one
test fails on any import outside the standard library and mokkari.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

import mokkari
import pytest
from mokkari.exceptions import ApiError

from comicbox.formats.metron_api import cover_search
from comicbox.formats.metron_api.cover_search import (
    DEFAULT_COVER_HASH_DISTANCE,
    MAX_COVER_HASH_DISTANCE,
    hamming_distance,
    issues_by_cover_hash,
)
from tests.util.metron_transport import Reply, install, issue_page, issue_row

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mokkari.session import Session

_HASH = "95977c2b3129c2d3"


def _flip(bits: int) -> str:
    """Make `_HASH` with its lowest ``bits`` bits flipped."""
    return f"{int(_HASH, 16) ^ ((1 << bits) - 1):016x}"


def _row(issue_id: int, cover_hash: str | None = None) -> dict[str, Any]:
    """Build an issue row; without a hash, mokkari's default "" applies."""
    row = issue_row(issue_id)
    if cover_hash is not None:
        row["cover_hash"] = cover_hash
    return row


@pytest.fixture
def session() -> Iterator[Session]:
    """Yield a plain mokkari Session with no response cache."""
    session = mokkari.api("t")
    yield session
    session.close()


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


def test_one_issues_list_request_carries_both_cover_filters(session: Session) -> None:
    adapter = install(session, [Reply(issue_page([]))])

    issues_by_cover_hash(session, _HASH, MAX_COVER_HASH_DISTANCE)

    assert len(adapter.urls) == 1
    assert urlsplit(adapter.urls[0]).path.endswith("/issue/")
    assert _query(adapter.urls[0]) == {
        "cover_hash_near": [_HASH],
        "cover_hash_max_distance": ["20"],
    }


def test_rows_keep_metron_order_each_with_its_distance(session: Session) -> None:
    """It annotates and does not filter: a row past the limit stays."""
    rows = [_row(1, _flip(21)), _row(2, _HASH), _row(3, _flip(20)), _row(4, _flip(4))]
    install(session, [Reply(issue_page(rows))])

    matches = issues_by_cover_hash(session, _HASH, MAX_COVER_HASH_DISTANCE)

    assert [match.issue.id for match in matches] == [1, 2, 3, 4]
    assert [match.distance for match in matches] == [21, 0, 20, 4]


def test_a_missing_or_malformed_row_hash_has_no_distance(session: Session) -> None:
    install(session, [Reply(issue_page([_row(1), _row(2, "not-a-hash")]))])

    matches = issues_by_cover_hash(session, _HASH)

    assert [match.distance for match in matches] == [None, None]


def test_without_a_max_distance_the_server_default_applies(session: Session) -> None:
    adapter = install(session, [Reply(issue_page([]))])

    issues_by_cover_hash(session, _HASH)

    assert "cover_hash_max_distance" not in _query(adapter.urls[0])


def test_the_distance_limits_are_metrons() -> None:
    assert DEFAULT_COVER_HASH_DISTANCE == 10
    assert MAX_COVER_HASH_DISTANCE == 20


def test_caller_params_pass_through_untouched(session: Session) -> None:
    adapter = install(session, [Reply(issue_page([]))])
    params: dict[str, str | int] = {"number": "10", "series_id": 77}

    issues_by_cover_hash(session, _HASH, 20, params)

    assert _query(adapter.urls[0]) == {
        "number": ["10"],
        "series_id": ["77"],
        "cover_hash_max_distance": ["20"],
        "cover_hash_near": [_HASH],
    }
    # The cover filters are added to a copy.
    assert params == {"number": "10", "series_id": 77}


def test_a_bad_value_is_the_servers_to_refuse(session: Session) -> None:
    """Nothing is validated here: Metron's 400 is mokkari's ApiError."""
    adapter = install(session, [Reply({"detail": "bad hash"}, status_code=400)])

    with pytest.raises(ApiError):
        issues_by_cover_hash(session, "not-a-hash", 99)

    assert len(adapter.urls) == 1
    assert _query(adapter.urls[0])["cover_hash_near"] == ["not-a-hash"]


@pytest.mark.parametrize(
    ("a", "b", "bits"),
    [
        (_HASH, _HASH, 0),
        (_HASH, _flip(4), 4),
        (_HASH, _flip(64), 64),
        (_HASH, _HASH.upper(), 0),
        (_HASH, "", None),
        ("", _HASH, None),
        (_HASH, "not-a-hash-at-al", None),
        (_HASH, _HASH[:15], None),
        (_HASH, _HASH + "0", None),
        # int() would take these; a pHash is exactly 16 hex digits.
        (_HASH, "0x" + _HASH[:14], None),
        (_HASH, "+" + _HASH[:15], None),
        (_HASH, "_".join((_HASH[:8], _HASH[9:])), None),
    ],
)
def test_hamming_distance(a: str, b: str, bits: int | None) -> None:
    assert hamming_distance(a, b) == bits


def test_the_module_imports_only_the_stdlib_and_mokkari() -> None:
    """Anything else would tie it to comicbox and stop it being lifted."""
    path = Path(cover_search.__file__)
    tree = ast.parse(path.read_text(), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import ties it to its package"
            modules.add(node.module or "")
    packages = {module.split(".")[0] for module in modules}

    assert "mokkari" in packages
    assert {
        package
        for package in packages
        if package != "mokkari" and package not in sys.stdlib_module_names
    } == set()
