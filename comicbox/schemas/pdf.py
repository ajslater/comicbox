"""Mimic comicbox.Comicbox functions for PDFs."""

from types import MappingProxyType

from marshmallow.fields import Constant, Nested

from comicbox.fields.collections import StringSetField
from comicbox.fields.fields import StringField
from comicbox.schemas.base import BaseSubSchema
from comicbox.schemas.json import JsonSchema, JsonSubSchema
from comicbox.schemas.xml import XmlSchema, XmlSubSchema


class MuPDFSubSchema(JsonSubSchema):
    """muPDF Sub Schema."""

    # https://pymupdf.readthedocs.io/en/latest/document.html#Document.metadata

    author = StringSetField(as_string=True)
    creator = StringField()
    keywords = StringField()
    producer = StringField()
    subject = StringSetField(as_string=True)
    title = StringField()


class MuPDFSchema(JsonSchema):
    """muPDFSchema."""

    CONFIG_KEYS = frozenset({"pdf", "mudpdf"})
    FILENAME = "mupdf.json"
    ROOT_TAGS = ("MuPDF",)

    MuPDF = Nested(MuPDFSubSchema)


class PDFSubSchema(BaseSubSchema):
    """PDF Data Sub Schema."""

    class Meta(BaseSubSchema.Meta):
        """Schema options."""

        include = MappingProxyType(
            {
                "@xmlns:pdf": Constant("http://ns.adobe.com/pdf/1.3/"),
                "pdf:Author": StringSetField(as_string=True),
                "pdf:Creator": StringField(),
                "pdf:Keywords": StringField(),
                "pdf:Producer": StringField(),
                "pdf:Subject": StringSetField(as_string=True),
                "pdf:Title": StringField(),
            }
        )


class PDFRDFDescriptionSchema(BaseSubSchema):
    """PDF RDF Description Schema."""

    class Meta(BaseSubSchema.Meta):
        """Schema options."""

        include = MappingProxyType(
            {
                "@xmlns:rdf": Constant("http://www.w3.org/1999/02/22-rdf-syntax-ns"),
                "rdf:Description": Nested(PDFSubSchema),
            },
        )


class PDFXMPMetaSchema(XmlSubSchema):
    """PDF XMP Meta Schema."""

    class Meta(XmlSubSchema.Meta):
        """Schema options."""

        include = MappingProxyType(
            {
                "@x:xmptk": Constant(
                    "Adobe XMP Core 5.6-c140 79.160451, 2017/05/06-01:08:21"
                ),
                "@xmlns:x": Constant("adobe:ns:meta/"),
                XmlSubSchema.Meta.XSI_SCHEMA_LOCATION_KEY: Constant(
                    "http://ns.adobe.com/pdf/1.3/"
                ),
                "rdf:RDF": Nested(PDFRDFDescriptionSchema),
            }
        )


class PDFXmlSchema(XmlSchema):
    """PDF Schema."""

    CONFIG_KEYS = frozenset({"pdfxml"})
    FILENAME = "pdf.xml"
    ROOT_TAGS = ("x:xmpmeta", "rdf:RDF", "rdf:Description")

    class Meta(XmlSchema.Meta):
        """Schema options."""

        include = MappingProxyType({"x:xmpmeta": Nested(PDFXMPMetaSchema)})
