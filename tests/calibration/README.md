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

2. **Build a fixtures.json.** Copy the example and edit:

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
