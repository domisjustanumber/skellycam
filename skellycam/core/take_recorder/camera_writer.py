"""The camera level: the camera writer, its queue and its writer thread (specs/recorder.md, 4.3 and 5)."""
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass

from skellycam.core.ipc.frame_ring import NO_SAMPLE_NS
from skellycam.core.take_recorder import sidecar
from skellycam.core.take_recorder.mkv import MkvFile
from skellycam.core.take_recorder.placeholder import JpegLayout, build_placeholder, parse_sof

logger = logging.getLogger(__name__)

ERROR_MASK = 0x0F  # the error bits of the ring flags [ring 4]: the row is `missing` (7.2)
FALLBACK_FACTORS = ((2, 1), (1, 1), (1, 1))  # 4:2:2, the layout of all real camera JPEGs of the research (6.4)
FSYNC_PERIOD_NS = 1_000_000_000  # SFF-788


class RecorderStalled(Exception):
    """`give` waited the stall limit for space in the queue (5.3). The frame in hand is not written."""


class RecorderWriteError(Exception):
    """The writer thread stopped after a write error (5.4)."""


@dataclass(frozen=True)
class CameraTakeResult:
    camera_id: str
    rows: int
    blocks: int
    missing_rows: int
    last_real_row: int | None
    queue_high_water: int
    give_wait_count: int
    give_wait_ms_max: float
    files_closed: bool
    error: str | None


class CameraTakeWriter:
    """One camera's MKV and CSV of a take. The camera loop thread calls `give`, `give_missing` and
    `end`; the writer thread does each file write. Not reusable."""

    def __init__(self, spec):
        self.spec = spec
        # Items: a RecorderFrame; None for a `missing` row with no frame; an int (the frame count) to end.
        self.queue = queue.Queue(maxsize=spec.queue_size)
        self._started = self._ended = False
        self._error = None
        self._closed = False
        self._high_water = self._wait_count = 0
        self._wait_ms_max = 0.0
        self._rows = self._blocks = self._gaps = self._missing = 0
        self._last_real = None
        self._last_frame_number = None
        self._abandoned = False  # set by `end` when the writer made no progress for the stall limit
        self._shared_progress = None
        # Progress (D1): the time.monotonic() at which a write call on the MKV or the CSV, or an fsync,
        # last returned. A call that does not return is no progress: the disk took nothing.
        self._progress_at = time.monotonic()

    def _progress(self) -> None:
        self._progress_at = time.monotonic()
        if self._shared_progress is not None:  # the main process applies D1 at the end of a take (5.3 item 4)
            self._shared_progress.value = self._progress_at

    def _wait_with_progress(self, started, attempt) -> bool:
        """Call `attempt(timeout)` until it returns True. Return False when the writer made no
        progress for the stall limit, counted from `started` or from its last progress, whichever is
        later (D1). Each attempt blocks; nothing polls."""
        while True:
            remaining = max(started, self._progress_at) + self.spec.stall_limit_s - time.monotonic()
            if remaining <= 0:
                return False
            if attempt(remaining):
                return True

    def _try_put(self, item, timeout) -> bool:
        try:
            self.queue.put(item, timeout=timeout)
            return True
        except queue.Full:
            return False

    def _try_join(self, timeout) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    @classmethod
    def start(cls, spec, *, clock=None, progress=None):
        """Open the files, write the MKV header and the CSV header, start the writer thread. `progress` is a
        shared double that gets the time of each progress, for the main process (recorder.md 5.3 item 4)."""
        self = cls(spec)
        self._shared_progress = progress
        self._progress()
        self._clock = clock or time.perf_counter_ns
        self._layout = spec.layout
        self._placeholder = None if spec.layout is None else build_placeholder(spec.layout)
        self._held = []  # rows that wait for the first good frame when the spec has no layout (6.4)
        self._layout_warned = self._sof_warned = False
        self._k, self._pending, self._previous_sfn = 0, None, None
        self._mkv = MkvFile(spec.mkv_path, num=spec.num, den=spec.den, width=spec.width, height=spec.height,
                            on_write=self._progress)
        self._csv = None
        try:
            self._csv = open(spec.csv_path, "xb", buffering=0)
            for key, value in spec.header:
                self._write_line(sidecar.header_line(key, value))
            self._write_line(sidecar.COLUMN_LINE)
        except BaseException:
            self._close_files()
            raise
        self._last_fsync_ns = self._clock()
        self._thread = threading.Thread(target=self._run, name=f"take-writer-{spec.camera_id}")
        self._thread.start()
        self._started = True
        return self

    # --- the camera loop thread ---

    def give(self, frame) -> None:
        """Raises ValueError, and does not queue the frame, when `frame_number` does not increase (4.1)."""
        if self._started and not self._ended and self._last_frame_number is not None \
                and frame.frame_number <= self._last_frame_number:
            raise ValueError(f"camera {self.spec.camera_id}: frame_number {frame.frame_number} after "
                             f"{self._last_frame_number}; it must increase")
        self._put(frame)
        self._last_frame_number = frame.frame_number

    def give_missing(self) -> None:
        self._put(None)

    def _put(self, item) -> None:
        if not self._started or self._ended:
            raise RuntimeError("give before start or after end")
        if self._error is not None:
            raise RecorderWriteError(self._error)
        try:
            self.queue.put_nowait(item)
        except queue.Full:
            # A full queue slows capture and never drops a frame (5.2): wait on the queue, no poll.
            started = time.monotonic()
            try:
                if not self._wait_with_progress(started, lambda timeout: self._try_put(item, timeout)):
                    raise RecorderStalled(f"camera {self.spec.camera_id}: the writer made no progress for "
                                          f"{self.spec.stall_limit_s} s")
            finally:
                self._wait_count += 1
                self._wait_ms_max = max(self._wait_ms_max, (time.monotonic() - started) * 1000)
        self._high_water = max(self._high_water, self.queue.qsize())

    def end(self, frame_count: int) -> CameraTakeResult:
        """Pad with placeholders to `frame_count`, finish both files. A writer that still makes
        progress, however slowly, is left to finish (D1). When it makes no progress for the stall
        limit, `end` returns with `error="disk stall"` (4.3) [C6]."""
        if not self._started or self._ended:
            raise RuntimeError("end before start or a second end")
        self._ended = True
        started = time.monotonic()
        if not (self._wait_with_progress(started, lambda timeout: self._try_put(frame_count, timeout))
                and self._wait_with_progress(started, self._try_join)):
            # The non-daemon writer thread must not wait for ever for the marker, and must not finish
            # files that the take level completes (7.4): it stops after its current item.
            self._abandoned = True
            try:
                self.queue.put_nowait(frame_count)  # wakes a writer that emptied the queue meanwhile
            except queue.Full:
                pass
        stuck = self._thread.is_alive()
        result = CameraTakeResult(
            camera_id=self.spec.camera_id, rows=self._rows, blocks=self._blocks, missing_rows=self._missing,
            last_real_row=self._last_real, queue_high_water=self._high_water, give_wait_count=self._wait_count,
            give_wait_ms_max=self._wait_ms_max, files_closed=self._closed and not stuck,
            error="disk stall" if stuck else self._error)
        logger.info("camera %s: %d rows, %d missing; queue high-water %d of %d items; %d give waits, longest "
                    "%.1f ms; error %s", result.camera_id, result.rows, result.missing_rows, result.queue_high_water,
                    self.spec.queue_size, result.give_wait_count, result.give_wait_ms_max, result.error)
        return result

    def abandon(self) -> None:
        """End the writer thread with no end of the files, as a kill does: the take level completes them
        (7.4). For a take that did not end: the frame count is not known."""
        if not self._started or self._ended:
            raise RuntimeError("abandon before start or after end")
        self._ended = self._abandoned = True
        try:
            self.queue.put_nowait(0)  # wakes a writer that waits on an empty queue
        except queue.Full:
            pass  # the writer takes an item, sees `_abandoned` and stops
        self._thread.join(self.spec.stall_limit_s)

    # --- the writer thread ---

    def _run(self) -> None:
        while True:
            item = self.queue.get()
            if self._abandoned:
                self._close_files()
                return
            if isinstance(item, int):
                break
            if self._error is not None:
                continue  # after a write error, drain the queue so that `give` never waits
            try:
                self._take(item)
            except Exception as error:  # no exception leaves the writer thread (5.4)
                self._fail(error)
        if self._error is None:
            try:
                self._finish(item)
            except Exception as error:
                self._fail(error)

    def _take(self, item) -> None:
        if item is None:  # a dead camera: a placeholder with no times and no source frame number (7.3)
            entry = (None, None, None, True, None)
        else:
            start = self.spec.take_start_host_ns
            damaged = bool(item.flags & ERROR_MASK)
            sample = None if item.sample_ns == NO_SAMPLE_NS else item.sample_ns - start
            entry = (item.source_frame_number, item.arrival_ns - start, sample, damaged,
                     None if damaged else item.payload)
        if self._placeholder is not None:
            self._write(entry)
            return
        self._held.append(entry)
        if entry[4] is not None:
            try:
                self._layout = parse_sof(entry[4])
                self._placeholder = build_placeholder(self._layout)
            except ValueError:
                self._layout = None
        if self._placeholder is None and len(self._held) >= self.spec.queue_size:
            self._fallback()
        if self._placeholder is not None:
            held, self._held = self._held, []
            for entry in held:
                self._write(entry)

    def _fallback(self) -> None:
        self._layout = JpegLayout(self.spec.width, self.spec.height, FALLBACK_FACTORS)
        self._placeholder = build_placeholder(self._layout)
        logger.warning("camera %s: no good frame in the first %d rows; the placeholder is 4:2:2 at %dx%d",
                       self.spec.camera_id, len(self._held), self.spec.width, self.spec.height)

    def _write(self, entry) -> None:
        """Mux block k, then write row k - 1: its block is now in the file (6.3)."""
        sfn, arrival, sample, missing, payload = entry
        if payload is not None:
            try:
                layout = parse_sof(payload)
            except ValueError:
                layout = None
            if layout is None:  # no decoder can read it: a damaged frame (7.2)
                missing, payload = True, None
                if not self._sof_warned:
                    self._sof_warned = True
                    logger.warning("camera %s: row %d has no readable SOF; it is stored as a placeholder",
                                   self.spec.camera_id, self._k)
            elif layout != self._layout and not self._layout_warned:
                # A setting change is refused during a take [D36], so this is a defect.
                self._layout_warned = True
                logger.warning("camera %s: row %d has another JPEG layout than the placeholder",
                               self.spec.camera_id, self._k)
        block = self._placeholder if missing else payload
        self._mkv.mux(block, self._k)
        self._blocks += 1
        if self._pending is not None:
            self._write_row(self._mkv.tell())
        flags = sidecar.row_flags(self._previous_sfn, sfn, missing)
        self._previous_sfn = sfn
        self._pending = (sidecar.Row(self._k, sfn, arrival, sample, flags, None, len(block)), block)
        self._k += 1

    def _write_row(self, block_end: int) -> None:
        row, block = self._pending
        self._pending = None
        self._write_line(sidecar.row_line(row._replace(byte_offset=block_end - len(block))))
        self._rows += 1
        self._gaps += bool(row.flags & sidecar.GAP)
        if row.flags & sidecar.MISSING:
            self._missing += 1
        else:
            self._last_real = row.frame
        now = self._clock()
        if now - self._last_fsync_ns >= FSYNC_PERIOD_NS:
            self._fsync_both()
            self._last_fsync_ns = now

    def _fsync_both(self) -> None:
        self._mkv.fsync()
        self._progress()
        os.fsync(self._csv.fileno())
        self._progress()

    def _write_line(self, line: bytes) -> None:
        if self._csv.write(line) != len(line):
            raise OSError(f"short write of the timing sidecar of camera {self.spec.camera_id}")
        self._progress()

    def _finish(self, frame_count: int) -> None:
        if self._placeholder is None and (self._held or self._k < frame_count):
            self._fallback()
            held, self._held = self._held, []
            for entry in held:
                self._write(entry)
        while self._k < frame_count:
            self._write((None, None, None, True, None))
        last_cluster = self._mkv.tell()
        self._mkv.close_container()
        if self._pending is not None:
            # The muxer wrote the last block at the close: find it after the last position before the close.
            block = self._pending[1]
            with open(self.spec.mkv_path, "rb") as handle:
                handle.seek(last_cluster)
                window = handle.read(len(block) + 64)
            at = window.find(block)
            if at < 0:
                raise OSError(f"camera {self.spec.camera_id}: the last block is not in the camera file after the close")
            self._write_row(last_cluster + at + len(block))
        self._write_line(sidecar.end_line(self._rows, self._gaps, self._missing))
        self._fsync_both()
        self._mkv.raw.close()
        self._csv.close()
        self._closed = True

    def _fail(self, error: Exception) -> None:
        logger.error("camera %s: the writer stopped after a write error at row %d: %r",
                     self.spec.camera_id, self._k, error)
        self._error = str(error) or type(error).__name__
        self._close_files()

    def _close_files(self) -> None:
        for close in [self._mkv.close] + ([self._csv.close] if self._csv is not None else []):
            try:
                close()
            except OSError as error:
                logger.error("camera %s: a file close failed: %r", self.spec.camera_id, error)
        self._closed = True
