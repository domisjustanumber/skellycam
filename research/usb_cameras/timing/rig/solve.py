"""Band -> strobe assignment and per-frame solve (sync_rig/DESIGN.md §F items 6-7). numpy only.

Units: ns everywhere. ESP32 times are esp_timer ns; frame host times are QPC ns mapped to ESP time with the ping
fit (only needed coarsely, to pick the right strobe). Row 0 = top = read out first.

Per frame k (rolling shutter, row r integrates [s0_k + r*L, s0_k + r*L + E_k]):
    s0_k = t_c - r_b * L          (t_c = strobe centre, r_b = bottom 50 % edge)
    E_k  = (r_b - r_t) * L        (only when both edges are unclipped)
    x_k  = s0_k + E_k             (row 0 readout start on a sensor whose readout timing is fixed; used for frame slots)

Assignment (which strobe made a band). For a band with a top edge, tau = t_c - r_t*L0 estimates x_k; the host
arrival a_k (mapped to ESP time) trails x_k by a roughly constant D = a_k - x_k (readout + transfer + scheduling).
Every candidate strobe within [a_k - 300 ms, a_k + 50 ms] gives one D; wrong candidates differ from the true one by
multiples of the strobe spacing, so the histogram of all candidate D values peaks at the true D*. Each band takes
the candidate nearest a running local D* and is accepted within 0.4 strobe spacings. Using x_k (not s0_k) keeps D
independent of exposure changes. A host arrival on the ~16 ms Windows grid (REPORT finding 7) is still well inside
the 0.4 x 33 ms acceptance. Double strobe: two bands in one frame whose separation matches gap/L0 within 35 % are
taken as pulse 1 (upper) and pulse 2 (lower) of the same cycle; unpaired bands in a double-strobe run are not used.

Continuity: frame slots n_k come from x_k (precise to us), and o_k = n_k - seq_k must be piecewise constant (steps =
dropped frames). A frame whose o_k or residual departs from the running median is a misassignment: the +-1/+-2
neighbouring cycles are tried, otherwise the frame is dropped. Counts are reported.
"""
from __future__ import annotations

import numpy as np

from bands import amplitude_reference, detect_bands, mean_level


def running_median(x: np.ndarray, w: int) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n == 0:
        return x
    h = max(1, w // 2)
    out = np.empty(n)
    for i in range(n):
        a, b = max(0, i - h), min(n, i + h + 1)
        out[i] = np.median(x[a:b])
    return out


def _cycles(strobes: dict, double: bool) -> tuple[np.ndarray, np.ndarray]:
    """(t1, t2) per cycle: pulse-1 centre and pulse-2 centre (NaN when absent or single mode)."""
    t_c = strobes["t_c"].astype(np.float64)
    if not double:
        return t_c, np.full(len(t_c), np.nan)
    p, cyc = strobes["pulse"], strobes["cycle"]
    nc = int(cyc.max()) + 1 if len(cyc) else 0
    t1 = np.full(nc, np.nan)
    t2 = np.full(nc, np.nan)
    for t, pp, c in zip(t_c, p, cyc):
        if c < 0:
            continue
        if pp == 1:
            t1[c] = t
        else:
            t2[c] = t
    return t1, t2


def _units(segs: list[list[dict]], double: bool, gap_ns: float, L0: float) -> list[dict]:
    units = []
    for k, ss in enumerate(segs):
        if not double:
            for i, s in enumerate(ss):
                units.append({"k": k, "members": [(i, 1)]})
            continue
        used = set()
        for i in range(len(ss) - 1):
            if i in used:
                continue
            u, v = ss[i], ss[i + 1]
            sep = None
            if u["r_bot"] is not None and v["r_bot"] is not None:
                sep = v["r_bot"] - u["r_bot"]
            elif u["r_top"] is not None and v["r_top"] is not None:
                sep = v["r_top"] - u["r_top"]
            if sep is not None and abs(sep * L0 - gap_ns) < 0.35 * gap_ns:
                units.append({"k": k, "members": [(i, 1), (i + 1, 2)]})
                used.update((i, i + 1))
    return units


def _tau(unit: dict, segs_k: list[dict], c: int, t1: np.ndarray, t2: np.ndarray, L: float,
         E_est: float | None) -> float | None:
    """Estimate of x_k (row-0 readout start) if `unit` came from cycle c."""
    for i, p in unit["members"]:
        s = segs_k[i]
        tc = t1[c] if p == 1 else t2[c]
        if not np.isfinite(tc) or s["stepped"]:
            continue
        if s["r_top"] is not None:
            return float(tc - s["r_top"] * L)
    if E_est is not None:
        for i, p in unit["members"]:
            s = segs_k[i]
            tc = t1[c] if p == 1 else t2[c]
            if np.isfinite(tc) and s["r_bot"] is not None and not s["stepped"]:
                return float(tc - s["r_bot"] * L + E_est)
    return None


def pair_line_time(segs: list[list[dict]], gap_ns: float, L0: float) -> float | None:
    """L from double-strobe pairs inside one frame, before any strobe is identified (gap_ns = measured t_c2 - t_c1)."""
    Ls = []
    for u in _units(segs, True, gap_ns, L0):
        a, b = segs[u["k"]][u["members"][0][0]], segs[u["k"]][u["members"][1][0]]
        for key in ("r_bot", "r_top"):
            if a[key] is not None and b[key] is not None and b[key] - a[key] > 5:
                Ls.append(gap_ns / (b[key] - a[key]))
    return float(np.median(Ls)) if len(Ls) >= 5 else None


def assign(segs: list[list[dict]], a_esp: np.ndarray, strobes: dict, *, double: bool, gap_ns: float, L0: float,
           H: int, floor_margin_ns: float = 2e6, window_ns: tuple[float, float] = (300e6, 50e6)) -> dict:
    """Strobe identity. The candidate-D histogram is a comb (teeth one strobe period apart, all about equally high,
    because the strobe slips only ~33 us per frame), so it cannot by itself say which tooth is right. The tooth is
    chosen by physics: a frame cannot arrive before its last row is read out, so D = a - x >= (H-1)*L. Each unit
    takes its smallest candidate D above floor = (H-1)*L0 - floor_margin_ns, and D* is the median. This is right as
    long as host arrival trails the end of readout by less than one strobe period (minus the margin); an epoch check
    (first band after a deferred START, analyze_bands) confirms it independently when available."""
    t1, t2 = _cycles(strobes, double)
    order = np.argsort(np.where(np.isfinite(t1), t1, np.inf))
    t1s = t1[order]
    nfin = int(np.isfinite(t1s).sum())
    t1s = t1s[:nfin]
    order = order[:nfin]
    spacing = float(np.median(np.diff(t1s))) if nfin > 2 else 33e6
    units = _units(segs, double, gap_ns, L0)

    def candidates(k: int) -> np.ndarray:
        lo = np.searchsorted(t1s, a_esp[k] - window_ns[0])
        hi = np.searchsorted(t1s, a_esp[k] + window_ns[1])
        return order[lo:hi]

    # pass 1: per unit, the smallest candidate D above the physical floor
    floor = (H - 1) * L0 - floor_margin_ns
    Du = []
    for u in units:
        ds = [a_esp[u["k"]] - t for c in candidates(u["k"])
              if (t := _tau(u, segs[u["k"]], int(c), t1, t2, L0, None)) is not None]
        ds = [d for d in ds if d >= floor]
        if ds:
            Du.append(min(ds))
    if not Du:
        return {"entries": [], "units": len(units), "D_star_ms": None, "spacing_ns": spacing, "rejected": len(units)}
    D_star = float(np.median(Du))
    tol = 0.4 * spacing

    def pick(u: dict, Dref: float, E_est: float | None):
        best = None
        for c in candidates(u["k"]):
            t = _tau(u, segs[u["k"]], int(c), t1, t2, L0, E_est)
            if t is None:
                continue
            d = a_esp[u["k"]] - t
            if best is None or abs(d - Dref) < abs(best[1] - Dref):
                best = (int(c), d)
        return best

    chosen = [pick(u, D_star, None) for u in units]
    ks = np.array([u["k"] for u in units])
    dvals = np.array([c[1] if c is not None and abs(c[1] - D_star) < tol else np.nan for c in chosen])
    good = np.isfinite(dvals)
    # local D*: running median over accepted units (handles slow drift of the arrival latency or clock map)
    Dloc = np.full(len(units), D_star)
    if good.sum() > 5:
        rm = running_median(dvals[good], 61)
        Dloc = np.interp(ks, ks[good], rm)
    # E estimate for bottom-only bands: nearest frame with a full band from pass 1
    fullE = {}
    for u, c in zip(units, chosen):
        if c is None:
            continue
        for i, _p in u["members"]:
            s = segs[u["k"]][i]
            if s["r_top"] is not None and s["r_bot"] is not None and not s["stepped"]:
                fullE[u["k"]] = (s["r_bot"] - s["r_top"]) * L0
    fk = np.array(sorted(fullE))
    entries = []
    rejected = 0
    for j, u in enumerate(units):
        E_est = None
        if len(fk):
            q = int(np.clip(np.searchsorted(fk, u["k"]), 0, len(fk) - 1))
            near = fk[max(0, q - 1): q + 1]
            kk = near[np.argmin(np.abs(near - u["k"]))]
            if abs(kk - u["k"]) <= 30:
                E_est = fullE[int(kk)]
        c = pick(u, Dloc[j], E_est)
        if c is None or abs(c[1] - Dloc[j]) >= tol:
            rejected += 1
            continue
        for i, p in u["members"]:
            entries.append({"k": u["k"], "seg": i, "pulse": p, "cycle": c[0], "D": c[1]})
    return {"entries": entries, "units": len(units), "D_star_ms": D_star / 1e6, "spacing_ns": spacing,
            "rejected": rejected, "t1": t1, "t2": t2, "floor_ms": floor / 1e6,
            "latency_after_readout_ms": (D_star - (H - 1) * L0) / 1e6}


def epoch_check(entries: list[dict], a_esp: np.ndarray, strobes: dict, double: bool) -> dict:
    """Independent check of strobe identity: when the strobe was STARTed while the camera was already streaming
    (run_anchor_test.py default), k restarts at 0 and no band can exist before strobe k=0. The first frame with an
    assigned band after that epoch must hold cycle c0 (or c0+1 if strobe 0 fell into blanking or was too faint)."""
    k = strobes["k"]
    t_c = strobes["t_c"].astype(np.float64)
    pulse = strobes["pulse"]
    cyc = strobes["cycle"] if double else np.arange(len(t_c))
    lo, hi = float(np.min(a_esp)) + 0.2e9, float(np.max(a_esp)) - 0.5e9
    ep = [i for i in np.flatnonzero((k == 0) & (pulse == 1)) if lo < t_c[i] < hi]
    if not ep:
        return {"available": False, "note": "no strobe epoch (k=0) inside this capture; identity rests on the arrival floor rule"}
    out = []
    for i in ep:
        c0 = int(cyc[i])
        after = [e for e in entries if a_esp[e["k"]] > t_c[i]]
        before = [e for e in entries if e["cycle"] < c0 and a_esp[e["k"]] > t_c[i] + 0.1e9]
        if not after:
            out.append({"c0": c0, "consistent": False, "note": "no band after the epoch"})
            continue
        fk = min(e["k"] for e in after)
        m = min(e["cycle"] for e in after if e["k"] == fk) - c0
        out.append({"c0": c0, "first_band_cycle_minus_c0": int(m), "bands_assigned_to_pre_epoch_strobes": len(before),
                    "consistent": bool(m in (0, 1) and not before)})
    return {"available": True, "epochs": out, "consistent": all(o["consistent"] for o in out)}


def per_frame(segs, entries, t1, t2, L: float, N: int, conflict_ns: float = 0.5e6) -> dict:
    s0 = np.full(N, np.nan)
    E = np.full(N, np.nan)
    s0_only = np.full(N, np.nan)
    cyc = np.full(N, -1)
    conflicts = 0
    byk: dict[int, list[dict]] = {}
    for e in entries:
        byk.setdefault(e["k"], []).append(e)
    for k, es in byk.items():
        full_s0, full_E, bot_s0 = [], [], []
        c_full = -1
        for e in es:
            s = segs[k][e["seg"]]
            tc = t1[e["cycle"]] if e["pulse"] == 1 else t2[e["cycle"]]
            if not np.isfinite(tc) or s["stepped"]:
                continue
            if s["r_bot"] is not None:
                v = tc - s["r_bot"] * L
                bot_s0.append(v)
                if s["r_top"] is not None:
                    full_s0.append(v)
                    full_E.append((s["r_bot"] - s["r_top"]) * L)
                    c_full = e["cycle"]
        if full_s0:
            if np.ptp(full_s0) > conflict_ns:
                conflicts += 1
                continue
            s0[k] = float(np.mean(full_s0))
            E[k] = float(np.mean(full_E))
            cyc[k] = c_full
        if bot_s0:
            if np.ptp(bot_s0) > conflict_ns:
                if not full_s0:
                    conflicts += 1
                continue
            s0_only[k] = float(np.mean(bot_s0))
    return {"s0": s0, "E": E, "s0_any": np.where(np.isfinite(s0), s0, s0_only), "cycle": cyc, "conflicts": conflicts}


def line_time_double(segs, entries, t1, t2) -> dict:
    """L from double-strobe pairs: L = (t_c2 - t_c1) / (row separation), bottom and top edges separately."""
    byk: dict[tuple[int, int], dict[int, dict]] = {}
    for e in entries:
        byk.setdefault((e["k"], e["cycle"]), {})[e["pulse"]] = segs[e["k"]][e["seg"]]
    Ls, mids = [], []
    for (k, c), d in byk.items():
        if 1 not in d or 2 not in d or not np.isfinite(t2[c]):
            continue
        dt = t2[c] - t1[c]
        vals = []
        for key in ("r_bot", "r_top"):
            a, b = d[1][key], d[2][key]
            if a is not None and b is not None and b - a > 5:
                vals.append(dt / (b - a))
                mids.append(0.5 * (a + b))
        if vals:
            Ls.append(float(np.mean(vals)))
    if not Ls:
        return {"n": 0}
    L = np.array(Ls)
    med = float(np.median(L))
    keep = np.abs(L - med) < 0.02 * med
    L = L[keep]
    return {"n": int(len(L)), "L_ns": float(np.mean(L)), "L_se_ns": float(np.std(L, ddof=1) / np.sqrt(len(L))) if len(L) > 1 else None,
            "L_cv_pct": float(100 * np.std(L, ddof=1) / np.mean(L)) if len(L) > 1 else None,
            "rejected_outliers": int((~keep).sum()), "method": "double strobe: (t_c2 - t_c1) / row separation, mean of bottom- and top-edge estimates per frame"}


def frame_slots(x: np.ndarray, seq: np.ndarray, T_nom: float) -> dict:
    """Frame slots n_k from x_k (precise), with T fitted. Returns n (int, -1 where x is NaN), T, intercept, resid."""
    ok = np.isfinite(x)
    n = np.full(len(x), -1, dtype=np.int64)
    if ok.sum() < 3:
        return {"n": n, "n_all": n, "T": T_nom, "c": np.nan, "resid": np.full(len(x), np.nan)}
    idx = np.flatnonzero(ok)
    dx = np.diff(x[idx])
    dq = np.diff(seq[idx])
    sel = (dq == 1) & (np.abs(dx - T_nom) < 0.3 * T_nom)
    T = float(np.median(dx[sel])) if sel.sum() >= 3 else T_nom
    x0 = x[idx[0]]
    nn = np.round((x[idx] - x0) / T)
    for _ in range(3):  # refine T by a straight-line fit through x vs slot
        A = np.vstack([np.ones_like(nn), nn]).T
        c, T = np.linalg.lstsq(A, x[idx] - x0, rcond=None)[0]
        nn = np.round((x[idx] - x0 - c) / T)
    n[idx] = nn.astype(np.int64)
    resid = np.full(len(x), np.nan)
    resid[idx] = x[idx] - x0 - (c + T * nn)
    # frames without a band (strobe in blanking, clipped bands) get a slot from the nearest frame that has one,
    # offset by the seq difference (exact unless a frame was dropped in between)
    n_all = n.copy()
    for k in np.flatnonzero(~ok):
        q = int(np.clip(np.searchsorted(idx, k), 0, len(idx) - 1))
        j = idx[q] if abs(idx[q] - k) <= abs(idx[max(q - 1, 0)] - k) else idx[max(q - 1, 0)]
        n_all[k] = n[j] + (seq[k] - seq[j])
    return {"n": n, "n_all": n_all, "T": float(T), "c": float(x0 + c), "resid": resid}


def line_time_sweep(t_c_frame: np.ndarray, r_bot: np.ndarray, n: np.ndarray, E: np.ndarray, H: int) -> dict:
    """Cross-check of L from the equivalent-time sweep: t_c = s0_seg + T*n + L*r_b, with one intercept per exposure
    dwell (so an exposure-dependent shift of s0 does not leak into L) and T, L shared. L is identified by the band
    wrapping from the bottom of one frame to the top of a later one, so a run needs several sweep cycles."""
    ok = np.isfinite(t_c_frame) & np.isfinite(r_bot) & (n >= 0) & np.isfinite(E)
    idx = np.flatnonzero(ok)
    if len(idx) < 20:
        return {"n": int(len(idx))}
    Ei = E[idx]
    seg = np.zeros(len(idx), dtype=int)
    for i in range(1, len(idx)):
        seg[i] = seg[i - 1] + (abs(Ei[i] - Ei[i - 1]) > max(30e3, 0.03 * Ei[i - 1]))
    nseg = seg.max() + 1
    t0 = t_c_frame[idx[0]]
    y = t_c_frame[idx] - t0
    D = np.zeros((len(idx), nseg + 2))
    D[np.arange(len(idx)), seg] = 1.0
    D[:, nseg] = n[idx] - n[idx[0]]
    D[:, nseg + 1] = r_bot[idx]
    coef, *_ = np.linalg.lstsq(D, y, rcond=None)
    res = y - D @ coef
    dof = max(1, len(idx) - D.shape[1])
    s2 = float(res @ res / dof)
    try:
        cov = s2 * np.linalg.inv(D.T @ D)
        se = float(np.sqrt(cov[-1, -1]))
    except np.linalg.LinAlgError:
        se = float("nan")
    rb = r_bot[idx]
    wraps = int(np.sum(np.diff(rb) < -0.5 * H))
    if wraps < 2:
        return {"n": int(len(idx)), "wraps_seen": wraps, "identified": False,
                "note": "fewer than 2 band wraps: L and T are collinear in this run (use a double strobe or a faster sweep)"}
    return {"n": int(len(idx)), "identified": True, "L_ns": float(coef[-1]), "L_se_ns": se, "T_cam_ns": float(coef[nseg]),
            "resid_std_ns": float(np.sqrt(s2)), "dwell_segments": int(nseg), "wraps_seen": wraps,
            "method": "sweep regression t_c = s0_dwell + T*n + L*r_b"}


def _longest_empty(tot: np.ndarray, hit: np.ndarray) -> tuple[int, int]:
    """Longest circular run of phase bins without a detected band. Bins that received no strobe at all bridge a run
    but are trimmed from its ends, so the gap is bounded by bins that had strobes and no band."""
    nb = len(tot)
    nohit = hit == 0
    e2 = np.concatenate([nohit, nohit])
    t2 = np.concatenate([tot, tot])
    best, bstart = 0, 0
    i = 0
    while i < 2 * nb:
        if not e2[i]:
            i += 1
            continue
        j = i
        while j < 2 * nb and e2[j] and j - i < nb:
            j += 1
        a, b = i, j - 1
        while a <= b and t2[a] == 0:
            a += 1
        while b >= a and t2[b] == 0:
            b -= 1
        if b >= a and b - a + 1 > best:
            best, bstart = b - a + 1, a % nb
        i = j
    return best, bstart


def blanking_map(t1: np.ndarray, detected_cycles: set[int], slot_model: dict, slots: np.ndarray, E: np.ndarray,
                 L: float, H: int, bin_ns: float = 0.25e6) -> dict:
    """Vertical-blanking map. Strobe phase psi = t_c - x(n), x(n) = row-0 readout start of the frame slot n the
    strobe falls in (x(n) = c + T*n). Row r of frame n integrates [x - E + r*L, x + r*L], so the strobe lights rows
    psi/L .. (psi+E)/L of frame n (visible iff psi <= (H-1)*L) and rows (psi-T)/L .. (psi-T+E)/L of frame n+1
    (visible iff psi >= T - E). Strobes with (H-1)*L < psi < T - E leave no band at all. Computed per exposure value
    (E rounded to 0.1 ms): the gap shrinks as E grows and vanishes once E >= T - (H-1)*L."""
    T, c = slot_model["T"], slot_model["c"]
    if not np.isfinite(c):
        return {"error": "no slot model"}
    ok = (slots >= 0) & np.isfinite(E)
    if ok.sum() < 3:
        return {"error": "too few frames with E"}
    sl_ok, E_ok = slots[ok], E[ok]
    order = np.argsort(sl_ok)
    sl_ok, E_ok = sl_ok[order], E_ok[order]
    delivered = set(int(v) for v in slot_model.get("n_all", slots))
    psi, det, Es = [], [], []
    for ci, t in enumerate(t1):
        if not np.isfinite(t):
            continue
        n = int(np.floor((t - c) / T))
        if n not in delivered or (n + 1) not in delivered:
            continue
        q = int(np.clip(np.searchsorted(sl_ok, n), 0, len(sl_ok) - 1))
        j = q if abs(sl_ok[q] - n) <= abs(sl_ok[max(q - 1, 0)] - n) else max(q - 1, 0)
        if abs(sl_ok[j] - n) > 30:
            continue
        psi.append(t - (c + T * n))
        det.append(ci in detected_cycles)
        Es.append(E_ok[j])
    if not psi:
        return {"error": "no strobes inside delivered frames"}
    psi, det, Es = np.array(psi), np.array(det), np.round(np.array(Es) / 0.1e6) * 0.1e6
    nb = int(np.ceil(T / bin_ns))
    groups = []
    for e in np.unique(Es):
        m = Es == e
        if m.sum() < 50:
            continue
        b = np.clip((psi[m] / bin_ns).astype(int), 0, nb - 1)
        tot = np.bincount(b, minlength=nb)
        hit = np.bincount(b[det[m]], minlength=nb)
        best, bstart = _longest_empty(tot, hit)
        gap = None
        if best:
            gap = {"start_ms": bstart * bin_ns / 1e6, "end_ms": ((bstart + best) % nb or nb) * bin_ns / 1e6,
                   "width_ms": best * bin_ns / 1e6}
        groups.append({"E_ms": float(e / 1e6), "strobes": int(m.sum()), "detected": int(det[m].sum()),
                       "phase_bins_covered": int((tot > 0).sum()), "observed_gap": gap,
                       "expected_gap_start_ms": (H - 1) * L / 1e6, "expected_gap_end_ms": (T - e) / 1e6,
                       "expected_gap_ms": max(0.0, (T - e - (H - 1) * L) / 1e6)})
    return {"bin_ms": bin_ns / 1e6, "by_exposure": groups, "readout_ms": H * L / 1e6, "frame_period_ms": T / 1e6,
            "blanking_ms": (T - H * L) / 1e6,
            "convention": "psi = t_c - row-0 readout start of the frame slot; gap = longest run of phase bins with strobes but no band; a bin needs strobes in it to count, so coverage depends on run length"}


def echo_check(pb: np.ndarray, segs, s0, E, seq, entries, min_rows: int = 6) -> dict:
    """Temporal-noise-reduction echo: level in frame k+1 at the rows of frame k's band, away from frame k+1's own
    bands, as a fraction of frame k's band plateau."""
    byk = {}
    for e in entries:
        s = segs[e["k"]][e["seg"]]
        if s["r_top"] is not None and s["r_bot"] is not None and not s["stepped"]:
            byk.setdefault(e["k"], []).append(s)
    pos = {int(q): i for i, q in enumerate(seq)}
    ratios = []
    for k, bands in byk.items():
        k1 = pos.get(int(seq[k]) + 1)
        if k1 is None or not np.all(np.isfinite(pb[k1])):
            continue
        H = pb.shape[1]
        mask = np.zeros(H, bool)
        for s in bands:
            mask[int(np.ceil(s["r_top"] + 3)): int(np.floor(s["r_bot"] - 3)) + 1] = True
        own = np.zeros(H, bool)
        for s in segs[k1]:
            own[max(0, s["i0"] - 5): s["i1"] + 6] = True
        rows = mask & ~own
        if rows.sum() < min_rows:
            continue
        far = ~mask & ~own
        base = float(np.median(pb[k1][far])) if far.sum() > 10 else 0.0
        plateau = float(np.mean([0.5 * (s["p_top"] + s["p_bot"]) for s in bands]))
        if plateau <= 0:
            continue
        ratios.append((float(np.mean(pb[k1][rows])) - base) / plateau)
    if not ratios:
        return {"n_frames": 0, "note": "no frame pair where frame k+1 left frame k's band rows free"}
    r = np.array(ratios)
    return {"n_frames": int(len(r)), "echo_ratio_median": float(np.median(r)), "echo_ratio_p90": float(np.percentile(r, 90)),
            "flag": bool(np.median(r) > 0.03),
            "method": "mean linear level in frame k+1 over frame k's band rows (excluding frame k+1's own bands +-5 rows) / frame k band plateau"}


def analyze_bands(profiles: np.ndarray, seq: np.ndarray, a_esp: np.ndarray, strobes: dict, *, gap_ns: float,
                  T_nom: float, L_known: float | None = None, thr_frac: float = 0.35, sigma: float = 1.0,
                  L_guess_frac: float = 0.92) -> dict:
    """Full per-camera-run solve. Returns per-frame arrays (s0, E, slot, ...) and summaries."""
    N, H = profiles.shape
    double = gap_ns > 0
    bg = np.nanpercentile(profiles, 10, axis=0)
    pb = profiles - bg[None, :]
    A = amplitude_reference(pb, sigma)
    thr = thr_frac * A
    segs = [detect_bands(pb[k], thr, sigma=sigma) if np.all(np.isfinite(pb[k])) else [] for k in range(N)]
    L0 = L_known if L_known else L_guess_frac * T_nom / H
    L0_source = "given" if L_known else "guess"
    if double and not L_known:
        t1_, t2_ = _cycles(strobes, True)
        g = t2_ - t1_
        g_meas = float(np.nanmedian(g)) if np.isfinite(g).any() else gap_ns
        Lp = pair_line_time(segs, g_meas, L0)
        if Lp:
            L0, L0_source = Lp, "double-strobe pairs"
    margin = (1e6 + 0.005 * H * L0) if L0_source != "guess" else (2e6 + 0.03 * H * L0)
    asg = assign(segs, a_esp, strobes, double=double, gap_ns=gap_ns, L0=L0, H=H, floor_margin_ns=margin)
    if not asg["entries"]:
        return {"error": "no band could be assigned to a strobe", "n_frames": N, "amplitude_ref": A,
                "frames_with_segments": int(sum(1 for s in segs if s)), "assignment": {k: v for k, v in asg.items() if k not in ("t1", "t2")}}
    t1, t2 = asg["t1"], asg["t2"]
    Ld = line_time_double(segs, asg["entries"], t1, t2) if double else {"n": 0}
    L = L_known or (Ld.get("L_ns") if Ld.get("n", 0) >= 5 else None) or L0
    L_source = "given" if L_known else ("double strobe (this run)" if Ld.get("n", 0) >= 5 else "guess (0.92*T/H)")
    sweep = {"n": 0}
    fixed = dropped = 0
    entries = asg["entries"]
    for it in range(3):
        pf = per_frame(segs, entries, t1, t2, L, N)
        E_fill = pf["E"].copy()
        okE = np.isfinite(E_fill)
        if okE.sum():
            E_fill = np.interp(np.arange(N), np.flatnonzero(okE), E_fill[okE])
        x = pf["s0_any"] + E_fill
        sl = frame_slots(x, seq, T_nom)
        # continuity: o = slot - seq is piecewise constant (drops); spikes are misassignments
        okx = sl["n"] >= 0
        if okx.sum() > 10 and it < 2:
            idx = np.flatnonzero(okx)
            o = (sl["n"][idx] - seq[idx]).astype(float)
            rm = np.round(running_median(o, 31))
            rr = running_median(sl["resid"][idx], 31)
            bad = (o != rm) | (np.abs(sl["resid"][idx] - rr) > 0.2 * sl["T"])
            bad_k = set(idx[bad].tolist())
            if bad_k:
                new_entries = [e for e in entries if e["k"] not in bad_k]
                spacing = asg["spacing_ns"]
                for kpos, k in enumerate(idx):
                    if k not in bad_k:
                        continue
                    ek = [e for e in entries if e["k"] == k]
                    target_n = seq[k] + rm[kpos]
                    ok_fix = None
                    for m in (1, -1, 2, -2):
                        cand = [dict(e, cycle=e["cycle"] + m) for e in ek if 0 <= e["cycle"] + m < len(t1)]
                        if len(cand) != len(ek):
                            continue
                        p2 = per_frame(segs, cand, t1, t2, L, N)
                        if not np.isfinite(p2["s0_any"][k]):
                            continue
                        xk = p2["s0_any"][k] + E_fill[k]
                        nk = np.round((xk - sl["c"]) / sl["T"])
                        rk = xk - (sl["c"] + sl["T"] * nk)
                        if nk == target_n and abs(rk - rr[kpos]) < 0.2 * sl["T"]:
                            ok_fix = cand
                            break
                    if ok_fix:
                        new_entries.extend(ok_fix)
                        fixed += 1
                    else:
                        dropped += 1
                entries = new_entries
                continue
        # L from the sweep (cross-check; used only when no double-strobe or given L exists)
        if not double:
            tc_frame = np.full(N, np.nan)
            rb = np.full(N, np.nan)
            for e in entries:
                s = segs[e["k"]][e["seg"]]
                if e["pulse"] == 1 and s["r_bot"] is not None and s["r_top"] is not None and not s["stepped"] and pf["cycle"][e["k"]] == e["cycle"]:
                    tc_frame[e["k"]] = t1[e["cycle"]]
                    rb[e["k"]] = s["r_bot"]
            sweep = line_time_sweep(tc_frame, rb, sl["n"], pf["E"], H)
            if L_source.startswith("guess") and sweep.get("n", 0) >= 50 and sweep.get("identified") \
                    and np.isfinite(sweep.get("L_se_ns", np.nan)) and abs(sweep["L_ns"] - L) > 0.0005 * L:
                L = sweep["L_ns"]
                L_source = "sweep (no double strobe given)"
                continue
        break
    pf = per_frame(segs, entries, t1, t2, L, N)
    E_fill = pf["E"].copy()
    okE = np.isfinite(E_fill)
    if okE.sum():
        E_fill = np.interp(np.arange(N), np.flatnonzero(okE), E_fill[okE])
    sl = frame_slots(pf["s0_any"] + E_fill, seq, T_nom)
    detected = {e["cycle"] for e in entries if e["pulse"] == 1}
    blank = {"note": "not computed for double-strobe runs (only paired bands are assigned)"} if double else \
        blanking_map(t1, detected, sl, sl["n"], pf["E"], L, H)
    echo = echo_check(pb, segs, pf["s0"], pf["E"], seq, entries)
    # per-frame band table rows
    table = []
    for e in sorted(entries, key=lambda e: (e["k"], e["seg"])):
        s = segs[e["k"]][e["seg"]]
        tc = t1[e["cycle"]] if e["pulse"] == 1 else t2[e["cycle"]]
        table.append({"seq": int(seq[e["k"]]), "slot": int(sl["n"][e["k"]]), "cycle": int(e["cycle"]), "pulse": int(e["pulse"]),
                      "t_c_ns": int(tc), "r_top": s["r_top"], "r_bot": s["r_bot"], "clipped_top": s["clipped_top"],
                      "clipped_bot": s["clipped_bot"], "stepped": s["stepped"], "plateau": 0.5 * (s["p_top"] + s["p_bot"]),
                      "D_ms": e["D"] / 1e6})
    n_full = int(np.isfinite(pf["s0"]).sum())
    return {
        "n_frames": N, "rows": H, "amplitude_ref": A, "threshold": thr,
        "frames_with_segments": int(sum(1 for s in segs if s)),
        "assignment": {"units": asg["units"], "accepted_entries": len(entries), "rejected_units": asg["rejected"],
                       "D_star_ms": asg["D_star_ms"], "strobe_spacing_ms": asg["spacing_ns"] / 1e6,
                       "arrival_floor_ms": asg["floor_ms"], "L_for_assignment_source": L0_source,
                       "median_arrival_after_readout_end_ms": asg["latency_after_readout_ms"],
                       "identity_rule": "smallest candidate with host arrival after the end of readout (D >= (H-1)*L - margin)",
                       "epoch_check": epoch_check(entries, a_esp, strobes, double),
                       "continuity_fixed": fixed, "continuity_dropped": dropped},
        "L_ns": L, "L_source": L_source, "L_double": Ld, "L_sweep": sweep, "readout_ms": H * L / 1e6,
        "frames_full_band": n_full, "frames_s0_only": int(np.isfinite(pf["s0_any"]).sum()) - n_full,
        "frame_conflicts": pf["conflicts"], "frame_period_ns": sl["T"], "slots": sl["n"],
        "s0": pf["s0"], "E": pf["E"], "s0_any": pf["s0_any"], "blanking": blank, "echo": echo, "band_table": table,
    }
