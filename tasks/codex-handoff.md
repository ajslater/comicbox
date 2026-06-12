# Codex handoff: comicbox 4.0.0a2 review-remediation changes

For a future codex session adapting to the comicbox `pre-release` branch
(commits `d0e2197..4f1ba95`, 2026-06-11/12). Comicbox and codex ship as a
version-locked pair, so there are **no compatibility shims** — codex must
adapt at the same time it bumps. Everything below is in comicbox already;
this file lists what codex must change and what it can now rely on.

## 1. Required codex changes (will break otherwise)

### 1.1 `Comicbox(logger=...)` is gone
The constructor no longer accepts `logger=` and — more importantly — **no
longer reconfigures loguru at all**. The old behavior wiped every sink the
host app configured (`logger.remove()` on first construction); passing
`logger=` was only ever a workaround that suppressed the wipe (the
parameter itself routed nothing).

Codex call sites that pass it now raise `TypeError`. Known sites:
- `codex/views/reader/_archive_cache.py` (~166, ~188, ~207)
- `codex/views/opds/v1/entry/links.py` (~132)

**Action:** delete the `logger=logger` kwarg everywhere (grep
`Comicbox(` for `logger=`). No replacement needed — comicbox modules log
through whatever loguru sinks codex configures, including its
secret-scrubbing filter. `comicbox.logger.init_logging` still exists but
is for comicbox-owned processes only; never call it from codex.

### 1.2 Exceptions: catch `ComicboxError`
Every operational error comicbox raises on a public path now derives from
`comicbox.exceptions.ComicboxError`:

```
ComicboxError
├── UnsupportedArchiveTypeError   (bad/garbage archive)
├── ArchiveError                  (open/read failures, pathless reads)
│   └── ArchiveWriteError         (write/repack/rename failures)
├── MetadataError                 (load/routing/format-guess failures)
├── ExportError                   (file export & page-extraction guards)
├── WriteValidationError          (write_metadata input validation)
├── OnlineConfigurationError      (OnlineSession construction)
└── OnlineLookupAbortedError      (user/handler abort, cancelled retry)
```

The bare `ValueError`s formerly raised from archive/load/dump/extract
paths are now these subclasses. Historical import paths still work
(`comicbox.write.WriteValidationError`,
`comicbox.online_session.OnlineConfigurationError`,
`comicbox.box.online_lookup.OnlineLookupAbortedError`), but prefer
`comicbox.exceptions`.

**Action:** replace codex's broad `except Exception` around comicbox
calls with `except ComicboxError` where the intent is "comicbox failed
on this file" — programming errors will then surface instead of being
swallowed. `FileNotFoundError` / `IsADirectoryError` from the
constructor are unchanged (stdlib types).

### 1.3 Event dataclasses are keyword-only
All `comicbox.events` classes are `kw_only=True`. Codex consumes events
(doesn't construct them) so this mostly matters for codex tests that
build fake events positionally — `FileError("disk full")` used to
silently construct `kind="disk full"`; now it's a TypeError.

## 2. Bugs fixed that codex was exposed to (remove workarounds)

### 2.1 `bulk_write` cancellation actually works
- `stop_on_error=True` now stops the batch deterministically: submission
  happens in a bounded window behind draining, so queued files are never
  started after the first error. Previously every file ran to completion.
- A caller-supplied `cancel: threading.Event` now stops queued work
  mid-batch. **Codex's `abort_event` in
  `codex/librarian/scribe/tag_writer.py` was a near-guaranteed no-op
  before; it is real now.**
- New `WriteResult.cancelled: bool` — files that never started report
  `cancelled=True, written=False` (no per-file event is emitted for them).
- Contract: the returned generator **must be drained** to perform writes
  (submission interleaves with consumption). `BatchStarted` fires eagerly
  at call time; abandoning the iterator mid-batch no longer blocks on
  queued repacks (they're cancelled; in-flight ones finish in worker
  threads).

### 2.2 `write_metadata` round-trip no longer silently no-ops
`write_metadata(path, cb.to_dict())` used to double-wrap the root tag,
write nothing, and return `written=True`. Root-wrapped patches
(`{"comicbox": {...}}`) are now detected and unwrapped, so both shapes
work. If codex has an unwrap workaround (`.get("comicbox", ...)` before
patching), it can stay or go — both forms are correct now.

### 2.3 OnlineSession contract fixes
- **`abort` aborts the run.** A `PromptResponse(action="abort")` (or any
  `OnlineLookupAbortedError`) cancels the whole session: the aborting
  file and all remaining files come back `cancelled=True`, not errored.
  Previously abort was silently downgraded to skip-this-file.
- **`set_policy` / `set_unattended` persist.** Handler responses with
  these actions now update session state, so they apply to every
  subsequent file, as documented — not just the in-flight one.
- **`cancel()` interrupts retry sleeps.** Rate-limit recovery can sleep
  minutes per attempt; cancel() now aborts an in-flight wait instead of
  blocking until the budget plays out (the file reports cancelled).
- Config files/env are read once at session construction, not per file.

### 2.4 Retry / rate-limit reliability
- Metron's nested retry decorators are gone: worst-case multi-hour
  sleep cascades (8×8 and 8×8×8 budget multiplication) can't happen.
- Hard auth failures (`AuthenticationError`, mokkari credential
  `ApiError`), not-found ids (`LookupError`, simyan 404 `ServiceError`)
  are terminal — no more 5×-retrying a bad API key on every call.
- `online.<source>.rate_limit` overrides are now actually enforced:
  buckets are memoized per process at a stable sqlite path under the
  comicbox cache dir (previously a fresh empty temp-file bucket per call
  meant the override never limited anything).
- The upstream client (simyan/mokkari) is built once per source
  lifetime instead of per API call.

### 2.5 Cache-mode semantics
`CacheMode.REFRESH` unlinks the response cache **once per process per
path** ("discard at run start"). Previously it wiped between every API
call, destroying the +1-call-per-volume amortization. **Daemon caveat:**
in a long-lived codex process, only the first refresh-mode batch wipes;
later batches in the same process reuse the cache. If codex needs
"refresh every batch," restart the worker or ask for a per-session
refresh hook (deliberate trade-off; easy to extend).

### 2.6 Box (Comicbox instance) correctness
- `add_source`/`add_metadata` after a read now actually takes effect
  (the normalize cache used to silently swallow late additions).
- `to_dict(fmt)` computes pages/page_count under *its own* format
  context; previously the first call's format froze computed pages for
  every later call on the same instance. If codex calls `to_dict` with
  multiple formats per instance, results are now correct per call.
- The process-global marshmallow schema cache is thread-safe (the
  warning-prefix path is a ContextVar, not shared instance state) —
  relevant to codex's threaded readers.

### 2.7 Event-stream accounting
- `BatchFinished` invariant `parsed + short_circuited + errored == total`
  now holds for `iter_process_files` even when submits fail; submit
  failures carry real `index`/`total` (they were `None`/`None`).
- Write-path dry-run files emit `FileShortCircuited(reason="dry_run")`
  (new literal) instead of misusing the read-path `"filtered"`.
- Post-session-change resolutions (after `set_policy`/`set_unattended`)
  now emit `AutoWritten`/`Skipped`/`NoMatch` like every other path —
  codex's per-source outcome attribution has no silent gap.

## 3. Smaller things worth knowing

- `-f mupdf` works as a config key (the `mudpdf` typo alias remains).
- The icecream dev hook triggers on `COMICBOX_DEBUG`, not
  `PYTHONDEVMODE` — `import comicbox` no longer crashes production
  installs running dev mode.
- `comicbox.cli` is now a package; `from comicbox.cli import main` and
  the console script are unchanged. `comicbox/config/online.py` holds
  online settings assembly. `CoverHashUrlCache` lives in
  `comicbox.formats.base.online.cover_hash`. Only matters if codex
  imports comicbox internals.
- If codex ever subclasses `OnlineSource` (e.g. a GCD source): implement
  `_lookup_issue_in_volume` (the base `lookup_issue` owns failure
  semantics), use `_resolve_response_cache()` /
  `_effort_max_results()` / `_effort_name_threshold()` /
  `_log_discovery_sample()`, and set nothing up per call — `_client` is
  memoized per instance. `retry_sleep` on the instance is the
  cancellable-sleep hook (raise from it to abort).
- Source instances are still rebuilt per file; cross-file HTTP
  connection reuse is a known future improvement, not a regression.
- Format registrations are validated at import (unknown source keys,
  config-key collisions, registry drift fail fast with RuntimeError).
- The heavy online-tagging deps (imagehash→numpy/scipy) are still
  mandatory installs. Making them a `comicbox[online]` extra was
  considered and deferred because it changes codex's install line —
  decide jointly when convenient.

## 4. Suggested codex adoption checklist

1. Bump comicbox to the paired pre-release build.
2. Delete `logger=` kwargs (1.1) — required, it's a TypeError.
3. Narrow `except Exception` → `except ComicboxError` around comicbox
   calls (1.2).
4. Delete any workarounds for: bulk-write abort not working (2.1),
   root-wrapped patch unwrapping (2.2), abort-only-skips-file (2.3),
   re-tagging after `add_metadata` not sticking (2.6).
5. If codex renders write-path events: handle
   `FileShortCircuited(reason="dry_run")` and expect real indices on
   submit-failure `FileError`s (2.7).
6. If codex documents tagging behavior to users: rate-limit overrides
   now work, cancel is responsive mid-retry, and `--refresh-cache` is
   once-per-process (2.4, 2.5).
