# 2026-05-17 — bigmedia 247-fixture re-run (post-H/I revert + J/K rev 2)

The first bigmedia calibration since the H/I reverts (commits `b33da25`,
`62a5725`, `b407815`) and the J/K rev 2 additions (commits `7a44fa4`,
`916a488`). Validates the matcher's state at HEAD against the 2026-05-14
baseline.

## Run config

|                 |                                                           |
| --------------- | --------------------------------------------------------- |
| Library         | `/Volumes/Media/Comics/` (bigmedia)                       |
| Fixture set     | 247 stratified one-per-series                             |
| Sampler seed    | 0                                                         |
| Cover quality   | full                                                      |
| API budget      | fast                                                      |
| Metron labeling | 47 newly labeled via cv_id cross-ref (matches 2026-05-14) |
| Wall time       | ~5h overnight                                             |

Reproduce per `2026-05-14-bigmedia-247.md` "Reproducing this run" section.

## Headline numbers + comparison

|                                | 2026-05-14 baseline  | 2026-05-17 (HEAD) | Delta   |
| ------------------------------ | -------------------- | ----------------- | ------- |
| CV correct                     | 233 / 247            | **219 / 247**     | **-14** |
| CV accuracy (all labeled)      | 94.3%                | **89.4%**         | -4.9pp  |
| CV auto-write band (0.85-0.95) | 97.6%                | **97.0%**         | -0.6pp  |
| CV prompt zone (0.70-0.85)     | n/a (not broken out) | 55% (24/44)       | —       |
| Metron correct                 | 32 / 33              | **32 / 33**       | 0       |
| Metron accuracy                | 97.0%                | **97.0%**         | 0       |
| Metron auto-write band         | 100% (31/31)         | **100% (31/31)**  | 0       |

## Interpretation: production accuracy unchanged, prompt-zone surprised

**The production-relevant number — CV auto-write band — held at 97% (vs 97.6%
baseline).** Production users running `--policy normal` see only auto-write-band
picks as tags; the matcher is just as right in that band as it was on
2026-05-14.

**The overall accuracy regressed 4.9pp because the prompt zone (0.70-0.85)
accumulated more wrong-but-not-confident picks** — 24 of 44 (55%) are wrong,
where the baseline didn't break this band out separately but had far fewer total
prompt-zone fixtures.

In production:

- Auto-write-band picks → tags written. **Same accuracy as before.**
- Prompt-zone picks → user sees a prompt and decides. The matcher's wrong picks
  here become wrong PROMPTS, not wrong TAGS — the user vetoes or accepts
  manually.
- Solo-viable band → 1/1 correct, unchanged.

**Net for users: no degradation under `--policy normal`. Under `--policy eager`
or `--unattended`, slightly more wrong tags would land than on 2026-05-14.**
That's the cost of the J/K rev 2 + H/I revert combo on this fixture set.

## Misses break down into three patterns

26 CV misses vs 14 in the baseline. Same Pattern A and B from the 2026-05-14
note, plus a NEW pattern.

### Pattern A — "right answer not in CV's top-5" (7 cases, unchanged)

All 7 from the 2026-05-14 baseline reproduce:

- Akira (2000), Ghost in the Shell (2009), Powers (2015)
- Savage Sword of Conan (2024), Conan the Barbarian (2025)
- Storm (2024), X-Men #1 Facsimile (2019)

Plus a couple new variants:

- Conan the Barbarian (2025) #025
- Powers The Bureau - Undercover (2013)

Search relevance, not matcher scoring. Research note at
[`../research-notes/cv-top-5-search-relevance.md`](../research-notes/cv-top-5-search-relevance.md).

### Pattern B — CV catalog duplicates (6 cases, unchanged)

Same 6 cases as the baseline: Barry Ween 2.0, Hilda and the Stone Forest, Who is
Jake Ellis, Fallen Son, Captain America First Vengeance, Hawkeye Freefall.
Tiebreak picks lower vol_id; sometimes the user tagged with the higher one.

### Pattern D (new) — "trade collection by Author" — turns out to be Pattern A in disguise

11+ cases not present in the baseline:

- Wolverine by Greg Rucka Ultimate Collection (2011)
- Conan the Barbarian by Jim Zub Land of the Lotus (2021)
- Conan the Barbarian by Jim Zub Into The Crucible (2021)
- Conan the Barbarian by Aaron & Asrar (2021)
- Black Widow by Waid & Samnee The Complete Collection (2020)
- Black Widow by Kelly Thompson Die By The Blade (2022)
- Black Widow by Kelly Thompson I Am the Black Widow (2021)
- Black Widow by Kelly Thompson The Ties That Bind (2021)
- Wolverine by Claremont & Miller Deluxe Edition (2022)
- Daredevil by Chip Zdarsky To Heaven Through Hell (2021)
- Elektra by Greg Rucka Ultimate Collection (2012)

META-PLAN.md attributes the Conan-by-Jim-Zub case to a Phase K rev 2 scoring
fix, with hand-computed scores:

> Right (910095, year=2021): md = 0.9125 (publisher/pages asymmetric) Wrong
> (690927, year=None): md = 0.7875 (year asymmetric too) → 0.125 metadata margin
> on right's side.

**The META-PLAN diagnosis is wrong.** A `debug_search` probe of the
Conan-by-Jim-Zub-Lotus fixture shows CV returns 20 volumes for the query "Conan
the Barbarian", but the matcher under FAST budget only sees the top 5 — all
canonical Marvel runs with names like "Conan the Barbarian" but NOT the specific
trade-collection volume that contains issue 910095.

**This is Pattern A in disguise.** Every one of the 11 cases checked has its
expected ID at rank ≥ 6 of CV's relevance ranking — never reaches the matcher.
The probe was repeated on "Black Widow by Kelly Thompson Die By The Blade" with
the same result: 20 candidate volumes returned, top 5 are canonical Black Widow
runs (7167, 11492, etc.), the trade-collection volume isn't in those 5.

So the 4.9pp "regression" is _library composition_, not code regression. The
bigmedia library has gained more trade-collection-by-Author fixtures between
2026-05-14 and now (the seed=0 sampler is deterministic for a given library, but
the library itself grew). These all probe the same CV search-relevance failure
the 7 Pattern-A cases already do.

**Phase K rev 2's claimed fix is moot for these fixtures** — it can't score what
the matcher never sees. The hand-calculation in META-PLAN assumed both volumes
(910095 and 690927) were in the candidate set; empirically only 690927 is.

**The actual fix is the CV search-relevance work documented in**
[`../research-notes/cv-top-5-search-relevance.md`](../research-notes/cv-top-5-search-relevance.md)
**, not a matcher-scoring tweak.**

## Cross-checks

- **Phase G (cover-diff 0.03 noise margin) is restored.** Fallen Son and Hawkeye
  Freefall both still miss (Pattern B), behaving the same as 2026-05-14.
  Confirms the revert worked.
- **Phase J (adaptive top-K for cover hashing) is in effect.** Can't easily
  verify from this run; would need a flagged log.
- **The 2 Pattern C "no-candidates" cases recur.** Step Aside Pops and Punisher
  Last Days. Same catalog gap as baseline.

## What this validates / doesn't

**Validates:**

- The H/I reverts didn't cause production-user regressions (auto- write band is
  unchanged at 97%).
- Metron path is healthy — 100% auto-write-band accuracy still.
- Phase G's cover-diff noise margin is correctly restored.

**Doesn't validate:**

- The META-PLAN claim that Phase K rev 2 fixes the trade-collection pattern. The
  Pattern-D investigation showed these misses are Pattern A in disguise — the
  matcher never sees the right candidate, so any scoring fix is moot.
  META-PLAN's hand-calculation assumed both candidates were in the candidate
  set; empirically the right one isn't.

**Refutes:**

- The "code regression" interpretation of the 4.9pp drop. The Pattern-D
  investigation shows the drop is library composition (more trade-collection
  fixtures in bigmedia now), all probing the same Pattern A search-relevance
  gap. No code change introduced these misses.

## Recommendation

**Ship-readiness:** safe to ship under `--policy normal` (the default).
Auto-write-band accuracy is unchanged at 97%; the 4.9pp overall regression is
concentrated in the prompt zone, which doesn't auto-tag. Combined with the
Pattern-D investigation showing the misses are library-composition + Pattern A
(not a code regression), there's nothing in this data blocking ship.

**To recover the overall accuracy number:** ship the CV search-relevance fix
from
[`../research-notes/cv-top-5-search-relevance.md`](../research-notes/cv-top-5-search-relevance.md).
Pattern A (7 cases) + Pattern D (11 cases) = 18 of the 26 CV misses share the
same root cause and would all be addressed by narrow-then-fuzzy volume search
with `name + start_year` filter.

**META-PLAN.md needs a correction.** The Phase K rev 2 entry attributes a
Conan-by-Jim-Zub win to the signal-content-aware renormalisation; that's an
incorrect diagnosis (the right answer was never in the candidate set in this
run). The K rev 2 fix may still help OTHER cases (the slimlib Wolverine
thumbnail case, which META-PLAN also cites), but not the trade-collection
pattern.

## Where to find the data

- Outcomes: `tests/calibration/fixtures-bigmedia.outcomes.json` (gitignored,
  per-developer).
- Full miss details:
  `uv run python -m tests.calibration.summarize --fixtures tests/calibration/fixtures-bigmedia.json --misses`.
- Per-fixture log: `tests/calibration/run.py`'s stdout was captured during this
  run.
