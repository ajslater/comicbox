"""A class to encapsulate ComicRack's ComicInfo.xml data."""

from itertools import zip_longest
from logging import getLogger

from comicbox.schemas.comicbox_mixin import ARCS_KEY, NUMBER_KEY
from comicbox.transforms.transform_map import KeyTransforms, MultiAssigns

LOG = getLogger(__name__)


def _story_arcs_to_arcs(
    source_data: dict, ci_story_arcs: list[str], story_arc_number_tag: str
):
    if story_arc_number_tag:
        ci_story_arc_numbers: list | tuple = source_data.get(story_arc_number_tag, [])
        ci_story_arc_numbers = ci_story_arc_numbers[: len(ci_story_arcs)]
    else:
        ci_story_arc_numbers = []

    comicbox_arcs = {}
    zipped_itr = zip_longest(ci_story_arcs, ci_story_arc_numbers, fillvalue=None)
    for name, number in zipped_itr:
        arc = {}
        try:
            if number is not None:
                arc[NUMBER_KEY] = number
        except Exception:
            LOG.exception(f"Deserialize story_arc_number{name}:{number}")
        comicbox_arcs[name] = arc
    return comicbox_arcs


def _arcs_to_story_arcs(
    comicbox_arcs: dict[str, dict[str, int]], story_arc_number_tag: str
):
    ci_story_arcs = []
    ci_story_arc_numbers = []
    for name, comicbox_arc in comicbox_arcs.items():
        if name:
            ci_story_arcs.append(name)
            if not comicbox_arc:
                continue
            number = comicbox_arc.get(NUMBER_KEY)
            num_str = "" if number is None else str(number)
            ci_story_arc_numbers.append(num_str)
    if story_arc_number_tag and ci_story_arc_numbers:
        result = MultiAssigns(
            value=ci_story_arcs,
            extra_assigns=((story_arc_number_tag, ci_story_arc_numbers),),
        )
    else:
        result = ci_story_arcs
    return result


def story_arcs_transform(story_arc_tag, story_arc_number_tag):
    """Aggregate and dissagregate ComicInfo StoryArcs & StoryArcNumbers to arcs."""

    def to_cb(source_data, ci_story_arcs):
        return _story_arcs_to_arcs(source_data, ci_story_arcs, story_arc_number_tag)

    def from_cb(_source_data, comicbox_arcs):
        return _arcs_to_story_arcs(comicbox_arcs, story_arc_number_tag)

    return KeyTransforms(
        key_map={
            story_arc_tag: ARCS_KEY,
        },
        to_cb=to_cb,
        from_cb=from_cb,
    )
