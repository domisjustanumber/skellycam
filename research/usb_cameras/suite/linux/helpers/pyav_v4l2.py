# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2"]
# ///
"""PyAV / FFmpeg v4l2 input with input_format=mjpeg: the camera's JPEG packets (never decoded). Linux suite helper.

    uv run --script pyav_v4l2.py version
    uv run --script pyav_v4l2.py capture --device /dev/video0 --width 1280 --height 720 --fps 30
                                 (--frames N | --seconds S) --out-dir D [--raw-dir R] [--save none|all|first:K]
    uv run --script pyav_v4l2.py cycle   --device /dev/video0 --width W --height H --fps F --cycles K --frames N
                                 --out-dir D [--alt-width ... --alt-height ... --alt-fps ...] [--gap-ms G]

Writes D/frames.jsonl (seq, host_ns, pts, pts_ns, bytes, soi, eoi, sof0_w, sof0_h, hdr_sha1, zero_len, raw_off,
raw_len) or D/cycles.jsonl (the camworker cycle schema: i, mode, ok, stage_failed, errno, errno_name, open_ms,
first_frame_ms, frames, close_ms ...), and prints ONE JSON object. Exit: 0 ok, 2 usage, 4 camera failure.

Notes (plan section 2.6 / linux.md section 4):
- FFmpeg turns a buffer flagged V4L2_BUF_FLAG_ERROR into a zero-length packet: counted as zero_len.
- FFmpeg 9.0.2 (bundled with PyAV 19.0.2) still has the v4l2 out-of-bounds read on compressed mmap packets that
  FFmpeg master fixed on 2026-10-20 (deps_audit verifier D31). A crash here is a RESULT; the runner records it.
- With -ts default the packet pts is the kernel buffer timestamp (CLOCK_MONOTONIC, microseconds).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

SUITE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SUITE_DIR))
from common import jpegcheck  # noqa: E402  (stdlib only)


def mono_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def emit(obj: dict, rc: int) -> int:
    obj.setdefault("exit_code", rc)
    print(json.dumps(obj, default=str), flush=True)
    return rc


def quick(data: bytes) -> dict:
    out = {"soi": data[:2] == b"\xff\xd8", "eoi": data.rfind(b"\xff\xd9", max(0, len(data) - 64)) >= 0,
           "sof0_w": None, "sof0_h": None, "hdr_sha1": None}
    if out["soi"]:
        sof = jpegcheck.parse_sof0(data[:65536])
        if sof:
            out["sof0_w"], out["sof0_h"] = sof["w"], sof["h"]
        span = jpegcheck.header_span(data[:65536])
        if span:
            out["hdr_sha1"] = hashlib.sha1(data[span[0]:span[1]]).hexdigest()
    return out


def err_info(e: BaseException) -> dict:
    return {"type": type(e).__name__, "errno": getattr(e, "errno", None),
            "errno_name": __import__("errno").errorcode.get(getattr(e, "errno", None) or -1),
            "message": str(e)[:500]}


def open_container(a, w, h, fps):
    import av
    opts = {"input_format": "mjpeg", "video_size": f"{w}x{h}", "framerate": f"{fps:g}", "ts": "default"}
    return av.open(a.device, format="v4l2", options=opts, timeout=(a.open_timeout_s, a.read_timeout_s))


def run_session(a, w, h, fps, n_frames, seconds, fh=None, raw=None, save=("none", 0)):
    t0 = mono_ns()
    r = {"mode": f"MJPG {w}x{h}@{fps:g}", "ok": False, "stage_failed": None, "frames": 0, "zero_len": 0,
         "bad_markers": 0, "hdr_sha1": {}, "sof_sizes": {}}
    c = None
    try:
        c = open_container(a, w, h, fps)
        r["open_ms"] = round((mono_ns() - t0) / 1e6, 3)
        st = c.streams.video[0]
        cc = st.codec_context
        r["stream"] = {"codec": cc.name, "width": cc.width, "height": cc.height,
                       "pix_fmt": getattr(cc, "pix_fmt", None), "time_base": str(st.time_base),
                       "average_rate": str(st.average_rate)}
        t_first = None
        t_last = None
        deadline = None
        raw_off = raw.tell() if raw else 0
        for pkt in c.demux(st):
            host = mono_ns()
            data = bytes(pkt)
            if pkt.size == 0 and pkt.pts is None:
                continue  # flush packet
            if t_first is None:
                t_first = host
                r["first_frame_ms"] = round((host - t0) / 1e6, 3)
                if seconds:
                    deadline = host + int(seconds * 1e9)
            t_last = host
            q = quick(data) if data else {"soi": False, "eoi": False, "sof0_w": None, "sof0_h": None,
                                          "hdr_sha1": None}
            if not data:
                r["zero_len"] += 1
            if not (q["soi"] and q["eoi"]):
                r["bad_markers"] += 1
            if q["hdr_sha1"]:
                r["hdr_sha1"][q["hdr_sha1"]] = r["hdr_sha1"].get(q["hdr_sha1"], 0) + 1
            sz = f"{q['sof0_w']}x{q['sof0_h']}"
            r["sof_sizes"][sz] = r["sof_sizes"].get(sz, 0) + 1
            row = None
            if fh is not None:
                pts_ns = int(pkt.pts * pkt.time_base * 1_000_000_000) if pkt.pts is not None else None
                row = {"seq": r["frames"], "host_ns": host, "pts": pkt.pts, "pts_ns": pts_ns, "bytes": len(data),
                       "zero_len": not data, **q}
            kind, k = save
            if raw is not None and data and (kind == "all" or (kind == "first" and r["frames"] < k)):
                raw.write(data)
                if row is not None:
                    row["raw_off"], row["raw_len"] = raw_off, len(data)
                raw_off += len(data)
            if row is not None:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            r["frames"] += 1
            if (n_frames and r["frames"] >= n_frames) or (deadline and host >= deadline):
                break
        if t_first and t_last and r["frames"] > 1 and t_last > t_first:
            r["fps_host"] = round((r["frames"] - 1) / ((t_last - t_first) / 1e9), 3)
        r["ok"] = r["frames"] > 0 and (not n_frames or r["frames"] >= n_frames)
        if not r["frames"]:
            r["stage_failed"] = "first_frame"
    except Exception as e:  # av.error.* carry errno
        r["stage_failed"] = "open" if "open_ms" not in r else "read"
        r.update({"error": err_info(e), "errno": getattr(e, "errno", None),
                  "errno_name": err_info(e)["errno_name"]})
    finally:
        t1 = mono_ns()
        if c is not None:
            try:
                c.close()
            except Exception as e:
                r["close_error"] = err_info(e)
        r["close_ms"] = round((mono_ns() - t1) / 1e6, 3)
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version")
    for name in ("capture", "cycle"):
        p = sub.add_parser(name)
        p.add_argument("--device", required=True)
        p.add_argument("--width", type=int, required=True)
        p.add_argument("--height", type=int, required=True)
        p.add_argument("--fps", type=float, required=True)
        p.add_argument("--frames", type=int, default=None)
        p.add_argument("--out-dir", required=True)
        p.add_argument("--open-timeout-s", type=float, default=10.0)
        p.add_argument("--read-timeout-s", type=float, default=4.0)
        if name == "capture":
            p.add_argument("--seconds", type=float, default=None)
            p.add_argument("--raw-dir", default=None)
            p.add_argument("--save", default="none")
        else:
            p.add_argument("--cycles", type=int, required=True)
            p.add_argument("--alt-width", type=int, default=None)
            p.add_argument("--alt-height", type=int, default=None)
            p.add_argument("--alt-fps", type=float, default=None)
            p.add_argument("--gap-ms", type=float, default=0)
    a = ap.parse_args()
    try:
        import av
    except Exception as e:
        return emit({"cmd": a.cmd, "error": err_info(e)}, 4)
    if a.cmd == "version":
        return emit({"cmd": "version", "av": av.__version__,
                     "ffmpeg": getattr(av, "ffmpeg_version_info", None) or str(getattr(av, "library_versions", ""))},
                    0)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "capture":
        save = ("none", 0) if a.save == "none" else (("all", 0) if a.save == "all"
                                                    else (a.save.split(":")[0], int(a.save.split(":")[1])))
        raw = None
        if save[0] != "none":
            rd = Path(a.raw_dir or a.out_dir)
            rd.mkdir(parents=True, exist_ok=True)
            raw = (rd / "frames.mjpeg").open("wb")
        with (out / "frames.jsonl").open("w", buffering=1) as fh:
            r = run_session(a, a.width, a.height, a.fps, a.frames, a.seconds if not a.frames else None, fh, raw,
                            save)
        if raw:
            raw.close()
            r["raw_file"] = raw.name
        r.update({"cmd": "capture", "api": "pyav_v4l2", "av": av.__version__, "device": a.device})
        (out / "summary.json").write_text(json.dumps(r, default=str, indent=1))
        return emit(r, 0 if r["ok"] else 4)
    rows = []
    with (out / "cycles.jsonl").open("w", buffering=1) as fh:
        for i in range(a.cycles):
            alt = bool(a.alt_width and a.alt_height) and i % 2 == 1
            w, h, f = (a.alt_width, a.alt_height, a.alt_fps or a.fps) if alt else (a.width, a.height, a.fps)
            r = run_session(a, w, h, f, a.frames or 30, None)
            r = {"i": i, **{k: v for k, v in r.items() if k not in ("hdr_sha1", "sof_sizes")}}
            fh.write(json.dumps(r, default=str) + "\n")
            rows.append(r)
            if a.gap_ms:
                time.sleep(a.gap_ms / 1000)
    return emit({"cmd": "cycle", "api": "pyav_v4l2", "av": av.__version__, "device": a.device, "rows": len(rows),
                 "n_ok": sum(1 for r in rows if r["ok"])}, 0)


if __name__ == "__main__":
    sys.exit(main())
