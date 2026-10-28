"""Runs every step of the C++ comparison stage through run_with_load.py (machine load before / during / after each step),
with a 15 s pause between steps, like the baseline and prototypes stages. NOT SkellyCam code.

Prerequisites (once): build.bat (MSVC + OpenCV 4.8.0 SDK + pybind11 in .venv-bench), make_inputs.py, and the throw-away
venv with opencv-python 4.8.0.76 + numpy 1.26.4 at C:\\Users\\Dom\\AppData\\Local\\Temp\\skellycam_frame_pipeline_tmp\\venv_cv48
(see README.md, "How to run").

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam):
    .venv\\Scripts\\python.exe research\\frame_ring_buffer\\cpp\\run_all.py            # everything
    .venv\\Scripts\\python.exe research\\frame_ring_buffer\\cpp\\run_all.py micro ring  # only steps starting with these
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SK = HERE.parents[2]
PY_SK = str(SK / ".venv" / "Scripts" / "python.exe")
PY_B = str(HERE.parent / ".venv-bench" / "Scripts" / "python.exe")
PY_48 = r"C:\Users\Dom\AppData\Local\Temp\skellycam_frame_pipeline_tmp\venv_cv48\Scripts\python.exe"
C = "research\\frame_ring_buffer\\cpp\\"
B = str(HERE / "build")
import sys as _fp_sys; _fp_sys.path.insert(0, str(Path(__file__).resolve().parents[1])); from fp_paths import results_dir as _results_dir  # noqa: E402,E702
R = str(_results_dir(HERE))

STEPS = [
    ("env_snapshot_skellycamvenv", 300, [PY_SK, C + "env_snapshot.py", "skellycamvenv"]),
    ("env_snapshot_benchvenv", 300, [PY_B, C + "env_snapshot.py", "benchvenv"]),
    ("env_snapshot_cv48venv", 300, [PY_48, C + "env_snapshot.py", "cv48venv"]),
    ("largepages_probe", 120, [B + "\\ringbench.exe", "largepages"]),
    ("micro_cpp", 600, [B + "\\microbench.exe", R + "\\micro_cpp.json"]),
    ("micro_py", 900, [PY_SK, C + "py_micro.py", R + "\\micro_py.json"]),
    ("memcpy_cpp", 1800, [B + "\\memcpybench.exe", R + "\\memcpy_cpp.json"]),
    ("memcpy_py", 1800, [PY_SK, C + "py_memcpy.py", R + "\\memcpy_py.json"]),
    ("ring_write", 5400, [PY_SK, C + "run_matrix.py", "ring_write"]),
    ("ring_spsc", 7200, [PY_SK, C + "run_matrix.py", "ring_spsc"]),
    ("codec", 5400, [PY_SK, C + "run_matrix.py", "codec"]),
    ("pixel_cv2_py", 600, [PY_SK, C + "py_pixel_cv2.py", R + "\\pixel_cv2_py.json"]),
]


def main():
    want = sys.argv[1:]
    log = open(_results_dir(HERE) / "run_all_log.txt", "a", encoding="utf-8")
    first = True
    for name, timeout_s, cmd in STEPS:
        if want and not any(name.startswith(w) for w in want):
            continue
        if not first:
            time.sleep(15)
        first = False
        full = [PY_SK, C + "run_with_load.py", name, f"{name}_stdout.log", str(timeout_s), "--"] + cmd
        t0 = time.time()
        cp = subprocess.run(full, cwd=str(SK), capture_output=True, text=True, encoding="utf-8", errors="replace")
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {name} exit={cp.returncode} {time.time() - t0:.0f}s :: {cp.stdout.strip()[-600:]}"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()
    log.close()


if __name__ == "__main__":
    main()
