"""T-TIM-01 to T-TIM-03, T-TIM-22 and the Python part of T-TIM-24 (specs/capture-timings.md 5.1, 5.2, 6.1, 3.1, 8.5)."""

import json
import random
import threading
from pathlib import Path

from skellycam.tests.capture_timings.loop_harness import timings

FIXTURE = Path(__file__).with_name("summary_fixture.json")


def test_t_tim_01_nearest_rank_statistics_and_rounding():
    """T-TIM-01: nearest-rank p50, p95 and max for known lists; n 0 gives null; rounding to 0.001 ms."""
    stats = timings().stats
    assert stats(1, [5_000_000]) == dict(n=1, p50_ms=5.0, p95_ms=5.0, max_ms=5.0)
    assert stats(2, [3_000_000, 1_000_000]) == dict(n=2, p50_ms=1.0, p95_ms=3.0, max_ms=3.0)
    twenty = [k * 1_000_000 for k in range(1, 21)]
    random.Random(7).shuffle(twenty)
    assert stats(20, twenty) == dict(n=20, p50_ms=10.0, p95_ms=19.0, max_ms=20.0)
    full = [k * 1000 for k in range(1, 513)]
    random.Random(8).shuffle(full)
    assert stats(512, full) == dict(n=512, p50_ms=0.256, p95_ms=0.487, max_ms=0.512)
    assert stats(0, []) == dict(n=0, p50_ms=None, p95_ms=None, max_ms=None)
    assert stats(3, [1_234_567, 1_234_500, 1_234_499]) == dict(n=3, p50_ms=1.235, p95_ms=1.235, max_ms=1.235)
    assert stats(1, [1_234_499])["p50_ms"] == 1.234


def test_t_tim_02_a_window_takes_the_samples_between_two_totals():
    """T-TIM-02: the samples of a window are those from the last total to the new one; more than 512 samples give
    the full n and statistics over the newest 512."""
    module = timings()
    samples = module.StepSamples()
    for value in range(1, 11):
        samples.add(value)
    total, n, values = samples.since(0)
    assert (total, n, sorted(values)) == (10, 10, list(range(1, 11)))
    for value in range(11, 16):
        samples.add(value)
    total, n, values = samples.since(10)
    assert (total, n, sorted(values)) == (15, 5, list(range(11, 16)))
    for value in range(16, 616):
        samples.add(value * 1000)
    total, n, values = samples.since(15)
    assert (total, n) == (615, 600)
    assert sorted(values) == [value * 1000 for value in range(104, 616)]  # the newest 512
    assert module.stats(n, values) == dict(n=600, p50_ms=module.stats(512, values)["p50_ms"],
                                           p95_ms=module.stats(512, values)["p95_ms"], max_ms=0.615)
    assert module.CAPACITY == 512


def test_t_tim_03_the_writer_stores_before_it_counts():
    """T-TIM-03: a writer thread stores 1 to 200,000 in groups of 400 and waits for the reader after each group;
    the reader closes windows meanwhile. Each window holds consecutive integers, and the windows join with no gap
    and no overlap."""
    module = timings()
    control = module.TimingControl(lambda: 0)
    steps = module.StepSet(control, ("x",))
    reader = module.WindowReader()
    group_done, reader_done = threading.Event(), threading.Event()
    last, finished = 200_000, threading.Event()

    def write():
        for start in range(1, last + 1, 400):
            for value in range(start, start + 400):
                steps.add("x", value)
            group_done.set()
            reader_done.wait(10)
            reader_done.clear()
        finished.set()

    seen = []

    def read_window():
        n, values = reader.read([steps]).get("x", (0, []))
        assert n == len(values), "no window holds more than one group"
        assert sorted(values) == values == list(range(len(seen) + 1, len(seen) + 1 + n)), "a gap or a wrong value"
        seen.extend(values)

    writer = threading.Thread(target=write)
    writer.start()
    while not finished.is_set():
        read_window()
        if group_done.is_set():
            group_done.clear()
            read_window()
            reader_done.set()
    writer.join(10)
    read_window()
    assert len(seen) == last


STEP_TABLE = {  # table 3.1 and table 8.5 of the spec
    "camera_wait": ("wait", "frame", "camera_loop"),
    "gate_wait": ("wait", "frame", "camera_loop"),
    "camera_sample_copy": ("work", "frame", "camera_callback"),
    "opencv_retrieve": ("work", "frame", "camera_loop"),
    "jpeg_encode": ("work", "frame", "camera_loop"),
    "capture_check": ("work", "frame", "camera_loop"),
    "frame_hash": ("work", "frame", "camera_loop"),
    "recorder_give": ("wait", "frame", "camera_loop"),
    "ring_write": ("work", "frame", "camera_loop"),
    "exposure_search_brightness": ("work", "event", "camera_loop"),
    "diagnostics_publish": ("work", "second", "camera_loop"),
    "take_start": ("work", "event", "camera_loop"),
    "take_end": ("wait", "event", "camera_loop"),
    "bgr_decode": ("work", "frame", "decode_thread"),
    "bgr_ring_write": ("work", "frame", "decode_thread"),
    "mkv_mux": ("work", "frame", "recorder_thread"),
    "csv_row": ("work", "frame", "recorder_thread"),
    "fsync": ("work", "second", "recorder_thread"),
    "mkv_close": ("work", "event", "recorder_thread"),
    "preview_ring_read": ("work", "frame", "main_process"),
    "preview_pack": ("work", "frame", "main_process"),
    "preview_send": ("work", "frame", "main_process"),
    "ui_jpeg_decode": ("work", "frame", "ui_tile"),
    "ui_draw": ("work", "frame", "ui_tile"),
}
DELAY_TABLE = {"arrival_to_published": "camera_loop", "published_to_send": "main_process", "receive_to_draw": "ui_tile"}


def test_t_tim_22_the_step_registry():
    """T-TIM-22: `STEPS` (id: kind, cadence, where) equals table 3.1 and table 8.5; the delays of section 4. The ids
    of the summaries of the other tests are checked with `assert_known_ids`."""
    module = timings()
    assert module.STEPS == STEP_TABLE
    assert module.DELAYS == DELAY_TABLE
    assert set(module.CAMERA_STEPS) | set(module.MEDIA_FOUNDATION_STEPS) | set(module.OPENCV_STEPS) \
        | set(module.BGR_STEPS) | set(module.PREVIEW_STEPS) == set(STEP_TABLE) - {"ui_jpeg_decode", "ui_draw"}


def assert_known_ids(summary):
    """T-TIM-22: each id of a summary is in `STEPS` or `DELAYS`, with the kind, cadence and where of the table."""
    for step_id, entry in summary["steps"].items():
        assert (entry["kind"], entry["cadence"], entry["where"]) == STEP_TABLE[step_id], step_id
    for delay_id, entry in summary["delays"].items():
        assert entry["where"] == DELAY_TABLE[delay_id], delay_id


def test_t_tim_24_one_shape_python_part():
    """T-TIM-24 (the Python part): the summary function gives the summary of the shared fixture file. The
    TypeScript part comes with step 4b (section 11 step 8)."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    given = dict(fixture["input"])
    given["windows"] = {key: (n, values) for key, (n, values) in given["windows"].items()}
    summary = timings().build_summary(**given)
    assert json.loads(json.dumps(summary)) == fixture["expected"]
    assert_known_ids(summary)
