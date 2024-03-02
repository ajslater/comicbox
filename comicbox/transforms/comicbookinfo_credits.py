"""Comic Book Info Credits Transform Mixin."""

from logging import getLogger
from types import MappingProxyType

from comicbox.schemas.comicbookinfo import (
    COLORER_TAG,
    COVER_ARTIST_TAG,
    CREDITS_TAG,
    EDITOR_TAG,
    INKER_TAG,
    LETTERER_TAG,
    OTHER_TAG,
    PENCILLER_TAG,
    PERSON_TAG,
    ROLE_TAG,
    WRITER_TAG,
)
from comicbox.schemas.comicbox_mixin import (
    COLORIST_KEY,
    CONTRIBUTORS_KEY,
    COVER_ARTIST_KEY,
    CREATOR_KEY,
    EDITOR_KEY,
    INKER_KEY,
    LETTERER_KEY,
    PENCILLER_KEY,
    WRITER_KEY,
)

LOG = getLogger(__name__)


class ComicBookInfoCreditsTransformMixin:
    """Comic Book Info Credits Transform Mixin."""

    # comicbookinfo and comictagger use the same tag names
    CREDITS_TAG = CREDITS_TAG
    ROLE_TAG = ROLE_TAG
    PERSON_TAG = PERSON_TAG
    CONTRIBUTOR_COMICBOX_MAP = MappingProxyType(
        {
            # ARTIST_TAG: PENCILLER_KEY,
            COLORER_TAG: COLORIST_KEY,
            COVER_ARTIST_TAG: COVER_ARTIST_KEY,
            EDITOR_TAG: EDITOR_KEY,
            INKER_TAG: INKER_KEY,
            LETTERER_TAG: LETTERER_KEY,
            OTHER_TAG: CREATOR_KEY,
            PENCILLER_TAG: PENCILLER_KEY,
            WRITER_TAG: WRITER_KEY,
        }
    )
    CONTRIBUTOR_SCHEMA_MAP = MappingProxyType(
        {
            COLORIST_KEY: COLORER_TAG,
            COVER_ARTIST_KEY: COVER_ARTIST_TAG,
            EDITOR_KEY: EDITOR_TAG,
            INKER_KEY: INKER_TAG,
            LETTERER_KEY: LETTERER_TAG,
            PENCILLER_KEY: PENCILLER_TAG,
            WRITER_KEY: WRITER_TAG,
        }
    )

    def _get_comicbox_role(self, credit_dict):
        """Consolidate credit tags."""
        extra_credit = None
        cbi_role = credit_dict.get(self.ROLE_TAG)
        if not cbi_role:
            return None, extra_credit

        # Special extra credit if role is Artist
        if cbi_role == "Artist" and (person := credit_dict.get(self.PERSON_TAG)):
            inker_dict = {self.ROLE_TAG: "Inker", self.PERSON_TAG: person}
            extra_credit = inker_dict
            cbi_role = "Penciller"

        comicbox_role = self.CONTRIBUTOR_COMICBOX_MAP.get(cbi_role)  # type: ignore
        return comicbox_role, extra_credit

    def _aggregate_contributor(self, contributors, credit_dict):
        extra_credit = None
        try:
            person = credit_dict.get(self.PERSON_TAG)
            if not person:
                return extra_credit
            comicbox_role, extra_credit = self._get_comicbox_role(credit_dict)
            if not comicbox_role:
                return extra_credit

            if comicbox_role not in contributors:
                contributors[comicbox_role] = set()
            contributors[comicbox_role].add(person)
        except Exception:
            LOG.exception(f"{self._path} Could not parse credit: {credit_dict}")  # type: ignore
        return extra_credit

    def aggregate_contributors(self, data):
        """Aggregate dict from comicbookinfo style list."""
        if not data.get(self.CREDITS_TAG):
            return data
        credits_list = data.pop(self.CREDITS_TAG)
        contributors = {}
        for credit_dict in credits_list:
            add_credit = credit_dict
            while add_credit:
                add_credit = self._aggregate_contributor(contributors, add_credit)
        if contributors:
            data[CONTRIBUTORS_KEY] = contributors
        return data

    def disaggregate_contributors(self, data):
        """Create comicbookinfo style list from dict."""
        if CONTRIBUTORS_KEY not in data:
            return data
        contributors = data.pop(CONTRIBUTORS_KEY, {})
        credits_list = []
        for comicbox_role, comicbox_persons in contributors.items():
            for person in comicbox_persons:
                try:
                    cbi_role = self.CONTRIBUTOR_SCHEMA_MAP.get(comicbox_role)
                    credit_dict = {self.ROLE_TAG: cbi_role, self.PERSON_TAG: person}
                    credits_list.append(credit_dict)
                except Exception as exc:
                    LOG.warning(
                        f"{self._path} Disaggregating credit"  # type: ignore
                        f" {comicbox_role}:{person} - {exc}"
                    )
        if credits_list:
            data[self.CREDITS_TAG] = credits_list
        return data
