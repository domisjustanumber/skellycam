"""Preflight: list cameras (cv2_enumerate_cameras, MSMF) and open a chosen set together at 1280x720 MJPG.

Run under camlock. Prints JSON: per camera, open ok, frames read in ~3 s, achieved fps, mean grab ms.
Usage: preflight.py [VID:PID ...]   (hex)
"""
import json, sys, time
import cv2
from cv2_enumerate_cameras import enumerate_cameras

wanted = [tuple(int(x, 16) for x in a.split(":")) for a in sys.argv[1:]]
cams = [c for c in enumerate_cameras(cv2.CAP_MSMF)]
print(json.dumps([dict(index=c.index, name=c.name, vid=c.vid and f"{c.vid:04X}", pid=c.pid and f"{c.pid:04X}", path=c.path) for c in cams], indent=1))
sel = [c for w in wanted for c in cams if (c.vid, c.pid) == w]
caps = {}
for c in sel:
    t = time.perf_counter()
    cap = cv2.VideoCapture(c.index, cv2.CAP_MSMF)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    caps[c.name] = (cap, time.perf_counter() - t)
out = {}
counts = {k: 0 for k in caps}
t0 = time.perf_counter()
while time.perf_counter() - t0 < 4.0:
    for k, (cap, _) in caps.items():
        if cap.isOpened() and cap.grab():
            ok, img = cap.retrieve()
            if ok: counts[k] += 1
el = time.perf_counter() - t0
for k, (cap, topen) in caps.items():
    out[k] = dict(opened=cap.isOpened(), open_s=round(topen, 2), frames=counts[k], fps=round(counts[k] / el, 1),
                  w=cap.get(cv2.CAP_PROP_FRAME_WIDTH), h=cap.get(cv2.CAP_PROP_FRAME_HEIGHT), cap_fps=cap.get(cv2.CAP_PROP_FPS))
    cap.release()
print(json.dumps(out, indent=1))
