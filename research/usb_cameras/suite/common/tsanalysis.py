"""Per-frame timestamp analysis for G-TS (stdlib only, any OS).

    from common import tsanalysis as ts
    g = ts.grid_analysis(times_ns)                       # quantisation step (e.g. 15.625 / 16 ms), interval histogram
    f = ts.fit_frame_index(arrival_ns, causal=True)      # t = offset + period * n, n = frame slot (slot_frames)
    s = ts.slot_frames(times_ns)                         # slots from the measured period: sequence or incremental
    c = ts.fit_device_clock(pts_ticks, host_ns, clock_hz, causal=False)   # UVC PTS -> host time, 32-bit wrap
    d = ts.detect_drops(pts_or_seq, period)              # gaps in a sequence counter or a periodic clock
    y = ts.synthesized_check(pts_ns, arrival_ns)         # host-API timestamps made up from a counter?
    m = ts.modes_report(latency_ms)                      # per-mode shares of a (bimodal) latency, no median

Tier 0 only (Dom 2026-11-09): the UVC SCR / SOF analysis (analyse_uvc_scr, sof_rate), the device-counter units check
(clock_units_check) and the device-stamp regularity check were removed with the Windows W-TS UVC PTS/SCR sources.
fit_device_clock stays because the Linux suite's l_ts still calls it.

Frame slots never come from the nominal period (a camera can run at 25.7 fps in a "30 fps" mode): see
slot_frames. Changes after results/windows/Gerald/suite_20261106T181941Z/analysis/ts.md (B2, B3, B5, B7, B8, V5).

Methods follow tools/analyze_frames.py (periodic fit with integer frame slots, lower-envelope offset because
arrival = capture + a positive latency, 32-bit PTS unwrap) and timing/scripts/flash_verify_method.py (a *causal*
estimate for frame i uses frames 0..i only: what a live system could compute). They are rewritten here without
numpy so the suites' common code has no third-party dependency.

All times are integers or floats in ns unless the name says otherwise. Statistics dicts have
{n, mean, std, min, max, median, p05, p95} (std is the sample standard deviation).
"""
from __future__ import annotations

import cmath
import math
from collections import Counter
from typing import Any, Iterable, Sequence

KNOWN_STEPS_MS = {
    "windows_timer_15.625ms": 15.625,
    "16ms": 16.0,
    "1ms_usb_frame": 1.0,
    "4ms": 4.0,
    "0.125ms_usb_microframe": 0.125,
}


# ---------------------------------------------------------------------------------------------------- helpers
def _percentile(sorted_vals: Sequence[float], q: float) -> float:
    if not sorted_vals:
        return math.nan
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def stats(values: Iterable[float], scale: float = 1.0) -> dict[str, Any]:
    """{n, mean, std, min, max, median, p05, p95, rms} of values * scale ({} if empty; NaNs dropped)."""
    v = [float(x) * scale for x in values if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not v:
        return {"n": 0}
    n = len(v)
    mean = sum(v) / n
    std = math.sqrt(sum((x - mean) ** 2 for x in v) / (n - 1)) if n > 1 else 0.0
    s = sorted(v)
    return {"n": n, "mean": mean, "std": std, "min": s[0], "max": s[-1], "median": _percentile(s, 0.5),
            "p05": _percentile(s, 0.05), "p95": _percentile(s, 0.95),
            "rms": math.sqrt(sum(x * x for x in v) / n)}


def linfit(x: Sequence[float], y: Sequence[float]) -> tuple[float, float]:
    """Least squares y = a + b*x. Returns (a, b). Needs >= 2 distinct x."""
    n = len(x)
    if n < 2:
        raise ValueError("need at least two points")
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx == 0:
        raise ValueError("x has no spread")
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    b = sxy / sxx
    return my - b * mx, b


class _RunningFit:
    """Incremental least squares y = a + b*x (x, y shifted by the first point for numerical stability)."""

    def __init__(self) -> None:
        self.n = 0
        self.sx = self.sy = self.sxx = self.sxy = 0.0
        self.x0 = self.y0 = None

    def add(self, x: float, y: float) -> None:
        if self.x0 is None:
            self.x0, self.y0 = x, y
        dx, dy = x - self.x0, y - self.y0
        self.n += 1
        self.sx += dx
        self.sy += dy
        self.sxx += dx * dx
        self.sxy += dx * dy

    def coef(self) -> tuple[float, float] | None:
        if self.n < 2:
            return None
        d = self.n * self.sxx - self.sx * self.sx
        if d == 0:
            return None
        b = (self.n * self.sxy - self.sx * self.sy) / d
        a = (self.sy - b * self.sx) / self.n
        # back to absolute coordinates: y = y0 + a + b (x - x0)
        return self.y0 + a - b * self.x0, b


def unwrap(values: Sequence[int], bits: int = 32) -> list[int]:
    """Unwrap a counter that rolls over at 2**bits (successive samples less than half the range apart)."""
    if not values:
        return []
    m = 1 << bits
    out = [int(values[0])]
    for prev, cur in zip(values, values[1:]):
        d = (int(cur) - int(prev) + m // 2) % m - m // 2
        out.append(out[-1] + d)
    return out


def _lower_envelope_shift(residuals: Sequence[float], q: float = 0.02) -> float:
    """Offset that moves a fitted line onto the lower envelope of the data (arrival = capture + latency >= 0)."""
    s = sorted(residuals)
    return _percentile(s, q) if s else 0.0


# ---------------------------------------------------------------------------------------------------- grid
def _cluster(values_ms: Sequence[float], tol_ms: float) -> list[dict[str, float]]:
    s = sorted(values_ms)
    clusters: list[list[float]] = []
    for v in s:
        if clusters and v - clusters[-1][-1] <= tol_ms:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    n = len(s)
    return [{"ms": sum(c) / len(c), "count": len(c), "share": len(c) / n} for c in clusters]


def _phase_concentration(times_ns: Sequence[float], step_ns: float) -> float:
    """|mean(exp(2 pi i t / step))|: 1.0 when every timestamp sits on one grid of this step."""
    if step_ns <= 0 or not times_ns:
        return 0.0
    t0 = times_ns[0]
    acc = sum(cmath.exp(2j * math.pi * ((t - t0) % step_ns) / step_ns) for t in times_ns)
    return abs(acc) / len(times_ns)


def grid_analysis(times_ns: Sequence[float], tol_ms: float = 0.3, bin_ms: float = 0.1,
                  min_share: float = 0.03, nominal_period_ns: float | None = None) -> dict[str, Any]:
    """Detect a quantisation grid in timestamps (e.g. Windows' 15.625/16 ms host-time grid that makes an MF or
    DirectShow timestamp useless at 30 fps) and histogram the frame intervals.

    Method: cluster the intervals (tolerance ``tol_ms``); with two or more populated clusters, look for the
    largest step q whose integer multiples explain >= 95% of the intervals (candidates: cluster centres and their
    differences divided by 1..8), then confirm that the absolute times sit on one grid of step q (phase
    concentration >= 0.9). Known steps (KNOWN_STEPS_MS) are also tested on the absolute times; a step that divides
    the frame period is reported but flagged ``ambiguous_with_period``. A step equal to the frame period (gaps
    are dropped frames) is not a grid (``period_multiples``); pass ``nominal_period_ns`` (1e9 / requested fps) to
    tell a coarse grid near the frame period (60 fps on 16 ms) from drops.

    Returns {"n", "interval_ms": stats, "histogram": [{"ms", "count"}], "clusters": [{"ms","count","share"}],
             "quantized": bool, "step_ms": float|None, "on_grid_fraction", "phase_concentration",
             "known_step": name|None, "ambiguous_with_period": bool, "known_steps": {name: concentration}}
    """
    t = [float(x) for x in times_ns if x is not None]
    out: dict[str, Any] = {"n": len(t), "quantized": False, "step_ms": None, "on_grid_fraction": None,
                           "phase_concentration": None, "known_step": None, "ambiguous_with_period": False}
    if len(t) < 3:
        return out
    iv = [(b - a) / 1e6 for a, b in zip(t, t[1:])]
    out["interval_ms"] = stats(iv)
    hist: dict[float, int] = {}
    for v in iv:
        k = round(round(v / bin_ms) * bin_ms, 6)
        hist[k] = hist.get(k, 0) + 1
    out["histogram"] = [{"ms": k, "count": c} for k, c in sorted(hist.items())]
    clusters = [c for c in _cluster(iv, tol_ms) if c["share"] >= min_share]
    out["clusters"] = clusters
    median_iv = out["interval_ms"]["median"]
    best = None
    if len(clusters) >= 2:
        centres = [c["ms"] for c in clusters if c["ms"] > tol_ms]
        cands = set()
        for c in centres:
            for k in range(1, 9):
                cands.add(round(c / k, 4))
        for a in centres:
            for b in centres:
                if b > a + tol_ms:
                    for k in range(1, 5):
                        cands.add(round((b - a) / k, 4))
        for q in sorted(cands, reverse=True):
            if q < max(2 * tol_ms, 0.1) or q > min(centres) * 1.02:
                continue
            on = sum(1 for v in iv if v > tol_ms and abs(v / q - round(v / q)) * q <= tol_ms
                     and round(v / q) >= 1) / len(iv)
            if on >= 0.95:
                best = (q, on)
                break
    known = {}
    for name, q in KNOWN_STEPS_MS.items():
        known[name] = round(_phase_concentration(t, q * 1e6), 4)
    out["known_steps"] = known
    if best:
        ref = (nominal_period_ns / 1e6) if nominal_period_ns else median_iv
        tol = 0.02 if nominal_period_ns else 0.05
        if ref > 0 and abs(best[0] - ref) / ref < tol:
            # intervals are whole multiples of the frame period itself: dropped frames, not a timestamp grid.
            # (Without nominal_period_ns a 60 fps stream on a 16 ms grid looks the same: flagged ambiguous.)
            out["period_multiples"] = True
            out["ambiguous_with_period"] = not nominal_period_ns
            best = None
    if best:
        q, on = best
        # snap to a known step when within tolerance
        for name, kq in KNOWN_STEPS_MS.items():
            if abs(kq - q) <= tol_ms / 2:
                q = kq
                out["known_step"] = name
                break
        pc = _phase_concentration(t, q * 1e6)
        out.update(step_ms=q, on_grid_fraction=round(on, 4), phase_concentration=round(pc, 4),
                   quantized=pc >= 0.9)
    else:
        # single interval cluster: absolute times may still sit on a fine grid (e.g. 1 ms URB completions).
        # The period used to judge "step divides the frame period" is the nominal one when given: the median
        # interval of gridded times is itself a grid multiple (32 ms on a 16 ms grid), so it would always look
        # ambiguous (analysis ts.md B8).
        period_ms = (nominal_period_ns / 1e6) if nominal_period_ns else median_iv
        for name, q in sorted(KNOWN_STEPS_MS.items(), key=lambda kv: -kv[1]):
            if q >= median_iv * 0.9:
                continue
            pc = known[name]
            if pc >= 0.9:
                ratio = period_ms / q
                amb = abs(ratio - round(ratio)) < 0.02
                out.update(step_ms=q, known_step=name, phase_concentration=pc, quantized=True,
                           ambiguous_with_period=amb, on_grid_fraction=None)
                break
    return out


# ---------------------------------------------------------------------------------------------------- frame index
def _fit_residual_std(slots: Sequence[int], t: Sequence[float]) -> float:
    try:
        a, b = linfit(slots, [x - t[0] for x in t])
    except ValueError:
        return math.inf
    r = [x - t[0] - (a + b * s) for x, s in zip(t, slots)]
    m = sum(r) / len(r)
    return math.sqrt(sum((v - m) ** 2 for v in r) / max(1, len(r) - 1))


def _auto_grid_ms(t: Sequence[float], nominal_period_ns: float | None) -> float | None:
    """Quantisation step of the timestamps themselves (None if not on a grid)."""
    iv = sorted(b - a for a, b in zip(t, t[1:]))
    ref = nominal_period_ns or (_percentile(iv, 0.5) if iv else None)
    g = grid_analysis(t, nominal_period_ns=ref)
    return g.get("step_ms") if g.get("quantized") else None


def slot_frames(times_ns: Sequence[float], grid_ms: float | None = None, gap_factor: float = 1.5,
                nominal_period_ns: float | None = None, max_iter: int = 10) -> dict[str, Any]:
    """Integer frame slots n_i for the timestamps of a periodic stream that may have dropped frames.

    The nominal period is never used as the seed (a camera that runs at 25.7 fps in a "30 fps" mode would be
    mis-slotted; analysis ts.md B2). Method:
    1. p = span / (N - 1), i.e. assume no gaps.
    2. A gap is an interval > ``gap_factor`` * p. Gaps are only trusted when they are detectable at all: the
       timestamp grid (``grid_ms``; auto-detected when None) must be finer than half the period
       (``drops_detectable = p > 2 * grid``). At 60 fps on a 16 ms grid a 32 ms interval is not a drop.
    3. No (trusted) gap: slots are the sequence 0..N-1 (the whole-span method; ``slotting = "sequence"``).
    4. Gaps: incremental slotting n_i = n_(i-1) + max(1, round(dt_i / p)), with p re-estimated as span / n_last
       until the slots stop changing. Local intervals are used, so a slope error cannot accumulate the way a
       global round((t - t0) / p) does under a 16 ms jitter. The incremental slotting is kept only if it lowers
       the whole-run residual of the linear fit against the sequence slotting (a real drop leaves a step in the
       sequence-slot residuals; phantom gaps from late/early arrivals leave a step in the incremental ones).

    Returns {"slots", "period_ns", "slotting", "gaps_found", "drops_detectable", "grid_ms", "gap_threshold_ns",
             "rejected_gap_slots", "iterations"}.
    """
    t = [float(x) for x in times_ns]
    n = len(t)
    out: dict[str, Any] = {"n": n, "slots": list(range(n)), "period_ns": None, "slotting": "sequence",
                           "gaps_found": 0, "drops_detectable": None, "grid_ms": grid_ms,
                           "gap_threshold_ns": None, "rejected_gap_slots": 0, "iterations": 0}
    if n < 2:
        return out
    span = t[-1] - t[0]
    if span <= 0:
        raise ValueError("timestamps do not increase")
    p = span / (n - 1)
    if grid_ms is None and n >= 3:
        grid_ms = _auto_grid_ms(t, nominal_period_ns)
        out["grid_ms"] = grid_ms
        out["grid_auto"] = True
    detectable = True if grid_ms is None else p > 2.0 * grid_ms * 1e6
    out["drops_detectable"] = detectable
    out["period_ns"] = p
    out["gap_threshold_ns"] = gap_factor * p
    iv = [b - a for a, b in zip(t, t[1:])]
    gaps = sum(1 for d in iv if d > gap_factor * p)
    out["gaps_found"] = gaps
    if gaps == 0 or not detectable:
        if gaps and not detectable:
            out["gaps_ignored_not_detectable"] = gaps
        return out
    slots = list(range(n))
    it = 0
    for it in range(1, max_iter + 1):
        new = [0]
        for d in iv:
            new.append(new[-1] + max(1, int(round(d / p))))
        changed = new != slots
        slots = new
        p = span / slots[-1]
        if not changed:
            break
    out["iterations"] = it
    seq_std = _fit_residual_std(list(range(n)), t)
    inc_std = _fit_residual_std(slots, t)
    out["residual_std_ms"] = {"sequence": seq_std / 1e6, "incremental": inc_std / 1e6}
    if inc_std < seq_std:
        out.update(slots=slots, period_ns=p, slotting="incremental")
    else:
        out["slotting"] = "sequence (incremental rejected)"
        out["rejected_gap_slots"] = slots[-1] - (n - 1)
    return out


def fit_frame_index(arrival_ns: Sequence[float], causal: bool = True, nominal_period_ns: float | None = None,
                    min_points: int = 30, window: int | None = None, envelope: bool = True,
                    grid_ms: float | None = None, unreliable_fraction: float = 0.01) -> dict[str, Any]:
    """Frame-index model: estimated capture time t_i = offset + period * n_i, n_i = integer frame slot.

    Slots come from ``slot_frames`` (sequence slots when there is no detectable gap, else incremental slotting
    from local intervals; the period comes from the data, never from the nominal). ``nominal_period_ns`` only
    helps grid detection and is reported as ``rate_vs_nominal_ppm``. ``causal=False``: one least-squares fit over
    the whole run. ``causal=True``: the estimate for frame i uses frames [max(0, i-window+1) .. i] only (running
    sums; frames before ``min_points`` get no estimate). ``envelope``: shift the line onto the lower envelope of
    arrivals (arrival = capture + latency >= 0); without a ground truth this only moves the offset, not the jitter.

    ``fit_unreliable`` is set when skipped + duplicate slots exceed ``unreliable_fraction`` of N, or when gaps
    were seen but could not be told from the timestamp grid.

    Returns {"causal", "period_ns", "fps", "offset_ns", "slots": [n_i], "fitted_ns": [t_i|None],
             "residuals_ns": [arrival - t_i|None], "residual_stats_ms", "slots_skipped", "duplicate_slots",
             "n_estimated", "slotting", "drops_detectable", "grid_ms", "fit_unreliable", "unreliable_reasons"}.
    With a ground truth gt_i, error = fitted_ns - gt_i (compare with rating.rate_ts).
    """
    t = [float(x) for x in arrival_ns]
    if len(t) < 3:
        return {"causal": causal, "error": "too few frames", "n": len(t)}
    sl = slot_frames(t, grid_ms=grid_ms, nominal_period_ns=nominal_period_ns)
    slots = sl["slots"]
    p = sl["period_ns"]
    t0 = t[0]
    fitted: list[float | None] = [None] * len(t)
    if not causal:
        a, b = linfit(slots, [x - t0 for x in t])
        res = [x - t0 - (a + b * s) for x, s in zip(t, slots)]
        shift = _lower_envelope_shift(res) if envelope else 0.0
        fitted = [t0 + a + shift + b * s for s in slots]
        period, offset = b, t0 + a + shift
    else:
        rf = _RunningFit()
        hist: list[tuple[float, float]] = []
        min_res = math.inf
        period, offset = p, t0
        for i, (x, s) in enumerate(zip(t, slots)):
            rf.add(float(s), x - t0)
            hist.append((float(s), x - t0))
            if window and len(hist) > window:
                rf = _RunningFit()
                hist = hist[-window:]
                for hs, hx in hist:
                    rf.add(hs, hx)
            co = rf.coef()
            if co is None or i + 1 < min_points:
                continue
            a, b = co
            r = x - t0 - (a + b * s)
            if envelope:
                # causal lower envelope: running minimum of residuals of past frames against the current line
                # (approximated by the running min of each frame's residual when it arrived)
                min_res = min(min_res, r)
                shift = min_res
            else:
                shift = 0.0
            fitted[i] = t0 + a + shift + b * s
            period, offset = b, t0 + a + shift
    residuals = [None if f is None else x - f for x, f in zip(t, fitted)]
    gaps = [b - a for a, b in zip(slots, slots[1:])]
    skipped = sum(g - 1 for g in gaps if g > 1)
    dup = sum(1 for g in gaps if g == 0)
    reasons = []
    if skipped + dup > unreliable_fraction * len(t):
        reasons.append(f"skipped + duplicate slots ({skipped + dup}) > {unreliable_fraction:.0%} of {len(t)} frames")
    if sl.get("gaps_ignored_not_detectable"):
        reasons.append(f"{sl['gaps_ignored_not_detectable']} long intervals but the timestamp grid "
                       f"({sl.get('grid_ms')} ms) cannot separate one period from two: drops not detectable")
    if sl.get("rejected_gap_slots", 0) > unreliable_fraction * len(t):
        reasons.append(f"incremental slotting found {sl['rejected_gap_slots']} gap slots that did not lower the "
                       "residual (rejected): arrivals too irregular to place frames")
    fps = 1e9 / period if period else None
    return {"causal": causal, "period_ns": period, "fps": fps, "offset_ns": offset,
            "slots": slots, "fitted_ns": fitted, "residuals_ns": residuals,
            "residual_stats_ms": stats([r for r in residuals if r is not None], 1e-6),
            "slots_skipped": skipped, "duplicate_slots": dup,
            "n_estimated": sum(1 for f in fitted if f is not None), "n": len(t),
            "slotting": sl["slotting"], "gaps_found": sl["gaps_found"], "drops_detectable": sl["drops_detectable"],
            "grid_ms": sl.get("grid_ms"), "slotting_residual_std_ms": sl.get("residual_std_ms"),
            "nominal_period_ns": nominal_period_ns,
            "rate_vs_nominal_ppm": ((nominal_period_ns / period - 1.0) * 1e6) if (nominal_period_ns and period)
            else None,
            "fit_unreliable": bool(reasons), "unreliable_reasons": reasons}


def score_against_truth(estimates_ns: Sequence[float | None], truth_ns: Sequence[float | None],
                        remove_offset: bool = True) -> dict[str, Any]:
    """Error stats (ms) of estimates vs a ground truth (e.g. flash / LED rig), optionally after removing the mean
    offset (a constant pipeline delay is calibratable; the 1-sigma jitter is what rating.rate_ts scores)."""
    pairs = [(e, g) for e, g in zip(estimates_ns, truth_ns) if e is not None and g is not None]
    if not pairs:
        return {"n": 0}
    err = [e - g for e, g in pairs]
    off = sum(err) / len(err) if remove_offset else 0.0
    return {"n": len(err), "offset_ms": off / 1e6, "error_ms": stats([x - off for x in err], 1e-6)}


# ---------------------------------------------------------------------------------------------------- device clock
def fit_device_clock(pts_ticks: Sequence[int], host_ns: Sequence[float], clock_hz: float | None,
                     causal: bool = False, bits: int = 32, min_points: int = 30,
                     envelope: bool = True) -> dict[str, Any]:
    """Map a device clock (UVC PTS, dwClockFrequency ticks) to host time: host = a + b * pts_unwrapped.

    The counter is unwrapped at 2**bits (UVC PTS/STC are 32-bit). ``clock_hz``: nominal frequency
    (dwClockFrequency; None -> estimated only). Lower-envelope offset as in analyze_frames.lower_envelope_fit.
    causal=True uses frames 0..i for frame i (running least squares).

    Returns {"causal", "n", "freq_hz_est", "nominal_hz", "ppm_vs_nominal", "mapped_ns": [..|None],
             "residuals_ns", "residual_stats_ms", "pts_zero_fraction", "pts_period_ticks", "monotonic"}.
    """
    pts_raw = [int(x) for x in pts_ticks]
    h = [float(x) for x in host_ns]
    n = min(len(pts_raw), len(h))
    pts_raw, h = pts_raw[:n], h[:n]
    out: dict[str, Any] = {"causal": causal, "n": n, "nominal_hz": clock_hz}
    if n < 3:
        out["error"] = "too few frames"
        return out
    out["pts_zero_fraction"] = sum(1 for x in pts_raw if x == 0) / n
    if out["pts_zero_fraction"] > 0.5:
        out["error"] = "PTS mostly zero (camera does not fill it)"
        return out
    pts = unwrap(pts_raw, bits)
    d = [b - a for a, b in zip(pts, pts[1:])]
    out["monotonic"] = all(x > 0 for x in d)
    out["pts_period_ticks"] = stats(d)
    p0 = float(pts[0])
    x = [float(v) - p0 for v in pts]
    mapped: list[float | None] = [None] * n
    if not causal:
        try:
            a, b = linfit(x, h)
        except ValueError as e:
            out["error"] = str(e)
            return out
        res = [hi - (a + b * xi) for xi, hi in zip(x, h)]
        shift = _lower_envelope_shift(res) if envelope else 0.0
        mapped = [a + shift + b * xi for xi in x]
        slope = b
        # 1-sigma uncertainty of the fitted rate (host arrivals on a 16 ms grid make it ~ +-18 ppm over 30 s)
        mx = sum(x) / n
        sxx = sum((xi - mx) ** 2 for xi in x)
        if n > 2 and sxx > 0 and b:
            s_res = math.sqrt(sum(r * r for r in res) / (n - 2))
            out["freq_ppm_1sigma"] = s_res / math.sqrt(sxx) / abs(b) * 1e6
    else:
        rf = _RunningFit()
        slope = None
        min_res = math.inf
        for i, (xi, hi) in enumerate(zip(x, h)):
            rf.add(xi, hi)
            co = rf.coef()
            if co is None or i + 1 < min_points:
                continue
            a, b = co
            r = hi - (a + b * xi)
            min_res = min(min_res, r) if envelope else 0.0
            mapped[i] = a + (min_res if envelope else 0.0) + b * xi
            slope = b
    if slope:
        f = 1e9 / slope  # ticks per second
        out["freq_hz_est"] = f
        if clock_hz:
            out["ppm_vs_nominal"] = (f - clock_hz) / clock_hz * 1e6
    out["mapped_ns"] = mapped
    out["residuals_ns"] = [None if m is None else hi - m for hi, m in zip(h, mapped)]
    out["residual_stats_ms"] = stats([r for r in out["residuals_ns"] if r is not None], 1e-6)
    return out


# ---------------------------------------------------------------------------------------------------- drops
def detect_drops(pts_or_seq: Sequence[float], period: float | None = None, bits: int | None = None) -> dict:
    """Find gaps. ``period=None``: values are sequence numbers (expected step 1). Otherwise values are timestamps
    on a periodic clock with this period (same unit), and a gap of k periods means k-1 dropped frames.
    ``bits`` unwraps a rolling counter first (e.g. 32 for UVC PTS, 11 for SOF).

    Returns {"n", "drops", "gap_events": [{"index", "missing"}], "duplicates", "backwards", "max_gap"}."""
    v = [int(x) for x in pts_or_seq] if bits else [float(x) for x in pts_or_seq]
    if bits:
        v = unwrap(v, bits)
    step = 1.0 if period is None else float(period)
    events, dup, back, drops, max_gap = [], 0, 0, 0, 0
    for i, (a, b) in enumerate(zip(v, v[1:]), start=1):
        k = round((b - a) / step)
        if k <= 0:
            if b == a or k == 0:
                dup += 1
            else:
                back += 1
            continue
        if k > 1:
            events.append({"index": i, "missing": int(k - 1)})
            drops += int(k - 1)
            max_gap = max(max_gap, int(k - 1))
    return {"n": len(v), "drops": drops, "gap_events": events[:200], "gap_event_count": len(events),
            "duplicates": dup, "backwards": back, "max_gap": max_gap}


# ---------------------------------------------------------------------------------------------------- synthesized
def drift_ms_per_s(ts_ns: Sequence[float], arrival_ns: Sequence[float]) -> float | None:
    """Least-squares slope of (arrival - ts) against arrival, in ms per second. End points are not used: they
    carry the full quantisation noise of a 16 ms grid (analysis ts.md, verifier V2)."""
    pr = [(float(a), float(a) - float(s)) for s, a in zip(ts_ns, arrival_ns) if s is not None and a is not None]
    if len(pr) < 3:
        return None
    x0 = pr[0][0]
    try:
        _, b = linfit([(a - x0) / 1e9 for a, _ in pr], [d / 1e6 for _, d in pr])
    except ValueError:
        return None
    return b


def synthesized_check(ts_ns: Sequence[float], arrival_ns: Sequence[float] | None = None,
                      modal_share_min: float = 0.9, max_distinct: int = 3, arrival_std_min_ms: float = 1.0,
                      drift_max_ms_per_s: float = 5.0) -> dict[str, Any]:
    """Are these host-API timestamps made up from a counter (e.g. DirectShow pts = n * nominal period)?

    Synthesized when the intervals are (almost) all identical -- >= ``modal_share_min`` of them equal one value
    exactly, or they take <= ``max_distinct`` distinct values (the C930e DS pts alternate 333333 / 333283 x 100 ns)
    -- while the arrivals jitter (arrival interval std > ``arrival_std_min_ms``); or when the timestamps drift
    against arrival by more than ``drift_max_ms_per_s`` (a real clock is within ~1 ms/s = 1000 ppm of the host;
    the generic camera's DS pts drift +143 ms/s because they count the nominal rate while it runs at 25.7 fps).
    Only meant for host-API timestamps: a device clock locked to the sensor can legitimately have constant
    intervals. Returns {"synthesized": bool|None, "modal_share", "distinct_intervals", "modal_interval_ms",
    "arrival_interval_std_ms", "drift_ms_per_s", "reasons"}."""
    t = [float(x) for x in ts_ns if x is not None]
    out: dict[str, Any] = {"synthesized": None, "n": len(t), "reasons": []}
    if len(t) < 10:
        out["reasons"].append("too few timestamps")
        return out
    iv = [int(round(b - a)) for a, b in zip(t, t[1:])]
    cnt = Counter(iv)
    modal, modal_n = cnt.most_common(1)[0]
    out.update(modal_share=modal_n / len(iv), distinct_intervals=len(cnt), modal_interval_ms=modal / 1e6,
               interval_std_ms=stats(iv, 1e-6).get("std"))
    even = out["modal_share"] >= modal_share_min or len(cnt) <= max_distinct
    out["even_intervals"] = even
    arr_std = None
    drift = None
    if arrival_ns is not None:
        a = [float(x) for x in arrival_ns if x is not None]
        if len(a) >= 3:
            arr_std = stats([(y - x) / 1e6 for x, y in zip(a, a[1:])]).get("std")
        if len(a) == len(t):
            drift = drift_ms_per_s(t, a)
    out["arrival_interval_std_ms"] = arr_std
    out["drift_ms_per_s"] = drift
    if arrival_ns is None:
        if even:
            out["reasons"].append("even intervals but no arrivals to compare")
        return out
    synth = False
    if even and arr_std is not None and arr_std > arrival_std_min_ms:
        synth = True
        out["reasons"].append(f"intervals {out['modal_share']:.0%} modal / {len(cnt)} distinct values while "
                              f"arrivals jitter (std {arr_std:.2f} ms)")
    if drift is not None and abs(drift) > drift_max_ms_per_s:
        synth = True
        out["reasons"].append(f"drift vs arrival {drift:+.1f} ms/s: not the camera's clock")
    out["synthesized"] = synth
    return out


# ---------------------------------------------------------------------------------------------------- modes
def modes_report(values_ms: Iterable[float], gap_ms: float = 3.0, min_share: float = 0.01) -> dict[str, Any]:
    """Split a (latency) distribution into modes separated by empty stretches > ``gap_ms`` and report each mode's
    share. A bimodal arrival-minus-sample-time (sub-ms vs ~16 ms on a 16 ms grid) must be reported per mode,
    never as one median (REPORT; analysis ts.md V5). Returns {"n", "modes": [{"centre_ms" (median within the
    mode), "count", "share", "min_ms", "max_ms", "std_ms"}], "n_modes", "multimodal", "minor_share", "mean_ms"};
    modes below ``min_share`` are folded into ``minor_share``. There is deliberately no overall median."""
    v = sorted(float(x) for x in values_ms if x is not None and not (isinstance(x, float) and math.isnan(x)))
    out: dict[str, Any] = {"n": len(v), "modes": [], "n_modes": 0, "multimodal": False, "minor_share": 0.0,
                           "gap_ms": gap_ms}
    if not v:
        return out
    groups: list[list[float]] = [[v[0]]]
    for x in v[1:]:
        if x - groups[-1][-1] > gap_ms:
            groups.append([x])
        else:
            groups[-1].append(x)
    n = len(v)
    minor = 0
    for g in groups:
        share = len(g) / n
        if share < min_share:
            minor += len(g)
            continue
        s = stats(g)
        out["modes"].append({"centre_ms": s["median"], "count": len(g), "share": share, "min_ms": g[0],
                             "max_ms": g[-1], "std_ms": s["std"]})
    out["n_modes"] = len(out["modes"])
    out["multimodal"] = out["n_modes"] > 1
    out["minor_share"] = minor / n
    out["mean_ms"] = sum(v) / n
    return out
