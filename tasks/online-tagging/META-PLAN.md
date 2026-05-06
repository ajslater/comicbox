# Meta-plan: online metadata tagging

## Goal

Add a feature to comicbox that examines a comic's existing metadata, enriches
it from online comic databases (Metron, ComicVine, and optionally Grand Comics
Database), and writes the merged result back to the archive.

> **Marvel API removed from scope.** Marvel shut down their Developer API in
> November 2025 and the `esak` Python client was archived 2026-02-02. Marvel
> coverage is available indirectly via ComicVine.

The feature includes:

- Direct ID-based exact match (`--id <db>:<id>`).
- Search-based fuzzy match using existing metadata + filename parsing.
- Ambiguity resolution via ranked candidates, optionally disambiguated by
  cover-image hashing.
- A configurable confidence threshold gating auto-write.
- Per-API rate-limiting, caching with TTL and explicit busting.
- Multi-comic batch processing, optionally parallel.
- A programmatic candidate-selection API so a future codex feature can drive
  ambiguity resolution non-interactively.

## Non-goals

- No GUI. CLI + library API only. We will not replicate ComicTagger's QT desktop UI.
- No web scraping fallback. First-class APIs only.
- No automatic write of low-confidence matches. Auto-write is gated on a
  confidence score (or explicit user/API consent).
- No new metadata schema invention; online responses transform into the
  existing comicbox internal schema.

## Sources of inspiration

- **metron-tagger** (https://github.com/Metron-Project/metron-tagger) — primary
  reference for the talker pattern, `CoverHashMatcher`, ambiguity prompts.
- **comictagger** (https://github.com/comictagger/comictagger) — secondary
  reference for CLI ergonomics, settings layout, and the `IssueIdentifier`
  ranking algorithm.
- **mokkari** (Metron), **simyan** (ComicVine), **Grayven** (GCD, pre-1.0) —
  Python clients for the in-scope databases. (`esak` / Marvel was investigated
  but the Marvel API is dead — see Goal section.)

## Phases

### Phase 1 — Survey (in progress, parallel subagents)

Per-area digests, each focused and bounded, in
`tasks/online-tagging/surveys/`:

- `01-codebase.md` — comicbox internals: sources, transforms, config, CLI,
  merge, identifiers, page/cover extraction.
- `02-mokkari.md` — Metron client surface: auth, rate limit, methods, response
  shape, cover URL access.
- `03-simyan.md` — ComicVine client: same dimensions.
- `04-esak.md` — Marvel client: documented for posterity; **out of scope**
  (Marvel API shut down November 2025).
- `05-grayven.md` — GCD client: same dimensions; library is pre-1.0.
- `06-metron-tagger-talker.md` — identification flow + `CoverHashMatcher` +
  ambiguity prompt.
- `07-comictagger-identifier.md` — `IssueIdentifier` cover hash + scoring
  algorithm.
- `08-cli-matrix.md` — flag-by-flag comparison: comictagger vs metron-tagger
  vs comicbox today, with an "adopt / skip / rename" column for each.

Phase 1 ends when all eight digests are reviewed.

### Phase 2 — CLI & config spec

Output: `tasks/online-tagging/02-cli-config-spec.md`

- Decide CLI surface: `--online <list>`, `--id <db>:<id>`, interactive vs
  `--auto-accept-only` vs `--skip-multiple`, cache flags
  (`--no-cache`, `--bust-cache`, optional TTL override), concurrency,
  confidence threshold for auto-write.
- Decide config sections: per-API (`api_key`, `base_url`,
  `rate_limit_override`), cache settings, autotag (confidence threshold,
  auto-write toggle).
- Rule: an API key's presence enables a source; `--online <list>` filters
  which enabled sources to actually query in this invocation; absence of
  `--online` means online lookup is off.
- Confirm config-file location obeys existing comicbox conventions (confuse).

### Phase 3 — Architecture spec

Output: `tasks/online-tagging/03-architecture-spec.md`

- Decision (confirmed): each online provider gets its own
  `MetadataSources` enum entry and its own `MetadataFormats` entry, with its
  own priority. They reuse the existing load → normalize → merge pipeline.
  (Note: the existing `MetadataSources.API` slot is reserved for programmatic
  library input via `add_metadata()` and is **not** repurposed for online
  sources.)
- Per-API transform: native API response → comicbox internal schema.
- Cache: backend choice (sqlite via mokkari pattern? plain JSON file? Use
  each library's built-in cache where available?), key strategy
  `(db, endpoint, args)`, TTL, invalidation flag.
- Rate limiter: per-API token bucket, 429 handling, exponential backoff.
- Concurrency model: thread pool per API (the libs are sync); per-file vs
  cross-file parallelism; how to keep batch parallelism under each API's
  rate limit.
- Merge precedence: configurable; default proposal — online enriches but
  does not overwrite explicit local values. Conflicts between two online
  sources resolved by priority order (proposed: Metron > ComicVine > GCD).
  Note: comicbox's current merge precedence is fixed by enum order; making
  it runtime-configurable is part of this work, not a free hookup.
- Pipeline sketch: load existing → search candidates → rank → resolve
  (auto / interactive / api-callback) → fetch full → transform → merge →
  save.

### Phase 4 — Match resolution spec

Output: `tasks/online-tagging/04-match-resolution-spec.md`

- Candidate gathering signals: filename parse + existing metadata (series,
  issue#, year, publisher).
- Ranking signals: title similarity, year, issue#, page count, cover hash
  distance.
- Cover hash: **pHash via `imagehash` (8×8 = 64 bits), Hamming threshold 10**
  — matches metron-tagger's choice and Metron's server-side precomputed
  `cover_hash`, so Metron candidates string-compare without an extra
  download. Hashing runs only when metadata is ambiguous (precision-optimised
  disambiguator, not always-on primary matcher). Hash distance blends with
  title-similarity / year / issue# / page-count into a unified confidence
  score (unlike comictagger's filter-then-hash approach).
- Confidence threshold for auto-write: default conservative, configurable.
- CLI prompt UX for ambiguous matches: numbered list, "skip", "manual ID",
  "open URL".
- Programmatic API: yields ranked candidates and accepts a selection callback,
  so a future codex feature can plug in without the CLI prompt.

### Phase 5 — Implementation roadmap & test strategy

Output: `tasks/online-tagging/05-roadmap.md`

PR-sized milestones in dependency order:

1. Config + CLI scaffolding for online flag plumbing (no API calls yet).
2. Metron `MetadataSource`: transform + talker + cache + rate limit + ID-only mode.
3. Search + ranking + auto-accept by confidence threshold.
4. Cover-hash matcher: cover extraction + pHash + scoring weight integration.
5. Interactive ambiguity prompt + programmatic callback API.
6. ComicVine `MetadataSource` (reuse pipeline).
7. Parallel batch processing.

**Out of initial scope but architected for:** GCD `MetadataSource` via Grayven
— deferred until Grayven hits v1.0 or user need is concrete. The pluggable
sources design from Phase 3 ensures GCD lands as a focused follow-up PR
without rework.

Test strategy:

- Unit tests with mocked API clients per source.
- Integration tests with VCR-style cassettes against each library.
- E2E: small fixture of comics with known online IDs; verify roundtrip.

## Branch

`online-tagging`, off of `origin/develop`.

## Open questions resolved

1. Artifact home → `tasks/online-tagging/`.
2. API survey scope → all four (mokkari, esak, simyan, Grayven).
3. Phase 1 timing → run in parallel now, while user reviews this plan.
4. Non-goals → no GUI, no scraping; auto-write gated by confidence score.
5. Marvel / esak dropped from scope (Marvel API discontinued).
6. Online sources get **new** `MetadataSources` + `MetadataFormats` entries
   with their own priorities. `MetadataSources.API` is **not** repurposed.
7. Cover hash → pHash via `imagehash` (64-bit, Hamming threshold 10),
   matching metron-tagger and Metron's server-side precomputed `cover_hash`.
   Hash distance blends with metadata signals into a unified confidence score.
8. GCD / Grayven → deferred from initial implementation; pluggable
   architecture keeps the door open. Add when Grayven reaches v1.0 or when
   user need is concrete.
9. Plugin refactor → **defer until after online tagging ships.** Flavor A
   (self-contained format modules, no dynamic loading) is the planned next
   chapter, informed by integration pain surfaced during this feature.
   Flavor B (entry_points / third-party plugin packages) is not on the roadmap.

## Open questions deferred to later phases

- Where should the on-disk cache live by default? (Phase 3)
- Should we reuse each library's built-in cache (mokkari `SqliteCache`, simyan
  `SQLiteCache`, Grayven `SQLiteCache`) or layer our own on top? (Phase 3)
- What's the default auto-write confidence threshold? (Phase 4)
- How do we handle conflicting issue IDs from different databases for the same
  archive? (Phase 3)
- Do we expose per-source merge weights, or fixed priority? (Phase 3)
- `--id` semantics: issue-id, series-id, or both with explicit prefix? Note
  metron-tagger's `--id` is series-id. (Phase 2)

## Follow-up work (after this feature ships)

- **Flavor A plugin refactor.** Consolidate each format (ComicInfo, MetronInfo,
  ComicBookInfo, CoMet, ComicTagger, PDF, plus the new Metron and ComicVine
  online sources) into self-contained modules that own their schema,
  transforms, source registration, and format registration. No dynamic
  discovery — just better internal organisation. Plan to be drafted after
  online tagging lands, with the integration experience as input.
- **`LegacyNestedMDStringSetField` cleanup.** After `LEGACY_NESTED` is
  removed in M1, the `LegacyNestedMDStringSetField` /
  `XmlLegacyNestedMDStringSetField` classes (which still handle PDF
  `keywords` deserialization sanely) may be simplifiable. Investigate
  post-feature; out of scope for online tagging.
