"""Test issue parsing."""

from comicbox.formats.base.fields.fields import IssueField

ISSUES = {
    "3": ("3", " 3", " 3 ", "3."),
    "3.0": ("3.0",),
    "4AU": (" #004AU",),
    "4.0": ("004.0",),
    "1.5": ("1½", "1 1/2"),
    "0": ("0", "000"),
    "0.0": ("0.0",),
}


def test_parse_issue() -> None:
    """Test many issue variations."""
    for result, issue_list in ISSUES.items():
        for issue in issue_list:
            assert result == IssueField.parse_issue(issue)


SPLITS = {
    "4AU": ("4", "AU"),
    "1.MU": ("1.", "MU"),
    ".5": (".5", ""),
    "3.0": ("3.0", ""),
    "Annual": ("", "Annual"),
    "": ("", ""),
    # A minus belongs to the number when a number follows it (B10).
    "-1": ("-1", ""),
    "-1AU": ("-1", "AU"),
    "-.5": ("-.5", ""),
    "-AU": ("", "-AU"),
    "-": ("", "-"),
    "1-2": ("1", "-2"),
}


def test_split_issue() -> None:
    """The leading number and the suffix after it."""
    for name, parts in SPLITS.items():
        assert IssueField.split_issue(name) == parts


def test_a_comic_numbered_minus_one_has_that_number() -> None:
    """B10: issue -1 got no number, and -1 as its suffix."""
    from decimal import Decimal

    from comicbox.box import Comicbox

    for name, number, suffix in (
        ("-1", Decimal(-1), None),
        ("-1AU", Decimal(-1), "AU"),
    ):
        metadata = {"comicbox": {"series": {"name": "X"}, "issue": {"name": name}}}
        with Comicbox(metadata=metadata) as box:
            issue = box.to_dict()["comicbox"]["issue"]
        assert issue.get("number") == number
        assert issue.get("suffix") == suffix
