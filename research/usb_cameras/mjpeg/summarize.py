# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "simplejpeg>=1.7", "psutil>=5.9"]
# ///
"""Validate + summarize one capture run directory (see mjpeg_common.py for the contract).

  uv run --script research/usb_cameras/mjpeg/summarize.py <run_dir> --test mjpeg_msmf --label 720p30_c922
        [--keep-samples 1] [--command "<the capture command that produced run_dir>"] [--not-jpeg]

Writes results/<platform>/<host>/<test>/<label>/{summary.json,frames.jsonl[,sample_*.jpghdr]}, or
<root>/<test>/<label>/... with --root (run_matrix.py passes a fresh timestamped root so earlier results are never overwritten).
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mjpeg_common as mc

ap = argparse.ArgumentParser()
ap.add_argument("run_dir")
ap.add_argument("--test", required=True)
ap.add_argument("--label", required=True)
ap.add_argument("--keep-samples", type=int, default=0)
ap.add_argument("--command", default="")
ap.add_argument("--not-jpeg", action="store_true", help="payload is decoded pixels; skip JPEG validation")
ap.add_argument("--extra", default=None, help="JSON object merged into summary")
ap.add_argument("--root", default=None, help="results root (default results/<platform>/<host>)")
a = ap.parse_args()
out = mc.results_dir(a.test, a.label, root=a.root)
if (out / "summary.json").exists():
    raise SystemExit(f"error: {out / 'summary.json'} exists; results are never overwritten (use a new --root or --label)")
s = mc.summarize_run(Path(a.run_dir), out, test=a.test, command=a.command, keep_samples=a.keep_samples,
                     payload_is_jpeg=False if a.not_jpeg else None, extra=json.loads(a.extra) if a.extra else None)
print(mc.brief(s))
print("wrote", out / "summary.json")
