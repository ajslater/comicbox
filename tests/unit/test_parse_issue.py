"""Test issue parsing."""

from comicbox.fields.fields import IssueField

ISSUES = {
    "3": ("3", " 3", " 3 ", "3."),
    "3.0": ("3.0",),
    "4AU": (" #004AU",),
    "4.0": ("004.0",),
    "1.5": ("1½", "1 1/2"),
}


def test_parse_issue():
    """Test many issue variations."""
    for result, issue_list in ISSUES.items():
        for issue in issue_list:
            assert result == IssueField.parse_issue(issue)
