"""MetronInfo.xml Reprints Transform."""

from comicfn2dict.parse import comicfn2dict

from comicbox.fields.xml_fields import get_cdata
from comicbox.schemas.comicbox_mixin import (
    ISSUE_KEY,
    NAME_KEY,
    REPRINT_ISSUE_KEY,
    REPRINT_SERIES_KEY,
    REPRINTS_KEY,
    SERIES_KEY,
)
from comicbox.transforms.metroninfo.nested import MetronInfoTransformNestedTags
from comicbox.transforms.xml_reprints import reprint_to_filename


class MetronInfoTransformReprints(MetronInfoTransformNestedTags):
    """MetronInfo.xml Reprints Transform."""

    @classmethod
    def _parse_reprint(cls, data, metron_reprint) -> tuple[str, dict]:
        """Parse a metron Reprint."""
        comicbox_reprint = {}
        name = get_cdata(metron_reprint)
        if not name:
            return "", comicbox_reprint
        fn_dict = comicfn2dict(name)
        series = fn_dict.get(SERIES_KEY)
        if series:
            comicbox_reprint[REPRINT_SERIES_KEY] = {NAME_KEY: series}
        issue = fn_dict.get(ISSUE_KEY)
        if issue is not None:
            comicbox_reprint[REPRINT_ISSUE_KEY] = issue
        cls._parse_metron_id_attribute(
            data, "reprint", metron_reprint, comicbox_reprint
        )
        return name, comicbox_reprint

    def parse_reprints(self, data):
        """Parse a metron Reprint."""
        return self._parse_metron_tag(
            data, self.REPRINTS_TAG, self._parse_reprint, list_type=True
        )

    @classmethod
    def _unparse_reprint(cls, data, _, comicbox_reprint) -> dict:
        """Unparse a structured comicbox reprints into metron reprint."""
        name = reprint_to_filename(comicbox_reprint)
        if not name:
            return {}
        metron_reprint = {"#text": name}
        cls._unparse_metron_id_attribute(data, metron_reprint, comicbox_reprint)
        return metron_reprint

    def unparse_reprints(self, data):
        """Unparse reprint structures into metron reprint names."""
        return self._unparse_metron_tag(
            data, REPRINTS_KEY, self._unparse_reprint, list_type=True
        )
