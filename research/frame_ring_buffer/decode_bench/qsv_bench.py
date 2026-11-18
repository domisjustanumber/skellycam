"""mjpeg_qsv timing over the real frames (read in place); numbers only."""
import glob, time, json, numpy as np, av
from av.codec.hwaccel import HWAccel
D = r"C:\Users\Dom\GitHub\freemocap\skellycam\research\frame_ring_buffer\jpeg_bound\frames"
out = {}
for res in ("1280x720", "1920x1080"):
    fr = [open(p, "rb").read() for p in sorted(glob.glob(f"{D}\*_{res}_*.jpg")) if "generic_1920" not in p]
    c = av.codec.CodecContext.create("mjpeg_qsv", "r", hwaccel=HWAccel(device_type="qsv"))
    got = 0; ts = []; fmts = set()
    for i in range(340):
        t0 = time.perf_counter_ns()
        f = c.decode(av.Packet(fr[i % len(fr)]))
        for x in f: a = x.to_ndarray(format="bgr24"); fmts.add(x.format.name); assert a.shape[2] == 3
        dt = (time.perf_counter_ns() - t0) / 1e6
        if i >= 40: ts.append(dt); got += len(f)
    ts = np.array(ts)
    out[res] = dict(frames_out_per_300_in=got, fmts=sorted(fmts), shape=list(a.shape), median=float(np.median(ts)), p95=float(np.percentile(ts, 95)),
                    p99=float(np.percentile(ts, 99)), max=float(ts.max()), fps_per_core=float(1000 / ts.mean()))
    print(res, out[res])
json.dump(out, open("qsv_bench.json", "w"), indent=1)
