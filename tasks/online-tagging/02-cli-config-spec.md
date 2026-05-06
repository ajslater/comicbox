# Phase 2 — CLI & Config Spec

Concrete CLI surface and config-layout proposal for the online metadata tagging
feature. Mirrors and refines the recommendations in `surveys/08-cli-matrix.md`,
grounded in the actual current [comicbox/cli.py](../../comicbox/cli.py) and
[config_default.yaml](../../comicbox/config_default.yaml).

> **Major version bump.** This feature ships as the next major (e.g. 4.0). CLI
> breaking changes are acceptable.

## Decisions confirmed

From Phase 1:

- Marvel API / esak is out of scope (API discontinued).
- Each online provider gets its own `MetadataSources` and `MetadataFormats`
  entry with its own merge priority.
- Cover hash: pHash via `imagehash`, 64-bit, Hamming threshold 10. Disambiguator
  only, blended into a unified confidence score.
- GCD/Grayven deferred from initial scope but architected for inclusion.

From Phase 2 review:

- `-y`/`--dry-run` renames to `-n`/`--dry-run`. `-y` stays as a
  deprecation-warned alias **through the entire 4.x series**; removed in 5.0.
- `OnlineSettings` is a nested dataclass on `ComicboxSettings`.
- `--api-password` is kept on the CLI with a stderr warning at use time.
- Bare `--online` (no list) defaults to all sources with credentials configured.
- `--id` is single-comic only; submitting >1 input path with `--id` is a hard
  error to prevent mass-mistagging.
- Persistent settings get env-var overrides (`COMICBOX_ONLINE_*`) — match
  policy, cache, refresh.
- At config / env layer, prefer **positive** names (`cache_enabled`, not
  `no_cache`); at CLI layer, negative is fine when it matches the natural
  opt-out idiom (`--no-cache`).
- Per-source rate limits not configurable; inherit upstream library defaults.
- Cache TTL parses simple durations only (`7d`, `24h`, `60m`); no compound.
- Multiple `--id` flags = first-win cross-validation.
- Keyring inherits Python `keyring` defaults; no `--keyring-backend` flag.

## Constraint: short-flag pressure

Comicbox already uses these single-letter flags
([`comicbox/cli.py`](../../comicbox/cli.py)):
`c d e f g h i l m o p r s t v w x y z A D N P Q R V`. Several short flags that
comictagger / metron-tagger use for online concepts collide:

| Their flag             | Their meaning | Comicbox conflict                            |
| ---------------------- | ------------- | -------------------------------------------- |
| `-o` / `--online`      | enable online | `-o`/`--covers` — extract cover pages        |
| `-i` / `--interactive` | prompt        | `-i`/`--import` — import metadata            |
| `-r` / `--recurse`     | recurse       | `-r`/`--read` — read formats                 |
| `-R` / `--recursive`   | recurse       | `-R`/`--replace-metadata` — opposite meaning |
| `-n` / `--dry-run`     | dry run       | unused; comicbox uses `-y`/`--dry-run`       |

**Decision: long-only for all new online flags** except `-j`/`--jobs`
(conventional). No `-O`/`-I` etc.; capitalization-as-disambiguator hurts
discoverability.

## CLI surface

All flags below land in the **Options** group (`_add_option_group` in
[cli.py:176](../../comicbox/cli.py:176)).

### Online-lookup flags

| Flag                           | Type                                                                       | Default                     | Notes                                                                                                                                                                                                                                                                                                           |
| ------------------------------ | -------------------------------------------------------------------------- | --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--online [LIST]`              | optional CSV (uses `CSVAction` from [cli.py:80](../../comicbox/cli.py:80)) | off                         | Enables online lookup. Bare `--online` uses every source with credentials configured. With a list (`--online metron,comicvine`) filters that set.                                                                                                                                                               |
| `--id DB:ID`                   | str (repeatable)                                                           | —                           | Skip search; tag by exact **issue** id from named source. Series-id constraint deferred. Multiple `--id` flags allowed for cross-source confirmation; first non-error wins. **Errors out if more than one input comic is submitted in the same invocation** — applying one id to many comics would mass-mistag. |
| `--ignore-existing`            | bool                                                                       | false                       | Skip files already tagged from any online source (idempotent re-runs).                                                                                                                                                                                                                                          |
| `--accept-only`                | bool                                                                       | false                       | Auto-accept solo matches without prompting. See _Match Resolution Policy_ table below.                                                                                                                                                                                                                          |
| `--skip-multiple`              | bool                                                                       | false                       | Skip files with >1 candidate without prompting. See _Match Resolution Policy_ table below.                                                                                                                                                                                                                      |
| `--confidence-threshold FLOAT` | float in [0,1]                                                             | 0.85 (placeholder; Phase 4) | Confidence at or above auto-writes; below requires prompt or skip.                                                                                                                                                                                                                                              |

### Credential & endpoint overrides

| Flag                     | Type       | Default         | Notes                                                                                         |
| ------------------------ | ---------- | --------------- | --------------------------------------------------------------------------------------------- |
| `--api-key DB:KEY`       | repeatable | from config/env | API-key sources (currently ComicVine).                                                        |
| `--api-user DB:USER`     | repeatable | from config/env | User-auth sources (Metron, GCD).                                                              |
| `--api-password DB:PASS` | repeatable | from config/env | Kept for parity. Emits a stderr warning recommending env var or keyring (shell-history risk). |
| `--api-url DB:URL`       | repeatable | from config     | Override base URL (self-hosted Metron, dev mirrors).                                          |

### Cache flags

| Flag                   | Type                          | Default                          | Notes                                                                                                                                                                                     |
| ---------------------- | ----------------------------- | -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--cache-dir PATH`     | path                          | platformdirs default             | Per-source caches live as subdirs inside.                                                                                                                                                 |
| `--cache-ttl DURATION` | str (`7d`, `24h`, `60m`, `0`) | `7d`                             | Simple granularity; no compound durations. `0` disables expiry. Parsed into `timedelta`.                                                                                                  |
| `--no-cache`           | bool                          | (default `cache_enabled: true`)  | Opt-out: sets `online.cache_enabled = false` for this invocation (no read, no write). Config and env var stay positive (`cache_enabled`); CLI negative matches Unix idiom for opt-outs.   |
| `--refresh-cache`      | bool                          | (default `refresh_cache: false`) | Skip cache reads but write fresh results back. Persistent — config-file knob and env var supported alongside the CLI flag (rare but legitimate to want it always-on, e.g. dev workflows). |

### Concurrency (deferred to milestone 7 in roadmap)

| Flag                | Type | Default | Notes                                                                                                                                                                  |
| ------------------- | ---- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-j N` / `--jobs N` | int  | 1       | Parallel workers across files. Per-API rate limit still enforced. Implementation lands in milestone 7; flag accepted (no-op) in earlier milestones for forward-compat. |

### Match Resolution Policy matrix

`--accept-only` and `--skip-multiple` compose orthogonally on top of the default
(interactive prompt). Semantics match metron-tagger's: `--accept-only`
auto-accepts only when a single candidate exists, never "best of many."

|                       | conf ≥ threshold | 1 cand below threshold | >1 cand below threshold |
| --------------------- | ---------------- | ---------------------- | ----------------------- |
| **(default)**         | auto-write       | prompt                 | prompt                  |
| **`--accept-only`**   | auto-write       | accept solo            | prompt                  |
| **`--skip-multiple`** | auto-write       | prompt                 | skip                    |
| **both flags**        | auto-write       | accept solo            | skip                    |

There is **no `--interactive` flag** because interactive is the default; the two
opt-out flags above cover the unattended cases. `--accept-only --skip-multiple`
together = fully unattended bulk mode.

### CLI help text design

The match-resolution semantics are intricate enough to deserve dedicated help
output. Plan:

- Add an **Online — Match Resolution Policy** epilog table to the parser, in the
  same style as the existing PRINT_PHASE characters table
  (`_get_help_print_phases_table` at [cli.py:133](../../comicbox/cli.py:133)).
  The four-row × three-column matrix above appears verbatim in `comicbox -h`.
- Each individual flag's `help=` is short and back-references the table: e.g.
  `--accept-only` →
  `"Auto-accept solo low-confidence matches without prompting. See Match Resolution Policy table below."`
- An accompanying epilog prose block (similar in style to `_METADATA_EXAMPLES`
  at [cli.py:47](../../comicbox/cli.py:47)) explains the policy:
  "`--confidence-threshold` governs auto-write; the two opt-out flags control
  unattended behavior for below-threshold cases; combine for fully unattended."
- Online-related action examples join the existing examples section (similar to
  `_DELETE_KEYS_EXAMPLES` at [cli.py:58](../../comicbox/cli.py:58)).

## Config layout

Add an `online` namespace under the existing `comicbox:` root in
[config_default.yaml](../../comicbox/config_default.yaml):

```yaml
comicbox:
    # ... existing flat keys unchanged ...

    online:
        # Match policy
        confidence_threshold: 0.85
        skip_multiple: false
        accept_only: false
        ignore_existing: false

        # Cache
        cache_enabled: true # positive at config/env layer
        cache_dir: null # null → platformdirs default
        cache_ttl: "7d"
        refresh_cache: false # rare to set persistently; supported anyway

        # Per-source credentials and endpoints.
        # A source is "enabled" iff its required credentials are present.
        metron:
            username: null # also COMICBOX_METRON_USERNAME
            password: null # also COMICBOX_METRON_PASSWORD (or keyring)
            url: null # null → mokkari default

        comicvine:
            api_key: null # also COMICBOX_COMICVINE_API_KEY
            url: null # null → simyan default


        # gcd: deferred. Stub left out of default to avoid documenting an
        # unsupported config knob; add when Grayven hits v1.0.
```

CLI-only runtime flags (`--online`, `--id`, `--no-cache`) do **not** live in the
config file — they're per-invocation activation/override signals. They map to
runtime-only fields on the settings dataclass.

### Settings dataclass shape

Current [`ComicboxSettings`](../../comicbox/config/settings.py:18) is flat.
Adding ~15 online fields flat would push it past readable. Confirmed: use a
nested `OnlineSettings` dataclass.

```python
@dataclass(frozen=True, slots=True)
class OnlineSourceCredentials:
    api_key: str | None
    username: str | None
    password: str | None
    url: str | None

@dataclass(frozen=True, slots=True)
class OnlineSettings:
    # Runtime-only (CLI-derived; never lives in config file)
    enabled: bool                                       # --online passed
    selected_sources: frozenset[str] | None             # --online list filter; None = all configured
    explicit_ids: Mapping[str, int]                     # --id db:id

    # Persistent (config file + env var; CLI flag may override)
    confidence_threshold: float
    skip_multiple: bool
    accept_only: bool
    ignore_existing: bool
    cache_enabled: bool
    cache_dir: Path | None
    cache_ttl: timedelta
    refresh_cache: bool
    sources: Mapping[str, OnlineSourceCredentials]      # keyed by source name

@dataclass(frozen=True, slots=True)
class ComicboxSettings:
    # ... existing fields ...
    online: OnlineSettings   # always present; .enabled gates lookup
```

`enabled` and `selected_sources` are runtime-only on purpose: storing
`enabled: true` in a config file would surprise users by hitting the network on
every `comicbox -p`. The CLI `--online` flag is the activation gate.

## Credential & setting resolution order

For each `(setting)`, walk the chain and stop at first non-null/non-default:

1. **CLI flag** — `--api-key metron:...`, `--confidence-threshold 0.9`, etc.
2. **Environment variable** — `COMICBOX_<...>`, uppercase. Booleans accept
   `1/0`, `true/false`, `yes/no` (case-insensitive). Includes:
    - **Per-source credentials and URLs**: `COMICBOX_METRON_USERNAME`,
      `COMICBOX_METRON_PASSWORD`, `COMICBOX_METRON_URL`,
      `COMICBOX_COMICVINE_API_KEY`, `COMICBOX_COMICVINE_URL`
    - **Match policy**: `COMICBOX_ONLINE_ACCEPT_ONLY`,
      `COMICBOX_ONLINE_SKIP_MULTIPLE`, `COMICBOX_ONLINE_IGNORE_EXISTING`,
      `COMICBOX_ONLINE_CONFIDENCE_THRESHOLD`
    - **Cache**: `COMICBOX_ONLINE_CACHE_ENABLED`, `COMICBOX_ONLINE_CACHE_DIR`,
      `COMICBOX_ONLINE_CACHE_TTL`, `COMICBOX_ONLINE_REFRESH_CACHE`
3. **User config file** — `online.<...>` path (see YAML structure above).
4. **Keyring (password fields only)** —
   `keyring.get_password("comicbox-<source>", username)`. Inherits Python
   `keyring` defaults. Only consulted if `keyring` is importable. Never written
   by comicbox; user manages the entry out-of-band.

Keyring stays optional both for users who don't want a system keychain
dependency and to keep CI/headless installs unencumbered.

## CLI ↔ config ↔ env mapping

| CLI flag                      | Settings path                               | Config-file path                   | Env var                                     |
| ----------------------------- | ------------------------------------------- | ---------------------------------- | ------------------------------------------- |
| `--online`, `--online <list>` | `online.enabled`, `online.selected_sources` | (runtime only)                     | —                                           |
| `--id DB:ID`                  | `online.explicit_ids`                       | (runtime only)                     | —                                           |
| `--accept-only`               | `online.accept_only`                        | `online.accept_only`               | `COMICBOX_ONLINE_ACCEPT_ONLY`               |
| `--skip-multiple`             | `online.skip_multiple`                      | `online.skip_multiple`             | `COMICBOX_ONLINE_SKIP_MULTIPLE`             |
| `--ignore-existing`           | `online.ignore_existing`                    | `online.ignore_existing`           | `COMICBOX_ONLINE_IGNORE_EXISTING`           |
| `--confidence-threshold`      | `online.confidence_threshold`               | `online.confidence_threshold`      | `COMICBOX_ONLINE_CONFIDENCE_THRESHOLD`      |
| `--cache-dir`                 | `online.cache_dir`                          | `online.cache_dir`                 | `COMICBOX_ONLINE_CACHE_DIR`                 |
| `--cache-ttl`                 | `online.cache_ttl`                          | `online.cache_ttl`                 | `COMICBOX_ONLINE_CACHE_TTL`                 |
| `--no-cache`                  | `online.cache_enabled` ← false              | `online.cache_enabled` (set false) | `COMICBOX_ONLINE_CACHE_ENABLED` (set false) |
| `--refresh-cache`             | `online.refresh_cache`                      | `online.refresh_cache`             | `COMICBOX_ONLINE_REFRESH_CACHE`             |
| `--api-key DB:KEY`            | `online.sources[DB].api_key`                | `online.<DB>.api_key`              | `COMICBOX_<DB>_API_KEY`                     |
| `--api-user DB:U`             | `online.sources[DB].username`               | `online.<DB>.username`             | `COMICBOX_<DB>_USERNAME`                    |
| `--api-password DB:P`         | `online.sources[DB].password`               | `online.<DB>.password`             | `COMICBOX_<DB>_PASSWORD`                    |
| `--api-url DB:U`              | `online.sources[DB].url`                    | `online.<DB>.url`                  | `COMICBOX_<DB>_URL`                         |
| `-j N` / `--jobs N`           | `online.jobs` (deferred)                    | `online.jobs`                      | `COMICBOX_ONLINE_JOBS`                      |

## Validation rules

- `--online` (with or without list) but **no source has all required
  credentials** → error:
  `"no online source is fully configured; set Metron user/pass or ComicVine api_key"`.
- `--online <list>` references a name not in `{metron, comicvine}` → error with
  the list of known sources.
- `--id DB:ID` where DB is unknown → error.
- `--id DB:ID` where DB is known but lacks credentials → error.
- `--id DB:ID` where ID is non-numeric (assuming all current sources use integer
  ids) → error.
- **`--id` with more than one input path → error** (would mass-mistag). This
  applies whether the multiple paths come from CLI args or `--recurse`.
- `--confidence-threshold` outside `[0.0, 1.0]` → error.
- `--cache-ttl` unparseable → error with examples (`7d`, `24h`, `60m`, `0`).
- `--accept-only --skip-multiple` together → legal (unattended mode).
- `--api-password ...` on CLI → emit a stderr warning recommending env var or
  keyring.
- Zero candidates clear `min_confidence` (drop threshold, separate from
  `confidence_threshold`) under `--accept-only` → log the miss at INFO, continue
  to next file.

## Examples

```bash
# Basic interactive online lookup, prompting on ambiguity
comicbox --online --write metroninfo path/to/comic.cbz

# Tag by exact issue id, no search
comicbox --id metron:42 --write metroninfo path/to/comic.cbz

# Cross-source confirmation: tag from Metron, also write CV id
comicbox --id metron:42 --id comicvine:1234 --write metroninfo,comicinfo \
    path/to/comic.cbz

# Bulk unattended: low-friction batch
comicbox --online --accept-only --skip-multiple --ignore-existing \
    --recurse /comics/

# Use only ComicVine even though both are configured
comicbox --online comicvine /comics/*.cbz

# One-off API key override (e.g. trying a different account)
comicbox --online comicvine --api-key comicvine:abcd1234 /comics/issue.cbz

# Force-refresh cached responses (e.g. after Metron data correction)
comicbox --online --refresh-cache --recurse /comics/

# Self-hosted Metron mirror
comicbox --online metron --api-url metron:https://metron.local/api /comics/issue.cbz
```

## Migration notes

- `-y`/`--dry-run` → `-n`/`--dry-run`. Online tagging ships as a major version
  bump (e.g. 4.0). `-y` stays as a deprecation-warned alias through the entire
  4.x series; removed in 5.0. The deprecation warning emits to stderr on every
  use of `-y`.
- New `online:` config namespace is purely additive; existing user configs
  continue to load.
- No existing comicbox flag changes meaning beyond `-y`'s rename.

## Resolved Phase 3 questions

- **Per-source rate-limit override** → not configurable; inherit upstream
  library defaults (mokkari and simyan ship their own pyrate_limiter setups).
- **Cache TTL granularity** → simple only (`7d`, `24h`, `60m`, `0` for none). No
  compound durations.
- **`--id` with multiple sources** → first-win cross-validation. Tag from first
  source that returns a successful lookup; treat the others as cross-validation
  references.
- **Keyring backend** → inherit Python `keyring` defaults; no
  `--keyring-backend` flag.
- **`--api-password` on CLI** → keep, with stderr warning at use.

## Resolved Phase 4 questions

- **Zero candidates clear `min_confidence` under `--accept-only`** → log the
  miss at INFO and move on. (Phase 4 still owns picking the actual default for
  `min_confidence` separate from `confidence_threshold`.)

## Open questions deferred to later phases

- Default value of `--confidence-threshold` (Phase 4, calibrated against the
  ranking model).
- Default value of `min_confidence` drop threshold (Phase 4).
- Whether `--ignore-existing` keys off "any online identifier present" or
  "specifically this run's selected sources" (Phase 3 architecture).
- Concurrency model details for `-j` / milestone 7.
