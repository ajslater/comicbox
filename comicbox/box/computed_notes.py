"""Computed metadata methods."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from logging import getLogger

from comicbox.box.normalize import ComicboxNormalizeMixin
from comicbox.fields.time_fields import DateField, DateTimeField
from comicbox.identifiers import (
    COMICVINE_NID,
    IDENTIFIER_EXP,
    IDENTIFIER_URN_NIDS_REVERSE_MAP,
    NID_ORIGIN_MAP,
    create_identifier,
    parse_urn_identifier,
)
from comicbox.schemas.comicbox_mixin import (
    DATE_KEY,
    DAY_KEY,
    IDENTIFIERS_KEY,
    MONTH_KEY,
    NOTES_KEY,
    TAGGER_KEY,
    UPDATED_AT_KEY,
    YEAR_KEY,
)
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.schemas.identifier import NSS_KEY, URL_KEY

LOG = getLogger(__name__)
_DATE_KEYS = frozenset({DATE_KEY, YEAR_KEY, MONTH_KEY, DAY_KEY})
_NOTES_TAGGER_VERSION_EXP = r"(?:\s(?:dev|test|[\d\.]+\S+))?"
_NOTES_TAGGER_RE_EXP = (
    r"(?:Tagged\s(?:with|by)\s(?P<tagger>\w+" + _NOTES_TAGGER_VERSION_EXP + "))"
)
_NOTES_TAGGER_RE = re.compile(_NOTES_TAGGER_RE_EXP)
_NOTES_UPDATED_AT_RE_EXP = r"(?:\s+on\s(?P<updated_at>[12]\d{3}-[012]\d-[01]\d[\sT](?:[012]\d:\d{2}:\d{2}\S*)?))"
_NOTES_UPDATED_AT_RE = re.compile(_NOTES_UPDATED_AT_RE_EXP)
_NOTES_ORIGIN_RE_EXP = r"(?:\s+using info from (?P<origin>\w+))"
_NOTES_IDENTIFIER_RE_EXP = r"(?:\s+\[Issue ID (?P<identifier>\w+)\])"
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
_NOTES_IDENTIFIER_EXTRA_EXP = r"\[" + IDENTIFIER_EXP + r"\]"
_NOTES_IDENTIFIER_EXTRA_RE = re.compile(
    _NOTES_IDENTIFIER_EXTRA_EXP, flags=re.IGNORECASE
)
_NOTES_KEYS = (TAGGER_KEY, UPDATED_AT_KEY)
_ALL_NOTES_KEYS = (*_NOTES_KEYS, IDENTIFIERS_KEY)
_NOTES_RELDATE_RE = re.compile(r"[RELDATE:(.\S)]")


@dataclass
class ComputedData:
    """Computed metadata."""

    label: str
    metadata: Mapping | None


class ComicboxComputedNotesMixin(ComicboxNormalizeMixin):
    """Computed metadata methods for notes field."""

    def _set_compute_notes_key(self, data, key, match, md):
        schema = ComicboxYamlSchema(path=self._path)
        if not data.get(key) and (new_value := match.group(key)):
            field = schema.fields.get(key)
            if not field:
                return
            new_value = field.deserialize(new_value)
            md[key] = new_value

    @staticmethod
    def merge_identifiers_md(sub_data, identifiers):
        """Return only new identifiers."""
        if not identifiers:
            return None
        old_identifiers = frozenset(sub_data.get(IDENTIFIERS_KEY, {}).keys())
        pruned_identifiers = {}
        for nid, identifier in identifiers.items():
            canon_nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), COMICVINE_NID)
            if canon_nid in old_identifiers:
                # Do NOT replace identifiers.
                continue
            if nid not in pruned_identifiers:
                pruned_identifiers[canon_nid] = {}
            nss = identifier.get(NSS_KEY)
            url = identifier.get(URL_KEY)
            new_identifier = create_identifier(canon_nid, nss, url)
            pruned_identifiers[canon_nid] = new_identifier
            pruned_identifiers[canon_nid][URL_KEY] = url
        if not pruned_identifiers:
            return None
        return {IDENTIFIERS_KEY: pruned_identifiers}

    def _get_compute_notes_keys_comictagger(self, notes, data, md):
        identifiers = {}
        match = _NOTES_RE.search(notes)
        if not match:
            return identifiers
        for key in _NOTES_KEYS:
            self._set_compute_notes_key(data, key, match, md)
        nss = match.group("identifier")
        if nss:
            origin = match.group("origin")
            nid = NID_ORIGIN_MAP.inverse.get(origin, COMICVINE_NID)
            identifier = create_identifier(nid, nss)
            if identifier:
                identifiers[nid] = identifier
        return identifiers

    @staticmethod
    def _get_compute_notes_urn_identifiers(notes):
        identifiers = {}
        match = _URN_RE.search(notes)
        if not match:
            return identifiers
        for urn in match.groups():
            nid, nss = parse_urn_identifier(urn, warn=True)
            if nid:
                nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), COMICVINE_NID)
                if nss:
                    identifier = create_identifier(nid, nss)
                    identifiers[nid] = identifier
        return identifiers

    @staticmethod
    def _get_compute_notes_extra_identifiers(notes):
        identifiers = {}
        matches = _NOTES_IDENTIFIER_EXTRA_RE.finditer(notes)
        if not matches:
            return identifiers
        for match in matches:
            nss = match.group("nss")
            if nss and (nid := match.group("type")):
                nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), COMICVINE_NID)
                identifier = create_identifier(nid, nss)
                identifiers[nid] = identifier
        return identifiers

    def _set_computed_notes_identifiers(self, sub_data, notes, sub_md):
        identifiers = self._get_compute_notes_keys_comictagger(notes, sub_data, sub_md)
        extra_identifiers = self._get_compute_notes_extra_identifiers(notes)
        identifiers.update(extra_identifiers)
        urn_identifiers = self._get_compute_notes_urn_identifiers(notes)
        identifiers.update(urn_identifiers)
        identifiers_md = self.merge_identifiers_md(sub_data, identifiers)
        if identifiers_md:
            sub_md.update(identifiers_md)

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
            LOG.debug(f"Unparsable RELDATE {date_str}")
            return None

    def _set_computed_notes_date(self, sub_data, notes, sub_md):
        if frozenset(_DATE_KEYS | frozenset(sub_data.keys())):
            return
        date = self._get_computed_notes_date(notes)
        if date:
            if DATE_KEY not in sub_data:
                sub_md[DATE_KEY] = date
            if YEAR_KEY not in sub_data:
                sub_md[YEAR_KEY] = date.year
            if MONTH_KEY not in sub_data:
                sub_md[MONTH_KEY] = date.month
            if DAY_KEY not in sub_data:
                sub_md[DAY_KEY] = date.day

    def _set_computed_notes_tagger(self, sub_data, notes, sub_md):
        if sub_data.get(TAGGER_KEY):
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
        do_extract = False
        for key in _ALL_NOTES_KEYS:
            if not sub_data.get(key):
                do_extract = True
                break
        if not do_extract:
            return None

        # Extract groups for keys
        sub_md = {}
        self._set_computed_notes_tagger(sub_data, notes, sub_md)
        self._set_computed_notes_updated_at(sub_data, notes, sub_md)
        self._set_computed_notes_date(sub_data, notes, sub_md)
        self._set_computed_notes_identifiers(sub_data, notes, sub_md)
        return sub_md
