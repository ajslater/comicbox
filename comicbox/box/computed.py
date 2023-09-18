"""Computed metadata methods."""
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from logging import getLogger
from sys import maxsize
from typing import Optional

from comicbox.box.archive import archive_close
from comicbox.box.parse_load import ComicboxParseLoadMixin
from comicbox.fields.collections import IdentifiersField
from comicbox.fields.enum import PageTypeEnum
from comicbox.fields.fields import EMPTY_VALUES, StringField
from comicbox.fields.numbers import DecimalField
from comicbox.identifiers import (
    COMICVINE_NID,
    CV_COMIC_PREFIX,
    IDENTIFIER_EXP,
    MATCH_URLS,
    SERIES_SUFFIX,
    WEB_REGEX_URLS,
    get_web_link,
    parse_urn_identifier,
)
from comicbox.schemas.comicbox_base import (
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    ISSUE_NUMBER_KEY,
    ISSUE_SUFFIX_KEY,
    NOTES_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    PAGES_KEY,
    SCAN_INFO_KEY,
    TAGGER_KEY,
    TAGS_KEY,
    UPDATED_AT_KEY,
    WEB_KEY,
    ComicboxBaseSchema,
)
from comicbox.schemas.comictagger import ISSUE_ID_KEY, SERIES_ID_KEY, TAG_ORIGIN_KEY
from comicbox.schemas.page_info import PAGE_TYPE_KEY
from comicbox.sources import SourceFrom
from comicfn2dict.regex import ORIGINAL_FORMAT_RE

LOG = getLogger(__name__)


@dataclass
class ComputedData:
    """Computed metadata."""

    label: str
    metadata: Optional[Mapping]


class ComicboxComputedMixin(ComicboxParseLoadMixin):
    """Computed metadata methods."""

    _NOTES_RE_EXP = (
        r"(?:.*(?:by|with)\s*\b(?P<tagger>\w+\s\S+))?"
        r"(?:.*(?P<updated_at>[12]\d{3}-\d\d?-\d\d?[\sT]\d\d:\d\d:\d\d\S*))"
        r"(?:.*\[Issue ID (?P<identifier>\w+)\])?"
    )
    _NOTES_RE = re.compile(_NOTES_RE_EXP, flags=re.IGNORECASE)
    _URN_RE_EXP = r"(?P<urn>urn:.{2,}:.{2,})"
    _URN_RE = re.compile(_URN_RE_EXP)
    _NOTES_IDENTIFIER_EXTRA_EXP = r"\[" + IDENTIFIER_EXP + r"\]"
    _NOTES_IDENTIFIER_EXTRA_RE = re.compile(
        _NOTES_IDENTIFIER_EXTRA_EXP, flags=re.IGNORECASE
    )
    _NOTES_KEYS = (TAGGER_KEY, UPDATED_AT_KEY)
    _ALL_NOTES_KEYS = (*_NOTES_KEYS, IDENTIFIERS_KEY)
    _PARSE_ISSUE_MATCHER = re.compile(r"(\d*\.?\d*)(.*)")
    _PDF_IDENTIFIER_KEYWORD_PREFIX = "identifier"

    def _enable_compute_attribute(self, attr):
        """Determine if we should compute this attribute."""
        read_sources = set()
        for source, value in self._sources.items():
            from_archive = source.value.from_archive.value
            if value is not None and from_archive >= SourceFrom.ARCHIVE_CONTENTS.value:
                read_sources.add(source)
        all_sources = read_sources | self._config.all_write_sources
        for source in all_sources:
            schema = source.value.schema_class()
            if attr in schema.fields:
                return True
        return False

    def _get_computed_page_count_metadata(self, md):
        """Compute page_count from page_filenames.

        Allow for extra images in the archive that are not pages.
        """
        if not self._enable_compute_attribute(PAGE_COUNT_KEY):
            return None
        md_page_count = md.get(PAGE_COUNT_KEY)
        real_page_count = self.get_page_count()
        if md_page_count is None or md_page_count > real_page_count:
            return {PAGE_COUNT_KEY: real_page_count}
        return None

    def _ensure_pages_front_cover_metadata(self, metadata):
        """Ensure there is a FrontCover page type in pages."""
        if PAGES_KEY not in metadata:
            return
        pages = metadata[PAGES_KEY]
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

    def _get_computed_synthed_pages_metadata(self, md, pages):
        max_page_index = self._get_max_page_index()
        old_pages = md.get(PAGES_KEY, [])[:max_page_index]
        computed_pages_md = {PAGES_KEY: deepcopy(old_pages)}
        new_pages_md = {PAGES_KEY: pages}
        computed_md_list = (ComputedData("Truncated Synthed Pages", new_pages_md),)
        self.synth_metadata_list(computed_md_list, computed_pages_md)
        self._ensure_pages_front_cover_metadata(computed_pages_md)
        return computed_pages_md

    def _get_computed_pages_metadata(self, md):
        """Recompute the tag image sizes for ComicRack."""
        if not self._enable_compute_attribute(PAGES_KEY):
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
            return self._get_computed_synthed_pages_metadata(md, pages)
        return {PAGES_KEY: None}

    @staticmethod
    def _set_compute_notes_key(data, key, match, schema, md):
        if not data.get(key) and (new_value := match.group(key)):
            field = schema.fields.get(key)
            if not field:
                return
            new_value = field.deserialize(new_value)
            md[key] = new_value

    @staticmethod
    def _get_identifiers_md(data, identifiers):
        if not identifiers:
            return None
        if identifiers:
            identifiers = IdentifiersField().deserialize(identifiers)
        if not identifiers:
            return None
        old_identifiers = data.get(IDENTIFIERS_KEY, {})
        pruned_identifiers = {}
        for identifier_type, code in identifiers.items():
            if identifier_type not in old_identifiers:
                pruned_identifiers[identifier_type] = code
        if not pruned_identifiers:
            return None
        return {IDENTIFIERS_KEY: pruned_identifiers}

    @classmethod
    def _get_compute_notes_keys_comictagger(cls, notes, data, schema, md):
        identifiers = {}
        match = cls._NOTES_RE.search(notes)
        if not match:
            return identifiers
        for key in cls._NOTES_KEYS:
            cls._set_compute_notes_key(data, key, match, schema, md)
        code = match.group("identifier")
        if code:
            identifiers[COMICVINE_NID] = code
        return identifiers

    @classmethod
    def _get_compute_notes_urn_identifiers(cls, notes):
        identifiers = {}
        match = cls._URN_RE.search(notes)
        if not match:
            return identifiers
        for urn in match.groups():
            identifier_type, code = parse_urn_identifier(urn)
            if code:
                identifiers[identifier_type] = code
        return identifiers

    @classmethod
    def _get_compute_notes_extra_identifiers(cls, notes):
        identifiers = {}
        matches = cls._NOTES_IDENTIFIER_EXTRA_RE.finditer(notes)
        if not matches:
            return identifiers
        for match in matches:
            identifier_type = match.group("type")
            code = match.group("code")
            if code:
                if not identifier_type:
                    identifier_type = COMICVINE_NID
                identifiers[identifier_type] = code
        return identifiers

    def _get_computed_from_notes(self, data):
        """Parse the tagger, updated_at & identifier from notes if not already set."""
        notes = data.get(NOTES_KEY)
        if not notes:
            return None
        do_extract = False
        for key in self._ALL_NOTES_KEYS:
            if not data.get(key):
                do_extract = True
                break
        if not do_extract:
            return None

        # Extract groups for keys
        schema = ComicboxBaseSchema(path=self._path)
        md = {}
        identifiers = self._get_compute_notes_keys_comictagger(notes, data, schema, md)
        extra_identifiers = self._get_compute_notes_extra_identifiers(notes)
        identifiers.update(extra_identifiers)
        urn_identifiers = self._get_compute_notes_urn_identifiers(notes)
        identifiers.update(urn_identifiers)
        identifiers_md = self._get_identifiers_md(data, identifiers)
        if identifiers_md:
            md.update(identifiers_md)
        if not md:
            return None
        return md

    def _get_web_from_identifiers(self, data):
        if data.get(WEB_KEY):
            return None
        identifiers = data.get(IDENTIFIERS_KEY)

        for identifier_type in MATCH_URLS:
            code = identifiers.get(identifier_type)
            if not code:
                continue
            code = code.replace("-", "")
            return get_web_link(identifier_type, code)
        if (code := identifiers.get(None)) and code.startswith(CV_COMIC_PREFIX):
            code = code.removeprefix(CV_COMIC_PREFIX)
            return get_web_link(COMICVINE_NID, code)
        return None

    def _get_computed_from_identifiers(self, data):
        """Parse identifiers for web link."""
        identifiers = data.get(IDENTIFIERS_KEY)
        if not identifiers:
            return None
        md = {}
        web = self._get_web_from_identifiers(data)
        if web:
            md[WEB_KEY] = web
        if md:
            return md
        return None

    def _get_computed_from_web(self, data):
        """Parse web link for identifiers."""
        web = data.get(WEB_KEY)
        if not web:
            return None
        for identifier_type, regex in WEB_REGEX_URLS.items():
            match = regex.search(web)
            if not match:
                continue
            code = match.group("identifier")
            if not code:
                continue
            identifiers = {identifier_type: code}
            return self._get_identifiers_md(data, identifiers)
        return None

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

    def _get_computed_from_issue(self, data, **_kwargs):
        """Break parsed issue up into parts."""
        issue = data.get("issue", "")
        old_issue_number = data.get(ISSUE_NUMBER_KEY)
        old_issue_suffix = data.get(ISSUE_SUFFIX_KEY)
        md = {}
        try:
            if issue and (old_issue_number not in EMPTY_VALUES or not old_issue_suffix):
                match = self._PARSE_ISSUE_MATCHER.match(issue)
                if match:
                    self._parse_issue_match(
                        match, old_issue_number, old_issue_suffix, md
                    )
        except Exception:
            LOG.debug(f"{self._path} Error parsing issue into components: {issue}")
            raise

        return md

    def _get_computed_issue(self, data, **_kwargs):
        """Build issue from parts before dump if issue doesn't already exist."""
        issue = data.get("issue")
        if issue:
            return None
        md = {}
        # Decimal removes unspecified decimal points
        issue = str(data.get(ISSUE_NUMBER_KEY, "")) + str(
            data.get(ISSUE_SUFFIX_KEY, "")
        )
        # This is pre-dump so issue gets serialized properly next.
        issue = issue.strip()
        if issue:
            md[ISSUE_KEY] = issue
        return data

    def _get_computed_from_scan_info(self, data, **_kwargs):
        """Parse scan_info for original format info."""
        scan_info = data.get(SCAN_INFO_KEY)
        if not scan_info or data.get(ORIGINAL_FORMAT_KEY):
            return None

        match = ORIGINAL_FORMAT_RE.search(scan_info)
        if not match:
            return None
        return {ORIGINAL_FORMAT_KEY: match.group(ORIGINAL_FORMAT_KEY)}

    def _get_computed_from_tags(self, data):
        tags = data.get(TAGS_KEY)
        if not tags:
            return None
        identifiers = {}
        for tag in tags:
            identifier_type, code = parse_urn_identifier(tag)
            if code:
                identifiers[identifier_type] = code
        return self._get_identifiers_md(data, identifiers)

    def _get_computed_from_tag_origin(self, data):
        identifier_type = data.get(TAG_ORIGIN_KEY, {}).get("id")
        code = data.get(ISSUE_ID_KEY)

        identifiers = {}
        if code:
            identifiers[identifier_type] = code

        series_code = data.get(SERIES_ID_KEY)
        if series_code:
            if not identifier_type:
                identifier_type = COMICVINE_NID
            series_type = identifier_type + SERIES_SUFFIX
            identifiers[series_type] = series_code

        return self._get_identifiers_md(data, identifiers)

    _COMPUTED_ACTIONS = (
        # Order is important
        ("Page Count", _get_computed_page_count_metadata),
        ("Pages", _get_computed_pages_metadata),
        ("from issue", _get_computed_from_issue),
        ("from issue_number & issue_suffix", _get_computed_issue),
        ("from notes", _get_computed_from_notes),
        ("from tags", _get_computed_from_tags),
        ("from identifiers", _get_computed_from_identifiers),
        ("from web", _get_computed_from_web),
        ("from scan_info", _get_computed_from_scan_info),
        ("from tag_origin", _get_computed_from_tag_origin),
    )

    def _set_computed_metadata(self):
        synth_loaded_md = self.get_loaded_synthed_metadata()
        computed_list = []
        computed_synthed_md = deepcopy(dict(synth_loaded_md))

        # Compute each
        for label, method in self._COMPUTED_ACTIONS:
            md = method(self, computed_synthed_md)
            if not md:
                continue
            computed_list.append(ComputedData(label, md))
            computed_synthed_md.update(md)

        # Remove none values.
        pop_keys = []
        for key, value in computed_synthed_md.items():
            if value is None:
                pop_keys.append(key)
        for key in pop_keys:
            computed_synthed_md.pop(key, None)

        # Set values
        self._computed = tuple(computed_list)
        self._computed_synthed_metadata = computed_synthed_md

    @archive_close
    def get_computed_metadata(self):
        """Get the computed metadata for printing."""
        if not self._computed:
            self._set_computed_metadata()
        return self._computed

    def get_computed_synthed_metadata(self):
        """Get the computed synthed metadata."""
        if not self._computed_synthed_metadata:
            self._set_computed_metadata()
        return self._computed_synthed_metadata
