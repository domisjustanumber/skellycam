# /// script
# requires-python = ">=3.10"
# ///
"""Run a batch of simultaneous-open combinations through mf_multi_open.exe and, while each combination is
streaming, snapshot the hub's open pipes (=> the VideoStreaming alt setting usbvideo.sys selected).

Goal 3 (USB bandwidth) harness, Windows. Must be run under camlock (it opens cameras):

  uv run --script research/usb_cameras/tools/camlock.py -- \
      uv run --script research/usb_cameras/bandwidth/run_concurrency.py --batch NAME \
      --combo "label|vid_046d&pid_085c:MJPG:1280x720@30;vid_1532&pid_0e05:MJPG:1280x720@30" [--combo ...] \
      [--seconds 6] [--exposure -7] [--wb 4500] [--stagger-ms 0] [--budget-s 170] [--list]
      [--out-dir DIR] [--exclude VID:PID ...] [--save-dir DIR [--save-max N]] [--exe PATH]

Each combo is "label|spec;spec;..." with spec = <symlink-substring>:<MJPG|YUY2|NV12|H264>:<W>x<H>@<fps>.
--list first saves `mf_multi_open --list` (devices + native media types) to mf_list.json.
Output: results/windows/<hostname>/bw_concurrency/<batch>.json (one entry per combo), or --out-dir/<batch>.json.
--exclude is passed to win_usb_topology.py --pipes-only (no descriptor requests to that device).
--save-dir saves MJPG samples per combo as SAVE_DIR/<label>/cam<k>/frame_<n>.jpg (needs an mf_multi_open build with
--save-dir, 2026-10-27+). Machine CPU% (GetSystemTimes, 1 s sample) is recorded before and after the batch.
Combos that would start after --budget-s seconds are recorded as skipped (keeps the camera lock short).
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import platform
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXE = HERE / "build" / "mf_multi_open.exe"
spec = importlib.util.spec_from_file_location("win_usb_topology", HERE / "win_usb_topology.py")
topo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(topo)


def cpu_pct(sample_s: float = 1.0) -> float | None:
    """Whole-machine CPU busy % over sample_s (kernel32 GetSystemTimes; kernel time includes idle)."""
    try:
        import ctypes
        FT = ctypes.c_ulonglong
        def snap():
            i, k, u = FT(), FT(), FT()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
            return i.value, k.value, u.value
        i0, k0, u0 = snap(); time.sleep(sample_s); i1, k1, u1 = snap()
        tot = (k1 - k0) + (u1 - u0)
        return round(100.0 * (tot - (i1 - i0)) / tot, 1) if tot else None
    except Exception:
        return None


def run_combo(label: str, specs: list[str], seconds: float, exposure, wb, stagger_ms: float = 0,
              exe: Path = EXE, exclude: list[str] | None = None, save_dir: Path | None = None, save_max: int = 0) -> dict:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "r.json"
        cmd = [str(exe), "--seconds", str(seconds), "--out", str(out), "--stagger-ms", str(stagger_ms)]
        if exposure is not None:
            cmd += ["--exposure", str(exposure)]
        if wb is not None:
            cmd += ["--wb", str(wb)]
        if save_dir is not None:
            cmd += ["--save-dir", str(save_dir), "--save-max", str(save_max)]
        for s in specs:
            cmd += ["--cam", s]
        t0 = time.monotonic()
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        err_chunks: list[str] = []
        threading.Thread(target=lambda: err_chunks.append(p.stderr.read()), daemon=True).start()
        pipes = None
        pipes_t = None
        for line in p.stdout:
            if line.strip() == "STREAMING":
                time.sleep(1.0)  # let every stream settle into steady state
                pipes_t = time.monotonic() - t0
                # separate process: a ctypes fault while a device re-enumerates must not kill the batch
                snap = subprocess.run([sys.executable, str(HERE / "win_usb_topology.py"), "--pipes-only"]
                                      + [x for e in (exclude or []) for x in ("--exclude", e)],
                                      capture_output=True, text=True, timeout=60)
                try:
                    pipes = json.loads(snap.stdout)
                except ValueError:
                    pipes = {"error": f"pipes snapshot rc={snap.returncode}", "stderr": snap.stderr[-2000:]}
        rc = p.wait(timeout=seconds + 60)
        time.sleep(0.2)
        res = json.loads(out.read_text()) if out.exists() else {"error": "no result file", "stderr": "".join(err_chunks)[-2000:]}
    # idle snapshot after the stream stopped (should show only the interrupt pipe again)
    return {"label": label, "specs": specs, "command": cmd[:1] + [c for c in cmd[1:] if not c.endswith("r.json")],
            "exit_code": rc, "mf": res, "pipes_while_streaming_t_s": pipes_t, "pipes_while_streaming": pipes}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--combo", action="append", default=[])
    ap.add_argument("--seconds", type=float, default=6)
    ap.add_argument("--exposure", type=int)
    ap.add_argument("--wb", type=int)
    ap.add_argument("--budget-s", type=float, default=170)
    ap.add_argument("--stagger-ms", type=float, default=0, help="start camera k at k*stagger ms (deterministic start order)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--exclude", action="append", default=[], metavar="VID:PID")
    ap.add_argument("--save-dir", type=Path)
    ap.add_argument("--save-max", type=int, default=300)
    ap.add_argument("--exe", type=Path, default=EXE)
    a = ap.parse_args()
    host = socket.gethostname()
    outdir = a.out_dir or HERE.parent / "results" / "windows" / host / "bw_concurrency"
    outdir.mkdir(parents=True, exist_ok=True)
    t_start = time.monotonic()
    if a.list:
        lst = subprocess.run([str(a.exe), "--list"], capture_output=True, text=True, timeout=120)
        (outdir / "mf_list.json").write_text(lst.stdout)
        print(f"wrote {outdir / 'mf_list.json'}")
    doc = {"test": "bw_concurrency", "batch": a.batch, "platform": "windows", "hostname": host,
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(), "command": " ".join(sys.argv),
           "environment": {"os": platform.platform(), "python": platform.python_version(), "exe": str(a.exe)},
           "exclude": a.exclude, "save_dir": str(a.save_dir) if a.save_dir else None,
           "machine_cpu_pct_start": cpu_pct(),
           "settings": {"seconds": a.seconds, "exposure": a.exposure, "wb": a.wb, "stagger_ms": a.stagger_ms}, "combos": []}
    for c in a.combo:
        label, _, rest = c.partition("|")
        specs = [s for s in rest.split(";") if s]
        if time.monotonic() - t_start + a.seconds + 8 > a.budget_s:
            doc["combos"].append({"label": label, "specs": specs, "skipped": "camera-lock time budget"})
            continue
        r = run_combo(label, specs, a.seconds, a.exposure, a.wb, a.stagger_ms, a.exe, a.exclude,
                      (a.save_dir / label) if a.save_dir else None, a.save_max)
        r["utc_end"] = dt.datetime.now(dt.timezone.utc).isoformat()
        doc["combos"].append(r)
        (outdir / f"{a.batch}.json").write_text(json.dumps(doc, indent=1))  # incremental
        cams = r["mf"].get("cameras", []) if isinstance(r["mf"], dict) else []
        summ = []
        for cam in cams:
            summ.append(f"{cam['spec'].split(':')[0]} {'OK' if cam['streamed'] else 'FAIL ' + str(cam['failed_stage']) + ' ' + str(cam['error_hr'])}"
                        f" fps={cam['steady_fps']:.2f} B/s={cam['steady_bytes_per_s']:.0f}")
        alts = []
        if isinstance(r["pipes_while_streaming"], list):
            for pc in r["pipes_while_streaming"]:
                alts.append(f"{pc['idProduct']}:alt{[m['bAlternateSetting'] for m in pc['matched_alt_settings']]}")
        print(f"[{label}] rc={r['exit_code']} {' | '.join(summ)} pipes={alts}", flush=True)
    doc["machine_cpu_pct_end"] = cpu_pct()
    doc["utc_finished"] = dt.datetime.now(dt.timezone.utc).isoformat()
    out = outdir / f"{a.batch}.json"
    out.write_text(json.dumps(doc, indent=1))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
