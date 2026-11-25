"""Self-tests of the step 3b test helpers: the raw frames, the JPEG parsing, the fake Quick Sync
encoder, the raw path of the fake source, the BGR image keeper and the stop line.

These tests pass before the product code of step 3b exists. They give the fake stand-in names for
the product names of ADR-HP7D and ADR-3WCA. Thus a failure of a T-CAP test comes from the product,
not from a helper. Ported from `dom/3bc-tests` (ADR-0Z2F).
"""

from dataclasses import dataclass
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from skellycam.tests.capture import uncompressed as un
from skellycam.tests.capture.fake_source import FakeScript, FakeSource, VirtualClock
from skellycam.tests.capture.test_helpers import STAND_INS, StandInFailure


@dataclass(frozen=True)
class StandInMode3b:
    width: int
    height: int
    fps_num: int
    fps_den: int
    format: str
    device_path: str
    os_range: str | None = None


def stand_in_choose_format(native, request):
    """Exactly the size and format, the nearest rate within 0.5 fps (7.5, 13.1)."""
    near = [m for m in native if (m.width, m.height, m.format) == (request.width, request.height, request.capture_fourcc)
            and abs(m.fps_num / m.fps_den - request.framerate) <= 0.5]
    if not near:
        raise StandInFailure("set mode", "no such mode")
    return near[0]


STAND_INS_3B = SimpleNamespace(**{**vars(STAND_INS), "OpenedMode": StandInMode3b, "choose_mode": stand_in_choose_format})


def raw_request(fmt, width=320, height=240):
    return SimpleNamespace(camera_id="0", width=width, height=height, framerate=30.0, capture_fourcc=fmt)


# ---------------------------------------------------------------------------
# Raw frames and JPEG parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", un.RAW_FORMATS)
@pytest.mark.parametrize("outside", [0.0, 0.005, 0.02])
def test_synthetic_raw_has_the_shape_and_the_exact_share_outside(fmt, outside):
    frame = un.synthetic_raw(fmt, 320, 240, outside)
    assert frame.shape == un.raw_shape(fmt, 320, 240) and frame.dtype == np.uint8 and frame.flags.c_contiguous
    assert un.share_outside(frame, fmt) == pytest.approx(outside, abs=0.5 / (320 * 240))
    inside = un.y_values(frame, fmt).reshape(-1)[round(outside * 320 * 240):]
    assert inside.min() >= 16 and inside.max() <= 235
    assert un.to_bgr(frame, fmt).shape == (240, 320, 3)
    assert un.synthetic_raw(fmt, 320, 240, outside) is not frame, "each call gives a new object"


@pytest.mark.parametrize(("factor", "chroma"), [("IMWRITE_JPEG_SAMPLING_FACTOR_422", "4:2:2"),
                                                ("IMWRITE_JPEG_SAMPLING_FACTOR_420", "4:2:0"),
                                                ("IMWRITE_JPEG_SAMPLING_FACTOR_444", "4:4:4")])
def test_jpeg_chroma_and_quant_tables(factor, chroma):
    image = un.to_bgr(un.synthetic_raw("YUY2", 64, 48), "YUY2")
    params = [int(cv2.IMWRITE_JPEG_QUALITY), 90, int(cv2.IMWRITE_JPEG_SAMPLING_FACTOR), int(getattr(cv2, factor))]
    jpeg = cv2.imencode(".jpg", image, params)[1].tobytes()
    assert un.jpeg_chroma(jpeg) == chroma
    assert un.jpeg_quant_tables(jpeg) == un.Q90_TABLES
    q80 = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 80])[1].tobytes()
    assert un.jpeg_quant_tables(q80) != un.Q90_TABLES
    marked = un.with_mark(jpeg, un.QUICK_SYNC_MARK)
    assert un.is_quick_sync_jpeg(marked) and not un.is_quick_sync_jpeg(jpeg)
    assert un.jpeg_chroma(marked) == chroma


# ---------------------------------------------------------------------------
# The fake Quick Sync encoder
# ---------------------------------------------------------------------------

def stand_in_module():
    return SimpleNamespace(quick_sync_works=lambda: False, open_quick_sync_encoder=None)


def test_quick_sync_fake_counts_checks_and_holds_one_frame(monkeypatch):
    module = stand_in_module()
    fake = un.QuickSyncFake(monkeypatch, available=True, module=module)
    assert module.quick_sync_works() is True and module.quick_sync_works() is True
    assert fake.checks == 2
    encoder = module.open_quick_sync_encoder("NV12", 64, 48, quality=90)
    assert fake.encoders == [encoder]
    frames = [un.synthetic_raw("NV12", 64, 48) for _ in range(3)]
    assert encoder.encode(frames[0]) == []
    outputs = encoder.encode(frames[1]) + encoder.encode(frames[2]) + encoder.flush()
    assert len(outputs) == 3 and encoder.accepted == 3 and encoder.outputs == 3
    for number, jpeg in enumerate(outputs):
        assert un.is_quick_sync_jpeg(jpeg) and un.QUICK_SYNC_MARK + b" %d" % number in jpeg
        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        assert image.shape == (48, 64, 3)
    assert encoder.flush() == []


def test_quick_sync_fake_fails_once_and_refuses_a_wrong_shape(monkeypatch):
    module = stand_in_module()
    fake = un.QuickSyncFake(monkeypatch, available=True, module=module)
    encoder = module.open_quick_sync_encoder("YUY2", 64, 48, quality=90)
    calls = []
    fake.fail_when = lambda: len(calls) >= 2
    for _ in range(2):
        calls.append(encoder.encode(un.synthetic_raw("YUY2", 64, 48)))
    with pytest.raises(RuntimeError):
        encoder.encode(un.synthetic_raw("YUY2", 64, 48))
    assert fake.failures == 1 and encoder.failed and encoder.accepted == 2 and encoder.outputs == 1
    with pytest.raises(RuntimeError):
        encoder.flush()  # the held frame does not come out of a failed device
    encoder.failed = False  # only to reach the shape check below
    with pytest.raises(ValueError):
        encoder.encode(np.zeros(64 * 48 * 2 - 100, np.uint8))
    assert encoder.shapes[-1] == (64 * 48 * 2 - 100,)
    assert fake.failures == 1, "a second failure was raised"


def test_quick_sync_fake_refuses_an_open_after_false(monkeypatch):
    module = stand_in_module()
    un.QuickSyncFake(monkeypatch, available=False, module=module)
    assert module.quick_sync_works() is False
    with pytest.raises(AssertionError):
        module.open_quick_sync_encoder("YUY2", 64, 48, quality=90)


def test_quick_sync_fake_without_the_product_module(monkeypatch):
    """`available=False` replaces nothing; `available=True` fails the test and names the module."""
    import importlib

    real = importlib.import_module

    def no_encoder(name, *args):
        if name == un.ENCODER_MODULE:
            raise ModuleNotFoundError(name)
        return real(name, *args)

    monkeypatch.setattr(un.importlib, "import_module", no_encoder)
    assert un.QuickSyncFake(monkeypatch, available=False).module is None
    with pytest.raises(pytest.fail.Exception, match="capture.encoder"):
        un.QuickSyncFake(monkeypatch, available=True)


# ---------------------------------------------------------------------------
# The raw path of the fake source
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", un.RAW_FORMATS)
def test_fake_raw_frames_range_schedule_and_os_flag(fmt):
    script = FakeScript(modes=((320, 240, 30, 1, "MJPG"), (320, 240, 30, 1, fmt)), os_range="limited",
                        y_outside=((0, 0.005), (5, 0.02)))
    source = FakeSource(script, clock=VirtualClock(), types=STAND_INS_3B)
    opened = source.open(raw_request(fmt))
    assert (opened.format, opened.os_range) == (fmt, "limited")
    frames = [source.read_frame(1.0) for _ in range(8)]
    assert [f.source_frame_number for f in frames] == list(range(8))
    for frame in frames:
        assert frame.format == fmt and frame.payload.shape == un.raw_shape(fmt, 320, 240)
        assert frame.delivered_len == frame.payload.nbytes
    assert [round(un.share_outside(f.payload, fmt), 3) for f in frames] == [0.005] * 5 + [0.02] * 3
    assert len({id(f.payload) for f in frames}) == 8


def test_fake_short_raw_frame_and_mjpg_mode_without_os_flag():
    source = FakeSource(FakeScript(modes=((320, 240, 30, 1, "YUY2"),), short_frames=(2,)), clock=VirtualClock(),
                        types=STAND_INS_3B)
    source.open(raw_request("YUY2"))
    frames = [source.read_frame(1.0) for _ in range(3)]
    source.short_next()
    frames.append(source.read_frame(1.0))
    assert source.short == [2, 3]
    for frame in frames[2:]:
        assert frame.payload.shape == (320 * 240 * 2 - 100,) and frame.delivered_len == 320 * 240 * 2 - 100
    assert frames[1].payload.shape == (240, 320, 2)
    mjpg = FakeSource(FakeScript(modes=((320, 240, 30, 1, "MJPG"),)), clock=VirtualClock(), types=STAND_INS)
    assert not hasattr(mjpg.open(raw_request("MJPG")), "os_range"), "an MJPG open gives the 3a OpenedMode"


def test_fake_raw_open_without_the_os_range_field():
    """A product `OpenedMode` with no `os_range` field: the raw open still works, with no range flag."""
    source = FakeSource(FakeScript(modes=((320, 240, 30, 1, "YUY2"),), os_range="limited"), clock=VirtualClock(),
                        types=SimpleNamespace(**{**vars(STAND_INS), "choose_mode": stand_in_choose_format}))
    opened = source.open(raw_request("YUY2"))
    assert opened.format == "YUY2" and not hasattr(opened, "os_range")


# ---------------------------------------------------------------------------
# The stop line and the range conversions
# ---------------------------------------------------------------------------

def test_stop_line_count_with_another_word():
    messages = ["Camera ab12 replaced 3 frames", "Camera ab12: encoder fallbacks 1"]
    assert un.stop_line_count(messages, "ab12", "replaced") == 3
    assert un.stop_line_count(messages, "ab12", "encoder fallbacks") == 1
    with pytest.raises(AssertionError):
        un.stop_line_count(messages, "cd34", "encoder fallbacks")


@pytest.mark.parametrize("fmt", un.RAW_FORMATS)
def test_full_range_conversion_keeps_the_levels_and_differs_from_the_default(fmt):
    frame = un.synthetic_raw(fmt, 64, 48)
    gray = frame.copy()
    un.y_values(gray, fmt)[...] = 77
    if fmt == "YUY2":
        gray[:, :, 1] = 128
    else:
        gray[48:] = 128
    assert np.all(un.full_range_to_bgr(gray, fmt) == 77), "a full-range gray must keep its level"
    assert np.all(np.abs(un.to_bgr(gray, fmt).astype(int) - round((77 - 16) * 255 / 219)) <= 1), \
        "the default conversion expands a limited-range level"
    assert un.mean_difference(un.full_range_to_bgr(frame, fmt), un.to_bgr(frame, fmt)) > 3.0
    assert un.mean_difference(frame, frame) == 0.0
