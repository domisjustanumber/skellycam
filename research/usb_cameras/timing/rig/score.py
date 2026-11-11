"""Timestamp-anchor scoring (sync_rig/DESIGN.md §F item 10). numpy only.

Model per frame k, for one timestamp source in one capture run:

    ts_k = a + b*s0_k + c*E_k + eps_k,      alpha = c / b

  s0_k = row-0 exposure start (ESP32 ns), E_k = measured exposure (ns), both from the strobe band.
  a, b absorb the source clock's offset and rate (b = 1 + ppm for host-clock sources; b = ticks per ESP ns for a
  camera clock), so alpha needs no host-clock link. alpha = 0: the timestamp tracks exposure start; 0.5: mid-
  exposure; 1: exposure end = row-0 readout start on a fixed-readout rolling-shutter sensor.
  The fit needs E to vary inside the run (exposure schedule); with one exposure alpha is not identified.

Fitting: OLS, then up to 3 rounds dropping |residual| > 6 * 1.4826 * MAD (late deliveries); the dropped count is
reported. Confidence interval of alpha: the wider of (a) OLS delta-method 95 % and (b) a moving-block bootstrap 95 %
(blocks of ~2 s of frames, 400 resamples). (b) matters for sources whose errors are correlated in time, e.g. the
~16 ms grid of Windows sample times (REPORT finding 7), where OLS alone would claim false precision.

K (host-clock sources only, QPC ns):
    K_alpha1   = mean(ts - host(s0 + E))          (alpha = 1: ts - K = row-0 readout start)
    K_alphafit = mean(ts - host(s0 + alpha*E))
  host() = ESP -> QPC through the ping fit. K_abs uses the fit's two offsets ("first_byte", "last_byte") and is
  ESTIMATED (path asymmetry, |bias| <= asymmetry_bound_us). K_rel = K - K_ref of another camera/source in the SAME
  run with the same mapping: the offset cancels and only the clock rate matters.

Camera-clock sources (UVC PTS/SCR ticks) get alpha and jitter only. A derived "<name>->qpc_env" source maps the
ticks to QPC by a whole-run lower-envelope line against host_arrival_ns (non-causal; how a downstream user would
map PTS without SOF), and is then scored like a host source, so it gets a K too.
"""
from __future__ import annotations

import numpy as np


def _ols(X: np.ndarray, y: np.ndarray):
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ coef
    return coef, res


def _alpha_from(coef):
    return coef[2] / coef[1]


def lower_envelope_map(x_ticks: np.ndarray, host_ns: np.ndarray, q: float = 0.02) -> tuple[np.ndarray, dict]:
    """host ~ p + s*x through the lower envelope of host arrival (latency floor). Returns mapped host ns."""
    x = x_ticks.astype(np.float64) - float(x_ticks[0])
    y = host_ns.astype(np.float64) - float(host_ns[0])
    keep = np.ones(len(x), bool)
    for _ in range(5):
        A = np.vstack([np.ones(keep.sum()), x[keep]]).T
        (p, s), *_ = np.linalg.lstsq(A, y[keep], rcond=None)
        r = y - (p + s * x)
        keep = r <= np.quantile(r, 0.2)
    r = y - (p + s * x)
    shift = float(np.quantile(r, q))
    mapped = float(host_ns[0]) + p + s * x + shift
    return mapped, {"ns_per_tick": float(s), "clock_hz_est": float(1e9 / s) if s else None,
                    "method": f"whole-run lower envelope (q={q}) of host_arrival_ns vs ticks; non-causal"}


def fit_anchor(ts: np.ndarray, s0: np.ndarray, E: np.ndarray, *, block_s: float = 2.0, frame_period_ns: float = 33.3e6,
               n_boot: int = 400, seed: int = 0) -> dict:
    """Fit ts = a + b*s0 + c*E. ts may be ns or ticks (int64 or float). Arrays already masked to valid frames and in
    capture order. Residuals are reported in ESP ns (divided by b)."""
    n = len(ts)
    if n < 10:
        return {"n": int(n), "error": "fewer than 10 frames with s0, E and this timestamp"}
    t_ref = ts[0]
    s_ref = s0[0]
    y = (ts - t_ref).astype(np.float64)
    x1 = (s0 - s_ref).astype(np.float64)
    x2 = E.astype(np.float64)
    if np.ptp(x2) < 50e3:
        return {"n": int(n), "error": "exposure did not vary (range < 50 us): alpha not identified"}
    X = np.vstack([np.ones(n), x1, x2]).T
    keep = np.ones(n, bool)
    for _ in range(3):
        coef, res = _ols(X[keep], y[keep])
        r_all = y - X @ coef
        mad = np.median(np.abs(r_all[keep] - np.median(r_all[keep])))
        new = np.abs(r_all - np.median(r_all[keep])) <= max(6 * 1.4826 * mad, 1.0)
        if np.array_equal(new, keep):
            break
        keep = new
    coef, res = _ols(X[keep], y[keep])
    a, b, c = coef
    alpha = c / b
    m = int(keep.sum())
    dof = max(1, m - 3)
    s2 = float(res @ res / dof)
    cov = s2 * np.linalg.inv(X[keep].T @ X[keep])
    g = np.array([0.0, -c / b ** 2, 1.0 / b])  # gradient of c/b wrt (a, b, c)
    se = float(np.sqrt(g @ cov @ g))
    ci_ols = (alpha - 1.96 * se, alpha + 1.96 * se)
    # moving-block bootstrap over the kept frames (capture order)
    Xk, yk = X[keep], y[keep]
    blk = max(10, int(round(block_s * 1e9 / frame_period_ns)))
    nb = int(np.ceil(m / blk))
    rng = np.random.default_rng(seed)
    boots = []
    if m > 2 * blk:
        starts_max = m - blk
        for _ in range(n_boot):
            st = rng.integers(0, starts_max + 1, nb)
            idx = (st[:, None] + np.arange(blk)[None, :]).ravel()[:m]
            cb, _ = _ols(Xk[idx], yk[idx])
            if cb[1] != 0:
                boots.append(_alpha_from(cb))
    if len(boots) >= 50:
        ci_boot = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)))
    else:
        ci_boot = None
    lo = min(ci_ols[0], ci_boot[0]) if ci_boot else ci_ols[0]
    hi = max(ci_ols[1], ci_boot[1]) if ci_boot else ci_ols[1]
    res_ns = res / b
    mad_ns = float(np.median(np.abs(res_ns - np.median(res_ns))))
    return {
        "n": m, "n_outliers_dropped": int(n - m),
        "alpha": float(alpha), "alpha_ci95": [float(lo), float(hi)], "alpha_ci95_halfwidth": float((hi - lo) / 2),
        "alpha_se_ols": se, "alpha_ci95_ols": [float(ci_ols[0]), float(ci_ols[1])],
        "alpha_ci95_block_bootstrap": list(ci_boot) if ci_boot else None, "bootstrap_block_frames": blk,
        "rate_b": float(b), "rate_ppm_vs_esp": float((b - 1) * 1e6) if abs(b - 1) < 0.01 else None,
        "exposure_range_ms": [float(x2.min() / 1e6), float(x2.max() / 1e6)],
        "residual_std_us": float(np.std(res_ns) / 1e3), "residual_mad_us": float(mad_ns / 1e3),
        "residual_sigma_mad_us": float(1.4826 * mad_ns / 1e3),
        "_keep": keep, "_coef": coef,
    }


def k_values(ts_ns: np.ndarray, s0: np.ndarray, E: np.ndarray, alpha: float, clock, keep: np.ndarray,
             frame_period_ns: float, block_s: float = 2.0) -> dict:
    """K for a host-clock source (QPC ns), both ping-offset variants. Means over the frames kept by fit_anchor."""
    out = {}
    tsk = ts_ns[keep].astype(np.float64)
    for variant in ("first_byte", "last_byte"):
        s0h = clock.esp_to_host(s0[keep], variant)
        Eh = clock.esp_delta_to_host(E[keep])
        d1 = tsk - (s0h + Eh)
        dfit = tsk - (s0h + alpha * Eh)
        out[variant] = {"K_alpha1_us": float(np.mean(d1) / 1e3), "K_alphafit_us": float(np.mean(dfit) / 1e3)}
    # SE of the mean with ~2 s blocks (errors can be correlated in time)
    d = tsk - (clock.esp_to_host(s0[keep]) + clock.esp_delta_to_host(E[keep]))
    blk = max(10, int(round(block_s * 1e9 / frame_period_ns)))
    nb = len(d) // blk
    if nb >= 3:
        bm = d[: nb * blk].reshape(nb, blk).mean(axis=1)
        se = float(np.std(bm, ddof=1) / np.sqrt(nb) / 1e3)
    else:
        se = float(np.std(d) / np.sqrt(max(1, len(d))) / 1e3)
    out["K_alpha1_se_us"] = se
    return out
