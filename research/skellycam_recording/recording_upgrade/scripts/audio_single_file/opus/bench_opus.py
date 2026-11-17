# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Size per hour and CPU cost of live Opus encoding at the D9N1 settings (48 kHz, 20 ms, application audio, VBR,
complexity 10; mono 128 kbit/s, stereo 256 kbit/s), 60 s per run, unpaced (CPU time is what matters).
Signals: 'timing' = the opus_common test signal (noise at about -17 dBFS rms + clicks; worst case for VBR);
         'quiet'  = -60 dBFS noise + bursts of noise at -20 dBFS 30 % of the time + a click every second
                    (the audio_skellycam bench.py description).
Per run: libopus encode time per 960-sample packet (median/p99 us), process CPU time as % of one core, payload
bytes -> MB/h. Then per container: the live writer as used in kill_opus.py (1024-sample blocks through
asf_common.PyAVWriter, flush per packet), time per write() call (FIFO + encode + mux + write), file bytes -> MB/h
and container overhead per packet. WAV and FLAC reference sizes from the same writers.

Usage: uv run --script .../opus/bench_opus.py     Output: results/audio_single_file/opus/bench_opus.json
"""
import fractions
import json
import os
import sys
import time

import av
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import opus_common as O  # noqa: E402

C = O.C
SECONDS = 60


def quiet(n, ch):
    rng = np.random.default_rng(7)
    x = rng.normal(0, 32768 * 10 ** (-60 / 20), (n, ch))
    burst = (np.arange(n) // (O.RATE // 2)) % 10 < 3
    x[burst] += rng.normal(0, 32768 * 10 ** (-20 / 20), (int(burst.sum()), ch))
    x[(np.arange(n) % O.RATE) == O.RATE // 2] = 29000
    return np.clip(x, -32768, 32767).astype(np.int16)


def signal(kind, ch):
    n = SECONDS * O.RATE
    x = O.sig(0, n) if kind == "timing" else quiet(n, 2)
    return np.ascontiguousarray(x[:, :ch])


def encode_only(x, ch):
    layout = "mono" if ch == 1 else "stereo"
    cc = av.CodecContext.create("libopus", "w")
    cc.sample_rate, cc.layout, cc.format = O.RATE, layout, "s16"
    cc.time_base = fractions.Fraction(1, O.RATE)
    cc.options = dict(O.COPTS, b="128000" if ch == 1 else "256000")
    cc.open()
    per, nbytes, npk = [], 0, 0
    c0 = time.process_time()
    for k in range(0, len(x), 960):
        fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(x[k:k + 960].reshape(1, -1)), format="s16", layout=layout)
        fr.sample_rate, fr.pts, fr.time_base = O.RATE, k, cc.time_base
        t = time.perf_counter_ns()
        pk = cc.encode(fr)
        per.append(time.perf_counter_ns() - t)
        nbytes += sum(p.size for p in pk); npk += len(pk)
    cpu = time.process_time() - c0
    per = np.array(per) / 1e3
    return dict(packets=npk, payload_bytes=nbytes, payload_mb_per_h=round(nbytes * 3600 / SECONDS / 1e6, 2),
                mean_packet_bytes=round(nbytes / npk, 1), encode_us_median=round(float(np.median(per)), 1),
                encode_us_p99=round(float(np.percentile(per, 99)), 1), cpu_pct_one_core=round(100 * cpu / SECONDS, 3))


def live_writer(name, x, ch, d):
    path = os.path.join(d, f"bench_{name}_{ch}ch{C.EXT[name]}")
    copts = dict(O.COPTS, b="128000" if ch == 1 else "256000") if name in O.WRITERS else dict(C.PYAV[name][3])
    fmt, ext, codec, _, mopts = C.PYAV[name]
    out = av.open(path, "w", format=fmt, options=dict(mopts))
    layout = "mono" if ch == 1 else "stereo"
    st = out.add_stream(codec, rate=O.RATE, layout=layout)
    st.codec_context.options = copts
    st.time_base = fractions.Fraction(1, O.RATE)
    per, payload, npk = [], 0, 0
    c0 = time.process_time()
    for k in range(0, len(x), O.BLOCK):
        blk = x[k:k + O.BLOCK]
        fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(blk.reshape(1, -1)), format="s16", layout=layout)
        fr.sample_rate, fr.pts, fr.time_base = O.RATE, k, st.time_base
        t = time.perf_counter_ns()
        for p in st.encode(fr):
            payload += p.size; npk += 1
            out.mux(p)
        per.append(time.perf_counter_ns() - t)
    for p in st.encode(None):
        payload += p.size; npk += 1
        out.mux(p)
    out.close()
    cpu = time.process_time() - c0
    size = os.path.getsize(path)
    per = np.array(per) / 1e3
    os.remove(path)
    return dict(file_bytes=size, mb_per_h=round(size * 3600 / SECONDS / 1e6, 2), packets=npk,
                overhead_bytes_per_packet=round((size - payload) / npk, 1), overhead_pct=round(100 * (size - payload) / payload, 2),
                write_us_median=round(float(np.median(per)), 1), write_us_p99=round(float(np.percentile(per, 99)), 1),
                cpu_pct_one_core=round(100 * cpu / SECONDS, 3))


def main():
    d = os.path.join(O.SCRATCH, "bench"); os.makedirs(d, exist_ok=True)
    res = dict(av=av.__version__, seconds=SECONDS, codec_options=O.COPTS, encode_only={}, live={})
    for kind in ("timing", "quiet"):
        for ch in (1, 2):
            x = signal(kind, ch)
            res["encode_only"][f"{kind}_{ch}ch"] = encode_only(x, ch)
            for name in ["ogg_pd20", "mka_ct1", "webm_ct1", "mp4_fragpkt", "mp4_frag100", "mp4_plain", "wav_pyav", "flac_pyav"]:
                res["live"][f"{name}_{kind}_{ch}ch"] = live_writer(name, x, ch, d)
            print(kind, ch, res["encode_only"][f"{kind}_{ch}ch"], flush=True)
    json.dump(res, open(os.path.join(O.RESULTS, "bench_opus.json"), "w"), indent=1)
    for k, v in res["live"].items():
        print(k, v["mb_per_h"], v["overhead_bytes_per_packet"], v["write_us_median"], v["write_us_p99"], v["cpu_pct_one_core"])


if __name__ == "__main__":
    main()
