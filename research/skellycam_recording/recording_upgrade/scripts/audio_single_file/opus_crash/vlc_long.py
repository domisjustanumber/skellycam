# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1", "python-vlc==3.0.21203"]
# ///
"""VLC seek bar on the 30-32 min files: how long a set_time far into the file takes, and where it lands.
Play 0.6 s, set_time(T), poll get_time() every 20 ms (up to 60 s) until it is within 2 s of T (latency), play 1.5 s
more, stop; landing from the afile output (crash_common.land). Killed files and their repairs (sets crash, repaired).
Usage: uv run --script .../opus_crash/vlc_long.py [seq]   Output: results/audio_single_file/opus_crash/vlc_long.json (vlc_long_seq.json)
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import vlc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crash_common as K  # noqa: E402

SETS = os.path.join(K.SCRATCH, "sets")
SR = K.RATE


def one(path, tgt, out):
    if os.path.exists(out):
        os.remove(out)
    inst = vlc.Instance("--aout=afile", f"--audiofile-file={out}", "--audiofile-wav", "--audiofile-format=s16",
                        "--audiofile-channels=1", "--no-video", "--quiet")
    pl = inst.media_player_new(); pl.set_media(inst.media_new_path(os.path.normpath(path)))
    t0 = time.time(); pl.play()
    while pl.get_state() != vlc.State.Playing and time.time() - t0 < 60:
        time.sleep(0.01)
    r = dict(open_s=round(time.time() - t0, 3), length_ms=pl.get_length())
    time.sleep(0.6)
    req = int(round(tgt / SR * 1000))
    t1 = time.time(); pl.set_time(req)
    lat = None
    while time.time() - t1 < 60:
        t = pl.get_time()
        if t is not None and abs(t - req) < 2000:
            lat = time.time() - t1
            break
        time.sleep(0.02)
    r.update(seek_latency_s=None if lat is None else round(lat, 3), time_ms_after=pl.get_time())
    time.sleep(1.5)
    r.update(time_ms_end=pl.get_time(), state=str(pl.get_state()))
    pl.stop(); pl.release(); inst.release()
    b = open(out, "rb").read() if os.path.exists(out) else b""
    i = b.find(b"data")
    y = np.frombuffer(b[i + 8:][: (len(b) - i - 8) // 2 * 2], np.int16) if i >= 0 else np.zeros(0, np.int16)
    if os.path.exists(out):
        os.remove(out)
    r["samples"] = int(len(y))
    r["request_minus_target"] = req * SR // 1000 - tgt
    if len(y) > 4800:
        q = K.land(y, tgt, tgt + 3 * SR)
        r.update({k: q.get(k) for k in ("landed", "error_samples", "silence_after_jump", "jump_at_output_sample", "nonzero_len")})
        if q.get("error_samples") is not None:
            r["error_corrected"] = q["error_samples"] - r["request_minus_target"]
    return r


def main():
    files = [os.path.join(SETS, "crash", f) for f in ("wav__long.wav", "fragpkt__long.m4a", "frag100__long.m4a", "mka__long.mka", "fragpkt__term0.m4a")]
    files += [os.path.join(SETS, "repaired", f) for f in ("fragpkt__long__mfra.m4a", "fragpkt__long__remux.m4a", "fragpkt__long__refrag.m4a",
                                                          "frag100__long__mfra.m4a", "mka__long__dur.mka", "mka__long__full.mka", "mka__long__remux.mka")]
    vdir = os.path.join(K.SCRATCH, "vlc_out"); os.makedirs(vdir, exist_ok=True)
    jobs = []
    for p in files:
        import av
        with av.open(p) as c:
            L = int(c.duration * SR / 1_000_000) if c.duration else 2_000_000
        for t in ([5 * 60 * SR + 1234, 15 * 60 * SR + 777, L - 20 * SR - 345] if L > 40 * SR else [20 * SR + 11, 40 * SR + 5]):
            jobs.append((p, t))
    seq = "seq" in sys.argv  # one at a time, one target per file (clean open times)
    if seq:
        jobs = [j for k, j in enumerate(jobs) if k == 0 or jobs[k - 1][0] != j[0]]
    with ThreadPoolExecutor(1 if seq else 3) as ex:
        res = list(ex.map(lambda j: dict(file=os.path.relpath(j[0], SETS), target=j[1], **one(j[0], j[1], os.path.join(vdir, f"long_{abs(hash(j))}.wav"))), jobs))
    for r in res:
        print(r["file"], r["target"], r.get("open_s"), r.get("seek_latency_s"), r.get("error_corrected"), r.get("samples"), r.get("state"), flush=True)
    json.dump(dict(vlc=vlc.libvlc_get_version().decode(), mode="sequential, first target" if seq else "3 in parallel", results=res),
              open(os.path.join(K.RESULTS, "vlc_long_seq.json" if seq else "vlc_long.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
