"""Test getting pages."""

from argparse import Namespace
from types import MappingProxyType

import pytest
from deepdiff import DeepDiff
from icecream import ic

from comicbox.box import Comicbox
from comicbox.config import get_config
from comicbox.schemas.comicbox import STORIES_KEY, TITLE_KEY

STORIES = {"a": {"identifiers": {"comicvine": {"key": "123"}}}, "d": {}}
TITLE = "a; b; c"
TITLE_FROM_STORIES = "a; d"
ALL_STORIES = {"b": {}, "c": {}, **STORIES}

FIXTURES = MappingProxyType(
    {
        "No Stories, No Title": ((False, False), MappingProxyType({"comicbox": {}})),
        "Yes Stories, No Title": (
            (True, False),
            MappingProxyType(
                {"comicbox": {STORIES_KEY: STORIES, TITLE_KEY: TITLE_FROM_STORIES}}
            ),
        ),
        "No Stories, Yes Title": (
            (False, True),
            MappingProxyType(
                {
                    "comicbox": {
                        STORIES_KEY: {"a": {}, "b": {}, "c": {}},
                        TITLE_KEY: TITLE,
                    }
                }
            ),
        ),
        "Yes Stories, Yes Title": (
            (True, True),
            MappingProxyType(
                {"comicbox": {STORIES_KEY: ALL_STORIES, TITLE_KEY: TITLE_FROM_STORIES}}
            ),
        ),
    }
)
PRINT_CONFIG = get_config(Namespace(comicbox=Namespace(print="snmcp")))


@pytest.mark.parametrize("label", FIXTURES)
def test_story_title_combo(label):
    """Test metadata mtime."""
    row = FIXTURES[label]
    values, md_out = row
    use_stories, use_title = values

    md_in = {}
    if use_stories:
        md_in[STORIES_KEY] = STORIES
    if use_title:
        md_in[TITLE_KEY] = TITLE
    md_in = {"comicbox": md_in}

    with Comicbox(metadata=md_in, config=PRINT_CONFIG) as car:
        # car.print_out() debug
        md = car.get_metadata()

    diff = DeepDiff(md_out, md)

    if diff:
        ic(diff)
        ic(md)
    assert not diff
