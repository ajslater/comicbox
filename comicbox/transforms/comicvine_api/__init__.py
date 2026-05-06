"""
ComicVine API transform.

Stub for M1 — real spec maps land in M6.
"""

from comicbox.schemas.comicvine_api import ComicVineApiSchema
from comicbox.transforms.base import BaseTransform


class ComicVineApiTransform(BaseTransform):
    """Stub ComicVine API transform; real spec maps in M6."""

    SCHEMA_CLASS = ComicVineApiSchema
