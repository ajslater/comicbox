# CLI Flag-by-Flag Comparison: comictagger / metron-tagger / comicbox

Settings-file-only options noted in parens. comictagger settings live at
`~/.ComicTagger/settings`; metron-tagger reads an INI with `[metron]`
(user/password), `[rename]` (rename_template/issue_padding/smart_cleanup), and
`[sort]` (directory).

| Concept                         | comictagger                             | metron-tagger                           | comicbox today                              | Recommendation                                                                      |
| ------------------------------- | --------------------------------------- | --------------------------------------- | ------------------------------------------- | ----------------------------------------------------------------------------------- |
| **Online lookup enable**        | `-o`, `--online`                        | `-o`, `--online`                        | none                                        | **adopt** `-o`/`--online`                                                           |
| **Source selection**            | hardcoded ComicVine; (`cv_url`)         | hardcoded Metron                        | n/a                                         | **adopt** new `--source metron,comicvine`; design pluggable from start              |
| **ID-based exact match**        | `--id ISSUE_ID`                         | `--id ID` (issue or series)             | none                                        | **adopt** `--id <source>:<id>` (qualified for multi-source)                         |
| **Interactive disambiguation**  | `-i`, `--interactive`                   | (default; opt out via flags)            | n/a                                         | **adopt** `-i`; make it the default like metron-tagger                              |
| **Auto-accept single match**    | (implicit when not `-i`)                | `--accept-only`                         | n/a                                         | **adopt** `--accept-only`                                                           |
| **Skip multi-match files**      | none                                    | `--skip-multiple`                       | n/a                                         | **adopt** `--skip-multiple`                                                         |
| **Preserve existing tags**      | `--no-overwrite`                        | `--ignore-existing`                     | none (`-R`/`--replace-metadata` is inverse) | **adopt** `--ignore-existing` (clearer name)                                        |
| **Force-overwrite all**         | `--overwrite`                           | n/a                                     | `-R`/`--replace-metadata`                   | **keep** `-R`; document for online use                                              |
| **Save on low confidence**      | `--noabort`; (`save_on_low_confidence`) | n/a                                     | n/a                                         | **defer** — pick one policy, don't expose                                           |
| **Auto-imprint normalization**  | `-a`/`--auto-imprint`                   | n/a                                     | n/a                                         | **defer** — normalization concern                                                   |
| **API key (CLI)**               | `--cv-api-key`, `--only-set-cv-key`     | none                                    | none                                        | **adopt** `--api-key <source>:<key>`; **skip** `--only-set-cv-key`                  |
| **API key (config)**            | `cv_api_key`                            | INI user+password                       | n/a                                         | **adopt** per-source keys/env-vars; **skip** plaintext passwords                    |
| **Custom API URL**              | `--cv-url`                              | n/a                                     | n/a                                         | **adopt** `--api-url <source>:<url>` (self-hosted Metron)                           |
| **Cache (path/TTL/bust)**       | none                                    | none                                    | n/a                                         | **adopt** `--cache-dir`, `--cache-ttl`, `--no-cache`, `--refresh-cache`             |
| **Wait on rate limit**          | `-w`/`--wait-on-cv-rate-limit`          | none                                    | n/a                                         | **adopt as default** with backoff (no flag)                                         |
| **Recursion**                   | `-R`, `--recursive`                     | implicit on folder paths                | `--recurse`                                 | **rename** to `-r`/`--recurse` (comicbox's `-R` collides with `--replace-metadata`) |
| **Filename parsing for hints**  | `-f`, `--parse-filename`                | always-on                               | always-on (filename source)                 | **keep** comicbox's behavior                                                        |
| **Word splitting**              | `--split-words`                         | n/a                                     | n/a                                         | **defer** — push into comicfn2dict                                                  |
| **Verbose / terse / nosummary** | `-v`, `--terse`, `--nosummary`          | none                                    | `-Q`/`--quiet` (count)                      | **keep** `-Q`; **adopt** `-v`; **skip** `--nosummary`                               |
| **Dry-run / no-write**          | `-n`, `--dryrun`                        | none                                    | `-y`, `--dry-run`                           | **rename** comicbox short flag to `-n` (`-y` conventionally means "yes")            |
| **Rename**                      | `-r`, `--rename`                        | `-r`, `--rename`                        | `--rename`                                  | out of scope for online tagging                                                     |
| **Sort/move**                   | (`rename_dir`, `rename_move_dir`)       | `-s`, `--sort`                          | n/a                                         | out of scope                                                                        |
| **Format conversion**           | `-e`, `--delete-rar`                    | `-z`, `--delete-original`               | `-z`/`--cbz`, `--delete-orig`               | out of scope; comicbox already richer                                               |
| **Metadata write target**       | `-t {CR,CBL,COMET}`                     | `-m`/`--metroninfo`, `-c`/`--comicinfo` | `-w FORMATS` (csv)                          | **keep** `-w` — already richer than both                                            |
| **Validation**                  | none                                    | `--validate`, `--remove-non-valid`      | `-V`/`--validate`                           | **keep**; **defer** `--remove-non-valid` (destructive)                              |
| **CIX→MIX migrate**             | none                                    | `--migrate`                             | covered by `-w mix`                         | **skip** — already covered                                                          |
| **Missing-tag listing**         | none                                    | `--missing`                             | none                                        | **defer** — small UX win                                                            |
| **Duplicate-page detection**    | none                                    | `--duplicates`, `--quick-duplicates`    | none                                        | **skip** — unrelated                                                                |
| **Batch / parallel**            | none                                    | none                                    | none                                        | **defer** — design for it; ship serial                                              |
| **Custom scripts**              | `-S`/`--script`                         | none                                    | none                                        | **skip** — comicbox is library-first                                                |
| **GUI / dark mode**             | `--darkmode`                            | n/a                                     | n/a                                         | **skip**                                                                            |

## Notable gaps in comicbox today

- **No online lookup at all** — the entire feature being designed.
- **No `--ignore-existing` mode.** `--replace-metadata` is the only knob and
  it's binary; bulk runs need a "skip already-tagged" mode.
- **No `--id` for exact-match tagging** when filename parsing is unreliable.
- **No disambiguation hook.** The library API needs a callback so CLI and codex
  can prompt differently.
- **No credential management** — no config schema, env-var convention, or flag.
- **No HTTP cache.** Re-runs after edits should not re-hit the API.
- **No rate-limit / retry handling.**
- **No source-selection mechanism.** Architect for multiple sources (Metron,
  ComicVine, GCD) from day one.
- **No `--accept-only` / `--skip-multiple`** for unattended bulk runs.

## Choices we should NOT adopt

- **Plaintext passwords in config.** metron-tagger stores user+password in INI.
  Require API tokens, env vars, or keyring; never log credentials.
- **Opt-in rate-limit waiting.** comictagger's `-w` makes hard-fail the default
  and punishes well-behaved users. Backoff should be always-on, opt-out for
  tests.
- **GUI state in settings file.** comictagger mixes prefs with window geometry,
  install IDs, last-folder paths. Keep comicbox's config user-meaningful only.
- **`--only-set-cv-key` mode** — a whole CLI verb to set one value is
  over-engineered.
- **`-S`/`--script` arbitrary Python.** Attack surface and maintenance burden;
  users should import the library.
- **Hardcoded single source.** Both prior tools bake in one provider; design
  pluggable from the start.
- **Confusing inverse pairs.** `--no-overwrite` vs `--overwrite` (comictagger)
  is easy to misread. Prefer `--ignore-existing`.
- **Two-axis confidence config** (`--noabort` flag + `save_on_low_confidence`
  setting). Pick one policy.
- **`-y` for dry-run** (comicbox today). `-y` means "yes" in Unix; rename to
  `-n`.
- **`--abort-on-conflict` for filename collisions.** If adopted, scope to
  tag-write conflicts only.
