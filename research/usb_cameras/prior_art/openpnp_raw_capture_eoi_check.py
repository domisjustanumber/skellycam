# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26"]
# ///
"""Offline check of the raw-MJPEG path on skellycam branch dom/openpnp-capture-mf. Opens no camera.

openpnp-capture-python 0aec3cc (`OpenPnPCamera.capture_raw_frame_into`) finds the frame length by the LAST
0xFF 0xD9 (JPEG EOI) pair in the buffer. With the stock openpnp-capture v0.0.30 DLL the buffer holds RGB24
pixels, not JPEG. skellycam's `openpnp_get_frame` then slices the buffer to that length and reshapes it to
(h, w, 3). This replays both steps on synthetic 720p RGB buffers.

RUN: uv run --script research/usb_cameras/prior_art/openpnp_raw_capture_eoi_check.py [--out <json>]
"""
import argparse, datetime, json, socket, sys
from pathlib import Path

import numpy as np

H, W = 720, 1280
NEED = H * W * 3


def wrapper_byte_count(buf):
    # openpnp_capture/camera.py capture_raw_frame_into, verbatim logic
    eoi = np.where((buf[:-1] == 0xFF) & (buf[1:] == 0xD9))[0]
    return int(eoi[-1]) + 2 if len(eoi) else NEED


def skellycam_reshape(buf, byte_count):
    # skellycam openpnp_get_frame.py RGB branch
    raw = buf[:byte_count]
    try:
        raw[: H * W * 3].reshape(H, W, 3)
        return "reshape ok"
    except ValueError as e:
        return f"ValueError: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    dark = rng.integers(10, 60, NEED, dtype=np.uint8)  # dim scene, no byte reaches 255
    one_pixel = dark.copy()
    one_pixel[NEED // 2], one_pixel[NEED // 2 + 1] = 0xFF, 0xD9  # one warm highlight: R=255, G=217
    bright = np.clip(np.linspace(150, 300, NEED) + rng.normal(0, 20, NEED), 0, 255).astype(np.uint8)
    cases = []
    for name, buf in [("dim frame", dark), ("dim frame + one R=255,G=217 pixel", one_pixel), ("bright gradient + noise", bright)]:
        bc = wrapper_byte_count(buf)
        cases.append({
            "case": name,
            "ff_d9_pairs": int(((buf[:-1] == 0xFF) & (buf[1:] == 0xD9)).sum()),
            "byte_count": bc,
            "need": NEED,
            "outcome": skellycam_reshape(buf, bc),
        })
    rec = {
        "test": "openpnp_raw_capture_eoi_check",
        "platform": sys.platform,
        "hostname": socket.gethostname(),
        "utc_started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "command": " ".join(sys.argv),
        "environment": {"python": sys.version, "numpy": np.__version__},
        "cameras": [],
        "cases": cases,
    }
    text = json.dumps(rec, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
