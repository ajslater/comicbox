"""Computed metadata methods."""

import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from logging import getLogger
from sys import maxsize
from types import MappingProxyType

from comicfn2dict.regex import ORIGINAL_FORMAT_RE

from comicbox.box.archive import archive_close
from comicbox.box.normalize import ComicboxNormalizeMixin
from comicbox.dict_funcs import deep_update
from comicbox.fields.enum import PageTypeEnum
from comicbox.fields.fields import EMPTY_VALUES, StringField
from comicbox.fields.numbers import DecimalField
from comicbox.fields.time import DateField, DateTimeField
from comicbox.identifiers import (
    COMICVINE_NID,
    IDENTIFIER_EXP,
    IDENTIFIER_URN_NIDS_REVERSE_MAP,
    create_identifier,
    parse_urn_identifier,
    to_urn_string,
)
from comicbox.schemas.comicbox_mixin import (
    DATE_KEY,
    DAY_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    ISSUE_NUMBER_KEY,
    ISSUE_SUFFIX_KEY,
    MONTH_KEY,
    NOTES_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    PAGE_TYPE_KEY,
    PAGES_KEY,
    ROOT_TAG,
    SCAN_INFO_KEY,
    TAGGER_KEY,
    TAGS_KEY,
    UPDATED_AT_KEY,
    YEAR_KEY,
)
from comicbox.schemas.comicbox_yaml import ComicboxYamlSchema
from comicbox.schemas.comictagger import ISSUE_ID_KEY, SERIES_ID_KEY, TAG_ORIGIN_KEY
from comicbox.schemas.identifier import NSS_KEY, URL_KEY
from comicbox.sources import SourceFrom

LOG = getLogger(__name__)
_DATE_KEYS = frozenset({DATE_KEY, YEAR_KEY, MONTH_KEY, DAY_KEY})
_NOTES_RE_EXP = (
    r"(?:.*(?:by|with)\s*\b(?P<tagger>\w+\s\S+))?"
    r"(?:.*(?P<updated_at>[12]\d{3}-\d\d?-\d\d?[\sT]\d\d:\d\d:\d\d\S*))"
    r"(?:.*\[Issue ID (?P<identifier>\w+)\])?"
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
_PARSE_ISSUE_MATCHER = re.compile(r"(\d*\.?\d*)(.*)")
_PAGE_COUNT_KEYS = frozenset({"PageCount", PAGE_COUNT_KEY, "pages"})
_PAGES_KEYS = frozenset({"Pages", PAGES_KEY})
_NOTES_RELDATE_RE = re.compile(r"[RELDATE:(.\S)]")
_NOTES_TAGGER_RE = re.compile(r"Tagged (with|by)\b(?P<tagger>.*)\b(using|on)")
_NOTES_UPDATED_AT_RE = re.compile(
    r"on\s(?P<updated_at>\d{2,4}-[01]\d-[0-3]\d[T\s:][0-2]\d:[0-5]\d:[0-5]\d)(.\d+)?\.?"
)


@dataclass
class ComputedData:
    """Computed metadata."""

    label: str
    metadata: Mapping | None


class ComicboxComputedMixin(ComicboxNormalizeMixin):
    """Computed metadata methods."""

    def _get_all_sources(self):
        read_sources = set()
        for source, value in self._sources.items():
            from_archive = source.value.from_archive.value
            if value is not None and from_archive >= SourceFrom.ARCHIVE_CONTENTS.value:
                read_sources.add(source)
        return read_sources | self._config.all_write_sources

    def _enable_page_compute_attribute(self, valid_keys, sub_md, attr):
        """Determine if we should compute this attribute."""
        if not self._path or not self._config.compute_pages:
            # Cannot compute pages if there's no path.
            return False

        if self._archive_is_pdf:
            if attr == "has_page_count":
                return True
            if attr == "has_pages":
                return False

        if valid_keys | sub_md.keys():
            # If there's page keys at all, then compute.
            return True

        # If the enabled source types have page keys then compute.
        if self._all_sources is None:
            # cache all sources
            self._all_sources = self._get_all_sources()
        return any(getattr(source.value, attr) for source in self._all_sources)

    def _get_computed_page_count_metadata(self, sub_md):
        """Compute page_count from page_filenames.

        Allow for extra images in the archive that are not pages.
        """
        if not self._enable_page_compute_attribute(
            _PAGE_COUNT_KEYS, sub_md, "has_page_count"
        ):
            return None
        if not sub_md:
            return None
        md_page_count = sub_md.get(PAGE_COUNT_KEY)
        real_page_count = self.get_page_count()
        if md_page_count is None or md_page_count > real_page_count:
            return {PAGE_COUNT_KEY: real_page_count}
        return None

    def _ensure_pages_front_cover_metadata(self, sub_md):
        """Ensure there is a FrontCover page type in pages."""
        pages = sub_md.get(PAGES_KEY)
        if not pages:
            return
        for page in pages:
            if page.get(PAGE_TYPE_KEY) == PageTypeEnum.FRONT_COVER:
                return

        pages[0][PAGE_TYPE_KEY] = PageTypeEnum.FRONT_COVER

    def _get_max_page_index(self):
        if self._path:
            max_page_index = self.get_page_count() - 1
        else:
            # don't strip pages if no path given
            LOG.debug("No path given, not computing real pages.")
            max_page_index = maxsize
        return max_page_index

    def _get_computed_merged_pages_metadata(self, md, pages):
        max_page_index = self._get_max_page_index()
        old_pages = md.get(PAGES_KEY, [])[:max_page_index]
        computed_pages_sub_md = {PAGES_KEY: deepcopy(old_pages)}
        new_pages_sub_md = {PAGES_KEY: pages}
        computed_md_list = (ComputedData("Truncated Merged Pages", new_pages_sub_md),)
        self.merge_metadata_list(computed_md_list, computed_pages_sub_md)
        self._ensure_pages_front_cover_metadata(computed_pages_sub_md)
        return computed_pages_sub_md

    def _get_computed_pages_metadata(self, sub_md):
        """Recompute the tag image sizes for the ComicRack PageInfo list."""
        if not self._enable_page_compute_attribute(_PAGES_KEYS, sub_md, "has_pages"):
            return None
        pages = []
        try:
            index = 0
            infolist = self._get_archive_infolist()
            for info in infolist:
                filename = self._get_info_fn(info)
                if self.IMAGE_EXT_RE.search(filename) is None:
                    continue
                size = self._get_info_size(info)
                # height & width could go here.
                computed_page = {"index": index, "size": size}
                pages.append(computed_page)
                index += 1
        except Exception as exc:
            LOG.warning(f"{self._path}: Compute pages metadata: {exc}")
        if pages:
            return self._get_computed_merged_pages_metadata(sub_md, pages)
        return {PAGES_KEY: None}

    def _set_compute_notes_key(self, data, key, match, md):
        schema = ComicboxYamlSchema(path=self._path)
        if not data.get(key) and (new_value := match.group(key)):
            field = schema.fields.get(key)
            if not field:
                return
            new_value = field.deserialize(new_value)
            md[key] = new_value

    @staticmethod
    def _merge_identifiers_md(sub_data, identifiers):
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
            nid = COMICVINE_NID
            identifier = create_identifier(nid, nss)
            identifiers[nid] = identifier
        return identifiers

    @staticmethod
    def _get_compute_notes_urn_identifiers(notes):
        identifiers = {}
        match = _URN_RE.search(notes)
        if not match:
            return identifiers
        for urn in match.groups():
            nid, nss = parse_urn_identifier(urn)
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
        identifiers_md = self._merge_identifiers_md(sub_data, identifiers)
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
        tagger = match.group("tagger").strip()
        sub_md[TAGGER_KEY] = tagger

    def _set_computed_notes_updated_at(self, sub_data, notes, sub_md):
        if sub_data.get(UPDATED_AT_KEY):
            return
        match = _NOTES_UPDATED_AT_RE.search(notes)
        if not match:
            return
        dttm_str = match.group("updated_at").strip()
        updated_at = DateTimeField()._deserialize(dttm_str)  # noqa: SLF001
        sub_md[UPDATED_AT_KEY] = updated_at

    def _get_computed_from_notes(self, sub_data):
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

    def _parse_issue_match(self, match, old_issue_number, old_issue_suffix, md):
        """Use regex match to break the issue into parts."""
        issue_number, issue_suffix = match.groups()
        if old_issue_number in EMPTY_VALUES and issue_number not in EMPTY_VALUES:
            try:
                issue_number = DecimalField().deserialize(
                    issue_number, ISSUE_NUMBER_KEY, md
                )
                md[ISSUE_NUMBER_KEY] = issue_number
            except Exception as exc:
                LOG.warning(f"{self._path} Parsing issue_number from issue {exc}")
        if not old_issue_suffix and issue_suffix:
            md[ISSUE_SUFFIX_KEY] = StringField().deserialize(
                issue_suffix, ISSUE_SUFFIX_KEY, md
            )

    def _get_computed_from_issue(self, sub_data, **_kwargs):
        """Break parsed issue up into parts."""
        if not sub_data:
            return None
        issue = sub_data.get("issue", "")
        old_issue_number = sub_data.get(ISSUE_NUMBER_KEY)
        old_issue_suffix = sub_data.get(ISSUE_SUFFIX_KEY)
        sub_md = {}
        try:
            if issue and (old_issue_number not in EMPTY_VALUES or not old_issue_suffix):
                match = _PARSE_ISSUE_MATCHER.match(issue)
                if match:
                    self._parse_issue_match(
                        match, old_issue_number, old_issue_suffix, sub_md
                    )
        except Exception:
            LOG.debug(f"{self._path} Error parsing issue into components: {issue}")
            raise

        return sub_md

    def _get_computed_issue(self, sub_data, **_kwargs):
        """Build issue from parts before dump if issue doesn't already exist."""
        if not sub_data:
            return None
        issue = sub_data.get("issue")
        if issue:
            return None
        sub_md = {}
        # Decimal removes unspecified decimal points
        issue = str(sub_data.get(ISSUE_NUMBER_KEY, "")) + str(
            sub_data.get(ISSUE_SUFFIX_KEY, "")
        )
        # This is pre-dump so issue gets serialized properly next.
        issue = issue.strip()
        if issue:
            sub_md[ISSUE_KEY] = issue
        return sub_md

    def _get_computed_from_scan_info(self, sub_data, **_kwargs):
        """Parse scan_info for original format info."""
        if not sub_data:
            return None
        scan_info = sub_data.get(SCAN_INFO_KEY)
        if not scan_info or sub_data.get(ORIGINAL_FORMAT_KEY):
            return None

        match = ORIGINAL_FORMAT_RE.search(scan_info)
        if not match:
            return None
        return {ORIGINAL_FORMAT_KEY: match.group(ORIGINAL_FORMAT_KEY)}

    def _get_computed_from_tags(self, sub_data):
        if not sub_data:
            return None

        tags = sub_data.get(TAGS_KEY)
        if not tags:
            return None
        identifiers = {}
        for tag in tags:
            # Silently fail because most tags are not urns
            nid, nss = parse_urn_identifier(tag, warn=False)
            if nid:
                nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), COMICVINE_NID)
                if nss:
                    identifiers[nid] = create_identifier(nid, nss)
        return self._merge_identifiers_md(sub_data, identifiers)

    def _get_computed_from_identifiers(self, sub_data):
        identifiers = sub_data.get(IDENTIFIERS_KEY, {})
        if not identifiers:
            return None
        new_identifiers = {}
        for nid, identifier in identifiers.items():
            if identifier.get(URL_KEY):
                continue
            if nss := identifier.get(NSS_KEY):
                new_identifier = create_identifier(nid, nss)
                new_identifiers[nid] = new_identifier
        if new_identifiers:
            return {IDENTIFIERS_KEY: new_identifiers}
        return None

    def _get_computed_from_tag_origin(self, sub_data):
        # Should this pop or should it pop on ct post load?
        if not sub_data:
            return None
        nid = sub_data.pop(TAG_ORIGIN_KEY, {}).get("id", COMICVINE_NID)
        nss = sub_data.pop(ISSUE_ID_KEY, None)

        identifiers = {}
        if nss:
            identifiers[nid] = nss

        series_nss = sub_data.pop(SERIES_ID_KEY, None)
        if series_nss:
            identifiers[nid] = series_nss

        return self._merge_identifiers_md(sub_data, identifiers)

    # Tagger Stamp
    def _get_unparsed_comictagger_style_notes(self, sub_data):
        """Build notes from other tags."""
        notes = ""
        if tagger := sub_data.get(TAGGER_KEY):
            notes += f"Tagged with {tagger}"

        if updated_at := sub_data.get(UPDATED_AT_KEY):
            field = DateTimeField()
            ts = field._serialize(updated_at)  # noqa: SLF001
            if ts:
                notes += f" on {ts}"

        if (
            comicvine_id := sub_data.get(IDENTIFIERS_KEY, {})
            .get(COMICVINE_NID, {})
            .get(NSS_KEY)
        ):
            notes += f" [Issue ID {comicvine_id}]"
        return notes

    def _get_unparsed_urns_for_notes(self, sub_data):
        """Unparse all types."""
        notes = ""
        identifiers = sub_data.get(IDENTIFIERS_KEY)
        if not identifiers:
            return notes
        urn_strs = []
        for nid, identifier in identifiers.items():
            nss = identifier.get(NSS_KEY)
            if not nss:
                continue
            urn_str = to_urn_string(nid, nss)
            urn_strs.append(urn_str)
        notes += " ".join(sorted(urn_strs))
        return notes

    def _get_computed_notes_stamp(self, sub_data, md):
        """Write comicbox notes to notes field if present."""
        if not self._config.stamp_notes:
            return None
        data_copy = deepcopy(md)
        if identifiers := sub_data.get(IDENTIFIERS_KEY):
            data_copy[IDENTIFIERS_KEY] = identifiers

        comictagger_style_notes = self._get_unparsed_comictagger_style_notes(data_copy)
        urn_notes = self._get_unparsed_urns_for_notes(data_copy)
        notes = " ".join((comictagger_style_notes, urn_notes))
        return notes.strip()

    def _get_tagger_stamp(self, sub_data):
        """Stamp when writing."""
        if not self._config.all_write_sources:
            # Only stamp on write.
            return None

        # tagger & updated_at
        md = {
            TAGGER_KEY: self._config.tagger,
            # Deprecated method needed for python 3.10
            UPDATED_AT_KEY: datetime.utcnow(),  # noqa: DTZ003, type: ignore
        }

        # notes
        if notes := self._get_computed_notes_stamp(sub_data, md):
            md[NOTES_KEY] = notes

        return md

    _COMPUTED_ACTIONS = (
        # Order is important
        ("Page Count", _get_computed_page_count_metadata, True),
        ("Pages", _get_computed_pages_metadata, True),
        ("from issue", _get_computed_from_issue, False),
        ("from issue_number & issue_suffix", _get_computed_issue, False),
        ("from notes", _get_computed_from_notes, False),
        ("from tags", _get_computed_from_tags, False),
        ("from identifiers", _get_computed_from_identifiers, False),
        ("from scan_info", _get_computed_from_scan_info, False),
        ("from tag_origin", _get_computed_from_tag_origin, False),
        ("Tagger Stamp", _get_tagger_stamp, True),
    )

    def _set_computed_metadata(self):
        computed_list = []
        merged_md = self.get_merged_metadata()
        computed_merged_md = deepcopy(dict(merged_md))
        sub_data = computed_merged_md.get(ROOT_TAG, {})

        # Compute each
        for label, method, update in self._COMPUTED_ACTIONS:
            sub_md = method(self, sub_data)
            if not sub_md:
                continue

            md = {ROOT_TAG: sub_md}
            computed_list.append(ComputedData(label, md))
            if update:
                deep_update(sub_data, sub_md)
            else:
                self.merge_metadata(sub_data, sub_md)

        # Remove none values.
        pop_keys = []
        for key, value in sub_data.items():
            if value is None:
                pop_keys.append(key)
        for key in pop_keys:
            sub_data.pop(key, None)

        # Set values
        self._computed = tuple(computed_list)
        if computed_merged_md:
            self._computed_merged_metadata = MappingProxyType(computed_merged_md)

    @archive_close
    def get_computed_metadata(self):
        """Get the computed metadata for printing."""
        if not self._computed:
            self._set_computed_metadata()
        return self._computed

    def get_computed_merged_metadata(self):
        """Get the computed merged metadata."""
        if not self._computed_merged_metadata:
            self._set_computed_metadata()
        return self._computed_merged_metadata
