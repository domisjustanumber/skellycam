"""Crash-side checks for passthrough containers (compat side of G1/G5; the crash_resilience topic goes deeper).

A) Hard stop without close: a child process muxes K camera JPEGs with PyAV and calls os._exit(1) without closing the
   container (no trailer, no user-space flush; same effect on Python/FFmpeg buffers as TerminateProcess). Then every reader.
B) Byte truncation of a cleanly closed file at 50% and 90% of its size (cut lands mid-packet).
C) AVI over 1 GiB (OpenDML RIFF-AVIX): 6000 looped c922_1080p frames, readers + seek near the end. File deleted afterwards.

Run (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/truncation_check.py [--skip-large]
Writes results/jpeg_passthrough/truncation.json
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402
import jp_io as io  # noqa: E402

SET = "c930e_720p_flash"
CONTS = ["mkv", "mp4", "fmp4_1s", "fmp4_perframe", "mov", "avi_tb_rate", "nut", "mjpeg_raw_mux", "raw_sidecar"]


def child(cont: str, path: str, k: int) -> None:
    """Mux k frames then die without closing."""
    frames = C.load_set(SET, k)
    ts = C.real_timestamps_ns(SET, C.load_set(SET))[:k]
    us = [(t - ts[0]) // 1000 for t in ts]
    if cont == "raw_sidecar":
        p = Path(path)
        f = open(p, "wb")  # noqa: SIM115 - deliberately never closed
        fi = open(p.with_suffix(".idx"), "wb")  # noqa: SIM115
        off = 0
        for fb, t in zip(frames, ts):
            f.write(fb)
            fi.write(io.IDX_REC.pack(off, len(fb), t))
            off += len(fb)
        os._exit(1)
    import av
    from fractions import Fraction
    fmt, _, opts = io.CONTAINERS[cont][:3]
    stb = io.CONTAINERS[cont][3] if len(io.CONTAINERS[cont]) > 3 else None
    c = av.open(path, "w", format=fmt, options=dict(opts))
    st = c.add_mux_stream("mjpeg", rate=30, width=1280, height=720)
    if stb == "rate":
        st.time_base = Fraction(1, 30)
    vfr = stb != "rate"
    for i, fb in enumerate(frames):
        pkt = av.Packet(fb)
        pkt.stream = st
        pkt.time_base = Fraction(1, 1_000_000) if vfr else Fraction(1, 30)
        pkt.pts = pkt.dts = us[i] if vfr else i
        pkt.is_keyframe = True
        c.mux(pkt)
    os._exit(1)


def read_side(path: Path, frames: list[bytes]) -> dict:
    data = path.read_bytes()
    idx = path.with_suffix(".idx").read_bytes()
    ok = 0
    for i in range(len(idx) // io.IDX_REC.size):
        off, size, _ = io.IDX_REC.unpack_from(idx, i * io.IDX_REC.size)
        if off + size <= len(data) and i < len(frames) and data[off:off + size] == frames[i]:
            ok += 1
        else:
            break
    return {"sidecar_entries": len(idx) // io.IDX_REC.size, "sidecar_complete_exact_frames": ok, "data_bytes": len(data)}


def readers(path: Path, frames: list[bytes]) -> dict:
    in_shas = [C.sha(f) for f in frames]
    r = {"bytes": path.stat().st_size}
    fp = io.ffprobe(path)
    fp.pop("pts_time", None)
    r["ffprobe"] = {k: fp.get(k) for k in ("returncode", "stderr", "nb_frames", "nb_read_packets", "packets_nonempty")}
    pv = io.pyav_demux(path)
    if pv.get("ok"):
        sh = pv.pop("shas")
        pv.pop("pts_s", None)
        pre = 0
        for a, b in zip(sh, in_shas):
            if a != b:
                break
            pre += 1
        r["pyav"] = {"packets": len(sh), "exact_prefix": pre, "decoded": pv.get("decoded_frames"), "decode_errors": pv.get("decode_error_count"),
                     "first_errors": pv.get("decode_errors")[:2]}
    else:
        r["pyav"] = {"error": pv.get("error")}
    cv = io.cv2_read(path, "FFMPEG", None, seek=False)
    cv.pop("_hashes", None)
    cv.pop("pos_msec", None)
    r["cv2_ffmpeg"] = {k: cv.get(k) for k in ("opened", "frames_read", "frame_count_prop")}
    fm = io.freemocap_read(path, None)
    r["freemocap"] = {"frame_count": fm.get("frame_count"), "error": fm.get("error"),
                      "reads_ok": sum(1 for x in fm.get("reads", []) if x.get("ok")), "reads": len(fm.get("reads", []))}
    return r


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-large", action="store_true")
    ap.add_argument("--kill-after", type=int, default=600)
    a = ap.parse_args()
    d = C.MEDIA / "truncation"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    frames = C.load_set(SET)
    ts = C.real_timestamps_ns(SET, frames)
    us = [(t - ts[0]) // 1000 for t in ts]
    res = {"meta": {"date": time.strftime("%Y-%m-%dT%H:%M:%S"), "set": SET, "kill_after_frames": a.kill_after}, "killed": {}, "truncated": {}}
    for cont in CONTS:
        ext = ".mjpeg" if cont == "raw_sidecar" else io.CONTAINERS[cont][1]
        # A) killed child
        p = d / f"killed_{cont}{ext}"
        cp = subprocess.run([sys.executable, __file__, "--child", cont, str(p), str(a.kill_after)], capture_output=True)
        row = {"child_rc": cp.returncode, "child_stderr": cp.stderr.decode("utf8", "replace")[-200:]}
        if p.exists():
            row.update(read_side(p, frames) if cont == "raw_sidecar" else readers(p, frames))
        res["killed"][cont] = row
        print("killed", cont, row.get("pyav", row.get("sidecar_complete_exact_frames")), flush=True)
        # B) truncated clean file
        full = d / f"full_{cont}{ext}"
        if cont == "raw_sidecar":
            io.python_write(full, cont, frames, ts)
        else:
            vfr = cont != "avi_tb_rate"
            io.pyav_write(full, cont, frames, 1280, 720, us if vfr else None)
        for frac in (0.5, 0.9):
            tp = d / f"trunc{int(frac * 100)}_{cont}{ext}"
            b = full.read_bytes()
            tp.write_bytes(b[: int(len(b) * frac)])
            if cont == "raw_sidecar":
                ib = full.with_suffix(".idx").read_bytes()
                tp.with_suffix(".idx").write_bytes(ib)  # index complete, data truncated: reader must bounds-check
                r = read_side(tp, frames)
            else:
                r = readers(tp, frames)
            res["truncated"][f"{cont}|{frac}"] = r
            print("trunc", cont, frac, r.get("pyav", r.get("sidecar_complete_exact_frames")), r.get("cv2_ffmpeg"), flush=True)
    shutil.rmtree(d, ignore_errors=True)
    if not a.skip_large:
        big = C.load_looped("c922_1080p", 6000)
        p = C.MEDIA / "large" / "large_avi_tb_rate.avi"
        p.parent.mkdir(parents=True, exist_ok=True)
        wr = io.pyav_write(p, "avi_tb_rate", big, 1920, 1080, None)
        r = {"write": wr, "payload_bytes": sum(map(len, big))}
        head = p.read_bytes()
        r["riff_avix_chunks"] = head.count(b"AVIX")
        r["has_odml_indx"] = b"indx" in head[:65536]
        del head
        fp = io.ffprobe(p)
        fp.pop("pts_time", None)
        r["ffprobe"] = {k: fp.get(k) for k in ("returncode", "nb_frames", "nb_read_packets")}
        pv = io.pyav_demux(p, decode=False)
        sh = pv.pop("shas", [])
        r["pyav_byte_exact_all"] = sh == [C.sha(x) for x in big]
        r["pyav_packets"] = len(sh)
        cv = io.cv2_read(p, "FFMPEG", None, seek=True)
        cv.pop("_hashes", None)
        cv.pop("pos_msec", None)
        r["cv2_ffmpeg"] = {k: cv.get(k) for k in ("opened", "frames_read", "frame_count_prop", "seek_exact", "seek_total")}
        ms = io.cv2_read(p, "MSMF", None, seek=False)
        ms.pop("_hashes", None)
        ms.pop("pos_msec", None)
        r["cv2_msmf"] = {k: ms.get(k) for k in ("opened", "frames_read", "frame_count_prop")}
        fm = io.freemocap_read(p, None)
        r["freemocap"] = {"frame_count": fm.get("frame_count"), "reads": fm.get("reads"), "error": fm.get("error")}
        res["large_avi"] = r
        print("large", r, flush=True)
        p.unlink()
    C.write_json(C.RESULTS / "truncation.json", res)
    print("wrote", C.RESULTS / "truncation.json")


if __name__ == "__main__":
    main()
