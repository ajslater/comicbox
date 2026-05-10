# Calibration Harness

Tunes the online matcher's confidence thresholds against a real-world
fixture set.

This is **not** part of the regular test suite — it hits live Metron
and ComicVine APIs, requires credentials, and takes minutes to run.
You invoke it manually when you want to (re-)evaluate the matcher's
defaults against your own comic library.

---

## Setup

1. **Credentials.** Configure Metron (username + password) and/or
   ComicVine (api_key). Easiest is `~/.config/comicbox/config.yaml`:

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

2. **Build a fixtures.json.**

   **Easy mode** — if your library is already tagged with metron / cv ids
   (from previous metron-tagger / comictagger / comicbox runs), bootstrap
   the fixture set automatically:

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

   **Manual mode** — if your library is mostly untagged, copy the
   example and edit by hand:

   ```sh
   cp tests/calibration/fixtures.example.json tests/calibration/fixtures.json
   ```

   The file is gitignored — it's specific to your library.

   Each fixture entry:
   - `file` — absolute or `~`-prefixed path to a `.cbz` / `.cbr` /
     `.cbt` / `.pdf` (any format comicbox reads).
   - `metron` — the issue's Metron id (integer), or `null` if Metron
     doesn't have it.
   - `comicvine` — the issue's ComicVine id (integer), or `null`.
   - `cover_quality` — `"full"`, `"thumbnail"`, or `"missing"`. Used
     today only as documentation; the harness doesn't yet adjust
     hashing based on it.
   - `notes` — optional free text.

   Aim for ~100–300 fixtures spanning eras, publishers, tagging
   quality. Mix:
   - Cleanly-tagged comics (good metadata signal).
   - Filename-only comics (tests filename parser → matcher chain).
   - Comics where Metron/CV ids you know are correct, including
     borderline cases (volume reboots, ambiguous series names).

3. **Run.**

   ```sh
   make calibrate                                # both sources, full set
   uv run python -m tests.calibration.run --sources metron --limit 30
   ```

   Each full run writes its outcomes to a sibling
   `fixtures.outcomes.json` for use by `--retry-misses` (see below).

---

## Iterating against a subset (recommended)

A full run against 300+ fixtures can take **hours** — CV's 200/hour
cap is the binding constraint. When you've made a code change and
want to verify it without burning a full run's budget:

### `make calibrate-retry` (or `--retry-misses`)

Re-runs only the fixtures that previously failed (wrong / no
candidates / error). Reads the saved `fixtures.outcomes.json`:

```sh
make calibrate-retry
```

Typical iteration loop:
1. `make calibrate` once on the full set — slow, but caches results.
2. Make a code change.
3. `make calibrate-retry` — runs only what previously broke. Often
   1/10th the wall time.
4. Inspect, repeat.

The retry run does NOT overwrite the main outcomes.json; it writes
to `fixtures.outcomes.partial.json` so you can compare before/after.

### `make calibrate-retry-sampled` (or `--one-per-series`)

Even faster than `calibrate-retry`: drops to one representative
fixture per series. If 19 Conan issues all failed the same way,
testing one of them tells you everything testing all 19 does — they
share the volume-search code path.

```sh
make calibrate-retry-sampled
```

Series key is "everything before the issue marker", so:

| Filename | Series key |
|---|---|
| `Watchmen (1986) #002.cbz` | `Watchmen (1986)` |
| `Conan (2004) #005.cbz`    | `Conan (2004)` |
| `Lois Lane (2019) #001.cbz`| `Lois Lane (2019)` |
| `Akira (1984) #001.cbz`    | `Akira (1984)`* |

\* `Akira (1984)` and `Akira (1990)` are treated as separate series
because the year-in-parens often distinguishes volumes (`Lois Lane
(1986)` vs `Lois Lane (2019)`). For Akira specifically the same
logical run got split across years, but the harness errs conservative
— group further with `--filter` if you want.

`--one-per-series` composes with `--retry-misses` and `--filter`.

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

Metron's 20/min cap is much more forgiving than CV's 200/hr.
For most scoring-tweak iterations, calibrating just Metron first
is faster:

```sh
uv run python -m tests.calibration.run --sources metron
```

---

## Rate-limit cost

The upstream libraries enforce per-IP limits via SQLite-backed
buckets that persist across runs. Plan your run accordingly:

| Source    | Documented limit              | ~300-fixture cost (cold cache) |
|-----------|-------------------------------|---------------------------------|
| Metron    | 20 req/min, 5,000 req/day     | ~15 min wall time              |
| ComicVine | 1 req/sec, 200 req/hour       | ~50 min wall (forced 60-min waits between 200-req batches) |

**Subsequent runs are near-instant** — the SQLite response cache
(default 7-day TTL) replays previous responses without API calls. So
the slow run is only the first one, and only on cache-miss fixtures.

If you have a higher API tier on either service, you can raise the
caps via `online.<source>.rate_limit.per_minute` (etc.) in your
config.yaml — see `comicbox/online/rate_limits.py` for the keys.

---

## Reading the report

Sample output:

```
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
- **Top accuracy** — the headline number. Aim for ≥95% on a
  representative fixture set before declaring the matcher tuned.
- **Per-band correctness** — the auto-write band (0.85-0.95) should
  be ≥99% correct; if it's lower, the threshold is too low and
  comicbox is confidently writing wrong tags. Raise the
  `--confidence-threshold` default.
- **Prompt-zone accuracy** — the 0.70-0.85 band is where users see
  prompts. ~50% correct is fine here; users veto bad ones manually.
- **No candidates** — comicbox found nothing. May indicate: bad
  filename parse, source doesn't have the issue, or query is too
  strict (year off, volume off). The "Outcomes worth a look" section
  lists each one for hand-investigation.

---

## What's NOT calibrated yet

- **Cover hash signal.** Calibration runs metadata-only ranking. The
  hashing pass invokes only when ranking is ambiguous, and the
  slimlib comics have degraded covers, so we'd be measuring noise.
  Cover-hash calibration needs full-cover fixtures and a separate
  harness mode — TODO.
- **Per-source thresholds.** This harness reports per-source numbers
  but doesn't yet recommend per-source threshold tuning. Future
  work: surface fixtures where metron's confidence and comicvine's
  disagree dramatically.

---

## Internals

`run.py` does:

1. Loads fixtures from `fixtures.json`.
2. For each fixture, builds a `ComicProfile` from its existing
   metadata + filename (running comicbox's normal read/normalize/merge
   without online).
3. Calls `source.search(profile)` directly (one source at a time).
4. Calls `OnlineMatcher.rank(profile, candidates)` with metadata-only
   ranking.
5. Compares the top candidate's `issue_id` against the fixture's
   expected id. Buckets by score band.
6. Prints summary + per-fixture details for failures.

No writes happen — the harness is read-only against the comic files.
