# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "opencv-python==4.12.0.88"]
# ///
"""Lean PyAV 19.0.2 functional re-check of test_roundtrip.py and test_crash.py (python_integration topic).

Reuses the study scripts' writer, set loading, kill child and recovery code unchanged; only the expensive
full-decode loops are trimmed to keep CPU under a minute (other agents share the machine):
  - roundtrip: all 7 MJPEG sets x 5 (container, pts_mode) variants, packet-level checks as in
    test_roundtrip.check (byte-exact, sidecar ts/fn exact, PTS == sidecar, half-tick, adjusted count, overhead),
    cv2 CAP_FFMPEG open/FRAME_COUNT/FPS/FOURCC on every file; cv2 grab-count only for c930e_720p_flash;
    no PyAV full decode.
  - crash: part A (TerminateProcess kill at >=300 sidecar records, find_unfinished, recover) and part B
    (truncation at 50/90/99.9%/-1 byte) as in test_crash, with probe() trimmed to: exact-prefix packets,
    PyAV demux packet count, PyAV decode of the LAST packet only (is_corrupt flag / error), cv2 FRAME_COUNT and
    grab-count.
No timing is measured or reported. Media -> raw folder *_pyav19; JSON -> argv[1].
"""
from __future__ import annotations

import json
import shutil
import sys
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

S = Path("C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/python_integration")
sys.path.insert(0, str(S))
import recwriter as rw  # noqa: E402
import test_roundtrip as tr  # noqa: E402
import test_crash as tc  # noqa: E402

RAW = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration")
tr.MEDIA = RAW / "roundtrip_pyav19"
tc.MEDIA = RAW / "crash_pyav19"


def cv2_info(video: Path, grab: bool) -> dict:
    cap = cv2.VideoCapture(str(video), cv2.CAP_FFMPEG)
    o = {"cv2_opened": cap.isOpened()}
    if cap.isOpened():
        o["cv2_frame_count_prop"] = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        o["cv2_fps_prop"] = round(cap.get(cv2.CAP_PROP_FPS), 4)
        fcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        o["cv2_fourcc"] = "".join(chr((fcc >> 8 * i) & 0xFF) for i in range(4))
        if grab:
            n = 0
            while cap.grab():
                n += 1
            o["cv2_grabbed_frames"] = n
    cap.release()
    return o


def rt_check(stem: Path, frames, ts, fns, grab: bool) -> dict:
    man = json.loads(stem.with_name(stem.name + ".recording.json").read_text())
    video = stem.with_name(man["video"])
    side = rw.read_sidecar(stem.with_name(man["sidecar"]))
    pk = list(rw.RecordingReader(video).packets())
    res = {"container_time_base": man["time_base"], "packets": len(pk), "sidecar_records": int(len(side.records)),
           "bytes_exact": len(pk) == len(frames) and all(b == f for (_, b, _, _), f in zip(pk, frames)),
           "sidecar_crc_ok": side.bad_crc_records == 0 and side.torn_tail_bytes == 0,
           "sidecar_ts_exact": bool(np.array_equal(side.records["timestamp_ns"], np.array(ts, dtype=np.int64))),
           "sidecar_fn_exact": bool(np.array_equal(side.records["frame_number"], np.array(fns, dtype=np.int64))),
           "container_pts_eq_sidecar": len(pk) == len(side.records) and all(
               p[2] == int(r["pts"]) for p, r in zip(pk, side.records)),
           "pts_adjusted_frames": int(np.count_nonzero(side.records["flags"] & rw.FLAG_PTS_ADJUSTED))}
    tb = Fraction(man["time_base"])
    errs = [abs(float(pts * tb) - (t - ts[0]) / 1e9) for (_, _, pts, _), t, r in zip(pk, ts, side.records)
            if not (r["flags"] & rw.FLAG_PTS_ADJUSTED or man.get("pts_mode") == "index")]
    res["max_abs_pts_error_s_unadjusted"] = max(errs) if errs else None
    res["pts_within_half_tick"] = all(e <= float(tb / 2) + 1e-12 for e in errs)
    res.update(cv2_info(video, grab))
    res["container_overhead_bytes_per_frame"] = round((video.stat().st_size - sum(map(len, frames))) / len(frames), 1)
    return res


def roundtrip() -> dict:
    index = json.loads((tr.CORPUS / "index.json").read_text())
    if tr.MEDIA.exists():
        shutil.rmtree(tr.MEDIA)
    tr.MEDIA.mkdir(parents=True)
    rows = []
    for name, meta in index.items():
        if meta["kind"] != "mjpeg":
            continue
        frames, ts, src = tr.load_set(name)
        fns = list(range(1000, 1000 + len(frames)))
        for cont, mode in [(c, "real") for c in rw.CONTAINERS] + [("mkv", "index"), ("avi", "index")]:
            stem = tr.MEDIA / f"{name}.{cont}.{mode}"
            w = rw.RecordingWriter(stem, meta["width"], meta["height"], container=cont,
                                   nominal_fps=int(meta["nominal_fps"]), pts_mode=mode)
            for f, fn, t in zip(frames, fns, ts):
                w.write(f, fn, t)
            w.close()
            rows.append({"set": name, "container": cont, "pts_mode": mode, "frames_in": len(frames),
                         "timestamps": src, **rt_check(stem, frames, ts, fns, grab=name == "c930e_720p_flash")})
            print("RT", name, cont, mode, rows[-1]["bytes_exact"], rows[-1].get("cv2_frame_count_prop"), flush=True)
    return {"rows": rows}


def lean_probe(video: Path, frames: list[bytes] | None = None) -> dict:
    out = {"bytes": video.stat().st_size if video.exists() else 0}
    if frames is not None:
        n_exact, partial = 0, None
        try:
            for i, b, _, _ in rw.RecordingReader(video).packets():
                if i < len(frames) and b == frames[i]:
                    n_exact += 1
                else:
                    partial = {"index": i, "bytes": len(b), "expected": len(frames[i]) if i < len(frames) else None}
                    break
        except Exception as e:  # noqa: BLE001
            partial = repr(e)[:120]
        out["exact_prefix_packets"], out["first_non_exact_packet"] = n_exact, partial
    last, n_pk, err = None, 0, None
    try:
        with av.open(str(video)) as c:
            s = c.streams.video[0]
            try:
                for p in c.demux(s):
                    if p.size:
                        n_pk += 1
                        last = bytes(p)
            except Exception as e:  # noqa: BLE001
                err = repr(e)[:160]
    except Exception as e:  # noqa: BLE001
        err = repr(e)[:160]
    out["pyav_packets"], out["pyav_demux_error"] = n_pk, err
    out["pyav_decoded"] = "not run (lean: last packet only)"  # key needed by test_crash.part_b's print
    if last is not None:  # decode only the last packet: is a torn tail flagged?
        try:
            cc = av.CodecContext.create("mjpeg", "r")
            fr = list(cc.decode(av.Packet(last))) + list(cc.decode(None))
            out["last_packet_bytes"] = len(last)
            out["last_packet_decoded_frames"] = len(fr)
            out["last_packet_is_corrupt"] = [bool(f.is_corrupt) for f in fr]
            out["last_packet_decode_error"] = None
        except Exception as e:  # noqa: BLE001
            out["last_packet_decode_error"] = repr(e)[:160]
    o = cv2_info(video, grab=True)
    out.update({k: o.get(k) for k in ("cv2_opened", "cv2_frame_count_prop", "cv2_grabbed_frames")})
    out["cv2_read_frames"] = o.get("cv2_grabbed_frames")  # = grab() count; key needed by test_crash.part_b's print
    return out


def crash() -> dict:
    tc.probe = lean_probe  # part_a / part_b call the module-level probe()
    if tc.MEDIA.exists():
        shutil.rmtree(tc.MEDIA)
    return {"kill_at_sidecar_records": tc.KILL_AT, "part_a_kill": tc.part_a(), "part_b_truncate": tc.part_b()}


if __name__ == "__main__":
    dst = Path(sys.argv[1])
    out = {"what": "lean PyAV 19.0.2 re-check of test_roundtrip + test_crash (no timing; full decode trimmed)",
           "pyav": av.__version__, "ffmpeg": av.ffmpeg_version_info,
           "libavformat": av.library_versions["libavformat"], "opencv": cv2.__version__,
           "python": sys.version.split()[0], "date": "2026-11-09"}
    out["roundtrip"] = roundtrip()
    out["crash"] = crash()
    dst.write_text(json.dumps(out, indent=1, default=str))
    print("wrote", dst)
