"""Audio bitrate and encode cost per codec on synthetic proxies of camera audio (60 s, 48 kHz stereo).
Proxies are synthetic: real camera audio sizes are not measured here.
Usage: python -I size_test.py <out json>
"""
import fractions, json, sys, time

import av
import numpy as np
from scipy import signal

SR, SEC = 48000, 60


def pink(n, rng):
    w = rng.standard_normal(n)
    b, a = [0.049922035, -0.095993537, 0.050612699, -0.004408786], [1, -2.494956002, 2.017265875, -0.522189400]
    p = signal.lfilter(b, a, w)
    return p / np.std(p)


def proxies():
    rng = np.random.default_rng(3)
    n = SR * SEC
    db = lambda d: 10 ** (d / 20)
    common_p, l_p, r_p = pink(n, rng), pink(n, rng), pink(n, rng)
    room = np.stack([0.8 * common_p + 0.6 * l_p, 0.8 * common_p + 0.6 * r_p]) * db(-45)
    # speech-like: band-limited noise, 4 Hz syllable envelope, gaps, on top of the room
    bp = signal.butter(4, [200, 4000], btype="band", fs=SR, output="sos")
    v = signal.sosfilt(bp, rng.standard_normal(n)); v /= np.std(v)
    t = np.arange(n) / SR
    env = np.clip(np.sin(2 * np.pi * 4 * t) + 0.3, 0, None) * (np.sin(2 * np.pi * 0.2 * t) > -0.3)
    speech = room + np.stack([v * env, 0.9 * v * env]) * db(-20)
    loud = np.stack([0.8 * common_p + 0.6 * l_p, 0.8 * common_p + 0.6 * r_p]) * db(-20)
    white = rng.standard_normal((2, n)) * db(-12)
    return dict(quiet_room=room, speech_like=speech, loud_ambient=loud, white_noise_worst=white)


def encode(x, codec, layout, **kw):
    out = av.open("NUL" if sys.platform == "win32" else "/dev/null", "w", format="matroska")
    s = out.add_stream(codec, rate=SR)
    if codec == "flac":
        s.format = "s32" if kw.get("s32") else "s16"
        if kw.get("s32"): s.codec_context.bits_per_raw_sample = 24
    if codec == "vorbis":
        s.codec_context.options = {"strict": "experimental"}
    if "br" in kw: s.bit_rate = kw["br"]
    s.layout = layout
    if layout == "mono": x = x.mean(axis=0, keepdims=True)
    x = np.clip(x, -1, 1).astype(np.float32)
    total, t0 = 0, time.process_time()
    for i in range(0, x.shape[1], 1600):
        f = av.AudioFrame.from_ndarray(np.ascontiguousarray(x[:, i:i + 1600]), format="fltp", layout=layout)
        f.sample_rate = SR; f.pts = i; f.time_base = fractions.Fraction(1, SR)
        for p in s.encode(f): total += p.size
    for p in s.encode(None): total += p.size
    cpu = time.process_time() - t0
    out.close()
    return dict(kbps=round(total * 8 / SEC / 1000, 1), cpu_ms_per_audio_s=round(cpu / SEC * 1000, 2))


def main():
    res = dict(av=av.__version__, note="synthetic proxies, 60 s, 48 kHz", results={})
    encs = [("flac16_stereo", "flac", "stereo", {}), ("flac24_stereo", "flac", "stereo", dict(s32=True)),
            ("flac16_mono", "flac", "mono", {}),
            ("opus64_mono", "libopus", "mono", dict(br=64000)), ("opus96_stereo", "libopus", "stereo", dict(br=96000)),
            ("opus128_stereo", "libopus", "stereo", dict(br=128000)), ("vorbis128_stereo", "vorbis", "stereo", dict(br=128000)),
            ("pcm_s16le_stereo", "pcm_s16le", "stereo", {})]
    for pname, x in proxies().items():
        res["results"][pname] = {e[0]: encode(x, e[1], e[2], **e[3]) for e in encs}
        print(pname, res["results"][pname], flush=True)
    json.dump(res, open(sys.argv[1], "w"), indent=1)


if __name__ == "__main__":
    main()
