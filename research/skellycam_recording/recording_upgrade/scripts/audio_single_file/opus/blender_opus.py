# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Blender 5.2.3 headless on the Electron set (<scratch>/opus/electron_set: clean incl. WAV/FLAC references, killed,
repaired, gap, preskip0 when present): audaspace decode start offset (click offsets, correlation lag), audaspace seek
landing at T = 2 s (opus_common.seek_landing), VSE strip length vs the decoded length at the scene fps; gap files:
clicks before / after the gap. Run electron_opus.py first (it builds the set).

Usage: uv run --script .../opus/blender_opus.py     Output: results/audio_single_file/opus/blender_opus.json
"""
import glob, json, os, subprocess, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import opus_common as O  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"


def main():
    base = os.path.join(O.SCRATCH, "electron_set")
    files = sorted(p for p in glob.glob(os.path.join(base, "*", "*")) if p.endswith((".opus", ".mka", ".webm", ".m4a", ".wav", ".flac")))
    npy = os.path.join(O.SCRATCH, "blender_npy"); os.makedirs(npy, exist_ok=True)
    lst, out = os.path.join(O.SCRATCH, "blender_files.json"), os.path.join(O.SCRATCH, "blender_out.json")
    json.dump([[os.path.normpath(p), 2.0] for p in files], open(lst, "w"))
    p = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", os.path.join(HERE, "blender_inner_opus.py"), "--", lst, out, npy],
                       capture_output=True, text=True, timeout=1800)
    raw = json.load(open(out))
    n_src = 12 * O.RATE
    src = O.src_f(n_src)
    res = dict(blender=raw["blender"], fps=raw["fps"], rc=p.returncode, files={})
    for path, r in raw["files"].items():
        a = {k: v for k, v in r.items() if not k.endswith("_npy")}
        if "full_npy" in r:
            x = np.load(r["full_npy"]).astype(np.float64)
            a.update(O.timing(x, n_src))
            if os.path.basename(os.path.dirname(path)) == "gap":
                offs = O.click_offsets(x); a.update(pre=sorted(set(offs[:5])), post=sorted(set(offs[5:])))
            a["vse_expected_frames"] = round(len(x) / O.RATE * raw["fps"], 3)
            y = np.load(r["seek_npy"]).astype(np.float64)
            a["aud_seek"] = O.seek_landing(y, src, int(r["seek_s"] * O.RATE)) if len(y) > 4800 else dict(samples=int(len(y)))
            for k in ("full_npy", "seek_npy"):
                os.remove(r[k])
        res["files"][os.path.relpath(path, base)] = a
        print(os.path.relpath(path, base), a.get("aud_samples"), a.get("click_offsets"), a.get("post"), a.get("aud_seek", {}).get("error_samples"),
              a.get("vse_frame_final_duration"), a.get("vse_expected_frames"), a.get("aud_error"))
    json.dump(res, open(os.path.join(O.RESULTS, "blender_opus.json"), "w"), indent=1)
    print("blender rc", p.returncode, p.stderr[-300:])


if __name__ == "__main__":
    main()
