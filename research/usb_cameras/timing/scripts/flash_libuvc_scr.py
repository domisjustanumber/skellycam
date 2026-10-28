# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Phase 2 (goal 2): UVC PTS/SCR read by libuvc straight from the payload headers (C930e on WinUSB), mapped to QPC
through the USB SOF counter, judged against a screen-flash ground truth that uses NO device timestamp; the C922
(Media Foundation, same flash run) is judged against the same display log at the same fixed image rows.

Input: a run_flash_libuvc.ps1 run dir:  display_m0/  c930e_libuvc/{frames.jsonl,usb_frame_qpc.jsonl,frame_*.jpg}
       capture/<c922>.frames.jsonl + .mjpeg (optional)

Usage:
  uv run --script research/usb_cameras/timing/scripts/flash_libuvc_scr.py --run DIR --col-c930e F --col-c922 F
      [--rows 0.3,0.5,0.7] [--gamma 2.2] [--skip-first 15] [--e-c930e-ms 7.8] [--e-c922-ms 7.8125] [--out json]
  --stdmap: only print each camera's temporal-std map (24x24 blocks, % of max) to pick columns; no fit.

Clock chain (all host times are QPC ns):
  1. USB frame clock: xHCI IOCTL samples (usb_frame + uframe/8, QPC) -> lower-envelope line t_frame(F) (QPC of the
     start of 1 ms USB frame F; the IOCTL QPC lies 0..125 us after the microframe start).
  2. Every frame carries two SCRs (first and last payload of the frame): (STC, 11-bit SOF). SOF is unwrapped to the
     full bus frame number with the payload's host callback time (must give 0 < callback - t_frame < a few ms; this
     is checked and reported) -> (STC, t_frame(SOF)) pairs.
  3. STC -> QPC: least-squares line over all pairs, +0.5 ms (STC is latched at an unknown point inside the 1 ms
     frame; residual width ~1 ms if the STC is a stable clock). Rate vs QPC in ppm; 5 s chunk slopes; residual.
  4. Sources mapped: scr_first (STC of first payload), scr_last, scr_first_sofdirect (bus frame of the first
     payload, no STC: 1 ms quantised), pts_via_stc (PTS on the STC line), host first/last payload transfer-callback
     times (and first-payload back-dated by its packet index within the 32-packet transfer), host_arrival, and
     seq_env (frame index + lower envelope of host arrival: NO device timestamp; also the GT reference).
Ground truth (per camera, per fixed ROI): fa.fit_source logic with the reference = seq_env and a FIXED gamma
(no tuning on any judged source): frames whose exposure window [X_ref+d, X_ref+d+E] contains exactly one display
transition T give the ROI exposure start w = T - E(1-f) (rising) or T - E f (falling), f = y_norm**gamma in
(0.08, 0.92). Each source X is scored by e = w - X: offset = median(e), std/MAD after removing the median only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flash_analyze as fa  # noqa: E402

af = fa.af
NS = 1e9


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.open() if l.strip()]


def load_display_robust(d: Path, period_tol_ns: float = 0.05e6) -> dict:
    """Display model that does not assume a glitch-free run. DXGI stats samples give (sync_refresh_count, sync_qpc)
    and (present_count -> present_refresh_count). A pair of consecutive stats samples is CLEAN when the
    present->refresh offset did not change between them and every refresh between them lasted P +- tol (P = median
    refresh period). Presents between the two samples of a clean pair are placed exactly (refresh index ->
    interpolated vblank time); every other present is marked unreliable, and GT frames whose exposure window touches
    an unreliable present interval are dropped. Equals fa.load_display on a glitch-free run."""
    recs = [json.loads(l) for l in (d / "display.jsonl").open()]
    ses = json.loads((d / "display.session.json").read_text())
    pres = [r for r in recs if r["type"] == "present"]
    st = [r for r in recs if r["type"] == "stats"]
    src = np.array([r["sync_refresh_count"] for r in st], float); sq = np.array([r["sync_qpc_ns"] for r in st], float)
    pc = np.array([r["present_count"] for r in st]); prc = np.array([r["present_refresh_count"] for r in st])
    off = prc - pc
    per = np.diff(sq) / np.maximum(np.diff(src), 1)
    P = float(np.median(per[np.diff(src) > 0]))
    clean_pair = (np.diff(off) == 0) & (np.abs(per - P) < period_tol_ns) & (np.diff(src) > 0)
    pcs = np.array([r["present_count"] for r in pres]); lev = np.array([r["level"] for r in pres], float)
    j = np.searchsorted(pc, pcs, side="right") - 1          # last stats sample at or before this present
    ok = (j >= 0) & (j < len(pc) - 1)
    jj = np.clip(j, 0, len(pc) - 2)
    ok &= clean_pair[jj] & (pcs <= pc[jj + 1])
    refresh = pcs + off[np.clip(j, 0, len(pc) - 1)]
    # vblank time by local interpolation of the refresh counter (exact inside a clean pair)
    t_on = np.interp(refresh, src, sq)
    order = np.argsort(t_on)
    t_on, lev, ok = t_on[order], lev[order], ok[order]
    bad_iv = []  # [start, end) of display intervals that cannot be trusted
    for i in np.flatnonzero(~ok):
        bad_iv.append((t_on[i - 1] if i > 0 else t_on[i] - 1e9, t_on[i + 1] if i + 1 < len(t_on) else t_on[i] + 1e9))
    return {"dir": str(d), "session": ses, "t_on": t_on, "level": lev, "period_ns": P, "bad_intervals": bad_iv,
            "refresh_glitches": int(np.sum(np.diff(off) != 0)), "bad_refresh_pairs": int(np.sum(~clean_pair)),
            "presents": len(pres), "unreliable_presents": int((~ok).sum()), "stats_samples": len(st)}


def frame_clock(fq_path: Path, hc_match: str = "dev_7a60") -> dict:
    recs = load_jsonl(fq_path)
    hdr = [r for r in recs if "path" in r]
    hc = next(r["hc"] for r in hdr if hc_match in r["path"].lower())
    s = [r for r in recs if r.get("hc") == hc and "usb_frame" in r]
    x = np.array([r["usb_frame"] + r["uframe"] / 8.0 for r in s])
    y = np.array([r["frame_qpc_ns"] for r in s], float)
    a, b, res = af.linfit(x, y)
    al, bl = af.lower_envelope_fit(x, y)
    hw_ok = all((r["usb_frame"] & 0x7FF) == r["hw_frame"] for r in s)
    return {"a": al, "b": bl, "n": len(s), "lsq_ns_per_frame": b, "usb_frame_vs_qpc_ppm": (1e6 / b - 1) * 1e6,
            "lsq_residual_us": af.stats(res, 1e-3), "hw_frame_is_low11_of_usb_frame": hw_ok,
            "call_duration_us": af.stats(np.array([r["call_after_ns"] - r["call_before_ns"] for r in s], float), 1e-3),
            "x0": float(x[0]), "x1": float(x[-1])}


def unwrap_sof(sof: np.ndarray, t_ref: np.ndarray, fc: dict) -> np.ndarray:
    fpred = (t_ref - fc["a"]) / fc["b"]
    return sof + 2048 * np.round((fpred - sof) / 2048.0)


def gt_fixed(Xref, y, disp, E, gamma):
    """ground truth exposure start per frame from the display log + ROI brightness; Xref only selects frames."""
    dc = fa.cumulative(disp)
    ok = np.isfinite(y) & np.isfinite(Xref)
    best = (-2.0, 0.0)
    for d in np.arange(-400e6, 100e6, 0.5e6):
        p = fa.window_mean(dc, Xref + d, E)
        c = np.corrcoef(p[ok], y[ok])[0, 1] if np.std(p[ok]) > 0 else -1
        if c > best[0]:
            best = (c, d)
    for d in np.arange(best[1] - 1e6, best[1] + 1e6, 0.02e6):
        p = fa.window_mean(dc, Xref + d, E)
        c = np.corrcoef(p[ok], y[ok])[0, 1]
        if c > best[0]:
            best = (c, d)
    corr, d0 = best
    lo, hi = np.nanpercentile(y, 2), np.nanpercentile(y, 98)
    yn = np.clip((y - lo) / (hi - lo), 0, 1)
    t, s, _ = dc
    tr_t = t[1:][np.diff(s) != 0]; tr_d = np.diff(s)[np.diff(s) != 0]
    w0 = Xref + d0
    i0 = np.searchsorted(tr_t, w0); i1 = np.searchsorted(tr_t, w0 + E)
    good = (i1 - i0 == 1) & ok
    for b0, b1 in disp.get("bad_intervals", []):  # robust display model: drop windows touching unreliable presents
        good &= ~((w0 - 2e6 < b1) & (w0 + E + 2e6 > b0))
    k = np.flatnonzero(good)
    Tk = tr_t[i0[k]]; up = tr_d[i0[k]] > 0
    f = yn[k] ** gamma
    sel = (f > 0.08) & (f < 0.92)
    w = np.where(up, Tk - E * (1 - f), Tk - E * f)
    return {"corr": float(corr), "ref_offset_ms": d0 / 1e6, "k": k[sel], "w": w[sel], "up": up[sel], "f": f[sel]}


def score(X, gt) -> dict:
    e = gt["w"] - X[gt["k"]]
    m = np.isfinite(e)
    e = e[m]
    if e.size < 8:
        return {"n": int(e.size)}
    med = np.median(e)
    r = e - med
    up = gt["up"][m]
    return {"n": int(e.size), "offset_ms": med / 1e6, "err_std_us": float(np.std(r) / 1e3),
            "err_mad_sigma_us": float(1.4826 * np.median(np.abs(r)) / 1e3),
            "err_p05_p95_us": [float(np.percentile(r, 5) / 1e3), float(np.percentile(r, 95) / 1e3)],
            "rising_mean_us": float(r[up].mean() / 1e3) if up.any() else None,
            "falling_mean_us": float(r[~up].mean() / 1e3) if (~up).any() else None}


def quantization(X: np.ndarray, seq: np.ndarray) -> dict:
    """residual vs a periodic model (frame index, least squares) and the strongest timing grid 0.5..40 ms"""
    m = np.isfinite(X)
    a, b, r = af.linfit(seq[m].astype(float), X[m])
    t = X[m] - X[m][0]
    grid = np.arange(0.5e6, 40e6, 0.005e6)
    conc = np.array([abs(np.mean(np.exp(2j * np.pi * t / g))) for g in grid])
    # skip grids near the frame period and its integer fractions/multiples (a periodic source concentrates there)
    P = b
    near = np.zeros_like(grid, bool)
    for q in (1, 2, 3, 4, 5, 6, 8):
        near |= np.abs(grid - P / q) < 0.15e6
    near |= np.abs(grid - P) < 0.3e6
    cc = np.where(near, 0, conc)
    k = int(np.argmax(cc))
    return {"period_ms": b / 1e6, "residual_std_us": float(np.std(r) / 1e3),
            "residual_p01_p99_ms": [float(np.percentile(r, 1) / 1e6), float(np.percentile(r, 99) / 1e6)],
            "best_grid_ms": float(grid[k] / 1e6), "grid_phase_concentration": float(cc[k]),
            "conc_at_1ms": float(abs(np.mean(np.exp(2j * np.pi * t / 1e6)))),
            "conc_at_4ms": float(abs(np.mean(np.exp(2j * np.pi * t / 4e6)))),
            "conc_at_16ms": float(np.max([abs(np.mean(np.exp(2j * np.pi * t / g))) for g in np.arange(15.5e6, 16.7e6, 0.005e6)]))}


def decode_dir(files: list[Path]) -> np.ndarray:
    ims = [cv2.imread(str(p), cv2.IMREAD_REDUCED_GRAYSCALE_8) for p in files]
    return np.stack([i.astype(np.float32) for i in ims])


def decode_mjpeg(rows, mj: Path) -> np.ndarray:
    data = mj.read_bytes()
    return np.stack([cv2.imdecode(np.frombuffer(data, np.uint8, r["payload_bytes"], r["mjpeg_offset"]),
                                  cv2.IMREAD_REDUCED_GRAYSCALE_8).astype(np.float32) for r in rows])


def stdmap(stack: np.ndarray) -> list[list[int]]:
    sd = stack.std(0)
    H, W = sd.shape
    g = 12
    out = []
    for i in range(g):
        row = []
        for j in range(g):
            row.append(float(sd[i * H // g:(i + 1) * H // g, j * W // g:(j + 1) * W // g].mean()))
        out.append(row)
    mx = max(max(r) for r in out)
    return [[int(round(100 * v / mx)) for v in r] for r in out]


def roi_series(stack, rf, cf):
    N, H, W = stack.shape
    bh, bw = max(2, H // 24), max(2, W // 24)
    r0 = int(np.clip(round(rf * H - bh / 2), 0, H - bh)); c0 = int(np.clip(round(cf * W - bw / 2), 0, W - bw))
    return stack[:, r0:r0 + bh, c0:c0 + bw].reshape(N, -1).mean(1), [r0, r0 + bh, c0, c0 + bw]


def c930e_sources(rows, fc) -> tuple[dict, dict]:
    g = lambda k: np.array([r[k] for r in rows], dtype=np.float64)  # noqa: E731
    seq = g("seq"); host = g("host_arrival_ns")
    hf = g("host_first_payload_ns"); hl = g("host_last_payload_ns")
    ppt = g("packets_per_transfer"); fi = g("first_payload_packet_idx"); li = g("last_payload_packet_idx")
    stc1 = af.unwrap(np.array([r["uvc_scr_stc_first"] for r in rows], np.int64), 32).astype(float)
    stc2 = af.unwrap(np.array([r["uvc_scr_stc"] for r in rows], np.int64), 32).astype(float)
    # common unwrap base for both STC series
    stc2 += np.round((stc1[0] - stc2[0]) / 2 ** 32) * 2 ** 32 if abs(stc1[0] - stc2[0]) > 2 ** 31 else 0
    pts = af.unwrap(np.array([r["uvc_pts"] for r in rows], np.int64), 32).astype(float)
    if abs(pts[0] - stc1[0]) > 2 ** 31:
        pts += np.round((stc1[0] - pts[0]) / 2 ** 32) * 2 ** 32
    sof1 = unwrap_sof(g("uvc_scr_sof_first"), hf, fc); sof2 = unwrap_sof(g("uvc_scr_sof"), hl, fc)
    tsof1 = fc["a"] + fc["b"] * sof1; tsof2 = fc["a"] + fc["b"] * sof2
    clk = {}
    clk["callback_minus_sof_frame_ms"] = {"first": af.stats(hf - tsof1, 1e-6), "last": af.stats(hl - tsof2, 1e-6)}
    S = np.concatenate([stc1, stc2]); T = np.concatenate([tsof1, tsof2])
    c, d, res = af.linfit(S, T)
    clk["stc_hz_vs_qpc"] = 1e9 / d
    clk["stc_ppm_vs_nominal_30MHz_qpc_timebase"] = (1e9 / d / 30e6 - 1) * 1e6
    clk["stc_line_residual_us"] = af.stats(res, 1e-3)
    clk["stc_line_residual_range_us"] = [float(res.min() / 1e3), float(res.max() / 1e3)]
    # stability: 5 s chunks (by host time)
    t0 = host[0]; chunks = []
    for c0 in np.arange(0, (host[-1] - t0) / NS - 4.99, 5.0):
        m = ((hf - t0) / NS >= c0) & ((hf - t0) / NS < c0 + 5)
        if m.sum() > 50:
            cc, dd, rr = af.linfit(np.concatenate([stc1[m], stc2[m]]), np.concatenate([tsof1[m], tsof2[m]]))
            chunks.append({"t_s": float(c0), "ppm": float((1e9 / dd / 30e6 - 1) * 1e6),
                           "offset_vs_global_us_at_mid": float(((cc + dd * np.median(stc1[m])) - (c + d * np.median(stc1[m]))) / 1e3),
                           "resid_std_us": float(np.std(rr) / 1e3)})
    clk["stc_chunks_5s"] = chunks
    # STC per-frame step (does the STC show the PTS-style 2-period jumps?)
    dstc = np.diff(stc1) / 30e3
    clk["stc_first_step_ms"] = af.stats(dstc)
    dpts = np.diff(pts)
    medp = np.median(dpts)
    clk["pts_step_ticks_median"] = float(medp)
    clk["pts_steps_not_1x"] = [{"idx": int(i), "ratio": float(dpts[i] / medp)} for i in np.flatnonzero(np.abs(dpts / medp - 1) > 0.3)]
    stc_ms = lambda x: (c + d * x + 0.5e6)  # noqa: E731
    clk["stc_first_minus_pts_ms"] = af.stats((stc1 - pts) / 30e3)
    srcs = {
        "host_arrival": host,
        "libuvc_capture_time_finished": g("os_timestamp_ns"),
        "host_first_payload": hf,
        "host_last_payload": hl,
        "host_first_payload_backdated": hf - (ppt - 1 - fi) * 125e3,
        "host_last_payload_backdated": hl - (ppt - 1 - li) * 125e3,
        "scr_first_sofdirect": tsof1 + 0.5e6,
        "scr_first_stc": stc_ms(stc1),
        "scr_last_stc": stc_ms(stc2),
        "pts_via_stc": stc_ms(pts),
    }
    a2, b2 = af.lower_envelope_fit(seq, host); srcs["seq_env"] = a2 + b2 * seq
    a3, b3, _ = af.linfit(seq, srcs["scr_first_stc"]); srcs["seq_fit_to_scr_first"] = a3 + b3 * seq
    clk["frame_period_ms_scr_first"] = b3 / 1e6
    clk["frame_period_ms_seq_env_host"] = b2 / 1e6
    clk["pts_period_ms_on_stc_clock"] = medp * d / 1e6
    return srcs, clk


def c922_sources(rows) -> tuple[dict, dict]:
    ana = af.analyze(rows, 30e6 * 10, 0, 32)  # 300 MHz nominal (phase 1: C922 PTS/STC clock)
    arr = ana.pop("_arrays")
    srcs = {}
    for k, X in arr["sources"].items():
        Xf = X.astype(float); m = arr["masks"].get(k)
        if m is not None:
            Xf[~m] = np.nan
        srcs[k] = Xf
    seq = np.array([r["seq"] for r in rows], float)
    a2, b2 = af.lower_envelope_fit(seq, arr["host"].astype(float)); srcs["seq_env"] = a2 + b2 * seq
    return srcs, {"device_clock": ana.get("device_clock")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--col-c930e", type=float, default=0.5); ap.add_argument("--col-c922", type=float, default=0.75)
    ap.add_argument("--rows", default="0.3,0.5,0.7"); ap.add_argument("--gamma", type=float, default=2.2)
    ap.add_argument("--skip-first", type=int, default=15)
    ap.add_argument("--e-c930e-ms", type=float, default=7.8); ap.add_argument("--e-c922-ms", type=float, default=7.8125)
    ap.add_argument("--stdmap", action="store_true"); ap.add_argument("--out")
    a = ap.parse_args()
    run = Path(a.run)
    rows_frac = [float(v) for v in a.rows.split(",")]
    res = {"test": "flash_libuvc_scr", "hostname": socket.gethostname(), "platform": sys.platform,
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(), "command": " ".join(sys.argv),
           "environment": {"numpy": np.__version__, "opencv": cv2.__version__}, "run": str(run),
           "params": vars(a), "cameras": {}}
    disp = load_display_robust(run / "display_m0")
    res["display"] = {k: v for k, v in disp.items() if k not in ("t_on", "level", "bad_intervals")}
    res["display"]["model"] = "load_display_robust (presents outside clean stats pairs excluded from GT)"
    cams = {}
    # ---- C930e (libuvc) ----
    ud = run / "c930e_libuvc"
    rows = load_jsonl(ud / "frames.jsonl")[a.skip_first:]
    files = [ud / f"frame_{r['seq']:05d}.jpg" for r in rows]
    keep = [i for i, p in enumerate(files) if p.exists()]
    rows = [rows[i] for i in keep]; files = [files[i] for i in keep]
    fc = frame_clock(ud / "usb_frame_qpc.jsonl")
    cams["c930e_libuvc"] = {"rows": rows, "stack": decode_dir(files), "col": a.col_c930e, "E": a.e_c930e_ms * 1e6}
    res["usb_frame_clock"] = {k: v for k, v in fc.items()}
    # ---- C922 (MF) ----
    cj = sorted((run / "capture").glob("*085c*.frames.jsonl")) if (run / "capture").exists() else []
    if cj:
        r2 = af.load(cj[0])[a.skip_first:]
        cams["c922_mf"] = {"rows": r2, "stack": decode_mjpeg(r2, cj[0].with_name(cj[0].name.replace(".frames.jsonl", ".mjpeg"))),
                           "col": a.col_c922, "E": a.e_c922_ms * 1e6}
    if a.stdmap:
        for k, c in cams.items():
            print(k, "temporal std per 12x12 block (% of max):")
            for r in stdmap(c["stack"]):
                print("  " + " ".join(f"{v:3d}" for v in r))
        return 0
    for k, c in cams.items():
        if k == "c930e_libuvc":
            srcs, clk = c930e_sources(c["rows"], fc)
        else:
            srcs, clk = c922_sources(c["rows"])
        seq = np.array([r["seq"] for r in c["rows"]], float)
        out = {"frames": len(c["rows"]), "E_ms": c["E"] / 1e6, "col_frac": c["col"], "clock": clk,
               "quantization": {n: quantization(X, seq) for n, X in srcs.items() if np.isfinite(X).sum() > 50},
               "rows": []}
        # GT-free cross-check: two INDEPENDENT measurements of the same event (device STC/SOF vs host transfer
        # callback back-dated by packet index) -> std of their per-frame difference bounds both their noises
        pairs = [("scr_first_stc", "host_first_payload_backdated"), ("scr_first_sofdirect", "host_first_payload_backdated"),
                 ("scr_first_stc", "host_first_payload"), ("scr_first_stc", "host_arrival"), ("scr_first_stc", "pts_via_stc"),
                 ("scr_first_stc", "seq_fit_to_scr_first"), ("host_first_payload_backdated", "seq_env"),
                 ("uvc_pts_mapped_direct", "seq_env"), ("os_timestamp", "host_arrival"), ("uvc_pts_mapped_direct", "host_arrival")]
        pw = {}
        for p1, p2 in pairs:
            if p1 in srcs and p2 in srcs:
                dd = srcs[p2] - srcs[p1]; mk = np.isfinite(dd)
                tt = (srcs[p1][mk] - srcs[p1][mk][0]) / NS; dd = dd[mk]
                sl = np.polyfit(tt, dd, 1)[0] / 1e3 if dd.size > 10 else None
                pw[f"{p2} - {p1}"] = {"median_ms": float(np.median(dd) / 1e6), "std_us": float(np.std(dd) / 1e3),
                                      "trend_us_per_s": float(sl) if sl is not None else None,
                                      "detrended_std_us": float(np.std(dd - np.polyval(np.polyfit(tt, dd, 1), tt)) / 1e3),
                                      "mad_sigma_us": float(1.4826 * np.median(np.abs(dd - np.median(dd))) / 1e3),
                                      "p01_p99_ms": [float(np.percentile(dd, 1) / 1e6), float(np.percentile(dd, 99) / 1e6)]}
        out["pairwise_gt_free"] = pw
        print(f"== {k}: {len(c['rows'])} frames, E={c['E']/1e6} ms, col={c['col']}")
        for n_, v_ in pw.items():
            print(f"   pair {n_:55s} median={v_['median_ms']:8.3f} ms std={v_['std_us']:8.1f} us")
        for rf in rows_frac:
            y, box = roi_series(c["stack"], rf, c["col"])
            gt = gt_fixed(srcs["seq_env"], y, disp, c["E"], a.gamma)
            ent = {"row_frac": rf, "box_r0r1c0c1": box, "roi_temporal_std": float(np.std(y)), "gt_corr": gt["corr"],
                   "gt_n": int(gt["k"].size), "gt_frames_index_range": [int(gt["k"].min()), int(gt["k"].max())] if gt["k"].size else None,
                   "sources": {n: score(X, gt) for n, X in srcs.items()}}
            out["rows"].append(ent)
            print(f"  row {rf}: corr={gt['corr']:.4f} gt_n={gt['k'].size} roi_std={np.std(y):.1f}")
            for n, s in ent["sources"].items():
                if s.get("n", 0) >= 8:
                    print(f"     {n:32s} off={s['offset_ms']:9.3f} ms std={s['err_std_us']:8.1f} us mad={s['err_mad_sigma_us']:8.1f} n={s['n']}")
        res["cameras"][k] = out
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
