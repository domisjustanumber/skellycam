"""Repair a killed native .flac cheaply: write the decoded sample count into STREAMINFO's 36-bit
total-samples field (RFC 9639 §8.2), in place, on a copy. Then check ffprobe duration and a seek.
Usage: python -I flac_patch.py <killed.flac> <out_json>
"""
import json, os, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ac_common import SCRATCH, decode_pyav, ffprobe, flac_streaminfo  # noqa: E402

src = sys.argv[1]
dst = os.path.join(SCRATCH, "repaired", "patched_" + os.path.basename(src))
os.makedirs(os.path.dirname(dst), exist_ok=True)
shutil.copyfile(src, dst)
t0 = time.perf_counter()
n = decode_pyav(dst)["samples"]                        # count by decoding (or by scanning frame headers)
t_count = time.perf_counter() - t0
with open(dst, "r+b") as f:
    b = bytearray(f.read(42))
    assert b[:4] == b"fLaC"
    si = 8  # STREAMINFO body starts after 'fLaC' + 4-byte block header
    b[si + 13] = (b[si + 13] & 0xF0) | ((n >> 32) & 0x0F)
    b[si + 14:si + 18] = (n & 0xFFFFFFFF).to_bytes(4, "big")
    f.seek(0); f.write(b[:42])
t_patch = time.perf_counter() - t0 - t_count
p = subprocess.run(["ffmpeg", "-v", "error", "-ss", "5", "-i", dst, "-t", "0.1", "-f", "null", "-"], capture_output=True)
res = dict(src=os.path.basename(src), decoded=n, count_s=round(t_count, 3), patch_s=round(t_patch, 4),
           before=flac_streaminfo(src), after=flac_streaminfo(dst), ffprobe_before=ffprobe(src)["duration"],
           ffprobe_after=ffprobe(dst)["duration"], seek5s_rc=p.returncode, seek5s_err=p.stderr.decode()[-200:],
           decoded_after=decode_pyav(dst)["samples"])
os.remove(dst)
json.dump(res, open(sys.argv[2], "w"), indent=1); print(res)
