"""V6: cv2 retrieve(image=buf) when buf shape != decoded frame shape (simulates a resolution change with the
non-reallocated frame_rec_array, check_for_new_config.py L30-41). V7: does av.VideoFrame.from_ndarray copy the input?
Run: C:/Users/Dom/GitHub/freemocap/skellycam/.venv/Scripts/python.exe -I -u <this file>"""
import os, sys, tempfile
import numpy as np, cv2
path = os.path.join(tempfile.gettempdir(), "skc_verify_v6.avi")
vw = cv2.VideoWriter(path, cv2.VideoWriter.fourcc(*"MJPG"), 30, (640, 480))
for i in range(3):
    vw.write(np.full((480, 640, 3), 100, np.uint8))
vw.release()
cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)
buf = np.full((720, 1280, 3), 255, np.uint8)
cap.grab()
ok, out = cap.retrieve(image=buf)
print(f"V6 retrieve ok={ok}; returned shape={out.shape}; returned shares memory with provided buf={np.shares_memory(out, buf)}; "
      f"provided buf modified={(buf != 255).any()}")
cap.release(); os.remove(path)
try:
    import av
    a = np.random.randint(0, 255, (720, 1280, 3), np.uint8)
    f = av.VideoFrame.from_ndarray(a, format="bgr24")
    p = np.frombuffer(f.planes[0], np.uint8)
    print(f"V7 av {av.__version__}: from_ndarray plane shares memory with input={np.shares_memory(p, a)}")
except ImportError as e:
    print(f"V7 av not importable in this venv: {e}")
