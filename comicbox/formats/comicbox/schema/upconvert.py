"""
Read comicbox v2.0 documents into the v3.0 shape.

Comicbox and its clients ship paired, so there are no compatibility shims
past this one: a v2 document is converted once, on the way in, and
everything downstream sees v3 only.

Every rule is guarded on the key it converts and is idempotent, so this runs
unconditionally rather than trusting a version marker. YAML documents carry
no version at all, and the ``schema`` key in JSON is a Constant that reports
v3 once loaded — only the raw pre-load data can be trusted, which is where
this runs.
"""

from collections.abc import Mapping
from typing import Any

from comicfn2dict.unparse import dict2comicfn
from loguru import logger

from comicbox.constants import ROOT_TAG
from comicbox.enums.comicbox import MangaEnum, ReadingDirectionEnum

_V2_MANGA_YES_RTL = "YesAndRightToLeft"
_REMOVED_KEYS = ("alternate_images", "critical_rating")
# Every place a v2 identifiers map could appear.
_IDENTIFIED_KEYS = ("imprint", "publisher", "series")
_IDENTIFIED_MAP_KEYS = (
    "arcs",
    "characters",
    "credits",
    "genres",
    "locations",
    "stories",
    "tags",
    "teams",
    "universes",
)


def _strip_identifier_urls(identifiers: Any) -> list[str]:
    """Take the urls out of an identifiers map, returning them in order."""
    if not isinstance(identifiers, dict):
        return []
    return [
        str(url)
        for identifier in identifiers.values()
        if isinstance(identifier, dict) and (url := identifier.pop("url", None))
    ]


def _drop_hostname_identifiers(identifiers: Any) -> None:
    """
    Drop identifiers v2 invented from a url's hostname.

    They were keyed by netloc, like ``bar.foo``, and named no database
    anything could look up. Their urls are kept.
    """
    if not isinstance(identifiers, dict):
        return
    for id_source in [key for key in identifiers if "." in str(key)]:
        del identifiers[id_source]


def _upconvert_primary_source(sub_data: dict[str, Any]) -> None:
    """Collapse the primary source object to the source string it named."""
    ips = sub_data.pop("identifier_primary_source", None)
    # Its url was synthesized from the source, never read from a file.
    if isinstance(ips, Mapping) and (id_source := ips.get("source")):
        sub_data.setdefault("primary_id_source", id_source)


def _strip_tag_urls(all_tags: Any) -> list[str]:
    """Take the urls out of a name-keyed tag map, credit roles included."""
    urls: list[str] = []
    if not isinstance(all_tags, dict):
        return urls
    for tag in all_tags.values():
        if not isinstance(tag, dict):
            continue
        urls += _strip_identifier_urls(tag.get("identifiers"))
        if isinstance(roles := tag.get("roles"), dict):
            for role in roles.values():
                if isinstance(role, dict):
                    urls += _strip_identifier_urls(role.get("identifiers"))
    return urls


def _strip_reprint_urls(reprints: Any) -> list[str]:
    """Take the urls out of the reprints list."""
    if not isinstance(reprints, list):
        return []
    urls: list[str] = []
    for reprint in reprints:
        if isinstance(reprint, dict):
            urls += _strip_identifier_urls(reprint.get("identifiers"))
    return urls


def _upconvert_identifiers(sub_data: dict[str, Any]) -> None:
    """Move urls out of every identifiers map into the top level urls list."""
    _upconvert_primary_source(sub_data)

    urls = _strip_identifier_urls(sub_data.get("identifiers"))
    _drop_hostname_identifiers(sub_data.get("identifiers"))
    for key in _IDENTIFIED_KEYS:
        if isinstance(value := sub_data.get(key), dict):
            urls += _strip_identifier_urls(value.get("identifiers"))
    for key in _IDENTIFIED_MAP_KEYS:
        urls += _strip_tag_urls(sub_data.get(key))
    urls += _strip_reprint_urls(sub_data.get("reprints"))

    if not urls:
        return
    old_urls = (str(url) for url in sub_data.get("urls") or ())
    sub_data["urls"] = list(dict.fromkeys([*old_urls, *urls]))


def _upconvert_credit_primaries(sub_data: dict[str, Any]) -> None:
    """Fold the flat {role: person} map onto each person's role."""
    credit_primaries = sub_data.pop("credit_primaries", None)
    if not isinstance(credit_primaries, Mapping):
        return
    credits_md = sub_data.get("credits")
    if not isinstance(credits_md, dict):
        return
    for role_name, person_name in credit_primaries.items():
        person = credits_md.get(person_name)
        if not isinstance(person, dict):
            continue
        roles = person.get("roles")
        if isinstance(roles, dict) and isinstance(roles.get(role_name), dict):
            roles[role_name]["primary"] = True


def _upconvert_manga(sub_data: dict[str, Any]) -> None:
    """Split the compound manga value into manga and reading_direction."""
    if sub_data.get("manga") != _V2_MANGA_YES_RTL:
        return
    sub_data["manga"] = MangaEnum.YES.value
    sub_data.setdefault("reading_direction", ReadingDirectionEnum.RTL.value)


def _upconvert_reprints(sub_data: dict[str, Any]) -> None:
    """Give a structured v2 reprint the name v3 stores it under."""
    reprints = sub_data.get("reprints")
    if not isinstance(reprints, list):
        return
    for reprint in reprints:
        if not isinstance(reprint, dict) or reprint.get("name"):
            continue
        # The same fields the reprint transform builds a name from. Spelled
        # out rather than imported: the transform package imports this
        # schema package.
        series = reprint.get("series") or {}
        volume = reprint.get("volume") or {}
        filename_dict = {
            "series": series.get("name"),
            "volume": volume.get("number"),
            "issue_count": volume.get("issue_count"),
            "issue": reprint.get("issue"),
        }
        filename_dict = {k: v for k, v in filename_dict.items() if v is not None}
        if name := dict2comicfn(filename_dict, ext=False):
            reprint["name"] = name


def upconvert_v2(data: Any) -> Any:
    """Convert a comicbox v2.0 document to the v3.0 shape."""
    if not isinstance(data, Mapping):
        return data
    sub_data = data.get(ROOT_TAG)
    if not isinstance(sub_data, dict):
        return data
    try:
        for key in _REMOVED_KEYS:
            sub_data.pop(key, None)
        _upconvert_identifiers(sub_data)
        _upconvert_credit_primaries(sub_data)
        _upconvert_manga(sub_data)
        _upconvert_reprints(sub_data)
    except Exception as exc:
        # pre_load traps exceptions into warnings, which would leave a half
        # converted document looking valid.
        logger.warning(f"Converting comicbox v2 metadata: {exc}")
    return data
