# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""GF04 (doc fix, no timing run): re-read the quiet-run intra_compare JSONs and extract, per candidate,
the measured 1080p30 / 720p30 capacity at target A (largest N whose paced reps all keep up), the CPU
cores at that N, the unpaced aggregate fps at that N, plus single-stream rows for paths with no
scaling item (libx264/libx265, nvJPEG fed decoded MJPEG). Reads files only; opens no device.

Run from the repo root:
  uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/gf04_capacity_extract.py
Writes research/skellycam_recording/recording_upgrade/results/hw_accel_target/gapfill/GF04_capacity.json
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

RU = Path(__file__).resolve().parents[2]
B = RU / "results" / "intra_compare" / "bench"
OUT = RU / "results" / "hw_accel_target" / "gapfill" / "GF04_capacity.json"


def stats(v):
    v = [x for x in v if x is not None]
    if not v:
        return None
    return {"median": round(statistics.median(v), 3), "min": round(min(v), 3), "max": round(max(v), 3), "n": len(v)}


def scaling(path: Path) -> dict:
    d = json.loads(path.read_text())
    by = defaultdict(lambda: defaultdict(list))
    for r in d["runs"]:
        by[r["mode"]][r["requested"]].append(r)
    per_n = {}
    for n, reps in sorted(by["paced"].items()):
        per_n[n] = {
            "opened": [r["opened"] for r in reps],
            "streams_keeping_up": [r["streams_keeping_up"] for r in reps],
            "late_frames": [r["late_frames"] for r in reps],
            "all_keep_up": all(r["opened"] > 0 and r["streams_keeping_up"] == r["opened"] for r in reps),
            "cpu_cores": stats([r["cpu_cores"] for r in reps]),
            "aggregate_fps": stats([r["aggregate_fps"] for r in reps]),
        }
    ok = [n for n, v in per_n.items() if v["all_keep_up"]]
    best_req = max(ok) if ok else None
    best = per_n.get(best_req) if best_req else None
    unp = by["unpaced"].get(best_req, []) if best_req else []
    a = d["args"]
    return {
        "file": f"results/intra_compare/bench/{path.name}",
        "path": a["path"], "size": a["size"], "source": a["source"], "workers": a["workers"],
        "target": a["target"], "reps": a["reps"],
        "affinity_before": d["system_before"].get("process_cpu_affinity"),
        "affinity_after": d["system_after"].get("process_cpu_affinity"),
        "max_requested_N_all_reps_keep_up": best_req,
        "streams_at_that_N": min(best["opened"]) if best else 0,
        "late_frames_at_that_N": best["late_frames"] if best else None,
        "cpu_cores_paced_at_that_N": best["cpu_cores"] if best else None,
        "unpaced_aggregate_fps_at_that_N": stats([r["aggregate_fps"] for r in unp]),
        "limit_probe": {k: d.get("limit_probe", {}).get(k) for k in ("max_tried", "opened")} if d.get("limit_probe") else None,
        "paced_per_N": per_n,
    }


def single(name: str, want: list[tuple[str, str]]) -> list[dict]:
    d = json.loads((B / name).read_text())
    out = []
    for s in d["summary"]:
        if (s["path"], s["source"]) in want:
            qc = s.get("quality_check") or {}
            out.append({
                "file": f"results/intra_compare/bench/{name}", "path": s["path"], "source": s["source"],
                "fps_median": s.get("fps_median"), "fps_min": s.get("fps_min"), "fps_max": s.get("fps_max"),
                "cpu_cores_median": s.get("cpu_cores_median"), "cpu_ms_per_frame_median": s.get("cpu_ms_per_frame_median"),
                "qc_psnr_y": qc.get("psnr_y"), "qc_ssim_y": qc.get("ssim_y"),
                "matched_psnr_y": qc.get("matched_psnr_y"), "matched_ssim_y": qc.get("matched_ssim_y"),
            })
    return out


def main():
    res = {"note": "parsed from quiet run 20261109T230007 JSONs; no timing was run for GF04",
           "scaling": [scaling(p) for p in sorted(B.glob("matched_concurrent_*.json"))]}
    want = [("libx264_ultrafast_420", "nv12"), ("libx264_veryfast_420", "nv12"), ("libx265_ultrafast_420", "nv12"),
            ("nvjpeg_420", "mjpeg_cpu"), ("nvjpeg_422", "mjpeg_cpu"), ("nvjpeg_420", "mjpeg_qsv"),
            ("hevc_qsv_420", "nv12"), ("mjpeg_qsv_422", "yuy2"), ("nvjpeg_422", "yuy2"), ("nvjpeg_420", "nv12")]
    res["single_stream_A_1080p"] = single("matched_stream_A_1080p_20261110T042204Z.json", want)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    for s in res["scaling"]:
        print(f'{s["path"]:16} {s["size"]:5} {s["source"]:9} {s["workers"]:7} N_req={s["max_requested_N_all_reps_keep_up"]} '
              f'streams={s["streams_at_that_N"]} cores={s["cpu_cores_paced_at_that_N"]} unp={s["unpaced_aggregate_fps_at_that_N"]} '
              f'late={s["late_frames_at_that_N"]} probe={s["limit_probe"]}')
    for r in res["single_stream_A_1080p"]:
        print(r)


if __name__ == "__main__":
    main()
