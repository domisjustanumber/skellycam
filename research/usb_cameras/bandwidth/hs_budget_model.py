# /// script
# requires-python = ">=3.10"
# ///
"""USB 2.0 high-speed periodic-budget model vs. observed shared-hub results (goal 3, offline, no hardware).

Model (USB 2.0 spec rev 2.0, sec. 5.11.3 "Calculating Bus Transaction Times", HS isochronous IN):
    t_ns(n) = 38*8*2.083 + 2.083*floor(3.167 + BitStuffTime(n)),  BitStuffTime(n) = 1.1667*8*n (worst case)
    (Host_Delay is implementation specific and taken as 0 here.)
Sec. 5.6.4: high-speed periodic transfers may use at most 80% of a 125 us microframe = 100 000 ns.
An alt setting with wMaxPacketSize base b and m transactions/microframe costs m * t_ns(b).

For every 2-camera combo in results/windows/<host>/bw_concurrency/b05*,b07* whose cameras share one USB 2.0
hub upstream link, this prints the alt setting of each camera (observed open pipe when it streamed; else the
alt the same camera+mode selected when run alone, from b03/b06), the model's predicted microframe use, and
whether both cameras streamed.

  uv run --script research/usb_cameras/bandwidth/hs_budget_model.py [--host Gerald]
      [--concurrency-dir DIR --solo-glob 'r0*.json' --pair-glob 'r05*.json' ... --topology FILE --out FILE] (2026-10-27)
Writes results/windows/<host>/bw_budget_model/model_vs_observed.json
"""
from __future__ import annotations

import argparse
import json
import math
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MICROFRAME_NS = 125_000
PERIODIC_LIMIT_NS = 0.8 * MICROFRAME_NS


def t_iso_in_ns(n: int) -> float:
    return 38 * 8 * 2.083 + 2.083 * math.floor(3.167 + 1.1667 * 8 * n)


def alt_cost_ns(cam_topo: dict, alt: int) -> tuple[float, int, int]:
    for vs in cam_topo["uvc"]["vs_interfaces"].values():
        for a in vs["alt_settings"]:
            if a["bAlternateSetting"] == alt and a["endpoints"]:
                e = a["endpoints"][0]
                return e["transactions_per_microframe"] * t_iso_in_ns(e["base_packet_bytes"]), e["base_packet_bytes"], e["transactions_per_microframe"]
    return 0.0, 0, 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=socket.gethostname())
    ap.add_argument("--concurrency-dir", type=Path)
    ap.add_argument("--solo-glob", action="append", help="default b0*.json")
    ap.add_argument("--pair-glob", action="append", help="default b0[57]*.json")
    ap.add_argument("--topology", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    base = ROOT / "results" / "windows" / a.host
    topo = json.loads((a.topology or base / "bw_topology" / "topology.json").read_text())
    cdir = a.concurrency_dir or base / "bw_concurrency"
    solo_files = sorted({f for g in (a.solo_glob or ["b0*.json"]) for f in cdir.glob(g)})
    pair_files = sorted({f for g in (a.pair_glob or ["b0[57]*.json"]) for f in cdir.glob(g)})
    by_pid = {c["idProduct"]: c for c in topo["cameras"]}
    # alt chosen when each camera+mode ran alone
    solo: dict[tuple[str, str], int] = {}
    for f in solo_files:
        d = json.loads(f.read_text())
        for combo in d.get("combos", []):
            if len(combo.get("specs", [])) != 1 or not isinstance(combo.get("pipes_while_streaming"), list):
                continue
            spec = combo["specs"][0]
            pid = spec.split("pid_")[1][:4]
            for pc in combo["pipes_while_streaming"]:
                if pc["idProduct"] == pid and len(pc["matched_alt_settings"]) == 1:
                    solo[(pid, spec.split(":", 1)[1])] = pc["matched_alt_settings"][0]["bAlternateSetting"]
    rows = []
    for f in pair_files:
        d = json.loads(f.read_text())
        for combo in d["combos"]:
            if "mf" not in combo:
                continue
            cams = combo["mf"]["cameras"]
            shared = [c for c in cams if c["spec"].split("pid_")[1][:4] in ("0843", "4a55")]  # same 05e3:0610 hub
            if len(shared) != 2:
                continue
            total, parts = 0.0, []
            for c in shared:
                pid = c["spec"].split("pid_")[1][:4]
                mode = c["spec"].split(":", 1)[1]
                alt = None
                for pc in combo["pipes_while_streaming"] if isinstance(combo["pipes_while_streaming"], list) else []:
                    if pc["idProduct"] == pid and len(pc["matched_alt_settings"]) == 1:
                        alt = pc["matched_alt_settings"][0]["bAlternateSetting"]
                src = "observed"
                if alt is None:
                    alt, src = solo.get((pid, mode)), "solo-run"
                if alt is None:  # camera with a single streaming alt setting (4a55: alt 1 only)
                    nz = [x["bAlternateSetting"] for vs in by_pid[pid]["uvc"]["vs_interfaces"].values()
                          for x in vs["alt_settings"] if x["endpoints"]]
                    if len(nz) == 1:
                        alt, src = nz[0], "only-streaming-alt"
                cost, base_b, mult = alt_cost_ns(by_pid[pid], alt) if alt is not None else (0.0, 0, 0)
                total += cost
                parts.append({"pid": pid, "mode": mode, "alt": alt, "alt_source": src, "packet": base_b, "mult": mult,
                              "cost_ns": round(cost), "streamed": c["streamed"], "error_hr": c["error_hr"]})
            pred_fit = total <= PERIODIC_LIMIT_NS
            obs_fit = all(p["streamed"] for p in parts)
            rows.append({"file": f.name, "label": combo["label"], "cameras": parts, "total_ns": round(total),
                         "pct_of_microframe": round(100 * total / MICROFRAME_NS, 1), "predicted_fit": pred_fit,
                         "observed_both_streamed": obs_fit, "agree": pred_fit == obs_fit})
    for r in rows:
        print(f"{r['label']:36s} {r['pct_of_microframe']:6.1f}%  pred_fit={r['predicted_fit']!s:5} observed={r['observed_both_streamed']!s:5} "
              f"{'AGREE' if r['agree'] else 'DISAGREE'}  " + " + ".join(f"{p['pid']}:alt{p['alt']}({p['mult']}x{p['packet']})" for p in r["cameras"]))
    out = a.out or base / "bw_budget_model" / "model_vs_observed.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"test": "bw_budget_model", "host": a.host, "limit_ns": PERIODIC_LIMIT_NS,
                               "formula": "USB2.0 5.11.3 HS iso IN, worst-case bit stuffing, Host_Delay=0",
                               "per_transaction_ns": {n: round(t_iso_in_ns(n)) for n in (192, 384, 512, 640, 800, 896, 944, 992, 1020, 1023, 1024)},
                               "inputs": [str(f) for f in pair_files], "rows": rows, "n_agree": sum(r["agree"] for r in rows), "n": len(rows)}, indent=1))
    print(f"agree {sum(r['agree'] for r in rows)}/{len(rows)}; wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
