# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""GF05 (2026-11-10): replace the 'GB' GPU-memory cells in results/intra_playback/BENCH.md
section 5 scrub tables with the raw `private_kb` peak read from each config JSON.
The old cells were private_kb / 1,048,576 labelled "GB"; Electron's kilobyte unit is
NOT VERIFIED (FINDINGS F22). Checks every old cell equals round(kb / 2**20, 1) before
replacing it. Reads JSON only; no test, no timing.

Usage: uv run --script gf05_bench_private_kb_edit.py <RU root> <evidence json out>
"""
import json
import os
import re
import sys

ru = sys.argv[1]
ev_out = sys.argv[2]
bench_md = os.path.join(ru, "results", "intra_playback", "BENCH.md")
B = os.path.join(ru, "results", "intra_playback", "bench")

FILES = {
    "H.264 NVENC intra (mp4)": "h264_nvenc_intra.mp4",
    "HEVC NVENC intra (mp4)": "hevc_nvenc_intra.mp4",
    "H.264 QSV intra (mp4)": "h264_qsv_intra.mp4",
    "HEVC QSV intra (mp4)": "hevc_qsv_intra.mp4",
    "JPEG concatenated (.mjpeg)": "jpeg_seq",
    "JPEG-in-MKV": "jpeg_in_mkv",
}
METHODS = {
    "`<video>` gated": "video-gated",
    "WebCodecs (wcflush)": "webcodecs",
    "Range + createImageBitmap": "jpeg-range-bitmap",
    "Range + ImageDecoder": "jpeg-range-imagedecoder",
}
OLD_HDR = "GPU proc private peak GB; GPU pids |"
NEW_HDR = ("GPU proc peak `private_kb` (raw; unit NOT VERIFIED, FINDINGS F22); GPU pids "
           "(corrected 2026-11-10, GF05: was private_kb / 1,048,576 labelled GB) |")

with open(bench_md, encoding="utf-8", newline="") as f:
    raw = f.read()
eol = "\r\n" if "\r\n" in raw else "\n"
lines = raw.split(eol)

electron = None
evidence = []
changed = 0
for i, line in enumerate(lines):
    if line.startswith("### E35:"):
        electron = "e35"
    elif line.startswith("### E45:"):
        electron = "e45"
    elif line.startswith("## 6."):
        electron = None
    if electron is None or not line.startswith("| "):
        continue
    if line.rstrip().endswith(OLD_HDR):
        lines[i] = line.replace(OLD_HDR, NEW_HDR)
        evidence.append({"line": i + 1, "kind": "header", "old": OLD_HDR, "new": NEW_HDR})
        changed += 1
        continue
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) != 11 or cells[0] not in FILES:
        continue
    fname = f"c1080p30_{FILES[cells[0]]}__{METHODS[cells[1]]}__n{cells[2]}.json"
    with open(os.path.join(B, electron, "bench_intra_scrub", fname), encoding="utf-8") as jf:
        d = json.load(jf)
    gpu = [s for s in d["metrics_samples"] if s.get("type") == "GPU"]
    kb = max(s["private_kb"] for s in gpu)
    pids = len({s["pid"] for s in gpu})
    last = cells[10]
    m = re.match(r"^([\d.]+); (\d+)(.*)$", last)
    assert m, (i + 1, last)
    old_gb, old_pids, rest = float(m.group(1)), int(m.group(2)), m.group(3)
    assert abs(old_gb - round(kb / 2**20, 1)) < 1e-9, (i + 1, old_gb, kb)
    assert old_pids == pids, (i + 1, old_pids, pids)
    new_last = f"{kb:,}; {pids}{rest}"
    cells[10] = new_last
    lines[i] = "| " + " | ".join(cells) + " |"
    evidence.append({"line": i + 1, "electron": electron, "json": fname, "old": last, "new": new_last,
                     "private_kb_peak": kb, "gpu_pids": pids})
    changed += 1

with open(bench_md, "w", encoding="utf-8", newline="") as f:
    f.write(eol.join(lines))
# Note: the GF05 run used an earlier version that wrote LF; BENCH.md was converted back
# to CRLF right after. Re-running this script on the edited file is a no-op (no "GB" cells left).
with open(ev_out, "w", encoding="utf-8") as f:
    json.dump({"bench_md": "results/intra_playback/BENCH.md", "changed": changed, "edits": evidence}, f, indent=1)
print("changed", changed)
