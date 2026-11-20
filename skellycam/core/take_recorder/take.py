"""The take level in the main process: start_take, Take.finish (specs/recorder.md, 4.2, 6, 8.1)."""
import datetime
import hashlib
import logging
import math
import sys
import time
import unicodedata
import uuid
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from skellycam.core.take_recorder import folder_files, sidecar
from skellycam.core.take_recorder.completion import complete_pair
from skellycam.core.take_recorder.placeholder import JpegLayout, can_build, parse_sof
from skellycam.core.take_recorder.stop_stats import stop_response_fields

logger = logging.getLogger(__name__)

CLOCKS = {"win32": "windows_qpc", "linux": "linux_monotonic", "darwin": "macos_uptime_raw"}  # SFF-772
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


@dataclass(frozen=True, kw_only=True)
class TakeCamera:
    camera_id: str
    nominal_rate: tuple  # (num, den)
    width: int
    height: int
    rotation_cw_deg: int
    capture_format: str  # "MJPG", "YUYV" or "H264"
    layout: JpegLayout | None  # from the SOF of the camera's last good frame before the take (6.4)
    os_name: str | None
    vendor_id: str | None
    product_id: str | None
    backend: str
    os_index: int | None
    requested: dict
    controls: dict  # {"exposure": (log2 seconds, auto), "gain": (value, auto), "focus": (value, auto)}


@dataclass(frozen=True)
class CameraTakeSpec:
    """What a camera process needs to write its pair. It pickles."""

    camera_id: str
    mkv_path: Path
    csv_path: Path
    header: tuple  # the (key, value) pairs of the header lines of 6.5
    take_start_host_ns: int
    num: int
    den: int
    width: int
    height: int
    layout: JpegLayout | None
    queue_size: int
    stall_limit_s: float


@dataclass(frozen=True)
class TakeSummary:
    stop_response: dict  # the fields of StopRecordingResponse (8.2)
    results: list  # the CameraTakeResult (or None) of each camera
    warnings: list  # the warnings that finish wrote


def _check_name(rec: str) -> None:
    """SFF-715."""
    if not 1 <= len(rec.encode("utf-8")) <= 128:
        raise ValueError(f"the recording name must be 1 to 128 bytes of UTF-8: {rec!r}")
    if any(unicodedata.category(c) == "Cc" or c in './\\:*?"<>|' for c in rec):
        raise ValueError(f"the recording name holds a control character, a '.' or one of / \\ : * ? \" < > |: {rec!r}")
    if rec != rec.strip(" ") or rec.upper() in RESERVED_NAMES:
        raise ValueError(f"the recording name starts or ends with a space, or is a Windows device name: {rec!r}")


def _check_camera(camera: TakeCamera) -> None:
    num, den = camera.nominal_rate
    if not (1 <= num <= 2**20 and 1 <= den <= 2**20):  # SFF-750
        raise ValueError(f"camera {camera.camera_id}: num and den of the nominal rate must be 1 to 2^20")
    if Fraction(num, den) > 1000:  # SFF-736
        raise ValueError(f"camera {camera.camera_id}: a nominal rate above 1000 frames per second")
    if camera.capture_format == "H264":  # SFF-734
        raise ValueError(f"camera {camera.camera_id}: H.264 capture is not recorded")
    if camera.layout is not None and not can_build(camera.layout):
        raise ValueError(f"camera {camera.camera_id}: no placeholder for the JPEG layout {camera.layout.factors}")


def start_take(folder, rec, cameras, *, writer, clock=None, lock_timeout_s=10.0, queue_seconds=3.0,
               stall_limit_s=10.0) -> "Take":
    """Create the take folder, write the capture info and the manifest (`recording`) under the lock.
    A refusal raises ValueError before the first write."""
    folder = Path(folder)
    _check_name(rec)
    for camera in cameras:
        _check_camera(camera)
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):  # SFF-719 [agent 16]
        raise ValueError(f"the take folder is not empty: {folder}")
    (folder / folder_files.MEDIA).mkdir(parents=True, exist_ok=True)
    open(folder / folder_files.LOCK_NAME, "xb").close()
    host_clock, utc_clock = clock or (time.perf_counter_ns, time.time_ns)
    host_ns = host_clock()
    utc_ns = utc_clock()  # at once after the host clock (SFF-774)
    offset_min = int(datetime.datetime.now().astimezone().utcoffset().total_seconds() // 60)
    take = Take(folder, rec, list(cameras), writer=writer, host_ns=host_ns, utc_ns=utc_ns, offset_min=offset_min,
                lock_timeout_s=lock_timeout_s, queue_seconds=queue_seconds, stall_limit_s=stall_limit_s)
    with folder_files.take_lock(folder / folder_files.LOCK_NAME, lock_timeout_s):
        take.write_folder_files("recording", folder_files.summary(take), [])
    return take


class Take:
    def __init__(self, folder, rec, cameras, *, writer, host_ns, utc_ns, offset_min, lock_timeout_s, queue_seconds,
                 stall_limit_s):
        self.folder, self.rec, self.cameras, self.writer = folder, rec, cameras, writer
        self.take_uuid = uuid.uuid4().hex
        self.take_start_host_ns, self.take_start_utc_ns, self.utc_offset_min = host_ns, utc_ns, offset_min
        self.lock_timeout_s, self.queue_seconds, self.stall_limit_s = lock_timeout_s, queue_seconds, stall_limit_s
        # 6.2 [C3]: camera_id + 12 hexadecimal characters of its SHA-256 until step 5d.
        self.keys = [c.camera_id + hashlib.sha256(c.camera_id.encode("utf-8")).hexdigest()[:12] for c in cameras]
        self.labels = [key[:6] for key in self.keys]
        self.info_name = f"{rec}_info.json"

    def video_path(self, label) -> str:
        return f"{folder_files.MEDIA}/{self.rec}.{label}.mkv"

    def timing_path(self, label) -> str:
        return f"{folder_files.MEDIA}/{self.rec}.{label}.csv"

    def _position(self, camera_id) -> int:
        return next(i for i, c in enumerate(self.cameras) if c.camera_id == camera_id)

    def camera_spec(self, camera_id) -> CameraTakeSpec:
        position = self._position(camera_id)
        camera, key, label = self.cameras[position], self.keys[position], self.labels[position]
        num, den = camera.nominal_rate
        header = (
            ("skellyfileformat", "video_timing"), ("format_version", folder_files.FORMAT_VERSION),
            ("format_prerelease", folder_files.FORMAT_PRERELEASE), ("writer", self.writer),
            ("take_uuid", self.take_uuid), ("take_start_host_ns", self.take_start_host_ns),
            ("take_start_utc_ns", self.take_start_utc_ns), ("utc_offset_min", self.utc_offset_min),
            ("clock", CLOCKS[sys.platform]), ("clock_hz", ""), ("group_size", len(self.cameras)), ("audio_count", 0),
            ("group_position", position), ("camera_key", key), ("camera_label", label),
            ("nominal_rate", f"{num}/{den}"), ("display_rotation", camera.rotation_cw_deg),
        )
        return CameraTakeSpec(
            camera_id=camera_id, mkv_path=self.folder / self.video_path(label),
            csv_path=self.folder / self.timing_path(label), header=header, take_start_host_ns=self.take_start_host_ns,
            num=num, den=den, width=camera.width, height=camera.height, layout=camera.layout,
            queue_size=math.ceil(Fraction(str(self.queue_seconds)) * num / den), stall_limit_s=self.stall_limit_s)

    def write_folder_files(self, state, summary, warnings) -> None:
        """The capture info, then the manifest; the caller holds the lock (6.8)."""
        info = folder_files.json_bytes(folder_files.capture_info(self))
        folder_files.write_whole(self.folder / self.info_name, info)
        manifest_path = self.folder / folder_files.MANIFEST_NAME
        existing = folder_files.read_json(manifest_path)
        manifest = folder_files.manifest(self, existing, state=state, info_sha=hashlib.sha256(info).hexdigest(),
                                         warnings=warnings, summary_value=summary)
        folder_files.write_whole(manifest_path, folder_files.json_bytes(manifest))

    def finish(self, results, *, frame_count, ended_by_error=None, dead_cameras=None) -> TakeSummary:
        """The end of the take (8.1 step 5). The caller passes a result, or None, for each camera only
        after the camera's writer ended or its process was joined [review B2]."""
        dead_cameras = dead_cameras or {}
        mkvs = [self.folder / self.video_path(label) for label in self.labels]
        paths = [self.folder / self.timing_path(label) for label in self.labels]
        # 7.4: complete each pair whose sidecar has no `# end` line; then read each sidecar (8.1 step 5).
        shorts = [complete_pair(mkv, csv, frame_count, self.writer) for mkv, csv in zip(mkvs, paths)]
        warnings, sidecars = [], []
        for camera, key, mkv, csv, blocks in zip(self.cameras, self.keys, mkvs, paths, shorts):
            rows = sidecar.read_strict(csv).rows
            if len(rows) != frame_count:  # 7.6: a defect
                logger.error("camera %s: %d rows, expected %d", camera.camera_id, len(rows), frame_count)
                warnings.append(self._warning("take_error", key, f"camera {camera.camera_id}: {len(rows)} rows, "
                                                                 f"expected {frame_count}"))
            sidecars.append((rows, self._stored_px(camera, mkv, rows)))
            gaps, _ = sidecar.counts(rows)
            if gaps:
                warnings.append(self._warning("camera_gap", key, None))
            if camera.camera_id in dead_cameras:
                last = next((r.frame for r in reversed(rows) if not r.flags & sidecar.MISSING), "none")
                warnings.append(self._warning("camera_dead", key,
                                              f"last_frame={last} reason={dead_cameras[camera.camera_id]}"))
            if blocks is not None:
                warnings.append(self._warning("camera_file_short", key, f"blocks={blocks} rows={frame_count}"))
        if ended_by_error is not None:
            # camera_key: the camera whose result holds the error text, or null (F-5).
            failed = [key for key, r in zip(self.keys, results) if r is not None and r.error == ended_by_error]
            warnings.append(self._warning("take_error", failed[0] if failed else None, ended_by_error))
        try:
            with folder_files.take_lock(self.folder / folder_files.LOCK_NAME, self.lock_timeout_s):
                self.write_folder_files("finished", folder_files.summary(self, sidecars), warnings)
        except TimeoutError as error:
            logger.error("the manifest stays `recording`: %s", error)  # step 5c repairs the take (6.8)
        stop = stop_response_fields(paths, recording_name=self.rec, recording_path=self.folder,
                                    frame_count=frame_count)
        return TakeSummary(stop_response=stop, results=list(results), warnings=warnings)

    @staticmethod
    def _warning(code, camera_key, detail) -> dict:
        return {"code": code, "source": "skellycam", "camera_key": camera_key, "detail": detail}

    @staticmethod
    def _stored_px(camera, mkv, rows):
        """The size of the first block that is not a placeholder; else of the first placeholder; else
        of the mode (SFF-728, agent 26)."""
        stored = [r for r in rows if r.byte_offset is not None]
        row = next((r for r in stored if not r.flags & sidecar.MISSING), stored[0] if stored else None)
        if row is None:
            return f"{camera.width}x{camera.height}"
        with open(mkv, "rb") as handle:
            handle.seek(row.byte_offset)
            payload = handle.read(row.byte_size)
        try:
            layout = parse_sof(payload)
        except ValueError:
            return f"{camera.width}x{camera.height}"
        return f"{layout.width}x{layout.height}"
