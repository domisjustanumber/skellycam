# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow==11.3.0"]
# ///
"""Decode-check the frames uvc_iso wrote with --raw-mjpeg.

Usage:
    uv run --script research/usb_cameras/rust/tools/decode_mjpeg_check.py <run_dir> <raw.mjpeg> [<run_dir> <raw.mjpeg> ...]

<run_dir> holds frames_*.jsonl; <raw.mjpeg> is the concatenation of the frames in that order
(offsets = running sum of payload_bytes). Each frame is fully decoded with Pillow; writes
<run_dir>/decode_check.json with counts, image size and first failures. No pixels are saved.
"""
import io
import json
import sys
from pathlib import Path

from PIL import Image


def check(run_dir: Path, raw: Path) -> dict:
    rows = [json.loads(l) for l in next(run_dir.glob("frames_*.jsonl")).read_text().splitlines() if l.strip()]
    data = raw.read_bytes()
    off, ok, bad, sizes, fails = 0, 0, 0, {}, []
    for r in rows:
        n = r["payload_bytes"]
        b = data[off:off + n]
        off += n
        try:
            im = Image.open(io.BytesIO(b))
            im.load()
            ok += 1
            sizes[f"{im.size[0]}x{im.size[1]}"] = sizes.get(f"{im.size[0]}x{im.size[1]}", 0) + 1
        except Exception as e:  # noqa: BLE001 - record any decoder failure
            bad += 1
            if len(fails) < 5:
                fails.append({"seq": r["seq"], "bytes": n, "error": repr(e)[:200]})
    out = {"run_dir": str(run_dir), "raw_file": str(raw), "raw_bytes": len(data), "bytes_accounted": off,
           "frames": len(rows), "decoded_ok": ok, "decode_failed": bad,
           "percent_decoded": 100.0 * ok / len(rows) if rows else None, "image_sizes": sizes, "first_failures": fails,
           "decoder": f"Pillow {Image.__version__ if hasattr(Image, '__version__') else ''}"}
    (run_dir / "decode_check.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    for d, r in zip(a[0::2], a[1::2]):
        o = check(Path(d), Path(r))
        print(f"{Path(d).name}: frames={o['frames']} decoded_ok={o['decoded_ok']} failed={o['decode_failed']} sizes={o['image_sizes']} bytes {o['bytes_accounted']}/{o['raw_bytes']}")
