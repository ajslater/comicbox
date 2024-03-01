"""XML Metadata parser superclass."""

from logging import getLogger

from stringcase import capitalcase

from comicbox.fields.collections import StringSetField
from comicbox.schemas.comicbox_mixin import CONTRIBUTORS_KEY

LOG = getLogger(__name__)


class XmlCreditsTransformMixin:
    """XML Schema customizations."""

    @staticmethod
    def tag_case(data):
        """Transform tag case."""
        return capitalcase(data)

    def aggregate_contributors(self, data):
        """Aggregate credits from individual role tags to contributors entries."""
        for schema_role, comicbox_role in self.CONTRIBUTOR_COMICBOX_MAP.items():  # type: ignore
            try:
                persons = data.pop(schema_role, None)
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
                LOG.exception(f"{self._path} Aggregating credit role {comicbox_role}")  # type: ignore
        return data

    def disaggregate_contributors(self, data):
        """Disaggregate credits from contributors entries to individual role tags."""
        contributors = data.pop(CONTRIBUTORS_KEY, {})
        if not contributors:
            return data
        for comicbox_role, comicbox_persons in contributors.items():
            if not comicbox_persons:
                continue
            try:
                schema_role = self.CONTRIBUTOR_SCHEMA_MAP.get(comicbox_role)  # type: ignore
                if schema_role:
                    data[schema_role] = comicbox_persons
            except Exception as exc:
                LOG.warning(
                    f"{self._path} Disaggregating credits "  # type: ignore
                    f"{comicbox_role}:{comicbox_persons}: {exc}"
                )
        return data
