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

## Per-comic cost

| Path                                  | Calls   | Which                                                          |
| ------------------------------------- | ------- | -------------------------------------------------------------- |
| Cold, series unresolved               | 2       | `issues_list` (search) + `issue(id)`                           |
| Cold, search misses at the exact year | up to 8 | 3 year attempts x 2 volume cycles, + `issue(id)` on a late hit |
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

Two things in the plan are still open and deliberately unimplemented:

1. **Dropping `series_volume` from queries** (§B2). The plan's premise — "the
   matcher already scores year distance", implying volume is recoverable at
   scoring time — does not hold. `CandidateSummary` has no volume field at all,
   and `_contributing_signals` (`matcher.py:163-192`) scores series, issue,
   year, publisher and pages, where `year` is the ISSUE cover year, not the
   series start year. Dropping the filter would widen results to sibling reboot
   volumes with nothing to separate them, and `_candidate_sort_key` breaks the
   resulting tie on the LOWEST `volume_id` — the oldest series record, which is
   the wrong answer for a modern reboot.

    Making it safe needs a volume signal in the matcher first (`BasicSeries`
    carries `volume` and `year_began`, so the data is already on the wire), and
    that needs its own calibration run.

2. **Shortening the year cascade** (§B2). Replacing the Y-1/Y+1 pair with one
   year-less `series_name + number` call would cut a missing search from 3 calls
   to 2 and strictly widen recall, but it also admits candidates many years off,
   discriminated only by `W_YEAR` (0.10). Whether that flips matches is exactly
   the parity question the fixture set answers.

Both need `make calibrate` against live Metron with
`tests/calibration/fixtures.json`, comparing `top_issue_id` before and after.
There is no offline cassette harness — `tests/calibration/ README.md` and
`tests/stress/README.md` both require real credentials — so this could not be
answered from the repository alone. The DB-load half of the question is Brian's
to answer either way.
