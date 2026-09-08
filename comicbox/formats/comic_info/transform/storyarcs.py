"""A class to encapsulate ComicRack's ComicInfo.xml data."""

from collections.abc import Mapping
from contextlib import suppress
from itertools import zip_longest
from typing import Any

from glom import Coalesce, Iter, T

from comicbox.formats.base.transforms.spec import MetaSpec
from comicbox.formats.comicbox.schema import ARCS_KEY, NUMBER_KEY


def _story_arcs_to_arcs(
    story_arc_tag: str, story_arc_number_tag: str, values: Mapping
) -> dict:
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


def _alternates_to_arcs(
    alternate_series_tag: str, alternate_number_tag: str, values: Mapping
) -> dict:
    """
    Read ComicInfo's Alternate tags as the crossover arc they name.

    ComicInfo v1.0 had no StoryArc, so these were how a book recorded that it
    belonged to a crossover, which is what ComicRack documented them for and
    what Komga and Kavita still read them as. Comicbox finds those arcs in
    older files, and only ever writes arcs back to StoryArc.

    AlternateCount has no arc equivalent and nothing reads it, so it is
    dropped.
    """
    name = values.get(alternate_series_tag)
    if not name:
        return {}
    arc: dict[str, Any] = {}
    number = values.get(alternate_number_tag)
    if number is not None:
        # A non numeric position says nothing about order, so it is dropped.
        with suppress(ValueError):
            arc[NUMBER_KEY] = int(str(number).strip())
    return {str(name): arc}


def story_arcs_to_cb(
    story_arc_tag: str,
    story_arc_number_tag: str,
    alternate_series_tag: str = "",
    alternate_number_tag: str = "",
) -> MetaSpec:
    """Aggregate ComicInfo's two arc tag pairs into comicbox arcs."""

    def to_cb(
        values: dict[str, list[int] | list[str] | None],
    ) -> dict[str | Any, dict[str, int] | Any]:
        arcs = _story_arcs_to_arcs(story_arc_tag, story_arc_number_tag, values)
        if alternate_series_tag:
            for name, arc in _alternates_to_arcs(
                alternate_series_tag, alternate_number_tag, values
            ).items():
                arcs.setdefault(name, arc)
        return arcs

    source_tags = tuple(
        tag
        for tag in (
            story_arc_tag,
            story_arc_number_tag,
            alternate_series_tag,
            alternate_number_tag,
        )
        if tag
    )
    return MetaSpec(key_map={ARCS_KEY: source_tags}, spec=to_cb)


def story_arcs_from_cb(story_arc_tag: str, story_arc_number_tag: str) -> tuple:
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
