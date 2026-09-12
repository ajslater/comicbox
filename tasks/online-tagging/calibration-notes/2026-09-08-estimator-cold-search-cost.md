# 2026-09-08 — per-comic cold-search cost for the run estimator

Where `comicbox/online_estimate.py`'s Comic Vine numbers come from. No API calls
were made for this note: it re-reads the 2026-05-17 bigmedia outcomes still on
disk (`tests/calibration/fixtures-bigmedia.outcomes.json`, gitignored and
per-developer, so the aggregates are recorded here instead of cited by path).

## What the estimator got wrong

`requests_per_comic()` keyed Comic Vine's cost off `MatchMode` alone, with a
table of `{eager 2, auto 3, careful 5}` whose provenance no comment records.
Match mode never reaches the search path: it branches only in `matcher.py`,
deciding how a verdict is applied. The axis that does move Comic Vine's request
count is `Effort`, which since 5.0 bounds the per-candidate fan-out
(`series_filter.max_calls_for`) and, at `thorough`, turns the bound off. So the
shipped estimate described neither a default run nor a thorough one. Codex,
which shows the projection before a scan and mirrors it in a live countdown,
reported the numbers reading high by default and low under `thorough`.

## The measurement

494 outcome records, 247 of them Comic Vine, one per fixture, each carrying the
per-endpoint `api_call_counts` delta the harness snapshots around a search. The
run predates the name pre-filter (`series_filter.py`, `39dd54c`) and the bounded
fan-out (`98a548e`, PR #191), so it measures an unfiltered, unbounded search:
the `thorough` shape.

| Endpoint         | Pool    | Mean | Median | p90 | Max | Present in |
| ---------------- | ------- | ---- | ------ | --- | --- | ---------- |
| `search_volumes` | search  | 1.00 | 1      | 1   | 1   | 247/247    |
| `filter_volumes` | volumes | 1.00 | 1      | 1   | 1   | 247/247    |
| `list_issues`    | issues  | 3.48 | 2      | 7   | 16  | 246/247    |

Totals per fixture: mean 5.47, median 4, p90 9, max 18.

The harness stops at the search, so the two accept-time calls (`get_issue` +
`get_volume`, `online_source.get()`) are not in the table. They are one request
each and land in their own pools.

## What the constants say

Discovery is a flat 2 (`search_volumes`, plus the year-narrowed `list_volumes`
when the comic names a year — the fixtures all did). The accept fetch is a
flat 2. Only the issue-list fan-out varies, and it is also the only part that
stacks in one pool, so it sets both the bulk of the cost and the pace.

Scaling the measured 3.48 by the call reductions `series_filter`'s threshold
comments record for each effort:

| Effort   | Filter effect        | Scaled | Constant |
| -------- | -------------------- | ------ | -------- |
| minimal  | -60.5% (0.7 cutoff)  | 1.37   | 1        |
| balanced | -18% (0.4 cutoff)    | 2.85   | 3        |
| thorough | none (0.0, measured) | 3.48   | 4        |

`thorough` rounds up rather than to the nearest integer: rounding to 3 would tie
it with `balanced` and reproduce the "thorough reads low" complaint the change
exists to fix. Its true tail is much longer than 4 — the p90 is 7 and the max
16, and with the fan-out unbounded the ceiling is the discovery cap of 20
volumes times a year-window retry each. The estimate is a projection an operator
reads before a run, not a worst case.

Per comic that gives `2 + n + 2` requests and `60 * n / 3` seconds (Comic Vine's
200/hour pool cap spread over the minute):

| Effort   | Requests | Seconds |
| -------- | -------- | ------- |
| minimal  | 5        | 20      |
| balanced | 7        | 60      |
| thorough | 8        | 80      |

The default projection therefore rises from 20 s to 60 s per comic.

## Two known under-counts, one now closed

- **simyan pagination — CLOSED by simyan 4.1.0 (2026-09-11).**
  `Comicvine._offset` used to loop until it got an empty page, so every fan-out
  `list_issues` spent two of the 200/hour `issues` budget rather than one, and
  the constants above were a floor for wall clock. 4.1.0 stops on a short page
  (Simyan#309 / PR #310, the fix this project filed), verified by fake-transport
  probe at 1 request per call. **The constants above needed no change**: they
  count comicbox-level `api_call_counts` calls, so they always described logical
  calls, and one logical call is now one request. The 2026-09-08 decision not to
  double them is what makes this a no-op rather than a second correction.
- **Metron.** `_record_api_call` counts one call where mokkari may follow `next`
  pages inside it. The production filters keep results under a page, so the flat
  2 holds in practice.

## What a calibration run should settle

- The post-#191 fan-out at each effort, measured rather than scaled. The -18%
  and -60.5% figures come from the Phase B experiment whose raw data is not in
  the tree; this note scales them rather than re-deriving them.
- Whether `balanced` at 3 is right once the series-batch path is included. A
  library run pays a full search once per series and about one issue-list call
  per issue after that, so the per-comic average across a real batch is well
  under the cold-search number this estimate uses.
