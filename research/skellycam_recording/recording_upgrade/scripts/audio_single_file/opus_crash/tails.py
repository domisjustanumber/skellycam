# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Structure of killed vs cleanly closed files (same deterministic signal and encoder, so their bytes are identical
up to the kill point except what the close rewrites):
  fMP4 : top-level box list summary, complete moof+mdat pairs, bytes after the last complete pair (torn tail),
         boxes the clean close appends (e.g. mfra), header bytes the close rewrote (diff over the common prefix)
  MKA / WAV : header bytes the close rewrote, bytes the close appended
Usage: uv run --script .../opus_crash/tails.py      Output: results/audio_single_file/opus_crash/tails.json
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crash_common as K  # noqa: E402


def diff_ranges(a, b):
    n = min(len(a), len(b))
    out, i = [], 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            out.append([i, j - i, a[i:j].hex()[:64], b[i:j].hex()[:64]])
            i = j
        else:
            i += 1
    return out


def main():
    res = {}
    for w, (_, ext, *_r) in K.WRITERS.items():
        clean = open(os.path.join(K.SCRATCH, "clean", f"{w}__clean{ext}"), "rb").read()
        for p in sorted(glob.glob(os.path.join(K.SCRATCH, "short", f"{w}__*{ext}")) + glob.glob(os.path.join(K.SCRATCH, "long", f"{w}__*{ext}"))):
            b = open(p, "rb").read()
            r = dict(bytes=len(b))
            if ext == ".m4a":
                bx = K.boxes(b)
                end, frags = K.fmp4_complete_end(b)
                r.update(n_boxes=len(bx), first=[x[:3] for x in bx[:3]], last=[list(x) for x in bx[-3:]], complete_pairs=len(frags),
                         complete_end=end, torn_tail_bytes=len(b) - end)
            # what the clean close changed inside the common prefix (only meaningful within the clean file's length)
            n = min(len(b), len(clean))
            # (when the killed file is longer, the last ranges are just the clean file's own trailer vs more audio)
            r["close_rewrote_in_prefix"] = diff_ranges(b[:n], clean[:n])[:6]
            res[os.path.relpath(p, K.SCRATCH)] = r
        if ext == ".m4a":
            bx = K.boxes(clean)
            res[f"clean/{w}"] = dict(bytes=len(clean), last=[list(x) for x in bx[-3:]], types={t: sum(1 for x in bx if x[0] == t) for t in {x[0] for x in bx}})
        else:
            res[f"clean/{w}"] = dict(bytes=len(clean))
    json.dump(res, open(os.path.join(K.RESULTS, "tails.json"), "w"), indent=1)
    for k, v in res.items():
        print(k, json.dumps(v)[:600])


if __name__ == "__main__":
    main()
