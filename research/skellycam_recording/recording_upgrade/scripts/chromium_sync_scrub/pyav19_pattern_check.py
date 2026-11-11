# /// script
# requires-python = ">=3.10"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""Functional check (no timing): decode every frame of the given clips with PyAV 19.0.2 (libavcodec) and read the
burned 16-bit index with the same rule as gen_clips.py read_index / the browser harness.
Records unreadable frames (pattern pair differs by <= 64) and wrong frames (index != decode position).
Usage: uv run --script pyav19_pattern_check.py <out_json> <clip> [<clip> ...]
"""
import json
import sys
from pathlib import Path

import av
import numpy as np

BITS, CELLS = 16, 32


def read_index(img: np.ndarray):
    h, w = img.shape[:2]
    cw = w // CELLS
    y = cw // 2
    gray = img[y, :, :].mean(axis=1)
    v = 0
    for b in range(BITS):
        a = gray[(2 * b) * cw + cw // 2]
        c = gray[(2 * b + 1) * cw + cw // 2]
        if abs(a - c) <= 64:
            return None
        v = (v << 1) | (1 if a > c else 0)
    return v


res = {"pyav": av.__version__, "libavcodec": av.library_versions.get("libavcodec"), "files": {}}
for f in sys.argv[2:]:
    unreadable, wrong, n = [], [], 0
    with av.open(f) as c:
        s = c.streams.video[0]
        dec_name = s.codec_context.name
        for k, fr in enumerate(c.decode(s)):
            n += 1
            idx = read_index(fr.to_ndarray(format="bgr24"))
            if idx is None:
                unreadable.append(k)
            elif idx != k:
                wrong.append([k, idx])
    res["files"][Path(f).resolve().as_posix()] = {"decoder": dec_name, "frames_decoded": n,
                                                  "unreadable": unreadable, "wrong": wrong}
Path(sys.argv[1]).write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
