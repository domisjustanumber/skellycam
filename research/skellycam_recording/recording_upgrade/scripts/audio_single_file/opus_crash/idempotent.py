# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Is the fMP4 repair (truncate at the last complete moof+mdat, append mfra) idempotent? Re-run it on copies of its
own output (sets/repaired/*__mfra.m4a) and compare bytes.
Usage: uv run --script .../opus_crash/idempotent.py      Output: results/audio_single_file/opus_crash/idempotent.json
"""
import glob
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crash_common as K  # noqa: E402


def repair(path):
    b = open(path, "rb").read()
    end, frags = K.fmp4_complete_end(b)
    with open(path, "r+b") as f:
        f.truncate(end)
    with open(path, "ab") as f:
        f.write(K.mfra_bytes(frags))


out = {}
for src in sorted(glob.glob(os.path.join(K.SCRATCH, "sets", "repaired", "*__mfra.m4a"))):
    dst = os.path.join(K.SCRATCH, "idem.m4a")
    shutil.copy(src, dst)
    repair(dst)
    h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
    out[os.path.basename(src)] = h(src) == h(dst)
    os.remove(dst)
assert all(out.values()), out
json.dump(dict(files=len(out), identical=sum(out.values()), per_file=out), open(os.path.join(K.RESULTS, "idempotent.json"), "w"), indent=1)
print(len(out), "files, all identical")
