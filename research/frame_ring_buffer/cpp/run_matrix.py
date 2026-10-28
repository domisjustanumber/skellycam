"""Runs one matrix of head-to-head configurations (C++ and Python back to back, same config) and saves one JSON per run.

  .venv\\Scripts\\python.exe research\\frame_ring_buffer\\cpp\\run_matrix.py <ring_write|ring_spsc|codec> [name-prefix ...]

Every run is a separate OS process tree (ringbench.exe / codecbench.exe, or py_ring.py / py_codec.py with
multiprocessing spawn). Order: for each config the implementations run back to back, so slow drift of the machine
affects them alike; the 5-camera ring configs are repeated a second time in reverse implementation order (suffix _r2).
Outputs: results/<matrix>/<run name>.json and results/<matrix>/_log.txt. Videos written by the codec matrix go to the
scratch bench_tmp folder; their sizes are in the run JSON (procs[].file_bytes) and they are deleted after each run.
Run it through run_with_load.py (see run_all.py) to record machine load.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import sys as _fp_sys; _fp_sys.path.insert(0, str(Path(__file__).resolve().parents[1])); from fp_paths import results_dir as _results_dir  # noqa: E402,E702

HERE = Path(__file__).resolve().parent
SK = HERE.parents[2]
PY_SK = str(SK / ".venv" / "Scripts" / "python.exe")
PY_B = str(HERE.parent / ".venv-bench" / "Scripts" / "python.exe")
TMP_ROOT = Path(r"C:\Users\Dom\AppData\Local\Temp\skellycam_frame_pipeline_tmp")
PY_48 = str(TMP_ROOT / "venv_cv48" / "Scripts" / "python.exe")
BENCH_TMP = TMP_ROOT / "bench_tmp"
INPUTS = str(BENCH_TMP / "cpp_inputs")
OPENCV_BIN = r"C:\Users\Dom\Downloads\opencv\build\x64\vc16\bin"
BUILD = HERE / "build"
RB = str(BUILD / "ringbench.exe")
CB = str(BUILD / "codecbench.exe")
PYR = str(HERE / "py_ring.py")
PYC = str(HERE / "py_codec.py")
RUN_S = "10"


def ring_impl_cmd(mode, size, n, impl, paced=None):
    if impl.startswith("cpp_"):
        if mode == "write":
            return [RB, "write", size, str(n), "head_port" if impl == "cpp_head_port" else "one_copy", RUN_S]
        topo = "thread" if impl == "cpp_thread" else "proc"
        return [RB, "spsc", size, str(n), str(paced), RUN_S, topo]
    py = PY_B if impl.startswith("hybrid") else PY_SK
    if mode == "write":
        return [py, PYR, "write", size, str(n), impl, RUN_S]
    return [py, PYR, "spsc", size, str(n), impl, str(paced), RUN_S]


def matrix(name):
    runs = []  # (run name, cmd, out-arg-style)
    if name == "ring_write":
        impls = ["sk_head", "cpp_head_port", "py_seq", "hybrid", "hybrid_ctypes", "cpp_one_copy"]
        for size in ("1080p", "720p", "64x64"):
            for n in (1, 5):
                for impl in impls:
                    runs.append((f"write_{size}_n{n}_{impl}", ring_impl_cmd("write", size, n, impl)))
        for size in ("1080p", "720p"):
            for impl in reversed(impls):
                runs.append((f"write_{size}_n5_{impl}_r2", ring_impl_cmd("write", size, 5, impl)))
    elif name == "ring_spsc":
        impls = ["sk_head", "py_seq", "hybrid", "cpp_proc", "cpp_thread"]
        for size in ("1080p", "720p"):
            for impl in impls:
                runs.append((f"spsc_{size}_n5_paced60_{impl}", ring_impl_cmd("spsc", size, 5, impl, 60)))
        for size in ("1080p", "720p", "64x64"):
            for n in (1, 5):
                for impl in impls:
                    runs.append((f"spsc_{size}_n{n}_max_{impl}", ring_impl_cmd("spsc", size, n, impl, 0)))
        for size in ("1080p", "720p"):
            for impl in reversed(impls):
                runs.append((f"spsc_{size}_n5_max_{impl}_r2", ring_impl_cmd("spsc", size, 5, impl, 0)))
    elif name == "codec":
        for size in ("1080p", "720p"):
            for n in (1, 5):
                runs.append((f"decode_{size}_n{n}_cpp48_copy", [CB, "decode", size, str(n), RUN_S, INPUTS, "0"]))
                runs.append((f"decode_{size}_n{n}_cpp48_inplace", [CB, "decode", size, str(n), RUN_S, INPUTS, "1"]))
                runs.append((f"decode_{size}_n{n}_py48", [PY_48, PYC, "decode", size, str(n), RUN_S, INPUTS]))
                runs.append((f"decode_{size}_n{n}_py412", [PY_SK, PYC, "decode", size, str(n), RUN_S, INPUTS]))
        for size in ("1080p", "720p"):
            runs.append((f"imencode_{size}_cpp48", [CB, "imencode", size, RUN_S, INPUTS]))
            runs.append((f"imencode_{size}_py48", [PY_48, PYC, "imencode", size, RUN_S, INPUTS]))
            runs.append((f"imencode_{size}_py412", [PY_SK, PYC, "imencode", size, RUN_S, INPUTS]))
        vw = [("1080p", 5, 60, 600, -1), ("1080p", 5, 60, 600, 1), ("720p", 5, 60, 600, -1),
              ("1080p", 1, 0, 600, -1), ("720p", 1, 0, 600, -1)]
        for size, n, paced, nfr, th in vw:
            tag = f"vw_{size}_n{n}_{'paced60' if paced else 'max'}_th{'default' if th < 0 else th}"
            runs.append((tag + "_cpp48", [CB, "videowriter", size, str(n), str(paced), str(nfr), str(th), INPUTS, str(BENCH_TMP)]))
            runs.append((tag + "_py48", [PY_48, PYC, "videowriter", size, str(n), str(paced), str(nfr), str(th), INPUTS, str(BENCH_TMP)]))
            runs.append((tag + "_py412", [PY_SK, PYC, "videowriter", size, str(n), str(paced), str(nfr), str(th), INPUTS, str(BENCH_TMP)]))
    return runs


def main():
    name = sys.argv[1]
    prefixes = sys.argv[2:]
    outdir = _results_dir(HERE) / name
    outdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env["PATH"] = OPENCV_BIN + os.pathsep + env.get("PATH", "")
    log = open(outdir / "_log.txt", "a", encoding="utf-8")
    for run_name, cmd in matrix(name):
        if prefixes and not any(run_name.startswith(p) for p in prefixes):
            continue
        out = outdir / f"{run_name}.json"
        t0 = time.time()
        try:
            cp = subprocess.run(cmd + [str(out)], cwd=str(SK), env=env, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=900)
            rc, tail = cp.returncode, (cp.stderr or "")[-1500:]
        except subprocess.TimeoutExpired:
            rc, tail = "timeout", ""
        dt = time.time() - t0
        ok = out.exists()
        line = f"{time.strftime('%H:%M:%S')} {run_name} rc={rc} {dt:.1f}s json={'ok' if ok else 'MISSING'} cmd={' '.join(cmd)}"
        print(line, flush=True)
        log.write(line + "\n")
        if not ok or rc not in (0,):
            log.write("  stderr tail: " + tail.replace("\n", " | ") + "\n")
        log.flush()
        # delete videos written by this run (their sizes are in the JSON)
        for f in glob.glob(str(BENCH_TMP / "*_vw_*.mp4")):
            try:
                os.remove(f)
            except OSError as e:
                log.write(f"  could not delete {f}: {e}\n")
        time.sleep(3)
    log.close()


if __name__ == "__main__":
    main()
