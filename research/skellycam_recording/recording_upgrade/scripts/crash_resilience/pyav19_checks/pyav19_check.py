# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""PyAV 19.0.2 functional re-check of the crash_resilience PyAV-18 results (no timing).

A. Hard kill after all frames muxed (drained:150, no close) - MJPEG passthrough, NVENC H.264, SVT-AV1 - for the
   key containers; reads with ffprobe -count_frames and PyAV 19 (byte-exact for MJPEG); file size mod 262144;
   ffmpeg -c copy -> .mkv repair frame count; PyAV 19 remux with add_stream_from_template default vs opaque=True.
B. pict_type: decoded JPEG frames fed to libsvtav1 / libx264 / h264_nvenc with and without pict_type = NONE.
Writers are the study's own writer_child.py, run with this script's interpreter (PyAV 19.0.2).
usage: uv run --script pyav19_check.py <out_json>
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

SCRIPTS = Path("C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/crash_resilience")
sys.path.insert(0, str(SCRIPTS))
import common_cr as cc  # noqa: E402  (stdlib-only at import time)

MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/pyav19_check")
N = 150
MATRIX = {
    "mjpeg": ["mkv", "mkv+fp", "mkv_cl0+fp", "fmp4_every", "fmp4_every+fp", "fmp4_kf+fp", "mp4", "mp4+fp",
              "nut", "nut+fp", "avi+fp", "seg_mkv+fp"],
    "h264nv": ["mkv", "mkv+fp", "mkv_cl0+fp", "fmp4_kf+fp", "fmp4_every+fp", "mp4+fp", "nut+fp"],
    "av1": ["mkv", "mkv+fp", "mkv_cl0+fp", "webm_cl0+fp", "fmp4_every+fp", "mp4+fp"],
}


def kill_run(payload: str, cont: str) -> dict:
    out = cc.out_path(MEDIA, payload, cont, f"drained{N}")
    cc.rm(out)
    p = subprocess.Popen([sys.executable, str(SCRIPTS / "writer_child.py"), payload, cont, str(out), str(N), f"drained:{N}"],
                         stdout=subprocess.PIPE, stdin=subprocess.PIPE, text=True)
    inner = None
    last = None
    status = None
    for line in p.stdout:
        line = line.strip()
        if line.startswith("PID "):
            inner = int(line.split()[1])
        elif line.startswith("M "):
            last = line
        elif line == "IDLE":
            status = "killed_idle"
            break
        elif line.startswith(("OPENFAIL", "STREAMFAIL", "MUXFAIL")):
            status = line
            break
    if inner and status == "killed_idle":
        os.kill(inner, signal.SIGTERM)  # TerminateProcess on Windows
    try:
        p.kill()
    except Exception:
        pass
    p.wait(timeout=30)
    r = {"payload": payload, "container": cont, "status": status, "last_mux_line": last}
    if status != "killed_idle":
        return r
    kind = cc.spec(cont)[3]
    if kind == "segment":
        files = cc.segment_files(out, cc.spec(cont)[1])
        r["segment_files"] = len(files)
        r["bytes"] = sum(f.stat().st_size for f in files)
        r["ffprobe_frames_per_segment"] = [cc.ffprobe_count(str(f))["frames"] for f in files]
        r["ffprobe_frames"] = sum(r["ffprobe_frames_per_segment"])
        return r
    r["bytes"] = out.stat().st_size if out.exists() else None
    r["bytes_mod_262144"] = None if r["bytes"] is None else r["bytes"] % 262144
    fp = cc.ffprobe_count(str(out))
    r["ffprobe_frames"] = fp.get("frames")
    r["ffprobe_format_duration"] = fp.get("format_duration")
    ref = [cc.sha(b) for b in cc.load_jpegs(cc.DEFAULT_SET, N)] if payload == "mjpeg" else None
    pr = cc.pyav_read(str(out), ref_shas=ref)
    r["pyav"] = {k: pr.get(k) for k in ("frames", "packets", "byte_exact", "error", "container_duration_s", "seek")}
    if (r["ffprobe_frames"] or 0) > 0:
        rep = MEDIA / "repaired" / (out.stem + ".repaired.mkv")
        rep.parent.mkdir(parents=True, exist_ok=True)
        cc.rm(rep)
        rr = cc.remux_ffmpeg(str(out), str(rep))
        rf = cc.ffprobe_count(str(rep))
        r["ffmpeg_copy_mkv"] = {"rc": rr.get("rc"), "ffprobe_frames": rf.get("frames"), "format_duration": rf.get("format_duration")}
        r["pyav_remux_template_default"] = pyav_remux(str(out), str(MEDIA / "repaired" / (out.stem + ".pyav_default.mkv")), None)
        r["pyav_remux_template_opaque"] = pyav_remux(str(out), str(MEDIA / "repaired" / (out.stem + ".pyav_opaque.mkv")), True)
    return r


def pyav_remux(src: str, dst: str, opaque) -> dict:
    import av
    n = 0
    err = None
    try:
        with av.open(src) as ic, av.open(dst, "w") as oc:
            ist = ic.streams.video[0]
            ost = oc.add_stream_from_template(ist) if opaque is None else oc.add_stream_from_template(ist, opaque=opaque)
            for pkt in ic.demux(ist):
                if pkt.size == 0 or (pkt.dts is None and pkt.pts is None):
                    continue
                pkt.stream = ost
                oc.mux(pkt)
                n += 1
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:160]}"
    ff = cc.ffprobe_count(dst)["frames"] if os.path.exists(dst) and os.path.getsize(dst) else 0
    return {"packets": n, "error": err, "ffprobe_frames": ff}


def pict_type_run(codec: str, opts: dict, clear: bool) -> dict:
    import av
    from av.video.frame import PictureType
    jp = cc.load_jpegs(cc.DEFAULT_SET, 60)
    dec = av.CodecContext.create("mjpeg", "r")
    w, h = cc.corpus_dims()
    enc = av.CodecContext.create(codec, "w")
    enc.width, enc.height, enc.pix_fmt = w, h, "yuv420p"
    enc.time_base = Fraction(1, cc.FPS)
    enc.framerate = Fraction(cc.FPS, 1)
    enc.gop_size = 30
    enc.options = opts
    keys = pk = 0
    first_type = None
    for i, b in enumerate(jp):
        fr = dec.decode(av.Packet(b))[0]
        if first_type is None:
            first_type = str(fr.pict_type)
        f2 = fr.reformat(format="yuv420p")
        if clear:
            f2.pict_type = PictureType.NONE
        f2.pts = i
        for p in enc.encode(f2):
            pk += 1
            keys += int(p.is_keyframe)
    for p in enc.encode(None):
        pk += 1
        keys += int(p.is_keyframe)
    return {"codec": codec, "pict_type_cleared": clear, "packets": pk, "key_packets": keys, "decoded_jpeg_pict_type": first_type}


def main():
    import av
    outj = Path(sys.argv[1])
    MEDIA.mkdir(parents=True, exist_ok=True)
    ff = subprocess.run(["ffprobe", "-hide_banner", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    res = {"env": {"python": sys.version.split()[0], "pyav": av.__version__,
                   "libav": {k: ".".join(map(str, v)) for k, v in av.library_versions.items()},
                   "ffprobe_cli_used_for_reading": ff, "corpus_set": cc.DEFAULT_SET, "n": N},
           "nvidia_smi_before": cc.nvidia_smi(), "kill": [], "pict_type": []}
    for payload, conts in MATRIX.items():
        for c in conts:
            try:
                r = kill_run(payload, c)
            except Exception as e:
                r = {"payload": payload, "container": c, "error": repr(e)}
            res["kill"].append(r)
            print(payload, c, r.get("status"), r.get("ffprobe_frames"), r.get("bytes_mod_262144"), flush=True)
    for codec, opts in (("libsvtav1", {"preset": "10", "crf": "35"}), ("h264_nvenc", {"preset": "p4", "bf": "0"}),
                        ("libx264", {"preset": "ultrafast"})):
        for clear in (False, True):
            try:
                r = pict_type_run(codec, opts, clear)
            except Exception as e:
                r = {"codec": codec, "pict_type_cleared": clear, "error": repr(e)}
            res["pict_type"].append(r)
            print(r, flush=True)
    res["nvidia_smi_after"] = cc.nvidia_smi()
    outj.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
