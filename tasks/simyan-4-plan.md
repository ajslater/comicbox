# simyan 4.0.0 adoption plan

**Status:** phases 1, 2, 4, 5 and 6 landed on branch `simyan-4` (off `develop`,
2026-09-03). Phase 3 is filed upstream and blocked on a simyan release. No
version bump — NEWS lines went under the existing `v5.0.0` section.

Decisions taken (the three questions this plan originally left open):

1. `RetryCategory.INVALID` was added, for Comic Vine 102/104.
2. Comic Vine's budget reports a **per-pool dict**, one window per endpoint,
   sharing Metron's `limit` / `remaining` / `reset_epoch` shape.
3. The upstream issue was filed first:
   [Simyan#309](https://github.com/Metron-Project/Simyan/issues/309).

## Where we started

- `pyproject.toml` already required `simyan>=4.0.0,<5` and `uv.lock` resolved
  4.0.0 (commit `fbcaa26`, 2026-09-03). That commit touched only the lock files.
- Under 4.0.0 the 111 tests in `test_comicvine.py`, `test_comicvine_client.py`,
  `test_online_abort_propagation.py` and `test_rich_transforms.py` passed
  unchanged. Nothing was broken.
- But the code, comments, warnings and test names still described simyan 3.x
  behaviour, and two pieces of defensive code existed only because of 3.x quirks
  that 4.0.0 removed.

## What changed, 3.1.0 → 4.0.0

Verified by diffing the installed 4.0.0 wheel against a downloaded 3.1.0
(`git diff --no-index`), and by the GitHub release notes for tag `4.0.0`.

**1. `_request` now inspects the JSON body.** A `status_code != 1` raises
`AuthenticationError` (CV 100 "Invalid API Key"), `RateLimitError` (CV 107 "Rate
Limit Exceeded"), else `ServiceError(body["error"])` (101 "Object Not Found",
102 "Error in URL Format", 104 "Filter Error"). Raised before pydantic runs.
Under 3.x these HTTP-200 error bodies died inside pydantic as a `ServiceError`
wrapping a `ValidationError`; comicbox sniffed "rate limit" in that message to
catch 107, and an invalid key was classified TRANSIENT and retried five times
(~31 s) before failing.

**2. `cache_control=cache_expiry != NEVER_EXPIRE` dropped** from the session
constructor. Comic Vine's response cache headers no longer override
`cache_expiry`, so comicbox's `online.cache.ttl` now fully governs.
`DO_NOT_CACHE` alone skips reads **and** writes (requests-cache 1.3.3
`update_from_response`, "disabled by expiration" criterion), which made the
`settings.disabled` reach-in redundant.

**3. `ComicvineResource` enum removed**, replaced by a `simyan.resources` module
with a `Resource` dataclass and `ISSUE`, `VOLUME`, … constants. Unused by
comicbox.

**4. Deprecated generic `search()` removed.** Comicbox has used
`search_volumes()` since 3.1.0.

**5. `BasicCreator.date_of_death` is a `TimezonedDate`.** Comicbox never fetches
creators.

**6. Endpoint strings now come from `Resource`** with a trailing slash. The
resulting URLs are byte-identical to 3.x, so existing `comicvine_cache.sqlite`
rows stay valid, and bucket names (`search`, `volumes`, `issues`, `get_issue`,
`get_volume`) are unchanged.

**7. Unchanged:** the 1/s and 200/h per-bucket limits,
`max_delay = 2 × timeout = 40 s`, the
`Timeout("Rate limit not cleared within max_delay=…")` cause,
`ignored_parameters=["api_key"]`, the `Issue` / `Volume` schemas, and the
pagination helpers. So retry cause-sniffing, api-key redaction, the transform
and the estimator constants all still apply.

Dependency floors moved to pydantic ≥ 2.13, requests-cache ≥ 1.3,
requests-ratelimiter ≥ 0.10, requests ≥ 2.34. Already satisfied by `uv.lock`.

## Findings that shaped the plan

### A. Error classification had dead and mis-tuned branches

In `_classify_service_error`
(`comicbox/formats/comicvine_api/online_source.py`):

- The final `"rate limit" in str(exc).lower()` fallback was dead: 107 now
  arrives as a typed `RateLimitError`.
- "Object Not Found" (CV 101) already landed on NOT_FOUND through the literal
  `"not found"` check, but the comment claimed the only literal was "Resource
  not found".
- "Error in URL Format" / "Filter Error" (CV 102/104) became `ServiceError` →
  TRANSIENT → five retries. They are programmer errors and should raise
  immediately, like the `_NON_RETRIABLE` tuple in `retry.py`.
- The `Timeout("Rate limit not cleared…")` cause sniff and
  `_service_error_status` (HTTPError path) are still the only signal for their
  cases, and stay.

### B. Cache OFF no longer needs a private reach-in

`_disable_response_cache` set `client._session.settings.disabled = True` because
3.x's `cache_control=True` let header-driven expiry write anyway. With
`cache_control` gone, `cache_expiry=DO_NOT_CACHE` is sufficient. Confirmed
against the real client with a fake transport returning
`Cache-Control: max-age=3600`: zero rows written.

### C. Hidden 2× pagination cost (pre-existing; fix belongs upstream)

Measured with a fake `_request` transport against the installed 4.0.0:

| Call                                                   | Results | HTTP requests |
| ------------------------------------------------------ | ------- | ------------- |
| `list_issues(filter=volume+issue_number)`              | 2       | **2**         |
| `list_issues(...)`                                     | 0       | 1             |
| `list_volumes(filter=name+start_year, max_results=20)` | 3       | **2**         |
| `search_volumes(max_results=20)`                       | 7       | **2**         |
| `search_volumes(max_results=20)`                       | 50      | **2**         |
| `list_issues(filter=volume)` whole volume              | 43      | **2**         |

Cause: `Comicvine._offset` loops until it receives an empty page rather than
stopping when a page is short, or when `offset + limit` reaches
`number_of_total_results`, which every Comic Vine response carries. The same
code is in 3.1.0, so this is not a regression, but every fan-out `list_issues`
call spends **two** of the 200/h `issues` budget, and `api_call_counts` /
`online_estimate.py` under-count by about 2×. Nothing comicbox can pass
(`max_results`, `limit`) stops a short page early, and overriding `_offset` is
private surface. Fix it in simyan.

**Correction to this plan's first draft:** sending `limit=min(100, max_results)`
on `/search/` is _not_ a valid fix. Comic Vine caps that endpoint's `limit` at
10, so `search_volumes(max_results=20)` genuinely needs two pages. Only the
short-page exit helps there, and it does: the 7-total row drops to one request.

### D. A Comic Vine budget readout is cheap and dependency-free

`comicvine_rate_limit.sqlite` holds one table per bucket (`bucket_issues`,
`bucket_search`, …) with `item_timestamp` in milliseconds since the epoch, at
rates of 1 per 1000 ms and 200 per 3,600,000 ms. Verified by driving the real
`Comicvine` limiter on a tmp path. Per pool, `remaining` is 200 minus the rows
whose `item_timestamp` falls inside the last 3600 s — read-only, with no simyan
or pyrate-limiter internals. `OnlineSession.rate_limit_status()` returned `{}`
for Comic Vine, and NEWS 4.x said "simyan exposes no budget to read", but the
sqlite file _is_ the budget.

## Phases

### Phase 1 — Adopt the 4.0 error contract ✅

Files: `comicbox/formats/comicvine_api/online_source.py`,
`comicbox/formats/base/online/retry.py`, `tests/unit/test_comicvine_client.py`.

- [x] Delete the `"rate limit"` message fallback in `_classify_service_error`;
      rewrite its docstring around "body-status errors arrive typed".
- [x] Replace the two ad-hoc message checks with a `_CV_BODY_ERRORS` table keyed
      on the lower-cased body messages 4.0 surfaces verbatim: `object not found`
      → NOT_FOUND, `resource not found` → NOT_FOUND (simyan's own 404 text),
      `error in url format` / `filter error` → INVALID.
- [x] Add `RetryCategory.INVALID` and treat it like AUTH/NOT_FOUND in
      `_is_retriable`.
- [x] Tests: drop `test_classify_cv_status_107_body_is_rate_limit`; parametrize
      the typed cases; assert every terminal classification is called exactly
      once through `with_retry`.
- [x] NEWS (Fixes): an invalid Comic Vine API key fails at once.

### Phase 2 — Cache policy simplification ✅

- [x] Remove `_disable_response_cache` and its call in `_build_session`;
      document why `DO_NOT_CACHE` is now sufficient in `_cache_expiry`.
- [x] `test_build_session_cache_off_uses_do_not_cache`: drop the
      `settings.disabled` assertion; `cache_expiry == DO_NOT_CACHE` and
      `cache_path` remain the contract.
- [x] NEWS (Performance): cached responses honor `online.cache.ttl`.
- [x] Keep `_drop_v2_cache_table` (eight lines, once per process, harmless);
      revisit at the next major.

### Phase 3 — Upstream pagination fix, then a floor bump ⛔ blocked upstream

Filed as [Simyan#309](https://github.com/Metron-Project/Simyan/issues/309) with
the fake-transport reproduction, a verified before/after table, and the patch
for both loops. The fix was tested locally by binding the patched methods
per-instance: every returned result set is identical and the request count drops
by one in each non-boundary case, including a full 100-item page — which only
the `number_of_total_results` check catches, not the short-page test.

- [x] Open the issue, including the doc nit that the `Comicvine` docstring still
      promises "Response cache-headers take precedence" after 4.0 dropped
      `cache_control`, and that both loops mutate the caller's `params` dict.
- [ ] Offer the PR if the maintainer approves the approach.
- [ ] When it ships: `simyan>=4.1.0,<5` (or whatever the tag is), `uv lock`,
      NEWS (Dev): "Require simyan ≥ 4.1.0."
- [ ] Re-run the fake-transport probe to confirm one request per short page.
- [ ] Decide then whether to re-derive `COMICVINE_REQUESTS_BY_MODE` and
      `COMICVINE_BUSIEST_POOL_REQUESTS_BY_MODE` in `comicbox/online_estimate.py`
      with the 2× list cost. Deliberately not done now: those numbers are a
      projection shown to an operator before a run, and doubling them to
      describe a bug we are fixing upstream would make them wrong again as soon
      as the floor bumps. Revisit only if comicbox 5.0.0 ships first.
- [ ] No interim client-side workaround: shrinking `_MAX_VOLUMES_PER_SEARCH` to
      10 would save the second `/search/` page but changes calibrated recall,
      and nothing else can stop a short page early.

### Phase 4 — Comic Vine budget in `rate_limit_status()` ✅

- [x] Add `shared_client_rate_limit_status(settings)` beside
      `reset_shared_sessions`. It opens the bucket file read-only
      (`file:…?mode=ro`), lists `bucket_%` tables, and reports `limit` /
      `remaining` / `reset_epoch` per pool. Best-effort: a missing or unreadable
      file yields `{}`. It takes settings rather than credentials because the
      path depends only on the cache dir — so it works before a session has
      issued any request, and the budget survives across runs.
- [x] Wire `"comicvine"` into `OnlineSession.rate_limit_status()` and rewrite
      its docstring: per-pool windows keyed by bucket name, in the same shape as
      Metron's, so one renderer handles both.
- [x] Test: drive the real limiter through pyrate-limiter's public `try_acquire`
      and assert the numbers. This pins the sqlite layout, so a future change to
      table naming or timestamp units fails loudly instead of silently reading
      as a full budget.
- [x] NEWS (Features): `rate_limit_status()` reports Comic Vine's per-endpoint
      hourly budget.
- [x] Split `resolve_cache_db_path` out of `OnlineSource.cache_db_path` so a
      read-only caller can skip the `mkdir`.
- [ ] Flag for Codex: a per-pool dict rather than Metron's fixed burst/sustained
      pair. Paired release; no shim.

### Phase 5 — Retire "simyan 3.x" wording and stale rationale ✅

- [x] `online_source.py`: module docstring (now also describes the two direct
      sqlite reads and 4.0's typed body errors), `_session_cache` comment,
      `_warn_ignored_rate_limit_overrides` message, `_maintain_cache` and
      `_classify_service_error` comments.
- [x] `rate_limits.py` (now records the hourly cap's second consumer),
      `config/online/settings.py`, `retry.py`, `online_estimate.py`,
      `online_session.py`.
- [x] Tests: rename `test_build_session_passes_v3_kwargs`; `_FakeComicvine` and
      cap-timeout docstrings; `test_online_estimate.py`, `test_rate_limits.py`,
      `test_online_retry.py` comments.
- [x] References to simyan **v2** stay: those name a version whose artifacts the
      code really does still clean up.
- [ ] After landing, update the memory note
      `project_simyan_version_bump_review.md`.

### Phase 6 — Verify and ship ✅

- [x] `make fix`, `make lint`, `make ty`, `make typecheck` — all clean.
- [x] `make complexity` green.
- [x] `make test`: 2061 passed, 1 skipped (2048 on `fbcaa26`), warning count
      unchanged at 15.
- [ ] Optional live smoke with a real key using the warm-cache method in the
      calibration notes: one `--online` lookup, confirm the new
      `rate_limit_status()` entry moves.
- [x] Commit per phase.
- [ ] PR `simyan-4` → `develop`.

## Out of scope

- Using `simyan.resources` generics: every comicbox call is already a public
  typed wrapper (`search_volumes`, `list_volumes`, `list_issues`, `get_issue`,
  `get_volume`).
- Passing `timeout`: the 20 s default and the derived 40 s client-side
  rate-limit wait interact with comicbox's retry schedule as designed.
- Restoring `per_second` / `per_hour` config overrides: still no injection point
  in 4.0; the warn-and-ignore stays.

## Outcome

Landed in five commits on `simyan-4`. Two things surfaced that were not in the
original plan:

- **The test suite was never isolated from the real online cache dir.**
  `online.cache.dir` defaults to the platformdirs user cache, which holds live
  response and rate-limit sqlite files. Phase 4's budget read made this visible
  by returning this machine's actual Comic Vine pools inside a unit test. The
  hermetic env fixture now pins the directory into `tmp_path`, so no test can
  read or corrupt real cached data.
- **Closing a simyan client does not release its sqlite handles.**
  requests-ratelimiter's `HostBucketFactory` stores buckets in its own `buckets`
  dict, which pyrate-limiter's `BucketFactory.close()` does not iterate, so
  `session.close()` stops the leaker but leaves the bucket connections open —
  measured, 2 of 4 released. This is the cause of the `unclosed database`
  ResourceWarnings that already existed on `develop` (10 on `fbcaa26`).
  `tests/util/online_client.py` closes them explicitly so the new tests add
  none. **Not fixed broadly:** the pre-existing warnings come from other tests
  building real clients, and a general fix belongs either upstream in
  requests-ratelimiter or in a shared fixture, which is a separate change.
