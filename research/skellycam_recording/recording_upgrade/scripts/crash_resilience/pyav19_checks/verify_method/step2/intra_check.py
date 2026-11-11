# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""VERIFY_method step2 (2026-11-10), functional only, no timing reported:
A. encoder hold-back of the in-scope intra NVENC settings (bench_fragment_overhead.py:42-46), 75 frames paced 30 fps.
B. rt kill (paced 30 fps, TerminateProcess once 75 frames fed) of h264nv_intra / hevcnv_intra into mkv+fp.
usage: uv run --script intra_check.py <out_json>"""
import json, os, signal, subprocess, sys, time
from fractions import Fraction
from pathlib import Path
SCR = Path("C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/crash_resilience")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(SCR))
import common_cr as cc
import av
from av.video.frame import PictureType
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/verify_method_step2")
MEDIA.mkdir(parents=True, exist_ok=True)
INTRA = {"h264nv_intra": ("h264_nvenc", {"preset": "p4", "tune": "ll", "rc": "constqp", "qp": "14", "i_qfactor": "1", "i_qoffset": "0", "bf": "0"}),
         "hevcnv_intra": ("hevc_nvenc", {"preset": "p4", "tune": "ll", "rc": "constqp", "qp": "11", "i_qfactor": "1", "i_qoffset": "0", "bf": "0"})}
res = {"env": {"pyav": av.__version__, "libavcodec": ".".join(map(str, av.library_versions["libavcodec"]))}, "hold": [], "rt": []}

def hold(codec, opts, fed=75):
    jp = cc.load_jpegs(cc.DEFAULT_SET, fed)
    dec = av.CodecContext.create("mjpeg", "r")
    frames = []
    for b in jp:
        f2 = dec.decode(av.Packet(b))[0].reformat(format="yuv420p"); f2.pict_type = PictureType.NONE; frames.append(f2)
    w, h = cc.corpus_dims()
    enc = av.CodecContext.create(codec, "w")
    enc.width, enc.height, enc.pix_fmt = w, h, "yuv420p"
    enc.time_base = Fraction(1, cc.FPS); enc.framerate = Fraction(cc.FPS, 1); enc.gop_size = 0
    enc.options = dict(opts)
    got = 0; keys = 0; t0 = time.perf_counter()
    for i, f in enumerate(frames):
        dt = t0 + i / cc.FPS - time.perf_counter()
        if dt > 0: time.sleep(dt)
        f.pts = i
        pk = enc.encode(f); got += len(pk); keys += sum(p.is_keyframe for p in pk)
    pk = enc.encode(None)
    keys += sum(p.is_keyframe for p in pk)
    return {"codec": codec, "options": opts, "gop_size": 0, "fed": fed, "packets_before_drain": got,
            "held_by_encoder": fed - got, "packets_from_drain": len(pk), "keyframe_packets_total": keys}

for name, (codec, opts) in INTRA.items():
    try: r = hold(codec, opts)
    except Exception as e: r = {"codec": codec, "error": repr(e)}
    res["hold"].append(r); print(r, flush=True)

def rt_kill(p, c="mkv+fp", kill_fed=75):
    out = cc.out_path(MEDIA, p, c, "rt75"); cc.rm(out)
    pr = subprocess.Popen([sys.executable, str(HERE / "child_wrap.py"), p, c, str(out), "150", "rt"],
                          stdout=subprocess.PIPE, stdin=subprocess.PIPE, text=True)
    inner = None; last = None
    for line in pr.stdout:
        line = line.strip()
        if line.startswith("PID "): inner = int(line.split()[1])
        elif line.startswith("M "):
            last = line
            if int(line.split()[2]) >= kill_fed:
                os.kill(inner, signal.SIGTERM); break
        elif line.startswith(("OPENFAIL", "STREAMFAIL", "MUXFAIL")):
            last = line; break
    try: pr.kill()
    except Exception: pass
    pr.wait(timeout=30)
    r = {"payload": p, "container": c, "last_mux_line_seen": last, "bytes": out.stat().st_size if out.exists() else None}
    fp = cc.ffprobe_count(str(out)); r["ffprobe_frames"] = fp.get("frames")
    pr2 = cc.pyav_read(str(out), ref_shas=None)
    r["pyav"] = {k: pr2.get(k) for k in ("frames", "packets", "error", "seek")}
    try:
        with av.open(str(out)) as ic:
            ks = [pkt.is_keyframe for pkt in ic.demux(ic.streams.video[0]) if pkt.size]
        r["demux_packets"] = len(ks); r["demux_keyframes"] = sum(ks)
    except Exception as e:
        r["demux_error"] = repr(e)
    return r

for p in INTRA:
    try: r = rt_kill(p)
    except Exception as e: r = {"payload": p, "error": repr(e)}
    res["rt"].append(r); print(r, flush=True)
Path(sys.argv[1]).write_text(json.dumps(res, indent=1))
