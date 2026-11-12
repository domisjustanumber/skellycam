"""W-PYMF-ALL: several cameras streaming from ONE pure-Python Media Foundation process (pymf multi), the way
skellycam's camera process would run the package-1.3 backend (CAPTURE_AND_RECORDING_PLAN.md 3.2: comtypes/ctypes
source reader, native format, converters off, JPEG bytes kept). It covers W-PYMF's documented gaps: one pymf process
streaming all cameras; 60 fps; control sets while streaming; in-use detection.

Every part is ONE ``ctx.camcmd`` running ``pymf multi --spec`` (camlock serialises it; the spec and threading model
are in pymf/multi.py: one camera thread and one async source reader per camera, samples on MF work-queue threads,
every camera call bounded by --timeout-ms, the pymf watchdog and the camcmd timeout as backstops):

| Part | Cameras | Length (quick) | Measured |
| all_720p30 | every camera not gated / dead / faulted, MJPG 720p30 (in-scope default) | 600 s (60 s) | per camera: delivered fps, gaps > 1.5 nominal periods (arrival and MF sample time), frames lost in the MF sample-time slots, arrival jitter (interval percentiles; arrival-minus-sample-time offset off the grid), JPEG integrity (SOI/EOI/SOF size every frame; strict decode of the kept samples), first-frame times, clean stop and time to release; CPU % of the process |
| controls (during all_720p30) | each camera of that part | at 120 s and 300 s (20 s, 40 s) | exposure set through the camera's own IMFMediaSource (IAMCameraControl, IKsControl fallback) from the same process while its reader streams: readback, frames until the ROI luma changes, restore at the end |
| all_720p60 | cameras with an in-scope MJPG 1280x720 mode >= 59 fps (Kiyo Pro, C922) | 180 s (30 s) | as all_720p30 |
| in_use | ONE camera other than the Kiyo Pro, 720p30 | 45 s (30 s) | while pymf streams it, a second process opens the same camera: ``wincam activity`` (opens nothing; does the activity monitor see pymf?), ``wincam capture`` and ``pymf capture`` 1 frame. The error code and class each sees, and whether the first stream was disturbed. NEVER the Kiyo Pro (concurrent access is suspected in its wedges) |

Rules: cameras with ``ctx.camera_gated`` / ``ctx.camera_dead`` / ``ctx.camera_faulted`` are left out before a part
starts. A Kiyo Pro first-sample timeout, stall, unreleasable reader or 0x8007001F: pymf closes its reader at once and
never re-opens it; this module then calls ``ctx.mark_fault`` (Kiyo Pro dead rule) and leaves it out of the later
parts; ``measurements.kiyo_pro_fault`` reports it. A bandwidth refusal (the C922 and the generic 4c4a:4a55 share a
USB 2.0 hub) is a recorded result (``measurements.refusals``; camera rated 'untested (refused)'), never a crash.
Tier 0 only: MF sample time and QPC arrival; no UVC PTS/SCR. Files: per-frame records (pymf/framerec.py, 41 bytes a
frame) and the few kept JPEGs stay in raw_dir; summaries go into the result.

Standalone (opens cameras; camlock): python suite/windows/tests/w_pymf_all.py [--quick]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
import w_pymf as wp  # noqa: E402
from common import jpegcheck, rating, results, tsanalysis as tsa  # noqa: E402
from pymf import framerec as FR  # noqa: E402

TEST = "W-PYMF-ALL"
TIMEOUT_MS = 5000
PART_S = {"all_720p30": 600.0, "all_720p60": 180.0, "in_use": 45.0}
PART_QUICK_S = {"all_720p30": 60.0, "all_720p60": 30.0, "in_use": 30.0}
CTRL_AT_S = (120.0, 300.0)
CTRL_AT_QUICK_S = (20.0, 40.0)
CTRL_CONTROL = "exposure"
CTRL_DELTA = -2                 # steps (exposure: log2 s, so 4x shorter -> darker); the second set goes back
WINDOW = {"pre": 5, "post": 60}
SAMPLES = 4
INTRUDERS_AT_S = (6.0, 14.0, 26.0)
INTRUDERS_AT_QUICK_S = (4.0, 9.0, 16.0)
INTRUDER_TIMEOUT_MS = 4000
STEADY_SKIP_S = 2.0             # start-up seconds left out of the stream statistics (first-frame times cover them)
GAP_FACTOR = 1.5
ROI = (0.1, 0.1, 0.9, 0.9)
FPS60_MIN = 59.0
#: thresholds of the per-camera stream rating (criteria texts say them)
VALID_MIN = 0.99
LOSS_FRAC = 0.001
FPS_MIN_FRAC = 0.98
RELEASE_MAX_MS = 5000.0
NOT_BW = ("device_error", "in_use", "permission", "device_not_ready")
#: estimate only (no camera is queried for the estimate): VID:PID with an MJPG 720p60 mode on Gerald
KNOWN_720P60 = {("1532", "0e05"), ("046d", "085c")}

INFO = {"id": TEST, "module": "tests.w_pymf_all", "goal": "pymf_multi", "opens_cameras": True,
        "tools": ["pymf/cli.py multi (uv, comtypes)", "native/build/wincam.exe (in-use second opener, activity)"],
        "flags": {"--quick": "60 s / 30 s / 30 s parts"},
        "description": "pymf: every camera in one process at 720p30 (10 min) with exposure sets while streaming, "
                       "720p60 cameras together (3 min), in-use detection on one camera other than the Kiyo Pro"}

NOT_COVERED = ("several pymf processes at once (one process only, as skellycam's camera process)",
               "decode to BGR in the capture process: the JPEG bytes are kept and checked (markers, strict decode of "
               "samples), the decode cost of package 1.3 is not in the CPU figure",
               "long runs beyond the 10-minute part")


# ============================================================================================================ knobs
def part_seconds(ctx) -> dict[str, float]:
    base = dict(PART_QUICK_S if ck.quick(ctx) else PART_S)
    v = getattr(getattr(ctx, "args", None), "pymf_all_seconds", None)
    if v:
        base["all_720p30"] = float(v)
    return base


def ctrl_times(ctx, seconds: float) -> list[float]:
    """Control set times inside part 1 that leave >= 10 s of streaming after the last one."""
    return [t for t in (CTRL_AT_QUICK_S if ck.quick(ctx) else CTRL_AT_S) if t + 10.0 <= seconds]


def _dead(ctx, cam) -> dict | None:
    try:
        return getattr(ctx, "camera_dead", lambda c: None)(cam)
    except Exception:  # noqa: BLE001
        return None


def estimate_s(ctx) -> float:
    """Each part: its length + open/close (~25 s) + uv start (~10 s) + analysis; format lists come from the run's
    cache (else ~12 s per camera). Part 2 only when a camera with a known 720p60 mode is attached; part 4 only with a
    camera other than the Kiyo Pro. Full run ~18 min with 4 cameras, quick ~5 min. Opens no camera."""
    sec = part_seconds(ctx)
    cams = [c for c in ctx.cameras if not _dead(ctx, c)]
    n = max(1, len(cams))
    total = 20.0 + 6.0 * n
    total += sec["all_720p30"] + 35.0 + 6.0 * n
    if any((c.get("vid"), c.get("pid")) in KNOWN_720P60 for c in cams):
        total += sec["all_720p60"] + 35.0
    if any(not c.get("is_kiyo") for c in cams):
        total += sec["in_use"] + 45.0
    return total


# ============================================================================================================ stats
def _pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    v = sorted(vals)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))]


def _r(x: float | None, n: int = 3) -> float | None:
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


def _dist_ms(vals_ms: list[float]) -> dict:
    if not vals_ms:
        return {"n": 0}
    m = sum(vals_ms) / len(vals_ms)
    return {"n": len(vals_ms), "mean": _r(m), "std": _r((sum((x - m) ** 2 for x in vals_ms) / len(vals_ms)) ** 0.5),
            "p50": _r(_pct(vals_ms, 0.5)), "p90": _r(_pct(vals_ms, 0.9)), "p99": _r(_pct(vals_ms, 0.99)),
            "p999": _r(_pct(vals_ms, 0.999)), "max": _r(max(vals_ms))}


def gaps(times_ns: list[float], seqs: list[int], period_ns: float, factor: float = GAP_FACTOR, top: int = 5) -> dict:
    """Intervals longer than ``factor`` nominal periods: count, the largest (seq after the gap, gap ms, time s)."""
    out = [(seqs[i], times_ns[i] - times_ns[i - 1]) for i in range(1, len(times_ns))
           if times_ns[i] - times_ns[i - 1] > factor * period_ns]
    out.sort(key=lambda x: -x[1])
    return {"threshold_ms": _r(factor * period_ns / 1e6), "count": len(out),
            "max_ms": _r(out[0][1] / 1e6) if out else None,
            "largest": [{"seq": s, "gap_ms": _r(d / 1e6), "t_s": None} for s, d in out[:top]]}


def drops_from_sample_times(st_ns: list[float], nominal_period_ns: float | None = None) -> dict:
    """Frames lost in the MF sample-time slots (tsanalysis.slot_frames: measured period, gaps only where the
    timestamp grid can tell one period from two, i.e. period > 2 x grid). ``drops`` None when not detectable (60 fps
    on a 16 ms grid). ``frames_short_of_nominal`` is filled by stream_metrics."""
    if len(st_ns) < 10:
        return {"n": len(st_ns), "drops": None, "reason": "fewer than 10 sample times"}
    try:
        sl = tsa.slot_frames(st_ns, nominal_period_ns=nominal_period_ns)   # tells 60 fps on a 16 ms grid from drops
    except ValueError as e:
        return {"n": len(st_ns), "drops": None, "reason": f"sample times do not increase: {e}"}
    det = bool(sl.get("drops_detectable"))
    return {"n": len(st_ns), "grid_ms": sl.get("grid_ms"), "period_ms_measured": _r((sl.get("period_ns") or 0) / 1e6),
            "drops_detectable": det, "slotting": sl.get("slotting"), "gaps_found": sl.get("gaps_found"),
            "drops": (sl["slots"][-1] - (len(st_ns) - 1)) if det else None}


def stream_metrics(rows: list[dict], nominal_fps: float, skip_s: float = STEADY_SKIP_S) -> dict:
    """Per-camera stream statistics from framerec rows (pure). Integrity over every frame; timing over the steady
    part (after ``skip_s`` from the first frame)."""
    n = len(rows)
    out: dict[str, Any] = {"frames": n, "nominal_fps": nominal_fps, "skip_s": skip_s}
    if n == 0:
        return out
    bits = [r.get("bits") or 0 for r in rows]
    size = [r.get("bytes") or 0 for r in rows]
    out["integrity"] = {"soi": sum(1 for b in bits if b & FR.BIT_SOI) / n,
                        "eoi": sum(1 for b in bits if b & FR.BIT_EOI) / n,
                        "size_ok": sum(1 for b in bits if b & FR.BIT_SIZE) / n,
                        "valid": sum(1 for b in bits if (b & (FR.BIT_SOI | FR.BIT_EOI | FR.BIT_SIZE)) ==
                                     (FR.BIT_SOI | FR.BIT_EOI | FR.BIT_SIZE)) / n,
                        "trailing_after_eoi": sum(1 for b in bits if b & FR.BIT_TRAIL),
                        "discontinuities": sum(1 for b in bits if b & FR.BIT_DISC),
                        "bytes_min": min(size), "bytes_p50": _pct(size, 0.5), "bytes_max": max(size)}
    t0 = rows[0]["qpc_ns"]
    span_all = (rows[-1]["qpc_ns"] - t0) / 1e9
    out["fps_delivered"] = _r((n - 1) / span_all) if span_all > 0 else None
    seq_gap = sum(max(0, b["seq"] - a["seq"] - 1) for a, b in zip(rows, rows[1:]))
    out["seq_gaps"] = seq_gap                  # records missing from the file (never expected)
    steady = [r for r in rows if r["qpc_ns"] - t0 >= skip_s * 1e9]
    out["steady_frames"] = len(steady)
    if len(steady) < 10:
        return out
    period = 1e9 / nominal_fps
    arr = [float(r["qpc_ns"]) for r in steady]
    seqs = [r["seq"] for r in steady]
    span = (arr[-1] - arr[0]) / 1e9
    out["fps_steady"] = _r((len(arr) - 1) / span) if span > 0 else None
    out["fps_fit"] = _r(ck.fps_from_rows(steady, skip_frac=0.0))
    iv = [(b - a) / 1e6 for a, b in zip(arr, arr[1:])]
    out["arrival_interval_ms"] = _dist_ms(iv)
    ag = gaps(arr, seqs, period)
    for g in ag["largest"]:
        r = next(x for x in steady if x["seq"] == g["seq"])
        g["t_s"] = _r((r["qpc_ns"] - t0) / 1e9)
    st = [(float(r["qpc_ns"]), float(r["sample_time_100ns"]) * 100.0, r["seq"]) for r in steady
          if r.get("sample_time_100ns") is not None]
    dr = drops_from_sample_times([s for _, s, _ in st], period)
    grid = dr.get("grid_ms")
    grid_limited = bool(grid) and period <= 2.0 * grid * 1e6
    ag["grid_limited"] = grid_limited          # at 60 fps on a 16 ms grid a 32 ms interval is not a gap
    out["arrival_gaps"] = ag
    out["sample_time"] = dr
    if len(st) >= 10:
        sts = [s for _, s, _ in st]
        sg = gaps(sts, [q for _, _, q in st], period)
        sg["grid_limited"] = grid_limited
        out["sample_time_gaps"] = sg
        st_span = (sts[-1] - sts[0]) / 1e9
        dr["frames_short_of_nominal"] = int(round(st_span * nominal_fps)) + 1 - len(sts)
        lat = [(a - s) / 1e6 for a, s, _ in st]
        off = wp.grid_offsets(lat, grid)
        med = _pct(off, 0.5) or 0.0
        dev = [abs(x - med) for x in off]
        om = sum(off) / len(off)
        out["arrival_minus_sample_ms"] = {
            "grid_ms": grid, "p50": _r(_pct(lat, 0.5)), "offset_p50_ms": _r(_pct(dev, 0.5)),
            "offset_p99_ms": _r(_pct(dev, 0.99)), "offset_max_ms": _r(max(dev)),
            "offset_std_ms": _r((sum((x - om) ** 2 for x in off) / len(off)) ** 0.5),
            "note": "arrival (QPC at OnReadSample entry, incl. the GIL wait) minus MF sample time, folded onto the "
                    "sample-time grid (w_pymf.grid_offsets): the delivery delay a busy Python process would add"}
    return out


# ============================================================================================================ controls
def _mean(v: list[float]) -> float | None:
    return sum(v) / len(v) if v else None


def control_effect(rec: dict, luma: dict[int, float], qpc_by_seq: dict[int, int] | None = None) -> dict:
    """Frames until the ROI luma changes after one set (pure). Baseline = mean luma of the kept frames before the set
    started (seq < seq_at_set_start); final = mean of the last 5 kept frames; changed when |final - base| >=
    max(3 levels, 4 x baseline std, 4 % of base); the change frame is the first frame at or after the set start
    whose luma has moved half of that step. Expected direction: brighter for a larger exposure value."""
    out: dict[str, Any] = {"measured": False}
    s0 = rec.get("seq_at_set_start")
    if s0 is None or not luma:
        out["reason"] = "no frames kept around the set" if s0 is not None else "set not issued"
        return out
    pre = [luma[k] for k in sorted(luma) if k < s0]
    post = [(k, luma[k]) for k in sorted(luma) if k >= s0]
    if len(pre) < 2 or len(post) < 6:
        out["reason"] = f"too few kept frames ({len(pre)} before, {len(post)} after)"
        return out
    base = _mean(pre)
    sd = (sum((x - base) ** 2 for x in pre) / len(pre)) ** 0.5
    final = _mean([v for _, v in post[-5:]])
    step = final - base
    floor = max(3.0, 4.0 * sd, 0.04 * base)
    out.update(measured=True, luma_before=_r(base, 2), luma_before_std=_r(sd, 2), luma_after=_r(final, 2),
               luma_step=_r(step, 2), change_floor=_r(floor, 2), changed=abs(step) >= floor,
               frames_kept={"before": len(pre), "after": len(post)})
    bv, sv = (rec.get("before") or {}).get("value"), rec.get("set_value")
    if isinstance(bv, (int, float)) and isinstance(sv, (int, float)) and sv != bv:
        exp = 1 if sv > bv else -1
        out["expected_direction"] = "brighter" if exp > 0 else "darker"
        out["direction_ok"] = (step > 0) == (exp > 0) if out["changed"] else None
    if not out["changed"]:
        return out
    sign = 1.0 if step > 0 else -1.0
    first = next((k for k, v in post if (v - base) * sign >= 0.5 * abs(step)), None)
    if first is not None:
        out["frames_to_change"] = first - s0
        s1 = rec.get("seq_at_set_return")
        out["frames_after_set_returned"] = (first - s1) if isinstance(s1, int) else None
        q = (qpc_by_seq or {}).get(first)
        if q is not None and rec.get("qpc_set_start_ns"):
            out["ms_to_change"] = _r((q - rec["qpc_set_start_ns"]) / 1e6, 1)
    return out


def window_lumas(rec: dict) -> tuple[dict[int, float], dict]:
    """ROI luma of every kept frame of one control window (common.imgmetrics, Pillow + numpy) and a strict decode of
    its first and last frame (common.jpegcheck)."""
    d = Path(((rec.get("window") or {}).get("dir")) or "")
    out: dict[int, float] = {}
    info: dict[str, Any] = {"dir": str(d)}
    if not d.is_dir():
        info["reason"] = "window folder missing"
        return out, info
    try:
        from common import imgmetrics as im  # noqa: PLC0415 - Pillow + numpy
    except Exception as e:  # noqa: BLE001
        info["reason"] = f"imgmetrics unavailable: {e!r}"
        return out, info
    files = sorted(d.glob("f*.jpg"))
    for f in files:
        try:
            out[int(f.stem[1:])] = im.luma_mean(f.read_bytes(), roi=ROI)
        except Exception:  # noqa: BLE001 - a broken JPEG is counted, not fatal
            info["undecodable"] = info.get("undecodable", 0) + 1
    chk = [jpegcheck.check_jpeg(files[i].read_bytes()) for i in sorted({0, len(files) - 1}) if files]
    info["strict_ok"] = [c.get("strict_ok") for c in chk]
    info["kept"] = len(files)
    return out, info


def rate_control(cam_key: str, recs: list[dict], restore: list[dict], skipped: str | None) -> dict:
    """pymf_streaming_set|<camera>|exposure from the part-1 set records (with ``effect``)."""
    sets = [r for r in recs if r.get("control")]
    if not sets:
        return rating.untested("no control set scheduled (part 1 did not stream this camera long enough)")
    if all(r.get("supported") is False for r in sets):
        return {**rating.untested(f"{CTRL_CONTROL} not supported through the MF source: "
                                  f"{sets[0].get('reason') or 'no manual value'}"), "summary_label": "untested (unsupported)"}
    crit = []

    def add(t, met, d=None):
        crit.append({"criterion": t, "met": met, "detail": d})
    add("every set returned within --timeout-ms while the reader streamed", not any(r.get("timed_out") for r in sets),
        [r.get("call_ms") for r in sets])
    add("readback equals the value set, manual mode", all(bool(r.get("matches")) for r in sets),
        [{"set": r.get("set_value"), "readback": (r.get("after") or {}).get("value"), "hr": r.get("hr_set_name")}
         for r in sets])
    eff = [r.get("effect") or {} for r in sets]
    measured = [e for e in eff if e.get("measured")]
    add("ROI luma moved in the expected direction after each set",
        None if not measured else all(e.get("changed") and e.get("direction_ok") is not False for e in measured),
        [{k: e.get(k) for k in ("luma_before", "luma_after", "frames_to_change", "ms_to_change", "direction_ok")}
         for e in eff])
    add("controls restored to their first-read value and mode, read back",
        None if skipped else (all(r.get("ok") for r in restore) if restore else None),
        skipped or [{k: r.get(k) for k in ("control", "restore_value", "readback_value", "restore_flags",
                                            "readback_flags")} for r in restore])
    failed = [c["criterion"] for c in crit if c["met"] is False]
    if crit[0]["met"] is False or crit[1]["met"] is False:
        rr = "no"
    elif failed:
        rr = "partial"
    elif any(c["met"] is None for c in crit):
        rr = "partial"
    else:
        rr = "yes"
    ftc = [e.get("frames_to_change") for e in measured if e.get("frames_to_change") is not None]
    return {"rating": rr, "criteria": crit, "evidence": {"frames_to_change": ftc, "camera": cam_key},
            "summary_label": rr if rr != "partial" else
            f"partial ({'; '.join(failed) if failed else 'effect or restore not measured'})"}


# ============================================================================================================ failures
def classify_camera_failure(crec: dict, others_streaming_same_hub: bool) -> dict:
    """Fault kind (framerec.fault_kind) plus the suite's failure class (topology_model via capkit.classify) and
    whether it counts as a bandwidth refusal (W-MULTI's rule: a bandwidth class, or any non-device class while
    another camera of the same hub streams)."""
    err = crec.get("error") or {}
    kind = crec.get("fault_kind") or FR.fault_kind(err, bool(crec.get("unreleasable")))
    if not err and not kind:
        return {"failed": False}
    code, stage, _ = ck.failure_code("mf", {"error": err}, None)
    frames = (crec.get("frames") or {}).get("total")
    cls = ck.classify("mf", code, stage, frames=frames, timed_out=err.get("class") == "timeout",
                      other_streaming_in_domain=others_streaming_same_hub)
    c = str(cls.get("class"))
    refusal = kind not in FR.DEVICE_FAULT_KINDS and not crec.get("kiyo_pro_fault") and (
        c.startswith("bandwidth") or (others_streaming_same_hub and c not in NOT_BW))
    return {"failed": True, "fault_kind": kind, "code": code, "stage": stage, "class": c,
            "reason": cls.get("reason"), "refusal": bool(refusal),
            "others_streaming_same_hub": others_streaming_same_hub}


def rate_stream(pa: dict) -> dict:
    """pymf_multi|<camera>|<part> from one camera's part analysis (pure)."""
    if pa.get("excluded"):
        return {**rating.untested(f"left out: {pa['excluded']}"),
                "summary_label": "untested (scope)" if pa.get("scope") else "untested (excluded)"}
    if not pa.get("ran"):
        return rating.untested(pa.get("untested_reason") or "part did not run")
    fl = pa.get("failure") or {}
    if pa.get("kiyo_pro_fault") or fl.get("fault_kind") in FR.DEVICE_FAULT_KINDS:
        r = rating.untested(f"device fault ({fl.get('fault_kind')}, {fl.get('code')} at {fl.get('stage')}): the "
                            "session closed this reader and never re-opened it (a device fault is not an API result)")
        return {**r, "summary_label": "untested (device fault)", "evidence": {"failure": fl}}
    if fl.get("refusal"):
        r = rating.untested(f"bandwidth refusal ({fl.get('class')}, {fl.get('code')} at {fl.get('stage')}) while a "
                            "same-hub camera streamed: a topology result, recorded in refusals")
        return {**r, "summary_label": "untested (refused)", "evidence": {"failure": fl}}
    m = pa.get("metrics") or {}
    crit = []

    def add(t, met, d=None):
        crit.append({"criterion": t, "met": met, "detail": d})
    add("streamed the whole part and stopped on request (no error, stall or end of stream)",
        bool(pa.get("ok") and pa.get("closed_by") == "stop"), {"closed_by": pa.get("closed_by"), "error": pa.get("error")})
    rel = pa.get("stop_to_released_ms")
    add(f"released at the stop within {RELEASE_MAX_MS / 1000:g} s (stop reads, Flush, reader release, source "
        "shutdown; all bounded)", (not pa.get("unreleasable")) and isinstance(rel, (int, float)) and rel <= RELEASE_MAX_MS,
        {"stop_to_released_ms": rel, "close_ms": pa.get("close_ms")})
    integ = m.get("integrity") or {}
    smp = pa.get("samples") or {}
    strict = smp.get("strict_ok")
    add(f"valid JPEG (SOI, EOI, SOF size) >= {VALID_MIN:.0%} of frames, kept samples decode strictly",
        None if not integ else (integ.get("valid", 0) >= VALID_MIN and strict is not False),
        {"valid": _r(integ.get("valid"), 5), "samples_strict_ok": strict, "samples": smp.get("n")})
    dr = m.get("sample_time") or {}
    n = m.get("steady_frames") or 0
    lim = max(1, int(LOSS_FRAC * n))
    add(f"frames lost in the MF sample-time slots <= max(1, {LOSS_FRAC:.1%} of frames)",
        None if dr.get("drops") is None else dr["drops"] <= lim,
        {"drops": dr.get("drops"), "detectable": dr.get("drops_detectable"), "limit": lim,
         "frames_short_of_nominal": dr.get("frames_short_of_nominal")})
    ag = m.get("arrival_gaps") or {}
    add(f"arrival gaps > {GAP_FACTOR:g} nominal periods <= max(1, {LOSS_FRAC:.1%} of frames) (not rated where the "
        "16 ms host grid makes such intervals normal, i.e. 60 fps)",
        None if (not ag or ag.get("grid_limited")) else ag.get("count", 0) <= lim,
        {"count": ag.get("count"), "max_ms": ag.get("max_ms"), "grid_limited": ag.get("grid_limited")})
    fps, nom = m.get("fps_fit") or m.get("fps_steady"), m.get("nominal_fps")
    fps_ok = None
    if isinstance(fps, (int, float)) and nom:
        fps_ok = fps >= FPS_MIN_FRAC * nom
        if not fps_ok and dr.get("drops") == 0 and not (ag.get("count") and not ag.get("grid_limited")):
            fps_ok = None                       # an even, lower rate: the camera's own rate, not frames lost by pymf
    add(f"delivered fps >= {FPS_MIN_FRAC:.0%} of nominal (an even lower rate with no lost slot = the camera's rate, "
        "not rated; W-MJPEG rates it)", fps_ok, {"fps_fit": fps, "nominal": nom})
    failed = [c["criterion"] for c in crit if c["met"] is False]
    if crit[0]["met"] is False or crit[1]["met"] is False:
        rr = "no"
    elif failed:
        rr = "partial"
    else:
        rr = "yes"
    return {"rating": rr, "criteria": crit,
            "evidence": {"fps_fit": fps, "drops": dr.get("drops"), "gaps": ag.get("count"),
                         "first_frame_ms": pa.get("first_frame_ms"), "cpu_pct_of_one_core_process":
                         pa.get("cpu_pct_of_one_core_process")},
            "summary_label": rr if rr != "partial" else f"partial ({len(failed)} criteria)"}


# ============================================================================================================ in use
def _intr_kind(label: str) -> str:
    return "activity" if "activity" in str(label) else "opener"


def analyse_in_use(doc: dict, rows: list[dict], target_label: str, nominal_fps: float,
                   target_symlink: str | None) -> dict:
    """The in-use part (pure): what each second opener saw, whether the activity monitor saw pymf, and whether the
    first stream was disturbed in each opener's window (window = its run + 2 s; disturbed = a gap > max(2.5 periods,
    1.5 x the baseline's largest gap), or a rate < 90 % of the baseline's, or the first stream failing)."""
    period = 1e9 / nominal_fps
    sess = doc.get("session") or {}
    t_all = sess.get("t_all_qpc_ns") or (rows[0]["qpc_ns"] if rows else 0)
    intr = [i for i in doc.get("intruders") or [] if i.get("label")]
    crec = next((c for c in doc.get("cameras") or [] if c.get("label") == target_label), {})
    qs = [i["qpc_start_ns"] for i in intr if i.get("qpc_start_ns")]
    first_q = min(qs) if qs else None
    arr = [(r["qpc_ns"], r["seq"]) for r in rows]

    def win(a, b):
        w = [q for q, _ in arr if a <= q <= b]
        mg = max([(y - x) for x, y in zip(w, w[1:])] or [0]) / 1e6
        fps = (len(w) - 1) / ((w[-1] - w[0]) / 1e9) if len(w) > 2 and w[-1] > w[0] else None
        return {"frames": len(w), "max_gap_ms": _r(mg), "fps": _r(fps)}
    base = win(t_all + 2e9, first_q) if first_q else win(t_all + 2e9, t_all + 1e15)
    out: dict[str, Any] = {"target": target_label, "baseline": base, "first_stream": {
        k: crec.get(k) for k in ("ok", "closed_by", "fault_kind", "unreleasable")}, "openers": []}
    out["first_stream"]["error_class"] = (crec.get("error") or {}).get("class")
    gap_lim = max(2.5 * period / 1e6, 1.5 * (base.get("max_gap_ms") or 0))
    want = ck.norm_link(target_symlink) if target_symlink else None
    for i in intr:
        rec: dict[str, Any] = {"label": i.get("label"), "kind": _intr_kind(i.get("label")),
                               "start_after_t_all_s": i.get("start_after_t_all_s"), "elapsed_s": i.get("elapsed_s"),
                               "rc": i.get("rc"), "timed_out": i.get("timed_out")}
        if i.get("skipped"):
            rec["outcome"] = "skipped"
            rec["reason"] = i["skipped"]
            out["openers"].append(rec)
            continue
        j = i.get("stdout_json") if isinstance(i.get("stdout_json"), dict) else None
        if rec["kind"] == "activity":
            dev = None
            for d in (j or {}).get("devices") or []:
                mk = d.get("match_key") or ck.norm_link(d.get("symlink"))
                if want and mk == want:
                    dev = d
            procs = (dev or {}).get("processes") or []
            rec.update(outcome="no result" if j is None else ("listed" if dev else "camera not listed"),
                       in_use=(dev or {}).get("in_use"), streaming=(dev or {}).get("streaming"),
                       sees_pymf=any(p.get("pid") == doc.get("pid") for p in procs) if dev else None,
                       processes=[{k: p.get(k) for k in ("pid", "name", "streaming")} for p in procs][:8])
        else:
            err = (j or {}).get("error") if isinstance((j or {}).get("error"), dict) else None
            frames = ((j or {}).get("frames") or {}).get("total") if isinstance((j or {}).get("frames"), dict) else None
            if i.get("timed_out"):
                outcome = "hung (killed at its timeout)"
            elif j is None:
                outcome = "no result"
            elif j.get("ok") and (frames or 0) >= 1:
                outcome = "opened (shared access)"
            elif err:
                outcome = f"refused ({err.get('class') or 'other'})"
            else:
                outcome = "failed (no error detail)"
            rec.update(outcome=outcome, frames=frames,
                       opener_error={k: (err or {}).get(k) for k in ("stage", "hr", "hr_name", "class", "reason",
                                                                     "message")} if err else None)
        q0, q1 = i.get("qpc_start_ns"), i.get("qpc_end_ns")
        if q0 and q1:
            w = win(q0, q1 + 2e9)
            w["disturbed"] = bool((w["max_gap_ms"] or 0) > gap_lim or
                                  (base.get("fps") and w.get("fps") and w["fps"] < 0.9 * base["fps"]))
            rec["first_stream_window"] = w
        out["openers"].append(rec)
    out["gap_limit_ms"] = _r(gap_lim)
    out["first_stream_disturbed"] = any((o.get("first_stream_window") or {}).get("disturbed") for o in out["openers"])
    return out


def rate_in_use(iu: dict) -> dict:
    if iu.get("untested_reason"):
        return rating.untested(iu["untested_reason"])
    ops = [o for o in iu.get("openers") or [] if o.get("kind") == "opener"]
    act = [o for o in iu.get("openers") or [] if o.get("kind") == "activity"]
    fs = iu.get("first_stream") or {}
    crit = []

    def add(t, met, d=None):
        crit.append({"criterion": t, "met": met, "detail": d})
    add("each second opener (wincam, pymf) returned a classified result within its timeout",
        None if not ops else all(o.get("outcome", "").startswith(("refused", "opened")) for o in ops),
        [{k: o.get(k) for k in ("label", "outcome", "opener_error")} for o in ops])
    add("the pymf stream streamed through to the stop", bool(fs.get("ok") and fs.get("closed_by") == "stop"), fs)
    add("the pymf stream was not disturbed during any opener's window (gaps, rate)",
        None if not any(o.get("first_stream_window") for o in iu.get("openers") or []) else
        not iu.get("first_stream_disturbed"), {"gap_limit_ms": iu.get("gap_limit_ms"), "baseline": iu.get("baseline")})
    add("IMFSensorActivityMonitor (wincam activity) lists the camera in use by the pymf process (information)", None,
        [{k: o.get(k) for k in ("outcome", "in_use", "sees_pymf")} for o in act])
    failed = [c["criterion"] for c in crit if c["met"] is False]
    if crit[1]["met"] is False or any(o.get("outcome", "").startswith("hung") for o in ops):
        rr = "no"
    elif failed:
        rr = "partial"
    elif crit[0]["met"] is None:
        rr = "partial"
    else:
        rr = "yes"
    return {"rating": rr, "criteria": crit, "evidence": {"outcomes": [o.get("outcome") for o in ops]},
            "summary_label": rr if rr != "partial" else f"partial ({'; '.join(failed) or 'openers not run'})"}


# ============================================================================================================ session
def _summary_doc(r: dict, od: Path) -> dict | None:
    return wp._summary_file(od, ck.parse_json(r))


def run_session(ctx, part: str, entries: list[dict], seconds: float, rdir: Path, tdir: Path,
                intruders: list[dict] | None = None) -> dict:
    """ONE camcmd: pymf multi with this part's spec. ``entries``: [{cam, mode, controls}]."""
    od = rdir / part
    spec = {"seconds": seconds, "tail_s": 3.0, "intruders": intruders or [],
            "cameras": [{"label": ck.cam_slug(e["cam"]), "device": e["cam"]["mf_symlink"], "width": e["mode"].w,
                         "height": e["mode"].h, "fps": float(e["mode"].fps_arg), "subtype": "MJPG",
                         "is_kiyo": bool(e["cam"].get("is_kiyo")), "samples": SAMPLES, "window": WINDOW,
                         "controls": e.get("controls") or [], "restore": True} for e in entries]}
    spec_path = tdir / f"{part}_spec.json"
    results.write_json(spec_path, spec)
    wd_ms = FR.watchdog_ms(spec, TIMEOUT_MS)
    argv = wp.pymf_argv(ctx, "multi", "--spec", spec_path, "--timeout-ms", TIMEOUT_MS, "--out-dir", od,
                        "--watchdog-ms", int(wd_ms))
    ctx.log(f"{TEST}: {part}: {len(entries)} camera(s) for {seconds:g} s in one pymf process")
    r = ctx.camcmd(argv, timeout_s=wd_ms / 1000.0 + wp.UV_SLACK_S + 30.0)
    return {"doc": _summary_doc(r, od), "run": ck.run_brief(r), "dry_run": bool(r.get("dry_run")), "out_dir": od, "spec": spec,
            "spec_file": str(spec_path), "watchdog_ms": wd_ms, "timed_out": bool(r.get("timed_out")),
            "dry_run": bool(r.get("dry_run"))}


def sample_checks(crec: dict) -> dict:
    d = Path(((crec.get("files") or {}).get("samples_dir")) or "")
    files = sorted(d.glob("f*.jpg")) if d.is_dir() else []
    chk = [jpegcheck.check_jpeg(f.read_bytes()) for f in files]
    vals = [c.get("strict_ok") for c in chk if c.get("strict_ok") is not None]
    return {"n": len(files), "dir": str(d), "strict_ok": (all(vals) if vals else None),
            "strict_errors": [c.get("strict_error") for c in chk if c.get("strict_ok") is False][:3],
            "sof": sorted({f"{c.get('sof0_w')}x{c.get('sof0_h')}" for c in chk}),
            "header_sha1": sorted({c.get("header_sha1") for c in chk if c.get("header_sha1")})[:3]}


def analyse_part(sess: dict, cams_by_label: dict[str, dict], nominal: dict[str, float]) -> dict:
    """Per camera analysis of one part's pymf output (pure apart from reading its raw files)."""
    doc = sess.get("doc") or {}
    out: dict[str, Any] = {}
    recs = doc.get("cameras") or []
    streaming = {c["label"] for c in recs if c.get("open_ok") and (c.get("frames") or {}).get("total")}
    n_stream = max(1, len(streaming))
    cpu = (doc.get("cpu") or {}).get("pct_of_one_core")
    for crec in recs:
        lab = crec.get("label")
        cam = cams_by_label.get(lab) or {}
        hub = cam.get("parent_instance_id")
        mates = [ol for ol in streaming if ol != lab and hub and (cams_by_label.get(ol) or {}).get("parent_instance_id") == hub]
        rows = FR.read_file((crec.get("files") or {}).get("frames_bin") or "")
        t = crec.get("timings") or {}
        pa = {"ran": True, "label": lab, "mode": crec.get("mode"), "ok": crec.get("ok"), "closed_by": crec.get("closed_by"),
              "error": crec.get("error"), "fault_kind": crec.get("fault_kind"), "unreleasable": crec.get("unreleasable"),
              "kiyo_pro_fault": crec.get("kiyo_pro_fault"), "negotiated": crec.get("negotiated"),
              "first_frame_ms": t.get("first_frame_ms"), "open_to_first_frame_ms": t.get("open_to_first_frame_ms"),
              "first_sample_after_session_start_ms": t.get("first_sample_after_session_start_ms"),
              "stop_to_released_ms": t.get("stop_to_released_ms"), "close_ms": t.get("close_ms"),
              "timings": t, "frames": crec.get("frames"), "callback_s": crec.get("callback_s"),
              "cpu_pct_of_one_core_process": cpu, "cpu_pct_per_streaming_camera": _r(cpu / n_stream, 2) if cpu else None,
              "same_hub_streaming": sorted(mates), "steps": crec.get("steps"),
              "metrics": stream_metrics(rows, nominal.get(lab) or (crec.get("requested") or {}).get("fps") or 30.0)}
        pa["samples"] = sample_checks(crec)
        fl = classify_camera_failure(crec, bool(mates))
        pa["failure"] = fl if fl.get("failed") else None
        out[lab] = pa
    return out


def part_summary(sess: dict, excluded: dict) -> dict:
    doc = sess.get("doc") or {}
    return {"ran": bool(sess.get("doc")), "cameras": [c.get("label") for c in doc.get("cameras") or []],
            "excluded": excluded, "run": sess.get("run"), "exit_code": doc.get("exit_code"), "error_top": doc.get("error"),
            "watchdog_fired": doc.get("watchdog_fired"), "partial": doc.get("partial"),
            "cpu": doc.get("cpu"), "session": doc.get("session"), "release": doc.get("release"),
            "writer": doc.get("writer"), "kiyo_pro_fault": doc.get("kiyo_pro_fault"), "spec_file": sess.get("spec_file"),
            "raw_dir": str(sess.get("out_dir")), "watchdog_ms": sess.get("watchdog_ms"),
            "abandoned_threads": doc.get("abandoned_threads")}


# ============================================================================================================ faults
def session_suspects(sess: dict, labels: list[str]) -> tuple[list[str], str]:
    """Which cameras a session that ended without its final JSON (watchdog / killed) leaves under suspicion: from the
    watchdog's partial per-camera progress (stage not closed and progress older than the timeout, or no record);
    all session cameras when there is no partial record at all."""
    doc = sess.get("doc") or {}
    if doc.get("cameras") and not doc.get("watchdog_fired"):
        return [], "final JSON present"
    part = ((doc.get("partial") or {}).get("cameras")) if isinstance(doc.get("partial"), dict) else None
    if not part:
        return list(labels), "no per-camera progress record (process killed or watchdog without progress)"
    sus = []
    for lab in labels:
        p = part.get(lab)
        if p is None or (p.get("stage") not in ("closed",) and (p.get("progress_age_ms") or 0) > TIMEOUT_MS):
            sus.append(lab)
    return sus, "watchdog partial progress"


def handle_faults(ctx, part: str, sess: dict, cams_by_label: dict[str, dict], modes: dict[str, str],
                  state: dict) -> None:
    """After a session: a Kiyo Pro fault -> ctx.mark_fault (dead rule) and out of the later parts; another camera's
    device fault (0x8007001F, unreleasable) -> capkit.mark_device_fault. A session without its final JSON: the
    suspects (session_suspects) are treated the same way for the Kiyo Pro; for other cameras the hang is marked only
    when the progress record names them."""
    doc = sess.get("doc") or {}
    events = []
    for crec in doc.get("cameras") or []:
        cam = cams_by_label.get(crec.get("label"))
        if cam is None:
            continue
        kind = crec.get("fault_kind")
        err = crec.get("error") or {}
        if cam.get("is_kiyo") and (crec.get("kiyo_pro_fault") or FR.is_kiyo_fault(kind)):
            events.append((cam, kind, err.get("hr") or "timeout", err.get("stage"), "kiyo_pro_fault"))
        elif kind in FR.DEVICE_FAULT_KINDS:
            events.append((cam, kind, err.get("hr") or "timeout", err.get("stage"), "device_fault"))
    ran = not getattr(ctx, "dry_run", False) and not sess.get("dry_run")
    if ran and (not doc.get("cameras") or doc.get("watchdog_fired")):
        labels = [c["label"] for c in sess["spec"]["cameras"]]
        sus, why = session_suspects(sess, labels)
        state.setdefault("session_hangs", []).append({"part": part, "suspects": sus, "basis": why,
                                                      "run": sess.get("run")})
        named = why == "watchdog partial progress"
        for lab in sus:
            cam = cams_by_label.get(lab)
            if cam is None:
                continue
            if cam.get("is_kiyo"):
                events.append((cam, "hung_process", "timeout", "session", "kiyo_pro_fault" if named else "kiyo_suspect"))
            elif named:
                events.append((cam, "hung_process", "timeout", "session", "device_fault"))
    for cam, kind, code, stage, what in events:
        key = cam["key"]
        state.setdefault("faulted", set()).add(key)
        rec = {"key": key, "name": cam.get("name"), "part": part, "kind": kind, "code": code, "stage": stage,
               "mode": modes.get(ck.cam_slug(cam)), "utc": results.utc_now_iso(), "marked": False}
        if what == "kiyo_suspect":
            # integrated 2026-11-11: a session killed without progress while the Kiyo Pro was in it is treated as a
            # Kiyo Pro fault (the suite counts a killed streaming command as a fault). If it really wedged, opening it
            # again would break the dead rule, so it is marked dead: conservative, and recorded as "suspected".
            rec["note"] = ("the session ended without per-camera progress while the Kiyo Pro was in it: treated as a "
                           "Kiyo Pro fault and marked (dead rule, conservative); suspected, not proven")
            rec["suspected"] = True
            ctx.log(f"{TEST}: {part}: session hung with the Kiyo Pro in it (no progress record): marking the Kiyo Pro "
                    "dead (conservative)")
            what = "kiyo_pro_fault"
        fn = getattr(ctx, "mark_fault", None)
        if what == "kiyo_pro_fault":
            if callable(fn):
                try:
                    fn(key, test=TEST, mode=rec["mode"], code=code, api="pymf", stage=stage, cls=kind, source=TEST,
                       detail={"part": part, "rule": "pymf multi closed the Kiyo Pro reader at the fault and never "
                                                     "re-opened it"})
                    rec["marked"] = True
                except Exception as e:  # noqa: BLE001
                    rec["mark_error"] = repr(e)
            state.setdefault("kiyo_pro_fault", rec)
            ctx.log(f"{TEST}: {part}: KIYO PRO FAULT ({kind}, {code} at {stage}); reader closed, never re-opened"
                    + ("; ctx.mark_fault called" if rec["marked"] else "; ctx.mark_fault NOT available"))
        else:
            try:
                ck.mark_device_fault(ctx, cam, TEST, rec["mode"], "pymf",
                                     {"kind": kind, "code": code, "stage": stage,
                                      "reason": f"pymf multi {part}: {kind} at {stage}"})
                rec["marked"] = True
            except Exception as e:  # noqa: BLE001
                rec["mark_error"] = repr(e)
        state.setdefault("faults_marked", []).append(rec)


def excluded_reason(ctx, cam: dict, state: dict) -> str | None:
    """Why a camera is left out of the next part (checked right before each part starts)."""
    try:
        g = ctx.camera_gated(cam)
    except Exception:  # noqa: BLE001
        g = None
    if g:
        return f"gated by the device-fault gate (since {g.get('since_utc')}, {g.get('code') or g.get('class')})"
    d = _dead(ctx, cam)
    if d:
        return f"dead (Kiyo Pro dead rule, since {d.get('since_utc')})"
    try:
        f = getattr(ctx, "camera_faulted", lambda c: None)(cam.get("key"))
    except Exception:  # noqa: BLE001
        f = None
    if f or cam.get("key") in state.get("faulted", set()):
        return "faulted earlier in this test"
    if not cam.get("mf_symlink"):
        return "no MF symbolic link"
    return None


# ============================================================================================================ modes
def mode_60(ctx, fm: dict | None, m30) -> Any:
    """The in-scope MJPG mode at the default's size (1280x720) with >= FPS60_MIN fps, else None."""
    if m30 is None:
        return None
    c = [m for m in ck.mjpeg_modes(fm) if (m.w, m.h) == (m30.w, m30.h) and m.fps >= FPS60_MIN and wp._in_scope(ctx, m)]
    return max(c, key=lambda m: m.fps) if c else None


def select_modes(ctx, cams: list[dict]) -> dict:
    cache: dict = {}
    sel = {}
    for cam in cams:
        fm, frun = ck.get_formats(ctx, cam, cache)
        m30, rec = wp.choose_mode(ctx, fm)
        m60 = mode_60(ctx, fm, m30)
        sel[cam["key"]] = {"m30": m30, "m60": m60, "scope": rec, "formats_run": frun,
                           "formats_ok": fm is not None}
    return sel


# ============================================================================================================ verdicts
def verdicts_from(m: dict) -> dict:
    v: dict[str, Any] = {}
    per: list[dict] = []
    for key, cm in (m.get("cameras") or {}).items():
        for part, tag in (("all_720p30", "720p30"), ("all_720p60", "720p60")):
            pa = cm.get(part)
            if pa is None:
                continue
            r = rate_stream(pa)
            v[f"pymf_multi|{key}|{tag}"] = r
            per.append(r)
        if cm.get("controls") is not None:
            v[f"pymf_streaming_set|{key}|{CTRL_CONTROL}"] = rate_control(key, cm["controls"], cm.get("restore") or [],
                                                                         cm.get("restore_skipped"))
        if cm.get("in_use") is not None:
            v[f"pymf_in_use|{key}"] = rate_in_use(cm["in_use"])
    tested = [r for r in per if r.get("rating") in ("yes", "partial", "no")]
    if not tested:
        v["pymf_multi"] = rating.untested("no camera streamed in a pymf multi session")
    else:
        w = rating.worst(tested)
        p1 = (m.get("parts") or {}).get("all_720p30") or {}
        refused = [x.get("camera") for x in m.get("refusals") or []]
        lab = w
        if w == "yes" and (refused or m.get("kiyo_pro_fault")):
            w, lab = "partial", "partial (" + ", ".join(filter(None, [
                f"refused: {', '.join(map(str, refused))}" if refused else None,
                "Kiyo Pro faulted" if m.get("kiyo_pro_fault") else None])) + ")"
        v["pymf_multi"] = {"rating": w, "criteria": [{"criterion": k, "met": None if x.get("rating") == "untested"
                                                      else x.get("rating") == "yes",
                                                      "detail": x.get("summary_label") or x.get("rating")}
                                                     for k, x in v.items() if k.startswith("pymf_multi|")],
                           "evidence": {"cpu_pct_of_one_core_720p30": (p1.get("cpu") or {}).get("pct_of_one_core"),
                                        "refusals": m.get("refusals"), "kiyo_pro_fault": m.get("kiyo_pro_fault"),
                                        "not_covered": NOT_COVERED,
                                        "question": "can ONE pure-Python MF process stream every camera (skellycam's "
                                                    "camera process, package 1.3)?"},
                           "summary_label": lab}
    return v


# ============================================================================================================ run
def _nominal(entries: list[dict]) -> dict[str, float]:
    return {ck.cam_slug(e["cam"]): float(e["mode"].fps) for e in entries}


def _merge_part(m: dict, part: str, analysis: dict, cams_by_label: dict, entries: list[dict] | None = None,
                sess: dict | None = None) -> None:
    for e in entries or []:                    # a camera of the spec without a per-camera result (session hung)
        lab = ck.cam_slug(e["cam"])
        if lab not in analysis:
            why = ("plan mode: not executed" if (sess or {}).get("dry_run") else
                   f"the {part} session produced no per-camera result (watchdog / killed; see parts.{part})")
            m["cameras"].setdefault(e["cam"]["key"], {"name": e["cam"].get("name"),
                                                      "is_kiyo": e["cam"].get("is_kiyo")})[part] =                 {"ran": False, "untested_reason": why}
    for lab, pa in analysis.items():
        cam = cams_by_label.get(lab)
        if cam is None:
            continue
        cm = m["cameras"].setdefault(cam["key"], {"name": cam.get("name"), "is_kiyo": cam.get("is_kiyo")})
        cm[part] = pa
        fl = pa.get("failure") or {}
        if fl.get("refusal"):
            m["refusals"].append({"part": part, "camera": cam["key"], "name": cam.get("name"), **fl})


def run(ctx) -> dict:
    res = ck.new_result(ctx, TEST)
    sec = part_seconds(ctx)
    m: dict[str, Any] = {"info": INFO, "parts_seconds": sec, "timeout_ms": TIMEOUT_MS, "pymf_cli": str(wp.PYMF_CLI),
                         "frames_format": {"struct": FR.REC.format, "size": FR.REC.size, "fields": list(FR.FIELDS),
                                           "bits": FR.BITS},
                         "selection": {}, "parts": {}, "cameras": {}, "refusals": [], "kiyo_pro_fault": None,
                         "faults_marked": [], "not_covered": NOT_COVERED}
    errors: list = []
    state: dict[str, Any] = {"faulted": set()}
    tdir = ctx.test_dir(TEST)
    rdir = ctx.raw_test_dir(TEST)
    before = ck.arrivals_before(ctx)
    cams_by_label = {ck.cam_slug(c): c for c in ctx.cameras}
    cams_by_key = {c["key"]: c for c in ctx.cameras}
    try:
        if not wp.PYMF_CLI.exists():
            raise FileNotFoundError(f"pymf CLI missing at {wp.PYMF_CLI}")
        warm = ctx.run(wp.pymf_argv(ctx, "--version"), 180)        # resolves the uv environment; opens no camera
        m["pymf_version"] = (warm.get("stdout") or "").strip() or None
        m["pymf_warmup"] = ck.run_brief(warm)
        pre_excl = {c["key"]: excluded_reason(ctx, c, state) for c in ctx.cameras}
        sel = select_modes(ctx, [c for c in ctx.cameras if not pre_excl[c["key"]]])
        for c in ctx.cameras:
            s = sel.get(c["key"]) or {}
            m["selection"][c["key"]] = {"name": c.get("name"), "is_kiyo": c.get("is_kiyo"),
                                        "excluded_at_start": pre_excl[c["key"]],
                                        "mode_720p30": s["m30"].text if s.get("m30") else None,
                                        "mode_720p60": s["m60"].text if s.get("m60") else None,
                                        "mode_scope": s.get("scope"), "formats_ok": s.get("formats_ok"),
                                        "formats_run": s.get("formats_run")}
        modes_txt = {ck.cam_slug(c): (sel.get(c["key"]) or {}).get("m30").text
                     for c in ctx.cameras if (sel.get(c["key"]) or {}).get("m30")}

        def eligible(want: str) -> tuple[list[dict], dict]:
            ent, excl = [], {}
            for c in ctx.cameras:
                why = excluded_reason(ctx, c, state)
                md = (sel.get(c["key"]) or {}).get(want)
                if why is None and c["key"] in sel and not sel[c["key"]].get("formats_ok"):
                    why = "format list unavailable (wincam formats failed; see selection.formats_run)"
                if why is None and md is None:
                    why = ("no in-scope MJPG 720-line mode" if want == "m30" else
                           f"no MJPG {FPS60_MIN:g}+ fps mode at the default size")
                if why:
                    excl[c["key"]] = why
                else:
                    ent.append({"cam": c, "mode": md})
            return ent, excl

        # ---- part 1 (+ part 3: controls while streaming)
        ent, excl = eligible("m30")
        ct = ctrl_times(ctx, sec["all_720p30"])
        for e in ent:
            e["controls"] = ([{"at_s": ct[0], "control": CTRL_CONTROL, "delta": CTRL_DELTA, "flags": "manual"}] +
                             [{"at_s": t, "control": CTRL_CONTROL, "value": "start", "flags": "manual"}
                              for t in ct[1:]]) if ct else []
        m["control_plan"] = {"control": CTRL_CONTROL, "times_s": ct, "first": f"delta {CTRL_DELTA} steps, manual",
                             "then": "back to the first-read value, manual", "restore": "first-read value and mode",
                             "window": WINDOW, "roi": ROI}
        for k, why in excl.items():
            m["cameras"].setdefault(k, {"name": (cams_by_key.get(k) or {}).get("name")})["all_720p30"] = \
                {"excluded": why, "scope": why.startswith("no ")}
        if ent:
            s1 = run_session(ctx, "all_720p30", ent, sec["all_720p30"], rdir, tdir)
            m["parts"]["all_720p30"] = part_summary(s1, excl)
            handle_faults(ctx, "all_720p30", s1, cams_by_label, modes_txt, state)
            a1 = analyse_part(s1, cams_by_label, _nominal(ent))
            _merge_part(m, "all_720p30", a1, cams_by_label, ent, s1)
            for crec in (s1.get("doc") or {}).get("cameras") or []:
                cam = cams_by_label.get(crec.get("label"))
                if cam is None or not ct:
                    continue
                for rec in crec.get("controls") or []:
                    if rec.get("window"):
                        lum, info = window_lumas(rec)
                        q = {}
                        rows = FR.read_file((crec.get("files") or {}).get("frames_bin") or "")
                        want = set(lum)
                        for r in rows:
                            if r["seq"] in want:
                                q[r["seq"]] = r["qpc_ns"]
                        rec["effect"] = control_effect(rec, lum, q)
                        rec["window_check"] = info
                cm = m["cameras"].setdefault(cam["key"], {"name": cam.get("name")})
                cm["controls"] = crec.get("controls") or []
                cm["restore"] = crec.get("restore") or []
                cm["restore_skipped"] = crec.get("restore_skipped")
            if s1.get("dry_run"):
                m["parts"]["all_720p30"]["note"] = "plan mode: not executed"
        else:
            m["parts"]["all_720p30"] = {"ran": False, "excluded": excl, "reason": "no eligible camera"}

        # ---- part 2: 720p60 cameras together
        ent, excl = eligible("m60")
        for k, why in excl.items():
            m["cameras"].setdefault(k, {"name": (cams_by_key.get(k) or {}).get("name")})["all_720p60"] = \
                {"excluded": why, "scope": why.startswith("no ")}
        if ent:
            s2 = run_session(ctx, "all_720p60", ent, sec["all_720p60"], rdir, tdir)
            m["parts"]["all_720p60"] = part_summary(s2, excl)
            handle_faults(ctx, "all_720p60", s2, cams_by_label,
                          {ck.cam_slug(e["cam"]): e["mode"].text for e in ent}, state)
            _merge_part(m, "all_720p60", analyse_part(s2, cams_by_label, _nominal(ent)), cams_by_label, ent, s2)
        else:
            m["parts"]["all_720p60"] = {"ran": False, "excluded": excl, "reason": "no eligible 720p60 camera"}

        # ---- part 4: in-use detection on ONE camera other than the Kiyo Pro (never the Kiyo Pro)
        ent, excl = eligible("m30")
        ent = [e for e in ent if not e["cam"].get("is_kiyo")]
        p1c = m["cameras"]
        ent.sort(key=lambda e: 0 if ((p1c.get(e["cam"]["key"]) or {}).get("all_720p30") or {}).get("ok") else 1)
        if ent:
            tgt = ent[0]
            cam, md = tgt["cam"], tgt["mode"]
            lab = ck.cam_slug(cam)
            od = rdir / "in_use"
            at = INTRUDERS_AT_QUICK_S if ck.quick(ctx) else INTRUDERS_AT_S
            common = ["--device", cam["mf_symlink"], "--width", md.w, "--height", md.h, "--fps", md.fps_arg,
                      "--subtype", "MJPG", "--frames", 1, "--timeout-ms", INTRUDER_TIMEOUT_MS, "--save", "none"]
            intr = [{"label": "wincam_activity", "at_s": at[0], "timeout_s": 25, "target": lab,
                     "argv": ck.wincam_argv(ctx, "activity", "--wait-ms", 1500)},
                    {"label": "wincam_capture", "at_s": at[1], "timeout_s": 40, "target": lab,
                     "argv": ck.wincam_argv(ctx, "capture", "--api", "mf", *common, "--out-dir", od / "opener_wincam")},
                    {"label": "pymf_capture", "at_s": at[2], "timeout_s": 40 + wp.UV_SLACK_S, "target": lab,
                     "argv": wp.pymf_argv(ctx, "capture", *common, "--out-dir", od / "opener_pymf")}]
            for it in intr:
                it["argv"] = [str(a) for a in it["argv"]]
            s4 = run_session(ctx, "in_use", [{"cam": cam, "mode": md}], sec["in_use"], rdir, tdir, intruders=intr)
            m["parts"]["in_use"] = {**part_summary(s4, {k: v for k, v in excl.items()}), "target": cam["key"],
                                    "intruders": (s4.get("doc") or {}).get("intruders")}
            handle_faults(ctx, "in_use", s4, cams_by_label, {lab: md.text}, state)
            cm = m["cameras"].setdefault(cam["key"], {"name": cam.get("name"), "is_kiyo": False})
            if s4.get("doc") and (s4["doc"].get("cameras")):
                crec = next((c for c in s4["doc"]["cameras"] if c.get("label") == lab), {})
                rows = FR.read_file((crec.get("files") or {}).get("frames_bin") or "")
                cm["in_use"] = analyse_in_use(s4["doc"], rows, lab, float(md.fps), cam.get("mf_symlink"))
            else:
                cm["in_use"] = {"untested_reason": "the in-use session produced no result"
                                + (" (plan mode)" if s4.get("dry_run") else "")}
        else:
            m["parts"]["in_use"] = {"ran": False, "excluded": excl,
                                    "reason": "no eligible camera other than the Kiyo Pro (never used for this part)"}
    except Exception as e:  # noqa: BLE001
        import traceback
        errors.append({"exception": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()})
    m["kiyo_pro_fault"] = state.get("kiyo_pro_fault")
    m["faults_marked"] = state.get("faults_marked", [])
    m["session_hangs"] = state.get("session_hangs", [])
    m["arrivals"] = ck.arrivals_after(ctx, before)
    v = verdicts_from(m)
    return results.finish_result(res, measurements=m, verdicts=v, errors=errors)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import suitectx
    a0 = list(sys.argv[1:] if argv is None else argv)
    ap = suitectx.add_common_args(argparse.ArgumentParser(description=f"{TEST} standalone (opens cameras)"))
    ap.add_argument("--pymf-all-seconds", dest="pymf_all_seconds", type=float, default=None,
                    help="part 1 length (default 600 s, quick 60 s)")
    a = ap.parse_args(a0)
    ctx = suitectx.build_ctx(a)
    res = run(ctx)
    p = ctx.write(TEST, res)
    print(json.dumps({"out": str(p), "verdicts": {k: (x or {}).get("summary_label") or (x or {}).get("rating")
                                                  for k, x in (res.get("verdicts") or {}).items()}}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
