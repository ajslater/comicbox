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
    from typing import Self

    import httpx

    from comicbox.config.settings import ComicboxSettings
    from comicbox.events import Event, EventHandler
    from comicbox.online_session import OnlineCredentials

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
        self.check_cancelled()
        self.emit(ReadingListFetchStarted(source=kind, key=url))
        try:
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
        finally:
            self.emit(ReadingListFetchFinished(source=kind, key=url))
