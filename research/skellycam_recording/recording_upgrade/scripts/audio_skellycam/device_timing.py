"""Real-microphone TIMING ONLY (privacy: the callback never copies, stores or measures the samples).

Opens a sounddevice InputStream (shared mode, default settings, no device or system settings changed)
for at most 30 s and records per callback:
  host_ns   = time.perf_counter_ns() at callback entry (QPC on Windows),
  adc       = time_info.inputBufferAdcTime (PortAudio stream clock, seconds),
  cur       = time_info.currentTime (same clock),
  frames, status flags.
Then fits sample index -> time and reports jitter, start-up, gaps and drift (ppm vs nominal rate).

Usage: python -I device_timing.py <out_json> <device_index> <rate> <blocksize> <seconds> [label]
"""
import json
import sys
import time

import numpy as np
import sounddevice as sd

MAX_S = 30.0


def fit(x, y):
    """Least squares y = a + b x; returns a, b, residuals, slope standard error."""
    A = np.vstack([np.ones_like(x), x]).T
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    r = y - A @ coef
    n = len(x)
    s2 = (r @ r) / max(n - 2, 1)
    se_b = np.sqrt(s2 / np.sum((x - x.mean()) ** 2))
    return coef[0], coef[1], r, se_b


def envelope_fit(x, y, iters=8):
    """Lower-envelope fit: callback lateness is one-sided, so fit the earliest arrivals.
    Iteratively keep points whose residual is in the lowest 20 %."""
    keep = np.ones_like(x, dtype=bool)
    a = b = 0.0
    for _ in range(iters):
        a, b, r, _ = fit(x[keep], y[keep])
        rr = y - (a + b * x)
        thr = np.quantile(rr, 0.2)
        keep = rr <= thr
    rr = y - (a + b * x)
    return a, b, rr


def summarize(arr):
    arr = np.asarray(arr, dtype=float)
    return dict(median=round(float(np.median(arr)), 4), p1=round(float(np.quantile(arr, 0.01)), 4),
                p99=round(float(np.quantile(arr, 0.99)), 4), min=round(float(arr.min()), 4),
                max=round(float(arr.max()), 4), std=round(float(arr.std()), 4))


def main():
    out, dev, rate, block, seconds = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])
    label = sys.argv[6] if len(sys.argv) > 6 else ""
    seconds = min(seconds, MAX_S)
    info = sd.query_devices(dev)
    hostapi = sd.query_hostapis(info["hostapi"])["name"]
    ch = min(2, int(info["max_input_channels"]))
    nmax = int(seconds * rate / max(block, 64)) + 2000
    host = np.zeros(nmax, np.int64)
    adc = np.zeros(nmax, np.float64)
    cur = np.zeros(nmax, np.float64)
    frames = np.zeros(nmax, np.int32)
    flags = np.zeros(nmax, np.int32)
    idx = [0]

    def cb(indata, n, ti, status):  # indata deliberately unused
        h = time.perf_counter_ns()
        i = idx[0]
        if i < nmax:
            host[i] = h
            adc[i] = ti.inputBufferAdcTime
            cur[i] = ti.currentTime
            frames[i] = n
            flags[i] = int(status._flags) if hasattr(status, "_flags") else (1 if status else 0)
            idx[0] = i + 1

    stream = sd.InputStream(device=dev, samplerate=rate, channels=ch, dtype="int16", blocksize=block, callback=cb)
    # relation between PortAudio's stream clock and perf_counter (both QPC-based on Windows?)
    pairs = []
    stream.start()
    t_start_host = time.perf_counter_ns()
    for _ in range(5):
        a = time.perf_counter_ns(); s = stream.time; b = time.perf_counter_ns()
        pairs.append(((a + b) / 2e9, s, (b - a) / 1e3))
    time.sleep(seconds)
    for _ in range(5):
        a = time.perf_counter_ns(); s = stream.time; b = time.perf_counter_ns()
        pairs.append(((a + b) / 2e9, s, (b - a) / 1e3))
    latency = stream.latency
    stream.stop(); stream.close()
    n = idx[0]
    host, adc, cur, frames, flags = host[:n], adc[:n], cur[:n], frames[:n], flags[:n]
    pa_minus_perf = [s - p for p, s, _ in pairs]

    # sample index of the FIRST sample of each block
    s0 = np.concatenate([[0], np.cumsum(frames)[:-1]]).astype(np.float64)
    s_end = s0 + frames  # index after the last sample of the block
    # host time of the block's LAST sample ~ callback time (minus latency); ADC time is the FIRST sample
    host_s = (host - host[0]) / 1e9
    adc_host = (host + (adc - cur) * 1e9)  # Rust sfn26 mapping: host now + (adc - current)
    adc_host_s = (adc_host - host[0]) / 1e9
    adc_direct_s = adc - (host[0] / 1e9 + np.median(pa_minus_perf))  # if PaTime == perf_counter + offset

    res = dict(label=label, device=dev, device_name=info["name"], hostapi=hostapi, rate=rate, blocksize=block,
               channels=ch, seconds=seconds, callbacks=int(n), samples=int(frames.sum()),
               stream_latency_s=latency, default_low_input_latency=info["default_low_input_latency"],
               device_default_rate=info["default_samplerate"],
               pa_time_minus_perf_s=dict(values=[round(v, 6) for v in pa_minus_perf], spread_us=round(1e6 * (max(pa_minus_perf) - min(pa_minus_perf)), 1)),
               frames_per_callback=dict(zip(*[[int(v) for v in u] for u in np.unique(frames, return_counts=True)])),
               status_nonzero=int((flags != 0).sum()),
               first_callback_after_start_ms=round((host[0] - t_start_host) / 1e6, 2) if n else None,
               callback_minus_adc_ms=summarize(1e3 * (cur - adc)))
    # raw time_info values (timing only), to see what each host API really reports
    res["adc_first5_s"] = [round(float(v), 6) for v in adc[:5]]
    res["cur_first5_s"] = [round(float(v), 6) for v in cur[:5]]
    res["host_first5_s"] = [round(float(v) / 1e9, 6) for v in host[:5]]
    res["adc_zero"] = int((adc == 0).sum()); res["cur_zero"] = int((cur == 0).sum())
    res["adc_minus_host_ms"] = summarize(1e3 * (adc - host / 1e9))
    # elapsed check: samples delivered vs host time span
    period = block / rate
    dt = np.diff(host) / 1e6
    res["callback_interval_ms"] = summarize(dt)
    res["nominal_interval_ms"] = round(1e3 * period, 4)

    for skip_s in (0.0, 1.0):
        m = host_s >= skip_s
        if m.sum() < 20:
            continue
        key = f"skip{skip_s:.0f}s"
        out_k = {}
        for nm, t, xs in (("callback_host", host_s, s_end), ("adc_mapped", adc_host_s, s0), ("adc_direct", adc_direct_s, s0)):
            a, b, r, se = fit(xs[m], t[m])
            ea, eb, er = envelope_fit(xs[m], t[m])
            out_k[nm] = dict(
                ppm_lsq=round((b * rate - 1) * 1e6, 2), ppm_lsq_se=round(se * rate * 1e6, 2),
                ppm_envelope=round((eb * rate - 1) * 1e6, 2),
                resid_ms=summarize(1e3 * r), env_resid_ms=summarize(1e3 * er),
            )
            # stability: slope of each half
            half = xs[m][len(xs[m]) // 2]
            m1 = m & (xs < half); m2 = m & (xs >= half)
            if m1.sum() > 10 and m2.sum() > 10:
                _, b1, _, _ = fit(xs[m1], t[m1]); _, b2, _, _ = fit(xs[m2], t[m2])
                out_k[nm]["ppm_half1"] = round((b1 * rate - 1) * 1e6, 2)
                out_k[nm]["ppm_half2"] = round((b2 * rate - 1) * 1e6, 2)
        res[key] = out_k
    # startup: residual of the first 20 callbacks against the fit made after 1 s
    m = host_s >= 1.0
    a, b, _, _ = fit(s_end[m], host_s[m])
    res["startup_resid_ms_first20"] = [round(1e3 * (host_s[i] - (a + b * s_end[i])), 3) for i in range(min(20, n))]
    # gaps: any callback whose interval exceeds 2.5 periods
    res["intervals_over_2p5_periods"] = int((dt > 2.5 * 1e3 * period).sum())
    # raw TIMING arrays (no audio) for offline analysis; kept in the scratchpad, not the repo
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ac_common import SCRATCH
    os.makedirs(os.path.join(SCRATCH, "timing_raw"), exist_ok=True)
    np.savez_compressed(os.path.join(SCRATCH, "timing_raw", os.path.basename(out).replace(".json", ".npz")),
                        host=host, adc=adc, cur=cur, frames=frames, flags=flags, rate=rate)
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("label", "hostapi", "callbacks", "status_nonzero", "callback_interval_ms")}))
    for k in ("skip1s",):
        for nm, v in res.get(k, {}).items():
            print(k, nm, "ppm", v["ppm_lsq"], "+-", v["ppm_lsq_se"], "env", v["ppm_envelope"], "halves", v.get("ppm_half1"), v.get("ppm_half2"), "resid_std_ms", v["resid_ms"]["std"], "env_p99", v["env_resid_ms"]["p99"])


if __name__ == "__main__":
    main()
