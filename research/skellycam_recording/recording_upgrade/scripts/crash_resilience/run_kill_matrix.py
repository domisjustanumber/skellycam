"""(a) hard kill and (c) clean close for every payload x container combo, then -c copy repair.

For each combo the writer child (writer_child.py) runs in these modes:
  clean        write N frames and close normally (reference)
  idle:1       killed after 1 frame fed, trailer never written
  idle:H       killed after N/2 frames fed (encoder not drained)
  drained:N    all N frames fed and the encoder drained, then killed before close (= the on-disk image a crash at the
               very end of a recording leaves; it is also the source image for the truncation test)
  busy         killed (Popen.kill = TerminateProcess) while writing as fast as it can, as soon as the parent has seen
               N/2 packets muxed; the child's own last 'M' line says how far it really got
  rt           frames fed at 30 fps (live-recording shape); killed once N/2 frames have been FED, so encoder lag shows
               up as fed - muxed
Every recording is then read by ffprobe -count_frames, a PyAV decode loop (+seek) and a cv2 read loop (+seek), and
repaired with `ffmpeg -c copy` into .mkv and read again.

usage: python run_kill_matrix.py [--n 150] [--payloads mjpeg,ffv1,av1,h264nv] [--containers mkv,...] [--modes ...]
writes results/crash_resilience/kill_matrix.json and kill_matrix.md; media under MEDIA/kill/
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_cr as cc  # noqa: E402


def run_child(p, c, out: Path, n: int, mode: str, logdir: Path, busy_kill_at: int) -> dict:
    cc.rm(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    errf = open(logdir / f"{out.name}.stderr.txt", "w")
    cmd = [str(cc.VENV_PY), str(cc.SCRIPTS / "writer_child.py"), p, c, str(out), str(n), mode]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errf, text=True)
    muxed = fed = 0
    status = None
    killed = False
    inner = None

    def kill():
        # TerminateProcess on the real interpreter (os.kill with a non-CTRL signal on Windows), then the launcher
        if inner:
            try:
                os.kill(inner, signal.SIGTERM)
            except OSError:
                pass
        pr.kill()
    t0 = time.time()
    try:
        for line in pr.stdout:
            line = line.strip()
            if line.startswith("PID "):
                inner = int(line.split()[1])
            elif line.startswith("M "):
                _, a, b = line.split()
                muxed, fed = int(a), int(b)
                if mode in ("busy", "rt") and (fed if mode == "rt" else muxed) >= busy_kill_at and not killed:
                    kill()
                    killed = True
            elif line == "IDLE":
                kill()
                killed = True
            elif line == "CLOSED":
                status = "closed"
            elif line.split(" ")[0] in ("OPENFAIL", "STREAMFAIL", "MUXFAIL"):
                status = line[:200]
            if time.time() - t0 > 600:
                kill()
                status = "timeout"
                break
    finally:
        pr.wait(timeout=60)
        errf.close()
    return {"mode": mode, "exit_code": pr.returncode, "killed": killed, "status": status or ("killed" if killed else "?"),
            "packets_muxed_reported": muxed, "frames_fed_reported": fed}


def repair(out: Path, c: str, repdir: Path) -> dict:
    fmt, ext, opts, kind = cc.spec(c)
    repdir.mkdir(parents=True, exist_ok=True)
    if kind == "file":
        if not out.exists():
            return {"skipped": "no file"}
        dst = repdir / (out.stem + ".repaired.mkv")
        cc.rm(dst)
        r = cc.remux_ffmpeg(str(out), str(dst))
        dst2 = repdir / (out.stem + ".pyrepaired.mkv")
        cc.rm(dst2)
        r2 = cc.remux_pyav(str(out), str(dst2))
        rd = cc.read_any(dst, "mkv", None) if dst.exists() and dst.stat().st_size else None
        rd2 = cc.ffprobe_count(str(dst2)) if dst2.exists() and dst2.stat().st_size else None
        return {"ffmpeg_copy": r, "ffmpeg_copy_read": cc.summarize_read(rd) if rd else None,
                "pyav_copy": r2, "pyav_copy_ffprobe_frames": rd2["frames"] if rd2 else 0}
    if kind == "segment":
        tot = 0
        res = []
        for f in cc.segment_files(out, ext):
            dst = repdir / f"{out.name}__{f.stem}.repaired.mkv"
            cc.rm(dst)
            r = cc.remux_ffmpeg(str(f), str(dst))
            fr = cc.ffprobe_count(str(dst))["frames"] if dst.exists() and dst.stat().st_size else 0
            tot += fr
            res.append({"seg": f.name, "rc": r["rc"], "frames": fr})
        return {"segments": res, "frames_total": tot}
    if kind == "rawidx":
        src = out / "frames.mjpeg"
        if not src.exists() or src.stat().st_size == 0:
            return {"skipped": "empty"}
        dst = repdir / (out.name + ".repaired.mkv")
        cc.rm(dst)
        r = cc.remux_ffmpeg(str(src), str(dst), "mjpeg")
        return {"ffmpeg_copy": r, "frames": cc.ffprobe_count(str(dst))["frames"] if dst.exists() else 0}
    return {"skipped": "folder: frames are already individual files"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--payloads", default=",".join(cc.PAYLOADS))
    ap.add_argument("--containers", default=",".join(cc.CONTAINERS))
    ap.add_argument("--modes", default=None)
    ap.add_argument("--tag", default="kill_matrix")
    ap.add_argument("--resume", action="store_true", help="skip runs already in <tag>.json")
    ap.add_argument("--replace-modes", action="store_true", help="with --resume: rerun the given --modes, replacing old rows")
    ap.add_argument("--fp", default="both", choices=["both", "only", "none"], help="flush_packets=1 variants")
    a = ap.parse_args()
    n = a.n
    modes = a.modes.split(",") if a.modes else ["clean", "idle:1", f"idle:{n // 2}", f"drained:{n}", "busy", "rt"]
    media = cc.MEDIA / "kill"
    logdir = cc.TEMP / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    jpegs_long = cc.load_jpegs(cc.DEFAULT_SET, 891)
    ref = [cc.sha(jpegs_long[i % n]) for i in range(5000)]  # writer loops its first n frames
    results = {"env": cc.env_versions(), "n": n, "set": cc.DEFAULT_SET, "modes": modes, "runs": [],
               "nvidia_smi_before": cc.nvidia_smi()}
    done = set()
    jf = cc.RES / f"{a.tag}.json"
    if a.resume and jf.exists():
        old = json.loads(jf.read_text())
        if a.replace_modes:
            old["runs"] = [r for r in old["runs"] if r.get("mode") not in modes or "summary" not in r]
            results["replaced_modes"] = modes
        results["runs"] = old["runs"]
        results["resumed_from_partial_run"] = True
        done = {(r["payload"], r["container"], r.get("mode")) for r in old["runs"]}
        done |= {(r["payload"], r["container"], "*") for r in old["runs"] if "summary" not in r}
    pl = a.payloads.split(",")
    cl = a.containers.split(",")
    for p, c in cc.combos():
        if p not in pl or c.replace("+fp", "") not in cl:
            continue
        if (a.fp == "none" and c.endswith("+fp")) or (a.fp == "only" and not c.endswith("+fp")
                                                     and cc.spec(c)[3] in ("file", "segment")):
            continue
        for mode in modes:
            if (p, c, mode) in done or (p, c, "*") in done:
                continue
            tag = mode.replace(":", "")
            out = cc.out_path(media, p, c, tag)
            if p == "h264nv":
                gpu_before = cc.nvidia_smi()
            r = run_child(p, c, out, n, mode, logdir, busy_kill_at=n // 2)
            r.update({"payload": p, "container": c, "path": str(out)})
            if r["status"] and r["status"].split(" ")[0] in ("OPENFAIL", "STREAMFAIL", "MUXFAIL"):
                r["mode"] = mode
            if p == "h264nv":
                r["nvidia_smi_before_after"] = [gpu_before, cc.nvidia_smi()]
            if r["status"] and r["status"].split(" ")[0] in ("OPENFAIL", "STREAMFAIL", "MUXFAIL"):
                results["runs"].append(r)
                print(p, c, mode, r["status"], flush=True)
                break  # muxer refuses this combo; no point in other modes
            if out.is_file():
                r["bytes"] = out.stat().st_size
            elif out.is_dir():
                r["bytes"] = sum(f.stat().st_size for f in out.iterdir())
            rd = cc.read_any(out, c, ref if p == "mjpeg" else None)
            r["read"] = rd
            r["summary"] = cc.summarize_read(rd)
            r["repair"] = repair(out, c, media / "repaired")
            results["runs"].append(r)
            s = r["summary"]
            print(f"{p:7s} {c:10s} {mode:11s} muxed={r['packets_muxed_reported']:4d} fed={r['frames_fed_reported']:4d} "
                  f"ffprobe={s['ffprobe']} pyav={s['pyav']} cv2={s['cv2']} exact={s['byte_exact']} "
                  f"seek={s['pyav_seek']}/{s['cv2_seek']} err={s['pyav_err'][:50]}", flush=True)
            (cc.RES / f"{a.tag}.json").write_text(json.dumps(results, indent=1, default=str))
    results["nvidia_smi_after"] = cc.nvidia_smi()
    (cc.RES / f"{a.tag}.json").write_text(json.dumps(results, indent=1, default=str))
    write_md(results, cc.RES / f"{a.tag}.md")


def rep_frames(r):
    rp = r.get("repair") or {}
    if "ffmpeg_copy_read" in rp:
        x = rp["ffmpeg_copy_read"]
        return "-" if not x else f"{x['ffprobe']} (seek {'ok' if x['pyav_seek'] else 'no'})"
    if "frames_total" in rp:
        return str(rp["frames_total"])
    if "frames" in rp:
        return str(rp["frames"])
    return "n/a"


def write_md(res, path: Path):
    L = [f"# Kill matrix (generated by run_kill_matrix.py)", "",
         f"Source frames: corpus `{res['set']}` (camera JPEG bytes), N={res['n']} frames, nominal 30 fps. "
         f"Kill = TerminateProcess on the writer interpreter (os.kill(pid, SIGTERM) on the PID the child prints, then "
         f"Popen.kill() on the venv launcher; busy/rt rows use this; idle/drained rows were killed while the writer was "
         f"blocked, so which process received TerminateProcess first does not change the file). Env: {json.dumps(res['env'])}", "",
         f"nvidia-smi (sessionCount, util) before: {res.get('nvidia_smi_before')} after: {res.get('nvidia_smi_after')}", "",
         "Columns: muxed/fed = what the child reported before death; ffprobe/PyAV/cv2 = frames each reader got from the "
         "file as left on disk; exact = PyAV packets byte-identical to the camera JPEG (MJPEG only); seek = PyAV seek / "
         "cv2 seek to the middle frame; dur = ffprobe format duration without repair; repaired = frames ffprobe counts "
         "after `ffmpeg -c copy` to .mkv.", "",
         "| payload | container | mode | exit | muxed | fed | bytes | ffprobe | PyAV | cv2 | exact | seek PyAV/cv2 | dur (s) | PyAV error | repaired |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    order = {m: i for i, m in enumerate(res["modes"] + ["busy", "rt"])}
    pidx = {p: i for i, p in enumerate(cc.PAYLOADS)}
    cidx = {c: i for i, (_, c) in enumerate(cc.combos())}
    runs = sorted(res["runs"], key=lambda r: (pidx.get(r["payload"], 9), cidx.get(r["container"], 999),
                                              order.get(r.get("mode"), 99)))
    for r in runs:
        if "summary" not in r:
            L.append(f"| {r['payload']} | {r['container']} | - | - | - | - | - | - | - | - | - | - | - | refused: {r['status'][:90]} | - |")
            continue
        s = r["summary"]
        L.append(f"| {r['payload']} | {r['container']} | {r['mode']} | {r['exit_code']} | {r['packets_muxed_reported']} | "
                 f"{r['frames_fed_reported']} | {r.get('bytes', '')} | {s['ffprobe']} | {s['pyav']} | {s['cv2']} | "
                 f"{'' if s['byte_exact'] is None else s['byte_exact']} | {s['pyav_seek']}/{s['cv2_seek']} | {s['dur']} | "
                 f"{s['pyav_err'][:60]} | {rep_frames(r)} |")
    path.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--md-only":
        _r = json.loads(Path(sys.argv[2]).read_text())
        write_md(_r, Path(sys.argv[2]).with_suffix(".md"))
    else:
        main()
