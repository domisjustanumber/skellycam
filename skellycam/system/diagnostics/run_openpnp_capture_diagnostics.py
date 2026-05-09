"""Enumerate cameras and benchmark ``Cap_captureFrame`` latency via :class:`OpenPnPCamera`."""

from __future__ import annotations

import statistics
import time
from typing import Any

import numpy as np
import pandas as pd

from skellycam.core.camera.openpnp_capture import OpenPnPCamera


def measure_capture_latency(camera: OpenPnPCamera, frames: int = 30) -> dict[str, float]:
    durations_ms: list[float] = []
    h, w = camera.format.height, camera.format.width
    buf = np.zeros((h, w, 3), dtype=np.uint8)
    for _ in range(frames):
        t0 = time.perf_counter_ns()
        ok = camera.capture_frame_into(buf)
        t1 = time.perf_counter_ns()
        if ok:
            durations_ms.append((t1 - t0) / 1e6)
    if not durations_ms:
        return {
            "Mean Frame Rate (fps)": float("nan"),
            "Mean Capture Duration (ms)": float("nan"),
            "Std Dev Capture Duration (ms)": float("nan"),
        }
    elapsed_s = sum(durations_ms) / 1000.0
    return {
        "Mean Frame Rate (fps)": len(durations_ms) / max(elapsed_s, 1e-9),
        "Mean Capture Duration (ms)": float(statistics.mean(durations_ms)),
        "Std Dev Capture Duration (ms)": float(statistics.pstdev(durations_ms)) if len(durations_ms) > 1 else 0.0,
    }


def run_camera_diagnostics(image_sizes: list[tuple[int, int]]) -> None:
    results: list[dict[str, Any]] = []
    devices = OpenPnPCamera.list_devices()
    if not devices:
        print("No cameras detected.")
        return

    dev = devices[0]
    size_set = set(image_sizes)
    for fmt in dev.formats:
        if (fmt.width, fmt.height) not in size_set:
            continue
        print(f"Testing device 0: {fmt.fourcc_str} @ {fmt.width}x{fmt.height} ({fmt.fps}fps)")
        cam = OpenPnPCamera(0, fmt.format_id, format_info=fmt, device_formats=dev.formats)
        try:
            cam.open()
            metrics = measure_capture_latency(cam)
            results.append(
                {
                    "FourCC": fmt.fourcc_str,
                    "Resolution": f"{fmt.width}x{fmt.height}",
                    **metrics,
                }
            )
            print(results[-1])
        finally:
            cam.close()

    if results:
        df = pd.DataFrame(results)
        pd.set_option("display.float_format", "{:.3f}".format)
        print(df.to_string(index=False))


if __name__ == "__main__":
    run_camera_diagnostics(image_sizes=[(640, 480), (1280, 720), (1920, 1080)])
