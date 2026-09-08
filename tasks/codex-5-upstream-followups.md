# Comicbox 5.0 — Upstream Follow-ups Found While Adopting It in Codex

**Audience:** an agent working in [comicbox](https://github.com/ajslater/comicbox).
This document is self-contained: it does not assume you saw the codex
conversation or PRs. It is the return leg of `tasks/codex-v3-handoff.md`.

**Status:** one item is already implemented on the branch
`online-session-config-hook` and needs merging before the 5.0 release. The rest
are observations codex worked around; each says what codex did instead, so
nothing here is blocking.

## Context

Codex was migrated to comicbox 5.0.0 (schema v3.0) over three commits on its
`comicbox-5` branch. The migration is straightforward and the v3 design holds
up well in practice. What follows is only the friction: places where codex had
to reach around an API, accept a lossy round trip, or duplicate something
comicbox already knows.

The codex side is on branch `comicbox-5`, pinned to `comicbox[pdf]~=5.0.0`.

---

## 1. `OnlineSession` could not be given settings (DONE, needs merge)

**Branch:** `online-session-config-hook`, commit `33a369a`.

`OnlineSession.__init__` read its base `ComicboxSettings` from `get_config()`
(`comicbox/online_session.py:320`). Every other comicbox entry point lets a
caller pass settings in, but this one did not, so an embedder holding
configured settings had no way to hand them over.

That mattered to codex twice:

- **Cache directory.** Codex keeps comicbox's online sqlite caches under its
  own `/config` volume, because comicbox's platformdirs default is thrown away
  when a Docker container is recreated. It travelled as
  `COMICBOX_ONLINE_CACHE_DIR`, which 5.0 stops reading — correctly, since env
  vars now nest with `__`. Codex could have switched to
  `COMICBOX_ONLINE__CACHE__DIR`, but that puts the setting back on a name
  comicbox is free to rename again.
- **Effort.** `Effort` has no `OnlineSession` keyword, so an embedder wanting
  anything but the default has only the environment to reach it through.

The fix adds a `config` keyword. Passing it also skips the config-file and
environment read, which is pure waste when the caller's settings are already
the answer that read would find. Tests are in
`tests/unit/test_online_session.py`; `NEWS.md`'s 5.0.0 Features section has an
entry.

**Action:** merge before releasing 5.0.0. Codex's `comicbox-5` branch depends
on it — `session_manager.py` passes `config=COMICBOX_ONLINE_CONFIG`.

---

## 2. The run estimator still models unbounded Comic Vine fan-out

`comicbox/online_estimate.py:117` `requests_per_comic()` keys Comic Vine's cost
off `MatchMode` alone. Since 5.0 bounds Comic Vine's per-candidate fan-out by
default and `Effort.THOROUGH` restores the unbounded search, the estimate no
longer describes what a default run actually costs.

Codex surfaces this estimate directly: the online-tag launcher shows a
projected duration before a scan and a live countdown during it
(`codex/librarian/onlinetag/estimate.py`, `codex/choices/onlinetag.py`). Under
the new default those numbers read high, and under `thorough` they read low.

**Suggested shape:** `requests_per_comic(source, mode, effort)` and
`estimate_run(..., effort=...)`, with `COMICVINE_REQUESTS_BY_MODE` becoming a
mode-by-effort table. Codex would pass the admin's configured effort, which it
already threads into the session.

---

## 3. The credit primary flag reaches no format codex writes

`credits.<person>.roles.<role>.primary` persists to ComicBookInfo only
(`comicbox/formats/comicbox/schema/__init__.py:150` marks it "CBI ONLY"; the
only writer is `comicbox/formats/comic_book_info/transform/credits.py:145`).
MetronInfo v1.1's schema has `primary` attributes on `URL` and `ID` but none on
a credit, and ComicInfo has no notion of one.

Codex writes ComicInfo and MetronInfo. It reads the flag, stores it on the
person-and-role pairing, and shows primaries first in the metadata panel — but
it deliberately ships **no editor control**, because a control whose value
could never be written back would be a lie. The flag survives only as long as
nothing rewrites the file.

**Not obviously actionable** — it is a limitation of the format specs, not of
comicbox. Worth knowing that the field is, in practice, read-only for the two
formats most tools use. If MetronInfo ever gains the attribute, codex's field
support map derives itself from the transforms and the control would light up
on its own.

---

## 4. Metron publishes no URL for several id types

`IDENTIFIER_PARTS_MAP[IdSources.METRON]`
(`comicbox/identifiers/identifiers.py:238`) notes that genre, location,
reprint, role, story and tag have no public web page, so `unparse_url` returns
`""` for them.

That is correct, and codex now derives its `Identifier.url` column through
`get_identifier_url` and stores the empty string. Two observations:

- An id on one of a series' `alternative_names` is a **series** id, but where
  it sits no longer implies that. Codex has to inject `id_type: series` when it
  folds those names in among its reprints, or the derived link is empty. If
  comicbox stated the type on those identifiers itself — the way it does for a
  top-level id that isn't an issue — the positional rule would carry through
  and no consumer would need to know this.
- `reprint` as an id type can never build a Metron URL, so any identifier
  comicbox files under it is linkless by construction.

---

## 5. `MergeMode` note — no action, just confirmation

The `MergeMode` docstring (`comicbox/config/settings.py:81`) is the clearest
statement of the tradeoff and it is accurate: `update` replaces top-level keys
wholesale and drops siblings, while `replace` recurses into dicts and replaces
only the leaves.

Codex writes with `update`, so a patch that carried only
`series.alternative_names` would drop the series' `name`. Codex compensates by
sending the whole series object it knows about. Switching codex to `replace`
for these writes would be the cleaner fix and is a codex-side decision;
recorded here only so the next person does not read the compensation as a
comicbox bug.

---

## Things that worked well, for what it's worth

- **The new skip warning earned its keep immediately.** Two codex test fixtures
  had been malformed for as long as they had existed — a null team value that
  voided the entire `teams` field, and a credit role's identifier keyed by
  `key` instead of by its source. 4.8.7 dropped both as silently as an absent
  tag. 5.0 named them, and both were repaired.
- **Deriving links from keys rather than storing them** removed a whole class
  of disagreement. Codex kept its url column and now fills it through
  `get_identifier_url`, which also fixed a latent mismatch: the column stores
  `""` for a linkless type, and the aggregate now carries `""` too rather than
  `None`.
- **`id_type` on a top-level identifier** let codex file a stated series or
  volume id correctly instead of assuming every comic-level id was an issue id.
- **Splitting manga from reading direction** was clean to adopt. The two facts
  land in two columns and two editor fields, and the format support map derives
  which format can store which without anything hand-written.

## Where the codex work lives

| Branch | Commit | What |
|---|---|---|
| `comicbox-5` | `1f1c593` | Moved and renamed APIs, derived identifier urls, v3 fixtures |
| `comicbox-5` | `07188d9` | Identifier type vocabulary bridge, reprint name fallback |
| `comicbox-5` | `0db3cf0` | manga, manga_volume, urls, Credit.primary, Reprint.alternative_name |

Remaining codex phases: online extras (effort setting, Comic Vine rate-limit
display), the one-time re-read migration, and docs.
