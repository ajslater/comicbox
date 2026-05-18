# Plugin Refactor — Plan

**Branch:** `plugins` (off `online-tagging` @ 7fd1971) **Companion:**
[01-current-state-survey.md](01-current-state-survey.md) **Scope (resolved):**
All **12** format entries in `MetadataFormats` — the 7 named in
[TODO.md §6](../online-tagging/TODO.md) (ComicTagger removed pre-Phase 1, see
NEWS v4.0.0) plus `PDF_XML`, `FILENAME`, `COMICBOX_YAML`, `COMICBOX_JSON`,
`COMICBOX_CLI_YAML`.

## 1. Goal

Each metadata format becomes a self-contained Python package owning its schema,
transform, registration data, and any format-specific hooks. The central
`MetadataFormats` / `MetadataSources` enums become **assembly points** that
import per-format declarations rather than the sources of truth for everything
format-related.

**Non-goals (explicit):**

- Flavor B (`entry_points` / third-party plugin packages). Declined per
  [META-PLAN §9](../online-tagging/META-PLAN.md).
- No dynamic discovery. Imports stay static and explicit.
- **No schema/transform behavior change.** This is pure organizational work;
  output bytes must be identical pre/post for every format.
- No new formats. Working with the existing 13.

## 2. Target architecture

### 2.1 Package layout

```
comicbox/formats/
├── __init__.py              # assembles MetadataFormats enum
├── _base.py                 # FormatRegistration dataclass, helpers
├── comet/
│   ├── __init__.py          # exports REGISTRATION
│   ├── schema.py            # CoMetSchema, CoMetSubSchema
│   └── transform/
│       ├── __init__.py      # CoMetTransform
│       └── reprints.py
├── comic_book_info/
│   ├── __init__.py
│   ├── schema.py
│   └── transform/
│       ├── __init__.py      # ComicBookInfoTransform
│       └── credits.py
├── comic_info/
│   ├── __init__.py
│   ├── schema.py
│   └── transform/
│       ├── __init__.py      # ComicInfoTransform
│       ├── identifiers.py
│       ├── pages.py
│       ├── reprints.py
│       └── storyarcs.py
├── comicvine_api/
│   ├── __init__.py
│   ├── schema.py
│   ├── transform.py         # explicit-Python builder, no sub-transforms
│   └── online_source.py     # ← currently comicbox/online/sources/comicvine.py
├── filename/
│   ├── __init__.py
│   ├── schema.py
│   └── transform.py         # single file, no sub-transforms
├── metron_api/
│   ├── __init__.py
│   ├── schema.py
│   ├── transform.py         # explicit-Python builder, no sub-transforms
│   └── online_source.py     # ← currently comicbox/online/sources/metron.py
├── metron_info/
│   ├── __init__.py
│   ├── schema/              # already a multi-file schema today
│   │   ├── __init__.py      # MetronInfoSchema, MetronInfoSubSchema
│   │   ├── credits.py
│   │   ├── identifiers.py
│   │   ├── publishing.py
│   │   ├── price.py
│   │   └── resource.py
│   └── transform/
│       ├── __init__.py      # MetronInfoTransform
│       ├── const.py
│       ├── credits.py
│       ├── identified_name.py
│       ├── identifier_attribute.py
│       ├── identifiers.py
│       ├── publishing_tags.py
│       ├── reprints.py
│       └── resources.py
├── native_cli_yaml/         # COMICBOX_CLI_YAML — sub-split TBD in pilot
├── native_json/             # COMICBOX_JSON
├── native_yaml/             # COMICBOX_YAML
└── pdf/                     # PDF + PDF_XML (both MuPDF and PDFXml schemas)
    ├── __init__.py
    ├── schema.py            # MuPDFSchema + PDFXmlSchema
    └── transform/
        ├── __init__.py      # MuPDFTransform + PDFXmlTransform
        └── credits.py
```

**Layout rule:** A format gets `transform/` (subpackage with main class in
`__init__.py`) iff it has any sub-transform files. A format with a single
transform gets `transform.py` (file). Same rule applies to `schema/` vs
`schema.py`. This mirrors the existing convention under
[comicbox/transforms/](../../comicbox/transforms/) and
[comicbox/schemas/](../../comicbox/schemas/) today — no invention of
`transforms_<thing>.py` siblings.

12 format entries map to **11 format packages** because `PDF` and `PDF_XML` ship
together (same `pdffile` dependency, same module today).

### 2.2 Per-format module contract

Each format package's `__init__.py` exports a single `REGISTRATION` object
(frozen dataclass). The central `formats.py` and `sources.py` read from
`REGISTRATION` and nothing else.

```python
# comicbox/formats/_base.py
from dataclasses import dataclass, field
from types import MappingProxyType

@dataclass(frozen=True, slots=True)
class FormatRegistration:
    """Everything a format module declares about itself."""

    # MetadataFormat data
    format: MetadataFormat                       # the existing dataclass

    # MetadataSources membership: {source_name: priority_within_source}
    # priority is 0-indexed; gaps allowed; central assembler sorts
    sources: MappingProxyType[str, int]

    # Optional hooks (None = no opt-in)
    validator: type[Validator] | None = None     # FMT_VALIDATOR_MAP
    archive_filename: str | None = None          # FILENAME_FORMAT_MAP (defaults to format.filename)
    has_tags_without_ids: bool = False           # _FORMATS_WITH_TAGS_WITHOUT_IDS
    archive_role: ArchiveRole | None = None      # see §3.2 — replaces hardcoded archive-comment/PDF dispatch
    online_source_factory: type[OnlineSource] | None = None  # online only
    cli_help_style: CliHelpStyle = CliHelpStyle.DEFAULT       # replaces label-prefix dimming check
    cli_info: OnlineSourceCliInfo | None = None  # online only — replaces _ONLINE_SOURCES_INFO
```

```python
# comicbox/formats/comet/__init__.py
from types import MappingProxyType
from comicbox.formats._base import FormatRegistration, MetadataFormat
from comicbox.formats.comet.transform import CoMetTransform

REGISTRATION = FormatRegistration(
    format=MetadataFormat(
        "CoMet",
        frozenset({"comet"}),
        "CoMet.xml",
        CoMetTransform,
        lexer="xml",
    ),
    sources=MappingProxyType({
        "CONFIG": 4,
        "ARCHIVE_FILE": 5,
        "CLI": 5,
        "API": 6,
    }),
)
```

```python
# comicbox/formats/__init__.py — the assembly point
from enum import Enum
from comicbox.formats.comet import REGISTRATION as _COMET
from comicbox.formats.comic_info import REGISTRATION as _COMIC_INFO
# ... 11 more imports

_ALL_REGISTRATIONS = (
    _FILENAME, _PDF, _PDF_XML, _COMET, _COMIC_BOOK_INFO,
    _COMIC_INFO, _METRON_INFO, _METRON_API, _COMICVINE_API,
    _COMICBOX_YAML, _COMICBOX_JSON, _COMICBOX_CLI_YAML,
)  # order = masking precedence

class MetadataFormats(Enum):
    FILENAME = _FILENAME.format
    PDF = _PDF.format
    # ... etc, one line per format
```

The central enum is still hand-written for static-type clarity, but its body is
one line per format and imports come from format modules. Everything _else_
about each format lives in the format module.

### 2.3 Source assembly

`MetadataSources` enum stops being a hand-maintained list of format tuples. The
enum is built **dynamically** from a single source-definition table plus
per-format `REGISTRATION.sources` data:

```python
# comicbox/sources.py (after refactor)

# Source order = source-level masking precedence (today's "Source order
# declares masking precedence" comment).
_SOURCE_DEFINITIONS: tuple[tuple[str, str, bool], ...] = (
    # (enum_member_name, label, from_archive)
    ("CONFIG",           "Config",          False),
    ("ARCHIVE_FILENAME", "Filename",        True),
    ("ARCHIVE_PDF",      "Archive Header",  True),
    ("ARCHIVE_COMMENT",  "Archive Comment", True),
    ("ARCHIVE_FILE",     "Archive File",    True),
    ("METRON_API",       "Metron API",      False),
    ("COMICVINE_API",    "ComicVine API",   False),
    ("IMPORT_FILE",      "Imported File",   False),
    ("CLI",              "Comicbox CLI",    False),
    ("API",              "API",             False),
)


def _formats_for_source(name: str) -> tuple[MetadataFormats, ...]:
    pairs = [
        (priority, fmt)
        for fmt in MetadataFormats
        if (priority := fmt.value.registration.sources.get(name)) is not None
    ]
    return tuple(fmt for _, fmt in sorted(pairs))


MetadataSources = Enum(
    "MetadataSources",
    {
        name: MetadataSource(
            label,
            formats=_formats_for_source(name),
            from_archive=from_archive,
        )
        for name, label, from_archive in _SOURCE_DEFINITIONS
    },
)
```

Source taxonomy lives in `_SOURCE_DEFINITIONS` (one row per source).
Format-to-source membership lives in each format's `REGISTRATION.sources`. Call
sites continue to use `MetadataSources.CONFIG`, `.ARCHIVE_FILE` etc. — attribute
access works the same.

**Trade-off accepted:** pyright/mypy won't statically see the enum members.
Typo'd member access would raise `AttributeError` at runtime instead of being
flagged by `make ty`. Acceptable because all ~54 call sites are internal, every
code path is exercised by the test suite, and the source list (~10 entries) is
stable. If this turns out to bite — surface the problem and flip back to a
class-body enum; it's a 15-line change.

This kills the five scattered hardcoded format tuples _and_ removes the
hand-maintained format ordering inside each source.

### 2.4 Hook consolidation

The pain points from [01-current-state-survey.md §3](01-current-state-survey.md)
collapse:

| Today (scattered)                                                                                  | After (declared per format)                                                 |
| -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `FMT_VALIDATOR_MAP` ([box/validate/**init**.py:26-44](../../comicbox/box/validate/__init__.py))    | `REGISTRATION.validator`                                                    |
| `FILENAME_FORMAT_MAP` ([box/sources.py:16-21](../../comicbox/box/sources.py))                      | `REGISTRATION.archive_filename` (default = `format.filename`)               |
| `_FORMATS_WITH_TAGS_WITHOUT_IDS` ([config/computed.py:13-21](../../comicbox/config/computed.py))   | `REGISTRATION.has_tags_without_ids`                                         |
| `ARCHIVE_FORMATS` ([box/dump.py:11-14](../../comicbox/box/dump.py))                                | derived from `sources` map                                                  |
| `_ENSURE_PDF_TO_CBZ_DEFAULT` ([box/dump.py:45-53](../../comicbox/box/dump.py))                     | `REGISTRATION.archive_role = ArchiveRole.PDF_NATIVE` + dispatch in box/dump |
| `_get_source_comment_metadata` "only one" ([box/sources.py:99-108](../../comicbox/box/sources.py)) | dispatch reads `ARCHIVE_COMMENT` formats; no special-case                   |
| `_DEFAULT_SOURCE_FACTORIES` ([box/online_lookup.py:63-68](../../comicbox/box/online_lookup.py))    | `REGISTRATION.online_source_factory`                                        |
| `_ONLINE_SOURCE_ENUMS` ([box/online_lookup.py:72-74](../../comicbox/box/online_lookup.py))         | derived (`fmt.value.registration.online_source_factory is not None`)        |
| `SOURCES_SET_ELSEWHERE` ([box/sources.py:187-193](../../comicbox/box/sources.py))                  | same derived predicate                                                      |
| `_ONLINE_SOURCES_INFO` ([cli.py:96-109](../../comicbox/cli.py))                                    | `REGISTRATION.cli_info`                                                     |
| CLI help label-prefix dimming ([cli.py:302-303](../../comicbox/cli.py))                            | `REGISTRATION.cli_help_style`                                               |

After this, **adding a new format = creating one package + adding one import
line + one enum member in `formats/__init__.py`.** Five lines of central change
vs. the current 10+ files.

### 2.5 Transform style — keep both, formalize the split

The file-based-vs-online mismatch ([survey §3](01-current-state-survey.md))
stays. The decoupling is real (irregular online shapes don't fit `MetaSpec`).
The plan:

- Introduce `BaseTransform` (today's) and `BuilderTransform` (explicit-Python
  style) as sibling subclasses of a new `Transform` ABC. Or keep `BaseTransform`
  as the base and add `OnlineBuilderTransform` for clarity. **TBD in Phase 1
  pilot.**
- Remove the empty `SPECS_TO = MappingProxyType({})  # not used` boilerplate
  from online transforms. The intent is currently obscured.
- Online transforms keep their explicit-Python style.

## 3. Decisions to lock before Phase 1

| Decision                    | Default proposal                                                                                                                                                                              | Notes                                                                                                                                                                                                                                                                                  |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Package name                | `comicbox/formats/`                                                                                                                                                                           | Replaces the current `comicbox/transforms/` + `comicbox/schemas/` split. The existing `comicbox/formats.py` becomes `comicbox/formats/__init__.py`.                                                                                                                                    |
| Sub-module split            | `transform/` subpackage with main class in `__init__.py` + sibling sub-transform files iff there is any sub-transform; otherwise flat `transform.py`. Same rule for `schema/` vs `schema.py`. | Mirrors today's [comicbox/transforms/](../../comicbox/transforms/) / [comicbox/schemas/](../../comicbox/schemas/) convention; no `transforms_<thing>.py` siblings.                                                                                                                     |
| Test layout                 | Keep `tests/schemas/test_<fmt>.py` and `tests/unit/test_<fmt>_transform.py` paths unchanged                                                                                                   | Test reorg is out of scope; keeps PR-by-PR review focused.                                                                                                                                                                                                                             |
| Import-compat shims         | **No**                                                                                                                                                                                        | Old import paths (`comicbox.transforms.comet.CoMetTransform` etc.) are deleted, not re-exported. The current codex release pins to the current comicbox; a new codex that supports online tagging will be the first to use this format-based architecture. No staged migration needed. |
| `MetadataSources` enum body | Dynamic `Enum("MetadataSources", {...})` built from `_SOURCE_DEFINITIONS` + per-format `REGISTRATION.sources`.                                                                                | Avoids duplicating source names in both the enum body and a helper arg. All ~54 call sites are internal; runtime AttributeError on a typo is acceptable since the test suite exercises every path. Revisit if it bites.                                                                |
| Online wrapper relocation   | Move `comicbox/online/sources/{metron,comicvine}.py` → `comicbox/formats/{metron_api,comicvine_api}/online_source.py`                                                                         | Online matcher/rate-limit/retry stay under `comicbox/online/`. Only the per-DB source class moves.                                                                                                                                                                                     |

## 4. Phasing

Six phases. Each phase = one mergeable PR; tests must stay green between phases.

### Phase 0 — Module-shape pilot (CoMet)

CoMet has the smallest surface: no Box mixin hooks, no special CLI/config, one
schema, one transform + one sub-transform. Build out the new layout for CoMet
only to validate the module-shape decisions.

**Scope:**

- Create `comicbox/formats/_base.py` with `FormatRegistration`.
- Create `comicbox/formats/comet/` with `__init__.py`, `schema.py`, and
  `transform/{__init__.py, reprints.py}`.
- `comicbox/formats.py` imports CoMet's `REGISTRATION` and uses it. Other 12
  formats stay as-is.
- Delete the old `comicbox/schemas/comet.py` and `comicbox/transforms/comet/`.
  Update every import site in-tree.

**Validation:** Full test suite passes; CoMet round-trip identical pre/post.

**Exit criteria:** Module shape feels right. If it doesn't, iterate here — do
**not** generalize to other formats yet.

### Phase 1 — Migrate remaining file-based formats

ComicInfo, MetronInfo, ComicBookInfo, Filename, and the three native Comicbox
formats. Five packages. Mechanical once Phase 0 locks the shape.

PDF deferred to Phase 2 (it has the most hooks). Online deferred to Phase 3.

**Scope per format:** create package, move schema + transform, add
`REGISTRATION` declaration, delete the old paths, update every in-tree import
site.

**Validation:** Full test suite green; each format's tests pass against new
module.

### Phase 2 — PDF (file-based with hooks)

PDF is file-based but has the most format-specific dispatch:
`_get_source_pdf_metadata`, `_ensure_pdf_to_cbz_default_format`,
`--pdf-page-format` CLI flag, `PDF_ENABLED` conditional. This phase exercises
the `archive_role` and `cli_help_style` hooks proposed in §2.4.

**Scope:**

- Create `comicbox/formats/pdf/` with both `MuPDFTransform` and
  `PDFXmlTransform`.
- Move `_ensure_pdf_to_cbz_default_format` logic behind an `archive_role`-driven
  dispatch in `box/dump.py`.
- Move `--pdf-page-format` flag registration into the PDF module (CLI exposes a
  `format_cli_options` hook).
- `PDF_ENABLED` becomes an attribute on `REGISTRATION` (more uniform than
  today's two patterns).

**Validation:** PDF read/write/CBZ-conversion tests pass; `--pdf-page-format`
works; `pdffile`-extras-absent path still degrades gracefully.

**Decision needed at start of phase:** is the `archive_role` enum the right
abstraction, or is it overfitting on the one PDF case? If only PDF needs it,
prefer a simpler `is_archive_native: bool` flag.

### Phase 3 — Online formats (Metron API + ComicVine API)

The most consolidation payoff — folds five separate registrations
(`_DEFAULT_SOURCE_FACTORIES`, `_ONLINE_SOURCE_ENUMS`, `SOURCES_SET_ELSEWHERE`,
`_ONLINE_SOURCES_INFO`, plus the `MetadataSources` entry) into each online
format's `REGISTRATION`.

**Scope:**

- Create `comicbox/formats/metron_api/` and `comicbox/formats/comicvine_api/`.
- Each contains its `OnlineSource` subclass (moved from
  `comicbox/online/sources/`).
- `REGISTRATION.online_source_factory` and `REGISTRATION.cli_info` replace the
  four scattered tables.
- `box/online_lookup.py` becomes a thin orchestrator: discovers online formats
  by inspecting `REGISTRATION.online_source_factory is not None`.
- Drop the empty `SPECS_TO = MappingProxyType({})  # not used` boilerplate from
  online transforms; pick the cleaner transform-base abstraction landed in
  Phase 0.

**Validation:** Online tagging end-to-end works against the calibration
fixtures. Phase 3 is where the M2/M6 integration pain points were felt, so this
is the phase that actually delivers on the refactor's motivation.

**Risk:** This phase touches `box/online_lookup.py` which is large. Plan to do
it in two PRs if needed: (a) move source classes + add registration; (b)
collapse the duplicate tables.

### Phase 4 — Consolidate scattered hardcoded lists

Now that every format has a `REGISTRATION`, the five scattered hardcoded lists
in §2.4's table become derived.

**Scope:**

- `FMT_VALIDATOR_MAP` → derived from `REGISTRATION.validator`.
- `FILENAME_FORMAT_MAP` → derived from `REGISTRATION.archive_filename`
  (defaulting to `format.filename`).
- `_FORMATS_WITH_TAGS_WITHOUT_IDS` → derived from
  `REGISTRATION.has_tags_without_ids`. Fix the missing `METRON_INFO` entry (open
  bug, see survey §3).
- `ARCHIVE_FORMATS` → derived from source membership.
- CLI help-table dimming → `REGISTRATION.cli_help_style`.

**Validation:** Every behavior controlled by these lists is regression-tested.
Existing test suite should catch divergence; spot-check the `METRON_INFO` fix.

### Phase 5 — Cleanup

- Remove any dead helpers exposed by the move (e.g., the now-unused
  `_swap_data_key` hack at
  [transforms/base.py:32](../../comicbox/transforms/base.py) if applicable).
- Delete the now-empty `comicbox/schemas/` and `comicbox/transforms/`
  directories if nothing else lives there.
- Update CLAUDE.md "Architecture" section to describe the new layout.
- Update CONTRIBUTING / docstrings.

**Validation:** Full suite green; `make fix`/`make lint`/`make ty` clean.

## 5. Risks

- **Import-path churn.** Downstream consumers (codex) import from
  `comicbox.schemas.*` and `comicbox.transforms.*`. No mitigation needed
  in-tree: the current codex pins to the current comicbox, and the new codex
  (online-tagging-capable) will be written against the format-based architecture
  from the start. Every in-tree import site **does** get rewritten each phase;
  the unit and integration test suites are the regression net.
- **Enum ordering = masking precedence.** Both `MetadataFormats` and
  `MetadataSources` use declaration order for precedence. Easy to break silently
  when reordering. **Mitigation:** add an explicit ordering test that asserts
  the assembled enum matches a known-good sequence, run on every PR.
- **Online wrapper coupling.** The `OnlineSource` classes import from
  `comicbox/online/{matcher,rate_limits,retry,...}`. Moving them under
  `comicbox/formats/` is fine, but watch for accidental circular imports through
  `comicbox.online.auto_engage`.
- **Test discovery drift.** Tests reference fixture paths and import paths. Keep
  test files where they are; only update import statements.
- **`make fix` noise.** Reorg PRs will inevitably pull in unrelated lint
  cleanups if `make fix` is run unfocused. Run it per-phase and review diff
  before committing — per [user workflow rules](../../CLAUDE.md).

## 6. Estimation (rough)

Phase 0: ½ day (high-leverage; design decisions land here). Phase 1: 1–1½ days
(6 packages, mechanical). Phase 2: 1 day (PDF hooks). Phase 3: 1–2 days (online;
touches `box/online_lookup.py`). Phase 4: ½ day (consolidation; mostly
deletions). Phase 5: ½ day (cleanup + docs).

**Total:** ~5 working days end-to-end. Phase 0 is the only one that can't be
safely paused; the rest are independent and mergeable.

## 7. Open questions

1. **`Transform` ABC vs keeping `BaseTransform` as-is.** Decide in Phase 0
   pilot. The honest answer may be "leave it alone if a clean split doesn't
   materialize."
2. **PDF `archive_role` vs `is_archive_native: bool`.** Decide at start of Phase
   2 based on whether other formats want similar dispatch. Default to the
   simpler boolean if PDF is the only case.
3. **Test reorganization.** Keep `tests/schemas/test_*.py` paths as-is for now
   (out of scope per §3). Future grooming PR can move tests under
   `tests/formats/<fmt>/` if it feels worth the churn — flag as a separate task.
4. **`comicbox.online.transform_helpers`.** Used by both online format
   transforms. Where should it live after Phase 3? Options: (a) stay under
   `comicbox/online/`; (b) move to `comicbox/formats/_online_helpers.py`. Defer
   to Phase 3 review.
