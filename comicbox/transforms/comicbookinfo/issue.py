"""Coimcbox integer issue transforms."""

from comicbox.schemas.comicbox import ISSUE_KEY
from comicbox.transforms.spec import MetaSpec

ISSUE_TAG = "issue"


def _to_cb_issue_transform(issue_number):
    return str(issue_number)


def issue_transform_to_cb():
    """Transform cbi integer issues to comicbox issue str and copy the issue number."""
    return MetaSpec(
        key_map={ISSUE_TAG: ISSUE_KEY},
        spec=_to_cb_issue_transform,
    )


def issue_transform_from_cb():
    """Transform cbi integer issues to comicbox issue str and copy the issue number."""
    return MetaSpec(
        key_map={ISSUE_TAG: ISSUE_TAG},
    )
