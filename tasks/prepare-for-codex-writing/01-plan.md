# Prepare for Codex Writing — Project Plan

## Purpose

Comicbox exists to serve Codex. Codex is preparing a major revision that will:

- continue reading tags in bulk (today's hot path: importer over libraries up to
  ~600 000 comics),
- begin **writing** tags from the metadata screen — both single-comic writes and
  bulk sparse writes across thousands of comics (e.g. "rename publisher
  `Foo Comics` → `Foo`"),
- begin **online tagging** through comicbox — Metron / Comic Vine driven, with a
  UI that needs progress feedback and a human-in-the-loop prompt channel.

The current comicbox surface area is correct for read; it is **thin and
under-documented** for write and online. This project closes those gaps and also
pays down a few read-side hygiene items found along the way.

## Current Codex ↔ Comicbox boundary (ground truth)

Read so we don't propose changes that contradict how Codex actually uses us.

- **Codex owns its own frozen comicbox config**:
  `codex/settings/__init__.py:902` defines `USED_COMICBOX_FIELDS` (37 fields)
  and `_COMICBOX_DELETE_KEYS` (the complement). Field selection lives in Codex,
  not in comicbox.
- **Streaming bulk read is already in place**:
  `codex/librarian/scribe/importer/read/extract.py:230` calls
  `comicbox.process.iter_process_files()` with the frozen config, an
  `old_mtime_map` (FS-mtime pre-filter at extract.py:32), and a `full_metadata`
  flag. Worker re-checks embedded mtime; unchanged files short-circuit inside
  comicbox.
- **Codex consumes `page_count`** (envelope merge in
  `_extract_post_process_comic`, extract.py:139) and uses **all** read formats
  intentionally. A "tags-only / no-page-count" profile would break Codex; do not
  build it.
- **Codex does not hold `Comicbox` instances** during import — it receives
  dicts. (The reader view has its own `ArchiveCache`; that is separate.)
- **Codex does not write tags today and has no online-tagging UI.** Both arrive
  with this revision.

## Shared event protocol

One event dataclass family used by reads, writes, and online tagging. Symmetric
handler signature so Codex wires one callback.

```python
@dataclass
class Event:
    kind: str
    path: Path | None = None
    index: int | None = None       # 0-based, when applicable
    total: int | None = None       # may be None for generator inputs
    duration_ms: float | None = None
    error: str | None = None
    # subclass-specific fields below
```

Subclasses per workflow are listed in their sections. Delivery: each public bulk
entry point accepts `on_event: Callable[[Event], None] | None = None`, called
from worker threads (callback must be thread-safe). Iterator-style delivery may
be added later if needed.

---

## 1. Reading

### What we're keeping as-is

- `comicbox.process.iter_process_files()` — Codex already uses it; do not break
  the signature.
- The merge → normalize → compute pipeline. Codex relies on the full output.
- No `read_metadata(fields=...)`, no "tags-only" profile, no JSONL CLI mode, no
  `quick_identity()`. All rejected — Codex's field-selection lives in Codex.

### 1.1 Read hygiene (three small items)

1. **Audit `to_dict()` archive-member enumeration.** Measurement task on
   representative CB7 / CBR / large-CBZ samples. Confirm that with
   `compute.pages=False` we don't enumerate beyond what `page_count` requires.
   Page-count itself needs a filtered member listing — that stays; the goal is
   to drop any redundant `infolist()` / sort work. May be no-change; ship the
   benchmark either way.
2. **Verify `BytesIOFactory` teardown.** Confirm `_get_7zfactory()`
   (`comicbox/box/archive/read.py:76`) is released on `Comicbox.close()` and on
   worker exit paths. CB7 is rare but at 600 k files a small leak hurts.
3. **Lazy heavy imports.** `rarfile` and `py7zr` are imported in
   `comicbox/box/init.py:15` at module load. Defer to first-use. `rarfile`
   matters more (CBRs are common); `py7zr` is bonus.

### 1.2 Read event stream

Add an optional `on_event` parameter to `iter_process_files()`. Events:

```python
ReadEvent =
    | BatchStarted(total)
    | FileStarted(path)
    | FileShortCircuited(path, reason="mtime_unchanged" | "filtered")
    | FileParsed(path, duration_ms, source_count)
    | FileError(path, error)
    | BatchFinished(stats)
```

`FileShortCircuited` is the high-value event: today the embedded-mtime
short-circuit inside the worker is invisible to Codex, which sees a
`(path, None)` tuple and infers. Naming it lets the importer surface "skipped N
unchanged comics" in status without inference.

The existing `(path, result)` tuple stream is unchanged — events are additive.

---

## 2. Writing

### 2.1 `write_metadata(path, patch, *, mode, formats, dry_run)`

Public, documented single-file write. Signature:

```python
from comicbox import write_metadata

write_metadata(
    path,
    {"publisher": {"name": "Foo"}},
    mode="replace",          # "additive" | "update" | "replace" — see §2.2
    formats={"cix"},         # which on-archive formats to write
    dry_run=False,           # if True, return would-be-written payload
)
```

Behind the existing `Comicbox(...).dump()` plumbing.

### 2.2 Wire `ReplaceMerger` into the write path

The merger we need is **already implemented** in `comicbox/merge/__init__.py:33`
as `ReplaceMerger` (using `Strategy.REPLACE` from
`comicbox/merge/mergedeep.py`). It's defined but never wired into the write path
— `comicbox/box/merge.py:36` picks between `AdditiveMerger` and `UpdateMerger`
only, based on the `write.replace` bool.

The three mergers, applied to Codex's "publisher rename" — patch
`{"publisher": {"name": "Foo"}}` against existing
`{"publisher": {"name": "Foo Comics", "url": "https://foo.com", "identifiers": {...}}}`:

| Merger                                                                                                                                    | Behavior                                                                     | Result                                                           |
| ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `AdditiveMerger` (default, `Strategy.ADDITIVE`): dicts merge, lists/tuples/sets concat, **scalars at conflicting paths keep destination** | falls through to REPLACE only when types don't match a known collection pair | name does **not** change. ⚠️                                     |
| `UpdateMerger` (today's `write.replace=True`, `dict.update()` at ROOT_TAG): entire `publisher` value replaced top-level                   | publisher dict replaced wholesale                                            | name becomes `Foo`, but `url` and `identifiers` are **lost**. ⚠️ |
| `ReplaceMerger` (`Strategy.REPLACE`): recurse into dicts, **replace scalars and lists at leaves**                                         | exactly what Codex wants                                                     | `publisher.name = Foo`, `url` and `identifiers` preserved. ✅    |

`Strategy.REPLACE` replaces lists at the leaf (`_handle_merge_replace` does
`dest_parent[key] = deepcopy(source)` for any non-mapping value, see
`comicbox/merge/mergedeep.py:25`), so the earlier `Replace(...)` list sentinel
is **not needed**.

Implementation:

- Wire `ReplaceMerger` into `comicbox/box/merge.py:36`'s merger selection under
  the new `mode="replace"` value (see write mode naming below).
- Introduce `write.mode: Literal["additive", "update", "replace"]` on
  `WriteSettings`, replacing the legacy bool `write.replace`. The bool stays as
  a deprecated alias (`replace=True` → `mode="update"`, matching its current
  `UpdateMerger` behavior) with a deprecation warning. Remove in a later major
  version.
- Verify `Strategy.REPLACE` handles the cases Codex exercises (mappings of
  identifiers, list-valued M2M fields like `characters` / `genres`, `None` to
  clear a field).
- Add tests that lock in the publisher-rename behavior end-to-end: patch → read
  existing → apply ReplaceMerger → re-serialize → re-read → assert URL
  preserved, name changed.

Semantics this gives Codex (free, since they're already implemented):

- A "leaf" is a scalar, list, tuple, set, or Counter. Replaced wholesale.
- For nested dicts in the patch, recurse — siblings not in the patch are
  untouched.
- An explicit `None` clears the field.
- Keys absent from the patch are not touched in the destination.

**No pipeline-bypass optimization in v1.** The idea of patching ComicInfo.xml
directly (skip the full merge pipeline for simple leaf-replace) is a follow-up —
profile first (see 2.4), optimize only if numbers warrant.

### 2.3 `bulk_write(items, *, on_event, ...)`

```python
def bulk_write(
    items: Iterable[BulkWriteItem],   # path + patch + mode + formats
    *,
    workers: int | None = None,
    on_event: Callable[[WriteEvent], None] | None = None,
    stop_on_error: bool = False,
    cancel: CancellationToken | None = None,
) -> Iterator[BulkWriteResult]:
```

Also a `bulk_write_same(paths, patch, *, ...)` convenience for the common "same
patch, many files" shape (publisher rename).

Why a dedicated function instead of "loop + `write_metadata`":

- Owns the worker pool: writes are I/O-bound (CBZ repack), `ThreadPoolExecutor`
  is correct. Owns a global semaphore so a Codex-triggered batch can't starve
  other disk traffic.
- Owns progress events (2.5).
- Owns the cancellation token (interrupt cleanly _between_ files, not
  mid-repack).

Dry-run pairs with the existing `WriteSettings.dry_run` config option — extend
it to return the would-be-written payload so Codex can preview a 10 000-comic
rename before committing.

### 2.4 CBZ write-cost benchmark

The dominant cost of a publisher-rename batch is the per-file CBZ repack:
`_patch_zipfile()` does `zf.remove()` + `zf.repack()` (full archive rewrite) in
`comicbox/box/archive/write.py:60`. Alternative: `_create_zipfile()` (write
temp + atomic rename). Both rewrite the whole archive; the question is which is
faster in practice and whether the answer varies by archive size / image count /
compression settings.

- **Drop** the earlier "rewrite metadata in place to skip repack" idea — leaves
  dead bytes in the ZIP central directory and confuses source-of-truth.
- **Keep** always removing the previous metadata file (truth-source clarity).
- **Benchmark** `_patch_zipfile()` vs `_create_zipfile()` on a representative
  sample: small CBZ, large CBZ, many-image CBZ, sparse-metadata CBZ. Pick a
  winner per-size or across the board based on numbers.

This benchmark is a prerequisite for any Codex "rename 10 000 comics" button
being usable.

### 2.5 Write event stream

```python
WriteEvent =
    | BatchStarted(total)
    | FileStarted(path)
    | FileWritten(path, formats, duration_ms)
    | FileSkipped(path, reason="no_change" | "dry_run" | ...)
    | FileError(path, error)
    | BatchFinished(stats)
```

Same `Event` base, same handler shape as read / online.

### 2.6 Dropped

- **`validate_patch()`** — would require re-implementing schema validation
  against partial-dict shapes that marshmallow does not natively support.
  Per-file validation errors flow through the event stream instead.

### 2.7 Out of scope for write path

- CBR / CBT in-place writes — comicbox forces conversion to CBZ today
  (`write.py:185`), keep that behavior.
- PDF metadata writes — already non-destructive; no changes needed.

---

## 3. Online tagging

### 3.1 What's already right (do not redesign)

- `SelectorCallback` abstraction with rich return actions
  (`choose / skip / manual / abort / set_unattended / set_policy`) in
  `comicbox/formats/base/online/selector.py:67`.
- `MatchMode` (`ask / careful / auto / eager`) + `Prompts` (`ask / never`) in
  `comicbox/config/settings.py:32`.
- Process-wide rate limiting via SQLite buckets — automatic budget sharing
  across worker threads and processes.
- Per-source retry / backoff in `comicbox/formats/base/online/retry.py:170`.

### 3.2 Match Mode-names

Codex has no concept of matching modes today at all. Codex will use Comicbox's
match mode names.

### 3.3 `OnlineSession`

Stateful object that owns a batch:

```python
class OnlineSession:
    def __init__(
        self,
        *,
        sources: set[Literal["metron", "comicvine"]],
        credentials: dict[str, OnlineSourceCredentials],
        mode: Literal["strict", "normal", "fast"] = "normal",
        unattended: bool = False,
        prompt_handler: PromptHandler | None = None,
        on_event: Callable[[OnlineEvent], None] | None = None,
    ) -> None: ...

    def tag(self, path: Path) -> OnlineResult: ...
    def tag_many(self, paths: Iterable[Path]) -> Iterator[OnlineResult]: ...

    # Session-mutable, callable from any thread:
    def set_mode(self, mode) -> None: ...
    def set_unattended(self, unattended: bool) -> None: ...
    def cancel(self) -> None: ...

    def rate_limit_status(self) -> dict[str, RateLimitState]: ...
```

Collapses today's four-step setup (`ComicboxSettings` → `Comicbox` →
`set_online_selector()` → `run_online_lookup()`) into one stateful object that
survives across a batch and owns the rate-limit budget. Provides clean homes for
`set_mode()` / `set_unattended()` / `cancel()` which today are only reachable
via selector-action returns.

A new `WRITE_*` config constant on the Codex side will follow once
write-via-session lands — flagged so Codex can plan settings boilerplate.

### 3.4 `PromptHandler` with single + batched modes

Generalize `SelectorCallback` so it satisfies both "one at a time" and "show me
everything queued":

```python
class PromptHandler(Protocol):
    def request(self, prompt: OnlinePrompt) -> PromptResponse: ...
    # Optional: if implemented, engine releases the per-session lock and
    # queues prompts up to `batch_window_ms` before delivering.
    def request_many(self, prompts: list[OnlinePrompt]) -> list[PromptResponse]: ...
```

`OnlinePrompt` is a serializable dataclass with file path, source name,
candidate list (scores + cover-match info + source links), and current mode.
`PromptResponse` mirrors `SelectorResult` with named fields.

For batched mode to actually be useful: drop the class-level `_PROMPT_LOCK` in
`comicbox/box/online_lookup.py:235` in favor of a **per-session ordered queue**.
Workers post prompts onto the queue and await responses; the queue can be
drained one-at-a-time (default) or in windowed batches if the handler implements
`request_many`.

Opt-in initially. Default = current single-prompt behavior;
`OnlineSession(prompt_concurrency="batched")` = new behavior.

### 3.5 Online event stream

Replace polling-style `_OutcomeStats` (keep counters for end-of-run summary)
with an event stream emitted alongside the existing counter bumps in
`online_lookup.py`:

```python
OnlineEvent =
    | BatchStarted(total)
    | FileStarted(path)
    | SearchStarted(path, source)
    | SearchCompleted(path, source, n_candidates, top_score)
    | CandidatesRanked(...)
    | PromptQueued(path, prompt_id)
    | PromptResolved(path, prompt_id, action)
    | PromptResolvedFromCache(path, prompt_id, fingerprint)   # see 3.7
    | PromptDeferred(path, prompt_id, candidates)             # see 3.8
    | AutoWritten(path, source, candidate)
    | Skipped(path, reason)
    | NoMatch(path)
    | RateLimited(source, retry_after_seconds)
    | FileFinished(path, outcome)
    | BatchFinished(stats)
```

`RateLimited` is critical: people **will** try to online-tag thousands of
comics, and Codex needs to render "you are limited by source X, ETA Y" rather
than appearing frozen.

### 3.6 Rate-limit status query + cancellation

- `OnlineSession.rate_limit_status()` returns per-source
  `{capacity, remaining, reset_at}` so Codex can compute and show ETAs before a
  user clicks "tag 5 000 comics."
- `OnlineSession.cancel()` — programmatic graceful cancel: stop accepting new
  files, let in-flight per-file lookups finish, emit `BatchFinished` with
  `cancelled=True`. Today the only cancel path is `OnlineLookupAbortedError`
  from a user prompt action.

### 3.7 Prompt deduplication by fingerprint

The core problem with bulk online tagging is **prompt fatigue**: at a 30%
ambiguity rate, 1 000 comics = 300 prompts. Many of those prompts are duplicates
— when importing every issue of _Foo Comics — Bar Adventures_, the matcher asks
"which series is this?" once per issue with identical candidates each time.

Implementation:

- Build a deterministic fingerprint from the `ComicProfile`'s series-level
  fields + the sorted `Candidate` ids.
- Within an `OnlineSession`, cache `fingerprint → PromptResponse`:
    - First occurrence: dispatch to `PromptHandler`, store response.
    - Subsequent occurrences: auto-resolve from cache, emit
      `PromptResolvedFromCache`, never call the handler.
- Cache scope: per-session, in-memory by default. Optional disk persistence
  (e.g. SQLite table keyed by fingerprint) for resumable batches.

For a typical "import a publisher" batch this collapses 100× duplicate prompts
into 1. **General-purpose** — benefits CLI users too, not just Codex.

### 3.8 Defer-prompt mode

A new value on `MatchMode` (or an orthogonal flag): **`defer`**. The matcher
runs full search + ranking but instead of blocking on a prompt:

- writes auto-write candidates as it would in `auto` mode,
- emits a `PromptDeferred` event for ambiguous cases,
- records the deferred prompt in a session-owned queue,
- continues to the next file.

At end of batch, Codex receives the full queue of deferred prompts and renders a
separate "Review Tagging" UI — outside the batch run. The user is not held
hostage by a modal mid-batch.

Composes with 3.7: the deferred queue is already deduped by fingerprint.

Pairs naturally with Codex's existing async/status architecture: batch finishes,
status flips to "Done — N items need review," user comes back to resolve on
their own time.

### 3.9 Per-source enable + credential validation

Tighten the error model. If Codex passes a Metron-only batch with no Metron
credentials, fail fast with
`ConfigurationError("metron enabled but not configured: missing user/password")`
**before** opening the first archive — not log a warning per file.

### 3.10 Series-first batching — separate design doc

When a batch contains many comics from the same series, do one search per
series, prompt once, then apply the chosen `series_id` to every issue and use
cheaper per-issue lookups. This is a real refactor of the matcher and needs its
own design doc.

Mainly helps with **API rate limits**, not user attention (3.7 + 3.8 already
handle the human-attention problem). Worth doing — API limits will always be the
bottleneck for large online-tagging batches.

Tracking only; not part of this project's v1 deliverable.

---

## Build order

Numbered for execution. Each item is independently shippable.

1. **Read hygiene** (1.1) — three small items: `to_dict()` enumeration audit,
   `BytesIOFactory` teardown verification, lazy heavy imports.
2. **Shared `Event` protocol** + **read events on `iter_process_files()`**
   (1.2).
3. **`OnlineSession` skeleton** (3.3) + **online event stream** (3.5) +
   **rate-limit status query** + **cancellation** (3.6) + **credential
   validation** (3.9). Also ships the mode-name aliases (3.2).
4. **`write_metadata` / `bulk_write`** (2.1, 2.3) with **`SetMerger`** (2.2),
   **dry-run**, **write event stream** (2.5).
5. **CBZ write-cost benchmark** (2.4), then act on results.
6. **Prompt dedup by fingerprint** (3.7) — general-purpose, lands ahead of
   Codex's online UI.
7. **Defer-prompt mode** (3.8) — unblocks Codex's "review tagging" UX.
8. **`PromptHandler` batched mode** + **drop `_PROMPT_LOCK`** (3.4). Most
   invasive; opt-in.
9. **Series-first batching design doc** (3.10), then implementation if approved.

## Open questions

### Resolved

- **Disk persistence for the prompt-dedup cache** (3.7) — **not in v1.**
  In-memory per session only. Adds too much complexity for the resumable batch
  use case; revisit if real usage demands it.
- **`Replace` list sentinel** — **not needed.** `Strategy.REPLACE` already
  replaces lists at the leaf (`comicbox/merge/mergedeep.py:25`). See §2.2.
- **Merger location** — **`comicbox/merge/__init__.py`**. `AdditiveMerger`,
  `ReplaceMerger`, and `UpdateMerger` already live there.
- **Bulk-write worker pool scope** — **process-global** with a semaphore.
  Friendlier when Codex runs bulk writes concurrent with bulk reads.
- **Event handler thread context** — **invoke on worker thread.** Cheap; caller
  must be thread-safe. Document the contract.

- **Write mode naming** — **decided: `additive | update | replace`.** Maps
  one-to-one onto the existing merger classes in `comicbox/merge/__init__.py`.
  Deprecate the bool `write.replace` (kept as an alias for `mode="update"` with
  a deprecation warning; remove in a later major version). See §2.2 for the
  wiring detail.

### Still open

(none)

## Out of scope

- Anything write-related on CBR / CBT archives beyond today's force-convert
  behavior.
- New on-archive metadata formats.
- Schema changes (no fields added or renamed as part of this project).
- Codex-side UI work. This doc is the comicbox half of the contract; the Codex
  half lives in the Codex repo.
