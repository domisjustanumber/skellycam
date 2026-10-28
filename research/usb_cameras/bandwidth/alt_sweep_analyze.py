# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow==12.0.0"]
# ///
"""Analyse alt_sweep_run.sh output (goal 3 phase 2): per run, delivered fps, valid JPEG (SOI/EOI AND full decode
with Pillow), sequence gaps, camera-side frame skips (UVC SCR STC / PTS steps), error payloads, payload sizes vs the
forced alt's capacity, and the PROBE/COMMIT dwMaxPayloadTransferSize. Optionally deletes the saved JPEGs afterwards.

  uv run --script research/usb_cameras/bandwidth/alt_sweep_analyze.py RAWDIR [RAWDIR...] --out RESULT.json [--delete-jpegs]
       [--only SUBSTRING]
Capacity per frame = bytes_per_microframe(alt) * 8000 / fps  (high-speed: 8000 microframes/s; the 12-byte UVC
payload header per microframe is included, so usable JPEG capacity is ~0.4-6 % lower depending on alt).
"""
from __future__ import annotations
import argparse, json, os, statistics, sys, warnings
from pathlib import Path
from PIL import Image


def pct(v, p):
    if not v:
        return None
    s = sorted(v)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def decode_ok(path: Path, w: int, h: int) -> tuple[bool, str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            im = Image.open(path)
            im.load()
        if im.size != (w, h):
            return False, f"size {im.size}"
        return True, ""
    except Exception as e:  # truncated / corrupt
        return False, f"{type(e).__name__}: {str(e)[:80]}"


def analyse(d: Path, delete: bool) -> dict:
    out = {"run_dir": str(d), "name": d.name}
    if not (d / "result.json").exists():
        out["error"] = "no result.json"
        out["stderr"] = (d / "stderr.log").read_text(errors="replace")[-600:] if (d / "stderr.log").exists() else None
        return out
    res = json.loads((d / "result.json").read_text())
    req, iso, neg, m = res["requested"], res["iso"], res["negotiation"], res["measurements"]
    alts = {a["alt"]: a["bytes_per_interval"] for a in res["cameras"][0]["vs_altsettings"]}
    fps = req["fps"]
    w, h = req["width"], req["height"]
    cap = iso["bytes_per_packet"] * 8000 / fps if iso["bytes_per_packet"] else None
    fl = d / "frames.jsonl"
    frames = [json.loads(l) for l in fl.read_text().splitlines() if l.strip()] if fl.exists() else []
    sizes = [f["payload_bytes"] for f in frames]
    soi = sum(1 for f in frames if f["is_valid_jpeg"])
    jp = sorted(d.glob("frame_*.jpg"))
    dec_ok, dec_fail, fail_examples = 0, 0, []
    for p in jp:
        ok, why = decode_ok(p, w, h)
        if ok:
            dec_ok += 1
        else:
            dec_fail += 1
            if len(fail_examples) < 3:
                fail_examples.append({"file": p.name, "why": why})
    # frames failing the SOI/EOI check are never saved by uvc_capture_test -> they count as not decodable
    stc_hz = frames[0]["device_clock_hz"] if frames else 0
    period_ticks = stc_hz / fps if stc_hz else None
    skips_stc = skips_pts = 0
    # interval 0 is excluded: the C930e always discards ~5-6 frames before its first delivered frame (startup)
    out["startup_skip_frames_by_scr_stc"] = (round(((frames[1]["uvc_scr_stc_first"] - frames[0]["uvc_scr_stc_first"]) % (1 << 32)) / period_ticks) - 1
                                             if len(frames) > 1 and period_ticks and frames[0].get("uvc_scr_stc_first") is not None else None)
    for a, b in zip(frames[1:], frames[2:]):
        if a.get("uvc_scr_stc_first") is not None and b.get("uvc_scr_stc_first") is not None and period_ticks:
            k = round(((b["uvc_scr_stc_first"] - a["uvc_scr_stc_first"]) % (1 << 32)) / period_ticks)
            if k > 1:
                skips_stc += k - 1
        if a.get("uvc_pts") is not None and b.get("uvc_pts") is not None:
            k = round(((b["uvc_pts"] - a["uvc_pts"]) % (1 << 32)) / 997222)  # C930e synthetic PTS step (phase 1)
            if k > 1:
                skips_pts += k - 1
    arr = [f["host_arrival_ns"] for f in frames]
    gaps = [(b - a) / 1e6 for a, b in zip(arr, arr[1:])]
    med = statistics.median(sizes) if sizes else None
    out.update({
        "mode": f"MJPEG {w}x{h}@{fps}", "requested_alt": req["alt"], "chosen_alt": iso["chosen_altsetting"],
        "alt_bytes_per_microframe": iso["bytes_per_packet"], "capacity_bytes_per_frame": round(cap) if cap else None,
        "probe_dwMaxPayloadTransferSize": neg["probe"]["dwMaxPayloadTransferSize"],
        "commit_dwMaxPayloadTransferSize": neg["commit"]["dwMaxPayloadTransferSize"],
        "camera_alt_for_request": min((a for a, b in alts.items() if b >= neg["commit"]["dwMaxPayloadTransferSize"]), default=None),
        "dwMaxVideoFrameSize": neg["commit"]["dwMaxVideoFrameSize"], "wCompQuality": neg["commit"]["wCompQuality"],
        "stream_start_error": iso["stream_start_error"], "stream_start_error_name": iso["stream_start_error_name"],
        "seconds": req["seconds"], "frames": len(frames), "fps_delivered": m["fps_from_arrivals"],
        "fps_frames_over_seconds": round(len(frames) / req["seconds"], 3),
        "jpeg_soi_eoi_ok": soi, "jpeg_decoded_ok": dec_ok, "jpeg_decode_failed": dec_fail, "jpegs_saved": len(jp),
        "decode_fail_examples": fail_examples,
        "pct_valid_decoded": round(100 * dec_ok / len(frames), 2) if frames else None,
        "seq_gaps": m["seq_gaps"], "error_payloads": m["error_payloads"], "frames_closed_by_eof": m["frames_closed_by_eof"],
        "camera_skipped_frames_by_scr_stc": skips_stc, "camera_skipped_frames_by_pts": skips_pts,
        "host_gaps_gt_1p5_period": sum(1 for g in gaps if g > 1.5 * 1000 / fps),
        "max_host_gap_ms": round(max(gaps), 2) if gaps else None,
        "frames_smaller_than_half_median": sum(1 for s in sizes if med and s < 0.5 * med),
        "payload_bytes": {"min": min(sizes) if sizes else None, "median": med, "p99": pct(sizes, 99), "max": max(sizes) if sizes else None},
        "median_payload_over_capacity": round(med / cap, 3) if sizes and cap else None,
        "max_payload_over_capacity": round(max(sizes) / cap, 3) if sizes and cap else None,
        "payloads_per_frame_median": statistics.median([f["payload_count"] for f in frames]) if frames else None,
        "controls": res["controls"], "command": res["command"], "utc_started": res["utc_started"],
    })
    if delete:
        for p in jp:
            p.unlink()
        out["jpegs_deleted"] = len(jp)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--delete-jpegs", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    runs = []
    for r in a.raw:
        for d in sorted(Path(r).iterdir()):
            if d.is_dir() and a.only in d.name and ((d / "result.json").exists() or (d / "stderr.log").exists()):
                runs.append(analyse(d, a.delete_jpegs))
    doc = {"test": "bw_alt_sweep", "label": a.label, "platform": "windows", "hostname": os.environ.get("COMPUTERNAME"),
           "camera": "Logitech C930e 046d:0843 on WinUSB (libuvc d07de4fa + patch 0001, libusb 1.0.30)",
           "analyzer_command": " ".join(sys.argv), "runs": runs}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, indent=1))
    for r in runs:
        if "error" in r:
            print(r["name"], "ERROR", r["error"], (r.get("stderr") or "")[-200:])
            continue
        pb = r["payload_bytes"]
        print(f'{r["name"]:24s} alt={r["chosen_alt"]:>2} cap={r["capacity_bytes_per_frame"]} req={r["commit_dwMaxPayloadTransferSize"]} '
              f'err={r["stream_start_error"]} fr={r["frames"]} fps={r["fps_delivered"]:.2f} dec={r["jpeg_decoded_ok"]}/{r["frames"]} soi={r["jpeg_soi_eoi_ok"]} '
              f'gaps={r["seq_gaps"]} errp={r["error_payloads"]} skipSTC={r["camera_skipped_frames_by_scr_stc"]} skipPTS={r["camera_skipped_frames_by_pts"]} '
              f'late={r["host_gaps_gt_1p5_period"]} small={r["frames_smaller_than_half_median"]} med={pb["median"]} p99={pb["p99"]} max={pb["max"]} max/cap={r["max_payload_over_capacity"]}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
