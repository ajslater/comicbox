"""
Images: what online cover matching needs to hash a cover.

Only online tagging hashes images, so nothing here stops comicbox from
reading or writing comics.
"""

from __future__ import annotations

from functools import partial
from io import BytesIO
from typing import TYPE_CHECKING

from comicbox.box.archive.init import IMAGE_EXTS
from comicbox.doctor.packages import dist_version, reinstall_hint
from comicbox.doctor.result import CheckResult, Status

if TYPE_CHECKING:
    from collections.abc import Iterator

    from comicbox.doctor.context import Check, DoctorContext

SECTION = "Images (online cover matching)"

# Pillow's wheels ship no JPEG XL codec at all, so a missing one is a
# note on a healthy row, not a warning every install would show.
_OPTIONAL_EXTS = frozenset({"jxl"})

_row = partial(CheckResult, SECTION)


def check_pillow(_ctx: DoctorContext) -> Iterator[CheckResult]:
    """Every page image extension comicbox knows must have a Pillow codec."""
    try:
        from PIL import Image
    except ImportError as exc:
        yield _row(
            "Pillow",
            Status.MISSING,
            detail=f"can't import {exc.name}: {exc}",
            fix=reinstall_hint("pillow"),
        )
        return
    Image.init()
    registered = Image.registered_extensions()
    missing = [ext for ext in IMAGE_EXTS if f".{ext}" not in registered]
    found = f"Pillow {dist_version('pillow')}"
    if core_missing := [ext for ext in missing if ext not in _OPTIONAL_EXTS]:
        yield _row(
            "Pillow",
            Status.WARN,
            found=found,
            detail=f"no {' '.join(core_missing)} codec: those covers can't be matched",
            fix=reinstall_hint("pillow"),
        )
        return
    codecs = dict.fromkeys(
        registered[f".{ext}"].lower() for ext in IMAGE_EXTS if ext not in missing
    )
    notes = [" ".join(codecs)]
    notes.extend(f"no {ext} codec" for ext in missing)
    yield _row("Pillow", Status.OK, found=found, detail=" · ".join(notes))


def _tiny_png() -> bytes:
    """Make an 8x8 gradient PNG to hash."""
    from PIL import Image

    side = 8
    image = Image.new("L", (side, side))
    image.putdata([x * y * 4 for y in range(side) for x in range(side)])
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def check_imagehash(_ctx: DoctorContext) -> Iterator[CheckResult]:
    """Hash a real image the way cover matching does."""
    from comicbox.formats.base.online.cover_hash import compute_phash

    try:
        # imagehash pulls in numpy, scipy and pywt.
        import imagehash  # noqa: F401  # pyright: ignore[reportUnusedImport]

        png = _tiny_png()
    except ImportError as exc:
        yield _row(
            "imagehash",
            Status.MISSING,
            detail=f"can't import {exc.name}: {exc}",
            fix=reinstall_hint("imagehash"),
        )
        return
    found = f"imagehash {dist_version('imagehash')}"
    try:
        compute_phash(png)
    except Exception as exc:  # any failure here is the finding
        yield _row(
            "imagehash",
            Status.ERROR,
            found=found,
            detail=f"phash smoke test failed: {exc!r}",
            fix=reinstall_hint("imagehash"),
        )
        return
    yield _row("imagehash", Status.OK, found=found, detail="phash smoke test OK")


CHECKS: tuple[Check, ...] = (
    (SECTION, "Pillow", check_pillow),
    (SECTION, "imagehash", check_imagehash),
)
