"""Locate and load the openpnp-capture native shared library."""

from __future__ import annotations

import ctypes
import os
import platform
import sys
from functools import lru_cache
from pathlib import Path

from skellycam.core.camera.openpnp_capture.types import OpenPnPCaptureLibraryNotFoundError


def _vendor_subdir() -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        if machine in ("amd64", "x86_64"):
            return "win-x64"
        return None
    if system == "linux":
        if machine in ("x86_64", "amd64"):
            return "linux-x64"
        if machine in ("aarch64", "arm64"):
            return "linux-arm64"
        return None
    if system == "darwin":
        if machine == "arm64":
            return "macos-arm64"
        if machine == "x86_64":
            return "macos-x64"
        return None
    return None


def _candidate_filenames() -> list[str]:
    if sys.platform == "win32":
        return ["openpnp-capture.dll", "openpnp_capture.dll"]
    if sys.platform == "darwin":
        return ["libopenpnp-capture.dylib"]
    return ["libopenpnp-capture.so"]


def _skellycam_package_root() -> Path:
    # skellycam/core/camera/openpnp_capture/_lib_loader.py -> skellycam/
    return Path(__file__).resolve().parents[3]


def _vendor_search_paths() -> list[Path]:
    paths: list[Path] = []
    sub = _vendor_subdir()
    root = _skellycam_package_root()
    if sub:
        paths.append(root / "_vendor" / "openpnp_capture" / sub)
    # PyInstaller one-folder: bundled next to executable
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        if sub:
            paths.append(meipass / "skellycam" / "_vendor" / "openpnp_capture" / sub)
            paths.append(meipass / "_vendor" / "openpnp_capture" / sub)
    return paths


@lru_cache(maxsize=1)
def load_openpnp_capture_library() -> ctypes.CDLL:
    """Load openpnp-capture and return a ctypes CDLL with standard resolution."""
    last_error: Exception | None = None
    for directory in _vendor_search_paths():
        for name in _candidate_filenames():
            candidate = directory / name
            if candidate.is_file():
                try:
                    return ctypes.CDLL(str(candidate))
                except OSError as e:
                    last_error = e
    # Fallback: system loader (PATH / LD_LIBRARY_PATH / DYLD_LIBRARY_PATH)
    for name in _candidate_filenames():
        try:
            return ctypes.CDLL(name)
        except OSError as e:
            last_error = e
    hint = _vendor_subdir() or "your-platform"
    raise OpenPnPCaptureLibraryNotFoundError(
        "Could not load openpnp-capture native library. "
        f"Expected it under skellycam/_vendor/openpnp_capture/{hint}/ "
        f"({' or '.join(_candidate_filenames())}), or on PATH. "
        f"Original error: {last_error!r}"
    )
