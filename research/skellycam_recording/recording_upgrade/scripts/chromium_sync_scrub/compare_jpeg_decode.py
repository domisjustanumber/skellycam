"""Compare Chromium's decode of the cameras' own JPEG bytes (frame 0 of each corpus MJPEG set) with
OpenCV (libjpeg-turbo) and PyAV/libavcodec mjpeg decodes.

Input: RGBA dumps written by the harness 'jpegcompat' test:
  C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/blobs/<set>_f0_{bitmap,imagedecoder}_e<ver>.rgba
Output: research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/functional/jpeg_decode_compare.json
Run: .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/compare_jpeg_decode.py
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import av
import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[5]
CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
BLOBS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/blobs")
OUT = REPO / "research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/functional/jpeg_decode_compare.json"


def diff(a: np.ndarray, b: np.ndarray) -> dict:
    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    return {"max_abs": int(d.max()), "mean_abs": round(float(d.mean()), 4), "pct_exact": round(100 * float((d == 0).mean()), 3)}


def main() -> None:
    idx = json.loads((CORPUS / "index.json").read_text())
    out = {}
    for name, s in idx.items():
        if s["kind"] != "mjpeg":
            continue
        jb = (CORPUS / name / "frame_000000.jpg").read_bytes()
        w, h = s["width"], s["height"]
        ocv = cv2.cvtColor(cv2.imdecode(np.frombuffer(jb, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        with av.open(io.BytesIO(jb), format="mjpeg") as c:
            pyav = next(c.decode(video=0)).to_ndarray(format="rgb24")
        r = {"opencv_vs_pyav": diff(ocv, pyav)}
        for f in sorted(BLOBS.glob(f"{name}_f0_*.rgba")):
            rgba = np.frombuffer(f.read_bytes(), np.uint8)
            if rgba.size != w * h * 4:
                r[f.stem] = {"error": f"size {rgba.size} != {w * h * 4}"}
                continue
            rgb = rgba.reshape(h, w, 4)[:, :, :3]
            r[f.stem.replace(f"{name}_f0_", "")] = {"vs_opencv": diff(rgb, ocv), "vs_pyav": diff(rgb, pyav)}
        out[name] = r
        print(name, json.dumps(r))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"opencv": cv2.__version__, "pyav": av.__version__, "sets": out}, indent=1))


if __name__ == "__main__":
    main()
