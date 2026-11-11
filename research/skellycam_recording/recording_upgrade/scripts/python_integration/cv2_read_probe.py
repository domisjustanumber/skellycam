# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["opencv-python==5.0.0.93", "numpy==2.2.6"]
# ///
"""Open each compat clip the way FreeMoCap does and check frame identity (functional only, no timing).

FreeMoCap reads synchronized videos with cv2.VideoCapture(path) (video_group_helper.py:151) and
cv2.VideoCapture(path, cv2.CAP_FFMPEG) (video_node.py:297), takes CAP_PROP_FRAME_COUNT / CAP_PROP_FPS, reads
sequentially, and on upstream/sfn26 also seeks with CAP_PROP_POS_FRAMES (annotation_workers.py:56-57).

For each clip and each API preference (CAP_ANY, CAP_FFMPEG, CAP_MSMF): opened?, backend name, FRAME_COUNT,
FPS, FOURCC, frames read sequentially, whether frame k carries barcode k for every k, and POS_FRAMES seeks to
a set of targets (does the next read return barcode == target?).

Run with the skellycam venv (OpenCV 4.12):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/python_integration/cv2_read_probe.py --tag cv2_4.12_venv
Run isolated with OpenCV 5.0.0.93 (deps from the header above):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/python_integration/cv2_read_probe.py --tag cv2_5.0.0.93_uv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

COMPAT = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/compat")
ROUNDTRIP = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/roundtrip")
RESULTS = Path(__file__).resolve().parents[2] / "results/python_integration"
SEEK_TARGETS = [0, 1, 29, 30, 31, 59, 61, 62, 77, 119, 5]


def read_barcode(bgr: np.ndarray) -> int:
    g = bgr[4:36, :, :].mean(axis=2)
    v = 0
    for bit in range(16):
        if g[:, bit * 80 + 20: bit * 80 + 60].mean() > 128:
            v |= 1 << bit
    return v


def fourcc_str(cap) -> str:
    f = int(cap.get(cv2.CAP_PROP_FOURCC))
    return "".join(chr((f >> 8 * i) & 0xFF) for i in range(4)).strip("\x00")


def probe_clip(path: Path, api: int, n_expected: int, barcoded: bool) -> dict:
    cap = cv2.VideoCapture(str(path), api)
    r = {"opened": cap.isOpened()}
    if not cap.isOpened():
        return r
    try:
        r["backend"] = cap.getBackendName()
    except cv2.error as e:
        r["backend"] = repr(e)[:80]
    r["frame_count_prop"] = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    r["fps_prop"] = round(cap.get(cv2.CAP_PROP_FPS), 4)
    r["fourcc"] = fourcc_str(cap)
    ids = []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        ids.append(read_barcode(fr) if barcoded else -1)
    r["frames_read"] = len(ids)
    if barcoded:
        r["sequence_exact"] = ids == list(range(n_expected))
        if not r["sequence_exact"]:
            r["sequence_first_bad"] = next((i for i, v in enumerate(ids) if v != i), len(ids))
        seeks = {}
        for t in SEEK_TARGETS:
            if t >= n_expected:
                continue
            okset = cap.set(cv2.CAP_PROP_POS_FRAMES, t)
            ok, fr = cap.read()
            seeks[str(t)] = (read_barcode(fr) if ok else None) if okset else "set() False"
        r["seek_results"] = seeks
        r["seek_all_exact"] = all(seeks[k] == int(k) for k in seeks)
    cap.release()
    return r


TIMEOUT_S = 180


def run_one(path: str, api_name: str, n: int, barcoded: bool) -> dict:
    """Each (clip, API) runs in a child process so a hanging backend is recorded as a timeout, not a stall."""
    import subprocess
    cmd = [sys.executable, __file__, "--one", path, api_name, str(n), "1" if barcoded else "0"]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"opened": None, "error": f"TIMEOUT after {TIMEOUT_S} s (killed)"}
    line = [l for l in cp.stdout.splitlines() if l.startswith("{")]
    if not line:
        return {"opened": None, "error": f"child exit {cp.returncode}: {cp.stderr[-300:]}"}
    return json.loads(line[-1])


APIS = {"CAP_ANY": cv2.CAP_ANY, "CAP_FFMPEG": cv2.CAP_FFMPEG, "CAP_MSMF": cv2.CAP_MSMF}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--one":
        _, _, path, api_name, n, bc = sys.argv
        print(json.dumps(probe_clip(Path(path), APIS[api_name], int(n), bc == "1")))
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    man = json.loads((COMPAT / "manifest.json").read_text())
    apis = APIS
    out = {"tag": args.tag, "opencv": cv2.__version__, "python": sys.version.split()[0], "numpy": np.__version__,
           "videoio_backends": [cv2.videoio_registry.getBackendName(b) for b in cv2.videoio_registry.getBackends()],
           "file_backends": [cv2.videoio_registry.getBackendName(b) for b in cv2.videoio_registry.getStreamBackends()],
           "clips": {}}
    for name, e in man["clips"].items():
        if not e.get("ok"):
            continue
        out["clips"][name] = {a: run_one(e["path"], a, man["frames"], True) for a in apis}
        print(name, {a: (d.get("opened"), d.get("frames_read"), d.get("error")) for a, d in out["clips"][name].items()}, flush=True)
    # the real-camera-byte files from test_roundtrip.py (no barcode; frame count only)
    for p in sorted(ROUNDTRIP.glob("c930e_720p_flash.*")):
        if p.suffix in (".mkv", ".mp4", ".avi"):
            out["clips"]["camera_bytes:" + p.name] = {a: run_one(str(p), a, 891, False) for a in apis}
            print(p.name, flush=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"cv2_read_probe_{args.tag}.json").write_text(json.dumps(out, indent=1))
    for name, d in out["clips"].items():
        a, f = d["CAP_ANY"], d["CAP_FFMPEG"]
        print(f"{name:42s} ANY:{a.get('backend')},{a.get('frame_count_prop')},{a.get('frames_read')},seq={a.get('sequence_exact')},seek={a.get('seek_all_exact')} "
              f"FFMPEG:{f.get('opened')},{f.get('frame_count_prop')},{f.get('frames_read')},seq={f.get('sequence_exact')},seek={f.get('seek_all_exact')} MSMF:{d['CAP_MSMF'].get('opened')}")


if __name__ == "__main__":
    main()
