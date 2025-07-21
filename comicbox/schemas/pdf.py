"""Mimic comicbox.Comicbox functions for PDFs."""

from types import MappingProxyType

from marshmallow.fields import Constant, Nested

from comicbox.fields.collection_fields import (
    EmbeddedStringSetField,
    StringSetField,
)
from comicbox.fields.fields import StringField
from comicbox.fields.pdf import PdfDateTimeField
from comicbox.fields.xml_fields import (
    XmlEmbeddedStringSetField,
    XmlPdfDateTimeField,
    XmlStringField,
    XmlStringSetField,
)
from comicbox.schemas.base import BaseSubSchema
from comicbox.schemas.json_schemas import JsonSchema, JsonSubSchema
from comicbox.schemas.xml_schemas import (
    XmlSchema,
    XmlSubHeadSchema,
    XmlSubSchema,
    create_xml_headers,
)


class MuPDFSubSchema(JsonSubSchema):
    """muPDF Sub Schema."""

    # https://pymupdf.readthedocs.io/en/latest/document.html#Document.metadata

    author = StringSetField(as_string=True)
    creator = StringField()
    keywords = EmbeddedStringSetField()
    modDate = PdfDateTimeField()  # noqa: N815
    producer = StringField()
    subject = StringSetField(as_string=True)
    title = StringField()


class MuPDFSchema(JsonSchema):
    """muPDFSchema."""

    ROOT_TAG: str = "MuPDF"
    ROOT_KEYPATH: str = ROOT_TAG
    EMBED_KEYPATH: str = f"{ROOT_KEYPATH}.keywords"

    MuPDF = Nested(MuPDFSubSchema)


class PDFSubSchema(BaseSubSchema):
    """PDF Data Sub Schema."""

    class Meta(BaseSubSchema.Meta):
        """Schema options."""

        include = MappingProxyType(
            {
                "@xmlns:pdf": Constant("http://ns.adobe.com/pdf/1.3/"),
                "pdf:Author": XmlStringSetField(as_string=True),
                "pdf:Creator": XmlStringField(),
                "pdf:Keywords": XmlEmbeddedStringSetField(),
                "pdf:ModDate": XmlPdfDateTimeField(),
                "pdf:Producer": XmlStringField(),
                "pdf:Subject": XmlStringSetField(as_string=True),
                "pdf:Title": XmlStringField(),
            }
        )


class PDFRDFDescriptionSchema(XmlSubSchema):
    """PDF RDF Description Schema."""

    class Meta(XmlSubSchema.Meta):
        """Schema options."""

        include = MappingProxyType(
            {
                "@xmlns:rdf": Constant("http://www.w3.org/1999/02/22-rdf-syntax-ns"),
                "rdf:Description": Nested(PDFSubSchema),
            },
        )


class PDFXMPMetaSchema(XmlSubHeadSchema):
    """PDF XMP Meta Schema."""

    class Meta(XmlSubHeadSchema.Meta):
        """Schema options."""

        NS = "x"
        NS_URI = "adobe:ns:meta/"
        XSD_URI = "http://ns.adobe.com/pdf/1.3/"

        include = MappingProxyType(
            {
                **create_xml_headers(NS, NS_URI, XSD_URI),
                "@x:xmptk": Constant(
                    "Adobe XMP Core 5.6-c140 79.160451, 2017/05/06-01:08:21"
                ),
                "rdf:RDF": Nested(PDFRDFDescriptionSchema),
            }
        )


class PDFXmlSchema(XmlSchema):
    """PDF Schema."""

    ROOT_TAG: str = "x:xmpmeta"
    ROOT_KEYPATH: str = f"{ROOT_TAG}.rdf:RDF.rdf:Description"
    EMBED_KEYPATH: str = f"{ROOT_KEYPATH}.pdf:Keywords"

    class Meta(XmlSchema.Meta):
        """Schema options."""

        include = MappingProxyType({"x:xmpmeta": Nested(PDFXMPMetaSchema)})
