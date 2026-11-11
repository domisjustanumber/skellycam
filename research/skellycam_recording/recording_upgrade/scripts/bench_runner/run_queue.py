# /// script
# requires-python = ">=3.12"
# dependencies = ["psutil==7.2.2"]
# ///
"""23:00 bench queue runner for the recording upgrade study (HANDOFF.md sections 5, 6A.5, 7; section 1 items 9-11).

Reads results/bench_queue_2300.json and runs its items STRICTLY ONE AT A TIME from the repo root.
At start (read-only): active power plan (powercfg /getactivescheme), display/sleep idle timeouts, Defender schedule
(Get-MpPreference ScanScheduleDay/ScanScheduleTime/ScanScheduleQuickScanTime/ScanParameters/ScanOnlyIfIdleEnabled),
display adapters (Intel UHD 770 presence, checked once: items tagged 'qsv' are skipped and logged if it is absent),
P-core set (GetLogicalProcessorInformationEx, EfficiencyClass), free disk.
Keeps the display on for the run with SetThreadExecutionState(ES_CONTINUOUS|ES_SYSTEM_REQUIRED|ES_DISPLAY_REQUIRED):
a per-process request that ends when this process exits (no power setting is changed). The Electron benches need a
visible, unthrottled window; the display otherwise turns off after the plan's idle timeout.
Before each item: 10 s typeperf total CPU, top 10 processes by CPU seconds over the same window (psutil),
nvidia-smi utilisation + encoder sessions, free disk. If the mean CPU is above 15 % it waits 30 s and re-checks for up to
5 min, then runs the item anyway with the flag 'load_over_15pct'.
Each item runs with a hard timeout; on expiry the whole process tree is killed (psutil, then taskkill /T /F).
No item is started after the deadline (default 05:00 local), nor if its estimate would end after the deadline;
items that would overlap an avoid window (the Defender scheduled scan, from the queue file) wait for the window to end.
CPU affinity: items with "affinity": "pcores" run with this process's affinity set to the P-cores before the child
is created (Windows children inherit the creator's affinity mask); "all" restores every logical CPU.
Appends one JSON line per item to results/BENCH_RUN_2300_LOG.jsonl and writes stdout/stderr per item to
results/bench_runner/logs/.

  uv run --script research/skellycam_recording/recording_upgrade/scripts/bench_runner/run_queue.py            # real run
  ... run_queue.py --dry-run     print the plan (order, gaps, skips) without running anything
  ... run_queue.py --smoke       every item's smoke_command (tiny frame counts), no load waiting; logs + JSONL go to
                                 the scratchpad; result folders listed in an item's "watch" are snapshotted and
                                 restored afterwards, so no smoke output stays under results/<topic>/bench/
  options: --only id1,id2  --start-from id  --deadline HH:MM  --no-affinity  --queue PATH
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
REPO = STUDY.parents[2]
RESULTS = STUDY / "results"
QUEUE = RESULTS / "bench_queue_2300.json"
LOG = RESULTS / "BENCH_RUN_2300_LOG.jsonl"
LOGDIR = RESULTS / "bench_runner" / "logs"
SCRATCH = Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/"
               "scratchpad/bench_runner")
CPU_LIMIT = 15.0


def now() -> dt.datetime:
    return dt.datetime.now()


def iso(t: dt.datetime | None = None) -> str:
    return (t or now()).astimezone().isoformat(timespec="seconds")


def sh(cmd: list[str], timeout: float = 60) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
        return (r.stdout + (r.stderr if r.returncode else "")).strip()
    except Exception as ex:  # noqa: BLE001
        return f"ERROR {ex!r}"


def ps(cmd: str, timeout: float = 60) -> str:
    return sh(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], timeout)


# ---------------------------------------------------------------- machine state (read-only)
def pcores() -> tuple[list[int], str]:
    """Logical CPUs of the highest EfficiencyClass (P-cores) via GetLogicalProcessorInformationEx(RelationProcessorCore)."""
    k32 = ctypes.windll.kernel32
    need = ctypes.c_uint32(0)
    k32.GetLogicalProcessorInformationEx(0, None, ctypes.byref(need))
    buf = ctypes.create_string_buffer(need.value)
    if not k32.GetLogicalProcessorInformationEx(0, buf, ctypes.byref(need)):
        return [], f"GetLogicalProcessorInformationEx failed: {ctypes.GetLastError()}"
    raw, off, cores = buf.raw, 0, []
    while off < need.value:
        rel = int.from_bytes(raw[off:off + 4], "little")
        size = int.from_bytes(raw[off + 4:off + 8], "little")
        if rel == 0:  # PROCESSOR_RELATIONSHIP: Flags(1) EfficiencyClass(1) Reserved(20) GroupCount(2) GROUP_AFFINITY[]
            body = off + 8
            eff = raw[body + 1]
            gcount = int.from_bytes(raw[body + 22:body + 24], "little")
            cpus = []
            for g in range(gcount):
                ga = body + 24 + g * 16  # KAFFINITY Mask (8), WORD Group (2), WORD Reserved[3]
                mask = int.from_bytes(raw[ga:ga + 8], "little")
                group = int.from_bytes(raw[ga + 8:ga + 10], "little")
                cpus += [group * 64 + i for i in range(64) if mask >> i & 1]
            cores.append((eff, cpus))
        off += size
    if not cores:
        return [], "no RelationProcessorCore records"
    top = max(e for e, _ in cores)
    classes = sorted({e for e, _ in cores})
    if len(classes) == 1:
        return [], f"single EfficiencyClass {classes}: no P/E split, affinity left at all CPUs"
    sel = sorted(c for e, cs in cores if e == top for c in cs)
    return sel, (f"{sum(1 for e, _ in cores if e == top)} cores of EfficiencyClass {top} (P-cores), "
                 f"{sum(1 for e, _ in cores if e != top)} other cores; classes {classes}")


def free_disk_gb() -> float:
    return round(shutil.disk_usage("C:/").free / 1e9, 1)


def nvidia_smi() -> str:
    return sh(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,encoder.stats.averageFps,utilization.gpu,"
               "utilization.encoder,utilization.decoder,memory.used", "--format=csv,noheader"], 30)


def igpu_present() -> tuple[bool, str]:
    out = ps("Get-PnpDevice -Class Display | ForEach-Object { \"$($_.Status)|$($_.Present)|$($_.FriendlyName)\" }")
    ok = any("UHD Graphics 770" in ln and "|True|" in ln for ln in out.splitlines())
    return ok, out


def start_state(pc: tuple[list[int], str]) -> dict:
    return {
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "local": iso(),
        "machine": os.environ.get("COMPUTERNAME"),
        "power_plan": sh(["powercfg", "/getactivescheme"]),
        "display_idle_timeout": ps("powercfg /q SCHEME_CURRENT SUB_VIDEO VIDEOIDLE | Select-String 'Current AC|Current DC' | % { $_.Line.Trim() }"),
        "sleep_idle_timeout": ps("powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String 'Current AC|Current DC' | % { $_.Line.Trim() }"),
        "defender_schedule": ps("Get-MpPreference | Select-Object ScanScheduleDay,ScanScheduleTime,"
                                "ScanScheduleQuickScanTime,ScanScheduleOffset,ScanParameters,ScanOnlyIfIdleEnabled,"
                                "SignatureScheduleDay,SignatureScheduleTime | ConvertTo-Json -Compress"),
        "display_devices": igpu_present()[1],
        "pcores": pc[0], "pcores_note": pc[1],
        "logical_cpus": psutil.cpu_count(), "free_disk_gb_c": free_disk_gb(), "nvidia_smi": nvidia_smi(),
        "python": sys.version.split()[0], "uv": sh(["uv", "--version"]),
    }


def load_record(seconds: int = 10) -> dict:
    """typeperf total CPU over `seconds` + top 10 processes by CPU seconds in the same window + nvidia-smi + disk."""
    t0 = {}
    for p in psutil.process_iter(["pid", "name"]):
        try:
            ct = p.cpu_times()
            t0[p.pid] = (p.info["name"], ct.user + ct.system)
        except Exception:  # noqa: BLE001
            pass
    out = sh(["typeperf", r"\Processor(_Total)\% Processor Time", "-si", "1", "-sc", str(seconds)], seconds + 30)
    vals = []
    for ln in out.splitlines():
        parts = ln.strip().split('","')
        if len(parts) == 2:
            try:
                vals.append(float(parts[1].strip('"')))
            except ValueError:
                pass
    rows = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            ct = p.cpu_times()
            if p.pid in t0 and p.pid not in (0, 4):
                rows.append((round(ct.user + ct.system - t0[p.pid][1], 2), p.pid, p.info["name"],
                             " ".join(p.info["cmdline"] or [])[:160]))
        except Exception:  # noqa: BLE001
            pass
    rows.sort(reverse=True)
    mean = round(sum(vals) / len(vals), 2) if vals else None
    return {"local": iso(), "typeperf_cpu_total_pct": {"samples": vals, "mean": mean, "max": max(vals) if vals else None},
            "load_over_15pct": bool(mean is not None and mean > CPU_LIMIT),
            "top10_cpu_s_in_window": [{"cpu_s": c, "pid": pid, "name": n, "cmdline": cl} for c, pid, n, cl in rows[:10]],
            "nvidia_smi": nvidia_smi(), "free_disk_gb_c": free_disk_gb()}


# ---------------------------------------------------------------- process control
def kill_tree(pid: int) -> list[str]:
    killed = []
    try:
        root = psutil.Process(pid)
        procs = root.children(recursive=True) + [root]
    except psutil.NoSuchProcess:
        procs = []
    for p in procs:
        try:
            killed.append(f"{p.pid}:{p.name()}")
            p.kill()
        except Exception:  # noqa: BLE001
            pass
    psutil.wait_procs(procs, timeout=10)
    sh(["taskkill", "/T", "/F", "/PID", str(pid)], 30)
    return killed


def leftovers(markers=("recording_upgrade", "ca7e9b09df19a3f5", "skellycam-raw")) -> list[str]:
    """Processes whose command line names this study (repo folder, the Claude scratchpad root, the media root)."""
    me = os.getpid()
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.pid == me:
                continue
            cl = " ".join(p.info["cmdline"] or [])
            if "run_queue.py" in cl or not any(m in cl for m in markers):
                continue
            out.append(f"{p.pid}:{p.info['name']}:{cl[:160]}")
        except Exception:  # noqa: BLE001
            pass
    return out


def msmpeng_cpu_s() -> float | None:
    tot = None
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower() == "msmpeng.exe":
            try:
                c = p.cpu_times()
                tot = (tot or 0.0) + c.user + c.system
            except Exception:  # noqa: BLE001
                return None  # protected process: access denied
    return tot


def defender_scans_since(t0: dt.datetime) -> str:
    """Defender scan start/finish events (Operational log ids 1000/1001) since t0, read-only."""
    return ps("Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Windows Defender/Operational'; Id=1000,1001; "
              f"StartTime=[datetime]'{t0.strftime('%Y-%m-%d %H:%M:%S')}'}} -ErrorAction SilentlyContinue | "
              "ForEach-Object { \"$($_.TimeCreated.ToString('s')) id=$($_.Id)\" }")


def subst(argv: list[str], smoke_out: Path) -> list[str]:
    return [a.replace("{SMOKE_OUT}", str(smoke_out)).replace("{REPO}", str(REPO)) for a in argv]


# ---------------------------------------------------------------- smoke protection of result folders
def snap(dirs: list[str]) -> dict[str, tuple[float, int]]:
    s = {}
    for d in dirs:
        root = REPO / d
        if root.exists():
            for f in root.rglob("*"):
                if f.is_file():
                    st = f.stat()
                    s[str(f)] = (st.st_mtime, st.st_size)
    return s


def backup(dirs: list[str], dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    for d in dirs:
        src = REPO / d
        if src.exists():
            shutil.copytree(src, dst / d)


def restore(dirs: list[str], before: dict, bk: Path, existed: dict[str, bool]) -> dict:
    removed, restored = [], []
    after = snap(dirs)
    for f, meta in after.items():
        if f not in before:
            Path(f).unlink(missing_ok=True)
            removed.append(f)
        elif before[f] != meta:
            rel = Path(f).relative_to(REPO)
            shutil.copy2(bk / rel, f)
            restored.append(f)
    for f in before:  # deleted by the smoke run -> restore
        if not Path(f).exists():
            rel = Path(f).relative_to(REPO)
            Path(f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bk / rel, f)
            restored.append(f)
    for d in dirs:  # drop empty folders the smoke run created
        root = REPO / d
        if root.exists():
            for sub in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
                try:
                    if not any(sub.iterdir()):
                        sub.rmdir()
                except OSError:
                    pass
            if not existed.get(d, True):
                shutil.rmtree(root, ignore_errors=True)  # the folder did not exist before the smoke run
    return {"removed": removed, "restored": restored}


# ---------------------------------------------------------------- scheduling helpers
def at_today(hhmm: str, ref: dt.datetime) -> dt.datetime:
    h, m = map(int, hhmm.split(":"))
    t = ref.replace(hour=h, minute=m, second=0, microsecond=0)
    if t < ref - dt.timedelta(hours=12):  # e.g. 05:00 when the run starts at 23:00 -> tomorrow
        t += dt.timedelta(days=1)
    return t


def windows(q: dict, ref: dt.datetime) -> list[tuple[dt.datetime, dt.datetime, str]]:
    out = []
    for w in q.get("avoid_windows", []):
        a, b = at_today(w["start"], ref), at_today(w["end"], ref)
        if b <= a:
            b += dt.timedelta(days=1)
        out.append((a, b, w.get("why", "")))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", default=str(QUEUE))
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--deadline", default=None, help="HH:MM local; default from the queue file (05:00)")
    ap.add_argument("--only", default="")
    ap.add_argument("--start-from", default="")
    ap.add_argument("--no-affinity", action="store_true")
    ap.add_argument("--dry-start", default="", help="--dry-run only: plan as if starting at HH:MM (e.g. 23:00)")
    a = ap.parse_args()
    q = json.loads(Path(a.queue).read_text(encoding="utf-8"))
    items = sorted(q["items"], key=lambda x: x["order"])
    if a.only:
        keep = set(a.only.split(","))
        items = [i for i in items if i["id"] in keep]
    if a.start_from:
        ids = [i["id"] for i in items]
        items = items[ids.index(a.start_from):]
    t_start = now()
    if a.dry_run and a.dry_start:
        h, m = map(int, a.dry_start.split(":"))
        t_start = t_start.replace(hour=h, minute=m, second=0, microsecond=0)
    deadline = at_today(a.deadline or q.get("deadline", "05:00"), t_start)
    wins = windows(q, t_start)
    run_id = t_start.strftime("%Y%m%dT%H%M%S") + ("_smoke" if a.smoke else "") + ("_dry" if a.dry_run else "")
    if a.smoke or a.dry_run:
        logdir = SCRATCH / "smoke" / run_id
        logf = SCRATCH / "smoke" / f"BENCH_RUN_{run_id}_LOG.jsonl"
    else:
        logdir, logf = LOGDIR / run_id, LOG
    logdir.mkdir(parents=True, exist_ok=True)
    smoke_out = SCRATCH / "smoke" / run_id / "out"
    smoke_out.mkdir(parents=True, exist_ok=True)

    def log(rec: dict) -> None:
        rec = {"run_id": run_id, **rec}
        with open(logf, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        print(json.dumps({k: v for k, v in rec.items() if k not in ("load_before", "state", "top10")}, default=str)[:600],
              flush=True)

    pc = pcores()
    all_cpus = list(range(psutil.cpu_count()))
    igpu, _ = igpu_present()
    if a.dry_run:
        t = t_start
        print(f"dry run from {iso(t)}; deadline {iso(deadline)}; P-cores {pc[1]}; iGPU present {igpu}")
        tot = 0.0
        for it in items:
            est = dt.timedelta(minutes=it["est_minutes"])
            for wa, wb, why in wins:
                if t < wb and t + est > wa:
                    print(f"   wait {iso(t)} -> {iso(wb)} (avoid window: {why})")
                    t = wb
            if "qsv" in it.get("tags", []) and not igpu:
                print(f"{it['order']:>3} {it['id']:<28} SKIP (iGPU absent)")
                continue
            if t + est > deadline:
                print(f"{it['order']:>3} {it['id']:<28} SKIP (would end after the deadline)")
                continue
            print(f"{it['order']:>3} {it['id']:<28} {iso(t)} est {it['est_minutes']:>5} min, timeout {it['timeout_minutes']} min")
            print("      " + " ".join(subst(it["command"], smoke_out)))
            t += est + dt.timedelta(seconds=25)
            tot += it["est_minutes"]
        print(f"total estimate {tot} min; planned end {iso(t)}")
        log({"event": "dry_run", "total_est_minutes": tot, "planned_end": iso(t)})
        return

    # keep the display (and the system) awake for this process's lifetime: per-process request, no setting change
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2
    exec_state = ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
    state = start_state(pc)
    state["set_thread_execution_state_prev"] = exec_state
    state["igpu_present"] = igpu
    state["deadline"] = iso(deadline)
    state["avoid_windows"] = [(iso(x), iso(y), w) for x, y, w in wins]
    log({"event": "start", "smoke": a.smoke, "queue": a.queue, "items": [i["id"] for i in items], "state": state})
    if not igpu:
        log({"event": "igpu_absent", "note": "Intel UHD 770 not Present True: items tagged qsv are skipped"})
    me = psutil.Process()
    for it in items:
        rec: dict = {"event": "item", "order": it["order"], "id": it["id"], "topic": it["topic"],
                     "est_minutes": it["est_minutes"], "timeout_minutes": it["timeout_minutes"], "smoke": a.smoke,
                     "flags": []}
        if "qsv" in it.get("tags", []) and not igpu:
            rec.update(status="skipped", reason="Intel UHD 770 absent")
            log(rec)
            continue
        extra = it.get("qsv_absent_extra_args", []) if not igpu else []
        if extra:
            rec["flags"].append(f"Intel UHD 770 absent: QSV parts dropped via {extra}")
        est = dt.timedelta(minutes=it["est_minutes"] if not a.smoke else 0)
        if not a.smoke:
            for wa, wb, why in wins:
                if now() < wb and now() + est > wa:
                    rec["flags"].append(f"waited for avoid window until {iso(wb)} ({why})")
                    log({"event": "wait_window", "id": it["id"], "until": iso(wb), "why": why})
                    while now() < wb:
                        time.sleep(20)
        if now() >= deadline or (not a.smoke and now() + est > deadline):
            rec.update(status="skipped", reason=f"deadline {iso(deadline)}: not started")
            log(rec)
            continue
        # background load
        if a.smoke:
            load = load_record(3)
        else:
            load = load_record(10)
            waited = 0
            while load["load_over_15pct"] and waited < 300:
                time.sleep(30)
                waited += 40
                load = load_record(10)
            if waited:
                rec["flags"].append(f"waited {waited} s for CPU <= {CPU_LIMIT} %")
        if load["load_over_15pct"]:
            rec["flags"].append("load_over_15pct")
        rec["load_before"] = load
        argv = subst(it["smoke_command"] if a.smoke else it["command"], smoke_out) + extra
        rec["command"] = argv
        watch = it.get("watch", []) if a.smoke else []
        bk = SCRATCH / "smoke" / run_id / "backup" / it["id"]
        before = snap(watch)
        existed = {d: (REPO / d).exists() for d in watch}
        if watch:
            backup(watch, bk)
        aff = all_cpus if (a.no_affinity or it.get("affinity", "pcores") == "all" or not pc[0]) else pc[0]
        try:
            me.cpu_affinity(aff)
        except Exception as ex:  # noqa: BLE001
            rec["flags"].append(f"affinity not set: {ex!r}")
        rec["affinity"] = "pcores" if aff == pc[0] and pc[0] else "all"
        env = dict(os.environ)
        env.pop("ELECTRON_RUN_AS_NODE", None)
        env["PYTHONUNBUFFERED"] = "1"
        env.update(it.get("env", {}))
        out_p = logdir / f"{it['order']:02d}_{it['id']}.out.txt"
        err_p = logdir / f"{it['order']:02d}_{it['id']}.err.txt"
        rec["stdout"], rec["stderr"] = str(out_p), str(err_p)
        rec["start"] = iso()
        t_item = now()
        ms0 = msmpeng_cpu_s()
        t0 = time.perf_counter()
        timeout_s = 60 * (it["timeout_minutes"] if not a.smoke else it.get("smoke_timeout_minutes", 15))
        with open(out_p, "w", encoding="utf-8") as fo, open(err_p, "w", encoding="utf-8") as fe:
            try:
                p = subprocess.Popen(argv, cwd=str(REPO), stdout=fo, stderr=fe, env=env,
                                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                try:
                    rc = p.wait(timeout=timeout_s)
                    rec["status"] = "ok" if rc == 0 else "failed"
                except subprocess.TimeoutExpired:
                    rec["killed"] = kill_tree(p.pid)
                    rc = p.wait(timeout=30) if p.poll() is None else p.returncode
                    rec["status"] = "timeout"
                    rec["flags"].append(f"hard timeout {timeout_s} s: process tree killed")
            except Exception as ex:  # noqa: BLE001
                rc = None
                rec["status"] = "launch_error"
                rec["error"] = repr(ex)
        try:
            me.cpu_affinity(all_cpus)
        except Exception:  # noqa: BLE001
            pass
        rec.update(end=iso(), exit_code=rc, duration_min=round((time.perf_counter() - t0) / 60, 2),
                   nvidia_smi_after=nvidia_smi(), free_disk_gb_after=free_disk_gb())
        ms1 = msmpeng_cpu_s()
        rec["msmpeng_cpu_s_during_item"] = round(ms1 - ms0, 2) if ms0 is not None and ms1 is not None else "unreadable"
        if not a.smoke:
            ev = defender_scans_since(t_item)
            rec["defender_scan_events_during_item"] = ev
            if "id=1000" in ev or "id=1001" in ev:
                rec["flags"].append("Defender scan event during item")
        left = leftovers()
        if left:
            rec["leftover_processes"] = left
            rec["flags"].append("leftover processes after item (listed, not killed)")
        if watch:
            rec["smoke_cleanup"] = restore(watch, before, bk, existed)
        log(rec)
    log({"event": "end", "local": iso(), "minutes": round((now() - t_start).total_seconds() / 60, 1),
         "leftover_processes": leftovers(), "defender_scan_events_during_run": defender_scans_since(t_start)})
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)


if __name__ == "__main__":
    main()
