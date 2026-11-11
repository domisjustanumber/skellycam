# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "psutil==7.2.2", "opencv-python-headless==4.12.0.88"]
# ///
# PEP 723 header added 2026-11-09 for the 23:00 bench queue: runs under PyAV 19.0.2 via `uv run --script`
# (child processes started with sys.executable inherit this environment).
"""BENCH (run on a quiet machine): CPU / wall / size overhead of crash-tolerant container settings.

Isolates the container: packets are prepared in memory first (MJPEG = the camera's own JPEG bytes; other payloads are
encoded once, then the same packets are re-muxed), so only muxing + file writing is timed.

Variants (container id from common_cr.CONTAINERS; '+fp' = flush_packets=1):
  mkv, mkv+fp, mkv_cl0+fp, fmp4_kf(+fp), fmp4_every(+fp), fmp4_frag_<ms> (+fp; frag_duration 100/500/1000/2000 ms),
  mp4 (plain), nut+fp, avi+fp, seg_mkv_<s>+fp (segment_time 1/10/60 s), rawidx (raw .mjpeg + 32-byte index, flush per
  frame), folder (one .jpg per frame)
Per variant and repeat: wall seconds, process CPU seconds (time.process_time), bytes on disk, container overhead bytes
per frame (= file bytes - payload bytes) / frames.

usage:
  python bench_fragment_overhead.py --frames 9000 --repeats 5 --payloads mjpeg,ffv1,h264nv
  (smoke: --frames 60 --repeats 1 --payloads mjpeg --out-name smoke)
writes results/crash_resilience/bench/fragment_overhead[_<out-name>].json ; temp files under MEDIA/bench_tmp (deleted)
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import struct
import sys
import time
import zlib
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_cr as cc  # noqa: E402

# Intra-only H.264/HEVC payloads (added 2026-11-09 for the 23:00 queue; HANDOFF section 1 item 10 = intra only, so the
# gop-30 'h264nv' payload is out of scope). Options = results/intra_compare/matched_settings.json target A for
# h264_nvenc_420 / hevc_nvenc_420, input class mjpeg_720p (the corpus here is c930e 720p camera JPEG); gop 0 = intra
# only for NVENC, as matched_settings 'gop_size'. Defined here, not in common_cr.PAYLOADS, so other scripts that iterate
# PAYLOADS are unchanged.
cc.PAYLOADS.setdefault("h264nv_intra", {"codec": "h264_nvenc", "pix_fmt": "yuv420p", "gop": 0, "options": {
    "preset": "p4", "tune": "ll", "rc": "constqp", "qp": "14", "i_qfactor": "1", "i_qoffset": "0", "bf": "0"}})
cc.PAYLOADS.setdefault("hevcnv_intra", {"codec": "hevc_nvenc", "pix_fmt": "yuv420p", "gop": 0, "options": {
    "preset": "p4", "tune": "ll", "rc": "constqp", "qp": "11", "i_qfactor": "1", "i_qoffset": "0", "bf": "0"}})


def prepare_packets(payload: str, n: int):
    """-> (template_path or None, list of (bytes, pts, is_key), time_base)"""
    import av
    from av.video.frame import PictureType
    jp = cc.load_jpegs(cc.DEFAULT_SET, min(n, 891))
    if payload == "mjpeg":
        return None, [(jp[i % len(jp)], round(i * 1000 / cc.FPS), True) for i in range(n)], Fraction(1, 1000)
    spec = cc.PAYLOADS[payload]
    tmp = cc.MEDIA / "bench_tmp" / f"template_{payload}.mkv"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    w, h = cc.corpus_dims()
    dec = av.CodecContext.create("mjpeg", "r")
    base = min(n, 300)
    with av.open(str(tmp), "w") as c:
        st = c.add_stream(spec["codec"], rate=cc.FPS)
        st.width, st.height, st.pix_fmt = w, h, spec["pix_fmt"]
        st.codec_context.gop_size = spec["gop"]
        st.options = dict(spec["options"])
        for i in range(base):
            fr = dec.decode(av.Packet(jp[i % len(jp)]))[0].reformat(format=spec["pix_fmt"])
            fr.pict_type = PictureType.NONE
            fr.pts = i
            fr.time_base = Fraction(1, cc.FPS)
            for p in st.encode(fr):
                c.mux(p)
        for p in st.encode(None):
            c.mux(p)
    pk = []
    with av.open(str(tmp)) as c:
        st = c.streams.video[0]
        tb = st.time_base
        for p in c.demux(st):
            if p.size:
                pk.append((bytes(p), p.pts, p.is_keyframe))
    # loop the GOP-aligned packet list to n packets with rising pts
    period = len(pk)
    loop = max(p[1] for p in pk) - min(p[1] for p in pk) + round(1 / (cc.FPS * tb))  # one frame after the last pts
    out = [(pk[i % period][0], pk[i % period][1] + (i // period) * loop, pk[i % period][2]) for i in range(n)]
    return tmp, out, tb


def variants():
    v = ["mkv", "mkv+fp", "mkv_cl0+fp", "fmp4_kf", "fmp4_kf+fp", "fmp4_every", "fmp4_every+fp", "mp4", "nut+fp", "avi+fp"]
    v += [f"fmp4_frag_{ms}+fp" for ms in (100, 500, 1000, 2000)]
    v += [f"seg_mkv_{s}+fp" for s in (1, 10, 60)]
    v += ["rawidx", "folder"]
    return v


def resolve(v: str):
    fp = v.endswith("+fp")
    b = v[:-3] if fp else v
    if b.startswith("fmp4_frag_"):
        fmt, ext, opts, kind = "mp4", "mp4", {"movflags": "empty_moov+default_base_moof",
                                              "frag_duration": str(int(b.split("_")[2]) * 1000)}, "file"
    elif b.startswith("seg_mkv_"):
        fmt, ext, opts, kind = "segment", "mkv", {"segment_format": "matroska", "segment_time": b.split("_")[2],
                                                  "reset_timestamps": "0"}, "segment"
    else:
        fmt, ext, opts, kind = cc.CONTAINERS[b]
        opts = dict(opts)
    if fp:
        opts = {**opts, "flush_packets": "1"}
    return fmt, ext, opts, kind


def run_one(v, template, pkts, tb, workdir: Path, payload: str):
    import av
    fmt, ext, opts, kind = resolve(v)
    out = workdir / f"o_{v.replace('+', '_')}"
    cc.rm(out)
    if kind != "file":
        out.mkdir(parents=True)
    t0w = time.perf_counter()
    t0c = time.process_time()
    if kind == "rawidx":
        with open(out / "frames.mjpeg", "wb") as fd, open(out / "frames.idx", "wb") as fi:
            off = 0
            for i, (b, pts, k) in enumerate(pkts):
                fd.write(b)
                fd.flush()
                fi.write(cc.IDX_REC.pack(i, off, len(b), zlib.crc32(b), pts))
                fi.flush()
                off += len(b)
    elif kind == "folder":
        for i, (b, pts, k) in enumerate(pkts):
            with open(out / f"frame_{i:06d}.jpg", "wb") as f:
                f.write(b)
    else:
        target = str(out) + f".{ext}" if kind == "file" else str(out / f"seg_%05d.{ext}")
        with av.open(target, "w", format=fmt, options=opts) as c:
            if template is None:
                st = c.add_stream("mjpeg", rate=cc.FPS)
                w, h = cc.corpus_dims()
                st.width, st.height, st.pix_fmt = w, h, "yuvj422p"
            else:
                with av.open(str(template)) as ic:
                    st = c.add_stream_from_template(ic.streams.video[0], opaque=True)
            for b, pts, k in pkts:
                p = av.Packet(b)
                p.stream = st
                p.time_base = tb
                p.pts = p.dts = pts
                p.is_keyframe = k
                c.mux(p)
        if kind == "file":
            out = Path(target)
    wall = time.perf_counter() - t0w
    cpu = time.process_time() - t0c
    size = out.stat().st_size if out.is_file() else sum(f.stat().st_size for f in out.iterdir())
    payload_bytes = sum(len(b) for b, _, _ in pkts)
    cc.rm(out)
    return {"wall_s": wall, "cpu_s": cpu, "bytes": size, "payload_bytes": payload_bytes,
            "overhead_bytes_per_frame": (size - payload_bytes) / len(pkts)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=9000)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--payloads", default="mjpeg,ffv1,h264nv")
    ap.add_argument("--variants", default=None)
    ap.add_argument("--out-name", default="")
    a = ap.parse_args()
    cc.BENCH.mkdir(parents=True, exist_ok=True)
    work = cc.MEDIA / "bench_tmp"
    work.mkdir(parents=True, exist_ok=True)
    res = {"env": cc.env_versions(), "frames": a.frames, "repeats": a.repeats, "nvidia_smi_before": cc.nvidia_smi(),
           "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": []}
    vl = a.variants.split(",") if a.variants else variants()
    for payload in a.payloads.split(","):
        template, pkts, tb = prepare_packets(payload, a.frames)
        for v in vl:
            if v in ("rawidx", "folder") and payload != "mjpeg":
                continue
            if v.startswith("avi") and payload.startswith(("h264nv", "hevcnv")):
                continue  # MKV-template H.264 packets are AVCC; the AVI muxer rejected them in the smoke test
            reps = []
            err = None
            for r in range(a.repeats):
                try:
                    reps.append(run_one(v, template, pkts, tb, work, payload))
                except Exception as e:
                    err = f"{type(e).__name__}: {e}"
                    break
            row = {"payload": payload, "variant": v, "repeats": reps, "error": err}
            if reps:
                for k in ("wall_s", "cpu_s"):
                    row[f"{k}_median"] = statistics.median(x[k] for x in reps)
                row["cpu_us_per_frame_median"] = row["cpu_s_median"] / a.frames * 1e6
                row["bytes"] = reps[0]["bytes"]
                row["overhead_bytes_per_frame"] = reps[0]["overhead_bytes_per_frame"]
            res["results"].append(row)
            print(payload, v, {k: row.get(k) for k in ("wall_s_median", "cpu_us_per_frame_median", "overhead_bytes_per_frame", "error")}, flush=True)
            out = cc.BENCH / f"fragment_overhead{'_' + a.out_name if a.out_name else ''}.json"
            out.write_text(json.dumps(res, indent=1))
    res["nvidia_smi_after"] = cc.nvidia_smi()
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    out = cc.BENCH / f"fragment_overhead{'_' + a.out_name if a.out_name else ''}.json"
    out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
