# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""How a device-side gap plays in Opus files, per container, as ../gap_test.py. 10 s of the opus_common timing
signal; device samples [239688, 244488) (4,800 = 100 ms; starts on an Opus packet boundary of the encoder timeline,
960k - 312) are 'lost by the device'.
  <c>_silence : zeros encoded in their place (file sample index == device sample index)
  <c>_ptsjump : the samples are not encoded; packets after the gap get pts + 4,800 (the container carries the gap:
                Ogg granule jump, Matroska block timestamp jump, MP4 fragment timestamps)
Readers: PyAV (count, packet pts steps), ffmpeg CLI (default and -af aresample=async=1), VLC afile playback.
Metric: click offsets per 1 s window against the DEVICE index (clicks 0-4 before the gap, 5-9 after).
After the gap: 0 = in sync; -4,800 = audio early by 100 ms.

Usage: uv run --script .../opus/gap_opus.py     Output: results/audio_single_file/opus/gap_opus.json
"""
import fractions
import json
import os
import sys

import av
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import opus_common as O  # noqa: E402

C = O.C
N, G0, GAP = 480000, 239688, 4800
CONTAINERS = ["ogg_pd20", "mka_ct1", "webm_ct1", "mp4_fragpkt", "mp4_plain"]


def write(name, variant, path):
    fmt, _, mopts = O.WRITERS[name]
    dev = O.sig(0, N)
    if variant == "silence":
        x = dev.copy(); x[G0:G0 + GAP] = 0
    else:
        x = np.r_[dev[:G0], dev[G0 + GAP:]]
    out = av.open(path, "w", format=fmt, options=dict(mopts))
    st = out.add_stream("libopus", rate=O.RATE, layout="stereo")
    st.codec_context.options = dict(O.COPTS)
    tb = fractions.Fraction(1, O.RATE)
    st.time_base = tb

    def mux(pkts):
        for p in pkts:
            if variant == "ptsjump" and p.pts is not None and p.pts >= G0:
                p.pts += GAP; p.dts = p.pts
            out.mux(p)
    for k in range(0, len(x), 960):
        blk = x[k:k + 960]
        fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(blk.reshape(1, -1)), format="s16", layout="stereo")
        fr.sample_rate, fr.pts, fr.time_base = O.RATE, k, tb
        mux(st.encode(fr))
    mux(st.encode(None))
    out.close()


def shifts(x):
    if x is None or len(x) < O.RATE:
        return dict(samples=None if x is None else int(len(x)))
    offs = O.click_offsets(x)
    return dict(samples=int(len(x)), click_offsets=offs, pre=sorted(set(offs[:5])), post=sorted(set(offs[5:])))


def main():
    gdir = os.path.join(O.SCRATCH, "gap"); os.makedirs(gdir, exist_ok=True)
    vdir = os.path.join(O.SCRATCH, "vlc_out"); os.makedirs(vdir, exist_ok=True)
    res = dict(gap_samples=GAP, gap_at_device_sample=G0, variants={})
    for name in CONTAINERS:
        for variant in ("silence", "ptsjump"):
            tag = f"{name}_{variant}"
            path = os.path.join(gdir, tag + O.WRITERS[name][1])
            write(name, variant, path)
            info, x = O.decode_all(path)
            r = dict(pyav=dict(shifts(x), duration_s=info["duration_s"], error=info["error"]))
            with av.open(path) as c:
                st = c.streams.audio[0]
                pts = [pk.pts for pk in c.demux(st) if pk.size and pk.pts is not None]
                tb = st.time_base
            steps = np.diff(np.array(pts, dtype=np.int64) * tb.numerator * O.RATE // tb.denominator)
            r["pyav"]["packet_pts_steps"] = {str(int(k)): int(v) for k, v in zip(*np.unique(steps, return_counts=True))}
            r["ffmpeg_default"] = shifts(O.ffmpeg_f(path)[0])
            r["ffmpeg_aresample_async"] = shifts(O.ffmpeg_f(path, ["-af", "aresample=async=1"])[0])
            rc, wall, y = C.vlc_afile(path, os.path.join(vdir, tag + ".gap.wav"))
            r["vlc_play"] = dict(rc=rc, **shifts(y))
            res["variants"][tag] = r
            print(tag, {k: (v.get("pre"), v.get("post"), v.get("samples")) for k, v in r.items()}, flush=True)
    json.dump(res, open(os.path.join(O.RESULTS, "gap_opus.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
