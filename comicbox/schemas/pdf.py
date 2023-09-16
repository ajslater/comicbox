"""Mimic comicbox.Comicbox functions for PDFs."""
from copy import deepcopy
from types import MappingProxyType

from marshmallow import post_dump, post_load, pre_dump, pre_load

from comicbox.fields.collections import IdentifiersField, StringSetField
from comicbox.fields.fields import StringField
from comicbox.schemas.comicbox_base import CONTRIBUTORS_KEY, IDENTIFIERS_KEY, TAGS_KEY
from comicbox.schemas.decorators import trap_error
from comicbox.schemas.xml import ComicboxXmlSchema

_WRITER_KEY = "writer"
_PDF_CREDIT_KEY_MAP = MappingProxyType({"author": _WRITER_KEY})

_PDF_DATA_KEY_MAP = MappingProxyType(
    {
        "creator": "scan_info",  # original document creator
        "keywords": TAGS_KEY,
        IDENTIFIERS_KEY: IDENTIFIERS_KEY,
        "producer": "tagger",
        "subject": "genres",
        "title": "title",
        **_PDF_CREDIT_KEY_MAP,
    }
)

_PDF_EXTRA_KEYS = (CONTRIBUTORS_KEY,)


class PDFSchema(ComicboxXmlSchema):
    """PDF Schema."""

    _RDF_TAG = "rdf:RDF"
    _DESC_TAG = "rdf:Description"
    _IDENTIFIER_KEYWORD_PREFIX = "identifier"
    DATA_KEY_MAP = _PDF_DATA_KEY_MAP
    CREDIT_KEY_MAP = _PDF_CREDIT_KEY_MAP
    ROOT_TAG = "x:xmpmeta"
    MU_ROOT_TAG = "mu"
    ROOT_TAGS = MappingProxyType(
        {
            "@x:xmptk": "Adobe XMP Core 5.6-c140 79.160451, 2017/05/06-01:08:21",
            "@xmlns:x": "adobe:ns:meta/",
            _RDF_TAG: {
                "@xmlns:rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns",
                _DESC_TAG: {"@xmlns:pdf": "http://ns.adobe.com/pdf/1.3/"},
            },
        }
    )
    PDF_TAG_PREFIX = "pdf:"
    CONFIG_KEYS = frozenset({"pdf"})
    FILENAME = "pdf-metadata.xml"

    genres = StringSetField(as_string=True)
    tags = StringSetField(as_string=True)
    writer = StringSetField(as_string=True)

    class Meta(ComicboxXmlSchema.Meta):
        """Schema options."""

        fields = ComicboxXmlSchema.Meta.create_fields(
            _PDF_DATA_KEY_MAP, _PDF_EXTRA_KEYS, inherit_extra_keys=False
        )

    @classmethod
    def _from_pdf_key(cls, key):
        key = StringField().deserialize(key)
        if key:
            return key.removeprefix(cls.PDF_TAG_PREFIX).lower()
        return None

    @classmethod
    def _to_pdf_key(cls, key):
        return cls.PDF_TAG_PREFIX + key.capitalize()

    @trap_error(pre_load(pass_many=True))
    def strip_root_tags(self, data, **_kwargs):
        """Parse dicts from xmltodict or pymupdf."""
        data = deepcopy(dict(data))
        if self.ROOT_TAG in data:
            # from xmltodict
            data = (
                data.get(self.ROOT_TAG, {})
                .get(self._RDF_TAG, {})
                .get(self._DESC_TAG, {})
            )
            mu_dict = {}
            for key, value in data.items():
                mu_key = self._from_pdf_key(key)
                if mu_key:
                    mu_dict[mu_key] = value
            data = mu_dict
        elif self.MU_ROOT_TAG in data:
            # from pymupdf
            data = data[self.MU_ROOT_TAG]
        return data

    @trap_error(post_load)
    def aggregate_contributors(self, data, **_kwargs):
        """Convert csv to writer credits."""
        authors = data.get(_WRITER_KEY)
        if not authors:
            return data
        data = deepcopy(dict(data))
        if authors := data.pop(_WRITER_KEY, None):
            data[CONTRIBUTORS_KEY] = {_WRITER_KEY: authors}
        return data

    @pre_dump
    def disaggregate_contributors(self, data, **_kwargs):
        """Convert writer credits to csv."""
        contributors = data.get(CONTRIBUTORS_KEY)
        if not contributors:
            return data
        data = deepcopy(dict(data))
        contributors = data.pop(CONTRIBUTORS_KEY, {})
        if authors := contributors.get(_WRITER_KEY):
            data[_WRITER_KEY] = authors
        return data

    @pre_dump
    def unparse_tags(self, data, **_kwargs):
        """Write identifiers to keywords only for PDF."""
        identifiers = data.pop(IDENTIFIERS_KEY, None)
        if not identifiers:
            return data
        data = deepcopy(dict(data))
        tags = data.get(TAGS_KEY, set())
        for identifier_type, identifier in identifiers.items():
            identifier_tag = IdentifiersField.to_urn_string(identifier_type, identifier)
            tags.add(identifier_tag)
        data[TAGS_KEY] = tags
        return data

    @post_dump(pass_many=True)
    def wrap_in_root_tags(self, data, **_kwargs):
        """To pymupdf dict or adobe xml dict."""
        if self._adobe_format:
            root_dict = {self.ROOT_TAG: dict(self.ROOT_TAGS)}
            rdf_dict = root_dict[self.ROOT_TAG][self._RDF_TAG]
            pdf_data = {}
            for key, value in data.items():
                pdf_key = self._to_pdf_key(key)
                pdf_data[pdf_key] = value
            rdf_dict[self._DESC_TAG].update(pdf_data)  # type: ignore
            result = root_dict
        else:
            result = {self.MU_ROOT_TAG: data}
        return result

    def dump(self, *args, adobe_format=False, **kwargs):
        """Pass special adobe_format context to processors."""
        self._adobe_format = adobe_format
        return super().dump(*args, **kwargs)

    def dumps(self, obj, *args, adobe_format=True, **kwargs):
        """By default export adobe_format."""
        serialized = self.dump(obj, adobe_format=adobe_format, **kwargs)
        return self.opts.render_module.dumps(serialized, *args, **kwargs)
