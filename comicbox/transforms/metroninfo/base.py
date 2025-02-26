"""MetronInfo.xml Transformer."""

from collections.abc import Mapping
from logging import getLogger

from bidict import frozenbidict

from comicbox.identifiers import (
    create_identifier,
)
from comicbox.schemas.comicbox_mixin import (
    DATE_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    NOTES_KEY,
    PAGE_COUNT_KEY,
    SUMMARY_KEY,
    UPDATED_AT_KEY,
)
from comicbox.schemas.metroninfo import (
    MetronInfoSchema,
)
from comicbox.transforms.identifiers import IdentifiersTransformMixin
from comicbox.transforms.xml_transforms import XmlTransform

LOG = getLogger(__name__)


class MetronInfoTransformBase(XmlTransform, IdentifiersTransformMixin):
    """MetronInfo.xml Schema."""

    # Tag Names
    ID_ATTRIBUTE = "@id"
    TRANSFORM_MAP = frozenbidict(
        {
            "CollectionTitle": "collection_title",
            "CoverDate": DATE_KEY,
            "StoreDate": "store_date",
            "Notes": NOTES_KEY,
            "Number": ISSUE_KEY,
            "PageCount": PAGE_COUNT_KEY,
            "Summary": SUMMARY_KEY,
            "LastModified": UPDATED_AT_KEY,
        }
    )

    SCHEMA_CLASS = MetronInfoSchema

    # ID ATTRIBUTE
    ###########################################################################
    @classmethod
    def _parse_metron_id_attribute(
        cls, data: dict, nss_type: str, metron_obj: Mapping | str, comicbox_obj: dict
    ):
        """Parse the metron series identifier."""
        try:
            if not (
                isinstance(metron_obj, Mapping)
                and (nss := metron_obj.get(cls.ID_ATTRIBUTE))
            ):
                return
            primary_nid = cls.get_primary_source_nid(data)
            comicbox_identifier = create_identifier(primary_nid, nss, nss_type=nss_type)
            comicbox_obj[IDENTIFIERS_KEY] = {primary_nid: comicbox_identifier}
        except Exception as exc:
            LOG.warning(
                f"Parsing metron tag identifier {nss_type}:{metron_obj} - {exc}"
            )

    @classmethod
    def _unparse_metron_id_attribute(
        cls, data: dict, metron_obj: dict, comicbox_obj: dict
    ):
        """Unparse Metron series identifiers from series identifiers."""
        comicbox_identifiers = comicbox_obj.get(IDENTIFIERS_KEY)
        if not comicbox_identifiers:
            return
        primary_nid = cls.get_primary_source_nid(data)
        for nid, identifier in comicbox_identifiers.items():
            if primary_nid and nid == primary_nid and (nss := identifier.get("nss")):
                metron_obj[cls.ID_ATTRIBUTE] = nss
                break
