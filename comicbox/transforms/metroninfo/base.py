"""MetronInfo.xml Transformer."""

from collections.abc import Mapping
from logging import getLogger

from comicbox.identifiers import (
    METRON_NID,
    create_identifier,
)
from comicbox.schemas.comicbox_mixin import (
    AGE_RATING_KEY,
    COLLECTION_TITLE_KEY,
    DATE_KEY,
    IDENTIFIERS_KEY,
    ISSUE_KEY,
    NOTES_KEY,
    PAGE_COUNT_KEY,
    STORE_DATE_KEY,
    SUMMARY_KEY,
    UPDATED_AT_KEY,
)
from comicbox.schemas.metroninfo import (
    MetronInfoSchema,
)
from comicbox.transforms.identifiers import get_primary_source_nid
from comicbox.transforms.metroninfo.credits import METRON_CREDITS_TRANSFORM
from comicbox.transforms.metroninfo.identifiers import (
    METRON_GTIN_TRANSFORM,
    METRON_IDENTIFIERS_TRANSFORM,
    METRON_PRIMARY_SOURCE_KEY_TRANSFORM,
    METRON_URLS_TRANSFORM,
)
from comicbox.transforms.metroninfo.publishing_tags import (
    METRON_IMPRINT_TRANSFORM,
    METRON_MANGA_VOLUME_TRANSFORM,
    METRON_PUBLISHER_TRANSFORM,
    METRON_SERIES_ALTERNATIVE_NAMES_TRANSFORM,
    METRON_SERIES_IDENTIFIERS_TRANSFORM,
    SERIES_KEY_MAP,
)
from comicbox.transforms.metroninfo.reprints import METRON_REPRINTS_TRANSFORM
from comicbox.transforms.transform_map import KeyTransforms, create_transform_map
from comicbox.transforms.xml_transforms import XmlTransform

LOG = getLogger(__name__)


class MetronInfoTransformBase(XmlTransform):
    """MetronInfo.xml Schema."""

    SCHEMA_CLASS = MetronInfoSchema
    TRANSFORM_MAP = create_transform_map(
        KeyTransforms(
            key_map={
                "AgeRating": AGE_RATING_KEY,
                "CollectionTitle": COLLECTION_TITLE_KEY,
                "CoverDate": DATE_KEY,
                "StoreDate": STORE_DATE_KEY,
                "Notes": NOTES_KEY,
                "Number": ISSUE_KEY,
                "PageCount": PAGE_COUNT_KEY,
                "Summary": SUMMARY_KEY,
                "LastModified": UPDATED_AT_KEY,
                **SERIES_KEY_MAP,
                **{
                    key: key
                    for key in {
                        "arcs",
                        "characters",
                        "genres",
                        "locations",
                        "prices",
                        "stories",
                        "tags",
                        "teams",
                        "universes",
                    }
                    | {
                        "Arcs",
                        "Characters",
                        "Genres",
                        "Locations",
                        "MangaVolume",
                        "Prices",
                        "Stories",
                        "Tags",
                        "Teams",
                        "Universes",
                    }
                },
            }
        ),
        METRON_PUBLISHER_TRANSFORM,
        METRON_IMPRINT_TRANSFORM,
        METRON_SERIES_IDENTIFIERS_TRANSFORM,
        METRON_SERIES_ALTERNATIVE_NAMES_TRANSFORM,
        METRON_MANGA_VOLUME_TRANSFORM,
        METRON_CREDITS_TRANSFORM,
        METRON_GTIN_TRANSFORM,
        METRON_IDENTIFIERS_TRANSFORM,
        METRON_PRIMARY_SOURCE_KEY_TRANSFORM,
        METRON_REPRINTS_TRANSFORM,
        METRON_URLS_TRANSFORM,
    )
    ID_ATTRIBUTE = "@id"

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
            primary_nid = get_primary_source_nid(data, METRON_NID)
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
        primary_nid = get_primary_source_nid(data, METRON_NID)
        for nid, identifier in comicbox_identifiers.items():
            if primary_nid and nid == primary_nid and (nss := identifier.get("nss")):
                metron_obj[cls.ID_ATTRIBUTE] = nss
                break
