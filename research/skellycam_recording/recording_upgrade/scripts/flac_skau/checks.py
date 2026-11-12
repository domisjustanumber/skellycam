"""Follow-up checks after flac_skau.py (skellycam-phase1 venv).
Usage:
  python -I checks.py recovery <outdir>     killed .flac (F2) -> .mka stream copy, then append a .skau
  python -I checks.py vlc <outdir>          compare VLC afile WAVs with the source (run VLC first, below)

VLC (PowerShell; native Windows paths), per file f in f1_1ch.flac, f1_1ch_skau.mka, f1_2ch_skau.mka:
  vlc.exe -I dummy --dummy-quiet --no-video --play-and-exit --aout=afile --audiofile-file="<outdir>\\vlc_<f>.wav"
          --audiofile-wav --audiofile-format=s16 "<outdir>\\<f>" vlc://quit
"""
import json, os, sys, wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import flac_skau as fs  # noqa: E402


def recovery(outdir):
    out = {}
    for k in (40, 138, 301):
        src = os.path.join(outdir, f"f2_kill{k}.flac"); dst = src.replace(".flac", "_recovered.mka")
        if os.path.exists(dst): os.remove(dst)
        fs.remux_mka(src, dst)
        blob = open(src, "rb").read(); hl, _ = fs.flac_header_len(blob)
        total = int.from_bytes(blob[18:26], "big") & ((1 << 36) - 1)        # STREAMINFO total samples
        sc = fs.scan_mkv(dst); mb = open(dst, "rb").read()
        blocks = [b for b in sc["blocks"] if b[0] == 1]
        concat = b"".join(mb[o:o + s] for _, o, s, *r in blocks)
        a = fs.decode_pcm(src); b = fs.decode_pcm(dst); ref = fs.signal(20, 1, seed=5)
        r = fs.aa.append(dst, os.urandom(4096), name="skellycam_audio.skau", mime="application/x-skellycam-audio-timing")
        out[f"kill{k}"] = dict(streaminfo_total_samples=total, mka_blocks=len(blocks),
                               frames_bytes_identical=concat == blob[hl:], decoded_samples=len(b),
                               decoded_equals_killed_flac=bool(np.array_equal(a, b)),
                               decoded_is_source_prefix=bool(np.array_equal(b, ref[:len(b)])),
                               append_after_recovery_void_pad=r["void_pad"])
    json.dump(out, open(os.path.join(outdir, "recovery_check.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


def vlc(outdir):
    res = {}
    for f, ch in (("f1_1ch.flac", 1), ("f1_1ch_skau.mka", 1), ("f1_2ch_skau.mka", 2)):
        ref = fs.signal(30, ch)
        w = wave.open(os.path.join(outdir, f"vlc_{f}.wav"))
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, w.getnchannels())
        offset = None
        for lag in range(-4000, 4001):                      # first lag where 1 s of samples matches exactly
            lo = max(0, lag)
            if len(x) >= lo + 48000 and np.array_equal(x[lo:lo + 48000, 0], ref[lo - lag:lo - lag + 48000, 0]):
                offset = lag; break
        n = min(len(x), len(ref))
        res[f] = dict(vlc_rate=w.getframerate(), vlc_channels=w.getnchannels(), vlc_samples=len(x),
                      ref_samples=len(ref), offset_samples=offset,
                      prefix_identical=bool(offset == 0 and np.array_equal(x[:n], ref[:n])),
                      missing_tail_samples=int(len(ref) - len(x)))
    json.dump(res, open(os.path.join(outdir, "vlc_check.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"recovery": recovery, "vlc": vlc}[sys.argv[1]](sys.argv[2])
