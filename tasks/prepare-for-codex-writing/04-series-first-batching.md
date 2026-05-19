# Series-First Batching — Design Doc

## Status

Plan §3.10 / build-order step 9. **Design doc only — implementation deferred.**
Greenlit in principle ("we'll do this too"). This doc captures the design so it
can be picked up when API rate limits become the visible bottleneck for
online-tagging batches.

## Problem

Today, `ComicboxOnlineLookup` walks one comic at a time. For each comic it
builds a `ComicProfile` from filename + on-archive metadata and asks each
enabled online source: "find me this issue." Even when fifty issues from the
same series go through one after another, each makes its own search call to
Metron or ComicVine.

The per-source rate budgets:

- **Metron** (mokkari): 20 req/min, 5 000 req/day.
- **ComicVine** (simyan): 1 req/sec, 200 req/hr.

Concretely: a 600-issue "tag every issue of Spider-Man" batch costs 600 searches
at ComicVine's 1 req/sec — ten minutes of wall time _before_ any per-issue
`get(id)` calls. At Metron's 20/min it's 30 minutes.

The matcher already returns Candidates with `volume_id` set (the series-level
container — Metron's `series.id`, ComicVine's `volume.id`). Two issues of the
same series share a `volume_id`. Step 6's prompt-dedup cache
(`comicbox.online_session._prompt_fingerprint`) already keys on the candidate
volume_ids — so the _user_ sees one prompt per series. The API cost is still N
searches per series.

The fix: collapse those N searches into 1.

## Approach

Add a pre-pass that groups the input paths by series fingerprint _before_ any
online searches happen. For each group:

1. **First-issue search.** Pick one representative comic (the one whose profile
   is most likely to match — highest filename signal strength, prefer one with
   `--id`, prefer one with year + issue#). Run the existing search → rank →
   resolve pipeline on it.
2. **Cache the verdict at series scope.** The chosen Candidate carries
   `volume_id`. Store `series_fingerprint → (source, volume_id)` in a
   session-level cache distinct from the prompt-dedup cache (step 6).
3. **Per-issue fast path.** Every other issue in the group queries the source's
   per-volume issue API directly:
    - Metron: `mokkari.session.issues_list(series_id=…, number=…)` or
      `series(id).issue_list()`
    - ComicVine:
      `simyan.session.issues_list({"filter": "volume:…,   issue_number:…"})`

    These calls cost the same rate-limit budget as a search but return fewer
    rows and zero ambiguity. More importantly, with the series fingerprint
    already resolved, **the matcher skips the prompt path entirely**: there is
    exactly one issue matching "volume X, issue#=5" in a healthy data source.

## What the matcher currently does that this changes

The existing flow (`comicbox/box/online_lookup.py:_search_path`):

```
profile = build_profile(comic)
candidates = source.search(profile)        # ← one round-trip per comic
resolution = matcher.resolve(candidates)
if resolution is PROMPT:
    prompt user                            # ← step 6 dedups by fingerprint
elif resolution is AUTO_WRITE:
    accept(candidate)
```

The proposed flow (series-first):

```
groups = group_paths_by_series_fingerprint(paths)
for series_fp, group in groups:
    if series_fp not in session.series_cache:
        # Cold path: search + prompt once per group
        rep = pick_representative(group)
        profile = build_profile(rep)
        candidates = source.search(profile)        # ← one round-trip per series
        resolution = matcher.resolve(candidates)
        if resolution is PROMPT:
            prompt user (cache by step-6 fingerprint)
        session.series_cache[series_fp] = (source, chosen_volume_id)

    source, volume_id = session.series_cache[series_fp]
    for comic in group:
        issue = parse_issue(comic)
        candidate = source.lookup_issue(volume_id=volume_id, number=issue)
        if candidate:
            accept(candidate)
```

Key invariant: **the prompt budget is per-series, not per-issue**. For
Spider-Man 1-100 the user sees at most one prompt; the matcher makes 1 search +
100 per-volume issue lookups instead of 100 searches.

## What we don't yet have

`OnlineSource.lookup_issue(volume_id, number)` does not exist today. We have
`OnlineSource.get(issue_id)` (which needs the issue_id already in hand) and
`OnlineSource.search(profile)` (the expensive fuzzy search). Step 9
implementation needs to add the volume-scoped issue lookup to each source:

- **Metron** — `mokkari` already exposes a series-list iterator:
  `session.series(id).issue_list()` or
  `issues_list({"series_id": …, "number": …})`. Wrap that.
- **ComicVine** —
  `simyan.session.issues_list({"filter": "volume:VOL,issue_number:N"})`. Direct
  field match.

Both providers serve this from their per-volume issue index; the queries are
cheap on their end (much cheaper than the unbounded "search by name + year +
publisher" path).

## API surface — what changes for callers

**Nothing.** Series-first batching is a matcher-internal optimization; the
`OnlineSession.tag` / `tag_many` contract stays the same. Codex keeps its
current integration:

```python
session = OnlineSession(sources=…, credentials=…)
for result in session.tag_many(paths):
    ...
```

The per-comic events are unchanged (`SearchStarted`, `SearchCompleted`,
`AutoWritten`, …) — the dedup case already silences `PromptQueued` across issues
of the same series, so the user-visible event stream already approximates the
"one prompt per series" UX. The internal-perf change just means many more
`SearchCompleted` events fire from the fast path (`source.lookup_issue`) instead
of the slow path (`source.search`).

One **new** event would be useful for Codex's UI:

```python
SeriesIdentified(path, source, volume_id, n_issues_in_group)
```

so the UI can render "Resolved series Spider-Man → ComicVine vol 12345; tagging
100 issues from this series." Trivial addition; lands with the implementation.

## Phases

1. **Pre-pass grouping**. Add a helper that builds series fingerprints from the
   path list before the per-comic loop. The fingerprint here is a _lighter_
   version of the step-6 prompt fingerprint because we don't have candidate
   volume_ids yet — series-name normalized + year + publisher, derived from
   filename and embedded metadata. Hash collisions cause re-prompts, not
   correctness bugs (false-positive groups fall through to per-issue searches).

2. **Per-source `lookup_issue` method**. Add to `OnlineSource` abstract base in
   `comicbox/formats/base/online/sources/base.py`. Implement for Metron +
   ComicVine. Returns at most one Candidate (the matching issue) or None.

3. **Session-level `series_cache`**. New attribute on `OnlineSession`, parallel
   to the existing `_prompt_cache`. Keyed by series fingerprint; value is
   `(source_name, volume_id, n_issues_seen)`. Codex would also get a
   `seed_series_resolution(fingerprint, source, volume_id)` for the
   "previously-resolved on a prior batch" case.

4. **Matcher refactor**. Add a `lookup_via_volume_id` path to
   `ComicboxOnlineLookup`. Engaged when the series fingerprint is in the cache;
   falls back to `_search_path` when it's not.

5. **End-to-end test**. Patched Metron source verifying that tagging Spider-Man
   #1 then #2 results in exactly one `search()` call + two `lookup_issue()`
   calls, and that step-6's prompt dedup still fires correctly on the cold-path
   prompt.

## Open questions

- **Cross-source resolution**: if the cold-path search returns candidates from
  multiple sources, do we cache per-source or unified? Probably per-source —
  Metron and CV have different `volume_id` namespaces. The session cache is
  keyed by `(source, series_fingerprint)`.

- **Falsy groups**: what if pre-pass grouping is wrong and two comics that look
  like the same series turn out to be different? Catch this at issue-lookup time
  — if `source.lookup_issue` returns None for an issue whose series we thought
  we'd resolved, fall back to a fresh `_search_path` for that comic. Mark the
  fingerprint as "ambiguous" so we don't waste budget retrying it.

- **Group ordering**: the representative we pick for the cold-path search
  affects whether the prompt-dedup cache will hit on later groups whose
  fingerprints land near it. Pick deterministically (sort by path) so re-runs of
  the same batch produce the same cache key sequence.

- **`--rematch`**: today `--rematch` skips the stored-id fast path to force a
  re-search per comic. Should it also bypass the series cache? Probably yes —
  `--rematch` is "I don't trust the prior verdict." Bypass both caches.

## Cost model

Worst case (every comic in its own series): same as today — N searches.

Best case (publisher import: 10 000 comics across ~50 series):

- 50 cold-path searches at ComicVine's 1 req/sec = 50 seconds.
- 10 000 `lookup_issue` calls at 1 req/sec = ~2.8 hours. (Still rate-limited,
  but mostly cheap.)

Today, the same workload costs 10 000 searches × 1 req/sec = 2.8 hours of search
alone, _plus_ the per-issue get() to retrieve chosen candidates → roughly 5.5
hours wall time. Series-first halves it.

For Metron the win is bigger: 50 cold + 10 000 lookup_issue calls vs. 10 000
search calls — both at 20 req/min, so 1.4× faster on search avoidance but the
lookup_issue path doesn't pay the unbounded-search penalty (mokkari's
series-scoped issue iterator is a different endpoint with its own — usually
higher — limit).

## When to ship this

Land when one of:

- Codex's online-tagging dashboard shows users routinely waiting hours on big
  batches and ComicVine 1 req/sec is the visible bottleneck.
- An external user reports "I tried to tag my 50 000-comic library and it timed
  out at the API limit."
- We add a fanout/parallelism mode that turns API rate limits from "wall-time
  bound" to "user-frustration bound."

Until then: the prompt-dedup cache (step 6) + defer mode (step 7) already handle
the user-attention bottleneck. The rate-limit bottleneck is real but bounded;
users can run a batch overnight.
