# Batched PromptHandler — Deferred Implementation Plan

## Status

Plan §3.4 / build-order step 8. **Protocol surface shipped; queue implementation
deferred.** This doc captures the design so it can be picked up cleanly when a
concrete consumer needs it.

## What v1 ships

`comicbox/online_session.py` now declares two `@runtime_checkable` Protocols:

- **`PromptHandler`** — the existing single-prompt callback. All in-tree code
  paths drive prompts through this.
- **`BatchedPromptHandler`** — same as `PromptHandler` plus an optional
  `request_many(prompts: Sequence[OnlinePrompt]) -> Sequence[PromptResponse]`
  method.

The engine does not yet route through `request_many`. Codex can implement either
Protocol today; only `request` is exercised.

## Why this is deferred

Three reasons it isn't worth doing the invasive surgery now:

1. **OnlineSession.tag_many is sequential.** Until a caller fans out tag()
   across threads (or the engine grows internal worker fanout), the per-session
   prompt queue would always hold ≤1 entry — there is nothing to batch.
2. **Defer mode (step 7) already solves Codex's UX problem.** When the user
   kicks off "tag online" over a library and prompts pile up,
   `defer_prompts=True` lets the batch run to completion and queues the prompts
   for a separate review UI. That review UI naturally renders all queued prompts
   together — without needing the engine to deliver them as a `request_many`
   window mid-run.
3. **Dropping `_PROMPT_LOCK` is invasive.** The class-level lock in
   `comicbox/box/online_lookup.py:235` serializes the selector callback across
   worker threads under CLI `-j N`. Replacing it with a per-session queue means
   rewriting the selector-invocation path in `_invoke_selector`, threading a
   queue through the box instance, and adding a dispatcher loop. Lots of surface
   area for a feature with no current consumer.

## When to revisit

Land the queue when one of these arrives:

- **OnlineSession grows concurrent per-file lookups.** If `tag_many` starts
  using a ThreadPoolExecutor internally for online lookups, prompts will start
  contending and a queue becomes load-bearing.
- **Series-first batching (step 9 / plan §3.10) lands.** That refactor
  consolidates "one prompt per series" into the matcher itself; the natural
  delivery shape becomes a windowed request rather than a per-issue prompt.
- **A user reports they want CLI -j N with batched prompts.** The current CLI
  behavior (one prompt at a time, serialized by `_PROMPT_LOCK`) is the right
  default for an interactive TTY, but there's a plausible "tagger UI for
  headless workers" use case.

## Implementation sketch when it's time

Roughly:

1. **Add a queue to `OnlineSession`**:
   `_pending_prompts: Queue[(prompt, Future)]` plus a dispatcher thread.
2. **Bridged selector posts to the queue instead of calling the handler
   directly.** Each worker thread blocks on its `Future` for the response.
3. **Dispatcher drains in windows.** When idle: wait for the first prompt. Once
   one arrives, drain up to N more within a small window (configurable, default
   ~50–100 ms). Hand the batch to `handler.request_many` if the handler supports
   it; otherwise call `handler.request` once per entry.
4. **Resolve futures in order, then loop.** Workers unblock with their
   responses; the bridged selector returns the `SelectorResult`.
5. **Remove `_PROMPT_LOCK` from `ComicboxOnlineLookup`.** The queue is the new
   serialization point; the class-level lock becomes dead code. Keep the CLI
   path (default `cli_selector` in `prompt.py`) on a local lock if needed to
   keep questionary readable.

## API stability

The `BatchedPromptHandler` Protocol is the public contract. The deferred work is
purely engine plumbing; no caller-visible breakage when the queue ships.
