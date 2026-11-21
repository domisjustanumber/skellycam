"""The reader of the record of checked models and of the shipped evidence file (specs/unix-capture.md 4.2
item 8, 4.9; specs/certify.md 2.5, 11.2, 11.3). Pure file I/O. It never writes a file: certify owns the
writer of the record.

- The record: `camera_checks.json` in the skellycam base folder, `{"format": 1, "rows": [...]}`.
- The evidence file: `skellycam/core/camera/camera_evidence.json`, shipped in the package.

A missing file, a file that cannot be read and a file that does not parse count as no rows; the reader
logs that one time for each file, and never raises for the file.
"""

import json
import logging
import platform
import struct
from pathlib import Path

logger = logging.getLogger(__name__)

CHECKS_FILE = "camera_checks.json"
EVIDENCE_PATH = Path(__file__).resolve().parents[1] / "camera_evidence.json"
_logged: set[str] = set()


def _read(path: Path, list_key: str, check) -> list:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not check(data) or not isinstance(data.get(list_key), list):
            raise ValueError("not the form of certify.md 2.5 or 11.2")
        return [row for row in data[list_key] if isinstance(row, dict)]
    except (OSError, ValueError) as error:  # json.JSONDecodeError is a ValueError
        if str(path) not in _logged:
            _logged.add(str(path))
            logger.info(f"{path}: no rows ({type(error).__name__}: {error})")
        return []


def read_rows(path: Path | None = None) -> list[dict]:
    """The rows of the record of checked models, in file order (a later row of a key replaces an earlier one)."""
    if path is None:
        from skellycam.system.default_paths import get_default_skellycam_base_folder_path
        path = Path(get_default_skellycam_base_folder_path()) / CHECKS_FILE
    return _read(path, "rows", lambda data: data.get("format") == 1)


def read_evidence(path: Path = EVIDENCE_PATH) -> list[dict]:
    """The `cameras` rows of the shipped evidence file."""
    return _read(path, "cameras", lambda data: data.get("schema") == 1)


def _newest(rows: list[dict], device: str, backend: str, os_key: str, abi: str, level: str | None = None) -> dict | None:
    found = None
    for row in rows:
        if ((row.get("device"), row.get("backend"), row.get("os_key"), row.get("abi")) == (device, backend, os_key, abi)
                and (level is None or row.get("level") == level)):
            found = row
    return found


def checked(rows: list[dict], device: str, backend: str, os_key: str, abi: str) -> bool:
    """A `quick` or `full` row of the model on this backend, OS key and ABI (certify.md 2.5)."""
    return _newest(rows, device, backend, os_key, abi) is not None


def local_pass(rows: list[dict], device: str, backend: str, os_key: str, abi: str) -> bool:
    """The local pass of certify.md 11.3: the newest row of the key is `full`, and each turn-on check passed."""
    row = _newest(rows, device, backend, os_key, abi)
    gate = row.get("gate") if row is not None and row.get("level") == "full" else None
    return isinstance(gate, dict) and bool(gate) and all(value == "pass" for value in gate.values())


def control_routes(rows: list[dict], device: str, backend: str, os_key: str, abi: str) -> dict:
    """The result of each route of exposure, gain and focus of the newest `full` row of the key (certify.md 2.5)."""
    row = _newest(rows, device, backend, os_key, abi, level="full")
    return dict(row.get("controls") or {}) if row is not None else {}


def evidence_state(cameras: list[dict], device: str, backend: str, os_key: str, abi: str) -> str:
    """`verified`, `known-bad` or `unknown` (a key with no row) (certify.md 11.2)."""
    row = _newest(cameras, device, backend, os_key, abi)
    return row["state"] if row is not None and row.get("state") in ("verified", "known-bad") else "unknown"


def current_os_key() -> str:
    """certify.md 11.2: Windows the release and the feature version (`11 26H2`); macOS the major version;
    Linux the kernel major and minor version."""
    system = platform.system()
    if system == "Windows":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                feature = winreg.QueryValueEx(key, "DisplayVersion")[0]
        except OSError:
            feature = "unknown"
        return f"{platform.release()} {feature}"
    if system == "Darwin":
        return platform.mac_ver()[0].split(".")[0]
    return ".".join(platform.release().split(".")[:2])


def current_abi() -> str:
    """certify.md 11.2: `lp64` for a 64-bit process, `ilp32` for a 32-bit one."""
    return "lp64" if struct.calcsize("P") == 8 else "ilp32"


def mark_devices(devices: list, *, checks_path: Path | None = None, evidence_path: Path = EVIDENCE_PATH,
                 os_key: str | None = None, abi: str | None = None) -> list:
    """Set `evidence` and `checked` of each detected camera with a backend and USB ids (unix-capture.md 4.2
    item 8). Returns the same list."""
    rows, cameras = read_rows(checks_path), read_evidence(evidence_path)
    os_key, abi = os_key or current_os_key(), abi or current_abi()
    for device in devices:
        if device.backend is None or device.vendor_id is None or device.product_id is None:
            continue
        key = (f"{device.vendor_id:04x}:{device.product_id:04x}", device.backend, os_key, abi)
        device.evidence, device.checked = evidence_state(cameras, *key), checked(rows, *key)
    return devices
