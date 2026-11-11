# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""PyAV 19.0.2: FFmpeg log lines and return path when an empty av.Packet() is muxed into Matroska
after each MJPEG frame (what happens inside the muxer). Functional only."""
import json, shutil, sys
from fractions import Fraction
import av, av.logging
sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/write_throughput")
import wt_common as W
MEDIA = W.MEDIA / "av19_checks_emptypkt_log"; MEDIA.mkdir(parents=True, exist_ok=True)
src = W.load_mjpeg_set("c930e_720p_flash", 3); US = Fraction(1, 1_000_000)
av.logging.set_level(av.logging.DEBUG)
res = dict(env=W.env_versions(), steps=[])
with av.logging.Capture(local=False) as logs:
    c = av.open(str(MEDIA / "x.mkv"), "w", format="matroska", options={"flush_packets": "1"})
    st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
    for i in range(3):
        n0 = len(logs)
        pk = av.Packet(src[i]); pk.stream = st; pk.time_base = US; pk.pts = pk.dts = int(i * 1e6 / 30); pk.is_keyframe = True
        c.mux(pk)
        ep = av.Packet(); ep.stream = st
        info = dict(frame=i, empty_pkt_pts=ep.pts, empty_pkt_dts=ep.dts, empty_pkt_size=ep.size)
        try:
            c.mux_one(ep); info["mux_one_empty"] = "no exception"
        except Exception as e:  # noqa: BLE001
            info["mux_one_empty"] = f"{type(e).__name__}: {e}"
        info["log_lines"] = [f"{lvl} {name}: {msg.strip()}" for lvl, name, msg in list(logs)[n0:]
                             if name and ("matroska" in name or "mux" in name.lower() or "avformat" in name.lower() or "mkv" in name.lower())][:12]
        res["steps"].append(info)
    c.close()
av.logging.set_level(None)
(W.RESULTS / "functional" / "mkv_emptypkt_log_av19.0.2.json").write_text(json.dumps(res, indent=1, default=str))
shutil.rmtree(MEDIA, ignore_errors=True)
print(json.dumps(res["steps"], indent=1))
