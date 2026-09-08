"""
Read structured metadata back out of a free-text notes field.

Most formats have one notes field and nowhere else to put a tagger name, a
timestamp, a release date, a database id or a url, so taggers write all of
them into that prose. This module parses each of those back into its own
comicbox field.

Grammar read here
-----------------
- ``Tagged with|by <tagger>[ <version>]`` -> ``tagger``
- ``on <YYYY-MM-DD[ T]HH:MM:SS...>``      -> ``updated_at``
- ``[RELDATE:<date>]``                    -> ``date.cover_date`` + parts
- ``using info from <source>`` paired with ``[Issue ID <key>]``
  -> ``identifiers[source]``  (ComicTagger's own stamp)
- ``urn:<source>:<type>:<key>``           -> ``identifiers[source]``
- ``[<source>:<type>:<key>]``, ``[CVDB1234]`` -> ``identifiers[source]``

Urls in notes are read one step earlier, by ``url_identifiers``, because the
stamp below replaces the whole notes text and a url that lived only in that
prose would otherwise be gone.

What the tagger stamp writes back
---------------------------------
``ComicboxComputedStamp._get_computed_notes_stamp`` rebuilds notes from
scratch as ``Tagged with <tagger> on <ts> [Issue ID <comicvine key>]`` plus a
urn for every identifier. It is a projection of the structured fields, not an
edit of the text it replaces, so restamping is lossy *as text*. Each loss, and
why it is not a loss of data:

- ``[RELDATE:...]`` is not written back. The date it named was parsed into
  ``date.cover_date``/``year``/``month``/``day``, which every write format
  carries, so the date survives; only the prose spelling of it is dropped.
- Urls are not written back. ``url_identifiers`` collected them into ``urls``
  before the stamp ran, and ``urls`` is a real field.
- ``using info from <source>`` is not written back. The source it named is
  what each urn's first field says, so the fact survives in a form this
  parser can read without a second clause to pair it with.
- Bracketed ``[CVDB1234]``-style identifiers come back as urns. Different
  spelling, same source, type and key.
- ``[Issue ID <key>]`` is written for ComicVine only, for ComicTagger's
  benefit. Comicbox reads its own ids back from the urns, which cover every
  source.
- Anything else a human wrote in notes is discarded. That is the one real
  loss, and it is the point of the field being a stamp: the stamp is only
  written when the caller asks comicbox to write, convert or export.
"""

import re
from datetime import date
from typing import Any

from loguru import logger

from comicbox.box.computed.url_identifiers import ComicboxComputedUrlIdentifiers
from comicbox.enums.maps.identifiers import (
    ID_SOURCE_NAME_RE_EXP,
    get_id_source_by_alias,
)
from comicbox.formats.base.fields.time_fields import DateField, DateTimeField
from comicbox.formats.comicbox.schema import (
    COVER_DATE_KEY,
    DATE_KEY,
    DAY_KEY,
    IDENTIFIERS_KEY,
    MONTH_KEY,
    NOTES_KEY,
    TAGGER_KEY,
    UPDATED_AT_KEY,
    YEAR_KEY,
)
from comicbox.identifiers import IDENTIFIER_RE_EXP, match_id_source_str
from comicbox.identifiers.identifiers import (
    create_identifier,
)
from comicbox.identifiers.urns import (
    URN_SCAN_EXP,
    parse_urn_identifier,
)
from comicbox.merge import AdditiveMerger

_DATE_KEYS = frozenset({COVER_DATE_KEY, YEAR_KEY, MONTH_KEY, DAY_KEY})
_NOTES_TAGGER_VERSION_EXP = r"(?:\s(?:dev|test|[\d\.]+\S+))?"
_NOTES_TAGGER_RE = re.compile(
    r"(?:Tagged\s(?:with|by)\s(?P<tagger>\w+" + _NOTES_TAGGER_VERSION_EXP + "))",
    flags=re.IGNORECASE,
)
_NOTES_UPDATED_AT_RE = re.compile(
    r"(?:\s+on\s(?P<updated_at>[12]\d{3}-[012]\d-[01]\d[\sT](?:[012]\d:\d{2}:\d{2}\S*)?))",
    flags=re.IGNORECASE,
)
# Every name and alias a source answers to, so the multi-word ones ("Comic
# Vine", "Grand Comics Database", "League of Comic Geeks") match. A bare \w+
# stopped at the first space and then resolved to nothing, which made this
# whole clause dead for most of the databases comicbox knows.
_NOTES_ORIGIN_RE = re.compile(
    r"using\sinfo\sfrom\s(?P<origin>" + ID_SOURCE_NAME_RE_EXP + r")",
    flags=re.IGNORECASE,
)
# ComicTagger writes the origin and the issue id at opposite ends of its
# stamp, with the timestamp between them, so they are searched for
# separately. Both spellings are distinctive enough to stand alone.
_NOTES_ISSUE_ID_RE = re.compile(r"\[Issue ID (?P<id_key>\w+)\]", flags=re.IGNORECASE)
# One grammar for urns, owned by the urns module that reads and writes them.
# A hand-maintained copy here drifted: it accepted a one character namespace
# and a trailing hyphen that the urn parser then rejected.
_URN_RE_EXP = rf"(?P<urn>{URN_SCAN_EXP})"
_URN_RE = re.compile(_URN_RE_EXP, flags=re.IGNORECASE)
_NOTES_IDENTIFIER_EXTRA_EXP = r"\[" + IDENTIFIER_RE_EXP + r"\]"
_NOTES_IDENTIFIER_EXTRA_RE = re.compile(
    _NOTES_IDENTIFIER_EXTRA_EXP, flags=re.IGNORECASE
)
_NOTES_RELDATE_RE = re.compile(r"\[RELDATE:(?P<reldate>\S+)\]")
# Field instances are stateless parsers; one of each is enough.
_DATE_FIELD = DateField()
_DATETIME_FIELD = DateTimeField()


class ComicboxComputedNotes(ComicboxComputedUrlIdentifiers):
    """Computed metadata methods for notes field."""

    @staticmethod
    def _get_computed_notes_comictagger_identifier(notes: str) -> dict:
        """Read the source & issue id out of a ComicTagger style stamp."""
        identifiers = {}
        origin_match = _NOTES_ORIGIN_RE.search(notes)
        id_key_match = _NOTES_ISSUE_ID_RE.search(notes)
        if (
            origin_match
            and id_key_match
            # default=None: an unrecognized origin names no source. The
            # default would silently file every one of them under ComicVine.
            and (
                id_source := get_id_source_by_alias(origin_match.group("origin"), None)
            )
            and (id_key := id_key_match.group("id_key"))
            and (identifier := create_identifier(id_source.value, id_key))
        ):
            identifiers[id_source.value] = identifier
        return identifiers

    @staticmethod
    def _get_computed_notes_urn_identifiers(notes: str) -> dict:
        identifiers = {}
        for match in _URN_RE.finditer(notes):
            urn = match.group("urn")
            id_source, id_type, id_key = parse_urn_identifier(urn)
            if id_source and id_key:
                identifier = create_identifier(id_source.value, id_key, id_type=id_type)
                identifiers[id_source.value] = identifier
        return identifiers

    @staticmethod
    def _get_computed_notes_extra_identifiers(notes: str) -> dict:
        identifiers = {}
        matches = _NOTES_IDENTIFIER_EXTRA_RE.finditer(notes)
        if not matches:
            return identifiers
        for match in matches:
            if (
                (id_source_str := match_id_source_str(match))
                and (id_source := get_id_source_by_alias(id_source_str))
                and (id_key := match.group("id_key"))
                and (
                    identifier := create_identifier(
                        id_source.value,
                        id_key,
                        id_type=(match.group("id_type") or "").lower(),
                    )
                )
            ):
                identifiers[id_source.value] = identifier
        return identifiers

    def _set_computed_notes_identifiers(
        self, sub_data: dict[str, Any], notes: str, sub_md: dict[str, Any]
    ) -> None:
        extra_identifiers = self._get_computed_notes_extra_identifiers(notes)
        comictagger_identifiers = self._get_computed_notes_comictagger_identifier(notes)
        urn_identifiers = self._get_computed_notes_urn_identifiers(notes)
        explicit_identifiers = sub_data.get(IDENTIFIERS_KEY, {})
        pruned_notes_identifiers = {}
        for notes_identifiers in (
            extra_identifiers,
            comictagger_identifiers,
            urn_identifiers,
        ):
            # Ordered in replacement order.
            for id_source, identifier in notes_identifiers.items():
                if id_source not in explicit_identifiers:
                    AdditiveMerger.merge(
                        pruned_notes_identifiers, {id_source: identifier}
                    )
        if pruned_notes_identifiers:
            sub_md[IDENTIFIERS_KEY] = pruned_notes_identifiers

    @staticmethod
    def _get_computed_notes_date(notes: str) -> date | None:
        """Parse the date from the notes."""
        match = _NOTES_RELDATE_RE.search(notes)
        if not match:
            return None
        date_str = match.group("reldate")
        try:
            return _DATE_FIELD._deserialize(date_str)  # noqa: SLF001
        except Exception:
            logger.debug(f"Unparsable RELDATE {date_str}")
        return None

    def _set_computed_notes_date(
        self, sub_data: dict[str, Any], notes: str, sub_md: dict[str, Any]
    ) -> None:
        if (old_date := sub_data.get(DATE_KEY, {})) and _DATE_KEYS & frozenset(
            old_date.keys()
        ):
            # do not overwrite explicit date keys
            return
        if date := self._get_computed_notes_date(notes):
            new_date = {
                COVER_DATE_KEY: date,
                YEAR_KEY: date.year,
                MONTH_KEY: date.month,
                DAY_KEY: date.day,
            }
            new_date.update(old_date)
            sub_md[DATE_KEY] = new_date

    @staticmethod
    def _set_computed_notes_tagger(
        sub_data: dict[str, Any], notes: str, sub_md: dict[Any, Any]
    ) -> None:
        if sub_data.get(TAGGER_KEY):
            # Do not overwrite an explicit tagger
            return
        match = _NOTES_TAGGER_RE.search(notes)
        if not match:
            return
        match_group = match.group("tagger")
        if not match_group:
            return
        sub_md[TAGGER_KEY] = match_group.strip()

    @staticmethod
    def _set_computed_notes_updated_at(
        sub_data: dict[str, Any], notes: str, sub_md: dict[str, Any]
    ) -> None:
        if sub_data.get(UPDATED_AT_KEY):
            # Do not overwrite an explicit updated_at
            return
        match = _NOTES_UPDATED_AT_RE.search(notes)
        if not match:
            return
        match_group = match.group("updated_at")
        if not match_group:
            return
        dttm_str = match_group.strip()
        # The pattern admits impossible dates ("2020-19-19"), which the field
        # warns about and returns None for. Writing that None back would
        # replace a missing updated_at with an explicitly null one.
        if updated_at := _DATETIME_FIELD._deserialize(dttm_str):  # noqa: SLF001
            sub_md[UPDATED_AT_KEY] = updated_at

    def get_computed_from_notes(self, sub_data: dict[str, Any]) -> dict | None:
        """Parse the tagger, updated_at & identifier from notes if not already set."""
        if not sub_data:
            return None
        notes = sub_data.get(NOTES_KEY)
        if not notes:
            return None

        # Extract groups for keys
        sub_md = {}
        self._set_computed_notes_tagger(sub_data, notes, sub_md)
        self._set_computed_notes_updated_at(sub_data, notes, sub_md)
        self._set_computed_notes_date(sub_data, notes, sub_md)
        self._set_computed_notes_identifiers(sub_data, notes, sub_md)
        if not sub_md:
            return None
        return sub_md
