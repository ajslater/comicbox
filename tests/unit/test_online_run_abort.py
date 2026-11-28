"""An abort answered at one worker's prompt ends the lookups of its siblings."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from typing import TYPE_CHECKING

from comicbox.exceptions import OnlineLookupAbortedError
from comicbox.formats.base.online.series_cache import SeriesCache
from comicbox.formats.base.online.session_state import OnlineSessionState
from tests.unit.test_series_cache import (
    _build_cb,
    _CountingMetron,
    _make_candidate,
    _patch_source,
)

if TYPE_CHECKING:
    import pytest

    from comicbox.formats.base.online.profile import Candidate
    from comicbox.formats.base.online.selector import SelectorContext, SelectorResult

_WORKERS = 3


def test_abort_at_one_prompt_ends_the_sibling_lookups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Siblings in flight under -j N neither prompt nor search after an abort.

    Only the answering thread raised, so every worker waiting on the
    prompt lock showed its own prompt, and the series waiters woke to run
    their own cold search, after the user had said abort.
    """
    # Two close candidates of one volume: the matcher cannot choose, so it
    # prompts.
    close = _make_candidate(102, volume_id=42)
    close = replace(close, summary=replace(close.summary, year=2021))
    instances = _patch_source(monkeypatch, [_make_candidate(101, volume_id=42), close])
    monkeypatch.setattr(
        _CountingMetron, "enrich_prompt_candidates", tuple, raising=False
    )
    series_cache = SeriesCache()
    boxes = [_build_cb() for _ in range(_WORKERS)]
    state = OnlineSessionState.from_lookup(boxes[0]._config.online.lookup)
    selector_calls: list[int] = []
    lock = threading.Lock()

    def selector(
        _profile: object, _candidates: tuple[Candidate, ...], _ctx: SelectorContext
    ) -> SelectorResult:
        with lock:
            selector_calls.append(1)
            first = len(selector_calls) == 1
        if first:
            time.sleep(0.2)  # let the siblings queue behind the prompt
            return ("abort", None)
        return ("skip", None)

    outcomes: list[str] = []

    def work(box) -> None:
        box.set_series_cache(series_cache)
        box.set_online_session_state(state)
        box.set_online_selector(selector)
        try:
            box.run_online_lookup()
        except OnlineLookupAbortedError:
            outcome = "aborted"
        else:
            outcome = "finished"
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=work, args=(box,)) for box in boxes]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(selector_calls) == 1
    assert sum(source.search_calls for source in instances) == 1
    assert outcomes == ["aborted"] * _WORKERS
