"""
The DieselTech catalog: an index of a GitHub repository of ``.cbl`` lists.

The repository has no index, so one is built from a single recursive
git-tree call to GitHub's API and cached under the online cache directory
with its ETag. Within ``readinglists.catalog_ttl`` the cached index is used
without a request; after it, the ETag revalidates it. Lists download from
``raw.githubusercontent.com``, which GitHub's API rate limit does not cover.

Paths are not stable there, so a list is known by its path and its blob
sha: when a path is gone, the entry with the same sha is taken in its
place.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote

from loguru import logger

from comicbox.config.online.settings import CacheMode
from comicbox.exceptions import ReadingListFetchError
from comicbox.readinglists.changes import quote_value
from comicbox.readinglists.identity import fold_text
from comicbox.readinglists.schema import (
    SOURCE_CURATOR_KEY,
    SOURCE_KEY_KEY,
    SOURCE_KIND_KEY,
    SOURCE_REVISION_KEY,
    SOURCE_URL_KEY,
    SourceKind,
)
from comicbox.readinglists.sources.url import Download, HttpStatusError, download

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from comicbox.readinglists.sources import FetchContext

_API_URL = "https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1"
_RAW_URL = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"
_API_HEADERS: Final = MappingProxyType(
    {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
)
_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
_SUFFIX = ".cbl"
_CACHE_VERSION = 1
_RATE_LIMITED = frozenset({HTTPStatus.FORBIDDEN, HTTPStatus.TOO_MANY_REQUESTS})
# How far ahead of this clock a cache's time may be before it is damaged.
_CLOCK_SKEW = timedelta(minutes=5)

# The curator marks in the DieselTech tree, pinned from a scan of `main` on
# 2026-11-14: a trailing ``(MARK)`` on the file name, else a folder that is
# the mark or starts with it and a space (``CBRO - With Events``). Other
# trailing groups name eras or editions (``(Post-Crisis)``, ``(New 52)``),
# not curators. Values are the model's curator spellings; the ones Metron
# has no name for keep their own.
_CURATOR_MARKS: Final = MappingProxyType(
    {
        "cbro": "cbro",
        "web-cbro": "cbro",
        "cmro": "cmro",
        "cbh": "cbh",
        "comic book herald": "cbh",
        "cbt": "cbt",
        "htlc": "htlc",
        "locg": "locg",
        "web-locg": "locg",
        "mg": "mg",
        "marvel guides": "mg",
        "official": "official",
        "uxro": "uxro",
        "ultimate x-men reading order": "uxro",
        "kcv": "kcv",
        "web-kcv": "kcv",
        "community": "community",
        "community-contributed": "community",
    }
)
_TRAILING_GROUP_RE = re.compile(r"\(([^()]*)\)\s*$")


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """
    One list in the catalog.

    ``publisher`` and ``category`` are the first two folders of its path,
    when it has them. ``curator`` is the site the list was taken from, from
    the file name or a folder, in the model's spelling.
    """

    path: str
    sha: str
    size: int
    publisher: str | None = None
    category: str | None = None
    curator: str | None = None

    @property
    def name(self) -> str:
        """The file name without its ``.cbl``."""
        return PurePosixPath(self.path).stem


@dataclass(frozen=True, slots=True)
class Catalog:
    """
    The index of one repository at one ref.

    ``etag`` revalidates it; ``fetched`` is when GitHub last confirmed it.
    """

    repo: str
    ref: str
    etag: str | None
    fetched: datetime
    entries: tuple[CatalogEntry, ...]

    def find(self, path: str, sha: str | None = None) -> CatalogEntry | None:
        """
        Find a list by path, else by blob sha, if one is given.

        Copies share a sha. Among them, the one with the old path's file
        name wins, then the one in its folder; if that leaves more than
        one, ``ReadingListFetchError`` names them rather than guess.
        """
        by_path = next((entry for entry in self.entries if entry.path == path), None)
        if by_path is not None or not sha:
            return by_path
        return _one_copy([entry for entry in self.entries if entry.sha == sha], path)

    def search(self, query: str) -> tuple[CatalogEntry, ...]:
        """Find the lists whose path holds every word of ``query``."""
        if not (words := fold_text(query).split()):
            return ()
        return tuple(
            entry
            for entry in self.entries
            if all(word in fold_text(entry.path) for word in words)
        )


def _one_copy(candidates: list[CatalogEntry], path: str) -> CatalogEntry | None:
    """Tell copies of one blob apart by the old path's name, then its folder."""
    old = PurePosixPath(path)
    for same in (_same_name(old), _same_folder(old)):
        if len(candidates) <= 1:
            break
        candidates = [entry for entry in candidates if same(entry)] or candidates
    if len(candidates) > 1:
        names = ", ".join(entry.path for entry in candidates)
        reason = f"{path} is gone, and {len(candidates)} lists share its sha: {names}."
        raise ReadingListFetchError(reason)
    return candidates[0] if candidates else None


def _same_name(old: PurePosixPath) -> Callable[[CatalogEntry], bool]:
    return lambda entry: PurePosixPath(entry.path).name == old.name


def _same_folder(old: PurePosixPath) -> Callable[[CatalogEntry], bool]:
    return lambda entry: PurePosixPath(entry.path).parent == old.parent


def curator(path: str) -> str | None:
    """Read a list's curator from its file name, else its innermost folder."""
    parts = PurePosixPath(path)
    if (match := _TRAILING_GROUP_RE.search(parts.stem)) and (
        mark := _CURATOR_MARKS.get(match.group(1).strip().casefold())
    ):
        return mark
    for folder in reversed(parts.parent.parts):
        folded = folder.casefold()
        for name, mark in _CURATOR_MARKS.items():
            if folded == name or folded.startswith(f"{name} "):
                return mark
    return None


def _entry(item: Mapping[str, Any]) -> CatalogEntry:
    path = str(item["path"])
    folders = PurePosixPath(path).parent.parts
    return CatalogEntry(
        path=path,
        sha=str(item["sha"]),
        size=int(item.get("size") or 0),
        publisher=folders[0] if folders else None,
        category=folders[1] if len(folders) > 1 else None,
        curator=curator(path),
    )


def entries_from_tree(items: Iterable[Mapping[str, Any]]) -> tuple[CatalogEntry, ...]:
    """Index the ``.cbl`` blobs of a git tree, in path order."""
    lists = (
        item
        for item in items
        if item.get("type") == "blob" and str(item.get("path", "")).endswith(_SUFFIX)
    )
    return tuple(sorted((_entry(item) for item in lists), key=lambda e: e.path))


# Cache file.


def _cache_path(context: FetchContext, repo: str, ref: str) -> Path | None:
    """Where this repository's index is cached; None when caching is off."""
    from comicbox.formats.base.online.sources.base import resolve_cache_dir

    cache = context.settings.online.cache
    if cache.mode is CacheMode.OFF:
        return None
    digest = hashlib.sha256(f"{repo}@{ref}".encode()).hexdigest()[:16]
    return resolve_cache_dir(cache.dir) / f"readinglists_catalog_{digest}.json"


def _read_cache(path: Path | None, repo: str, ref: str) -> Catalog | None:
    """Read a cached index of this repository and ref, or nothing."""
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (data["version"], data["repo"], data["ref"]) != (_CACHE_VERSION, repo, ref):
            return None
        fetched = datetime.fromisoformat(data["fetched"])
        # A time with no zone cannot be compared; one in the future would
        # be reused forever. Either way the file is damaged.
        if fetched.tzinfo is None or fetched > datetime.now(tz=UTC) + _CLOCK_SKEW:
            reason = f"fetched at {data['fetched']!r}"
            raise ValueError(reason)  # noqa: TRY301 - one handler for every damage
        return Catalog(
            repo=repo,
            ref=ref,
            etag=data["etag"],
            fetched=fetched,
            entries=tuple(CatalogEntry(**entry) for entry in data["entries"]),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.debug(f"reading-list catalog: ignoring unreadable cache {path}: {exc}")
        return None


def _write_cache(path: Path | None, catalog: Catalog) -> None:
    """Replace the cached index whole, so a reader never sees half of one."""
    if path is None:
        return
    data = {
        "version": _CACHE_VERSION,
        "repo": catalog.repo,
        "ref": catalog.ref,
        "etag": catalog.etag,
        "fetched": catalog.fetched.isoformat(),
        "entries": [asdict(entry) for entry in catalog.entries],
    }
    temp: str | None = None
    try:
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        Path(temp).replace(path)
        temp = None
    except OSError as exc:
        # The index is already in hand; a cache that cannot be written only
        # costs the next run a request.
        logger.warning(f"reading-list catalog: cannot cache the index: {exc}")
    finally:
        if temp is not None:
            Path(temp).unlink(missing_ok=True)


# Fetches.


def _repo_and_ref(context: FetchContext) -> tuple[str, str]:
    settings = context.settings.readinglists
    repo, ref = settings.catalog_repo.strip(), settings.catalog_ref.strip()
    if not _REPO_RE.match(repo) or not ref:
        reason = (
            "readinglists.catalog_repo must be a GitHub owner/name and"
            f" catalog_ref a branch, tag or commit: {repo!r} at {ref!r}."
        )
        raise ReadingListFetchError(reason)
    return repo, ref


def _rate_limit_reason(error: HttpStatusError) -> str | None:
    """Explain a refusal for a spent API rate limit, if it was one."""
    if (
        error.status not in _RATE_LIMITED
        or error.headers.get("x-ratelimit-remaining") != "0"
    ):
        return None
    reset = error.headers.get("x-ratelimit-reset", "")
    when = ""
    if reset.isascii() and reset.isdigit():
        try:
            at = datetime.fromtimestamp(int(reset), tz=UTC).astimezone()
        except (OverflowError, ValueError, OSError):
            pass  # Too far off to be a time; say nothing of when.
        else:
            when = f" It resets at {at:%H:%M}."
    return f"GitHub's API rate limit for this address is spent.{when}"


def _fetch_tree(
    context: FetchContext, repo: str, ref: str, cached: Catalog | None
) -> Catalog:
    """Fetch the index, or confirm the cached one with its ETag."""
    url = _API_URL.format(repo=repo, ref=quote(ref, safe="/"))
    headers = dict(_API_HEADERS)
    if cached is not None and cached.etag:
        headers["If-None-Match"] = cached.etag
    fetched = _download_tree(context, url, headers, repo, ref)
    now = datetime.now(tz=UTC)
    if fetched.not_modified and cached is not None:
        return Catalog(repo, ref, cached.etag, now, cached.entries)
    entries = _entries_from_body(fetched.body, url, repo, ref)
    return Catalog(repo, ref, fetched.headers.get("etag"), now, entries)


def _download_tree(
    context: FetchContext, url: str, headers: dict[str, str], repo: str, ref: str
) -> Download:
    """Download the tree, saying which repository or limit refused it."""
    max_bytes = context.settings.readinglists.max_download_bytes
    try:
        return download(
            context.http(), url, max_bytes, headers, cancelled=context.cancelled.is_set
        )
    except HttpStatusError as exc:
        if exc.status == HTTPStatus.NOT_FOUND:
            reason = f"GitHub has no repository {repo} with a ref {ref}."
            raise ReadingListFetchError(reason) from exc
        if reason := _rate_limit_reason(exc):
            raise ReadingListFetchError(reason) from exc
        raise


def _entries_from_body(
    body: bytes, url: str, repo: str, ref: str
) -> tuple[CatalogEntry, ...]:
    """Index a tree's lists, or say why it is no git tree to index."""
    try:
        tree = json.loads(body)
        items = tree["tree"]
    except (ValueError, KeyError, TypeError) as exc:
        reason = f"{url}: not a git tree: {exc}"
        raise ReadingListFetchError(reason) from exc
    if tree.get("truncated"):
        # GitHub cuts a recursive tree off past its limits; an index of part
        # of a repository would silently lose lists.
        reason = (
            f"GitHub truncated the tree of {repo} at {ref}, so it cannot be indexed."
        )
        raise ReadingListFetchError(reason)
    try:
        return entries_from_tree(items)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        reason = f"{url}: not a git tree: {quote_value(exc)}"
        raise ReadingListFetchError(reason) from exc


def load_catalog(
    context: FetchContext, *, refresh: bool = False
) -> tuple[Catalog, bool]:
    """
    Get the index; say whether GitHub was asked for it just now.

    ``refresh`` asks GitHub even within the cache lifetime, as cache mode
    ``refresh`` does.
    """
    repo, ref = _repo_and_ref(context)
    path = _cache_path(context, repo, ref)
    cached = _read_cache(path, repo, ref)
    refresh = refresh or context.settings.online.cache.mode is CacheMode.REFRESH
    lifetime = context.settings.readinglists.catalog_ttl
    if (
        cached is not None
        and not refresh
        and datetime.now(tz=UTC) - cached.fetched < lifetime
    ):
        return cached, False
    context.check_cancelled()
    catalog = _fetch_tree(context, repo, ref, cached)
    _write_cache(path, catalog)
    return catalog, True


def _blob_sha(data: bytes) -> str:
    """Hash the bytes as git hashes a blob, so they match the tree's sha."""
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def _download(
    context: FetchContext, catalog: Catalog, entry: CatalogEntry
) -> tuple[bytes, dict[str, Any]]:
    """Download one list; return its bytes and the source to record."""
    url = _RAW_URL.format(
        repo=catalog.repo, ref=quote(catalog.ref, safe="/"), path=quote(entry.path)
    )
    max_bytes = context.settings.readinglists.max_download_bytes
    data = download(
        context.http(), url, max_bytes, cancelled=context.cancelled.is_set
    ).body
    source = {
        SOURCE_KIND_KEY: SourceKind.CATALOG.value,
        SOURCE_KEY_KEY: entry.path,
        SOURCE_URL_KEY: url,
        # The sha of what arrived: the index may be older than the file.
        SOURCE_REVISION_KEY: _blob_sha(data),
        SOURCE_CURATOR_KEY: entry.curator,
    }
    return data, source


def fetch_entry(
    context: FetchContext, path: str, sha: str | None = None
) -> tuple[bytes, dict[str, Any]]:
    """
    Download a list by path, or by sha when the path is gone.

    A cached index may predate a rename: when the list is missing from it,
    or its path no longer downloads, the index is fetched again once and
    the list looked up anew.
    """
    catalog, asked = load_catalog(context)
    if (entry := catalog.find(path, sha)) is not None:
        try:
            return _download(context, catalog, entry)
        except HttpStatusError as exc:
            if asked or exc.status != HTTPStatus.NOT_FOUND:
                raise
    if not asked:
        catalog, _ = load_catalog(context, refresh=True)
        entry = catalog.find(path, sha)
    if entry is None:
        reason = f"{path} is not in the catalog of {catalog.repo} at {catalog.ref}."
        raise ReadingListFetchError(reason)
    context.check_cancelled()
    return _download(context, catalog, entry)
