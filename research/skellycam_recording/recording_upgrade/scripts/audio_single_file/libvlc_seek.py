# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1", "python-vlc==3.0.21203"]
# ///
"""A seek the way a VLC user does it (seek bar = libvlc set_time while playing), measured on the audio VLC outputs.
readers.py found that the CLI --start-time is ignored for WAV, so this checks the interactive path.

Per file: libvlc with the afile output, play 0.6 s, set_time(T), play 1.0 s more, stop. In the output, find the
jump in the index signal; error = first index after the jump - T * 48000 (in samples).
T = 5.0 s (clean, 10 s), 50 % of the file (killed / repaired), 23,500 s (the > 4 GiB WAVs).

Usage: uv run --script .../libvlc_seek.py    Output: results/audio_single_file/libvlc_seek.json
"""
import glob
import json
import os
import sys
import time

import numpy as np
import vlc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asf_common as C  # noqa: E402


def seek_once(path, t_s, out):
    if os.path.exists(out):
        os.remove(out)
    inst = vlc.Instance("--aout=afile", f"--audiofile-file={out}", "--audiofile-wav", "--audiofile-format=s16",
                        "--audiofile-channels=2", "--no-video", "--quiet")
    pl = inst.media_player_new(); pl.set_media(inst.media_new_path(os.path.normpath(path))); pl.play()
    t0 = time.time()
    while pl.get_state() != vlc.State.Playing and time.time() - t0 < 4:
        time.sleep(0.01)
    time.sleep(0.6)
    ok = pl.set_time(int(t_s * 1000))
    time.sleep(1.0)
    res = dict(set_time_rc=ok, length_ms=pl.get_length(), time_ms=pl.get_time())
    pl.stop(); pl.release(); inst.release()
    x = C.read_wav_out(out)
    if x is None or len(x) == 0:
        return dict(res, samples=0)
    os.remove(out)
    idx = x[:, 0].view(np.uint16).astype(np.int64)
    step = (np.diff(idx) % 65536)
    jumps = np.flatnonzero(step != 1)
    res["samples"] = int(len(x))
    # first jump that is not inside leading/trailing silence; locate what follows it
    for j in jumps:
        seg = x[j + 1:]
        nz = int((seg != 0).any(axis=1).argmax()) if len(seg) else 0
        loc = C.locate(seg[nz:nz + 24000], int(t_s * C.RATE))
        if loc["n0"] is not None and abs(loc["n0"] - int(t_s * C.RATE)) < 10 * C.RATE:
            return dict(res, jump_at_output_sample=int(j + 1), silence_after_jump=nz, landed=loc["n0"],
                        error_samples=loc["n0"] - int(round(t_s * C.RATE)), exact_after=loc["exact"])
    return dict(res, jumps=len(jumps), landed=None)


def main():
    km = {k["file"]: k for k in json.load(open(os.path.join(C.RESULTS, "kill_matrix.json")))["kills"]}
    jobs = [(p, 5.0) for p in sorted(glob.glob(os.path.join(C.SCRATCH, "clean", "*.*"))) if not p.endswith(".csv")]
    for sub in ("killed", "repaired"):
        for p in sorted(glob.glob(os.path.join(C.SCRATCH, sub, "*__term__0[0-2].*"))):
            if not p.endswith(".csv"):
                jobs.append((p, round(km[os.path.basename(p)]["acked_samples"] / C.RATE / 2, 3)))
    jobs += [(p, 23500.0) for p in sorted(glob.glob(os.path.join(C.SCRATCH, "big", "*.wav")))]
    tmp = os.path.join(C.SCRATCH, "vlc_out", "libvlc_seek.wav")
    res = dict(vlc=vlc.libvlc_get_version().decode(), files={})
    for p, t in jobs:
        r = seek_once(p, t, tmp)
        res["files"][os.path.relpath(p, C.SCRATCH)] = dict(target_s=t, **r)
        print(os.path.relpath(p, C.SCRATCH), t, r)
    json.dump(res, open(os.path.join(C.RESULTS, "libvlc_seek.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
