# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy", "opencv-python==4.12.0.88"]
# ///
"""Functional (no timing), PyAV 19.0.2: MKV writer that muxes an EMPTY av.Packet() after every MJPEG frame
(flush_packets=1). Questions: (1) is every frame on disk while the writer is still open (snapshot after each
of N frames)? (2) what do readers see in the closed file (ffprobe packets/sizes, PyAV demux/decode, cv2)?
Control: the same without empty packets."""
import json, shutil, subprocess, sys
from fractions import Fraction
from pathlib import Path
import av, cv2

sys.path.insert(0, "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/write_throughput")
import wt_common as W

MEDIA = W.MEDIA / "av19_checks_emptypkt"
RES = W.RESULTS / "functional"
N = 30
src = W.load_mjpeg_set("c930e_720p_flash", N)
US = Fraction(1, 1_000_000)


def snapshot_exact(path: Path) -> int:
    snap = path.with_suffix(".snap.mkv")
    shutil.copyfile(path, snap)
    n = 0
    try:
        with av.open(str(snap)) as ic:
            for pk in ic.demux(ic.streams.video[0]):
                if pk.size and n < N and bytes(pk) == src[n]:
                    n += 1
    except Exception:  # noqa: BLE001
        pass
    snap.unlink()
    return n


def readers(path: Path) -> dict:
    d = {}
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=size,pts,flags",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    sizes = [int(l.split(",")[1]) for l in lines]
    d["ffprobe_packets"] = len(lines)
    d["ffprobe_zero_size_packets"] = sum(1 for s in sizes if s == 0)
    d["ffprobe_first_lines"] = lines[:4]
    d["ffprobe_stderr_tail"] = p.stderr.strip().splitlines()[-1:] if p.stderr.strip() else []
    dec, errs, demux_n, empty_n = 0, [], 0, 0
    with av.open(str(path)) as ic:
        st = ic.streams.video[0]
        for pk in ic.demux(st):
            if pk.dts is None and pk.size == 0:
                continue  # demuxer flush packet at EOF
            demux_n += 1
            empty_n += pk.size == 0
            try:
                dec += len(pk.decode())
            except Exception as e:  # noqa: BLE001
                errs.append(f"{type(e).__name__}: {e}")
    d.update(pyav_demux_packets=demux_n, pyav_empty_packets=empty_n, pyav_decoded_frames=dec, pyav_decode_errors=errs[:3],
             pyav_decode_error_count=len(errs))
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    n = 0
    while cap.isOpened():
        ok, _ = cap.read()
        if not ok:
            break
        n += 1
    d["cv2_frames"] = n
    return d


rows = []
MEDIA.mkdir(parents=True, exist_ok=True)
for name, empty in (("mkv_flush", False), ("mkv_flush_emptypkt", True)):
    p = MEDIA / f"{name}.mkv"
    row = dict(variant=name, options={"flush_packets": "1"}, empty_packet_after_each_frame=empty, frames=N)
    c = av.open(str(p), "w", format="matroska", options={"flush_packets": "1"})
    st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
    lag = []
    try:
        for i in range(N):
            pk = av.Packet(src[i]); pk.stream = st; pk.time_base = US
            pk.pts = pk.dts = int(i * 1_000_000 / 30); pk.is_keyframe = True
            c.mux(pk)
            if empty:
                ep = av.Packet(); ep.stream = st
                c.mux_one(ep)
            if i in (0, 1, 9, N - 1):
                lag.append(dict(after_frame=i + 1, readable_exact_on_disk=snapshot_exact(p)))
        row["while_open"] = lag
        c.close()
        row["closed"] = readers(p)
    except Exception as e:  # noqa: BLE001
        row["error"] = f"{type(e).__name__}: {e}"
    rows.append(row)
    print(json.dumps(row), flush=True)

out = dict(env=W.env_versions(), ffmpeg=getattr(av, "ffmpeg_version_info", None), rows=rows)
(RES / "mkv_emptypkt_check_av19.0.2.json").write_text(json.dumps(out, indent=1, default=str))
shutil.rmtree(MEDIA, ignore_errors=True)
print("wrote", RES / "mkv_emptypkt_check_av19.0.2.json")
