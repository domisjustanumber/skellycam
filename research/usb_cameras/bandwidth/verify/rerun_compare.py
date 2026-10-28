# /// script
# requires-python = ">=3.10"
# ///
"""Compare a re-run of run_concurrency.py batches against the earlier batches, combo by combo (offline).

  uv run --script research/usb_cameras/bandwidth/verify/rerun_compare.py --old-dir OLD --new-dir NEW \
      --pair b02_c922_alt_by_mode=r02_c922_alt_by_mode [--pair ...] [--luma frame_luma.json --raw-root RAW] --out OUT.json

For every combo label present in both batches and every camera in it: selected alt (open-pipe match), streamed or
failed (stage + HRESULT), steady fps, steady bytes/s, max sample bytes, and (if --luma is given) the mean luma of the
re-run frames saved under RAW/<new batch>/<label>/cam<k>. Flags: alt_changed, outcome_changed, fps_changed (>3 %
relative), bytes_changed (>25 % relative). Earlier runs had no luma record, so byte changes can only be attributed
to the scene when the re-run luma is reported alongside.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cams_of(combo: dict) -> list[dict]:
    mf = combo.get("mf")
    if not isinstance(mf, dict):
        return []
    out = []
    pipes = combo.get("pipes_while_streaming") if isinstance(combo.get("pipes_while_streaming"), list) else []
    for k, c in enumerate(mf.get("cameras", [])):
        pid = c["spec"].split("pid_")[1][:4]
        pc = next((p for p in pipes if p["idProduct"] == pid), None)
        alts = [m["bAlternateSetting"] for m in pc["matched_alt_settings"]] if pc else None
        out.append({"k": k, "spec": c["spec"], "pid": pid, "streamed": c["streamed"], "failed_stage": c["failed_stage"],
                    "error_hr": c["error_hr"], "fps": round(c["steady_fps"], 2), "Bps": round(c["steady_bytes_per_s"]),
                    "max_sample_bytes": c["max_sample_bytes"], "alt": alts,
                    "exposure_prev": c.get("exposure", {}).get("prev"), "exposure_prev_flags": c.get("exposure", {}).get("prev_flags"),
                    "exposure_set_ok": c.get("exposure", {}).get("set_ok")})
    return out


def rel(a, b):
    return abs(a - b) / b if b else (0.0 if a == b else float("inf"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-dir", type=Path, required=True)
    ap.add_argument("--new-dir", type=Path, required=True)
    ap.add_argument("--pair", action="append", required=True, help="OLDBATCH=NEWBATCH")
    ap.add_argument("--luma", type=Path)
    ap.add_argument("--raw-root", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    luma = {}
    if a.luma:
        for r in json.loads(a.luma.read_text())["dirs"]:
            luma[Path(r["rel"]).as_posix()] = r["mean_luma"]
    rows = []
    for pr in a.pair:
        ob, nb = pr.split("=")
        od = json.loads((a.old_dir / f"{ob}.json").read_text())
        nd = json.loads((a.new_dir / f"{nb}.json").read_text())
        old = {c["label"]: c for c in od["combos"]}
        for nc in nd["combos"]:
            oc = old.get(nc["label"])
            if oc is None or "mf" not in nc or "mf" not in oc:
                rows.append({"old_batch": ob, "new_batch": nb, "label": nc["label"], "note": "no earlier counterpart"})
                continue
            ocs, ncs = cams_of(oc), cams_of(nc)
            for n in ncs:
                o = next((x for x in ocs if x["spec"] == n["spec"]), None)
                if o is None:
                    continue
                row = {"old_batch": ob, "new_batch": nb, "label": nc["label"], "spec": n["spec"], "old": o, "new": n,
                       "alt_changed": o["alt"] != n["alt"],
                       "outcome_changed": (o["streamed"], o["error_hr"]) != (n["streamed"], n["error_hr"]),
                       "fps_changed": bool(o["streamed"] and n["streamed"] and rel(n["fps"], o["fps"]) > 0.03),
                       "bytes_changed": bool(o["streamed"] and n["streamed"] and rel(n["Bps"], o["Bps"]) > 0.25),
                       "new_mean_luma": luma.get(f"{nb}/{nc['label']}/cam{n['k']}")}
                rows.append(row)
    flagged = [r for r in rows if any(r.get(k) for k in ("alt_changed", "outcome_changed", "fps_changed", "bytes_changed"))]
    summ = {"cameras_compared": sum(1 for r in rows if "spec" in r),
            "alt_changed": sum(1 for r in rows if r.get("alt_changed")),
            "outcome_changed": sum(1 for r in rows if r.get("outcome_changed")),
            "fps_changed": sum(1 for r in rows if r.get("fps_changed")),
            "bytes_changed": sum(1 for r in rows if r.get("bytes_changed"))}
    for r in rows:
        if "spec" not in r:
            print(f"{r['new_batch']:36s} {r['label']:40s} {r['note']}")
            continue
        o, n = r["old"], r["new"]
        fl = ",".join(k.replace("_changed", "") for k in ("alt_changed", "outcome_changed", "fps_changed", "bytes_changed") if r[k])
        print(f"{r['new_batch'][:30]:30s} {r['label'][:38]:38s} {n['pid']} alt {o['alt']}->{n['alt']} "
              f"{'OK' if o['streamed'] else o['error_hr']}->{'OK' if n['streamed'] else n['error_hr']} "
              f"fps {o['fps']}->{n['fps']} MB/s {o['Bps']/1e6:.2f}->{n['Bps']/1e6:.2f} luma {r['new_mean_luma']} {fl}")
    print(json.dumps(summ))
    if a.out:
        a.out.write_text(json.dumps({"tool": "rerun_compare", "command": " ".join(sys.argv), "summary": summ,
                                     "flagged": flagged, "rows": rows}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
