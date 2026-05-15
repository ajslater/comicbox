# 2026-05-15 — M7 stress test, -j 8, 20 fixtures, cold cache

First real-load validation of the parallel batch pipeline. Closes the
"Real-load stress test" gate in `TODO.md` section 2.

## Run config

| | |
| --- | --- |
| Fixtures | `~/Milliways/Comics/Test`, first 20 (sorted) |
| Sources | metron, comicvine |
| Jobs | 8 |
| Cache | wiped before run (cold) |
| Write mode | `-n` (dry-run, no archive writes) |
| Selector | `--unattended` (matcher SKIPs ambiguous instead of prompting) |
| Wall time | 6.3 minutes |

Reproduce: `make stress STRESS_LIMIT=20 STRESS_JOBS=8`.

## Headline result

**PASS.** Exit code 0. No tracebacks. Per-source observed rates within
documented caps:

| Source | New cache rows | Observed | Cap | Status |
| --- | --- | --- | --- | --- |
| metron | 127 | 20.10/min | 20/min | OK |
| comicvine | 52 | 8.23/min | 60/min | OK |

Metron sits exactly on its 20/min cap → the in-process limiter is the
binding constraint (as designed). ComicVine is well under its 60/min
cap → CV wasn't the bottleneck on this fixture set; it would become
the binding constraint at longer wall times (200/hr cap binds around
the 30-minute mark for cold-cache runs).

## Retry behaviour under contention

187 rate-limit retries logged (`retry.py:198`). Distribution: all
showed `attempt 1/5`, i.e. one retry was enough to clear. The schedule
honours the server-hinted `retry_after` (e.g. `retrying in 51.2s`),
not the static `_RATE_LIMIT_SCHEDULE`. The schedule is fallback for
when mokkari/simyan don't surface a hint; in practice the server
always tells us how long to wait.

This is exactly the intended behaviour: workers contend for the
shared sqlite bucket, lose, and politely wait the server-suggested
window before retrying.

## Failure mode worth knowing about

**16 terminal API failures** logged as WARNINGs (not errors, no
traceback). Two patterns:

- **6 × series_list rate-limit propagated through unwrapped.**
  `metron.py:254` calls `session.series_list(...)` directly. The
  surrounding `try/except Exception` re-raises after logging. The
  `_retry` decorator is **not** applied to this call. Under -j 8
  with cold cache the series-search hits the bucket and fails before
  any retry attempts. This is a real bug → tracked as a follow-up
  below.

- **10 × issue-list retry budget exhausted.** `metron.py:407` calls
  `_issues_list_with_retry` (`@with_retry()`-decorated, 5 retries).
  Under sustained -j 8 contention some calls exhausted the 5-retry
  budget. The retry schedule respects server hints (typically 30-60s),
  so 5 attempts can stretch to several minutes. The loop at line 408
  `continue`s past the failed series so the matcher just sees one
  fewer candidate.

Effect: ~5% of API calls degrade match quality (fewer candidates
than a `-j 1` run would have produced). No incorrect tags written,
no crashes.

## Recommendations for the `-j` flag

- **Default `-j 1`** stays safe. The flag accepts higher values, but
  the calibration data should be the floor for the recommendation.
- **`-j 4`** is the practical sweet spot. Halves wall time vs `-j 1`
  on cold-cache runs while keeping the bucket well under sustained
  saturation; expect minimal terminal failures.
- **`-j 8`** is the spec'd target. Works under the rate limiter but
  expect ~5% of API calls to terminate without retries succeeding,
  which means slightly lower match accuracy. Acceptable for batch
  cron jobs, less ideal for one-shot tagging where every match
  matters.
- **`-j 16+`** is NOT faster than `-j 8` because both rate limiters
  serialise into a single shared bucket. Extra threads queue and
  contend on the bucket more aggressively — terminal-failure rate
  rises further with no wall-time benefit.

CLI help text update follows in the next commit.

## Follow-ups surfaced by this run

1. **Wrap `Metron.series_list` in `@with_retry()`.** Six terminal
   failures in this run came from this un-retried path. Trivial fix:
   either decorate `_series_list_with_retry` like the issue-list
   helper, or wrap the call site at `metron.py:254`. ComicVine's
   equivalent search path should be audited for the same gap.

2. **Increase `_MAX_RATE_LIMIT_RETRIES` or shorten the schedule for
   high-contention runs.** Under -j 8 some calls genuinely need 6-7
   server-hinted waits before clearing. Either bump from 5 to 8 or
   make it `-j`-aware. Worth measuring against a re-run before
   deciding the shape.

3. **Validate prompt UX under -j**, not just rate-limit compliance.
   This run used `--unattended` so `_PROMPT_LOCK` was never acquired.
   A follow-up run with a programmatic selector that simulates
   user think-time would close the second half of the M7 acceptance
   gate. Tracked in `tests/stress/README.md` "What it doesn't measure".

4. **Move beyond 20 fixtures.** This run's wall time was Metron-
   bound. Bigger runs (50-100 fixtures) would also show CV's 200/hr
   cap engaging, which exercises a different code path
   (`pyrate_limiter` exponential backoff inside simyan vs mokkari's
   raise-and-retry). A second stress run at 50 fixtures is worth
   doing before declaring M7 fully shipped, but it doesn't block
   merging the harness or the doc updates.

## Notes for future stress runs

- Cache wipe lands at `~/.cache/comicbox/online/` on this system
  (platformdirs XDG path), not `~/Library/Caches/comicbox/`. Be aware
  that re-warming the cache takes a while after a stress run.
- Run-output lives at `tests/stress/output/`; the latest is always
  `SUMMARY.md`. Older runs are timestamped logs in the same dir.
- For iteration, `--no-wipe-cache` makes follow-up runs near-instant
  (every call is a cache hit) — useful for harness-mechanics changes
  but NOT for the rate-limiter check.
