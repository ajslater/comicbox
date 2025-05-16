"""Comicbox Computed Issue tags."""

import re
from collections.abc import Callable
from types import MappingProxyType

from loguru import logger

from comicbox.box.computed.stamp import ComicboxComputedStamp
from comicbox.empty import is_empty
from comicbox.fields.comicbox import NAME_KEY
from comicbox.fields.fields import StringField
from comicbox.fields.number_fields import DecimalField
from comicbox.merge import AdditiveMerger, Merger
from comicbox.schemas.comicbox import (
    ISSUE_KEY,
    ISSUE_SUFFIX_KEY,
    NUMBER_KEY,
)

ISSUE_SUFFIX_KEYPATH = f"{ISSUE_KEY}.{ISSUE_SUFFIX_KEY}"
_PARSE_ISSUE_MATCHER = re.compile(r"(\d*\.?\d*)(.*)")


class ComicboxComputedIssue(ComicboxComputedStamp):
    """Comicbox Computed Issue tags."""

    def _parse_issue_match(self, match, old_issue_number, old_issue_suffix, issue):
        """Use regex match to break the issue into parts."""
        issue_number, issue_suffix = match.groups()
        if is_empty(old_issue_number) and not is_empty(issue_number):
            try:
                issue_number = DecimalField().deserialize(
                    issue_number, NUMBER_KEY, issue
                )
                issue[NUMBER_KEY] = issue_number
            except Exception as exc:
                logger.warning(f"{self._path} Parsing issue_number from issue {exc}")
        if not old_issue_suffix and issue_suffix:
            issue[ISSUE_SUFFIX_KEY] = StringField().deserialize(
                issue_suffix, ISSUE_SUFFIX_KEY, issue
            )

    def _get_computed_from_issue(self, sub_data, **_kwargs):
        """Break parsed issue up into parts."""
        if not sub_data:
            return None
        issue = sub_data.get(ISSUE_KEY)
        if not issue:
            return None
        issue_name = issue.get(NAME_KEY)
        old_issue_number = issue.get(NUMBER_KEY)
        old_issue_suffix = issue.get(ISSUE_SUFFIX_KEY)
        try:
            if (
                issue_name
                and (not is_empty(old_issue_number) or not old_issue_suffix)
                and (match := _PARSE_ISSUE_MATCHER.match(issue_name))
            ):
                self._parse_issue_match(
                    match, old_issue_number, old_issue_suffix, issue
                )
        except Exception:
            logger.debug(f"{self._path} Error parsing issue into components: {issue}")
            raise

        return {ISSUE_KEY: issue}

    def _get_computed_issue(self, sub_data, **_kwargs):
        """Build issue from parts before dump if issue doesn't already exist."""
        if not sub_data or ISSUE_KEY in self._config.delete_keys:
            return None
        issue = sub_data.get(ISSUE_KEY)
        if not issue:
            return None
        if issue_name := issue.get(NAME_KEY):
            return None
        issue_number = issue.get(NUMBER_KEY, "")
        issue_suffix = issue.get(ISSUE_SUFFIX_KEY, "")
        # Decimal removes unspecified decimal points
        if issue_name := f"{issue_number}{issue_suffix}".strip():
            issue[NAME_KEY] = issue_name
            return {ISSUE_KEY: issue}
        return None

    COMPUTED_ACTIONS: MappingProxyType[str, tuple[Callable, type[Merger] | None]] = (
        MappingProxyType(
            {
                **ComicboxComputedStamp.COMPUTED_ACTIONS,
                "from issue": (_get_computed_from_issue, AdditiveMerger),
                "from issue.number & issue.suffix": (
                    _get_computed_issue,
                    AdditiveMerger,
                ),
            }
        )
    )
