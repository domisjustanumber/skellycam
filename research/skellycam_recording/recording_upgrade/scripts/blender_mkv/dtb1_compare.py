# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "pillow==11.3.0"]
# ///
"""DT-B1 driver: build jobs, run Blender headless, check frame identity against PyAV decodes.

Run (repo root):  uv run --script research/skellycam_recording/recording_upgrade/scripts/blender_mkv/dtb1_compare.py <work_dir>
Inputs: the GF02 Part A MKVs (gf02_common.MEDIA/partA, PyAV 19.0.2 writer, MJPEG passthrough), index and real PTS.
Output: results/blender_mkv/DTB1_result.json (PNG renders stay in <work_dir>; rebuildable).

Identity: Blender frame f (1-based) is compared with PyAV's decode of packets f-1-3 .. f-1+3 (mean absolute
difference over RGB). Expected match = packet f-1. 'margin' = second-best MAE / best MAE.
"""
import json
import subprocess
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "results" / "blender_mkv"
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/gapfill/GF02/partA")
BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")
INPUTS = ["c930e_full", "gap60", "drop50", "c922_full"]
WINDOW = 3


def packet_count(path: Path) -> int:
    with av.open(str(path)) as c:
        return sum(1 for p in c.demux(c.streams.video[0]) if p.size)


def reference_frames(path: Path, wanted: set[int]) -> dict[int, np.ndarray]:
    out = {}
    with av.open(str(path)) as c:
        for i, frame in enumerate(c.decode(video=0)):
            if i in wanted:
                out[i] = frame.to_ndarray(format="rgb24").astype(np.int16)
            if i >= max(wanted):
                break
    return out


def main() -> None:
    work = Path(sys.argv[1])
    work.mkdir(parents=True, exist_ok=True)
    jobs, counts = [], {}
    for inp in INPUTS:
        for mode in ("index", "real"):
            name = f"{inp}_{mode}"
            path = MEDIA / f"A_{inp}_mkv_fp_{mode}.mkv"
            n = packet_count(path)
            counts[name] = n
            frames = sorted({1, 2, n // 2, n - 1, n})
            jobs.append({"name": name, "path": str(path), "frames": frames})
    (work / "jobs.json").write_text(json.dumps(jobs, indent=1))
    proc = subprocess.run([str(BLENDER), "-b", "--factory-startup", "--python", str(HERE / "dtb1_blender.py"),
                           "--", str(work / "jobs.json"), str(work / "renders")],
                          capture_output=True, text=True, timeout=1800)
    (work / "blender_stdout.txt").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr)
    bres = json.loads((work / "renders" / "blender_result.json").read_text())

    files = {}
    for job in jobs:
        name, n = job["name"], counts[job["name"]]
        b = bres["files"][name]
        rendered = b.get("vse_strip", {}).get("rendered", {})
        wanted = {k for f in job["frames"] for k in range(f - 1 - WINDOW, f + WINDOW) if 0 <= k < n}
        ref = reference_frames(Path(job["path"]), wanted)
        ident = {}
        for f in job["frames"]:
            png = rendered.get(str(f))
            if not png or not Path(png).exists():
                ident[f] = {"error": "no render"}
                continue
            img = np.asarray(Image.open(png).convert("RGB"), dtype=np.int16)
            maes = {k: float(np.abs(img - ref[k]).mean()) for k in sorted(ref) if abs(k - (f - 1)) <= WINDOW
                    and ref[k].shape == img.shape}
            if not maes:
                ident[f] = {"error": f"shape mismatch: blender {img.shape}"}
                continue
            best = min(maes, key=maes.get)
            others = sorted(v for k, v in maes.items() if k != best)
            ident[f] = {"best_packet": best, "expected_packet": f - 1, "match": best == f - 1,
                        "best_mae": round(maes[best], 3),
                        "margin": round(others[0] / maes[best], 2) if others and maes[best] > 0 else None}
        files[name] = {"packets": n, "images_load": b["images_load"], "movieclips_load": b["movieclips_load"],
                       "vse": {k: v for k, v in b.get("vse_strip", {}).items() if k != "rendered"},
                       "identity": ident}
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = {"blender": bres["blender"], "build_hash": bres["build_hash"], "ffmpeg": bres["ffmpeg"],
           "pyav": av.__version__, "media": str(MEDIA), "blender_returncode": proc.returncode, "files": files}
    (RESULTS / "DTB1_result.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
