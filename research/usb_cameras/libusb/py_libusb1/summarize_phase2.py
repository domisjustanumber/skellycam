# /// script
# requires-python = ">=3.10"
# ///
"""Aggregate results/windows/<host>/phase2_python_libusb/*/result.json (+ analyze_frames.json, frames.jsonl PTS deltas)
into summary.json.  uv run --script research/usb_cameras/libusb/py_libusb1/summarize_phase2.py [RESULT_DIR]"""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "results/windows/Gerald/phase2_python_libusb"
rows = []
for d in sorted(p for p in root.iterdir() if (p / "result.json").exists() and (p / "frames.jsonl").exists()):
    r = json.loads((d / "result.json").read_text())
    m, i = r.get("measurements", {}), r.get("iso", {})
    fr = [json.loads(x) for x in (d / "frames.jsonl").read_text().splitlines() if x.strip()]
    pts = [x["uvc_pts"] for x in fr]
    hist: dict = {}
    for a, b in zip(pts[1:], pts[2:]):  # skip the first delta (stream start-up)
        if a is None or b is None:
            continue
        k = round(((b - a) % 2**32) / 997222)  # C930e PTS step per 30 fps frame (phase 1)
        hist[str(k)] = hist.get(str(k), 0) + 1
    row = {"run": d.name, "command": r.get("command"), "width_height": [fr[0]["payload_bytes"] and None][0],
           "altsetting": i.get("altsetting"), "bytes_per_microframe": i.get("bytes_per_packet"),
           "packets_per_transfer": i.get("packets_per_transfer"), "transfers": i.get("transfers"),
           "frames": m.get("frames"), "pillow_full_decode_ok": m.get("pillow_full_decode_ok"),
           "fps_from_arrivals": m.get("fps_from_arrivals"), "mean_frame_bytes": m.get("mean_frame_bytes"),
           "cpu_fraction_of_one_core": m.get("cpu_fraction_of_one_core"), "callback_mean_us": m.get("callback_mean_us"),
           "iso_packets_per_s": m.get("iso_packets_per_s"), "transfer_errors": m.get("transfer_errors"),
           "iso_packet_errors": m.get("iso_packet_errors"), "uvc_error_payloads": m.get("uvc_error_payloads"),
           "frames_with_pts": sum(p is not None for p in pts), "frames_with_scr": sum(x["uvc_scr_stc"] is not None for x in fr),
           "pts_delta_periods_hist": hist, "wCompQuality": r.get("negotiation", {}).get("probe", {}).get("wCompQuality")}
    row.pop("width_height")
    af = d / "analyze_frames.json"
    if af.exists():
        c = json.loads(af.read_text())["cameras"][0]
        s = c["sources"]
        row["periodic_fit_residual_rms_us"] = {k: v["periodic_fit"]["residual_rms_us"] for k, v in s.items() if "periodic_fit" in v}
        row["stc_minus_pts_ms_median"] = c["device_clock"]["stc_minus_pts_ms"]["median"]
    rows.append(row)
(root / "summary.json").write_text(json.dumps({"test": "py_libusb1_phase2_summary", "source_dir": str(root), "runs": rows}, indent=1))
for x in rows:
    print(f"{x['run']:24s} alt {x['altsetting']:>2} {x['bytes_per_microframe']:>4}B ppt {x['packets_per_transfer']:>3}x{x['transfers']} "
          f"frames {x['frames']} dec {x['pillow_full_decode_ok']} fps {x['fps_from_arrivals']:.2f} cpu {x['cpu_fraction_of_one_core']:.3f} "
          f"pts {x['pts_delta_periods_hist']}")
