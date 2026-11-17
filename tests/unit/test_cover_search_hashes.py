"""
The hashes a cover search sends: uprighted, and split for wraparound spreads.

Metron hashes each issue's front cover with ``imagehash.phash``, so a
half-spread hash only matches if it is computed bit for bit as imagehash
would compute it on that crop; the parity checks below guard that.
"""

from __future__ import annotations

import random
from io import BytesIO

import imagehash
import pytest
from PIL import Image

from comicbox.box import Comicbox
from comicbox.formats.base.online.cover_hash import (
    FULL_COVER_ACCEPT_BITS,
    HALF_COVER_ACCEPT_BITS,
    CoverPart,
    compute_phash,
    search_hashes,
)
from tests.const import TEST_FILES_DIR

# EXIF tag 0x0112; 6 means "rotate 90 degrees clockwise to display".
_ORIENTATION_TAG = 0x0112
_ROTATE_90_CW = 6


def _noise(size: tuple[int, int], seed: int = 1) -> Image.Image:
    rng = random.Random(seed)  # noqa: S311 — reproducible test images, not crypto
    width, height = size
    return Image.frombytes("L", size, rng.randbytes(width * height))


def _png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _imagehash(image: Image.Image) -> str:
    return str(imagehash.phash(image))


def test_portrait_cover_is_one_full_hash() -> None:
    """A single cover is searched whole, at the whole-cover limit."""
    data = _png(_noise((200, 300)))

    hashes = search_hashes(data)

    assert len(hashes) == 1
    (only,) = hashes
    assert only.part is CoverPart.FULL
    assert only.accept_bits == FULL_COVER_ACCEPT_BITS
    assert only.phash == compute_phash(data)


def test_spread_is_searched_right_then_left_then_whole() -> None:
    """Halves first, at the half limit; the whole image last."""
    spread = _noise((600, 400))

    hashes = search_hashes(_png(spread))

    assert [h.part for h in hashes] == [
        CoverPart.RIGHT,
        CoverPart.LEFT,
        CoverPart.FULL,
    ]
    assert [h.accept_bits for h in hashes] == [
        HALF_COVER_ACCEPT_BITS,
        HALF_COVER_ACCEPT_BITS,
        FULL_COVER_ACCEPT_BITS,
    ]
    right, left, full = (h.phash for h in hashes)
    assert right == _imagehash(spread.crop((300, 0, 600, 400)))
    assert left == _imagehash(spread.crop((0, 0, 300, 400)))
    assert full == _imagehash(spread)


def test_odd_width_spread_splits_at_floor_of_the_midpoint() -> None:
    """The cut is ``width // 2``, with no adjustment for a spine."""
    spread = _noise((601, 400), seed=2)

    right, left, _ = search_hashes(_png(spread))

    assert right.phash == _imagehash(spread.crop((300, 0, 601, 400)))
    assert left.phash == _imagehash(spread.crop((0, 0, 300, 400)))


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        pytest.param((120, 100), 1, id="aspect-1.2-is-not-a-spread"),
        pytest.param((121, 100), 3, id="just-past-1.2-is-a-spread"),
    ],
)
def test_spread_threshold(size: tuple[int, int], expected: int) -> None:
    """Wider than 1.2 to 1 is a spread; 1.2 exactly is not."""
    assert len(search_hashes(_png(_noise(size)))) == expected


def test_exif_rotated_portrait_is_hashed_upright() -> None:
    """
    Hash a sideways-stored portrait cover as the upright cover it shows.

    It is neither mistaken for a spread nor hashed sideways, so it matches
    the upright cover the server has.
    """
    upright = _noise((200, 300), seed=3)
    # Stored rotated a quarter turn counter-clockwise, with the EXIF tag
    # that tells a viewer to turn it back.
    stored = upright.rotate(90, expand=True)
    exif = Image.Exif()
    exif[_ORIENTATION_TAG] = _ROTATE_90_CW
    buffer = BytesIO()
    stored.save(buffer, format="JPEG", exif=exif.tobytes(), quality=100)
    data = buffer.getvalue()
    with Image.open(BytesIO(data)) as img:
        assert img.width > img.height  # stored landscape

    hashes = search_hashes(data)

    assert [h.part for h in hashes] == [CoverPart.FULL]
    with Image.open(BytesIO(data)) as img:
        as_displayed = img.transpose(Image.Transpose.ROTATE_270)
        assert hashes[0].phash == _imagehash(as_displayed)


def test_box_search_hashes_are_memoized(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cover is read once however often the lookup asks."""
    reads: list[None] = []
    with Comicbox(TEST_FILES_DIR / "Captain Science #001.cbz") as car:
        original = car._read_local_cover

        def counting_read() -> bytes | None:
            reads.append(None)
            return original()

        monkeypatch.setattr(car, "_read_local_cover", counting_read)
        first = car._local_cover_search_hashes()
        second = car._local_cover_search_hashes()

    assert first == second
    assert len(first) == 1
    assert len(reads) == 1


def test_box_search_hashes_empty_without_a_cover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No cover means no hashes, remembered as such: no second read."""
    reads: list[None] = []

    def no_cover() -> bytes | None:
        reads.append(None)
        return None

    with Comicbox(TEST_FILES_DIR / "Captain Science #001.cbz") as car:
        monkeypatch.setattr(car, "_read_local_cover", no_cover)
        assert car._local_cover_search_hashes() == ()
        assert car._local_cover_search_hashes() == ()

    assert len(reads) == 1
