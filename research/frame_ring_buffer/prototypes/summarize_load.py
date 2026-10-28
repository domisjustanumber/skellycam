"""Builds results/load_summary.md from every results/load_*.json written by run_with_load.py (prototypes stage).

Run:  cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam && .venv\\Scripts\\python.exe research\\frame_ring_buffer\\baseline\\summarize_load.py
"""
import json
from pathlib import Path

import sys as _fp_sys; _fp_sys.path.insert(0, str(Path(__file__).resolve().parents[1])); from fp_paths import results_dir as _results_dir  # noqa: E402,E702
R = _results_dir(Path(__file__).resolve().parent)
ORDER = ["env_snapshot", "p1_write_skellycamvenv", "p1_write_benchvenv", "p2_seqlock_read", "p3_lossless_record", "p4_mjpeg_passthrough", "p5_nvenc", "p6_ui_skellycamvenv", "p6_ui_benchvenv", "p7_topology_skellycamvenv", "p7_topology_benchvenv"]


def key(p):
    n = p.stem[5:]
    return (ORDER.index(n) if n in ORDER else len(ORDER), n)


def top(w, k=3):
    return ", ".join(f"{t['name']} {t['cpu_pct_of_machine']:.1f}" for t in w["top_processes"][:k])


lines = ["# Machine load around each benchmark (prototypes stage)", "",
         "CPU % is of the whole machine (28 logical CPUs = 100%). 'before'/'after' = 3 s windows just before the command "
         "started and just after it exited. 'background' = summed CPU of every process outside the benchmark's process "
         "tree and the wrapper, sampled about once a second while it ran; 'sys - tree' = system CPU minus the tree and the "
         "wrapper (includes processes psutil cannot read, e.g. kernel I/O). Idle rule: background mean < 10 and p95 < 10, "
         "and system CPU < 10 before and after. Runs shorter than one sample have no 'during' numbers.", "",
         "| run | exit | elapsed s | before: system CPU % / memory % | before: top 3 processes (CPU %) | during: background mean / p95 / max | during: sys - tree mean | during: benchmark tree mean | after: system CPU % / memory % | after: top 3 processes | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
for p in sorted(R.glob("load_*.json"), key=key):
    d = json.loads(p.read_text())
    b, a, du = d["before"], d["after"], d["during"]
    if du["n_samples"]:
        dur = f"{du['background_mean']:.1f} / {du['background_p95']:.1f} / {du['background_max']:.1f}"
        smt = f"{du['background_sys_minus_tree_mean']:.1f}"
        tr = f"{du['tree_mean']:.1f}"
        verdict = d["verdict"]
    else:
        dur, smt, tr = "(no sample)", "-", "-"
        verdict = "idle before/after (too short to sample)" if b["system_cpu_pct"] < 10 and a["system_cpu_pct"] < 10 else "provisional"
    lines.append(f"| {d['name']} | {d['exit_code']} | {d['elapsed_s']} | {b['system_cpu_pct']:.1f} / {b['memory_pct']:.1f} | {top(b)} | "
                 f"{dur} | {smt} | {tr} | {a['system_cpu_pct']:.1f} / {a['memory_pct']:.1f} | {top(a)} | {verdict} |")
(R / "load_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
