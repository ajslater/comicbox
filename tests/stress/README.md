# M7 Stress-test Harness

Validates parallel batch processing (`-j N`) under live-API load. Three
harnesses, each answering one piece of the M7 acceptance gate in
[`tasks/online-tagging/TODO.md`](../../tasks/online-tagging/TODO.md) section 2:

- **`run.py`** (`make stress`) — rate-limiter compliance + no exceptions under
  parallel load. Uses `--unattended` so prompts become SKIPs.
- **`prompt_ux.py`** (`make stress-prompt-ux`) — prompt serialisation under
  contention. Uses `--policy always-prompt --force-search` + a monkeypatched
  recording selector that simulates user think-time.
- **`jobs_accuracy.py`** (`make stress-jobs-accuracy`) — does parallelism change
  the matcher's per-fixture decision vs the serial path? Drives `cli.main()`
  in-process with a monkeypatched recording hook on `_accept_candidate`; diffs
  jobs=N outcomes vs jobs=1 as the baseline.

None of these is part of the regular test suite — all hit live Metron and
ComicVine APIs, require credentials, and take minutes to run. Run them manually
before declaring an M7-touching change shipped.

## `run.py` — rate-limiter compliance

### What `run.py` measures

| Signal                                  | Source                                                                                                 |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Wall time                               | `time.monotonic()` around the subprocess                                                               |
| Per-source upstream requests            | sqlite cache-row delta (response cache: 1 row per cached upstream response = 1 cache miss = 1 request) |
| Observed request rate vs documented cap | computed; flags >5% over cap as FAIL                                                                   |
| Rate-limit retries                      | parsed from `retry.py` INFO log lines                                                                  |
| Exceptions                              | parsed from log (traceback markers)                                                                    |

### What `run.py` doesn't measure

- **Prompt-lock contention.** `--unattended` makes the matcher SKIP instead of
  prompting → `_PROMPT_LOCK` is never acquired. Covered by `prompt_ux.py`
  instead.
- **Per-worker wall-time distribution.** Possible by parsing per-file log lines
  but the existing log format makes this brittle; skipped for now.

## `prompt_ux.py` — prompt serialisation

### What `prompt_ux.py` measures

| Signal                           | Source                                    |
| -------------------------------- | ----------------------------------------- |
| Selector entry/exit timestamps   | recorded by a monkeypatched stub selector |
| Overlapping intervals            | `detect_overlaps` over the timestamp list |
| Distinct worker threads observed | `threading.get_ident()` per call          |
| Wall time vs serialised baseline | `N_prompts × think_time` as lower bound   |

### How `prompt_ux.py` works

Drives `comicbox.cli.main(argv)` in-process (NOT via subprocess) so it can
monkeypatch `comicbox.box.online_lookup.cli_selector` for the run's duration.
The patched selector sleeps `--think-time` seconds (simulating user think-time),
records the event, and returns `("skip", None)` — no archive writes happen.

The real `Runner._run_parallel` runs the ThreadPoolExecutor + the
`_PROMPT_LOCK`-protected selector path end-to-end.

### What `prompt_ux.py` doesn't measure

- **Real user think-time variability.** Fixed think-time is uniform; real users
  take 1-30+ seconds. The lock is fair regardless, but UX considerations like
  "show progress for queued workers" aren't empirically tested here.
- **The `questionary` TTY interaction.** The recording selector bypasses the
  actual prompt rendering. Manual smoke run with the real `cli_selector` in a
  TTY is still worth doing before declaring 4.0.0 fully shipped.

## `jobs_accuracy.py` — does parallelism change matcher decisions

### What `jobs_accuracy.py` measures

| Signal                              | Source                                              |
| ----------------------------------- | --------------------------------------------------- |
| Per-fixture chosen Metron id        | recorded via monkeypatched `_accept_candidate` hook |
| Per-fixture decision diff vs jobs=1 | computed across the chosen-id dicts                 |
| Decided vs SKIPPED counts           | per jobs value, from the chosen dict                |
| Wall time + Metron cache-row delta  | per jobs value                                      |

### How `jobs_accuracy.py` works

Same in-process pattern as `prompt_ux.py`: drives `comicbox.cli.main(argv)` and
monkeypatches `ComicboxOnlineLookup._accept_candidate` to record
`(path, source, issue_id)` before calling the original. The patch hooks into the
matcher's actual auto-write decision point — robust under heavy -j N log
interleaving (a prior subprocess-based iteration broke under -j 8 and only
caught 2 of 39 actual auto-writes).

Targets Metron only (the contention-prone source per 2026-05-15-stress-100).
Uses `--force-search` so fixtures with stored Metron IDs still go through the
matcher path (without it, the explicit-id shortcut skips search entirely → -j is
moot). Use `--threshold 0.50` to force decisions when the labeled fixture set is
too thin for auto-writes to land naturally at the production 0.95 default.

### What `jobs_accuracy.py` doesn't measure

- **Absolute correctness.** Uses jobs=1 as the baseline, not labels. Tells you
  "did -j N change the answer?" not "is jobs=N's answer right?". The labeled
  fixture set in `tests/calibration/fixtures-jobs.json` is CV-only-tagged so we
  can't measure absolute Metron accuracy without bootstrapping a Metron-tagged
  set first.
- **ComicVine source path.** Metron-only by current design. CV's hourly cap
  makes a CV-source sweep expensive and the cap dynamics haven't been a problem
  on CV per the production stress data.

## Setup

Same as the calibration harness:

```yaml
# ~/.config/comicbox/config.yaml
comicbox:
    online:
        metron:
            username: your_metron_user
            password: your_metron_password
        comicvine:
            api_key: your_cv_api_key
```

Or env vars (`COMICBOX_METRON_USERNAME`, etc.).

## Running

```sh
# Rate-limiter compliance: 10 fixtures, warm cache, jobs=4
uv run python -m tests.stress.run ~/Milliways/Comics/Test \
    --limit 10 --jobs 4 --no-wipe-cache

# Rate-limiter compliance: ~50 fixtures, cold cache, jobs=8 (the M7 spec'd test)
uv run python -m tests.stress.run /path/to/fixtures --limit 50 --jobs 8

# Single source only (cheap iteration)
uv run python -m tests.stress.run /path/to/fixtures --sources metron --limit 50

# Prompt-UX: 16 fixtures, jobs=8, 0.5s think-time per prompt
uv run python -m tests.stress.prompt_ux /path/to/fixtures \
    --limit 16 --jobs 8 --think-time 0.5

# Jobs-accuracy: 50 fixtures × jobs=1,4,8 cold cache, threshold 0.50
uv run python -m tests.stress.jobs_accuracy \
    tests/calibration/fixtures-jobs.json \
    --jobs 1,4,8 --limit 50 --threshold 0.5
```

Makefile shortcuts: `make stress`, `make stress-prompt-ux`, and
`make stress-jobs-accuracy`. All respect `STRESS_PATH`, `STRESS_LIMIT`,
`STRESS_JOBS` overrides; `stress-jobs-accuracy` also takes
`STRESS_FIXTURES_JSON`, `STRESS_JOBS_VALUES`, `STRESS_THRESHOLD`.

The harness is **read-only against your archives** — always passes `-n`
(dry-run) to comicbox. No tag writes.

The harness is **destructive to the sqlite response caches** under
`~/Library/Caches/comicbox/online/` when the default cache wipe runs. Re-warming
the caches takes a long time on the next non-stress run — fine for a stress
test, surprising in other contexts. Pass `--no-wipe-cache` to skip the wipe.

## Output

Each run writes:

- `tests/stress/output/run-<timestamp>.log` — full subprocess stdout
    - stderr capture
- `tests/stress/output/SUMMARY.md` — overwritten each run; the latest result is
  always at this path

The summary markdown is also printed to stdout.

## Pass criteria

A run PASSes when:

- comicbox exits with status 0
- No tracebacks appear in the log
- No per-source request rate exceeds its documented cap (Metron 20/min,
  ComicVine 60/min and 200/hr) by more than 5%

Failures are listed explicitly in the summary's "Pass/fail" section.

## Interpreting the request-rate row

The observed rate is computed as `(new cache rows) / (wall seconds) × 60`. For a
cold-cache run where every request is a cache miss, this is the real
upstream-request rate. For a warm-cache run it under-counts (cache hits don't
add rows) — which is fine for the "did the limiter hold?" question because cache
hits never hit the limiter.

The "Status" column:

- `OK` — observed rate within 5% of the documented per-minute cap.
- `OVER (X/min vs Y)` — exceeded the per-minute cap. Investigate whether
  mokkari/simyan's `pyrate_limiter` bucket is misconfigured or whether parallel
  workers aren't sharing the limiter correctly.
- `OVER hourly (X/hr vs Y)` — same for ComicVine's hourly cap.

Rate-limit retries in the metrics section are a SEPARATE signal: even a passing
run may show retries if the in-process limiter and the server's enforcement
disagree slightly (clock skew, request-coalescing in the proxy, etc.). A pile of
retries + a passing rate check is fine; zero retries + a failing rate check is
the alarming combination.

## Limit & jobs sizing

| Goal                        | Suggested                                             |
| --------------------------- | ----------------------------------------------------- |
| Validate harness end-to-end | `--limit 5 --jobs 2 --no-wipe-cache`                  |
| M7 acceptance gate          | `--limit 50` to `--limit 100`, `--jobs 8`, cold cache |
| Investigate a regression    | `--limit 30`, `--jobs 8`, cold cache, single source   |

`--jobs 8` is the spec'd target. Higher (`-j 16`) tends to be no faster than
`-j 8` because both libraries' rate limiters serialise into the same
process-wide bucket — extra threads just queue.
