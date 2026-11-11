"""Build the media for the overlay-in-Chromium functional tests (G3, also feeds G9).

Input: real camera JPEGs, corpus set c930e_720p_flash, frames 0..N-1 (1280x720, decoded with OpenCV).
Each base frame gets a frame-index barcode in the bottom 40 rows (y 680..719):
    16 blocks of 80x40 px; block k (left to right) = bit k; bits 0..11 = frame index, bits 12..15 = popcount(index) & 15.
    White = 1, black = 0. The browser samples each block centre and thresholds luma at 128.
The overlay layers carry their OWN barcode (opaque) in a strip y 60..99, x 0..639 (16 blocks of 40x40),
so the alignment of overlay vs video can be read back from pixels.

Outputs (media, outside the repo): <raw>/overlays/media/
  base_cfr_h264.mp4      libx264 yuv420p, GOP 30, CFR 30 (today's codec family)
  base_cfr_vp9.webm      libvpx-vp9, GOP 30, CFR 30
  base_cfr_av1.webm      libsvtav1, GOP 30, CFR 30
  base_vfr_vp9.webm      libvpx-vp9 with jittered pts (+-4 ms) and a 2-frame gap after frame N/2  (time_base 1/1000)
  base_vfr_h264.mp4      libx264, same pts (time_base 1/90000)
  overlay_vp9alpha.webm  overlay-only layer, VP9 with alpha (yuva420p), via ffmpeg CLI from BGRA
  overlay_png.mov        overlay-only layer, PNG in MOV (rgba)
  overlay_qtrle.mov      overlay-only layer, QuickTime Animation (argb)
  overlay.vtt            WebVTT metadata cues, one per frame, cue id = frame index, JSON payload; CFR timing
  overlay_vfr.vtt        same, cue times = the VFR file's pts
  overlay_half.vtt       CFR cues shifted half a frame earlier: cue f = [(f-0.5)/30, (f+0.5)/30)
  overlay.jsonl          JSON-lines sidecar (frame, timestamp, skeleton, charuco) - what the canvas renderer draws
  overlay.ass            ASS subtitle version (text + \\p drawing)
  base_vp9_vtt_inband.webm  base_cfr_vp9 + overlay.vtt muxed in-band (WebVTT in WebM)
  base_vp9_ass.mkv       base_cfr_vp9 + overlay.ass muxed (ASS in Matroska)
  truncated/overlay_trunc.vtt, truncated/overlay_trunc.svg  (cut at 50 %)
  pts_<name>.json        presentation timestamps (s) per frame, from ffprobe (what the player's lookup uses)
Results (text): results/overlays/make_test_media.json (versions, ffmpeg return codes, sizes, ffprobe summaries)

Run from repo root:
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/make_test_media.py [--frames 300]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import overlay_model as M  # noqa: E402

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus/c930e_720p_flash")
OUT = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/overlays/media")
RES = HERE.parents[1] / "results" / "overlays"
W, H, FPS = 1280, 720, 30


def code_bits(i: int) -> list[int]:
    return [(i >> k) & 1 for k in range(12)] + [((bin(i).count("1") & 15) >> k) & 1 for k in range(4)]


def stamp_base(img: np.ndarray, i: int) -> None:
    for k, b in enumerate(code_bits(i)):
        img[680:720, k * 80:(k + 1) * 80] = 255 if b else 0


def stamp_overlay_bgra(img: np.ndarray, i: int) -> None:
    for k, b in enumerate(code_bits(i)):
        img[60:100, k * 40:(k + 1) * 40, :3] = 255 if b else 0
        img[60:100, k * 40:(k + 1) * 40, 3] = 255


def vfr_pts_ms(n: int) -> list[int]:
    rng = np.random.default_rng(7)
    out, t = [], 0.0
    for i in range(n):
        if i == n // 2:
            t += 2 * 1000 / FPS  # two dropped frames
        out.append(int(round(t + rng.uniform(-4, 4))) if i else 0)
        t += 1000 / FPS
    return out


def encode_pyav(path: Path, frames_bgr, codec: str, pts=None, tb=Fraction(1, FPS), opts=None):
    with av.open(str(path), "w") as c:
        s = c.add_stream(codec, rate=FPS, options=opts or {})
        s.width, s.height, s.pix_fmt = W, H, "yuv420p"
        s.time_base = tb
        s.codec_context.time_base = tb
        s.gop_size = 30
        for i, img in enumerate(frames_bgr):
            vf = av.VideoFrame.from_ndarray(img, format="bgr24")
            vf.pts = i if pts is None else pts[i]
            vf.time_base = tb
            for p in s.encode(vf):
                c.mux(p)
        for p in s.encode():
            c.mux(p)


def ffprobe_pts(path: Path) -> list[float]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return sorted(float(x.split(",")[0]) for x in r.stdout.split() if x.strip() and x.strip() != "N/A")


def run(cmd, log, name, stdin_bytes=None):
    r = subprocess.run(cmd, input=stdin_bytes, capture_output=True)
    log[name] = {"cmd": " ".join(str(c) for c in cmd if not isinstance(c, bytes))[:600], "rc": r.returncode,
                 "stderr_tail": r.stderr.decode("utf-8", "replace")[-600:] if r.returncode else ""}
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=300)
    a = ap.parse_args()
    n = a.frames
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "truncated").mkdir(exist_ok=True)
    RES.mkdir(parents=True, exist_ok=True)
    log = {"pyav": av.__version__, "libavcodec": ".".join(map(str, av.library_versions["libavcodec"])),
           "opencv": cv2.__version__, "frames": n, "source": str(CORPUS), "steps": {}}
    log["ffmpeg"] = subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True, text=True).stdout.splitlines()[0]

    base = []
    for i in range(n):
        img = cv2.imdecode(np.fromfile(CORPUS / f"frame_{i:06d}.jpg", np.uint8), cv2.IMREAD_COLOR)
        assert img.shape == (H, W, 3)
        stamp_base(img, i)
        base.append(img)

    steps = log["steps"]
    for name, codec, opts in (("base_cfr_h264.mp4", "libx264", {"preset": "veryfast", "crf": "20"}),
                              ("base_cfr_vp9.webm", "libvpx-vp9", {"crf": "32", "b": "0", "deadline": "realtime", "cpu-used": "8", "row-mt": "1"}),
                              ("base_cfr_av1.webm", "libsvtav1", {"crf": "35", "preset": "10"})):
        try:
            encode_pyav(OUT / name, base, codec, opts=opts)
            steps[name] = {"rc": 0, "how": f"PyAV {codec} {opts}"}
        except Exception as e:  # noqa: BLE001
            steps[name] = {"rc": 1, "error": repr(e)[:300]}
    pts = vfr_pts_ms(n)
    encode_pyav(OUT / "base_vfr_vp9.webm", base, "libvpx-vp9", pts=pts, tb=Fraction(1, 1000),
                opts={"crf": "32", "b": "0", "deadline": "realtime", "cpu-used": "8", "row-mt": "1"})
    encode_pyav(OUT / "base_vfr_h264.mp4", base, "libx264", pts=[p * 90 for p in pts], tb=Fraction(1, 90000),
                opts={"preset": "veryfast", "crf": "20"})
    steps["vfr"] = {"pts_ms_first10": pts[:10], "gap_after_frame": n // 2 - 1}

    # overlay data, sidecars
    frames = M.make_frames(n, W, H, "all")
    hdr = M.header(W, H, FPS, "all")
    jw = M.JsonlWriter(OUT / "overlay.jsonl", hdr)
    vw = M.VttWriter(OUT / "overlay.vtt", hdr)
    aw = M.AssWriter(OUT / "overlay.ass", hdr)
    sw = M.SvgSingleWriter(OUT / "overlay_single.svg", hdr)
    for fd in frames:
        jw.write(fd); vw.write(fd); aw.write(fd); sw.write(fd)
    for x in (jw, vw, aw, sw):
        x.close()
    # VFR vtt: cue times from the container pts read back with ffprobe
    for name in ("base_cfr_h264.mp4", "base_cfr_vp9.webm", "base_cfr_av1.webm", "base_vfr_vp9.webm", "base_vfr_h264.mp4"):
        if (OUT / name).exists():
            p = ffprobe_pts(OUT / name)
            (OUT / f"pts_{name}.json").write_text(json.dumps(p))
            steps[f"probe_{name}"] = {"frames": len(p), "first5": p[:5], "last": p[-1] if p else None,
                                      "bytes": (OUT / name).stat().st_size}
    pv = json.loads((OUT / "pts_base_vfr_vp9.webm.json").read_text())
    vv = M.VttWriter(OUT / "overlay_vfr.vtt", hdr)
    for i, fd in enumerate(frames):
        nxt = pv[i + 1] if i + 1 < len(pv) else pv[i] + 1 / FPS
        vv.write(fd, pts_s=pv[i], dur_s=nxt - pv[i])
    vv.close()
    # half-frame-shifted CFR cues: cue f = [(f-0.5)/fps, (f+0.5)/fps)  (clamped at 0)
    vh = M.VttWriter(OUT / "overlay_half.vtt", hdr)
    for fd in frames:
        st = max(0.0, (fd.f - 0.5) / FPS)
        vh.write(fd, pts_s=st, dur_s=(fd.f + 0.5) / FPS - st)
    vh.close()

    # alpha overlay layers: BGRA rawvideo -> ffmpeg
    raw = bytearray()
    for fd in frames:
        rgba = M.render_rgba(M.primitives(fd, W, H), W, H)
        stamp_overlay_bgra(rgba, fd.f)
        raw += rgba.tobytes()
    raw = bytes(raw)
    src = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    run(src + ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-crf", "32", "-b:v", "0", "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1",
               "-auto-alt-ref", "0", "-g", "30", str(OUT / "overlay_vp9alpha.webm")], steps, "overlay_vp9alpha.webm", raw)
    run(src + ["-c:v", "png", "-pix_fmt", "rgba", str(OUT / "overlay_png.mov")], steps, "overlay_png.mov", raw)
    run(src + ["-c:v", "qtrle", "-pix_fmt", "argb", str(OUT / "overlay_qtrle.mov")], steps, "overlay_qtrle.mov", raw)
    for name in ("overlay_vp9alpha.webm", "overlay_png.mov", "overlay_qtrle.mov"):
        if (OUT / name).exists():
            steps[name]["bytes"] = (OUT / name).stat().st_size
            steps[name]["bytes_per_frame"] = round((OUT / name).stat().st_size / n)
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,pix_fmt:stream_tags=alpha_mode", "-of", "json", str(OUT / name)],
                               capture_output=True, text=True)
            steps[name]["ffprobe"] = json.loads(r.stdout or "{}")
    # alpha round trip: decode the VP9-alpha layer with libvpx-vp9 (needed for alpha) and compare alpha plane
    r = subprocess.run(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i", str(OUT / "overlay_vp9alpha.webm"), "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "bgra", "-"], capture_output=True)
    if r.returncode == 0 and len(r.stdout) == W * H * 4:
        dec = np.frombuffer(r.stdout, np.uint8).reshape(H, W, 4)
        ref = np.frombuffer(raw[: W * H * 4], np.uint8).reshape(H, W, 4)
        steps["vp9alpha_decode_check"] = {"alpha_mean_abs_diff": float(np.abs(dec[..., 3].astype(int) - ref[..., 3]).mean()),
                                          "alpha_zero_fraction_ref": float((ref[..., 3] == 0).mean()),
                                          "alpha_zero_fraction_dec": float((dec[..., 3] < 8).mean())}
    # in-band text tracks
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(OUT / "base_cfr_vp9.webm"), "-i", str(OUT / "overlay.vtt"),
         "-map", "0:v", "-map", "1:s", "-c:v", "copy", "-c:s", "webvtt", str(OUT / "base_vp9_vtt_inband.webm")], steps, "base_vp9_vtt_inband.webm")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(OUT / "base_cfr_vp9.webm"), "-i", str(OUT / "overlay.ass"),
         "-map", "0:v", "-map", "1:s", "-c", "copy", str(OUT / "base_vp9_ass.mkv")], steps, "base_vp9_ass.mkv")
    # ASS round trip through ffmpeg: how many events / what timing precision survive
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "s:0", "-show_entries", "packet=pts_time,duration_time", "-of", "csv=p=0",
                        str(OUT / "base_vp9_ass.mkv")], capture_output=True, text=True)
    pk = [l.split(",") for l in r.stdout.split() if l]
    steps["ass_mkv_packets"] = {"n": len(pk), "first6": pk[:6]}
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "s:0", "-show_entries", "packet=pts_time,duration_time", "-of", "csv=p=0",
                        str(OUT / "base_vp9_vtt_inband.webm")], capture_output=True, text=True)
    pk = [l.split(",") for l in r.stdout.split() if l]
    steps["vtt_webm_packets"] = {"n": len(pk), "first6": pk[:6]}
    # truncated copies
    for name, outn in (("overlay.vtt", "overlay_trunc.vtt"), ("overlay_single.svg", "overlay_trunc.svg")):
        d = (OUT / name).read_bytes()
        (OUT / "truncated" / outn).write_bytes(d[: len(d) // 2])
    # a complete single SVG and a per-frame SVG for the <img> load check
    (OUT / "truncated" / "overlay_full.svg").write_bytes((OUT / "overlay_single.svg").read_bytes())
    (RES / "make_test_media.json").write_text(json.dumps(log, indent=1, default=str))
    print(json.dumps(log, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
