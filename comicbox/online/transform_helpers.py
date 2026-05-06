"""
Shared helpers for online-source transforms.

Both `MetronApiTransform` and `ComicVineApiTransform` need to convert
list-of-dicts collections into comicbox's `SimpleNamedDictField` shape
(`{name: {extra_fields}}`), parse credit/role lists, and build
identifier sub-dicts. Putting the shared logic here keeps the per-
source transforms readable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from comicbox.identifiers.identifiers import create_identifier


def named_dict(
    items: Iterable[Mapping[str, Any]] | None,
    *,
    key: str = "name",
) -> dict[str, dict]:
    """
    Convert a list of `{name, ...}` dicts into a `{name: {}}` dict.

    Used for SimpleNamedDictField targets: characters, teams, story
    arcs, locations, universes, etc.
    """
    if not items:
        return {}
    out: dict[str, dict] = {}
    for item in items:
        if not item:
            continue
        name = item.get(key)
        if not name:
            continue
        out.setdefault(str(name), {})
    return out


def named_dict_with_id(
    items: Iterable[Mapping[str, Any]] | None,
    source: str,
    id_type: str = "issue",
) -> dict[str, dict]:
    """
    Like `named_dict`, but each entry carries an `identifiers` sub-dict.

    The id field of each item maps to comicbox's IdentifiedNameSchema
    `identifiers.<source>.{key, url}`. Used where the upstream provides
    an id alongside the name (most named collections on Metron and CV).
    """
    if not items:
        return {}
    out: dict[str, dict] = {}
    for item in items:
        if not item:
            continue
        name = item.get("name")
        if not name:
            continue
        entry: dict = {}
        if (item_id := item.get("id")) is not None:
            entry["identifiers"] = {source: build_identifier(source, id_type, item_id)}
        out.setdefault(str(name), entry)
    return out


def build_identifier(source: str, id_type: str, value: Any) -> dict[str, str]:
    """Build the {key, url} sub-dict for one identifier."""
    s = str(value)
    if not s:
        return {}
    try:
        identifier = create_identifier(source, s, id_type=id_type)
    except Exception:
        return {"key": s}
    # `create_identifier` already returns a {key, url?} dict.
    return dict(identifier) or {"key": s}


_ROLE_SPLIT_RE = re.compile(r"\s*,\s*")


def parse_creator_roles(raw: str | None) -> list[str]:
    """
    Split a comma-string of role names ("writer, penciler") into a list.

    ComicVine returns creator roles as a comma-separated string;
    mokkari returns them as a list of `{id, name}` dicts so this is
    only used for the CV path. Empty / None inputs produce [].
    """
    if not raw:
        return []
    return [r.strip() for r in _ROLE_SPLIT_RE.split(raw) if r.strip()]


def _extract_role_names(roles_raw: Any, *, role_is_string: bool) -> Iterable[str]:
    """Yield role-name strings from either CV's comma-string form or mokkari's list-of-dicts."""
    if role_is_string:
        yield from parse_creator_roles(roles_raw)
        return
    if not roles_raw:
        return
    for role_item in roles_raw:
        if isinstance(role_item, Mapping) and (name := role_item.get("name")):
            yield str(name)


def credits_to_cb(
    credits_list: Iterable[Mapping[str, Any]] | None,
    *,
    creator_key: str,
    role_key: str,
    role_is_string: bool = False,
    source: str | None = None,
    creator_id_type: str = "creator",
) -> dict[str, dict]:
    """
    Convert a list of credits into comicbox's nested `credits` shape.

    The shape is `{<creator>: {roles: {<role>: {}}, identifiers: {...}}}`.

    `role_is_string=True` means `role` is a comma-separated string (CV).
    Otherwise `role` is a list of `{id, name}` dicts (mokkari).

    `source` and `creator_id_type` populate the per-creator identifiers
    sub-dict from the upstream creator id; pass None to skip.
    """
    if not credits_list:
        return {}
    out: dict[str, dict] = {}
    for credit in credits_list:
        if not credit:
            continue
        creator_name = credit.get(creator_key)
        if not creator_name:
            continue
        entry: dict = out.setdefault(str(creator_name), {})
        roles_dict: dict = entry.setdefault("roles", {})
        for role in _extract_role_names(
            credit.get(role_key), role_is_string=role_is_string
        ):
            roles_dict.setdefault(role, {})

        if (
            source
            and (creator_id := credit.get("id")) is not None
            and "identifiers" not in entry
        ):
            entry["identifiers"] = {
                source: build_identifier(source, creator_id_type, creator_id)
            }
    return out


def reprints_to_cb(
    reprints: Iterable[Mapping[str, Any]] | None,
    *,
    source: str,
) -> list[dict]:
    """
    Convert mokkari's `reprints` list into comicbox's ReprintSchema list.

    mokkari `Reprint` has `id` (Metron issue id) and `issue` (display
    string like "Series Name #N"). We pass the issue string through;
    the metron id goes into `identifiers.<source>` per ReprintSchema.
    """
    if not reprints:
        return []
    out: list[dict] = []
    for r in reprints:
        if not r:
            continue
        entry: dict = {}
        if issue := r.get("issue"):
            entry["issue"] = str(issue)
        if (rid := r.get("id")) is not None:
            entry["identifiers"] = {source: build_identifier(source, "issue", rid)}
        if entry:
            out.append(entry)
    return out
