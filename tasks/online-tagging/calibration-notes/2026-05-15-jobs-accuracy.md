# 2026-05-15 — jobs-accuracy sweep at -j 1, 4, 8

Measures how parallelism affects the matcher's per-fixture decisions
under cold cache and production policy. Closes the "Tagging-quality
measurement under -j 8 cold cache" item in TODO.md section 2 — but
the result reframes the question; see "Interpretation" below.

## Run config

| | |
| --- | --- |
| Fixtures | 50, from `tests/calibration/fixtures-jobs.json` (bootstrap'd from `~/Milliways/Comics/Test`) |
| Source | metron |
| Policy | `normal` (default; auto-write threshold 0.95) |
| Flags | `-n --online metron --unattended --force-search` |
| Cache | Metron sqlite cache wiped between each j value (cold) |
| jobs values | 1, 4, 8 |

`--force-search` is essential here — without it, fixtures with stored
Metron IDs take the refresh-by-id path and never invoke the matcher,
making -j irrelevant.

Reproduce: `make stress-jobs-accuracy STRESS_LIMIT=50`.

## Headline result

| Jobs | Wall (min) | Metron requests | Decided | Skipped | Same as jobs=1 |
| --- | --- | --- | --- | --- | --- |
| 1 | 20.5 | 393 | 0 | 50 | — |
| 4 | 22.1 | 390 | 0 | 50 | **50/50 (100%)** |
| 8 | 22.4 | 409 | 0 | 50 | **50/50 (100%)** |

**Zero differences across jobs values.** But not for the reason I
expected.

## Interpretation

Every single fixture in the 50-fixture sample landed in SKIP under
the production `normal` policy with `--unattended`. None reached the
0.95 auto-write threshold. This isn't a parallelism failure — it's
the matcher being correctly conservative.

The test as designed measures "does parallelism change which fixture
got which decision?" — but if every fixture gets the same decision
(SKIP) regardless, the test is technically passing trivially. The
deeper finding worth recording:

**Under production `normal` policy, parallelism is invisible.** The
0.95 auto-write floor is well above the noise that candidate-set
drops can introduce. Even when -j 8 contention causes some Metron
issue-list calls to fail terminally (the cascade from
2026-05-15-stress-100), and the matcher therefore sees a partial
candidate set, no candidate makes it across 0.95 anyway. The
production policy is naturally robust to the degradation pattern
the stress runs surfaced.

The interesting sub-result: **request counts and wall times track
closely across -j values**. 393 / 390 / 409 Metron requests at
j=1/4/8 (within ~5% of each other), wall times 20.5 / 22.1 / 22.4
min. The retry-budget bump from the same-day fix (5 → 8) means most
calls eventually succeed; contention adds modest wall-time overhead
(~9% at -j 8) but doesn't lose meaningful work.

## What this doesn't prove

The "no change under production policy" finding is fixture-set-
specific. With a different mix — fixtures that DO land in the
0.85-0.95 confidence band where contention could flip the auto-write
decision — there might be measurable differences. The bootstrap'd
set from `~/Milliways/Comics/Test` is mostly CV-only-labeled (CV
indie / older comics with weak Metron coverage), so most Metron
searches either find nothing or surface candidates the matcher
rejects on issue-number or year mismatch.

A stronger follow-up test would either:

1. **Lower the confidence threshold** (`--confidence-threshold 0.50`)
   to force decisions on every candidate. Tests "does -j change the
   matcher's top pick?" rather than "does -j change auto-write
   eligibility?". Re-uses this harness; another ~60-min sweep.

2. **Top-pick selector mode** (analogous to prompt_ux.py's recording
   selector but always picking index 0). Same measurement, in-
   process, also ~60 min wall.

3. **A Metron-rich fixture set.** Fixtures whose existing tags
   already carry Metron IDs would land in the auto-write band more
   often. The current set has 0 Metron-labeled fixtures because the
   library is CV-tagged. Would need a separate library walk.

I'd pick option 1 as the cheapest meaningful next test if the user
wants to push this further. The trivial-pass result is a real
finding — it justifies leaving -j 8 as the spec'd target without
narrowing the recommended default — but it's a weaker conclusion
than a richer comparison would yield.

## Harness notes

The harness lives at `tests/stress/jobs_accuracy.py`. It subprocess-
invokes `comicbox -n --online metron --unattended --force-search -j N
<files>` at each jobs value with cold cache between, parses
"auto-writing id=N" lines per fixture from the captured log, and
diffs each parallel outcome against jobs=1.

Run via `make stress-jobs-accuracy` (defaults: 50 fixtures at
jobs=1,4,8). Override via `STRESS_LIMIT`, `STRESS_JOBS_VALUES`, and
`STRESS_FIXTURES_JSON` env vars.

Unit tests at `tests/stress/test_jobs_accuracy.py` cover the parser
and the diff bucketing logic. 9 cases; pure functions, no live API.
