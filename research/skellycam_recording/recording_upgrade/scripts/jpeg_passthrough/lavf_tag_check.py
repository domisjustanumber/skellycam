# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2"]
# ///
"""PyAV 19.0.2 functional check (no timing): how many 'Lavf<version>' writer tags each muxer writes (3 c930e frames, CFR,
in memory). Used to explain the 0-3 B size difference between PyAV 18 (libavformat 62.12.102) and PyAV 19 (63.1.102) writes.
Run (repo root): uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/lavf_tag_check.py
"""
import io, re, sys, json
from fractions import Fraction
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402
import av
f = C.load_set("c930e_720p_flash", 1)[0]
res = {"meta": {"pyav": av.__version__, "ffmpeg_version_info": av.ffmpeg_version_info, "note": "functional only; no timing"}, "tags": {}}
for fmt in ("matroska", "mp4", "mov", "nut", "avi", "mjpeg"):
    b = io.BytesIO()
    with av.open(b, "w", format=fmt) as c:
        st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
        for k in range(3):
            p = av.Packet(f); p.stream = st; p.time_base = Fraction(1, 30); p.pts = p.dts = k; c.mux(p)
    res["tags"][fmt] = [t.decode() for t in re.findall(rb"Lavf[0-9.]+", b.getvalue())]
print(res)
C.write_json(C.RESULTS / "pyav19_lavf_tag.json", res)
