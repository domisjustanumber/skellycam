# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "psutil==7.2.2", "opencv-python==4.12.0.88"]
# ///
# PEP 723 header added 2026-11-09 for the 23:00 bench queue: runs under PyAV 19.0.2 via `uv run --script`
# (child processes started with sys.executable inherit this environment).
"""Recording-wrapper write benchmark (goal G5). One run = one cell: writer variant x cameras x load profile x model.

Simulated cameras replay real camera payloads (corpus JPEGs, looped; or FFV1 packets made from the YUY2 corpus)
on an absolute per-camera schedule (fps from the profile). Each camera is its own process, like SkellyCam.
Nothing is encoded; only the wrapper / file-system cost is measured.

Threading models (--model):
  inloop           the camera process writes each frame itself before grabbing the next (today's SkellyCam
                   recorder runs inside the capture loop). A tick is DROPPED when, at the moment the loop is
                   ready, more than --inloop-buffer ticks have elapsed (driver-queue model; an assumption).
  inloop_lockstep  inloop + a multiprocessing.Barrier across cameras before every frame (SkellyCam's lockstep
                   gate grabs only when no camera is behind), so one slow write delays every camera.
  thread           camera loop hands frames to one writer thread per camera through a bounded queue
                   (--ring-s seconds of frames); a full queue drops the frame (counted, explicit).
  process          camera loop memcpy's frames into a shared-memory ring; one writer PROCESS per camera.
  process_shared   same ring, ONE writer process serving all cameras round-robin.

Per frame it records: write-call latency (writer.write duration), tick->written latency, drops; per process:
CPU seconds (process_time / thread_time); system-wide: psutil CPU busy, PhysicalDrive write bytes,
MsMpEng.exe CPU when readable. Output media goes to --out-dir (default MEDIA/bench_runs) and is deleted after
the run unless --keep. Results: one JSON (--json-out, default results/write_throughput/bench/adhoc/<cell>.json).

Example (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/bench_write.py \
      --writer mkv --cams 4 --profile 1080p30 --model thread --duration 30
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import queue
import shutil
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wt_common as W  # noqa: E402

CTRL_HEAD, CTRL_TAIL, CTRL_DONE = 0, 1, 2


# ------------------------------------------------------------------------------------------- shared-memory ring
class Ring:
    def __init__(self, name: str, slots: int, slot_bytes: int, create: bool):
        from multiprocessing import shared_memory
        import numpy as np
        self.L, self.S = slots, slot_bytes
        if create:
            self.data = shared_memory.SharedMemory(name=name + "_d", create=True, size=slots * slot_bytes)
            self.meta_m = shared_memory.SharedMemory(name=name + "_m", create=True, size=slots * 3 * 8 + 3 * 8)
        else:
            self.data = shared_memory.SharedMemory(name=name + "_d")
            self.meta_m = shared_memory.SharedMemory(name=name + "_m")
        arr = np.ndarray((slots * 3 + 3,), dtype=np.int64, buffer=self.meta_m.buf)
        if create:
            arr[:] = 0
        self.meta = arr[: slots * 3].reshape(slots, 3)
        self.ctrl = arr[slots * 3:]
        self.buf = self.data.buf

    def close(self, unlink=False):
        self.meta = self.ctrl = None
        self.buf = None
        self.data.close()
        self.meta_m.close()
        if unlink:
            self.data.unlink()
            self.meta_m.unlink()


# ------------------------------------------------------------------------------------------- writer side
class WriterStats:
    def __init__(self):
        self.wlat, self.lat, self.n, self.bytes = [], [], 0, 0
        self.last_written_ns = 0

    def add(self, t0, t1, tick, n):
        self.wlat.append(t1 - t0)
        self.lat.append(t1 - tick)
        self.n += 1
        self.bytes += n
        self.last_written_ns = t1


def timed_write(wr, st: WriterStats, fi, data, tick):
    t0 = time.perf_counter_ns()
    wr.write(fi, data, tick)
    t1 = time.perf_counter_ns()
    st.add(t0, t1, tick, len(data))


def close_writer(wr) -> tuple[dict, float]:
    t0 = time.perf_counter()
    info = wr.close()
    return info, time.perf_counter() - t0


def writer_process_main(cfg, cams, ring_names, slots, slot_bytes, ready_q, go, res_q):
    import psutil  # noqa: F401  (import cost outside the timed region)
    out = Path(cfg["out_dir"])
    rings = {c: Ring(ring_names[c], slots, slot_bytes, create=False) for c in cams}
    writers = {c: W.make_writer(cfg["writer"], out, c, W.payload_for(cfg["profile"], cfg["payload"], c, 1),
                                cfg["fps"], sidecar=not cfg["no_sidecar"]) for c in cams}
    stats = {c: WriterStats() for c in cams}
    tails = {c: 0 for c in cams}
    ready_q.put(("writer", tuple(cams)))
    go.wait()
    cpu0 = time.process_time()
    idle_sleeps = 0
    live = set(cams)
    while live:
        progressed = False
        for c in list(live):
            r = rings[c]
            head = int(r.ctrl[CTRL_HEAD])
            if tails[c] < head:
                sl = tails[c] % r.L
                fi, tick, n = (int(x) for x in r.meta[sl])
                timed_write(writers[c], stats[c], fi, r.buf[sl * r.S: sl * r.S + n], tick)
                tails[c] += 1
                r.ctrl[CTRL_TAIL] = tails[c]
                progressed = True
            elif r.ctrl[CTRL_DONE]:
                live.discard(c)
        if not progressed:
            idle_sleeps += 1
            time.sleep(0.0005)
    closes = {}
    for c in cams:
        closes[c] = close_writer(writers[c])
    cpu = time.process_time() - cpu0
    for c in cams:
        s = stats[c]
        res_q.put(dict(role="writer", cam=c, written=s.n, bytes=s.bytes, wlat=s.wlat, lat=s.lat,
                       last_written_ns=s.last_written_ns, close_s=closes[c][1], close_info=closes[c][0],
                       writer_cpu_s=cpu / len(cams), writer_proc_cams=len(cams), idle_sleeps=idle_sleeps))
    for r in rings.values():
        r.close()


# ------------------------------------------------------------------------------------------- camera side
def camera_main(cfg, cam, ready_q, go, t0_val, res_q, barrier, stop_val, ring_name, slots, slot_bytes):
    import psutil  # noqa: F401
    model = cfg["model"]
    fps = cfg["fps"]
    pl = W.payload_for(cfg["profile"], cfg["payload"], cam)
    src = pl["packets"]
    out = Path(cfg["out_dir"])
    period = 1e9 / fps
    n_ticks = int(round(cfg["duration"] * fps))
    wr = None
    q = None
    th = None
    ring = None
    wstats = WriterStats()
    wres = {}
    if model in ("inloop", "inloop_lockstep", "thread"):
        wr = W.make_writer(cfg["writer"], out, cam, pl, fps, sidecar=not cfg["no_sidecar"])
    if model == "thread":
        q = queue.Queue(maxsize=slots)

        def wloop():
            tc0 = time.thread_time()
            while True:
                item = q.get()
                if item is None:
                    break
                fi, data, tick = item
                timed_write(wr, wstats, fi, data, tick)
            wres["close"] = close_writer(wr)
            wres["writer_cpu_s"] = time.thread_time() - tc0
        th = threading.Thread(target=wloop, name=f"writer{cam}", daemon=True)
    if model.startswith("process"):
        ring = Ring(ring_name, slots, slot_bytes, create=False)
    ready_q.put(("camera", cam))
    go.wait()
    t0 = t0_val.value
    if th:
        th.start()
    cpu0 = time.process_time()
    tcam0 = time.thread_time()
    produced = dropped = late = 0
    lateness = []
    k = 0
    t_end = int(t0 + n_ticks * period)
    while True:
        if barrier is not None:
            # lockstep: every camera passes the gate together; camera 0's clock decides when to stop so all
            # processes leave on the same iteration (two barrier phases per frame)
            if barrier.wait() == 0:
                stop_val.value = int(time.perf_counter_ns() >= t_end)
            barrier.wait()
            if stop_val.value:
                break
            if k >= n_ticks:
                time.sleep(max(0, t_end - time.perf_counter_ns()) / 1e9)
                continue
        elif k >= n_ticks:
            break
        tick = int(t0 + k * period)
        now = time.perf_counter_ns()
        if tick > now:
            time.sleep((tick - now) / 1e9)
            now = time.perf_counter_ns()
        if model.startswith("inloop"):
            # ticks that elapsed while we were busy: only the newest --inloop-buffer survive
            cur = int((now - t0) // period)
            oldest_alive = cur - cfg["inloop_buffer"] + 1
            if oldest_alive > k:
                skip = min(oldest_alive, n_ticks) - k
                dropped += skip
                k += skip
                if k >= n_ticks:
                    continue
                tick = int(t0 + k * period)
        lateness.append(now - tick)
        if now - tick > period:
            late += 1
        data = bytes(memoryview(src[k % len(src)]))  # a fresh buffer per frame, like a capture would deliver
        produced += 1
        if model.startswith("inloop"):
            timed_write(wr, wstats, k, data, tick)
        elif model == "thread":
            try:
                q.put_nowait((k, data, tick))
            except queue.Full:
                dropped += 1
        else:
            head = int(ring.ctrl[CTRL_HEAD])
            if head - int(ring.ctrl[CTRL_TAIL]) >= ring.L:
                dropped += 1
            else:
                sl = head % ring.L
                n = len(data)
                ring.buf[sl * ring.S: sl * ring.S + n] = data
                ring.meta[sl] = (k, tick, n)
                ring.ctrl[CTRL_HEAD] = head + 1
        k += 1
    cam_thread_cpu = time.thread_time() - tcam0
    if model.startswith("inloop"):
        wres["close"] = close_writer(wr)
    elif model == "thread":
        q.put(None)
        th.join()
    else:
        ring.ctrl[CTRL_DONE] = 1
        ring.close()
    cpu = time.process_time() - cpu0
    r = dict(role="camera", cam=cam, ticks=n_ticks, produced=produced, dropped=dropped, late_ticks=late,
             lateness=lateness, process_cpu_s=cpu, camera_thread_cpu_s=cam_thread_cpu, source=pl.get("source"))
    if wr is not None:
        r.update(written=wstats.n, bytes=wstats.bytes, wlat=wstats.wlat, lat=wstats.lat,
                 last_written_ns=wstats.last_written_ns, close_s=wres["close"][1], close_info=wres["close"][0],
                 writer_cpu_s=wres.get("writer_cpu_s"))
    res_q.put(r)


# ------------------------------------------------------------------------------------------- parent
def msmpeng_cpu():
    import psutil
    for p in psutil.process_iter(["name"]):
        if (p.info.get("name") or "").lower() == "msmpeng.exe":
            try:
                t = p.cpu_times()
                return t.user + t.system
            except Exception as e:  # noqa: BLE001
                return f"{type(e).__name__}"
    return None


def disk_counters():
    import psutil
    try:
        d = psutil.disk_io_counters(perdisk=True)
        return {k: dict(write_bytes=v.write_bytes, write_count=v.write_count, read_bytes=v.read_bytes,
                        write_time_ms=getattr(v, "write_time", None)) for k, v in d.items()}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}


def run(cfg) -> dict:
    import numpy as np
    import psutil
    w, h, fps, _ = W.PROFILES[cfg["profile"]]
    cfg["fps"] = fps
    n = cfg["cams"]
    out = Path(cfg["out_dir"])
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    # payload sizes -> slot size and disk-space guard
    sizes = []
    for c in range(n):
        pk = W.payload_for(cfg["profile"], cfg["payload"], c)["packets"]
        sizes.append((max(len(p) for p in pk), sum(len(p) for p in pk) / len(pk)))
    slot_bytes = (max(s[0] for s in sizes) + 4095) // 4096 * 4096
    slots = max(int(round(cfg["ring_s"] * fps)), 2)
    est = sum(s[1] for s in sizes) * fps * cfg["duration"]
    free = shutil.disk_usage(out).free
    if free < 2 * est + 50e9:
        raise SystemExit(f"refusing: estimated {est / 1e9:.1f} GB, free {free / 1e9:.1f} GB")
    ctx = mp.get_context("spawn")
    ready_q, res_q = ctx.Queue(), ctx.Queue()
    go = ctx.Event()
    t0_val = ctx.Value("q", 0, lock=False)
    barrier = ctx.Barrier(n) if cfg["model"] == "inloop_lockstep" else None
    stop_val = ctx.Value("i", 0, lock=False)
    tag = f"wt{os.getpid()}"
    ring_names = {c: f"{tag}_{c}" for c in range(n)}
    rings = []
    procs = []
    if cfg["model"].startswith("process"):
        rings = [Ring(ring_names[c], slots, slot_bytes, create=True) for c in range(n)]
        groups = [[c] for c in range(n)] if cfg["model"] == "process" else [list(range(n))]
        for g in groups:
            procs.append(ctx.Process(target=writer_process_main,
                                     args=(cfg, g, ring_names, slots, slot_bytes, ready_q, go, res_q)))
    for c in range(n):
        procs.append(ctx.Process(target=camera_main,
                                 args=(cfg, c, ready_q, go, t0_val, res_q, barrier, stop_val, ring_names.get(c), slots,
                                       slot_bytes)))
    for p in procs:
        p.start()
    for _ in procs:
        ready_q.get(timeout=300)
    cpu_sys0 = psutil.cpu_times()
    disk0 = disk_counters()
    mse0 = msmpeng_cpu()
    t0 = time.perf_counter_ns() + 500_000_000
    t0_val.value = t0
    wall0 = time.perf_counter()
    go.set()
    n_results = n + (n if cfg["model"].startswith("process") else 0)
    results = [res_q.get(timeout=cfg["duration"] + 600) for _ in range(n_results)]
    for p in procs:
        p.join(timeout=120)
    wall = time.perf_counter() - wall0
    cpu_sys1 = psutil.cpu_times()
    disk1 = disk_counters()
    mse1 = msmpeng_cpu()
    for r in rings:
        r.close(unlink=True)
    # ----- merge per camera
    cams = {}
    for r in results:
        d = cams.setdefault(r["cam"], {})
        for k, v in r.items():
            if k in ("role",):
                continue
            if k == "writer_cpu_s" and v is None:
                continue
            d[k] = v
    per_cam = []
    all_w, all_l, all_late = [], [], []
    tot_bytes = 0
    last_written = 0
    for c in sorted(cams):
        d = cams[c]
        wl = np.asarray(d.get("wlat", []), dtype=np.float64) / 1e6
        ll = np.asarray(d.get("lat", []), dtype=np.float64) / 1e6
        la = np.asarray(d.get("lateness", []), dtype=np.float64) / 1e6
        all_w.append(wl)
        all_l.append(ll)
        all_late.append(la)
        tot_bytes += d.get("bytes", 0)
        last_written = max(last_written, d.get("last_written_ns", 0))
        per_cam.append(dict(cam=c, source=d.get("source"), ticks=d["ticks"], produced=d["produced"],
                            written=d.get("written"), dropped=d["dropped"], late_ticks=d["late_ticks"],
                            bytes=d.get("bytes"), write_ms=W.pct(wl), tick_to_written_ms=W.pct(ll),
                            grab_lateness_ms=W.pct(la), close_s=d.get("close_s"), close_info=d.get("close_info"),
                            camera_process_cpu_s=d.get("process_cpu_s"), camera_thread_cpu_s=d.get("camera_thread_cpu_s"),
                            writer_cpu_s=d.get("writer_cpu_s"), writer_proc_cams=d.get("writer_proc_cams")))
    aw, al, ala = (np.concatenate(x) if x else np.array([]) for x in (all_w, all_l, all_late))
    busy = lambda t: sum(v for k, v in t._asdict().items() if k not in ("idle",))  # noqa: E731
    sys_busy = busy(cpu_sys1) - busy(cpu_sys0)
    sys_total = sum(cpu_sys1) - sum(cpu_sys0)
    ours = sum((p["camera_process_cpu_s"] or 0) for p in per_cam)
    if cfg["model"].startswith("process"):
        ours += sum((p["writer_cpu_s"] or 0) for p in per_cam)
    ncpu = psutil.cpu_count()
    phys = {}
    for k in disk1:
        if k in disk0 and isinstance(disk1[k], dict):
            phys[k] = {m: (disk1[k][m] - disk0[k][m]) if disk1[k][m] is not None else None for m in disk1[k]}
    files_written = sum((p["close_info"] or {}).get("files", 0) for p in per_cam)
    produce_s = cfg["duration"]
    write_span_s = (last_written - t0) / 1e9 if last_written else None
    summary = dict(
        cams=n, profile=cfg["profile"], fps=fps, writer=cfg["writer"], model=cfg["model"], payload=cfg["payload"],
        duration_s=cfg["duration"], wall_s=wall, ticks=sum(p["ticks"] for p in per_cam),
        produced=sum(p["produced"] for p in per_cam), written=sum((p["written"] or 0) for p in per_cam),
        dropped=sum(p["dropped"] for p in per_cam), late_ticks=sum(p["late_ticks"] for p in per_cam),
        bytes=tot_bytes, files_written=files_written,
        throughput_MBps_over_duration=tot_bytes / produce_s / 1e6,
        throughput_MBps_over_write_span=(tot_bytes / write_span_s / 1e6) if write_span_s else None,
        nominal_MBps=sum(s[1] for s in sizes) * fps / 1e6,
        write_ms_all=W.pct(aw), tick_to_written_ms_all=W.pct(al), grab_lateness_ms_all=W.pct(ala),
        worst_cam_write_ms_p999=max((p["write_ms"]["p99.9"] or 0) for p in per_cam),
        max_close_s=max((p["close_s"] or 0) for p in per_cam),
        our_cpu_s=ours, our_cpu_pct_of_one_core_per_cam=100 * ours / produce_s / n,
        system_busy_pct_all_cpus=100 * sys_busy / sys_total if sys_total else None,
        other_cpu_s_estimate=sys_busy - ours, logical_cpus=ncpu,
        msmpeng_cpu_s=(mse1 - mse0) if isinstance(mse0, float) and isinstance(mse1, float) else f"{mse0}/{mse1}",
        physical_disk_delta=phys, slots=slots, slot_bytes=slot_bytes,
    )
    return dict(config=cfg, env=W.env_versions(), started=time.strftime("%Y-%m-%dT%H:%M:%S"), summary=summary,
                per_cam=per_cam)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--writer", required=True, choices=list(W.WRITER_VARIANTS))
    ap.add_argument("--cams", type=int, default=1)
    ap.add_argument("--profile", default="720p30", choices=list(W.PROFILES))
    ap.add_argument("--payload", default="mjpeg", choices=["mjpeg", "ffv1"])
    ap.add_argument("--model", default="thread",
                    choices=["inloop", "inloop_lockstep", "thread", "process", "process_shared"])
    ap.add_argument("--duration", type=float, default=30.0, help="seconds of production per camera")
    ap.add_argument("--ring-s", type=float, default=2.87,
                    help="queue/ring depth in seconds (2.87 s = the ring study's 1080p ring)")
    ap.add_argument("--inloop-buffer", type=int, default=1, help="inloop drop model: ticks that survive a stall")
    ap.add_argument("--no-sidecar", action="store_true", help="skip the per-frame index sidecar (append keeps it)")
    ap.add_argument("--out-dir", default=str(W.MEDIA / "bench_runs" / "current"))
    ap.add_argument("--keep", action="store_true", help="keep the recording (default: delete after the run)")
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()
    cfg = dict(writer=a.writer, cams=a.cams, profile=a.profile, payload=a.payload, model=a.model,
               duration=a.duration, ring_s=a.ring_s, inloop_buffer=a.inloop_buffer, no_sidecar=a.no_sidecar,
               out_dir=a.out_dir, argv=sys.argv)
    cell = f"{a.writer}__{a.cams}cam__{a.profile}__{a.payload}__{a.model}__{int(a.duration)}s"
    res = run(cfg)
    res["cell"] = cell
    t = time.perf_counter()
    if not a.keep:
        shutil.rmtree(a.out_dir, ignore_errors=True)
    res["summary"]["delete_s"] = None if a.keep else time.perf_counter() - t
    jo = Path(a.json_out) if a.json_out else W.BENCH_RESULTS / "adhoc" / f"{cell}.json"
    jo.parent.mkdir(parents=True, exist_ok=True)
    jo.write_text(json.dumps(res, indent=1, default=str))
    s = res["summary"]
    print(json.dumps({k: s[k] for k in ("writer", "model", "cams", "profile", "produced", "written", "dropped",
                                        "late_ticks", "files_written", "write_ms_all", "max_close_s")}, default=str))
    print("wrote", jo)


if __name__ == "__main__":
    main()
