"""A class to encapsulate the ComicBookInfo data."""
from copy import deepcopy
from datetime import datetime
from logging import getLogger
from types import MappingProxyType

from marshmallow import Schema, post_dump, post_load, pre_dump
from marshmallow.fields import Nested
from stringcase import titlecase

from comicbox.fields.collections import ListField, StringSetField
from comicbox.fields.fields import StringField
from comicbox.fields.numbers import BooleanField
from comicbox.fields.time import DateTimeField
from comicbox.schemas.comicbox_base import (
    CONTRIBUTORS_KEY,
    PAGE_COUNT_KEY,
    TAGS_KEY,
    UPDATED_AT_KEY,
)
from comicbox.schemas.contributors import (
    get_case_contributor_map,
    get_case_credit_map,
)
from comicbox.schemas.decorators import trap_error
from comicbox.schemas.json import ComicboxJsonSchema
from comicbox.version import VERSION

LOG = getLogger(__name__)

LAST_MODIFIED_KEY = "lastModified"
_CBI_CREDIT_ROLE_MAP = get_case_credit_map(titlecase)
_CBI_DATA_KEY_MAP = MappingProxyType(
    {
        "comments": "summary",
        "country": "country",
        "credits": "credits_list",
        "genre": "genres",
        "issue": "issue",
        "language": "language",
        LAST_MODIFIED_KEY: UPDATED_AT_KEY,
        "numberOfVolumes": "volume_count",
        "numberOfIssues": "issue_count",
        "pages": PAGE_COUNT_KEY,
        "publicationDay": "day",
        "publicationMonth": "month",
        "publicationYear": "year",
        "publisher": "publisher",
        "rating": "critical_rating",
        "series": "series",
        TAGS_KEY: TAGS_KEY,
        "title": "title",
        "volume": "volume",
    }
)
_CBI_EXTRA_KEYS = (CONTRIBUTORS_KEY,)


class CreditDictSchema(Schema):
    """ComicBookInfo Credit Dict Schema."""

    role = StringField()
    person = StringField()
    primary = BooleanField()


class ComicBookInfoSchema(ComicboxJsonSchema):
    """ComicBookInfo JSON schema."""

    DATA_KEY_MAP = _CBI_DATA_KEY_MAP
    ROOT_TAG = "ComicBookInfo/1.0"
    ROOT_TAGS = MappingProxyType(
        {
            ROOT_TAG: {},
            "appID": f"comicbox/{VERSION}",
            "schema": "https://code.google.com/archive/p/comicbookinfo/wikis/Example.wiki",
        }
    )
    CONFIG_KEYS = frozenset({"cbi", "cbl", "comicbookinfo", "comicbooklover"})
    FILENAME = "comic-book-info.json"
    CONTRIBUTOR_TAGS = get_case_contributor_map(
        ComicboxJsonSchema.CONTRIBUTOR_TAGS, titlecase
    )
    _CREDIT_ROLE_MAP = _CBI_CREDIT_ROLE_MAP
    _CONTRIBUTOR_ROLE_MAP = MappingProxyType(
        {v: k for k, v in _CREDIT_ROLE_MAP.items()}
    )
    _CREDITS_LIST_KEY = "credits_list"
    _ROLE_KEY = "role"
    _PERSON_KEY = "person"

    credits_list = ListField(Nested(CreditDictSchema))
    genres = StringSetField(as_string=True)

    class Meta(ComicboxJsonSchema.Meta):
        """Schema options."""

        fields = ComicboxJsonSchema.Meta.create_fields(
            _CBI_DATA_KEY_MAP, _CBI_EXTRA_KEYS
        )

    def _get_comicbox_role(self, credit_dict):
        """Consolidate credit tags."""
        extra_credit = None
        cbi_role = credit_dict.get(self._ROLE_KEY)
        if not cbi_role:
            return None, extra_credit

        # Special extra credit if role is Artist
        if cbi_role == "Artist" and (person := credit_dict.get(self._PERSON_KEY)):
            inker_dict = {self._ROLE_KEY: "Inker", self._PERSON_KEY: person}
            extra_credit = inker_dict
            cbi_role = "Penciller"

        if cbi_role not in self.CONTRIBUTOR_TAGS:
            cbi_role = self.contributor_variant_map.get(cbi_role)
        if not cbi_role:
            return None, extra_credit
        return self._CREDIT_ROLE_MAP.get(cbi_role), extra_credit

    def _aggregate_contributor(self, contributors, credit_dict):
        extra_credit = None
        try:
            person = credit_dict.get(self._PERSON_KEY)
            if not person:
                return extra_credit
            comicbox_role, extra_credit = self._get_comicbox_role(credit_dict)
            if not comicbox_role:
                return extra_credit

            if comicbox_role not in contributors:
                contributors[comicbox_role] = set()
            contributors[comicbox_role].add(person)
        except Exception:
            LOG.exception(f"{self._path} Could not parse credit: {credit_dict}")
        return extra_credit

    @trap_error(post_load)
    def aggregate_contributors(self, data, **_kwargs):
        """Aggregate dict from comicbookinfo style list."""
        if not data.get(self._CREDITS_LIST_KEY):
            return data
        data = deepcopy(dict(data))
        credits_list = data.pop(self._CREDITS_LIST_KEY)
        contributors = {}
        for credit_dict in credits_list:
            add_credit = credit_dict
            while add_credit:
                add_credit = self._aggregate_contributor(contributors, add_credit)
        if contributors:
            data[CONTRIBUTORS_KEY] = contributors
        return data

    @pre_dump
    def disaggregate_contributors(self, data, **_kwargs):
        """Create comicbookinfo style list from dict."""
        if CONTRIBUTORS_KEY not in data:
            return data
        data = deepcopy(dict(data))
        contributors = data.pop(CONTRIBUTORS_KEY, {})
        credits_list = []
        for comicbox_role, comicbox_persons in contributors.items():
            for person in comicbox_persons:
                try:
                    cbi_role = self._CONTRIBUTOR_ROLE_MAP.get(comicbox_role)
                    credit_dict = {self._ROLE_KEY: cbi_role, self._PERSON_KEY: person}
                    credits_list.append(credit_dict)
                except Exception as exc:
                    LOG.warning(
                        f"{self._path} Disaggregating credit"
                        f" {comicbox_role}:{person} - {exc}"
                    )
        if credits_list:
            data[self._CREDITS_LIST_KEY] = credits_list
        return data

    @pre_dump
    def store_timestamp(self, data, **_kwargs):
        """Hack to store updated_at for post_dump."""
        self._timestamp = data.get(UPDATED_AT_KEY, datetime.utcnow())  # noqa DTZ003
        return data

    @post_dump(pass_many=True)
    def wrap_in_root_tags(self, data, **kwargs):
        """Add the last modified timestamp."""
        last_modified = data.pop(LAST_MODIFIED_KEY, None)
        data = super().wrap_in_root_tags(data, **kwargs)
        if type(self) == ComicBookInfoSchema:
            if self._timestamp:
                field = DateTimeField()
                last_modified = field._serialize(self._timestamp)  # noqa: SLF001
            if last_modified:
                data[LAST_MODIFIED_KEY] = last_modified  # type: ignore
        return data
