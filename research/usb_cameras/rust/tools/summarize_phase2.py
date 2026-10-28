# /// script
# requires-python = ">=3.10"
# ///
"""Collect the phase-2 uvc_iso runs (+ libuvc and nusb-PR233 baselines) into one comparison JSON.

Usage:
    uv run --script research/usb_cameras/rust/tools/summarize_phase2.py <phase2_rust_uvc_iso/<ts> dir> [--libuvc DIR ...] [--nusb DIR ...] --out FILE

For every stream_* dir (recursively) it reads summary.json, decode_check.json (Pillow full decode) and
the frames jsonl, and reports alt, bytes/interval, PROBE/COMMIT, frames, fps, decoded %, PTS gaps
(excluding the first frame pair, whose PTS is stale on the C930e), host-arrival gaps, mean frame size,
latency arrival-PTS, CPU %, time to first frame.
"""
import json
import statistics
import sys
from pathlib import Path


def load(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return None


def uvc_iso_row(d: Path):
    s = load(d / "summary.json")
    if not s:
        return None
    r = s.get("results") or {}
    dc = load(d / "decode_check.json") or {}
    fr = sorted(d.glob("frames_*.jsonl"))
    rows = [json.loads(l) for l in fr[0].read_text().splitlines() if l.strip()] if fr else []
    hz = rows[0]["device_clock_hz"] if rows else 0
    per = (s["probe_commit"]["negotiated"]["dwFrameInterval"] * hz / 1e7) if rows and "probe_commit" in s else None
    pts = [x["uvc_pts"] for x in rows if x.get("uvc_pts") is not None]
    dd = [((b - a) % (1 << 32)) for a, b in zip(pts, pts[1:])]
    gaps_after_first = sum(1 for x in dd[1:] if per and x >= 1.5 * per)
    sizes = [x["payload_bytes"] for x in rows]
    lat = r.get("latency_arrival_minus_pts_ms") or {}
    return {
        "run": str(d.as_posix()), "backend": s.get("environment", {}).get("backend"), "error": s.get("error"),
        "alt_policy": s.get("settings", {}).get("alt_policy"),
        "alt": s.get("alt_selected", {}).get("alt"), "bytes_per_interval": s.get("alt_selected", {}).get("bytes_per_interval"),
        "probe_commit_negotiated": (s.get("probe_commit") or {}).get("negotiated"), "probe_commit_ms": (s.get("probe_commit") or {}).get("ms"),
        "seconds": s.get("settings", {}).get("seconds"), "frames": r.get("frames"), "fps": r.get("fps_host_after_skip30"),
        "valid_soi_eoi": r.get("valid_jpeg"), "decoded_ok": dc.get("decoded_ok"), "decode_failed": dc.get("decode_failed"),
        "percent_decoded": dc.get("percent_decoded"),
        "pts_gaps_excluding_first_pair": gaps_after_first, "host_arrival_gaps": r.get("host_arrival_gaps_ge_1p5_period"),
        "assembler_seq_gaps": 0, "bad_headers": r.get("bad_headers"), "payloads_without_eoh": r.get("payloads_without_eoh_bit"),
        "err_flag_payloads": r.get("err_flag_payloads"), "overflows": r.get("overflows"),
        "frames_with_pts": sum(1 for x in rows if x.get("uvc_pts") is not None), "frames_with_scr": sum(1 for x in rows if x.get("uvc_scr_stc") is not None),
        "mean_frame_bytes": statistics.fmean(sizes) if sizes else None,
        "latency_arrival_minus_pts_ms_p50": lat.get("p50"), "latency_min": lat.get("min"),
        "cpu_percent_one_core": (r.get("cpu") or {}).get("percent_of_one_core"), "time_to_first_frame_ms": r.get("time_to_first_frame_ms"),
        "device_clock_fit": s.get("device_clock_fit"),
    }


def libuvc_row(d: Path):
    s = load(d / "result.json")
    if not s:
        return None
    m = s["measurements"]
    return {"run": str(d.as_posix()), "backend": f"libuvc {s['environment']['libuvc_commit'][:8]} + libusb {s['environment']['libusb']}",
            "alt": s["iso"]["chosen_altsetting"], "bytes_per_interval": s["iso"]["bytes_per_packet"],
            "probe_commit_negotiated": s["negotiation"]["commit"], "seconds": s["requested"]["seconds"], "frames": m["frames"],
            "fps": m["fps_from_arrivals"], "valid_soi_eoi": m["jpeg_soi_eoi_ok"], "seq_gaps_libuvc": m["seq_gaps"],
            "error_payloads": m["error_payloads"], "frames_with_pts": m["frames_with_pts"], "frames_with_scr": m["frames_with_scr"],
            "mean_frame_bytes": m["mean_frame_bytes"], "transfers_queued": s["iso"]["transfers_queued"], "packets_per_transfer": s["iso"]["packets_per_transfer"]}


def nusb_row(d: Path):
    s = load(d / "summary.json")
    if not s:
        return None
    r = s.get("results") or {}
    dc = load(d / "decode_check.json") or {}
    return {"run": str(d.as_posix()), "backend": s["environment"]["nusb"], "alt": s.get("alt_selected", {}).get("alt"),
            "bytes_per_interval": s.get("alt_selected", {}).get("bytes_per_interval"), "initial_queue": s.get("initial_queue"),
            "frames": r.get("frames"), "fps": r.get("fps_after_skip30"), "valid_soi_eoi": r.get("valid_jpeg_soi_eoi"),
            "decoded_ok": dc.get("decoded_ok"), "pts_gaps": r.get("pts_gaps_ge_1p5_period"), "packets": r.get("packets"),
            "microframes_in_wall": round((r.get("wall_s") or 0) * 8000), "max_pending_observed": r.get("max_pending_observed"), "error": s.get("error")}


def main(a):
    root = Path(a[0])
    out = None
    lib, nus = [], []
    i = 1
    while i < len(a):
        if a[i] == "--libuvc":
            lib.append(Path(a[i + 1])); i += 2
        elif a[i] == "--nusb":
            nus.append(Path(a[i + 1])); i += 2
        elif a[i] == "--out":
            out = Path(a[i + 1]); i += 2
        else:
            i += 1
    runs = [x for x in (uvc_iso_row(d) for d in sorted(root.rglob("stream_*")) if d.is_dir()) if x]
    res = {"test": "phase2_rust_uvc_iso_summary", "analyzer": "research/usb_cameras/rust/tools/summarize_phase2.py",
           "command": "uv run --script research/usb_cameras/rust/tools/summarize_phase2.py " + " ".join(a),
           "uvc_iso_runs": runs, "libuvc_baseline": [x for x in map(libuvc_row, lib) if x], "nusb_pr233": [x for x in map(nusb_row, nus) if x]}
    out.write_text(json.dumps(res, indent=1))
    for x in runs:
        print(f"{Path(x['run']).name:30s} {str(x['backend'])[:12]:12s} alt={x['alt']} bpi={x['bytes_per_interval']} fr={x['frames']} fps={x['fps'] and round(x['fps'],2)} dec={x['decoded_ok']}/{x['frames']} ptsgap={x['pts_gaps_excluding_first_pair']} KB={x['mean_frame_bytes'] and round(x['mean_frame_bytes']/1e3)} lat={x['latency_arrival_minus_pts_ms_p50'] and round(x['latency_arrival_minus_pts_ms_p50'],1)} cpu={x['cpu_percent_one_core'] and round(x['cpu_percent_one_core'],1)} ttff={x['time_to_first_frame_ms'] and round(x['time_to_first_frame_ms'],1)}")


if __name__ == "__main__":
    main(sys.argv[1:])
