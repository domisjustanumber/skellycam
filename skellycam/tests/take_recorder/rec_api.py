"""Shared helpers of the recorder tests (specs/recorder.md, section 12).

The product package is imported inside each test (`rec()`), so that pytest collects each test and
each test fails only because the package does not exist yet. The names that the tests assume and
that the spec does not fix are in ADR-QEQ8. The expected values here come from the spec text, not
from the product.
"""

import hashlib
import importlib
import json
import os
import threading
from pathlib import Path

from skellycam.tests.take_recorder import jpeg_tools

REC_MODULE = "skellycam.core.take_recorder"
WRITER = "skellycam 2.0.0"
T0 = 1_000_000_000_000  # the host clock at the take start, in the tests with a fixed clock
UTC0 = 1_795_000_000_123_456_789  # the UTC clock at the take start, in the same tests
MEDIA = "synchronized_videos"

# SKELLYCAM_BENCH=1 runs the benchmarks and the full forms of T-REC-KILL (section 12.1, agent 27).
BENCH = os.environ.get("SKELLYCAM_BENCH", "") == "1"
BENCH_OUT = os.environ.get("SKELLYCAM_BENCH_OUT", "")


def rec():
    """Import the recorder package inside a test, so that a missing package fails the test."""
    return importlib.import_module(REC_MODULE)


def rec_module(name):
    return importlib.import_module(f"{REC_MODULE}.{name}")


def ring_flags():
    from skellycam.core.ipc.frame_ring import NO_SAMPLE_NS, FrameFlag

    return FrameFlag, NO_SAMPLE_NS


# ---------------------------------------------------------------------------
# Spec rules written in the tests (6.2, 6.3, 5.1)
# ---------------------------------------------------------------------------

def camera_key(camera_id):
    """6.2 [C3]: `camera_id` + the first 12 hexadecimal characters of the SHA-256 of its UTF-8 bytes."""
    return camera_id + hashlib.sha256(camera_id.encode("utf-8")).hexdigest()[:12]


def camera_label(camera_id):
    return camera_key(camera_id)[:6]


def block_time_ms(k, num, den):
    """SFF-736: ⌊(2 × k × den × 1000 + num) / (2 × num)⌋ ms."""
    return (2 * k * den * 1000 + num) // (2 * num)


def default_duration_ns(num, den):
    return 10**9 * den // num


def queue_size(num, den, seconds=3.0):
    """5.1 [agent 4]: ⌈queue_seconds × num / den⌉ items, computed with integers where exact."""
    from fractions import Fraction

    value = Fraction(str(seconds)) * num / den
    return -(-value.numerator // value.denominator)


def fixed_clock(host=T0, utc=UTC0, calls=None):
    """The `clock` test seam of start_take (4.2): (host clock, UTC clock). `calls` records the order."""

    def host_clock():
        if calls is not None:
            calls.append("host")
        return host

    def utc_clock():
        if calls is not None:
            calls.append("utc")
        return utc

    return host_clock, utc_clock


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def layout_of(payload):
    return rec().parse_sof(payload)


def take_camera(camera_id, *, rate=(30, 1), width=640, height=480, layout="422", rotation=0,
                capture_format="MJPG", os_index=0, os_name="Synthetic Camera", vendor_id="046d",
                product_id="0825", backend="media_foundation", requested=None, controls=None):
    """A TakeCamera (4.2, ADR-QEQ8). `layout` is a key of jpeg_tools.LAYOUTS, a JpegLayout, or None."""
    module = rec()
    if isinstance(layout, str):
        layout = module.parse_sof(jpeg_tools.synthetic_jpeg(0, width, height, layout))
    return module.TakeCamera(
        camera_id=camera_id, nominal_rate=rate, width=width, height=height, rotation_cw_deg=rotation,
        capture_format=capture_format, layout=layout, os_name=os_name, vendor_id=vendor_id,
        product_id=product_id, backend=backend, os_index=os_index,
        requested=requested or {"width": width, "height": height, "framerate": rate[0] / rate[1] if rate[1] else 0,
                                "capture_format": capture_format, "exposure_mode": "manual"},
        controls=controls if controls is not None else {"exposure": (-5.0, False), "gain": (0.0, False),
                                                        "focus": (None, None)},
    )


def recorder_frame(payload, k, *, arrival_ns, sample_ns=None, sfn=None, flags=0, rotation=0):
    """A RecorderFrame (4.1). `sample_ns` None gives NO_SAMPLE_NS."""
    _, no_sample = ring_flags()
    return rec().RecorderFrame(
        payload=payload, frame_number=k, arrival_ns=arrival_ns,
        sample_ns=no_sample if sample_ns is None else sample_ns,
        source_frame_number=1000 + k if sfn is None else sfn, flags=int(flags),
        delivered_len=len(payload), rotation_cw_deg=rotation,
    )


class Frames:
    """Synthetic JPEGs of one size and layout, cached by index."""

    def __init__(self, width=640, height=480, layout="422", quality=90):
        self.width, self.height, self.layout, self.quality = width, height, layout, quality
        self.cache = {}

    def __call__(self, k):
        if k not in self.cache:
            self.cache[k] = jpeg_tools.synthetic_jpeg(k, self.width, self.height, self.layout, self.quality)
        return self.cache[k]


class Run:
    """One take in one process: the take level and one camera writer for each camera (4.4, R10).

    It records each payload that it gives, so a test can compare the blocks. `close()` ends each
    writer that is still open, so that no writer thread outlives a failed test.
    """

    def __init__(self, folder, cameras, *, name="take", clock=None, queue_seconds=3.0, stall_limit_s=10.0,
                 writer_clock=None, start_writers=True, frames=None, **kwargs):
        module = rec()
        self.module, self.folder, self.name = module, Path(folder), name
        self.cameras = cameras
        self.frames = frames or Frames(cameras[0].width, cameras[0].height)
        self.take = module.start_take(self.folder, name, cameras, writer=WRITER,
                                      clock=clock or fixed_clock(), queue_seconds=queue_seconds,
                                      stall_limit_s=stall_limit_s, **kwargs)
        self.writers, self.given, self.results = {}, {c.camera_id: [] for c in cameras}, {}
        self.writer_clock = writer_clock
        if start_writers:
            for camera in cameras:
                self.start_writer(camera.camera_id)

    def start_writer(self, camera_id):
        spec = self.take.camera_spec(camera_id)
        if self.writer_clock is None:
            writer = self.module.CameraTakeWriter.start(spec)
        else:
            writer = self.module.CameraTakeWriter.start(spec, clock=self.writer_clock)
        self.writers[camera_id] = writer
        return writer

    def rate(self, camera_id):
        camera = next(c for c in self.cameras if c.camera_id == camera_id)
        return camera.nominal_rate

    def give(self, camera_id, k, *, payload=None, arrival_ns=None, sample_ns=-1, sfn=None, flags=0):
        """Give frame k. Default times: arrival T0 + k periods + 1 ms; sample 0.5 ms before."""
        num, den = self.rate(camera_id)
        payload = self.frames(k) if payload is None else payload
        arrival = T0 + k * 10**9 * den // num + 1_000_000 if arrival_ns is None else arrival_ns
        sample = arrival - 500_000 if sample_ns == -1 else sample_ns
        frame = recorder_frame(payload, k, arrival_ns=arrival, sample_ns=sample, sfn=sfn, flags=flags)
        self.given[camera_id].append(("frame", frame))
        self.writers[camera_id].give(frame)
        return frame

    def give_missing(self, camera_id):
        self.given[camera_id].append(("missing", None))
        self.writers[camera_id].give_missing()

    def end(self, frame_count, camera_ids=None):
        for camera_id in camera_ids or list(self.writers):
            if camera_id not in self.results:
                self.results[camera_id] = self.writers[camera_id].end(frame_count)
        return self.results

    def finish(self, frame_count, *, results=None, ended_by_error=None, dead_cameras=None):
        """`dead_cameras` is the assumed keyword of ADR-QEQ8: {camera_id: reason} of each camera that
        stopped during the take. It is passed only when a test names one."""
        self.end(frame_count)
        if results is None:
            results = [self.results.get(c.camera_id) for c in self.cameras]
        extra = {} if dead_cameras is None else {"dead_cameras": dead_cameras}
        return self.take.finish(results, frame_count=frame_count, ended_by_error=ended_by_error, **extra)

    def close(self):
        for camera_id, writer in self.writers.items():
            if camera_id not in self.results:
                try:
                    self.results[camera_id] = writer.end(max(len(self.given[camera_id]), 1))
                except Exception:
                    pass

    # --- paths ---

    def label(self, camera_id):
        return camera_label(camera_id)

    def mkv(self, camera_id):
        return self.folder / MEDIA / f"{self.name}.{camera_label(camera_id)}.mkv"

    def csv(self, camera_id):
        return self.folder / MEDIA / f"{self.name}.{camera_label(camera_id)}.csv"

    def manifest(self):
        return read_json(self.folder / "recording_manifest.json")

    def info(self):
        return read_json(self.folder / f"{self.name}_info.json")


def simple_take(folder, runs, *, ids=("0a1b", "ff00"), frames=100, finish=True, **kwargs):
    """Start a take, give `frames` good frames to each camera, and (with `finish`) end it."""
    cameras = [take_camera(camera_id, os_index=i) for i, camera_id in enumerate(ids)]
    run = Run(folder, cameras, **kwargs)
    runs.append(run)
    for k in range(frames):
        for camera_id in ids:
            run.give(camera_id, k)
    if finish:
        run.summary = run.finish(frames)
    return run


DAMAGED_BYTES = b"\xff\xd8DAMAGED-FRAME-BYTES" * 50  # the bytes of a damaged frame: never in a camera file (R3)


def damaged_take(folder, runs, *, flags=None, frames=100):
    """The take of T-REC-12: cameras A (`0a1b`) and B (`ff00`), frames 0 to 99. A's frames 20 and 21
    have `CAPTURE_ERROR`, frame 50 `NO_SOI_EOI` (or each frame of `flags`, a {k: flag} map)."""
    frame_flag, _ = ring_flags()
    flags = flags or {20: frame_flag.CAPTURE_ERROR, 21: frame_flag.CAPTURE_ERROR, 50: frame_flag.NO_SOI_EOI}
    run = Run(folder, [take_camera("0a1b", os_index=0), take_camera("ff00", os_index=1)])
    runs.append(run)
    for k in range(frames):
        if k in flags:
            run.give("0a1b", k, payload=DAMAGED_BYTES, flags=flags[k])
        else:
            run.give("0a1b", k)
        run.give("ff00", k)
    run.summary = run.finish(frames)
    return run, flags


def dead_take(folder, runs, *, case=1):
    """The take of T-REC-23: 600 group frames. Camera B (`ff00`) dies at row 300: the test gives
    `give_missing` for rows 300 to 549, then `end(600)`. Case 2: B's rows 297 to 299 are damaged
    frames. Case 3: B dies before its first frame (`give_missing` for rows 0 to 549)."""
    frame_flag, _ = ring_flags()
    run = Run(folder, [take_camera("0a1b", os_index=0), take_camera("ff00", os_index=1)])
    runs.append(run)
    death = 0 if case == 3 else 300
    for k in range(600):
        run.give("0a1b", k)
        base = T0 + k * 10**9 // 30
        if k < death:  # B arrives 2 ms after A; its damaged frames 14 ms after A (they must not count, 8.2)
            if case == 2 and k >= 297:
                run.give("ff00", k, payload=DAMAGED_BYTES, flags=frame_flag.CAPTURE_ERROR, arrival_ns=base + 15_000_000)
            else:
                run.give("ff00", k, arrival_ns=base + 3_000_000)
        elif k < 550:
            run.give_missing("ff00")
    run.summary = run.finish(600, dead_cameras={"ff00": DEAD_REASON})
    return run


DEAD_REASON = "device removed"


def hand_stop_fields(cameras_rows):
    """The statistics of 8.2, computed by hand. `cameras_rows` holds, for each camera, a list of
    (arrival_ns or None, missing) for each group frame. A `missing` row is left out of each statistic.
    Returns (rates, durations_ms, ranges_ms): the per-frame values that the fields summarise."""
    rates, durations, ranges = [], [], []
    for k in range(len(cameras_rows[0])):
        live = [rows[k][0] for rows in cameras_rows if not rows[k][1] and rows[k][0] is not None]
        if live:
            ranges.append((max(live) - min(live)) / 1e6)
        if k == 0:
            continue
        pairs = [(rows[k - 1][0], rows[k][0]) for rows in cameras_rows if not rows[k][1] and not rows[k - 1][1]]
        if pairs:
            rates.append(sum(1e9 / (b - a) for a, b in pairs) / len(pairs))
            durations.append(sum((b - a) / 1e6 for a, b in pairs) / len(pairs))
    return rates, durations, ranges


def hand_mean_framerate(cameras_rows):
    """`mean_framerate` of 8.2 by hand (decision M of the user, 2026-11-20): for each camera, the group frames
    from its first to its last row with a time, divided by the time between them (arrival, s); the mean over
    the cameras, rounded to 2 decimals. NaN (null) when no camera has two rows with a time."""
    rates = []
    for rows in cameras_rows:
        timed = [(k, t) for k, (t, missing) in enumerate(rows) if not missing and t is not None]
        if len(timed) >= 2 and timed[-1][1] > timed[0][1]:
            rates.append((timed[-1][0] - timed[0][0]) / ((timed[-1][1] - timed[0][1]) / 1e9))
    return round(sum(rates) / len(rates), 2) if rates else float("nan")


def tree(root):
    """Each file and folder under `root`, as relative POSIX paths (folders end with `/`)."""
    root = Path(root)
    return sorted(p.relative_to(root).as_posix() + ("/" if p.is_dir() else "") for p in root.rglob("*"))


def snapshot(root):
    """The paths, sizes and modification times under `root`: a test compares two snapshots."""
    root = Path(root)
    return {p.relative_to(root).as_posix(): (p.is_dir(), p.stat().st_size, p.stat().st_mtime_ns) for p in root.rglob("*")}


def read_json(path):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"), object_pairs_hook=_ordered)


def _ordered(pairs):
    return dict(pairs)


def warnings_of(manifest, code):
    return [w for w in manifest["warnings"] if w["code"] == code]


def run_in_thread(target, *args):
    """Run `target(*args)` on a daemon thread; return (thread, box) where box holds the result or error."""
    box = {}

    def body():
        try:
            box["result"] = target(*args)
        except BaseException as error:  # noqa: BLE001 - the test reads it
            box["error"] = error

    thread = threading.Thread(target=body, daemon=True)
    thread.start()
    return thread, box
