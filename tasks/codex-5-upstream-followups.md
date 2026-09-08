# Comicbox 5.0 — Upstream Follow-ups Found While Adopting It in Codex

**Audience:** an agent working in
[comicbox](https://github.com/ajslater/comicbox). This document is
self-contained: it does not assume you saw the codex conversation or PRs. It is
the return leg of `tasks/codex-v3-handoff.md`.

**Status:** items 1, 2 and 4 are done. Item 1 is
[PR #203](https://github.com/ajslater/comicbox/pull/203); items 2 and 4 are
[PR #204](https://github.com/ajslater/comicbox/pull/204), stacked on it. Items 3
and 5 need no comicbox change. Sections below record what shipped and what codex
has to change to match; the checklist at the end is codex's.

Two of the three fixes change comicbox's public surface, so codex's `comicbox-5`
branch does not build against them unchanged. Nothing here is urgent — none of
it is a regression — but all of it lands before 5.0.0 ships.

## Context

Codex was migrated to comicbox 5.0.0 (schema v3.0) over three commits on its
`comicbox-5` branch. The migration is straightforward and the v3 design holds up
well in practice. What follows is only the friction: places where codex had to
reach around an API, accept a lossy round trip, or duplicate something comicbox
already knows.

The codex side is on branch `comicbox-5`, pinned to `comicbox[pdf]~=5.0.0`.

---

## 1. `OnlineSession` could not be given settings (DONE, PR #203)

**Branch:** `online-session-config-hook`, commit `33a369a`.

`OnlineSession.__init__` read its base `ComicboxSettings` from `get_config()`
(now the `config` keyword at `comicbox/online_session.py:302` and the read it
skips at `:333-335`). Every other comicbox entry point lets a caller pass
settings in, but this one did not, so an embedder holding configured settings
had no way to hand them over.

That mattered to codex twice:

- **Cache directory.** Codex keeps comicbox's online sqlite caches under its own
  `/config` volume, because comicbox's platformdirs default is thrown away when
  a Docker container is recreated. It travelled as `COMICBOX_ONLINE_CACHE_DIR`,
  which 5.0 stops reading — correctly, since env vars now nest with `__`. Codex
  could have switched to `COMICBOX_ONLINE__CACHE__DIR`, but that puts the
  setting back on a name comicbox is free to rename again.
- **Effort.** `Effort` has no `OnlineSession` keyword, so an embedder wanting
  anything but the default has only the environment to reach it through.

The fix adds a `config` keyword. Passing it also skips the config-file and
environment read, which is pure waste when the caller's settings are already the
answer that read would find. Tests are in `tests/unit/test_online_session.py`;
`NEWS.md`'s 5.0.0 Features section has an entry.

**Action:** none for codex. `session_manager.py`'s
`config=COMICBOX_ONLINE_CONFIG` works as written.

---

## 2. The run estimator still models unbounded Comic Vine fan-out (DONE)

Right, and worse than reported: the estimate was keyed on an axis that moves
nothing. `MatchMode` branches only in the matcher, deciding how a verdict is
applied — no match mode changes a single Comic Vine request. The shipped table
`{eager 2, auto 3, careful 5}` had no recorded provenance and priced `careful`
above `eager`, which is backwards even for the one mode-dependent cost there is
(a declined match skips the two-call accept fetch).

So the mode axis is gone rather than joined by a second one. `Effort` is the
axis, and the numbers are now anchored to a measurement rather than asserted:

```python
requests_per_comic(source, effort="balanced") -> int
estimate_run(comics, sources, *, effort="balanced", merge_all_sources=False)
```

`mode` is no longer a parameter of either. `sources` moves up to second
positional. `effort` is keyword-only on `estimate_run` and takes an `Effort` or
its value; an unrecognized one is priced as `balanced`.

Comic Vine's cost is now built from three constants instead of a mode table:
`COMICVINE_DISCOVERY_REQUESTS` (2), `COMICVINE_ISSUE_LIST_REQUESTS_BY_EFFORT`
(`{minimal 1, balanced 3, thorough 4}`) and `COMICVINE_FETCH_REQUESTS` (2).
`COMICVINE_REQUESTS_BY_MODE` and `COMICVINE_BUSIEST_POOL_REQUESTS_BY_MODE` are
removed. Only the middle table paces the run: those calls all stack in one
resource pool while everything else sits alone in its own.

| Effort   | Requests/comic | Seconds/comic |
| -------- | -------------- | ------------- |
| minimal  | 5              | 20            |
| balanced | 7              | 60            |
| thorough | 8              | 80            |

**The default projection triples**, from 20 s to 60 s per comic, so codex's
countdown numbers jump. That is the estimate becoming honest about a cold
search, not the run getting slower. Provenance is in
`tasks/online-tagging/calibration-notes/2026-09-08-estimator-cold-search-cost.md`.

Two things that estimate cannot see, both worth a word in codex's UI copy if the
numbers ever look wrong:

- **A batch beats the projection.** Every comic is priced as a cold search, but
  a run batches by series: one search answers for a whole series and the issues
  after it cost about one call each. This is the real reason a library finishes
  early, and a series-aware estimate is the obvious next lever if the gap annoys
  anyone.
- **Per-source effort.** `resolve_effort(settings.online, "comicvine")` is the
  value to pass. A per-source override beats the global one, and a global
  `effort` read straight off the settings misses it.

`Effort` is now exported from `comicbox.online_session` alongside `MatchMode`,
so the estimator and the enum it takes come off the same facade.

---

## 3. The credit primary flag reaches no format codex writes

`credits.<person>.roles.<role>.primary` persists to ComicBookInfo only
(`comicbox/formats/comicbox/schema/__init__.py:150` marks it "CBI ONLY"; the
only writer is `comicbox/formats/comic_book_info/transform/credits.py:145`).
MetronInfo v1.1's schema has `primary` attributes on `URL` and `ID` but none on
a credit, and ComicInfo has no notion of one.

Codex writes ComicInfo and MetronInfo. It reads the flag, stores it on the
person-and-role pairing, and shows primaries first in the metadata panel — but
it deliberately ships **no editor control**, because a control whose value could
never be written back would be a lie. The flag survives only as long as nothing
rewrites the file.

**Not obviously actionable** — it is a limitation of the format specs, not of
comicbox. Worth knowing that the field is, in practice, read-only for the two
formats most tools use. If MetronInfo ever gains the attribute, codex's field
support map derives itself from the transforms and the control would light up on
its own.

---

## 4. Metron publishes no URL for several id types (DONE)

Both observations were symptoms of comicbox filing ids by position when the
position said nothing. Both are fixed; the workarounds can come out.

**Alternative names now state their type.** An id on a series
`alternative_names` entry is stored as `{"key": "3333", "id_type": "series"}`
and `get_url_from_identifier` builds `https://metron.cloud/series/3333` from it
with no help. The rule that made it bare was right in general and unchanged: a
type is recorded only when it differs from the one its position implies. What
was wrong was treating an alternative name as implying `series` — a name is not
the thing it names, so it implies nothing, and the id states its type the way a
top-level non-issue id does. Codex can drop its `id_type: series` injection.

Note the old behavior was worse than the empty string codex saw: a consumer that
applied the documented default got `metron.cloud/issue/3333`, a live link to the
wrong page.

**Reprint ids are issue ids.** A MetronInfo `<Reprint id>` is the reprinted
issue's Metron id — mokkari's `Reprint.id` is the same thing, and the online
transform already filed it as `issue`. The MetronInfo transform called it
`reprint`, a type no database publishes a page for, which is why it was linkless
by construction. It now files `issue`, so `get_url_from_identifier` returns
`https://metron.cloud/issue/4444`.

The stored shape does not change (`{"key": "4444"}`; the type is implied and so
not recorded), which means **codex sees no data change here and must change its
bridge anyway**: whatever maps a reprint identifier to a type for the url column
has to say `issue`, not `reprint`, or use `get_url_from_identifier`, whose
default is `issue`.

Neither change touches written XML. The MetronInfo writer reads only the key.

`reprint` remains in the id-type vocabulary for hand-tagged keys that name it,
and still builds no url. The online-API path needs nothing: it already files
reprint ids as issues, and it attaches no identifiers to alternative names at
all, because mokkari and Comic Vine both return those as bare strings. If
mokkari ever returns alternative-name ids, `build_identifier` will need the same
treatment.

---

## 5. `MergeMode` note — no action, just confirmation

The `MergeMode` docstring (`comicbox/config/settings.py:81`) is the clearest
statement of the tradeoff and it is accurate: `update` replaces top-level keys
wholesale and drops siblings, while `replace` recurses into dicts and replaces
only the leaves.

Codex writes with `update`, so a patch that carried only
`series.alternative_names` would drop the series' `name`. Codex compensates by
sending the whole series object it knows about. Switching codex to `replace` for
these writes would be the cleaner fix and is a codex-side decision; recorded
here only so the next person does not read the compensation as a comicbox bug.

---

## Things that worked well, for what it's worth

- **The new skip warning earned its keep immediately.** Two codex test fixtures
  had been malformed for as long as they had existed — a null team value that
  voided the entire `teams` field, and a credit role's identifier keyed by `key`
  instead of by its source. 4.8.7 dropped both as silently as an absent tag. 5.0
  named them, and both were repaired.
- **Deriving links from keys rather than storing them** removed a whole class of
  disagreement. Codex kept its url column and now fills it through
  `get_identifier_url`, which also fixed a latent mismatch: the column stores
  `""` for a linkless type, and the aggregate now carries `""` too rather than
  `None`.
- **`id_type` on a top-level identifier** let codex file a stated series or
  volume id correctly instead of assuming every comic-level id was an issue id.
- **Splitting manga from reading direction** was clean to adopt. The two facts
  land in two columns and two editor fields, and the format support map derives
  which format can store which without anything hand-written.

## What codex should change

- [ ] `estimate_run(comics, mode, sources, ...)` ->
      `estimate_run(comics, sources, *, effort=...)` at
      `codex/librarian/onlinetag/estimate.py` and `codex/choices/onlinetag.py`.
      Same for `requests_per_comic(source, mode)` ->
      `requests_per_comic(source, effort)`.
- [ ] Pass `resolve_effort(settings.online, "comicvine")`, not the global
      `tuning.effort`, so a per-source override reaches the estimate.
- [ ] Import `Effort` from `comicbox.online_session` if you want it off the same
      facade as `estimate_run`.
- [ ] Drop any import of `COMICVINE_REQUESTS_BY_MODE` or
      `COMICVINE_BUSIEST_POOL_REQUESTS_BY_MODE`; they are gone.
- [ ] Expect the default projection to triple (20 s -> 60 s per comic) and
      decide whether the launcher's copy needs to say a batch beats it.
- [ ] Drop the `id_type: series` injection for series `alternative_names`.
- [ ] Map a reprint identifier to `issue` (or call `get_url_from_identifier`) so
      reprint links stop coming back empty.

## Where the codex work lives

| Branch       | Commit    | What                                                                |
| ------------ | --------- | ------------------------------------------------------------------- |
| `comicbox-5` | `1f1c593` | Moved and renamed APIs, derived identifier urls, v3 fixtures        |
| `comicbox-5` | `07188d9` | Identifier type vocabulary bridge, reprint name fallback            |
| `comicbox-5` | `0db3cf0` | manga, manga_volume, urls, Credit.primary, Reprint.alternative_name |

Remaining codex phases: online extras (effort setting, Comic Vine rate-limit
display), the one-time re-read migration, and docs.
