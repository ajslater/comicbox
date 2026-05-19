# Codex Integration Handoff

This document hands off the comicbox-side work to the Codex engineering session
that will consume it. You are picking up cold — read the **Background** section
first, then jump to the workflow you're integrating.

## Background

Comicbox shipped a `codex-api` branch (14 substantive commits) that expands its
public surface for three Codex workflows:

- **Reading bulk tags** — already in production. Performance improvements are
  automatic; new optional event stream surfaces per-file progress.
- **Writing tags** — _new feature for Codex_. The metadata-screen "save" button
  and bulk-write operations (e.g., "rename publisher across 10 000 comics") both
  route through the new `write_metadata` / `bulk_write` API.
- **Online tagging** — _new feature for Codex_. Metron / ComicVine metadata
  discovery driven from Codex's UI. The new `OnlineSession` class is the entry
  point; series-first batching
    - prompt-dedup + defer mode mean a 10 000-comic batch finishes without
      drowning the user in prompts.

Source-of-truth docs on the comicbox side:

- `tasks/prepare-for-codex-writing/01-plan.md` — the full plan with every design
  decision and rejected idea.
- `02-cbz-write-benchmark.md` — write-cost numbers (1 ms / file median on a real
  15 MB CBZ).
- `03-batched-prompt-handler.md` — why `request_many` is declared but not yet
  wired.
- `04-series-first-batching.md` — series-first design + resolved questions +
  as-shipped status.

Branch: `codex-api` off `v4-alpha`. Tests: 953 passing.

## Codex ↔ comicbox state today

(Captured from the prior exploration — verify before relying on it.)

- **Read API used:** `codex.librarian.scribe.importer.read.extract.py:230` calls
  `comicbox.process.iter_process_files()` with `codex.settings.COMICBOX_CONFIG`
  (frozen), an `old_mtime_map`, and a `full_metadata` flag.
- **Field whitelist:** `codex.settings.USED_COMICBOX_FIELDS` (37 fields) +
  `_COMICBOX_DELETE_KEYS` (the complement). Codex strips unused fields at the
  boundary; comicbox does not need to know.
- **No write usage today.** No call to `Comicbox.dump()` or the new
  `write_metadata`. The cover renderer in `codex.librarian.covers.create.py`
  uses Comicbox for _page_ reads only.
- **No online-tagging usage today.** No UI surface, no calls to
  `run_online_lookup()` or `OnlineSession`.
- **Progress UI:** `codex.librarian.status_controller.StatusController` pushes
  status to the DB + websocket subscribers. Currently driven by the importer's
  own per-file `increment_complete()`.

---

## 1. Reading — optional event integration

### What changed in comicbox

- `iter_process_files()` is **drop-in compatible** — Codex's existing call needs
  no changes. The performance wins (cached-namelist derivation, BytesIOFactory
  teardown, lazy py7zr/rarfile imports) apply automatically.
- New optional `on_event=` parameter delivers a stream of typed events on the
  orchestrator thread:
    - `BatchStarted(total)`
    - `FileParsed(path, index, total)`
    - `FileShortCircuited(path, reason="mtime_unchanged" | "filtered")`
    - `FileError(path, error)`
    - `BatchFinished(total, parsed, short_circuited, errored)`

The `(path, result)` tuple stream is unchanged — events are additive.

### Why care

Today Codex infers "skipped via mtime gate" from `result["tags"] is None`. With
`FileShortCircuited` the worker tells Codex explicitly, with a `reason` field
that distinguishes the two short-circuit modes. This lets the importer's status
display surface "Skipped: 47 832 unchanged" without inference.

### Suggested Codex change

In `codex/librarian/scribe/importer/read/extract.py`, plumb an event handler
into `iter_process_files()`:

```python
def _on_comicbox_event(self, event):
    # Forward to StatusController. Cheap and thread-safe.
    if isinstance(event, BatchStarted):
        self.status.set_total(event.total)
    elif isinstance(event, FileParsed | FileShortCircuited):
        self.status.increment_complete()
    elif isinstance(event, FileError):
        self.log.warning(f"Failed to read {event.path}: {event.error}")

iter_process_files(
    paths,
    config=COMICBOX_CONFIG,
    old_mtime_map=mtime_map,
    full_metadata=full_metadata,
    on_event=self._on_comicbox_event,  # ← add this
)
```

This is optional — Codex's current `increment_complete()` call site after
`_extract_post_process_comic` works fine without it. The event-handler path is
cleaner because it survives changes to the loop structure (events fire from the
same place regardless).

### Imports

```python
from comicbox.events import (
    BatchStarted, BatchFinished,
    FileParsed, FileShortCircuited, FileError,
)
```

---

## 2. Writing — brand new feature

### What comicbox ships

```python
from comicbox.write import (
    write_metadata,         # single file
    bulk_write,             # many files, parallel
    BulkWriteItem,          # input dataclass for bulk_write
    WriteResult,            # output dataclass
    WriteValidationError,   # raised on bad inputs
)
from comicbox.config.settings import WriteMode  # additive/update/replace
```

### Single-file write — the metadata-screen "save"

```python
result = write_metadata(
    path,
    patch={"publisher": {"name": "Foo Comics"},
           "series": {"name": "Bar"}},
    mode="replace",          # see Mode semantics below
    formats={"COMIC_INFO"},  # or {"COMICBOX_JSON"} etc.; multiple OK
    dry_run=False,
)
# result.written: bool
# result.error: BaseException | None
# result.dry_run_payload: dict[str, str] | None  (serialized would-be-written, dry_run only)
```

Patch shape is the comicbox-internal dict (same shape `Comicbox.to_dict()`
returns under the `"comicbox"` root). Wrapping in `{"comicbox": ...}` is done
internally.

**Dry-run** returns the serialized would-be-written payload per requested
format, keyed by format name. Codex's "preview the change" UX rides on this.

### Bulk write — the publisher-rename UX

```python
items = [
    BulkWriteItem(
        path=p,
        patch={"publisher": {"name": "Foo"}},
        mode="replace",
        formats=frozenset({"COMIC_INFO"}),
    )
    for p in paths_to_rename
]

cancel = threading.Event()
for result in bulk_write(
    items,
    workers=8,                  # default = cap of 8 concurrent writes
    on_event=codex_event_sink,
    cancel=cancel,              # set this from the UI to stop the batch
    stop_on_error=False,        # True → first error sets cancel
):
    # Yields completion-order; not submission-order.
    record_result(result)
```

Process-global semaphore caps concurrent writes at 8 by default — CBZ writes are
I/O-bound (full archive repack) and over-parallelizing just contends on disk.
Codex can pass its own `workers` if it wants tighter control.

Events: same `BatchStarted` / `FileParsed` / `FileError` / `BatchFinished`
shapes as reading. `FileShortCircuited(reason="filtered")` fires for
`dry_run=True` items.

### Mode semantics (read carefully — the table in plan §2.2 was wrong; the actual table is here)

Patch: `{"publisher": {"name": "Foo"}}` against existing
`{"publisher": {"name": "Original", "identifiers": {"metron": {"key": "42"}}}}`.

| mode                   | Result                                                                                                                                                                                                                        |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `"additive"` (default) | `publisher.name` becomes `"Foo"`; `identifiers` preserved. (mergedeep ADDITIVE falls through to REPLACE for scalars.)                                                                                                         |
| `"update"`             | `publisher` replaced wholesale → `{"name": "Foo"}`. `identifiers` **dropped**. Top-level `.update()` semantics; siblings of replaced keys are lost.                                                                           |
| `"replace"`            | `publisher.name` becomes `"Foo"`; `identifiers` preserved. **Differs from `additive` only on list-typed fields**: ADDITIVE concats lists, REPLACE overwrites. For dict-of-dict comicbox shapes the two are indistinguishable. |

**Codex default:** `"replace"` for the publisher-rename use case — explicit
replacement of named leaves, sibling preservation. Use `"update"` only when you
intentionally want to drop everything under a top-level key.

### CBZ write performance

Median ~1 ms / file on a realistic 15 MB CBZ (see `02-cbz-write-benchmark.md`).
10 000 comics = ~10 s of pure write work. Per-file comicbox pipeline overhead
(load/normalize/merge/dump-format) will dominate the wall clock; profile that if
a 10 000-comic batch takes much longer than a minute. RAR can't be written
in-place — comicbox converts to CBZ automatically.

### Suggested Codex implementation

1. **Metadata-screen save**: single-comic call to `write_metadata`. Build the
   patch from the form diff, set `mode="replace"`, `formats={"COMIC_INFO"}` (or
   what Codex stores), call once, render result.
2. **Bulk operations** (publisher rename, etc.): launch a Celery / Huey / RQ
   task that iterates via `bulk_write()`. Stream the events into Codex's
   existing `StatusController` / websocket-subscriber stack.
3. **Cancel button** in the UI sets `cancel.set()` (you'll need to wire the
   `threading.Event` into the worker's task context).

---

## 3. Online tagging — brand new feature

### Mental model

`OnlineSession` is a stateful per-batch object. Codex constructs it with the
user's credentials + preferences, then calls `tag(path)` / `tag_many(paths)`.
The session owns:

- Mode + unattended + cancel state (settable mid-batch via setters).
- A per-session **prompt dedup cache** (keyed by series fingerprint
    - candidate volume_ids).
- A per-session **series cache** for series-first batching (one search per
  series, then `lookup_issue` for each issue).
- A **deferred-prompts queue** (when `defer_prompts=True`, ambiguous prompts
  pile up here instead of blocking the batch).

### Construction

```python
from comicbox.online_session import (
    OnlineSession, OnlineCredentials,
    PromptHandler, OnlinePrompt, PromptResponse,
    OnlineResult, DeferredPrompt,
    OnlineConfigurationError,
)

creds = OnlineCredentials(
    metron_user="…",      # only required if "metron" in sources
    metron_password="…",
    comicvine_key="…",    # only required if "comicvine" in sources
)

session = OnlineSession(
    sources={"metron", "comicvine"},
    credentials=creds,
    mode="normal",          # "strict" | "normal" | "fast"
    unattended=False,
    prompt_handler=MyCodexHandler(),  # implements .request()
    on_event=codex_event_sink,
    defer_prompts=False,    # True for the "tag library, review later" UX
    series_batching=True,   # default — keep it on
)
```

`OnlineConfigurationError` raises at construction time on:

- Unknown source name
- Empty sources
- Enabled source missing required credentials
- Unknown mode value

### Mode aliases

Codex's UI vocabulary maps onto the internal enums:

| Codex UI | OnlineSession `mode` | Internal `MatchMode` | Notes                                              |
| -------- | -------------------- | -------------------- | -------------------------------------------------- |
| Strict   | `"strict"`           | `CAREFUL`            | Auto-write only on unambiguous top                 |
| Normal   | `"normal"`           | `AUTO`               | Auto-write on unambiguous or solo viable (default) |
| Fast     | `"fast"`             | `EAGER`              | Auto-write on anything > min_confidence            |

`unattended=True` separately maps to `Prompts.NEVER` — no prompts ever fire;
ambiguous matches just skip.

### Tagging

```python
# Single file
result: OnlineResult = session.tag(path)
# result.tags: dict[str, Any] | None  (populated comicbox-shaped dict)
# result.error: BaseException | None
# result.cancelled: bool

# Many files — completion order is INPUT order (sequential), but paths
# are pre-sorted by filename-derived series fingerprint so same-series
# clusters together — the first issue of each series fires the cold-path
# search and populates the cache; subsequent issues hit lookup_issue
# and skip the search.
for result in session.tag_many(paths):
    save_to_codex_db(result)
```

### Implementing `PromptHandler` for Codex UI

```python
class CodexPromptHandler:
    """Connects comicbox's matcher to Codex's websocket+modal flow."""

    def __init__(self, codex_session_id):
        self.codex_session_id = codex_session_id

    def request(self, prompt: OnlinePrompt) -> PromptResponse:
        # 1. Push prompt to Codex's websocket queue for this session.
        # 2. Block on user's response (with timeout / cancel).
        # 3. Translate the UI response into PromptResponse.
        ui_response = await_user_decision(self.codex_session_id, prompt)
        return PromptResponse(
            action="choose",       # or "skip" / "manual" / "abort"
                                   #  / "set_unattended" / "set_policy"
            payload=ui_response.candidate_index,  # int for choose
        )
```

`OnlinePrompt` exposes `path`, `source`, `profile_summary`,
`candidates: tuple[Candidate, ...]`, `mode`, `unattended`. Render candidates by
`summary.series / issue / year / publisher` etc.

### Events

Subscribe via `on_event`. Online events Codex should render:

- `SearchStarted(path, source)` /
  `SearchCompleted(path, source, n_candidates, top_score)`
- `AutoWritten(path, source, candidate_summary)` — matcher accepted without
  prompting
- `SeriesIdentified(path, source, series_fingerprint, volume_id)` — fires once
  per series; "we resolved Spider-Man → Metron vol 5678"
- `PromptQueued` / `PromptResolved` — the prompt round-trip
- `PromptResolvedFromCache(action, fingerprint)` — fingerprint matched the
  per-session dedup cache; no user prompt fired
- `PromptDeferred(prompt_id, fingerprint, n_candidates)` — defer mode queued
  this; user will resolve later
- `Skipped(path, source, reason)` / `NoMatch(path, source)`
- `RateLimited(source, retry_after_seconds)` — _important_: tell users the ETA
  so they don't think Codex is frozen
- `FileFinished(path, outcome)` — "written" or "no_change"

### Defer mode for Codex's review-tagging UX

The intended Codex flow for large library imports:

```python
session = OnlineSession(..., defer_prompts=True)

# Run to completion — no blocking prompts.
for result in session.tag_many(library_paths):
    record_result(result)

# Drain queued prompts for the review UI.
deferred: tuple[DeferredPrompt, ...] = session.deferred_prompts()
# Each: path, source, fingerprint, profile_summary, candidates, mode, unattended

# Codex renders review screen. User resolves N prompts.
# For each resolution, seed the cache:
for d, user_choice in resolved:
    session.preload_resolution(
        d.fingerprint,
        action="choose",
        payload=user_choice.candidate_index,
        chosen_volume_id=d.candidates[user_choice.candidate_index].volume_id,
    )

# Toggle defer off and re-run only the previously-deferred files.
session.set_defer_prompts(defer=False)
revisit_paths = [d.path for d in deferred]
for result in session.tag_many(revisit_paths):
    # Cache hits resolve everything; no prompts fire.
    record_result(result)
```

### Cross-run series-cache persistence (optional but recommended)

```python
# At end-of-batch, snapshot the resolved series for storage in Codex's DB:
snapshot: dict[tuple[str, str], int] = session.series_cache_snapshot()
# Each entry: (source_name, series_fingerprint) → volume_id

# Next session: replay before any tagging.
for (source, fp), volume_id in stored_resolutions.items():
    new_session.preload_series_resolution(
        source=source, series_fingerprint=fp, volume_id=volume_id,
    )
# Now the cold-path search is skipped for known series even on the
# very first comic of that series in this run.
```

### Cancellation + state mutation

```python
session.cancel()                      # stops tag_many between files
session.set_mode("fast")              # mode changes apply to next file
session.set_unattended(unattended=True)  # ditto
session.rate_limit_status()           # v1 stub: returns {source: {}}
```

### API rate-limit notes

- **Metron**: 20 req/min, 5 000/day. With series-first batching, a 50-series /
  10 000-comic batch costs ~50 cold searches + ~10 000 lookup_issue calls. The
  lookup_issue path is single-request and unambiguous, so it processes faster
  than the multi-request fuzzy search.
- **ComicVine**: 1 req/sec, 200/hr. The hourly cap is the binding constraint for
  big batches. Surface this in the UI via `RateLimited` events.

### Future-facing protocol: `BatchedPromptHandler`

Codex can also implement `BatchedPromptHandler` (with both `request()` and
`request_many(prompts)`). v1 only invokes `request()`; `request_many` is
reserved for a future per-session prompt queue (see
`03-batched-prompt-handler.md`). Wiring this in on the Codex side now is fine —
when comicbox lights it up, no Codex changes needed.

---

## Public-symbol cheat sheet

```python
# Reading
from comicbox.process import iter_process_files, process_files, ReadResult
from comicbox.events import (
    BatchStarted, BatchFinished,
    FileParsed, FileShortCircuited, FileError,
    Event, EventHandler,
)

# Writing
from comicbox.write import (
    write_metadata, bulk_write,
    BulkWriteItem, WriteResult,
    WriteValidationError,
)
from comicbox.config.settings import WriteMode  # additive | update | replace

# Online tagging
from comicbox.online_session import (
    OnlineSession,
    OnlineCredentials, OnlinePrompt, PromptResponse, OnlineResult,
    DeferredPrompt,
    PromptHandler, BatchedPromptHandler,  # protocols
    OnlineConfigurationError,
)
from comicbox.events import (
    SearchStarted, SearchCompleted,
    AutoWritten, SeriesIdentified,
    PromptQueued, PromptResolved, PromptResolvedFromCache, PromptDeferred,
    Skipped, NoMatch, RateLimited, FileFinished,
)
```

## Suggested implementation order for the Codex session

1. **Read-side event integration** (smallest delta, lowest risk). Plumb
   `on_event` into `iter_process_files`, surface `FileShortCircuited` reasons in
   the importer status.
2. **Metadata-screen save** with `write_metadata`. Per-comic, no bulk yet — get
   the round-trip working.
3. **Bulk-write background task** for "rename publisher" etc. Reuse Codex's
   existing task-orchestration infra; events drive the UI.
4. **OnlineSession plumbing without prompts**: `mode="normal"` +
   `unattended=True` first. Tag a few comics end-to-end with auto-write only.
   Validate events, error paths, credentials.
5. **PromptHandler + interactive UI**. Modal or queue. Resolve a real ambiguous
   match.
6. **Defer mode + review-tagging screen**. The big-batch UX.
7. **Series-cache persistence**. Snapshot + preload across sessions.

## Open questions for the Codex session

These are decisions I had no business making on the comicbox side:

- **Where does Codex store the user's Metron/CV credentials?** New Django admin?
  Environment variables? Encrypted DB? Keyring? The shape of the UI for this is
  Codex's call.
- **How does Codex represent a "session" of online tagging?** A Django model?
  In-memory only for the user's browser session? The defer-prompts review screen
  presumes the session outlives the initial batch.
- **What happens to comics tagged by an aborted batch?** Roll back? Leave
  partial? Codex DB transaction strategy is independent of comicbox.
- **Should the metadata-screen "save" be optimistic-update or
  request-response?** `write_metadata` is synchronous and ~tens of milliseconds;
  either pattern works.
- **Bulk-write progress UI**: re-use the importer's existing `StatusController`
  rendering, or a new "operation in progress" surface? Probably the same.

## Files to start at on the comicbox side

If you need to see how something works internally:

- `comicbox/online_session.py` — the entire session API surface.
- `comicbox/write.py` — write_metadata + bulk_write.
- `comicbox/events.py` — all event dataclasses.
- `comicbox/box/online_lookup.py` — internal matcher + warm/cold path logic.
- `comicbox/formats/base/online/sources/base.py` — OnlineSource ABC (where
  `lookup_issue` lives).

If you need to see how comicbox tests these, look in:

- `tests/unit/test_online_session.py`
- `tests/unit/test_online_events.py`
- `tests/unit/test_prompt_dedup.py`
- `tests/unit/test_defer_prompts.py`
- `tests/unit/test_series_cache.py`
- `tests/unit/test_session_series_batching.py`
- `tests/unit/test_write_api.py`
- `tests/unit/test_read_events.py`

Good luck.
