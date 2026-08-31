"""The computed pipeline's order is a contract, so it is asserted here."""

from unittest.mock import patch

from comicbox.box import Comicbox
from comicbox.box.computed import ComicboxComputed
from comicbox.merge import AdditiveMerger, ReplaceMerger

# The exact pipeline, in order. Every entry is a decision — see the
# comicbox.box.computed module docstring for why each one sits where it does.
# Changing this list means changing behavior; changing it by accident, which
# splicing the order together across nine class bodies invited, means changing
# behavior by accident.
EXPECTED_ACTIONS = (
    ("Page Count", "_get_computed_page_count_metadata", ReplaceMerger),
    ("Pages", "_get_computed_pages_metadata", ReplaceMerger),
    ("urls from notes", "_get_computed_urls_from_notes", AdditiveMerger),
    ("identifiers from urls", "_get_computed_identifiers_from_urls", AdditiveMerger),
    ("from notes", "get_computed_from_notes", AdditiveMerger),
    ("from tags", "_get_computed_from_tags", AdditiveMerger),
    ("normalize identifier keys", "_normalize_all_identifier_keys", AdditiveMerger),
    ("urls", "_get_computed_urls", ReplaceMerger),
    ("Tagger Stamp", "_get_tagger_stamp", ReplaceMerger),
    ("from manga_volume", "_get_computed_from_manga_volume", AdditiveMerger),
    ("from issue", "_get_computed_from_issue", AdditiveMerger),
    ("from issue.number & issue.suffix", "_get_computed_issue", AdditiveMerger),
    ("from alternative_issue", "_get_computed_from_alternative_issue", AdditiveMerger),
    (
        "from alternative_issue.number & alternative_issue.suffix",
        "_get_computed_alternative_issue",
        AdditiveMerger,
    ),
    ("from date", "_get_computed_from_date", AdditiveMerger),
    ("from title", "_get_computed_from_title", AdditiveMerger),
    ("from stories", "_get_computed_from_stories", AdditiveMerger),
    ("from reprint names", "_get_computed_from_reprint_names", ReplaceMerger),
    ("from reprints", "_get_computed_from_reprints", ReplaceMerger),
    ("from scan_info", "_get_computed_from_scan_info", AdditiveMerger),
    ("Delete Keys", "_get_delete_keys", None),
)


def test_computed_action_order() -> None:
    """The registry is the pipeline, in the exact order it runs."""
    actions = tuple(
        (action.label, action.method_name, action.merger)
        for action in ComicboxComputed.COMPUTED_ACTIONS
    )
    assert actions == EXPECTED_ACTIONS


def test_computed_action_methods_resolve() -> None:
    """Every registered name is a real method on the box."""
    with Comicbox() as car:
        for action in ComicboxComputed.COMPUTED_ACTIONS:
            method = getattr(car, action.method_name, None)
            assert callable(method), action.method_name


def test_computed_action_labels_are_unique() -> None:
    """Labels name a phase in --print output, so two may not collide."""
    labels = [action.label for action in ComicboxComputed.COMPUTED_ACTIONS]
    assert len(labels) == len(set(labels))


def test_computed_actions_dispatch_through_the_instance() -> None:
    """
    An override of a computed method is the one that runs.

    The registry used to hold the plain function objects lifted out of each
    class body, so dispatch bypassed the instance entirely and an override was
    silently never called.
    """
    sentinel = {"title": "overridden"}
    with (
        Comicbox() as car,
        patch.object(car, "_get_computed_from_title", return_value=sentinel) as mock,
    ):
        car.get_computed_metadata()
    assert mock.call_count == 1
