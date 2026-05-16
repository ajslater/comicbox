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

## Follow-up run: threshold=0.50 sweep (CRITICAL wall-time finding)

Re-ran with `--threshold 0.50` per option 1 above. Same 50 fixtures,
same cold-cache + Metron-only + force-search.

**The wall-time result is the headline:**

| Jobs | Wall (min) | Metron requests | Rate-limit retries |
| --- | --- | --- | --- |
| 1 | 22.4 | 432 | 351 |
| 4 | 24.1 | 428 | 938 |
| 8 | **342.2** | 453 | **1238** |

**Jobs=8 took 5.7 hours — 15x longer than jobs=1.** Request counts
barely budged (453 vs 432, +5%); the time went into rate-limit
*waits*. Retry-attempt distribution at jobs=8 (out of 8 max):

| Attempt | Count |
| --- | --- |
| 1/8 | 398 |
| 2/8 | 257 |
| 3/8 | 180 |
| 4/8 | 137 |
| 5/8 | 98 |
| 6/8 | 72 |
| 7/8 | 54 |
| 8/8 | 42 |

42 calls reached the final retry (attempt 8/8) — those waited the
full schedule (30+60+120+300+600+600+600+600 = ~50 min worst case
with server-hinted overrides applying), all in series across the 8
contending workers.

**Root cause: the retry-budget bump from 5 → 8 (the same-day fix
in commit `5359cc4`) trades wall time for cascade-WARNING
reduction. At -j 8 cold-cache with the matcher fully invested
(threshold=0.50 makes more fixtures progress past the early-skip
gate), more calls patient-wait their way through the longer
schedule instead of failing fast.** The 100-fixture stress run
that validated the fix (`2026-05-15-stress-100-verify.md`) didn't
expose this because under production `--policy normal` most
fixtures SKIP before exercising the slow retry path.

### What changed in user-visible behaviour

This finding contradicts the `-j` doc text we shipped in commit
`111a75a` ("8 with caveat — trade match quality for wall time").
The actual trade-off at jobs=8 under high contention is much worse
than that: wall time can be **15x** slower, not "slightly".

### Recommendations

1. **Tighten the `-j` doc.** Recommend `-j 4` as the actual safe
   ceiling for cold-cache runs, not just the sweet spot. Mark `-j 8`
   as "experimental — wall time can balloon under cold-cache
   contention with `--force-search`".
2. **Bound the retry-cumulative wait.** Add a per-call max wait
   (e.g. 5 min total). Once a call's accumulated retry waits exceed
   that, give up — the wall-time cost of patient-waiting isn't
   worth the partial-candidate-recovery gain.
3. **Or revert the budget bump under -j > 4.** Make
   `_MAX_RATE_LIMIT_RETRIES` jobs-aware: 8 at jobs=1, dropping to 5
   at jobs >= 4. The schedule that was fine at jobs=1 becomes
   pathological under parallelism.

(2) is probably the right structural fix. (3) is more conservative.

### Accuracy result is suspect

The harness reported 49/50 same outcome at jobs=8 with 1 identity
change (Captain Science 53445 → 4749). But the log parser broke
down under -j 8 interleaving: under heavy parallelism, comicbox's
rich-styled fixture banners get word-wrapped AND shuffled by 8
concurrent workers, so the path-substring tracking heuristic in
`parse_chosen_ids` fails. **The harness caught only 2 of 39 actual
auto-writes; the 1 changed-identity result is from an unknown
sample size, not 50.**

To get a clean accuracy measurement under -j 8, the harness needs
either an in-process driver with monkeypatched recording (like
prompt_ux.py) or a more robust parser keyed on a more
identification-friendly log anchor than path substrings. Tracked
as a separate follow-up.

The wall-time finding above is rock-solid (timing data is captured
externally; not affected by parser bugs).

## Failed fix attempt 2026-05-16: cumulative-wait cap

Tried capping retry cumulative wait at 300s per call as a backstop
against the 5.7-hour pathology. **It made things worse for the
production stress workload.** Two iterations, both reverted:

### Attempt A: cap on every wait

Logic: `if cumulative_wait + delay > 300: bail`.

Broke the pre-existing 1-day-clamp test
(`test_with_retry_clamps_excessive_retry_after` expected a 3600s
wait to be honored). Test was correct under the old semantic; the
cap was too aggressive.

### Attempt B: cap exempts first wait

Logic: `if cumulative_wait > 0 and cumulative_wait + delay > 300: bail`.

Preserved the 1-day-clamp test, but **mokkari hands out 3600s
retry_after hints under -j 8 heavy contention** (server's view of
backlogged bucket). The first-wait exemption let those through →
wall ballooned to 6.8 hours in a 100-fixture re-verify.

### Attempt C: hard cap including first wait

Logic: `if cumulative_wait + delay > 300: bail` (reverting Attempt B).

20-fixture smoke passed (6.2 min wall, similar to baseline). But
100-fixture verify regressed: **49 min (pre-cap) → 231 min (4.7x
slower)**, WARNINGs 161 → 864. Root cause: under heavy contention
with short server hints (typically 30-60s in this workload), the
cap interrupts the productive patient-waiting that lets the
rate-limit bucket clear. Each cap-bail spawns a fresh retry cycle
on the next series — failure cycling cascades through the matcher's
candidate set.

The pre-cap behaviour (wait through the long-tail of the schedule)
was actually adaptive: it gave the bucket time to refill. The cap
breaks this.

### Decision: revert, accept the pathology

Reverted retry.py and tests. The 5.7-hour pathological case under
`--confidence-threshold 0.50 --force-search -j 8 cold cache` stays
as a known limitation. It only manifests under a specific
power-user workload that production users won't hit. The doc
downgrade in commit `8ac616f` (recommending `-j 4` ceiling for
cold-cache runs) is the right user-facing response.

### Notes for any future fix

If someone tries this again:

- Don't cap based on cumulative wait alone — the production
  workload benefits from patient-waiting.
- Don't cap based on single-wait length — short hints under
  contention are normal and productive.
- The pathology is specifically: *many calls, each with short
  hints, all bailing early creates re-issuance cycles*. The fix
  needs to recognise the cycle, not the wait.
- A more promising direction: when a worker's call fails terminally,
  briefly back off the WHOLE WORKER for a few seconds before
  starting the next series. Reduces re-issuance pressure. But
  that's a structural change to the matcher loop, not retry.py.
- Or: the real fix is to back off the matcher's fan-out under
  detected contention (drop max_series_per_search from 20 to 5
  when WARNINGs accumulate). Adaptive throttling at the matcher
  level, not the retry level.

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
