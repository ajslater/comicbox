# Phase 3 — Architecture Spec

How online metadata tagging plugs into comicbox's existing mixin chain,
sources/formats registries, and merge pipeline. **Designed within the current
architecture** — no plugin-discovery refactor (that's Flavor A, deferred until
after this feature ships).

## Decisions confirmed

From Phase 1 + Phase 2:

- New `MetadataSources` and `MetadataFormats` entries per online provider, with
  explicit priorities. `MetadataSources.API` is **not** repurposed.
- Cover hash: pHash via `imagehash`, blended into a unified confidence score.
- Cache TTL: simple durations only.
- Per-source rate limits: inherit upstream library defaults.
- Persistent settings have `COMICBOX_ONLINE_*` env-var overrides.
- `--id`: first-win cross-validation, single-comic only.

## New `MetadataFormats` entries

Add to [comicbox/formats.py:37](../../comicbox/formats.py:37):

```python
METRON_API = MetadataFormat(
    "Metron API",
    frozenset({"metron-api", "metronapi"}),
    "metron-api.json",                  # filename only used for --export
    MetronApiTransform,
    has_pages=False,
    lexer="json",
)
COMICVINE_API = MetadataFormat(
    "ComicVine API",
    frozenset({"comicvine-api", "cv-api", "comicvineapi"}),
    "comicvine-api.json",
    ComicVineApiTransform,
    has_pages=False,
    lexer="json",
)
```

Why new formats rather than reusing `METRON_INFO` / `COMIC_INFO`:

- mokkari and simyan return Pydantic models with shapes distinct from the XML
  schemas (richer relations, nested structures, different field names — see
  surveys [02-mokkari.md](surveys/02-mokkari.md) and
  [03-simyan.md](surveys/03-simyan.md)).
- A separate format makes the data lineage in `--print` and `--export` honest
  (the user can see Metron-API-sourced metadata distinct from a writer-supplied
  MetronInfo.xml).
- Reuses the existing transform machinery cleanly — no overloading.

`enabled` defaults to `True` but is dynamically gated at runtime by credential
availability (see "Source enable rules" below).

## New `MetadataSources` entries

Add to [comicbox/sources.py:21](../../comicbox/sources.py:21). Position
matters: enum order = additive-merge precedence (earlier wins). Online sources
slot in **between `ARCHIVE_FILE` and `IMPORT_FILE`**:

```python
class MetadataSources(Enum):
    CONFIG = ...                # unchanged
    ARCHIVE_FILENAME = ...      # unchanged
    ARCHIVE_PDF = ...
    ARCHIVE_COMMENT = ...
    ARCHIVE_FILE = ...
    METRON_API = MetadataSource("Metron API", formats=(MetadataFormats.METRON_API,))      # NEW
    COMICVINE_API = MetadataSource("ComicVine API", formats=(MetadataFormats.COMICVINE_API,))  # NEW
    IMPORT_FILE = ...           # unchanged
    CLI = ...                   # unchanged
    API = ...                   # programmatic library injection (existing)
    LEGACY_NESTED = ...         # unchanged
```

Rationale: archive-embedded metadata is the user's prior curated record and
should win — the file's own MetronInfo.xml represents an intentional commit.
Online data is then treated as the authoritative database source-of-truth and
beats per-invocation inputs (`IMPORT_FILE`, `CLI`, `API`), which are usually
search hints rather than final values. A user who genuinely wants
CLI/import/API to override online data uses `-R`/`--replace-metadata`.
`LEGACY_NESTED` stays at the bottom as the deepest fallback (and is flagged
for review — see "Follow-up work" in META-PLAN).

## Configurable merge precedence

Currently
[`comicbox/box/merge.py:36`](../../comicbox/box/merge.py:36) iterates
`MetadataSources` directly:

```python
for source in MetadataSources:
    self._merge_metadata_by_source(source, ...)
```

**Change**: introduce `merge_order: tuple[MetadataSources, ...]` on
`ComicboxSettings`, defaulting to the enum order. `ComicboxMerge` iterates
`merge_order` instead of `MetadataSources`.

Config layer:

```yaml
comicbox:
  merge_order: null   # null → use MetadataSources enum order (default)
  # OR explicit:
  # merge_order: [CONFIG, ARCHIVE_FILENAME, ARCHIVE_PDF, ARCHIVE_COMMENT,
  #               ARCHIVE_FILE, METRON_API, COMICVINE_API, IMPORT_FILE,
  #               CLI, API, LEGACY_NESTED]
```

Validation:

- All listed names must be valid `MetadataSources` members.
- Missing members are silently appended at the end (so adding new sources
  later doesn't break existing user configs).
- Duplicates → error.

Per-field merge weights are **out of scope**. Fixed priority by source is
simpler, matches the existing mental model, and the confidence-score blend
in Phase 4 handles per-candidate weighting (not per-field).

## Per-API transform layer

Pattern follows the existing
[`comicbox/transforms/comicinfo/__init__.py`](../../comicbox/transforms/comicinfo/__init__.py)
shape:

```python
# comicbox/transforms/metron_api/__init__.py
class MetronApiTransform(BaseTransform):
    SCHEMA_CLASS = MetronApiSchema   # marshmallow schema mirroring mokkari Issue
    SPECS_TO = create_specs_to_comicbox(_METRON_API_TO_COMICBOX)
    SPECS_FROM = create_specs_from_comicbox(...)  # near-empty; we don't write back to API
```

Mapping (mokkari `Issue` → comicbox schema), at a glance:

| mokkari field | comicbox path |
|---|---|
| `series.name` | `series.name` |
| `series.volume` | `series.volume` |
| `series.year_began` | `series.start_year` |
| `cover_date` | `date` |
| `image` | `cover_image` |
| `cover_hash` | `comicbox_cover_hash` (new internal field) |
| `arcs[].name` | `story_arcs.<name>` |
| `characters[].name` | `characters` (set) |
| `teams[].name` | `teams` (set) |
| `credits[]` | `contributors.<role>` (set) |
| `id` | `identifiers.metron.issue` |
| `cv_id` | `identifiers.comicvine.issue` (cross-reference!) |
| `gcd_id` | `identifiers.grandcomicsdatabase.issue` |
| `name` | `title` |
| `number` | `issue` |

ComicVine uses simyan's `Issue` model and a separate transform with a similar
mapping table; the two transforms are independent modules under
`comicbox/transforms/`. Stub schemas live in `comicbox/schemas/<source>.py`
matching the existing per-format pattern.

The transforms are **read-only** in practice (we never push back to the
APIs), so `SPECS_FROM` is minimal — present only to satisfy the
`BaseTransform` contract for `--export`-style introspection.

## Source enable rules

A `MetadataSources.<ONLINE>` member is **active for this run** iff:

1. Its credentials resolve (CLI > env > config > keyring) to non-null values
   for all required fields. Required by source:
   - `METRON_API`: `username` AND `password`.
   - `COMICVINE_API`: `api_key`.
2. The source name is in `online.selected_sources`, or
   `online.selected_sources is None` (bare `--online`).
3. `online.enabled` is true (i.e. `--online` was passed).

Sources that fail any check are skipped silently for the run. Calling
`--online comicvine` with no CV api_key configured produces the validation
error specified in
[02-cli-config-spec.md](02-cli-config-spec.md#validation-rules).

## Online lookup pipeline

Insert a new mixin between
[`ComicboxNormalize`](../../comicbox/box/normalize.py) and
[`ComicboxMerge`](../../comicbox/box/merge.py:11). Tentative name:
`ComicboxOnlineLookup`. The mixin chain becomes:

```
... → ComicboxLoad → ComicboxNormalize → ComicboxOnlineLookup → ComicboxMerge → ...
```

Per-comic flow inside `ComicboxOnlineLookup`:

1. **Gate**: if `settings.online.enabled` is false, return immediately. No
   network, no work.
2. **Build search criteria** from already-normalized offline metadata —
   series, issue#, year, publisher. Pulls best-available value across
   normalized sources using the existing additive-merge logic over a small
   field set.
3. **For each active online source** (in `merge_order` order, so Metron
   first by default):
   - If `online.explicit_ids[source]` is set (`--id metron:42`): skip search;
     fetch the issue by id directly. **First successful fetch wins**;
     remaining sources act as cross-validation only (their identifiers get
     stored, their other fields are still merged subject to priority).
   - Else: query the API's search endpoint with the criteria. Receive a list
     of candidates.
   - Rank candidates by confidence (Phase 4 — `OnlineMatcher`). Cover-hash
     comparison is invoked here when the metadata-only score is ambiguous.
   - Apply Match Resolution Policy (default prompt / `--accept-only` /
     `--skip-multiple`) to pick zero or one candidate.
4. **For each accepted match**: fetch the full Issue record (mokkari
   `issue(id)` / simyan `get_issue(id)` — full credits etc.).
5. **Inject**: serialise the full record to JSON, transform via the
   per-source transform, and call
   [`add_source(MetadataSources.<ONLINE>, source_data)`](../../comicbox/box/sources.py:224).
6. **Continue** to `ComicboxMerge`, which now sees the new source data and
   merges it according to `merge_order`.

This keeps the new mixin focused on lookup; everything downstream (merge,
write, print, export) treats the online sources identically to existing ones.

## Caching strategy

**Reuse upstream library caches.** Both mokkari and simyan ship SQLite-backed
caches:

- mokkari: `mokkari.sqlite_cache.SqliteCache(db_name=..., expire=...)` passed
  via `cache=` to the API factory.
- simyan: `SQLiteCache` with similar semantics; covers response caching
  separately from its rate-limit SQLite bucket.

Comicbox owns the cache directory (`online.cache_dir`, defaulting to
platformdirs); each library gets a sub-path:

```
${cache_dir}/
  metron_cache.sqlite
  metron_ratelimit.sqlite     # mokkari's separate rate-limit bucket
  comicvine_cache.sqlite
  comicvine_ratelimit.sqlite
```

Cache TTL: pass `online.cache_ttl` (parsed as `timedelta`, in seconds) to each
library's cache.

CLI flag plumbing:

- **`--no-cache`**: instantiate the API client without the `cache=` kwarg.
  No reads, no writes for the run.
- **`--refresh-cache`**: brute-force approach — `unlink()` each
  `${source}_cache.sqlite` before instantiating the client, then run normally.
  This is small-cost (cache rebuilds during the run) and predictable.
  Alternative finer-grained "skip-read but write" wrapping is rejected as
  added complexity for low payoff.
- Persistent `online.cache_enabled: false` → same as `--no-cache` per run.
- Persistent `online.refresh_cache: true` → same as `--refresh-cache` per run.

## Rate limiting & retry

Inherit upstream pyrate_limiter setups (mokkari 20/min and 5000/day; simyan
1/sec and 200/hr). When a library raises `RateLimitError` (or equivalent),
wrap with retry:

- Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s. Cap at 60s.
- Max retries: 5. Beyond that → fail this comic, log, continue.
- `RateLimitError.retry_after` (when present, mokkari has it) overrides the
  exponential schedule.
- HTTP 5xx errors retry with the same schedule. Auth errors (401/403) do
  not retry — log and skip the source for the rest of the run.

Implementation: a small `comicbox/online/retry.py` decorator that wraps
each API call. No global state needed.

## Concurrency model (deferred to milestone 7)

Specced for forward-compat; flag accepted but no-op until milestone 7.

- ThreadPoolExecutor with `max_workers = settings.online.jobs` (default 1).
- Workers process one **comic** each — easier than per-API parallelism and
  naturally bounded by the slowest source.
- pyrate_limiter is process-wide and thread-safe, so multiple workers share
  the rate budget without coordination from us.
- For batch invocations (`--recurse`), the threadpool sits at the file-loop
  level; per-comic work is sequential within a worker.
- No async; comicbox is sync end-to-end and the upstream libs are sync too.
- Open question for Phase 5 implementation: does cover-hashing need its own
  worker pool, or piggyback on the per-comic pool?

## Identifier handling & cross-source conflicts

Comicbox already supports multiple identifier sources via
[`identifiers.IDENTIFIER_PARTS_MAP`](../../comicbox/identifiers/identifiers.py:112)
(16 sources catalogued). Online tagging populates the `identifiers` field
with the issue id from each successful source. Multi-source coexistence is
the normal case, not a conflict.

Real conflicts:

1. **Metron's `cv_id` field disagrees with our ComicVine search result.**
   Both Metron and ComicVine are queried; Metron's record self-reports a
   ComicVine id; we also independently picked a ComicVine candidate.
   - If they match: store one identifier. (Strong cross-validation signal —
     boosts confidence.)
   - If they disagree: log a `WARNING`, keep both identifiers (with
     source labels), fall through to merge by priority. The user can
     inspect later via `--print`.
2. **Two sources give different `series` / `title` for the same comic.**
   Resolved by `merge_order`: Metron wins by default. Both raw values are
   preserved in their respective source's `SourceData` (visible via
   `--print` or `-P s`), so nothing is lost.
3. **`--ignore-existing` keying.** Skip the file if it already carries an
   identifier from any of **this run's selected sources** —
   `--online comicvine --ignore-existing` skips files with a CV id but
   re-queries those that have only a Metron id. Importantly, identifiers
   produced by the **compute phase** (`comicbox/box/computed/`) do **not**
   count as "already tagged" — only identifiers present in pre-merge
   `SourceData` from real upstream sources count. Implementation: walk the
   loaded source data before the online step and look for
   `identifiers.<source.name>` entries, ignoring computed-phase output.

## Confidence scoring (signpost to Phase 4)

Phase 3 declares the **integration point**, Phase 4 picks the **algorithm**.

- An `OnlineMatcher` class is invoked from `ComicboxOnlineLookup` step 3
  (rank candidates).
- Inputs: a normalized "comic profile" dict (series, issue#, year,
  publisher, page-count) + a list of candidate dicts in the same shape +
  the original archive's cover bytes (lazy, fetched only if needed).
- Output: list of `(candidate, score: float)` pairs, sorted descending.
- The matcher decides internally whether to invoke cover hashing
  (precision-optimised disambiguator).

## Configuration additions (Phase 3-specific)

Beyond what's already in
[02-cli-config-spec.md](02-cli-config-spec.md#config-layout):

```yaml
comicbox:
  # NEW top-level field
  merge_order: null   # null → MetadataSources enum order

  online:
    # ... existing Phase 2 keys ...

    # Retry budget for transient API failures
    retry_budget: 5
```

Settings dataclass additions:

```python
@dataclass(frozen=True, slots=True)
class ComicboxSettings:
    # ... existing fields ...
    merge_order: tuple[MetadataSources, ...] | None  # None = enum order

@dataclass(frozen=True, slots=True)
class OnlineSettings:
    # ... existing fields ...
    retry_budget: int
```

## Module layout (proposed)

```
comicbox/
  online/
    __init__.py
    lookup.py              # ComicboxOnlineLookup mixin
    retry.py               # exponential backoff decorator
    matcher.py             # OnlineMatcher (Phase 4 fills in)
    cover_hash.py          # pHash on cover bytes
    sources/
      __init__.py
      base.py              # OnlineSource ABC: search(), get(), credentials()
      metron.py            # MetronOnlineSource wrapping mokkari
      comicvine.py         # ComicVineOnlineSource wrapping simyan
  transforms/
    metron_api/
      __init__.py
      schema.py            # marshmallow schema mirroring mokkari Issue
      __init__.py          # MetronApiTransform
    comicvine_api/
      ...                  # mirror structure
```

The `online/sources/base.py` ABC defines the small contract every source
must implement, so adding GCD/Grayven later is a matter of adding one file
plus enum entries. Contract sketch:

```python
class OnlineSource(ABC):
    name: ClassVar[str]                                      # "metron"
    metadata_source: ClassVar[MetadataSources]               # METRON_API
    metadata_format: ClassVar[MetadataFormats]               # METRON_API

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def search(self, criteria: SearchCriteria) -> list[Candidate]: ...

    @abstractmethod
    def get(self, issue_id: int) -> dict: ...    # returns native API JSON
```

`ComicboxOnlineLookup` instantiates one `OnlineSource` per active provider
and walks them in `merge_order` order.

## Test strategy (preview; full plan in Phase 5)

- **Unit**: per-source transform exercised against fixtured API JSON
  responses (mokkari/simyan provide example payloads in their test suites
  we can borrow from).
- **Integration**: VCR.py cassettes for one search + one get per source.
- **E2E**: small fixture of CBZ files with known online ids; verify a
  full `--online --write metroninfo` run produces expected output.
- **Mocking layer**: each `OnlineSource` is straightforward to mock
  (small ABC); the lookup mixin tests use mocked sources to exercise the
  pipeline without HTTP.

## Resolved Phase 3 questions

- Reuse upstream library caches → yes; comicbox just owns the cache dir.
- Per-source rate-limit override → no; inherit upstream defaults.
- Conflicting issue ids across sources → store all identifiers; merge other
  fields by `merge_order`; **warn** on Metron `cv_id` ↔ CV-search disagreement
  (`WARNING` log level — it materially affects resulting metadata).
- Per-source merge weights vs fixed priority → fixed priority via
  `merge_order`. Per-field weighting not exposed.
- Where the cache lives by default → platformdirs default, configurable via
  `online.cache_dir`.
- `--ignore-existing` scope → only identifiers from this run's selected
  sources; identifiers produced by the compute phase don't count.
- Default position of online sources in `merge_order` → between `ARCHIVE_FILE`
  and `IMPORT_FILE`.
- Location of `merge_order` setting → top-level `ComicboxSettings.merge_order`
  (affects all sources, not just online).

## Open questions deferred to Phase 4

- Confidence-score formula and weights (metadata signals vs cover-hash).
- Default `confidence_threshold` and `min_confidence` values.
- Whether cover hashing always runs or only when metadata score is ambiguous.
- CLI prompt UX for ambiguous matches.
