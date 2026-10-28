# /// script
# requires-python = ">=3.10"
# ///
"""Analyse per-frame JSONL logs (README frame-log schema) written by the Rust probes.

Usage:
    uv run --script research/usb_cameras/rust/tools/analyze_frames_rust.py [--os-ts-field FIELD] <run_dir> [<run_dir> ...]

--os-ts-field: use another per-frame field as os_timestamp_ns (e.g. implied_sample_time_ns for
  nokhwa_probe runs made before the Windows mapping fix, where os_timestamp_ns used the age method).

For each frames_*.jsonl in a run dir computes, after skipping the first 30 frames:
  - host-arrival interval stats and fps
  - os_timestamp interval stats (the OS/driver timestamp cadence)
  - latency = host_arrival_ns - os_timestamp_ns (only meaningful when both are on one clock)
  - JPEG validity counts, payload sizes
  - cross-camera: per-pair offset of nearest os_timestamps (for multi-camera runs)
Writes <run_dir>/analysis.json and prints a one-line summary per camera.
"""
import json
import statistics
import sys
from pathlib import Path

SKIP = 30


def st(v):
    if not v:
        return None
    s = sorted(v)
    q = lambda p: s[min(len(s) - 1, round(p * (len(s) - 1)))]
    return {"n": len(s), "mean": statistics.fmean(s), "std": statistics.pstdev(s), "min": s[0],
            "p01": q(0.01), "p50": q(0.5), "p99": q(0.99), "max": s[-1]}


OS_FIELD = None


def analyse_file(p: Path):
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    if OS_FIELD:
        for x in rows:
            x["os_timestamp_ns"] = x.get(OS_FIELD)
    r = rows[SKIP:] if len(rows) > SKIP + 10 else rows
    arr = [x["host_arrival_ns"] for x in r]
    ost = [x["os_timestamp_ns"] for x in r if x.get("os_timestamp_ns") is not None]
    out = {
        "file": p.name,
        "camera_key": rows[0]["camera_key"] if rows else None,
        "backend": rows[0]["backend"] if rows else None,
        "frames_total": len(rows),
        "frames_analysed": len(r),
        "skip_first": SKIP if r is not rows else 0,
        "valid_jpeg": sum(1 for x in rows if x.get("is_valid_jpeg")),
        "decoded_true": sum(1 for x in rows if x.get("decoded") is True),
        "decoded_false": sum(1 for x in rows if x.get("decoded") is False),
        "seq_gaps": sum(1 for a, b in zip(rows, rows[1:]) if b["seq"] != a["seq"] + 1),
        "payload_bytes": st([x["payload_bytes"] for x in r]),
        "fps_host": (len(arr) - 1) / ((arr[-1] - arr[0]) / 1e9) if len(arr) > 1 else None,
        "host_interval_ms": st([(b - a) / 1e6 for a, b in zip(arr, arr[1:])]),
        "os_ts_interval_ms": st([(b - a) / 1e6 for a, b in zip(ost, ost[1:])]),
        "latency_host_minus_os_ms": st([(x["host_arrival_ns"] - x["os_timestamp_ns"]) / 1e6 for x in r if x.get("os_timestamp_ns") is not None]),
        "first_frame_latency_ms": ((rows[0]["host_arrival_ns"] - rows[0]["os_timestamp_ns"]) / 1e6) if rows and rows[0].get("os_timestamp_ns") is not None else None,
        "os_timestamp_source": rows[0].get("os_timestamp_source") if rows else None,
    }
    # uvc fields if present (from uvc_iso)
    if any(x.get("uvc_pts") is not None for x in r):
        hz = next((x["device_clock_hz"] for x in r if x.get("device_clock_hz")), None)
        pts = [x["uvc_pts"] for x in r if x.get("uvc_pts") is not None]
        if hz:
            d = [((b - a) % (1 << 32)) / hz * 1e3 for a, b in zip(pts, pts[1:])]
            out["uvc_pts_interval_ms"] = st(d)
    return out, r


def cross(cams):
    """For each pair, nearest-neighbour os_timestamp offset (ms) — shows relative phase of free-running cameras."""
    res = []
    keys = list(cams)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a = [x["os_timestamp_ns"] for x in cams[keys[i]] if x.get("os_timestamp_ns") is not None]
            b = [x["os_timestamp_ns"] for x in cams[keys[j]] if x.get("os_timestamp_ns") is not None]
            if not a or not b:
                continue
            k = 0
            offs = []
            for t in a:
                while k + 1 < len(b) and abs(b[k + 1] - t) <= abs(b[k] - t):
                    k += 1
                offs.append((b[k] - t) / 1e6)
            res.append({"a": keys[i], "b": keys[j], "nearest_offset_ms": st(offs),
                        "first_offset_ms": offs[0], "last_offset_ms": offs[-1],
                        "drift_ms_per_min": (offs[-1] - offs[0]) / (((a[-1] - a[0]) / 1e9) / 60) if len(a) > 1 else None})
    return res


def main():
    global OS_FIELD
    argv = sys.argv[1:]
    if argv[:1] == ["--os-ts-field"]:
        OS_FIELD = argv[1]
        argv = argv[2:]
    for d in argv:
        d = Path(d)
        files = sorted(d.glob("frames_*.jsonl"))
        per = []
        cams = {}
        for f in files:
            o, r = analyse_file(f)
            per.append(o)
            cams[f.stem] = r
            lat = o["latency_host_minus_os_ms"]
            print(f"{d.name} {f.stem}: frames={o['frames_total']} valid_jpeg={o['valid_jpeg']} fps={o['fps_host'] and round(o['fps_host'],2)} "
                  f"host_int_std={o['host_interval_ms'] and round(o['host_interval_ms']['std'],2)}ms "
                  f"os_int_std={o['os_ts_interval_ms'] and round(o['os_ts_interval_ms']['std'],3)}ms "
                  f"lat_p50={lat and round(lat['p50'],2)}ms lat_min={lat and round(lat['min'],2)} lat_p99={lat and round(lat['p99'],2)}")
        out = {"run_dir": str(d), "analyzer": "research/usb_cameras/rust/tools/analyze_frames_rust.py", "os_ts_field_override": OS_FIELD, "cameras": per, "cross_camera": cross(cams)}
        (d / "analysis.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
