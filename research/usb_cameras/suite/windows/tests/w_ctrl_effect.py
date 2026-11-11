"""W-CTRL-EFFECT: set -> readback -> effect in the image, before and after stream start, persistence (G-CTRL).

Plan section 6.2 (CTRL-EFFECT) and section 3 (G-CTRL thresholds). Per camera, for each of exposure, gain,
white-balance temperature and focus that the camera supports with a manual mode (ranges read live with
``wincam controls --read-only``), through two control paths:

- ``mf``: the MF source during an MF capture: ``wincam capture --controls-before <c>=v1 --schedule
  "0:<c>=manual;1000:<c>=v2;2200:<c>=v3"`` (set on the same IMFMediaSource; readback per event). The 0 ms
  ``<c>=manual`` item re-sets the current value with the manual flag (a no-op when it held) and so records the value
  the camera has at the FIRST FRAME; fixed controls (exposure during the gain test) are re-applied at 0 ms and their
  readback asserted (ctrl_id_env B4: the C930e reset the fixed exposure at stream start);
- ``ds``: a DirectShow side channel during a pyav_ds capture: ``wincam controls --api ds --set`` in a concurrent
  process, once before the capture opens, a ``fix0`` re-apply of the fixed controls just after the capture opens
  (segment 1 starts after it), then twice while it streams. The leg runs under ONE camera lock in this module's
  ``--ds-leg`` child: each in-stream set starts only after the previous one RETURNED plus the segment gap, and the
  capture ends by stop file after the last set (11-06: slow Kiyo DS sets overran the old fixed schedule and left
  empty segments).

Values: exposure 3 in-range values (25/50/75% of the range), gain 10/50/90% with exposure fixed manual at mid-range,
white balance 3 temperatures inside 2800-6500 K (clipped to the range), focus with AF off at 0/25/50/75/100%.
Frames are saved every 3rd frame (raw_dir) and measured with common.imgmetrics (luma, R/B ratio, normalised
Laplacian sharpness) on the settled second half of each segment; raw YUY2/NV12 frames (PyAV's DirectShow fallback,
e.g. on the Kiyo) get the same three metrics computed from the Y/U/V planes. Effect criteria: exposure and gain raise luma
monotonically (last/first >= 1.25 and >= 1.15); white balance raises R/B monotonically (>= 1.10); focus changes
sharpness (max/min >= 1.30); the segments set while streaming alone need half that ratio.

Held through start (ctrl_id_env B3): a value set before the stream starts must still be there in the stream: MF
compares the value at the first frame (0 ms item) AND the value read just before the first in-stream set
(``schedule[0].before_value``) with the value set; DS uses ``before_value`` of set1. Tolerance: one range step
(min 1), because firmware rounds (C930e: 128 -> 127). A revert fails ``before_start_ok`` and names the workaround.

Persistence (B5): after the last run a short capture with no set, through the leg's own path, records the value in
the new stream and compares the image metric with the last segment of the last run: MF leg = MF capture with only
the 0 ms manual-keep read (value at the first frame); DS leg = PyAV DirectShow capture with one in-stream DS
read-only query ~1.2 s after it starts. The fresh-open readback without streaming is kept as
``readback_after_reopen`` (it read -4 on the C930e although the next stream start reverted it).

State and restore (V1): the full control state (exposure, gain, WB, focus, AE priority) is read before EVERY run and
the controls a control test touched (itself + fixed controls) are restored after THAT control's runs (auto -> auto,
others -> original value, verified by a read-only check, retried once), so one control test no longer runs in the
state the previous one left. A final restore in ``finally`` covers exceptions.

Device not answering (B1): when every device-backed GET fails (wincam ``device_not_answering`` / rc 4, a control
query timeout, or an MF/DS open that fails with device_error), the path rates ``no`` ("cannot set: device not
answering", with the HRESULT), the initial read JSON is saved to the test folder, the camera's remaining work is
skipped, and the fault is reported to the suite's dead-device gate when the runner provides one. A camera the gate
already marked faulted (and that failed the runner's re-probe) is skipped as "untested: device fault since <ts>".

Criterion 1 (B6): ``listed`` and ``range_matches_descriptor`` come from W-CTRL-LIST's ``per_control`` (listed through
MF and DS with descriptor support; MF and DS ranges equal), read from <out_dir>/W-CTRL-LIST.json; without that file,
from this test's own MF and DS initial reads (descriptor not checked; recorded as the source).
Runs: 3 per control and path (quick: 1, and the DS path only for exposure).

Offline re-rating of an existing run (no camera): ``python w_ctrl_effect.py --reanalyze <run_dir>`` writes
<run_dir>/reanalysis/W-CTRL-EFFECT.json (criterion 1 from W-CTRL-LIST, held-through-start from the stored MF
schedule readbacks, Kiyo paths whose every control was skipped for an empty caps field re-rated as device not
answering).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
import suitectx  # noqa: E402
from common import rating, results  # noqa: E402

TEST = "W-CTRL-EFFECT"
CONTROLS = ("exposure", "gain", "white_balance", "focus")
STATE_CONTROLS = CONTROLS + ("auto_exposure_priority",)
KS_KEY = {"exposure": "cc.exposure", "gain": "pa.gain", "white_balance": "pa.white_balance", "focus": "cc.focus"}
RANGE_FIELDS = ("min", "max", "step", "default", "caps_flags")
SAVE_EVERY = 3
PERSIST_TOL = {"luma_mean": 0.15, "rb_ratio": 0.15, "sharpness": 0.35}


def runs_per(ctx) -> int:
    return int(ck.arg(ctx, "ctrl_runs", 3, 1))


def estimate_s(ctx) -> float:
    """~8 s per MF run, ~11 s per DS run (incl. the per-run state read), persistence capture + restore per control,
    plus reads (calibrated on the C930e)."""
    r = runs_per(ctx)
    ds_ctrl = 1 if ck.quick(ctx) else 4
    return len(ctx.cameras) * (4 * r * 8 + ds_ctrl * r * 11 + (4 + ds_ctrl) * 7 + 12)


def _snap(v: float, c: dict) -> int:
    lo, hi, st = c.get("min"), c.get("max"), c.get("step") or 1
    v = max(lo, min(hi, v))
    return int(lo + round((v - lo) / st) * st) if st else int(round(v))


def values_for(name: str, c: dict) -> list[int] | None:
    lo, hi = c.get("min"), c.get("max")
    if lo is None or hi is None or hi <= lo:
        return None
    span = hi - lo
    if name == "exposure":
        qs = (0.25, 0.5, 0.75)
        vals = [_snap(lo + q * span, c) for q in qs]
    elif name == "gain":
        vals = [_snap(lo + q * span, c) for q in (0.1, 0.5, 0.9)]
    elif name == "white_balance":
        a, b = max(lo, 2800), min(hi, 6500)
        if b <= a:
            a, b = lo, hi
        vals = [_snap(a, c), _snap((a + b) / 2, c), _snap(b, c)]
    elif name == "focus":
        vals = [_snap(lo + q * span, c) for q in (0.0, 0.25, 0.5, 0.75, 1.0)]
    else:
        return None
    out = []
    for v in vals:
        if v not in out:
            out.append(v)
    return out if len(out) >= 2 else None


def manual_capable(c: dict) -> bool:
    return "manual" in (c.get("caps_flags_names") or []) and c.get("min") is not None


def _metric(name: str) -> str:
    return {"exposure": "luma_mean", "gain": "luma_mean", "white_balance": "rb_ratio", "focus": "sharpness"}[name]


# ------------------------------------------------------------------------------------------------------- health
def control_answered(c: dict) -> bool:
    """A supported control answered its value GET (new wincam: get_ok; older JSON: a value is present)."""
    if "get_ok" in c:
        return bool(c.get("get_ok"))
    return c.get("value") is not None


def _get_hr(c: dict):
    hr = c.get("hr") or {}
    if c.get("get_hr"):
        return c["get_hr"]
    if c.get("via") == "IKsControl":
        return hr.get("ks_get")
    return hr.get("iam_get") or hr.get("iam_get_range")


def not_answering(j: dict | None, run: dict | None) -> tuple[bool, str | None]:
    """(device not answering, HRESULT/reason) from one ``wincam controls --read-only`` result. Not answering =
    wincam's device_not_answering flag, a control query timeout or no JSON at all, an open that failed with a
    device_error or timeout class, or (older JSON) every device-backed supported control without a value.
    focal_length is descriptor data the driver answers without the device, so it does not count."""
    run = run or {}
    if j is None:
        if run.get("error"):            # not a camera call (e.g. no device link)
            return False, None
        return True, "timeout" if run.get("timed_out") else f"no JSON (rc={run.get('rc')})"
    err = j.get("error") or {}
    if j.get("device_not_answering"):
        return True, err.get("hr") or "control_get"
    if err and (err.get("class") in ("device_error", "timeout") or err.get("stage") in ("control_query",
                                                                                         "control_get")):
        return True, err.get("hr") or err.get("hr_name") or err.get("class")
    sup = [c for c in j.get("controls") or [] if c.get("supported") and c.get("name") != "focal_length"]
    if sup and not any(control_answered(c) for c in sup):
        return True, next((_get_hr(c) for c in sup if _get_hr(c)), None) or "every GET failed"
    return False, None


def _state(ctx, cam: dict, api: str) -> tuple[dict, tuple[bool, str | None], dict]:
    """Full control state (STATE_CONTROLS) through ``api``, the health verdict and the run record."""
    j, r = ck.get_controls(ctx, cam, api)
    tab = ck.control_table(j)
    st = {n: {"value": (tab.get(n) or {}).get("value"), "flags": (tab.get(n) or {}).get("flags_names")}
          for n in STATE_CONTROLS if n in tab}
    return st, not_answering(j, r), r


# --------------------------------------------------------------------------------------- dead-device gate (runner)
def gate_fault(ctx, cam: dict, gated_only: bool = True) -> dict | None:
    """The suite dead-device gate record for this camera. With the runner's gate (suitectx camera_gated /
    camera_faulted through capkit.device_gated / device_fault): ``gated_only`` = faulted at the START of this test
    after the runner's 1-frame re-probe (its work here is skipped); otherwise faulted now (e.g. by a capture during
    this test). Without it: a duck-typed ctx.device_fault / camera_fault / fault_for(key) or dict device_faults."""
    fn = getattr(ck, "device_gated" if gated_only else "device_fault", None)
    if callable(fn):
        try:
            return fn(ctx, cam)
        except Exception:  # noqa: BLE001
            return None
    key = cam.get("key")
    for attr in ("device_fault", "camera_fault", "fault_for", "faulted"):
        f2 = getattr(ctx, attr, None)
        if callable(f2):
            try:
                f = f2(key)
            except Exception:  # noqa: BLE001
                f = None
            return (f if isinstance(f, dict) else {"faulted": True, "detail": f}) if f else None
    for attr in ("device_faults", "faults"):
        d = getattr(ctx, attr, None)
        if isinstance(d, dict) and d.get(key):
            f = d[key]
            return f if isinstance(f, dict) else {"faulted": True, "detail": f}
    return None


def gate_untested(ctx, cam: dict, fault: dict) -> dict:
    """'untested: device fault since <ts>' (suitectx fault_untested when present, else common.rating)."""
    fn = getattr(ctx, "fault_untested", None)
    if callable(fn):
        try:
            return fn(cam)
        except Exception:  # noqa: BLE001
            pass
    return rating.device_fault_untested(fault)


def gate_report(ctx, cam: dict, mode: str | None, code: str | None, detail: str, api: str | None = None) -> bool:
    """Report 'device not answering' found here to the suite gate (capkit.mark_device_fault -> ctx.mark_fault, which
    also records the suite-wide first failure; idempotent). Falls back to a duck-typed ctx.mark_fault."""
    fault = {"kind": "device_error", "code": code, "stage": "control_get", "reason": f"device not answering: {detail}"}
    fn = getattr(ck, "mark_device_fault", None)
    if callable(fn):
        try:
            fn(ctx, cam, TEST, mode, api, fault)
            return True
        except Exception:  # noqa: BLE001
            return False
    f2 = getattr(ctx, "mark_fault", None)
    if callable(f2):
        try:
            f2(cam.get("key"), test=TEST, mode=mode, code=code, detail=detail)
            return True
        except Exception:  # noqa: BLE001
            return False
    return False


# ------------------------------------------------------------------------------------------------------- metrics
def _raw_planes(data: bytes, w: int, h: int):
    """(Y, U, V) float arrays from a raw YUY2 (w*h*2 bytes) or NV12 (w*h*3/2) frame, else None. PyAV DirectShow
    delivers raw video when a raw format matches the requested size and rate (see pyav_ds.py), e.g. on the Kiyo."""
    import numpy as np  # noqa: PLC0415
    n = len(data)
    a = np.frombuffer(data, dtype=np.uint8)
    if n == w * h * 2:
        q = a.reshape(h, w // 2, 4).astype(np.float64)
        y = a.reshape(h, w * 2)[:, 0::2].astype(np.float64)
        return y, q[..., 1], q[..., 3]
    if n == w * h * 3 // 2:
        y = a[: w * h].reshape(h, w).astype(np.float64)
        uv = a[w * h:].reshape(h // 2, w // 2, 2).astype(np.float64)
        return y, uv[..., 0], uv[..., 1]
    return None


def _crop(arr, roi):
    hh, ww = arr.shape[:2]
    l, t, r, b = roi
    return arr[int(t * hh):max(int(t * hh) + 1, int(b * hh)), int(l * ww):max(int(l * ww) + 1, int(r * ww))]


def metric_value(data: bytes, w: int, h: int, metric: str) -> float | None:
    """luma_mean / rb_ratio / sharpness of a JPEG (common.imgmetrics) or a raw YUY2/NV12 frame (same formulas)."""
    roi = (0.25, 0.25, 0.75, 0.75) if metric == "sharpness" else (0.1, 0.1, 0.9, 0.9)
    if data[:2] == b"\xff\xd8":
        from common import imgmetrics as im  # noqa: PLC0415
        return {"luma_mean": im.luma_mean, "rb_ratio": im.rb_ratio, "sharpness": im.sharpness}[metric](data, roi)
    planes = _raw_planes(data, w, h)
    if planes is None:
        return None
    y, u, v = planes
    if metric == "luma_mean":
        return float(_crop(y, roi).mean())
    if metric == "rb_ratio":
        ym, um, vm = float(_crop(y, roi).mean()), float(_crop(u, roi).mean()), float(_crop(v, roi).mean())
        r_ = ym + 1.402 * (vm - 128.0)
        b_ = ym + 1.772 * (um - 128.0)
        return r_ / max(b_, 1e-6)
    yy = _crop(y, roi)
    if yy.shape[0] < 3 or yy.shape[1] < 3:
        return 0.0
    lap = (yy[1:-1, :-2] + yy[1:-1, 2:] + yy[:-2, 1:-1] + yy[2:, 1:-1]) - 4.0 * yy[1:-1, 1:-1]
    m = float(yy.mean())
    return float(lap.var() / max(m * m, 1e-6))


def _segment_metrics(out_dir: Path, bounds_ns: list[tuple[float, float]], metric: str, mode=None) -> list[dict]:
    """bounds_ns: per segment (start, end) in qpc ns; uses saved frames in the second half of each segment."""
    rows = ck.load_frames(out_dir)
    frames = ck.saved_frame_bytes(out_dir, rows)
    w, h = (mode.w, mode.h) if mode is not None else (0, 0)
    out = []
    kinds = set()
    for a, b in bounds_ns:
        mid = a + (b - a) / 2
        vals = []
        err = None
        for r, data in frames:
            t = r.get("qpc_ns")
            if t is None or not (mid <= t < b):
                continue
            kinds.add("jpeg" if data[:2] == b"\xff\xd8" else "raw")
            try:
                v = metric_value(data, w, h, metric)
                if v is not None:
                    vals.append(v)
            except Exception as e:  # noqa: BLE001
                err = repr(e)[:160]
                continue
        out.append({"n": len(vals), "value": (sum(vals) / len(vals)) if vals else None, "error": err,
                    "frame_kinds": sorted(kinds)})
    return out


def _mono_effect(name: str, vals: list[int], m: list[float], half: bool = False) -> tuple[bool, bool, float | None]:
    """Monotonic in the setting and last/first >= the required ratio (``half``: half the effect, used for the
    two segments set while streaming, which span a smaller part of the range)."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    mv = [m[i] for i in order]
    mono = all(b >= a * 0.98 for a, b in zip(mv, mv[1:]))
    ratio = (mv[-1] / mv[0]) if mv[0] else None
    need = {"exposure": 1.25, "gain": 1.15, "white_balance": 1.10}[name]
    if half:
        need = 1 + (need - 1) / 2
    return bool(mono and ratio is not None and ratio >= need), mono, ratio


def judge(name: str, vals: list[int], seg: list[dict]) -> dict:
    """effect_ok over all segments; effect_after_ok over the segments set while streaming; effect_before_ok =
    the segment set before the stream started fits the trend (exposure/gain/WB) - a camera that ignores a
    before-start set until it is re-applied (needs a workaround) shows effect_after_ok True, effect_before_ok False."""
    m = [s.get("value") for s in seg]
    if any(x is None for x in m) or len(m) < 2:
        return {"effect_ok": None, "effect_after_ok": None, "effect_before_ok": None,
                "reason": "a segment had no measurable frames", "metric_values": m}
    if name in ("exposure", "gain", "white_balance"):
        need = {"exposure": 1.25, "gain": 1.15, "white_balance": 1.10}[name]
        ok, mono, ratio = _mono_effect(name, vals, m)
        after_ok = None
        if len(m) >= 3:
            after_ok, _, after_ratio = _mono_effect(name, vals[1:], m[1:], half=True)
        else:
            after_ratio = None
        before_ok = ok if after_ok else None
        return {"effect_ok": ok, "effect_after_ok": after_ok, "effect_before_ok": before_ok, "monotonic": mono,
                "ratio_last_first": ratio, "ratio_after_start": after_ratio, "required_ratio": need,
                "metric_values": m}
    mx, mn = max(m), min(m)
    ratio = (mx / mn) if mn else None
    ok = bool(ratio is not None and ratio >= 1.30)
    m_after = m[1:]
    after_ok = bool(min(m_after) and max(m_after) / min(m_after) >= 1.30) if len(m_after) >= 2 else None
    return {"effect_ok": ok, "effect_after_ok": after_ok, "effect_before_ok": None, "ratio_max_min": ratio,
            "required_ratio": 1.30, "metric_values": m, "best_value": vals[m.index(mx)]}


# ------------------------------------------------------------------------------------------------------- held
def step_tol(step) -> float:
    """Readback tolerance: one range step and at least 1 (firmware rounding, e.g. C930e gain 128 -> 127); when the
    control's range is known (``step`` given as the control / range dict) also 1% of the span (the C922 set gain 230
    and read 228 at the next stream start, a 0..255 range)."""
    span = None
    if isinstance(step, dict):
        lo, hi = step.get("min"), step.get("max")
        span = (hi - lo) if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) else None
        step = step.get("step")
    try:
        st = max(1, abs(int(step or 1)))
    except (TypeError, ValueError):
        st = 1
    return max(st, 0.01 * span) if span else st


def held(value, flags, want, step) -> bool | None:
    """The camera still has ``want`` (within ``step_tol(step)``) in manual mode; None when nothing was read.
    ``step``: the range step, or the control / range dict (min, max, step)."""
    if value is None or want is None:
        return None
    ok = abs(value - want) <= step_tol(step)
    if isinstance(flags, int) and not isinstance(flags, bool):
        ok = ok and bool(flags & 2)
    return bool(ok)


def _all_held(*vals) -> bool | None:
    known = [v for v in vals if v is not None]
    return None if not known else all(known)


def mf_held_from_record(rr: dict, name: str, step) -> dict:
    """Held-through-start fields of an MF run record (also works on runs stored before the 0 ms read existed:
    then only the value before the first in-stream set is known)."""
    vals = rr.get("values") or []
    want = vals[0] if vals else None
    sched = [e for e in rr.get("schedule") or [] if str(e.get("control", "")).endswith(name)]
    first = [e for e in sched if (e.get("at_ms") or 0) <= 0]
    later = [e for e in sched if (e.get("at_ms") or 0) > 0]
    v_ff = first[0].get("before_value") if first else None
    f_ff = first[0].get("before_flags") if first else None
    v_bs = later[0].get("before_value") if later else None
    f_bs = later[0].get("before_flags") if later else None
    h_ff, h_bs = held(v_ff, f_ff, want, step), held(v_bs, f_bs, want, step)
    return {"value_at_first_frame": v_ff, "value_before_first_set": v_bs, "held_at_first_frame": h_ff,
            "held_until_first_set": h_bs, "held_through_start": _all_held(h_ff, h_bs), "tolerance": step_tol(step)}


# ------------------------------------------------------------------------------------------------------- MF path
def run_mf(ctx, cam, name: str, vals: list[int], fix: dict, od: Path, mode, step=1, fix_steps=None) -> dict:
    step_ms = 1200 if name != "focus" else 900
    before = ",".join([f"{k}={v}" for k, v in fix.items()] + [f"{name}={vals[0]}"])
    # 0 ms: re-apply fixed controls (B4) and read the tested control at the first frame (manual keep, B3)
    sched_items = [f"0:{k}={v}" for k, v in fix.items()] + [f"0:{name}=manual"]
    sched_items += [f"{1000 + (i - 1) * step_ms}:{name}={v}" for i, v in enumerate(vals) if i > 0]
    sched = ";".join(sched_items)
    secs = (1000 + (len(vals) - 1) * step_ms) / 1000.0 + 1.2
    s, r = ck.wincam_capture(ctx, cam, mode, od, seconds=secs, save=f"every:{SAVE_EVERY}",
                             extra=["--controls-before", before, "--schedule", sched])
    s = s or {}
    rows = ck.load_frames(od)
    t_first = rows[0]["qpc_ns"] if rows else None
    t_last = rows[-1]["qpc_ns"] if rows else None
    allev = s.get("schedule") or []
    ev = [e for e in allev if str(e.get("control", "")).endswith(name) and (e.get("at_ms") or 0) > 0]
    cuts = [e.get("applied_qpc_ns") for e in ev]
    bounds = []
    if t_first is not None and all(isinstance(c, (int, float)) for c in cuts) and len(cuts) == len(vals) - 1:
        edges = [t_first] + cuts + [t_last + 1]
        bounds = list(zip(edges[:-1], edges[1:]))
    seg = _segment_metrics(od, bounds, _metric(name), mode) if bounds else []
    cb_all = s.get("controls_before") or []
    cb = [x for x in cb_all if str(x.get("control", "")).endswith(name)]
    before_rb = bool(cb) and all(x.get("matches") for x in cb)
    after_rb = bool(ev) and all(x.get("matches") for x in ev)
    j = judge(name, vals, seg) if seg else {"effect_ok": None, "reason": "no segments (capture failed?)"}
    rec = {"path": "mf", "values": vals, "fixed": fix, "capture_ok": bool(s.get("ok")), "run": r,
           "frames": len(rows), "before_start_readback": before_rb, "after_start_readback": after_rb,
           "controls_before": cb, "controls_before_all": cb_all, "schedule": ev,
           "schedule_at_first_frame": [e for e in allev if (e.get("at_ms") or 0) <= 0],
           "segments": seg, **j, "error": s.get("error")}
    rec.update(mf_held_from_record({"values": vals, "schedule": allev}, name, step))
    fixd = {}
    for k, v in fix.items():
        e0 = next((e for e in allev if str(e.get("control", "")).endswith(k) and (e.get("at_ms") or 0) <= 0), None)
        fixd[k] = {"value_at_first_frame": (e0 or {}).get("before_value"),
                   "held_through_start": held((e0 or {}).get("before_value"), (e0 or {}).get("before_flags"), v,
                                              (fix_steps or {}).get(k, 1)),
                   "reapplied_at_0ms_ok": (e0 or {}).get("matches")}
    rec["fixed_controls"] = fixd
    return rec


# ------------------------------------------------------------------------------------------------------- DS path
#: DS leg schedule (seconds): the capture starts this long after set0 returned; fix0 runs this long after the capture
#: started; set1 no earlier than DS_FIRST_SET_S after the capture started; every later set starts only after the
#: previous one RETURNED plus the segment gap (11-06: slow Kiyo DS sets overran a fixed schedule and left empty
#: segments); the capture ends by stop file DS_TAIL_S after the last set returned
DS_CAPTURE_AFTER_SET0_S = 0.3
DS_FIX0_S = 1.2
DS_FIRST_SET_S = 3.0
DS_TAIL_S = 1.6
DS_SET_TIMEOUT_S = 20.0
DS_CAPTURE_MAX_S = 90.0


def ds_set_argv(ctx, cam: dict, items: dict) -> list[str]:
    spec = ",".join(f"{k}={x}" for k, x in items.items())
    return ck.wincam_argv(ctx, "controls", "--api", "ds", "--device", cam["ds_path"], "--set", spec, "--timeout-ms",
                          4000)


def ds_leg(ctx, cam: dict, mode, od: Path, before: list[dict], stream: list[dict], tail_s: float = DS_TAIL_S,
           save: str = f"every:{SAVE_EVERY}") -> tuple[dict | None, dict]:
    """One DirectShow leg under ONE camera lock (this module's ``--ds-leg`` runner in a child): the ``before``
    steps run back to back, then a PyAV DirectShow capture starts, then the ``stream`` steps run CHAINED (each no
    earlier than its ``not_before_s`` after the capture start and ``after_prev_s`` after the previous step returned),
    and the capture is ended by stop file ``tail_s`` after the last step. Returns (runner JSON, run record)."""
    od = Path(od)
    od.mkdir(parents=True, exist_ok=True)
    stop = od / "stop_capture.flag"
    try:
        stop.unlink()
    except OSError:
        pass
    cap = ck.pyav_capture_argv(ctx, cam, mode, od, DS_CAPTURE_MAX_S, save=save, stop_file=stop)
    spec = {"before": before, "stream": stream, "capture": {"argv": [str(a) for a in cap],
                                                             "start_delay_s": DS_CAPTURE_AFTER_SET0_S,
                                                             "stdout": str(od / "capture_stdout.json"),
                                                             "stderr": str(od / "capture_stderr.txt"),
                                                             "stop_timeout_s": 25.0},
            "stop_file": str(stop), "tail_s": tail_s}
    sp = od.parent / f"{od.name}_leg.json"
    results.write_json(sp, spec)
    bound = sum(float(s.get("timeout_s") or DS_SET_TIMEOUT_S) + float(s.get("after_prev_s") or 0)
                for s in before + stream) + DS_FIRST_SET_S + tail_s + 60
    r = ctx.camcmd([sys.executable, str(Path(__file__).resolve()), "--ds-leg", str(sp)],
                   timeout_s=min(bound, DS_CAPTURE_MAX_S + 120))
    return ck.parse_json(r), ck.run_brief(r)


def ds_leg_main(spec_path: str) -> int:
    """Child process: run one DS leg (see ``ds_leg``) and print one JSON object. Times are perf_counter_ns (QPC on
    Windows: the same clock as pyav_ds's ``qpc_ns``)."""
    import shutil  # noqa: PLC0415
    from common import procutil  # noqa: PLC0415
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    t0 = time.perf_counter_ns()
    steps: list[dict] = []

    def resolve(argv: list) -> list[str]:
        argv = [str(a) for a in argv]
        if argv and not Path(argv[0]).is_absolute():
            argv = [shutil.which(argv[0]) or argv[0]] + argv[1:]
        return argv

    def run_step(s: dict) -> dict:
        ts = time.perf_counter_ns()
        rr = procutil.run(resolve(s["argv"]), timeout_s=float(s.get("timeout_s") or DS_SET_TIMEOUT_S))
        te = time.perf_counter_ns()
        rec = {"label": s.get("label"), "t_start_ns": ts, "t_end_ns": te, "t_start_s": (ts - t0) / 1e9,
               "t_end_s": (te - t0) / 1e9, "rc": rr.get("rc"), "timed_out": rr.get("timed_out"),
               "stdout": (rr.get("stdout") or "")[-400_000:], "stderr_tail": (rr.get("stderr") or "")[-3000:]}
        steps.append(rec)
        return rec

    for s in spec.get("before") or []:
        run_step(s)
    c = spec["capture"]
    time.sleep(float(c.get("start_delay_s") or 0))
    bg = procutil.Background(resolve(c["argv"]), stdout_path=c.get("stdout"), stderr_path=c.get("stderr")).start()
    t_cap = bg.t_start_ns or time.perf_counter_ns()
    prev_end = t_cap
    for s in spec.get("stream") or []:
        due = max(t_cap + int(float(s.get("not_before_s") or 0) * 1e9),
                  prev_end + int(float(s.get("after_prev_s") or 0) * 1e9))
        while time.perf_counter_ns() < due and bg.running():
            time.sleep(0.02)
        prev_end = run_step(s)["t_end_ns"]
    end = prev_end + int(float(spec.get("tail_s") or DS_TAIL_S) * 1e9)
    while time.perf_counter_ns() < end and bg.running():
        time.sleep(0.02)
    Path(spec["stop_file"]).write_text("stop", encoding="ascii")
    cr = bg.stop(float(c.get("stop_timeout_s") or 25.0))
    try:
        cap_out = Path(c["stdout"]).read_text(encoding="utf-8", errors="replace") if c.get("stdout") else ""
    except OSError:
        cap_out = ""
    doc = {"tool": "w_ctrl_effect ds-leg", "t0_ns": t0, "utc_finished": results.utc_now_iso(), "steps": steps,
           "capture": {"label": "capture", "argv": c["argv"], "t_start_ns": t_cap, "t_end_ns": cr.get("t_end_ns"),
                       "t_start_s": (t_cap - t0) / 1e9, "rc": cr.get("rc"), "timed_out": cr.get("timed_out"),
                       "killed": cr.get("killed"), "stdout": cap_out[-400_000:],
                       "stderr_tail": "\n".join(cr.get("stderr_tail") or [])[-3000:]
                       if isinstance(cr.get("stderr_tail"), list) else (cr.get("stderr_tail") or "")[-3000:]}}
    sys.stdout.write(json.dumps(doc, default=str) + "\n")
    return 0


def run_ds(ctx, cam, name: str, vals: list[int], fix: dict, od: Path, mode, step=1, fix_steps=None) -> dict:
    gap = 1.4 if name != "focus" else 1.2
    before = [{"label": "set0", "argv": ds_set_argv(ctx, cam, {**fix, name: vals[0]}), "timeout_s": DS_SET_TIMEOUT_S}]
    stream = []
    if fix:   # B4: re-apply the fixed controls in-stream
        stream.append({"label": "fix0", "argv": ds_set_argv(ctx, cam, dict(fix)), "not_before_s": DS_FIX0_S,
                       "after_prev_s": 0.0, "timeout_s": DS_SET_TIMEOUT_S})
    for i, v in enumerate(vals[1:], start=1):
        stream.append({"label": f"set{i}", "argv": ds_set_argv(ctx, cam, {name: v}),
                       "not_before_s": DS_FIRST_SET_S + (i - 1) * gap, "after_prev_s": gap if i > 1 else 0.3,
                       "timeout_s": DS_SET_TIMEOUT_S})
    out, run = ds_leg(ctx, cam, mode, od, before, stream)
    cmds = {c.get("label"): c for c in (out or {}).get("steps", [])}
    cap = (out or {}).get("capture") or {}
    s, _ = suitectx.parse_json_stdout({"stdout": cap.get("stdout") or ""})
    s = s or {}
    rows = ck.load_frames(od)

    def parse_set(label: str, want: dict) -> dict:
        c = cmds.get(label) or {}
        sj, _ = suitectx.parse_json_stdout({"stdout": c.get("stdout") or ""})
        per = {}
        for k in want:
            mine = [x for x in (sj or {}).get("sets") or [] if str(x.get("control", "")).endswith(k)]
            per[k] = {"matches": bool(mine) and all(x.get("matches") for x in mine),
                      "before_value": mine[0].get("before_value") if mine else None,
                      "before_flags": mine[0].get("before_flags") if mine else None,
                      "readback_value": mine[0].get("readback_value") if mine else None,
                      "hr": [x.get("hr_set_name") for x in mine]}
        return {"rc": c.get("rc"), "t_start_ns": c.get("t_start_ns"), "t_end_ns": c.get("t_end_ns"), "per": per,
                "error": (sj or {}).get("error"), "device_not_answering": (sj or {}).get("device_not_answering")}

    sets = []
    for i in range(len(vals)):
        p = parse_set(f"set{i}", {name: vals[i]})
        me = p["per"][name]
        sets.append({"value": vals[i], "rc": p["rc"], "t_start_ns": p["t_start_ns"], "t_end_ns": p["t_end_ns"],
                     "matches": me["matches"], "before_value": me["before_value"], "before_flags": me["before_flags"],
                     "readback_value": me["readback_value"], "hr": me["hr"], "error": p["error"],
                     "device_not_answering": p["device_not_answering"]})
    fix0 = parse_set("fix0", fix) if fix else None
    bounds = []
    if rows and all(isinstance(x.get("t_end_ns"), (int, float)) for x in sets[1:]):
        t_first, t_last = rows[0]["qpc_ns"], rows[-1]["qpc_ns"]
        s0 = t_first
        if fix0 and isinstance(fix0.get("t_end_ns"), (int, float)):
            s0 = max(t_first, fix0["t_end_ns"] + 150e6)     # segment 1 starts after the in-stream re-apply
        starts = [s0] + [x["t_end_ns"] + 150e6 for x in sets[1:]]
        ends = [x["t_start_ns"] for x in sets[1:]] + [t_last + 1]
        bounds = list(zip(starts, ends))
    seg = _segment_metrics(od, bounds, _metric(name), mode) if bounds else []
    j = judge(name, vals, seg) if seg else {"effect_ok": None, "reason": "no segments (capture failed?)"}
    before_ok = sets[0]["matches"] and (sets[0].get("t_end_ns") or 0) <= (cap.get("t_start_ns") or 0) + 1.0e9
    # held through start (B3): the value set1 found before it set its own (= the value through the stream start)
    h_bs = held(sets[1]["before_value"], sets[1]["before_flags"], vals[0], step) if len(sets) > 1 else None
    fixd = {}
    for k, v in fix.items():
        pk = ((fix0 or {}).get("per") or {}).get(k) or {}
        fixd[k] = {"value_in_stream_before_reapply": pk.get("before_value"),
                   "held_through_start": held(pk.get("before_value"), pk.get("before_flags"), v,
                                              (fix_steps or {}).get(k, 1)),
                   "reapplied_in_stream_ok": pk.get("matches") if pk else None}
    return {"path": "ds", "values": vals, "fixed": fix, "capture_ok": bool(s.get("ok")) or bool(rows),
            "launcher": run, "frames": len(rows), "sets": sets, "fix0": fix0, "fixed_controls": fixd,
            "before_start_readback": bool(sets[0]["matches"]), "before_start_set_finished_before_open": before_ok,
            "after_start_readback": all(x["matches"] for x in sets[1:]), "segments": seg, **j,
            "value_before_first_set": sets[1]["before_value"] if len(sets) > 1 else None,
            "held_until_first_set": h_bs, "held_through_start": h_bs, "tolerance": step_tol(step),
            "capture_error": s.get("error"), "capture_stderr": None if s else cap.get("stderr_tail")}


# ------------------------------------------------------------------------------------------------------- persistence
def persistence_check(ctx, cam, name: str, vals: list[int], step, mode, od: Path, last_metric: float | None) -> dict:
    """Short MF capture without any set (only the 0 ms manual-keep read): is the last value still there at the first
    frame of a NEW stream, and does the image match the last segment of the last run? (B5)"""
    if not cam.get("mf_symlink") or mode is None:
        return {"skipped": "no MF symlink"}
    s, r = ck.wincam_capture(ctx, cam, mode, od, seconds=1.6, save=f"every:{SAVE_EVERY}",
                             extra=["--schedule", f"0:{name}=manual"])
    s = s or {}
    ev = [e for e in s.get("schedule") or [] if str(e.get("control", "")).endswith(name)]
    v0, f0 = (ev[0].get("before_value"), ev[0].get("before_flags")) if ev else (None, None)
    h = held(v0, f0, vals[-1], step)
    rows = ck.load_frames(od)
    seg = _segment_metrics(od, [(rows[0]["qpc_ns"], rows[-1]["qpc_ns"] + 1)], _metric(name), mode) if rows else []
    mval = seg[0]["value"] if seg else None
    ratio = (mval / last_metric) if (mval is not None and last_metric) else None
    tol = PERSIST_TOL[_metric(name)]
    m_ok = None if ratio is None else abs(ratio - 1.0) <= tol
    persisted = None if h is None and m_ok is None else bool((h is not False) and (m_ok is not False))
    return {"capture_ok": bool(s.get("ok")), "run": r, "frames": len(rows), "value_at_first_frame": v0,
            "flags_at_first_frame": f0, "held_at_first_frame": h, "metric": mval, "last_run_metric": last_metric,
            "metric_ratio": ratio, "metric_tolerance": tol, "metric_matches": m_ok, "persisted": persisted,
            "error": s.get("error")}


def persistence_check_ds(ctx, cam, name: str, vals: list[int], step, mode, od: Path,
                         last_metric: float | None) -> dict:
    """The DS leg's persistence check through its own path (11-06: it was always captured through MF): a short PyAV
    DirectShow capture with one in-stream ``wincam controls --api ds --read-only`` ~1.2 s after the capture started;
    is the last value still set in the NEW stream, and does the image match the last segment of the last run?"""
    if not cam.get("ds_path") or mode is None:
        return {"skipped": "no DirectShow path"}
    read = ck.wincam_argv(ctx, "controls", "--api", "ds", "--device", cam["ds_path"], "--read-only", "--timeout-ms",
                          4000)
    out, run = ds_leg(ctx, cam, mode, od, [], [{"label": "read", "argv": read, "not_before_s": DS_FIX0_S,
                                                 "after_prev_s": 0.0, "timeout_s": DS_SET_TIMEOUT_S}], tail_s=0.8)
    steps = {c.get("label"): c for c in (out or {}).get("steps", [])}
    rj, _ = suitectx.parse_json_stdout({"stdout": (steps.get("read") or {}).get("stdout") or ""})
    c = ck.control_table(rj).get(name) or {}
    v0, flags = c.get("value"), c.get("flags_names") or []
    h = None if v0 is None else (held(v0, None, vals[-1], step) and "manual" in flags)
    rows = ck.load_frames(od)
    seg = _segment_metrics(od, [(rows[0]["qpc_ns"], rows[-1]["qpc_ns"] + 1)], _metric(name), mode) \
        if rows and rows[0].get("qpc_ns") is not None else []
    mval = seg[0]["value"] if seg else None
    ratio = (mval / last_metric) if (mval is not None and last_metric) else None
    tol = PERSIST_TOL[_metric(name)]
    m_ok = None if ratio is None else abs(ratio - 1.0) <= tol
    persisted = None if h is None and m_ok is None else bool((h is not False) and (m_ok is not False))
    cap = (out or {}).get("capture") or {}
    s, _ = suitectx.parse_json_stdout({"stdout": cap.get("stdout") or ""})
    return {"path": "ds", "capture_ok": bool((s or {}).get("ok")) or bool(rows), "run": run, "frames": len(rows),
            "value_in_stream": v0, "flags_in_stream": flags, "held_in_new_stream": h, "metric": mval,
            "last_run_metric": last_metric, "metric_ratio": ratio, "metric_tolerance": tol, "metric_matches": m_ok,
            "persisted": persisted, "error": (s or {}).get("error") if s else (rj or {}).get("error")}


# ------------------------------------------------------------------------------------------------------- restore
def restore(ctx, cam, api: str, orig: dict[str, dict]) -> dict:
    auto = {n: "auto" for n, c in orig.items() if "auto" in (c.get("flags_names") or [])}
    manual = {n: c.get("value") for n, c in orig.items() if n not in auto and c.get("value") is not None}
    out = {"auto": auto, "manual": manual, "steps": []}
    for sets, flags in ((manual, "manual"), (auto, None)):
        if not sets:
            continue
        j, r = ck.set_controls(ctx, cam, api, sets, flags=flags)
        out["steps"].append({"sets": sets, "run": r, "ok": bool(j) and all(x.get("matches") for x in j.get("sets", [])),
                             "detail": (j or {}).get("sets")})
    chk, r = ck.get_controls(ctx, cam, api)
    tab = ck.control_table(chk)
    out["after"] = {n: {"value": tab.get(n, {}).get("value"), "flags": tab.get(n, {}).get("flags_names")} for n in orig}
    out["restored"] = all((("auto" in (out["after"][n]["flags"] or [])) if n in auto else
                           out["after"][n]["value"] == manual.get(n)) for n in orig) if chk else None
    return out


def restore_verified(ctx, cam, api: str, orig: dict[str, dict], errors: list, what: str) -> dict:
    rs = restore(ctx, cam, api, orig)
    if rs.get("restored") is not True:
        # one more attempt after a pause (a busy or slow camera); recorded
        ctx.log(f"{TEST}: {cam.get('name')} {api} {what}: restore not verified; retrying once")
        time.sleep(2.0)
        rs2 = restore(ctx, cam, api, orig)
        rs2["first_attempt"] = rs
        rs = rs2
        if rs.get("restored") is not True:
            errors.append({"camera": cam["key"], "api": api, "after": what, "restore_not_verified": rs.get("after"),
                           "wanted": {"auto": rs.get("auto"), "manual": rs.get("manual")}})
    return rs


# ------------------------------------------------------------------------------------------------------- rating input
def listing_inputs(ctrl_list_cam: dict | None, name: str, tabs: dict[str, dict] | None = None) -> dict:
    """{listed, range_matches_descriptor, source} for G-CTRL criterion 1 (B6). From W-CTRL-LIST's per_control
    (or, for results written before per_control existed, its descriptor_to_ks / supported / mf_vs_ds_differences);
    without a W-CTRL-LIST record, from this test's own MF and DS reads (descriptor not checked)."""
    ks = KS_KEY.get(name, name)
    if ctrl_list_cam:
        pc = (ctrl_list_cam.get("per_control") or {}).get(ks)
        if pc:
            listed = bool(pc.get("listed_mf") and pc.get("listed_ds") and pc.get("descriptor_listed_ok") is not False)
            return {"listed": listed, "range_matches_descriptor": pc.get("ranges_equal_mf_ds"),
                    "source": "W-CTRL-LIST per_control", "descriptor_backed": pc.get("descriptor_backed")}
        sup = (ctrl_list_cam.get("supported") or {}).get(ks)
        if sup is None:
            return {"listed": False, "range_matches_descriptor": None, "source": "W-CTRL-LIST (not listed)"}
        rows = [r for r in ctrl_list_cam.get("descriptor_to_ks") or [] if r.get("ks") == ks and r.get("aspect") == "value"]
        listed = bool(sup.get("mf") and sup.get("ds") and all(r.get("mf") and r.get("ds") for r in rows))
        diffs = [d for d in ctrl_list_cam.get("mf_vs_ds_differences") or [] if d.get("control") == ks
                 and d.get("field") in RANGE_FIELDS + ("supported",)]
        return {"listed": listed, "range_matches_descriptor": not diffs if (sup.get("mf") and sup.get("ds")) else None,
                "source": "W-CTRL-LIST descriptor_to_ks + mf_vs_ds_differences", "descriptor_backed": bool(rows)}
    tabs = tabs or {}
    a, b = (tabs.get("mf") or {}).get(name), (tabs.get("ds") or {}).get(name)
    if a is None and b is None:
        return {"listed": None, "range_matches_descriptor": None, "source": "no listing available"}
    eq = (all(a.get(f) == b.get(f) for f in RANGE_FIELDS) if (a and b) else None)
    return {"listed": bool(a and b), "range_matches_descriptor": eq,
            "source": "W-CTRL-EFFECT initial MF/DS reads (no W-CTRL-LIST result; descriptor not checked)"}


def load_ctrl_list(path: Path) -> dict[str, dict]:
    """{camera key: W-CTRL-LIST camera record} from a W-CTRL-LIST.json (empty if missing/unreadable)."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {c.get("key"): c for c in (d.get("measurements") or {}).get("cameras") or []}


def run_counts_ok(x: dict) -> bool:
    return bool(x.get("effect_ok") and x.get("after_start_readback") and x.get("before_start_readback")
                and x.get("held_through_start") is not False)


def control_rating_row(name: str, d: dict, listing: dict) -> dict:
    runs = d["runs"]
    eff_all = [x.get("effect_ok") for x in runs]
    eff_after = [x.get("effect_after_ok") if x.get("effect_after_ok") is not None else x.get("effect_ok")
                 for x in runs]
    eff_before = [x.get("effect_before_ok") for x in runs]
    held_runs = [x.get("held_through_start") for x in runs]
    fixed_held = [fc.get("held_through_start") for x in runs for fc in (x.get("fixed_controls") or {}).values()]
    workaround = None
    if all(eff_after) and any(h is False for h in held_runs):
        workaround = ("a value set before the stream starts reads back but is reset at stream start (seen at the "
                      "first in-stream readback); re-apply it after the stream has started (tested >= 1 s after "
                      "the first frame)")
    elif all(eff_after) and not all(e is not False for e in eff_before):
        workaround = ("a value set before the stream starts reads back but does not reach the image; "
                      "re-apply it after the stream has started (tested >= 1 s after the first frame)")
    pers = d.get("persistence") or {}
    return {"name": name, "listed": listing.get("listed"),
            "range_matches_descriptor": listing.get("range_matches_descriptor"),
            "listing_source": listing.get("source"),
            "set_readback_ok": all(x.get("before_start_readback") and x.get("after_start_readback")
                                   for x in runs) if runs else None,
            "effect_ok": (all(eff_after) if all(e is not None for e in eff_after) else None),
            "effect_all_segments_ok": (all(eff_all) if all(e is not None for e in eff_all) else None),
            "held_through_start": _all_held(*held_runs) if runs else None,
            "fixed_controls_held_through_start": _all_held(*fixed_held) if fixed_held else None,
            "before_start_ok": all(x.get("before_start_readback") for x in runs)
            and all(e is not False for e in eff_before) and all(h is not False for h in held_runs),
            "after_start_ok": all(x.get("after_start_readback") for x in runs) and all(eff_after),
            "runs_ok": sum(1 for x in runs if run_counts_ok(x)), "runs_total": len(runs),
            "persisted_after_reopen": pers.get("persisted", d.get("persisted_after_reopen")),
            "readback_after_reopen_ok": d.get("persisted_after_reopen") if "persistence" in d else None,
            "workaround": workaround}


def path_verdict(pres: dict, listing_for, nruns: int) -> dict:
    """G-CTRL verdict of one camera path from its record (live or stored)."""
    if pres.get("gate_verdict"):
        v = dict(pres["gate_verdict"])
    elif pres.get("scope_verdict"):
        v = dict(pres["scope_verdict"])
    elif pres.get("gate_fault"):
        v = rating.device_fault_untested(pres["gate_fault"])
    elif (pres.get("device_not_answering") or {}).get("kind") == "capture_fault":
        # a capture fault (device_error / unreleasable reader) during the test, controls still answering: the
        # camera's state, not a control result
        dna = pres["device_not_answering"]
        rc = [control_rating_row(n, d, listing_for(n)) for n, d in pres["controls"].items() if "runs" in d]
        v = rating.device_fault_untested(dna.get("fault") or {"utc": dna.get("utc"), "test": TEST,
                                                               "code": dna.get("hr")},
                                         evidence={"controls_before_fault": rc})
    elif (pres.get("device_not_answering") or {}).get("at") == "initial_read":
        dna = pres["device_not_answering"]
        v = rating.rate_ctrl([], device_not_answering=True, not_answering_hr=dna.get("hr"))
        v["evidence"]["device_not_answering_detail"] = dna
    else:
        rc = [control_rating_row(n, d, listing_for(n)) for n, d in pres["controls"].items() if "runs" in d]
        dna = pres.get("device_not_answering")
        if dna:     # stopped answering during the test
            v = rating.rate_ctrl(rc, runs_required=3, device_not_answering=True, not_answering_hr=dna.get("hr"))
            v["evidence"]["device_not_answering_detail"] = dna
        else:
            v = rating.rate_ctrl(rc, runs_required=3) if rc else rating.untested("no settable control on this path",
                                                                                 {"skipped": pres["controls"]})
        if rc and nruns < 3:
            v["note"] = ((v.get("note") or "") + f" only {nruns} run(s) per control (quick)").strip()
    v["restore"] = (pres.get("restore") or {}).get("restored")
    return v


# ------------------------------------------------------------------------------------------------------- run
def run(ctx) -> dict:
    res = ck.new_result(ctx, TEST)
    arr0 = ck.arrivals_before(ctx)
    nruns = runs_per(ctx)
    errors: list = []
    verdicts: dict = {}
    per_cam: dict = {}
    cache: dict = {}
    raw = Path(ctx.raw_dir) / TEST
    tdir = ctx.test_dir(TEST)
    ctrl_list = load_ctrl_list(Path(ctx.out_dir) / "W-CTRL-LIST.json")
    for cam in ctx.cameras:
        slug = ck.cam_slug(cam)
        cres: dict = {"name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"), "paths": {}}
        gf = gate_fault(ctx, cam)
        if gf:
            ctx.log(f"{TEST}: {cam.get('name')}: skipped, device fault since "
                    f"{gf.get('first_fault_utc') or gf.get('utc')} (dead-device gate)")
            gv = gate_untested(ctx, cam, gf)
            for api in ("mf", "ds"):
                cres["paths"][api] = {"gate_fault": gf, "gate_verdict": gv, "controls": {}}
                verdicts[f"G-CTRL|{cam['key']}|{api}"] = path_verdict(cres["paths"][api], lambda n: {}, nruns)
            per_cam[cam["key"]] = cres
            continue
        fm, _ = ck.get_formats(ctx, cam, cache)
        advertised = ck.mjpeg_modes(fm)
        # mode scope (common/modescope.py): 1280x720@30 MJPEG, else the nearest in-scope MJPEG mode
        mode, scope = ck.scoped_default(ctx, advertised)
        cres["mode"] = mode.text if mode else None
        cres["mode_scope"] = scope
        scope_out = mode is None and bool(advertised)
        # the camera's control state as FIRST read in this test (either path; both reach the same usbvideo
        # property sets). Restores use it, so a failed restore after the MF path is not baked in as the "original"
        # of the DS path (review 2026-11-06).
        cam_orig: dict[str, dict] = {}
        tabs: dict[str, dict] = {}
        dead: dict | None = None
        for api in ("mf", "ds"):
            if (api == "mf" and not cam.get("mf_symlink")) or (api == "ds" and not cam.get("ds_path")):
                continue
            pres: dict = {"controls": {}}
            cres["paths"][api] = pres
            if dead:
                pres["device_not_answering"] = dict(dead, at="earlier path")
                pres["controls"] = {n: {"skipped": f"device not answering since {dead['utc']}: {dead['hr']}"}
                                    for n in CONTROLS}
                continue
            initial, run0 = ck.get_controls(ctx, cam, api)
            pres["initial_read"] = run0
            if initial is not None:
                pres["initial_read_file"] = str(results.write_json(tdir / f"{slug}_initial_{api}.json", initial)
                                                .relative_to(ctx.out_dir)).replace("\\", "/")
            na, hr = not_answering(initial, run0)
            if na:
                dead = {"hr": hr, "utc": results.utc_now_iso(), "api": api, "at": "initial_read",
                        "failed_controls": (initial or {}).get("get_failed_controls")}
                pres["device_not_answering"] = dead
                pres["controls"] = {n: {"skipped": f"device not answering: {hr}"} for n in CONTROLS}
                ctx.log(f"{TEST}: {cam.get('name')} {api}: device not answering ({hr}); camera skipped")
                gate_report(ctx, cam, mode.text if mode else None, hr, f"{api} control GETs failed", api)
                continue
            ierr = (initial or {}).get("error") or {}
            if ierr or initial is None:
                why = (f"control path failed: {ierr.get('class')} {ierr.get('hr') or ierr.get('hr_name')} at "
                       f"{ierr.get('stage')}" if ierr else f"no controls JSON (rc={run0.get('rc')})")
                pres["controls"] = {n: {"skipped": why} for n in CONTROLS}
                errors.append({"camera": cam["key"], "api": api, "initial_read_error": ierr or run0})
                continue
            if mode is None:
                if scope_out:
                    pres["scope_verdict"] = ck.scope_untested(ctx, scope)
                    pres["controls"] = {n: {"skipped": scope.get("untested_reason")} for n in CONTROLS}
                else:
                    pres["controls"] = {n: {"skipped": "no MJPEG mode"} for n in CONTROLS}
                continue
            tab = ck.control_table(initial)
            tabs[api] = tab
            for n_, c_ in tab.items():
                cam_orig.setdefault(n_, c_)
            touched: dict[str, dict] = {}
            try:
                for name in CONTROLS:
                    if dead:
                        pres["controls"][name] = {"skipped": f"device not answering since {dead['utc']}"}
                        continue
                    c = tab.get(name)
                    if c is not None and not control_answered(c):
                        pres["controls"][name] = {"skipped": f"device did not answer this control's GET: {_get_hr(c)}"}
                        continue
                    if c is None or not manual_capable(c):
                        pres["controls"][name] = {"skipped": "not supported" if c is None else "no manual mode"}
                        continue
                    if api == "ds" and ck.quick(ctx) and name != "exposure":
                        pres["controls"][name] = {"skipped": "quick run: DS path tests exposure only"}
                        continue
                    vals = values_for(name, c)
                    if not vals:
                        pres["controls"][name] = {"skipped": f"degenerate range {c.get('min')}..{c.get('max')}"}
                        continue
                    fix, fix_steps = {}, {}
                    mine = {name: c}
                    if name == "gain" and "exposure" in tab and manual_capable(tab["exposure"]):
                        e = tab["exposure"]
                        fix["exposure"] = _snap((e["min"] + e["max"]) / 2, e)
                        fix_steps["exposure"] = e
                        mine["exposure"] = e
                    touched.update(mine)
                    # a value set with manual flags turns the control's auto mode off (AF off for focus)
                    runs = []
                    for k in range(nruns):
                        st, (na, hr), st_run = _state(ctx, cam, api)
                        if na:
                            dead = {"hr": hr, "utc": results.utc_now_iso(), "api": api,
                                    "at": f"before {name} run {k}"}
                            ctx.log(f"{TEST}: {cam.get('name')} {api}: device stopped answering ({hr})")
                            gate_report(ctx, cam, mode.text, hr, f"{api} control GETs failed before {name} run {k}",
                                        api)
                            break
                        od = raw / slug / f"{api}_{name}_r{k}"
                        try:
                            rr = (run_mf if api == "mf" else run_ds)(ctx, cam, name, vals, fix, od, mode,
                                                                     step=c, fix_steps=fix_steps)
                        except Exception as e:  # noqa: BLE001
                            rr = {"exception": repr(e)}
                            errors.append({"camera": cam["key"], "api": api, "control": name, "exception": repr(e)})
                        rr["state_at_start"] = st
                        rr["state_read"] = {k2: st_run.get(k2) for k2 in ("rc", "elapsed_s", "timed_out")}
                        runs.append(rr)
                        # a capture that hit a device fault (camcmd marks it on the suite gate): stop this camera
                        fnow = gate_fault(ctx, cam, gated_only=False)
                        if fnow or (rr.get("error") or {}).get("class") == "device_error":
                            fnow = fnow or {"utc": results.utc_now_iso(), "test": TEST, "mode": mode.text,
                                            "code": (rr.get("error") or {}).get("hr"), "kind": "device_error"}
                            dead = {"hr": fnow.get("code"), "utc": fnow.get("utc") or results.utc_now_iso(),
                                    "api": api, "at": f"{name} run {k}", "kind": "capture_fault", "fault": fnow}
                            ctx.log(f"{TEST}: {cam.get('name')} {api} {name}: device fault during the capture "
                                    f"({fnow.get('kind')} {fnow.get('code')}); remaining work on this camera skipped")
                            break
                    rec: dict = {"range": {k: c.get(k) for k in ("min", "max", "step", "default")},
                                 "original": {"value": c.get("value"), "flags": c.get("flags_names")},
                                 "values": vals, "runs": runs}
                    if not dead and runs:
                        # persistence: fresh open without streaming (readback), then a short capture (B5)
                        pj, _ = ck.get_controls(ctx, cam, api)
                        pc = ck.control_table(pj).get(name) or {}
                        rec["persisted_after_reopen"] = (held(pc.get("value"), None, vals[-1], c) and
                                                         "manual" in (pc.get("flags_names") or [])) if pj else None
                        rec["readback_after_reopen"] = {"value": pc.get("value"), "flags": pc.get("flags_names")}
                        last = runs[-1].get("metric_values") or []
                        # through the leg's own path: MF capture for the MF leg, DirectShow capture for the DS leg
                        check = persistence_check if api == "mf" else persistence_check_ds
                        rec["persistence"] = check(ctx, cam, name, vals, c, mode,
                                                   raw / slug / f"{api}_{name}_persist", last[-1] if last else None)
                    ok_runs = sum(1 for x in runs if run_counts_ok(x))
                    ok_runs_after = sum(1 for x in runs if (x.get("effect_after_ok") or (x.get("effect_after_ok") is None
                                                                                         and x.get("effect_ok")))
                                        and x.get("after_start_readback"))
                    rec.update(runs_ok=ok_runs, runs_ok_after_start_only=ok_runs_after, runs_total=len(runs))
                    # V1: restore what this control test touched before the next control test
                    if not dead:
                        orig = {n: cam_orig.get(n, cc) for n, cc in mine.items()}
                        try:
                            rec["restore"] = restore_verified(ctx, cam, api, orig, errors, name)
                        except Exception as e:  # noqa: BLE001
                            rec["restore"] = {"exception": repr(e)}
                            errors.append({"camera": cam["key"], "api": api, "control": name,
                                           "restore_exception": repr(e)})
                    pres["controls"][name] = rec
                    ctx.log(f"{TEST}: {cam.get('name')} {api} {name} {vals}: effect "
                            f"{[x.get('effect_ok') for x in runs]} readback "
                            f"{[(x.get('before_start_readback'), x.get('after_start_readback')) for x in runs]} "
                            f"held {[x.get('held_through_start') for x in runs]} persisted "
                            f"{(rec.get('persistence') or {}).get('persisted')}")
            finally:
                if touched and not dead:
                    try:
                        orig = {n: cam_orig.get(n, c) for n, c in touched.items()}
                        pres["restore"] = restore_verified(ctx, cam, api, orig, errors, "path end")
                    except Exception as e:  # noqa: BLE001
                        pres["restore"] = {"exception": repr(e)}
                        errors.append({"camera": cam["key"], "api": api, "restore_exception": repr(e)})
                elif touched and dead:
                    pres["restore"] = {"skipped": f"device not answering since {dead['utc']}", "restored": None}
            if dead and not pres.get("device_not_answering"):
                pres["device_not_answering"] = dead
        # ratings after both paths (criterion 1 may need both paths' reads when W-CTRL-LIST is missing)
        cl = ctrl_list.get(cam["key"])
        cres["listing_source"] = "W-CTRL-LIST" if cl else "own MF/DS reads"
        for api, pres in cres["paths"].items():
            verdicts[f"G-CTRL|{cam['key']}|{api}"] = path_verdict(
                pres, lambda n, _cl=cl: listing_inputs(_cl, n, tabs), nruns)
        per_cam[cam["key"]] = cres
    meas = {"runs_per_control": nruns, "quick": ck.quick(ctx), "save_every": SAVE_EVERY, "cameras": per_cam,
            "arrivals": ck.arrivals_after(ctx, arr0),
            "note": "criterion 1 (listed, MF/DS ranges equal) comes from W-CTRL-LIST per_control; frames stay in "
                    "raw_dir; held_through_start uses a one-step tolerance"}
    return results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)


# ------------------------------------------------------------------------------------------------------- offline
def reanalyze(run_dir: Path) -> dict:
    """Re-rate a stored W-CTRL-EFFECT.json without a camera: criterion 1 from W-CTRL-LIST.json, held-through-start
    from the stored MF schedule readbacks (DS: not stored -> None), and paths where EVERY control was skipped as
    'no manual mode' (the empty caps field of a camera whose GETs fail; B1) re-rated as device not answering, with
    the W-KIYO poll evidence when present. Stored run records are not changed."""
    run_dir = Path(run_dir)
    d = json.loads((run_dir / "W-CTRL-EFFECT.json").read_text(encoding="utf-8"))
    cl = load_ctrl_list(run_dir / "W-CTRL-LIST.json")
    kiyo = {}
    try:
        kj = json.loads((run_dir / "W-KIYO.json").read_text(encoding="utf-8"))
        kiyo = {"verdicts": {k: {"rating": v.get("rating"), "note": v.get("note")} for k, v in
                             (kj.get("verdicts") or {}).items() if isinstance(v, dict)}}
    except (OSError, ValueError):
        pass
    m = d.get("measurements") or {}
    nruns = m.get("runs_per_control") or 3
    out_v, changes, notes = {}, [], {}
    for key, cres in (m.get("cameras") or {}).items():
        for api, pres in (cres.get("paths") or {}).items():
            pres = json.loads(json.dumps(pres))
            ctrls = pres.get("controls") or {}
            for name, rec in ctrls.items():
                for rr in rec.get("runs") or []:
                    if "held_through_start" in rr:
                        continue
                    if rr.get("path") == "mf":
                        rr.update(mf_held_from_record(rr, name, rec.get("range") or {}))
                    else:
                        rr["held_through_start"] = None
                        rr["held_note"] = "DS set records of this run did not keep before_value"
            skipped = [x.get("skipped") for x in ctrls.values()]
            if ctrls and all(s == "no manual mode" for s in skipped):
                pres["device_not_answering"] = {
                    "at": "initial_read", "hr": None, "inferred": True,
                    "why": "every control listed as supported but with an empty caps field: wincam fills caps only "
                           "from a successful KS GET when IAM GetRange fails, i.e. every GET failed (ctrl_id_env B1); "
                           "the initial read JSON was not saved, so the HRESULT is unknown (W-KIYO's code was the "
                           "old 'not called' default 0x80004002)",
                    "w_kiyo": kiyo or None}
            v = path_verdict(pres, lambda n, _c=cl.get(key): listing_inputs(_c, n), nruns)
            vk = f"G-CTRL|{key}|{api}"
            old = (d.get("verdicts") or {}).get(vk, {}).get("rating")
            out_v[vk] = v
            notes[vk] = {"original": old, "reanalysed": v["rating"],
                         "held_through_start": {n: [rr.get("held_through_start") for rr in (x.get("runs") or [])]
                                                for n, x in ctrls.items() if "runs" in x}}
            if old != v["rating"]:
                changes.append({"cell": vk, "from": old, "to": v["rating"]})
    caveats = ["V1 (state carry-over between control tests) cannot be undone offline: C930e MF WB runs 1-2 ran with "
               "gain 230 manual left by the gain test (luma ~209, verifier F10); their 1.0531 ratio stays counted",
               "persistence by short capture (B5) and in-stream re-apply of fixed controls (B4) need a re-run",
               "DS held-through-start needs a re-run (set1 before_value was not stored)"]
    return {"test": TEST, "reanalysis_of": str(run_dir / "W-CTRL-EFFECT.json"), "utc": results.utc_now_iso(),
            "verdicts": out_v, "changes": changes, "cells": notes, "caveats": caveats,
            "fixes_applied": ["B1 device not answering -> no (inferred for all-'no manual mode' paths)",
                              "B3 held through start (MF, one-step tolerance) in before_start_ok / runs_ok",
                              "B6 criterion 1 from W-CTRL-LIST (listed + MF/DS ranges equal)"]}


def _main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "--ds-leg":
        return ds_leg_main(argv[1])
    if len(argv) >= 2 and argv[0] == "--reanalyze":
        rd = Path(argv[1])
        out = reanalyze(rd)
        p = results.write_json(rd / "reanalysis" / f"{TEST}.json", out)
        print(json.dumps({"written": str(p), "changes": out["changes"]}, indent=1))
        return 0
    print("usage: w_ctrl_effect.py --reanalyze <run_dir>   (live runs go through run_suite.py)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
