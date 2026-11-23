"""The restore record on disk (specs/unix-capture.md 4.7.1; a decision of the user of 2026-11-23, Q608) [ADR-HQE5].

One file for each camera, `<key>.json` in a folder that the caller gives. The key is an HMAC-SHA-256 of the stable
identity input of the camera with the salt of the folder (`.salt`), so the file holds no path, no link, no serial
number, no camera name and no user name, and its name differs on each machine. The main process makes the salt,
computes each key (`identity`) and reads the files at a group creation (`read_entries`); it removes each entry that
it drops. The camera process writes its file at each write of its record (`write_entry`) and removes it when the
record is empty. A fault of the disk never fails an open or a set: it is logged one time for each file and kind of
fault in each process.
"""

import datetime
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

FOLDER_NAME = "camera_restore"
SALT_NAME = ".salt"
VERSION = 1
LINUX_DEVICE = re.compile(r"^/dev/video\d+$")
MACOS_UNIQUE_ID = re.compile(r"0x[0-9a-f]{16}", re.IGNORECASE)
TEMPORARY = re.compile(r"^\.(?P<key>[0-9a-f]{64})\.(?P<pid>\d+)\.tmp$")
_logged: set[tuple[str, str]] = set()


def default_folder() -> Path:
    """The folder of the server of the app: `camera_restore` in the data folder of the app (never a recording folder)."""
    from skellycam.system.default_paths import get_default_skellycam_base_folder_path
    return Path(get_default_skellycam_base_folder_path()) / FOLDER_NAME


def _log_once(path: Path, kind: str, text: str) -> None:
    if (str(path), kind) not in _logged:
        _logged.add((str(path), kind))
        logger.warning(text)


def linux_port_input(device_path: str, sys_root: Path = Path("/sys")) -> str | None:
    """`v4l2:port:<name>` of a `/dev/video<n>` camera: the name of its USB interface folder in sysfs (bus, port chain,
    interface; A-2), or None when sysfs has no such folder."""
    device = sys_root / "class" / "video4linux" / Path(device_path).name / "device"
    try:
        name = device.resolve(strict=True).name
    except OSError:
        return None
    return f"v4l2:port:{name}" if re.fullmatch(r"\d+-[\d.]+:\d+\.\d+", name) else None


def identity_input(device, sys_root: Path = Path("/sys")) -> str | None:
    """The stable identity input of a detected camera (4.7.1), or None: the Media Foundation link, the AVFoundation
    unique ID, or the Linux USB interface. Never `/dev/video<n>` alone, the index or the USB IDs with the index."""
    path = getattr(device, "path", None)
    if not path:
        return None
    if path.startswith(r"\\?" + "\\"):
        return path.lower()
    if LINUX_DEVICE.match(path):
        return linux_port_input(path, sys_root)
    if MACOS_UNIQUE_ID.fullmatch(path):
        return path.lower()
    return None


def _salt(folder: Path) -> bytes | None:
    """The salt of the folder, or None when it is missing or cannot be read."""
    try:
        salt = bytes.fromhex((folder / SALT_NAME).read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None
    return salt if len(salt) == 32 else None


def _new_salt(folder: Path) -> bytes | None:
    """A new salt. Each entry file goes: no key of the old salt can match it now."""
    salt = secrets.token_bytes(32)
    path = folder / SALT_NAME
    temporary = folder / f".salt.{os.getpid()}.tmp"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.json"):
            old.unlink(missing_ok=True)
        temporary.write_text(salt.hex(), encoding="ascii")
        os.replace(temporary, path)
    except OSError as error:
        _log_once(path, "salt", f"The salt of the restore files could not be written: {error}; no restore file is used")
        return None
    return salt


def salt_of(folder) -> bytes | None:
    """The salt of `folder`; a missing or damaged salt gives a new one (and no old entry is used)."""
    if folder is None:
        return None
    folder = Path(folder)
    return _salt(folder) or _new_salt(folder)


def identity(device, folder=None, salt: bytes | None = None, sys_root: Path = Path("/sys")) -> dict | None:
    """The key and the USB IDs of a detected camera, as the camera process writes them; None with no stable input or
    no salt. The main process calls it; the camera process never reads the salt."""
    raw = identity_input(device, sys_root) if device is not None else None
    if raw is None:
        return None
    salt = salt if salt is not None else salt_of(folder)
    if salt is None:
        return None
    key = hmac.new(salt, raw.encode(), hashlib.sha256).hexdigest()
    return dict(key=key, vendor_id=device.vendor_id, product_id=device.product_id)


def entry_path(folder, key: str) -> Path:
    return Path(folder) / f"{key}.json"


def remove_entry(folder, key: str) -> None:
    path = entry_path(folder, key)
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        _log_once(path, "remove", f"The restore file {path.name} could not be removed: {error}")


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
        _log_once(path, "write", f"The restore file {path.name} could not be written: {error}; the restore after a "
                                 f"kill of the server is not kept for this camera")
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def valid_record(record) -> bool:
    """4.7.1: `names` from CONTROL_NAMES; `before[name]` = [bool, bool, int or null]; `set[name]` = [bool, int or null]."""
    from skellycam.core.camera.capture.source import CONTROL_NAMES

    if not isinstance(record, dict):
        return False
    names, before, last = record.get("names"), record.get("before"), record.get("set")
    if not isinstance(names, list) or not names or not isinstance(before, dict) or not isinstance(last, dict):
        return False
    for name in names:
        if not isinstance(name, str) or name not in CONTROL_NAMES:
            return False
        b, s = before.get(name), last.get(name)
        if not (isinstance(b, list) and len(b) == 3 and isinstance(b[0], bool) and isinstance(b[1], bool)
                and (b[2] is None or _is_int(b[2]))):
            return False
        if not (isinstance(s, list) and len(s) == 2 and isinstance(s[0], bool) and (s[1] is None or _is_int(s[1]))):
            return False
    return True


def _remove_stale_temporaries(folder: Path) -> None:
    """A kill between the write and the replace leaves `.<key>.<pid>.tmp`: remove it when its process does not run."""
    import psutil

    try:
        paths = [path for path in folder.iterdir() if TEMPORARY.match(path.name)]
    except OSError:
        return
    for path in paths:
        pid = int(TEMPORARY.match(path.name).group("pid"))
        if pid != os.getpid() and not psutil.pid_exists(pid):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def read_entries(folder, camera_ids, devices: dict, identities: dict | None = None) -> dict:
    """camera_id -> the record of its file, for each camera of `camera_ids` that the detection result `devices` holds.

    `identities`: camera_id -> `identity(...)` (made with the salt of the folder). An entry is used only when its
    camera has the USB IDs of the entry and the record is valid. Each other entry of version 1 is logged and
    removed. A file of a later version is left as it is, and its camera gets no identity here (no write over it). A
    camera that is not detected keeps its file. Never raises."""
    found = {}
    if folder is None:
        return found
    folder = Path(folder)
    _remove_stale_temporaries(folder)
    for camera_id in camera_ids:
        device = devices.get(camera_id)
        ident = (identities or {}).get(camera_id)
        if device is None or ident is None:
            continue
        path = entry_path(folder, ident["key"])
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            data, reason = None, type(error).__name__
        else:
            reason = "not a valid record of version 1"
        if isinstance(data, dict) and _is_int(data.get("version")) and data["version"] > VERSION:
            _log_once(path, "version", f"The restore file of camera {camera_id} has the later version "
                                       f"{data['version']}; it is not used and stays")
            if identities is not None:
                identities[camera_id] = None  # this server writes no file over it
            continue
        if not (isinstance(data, dict) and data.get("version") == VERSION and data.get("key") == ident["key"]
                and valid_record(data.get("record"))):
            _log_once(path, "damaged", f"The restore file of camera {camera_id} is damaged ({reason}); it is dropped")
            remove_entry(folder, ident["key"])
            continue
        if (data.get("vendor_id"), data.get("product_id")) != (device.vendor_id, device.product_id):
            _log_once(path, "model", f"The restore file of camera {camera_id} is dropped: the camera with this key has "
                                     f"other USB IDs")
            remove_entry(folder, ident["key"])
            continue
        found[camera_id] = data["record"]
    return found
