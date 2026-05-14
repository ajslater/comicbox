# Meta-plan: online metadata tagging

## Goal

Add a feature to comicbox that examines a comic's existing metadata, enriches it
from online comic databases (Metron, ComicVine, and optionally Grand Comics
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

- No GUI. CLI + library API only. We will not replicate ComicTagger's QT desktop
  UI.
- No web scraping fallback. First-class APIs only.
- No automatic write of low-confidence matches. Auto-write is gated on a
  confidence score (or explicit user/API consent).
- No new metadata schema invention; online responses transform into the existing
  comicbox internal schema.

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

Per-area digests, each focused and bounded, in `tasks/online-tagging/surveys/`:

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
- `08-cli-matrix.md` — flag-by-flag comparison: comictagger vs metron-tagger vs
  comicbox today, with an "adopt / skip / rename" column for each.

Phase 1 ends when all eight digests are reviewed.

### Phase 2 — CLI & config spec

Output: `tasks/online-tagging/02-cli-config-spec.md`

- Decide CLI surface: `--online <list>`, `--id <db>:<id>`, interactive vs
  `--auto-accept-only` vs `--skip-multiple`, cache flags (`--no-cache`,
  `--bust-cache`, optional TTL override), concurrency, confidence threshold for
  auto-write.
- Decide config sections: per-API (`api_key`, `base_url`,
  `rate_limit_override`), cache settings, autotag (confidence threshold,
  auto-write toggle).
- Rule: an API key's presence enables a source; `--online <list>` filters which
  enabled sources to actually query in this invocation; absence of `--online`
  means online lookup is off.
- Confirm config-file location obeys existing comicbox conventions (confuse).

### Phase 3 — Architecture spec

Output: `tasks/online-tagging/03-architecture-spec.md`

- Decision (confirmed): each online provider gets its own `MetadataSources` enum
  entry and its own `MetadataFormats` entry, with its own priority. They reuse
  the existing load → normalize → merge pipeline. (Note: the existing
  `MetadataSources.API` slot is reserved for programmatic library input via
  `add_metadata()` and is **not** repurposed for online sources.)
- Per-API transform: native API response → comicbox internal schema.
- Cache: backend choice (sqlite via mokkari pattern? plain JSON file? Use each
  library's built-in cache where available?), key strategy
  `(db, endpoint, args)`, TTL, invalidation flag.
- Rate limiter: per-API token bucket, 429 handling, exponential backoff.
- Concurrency model: thread pool per API (the libs are sync); per-file vs
  cross-file parallelism; how to keep batch parallelism under each API's rate
  limit.
- Merge precedence: configurable; default proposal — online enriches but does
  not overwrite explicit local values. Conflicts between two online sources
  resolved by priority order (proposed: Metron > ComicVine > GCD). Note:
  comicbox's current merge precedence is fixed by enum order; making it
  runtime-configurable is part of this work, not a free hookup.
- Pipeline sketch: load existing → search candidates → rank → resolve (auto /
  interactive / api-callback) → fetch full → transform → merge → save.

### Phase 4 — Match resolution spec

Output: `tasks/online-tagging/04-match-resolution-spec.md`

- Candidate gathering signals: filename parse + existing metadata (series,
  issue#, year, publisher).
- Ranking signals: title similarity, year, issue#, page count, cover hash
  distance.
- Cover hash: **pHash via `imagehash` (8×8 = 64 bits), Hamming threshold 10** —
  matches metron-tagger's choice and Metron's server-side precomputed
  `cover_hash`, so Metron candidates string-compare without an extra download.
  Hashing runs only when metadata is ambiguous (precision-optimised
  disambiguator, not always-on primary matcher). Hash distance blends with
  title-similarity / year / issue# / page-count into a unified confidence score
  (unlike comictagger's filter-then-hash approach).
- Confidence threshold for auto-write: default conservative, configurable.
- CLI prompt UX for ambiguous matches: numbered list, "skip", "manual ID", "open
  URL".
- Programmatic API: yields ranked candidates and accepts a selection callback,
  so a future codex feature can plug in without the CLI prompt.

### Phase 5 — Implementation roadmap & test strategy

Output: `tasks/online-tagging/05-roadmap.md`

PR-sized milestones in dependency order:

1. Config + CLI scaffolding for online flag plumbing (no API calls yet).
2. Metron `MetadataSource`: transform + talker + cache + rate limit + ID-only
   mode.
3. Search + ranking + auto-accept by confidence threshold.
4. Cover-hash matcher: cover extraction + pHash + scoring weight integration.
5. Interactive ambiguity prompt + programmatic callback API.
6. ComicVine `MetadataSource` (reuse pipeline).
7. Parallel batch processing.

**Out of initial scope but architected for:** GCD `MetadataSource` via Grayven —
deferred until Grayven hits v1.0 or user need is concrete. The pluggable sources
design from Phase 3 ensures GCD lands as a focused follow-up PR without rework.

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
6. Online sources get **new** `MetadataSources` + `MetadataFormats` entries with
   their own priorities. `MetadataSources.API` is **not** repurposed.
7. Cover hash → pHash via `imagehash` (64-bit, Hamming threshold 10), matching
   metron-tagger and Metron's server-side precomputed `cover_hash`. Hash
   distance blends with metadata signals into a unified confidence score.
8. GCD / Grayven → deferred from initial implementation; pluggable architecture
   keeps the door open. Add when Grayven reaches v1.0 or when user need is
   concrete.
9. Plugin refactor → **defer until after online tagging ships.** Flavor A
   (self-contained format modules, no dynamic loading) is the planned next
   chapter, informed by integration pain surfaced during this feature. Flavor B
   (entry_points / third-party plugin packages) is not on the roadmap.

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

## API budget rollout (sub-project)

Designed in [`06-api-budget-spec.md`](06-api-budget-spec.md). Rolled out
in five phases, all shipped on the `online-tagging` branch:

- **Phase A** ✓ — Build the levers as dormant code (a754f6a).
- **Phase B** ✓ — Calibrate against 339-fixture labeled set; pin
  thresholds (99d794e). See
  [`calibration-notes/2026-05-11-phase-b.md`](calibration-notes/2026-05-11-phase-b.md).
- **Phase C** ✓ — Ship `--api-budget` CLI flag + auto-engagement
  (c2b2ca6).
- **Phase D** ✓ — Per-budget `_MAX_VOLUMES_PER_SEARCH` (fast=5) +
  chunked-run scaffolding (`--resume`, sampler, labeler) (241fa04).
- **Phase E** ✓ — Solo-viable confidence floor; eliminates the
  solo-below-threshold silent-failure pattern (e7bfdbd).

Validated against the developer's 17,500-comic slimlib via a 500-fixture
stratified sample. See
[`calibration-notes/2026-05-12-slimlib-500.md`](calibration-notes/2026-05-12-slimlib-500.md):

- 96.9% CV accuracy on a one-per-series, decade+publisher-stratified sample
- 98.7% in the auto-write band
- 2 silent failures identified → addressed by Phase E

## Calibration follow-ups

Items surfaced by the slimlib calibration that warrant their own work:

1. **Phase E re-validation run.** Re-run the 500-fixture slimlib
   calibration with Phase E in place. Confirms:
   - Groo and Wanted Dossier convert from silent AUTO_WRITE → PROMPT
   - How many of the 471 currently-correct auto-write band hits convert
     to prompts (UX cost in real numbers)
   - No regressions on the other 469 auto-write band hits
   CV cache is warm so the re-run is paced by rate limits, not fetches —
   ~1-2 days wall-clock vs 3-4 for the first time.

2. **Multi-volume year-drift signal.** The Boys 2009 / Conan 2004 cases
   are multi-volume same-name series where the expected answer was in
   CV's top-3 candidates but lost on year ranking. `s_year` could be
   smarter about this: when a candidate's *volume* covers a year range
   that includes the file's year (even if `summary.year` differs by ±N),
   give credit. Touches: `comicbox/online/signals.py`. Worth a focused
   investigation before deciding the fix shape.

3. **Pre-filter tightening for FAST.** The Afterschool / Rain cases are
   single-candidate matches scoring 0.71-0.84 — they sneak past the 0.70
   pre-filter threshold but the actual right answer wasn't in CV's
   results. Tightening to 0.75 specifically for FAST would have dropped
   these. Needs validation that it doesn't introduce false negatives.

4. **Calibration against `/Volumes/Media/Comics/` (~860 full-cover
   comics).** A separate library, primarily Big Two with full cover
   images, makes this fixture set useful for two things slimlib couldn't
   exercise:
   - **Cover-hash signal calibration.** Slimlib's thumbnail covers
     forced `cover_quality: thumbnail`, so cover hashing never fired in
     the 500-fixture run. A full-cover library closes the loop on M4's
     cover-hash work.
   - **Metron calibration.** Slimlib's 2.2% Metron coverage was too
     sparse for reliable Metron accuracy stats. Big-Two-heavy is exactly
     Metron's strong suit; expect 30-50%+ Metron coverage after running
     `label_metron.py`.

   Run shape would mirror slimlib: stratified sample → label_metron →
   chunked --resume → summarize → notes doc.

5. **CLI surface for `solo_confidence_threshold`** (low priority).
   Internal-only for now. If real-world usage shows the 0.95 default is
   too strict and users want to tune per-source from config.yaml or CLI,
   that's a small plumbing exercise.

6. **Metron search returning the same wrong issue for unrelated comics.**
   Surfaced when running the post-Phase-E Phase E re-validation chunk:
   `label_metron.py` added Metron expected ids to 11 fixtures, and the
   compare report showed Metron issue id **7098** returned as the top
   matcher pick for three unrelated 2020 indie #1s (American Ronin,
   Kidz, Miles to Go). Issue 7098 is *New Mutants Vol 4 #1 (Marvel,
   Jan 2020)* per Metron's API. Issue id 128 similarly returned for
   Bad Reception 2019 and Archie 1955 #1.

   All matcher picks scored 0.88-0.89 against profiles that should have
   scored ~0.4-0.5 by the metadata weights. Three hypotheses to
   investigate (in order of likelihood):

   - The series_filter pre-filter at 0.7 isn't being applied on the
     Metron path for these fixtures (despite the FAST budget being
     active for CV).
   - Metron's `series_list({"name": ...})` filter isn't the AND-of-terms
     icontains+unaccent we documented — maybe loose-token match.
   - `_build_profile` for slimlib comics is picking up an unexpected
     series name from non-online tags.

   30-second diagnostic via `tests/calibration/debug_search.py`:
   ```
   uv run python -m tests.calibration.debug_search \
       ~/Milliways/Comics/slimlib/.../American\ Ronin\ \#001.cbz \
       --source metron
   ```
   That prints the profile, the exact search call, and the raw Metron
   response — instantly localizing where the false match enters.

   Likely a real matcher bug worth a focused fix; the math doesn't add
   up under any clean reading of the current scoring code.

## Follow-up work (after this feature ships)

> The full follow-up checklist lives in [TODO.md](TODO.md). The
> high-level entries below are kept here for context.


- **Flavor A plugin refactor.** Consolidate each format (ComicInfo, MetronInfo,
  ComicBookInfo, CoMet, ComicTagger, PDF, plus the new Metron and ComicVine
  online sources) into self-contained modules that own their schema, transforms,
  source registration, and format registration. No dynamic discovery — just
  better internal organisation. Plan to be drafted after online tagging lands,
  with the integration experience as input.
- **`LegacyNestedMDStringSetField` cleanup.** After `LEGACY_NESTED` is removed
  in M1, the `LegacyNestedMDStringSetField` / `XmlLegacyNestedMDStringSetField`
  classes (which still handle PDF `keywords` deserialization sanely) may be
  simplifiable. Investigate post-feature; out of scope for online tagging.
- **CV `description` HTML sanitization.** ComicVine's `description` field
  carries HTML markup (`<p>`, `<a>`, etc.). The M6 transform passes it
  through to `comicbox.summary` as-is. Decide whether to strip/escape on
  read; could live in the transform itself or as a computed-step pass.
  Touches: `comicbox/transforms/comicvine_api/`.
- **Richer Metron + ComicVine field mappings.** M2/M6 ship a focused subset
  (issue, series, dates, summary, page count, cover, publisher, collection
  title, modified). Add characters, teams, story arcs, credits with roles,
  identifiers (cross-source), prices, story_titles → stories, reprints,
  variants. Touches the per-format key maps and may need new `MetaSpec`
  builders for collections.
