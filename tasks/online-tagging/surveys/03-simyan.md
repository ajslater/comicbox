# Simyan (ComicVine API client) Survey

Source: <https://github.com/Metron-Project/Simyan> (v2.0.0, GPL-3.0). PyPI: `Simyan`.

## Auth
- ComicVine API key (free, but requires free ComicVine/GameSpot account; obtained at <https://comicvine.gamespot.com/api/>).
- Passed at construction: `Comicvine(api_key="...", cache=...)`. Sent as `?api_key=` query param.
- Errors: `AuthenticationError` (401), `RateLimitError` (420/429), `ServiceError` (other; 404 also).

## Rate Limit
- Hardcoded local limiter via `pyrate_limiter`: `Rate(1, SECOND)` and `Rate(200, HOUR)`, stored in a `SQLiteBucket` persisted to disk (survives restarts).
- `RateLimiterTransport` blocks client-side per request, keyed by URL path. ComicVine documents ~200/resource/hour plus a velocity limit.
- On real 420/429 raises `RateLimitError`; **no auto-retry/backoff**.

## Core Methods (signatures)
All on `simyan.comicvine.Comicvine`:
- `search(resource: ComicvineResource, query: str, max_results=500) -> list[Basic*]` — enum: ISSUE, VOLUME, PUBLISHER, CHARACTER, TEAM, STORY_ARC, CREATOR, LOCATION, CONCEPT, POWER, ORIGIN, ITEM.
- `list_publishers(params=None, max_results=500) -> list[BasicPublisher]`
- `list_volumes(params=None, max_results=500) -> list[BasicVolume]` (CV "volume" = series)
- `list_issues(params=None, max_results=500) -> list[BasicIssue]`
- Parallel `list_story_arcs / creators / characters / teams / locations / concepts / powers / origins / items`.
- `get_issue(issue_id) -> Issue` and parallel `get_volume / publisher / story_arc / creator / character / team / location / concept / power / origin / item`.
- No "find by series+issue+year" helper — use `list_issues(params={"filter": "volume:<id>,issue_number:<n>"})` or `search(ISSUE, "<title> #<n>")` and filter client-side.
- Filters use a single string `"filter": "field:value,field2:value2"`. Pagination internal (100/page, walks until `max_results`).

## Response Shape (Issue)
Pydantic v2 models in `simyan.schemas`. `BasicIssue` (search/list): `id`, `name`, `number` (alias `issue_number`), `cover_date`, `store_date`, `date_added`, `date_last_updated`, `description` (HTML), `summary` (alias `deck`), `aliases`, `volume: GenericEntry`, `image: Images`, `associated_images: list[AssociatedImage]`, `api_url`, `site_url`.

`Issue` (from `get_issue`) extends `BasicIssue` with: `characters` (alias `character_credits`), `concepts` (`concept_credits`), `creators` (`person_credits`, `list[GenericCreator]` with `roles` from `role`), `locations` (`location_credits`), `objects` (`object_credits`), `story_arcs` (`story_arc_credits`), `teams` (`team_credits`), `deaths` (`character_died_in`), `teams_disbanded`, plus six `first_appearance_*` lists.

## Cover Image
`Images` model on every resource exposes 9 URL sizes: `icon_url`, `tiny_url`, `small_url`, `thumbnail` (alias `thumb_url`), `medium_url`, `large_screen_url` (alias `screen_large_url`), `screen_url`, `super_url`, `original_url`, plus free-text `tags` (alias `image_tags`). `associated_images` carries variant covers as `AssociatedImage` (`original_url`, `id`, `caption`, `tags`).

## Caching
Built-in `simyan.cache.SQLiteCache` — pass to `Comicvine(cache=...)` (or `None` to disable). Keys are URL + sorted query string; transparent. Rate-limit bucket uses a separate SQLite file.

## Install / Deps
`pip install Simyan`. Python >=3.10. Runtime deps: `httpx`, `pydantic` v2, `pyrate-limiter`. License GPL-3.0-or-later.

## Gotchas
- CV's API is notoriously slow (multi-second responses); the 1/sec local limit compounds latency — plan async/batched UX.
- `description` and other text fields contain raw HTML; needs stripping for display.
- "volume" = series; "issue" = single comic. Easy to mis-name in mapping.
- `GenericCreator.roles` is a comma-joined string ("writer, penciler"), not a list — split on `,`.
- `search` results are `Basic*` only; must call `get_issue(id)` to retrieve credits.
- CV filter syntax is finicky about exact field names and ordering.
- 404 maps to `ServiceError("Resource not found")` — no distinct exception.
- GPL-3.0 license — relevant if comicbox vendors or links it tightly.
