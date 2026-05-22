# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## Project Overview

Comicbox is a Python library for reading and writing comic book archive
metadata. It supports CBZ, CBR, CBT, CB7, and PDF formats, and handles multiple
metadata schemas: ComicInfo.xml (ComicRack), MetronInfo.xml (Metron),
ComicBookInfo, CoMet, PDF metadata, and native Comicbox YAML/JSON.

## Commands

Refer to @\~/.claude/rules/python-devenv.md

## Architecture

The `Comicbox` class is assembled via a deep mixin inheritance chain in
`comicbox/box/`. Each mixin layer adds a focused concern:

```log
ComicboxInit → ComicboxArchive* (read/write/pages) → ComicboxSources
  → ComicboxLoad → ComicboxNormalize → ComicboxMerge
  → ComicboxComputed* (computed fields) → ComicboxMetadata
  → ComicboxPages* → ComicboxDump* → ComicboxValidate → ComicboxPrint
  → Comicbox
```

**Key subsystems:**

- `comicbox/formats/` — Everything format-related lives here:
    - `comicbox/formats/__init__.py` assembles the `MetadataFormats` enum and a
      `FORMAT_REGISTRATIONS` reverse-lookup map from each format module's
      `REGISTRATION: FormatRegistration`.
    - `comicbox/formats/sources.py` builds the dynamic `MetadataSources` enum
      from per-format `REGISTRATION.sources` declarations.
    - One self-contained package per metadata format (e.g.
      `comicbox/formats/comet/`, `comicbox/formats/metron_api/`). Each owns its
      schema, transform, online-source wrapper (online only), and `__init__.py`
      with the `REGISTRATION` export.
    - `comicbox/formats/base/` — shared infrastructure for the format packages:
        - `base/schemas/` — Marshmallow base schemas (`BaseSchema`, `XmlSchema`,
          `JsonSchema`, the YAML render module).
        - `base/transforms/` — shared transform helpers (`BaseTransform`,
          `MetaSpec`, plus reusable mini-transforms like `xml_credits`,
          `xml_reprints`, `identifiers`, `publishing_tags`, `price`).
        - `base/fields/` — Marshmallow field types (`XmlStringField`,
          `IntegerField`, `PageTypeField`, etc.).
        - `base/online/` — online-tagging infrastructure (matcher, rate limits,
          retry, profile, prompt, selector, signals, cover-hash, etc.).
          Per-database `OnlineSource` subclasses live in their format package.
- `comicbox/constants.py` — top-level data-model field-name strings shared
  between the comicbox-native schema and low-level consumers like the YAML
  validator. Lives outside `comicbox/formats/` to avoid load-order cycles.
- `comicbox/box/archive/` — Archive file I/O (zip, rar, 7z, tar, PDF).
- `comicbox/box/computed/` — Fields derived from other metadata (dates,
  identifiers, issue numbers, page counts).
- `comicbox/identifiers/` — Identifier parsing/serialization. Cross-cutting
  (used by formats and by `box/computed/`).
- `comicbox/config/` — `confuse`-based configuration management.
- `comicbox/enums/` — Enum types and bidirectional maps used across formats.
- `comicbox/_pdf.py` — Optional `pdffile` integration flag. Lives at the top
  level (not under `comicbox/formats/pdf/`) so importing the flag doesn't
  trigger the PDF format-package init.

## Testing, Linting & Type Checking

Refer to @\~/.claude/rules/python-devenv.md
