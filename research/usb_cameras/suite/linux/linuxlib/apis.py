"""Run one capture or one cycle batch through a given API and analyse it (runner side; children do the I/O).

APIs: 'v4l2' (linuxlib/camworker.py, the reference), 'pyav' (helpers/pyav_v4l2.py), 'opencv'
(helpers/opencv_v4l2.py), 'gst' (gst-launch-1.0 v4l2src ! image/jpeg ! multifilesink, if installed).
Every call goes through ctx.camcmd (camera lock + child timeout) and never raises: failures are returned.
"""
from __future__ import annotations

import os
import shutil
from fractions import Fraction
from pathlib import Path
from typing import Any

from common import results, topology_model as tm
import analysis
from suitectx import child_outcome, errno_from_text
from tutil import mode_args, mode_text, worker_error

KNOWN_QUIRKS = {("4c4a", "4a55"): "generic Jieli camera: extraneous bytes before EOI at large modes (REPORT finding 6)"}


def capture_timeout(seconds: float, fps: float) -> float:
    return 25.0 + seconds * 2.0 + 3 * (1.0 / max(fps, 1.0))


def frame_timeout_ms(fps: float) -> float:
    return max(2000.0, 3000.0 / max(fps, 0.5))


def capture(ctx, api: str, cam: dict[str, Any], mode: dict[str, Any], seconds: float, out_dir: Path,
            raw_dir: Path | None, save: str = "all", extra: list[str] | None = None, analyse: bool = True,
            timeout_s: float | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if raw_dir is not None:
        raw_dir.mkdir(parents=True, exist_ok=True)
    fps = float(mode["fps"])
    to = timeout_s or capture_timeout(seconds, fps)
    if not timeout_s and extra:
        # each control set + readback can take one uvcvideo control timeout (~5 s) on a camera that stopped
        # answering (the Kiyo): give the worker time to record that instead of being killed without a JSON
        n_sets = sum(str(v).count("=") for k, v in zip(extra, extra[1:]) if k in ("--controls-before", "--schedule"))
        to += 12.0 * n_sets
    env = None
    if api == "v4l2":
        argv = ctx.worker_cmd("capture", "--device", cam["node"], *mode_args(mode), "--seconds", seconds,
                              "--out-dir", out_dir, "--save", save if raw_dir else "none",
                              "--timeout-ms", frame_timeout_ms(fps), "--first-frame-timeout-ms",
                              max(5000.0, frame_timeout_ms(fps)), *(["--raw-dir", raw_dir] if raw_dir else []),
                              *(extra or []))
    elif api in ("pyav", "opencv"):
        helper = "pyav_v4l2.py" if api == "pyav" else "opencv_v4l2.py"
        argv = ctx.helper_cmd(helper, "capture", "--device", cam["node"], "--width", mode["w"], "--height", mode["h"],
                              "--fps", f"{fps:g}", "--seconds", seconds, "--out-dir", out_dir,
                              "--save", save if raw_dir else "none", *(["--raw-dir", raw_dir] if raw_dir else []))
        if api == "opencv":
            env = {"OPENCV_LOG_LEVEL": "DEBUG", "OPENCV_VIDEOIO_DEBUG": "1"}
    elif api == "gst":
        # frames never go into the results tree: without a raw dir use a scratch folder under the raw root
        return gst_capture(ctx, cam, mode, seconds, out_dir, raw_dir or ctx.raw_test_dir("gst_scratch"), to)
    else:
        return {"api": api, "ok": False, "error": {"message": f"unknown api {api}"}}
    r = ctx.camcmd(argv, timeout_s=to, env=env)
    j = r.get("json") or {}
    out: dict[str, Any] = {"api": api, "mode": mode_text(mode), "child": child_outcome(r), "error": worker_error(r)}
    if api == "opencv" and not j.get("ok"):
        out["opencv_streamon_errno"] = errno_from_text(r.get("stderr") or "")
    if api == "v4l2":
        st = j.get("stream") or {}
        fmt = ((j.get("info") or {}).get("format") or {})
        out.update({"timings": j.get("timings"), "format": fmt, "size_ok": fmt.get("size_ok"),
                    "fourcc_ok": fmt.get("fourcc_ok"), "first_frame_ms": (j.get("timings") or {}).get("first_frame_ms"),
                    "fps_host": st.get("fps_host"), "fps_buffer_ts": st.get("fps_buffer_ts"),
                    "counts": st.get("counts"), "cpu_pct_one_core": st.get("cpu_pct_one_core"),
                    "granted_alt": (((st.get("granted") or {}).get("alts") or [{}])[0]).get("alt"),
                    "parm": (j.get("info") or {}).get("parm"), "meta": (j.get("info") or {}).get("meta"),
                    "schedule_events": st.get("schedule_events"), "controls_before": j.get("controls_before"),
                    "usb_before": j.get("usb_before"), "usb_after": j.get("usb_after")})
        frames = st.get("counts", {}).get("frames", 0) if st else 0
        n_err = (st.get("counts") or {}).get("error_flag", 0) if st else 0
        # usable rate = frames not flagged V4L2_BUF_FLAG_ERROR (6.14+ delivers corrupt frames flagged; 6.8 drops
        # them, which lowers fps_host): the same quantity on every kernel leg
        out["fps_usable"] = (round(st["fps_host"] * (frames - n_err) / frames, 3)
                             if st.get("fps_host") and frames else st.get("fps_host"))
    else:
        out.update({"stream": j.get("stream") or j.get("negotiated"), "first_frame_ms": j.get("first_frame_ms"),
                    "fps_host": j.get("fps_host"), "zero_len": j.get("zero_len"), "not_raw": j.get("not_raw")})
        frames = j.get("frames", 0)
    out["frames"] = frames
    out["ok"] = bool(frames) and out["error"] is None
    rows = analysis.read_rows(out_dir / "frames.jsonl")
    out["rows"] = len(rows)
    if analyse:
        raw_file = (raw_dir / "frames.mjpeg") if raw_dir else None
        out["check"] = analysis.check_frames(rows, raw_file, int(mode["w"]), int(mode["h"]),
                                             exclude_error_flag=(api == "v4l2"))
        out["fps_rows"] = analysis.fps_from_rows(rows)
    return out


def gst_capture(ctx, cam, mode, seconds, out_dir, raw_dir, timeout_s) -> dict[str, Any]:
    if not shutil.which("gst-launch-1.0"):
        return {"api": "gst", "ok": False, "skipped": "gst-launch-1.0 not installed"}
    fps = Fraction(float(mode["fps"])).limit_denominator(1001)
    n = max(5, int(round(float(mode["fps"]) * seconds)))
    gdir = raw_dir / "gst_frames"
    if gdir.exists():
        shutil.rmtree(gdir, ignore_errors=True)
    gdir.mkdir(parents=True, exist_ok=True)
    argv = ["gst-launch-1.0", "-q", "v4l2src", f"device={cam['node']}", f"num-buffers={n}", "!",
            f"image/jpeg,width={mode['w']},height={mode['h']},framerate={fps.numerator}/{fps.denominator}", "!",
            "multifilesink", f"location={gdir}/f_%05d.jpg"]
    r = ctx.camcmd(argv, timeout_s=timeout_s)
    files = sorted(gdir.glob("f_*.jpg"))
    rows, off = [], 0
    raw = raw_dir / "frames.mjpeg"
    with raw.open("wb") as f:
        for p in files:
            b = p.read_bytes()
            f.write(b)
            rows.append({"seq": len(rows), "bytes": len(b), "raw_off": off, "raw_len": len(b),
                         "soi": b[:2] == b"\xff\xd8", "eoi": b.rfind(b"\xff\xd9", max(0, len(b) - 64)) >= 0})
            off += len(b)
    shutil.rmtree(gdir, ignore_errors=True)
    for row in rows:
        results.append_jsonl(out_dir / "frames.jsonl", row)
    chk = analysis.check_frames(rows, raw, int(mode["w"]), int(mode["h"]))
    return {"api": "gst", "mode": mode_text(mode), "ok": bool(rows) and r.get("rc") == 0, "frames": len(rows),
            "child": child_outcome(r), "check": chk,
            "error": None if r.get("rc") == 0 else {"message": (r.get("stderr") or "")[-500:]}}


def classify(err: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """classify_failure('linux', errno, ...) for a camworker error dict."""
    if not err:
        return None
    ctx_ = dict(context or {})
    ctx_.setdefault("api", "v4l2")
    stage = (err.get("stage") or "").lower()
    ctx_.setdefault("stage", stage)
    if err.get("errno_name") == "timeout" or stage == "timeout":
        return tm.classify_failure("linux", "timeout", {**ctx_, "timed_out": True})
    code = err.get("errno") if err.get("errno") is not None else err.get("errno_name")
    if code is None and stage == "first_frame":
        return tm.classify_failure("linux", None, {**ctx_, "frames": 0})
    return tm.classify_failure("linux", code, ctx_)


def mjpeg_mode_row(cam: dict[str, Any], mode: dict[str, Any], ref: dict[str, Any],
                   hashes: dict[str, str | None]) -> dict[str, Any]:
    """Input row for common.rating.rate_mjpeg from a reference capture."""
    chk = ref.get("check") or {}
    quirk = None
    if (cam["vid"], cam["pid"]) in KNOWN_QUIRKS and (chk.get("extra_bytes_before_eoi") or chk.get("strict_ok_fraction")
                                                     not in (None, 1.0)):
        quirk = KNOWN_QUIRKS[(cam["vid"], cam["pid"])]
    sof_frac = chk.get("sof_matches_request_fraction")
    return {"mode": mode_text(mode), "negotiated": bool(ref.get("ok") and ref.get("size_ok") is not False
                                                        and ref.get("fourcc_ok") is not False),
            "frames": ref.get("frames"), "strict_valid_fraction": chk.get("strict_ok_fraction"),
            "lenient_valid_fraction": chk.get("lenient_ok_fraction"), "known_quirk": quirk,
            "sof_matches": (sof_frac == 1.0) if sof_frac is not None else None,
            "fps_measured": ref.get("fps_usable", ref.get("fps_host")), "fps_expected": float(mode["fps"]),
            "header_sha1_by_api": {k: v for k, v in hashes.items() if v} or None,
            "is_jpeg": (chk.get("soi_fraction") or 0) > 0.5 if chk.get("n") else None,
            "error_flag_frames": (ref.get("counts") or {}).get("error_flag"),
            "seq_missing": (ref.get("counts") or {}).get("seq_missing")}


def prune_raw(raw_dir: Path, rows_file: Path, keep_frames: int = 3) -> None:
    """Keep only the first few frames of a raw dump (as samples.mjpeg) to bound disk use."""
    raw = raw_dir / "frames.mjpeg"
    if not raw.exists():
        return
    rows = results.read_jsonl(rows_file)
    saved = [r for r in rows if r.get("raw_off") is not None][:keep_frames]
    if saved:
        end = max(int(r["raw_off"]) + int(r["raw_len"]) for r in saved)
        with raw.open("rb") as f, (raw_dir / "samples.mjpeg").open("wb") as g:
            g.write(f.read(end))
    try:
        os.unlink(raw)
    except OSError:
        pass
