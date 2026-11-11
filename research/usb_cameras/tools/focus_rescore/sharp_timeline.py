"""Per-frame normalised Laplacian sharpness (centre 50%) over a wincam capture folder (frames.jsonl + frames.mjpeg).
Same formula as research/usb_cameras/suite/common/imgmetrics.py::sharpness. Read-only on result files."""
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def sharp(b: bytes) -> float:
    im = Image.open(io.BytesIO(b)).convert("L")
    w, h = im.size
    im = im.crop((int(w * 0.25), int(h * 0.25), int(w * 0.75), int(h * 0.75)))
    y = np.asarray(im, dtype=np.float64)
    lap = (y[1:-1, :-2] + y[1:-1, 2:] + y[:-2, 1:-1] + y[2:, 1:-1]) - 4.0 * y[1:-1, 1:-1]
    m = float(y.mean())
    return float(lap.var() / max(m * m, 1e-6))


def main(folder: str, every: int = 1) -> None:
    d = Path(folder)
    rows = [json.loads(x) for x in (d / "frames.jsonl").read_text().splitlines() if x.strip()]
    data = (d / "frames.mjpeg").read_bytes()
    t0 = rows[0]["qpc_ns"]
    out = []
    for r in rows:
        off, ln = r.get("mjpeg_offset"), r.get("mjpeg_len")
        if off is None or ln is None or off < 0 or ln <= 0:
            continue
        try:
            s = sharp(data[off:off + ln])
        except Exception:
            continue
        out.append(((r["qpc_ns"] - t0) / 1e6, r["seq"], s))
    for i, (t, seq, s) in enumerate(out):
        if i % every == 0:
            print(f"{t:8.0f} ms  seq {seq:4d}  sharp {s:.5f}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1)
