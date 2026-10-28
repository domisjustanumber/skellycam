# /// script
# requires-python = ">=3.10"
# ///
"""Diff identity snapshots (any platform) into a per-identifier stability table.

    uv run --script research/usb_cameras/naming/identity_diff.py SNAP_A.json SNAP_B.json [SNAP_C.json ...] [--out OUT.json]

Snapshots are the `naming.snapshot` JSON files written by
  windows: naming/win_identity_dump.py --label <name>      (or naming/win_stability_workflow.ps1)
  linux:   naming/linux_identity.py --label <name>
  macos:   naming/macos_identity.py --label <name>
Each has `cameras: [ {field: value, ...} ]`. Cameras are matched across snapshots by
  1. (vid, pid, usb_serial) when the serial is non-empty, else
  2. (vid, pid) when that pair is unique inside BOTH snapshots, else
  3. --match-field FIELD (e.g. a field you know is stable) - otherwise reported as unmatched.
For every matched camera and every field, the table says whether the value was identical in all snapshots.
Comparison is exact; a change that differs only by letter case is flagged `case_only`.
Fields in VOLATILE are expected to change (e.g. USB device address) and are reported but marked volatile.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

VOLATILE = {"usb_device_address", "devnum", "video_node", "opencv_index", "last_arrival"}


def _match_keys(cams: list[dict], extra: str | None) -> dict:
    out = {}
    pairs = {}
    for c in cams:
        pairs.setdefault((c.get("vid"), c.get("pid")), []).append(c)
    for c in cams:
        if c.get("usb_serial"):
            k = ("serial", c.get("vid"), c.get("pid"), c["usb_serial"])
        elif len(pairs[(c.get("vid"), c.get("pid"))]) == 1:
            k = ("vidpid", c.get("vid"), c.get("pid"))
        elif extra and c.get(extra) is not None:
            k = ("field", extra, json.dumps(c.get(extra), sort_keys=True))
        else:
            k = ("unmatched", id(c))
        out[k] = c
    return out


def diff(snaps: list[dict], match_field: str | None = None) -> dict:
    keyed = [_match_keys(s["cameras"], match_field) for s in snaps]
    all_keys = []
    for k in keyed:
        for kk in k:
            if kk not in all_keys:
                all_keys.append(kk)
    rows = []
    for k in all_keys:
        present = [k in ks for ks in keyed]
        cams = [ks.get(k) for ks in keyed]
        base = next(c for c in cams if c is not None)
        label = f"{base.get('vid')}:{base.get('pid')} {base.get('usb_product') or base.get('product') or ''}".strip()
        fields = {}
        if all(present) and k[0] != "unmatched":
            names = []
            for c in cams:
                for f in c:
                    if f not in names:
                        names.append(f)
            for f in names:
                vals = [c.get(f) for c in cams]
                ser = [json.dumps(v, sort_keys=True) for v in vals]
                same = len(set(ser)) == 1
                case_only = (not same) and len({s.lower() for s in ser}) == 1
                fields[f] = dict(stable=same, case_only=case_only, volatile=f in VOLATILE,
                                 values=vals if not same else vals[0])
        rows.append(dict(camera=label, match=list(k[:3]) if k[0] != "unmatched" else ["unmatched"],
                         present_in=[s.get("label") for s, p in zip(snaps, present) if p], fields=fields))
    return dict(test="naming.identity_diff", snapshots=[dict(label=s.get("label"), platform=s.get("platform"),
                                                             hostname=s.get("hostname"), utc_started=s.get("utc_started"))
                                                        for s in snaps], cameras=rows)


def print_table(res: dict) -> None:
    labels = [s["label"] for s in res["snapshots"]]
    print("snapshots:", " -> ".join(str(l) for l in labels))
    for r in res["cameras"]:
        print(f"\n== {r['camera']}  matched by {r['match']}  present in {r['present_in']}")
        for f, v in r["fields"].items():
            tag = "STABLE " if v["stable"] else ("CASE   " if v["case_only"] else "CHANGED")
            if v["volatile"] and not v["stable"]:
                tag += "(volatile)"
            shown = v["values"] if v["stable"] else " | ".join(str(x) for x in v["values"])
            print(f"  {tag:18s} {f:32s} {str(shown)[:160]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshots", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--match-field", default=None)
    a = ap.parse_args()
    if len(a.snapshots) < 2:
        ap.error("need at least two snapshots")
    snaps = [json.loads(p.read_text(encoding="utf-8")) for p in a.snapshots]
    res = diff(snaps, a.match_field)
    res["command"] = " ".join(sys.argv)
    res["inputs"] = [str(p) for p in a.snapshots]
    print_table(res)
    out = a.out or a.snapshots[-1].parent.parent / f"stability_{'__'.join(str(s.get('label')) for s in snaps)}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("\nwrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
