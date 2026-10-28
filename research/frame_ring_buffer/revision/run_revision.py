"""Runs the benchmarks added by the 2026-10-28 REVISION stage (answers to the critics), one at a time, each through the
stage's run_with_load.py (machine load before / during / after, idle rule), with a 15 s pause between steps.
NOT SkellyCam code. New result files use new names, so no earlier result file is overwritten.

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam):
    .venv\\Scripts\\python.exe research\\frame_ring_buffer\\revision\\run_revision.py e2ev      # steps whose name starts with these
Log: revision/run_revision_log.txt (one line per step).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FP = HERE.parent
SK = FP.parents[1]
PY_SK = str(SK / ".venv" / "Scripts" / "python.exe")
PY_B = str(FP / ".venv-bench" / "Scripts" / "python.exe")
B = "research\\frame_ring_buffer\\baseline\\"
P = "research\\frame_ring_buffer\\prototypes\\"
STEPS = []  # (name, wrapper dir, timeout, cmd, env)


def e2ev(variant, size="1080p", mode="mjpeg", ui="ui", rep=""):
    name = f"e2ev_{variant.replace(',', '+')}_{size}_{mode}_{ui}{rep}"
    STEPS.append((name, B, 600, [PY_SK, B + "bench_e2e_variants.py", variant, size, mode, ui, "30"], {"BENCH_E2E_REP": rep}))


e2ev("head")
e2ev("nocopycopy")
e2ev("nocopycopy", rep="_rep2")
e2ev("cvthreads1")
e2ev("nocopycopy,cvthreads1")
e2ev("extracpu3")
e2ev("dshowlike")
e2ev("head", ui="noui", rep="_rep2")
e2ev("dshowlike", rep="_v2")  # re-run after the read() logging fix


def p8(size, dec, rec, env, tag):
    STEPS.append((f"p8v_{size}_{dec}_{rec}{tag}", P, 600, [PY_SK, P + "p8_e2e_proto.py", size, dec, rec, "30"], dict(env, P8_REP=tag, P8_PREFIX="p8v_e2e_")))


p8("1080p", "imdecode", "msmf", {"P8_LOCKSTEP": "1", "P8_META": "1"}, "_lockstep_meta")
p8("1080p", "imdecode", "msmf", {"P8_LOCKSTEP": "1", "P8_META": "1"}, "_lockstep_meta_rep2")
p8("1080p", "imdecode", "msmf", {"P8_LOCKSTEP": "1", "P8_META": "1", "P8_RECTHREAD": "1"}, "_lockstep_meta_recthread")
p8("1080p", "imdecode", "msmf", {"P8_LOCKSTEP": "1", "P8_META": "1", "P8_EXTRA_CPU_MS": "3"}, "_lockstep_meta_extracpu3")
p8("1080p", "imdecode", "msmf", {}, "_spread")  # unchanged P8 (no lockstep) re-run, now with the cross-camera spread recorded
STEPS.append(("p8v_summarize", P, 120, [PY_SK, P + "p8_e2e_proto.py", "--summarize"],
              {"P8_SUMMARY_GLOB": "p8v_e2e_*.json", "P8_SUMMARY_OUT": "p8v_e2e_summary.md"}))
STEPS.append(("p10v_msmf_threads1", P, 1800, [PY_SK, P + "p10_msmf_threads.py"], {"P10_PLAN": "revision", "P10_OUT": "p10v_msmf_threads"}))
STEPS.append(("p11_crash_container", P, 900, [PY_SK, P + "p11_crash_container.py"], {}))
STEPS.append(("p3v_asymmetric_stall", P, 1800, [PY_SK, P + "p3_lossless_record.py", "ASYM"], {}))
STEPS.append(("p12_disk_sustained", P, 3600, [PY_SK, P + "p12_disk_sustained.py"], {"P12_A_GIB": "64"}))
STEPS.append(("h_deflate", B, 600, [PY_SK, B + "bench_h_deflate.py"], {}))
STEPS.append(("p6v_ui_rep2", P, 1200, [PY_SK, P + "p6_ui_path.py"], {"P6_RUN_S": "10", "P6_OUT": "p6_ui_skellycamvenv_rev_rep2"}))
STEPS.append(("p6v_ui_rep3", P, 1200, [PY_SK, P + "p6_ui_path.py"], {"P6_RUN_S": "10", "P6_OUT": "p6_ui_skellycamvenv_rev_rep3"}))


def main():
    sel = sys.argv[1:]
    log = HERE / "run_revision_log.txt"
    first = True
    for name, wdir, timeout_s, cmd, env in STEPS:
        if sel and not any(name.startswith(s) for s in sel):
            continue
        if not first:
            time.sleep(15)
        first = False
        e = dict(os.environ, PYTHONIOENCODING="utf-8", **env)
        t0 = time.strftime("%Y-%m-%d %H:%M:%S")
        r = subprocess.run([PY_SK, wdir + "run_with_load.py", name, f"{name}_stdout.log", str(timeout_s), "--"] + cmd,
                           cwd=str(SK), env=e, capture_output=True, text=True)
        line = f"{t0} {name} env={env} -> {r.stdout.strip()[-600:]} {r.stderr.strip()[-300:]}"
        with open(log, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line, flush=True)


if __name__ == "__main__":
    main()
