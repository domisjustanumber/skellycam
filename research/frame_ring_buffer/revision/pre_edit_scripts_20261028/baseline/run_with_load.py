"""Run one baseline benchmark command and record machine load before, during and after it.

Added for the 20261027 idle re-run. NOT SkellyCam code; it only launches the documented command.

Writes results/load_<name>.json and streams the command's stdout+stderr to results/<log>.

Load measures (psutil, 100% = the whole machine, i.e. all logical CPUs):
  * before / after: a 3 s window: system CPU %, memory %, top 10 processes by CPU.
  * during: every 1 s: system CPU %, CPU of the benchmark process tree (the command and all its descendants),
    CPU of this wrapper, and "background" CPU = sum over every other accessible process (System Idle excluded).
    `background_sys_minus_tree` = system - tree - wrapper is also stored (it includes processes psutil cannot read).
Idle rule (README, "20261027 idle re-run"): background mean < 10% AND background p95 < 10% during the run,
and system CPU < 10% in both the before and after windows. Otherwise the run is labelled provisional.

At the end every process of the benchmark tree that is still alive is killed (and listed in the JSON).

Run:  cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam
      .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\baseline\\run_with_load.py <name> <log file name> <timeout_s> -- <command...>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
NCPU = psutil.cpu_count(logical=True)
ME = os.getpid()


def _procs_snapshot(cache):
    """cpu_percent(None) for every process since the previous call; returns {pid: (name, pct_of_machine)}."""
    out = {}
    seen = set()
    for p in psutil.process_iter(["name"]):
        pid = p.pid
        seen.add(pid)
        if pid == 0:
            continue
        proc = cache.get(pid)
        if proc is None:
            cache[pid] = p
            try:
                p.cpu_percent(None)
            except Exception:
                pass
            continue
        try:
            out[pid] = (proc.info.get("name") if hasattr(proc, "info") else proc.name(), proc.cpu_percent(None) / NCPU)
        except Exception:
            pass
    for pid in list(cache):
        if pid not in seen:
            cache.pop(pid, None)
    return out


def window(seconds=3.0):
    cache = {}
    _procs_snapshot(cache)
    psutil.cpu_percent(None)
    time.sleep(seconds)
    sys_pct = psutil.cpu_percent(None)
    snap = _procs_snapshot(cache)
    top = sorted(((v[1], v[0], pid) for pid, v in snap.items() if pid != ME), reverse=True)[:10]
    vm = psutil.virtual_memory()
    return dict(time=time.strftime("%Y-%m-%d %H:%M:%S"), window_s=seconds, system_cpu_pct=sys_pct,
                memory_pct=vm.percent, memory_used_gb=round(vm.used / 1e9, 2),
                top_processes=[dict(name=n, pid=pid, cpu_pct_of_machine=round(c, 2)) for c, n, pid in top])


def tree_pids(root):
    try:
        return {root.pid} | {c.pid for c in root.children(recursive=True)}
    except Exception:
        return {root.pid}


def pct(a, q):
    a = sorted(a)
    if not a:
        return None
    k = min(len(a) - 1, max(0, int(round(q / 100 * (len(a) - 1)))))
    return a[k]


def main():
    sep = sys.argv.index("--")
    name, log_name, timeout_s = sys.argv[1], sys.argv[2], float(sys.argv[3])
    cmd = sys.argv[sep + 1:]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    before = window()
    t0 = time.time()
    log_path = RESULTS / log_name
    with open(log_path, "wb") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, cwd=str(HERE.parents[2]))
        root = psutil.Process(proc.pid)
        all_tree = {proc.pid: root}
        cache = {}
        _procs_snapshot(cache)
        psutil.cpu_percent(None)
        samples = []
        timed_out = False
        while proc.poll() is None:
            time.sleep(1.0)
            sys_pct = psutil.cpu_percent(None)
            snap = _procs_snapshot(cache)
            tp = tree_pids(root)
            for pid in tp:
                if pid not in all_tree:
                    try:
                        all_tree[pid] = psutil.Process(pid)
                    except Exception:
                        pass
            tree = sum(v[1] for pid, v in snap.items() if pid in tp or pid in all_tree)
            mine = snap.get(ME, (None, 0.0))[1]
            bg_items = [(v[1], v[0]) for pid, v in snap.items() if pid not in tp and pid not in all_tree and pid != ME]
            bg = sum(c for c, _ in bg_items)
            top_bg = sorted(bg_items, reverse=True)[:3]
            samples.append(dict(t=round(time.time() - t0, 1), system=sys_pct, tree=round(tree, 2), wrapper=round(mine, 2),
                                background=round(bg, 2), background_sys_minus_tree=round(sys_pct - tree - mine, 2),
                                top_background=[f"{n}:{c:.1f}" for c, n in top_bg]))
            if time.time() - t0 > timeout_s:
                timed_out = True
                break
        killed = []
        for pid, p in all_tree.items():
            try:
                if p.is_running():
                    p.kill()
                    killed.append(pid)
            except Exception:
                pass
        try:
            proc.wait(10)
        except Exception:
            pass
    elapsed = time.time() - t0
    after = window()
    bgs = [s["background"] for s in samples]
    smt = [s["background_sys_minus_tree"] for s in samples]
    summ = dict(n_samples=len(samples), background_mean=round(sum(bgs) / len(bgs), 2) if bgs else None,
                background_p95=pct(bgs, 95), background_max=max(bgs) if bgs else None,
                background_sys_minus_tree_mean=round(sum(smt) / len(smt), 2) if smt else None,
                system_mean=round(sum(s["system"] for s in samples) / len(samples), 2) if samples else None,
                tree_mean=round(sum(s["tree"] for s in samples) / len(samples), 2) if samples else None)
    idle = bool(bgs) and summ["background_mean"] < 10 and summ["background_p95"] < 10 \
        and before["system_cpu_pct"] < 10 and after["system_cpu_pct"] < 10
    out = dict(name=name, command=cmd, log=log_name, exit_code=proc.returncode, timed_out=timed_out,
               elapsed_s=round(elapsed, 1), ncpu=NCPU, before=before, after=after, during=summ,
               verdict="idle" if idle else "provisional", killed_leftover_pids=killed, samples=samples)
    (RESULTS / f"load_{name}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(dict(name=name, exit=proc.returncode, timed_out=timed_out, elapsed_s=out["elapsed_s"],
                          before_sys=before["system_cpu_pct"], after_sys=after["system_cpu_pct"], during=summ,
                          verdict=out["verdict"], killed=killed)))


if __name__ == "__main__":
    main()
