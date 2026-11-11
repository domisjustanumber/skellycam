# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""Score per-frame host timestamps without light ground truth.

Method (see results README):
  * A camera at fixed exposure emits frames on a lattice t_k = t0 + P*k.  For each stamp series: assign frame slots
    (drop = slot step > 1), fit t = a + P*slot robustly (iterative 4-sigma MAD trim), report residuals of ALL frames
    around the fit (median-centred): std, p95(|r|), max(|r|).  This is the per-frame random timestamp error excluding a
    constant offset; any constant latency is unmeasured.
  * Tier-0 "fitted" stamps: the same slots, line fitted to the lower envelope (frames whose residual is in the lowest
    10 %, two passes), t_hat = a_env + P_env*slot.
  * MF runs only: the camera's own clock (UVC SCR STC or PTS from the capture metadata; available because the
    MetadataBufferSizeInKB0 registry value is set on Gerald; used here ONLY as a measurement reference, never as part
    of a tier-0 method).  Each host series is scored against host = alpha + beta*clock (robust fit); the fitted
    lattice stamps are scored against the same mapped clock.
  * Multi-camera runs: for frame index k (what skellycam groups and freemocap pairs), the stored-stamp difference and
    the difference of the cameras' lattice (lower-envelope) times for the slots those frames occupy.

Usage: analyze.py <results_dir>   (reads *.session.json + *.frames.csv from dshow_capture.py, and mf_*/ folders)
Writes <results_dir>/analysis.json and prints markdown tables.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

VIDPID_NAME = {"046D:085C": "C922", "046D:0843": "C930e", "1532:0E05": "KiyoPro", "4C4A:4A55": "Generic"}
DSHOW_TRIM_S = 1.0   # DShow frames start after a 2.5 s warm phase; drop 1 s more
KNOWN_P: dict = {}  # camera -> period (ns) from free-running DShow and MF runs; filled in main()
MF_TRIM_S = 3.0      # MF: exposure is re-set 1.5 s after the first frame; drop the first 3 s


def robust_line(x, y, iters=4, k=4.0):
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.ones(len(x), bool)
    for _ in range(iters):
        A = np.vstack([np.ones(m.sum()), x[m]]).T
        a, b = np.linalg.lstsq(A, y[m], rcond=None)[0]
        r = y - (a + b * x)
        med = np.median(r[m]); mad = 1.4826 * np.median(np.abs(r[m] - med)) + 1e-9
        m_new = np.abs(r - med) < k * mad
        if m_new.sum() < 10 or (m_new == m).all():
            m = m_new if m_new.sum() >= 10 else m
            break
        m = m_new
    A = np.vstack([np.ones(m.sum()), x[m]]).T
    a, b = np.linalg.lstsq(A, y[m], rcond=None)[0]
    return a, b, m


def rstats(r_ns):
    r = np.asarray(r_ns, float)
    r = r - np.median(r)
    ar = np.abs(r)
    return {"std_ms": round(float(np.std(r)) / 1e6, 4), "p95_ms": round(float(np.percentile(ar, 95)) / 1e6, 4),
            "max_ms": round(float(ar.max()) / 1e6, 4), "n": int(len(r))}


def assign_slots(t, p0=None):
    """Slots for a stamp series with possible drops. Returns slots, P (ns), a (ns), ambiguous count."""
    t = np.asarray(t, float)
    # Gap thresholds do not work here: on the 16 ms delivery grid a normal 30 fps gap can be P+16 = 49.3 ms and a
    # one-drop gap 2P-16 = 50.7 ms.  So find P globally with a phase-coherence periodogram (drops do not disturb it),
    # then slot every stamp against the lattice.
    tt = t - t[0]
    P0 = float(p0) if p0 else float(tt[-1] / (len(t) - 1))  # >= P (drops only lengthen it)

    def coh(Ps, x):
        out = np.empty(len(Ps))
        for i in range(0, len(Ps), 256):
            ph = np.exp(2j * np.pi * x[None, :] / Ps[i:i + 256, None])
            out[i:i + 256] = np.abs(ph.mean(axis=1))
        return out
    seg = tt[tt < 10e9]
    Ps = P0 * np.linspace(0.85, 1.02, 4000)
    c = coh(Ps, seg)
    # Quantized stamps also fit shorter lattices with a few invented drops almost as well. Drops are rare, so take
    # the LONGEST period whose coherence peak is >= 0.7 x the best one (P0 >= true P, so true P is the longest).
    pk = np.where((c[1:-1] >= c[:-2]) & (c[1:-1] >= c[2:]) & (c[1:-1] >= 0.7 * c.max()))[0] + 1
    P = Ps[pk.max()] if len(pk) else Ps[np.argmax(c)]
    for span in (2e-3, 2e-4, 2e-5):
        Ps = P * np.linspace(1 - span, 1 + span, 801)
        P = Ps[np.argmax(coh(Ps, tt))]
    phi = np.angle(np.mean(np.exp(2j * np.pi * tt / P))) / (2 * np.pi) * P
    s = np.round((tt - phi) / P).astype(int)
    for i in range(1, len(s)):  # strictly increasing
        if s[i] <= s[i - 1]:
            s[i] = s[i - 1] + 1
    s = s - s[0]
    a, P, _ = robust_line(s, t)
    for _ in range(2):
        s2 = np.round((t - a) / P).astype(int)
        for i in range(1, len(s2)):
            if s2[i] <= s2[i - 1]:
                s2[i] = s2[i - 1] + 1
        s = s2 - s2[0]
        a, P, _ = robust_line(s, t)
    frac = (t - (a + P * s)) / P
    amb = int(np.sum(np.abs(frac - np.median(frac)) > 0.35))
    return s, P, a, amb


def lattice_scores(t, slots=None, p0=None):
    t = np.asarray(t, float)
    if slots is None:
        slots, P, a, amb = assign_slots(t, p0)
    else:
        a, P, _ = robust_line(slots, t); amb = None
    r = t - (a + P * slots)
    out = {"fps": round(1e9 / P, 5), "period_ms": round(P / 1e6, 6), "frames": int(len(t)),
           "drops": int(slots[-1] - slots[0] + 1 - len(t)), "ambiguous_slots": amb, "resid": rstats(r)}
    # lower-envelope (tier-0) fit
    m = r <= np.percentile(r, 10)
    for _ in range(2):
        ae, Pe = np.linalg.lstsq(np.vstack([np.ones(m.sum()), slots[m]]).T, t[m], rcond=None)[0]
        re = t - (ae + Pe * slots)
        m = re <= np.percentile(re, 10)
    ae = ae + np.percentile(re, 2)  # sit on the envelope
    fitted = ae + Pe * slots
    out["env_fps"] = round(1e9 / Pe, 5)
    out["env_vs_lsq_line"] = rstats(fitted - (a + P * slots))
    out["mean_delay_above_envelope_ms"] = round(float(np.mean(t - fitted)) / 1e6, 4)
    # split-half stability of the lattice: fit first half, predict second half vs second half's own fit
    h = len(t) // 2
    a1, P1, _ = robust_line(slots[:h], t[:h]); a2, P2, _ = robust_line(slots[h:], t[h:])
    pred = (a1 + P1 * slots[h:]) - (a2 + P2 * slots[h:])
    out["split_half_extrapolation_ms"] = {"mean": round(float(np.mean(pred)) / 1e6, 4),
                                          "end": round(float(pred[-1]) / 1e6, 4),
                                          "ppm_diff": round(float((P1 - P2) / P2 * 1e6), 2)}
    return out, slots, fitted


def unwrap32(v):
    v = np.asarray(v, np.int64)
    d = np.diff(v)
    d = np.where(d < -(1 << 31), d + (1 << 32), d)
    d = np.where(d > (1 << 31), d - (1 << 32), d)
    return np.concatenate([[v[0]], v[0] + np.cumsum(d)])


def score_vs_clock(host, clock):
    a, b, _ = robust_line(clock, host)
    return a, b, rstats(np.asarray(host, float) - (a + b * np.asarray(clock, float)))



def _dshow_slots(post, block, p_known=None):
    """Slot DirectShow frames.  OpenCV DSHOW SampleCB keeps the first sample that arrives after the previous
    retrieve() consumed its frame and discards later ones until the next retrieve (cap_dshow.cpp 703-716, 1551-1590).
    So frame k arrived in (post_retrieve[k-1], post_retrieve[k]].  Fresh frames (retrieve blocked > 2 ms) arrived
    just before post_retrieve; their lower envelope gives the arrival lattice env(s) = ae + Pe*s.  Each frame gets the
    first lattice slot whose arrival range [env(s), env(s)+dmax] can follow post_retrieve[k-1]."""
    fresh = block > 2.0
    if fresh.sum() < 30:
        sc, s, f = lattice_scores(post)
        return s, f, {"method": "all-frames lattice (too few fresh frames)", "fresh": int(fresh.sum())}
    # period search starts from the camera's period measured in its free-running runs when known (camera crystals
    # are stable to ppm), else from the mean spacing of all frames (>= true period)
    if p_known:
        # Lockstep runs: the camera's frame period does not depend on the host, so fix P to the period measured in
        # its free-running runs and find only the phase: the densest 16 ms window of fresh stamps modulo P.
        Pe = float(p_known)
        x = np.mod(post[fresh] - post[0], Pe)
        nb = int(Pe // 0.25e6); h = np.bincount(np.minimum((x / 0.25e6).astype(int), nb - 1), minlength=nb)
        w = 64
        hc = np.concatenate([h, h[:w]]); cs = np.concatenate([[0], np.cumsum(hc)])
        start = int(np.argmax(cs[w:w + nb] - cs[:nb])) * 0.25e6
        s_f = np.floor((post[fresh] - post[0] - start) / Pe).astype(int)
        d0 = post[fresh] - (post[0] + start + Pe * s_f)
        ae = post[0] + start + float(np.percentile(d0, 2))
        f_f = ae + Pe * s_f
    else:
        p0 = (post[-1] - post[0]) / (len(post) - 1)
        sc_f, s_f, f_f = lattice_scores(post[fresh], p0=p0)
        Pe = (f_f[-1] - f_f[0]) / (s_f[-1] - s_f[0]); ae = f_f[0] - Pe * s_f[0]
    ae -= Pe * np.ceil((ae - post[0]) / Pe + 1)  # shift slot origin before the first frame
    dly = post[fresh] - f_f  # delay of fresh frames above the envelope (shifting ae by whole periods keeps this)
    dmax = float(np.percentile(dly, 99)); dmean = float(np.median(dly))
    # Delivery is on a per-stream 16 ms grid (docs/windows_timer_resolution.md), so a slot's arrival is predictable:
    # A(s) = first grid point at or after env(s).  Grid phase from the fresh frames' post-retrieve stamps.
    g = 16.0e6
    gs = np.linspace(15.98e6, 16.02e6, 81)
    cc = [np.abs(np.mean(np.exp(2j * np.pi * post[fresh] / x))) for x in gs]
    g = float(gs[int(np.argmax(cc))])
    phi = np.angle(np.mean(np.exp(2j * np.pi * post[fresh] / g))) / (2 * np.pi) * g
    grid_coh = float(max(cc))

    def arrival(sl):
        e = ae + Pe * sl - 0.5e6  # half a millisecond of slack below the envelope
        return phi + g * np.ceil((e - phi) / g)
    s = np.empty(len(post), int); amb = 0; late = 0; agree = 0
    for k in range(len(post)):
        L = post[k - 1] + 1.0e6 if k else post[k] - Pe  # previous retrieve end (+1 ms: delivered after it)
        s_rule = int(np.ceil((L - dmax - ae) / Pe)) - 1
        while arrival(s_rule) <= L:
            s_rule += 1
        if k and s_rule <= s[k - 1]:
            s_rule = s[k - 1] + 1
        if fresh[k]:
            sk = int(np.round((post[k] - dmean - ae) / Pe))
            agree += int(sk == s_rule)
        else:
            sk = s_rule
            e1 = ae + Pe * sk
            if abs(e1 - phi - g * np.round((e1 - phi) / g)) < 1.0e6:  # envelope within 1 ms of a grid point
                amb += 1
        if k and sk <= s[k - 1]:
            sk = s[k - 1] + 1
        if ae + Pe * sk > post[k] + 1e6:
            late += 1
        s[k] = sk
    s0 = s[0]
    fitted = ae + Pe * s
    return s - s0, fitted, {"method": "dshow window rule", "fresh": int(fresh.sum()), "dmax_ms": round(dmax / 1e6, 3),
                            "dmedian_ms": round(dmean / 1e6, 3), "ambiguous_stale": amb, "grid_ms": round(g / 1e6, 4),
                            "grid_coherence": round(grid_coh, 3), "rule_agrees_on_fresh": round(agree / max(1, int(fresh.sum())), 4),
                            "slot_after_retrieve_conflicts": late, "env_fps": round(1e9 / Pe, 5)}


def dshow_slots(post, block, p_known=None):
    """Try the estimated-period and (when known) the fixed-period variants; keep the one whose window rule agrees
    best with the direct slots of fresh frames (the only internal validation available without ground truth)."""
    best = _dshow_slots(post, block, None)
    best[2]["variant"] = "estimated period"
    if p_known:
        alt = _dshow_slots(post, block, p_known)
        alt[2]["variant"] = "period fixed from free-running runs"
        est_ppm = abs(1e9 / best[2].get("env_fps", 1e9 / p_known) - p_known) / p_known * 1e6
        best[2]["estimated_vs_known_period_ppm"] = round(est_ppm, 1)
        # a camera crystal does not change rate by > 200 ppm between runs (free runs agree to < 20 ppm), so an
        # estimated period that far off means the slots follow the gate (the peer camera), not this camera
        if est_ppm > 200 or alt[2].get("rule_agrees_on_fresh", 0) > best[2].get("rule_agrees_on_fresh", 0) + 0.02:
            alt[2]["estimated_vs_known_period_ppm"] = round(est_ppm, 1)
            alt[2]["other_variant_agreement"] = best[2].get("rule_agrees_on_fresh")
            return alt
        best[2]["other_variant_agreement"] = alt[2].get("rule_agrees_on_fresh")
    return best

# ----------------------------------------------------------------------------------------------- DShow
def load_dshow(results: Path):
    runs = {}
    for sj in sorted(results.glob("*.session.json")):
        s = json.loads(sj.read_text())
        if "mode" not in s:
            continue
        cams = {}
        for info in s.get("cameras", []):
            vp = info["vidpid"]
            csvp = results / f"{s['label']}_{vp.replace(':', '')}.frames.csv"
            if not csvp.exists():
                cams[vp] = {"error": info.get("error", "no csv"), "info": info}
                continue
            with open(csvp) as fh:
                rows = list(csv.DictReader(fh))
            cols = {k: np.array([int(float(r[k])) for r in rows], np.int64) for k in rows[0] if k != "brightness"}
            cols["brightness"] = np.array([float(r["brightness"]) for r in rows])
            cams[vp] = {"cols": cols, "info": info}
        runs[s["label"]] = {"session": s, "cams": cams}
    return runs


def analyze_dshow_run(label, run):
    s = run["session"]
    res = {"mode": s["mode"], "cameras": {}}
    per = {}
    go = s.get("go_ns", 0)
    for vp, c in run["cams"].items():
        name = VIDPID_NAME.get(vp, vp)
        if "cols" not in c:
            res["cameras"][name] = {"error": c["error"]}
            continue
        k = c["cols"]
        keep = k["post_retrieve_ns"] >= go + DSHOW_TRIM_S * 1e9
        keep, stalls = longest_run(k["post_retrieve_ns"], keep)
        idx = k["frame_number"][keep]
        mid = ((k["pre_grab_ns"] + k["post_grab_ns"]) // 2)[keep].astype(float)
        post = k["post_retrieve_ns"][keep].astype(float)
        block = (k["post_retrieve_ns"] - k["pre_retrieve_ns"])[keep] / 1e6
        gate_wait = (k["gate_open_ns"] - k["loop_start_ns"])[keep] / 1e6
        loop_after = (k["count_set_ns"] - k["post_retrieve_ns"])[keep] / 1e6
        rec = (k["post_record_ns"] - k["pre_record_ns"])[keep] / 1e6
        fresh = block > 2.0
        # slots: DirectShow semantics (see dshow_slots), lattice from fresh frames only
        slots, fitted, slot_info = dshow_slots(post, block, KNOWN_P.get(name) if s["mode"] == "skellycam" else None)
        slot_info["period_hint_ms"] = round(KNOWN_P[name] / 1e6, 6) if (s["mode"] == "skellycam" and name in KNOWN_P) else None
        sc_post, _, _ = lattice_scores(post, slots=slots)
        sc_post["slotting"] = slot_info
        sc_post["resid_vs_envelope_lattice"] = rstats(post - fitted)
        sc_mid, _, _ = lattice_scores(mid, slots=slots)
        sc_post_fresh = rstats((post - fitted)[fresh] if fresh.sum() > 10 else post - fitted)
        b = c["info"].get("brightness_mean", {})
        bri = k["brightness"][keep]; bri = bri[bri >= 0]
        r = {"frames": int(keep.sum()), "stalls_gt_0p5s": stalls, "post_retrieve": sc_post, "grab_midpoint": {k2: v for k2, v in sc_mid.items()
             if k2 in ("resid", "fps", "drops")},
             "post_retrieve_minus_envelope_fresh_only": sc_post_fresh,
             "retrieve_block_ms": {"median": round(float(np.median(block)), 3), "p05": round(float(np.percentile(block, 5)), 3),
                                   "stale_frac_lt2ms": round(float(np.mean(block <= 2.0)), 4)},
             "gate_wait_ms": {"median": round(float(np.median(gate_wait)), 3), "p95": round(float(np.percentile(gate_wait, 95)), 3),
                              "max": round(float(gate_wait.max()), 3)},
             "post_retrieve_to_count_set_ms": {"median": round(float(np.median(loop_after)), 3),
                                               "p95": round(float(np.percentile(loop_after, 95)), 3)},
             "record_ms_median": round(float(np.median(rec)), 3),
             "grab_mid_minus_envelope_ms": rstats(mid - fitted),
             "brightness_before_after_exposure_reset": b, "brightness_run_median": round(float(np.median(bri)), 2) if len(bri) else None,
             "readback": c["info"].get("readback"), "writer": (c["info"].get("writer") or {}).get("codec")}
        res["cameras"][name] = r
        per[name] = {"idx": idx, "mid": mid, "post": post, "slots": slots, "fitted": fitted, "P": sc_post["period_ms"]}
    res["pairs"] = pair_analysis(per, stored_key="mid" if s["mode"] == "skellycam" else "post")
    return res


def pair_analysis(per, stored_key):
    names = list(per)
    out = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            A, B = per[names[i]], per[names[j]]
            common, ia, ib = np.intersect1d(A["idx"], B["idx"], return_indices=True)
            if len(common) < 20:
                continue
            d_stored = (A[stored_key][ia] - B[stored_key][ib]) / 1e6
            d_true = (A["fitted"][ia] - B["fitted"][ib]) / 1e6
            err = d_stored - d_true
            q = lambda v: {"median": round(float(np.median(v)), 3), "p05": round(float(np.percentile(v, 5)), 3),
                           "p95": round(float(np.percentile(v, 95)), 3), "min": round(float(v.min()), 3),
                           "max": round(float(v.max()), 3), "std": round(float(np.std(v)), 3),
                           "first": round(float(v[0]), 3), "last": round(float(v[-1]), 3)}
            # nearest-neighbour pairing by fitted (lattice) time instead of by index
            fa, fb = A["fitted"], B["fitted"]
            pos = np.clip(np.searchsorted(fb, fa), 1, len(fb) - 1)
            nn = np.where(np.abs(fa - fb[pos - 1]) < np.abs(fa - fb[pos]), fb[pos - 1], fb[pos])
            d_nn = (fa - nn) / 1e6
            out[f"{names[i]}-{names[j]}"] = {
                "frames_paired_by_index": int(len(common)),
                "stored_stamp_diff_ms": q(d_stored),
                "lattice_time_diff_by_index_ms": q(d_true),
                "stored_minus_lattice_ms": q(err),
                "abs_lattice_diff_by_index_ms": {"median": round(float(np.median(np.abs(d_true))), 3),
                                                 "p95": round(float(np.percentile(np.abs(d_true), 95)), 3)},
                "nearest_neighbour_by_lattice_ms": {"abs_median": round(float(np.median(np.abs(d_nn))), 3),
                                                    "abs_max": round(float(np.abs(d_nn).max()), 3)},
                "note": "lattice = lower-envelope fit of post-retrieve (DShow) or MF sample time; includes any difference in the two cameras' constant latency (unmeasured)",
            }
    return out



def longest_run(t_ns, keep, gap_s=0.5):
    """Restrict keep to the longest stretch without a gap > gap_s (camera stalls); return mask and stall list."""
    t = np.asarray(t_ns, float)
    idx = np.where(keep)[0]
    if len(idx) < 2:
        return keep, []
    gaps = np.where(np.diff(t[idx]) > gap_s * 1e9)[0]
    stalls = [{"at_s": round(float((t[idx[g]] - t[idx[0]]) / 1e9), 2), "gap_s": round(float((t[idx[g + 1]] - t[idx[g]]) / 1e9), 3)} for g in gaps]
    if not len(gaps):
        return keep, []
    bounds = np.concatenate([[0], gaps + 1, [len(idx)]])
    j = int(np.argmax(np.diff(bounds)))
    m = np.zeros_like(keep)
    m[idx[bounds[j]:bounds[j + 1]]] = True
    return m, stalls

# ----------------------------------------------------------------------------------------------- MF
def name_from_key(key):
    k = key.lower()
    for vp, n in VIDPID_NAME.items():
        v, p = vp.lower().split(":")
        if f"vid_{v}_pid_{p}" in k:
            return n
    return key


def analyze_mf_run(d: Path):
    res = {"cameras": {}}
    per = {}
    for fj in sorted(d.glob("*.frames.jsonl")):
        key = fj.name.split(".")[0]
        name = name_from_key(key)
        L = [json.loads(x) for x in fj.read_text().splitlines() if x.strip()]
        if len(L) < 50:
            res["cameras"][name] = {"error": f"only {len(L)} frames"}
            continue
        arr = np.array([x["host_arrival_ns"] for x in L], float)
        st = np.array([x["os_timestamp_ns"] for x in L], float)
        call = np.array([x["readsample_call_ns"] for x in L], float)
        seq = np.array([x["seq"] for x in L])
        keep = arr >= arr[0] + MF_TRIM_S * 1e9
        keep, stalls = longest_run(st, keep)
        meta = [(x.get("meta_items") or [{}])[0].get("_top") if x.get("meta_items") else None for x in L]
        has_meta = np.array([m is not None for m in meta])
        r = {"frames_total": len(L), "frames_scored": int(keep.sum()), "frames_with_uvc_meta": int(has_meta.sum()),
             "stalls_gt_0p5s": stalls}
        sc_st, slots, fitted = lattice_scores(st[keep])
        sc_arr, _, _ = lattice_scores(arr[keep], slots=slots)
        r["sample_time"] = sc_st
        r["arrival"] = {k: v for k, v in sc_arr.items() if k in ("resid", "fps", "drops")}
        r["arrival_minus_sample_time_ms"] = {"median": round(float(np.median(arr[keep] - st[keep])) / 1e6, 3),
                                             "p95": round(float(np.percentile(arr[keep] - st[keep], 95)) / 1e6, 3)}
        r["readsample_block_ms_median"] = round(float(np.median(arr[keep] - call[keep])) / 1e6, 3)
        sc_arr_own, slots_arr, fitted_arr = lattice_scores(arr[keep])
        if has_meta[keep].all():
            mk = [m for m, k in zip(meta, keep) if k]
            clocks = {"stc": unwrap32([m["uvc_scr_stc"] for m in mk]), "pts": unwrap32([m["uvc_pts"] for m in mk])}
            ref = {}
            for cn, cv in clocks.items():
                cv = cv.astype(float)
                # regularity of the camera clock itself on the slot lattice (ticks)
                a_c, b_c, _ = robust_line(slots, cv)
                res_ticks = cv - (a_c + b_c * slots)
                a, b, s_st = score_vs_clock(st[keep], cv)
                _, _, s_arr = score_vs_clock(arr[keep], cv)
                mapped = a + b * cv
                ref[cn] = {"implied_hz": round(1e9 / b, 1),
                           "clock_vs_lattice_resid_us": {"std": round(float(np.std(res_ticks) * b) / 1e3, 2),
                                                         "max": round(float(np.abs(res_ticks - np.median(res_ticks)).max() * b) / 1e3, 2)},
                           "sample_time_vs_clock": s_st, "arrival_vs_clock": s_arr,
                           "fitted_sample_time_lattice_vs_clock": rstats(fitted - mapped),
                           "fitted_arrival_lattice_vs_clock": rstats(fitted_arr - mapped) if len(fitted_arr) == len(mapped) else None,
                           "mapped": mapped}
            best = min(ref, key=lambda c: ref[c]["clock_vs_lattice_resid_us"]["std"])
            r["reference_clock"] = best
            # slots from the camera clock itself (reference) vs the tier-0 host-only slots
            cv = clocks[best].astype(float)
            dc = np.diff(cv); step = float(np.median(dc))
            sc_ = np.concatenate([[0], np.cumsum(np.maximum(1, np.round(dc / step)).astype(int))])
            r["clock_slots"] = {"drops": int(sc_[-1] + 1 - len(sc_)),
                                "tier0_slot_mismatches": int(np.sum((slots - slots[0]) != sc_))}
            r["clock_ref"] = {c: {k: v for k, v in x.items() if k != "mapped"} for c, x in ref.items()}
        r["arrival_own_lattice"] = {k: v for k, v in sc_arr_own.items() if k in ("resid", "fps", "drops", "ambiguous_slots")}
        res["cameras"][name] = r
        per[name] = {"idx": seq[keep], "mid": st[keep], "post": st[keep], "slots": slots, "fitted": fitted, "P": sc_st["period_ms"]}
    # MF delivers frames free-running; skellycam-style pairing would be by per-camera frame count
    for n in per:
        per[n]["idx"] = np.arange(len(per[n]["post"]))
    res["pairs"] = pair_analysis(per, stored_key="post")
    for ses in d.glob("*.session.json"):
        s = json.loads(ses.read_text())
        n = name_from_key(s["camera_key"])
        if n in res["cameras"]:
            res["cameras"][n]["exposure_control"] = s.get("controls", {}).get("exposure_log2")
            res["cameras"][n]["errors"] = s.get("errors")
    for cj in d.glob("*.controls.jsonl"):
        n = name_from_key(cj.name.split(".")[0])
        sets = [json.loads(x) for x in cj.read_text().splitlines() if '"exposure_set"' in x]
        if n in res["cameras"] and sets:
            res["cameras"][n]["exposure_reset"] = {"value": sets[0]["value_log2"], "hr": sets[0]["hr"],
                                                   "readback": sets[0]["readback_value"], "flags": sets[0]["readback_flags"],
                                                   "since_first_frame_s": sets[0]["since_first_frame_s"]}
    return res


def main():
    results = Path(sys.argv[1])
    out = {"dshow": {}, "mf": {}}
    runs = load_dshow(results)
    # pass 1: camera periods from free-running runs (no gate, every frame fresh) and MF runs
    per_cam: dict = {}
    for label, run in runs.items():
        if run["session"]["mode"] == "free":
            try:
                r = analyze_dshow_run(label, run)
                for n, c in r["cameras"].items():
                    if "post_retrieve" in c:
                        per_cam.setdefault(n, []).append(c["post_retrieve"]["period_ms"] * 1e6)
            except Exception:  # noqa: BLE001
                pass
    for n, v in per_cam.items():
        KNOWN_P[n] = float(np.median(v))
    out["known_periods_ms_from_free_runs"] = {n: round(v / 1e6, 6) for n, v in KNOWN_P.items()}
    for label, run in runs.items():
        try:
            out["dshow"][label] = analyze_dshow_run(label, run)
        except Exception as e:  # noqa: BLE001
            out["dshow"][label] = {"error": f"{type(e).__name__}: {e}"}
    for d in sorted(p for p in results.iterdir() if p.is_dir() and p.name.startswith("mf_")):
        try:
            out["mf"][d.name] = analyze_mf_run(d)
        except Exception as e:  # noqa: BLE001
            out["mf"][d.name] = {"error": f"{type(e).__name__}: {e}"}
    (results / "analysis.json").write_text(json.dumps(out, indent=1))
    # markdown summary
    print("| run | camera | fps | drops | grab-mid vs lattice std/p95/max | post-ret vs lattice std/p95/max | fitted vs own line std | stale | gate wait med/p95 |")
    print("|---|---|---|---|---|---|---|---|---|")
    f = lambda s: f"{s['std_ms']:.2f}/{s['p95_ms']:.2f}/{s['max_ms']:.2f}"
    for label, r in out["dshow"].items():
        if "error" in r:
            print(f"| {label} | ERROR {r['error']} |"); continue
        for n, c in r["cameras"].items():
            if "error" in c:
                print(f"| {label} | {n} | error: {c['error']} |"); continue
            print(f"| {label} | {n} | {c['post_retrieve']['fps']:.3f} | {c['post_retrieve']['drops']} | {f(c['grab_mid_minus_envelope_ms'])} | "
                  f"{f(c['post_retrieve']['resid_vs_envelope_lattice'])} | {c['post_retrieve']['env_vs_lsq_line']['std_ms']:.3f} | "
                  f"{c['retrieve_block_ms']['stale_frac_lt2ms']:.2f} | {c['gate_wait_ms']['median']:.1f}/{c['gate_wait_ms']['p95']:.1f} |")
    print()
    print("| run | camera | fps | drops | sample std/p95/max | arrival std/p95/max | ref clock | clock lattice std us | sample vs clock | arrival vs clock | fitted vs clock |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for label, r in out["mf"].items():
        if "error" in r:
            print(f"| {label} | ERROR {r['error']} |"); continue
        for n, c in r["cameras"].items():
            if "error" in c:
                print(f"| {label} | {n} | error: {c['error']} |"); continue
            rc = c.get("reference_clock")
            cr = c["clock_ref"][rc] if rc else None
            print(f"| {label} | {n} | {c['sample_time']['fps']:.3f} | {c['sample_time']['drops']} | {f(c['sample_time']['resid'])} | "
                  f"{f(c['arrival']['resid'])} | {rc or '-'} | {cr['clock_vs_lattice_resid_us']['std'] if cr else '-'} | "
                  f"{f(cr['sample_time_vs_clock']) if cr else '-'} | {f(cr['arrival_vs_clock']) if cr else '-'} | "
                  f"{f(cr['fitted_sample_time_lattice_vs_clock']) if cr else '-'} |")
    print()
    for kind in ("dshow", "mf"):
        for label, r in out[kind].items():
            for p, v in (r.get("pairs") or {}).items():
                print(f"{label} {p}: by-index lattice diff med {v['lattice_time_diff_by_index_ms']['median']} "
                      f"[{v['lattice_time_diff_by_index_ms']['min']}, {v['lattice_time_diff_by_index_ms']['max']}] first {v['lattice_time_diff_by_index_ms']['first']} last {v['lattice_time_diff_by_index_ms']['last']}; "
                      f"stored diff med {v['stored_stamp_diff_ms']['median']} std {v['stored_stamp_diff_ms']['std']}; "
                      f"stored-lattice std {v['stored_minus_lattice_ms']['std']} p95 {v['stored_minus_lattice_ms']['p95']} min {v['stored_minus_lattice_ms']['min']} max {v['stored_minus_lattice_ms']['max']}")


if __name__ == "__main__":
    main()
