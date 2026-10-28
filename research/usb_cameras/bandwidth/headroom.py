# /// script
# requires-python = ">=3.10"
# ///
"""Goal 3 offline analysis: reserved vs. used isochronous bandwidth per camera+mode (Windows measurements).

For every single-camera run in results/windows/<host>/bw_concurrency/b0*.json whose open pipe identifies exactly one
alt setting (high-speed cameras), report:
  reserved   = alt bytes/microframe * 8000           (what usbvideo.sys reserved, B/s)
  used       = measured mean payload bytes/s (MF samples = whole frames; MJPEG = compressed size)
  ratio      = reserved / used
  bus_pct    = microframe time of the reserved alt (USB 2.0 sec. 5.11.3 model, see hs_budget_model.py)
  min_alt_xN = smallest alt of the same camera whose bytes/microframe >= N * (peak frame bytes * fps / 8000), N = 1, 1.5, 2
  cams_per_port_xN = floor(80% / bus_pct(min_alt_xN)) -- cameras of this kind+mode per HS root port if that alt were used
The xN columns are the HEADROOM a bandwidth override could recover; whether the camera tolerates the smaller alt is NOT
tested here (needs libusb/WinUSB: phase 2, or bandwidth/libuvc_forced_alt on Linux/macOS).

  uv run --script research/usb_cameras/bandwidth/headroom.py [--host Gerald]
      [--concurrency-dir DIR --glob 'r0*.json' ... --topology FILE --out FILE]   (2026-10-27: re-run inputs/outputs)
Writes results/windows/<host>/bw_headroom/headroom.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import socket
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("m", HERE / "hs_budget_model.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=socket.gethostname())
    ap.add_argument("--concurrency-dir", type=Path)
    ap.add_argument("--glob", action="append", help="file globs in the concurrency dir (default b0*.json)")
    ap.add_argument("--topology", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    base = HERE.parent / "results" / "windows" / a.host
    topo = json.loads((a.topology or base / "bw_topology" / "topology.json").read_text())
    cdir = a.concurrency_dir or base / "bw_concurrency"
    files = sorted({f for g in (a.glob or ["b0*.json"]) for f in cdir.glob(g)})
    by_pid = {c["idProduct"]: c for c in topo["cameras"]}
    rows, seen = [], set()
    for f in files:
        d = json.loads(f.read_text())
        for combo in d.get("combos", []):
            if len(combo.get("specs", [])) != 1 or not isinstance(combo.get("pipes_while_streaming"), list):
                continue
            cam = combo["mf"]["cameras"][0]
            if not cam["streamed"]:
                continue
            pid = cam["spec"].split("pid_")[1][:4]
            mode = cam["spec"].split(":", 1)[1]
            pc = next((p for p in combo["pipes_while_streaming"] if p["idProduct"] == pid), None)
            if not pc or len(pc["matched_alt_settings"]) != 1 or (pid, mode) in seen:
                continue
            seen.add((pid, mode))
            alt = pc["matched_alt_settings"][0]["bAlternateSetting"]
            t = by_pid[pid]
            alts = [x for vs in t["uvc"]["vs_interfaces"].values() for x in vs["alt_settings"] if x["endpoints"]]
            bpi = {x["bAlternateSetting"]: x["endpoints"][0]["bytes_per_interval"] for x in alts}
            reserved = bpi[alt] * 8000
            used = cam["steady_bytes_per_s"]
            fps = cam["steady_fps"]
            peak_rate = cam["max_sample_bytes"] * fps  # B/s if every frame were the largest one seen
            row = {"camera": t.get("product"), "pid": pid, "mode": mode, "file": f.name, "alt": alt,
                   "alt_bytes_per_microframe": bpi[alt], "reserved_Bps": reserved, "used_Bps": round(used),
                   "fps": round(fps, 2), "max_frame_bytes": cam["max_sample_bytes"],
                   "ratio_reserved_over_used": round(reserved / used, 2) if used else None,
                   "bus_pct_reserved": round(100 * m.alt_cost_ns(t, alt)[0] / m.MICROFRAME_NS, 1)}
            for n in (1, 1.5, 2):
                need = n * peak_rate / 8000
                cand = sorted((b, k) for k, b in bpi.items() if b >= need)
                if cand:
                    b, k = cand[0]
                    pct = 100 * m.alt_cost_ns(t, k)[0] / m.MICROFRAME_NS
                    row[f"min_alt_x{n}"] = k
                    row[f"min_alt_x{n}_bytes"] = b
                    row[f"min_alt_x{n}_bus_pct"] = round(pct, 1)
                    row[f"cams_per_port_x{n}"] = math.floor(80 / pct) if pct else None
                else:
                    row[f"min_alt_x{n}"] = None
            row["cams_per_port_as_reserved"] = math.floor(80 / row["bus_pct_reserved"]) if row["bus_pct_reserved"] else None
            rows.append(row)
    rows.sort(key=lambda r: (r["pid"], r["mode"]))
    print(f"{'camera':24s} {'mode':18s} alt  resv MB/s used MB/s ratio bus%  minalt(x1/x1.5/x2) cams/port(resv|x1.5)")
    for r in rows:
        print(f"{(r['camera'] or '')[:24]:24s} {r['mode']:18s} {r['alt']:3d} {r['reserved_Bps']/1e6:9.2f} {r['used_Bps']/1e6:9.2f} "
              f"{r['ratio_reserved_over_used'] or 0:5.1f} {r['bus_pct_reserved']:5.1f}  "
              f"{r.get('min_alt_x1')}/{r.get('min_alt_x1.5')}/{r.get('min_alt_x2')}            {r['cams_per_port_as_reserved']}|{r.get('cams_per_port_x1.5')}")
    out = a.out or base / "bw_headroom" / "headroom.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"test": "bw_headroom", "host": a.host, "inputs": [str(f) for f in files],
                                "topology": str(a.topology or base / "bw_topology" / "topology.json"), "rows": rows}, indent=1))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
