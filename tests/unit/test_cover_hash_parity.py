"""
comicbox's pure-Python pHash against imagehash's, bit for bit.

Metron serves ``str(imagehash.phash(cover))`` as each issue's cover hash
and the matcher compares ours against it, so the two must agree exactly.
imagehash is a test-only dependency kept for this guard: an imagehash
release that changes ``phash`` output fails here instead of quietly
costing cover matches.
"""

from __future__ import annotations

import random
from functools import partial
from io import BytesIO
from typing import TYPE_CHECKING

import imagehash
import pytest
from PIL import Image, ImageDraw, ImageOps

from comicbox.doctor import images as doctor_images
from comicbox.formats.base.online.cover_hash import compute_phash
from tests.util.cover_images import real_images

if TYPE_CHECKING:
    from collections.abc import Callable

_SIZE = (256, 256)
_BLOCK_IMAGES = 50


def _png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg(image: Image.Image, quality: int) -> bytes:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _assert_parity(data: bytes) -> None:
    with Image.open(BytesIO(data)) as image:
        expected = str(imagehash.phash(image))
    assert compute_phash(data) == expected


def _drawn(fn: Callable[[int, int], int], size: tuple[int, int] = _SIZE) -> Image.Image:
    width, height = size
    image = Image.new("L", size)
    image.putdata([fn(x, y) for y in range(height) for x in range(width)])
    return image


def _noise(seed: int) -> Image.Image:
    rng = random.Random(seed)  # noqa: S311 — reproducible test images, not crypto
    return Image.frombytes("L", _SIZE, rng.randbytes(_SIZE[0] * _SIZE[1]))


def _blocks(seed: int) -> Image.Image:
    """Random rectangles of random colors on a random-sized canvas."""
    rng = random.Random(seed)  # noqa: S311 — reproducible test images, not crypto
    size = (rng.randrange(40, 400), rng.randrange(40, 400))

    def color() -> tuple[int, int, int]:
        return (rng.randrange(256), rng.randrange(256), rng.randrange(256))

    image = Image.new("RGB", size, color())
    draw = ImageDraw.Draw(image)
    for _ in range(rng.randrange(1, 12)):
        x0, x1 = sorted(rng.randrange(size[0]) for _ in range(2))
        y0, y1 = sorted(rng.randrange(size[1]) for _ in range(2))
        draw.rectangle((x0, y0, x1, y1), fill=color())
    return image


# Degenerate images: flat, ramped and hard-edged inputs are where a DCT
# that doesn't cancel equal values exactly drifts off imagehash's median.
#
# Patterns symmetric under transposition, f(x, y) == f(y, x) like
# `x * y * 4 % 256`, are left out on purpose. Their DCT has
# d[k][l] == d[l][k] exactly, so when such a pair holds the two middle
# values the median lands on both, and the last floating-point digit of
# each FFT decides which side each falls: a coin flip of a bit that two
# correct implementations can call differently. Any coefficient that is
# exactly the median in exact arithmetic is the same coin flip; it takes
# a contrived image to make one, never a scanned cover. The checkerboard
# is drawn on a non-square canvas to stay clear of it. Solid fills are
# symmetric too, but safe: every AC term cancels to exactly zero.
_SYNTHETICS: dict[str, Callable[[], Image.Image]] = {
    "solid-L-0": partial(Image.new, "L", _SIZE, 0),
    "solid-L-127": partial(Image.new, "L", _SIZE, 127),
    "solid-L-255": partial(Image.new, "L", _SIZE, 255),
    "solid-RGB": partial(Image.new, "RGB", _SIZE, (200, 30, 90)),
    "gradient-horizontal": partial(_drawn, lambda x, _y: x),
    "gradient-vertical": partial(_drawn, lambda _x, y: y),
    "checkerboard-8px": partial(
        _drawn, lambda x, y: (x // 8 + y // 8) % 2 * 255, (256, 192)
    ),
    "half-split": partial(_drawn, lambda x, _y: 255 * (x >= _SIZE[0] // 2)),
    "noise": partial(_noise, 1),
    **{f"blocks-{seed:02}": partial(_blocks, seed) for seed in range(_BLOCK_IMAGES)},
}


def _scaled(image: Image.Image, divisor: int) -> bytes:
    width, height = image.size
    return _png(image.resize((max(1, width // divisor), max(1, height // divisor))))


def _cropped(image: Image.Image, percent: int) -> bytes:
    width, height = image.size
    dx, dy = width * percent // 100, height * percent // 100
    return _png(image.crop((dx, dy, width - dx, height - dy)))


# What happens to a cover between a scan and Metron's copy of it.
_VARIANTS: dict[str, Callable[[Image.Image], bytes]] = {
    "jpeg-q25": partial(_jpeg, quality=25),
    "scale-fifth": partial(_scaled, divisor=5),
    "crop-5pct": partial(_cropped, percent=5),
    "mirror": lambda image: _png(ImageOps.mirror(image)),
}


def test_real_images_found() -> None:
    """An empty set would skip every real-image case without failing."""
    names = real_images()
    assert any(name.endswith(".cbz") for name in names)
    assert any(name.endswith(".pdf") for name in names)


@pytest.mark.parametrize("name", list(real_images()))
def test_real_image_parity(name: str) -> None:
    _assert_parity(real_images()[name])


@pytest.mark.parametrize("variant", list(_VARIANTS))
@pytest.mark.parametrize("name", list(real_images()))
def test_real_image_variant_parity(name: str, variant: str) -> None:
    with Image.open(BytesIO(real_images()[name])) as image:
        image.load()
        data = _VARIANTS[variant](image)
    _assert_parity(data)


@pytest.mark.parametrize("name", list(_SYNTHETICS))
def test_synthetic_parity(name: str) -> None:
    _assert_parity(_png(_SYNTHETICS[name]()))


def test_doctor_card_matches_imagehash() -> None:
    """The doctor's self-test constant is what imagehash says it is."""
    with Image.open(BytesIO(doctor_images._test_card_png())) as card:
        assert str(imagehash.phash(card)) == doctor_images._CARD_PHASH
