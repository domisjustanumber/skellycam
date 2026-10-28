"""Builds results/e_e2e_summary.md from every results/e_e2e_*.json written by bench_e_e2e.py.

Run:  cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam && .venv\\Scripts\\python.exe research\\frame_ring_buffer\\baseline\\summarize_e2e.py
"""
import json
from pathlib import Path

import sys as _fp_sys; _fp_sys.path.insert(0, str(Path(__file__).resolve().parents[1])); from fp_paths import results_dir as _results_dir  # noqa: E402,E702
R = _results_dir(Path(__file__).resolve().parent)


def mx(pc, k, s):
    return max(c[k][s] for c in pc.values())


def med(pc, k, s):
    v = sorted(c[k][s] for c in pc.values())
    return v[len(v) // 2]


lines = ["# (e) end-to-end: real SkellyCam CameraGroup stack, 5 synthetic 60 fps cameras, 30 s recording", "",
         "Per-camera values: median across the 5 cameras of each camera's median, or worst camera for p99/max.", "",
         "| file | size | retrieve stand-in | UI relay | achieved fps (min cam) | recorded frames / sensor frames (cam0) | sensor frames never grabbed (sum 5 cams) | frames in files == recorded | grab interval median / p99 / max ms | retrieve median ms | put_frame median / p99 ms | record_frame median / p99 ms | sensor tick -> written median / p99 / max ms | cross-cam grab spread p99 ms | UI payloads/s | UI build median / p99 ms | CPU% children / main / system | system CPU% before run |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
import sys  # noqa: E402
# REVISION stage (2026-10-28): optional argv[1] = glob, argv[2] = output .md name, so repeat / variant runs can be
# summarized without merging them into e_e2e_summary.md. Default unchanged (every e_e2e_*.json, incl. any repeats).
GLOB = sys.argv[1] if len(sys.argv) > 1 else "e_e2e_*.json"
OUT = sys.argv[2] if len(sys.argv) > 2 else "e_e2e_summary.md"
for f in sorted(R.glob(GLOB)):
    d = json.loads(f.read_text())
    pc = d["per_camera"]
    c0 = pc["0"]
    u = d["ui_summary"] or {}
    files_ok = all(x["decoded_frames"] == pc[str(i)]["recorded_frames"] for i, x in enumerate(d["files"]))
    cpu = d["cpu_pct_mean_during_recording"]
    lines.append(
        f"| {f.name} | {d['size']} | {d['retrieve_mode']} | {d['ui']} | {min(c['achieved_fps'] for c in pc.values()):.2f} | "
        f"{c0['recorded_frames']} / {c0['sensor_frames_during_recording']} | {sum(c['sensor_frames_never_grabbed'] for c in pc.values())} | {files_ok} | "
        f"{med(pc, 'grab_interval', 'median_ms'):.2f} / {mx(pc, 'grab_interval', 'p99_ms'):.2f} / {mx(pc, 'grab_interval', 'max_ms'):.1f} | "
        f"{med(pc, 'retrieve', 'median_ms'):.2f} | {med(pc, 'put_frame', 'median_ms'):.2f} / {mx(pc, 'put_frame', 'p99_ms'):.2f} | "
        f"{med(pc, 'record_frame_write', 'median_ms'):.2f} / {mx(pc, 'record_frame_write', 'p99_ms'):.2f} | "
        f"{med(pc, 'sensor_tick_to_written', 'median_ms'):.1f} / {mx(pc, 'sensor_tick_to_written', 'p99_ms'):.1f} / {mx(pc, 'sensor_tick_to_written', 'max_ms'):.1f} | "
        f"{d['cross_camera_grab_spread']['p99_ms']:.2f} | {u.get('payload_fps', 0):.1f} | "
        f"{u.get('build', {}).get('median_ms', 0):.1f} / {u.get('build', {}).get('p99_ms', 0):.1f} | "
        f"{cpu['sum_child_processes']:.0f} / {cpu['main']:.0f} / {cpu['system']:.0f} | {d['env']['system_cpu_pct_1s_before_run']:.0f} |")
lines += ["", "stop_recording/start_recording call durations, finalizer stats, per-camera CPU and capture logs are in each JSON."]
(R / OUT).write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
