"""Offline analysis of the raw timing arrays saved by device_timing.py (timing only, no audio).

For each run: drift (ppm of the mic clock vs QPC) from (a) the callback host time and (b) PortAudio's
inputBufferAdcTime (same clock as perf_counter on Windows, measured), fitted after several start-up
exclusions; per-2-s windowed residual medians (to see start-up transients); jitter after the fit.

Usage: python -I analyze_timing.py <raw_dir> <out_json>
"""
import glob
import json
import os
import sys

import numpy as np


def fit(x, y):
    A = np.vstack([np.ones_like(x), x]).T
    c, *_ = np.linalg.lstsq(A, y, rcond=None)
    r = y - A @ c
    se = np.sqrt((r @ r) / max(len(x) - 2, 1) / np.sum((x - x.mean()) ** 2))
    return c[0], c[1], r, se


def env(x, y, q=0.2, it=8):
    keep = np.ones_like(x, bool)
    for _ in range(it):
        a, b, _, _ = fit(x[keep], y[keep])
        rr = y - (a + b * x)
        keep = rr <= np.quantile(rr, q)
    return a, b, y - (a + b * x)


def q(a, p):
    return round(float(np.quantile(a, p)), 3)


def main():
    out = {}
    for f in sorted(glob.glob(os.path.join(sys.argv[1], "*.npz"))):
        z = np.load(f)
        host, adc, cur, frames, rate = z["host"], z["adc"], z["cur"], z["frames"], int(z["rate"])
        s0 = np.concatenate([[0], np.cumsum(frames)[:-1]]).astype(float)
        se_ = s0 + frames
        th = (host - host[0]) / 1e9
        ta = adc - host[0] / 1e9
        valid_adc = bool(np.all(adc > 1.0))
        row = dict(rate=rate, callbacks=int(len(host)), seconds=round(float(th[-1]), 2), adc_absolute=valid_adc,
                   adc_minus_cur_ms=dict(median=q(1e3 * (adc - cur), 0.5), p1=q(1e3 * (adc - cur), 0.01), p99=q(1e3 * (adc - cur), 0.99)),
                   host_minus_cur_ms=dict(median=q(1e3 * (host / 1e9 - cur), 0.5), p99=q(1e3 * (host / 1e9 - cur), 0.99)))
        fits = {}
        for skip in (1, 2, 5, 10):
            m = th >= skip
            if m.sum() < 100:
                continue
            d = {}
            for nm, t, xs in (("callback", th, se_), ("adc", ta, s0)):
                if nm == "adc" and not valid_adc:
                    continue
                a, b, r, se = fit(xs[m], t[m])
                ea, eb, er = env(xs[m], t[m])
                half = np.median(xs[m])
                m1, m2 = m & (xs < half), m & (xs >= half)
                _, b1, _, _ = fit(xs[m1], t[m1]); _, b2, _, _ = fit(xs[m2], t[m2])
                d[nm] = dict(ppm=round((b * rate - 1) * 1e6, 1), se=round(se * rate * 1e6, 1), ppm_env=round((eb * rate - 1) * 1e6, 1),
                             ppm_half1=round((b1 * rate - 1) * 1e6, 1), ppm_half2=round((b2 * rate - 1) * 1e6, 1),
                             resid_ms=dict(std=round(float(r.std()) * 1e3, 3), p1=q(r * 1e3, 0.01), p99=q(r * 1e3, 0.99)),
                             env_resid_ms=dict(p50=q(er * 1e3, 0.5), p99=q(er * 1e3, 0.99), max=q(er * 1e3, 1.0)))
            fits[f"skip{skip}s"] = d
        row["fits"] = fits
        # windowed residual medians against the skip-5 s fit (shows start-up transients)
        m = th >= 5
        for nm, t, xs in (("callback", th, se_), ("adc", ta, s0)):
            if nm == "adc" and not valid_adc:
                continue
            a, b, _, _ = fit(xs[m], t[m])
            r = (t - (a + b * xs)) * 1e3
            row[f"{nm}_resid_ms_by_2s"] = [round(float(np.median(r[(th >= k) & (th < k + 2)])), 2) for k in range(0, int(th[-1]), 2)]
        out[os.path.basename(f)] = row
        print(os.path.basename(f), json.dumps(fits.get("skip5s", {})))
    json.dump(out, open(sys.argv[2], "w"), indent=1)


if __name__ == "__main__":
    main()
