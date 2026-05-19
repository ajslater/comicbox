# v4 config / CLI reorg

Major-version reorganization of comicbox's config and CLI surface; ships as
comicbox 4.0.0. Locked plan; reference doc for implementation. No backwards
compat shims — v4 is a clean break paired with the next codex release.

## Goals

- Group every option into a clearly-named namespace so callers can find what
  they want without scanning the whole `--help`.
- Cut the online flag count by ~40%; consolidate near-duplicates.
- Drop every deprecated flag and env var.
- Push expert-only knobs to YAML-only.

## Group taxonomy

Ten groups, mirrored 1:1 between CLI argparse groups, the YAML config tree, and
the `ComicboxSettings` dataclass.

| #   | Group         | YAML key        | Owns                                                                                   |
| --- | ------------- | --------------- | -------------------------------------------------------------------------------------- |
| 1   | general       | `general`       | config path, recurse, dry-run, quiet, parallelism, tagger, theme                       |
| 2   | read          | `read`          | which formats to load metadata from; merge precedence                                  |
| 3   | write         | `write`         | which formats to write; replace-vs-merge; stamping; delete-all-tags                    |
| 4   | print         | `print`         | phase selection (loaded/normalized/merged/computed/final); validate; version           |
| 5   | convert       | `convert`       | cbz conversion; rename; page/cover extraction; import/export metadata files; pdf_pages |
| 6   | compute       | `compute`       | page-count computation; pages array computation                                        |
| 7   | online.lookup | `online.lookup` | enabled, sources, ids, series_ids, match, prompts, rematch, all_sources                |
| 8   | online.auth   | `online.auth`   | per-source credentials (key, user, pass, url)                                          |
| 9   | online.cache  | `online.cache`  | cache tri-state, dir, ttl                                                              |
| 10  | online.tuning | `online.tuning` | auto_threshold, effort, retry_budget; per-source overrides; advanced thresholds        |

## Decision: flat CLI with prefixed flags, not subcommands

Argparse groups (`add_argument_group`) provide the `--help` structure. No
`comicbox tag …` / `comicbox print …` subcommand split.

## New CLI surface

### General (group: "general")

| Flag                     | Type   | Default | Notes                                       |
| ------------------------ | ------ | ------- | ------------------------------------------- |
| `-c`, `--config PATH`    | path   | null    |                                             |
| `-r`, `--recurse`        | bool   | false   | Short-form kept; commonly typed             |
| `-n`, `--dry-run`        | bool   | false   |                                             |
| `-Q`, `--quiet`          | count  | 0       | INFO → SUCCESS → WARNING → ERROR → CRITICAL |
| `-j`, `--jobs N`         | int    | 1       |                                             |
| `-d`, `--dest-path PATH` | path   | `.`     |                                             |
| `-m`, `--metadata YAML`  | append | null    | Linear YAML; repeatable                     |
| `-D`, `--delete-keys`    | CSV    | []      | Glom key paths                              |
| `--delete-orig`          | bool   | false   |                                             |

YAML-only: `general.tagger`, `general.theme`.

### Read (group: "read")

| Flag                    | Type | Default | Notes                       |
| ----------------------- | ---- | ------- | --------------------------- |
| `--read FORMATS`        | CSV  | (all)   | Drop `-r` (now `--recurse`) |
| `--read-except FORMATS` | CSV  | []      | Was `--read-ignore`         |

YAML-only: `read.merge_order`.

### Write (group: "write")

| Flag                    | Type | Default | Notes                       |
| ----------------------- | ---- | ------- | --------------------------- |
| `-w`, `--write FORMATS` | CSV  | []      | Short form kept             |
| `--replace`             | bool | false   | Was `-R/--replace-metadata` |
| `--stamp`               | bool | false   | Was `-s/--stamp`            |
| `--no-stamp-notes`      | bool | false   | Was `-N/--no-stamp-notes`   |
| `--delete-all-tags`     | bool | false   |                             |

### Print (group: "print")

| Flag             | Type   | Default | Notes                                         |
| ---------------- | ------ | ------- | --------------------------------------------- |
| `--print PHASES` | string | ""      | Phase chars: v t f s l n m c p. Subsumes `-P` |
| `-p`             | alias  |         | = `--print p` (final metadata)                |
| `-v`             | alias  |         | = `--print v` (version)                       |
| `--validate`     | bool   | false   | Was `-V/--validate`                           |

`-l/--list` (filenames) folded into `--print f`. Drop `-V` short form since
`--validate` is unambiguous and rarely typed.

### Convert (group: "convert")

| Flag                    | Type   | Default | Notes                                        |
| ----------------------- | ------ | ------- | -------------------------------------------- |
| `--cbz`                 | bool   | false   | Was `-z/--cbz`                               |
| `--rename`              | bool   | false   |                                              |
| `--extract-pages RANGE` | range  | null    | Was `-e/--pages`                             |
| `--extract-covers`      | bool   | false   | Was `-o/--covers`                            |
| `--import PATHS`        | append | []      | Was `-i/--import`                            |
| `--export FORMATS`      | CSV    | []      | Was `-x/--export`                            |
| `--pdf-pages MODE`      | enum   | ""      | Was `-f/--pdf-page-format`; pdf/pixmap/image |

### Compute (no CLI; YAML-only)

YAML-only: `compute.pages` (default false), `compute.page_count` (default true).

### Online: Lookup (group: "online: lookup")

| Flag                | Type   | Default | Notes                                      |
| ------------------- | ------ | ------- | ------------------------------------------ |
| `--online SOURCES`  | CSV    | null    | `all` or comma list                        |
| `--id DB:ID`        | append | []      |                                            |
| `--series-id DB:ID` | append | []      |                                            |
| `--match MODE`      | enum   | auto    | ask / careful / auto / eager               |
| `--prompts MODE`    | enum   | ask     | ask / never (never = today's --unattended) |
| `--rematch`         | bool   | false   | Folds --force-search + --ignore-existing   |
| `--all-sources`     | bool   | false   | Was --tag-all-sources                      |

Match-mode rename map (user-facing names):

| Old policy       | New mode |
| ---------------- | -------- |
| always-prompt    | ask      |
| strict           | careful  |
| normal (default) | auto     |
| eager            | eager    |

The internal enum is renamed `Policy` → `MatchMode`; user-facing names change
for ASK / CAREFUL / AUTO; the EAGER member keeps its v3 spelling.

### Online: Auth (group: "online: auth")

Single repeatable flag with `<source>:<field>=<value>` syntax:

| Flag                       | Notes                                      |
| -------------------------- | ------------------------------------------ |
| `--auth metron:user=NAME`  | username                                   |
| `--auth metron:pass=PASS`  | password (warns: leaks into shell history) |
| `--auth metron:url=URL`    | base URL                                   |
| `--auth comicvine:key=KEY` | api key                                    |
| `--auth comicvine:url=URL` | base URL                                   |

Env vars preserved (recommended path):

- `COMICBOX_METRON_USER`, `COMICBOX_METRON_PASS`, `COMICBOX_METRON_URL`
- `COMICBOX_COMICVINE_KEY`, `COMICBOX_COMICVINE_URL`

(Rename `COMICBOX_METRON_USERNAME` → `COMICBOX_METRON_USER` and
`COMICBOX_METRON_PASSWORD` → `COMICBOX_METRON_PASS` and
`COMICBOX_COMICVINE_API_KEY` → `COMICBOX_COMICVINE_KEY` for consistency.)

### Online: Cache (group: "online: cache")

| Flag                   | Type   | Default | Notes                                                    |
| ---------------------- | ------ | ------- | -------------------------------------------------------- |
| `--cache MODE`         | enum   | on      | on / off / refresh. Folds --no-cache and --refresh-cache |
| `--cache-dir PATH`     | path   | null    |                                                          |
| `--cache-ttl DURATION` | string | 7d      |                                                          |

### Online: Tuning (group: "online: tuning")

| Flag                     | Type  | Default  | Notes                                                                      |
| ------------------------ | ----- | -------- | -------------------------------------------------------------------------- |
| `--auto-threshold FLOAT` | float | 0.95     | Was --confidence-threshold; single global value (no `:` syntax)            |
| `--effort MODE`          | enum  | balanced | minimal / balanced / thorough. Was --api-budget {fast,balanced,exhaustive} |

YAML-only (per-source):

```yaml
online:
    tuning:
        per_source:
            comicvine:
                auto_threshold: 0.99
                effort: thorough
            metron:
                effort: minimal
```

YAML-only (advanced; undocumented in user-facing reference):

```yaml
online:
    tuning:
        per_source:
            comicvine:
                min_confidence: 0.50
                disambiguation_margin: 0.10
                solo_threshold: 0.95
```

YAML-only (per-source rate-limit overrides; unchanged):

```yaml
online:
    tuning:
        per_source:
            metron:
                rate_limit:
                    per_minute: ...
```

YAML-only (retry budget): `online.tuning.retry_budget: 5`.

### Effort enum rename

| Old (api-budget) | New (effort) |
| ---------------- | ------------ |
| fast             | minimal      |
| balanced         | balanced     |
| exhaustive       | thorough     |

## YAML default file (final shape)

```yaml
comicbox:
    general:
        config: null
        recurse: false
        dry_run: false
        loglevel: INFO
        dest_path: .
        delete_keys: []
        delete_orig: false
        metadata: {}
        metadata_cli: null
        metadata_format: null
        jobs: 1
        tagger: null
        theme: gruvbox-dark

    read:
        formats:
            - cli
            - comet
            - metroninfo
            - comicbookinfo
            - comicinfo
            - filename
            - json
            - pdf
            - yaml
        except: []
        merge_order: null # null = MetadataSources enum order

    write:
        formats: []
        replace: false
        stamp: false
        stamp_notes: true
        delete_all_tags: false

    print:
        phases: ""
        validate: false

    convert:
        cbz: false
        rename: false
        extract_pages_from: null
        extract_pages_to: null
        extract_covers: false
        import_paths: []
        export_formats: []
        pdf_pages: ""

    compute:
        pages: false
        page_count: true

    online:
        lookup:
            enabled: false # runtime-only; CLI --online sets this
            sources: null # runtime-only
            ids: {} # runtime-only
            series_ids: {} # runtime-only
            match: auto
            prompts: ask
            rematch: false
            all_sources: false

        auth:
            metron:
                user: null
                pass: null
                url: null
            comicvine:
                key: null
                url: null

        cache:
            mode: on # on | off | refresh
            dir: null
            ttl: 7d

        tuning:
            auto_threshold: 0.95
            effort: balanced
            retry_budget: 5
            per_source: {} # see plan §online tuning for shape

    paths: null # CLI positional args
```

## Deletion list

CLI flags to delete entirely:

- `-y` (deprecated alias for `--dry-run`)
- `--skip-multiple` (deprecated; folded into `--prompts never --match careful`)
- `--accept-only` (deprecated; folded into `--match auto` which is the default)
- `--ignore-existing` (folded into `--rematch`)
- `--force-search` (folded into `--rematch`)
- `--no-cache` (folded into `--cache off`)
- `--refresh-cache` (folded into `--cache refresh`)
- `--api-key`, `--api-user`, `--api-password`, `--api-url` (folded into
  `--auth`)
- `--tag-all-sources` (renamed to `--all-sources`)
- `--read-ignore` (renamed to `--read-except`)
- `--confidence-threshold` (renamed to `--auto-threshold`; loses per-source CLI)
- `--api-budget` (renamed to `--effort`; loses per-source CLI; rename values)
- `--policy` (renamed to `--match`; rename values; loses per-source CLI)
- `--unattended` (renamed to `--prompts never`)
- `--cbz` short form `-z` (keep long flag)
- `--export` short form `-x` (keep long flag)
- `--import` short form `-i` (keep long flag)
- `--list` and `-l` (folded into `--print f`)
- `--print-phases` and `-P` (renamed to `--print`)
- `--print` and `-p` semantics moved to alias of `--print p`
- `--validate` short form `-V` (keep long flag)
- `--stamp` short form `-s` (keep long flag)
- `--no-stamp-notes` short form `-N` (keep long flag)
- `--compute-pages` and `-g` (YAML-only)
- `--no-compute-page-count` and `-A` (YAML-only)
- `--replace-metadata` short form `-R` (rename to `--replace`)
- `--theme` and `-t` (YAML-only)
- `--pdf-page-format` short form `-f` (rename to `--pdf-pages`, drop short form)

Env vars to delete:

- `COMICBOX_ONLINE_SKIP_MULTIPLE`
- `COMICBOX_ONLINE_ACCEPT_ONLY`

Env vars to rename:

- `COMICBOX_METRON_USERNAME` → `COMICBOX_METRON_USER`
- `COMICBOX_METRON_PASSWORD` → `COMICBOX_METRON_PASS`
- `COMICBOX_COMICVINE_API_KEY` → `COMICBOX_COMICVINE_KEY`
- `COMICBOX_ONLINE_FORCE_SEARCH`, `COMICBOX_ONLINE_IGNORE_EXISTING` → both →
  `COMICBOX_ONLINE_REMATCH`
- `COMICBOX_ONLINE_TAG_ALL_SOURCES` → `COMICBOX_ONLINE_ALL_SOURCES`
- `COMICBOX_ONLINE_CONFIDENCE_THRESHOLD` → `COMICBOX_ONLINE_AUTO_THRESHOLD`
- `COMICBOX_ONLINE_API_BUDGET` → `COMICBOX_ONLINE_EFFORT` (values also rename:
  fast→minimal, exhaustive→thorough)
- `COMICBOX_ONLINE_CACHE_ENABLED` + `COMICBOX_ONLINE_REFRESH_CACHE` →
  `COMICBOX_ONLINE_CACHE` (tri-state)
- `COMICBOX_ONLINE_POLICY` → `COMICBOX_ONLINE_MATCH` (values also rename)
- `COMICBOX_ONLINE_UNATTENDED` → `COMICBOX_ONLINE_PROMPTS` (values: ask | never)

Code paths to delete:

- `comicbox/config/__init__.py:_resolve_match_policy` — legacy translation logic
  for `accept_only` / `skip_multiple` / threshold-as-policy.
- The `skip_multiple`, `accept_only` fields in `OnlineSettings`.
- `DeprecatedDryRunAction` in `cli.py`.
- The `Policy.ALWAYS_PROMPT` validation that rejects pairing with unattended (no
  longer needed — `--match ask --prompts never` is the user's call).

## Dataclass shape (final)

```python
@dataclass(frozen=True, slots=True)
class GeneralSettings:
    config: str | Path | None = None
    recurse: bool = False
    dry_run: bool = False
    loglevel: str | int = "INFO"
    dest_path: str | Path = "."
    delete_keys: frozenset[str] = field(default_factory=frozenset)
    delete_orig: bool = False
    metadata: Mapping | None = None
    metadata_cli: tuple[str, ...] | None = None
    metadata_format: str | None = None
    jobs: int = 1
    tagger: str = "comicbox"
    theme: str | None = "gruvbox-dark"


@dataclass(frozen=True, slots=True)
class ReadSettings:
    formats: "frozenset[MetadataFormats]"
    except_: frozenset[str] | None = None  # YAML key: "except"
    merge_order: "tuple[MetadataSources, ...] | None" = None


@dataclass(frozen=True, slots=True)
class WriteSettings:
    formats: "frozenset[MetadataFormats]"
    replace: bool = False
    stamp: bool = False
    stamp_notes: bool = True
    delete_all_tags: bool = False


@dataclass(frozen=True, slots=True)
class PrintSettings:
    phases: "frozenset[PrintPhases]"
    validate: bool = False


@dataclass(frozen=True, slots=True)
class ConvertSettings:
    cbz: bool | None = None
    rename: bool | None = None
    extract_pages_from: int | None = None
    extract_pages_to: int | None = None
    extract_covers: bool | None = None
    import_paths: tuple[Path, ...] = ()
    export_formats: "frozenset[MetadataFormats]" = field(default_factory=frozenset)
    pdf_pages: str = ""


@dataclass(frozen=True, slots=True)
class ComputeSettings:
    pages: bool = False
    page_count: bool = True


@dataclass(frozen=True, slots=True)
class OnlineLookupSettings:
    enabled: bool = False
    sources: frozenset[str] | None = None
    ids: Mapping[str, int] = field(default_factory=dict)
    series_ids: Mapping[str, int] = field(default_factory=dict)
    match: MatchMode = MatchMode.AUTO
    prompts: Prompts = Prompts.ASK
    rematch: bool = False
    all_sources: bool = False


@dataclass(frozen=True, slots=True)
class OnlineSourceCredentials:
    # Metron uses user/pass/url; ComicVine uses key/url. Both fields are
    # nullable in either case; the source's `is_configured()` decides.
    user: str | None = None
    password: str | None = None  # YAML key: "pass"
    key: str | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class OnlineAuthSettings:
    metron: OnlineSourceCredentials = field(default_factory=OnlineSourceCredentials)
    comicvine: OnlineSourceCredentials = field(default_factory=OnlineSourceCredentials)


@dataclass(frozen=True, slots=True)
class OnlineCacheSettings:
    mode: CacheMode = CacheMode.ON   # ON | OFF | REFRESH
    dir: Path | None = None
    ttl: timedelta = field(default_factory=lambda: timedelta(days=7))


@dataclass(frozen=True, slots=True)
class OnlineSourceLimits:
    per_minute: int | None = None
    per_day: int | None = None
    per_second: int | None = None
    per_hour: int | None = None


@dataclass(frozen=True, slots=True)
class OnlineSourceTuning:
    auto_threshold: float | None = None
    effort: Effort | None = None
    min_confidence: float | None = None
    disambiguation_margin: float | None = None
    solo_threshold: float | None = None
    rate_limit: OnlineSourceLimits = field(default_factory=OnlineSourceLimits)


@dataclass(frozen=True, slots=True)
class OnlineTuningSettings:
    auto_threshold: float = 0.95
    effort: Effort = Effort.BALANCED
    retry_budget: int = 5
    per_source: Mapping[str, OnlineSourceTuning] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OnlineSettings:
    lookup: OnlineLookupSettings = field(default_factory=OnlineLookupSettings)
    auth: OnlineAuthSettings = field(default_factory=OnlineAuthSettings)
    cache: OnlineCacheSettings = field(default_factory=OnlineCacheSettings)
    tuning: OnlineTuningSettings = field(default_factory=OnlineTuningSettings)


@dataclass(frozen=True, slots=True)
class ComicboxSettings:
    general: GeneralSettings
    read: ReadSettings
    write: WriteSettings
    print: PrintSettings
    convert: ConvertSettings
    compute: ComputeSettings
    online: OnlineSettings
    paths: tuple[str | Path | None, ...]

    # Computed (derived in compute_config(); kept flat for ergonomics)
    all_write_formats: "frozenset[MetadataFormats]"
    read_filename_formats: "frozenset[MetadataFormats]"
    read_file_formats: "frozenset[MetadataFormats]"
    read_metadata_lower_filenames: frozenset[str]
    is_read_comments: bool
    is_skip_computed_from_tags: bool
```

New enums:

- `MatchMode = {ASK, CAREFUL, AUTO, EAGER}` (renames `Policy`)
- `Prompts = {ASK, NEVER}` (replaces `unattended: bool`)
- `Effort = {MINIMAL, BALANCED, THOROUGH}` (renames `APIBudget`)
- `CacheMode = {ON, OFF, REFRESH}` (replaces `cache_enabled` + `refresh_cache`)

Resolution helpers (in `settings.py`):

```python
def resolve_match(settings: OnlineSettings, source_name: str) -> MatchMode: ...
def resolve_auto_threshold(settings: OnlineSettings, source_name: str) -> float: ...
def resolve_effort(settings: OnlineSettings, source_name: str) -> Effort: ...
def resolve_min_confidence(settings: OnlineSettings, source_name: str) -> float: ...
def resolve_disambiguation_margin(settings: OnlineSettings, source_name: str) -> float: ...
def resolve_solo_threshold(settings: OnlineSettings, source_name: str) -> float: ...
```

Each does
`per_source[name].X if set else global.X if set else BUILT_IN_DEFAULT`.

## Execution order

1. **Plan doc** (this file) — checked in for safety.
2. **Settings dataclasses** — rewrite `comicbox/config/settings.py` into the new
   tree. Add the new enums.
3. **YAML template + defaults** — `comicbox/config/__init__.py` `_TEMPLATE`,
   `_ONLINE_TEMPLATE`, and `comicbox/config_default.yaml` rewritten.
4. **CLI** — rewrite `comicbox/cli.py` from scratch (or in-place if simpler)
   against the new shape with argparse groups matching the taxonomy.
5. **Deprecation sweep** — delete every flag, env var, and code path on the kill
   list in one commit.
6. **Internal callers** — search-and-replace every `self._config.X` reference in
   `box/`, `formats/`, `run.py`. The hot spots:
    - `comicbox/box/online_lookup.py` — heavy reader of `online.*`
    - `comicbox/formats/base/online/matcher.py` — reads policy/threshold/etc.
    - `comicbox/formats/base/online/auto_engage.py` — reads unattended,
      api_budget
    - `comicbox/formats/base/online/credentials.py` and `env.py` — auth
      resolution
    - `comicbox/formats/metron_api/online_source.py` and `comicvine_api/`
      equivalent — read `source_limits` and `cache_dir`
    - `comicbox/run.py` — reads `paths`, `recurse`, `jobs`, `online.enabled`,
      calls `_maybe_auto_engage_api_budget`.
7. **Tests** — mechanical update of fixtures that construct configs as
   dicts/Namespaces; new tests for `--rematch`, `--cache refresh`, `--auth`, and
   the env-var renames.
8. **Docs** — README, `tasks/online-tagging/*-user-doc.md`,
   `06-api-budget-spec.md`.
9. **Verify** — `make fix && make lint && make ty && make test`.

## Migration notes for downstream consumers

Codex is the primary library consumer. Breaking changes for them:

- All `comicbox.online.X` reads become `comicbox.online.lookup.X` /
  `comicbox.online.auth.X` / `comicbox.online.cache.X` /
  `comicbox.online.tuning.X` per the new taxonomy.
- `Policy` enum renamed to `MatchMode`; values renamed too.
- `APIBudget` enum renamed to `Effort`; values renamed.
- `unattended: bool` replaced by `prompts: Prompts` enum.
- `cache_enabled: bool` + `refresh_cache: bool` replaced by `mode: CacheMode`
  enum.
- Credentials: field names per source changed (Metron now uses
  `user`/`password`/`url`; field `username` no longer exists).
- `OnlineSettings` itself becomes a holder of 4 sub-settings, not flat.

Per the user's "no backward-compat shims" rule, codex updates in lockstep. No
translation layer.

## Open questions resolved

1. Flat CLI ✓
2. Per-source overrides → YAML only ✓
3. `--rematch` over `--force-search + --ignore-existing` ✓
4. `--effort` over `--api-budget` ✓
5. `--replace` on CLI; everything else YAML-only ✓

## What is NOT changing

- The set of supported metadata formats.
- The match-resolution policy algorithm (only the user-facing names change).
- The cover-hash signal, cache file names, retry schedule.
- The plugin system (separate work).
- Anything in `comicbox/formats/*/schema.py` or `transform/`.
- The Comicbox class chain or its mixin order.

## Testing strategy

- Mechanical: tests that construct `Namespace(comicbox=Namespace(...))` with the
  old flat shape get rewritten to the new nested shape.
- Coverage gaps: add tests for the new consolidated flags (`--rematch`,
  `--cache refresh`, `--auth`, `--prompts never`).
- Selector tests already exist for the prompt path — they need their
  `OnlineSettings` constructor updated for the new nested shape.
- Calibration harness (`tests/calibration/`) and stress harness
  (`tests/stress/`) construct configs; they need the same mechanical update.

## Done definition

- `make fix && make lint && make ty && make test` all clean.
- No reference to deleted flags or env vars anywhere in the codebase outside
  this plan doc.
- README and online-tagging user docs reflect the new surface.
