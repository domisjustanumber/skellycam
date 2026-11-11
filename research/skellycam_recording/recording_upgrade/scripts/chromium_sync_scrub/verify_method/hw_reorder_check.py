# /// script
# requires-python = ">=3.10"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""Functional check (no timing): do PyAV 19.0.2 hardware encoders with DEFAULT options reorder frames
(decode order != pts order)? The chromium_sync_scrub WebCodecs path decodes index[key..k] and waits for
frame k, and its clips were all software encodes with no reordering visible at the container level."""
import json, sys, av, numpy as np
from fractions import Fraction
out_dir, out_json = sys.argv[1], sys.argv[2]
res = {"pyav": av.__version__, "ffmpeg": av.library_versions.get("libavcodec"), "codecs": {}}
N = 60
for name in ["h264_nvenc", "hevc_nvenc", "av1_nvenc", "h264_qsv", "hevc_qsv", "av1_qsv", "libx264", "libsvtav1"]:
    r = {}
    path = f"{out_dir}/reorder_{name}.mp4"
    try:
        oc = av.open(path, "w", format="mp4")
        st = oc.add_stream(name, rate=30)
        st.width, st.height = 640, 368
        st.pix_fmt = "yuv420p" if not name.endswith("qsv") else "nv12"
        st.time_base = Fraction(1, 90000)
        st.codec_context.gop_size = 30
        for i in range(N):
            a = np.zeros((368, 640, 3), np.uint8); a[:, :, 0] = (i * 4) % 256; a[i % 368, :, 1] = 255
            f = av.VideoFrame.from_ndarray(a, format="rgb24").reformat(format=st.pix_fmt)
            f.pts = i * 3000; f.time_base = Fraction(1, 90000)
            for p in st.encode(f): oc.mux(p)
        for p in st.encode(None): oc.mux(p)
        oc.close()
        ic = av.open(path); vs = ic.streams.video[0]
        pts = [p.pts for p in ic.demux(vs) if p.pts is not None]
        ic.close()
        r["packets"] = len(pts)
        r["decode_order_equals_pts_order"] = pts == sorted(pts)
        r["first_12_pts_in_decode_order_div3000"] = [p // 3000 for p in pts[:12]]
    except Exception as e:
        r["error"] = f"{type(e).__name__}: {e}"[:300]
    res["codecs"][name] = r
json.dump(res, open(out_json, "w"), indent=1)
print(json.dumps(res, indent=1))
