# Metron batch cost after rate-gating and series prefetch

Date: 2026-09-16. Code: the PR A/B/C work for
[#207](https://github.com/ajslater/comicbox/issues/207). Backs
`METRON_REQUESTS_PER_WARM_COMIC` and `metron_requests_for_batch` in
`comicbox/online_estimate.py`.

## What the numbers are

**Derived from the call graph, not measured against live Metron.** Every figure
below is a count of the `session.*` calls the code makes on a given path,
verified by the unit tests named against each row. They are exact for a cold
response cache and an upper bound for a warm one, which is the same basis
`api_call_counts` has always reported on.

The live-API measurement the plan asked for (§B2: "measure on the Metron fixture
set: calls per miss, pages, parity on `top_issue_id`") has NOT been run — see
"Not measured" below.

**Updated 2026-09-17**: the miss path in the table below is no longer the
six-call cascade. `cover_date_range_after` / `_before` (Metron server #628)
collapsed it to a single wide fallback; see "Not measured" for what that leaves
open.

## Per-comic cost

| Path                                  | Calls   | Which                                                          |
| ------------------------------------- | ------- | -------------------------------------------------------------- |
| Cold, series unresolved               | 2       | `issues_list` (search) + `issue(id)`                           |
| Cold, search misses at the exact year | up to 3 | exact call + one wide `cover_date_range` fallback, + `issue(id)` |
| Warm, series resolved                 | 2       | `issues_list(series_id, number)` + `issue(id)`                 |
| Warm, series prefetched               | 1       | `issue(id)` only; the list came from memory                    |

`issue(id)` is the floor. `BaseIssue` from a list carries no credits and no
characters, so a match always costs one detail fetch. Removing it needs
something from Metron's side — a richer list serializer, or a `?fields=`
projection. That is the ask in the reply draft.

## Batch cost

For `n` comics spanning `s` series, all in one run:

```
requests = s * 2 + (n - s) * 1          # without prefetch, warm path only
requests = s * (2 + 1 + pages) + (n - s) * 1   # with prefetch
```

`metron_requests_for_batch` models the first form: the prefetch's extra
`1 + pages` per series is what buys the `(n - s)` term its lower constant, and
the source only takes that trade when `1 + pages < cluster_size`
(`MetronOnlineSource.prefetch_volume`), so the prefetched form is never worse
than the modelled one.

Worked example, the plan's 100-issue single-series batch at `-j 20`:

|                                                | issues_list | series | issue | total          |
| ---------------------------------------------- | ----------- | ------ | ----- | -------------- |
| Before (cold cache, all 20 workers start cold) | 100-200     | -      | 100   | 200-300 + 429s |
| Single-flight only (B1)                        | 100         | -      | 100   | 200            |
| With prefetch (C1)                             | 1           | 1      | 100   | 102            |

The "before" range is the one that also generated 429s, and on Metron every one
of those debits the daily quota exactly like a success.

## Pacing

`source_rate_per_minute("metron")` now prefers the burst limit the gate read off
`X-RateLimit-Burst-Limit`, falling back to `METRON_DEFAULT_PER_MINUTE` before
anything has talked to Metron. The constant is a documented default, not a fact
about a given user: donor tiers move the sustained window, and a self-hosted
instance may not throttle at all.

## Not measured

### Resolved by the wide fallback (2026-09-17)

Both of the items this note left open were about widening the query without
losing the precedence the cascade's call ORDER encoded. `cover_date_range_*`
answers both at once, without the matcher change either of them needed:

1. **Dropping `series_volume` from queries** (§B2). The objection stands — the
   matcher has no volume signal, `_contributing_signals` scores the ISSUE cover
   year rather than the series start year, and `_candidate_sort_key` breaks the
   resulting tie on the LOWEST `volume_id`, which is the wrong answer for a
   modern reboot. So the filter is not simply dropped: the fallback drops it on
   the wire and `_select_precedence_tier` reapplies it client-side, over rows
   that one call already returned. `CandidateSummary` grew the `volume` field
   that tiering needs, fed from `BasicSeries.volume`.

2. **Shortening the year cascade** (§B2). Not a year-less call, which is what
   admitted candidates many years off. A bounded Y-1..Y+1 cover-date range asks
   for exactly the three years the cascade asked for, in one request, and a
   local guard drops anything outside it in case the server ignores the filter.

Net: a miss costs 2 `issues_list` calls instead of 6, and for every profile
with an issue number the candidate set is the one the cascade produced.

### Still open

The **live parity run** (§B2's "parity on `top_issue_id`"). It is confirmation,
not a gate — the tiering is asserted against a mixed-volume, mixed-year fake in
`tests/unit/test_metron_source.py` — but it is the only thing that can show the
range filter behaving as documented against the real server:

```sh
uv run python -m tests.calibration.run \
  --fixtures tests/calibration/fixtures-bigmedia.json --sources metron
```

Run it before and after, on the 47 Metron-labelled fixtures, and compare
`top_issue_id` and the per-fixture `issues_list` count from `api_call_counts`
(cache-independent). It needs `/Volumes/Media` mounted and real credentials;
`make calibrate` takes no arguments and defaults to `fixtures.json`, so invoke
the module directly. The harness never reads `outcome_stats`, so for HTTP-level
page counts either read the end-of-run `outcome_stats` `issue_list` total per
pass with the mokkari cache wiped for both passes, or capture
`outcome_stats.api_snapshot()` deltas per fixture in `_score_one`. The DB-load
half of the question is Brian's to answer either way.
