# /// script
# requires-python = ">=3.10"
# ///
"""One W-FMT-NOGRAB session: a camera under one condition, every format-listing method run in turn.

    python nograb_session.py SPEC.json          # prints one JSON object (the raw timeline; analysis is in the test)

The runner wraps the WHOLE session in one camera lock (``ctx.camcmd([python, nograb_session.py, spec])``): the
streaming process, the listing method and the third-process open must overlap, which per-command locks would
prevent. Every child is a ``common.procutil.Background`` (whole-tree kill) with its own timeout.

Per session (condition = idle | streaming_native | streaming_second_api):
1. streaming conditions: start the streamer (``wincam capture`` = MF, or ``pyav_ds capture`` = DirectShow) with a
   ``--stop-file``, wait for its first frame, then ``baseline_s`` of undisturbed streaming;
2. idle condition: one CONTROL third-process open (``blocker``: a 1-frame MF capture) with no method running;
3. per method: USB-topology samples (helpers/win_topology.collect: cached hub-driver state, no device request) every
   ``sample.interval_s`` from launch to exit, recording the camera's open isochronous pipes and matched alt;
   for a method with a hold (``wincam formats --hold-ms``) the HOLD_BEGIN / HOLD_END stderr lines are timestamped
   and, in the idle condition, the third-process open starts ``blocker.delay_after_hold_s`` into the hold (after
   the pipe samples it would otherwise contaminate). A method without a hold runs twice in the idle condition:
   once alone (pipe samples) and once with a concurrent third-process open (blocking). Then ``settle_s`` of
   streaming after the method exits (recovery window). A streamer that died is restarted before the next method;
4. the streamer is stopped through its stop file (killed only if it does not stop).

Times are time.perf_counter_ns (QPC-based on Windows, the same clock as wincam's and pyav_ds's ``qpc_ns``).
SPEC keys: label, condition, camera {key, name, mf_symlink, ds_path}, out_dir, streamer (null | {argv, stop_file,
frames_jsonl, first_frame_timeout_s, stop_timeout_s, max_s}), baseline_s, settle_s, descriptor_file, methods
[{id, argv, timeout_s, hold, stdout_name}], blocker (null | {argv, out_dir_arg_index, timeout_s,
delay_after_hold_s}), sample {interval_s}. Stdlib only.
"""
from __future__ import annotations

import json
import re
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

HOLD_RE = re.compile(r"HOLD_(BEGIN|END) qpc_ns=(\d+)")


def _resolve(argv: list) -> list[str]:
    argv = [str(a) for a in argv]
    if argv and not Path(argv[0]).is_absolute():
        found = shutil.which(argv[0])
        if found:
            argv = [found] + argv[1:]
    return argv


def _clear(*paths: Path) -> None:
    for p in paths:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _lines(p: Path) -> int:
    try:
        with open(p, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


class Topo:
    """In-process win_topology sampler for one camera key (no device request)."""

    def __init__(self, desc_file: str | None, cam_key: str, device_hint: dict) -> None:
        self.desc_file = desc_file
        self.key = cam_key
        self.hint = device_hint
        self.error = None
        try:
            import win_topology as wt  # noqa: PLC0415
            self.wt = wt
        except Exception as e:  # noqa: BLE001
            self.wt = None
            self.error = f"win_topology import failed: {e!r}"

    def sample(self, tag: str = "") -> dict:
        t = time.perf_counter_ns()
        rec: dict = {"t_ns": t, "tag": tag}
        if self.wt is None:
            rec["error"] = self.error
            return rec
        try:
            s = self.wt.collect(descriptor_file=self.desc_file)
            obs = self.wt.observed_alts(s)
            o = obs.get(self.key)
            if o is None:   # key scheme differs: match the USB device instance instead
                iid = str(self.hint.get("instance_id") or "").upper()
                o = next((v for v in obs.values() if str(v.get("device_id") or "").upper() == iid), None)
            rec["collect_ms"] = round((time.perf_counter_ns() - t) / 1e6, 1)
            if o is None:
                rec["error"] = "camera not found in the topology snapshot"
            else:
                pipes = o.get("iso_pipes") or []
                rec.update(current_alt=o.get("current_alt"), iso_pipes=pipes, active=bool(pipes),
                           device_id=o.get("device_id"))
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)
        return rec


class Sampler(threading.Thread):
    def __init__(self, topo: Topo, interval_s: float, flags: dict) -> None:
        super().__init__(daemon=True)
        self.topo, self.interval_s, self.flags = topo, interval_s, flags
        self.samples: list[dict] = []
        self.stop_ev = threading.Event()

    def run(self) -> None:
        while not self.stop_ev.is_set():
            # a snapshot takes 50-400 ms: it overlaps the third-process open if the open was running when it
            # started, when it ended, or started and finished in between (generation counter changed)
            pre_run, pre_gen = bool(self.flags.get("blocker_running")), self.flags.get("blocker_gen", 0)
            pre_hold = bool(self.flags.get("in_hold"))
            r = self.topo.sample()
            r["blocker_running"] = (pre_run or bool(self.flags.get("blocker_running"))
                                    or self.flags.get("blocker_gen", 0) != pre_gen)
            r["in_hold"] = pre_hold and bool(self.flags.get("in_hold"))
            r["t_end_ns"] = time.perf_counter_ns()
            self.samples.append(r)
            self.stop_ev.wait(self.interval_s)


def run_blocker(spec: dict, out_dir: Path, tag: str) -> dict:
    """A third-process 1-frame open (bounded). Returns its timing, ok and first-frame time."""
    argv = [str(a) for a in spec["argv"]]
    i = spec.get("out_dir_arg_index")
    od = out_dir / f"blocker_{tag}"
    od.mkdir(parents=True, exist_ok=True)
    _clear(od / "frames.jsonl", od / "summary.json")      # never read a stale first frame from an earlier run
    if i is not None:
        argv[int(i)] = str(od)
    t0 = time.perf_counter_ns()
    r = procutil.run(_resolve(argv), timeout_s=float(spec.get("timeout_s") or 25))
    t1 = time.perf_counter_ns()
    obj = None
    try:
        obj = json.loads((r.get("stdout") or "").strip() or "null")
    except ValueError:
        so = r.get("stdout") or ""
        a, b = so.find("{"), so.rfind("}")
        if 0 <= a < b:
            try:
                obj = json.loads(so[a:b + 1])
            except ValueError:
                obj = None
    first_ns = None
    fj = od / "frames.jsonl"
    try:
        with open(fj, encoding="utf-8") as f:
            line = f.readline()
            if line.strip():
                first_ns = int(json.loads(line).get("qpc_ns"))
    except (OSError, ValueError, TypeError):
        first_ns = None
    frames = ((obj or {}).get("frames") or {}).get("total") if isinstance(obj, dict) else None
    ok = bool(isinstance(obj, dict) and obj.get("ok") and (frames or 0) >= 1 and not r.get("timed_out"))
    err = (obj or {}).get("error") if isinstance(obj, dict) else None
    return {"tag": tag, "argv": argv, "rc": r.get("rc"), "timed_out": r.get("timed_out"), "t_start_ns": t0,
            "t_end_ns": t1, "elapsed_s": r.get("elapsed_s"), "ok": ok, "frames": frames, "first_frame_ns": first_ns,
            "open_to_first_frame_ms": ((obj or {}).get("timings") or {}).get("open_to_first_frame_ms")
            if isinstance(obj, dict) else None,
            "activate_ms": ((obj or {}).get("timings") or {}).get("activate_ms") if isinstance(obj, dict) else None,
            "error": err, "unreleasable": (obj or {}).get("unreleasable") if isinstance(obj, dict) else None,
            "stderr_tail": (r.get("stderr") or "")[-800:], "out_dir": str(od)}


class Streamer:
    def __init__(self, spec: dict, out_dir: Path) -> None:
        self.spec = spec
        self.out_dir = out_dir
        self.n = 0
        self.bg: procutil.Background | None = None
        self.runs: list[dict] = []
        self.cur: dict | None = None

    def start(self) -> dict:
        sp = self.spec
        self.n += 1
        d = self.out_dir / f"streamer_{self.n}"
        d.mkdir(parents=True, exist_ok=True)
        stop = d / "stop.flag"
        frames = d / "frames.jsonl"
        _clear(stop, frames, d / "stdout.json", d / "stderr.txt", d / "summary.json")   # stale files of an earlier run
        argv = [str(a).replace("{out_dir}", str(d)).replace("{stop_file}", str(stop)) for a in sp["argv"]]
        self.bg = procutil.Background(_resolve(argv), stdout_path=d / "stdout.json", stderr_path=d / "stderr.txt")
        self.bg.start()
        self.cur = {"index": self.n, "argv": argv, "dir": str(d), "frames_jsonl": str(frames), "stop_file": str(stop),
                    "t_start_ns": self.bg.t_start_ns, "first_frame_seen_ns": None, "spawn_error": self.bg.spawn_error}
        deadline = time.monotonic() + float(sp.get("first_frame_timeout_s") or 20)
        while time.monotonic() < deadline:
            if _lines(frames) >= 1:
                self.cur["first_frame_seen_ns"] = time.perf_counter_ns()
                break
            if not self.bg.running():
                break
            time.sleep(0.05)
        self.cur["started_ok"] = self.cur["first_frame_seen_ns"] is not None
        if not self.cur["started_ok"]:
            self.cur["result"] = self.stop()
        return self.cur

    def alive(self) -> bool:
        return self.bg is not None and self.bg.running()

    def frames(self) -> int:
        return _lines(Path(self.cur["frames_jsonl"])) if self.cur else 0

    def stop(self) -> dict | None:
        if self.bg is None or self.cur is None:
            return None
        try:
            Path(self.cur["stop_file"]).write_text("stop", encoding="utf-8")
        except OSError:
            pass
        r = self.bg.stop(float(self.spec.get("stop_timeout_s") or 15))
        out = None
        try:
            out = json.loads(Path(self.cur["dir"], "stdout.json").read_text(encoding="utf-8", errors="replace")
                             .strip() or "null")
        except (OSError, ValueError):
            out = None
        self.cur["process"] = r
        self.cur["summary"] = {k: out.get(k) for k in ("ok", "error", "frames", "fps_measured", "duration_s",
                                                       "unreleasable", "stopped_by_stop_file", "format_fallback",
                                                       "pix_fmt", "negotiated", "timings", "stage_failed")
                               } if isinstance(out, dict) else None
        self.cur["t_stop_ns"] = time.perf_counter_ns()
        self.runs.append(self.cur)
        self.bg = None
        return r


def run_method(m: dict, out_dir: Path, sampler_iv: float, topo: Topo, blocker: dict | None, idle: bool,
               concurrent_blocker: bool, tag: str) -> dict:
    flags = {"blocker_running": False, "in_hold": False, "blocker_gen": 0}
    hold: dict = {"begin_ns": None, "end_ns": None, "begin_seen_ns": None, "end_seen_ns": None}
    blk_box: dict = {}
    blk_threads: list[threading.Thread] = []

    def start_blocker(delay_s: float) -> None:
        def go() -> None:
            if delay_s > 0:
                time.sleep(delay_s)
            flags["blocker_running"] = True
            flags["blocker_gen"] += 1
            try:
                blk_box["r"] = run_blocker(blocker, out_dir, f"{m['id']}_{tag}")
            finally:
                flags["blocker_running"] = False
                flags["blocker_gen"] += 1
        th = threading.Thread(target=go, daemon=True)
        th.start()
        blk_threads.append(th)

    def on_err(t_ns: int, line: str) -> None:
        mm = HOLD_RE.search(line)
        if not mm:
            return
        if mm.group(1) == "BEGIN":
            hold["begin_ns"], hold["begin_seen_ns"] = int(mm.group(2)), t_ns
            flags["in_hold"] = True
            if blocker and idle and m.get("hold"):
                start_blocker(float(blocker.get("delay_after_hold_s") or 0.6))
        else:
            hold["end_ns"], hold["end_seen_ns"] = int(mm.group(2)), t_ns
            flags["in_hold"] = False

    so = out_dir / f"{m.get('stdout_name') or m['id']}_{tag}.out"
    se = out_dir / f"{m.get('stdout_name') or m['id']}_{tag}.err"
    _clear(so, se)
    # a method without a hold may finish in < 100 ms (hub IOCTL): sample back to back so a snapshot overlaps it
    smp = Sampler(topo, sampler_iv if m.get("hold") else 0.0, flags)
    smp.start()
    bg = procutil.Background(_resolve(m["argv"]), stdout_path=so, stderr_path=se, on_stderr=on_err).start()
    if blocker and idle and concurrent_blocker:
        start_blocker(0.0)
    r = bg.stop(float(m.get("timeout_s") or 45))
    smp.stop_ev.set()
    smp.join(5)
    for th in blk_threads:
        th.join(float((blocker or {}).get("timeout_s") or 25) + 10)
    return {"id": m["id"], "tag": tag, "argv": [str(a) for a in m["argv"]], "process": r, "stdout_file": str(so),
            "stderr_file": str(se), "hold": hold if m.get("hold") else None, "topology_samples": smp.samples,
            "blocker": blk_box.get("r"), "concurrent_blocker": bool(concurrent_blocker and blocker and idle)}


def main(spec_path: str) -> int:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out_dir = Path(spec["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    cond = spec["condition"]
    idle = cond == "idle"
    cam = spec["camera"]
    topo = Topo(spec.get("descriptor_file"), cam["key"], cam)
    iv = float((spec.get("sample") or {}).get("interval_s") or 0.12)
    baseline_s = float(spec.get("baseline_s") or 1.5)
    settle_s = float(spec.get("settle_s") or 1.0)
    blocker = spec.get("blocker")
    doc: dict = {"tool": "nograb_session", "label": spec.get("label"), "condition": cond, "camera": cam,
                 "utc_started": results.utc_now_iso(), "t0_ns": time.perf_counter_ns(), "methods": [],
                 "streamer_runs": [], "control_blocker": None, "baseline_topology": [], "events": []}
    st = Streamer(spec["streamer"], out_dir) if spec.get("streamer") else None

    def ensure_stream(why: str) -> bool:
        if st is None:
            return True
        if st.alive():
            return True
        if st.bg is not None:
            st.stop()
        rec = st.start()
        doc["events"].append({"t_ns": time.perf_counter_ns(), "event": "streamer_start", "why": why,
                              "index": rec["index"], "ok": rec["started_ok"]})
        if rec["started_ok"]:
            time.sleep(baseline_s)
        return rec["started_ok"]

    try:
        if st is not None and not ensure_stream("session start"):
            doc["streamer_failed"] = True
        for k in range(2):
            doc["baseline_topology"].append(topo.sample(f"baseline_{k}"))
            time.sleep(0.1)
        if blocker and idle:
            doc["control_blocker"] = run_blocker(blocker, out_dir, "control")
            time.sleep(0.5)
        for m in spec.get("methods", []):
            if st is not None and not ensure_stream(f"before {m['id']}"):
                doc["methods"].append({"id": m["id"], "skipped": "streamer could not be (re)started",
                                       "tag": "main"})
                continue
            frames_before = st.frames() if st else None
            rec = run_method(m, out_dir, iv, topo, blocker, idle, concurrent_blocker=False, tag="main")
            rec["streamer_index"] = st.cur["index"] if st else None
            rec["streamer_frames_before"] = frames_before
            time.sleep(settle_s)
            rec["t_settle_end_ns"] = time.perf_counter_ns()
            rec["streamer_alive_after"] = st.alive() if st else None
            rec["streamer_frames_after"] = st.frames() if st else None
            doc["methods"].append(rec)
            if idle and blocker and not m.get("hold"):
                # no hold: run it again with a concurrent third-process open (the first run's pipe samples stay clean)
                rec2 = run_method(m, out_dir, iv, topo, blocker, idle, concurrent_blocker=True, tag="blocking")
                time.sleep(0.3)
                doc["methods"].append(rec2)
    finally:
        if st is not None:
            if st.bg is not None:
                st.stop()
            doc["streamer_runs"] = st.runs
        doc["utc_finished"] = results.utc_now_iso()
        doc["t_end_ns"] = time.perf_counter_ns()
        sys.stdout.write(json.dumps(doc, default=str) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: nograb_session.py SPEC.json", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
