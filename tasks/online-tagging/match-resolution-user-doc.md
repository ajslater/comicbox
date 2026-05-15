# Match Resolution — User-Perspective Doc

User-facing description of how comicbox decides whether to auto-write, prompt,
skip, or report no-match when an online source returns candidates for a comic.
This is a **proposed** design (rev 2), replacing the current `--accept-only` /
`--skip-multiple` flag scheme with two orthogonal knobs: `--unattended` and
`--policy`.

Source of truth for the current implementation: `comicbox/online/matcher.py`.
The proposal in this doc has not yet shipped.

---

## What "match resolution" means

When `--online metron` (or `comicvine`) is enabled, comicbox queries the
configured DB for each comic and gets back a list of candidate matches —
typically 1 to ~20 items per source. Each candidate is scored against the
comic's existing metadata, then sorted. **Match resolution is the rule that
turns that ranked list into a single decision per (comic, source):**

- **AUTO_WRITE** — pick the top candidate and apply its metadata, no prompt.
- **PROMPT** — show the user the ranked candidates and ask which (if any) to
  pick.
- **SKIP** — make no change to this comic; move on. This is informative —
  comicbox saw plausible candidates and declined to pick one.
- **NO_MATCH** — nothing scored well enough to be worth showing. Distinguishable
  from SKIP in the end-of-run summary.

The goal is to support three use cases with one rule set:

1. **Unattended automation** (cron job, codex batch). No prompting possible.
2. **Interactive CLI** (one or many files, user at the keyboard).
3. **Library use** (comicbox-as-dependency, e.g. codex with a registered prompt
   callback). Interactive, but not via TTY.

---

## The score: where 0.0–1.0 comes from

Every candidate gets a score in `[0, 1]`. Higher = more confident match. Score
is a weighted sum of metadata signals plus an optional cover-hash signal:

| Signal     | Weight   | What it compares                                    |
| ---------- | -------- | --------------------------------------------------- |
| Series     | 0.30     | Filename/tag series name vs candidate's series name |
| Issue #    | 0.25     | Filename/tag issue number vs candidate's number     |
| Year       | 0.10     | Filename/tag year vs candidate's cover-date year    |
| Publisher  | 0.10     | Tag publisher vs candidate's publisher name         |
| Page count | 0.05     | Archive page count vs candidate's reported count    |
| **Sum**    | **0.80** | (metadata only)                                     |
| Cover hash | 0.20     | pHash distance, local cover vs candidate cover      |

When cover hashing isn't invoked (see below), the metadata-only score is
renormalised to `[0, 1]` by dividing by 0.80.

**Cover hashing is invoked only when the metadata-only ranking is ambiguous** —
either the top score is below the auto-write threshold, or the gap between top
and runner-up is small. This avoids burning API/IO on already-clear cases.

---

## Internal thresholds (not user-facing)

| Constant                | Value | Role                                                                                                                |
| ----------------------- | ----- | ------------------------------------------------------------------------------------------------------------------- |
| `confidence_threshold`  | 0.95  | Above this, top is "auto-write worthy" (was 0.85; bumped post-calibration to suppress wrong-volume false positives) |
| `min_confidence`        | 0.50  | Below this, candidate is "not viable"                                                                               |
| `disambiguation_margin` | 0.10  | Required gap between top and runner-up for unambiguous                                                              |

These are calibration values — they live inside the matcher and you don't tune
them per-run. The two user-facing knobs (`--unattended` and `--policy`) compose
these into a behavior you choose.

`--confidence-threshold N` remains as a power-user override if you really want
to retune the auto-write bar, but the named policies should cover nearly all use
cases.

---

## The two knobs

### `--unattended` (boolean flag, default off)

When set: **never prompt.** Any decision that would have prompted becomes SKIP
instead.

Default off because the library / codex use case may run without a TTY but still
want interactive behavior via a registered prompt callback. The flag is explicit
— comicbox does not auto-flip to unattended based on TTY detection, because that
would silently change behavior for programmatic callers. If you want
unattended-on-cron-job behavior, pass the flag.

When stdin isn't a TTY and `--unattended` is not set and no programmatic prompt
callback is registered, comicbox logs a one-time hint at startup: _"no TTY
detected; pass `--unattended` if you don't expect to see prompts."_ This catches
the common cron-job-without-the-flag mistake without changing default behavior
for library callers (whose registered callback silences the hint).

### `--policy <name>` (default `normal`)

Four levels along an axis from "ask me about everything" to "trust the matcher
fully":

| Policy             | Behavior on top candidate ≥ confidence_threshold and clear gap | Behavior on solo viable (one ≥ min_confidence, no peers) | Behavior on top above threshold but narrow gap |
| ------------------ | -------------------------------------------------------------- | -------------------------------------------------------- | ---------------------------------------------- |
| `always-prompt`    | PROMPT                                                         | PROMPT                                                   | PROMPT                                         |
| `strict`           | AUTO_WRITE                                                     | PROMPT                                                   | PROMPT                                         |
| `normal` (default) | AUTO_WRITE                                                     | AUTO_WRITE                                               | PROMPT                                         |
| `eager`            | AUTO_WRITE                                                     | AUTO_WRITE                                               | AUTO_WRITE                                     |

In all four levels: candidates with `top.score < min_confidence` produce
NO_MATCH. NO_MATCH never auto-writes regardless of policy.

The progression is **strictly containing** — `eager` ⊃ `normal` ⊃ `strict` ⊃
`always-prompt` in terms of what gets auto-written. Anything `strict`
auto-writes, `normal` auto-writes too, and so on up to `eager`. The formal
rules:

- `strict`: AUTO_WRITE iff `unambig` (top ≥ 0.85 AND gap ≥ 0.10)
- `normal`: AUTO_WRITE iff `unambig` OR `solo_viable` (top ≥ 0.50 AND exactly
  one viable candidate)
- `eager`: AUTO_WRITE iff `top.score ≥ 0.85` OR `solo_viable`

Conservative users tune toward `strict`; users who trust their setup tune toward
`eager`.

### Combining the two

The 8-cell matrix below is what `--unattended` does to each PROMPT cell:

|                    | interactive (default)                                          | `--unattended`                                             |
| ------------------ | -------------------------------------------------------------- | ---------------------------------------------------------- |
| `always-prompt`    | prompts on every viable candidate                              | skips every viable candidate (essentially a dry-run)       |
| `strict`           | auto-writes unambiguous tops; prompts the rest                 | auto-writes unambiguous tops; skips the rest               |
| `normal` (default) | auto-writes unambiguous + solo-viable; prompts rest            | auto-writes unambiguous + solo-viable; skips rest          |
| `eager`            | auto-writes top above threshold; prompts only on sub-threshold | auto-writes top above threshold; skips sub-threshold cases |

`always-prompt --unattended` is mathematically valid but produces zero
auto-writes — useful for "show me what comicbox would have considered" runs
(similar to `--dry-run` in spirit).

---

## The decision algorithm

After the matcher ranks candidates, exactly one of
`AUTO_WRITE / PROMPT / SKIP / NO_MATCH` is chosen per the following:

```
top      = ranked[0]                         # highest-scored candidate
runner   = ranked[1] or None
gap      = top.score - runner.score if runner else 1.0
unambig  = top.score >= 0.85 AND gap >= 0.10
solo_viable = top.score >= 0.50 AND len([c for c in ranked if c.score >= 0.50]) == 1

# 1. Hard floor
if not ranked or top.score < 0.50:           → NO_MATCH

# 2. Policy decides whether to auto-write
elif policy == always-prompt:                → defer to step 3
elif policy == strict and unambig:           → AUTO_WRITE
elif policy == normal and (unambig or solo_viable):              → AUTO_WRITE
elif policy == eager  and (top.score >= 0.85 or solo_viable):    → AUTO_WRITE
else:                                        → defer to step 3

# 3. Couldn't auto-write; ask or skip
if --unattended:                             → SKIP
else:                                        → PROMPT
```

The gap rule (the 0.10 disambiguation margin) lives inside `unambig` and is
intentionally hidden from users — it's an implementation detail of "what counts
as a clear winner." `strict` and `normal` honor it; `eager` waives it and trusts
the threshold alone.

---

## Worked examples

For each scenario, candidates are listed by score after ranking. All defaults
active unless noted (`policy=normal`, interactive).

### Scenario 1 — clear winner

Candidates: A=0.92, B=0.71

| Policy        | Interactive  | `--unattended` |
| ------------- | ------------ | -------------- |
| always-prompt | PROMPT       | SKIP           |
| strict        | AUTO_WRITE A | AUTO_WRITE A   |
| normal        | AUTO_WRITE A | AUTO_WRITE A   |
| eager         | AUTO_WRITE A | AUTO_WRITE A   |

Why: top ≥ 0.85 and gap = 0.21 ≥ 0.10 → unambiguous. Strict, normal, eager all
auto-write.

### Scenario 2 — close call near the top

Candidates: A=0.86, B=0.84

| Policy        | Interactive  | `--unattended` |
| ------------- | ------------ | -------------- |
| always-prompt | PROMPT       | SKIP           |
| strict        | PROMPT       | SKIP           |
| normal        | PROMPT       | SKIP           |
| eager         | AUTO_WRITE A | AUTO_WRITE A   |

Why: top ≥ 0.85 but gap = 0.02 < 0.10. Only `eager` waives the gap and takes A.

### Scenario 3 — one decent match, one weak match

Candidates: A=0.70, B=0.45

| Policy        | Interactive  | `--unattended` |
| ------------- | ------------ | -------------- |
| always-prompt | PROMPT       | SKIP           |
| strict        | PROMPT       | SKIP           |
| normal        | AUTO_WRITE A | AUTO_WRITE A   |
| eager         | AUTO_WRITE A | AUTO_WRITE A   |

Why: top is below auto-write threshold (0.85), so `unambig` is false. Only one
viable (B is below 0.50), so `solo_viable` is true → `normal` and `eager` both
auto-write A. `strict` requires `unambig` and gets neither.

### Scenario 4 — sole candidate, just above the auto-write bar

Candidates: A=0.86

| Policy        | Interactive  | `--unattended` |
| ------------- | ------------ | -------------- |
| always-prompt | PROMPT       | SKIP           |
| strict        | AUTO_WRITE A | AUTO_WRITE A   |
| normal        | AUTO_WRITE A | AUTO_WRITE A   |
| eager         | AUTO_WRITE A | AUTO_WRITE A   |

Why: only one candidate, gap = 1.0, top ≥ 0.85 → unambiguous.

### Scenario 5 — sole candidate, between thresholds

Candidates: A=0.65

| Policy        | Interactive  | `--unattended` |
| ------------- | ------------ | -------------- |
| always-prompt | PROMPT       | SKIP           |
| strict        | PROMPT       | SKIP           |
| normal        | AUTO_WRITE A | AUTO_WRITE A   |
| eager         | AUTO_WRITE A | AUTO_WRITE A   |

Why: top below `confidence_threshold` but solo viable. `normal` and `eager` both
take it (containment); `strict` requires `unambig`.

### Scenario 6 — nothing meaningful

Candidates: A=0.40, B=0.25

| Policy | Interactive | `--unattended` |
| ------ | ----------- | -------------- |
| any    | NO_MATCH    | NO_MATCH       |

Top is below `min_confidence`. NO_MATCH short-circuits before policy.

### Scenario 7 — exactly one above threshold, runner-up close

Candidates: A=0.92, B=0.84

| Policy        | Interactive  | `--unattended` |
| ------------- | ------------ | -------------- |
| always-prompt | PROMPT       | SKIP           |
| strict        | PROMPT       | SKIP           |
| normal        | PROMPT       | SKIP           |
| eager         | AUTO_WRITE A | AUTO_WRITE A   |

Why: top ≥ 0.85 but gap = 0.08 < 0.10. The exact case the gap rule was designed
to catch — only `eager` auto-writes.

---

## Summary stats

End-of-run report counts each outcome distinctly:

```
N comics processed
  M auto-written  (online tag applied without prompt)
  P prompted      (user chose Q, declined R)
  S skipped       (could not pick automatically — needs review or relaxed policy)
  T no-match      (nothing scored above min_confidence — try different DB or check filename parse)
```

The S vs T distinction matters: S means "comicbox saw plausible candidates and
declined"; T means "the database doesn't seem to know about this comic at all."
Different remediation in each case.

---

## Mapping from current legacy flags

For users upgrading:

| Current flags                   | Equivalent new flags                             |
| ------------------------------- | ------------------------------------------------ |
| (no flags, has TTY)             | (default — interactive `normal`)                 |
| `--accept-only` (alone)         | `--policy normal`                                |
| `--skip-multiple` (alone)       | `--unattended --policy strict`                   |
| `--accept-only --skip-multiple` | `--unattended --policy normal`                   |
| `--confidence-threshold N`      | unchanged — still works as a power-user override |

The legacy flags will be deprecated with warnings, removed in a future version.

---

## Settled questions (was: open questions)

1. **Two thresholds vs one?** Settled: keep both internal (0.85 and 0.50),
   surface a 4-level `--policy` instead of asking users to think about
   thresholds.

2. **Should the gap rule be exposed?** Settled: no. It's an internal
   implementation of "what counts as unambiguous"; `strict` and `normal` honor
   it, `eager` waives it. Users get the choice via policy, not via a numeric
   tweak.

3. **Should `--accept-only` use `confidence_threshold`?** Moot — `--accept-only`
   is replaced by `--policy normal`'s solo-viable rule, which is explicit about
   its threshold being `min_confidence`.

4. **NO_MATCH vs SKIP in summary?** Settled: yes, distinct counts in the
   end-of-run report.

5. **Default policy?** Settled: `normal`. That auto-writes the obvious wins
   (unambiguous + solo viable) and prompts on close calls. Slightly more eager
   than today's default (today's default treats solo viable as ambiguous).

---

## Per-source policy and threshold overrides

`--policy` and `--confidence-threshold` accept a global value or a per-source
override using the same `<source>:<value>` syntax that `--id` and `--api-url`
already use:

```
--policy normal                       # global default
--policy metron:eager                  # override for metron only
--policy strict --policy metron:eager  # global = strict, metron = eager
```

Both flags are repeatable; later occurrences for the same source replace earlier
ones. Resolution order per source:

1. Per-source override (`--policy metron:X`) — wins if set
2. Global value (`--policy X`) — wins otherwise
3. Built-in default (`policy=normal`, `confidence_threshold=0.85`)

Same for `--confidence-threshold`:

```
--confidence-threshold 0.85
--confidence-threshold metron:0.75 --confidence-threshold comicvine:0.90
```

Internal thresholds (`min_confidence`, `disambiguation_margin`) follow the same
per-source machinery even though they're not user-exposed today — when
calibration data later justifies surfacing them, the override syntax is already
in place.

**Use case**: trust your high-quality source more than your fallback. A common
shape might be:

```
--online metron,comicvine --policy metron:eager --policy comicvine:strict
```

— Metron auto-writes plausible matches; ComicVine prompts unless it's truly
unambiguous.

**Validation**: unknown source names error out. Unknown policy names error out.
`--policy <source>:<name>` for a source not in `--online` warns but doesn't
error (the override is harmless if the source isn't queried, but the user
probably typo'd a source name).

---

## Settled questions (rev 2)

1. **The wart in `eager` (was open question 1).** Closed: `eager` redefined as
   "auto-write iff `top.score ≥ 0.85` OR `solo_viable`", so the
   `strict ⊂ normal ⊂ eager` containment now holds. Scenarios 3 and 5 in the
   worked-examples table reflect the fix.

2. **`always-prompt --unattended` (was open question 2).** Closed: reject the
   combination at config-validation time. It's nonsensical (every comic skips,
   no work is done) and almost certainly a user error. Surfacing the error early
   is friendlier than silently skipping every file.

3. **TTY auto-detection (was open question 3).** Closed: do not auto-flip to
   `--unattended`. The flag stays explicit. When stdin isn't a TTY and
   `--unattended` is _not_ set, log a one-time hint at startup: "no TTY
   detected; pass `--unattended` if you don't expect to see prompts."
   Programmatic library callers (codex with a registered prompt callback)
   silence the hint by registering the callback before run.

4. **`--policy` and `--confidence-threshold` interaction (was open question
   4).** Closed: keep both. `eager --confidence-threshold 0.70` is a meaningful
   "trust the matcher even more aggressively" combination. Per-source overrides
   on either flag work the same way.

---

## What I'd still flag for later

- **"Always prompt the first N, then go unattended."** Supervise early, trust
  later. Run two batches — first interactive on a sample, then unattended on the
  rest once you're satisfied. Not a flag; just a workflow.
- **Default policy choice.** Default is `normal`, slightly more eager than
  today's behavior. If real-world calibration shows `normal` is too eager (high
  false-positive write rate), retreat the default to `strict`. Calibration
  harness (section 2 in TODO.md) is the place to find out.
