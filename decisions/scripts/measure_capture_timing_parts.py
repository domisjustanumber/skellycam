"""Timing of the small parts of the frame path for ADR-3TYP. Synthetic JPEG bytes from a generated array; no camera.

Run: uv run python decisions/scripts/measure_capture_timing_parts.py
"""
import hashlib
import json
import multiprocessing
import pickle
import platform
import statistics
import sys
import threading
import time
from array import array
from types import SimpleNamespace

import cv2
import numpy as np

from skellycam.core.camera.capture.camera_loop import CameraLoop, dqt_segments
from skellycam.core.camera.capture.source import CapturedFrame, CaptureWaitingPlace, DIAGNOSTIC_KEYS
from skellycam.core.ipc.frame_ring.capture_check import check_jpeg
from skellycam.core.ipc.frame_ring.decode import DecodeInput, WaitingPlace, decode_jpeg
from skellycam.core.ipc.pubsub.pubsub_topics import DiagnosticsMessage
from skellycam.core.take_recorder.placeholder import parse_sof
from skellycam.core.take_recorder.sidecar import Row, row_line

pc = time.perf_counter_ns
RESULTS = {}


def bench(name, fn, n=2000, warm=50):
    for _ in range(warm):
        fn()
    samples = []
    for _ in range(n):
        t0 = pc()
        fn()
        samples.append(pc() - t0)
    samples.sort()
    RESULTS[name] = dict(n=n, p50_us=round(samples[n // 2] / 1e3, 2), p99_us=round(samples[int(n * 0.99)] / 1e3, 2),
                         max_us=round(samples[-1] / 1e3, 2))


def image(w, h):
    rng = np.random.default_rng(1)
    x = np.linspace(0, 255, w, dtype=np.float32)
    y = np.linspace(0, 255, h, dtype=np.float32)[:, None]
    base = np.stack([np.broadcast_to(x, (h, w)), np.broadcast_to(y, (h, w)), (x + y) / 2 * np.ones((h, w))], -1)
    return np.clip(base + rng.normal(0, 12, (h, w, 3)), 0, 255).astype(np.uint8)


def strip_dht(jpeg: bytes) -> bytes:
    out, i = bytearray(jpeg[:2]), 2
    while i < len(jpeg):
        marker = jpeg[i + 1]
        length = int.from_bytes(jpeg[i + 2:i + 4], "big")
        if marker == 0xDA:
            out += jpeg[i:]
            break
        if marker != 0xC4:
            out += jpeg[i:i + 2 + length]
        i += 2 + length
    return bytes(out)


for label, (w, h) in {"720p": (1280, 720), "1080p": (1920, 1080)}.items():
    img = image(w, h)
    jpeg = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1].tobytes()
    no_dht = strip_dht(jpeg)
    RESULTS[f"jpeg_bytes_{label}"] = len(jpeg)
    bgr = decode_jpeg(jpeg)
    bench(f"np_mean_{label}", lambda: float(np.mean(bgr)), n=300)
    bench(f"decode_jpeg_{label}", lambda: decode_jpeg(jpeg), n=300)
    bench(f"brightness_decode_and_mean_{label}", lambda: float(np.mean(decode_jpeg(jpeg))), n=300)
    bench(f"check_jpeg_with_dht_{label}", lambda: check_jpeg(jpeg, delivered_len=len(jpeg), driver_error=False))
    bench(f"check_jpeg_dht_inserted_{label}", lambda: check_jpeg(no_dht, delivered_len=len(no_dht), driver_error=False))
    bench(f"frame_hash_{label}", lambda: (hashlib.sha256(jpeg).hexdigest(), hashlib.sha256(dqt_segments(jpeg)).hexdigest()))
    bench(f"parse_sof_{label}", lambda: parse_sof(jpeg))
    frame = CapturedFrame(payload=jpeg, format="MJPG", arrival_ns=1, sample_ns=1, delivered_len=len(jpeg),
                          driver_error=False, source_frame_number=1, discontinuity=False)
    place = CaptureWaitingPlace()
    bench(f"capture_waiting_place_put_{label}", lambda: place.put(frame), n=20000)
    item = DecodeInput(payload=jpeg, source="JPEG", frame_number=1, arrival_ns=1, sample_ns=1, source_frame_number=1,
                       flags=0, rotation_cw_deg=0)
    wp = WaitingPlace()
    bench(f"decode_waiting_place_put_{label}", lambda: wp.put(item), n=20000)

row = Row(123456, 123456, 1_234_567_890_123, 1_234_567_000_000, 0, 123_456_789_012, 210_000)
bench("csv_row_line", lambda: row_line(row), n=20000)

count = multiprocessing.Value("q", -1, lock=False)
replaced = multiprocessing.Value("q", 0, lock=False)
bench("status_update_two_stores", lambda: (setattr(count, "value", 5), setattr(replaced, "value", 2)), n=20000)

last = multiprocessing.Value("q", -1)
first = multiprocessing.Value("q", 10, lock=False)


def decision():
    if first.value == -1:
        return False, False
    lock = last.get_lock()
    lock.acquire(timeout=0.5)
    try:
        value = last.value
    finally:
        lock.release()
    return 11 >= first.value, value


bench("frame_decision_in_take_uncontended", decision, n=20000)

fake = SimpleNamespace(take_writer=object(), block=(0, 0), slow=False, reference_rate=30.0, camera_id="a1b2",
                       check=None, search=None)
frames = [CapturedFrame(b"", "MJPG", i * 33_333_333, 0, 0, False, i, False) for i in range(1, 30001)]
it = iter(frames)
bench("rate_checks_feed_check_and_feed_block", lambda: (CameraLoop._feed_check(fake, f := next(it)),
                                                        CameraLoop._feed_block(fake, f)), n=20000)

# A diagnostics dict of the largest form (about 150 keys, 64 frame_log rows, 60 hash keys) plus a summary.
diag = {key: 123456 for key in DIAGNOSTIC_KEYS}
diag["frame_log"] = [[i, i, 1_234_567_890_123 + i, 1_234_567_890_999 + i, 210_000] for i in range(64)]
for i in range(30):
    diag[f"sha256_frame_{i:02d}"], diag[f"sha256_{i:02d}"] = i, "ab" * 32
diag["dqt_sha256"] = "cd" * 32
step = dict(kind="work", where="camera_loop", cadence="frame", n=30, p50_ms=0.123, p95_ms=0.456, max_ms=1.234)
summary = dict(source="camera", camera_group_id="g1", camera_id="a1b2", clock="perf_counter_ns", seq=1234,
               window_end_ns=1_234_567_890_123_456, window_s=1.0,
               steps={f"step_{i:02d}": dict(step) for i in range(20)},
               delays={"arrival_to_published": {k: v for k, v in step.items() if k != "kind"}})
message = DiagnosticsMessage(camera_id="a1b2", diagnostics=diag)
RESULTS["diagnostics_pickle_bytes"] = len(pickle.dumps(message))
message.timings = summary
RESULTS["diagnostics_with_summary_pickle_bytes"] = len(pickle.dumps(message))
RESULTS["summary_pickle_bytes"] = len(pickle.dumps(summary))
bench("diagnostics_pickle_with_summary", lambda: pickle.dumps(message), n=2000)

rng = np.random.default_rng(2)
buffers = {f"step_{i:02d}": array("q", rng.integers(10_000, 5_000_000, 512).tolist()) for i in range(20)}


def build_summary():
    out = {}
    for name, buf in buffers.items():
        window = sorted(buf[:60])
        n = len(window)
        out[name] = dict(n=n, p50_ms=round(window[-(-n // 2) - 1] / 1e6, 3),
                         p95_ms=round(window[-(-n * 95 // 100) - 1] / 1e6, 3), max_ms=round(window[-1] / 1e6, 3))
    return out


bench("summary_build_20_steps_60_samples", build_summary, n=2000)

samples, total = array("q", bytes(8 * 512)), [0]


def add():
    samples[total[0] % 512] = 1234567
    total[0] += 1


holder = SimpleNamespace(on=False)
bench("off_branch", lambda: holder.on and add(), n=50000)
bench("perf_counter_ns_call", pc, n=50000)
bench("sample_add", add, n=50000)
bench("empty_lambda_overhead", lambda: None, n=50000)

RESULTS["env"] = dict(python=sys.version.split()[0], numpy=np.__version__, opencv=cv2.__version__,
                      machine=platform.machine(), system=platform.system())
print(json.dumps(RESULTS, indent=1))
