# 2026-05-16 — jobs-accuracy sweep v2 (in-process harness)

Re-runs the 2026-05-15 jobs-accuracy sweep with the refactored harness (commit
`5aa76ff`) — drives `cli.main()` in-process with a monkeypatched
`_accept_candidate` hook, so per-fixture decisions are captured directly rather
than parsed from log lines.

The v1 (subprocess + log-parser) was unreliable under -j 8 interleaving — caught
only 2 of 39 actual auto-writes. This v2 captures all decisions cleanly and
gives the first decisive empirical answer to "does parallelism change the
matcher's pick?".

## Run config

|             |                                                        |
| ----------- | ------------------------------------------------------ |
| Fixtures    | first 50 of `tests/calibration/fixtures-jobs.json`     |
| Source      | metron                                                 |
| Policy      | `normal --unattended --force-search`                   |
| Threshold   | `--confidence-threshold metron:0.50` (force decisions) |
| Cache       | wiped between each jobs value (cold)                   |
| jobs values | 1, 4, 8                                                |
| Harness     | `tests/stress/jobs_accuracy.py` (in-process)           |

Reproduce: `make stress-jobs-accuracy STRESS_LIMIT=50 STRESS_THRESHOLD=0.50`.

## Headline result

| Jobs | Wall (min) | Decided | Skipped | Same as jobs=1  | Identity changes |
| ---- | ---------- | ------- | ------- | --------------- | ---------------- |
| 1    | 22.4       | 39      | 11      | baseline        | —                |
| 4    | 19.7       | 36      | 14      | **47/50 (94%)** | **0**            |
| 8    | 19.0       | 27      | 23      | **38/50 (76%)** | **0**            |

## The reassuring finding: zero identity changes

**At any -j value, the matcher never picked a different candidate than it would
have at jobs=1.** Every change is "decided at jobs=1 → SKIPPED at jobs=N", never
"picked X → picked Y".

This is the most important user-facing result of the day: **parallelism doesn't
degrade tagging accuracy, only coverage.** Under -j N contention, some fixtures
lose candidate data and SKIP instead of auto-writing — but the auto-writes that
do happen are the same auto-writes a serial run would have produced. No false
positives, no wrong-volume picks under contention.

The 100-fixture stress and the (failed) cumulative-wait cap experiments
suggested the matcher might pick a _different_ answer under contention. That
fear is now empirically refuted on this fixture set: 0 identity changes across
100 (50 × 2) parallel runs vs the serial baseline.

## The cost: coverage drops with -j

- **jobs=4 loses 3/50 decisions (6%).** Acceptable for batch cron-style runs.
- **jobs=8 loses 12/50 decisions (24%).** Notable; nearly a quarter of fixtures
  fall off the auto-write band when running at -j 8.

Lost fixtures cluster on high-fan-out series — same pattern as
2026-05-15-stress-100's cascade:

| jobs=4 losses              | jobs=8 losses                           |
| -------------------------- | --------------------------------------- |
| Lois Lane (2019) #002      | Lois Lane (2019) #001                   |
| Lois Lane (2020) #005      | Lois Lane (2020) #005, #006, #010, #012 |
| Wonder Woman Historia #002 | Watchmen (1986) #003, #004              |
|                            | Watchmen (1987) #006, #007, ...         |
|                            | Batgirl Adventures #001                 |
|                            | (and 2 more)                            |

Each lost fixture: the series has many candidates in Metron (multi-volume,
reboots, related-title fan-out), contention causes some candidate-series's
issue-list calls to fail terminally, the matcher sees a partial candidate set,
the top candidate's score drops below the threshold, fixture SKIPs.

This validates the doc downgrade in commit `8ac616f` — **-j 4 is the right
ceiling for cold-cache runs**, -j 8 is faster (3 min less wall on this set) but
loses meaningful coverage.

## Wall time inverse-correlates with -j (unexpected)

| jobs=1 | 22.4 min | | jobs=4 | 19.7 min (-12%) | | jobs=8 | 19.0 min (-15%) |

Higher -j finished FASTER. Hypothesis: failed calls bail faster than successful
ones. At jobs=8, more fixtures fail (12 extra SKIPs vs jobs=1) and bail quickly,
freeing wall time. The 5.7-hour pathology from 2026-05-15-jobs-accuracy.md
didn't reproduce because the cap experiment touched retry.py and was reverted —
current retry.py is back to commit `5359cc4`'s 8-step schedule, which lets calls
patient-wait through long-tail contention. That patient- waiting is the saving
grace at the production normal-policy case; under `--threshold 0.50` it still
works, just with different trade-offs.

This contradicts the wall-time anxiety from the day before: under the production
retry behaviour (no cap), -j 8 isn't slow — it's just _less complete_. The
accuracy/coverage trade is real; the wall-time trade isn't.

## Recommendations (refined)

1. **Keep the `-j 4` doc as the cold-cache ceiling.** -j 8 loses coverage faster
   than it saves wall time.
2. **Don't try to fix the contention-coverage trade at the retry layer.** The
   cap experiment showed retry-level interventions break the productive
   patient-wait dynamics. Adaptive matcher- level throttling (drop
   max_series_per_search under detected contention) remains the right structural
   direction if anyone wants to push this further.
3. **The "wrong candidate under contention" fear is now refuted.** Future stress
   fixes can focus on coverage recovery without worrying that they're masking
   accuracy regressions.

## What this run doesn't measure

- **Absolute correctness.** Still no Metron-labeled fixture set. jobs=1 is used
  as the baseline, but jobs=1's picks aren't validated against ground truth. The
  "0 identity changes" finding is about CONSISTENCY across jobs, not RIGHTNESS
  of any pick.
- **Larger fixture counts.** 50 fixtures is enough to see the pattern; 200+
  would tighten the percentages. Diminishing returns vs the wall-time cost.
- **CV source.** Metron-only. CV's cap dynamics haven't shown contention
  problems in any production stress run.
