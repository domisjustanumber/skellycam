# /// script
# requires-python = ">=3.10"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""Functional re-check of the chromium_sync_scrub recorder-index premise with PyAV 19.0.2 (no timing).

For each container/codec variant used by gen_clips.py (which ran on PyAV 18.0.0), encode a short synthetic
clip with explicit per-frame pts (real VFR capture times incl. the 0.011 ms pair at frames 81/82), then demux and
check: requested pts == demuxed pts, decode order == pts order, packet.pos points at the packet bytes directly
(no fallback search), and the burned 16-bit index decodes back on every frame.
Usage: uv run --script pyav19_recorder_index_check.py <flash_jsonl> <media_dir> <out_json>
"""
import json
import sys
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

BITS, CELLS = 16, 32
W, H, N = 640, 360, 96


def burn(k):
    img = np.full((H, W, 3), 96, np.uint8)
    img[H // 2:, :, 1] = (k * 7) % 256  # some changing content
    cw = W // CELLS
    for b in range(BITS):
        bit = (k >> (BITS - 1 - b)) & 1
        for j, v in enumerate((bit, 1 - bit)):
            x0 = (2 * b + j) * cw
            img[0:cw, x0:x0 + cw] = 255 if v else 0
    return img


def read(img):
    cw = W // CELLS
    g = img[cw // 2, :, :].mean(axis=1)
    v = 0
    for b in range(BITS):
        a, c = g[(2 * b) * cw + cw // 2], g[(2 * b + 1) * cw + cw // 2]
        if abs(a - c) <= 64:
            return None
        v = (v << 1) | (1 if a > c else 0)
    return v


VARIANTS = {
    "av1_gop.mp4": ("libsvtav1", "mp4", {"preset": "10", "crf": "35", "g": "30"}, {"movflags": "+faststart"}),
    "av1_gop_frag.mp4": ("libsvtav1", "mp4", {"preset": "10", "crf": "35", "g": "30"},
                         {"movflags": "frag_keyframe+empty_moov+default_base_moof"}),
    "av1_intra.mp4": ("libsvtav1", "mp4", {"preset": "10", "crf": "35", "g": "1"}, {"movflags": "+faststart"}),
    "av1_gop.webm": ("libsvtav1", "webm", {"preset": "10", "crf": "35", "g": "30"}, {}),
    "vp9_gop.webm": ("libvpx-vp9", "webm", {"deadline": "realtime", "cpu-used": "8", "crf": "33", "b": "0", "g": "30",
                                            "row-mt": "1", "lag-in-frames": "0", "auto-alt-ref": "0"}, {}),
    "h264_gop.mp4": ("libx264", "mp4", {"preset": "veryfast", "crf": "23", "bf": "0", "g": "30", "keyint_min": "30",
                                        "sc_threshold": "0"}, {"movflags": "+faststart"}),
}


def main():
    jsonl, media, out_json = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    media.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in jsonl.open()][:N]
    t = [r["mf_sample_time_100ns"] for r in rows]
    times = [(x - t[0]) / 1e7 for x in t]
    res = {"pyav": av.__version__, "library_versions": {k: ".".join(map(str, v)) for k, v in av.library_versions.items()},
           "frames": N, "size": f"{W}x{H}", "vfr_source": str(jsonl).replace("\\", "/"),
           "gap_81_82_ms": round((times[82] - times[81]) * 1000, 4), "variants": {}}
    for name, (codec, fmt, eopts, mopts) in VARIANTS.items():
        path = media / f"pyav19_{name}"
        tb = Fraction(1, 90000) if fmt == "mp4" else Fraction(1, 1000)
        r = {"codec": codec, "format": fmt, "time_base": str(tb), "mux_options": mopts}
        try:
            req, prev, adjusted = [], -1, 0
            with av.open(str(path), "w", format=fmt, options=mopts) as out:
                st = out.add_stream(codec, rate=30, options=eopts)
                st.width, st.height, st.pix_fmt = W, H, "yuv420p"
                st.time_base = tb
                st.codec_context.time_base = tb
                for k in range(N):
                    pts = int(round(times[k] / tb))
                    if pts <= prev:
                        pts, adjusted = prev + 1, adjusted + 1
                    prev = pts
                    req.append(pts)
                    vf = av.VideoFrame.from_ndarray(burn(k), format="rgb24").reformat(format="yuv420p")
                    vf.pts, vf.time_base = pts, tb
                    for p in st.encode(vf):
                        out.mux(p)
                for p in st.encode(None):
                    out.mux(p)
            data = path.read_bytes()
            pk = []
            with av.open(str(path)) as c:
                s = c.streams.video[0]
                r["demux_time_base"] = str(s.time_base)
                for p in c.demux(s):
                    if p.size == 0:
                        continue
                    b = bytes(p)
                    direct = p.pos is not None and p.pos >= 0 and data[p.pos:p.pos + p.size] == b
                    pk.append({"pts": p.pts, "dts": p.dts, "key": bool(p.is_keyframe), "pos_direct_exact": direct})
            dec = []
            with av.open(str(path)) as c:
                for f in c.decode(video=0):
                    dec.append((f.pts, read(f.to_ndarray(format="rgb24"))))
            dpts = sorted(x["pts"] for x in pk)
            r.update({
                "bytes": len(data),
                "packets": len(pk),
                "keyframes": sum(x["key"] for x in pk),
                "pts_adjusted_for_monotonic": adjusted,
                "demuxed_pts_equal_requested": dpts == req,
                "decode_order_equals_pts_order": all(a["dts"] <= b["dts"] for a, b in zip(pk, pk[1:]))
                and [x["pts"] for x in pk] == dpts,
                "packet_pos_direct_exact": sum(x["pos_direct_exact"] for x in pk),
                "decoded_frames": len(dec),
                "pattern_equals_frame_index": sum(1 for i, (_, v) in enumerate(sorted(dec)) if v == i),
                "pts_81_82_83": req[81:84],
            })
        except Exception as e:  # report, keep going
            r["error"] = f"{type(e).__name__}: {e}"
        res["variants"][name] = r
    out_json.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
