# 2026-05-15 — 100-fixture stress re-run after retry-audit fixes

Verifies the three bug fixes from the same-day audit pass collapsed the WARNING
cascade observed in [`2026-05-15-stress-100.md`](2026-05-15-stress-100.md).

## Run config

Identical to the baseline run, with the three fixes landed:

- `Metron._series_list_with_retry` wraps `session.series_list`
- `ComicVine._volume_search_with_retry` wraps `session.search(VOLUME, ...)`
- `ComicVine._get_volume_with_retry` wraps the supplementary publisher-lookup
  call (which the outer `try/except` had been swallowing before retries could
  fire)
- `_MAX_RATE_LIMIT_RETRIES` bumped 5 → 8 (`_RATE_LIMIT_SCHEDULE` extended with
  three 600s plateau entries)

## Comparison

| Metric                                 | Pre-fix   | Post-fix     | Delta                                               |
| -------------------------------------- | --------- | ------------ | --------------------------------------------------- |
| Wall time                              | 59.3 min  | **49.3 min** | -17%                                                |
| Exit code                              | 0         | 0            | clean                                               |
| Tracebacks                             | 0         | 0            | clean                                               |
| Metron requests                        | 995       | 895          | -10%                                                |
| Metron observed rate                   | 16.79/min | 18.15/min    | +8% (closer to 20/min cap — less wasted contention) |
| CV requests                            | 128       | 128          | unchanged                                           |
| Rate-limit retries                     | 4582      | 3861         | -16%                                                |
| **Series-search WARNINGs**             | **86**    | **3**        | **-96%**                                            |
| **Issue-list WARNINGs**                | **465**   | **158**      | **-66%**                                            |
| Total filtered WARNINGs                | 551       | 161          | -71%                                                |
| Distinct series w/ issue-list failures | 32        | 29           | -9%                                                 |

## Interpretation

The `series_list` retry wrap effectively eliminates that gap (86 → 3 residual).
The remaining 3 are cases where even 8 retries weren't enough — rare and
acceptable.

The retry-budget bump (5 → 8) cut the issue-list cascade by two-thirds. What
remains is mostly the **inherent high-fan-out problem**: Conan- titled fixtures
still fan out to 20+ candidate series in Metron, and under -j 8 contention some
of those candidates still exhaust the new 8-retry budget. Bumping further would
help less (diminishing returns: each additional retry adds another 10-minute
wait worst-case).

Wall time dropping 17% even though Metron's bucket is still binding is the most
user-visible win: fewer dropped candidates means the matcher progresses faster
on more fixtures.

## What's left for the cascade

To eliminate the residual 158 issue-list WARNINGs we'd need to attack the
fan-out itself, not the retry budget:

1. **Cap per-fixture fan-out more aggressively** — e.g., for series names with >
   N candidates, sample down to N. Affects accuracy if the right answer is in
   the long tail.
2. **`-j`-aware retry budget** — more workers → more attempts. Add `jobs`
   plumbing to `with_retry()`. Mechanical but spreads concern.
3. **Recommend `-j 4` as the practical default** in CLI docs (already done; this
   just reinforces it).

None of these is blocking — the system handles the cascade gracefully
(warnings + partial candidates, no crashes, no wrong writes).

## Quality measurement remains the right next thing

This run measures _load behaviour_; it doesn't measure _tagging accuracy_ under
-j 8 vs -j 1. With 29 series still suffering partial candidate-set drops at -j
8, some fixtures probably get the wrong match or get skipped where -j 1 would
have succeeded. That's the remaining open question — see TODO.md section 2
"Tagging-quality measurement under -j 8 cold cache".
