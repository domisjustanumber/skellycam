# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""Functional (no timing) checks, PyAV 19.0.2:
A) While an MKV / fMP4 writer is still OPEN (flush_packets=1), how many of the N muxed frames are already
   readable byte-exact from the file on disk (snapshot copy)? Tests whether anything PyAV exposes
   (mux_one(None), an empty packet, the 'live' option) closes the Matroska cluster early.
B) Can a finer stream time base than 1/1000 be kept in MKV through PyAV (requested 1/1000000 and 1/90000)?
"""
import json, shutil, sys
from fractions import Fraction
from pathlib import Path
import av

sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/write_throughput")
import wt_common as W

MEDIA = W.MEDIA / "av19_checks"
RES = W.RESULTS / "functional"
N = 30
src = W.load_mjpeg_set("c930e_720p_flash", N)
US = Fraction(1, 1_000_000)


def count_exact(path: Path):
    snap = path.with_suffix(path.suffix + ".snap")
    shutil.copyfile(path, snap)
    n_exact, err = 0, None
    try:
        with av.open(str(snap)) as ic:
            for i, pk in enumerate(ic.demux(ic.streams.video[0])):
                if pk.size == 0:
                    continue
                if bytes(pk) == src[n_exact]:
                    n_exact += 1
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    size = snap.stat().st_size
    snap.unlink()
    return n_exact, size, err


def mux_n(c, st, n, start=0):
    for i in range(start, start + n):
        pk = av.Packet(src[i])
        pk.stream = st
        pk.time_base = US
        pk.pts = pk.dts = int(i * 1_000_000 / 30)
        pk.is_keyframe = True
        c.mux(pk)


rows = []
MEDIA.mkdir(parents=True, exist_ok=True)
cases = [
    ("mkv_flush", "matroska", ".mkv", {"flush_packets": "1"}),
    ("mkv_flush_live", "matroska", ".mkv", {"flush_packets": "1", "live": "1"}),
    ("mkv_flush_cluster_time_limit0", "matroska", ".mkv", {"flush_packets": "1", "cluster_time_limit": "0"}),
    ("fmp4_frame_flush", "mp4", ".mp4", {"flush_packets": "1", "movflags": "frag_keyframe+empty_moov+default_base_moof", "video_track_timescale": "90000"}),
]
for name, fmt, ext, opts in cases:
    p = MEDIA / f"{name}{ext}"
    row = dict(check="A_open_file_readable", variant=name, options=opts, muxed=N)
    try:
        c = av.open(str(p), "w", format=fmt, options=opts)
        st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
        mux_n(c, st, N)
        row["readable_exact_while_open"], row["bytes_on_disk"], row["read_err"] = count_exact(p)
        # try mux_one(None)
        try:
            c.mux_one(None)
            row["mux_one_None"] = "accepted"
        except Exception as e:  # noqa: BLE001
            row["mux_one_None"] = f"{type(e).__name__}: {e}"
        row["after_mux_one_None_readable_exact"] = count_exact(p)[0]
        # try an empty packet on the stream
        try:
            ep = av.Packet()
            ep.stream = st
            c.mux_one(ep)
            row["empty_packet"] = "accepted"
        except Exception as e:  # noqa: BLE001
            row["empty_packet"] = f"{type(e).__name__}: {e}"
        row["after_empty_packet_readable_exact"], _, row["after_empty_packet_read_err"] = count_exact(p)
        c.close()
        row["after_close_readable_exact"], row["bytes_after_close"], row["after_close_read_err"] = count_exact(p)
    except Exception as e:  # noqa: BLE001
        row["error"] = f"{type(e).__name__}: {e}"
    rows.append(row)
    print(json.dumps(row), flush=True)

for req in (Fraction(1, 1_000_000), Fraction(1, 90000)):
    p = MEDIA / f"tb_{req.denominator}.mkv"
    row = dict(check="B_mkv_time_base", requested=str(req))
    try:
        c = av.open(str(p), "w", format="matroska")
        st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
        st.time_base = req
        mux_n(c, st, 5)
        row["stream_time_base_after_header"] = str(st.time_base)
        c.close()
        with av.open(str(p)) as ic:
            s = ic.streams.video[0]
            row["read_back_time_base"] = str(s.time_base)
            row["read_back_pts"] = [pk.pts for pk in ic.demux(s) if pk.size][:5]
        row["written_pts_us"] = [int(i * 1_000_000 / 30) for i in range(5)]
    except Exception as e:  # noqa: BLE001
        row["error"] = f"{type(e).__name__}: {e}"
    rows.append(row)
    print(json.dumps(row), flush=True)

out = dict(env=W.env_versions(), ffmpeg=getattr(av, "ffmpeg_version_info", None), rows=rows)
(RES / "mkv_flush_timebase_check_av19.0.2.json").write_text(json.dumps(out, indent=1, default=str))
shutil.rmtree(MEDIA, ignore_errors=True)
print("wrote", RES / "mkv_flush_timebase_check_av19.0.2.json")
