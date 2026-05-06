# Grayven — Grand Comics Database (GCD) client

Repo: https://github.com/Metron-Project/Grayven (MIT) — Docs: https://grayven.readthedocs.io/ — Upstream API: https://www.comics.org/api

Version 0.5.0 (March 2026) — pre-1.0, low adoption, active.

## Auth

GCD's API is **not** anonymous. Grayven authenticates with the user's GCD website credentials over HTTP Basic Auth — no API-key flow. Users register a free account at https://www.comics.org/accounts/register/ and pass email + password. Credentials are never written to the SQLite cache.

```python
GrandComicsDatabase(
    email: str,
    password: str,
    cache: SQLiteCache | None,
    base_url: str = "https://www.comics.org/api",
    user_agent: str | None = None,
    timeout: float = 30,
    limiter: Limiter = Limiter(RATELIMIT_BUCKET),
)
```

## Rate limits / etiquette

GCD is volunteer-run; Grayven enforces politeness client-side via `pyrate_limiter.Limiter` backed by `SQLiteBucket` so quotas survive process restarts. Default `RATELIMIT_BUCKET`: **20 req/min, 200 req/hour, 2000 req/day**. The limiter blocks/raises when exceeded; no automatic retry on 429.

Default User-Agent is auto-built as `Grayven/{version} ({OS}: {release}; Python v{version})`. Transport is `httpx` with `timeout=30s` default.

## Core methods

```python
get_issue(issue_id: int) -> Issue
list_issues(series_name: str, issue_number: int,
            year: int | None = None, max_results: int = 500) -> list[BasicIssue]
list_onsale_weekly_issues(year: int, week: int, max_results: int = 500) -> list[BasicIssue]

get_series(series_id: int) -> Series
list_series(name: str | None = None, year: int | None = None,
            max_results: int = 500) -> list[Series]

get_publisher(publisher_id: int) -> Publisher
list_publishers(max_results: int = 500) -> list[Publisher]
```

`list_issues(series_name, issue_number, year)` is the natural search-by-series+issue+year entry point.

## Response shape (Pydantic)

**`BasicIssue`**: `api_url`, `series_name`, `descriptor`, `publication_str`, `price`, `page_count`, `variant_of`, `series` (URL); computed `id`, `series_id`, `publication_date`.

**`Issue`** (extends `BasicIssue`): `number`, `volume`, `variant_name`, `title`, `key_str`, `editing`, `indicia_publisher`, `brand_emblem`, `isbn`, `barcode`, `rating`, `on_sale_str`, `indicia_frequency`, `notes`, `indicia_printer`, `keywords`, `story_set` (list[Story]), `cover` (HttpUrl); computed `key_date`, `on_sale_date`.

**`Series`**: `api_url`, `name`, `country`, `language`, `active_issues` (URL list), `issue_descriptors`, `color`, `dimensions`, `paper_stock`, `binding`, `publishing_format`, `notes`, `year_began`, `year_ended`, `publisher` (URL); computed `id`, `publisher_id`.

Cross-references (`series`, `publisher`, `variant_of`, `active_issues`) come back as URLs that you re-fetch with `get_*` — IDs are regex-extracted.

## Cover image

`Issue.cover: HttpUrl` is a single primary cover URL. GCD is famously thorough on variants: variants are separate `BasicIssue` records linked via `variant_of`, so enumerating every cover for an issue means walking variant relationships, not reading a list off one issue. No `images: list[HttpUrl]` field.

## Caching

Optional `grayven.cache.SQLiteCache`. Keyed by URL with sorted query params (deterministic hits). `_get_request()` consults the cache before every HTTP call and writes responses back. Credentials never cached.

## Install / deps

`pip install Grayven`. Runtime: `httpx`, `pydantic`, `pyrate-limiter` (SQLite bucket), stdlib `sqlite3`.

## Gotchas

- Pre-1.0; expect breaking changes, pin tightly.
- Endpoint coverage partial vs upstream GCD — no creator search, no story-by-ID, no cover-art-credit endpoint.
- Many fields are loose strings (`publication_str`, `on_sale_str`, `price`, `volume`, `page_count`) — parsing is the caller's problem.
- Cross-references come as URLs not IDs — every traversal is another HTTP call. Cache aggressively.
- BasicAuth means the user's GCD password sits in client memory.
- Variant-cover discovery requires extra round-trips through `variant_of`.
- `list_*` caps at `max_results=500` and paginates internally; broad queries chew through the bucket fast.
