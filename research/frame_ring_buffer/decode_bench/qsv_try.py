"""QSV attempt: numbers/errors only; frames read in place and never written."""
import glob, time, json, traceback, numpy as np, av
from av.codec.hwaccel import HWAccel
F = glob.glob(r"C:\Users\Dom\GitHub\freemocap\skellycam\research\frame_ring_buffer\jpeg_bound\frames\C922_1920x1080_median.jpg")[0]
b = open(F, "rb").read()
res = {}
for label, mk in [
    ("mjpeg_qsv+HWAccel(qsv)", lambda: av.codec.Codec("mjpeg_qsv", "r").create()),
    ("mjpeg_qsv hwaccel ctor", lambda: av.codec.CodecContext.create("mjpeg_qsv", "r", hwaccel=HWAccel(device_type="qsv"))),
    ("mjpeg+hwaccel d3d11va", lambda: av.codec.CodecContext.create("mjpeg", "r", hwaccel=HWAccel(device_type="d3d11va"))),
    ("mjpeg+hwaccel qsv", lambda: av.codec.CodecContext.create("mjpeg", "r", hwaccel=HWAccel(device_type="qsv"))),
]:
    try:
        c = mk()
        if label.startswith("mjpeg_qsv+"): raise RuntimeError("skipped: no hw device given")
        c.width, c.height = 1920, 1080
        out = []
        for i in range(5):
            out += c.decode(av.Packet(b))
        res[label] = f"frames={len(out)}" + (f" fmt={out[0].format.name} hwframe={getattr(out[0],"hw_frames_ctx",None) is not None}" if out else "")
        if out:
            a = out[0].to_ndarray(format="bgr24"); res[label] += f" shape={a.shape}"
            ts = []
            for i in range(300):
                t0 = time.perf_counter_ns(); fr = c.decode(av.Packet(b)); 
                if fr: fr[0].to_ndarray(format="bgr24")
                ts.append((time.perf_counter_ns() - t0) / 1e6)
            res[label] += f" median_ms={np.median(ts):.2f} p99={np.percentile(ts,99):.2f}"
    except Exception as e:
        res[label] = f"FAIL {type(e).__name__}: {e}"
for k, v in res.items(): print(k, "->", v)
json.dump(res, open(__file__.replace("qsv_try.py", "qsv_attempt.json"), "w"), indent=1)
