"""The manifest, the capture info, the whole-file write and the lock (specs/recorder.md, 6.6 to 6.8)."""
import contextlib
import datetime
import errno
import json
import os
import sys
import time

from skellycam.core.take_recorder.sidecar import FILLED, counts
from skellycam.core.take_recorder.stop_stats import duration_s

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

FORMAT_VERSION, FORMAT_PRERELEASE = "2.0", 1  # SFF-707, SFF-710
LOCK_NAME, MANIFEST_NAME, MEDIA = ".processing.lock", "recording_manifest.json", "synchronized_videos"
LOCK_RETRY_S = 0.05
# The errors of a lock that another program holds: msvcrt gives EACCES or EDEADLOCK (= EDEADLK),
# flock gives EWOULDBLOCK (= EAGAIN). Each other error is reported at once.
LOCK_BUSY = {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
CONTROLS = (("exposure", "exposure_us"), ("gain", "gain"), ("focus", "focus"))  # TakeCamera name, SFF-802 name
REQUESTED = ("width", "height", "framerate", "capture_format", "exposure_mode")


def _numbers(value):
    """SFF-702: a number with an integer value is written with no fraction (30, not 30.0)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_numbers(v) for v in value]
    return value


def json_bytes(value) -> bytes:
    return (json.dumps(_numbers(value), indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def read_json(path):
    """The JSON object of `path`, or None when the file does not exist."""
    try:
        with open(path, "rb") as handle:
            return json.loads(handle.read().decode("utf-8"))
    except FileNotFoundError:
        return None


def write_whole(path, data: bytes, timeout_s: float) -> None:
    """SFF-786: write `<name>.tmp` in the same folder, force it to disk, then replace the file.

    On Windows the replace fails while a reader holds the file open. It is tried again every 50 ms
    for `timeout_s`; then the `.tmp` file is removed and TimeoutError is raised."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as handle:  # "wb" also reuses a `.tmp` file that a kill left
        handle.write(data)
        os.fsync(handle.fileno())
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                with contextlib.suppress(OSError):
                    os.remove(tmp)
                raise TimeoutError(f"another program holds {path} open for more than {timeout_s} s") from None
            time.sleep(LOCK_RETRY_S)


@contextlib.contextmanager
def take_lock(path, timeout_s):
    """The OS file lock on `.processing.lock` (SFF-789, F-7). Tries again every 50 ms with a blocking
    sleep; raises TimeoutError after `timeout_s`."""
    with open(path, "r+b") as handle:
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                if sys.platform == "win32":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in LOCK_BUSY:
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"another program holds {path} for more than {timeout_s} s") from None
                time.sleep(LOCK_RETRY_S)
        try:
            yield
        finally:
            if sys.platform == "win32":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def nominal_fps(num, den) -> float:
    """SFF-728: ⌊(2000 × num + den) / (2 × den)⌋ thousandths."""
    return ((2000 * num + den) // (2 * den)) / 1000


def exposure_us(camera):
    value = camera.controls.get("exposure", (None, None))[0]
    return None if value is None else 2.0 ** value * 10**6  # log2 seconds to µs [D35, agent 29]


def capture_info(take) -> dict:
    """Section 13 of the format, with the values of 6.7. The 5d fields are null."""
    configs = {}
    for camera, key, label in zip(take.cameras, take.keys, take.labels):
        requested = dict(camera.requested)
        if requested.get("framerate") in (-1, 0):
            requested["framerate"] = "camera_default"  # [D16]
        controls = {}
        for name, sff_name in CONTROLS:
            if name in camera.controls:
                value, auto = camera.controls[name]
                controls[sff_name] = {"value": exposure_us(camera) if name == "exposure" else value, "auto": auto}
        configs[key] = {
            "camera_label": label, "user_name": None, "key_origin": "provisional",
            "device": {"model": None, "os_name": camera.os_name, "vendor_id": camera.vendor_id,
                       "product_id": camera.product_id, "serial": None, "port_path": None, "os_device_id": None,
                       "backend": camera.backend, "os_index": camera.os_index},
            "requested": {k: requested.get(k) for k in REQUESTED},
            "controls": controls, "exposure_step": None,
        }
    return {"skellyfileformat": "capture_info", "format_version": FORMAT_VERSION,
            "format_prerelease": FORMAT_PRERELEASE, "writer": take.writer, "take_uuid": take.take_uuid,
            "camera_configs": configs, "audio": None}


def _privacy(take) -> list:
    """SFF-881: the private fields of the files that skellycam writes."""
    fields = [{"file": take.info_name, "field": f"/camera_configs/{key}/device/os_name", "kind": "device_name"}
              for camera, key in zip(take.cameras, take.keys) if camera.os_name is not None]
    fields += [{"file": take.timing_path(label), "field": "utc_offset_min", "kind": "time_zone"}
               for label in take.labels]
    fields.append({"file": MANIFEST_NAME, "field": "/recording_name", "kind": "user_entered_name"})
    return fields


def summary(take, sidecars=None) -> dict:
    """SFF-728 with `missing` (F-1). `sidecars` is None in the state `recording`; at the end it holds,
    for each camera, (rows, stored_px)."""
    cameras = []
    for position, (camera, label) in enumerate(zip(take.cameras, take.labels)):
        item = {"camera_label": label, "user_name": None, "model": None, "stored_px": None,
                "display_rotation": camera.rotation_cw_deg, "nominal_fps": nominal_fps(*camera.nominal_rate),
                "gaps": None, "filled": None, "missing": None, "exposure_us": exposure_us(camera)}
        if sidecars is not None:
            rows, stored_px = sidecars[position]
            gaps, missing = counts(rows)
            filled = sum(1 for r in rows if r.flags & FILLED)
            item.update(stored_px=stored_px, gaps=gaps, filled=filled, missing=missing)
        cameras.append(item)
    start = datetime.datetime.fromtimestamp(take.take_start_utc_ns // 10**9, datetime.UTC)
    return {"take_start_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_s": None if sidecars is None else duration_s([rows for rows, _ in sidecars]),
            "cameras": cameras, "audio": None, "calibration": None, "processing_runs": [], "warnings": []}


def manifest(take, existing, *, state, info_sha, warnings, summary_value) -> dict:
    """The manifest of SFF-723. It keeps each member and each item of `existing` that another
    program owns (SFF-724)."""
    existing = existing or {}
    files = [f for f in existing.get("files", []) if f.get("owner") != "skellycam"]
    files.append({"path": take.info_name, "role": "capture_info", "owner": "skellycam", "sha256": info_sha})
    files.sort(key=lambda f: f["path"].encode("utf-8"))
    warnings = [w for w in existing.get("warnings", []) if w.get("source") != "skellycam"] + warnings
    ours = _privacy(take)
    mine = {(f["file"], f["field"]) for f in ours}
    fields = [f for f in existing.get("privacy", {}).get("fields", []) if (f["file"], f["field"]) not in mine] + ours
    fields.sort(key=lambda f: (f["file"].encode("utf-8"), f["field"].encode("utf-8")))
    summary_value["warnings"] = sorted({w["code"] for w in warnings})
    old_summary = existing.get("summary") or {}  # freemocap fills these two members (SFF-724)
    summary_value["calibration"] = old_summary.get("calibration")
    summary_value["processing_runs"] = old_summary.get("processing_runs") or []
    calibration = {c.get("camera_key"): c.get("calibration_camera") for c in existing.get("cameras", [])}
    value = {
        "skellyfileformat": "recording_manifest", "format_version": FORMAT_VERSION,
        "format_prerelease": FORMAT_PRERELEASE, "writer": take.writer, "take_uuid": take.take_uuid,
        "recording_name": take.rec, "purpose": "motion_capture", "state": state,
        "cameras": [{"camera_key": key, "camera_label": label, "group_position": position,
                     "video": take.video_path(label), "timing": take.timing_path(label),
                     "calibration_camera": calibration.get(key)}
                    for position, (key, label) in enumerate(zip(take.keys, take.labels))],
        "audio": None, "calibration": existing.get("calibration"), "files": files, "warnings": warnings,
        "privacy": {"fields": fields, "media_shows_people": True}, "summary": summary_value,
    }
    return {**existing, **value}
