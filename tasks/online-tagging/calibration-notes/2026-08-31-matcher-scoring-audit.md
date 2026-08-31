# 2026-08-31 — matcher scoring audit (desk audit, no new calibration run)

A read of `comicbox/formats/base/online/matcher.py` and the threshold
configuration around it, checked against the 2026-05-17 bigmedia outcomes still
on disk (`tests/calibration/fixtures-bigmedia.outcomes.json`, gitignored and
per-developer). No API calls were made and **no weights were retuned** — the
scoring constants (`W_SERIES` … `W_COVER`, `_COVER_DIFF_NOISE_MARGIN`,
`_TIED_METADATA_BLEND_MARGIN`) are untouched. Two behavioral fixes landed, both
narrow and both provable without a live run; everything that would need one is
written up under "What a calibration run should settle" below.

`tasks/online-tagging/` was removed from the tree in `d38eadd` ("remove old
tasks") and never reached `develop`. The historical notes cited here are
readable at `git show d38eadd^:tasks/online-tagging/calibration-notes/<file>`.
This file re-establishes the directory.

## Phase archaeology

The matcher's comments name phases with no surviving index. What each one was,
and whether the code it justifies still exists:

| Phase | What it did                                                     | Status today                                                                            |
| ----- | --------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| B     | api-budget matrix runs (`fast` vs `balanced`)                   | Superseded by `Effort`                                                                  |
| D     | Series-name pre-filter before scoring                           | Live (`series_filter.py`)                                                               |
| E     | Solo-viable auto-write floor                                    | Live. Floor shipped at 0.95 = the auto bar from day one (2026-05-12 note)               |
| G     | Cover-diff noise margin tightened 0.05 → 0.03                   | Live (`_COVER_DIFF_NOISE_MARGIN`)                                                       |
| H     | CV search broadens when the initial top scores weakly           | **Reverted** — `62a5725` (rev 1: 7 wins, 14 regressions), `b407815` (rev 2)             |
| I     | Quality-relative cover-diff threshold                           | **Reverted** — `b33da25` (silently cost CV ~13 cases, 94.6% → 89.9%)                    |
| J     | Adaptive cover-hash top-K (5 → count/2, capped 15)              | Live, but its motivation (H's wide candidate sets) is gone and it flipped zero outcomes |
| K     | `metadata_score` renormalises over contributing signals (rev 2) | Live                                                                                    |

Three comment blocks were still arguing from the reverted work; see "Stale
prose" below.

## Finding 1 — the solo floor had come loose from the auto bar

`DEFAULT_SOLO_THRESHOLD` was `0.85` until #179 raised it to
`DEFAULT_AUTO_THRESHOLD`. **That 0.85 was drift, not calibration**: the
2026-05-12 slimlib note introduces Phase E with "a new
`solo_confidence_threshold` (default 0.95 = same as the global confidence
threshold)", and the value only ever disagreed because
`OnlineTuningSettings.auto_threshold` had itself drifted to 0.85 and the solo
constant mirrored it by hand.

#179 fixed the value. The mirror itself survived: `resolve_solo_threshold`
returned a module constant while `resolve_auto_threshold` resolved per-source →
global → CLI → env. So the two agreed only at defaults:

- `auto_threshold: 0.99` (globally, per source, `--auto-threshold`, or
  `COMICBOX_ONLINE_AUTO_THRESHOLD`) left a lone 0.96-scoring candidate
  auto-writing through a 0.95 back door **no setting could close**.
- Lowering the bar left the floor stricter than the bar it is defined to mirror.

`resolve_solo_threshold` now falls back to `resolve_auto_threshold` for the same
source. Identical behavior at defaults (0.95 == 0.95); the constant is gone, so
there is no second declaration left to drift.

### The carve-out is subsumed at the default floor

Worth writing down, because it reads like a bug and isn't: with the floor equal
to the bar, Phase E's carve-out can never widen `AUTO`. `solo_viable` means
every other candidate is below `min_confidence` (0.50), so a top that clears a
bar ≥ 0.50 is also more than `disambiguation_margin` (0.10) clear of the
runner-up — i.e. already `unambig`. **`AUTO` therefore behaves exactly like
`CAREFUL` out of the box**, and the carve-out only does work once a user lowers
`solo_threshold` for a source. `test_auto_matches_careful_at_default_settings`
pins it.

## Finding 2 — hashed and un-hashed candidates are judged on different scales

`final_score` gives an un-hashed candidate its raw metadata score and a hashed
one `0.80*md + 0.20*cover`, and `_resolve_policy` compares both against one
`auto_threshold`. Measuring a cover therefore doesn't just rank a candidate — it
moves the bar that candidate has to clear:

    a hashed candidate holds bar T only while  cover >= (T - 0.80*md) / 0.20

At the shipped T = 0.95:

| md     | cover needed to hold 0.95 |
| ------ | ------------------------- |
| 1.0000 | 0.75                      |
| 0.9800 | 0.83                      |
| 0.9625 | 0.90                      |
| 0.9500 | 0.95                      |
| 0.9375 | 1.00                      |
| 0.9125 | unreachable (1.10)        |

Its un-hashed sibling — a thumbnail-quality local cover, a PDF with no readable
cover page, a candidate with no `cover_url`, a fetch failure, or simply a rank
past the hashing top-K — keeps its md and clears the bar unmeasured.

Measured against the 2026-05-17 bigmedia outcomes (494 records, 310 with hashing
fired, 548 candidate cover scores):

- **48% of measured cover scores are below 0.75** — the break-even a _flawless_
  md = 1.0 candidate needs just to stay where it already was.
- The blend **lowered** the top candidate's score in 114 of 306 hashed fixtures
  (raised 191, unchanged 1).
- Counterfactually, had the bar been 0.90, 45 top candidates would have been
  pushed below a bar their metadata alone cleared — **41 of them the correct
  match**. At 0.85: 48 demoted, 24 correct.
- At the real 0.95 bar the count is 0, for an uncomfortable reason: nothing in
  this corpus reaches 0.95 either way (below).

### Nobody reaches the bar

| Source    | Outcomes with candidates | Max md | Max blended score | ≥ 0.95 |
| --------- | ------------------------ | ------ | ----------------- | ------ |
| ComicVine | 245                      | 0.9125 | 0.930             | 0      |
| Metron    | 65                       | 0.8937 | 0.915             | 0      |

CV's search results (`BasicIssue`) carry no publisher and no page count, so
Phase K's asymmetric weak priors cap md at 0.9125; blending a perfect cover onto
that reaches 0.930. **On this library the default policy prompts on every
fixture and auto-writes nothing.** That is a defensible safety posture, but it
is not what the docs describe, and it means the auto-write band has never been
measured on real data — the notes that report "auto-write band 97.6% correct"
are reporting the 0.85-0.95 band, which the shipped default sends to a prompt.
The harness's band labels said "auto-write" for that band; they now derive from
`DEFAULT_AUTO_THRESHOLD` (see `tests/calibration/run.py`).

Fixing the asymmetry is a retune and is **not** done here. The candidate
approaches, for a run to arbitrate:

1. Renormalise the un-hashed side (score it out of `_METADATA_WEIGHT_SUM` too),
   so hashing changes a candidate's rank without changing its bar.
2. Hash every member of a tie group rather than a rank prefix, so comparisons
   are always like-for-like.
3. Separate bars for hashed and un-hashed candidates.
4. Leave the blend alone and lower the default bar to something CV's md ceiling
   can actually reach.

Each moves auto-write behavior on users' files; none should ship on reasoning
alone.

## Finding 3 — "cover hash not computed" is not "no cover available"

`_cover_diff_is_noise` treated any missing `cover_score` as noise, which lets
`_apply_tied_metadata_tiebreak` collapse the pair and hand the win to the lower
`volume_id`. Two very different situations were reaching that branch:

- **No cover signal to be had** — nothing was hashed, or the unscored candidate
  _was_ hashed and had no usable cover (no `cover_url`, fetch failure,
  undecodable image). Cover genuinely isn't helping; volume id should decide, as
  before.
- **Not computed** — the unscored candidate sits outside `_top_k_for_hashing`,
  so nobody looked at its cover. Treating that silence as "the covers are alike"
  lets an unexamined record beat one whose cover we _did_ measure against the
  local copy, on volume id alone.

`Candidate.cover_hash_attempted` now records which happened, and only the first
case counts as noise. Blast radius, deliberately small: it takes ≥ 6 candidates
(K ≥ 5), an _exact_ metadata-score tie straddling the K boundary, and blended
scores within `_TIED_METADATA_BLEND_MARGIN` (0.02) for the branch to be reached
at all. Only 16 of 494 outcomes in the corpus even had ≥ 6 candidates, and the
harness records just the top 3, so **the corpus can neither confirm nor refute
this case** — the change rests on the code path, not on measurement. The two
mixed hashed/un-hashed adjacent ties the data _does_ show (Akira 2000 #001,
Ghost in the Shell 2009 #001) are the attempted-but-coverless case, whose
behavior is unchanged.

## Finding 4 — stale prose

- `_apply_tied_metadata_tiebreak` documented the cover-diff guard as `<=0.05`;
  Phase G tightened the constant to 0.03 in May.
- `_top_k_for_hashing` and `_apply_cover_hashing` justified adaptive K by Phase
  H's broaden retry, reverted in `62a5725` / `b407815`. Phase J also flipped
  zero outcomes on the corpus that motivated it; it stays as a cost-bounded
  generalization of K = 5, and now says so.
- `settings.py` described the solo floor as equalling the auto-write threshold
  directly above a constant that hardcoded it (fixed by #179; the coupling
  itself is Finding 1).
- The calibration report labelled 0.85-0.95 the "auto-write" band and 0.95-1.00
  "very high". Labels now come from `DEFAULT_AUTO_THRESHOLD`.

## What a calibration run should settle

1. **Does anything reach 0.95?** Re-run bigmedia and read the top band. If it is
   still empty, the default bar and the md ceiling are incompatible and one of
   them has to move (Finding 2, option 4).
2. **The blend, options 1-3 of Finding 2.** Run each against the same fixture
   set; the metric that matters is per-band correctness at ≥ 0.95, not overall
   accuracy — prompt-zone churn is not user-visible harm.
3. **Whether the K-boundary tie ever fires in the wild.** Raise the harness's
   recorded-candidate cap above 3 and log `cover_hash_attempted`; the case is
   currently invisible.
4. **Per-source bars.** Metron's md ceiling (0.8937) sits below CV's (0.9125) on
   the same library; one global threshold is doing two different jobs.

## Reproducing the numbers

Against a finished outcomes file (paths are per-developer; the file is
gitignored):

```python
import json

WMD, WCOV = 0.80, 0.20
data = json.load(open("tests/calibration/fixtures-bigmedia.outcomes.json"))
hashed = [
    (o, c) for o in data for c in o["top_candidates"] if c["cover_score"] is not None
]
covers = [c["cover_score"] for _, c in hashed]
print(len(covers), sum(c < 0.75 for c in covers) / len(covers))
tops = [o["top_candidates"][0] for o in data if o["top_candidates"]]
print(max(c["metadata_score"] for c in tops), max(c["score"] for c in tops))
```
