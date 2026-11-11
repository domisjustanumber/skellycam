# /// script
# requires-python = ">=3.12"
# dependencies = ["psutil==7.2.2"]
# ///
"""Idle baseline (write_throughput VERIFY_method section 5 request 1, as a script instead of a python -c one-liner):
CPU seconds used by MsMpEng / SearchIndexer / SearchProtocolHost / SearchFilterHost over --seconds of idle.
Appends one JSON line to results/write_throughput/bench/idle_baseline_av19.jsonl (or --out).
  uv run --script research/skellycam_recording/recording_upgrade/scripts/bench_runner/idle_baseline.py --tag before
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import psutil

STUDY = Path(__file__).resolve().parents[2]
NAMES = ("msmpeng.exe", "searchindexer.exe", "searchprotocolhost.exe", "searchfilterhost.exe")


def grab() -> dict:
    o: dict = {}
    for p in psutil.process_iter(["name"]):
        n = (p.info["name"] or "").lower()
        if n in NAMES:
            try:
                c = p.cpu_times()
                o[n] = o.get(n, 0.0) + c.user + c.system
            except Exception as ex:  # noqa: BLE001
                o[n + "_err"] = type(ex).__name__
    return o


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", default=str(STUDY / "results/write_throughput/bench/idle_baseline_av19.jsonl"))
    a = ap.parse_args()
    t = time.strftime("%Y-%m-%dT%H:%M:%S")
    x = grab()
    time.sleep(a.seconds)
    y = grab()
    rec = {"when": t, "tag": a.tag, "seconds": a.seconds,
           "idle_cpu_s": {k: (round(y[k] - x.get(k, 0.0), 3) if isinstance(y[k], float) else y[k]) for k in y}}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps(rec))


if __name__ == "__main__":
    main()
