# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""PyAV 19.0.2 functional check: does a timestamp seek (target = the frame's own pts from a sidecar) return the right
JPEG bytes, on files with real VFR timestamps and dropped frames? (jpeg_passthrough FINDINGS revision, 2026-11-09)

No timing. Frame identity = SHA-256 of the first demuxed packet after seek == SHA-256 of input frame k.
Sets: c930e_720p_flash real timestamps (floored to us); 'full' (891), 'gap60' (frames 300-359 removed, 831),
'drop50' (every 50th frame removed, 874). Containers: fMP4 1 s 1/1e6, fMP4 per-frame 1/1e6, MP4 1/1e6, MKV (1/1000).
Seek: container.seek(pts, stream=st, backward=True, any_frame=False), then next(demux). Files written to the media
folder and deleted.

Run (repo root):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/pyav19_seek_ts_check.py
"""
from __future__ import annotations

import shutil
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402

CONTS = {
    "fmp4_1s_tb_us": ("mp4", ".mp4", {"movflags": "frag_keyframe+empty_moov+default_base_moof", "min_frag_duration": "1000000"}, True),
    "fmp4_perframe_tb_us": ("mp4", ".mp4", {"movflags": "frag_keyframe+empty_moov+default_base_moof"}, True),
    "mp4_tb_us": ("mp4", ".mp4", {}, True),
    "mkv": ("matroska", ".mkv", {}, False),
}


def main() -> None:
    import av
    name = "c930e_720p_flash"
    frames = C.load_set(name)
    ts = C.real_timestamps_ns(name, frames)
    us_all = [(t - ts[0]) // 1000 for t in ts]
    variants = {
        "full": list(range(len(frames))),
        "gap60": [i for i in range(len(frames)) if not 300 <= i < 360],
        "drop50": [i for i in range(len(frames)) if i % 50 != 49],
    }
    d = C.MEDIA / "seek_ts_check"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    res = {"meta": {"pyav": av.__version__, "ffmpeg_version_info": getattr(av, "ffmpeg_version_info", None),
                    "set": name, "note": "functional only; no timing"}, "rows": {}}
    for vname, idx in variants.items():
        fr = [frames[i] for i in idx]
        us = [us_all[i] for i in idx]
        shas = [C.sha(f) for f in fr]
        n = len(fr)
        targets = sorted(set([0, 1, 2, 81, 82, 299, 300, 301, n // 3, n // 2, n - 2, n - 1] + list(range(0, n, 37))))
        for cname, (fmt, ext, opts, tb_us) in CONTS.items():
            p = d / f"{vname}_{cname}{ext}"
            with av.open(str(p), "w", format=fmt, options=dict(opts)) as c:
                st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
                if tb_us:
                    st.time_base = Fraction(1, 1_000_000)
                for k, b in enumerate(fr):
                    pkt = av.Packet(b)
                    pkt.stream = st
                    pkt.time_base = Fraction(1, 1_000_000)
                    pkt.pts = pkt.dts = us[k]
                    c.mux(pkt)
            out = {"n": n, "targets": len(targets), "exact_bytes": 0, "misses": []}
            with av.open(str(p)) as c:
                st = c.streams.video[0]
                tb = st.time_base
                # sidecar-style target: the pts the file stores for frame k (read once sequentially), as a reader with
                # a sidecar would map ns -> stream ticks. For MKV this is the ms-rounded value.
                stored = [pk.pts for pk in c.demux(st) if pk.size]
                out["stream_tb"] = str(tb)
                out["stored_pts_count"] = len(stored)
                for k in targets:
                    tgt_sidecar = int(round(Fraction(us[k], 1_000_000) / tb))
                    c.seek(tgt_sidecar, stream=st, backward=True, any_frame=False)
                    pk = next(pk for pk in c.demux(st) if pk.size)
                    got = C.sha(bytes(pk))
                    if got == shas[k]:
                        out["exact_bytes"] += 1
                    else:
                        gi = shas.index(got) if got in shas else -1
                        out["misses"].append({"k": k, "target_pts": tgt_sidecar, "got_index": gi, "got_pts": pk.pts})
            res["rows"][f"{vname}|{cname}"] = out
            print(vname, cname, out["exact_bytes"], "/", out["targets"], out["misses"][:3], flush=True)
            p.unlink()
    shutil.rmtree(d, ignore_errors=True)
    C.write_json(C.RESULTS / "pyav19_seek_ts_check.json", res)
    print("wrote", C.RESULTS / "pyav19_seek_ts_check.json")


if __name__ == "__main__":
    main()
