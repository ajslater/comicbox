# Calibration Harness

Tunes the online matcher's confidence thresholds against a real-world fixture
set.

This is **not** part of the regular test suite — it hits live Metron and
ComicVine APIs, requires credentials, and takes minutes to run. You invoke it
manually when you want to (re-)evaluate the matcher's defaults against your own
comic library.

---

## Setup

1. **Credentials.** Configure Metron (username + password) and/or ComicVine
   (api_key). Easiest is `~/.config/comicbox/config.yaml`:

    ```yaml
    comicbox:
        online:
            metron:
                username: your_metron_user
                password: your_metron_password
            comicvine:
                api_key: your_cv_api_key
    ```

    Or set env vars (`COMICBOX_METRON_USERNAME`, etc.).

2. Build a fixtures.json.

    **Easy mode** — if your library is already tagged with metron / cv ids (from
    previous metron-tagger / comicbox runs), bootstrap the fixture set
    automatically:

    ```sh
    # Walk a directory, extract existing tags, write fixtures.json:
    uv run python -m tests.calibration.bootstrap ~/Milliways/Comics/Test

    # Mark all entries as thumbnail-quality (e.g. for slimlib):
    uv run python -m tests.calibration.bootstrap ~/Milliways/slimlib \
        --cover-quality thumbnail \
        --output tests/calibration/fixtures-slim.json

    # Cross-source calibration only — both ids required:
    uv run python -m tests.calibration.bootstrap \
        ~/Milliways/Comics/Test --require-both
    ```

    See `make calibrate-bootstrap` for the default invocation.

    **Manual mode** — if your library is mostly untagged, copy the example and
    edit by hand:

    ```sh
    cp tests/calibration/fixtures.example.json tests/calibration/fixtures.json
    ```

    The file is gitignored — it's specific to your library.

    Each fixture entry:
    - `file` — absolute or `~`-prefixed path to a `.cbz` / `.cbr` / `.cbt` /
      `.pdf` (any format comicbox reads).
    - `metron` — the issue's Metron id (integer), or `null` if Metron doesn't
      have it.
    - `comicvine` — the issue's ComicVine id (integer), or `null`.
    - `cover_quality` — `"full"`, `"thumbnail"`, or `"missing"`. The harness
      enables cover-hash ranking only for `"full"` fixtures; the others fall
      back to metadata-only so degraded covers don't pollute the per-band
      correctness numbers.
    - `notes` — optional free text.

    Aim for \~100–300 fixtures spanning eras, publishers, tagging quality. Mix:
    - Cleanly-tagged comics (good metadata signal).
    - Filename-only comics (tests filename parser → matcher chain).
    - Comics where Metron/CV ids you know are correct, including borderline
      cases (volume reboots, ambiguous series names).

3. **Run.**

    ```sh
    make calibrate # both sources, full set
    uv run python -m tests.calibration.run --sources metron --limit 30
    ```

    Each full run writes its outcomes to a sibling `fixtures.outcomes.json` for
    use by `--retry-misses` (see below).

---

## Iterating against a subset (recommended)

A full run against 300+ fixtures can take **hours** — CV's 200/hour cap is the
binding constraint. When you've made a code change and want to verify it without
burning a full run's budget:

### `make calibrate-retry` (or `--retry-misses`)

Re-runs only the fixtures that previously failed (wrong / no candidates /
error). Prefers `fixtures.outcomes.json` (full-run output); falls back to
`fixtures.outcomes.partial.json` (filtered-run output) when no full run has
finished — useful when CV's 200/hr cap means a full calibration would take days.

```sh
make calibrate-retry
```

Typical iteration loop:

1. `make calibrate` once on the full set — slow, but caches results.
2. Make a code change.
3. `make calibrate-retry` — runs only what previously broke. Often 1/10th the
   wall time.
4. Inspect, repeat.

The retry run does NOT overwrite the main outcomes.json; it writes to
`fixtures.outcomes.partial.json` so you can compare before/after. If you've
never finished a full run, that same `.partial.json` is what subsequent
`--retry-misses` invocations read.

### `make calibrate-retry-sampled` (or `--one-per-series`)

Even faster than `calibrate-retry`: drops to one representative fixture per
series. If 19 Conan issues all failed the same way, testing one of them tells
you everything testing all 19 does — they share the volume-search code path.

```sh
make calibrate-retry-sampled
```

Series key is "everything before the issue marker", so:

| Filename                    | Series key         |
| --------------------------- | ------------------ |
| `Watchmen (1986) #002.cbz`  | `Watchmen (1986)`  |
| `Conan (2004) #005.cbz`     | `Conan (2004)`     |
| `Lois Lane (2019) #001.cbz` | `Lois Lane (2019)` |
| `Akira (1984) #001.cbz`     | `Akira (1984)`\*   |

\* `Akira (1984)` and `Akira (1990)` are treated as separate series because the
year-in-parens often distinguishes volumes (`Lois Lane (1986)` vs
`Lois Lane (2019)`). For Akira specifically the same logical run got split
across years, but the harness errs conservative — group further with `--filter`
if you want.

`--one-per-series` composes with `--retry-misses` and `--filter`.

**When to use `--one-per-series` vs the full set:**

| Calibration task                                            | Sampling                              |
| ----------------------------------------------------------- | ------------------------------------- |
| Tune `confidence_threshold` from score-band data            | Full set                              |
| Phase B api_budget matrix runs (`fast` vs `balanced` flips) | `--one-per-series`                    |
| Code-iteration smoke runs (verify a fix)                    | `--one-per-series` + `--retry-misses` |
| Final acceptance check before shipping                      | Full set                              |

The rationale: every issue from a given series exercises the same matcher code
path (same volume-search, same per-volume issue-list filter). If `fast` mode
flips the Watchmen series's verdict, ALL six Watchmen fixtures will flip
together — running them all just confirms what one already showed at \~10x the
wall-clock cost. Threshold tuning is the exception because each fixture is an
independent score sample and the distribution shape matters.

### `--filter REGEX`

Run only fixtures whose filename matches a regex:

```sh
# Verify the smoking-gun cases after a scoring fix:
uv run python -m tests.calibration.run --filter 'Lois Lane|Watchmen \(1987\)'

# Just the AfterShock indie titles:
uv run python -m tests.calibration.run --filter 'Wrong Earth|Penultiman|Snow Angels'
```

Combines with `--sources` and `--limit`. Doesn't overwrite the main
outcomes.json (writes to `.partial.json`).

### Per-source iteration

Metron's 20/min cap is much more forgiving than CV's 200/hr. For most
scoring-tweak iterations, calibrating just Metron first is faster:

```sh
uv run python -m tests.calibration.run --sources metron
```

---

## Rate-limit cost

Metron's limits are per-user and tracked reactively by mokkari>=4 from
`X-RateLimit-*` response headers; ComicVine's are per-IP, enforced by simyan's
persistent local limiter. Plan your run accordingly:

| Source    | Documented limit                                 | \~300-fixture cost (cold cache)                             |
| --------- | ------------------------------------------------ | ----------------------------------------------------------- |
| Metron    | 20 req/min burst; 5,000-25,000 req/day (by tier) | \~15 min wall time                                          |
| ComicVine | 1 req/sec, 200 req/hour                          | \~50 min wall (forced 60-min waits between 200-req batches) |

**Subsequent runs are near-instant** — the SQLite response cache (default 7-day
TTL) replays previous responses without API calls. So the slow run is only the
first one, and only on cache-miss fixtures.

There is nothing to configure for a higher API tier: mokkari picks up your
actual Metron limits automatically from response headers, and ComicVine has no
tiers. The old `online.<source>.rate_limit.*` config keys are accepted but
ignored (with a warning).

### Periodic checkpointing

The harness saves outcomes-so-far to disk every 10 fixtures during the loop.
This bounds work lost to a `Ctrl-C` to at most \~10 fixtures — restart picks up
the API-cached calls fast (seconds each) and resumes on the remaining fixtures.

Writes are atomic (temp file + rename), so a kill mid-write leaves either the
previous version or the next version on disk — never a half-written file. The
destination follows the same logic as the end-of-run save: labeled runs go to
`<stem>.outcomes.<label>.json`, filtered runs merge into
`<stem>.outcomes.partial.json`, full runs overwrite `<stem>.outcomes.json`.

You'll see `[checkpoint: N outcomes saved]` in the progress output every 10
fixtures.

### Live ETA

The harness prints a rolling-window ETA so you can plan around long cold-cache
runs. Two display points:

- **Heartbeat ticks** (every 15s while a single fixture is in flight): two lines
  — current-fixture stall time, plus overall progress / ETA. Lets you tell apart
  "this one is rate-limited" from "everything is stuck."
- **Every 10 fixtures** (and on fixture 1 + the last fixture): a one-line
  progress summary.

Example:

```log
  [12/343] comicvine: Watchmen (1986) #005.cbz ... OK  score=0.99
  [overall 12/343 fixtures, 14.7m elapsed, ETA 6.7h]
```

The ETA uses a 20-fixture rolling average. Cache-warming (early fixtures slow,
later fast) and rate-limit walls (sudden multi-minute stalls) both reflect in
the estimate within a handful of fixtures. The first fixture has no ETA —
there's no data to project from.

---

## Reading the report

Sample output:

```log
=== metron ===
  correct: 178
  wrong:   8
  no candidates returned: 5
  fixtures missing expected metron id: 9
  accuracy on labeled fixtures: 95.7%
  by score band:
    0.95-1.00 (very high): 142/142 correct (100%)
    0.85-0.95 (auto-write): 32/35 correct (91%)
    0.70-0.85 (prompt zone): 4/8 correct (50%)
    0.50-0.70 (solo-viable): 0/1 correct (0%)
```

What to look at:

- **Top accuracy** — the headline number. Aim for ≥95% on a representative
  fixture set before declaring the matcher tuned.
- **Per-band correctness** — the auto-write band (0.85-0.95) should be ≥99%
  correct; if it's lower, the threshold is too low and comicbox is confidently
  writing wrong tags. Raise the `--confidence-threshold` default.
- **Prompt-zone accuracy** — the 0.70-0.85 band is where users see prompts.
  \~50% correct is fine here; users veto bad ones manually.
- **No candidates** — comicbox found nothing. May indicate: bad filename parse,
  source doesn't have the issue, or query is too strict (year off, volume off).
  The "Outcomes worth a look" section lists each one for hand-investigation.

---

## Cover-hash signal

For fixtures tagged `cover_quality: "full"` the harness passes the matcher both
a local-cover pHash provider and a candidate-cover fetcher — the same plumbing
used in production. The matcher only invokes hashing when the metadata-only top
is ambiguous (close call or below the confidence threshold), so most fixtures
pay no extra cost.

When hashing fires:

- Metron candidates carry a precomputed pHash and are compared in-memory.
- ComicVine candidates' cover URLs are downloaded and hashed on-demand, with the
  resulting `url → pHash` rows persisted in
  `<online cache dir>/cover_hashes.sqlite` so re-runs are free.

Fixtures whose `cover_quality` is `thumbnail` (slimlib's downsized covers) or
`missing` get `(None, None)` — ranking stays metadata-only for those, so the
per-band correctness number reflects what the matcher does without the hash
boost. That keeps slimlib's degraded covers from masking metadata-signal
regressions.

## What's NOT calibrated yet

- **Per-source thresholds.** This harness reports per-source numbers but doesn't
  yet recommend per-source threshold tuning. Future work: surface fixtures where
  metron's confidence and comicvine's disagree dramatically.

---

## Internals

`run.py` does:

1. Loads fixtures from `fixtures.json`.
2. For each fixture, opens the `Comicbox` and builds a `ComicProfile` from its
   existing metadata + filename (running comicbox's normal read/normalize/merge
   without online).
3. Calls `source.search(profile)` directly (one source at a time).
4. Calls `OnlineMatcher.rank(profile, candidates, ...)`. For
   `cover_quality: "full"` fixtures, the rank call also receives the
   `local_hash_provider` and `candidate_hash_fetcher` (production plumbing) so
   cover hashing can break ties on ambiguous candidates; `"thumbnail"` and
   `"missing"` fixtures stay metadata-only.
5. Compares the top candidate's `issue_id` against the fixture's expected id.
   Buckets by score band.
6. Prints summary + per-fixture details for failures.

No writes happen — the harness is read-only against the comic files.
