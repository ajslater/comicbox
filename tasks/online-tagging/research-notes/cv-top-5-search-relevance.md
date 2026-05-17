# CV "right answer not in top-5" search-relevance — research note

The 2026-05-14 bigmedia calibration surfaced 7 fixtures where the
matcher picked a different CV volume than the user's ground-truth
tag, all driven by **the right answer never reaching the matcher**:
under the FAST budget (`max_volumes=5`), CV's full-text `/search`
endpoint ranked the wrong volume in the top 5, and the matcher
faithfully scored what it was given.

Two prior code attempts to fix this (Phase H, Phase H rev 2) were
both reverted because they took the wrong angle. This note records
what's known, what failed, and what the remaining unexplored angle
looks like.

## The 7 cases (from 2026-05-14-bigmedia-247.md, Pattern A)

| Comic (year)                 | Got (year)       | Year diff |
| ---------------------------- | ---------------- | --------- |
| Akira (2000)                 | Akira (1998)     | 2         |
| Ghost in the Shell (2009)    | GitS (1995)      | 14        |
| Savage Sword of Conan (2024) | SSoC (1974)      | 50        |
| Conan the Barbarian (2025)   | CtB (1973)       | 52        |
| Storm (2024)                 | Storm (2014)     | 10        |
| Powers (2015)                | Powers (2000)    | 15        |
| X-Men #1 Facsimile (2019)    | The X-Men (1963) | 56        |

The common shape: a reissue, facsimile edition, or relaunch sharing
a name with an older / better-known volume. CV's relevance ranking
surfaces the older volume in the top 5; the new one is at rank
6-20+ or worse.

**This is not a scoring problem.** The matcher can't score what it
never sees. Fixing it means changing what we ask CV for, not how we
score the answer.

## What's been tried (and reverted)

### Phase H — broaden the fuzzy search on weak top quick-score

Commit `f772d75`, reverted by `62a5725`.

When the initial CV `/search` top candidate scored < 0.85 under
FAST, re-issue with `max_results=20` and fetch new volumes only
(vol_id dedup). Hypothesis: more candidates → right answer makes
it in.

**Why it failed:** broader candidate sets caused prompt-zone
regressions on the slimlib stress data (more close-but-wrong
candidates clustering near the auto-write threshold). The 7
Pattern-A cases mostly DID recover, but the regressions on
unrelated fixtures cost more than the wins.

### Phase H rev 2 — broaden + source-aware discovery_pass tiebreak

Commit `35ff22f`, reverted by `b407815`.

Same broaden, plus a discovery_pass tiebreak to prefer candidates
that came back in the BROADENED batch (the rationale being "they're
less canonical, so probably the reissue").

**Why it failed:** 0 net flips on bigmedia. The discovery_pass
heuristic didn't actually identify reissues in practice.

## What hasn't been tried: query-side narrowing

Both Phase H attempts broadened the result set (asked CV for MORE
candidates from the same fuzzy search). The unexplored angle is the
opposite: NARROW the query.

CV's `/search` endpoint is fuzzy-relevance and offers no filtering.
But CV's `/volumes` endpoint (already used by `simyan.list_volumes`)
supports server-side filters including `name`, `start_year`,
`publisher`, `count_of_issues`. We're not currently using it for
volume discovery.

### Proposal: two-step volume search

```python
# Pseudocode at comicbox/online/sources/comicvine.py:231 area
def _volume_search_with_retry(self, session, query, max_results,
                              start_year=None):
    if start_year is not None:
        # Step 1: narrow filter by name + year window.
        volumes = session.list_volumes(
            params={"filter": f"name:{query},start_year:{start_year}"},
            max_results=max_results,
        )
        if volumes:
            return volumes
    # Step 2: fall back to today's fuzzy search.
    return session.search(
        resource=ComicvineResource.VOLUME,
        query=query,
        max_results=max_results,
    )
```

For the 7 Pattern-A cases:

- "Akira (2000)" with year=2000 → `filter=name:Akira,start_year:2000`
  → returns the 2000 reissue volume directly → **likely fixed**
- "Conan the Barbarian (2025)" with year=2025 → similar → **likely fixed**
- "Storm (2024)" with year=2024 → similar → **likely fixed**
- "Powers (2015)" with year=2015 → similar → **likely fixed**
- "Savage Sword of Conan (2024)" with year=2024 → similar → **likely fixed**

For tricky cases:

- "X-Men #1 Facsimile (2019)" with year=2019 — CV stores facsimile
  editions under names like "True Believers: X-Men" or similar
  marketing names; the `filter=name:X-Men` icontains might miss
  the facsimile. Falls back to fuzzy. **Likely still misses**, but
  no worse than today.
- "Ghost in the Shell (2009)" — was the 2009 release a Dark Horse
  reprint or its own volume in CV? If CV catalogued it without
  exact-match name (e.g. "Ghost in the Shell 1.5" or
  "Ghost in the Shell Vol. 2"), filter misses → fuzzy fallback.

### Why this avoids the Phase H regression

Phase H broadened the FUZZY search → more close-but-wrong candidates
across all fixtures → prompt-zone clutter. The new approach only
narrows on the year axis, which doesn't change candidate
COMPOSITION quality, just COVERAGE. For fixtures where the narrow
search hits, we get the right answer with FEWER total candidates
(less noise, not more). For fixtures where it doesn't, we fall back
to today's behaviour.

### Cost

CV's hourly cap is 200. Each fixture today does ~1 search call.
The new approach:

- **Hit case** (narrow search returns ≥1): 1 list_volumes call.
- **Miss case** (narrow search returns 0): 1 list_volumes call +
  1 search call = 2 calls.

Worst case 2x search-call cost. But search calls are NOT the bulk
of CV usage — per-volume `list_issues` calls dominate. So actual
total API cost grows by maybe 10-15% in the miss case, less in
the hit case.

### Caveats and risks

1. **`name:foo` is icontains.** "Storm" filter would return any
   volume with "storm" in its name (Storm Lord, Storm Watch, etc.).
   That's noise but the year filter narrows it heavily.

2. **`start_year` is the VOLUME's start year, not the issue's
   cover_date year.** A volume that started in 2024 has all its
   issues filed under start_year=2024 regardless of when each issue
   shipped. So "Conan the Barbarian (2025) #001" might be in a
   volume that started in 2024 — query for start_year=2025 returns
   0, fall back to fuzzy. Mitigation: try `start_year:N-1` window
   too if exact-year returns 0. Three API calls worst case.

3. **profile.year is the cover-date year, derived from filename or
   metadata.** Sometimes wrong (filename mis-parse, cover-date
   drift, omnibus collections etc.). When wrong, narrow search
   misses, fallback to fuzzy. Same as today's behaviour for those
   fixtures.

4. **The filter syntax is `field:value,field2:value2` joined by
   commas.** Already used at comicvine.py:269 for `list_issues`
   filters; same syntax works for `list_volumes`.

## Empirical attempt 2026-05-17 — REVERTED

Implemented the narrow-then-fuzzy proposal above (commit `7390393`,
reverted by `ea7d776`). Bigmedia re-run results:

|              | Pre-fix | Post-fix | Delta |
| ------------ | ------- | -------- | ----- |
| CV accuracy  | 89.4%   | **85.6%** | **-3.8pp** |
| CV correct   | 219/247 | 208/247  | -11   |
| Improvements | —       | **2**    | Akira (2000), Ghost in the Shell (2009) |
| Regressions  | —       | **14**   | 300 (1999), Weapon X (1994), The Cimmerian (2020), etc. |

**The fix worked for Pattern A but introduced a larger class of
regressions.** 2 wins vs 14 losses.

### Root cause of the regressions

The "fall back to fuzzy when narrow returns 0" rule was too coarse.
**When narrow returns 1+ wrong volumes, fuzzy never fires** — the
matcher is stuck with whatever name+year happened to match in CV's
catalog, even if it's not the user's intended volume.

Concrete examples:

- **300 (1999)**: user's tag = volume 22632 (Frank Miller's "300",
  CV start_year likely 1998). Filename year = 1999 (TPB year).
  Narrow query `name:300,start_year:1999` returned volume 6811 (a
  different "300"-named series that actually started in 1999).
  Fuzzy WAS finding 22632 correctly. Lost it.
- **Weapon X (1994)**: user's tag = volume 35703. Narrow query
  `name:Weapon X,start_year:1994` returned volume 5564 instead.
  Fuzzy had 35703 in candidates. Lost it.
- **The Cimmerian (2020)**: user's tag = volume 132702. Narrow
  returned volume 127841 instead. Fuzzy had 132702. Lost it.

**The premise was wrong.** `profile.year` (from filename or
cover_date) doesn't reliably correspond to the user's tagged
volume's `start_year` in CV. User filenames mix conventions:
sometimes "(YYYY)" is the original-issue year, sometimes the TPB
year, sometimes the volume's start year. CV's `start_year` is one
specific thing (when the volume began publishing). They don't
always agree.

### What WOULD work (untried)

The fix would be to NOT replace fuzzy with narrow, but rather to
UNION their results. Run BOTH `list_volumes(name+start_year)` and
`session.search(VOLUME, query)`, dedup by volume_id, let the
matcher score the combined set. This way Pattern A cases pick up
the year-anchored volume AND keep the fuzzy canonical volumes.

Cost: every CV search now makes 2 API calls instead of 1 (about
+50% on CV's binding hourly cap). For the bigmedia run that's
manageable; for users with very large libraries it's a more
visible cost.

But there's a deeper concern with the union approach: under FAST
budget (max_volumes=5), combining two top-5 sets means we either
- accept 10 candidates (doubles per-volume `list_issues` cost), OR
- truncate to 5 of the combined 10 by some heuristic — and the
  heuristic determines which Pattern-A wins survive.

Both options have real tradeoffs that need calibration data.

### Recommendation for future work

Don't re-attempt this fix without:

1. **Acceptance that profile.year ≠ user's tag's start_year for
   many fixtures.** This is a CV catalog convention reality, not a
   filename-parsing fix.
2. **A combine-not-replace strategy.** Narrow as supplement to
   fuzzy, not as replacement. Calibrate the combined-set size and
   ranking under FAST budget.
3. **Empirical validation BEFORE shipping.** This commit looked
   right by unit tests; it was wrong by bigmedia data. Bigmedia
   validation is the bar for any CV search-relevance change.

The 7+11 Pattern A misses remain unfixed. They're in the prompt
zone, so production users see them as PROMPTs, not wrong tags.
That's acceptable for now per the 2026-05-17 bigmedia ship-readiness
finding.

## What this note is NOT

Not a design doc, not a plan. It's a research record of the
problem shape and the un-tried direction so future work doesn't
re-attempt Phase H's broadening approach.

## Suggested validation

Before shipping any fix:

1. **Probe CV manually** for the 7 cases. Run `list_volumes` with
   the narrow filter for each. Confirm the right volume comes back.
   ~7 manual API calls, no code change required to gather this data.
2. **Slimlib stress test** for prompt-zone clutter. Phase H's
   regression was on slimlib's prompt-zone cases. The new
   narrow-then-fuzzy approach shouldn't regress prompt-zone
   behaviour (it's strictly additive: hit case adds answers,
   miss case is identical), but worth a calibration pass to confirm.
3. **Bigmedia A/B.** Compare bigmedia accuracy with and without the
   change. Pattern-A cases should flip from misses to hits without
   affecting Patterns B or C.

## Pattern B and C (not addressed by this approach)

For completeness:

- **Pattern B** (6 cases): CV catalog duplicates. Same series,
  same year, different volume_ids. Matcher's tiebreak prefers
  lower vol_id. Not a search-relevance issue — separate problem.
- **Pattern C** (2 cases): genuinely no CV match. Search relevance
  can't help; these comics aren't in CV's catalog under any name
  the matcher would try.

## Cross-reference: Metron

Metron has the analogous gap (`series_list` is name-based, no
year filter). `_series_list_with_retry` at metron.py wraps the
single name-search call. Whether Metron sees the same Pattern A is
unknown — the bigmedia run had 97% Metron accuracy on its 47
labeled cases, only 1 miss (within-series wrong-issue). No
evidence of cross-volume Pattern A on Metron in current data.

Mokkari does support `params={"year": N}` on `series_list` though
(undocumented but mokkari/session.py allows arbitrary params). If
Pattern A ever shows up on Metron, the same narrow-then-fuzzy
approach would apply.
