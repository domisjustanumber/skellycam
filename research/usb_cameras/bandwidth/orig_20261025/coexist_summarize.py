# /// script
# requires-python = ">=3.10"
# ///
"""Summarise coexist_hold.sh output (goal 3 phase 2) and compare with the hs_budget_model.py prediction.

  uv run --script research/usb_cameras/bandwidth/coexist_summarize.py RAWDIR --out RESULT.json
Per run: C930e (libuvc) stream start result, alt, fps, frames, valid JPEG; generic (MF) streamed?, steady fps,
late intervals, error; the open pipes of both devices seen by win_usb_topology.py --pipes-only during the overlap;
and the budget model: generic alt-1 cost (3 x 1023 B) + C930e alt cost vs the 100 us periodic limit.
"""
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("hs", HERE / "hs_budget_model.py")
hs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hs)
# C930e alt -> (base packet bytes, transactions per microframe), from its descriptors (results/.../verify_stream_default)
C930E = {1: (192, 1), 2: (384, 1), 3: (512, 1), 4: (640, 1), 5: (800, 1), 6: (944, 1), 7: (640, 2), 8: (800, 2),
         9: (992, 2), 10: (896, 3), 11: (1024, 3)}
GEN_COST = 3 * hs.t_iso_in_ns(1023)


def load(p: Path):
    try:
        return json.loads(p.read_text(errors="replace"))
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for d in sorted(Path(a.raw).iterdir()):
        if not d.is_dir() or not d.name.startswith("coexist_"):
            continue
        c = load(d / "c930e" / "result.json")
        g = load(d / "gen_mf.json")
        pipes = load(d / "pipes.json")
        gcam = (g.get("cameras") or [{}])[0] if isinstance(g, dict) else {}
        alt_req = c.get("requested", {}).get("alt") if isinstance(c, dict) else None
        cm = c.get("measurements", {}) if isinstance(c, dict) else {}
        piped = {}
        if isinstance(pipes, list):
            for dev in pipes:
                key = f'{dev["idVendor"]}:{dev["idProduct"]}'
                if key in ("046d:0843", "4c4a:4a55"):
                    piped[key] = {"hub": dev.get("hub"), "port": dev.get("port"),
                                  "iso_pipes": [p for p in dev.get("open_pipes", []) if p.get("type") == "isochronous"],
                                  "matched_alt_settings": dev.get("matched_alt_settings")}
        alt_model = alt_req if alt_req else 11
        b, m = C930E.get(alt_model, (0, 0))
        c_cost = m * hs.t_iso_in_ns(b)
        rows.append({
            "run": d.name, "utc_start": (d / "utc_start.txt").read_text().strip() if (d / "utc_start.txt").exists() else None,
            "c930e": {"requested_alt": alt_req, "chosen_alt": c.get("iso", {}).get("chosen_altsetting"),
                      "stream_start_error": c.get("iso", {}).get("stream_start_error"),
                      "stream_start_error_name": c.get("iso", {}).get("stream_start_error_name"),
                      "frames": cm.get("frames"), "seconds": c.get("requested", {}).get("seconds"),
                      "fps_from_arrivals": cm.get("fps_from_arrivals"), "jpeg_soi_eoi_ok": cm.get("jpeg_soi_eoi_ok"),
                      "seq_gaps": cm.get("seq_gaps"), "error_payloads": cm.get("error_payloads"),
                      "mean_frame_bytes": cm.get("mean_frame_bytes"),
                      "commit_dwMaxPayloadTransferSize": c.get("negotiation", {}).get("commit", {}).get("dwMaxPayloadTransferSize"),
                      "stderr_tail": (d / "c930e.stderr.log").read_text(errors="replace")[-300:] if (d / "c930e.stderr.log").exists() else None},
            "generic_mf": {k: gcam.get(k) for k in ("spec", "chosen_native_type", "streamed", "failed_stage", "error_hr", "error_msg",
                                                     "samples", "steady_fps", "steady_mean_sample_bytes", "late_intervals_gt_1p5x",
                                                     "max_gap_ms", "read_errors")},
            "open_pipes_during_overlap": piped,
            "model": {"generic_alt1_cost_ns": round(GEN_COST), "c930e_alt_cost_ns": round(c_cost),
                      "total_ns": round(GEN_COST + c_cost), "pct_of_125us_microframe": round(100 * (GEN_COST + c_cost) / 125000, 1),
                      "predicted_fit_80pct": GEN_COST + c_cost <= hs.PERIODIC_LIMIT_NS},
        })
    doc = {"test": "bw_coexist_libuvc_vs_mf", "hub": "Genesys 05e3:0610 USB 2.0 hub on Intel xHCI DEV_7A60 root port 13",
           "cameras": {"c930e": "046d:0843 WinUSB, libuvc uvc_capture_test --alt", "generic": "4c4a:4a55 usbvideo, MF mf_multi_open MJPG 1280x720@30"},
           "command": " ".join(sys.argv), "runs": rows}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, indent=1))
    for r in rows:
        c, g, mo = r["c930e"], r["generic_mf"], r["model"]
        print(f'{r["run"]:28s} c930e alt={c["requested_alt"]} err={c["stream_start_error"]} frames={c["frames"]} fps={c["fps_from_arrivals"]} | '
              f'gen streamed={g["streamed"]} fps={g["steady_fps"]} late={g["late_intervals_gt_1p5x"]} hr={g["error_hr"]} | '
              f'model {mo["total_ns"]} ns fit={mo["predicted_fit_80pct"]} | pipes {{{", ".join(k + ":" + str([p["wMaxPacketSize"] for p in v["iso_pipes"]]) for k, v in r["open_pipes_during_overlap"].items())}}}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
