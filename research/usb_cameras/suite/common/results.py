"""Standard result JSON for every suite test (stdlib only, any OS).

Every test writes one JSON object with these fields (plan section 6):

    test, platform, hostname, utc_started, utc_finished, elapsed_s, command, environment, cameras,
    measurements, verdicts, errors

Typical use inside a test module::

    from common import results
    res = results.new_result("W-CYC", command=sys.argv, cameras=cams)
    ...
    results.finish_result(res, measurements={...}, verdicts={"reliability": rating.rate_reliability(...)},
                          errors=[...])
    results.write_json(out_dir / "W-CYC.json", res)

Default locations (plan section 6, task rules):
    results  <research/usb_cameras>/results/<windows|linux|macos>/<hostname>/suite_<UTC stamp>/
    raw data Windows: %USERPROFILE%/Documents/skellycam-raw/<same path relative to research/usb_cameras>
             POSIX:   ~/skellycam-raw/<same relative path>
             ($SKELLYCAM_RAW_ROOT overrides the raw root.) Big frame dumps go there, never into the repo.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import math
import os
import platform as _platform
import socket
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

#: research/usb_cameras (this file is research/usb_cameras/suite/common/results.py)
RESEARCH_ROOT = Path(__file__).resolve().parents[2]

#: packages whose versions env_info() records when they are importable/installed
DEFAULT_PACKAGES = ("av", "numpy", "pillow", "simplejpeg", "PyTurboJPEG", "opencv-python", "opencv-python-headless",
                    "opencv-contrib-python", "comtypes", "pywin32", "pyobjc-core", "pyobjc-framework-AVFoundation",
                    "psutil", "pytest")


def platform_name() -> str:
    """'windows', 'linux' or 'macos' (else sys.platform). Used for the results/<platform>/ folder."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    return sys.platform


def utc_now_iso() -> str:
    """Current UTC time as ISO 8601 with offset, e.g. '2026-11-06T15:23:37.176103+00:00'."""
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def utc_stamp(t: _dt.datetime | None = None) -> str:
    """Compact UTC stamp for folder names, e.g. '20261106T152337Z'."""
    t = t or _dt.datetime.now(_dt.timezone.utc)
    return t.astimezone(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _package_versions(names: Iterable[str]) -> dict[str, str | None]:
    try:
        from importlib import metadata
    except ImportError:  # pragma: no cover - Python < 3.8
        return {}
    out: dict[str, str | None] = {}
    for n in names:
        try:
            out[n] = metadata.version(n)
        except Exception:
            out[n] = None
    return {k: v for k, v in out.items() if v is not None}


def _os_details() -> dict[str, Any]:
    d: dict[str, Any] = {"platform": _platform.platform(), "system": _platform.system(),
                         "release": _platform.release(), "version": _platform.version(),
                         "machine": _platform.machine()}
    if sys.platform == "win32":
        try:
            wv = sys.getwindowsversion()  # type: ignore[attr-defined]
            d["windows_build"] = wv.build
            d["windows_version"] = f"{wv.major}.{wv.minor}.{wv.build}"
        except Exception:
            pass
        try:
            d["windows_edition"] = _platform.win32_edition()
        except Exception:
            pass
        try:  # UBR (update build revision) and display version, read-only registry query
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
                for name in ("DisplayVersion", "UBR", "ProductName", "CurrentBuild"):
                    try:
                        d["windows_" + name.lower()] = winreg.QueryValueEx(k, name)[0]
                    except OSError:
                        pass
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        d["kernel"] = _platform.release()
        try:
            rel = {}
            for line in Path("/etc/os-release").read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    rel[k] = v.strip().strip('"')
            d["os_release"] = {k: rel.get(k) for k in ("PRETTY_NAME", "ID", "VERSION_ID", "VARIANT_ID") if k in rel}
        except Exception:
            pass
        for env in ("XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", "WAYLAND_DISPLAY", "DISPLAY", "SSH_CONNECTION"):
            if os.environ.get(env):
                d.setdefault("session", {})[env] = os.environ[env] if env != "SSH_CONNECTION" else "set"
    elif sys.platform == "darwin":
        ver, _, mach = _platform.mac_ver()
        d["macos_version"] = ver
        d["macos_machine"] = mach
        d["kernel"] = _platform.release()
    return d


def env_info(packages: Iterable[str] | None = None) -> dict[str, Any]:
    """OS, build / kernel, Python and package versions. Never raises; never touches a camera."""
    return {
        "os": _os_details(),
        "python": _platform.python_version(),
        "python_implementation": _platform.python_implementation(),
        "python_executable": sys.executable,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "packages": _package_versions(packages or DEFAULT_PACKAGES),
    }


def new_result(test: str, platform: str | None = None, command: Any = None,
               cameras: list | None = None) -> dict[str, Any]:
    """Start a result dict with the standard fields. ``command`` may be an argv list or a string."""
    if command is None:
        command = list(sys.argv)
    res = {
        "test": test,
        "platform": platform or platform_name(),
        "hostname": socket.gethostname(),
        "utc_started": utc_now_iso(),
        "utc_finished": None,
        "elapsed_s": None,
        "command": command if isinstance(command, str) else " ".join(str(c) for c in command),
        "argv": None if isinstance(command, str) else [str(c) for c in command],
        "environment": env_info(),
        "cameras": cameras if cameras is not None else [],
        "measurements": {},
        "verdicts": {},
        "errors": [],
    }
    res["_t0"] = time.monotonic()
    return res


def finish_result(res: dict[str, Any], measurements: dict | None = None, verdicts: dict | None = None,
                  errors: list | None = None) -> dict[str, Any]:
    """Merge measurements / verdicts / errors into ``res`` and stamp utc_finished and elapsed_s. Returns res."""
    if measurements:
        res.setdefault("measurements", {}).update(measurements)
    if verdicts:
        res.setdefault("verdicts", {}).update(verdicts)
    if errors:
        res.setdefault("errors", []).extend(errors)
    res["utc_finished"] = utc_now_iso()
    t0 = res.pop("_t0", None)
    if t0 is not None:
        res["elapsed_s"] = round(time.monotonic() - t0, 3)
    return res


def _sanitize(o: Any) -> Any:
    """Make ``o`` strict-JSON serialisable: NaN/inf -> None, Path -> str, set -> sorted list, bytes -> summary,
    dataclasses -> dict, numpy scalars/arrays -> Python values."""
    if o is None or isinstance(o, (bool, int, str)):
        return o
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k): _sanitize(v) for k, v in o.items() if not (isinstance(k, str) and k.startswith("_t0"))}
    if isinstance(o, (list, tuple)):
        return [_sanitize(v) for v in o]
    if isinstance(o, (set, frozenset)):
        return [_sanitize(v) for v in sorted(o, key=str)]
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, (bytes, bytearray, memoryview)):
        b = bytes(o)
        return {"bytes_len": len(b), "head_hex": b[:32].hex()}
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return _sanitize(dataclasses.asdict(o))
    if hasattr(o, "tolist"):  # numpy arrays and scalars
        try:
            return _sanitize(o.tolist())
        except Exception:
            pass
    if hasattr(o, "item"):
        try:
            return _sanitize(o.item())
        except Exception:
            pass
    if hasattr(o, "__dict__") and not callable(o):
        return {k: _sanitize(v) for k, v in vars(o).items() if not k.startswith("_")}
    return str(o)


def to_json_text(obj: Any, indent: int | None = 1) -> str:
    """Serialise with the same sanitising rules as write_json (strict JSON: no NaN)."""
    return json.dumps(_sanitize(obj), indent=indent, ensure_ascii=False, allow_nan=False)


def write_json(path: str | os.PathLike, obj: Any, indent: int | None = 1) -> Path:
    """Write ``obj`` as UTF-8 JSON atomically (temp file + replace), creating parent folders. Returns the path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = to_json_text(obj, indent=indent)
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.write("\n")
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return p


def append_jsonl(path: str | os.PathLike, row: Any) -> None:
    """Append one JSON Lines row (sanitised, compact)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(to_json_text(row, indent=None))
        f.write("\n")


def read_jsonl(path: str | os.PathLike) -> list[dict]:
    """Read a JSON Lines file, skipping blank and unparsable lines (a killed writer can leave a partial last line)."""
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    with p.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def default_results_dir(stamp: str | None = None, hostname: str | None = None,
                        research_root: str | os.PathLike | None = None) -> Path:
    """<research/usb_cameras>/results/<platform>/<hostname>/suite_<stamp>/ (not created)."""
    root = Path(research_root) if research_root else RESEARCH_ROOT
    return root / "results" / platform_name() / (hostname or socket.gethostname()) / f"suite_{stamp or utc_stamp()}"


def raw_root() -> Path:
    """Root for big raw frame data, outside the repo. $SKELLYCAM_RAW_ROOT overrides."""
    env = os.environ.get("SKELLYCAM_RAW_ROOT")
    if env:
        return Path(env)
    if sys.platform == "win32":
        return Path.home() / "Documents" / "skellycam-raw"
    return Path.home() / "skellycam-raw"


def default_raw_dir(out_dir: str | os.PathLike, research_root: str | os.PathLike | None = None) -> Path:
    """Raw-data folder mirroring ``out_dir``: raw_root()/<out_dir relative to research/usb_cameras> (not created).
    If out_dir is outside the research folder, raw_root()/<out_dir name> is used."""
    out = Path(out_dir).resolve()
    root = (Path(research_root) if research_root else RESEARCH_ROOT).resolve()
    try:
        rel = out.relative_to(root)
    except ValueError:
        rel = Path(out.name)
    return raw_root() / rel
