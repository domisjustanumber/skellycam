# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python==4.10.0.84", "pygrabber==0.2"]
# ///
"""Grab one frame from every DirectShow video device (Windows) to check what each camera sees.

Run (Windows, under camlock):
    uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/timing/scripts/snapshot_all.py <outdir>
Writes <outdir>/snapshot_<index>_<name>.jpg (downscaled to 640 px wide) and snapshot.json.
"""
import json, sys, time, re
from pathlib import Path
import cv2
from pygrabber.dshow_graph import FilterGraph

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
names = FilterGraph().get_input_devices()
want = [w.lower() for w in sys.argv[2:]]  # optional name substrings to restrict to
res = []
for i, n in enumerate(names):
    if want and not any(w in n.lower() for w in want):
        continue
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    ok = cap.isOpened()
    frame = None
    if ok:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        t0 = time.time()
        while time.time() - t0 < 3:   # let auto-exposure settle
            ok, frame = cap.read()
    cap.release()
    entry = {"index": i, "name": n, "ok": bool(ok and frame is not None)}
    if entry["ok"]:
        h, w = frame.shape[:2]
        entry["shape"] = [h, w]
        small = cv2.resize(frame, (640, int(640 * h / w)))
        p = out / f"snapshot_{i}_{re.sub(r'[^A-Za-z0-9]+', '_', n)}.jpg"
        cv2.imwrite(str(p), small); entry["file"] = p.name
    res.append(entry)
(out / "snapshot.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
