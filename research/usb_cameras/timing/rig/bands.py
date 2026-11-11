"""Strobe band detector (sync_rig/DESIGN.md §F item 5). numpy only.

Conventions
  * A profile is one value per image row: row 0 = TOP of the decoded image = the row read out FIRST.
    Row r's sample sits at integer coordinate r; edges are returned as continuous row coordinates.
  * Input profiles are LINEAR light (tone curve already inverted) with the background already subtracted.
  * Rolling shutter: row r integrates [s0 + r*L, s0 + r*L + E]. A pulse [t_rise, t_rise + w] lights a band whose
    TOP edge (rising, rows above see none of the pulse) crosses 50 % at r_t = (t_c - E - s0)/L and whose BOTTOM edge
    crosses 50 % at r_b = (t_c - s0)/L, with t_c = t_rise + w/2. Hence s0 = t_c - r_b*L and E = (r_b - r_t)*L.

Method per profile
  1. Gaussian smoothing (sigma ~1 row) so sharpening overshoot and MJPEG block noise do not move the crossing
     (a symmetric kernel keeps the 50 % point of a symmetric ramp).
  2. Segments = runs above an absolute threshold (a fraction of the run-wide band amplitude), short gaps merged.
  3. Each edge gets its OWN plateau (median of rows just inside the edge) and baseline (median of rows just outside),
     so vignetting, a slowly varying card illumination or a weak echo band next to the edge do not bias it.
  4. 50 % crossing by linear interpolation between the two samples that straddle base + 0.5*(plateau - base).
  5. An edge is CLIPPED (None) when the band touches the image boundary, when fewer than 2 baseline rows exist
     outside it, or when the crossing is closer than edge_margin rows to the boundary. A clipped edge is never used;
     the other edge of the same band still is.
  6. 'stepped' marks a segment whose two plateaus differ by > 1.5x (two overlapping bands, e.g. a double strobe with
     E > gap); such segments are kept for s0 bookkeeping but never used for E or L.
"""
from __future__ import annotations

import numpy as np


def gaussian_smooth(p: np.ndarray, sigma: float) -> np.ndarray:
    p = np.asarray(p, dtype=np.float64)
    if sigma <= 0:
        return p.copy()
    r = max(1, int(np.ceil(3 * sigma)))
    x = np.arange(-r, r + 1)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k /= k.sum()
    pad = np.pad(p, r, mode="edge")
    return np.convolve(pad, k, mode="valid")


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive (start, end) index pairs of True runs."""
    if not mask.any():
        return []
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1) - 1
    return list(zip(starts.tolist(), ends.tolist()))


def detect_bands(p: np.ndarray, thr: float, *, sigma: float = 1.0, guard: int = 2, plateau_rows: int = 10,
                 base_rows: int = 6, min_len: int = 3, merge_gap: int = 2, edge_margin: float = 2.0) -> list[dict]:
    """Find lit bands in one linear, background-subtracted row profile. Returns a list of segment dicts, top first:
    {i0, i1, r_top, r_bot, clipped_top, clipped_bot, p_top, p_bot, base_top, base_bot, amp, stepped}."""
    ps = gaussian_smooth(p, sigma)
    H = len(ps)
    runs = _runs(ps > thr)
    merged: list[list[int]] = []
    for a, b in runs:
        if merged and a - merged[-1][1] - 1 <= merge_gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = []
    for i0, i1 in merged:
        if i1 - i0 + 1 < min_len:
            continue
        n = i1 - i0 + 1
        if n >= 2 * guard + 3:
            top_in = ps[i0 + guard: min(i0 + guard + plateau_rows, i1 - guard + 1)]
            bot_in = ps[max(i1 - guard - plateau_rows + 1, i0 + guard): i1 - guard + 1]
            p_top = float(np.median(top_in))
            p_bot = float(np.median(bot_in))
        else:
            p_top = p_bot = float(ps[i0:i1 + 1].max())
        inner_hi = float(np.percentile(ps[i0:i1 + 1], 95))
        seg = {"i0": int(i0), "i1": int(i1), "r_top": None, "r_bot": None, "clipped_top": True, "clipped_bot": True,
               "p_top": p_top, "p_bot": p_bot, "base_top": None, "base_bot": None,
               "amp": float(ps[i0:i1 + 1].max()),
               # two overlapping bands: unequal edge plateaus, or an interior level well above both edge plateaus
               "stepped": bool(max(p_top, p_bot) > 1.5 * max(min(p_top, p_bot), 1e-12)
                               or inner_hi > 1.5 * max(p_top, p_bot, 1e-12))}
        # ---- top edge (rising when walking down the image)
        b0, b1 = max(0, i0 - guard - base_rows), i0 - guard
        if b1 - b0 >= 2:
            base = float(np.median(ps[b0:b1]))
            level = base + 0.5 * (p_top - base)
            j = min(i0 + guard, i1)
            while j > 0 and ps[j] < level and j < i1:  # step inside if the start sample dipped
                j += 1
            while j > 0 and ps[j - 1] >= level:
                j -= 1
            if j > 0 and ps[j] > ps[j - 1]:
                r = (j - 1) + (level - ps[j - 1]) / (ps[j] - ps[j - 1])
                if r >= edge_margin:
                    seg.update(r_top=float(r), clipped_top=False, base_top=base)
        # ---- bottom edge (falling)
        b0, b1 = i1 + guard + 1, min(H, i1 + guard + 1 + base_rows)
        if b1 - b0 >= 2:
            base = float(np.median(ps[b0:b1]))
            level = base + 0.5 * (p_bot - base)
            j = max(i1 - guard, i0)
            while j < H - 1 and ps[j] < level and j > i0:
                j -= 1
            while j < H - 1 and ps[j + 1] >= level:
                j += 1
            if j < H - 1 and ps[j] > ps[j + 1]:
                r = j + (ps[j] - level) / (ps[j] - ps[j + 1])
                if r <= H - 1 - edge_margin:
                    seg.update(r_bot=float(r), clipped_bot=False, base_bot=base)
        out.append(seg)
    return out


def mean_level(p: np.ndarray, r0: float, r1: float) -> float | None:
    """Mean of a profile over rows [ceil(r0), floor(r1)] (None if empty)."""
    a, b = int(np.ceil(r0)), int(np.floor(r1))
    a, b = max(a, 0), min(b, len(p) - 1)
    if b < a:
        return None
    return float(np.mean(np.asarray(p, dtype=np.float64)[a:b + 1]))


def amplitude_reference(profiles_bgsub: np.ndarray, sigma: float = 1.0) -> float:
    """Run-wide band amplitude: median of per-frame maxima over the frames that clearly contain a band."""
    m = np.array([np.nanmax(gaussian_smooth(np.nan_to_num(p), sigma)) for p in profiles_bgsub])
    m = m[np.isfinite(m)]
    if not len(m):
        return float("nan")
    hi = np.percentile(m, 95)
    sel = m[m >= 0.5 * hi]
    return float(np.median(sel)) if len(sel) else float(hi)
