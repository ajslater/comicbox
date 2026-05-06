"""
Metron API transform.

Stub for M1 — real spec maps land in M2.
"""

from comicbox.schemas.metron_api import MetronApiSchema
from comicbox.transforms.base import BaseTransform


class MetronApiTransform(BaseTransform):
    """Stub Metron API transform; real spec maps in M2."""

    SCHEMA_CLASS = MetronApiSchema
