# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow==11.3.0"]
# ///
"""rerun20261027 helper: for each JPEG given, print mean luma (Pillow 'L', 0-255), size, and a sha256 of the
concatenated DQT segments (quantisation tables) plus the list of APPn markers. Writes JSON to stdout.
Usage: uv run --script jpeg_luma_dqt.py <jpg> [<jpg> ...]"""
import hashlib
import io
import json
import sys

from PIL import Image, ImageStat


def markers(b: bytes):
    i, out, dqt = 2, [], b""
    while i + 4 <= len(b) and b[i] == 0xFF:
        m = b[i + 1]
        if m == 0xDA:  # SOS: entropy data follows
            out.append("SOS")
            break
        ln = int.from_bytes(b[i + 2:i + 4], "big")
        seg = b[i:i + 2 + ln]
        if m == 0xDB:
            dqt += seg
        out.append(f"{m:02X}")
        i += 2 + ln
    return out, hashlib.sha256(dqt).hexdigest()[:16] if dqt else None


res = []
for p in sys.argv[1:]:
    b = open(p, "rb").read()
    im = Image.open(io.BytesIO(b))
    im.load()
    mk, dqt = markers(b)
    res.append({"file": p, "bytes": len(b), "size": list(im.size), "mean_luma": round(ImageStat.Stat(im.convert("L")).mean[0], 2),
                "markers_before_sos": mk, "dqt_sha256_16": dqt})
print(json.dumps(res, indent=1))
