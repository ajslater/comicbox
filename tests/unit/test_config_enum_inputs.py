"""
Enum-valued config keys accept their enum members, not just strings.

Each key is parsed with ``parse_enum(..., str(raw))``. While these enums
were ``(str, Enum)`` mixins, ``str(MatchMode.EAGER)`` rendered as
``"MatchMode.EAGER"``, so an embedder passing a member in a Mapping
config got a ValueError naming its own valid value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from comicbox.config import get_config
from comicbox.config.online.settings import CacheMode, Effort, MatchMode, Prompts
from comicbox.config.settings import MergeMode

if TYPE_CHECKING:
    from collections.abc import Callable
    from enum import StrEnum

    from comicbox.config.settings import ComicboxSettings


@pytest.mark.parametrize(
    ("block", "member", "read"),
    [
        (
            {"write": {"merge_mode": MergeMode.REPLACE}},
            MergeMode.REPLACE,
            lambda s: s.write.merge_mode,
        ),
        (
            {"online": {"lookup": {"match": MatchMode.EAGER}}},
            MatchMode.EAGER,
            lambda s: s.online.lookup.match,
        ),
        (
            {"online": {"lookup": {"prompts": Prompts.NEVER}}},
            Prompts.NEVER,
            lambda s: s.online.lookup.prompts,
        ),
        (
            {"online": {"cache": {"mode": CacheMode.REFRESH}}},
            CacheMode.REFRESH,
            lambda s: s.online.cache.mode,
        ),
        (
            {"online": {"tuning": {"effort": Effort.THOROUGH}}},
            Effort.THOROUGH,
            lambda s: s.online.tuning.effort,
        ),
    ],
    ids=["merge_mode", "match", "prompts", "cache", "effort"],
)
def test_mapping_config_accepts_enum_members(
    block: dict[str, object],
    member: StrEnum,
    read: Callable[[ComicboxSettings], StrEnum | None],
) -> None:
    """A member parses to itself, exactly as its string value does."""
    settings = get_config({"comicbox": block})
    assert read(settings) is member
