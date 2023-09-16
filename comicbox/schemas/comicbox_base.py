"""Metadata class for a comic archive."""
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from logging import getLogger
from types import MappingProxyType
from typing import Optional

from marshmallow.decorators import pre_dump, pre_load
from marshmallow.fields import Nested

from comicbox.fields.collections import (
    DictStringField,
    IdentifiersField,
    ListField,
    StringListField,
    StringSetField,
)
from comicbox.fields.enum import (
    AgeRatingField,
    MangaField,
    ReadingDirectionField,
)
from comicbox.fields.fields import (
    OriginalFormatField,
    StringField,
)
from comicbox.fields.numbers import (
    BooleanField,
    DecimalField,
    IntegerField,
)
from comicbox.fields.pycountry import PyCountryField
from comicbox.fields.time import (
    DateField,
    DateTimeField,
)
from comicbox.identifiers import COMICVINE_NID
from comicbox.schemas.base import BaseSchema
from comicbox.schemas.contributors import ContributorsSchema, get_role_variant_map
from comicbox.schemas.decorators import trap_error
from comicbox.schemas.hierarichical import HierarchicalSchema
from comicbox.schemas.page_info import PageInfoSchema
from comicbox.version import DEFAULT_TAGGER

LOG = getLogger(__name__)
CONTRIBUTORS_KEY = "contributors"
PAGES_KEY = "pages"
PAGE_COUNT_KEY = "page_count"
NOTES_KEY = "notes"
TAGGER_KEY = "tagger"
UPDATED_AT_KEY = "updated_at"
IDENTIFIERS_KEY = "identifiers"
TAGS_KEY = "tags"
STORY_ARCS_KEY = "story_arcs"
SCAN_INFO_KEY = "scan_info"
ORIGINAL_FORMAT_KEY = "original_format"
ORDERED_SET_KEYS = frozenset({"remainders"})
WEB_KEY = "web"
ISSUE_KEY = "issue"
ISSUE_NUMBER_KEY = "issue_number"
ISSUE_SUFFIX_KEY = "issue_suffix"


@dataclass
class SchemaConfig:
    """Special config for schema.

    stamp: controls weather to update updated_at, tagger & notes
    tagger: controls the text of updating tagger
    updated_at: inject a specific datetime.
    """

    stamp: bool = False
    tagger: Optional[str] = DEFAULT_TAGGER
    updated_at: Optional[datetime] = None


class ComicboxBaseSchema(HierarchicalSchema):
    """The Comicbox schema."""

    age_rating = AgeRatingField()
    alternate_images = StringSetField()
    alternate_issue = StringField()
    alternate_issue_count = IntegerField(minimum=0)
    characters = StringSetField()
    community_rating = DecimalField(places=2)
    contributors = Nested(ContributorsSchema)
    country = PyCountryField()
    cover_image = StringField()
    critical_rating = DecimalField(places=2)
    date = DateField()
    day = IntegerField(minimum=1, maximum=31)
    ext = StringField()
    original_format = OriginalFormatField()
    genres = StringSetField()
    identifiers = IdentifiersField()
    issue = StringField()
    issue_count = IntegerField(minimum=0)
    issue_number = DecimalField(minimum=Decimal(0))
    issue_suffix = StringField()
    imprint = StringField()
    language = PyCountryField()
    last_mark = IntegerField(minimum=0)
    locations = StringSetField()
    manga = MangaField()
    month = IntegerField(minimum=1, maximum=12)
    monochrome = BooleanField()
    notes = StringField()
    page_count = IntegerField(minimum=0)
    pages = ListField(Nested(PageInfoSchema))
    publisher = StringField()
    price = DecimalField(places=2, minimum=Decimal(0))
    protagonist = StringField()
    reading_direction = ReadingDirectionField()
    remainders = StringListField()
    review = StringField()
    rights = StringField()
    scan_info = StringField()
    series = StringField()
    series_aliases = StringSetField()
    series_groups = StringSetField()
    story_arcs = DictStringField(values=IntegerField())
    summary = StringField()
    tagger = StringField()
    tags = StringSetField()
    teams = StringSetField()
    title = StringField()
    title_aliases = StringSetField()
    updated_at = DateTimeField()
    web = StringField()
    volume = IntegerField()
    volume_count = IntegerField(minimum=0)
    year = IntegerField(minimum=0)

    _IDENTIFIER_IN_NOTES_RE = re.compile(
        r"\[Issue ID (?P<identifier>\w+)\]$", flags=re.IGNORECASE
    )
    CONFIG_KEYS = frozenset()
    CONTRIBUTOR_TAGS = MappingProxyType(
        {
            "colorist": frozenset({"colorist", "colourist", "colorer", "colourer"}),
            "cover_artist": frozenset({"cover", "cover_artist", "cover_designer"}),
            "creator": frozenset({"creator"}),
            "editor": frozenset({"editor"}),
            "inker": frozenset({"inker", "finishes", "finisher"}),
            "letterer": frozenset({"letterer", "letters"}),
            "penciller": frozenset({"artist", "penciller", "penciler", "breakdowns"}),
            "writer": frozenset({"writer", "author", "plotter", "scripter"}),
        }
    )
    CONTRIBUTORS_ROOT = CONTRIBUTORS_KEY

    def __init__(self, path=None, dump_config=None, **kwargs):
        """Set up contributor maps."""
        super().__init__(path=path, **kwargs)
        self._dump_config = dump_config if dump_config else SchemaConfig()
        self.contributor_variant_map = get_role_variant_map(self.CONTRIBUTOR_TAGS)
        self.contributor_variant_keys = frozenset(self.contributor_variant_map)

    @classmethod
    def _get_contributors_dict(cls, data):
        """Get the dict that has contributors."""
        # if we ever need to go very deep, use a dot notation and split.
        if cls.CONTRIBUTORS_ROOT:
            contributors = data.get(cls.CONTRIBUTORS_ROOT)
        else:
            contributors = data
        return contributors

    def _get_role_variants(self, data):
        """Check if consolidation is neccissary."""
        contributors = self._get_contributors_dict(data)
        if not contributors:
            return frozenset()

        return frozenset(self.contributor_variant_keys & frozenset(contributors.keys()))

    @trap_error(pre_load)
    def consolidate_contributors(self, data, **_kwargs):
        """Compbine many contributor tag variants into canonical ones."""
        role_variants = self._get_role_variants(data)
        if not role_variants:
            return data

        # Commit to changing data
        data = deepcopy(dict(data))
        contributors = self._get_contributors_dict(data)
        if not contributors:
            return data

        # Pop role variants off and merge them with canonical roles.
        for role in role_variants:
            try:
                if persons := contributors.pop(role, set()):
                    consolidated_role = self.contributor_variant_map.get(role)
                    if consolidated_role not in contributors:
                        contributors[consolidated_role] = set()
                    contributors[consolidated_role] |= set(persons)
            except Exception:
                LOG.exception(f"Merge {role} with canonical role.")

        return data

    def _get_unparsed_comictagger_style_notes(self, data):
        """Build notes from other tags."""
        notes = ""
        if tagger := data.get(TAGGER_KEY):
            notes += f"Tagged with {tagger}"

        if updated_at := data.get(UPDATED_AT_KEY):
            field = DateTimeField()
            ts = field._serialize(updated_at)  # noqa: SLF001
            if ts:
                notes += f" on {ts}"

        if comicvine_id := data.get(IDENTIFIERS_KEY, {}).get(COMICVINE_NID):
            notes += f" [Issue ID {comicvine_id}]"
        return notes

    def _get_unparsed_urns_for_notes(self, data):
        """Unparse all types."""
        notes = ""
        identifiers = data.get(IDENTIFIERS_KEY)
        if not identifiers:
            return notes
        urn_strs = []
        for identifier_type, code in identifiers.items():
            urn_str = IdentifiersField.to_urn_string(identifier_type, code)
            urn_strs.append(urn_str)
        notes += " ".join(urn_strs)
        return notes

    def _get_computed_notes(self, data):
        """Write comicbox notes to notes field if present."""
        if data.get(NOTES_KEY):
            return None

        comictagger_style_notes = self._get_unparsed_comictagger_style_notes(data)
        urn_notes = self._get_unparsed_urns_for_notes(data)
        notes = " ".join((comictagger_style_notes, urn_notes))
        return notes.strip()

    @pre_dump
    def set_stamps_and_notes(self, data, **_kwargs):
        """Stamp tagger and time."""
        if not self._dump_config.stamp:
            return data
        md = {TAGGER_KEY: self._dump_config.tagger}
        if self._dump_config.updated_at:
            updated_at = self._dump_config.updated_at
        else:
            updated_at = datetime.utcnow()  # noqa: DTZ003
        md[UPDATED_AT_KEY] = updated_at

        data_copy = {}
        data_copy.update(md)
        if identifiers := data.get(IDENTIFIERS_KEY):
            data_copy[IDENTIFIERS_KEY] = identifiers

        notes = self._get_computed_notes(data_copy)
        if notes:
            md[NOTES_KEY] = notes
        for key, value in md.items():
            if key in self.fields:
                data[key] = value
        return data

    class Meta(BaseSchema.Meta):
        """Schema options."""

        EXTRA_KEYS = ("issue_number", "issue_suffix")
