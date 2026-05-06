# esak — Marvel Developer API client

Repo: https://github.com/Metron-Project/Esak (MIT, fork of `marvelous`) Docs:
https://esak.readthedocs.io/

## Critical status

Marvel API was shut down November 2025; esak repo archived 2026-02-02
(read-only). esak is a historical reference, not a live integration target.
Below describes how it worked.

## Auth

Marvel required a public + private key pair from https://developer.marvel.com
(free, account + registered referrer domains). Every request needed `apikey`,
`ts`, and `hash = md5(ts + private_key + public_key)`.

esak hides this in `Session._update_params()`. Entry point:

```python
esak.api(public_key: str | None = None,
         private_key: str | None = None,
         cache: SqliteCache | None = None) -> Session
```

Missing keys raise `AuthenticationError`.

## Rate limits

Marvel's documented cap was 3000 calls/day per public key (no published
per-second limit). esak does **not** implement backoff or throttling — failures
surface as `ApiError`. Caching is the recommended mitigation.

## Core methods

`Session` exposes single-resource getters and list endpoints for every Marvel
entity:

- `comic(_id: int) -> Comic`
- `comics_list(params: dict | None = None) -> list[Comic]`
- `series(_id) / series_list(params)`
- `creator(_id) / creators_list(params)`
- `character(_id) / characters_list(params)`
- `story(_id) / stories_list(params)`
- `event(_id) / events_list(params)`

Plus ~40 cross-relation methods like `comic_characters(_id, params)`,
`series_creators(_id, params)`.

Search by series + issue + year goes through
`comics_list({"series": series_id, "issueNumber": 5, "startYear": 2020})` — no
dedicated convenience method; the `params` dict is forwarded to Marvel's filter
query string.

## Response shape

`Comic` (marshmallow-parsed) fields: `id`, `digital_id`, `title`,
`issue_number`, `variant_description`, `description`, `isbn`, `upc`,
`diamond_code`, `ean`, `issn`, `format`, `page_count`, `text_objects`, `series`,
`variants`, `collections`, `collected_issues`, `dates`, `prices`, `images`,
`creators`, `characters`, `stories`, `events`.

## Cover image

Marvel responses ship images as `{path, extension}` pairs. esak's `map_images`
validator joins them as `"{path}.{extension}"` and stores them in
`Comic.images: list[HttpUrl]`. `thumbnail` uses the same shape.

Marvel CDN pattern:
`https://i.annihil.us/u/prod/marvel/i/mg/<hash>/<id>/<variant>.jpg`. To request
a sized variant insert a Marvel-defined suffix between path and extension:
`portrait_small/medium/xlarge/fantastic/uncanny/incredible`,
`standard_small/medium/large/xlarge/fantastic/amazing`, `landscape_*`, `detail`,
`full` (full-size original). esak stores the unsuffixed URL — callers append the
size token themselves.

## Caching

Built-in `esak.sqlite_cache.SqliteCache(db_name, expire_days)` with `get`,
`store`, `cleanup`. Passed into `esak.api(..., cache=...)`; expired rows pruned
at init.

## Install / deps

`pip install esak`. Runtime: `requests`, `marshmallow`, `pydantic` (for
`HttpUrl`). Stdlib `sqlite3` for the cache.

## Gotchas

- Marvel-only catalog — no DC, Image, indie, or manga.
- API shut down Nov 2025; library archived. Reference only.
- Marvel terms required attribution: "Data provided by Marvel. (c) Marvel" near
  rendered data, plus link back to marvel.com on each marvel-sourced field.
- Authorized referrer enforcement scoped browser-side calls to registered
  domains.
- No throttling/backoff — relied on the cache and caller discipline.
- `params` dicts use Marvel's raw camelCase filter names (`dateDescriptor`,
  `noVariants`, `formatType`, `startYear`); typos silently return empty results.
