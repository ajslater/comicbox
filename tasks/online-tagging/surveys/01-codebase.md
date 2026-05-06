# Codebase Survey: Online Metadata Tagging

## SOURCES

`comicbox/sources.py:9` defines `MetadataSource` (dataclass: `label`,
`path`, `formats`, `from_archive`) and `MetadataSources` enum
(`comicbox/sources.py:21`). Enum order = source precedence; per-source
`formats` tuple = format precedence within. Existing values: `CONFIG`,
`ARCHIVE_FILENAME`, `ARCHIVE_PDF`, `ARCHIVE_COMMENT`, `ARCHIVE_FILE`,
`IMPORT_FILE`, `CLI`, `API`, `LEGACY_NESTED`. The `API` source
(`comicbox/sources.py:80`) is generic — used for programmatic injection
via `add_metadata()`.

`comicbox/box/sources.py:24` (`ComicboxSources` mixin) implements the
contract. Each source has a `_get_source_*_metadata()` method returning
`list[SourceData]` (`comicbox/box/init.py:41`: `data`, `path`, `fmt`,
`from_archive`). Dispatch is via `SOURCE_METHOD_MAP`
(`comicbox/box/sources.py:174`); `API` and `LEGACY_NESTED` are in
`SOURCES_SET_ELSEWHERE` (`comicbox/box/sources.py:187`) — populated
imperatively, not pulled. `add_source()`
(`comicbox/box/sources.py:224`) appends to `_sources[source]` and
clears forward caches.

## TRANSFORMS

`comicbox/transforms/base.py:20` defines `BaseTransform`. Subclasses
set three class attrs: `SCHEMA_CLASS`, `SPECS_TO`, `SPECS_FROM`. The
two methods are `to_comicbox()` (line 39) and `from_comicbox()` (line
46) — both run `glom(data, dict(specs))` then `schema.load()`.

`comicbox/transforms/comicinfo/__init__.py:216` (`ComicInfoTransform`)
shows the pattern. Static `frozenbidict` key maps (`SIMPLE_KEY_MAP`
line 177, `NAME_OBJ_KEY_MAP` line 204, `PAGE_KEY_MAP` line 165) define
field-by-field renames. `SPECS_TO` and `SPECS_FROM` are built by
`create_specs_to_comicbox()` /
`create_specs_from_comicbox()` (`comicbox/transforms/spec.py:144`,
`:157`) from `MetaSpec` entries (`comicbox/transforms/spec.py:17`).
Format-specific subdirs (e.g. `comicbox/transforms/comicinfo/pages.py`,
`identifiers.py`, `reprints.py`, `storyarcs.py`) hold non-trivial
spec builders. Each format is registered in
`comicbox/formats.py:37` (`MetadataFormats` enum) tying label,
config-key aliases, filename, transform class, and `enabled` flag.

## CONFIG

`comicbox/config/__init__.py:36` declares the confuse `_TEMPLATE`;
`get_config()` (line 145) calls `read_config_sources()`
(`comicbox/config/read.py:21`) which layers default → user → env →
args. Defaults live in `comicbox/config_default.yaml`. Validated
AttrDict is rebuilt into a frozen `ComicboxSettings` dataclass
(`comicbox/config/settings.py:18`) by `_build_settings()`
(`comicbox/config/__init__.py:94`). Computed/derived keys go under
nested `computed:` (`config/__init__.py:76`,
`comicbox/config/computed.py`). New per-API credentials and per-source
toggles would be new fields in both `_TEMPLATE` and `ComicboxSettings`
plus defaults in `config_default.yaml`.

## CLI

`comicbox/cli.py:438` (`get_args()`) builds an `argparse.ArgumentParser`
with three groups: Options (line 176), Actions (line 322), Targets
(line 429). All flags are flat — no subcommands. CSV-style values use
`CSVAction` (line 80). `post_process_args()` (line 467) maps a few
flags into print-phase characters. The Namespace is wrapped as
`Namespace(comicbox=cns)` (`comicbox/cli.py:486`) and handed to
`Runner` (`comicbox/run.py:20`); the same Namespace flows into
`get_config()`. New flags would be added to one of the existing
groups; no sub-flag pattern exists today.

## MERGE

`comicbox/box/merge.py:11` (`ComicboxMerge`) iterates
`MetadataSources` in declared order
(`comicbox/box/merge.py:36`). Within each source,
`_merge_metadata_by_source()` (line 14) reorders the normalized list
by the source's `formats` tuple (reversed) and feeds them to a
`Merger`. Two strategies: `AdditiveMerger` (default) and
`UpdateMerger` (when `replace_metadata` is set), both in
`comicbox/merge/__init__.py:22,44`; `mergedeep` does the deep work
(`comicbox/merge/mergedeep.py`). Precedence is **not** runtime
configurable — it's the enum order. An online source would slot in as
a new `MetadataSources` member; its position in the enum determines
precedence.

## IDENTIFIERS

`comicbox/identifiers/__init__.py` defines `DEFAULT_ID_SOURCE` (=
`IdSources.COMICVINE`), `DEFAULT_ID_TYPE` (= `"issue"`), and
`IDENTIFIER_RE_EXP`. `comicbox/identifiers/identifiers.py:112`
(`IDENTIFIER_PARTS_MAP`) catalogues 16 external sources (ComicVine,
Metron, GCD, Marvel, ISBN, ASIN, Comixology, MangaDex, MAL, AniList,
Kitsu, etc.) — each an `IdentifierParts` (line 67) with domain, slug
map (`IdentifierTypes` line 24), URL regex, and template. Functions
`get_identifier_url()` (line 260), `create_identifier()` (line 270),
`get_id_source_from_url()` (line 296) parse and emit URLs/keys. URN
form is in `comicbox/identifiers/urns.py`; alt parsing in
`comicbox/identifiers/other.py`. No HTTP/API client exists — only
parsing of stored IDs/URLs.

## PAGES / COVER

`comicbox/box/pages/covers.py:16` (`ComicboxPagesCovers`).
`get_cover_page(skip_metadata=False)` (line 86) returns cover image
**bytes**. `_get_cover_page_skip_metadata()` (line 57) bypasses
metadata parsing entirely — first archive page, fewest dependencies.
`_get_cover_page()` (line 67) tries hint-driven cover paths in order.
`generate_cover_paths()` (line 30) yields candidates from pages
metadata, `cover_image` field, then index-0 fallback. Underlying read
is `_archive_readfile()` (`comicbox/box/archive/read.py:84`) which
handles all archive types incl. PDF page rendering. No PIL conversion
in core — bytes only. `comicbox/box/archive/pages.py:11`
(`get_page_by_filename`) and `:23` (`get_page_by_index`) round out the
public API.

## INTEGRATION POINTS

A new online MetadataSource would minimally touch:

- `comicbox/sources.py` — add new `MetadataSources` enum value with
  precedence-correct position and supported `formats` tuple.
- `comicbox/box/sources.py` — add to `SOURCES_SET_ELSEWHERE` (if
  imperatively populated like `API`) or add a `_get_source_*` method
  and entry in `SOURCE_METHOD_MAP`.
- `comicbox/config/__init__.py` + `comicbox/config/settings.py` +
  `comicbox/config_default.yaml` — credentials/toggles in
  `_TEMPLATE`, `ComicboxSettings`, defaults.
- `comicbox/cli.py` — flags in `_add_option_group` /
  `_add_action_group`.
- `comicbox/box/__init__.py:24` (`_CONFIG_ACTIONS`) or `run()` (line
  43) — wire any new top-level action.
- A new transform isn't strictly required if the online source emits
  an existing format (e.g. MetronInfo). If a new format is needed, add
  a `comicbox/transforms/<source>/` and register in
  `comicbox/formats.py:37`.
