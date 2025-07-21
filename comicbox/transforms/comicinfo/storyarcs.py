"""A class to encapsulate ComicRack's ComicInfo.xml data."""

from collections.abc import Mapping
from itertools import zip_longest

from glom import Coalesce, Iter, T

from comicbox.schemas.comicbox import ARCS_KEY, NUMBER_KEY
from comicbox.transforms.spec import MetaSpec


def _story_arcs_to_arcs(story_arc_tag, story_arc_number_tag, values: Mapping):
    comicbox_arcs = {}
    ci_story_arcs = values.get(story_arc_tag)
    if not ci_story_arcs:
        return comicbox_arcs
    if ci_story_arc_numbers := values.get(story_arc_number_tag):
        ci_story_arc_numbers = ci_story_arc_numbers[: len(ci_story_arcs)]
    if not ci_story_arc_numbers:
        ci_story_arc_numbers = []
    zipped_itr = zip_longest(ci_story_arcs, ci_story_arc_numbers, fillvalue=None)
    for zipped_tuple in zipped_itr:
        name, number = zipped_tuple
        arc = {}
        if number is not None:
            arc[NUMBER_KEY] = number
        comicbox_arcs[name] = arc
    return comicbox_arcs


def story_arcs_to_cb(story_arc_tag, story_arc_number_tag):
    """Aggregate and dissagregate ComicInfo StoryArcs & StoryArcNumbers to arcs."""

    def to_cb(values):
        return _story_arcs_to_arcs(story_arc_tag, story_arc_number_tag, values)

    source_tags = tuple(tag for tag in (story_arc_tag, story_arc_number_tag) if tag)
    return MetaSpec(key_map={ARCS_KEY: source_tags}, spec=to_cb)


def story_arcs_from_cb(story_arc_tag, story_arc_number_tag):
    """Transform comicbox arcs to comicinfo story arc and story arc number."""
    metaspecs = []
    if story_arc_tag:
        ms = MetaSpec(
            key_map={
                story_arc_tag: ARCS_KEY,
            },
            spec=(Iter().all(),),
        )
        metaspecs.append(ms)
    if story_arc_number_tag:
        ms = MetaSpec(
            key_map={
                story_arc_number_tag: ARCS_KEY,
            },
            spec=(
                Coalesce(T.values()),
                Iter().map(NUMBER_KEY).all(),
            ),
        )
        metaspecs.append(ms)
    return tuple(metaspecs)
