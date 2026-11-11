"""Image metrics on synthetic JPEGs (skipped when Pillow / numpy are not installed)."""
import io

import pytest

PIL = pytest.importorskip("PIL")
np = pytest.importorskip("numpy")
from PIL import Image, ImageFilter  # noqa: E402

from common import imgmetrics as im  # noqa: E402


def _jpeg(img):
    b = io.BytesIO()
    img.save(b, "JPEG", quality=92)
    return b.getvalue()


def _checker(level=128, size=(128, 96)):
    a = np.zeros((size[1], size[0], 3), np.uint8)
    yy, xx = np.mgrid[0:size[1], 0:size[0]]
    a[((xx // 8 + yy // 8) % 2) == 0] = level
    return Image.fromarray(a)


def test_luma_increases_with_brightness():
    dark = _jpeg(Image.new("RGB", (64, 48), (40, 40, 40)))
    bright = _jpeg(Image.new("RGB", (64, 48), (200, 200, 200)))
    assert im.luma_mean(bright) > im.luma_mean(dark) + 100
    assert im.luma_mean(bright, roi=(0.25, 0.25, 0.75, 0.75)) == pytest.approx(200, abs=3)


def test_rb_ratio_tracks_warmth():
    warm = _jpeg(Image.new("RGB", (64, 48), (200, 120, 80)))
    cool = _jpeg(Image.new("RGB", (64, 48), (80, 120, 200)))
    assert im.rb_ratio(warm) > 2 and im.rb_ratio(cool) < 0.5


def test_sharpness_drops_with_blur():
    sharp_img = _checker()
    blurred = sharp_img.filter(ImageFilter.GaussianBlur(3))
    assert im.sharpness(_jpeg(sharp_img)) > 3 * im.sharpness(_jpeg(blurred))
    m = im.metrics(_jpeg(sharp_img))
    assert m["w"] == 128 and "error" not in m
    assert "error" in im.metrics(b"not a jpeg")
