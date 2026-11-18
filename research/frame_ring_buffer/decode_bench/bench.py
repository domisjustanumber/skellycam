"""MJPEG decode benchmark. Reads frames in place (never copies them); writes numbers only."""
import glob, io, json, multiprocessing as mp, os, platform, sys, time
import warnings; warnings.simplefilter("ignore")
import numpy as np, cv2, av, psutil, simplejpeg, turbojpeg
from PIL import Image

FRAMES = r"C:\Users\Dom\GitHub\freemocap\skellycam\research\frame_ring_buffer\jpeg_bound\frames"
DLL = glob.glob(r"C:\Users\Dom\AppData\Local\uv\cache\archive-v0\*\pupil_labs_uvc.libs\turbojpeg-*.dll")[0] \
    if not os.environ.get("TJ_DLL") else os.environ["TJ_DLL"]
RES = {"1280x720": (1280, 720), "1920x1080": (1920, 1080)}
DROPPED = []
N = 400
WARM = 40

def load(res):
    out = []
    for p in sorted(glob.glob(f"{FRAMES}\*_{res}_*.jpg")):
        b = open(p, "rb").read()
        try: simplejpeg.decode_jpeg(b)  # strict decoder: drop frames with trailing garbage inside the scan
        except ValueError: DROPPED.append(os.path.basename(p)); continue
        out.append((os.path.basename(p).split("_")[0] + "_" + p.rsplit("_", 1)[1][:-4], b))
    return out

def make(name, w, h):
    """Return decode(bytes)->BGR ndarray for decoder `name`."""
    if name.startswith("cv2"):
        if name == "cv2_1thread": cv2.setNumThreads(1)
        return lambda b: cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
    if name.startswith("turbo"):
        t = turbojpeg.TurboJPEG(DLL)
        fl = {"turbo": 0, "turbo_fast": turbojpeg.TJFLAG_FASTDCT | turbojpeg.TJFLAG_FASTUPSAMPLE,
              "turbo_fastdct": turbojpeg.TJFLAG_FASTDCT, "turbo_fastup": turbojpeg.TJFLAG_FASTUPSAMPLE}
        if name == "turbo_yuv_only":
            return lambda b: t.decode_to_yuv(b)
        f = fl[name]
        return lambda b: t.decode(b, pixel_format=turbojpeg.TJPF_BGR, flags=f)
    if name.startswith("simplejpeg"):
        kw = {"simplejpeg": {}, "simplejpeg_fast": dict(fastdct=True, fastupsample=True)}[name]
        return lambda b: simplejpeg.decode_jpeg(b, colorspace="BGR", **kw)
    if name == "pillow":
        return lambda b: np.ascontiguousarray(np.asarray(Image.open(io.BytesIO(b)).convert("RGB"))[:, :, ::-1])
    if name.startswith("pyav"):
        c = av.codec.CodecContext.create("mjpeg", "r")
        if name == "pyav_decode_only":
            return lambda b: c.decode(av.Packet(b))[0]
        return lambda b: c.decode(av.Packet(b))[0].to_ndarray(format="bgr24")
    if name.startswith("qsv"):
        from av.codec.hwaccel import HWAccel
        c = av.codec.Codec("mjpeg_qsv", "r").create()
        # hwaccel device given at context creation
        raise NotImplementedError
    raise ValueError(name)

def run(name, frames, w, h, n=N, warm=WARM):
    dec = make(name, w, h)
    for i in range(warm): dec(frames[i % len(frames)][1])
    ts = np.empty(n)
    for i in range(n):
        b = frames[i % len(frames)][1]
        t0 = time.perf_counter_ns(); dec(b); ts[i] = (time.perf_counter_ns() - t0) / 1e6
    return ts

def stats(ts):
    return dict(median=float(np.median(ts)), p95=float(np.percentile(ts, 95)), p99=float(np.percentile(ts, 99)),
                max=float(ts.max()), fps_per_core=float(1000 / np.mean(ts)))

def proc(args):
    name, res, bar, q = args
    w, h = RES[res]
    frames = load(res)
    dec = make(name, w, h)
    for i in range(WARM): dec(frames[i % len(frames)][1])
    bar.wait()
    ts = np.empty(N)
    for i in range(N):
        b = frames[i % len(frames)][1]
        t0 = time.perf_counter_ns(); dec(b); ts[i] = (time.perf_counter_ns() - t0) / 1e6
    q.put(stats(ts))

def concurrent(name, res, nproc=8):
    ctx = mp.get_context("spawn"); m = mp.Manager(); bar = m.Barrier(nproc); q = m.Queue()
    ps = [ctx.Process(target=proc, args=((name, res, bar, q),)) for _ in range(nproc)]
    [p.start() for p in ps]; [p.join() for p in ps]
    rs = [q.get() for _ in range(nproc)]
    return dict(per_proc_median_ms=float(np.median([r["median"] for r in rs])),
                per_proc_p99_ms_worst=float(max(r["p99"] for r in rs)),
                per_proc_p99_ms_median=float(np.median([r["p99"] for r in rs])),
                fps_per_proc=float(np.median([r["fps_per_core"] for r in rs])))

DECODERS = ["cv2_1thread", "cv2_default", "turbo", "turbo_fast", "turbo_fastdct", "turbo_fastup", "turbo_yuv_only",
            "simplejpeg", "simplejpeg_fast", "pillow", "pyav", "pyav_decode_only"]

if __name__ == "__main__":
    load_pre = psutil.cpu_percent(interval=5)
    info = dict(cpu=platform.processor(), logical_cores=os.cpu_count(), pre_run_cpu_percent=load_pre,
                versions=dict(python=sys.version.split()[0], numpy=np.__version__, opencv=cv2.__version__, av=av.__version__,
                              simplejpeg=simplejpeg.__version__, PyTurboJPEG=turbojpeg.__version__ if hasattr(turbojpeg, "__version__") else "2.6.1",
                              pillow=__import__("PIL").__version__, turbojpeg_dll=os.path.basename(DLL)))
    out = dict(info=info, dropped_frames=DROPPED, frames={}, single={}, validation={}, concurrent={})
    t = turbojpeg.TurboJPEG(DLL)
    for res, (w, h) in RES.items():
        fr = load(res)
        out["frames"][res] = [dict(frame=n, bytes=len(b), subsampling={0: "4:4:4", 1: "4:2:2", 2: "4:2:0", 3: "gray", 4: "4:4:0", 5: "4:1:1"}.get(t.decode_header(b)[2], t.decode_header(b)[2])) for n, b in fr]
        cv2.setNumThreads(1)
        ref = [cv2.imdecode(np.frombuffer(b, np.uint8), 1) for _, b in fr]
        out["single"][res] = {}; out["validation"][res] = {}
        for d in DECODERS:
            dec = make(d, w, h)
            if d not in ("turbo_yuv_only", "pyav_decode_only"):
                diffs = []
                for (_, b), r in zip(fr, ref):
                    o = dec(b); assert o.shape == (h, w, 3) and o.dtype == np.uint8, (d, o.shape)
                    diffs.append(float(np.abs(o.astype(np.int16) - r).mean()))
                out["validation"][res][d] = dict(mean_abs_diff_max_over_frames=max(diffs))
            ts = run(d, fr, w, h); out["single"][res][d] = stats(ts)
            print(res, d, out["single"][res][d], flush=True)
    for res in RES:
        for d in ["cv2_1thread", "turbo", "turbo_fast", "simplejpeg_fast"]:
            out["concurrent"].setdefault(res, {})[d] = concurrent(d, res)
            print("conc", res, d, out["concurrent"][res][d], flush=True)
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "results.json"), "w"), indent=1)
