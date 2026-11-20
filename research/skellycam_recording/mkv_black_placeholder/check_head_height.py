"""Does a smaller first block switch FFmpeg's MJPEG decoder to interlaced-field mode? Usage: python check_head_height.py OUT_DIR

Writes 640x480 4:2:2 files whose rows 0-9 are black placeholders of other sizes, then decodes them with PyAV
(one decoder, errors counted per packet) and reports the stream size ffprobe guesses.
"""

import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

out = Path(sys.argv[1])
P = [cv2.IMWRITE_JPEG_QUALITY, 90, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_422]
cam = cv2.imencode(".jpg", np.full((480, 640, 3), 128, np.uint8), P)[1].tobytes()
for w, h in [(640, 400), (640, 368), (640, 352), (640, 240), (320, 480), (16, 16), (1280, 960)]:
    ph = cv2.imencode(".jpg", np.zeros((h, w, 3), np.uint8), P)[1].tobytes()
    path = out / f"headsize_{w}x{h}.mkv"
    c = av.open(str(path), "w", format="matroska")
    s = c.add_mux_stream("mjpeg", rate=30, width=640, height=480)
    for row in range(40):
        p = av.Packet(ph if row < 10 else cam)
        p.stream, p.time_base, p.pts, p.dts, p.duration, p.is_keyframe = s, Fraction(1, 30), row, row, 1, True
        c.mux(p)
    c.close()
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    sizes, errors = [], 0
    with av.open(str(path)) as ic:
        st = ic.streams.video[0]
        for pk in ic.demux(st):
            try:
                for f in st.codec_context.decode(pk):
                    sizes.append(f"{f.width}x{f.height}")
            except av.error.InvalidDataError:
                errors += 1
    runs = []
    for x in sizes:
        if runs and runs[-1][0] == x:
            runs[-1][1] += 1
        else:
            runs.append([x, 1])
    print(f"head {w}x{h}: ffprobe {probe}; frames {len(sizes)}/40, packet errors {errors}, sizes {runs}")
