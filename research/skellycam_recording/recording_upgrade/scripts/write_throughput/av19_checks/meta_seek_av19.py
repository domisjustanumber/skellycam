# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""Functional (no timing), PyAV 19.0.2: for MKV (flush_packets=1) and fMP4 (fragment per frame + flush_packets=1)
holding 300 camera JPEG packets at 30 fps: (1) what stream.frames / duration report from metadata, (2) whether
seek(pts, backward=True) + demux to the exact pts returns the right bytes for 100 random frame indices."""
import json, random, shutil, sys
from fractions import Fraction
import av
sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/write_throughput")
import wt_common as W
MEDIA = W.MEDIA / "av19_checks_meta_seek"; MEDIA.mkdir(parents=True, exist_ok=True)
src = W.load_mjpeg_set("c930e_720p_flash"); N = 300; US = Fraction(1, 1_000_000)
cases = {"mkv_flush": ("matroska", ".mkv", {"flush_packets": "1"}),
         "fmp4_frame_flush": ("mp4", ".mp4", {"flush_packets": "1", "movflags": "frag_keyframe+empty_moov+default_base_moof", "video_track_timescale": "90000"})}
rows = []
for name, (fmt, ext, opts) in cases.items():
    p = MEDIA / f"{name}{ext}"
    c = av.open(str(p), "w", format=fmt, options=opts)
    st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
    for i in range(N):
        pk = av.Packet(src[i % len(src)]); pk.stream = st; pk.time_base = US
        pk.pts = pk.dts = int(i * 1_000_000 / 30); pk.is_keyframe = True
        c.mux(pk)
    c.close()
    row = dict(variant=name, frames_written=N)
    with av.open(str(p)) as ic:
        s = ic.streams.video[0]
        row.update(stream_frames=s.frames, stream_duration=s.duration, stream_time_base=str(s.time_base),
                   container_duration_s=(ic.duration / 1e6 if ic.duration else None))
        # frame table by demux
        table = [(pk.pts, bytes(pk)) for pk in ic.demux(s) if pk.size]
    row["demux_packets"] = len(table)
    rnd = random.Random(3); wrong = 0; idxs = [rnd.randrange(N) for _ in range(100)]
    with av.open(str(p)) as ic:
        s = ic.streams.video[0]
        for k in idxs:
            target_pts, want = table[k]
            ic.seek(target_pts, stream=s, backward=True)
            got = None
            for pk in ic.demux(s):
                if pk.pts is None or not pk.size:
                    continue
                if pk.pts >= target_pts:
                    got = bytes(pk) if pk.pts == target_pts else None
                    break
            wrong += got != want
    row.update(random_seeks=len(idxs), random_wrong=wrong)
    rows.append(row); print(json.dumps(row), flush=True)
(W.RESULTS / "functional" / "meta_seek_check_av19.0.2.json").write_text(json.dumps(dict(env=W.env_versions(), rows=rows), indent=1, default=str))
shutil.rmtree(MEDIA, ignore_errors=True)
