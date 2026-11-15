"""
ReadingListSession: the façade codex holds to fetch reading lists.

Synchronous: each call is one fetch, with no prompt loop. Network libraries
are imported inside methods, so importing this module stays cheap. A fetch
that fails raises ``ReadingListFetchError``; a cancel raises
``OnlineLookupAbortedError``, as tagging does.
"""

from __future__ import annotations

import sys
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from comicbox.config import get_config
from comicbox.events import ReadingListFetchFinished, ReadingListFetchStarted
from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.readinglists.schema import (
    SOURCE_KEY_KEY,
    SOURCE_KIND_KEY,
    SOURCE_REVISION_KEY,
    SOURCE_URL_KEY,
    SourceKind,
)
from comicbox.readinglists.serialize import ReadingListResult, loads
from comicbox.readinglists.sources import attach_source
from comicbox.version import set_user_agent_context, user_agent

if TYPE_CHECKING:
    from collections.abc import Generator
    from datetime import datetime
    from typing import Self

    import httpx

    from comicbox.config.settings import ComicboxSettings
    from comicbox.events import Event, EventHandler
    from comicbox.online_session import OnlineCredentials
    from comicbox.readinglists.formats.metron_api import MetronListSummary
    from comicbox.readinglists.sources.catalog import Catalog, CatalogEntry

# Read out of sys.modules on close, so a session that never touched Metron
# never imports it.
_METRON_SOURCE_MODULE = "comicbox.formats.metron_api.online_source"
_TIMEOUT_SECONDS = 30.0


class ReadingListSession:
    """
    Fetch reading lists from URLs and online sources.

    ``credentials`` are an ``OnlineCredentials``, as ``OnlineSession``
    takes; without them the config's ``online.auth`` is used. ``config``
    is a ``ComicboxSettings``; without it the usual config files and
    environment are read once. ``on_event`` receives the
    ``ReadingListFetch*`` events. ``client_name`` names the embedding
    application in the outgoing User-Agent.

    A context manager: leaving it closes the connections the session
    opened.
    """

    def __init__(
        self,
        *,
        credentials: OnlineCredentials | None = None,
        config: ComicboxSettings | None = None,
        on_event: EventHandler | None = None,
        client_name: str | None = None,
    ) -> None:
        """Read the config once; open nothing until the first fetch."""
        if client_name is not None:
            # Set before any client exists: clients bake the header in.
            set_user_agent_context("lib", client=client_name)
        self._credentials = credentials
        self._settings: ComicboxSettings = (
            config if config is not None else get_config()
        )
        self._on_event = on_event
        self._cancelled = threading.Event()
        self._http: httpx.Client | None = None
        # Tests and embedders may set an httpx transport before first use.
        self._transport: httpx.BaseTransport | None = None

    def __enter__(self) -> Self:
        """Use the session in a with block."""
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Close the session's connections."""
        self.close()

    @property
    def settings(self) -> ComicboxSettings:
        """The settings every fetch uses."""
        return self._settings

    @property
    def credentials(self) -> OnlineCredentials | None:
        """The credentials the session was given, if any."""
        return self._credentials

    def cancel(self) -> None:
        """Stop the session: the fetch under way, or the next, raises."""
        self._cancelled.set()

    def close(self) -> None:
        """Close the HTTP client and Metron's shared sessions, if opened."""
        if self._http is not None:
            self._http.close()
            self._http = None
        if (metron := sys.modules.get(_METRON_SOURCE_MODULE)) is not None:
            metron.close_shared_sessions()

    # Internals shared by the sources.

    def check_cancelled(self) -> None:
        """Raise if the session was cancelled."""
        if self._cancelled.is_set():
            reason = "Reading-list fetch cancelled."
            raise OnlineLookupAbortedError(reason)

    @property
    def cancelled(self) -> threading.Event:
        """The event ``cancel()`` sets, for sources that wait."""
        return self._cancelled

    def emit(self, event: Event) -> None:
        """Hand an event to the caller's handler, if any."""
        if self._on_event is not None:
            self._on_event(event)

    def http(self) -> httpx.Client:
        """Get the session's HTTP client, built on first use."""
        if self._http is None:
            import httpx

            self._http = httpx.Client(
                follow_redirects=True,
                timeout=_TIMEOUT_SECONDS,
                headers={"User-Agent": user_agent()},
                transport=self._transport,
            )
        return self._http

    @contextmanager
    def fetching(self, kind: str, key: str) -> Generator[None]:
        """Bracket one fetch with its start and finish events."""
        self.check_cancelled()
        self.emit(ReadingListFetchStarted(source=kind, key=key))
        try:
            yield
        finally:
            self.emit(ReadingListFetchFinished(source=kind, key=key))

    def load_fetched(self, data: bytes, source: dict[str, Any]) -> ReadingListResult:
        """Read fetched bytes as a list from ``source``, detecting the format."""
        result = loads(data)
        reading_list = attach_source(result.reading_list, source)
        return ReadingListResult(reading_list, result.fmt, result.warnings)

    # Fetches.

    def fetch_url(self, url: str) -> ReadingListResult:
        """
        Fetch a list from an http or https URL, in any format comicbox reads.

        Redirects are followed and the download is capped at
        ``readinglists.max_download_bytes``. Its source is of kind ``url``.
        """
        from comicbox.readinglists.sources.url import fetch

        kind = SourceKind.URL.value
        with self.fetching(kind, url):
            max_bytes = self._settings.readinglists.max_download_bytes
            data, revision = fetch(self.http(), url, max_bytes)
            self.check_cancelled()
            source = {
                SOURCE_KIND_KEY: kind,
                SOURCE_KEY_KEY: url,
                SOURCE_URL_KEY: url,
                SOURCE_REVISION_KEY: revision,
            }
            return self.load_fetched(data, source)

    def search_metron(
        self,
        *,
        name: str | None = None,
        curator: str | None = None,
        username: str | None = None,
        modified_since: datetime | None = None,
    ) -> list[MetronListSummary]:
        """
        Search Metron's reading lists: public ones and the token's own.

        ``curator`` is a site Metron credits lists to, such as ``cbro``.
        Needs a Metron API token.
        """
        from comicbox.readinglists.sources import metron

        self.check_cancelled()
        return metron.search(
            self,
            name=name,
            curator=curator,
            username=username,
            modified_since=modified_since,
        )

    def fetch_metron_list(
        self, list_id: int, *, if_modified_since: datetime | None = None
    ) -> ReadingListResult | None:
        """
        Fetch a Metron reading list, in its order.

        Returns None, having fetched no items, when the list is unchanged
        since ``if_modified_since``. Progress events count the items as
        their pages arrive. Needs a Metron API token. The result has no
        ``fmt``: it was read from no document.
        """
        from comicbox.readinglists.sources import metron

        metron.check_token(self)
        with self.fetching(SourceKind.METRON_LIST.value, str(list_id)):
            return metron.fetch_list(self, list_id, if_modified_since=if_modified_since)

    def fetch_metron_arc(
        self, arc_id: int, *, if_modified_since: datetime | None = None
    ) -> ReadingListResult | None:
        """
        Fetch a Metron story arc as an unordered list.

        Returns None, having fetched no issues, when the arc is unchanged
        since ``if_modified_since``. Needs a Metron API token.
        """
        from comicbox.readinglists.sources import metron

        metron.check_token(self)
        with self.fetching(SourceKind.METRON_ARC.value, str(arc_id)):
            return metron.fetch_arc(self, arc_id, if_modified_since=if_modified_since)

    def catalog(self, *, refresh: bool = False) -> Catalog:
        """
        Get the index of the reading-list catalog on GitHub.

        The repository and ref are ``readinglists.catalog_repo`` and
        ``catalog_ref``. The index is cached under the online cache
        directory: within ``readinglists.catalog_ttl`` no request is made,
        and after it the cached index is revalidated. ``refresh`` asks
        GitHub now.
        """
        from comicbox.readinglists.sources.catalog import load_catalog

        self.check_cancelled()
        return load_catalog(self, refresh=refresh)[0]

    def search_catalog(self, query: str) -> tuple[CatalogEntry, ...]:
        """Find the catalog's lists whose path holds every word of ``query``."""
        return self.catalog().search(query)

    def fetch_catalog(self, path: str, *, sha: str | None = None) -> ReadingListResult:
        """
        Fetch a list from the catalog by its path.

        Paths change there; when ``path`` is gone and ``sha`` names the
        blob it had, the list with that sha is fetched in its place. The
        result's source is of kind ``catalog``, keyed by the path it was
        found at, with the blob sha as its revision.
        """
        from comicbox.readinglists.sources.catalog import fetch_entry

        with self.fetching(SourceKind.CATALOG.value, path):
            data, source = fetch_entry(self, path, sha)
            self.check_cancelled()
            return self.load_fetched(data, source)
