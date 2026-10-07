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
from comicbox.doctor.packages import dist_version, pinned, reinstall_hint
from comicbox.doctor.result import CheckResult, Status
from comicbox.version import PACKAGE_NAME

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


# A test card and its pHash as imagehash 4.3.2 computes it, the library
# Metron hashes its covers with. The card is asymmetric on purpose: an
# image symmetric under transposition can tie at the median and flip a
# bit on rounding. Its hash is also the same under Pillow's bicubic,
# bilinear, hamming and box filters, so a resampling tweak in a Pillow
# upgrade won't flip it.
_CARD_SIZE = (16, 12)
_CARD_PHASH = "8c0c0d3d33fdc3d1"


def _test_card_png() -> bytes:
    """Make the small asymmetric grayscale PNG the self-test hashes."""
    from PIL import Image

    width, height = _CARD_SIZE
    image = Image.new("L", _CARD_SIZE)
    image.putdata(
        [
            (3 * x * x + 9 * y * y + x * y) % 256
            for y in range(height)
            for x in range(width)
        ]
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _cover_hash_fix() -> str:
    """Return the fix hint: the hash is comicbox's own code running on Pillow."""
    return (
        "reinstall comicbox and Pillow: "
        f"pip install --force-reinstall {PACKAGE_NAME} '{pinned('pillow')}'"
    )


def check_cover_hash(_ctx: DoctorContext) -> Iterator[CheckResult]:
    """Hash a known image the way cover matching does and check the answer."""
    from comicbox.formats.base.online.cover_hash import compute_phash

    try:
        phash = compute_phash(_test_card_png())
    except Exception as exc:  # any failure here is the finding
        yield _row(
            "cover hash",
            Status.ERROR,
            detail=f"pHash self-test failed: {exc!r}",
            fix=_cover_hash_fix(),
        )
        return
    if phash != _CARD_PHASH:
        yield _row(
            "cover hash",
            Status.ERROR,
            detail=(
                f"pHash self-test got {phash}, expected {_CARD_PHASH}: "
                "covers won't match Metron's"
            ),
            fix=_cover_hash_fix(),
        )
        return
    yield _row("cover hash", Status.OK, detail="pHash self-test OK")


CHECKS: tuple[Check, ...] = (
    (SECTION, "Pillow", check_pillow),
    (SECTION, "cover hash", check_cover_hash),
)
