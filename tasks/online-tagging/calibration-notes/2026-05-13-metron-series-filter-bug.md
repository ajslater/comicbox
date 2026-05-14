# Metron `series` filter silently ignored — 2026-05-13

A production matcher bug surfaced by the post-Phase-E calibration
re-run when `label_metron.py` added 11 fresh Metron expected ids to
the slimlib fixture set.

## Symptom

`compare.py` on the post-label outcomes file showed Metron issue id
**7098** returned as the matcher's top candidate for three unrelated
2020 indie #1s:

- `American Ronin #001 (2020).cbz` (AWA Studios) → got=7098, score=0.89
- `Kidz #001 (2020).cbz` (BOOM!) → got=7098, score=0.88
- `Miles to Go #001 (2020).cbz` (AfterShock) → got=7098, score=0.89

Issue 7098 is **New Mutants Vol 4 #1 (Marvel, Jan 2020)**.

Same pattern with issue id 128 returned for `Bad Reception #001 (2019)`
and `Archie 1955 #001 (2019)` — two unrelated 2019 #1s.

## Root cause

`MetronOnlineSource._build_issue_params` was constructing the
`issues_list` filter with `{"series": series_id}`. mokkari's docstring
example uses this form (`session.issues_list({"series": 1})`) but
Metron's DRF backend ignores the bare `series` keyword as an unknown
filter and silently returns issues matched by the remaining params
(`number` + `cover_year`) alone.

The correct filter is `series_id`.

Empirical confirmation via `tests/calibration/debug_search.py` with
both variants on the live API:

```text
  [follow-up:series] issues_list(params={'number': '1', 'cover_year': 2020, 'series': 1572})
    → 456 result(s)
      id=9838 series='2020 Force Works' number='1' cover_date=2020-04-01
      id=103345 series='2020 Iron Age' number='1' cover_date=2020-05-01
      id=118203 series='2020 Ironheart' number='1' cover_date=2020-07-01
      ...

  [follow-up:series_id] issues_list(params={'number': '1', 'cover_year': 2020, 'series_id': 1572})
    → 1 result(s)
      id=17654 series='American Ronin' number='1' cover_date=2020-10-01
```

The 456-result query was returning Marvel's "2020" event lineup
("2020 Force Works", "2020 Iron Age", "2020 Ironheart", etc.) plus
hundreds of other 2020 #1s. The matcher's scoring against the
American Ronin profile produced top-rank picks that scored 0.88-0.89
on `series=1.0, issue=1.0, year=1.0` (since the candidate happened to
be issue 1 cover-dated 2020), even though the actual series name
shared no tokens with the profile.

## Why this hid until now

The bug has been latent through every Metron run since the two-step
search refactor. Slimlib's near-zero Metron coverage (2.2%) meant the
Metron source mostly returned `no_candidates` outcomes — so the bug
never produced visible wrong answers. Only when `label_metron.py`
added 11 fresh Metron ids did the matcher's "wrong" picks become
gradeable and the pattern jump out.

Phase B's labeled fixture set similarly had thin Metron coverage
(73 / 339 fixtures with Metron expected ids), and the few wrong picks
weren't obviously *cross-series* — they could have been wrong-volume
picks within the right series.

## Fix

One-line change in `_build_issue_params`:

```python
# Before:
params: dict[str, Any] = {"series": series_id}

# After:
params: dict[str, Any] = {"series_id": series_id}
```

Plus parallel updates to `tests/unit/test_metron_source.py`'s fake
mocks (`params.get("series")` → `params.get("series_id")`, etc.) and
`tests/calibration/debug_search.py`'s test harness.

## Side note: mokkari docstring is misleading

The mokkari docstring (mokkari 3.13.0) at
`session.py:1116` documents:

> Common parameters include 'series', 'number', 'cover_date', ...

and the example shows `issues_list({"series": 1})`. Both are wrong —
or rather, mokkari blindly passes whatever dict you give it as query
params to Metron's REST endpoint, and Metron ignores `series` as an
unknown filter. The docstring should reference `series_id`.

Worth a separate report upstream; out of scope for this fix.

## Verification

- 821 existing tests pass after the fix.
- The same diagnostic against the same fixture now correctly returns
  exactly one issue from the queried series.
- The `series_volume` filter (used for multi-volume series like
  "Spider-Man Vol 2") was NOT tested in this diagnostic — `profile.volume`
  was None for American Ronin. May or may not have the same naming
  issue. Left as follow-up.
