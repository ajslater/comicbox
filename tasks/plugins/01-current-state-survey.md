# Plugin Refactor — Current-State Survey

**Branch:** `plugins` (off `online-tagging` @ 7fd1971) **Goal of refactor (per
[TODO.md §6](../online-tagging/TODO.md)):** Consolidate each metadata format
into a **self-contained module** owning schema + transforms + source
registration + format registration. Static wiring, no dynamic discovery (Flavor
A; Flavor B / `entry_points` is off-roadmap, see
[META-PLAN.md §9](../online-tagging/META-PLAN.md)).

This is a survey only — no design proposed here. Everything cited with
`file:line` for click-through. Companion doc `02-plan.md` will sit on top of
this.

---

## Scope note: 7 named vs. 12 in the registry

[TODO.md §6](../online-tagging/TODO.md) originally named 8 formats: ComicInfo,
MetronInfo, ComicBookInfo, CoMet, ComicTagger, PDF, Metron API, ComicVine API.
**ComicTagger was removed pre-Phase 1** (see NEWS v4.0.0 Breaking Changes), so 7
remain. `MetadataFormats` has **12 enum entries** total — the extras are:

- `PDF_XML` (treated as a sub-variant of PDF; same module dir)
- `FILENAME` (filename-only parser; no archive content)
- `COMICBOX_YAML`, `COMICBOX_JSON`, `COMICBOX_CLI_YAML` (native serialization)

All 12 have their own schema and transform code. Scope resolved in `02-plan.md`:
the refactor covers all 12 (was 13 — ComicTagger dropped before refactor began).

---

## Section 1 — Per-format breakdown

### ComicInfo

| Aspect                       | Location                                                                                                                                                                                                |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Schema class(es)             | [comicbox/schemas/comicinfo.py:192](../../comicbox/schemas/comicinfo.py) `ComicInfoSchema`; `:114` `ComicInfoSubSchema`; `:94` `XmlPageInfoSchema`                                                      |
| Transform class(es)          | [comicbox/transforms/comicinfo/\_\_init\_\_.py](../../comicbox/transforms/comicinfo/__init__.py) `ComicInfoTransform`; sub-transforms: `identifiers.py`, `pages.py`, `reprints.py`, `storyarcs.py`      |
| `MetadataFormats` entry      | [comicbox/formats.py:89-96](../../comicbox/formats.py) — `COMIC_INFO = MetadataFormat("ComicInfo", frozenset({"cr","ci","cix",...}), "ComicInfo.xml", ComicInfoTransform, has_pages=True, lexer="xml")` |
| `MetadataSources` membership | [comicbox/sources.py:31,57,77,92](../../comicbox/sources.py) — CONFIG, ARCHIVE_FILE, CLI, API                                                                                                           |
| Box mixin hooks              | [comicbox/box/dump.py:71-72](../../comicbox/box/dump.py) (PDF→CBZ default); [comicbox/box/validate/\_\_init\_\_.py:28](../../comicbox/box/validate/__init__.py) (`FMT_VALIDATOR_MAP`)                   |
| CLI / config                 | [comicbox/cli.py:298-306](../../comicbox/cli.py) (format help table); [comicbox/config/computed.py:13-21](../../comicbox/config/computed.py) (`_FORMATS_WITH_TAGS_WITHOUT_IDS`)                         |
| Tests                        | [tests/schemas/test_cix.py](../../tests/schemas/test_cix.py)                                                                                                                                            |

### MetronInfo

| Aspect                       | Location                                                                                                                                                                                                                                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Schema class(es)             | [comicbox/schemas/metroninfo/\_\_init\_\_.py:139](../../comicbox/schemas/metroninfo/__init__.py) `MetronInfoSchema`; `:71` `MetronInfoSubSchema`; sub-schemas: `credits.py`, `identifiers.py`, `publishing.py`, `price.py`, `resource.py`                                                  |
| Transform class(es)          | [comicbox/transforms/metroninfo/\_\_init\_\_.py](../../comicbox/transforms/metroninfo/__init__.py) `MetronInfoTransform`; sub-transforms: `credits.py`, `identifiers.py`, `identifier_attribute.py`, `identified_name.py`, `publishing_tags.py`, `reprints.py`, `resources.py`, `const.py` |
| `MetadataFormats` entry      | [comicbox/formats.py:97-104](../../comicbox/formats.py) — `METRON_INFO = MetadataFormat("MetronInfo", ..., MetronInfoTransform, has_pages=True, lexer="xml")`                                                                                                                              |
| `MetadataSources` membership | [comicbox/sources.py:30,56,77,91](../../comicbox/sources.py) — CONFIG, ARCHIVE_FILE, CLI, API                                                                                                                                                                                              |
| Box mixin hooks              | None format-specific                                                                                                                                                                                                                                                                       |
| CLI / config                 | [comicbox/cli.py:298-306](../../comicbox/cli.py) (format help table)                                                                                                                                                                                                                       |
| Tests                        | [tests/schemas/test_metron.py](../../tests/schemas/test_metron.py)                                                                                                                                                                                                                         |

### CoMet

| Aspect                       | Location                                                                                                                                                   |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Schema class(es)             | [comicbox/schemas/comet.py:86](../../comicbox/schemas/comet.py) `CoMetSchema`; `:26` `CoMetSubSchema`                                                      |
| Transform class(es)          | [comicbox/transforms/comet/\_\_init\_\_.py](../../comicbox/transforms/comet/__init__.py) `CoMetTransform`; sub-transform: `reprints.py`                    |
| `MetadataFormats` entry      | [comicbox/formats.py:75-81](../../comicbox/formats.py) — `COMET = MetadataFormat("CoMet", frozenset({"comet"}), "CoMet.xml", CoMetTransform, lexer="xml")` |
| `MetadataSources` membership | [comicbox/sources.py:33,58,81,94](../../comicbox/sources.py) — CONFIG, ARCHIVE_FILE, CLI, API                                                              |
| Box mixin hooks              | None format-specific                                                                                                                                       |
| CLI / config                 | [comicbox/cli.py:298-306](../../comicbox/cli.py) (format help table)                                                                                       |
| Tests                        | [tests/schemas/test_comet.py](../../tests/schemas/test_comet.py)                                                                                           |

### ComicBookInfo

| Aspect                       | Location                                                                                                                                                                 |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Schema class(es)             | [comicbox/schemas/comicbookinfo.py:65](../../comicbox/schemas/comicbookinfo.py) `ComicBookInfoSchema`; `:31` `ComicBookInfoSubSchema`; `:23` `ComicBookInfoCreditSchema` |
| Transform class(es)          | [comicbox/transforms/comicbookinfo/\_\_init\_\_.py](../../comicbox/transforms/comicbookinfo/__init__.py) `ComicBookInfoTransform`; sub-transform: `credits.py`           |
| `MetadataFormats` entry      | [comicbox/formats.py:82-88](../../comicbox/formats.py) — `COMIC_BOOK_INFO = MetadataFormat("ComicBookInfo", ..., ComicBookInfoTransform, lexer="json")`                  |
| `MetadataSources` membership | [comicbox/sources.py:32,47,59,79,93](../../comicbox/sources.py) — CONFIG, **ARCHIVE_COMMENT** (sole tenant), ARCHIVE_FILE, CLI, API                                      |
| Box mixin hooks              | [comicbox/box/sources.py:99-108](../../comicbox/box/sources.py) — `_get_source_comment_metadata` hardcodes "only one archive comment format exists"                      |
| CLI / config                 | [comicbox/cli.py:298-306](../../comicbox/cli.py); [comicbox/config/computed.py:13-21](../../comicbox/config/computed.py) (`_FORMATS_WITH_TAGS_WITHOUT_IDS`)              |
| Tests                        | [tests/schemas/test_cbi.py](../../tests/schemas/test_cbi.py)                                                                                                             |

### PDF (PDF + PDF_XML)

| Aspect                       | Location                                                                                                                                                                                  |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Schema class(es)             | [comicbox/schemas/pdf.py:50](../../comicbox/schemas/pdf.py) `MuPDFSchema`; `:100` `PDFXmlSchema`                                                                                          |
| Transform class(es)          | [comicbox/transforms/pdf/\_\_init\_\_.py](../../comicbox/transforms/pdf/__init__.py) `MuPDFTransform`, `PDFXmlTransform`; sub-transform: `credits.py`                                     |
| `MetadataFormats` entry      | [comicbox/formats.py:59-66](../../comicbox/formats.py) `PDF` (`enabled=PDF_ENABLED`); `:67-74` `PDF_XML` (`enabled=PDF_ENABLED`)                                                          |
| `MetadataSources` membership | [comicbox/sources.py:34](../../comicbox/sources.py) (CONFIG), `:43` (**ARCHIVE_PDF** sole tenant), `:80` (CLI), `:95-96` (API — `PDF` and `PDF_XML`)                                      |
| Box mixin hooks              | [comicbox/box/sources.py:110-130](../../comicbox/box/sources.py) `_get_source_pdf_metadata`; [comicbox/box/dump.py:45-72](../../comicbox/box/dump.py) `_ensure_pdf_to_cbz_default_format` |
| CLI / config                 | [comicbox/cli.py:19](../../comicbox/cli.py) (`_PDF_ENABLED` guard); `:644`, `:794-831` (`--pdf-page-format` flag); [comicbox/config/computed.py:13-21](../../comicbox/config/computed.py) |
| Tests                        | [tests/schemas/test_pdf_json.py](../../tests/schemas/test_pdf_json.py), [tests/schemas/test_pdf_xml.py](../../tests/schemas/test_pdf_xml.py)                                              |

### Metron API (online)

| Aspect                       | Location                                                                                                                                                                                                                                              |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Schema class(es)             | [comicbox/schemas/metron_api.py:26](../../comicbox/schemas/metron_api.py) `MetronApiSchema`; `:15` `MetronApiSubSchema`                                                                                                                               |
| Transform class(es)          | [comicbox/transforms/metron_api/\_\_init\_\_.py](../../comicbox/transforms/metron_api/__init__.py) `MetronApiTransform` — **explicit Python builder**, `SPECS_TO = MappingProxyType({})  # not used`, `SPECS_FROM = MappingProxyType({})  # not used` |
| `MetadataFormats` entry      | [comicbox/formats.py:105-112](../../comicbox/formats.py) — `METRON_API = MetadataFormat(..., MetronApiTransform, lexer="json", enabled=False)`                                                                                                        |
| `MetadataSources` membership | [comicbox/sources.py:64-67](../../comicbox/sources.py) `METRON_API` (sole tenant of its own source); set via online lookup, not `SOURCE_METHOD_MAP`                                                                                                   |
| Box mixin hooks              | [comicbox/box/online_lookup.py:63-68](../../comicbox/box/online_lookup.py) `_DEFAULT_SOURCE_FACTORIES["metron"]`; `:72-74` `_ONLINE_SOURCE_ENUMS`; [comicbox/box/sources.py:187-193](../../comicbox/box/sources.py) `SOURCES_SET_ELSEWHERE` bypass    |
| CLI / config                 | [comicbox/cli.py:96-109](../../comicbox/cli.py) `_ONLINE_SOURCES_INFO` table entry                                                                                                                                                                    |
| Tests                        | [tests/unit/test_metron_transform.py](../../tests/unit/test_metron_transform.py)                                                                                                                                                                      |

### ComicVine API (online)

| Aspect                       | Location                                                                                                                                                                                                                                       |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Schema class(es)             | [comicbox/schemas/comicvine_api.py:24](../../comicbox/schemas/comicvine_api.py) `ComicVineApiSchema`; `:15` `ComicVineApiSubSchema`                                                                                                            |
| Transform class(es)          | [comicbox/transforms/comicvine_api/\_\_init\_\_.py](../../comicbox/transforms/comicvine_api/__init__.py) `ComicVineApiTransform` — explicit Python builder, no `SPECS_TO`/`SPECS_FROM`                                                         |
| `MetadataFormats` entry      | [comicbox/formats.py:113-120](../../comicbox/formats.py) — `COMICVINE_API = MetadataFormat(..., ComicVineApiTransform, lexer="json", enabled=False)`                                                                                           |
| `MetadataSources` membership | [comicbox/sources.py:68-71](../../comicbox/sources.py) `COMICVINE_API` (sole tenant)                                                                                                                                                           |
| Box mixin hooks              | [comicbox/box/online_lookup.py:63-68](../../comicbox/box/online_lookup.py) `_DEFAULT_SOURCE_FACTORIES["comicvine"]`; `:72-74` `_ONLINE_SOURCE_ENUMS`; [comicbox/box/sources.py:187-193](../../comicbox/box/sources.py) `SOURCES_SET_ELSEWHERE` |
| CLI / config                 | [comicbox/cli.py:96-109](../../comicbox/cli.py) `_ONLINE_SOURCES_INFO`                                                                                                                                                                         |
| Tests                        | [tests/unit/test_rich_transforms.py](../../tests/unit/test_rich_transforms.py) (covers both online transforms)                                                                                                                                 |

### Other formats (not in TODO §6 list, but in the registry)

These all live in the same registries and would need a scope decision:

- **FILENAME** — [comicbox/formats.py:44-50](../../comicbox/formats.py);
  [comicbox/schemas/filename.py](../../comicbox/schemas/filename.py);
  [comicbox/transforms/filename.py](../../comicbox/transforms/filename.py)
  (single-file transform). Sole tenant of `ARCHIVE_FILENAME` source.
- **COMICBOX_YAML / COMICBOX_JSON / COMICBOX_CLI_YAML** —
  [comicbox/formats.py:121-143](../../comicbox/formats.py); schemas under
  [comicbox/schemas/comicbox/](../../comicbox/schemas/comicbox/) (yaml.py,
  json_schema.py, cli.py); transforms under
  [comicbox/transforms/comicbox/](../../comicbox/transforms/comicbox/). These
  are the native serialization formats.

---

## Section 2 — Cross-cutting findings

### Central registries

**`MetadataFormats`** ([comicbox/formats.py:39-143](../../comicbox/formats.py))
— flat enum of all 13 format entries. Each value is a `MetadataFormat` dataclass
with `(label, aliases, filename, transform, has_pages, lexer, enabled)`. Order
is masking precedence (least → most authoritative).

**`MetadataSources`** ([comicbox/sources.py:20-100](../../comicbox/sources.py))
— flat enum of 11 source entries. Each value is a
`MetadataSource(label, formats, from_archive)`. Source order is masking
precedence; format tuples within each source are masking precedence under that
source. **Five separate hardcoded format lists** (CONFIG, ARCHIVE_FILE, CLI,
API, plus per-source ones for
METRON_API/COMICVINE_API/ARCHIVE_COMMENT/ARCHIVE_PDF/ARCHIVE_FILENAME).

### Shared infrastructure

Base classes / shared helpers used across formats:

- [comicbox/schemas/base.py](../../comicbox/schemas/base.py) — `BaseSchema`,
  `BaseSubSchema`
- [comicbox/schemas/xml_schemas.py](../../comicbox/schemas/xml_schemas.py) —
  `XmlSchema`, `XmlSubSchema`, `XmlSubHeadSchema`
- [comicbox/schemas/json_schemas.py](../../comicbox/schemas/json_schemas.py) —
  `JsonSchema`, `JsonSubSchema`
- [comicbox/transforms/base.py](../../comicbox/transforms/base.py) —
  `BaseTransform` (`.to_comicbox()` / `.from_comicbox()` interface)
- [comicbox/transforms/spec.py](../../comicbox/transforms/spec.py) — `MetaSpec`
  (glom-based key-rename machinery used by all file-based transforms)
- [comicbox/transforms/identifiers.py](../../comicbox/transforms/identifiers.py),
  [comicbox/transforms/publishing_tags.py](../../comicbox/transforms/publishing_tags.py),
  [comicbox/transforms/xml_credits.py](../../comicbox/transforms/xml_credits.py),
  [comicbox/transforms/price.py](../../comicbox/transforms/price.py) —
  cross-format helpers
- [comicbox/online/transform_helpers.py](../../comicbox/online/transform_helpers.py)
  — online-API helpers (`build_identifier`, `credits_to_cb`, `reprints_to_cb`,
  `named_block`, `named_dict`)

### File-based vs online — structural differences

**File-based (6 named + 1 FILENAME + 3 native = 10 formats):**

- Schema lives in `comicbox/schemas/<format>.py` or `comicbox/schemas/<format>/`
- Transform uses `MetaSpec`-driven `SPECS_TO` / `SPECS_FROM` (glom key-mapping)
- Loaded via `SOURCE_METHOD_MAP` dispatch at
  [comicbox/box/sources.py:174-186](../../comicbox/box/sources.py)
- May appear in CONFIG / CLI / API sources (user-readable + user-writable)
- `enabled=True` (or `PDF_ENABLED` for PDF)

**Online (2 formats):**

- Schema is minimal — just `ROOT_TAG` / `ROOT_DATA_KEY` declarations
- Transform overrides `.to_comicbox()` with **explicit Python code**;
  `SPECS_TO`/`SPECS_FROM` are empty placeholders. From the metron_api docstring:
  "the source dict has irregular shapes (lists of nested objects, role lists,
  cross-source ids) that don't fit the simple key-rename pattern"
- **Bypasses** `SOURCE_METHOD_MAP`; routed via `ComicboxOnlineLookup` mixin
- Each is sole tenant of its own `MetadataSources` entry
- `enabled=False` — never user-readable/writable; only populated by online
  lookup
- No pages support
- Wired into
  [comicbox/box/online_lookup.py:63-68](../../comicbox/box/online_lookup.py)
  `_DEFAULT_SOURCE_FACTORIES` (a separate string-keyed registry) AND `:72-74`
  `_ONLINE_SOURCE_ENUMS` AND `:187-193` `SOURCES_SET_ELSEWHERE` AND
  [comicbox/cli.py:96-109](../../comicbox/cli.py) `_ONLINE_SOURCES_INFO`

### Recent online-tagging churn (touchpoints when wiring in Metron/CV)

Representative commits showing what got touched per phase:

- **`16063d89`** "ComicVine: fetch volume to populate publisher on issue tags" —
  extracted `_build_named_block` from `metron_api` into shared
  `transform_helpers.named_block`. Touched two transforms simultaneously.
- **`c4c867ab`** "Online: rich field coverage for Metron and ComicVine
  transforms" — 100+ line rewrites to both `comicvine_api/__init__.py` and
  `metron_api/__init__.py` for full-field coverage.
- **`5359cc4`** "Online: retry audit — wrap series_list/search/get_volume, bump
  budget" — infra, not format-structure.

Consistently-touched files when adding/extending online formats:
[comicbox/formats.py](../../comicbox/formats.py),
[comicbox/sources.py](../../comicbox/sources.py),
[comicbox/transforms/metron_api/\_\_init\_\_.py](../../comicbox/transforms/metron_api/__init__.py),
[comicbox/transforms/comicvine_api/\_\_init\_\_.py](../../comicbox/transforms/comicvine_api/__init__.py),
[comicbox/box/online_lookup.py](../../comicbox/box/online_lookup.py),
[comicbox/cli.py](../../comicbox/cli.py).

---

## Section 3 — Pain points (factual, not prescriptive)

### Hardcoded format/source lists scattered across files

1. [comicbox/sources.py:26-100](../../comicbox/sources.py) — five hardcoded
   format tuples in `MetadataSources` (CONFIG, ARCHIVE_FILE, CLI, API +
   per-source singletons). New format requires touching the relevant ones.
2. [comicbox/box/dump.py:11-14](../../comicbox/box/dump.py) — `ARCHIVE_FORMATS`
   derived from `ARCHIVE_FILE` + `ARCHIVE_COMMENT`.
3. [comicbox/box/validate/\_\_init\_\_.py:26-44](../../comicbox/box/validate/__init__.py)
   — `FMT_VALIDATOR_MAP` only covers 7 of 12 formats; 5 (PDF, PDF_XML, Filename,
   Metron API, ComicVine API) have no validator. Comments at `:39-42`
   acknowledge the gaps.
4. [comicbox/box/sources.py:16-21](../../comicbox/box/sources.py) —
   `FILENAME_FORMAT_MAP` (archive filename detection) derived from
   `ARCHIVE_FILE`.
5. [comicbox/config/computed.py:13-21](../../comicbox/config/computed.py) —
   `_FORMATS_WITH_TAGS_WITHOUT_IDS` hardcoded set; missing METRON_INFO; missing
   online formats. Maintenance hazard.
6. [comicbox/cli.py:298-306](../../comicbox/cli.py) — help table iterates
   `MetadataFormats` but filter at `:302-303` dims Comicbox formats by
   label-prefix check.

### Two conditional-enabling patterns

- **PDF** uses module-level `PDF_ENABLED` based on import availability
  ([comicbox/formats.py:65,73](../../comicbox/formats.py); guarded at
  [comicbox/box/load.py:102](../../comicbox/box/load.py); also at
  [comicbox/cli.py:19](../../comicbox/cli.py)).
- **Online APIs** use literal `enabled=False`
  ([comicbox/formats.py:111,119](../../comicbox/formats.py)) — never
  user-facing, only triggered by online-lookup machinery.
- No format-level abstraction for "needs credentials" / "archive-only" / "never
  user-writable." Each behavior lives scattered.

### Transform interface mismatch (file-based vs online)

- File-based transforms: declarative `SPECS_TO`/`SPECS_FROM` glom specs.
  Identical machinery for all 10 file-based formats.
- Online transforms: empty `SPECS_TO = MappingProxyType({})  # not used`,
  override `.to_comicbox()` with explicit Python. Reason quoted in
  [comicbox/transforms/metron_api/\_\_init\_\_.py](../../comicbox/transforms/metron_api/__init__.py):8-10
  — "irregular shapes don't fit the simple key-rename pattern."
- Both inherit `BaseTransform` but implement it in completely different styles.
  A new contributor must pick a side; mixing would be confusing.

### Awkward conditional patterns in `box/` dispatch

- [comicbox/box/sources.py:99-108](../../comicbox/box/sources.py)
  `_get_source_comment_metadata` assumes "only one archive comment format
  exists" — if a second comment-level format were added, this silently breaks
  (only reads `.formats[0]`).
- [comicbox/box/dump.py:45-53](../../comicbox/box/dump.py)
  `_ensure_pdf_to_cbz_default_format` hardcodes "PDF→CBZ defaults to ComicInfo."
  Not parameterized; new archive-writable formats wouldn't pick up an analogous
  default.
- [comicbox/box/sources.py:174-186](../../comicbox/box/sources.py)
  `SOURCE_METHOD_MAP` — each source type maps to one retrieval method; a new
  source type requires a new method + entry.
- [comicbox/box/online_lookup.py:63-68](../../comicbox/box/online_lookup.py)
  `_DEFAULT_SOURCE_FACTORIES` — string-keyed (`"metron"` / `"comicvine"`) which
  duplicates the enum at `:72-74`. Adding a third online source (e.g., GCD,
  deferred in TODO) requires three updates here.

---

## Section 4 — Files-touched checklist for "add a new format"

Concrete punch-list — what someone would edit today to add a new format. Note
how many distinct module boundaries are involved.

**Schema + transform (new code, expected):**

- [comicbox/schemas/](../../comicbox/schemas/) — new `<format>.py` or
  `<format>/` package
- [comicbox/transforms/](../../comicbox/transforms/) — new `<format>/` package
  with `__init__.py` + sub-transforms

**Registries (edit existing — the pain points):**

- [comicbox/formats.py:39-143](../../comicbox/formats.py) — add
  `MetadataFormats.<NAME>` enum entry
- [comicbox/sources.py:26-100](../../comicbox/sources.py) — add to relevant
  `MetadataSources` tuples (CONFIG / ARCHIVE_FILE / CLI / API as applicable)

**Box mixins (often required):**

- [comicbox/box/sources.py:16-21](../../comicbox/box/sources.py) —
  `FILENAME_FORMAT_MAP` if format has an archive filename
- [comicbox/box/sources.py:174-186](../../comicbox/box/sources.py) —
  `SOURCE_METHOD_MAP` if new source type
- [comicbox/box/dump.py](../../comicbox/box/dump.py) — any format-specific
  dump/export rules (cf. PDF→CBZ default)
- [comicbox/box/validate/\_\_init\_\_.py:26-44](../../comicbox/box/validate/__init__.py)
  — `FMT_VALIDATOR_MAP` entry (optional)

**Config / CLI:**

- [comicbox/config/computed.py:13-21](../../comicbox/config/computed.py) —
  `_FORMATS_WITH_TAGS_WITHOUT_IDS` if applicable
- [comicbox/config/formats.py](../../comicbox/config/formats.py) —
  format-specific config options
- [comicbox/cli.py](../../comicbox/cli.py) — flags + help text (e.g.
  `--pdf-page-format` style), display rules at `:298-306` if developer-only

**Online-only (if applicable):**

- [comicbox/online/sources/](../../comicbox/online/sources/) — new
  `OnlineSource` subclass
- [comicbox/box/online_lookup.py:63-68](../../comicbox/box/online_lookup.py) —
  `_DEFAULT_SOURCE_FACTORIES` entry
- [comicbox/box/online_lookup.py:72-74](../../comicbox/box/online_lookup.py) —
  `_ONLINE_SOURCE_ENUMS`
- [comicbox/box/sources.py:187-193](../../comicbox/box/sources.py) —
  `SOURCES_SET_ELSEWHERE`
- [comicbox/cli.py:96-109](../../comicbox/cli.py) — `_ONLINE_SOURCES_INFO`

**Tests:**

- [tests/schemas/test\_<format>.py](../../tests/schemas/) — schema round-trip
- [tests/unit/test\_<format>\_transform.py](../../tests/unit/) — transform
  round-trip
- [tests/files/](../../tests/files/) — fixtures

**Total touchpoints to add a new file-based format:** ~6-10 files across
schemas, transforms, formats.py, sources.py, box/, config/, cli.py, tests.
**Total touchpoints to add a new online format:** ~10-14 files (adds
online/sources, online_lookup, online_sources_info on top of the file-based
set).

That sprawl is the case for the refactor.
