"""
A fake simyan ``Comicvine`` and Comic Vine payloads, for reading-list tests.

The fake stands in for the client ``ComicVineOnlineSource`` builds, so the
shared-client path runs as it does for tagging. It answers from payloads
in Comic Vine's own field names, read into simyan's models as simyan
reads them, and records every call.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from simyan.errors import ServiceError
from simyan.schemas.issue import BasicIssue
from simyan.schemas.story_arc import StoryArc
from simyan.schemas.volume import BasicVolume

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    import pytest

_SITE = "https://comicvine.gamespot.com"
_API = f"{_SITE}/api"
_DATE_ADDED = "2008-06-06 11:27:52"
_UPDATED = "2024-05-01 12:00:00"
_IMAGE = {
    key: f"{_SITE}/a/uploads/{key}.jpg"
    for key in (
        "icon_url",
        "medium_url",
        "original_url",
        "screen_large_url",
        "screen_url",
        "small_url",
        "super_url",
        "thumb_url",
        "tiny_url",
    )
}


def _entry(singular: str, code: int, id_: int, name: str | None) -> dict[str, Any]:
    return {
        "api_detail_url": f"{_API}/{singular}/{code}-{id_}/",
        "id": id_,
        "name": name,
        "site_detail_url": f"{_SITE}/x/{code}-{id_}/",
    }


def arc_row(
    issue_ids: Iterable[int], arc_id: int = 12, **fields: Any
) -> dict[str, Any]:
    """Build a ``get_story_arc`` payload; ``fields`` override any key."""
    issues = [_entry("issue", 4000, id_, None) for id_ in issue_ids]
    return {
        "api_detail_url": f"{_API}/story_arc/4045-{arc_id}/",
        "count_of_isssue_appearances": len(issues),
        "date_added": _DATE_ADDED,
        "date_last_updated": _UPDATED,
        "deck": "Heroes fight.",
        "description": "<p>Hero against <b>hero</b>.</p>",
        "id": arc_id,
        "image": _IMAGE,
        "issues": issues,
        "name": "Crimson Tide",
        "site_detail_url": f"{_SITE}/crimson-tide/4045-{arc_id}/",
        **fields,
    }


def issue_row(
    issue_id: int, volume_id: int = 7, volume_name: str = "Crimson Tide", **fields: Any
) -> dict[str, Any]:
    """Build a ``list_issues`` row; ``fields`` override any key."""
    return {
        "api_detail_url": f"{_API}/issue/4000-{issue_id}/",
        "cover_date": "2006-07-01",
        "date_added": _DATE_ADDED,
        "date_last_updated": _UPDATED,
        "id": issue_id,
        "image": _IMAGE,
        "issue_number": str(issue_id),
        "name": f"A story title {issue_id}",
        "site_detail_url": f"{_SITE}/x/4000-{issue_id}/",
        "store_date": "2006-05-03",
        "volume": _entry("volume", 4050, volume_id, volume_name),
        **fields,
    }


def volume_row(
    volume_id: int = 7, name: str = "Crimson Tide", **fields: Any
) -> dict[str, Any]:
    """Build a ``list_volumes`` row; ``fields`` override any key."""
    return {
        "api_detail_url": f"{_API}/volume/4050-{volume_id}/",
        "count_of_issues": 7,
        "date_added": _DATE_ADDED,
        "date_last_updated": _UPDATED,
        "id": volume_id,
        "image": _IMAGE,
        "name": name,
        "publisher": _entry("publisher", 4010, 31, "Marvel"),
        "site_detail_url": f"{_SITE}/x/4050-{volume_id}/",
        "start_year": "2006",
        **fields,
    }


def _ids(params: dict[str, Any]) -> list[int]:
    """Read the ids out of an ``id:1|2|3`` filter."""
    field, _, values = params["filter"].partition(":")
    assert field == "id", params
    return [int(value) for value in values.split("|")]


class FakeComicvine:
    """
    Answer ``get_story_arc``, ``list_issues`` and ``list_volumes``.

    A missing arc fails as simyan fails Comic Vine's body status 101.
    ``fail`` maps a method name to the error it raises instead, and
    ``before`` runs ahead of every call, as a cancel would arrive.
    """

    def __init__(self) -> None:
        """Start with nothing to serve and nothing called."""
        self.arcs: dict[int, dict[str, Any]] = {}
        self.issues: dict[int, dict[str, Any]] = {}
        self.volumes: dict[int, dict[str, Any]] = {}
        self.calls: list[tuple[Any, ...]] = []
        self.fail: dict[str, Exception] = {}
        self.before: Callable[[str], None] | None = None
        self.built = 0
        self.closed = 0
        # What `close_client` closes.
        self._session = SimpleNamespace(close=self._close)

    def _close(self) -> None:
        self.closed += 1

    def serve(
        self,
        arc: dict[str, Any],
        issues: Iterable[dict[str, Any]] = (),
        volumes: Iterable[dict[str, Any]] = (),
    ) -> None:
        """Answer for one arc, its issues and their volumes."""
        self.arcs[arc["id"]] = arc
        self.issues.update((row["id"], row) for row in issues)
        self.volumes.update((row["id"], row) for row in volumes)

    def _call(self, *call: Any) -> None:
        if self.before is not None:
            self.before(call[0])
        self.calls.append(call)
        if (error := self.fail.get(call[0])) is not None:
            raise error

    def get_story_arc(self, story_arc_id: int) -> StoryArc:
        self._call("get_story_arc", story_arc_id)
        if story_arc_id not in self.arcs:
            reason = "Object Not Found"
            raise ServiceError(reason)
        return StoryArc.model_validate(self.arcs[story_arc_id])

    def list_issues(
        self, params: dict[str, Any] | None = None, max_results: int | None = 500
    ) -> list[BasicIssue]:
        params = params or {}
        self._call("list_issues", params.get("filter"), max_results)
        return [
            BasicIssue.model_validate(self.issues[id_])
            for id_ in _ids(params)
            if id_ in self.issues
        ]

    def list_volumes(
        self, params: dict[str, Any] | None = None, max_results: int | None = 500
    ) -> list[BasicVolume]:
        params = params or {}
        self._call("list_volumes", params.get("filter"), max_results)
        return [
            BasicVolume.model_validate(self.volumes[id_])
            for id_ in _ids(params)
            if id_ in self.volumes
        ]


def install(monkeypatch: pytest.MonkeyPatch) -> FakeComicvine:
    """Make every simyan client built from now on this one fake."""
    fake = FakeComicvine()

    def build(**_kwargs: Any) -> FakeComicvine:
        fake.built += 1
        return fake

    monkeypatch.setattr("simyan.comicvine.Comicvine", build)
    return fake
