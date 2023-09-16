"""A class to encapsulate ComicRack's ComicInfo.xml data."""
from copy import deepcopy
from itertools import zip_longest
from logging import getLogger

from marshmallow import post_load, pre_dump

from comicbox.fields.collections import (
    StringListField,
)
from comicbox.fields.numbers import IntegerField
from comicbox.schemas.comicbox_base import (
    STORY_ARCS_KEY,
)
from comicbox.schemas.decorators import trap_error

LOG = getLogger(__name__)

STORY_ARC_KEY = "story_arc"
STORY_ARC_NUMBER_KEY = "story_arc_number"


class ComicInfoStoryArcsSchemaMixin:
    """ComicInfo.xml Schema."""

    story_arc = StringListField(as_string=True, sort=False)
    story_arc_number = StringListField(as_string=True, sort=False)

    @trap_error(post_load)
    def aggregate_story_arcs(self, data, **_kwargs):
        """Aggregate StoryArc and StoryArcNumber csvs into dict."""
        if STORY_ARC_KEY not in data:
            return data
        data = deepcopy(dict(data))
        ci_story_arcs = data.pop(STORY_ARC_KEY, [])
        if not ci_story_arcs:
            return data
        ci_story_arc_numbers = data.pop(STORY_ARC_NUMBER_KEY, [])

        integer_field = IntegerField()
        story_arcs = {}
        zipped_itr = zip_longest(ci_story_arcs, ci_story_arc_numbers, fillvalue=None)
        for name, number_str in zipped_itr:
            try:
                if number_str is None:
                    number = None
                else:
                    number = integer_field.deserialize(number_str)
            except Exception:
                LOG.exception(
                    f"{self._path}:"  # type: ignore
                    f" Deserialize story_arc_number{name}:{number_str}"
                )
                number = None
            story_arcs[name] = number

        data[STORY_ARCS_KEY] = story_arcs
        return data

    @pre_dump
    def disaggregate_story_arcs(self, data, **_kwargs):
        """Disaggregate story_arcs into StoryArc and StoryArcNumber csv tags."""
        if STORY_ARCS_KEY not in data:
            return data
        data = deepcopy(dict(data))
        story_arcs = data.pop(STORY_ARCS_KEY, {})
        if not story_arcs:
            return data

        ci_story_arcs = []
        ci_story_arc_numbers = []
        for name, number in story_arcs.items():
            if name:
                ci_story_arcs.append(name)
                num_str = "" if number is None else str(number)
                ci_story_arc_numbers.append(num_str)
        if ci_story_arcs:
            data[STORY_ARC_KEY] = ci_story_arcs
            if ci_story_arc_numbers:
                data[STORY_ARC_NUMBER_KEY] = ci_story_arc_numbers
        return data
