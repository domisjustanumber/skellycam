"""Analyse the Opus decodes written by page.js (dec_none.f32, dec_head.f32, seek_trials.json) against mic_ref.f32.
Usage: uv run --no-project --python 3.13 --with numpy==2.5.4 python -I analyze_audio.py <media dir> <electron result json> <out json>

Timeline: every decoded output carries an AudioData timestamp (us). Sample i of an output with timestamp ts is placed at
ts + i/48 us. The input sample n was captured at T0 + n/48 us (T0 = 1 s, see gen_media.py). Errors are in samples at 48 kHz.
"""
import base64, json, os, sys
import numpy as np

media_dir, run_json, out_json = sys.argv[1:4]
media = json.load(open(os.path.join(media_dir, "media.json")))["mic"]
run = json.load(open(run_json))["audio"]
SR, T0_US = media["sample_rate"], 1_000_000
ref = np.fromfile(os.path.join(media_dir, "mic_ref.f32"), dtype=np.float32)
clicks, CL = media["clicks"], media["click_len"]


def best_lag(x, xi, y, yi, half=200, search=1000):
    """Lag L maximising correlation of y[yi-half : yi+half+CL] with x[xi+L-half : ...]."""
    w = y[yi - half: yi + half + CL]
    best, bl = -np.inf, None
    for L in range(-search, search + 1):
        a = xi + L - half
        if a < 0 or a + len(w) > len(x):
            continue
        c = float(np.dot(x[a:a + len(w)], w))
        if c > best:
            best, bl = c, L
    return bl


def db(x):
    return round(float(20 * np.log10(max(float(x), 1e-12))), 2)


res = {"full": {}}
for k in ("none", "head"):
    dec = np.fromfile(os.path.join(media_dir, f"dec_{k}.f32"), dtype=np.float32)
    f = run["full"][k]
    ts0 = f["ts_list"][0]
    counts = f["frame_counts"]
    # output timestamps continuous? (each = previous + previous frames)
    first_n = f["first"][0]["n"]
    lags, ts_err = [], []
    for c in clicks:
        L = best_lag(dec, c, ref, c)                      # decoded index of click = c + L
        lags.append(L)
        t_dec = ts0 + (c + L) * 1e6 / SR                   # outputs are back to back from ts0 (checked below)
        t_true = T0_US + c * 1e6 / SR
        ts_err.append(round((t_dec - t_true) * SR / 1e6, 2))
    L0 = int(np.median(lags))
    seg = dec[L0:L0 + len(ref)] if L0 >= 0 else np.concatenate([np.zeros(-L0, np.float32), dec[:len(ref) + L0]])
    n = min(len(seg), len(ref))
    snr = db(np.sqrt(np.mean(ref[:n] ** 2))) - db(np.sqrt(np.mean((seg[:n] - ref[:n]) ** 2)))
    # check timestamps are back-to-back
    ts_list = f["ts_list"]
    ns = [first_n] + [960] * (len(ts_list) - 1)
    gaps = [ts_list[i + 1] - ts_list[i] - ns[i] * 1e6 / SR for i in range(len(ts_list) - 1)]
    res["full"][k] = dict(total_decoded=len(dec), encoded=f["encoded_frames"], input_samples=media["n_input_samples"],
                          dropped_at_start=f["encoded_frames"] - len(dec), first_output_frames=first_n,
                          first_output_ts_us=ts0, first_input_log_time_us=ts0,
                          click_index_lag_samples=dict(min=min(lags), max=max(lags), median=L0),
                          click_timestamp_error_samples=dict(min=min(ts_err), max=max(ts_err)),
                          max_abs_timestamp_gap_us=max(abs(g) for g in gaps), snr_vs_input_db=round(snr, 2))

# seek trials
st = json.load(open(os.path.join(media_dir, "seek_trials.json")))
full = {k: np.fromfile(os.path.join(media_dir, f"dec_{k}.f32"), dtype=np.float32) for k in ("none", "head")}
full_ts0 = {k: run["full"][k]["ts_list"][0] for k in full}
W = 3840                                                  # 80 ms after the target
rows = []
for t in st["trials"]:
    outs = t["outs"]
    seg = np.concatenate([np.frombuffer(base64.b64decode(o["pcm"]), dtype=np.float32) for o in outs])
    s_ts0 = outs[0]["ts"]
    fl, f_ts0 = full[t["config"]], full_ts0[t["config"]]
    # timestamp alignment: target time = input timestamp of packet K
    i_t = round((t["target_ts"] - s_ts0) * SR / 1e6)
    j_t = round((t["target_ts"] - f_ts0) * SR / 1e6)
    a, b = seg[i_t:i_t + W], fl[j_t:j_t + W]
    rms_ref = float(np.sqrt(np.mean(b ** 2)))
    d = a - b
    # shift between the seek decode and the full decode (0 = same samples at the same timestamps);
    # search < half the 220 Hz period, so the tone cannot alias the lag
    lag = best_lag(seg, i_t + 1500, fl, j_t + 1500, half=1200, search=100) if i_t + 2900 < len(seg) else None
    d10 = d[:480]                                         # first 10 ms
    rows.append(dict(K=t["K"], config=t["config"], preroll=t["preroll"], first_out_frames=outs[0]["n"],
                     first_out_ts_minus_first_in_ts_us=s_ts0 - (t["target_ts"] - t["preroll"] * 20000),
                     lag_vs_full_samples=lag, rms_full_dbfs=db(rms_ref), rms_diff_dbfs=db(float(np.sqrt(np.mean(d ** 2)))),
                     rms_diff_rel_db=db(float(np.sqrt(np.mean(d ** 2)))) - db(rms_ref),
                     rms_diff_first10ms_dbfs=db(float(np.sqrt(np.mean(d10 ** 2)))),
                     rms_diff_by_20ms_dbfs=[db(float(np.sqrt(np.mean(d[q:q + 960] ** 2)))) for q in range(0, W, 960)], max_abs_diff=round(float(np.max(np.abs(d))), 4)))
summ = {}
for cfg in ("none", "head"):
    for P in (0, 4):
        r = [x for x in rows if x["config"] == cfg and x["preroll"] == P]
        summ[f"{cfg}_preroll{P}"] = dict(
            n=len(r), lag_vs_full=sorted({x["lag_vs_full_samples"] for x in r}),
            first_out_frames=sorted({x["first_out_frames"] for x in r}),
            rms_diff_rel_db=dict(median=float(np.median([x["rms_diff_rel_db"] for x in r])), max=max(x["rms_diff_rel_db"] for x in r)),
            rms_diff_dbfs=dict(median=float(np.median([x["rms_diff_dbfs"] for x in r])), max=max(x["rms_diff_dbfs"] for x in r)),
            rms_diff_first10ms_dbfs=dict(median=float(np.median([x["rms_diff_first10ms_dbfs"] for x in r])), max=max(x["rms_diff_first10ms_dbfs"] for x in r)),
            rms_diff_by_20ms_dbfs_median=[float(np.median([x["rms_diff_by_20ms_dbfs"][q] for x in r])) for q in range(4)],
            max_abs_diff=max(x["max_abs_diff"] for x in r))
res["seek_summary"] = summ
res["seek_rows"] = rows
res["signal"] = dict(ref_rms_dbfs=db(float(np.sqrt(np.mean(ref ** 2)))), clicks=len(clicks), note="220 Hz + 1375 Hz tones + noise; 1 ms 4 kHz clicks")
json.dump(res, open(out_json, "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "seek_rows"}, indent=1))
