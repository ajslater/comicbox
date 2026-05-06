# Phase 5 — Implementation Roadmap & Test Strategy

How to ship online metadata tagging in PR-sized chunks. Builds on the
specs in [META-PLAN.md](META-PLAN.md), [02-cli-config-spec.md](02-cli-config-spec.md),
[03-architecture-spec.md](03-architecture-spec.md), and
[04-match-resolution-spec.md](04-match-resolution-spec.md).

## Release strategy

Ships as a **single 4.0.0 major release** at the end. Milestones land as
sequential PRs into `online-tagging`; `online-tagging` merges to `develop`
only when all milestones are complete. The `online-tagging` branch lives
long; `develop` stays current with `main` until 4.0.0 ships.

Intermediate alphas (`4.0.0a1`, etc.) are **not** part of the default plan
— they can be cut on demand if early codex collaboration requires a real
package, but none are scheduled. Decide on tagging late, after most dev is
done.

## Resolved Phase 5 questions

- **String similarity** → `rapidfuzz`. Faster than stdlib `difflib`, MIT,
  small wheel, drop-in replacement for `fuzzywuzzy`. Used by metron-tagger
  too (consistency across the comic-tooling ecosystem).
- **Cover-hash cache file** → `${cache_dir}/cover_hashes.sqlite`, single
  shared file keyed by source-prefixed URL (`comicvine:<url>` etc.).
  Independent of per-source response caches.
- **Calibration harness** → in-tree under `tests/calibration/`, but
  excluded from default CI runs (slow, uses VCR cassettes against real
  responses). Runnable on demand via `make calibrate`.
- **Prompt UX library** → `questionary`. Matches metron-tagger's choice
  (already in the comic-tooling ecosystem). Provides the `select`
  primitive cleanly. Optional dep — fall back to plain `input()` when
  unavailable or stdin isn't a TTY.

## Dependencies between milestones

```
M1 (foundation) → M2 (Metron source) → M3 (search/rank/auto-accept) → M4 (cover hash) → M5 (prompt + selector) → M6 (ComicVine source) → M7 (parallel batch)
```

**All milestones serial** — no parallel development. M6's ComicVine work
waits on M5 in the queue, even though it could technically start once M3's
matcher is stable. Strictly serial keeps reviews focused and avoids merge
churn between the prompt UX and the new source.

## Cross-cutting standards (apply to every milestone)

- Each PR includes: code, tests, NEWS.md entry, docstrings, type annotations.
- `make fix && make lint && make test && make ty` clean before merge
  (per `~/.claude/rules/python-workflow.md`).
- Online support is **baked into comicbox 4.0** — no `online` extras
  group, no optional-import indirection. New deps go directly into
  `pyproject.toml`'s runtime dependencies. Online deps added across
  milestones: `mokkari`, `simyan`, `keyring`, `imagehash`, `Pillow`,
  `rapidfuzz`, `questionary`. Comicbox's existing `PDF_ENABLED` optional
  pattern is **not** mirrored for online.

### NEWS.md handling

NEWS.md is for **users**, not developers. Each milestone PR appends to a
**single 4.0.0 entry** that grows incrementally. Keep entries:

- **Functional** — describe what users can now do.
- **Brief** — headlines, not changelogs. One line per user-visible
  feature is the target.
- **Clear** — no jargon, no file paths, no internal symbol names.

Example for the whole feature:
`Online metadata lookup from Metron and ComicVine, with interactive
disambiguation and confidence-based auto-write.`

Don't write per-milestone diffs in NEWS — git log is the changelog.
- No `# type: ignore` without comment; no `cast()` without comment.
- Prefer `frozen=True, slots=True` dataclasses (matches existing
  `ComicboxSettings` style).

## M1 — Foundation: config + CLI scaffolding

**Goal**: every flag from the Phase 2 spec is parsed, every config key
loads, every settings field is typed — but no online code runs yet.

**Scope**:

- New CLI flags in [comicbox/cli.py](../../comicbox/cli.py): `--online`,
  `--id`, `--accept-only`, `--skip-multiple`, `--ignore-existing`,
  `--confidence-threshold`, `--cache-dir`, `--cache-ttl`, `--no-cache`,
  `--refresh-cache`, `--api-key`, `--api-user`, `--api-password`,
  `--api-url`, `-j`/`--jobs`. All accept input and validate. Plumbed
  into the namespace.
- `_y` → `-n` dry-run rename with deprecation alias for `-y` (stderr warning).
- Match Resolution Policy epilog table added to
  `_get_help_*` group in cli.py.
- New `online:` config namespace in
  [config_default.yaml](../../comicbox/config_default.yaml).
- `OnlineSettings` and `OnlineSourceCredentials` dataclasses in
  [comicbox/config/settings.py](../../comicbox/config/settings.py),
  nested on `ComicboxSettings`.
- `_TEMPLATE` updated in
  [comicbox/config/__init__.py](../../comicbox/config/__init__.py) for
  the new keys.
- New top-level `merge_order: tuple[MetadataSources, ...] | None` on
  `ComicboxSettings`.
- [`comicbox/box/merge.py`](../../comicbox/box/merge.py) iterates
  `settings.merge_order or MetadataSources` instead of the enum directly.
- New stub `MetadataFormats.METRON_API` and `COMICVINE_API` (transforms
  raise `NotImplementedError` for now).
- New stub `MetadataSources.METRON_API` and `COMICVINE_API` in correct
  position (between `ARCHIVE_FILE` and `IMPORT_FILE`).
- Credential resolution chain: CLI > env > config > keyring.
  Implementation lives in `comicbox/online/credentials.py`.
- `--api-password` use → stderr warning.
- `--id` with multiple paths → hard error.
- Boolean env-var parsing helper.
- **Cleanups** (paving for online additions to the same enum file):
  - Remove the unused `MetadataSource.path: bool` field at
    [comicbox/sources.py:14](../../comicbox/sources.py:14). Dead since the
    v2 refactor — declared but never read anywhere. Drop the now-pointless
    `path=True` constructor args from `ARCHIVE_FILENAME`, `ARCHIVE_PDF`,
    `ARCHIVE_COMMENT`, `ARCHIVE_FILE`, `IMPORT_FILE`. (The `source_data.path`
    access in [box/print.py:185](../../comicbox/box/print.py:185) is on
    `SourceData.path`, a different field, and is unaffected.)
  - Remove `MetadataSources.LEGACY_NESTED`. Its time is over. Drop:
    - the enum entry in [comicbox/sources.py:96](../../comicbox/sources.py:96),
    - the populator block in
      [comicbox/box/load.py:132](../../comicbox/box/load.py:132)–137,
    - the entry in `SOURCES_SET_ELSEWHERE` at
      [comicbox/box/sources.py:188](../../comicbox/box/sources.py:188),
    - the `LEGACY_NESTED_MD_KEYPATH` constants on the affected schemas
      ([schemas/base.py:143](../../comicbox/schemas/base.py:143),
      [schemas/pdf.py:48](../../comicbox/schemas/pdf.py:48),
      [schemas/pdf.py:113](../../comicbox/schemas/pdf.py:113)).
  Both cleanups land in M1 because they touch the same enum file; folding
  them in avoids a second pass over `sources.py`.

**Out of scope**: actual API calls; transforms; cache; rate limit; matcher;
prompt; mixin; `OnlineSource` ABC.

**Files touched**:

- New: `comicbox/online/__init__.py`, `comicbox/online/credentials.py`,
  `comicbox/online/env.py` (env-var helpers).
- Modified: `comicbox/cli.py`, `comicbox/config/__init__.py`,
  `comicbox/config/settings.py`, `comicbox/config_default.yaml`,
  `comicbox/sources.py`, `comicbox/formats.py`, `comicbox/box/merge.py`,
  `comicbox/box/load.py` (drop `LEGACY_NESTED` populator),
  `comicbox/box/sources.py` (drop from `SOURCES_SET_ELSEWHERE`),
  `comicbox/schemas/base.py`, `comicbox/schemas/pdf.py` (drop
  `LEGACY_NESTED_MD_KEYPATH` constants), `pyproject.toml`, `NEWS.md`.

**Dependencies**: none.

**Acceptance criteria**:

- `comicbox --help` shows all new flags and the policy epilog table.
- `comicbox --online --write metroninfo file.cbz` parses without crashing
  (and exits gracefully with "online code not yet implemented" log).
- `comicbox -y file.cbz` still works but logs a deprecation warning.
- `comicbox --id metron:42 file1.cbz file2.cbz` errors with the
  multi-comic message.
- Existing `comicbox -p file.cbz` behavior unchanged.
- Round-trip: setting `online.confidence_threshold: 0.9` in config and
  passing `--confidence-threshold 0.95` results in `0.95` in
  `ComicboxSettings.online.confidence_threshold`.
- `MetadataSource` no longer has a `path` field (verified by
  type-checker); existing `comicbox -p file.cbz` output unchanged.
- `MetadataSources.LEGACY_NESTED` is gone. Full test suite passes — any
  tests exercising re-extraction of metadata stored inside a PDF's
  `keywords` field are updated or removed. NEWS entry calls out the
  behavioral change: PDFs that hid comicbox metadata as JSON/XML inside
  their `keywords` field will no longer be auto-decoded. (The
  `LegacyNestedMDStringSetField` and `XmlLegacyNestedMDStringSetField`
  classes are left alone for now; their `_deserialize` behavior is still
  used for sane keyword string handling. Cleaning them up further is a
  separate, smaller follow-up if appetite remains.)

**Test plan**:

- Unit: `tests/test_online_credentials.py` — chain priority, missing-cred
  handling, keyring optional import.
- Unit: `tests/test_online_env.py` — boolean parsing edge cases.
- Unit: `tests/test_cli_online_flags.py` — every flag parses; deprecation
  warning fires; multi-comic `--id` errors.
- Unit: `tests/test_merge_order.py` — `merge_order: null` matches default
  behavior; explicit list reorders; missing names appended; duplicates
  raise.
- Snapshot: `comicbox --help` output (gates accidental regressions in the
  policy table).

## M2 — Metron source + ID-only path

**Goal**: `comicbox --id metron:42 --write metroninfo file.cbz` reads the
issue from Metron and writes a MetronInfo.xml block.

**Scope**:

- New `OnlineSource` ABC at `comicbox/online/sources/base.py`.
- New `comicbox/online/sources/metron.py` wrapping mokkari (`MetronOnlineSource`).
- `mokkari` and `keyring` added to runtime deps in
  [pyproject.toml](../../pyproject.toml).
- `comicbox/online/retry.py` — exponential-backoff decorator (1→60s,
  5 retries, honors `RateLimitError.retry_after`).
- `MetronApiSchema` (marshmallow) + `MetronApiTransform` under
  `comicbox/transforms/metron_api/`.
- mapping table from
  [03-architecture-spec.md#per-api-transform-layer](03-architecture-spec.md#per-api-transform-layer)
  realized.
- `ComicboxOnlineLookup` mixin (skeleton) in
  `comicbox/online/lookup.py` — handles only the `--id` shortcut path
  (no search yet). Inserted between `ComicboxNormalize` and `ComicboxMerge`.
- Cache wiring: `mokkari.api(cache=SqliteCache(db_name=...))` reads
  `online.cache_dir` and `cache_ttl`. `--no-cache` skips cache=. `--refresh-cache`
  unlinks the sqlite file before instantiation.
- `--ignore-existing` for the `--id` path: if comic already has a Metron
  identifier from a non-computed source, skip.

**Out of scope**: search; matcher; cover hashing; prompt; ComicVine.

**Files touched**:

- New: `comicbox/online/sources/__init__.py`,
  `comicbox/online/sources/base.py`, `comicbox/online/sources/metron.py`,
  `comicbox/online/retry.py`, `comicbox/online/lookup.py`,
  `comicbox/transforms/metron_api/__init__.py`,
  `comicbox/transforms/metron_api/schema.py`,
  `comicbox/schemas/metron_api.py`.
- Modified: `comicbox/box/__init__.py` (insert mixin in chain),
  `comicbox/formats.py` (real transform replaces stub),
  `pyproject.toml`, `NEWS.md`.

**Dependencies**: M1.

**Acceptance criteria**:

- `comicbox --id metron:42 --write metroninfo /tmp/test.cbz` (with valid
  Metron creds) fetches, transforms, merges, and writes MetronInfo.xml
  containing series, issue, year, characters, credits, identifiers.
- Re-running with `--ignore-existing` is a no-op (skips).
- Re-running without `--refresh-cache` reads from cache (no API hit).
- Network failure → retry → eventual success or graceful failure log.
- 401/403 → no retry, log + skip the source.

**Test plan**:

- Unit: `tests/test_online_retry.py` — backoff schedule, `retry_after`
  override, max retries, non-retriable errors (401/403).
- Unit: `tests/test_metron_transform.py` — fixed mokkari Issue payload →
  expected comicbox internal dict. Cover both string and integer issue#,
  missing optional fields, multi-arc/multi-team, `cv_id` cross-ref.
- Integration: VCR cassette of `mokkari.issue(42)` → full pipeline →
  written `MetronInfo.xml` snapshot.
- Integration: cache file appears in `${cache_dir}` after first run; second
  run doesn't hit the network (cassette assertion).
- Unit: `--ignore-existing` skip logic walks `_sources` correctly and
  ignores compute-phase identifiers.

## M3 — Search, rank, auto-accept

**Goal**: `comicbox --online metron --accept-only --skip-multiple file.cbz`
finds an unambiguous match by series + issue# + year, and tags it.

**Scope**:

- `MetronOnlineSource.search(criteria)` returns ranked candidates via
  `mokkari.issues_list(params={...})`.
- `OnlineMatcher` in `comicbox/online/matcher.py` — six-signal model,
  metadata-only (cover hashing in M4).
- `rapidfuzz` added to runtime deps.
- `comicbox/online/profile.py` — builds `ComicProfile` from normalized
  metadata.
- `Resolution` + decision tree in `OnlineMatcher.resolve()`.
- `ComicboxOnlineLookup.search_path` — for each comic without `--id`,
  build profile, search per active source, resolve, fetch full record on
  AUTO_WRITE.
- Match Resolution Policy applied: default = AUTO_WRITE only when
  threshold cleared; PROMPT case raises `NotImplementedError` (M5
  implements it); `--accept-only` and `--skip-multiple` work.

**Out of scope**: cover hashing; prompt; ComicVine.

**Files touched**:

- New: `comicbox/online/matcher.py`, `comicbox/online/profile.py`,
  `comicbox/online/signals.py` (the `s_*` functions).
- Modified: `comicbox/online/sources/metron.py` (search method),
  `comicbox/online/lookup.py` (search path), `pyproject.toml`,
  `NEWS.md`.

**Dependencies**: M2.

**Acceptance criteria**:

- For a comic with strong existing metadata (series, issue#, year), the
  matcher correctly identifies the Metron issue and writes it.
- For a comic with sparse metadata, `--accept-only --skip-multiple`
  results in no false-positive tagging.
- `--confidence-threshold 0.99` makes auto-write rare; `0.0` makes it
  almost always fire.
- Default-policy invocation (no `--accept-only`/`--skip-multiple`) on an
  ambiguous comic raises `NotImplementedError` mentioning M5.

**Test plan**:

- Unit: each `s_*` signal — table-driven cases incl. unicode, missing
  inputs, edge values.
- Unit: score blending — fixed candidates → expected scores.
- Unit: `Resolution` decision tree — every cell of the policy matrix
  exercised.
- Integration: VCR cassette of `issues_list` for "Foo Comics #5 (2020)"
  → matcher → AUTO_WRITE → MetronInfo.xml written.
- Integration: VCR cassette where metadata is sparse, `--accept-only` →
  AUTO_WRITE on solo, SKIP elsewhere.

## M4 — Cover-hash disambiguator

**Goal**: when metadata is ambiguous, cover hashing breaks the tie.

**Scope**:

- `comicbox/online/cover_hash.py` — pHash via `imagehash` + `Pillow`;
  shared SQLite cache at `${cache_dir}/cover_hashes.sqlite` keyed by
  source-prefixed URL.
- `imagehash` and `Pillow` added to runtime deps.
- `OnlineMatcher` invokes hashing per the policy from
  [04-match-resolution-spec.md#cover-hash-invocation-policy](04-match-resolution-spec.md#cover-hash-invocation-policy).
- For Metron candidates: use `Issue.cover_hash` directly (no download).
- For other sources (placeholder for M6): download `image` URL → hash.
- Local cover hash computed once per comic via
  `get_cover_page(skip_metadata=True)`; cached on `ComicboxComputed`
  layer (one local hash per archive).
- Hash failure → log WARNING, fall back to metadata-only score.
- `s_cover` blend integrated into `OnlineMatcher.score()`.
- Calibration harness skeleton at `tests/calibration/run.py` (full
  fixture set lands later).

**Out of scope**: ComicVine cover download (stub for M6); prompt;
calibration of actual thresholds (placeholders stand).

**Files touched**:

- New: `comicbox/online/cover_hash.py`,
  `tests/calibration/run.py`, `tests/calibration/README.md`.
- Modified: `comicbox/online/matcher.py`, `comicbox/online/sources/base.py`
  (add `cover_url` and `precomputed_hash` accessors on Candidate),
  `comicbox/online/sources/metron.py`, `pyproject.toml`, `NEWS.md`,
  `Makefile` (`calibrate` target).

**Dependencies**: M3.

**Acceptance criteria**:

- Comic with ambiguous metadata + matching cover → hash blend disambiguates
  to the correct issue.
- Comic with mismatched cover → score drops; doesn't auto-write.
- Cover hash cache file appears at expected path; second run hits the cache.
- `--no-cache` skips cover-hash cache too.
- Hash failure (corrupt cover, network error on candidate fetch) →
  WARNING logged, matcher continues without hash.

**Test plan**:

- Unit: `cover_hash` module — pHash repeatability, Hamming distance edge
  cases, cache hit/miss.
- Unit: matcher policy — when hashing triggers vs not.
- Integration: synthetic ambiguous case (two candidates, near-identical
  metadata, different precomputed Metron hashes) → matcher picks the
  hash-matching one.
- Integration: corrupt-cover case → WARNING, fall back to metadata score.

## M5 — Interactive prompt + Selector API

**Goal**: ambiguous matches that aren't auto-resolvable surface to the
user (or a programmatic callback).

**Scope**:

- `questionary` added to runtime deps. Required, not optional — the
  prompt UX is the spec'd default behavior, and `input()` fallback would
  dilute the contract.
- `comicbox/online/prompt.py` — default CLI selector implementing the UX
  from [04-match-resolution-spec.md#cli-prompt-ux](04-match-resolution-spec.md#cli-prompt-ux).
- `SelectorCallback` type alias and registration on `Comicbox.__init__`
  and the CLI runner.
- Manual ID re-entry path: user enters `metron:42` at the prompt → falls
  through to the `--id` code path for that one source.
- 5-minute prompt timeout (configurable via `online.prompt_timeout`,
  default `300`); timeout → SKIP + WARNING.
- `Resolution.kind == "PROMPT"` no longer raises `NotImplementedError`.

**Out of scope**: ComicVine; parallelism. (Prompts in parallel would
require coordination — handled in M7.)

**Files touched**:

- New: `comicbox/online/prompt.py`, `comicbox/online/selector.py` (the
  `SelectorCallback` type and registration).
- Modified: `comicbox/online/lookup.py`, `comicbox/run.py` (allow
  injecting selectors from outside the CLI), `comicbox/__init__.py`
  (expose selector on `Comicbox`), `pyproject.toml`, `NEWS.md`.

**Dependencies**: M4.

**Acceptance criteria**:

- Ambiguous comic without `--accept-only`/`--skip-multiple` → prompt
  appears in TTY, user can `1`-`9`, `s`, `m`, `q`.
- `m` opens manual ID prompt; valid `metron:42` → tags from id; invalid
  → re-prompt.
- `q` aborts entire run cleanly.
- 5-min stale prompt → WARNING, file skipped, run continues.
- Programmatic callback invoked via `Comicbox(path, online_selector=fn)`
  bypasses the prompt entirely.

**Test plan**:

- Unit: prompt rendering — snapshot test against fixed candidate set.
- Unit: callback wiring — programmatic selector receives expected
  `SelectorContext`.
- Unit: timeout — uses `select` or `signal.alarm`-equivalent; tested via
  an instant-timeout selector wrapping the real one.
- Manual smoke test: real terminal, walk the prompt UX in a sample run.

## M6 — ComicVine source

**Goal**: ComicVine works alongside Metron with the same flag surface.

**Scope**:

- `comicbox/online/sources/comicvine.py` wrapping `simyan` (`ComicVineOnlineSource`).
- `simyan` added to runtime deps.
- `ComicVineApiSchema` + `ComicVineApiTransform` under
  `comicbox/transforms/comicvine_api/`. Mapping per
  [03-architecture-spec.md](03-architecture-spec.md).
- ComicVine cover download for hashing — `image.thumb_url` (smallest
  practical size). Hash cached at `${cache_dir}/cover_hashes.sqlite`.
- simyan's `SQLiteCache` wired (response cache); separate from cover-hash
  cache.
- ComicVine quirks handled: HTML in `description` (strip / pass through?
  pass through; let downstream decide), CV's "volume" terminology (rename
  to comicbox's "series" in the transform), `BasicIssue` from search
  triggers a follow-up `get_issue()` for full data.

**Out of scope**: parallelism (M7); GCD.

**Files touched**:

- New: `comicbox/online/sources/comicvine.py`,
  `comicbox/transforms/comicvine_api/__init__.py`,
  `comicbox/transforms/comicvine_api/schema.py`,
  `comicbox/schemas/comicvine_api.py`.
- Modified: `pyproject.toml`, `NEWS.md`.

**Dependencies**: M2 (`OnlineSource` ABC), M3 (matcher), M4 (cover hash
flow). Can develop in parallel with M5 once those are stable.

**Acceptance criteria**:

- `comicbox --id comicvine:1234 --write comicinfo file.cbz` writes a
  full ComicInfo.xml.
- `comicbox --online file.cbz` (with both sources configured) queries
  both, merges per `merge_order`.
- Metron's stored `cv_id` vs independent CV match disagreement → WARN.
- ComicVine cover download cached; second run reuses.
- Rate-limit error from CV → backoff and retry.

**Test plan**:

- Unit: `comicvine_transform` — fixed simyan `Issue` → expected dict.
- Unit: HTML-in-description handling.
- Integration: VCR cassette for `cv.search()` + `cv.get_issue()` →
  matched and tagged.
- Integration: cross-validation case — Metron's `cv_id` ≠ independent CV
  match → WARN + both identifiers stored.
- Integration: `--online metron,comicvine` → merge order respected;
  archive metadata still wins.

## M7 — Parallel batch processing

**Goal**: `comicbox --online --recurse -j 4 /comics/` processes four files
at a time without exceeding upstream rate limits.

**Scope**:

- `-j N` threadpool at the file-loop level in `comicbox/run.py`.
- Per-API rate limiter (mokkari/simyan's `pyrate_limiter`) is process-wide
  and thread-safe; verify under load.
- Prompt-vs-parallel coordination: at most one prompt at a time. When a
  worker hits a `PROMPT` resolution, it acquires a `prompt_lock`; other
  workers continue their non-prompt work.
- Logging stays linear and prefixed with the file path so output is
  readable under parallel runs.
- `online.jobs` config key respected (default `1`).
- `--no-cache` + `-j` interaction documented.

**Out of scope**: async; cross-source parallelism within one comic
(stays sequential within a worker).

**Files touched**:

- Modified: `comicbox/run.py`, `comicbox/online/lookup.py`,
  `comicbox/online/prompt.py` (prompt lock), `NEWS.md`.

**Dependencies**: M6 (multi-source needed for realistic load test).

**Acceptance criteria**:

- 4 workers on a 100-file directory don't exceed Metron's documented
  20 req/min: confirmed via test with synthetic clock or a
  `pyrate_limiter` assertion harness.
- Two ambiguous files in parallel produce serialised prompts; output
  is readable.
- `-j 1` is byte-identical in behavior to the pre-M7 codepath.

**Test plan**:

- Unit: prompt lock under contention.
- Integration: multi-file fixture with mix of auto-resolvable and
  ambiguous comics; measure rate-limit compliance.
- Manual: stress test with 1000 files at `-j 8`.

## Cross-cutting test strategy

- **Unit tests** live alongside their modules under `tests/`. Use
  pytest's `monkeypatch` for env-var resolution; mock `OnlineSource`
  for matcher tests.
- **Integration tests** use VCR.py cassettes stored in
  `tests/cassettes/online/`. Record once with real credentials in a
  dev environment; commit cassettes; CI replays. Cassettes scrub
  Authorization headers and API keys.
- **E2E tests** under `tests/e2e/online/` use a small fixture set of
  CBZ files with known online ids. Each test:
  1. starts from a stripped CBZ,
  2. runs `comicbox --online --id <db>:<id> --write <fmt> file.cbz`,
  3. asserts the resulting metadata matches a snapshot.
- **CI configuration**: unit + integration on every PR; E2E on
  `online-tagging` branch pushes only (slower, network-replay-heavy).
  Calibration harness only on demand.
- **No test hits real APIs in CI.** Cassettes are the contract.
- **Coverage gate**: 90% line coverage on
  `comicbox/online/` and `comicbox/transforms/{metron_api,comicvine_api}/`.

## Calibration harness

`tests/calibration/` contains:

- `run.py` — script that loads a fixture set, runs the matcher against
  each, records `metadata_score`, `cover_score`, `final_score`, and
  whether the picked candidate matches the known-correct id.
- `fixtures.json` — gitignored manifest of (file, expected_id) pairs.
  Per-developer; not in CI.
- `README.md` — instructions for building a personal fixture set.
- Output: a markdown table of "matched correctly", "matched wrong
  thing", "no match", grouped by score band.

Use the harness to tune `confidence_threshold` and `min_confidence`
before 4.0.0 final; document the values in NEWS.md.

`make calibrate` runs `tests/calibration/run.py` against
`fixtures.json` if present.

## Out of scope for v1.0 (deferred to follow-up)

- **GCD via Grayven** — pluggable; ships as a focused PR when Grayven
  reaches v1.0.
- **Variant cover fallback** — see
  [04-match-resolution-spec.md](04-match-resolution-spec.md#deferred-enhancements-post-v1).
- **`min_confidence` exposure** — add a CLI flag if power-user demand
  surfaces post-launch.
- **Series-id constraint in `--id`** (metron-tagger style) — defer to
  Phase X if user demand surfaces.
- **Flavor A plugin refactor** — separately tracked in META-PLAN
  follow-up.
- **`LEGACY_NESTED` review** — separately tracked follow-up project.

## Resolved questions

- **Release strategy** → single 4.0.0 final; intermediate alphas only on
  demand (e.g. for codex collaboration), not scheduled. Decide on tagging
  cadence late, after most dev is done.
- **Deps shape** → no extras. All online deps in regular runtime deps.
  Comicbox 4.0 ships with online support baked in.
- **`questionary`** → required runtime dep, not optional with fallback.
- **M5 / M6 ordering** → strictly serial (M5 first, then M6).
- **NEWS.md cadence** → single 4.0.0 entry, grown as milestones land.
  User-facing headlines, not a per-PR changelog.
