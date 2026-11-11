"""Run sweep.py for every (path, input) in results/intra_compare/refine_plan.json (written by analyze.py).

Plain Python driver (no third-party imports); each sweep call runs in its own PEP 723 env via uv.
  python research/skellycam_recording/recording_upgrade/scripts/intra_compare/run_refine.py [--only=path1,path2] [--per-path]
Groups run in parallel by encoder family (CPU JPEG / NVIDIA / Intel / CPU H.264-HEVC) so one GPU is not shared by
several processes of this script.
"""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = HERE.parents[1] / "results/intra_compare/refine_plan.json"


def group(pid: str) -> str:
    if "nvenc" in pid or "nvjpeg" in pid:
        return "nvidia"
    if "qsv" in pid:
        return "intel"
    if pid.startswith("lib"):
        return "cpu_video"
    return "cpu_jpeg"


def run_jobs(jobs: list[tuple[str, str, list[int]]]) -> None:
    for pid, inp, vals in jobs:
        cmd = ["uv", "run", "--script", str(HERE / "sweep.py"), "--paths", pid, "--inputs", inp,
               "--values", ",".join(map(str, vals)), "--label", "refine"]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = [ln for ln in r.stdout.splitlines() if "{'ok'" in ln]
        print(pid, inp, vals, f"{len(lines)} points", "FAIL" if r.returncode else "", flush=True)
        for ln in lines:
            if "'ok': False" in ln:
                print("   ", ln[:200], flush=True)


def main() -> None:
    plan = json.loads(PLAN.read_text())
    only = [a.split("=", 1)[1].split(",") for a in sys.argv[1:] if a.startswith("--only=")]
    if only:
        plan = {k: v for k, v in plan.items() if k in only[0]}
    groups: dict[str, list] = {}
    for pid, per in plan.items():
        for inp, vals in per.items():
            groups.setdefault(pid if "--per-path" in sys.argv else group(pid), []).append((pid, inp, vals))
    with ThreadPoolExecutor(max_workers=len(groups) or 1) as ex:
        list(ex.map(run_jobs, groups.values()))


if __name__ == "__main__":
    sys.exit(main())
