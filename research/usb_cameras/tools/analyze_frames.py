# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26"]
# ///
"""Schema-driven per-frame timestamp analysis (shared tool; works on output of any capture backend).

Usage:
    uv run --script research/usb_cameras/tools/analyze_frames.py FRAMES.jsonl [FRAMES2.jsonl ...]
        [--out result.json] [--device-clock-hz HZ] [--skip-first N] [--scr-window 32]

Input: JSON Lines following research/usb_cameras/README.md "Per-frame log schema". Optional extra fields that are
used when present:
    uvc_eof_pts / uvc_eof_scr_stc / uvc_eof_scr_sof   header of the LAST payload of the frame (Windows metadata)
    uvc_host_sof                                         host USB frame number sampled when the SCR was received
    uvc_host_sof_ns                                      host monotonic ns at which uvc_host_sof was sampled (Linux
                                                         metadata node `ns` field) -> enables the exact Linux mapping
    any other *_ns integer field                         treated as an extra host-clock timestamp source
The Windows MF tool (timing/src/mf_uvc_timing.cpp) nests UVC fields in meta_items[*]._top; they are hoisted here.

Computes, per camera log:
  * inter-frame interval mean/std/min/max for every timestamp source, dropped-frame count
  * jitter of each source vs a fitted periodic clock t = a + P*n (n = frame slot, robust to drops) -> the source with
    the smallest residual is the least noisy estimate of the (periodic) sensor capture instants
  * offsets host_arrival - source (mean/std/min/max)
  * device clock: frequency estimated from PTS vs host time, drift in ppm vs the nominal frequency (dwClockFrequency if
    known, else nearest "round" frequency, flagged as assumed); STC-vs-SOF frequency (device clock in USB-bus time);
    USB SOF vs host clock ppm
  * PTS->host mapping following Linux uvc_video_clock_update() (drivers/media/usb/uvc/uvc_video.c): PTS->SOF through a
    sliding window of (STC, SOF) pairs, then SOF->host through (host SOF, host time) pairs. Where host SOF is not
    available (Windows usbvideo metadata has none) the second step uses a lower-envelope fit of device SOF vs host
    arrival time, which is labelled as such.
  * device-internal latency STC-PTS (capture start -> first byte on the bus) in ms
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import socket
import sys
from pathlib import Path

import numpy as np

ROUND_CLOCKS = [1e6, 2e6, 10e6, 12e6, 15e6, 24e6, 25e6, 27e6, 30e6, 33.333333e6, 40e6, 48e6, 50e6, 60e6, 90e6, 96e6, 100e6, 150e6, 200e6, 300e6, 1e9]


def load(path: Path) -> list[dict]:
    rows = []
    with path.open("rb") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            for it in r.get("meta_items", []) or []:
                top = it.get("_top")
                if top:
                    for k, v in top.items():
                        r.setdefault(k, v)
            if r.get("os_timestamp_ns") is None and r.get("mf_sample_time_100ns") is not None:
                r["os_timestamp_ns"] = int(r["mf_sample_time_100ns"]) * 100  # MF sample time: QPC-based 100 ns
                r["os_timestamp_source"] = "mf_sample_time"
            if "is_valid_jpeg" not in r and "jpeg_soi" in r:
                r["is_valid_jpeg"] = bool(r.get("jpeg_soi") and r.get("jpeg_eoi"))
            rows.append(r)
    rows.sort(key=lambda r: r.get("seq", 0))
    return rows


def unwrap(x: np.ndarray, bits: int) -> np.ndarray:
    """Unwrap a counter that rolls over at 2**bits (assumes successive samples < half range apart)."""
    m = 1 << bits
    d = np.diff(x.astype(np.int64))
    d = (d + m // 2) % m - m // 2
    return np.concatenate([[int(x[0])], int(x[0]) + np.cumsum(d)]).astype(np.int64)


def stats(a: np.ndarray, scale: float = 1.0) -> dict:
    a = np.asarray(a, dtype=float) * scale
    if a.size == 0:
        return {}
    return {"n": int(a.size), "mean": float(a.mean()), "std": float(a.std(ddof=1) if a.size > 1 else 0.0),
            "min": float(a.min()), "max": float(a.max()), "median": float(np.median(a)),
            "p05": float(np.percentile(a, 5)), "p95": float(np.percentile(a, 95))}


def estimate_period(t_ns: np.ndarray, guess_ns: float) -> float:
    """Periodogram search for the frame period: maximise |mean(exp(2*pi*i*t/P))| over P in [0.8, 1.25]*guess.
    Robust to dropped frames and to timestamp quantisation (e.g. Windows isoch URB granularity)."""
    t = (t_ns - t_ns[0]).astype(np.float64)
    best_p, best_s = guess_ns, -1.0
    for lo, hi, n in ((0.8, 1.25, 4001), (None, None, 2001)):
        if lo is None:
            span = guess_ns * 0.45 / max(1.0, t[-1] / guess_ns)  # +-0.45 slot over the run
            cands = np.linspace(best_p - span, best_p + span, n)
        else:
            cands = np.linspace(guess_ns * lo, guess_ns * hi, n)
        for P in cands:
            sc = abs(np.mean(np.exp(2j * np.pi * t / P)))
            if sc > best_s:
                best_s, best_p = sc, P
    return best_p


def periodic_fit(t_ns: np.ndarray, nominal_period_ns: float | None = None) -> dict:
    """Fit t = a + P*n where n is the integer frame slot (period from a periodogram, robust to drops/quantisation).
    Residuals measure how far each timestamp is from a perfectly periodic clock."""
    t = t_ns.astype(np.float64)
    d = np.diff(t)
    guess = nominal_period_ns or float(np.mean(d[d < 1.6 * np.median(d)])) if len(d) else 1.0
    P = estimate_period(t_ns, guess)
    ph = np.angle(np.mean(np.exp(2j * np.pi * (t - t[0]) / P))) / (2 * np.pi) * P
    n = np.round((t - t[0] - ph) / P)
    A = np.vstack([np.ones_like(n), n]).T
    coef, *_ = np.linalg.lstsq(A, t - t[0], rcond=None)
    res = (t - t[0]) - A @ coef
    gaps = np.diff(n)
    return {"period_ms": coef[1] / 1e6, "fps": 1e9 / coef[1], "residual_us": stats(res, 1e-3),
            "residual_rms_us": float(np.sqrt(np.mean(res ** 2)) / 1e3),
            "slots_skipped": int(np.sum(gaps[gaps > 1] - 1)), "duplicate_slots": int(np.sum(gaps == 0))}


def interval_stats(t_ns: np.ndarray) -> dict:
    d = np.diff(t_ns.astype(np.float64))
    med = np.median(d)
    return {"interval_ms": stats(d, 1e-6), "drops_est": int(np.sum(np.round(d / med) - 1)) if med > 0 else None}


def nearest_round(f: float) -> tuple[float, float]:
    best = min(ROUND_CLOCKS, key=lambda c: abs(c - f) / c)
    return best, (f - best) / best * 1e6


def linfit(x: np.ndarray, y: np.ndarray) -> tuple[float, float, np.ndarray]:
    x = x.astype(np.float64); y = y.astype(np.float64)
    x0, y0 = x.mean(), y.mean()
    b = np.sum((x - x0) * (y - y0)) / np.sum((x - x0) ** 2)
    a = y0 - b * x0
    return a, b, y - (a + b * x)


def lower_envelope_fit(x: np.ndarray, y: np.ndarray, q: float = 0.1, iters: int = 5) -> tuple[float, float]:
    """Fit y = a + b x to the lower envelope (y = true + positive delay): iteratively refit on the lowest residuals."""
    a, b, r = linfit(x, y)
    m = np.ones_like(r, dtype=bool)
    for _ in range(iters):
        thr = np.quantile(r[m] if m.any() else r, q)
        m = r <= thr + 1e-9
        if m.sum() < 5:
            break
        a, b, _ = linfit(x[m], y[m])
        r = y - (a + b * x)
    # shift so that the line sits at the lower envelope
    a += float(np.quantile(y - (a + b * x), 0.02))
    return a, b


def linux_style_map(pts, stc, dev_sof, host_sof, host_ns, window: int) -> np.ndarray:
    """PTS -> host ns following uvc_video_clock_update(): two-point line through first/last sample of a sliding
    window, PTS->SOF using (STC, dev SOF) and SOF->host using (host SOF, host ns). Inputs are already unwrapped
    (stc/pts in ticks as int64, SOF in ms as int64 extended beyond 11 bits). Returns float ns (nan where < 2 samples)."""
    out = np.full(len(pts), np.nan)
    for i in range(len(pts)):
        j0 = max(0, i - window + 1)
        x1, x2 = stc[j0], stc[i]
        y1, y2 = dev_sof[j0], dev_sof[i]
        if x2 == x1 or (y2 - y1) < 250:  # Linux requires >= 250 ms of SOF span
            continue
        sof = y1 + (y2 - y1) * (pts[i] - x1) / (x2 - x1)
        h1, h2 = host_sof[j0], host_sof[i]
        t1, t2 = host_ns[j0], host_ns[i]
        if h2 == h1:
            continue
        out[i] = t1 + (t2 - t1) * (sof - h1) / (h2 - h1)
    return out


def lsq_map(pts, stc, dev_sof, host_sof, host_ns, window: int) -> np.ndarray:
    """Same two steps as linux_style_map but with least-squares lines over the whole window instead of the two end
    points; SOF counters are integer ms (floor), so +0.5 ms centres them. Averages away the 1 ms SOF quantisation that
    the end-point method passes straight into the timestamp."""
    out = np.full(len(pts), np.nan)
    for i in range(len(pts)):
        j0 = max(0, i - window + 1)
        if i - j0 < 8 or dev_sof[i] - dev_sof[j0] < 250:
            continue
        x = stc[j0:i + 1].astype(np.float64); y = dev_sof[j0:i + 1] + 0.5
        a, b, _ = linfit(x - x[-1], y)
        sof = a + b * (pts[i] - x[-1])
        hx = host_sof[j0:i + 1] + 0.5; hy = host_ns[j0:i + 1].astype(np.float64)
        if np.ptp(hx) == 0:
            continue
        a2, b2, _ = linfit(hx - hx[-1], hy - hy[-1])
        out[i] = hy[-1] + a2 + b2 * (sof - hx[-1])
    return out


def analyze(rows: list[dict], device_clock_hz: float | None, skip_first: int, scr_window: int) -> dict:
    rows = rows[skip_first:]
    res: dict = {"frames": len(rows)}
    if len(rows) < 10:
        res["error"] = "too few frames"
        return res
    first = rows[0]
    res["camera_key"] = first.get("camera_key"); res["backend"] = first.get("backend")
    res["os_timestamp_source"] = first.get("os_timestamp_source")
    host = np.array([r["host_arrival_ns"] for r in rows], dtype=np.int64)
    pb = np.array([r.get("payload_bytes", 0) or 0 for r in rows])
    res["payload_bytes"] = stats(pb)
    valid = [r.get("is_valid_jpeg") for r in rows if r.get("is_valid_jpeg") is not None]
    if valid:
        res["valid_jpeg_fraction"] = float(np.mean(valid))
    seq = np.array([r.get("seq", i) for i, r in enumerate(rows)])
    res["duration_s"] = float((host[-1] - host[0]) / 1e9)

    sources: dict[str, np.ndarray] = {"host_arrival": host}
    if all(r.get("os_timestamp_ns") is not None for r in rows):
        sources["os_timestamp"] = np.array([r["os_timestamp_ns"] for r in rows], dtype=np.int64)
    skip = {"host_arrival_ns", "os_timestamp_ns", "uvc_host_sof_ns", "readsample_call_ns"}
    for k in first:
        if k.endswith("_ns") and k not in skip and isinstance(first[k], int) and all(isinstance(r.get(k), int) for r in rows):
            sources[k[:-3]] = np.array([r[k] for r in rows], dtype=np.int64)

    # ---- UVC device clock -----------------------------------------------------------------------------------------
    has_pts = all(r.get("uvc_pts") is not None for r in rows)
    has_scr = all(r.get("uvc_scr_stc") is not None and r.get("uvc_scr_sof") is not None for r in rows)
    clk: dict = {}
    if has_pts:
        pts = unwrap(np.array([r["uvc_pts"] for r in rows], dtype=np.int64), 32)
        clk["pts_zero_fraction"] = float(np.mean(np.array([r["uvc_pts"] for r in rows]) == 0))
        if clk["pts_zero_fraction"] < 0.5:
            # frequency from PTS vs host arrival (least squares over the whole run)
            a, b, r_ = linfit(host / 1e9, pts)
            f_est = b
            clk["pts_freq_vs_host_hz"] = float(f_est)
            nominal = device_clock_hz
            assumed = False
            if not nominal:
                nominal, _ = nearest_round(f_est); assumed = True
            clk["nominal_hz"] = nominal; clk["nominal_assumed"] = assumed
            clk["device_vs_host_ppm"] = float((f_est - nominal) / nominal * 1e6)
            # PTS -> host by lower-envelope mapping (arrival = capture + positive latency)
            a2, b2 = lower_envelope_fit(pts.astype(np.float64), host.astype(np.float64))
            sources["uvc_pts_mapped_direct"] = (a2 + b2 * pts).astype(np.int64)
            clk["pts_period_ticks"] = stats(np.diff(pts))
            if "uvc_eof_pts" in first:
                eof = np.array([r.get("uvc_eof_pts") or 0 for r in rows], dtype=np.int64)
                clk["eof_pts_equals_sof_pts_fraction"] = float(np.mean(eof == np.array([r["uvc_pts"] for r in rows])))
    if has_scr:
        stc = unwrap(np.array([r["uvc_scr_stc"] for r in rows], dtype=np.int64), 32)
        dsof = unwrap(np.array([r["uvc_scr_sof"] for r in rows], dtype=np.int64), 11)
        clk["scr_stc_zero_fraction"] = float(np.mean(np.array([r["uvc_scr_stc"] for r in rows]) == 0))
        if clk["scr_stc_zero_fraction"] < 0.5:
            # device clock in USB-bus time: STC ticks per SOF ms
            a, b, rr = linfit(dsof.astype(np.float64), stc.astype(np.float64))
            clk["stc_per_sof_hz"] = float(b * 1000.0)
            clk["stc_vs_sof_residual_us"] = stats(rr / (b * 1000.0) * 1e6) if b else None
            if clk.get("nominal_hz"):
                clk["device_vs_usb_ppm"] = float((b * 1000.0 - clk["nominal_hz"]) / clk["nominal_hz"] * 1e6)
            # USB SOF vs host clock (device SOF quantised to 1 ms, arrival latency jitter -> lower envelope)
            a3, b3 = lower_envelope_fit(dsof.astype(np.float64), host.astype(np.float64))
            clk["usb_sof_ms_per_host_s"] = float(1e9 / b3)
            clk["usb_vs_host_ppm"] = float((1e6 / b3 - 1.0) * 1e6)
            # SOF progression per frame (Linux marks C920/C922 device SOF as unreliable: UVC_QUIRK_INVALID_DEVICE_SOF)
            clk["dev_sof_step_ms"] = stats(np.diff(dsof))
            clk["stc_freq_vs_host_hz"] = float(linfit(host / 1e9, stc)[1])
            if "uvc_eof_scr_stc" in first and all(r.get("uvc_eof_scr_stc") is not None for r in rows):
                estc = np.array([r["uvc_eof_scr_stc"] for r in rows], dtype=np.int64)
                esof = np.array([r["uvc_eof_scr_sof"] for r in rows], dtype=np.int64)
                raw_stc = np.array([r["uvc_scr_stc"] for r in rows], dtype=np.int64)
                raw_sof = np.array([r["uvc_scr_sof"] for r in rows], dtype=np.int64)
                clk["eof_minus_sof_scr_stc_ticks"] = stats(((estc - raw_stc) % (1 << 32)).astype(float))
                clk["eof_minus_sof_scr_sof_ms"] = stats(((esof - raw_sof) % 2048).astype(float))
            # device-internal latency: STC (first data on bus) - PTS (capture start)
            if has_pts and clk.get("pts_zero_fraction", 1) < 0.5:
                lat = (stc - pts) / clk["nominal_hz"]
                clk["stc_minus_pts_ms"] = stats(lat, 1e3)
                # Linux-style two-step mapping
                if all(r.get("uvc_host_sof") is not None and r.get("uvc_host_sof_ns") is not None for r in rows):
                    hsof = unwrap(np.array([r["uvc_host_sof"] for r in rows], dtype=np.int64), 11)
                    hns = np.array([r["uvc_host_sof_ns"] for r in rows], dtype=np.int64)
                    # host SOF counters can be limited to fewer bits (Linux uvc_video_clock_host_sof): recover
                    # them from the device SOF + 8-bit delta as the kernel does
                    delta = (np.array([r["uvc_host_sof"] for r in rows]) - np.array([r["uvc_scr_sof"] for r in rows])) & 255
                    hsof = dsof + delta
                    m = linux_style_map(pts, stc, dsof, hsof, hns, scr_window)
                    label = "uvc_pts_via_scr_linux"
                else:
                    # Windows: no host SOF. SOF->host from lower-envelope fit of device SOF vs host arrival over the
                    # run (labelled: not the kernel algorithm's second step)
                    hns = (a3 + b3 * dsof).astype(np.int64)
                    m = linux_style_map(pts, stc, dsof, dsof, hns, scr_window)
                    label = "uvc_pts_via_scr_envelope"
                m2 = lsq_map(pts, stc, dsof, hsof if label.endswith("linux") else dsof, hns, scr_window)
                for lab, mv in ((label, m), (label.replace("via_scr", "via_scr_lsq"), m2)):
                    ok = ~np.isnan(mv)
                    clk[lab + "_valid_frames"] = int(ok.sum())
                    if ok.sum() > 10:
                        mm = mv.copy()
                        if (~ok).any():
                            mm[~ok] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), mv[ok])
                        sources[lab] = mm.astype(np.int64)
                        res["_mask_" + lab] = ok
    res["device_clock"] = clk

    # ---- per-source statistics ------------------------------------------------------------------------------------
    per: dict = {}
    masks = {}
    for name, t in sources.items():
        mask = res.pop("_mask_" + name, None)
        masks[name] = mask
        tt = t if mask is None else t[mask]
        e = {"interval": interval_stats(tt), "periodic_fit": periodic_fit(tt)}
        hh = host if mask is None else host[mask]
        if name != "host_arrival":
            e["arrival_minus_source_ms"] = stats((hh - tt).astype(np.float64), 1e-6)
        per[name] = e
    res["sources"] = per
    res["_arrays"] = {"seq": seq, "host": host, "sources": sources, "masks": masks}  # popped before JSON output
    rank = sorted(per.items(), key=lambda kv: kv[1]["periodic_fit"]["residual_rms_us"])
    res["jitter_ranking_rms_us"] = [[k, round(v["periodic_fit"]["residual_rms_us"], 2)] for k, v in rank]
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out")
    ap.add_argument("--device-clock-hz", type=float)
    ap.add_argument("--skip-first", type=int, default=5, help="drop first N frames (stream start-up)")
    ap.add_argument("--scr-window", type=int, default=32, help="frames in the SCR sliding window (Linux: 32)")
    a = ap.parse_args()
    out = {"test": "analyze_frames", "platform": sys.platform, "hostname": socket.gethostname(),
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(), "command": " ".join(sys.argv),
           "environment": {"python": platform.python_version(), "numpy": np.__version__, "os": platform.platform()},
           "inputs": a.files, "cameras": []}
    for f in a.files:
        rows = load(Path(f))
        r = analyze(rows, a.device_clock_hz, a.skip_first, a.scr_window)
        r["file"] = f
        r.pop("_arrays", None)
        out["cameras"].append(r)
    txt = json.dumps(out, indent=2, default=float)
    if a.out:
        Path(a.out).write_text(txt)
    # compact console summary
    for c in out["cameras"]:
        print(f"== {c.get('camera_key')}  frames={c['frames']}  dur={c.get('duration_s', 0):.1f}s")
        for k, v in c.get("jitter_ranking_rms_us", []):
            s = c["sources"][k]
            off = s.get("arrival_minus_source_ms", {})
            print(f"   {k:32s} jitter_rms={v:9.1f} us  fps={s['periodic_fit']['fps']:.4f}  "
                  f"arrival-src={off.get('mean', 0):8.3f}+-{off.get('std', 0):.3f} ms  drops={s['interval']['drops_est']}")
        if c.get("device_clock"):
            print("   device_clock:", json.dumps({k: v for k, v in c["device_clock"].items() if not isinstance(v, dict)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
