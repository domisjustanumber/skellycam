"""Capture timings: the time of each slow step of the frame path, as one summary once per second
(specs/capture-timings.md).

Each writer instance (the camera loop, a source, a decode stage, a camera writer, a websocket connection) has its own
`StepSet`, written by one thread. One reader of each process closes the windows (`WindowReader`) and makes the
summaries (`build_summary`). A bracket reads the clock only through its `TimingControl`, and only when `on` is set.
"""
import array
import math
import time

CAPACITY = 512  # 5.1: the newest durations of a step
VERSION = 1  # 6.7
MAX_AGE_NS = 3_000_000_000  # 6.3: an older summary of a camera is left out

# Table 3.1: id: (kind, cadence, where)
STEPS = {
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
DELAYS = {"arrival_to_published": "camera_loop", "published_to_send": "main_process", "receive_to_draw": "ui_tile"}

# Table 5.4: the steps that apply
RECORDER_STEPS = ("mkv_mux", "csv_row", "fsync", "mkv_close")
CAMERA_STEPS = ("camera_wait", "gate_wait", "capture_check", "frame_hash", "recorder_give", "ring_write",
                "exposure_search_brightness", "diagnostics_publish", "take_start", "take_end") + RECORDER_STEPS
MEDIA_FOUNDATION_STEPS = ("camera_sample_copy",)
OPENCV_STEPS = ("opencv_retrieve", "jpeg_encode")
BGR_STEPS = ("bgr_decode", "bgr_ring_write")
PREVIEW_STEPS = ("preview_ring_read", "preview_pack", "preview_send")
# The ids that the loop thread writes into its own set
LOOP_STEPS = ("camera_wait", "gate_wait", "jpeg_encode", "capture_check", "frame_hash", "recorder_give", "ring_write",
              "exposure_search_brightness", "diagnostics_publish", "take_start", "take_end", "arrival_to_published")

main_clock_ns = time.perf_counter_ns  # the main-process clock of a receipt and of the age rule (6.2, 6.3)


class TimingControl:
    """The switch of one process (`on`) and the clock of its brackets (5.1). Only a bracket calls `clock()`."""

    def __init__(self, clock):
        self.on = False
        self._clock = clock

    def clock(self) -> int:
        return self._clock()


class StepSamples:
    """The newest CAPACITY durations of one step in nanoseconds, and the count since its creation (5.1). One writer
    thread: it stores, then counts, so a reader that reads `total` first sees only stored values."""

    __slots__ = ("values", "total")

    def __init__(self):
        self.values = array.array("q", bytes(8 * CAPACITY))
        self.total = 0

    def add(self, duration_ns: int) -> None:
        self.values[self.total % CAPACITY] = duration_ns
        self.total += 1

    def since(self, last_total: int) -> tuple:
        """(total, n, the newest samples up to CAPACITY) of the samples after `last_total`."""
        total = self.total
        values = self.values
        return total, total - last_total, [values[i % CAPACITY] for i in range(max(last_total, total - CAPACITY), total)]


class StepSet:
    """The samples of one writer instance (5.1). A set of a thread that another thread reads gets each id at its
    creation, so that its dict never changes size during a read."""

    def __init__(self, control: TimingControl, ids=()):
        self.control = control
        self.samples = {key: StepSamples() for key in ids}

    def add(self, key, duration_ns: int) -> None:
        samples = self.samples.get(key)
        if samples is None:  # only a set of one thread grows: the steps of each camera of a connection
            samples = self.samples[key] = StepSamples()
        samples.add(duration_ns)


OFF_SET = StepSet(TimingControl(time.perf_counter_ns))  # the set of a source that no loop measures: never on


class WindowReader:
    """The one reader of the sets of a process (5.1): it keeps the total of its last read of each buffer and writes
    nothing into a buffer. A retired set is read one more time, then dropped."""

    def __init__(self):
        self._totals = {}
        self._retired = []

    def retire(self, step_set: StepSet | None) -> None:
        if step_set is not None and step_set is not OFF_SET:
            self._retired.append(step_set)

    def read(self, current) -> dict:
        """{key: (n, samples)} of the window that ends now, merged over the retired sets and `current`."""
        retired, self._retired = self._retired, []
        totals, windows = {}, {}
        for step_set in retired + [s for s in current if s is not None and s is not OFF_SET]:
            for key, samples in list(step_set.samples.items()):
                total, n, values = samples.since(self._totals.get(samples, 0))
                if step_set not in retired:
                    totals[samples] = total
                if n:
                    old_n, old_values = windows.get(key, (0, []))
                    windows[key] = (old_n + n, old_values + values)
        self._totals = totals
        return windows


def to_ms(ns: int) -> float:
    """Milliseconds, rounded half up to 0.001 ms in integers, so that the tile gives the same value (5.2, T-TIM-24)."""
    return ((ns + 500) // 1000) / 1000


def stats(n: int, values) -> dict:
    """5.2: `n`, and the nearest-rank p50 and p95 and the max over the newest CAPACITY samples; null for n 0."""
    if not n:
        return dict(n=0, p50_ms=None, p95_ms=None, max_ms=None)
    ordered = sorted(values[-CAPACITY:])
    count = len(ordered)
    return dict(n=n, p50_ms=to_ms(ordered[math.ceil(0.5 * count) - 1]),
                p95_ms=to_ms(ordered[math.ceil(0.95 * count) - 1]), max_ms=to_ms(ordered[-1]))


def build_summary(*, source: str, camera_group_id, camera_id, clock: str, seq: int, window_end_ns: int,
                  window_ns: int, step_ids, windows: dict) -> dict:
    """The summary of 6.1: each id of `step_ids` and of `windows`, a step or a delay; n 0 for an id with no sample."""
    ids = set(step_ids) | set(windows)
    steps, delays = {}, {}
    for key in [key for key in STEPS if key in ids]:
        kind, cadence, where = STEPS[key]
        steps[key] = dict(kind=kind, cadence=cadence, where=where, **stats(*windows.get(key, (0, []))))
    for key in [key for key in DELAYS if key in ids]:
        delays[key] = dict(where=DELAYS[key], **stats(*windows.get(key, (0, []))))
    return dict(source=source, camera_group_id=camera_group_id, camera_id=camera_id, clock=clock, seq=seq,
                window_end_ns=window_end_ns, window_s=((window_ns + 500_000) // 1_000_000) / 1000, steps=steps,
                delays=delays)


class PreviewTimings:
    """The preview steps of one websocket connection and their summaries (5.1, 6.5). The event loop of the connection
    writes and reads them. A key is (group id, camera id or None for the group message, step id)."""

    def __init__(self, clock=time.perf_counter_ns):
        self.control = TimingControl(clock)
        self.steps = StepSet(self.control)
        self._reader = WindowReader()
        self._seq = {}
        self._window_start = 0

    def summaries(self, on: bool, group_ids) -> list:
        """Close the window: one `"preview"` summary for each camera (and group message) of `group_ids` that this
        connection measured. A change of `on` applies here; the first window after a change to on gives none."""
        was_on, self.control.on = self.control.on, on
        windows = self._reader.read([self.steps])
        for key in [key for key in self.steps.samples if key[0] not in group_ids]:  # a group that is gone
            del self.steps.samples[key]
        for key in [key for key in self._seq if key[0] not in group_ids]:
            del self._seq[key]
        if not on:
            return []
        now = self.control.clock()
        start, self._window_start = self._window_start, now
        if not was_on:
            return []
        by_source = {}
        for group_id, camera_id, step_id in list(self.steps.samples):
            if group_id in group_ids:
                by_source.setdefault((group_id, camera_id), set()).add(step_id)
        result = []
        for (group_id, camera_id), step_ids in by_source.items():
            seq = self._seq.get((group_id, camera_id), 0)
            self._seq[(group_id, camera_id)] = seq + 1
            result.append(build_summary(
                source="preview", camera_group_id=group_id, camera_id=camera_id, clock="perf_counter_ns", seq=seq,
                window_end_ns=now, window_ns=now - start, step_ids=step_ids,
                windows={key[2]: value for key, value in windows.items() if key[:2] == (group_id, camera_id)}))
        return result
