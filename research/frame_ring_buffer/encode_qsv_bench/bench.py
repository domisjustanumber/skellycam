"""mjpeg_qsv (PyAV) vs cv2 cvtColor+imencode, from YUY2 / NV12. Frames read in place, held in memory only. Writes results.json (numbers only).
uv run --no-project --python 3.13 --with av==19.0.2 --with opencv-contrib-python==5.1.0.95 --with numpy==2.5.5 --with psutil==7.2.2 python bench.py [stage ...]
"""
import ctypes, glob, json, multiprocessing as mp, os, subprocess, sys, time, traceback
from fractions import Fraction
import numpy as np, cv2, av, psutil

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = r"C:\Users\Dom\GitHub\freemocap\skellycam\research\frame_ring_buffer\jpeg_bound\frames"
SCRATCH = r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\000f1fe2-336c-4dbd-863c-2f7b899e0194\scratchpad"
RES = {"1280x720": (1280, 720), "1920x1080": (1920, 1080)}
SUBS = {"yuy2": ("4:2:2", cv2.IMWRITE_JPEG_SAMPLING_FACTOR_422), "nv12": ("4:2:0", cv2.IMWRITE_JPEG_SAMPLING_FACTOR_420)}
PIX = {"yuy2": "yuyv422", "nv12": "nv12"}


# ---------- frames ----------
def load(res):
    return [cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR) for p in sorted(glob.glob(f"{FRAMES}\\*_{res}_*.jpg"))]


def yuy2(bgr):
    yuv = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV)
    out = np.empty((bgr.shape[0], bgr.shape[1], 2), np.uint8)
    out[:, :, 0] = yuv[:, :, 0]; out[:, 0::2, 1] = yuv[:, 0::2, 1]; out[:, 1::2, 1] = yuv[:, 0::2, 2]
    return out


def nv12(bgr):  # full range: BT.601 full-range planes, chroma 2x2 area mean
    h, w = bgr.shape[:2]; yuv = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV)
    u = cv2.resize(yuv[:, :, 1], (w // 2, h // 2), interpolation=cv2.INTER_AREA); v = cv2.resize(yuv[:, :, 2], (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    uv = np.empty((h // 2, w), np.uint8); uv[:, 0::2] = u; uv[:, 1::2] = v
    return np.vstack([yuv[:, :, 0], uv])


def to_limited(fmt, a, h):  # full -> studio range (Y 16..235, C 16..240), as a real camera sends
    lut = np.arange(256, dtype=np.float32); ly = np.round(16 + lut * 219 / 255).astype(np.uint8); lc = np.round(128 + (lut - 128) * 224 / 255).astype(np.uint8)
    o = a.copy()
    if fmt == "yuy2": o[:, :, 0] = ly[a[:, :, 0]]; o[:, :, 1] = lc[a[:, :, 1]]
    else: o[:h] = ly[a[:h]]; o[h:] = lc[a[h:]]
    return o


def expand_lut(fmt, a, h):  # limited -> full on the host (the extra step A would need)
    x = np.arange(256, dtype=np.float32); ly = np.clip(np.round((x - 16) * 255 / 219), 0, 255).astype(np.uint8); lc = np.clip(np.round(128 + (x - 128) * 255 / 224), 0, 255).astype(np.uint8)
    if fmt == "yuy2": return cv2.LUT(a, np.stack([ly, lc], 1).reshape(256, 1, 2))
    o = np.empty_like(a); o[:h] = cv2.LUT(a[:h], ly); o[h:] = cv2.LUT(a[h:], lc); return o


def raws(fmt, res):
    imgs = load(res); return [(yuy2 if fmt == "yuy2" else nv12)(i) for i in imgs]


def src_y(fmt, a, w, h):
    return a[:, :, 0] if fmt == "yuy2" else a[:h]


# ---------- encoders ----------
def make_qsv(fmt, w, h, gq, ad=None, low_power=None, fps=30):
    cc = av.CodecContext.create("mjpeg_qsv", "w")
    cc.width, cc.height, cc.pix_fmt = w, h, PIX[fmt]
    cc.time_base, cc.framerate, cc.gop_size = Fraction(1, fps), Fraction(fps, 1), 1
    o = {"global_quality": str(gq)}
    if ad is not None: o["async_depth"] = str(ad)
    if low_power is not None: o["low_power"] = str(low_power)
    cc.options = o; cc.color_range = 2; cc.open(); return cc


def make_frame(fmt, w, h):
    f = av.VideoFrame(w, h, PIX[fmt]); f.color_range = 2; return f


def fill(f, fmt, a, w, h):
    arrs = [a.reshape(h, 2 * w)] if fmt == "yuy2" else [a[:h], a[h:]]
    for p, x in zip(f.planes, arrs):
        np.frombuffer(p, np.uint8).reshape(-1, p.line_size)[:x.shape[0], :x.shape[1]] = x


class QsvEnc:
    def __init__(self, fmt, w, h, gq, ad=None, low_power=None, fps=30):
        self.fmt, self.w, self.h = fmt, w, h
        self.cc = make_qsv(fmt, w, h, gq, ad, low_power, fps); self.f = make_frame(fmt, w, h); self.k = 0

    def encode(self, a):  # frame wrap + encode + packet retrieval; returns list of (pts, bytes)
        fill(self.f, self.fmt, a, self.w, self.h); self.f.pts = self.k; self.k += 1
        return [(p.pts, bytes(p)) for p in self.cc.encode(self.f)]


class CvEnc:
    def __init__(self, fmt, q=90):
        self.code = cv2.COLOR_YUV2BGR_YUY2 if fmt == "yuy2" else cv2.COLOR_YUV2BGR_NV12
        self.p = [cv2.IMWRITE_JPEG_QUALITY, q, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, SUBS[fmt][1]]

    def encode(self, a): return cv2.imencode(".jpg", cv2.cvtColor(a, self.code), self.p)[1].tobytes()


# ---------- JPEG checks ----------
def markers(b):
    b = bytes(b); i = 2; sof = None; dht = dqt = 0; jfif = b[2:4] == b"\xff\xe0"; adobe = False
    while i < len(b):
        assert b[i] == 0xFF; m = b[i + 1]; L = int.from_bytes(b[i + 2:i + 4], "big")
        if m == 0xC4: dht += 1
        elif m == 0xDB: dqt += 1
        elif m == 0xEE: adobe = True
        elif m in (0xC0, 0xC1, 0xC2):
            n = b[i + 9]; sof = (m, [(b[i + 10 + 3 * k], b[i + 11 + 3 * k] >> 4, b[i + 11 + 3 * k] & 15) for k in range(n)])
        if m == 0xDA: break
        i += 2 + L
    s = f"{sof[1][0][1]}x{sof[1][0][2]}"
    return dict(SOF=hex(sof[0]), DHT=dht, DQT=dqt, JFIF=jfif, sampling={"2x2": "4:2:0", "2x1": "4:2:2", "1x1": "4:4:4"}.get(s, s))


def psnr(a, b): m = np.mean((a.astype(np.float64) - b) ** 2); return float(10 * np.log10(255 ** 2 / m)) if m else 99.0


def ssim(a, b):
    a = a.astype(np.float32); b = b.astype(np.float32); g = lambda x: cv2.GaussianBlur(x, (11, 11), 1.5)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    ma, mb = g(a), g(b); va = g(a * a) - ma * ma; vb = g(b * b) - mb * mb; cab = g(a * b) - ma * mb
    return float(np.mean(((2 * ma * mb + c1) * (2 * cab + c2)) / ((ma * ma + mb * mb + c1) * (va + vb + c2))))


def qsv_all(fmt, w, h, gq, rs, ad=1):
    e = QsvEnc(fmt, w, h, gq, ad=ad); out = []
    for a in rs:
        out += [b for _, b in e.encode(a)]
    assert len(out) == len(rs), (len(out), len(rs)); return out


def stats(ts):
    ts = np.asarray(ts); return dict(n=len(ts), median=float(np.median(ts)), p95=float(np.percentile(ts, 95)), p99=float(np.percentile(ts, 99)), max=float(ts.max()))


# ---------- worker ----------
def worker(args):
    mode, fmt, res, fps, n, ad, gq, bar, q = args
    out = dict(pid=os.getpid(), mode=mode, error=None)
    try:
        ctypes.windll.winmm.timeBeginPeriod(1); cv2.setNumThreads(1)
        w, h = RES[res]; rs = raws(fmt, res); t_open = time.perf_counter()
        enc = QsvEnc(fmt, w, h, gq, ad=ad, fps=max(fps, 30)) if mode == "qsv" else CvEnc(fmt)
        out["open_ms"] = (time.perf_counter() - t_open) * 1e3
        for i in range(30 + (ad or 4) + 2): enc.encode(rs[i % len(rs)])  # warm (past hold-back)
        bar.wait(timeout=120)
        per = 1.0 / fps if fps else 0; ts = []; lat = []; miss = 0; sub_t = {}
        cpu0 = time.process_time(); t0 = time.perf_counter(); base = enc.k if mode == "qsv" else 0
        for k in range(n):
            if per:
                d = t0 + k * per; r = d - time.perf_counter()
                if r > 0: time.sleep(r)
            a = rs[k % len(rs)]; ts0 = time.perf_counter()
            if mode == "qsv": sub_t[enc.k] = ts0
            r_ = enc.encode(a); te = time.perf_counter()
            ts.append((te - ts0) * 1e3)
            if mode == "qsv":
                for pts, _ in r_:
                    if pts in sub_t: lat.append((te - sub_t[pts]) * 1e3)
            else: lat.append((te - ts0) * 1e3)
            if per and te > t0 + (k + 1) * per: miss += 1
        wall = time.perf_counter() - t0; cpu = time.process_time() - cpu0
        out.update(call=stats(ts), latency=stats(lat) if lat else None, missed_period=miss, cpu_ms_per_frame=cpu / n * 1e3,
                   cores=cpu / wall, wall_s=wall, achieved_fps=n / wall)
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"; out["tb"] = traceback.format_exc()[-600:]
        try: bar.abort()
        except Exception: pass
    q.put(out)


def typeperf(sec):
    p = os.path.join(SCRATCH, "gpu.csv")
    return subprocess.Popen(["typeperf", r"\GPU Engine(*)\Utilization Percentage", "-si", "1", "-sc", str(sec), "-o", p, "-y"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL), p


def gpu_parse(path, pids):
    import csv
    rows = list(csv.reader(open(path, encoding="utf-8-sig"))); hdr = rows[0]; data = np.array([[float(x) if x.strip() else 0.0 for x in r[1:]] for r in rows[1:] if len(r) == len(hdr)])
    res = {}
    for j, name in enumerate(hdr[1:]):
        for pid in pids:
            if f"pid_{pid}_" in name:
                eng = name.split("engtype_")[-1].rstrip(")"); luid = name.split("luid_")[1].split("_phys")[0]
                res[f"{eng}|luid{luid[-6:]}"] = res.get(f"{eng}|luid{luid[-6:]}", 0) + data[:, j]
    os.remove(path)
    return {k: dict(mean_pct=float(v.mean()), max_pct=float(v.max())) for k, v in res.items() if v.max() > 0}


def cell(mode, fmt, res, fps, nproc, n, ad=None, gq=90, gpu=False):
    ctx = mp.get_context("spawn"); m = mp.Manager(); bar = m.Barrier(nproc); q = m.Queue()
    ps = [ctx.Process(target=worker, args=((mode, fmt, res, fps, n, ad, gq, bar, q),)) for _ in range(nproc)]
    tp = None
    if gpu: tp, path = typeperf(int(n / (fps or 60)) + 12 + 2 * nproc)
    [p.start() for p in ps]; [p.join() for p in ps]
    rs = [q.get() for _ in range(nproc)]; m.shutdown()
    ok = [r for r in rs if not r["error"]]; o = dict(mode=mode, fmt=fmt, res=res, fps=fps, nproc=nproc, async_depth=ad, gq=gq if mode == "qsv" else None,
                                                    failures=[r["error"] for r in rs if r["error"]], n_ok=len(ok))
    if ok:
        o.update(per_proc_median_ms=float(np.median([r["call"]["median"] for r in ok])), per_proc_p99_ms_median=float(np.median([r["call"]["p99"] for r in ok])),
                 per_proc_p99_ms_worst=max(r["call"]["p99"] for r in ok), per_proc_max_ms_worst=max(r["call"]["max"] for r in ok),
                 missed_period_total=sum(r["missed_period"] for r in ok), missed_period_pct=100 * sum(r["missed_period"] for r in ok) / (n * len(ok)),
                 cores_total=sum(r["cores"] for r in ok), cpu_ms_per_frame_mean=float(np.mean([r["cpu_ms_per_frame"] for r in ok])),
                 achieved_fps_min=min(r["achieved_fps"] for r in ok), open_ms_median=float(np.median([r["open_ms"] for r in ok])),
                 call_detail_first=ok[0]["call"], latency_first=ok[0]["latency"])
    if tp:
        tp.wait(); 
        try: o["gpu_by_pid"] = gpu_parse(path, [r["pid"] for r in rs])
        except Exception as e: o["gpu_by_pid"] = f"parse failed: {e}"
    print(json.dumps({k: v for k, v in o.items() if k not in ("call_detail_first", "latency_first")}), flush=True); return o


# ---------- stages ----------
def stage_match(R):
    R["match"] = {}
    for res, (w, h) in RES.items():
        for fmt in ("yuy2", "nv12"):
            rs = raws(fmt, res); sub, sf = SUBS[fmt]; p = [cv2.IMWRITE_JPEG_QUALITY, 90, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, sf]
            cvb = [cv2.imencode(".jpg", cv2.cvtColor(a, cv2.COLOR_YUV2BGR_YUY2 if fmt == "yuy2" else cv2.COLOR_YUV2BGR_NV12), p)[1].tobytes() for a in rs]
            cvm = float(np.median([len(b) for b in cvb])); by = {}
            for gq in range(60, 100):
                by[gq] = float(np.median([len(b) for b in qsv_all(fmt, w, h, gq, rs)]))
            best = min(by, key=lambda g: abs(by[g] - cvm))
            key = f"{res}_{fmt}"
            R["match"][key] = dict(chroma=sub, cv2_q90_median_B=cvm, qsv_matched_gq=best, qsv_matched_median_B=by[best], qsv_gq90_median_B=by[90],
                                   qsv_gq_vs_median_B={str(g): by[g] for g in range(70, 100, 3)})
            print(key, R["match"][key]["qsv_matched_gq"], cvm, by[best], by[90], flush=True)


def stage_range(R):
    """Realistic camera input is studio range. A fed it unchanged keeps the wrong levels; B (cv2 YUV2BGR_*) expands it."""
    R["range"] = {}
    for res, (w, h) in RES.items():
        for fmt in ("yuy2", "nv12"):
            full = raws(fmt, res); lim = [to_limited(fmt, a, h) for a in full]; sub, sf = SUBS[fmt]
            p = [cv2.IMWRITE_JPEG_QUALITY, 90, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, sf]; gq = R["match"][f"{res}_{fmt}"]["qsv_matched_gq"]
            def ev(outs):
                ps_ = []
                for a, b in zip(full, outs):
                    y = cv2.cvtColor(cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2YUV)[:, :, 0]; ps_.append(psnr(src_y(fmt, a, w, h), y))
                return dict(psnr_y_vs_full_median=float(np.median(ps_)), median_B=float(np.median([len(b) for b in outs])))
            d = {}
            d["B_cv2_limited_in"] = ev([cv2.imencode(".jpg", cv2.cvtColor(a, cv2.COLOR_YUV2BGR_YUY2 if fmt == "yuy2" else cv2.COLOR_YUV2BGR_NV12), p)[1].tobytes() for a in lim])
            d["A_qsv_limited_in_unchanged"] = ev(qsv_all(fmt, w, h, gq, lim))
            d["A_qsv_limited_in_host_LUT"] = ev(qsv_all(fmt, w, h, gq, [expand_lut(fmt, a, h) for a in lim]))
            for nm, f in (("lut_ms", lambda i: expand_lut(fmt, lim[i % 8], h)),):
                ts = []
                for i in range(130):
                    t0 = time.perf_counter(); f(i); ts.append((time.perf_counter() - t0) * 1e3)
                d[nm] = stats(ts[30:])
            R["range"][f"{res}_{fmt}"] = d; print(res, fmt, json.dumps(d), flush=True)


def stage_quality(R):
    R["quality"] = {}
    for res, (w, h) in RES.items():
        for fmt in ("yuy2", "nv12"):
            rs = raws(fmt, res); gq = R["match"][f"{res}_{fmt}"]["qsv_matched_gq"]; sub, sf = SUBS[fmt]
            p = [cv2.IMWRITE_JPEG_QUALITY, 90, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, sf]
            A = qsv_all(fmt, w, h, gq, rs); B = [cv2.imencode(".jpg", cv2.cvtColor(a, cv2.COLOR_YUV2BGR_YUY2 if fmt == "yuy2" else cv2.COLOR_YUV2BGR_NV12), p)[1].tobytes() for a in rs]
            d = {}
            for name, outs in (("A_qsv", A), ("B_cv2", B)):
                ps_, ss_, bias, mn, mx = [], [], [], 255, 0
                for a, b in zip(rs, outs):
                    dec = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR); assert dec is not None and dec.shape[:2] == (h, w)
                    y = cv2.cvtColor(dec, cv2.COLOR_BGR2YUV)[:, :, 0]; s = src_y(fmt, a, w, h)
                    ps_.append(psnr(s, y)); ss_.append(ssim(s, y)); bias.append(float(y.mean()) - float(s.mean()))
                    mn = min(mn, int(y.min())); mx = max(mx, int(y.max()))
                d[name] = dict(psnr_y_median=float(np.median(ps_)), psnr_y_min=min(ps_), ssim_y_median=float(np.median(ss_)), mean_Y_bias=float(np.mean(bias)),
                               dec_Y_min=mn, dec_Y_max=mx, markers=markers(outs[0]), median_B=float(np.median([len(b) for b in outs])))
            d["src_Y_min"] = int(min(src_y(fmt, a, w, h).min() for a in rs)); d["src_Y_max"] = int(max(src_y(fmt, a, w, h).max() for a in rs))
            R["quality"][f"{res}_{fmt}"] = d; print(res, fmt, json.dumps(d), flush=True)


def stage_holdback(R):
    R["holdback"] = {}
    for res, (w, h) in (("1920x1080", RES["1920x1080"]), ("1280x720", RES["1280x720"])):
        for fmt in ("yuy2", "nv12"):
            rs = raws(fmt, res)
            for label, kw in (("default", {}), ("ad1", dict(ad=1)), ("ad2", dict(ad=2)), ("ad4", dict(ad=4)), ("ad1_lowpower", dict(ad=1, low_power=1)), ("lowpower_default", dict(low_power=1))):
                key = f"{res}_{fmt}_{label}"
                try:
                    e = QsvEnc(fmt, w, h, 90, **kw); per_call = []; calls_late = []
                    for i in range(20):
                        o = e.encode(rs[i % len(rs)]); per_call.append(len(o)); calls_late += [i - pts for pts, _ in o]
                    tail = e.cc.encode(None)
                    R["holdback"][key] = dict(packets_per_call_first20=per_call, calls_late_set=sorted(set(calls_late)), frames_in_encoder_after_20=20 - sum(per_call), flush_returned=len(tail))
                except Exception as ex:
                    R["holdback"][key] = dict(error=f"{type(ex).__name__}: {ex}")
                print(key, R["holdback"][key], flush=True)
    c = CvEnc("yuy2"); R["holdback"]["cv2"] = dict(returns_same_call=bool(len(c.encode(raws("yuy2", "1280x720")[0])) > 0))


def stage_startup(R):
    R["startup"] = {}
    for res, (w, h) in RES.items():
        rs = raws("yuy2", res); ts = []
        for i in range(8):
            t0 = time.perf_counter(); e = QsvEnc("yuy2", w, h, 90, ad=1); t1 = time.perf_counter(); e.encode(rs[0]); t2 = time.perf_counter()
            ts.append(((t1 - t0) * 1e3, (t2 - t1) * 1e3))
        t0 = time.perf_counter(); e = QsvEnc("yuy2", w, h, 90); t1 = time.perf_counter()
        n = 0
        while not e.encode(rs[n % len(rs)]): n += 1
        t2 = time.perf_counter()
        R["startup"][res] = dict(open_ms_first=ts[0][0], open_ms_median=float(np.median([t[0] for t in ts])), first_call_ms_ad1_median=float(np.median([t[1] for t in ts])),
                                 default_depth_open_ms=(t1 - t0) * 1e3, default_depth_time_to_first_packet_ms=(t2 - t1) * 1e3, calls_to_first_packet_default=n + 1)
        print(res, R["startup"][res], flush=True)


def stage_single(R):
    R["single"] = {}
    for res in RES:
        for fmt in ("yuy2", "nv12"):
            gq = R["match"][f"{res}_{fmt}"]["qsv_matched_gq"]
            for fps, n in ((0, 600), (30, 600), (60, 600)):
                for mode, ad in (("qsv", 1), ("qsv", None), ("cv2", None)):
                    k = f"{res}_{fmt}_fps{fps}_{mode}{'' if ad is None else '_ad' + str(ad)}"
                    R["single"][k] = cell(mode, fmt, res, fps, 1, n, ad=ad, gq=gq, gpu=(mode == "qsv" and fps == 30))


def stage_conc(R):
    R["conc"] = {}
    gq = R["match"]["1920x1080_yuy2"]["qsv_matched_gq"]
    for nproc in (8, 16):
        for mode, ad in (("cv2", None), ("qsv", 1), ("qsv", None)):
            R["conc"][f"{nproc}_{mode}{'' if ad is None else '_ad' + str(ad)}"] = cell(mode, "yuy2", "1920x1080", 30, nproc, 300, ad=ad, gq=gq, gpu=(mode == "qsv" and ad is None))


if __name__ == "__main__":
    path = os.path.join(HERE, "results.json")
    R = json.load(open(path)) if os.path.exists(path) else {}
    R["info"] = dict(python=sys.version.split()[0], numpy=np.__version__, opencv=cv2.__version__, av=av.__version__, logical_cores=os.cpu_count(),
                     pre_cpu_pct=psutil.cpu_percent(interval=3), cv2_threads_in_workers=1)
    for s in sys.argv[1:] or ["match", "quality", "holdback", "startup", "single", "conc"]:
        globals()["stage_" + s](R); json.dump(R, open(path, "w"), indent=1)
