"""Sample-position alignment: does decoded sample i equal captured sample i, in every decoder?

Writes 10 s of synthetic tone with a full-scale click at sample 24000 + k*48000 (48 kHz) through
BlockWriter (pts = running sample count), cleanly closed. Then decodes with PyAV, the ffmpeg CLI and
VLC 3.0.24 (transcode dump, and the afile audio output = the playback path) and finds each click (argmax of |x| in each 1 s window). Offset = found - expected, in
samples at 48 kHz. Opus has 312 samples of encoder pre-skip; FLAC/WAV have none.

Also: a 44.1 kHz input resampled to 48 kHz inside the writer (PyAV's encoder-side resampler), to see
whether the resampler delay shifts the timeline.

Files go to the scratchpad (aligned/), used again by the Electron test.
Usage: python -I align.py <out_json>
"""
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ac_common import FFMPEG, FORMATS, SCRATCH, VLC, BlockWriter, synth  # noqa: E402
import av  # noqa: E402

FMTS = ["ogg_opus_pd60", "ogg_opus_pd20", "mka_opus_ct100", "webm_opus_ct100", "flac_native", "ogg_flac", "mka_flac_ct100", "wav_pcm"]
SECONDS = 10


def clicks_found(x, rate=48000):
    x = np.abs(x.astype(np.float64))
    out = []
    for k in range(SECONDS):
        w = x[k * rate:(k + 1) * rate]
        if len(w) < rate // 2:
            break
        out.append(k * rate + int(np.argmax(w)))
    return out


def dec_pyav(path):
    with av.open(path) as c:
        st = c.streams.audio[0]
        rs = av.AudioResampler(format="s16", layout="mono", rate=48000)
        chunks = []
        for fr in c.decode(st):
            for f2 in rs.resample(fr):
                chunks.append(f2.to_ndarray().reshape(-1))
        for f2 in rs.resample(None):
            chunks.append(f2.to_ndarray().reshape(-1))
    return np.concatenate(chunks)


def dec_ffmpeg(path):
    p = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", "48000", "-"], capture_output=True)
    return np.frombuffer(p.stdout, np.int16)


def dec_vlc(path):
    dst = path + ".vlc.wav"
    if os.path.exists(dst):
        os.remove(dst)
    sout = f"#transcode{{acodec=s16l,channels=1,samplerate=48000}}:std{{access=file,mux=wav,dst='{dst}'}}"
    subprocess.run([VLC, "-I", "dummy", "--no-repeat", "--play-and-exit", "--no-video", path, f"--sout={sout}", "vlc://quit"],
                   capture_output=True, timeout=120)
    b = open(dst, "rb").read()
    os.remove(dst)
    i = b.find(b"data")
    return np.frombuffer(b[i + 8:i + 8 + ((len(b) - i - 8) // 2) * 2], np.int16)


def dec_vlc_play(path):
    """VLC's real playback path: the afile audio output writes what would go to the speakers (real time)."""
    dst = path + ".afile.wav"
    if os.path.exists(dst):
        os.remove(dst)
    subprocess.run([VLC, "-I", "dummy", "--play-and-exit", "--no-video", "--aout=afile", f"--audiofile-file={dst}",
                    "--audiofile-wav", "--audiofile-format=s16", "--audiofile-channels=1", path, "vlc://quit"],
                   capture_output=True, timeout=120)
    b = open(dst, "rb").read()
    os.remove(dst)
    rate = int.from_bytes(b[24:28], "little")
    i = b.find(b"data")
    x = np.frombuffer(b[i + 8:i + 8 + ((len(b) - i - 8) // 2) * 2], np.int16)
    if rate != 48000:  # place samples on the 48 kHz grid by index scaling (nearest)
        idx = np.round(np.arange(int(len(x) * 48000 / rate)) * rate / 48000).astype(int)
        x = x[np.clip(idx, 0, len(x) - 1)]
    return x


def main():
    out = sys.argv[1]
    work = os.path.join(SCRATCH, "aligned")
    os.makedirs(work, exist_ok=True)
    expected = [24000 + k * 48000 for k in range(SECONDS)]
    res = []
    jobs = [(f, 48000) for f in FMTS] + [("ogg_opus_pd60", 44100), ("flac_native", 44100)]
    for name, in_rate in jobs:
        tag = name if in_rate == 48000 else f"{name}_from{in_rate // 100}"
        path = os.path.join(work, tag + FORMATS[name]["ext"])
        # writer runs at the format's rate (48k for Opus; FLAC/WAV take the input rate unless 48k)
        enc_rate = 48000 if FORMATS[name]["codec"] == "libopus" else in_rate
        w = BlockWriter(name, path, rate=enc_rate)
        n = 0
        while n < in_rate * SECONDS:
            blk = synth(n, 1024, in_rate)
            if in_rate != enc_rate:
                # feed frames at the input rate; PyAV's encode() resamples to the codec rate
                import fractions
                fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(blk.reshape(1, -1)), format="s16", layout="mono")
                fr.sample_rate = in_rate
                fr.pts = n
                fr.time_base = fractions.Fraction(1, in_rate)
                for p in w.st.encode(fr):
                    w.out.mux(p)
            else:
                w.write(blk)
            n += 1024
        w.close()
        # expected click positions in 48 kHz decoded samples
        exp = [round((in_rate // 2 + k * in_rate) * 48000 / in_rate) for k in range(SECONDS)]
        row = dict(file=os.path.basename(path), format=name, input_rate=in_rate, encoder_rate=enc_rate)
        for dn, fn in (("pyav", dec_pyav), ("ffmpeg", dec_ffmpeg), ("vlc", dec_vlc), ("vlc_play", dec_vlc_play)):
            try:
                x = fn(path)
                f = clicks_found(x)
                offs = [a - b for a, b in zip(f, exp)]
                row[dn] = dict(decoded_samples_48k=int(len(x)), click_offsets=offs)
            except Exception as e:  # noqa: BLE001
                row[dn] = dict(error=str(e)[:200])
        with av.open(path) as c:
            st = c.streams.audio[0]
            pk = next(c.demux(st))
            row["first_packet_pts"] = pk.pts
            row["stream_time_base"] = str(st.time_base)
            row["start_time"] = st.start_time
        print(tag, {k: (v.get("click_offsets") if isinstance(v, dict) else v) for k, v in row.items() if k in ("pyav", "ffmpeg", "vlc", "vlc_play")}, flush=True)
        res.append(row)
    json.dump(dict(pyav=av.__version__, expected_48k=expected, results=res), open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
