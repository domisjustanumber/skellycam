# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Chromium (Electron 35.7.5 / 45.2.3) on the Opus files: builds <scratch>/opus/electron_set/{clean,killed,repaired,gap,preskip0}
(copies: all clean files incl. WAV/FLAC references; per writer the first exit and first term kill with >= 4 s acked,
and the repaired copy of that term kill; all gap files), runs electron/main.cjs + page_opus.html in each Electron,
then analyses the returned audio in Python with opus_common:
  decodeAudioData : length, click offsets / correlation lag from sample 0 (gap files: clicks before / after the gap)
  <audio> play 0 / seek to 2 s : what the element renders (MediaElementSource capture): coarse lag profile of 100 ms
                    windows (the capture path steps by 128 samples in the first second, even for WAV)
  --analyse-only : re-analyse the raw page output in the scratchpad
Raw page output stays in the scratchpad.

Usage: uv run --script .../opus/electron_opus.py
Output: results/audio_single_file/opus/electron_opus_e35.json, electron_opus_e45.json
"""
import base64
import glob
import json
import os
import shutil
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import opus_common as O  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, *[".."] * 6))
ELECTRON = {
    "e35": os.path.join(REPO, "skellycam-ui", "node_modules", "electron", "dist", "electron.exe"),
    "e45": r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\106dc0c8-f977-4082-9d8d-367e9a9f721d\scratchpad\shared\electron-latest\node_modules\electron\dist\electron.exe",
}
MEDIA = (".opus", ".mka", ".webm", ".m4a", ".wav", ".flac")


def build_set():
    base = os.path.join(O.SCRATCH, "electron_set")
    shutil.rmtree(base, ignore_errors=True)
    for sub in ("clean", "killed", "repaired", "gap", "preskip0"):
        os.makedirs(os.path.join(base, sub))
    for p in glob.glob(os.path.join(O.SCRATCH, "clean", "*")) + glob.glob(os.path.join(O.SCRATCH, "gap", "*")) + glob.glob(os.path.join(O.SCRATCH, "preskip0", "*")):
        if p.endswith(MEDIA):
            shutil.copy(p, os.path.join(base, os.path.basename(os.path.dirname(p)), os.path.basename(p)))
    km = json.load(open(os.path.join(O.RESULTS, "kill_opus.json")))["kills"]
    picked = {}
    for k in km:
        key = (k["format"], k["method"])
        if key not in picked and k["acked_samples"] >= 4 * O.RATE:
            picked[key] = k
            shutil.copy(os.path.join(O.SCRATCH, "killed", k["file"]), os.path.join(base, "killed", k["file"]))
            rp = os.path.join(O.SCRATCH, "repaired", k["file"])
            if k["method"] == "term" and os.path.exists(rp):
                shutil.copy(rp, os.path.join(base, "repaired", k["file"]))
    return base, {v["file"]: v["acked_samples"] for v in picked.values()}


def arr(b):
    return np.frombuffer(base64.b64decode(b), np.int16).astype(np.float64) / 32768


def analyse(f, acked):
    out = {k: v for k, v in f.items() if k not in ("decodeAudioData", "capturePlay0", "captureSeek")}
    n_src = 12 * O.RATE
    src = O.src_f(n_src)
    d = f.get("decodeAudioData", {})
    if "data" in d:
        x = arr(d["data"])
        t = O.timing(x, n_src)
        if f["dir"] == "gap":
            offs = O.click_offsets(x)
            t.update(pre=sorted(set(offs[:5])), post=sorted(set(offs[5:])))
        out["decodeAudioData"] = dict(length=d["length"], **t)
        if acked:
            out["decodeAudioData"]["lost_vs_acked"] = acked - d["length"]
    else:
        out["decodeAudioData"] = d
    # <audio> -> MediaElementSource capture: the content lag steps by 128 samples during the first second, even for
    # WAV (measured), so only a coarse lag profile is reported: lag of 100 ms windows vs the expected position
    # (>0 = content ahead of the element's position = audio early), first and last window.
    for key in ("capturePlay0", "captureSeek"):
        c = f.get(key, {})
        if "data" not in c:
            out[key] = c
            continue
        y = arr(c["data"])
        nz = np.flatnonzero(y)
        tgt = int(round(c["seekTo"] * O.RATE))
        prof = []
        if len(nz):
            for w0 in range(int(nz[0]), len(y) - 4800, 4800):
                d, pk = O.find_lag(y[w0:w0 + 4800], src, max(0, tgt - O.RATE), tgt + 2 * O.RATE)
                if d is not None and pk > 0.3:
                    prof.append(int(d - w0 - int(nz[0]) - tgt))
        out[key] = dict(seekTo=c["seekTo"], currentTimeAtPlay=c["currentTimeAtPlay"], samples=c["samples"],
                        first_nonzero=int(nz[0]) if len(nz) else None, lag_profile=prof,
                        lag_first=prof[0] if prof else None, lag_last=prof[-1] if prof else None)
    return out


def main():
    if "--analyse-only" in sys.argv:  # re-analyse the raw page output already in the scratchpad
        acked = {k["file"]: k["acked_samples"] for k in json.load(open(os.path.join(O.RESULTS, "kill_opus.json")))["kills"]}
        for tag in ELECTRON:
            report(tag, json.load(open(os.path.join(O.SCRATCH, f"electron_raw_{tag}.json"))), acked)
        return
    base, acked = build_set()
    dirs = ";".join(os.path.join(base, s) for s in ("clean", "killed", "repaired", "gap", "preskip0"))
    for tag, exe in ELECTRON.items():
        raw = os.path.join(O.SCRATCH, f"electron_raw_{tag}.json")
        env = dict(os.environ, AUDIO_DIRS=dirs, AUDIO_OUT=raw)
        env.pop("ELECTRON_RUN_AS_NODE", None)
        p = subprocess.run([exe, os.path.join(HERE, "electron", "main.cjs")], env=env, capture_output=True, text=True, timeout=1800)
        print(tag, p.returncode, p.stdout[-200:], p.stderr[-300:], flush=True)
        report(tag, json.load(open(raw)), acked)


def report(tag, j, acked):
    res = dict(electron=j["electron"], chrome=j["chrome"], caps=j["caps"],
               files=[analyse(f, acked.get(f["name"])) for f in j["files"]])
    json.dump(res, open(os.path.join(O.RESULTS, f"electron_opus_{tag}.json"), "w"), indent=1)
    for f in res["files"]:
        d, c0, cs = f["decodeAudioData"], f["capturePlay0"], f["captureSeek"]
        print(tag, f["dir"], f["name"], d.get("length"), d.get("click_offsets"), d.get("post"), "| el", f["audioElement"].get("duration"),
              f["audioElement"].get("seekedAt"), "| play0", c0.get("lag_first"), c0.get("lag_last"), c0.get("error"), "| seek", cs.get("lag_first"), cs.get("lag_last"), cs.get("error"))


if __name__ == "__main__":
    main()
