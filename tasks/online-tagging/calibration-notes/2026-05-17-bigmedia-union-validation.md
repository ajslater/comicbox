# 2026-05-17 — bigmedia validation of CV union narrow+fuzzy

Empirical validation of commit `2381c0e` (CV union narrow+fuzzy
volume search). Same fixture set as the 2026-05-17-bigmedia-247-
postrevert.md run; only `_discover_volumes` changed.

## Result

| Metric              | Pre-union | Union  | Delta  |
| ------------------- | --------- | ------ | ------ |
| CV correct          | 219 / 247 | 221 / 247 | **+2** |
| CV accuracy         | 89.4%     | **90.2%** | **+0.8pp** |
| CV auto-write band  | 194 / 200 (97%) | 196 / 202 (97%) | +2 correct, +2 fixtures landing in band |
| CV prompt zone      | 24 / 44 (55%) | 24 / 42 (57%) | 0 correct, -2 fixtures (now decided) |
| Metron              | 32 / 33 (97%) | 32 / 33 (97%) | unchanged |

## Per-fixture diff

| Improved (2) | Regressed (0) |
| --- | --- |
| Akira (2000) #001 | _none_ |
| The Ghost in the Shell (2009) #001 | _none_ |

Both wins are classic Pattern A reissues — year-anchored volumes
that CV's fuzzy `/search` buried below older canonical runs. With
union, both the canonical fuzzy hit AND the year-matching narrow
hit are scored; the matcher correctly prefers the year-matching
one (high year-signal score).

**Zero regressions confirms the union design.** Yesterday's
narrow-then-fuzzy attempt regressed -3.8pp because narrow's wrong
hits prevented fuzzy from running, displacing previously-correct
candidates. With union, fuzzy always runs; narrow's contribution
is purely additive — the worst it can do is add useless candidates
the matcher scores lower.

## What didn't change

The 11 trade-collection-by-Author misses (Conan by Jim Zub, Black
Widow by Kelly Thompson, Wolverine by Claremont, etc.) did NOT
recover. Most likely cause: their volumes' `start_year` in CV's
catalog doesn't match the user's filename year exactly (the same
profile.year ≠ volume.start_year mismatch that broke the
narrow-then-fuzzy attempt — but here it just prevents a win
instead of causing a regression).

The 5 other original Pattern A cases (Conan 2025, Storm 2024,
SSoC 2024, Powers 2015, X-Men Facsimile 2019) also didn't
recover — same suspected cause.

To address those would require either:
- A year-tolerance window in the narrow filter (`start_year:Y-1` /
  `Y+1` fallback if `start_year:Y` returns 0)
- A different anchor (publisher? count_of_issues range?)
- Acceptance that they're catalog convention issues without a
  filename-derived fix

Out of scope for this commit.

## What this validates

- The union strategy is **safe to ship**: +0.8pp accuracy, 0
  regressions.
- Auto-write band picks up 2 fixtures (Akira, GitS) that previously
  landed in prompt zone. Production users running `--policy normal`
  now get auto-tags for these.
- The "fuzzy as floor" guarantee held: every fixture that was
  correct under fuzzy-only is still correct under union.

## Per-source API cost

Bigmedia run wall time: ~3-4 hours (CV cache warm from yesterday;
only narrow `list_volumes` calls + narrow-only volumes were fresh).

For cold-cache production runs, expect ~+1 CV API call per fixture
(the narrow `list_volumes`). Hit rate is small (2 of 247 fixtures
saw narrow add useful results), so the cost-to-value ratio is
poor at this scale. Better-targeted libraries (more reissue /
trade-collection content) would see better ROI.

## Recommendation

**Ship as-is.** Small win, zero regressions, clean code path.

The remaining ~16 Pattern A misses need a different approach (year
tolerance, alternative anchors) not just more narrowing. Future
work; not blocking on this commit.
