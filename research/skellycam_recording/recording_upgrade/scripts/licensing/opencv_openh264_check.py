"""Functional check: does cv2.VideoWriter(CAP_FFMPEG, 'avc1') open, and what does OpenCV print to stderr?
Writes a 4-frame synthetic (gray) clip into --tmp. No camera, no timing."""
import argparse, os, subprocess, sys, json

CHILD = r'''
import cv2, numpy as np, sys
p = sys.argv[1]
w = cv2.VideoWriter(p, cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*"avc1"), 30, (320, 240))
print("cv2", cv2.__version__, "opened", w.isOpened(), flush=True)
for _ in range(4):
    w.write(np.full((240, 320, 3), 128, np.uint8))
w.release()
'''

ap = argparse.ArgumentParser()
ap.add_argument("--tmp", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
os.makedirs(a.tmp, exist_ok=True)
clip = os.path.join(a.tmp, "openh264_check.mp4")
r = subprocess.run([sys.executable, "-I", "-c", CHILD, clip], capture_output=True, text=True, timeout=60)
res = {"python": sys.executable, "returncode": r.returncode, "stdout": r.stdout.strip(),
       "stderr_openh264_lines": [l for l in r.stderr.splitlines() if "penH264" in l or "openh264" in l],
       "clip_bytes": os.path.getsize(clip) if os.path.exists(clip) else None}
with open(a.out, "w") as f:
    json.dump(res, f, indent=1)
print(json.dumps(res, indent=1))
