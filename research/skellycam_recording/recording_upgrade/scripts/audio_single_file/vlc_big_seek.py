# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Where does VLC's --start-time land in a WAV past 4 GiB? Searches the whole index range for VLC's first output
sample (big_wav.py's nearby search found nothing). Seeks at 1,000 s (below 4 GiB) and 23,500 s (above).

Usage: uv run --script .../vlc_big_seek.py     Output: results/audio_single_file/vlc_big_seek.json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asf_common as C  # noqa: E402

BDIR = os.path.join(C.SCRATCH, "big")


def find_anywhere(x, n_max):
    """All n (< n_max) whose signal matches x's first 64 samples."""
    nz = int((x != 0).any(axis=1).argmax()) if len(x) else 0
    x = x[nz:]
    if len(x) < 64:
        return nz, []
    low = int(x[0, 0].view(np.uint16))
    cand = np.arange(low, n_max, 65536, dtype=np.uint64)
    r = (((cand * C.MUL) >> np.uint64(50)).astype(np.int32) - 8192).astype(np.int16)
    hits = [int(n) for n in cand[r == x[0, 1]] if np.array_equal(C.sig(int(n), 64), x[:64])]
    return nz, hits


def main():
    res = {}
    for f in ("rf64auto_clean.wav", "rf64auto_killed_repaired.wav"):
        p = os.path.join(BDIR, f)
        for t in (1000.0, 23500.0):
            rc, wall, y = C.vlc_afile(p, os.path.join(BDIR, "probe.wav"), start_s=t, run_s=0.5)
            nz, hits = find_anywhere(y, 1_150_080_000) if y is not None else (None, [])
            res[f"{f}@{t:.0f}"] = dict(rc=rc, samples=None if y is None else int(len(y)), leading_zero_samples=nz,
                                      found_at_sample=hits, target_sample=int(t * C.RATE),
                                      found_minus_target=[h - nz - int(t * C.RATE) for h in hits],
                                      target_bytes_mod_4GiB_as_sample=(int(t * C.RATE) * 4 % (1 << 32)) // 4)
            print(f, t, res[f"{f}@{t:.0f}"])
    json.dump(res, open(os.path.join(C.RESULTS, "vlc_big_seek.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
