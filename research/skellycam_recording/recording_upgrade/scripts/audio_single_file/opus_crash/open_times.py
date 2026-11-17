# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Sequential open/seek cost of the 30-32 min files (fragment count): ffprobe wall time, PyAV open, PyAV seek to
25 min + decode 1 s, 3 runs each (median reported with all runs). Killed files and their repairs.
Usage: uv run --script .../opus_crash/open_times.py      Output: results/audio_single_file/opus_crash/open_times.json
"""
import json
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crash_common as K  # noqa: E402

SETS = os.path.join(K.SCRATCH, "sets")


def pyav_open_seek(path):
    import av
    t0 = time.perf_counter()
    with av.open(path) as c:
        st = c.streams.audio[0]
        t1 = time.perf_counter()
        c.seek(int(25 * 60 / st.time_base), stream=st)
        n = 0
        for fr in c.decode(st):
            n += fr.samples
            if n >= K.RATE:
                break
    return t1 - t0, time.perf_counter() - t1


def main():
    files = [os.path.join(SETS, "crash", f) for f in ("wav__long.wav", "fragpkt__long.m4a", "frag100__long.m4a", "mka__long.mka")]
    files += [os.path.join(SETS, "repaired", f) for f in ("fragpkt__long__mfra.m4a", "fragpkt__long__remux.m4a", "fragpkt__long__refrag.m4a",
                                                          "frag100__long__mfra.m4a", "mka__long__dur.mka", "mka__long__full.mka")]
    out = {}
    for p in files:
        runs = []
        for _ in range(3):
            t0 = time.perf_counter()
            subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True)
            fp = time.perf_counter() - t0
            o, s = pyav_open_seek(p)
            runs.append((round(fp, 3), round(o, 3), round(s, 3)))
        out[os.path.relpath(p, SETS)] = dict(bytes=os.path.getsize(p), runs_ffprobe_open_seek_s=runs,
                                             median=[round(statistics.median(r[i] for r in runs), 3) for i in range(3)])
        print(os.path.relpath(p, SETS), out[os.path.relpath(p, SETS)]["median"], flush=True)
    json.dump(out, open(os.path.join(K.RESULTS, "open_times.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
