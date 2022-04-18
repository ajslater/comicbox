from comicbox.metadata.comic_base import ComicBaseMetadata


ISSUES = {
    "3": ("3", " 3", " 3 ", "3."),
    "3.0": ("3.0",),
    "4AU": (" #004AU",),
    "4.0": ("004.0",),
    "1.5": ("1½", "1 1/2"),
}


def test_parse_issue():
    for result, issue_list in ISSUES.items():
        for issue in issue_list:
            assert result == ComicBaseMetadata.parse_issue(issue)
