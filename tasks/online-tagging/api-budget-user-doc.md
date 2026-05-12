# API Budget — User-Perspective Doc

User-facing description of `--api-budget` — comicbox's lever for trading
matching accuracy against per-comic API call cost. Composes with `--policy` and
`--unattended`; orthogonal to both. See
[`match-resolution-user-doc.md`](match-resolution-user-doc.md) for the related
"what does comicbox do once it has candidates" decision.

Source of truth for the current implementation:
`comicbox/online/series_filter.py` (thresholds, validated against the
spring-2026 calibration set — [notes](calibration-notes/2026-05-11-phase-b.md)).

---

## What the lever does

Comicbox's online lookup is fundamentally a two-step API dance:

1. **Discovery**: ask the upstream source (Metron / ComicVine) for volumes whose
   name resembles the comic's series.
2. **Per-volume lookup**: for each candidate volume, fetch issues matching the
   issue number (and optionally a cover-date window).

Step 2 is where the API budget goes — up to 20 calls per comic, one per
discovered volume. Most of those volumes are obvious mismatches ("Lois Lane: A
Celebration", "The Adventures of Basil & Moebius" for a "Moebius Library"
comic). The matcher would score them near-zero and ignore them — but the API
call to confirm has already been spent.

`--api-budget` controls how aggressively comicbox pre-filters those
obvious-mismatch volumes BEFORE step 2 fires. The trade-off:

| Mode                 | Pre-filter strictness                | API cost           | Accuracy on validated set                                                     |
| -------------------- | ------------------------------------ | ------------------ | ----------------------------------------------------------------------------- |
| `exhaustive`         | off                                  | highest            | 99.7%                                                                         |
| `balanced` (default) | conservative (drops obvious garbage) | −18% vs exhaustive | 99.7% (identical)                                                             |
| `fast`               | aggressive                           | −60% vs exhaustive | 100% — and correctly says "I don't know" on the one case `balanced` got wrong |

The validated numbers come from a 339-fixture calibration run against a real
comic library. Your library may behave differently — the lever's defaults aim to
be safe-and-fast (balanced) and let you escalate or de-escalate when needed.

---

## When to pick which mode

### `--api-budget exhaustive`

"Spend whatever it takes; I want the best possible match." Use when:

- Tagging one comic (or a small handful) interactively and the matcher is
  borderline-confident; you want to see every plausible volume, not have the
  pre-filter prune anything.
- Debugging a wrong-volume pick — `exhaustive` shows you the full candidate set
  the matcher had to work with.
- You have a private API tier and aren't rate-limited.

Cost: highest. Roughly 32 API calls per comic in the validated set.

### `--api-budget balanced` (the default)

"Drop the obvious mismatches; don't overthink it." Use when:

- Most of the time. Default for a reason.
- Your library is small-to-medium (< 50 comics in one go) and you want maximum
  accuracy preservation with the side benefit of ~18% fewer API calls.
- You don't know which mode you want.

Cost: ~26 API calls per comic.

### `--api-budget fast`

"I'm tagging a lot at once; trade a tiny accuracy notch for big API savings."
Use when:

- Library is large (100+ comics on ComicVine, 500+ on Metron) and you can't wait
  through the rate cap.
- You're running unattended and would rather skip ambiguous cases than wait an
  hour.
- You're OK with the matcher returning "no candidates" on cases that `balanced`
  would have scored just below the auto-write threshold (i.e., would have
  prompted you anyway).

Cost: ~13 API calls per comic — about a 60% reduction. At ComicVine's 200/hr
cap, that's roughly 15 comics/hour vs balanced's ~6.

---

## Auto-engagement

Comicbox watches two signals and auto-engages `fast` mode per-source when it
would meaningfully reduce your wait time:

| Signal                        | ComicVine threshold | Metron threshold    |
| ----------------------------- | ------------------- | ------------------- |
| `--unattended` set            | batch ≥ 50 comics   | batch ≥ 500 comics  |
| stdin not a TTY (cron / pipe) | batch ≥ 200 comics  | batch ≥ 2000 comics |

Why different thresholds:

- **Per-source**: ComicVine's 200/hour cap is six times tighter than Metron's
  1,200/hour, so the breaking point for "this is going to take all day" is much
  lower on the CV side.
- **TTY vs unattended**: explicit `--unattended` is a strong signal you want
  batch behavior; non-TTY without `--unattended` could be a manual `xargs`
  pipeline, so the bar is stricter.

When auto-engagement fires, you'll see an INFO line:

```
online: auto-engaging api_budget=fast for comicvine (batch=343 >= 50,
unattended). Override with --api-budget-per-source comicvine:balanced.
```

You can suppress per-source with `--api-budget-per-source <source>:balanced` or
globally by setting `--api-budget exhaustive` (or `--api-budget fast` to make it
explicit-not-auto).

---

## Per-source overrides

Same shape as `--policy`. The flag is repeatable; bare values set the global
default, `source:value` pairs set a per-source override:

```sh
# Global default: exhaustive for everything.
comicbox --online --api-budget exhaustive *.cbz

# Mixed: fast on the rate-tight source, exhaustive on the looser one.
comicbox --online --api-budget comicvine:fast --api-budget metron:exhaustive *.cbz

# Mixed: global default + one override.
comicbox --online --api-budget fast --api-budget metron:balanced *.cbz
```

Per-source overrides ALWAYS win over the global default. Auto-engagement
respects user-set per-source overrides and never overrides them.

Environment variable equivalent: `COMICBOX_ONLINE_API_BUDGET=fast` for the
global setting. (No per-source env-var form yet; use the CLI flag or config
file.)

---

## Interaction with other settings

- **`--policy`**: orthogonal. `--api-budget` controls how candidates are
  produced; `--policy` controls what happens once they exist. Example:
  `--api-budget fast --policy strict` is a sensible unattended-batch
  combination.

- **`--unattended`**: triggers auto-engagement (see above) but is otherwise
  independent.

- **`--confidence-threshold`**: independent — same threshold applies regardless
  of budget. (Phase B preserved this for simplicity; a per-budget confidence
  threshold could be a future enhancement.)

- **`--id` / `--series-id`**: short-circuit the entire discovery flow;
  `--api-budget` doesn't affect them.

- **`--max-per-search`** (in the calibration harness only): an alternative
  escape valve that lowers the discovery breadth directly. Equivalent for
  measurement purposes but more granular than the three-tier `--api-budget`. The
  harness uses it; the production CLI uses `--api-budget`.

---

## What you'd lose under `fast`

The single labeled-fixture difference between `balanced` and `fast` on the
validated 339-comic set:

- **Moebius Library (2016) #001**: `balanced` returns a wrong-volume candidate
  at score 0.76 (below the 0.95 auto-write threshold, so it would have prompted
  you anyway). `fast` correctly returns no candidates — its pre-filter drops the
  "Adventures of Basil & Moebius" volume that `balanced` admits.

User-visible behavior: under both modes you don't get a wrong auto-write. Under
`balanced` you might see a prompt that you would reject; under `fast` you don't
see the prompt. Both end up with the comic untagged unless you supply
`--id comicvine:555444` directly.

This pattern generalizes: `fast`'s "false negatives" are cases where the matcher
would have prompted under `balanced` and you'd have declined. The savings come
from skipping the prompt-or-skip dance entirely. If your workflow auto-accepts
prompts, you may see slightly fewer suggestions under `fast`; if you reject most
prompts (the common case for ambiguous matches), the difference is invisible.

---

## When `fast` is wrong for you

Use `--api-budget exhaustive` (or `balanced` per-source) when:

- You're tagging an obscure series and need the matcher to consider every
  plausible volume — even ones with name-similarity below 0.7.
- You're testing the matcher against new data and want to see what it WOULD have
  found before filtering.
- You're not actually batch-tagging — auto-engagement won't fire for small
  batches anyway, but explicit `--api-budget exhaustive` guarantees nothing's
  hidden.

There's no scenario where `fast` is _strictly_ wrong on the validated set — the
only deviation is the strictly-better Moebius case described above. But your
library may exercise the pre-filter in ways the calibration set didn't.
