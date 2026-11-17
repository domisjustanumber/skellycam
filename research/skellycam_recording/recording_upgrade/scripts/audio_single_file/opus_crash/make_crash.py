# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Live-written, hard-killed mono files for the crashed-Opus seek/repair test (method of ../opus/kill_opus.py).
A child writes real-time-paced 1024-sample mono blocks (opus_common timing signal, left channel), after each write
one CRC'd CSV row (flushed), then publishes acked samples/rows; the parent kills it with TerminateProcess on its own
PID (../kill_matrix.terminate) at a set time.
  short : 3 kills per writer at 12-55 s (seed 20261116)
  long  : 1 kill per writer at 1800-1920 s (30-32 min)
  clean : one cleanly closed 20.011 s file per writer (to see what a clean close adds)
Writers: wav (rf64=auto), fragpkt (fMP4, fragment per packet), frag100 (fMP4, 100 ms fragments), mka (cluster 1 ms).

Usage (repo root): uv run --script .../opus_crash/make_crash.py [short|long|clean ...]
Output: results/audio_single_file/opus_crash/make_crash_<set>.json; media in <scratch>/opus_crash/<set>.
"""
import json
import multiprocessing as mp
import os
import random
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crash_common as K  # noqa: E402

C = K.C
sys.path.insert(0, os.path.join(K.HERE, ".."))
from kill_matrix import terminate  # noqa: E402

SEED = 20261116


def child(name, path, acked, rows, pid, clean_blocks):
    pid.value = os.getpid()
    w = K.MonoWriter(name, path)
    cf = open(path + ".csv", "w", newline="\n")
    extra = {"writer": name}
    if name != "wav":
        extra.update(pre_skip=K.PRESKIP, opus_frame=960, bitrate=K.COPTS["b"])
    cf.write(C.csv_header(str(uuid.uuid4()), "pcm_s16le" if name == "wav" else "opus", K.WRITERS[name][1][1:], extra).replace("# channels=2", "# channels=1"))
    cf.flush()
    t0 = time.perf_counter_ns()
    k = n = 0
    while True:
        due = t0 + (k + 1) * K.BLOCK * 1_000_000_000 // K.RATE
        while (d := due - time.perf_counter_ns()) > 0:
            time.sleep(min(d / 1e9, 0.002))
        host = time.perf_counter_ns() - t0
        w.write(K.sig1(n, K.BLOCK))
        cf.write(C.csv_row(k, n, K.BLOCK, host, -1, 0))
        cf.flush()
        n += K.BLOCK
        k += 1
        acked.value, rows.value = n, k
        if clean_blocks and k >= clean_blocks:
            w.close()
            cf.write(f"# end rows={k} samples={n}\n")
            cf.close()
            return


def one(name, kill_s, tag, work):
    path = os.path.join(work, f"{name}__{tag}{K.WRITERS[name][1]}")
    for p in (path, path + ".csv"):
        if os.path.exists(p):
            os.remove(p)
    acked, rows, pid = (mp.Value("q", 0, lock=False) for _ in range(3))
    clean = kill_s is None
    p = mp.Process(target=child, args=(name, path, acked, rows, pid, 938 if clean else 0))  # 938 blocks = 20.011 s
    p.start()
    term_ok = None
    if not clean:
        t_end = time.perf_counter() + kill_s
        while time.perf_counter() < t_end and p.is_alive():
            time.sleep(0.005)
        term_ok = terminate(pid.value)
    p.join(60)
    if p.is_alive():
        p.kill()
    return dict(file=os.path.basename(path), writer=name, kill_s=None if clean else round(kill_s, 3), acked_samples=acked.value,
                acked_rows=rows.value, exitcode=p.exitcode, term_ok=term_ok, bytes=os.path.getsize(path))


def main():
    rng = random.Random(SEED)
    plan = {"short": [(w, rng.uniform(12, 55), f"term{i}") for w in K.WRITERS for i in range(3)],
            "long": [(w, rng.uniform(1800, 1920), "long") for w in K.WRITERS],
            "clean": [(w, None, "clean") for w in K.WRITERS]}
    for s in sys.argv[1:] or ["short"]:
        work = os.path.join(K.SCRATCH, s)
        os.makedirs(work, exist_ok=True)
        t0 = time.time()
        with ThreadPoolExecutor(len(plan[s])) as ex:
            res = list(ex.map(lambda j: one(*j, work), plan[s]))
        os.makedirs(K.RESULTS, exist_ok=True)
        out = dict(seed=SEED, set=s, python=sys.version.split()[0], av=C.av.__version__, codec_options=K.COPTS, writers=K.WRITERS,
                   wall_s=round(time.time() - t0, 1), files=res)
        json.dump(out, open(os.path.join(K.RESULTS, f"make_crash_{s}.json"), "w"), indent=1)
        print(s, "files", len(res), "killed", sum(r["exitcode"] not in (0, None) for r in res), "wall", out["wall_s"], flush=True)


if __name__ == "__main__":
    main()
