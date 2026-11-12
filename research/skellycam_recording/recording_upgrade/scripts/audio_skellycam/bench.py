"""Encoder cost, size per hour, click-timing preservation, resampling cost, and GIL behaviour (PyAV 19.0.2).

Synthetic 60 s signal (never a real microphone): room-noise floor at about -60 dBFS, plus 'activity'
bursts of band-limited noise at about -20 dBFS for 30 % of the time, a quiet tone, and a click every
second at sample 24000 + k*48000. FLAC sizes depend on the signal, so they are indicative only.

Usage: python -I bench.py <out_json>
"""
import fractions
import json
import os
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ac_common import SCRATCH  # noqa: E402
import av  # noqa: E402

RATE = 48000
SECONDS = 60


def signal(rate=RATE, seconds=SECONDS, ch=1, seed=1):
    rng = np.random.default_rng(seed)
    n = rate * seconds
    x = rng.normal(0, 10 ** (-60 / 20), n)
    # bursts: 300 ms of low-passed noise, on 30 % of the time
    burst = np.zeros(n)
    for k in range(int(seconds / 1.0)):
        if rng.random() < 0.3:
            s = int(k * rate + rng.random() * 0.6 * rate)
            m = int(0.3 * rate)
            b = rng.normal(0, 10 ** (-20 / 20), m)
            b = np.convolve(b, np.ones(8) / 8, mode="same")
            burst[s:s + m] += b[: max(0, min(m, n - s))]
    t = np.arange(n)
    x += burst + 0.01 * np.sin(2 * np.pi * 220 * t / rate)
    x[(t % rate) == rate // 2] = 0.9
    y = np.clip(x * 32767, -32768, 32767).astype(np.int16)
    if ch == 2:
        y = np.stack([y, np.roll(y, 7)], axis=1)
    else:
        y = y[:, None]
    return y


def encode(codec, path, fmt, sig, rate, bitrate=None, opts=None, block=1024):
    ch = sig.shape[1]
    layout = "mono" if ch == 1 else "stereo"
    out = av.open(path, "w", format=fmt, options={"flush_packets": "1"})
    st = out.add_stream(codec, rate=rate, layout=layout)
    if bitrate:
        st.codec_context.bit_rate = bitrate
    st.codec_context.options = dict(opts or {})
    tb = fractions.Fraction(1, rate)
    c0 = time.process_time(); w0 = time.perf_counter()
    for i in range(0, sig.shape[0], block):
        blk = sig[i:i + block]
        fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(blk.reshape(1, -1)), format="s16", layout=layout)
        fr.sample_rate = rate; fr.pts = i; fr.time_base = tb
        for p in st.encode(fr):
            out.mux(p)
    for p in st.encode(None):
        out.mux(p)
    out.close()
    return time.process_time() - c0, time.perf_counter() - w0


def decode_mono48(path):
    with av.open(path) as c:
        rs = av.AudioResampler(format="s16", layout="mono", rate=RATE)
        ch = []
        for fr in c.decode(audio=0):
            for f2 in rs.resample(fr):
                ch.append(f2.to_ndarray().reshape(-1))
        for f2 in rs.resample(None):
            ch.append(f2.to_ndarray().reshape(-1))
    return np.concatenate(ch)


def click_offsets(x):
    xa = np.abs(x.astype(np.float64))
    return [int(np.argmax(xa[k * RATE:(k + 1) * RATE])) - RATE // 2 for k in range(SECONDS)]


def gil_probe(work, sig):
    """Pure-Python counter in the main thread, with and without an encoder thread running."""
    def spin(seconds):
        n = 0; t_end = time.perf_counter() + seconds
        while time.perf_counter() < t_end:
            n += 1
        return n
    base = spin(2.0)
    res = {}
    for codec, fmt, ext, br in (("libopus", "ogg", ".opus", 64000), ("flac", "flac", ".flac", None)):
        stop = threading.Event(); enc_s = [0.0]; loops = [0]

        def worker():
            while not stop.is_set():
                c0 = time.perf_counter()
                encode(codec, os.path.join(work, "gil" + ext), fmt, sig[: RATE * 5], RATE, br)
                enc_s[0] += time.perf_counter() - c0; loops[0] += 1
        th = threading.Thread(target=worker); th.start()
        time.sleep(0.2)
        n = spin(2.0)
        stop.set(); th.join()
        res[codec] = dict(main_thread_spin_ratio=round(n / base, 3), encoder_loops=loops[0])
    res["note"] = "ratio 1.0 = encoder never held the GIL against the main thread; 0.5 = it held it half the time"
    return res


def main():
    out = sys.argv[1]
    work = os.path.join(SCRATCH, "bench")
    os.makedirs(work, exist_ok=True)
    mono = signal(); stereo = signal(ch=2)
    rows = []
    cfgs = [
        ("opus mono 24k voip", "libopus", "ogg", ".opus", mono, 24000, {"application": "voip"}),
        ("opus mono 32k", "libopus", "ogg", ".opus", mono, 32000, {}),
        ("opus mono 48k", "libopus", "ogg", ".opus", mono, 48000, {}),
        ("opus mono 64k", "libopus", "ogg", ".opus", mono, 64000, {}),
        ("opus mono 96k", "libopus", "ogg", ".opus", mono, 96000, {}),
        ("opus stereo 96k", "libopus", "ogg", ".opus", stereo, 96000, {}),
        ("opus stereo 128k", "libopus", "ogg", ".opus", stereo, 128000, {}),
        ("opus mono 64k fd10", "libopus", "ogg", ".opus", mono, 64000, {"frame_duration": "10"}),
        ("flac mono lvl5", "flac", "flac", ".flac", mono, None, {}),
        ("flac mono lvl8", "flac", "flac", ".flac", mono, None, {"compression_level": "8"}),
        ("flac mono lvl0", "flac", "flac", ".flac", mono, None, {"compression_level": "0"}),
        ("flac stereo lvl5", "flac", "flac", ".flac", stereo, None, {}),
        ("vorbis stereo 96k (native, experimental)", "vorbis", "ogg", ".ogg", stereo, 96000, {"strict": "experimental"}),
        ("pcm wav mono", "pcm_s16le", "wav", ".wav", mono, None, {}),
    ]
    for label, codec, fmt, ext, sig, br, opts in cfgs:
        path = os.path.join(work, label.replace(" ", "_").replace("(", "").replace(")", "").replace(",", "") + ext)
        reps = []
        for _ in range(3):
            cpu, wall = encode(codec, path, fmt, sig, RATE, br, opts)
            reps.append((cpu, wall))
        cpu = sorted(r[0] for r in reps)[1]; wall = sorted(r[1] for r in reps)[1]
        size = os.path.getsize(path)
        x = decode_mono48(path)
        offs = click_offsets(x)
        rows.append(dict(config=label, codec=codec, container=fmt, channels=sig.shape[1], bitrate=br, options=opts,
                         bytes_60s=size, mb_per_hour=round(size * 60 / 1e6, 1), kbps_actual=round(size * 8 / SECONDS / 1000, 1),
                         cpu_s_per_audio_s=round(cpu / SECONDS, 5), cpu_pct_of_one_core=round(100 * cpu / SECONDS, 3),
                         wall_s_per_audio_s=round(wall / SECONDS, 5),
                         click_offset_samples=dict(min=min(offs), max=max(offs), nonzero=sum(1 for o in offs if o != 0))))
        print(rows[-1]["config"], rows[-1]["mb_per_hour"], "MB/h", rows[-1]["cpu_pct_of_one_core"], "% core", rows[-1]["click_offset_samples"], flush=True)
        os.remove(path)
    # resampling 44.1k -> 48k, mono s16, 1024-sample blocks
    sig44 = signal(rate=44100)
    rs = av.AudioResampler(format="s16", layout="mono", rate=48000)
    c0 = time.process_time(); nout = 0
    for i in range(0, sig44.shape[0], 1024):
        fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(sig44[i:i + 1024].reshape(1, -1)), format="s16", layout="mono")
        fr.sample_rate = 44100; fr.pts = i; fr.time_base = fractions.Fraction(1, 44100)
        for f2 in rs.resample(fr):
            nout += f2.samples
    for f2 in rs.resample(None):
        nout += f2.samples
    resample = dict(cpu_pct_of_one_core=round(100 * (time.process_time() - c0) / SECONDS, 3), in_samples=int(sig44.shape[0]), out_samples=int(nout),
                    expected_out=int(sig44.shape[0] * 48000 / 44100))
    print("resample", resample)
    gil = gil_probe(work, mono)
    print("gil", gil)
    json.dump(dict(pyav=av.__version__, libopus="1.6.1", seconds=SECONDS, signal="synthetic (see docstring)", rows=rows,
                   resample_44k1_to_48k=resample, gil=gil), open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
