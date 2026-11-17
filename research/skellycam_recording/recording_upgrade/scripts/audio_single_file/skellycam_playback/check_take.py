# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "pillow==11.3.0"]
# ///
"""Self-check of a generated take (assert-based): camera-0 barcodes and flash frames read back from the JPEG bytes at the
sidecar offsets (first 300 + last 50 frames), and every click sits at its true sample in PyAV's decode of each audio file
(ps0: +312). Usage: uv run --script check_take.py short|long
"""
import io
import json
import os
import sys

import av
import numpy as np
from PIL import Image

D = os.path.join(r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496"
                 r"\scratchpad\audio_single_file\skellycam_playback", sys.argv[1])
tr = json.load(open(os.path.join(D, "truth.json")))
raw = open(os.path.join(D, "cam0.mkv"), "rb").read()
rows = [line.split(",") for line in open(os.path.join(D, "cam0.csv")) if line[0].isdigit()]
flash = set(tr["cams"]["cam0"]["flash_index"])
for r in rows[:300] + rows[-50:]:
    i, off, sz = int(r[0]), int(r[3]), int(r[4])
    y = np.asarray(Image.open(io.BytesIO(raw[off:off + sz])).convert("L"))
    assert sum(1 << b for b in range(20) if y[8, 16 * b + 8] > 128) == i, i
    assert (y[140, 160] > 200) == (i in flash), i
want = np.array([f["device_sample"] for f in tr["flashes"]])
for key, a in tr["audio"].items():
    c = av.open(os.path.join(D, a["file"]))
    x = np.concatenate([fr.to_ndarray().reshape(-1).astype(np.float64) for fr in c.decode(audio=0)])
    off = 312 if key == "opus_ps0" else 0
    got = np.array([w - 2000 + np.argmax(np.abs(x[w - 2000:w + 2000])) for w in want + off])
    assert (got - want - off == 0).all(), (key, sorted(set((got - want - off).tolist())))
    print(key, "decoded", len(x), "clicks exact", len(want))
print("ok", sys.argv[1])
