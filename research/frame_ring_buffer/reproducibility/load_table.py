r"""Tabulate machine load of every re-run step from rerun/*/results/load_*.json. NOT SkellyCam code.
Run from C:\Users\Dom\GitHub\freemocap\skellycam:  .venv\Scripts\python.exe research\frame_ring_buffer\reproducibility\load_table.py
Writes reproducibility/load_summary_rerun.md."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
L = ["# Machine load of every re-run step", "",
     "CPU % of the whole 28-thread machine. Before/after = 3 s windows; background = every process outside the benchmark tree, ~1 s samples "
     "(recorded by each stage's run_with_load.py). Idle rule: background mean and p95 < 10%, system CPU < 10% before and after.", "",
     "| step (load file) | verdict | elapsed s | before: system CPU % / memory % | before: top 3 | during: background mean / p95 / max % | after: system CPU % / memory % | after: top 3 | leftover children killed |",
     "|---|---|---|---|---|---|---|---|---|"]
for f in sorted(HERE.glob("rerun/*/results/load_*.json")):
    d = json.loads(f.read_text())
    if "env_snapshot" in f.name or ("cpp" in f.parts and "ring" not in f.name):
        continue
    b, a, du = d.get("before", {}), d.get("after", {}), d.get("during") or {}
    top = lambda w: ", ".join(f"{t['name']} {t['cpu_pct_of_machine']}" for t in w.get("top_processes", [])[:3])
    bg = f"{du.get('background_mean')} / {du.get('background_p95')} / {du.get('background_max')}" if isinstance(du, dict) and du.get("background_mean") is not None else "no sample (< 1 s)"
    L.append(f"| {f.relative_to(HERE).as_posix()} | {d.get('verdict')} | {d.get('elapsed_s')} | {b.get('system_cpu_pct')} / {b.get('memory_pct')} | {top(b)} | {bg} | "
             f"{a.get('system_cpu_pct')} / {a.get('memory_pct')} | {top(a)} | {d.get('killed_leftover_pids', [])} |")
(HERE / "load_summary_rerun.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
