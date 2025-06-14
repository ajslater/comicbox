"""Computed metadata methods."""

import re
from collections.abc import Callable
from types import MappingProxyType

from loguru import logger

from comicbox.box.merge import ComicboxMerge
from comicbox.fields.time_fields import DateField, DateTimeField
from comicbox.identifiers import (
    ALIAS_ID_SOURCE_MAP,
    DEFAULT_ID_SOURCE,
    ID_SOURCE_NAME_MAP,
    IDENTIFIER_RE_EXP,
)
from comicbox.identifiers.identifiers import (
    create_identifier,
)
from comicbox.identifiers.urns import (
    parse_urn_identifier_and_warn,
)
from comicbox.merge import AdditiveMerger, Merger
from comicbox.schemas.comicbox import (
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
from comicbox.schemas.comicbox.yaml import ComicboxYamlSubSchema

_DATE_KEYS = frozenset({COVER_DATE_KEY, YEAR_KEY, MONTH_KEY, DAY_KEY})
_NOTES_TAGGER_VERSION_EXP = r"(?:\s(?:dev|test|[\d\.]+\S+))?"
_NOTES_TAGGER_RE_EXP = (
    r"(?:Tagged\s(?:with|by)\s(?P<tagger>\w+" + _NOTES_TAGGER_VERSION_EXP + "))"
)
_NOTES_TAGGER_RE = re.compile(_NOTES_TAGGER_RE_EXP)
_NOTES_UPDATED_AT_RE_EXP = r"(?:\s+on\s(?P<updated_at>[12]\d{3}-[012]\d-[01]\d[\sT](?:[012]\d:\d{2}:\d{2}\S*)?))"
_NOTES_UPDATED_AT_RE = re.compile(_NOTES_UPDATED_AT_RE_EXP)
_NOTES_ORIGIN_RE_EXP = r"(?:\s+using info from (?P<origin>\w+))"
_NOTES_IDENTIFIER_RE_EXP = r"(?:\s+\[Issue ID (?P<id_key>\w+)\])"
_NOTES_RE_EXP = (
    _NOTES_TAGGER_RE_EXP
    + _NOTES_UPDATED_AT_RE_EXP
    + r"?"
    + _NOTES_ORIGIN_RE_EXP
    + r"?"
    + _NOTES_IDENTIFIER_RE_EXP
    + r"?"
)
_NOTES_RE = re.compile(_NOTES_RE_EXP, flags=re.IGNORECASE)
_URN_RE_EXP = r"(?P<urn>urn:\S{2,}:\S{2,})"
_URN_RE = re.compile(_URN_RE_EXP)
_NOTES_IDENTIFIER_EXTRA_EXP = r"\[" + IDENTIFIER_RE_EXP + r"\]"
_NOTES_IDENTIFIER_EXTRA_RE = re.compile(
    _NOTES_IDENTIFIER_EXTRA_EXP, flags=re.IGNORECASE
)
_NOTES_KEYS = (TAGGER_KEY, UPDATED_AT_KEY)
_NOTES_RELDATE_RE = re.compile(r"\[RELDATE:(?P<reldate>\S+)\]")


class ComicboxComputedNotes(ComicboxMerge):
    """Computed metadata methods for notes field."""

    def _set_computed_notes_key(self, sub_data, key, match, md):
        schema = ComicboxYamlSubSchema(path=self._path)
        if not sub_data.get(key) and (new_value := match.group(key)):
            field = schema.fields.get(key)
            if not field:
                return
            new_value = field.deserialize(new_value)
            md[key] = new_value

    def _get_computed_notes_keys_comictagger(self, notes, sub_data, md):
        identifiers = {}
        match = _NOTES_RE.search(notes)
        if not match:
            return identifiers
        for key in _NOTES_KEYS:
            self._set_computed_notes_key(sub_data, key, match, md)
        if (origin := match.group("origin")) and (
            id_source := ID_SOURCE_NAME_MAP.inverse.get(origin, origin)
        ):
            id_source = ALIAS_ID_SOURCE_MAP.get(id_source.lower(), DEFAULT_ID_SOURCE)
            if (id_key := match.group("id_key")) and (
                identifier := create_identifier(id_source, id_key)
            ):
                identifiers[id_source] = identifier
        return identifiers

    @staticmethod
    def _get_computed_notes_urn_identifiers(notes):
        identifiers = {}
        match = _URN_RE.search(notes)
        if not match:
            return identifiers
        for urn in match.groups():
            id_source, _, id_key = parse_urn_identifier_and_warn(urn)
            if id_source:
                id_source = ALIAS_ID_SOURCE_MAP.get(
                    id_source.lower(), DEFAULT_ID_SOURCE
                )
                if id_key:
                    identifier = create_identifier(id_source, id_key)
                    identifiers[id_source] = identifier
        return identifiers

    @staticmethod
    def _get_computed_notes_extra_identifiers(notes):
        identifiers = {}
        matches = _NOTES_IDENTIFIER_EXTRA_RE.finditer(notes)
        if not matches:
            return identifiers
        for match in matches:
            if id_source := match.group("id_source"):
                id_source = ALIAS_ID_SOURCE_MAP.get(
                    id_source.lower(), DEFAULT_ID_SOURCE
                )
                if (id_key := match.group("id_key")) and (
                    identifier := create_identifier(id_source, id_key)
                ):
                    identifiers[id_source] = identifier
        return identifiers

    def _set_computed_notes_identifiers(self, sub_data, notes, sub_md):
        extra_identifiers = self._get_computed_notes_extra_identifiers(notes)
        comictagger_identifiers = self._get_computed_notes_keys_comictagger(
            notes, sub_data, sub_md
        )
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
    def _get_computed_notes_date(notes):
        """Parse the date from the notes."""
        match = _NOTES_RELDATE_RE.search(notes)
        if not match:
            return None
        date_str = match.group("reldate")
        try:
            return DateField()._deserialize(date_str)  # noqa: SLF001
        except Exception:
            logger.debug(f"Unparsable RELDATE {date_str}")
        return None

    def _set_computed_notes_date(self, sub_data, notes, sub_md):
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

    def _set_computed_notes_tagger(self, sub_data, notes, sub_md):
        if sub_data.get(TAGGER_KEY):
            # Do not overwrite an explicit tagger
            return
        match = _NOTES_TAGGER_RE.search(notes)
        if not match:
            return
        match_group = match.group("tagger")
        if not match_group:
            return
        tagger = match.group("tagger").strip()
        sub_md[TAGGER_KEY] = tagger

    def _set_computed_notes_updated_at(self, sub_data, notes, sub_md):
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
        updated_at = DateTimeField()._deserialize(dttm_str)  # noqa: SLF001
        sub_md[UPDATED_AT_KEY] = updated_at

    def get_computed_from_notes(self, sub_data):
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

    COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                "from notes": (
                    get_computed_from_notes,
                    AdditiveMerger,
                )
            }
        )
    )
