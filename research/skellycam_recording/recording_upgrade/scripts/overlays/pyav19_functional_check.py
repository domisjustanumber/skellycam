# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy", "opencv-python==4.12.0.88"]
# ///
"""PyAV 19.0.2 functional re-check of the overlay results that were made with PyAV 18 or the ffmpeg CLI (G3).
Functional only: no timing is measured or recorded.

Checks
  caps   codecs / filters / muxers present in PyAV 19.0.2's bundled FFmpeg that the overlay paths need
  p1     sidecar (.skov) -> cv2 burn-in -> PyAV 19 libvpx-vp9 WebM and libx264 MP4 -> decode -> barcode alignment
  alpha  VP9-alpha layer encoded by PyAV 19 (libvpx-vp9, yuva420p) -> decode with the default decoder and with
         libvpx-vp9 -> is alpha kept, does it match the matte; then a 50 % truncation decoded with libvpx-vp9
  p2     PyAV 19 filter graph 'overlay' (base VP9 + alpha layer) -> base barcode and overlay barcode in each output frame,
         with the layer decoded by libvpx-vp9 and (negative control) by the default decoder

Run from repo root (Git Bash):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/overlays/pyav19_functional_check.py --frames 60
Media -> <raw>/overlays/pyav19_check/ ; results -> results/overlays/pyav19_functional_check.json
"""
from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import overlay_model as M  # noqa: E402

RAW = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109")
CORPUS = RAW / "corpus" / "c930e_720p_flash"
OUT = RAW / "overlays" / "pyav19_check"
RES = HERE.parents[1] / "results" / "overlays"
W, H, FPS = 1280, 720, 30
VP9_OPTS = {"crf": "32", "b": "0", "deadline": "realtime", "cpu-used": "8", "row-mt": "1"}


# same barcode helpers as make_test_media.py / export_burnin.py (copied so this file does not import PyAV-18-era modules)
def code_bits(i: int) -> list[int]:
    return [(i >> k) & 1 for k in range(12)] + [((bin(i).count("1") & 15) >> k) & 1 for k in range(4)]


def stamp_base(img, i):
    for k, b in enumerate(code_bits(i)):
        img[680:720, k * 80:(k + 1) * 80] = 255 if b else 0


def stamp_overlay(img, i, bgra=False):
    for k, b in enumerate(code_bits(i)):
        img[60:100, k * 40:(k + 1) * 40, :3] = 255 if b else 0
        if bgra:
            img[60:100, k * 40:(k + 1) * 40, 3] = 255


def read_code(gray, centres) -> int:
    bits = [1 if gray[y, x] > 128 else 0 for x, y in centres]
    idx = sum(b << k for k, b in enumerate(bits[:12]))
    chk = sum(b << k for k, b in enumerate(bits[12:]))
    return idx if (bin(idx).count("1") & 15) == chk else -1


VC = [(k * 80 + 40, 700) for k in range(16)]
OC = [(k * 40 + 20, 80) for k in range(16)]


def tally(grays) -> dict:
    n = match = fail = 0
    mism = []
    for g in grays:
        a, b = read_code(g, VC), read_code(g, OC)
        n += 1
        if a < 0 or b < 0:
            fail += 1
            if len(mism) < 5:
                mism.append([a, b])
        elif a == b:
            match += 1
        elif len(mism) < 5:
            mism.append([a, b])
    return {"frames": n, "base==overlay": match, "decode_fail": fail, "mismatch_examples": mism}


def caps() -> dict:
    want_codecs = ["libvpx-vp9", "vp9", "libx264", "libsvtav1", "libdav1d", "png", "qtrle", "webvtt", "ass", "mjpeg"]
    want_filters = ["overlay", "alphamerge", "alphaextract", "ass", "subtitles", "drawtext", "drawbox"]
    want_formats = ["webm", "matroska", "mp4", "mov", "webvtt", "ass"]
    out = {"codecs": {}, "filters": {}, "formats": {}}
    for c in want_codecs:
        e = d = False
        try:
            av.Codec(c, "w"); e = True
        except Exception:
            pass
        try:
            av.Codec(c, "r"); d = True
        except Exception:
            pass
        out["codecs"][c] = {"encode": e, "decode": d}
    fa = av.filter.filters_available
    for f in want_filters:
        out["filters"][f] = f in fa
    fm = av.formats_available
    for f in want_formats:
        out["formats"][f] = f in fm
    return out


def p1(n: int) -> dict:
    hdr = M.header(W, H, FPS, "all")
    sc = OUT / "overlay.skov"
    wr = M.BinWriter(sc, hdr)
    for fd in M.make_frames(n, W, H, "all"):
        wr.write(fd)
    wr.close()
    _, frames, bad = M.read_bin(sc.read_bytes())
    by_f = {fd.f: fd for fd in frames}
    res = {"sidecar_frames_read": len(frames), "sidecar_bad": bad}
    for name, codec, opts in (("p1_burnin_vp9.webm", "libvpx-vp9", VP9_OPTS),
                              ("p1_burnin_h264.mp4", "libx264", {"preset": "veryfast", "crf": "20"})):
        path = OUT / name
        with av.open(str(path), "w") as c:
            s = c.add_stream(codec, rate=FPS, options=opts)
            s.width, s.height, s.pix_fmt = W, H, "yuv420p"
            for i in range(n):
                img = cv2.imdecode(np.fromfile(CORPUS / f"frame_{i:06d}.jpg", np.uint8), cv2.IMREAD_COLOR)
                stamp_base(img, i)
                fd = by_f[i]
                M.burn_in(img, M.primitives(fd, W, H))
                stamp_overlay(img, fd.f)
                for p in s.encode(av.VideoFrame.from_ndarray(img, format="bgr24")):
                    c.mux(p)
            for p in s.encode():
                c.mux(p)
        with av.open(str(path)) as c:
            r = tally(fr.to_ndarray(format="gray") for fr in c.decode(video=0))
        r["bytes"] = path.stat().st_size
        res[name] = r
    return res


def make_layer(n: int):
    """Overlay-only BGRA frames (difference matte, as make_test_media.py) with the overlay barcode opaque."""
    mattes, frames = [], []
    for fd in M.make_frames(n, W, H, "all"):
        rgba = M.render_rgba(M.primitives(fd, W, H), W, H)
        stamp_overlay(rgba, fd.f, bgra=True)
        frames.append(rgba)
        mattes.append(rgba[..., 3].copy())
    return frames, mattes


def decode_libvpx(path: Path, max_frames: int | None = None):
    """Decode a WebM video stream with the libvpx-vp9 decoder through PyAV (keeps alpha if the decoder does)."""
    out = []
    ctx = av.CodecContext.create("libvpx-vp9", "r")
    with av.open(str(path)) as c:
        st = c.streams.video[0]
        try:
            for pkt in c.demux(st):
                if pkt.size == 0:
                    continue
                for f in ctx.decode(pkt):
                    out.append(f)
            for f in ctx.decode(None):
                out.append(f)
        except av.error.FFmpegError as e:  # truncated file
            out.append(("error", f"{type(e).__name__}: {e}"))
    frames = [f for f in out if not isinstance(f, tuple)]
    errs = [f[1] for f in out if isinstance(f, tuple)]
    return frames, errs


def alpha(n: int, frames, mattes) -> dict:
    path = OUT / "overlay_vp9alpha_pyav19.webm"
    with av.open(str(path), "w") as c:
        s = c.add_stream("libvpx-vp9", rate=FPS, options={**VP9_OPTS, "auto-alt-ref": "0", "g": "30"})
        s.width, s.height, s.pix_fmt = W, H, "yuva420p"
        for i, img in enumerate(frames):
            vf = av.VideoFrame.from_ndarray(img, format="bgra").reformat(format="yuva420p")
            vf.pts = i
            for p in s.encode(vf):
                c.mux(p)
        for p in s.encode():
            c.mux(p)
    res = {"file": path.name, "bytes": path.stat().st_size, "bytes_per_frame": round(path.stat().st_size / n),
           "encoder_pix_fmt": "yuva420p"}
    with av.open(str(path)) as c:
        st = c.streams.video[0]
        res["stream_meta"] = {"codec": st.codec_context.name, "pix_fmt_reported": st.codec_context.pix_fmt,
                              "metadata": dict(st.metadata)}
        dflt = list(c.decode(video=0))
    res["default_decoder"] = {"decoder": "vp9 (FFmpeg native, PyAV default)", "frames": len(dflt),
                              "frame_format": dflt[0].format.name if dflt else None}
    lv, errs = decode_libvpx(path)
    diffs, zero_frac_dec = [], []
    for f, m in zip(lv, mattes):
        a = f.to_ndarray(format="bgra")[..., 3] if f.format.name.startswith("yuva") else None
        if a is not None:
            diffs.append(float(np.abs(a.astype(np.int16) - m.astype(np.int16)).mean()))
            zero_frac_dec.append(float((a == 0).mean()))
    res["libvpx_decoder"] = {"frames": len(lv), "frame_format": lv[0].format.name if lv else None, "errors": errs,
                             "frames_with_alpha_plane": len(diffs),
                             "alpha_mean_abs_diff_vs_matte_max": round(max(diffs), 4) if diffs else None,
                             "alpha_zero_fraction_frame0_ref": round(float((mattes[0] == 0).mean()), 4),
                             "alpha_zero_fraction_frame0_dec": round(zero_frac_dec[0], 4) if zero_frac_dec else None,
                             "overlay_barcode_matches": sum(read_code(f.to_ndarray(format="gray"), OC) == i for i, f in enumerate(lv))}
    # 50 % truncation, decoded through PyAV 19 with libvpx-vp9
    d = path.read_bytes()
    t = OUT / "trunc50_overlay_vp9alpha_pyav19.webm"
    t.write_bytes(d[: len(d) // 2])
    tf, terrs = decode_libvpx(t)
    transp = sum(int((f.to_ndarray(format="bgra")[..., 3] < 8).mean() > 0.5) for f in tf if f.format.name.startswith("yuva"))
    res["trunc50"] = {"bytes_cut": len(d) // 2, "frames_decoded": len(tf), "frames_with_transparency": transp, "errors": terrs[:3]}
    return res, lv, dflt


def p2(n: int, layer_lv, layer_dflt) -> dict:
    """overlay filter through PyAV 19's filter graph: base_cfr_vp9.webm (made in the PyAV 18 era, decoded here by PyAV 19)
    composited with the PyAV-19-encoded alpha layer."""
    base_path = RAW / "overlays" / "media" / "base_cfr_vp9.webm"
    with av.open(str(base_path)) as c:
        base = []
        for f in c.decode(video=0):
            base.append(f)
            if len(base) >= n:
                break
    res = {"base_file": base_path.name}
    tb = Fraction(1, FPS)
    for tag, layer in (("layer_libvpx_decoder", layer_lv), ("layer_default_decoder", layer_dflt)):
        g = av.filter.Graph()
        b0 = g.add_buffer(width=W, height=H, format=base[0].format.name, time_base=tb)
        b1 = g.add_buffer(width=W, height=H, format=layer[0].format.name, time_base=tb)
        ov = g.add("overlay", "x=0:y=0:eof_action=pass:format=yuv420")
        sink = g.add("buffersink")
        b0.link_to(ov, 0, 0)
        b1.link_to(ov, 0, 1)
        ov.link_to(sink)
        g.configure()
        grays = []
        for i in range(min(len(base), len(layer))):
            fb = base[i].reformat(format=base[0].format.name)
            fl = layer[i].reformat(format=layer[0].format.name)
            fb.pts = fl.pts = i
            fb.time_base = fl.time_base = tb
            b0.push(fb)
            b1.push(fl)
            while True:
                try:
                    o = sink.pull()
                except (av.error.BlockingIOError, av.error.EOFError):
                    break
                grays.append(o.to_ndarray(format="gray"))
        r = tally(grays)
        r["layer_frame_format"] = layer[0].format.name
        res[tag] = r
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=60)
    n = ap.parse_args().frames
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"pyav": av.__version__, "library_versions": {k: ".".join(map(str, v)) for k, v in av.library_versions.items()},
           "opencv": cv2.__version__, "numpy": np.__version__, "frames": n, "timing": "none recorded (functional only)"}
    res["caps"] = caps()
    res["p1"] = p1(n)
    frames, mattes = make_layer(n)
    res["alpha"], lv, dflt = alpha(n, frames, mattes)
    res["p2"] = p2(n, lv, dflt)
    (RES / "pyav19_functional_check.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
