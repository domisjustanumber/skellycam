# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1", "python-vlc==3.0.21203"]
# ///
"""VLC seek-bar seek (libvlc set_time while playing), as ../libvlc_seek.py, on the Opus files: afile output,
play 0.6 s, set_time(T), play 1.0 s, stop. The landing (source index of the first output sample after the jump)
comes from opus_common.seek_landing; error = landing - T*48000. T = 5.0 s (clean, preskip0), 50 % (killed/repaired term 00-02).
Also a start-offset check of the same libvlc run (content before the seek).

Usage: uv run --script .../opus/libvlc_seek_opus.py   Output: results/audio_single_file/opus/libvlc_seek_opus.json
"""
import glob
import json
import os
import sys
import time

import vlc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import opus_common as O  # noqa: E402

C = O.C


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
    if x is None or len(x) < 4800:
        return dict(res, samples=0 if x is None else len(x))
    os.remove(out)
    tgt = int(round(t_s * O.RATE))
    src = O.src_f(tgt + 12 * O.RATE)
    return dict(res, samples=int(len(x)), **O.seek_landing(x, src, tgt))


def main():
    km = {k["file"]: k for k in json.load(open(os.path.join(O.RESULTS, "kill_opus.json")))["kills"]}
    jobs = [(p, 5.0) for sub in ("clean", "preskip0") for p in sorted(glob.glob(os.path.join(O.SCRATCH, sub, "*.*"))) if not p.endswith(".csv")]
    for sub in ("killed", "repaired"):
        for p in sorted(glob.glob(os.path.join(O.SCRATCH, sub, "*__term__0[0-2].*"))):
            if not p.endswith(".csv"):
                jobs.append((p, round(km[os.path.basename(p)]["acked_samples"] / O.RATE / 2, 3)))
    tmp = os.path.join(O.SCRATCH, "vlc_out", "libvlc_seek.wav"); os.makedirs(os.path.dirname(tmp), exist_ok=True)
    res = dict(vlc=vlc.libvlc_get_version().decode(), files={})
    for p, t in jobs:
        r = seek_once(p, t, tmp)
        res["files"][os.path.relpath(p, O.SCRATCH)] = dict(target_s=t, **r)
        print(os.path.relpath(p, O.SCRATCH), t, {k: r.get(k) for k in ("length_ms", "landed", "error_samples", "silence_after_jump", "convergence_samples", "lag_pre")}, flush=True)
    json.dump(res, open(os.path.join(O.RESULTS, "libvlc_seek_opus.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
