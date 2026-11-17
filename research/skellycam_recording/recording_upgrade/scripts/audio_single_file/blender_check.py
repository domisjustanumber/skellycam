"""Blender 5.2.3 headless on the clean, killed (first exit and first term per format) and repaired files, plus
the gap-test and big-WAV files when present. Standard library only.

Usage: python -I blender_check.py      Output: results/audio_single_file/blender.json
"""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.path.normpath(os.environ.get(
    "ASF_SCRATCH",
    r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496\scratchpad\audio_single_file"))
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
RESULTS = os.path.join(HERE, "..", "..", "results", "audio_single_file")
AUDIO = (".wav", ".flac", ".mka")


def main():
    pats = ["clean/*", "killed/*__exit__00.*", "killed/*__term__00.*", "repaired/*__term__00.*", "gap/*"]
    files = sorted({os.path.normpath(p) for pat in pats for p in glob.glob(os.path.join(SCRATCH, pat)) if p.endswith(AUDIO)})
    jobs = [[p, 2.0] for p in files]
    jobs += [[p, 23500.0] for p in sorted(glob.glob(os.path.join(SCRATCH, "big", "*.wav")))]
    lst = os.path.join(SCRATCH, "blender_files.json")
    out = os.path.join(SCRATCH, "blender_out.json")
    json.dump(jobs, open(lst, "w"))
    p = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", os.path.join(HERE, "blender_inner.py"), "--", lst, out],
                       capture_output=True, text=True, timeout=1800)
    res = json.load(open(out))
    res["files"] = {os.path.relpath(k, SCRATCH): v for k, v in res["files"].items()}
    res["blender_rc"] = p.returncode
    json.dump(res, open(os.path.join(RESULTS, "blender.json"), "w"), indent=1)
    print(p.returncode, len(res["files"]), "files", p.stderr[-500:])


if __name__ == "__main__":
    main()
