# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Follow-up (Dom, 2026-11-16): Opus fMP4 written live with 1 s fragments. What does a hard kill lose?
Same child, pacing and TerminateProcess kill as make_crash.py; writer frag1s = empty_moov+default_base_moof,
frag_duration=1000000. 8 kills at 12-55 s (seed 20261117), plus 1 clean file.
Per file: acked, decoded (PyAV), lost, CSV lead, torn tail bytes (fMP4 walk), fragments.
Usage (repo root): uv run --script .../opus_crash/frag1s_kill.py
Output: results/audio_single_file/opus_crash/frag1s_kill.json; media in <scratch>/opus_crash/frag1s.
"""
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crash_common as K  # noqa: E402

# FRAG1S_STEREO=1 (env, so spawned children see it too): stereo 256 kbit/s, the opus_common stereo signal
STEREO = os.environ.get("FRAG1S_STEREO") == "1"
TAG = "frag1s_stereo" if STEREO else "frag1s"
COPTS = dict(K.COPTS, b="256000") if STEREO else K.COPTS
K.WRITERS["frag1s"] = ("mp4", ".m4a", "libopus", COPTS,
                       {"flush_packets": "1", "movflags": "empty_moov+default_base_moof", "frag_duration": "1000000"})
if STEREO:
    import fractions

    class StereoWriter(K.MonoWriter):
        def __init__(self, name, path):
            import av
            fmt, _, codec, copts, mopts = K.WRITERS[name]
            self.out = av.open(path, "w", format=fmt, options=dict(mopts))
            self.st = self.out.add_stream(codec, rate=K.RATE, layout="stereo")
            self.st.codec_context.options = dict(copts)
            self.st.time_base = fractions.Fraction(1, K.RATE)
            self.n = 0

        def write(self, block):  # block: (n, 2) int16
            import av
            fr = av.AudioFrame.from_ndarray(K.np.ascontiguousarray(block).reshape(1, -1), format="s16", layout="stereo")
            fr.sample_rate, fr.pts, fr.time_base = K.RATE, self.n, fractions.Fraction(1, K.RATE)
            self.n += len(block)
            for p in self.st.encode(fr):
                self.out.mux(p)

    K.MonoWriter = StereoWriter
    K.sig1 = lambda n0, n: K.O.sig(n0, n)
import make_crash as M  # noqa: E402
import seek_crash as S  # noqa: E402


def main():
    rng = random.Random(20261117)
    plan = [("frag1s", rng.uniform(12, 55), f"term{i}") for i in range(8)] + [("frag1s", None, "clean")]
    work = os.path.join(K.SCRATCH, TAG)
    os.makedirs(work, exist_ok=True)
    t0 = time.time()
    with ThreadPoolExecutor(len(plan)) as ex:
        res = list(ex.map(lambda j: M.one(*j, work), plan))
    for r in res:
        p = os.path.join(work, r["file"])
        info, _ = K.O.decode_all(p)
        b = open(p, "rb").read()
        bx = K.boxes(b)
        # torn = bytes after the last complete top-level box, with no zero-tail stripping
        complete_end = max((o + s for _, o, s, ok in bx if ok), default=0)
        cv = S.csv_cover(p + ".csv")
        r.update(decoded=info["samples"], lost=r["acked_samples"] - info["samples"],
                 lost_ms=round((r["acked_samples"] - info["samples"]) / K.RATE * 1000, 1),
                 csv_lead=cv["cover"] - info["samples"], csv_bad_rows=cv["bad_rows"], csv_torn=cv["torn_bytes"],
                 torn_tail_bytes=len(b) - complete_end, last_byte=b[-1],
                 # what crash_common.fmp4_complete_end (strips a zero tail first) would cut: a whole good fragment
                 # when the last mdat happens to end in 0x00
                 zero_strip_would_cut=len(b) - K.fmp4_complete_end(b)[0],
                 moofs=sum(1 for x in bx if x[0] == "moof"))
        print(r, flush=True)
    killed = [r for r in res if r["kill_s"] is not None]
    assert all(r["exitcode"] not in (0, None) for r in killed), "a kill did not land"
    out = dict(seed=20261117, stereo=STEREO, writer=K.WRITERS["frag1s"], av=K.C.av.__version__, wall_s=round(time.time() - t0, 1), files=res,
               lost_ms_range=[min(r["lost_ms"] for r in killed), max(r["lost_ms"] for r in killed)])
    json.dump(out, open(os.path.join(K.RESULTS, f"{TAG}_kill.json"), "w"), indent=1)
    print("lost ms range", out["lost_ms_range"])


if __name__ == "__main__":
    main()
