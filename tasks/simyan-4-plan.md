# simyan 4.0.0 adoption plan

**Status:** plan only, awaiting go-ahead. Branch for the work: `simyan-4` off
`develop`; PR against `develop`. No version bump — NEWS lines go under the
existing `v5.0.0` section.

## Where we are

- `pyproject.toml` already requires `simyan>=4.0.0,<5` and `uv.lock` resolves
  4.0.0 (commit `fbcaa26`, 2026-09-03). That commit touched only the lock files.
- Under 4.0.0 the 111 tests in `test_comicvine.py`, `test_comicvine_client.py`,
  `test_online_abort_propagation.py` and `test_rich_transforms.py` pass
  unchanged. Nothing is broken.
- The code, comments, warnings and test names still describe simyan 3.x
  behaviour, and two pieces of defensive code exist only because of 3.x quirks
  that 4.0.0 removed.

## What changed, 3.1.0 → 4.0.0

Verified by diffing the installed 4.0.0 wheel against a downloaded 3.1.0
(`git diff --no-index`), and by the GitHub release notes for tag `4.0.0`.

| #   | Change                                                                                                                                                                                                                                                                                                       | Effect on comicbox                                                                                                                                                                                                                                                                                        |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `_request` now inspects the JSON body. `status_code != 1` raises `AuthenticationError` (CV 100 "Invalid API Key"), `RateLimitError` (CV 107 "Rate Limit Exceeded"), else `ServiceError(body["error"])` (101 "Object Not Found", 102 "Error in URL Format", 104 "Filter Error"). Raised before pydantic runs. | Under 3.x these HTTP-200 error bodies died inside pydantic as a `ServiceError` wrapping a `ValidationError`. Comicbox sniffed "rate limit" in that message to catch 107; an invalid key was classified TRANSIENT and retried five times (~31 s) before failing.                                           |
| 2   | `cache_control=cache_expiry != NEVER_EXPIRE` dropped from the session constructor.                                                                                                                                                                                                                           | Comic Vine's response cache headers no longer override `cache_expiry`; comicbox's `online.cache.ttl` now fully governs. `DO_NOT_CACHE` alone skips reads **and** writes (requests-cache 1.3.3 `update_from_response`, "disabled by expiration" criterion). The `settings.disabled` reach-in is redundant. |
| 3   | `ComicvineResource` enum removed; `simyan.resources` module with a `Resource` dataclass and `ISSUE`, `VOLUME`, … constants added.                                                                                                                                                                            | Unused by comicbox.                                                                                                                                                                                                                                                                                       |
| 4   | Deprecated generic `search()` removed.                                                                                                                                                                                                                                                                       | Comicbox has used `search_volumes()` since 3.1.0.                                                                                                                                                                                                                                                         |
| 5   | `BasicCreator.date_of_death` is a `TimezonedDate`.                                                                                                                                                                                                                                                           | Comicbox never fetches creators.                                                                                                                                                                                                                                                                          |
| 6   | Endpoint strings now come from `Resource` with a trailing slash.                                                                                                                                                                                                                                             | Resulting URLs are byte-identical to 3.x, so existing `comicvine_cache.sqlite` rows stay valid. Bucket names (`search`, `volumes`, `issues`, `get_issue`, `get_volume`) are unchanged.                                                                                                                    |
| 7   | Unchanged: 1/s and 200/h per-bucket limits, `max_delay = 2 × timeout = 40 s`, the `Timeout("Rate limit not cleared within max_delay=…")` cause, `ignored_parameters=["api_key"]`, `Issue`/`Volume` schemas, the pagination helpers.                                                                          | Retry cause-sniffing, api-key redaction, the transform and the estimator constants all still apply.                                                                                                                                                                                                       |

Dependency floors moved to pydantic ≥ 2.13, requests-cache ≥ 1.3,
requests-ratelimiter ≥ 0.10, requests ≥ 2.34. Already satisfied by `uv.lock`.

## Findings that shape the plan

### A. Error classification has dead and mis-tuned branches

`_classify_service_error` in `comicbox/formats/comicvine_api/online_source.py`:

- The final `"rate limit" in str(exc).lower()` fallback is dead: 107 now arrives
  as a typed `RateLimitError`.
- "Object Not Found" (CV 101) already lands on NOT_FOUND through the literal
  `"not found"` check, but the comment claims the only literal is "Resource not
  found".
- "Error in URL Format" / "Filter Error" (CV 102/104) become `ServiceError` →
  TRANSIENT → five retries. They are programmer errors and should raise
  immediately, like the `_NON_RETRIABLE` tuple in `retry.py`.
- The `Timeout("Rate limit not cleared…")` cause sniff and
  `_service_error_status` (HTTPError path) are still the only signal for their
  cases and stay.

### B. Cache OFF no longer needs a private reach-in

`_disable_response_cache` sets `client._session.settings.disabled = True`
because 3.x's `cache_control=True` let header-driven expiry write anyway. With
`cache_control` gone, `cache_expiry=DO_NOT_CACHE` is sufficient.

### C. Hidden 2× pagination cost (pre-existing; fix belongs upstream)

Measured with a fake `_request` transport against the installed 4.0.0:

| Call                                                   | Results | HTTP requests |
| ------------------------------------------------------ | ------- | ------------- |
| `list_issues(filter=volume+issue_number)`              | 2       | **2**         |
| `list_issues(...)`                                     | 0       | 1             |
| `list_volumes(filter=name+start_year, max_results=20)` | 3       | **2**         |
| `search_volumes(max_results=20)`                       | 7       | **2**         |
| `search_volumes(max_results=20)`                       | 50      | **2**         |
| `search_volumes(max_results=5)`                        | 50      | 1             |

Cause: `Comicvine._offset` loops until it receives an empty page rather than
stopping when a page is short (or when
`offset + limit >= number_of_total_results`, which every CV response carries).
`_search` never sends `limit`, so CV's `/search/` default page size of 10 forces
a second page for `max_results=20`. The same code is in 3.1.0; this is not a
regression, but every fan-out `list_issues` call spends **two** of the 200/h
`issues` budget, and `api_call_counts` / `online_estimate.py` under-count by
about 2×. Nothing comicbox can pass (`max_results`, `limit`) stops a short page
early, and overriding `_offset` is private surface. Fix it in simyan.

### D. A Comic Vine budget readout is now cheap and dependency-free

`comicvine_rate_limit.sqlite` holds one table per bucket (`bucket_issues`,
`bucket_search`, …) with `item_timestamp` in ms since the epoch; the rates are
(1 per 1000 ms, 200 per 3 600 000 ms). Verified by driving the real `Comicvine`
limiter on a tmp path. `remaining = 200 − COUNT(item_timestamp

> = now − 3600
> s)`per pool, read-only, no simyan or pyrate-limiter internals.`OnlineSession.rate_limit_status()`currently returns`{}`
> for Comic Vine and NEWS 4.x says "simyan exposes no budget to read" — the
> sqlite file _is_ the budget.

## Phases

### Phase 1 — Adopt the 4.0 error contract

Files: `comicbox/formats/comicvine_api/online_source.py`,
`comicbox/formats/base/online/retry.py`, `tests/unit/test_comicvine_client.py`.

- [ ] Delete the `"rate limit"` message fallback in `_classify_service_error`;
      rewrite its docstring around "body-status errors arrive typed".
- [ ] Replace the single `"not found"` literal with a small `_CV_BODY_ERRORS`
      `MappingProxyType` keyed on the lower-cased body messages 4.0 surfaces
      verbatim: `object not found` → NOT_FOUND, `resource not found` → NOT_FOUND
      (simyan's own 404 text), `error in url format` / `filter error` → INVALID.
- [ ] Add `RetryCategory.INVALID` ("never retried; programmer/config error") and
      treat it like AUTH/NOT_FOUND in `_is_retriable`. Three lines.
- [ ] Tests: drop `test_classify_cv_status_107_body_is_rate_limit`; parametrize
      the typed cases (`RateLimitError("Rate Limit Exceeded")`,
      `RateLimitError(None)`, `AuthenticationError("Invalid API Key")`,
      `ServiceError("Object Not Found")`, `ServiceError("Filter Error")`); add
      one `with_retry` integration test proving a 200-body `AuthenticationError`
      makes exactly one call.
- [ ] NEWS (Fixes): "An invalid Comic Vine API key fails at once instead of
      retrying for half a minute."

### Phase 2 — Cache policy simplification

Files: `online_source.py`, `tests/unit/test_comicvine_client.py`.

- [ ] Remove `_disable_response_cache` and its call in `_build_session`; update
      `_cache_expiry`'s docstring.
- [ ] `test_build_session_cache_off_uses_do_not_cache`: drop the
      `settings.disabled is True` assertion; the
      `cache_expiry ==     DO_NOT_CACHE` and `cache_path` assertions remain the
      contract.
- [ ] NEWS (Performance): "Comic Vine responses now stay cached for
      `online.cache.ttl` instead of following the server's cache headers."
- [ ] Keep `_drop_v2_cache_table` (eight lines, once per process, harmless);
      revisit at the next major.

### Phase 3 — Upstream pagination fix, then a floor bump

- [ ] Open an issue + PR on `Metron-Project/Simyan` (under your account): 1.
      `_offset`: return when `len(page) < limit` or when
      `offset + limit >= number_of_total_results`. 2. `_paginate`: same, via
      `number_of_page_results` / `number_of_total_results`. 3. `_search`: send
      `limit=min(100, max_results)` so `search_volumes(max_results=20)` is one
      request. 4. Doc nit: the `Comicvine` docstring still says "Response
      cache-headers take precedence", which 4.0 made false. Attach the
      fake-transport table from Finding C as the reproduction.
- [ ] When it ships: `simyan>=4.1.0,<5` (or whatever the tag is), `uv lock`,
      NEWS (Dev): "Require simyan ≥ 4.1.0."
- [ ] Re-run the fake-transport probe to confirm one request per short page.
- [ ] If comicbox 5.0.0 ships before the upstream fix, re-derive
      `COMICVINE_REQUESTS_BY_MODE` and `COMICVINE_BUSIEST_POOL_REQUESTS_BY_MODE`
      in `comicbox/online_estimate.py` with the 2× list cost so Codex's estimate
      is honest, and note the reason in the module docstring. Revert when the
      floor bumps.
- [ ] No interim client-side workaround: shrinking `_MAX_VOLUMES_PER_SEARCH` to
      10 would save the second `/search/` page but changes calibrated recall,
      and nothing else can stop a short page early.

### Phase 4 — Comic Vine budget in `rate_limit_status()`

Files: `online_source.py`, `comicbox/online_session.py`,
`comicbox/formats/base/online/rate_limits.py`, new test.

- [ ] Add `shared_client_rate_limit_status(key, url)` next to
      `reset_shared_sessions`, mirroring Metron's
      `shared_session_rate_limit_status`. Store the ratelimit path in the
      `_session_cache` tuple at build time. Open the file read-only
      (`file:…?mode=ro` URI), list `bucket_%` tables, and for each report
      `{"limit": COMICVINE_DEFAULT_PER_HOUR, "remaining": limit − n,     "reset_epoch": oldest_in_window_ms / 1000 + 3600}`.
      Best-effort: any sqlite error or a missing file yields `{}`.
- [ ] Wire `"comicvine"` into `OnlineSession.rate_limit_status()` and rewrite
      its docstring (per-pool windows keyed by bucket name, each in the same
      `limit / remaining / reset_epoch` shape as Metron's windows so a renderer
      can reuse it).
- [ ] Test: build a real `Comicvine` on `tmp_path`, call
      `client._session.limiter.try_acquire("issues")` three times (public
      pyrate-limiter API), assert `remaining == 197` for `issues` and no entry
      for untouched pools. This pins the sqlite layout assumption.
- [ ] NEWS (Features): "`OnlineSession.rate_limit_status()` now reports Comic
      Vine's per-endpoint hourly budget."
- [ ] Flag for Codex: a per-pool dict rather than Metron's fixed burst/sustained
      pair. Paired release; no shim.

### Phase 5 — Retire "simyan 3.x" wording and stale rationale

- [ ] `online_source.py`: module docstring, `_session_cache` comment,
      `_warn_ignored_rate_limit_overrides` message ("simyan 3.x manages" →
      "simyan manages"), `_maintain_cache` and `_classify_service_error`
      comments.
- [ ] `rate_limits.py`, `config/online/settings.py` (`OnlineSourceLimits`),
      `retry.py` comments, `online_estimate.py` docstring, `vacuum.py`
      docstring, `online_session.py` (rewritten in Phase 4).
- [ ] Tests: rename `test_build_session_passes_v3_kwargs` →
      `test_build_session_passes_simyan_kwargs`; `_FakeComicvine` docstring;
      `test_classify_client_side_cap_timeout_is_rate_limit` docstring.
- [ ] After landing, update the memory note
      `project_simyan_version_bump_review.md`.

### Phase 6 — Verify and ship

- [ ] `make fix`, `make lint`, `make ty`, `make test` — run unpiped, fix every
      warning that surfaces.
- [ ] `make complexity` stays green (`online_source.py` is 984 lines; Phase 1
      and 2 shrink it, Phase 4 adds ~60 lines).
- [ ] Optional live smoke with a real key using the warm-cache method in the
      calibration notes: one `--online` lookup, confirm the new
      `rate_limit_status()` entry moves.
- [ ] Commit per phase; PR `simyan-4` → `develop`.

## Out of scope

- Using `simyan.resources` generics: every comicbox call is already a public
  typed wrapper (`search_volumes`, `list_volumes`, `list_issues`, `get_issue`,
  `get_volume`).
- Passing `timeout`: the 20 s default and the derived 40 s client-side
  rate-limit wait interact with comicbox's retry schedule as designed.
- Restoring `per_second` / `per_hour` config overrides: still no injection point
  in 4.0; the warn-and-ignore stays.

## Open questions

1. Phase 1: add `RetryCategory.INVALID` for CV 102/104 (recommended, three
   lines), or leave them TRANSIENT as today?
2. Phase 4: per-pool dict for Comic Vine, or collapse to the busiest pool as a
   single `sustained` window to match Metron's shape exactly? Depends on what
   Codex's renderer wants.
3. Phase 3: file the simyan issue/PR now, before the comicbox work, so the floor
   bump can ride the same release?
