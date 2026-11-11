# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""GF02 Part B (functional, no timing): kill the GF02Writer child (4 containers x {real, index} PTS, recwriter sidecar)
at 6 points, alternating os._exit inside the child and TerminateProcess from the parent, then check the killed file
with PyAV 19.0.2 and ffprobe (inspection), run recwriter.recover(), and check the recovered file. cv2 counts/seeks are
done afterwards by gf02_cv2_reader.py in the skellycam .venv (read-only) on the job list this script writes.

Kill = TerminateProcess: os.kill(inner_pid, SIGTERM) on the interpreter PID the child prints (Windows maps a non-CTRL
signal to TerminateProcess), then Popen.kill() on the launcher (same as scripts/crash_resilience/run_kill_matrix.py:42-50).
A random 0-33 ms delay (seeded) after "M <kill_at>" spreads TerminateProcess over the frame period.

Run (repo root): uv run --script research/.../GF02/gf02_partB_kills.py
Writes results/crash_resilience/gapfill/GF02_partB_kills.json (+ reader job list in TEMP).
"""
from __future__ import annotations

import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gf02_common as G  # noqa: E402

KILLS = [(50, "exit"), (137, "term"), (300, "exit"), (451, "term"), (611, "exit"), (700, "term")]


def run_child(stem: Path, cont: str, mode: str, kill_at: int, method: str, rnd: random.Random) -> dict:
    cmd = [sys.executable, str(Path(__file__).parent / "gf02_child.py"), str(stem), cont, mode, str(kill_at), method]
    errf = open(G.TEMP / f"{stem.name}.stderr.txt", "w")
    pr = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf, text=True)
    inner, last_m, killed_by_parent, nokill, delay = None, 0, False, False, None
    try:
        for line in pr.stdout:
            line = line.strip()
            if line.startswith("PID "):
                inner = int(line.split()[1])
            elif line.startswith("M "):
                last_m = int(line.split()[1])
                if method == "term" and last_m >= kill_at and not killed_by_parent:
                    delay = rnd.uniform(0.0, 0.033)
                    time.sleep(delay)  # spreads the kill over the frame period; not a measurement
                    if inner:
                        try:
                            os.kill(inner, signal.SIGTERM)
                        except OSError:
                            pass
                    pr.kill()
                    killed_by_parent = True
            elif line == "NOKILL":
                nokill = True
    finally:
        pr.wait(timeout=120)
        errf.close()
    return {"exit_code": pr.returncode, "inner_pid": inner, "last_M_line": last_m, "killed_by_parent": killed_by_parent,
            "kill_delay_drawn_s": delay, "nokill": nokill}


def main() -> None:
    import av
    av.logging.set_level(av.logging.ERROR)
    base = G.MEDIA / "partB"
    if base.exists():
        shutil.rmtree(base)
    G.TEMP.mkdir(parents=True, exist_ok=True)
    frames = G.C.load_set("c930e_720p_flash")
    expected = [frames[i % len(frames)] for i in range(1100)]
    rnd = random.Random(20261110)
    res = {"env": G.ffmpeg_versions(), "kills": KILLS, "set": "c930e_720p_flash looped", "rows": []}
    jobs = []
    for ci, (cont, mode) in enumerate([(c, m) for c in G.CONTAINERS for m in ("real", "index")]):
        for kill_at, method in KILLS:
            if ci % 2 == 1:  # alternate so every kill point gets both methods across combinations
                method = "term" if method == "exit" else "exit"
            d = base / f"{cont}_{mode}" / f"k{kill_at}_{method}"
            d.mkdir(parents=True)
            stem = d / "rec"
            ch = run_child(stem, cont, mode, kill_at, method, rnd)
            man = json.loads((d / "rec.recording.json").read_text())
            video = d / man["video"]
            side = G.rw.read_sidecar(d / man["sidecar"])
            n_side = int(len(side.records))
            row = {"container": cont, "pts_mode": mode, "kill_at": kill_at, "method": method, **ch,
                   "manifest_state": man["state"], "time_base": man.get("time_base"),
                   "sidecar_records": n_side, "sidecar_torn_tail_bytes": side.torn_tail_bytes,
                   "sidecar_bad_crc_records": side.bad_crc_records,
                   "find_unfinished_lists_it": stem in G.rw.find_unfinished(d),
                   "killed_bytes": video.stat().st_size if video.exists() else None}
            pk = G.pyav_check(video, expected)
            row["killed_pyav"] = pk
            row["killed_ffprobe"] = G.ffprobe_count(video)
            exact = pk["exact_prefix"]
            row["acked"] = min(n_side, ch["last_M_line"]) if ch["last_M_line"] else n_side
            row["lost_vs_sidecar"] = n_side - exact
            row["lost_vs_M_line"] = ch["last_M_line"] - exact
            k = max(0, min(exact, n_side) // 2)
            row["seek_k"] = k
            if exact and n_side:
                row["killed_pyav_seek"] = G.pyav_seek_identity(video, k, int(side.records[k]["pts"]), expected[k])
            jobs.append({"path": str(video), "set": "c930e_720p_flash", "loop": max(exact, 1), "targets": [k],
                         "seq": False, "fmc": False, "tag": f"killed|{cont}|{mode}|{kill_at}|{method}"})
            try:
                rep = G.rw.recover(stem)
                row["recover"] = {kk: v for kk, v in rep.items() if kk != "stem"}
                if rep.get("recovered_file"):
                    rv = d / rep["recovered_file"]
                    row["recovered_bytes"] = rv.stat().st_size
                    rp = G.pyav_check(rv, expected)
                    row["recovered_pyav"] = rp
                    row["recovered_ffprobe"] = G.ffprobe_count(rv)
                    if rp["exact_prefix"]:
                        kr = min(k, rp["exact_prefix"] - 1)
                        row["recovered_pyav_seek"] = G.pyav_seek_identity(rv, kr, int(side.records[kr]["pts"]),
                                                                         expected[kr])
                    jobs.append({"path": str(rv), "set": "c930e_720p_flash", "loop": max(rp["packets"], 1),
                                 "targets": [k], "seq": False, "fmc": False,
                                 "tag": f"recovered|{cont}|{mode}|{kill_at}|{method}"})
            except Exception as e:  # noqa: BLE001
                row["recover_error"] = f"{type(e).__name__}: {e}"[:300]
            res["rows"].append(row)
            fne = pk.get("first_non_exact") or {}
            print(cont, mode, kill_at, method, "M", ch["last_M_line"], "side", n_side, "exact", exact,
                  "pk", pk["packets"], "torn", bool(fne), fne.get("packet_is_corrupt"), "ffp",
                  row["killed_ffprobe"].get("nb_read_packets"), "rec", (row.get("recover") or {}).get("matched_prefix"),
                  (row.get("recovered_pyav") or {}).get("exact_prefix"), row.get("recover_error", ""), flush=True)
            G.write_json(G.RES / "GF02_partB_kills.json", res)
    G.write_json(G.RES / "GF02_partB_kills.json", res)
    G.write_json(G.TEMP / "jobs_partB.json", jobs)


if __name__ == "__main__":
    main()
