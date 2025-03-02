"""A class to encapsulate ComicRack's ComicInfo.xml data."""

from itertools import zip_longest
from logging import getLogger

from comicbox.fields.number_fields import IntegerField
from comicbox.schemas.comicbox_mixin import ARCS_KEY, NUMBER_KEY
from comicbox.transforms.base import BaseTransform

LOG = getLogger(__name__)


class ComicInfoStoryArcsTransformMixin(BaseTransform):
    """ComicInfo.xml StoryArcs Schema Mixin."""

    STORY_ARC_TAG = "StoryArc"
    STORY_ARC_NUMBER_TAG = "StoryArcNumber"

    def parse_arcs(self, data):
        """Aggregate StoryArc and StoryArcNumber csvs into dict."""
        ci_story_arcs = data.pop(self.STORY_ARC_TAG, [])
        if not ci_story_arcs:
            return data
        if self.STORY_ARC_NUMBER_TAG:
            ci_story_arc_numbers = data.pop(self.STORY_ARC_NUMBER_TAG, [])
            ci_story_arc_numbers = ci_story_arc_numbers[: len(ci_story_arcs)]
        else:
            ci_story_arc_numbers = []

        integer_field = IntegerField()
        comicbox_arcs = {}
        zipped_itr = zip_longest(ci_story_arcs, ci_story_arc_numbers, fillvalue=None)
        for name, number_str in zipped_itr:
            try:
                if number_str is None:
                    number = None
                else:
                    number = integer_field.deserialize(number_str)
            except Exception:
                LOG.exception(
                    f"{self._path}: Deserialize story_arc_number{name}:{number_str}"
                )
                number = None
            comicbox_arcs[name] = {NUMBER_KEY: number}

        data[ARCS_KEY] = comicbox_arcs
        return data

    def unparse_arcs(self, data):
        """Disaggregate arcs into StoryArc and StoryArcNumber csv tags."""
        comicbox_arcs = data.pop(ARCS_KEY, {})
        if not comicbox_arcs:
            return data

        ci_story_arcs = []
        ci_story_arc_numbers = []
        for name, comicbox_arc in comicbox_arcs.items():
            if name:
                ci_story_arcs.append(name)
                number = comicbox_arc.get(NUMBER_KEY)
                num_str = "" if number is None else str(number)
                ci_story_arc_numbers.append(num_str)
        if ci_story_arcs:
            data[self.STORY_ARC_TAG] = ci_story_arcs
            if self.STORY_ARC_NUMBER_TAG and ci_story_arc_numbers:
                data[self.STORY_ARC_NUMBER_TAG] = ci_story_arc_numbers
        return data
