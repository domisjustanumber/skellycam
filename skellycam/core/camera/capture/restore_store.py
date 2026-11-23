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


def _write_private(path: Path, text: str, exclusive: bool = True) -> None:
    """Write `text` to a new file at `path`, mode 0600 on POSIX (the salt and the entries are for this user only)."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        file.write(text.encode("utf-8"))


def _read_salt(folder: Path) -> tuple[str, bytes | None]:
    """("ok", salt), ("missing", None), ("damaged", None) for a file that is not 32 bytes of hex, or ("error", None)
    for a file that exists and cannot be read (a sharing violation, a folder in its place, EIO)."""
    try:
        text = (folder / SALT_NAME).read_text(encoding="ascii")
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "error", None
    except ValueError:  # UnicodeDecodeError: not ASCII
        return "damaged", None
    try:
        salt = bytes.fromhex(text.strip())
    except ValueError:
        return "damaged", None
    return ("ok", salt) if len(salt) == 32 else ("damaged", None)


def _remove_old_entries(folder: Path) -> None:
    """After a new salt: no key of the old salt can match an entry now."""
    for old in folder.glob("*.json"):
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass


def _new_salt(folder: Path, replace: bool) -> bytes | None:
    """A new salt (4.7.1). It is written and put in place first; the old entries go only after that. With no salt
    (`replace` False) the salt is created with no replace: when another server made one first, that salt is read back
    and nothing is removed. A damaged salt (`replace` True) is replaced."""
    salt = secrets.token_bytes(32)
    path = folder / SALT_NAME
    temporary = folder / f".salt.{os.getpid()}.tmp"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _write_private(temporary, salt.hex(), exclusive=False)
        if replace:
            os.replace(temporary, path)
        else:
            try:
                try:
                    os.link(temporary, path)  # atomic, and it fails when the file exists
                except FileExistsError:
                    raise
                except OSError:  # a file system with no hard links: an exclusive create of the salt itself
                    _write_private(path, salt.hex(), exclusive=True)
            except FileExistsError:
                state, other = _read_salt(folder)
                return other if state == "ok" else None
            finally:
                temporary.unlink(missing_ok=True)
    except OSError as error:
        _log_once(path, "salt", f"The salt of the restore files could not be written: {error}; no restore file is used")
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    _remove_old_entries(folder)
    return salt


def salt_of(folder) -> bytes | None:
    """The salt of `folder` (4.7.1). A missing or damaged salt gives a new one (and no old entry is used). A salt that
    exists and cannot be read gives None: no restore file this run, and nothing is removed."""
    if folder is None:
        return None
    folder = Path(folder)
    state, salt = _read_salt(folder)
    if state == "ok":
        return salt
    if state == "error":
        _log_once(folder / SALT_NAME, "salt-read", "The salt of the restore files cannot be read; no restore file is "
                                                   "used this time, and none is removed")
        return None
    return _new_salt(folder, replace=state == "damaged")


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
        _write_private(temporary, json.dumps(data), exclusive=False)
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
