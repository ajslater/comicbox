"""
Metron reading lists and story arcs, through the shared paced session.

The calls go through ``MetronOnlineSource.session()``, so they queue at the
same rate gate and fill the same response cache as tagging with the same
token. Imported only when a Metron fetch runs: it loads mokkari.
"""

from __future__ import annotations

from contextlib import contextmanager
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from mokkari.exceptions import (
    ApiError,
    AuthenticationError,
    CacheError,
    RateLimiterError,
    RateLimitError,
)

from comicbox.config.online.settings import OnlineSourceCredentials
from comicbox.events import ReadingListFetchProgress
from comicbox.exceptions import ReadingListFetchError
from comicbox.formats.metron_api.online_source import MetronOnlineSource
from comicbox.formats.metron_api.paced_session import fetch_hooks
from comicbox.readinglists.formats.metron_api import (
    MetronListSummary,
    reading_list_from_metron,
    reading_list_from_metron_arc,
    summary_from_metron,
)
from comicbox.readinglists.schema import SourceKind

if TYPE_CHECKING:
    from collections.abc import Generator
    from datetime import datetime

    import requests

    from comicbox.readinglists.serialize import ReadingListResult
    from comicbox.readinglists.sources import FetchContext

_SOURCE_NAME = "metron"
_MOKKARI_ERRORS = (
    ApiError,
    AuthenticationError,
    CacheError,
    RateLimiterError,
    RateLimitError,
)
_UNCONFIGURED = (
    "Metron needs an API token: pass --auth metron:TOKEN, or set"
    " online.auth.metron.key in the config or COMICBOX_ONLINE__AUTH__METRON__KEY"
    " in the environment."
)
# The last path segment of each paginated endpoint whose pages count.
_ITEMS_PAGE = "items"
_ARC_ISSUES_PAGE = "issue_list"


def _credentials(session: FetchContext) -> OnlineSourceCredentials:
    """Take the caller's credentials, else the config's ``online.auth.metron``."""
    sources = session.settings.online.auth.sources
    configured = sources.get(_SOURCE_NAME) or OnlineSourceCredentials()
    if (given := session.credentials) is None:
        return configured
    return OnlineSourceCredentials(
        key=given.metron_key or configured.key,
        url=given.metron_url or configured.url,
    )


def _configured(session: FetchContext) -> OnlineSourceCredentials:
    """Get the credentials, or raise if there is no API token."""
    credentials = _credentials(session)
    if not credentials.key:
        raise ReadingListFetchError(_UNCONFIGURED)
    return credentials


def check_token(session: FetchContext) -> None:
    """Raise unless a Metron API token is set, before a fetch begins."""
    _configured(session)


def _source(session: FetchContext) -> MetronOnlineSource:
    """Get the token's Metron source, or raise before any request."""
    return MetronOnlineSource(_configured(session), session.settings.online)


class _PageCounter:
    """Emit progress for each page of one paginated endpoint."""

    def __init__(
        self, session: FetchContext, kind: str, key: str, endpoint: str
    ) -> None:
        self._session = session
        self._kind = kind
        self._key = key
        self._endpoint = endpoint
        self._fetched = 0
        self._total: int | None = None

    def __call__(self, response: requests.Response) -> None:
        """Count a page of results; any other response is not one."""
        segments = urlsplit(response.url).path.rstrip("/").split("/")
        if response.status_code != HTTPStatus.OK or segments[-1] != self._endpoint:
            return
        page: dict[str, Any] = response.json()
        if self._total is None:
            self._total = page.get("count")
        self._fetched += len(page.get("results") or ())
        self._session.emit(
            ReadingListFetchProgress(
                index=self._fetched,
                total=self._total,
                source=self._kind,
                key=self._key,
            )
        )


def _detail(response: requests.Response) -> str:
    """Read the ``detail`` message of a Metron error body, if it has one."""
    try:
        body = response.json()
    except ValueError:
        return ""
    detail = body.get("detail") if isinstance(body, dict) else None
    return " ".join(str(detail).split()) if detail else ""


def _describe(exc: Exception) -> str:
    """
    Say what went wrong in one line.

    mokkari chains each HTTP failure to the requests error, whose response
    gives the status; Metron's ``detail`` follows when it says more than
    the status does, as "Invalid token." does.
    """
    response = getattr(exc.__cause__, "response", None)
    if response is None or response.status_code is None:
        return " ".join(str(exc).split())
    status = response.status_code
    phrase = HTTPStatus(status).phrase if status in HTTPStatus else ""
    message = f"HTTP {status} {phrase}".rstrip()
    detail = _detail(response)
    if detail and detail.rstrip(".").casefold() != phrase.casefold():
        message += f": {detail}"
    return message if message.endswith(".") else f"{message}."


@contextmanager
def _calling(
    session: FetchContext, what: str, on_page: _PageCounter | None = None
) -> Generator[MetronOnlineSource]:
    """
    Call Metron with the session's cancel and progress hooks set.

    Every mokkari failure becomes one ``ReadingListFetchError`` naming
    ``what``; a cancel passes through as ``OnlineLookupAbortedError``.
    """
    source = _source(session)
    try:
        with fetch_hooks(abort=session.cancelled.is_set, on_page=on_page):
            yield source
    except _MOKKARI_ERRORS as exc:
        reason = f"{what}: {_describe(exc)}"
        raise ReadingListFetchError(reason) from exc


def search(
    session: FetchContext,
    *,
    name: str | None = None,
    curator: str | None = None,
    username: str | None = None,
    modified_since: datetime | None = None,
) -> list[MetronListSummary]:
    """Search the reading lists the token can see."""
    params: dict[str, str | int] = {}
    if name:
        params["name"] = name
    if curator:
        params["attribution_source"] = curator.upper()
    if username:
        params["username"] = username
    if modified_since is not None:
        params["modified_gt"] = modified_since.isoformat()
    with _calling(session, "Metron reading-list search") as source:
        rows = source.session().reading_lists_list(params)
    return [summary_from_metron(row) for row in rows]


def fetch_list(
    session: FetchContext,
    list_id: int,
    *,
    if_modified_since: datetime | None = None,
) -> ReadingListResult | None:
    """Fetch a reading list, or None when it is unchanged since then."""
    kind, key = SourceKind.METRON_LIST.value, str(list_id)
    counter = _PageCounter(session, kind, key, _ITEMS_PAGE)
    with _calling(session, f"Metron reading list {list_id}", counter) as source:
        api = source.session()
        header = api.reading_list(list_id, if_modified_since=if_modified_since)
        if header is None:
            return None
        if if_modified_since is None:
            items = api.reading_list_items(list_id)
        else:
            # Changed since then, so the cached header and items are older
            # still: fetch both anew, and leave the cache holding them.
            with source.refreshing_session() as fresh:
                header = fresh.reading_list(list_id) or header
                items = fresh.reading_list_items(list_id)
    return reading_list_from_metron(header, items)


def fetch_arc(
    session: FetchContext,
    arc_id: int,
    *,
    if_modified_since: datetime | None = None,
) -> ReadingListResult | None:
    """Fetch a story arc as a list, or None when it is unchanged since then."""
    kind, key = SourceKind.METRON_ARC.value, str(arc_id)
    counter = _PageCounter(session, kind, key, _ARC_ISSUES_PAGE)
    with _calling(session, f"Metron arc {arc_id}", counter) as source:
        api = source.session()
        arc = api.arc(arc_id, if_modified_since=if_modified_since)
        if arc is None:
            return None
        if if_modified_since is None:
            issues = api.arc_issues_list(arc_id)
        else:
            with source.refreshing_session() as fresh:
                arc = fresh.arc(arc_id) or arc
                issues = fresh.arc_issues_list(arc_id)
    return reading_list_from_metron_arc(arc, issues)
