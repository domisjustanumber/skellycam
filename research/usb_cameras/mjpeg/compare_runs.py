# /// script
# requires-python = ">=3.10"
# ///
"""Compare two or more aggregated MJPEG matrix roots cell by cell (same backend, cell label, camera).

  uv run --script research/usb_cameras/mjpeg/compare_runs.py --old <root> [--old <root> ...] --new <root> --out <file.json>

Each root must hold a table.json from aggregate.py --root <root>. Cell labels are matched after normalising the
camera set (the 2026-10-25 'all cameras' sets included the Kiyo; the 2026-10-27 rerun excluded it), so multi-camera
cells are matched only when the camera set is identical. Per matched row: fps, valid %, payload p50, process CPU %,
luma p50, exposure, and whether the dominant JPEG header fingerprint is identical (same camera encoder tables on both
days). Writes --out (JSON) and prints a table. Opens no camera.
"""
import argparse
import json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--old", action="append", required=True)
ap.add_argument("--new", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()


def load(root):
    t = json.loads((Path(root) / "table.json").read_text())
    rows = {}
    for r in t["rows"]:
        if r.get("failed"):
            continue
        key = (r["test"], r["label"].replace("+kiyo", ""), r["cam"])
        if "kiyo" in r["label"] and "+" in r["label"]:
            continue  # 4-camera sets with the Kiyo are not comparable to the 3-camera rerun
        rows[key] = r
    return t, rows


old_rows = {}
for o in a.old:
    _, rr = load(o)
    old_rows.update(rr)
_, new_rows = load(a.new)
F = ("fps", "valid_jpeg_pct", "payload_p50", "cpu_pct_process", "luma_p50", "exposure", "native", "fingerprint_dominant",
     "arrival_minus_os_ms_median", "codec", "summary")
out = []
for k in sorted(set(old_rows) | set(new_rows), key=lambda x: tuple(str(i) for i in x)):
    o, n = old_rows.get(k), new_rows.get(k)
    if not (o and n):
        continue
    e = {"test": k[0], "label": k[1], "cam": k[2], "old": {f: o.get(f) for f in F}, "new": {f: n.get(f) for f in F}}
    e["same_dominant_fingerprint"] = (o.get("fingerprint_dominant") == n.get("fingerprint_dominant")) if (o.get("fingerprint_dominant") and n.get("fingerprint_dominant")) else None
    out.append(e)
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
Path(a.out).write_text(json.dumps({"command": "uv run --script research/usb_cameras/mjpeg/compare_runs.py " + " ".join(f"--old {x}" for x in a.old) + f" --new {a.new} --out {a.out}",
                                   "matched": out}, indent=1))
print(f"{'test':22} {'label':36} {'cam':7} {'fps o/n':>13} {'valid o/n':>11} {'p50B o/n':>15} {'cpu o/n':>11} {'luma o/n':>11} samefp")
for e in out:
    o, n = e["old"], e["new"]
    print(f"{e['test'][6:]:22} {e['label']:36} {str(e['cam']):7} {str(o['fps']):>6}/{str(n['fps']):<6} {str(o['valid_jpeg_pct']):>5}/{str(n['valid_jpeg_pct']):<5} "
          f"{str(o['payload_p50']):>7}/{str(n['payload_p50']):<7} {str(o['cpu_pct_process']):>5}/{str(n['cpu_pct_process']):<5} {str(o['luma_p50']):>5}/{str(n['luma_p50']):<5} {e['same_dominant_fingerprint']}")
print("wrote", a.out)
