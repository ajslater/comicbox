# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## Project Overview

Comicbox is a Python library for reading and writing comic book archive
metadata. It supports CBZ, CBR, CBT, CB7, and PDF formats, and handles multiple
metadata schemas: ComicInfo.xml (ComicRack), MetronInfo.xml (Metron),
ComicBookInfo, CoMet, ComicTagger, PDF metadata, and native Comicbox YAML/JSON.

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

- `comicbox/transforms/` — One subdirectory per metadata format. Each transform
  converts between that format's native representation and the internal Comicbox
  schema.
- `comicbox/schemas/` — Marshmallow schemas for serialization/deserialization.
- `comicbox/box/archive/` — Archive file I/O (zip, rar, 7z, tar, PDF).
- `comicbox/box/computed/` — Fields derived from other metadata (dates,
  identifiers, issue numbers, page counts).
- `comicbox/config/` — `confuse`-based configuration management.
- `comicbox/enums/` — Enum types and bidirectional maps used across formats.

## Testing, Linting & Type Checking

Refer to @\~/.claude/rules/python-devenv.md
