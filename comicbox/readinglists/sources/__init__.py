"""
Where reading lists are fetched from: URLs, Metron and the DieselTech catalog.

Network libraries are imported inside functions, so importing this package
stays cheap; only a fetch pays for them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from comicbox.empty import is_empty
from comicbox.readinglists.schema import SOURCE_KIND_KEY, SOURCES_KEY, SourceKind

if TYPE_CHECKING:
    import threading
    from collections.abc import Mapping

    import httpx

    from comicbox.config.settings import ComicboxSettings
    from comicbox.events import Event
    from comicbox.online_session import OnlineCredentials


class FetchContext(Protocol):
    """
    What a source needs from the session that runs its fetch.

    ``ReadingListSession`` is one. Sources name this rather than the session
    class, so the session can import them without a cycle.
    """

    @property
    def settings(self) -> ComicboxSettings:
        """The settings every fetch uses."""
        ...

    @property
    def credentials(self) -> OnlineCredentials | None:
        """The credentials the session was given, if any."""
        ...

    @property
    def cancelled(self) -> threading.Event:
        """Set once the session is cancelled."""
        ...

    def emit(self, event: Event) -> None:
        """Hand an event to the caller's handler, if any."""
        ...

    def check_cancelled(self) -> None:
        """Raise if the session was cancelled."""
        ...

    def http(self) -> httpx.Client:
        """Get the session's HTTP client."""
        ...


def attach_source(
    reading_list: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    """
    Record where a fetched list came from.

    A file read gives its list a source of kind ``file``; a fetched one came
    from ``source`` instead, so that one takes its place, keeping what it
    knew that ``source`` does not, such as a CBL's curator. A list with no
    file source gets ``source`` first.
    """
    fetched = {key: value for key, value in source.items() if not is_empty(value)}
    sources = [dict(item) for item in reading_list.get(SOURCES_KEY) or ()]
    for index, item in enumerate(sources):
        if item.get(SOURCE_KIND_KEY) == SourceKind.FILE.value:
            del item[SOURCE_KIND_KEY]
            sources[index] = {**item, **fetched}
            break
    else:
        sources.insert(0, fetched)
    return {**reading_list, SOURCES_KEY: sources}
