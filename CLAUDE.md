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

```
ComicboxInit → ComicboxArchive* (read/write/pages) → ComicboxSources
  → ComicboxLoad → ComicboxNormalize → ComicboxMerge
  → ComicboxComputed* (computed fields) → ComicboxMetadata
  → ComicboxPages* → ComicboxDump* → ComicboxValidate → ComicboxPrint
  → Comicbox
```

**Key subsystems:**

- `comicbox/formats/` — One self-contained package per metadata format. Each
  package owns its schema, transform, and a `REGISTRATION: FormatRegistration`
  declaration (`__init__.py`) that names its `MetadataFormat`, per-source
  masking priorities, validator, and other format-specific flags. The
  `comicbox.formats` package's `__init__.py` assembles the `MetadataFormats`
  enum and a `FORMAT_REGISTRATIONS` reverse-lookup map from the per-format
  REGISTRATIONs. `MetadataSources`, `FMT_VALIDATOR_MAP`,
  `_FORMATS_WITH_TAGS_WITHOUT_IDS`, and the online-source registries derive from
  those REGISTRATIONs at module load.
- `comicbox/schemas/` — Marshmallow base schemas (`BaseSchema`, `XmlSchema`,
  `JsonSchema`, the YAML render module, etc.). Format-specific schemas live
  inside their format package.
- `comicbox/transforms/` — Shared transform helpers (`BaseTransform`,
  `MetaSpec`, plus reusable mini-transforms like `xml_credits`, `xml_reprints`,
  `identifiers`, `publishing_tags`, `price`). Format-specific transforms live
  inside their format package.
- `comicbox/box/archive/` — Archive file I/O (zip, rar, 7z, tar, PDF).
- `comicbox/box/computed/` — Fields derived from other metadata (dates,
  identifiers, issue numbers, page counts).
- `comicbox/online/` — Online-tagging infrastructure (matcher, rate limits,
  retry, profile, prompt, selector). Per-database `OnlineSource` subclasses live
  in their format package (`comicbox/formats/metron_api/`,
  `comicbox/formats/comicvine_api/`).
- `comicbox/config/` — `confuse`-based configuration management.
- `comicbox/enums/` — Enum types and bidirectional maps used across formats.

## Testing, Linting & Type Checking

Refer to @\~/.claude/rules/python-devenv.md
