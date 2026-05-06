# Mokkari — survey

Python wrapper for the Metron Comic Book Database REST API.

## Install / deps

- PyPI: `pip install mokkari` (current 3.25.x as of 2026-05).
- Python: `>=3.10`.
- Runtime deps from `pyproject.toml`:
  - `requests>=2.26.0,<3` (HTTP client — **not** httpx)
  - `pydantic>=2.10.3,<3` (pydantic v2)
  - `pyrate-limiter>=4` (local rate limiting)
- License: GPL-3.0-or-later.

## Auth

Metron account required (created at metron.cloud). Pass username + password —
no API key (Metron has no key-based auth):

```python
import mokkari
m = mokkari.api(username, passwd)
```

`mokkari.api(...)` in `mokkari/__init__.py` returns a `Session`. Signature:

```python
mokkari.api(
    username: str | None = None,
    passwd: str | None = None,
    cache: sqlite_cache.SqliteCache | None = None,
    user_agent: str | None = None,
    dev_mode: bool = False,
    bucket: AbstractBucket | None = None,
)
```

`user_agent` is recommended (e.g. `"Comicbox/x.y.z"`).

## Rate limit

Metron enforces **20 req/min, 5,000 req/day**. Mokkari enforces locally via
`pyrate-limiter` before the wire — exceeding raises `RateLimitError` with a
`retry_after` (seconds) attribute. No automatic backoff/retry; caller must
catch and sleep. Server-side 429 surfaces the same exception.

## Caching

Built-in SQLite cache `mokkari.sqlite_cache.SqliteCache`:

```python
SqliteCache(db_name: str = "mokkari_cache.db", expire: int | None = None)
```

Pass an instance via `cache=` to `mokkari.api(...)`. All GETs consult it.
`expire` is days-to-live (`None` = forever). Methods: `get`, `store`, `cleanup`.

## Core methods (Session)

In `mokkari/session.py`:

- `issue(_id: int, if_modified_since: datetime | None = None) -> Issue | None`
- `issues_list(params: dict[str, str | int] | None = None) -> list[BaseIssue]`
- `series(_id: int, if_modified_since: datetime | None = None) -> Series | None`
- `series_list(params: dict[str, str | int] | None = None) -> list[BaseSeries]`
- Plus `character`(s), `team`(s), `arc`(s), `creator`(s), `publisher`(s)
  with POST/PATCH variants (admin-only).

Filters are a raw `params` dict pasted into the querystring. Known keys:

- `issues_list`: `series`, `number`, `cover_date`, `store_date_range_after`,
  `store_date_range_before`, `publisher_name`, `modified_gt`/`_lt`.
- `series_list`: `name`, `publisher`, `year_began`, `modified_gt`/`_lt`.

Search by **series+number+year** = `series_list(name=, year_began=)` first,
then `issues_list({"series": <id>, "number": "1"})`.

## Response shape — Issue

`mokkari.schemas.issue.Issue` (pydantic v2) extends `CommonIssue`:

- `id`, `number`, `alt_number`, `cover_date`, `store_date`, `foc_date`
- `image: HttpUrl | None`, `cover_hash: str`
- `series: IssueSeries` — has `id`, `name`, `sort_name`, `volume`,
  `year_began`, `series_type`, `genres`
- `publisher`, `imprint`, `rating` (all `GenericItem`)
- `collection_title`, `story_titles: list[str]`
- `price`, `price_currency`, `sku`, `isbn`, `upc`, `page_count`, `desc`
- `arcs`, `characters`, `teams`, `universes` (all `list[BaseResource]`)
- `credits: list[Credit]`, `reprints: list[Reprint]`, `variants: list[Variant]`
- `cv_id`, `gcd_id` (Comic Vine + GCD cross-IDs)
- `resource_url`, `modified`

`issues_list` returns lighter `BaseIssue` (id, issue name, cover_date,
image, cover_hash, modified) — fetch full `Issue` via `issue(id)`.

## Cover image

`issue.image` is an HTTPS URL (also on `BaseIssue`). Single full-size
PNG/JPG; no thumbnail variants. `cover_hash` is Metron's precomputed pHash
string — disambiguate without downloading covers.

## Gotchas

- `if_modified_since` returns `None` on 304 — caller must distinguish
  "not modified" from "not found".
- `RateLimitError` fires pre-emptively from the local limiter; no retry.
- Filters are raw dicts passed straight to the REST API; field names must
  match Metron exactly. No typed filter helpers.
- No anonymous tier — real Metron credentials required.
