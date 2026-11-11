# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""PyAV 19.0.2: empty packet WITH an explicit timestamp (frame pts + 1 us, time base 1/1000000) after each MJPEG
frame into Matroska (flush_packets=1). Records exceptions, FFmpeg warnings/errors, on-disk readability while open,
and the closed file's packet list (ffprobe). Functional only."""
import json, shutil, subprocess, sys
from fractions import Fraction
import av, av.logging
sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/write_throughput")
import wt_common as W
MEDIA = W.MEDIA / "av19_checks_emptypkt_ts"; MEDIA.mkdir(parents=True, exist_ok=True)
N = 10
src = W.load_mjpeg_set("c930e_720p_flash", N); US = Fraction(1, 1_000_000)
p = MEDIA / "x.mkv"
def on_disk():
    s = MEDIA / "snap.mkv"; shutil.copyfile(p, s); n = 0
    try:
        with av.open(str(s)) as ic:
            for pk in ic.demux(ic.streams.video[0]):
                if pk.size and n < N and bytes(pk) == src[n]: n += 1
    except Exception: pass
    s.unlink(); return n
av.logging.set_level(av.logging.WARNING)
res = dict(env=W.env_versions(), N=N, steps=[])
with av.logging.Capture(local=False) as logs:
    c = av.open(str(p), "w", format="matroska", options={"flush_packets": "1"})
    st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
    for i in range(N):
        n0 = len(logs)
        t = int(i * 1e6 / 30)
        pk = av.Packet(src[i]); pk.stream = st; pk.time_base = US; pk.pts = pk.dts = t; pk.is_keyframe = True
        c.mux(pk)
        ep = av.Packet(); ep.stream = st; ep.time_base = US; ep.pts = ep.dts = t + 1
        try:
            c.mux_one(ep); r = "no exception"
        except Exception as e:  # noqa: BLE001
            r = f"{type(e).__name__}: {e}"
        res["steps"].append(dict(frame=i, mux_one_empty=r, on_disk_exact=on_disk(),
                                 logs=[f"{l} {nm}: {m.strip()}" for l, nm, m in list(logs)[n0:]][:6]))
    c.close()
av.logging.set_level(None)
pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts,size,flags", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
res["ffprobe_closed"] = [l for l in pr.stdout.splitlines() if l.strip()]
res["ffprobe_stderr"] = pr.stderr.strip()
(W.RESULTS / "functional" / "mkv_emptypkt_ts_av19.0.2.json").write_text(json.dumps(res, indent=1, default=str))
shutil.rmtree(MEDIA, ignore_errors=True)
print(json.dumps(res, indent=1)[:3500])
