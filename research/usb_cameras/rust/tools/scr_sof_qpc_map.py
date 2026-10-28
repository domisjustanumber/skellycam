# /// script
# requires-python = ">=3.10"
# ///
"""Map UVC SCR (device STC + 11-bit SOF) to the host clock through the USB frame counter (Windows).

Usage:
    uv run --script research/usb_cameras/rust/tools/scr_sof_qpc_map.py <uvc_iso stream run dir with --sof-instance>

Inputs (written by `uvc_iso stream ... --sof-instance <id>`):
  summary.json  sof_calibration_before / sof_calibration_after: WinUsb_GetCurrentFrameNumber vs QPC fits
  frames_*.jsonl  per-frame uvc_scr_stc / uvc_scr_sof (first SCR of the frame), uvc_pts, host ns (QPC)
Method:
  1. USB frame clock vs QPC: long-baseline rate from before.first -> after.last (~stream length), so
     drift in ppm is resolved to ~1 frame / baseline. Frame F starts at qpc(F) ~ (F - f0 - a - 0.5)/rate
     (the counter is read as floor(), so the fitted intercept sits ~0.5 frame late; +-0.5 ms systematic).
  2. Each frame's SCR SOF (11 bits) is expanded to a full frame number with the host estimate of the packet
     time (first_packet_est_host_ns), then converted to QPC -> the host time of the SOF the device latched.
  3. Fit STC -> host from (STC, host(SOF)) pairs; residuals show how well SCR pins the device clock
     (vs the packet-arrival fit uvc_iso does on its own).
  4. PTS -> host with that fit (PTS-STC difference mod 2^32), latency = host arrival - PTS_host.
Writes <run_dir>/scr_sof_qpc_map.json.
"""
import json
import statistics
import sys
from pathlib import Path


def st(v):
    if not v:
        return None
    s = sorted(v)
    q = lambda p: s[min(len(s) - 1, round(p * (len(s) - 1)))]
    return {"n": len(s), "mean": statistics.fmean(s), "std": statistics.pstdev(s), "min": s[0], "p02": q(0.02),
            "p50": q(0.5), "p98": q(0.98), "max": s[-1]}


def linfit(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def main(run: Path):
    s = json.loads((run / "summary.json").read_text())
    cb, ca = s.get("sof_calibration_before"), s.get("sof_calibration_after")
    if not cb or "error" in cb:
        raise SystemExit(f"missing sof calibration before: {cb and cb.get('error')}")
    have_after = bool(ca) and "error" not in ca
    qf = cb["qpc_frequency"]
    f0, q0 = cb["first"]["frame"], cb["first"]["qpc"]
    rows = [json.loads(l) for l in next(run.glob("frames_*.jsonl")).read_text().splitlines() if l.strip()]
    # In-stream USB frame rate: expand each frame's 11-bit SCR SOF with a 1000/s prediction from the
    # 'before' anchor, then fit expanded frame number vs host packet-time estimate (arrival jitter ~0.2-1 ms,
    # so over 60 s the slope resolves ~10 ppm). Independent of the 'after' calibration.
    xs_t, ys_f = [], []
    for r in rows:
        sof = r.get("uvc_scr_sof")
        if sof is None:
            continue
        t = r["first_packet_est_host_ns"]
        fp = f0 + cb["fit_intercept_frames"] + (t * qf / 1e9 - q0) / qf * 1000.0
        xs_t.append((t * qf / 1e9 - q0) / qf)
        ys_f.append(sof + 2048 * round((fp - sof) / 2048))
    ia, ib = linfit(xs_t, ys_f)
    instream = {"frames_per_qpc_s": ib, "ppm_vs_qpc": (ib / 1000.0 - 1.0) * 1e6, "span_s": xs_t[-1] - xs_t[0],
                "residual_frames": st([y - (ia + ib * x) for x, y in zip(xs_t, ys_f)])}
    if have_after:
        # long baseline: before.first -> after.last (32-bit frame counter; wrap irrelevant over minutes)
        f1, q1 = ca["last"]["frame"], ca["last"]["qpc"]
        rate = (f1 - f0) / ((q1 - q0) / qf)  # frames per QPC-second
        rate_source = "WinUsb_GetCurrentFrameNumber before.first -> after.last"
    else:
        f1, q1 = None, None
        rate = ib
        rate_source = "in-stream SCR-SOF vs packet arrival (after-calibration missing)"
    ppm = (rate / 1000.0 - 1.0) * 1e6
    # intercept: average of the two short fits' intercepts, re-expressed at the long-baseline rate
    a_b = cb["fit_intercept_frames"]

    def qpc_ns_of_frame_start(F):
        return (q0 + (F - f0 - a_b - 0.5) / rate * qf) * 1e9 / qf

    def frame_at_ns(t_ns):
        return f0 + a_b + (t_ns * qf / 1e9 - q0) / qf * rate

    # consistency: predict the 'after' calibration's first sample from the before fit + long rate
    pred_after_first = frame_at_ns(ca["first"]["qpc"] * 1e9 / qf) - ca["first"]["frame"] if have_after else None
    pairs, lead = [], []
    un, last, base = [], None, 0
    for r in rows:
        stc, sof = r.get("uvc_scr_stc"), r.get("uvc_scr_sof")
        if stc is None or sof is None:
            un.append(None)
            continue
        if last is not None and stc < last and last - stc > 1 << 31:
            base += 1 << 32
        last = stc
        x = base + stc
        un.append(x)
        fp = frame_at_ns(r["first_packet_est_host_ns"])
        F = sof + 2048 * round((fp - sof) / 2048)
        lead.append(fp - F)  # frames between the latched SOF and the host's estimate of that packet
        pairs.append((x, qpc_ns_of_frame_start(F), r))
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    a, b = linfit(xs, ys)
    res_ms = [(y - (a + b * x)) / 1e6 for x, y in zip(xs, ys)]
    # uvc_iso's own arrival-based fit residuals for comparison
    a2, b2 = linfit(xs, [p[2]["first_packet_est_host_ns"] for p in pairs])
    res2_ms = [(p[2]["first_packet_est_host_ns"] - (a2 + b2 * p[0])) / 1e6 for p in pairs]
    lat, pts_iv = [], []
    prev = None
    for r, x in zip(rows, un):
        if x is None or r.get("uvc_pts") is None:
            continue
        d = ((r["uvc_pts"] - r["uvc_scr_stc"] + (1 << 31)) % (1 << 32)) - (1 << 31)
        t = a + b * (x + d)
        lat.append((r["host_arrival_ns"] - t) / 1e6)
        if prev is not None:
            pts_iv.append((t - prev) / 1e6)
        prev = t
    hz = rows[0].get("device_clock_hz") or 0
    out = {
        "run_dir": str(run), "analyzer": "research/usb_cameras/rust/tools/scr_sof_qpc_map.py",
        "usb_frame_clock": {"rate_source": rate_source, "baseline_s": (q1 - q0) / qf if have_after else None,
                            "frames": (f1 - f0) if have_after else None, "frames_per_qpc_s": rate,
                            "ppm_vs_qpc": ppm, "short_fit_rate_before": cb["fit_frames_per_s"],
                            "short_fit_rate_after": ca["fit_frames_per_s"] if have_after else None,
                            "after_first_sample_predicted_minus_actual_frames": pred_after_first},
        "usb_frame_clock_instream": instream,
        "sof_expansion_lead_frames": st(lead),
        "stc_fit_via_sof": {"ns_per_tick": b, "implied_device_clock_hz": 1e9 / b, "nominal_hz": hz,
                            "device_clock_ppm_vs_qpc": (1e9 / b / hz - 1) * 1e6 if hz else None, "residual_ms": st(res_ms)},
        "stc_fit_via_packet_arrival": {"implied_device_clock_hz": 1e9 / b2, "residual_ms": st(res2_ms)},
        "pts_host_interval_ms": st(pts_iv),
        "latency_host_arrival_minus_pts_ms": st(lat),
        "notes": "SOF->QPC has a +-0.5 ms systematic (WinUsb_GetCurrentFrameNumber is 1 ms, read as floor). "
                 "Residual spread, rates and drift are free of it. PTS on the C930e is a synthetic counter (phase 1).",
    }
    (run / "scr_sof_qpc_map.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ["usb_frame_clock", "usb_frame_clock_instream", "stc_fit_via_sof", "stc_fit_via_packet_arrival", "sof_expansion_lead_frames"]}, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
