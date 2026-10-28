# /// script
# requires-python = ">=3.10"
# dependencies = ["simplejpeg==1.8.2", "numpy<2.3", "opencv-python-headless==4.10.0.84"]
# ///
import sys, inspect, simplejpeg, cv2, numpy as np
print(simplejpeg.__version__, inspect.signature(simplejpeg.decode_jpeg))
b = open(sys.argv[1], "rb").read(); mid = len(b)//2
for name, bb in {"orig": b, "drop3072": b[:mid]+b[mid+3072:], "trunc_half_eoi": b[:mid]+b"\xff\xd9", "zero3072": b[:mid]+bytes(3072)+b[mid+3072:]}.items():
    try:
        simplejpeg.decode_jpeg(bb, strict=True); r = "ok"
    except Exception as e:
        r = f"ERR {e}"
    sys.stderr.write(f"--cv {name}\n"); sys.stderr.flush()
    cv2.imdecode(np.frombuffer(bb, np.uint8), cv2.IMREAD_COLOR)
    print(name, "simplejpeg strict:", r)
