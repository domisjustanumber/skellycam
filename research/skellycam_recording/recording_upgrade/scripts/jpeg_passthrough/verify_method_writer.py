# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""Adversarial method checks for jpeg_passthrough (VERIFY_method step, 2026-11-09). Functional only, no timing.

V1) Container-independent byte check: is every input JPEG present VERBATIM, in order, non-overlapping, in the raw
    container bytes? (The FINDINGS byte-exactness claim was only checked through FFmpeg demuxers.) In memory.
V2) Writes c930e_720p_flash variants with realistic dropped frames (real timestamps kept, so gaps appear):
    gap60  = frames 300..359 removed (one 2 s gap), 831 frames
    drop50 = every 50th frame removed, 873 frames
    into fmp4_1s_tb_us, fmp4_perframe_tb_us, mp4_tb_us, mkv. Files go to DIR (real-camera media folder) for the
    OpenCV 4.12 / FreeMoCap reader script verify_method_reader.py.
V3) Long synthetic fMP4 1/1e6 (54,000 tiny 64x48 JPEGs encoded here, intervals = real c930e intervals looped, plus one
    2 s gap) -> DIR/long_*.mp4, to see whether OpenCV's estimated frame count (fMP4 has no nb_frames) stays exact.

Run (repo root):
  uv run --script .../verify_method_writer.py DIR
Writes results/jpeg_passthrough/verify_method_writer.json
"""
from __future__ import annotations

import io as pyio
import json
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402

FRAG1S = {"movflags": "frag_keyframe+empty_moov+default_base_moof", "min_frag_duration": "1000000"}
FRAGPF = {"movflags": "frag_keyframe+empty_moov+default_base_moof"}
CONTS = {"fmp4_1s_tb_us": ("mp4", ".mp4", FRAG1S, True), "fmp4_perframe_tb_us": ("mp4", ".mp4", FRAGPF, True),
         "mp4_tb_us": ("mp4", ".mp4", {}, True), "mkv": ("matroska", ".mkv", {}, False),
         "mov_tb_us": ("mov", ".mov", {}, True), "nut_tb_us": ("nut", ".nut", {}, True)}


def write(target, cont, frames, w, h, us):
    import av
    fmt, _, opts, tb_us = CONTS[cont]
    c = av.open(target, "w", format=fmt, options=dict(opts))
    st = c.add_mux_stream("mjpeg", rate=30, width=w, height=h)
    if tb_us:
        st.time_base = Fraction(1, 1_000_000)
    for k, fb in enumerate(frames):
        p = av.Packet(fb)
        p.stream = st
        p.time_base = Fraction(1, 1_000_000)
        p.pts = p.dts = us[k]
        p.is_keyframe = True
        c.mux(p)
    c.close()


def verbatim(buf: bytes, frames: list[bytes]) -> dict:
    pos, found = 0, 0
    for fb in frames:
        i = buf.find(fb, pos)
        if i < 0:
            break
        found += 1
        pos = i + len(fb)
    return {"n_in": len(frames), "found_in_order": found, "all": found == len(frames)}


def main() -> None:
    import av
    import numpy as np
    av.logging.set_level(av.logging.ERROR)
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    name = "c930e_720p_flash"
    frames = C.load_set(name)
    ts = C.real_timestamps_ns(name, frames)
    us = [(t - ts[0]) // 1000 for t in ts]
    res = {"meta": {"pyav": av.__version__, "libavformat": ".".join(map(str, av.library_versions["libavformat"])),
                    "note": "functional only; no timing"}, "V1_verbatim": {}, "V2_files": {}, "V3_files": {}}

    # V1
    for cont in CONTS:
        b = pyio.BytesIO()
        write(b, cont, frames, 1280, 720, us)
        res["V1_verbatim"][cont] = verbatim(b.getvalue(), frames)
    print("V1", res["V1_verbatim"], flush=True)

    # V2
    variants = {"gap60": [k for k in range(len(frames)) if not 300 <= k < 360],
                "drop50": [k for k in range(len(frames)) if k % 50 != 49]}
    for vn, keep in variants.items():
        fr = [frames[k] for k in keep]
        u = [us[k] - us[keep[0]] for k in keep]
        for cont in ("fmp4_1s_tb_us", "fmp4_perframe_tb_us", "mp4_tb_us", "mkv"):
            p = out_dir / f"{vn}_{cont}{CONTS[cont][1]}"
            write(str(p), cont, fr, 1280, 720, u)
            res["V2_files"][p.name] = {"variant": vn, "container": cont, "n_frames": len(fr), "keep": keep}
    print("V2 done", flush=True)

    # V3: synthetic tiny JPEGs (index burned in as a binary pattern so frames are distinct)
    n = 54_000
    d = [b - a for a, b in zip(us, us[1:])]
    lu = [0]
    for i in range(1, n):
        step = d[(i - 1) % len(d)]
        if i == n // 2:
            step += 2_000_000  # one 2 s gap (dropped-frame burst)
        lu.append(lu[-1] + step)
    enc = av.CodecContext.create("mjpeg", "w")
    enc.width, enc.height, enc.pix_fmt, enc.time_base = 64, 48, "yuvj422p", Fraction(1, 30)
    tiny = []
    for i in range(n):
        a = np.zeros((48, 64, 3), np.uint8)
        bits = [(i >> j) & 1 for j in range(16)]
        for j, bt in enumerate(bits):
            a[(j // 8) * 24:(j // 8) * 24 + 24, (j % 8) * 8:(j % 8) * 8 + 8] = 255 * bt
        vf = av.VideoFrame.from_ndarray(a, format="rgb24").reformat(format="yuvj422p")
        pk = enc.encode(vf)
        tiny.append(bytes(pk[0]))
    for cont in ("fmp4_1s_tb_us", "fmp4_perframe_tb_us", "mp4_tb_us"):
        p = out_dir / f"long_{cont}.mp4"
        write(str(p), cont, tiny, 64, 48, lu)
        res["V3_files"][p.name] = {"container": cont, "n_frames": n, "duration_s": lu[-1] / 1e6, "gap_at": n // 2}
    print("V3 done", flush=True)
    C.write_json(C.RESULTS / "verify_method_writer.json", res)


if __name__ == "__main__":
    main()
