"""'Export with overlays burned in' paths (G3, for sharing). Functional only: does it run, is every exported frame
paired with the right overlay frame. No timing here (see bench_overlay_cost.py).

Paths:
  P1 PyAV + cv2: real camera JPEGs (corpus c930e_720p_flash) + the binary sidecar (.skov) -> cv2 burn-in -> libvpx-vp9 WebM
                 (royalty-free) and libx264 MP4. The overlay carries a barcode of the SIDECAR frame number (y 60..99);
                 the base carries the source frame number (y 680..719). Exported frames are decoded back and both read.
  P2 ffmpeg overlay filter: base_cfr_vp9.webm + overlay_vp9alpha.webm (from make_test_media.py) -> libvpx-vp9.
  P3 ffmpeg + libass: base_cfr_vp9.webm + an ASS file whose only content is the overlay barcode drawn with \\p1
                 rectangles, one event per frame at centisecond times -> tests whether centisecond ASS timing hits
                 every 30 fps frame exactly once.
Media -> <raw>/overlays/export/ ; results -> results/overlays/export_burnin.json

Run from repo root (needs make_test_media.py output first):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/export_burnin.py [--frames 300]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import av
import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import overlay_model as M  # noqa: E402
from make_test_media import code_bits, stamp_base  # noqa: E402

RAW = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109")
CORPUS = RAW / "corpus" / "c930e_720p_flash"
MEDIA = RAW / "overlays" / "media"
OUT = RAW / "overlays" / "export"
RES = HERE.parents[1] / "results" / "overlays"
W, H, FPS = 1280, 720, 30


def read_code(gray: np.ndarray, centres) -> int:
    bits = [1 if gray[y, x] > 128 else 0 for x, y in centres]
    idx = sum(b << k for k, b in enumerate(bits[:12]))
    chk = sum(b << k for k, b in enumerate(bits[12:]))
    return idx if (bin(idx).count("1") & 15) == chk else -1


VC = [(k * 80 + 40, 700) for k in range(16)]
OC = [(k * 40 + 20, 80) for k in range(16)]


def verify(path: Path) -> dict:
    n = match = fail = 0
    mism = []
    with av.open(str(path)) as c:
        for fr in c.decode(video=0):
            g = fr.to_ndarray(format="gray")
            a, b = read_code(g, VC), read_code(g, OC)
            n += 1
            if a < 0 or b < 0:
                fail += 1
            elif a == b:
                match += 1
            elif len(mism) < 10:
                mism.append([a, b])
    return {"frames": n, "base==overlay": match, "decode_fail": fail, "mismatch_examples": mism, "bytes": path.stat().st_size}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=300)
    a = ap.parse_args()
    n = a.frames
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"pyav": av.__version__, "opencv": cv2.__version__, "frames": n}
    # sidecar written as during recording, then read back (as an exporter would)
    hdr = M.header(W, H, FPS, "all")
    sc = OUT / "overlay.skov"
    wr = M.BinWriter(sc, hdr)
    for fd in M.make_frames(n, W, H, "all"):
        wr.write(fd)
    wr.close()
    _, frames, bad = M.read_bin(sc.read_bytes())
    res["sidecar_frames_read"] = len(frames)
    res["sidecar_bad"] = bad
    by_f = {fd.f: fd for fd in frames}

    # P1
    for name, codec, opts in (("p1_burnin_vp9.webm", "libvpx-vp9", {"crf": "32", "b": "0", "deadline": "realtime", "cpu-used": "8", "row-mt": "1"}),
                              ("p1_burnin_h264.mp4", "libx264", {"preset": "veryfast", "crf": "20"})):
        with av.open(str(OUT / name), "w") as c:
            s = c.add_stream(codec, rate=FPS, options=opts)
            s.width, s.height, s.pix_fmt = W, H, "yuv420p"
            for i in range(n):
                img = cv2.imdecode(np.fromfile(CORPUS / f"frame_{i:06d}.jpg", np.uint8), cv2.IMREAD_COLOR)
                stamp_base(img, i)
                fd = by_f[i]
                M.burn_in(img, M.primitives(fd, W, H))
                for k, bit in enumerate(code_bits(fd.f)):
                    img[60:100, k * 40:(k + 1) * 40] = 255 if bit else 0
                for p in s.encode(av.VideoFrame.from_ndarray(img, format="bgr24")):
                    c.mux(p)
            for p in s.encode():
                c.mux(p)
        res[name] = verify(OUT / name)

    # P2 ffmpeg overlay filter (VP9 alpha needs the libvpx decoder to keep alpha)
    out2 = OUT / "p2_overlay_filter_vp9.webm"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(MEDIA / "base_cfr_vp9.webm"), "-c:v", "libvpx-vp9",
           "-i", str(MEDIA / "overlay_vp9alpha.webm"), "-filter_complex", "[0:v][1:v]overlay=0:0:eof_action=pass[v]", "-map", "[v]",
           "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1", str(out2)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    res["p2_overlay_filter"] = {"cmd": " ".join(cmd), "rc": r.returncode, "stderr": r.stderr[-400:]}
    if r.returncode == 0:
        res["p2_overlay_filter"].update(verify(out2))
    # same without forcing the libvpx decoder (native vp9 decoder drops alpha?)
    out2b = OUT / "p2b_overlay_filter_native_dec.webm"
    cmd_b = [c for c in cmd if c not in ()]
    i = cmd_b.index("-c:v")
    del cmd_b[i:i + 2]  # remove decoder selection for input 1
    cmd_b[-1] = str(out2b)
    r = subprocess.run(cmd_b, capture_output=True, text=True)
    res["p2b_overlay_filter_native_vp9_decoder"] = {"cmd": " ".join(cmd_b), "rc": r.returncode, "stderr": r.stderr[-400:]}
    if r.returncode == 0:
        res["p2b_overlay_filter_native_vp9_decoder"].update(verify(out2b))

    # P3 libass with a barcode drawn as ASS vector drawing.
    #   p3:  event f = [f/fps, (f+1)/fps) rounded to centiseconds (the naive mapping)
    #   p3b: event f = [(f-0.5)/fps, (f+0.5)/fps) rounded to centiseconds (half-frame shifted, so rounding cannot cross a frame time)
    for tag, shift in (("p3_libass", 0.0), ("p3b_libass_halfframe", 0.5)):
        ass = OUT / f"barcode_{tag}.ass"
        lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "", "[V4+ Styles]",
                 "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                 "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1", "", "[Events]",
                 "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
        for f in range(n):
            st, en = M._ass_ts(max(0.0, (f - shift) / FPS)), M._ass_ts((f + 1 - shift) / FPS)
            lines.append(f"Dialogue: 0,{st},{en},Default,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&H000000&}}m 0 60 l 640 60 640 100 0 100{{\\p0}}")
            rects = " ".join(f"m {k * 40} 60 l {k * 40 + 40} 60 {k * 40 + 40} 100 {k * 40} 100" for k, b in enumerate(code_bits(f)) if b)
            if rects:
                lines.append(f"Dialogue: 1,{st},{en},Default,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&HFFFFFF&}}{rects}{{\\p0}}")
        ass.write_text("\n".join(lines) + "\n")
        out3 = OUT / f"{tag}_vp9.webm"
        # run from OUT so the filter argument needs no Windows drive-letter escaping
        cmd3 = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(MEDIA / "base_cfr_vp9.webm"), "-vf", f"ass={ass.name}",
                "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1", str(out3)]
        r = subprocess.run(cmd3, capture_output=True, text=True, cwd=str(OUT))
        res[tag] = {"cmd": " ".join(cmd3), "rc": r.returncode, "stderr": r.stderr[-400:]}
        if r.returncode == 0:
            res[tag].update(verify(out3))
    (RES / "export_burnin.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
