# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2"]
# ///
import io, sys, json
from fractions import Fraction
from pathlib import Path
sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough")
import jp_common as C
fr = C.load_set("c930e_720p_flash"); ts = C.real_timestamps_ns("c930e_720p_flash", fr); us = [(t-ts[0])//1000 for t in ts]
out = {}
D = C.MEDIA / "verify_size"; D.mkdir(parents=True, exist_ok=True)
import av
for fmt, ext in (("matroska", ".mkv"), ("mp4", ".mp4"), ("nut", ".nut")):
    sizes = {}
    for tgt in ("mem", "file"):
        t = io.BytesIO() if tgt == "mem" else str(D / f"x{ext}")
        c = av.open(t, "w", format=fmt)
        st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
        for k, b in enumerate(fr):
            p = av.Packet(b); p.stream = st; p.time_base = Fraction(1, 1_000_000); p.pts = p.dts = us[k]; c.mux(p)
        c.close()
        sizes[tgt] = t.getbuffer().nbytes if tgt == "mem" else (D / f"x{ext}").stat().st_size
        if tgt == "file":
            raw = (D / f"x{ext}").read_bytes()
            sizes["file_has_filename_or_title"] = (b"x" + ext.encode()) in raw
    out[fmt] = sizes
import shutil; shutil.rmtree(D)
out["meta"] = {"pyav": av.__version__, "set": "c930e_720p_flash VFR 1/1e6 pts", "note": "functional only"}
(C.RESULTS / "verify_method_size_check.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out))
