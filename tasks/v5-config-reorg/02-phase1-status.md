# v4 reorg — phase 1 status (HISTORICAL)

> All eight phases are now complete (phase 1–8); the reorg ships as
> comicbox 4.0.0. This document is preserved as the original
> phase-1 checkpoint and reflects state mid-reorg, not current state.

Resumable checkpoint after phase 1 of the v4 config/CLI reorg. The plan
lives in `01-plan.md`; this doc tracks where the in-flight work ended
and what's still TODO.

## Phase 1 outcome

**Goal:** make `import comicbox` succeed against the new nested
`ComicboxSettings` / `OnlineSettings` shape without committing to
the full call-site sweep.

**Done:**

- `comicbox/config/settings.py` — full rewrite. New enums
  (`MatchMode`, `Prompts`, `Effort`, `CacheMode`), new nested
  dataclasses (`GeneralSettings`, `ReadSettings`, `WriteSettings`,
  `PrintSettings`, `ConvertSettings`, `ComputeSettings`,
  `OnlineLookupSettings`, `OnlineAuthSettings`, `OnlineCacheSettings`,
  `OnlineSourceTuning`, `OnlineTuningSettings`, `OnlineSettings`,
  `ComicboxSettings`). New resolvers (`resolve_match`,
  `resolve_auto_threshold`, `resolve_effort`,
  `resolve_min_confidence`, `resolve_disambiguation_margin`,
  `resolve_solo_threshold`, `resolve_rate_limit`,
  `resolve_credentials`).
- `comicbox/config_default.yaml` — full rewrite. Mirrors the new
  dataclass tree. `general / read / write / print / convert /
  compute / online / paths`. Quoted `mode: "on"` to avoid YAML 1.1
  bool interpretation.
- `comicbox/config/__init__.py` — clean v5 version (~600 lines). New
  `_TEMPLATE`, `_ONLINE_TEMPLATE`, `_build_settings`,
  `_build_online_settings`, `_build_auth_settings`,
  `_build_per_source_tuning`. Helpers renamed:
  `_parse_match_value`, `_parse_prompts_value`,
  `_parse_effort_value`, `_parse_cache_mode_value`,
  `_parse_auto_threshold_value`. Legacy translation logic (the
  `_resolve_match_policy` / `_resolve_api_budget` blocks) deleted.
- `comicbox/formats/base/online/env.py` — rewritten. New env var
  surface (`COMICBOX_ONLINE_MATCH`, `COMICBOX_ONLINE_PROMPTS`,
  `COMICBOX_ONLINE_REMATCH`, `COMICBOX_ONLINE_ALL_SOURCES`,
  `COMICBOX_ONLINE_AUTO_THRESHOLD`, `COMICBOX_ONLINE_EFFORT`,
  `COMICBOX_ONLINE_CACHE`, `COMICBOX_ONLINE_CACHE_DIR`,
  `COMICBOX_ONLINE_CACHE_TTL`, `COMICBOX_ONLINE_RETRY_BUDGET`).
  Credential field names updated (`user`/`pass`/`key`/`url`).
  Function renamed: `read_policy_env` → `read_online_env`.
  Legacy env vars removed entirely.
- `comicbox/formats/base/online/credentials.py` — field names updated
  to `user`/`pass`/`key`/`url`. Keyword mapping to
  `OnlineSourceCredentials` (`pass` → `password=`) handled at
  construction.
- `comicbox/formats/base/online/cli_overrides.py` — rewritten for the
  new `--auth <source>:<field>=<value>` flag. `CliOverrides.from_cli`
  replaced by `CliOverrides.from_auth_list`.
- `comicbox/formats/base/online/matcher.py` — imports renamed:
  `Policy → MatchMode`, `resolve_policy → resolve_match`,
  `resolve_confidence_threshold → resolve_auto_threshold`,
  `resolve_solo_confidence_threshold → resolve_solo_threshold`. The
  `_policy_auto_writes` match statement updated for new enum names.
  `settings.unattended` → `settings.lookup.prompts is Prompts.NEVER`.
- `comicbox/formats/base/online/auto_engage.py` — `APIBudget` →
  `Effort` (with value renames `EXHAUSTIVE → THOROUGH`,
  `FAST → MINIMAL`). Reads `online.tuning.effort` and
  `online.tuning.per_source[name].effort`.
  `settings.unattended` → `settings.lookup.prompts is Prompts.NEVER`.
- `comicbox/formats/base/online/series_filter.py` — `APIBudget` →
  `Effort` (with value renames).
- `comicbox/formats/base/online/sources/base.py` —
  `settings.cache_dir` → `settings.cache.dir`.
- `comicbox/formats/metron_api/online_source.py` —
  `resolve_api_budget` → `resolve_effort`, `self._credentials.username`
  → `self._credentials.user`. Cache wrapping uses `CacheMode` enum.
  Rate-limit lookup uses `resolve_rate_limit(settings, name)`.
- `comicbox/formats/comicvine_api/online_source.py` —
  `resolve_api_budget` → `resolve_effort`, `self._credentials.api_key`
  → `self._credentials.key`. Cache wrapping uses `CacheMode` enum.
  Rate-limit lookup uses `resolve_rate_limit(settings, name)`.
- `comicbox/box/online_lookup.py` —
  `Policy → MatchMode`,
  `online.explicit_ids → online.lookup.ids`,
  `online.explicit_series_ids → online.lookup.series_ids`,
  `online.selected_sources → online.lookup.sources`,
  `online.sources.get → online.auth.sources.get`,
  `online.cache_dir → online.cache.dir`,
  `online.cache_enabled → online.cache.mode is CacheMode.OFF`,
  `online.ignore_existing → online.lookup.rematch`,
  `online.force_search → online.lookup.rematch`,
  `online.enabled → online.lookup.enabled`,
  `online.unattended → online.lookup.prompts is Prompts.NEVER`,
  `online.tag_all_sources → online.lookup.all_sources`.
  `_apply_session_online_override` renamed to
  `_apply_session_lookup_override` and updated to nest properly.
- `comicbox/run.py` —
  `self._config.loglevel → self._config.general.loglevel`,
  `self._config.recurse → self._config.general.recurse`,
  `self._config.jobs → self._config.general.jobs`,
  `self._config.online.enabled → self._config.online.lookup.enabled`.

**Verified:**

- `uv run python -c "import comicbox; from comicbox.box import
  Comicbox; from comicbox.config import get_config"` succeeds.
- `uv run python -c "from comicbox.cli import get_args, main"` succeeds.
- `uv run --group lint ruff check` clean on every file touched this
  phase.

## What's still broken

**Will fail at runtime** (not import):

- `cli.py` argparse setup still uses v4 flag names (`--policy`,
  `--unattended`, `--api-key`, etc.). `comicbox --help` shows the old
  flags. `comicbox -p file.cbz` will produce a `Namespace` shape the
  new `_build_settings` doesn't understand.
- `comicbox/config/computed.py` reads flat config keys (`metadata_cli`,
  `delete_keys`, `print`, `tagger`, `write`, `export`, `read`) — must
  traverse the new tree (`general.metadata_cli`, `general.delete_keys`,
  `print.phases`, `general.tagger`, `write.formats`,
  `convert.export_formats`, `read.formats`).
- `comicbox/config/formats.py:transform_keys_to_formats` reads
  `delete_all_tags`, `read`, `read_ignore`, `write`, `export` from
  flat keys. Needs to traverse.
- `comicbox/config/paths.py` reads `paths`, `recurse`,
  `index_from`/`index_to`, `write`, `covers`, `cbz`,
  `delete_all_tags`, `rename`, `print` from flat config / flat
  dataclass attrs.
- Most `comicbox/box/*.py` files access flat `self._config.X` keys —
  see `grep` output below for the inventory.
- `comicbox/run.py` still reads `self._config.paths` (top-level, not
  flat — this one is actually fine, paths stays at top-level).

**Will fail at module import** (none known after phase 1 sweep —
verified above).

**Tests are all broken.** Every test that constructs a config via
`Namespace` or dict mirrors the v4 flat shape. ~15 test files need
updates; mechanical search-and-replace will cover most.

## Resumption plan (phases 2-7)

### Phase 2: rewrite `cli.py` against the new shape

Argparse argument groups by taxonomy (`general`, `read`, `write`,
`print`, `convert`, `online: lookup`, `online: auth`, `online:
cache`, `online: tuning`). New flag names per the rename table in
`01-plan.md`. Short-flag whitelist (kept): `-c`, `-r`, `-n`, `-Q`,
`-j`, `-d`, `-m`, `-D`, `-p`, `-v`, `-w`. All others dropped.
Action classes (`CSVAction`, `PageRangeAction`,
`ApiPasswordAction`) — `ApiPasswordAction` becomes
`AuthPasswordAction` warning on `--auth *:pass=...` patterns.

### Phase 3: rewrite `comicbox/config/computed.py`

Traverse new nested config tree. `_ensure_cli_yaml` reads
`config["general"]["metadata_cli"]`. `_deduplicate_delete_keys`
reads `config["general"]["delete_keys"]`. `_parse_print` reads
`config["print"]["phases"]`. `_set_tagger` reads
`config["general"]["tagger"]`. `_set_computed` reads
`config["write"]["formats"]`, `config["convert"]["export_formats"]`,
`config["read"]["formats"]`.

### Phase 4: rewrite `comicbox/config/formats.py`

Update `transform_keys_to_formats` to traverse the new tree:
`config["read"]["formats"]`, `config["read"]["except"]`,
`config["write"]["formats"]`, `config["convert"]["export_formats"]`,
`config["write"]["delete_all_tags"]`.

### Phase 5: rewrite `comicbox/config/paths.py`

`clean_paths`: reads `config["paths"]` (unchanged) and
`config["general"]["recurse"]`. `_no_path_changes`: the
`_NO_PATH_ATTRS` mapping needs to be re-rooted; `getattr(settings,
attr)` must traverse (`settings.write.formats`, `settings.print.phases`,
`settings.convert.cbz`, `settings.convert.extract_covers`,
`settings.write.delete_all_tags`, `settings.convert.rename`,
`settings.convert.extract_pages_from/to`). Likely replace `_NO_PATH_ATTRS`
with explicit per-field replace() calls.

### Phase 6: sweep `comicbox/box/*.py` callers

Run `grep -rn "self._config\." comicbox/box/` and update every site.
Targets:

- `box/__init__.py`: `self._config.index_from/to`, `self._config.write`,
  `self._config.cbz`, `self._config.delete_all_tags`,
  `self._config.rename` → `general.recurse`, etc. via the new tree.
- `box/dump.py`: `self._config.write`, `self._config.cbz`,
  `self._config.delete_all_tags`, `self._config.dry_run`.
- `box/dump_files.py`: `self._config.dest_path`, `self._config.dry_run`,
  `self._config.export`.
- `box/init.py`: `self._config.loglevel`.
- `box/load.py`: `self._config.delete_keys`.
- `box/merge.py`: `self._config.replace_metadata`, `self._config.merge_order`.
- `box/metadata.py`: `self._config.delete_keys`.
- `box/print.py`: `self._config.theme`, `self._config.print` (many).
- `box/sources.py`: `self._config.metadata`, `self._config.metadata_format`,
  `self._config.read`, `self._config.metadata_cli`,
  `self._config.import_paths`, `self._config.delete_all_tags`.

### Phase 7: tests + docs

- ~15 test files need their config-construction fixtures updated.
  Search for `Namespace(comicbox=Namespace(...))` and `online=` kwargs.
- `comicbox/process.py` reads `ComicboxSettings`.
- `tests/calibration/run.py` constructs configs.
- README, online-tagging user docs, `06-api-budget-spec.md`.

### Phase 8: verify

`make fix && make lint && make ty && make test`. The full suite
should pass green.

## State of the worktree

```
M comicbox/box/online_lookup.py            (phase 1)
M comicbox/config/__init__.py              (phase 1)
M comicbox/config/settings.py              (phase 1)
M comicbox/config_default.yaml             (phase 1)
M comicbox/formats/base/online/auto_engage.py        (phase 1)
M comicbox/formats/base/online/cli_overrides.py      (phase 1)
M comicbox/formats/base/online/credentials.py        (phase 1)
M comicbox/formats/base/online/env.py                (phase 1)
M comicbox/formats/base/online/matcher.py            (phase 1)
M comicbox/formats/base/online/prompt.py             (pre-existing prompt-options work; uncommitted)
M comicbox/formats/base/online/selector.py           (pre-existing prompt-options work; uncommitted)
M comicbox/formats/base/online/series_filter.py      (phase 1)
M comicbox/formats/base/online/sources/base.py       (phase 1)
M comicbox/formats/comicvine_api/online_source.py    (phase 1)
M comicbox/formats/metron_api/online_source.py       (phase 1)
M comicbox/run.py                                    (phase 1)
M tests/unit/test_online_selector.py                 (pre-existing prompt-options work)
?? tasks/v5-config-reorg/                            (plan + this status doc)
```

Two streams of work are uncommitted:

1. The **prompt-options** session-mutation work (selector + prompt +
   online_lookup `_handle_prompt`) — feature-complete, tests green
   prior to this session. Files: `prompt.py`, `selector.py`,
   `test_online_selector.py`, plus the original additions in
   `online_lookup.py`.
2. The **v5 phase-1** refactor (everything else above).

These can be split into separate commits when ready:

- Commit 1: prompt-options (lifts selector mutation feature)
- Commit 2: v5 phase-1 scaffolding (plan doc + new dataclass tree +
  matching consumer-import fixes)
- Subsequent commits per phase (2-7) as the refactor lands.
