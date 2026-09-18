# Metron miss-cascade parity run

Date: 2026-09-17. The live before/after the miss-cascade collapse asked for —
W1.8 of `tasks/metron-followups-plan.md`, and the last open half of B2 in
`tasks/metron-rate-limit-plan.md`.

- **before**: `53a17f5` — #212 merged, #213 not. The six-call cascade.
- **after**: `3e69fff` — #213 merged. One exact call plus one wide
  `cover_date_range` fallback.

## Method

46 fixtures: the Metron-labelled subset of
`tests/calibration/fixtures-bigmedia.json` (47 labelled, minus
`The Department of Truth (2020) #001`, whose file is no longer on
`/Volumes/Media`). Copied to a scratch fixtures file so the existing
`fixtures-bigmedia.outcomes.json` was not clobbered.

Both passes ran cold and independently: `COMICBOX_ONLINE__CACHE__MODE=refresh`
with a per-pass `COMICBOX_ONLINE__CACHE__DIR`, so neither replayed the other's
responses and neither touched the real cache. The harness calls `search()` and
`rank()` only, so every fixture is a cold search with no `issue(id)` detail
fetch.

Two numbers per pass, because they answer different questions:

- `api_call_counts` from the outcomes JSON — comicbox's wrapper-level count,
  cache-independent, one per `issues_list` regardless of pages.
- `outcome_stats.api_snapshot()` — real HTTP sends. The harness never reads
  `outcome_stats` (only the CLI `Runner` prints it), so a small wrapper ran
  `run.main()` and dumped the snapshot afterwards.

## Parity: exact

|                      | before | after |
| -------------------- | ------ | ----- |
| correct              | 36     | 36    |
| wrong                | 0      | 0     |
| no candidates        | 10     | 10    |
| accuracy on labelled | 100%   | 100%  |

`top_issue_id` is **identical on all 46 fixtures**. So is `n_candidates`. No
fixture changed outcome in either direction.

## Cost

|                               | before | after |
| ----------------------------- | ------ | ----- |
| `issues_list` calls (wrapper) | 66     | 56    |
| real HTTP sends               | 66     | 56    |
| a search that hits on call 1  | 1      | 1     |
| a search that misses          | 3      | 2     |

Wrapper count equals HTTP sends in both passes, so nothing paginated: the
`number` filter keeps a result inside one 100-row page, as the cost model
assumed.

### The six-call path was never exercised

Ten fixtures missed on call 1. All ten had a cover year and **no** parsed
volume, so the old code ran the year cycle alone (Y, Y−1, Y+1) and never reached
the drop-volume cycle — `retrying without the volume filter` appears zero times
in the before log, against twenty `retrying with cover_year` lines.

So this set measures **3 → 2**. The headline 6 → 2 remains the worst case and is
still only derived: it needs a missing search on a comic whose filename carries
`Vol. N`. Worth adding one to the fixture set.

### Recall is unchanged, not improved

All ten misses stayed misses. The wide fallback found nothing the cascade did
not; it just spent less failing to. This fixture set contains no cover-date
drift case, which is the situation the fallback exists for, so it bounds the
regression risk without demonstrating the upside.

## `cover_date_range_*` is live on metron.cloud

Proven directly rather than inferred. It had to be: all ten fallbacks returned
zero rows, so the `_drop_out_of_range` guard never had a row to judge, and its
silence was equally consistent with the filter being ignored.

```
issues_list({series_name: "Wolverine", number: "1"})
  → 132 rows, cover years 1982 … 2027

  + cover_date_range_after=2002-01-01
  + cover_date_range_before=2004-12-31
  → 5 rows, cover years {2002, 2003}
```

A strict in-window subset, so Metron server #628 is deployed. Consistent with
`metron:cover-date-range-ignored` never firing during the after pass.

It also shows what the bound is worth: an unbounded `series_name + number`
fallback on a long-running title hands the matcher 132 rows spanning 45 years.
That is the variant the plan rejected, and this is the shape of what it would
have cost.

## Incidental: the burst limit really does float

Both passes had Metron report `X-RateLimit-Burst-Limit: 60`, not the
documented 20. The gate adopted it, paced 21.6s (before) and 45.6s (after), and
earned **zero** rejections. That is the W3 wording change confirmed against
production rather than taken from bpepple's word: the constant is a
pre-first-response pace, not a floor.

Also across 122 sends: zero responses without rate-limit headers and zero
connection failures — so the W2 counters read clean on a healthy run, which is
the baseline they need for an unhealthy one to mean anything.

Daily quota: 5,000 → 4,934 (before), 4,934 → 4,878 (after).

## Reproduce

```sh
FIXTURES=tests/calibration/fixtures-bigmedia.json
COMICBOX_ONLINE__CACHE__MODE=refresh \
COMICBOX_ONLINE__CACHE__DIR=/tmp/parity-cache \
  uv run python -m tests.calibration.run --fixtures "$FIXTURES" --sources metron
```

Filter the fixtures to the Metron-labelled rows first, or the 200 unlabelled
ones cost a search each. Note that `make calibrate` takes no arguments and
defaults to `fixtures.json`, so invoke the module directly. Reading the comic
files needs whatever is running this to hold macOS network-volume permission for
`/Volumes/Media`; without it every fixture errors as `PermissionError` before
any API call.
