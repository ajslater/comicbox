"""XML Metadata parser superclass."""
from copy import deepcopy
from logging import getLogger

from marshmallow.decorators import post_load, pre_dump
from marshmallow.fields import Nested
from stringcase import capitalcase

from comicbox.fields.collections import StringSetField
from comicbox.schemas.base import BaseSchema
from comicbox.schemas.comicbox_base import CONTRIBUTORS_KEY
from comicbox.schemas.contributors import get_case_contributor_map
from comicbox.schemas.decorators import trap_error
from comicbox.schemas.xml import ComicboxXmlSchema

LOG = getLogger(__name__)


class ContributorsStringListSchema(BaseSchema):
    """Contributors."""

    colorist = StringSetField(as_string=True)
    cover_artist = StringSetField(as_string=True)
    creator = StringSetField(as_string=True)
    editor = StringSetField(as_string=True)
    inker = StringSetField(as_string=True)
    letterer = StringSetField(as_string=True)
    penciller = StringSetField(as_string=True)
    writer = StringSetField(as_string=True)


class ComicXmlCreditsSchema(ComicboxXmlSchema):
    """XML Schema customizations."""

    CONTRIBUTOR_TAGS = get_case_contributor_map(
        ComicboxXmlSchema.CONTRIBUTOR_TAGS, capitalcase
    )
    CONTRIBUTORS_ROOT = None
    _VALID_CONTRIBUTOR_TAGS = frozenset(ComicboxXmlSchema.CONTRIBUTOR_TAGS.keys())

    contributors = Nested(ContributorsStringListSchema)

    @trap_error(post_load)
    def aggregate_contributors(self, data, **_kwargs):
        """Aggregate credits from individual role tags to contributors entries."""
        contributor_keys = self._VALID_CONTRIBUTOR_TAGS & frozenset(data.keys())
        if not contributor_keys:
            return data
        data = deepcopy(dict(data))
        for comicbox_role in self.CREDIT_KEY_MAP.values():
            try:
                persons = data.pop(comicbox_role, None)
                if not persons:
                    continue
                persons = StringSetField().deserialize(persons)
                if not persons:
                    continue
                if CONTRIBUTORS_KEY not in data:
                    data[CONTRIBUTORS_KEY] = {}
                contributors = data[CONTRIBUTORS_KEY]
                if comicbox_role not in contributors:
                    contributors[comicbox_role] = set()
                contributors[comicbox_role] |= persons
            except Exception:
                LOG.exception(f"{self._path} Aggregating credit role {comicbox_role}")
        return data

    @pre_dump
    def disaggregate_contributors(self, data, **_kwargs):
        """Disaggregate credits from contributors entries to individual role tags."""
        if CONTRIBUTORS_KEY not in data:
            return data
        data = deepcopy(dict(data))
        contributors = data.pop(CONTRIBUTORS_KEY, {})
        for comicbox_role, comicbox_persons in contributors.items():
            try:
                if comicbox_persons:
                    data[comicbox_role] = comicbox_persons
            except Exception as exc:
                LOG.warning(
                    f"{self._path} Disaggregating credits "
                    f"{comicbox_role}:{comicbox_persons}: {exc}"
                )
        return data
