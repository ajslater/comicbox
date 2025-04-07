"""Computed metadata methods."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from logging import getLogger
from sys import maxsize
from types import MappingProxyType

from comicfn2dict.regex import ORIGINAL_FORMAT_RE
from deepdiff import DeepDiff

from comicbox.box.archive import archive_close
from comicbox.box.computed_notes import ComicboxComputedNotesMixin
from comicbox.empty import is_empty
from comicbox.fields.enum_fields import PageTypeEnum
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import DecimalField
from comicbox.fields.time_fields import DateTimeField
from comicbox.formats import MetadataFormats
from comicbox.identifiers import (
    COMICVINE_NID,
    DEFAULT_NID,
    NID_ORDER,
    NSS_KEY,
    URL_KEY,
    create_identifier,
)
from comicbox.merge import AdditiveMerger, Merger, ReplaceMerger
from comicbox.schemas.comicbox import (
    IDENTIFIER_PRIMARY_SOURCE_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    ISSUE_SUFFIX_KEY,
    NAME_KEY,
    NOTES_KEY,
    NUMBER_KEY,
    ORIGINAL_FORMAT_KEY,
    PAGE_COUNT_KEY,
    PAGE_TYPE_KEY,
    PAGES_KEY,
    REPRINTS_KEY,
    SCAN_INFO_KEY,
    TAGGER_KEY,
    TAGS_KEY,
    UPDATED_AT_KEY,
    ComicboxSchemaMixin,
)
from comicbox.schemas.comictagger import ISSUE_ID_KEY, SERIES_ID_KEY, TAG_ORIGIN_KEY
from comicbox.transforms.identifiers import create_identifier_primary_source
from comicbox.urns import (
    IDENTIFIER_URN_NIDS_REVERSE_MAP,
    parse_urn_identifier,
    to_urn_string,
)

NUMBER_KEYPATH = f"{ISSUE_KEY}.{NUMBER_KEY}"
ISSUE_SUFFIX_KEYPATH = f"{ISSUE_KEY}.{ISSUE_SUFFIX_KEY}"
_PARSE_ISSUE_MATCHER = re.compile(r"(\d*\.?\d*)(.*)")
_COMICBOX_FORMATS = frozenset(
    {
        MetadataFormats.COMICBOX_CLI_YAML,
        MetadataFormats.COMICBOX_YAML,
        MetadataFormats.COMICBOX_JSON,
    }
)
LOG = getLogger(__name__)


class ComputeSchemaAttribute(Enum):
    """Schema attributes that control weather or not to compute entries."""

    HAS_PAGE_COUNT = "HAS_PAGE_COUNT"
    HAS_PAGES = "HAS_PAGES"


@dataclass
class ComputedData:
    """Computed metadata."""

    label: str
    metadata: Mapping | None
    merger: type[Merger] | None = AdditiveMerger


class ComicboxComputedMixin(ComicboxComputedNotesMixin):
    """Computed metadata methods."""

    def _enable_page_compute_attribute(self, attr: ComputeSchemaAttribute):
        """Determine if we should compute this attribute."""
        if not self._path or not self._config.compute_pages:
            # Cannot compute pages if there's no path.
            return False

        formats = self._config.all_write_formats
        if attr == ComputeSchemaAttribute.HAS_PAGES:
            formats = formats - _COMICBOX_FORMATS
        elif attr == ComputeSchemaAttribute.HAS_PAGE_COUNT:
            read_formats = set()

            for loaded_list in self._loaded.values():
                for loaded in loaded_list:
                    read_formats.add(loaded.fmt)
            formats |= read_formats

        # If the enabled format types have page flags then compute.
        return any(getattr(fmt.value.schema_class, attr.value) for fmt in formats)

    def _get_computed_page_count_metadata(self, sub_md):
        """
        Compute page_count from page_filenames.

        Allow for extra images in the archive that are not pages.
        """
        if PAGE_COUNT_KEY in self._config.delete_keys:
            return None
        if not sub_md or not self._enable_page_compute_attribute(
            ComputeSchemaAttribute.HAS_PAGE_COUNT
        ):
            return None
        md_page_count = sub_md.get(PAGE_COUNT_KEY)
        real_page_count = self.get_page_count()
        if md_page_count is None or md_page_count > real_page_count:
            return {PAGE_COUNT_KEY: real_page_count}
        return None

    def _ensure_pages_front_cover_metadata(self, pages):
        """Ensure there is a FrontCover page type in pages."""
        for page in pages.values():
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
        old_pages = md.get(PAGES_KEY, {})
        max_page_index = self._get_max_page_index()
        trimmed_old_pages = {k: v for k, v in old_pages.items() if k <= max_page_index}
        computed_pages = AdditiveMerger.merge(trimmed_old_pages, pages)
        self._ensure_pages_front_cover_metadata(computed_pages)
        return computed_pages

    def _get_computed_pages_metadata(self, sub_md):
        """Recompute the tag image sizes for the ComicRack PageInfo list."""
        if PAGES_KEY in self._config.delete_keys:
            return None
        if not sub_md or not self._enable_page_compute_attribute(
            ComputeSchemaAttribute.HAS_PAGES
        ):
            return None
        pages = {}
        try:
            index = 0
            infolist = self._get_archive_infolist()
            for info in infolist:
                filename = self._get_info_fn(info)
                if self.IMAGE_EXT_RE.search(filename) is None:
                    continue
                size = self._get_info_size(info)
                # height & width could go here.
                if size is not None:
                    computed_page = {"size": size}
                    pages[index] = computed_page
                index += 1
        except Exception as exc:
            LOG.warning(f"{self._path}: Compute pages metadata: {exc}")
        if pages:
            pages = self._get_computed_merged_pages_metadata(sub_md, pages)
        return {PAGES_KEY: pages}

    def _parse_issue_match(self, match, old_issue_number, old_issue_suffix, issue):
        """Use regex match to break the issue into parts."""
        issue_number, issue_suffix = match.groups()
        if is_empty(old_issue_number) and not is_empty(issue_number):
            try:
                issue_number = DecimalField().deserialize(
                    issue_number, NUMBER_KEY, issue
                )
                issue[NUMBER_KEY] = issue_number
            except Exception as exc:
                LOG.warning(f"{self._path} Parsing issue_number from issue {exc}")
        if not old_issue_suffix and issue_suffix:
            issue[ISSUE_SUFFIX_KEY] = StringField().deserialize(
                issue_suffix, ISSUE_SUFFIX_KEY, issue
            )

    def _get_computed_from_issue(self, sub_data, **_kwargs):
        """Break parsed issue up into parts."""
        if not sub_data:
            return None
        issue = sub_data.get(ISSUE_KEY)
        if not issue:
            return None
        issue_name = issue.get(NAME_KEY)
        old_issue_number = issue.get(NUMBER_KEY)
        old_issue_suffix = issue.get(ISSUE_SUFFIX_KEY)
        try:
            if (
                issue_name
                and (not is_empty(old_issue_number) or not old_issue_suffix)
                and (match := _PARSE_ISSUE_MATCHER.match(issue_name))
            ):
                self._parse_issue_match(
                    match, old_issue_number, old_issue_suffix, issue
                )
        except Exception:
            LOG.debug(f"{self._path} Error parsing issue into components: {issue}")
            raise

        return {ISSUE_KEY: issue}

    def _get_computed_issue(self, sub_data, **_kwargs):
        """Build issue from parts before dump if issue doesn't already exist."""
        if not sub_data or ISSUE_KEY in self._config.delete_keys:
            return None
        issue = sub_data.get(ISSUE_KEY)
        if not issue:
            return None
        if issue_name := issue.get(NAME_KEY):
            return None
        issue_number = issue.get(NUMBER_KEY, "")
        issue_suffix = issue.get(ISSUE_SUFFIX_KEY, "")
        # Decimal removes unspecified decimal points
        if issue_name := f"{issue_number}{issue_suffix}".strip():
            issue[NAME_KEY] = issue_name
            return {ISSUE_KEY: issue}
        return None

    def _get_computed_from_scan_info(self, sub_data, **_kwargs):
        """Parse scan_info for original format info."""
        if ORIGINAL_FORMAT_KEY in self._config.delete_keys:
            return None
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
            nid, _, nss = parse_urn_identifier(tag)
            if nid:
                nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), DEFAULT_NID)
                if nss:
                    identifiers[nid] = create_identifier(nid, nss)
        return identifiers

    def _add_urls_to_identifiers(self, sub_data):
        if IDENTIFIERS_KEY in self._config.delete_keys:
            return None
        identifiers = sub_data.get(IDENTIFIERS_KEY, {})
        if not identifiers:
            return None
        identifiers_with_urls = {}
        for nid, identifier in identifiers.items():
            if identifier.get(URL_KEY):
                continue
            if nss := identifier.get(NSS_KEY):
                new_identifier = create_identifier(nid, nss)
                identifiers_with_urls[nid] = new_identifier
        return identifiers_with_urls

    def _add_identifier_primary_source_key(self, sub_data):
        ips = {}
        if {IDENTIFIERS_KEY, IDENTIFIER_PRIMARY_SOURCE_KEY} & {
            self._config.delete_keys
        }:
            return ips
        if not (
            self._config.write
            & {MetadataFormats.COMICTAGGER, MetadataFormats.METRON_INFO}
        ):
            return ips
        identifiers = sub_data.get(IDENTIFIERS_KEY, {})
        if sub_data.get(IDENTIFIER_PRIMARY_SOURCE_KEY) or not identifiers:
            return ips
        for nid in NID_ORDER:
            if nid in identifiers:
                ips = create_identifier_primary_source(nid)
                break
        return ips

    def _get_computed_from_identifiers(self, sub_data):
        if IDENTIFIERS_KEY in self._config.delete_keys:
            return None
        result = {}
        if identifiers_with_urls := self._add_urls_to_identifiers(sub_data):
            result[IDENTIFIERS_KEY] = identifiers_with_urls
        if ips := self._add_identifier_primary_source_key(sub_data):
            result[IDENTIFIER_PRIMARY_SOURCE_KEY] = ips
        if result:
            return result
        return None

    def _get_computed_from_reprints(self, sub_data):
        """Consolidate reprints."""
        if REPRINTS_KEY in self._config.delete_keys:
            return None
        old_reprints = sub_data.get(REPRINTS_KEY)
        if not old_reprints:
            return None
        new_reprints = []
        merged_indexes = set()
        for index, old_reprint in enumerate(old_reprints):
            if index in merged_indexes:
                continue
            for sub_index, compare_old_reprint in enumerate(old_reprints[index:]):
                diff = DeepDiff(
                    old_reprint,
                    compare_old_reprint,
                    ignore_order=True,
                    ignore_string_case=True,
                    ignore_encoding_errors=True,
                )
                if "values_changed" not in diff:
                    AdditiveMerger.merge(old_reprint, compare_old_reprint)
                    merged_indexes.add(index + sub_index)
            new_reprints.append(old_reprint)

        if len(old_reprints) != len(new_reprints):
            return {REPRINTS_KEY: new_reprints}
        return None

    def _get_computed_from_tag_origin(self, sub_data):
        # Should this pop or should it pop on ct post load?
        if IDENTIFIERS_KEY in self._config.delete_keys:
            return None
        if not sub_data:
            return None
        nid = sub_data.pop(TAG_ORIGIN_KEY, {}).get("id", "")
        nid = IDENTIFIER_URN_NIDS_REVERSE_MAP.get(nid.lower(), DEFAULT_NID)
        if not nid:
            return None
        nss = sub_data.pop(ISSUE_ID_KEY, None)
        if not nss:
            nss = sub_data.pop(SERIES_ID_KEY, None)
            if not nss:
                return None
        return {nid: nss}

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
        urn_strs = set()
        # The are issues which is the default type.
        nss_type = ""
        for nid, identifier in identifiers.items():
            nss = identifier.get(NSS_KEY)
            if not nss:
                continue
            urn_str = to_urn_string(nid, nss_type, nss)
            urn_strs.add(urn_str)
        notes += " ".join(sorted(urn_strs))
        return notes

    def _get_computed_notes_stamp(self, sub_data, stamp_md):
        """Write comicbox notes to notes field if present."""
        if not self._config.stamp_notes:
            return None
        if identifiers := sub_data.get(IDENTIFIERS_KEY):
            stamp_md[IDENTIFIERS_KEY] = identifiers

        comictagger_style_notes = self._get_unparsed_comictagger_style_notes(stamp_md)
        urn_notes = self._get_unparsed_urns_for_notes(stamp_md)
        notes = f"{comictagger_style_notes} {urn_notes}"
        return notes.strip()

    def _get_tagger_stamp(self, sub_data):
        """Stamp when writing."""
        if NOTES_KEY in self._config.delete_keys:
            return None
        if not self._config.all_write_formats:
            # Only stamp on write.
            return None

        # tagger & updated_at
        stamp_md = {
            TAGGER_KEY: self._config.tagger,
            # Deprecated method needed for python 3.10
            # Update after 2026-11
            UPDATED_AT_KEY: datetime.utcnow(),  # noqa: DTZ003, type: ignore
        }

        # notes
        if notes := self._get_computed_notes_stamp(sub_data, stamp_md):
            stamp_md[NOTES_KEY] = notes

        return stamp_md

    def _get_delete_keys(self, _sub_data: Mapping):
        if self._config.delete_keys:
            return self._config.delete_keys
        return None

    _COMPUTED_ACTIONS = MappingProxyType(
        {
            # Order is important here
            "Page Count": (_get_computed_page_count_metadata, ReplaceMerger),
            "Pages": (_get_computed_pages_metadata, ReplaceMerger),
            "from issue": (_get_computed_from_issue, AdditiveMerger),
            "from issue.number & issue.suffix": (
                _get_computed_issue,
                AdditiveMerger,
            ),
            "from notes": (
                ComicboxComputedNotesMixin.get_computed_from_notes,
                AdditiveMerger,
            ),
            "from tags": (_get_computed_from_tags, AdditiveMerger),
            "from identifiers": (_get_computed_from_identifiers, AdditiveMerger),
            "from reprints": (_get_computed_from_reprints, ReplaceMerger),
            "from scan_info": (_get_computed_from_scan_info, AdditiveMerger),
            "from tag_origin": (_get_computed_from_tag_origin, AdditiveMerger),
            "Tagger Stamp": (_get_tagger_stamp, ReplaceMerger),
            "Delete Keys": (_get_delete_keys, None),
        }
    )

    def _set_computed_metadata(self):
        computed_list = []
        merged_md = self.get_merged_metadata()
        sub_data = merged_md.get(ComicboxSchemaMixin.ROOT_TAG, {})

        # Compute each
        for label, actions in self._COMPUTED_ACTIONS.items():
            method, merger = actions
            sub_md = method(self, sub_data)
            if not sub_md:
                continue

            md = {ComicboxSchemaMixin.ROOT_TAG: sub_md}
            computed_data = ComputedData(label, md, merger)
            computed_list.append(computed_data)

        # Set values
        self._computed = tuple(computed_list)

    @archive_close
    def get_computed_metadata(self):
        """Get the computed metadata for printing."""
        if not self._computed:
            self._set_computed_metadata()
        return self._computed
