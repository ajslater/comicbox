"""
Vulture whitelist.

Names listed here are "used" by this file so `vulture .` doesn't flag
them. Excluded from ruff/pyright in pyproject.toml. Regenerate location
comments with: uv run --group lint vulture . --make-whitelist
"""

option_string  # argparse.Action.__call__ signature (comicbox/cli/parser.py)
