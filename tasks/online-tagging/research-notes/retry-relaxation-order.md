# Retry-relaxation order — empirical analysis

The §4 TODO from `tasks/online-tagging/TODO.md` asked for an A/B between two
retry-relaxation orders in Metron's `search()`:

**Current** (in `comicbox/online/sources/metron.py`):

```
(year=Y, volume=V)        ← initial query
  ↓ if 0 candidates AND profile.year:
(year=Y-1, volume=V)      ← year-relax retry (1)
(year=Y+1, volume=V)      ← year-relax retry (2)
  ↓ if still 0 AND profile.volume:
(year=Y, no volume)       ← drop-volume retry, year exact
  ↓ if 0:
(year=Y-1, no volume)     ← drop-volume + year-relax (1)
(year=Y+1, no volume)     ← drop-volume + year-relax (2)
```

**Proposed** (the §4 hypothesis): try `drop volume` BEFORE year-relax, on the
theory that filename-parsed `Vol. N` is less reliable than the user-tagged year.

## Answer: the question is moot on real-world data

Looking at the 2026-05-17 bigmedia 247-fixture run:

- **246 of 247 fixtures have no `Vol. N` / `Volume N` / `vN` marker in their
  filename**, so `profile.volume` is None for them.
- The drop-volume retry path requires `profile.volume is not None` (per
  `metron.py:292`). It cannot fire for fixtures without a parsed volume —
  there's no volume filter to drop.
- The A/B between "year-relax first" and "drop-volume first" only differs on
  fixtures where BOTH paths are reachable. That's 1 fixture out of 247.

**Whatever the proposed order does on 1 fixture, the calibration sample-size is
too small to draw conclusions from.**

## Why so few volume markers?

Bigmedia is mostly CV-tagged content where the filename pattern is
`<Series> (<Year>) #<Issue>.cbz` — no volume marker. Scanners and tagging tools
have largely converged on this format. Volume info, when present, is typically
embedded in the SERIES name itself (e.g. `Lois Lane (2019) #001.cbz` — the
(2019) disambiguates from older Lois Lane volumes without a separate `Vol N`
field).

So `profile.volume` is rarely populated in practice. The retry path that DROPS
it is rarely reached.

## What this rules out

- **The §4 reorder is not worth implementing.** The data doesn't justify it.
- **Adding instrumentation + running A/B would be wasted effort.** Even if the
  alternative order were marginally better on the 1 fixture, the bigmedia
  outcome would round to "no change".

## What this implies for future work

If a future calibration set is dominated by sources that DO encode volume
markers (older scanner conventions, manual tagging), the relaxation-order
question might become relevant. Re-test then with fresh telemetry, not from this
246-of-247 = 99.6% no-volume data.

## Per-fixture Metron call patterns from bigmedia

For completeness, the issues_list call distribution across 247 fixtures
(already-computed from outcomes JSON):

| issues_list count | fixtures | likely scenario                                    |
| ----------------- | -------- | -------------------------------------------------- |
| 0                 | 159      | series_list returned 0 series (Metron has nothing) |
| 1                 | 35       | single candidate series, single call               |
| 2                 | 5        | 2 candidate series                                 |
| 3                 | 23       | 3 candidate series                                 |
| 4                 | 1        |                                                    |
| 5                 | 2        |                                                    |
| 6                 | 7        |                                                    |
| 9                 | 3        |                                                    |
| 15                | 7        | high fan-out (Conan/Lois Lane-style multi-volume)  |
| 18                | 1        |                                                    |
| 24                | 2        |                                                    |
| 30                | 2        | very high fan-out                                  |

Most fixtures with 1+ issues_list calls likely hit on the FIRST (year, volume)
try and didn't trigger year-relax either. The relaxation cascade is rare across
the board on bigmedia.

The TODO entry can be closed as "won't fix — empirical data shows the path isn't
exercised".
