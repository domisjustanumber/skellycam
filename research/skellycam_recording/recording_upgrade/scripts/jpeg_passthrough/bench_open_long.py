# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "opencv-python==4.12.0.88", "numpy"]
# ///
"""TIMED bench (VERIFY_method request, for the 23:00 queue only): how long do readers take to OPEN a long
camera-JPEG recording, and is the frame count right, per container?

Why: fMP4 has no nb_frames, so OpenCV derives the count from duration x avg fps, which needs the mov demuxer to walk
every moof at open. With per-frame fragments a 30-min 30 fps file has 54,000 moof boxes. FreeMoCap opens every camera
file with cv2.VideoCapture + CAP_PROP_FRAME_COUNT (video_group_helper.py:151,159), so open cost matters.

Writes (PyAV 19.0.2, add_mux_stream passthrough) c930e_720p_flash frames LOOPED to --frames (loop stated: payload
compressibility is irrelevant to open cost; real VFR intervals looped) into fmp4_1s_tb_us, fmp4_perframe_tb_us,
mp4_tb_us, mkv. Then per file, --reps times: cv2.VideoCapture(CAP_FFMPEG) open + CAP_PROP_FRAME_COUNT wall ms, and
av.open + streams.video[0].frames wall ms. First rep after write is page-cache warm (stated); no cache drop is done.

Run (repo root, quiet machine):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/bench_open_long.py --frames 54000 --reps 5
  add --dry to only write + check counts (no timing), for a smoke test.
Writes results/jpeg_passthrough/bench/open_long.json; deletes the media.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402

FRAG1S = {"movflags": "frag_keyframe+empty_moov+default_base_moof", "min_frag_duration": "1000000"}
FRAGPF = {"movflags": "frag_keyframe+empty_moov+default_base_moof"}
CONTS = {"fmp4_1s_tb_us": ("mp4", ".mp4", FRAG1S, True), "fmp4_perframe_tb_us": ("mp4", ".mp4", FRAGPF, True),
         "mp4_tb_us": ("mp4", ".mp4", {}, True), "mkv": ("matroska", ".mkv", {}, False)}


def main() -> None:
    import av
    import cv2
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=54000)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    base = C.load_set("c930e_720p_flash")
    ts = C.real_timestamps_ns("c930e_720p_flash", base)
    d = [(b - x) // 1000 for x, b in zip(ts, ts[1:])]
    us = [0]
    for i in range(1, a.frames):
        us.append(us[-1] + d[(i - 1) % len(d)])
    out_dir = C.MEDIA / "bench_open_long"
    out_dir.mkdir(parents=True, exist_ok=True)
    res = {"meta": {"pyav": av.__version__, "opencv": cv2.__version__, "frames": a.frames, "reps": a.reps,
                    "corpus": "c930e_720p_flash looped", "dry": a.dry, "date": time.strftime("%Y-%m-%dT%H:%M:%S")}, "files": {}}
    for cont, (fmt, ext, opts, tb_us) in CONTS.items():
        p = out_dir / f"long_{cont}{ext}"
        c = av.open(str(p), "w", format=fmt, options=dict(opts))
        st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
        if tb_us:
            st.time_base = Fraction(1, 1_000_000)
        for k in range(a.frames):
            pk = av.Packet(base[k % len(base)])
            pk.stream = st
            pk.time_base = Fraction(1, 1_000_000)
            pk.pts = pk.dts = us[k]
            c.mux(pk)
        c.close()
        r = {"bytes": p.stat().st_size, "cv2_open_ms": [], "pyav_open_ms": []}
        for _ in range(1 if a.dry else a.reps):
            t0 = time.perf_counter()
            cap = cv2.VideoCapture(str(p), cv2.CAP_FFMPEG)
            n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            t1 = time.perf_counter()
            cap.release()
            t2 = time.perf_counter()
            with av.open(str(p)) as ic:
                nf = ic.streams.video[0].frames
                t3 = time.perf_counter()
            if not a.dry:
                r["cv2_open_ms"].append(round((t1 - t0) * 1e3, 2))
                r["pyav_open_ms"].append(round((t3 - t2) * 1e3, 2))
            r["cv2_frame_count"] = n
            r["pyav_stream_frames"] = nf
        # full demux packet count (no decode): what "count frames with PyAV" costs when nb_frames is absent
        t4 = time.perf_counter()
        with av.open(str(p)) as ic:
            npk = sum(1 for pk in ic.demux(ic.streams.video[0]) if pk.size > 0)
        t5 = time.perf_counter()
        r["pyav_demux_packets"] = npk
        if not a.dry:
            r["pyav_demux_count_ms"] = round((t5 - t4) * 1e3, 2)
        r["count_exact"] = r["cv2_frame_count"] == a.frames
        res["files"][cont] = r
        print(cont, r, flush=True)
        p.unlink()
    shutil.rmtree(out_dir, ignore_errors=True)
    if not a.dry:
        C.write_json(C.BENCH_RESULTS / "open_long.json", res)
    else:
        C.write_json(C.RESULTS / "verify_method_open_dry.json", res)
        print(json.dumps(res["files"]))


if __name__ == "__main__":
    main()
