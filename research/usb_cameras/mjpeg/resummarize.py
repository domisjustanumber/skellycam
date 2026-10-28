# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "simplejpeg>=1.7", "psutil>=5.9"]
# ///
"""Re-run validation/summary for every cell under a results root whose raw run dir still exists in scratch, with the
current mjpeg_common.py (no camera access). Used after the validator changes, so all cells share one validator.

  uv run --script research/usb_cameras/mjpeg/resummarize.py --root <results root> --out-root <NEW dir> [--test mjpeg_msmf ...]

<results root> is a run_matrix.py --root dir (cells at <root>/mjpeg_<backend>/<label>/); its raw run dirs are
$MJPEG_SCRATCH/<root name>/mjpeg_<backend>/<label>/. Without --root the legacy 2026-10-25 layout is read
(results/<plat>/<host>/mjpeg_<backend>/<label>/, raw dirs at $MJPEG_SCRATCH/mjpeg_<backend>/<label>/).
Output goes to --out-root, which must not exist yet: earlier summaries are never modified. The original capture
command recorded in each summary.json is kept. Then: aggregate.py --root <out-root>.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mjpeg_common as mc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=None)
ap.add_argument("--out-root", required=True)
ap.add_argument("--test", action="append", default=None)
a = ap.parse_args()
base = Path(a.root) if a.root else mc.USB_ROOT / "results" / mc.plat() / mc.HOST
scr = mc.scratch_root() / base.name if a.root else mc.scratch_root()
out_root = Path(a.out_root)
if out_root.exists():
    raise SystemExit(f"error: {out_root} exists; pick a new --out-root (results are never overwritten)")
done, missing = [], []
for s in sorted(base.glob("mjpeg_*/*/summary.json")):
    test, label = s.parent.parent.name, s.parent.name
    if test.startswith(("mjpeg_run_", "mjpeg_rerun_")) or (a.test and test not in a.test):
        continue
    if any((s.parent / m).exists() for m in ("INVALID.txt", "SUPERSEDED.txt")):
        continue
    rd = scr / test / label
    if not (rd / "meta.json").exists():
        missing.append(f"{test}/{label}")
        continue
    old = json.loads(s.read_text())
    out = mc.results_dir(test, label, root=out_root)
    not_jpeg = "decoded" in test or test.endswith("-decode")
    summ = mc.summarize_run(rd, out, test=test, command=old.get("command", ""), keep_samples=1,
                            payload_is_jpeg=False if not_jpeg else None, extra={"resummarized_from": str(s)})
    if (s.parent / "controls.json").exists() and not (out / "controls.json").exists():
        (out / "controls.json").write_text((s.parent / "controls.json").read_text())
    done.append(f"{test}/{label}")
    print(mc.brief(summ))
print(json.dumps({"resummarized": len(done), "out_root": str(out_root), "no_scratch_run_dir": missing}, indent=1))
