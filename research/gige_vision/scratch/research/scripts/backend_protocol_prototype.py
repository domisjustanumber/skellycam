"""Prototype: a CameraBackend Protocol + fake GigE backend driving a skellycam frame recarray.

Checks (a) beartype's handling of typing.Protocol annotations (skellycam runs beartype_this_package),
(b) that a backend-agnostic grab/retrieve split can fill the existing frame dtype, including a
camera-side (PTP) timestamp that has no slot in the current dtype.
Usage: python backend_protocol_prototype.py <path-to-skellycam-repo>
"""
import sys
import time
from typing import Protocol, runtime_checkable

repo = sys.argv[1]
sys.path.insert(0, repo)

import cv2
import numpy as np
from beartype import beartype
from beartype.roar import BeartypeException

from skellycam.core.camera.config.camera_config import CameraConfig
from skellycam.core.camera.config.image_resolution import ImageResolution
from skellycam.core.types.frame_dtype_factories import create_frame_dtype


@runtime_checkable
class CameraBackend(Protocol):
    def open(self, config: CameraConfig) -> CameraConfig: ...
    def grab(self) -> bool: ...
    def retrieve(self, out: np.ndarray) -> bool: ...
    def last_device_timestamp_ns(self) -> int: ...
    def close(self) -> None: ...


class NotRuntimeCheckable(Protocol):
    def grab(self) -> bool: ...


class FakeGigEBackend:
    """Emits BayerRG8 (RGGB) frames + a fake PTP timestamp, like a GenICam buffer would."""

    def __init__(self) -> None:
        self._buf: np.ndarray | None = None
        self._ts = 0
        self._ptp_epoch = 1_700_000_000_000_000_000

    def open(self, config: CameraConfig) -> CameraConfig:
        self._h, self._w = config.resolution.height, config.resolution.width
        return config

    def grab(self) -> bool:
        self._buf = np.zeros((self._h, self._w), np.uint8)
        self._buf[0::2, 0::2] = 200  # red sites only
        self._ts = self._ptp_epoch + time.perf_counter_ns()
        return True

    def retrieve(self, out: np.ndarray) -> bool:
        cv2.cvtColor(self._buf, cv2.COLOR_BayerBG2BGR, dst=out)  # PFNC BayerRG -> OpenCV BayerBG code
        return True

    def last_device_timestamp_ns(self) -> int:
        return self._ts

    def close(self) -> None:
        self._buf = None


@beartype
def get_frame(backend: CameraBackend, rec: np.recarray) -> tuple[bool, int]:
    rec.frame_metadata.timestamps.pre_frame_grab_ns[0] = time.perf_counter_ns()
    ok = backend.grab()
    rec.frame_metadata.timestamps.post_frame_grab_ns[0] = time.perf_counter_ns()
    if not ok:
        return False, 0
    ok = backend.retrieve(rec.image[0])
    return ok, backend.last_device_timestamp_ns()


cfg = CameraConfig(resolution=ImageResolution(height=48, width=64))
rec = np.recarray(1, dtype=create_frame_dtype(cfg))
be = FakeGigEBackend()
be.open(cfg)
print("isinstance(FakeGigEBackend(), CameraBackend):", isinstance(be, CameraBackend))
ok, dev_ts = get_frame(be, rec)
print("get_frame ok:", ok, "device ts:", dev_ts, "centre BGR:", tuple(int(v) for v in rec.image[0][24, 32]))


class NotABackend:
    pass


try:
    get_frame(NotABackend(), rec)
    print("beartype accepted NotABackend (unexpected)")
except BeartypeException as e:
    print("beartype rejected NotABackend:", type(e).__name__)

try:
    @beartype
    def f(b: NotRuntimeCheckable) -> None: ...
    f(be)
    print("non-runtime_checkable Protocol: decorated & called OK")
except Exception as e:
    print("non-runtime_checkable Protocol:", type(e).__name__, str(e)[:160])

print("'device_timestamp_ns' in frame timestamps dtype:",
      "device_timestamp_ns" in rec.frame_metadata.timestamps.dtype.names)
