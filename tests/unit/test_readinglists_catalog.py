"""
The DieselTech catalog, through httpx.MockTransport.

Every path here is made up in the shape of the real tree's; no list file
or listing of the repository is copied into the suite.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlsplit

import httpx
import pytest

from comicbox.config.online.settings import CacheMode
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.readinglists import (
    CatalogEntry,
    ReadingListFetchError,
    ReadingListSession,
)
from comicbox.readinglists.sources.catalog import curator
from tests.const import TEST_FILES_DIR

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from pathlib import Path

_CBL = (TEST_FILES_DIR / "readinglists" / "cbl" / "startyear-source.cbl").read_bytes()
_API = "https://api.github.com/repos/DieselTech/CBL-ReadingLists/git/trees/main"
_RAW = "https://raw.githubusercontent.com/DieselTech/CBL-ReadingLists/main/"
_EVENT = "Marvel/Events/Marvel Guides/[Marvel] [2006] Example Event (MG).cbl"
_RENAMED = "Marvel/Events/Marvel Guides/[Marvel] [2006-2007] Example Event (MG).cbl"
_PLAIN = "Other/Example Publisher/Example Series.cbl"


def _blob_sha(data: bytes) -> str:
    """Hash as git does, independently of the code under test."""
    return hashlib.sha1(
        b"blob " + str(len(data)).encode() + b"\0" + data, usedforsecurity=False
    ).hexdigest()


_SHA = _blob_sha(_CBL)


def _tree(*paths: str, truncated: bool = False) -> dict[str, Any]:
    """Build a recursive git tree holding ``paths``, all with the fixture's sha."""
    items: list[dict[str, Any]] = [
        {"path": "Marvel", "type": "tree", "sha": "t1"},
        {"path": "README.md", "type": "blob", "sha": "r1", "size": 10},
    ]
    items += [
        {"path": path, "type": "blob", "sha": _SHA, "size": len(_CBL)} for path in paths
    ]
    return {"sha": "root", "tree": items, "truncated": truncated}


class _GitHub:
    """A fake api.github.com and raw.githubusercontent.com."""

    def __init__(self, *paths: str, etag: str = '"v1"') -> None:
        self.tree = _tree(*paths)
        self.raw: dict[str, bytes] = dict.fromkeys(paths, _CBL)
        self.etag = etag
        self.requests: list[httpx.Request] = []
        self.api_headers: Mapping[str, str] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = request.url
        if url.host == "api.github.com":
            if request.headers.get("If-None-Match") == self.etag:
                return httpx.Response(304, headers={"ETag": self.etag})
            return httpx.Response(
                200,
                content=json.dumps(self.tree).encode(),
                headers={"ETag": self.etag, **self.api_headers},
            )
        path = unquote(url.path).split("/", 4)[-1]
        if (data := self.raw.get(path)) is not None:
            return httpx.Response(200, content=data)
        return httpx.Response(404)

    @property
    def urls(self) -> list[str]:
        return [str(request.url) for request in self.requests]


def _session(github: Callable[[httpx.Request], httpx.Response], **knobs: Any):
    """Build a session on the fake GitHub, with ``readinglists`` knobs set."""
    session = ReadingListSession()
    settings = session.settings
    online = settings.online
    mode = knobs.pop("cache_mode", None)
    if mode is not None:
        online = replace(online, cache=replace(online.cache, mode=mode))
    session._settings = replace(
        settings,
        online=online,
        readinglists=replace(settings.readinglists, **knobs),
    )
    session._transport = httpx.MockTransport(github)
    return session


@pytest.fixture
def github() -> _GitHub:
    return _GitHub(_EVENT, _PLAIN)


@pytest.fixture
def session(github: _GitHub) -> Iterator[ReadingListSession]:
    with _session(github) as session:
        yield session


def _cache_files(session: ReadingListSession) -> list[Path]:
    from comicbox.formats.base.online.sources.base import resolve_cache_dir

    return sorted(
        resolve_cache_dir(session.settings.online.cache.dir).glob(
            "readinglists_catalog_*.json"
        )
    )


# ----------------------------------------------------------------- index


def test_the_index_is_one_tree_call(
    session: ReadingListSession, github: _GitHub
) -> None:
    catalog = session.catalog()

    assert github.urls == [f"{_API}?recursive=1"]
    (request,) = github.requests
    assert request.headers["Accept"] == "application/vnd.github+json"
    assert request.headers["User-Agent"].startswith("comicbox/")
    assert [entry.path for entry in catalog.entries] == [_EVENT, _PLAIN]
    assert catalog.entries[0] == CatalogEntry(
        path=_EVENT,
        sha=_SHA,
        size=len(_CBL),
        publisher="Marvel",
        category="Events",
        curator="mg",
    )
    assert catalog.entries[1].curator is None
    assert catalog.etag == '"v1"'


def test_within_the_lifetime_no_request_is_made(github: _GitHub) -> None:
    with _session(github) as first:
        first.catalog()
    with _session(github) as second:
        assert [entry.path for entry in second.catalog().entries] == [_EVENT, _PLAIN]
        assert len(github.requests) == 1

        second.catalog(refresh=True)

    assert len(github.requests) == 2
    assert github.requests[1].headers["If-None-Match"] == '"v1"'


def test_a_304_keeps_the_cached_index(github: _GitHub) -> None:
    with _session(github) as first:
        before = first.catalog()
    github.tree = _tree()  # Would be empty, were it sent again.
    with _session(github, catalog_ttl=timedelta(0)) as second:
        after = second.catalog()

    assert [request.url.host for request in github.requests] == ["api.github.com"] * 2
    assert after.entries == before.entries
    assert after.fetched > before.fetched


def test_a_changed_tree_replaces_the_index(github: _GitHub) -> None:
    with _session(github) as first:
        first.catalog()
    github.tree, github.etag = _tree(_PLAIN), '"v2"'
    with _session(github, catalog_ttl=timedelta(0)) as second:
        catalog = second.catalog()

    assert [entry.path for entry in catalog.entries] == [_PLAIN]
    assert catalog.etag == '"v2"'


def test_with_the_cache_off_nothing_is_written(github: _GitHub) -> None:
    with _session(github, cache_mode=CacheMode.OFF) as session:
        session.catalog()
        session.catalog()

        assert _cache_files(session) == []
    assert len(github.requests) == 2


def test_cache_mode_refresh_revalidates(github: _GitHub) -> None:
    with _session(github) as first:
        first.catalog()
    with _session(github, cache_mode=CacheMode.REFRESH) as second:
        second.catalog()

    assert github.requests[1].headers["If-None-Match"] == '"v1"'


def test_an_unreadable_cache_is_fetched_again(github: _GitHub) -> None:
    with _session(github) as first:
        first.catalog()
        (cache_file,) = _cache_files(first)
    cache_file.write_text("{not json")
    with _session(github) as second:
        assert len(second.catalog().entries) == 2
    assert len(github.requests) == 2


def test_a_truncated_tree_fails(github: _GitHub, session: ReadingListSession) -> None:
    github.tree = _tree(_EVENT, truncated=True)

    with pytest.raises(ReadingListFetchError, match="truncated the tree"):
        session.catalog()
    assert _cache_files(session) == []


def test_a_custom_repository_and_ref(github: _GitHub) -> None:
    with _session(github, catalog_repo="someone/lists", catalog_ref="dev") as session:
        session.fetch_catalog(_EVENT)

    assert github.urls[0] == (
        "https://api.github.com/repos/someone/lists/git/trees/dev?recursive=1"
    )
    assert github.urls[1].startswith(
        "https://raw.githubusercontent.com/someone/lists/dev/"
    )


@pytest.mark.parametrize("repo", ["", "lists", "a/b/c", "https://github.com/a/b"])
def test_a_malformed_repository_is_refused_before_any_request(
    github: _GitHub, repo: str
) -> None:
    with (
        _session(github, catalog_repo=repo) as session,
        pytest.raises(ReadingListFetchError, match="owner/name"),
    ):
        session.catalog()
    assert github.requests == []


def test_an_unknown_ref_says_so(session: ReadingListSession) -> None:
    session._transport = httpx.MockTransport(lambda _request: httpx.Response(404))

    with pytest.raises(
        ReadingListFetchError, match=r"no repository .* with a ref main"
    ):
        session.catalog()


def test_a_spent_rate_limit_says_so(github: _GitHub) -> None:
    def refuse(_request: httpx.Request) -> httpx.Response:
        headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1900000000"}
        return httpx.Response(403, headers=headers)

    with (
        _session(refuse) as session,
        pytest.raises(ReadingListFetchError, match=r"rate limit .* It resets at"),
    ):
        session.catalog()


def test_a_cancelled_session_asks_nothing(
    session: ReadingListSession, github: _GitHub
) -> None:
    session.cancel()
    with pytest.raises(OnlineLookupAbortedError):
        session.catalog()
    with pytest.raises(OnlineLookupAbortedError):
        session.fetch_catalog(_EVENT)
    assert github.requests == []


# --------------------------------------------------------------- curator


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("Marvel/Events/CBRO/[Marvel] Example (WEB-CBRO).cbl", "cbro"),
        ("IDW/Characters/Example/[IDW] Example (CBRO).cbl", "cbro"),
        ("Marvel/Events/Marvel Guides/Example (MG).cbl", "mg"),
        ("Marvel/Events/LoCG/Example (LoCG).cbl", "locg"),
        ("Boom/Events/LOCG/[LOCG] Example.cbl", "locg"),
        ("Marvel/Events/Example (WEB-LOCG).cbl", "locg"),
        ("Marvel/Events/LoCG Community/Example (Marvel)(LoCG).cbl", "locg"),
        ("Marvel/Master Reading Order/CMRO/Core/Example Part 01.cbl", "cmro"),
        ("Marvel/Events/CBRO - With Events/Example.cbl", "cbro"),
        ("Marvel/Teams/X-Men/CBH X-Men Reading Order/Example.cbl", "cbh"),
        ("DC/Events/CBH/Example (CBH).cbl", "cbh"),
        ("Marvel/Events/Example (Comic Book Herald).cbl", "cbh"),
        ("Marvel/Events/CBT/Example (CBT).cbl", "cbt"),
        ("Vertigo/Characters/Example (HTLC).cbl", "htlc"),
        ("Marvel/Events/Official/Example (Official).cbl", "official"),
        ("Marvel/Teams/X-Men/Example Era One (UXRO).cbl", "uxro"),
        ("Image/Master Reading Order/Example (WEB-KCV).cbl", "kcv"),
        ("Marvel/Events/Community/Example (Community-Contributed).cbl", "community"),
        # The file's own mark wins over its folder's.
        ("Marvel/Events/CBRO/Example (MG).cbl", "mg"),
        # Era and edition labels are not curators.
        ("DC/Characters/Superman/Example (Post-Crisis).cbl", None),
        ("DC/Events/Example (New 52).cbl", None),
        ("Archie Comics/Example/Example (Archie)(someone).cbl", None),
        ("Other/Example.cbl", None),
        # A mark that is not the last group does not count.
        ("Marvel/Events/Example (WEB-CBRO) copy.cbl", None),
    ],
)
def test_the_curator_comes_from_the_name_or_a_folder(
    path: str, expected: str | None
) -> None:
    assert curator(path) == expected


# ---------------------------------------------------------------- search


def test_search_matches_every_word_of_the_query(session: ReadingListSession) -> None:
    assert [entry.path for entry in session.search_catalog("example event")] == [_EVENT]
    assert [entry.path for entry in session.search_catalog("EXAMPLE")] == [
        _EVENT,
        _PLAIN,
    ]
    assert session.search_catalog("crisis") == ()


# ----------------------------------------------------------------- fetch


def test_a_fetched_list_names_the_catalog_as_its_source(
    session: ReadingListSession,
) -> None:
    result = session.fetch_catalog(_EVENT)

    assert result.reading_list["name"] == "Civil War"
    assert result.reading_list["sources"] == [
        {
            "kind": "catalog",
            "key": _EVENT,
            "url": (
                f"{_RAW}Marvel/Events/Marvel%20Guides/"
                "%5BMarvel%5D%20%5B2006%5D%20Example%20Event%20%28MG%29.cbl"
            ),
            "revision": _SHA,
            # The catalog's curator replaces the file's own <Source>CBRO.
            "curator": "mg",
        }
    ]


def test_without_a_curator_the_file_keeps_its_own(
    session: ReadingListSession,
) -> None:
    result = session.fetch_catalog(_PLAIN)

    (source,) = result.reading_list["sources"]
    assert source["curator"] == "CBRO"


def test_a_renamed_path_is_found_by_its_sha(github: _GitHub) -> None:
    github = _GitHub(_RENAMED)
    with _session(github) as session:
        result = session.fetch_catalog(_EVENT, sha=_SHA)

    assert result.reading_list["sources"][0]["key"] == _RENAMED
    assert unquote(github.urls[-1]) == f"{_RAW}{_RENAMED}"


def test_an_index_from_before_a_rename_is_fetched_again(github: _GitHub) -> None:
    """The cached index still lists the old path, which no longer downloads."""
    with _session(github) as first:
        first.catalog()
    github.tree, github.etag = _tree(_RENAMED, _PLAIN), '"v2"'
    github.raw = {_RENAMED: _CBL, _PLAIN: _CBL}

    with _session(github) as second:
        result = second.fetch_catalog(_EVENT, sha=_SHA)

    assert result.reading_list["sources"][0]["key"] == _RENAMED
    hosts = [(r.url.host, r.headers.get("If-None-Match")) for r in github.requests]
    assert hosts == [
        ("api.github.com", None),
        ("raw.githubusercontent.com", None),
        ("api.github.com", '"v1"'),
        ("raw.githubusercontent.com", None),
    ]


def test_a_path_that_is_gone_without_a_sha_fails(github: _GitHub) -> None:
    with (
        _session(_GitHub(_RENAMED)) as session,
        pytest.raises(ReadingListFetchError, match="is not in the catalog of"),
    ):
        session.fetch_catalog(_EVENT)


def test_a_path_missing_from_a_cached_index_is_looked_up_again(
    github: _GitHub,
) -> None:
    """A list added since the index was cached is found by fetching it again."""
    with _session(github) as first:
        first.catalog()
    added = "DC/Events/CBH/[DC] Example Added (CBH).cbl"
    github.tree, github.etag = _tree(_EVENT, _PLAIN, added), '"v2"'
    github.raw[added] = _CBL

    with _session(github) as second:
        result = second.fetch_catalog(added)

    assert result.reading_list["sources"][0]["curator"] == "cbh"


def test_the_size_cap_on_a_download(github: _GitHub) -> None:
    github.raw[_EVENT] = b"x" * 2000
    with (
        _session(github, max_download_bytes=1000) as session,
        pytest.raises(ReadingListFetchError, match="1,000-byte download limit"),
    ):
        session.fetch_catalog(_EVENT)


def test_the_size_cap_on_the_index(github: _GitHub) -> None:
    with (
        _session(github, max_download_bytes=100) as session,
        pytest.raises(ReadingListFetchError, match="download limit"),
    ):
        session.catalog()


def test_the_revision_is_the_sha_of_what_arrived(github: _GitHub) -> None:
    """A branch that moved after the index was taken serves newer bytes."""
    newer = _CBL.replace(b"Civil War</Name>", b"Civil War (Revised)</Name>")
    github.raw[_EVENT] = newer
    with _session(github) as session:
        result = session.fetch_catalog(_EVENT)

    assert result.reading_list["sources"][0]["revision"] == _blob_sha(newer)
    assert _blob_sha(newer) != _SHA


def test_a_fetch_reports_start_and_finish(github: _GitHub) -> None:
    events: list[Any] = []
    with ReadingListSession(on_event=events.append) as session:
        session._transport = httpx.MockTransport(github)
        session.fetch_catalog(_EVENT)

    assert [(e.kind, e.source, e.key) for e in events] == [
        ("reading_list_fetch_started", "catalog", _EVENT),
        ("reading_list_fetch_finished", "catalog", _EVENT),
    ]


def test_urls_are_only_github_hosts(
    session: ReadingListSession, github: _GitHub
) -> None:
    session.fetch_catalog(_EVENT)
    assert {urlsplit(url).netloc for url in github.urls} == {
        "api.github.com",
        "raw.githubusercontent.com",
    }
