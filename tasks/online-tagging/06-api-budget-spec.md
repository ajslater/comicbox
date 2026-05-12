# Phase 6 — API Budget Spec

How comicbox decides how stingy to be with online API calls per comic.
Orthogonal to (and composes with) the Match Resolution Policy in
[04-match-resolution-spec.md](04-match-resolution-spec.md).

## Problem

Today's online lookup runs a fixed algorithm regardless of batch size: for each
comic, do one volume/series search then up to `_MAX_*_PER_SEARCH = 20`
per-volume issue lookups. Worst case is ~21 calls per comic per source. Plus
optional `get_issue` and cover-image downloads after a match is accepted.

ComicVine's hard cap is **200 requests/hour**. At 21 calls/comic worst case,
that's **~9 comics/hour cold-cache** — a multi-day overnight for a 343-comic
library. After the start-year filter, average drops to ~10/comic, which lifts
the rate to ~20 comics/hour. Still painful. The user has no in-tool dial to
trade accuracy for throughput.

Metron's 1,200/hr + 5,000/day caps are 6× more forgiving than CV in the per-hour
direction, but the daily cap pinches just as hard at the upper end: a
500,000-comic library under `balanced` blows through Metron's daily budget in 30
minutes and then waits a day before resuming, for **~100 days of total wall
time**. CV at the same library size: years. Both sources need this lever at
sufficient scale; the boundaries are different but the shape is the same.

The Match Resolution Policy (`strict`/`normal`/`eager`/`always-prompt`) controls
how _the matcher's verdict gets applied_ — but it has zero effect on how many
API calls were spent producing the candidate set in the first place. That's the
gap this spec fills.

## Two orthogonal dials

This was the design correction that prompted this spec. Conflating
unattended-vs-attended with fast-vs-exhaustive was wrong — they're independent
axes with four legitimate quadrants:

|                | **Attended (prompts allowed)**                                                                                               | **Unattended (`--unattended`)**                                                                                                                    |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Exhaustive** | Tagging a single comic interactively; user accepts prompts; wants the most accurate result available regardless of API cost. | Overnight cron on a small library where accuracy matters more than wall time. User wants 200 high-confidence tags, not 2000 "probably right" ones. |
| **Fast**       | Power user crunching a few hundred comics interactively, will prompt for ambiguity but wants throughput; OK losing a few.    | The headline use case: thousands of comics, unattended job, willing to skip ambiguous cases to stay under the hourly cap.                          |

Picking `unattended` as a proxy for `fast` (or vice versa) breaks the
"unattended + exhaustive" and "attended + fast" cells. They're real cases.

## Settings model

One new global + per-source setting:

```python
class APIBudget(StrEnum):
    EXHAUSTIVE = "exhaustive"   # Spend API budget freely; max accuracy.
    BALANCED = "balanced"   # Today's behavior; the default.
    FAST     = "fast"       # Aggressive pre-filtering; trade accuracy for throughput.

class OnlineSettings:
    api_budget: APIBudget = APIBudget.BALANCED
    api_budget_per_source: dict[str, APIBudget] = field(default_factory=dict)
    # ... existing settings unchanged
```

Per-source override matters because **Metron's 20/min × 60 min = 1,200/hr is 6×
more forgiving than CV's 200/hr**. The same library run might rationally want
`fast` for CV and `exhaustive` for Metron.

CLI surface mirrors the existing `--policy` / `--policy-per-source` patterns:

```sh
comicbox --online --api-budget fast *.cbz
comicbox --online --api-budget-per-source comicvine:fast,metron:exhaustive *.cbz
```

Composes with `--unattended`. The two flags address different concerns:

```sh
# Single comic, careful work, no human present (overnight script).
comicbox --online --unattended --api-budget exhaustive rare.cbz

# Big batch, human at keyboard, OK to skip prompts when score is borderline.
comicbox --online --api-budget fast Library/**/*.cbz
```

## What each budget controls

The levers grouped by what they touch:

### Search breadth (pre-call)

| Lever                             | exhaustive | balanced                               | fast                      |
| --------------------------------- | ---------- | -------------------------------------- | ------------------------- |
| `_MAX_VOLUMES_PER_SEARCH` (CV)    | 20         | 20                                     | 5                         |
| `_MAX_SERIES_PER_SEARCH` (Metron) | 20         | 20                                     | 5                         |
| **Series-name pre-filter**        | off        | conservative (filter < 0.4 similarity) | aggressive (filter < 0.7) |
| Year-fallback retry on empty      | yes        | yes                                    | no                        |

The series-name pre-filter is the highest-leverage piece. Currently every volume
the volume-search returns gets a `list_issues` call, even if the volume's name
barely resembles `profile.series`. CV's full-text search will return "Lois Lane:
A Celebration" and "Lois Lane and Friends" alongside "Lois Lane" — we waste a
call per non-matching volume. Filtering at search time using `rapidfuzz` against
`profile.series` drops the obvious garbage before we issue the call.

### Match resolution interaction

| Lever                            | exhaustive | balanced | fast                                      |
| -------------------------------- | ---------- | -------- | ----------------------------------------- |
| `confidence_threshold` default   | 0.95       | 0.95     | 0.97                                      |
| Cover hashing on ambiguous match | yes        | yes      | optional (config: `fast.skip_cover_hash`) |
| `min_confidence` default         | 0.50       | 0.50     | 0.60                                      |

`fast` raises the bar so borderline matches get classified as NO_MATCH
(unattended) or PROMPT (attended) rather than auto-write. This is a fail-closed
orientation: in `fast`, "we're not sure" should become "skip and move on" rather
than risk writing wrong tags into hundreds of files.

Cover hashing in `fast` is _configurable_ rather than hard-off. Cover downloads
from CV count against the rate-limit budget. In `fast` mode the user can opt out
via `fast.skip_cover_hash: true` if they want to push throughput further;
default stays "hash when ambiguous" because the cost is amortized via the
URL→pHash SQLite cache after first hit.

### Post-accept fetches

`get_issue(id)` after an AUTO_WRITE always runs — it's the only way to get full
issue metadata. Same in all modes. `get_volume(volume_id)` for the
publisher-injection trick on CV gets skipped in `fast` (the matcher already has
the series name from the candidate; the publisher we'd be missing is recoverable
from local metadata or future runs).

### What stays the same in all modes

- The matcher's signal weights (`W_SERIES`, `W_ISSUE`, etc.) — those are the
  _quality_ of the ranking, not the _quantity_ of API calls.
- The Match Resolution Policy (`strict`/`normal`/`eager`/`always-prompt`) —
  that's how a verdict gets applied, orthogonal to budget.
- Cache and rate-limit infrastructure — both modes use the same SQLite buckets
  and response caches.
- `--id`, `--series-id` short-circuits — explicit ids skip the discovery
  two-step regardless of mode.

## Defaults and auto-detection

`api_budget` defaults to `balanced` (today's behavior, exact match).

Auto-detection should be **conservative and verbose**, not silent and clever.
Triggers fire per-source — Metron's looser cap means its auto-engagement
threshold is much higher than ComicVine's, but **both sources auto-engage at
some library size**. At the extreme — a 500,000-comic collection — even Metron's
5,000/day daily cap means a full sweep takes 100 days under `balanced`; `fast`
matters everywhere if you're tagging enough.

Triggers, both logged loudly when they fire:

1. **`--unattended` + batch size ≥ per-source threshold**: auto-suggest `fast`
   for that source. Thresholds are per-source because the caps are per-source:
    - ComicVine: 200/hr → threshold ~50 comics (≈ 2.5 hours of waiting under
      `balanced`).
    - Metron: 1,200/hr but 5,000/day → threshold ~500 comics (≈ a day of waiting
      under `balanced`).

    Both numbers are Phase B placeholders; calibration data picks the real curve
    breakpoints. Logs:

    ```
    online: auto-enabling api_budget=fast for comicvine (batch=343 >= 50,
    unattended). Override with --api-budget-per-source comicvine:balanced.
    ```

2. **stdin is not a TTY**: same condition with stricter thresholds (~4× the
   attended numbers). Cron-shaped invocations get the suggestion at a higher
   threshold so manual `xargs` pipelines don't surprise the user.

In both cases the user can override explicitly with `--api-budget` (which takes
precedence over auto-detection). Auto-detection is a hint, not a policy.

## Rollout phases

This work ships in **three sequential phases**. Phase B (calibration) is
load-bearing — the thresholds in this spec are placeholders chosen on intuition;
only Phase B's data can confirm or correct them. Phase C (integration + release)
only proceeds with Phase B's numbers in hand.

### Phase A — Build

Land the levers as code, with placeholder thresholds. Nothing user-visible ships
at end of Phase A; the new code is dormant on the default `balanced` budget.

1. **`config/settings.py`**: add `APIBudget` enum + `api_budget` +
   `api_budget_per_source`. Wire into `OnlineSettings.from_confuse(...)`. Add
   `resolve_api_budget(settings, source_name)` helper next to the existing
   `resolve_*` helpers.

2. **`online/sources/comicvine.py`**: read `_MAX_VOLUMES_PER_SEARCH` from the
   resolved budget instead of the class constant; the class constant stays as
   the `balanced` default.

3. **`online/sources/metron.py`**: same shape, `_MAX_SERIES_PER_SEARCH`.

4. **`online/sources/base.py`** (or a new module `online/series_filter.py`): add
   `should_keep_volume_name(profile_series, volume_name, threshold)` — shared by
   both sources. Uses `rapidfuzz.fuzz.token_set_ratio` (same primitive as
   `s_series` in `signals.py`).

5. **Per-source caller pass-through**: each source threads `resolved_budget`
   into its search loop and consults `should_keep_volume_name` before issuing
   `list_issues`.

6. **`online/matcher.py`**: `OnlineMatcher.resolve(...)` reads
   `resolve_confidence_threshold(settings, source_name)` already; per-source
   override pattern flexes here naturally — `fast` just sets a higher default.
   No code change required, only config wiring.

7. **`box/online_lookup.py`**: stub out orchestrator-level auto-detection. Wire
   the inputs (batch size, `unattended`, TTY) but keep the trigger thresholds as
   `None` until Phase B confirms them. No auto-engagement actually fires from
   this PR.

8. **Calibration harness**: add `--api-budget` pass-through so we can measure
   each setting empirically. Also add `--label` so we can name runs and compare
   across them (`fixtures.outcomes.fast-threshold-0.5.json`, etc.). Outcomes
   files merge cleanly via the existing `--retry-misses` plumbing.

9. **Unit tests** for the resolve helpers and the series-name filter. Behavioral
   tests come in Phase B against the fixture set.

### Phase B — Calibrate

Run experiments against the 343-fixture set. Output: principled threshold
numbers grounded in observed data, plus a writeup. Lives in
`tasks/online-tagging/calibration-notes/` as dated markdown files.

The experiment matrix:

| Run | Budget       | Pre-filter threshold | `_MAX_VOLUMES_PER_SEARCH` | `_TOP_K_FOR_HASHING` | Purpose                    |
| --- | ------------ | -------------------- | ------------------------- | -------------------- | -------------------------- |
| B0  | `balanced`   | n/a (off)            | 20                        | 5                    | Current-behavior baseline. |
| B1  | `exhaustive` | off                  | 20                        | 5                    | Accuracy ceiling.          |
| B2  | `fast`       | 0.4                  | 5                         | 5                    | Conservative fast.         |
| B3  | `fast`       | 0.5                  | 5                         | 5                    | Tighter pre-filter.        |
| B4  | `fast`       | 0.6                  | 5                         | 5                    | Tighter still.             |
| B5  | `fast`       | 0.7                  | 5                         | 5                    | Aggressive pre-filter.     |
| B6  | `fast`       | _winner from B2-B5_  | 3                         | 5                    | Lower max-per-search.      |
| B7  | `fast`       | _winner_             | 10                        | 5                    | Higher max-per-search.     |
| B8  | `fast`       | _winner_             | _winner_                  | 2                    | Lower top-K hashing.       |
| B9  | `fast`       | _winner_             | _winner_                  | 3                    | Mid top-K hashing.         |

Per-run measurements (all in the outcomes JSON for post-hoc grep):

- Per-band correctness (the existing report).
- Total wall-clock time (cold cache for B0; warm cache for B1-B9 to isolate the
  algorithm changes from cache benefits).
- Total API calls per source (need a counter in the harness — small addition).
- Percentage of NO_MATCH outcomes (proxy for "skipped too aggressively").
- Per-fixture: which volumes got dropped by the pre-filter. Catches
  false-negative pre-filter cases.

Tooling Phase B needs that doesn't exist yet:

- **Run labeling** (`--label NAME`) → already in Phase A.
- **API-call counter** in each source. Increment on cache miss. Serialized into
  outcomes JSON.
- **Outcomes-comparison tool**: `tests/calibration/compare.py` that takes two
  outcomes files and diffs the per-fixture results. Highlights fixtures that
  flipped correct→wrong or wrong→correct between runs.

Calibration thresholds get pinned at end of Phase B as PRs against this spec:
replace placeholder numbers (50/200, 0.4/0.7, top-K, etc.) with data-driven
values and remove the corresponding `*placeholder*` callouts from the lever
tables.

### Phase C — Integrate & ship

1. **Wire the auto-engagement triggers in `box/online_lookup.py`** using the
   thresholds Phase B confirmed.

2. **CLI flags**: add `--api-budget` and `--api-budget-per-source`. Help text
   references the user doc.

3. **User doc**: add `tasks/online-tagging/api-budget-user-doc.md` alongside
   `match-resolution-user-doc.md`. Covers: when to pick which mode, what each
   one trades, the auto-engagement behavior, per-source overrides.

4. **NEWS.md**: user-facing entry covering the flag, the auto-detection, and a
   pointer to the user doc.

5. **Calibration acceptance check**: re-run B0/B1 against the _shipped_ code
   (not the prototype) to confirm no regression. Sign-off requires:
    - `fast` mode completes the 343-fixture set in ≤2 hours cold-cache
      (currently ~17h).
    - `fast` auto-write band ≥97% correct (vs `balanced`'s post-Watchmen-fix
      baseline).
    - `fast` produces ≤5% more NO_MATCH outcomes than `balanced`.
    - `exhaustive` matches `balanced` accuracy within 1 percentage point (i.e.,
      the cost of full breadth isn't paying off measurably, OR it is and we know
      which fixtures benefit).

## What's NOT in this spec

- **Adaptive mid-run downgrade.** Tempting design: notice we're rate-limited for
  the 3rd time in 10 minutes and auto-switch from `exhaustive` to `fast` for the
  rest of the batch. Too much hidden state. Out of scope.
- **Cost telemetry.** "You spent 187/200 hourly budget on this run" is useful
  but separate. Worth a follow-up spec; not in this one.
- **Cross-source budget pooling.** If Metron's bucket is empty but CV's is full,
  lean harder on CV. Future work; out of scope here.
- **Per-workflow presets** (e.g. `--api-budget-preset metron-tagger-style` or
  `--api-budget-preset comicvine-only`). Considered and rejected:
  source-exclusive presets are already expressible by configuring credentials
  for only one source (or by `--online <source>` selection). Source selection
    - per-source budget cover the same surface without adding a separate naming
      dimension. The same argument applies to any preset that's really "use
      source X with these settings" — that's not a preset, it's the source's own
      config. If a workflow is common enough to want sugar, it can be documented
      as a one-line example in the user doc — no code needed.
