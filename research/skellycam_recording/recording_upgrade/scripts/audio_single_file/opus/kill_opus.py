# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Hard-kill matrix for live-written Opus (libopus via PyAV) in standard containers + one CSV timing sidecar each.
Same method as ../kill_matrix.py: a child writes real-time-paced 1024-sample stereo blocks (timing signal of
opus_common), after each write one CRC'd CSV row (flushed), then publishes acked samples/rows and its own PID.
  exit : os._exit(1) after a random block;  term : TerminateProcess on the child's own PID at a random time.
Kill times 0.5-8 s, seed 20261115. Also one cleanly closed 10.005 s file per writer, plus WAV and native FLAC
references of the same signal (asf_common writers) for the player checks.

Usage (repo root): uv run --script .../opus/kill_opus.py [kills_per_method] [writers]
Output: results/audio_single_file/opus/kill_opus.json; media in <scratch>/opus/{killed,clean}.
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
import opus_common as O  # noqa: E402

C = O.C
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kill_matrix import terminate  # noqa: E402

SEED = 20261115
KILL_WRITERS = ["ogg_pd20", "mka_ct1", "webm_ct1", "mp4_fragpkt", "mp4_frag100", "mp4_plain"]
REFS = ["wav_pyav", "flac_pyav"]


def child(name, path, csv_path, acked, rows, pid, exit_after, clean_blocks):
    pid.value = os.getpid()
    w = C.open_writer(name, path)
    cf = open(csv_path, "w", newline="\n")
    opus = name in O.WRITERS
    extra = {"writer": name}
    if opus:
        extra.update(pre_skip=O.PRESKIP, opus_frame=960, bitrate=O.COPTS["b"], sample_index_origin_note="after pre_skip")
    cf.write(C.csv_header(str(uuid.uuid4()), "opus" if opus else C.PYAV[name][2], C.EXT[name][1:], extra))
    cf.flush()
    t0 = time.perf_counter_ns()
    k = n = 0
    while True:
        due = t0 + (k + 1) * O.BLOCK * 1_000_000_000 // O.RATE
        while (d := due - time.perf_counter_ns()) > 0:
            time.sleep(min(d / 1e9, 0.002))
        host = time.perf_counter_ns() - t0
        w.write(O.sig(n, O.BLOCK))
        cf.write(C.csv_row(k, n, O.BLOCK, host, -1, 0))
        cf.flush()
        n += O.BLOCK
        k += 1
        acked.value, rows.value = n, k
        if exit_after and k >= exit_after:
            os._exit(1)
        if clean_blocks and k >= clean_blocks:
            w.close()
            cf.write(f"# end rows={k} samples={n}\n")
            cf.close()
            return


def one(name, method, kill_s, idx, work):
    path = os.path.join(work, f"{name}__{method}__{idx:02d}{C.EXT[name]}")
    for p in (path, path + ".csv"):
        if os.path.exists(p):
            os.remove(p)
    acked, rows, pid = (mp.Value("q", 0, lock=False) for _ in range(3))
    exit_after = int(kill_s * O.RATE / O.BLOCK) if method == "exit" else 0
    p = mp.Process(target=child, args=(name, path, path + ".csv", acked, rows, pid, exit_after, 0))
    p.start()
    term_ok = None
    if method == "term":
        t_end = time.perf_counter() + kill_s
        while time.perf_counter() < t_end and p.is_alive():
            time.sleep(0.001)
        term_ok = terminate(pid.value)
    p.join(30)
    if p.is_alive():
        p.kill()
    return dict(file=os.path.basename(path), format=name, method=method, kill_s=round(kill_s, 3),
                acked_samples=acked.value, acked_rows=rows.value, exitcode=p.exitcode, term_ok=term_ok)


def clean(name, work):
    path = os.path.join(work, f"{name}__clean{C.EXT[name]}")
    acked, rows, pid = (mp.Value("q", 0, lock=False) for _ in range(3))
    p = mp.Process(target=child, args=(name, path, path + ".csv", acked, rows, pid, 0, 469))  # 10.005 s
    p.start(); p.join(60)
    return dict(file=os.path.basename(path), format=name, samples=acked.value, exitcode=p.exitcode)


def main():
    per = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    names = sys.argv[2].split(",") if len(sys.argv) > 2 else KILL_WRITERS
    work, cdir = os.path.join(O.SCRATCH, "killed"), os.path.join(O.SCRATCH, "clean")
    os.makedirs(work, exist_ok=True); os.makedirs(cdir, exist_ok=True)
    rng = random.Random(SEED)
    jobs = [(f, m, rng.uniform(0.5, 8.0), i) for f in names for m in ("exit", "term") for i in range(per)]
    t0 = time.time()
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda j: one(*j, work), jobs))
        cl = list(ex.map(lambda f: clean(f, cdir), names + REFS))
    out = dict(seed=SEED, python=sys.version.split()[0], av=C.av.__version__, codec_options=O.COPTS,
               writers={k: O.WRITERS[k] for k in names}, wall_s=round(time.time() - t0, 1), kills=res, clean=cl)
    os.makedirs(O.RESULTS, exist_ok=True)
    json.dump(out, open(os.path.join(O.RESULTS, "kill_opus.json"), "w"), indent=1)
    print("kills", len(res), "landed", sum(r["exitcode"] not in (0, None) for r in res), "wall", out["wall_s"])


if __name__ == "__main__":
    main()
