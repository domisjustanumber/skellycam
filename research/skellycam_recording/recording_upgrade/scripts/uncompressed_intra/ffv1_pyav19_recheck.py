# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""PyAV 19.0.2 re-check of three verifier claims that were made with the ffmpeg CLI (functional only, no timing).

1. FFV1 coder on >8-bit gray16le (v3) and native bayer_rggb16le (v4): does coder=rice get forced to range?
2. Share of 12-bit FFV1 bytes caused by the seeded noise bits (noise=True vs noise=False), 1 frame.
3. FFV1 v3 s24 rice g1 KB/frame for both real YUY2 cameras (c930e, c922), 8 frames each.
Every encode is decoded back and compared bit-exact with what was fed.

Run from repo root:
  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/ffv1_pyav19_recheck.py
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import av
import av.logging
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uintra_frames as uf  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra" / "ffv1_recheck_pyav19.0.2.json"


def encode(planes_list, pix_fmt, w, h, opts, enc_pix_fmt=None):
    """Encode frames to in-memory MKV; return (packet_bytes_mean, exact, log, decoded_pix_fmt)."""
    enc_pix_fmt = enc_pix_fmt or pix_fmt
    buf = io.BytesIO()
    sizes = []
    with av.logging.Capture() as cap:
        with av.open(buf, "w", format="matroska") as c:
            st = c.add_stream("ffv1", rate=30, options=opts)
            st.width, st.height, st.pix_fmt = w, h, enc_pix_fmt
            st.codec_context.gop_size = 1
            st.codec_context.thread_count = 1
            for i, pl in enumerate(planes_list):
                fr = uf.make_frame(pl, pix_fmt, w, h)
                fr.pts = i
                for p in st.encode(fr):
                    sizes.append(p.size); c.mux(p)
            for p in st.encode(None):
                sizes.append(p.size); c.mux(p)
    log = sorted({m.strip() for (_l, _n, m) in cap if "coder" in m or "experimental" in m})
    buf.seek(0)
    with av.open(buf) as c:
        dec = list(c.decode(video=0))
    exact = len(dec) == len(planes_list) and all(
        all(np.array_equal(a, b) for a, b in zip(uf.read_planes(d, enc_pix_fmt), pl))
        for d, pl in zip(dec, planes_list))
    return {"bytes_per_frame": float(np.mean(sizes)), "frames": len(dec), "exact": exact,
            "decoded_pix_fmt": dec[0].format.name if dec else None, "log": log}


def main() -> int:
    out = {"av_version": av.__version__, "libavcodec": av.library_versions.get("libavcodec"),
           "note": "functional only, no timing; thread_count=1", "coder_and_noise": [], "camera_size": []}
    yuyv, w, h = uf.load_yuy2("c930e_1080p_yuy2", 1)
    base = {"slices": "24", "slicecrc": "1"}
    for noise in (True, False):
        for src in ("bayer16_quad", "bayer_rggb16le"):
            pl, fmt, ww, hh = uf.derive(src, yuyv[0], w, h, 0, noise)
            for level, coder in (("3", "rice"), ("3", "range_tab")):
                # v3 cannot take bayer_rggb16le: store the mosaic as gray16le (exact re-tag, same bytes)
                r = encode([pl], "gray16le", ww, hh, {**base, "level": level, "coder": coder})
                r.update(source=src, stored_as="gray16le", level=level, coder=coder, noise=noise)
                out["coder_and_noise"].append(r); print(json.dumps(r))
            if src == "bayer_rggb16le" and noise:
                for coder in ("rice", "range_tab"):
                    r = encode([pl], "bayer_rggb16le", ww, hh,
                               {**base, "level": "4", "coder": coder, "strict": "experimental"})
                    r.update(source=src, stored_as="bayer_rggb16le", level="4", coder=coder, noise=noise)
                    out["coder_and_noise"].append(r); print(json.dumps(r))
    for cam in ("c930e_1080p_yuy2", "c922_1080p_yuy2"):
        frames, w, h = uf.load_yuy2(cam, 8)
        pls = [list(uf.yuyv_split(f)) for f in frames]
        r = encode(pls, "yuv422p", w, h, {**base, "level": "3", "coder": "rice"})
        r.update(camera=cam, config="ffv1 v3 s24 crc rice g1, yuv422p (exact de-interleave)",
                 kb_per_frame=round(r["bytes_per_frame"] / 1000, 1))
        out["camera_size"].append(r); print(json.dumps(r))
    OUT.write_text(json.dumps(out, indent=1))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
