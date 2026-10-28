r"""Which cv2.VideoWriter backend/codec is used for SkellyCam's DEFAULT_WRITER_FOURCC='X264' on this Windows box?
Run: C:\Users\Dom\GitHub\freemocap\skellycam\.venv\Scripts\python.exe probe_writer_backend.py > probe_writer_backend.out.txt 2>&1"""
import cv2, os, tempfile, numpy as np, av
for size in [(1280, 720), (1920, 1080)]:
    p = os.path.join(tempfile.gettempdir(), f"probe_{size[0]}.mp4")
    w = cv2.VideoWriter(p, cv2.VideoWriter.fourcc(*"X264"), 60, size)
    print(size, "isOpened", w.isOpened(), "backend:", w.getBackendName())
    for i in range(30):
        w.write(np.full((size[1], size[0], 3), i, np.uint8))
    w.release()
    c = av.open(p); print("   codec in file:", c.streams.video[0].codec_context.name); c.close(); os.remove(p)
