# /// script
# requires-python = ">=3.10"
# ///
"""Goal 3 phase 2: combine every results/windows/<host>/phase2_bw_alt/sweep_*.json into one table, test the model
"delivered fps = fps / ceil(frame_bytes / capacity)" and estimate cameras per USB 2.0 high-speed link (ESTIMATE).

  uv run --script research/usb_cameras/bandwidth/alt_sweep_summary.py [--host Gerald]
Writes phase2_bw_alt/summary.json.
"""
from __future__ import annotations
import argparse, importlib.util, json, math, socket
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("hs", HERE / "hs_budget_model.py")
hs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hs)
C930E = {1: (192, 1), 2: (384, 1), 3: (512, 1), 4: (640, 1), 5: (800, 1), 6: (944, 1), 7: (640, 2), 8: (800, 2),
         9: (992, 2), 10: (896, 3), 11: (1024, 3)}
HDR = 12  # C930e UVC payload header bytes per microframe (PTS+SCR present on every payload)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=socket.gethostname())
    a = ap.parse_args()
    base = HERE.parent / "results" / "windows" / a.host / "phase2_bw_alt"
    rows = []
    for f in sorted(base.glob("sweep_*.json")):
        d = json.loads(f.read_text())
        for r in d["runs"]:
            if "error" in r or not r.get("alt_bytes_per_microframe"):
                continue
            alt, fps = r["chosen_alt"], int(r["mode"].split("@")[1])
            cap_eff = (r["alt_bytes_per_microframe"] - HDR) * 8000 / fps
            med = r["payload_bytes"]["median"]
            k = math.ceil(med / cap_eff)
            rows.append({"file": f.name, "run": r["name"], "mode": r["mode"], "alt": alt,
                         "capacity_bytes_per_frame": r["capacity_bytes_per_frame"], "capacity_minus_headers": round(cap_eff),
                         "median_bytes": med, "max_bytes": r["payload_bytes"]["max"],
                         "median_over_capacity": round(med / cap_eff, 3), "max_over_capacity": round(r["payload_bytes"]["max"] / cap_eff, 3),
                         "fps_delivered": r["fps_delivered"], "fps_model_fps_over_ceil": round(fps / k, 2),
                         "camera_skipped_frames": r["camera_skipped_frames_by_scr_stc"], "frames": r["frames"],
                         "pct_valid_decoded": r["pct_valid_decoded"], "seq_gaps": r["seq_gaps"], "error_payloads": r["error_payloads"],
                         "commit_dwMaxPayloadTransferSize": r["commit_dwMaxPayloadTransferSize"],
                         "camera_alt_for_request": r["camera_alt_for_request"], "scene": d.get("label")})
    # model check: runs at full rate vs runs at reduced rate
    ok = [x for x in rows if abs(x["fps_delivered"] - x["fps_model_fps_over_ceil"]) / x["fps_model_fps_over_ceil"] < 0.06]
    full = [x for x in rows if x["median_over_capacity"] <= 1]
    clean = sorted(x["max_over_capacity"] for x in full if x["camera_skipped_frames"] == 0)
    skipping = sorted(x["median_over_capacity"] for x in full if x["camera_skipped_frames"] > 0)
    cost = {alt: round(m * hs.t_iso_in_ns(b)) for alt, (b, m) in C930E.items()}
    doc = {"test": "bw_alt_sweep_summary", "host": a.host, "runs": rows,
           "fps_step_model": {"rule": "fps_delivered ~= fps / ceil(median_frame_bytes / ((alt_bytes - 12) * 8000 / fps))",
                              "runs": len(rows), "runs_within_6pct": len(ok),
                              "exceptions": [(x["run"], x["fps_delivered"], x["fps_model_fps_over_ceil"]) for x in rows if x not in ok]},
           "skip_threshold": {"largest_max_over_capacity_with_zero_skips": clean[-1] if clean else None,
                              "median_over_capacity_of_runs_with_skips_but_full_rate": skipping},
           "alt_cost_ns_usb2_5_11_3_model": cost, "periodic_limit_ns": hs.PERIODIC_LIMIT_NS,
           "cameras_per_link_if_only_this_alt": {alt: int(hs.PERIODIC_LIMIT_NS // c) for alt, c in cost.items()}}
    (base / "summary.json").write_text(json.dumps(doc, indent=1))
    for x in rows:
        print(f'{x["mode"]:20s} alt={x["alt"]:>2} cap={x["capacity_minus_headers"]:>6} med={x["median_bytes"]:>8} med/cap={x["median_over_capacity"]:<6} '
              f'max/cap={x["max_over_capacity"]:<6} fps={x["fps_delivered"]:<6} model={x["fps_model_fps_over_ceil"]:<5} skips={x["camera_skipped_frames"]:<4} '
              f'valid={x["pct_valid_decoded"]} {x["run"]}')
    print(json.dumps({k: doc[k] for k in ("fps_step_model", "skip_threshold", "alt_cost_ns_usb2_5_11_3_model", "cameras_per_link_if_only_this_alt")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
