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
