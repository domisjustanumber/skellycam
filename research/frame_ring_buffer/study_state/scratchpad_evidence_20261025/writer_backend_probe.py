r"""Which cv2.VideoWriter backend serves fourcc 'X264' (SkellyCam DEFAULT_WRITER_FOURCC) on this machine?
Run: C:\Users\Dom\GitHub\freemocap\skellycam\.venv\Scripts\python.exe writer_backend_probe.py"""
import os, tempfile, cv2, numpy as np
for fourcc in ["X264", "H264", "avc1", "MJPG"]:
    ext = "avi" if fourcc == "MJPG" else "mp4"
    p = os.path.join(tempfile.gettempdir(), f"_skc_backend_probe_{fourcc}.{ext}")
    w = cv2.VideoWriter(p, cv2.VideoWriter.fourcc(*fourcc), 60.0, (1280, 720))
    opened = w.isOpened()
    name = w.getBackendName() if opened else None
    if opened:
        w.write(np.zeros((720, 1280, 3), np.uint8)); w.release()
    print(f"RESULT fourcc={fourcc} opened={opened} backend={name}")
    if os.path.exists(p): os.remove(p)
