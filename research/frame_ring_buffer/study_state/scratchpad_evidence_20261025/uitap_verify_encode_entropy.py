"""imencode q60 cost vs image entropy at 960x540 and 640x360 (skellycam venv python)."""
import time, cv2, numpy as np
from ui_tap_bench import synthetic_image
P=[int(cv2.IMWRITE_JPEG_QUALITY),60]; N=60
for h,w in [(360,640),(540,960)]:
    grad = synthetic_image(h,w,0)
    rng=np.random.default_rng(1); bn=cv2.GaussianBlur(rng.integers(0,255,(h,w,3),dtype=np.uint8),(5,5),0)
    for name,img in [("gradient+noise",grad),("blurred-noise",bn)]:
        cv2.imencode(".jpg",img,P); t0=time.perf_counter_ns()
        for _ in range(N): ok,j=cv2.imencode(".jpg",img,P)
        print(f"{w}x{h} {name}: imencode {(time.perf_counter_ns()-t0)/N/1e6:.2f} ms, {len(j)/1024:.1f} KiB")
