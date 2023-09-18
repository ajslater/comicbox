"""Parse comic book archive names using the simple 'parse' parser."""
import re
from pathlib import Path
from typing import Union

from comicfn2dict.regex import (
    DASH_SPLIT_RE,
    EXTRA_SPACES_RE,
    ISSUE_ANYWHERE_RE,
    ISSUE_BEGIN_RE,
    ISSUE_COUNT_RE,
    ISSUE_END_RE,
    ISSUE_NUMBER_RE,
    ISSUE_TOKEN_RE,
    NON_SPACE_DIVIDER_RE,
    ORIGINAL_FORMAT_RE,
    ORIGINAL_FORMAT_SCAN_INFO_RE,
    REMAINING_GROUP_RE,
    SCAN_INFO_RE,
    VOLUME_RE,
    YEAR_BEGIN_RE,
    YEAR_END_RE,
    YEAR_TOKEN_RE,
)

_REMAINING_GROUP_KEYS = ("series", "title")


def _parse_ext(name, suffix, metadata):
    """Pop the extension from the pathname."""
    data = name.removesuffix(suffix)
    metadata["ext"] = suffix.lstrip(".")
    return data


def _clean_dividers(data):
    """Replace non space dividers and clean extra spaces out of string."""
    data = NON_SPACE_DIVIDER_RE.sub(" ", data)
    return EXTRA_SPACES_RE.sub(" ", data)


def _get_data_list(path, metadata):
    """Prepare data list from a path or string."""
    if isinstance(path, str):
        path = path.strip()
    path = Path(path)
    data = _parse_ext(path.name, path.suffix, metadata)
    data = _clean_dividers(data)
    return DASH_SPLIT_RE.split(data)


def _paren_strip(value: str):
    """Strip spaces and parens."""
    return value.strip().strip("()").strip()


def _splicey_dicey(data_list, index, match, match_group: Union[int, str] = 0):
    """Replace a string token from a list with two strings and the value removed.

    And return the value.
    """
    value = match.group(match_group)
    data = data_list.pop(index)
    data_ends = []
    if data_before := data[: match.start()].strip():
        data_ends.append(data_before)
    if data_after := data[match.end() :].strip():
        data_ends.append(data_after)
    data_list[index:index] = data_ends
    return _paren_strip(value)


def _parse_original_format_and_scan_info(data_list, metadata):
    """Parse (ORIGINAL_FORMAT-SCAN_INFO)."""
    original_format = None
    scan_info = None
    index = 0
    match = None
    for data in data_list:
        match = ORIGINAL_FORMAT_SCAN_INFO_RE.search(data)
        if match:
            original_format = match.group("original_format")
            try:
                scan_info = match.group("scan_info")
            except IndexError:
                scan_info = None
            break
        index += 1
    if original_format:
        metadata["original_format"] = _paren_strip(original_format)
        match_group = 1
        if scan_info:
            metadata["scan_info"] = _paren_strip(scan_info)
            match_group = 0
        _splicey_dicey(data_list, index, match, match_group=match_group)
    else:
        index = 0
    return index


def _pop_value_from_token(
    data_list: list,
    metadata: dict,
    regex: re.Pattern,
    key: str,
    index: int = 0,
):
    """Search token for value, splice and assign to metadata."""
    data = data_list[index]
    match = regex.search(data)
    if match:
        value = _splicey_dicey(data_list, index, match, key)
        metadata[key] = value
    return match


def _parse_item(
    data_list,
    metadata,
    regex,
    key,
    start_index: int = 0,
):
    """Parse a value from the data list into metadata and alter the data list."""
    index = start_index
    dl_len = end_index = len(data_list)
    if index >= end_index:
        index = 0
    while index < end_index:
        match = _pop_value_from_token(data_list, metadata, regex, key, index)
        if match:
            break
        index += 1
        if index > dl_len and start_index > 0:
            index = 0
            end_index = start_index
    return index


def _pop_issue_from_text_fields(data_list, metadata, index):
    """Search issue from ends of text fields."""
    if "issue" not in metadata:
        _pop_value_from_token(data_list, metadata, ISSUE_END_RE, "issue", index=index)
    if "issue" not in metadata:
        _pop_value_from_token(data_list, metadata, ISSUE_BEGIN_RE, "issue", index=index)
    return data_list.pop(index)


def _assign_remaining_groups(data_list, metadata):
    """Assign series and title."""
    index = 0
    for key in _REMAINING_GROUP_KEYS:
        try:
            data = data_list[index]
        except (IndexError, TypeError):
            break
        match = REMAINING_GROUP_RE.search(data) if data else None
        if match:
            value = _pop_issue_from_text_fields(data_list, metadata, index)
            value = _paren_strip(value)
            if value:
                metadata[key] = value
        else:
            index += 1


def _pickup_issue(remainders, metadata):
    """Get issue from remaining tokens or anywhere in a pinch."""
    if "issue" in metadata:
        return
    _parse_item(remainders, metadata, ISSUE_TOKEN_RE, "issue")
    if "issue" in metadata:
        return
    _parse_item(remainders, metadata, ISSUE_ANYWHERE_RE, "issue")


def parse(path):
    """Parse the filename with a hierarchy of regexes."""
    metadata = {}
    data_list = _get_data_list(path, metadata)

    # Parse paren tokens
    _parse_item(data_list, metadata, ISSUE_COUNT_RE, "issue_count")
    _parse_item(data_list, metadata, YEAR_TOKEN_RE, "year")
    of_index = _parse_original_format_and_scan_info(data_list, metadata)
    if "original_format" not in metadata:
        of_index = _parse_item(
            data_list, metadata, ORIGINAL_FORMAT_RE, "original_format"
        )
    if "scan_info" not in metadata:
        # Start searching for scan_info after original format.
        _parse_item(
            data_list,
            metadata,
            SCAN_INFO_RE,
            "scan_info",
            start_index=of_index + 1,
        )

    # Parse regular tokens
    _parse_item(data_list, metadata, VOLUME_RE, "volume")
    _parse_item(data_list, metadata, ISSUE_NUMBER_RE, "issue")

    # Pickup year if not gotten.
    if "year" not in metadata:
        _parse_item(data_list, metadata, YEAR_BEGIN_RE, "year")
    if "year" not in metadata:
        _parse_item(data_list, metadata, YEAR_END_RE, "year")

    # Pickup issue if it's a standalone token
    if "issue" not in metadata:
        _parse_item(data_list, metadata, ISSUE_TOKEN_RE, "issue")

    # Series and Title. Also looks for issue.
    _assign_remaining_groups(data_list, metadata)

    # Final try for issue number.
    _pickup_issue(data_list, metadata)

    # Add Remainders
    if data_list:
        metadata["remainders"] = tuple(data_list)

    return metadata
