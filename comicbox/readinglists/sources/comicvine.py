"""
Comic Vine story arcs, through the shared simyan client.

The calls go through ``ComicVineOnlineSource``, so they spend the same
hourly budgets and fill the same response cache as tagging with the same
key. Imported only when a Comic Vine fetch runs: it loads simyan.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Final

from simyan.errors import ServiceError

from comicbox.config.online.settings import OnlineSourceCredentials
from comicbox.events import ReadingListFetchProgress
from comicbox.exceptions import ReadingListFetchError
from comicbox.formats.base.online.retry import RetryCategory
from comicbox.formats.comicvine_api.online_source import ComicVineOnlineSource
from comicbox.readinglists.formats.comicvine_api import (
    reading_list_from_comicvine_arc,
)
from comicbox.readinglists.schema import SourceKind

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from comicbox.readinglists.serialize import ReadingListResult
    from comicbox.readinglists.sources import FetchContext

_SOURCE_NAME = "comicvine"
_UNCONFIGURED = (
    "Comic Vine needs an API key: pass --auth comicvine:KEY, or set"
    " online.auth.comicvine.key in the config or"
    " COMICBOX_ONLINE__AUTH__COMICVINE__KEY in the environment."
)
# Rows a call asks for by id: one page of a Comic Vine list endpoint.
_BATCH_SIZE: Final = 100


def _credentials(session: FetchContext) -> OnlineSourceCredentials:
    """Take the caller's credentials, else the config's ``online.auth.comicvine``."""
    sources = session.settings.online.auth.sources
    configured = sources.get(_SOURCE_NAME) or OnlineSourceCredentials()
    if (given := session.credentials) is None:
        return configured
    return OnlineSourceCredentials(
        key=given.comicvine_key or configured.key,
        url=given.comicvine_url or configured.url,
    )


def _configured(session: FetchContext) -> OnlineSourceCredentials:
    """Get the credentials, or raise if there is no API key."""
    credentials = _credentials(session)
    if not credentials.key:
        raise ReadingListFetchError(_UNCONFIGURED)
    return credentials


def check_key(session: FetchContext) -> None:
    """Raise unless a Comic Vine API key is set, before a fetch begins."""
    _configured(session)


def _describe(exc: ServiceError) -> str:
    """
    Say what went wrong in one line.

    A refused key and a missing arc are said plainly; anything else in
    simyan's words, which for a spent hourly budget say when a call frees.
    """
    # simyan raises some with None for Comic Vine's missing message.
    said = " ".join(str(exc.args[0]).split()) if exc.args and exc.args[0] else ""
    match ComicVineOnlineSource.classify_retry_exception(exc):
        case RetryCategory.AUTH:
            return "Comic Vine refused the API key."
        case RetryCategory.NOT_FOUND:
            return "not found."
        case RetryCategory.RATE_LIMIT if not said:
            return "Comic Vine's rate limit is reached."
        case _:
            said = said or "Comic Vine gave no reason"
            return said if said.endswith(".") else f"{said}."


@contextmanager
def _calling(session: FetchContext, what: str) -> Generator[ComicVineOnlineSource]:
    """
    Call Comic Vine, making every simyan failure one fetch error.

    The error names ``what``; a cancel passes through as
    ``OnlineLookupAbortedError``.
    """
    source = ComicVineOnlineSource(_configured(session), session.settings.online)
    try:
        yield source
    except ServiceError as exc:
        reason = f"{what}: {_describe(exc)}"
        raise ReadingListFetchError(reason) from exc


def _unique(ids: Iterable[int]) -> list[int]:
    return list(dict.fromkeys(ids))


def _batches(ids: list[int]) -> Generator[list[int]]:
    for start in range(0, len(ids), _BATCH_SIZE):
        yield ids[start : start + _BATCH_SIZE]


def fetch_arc(session: FetchContext, arc_id: int) -> ReadingListResult:
    """
    Fetch a story arc as a list: the arc, then its issues, then their volumes.

    The arc names its issues by id alone, so they are asked for by id, a
    hundred a call, and their volumes the same way, for the series, numbers
    and dates. Each issue call emits a progress event counting the issues
    asked for.

    A cancel is checked before each call. A call already sent runs to its
    end: simyan has no hook to stop one, and paces each to a second.
    """
    kind, key = SourceKind.COMICVINE_ARC.value, str(arc_id)
    with _calling(session, f"Comic Vine arc {arc_id}") as source:
        arc = source.story_arc(arc_id)
        issue_ids = _unique(member.id for member in arc.issues)
        issues, asked = [], 0
        for batch in _batches(issue_ids):
            session.check_cancelled()
            issues.extend(source.issues_by_id(batch))
            asked += len(batch)
            session.emit(
                ReadingListFetchProgress(
                    index=asked,
                    total=len(issue_ids),
                    source=kind,
                    key=key,
                )
            )
        volumes = []
        for batch in _batches(_unique(issue.volume.id for issue in issues)):
            session.check_cancelled()
            volumes.extend(source.volumes_by_id(batch))
    return reading_list_from_comicvine_arc(arc, issues, volumes)
