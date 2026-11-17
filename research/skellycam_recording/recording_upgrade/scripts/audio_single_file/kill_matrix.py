# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Hard-kill matrix: live-written standard audio files + one CSV timing sidecar each.

A child writes paced real-time 1024-sample stereo blocks (48 kHz, synthetic index signal) to one audio file and,
after each block's write returns, one CRC'd CSV row (flushed). After each row it publishes the acknowledged
sample count and row count in shared memory, and its own PID (the uv venv python.exe is a launcher, so the parent
kills the PID the child reports, not Popen's).
  exit : the child calls os._exit(1) after a random block (0.5-8 s);
  term : the parent waits a random 0.5-8 s and calls TerminateProcess on the child's own PID (lands anywhere).
Also writes one cleanly closed 10 s file per format (with the CSV footer) into <scratch>/clean.

Usage (repo root):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/audio_single_file/kill_matrix.py [kills_per_method] [formats]
Output: results/audio_single_file/kill_matrix.json; media in the scratchpad (rebuildable).
"""
import ctypes
import json
import multiprocessing as mp
import os
import random
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asf_common as C  # noqa: E402

SEED = 20261115


def child(name, path, csv_path, acked, rows, pid, exit_after, clean_blocks):
    pid.value = os.getpid()
    w = C.open_writer(name, path)
    cf = open(csv_path, "w", newline="\n")
    codec = "flac" if "flac" in name else "pcm_s16le"
    cf.write(C.csv_header(str(uuid.uuid4()), codec, C.EXT[name][1:], {"writer": name}))
    cf.flush()
    t0 = time.perf_counter_ns()
    k = n = 0
    while True:
        due = t0 + (k + 1) * C.BLOCK * 1_000_000_000 // C.RATE
        while (d := due - time.perf_counter_ns()) > 0:
            time.sleep(min(d / 1e9, 0.002))
        host = time.perf_counter_ns() - t0
        w.write(C.sig(n, C.BLOCK))
        cf.write(C.csv_row(k, n, C.BLOCK, host, -1, 0))
        cf.flush()
        n += C.BLOCK
        k += 1
        acked.value, rows.value = n, k
        if exit_after and k >= exit_after:
            os._exit(1)
        if clean_blocks and k >= clean_blocks:
            w.close()
            cf.write(f"# end rows={k} samples={n}\n")
            cf.close()
            return


def terminate(pid):
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
    ok = bool(h) and bool(k32.TerminateProcess(h, 15))
    if h:
        k32.CloseHandle(h)
    return ok


def one(name, method, kill_s, idx, work):
    path = os.path.join(work, f"{name}__{method}__{idx:02d}{C.EXT[name]}")
    csv_path = path + ".csv"
    for p in (path, csv_path):
        if os.path.exists(p):
            os.remove(p)
    acked, rows, pid = mp.Value("q", 0, lock=False), mp.Value("q", 0, lock=False), mp.Value("q", 0, lock=False)
    exit_after = int(kill_s * C.RATE / C.BLOCK) if method == "exit" else 0
    p = mp.Process(target=child, args=(name, path, csv_path, acked, rows, pid, exit_after, 0))
    p.start()
    term_ok = None
    if method == "term":
        t_end = time.perf_counter() + kill_s
        while time.perf_counter() < t_end and p.is_alive():
            time.sleep(0.001)
        a_before = acked.value
        term_ok = terminate(pid.value)
    p.join(30)
    if p.is_alive():
        p.kill()
    return dict(file=os.path.basename(path), format=name, method=method, kill_s=round(kill_s, 3),
                acked_samples=acked.value, acked_rows=rows.value, exitcode=p.exitcode, term_ok=term_ok,
                acked_before_term=a_before if method == "term" else None, child_pid=pid.value)


def clean(name, work):
    path = os.path.join(work, f"{name}__clean{C.EXT[name]}")
    acked, rows, pid = mp.Value("q", 0, lock=False), mp.Value("q", 0, lock=False), mp.Value("q", 0, lock=False)
    blocks = 469  # 10.005 s; not a multiple of 4608 or of 1 s on purpose
    p = mp.Process(target=child, args=(name, path, path + ".csv", acked, rows, pid, 0, blocks))
    p.start(); p.join(60)
    return dict(file=os.path.basename(path), format=name, samples=acked.value, exitcode=p.exitcode)


def main():
    per = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    fmts = sys.argv[2].split(",") if len(sys.argv) > 2 else C.FORMATS
    work = os.path.join(C.SCRATCH, "killed"); cdir = os.path.join(C.SCRATCH, "clean")
    os.makedirs(work, exist_ok=True); os.makedirs(cdir, exist_ok=True)
    rng = random.Random(SEED)
    jobs = [(f, m, rng.uniform(0.5, 8.0), i) for f in fmts for m in ("exit", "term") for i in range(per)]
    t0 = time.time()
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda j: one(*j, work), jobs))
        cl = list(ex.map(lambda f: clean(f, cdir), fmts))
    out = dict(seed=SEED, python=sys.version.split()[0], av=C.av.__version__, wall_s=round(time.time() - t0, 1),
               kills=res, clean=cl)
    if per == 0:  # clean files only: keep the kills already recorded
        prev = json.load(open(os.path.join(C.RESULTS, "kill_matrix.json")))
        out = dict(prev, clean=cl)
    try:
        import soundfile
        out["soundfile"], out["libsndfile"] = soundfile.__version__, soundfile.__libsndfile_version__
    except Exception:  # noqa: BLE001
        pass
    os.makedirs(C.RESULTS, exist_ok=True)
    with open(os.path.join(C.RESULTS, "kill_matrix.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("kills", len(res), "landed", sum(r["exitcode"] not in (0, None) for r in res), "wall", out["wall_s"])


if __name__ == "__main__":
    main()
