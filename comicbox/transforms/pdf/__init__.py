"""Transform PDF formats to comicbox and back."""

from bidict import frozenbidict

from comicbox.schemas.comicbox import (
    GENRES_KEY,
    SCAN_INFO_KEY,
    TAGGER_KEY,
    TITLE_KEY,
    UPDATED_AT_KEY,
)
from comicbox.schemas.pdf import MuPDFSchema, PDFXmlSchema
from comicbox.transforms.base import BaseTransform
from comicbox.transforms.comicbox.name_objs import (
    name_obj_from_cb,
    name_obj_to_cb,
)
from comicbox.transforms.pdf.credits import (
    authors_to_credits_transform_from_cb,
    authors_to_credits_transform_to_cb,
)
from comicbox.transforms.spec import (
    MetaSpec,
    create_specs_from_comicbox,
    create_specs_to_comicbox,
)

XMLPDF_SIMPLE_KEY_MAP = frozenbidict(
    {
        "pdf:Creator": SCAN_INFO_KEY,  # original document creator
        "pdf:Producer": TAGGER_KEY,
        "pdf:ModDate": UPDATED_AT_KEY,
        "pdf:Title": TITLE_KEY,
    }
)
XMLPDF_NAME_OBJ_KEY_MAP = frozenbidict(
    {
        "pdf:Subject": GENRES_KEY,
    },
)


class PDFXmlTransform(BaseTransform):
    """PDF Schema."""

    SCHEMA_CLASS = PDFXmlSchema
    SPECS_TO = create_specs_to_comicbox(
        MetaSpec(key_map=XMLPDF_SIMPLE_KEY_MAP.inverse),
        authors_to_credits_transform_to_cb("pdf:Author"),
        name_obj_to_cb(XMLPDF_NAME_OBJ_KEY_MAP.inverse),
        format_root_keypath=PDFXmlSchema.ROOT_KEYPATH,
    )
    SPECS_FROM = create_specs_from_comicbox(
        MetaSpec(key_map=XMLPDF_SIMPLE_KEY_MAP),
        authors_to_credits_transform_from_cb("pdf:Author"),
        name_obj_from_cb(XMLPDF_NAME_OBJ_KEY_MAP),
        format_root_keypath=PDFXmlSchema.ROOT_KEYPATH,
    )


MUPDF_SIMPLE_KEY_MAP = frozenbidict(
    {
        "creator": SCAN_INFO_KEY,  # original document creator
        "modDate": UPDATED_AT_KEY,
        "producer": TAGGER_KEY,
        "title": TITLE_KEY,
    }
)
MUPDF_NAME_OBJ_KEY_MAP = frozenbidict(
    {
        "subject": GENRES_KEY,
    },
)


class MuPDFTransform(PDFXmlTransform):
    """MuPDF Transformer."""

    SCHEMA_CLASS = MuPDFSchema
    SPECS_TO = create_specs_to_comicbox(
        MetaSpec(key_map=MUPDF_SIMPLE_KEY_MAP.inverse),
        authors_to_credits_transform_to_cb("author"),
        name_obj_to_cb(MUPDF_NAME_OBJ_KEY_MAP.inverse),
        format_root_keypath=MuPDFSchema.ROOT_KEYPATH,
    )
    SPECS_FROM = create_specs_from_comicbox(
        MetaSpec(key_map=MUPDF_SIMPLE_KEY_MAP),
        authors_to_credits_transform_from_cb("author"),
        name_obj_from_cb(MUPDF_NAME_OBJ_KEY_MAP),
        format_root_keypath=MuPDFSchema.ROOT_KEYPATH,
    )
