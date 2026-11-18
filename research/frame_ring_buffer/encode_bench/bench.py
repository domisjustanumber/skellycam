"""JPEG encode benchmark (cv2.imencode). Frames are read in place and held in memory; writes numbers only."""
import glob, json, multiprocessing as mp, os, platform, sys, time
import numpy as np, cv2, psutil

FRAMES = r"C:\Users\Dom\GitHub\freemocap\skellycam\research\frame_ring_buffer\jpeg_bound\frames"
RES = {"1280x720": (1280, 720), "1920x1080": (1920, 1080)}
N, WARM = 400, 30
SUB = {"4:2:0": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_420, "4:2:2": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_422,
       "4:4:4": cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444}
QS = [80, 85, 90, 95]


def slot(w, h): return -(-2 * (2048 + w * h // 2) // 4096) * 4096


def params(q, sub=None, opt=None):
    p = [cv2.IMWRITE_JPEG_QUALITY, q]
    if sub: p += [cv2.IMWRITE_JPEG_SAMPLING_FACTOR, SUB[sub]]
    if opt is not None: p += [cv2.IMWRITE_JPEG_OPTIMIZE, int(opt)]
    return p


def load(res):
    raw = [open(p, "rb").read() for p in sorted(glob.glob(f"{FRAMES}\\*_{res}_*.jpg"))]
    return raw, [cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR) for b in raw]


def noisy(img, sigma, rng):
    return np.clip(img + rng.normal(0, sigma, img.shape), 0, 255).astype(np.uint8)


def enc(img, p): return cv2.imencode(".jpg", img, p)[1]


def markers(b):
    b = bytes(b); i = 2; sof = None; dht = dqt = dri = 0
    while i < len(b):
        assert b[i] == 0xFF; m = b[i + 1]; L = int.from_bytes(b[i + 2:i + 4], "big")
        if m == 0xC4: dht += 1
        elif m == 0xDB: dqt += 1
        elif m == 0xDD: dri += 1
        elif m in (0xC0, 0xC2):
            n = b[i + 9]; sof = [(b[i + 10 + 3 * k], b[i + 11 + 3 * k] >> 4, b[i + 11 + 3 * k] & 15) for k in range(n)]
        if m == 0xDA: i += 2 + L; break
        i += 2 + L
    scan = b[i:]
    rst = sum(1 for k in range(len(scan) - 1) if scan[k] == 0xFF and 0xD0 <= scan[k + 1] <= 0xD7)
    return dict(DHT=dht, DQT=dqt, DRI=dri, RST_in_scan=rst, sampling=f"{sof[0][1]}x{sof[0][2]}")


def sub_name(b):
    m = markers(b)["sampling"]; return {"2x2": "4:2:0", "2x1": "4:2:2", "1x1": "4:4:4", "1x2": "4:4:0"}.get(m, m)


def timeit(f, n=N, warm=WARM):
    for i in range(warm): f(i)
    ts = np.empty(n)
    for i in range(n):
        t0 = time.perf_counter_ns(); f(i); ts[i] = (time.perf_counter_ns() - t0) / 1e6
    return ts


def tstats(ts):
    return dict(median=float(np.median(ts)), p95=float(np.percentile(ts, 95)), p99=float(np.percentile(ts, 99)), max=float(ts.max()))


def proc(args):
    res, bar, q = args
    cv2.setNumThreads(1)
    _, imgs = load(res); p = params(90, "4:2:2")
    for i in range(WARM): enc(imgs[i % len(imgs)], p)
    bar.wait(); ts = np.empty(N)
    for i in range(N):
        t0 = time.perf_counter_ns(); enc(imgs[i % len(imgs)], p); ts[i] = (time.perf_counter_ns() - t0) / 1e6
    q.put(tstats(ts))


def concurrent(res, n=8):
    ctx = mp.get_context("spawn"); m = mp.Manager(); bar = m.Barrier(n); q = m.Queue()
    ps = [ctx.Process(target=proc, args=((res, bar, q),)) for _ in range(n)]
    [p.start() for p in ps]; [p.join() for p in ps]
    rs = [q.get() for _ in range(n)]
    return dict(per_proc_median_ms=float(np.median([r["median"] for r in rs])),
                per_proc_p99_ms_median=float(np.median([r["p99"] for r in rs])), per_proc_p99_ms_worst=float(max(r["p99"] for r in rs)))


def yuy2(bgr):
    yuv = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV)
    out = np.empty((bgr.shape[0], bgr.shape[1], 2), np.uint8)
    out[:, :, 0] = yuv[:, :, 0]; out[:, 0::2, 1] = yuv[:, 0::2, 1]; out[:, 1::2, 1] = yuv[:, 0::2, 2]
    return out


def nv12(bgr):
    h, w = bgr.shape[:2]; i420 = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV_I420)
    y = i420[:h]; u = i420[h:h + h // 4].reshape(-1); v = i420[h + h // 4:].reshape(-1)
    uv = np.empty(u.size * 2, np.uint8); uv[0::2] = u; uv[1::2] = v
    return np.vstack([y, uv.reshape(h // 2, w)])


if __name__ == "__main__":
    pre = psutil.cpu_percent(interval=5)
    out = dict(info=dict(cpu=platform.processor(), logical_cores=os.cpu_count(), pre_run_cpu_percent=pre,
                         python=sys.version.split()[0], numpy=np.__version__, opencv=cv2.__version__,
                         default_cv2_threads=cv2.getNumThreads()),
               sampling_default={}, markers={}, sizes={}, timing={}, convert={}, camera_orig={}, equal_size={}, concurrent={}, slot={})
    cv2.setNumThreads(1)
    for res, (w, h) in RES.items():
        raw, imgs = load(res); rng = np.random.default_rng(0)
        out["slot"][res] = slot(w, h)
        out["sampling_default"][res] = sub_name(enc(imgs[0], [cv2.IMWRITE_JPEG_QUALITY, 90]))
        out["markers"][res] = markers(enc(imgs[0], params(90, "4:2:2", False)))
        out["markers"][res + "_optimize"] = markers(enc(imgs[0], params(90, "4:2:2", True)))
        sets = {"real": imgs, "noise5": [noisy(i, 5, rng) for i in imgs], "noise15": [noisy(i, 15, rng) for i in imgs],
                "uniform_random_synthetic": [rng.integers(0, 256, (h, w, 3), dtype=np.uint8)]}
        settings = [(q, s, None) for q in QS for s in SUB] + [(90, "4:2:2", True), (90, "4:2:2", False)]
        out["sizes"][res] = {}; out["timing"][res] = {}
        for q, s, o in settings:
            key = f"q{q}_{s}" + ("" if o is None else f"_opt{int(o)}"); p = params(q, s, o)
            out["sizes"][res][key] = {}
            for name, ims in sets.items():
                sz = [len(enc(im, p)) for im in ims]
                out["sizes"][res][key][name] = dict(min=min(sz), median=float(np.median(sz)), max=max(sz),
                    bpp_median=float(np.median(sz)) / (w * h), max_frac_slot=max(sz) / out["slot"][res])
            out["timing"][res][key] = dict(real=tstats(timeit(lambda i: enc(imgs[i % len(imgs)], p))),
                                           noise15=tstats(timeit(lambda i: enc(sets["noise15"][i % len(imgs)], p), n=300)))
            print(res, key, out["timing"][res][key]["real"], out["sizes"][res][key]["real"]["max_frac_slot"], flush=True)
        cb = [len(b) for b in raw]
        out["camera_orig"][res] = dict(bytes=cb, median=float(np.median(cb)), bpp_median=float(np.median(cb)) / (w * h))
        out["equal_size"][res] = {}
        for s in ("4:2:0", "4:2:2"):
            qs = list(range(50, 100))
            med = [np.median([len(enc(im, params(q, s))) for im in imgs]) for q in qs]
            out["equal_size"][res][s] = dict(best_q=qs[int(np.argmin([abs(m - np.median(cb)) for m in med]))],
                                             median_by_q={str(q): float(m) for q, m in zip(qs, med) if q % 5 == 0})
        yu = [yuy2(i) for i in imgs]; nv = [nv12(i) for i in imgs]
        out["convert"][res] = dict(
            YUY2_to_BGR=tstats(timeit(lambda i: cv2.cvtColor(yu[i % len(yu)], cv2.COLOR_YUV2BGR_YUY2))),
            NV12_to_BGR=tstats(timeit(lambda i: cv2.cvtColor(nv[i % len(nv)], cv2.COLOR_YUV2BGR_NV12))))
        print(res, out["convert"][res], flush=True)
    cv2.setNumThreads(out["info"]["default_cv2_threads"])
    out["timing_default_threads"] = {}
    for res in RES:
        _, imgs = load(res); p = params(90, "4:2:2")
        out["timing_default_threads"][res] = tstats(timeit(lambda i: enc(imgs[i % len(imgs)], p)))
    for res in RES:
        out["concurrent"][res] = concurrent(res); print("conc", res, out["concurrent"][res], flush=True)
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.json"), "w"), indent=1)
