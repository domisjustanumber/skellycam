# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""How a device-side gap (WASAPI glitch: GAP samples never delivered) plays, per way of writing it.

10 s stereo index signal; blocks 235..239 (5 x 1024 = 5,120 samples, 106.7 ms) are 'lost by the device'.
  wav_silence / flac_silence : zeros written in their place (file sample index == device sample index)
  wav_jump                   : nothing written (later audio sits GAP samples earlier in the file)
  flac_ptsgap                : native FLAC, frames given pts with the jump (the FLAC muxer ignores pts)
  mka_flac_ptsgap            : FLAC in Matroska, block timestamps jump by GAP (container carries the gap)
Readers: PyAV (samples, pts jumps), ffmpeg CLI (default, and -af aresample=async=1), VLC afile playback.
Metric: after the gap, shift = device index of output sample p - p. 0 = in sync; +GAP = audio early by GAP.

Usage: uv run --script .../gap_test.py     Output: results/audio_single_file/gap_test.json
"""
import fractions
import json
import os
import subprocess
import sys

import av
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asf_common as C  # noqa: E402

N_BLOCKS, GAP0, GAP_BLOCKS = 469, 235, 5
GAP = GAP_BLOCKS * C.BLOCK


def write(name, path):
    lost = set(range(GAP0, GAP0 + GAP_BLOCKS))
    if name.startswith("wav"):
        import soundfile as sf
        with sf.SoundFile(path, "w", samplerate=C.RATE, channels=2, subtype="PCM_16", format="WAV") as f:
            for k in range(N_BLOCKS):
                if k in lost:
                    if name == "wav_silence":
                        f.write(np.zeros((C.BLOCK, 2), np.int16))
                    continue
                f.write(C.sig(k * C.BLOCK, C.BLOCK))
        return
    fmt = "matroska" if name.startswith("mka") else "flac"
    out = av.open(path, "w", format=fmt)
    st = out.add_stream("flac", rate=C.RATE, layout="stereo")
    st.codec_context.options = {"frame_size": "1024"}
    tb = fractions.Fraction(1, C.RATE)
    st.time_base = tb
    for k in range(N_BLOCKS):
        if k in lost and name != "flac_silence":
            continue
        blk = np.zeros((C.BLOCK, 2), np.int16) if k in lost else C.sig(k * C.BLOCK, C.BLOCK)
        fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(blk.reshape(1, -1)), format="s16", layout="stereo")
        fr.sample_rate, fr.pts, fr.time_base = C.RATE, k * C.BLOCK, tb  # pts = device sample index
        for p in st.encode(fr):
            p.pts = p.dts = fr.pts  # keep the device index on the packet (the encoder renumbers otherwise)
            out.mux(p)
    for p in st.encode(None):
        out.mux(p)
    out.close()


def shifts(x):
    """Device-index shift before and after the gap, and how the gap region looks."""
    pre = C.locate(x[:200_000], 0)
    p = 300 * C.BLOCK
    post = C.locate(x[p:p + 48_000], p) if len(x) > p + 48_000 else dict(n0=None)
    g0 = GAP0 * C.BLOCK
    region = x[g0:g0 + GAP]
    return dict(samples=int(len(x)), pre_n0=pre["n0"], pre_exact=pre["exact"],
                post_shift=None if post.get("n0") is None else post["n0"] - p, post_exact=post.get("exact"),
                gap_region_zero=bool(len(region) and not region.any()))


def ffmpeg_x(path, extra=()):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, *extra, "-f", "s16le", "-ac", "2", "-"], capture_output=True)
    return np.frombuffer(r.stdout[: len(r.stdout) // 4 * 4], np.int16).reshape(-1, 2)


def main():
    gdir = os.path.join(C.SCRATCH, "gap"); os.makedirs(gdir, exist_ok=True)
    vdir = os.path.join(C.SCRATCH, "vlc_out"); os.makedirs(vdir, exist_ok=True)
    res = dict(gap_samples=GAP, gap_at_sample=GAP0 * C.BLOCK, variants={})
    for name, ext in (("wav_silence", ".wav"), ("wav_jump", ".wav"), ("flac_silence", ".flac"),
                      ("flac_ptsgap", ".flac"), ("mka_flac_ptsgap", ".mka")):
        path = os.path.join(gdir, name + ext)
        write(name, path)
        r = {}
        info, x = C.decode_pyav(path)
        r["pyav"] = dict(shifts(x), duration_s=info["duration_s"])
        with av.open(path) as c:
            pts = [pk.pts for pk in c.demux(c.streams.audio[0]) if pk.size]
            tb = c.streams.audio[0].time_base
        steps = np.diff(np.array(pts, dtype=np.int64) * tb.numerator * C.RATE // tb.denominator)
        r["pyav"]["packet_pts_steps"] = {str(int(k)): int(v) for k, v in zip(*np.unique(steps, return_counts=True))}
        r["ffmpeg_default"] = shifts(ffmpeg_x(path))
        r["ffmpeg_aresample_async"] = shifts(ffmpeg_x(path, ["-af", "aresample=async=1"]))
        rc, wall, y = C.vlc_afile(path, os.path.join(vdir, name + ".gap.wav"))
        r["vlc_play"] = dict(rc=rc, **shifts(y)) if y is not None else dict(rc=rc)
        res["variants"][name] = r
        print(name, json.dumps(r)[:400])
    json.dump(res, open(os.path.join(C.RESULTS, "gap_test.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
