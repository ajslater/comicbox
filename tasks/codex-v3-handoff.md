# Comicbox Schema v3.0 — Codex Handoff

**Audience:** an agent updating [codex](https://github.com/ajslater/codex) to
the paired comicbox release that ships schema v3.0. This document is
self-contained: it does not assume you saw the comicbox conversation or PRs.

**Status:** in progress. Each comicbox PR that changes the internal metadata
shape appends to the "Shape changes" section below. The **Adoption checklist**
at the bottom is the actionable summary; read it first, then the details you
need.

## Why this exists

comicbox and codex ship paired. Schema v3.0 changes the shape of the metadata
dict that `Comicbox.get_internal_metadata()` returns, plus the on-disk comicbox
JSON/YAML serializations. There are **no compatibility shims** — comicbox reads
v2 documents through a one-shot up-converter and thereafter speaks only v3.
Codex must be updated in the same release cycle.

The redesign came from an audit of every supported format spec (MetronInfo v1.1,
ComicInfo v2.1 draft, ComicBookInfo 1.0, CoMet 1.1) against the v2.0 unified
schema. Two themes drove it:

1. **Comicbox was inventing structure the source specs don't have** — splitting
   single-valued fields into collections, parsing free strings into objects,
   then fabricating format tags back out of those guesses.
2. **Comicbox conflated concepts that the highest-priority format keeps
   separate** — most importantly identifiers vs URLs, and four different "this
   issue relates to another book" concepts all crammed into `reprints`.

Format priority when specs disagree: **MetronInfo > ComicInfo >>
ComicBookInfo >> CoMet / PDF / filename.**

## Versioning and detection

- JSON documents carry
  `"schema": "https://github.com/ajslater/comicbox/blob/main/schemas/v3.0/comicbox-v3.0.schema.json"`.
  v2 documents carry the `/v2.0/comicbox-v2.0.schema.json` URL.
- YAML documents carry the same `schema:` key when exported by comicbox, but
  hand-written YAML often omits it — do not rely on it being present.
- The JSON Schemas live in the comicbox package at `comicbox/schemas/v3.0/`
  (`schemas/` at the repo root is a symlink to `comicbox/schemas/`). The v2.0
  directory is retained unchanged as the published v2 contract.
- The schemas are **hand-maintained**, not generated.
  `tests/schemas/test_json_schema_drift.py` walks the Marshmallow model against
  the JSON Schema and fails on any divergence in property names, types, or enum
  values — so the JSON Schema is a trustworthy description of the real shape.

## Shape changes

### PR 1 — v3.0 scaffolding, two field deletions

| Field                       | v2                  | v3          |
| --------------------------- | ------------------- | ----------- |
| `comicbox.alternate_images` | `[string]`          | **removed** |
| `comicbox.critical_rating`  | `number` (0–5, 1dp) | **removed** |

- `alternate_images` was dead: no format transform produced or consumed it since
  the ComicTagger format was dropped. Nothing to migrate.
- `critical_rating` was orphaned: comicbox's own schema README recorded that it
  "no longer maps to any format". All ratings flow through
  `community_rating.average_rating` (0–5, one decimal place) and
  `community_rating.rating_count`.

**Codex impact:** if codex has a column, serializer field, or import mapping for
either name, drop it. If codex used `critical_rating` for a _user's personal_
rating, that is now codex-side state with no comicbox representation — comicbox
will neither read nor write it.

<!-- Subsequent PRs append their shape-change tables here:
     PR 4 credits/primary, PR 5 identifiers/urls, PR 7 manga_volume,
     PR 8 CIX Alternate*, PR 9 reprints + series.alternative_names,
     PR 10 stories/title. -->

## Planned changes not yet landed

Listed so you can plan the codex work ahead of the final release. Shapes here
are the intended design; confirm against the tables above (and the v3.0 JSON
Schema) before writing code, since details can shift during implementation.

- **Roles canonicalized** to the MetronInfo vocabulary (42 roles) at ingest.
  `Colourist`/`Colorer` → `Colorist`; `CoverArtist`/`Cover Artist` → `Cover`;
  unmapped role strings pass through verbatim. Codex role tables that assume
  ComicInfo spellings need a migration.
- **Age rating canonicalized** to the MetronInfo scale: `Unknown`, `Everyone`,
  `Teen`, `Teen Plus`, `Mature`, `Explicit`, `Adult`. ComicInfo's 15 values are
  mapped in on read (`Everyone 10+`, `G`, `Kids to Adults` → `Everyone`, etc.)
  and projected back out on ComicInfo write.
- **`credit_primaries` removed**, folded into the role objects as
  `credits.<person>.roles.<role>.primary: true`. The flag is per (person, role):
  a primary Writer who also inked is not thereby a primary Inker.
- **Identifiers split from URLs**: `identifiers` becomes `{source: {key}}` with
  no per-identifier `url`; a new top-level `urls: [string]` holds verbatim URLs,
  primary first; `identifier_primary_source: {source, url}` collapses to
  `primary_id_source: string`. Comicbox still derives missing URLs from
  identifiers and missing identifiers from recognized URLs, so the convenience
  remains — it is just no longer stored redundantly.
- **`manga_volume: string`** added, holding MetronInfo's `MangaVolume` verbatim;
  `volume.number`/`volume.number_to` are parsed from it when unset.
- **`manga`** becomes tri-state `Yes`/`No`/`Unknown`; the `YesAndRightToLeft`
  compound is decomposed into `manga: Yes` + `reading_direction: rtl`.
- **`reprints`** entries gain an authoritative verbatim `name`; structured
  `series`/`volume`/`issue` become derived enrichment.
- **`series.alternative_names: [{name, language, identifiers}]`** added — Metron
  `Series/AlternativeNames` no longer lands in `reprints`.
- **ComicInfo `AlternateSeries`/`AlternateNumber`** now read into `arcs` (they
  predate `StoryArc` and were the pre-v2.0 way to record crossovers);
  `AlternateCount` is dropped, and comicbox writes arc data only to
  `StoryArc`/`StoryArcNumber`.
- **`title` is verbatim** — never split, never overwritten by joined story
  names. `stories` are derived from `title` (split on `;`) only when absent, and
  `title` from `stories` (joined with `; `) only when absent.

## Adoption checklist

- [ ] Remove any `alternate_images` and `critical_rating` handling.
- [ ] (later PRs) Update role vocabulary and its migration.
- [ ] (later PRs) Update age-rating vocabulary and its migration.
- [ ] (later PRs) Move credit primary flags into the per-role object.
- [ ] (later PRs) Split stored identifiers/urls; rename
      `identifier_primary_source` → `primary_id_source`.
- [ ] (later PRs) Handle `manga_volume`, tri-state `manga`, `reprints[].name`,
      `series.alternative_names`.
- [ ] Re-run codex's comicbox integration tests against the paired comicbox
      release; comicbox's own `tests/test_codex_api.py` pins the
      `get_internal_metadata()` contract and is the reference for expected
      shape.
