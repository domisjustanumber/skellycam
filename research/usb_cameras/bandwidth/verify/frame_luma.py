# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow==12.0.0"]
# ///
"""Mean frame luma (0-255, Pillow 'L' = ITU-R 601 Y) of saved MJPEG frames, per capture directory.

  uv run --script research/usb_cameras/bandwidth/verify/frame_luma.py DIR [DIR ...] [--every 10] [--out OUT.json]

DIR is searched recursively for directories that contain frame_*.jpg (e.g. the per-camera cam<k>/ dirs that
mf_multi_open.exe --save-dir writes). For every such directory: number of JPEGs, mean/min/max of per-frame mean
luma over every --every'th frame, and mean/median JPEG size. Used to label night-time re-runs (dark scenes give
smaller JPEGs and, with auto exposure, can lower fps). Writes no images.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


def luma_dir(d: Path, every: int) -> dict:
    from PIL import Image
    jp = sorted(d.glob("frame_*.jpg"))
    sizes = [p.stat().st_size for p in jp]
    lum = []
    bad = 0
    for p in jp[::max(1, every)]:
        try:
            with Image.open(p) as im:
                g = im.convert("L")
                h = g.histogram()
                n = sum(h)
                lum.append(sum(i * c for i, c in enumerate(h)) / n)
        except Exception:
            bad += 1
    return {"dir": str(d), "jpegs": len(jp), "luma_frames": len(lum), "decode_errors": bad,
            "mean_luma": round(statistics.fmean(lum), 2) if lum else None,
            "min_luma": round(min(lum), 2) if lum else None, "max_luma": round(max(lum), 2) if lum else None,
            "mean_jpeg_bytes": round(statistics.fmean(sizes)) if sizes else None,
            "median_jpeg_bytes": statistics.median(sizes) if sizes else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--every", type=int, default=10)
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = []
    for root in a.dirs:
        r = Path(root)
        cand = sorted({p.parent for p in r.rglob("frame_*.jpg")})
        for d in cand:
            row = luma_dir(d, a.every)
            row["rel"] = str(d.relative_to(r)) if d != r else "."
            row["root"] = str(r)
            rows.append(row)
            print(f"{row['root']}/{row['rel']}: n={row['jpegs']} luma={row['mean_luma']} "
                  f"[{row['min_luma']},{row['max_luma']}] mean_bytes={row['mean_jpeg_bytes']}", flush=True)
    doc = {"tool": "frame_luma", "command": " ".join(sys.argv), "every": a.every, "dirs": rows}
    if a.out:
        Path(a.out).write_text(json.dumps(doc, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
