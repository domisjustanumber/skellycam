"""P11 - is a recording still readable after its writer process is killed without release()? (REVISION stage, 2026-10-28)

Brought into the benchmark tree from the priorities critic's one-off test
(C:\\Users\\Dom\\AppData\\Local\\Temp\\skellycam_frame_pipeline_tmp\\critic_p1\\crash_container_test.py) and extended with the
crash-tolerant containers the critic proposed. NOT SkellyCam code.

Writers (each in a spawned child, 1280x720 and 1920x1080 BGR, 60 fps timebase):
  msmf_mp4        cv2.VideoWriter fourcc 'X264' -> MSMF H.264 .mp4 = SkellyCam's default writer
                  (camera_config.py L29 'X264' + fourcc_codec_helpers.py L54-58 @23ccbf20)
  mjpeg_mkv       PyAV mjpeg packets (cv2.imencode q90) muxed into .mkv = the P8 passthrough recorder
  nvenc_fmp4      PyAV h264_nvenc into .mp4 with movflags=frag_keyframe+empty_moov (fragmented MP4), g=60
  nvenc_mkv       PyAV h264_nvenc into .mkv, g=60
Modes:
  clean           write N frames, release/close, then the parent terminates the idle child
  killed_idle     write N frames, signal, then sleep; the parent calls Process.terminate() (TerminateProcess on Windows:
                  no finally, no release) - what WorkerRegistry.shutdown_all does after its timeout and what a hard crash does
  killed_mid      write N frames, signal, and KEEP WRITING until killed (crash while the writer is busy)
Each file is then probed: cv2 frames decoded and PyAV frames decoded (or the open error). Expected >= N for every row.

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam):
  .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\p11_crash_container.py
Output: prototypes/results/p11_crash_container.json and .md
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

N = 300  # 5 s at 60 fps
SIZES = {"720p": (720, 1280), "1080p": (1080, 1920)}
KINDS = [("msmf_mp4", "mp4"), ("mjpeg_mkv", "mkv"), ("nvenc_fmp4", "mp4"), ("nvenc_mkv", "mkv")]
MODES = ["clean", "killed_idle", "killed_mid"]


def child(kind, path, h, w, ready, mode, err_q):
    import cv2
    import av
    import numpy as np
    import proto_common as pcm
    try:
        fr = pcm.synthetic_frames(h, w, n=30, seed=0, noise=8)
        if kind == "msmf_mp4":
            vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"X264"), 60, (w, h))

            def put(i):
                vw.write(fr[i % 30])

            def close():
                vw.release()
        else:
            opts = {"movflags": "frag_keyframe+empty_moov"} if kind == "nvenc_fmp4" else {}
            c = av.open(path, "w", options=opts)
            if kind == "mjpeg_mkv":
                st = c.add_stream("mjpeg", rate=60)
                st.width, st.height, st.pix_fmt = w, h, "yuvj420p"
                jp = [cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes() for f in fr]

                def put(i):
                    pk = av.Packet(jp[i % 30])
                    pk.stream = st
                    pk.time_base = Fraction(1, 60)
                    pk.pts = pk.dts = i
                    c.mux(pk)

                def close():
                    c.close()
            else:
                st = c.add_stream("h264_nvenc", rate=60)
                st.width, st.height, st.pix_fmt = w, h, "yuv420p"
                st.options = {"preset": "p4", "tune": "ll", "rc": "vbr", "cq": "23", "g": "60", "bf": "0"}
                i420 = [cv2.cvtColor(f, cv2.COLOR_BGR2YUV_I420) for f in fr]

                def put(i):
                    f = av.VideoFrame.from_ndarray(i420[i % 30], format="yuv420p")
                    f.pts = i
                    for pk in st.encode(f):
                        c.mux(pk)

                def close():
                    for pk in st.encode():
                        c.mux(pk)
                    c.close()
        for i in range(N):
            put(i)
        if mode == "clean":
            close()
        ready.set()
        i = N
        if mode == "killed_mid":
            t_next = time.perf_counter()
            while True:  # keep writing at 60 fps until terminated
                put(i)
                i += 1
                t_next += 1 / 60
                d = t_next - time.perf_counter()
                if d > 0:
                    time.sleep(d)
        time.sleep(120)
    except Exception as e:  # noqa: BLE001
        err_q.put(f"{type(e).__name__}: {e}")
        ready.set()


def probe(path: str) -> dict:
    import cv2
    import av
    out = {"exists": os.path.exists(path), "bytes": os.path.getsize(path) if os.path.exists(path) else 0}
    cap = cv2.VideoCapture(path)
    out["cv2_opened"] = bool(cap.isOpened())
    n = 0
    if cap.isOpened():
        while cap.grab():
            n += 1
    cap.release()
    out["cv2_frames_decoded"] = n
    try:
        with av.open(path) as c:
            m = 0
            for _ in c.decode(video=0):
                m += 1
            out["pyav_frames_decoded"] = m
    except Exception as e:  # noqa: BLE001
        out["pyav_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out


def main():
    import proto_common as pcm
    out_dir = pcm.SCRATCH_TMP / "p11_crash"
    out_dir.mkdir(parents=True, exist_ok=True)
    res = dict(env=pcm.env_summary(), frames_before_signal=N, rows=[])
    ctx = mp.get_context("spawn")
    for size, (h, w) in SIZES.items():
        for kind, ext in KINDS:
            for mode in MODES:
                path = str(out_dir / f"{kind}_{size}_{mode}.{ext}")
                if os.path.exists(path):
                    os.remove(path)
                ready, eq = ctx.Event(), ctx.Queue()
                p = ctx.Process(target=child, args=(kind, path, h, w, ready, mode, eq))
                t0 = time.perf_counter()
                p.start()
                ready.wait(180)
                time.sleep(1.0 if mode == "killed_mid" else 0.5)  # killed_mid: about 60 more frames written
                p.terminate()
                p.join(10)
                err = None if eq.empty() else eq.get()
                r = dict(size=size, kind=kind, mode=mode, exitcode=p.exitcode, child_error=err, wall_s=round(time.perf_counter() - t0, 2))
                r.update(probe(path))
                r["readable_ge_N"] = (r.get("pyav_frames_decoded") or 0) >= N or r["cv2_frames_decoded"] >= N
                res["rows"].append(r)
                print(json.dumps(r), flush=True)
                try:
                    os.remove(path)
                except OSError:
                    pass
                pcm.write_json("p11_crash_container.json", res)
    L = ["# P11 - is the recording readable after the writer process is killed without release()?", "",
         f"{N} frames written before the parent's signal; killed_mid keeps writing at 60 fps for about 1 s more before "
         "Process.terminate() (TerminateProcess). Files are deleted after probing.", "",
         "| size | writer / container | mode | exit code | bytes | cv2 frames decoded | PyAV frames decoded (or error) | >= 300 readable | child error |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        L.append(f"| {r['size']} | {r['kind']} | {r['mode']} | {r['exitcode']} | {r['bytes']} | {r['cv2_frames_decoded']} | "
                 f"{r.get('pyav_frames_decoded', r.get('pyav_error'))} | {r['readable_ge_N']} | {r['child_error'] or ''} |")
    pcm.write_text("p11_crash_container.md", "\n".join(L) + "\n")
    print("\n".join(L))
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
