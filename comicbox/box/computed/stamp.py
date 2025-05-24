"""Comicbox Computed tagger, updated_at and notes stamps."""

from datetime import datetime
from types import MappingProxyType

from comicbox.box.computed.pages import ComicboxComputedPages
from comicbox.fields.time_fields import DateTimeField
from comicbox.identifiers import ID_KEY_KEY, IdSources
from comicbox.identifiers.urns import to_urn_string
from comicbox.merge import ReplaceMerger
from comicbox.schemas.comicbox import (
    IDENTIFIERS_KEY,
    NOTES_KEY,
    TAGGER_KEY,
    UPDATED_AT_KEY,
)


class ComicboxComputedStamp(ComicboxComputedPages):
    """Comicbox Computed tagger, updated_at and notes stamps."""

    def _get_unparsed_comictagger_style_notes(self, sub_data):
        """Build notes from other tags."""
        notes = ""
        if sub_data and (tagger := sub_data.get(TAGGER_KEY)):
            notes += f"Tagged with {tagger}"

        if (
            sub_data
            and (updated_at := sub_data.get(UPDATED_AT_KEY))
            and (ts := DateTimeField()._serialize(updated_at))  # noqa: SLF001
        ):
            notes += f" on {ts}"

        if sub_data and (
            comicvine_id := sub_data.get(IDENTIFIERS_KEY, {})
            .get(IdSources.COMICVINE.value, {})
            .get(ID_KEY_KEY)
        ):
            notes += f" [Issue ID {comicvine_id}]"
        return notes

    def _get_unparsed_urns_for_notes(self, sub_data):
        """Unparse all types."""
        notes = ""
        if not sub_data:
            return notes
        identifiers = sub_data.get(IDENTIFIERS_KEY)
        if not identifiers:
            return notes
        urn_strs = set()
        # The are issues which is the default type.
        id_type = ""
        for id_source, identifier in identifiers.items():
            id_key = identifier.get(ID_KEY_KEY)
            if not id_key:
                continue
            urn_str = to_urn_string(id_source, id_type, id_key)
            urn_strs.add(urn_str)
        notes += " ".join(sorted(urn_strs))
        return notes

    def _get_computed_notes_stamp(self, sub_data, stamp_md):
        """Write comicbox notes to notes field if present."""
        if not self._config.stamp_notes or NOTES_KEY in self._config.delete_keys:
            return None
        if identifiers := sub_data.get(IDENTIFIERS_KEY):
            stamp_md[IDENTIFIERS_KEY] = identifiers

        comictagger_style_notes = self._get_unparsed_comictagger_style_notes(stamp_md)
        urn_notes = self._get_unparsed_urns_for_notes(stamp_md)
        notes = f"{comictagger_style_notes} {urn_notes}"
        return notes.strip()

    def _get_tagger_stamp(self, sub_data):
        """Stamp when writing or explicitly told to."""
        if not (
            self._config.stamp
            or self._config.computed.all_write_formats
            or self._config.cbz
            or self._config.export
        ):
            return None

        stamp_md = {}
        if TAGGER_KEY not in self._config.delete_keys:
            stamp_md[TAGGER_KEY] = self._config.tagger

        if UPDATED_AT_KEY not in self._config.delete_keys:
            # Deprecated method needed for python 3.10
            # Update after 2026-11
            stamp_md[UPDATED_AT_KEY] = datetime.utcnow()  # noqa: DTZ003, # pyright: ignore[reportDeprecated]

        if notes := self._get_computed_notes_stamp(sub_data, stamp_md):
            stamp_md[NOTES_KEY] = notes

        if not stamp_md:
            return None

        return stamp_md

    COMPUTED_ACTIONS = MappingProxyType(
        {
            **ComicboxComputedPages.COMPUTED_ACTIONS,
            "Tagger Stamp": (_get_tagger_stamp, ReplaceMerger),
        }
    )
