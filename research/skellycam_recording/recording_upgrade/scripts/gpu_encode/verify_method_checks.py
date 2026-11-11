# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Verifier (method) functional checks, PyAV 19.0.2, NO timing.
a) hevc_qsv: does the 'gpb' option reach the encoder? (verbose log lines mentioning GPB, gpb=0 vs 1)
b) pixel fidelity: Y-plane PSNR of existing encoder outputs vs the NV12 source frames (decode with PyAV software decoders)
c) mjpeg_qsv decode: raw Y plane (no swscale) vs CPU mjpeg Y plane; color_range; fit of limited-range mapping; chroma
Writes JSON to argv[1].
"""
import json
import sys
from pathlib import Path

import av
import av.logging
import numpy as np

MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode")
CORPUS = MEDIA.parent / "corpus"
W, H, N = 1920, 1080, 8
out: dict = {"pyav": av.__version__}

raw = (MEDIA / "inputs/nv12_1080p.yuv").read_bytes()
fs = W * H * 3 // 2
src_y = [np.frombuffer(raw[i * fs:i * fs + W * H], np.uint8).reshape(H, W) for i in range(N)]

# a) gpb option
out["gpb"] = {}
tmp = Path(sys.argv[2])
tmp.mkdir(parents=True, exist_ok=True)
for gpb in ("0", "1"):
    av.logging.set_level(av.logging.VERBOSE)
    with av.logging.Capture() as logs:
        rec = {}
        try:
            dst = tmp / f"gpb{gpb}.mkv"
            with av.open(str(dst), "w") as c:
                s = c.add_stream("hevc_qsv", rate=30, options={"gpb": gpb})
                s.width, s.height, s.pix_fmt = W, H, "nv12"
                s.codec_context.gop_size = 15
                s.codec_context.max_b_frames = 0
                rec["codec_context_options_after_open_attempt"] = dict(s.codec_context.options)
                for i in range(4):
                    vf = av.VideoFrame.from_ndarray(np.frombuffer(raw[(i % N) * fs:(i % N + 1) * fs], np.uint8).reshape(H * 3 // 2, W), format="nv12")
                    vf.pts = i
                    for p in s.encode(vf):
                        c.mux(p)
                for p in s.encode(None):
                    c.mux(p)
            rec["ok"] = True
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)[:300]
    av.logging.set_level(None)
    rec["log_gpb_lines"] = [l[2].strip() for l in logs if "gpb" in l[2].lower() or "GPB" in l[2]][:10]
    rec["log_unused_option_lines"] = [l[2].strip() for l in logs if "not used" in l[2].lower() or "unused" in l[2].lower()][:10]
    out["gpb"][gpb] = rec

# b) PSNR of existing outputs vs source (Y plane)
def psnr(a, b):
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float("inf") if mse == 0 else 10 * np.log10(255 ** 2 / mse)

out["psnr_y"] = {}
files = sorted((MEDIA / "qsv_recheck_19.0.2").glob("*_sw.mkv")) + sorted((MEDIA / "pyav_19.0.2").glob("*"))
for f in files:
    rec = {}
    try:
        with av.open(str(f)) as c:
            vs = c.streams.video[0]
            ys = []
            rng = set()
            for fr in c.decode(vs):
                pl = fr.planes[0]
                arr = np.frombuffer(bytes(pl), np.uint8).reshape(pl.height, pl.line_size)[:, :pl.width]
                ys.append(arr[:H, :W].copy())
                rng.add(str(getattr(fr, "color_range", "?")))
                fmt = fr.format.name
        p = [psnr(ys[i], src_y[i % N]) for i in range(len(ys))]
        rec = {"frames": len(ys), "fmt": fmt, "color_range": sorted(rng), "psnr_y_min": round(min(p), 2),
               "psnr_y_mean": round(float(np.mean(p)), 2),
               "mean_y_out_minus_src": round(float(np.mean([ys[i].astype(float).mean() - src_y[i % N].mean() for i in range(len(ys))])), 3)}
    except Exception as e:  # noqa: BLE001
        rec = {"error": repr(e)[:200]}
    out["psnr_y"][f"{f.parent.name}/{f.name}"] = rec

# c) mjpeg_qsv raw planes
out["mjpeg_qsv_raw"] = []
for setname in ("c930e_1080p", "c930e_720p_flash"):
    jpgs = sorted((CORPUS / setname).glob("frame_*.jpg"))[:5]
    res = {}
    for mode in ("mjpeg", "mjpeg_qsv"):
        cc = av.CodecContext.create(mode, "r")
        frs = []
        for j in jpgs:
            frs += list(cc.decode(av.Packet(j.read_bytes())))
        frs += list(cc.decode(None))
        res[mode] = frs
    rec = {"set": setname}
    a, b = res["mjpeg"], res["mjpeg_qsv"]
    rec["cpu_fmt"], rec["qsv_fmt"] = a[0].format.name, b[0].format.name
    rec["cpu_color_range"], rec["qsv_color_range"] = str(a[0].color_range), str(b[0].color_range)
    def yplane(fr):
        pl = fr.planes[0]
        return np.frombuffer(bytes(pl), np.uint8).reshape(pl.height, pl.line_size)[:fr.height, :fr.width].astype(np.float64)
    diffs_raw, diffs_lim, fits = [], [], []
    for k in range(min(len(a), len(b))):
        ya, yb = yplane(a[k]), yplane(b[k])
        diffs_raw.append(np.abs(ya - yb))
        ya_lim = ya * 219.0 / 255.0 + 16.0  # full -> limited
        diffs_lim.append(np.abs(ya_lim - yb))
        A = np.vstack([ya.ravel(), np.ones(ya.size)]).T
        slope, icpt = np.linalg.lstsq(A, yb.ravel(), rcond=None)[0]
        fits.append((slope, icpt))
    rec["y_raw_mean_abs"] = round(float(np.mean([d.mean() for d in diffs_raw])), 3)
    rec["y_raw_max_abs"] = float(max(d.max() for d in diffs_raw))
    rec["y_after_full_to_limited_mean_abs"] = round(float(np.mean([d.mean() for d in diffs_lim])), 3)
    rec["y_after_full_to_limited_max_abs"] = round(float(max(d.max() for d in diffs_lim)), 2)
    rec["lstsq_qsv_vs_cpu_slope_intercept"] = [round(float(np.mean([f[0] for f in fits])), 4), round(float(np.mean([f[1] for f in fits])), 3)]
    rec["cpu_y_min_max"] = [float(yplane(a[0]).min()), float(yplane(a[0]).max())]
    rec["qsv_y_min_max"] = [float(yplane(b[0]).min()), float(yplane(b[0]).max())]
    out["mjpeg_qsv_raw"].append(rec)

Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str))
print(json.dumps(out, indent=1, default=str))
