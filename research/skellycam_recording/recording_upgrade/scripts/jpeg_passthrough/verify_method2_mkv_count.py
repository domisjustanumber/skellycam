# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "opencv-python==4.12.0.88", "numpy"]
# ///
"""Functional only (no timing): OpenCV 4.12 CAP_FFMPEG frame count of MKV written by PyAV 19.0.2 with real VFR
timestamps (floored to us), for c930e_720p_flash and c922_720p_flash. Media written under the study media dir, deleted."""
import json, sys
from fractions import Fraction
from pathlib import Path
sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough")
import jp_common as C
import av, cv2
out = {"pyav": av.__version__, "opencv": cv2.__version__, "rows": {}}
d = C.MEDIA / "verify_method_20261110"
d.mkdir(parents=True, exist_ok=True)
for name in ("c930e_720p_flash", "c922_720p_flash"):
    fr = C.load_set(name)
    ts = C.real_timestamps_ns(name, fr)
    us = [(t - ts[0]) // 1000 for t in ts]
    ms = [u // 1000 for u in us]
    for cont, fmt in (("mkv", "matroska"), ("fmp4_1s_tb_us", "mp4")):
        p = d / f"{name}_{cont}.{'mkv' if cont=='mkv' else 'mp4'}"
        opts = {} if cont == "mkv" else {"movflags": "frag_keyframe+empty_moov+default_base_moof", "min_frag_duration": "1000000"}
        c = av.open(str(p), "w", format=fmt, options=opts)
        st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
        if cont != "mkv":
            st.time_base = Fraction(1, 1_000_000)
        for b, u in zip(fr, us):
            pk = av.Packet(b); pk.stream = st; pk.time_base = Fraction(1, 1_000_000); pk.pts = pk.dts = u; c.mux(pk)
        c.close()
        cap = cv2.VideoCapture(str(p), cv2.CAP_FFMPEG)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps = cap.get(cv2.CAP_PROP_FPS); cap.release()
        out["rows"][f"{name}|{cont}"] = {"frames": len(fr), "cv2_count": n, "cv2_fps": fps,
                                          "same_ms_pairs": sum(1 for a, b in zip(ms, ms[1:]) if a == b) if cont == "mkv" else None}
        p.unlink()
d.rmdir()
print(json.dumps(out, indent=1))
