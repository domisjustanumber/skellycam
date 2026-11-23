"""The restore record on disk (specs/unix-capture.md 4.7.1; a decision of the user of 2026-11-23, Q608) [ADR-HQE5].

One file for each camera, `<key>.json` in a folder that the caller gives. The key is the SHA-256 (hex) of the input of
the `camera_id` hash (the Media Foundation link, the path, or the USB IDs with the index): the file holds no path, no
link, no serial number, no camera name and no user name. The camera process writes the file at each write of its
record (`write_entry`) and removes it when the record becomes empty. The main process reads the files at a group
creation (`read_entries`) and removes each entry that it drops. A fault of the disk never fails an open or a set: it
is logged one time for each file and process.
"""

import datetime
import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

FOLDER_NAME = "camera_restore"
VERSION = 1
STABLE_ID_SOURCES = ("serial", "id-path", "unique-id", "mf-link")
_logged: set[str] = set()


def default_folder() -> Path:
    """The folder of the server of the app: `camera_restore` in the data folder of the app (never a recording folder)."""
    from skellycam.system.default_paths import get_default_skellycam_base_folder_path
    return Path(get_default_skellycam_base_folder_path()) / FOLDER_NAME


def identity(device) -> dict | None:
    """The key and the USB IDs of a detected camera, as the camera process writes them; None with no stable input."""
    raw = device.identity_input() if device is not None else None
    if raw is None:
        return None
    return dict(key=hashlib.sha256(raw.encode()).hexdigest(), vendor_id=device.vendor_id, product_id=device.product_id)


def stable(device) -> bool:
    """The `camera_id` of `device` comes from an input that a restart does not change for another camera (4.7.1)."""
    return bool(device.has_serial) or device.id_source in STABLE_ID_SOURCES or bool(
        device.path and device.path.startswith(r"\\?" + "\\"))


def entry_path(folder, key: str) -> Path:
    return Path(folder) / f"{key}.json"


def _log_once(path: Path, text: str) -> None:
    if str(path) not in _logged:
        _logged.add(str(path))
        logger.warning(text)


def remove_entry(folder, key: str) -> None:
    path = entry_path(folder, key)
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        _log_once(path, f"The restore file {path.name} could not be removed: {error}")


def write_entry(folder, ident: dict | None, record: dict) -> None:
    """Write the record of one camera (temporary file, then `os.replace`), or remove the file of an empty record."""
    if folder is None or not ident:
        return
    if not record or not record.get("names"):
        remove_entry(folder, ident["key"])
        return
    path = entry_path(folder, ident["key"])
    data = {"version": VERSION, "key": ident["key"], "vendor_id": ident.get("vendor_id"),
            "product_id": ident.get("product_id"),
            "written_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "record": record}
    temporary = path.with_name(f".{path.stem}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(data), encoding="utf-8")
        os.replace(temporary, path)
    except OSError as error:
        _log_once(path, f"The restore file {path.name} could not be written: {error}; the restore after a kill of the "
                        f"server is not kept for this camera")
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _valid_record(record) -> bool:
    if not isinstance(record, dict) or not isinstance(record.get("names"), list) or not record["names"]:
        return False
    before, last = record.get("before"), record.get("set")
    return isinstance(before, dict) and isinstance(last, dict) and all(
        isinstance(before.get(name), list) and len(before[name]) == 3
        and isinstance(last.get(name), list) and len(last[name]) == 2 for name in record["names"])


def read_entries(folder, camera_ids, devices: dict) -> dict:
    """camera_id -> the record of its file, for each camera of `camera_ids` that the detection result `devices` holds.

    An entry is used only when its camera has the USB IDs of the entry, and, when two or more detected cameras have
    these USB IDs, a stable identity (4.7.1). Each other entry, and a damaged file, is dropped: it is logged and
    removed. A camera that is not detected keeps its file. Never raises."""
    found = {}
    if folder is None:
        return found
    for camera_id in camera_ids:
        device = devices.get(camera_id)
        ident = identity(device)
        if ident is None:
            continue
        path = entry_path(folder, ident["key"])
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            valid = (isinstance(data, dict) and data.get("version") == VERSION and data.get("key") == ident["key"]
                     and _valid_record(data.get("record")))
        except (OSError, ValueError) as error:
            data, valid = None, False
            reason = f"{type(error).__name__}"
        else:
            reason = "not a record of version 1"
        if not valid:
            _log_once(path, f"The restore file of camera {camera_id} is damaged ({reason}); it is dropped")
            remove_entry(folder, ident["key"])
            continue
        model = (data.get("vendor_id"), data.get("product_id"))
        same_model = [other for other in devices.values() if (other.vendor_id, other.product_id) == model]
        if model != (device.vendor_id, device.product_id):
            reason = "the camera with this ID has other USB IDs"
        elif len(same_model) > 1 and not stable(device):
            reason = "two cameras of this model cannot be told apart"
        else:
            found[camera_id] = data["record"]
            continue
        _log_once(path, f"The restore file of camera {camera_id} is dropped: {reason}")
        remove_entry(folder, ident["key"])
    return found
