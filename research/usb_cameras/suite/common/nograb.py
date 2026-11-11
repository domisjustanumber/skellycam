"""FMT-NOGRAB analysis, OS-neutral (plan docs/xplat_capture_plan.md section 6.2 FMT-NOGRAB; Dom 2026-11-06).

Question: which method identifies a camera's formats correctly WITHOUT grabbing the camera or starting a stream?
Every format-listing method on an OS runs under three conditions: (i) camera idle, (ii) camera streaming in another
process through the OS-native API, (iii) streaming in another process through the second API. Per method and
condition the suites measure: succeeded; completeness vs the USB descriptors (MJPEG and raw separately); elapsed;
disturbance of the other stream (max frame interval and errors during the listing window vs a baseline); whether it
starts a stream or reserves bandwidth (open isochronous pipe / non-zero alt setting while the method holds the
device); whether it blocks another process from opening the camera (a 1-frame capture from a third process during
the hold, against a control attempt without the method). ``common.rating.rate_fmt_nograb`` turns those into
yes / partial / no.

Modes are tuples ``(fourcc, width, height, interval_100ns)``; fourcc is upper case ('MJPG', 'YUY2', 'NV12', 'H264').
Stdlib only.
"""
from __future__ import annotations

import statistics
from typing import Any, Iterable, Sequence

#: uncompressed ("raw") fourccs a UVC camera / OS API may report
RAW_FOURCCS = {"YUY2", "YUYV", "YUV2", "UYVY", "NV12", "NV21", "I420", "IYUV", "YV12", "M420", "Y800", "GREY",
               "Y8", "Y16", "RGB3", "RGB24", "RGB32", "BGR3", "RGBP", "RGB565", "L8", "L16", "D16", "Y10", "Y12",
               "Y12I", "Z16", "INVZ", "HM12", "YVYU", "VYUY", "422V", "BA81"}
#: fourcc aliases the listing APIs use for the same descriptor format
FOURCC_ALIASES = {"MJPEG": "MJPG", "JPEG": "MJPG", "YUYV": "YUY2", "YUYV422": "YUY2", "YUV422": "YUY2",
                  "YUVY": "YUY2", "YUY2": "YUY2", "AVC1": "H264", "H.264": "H264", "X264": "H264"}
#: FFmpeg pixel_format / vcodec names -> fourcc (dshow -list_options, v4l2 -list_formats)
FFMPEG_NAMES = {"mjpeg": "MJPG", "yuyv422": "YUY2", "nv12": "NV12", "nv21": "NV21", "yuv420p": "I420",
                "uyvy422": "UYVY", "gray": "Y800", "rgb24": "RGB24", "bgr24": "BGR3", "bgr0": "RGB32",
                "h264": "H264", "hevc": "HEVC", "p010le": "P010"}
CLASSES = ("mjpeg", "raw", "other")
TOL_100NS = 3                    # MF fps_num/den and DS intervals round differently (W-FMT's tolerance)
REL_TOL = 0.0015                 # for listings that print fps with few digits (ffmpeg "fps=7.5")

# disturbance thresholds (streaming process, frame arrival intervals)
GAP_FACTOR_P50 = 3.0             # a gap > 3 x the baseline median interval ...
GAP_FACTOR_MAX = 1.5             # ... and > 1.5 x the baseline maximum interval is a disturbance
GAP_MIN_EXTRA_MS = 25.0          # and at least 25 ms above the baseline maximum (jitter floor)


def norm_fourcc(f: Any) -> str:
    s = str(f or "?").strip()
    low = s.lower()
    if low in FFMPEG_NAMES:
        return FFMPEG_NAMES[low]
    u = s.upper()
    return FOURCC_ALIASES.get(u, u)


def fmt_class(fourcc: Any) -> str:
    f = norm_fourcc(fourcc)
    if f == "MJPG":
        return "mjpeg"
    if f in RAW_FOURCCS:
        return "raw"
    return "other"


def interval_from_fps(fps: float | None) -> int:
    return int(round(1e7 / float(fps))) if fps else 0


def fps_of(iv: int) -> float:
    return round(1e7 / iv, 3) if iv else 0.0


def mode_text(m: tuple) -> str:
    f, w, h, iv = m
    return f"{f} {w}x{h}@{fps_of(iv):g}"


def mode_texts(ms: Iterable[tuple]) -> list[str]:
    return [mode_text(m) for m in sorted(ms, key=lambda x: (x[0], -x[1] * x[2], x[3]))]


def _near(a: tuple, b: tuple, abs_tol: int, rel_tol: float) -> bool:
    if a[0] != b[0] or a[1] != b[1] or a[2] != b[2]:
        return False
    tol = max(abs_tol, int(round(rel_tol * max(a[3], b[3]))))
    return abs(int(a[3]) - int(b[3])) <= tol


def match(a: set, b: set, abs_tol: int = TOL_100NS, rel_tol: float = 0.0) -> tuple[set, set]:
    """(in a not in b, in b not in a) with an interval tolerance."""
    a, b = set(a), set(b)
    only_a = {x for x in a if not any(_near(x, y, abs_tol, rel_tol) for y in b)}
    only_b = {y for y in b if not any(_near(x, y, abs_tol, rel_tol) for x in a)}
    return only_a, only_b


def normalize(modes: Iterable[tuple]) -> set:
    out = set()
    for f, w, h, iv in modes:
        try:
            out.add((norm_fourcc(f), int(w), int(h), int(iv)))
        except (TypeError, ValueError):
            continue
    return out


def compare(reference: Iterable[tuple], listed: Iterable[tuple] | None, abs_tol: int = TOL_100NS,
            rel_tol: float = 0.0, max_list: int = 24) -> dict[str, Any]:
    """Completeness of ``listed`` vs ``reference`` (the USB descriptors), per class (mjpeg / raw / other).

    complete = no reference mode missing in the classes the reference has for MJPEG and raw (``other``, e.g.
    H.264, is reported but not required). ``exact`` = complete and no extra mode in MJPEG / raw. ``listed`` None =
    the method returned nothing (complete False)."""
    ref = normalize(reference)
    got = normalize(listed or [])
    per: dict[str, Any] = {}
    for cls in CLASSES:
        r = {m for m in ref if fmt_class(m[0]) == cls}
        g = {m for m in got if fmt_class(m[0]) == cls}
        miss, extra = match(r, g, abs_tol, rel_tol)
        per[cls] = {"n_reference": len(r), "n_listed": len(g), "n_missing": len(miss), "n_extra": len(extra),
                    "complete": not miss, "missing": mode_texts(miss)[:max_list],
                    "extra": mode_texts(extra)[:max_list],
                    "sizes_reference": len({(w, h) for _, w, h, _ in r}),
                    "sizes_listed": len({(w, h) for _, w, h, _ in g}),
                    "sizes_missing": sorted({f"{w}x{h}" for _, w, h, _ in miss})[:max_list],
                    "rates_only_missing": bool(miss) and not ({(w, h) for _, w, h, _ in miss} -
                                                             {(w, h) for _, w, h, _ in g})}
    required = [c for c in ("mjpeg", "raw") if per[c]["n_reference"]]
    complete = listed is not None and bool(ref) and all(per[c]["complete"] for c in required)
    exact = complete and all(per[c]["n_extra"] == 0 for c in required)
    return {"complete": complete, "exact": exact, "required_classes": required, "per_class": per,
            "n_reference": len(ref), "n_listed": len(got), "listed_none": listed is None,
            "formats_reference": sorted({m[0] for m in ref}), "formats_listed": sorted({m[0] for m in got})}


# ------------------------------------------------------------------------------------------------ disturbance
def _intervals_ms(ts_ns: Sequence[int]) -> list[float]:
    return [(b - a) / 1e6 for a, b in zip(ts_ns, ts_ns[1:])]


def disturbance(frame_ts_ns: Sequence[int], window: tuple[int, int], baseline: tuple[int, int] | None = None,
                bad_frame_ts_ns: Sequence[int] = (), stream_error_ns: int | None = None,
                stream_end_ns: int | None = None, nominal_fps: float | None = None) -> dict[str, Any]:
    """Did the other process's stream suffer during ``window`` (t0, t1 in the frames' clock, ns)?

    Uses frame arrival times of the streaming process. An interval counts for the window when it ENDS inside the
    window or spans it (a stall that started inside and ended after it is included up to the next frame). The
    baseline is the window before (default: up to 2 s before t0). disturbed = a gap above the threshold, a bad
    frame in the window, a stream error in the window, or the stream ending inside the window (no frame after
    it although the stream was expected to continue: ``stream_end_ns`` after the window)."""
    ts = sorted(int(t) for t in frame_ts_ns)
    t0, t1 = int(window[0]), int(window[1])
    if baseline is None:
        baseline = (t0 - 2_000_000_000, t0)
    b0, b1 = int(baseline[0]), int(baseline[1])
    base_ts = [t for t in ts if b0 <= t <= b1]
    base_iv = _intervals_ms(base_ts)
    win_iv = []
    for a, b in zip(ts, ts[1:]):
        if (t0 <= b <= t1) or (a <= t1 and b > t1 and a >= t0) or (a < t0 and b > t1):
            win_iv.append((b - a) / 1e6)
    after = [t for t in ts if t > t1]
    in_win = [t for t in ts if t0 <= t <= t1]
    last = ts[-1] if ts else None
    # a stream still expected to run after the window but with no frame after it: stopped inside the window
    stopped = bool(ts) and not after and (stream_end_ns is None or stream_end_ns > t1 + 300_000_000)
    p50 = statistics.median(base_iv) if base_iv else (1000.0 / nominal_fps if nominal_fps else None)
    bmax = max(base_iv) if base_iv else p50
    thr = None
    if p50 is not None:
        thr = max(GAP_FACTOR_P50 * p50, GAP_FACTOR_MAX * (bmax or p50), (bmax or p50) + GAP_MIN_EXTRA_MS)
    wmax = max(win_iv) if win_iv else None
    bad = [t for t in bad_frame_ts_ns if t0 <= int(t) <= t1]
    err_in = stream_error_ns is not None and t0 - 100_000_000 <= int(stream_error_ns) <= t1 + 1_000_000_000
    gap = (wmax is not None and thr is not None and wmax > thr)
    no_frames = not in_win and (t1 - t0) > 3 * 1e6 * (p50 or 50.0)
    disturbed = bool(gap or bad or err_in or stopped or no_frames) if ts else None
    why = [x for x, c in (("gap", gap), ("bad_frames", bool(bad)), ("stream_error", err_in),
                          ("stream_stopped", stopped), ("no_frames_in_window", no_frames)) if c]
    return {"disturbed": disturbed, "why": why, "window_ms": round((t1 - t0) / 1e6, 1),
            "frames_in_window": len(in_win), "frames_after_window": len(after),
            "baseline_frames": len(base_ts), "baseline_p50_interval_ms": None if p50 is None else round(p50, 2),
            "baseline_max_interval_ms": None if bmax is None else round(bmax, 2),
            "window_max_interval_ms": None if wmax is None else round(wmax, 2),
            "gap_threshold_ms": None if thr is None else round(thr, 2), "bad_frames_in_window": len(bad),
            "stream_error_in_window": err_in, "stream_stopped_in_window": stopped,
            "last_frame_after_window_ms": None if last is None else round((last - t1) / 1e6, 1),
            "measured": bool(ts)}


def blocked(control_ok: bool | None, during_ok: bool | None, first_frame_after_release: bool | None = None
            ) -> bool | None:
    """Did the method block a third process's open? None = not testable (the control attempt, made without the
    method, failed too, or nothing was tried). A third-process open that only got its first frame after the method
    released the device counts as blocked (delayed until release)."""
    if control_ok is not True or during_ok is None:
        return None
    if during_ok is False:
        return True
    return bool(first_frame_after_release)


def stream_started(samples: Sequence[dict], baseline_active: bool | None = None) -> bool | None:
    """From pipe / alt samples taken while the method held the device: each sample is {"active": bool | None}
    (an open isochronous pipe, or a non-zero bAlternateSetting on the streaming interface). None when nothing was
    sampled or the camera was already streaming before the method (baseline_active True: not determinable)."""
    vals = [s.get("active") for s in samples if s.get("active") is not None]
    if baseline_active:
        return None
    if not vals:
        return None
    return any(vals)
