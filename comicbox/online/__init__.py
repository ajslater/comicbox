"""
Online metadata tagging support.

Built incrementally across milestones:

- M1: config/CLI scaffolding, credential resolution chain, env-var helpers.
- M2: Metron source via mokkari, retry decorator, ID-only lookup path.
- M3: search and ranking, auto-accept policy.
- M4: cover-hash disambiguator.
- M5: interactive prompt + programmatic SelectorCallback API.
- M6: ComicVine source via simyan.
- M7: parallel batch processing.
"""

# Source name constants, used as keys throughout the online subsystem.
SOURCE_NAMES = ("metron", "comicvine")
