# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "opencv-python==4.12.0.88"]
# ///
"""Adversarial verifier (method lens) functional checks, PyAV 19.0.2. No timing.
1. Container-level decode (packet flags kept) of the PyAV 19 killed / truncated files: packet.is_corrupt,
   frame.is_corrupt, decode errors on the torn tail (the lean re-check re-wrapped the bytes in av.Packet(),
   which drops demuxer packet flags).
2. Killed-file sizes vs 32 KiB multiples.
3. VFR confounder: compat clips re-made with (a) the original vfr_pts_ms pattern, (b) jitter only (no 67 ms gap),
   (c) original pattern shifted so the first PTS is >= 0; MJPEG MKV, MJPEG fMP4, SVT-AV1 MP4; cv2 probe_clip.
   Also logs the SVT-AV1 encoder's first packet PTS before muxing.
"""
import json, sys
from fractions import Fraction
from pathlib import Path
import av, cv2
S = Path("C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/python_integration")
sys.path.insert(0, str(S))
import cv2_read_probe as cp
import make_compat_clips as mc
RAW = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration")
out = {"pyav": av.__version__, "ffmpeg": av.ffmpeg_version_info, "opencv": cv2.__version__, "date": "2026-11-09"}

def container_decode(p: Path) -> dict:
    o = {"file": p.name, "bytes": p.stat().st_size, "bytes_mod_32KiB": p.stat().st_size % 32768}
    pk_corrupt, fr_corrupt, n_pk, n_fr, err, last = [], [], 0, 0, None, None
    try:
        with av.open(str(p)) as c:
            s = c.streams.video[0]
            for pkt in c.demux(s):
                if pkt.size == 0:
                    continue
                n_pk += 1
                last = (n_pk - 1, pkt.size)
                if pkt.is_corrupt:
                    pk_corrupt.append(n_pk - 1)
                try:
                    for f in pkt.decode():
                        n_fr += 1
                        if f.is_corrupt:
                            fr_corrupt.append(n_fr - 1)
                except Exception as e:
                    err = f"pkt {n_pk-1}: {e!r}"[:160]
    except Exception as e:
        err = repr(e)[:160]
    o.update(packets=n_pk, frames=n_fr, last_packet=last, packets_flagged_corrupt=pk_corrupt,
             frames_flagged_corrupt=fr_corrupt, error=err)
    return o

k = RAW / "crash_pyav19/kill"; t = RAW / "crash_pyav19/truncate"
out["killed_container_decode"] = [container_decode(k / n) for n in
    ["killed.mkv.real.mkv", "killed.mp4f.real.mp4", "killed.avi.index.avi"]]
out["truncated_container_decode"] = [container_decode(t / n) for n in
    ["cut_50pct.mp4f.real.mp4", "cut_90pct.avi.index.avi", "cut_50pct.mkv.real.mkv"]]
for r in out["killed_container_decode"] + out["truncated_container_decode"]:
    print(r)

def gap_free(i):  # jitter only, no 67 ms drop gap
    return round(i * 1000 / 30) + ((i * 37) % 7 - 3)
def shifted(i):
    return mc.vfr_pts_ms(i) + 3
PATTERNS = {"orig": mc.vfr_pts_ms, "jitter_only": gap_free, "orig_nonneg": shifted}
CLIPS = {"mjpeg_mkv": ("matroska", "mkv", "mjpeg", "yuvj422p", {"qmin": "2", "qmax": "4"}, 1, {}),
         "mjpeg_mp4frag": ("mp4", "mp4", "mjpeg", "yuvj422p", {"qmin": "2", "qmax": "4"}, 1,
                           {"movflags": "frag_keyframe+empty_moov+default_base_moof"}),
         "av1svt_mp4": ("mp4", "mp4", "libsvtav1", "yuv420p", {"crf": "35", "preset": "10"}, 30, {})}
D = RAW / "verify_method_vfr"; D.mkdir(parents=True, exist_ok=True)
files = sorted((mc.CORPUS / "c930e_720p_flash").glob("frame_*.jpg"))[:mc.N]
src = []
for i, f in enumerate(files):
    with av.open(str(f)) as c:
        rgb = next(c.decode(video=0)).to_ndarray(format="rgb24")
    mc.barcode(rgb, i); src.append(rgb)
out["vfr"] = {}
for cname, (fmt, ext, codec, pix, opts, gop, mux_opts) in CLIPS.items():
    for pname, fn in PATTERNS.items():
        if cname != "av1svt_mp4" and pname == "orig_nonneg":
            continue
        path = D / f"{cname}_{pname}.{ext}"
        if path.exists(): path.unlink()
        enc_first = []
        with av.open(str(path), "w", format=fmt, options=mux_opts) as c:
            s = c.add_stream(codec, rate=30)
            s.width, s.height, s.pix_fmt = 1280, 720, pix
            s.codec_context.gop_size = gop
            if gop == 1: s.codec_context.max_b_frames = 0
            s.options = opts
            tb = Fraction(1, 1000); s.codec_context.time_base = tb
            for i, rgb in enumerate(src):
                vf = av.VideoFrame.from_ndarray(rgb, format="rgb24").reformat(format=pix)
                vf.pts = fn(i); vf.time_base = tb
                for p in s.encode(vf):
                    if len(enc_first) < 3: enc_first.append((p.pts, p.dts, str(p.time_base)))
                    c.mux(p)
            for p in s.encode():
                c.mux(p)
        with av.open(str(path)) as c:
            st = c.streams.video[0]
            dec = sum(1 for _ in c.decode(st))
            first_pk = [(p.pts, bool(p.is_discard) if hasattr(p, "is_discard") else None) for _, p in zip(range(2), c.demux(st))] if False else None
        r = {"first_pts_ms": [fn(i) for i in range(3)], "encoder_first_packets": enc_first, "pyav_decoded": dec,
             "cv2": cp.probe_clip(path, cv2.CAP_FFMPEG, mc.N, True)}
        out["vfr"][f"{cname}_{pname}"] = r
        f = r["cv2"]
        print(cname, pname, enc_first[:2], dec, f.get("frame_count_prop"), f.get("frames_read"), f.get("sequence_exact"), f.get("seek_results"))
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str))
print("wrote", sys.argv[1])
