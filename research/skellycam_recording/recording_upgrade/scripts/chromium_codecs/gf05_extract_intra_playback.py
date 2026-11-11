# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""GF05 (2026-11-10): re-read intra_playback timed-bench JSON for the chromium_codecs /
chromium_sync_scrub doc fixes. Reads files only; runs no test and no timing.

Usage: uv run --script gf05_extract_intra_playback.py <RU root> <out json>
"""
import glob
import json
import os
import sys

ru = sys.argv[1]
out = sys.argv[2]
B = os.path.join(ru, "results", "intra_playback", "bench")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


res = {"seek": [], "sync": [], "scrub": []}

for e in ("e35", "e45"):
    for p in sorted(glob.glob(os.path.join(B, e, "bench_intra_seek", "c1080p30_*.json"))):
        d = load(p)
        s = d["result"]["summary"]
        row = {
            "electron": e,
            "file": os.path.basename(p),
            "exact": s.get("exact"),
            "n": s.get("n"),
            "errors": s.get("errors"),
            "lat_ms_p50": (s.get("lat_ms") or {}).get("p50"),
            "lat_rvfc_ms_p50": (s.get("lat_rvfc_ms") or {}).get("p50"),
            "lat_seeked_ms_p50": (s.get("lat_seeked_ms") or {}).get("p50"),
        }
        res["seek"].append(row)
    for p in sorted(glob.glob(os.path.join(B, e, "bench_intra_sync", "c1080p30_*.json"))):
        d = load(p)
        r = d["result"]
        ms = d.get("metrics_summary") or {}
        per = r.get("per_stream") or []
        rv = [x.get("rvfc_callbacks") for x in per if isinstance(x, dict) and x.get("rvfc_callbacks") is not None]
        med = sorted(rv)[len(rv) // 2] if rv else None
        row = {
            "electron": e,
            "file": os.path.basename(p),
            "n": r.get("n"),
            "spread_p50": (r.get("spread") or {}).get("p50"),
            "spread_p95": (r.get("spread") or {}).get("p95"),
            "spread_max": (r.get("spread") or {}).get("max"),
            "spread_exact0_pct": r.get("spread_exact0_pct"),
            "ticks_per_s": (r["ticks"] / r["dur_s"]) if r.get("ticks") and r.get("dur_s") else None,
            "rvfc_min": min(rv) if rv else None,
            "rvfc_median_upper": med,
            "rvfc_min_over_median": (min(rv) / med) if rv and med else None,
            "cpu_cores_total": ms.get("cpu_cores_total_from_cumulative"),
            "ws_mb_last": ms.get("total_ws_mb_last"),
        }
        res["sync"].append(row)
    for p in sorted(glob.glob(os.path.join(B, e, "bench_intra_scrub", "c1080p30_*.json"))):
        d = load(p)
        r = d["result"]
        fs = r.get("frames_shown_per_s")
        per = r.get("per_stream") or []
        errs = [x.get("errors") for x in per if isinstance(x, dict) and isinstance(x.get("errors"), (int, float))]
        gpu = [s for s in d.get("metrics_samples", []) if s.get("type") == "GPU"]
        res["scrub"].append({
            "electron": e,
            "file": os.path.basename(p),
            "frames_shown_per_s": fs,
            "lag_frames": r.get("lag_frames"),
            "input_events": r.get("input_events"),
            "per_stream_errors_sum": sum(errs) if errs else 0,
            "gpu_private_kb_peak": max((s["private_kb"] for s in gpu), default=None),
            "gpu_pids": len({s["pid"] for s in gpu}),
            "cpu_cores_total": (d.get("metrics_summary") or {}).get("cpu_cores_total_from_cumulative"),
        })

# intra_playback clip checks for the 48 NVENC/QSV H.264/HEVC clips (all-IDR, no B, decode order)
cs = load(os.path.join(ru, "results", "intra_playback", "clips_summary.json"))["clips"]
n = idr = nob = order = 0
for k, v in cs.items():
    if "mjpeg" in k or not any(e in k for e in ("h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv")):
        continue
    n += 1
    nc, ff = v["nal_check"], v["ffprobe"]
    idr += nc["frames_with_idr"] == nc["frames"] and nc["frames_with_non_irap_vcl"] == 0
    nob += ff["stream"].get("has_b_frames") == 0
    order += bool(v.get("decode_order_equals_pts_order"))
res["clip_checks"] = {"clips": n, "all_idr": idr, "has_b_frames_0": nob, "decode_order_equals_pts_order": order,
                      "source": "results/intra_playback/clips_summary.json clips.*.{nal_check,ffprobe.stream.has_b_frames,decode_order_equals_pts_order}"}

with open(out, "w", encoding="utf-8") as f:
    json.dump(res, f, indent=1)
print("seek", len(res["seek"]), "sync", len(res["sync"]), "scrub", len(res["scrub"]))
