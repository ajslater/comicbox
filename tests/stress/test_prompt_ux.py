"""
Unit tests for the prompt-UX harness's pure functions.

The full pipeline path (monkeypatch + CLI invocation) needs real
fixtures + live APIs, so it's exercised by the harness itself in
live runs. These tests cover the overlap-detection logic — the bit
that decides pass/fail.
"""

from __future__ import annotations

from tests.stress.prompt_ux import PromptEvent, detect_overlaps


def _event(*, tid: int, enter: int, exit_: int, file: str = "f.cbz") -> PromptEvent:
    return PromptEvent(file_path=file, thread_id=tid, enter_ns=enter, exit_ns=exit_)


class TestDetectOverlaps:
    def test_no_events_yields_no_overlaps(self) -> None:
        assert detect_overlaps([]) == []

    def test_single_event_yields_no_overlap(self) -> None:
        assert detect_overlaps([_event(tid=1, enter=0, exit_=10)]) == []

    def test_disjoint_events_yield_no_overlap(self) -> None:
        events = [
            _event(tid=1, enter=0, exit_=10),
            _event(tid=2, enter=10, exit_=20),
            _event(tid=3, enter=25, exit_=40),
        ]
        assert detect_overlaps(events) == []

    def test_overlapping_pair_detected(self) -> None:
        a = _event(tid=1, enter=0, exit_=10, file="a.cbz")
        b = _event(tid=2, enter=5, exit_=15, file="b.cbz")
        overlaps = detect_overlaps([a, b])
        assert overlaps == [(a, b)]

    def test_contained_event_detected(self) -> None:
        # B fully inside A's window — classic missing-lock signature.
        a = _event(tid=1, enter=0, exit_=100)
        b = _event(tid=2, enter=20, exit_=30)
        overlaps = detect_overlaps([a, b])
        assert overlaps == [(a, b)]

    def test_multiple_overlaps_detected(self) -> None:
        a = _event(tid=1, enter=0, exit_=50)
        b = _event(tid=2, enter=10, exit_=60)
        c = _event(tid=3, enter=20, exit_=30)
        overlaps = detect_overlaps([a, b, c])
        # Every pair overlaps.
        assert (a, b) in overlaps
        assert (a, c) in overlaps
        assert (b, c) in overlaps
        assert len(overlaps) == 3

    def test_input_order_independence(self) -> None:
        # detect_overlaps sorts internally; reversed input → same result.
        a = _event(tid=1, enter=0, exit_=10)
        b = _event(tid=2, enter=5, exit_=15)
        assert detect_overlaps([b, a]) == detect_overlaps([a, b])

    def test_zero_width_event_at_boundary(self) -> None:
        # Event with enter == exit at the boundary of another event.
        # Boundary is non-overlap (exclusive on the right per
        # `enter_ns >= exit_ns`).
        a = _event(tid=1, enter=0, exit_=10)
        b = _event(tid=2, enter=10, exit_=10)
        assert detect_overlaps([a, b]) == []
