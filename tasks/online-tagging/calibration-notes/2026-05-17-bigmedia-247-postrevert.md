# 2026-05-17 — bigmedia 247-fixture re-run (post-H/I revert + J/K rev 2)

The first bigmedia calibration since the H/I reverts (commits
`b33da25`, `62a5725`, `b407815`) and the J/K rev 2 additions
(commits `7a44fa4`, `916a488`). Validates the matcher's state at
HEAD against the 2026-05-14 baseline.

## Run config

| | |
| --- | --- |
| Library | `/Volumes/Media/Comics/` (bigmedia) |
| Fixture set | 247 stratified one-per-series |
| Sampler seed | 0 |
| Cover quality | full |
| API budget | fast |
| Metron labeling | 47 newly labeled via cv_id cross-ref (matches 2026-05-14) |
| Wall time | ~5h overnight |

Reproduce per `2026-05-14-bigmedia-247.md` "Reproducing this run"
section.

## Headline numbers + comparison

|                            | 2026-05-14 baseline | 2026-05-17 (HEAD) | Delta  |
| -------------------------- | ------------------- | ----------------- | ------ |
| CV correct                 | 233 / 247           | **219 / 247**     | **-14** |
| CV accuracy (all labeled)  | 94.3%               | **89.4%**         | -4.9pp |
| CV auto-write band (0.85-0.95) | 97.6%           | **97.0%**         | -0.6pp |
| CV prompt zone (0.70-0.85) | n/a (not broken out) | 55% (24/44)      | —      |
| Metron correct             | 32 / 33             | **32 / 33**       | 0      |
| Metron accuracy            | 97.0%               | **97.0%**         | 0      |
| Metron auto-write band     | 100% (31/31)        | **100% (31/31)**  | 0      |

## Interpretation: production accuracy unchanged, prompt-zone surprised

**The production-relevant number — CV auto-write band — held at
97% (vs 97.6% baseline).** Production users running `--policy
normal` see only auto-write-band picks as tags; the matcher is
just as right in that band as it was on 2026-05-14.

**The overall accuracy regressed 4.9pp because the prompt zone
(0.70-0.85) accumulated more wrong-but-not-confident picks** — 24
of 44 (55%) are wrong, where the baseline didn't break this band
out separately but had far fewer total prompt-zone fixtures.

In production:
- Auto-write-band picks → tags written. **Same accuracy as before.**
- Prompt-zone picks → user sees a prompt and decides. The matcher's
  wrong picks here become wrong PROMPTS, not wrong TAGS — the user
  vetoes or accepts manually.
- Solo-viable band → 1/1 correct, unchanged.

**Net for users: no degradation under `--policy normal`. Under
`--policy eager` or `--unattended`, slightly more wrong tags would
land than on 2026-05-14.** That's the cost of the J/K rev 2 +
H/I revert combo on this fixture set.

## Misses break down into three patterns

26 CV misses vs 14 in the baseline. Same Pattern A and B from the
2026-05-14 note, plus a NEW pattern.

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

Same 6 cases as the baseline: Barry Ween 2.0, Hilda and the Stone
Forest, Who is Jake Ellis, Fallen Son, Captain America First
Vengeance, Hawkeye Freefall. Tiebreak picks lower vol_id;
sometimes the user tagged with the higher one.

### Pattern D (new) — "trade collection by Author" loses to canonical series volume

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

These are the *exact* fixtures that the Phase I revert
(`b33da25`) and Phase K rev 2 (`916a488`) were supposed to fix.
META-PLAN.md cites the Conan-by-Jim-Zub case specifically as the
canonical example, with hand-computed scores:

> Right (910095, year=2021):  md = 0.9125  (publisher/pages asymmetric)
> Wrong (690927, year=None):  md = 0.7875  (year asymmetric too)
> → 0.125 metadata margin on right's side.

But this run shows that case as a MISS with `md=0.83` on the
chosen (wrong) candidate and `gap=0.00` between top 2 — i.e., the
right answer is in the top set but tied or below the picked one.

**This is the most surprising finding of the run.** The
hand-calculated scores in the META-PLAN note don't match what the
matcher is actually producing. Possible reasons:

1. Phase K rev 2 doesn't behave the way META-PLAN described under
   FAST budget specifically (maybe the candidate pruning kicks in
   before signal-content-aware normalisation runs).
2. The candidate-set on this run differs from what META-PLAN
   analyzed (different volumes returned by CV search, different
   metadata fields populated).
3. Phase K rev 2's signal-asymmetric weights (s_year=0.3,
   s_publisher=0.5, s_pages=0.6) are right in isolation but get
   diluted in the renormalisation when more signals are tied.

Whichever it is, **the documented win on this case isn't
holding in practice on the real bigmedia data.** Worth a focused
investigation if the goal is to get back to the 94%+ overall
number.

## Cross-checks

- **Phase G (cover-diff 0.03 noise margin) is restored.** Fallen
  Son and Hawkeye Freefall both still miss (Pattern B), behaving
  the same as 2026-05-14. Confirms the revert worked.
- **Phase J (adaptive top-K for cover hashing) is in effect.**
  Can't easily verify from this run; would need a flagged log.
- **The 2 Pattern C "no-candidates" cases recur.** Step Aside Pops
  and Punisher Last Days. Same catalog gap as baseline.

## What this validates / doesn't

**Validates:**
- The H/I reverts didn't cause production-user regressions (auto-
  write band is unchanged at 97%).
- Metron path is healthy — 100% auto-write-band accuracy still.
- Phase G's cover-diff noise margin is correctly restored.

**Doesn't validate:**
- The META-PLAN claim that Phase K rev 2 fixes the trade-collection
  pattern. Empirically it does NOT on the bigmedia data — the same
  pattern surfaces as 11+ new misses in the prompt zone.
- The hoped-for recovery toward the pre-HI ~94.6% number. Overall
  number is at 89.4%, below baseline.

## Recommendation

**Ship-readiness:** safe to ship under `--policy normal` (which is
the default). Auto-write-band accuracy is unchanged. The 4.9pp
regression in overall accuracy is concentrated in the prompt zone,
which doesn't auto-tag.

**Investigation worth doing before ship if higher overall accuracy
matters:** dig into one of the 11+ trade-collection-by-Author
misses. Run a unit-test-style probe of `OnlineMatcher.rank()`
against the actual candidate set from the bigmedia run for, say,
"Conan the Barbarian by Jim Zub Land of the Lotus (2021)". Confirm
whether Phase K rev 2's signal-content-aware normalisation is
producing the META-PLAN's documented md=0.9125 vs md=0.7875 gap,
or something different. Cheap probe — no live API needed once we
have the candidate IDs from the existing outcomes JSON.

## Where to find the data

- Outcomes: `tests/calibration/fixtures-bigmedia.outcomes.json`
  (gitignored, per-developer).
- Full miss details: `uv run python -m tests.calibration.summarize
  --fixtures tests/calibration/fixtures-bigmedia.json --misses`.
- Per-fixture log: `tests/calibration/run.py`'s stdout was
  captured during this run.
