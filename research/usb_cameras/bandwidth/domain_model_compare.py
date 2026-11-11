# /// script
# requires-python = ">=3.10"
# ///
"""Compare three HS periodic-admission models against the Gerald shared-hub observations (offline, no hardware).

Models, all for high-speed isochronous IN endpoints with bInterval=1 (every microframe), per bandwidth domain:
  usb2_spec : USB 2.0 sec. 5.11.3 transaction time (worst-case bit stuffing, Host_Delay=0), limit 80% of 125 us
              (same formula as hs_budget_model.py).
  intel_sw  : Linux xhci software bandwidth table used for Intel Panther Point (XHCI_SW_BW_CHECKING):
              blocks of 4 B, HS_OVERHEAD 26 blocks per packet, HS_BW_LIMIT 1607 blocks incl. 20% reserve
              (drivers/usb/host/xhci.h, xhci_check_bw_table in xhci.c; interval-0 path only).
  mtk_sw    : Linux xhci-mtk software scheduler: payload bytes per microframe <= HS_BW_BOUNDARY 6144
              (drivers/usb/host/xhci-mtk-sch.c), no per-packet overhead.
Inputs: results/windows/Gerald/bw_rerun_20261027_analysis/model_vs_observed_rerun.json (alt, packet, mult, outcome).
Also prints predictions for the camera placement seen on 2026-11-06 (C922 + generic share root port HS13).

  uv run --script research/usb_cameras/bandwidth/domain_model_compare.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GERALD = ROOT / "results" / "windows" / "Gerald"


def usb2_ns(packet: int, mult: int) -> float:
    return mult * (38 * 8 * 2.083 + 2.083 * math.floor(3.167 + 1.1667 * 8 * packet))


def intel_blocks(eps: list[tuple[int, int]]) -> int:
    esit = sum(p * m for p, m in eps)
    npk = sum(m for _, m in eps)
    return math.ceil(esit / 4) + npk * 26 + math.ceil(20 * 1607 / 100)


def verdicts(eps: list[tuple[int, int]]) -> dict:
    ns = sum(usb2_ns(p, m) for p, m in eps)
    blocks = intel_blocks(eps)
    payload = sum(p * m for p, m in eps)
    return {"usb2_pct_microframe": round(100 * ns / 125_000, 1), "usb2_fit": ns <= 100_000,
            "intel_sw_blocks": blocks, "intel_sw_fit": blocks <= 1607,
            "mtk_payload_B": payload, "mtk_fit": payload <= 6144}


# alt tables read from results/windows/Gerald/bw_topology_rerun_20261027/topology_idle_0307Z.json
C922 = {1: (192, 1), 2: (384, 1), 3: (512, 1), 4: (640, 1), 5: (800, 1), 6: (944, 1), 7: (640, 2), 8: (800, 2),
        9: (992, 2), 10: (896, 3), 11: (1020, 3)}
C930E = dict(C922) | {11: (1024, 3)}
GENERIC = {1: (1023, 3)}
# alt chosen by usbvideo per mode, results/windows/Gerald/bw_concurrency_rerun_20261027/r02_*.json
C922_MODE_ALT = {"MJPG 640x480@30": 4, "MJPG 1280x720@30": 9, "MJPG 1280x720@60": 11, "MJPG 1920x1080@30": 11,
                 "MJPG 1920x1080@5": 5, "YUY2 640x480@30": 10, "YUY2 320x240@30": 5}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "agent_reports" / "plan_20261106" / "bandwidth_domain_model_compare.json")
    a = ap.parse_args()
    src = GERALD / "bw_rerun_20261027_analysis" / "model_vs_observed_rerun.json"
    rows = []
    for r in json.loads(src.read_text())["rows"]:
        eps = [(c["packet"], c["mult"]) for c in r["cameras"]]
        v = verdicts(eps)
        v.update(label=r["label"], alts=[f"{c['pid']}:alt{c['alt']}" for c in r["cameras"]], observed_fit=r["observed_both_streamed"])
        rows.append(v)
    agree = {m: sum(r[f"{m}_fit"] == r["observed_fit"] for r in rows) for m in ("usb2", "intel_sw", "mtk")}
    # cross-root-port observation (r08): C922 alt11 + C930e alt11 both streamed on different root ports of 8086:7A60
    cross = verdicts([C922[11], C930E[11]]) | {"label": "c922_alt11 + c930e_alt11 IF they were one domain (observed: both streamed on different root ports)"}
    today = [verdicts([C922[alt], GENERIC[1]]) | {"label": f"2026-11-06 HS13: C922 {mode} (alt {alt}) + generic (alt 1)"}
             for mode, alt in C922_MODE_ALT.items()]
    out = {"test": "bandwidth_domain_model_compare", "input": str(src.relative_to(ROOT)), "n": len(rows), "agree": agree,
           "rows": rows, "controller_wide_counterfactual": cross, "predictions_20261106_layout": today}
    for r in rows:
        print(f"{r['label']:42s} usb2 {r['usb2_pct_microframe']:5.1f}% {r['usb2_fit']!s:5}  intel {r['intel_sw_blocks']:4d} {r['intel_sw_fit']!s:5}  "
              f"mtk {r['mtk_payload_B']:4d} {r['mtk_fit']!s:5}  observed {r['observed_fit']}")
    print("agree:", agree, "of", len(rows))
    print("counterfactual one-domain:", cross)
    for t in today:
        print(t)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
