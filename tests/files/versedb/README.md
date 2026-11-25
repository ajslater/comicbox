# VerseDB API fixtures

Data from [VerseDB](https://versedb.com).

Real API responses recorded on 2026-11-21 (Phase 0 of the VerseDB source plan),
trimmed only by shortening lists, with real title names swapped for fictitious
ones. Every key the `versedb` SDK's models require is kept, so tests that serve
these through `httpx.MockTransport` run the SDK's real parsing.

- `issue_regular.json`: `GET /api/v1/issues/1215061`, Absolute Bladehawk (2024)
  #24.
- `issue_manga.json`: `GET /api/v1/issues/1214514`, Medalist volume 14.
- `issue_collected.json`: `GET /api/v1/issues/1222815`, Metal Hurlant TPB #6.
- `issue_missing.json`: the 404 body.
- `series_search.json`: `GET /api/v1/series?q=Absolute Bladehawk&limit=10`.
- `list_issues.json`:
  `GET /api/v1/issues?series_ids=139382,165850,54159&q=1&include=series`.
