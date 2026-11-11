"""Shared helpers for the tier-0 timestamp-accuracy re-analysis (numpy only).

Imported by score_vs_flash_gt.py, score_vs_camera_clock.py and collect_existing_gt.py (same folder).

Contents
- load_frames(): reads a frames.jsonl from either capture tool and returns plain numpy arrays:
    mf_uvc_timing.exe  (timing/build):  host_arrival_ns, mf_sample_time_100ns, uvc_pts/uvc_scr_* in meta_items
    wincam.exe mf/ds   (suite/windows/native): qpc_ns (arrival), sample_time_100ns (mf), pts_ns (ds), uvc_* (mf)
- assign_slots(): tier-0 frame-slot indices from host stamps alone, with drop detection by gaps > 1.5 P.
- Lattice fits t_k = a + P*k (tier 0): whole run or sliding window (centred = offline, trailing = causal), with
  the offset a taken from the lower envelope of the residuals (a low quantile; q = 0 is the minimum).
- err_stats(): mean offset, std, p95 |e - mean|, max |e - mean|, MAD sigma.
All times are QPC nanoseconds (QPC is 10 MHz on Gerald, so 100 ns units * 100 = ns exactly).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------------------------------------------- io
def _unwrap(x: np.ndarray, bits: int) -> np.ndarray:
    m = 1 << bits
    d = np.diff(x.astype(np.int64))
    d = (d + m // 2) % m - m // 2
    return np.concatenate([[int(x[0])], int(x[0]) + np.cumsum(d)]).astype(np.int64)


def load_frames(path: Path) -> dict:
    """Return dict of arrays (float64 ns unless noted). Missing fields are absent from the dict."""
    rows = []
    with Path(path).open("rb") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("seq", 0))
    out: dict = {"n": len(rows), "path": str(path)}
    if not rows:
        return out
    r0 = rows[0]
    # flatten mf_uvc_timing meta_items[*]._top
    for r in rows:
        for it in r.get("meta_items", []) or []:
            for k, v in (it.get("_top") or {}).items():
                r.setdefault(k, v)
    out["seq"] = np.array([r.get("seq", i) for i, r in enumerate(rows)], float)
    if "host_arrival_ns" in r0:                       # mf_uvc_timing.exe
        out["tool"] = "mf_uvc_timing"
        out["arrival"] = np.array([r["host_arrival_ns"] for r in rows], float)
        if r0.get("mf_sample_time_100ns") is not None:
            out["sample_time"] = np.array([r["mf_sample_time_100ns"] * 100 for r in rows], float)
        if r0.get("readsample_call_ns") is not None:
            out["readsample_call"] = np.array([r["readsample_call_ns"] for r in rows], float)
    elif "qpc_ns" in r0:                              # wincam.exe
        out["tool"] = "wincam"
        out["arrival"] = np.array([r["qpc_ns"] for r in rows], float)
        if r0.get("sample_time_100ns") is not None:
            out["sample_time"] = np.array([r["sample_time_100ns"] * 100 for r in rows], float)
        if r0.get("pts_ns") is not None:
            out["ds_pts"] = np.array([r["pts_ns"] for r in rows], float)
    def has(k):
        return all(isinstance(r.get(k), int) for r in rows)
    if has("uvc_pts"):
        out["uvc_pts_ticks"] = _unwrap(np.array([r["uvc_pts"] for r in rows], np.int64), 32).astype(float)
    if has("uvc_scr_stc"):
        out["uvc_stc_ticks"] = _unwrap(np.array([r["uvc_scr_stc"] for r in rows], np.int64), 32).astype(float)
    return out


# ------------------------------------------------------------------------------------------------------------ stats
def err_stats(e_ns: np.ndarray) -> dict:
    """e = stamp - reference (ns). Offset = mean; spread stats after removing the mean (us)."""
    e = np.asarray(e_ns, float)
    e = e[np.isfinite(e)]
    if e.size < 3:
        return {"n": int(e.size)}
    mu = float(e.mean()); med = float(np.median(e))
    r = e - mu
    return {"n": int(e.size), "mean_offset_ms": mu / 1e6, "median_offset_ms": med / 1e6,
            "std_us": float(np.std(r, ddof=1) / 1e3),
            "p95_abs_us": float(np.percentile(np.abs(r), 95) / 1e3),
            "max_abs_us": float(np.max(np.abs(r)) / 1e3),
            "mad_sigma_us": float(1.4826 * np.median(np.abs(e - med)) / 1e3)}


def _env_offset(res: np.ndarray, q: float) -> float:
    return float(np.min(res)) if q <= 0 else float(np.quantile(res, q))


def linfit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    x0, y0 = x.mean(), y.mean()
    b = float(np.sum((x - x0) * (y - y0)) / np.sum((x - x0) ** 2))
    return float(y0 - b * x0), b


def lower_envelope_fit(x: np.ndarray, y: np.ndarray, q: float = 0.1, iters: int = 5,
                       q_final: float = 0.02) -> tuple[float, float]:
    """Same algorithm as tools/analyze_frames.py lower_envelope_fit (copied so this file stays numpy-only and
    importable without the tools/ path): iterative refit on the lowest residuals (fraction q), then shift the line
    to the q_final quantile of the residuals (analyze_frames uses 0.02; q_final = 0 -> the minimum)."""
    a, b = linfit(x, y)
    r = y - (a + b * x)
    m = np.ones_like(r, dtype=bool)
    for _ in range(iters):
        thr = np.quantile(r[m] if m.any() else r, q)
        m = r <= thr + 1e-9
        if m.sum() < 5:
            break
        a, b = linfit(x[m], y[m])
        r = y - (a + b * x)
    a += _env_offset(y - (a + b * x), q_final)
    return a, b


# ------------------------------------------------------------------------------------------------- tier-0 lattice
def assign_slots(t: np.ndarray, gap_factor: float = 1.5) -> dict:
    """Frame-slot index k for each delivered frame from host stamps only.

    1. Period guess Pg = median over i of (t[i+m] - t[i]) / m with m ~ 1 s of frames (averages out the 16 ms
       delivery grid; the median ignores spans that contain a drop).
    2. k[i] = k[i-1] + 1, or + round(dt/Pg) when dt > gap_factor * Pg (a drop), unless the next interval is so short
       that the two together span only the expected slots (late delivery, not a drop).
    3. P from least squares t = a + P k; repeat step 2 once with the refined P.
    Returns k (float array), P_ns, drops (= k[-1] - (n-1)), dup (intervals < 0.25 P: a repeated/phantom frame)."""
    t = np.asarray(t, float)
    n = len(t)
    d = np.diff(t)
    m = max(1, min(30, n // 4))
    Pg = float(np.median((t[m:] - t[:-m]) / m))
    k = None
    late = 0
    for _ in range(2):
        steps = np.where(d > gap_factor * Pg, np.maximum(1, np.round(d / Pg)), 1.0)
        # late delivery, not a drop: a long interval followed by a short one that together span only the expected
        # slots (e.g. the Kiyo at start-up: 62 ms then 1 ms)
        nxt = np.concatenate([d[1:], [np.inf]])
        is_late = (steps > 1) & (d + nxt < (steps + 0.5) * Pg)
        steps = np.where(is_late, 1.0, steps)
        late = int(is_late.sum())
        k = np.concatenate([[0.0], np.cumsum(steps)])
        _, Pg = linfit(k, t)
    return {"k": k, "P_ns": Pg, "drops": int(k[-1] - (n - 1)), "late_deliveries": late,
            "short_intervals": int(np.sum(d < 0.25 * Pg))}


def lattice_whole(t: np.ndarray, k: np.ndarray, q: float | None) -> np.ndarray:
    """Whole run, slope P by plain least squares on all frames (NOT robust to a latency change such as the C930e's
    +23 ms first 2 s). q=None: least-squares offset (mean-centred lattice, = the suite's frame-index fit);
    otherwise a = quantile_q(t - P k) (lower envelope; q=0 -> min)."""
    a, P = linfit(k, t)
    if q is None:
        return a + P * k
    return _env_offset(t - P * k, q) + P * k


def lattice_robust_whole(t: np.ndarray, k: np.ndarray, q_final: float = 0.02) -> np.ndarray:
    """Whole run, robust: slope and offset from the iterative lower-envelope fit on slot index (the 'seq_env'
    estimator of the existing flash scripts when q_final = 0.02 and k = seq)."""
    a, b = lower_envelope_fit(k, t, q_final=q_final)
    return a + b * k


def lattice_window(t: np.ndarray, k: np.ndarray, win_s: float, q_final: float, causal: bool, robust: bool = True,
                   min_frames: int = 15) -> np.ndarray:
    """Sliding window evaluated at each frame. Window = frames with t in [t_i - W/2, t_i + W/2] (centred, offline)
    or [t_i - W, t_i] (trailing, causal = usable live). robust=True: iterative lower-envelope fit in the window;
    robust=False: least-squares slope + quantile offset. Frames whose window has < min_frames frames get NaN."""
    t = np.asarray(t, float); k = np.asarray(k, float)
    W = win_s * 1e9
    out = np.full(len(t), np.nan)
    lo_idx = np.searchsorted(t, t - (W if causal else W / 2), side="left")
    hi_idx = np.searchsorted(t, t if causal else t + W / 2, side="right")
    for i in range(len(t)):
        j0, j1 = lo_idx[i], hi_idx[i]
        if j1 - j0 < min_frames:
            continue
        kk = k[j0:j1]; tt = t[j0:j1]
        if robust:
            a, P = lower_envelope_fit(kk, tt, q_final=q_final)
        else:
            a, P = linfit(kk, tt)
            a = _env_offset(tt - P * kk, q_final)
        out[i] = a + P * k[i]
    return out


def lattice_fixedP_window(t: np.ndarray, k: np.ndarray, win_s: float, q: float, causal: bool,
                          min_frames: int = 15) -> np.ndarray:
    """Two-stage fit: the period P comes from a long robust fit, only the offset is taken from the window.
      centred (offline): P from the robust whole-run fit; a = q-quantile of (t - P k) over [t_i - W/2, t_i + W/2]
      causal  (live):    P from the robust fit of all frames up to i (expanding); a = q-quantile over [t_i - W, t_i]
    The period of a camera clock is stable to ppm, so this avoids slope errors when a window holds a latency step."""
    t = np.asarray(t, float); k = np.asarray(k, float)
    W = win_s * 1e9
    out = np.full(len(t), np.nan)
    if not causal:
        _, P = lower_envelope_fit(k, t)
        r = t - P * k
        lo = np.searchsorted(t, t - W / 2, side="left"); hi = np.searchsorted(t, t + W / 2, side="right")
        for i in range(len(t)):
            if hi[i] - lo[i] >= min_frames:
                out[i] = _env_offset(r[lo[i]:hi[i]], q) + P * k[i]
        return out
    lo = np.searchsorted(t, t - W, side="left")
    for i in range(len(t)):
        if i + 1 < min_frames or i + 1 - lo[i] < min_frames:
            continue
        _, P = lower_envelope_fit(k[:i + 1], t[:i + 1])
        out[i] = _env_offset(t[lo[i]:i + 1] - P * k[lo[i]:i + 1], q) + P * k[i]
    return out


WINDOWS_S = (2.0, 5.0, 10.0, 20.0)
QUANTILES = (0.0, 0.02, 0.05, 0.10)


def tier0_variants(t: np.ndarray, k: np.ndarray) -> dict[str, np.ndarray]:
    """All tier-0 lattice variants on one host stamp series.
      lsq_whole                  least-squares lattice (mean offset), whole run (= the suite's frame-index fit)
      lsqP_envq{q}_whole         least-squares slope, offset = q-quantile of residuals, whole run
      rob_envq{q}_whole          iterative lower-envelope slope + offset, final shift to the q-quantile
                                 (q = 0.02 is the 'seq_env' estimator of the existing flash scripts)
      rob_envq{q}_win{W}s_{centred|causal}    full robust refit (slope and offset) inside a sliding window
      fixP_envq{q}_win{W}s_{centred|causal}   slope from a long robust fit, offset from the window (lattice_fixedP_window)
    q = 0 means the minimum."""
    v: dict[str, np.ndarray] = {"lsq_whole": lattice_whole(t, k, None)}
    for q in QUANTILES:
        v[f"lsqP_envq{q:g}_whole"] = lattice_whole(t, k, q)
        v[f"rob_envq{q:g}_whole"] = lattice_robust_whole(t, k, q)
    for W in WINDOWS_S:
        for causal in (False, True):
            tag = "causal" if causal else "centred"
            for q in (0.0, 0.02):
                v[f"rob_envq{q:g}_win{W:g}s_{tag}"] = lattice_window(t, k, W, q, causal, robust=True)
            for q in (0.0, 0.02, 0.05):
                v[f"fixP_envq{q:g}_win{W:g}s_{tag}"] = lattice_fixedP_window(t, k, W, q, causal)
    return v
