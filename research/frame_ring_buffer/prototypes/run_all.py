"""Runs every prototype benchmark in sequence through run_with_load.py (machine load before / during / after each step),
with a 15 s pause between steps, exactly as the 20261027 baseline re-run did. NOT SkellyCam code.

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam):
    .venv\\Scripts\\python.exe research\\frame_ring_buffer\\prototypes\\run_all.py            # everything
    .venv\\Scripts\\python.exe research\\frame_ring_buffer\\prototypes\\run_all.py p3 p8      # only steps whose name starts with these
Outputs: prototypes/results/* (each script's JSON + .md), results/load_<step>.json, results/<step>_stdout.log,
results/run_all_log.txt (one line per step).
"""
from __future__ import annotations

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
P = "research\\frame_ring_buffer\\prototypes\\"


def step(name, timeout_s, cmd, env=None):
    return (name, timeout_s, cmd, env or {})


STEPS = [
    step("env_snapshot_skellycamvenv", 300, [PY_SK, P + "env_snapshot.py"]),
    step("env_snapshot_benchvenv", 300, [PY_B, P + "env_snapshot.py"]),
    step("p1_write_skellycamvenv", 2400, [PY_SK, P + "p1_write_variants.py"], {"P1_RUN_S": "10"}),
    step("p1_write_benchvenv", 1200, [PY_B, P + "p1_write_variants.py"], {"P1_RUN_S": "10"}),
    step("p1_write_summarize", 120, [PY_SK, P + "p1_write_variants.py", "--summarize"]),
    step("p2_seqlock_read", 1800, [PY_SK, P + "p2_seqlock_read.py"], {"P2_RUN_A_S": "10", "P2_RUN_B_S": "2"}),
    step("p3_lossless_record", 2700, [PY_SK, P + "p3_lossless_record.py", "A", "B"]),
    step("p4_mjpeg_passthrough", 1800, [PY_SK, P + "p4_mjpeg_passthrough.py"], {"P4_RUN_S": "20"}),
    step("p5_nvenc", 2700, [PY_SK, P + "p5_nvenc.py"], {"P5_RUN_S": "20"}),
    step("p6_ui_skellycamvenv", 1200, [PY_SK, P + "p6_ui_path.py"], {"P6_RUN_S": "10"}),
    step("p6_ui_benchvenv", 600, [PY_B, P + "p6_ui_path.py"], {"P6_RUN_S": "10"}),
    step("p6_ui_summarize", 120, [PY_SK, P + "p6_ui_path.py", "--summarize"]),
    step("p7_topology_skellycamvenv", 1800, [PY_SK, P + "p7_topology.py"], {"P7_REPS": "5"}),
    step("p7_topology_benchvenv", 900, [PY_B, P + "p7_topology.py", "simplejpeg"], {"P7_REPS": "5"}),
]
P8 = [  # (size, decode, recorder, rep tag, venv)
    ("1080p", "imdecode", "msmf", "", PY_SK), ("1080p", "imdecode", "msmf", "_rep2", PY_SK),
    ("1080p", "memcpy", "msmf", "", PY_SK), ("720p", "imdecode", "msmf", "", PY_SK),
    ("1080p", "imdecode", "nvenc", "", PY_SK), ("720p", "imdecode", "nvenc", "", PY_SK),
    ("1080p", "imdecode", "passthrough", "", PY_SK),
    ("1080p", "imdecode_off", "passthrough", "", PY_SK), ("1080p", "imdecode_off", "passthrough", "_rep2", PY_SK),
    ("720p", "imdecode_off", "passthrough", "", PY_SK),
    ("1080p", "simplejpeg", "msmf", "", PY_B), ("1080p", "simplejpeg", "nvenc", "", PY_B),
]
for size, dec, rec, rep, py in P8:
    STEPS.append(step(f"p8_e2e_{size}_{dec}_{rec}{rep}", 600, [py, P + "p8_e2e_proto.py", size, dec, rec, "30"], {"P8_REP": rep}))
STEPS += [step("p8_e2e_summarize", 120, [PY_SK, P + "p8_e2e_proto.py", "--summarize"]),
          # added after P5 showed the cv2 thread-count effect on the MSMF recorder; then the real-camera bonus check
          step("p10_msmf_threads", 1800, [PY_SK, P + "p10_msmf_threads.py"]),
          step("p9_real_camera", 900, [PY_SK, P + "p9_real_camera.py"], {"P9_RUN_S": "10"}),
          step("p9b_pyav_dshow_probe", 600, [PY_SK, P + "p9b_pyav_dshow_probe.py"])]


def main():
    sel = sys.argv[1:]
    log = _results_dir(HERE) / "run_all_log.txt"
    log.parent.mkdir(exist_ok=True)
    first = True
    for name, timeout_s, cmd, env in STEPS:
        if sel and not any(name.startswith(s) for s in sel):
            continue
        if not first:
            time.sleep(15)
        first = False
        e = dict(os.environ, PYTHONIOENCODING="utf-8", **env)
        t0 = time.strftime("%Y-%m-%d %H:%M:%S")
        r = subprocess.run([PY_SK, P + "run_with_load.py", name, f"{name}_stdout.log", str(timeout_s), "--"] + cmd,
                           cwd=str(SK), env=e, capture_output=True, text=True)
        line = f"{t0} {name} env={env} -> {r.stdout.strip()[-600:]} {r.stderr.strip()[-300:]}"
        with open(log, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line, flush=True)
    subprocess.run([PY_SK, P + "summarize_load.py"], cwd=str(SK), capture_output=True)


if __name__ == "__main__":
    main()
