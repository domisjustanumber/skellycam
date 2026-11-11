# /// script
# requires-python = ">=3.10"
# ///
"""Start several camera commands concurrently (with per-command start offsets and timeouts) and take USB topology
snapshots while they run. Used by W-MULTI (all cameras at once, staggered starts, predicted conflicting pairs) and
by W-CTRL-EFFECT (a DirectShow control side channel while pyav_ds streams).

    python multi_launch.py SPEC.json            # prints one JSON object

The runner wraps the WHOLE launcher in one camera lock (``ctx.camcmd([python, multi_launch.py, spec])``): if every
child took camlock itself they would serialize and never stream together.

SPEC:
    {"commands": [{"label": str, "argv": [...], "start_at_s": 0.0, "timeout_s": 30}],
     "snapshots_at_s": [2.5, ...],          # times after launch to read the topology (granted alts / open pipes)
     "descriptor_file": null | path,        # win_descriptors.py JSON, gives alt numbers in the snapshots
     "snapshot_dir": null | path}           # also save each full snapshot there

Each child runs through common.procutil.run (whole-tree kill on timeout). Times are perf_counter_ns (QPC based on
Windows: the same clock as wincam's and pyav_ds's ``qpc_ns``), so control-set windows line up with frame arrivals.
Snapshots use helpers/win_topology.collect(), which sends no request to any device (cached hub-driver state).
Stdlib only.
"""
from __future__ import annotations

import json
import shutil
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITE_DIR = HERE.parents[1]
for _p in (str(SUITE_DIR), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from common import procutil, results  # noqa: E402


def _resolve(argv: list[str]) -> list[str]:
    argv = [str(a) for a in argv]
    if argv and not Path(argv[0]).is_absolute():
        found = shutil.which(argv[0])
        if found:
            argv = [found] + argv[1:]
    return argv


def main(spec_path: str) -> int:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    cmds = spec.get("commands", [])
    snaps_at = sorted(float(x) for x in spec.get("snapshots_at_s", []) or [])
    desc_file = spec.get("descriptor_file")
    snap_dir = Path(spec["snapshot_dir"]) if spec.get("snapshot_dir") else None
    t0 = time.perf_counter_ns()
    out_cmds: list[dict] = [dict() for _ in cmds]
    snaps: list[dict] = []

    def run_one(i: int, c: dict) -> None:
        delay = float(c.get("start_at_s") or 0.0)
        target = t0 + int(delay * 1e9)
        while True:
            now = time.perf_counter_ns()
            if now >= target:
                break
            time.sleep(min(0.05, (target - now) / 1e9))
        ts = time.perf_counter_ns()
        r = procutil.run(_resolve(c["argv"]), timeout_s=float(c.get("timeout_s") or 60))
        te = time.perf_counter_ns()
        so = r.get("stdout") or ""
        out_cmds[i] = {"label": c.get("label", str(i)), "argv": r.get("argv"), "start_at_s": delay,
                       "t_start_ns": ts, "t_end_ns": te, "t_start_s": (ts - t0) / 1e9, "t_end_s": (te - t0) / 1e9,
                       "rc": r.get("rc"), "timed_out": r.get("timed_out"), "killed": r.get("killed"),
                       "elapsed_s": r.get("elapsed_s"), "spawn_error": r.get("spawn_error"),
                       "stdout": so if len(so) < 400_000 else so[-400_000:],
                       "stderr_tail": (r.get("stderr") or "")[-3000:]}

    def snapshotter() -> None:
        try:
            import win_topology as wt  # noqa: PLC0415
        except Exception as e:  # noqa: BLE001
            snaps.append({"error": f"win_topology import failed: {e!r}"})
            return
        for k, at in enumerate(snaps_at):
            target = t0 + int(at * 1e9)
            while time.perf_counter_ns() < target:
                time.sleep(0.02)
            ts = time.perf_counter_ns()
            rec: dict = {"at_s": at, "t_ns": ts}
            try:
                s = wt.collect(descriptor_file=desc_file)
                rec["collect_ms"] = (time.perf_counter_ns() - ts) / 1e6
                rec["observed"] = wt.observed_alts(s)
                rec["periodic_pipes"] = {d["id"]: d.get("periodic_pipes") for d in s.get("devices", [])
                                         if d.get("periodic_pipes")}
                if snap_dir is not None:
                    p = snap_dir / f"snapshot_{k}_{at:.1f}s.json"
                    results.write_json(p, s)
                    rec["file"] = str(p)
            except Exception as e:  # noqa: BLE001
                rec["error"] = repr(e)
            snaps.append(rec)

    threads = [threading.Thread(target=run_one, args=(i, c), daemon=True) for i, c in enumerate(cmds)]
    st = threading.Thread(target=snapshotter, daemon=True) if snaps_at else None
    for th in threads:
        th.start()
    if st:
        st.start()
    for th in threads:
        th.join()
    if st:
        st.join(timeout=30)
    doc = {"tool": "multi_launch", "t0_ns": t0, "utc_finished": results.utc_now_iso(), "commands": out_cmds,
           "snapshots": snaps}
    sys.stdout.write(json.dumps(doc, default=str) + "\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: multi_launch.py SPEC.json", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
