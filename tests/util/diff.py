"""Diff-based assertion helpers for tests."""

from difflib import ndiff
from pprint import pprint
from typing import Any

from deepdiff.diff import DeepDiff


def assert_diff_strings(a: str, b: str) -> None:
    """Debug string diffs."""
    if a != b:
        diff = tuple(ndiff(a.splitlines(keepends=True), b.splitlines(keepends=True)))
        if diff:
            print("".join(diff), end="")  # noqa: T201
        for i, s in enumerate(diff):
            if s[0] == " ":
                continue
            if s[0] == "-":
                print(f'Delete "{s[-1]}" from position {i}')  # noqa: T201
            elif s[0] == "+":
                print(f'Add "{s[-1]}" to position {i}')  # noqa: T201
        assert not diff
    else:
        assert a == b


def assert_diff(old_map: Any, new_map: Any) -> None:
    """Assert no diff and print if there is."""
    if diff := DeepDiff(old_map, new_map, ignore_order=True):
        pprint(old_map)
        pprint(new_map)
        pprint(diff)
    assert not diff
