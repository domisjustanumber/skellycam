# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "scipy==1.16.2", "simplejpeg==1.9.0",
#                 "nvidia-nvimgcodec-cu12[nvjpeg]==0.10.0.9", "psutil==7.2.2"]
# ///
"""BENCHMARK (timing, 23:00 queue): N concurrent intra encode streams at MATCHED QUALITY (stream scaling).

One encode path per run (--path, an id from results/intra_compare/matched_settings.json, target A unless --target B),
N streams, each with its own encoder and its own per-frame input work (benchpaths.Feed), as N camera loops would.
  --workers thread   one Python thread per stream in this process (PyAV releases the GIL in avcodec_send_frame;
                     whether simplejpeg / nvImageCodec release it shows up as flat scaling)
  --workers process  one spawned process per stream (CPU summed over the children with psutil)
Modes:
  paced    each stream at --fps; frame i is due at t0 + i/fps. late = encode finished after frame i+1 was due;
           lag_end_s = how far behind schedule the stream ended; dropped_equiv = frames a 1-deep camera buffer would
           have lost (= max(0, round(lag_end_s * fps))); keeps_up = per-stream fps >= 0.98 * fps and lag_end_s < 1/fps.
  unpaced  as fast as possible: aggregate and per-stream fps.
Per N: streams opened, first open error (session limit), aggregate fps, per-stream fps min/median, encode-call
p50/p99, process CPU s, CPU ms per frame, CPU cores, nvidia-smi and per-adapter GPU Engine utilisation.
--limit-probe M: open up to M encoders one by one (2 frames each, all kept open) and record how many opened and the
first error (hardware encoders only).

Run from the repo root on a QUIET machine (one bench at a time):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/bench_matched_concurrent.py \
      --path h264_nvenc_420 --size 1080p --source nv12 --streams 1,4,8,16 --modes paced,unpaced --reps 2 --limit-probe 32
  --smoke: streams 1,2, a few frames, no limit probe (numbers meaningless).
Writes results/intra_compare/bench/matched_concurrent_<path>_<size>_<source>_<workers>_<UTC>.json (or --outdir).
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import statistics
import sys
import threading
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).parent))
import benchpaths as B  # noqa: E402
import iclib  # noqa: E402


def stream_loop(enc, feed, n: int, fps: float, paced: bool, barrier, t0_holder=None) -> dict:
    lat, nbytes, late, err = [], 0, 0, None
    for _ in range(5):  # warm-up, untimed
        enc.encode(feed.next())
    barrier.wait()
    t0 = time.perf_counter()
    done = 0
    lag_end = 0.0
    for i in range(n):
        if paced:
            d = t0 + i / fps - time.perf_counter()
            if d > 0:
                time.sleep(d)
        try:
            a = time.perf_counter()
            for x in enc.encode(feed.next()):
                nbytes += len(x)
            b = time.perf_counter()
        except Exception as ex:  # noqa: BLE001
            err = f"{type(ex).__name__}: {ex}"[:200]
            break
        lat.append(b - a)
        done += 1
        if paced:
            if b > t0 + (i + 1) / fps:
                late += 1
            lag_end = max(0.0, b - (t0 + (i + 1) / fps))
    try:
        for x in enc.flush():
            nbytes += len(x)
    except Exception:  # noqa: BLE001
        pass
    secs = time.perf_counter() - t0
    return {"frames": done, "seconds": secs, "bytes": nbytes, "late": late, "lag_end_s": lag_end, "lat": lat,
            "error": err}


def _thread_worker(enc, feed, n, fps, paced, barrier, res):
    try:
        res.append(stream_loop(enc, feed, n, fps, paced, barrier))
    except Exception as ex:  # noqa: BLE001
        res.append({"error": f"{type(ex).__name__}: {ex}"[:200]})
        try:
            barrier.abort()
        except Exception:  # noqa: BLE001
            pass


def _process_worker(path, source, size, target, n, fps, paced, barrier, q):
    """Spawned per stream: builds its own input, encoder and feed, then runs the same loop."""
    try:
        e = B.entry(B.load_matched(), path, B.input_class(source, size), target)
        prep = B.Prepared(path, source, size)
        enc = B.Encoder(path, prep.w, prep.h, e)
        feed = B.Feed(prep)
    except Exception as ex:  # noqa: BLE001
        q.put({"open_error": f"{type(ex).__name__}: {ex}"[:200]})
        try:
            barrier.abort()
        except Exception:  # noqa: BLE001
            pass
        return
    q.put({"opened": True})
    r = stream_loop(enc, feed, n, fps, paced, barrier)
    q.put(r)


def summarize_streams(res: list[dict], wall: float, cpu: float, fps: float, paced: bool) -> dict:
    good = [r for r in res if r.get("frames")]
    out: dict = {"stream_errors": [r["error"] for r in res if r.get("error")]}
    if not good:
        return out
    tot = sum(r["frames"] for r in good)
    per = [r["frames"] / r["seconds"] for r in good]
    lat = sorted(x for r in good for x in r["lat"])
    out.update(total_frames=tot, aggregate_fps=round(tot / wall, 2), per_stream_fps_min=round(min(per), 2),
               per_stream_fps_median=round(statistics.median(per), 2), cpu_ms_per_frame=round(1000 * cpu / tot, 3),
               cpu_cores=round(cpu / wall, 3), encode_ms_p50=round(1000 * lat[len(lat) // 2], 3),
               encode_ms_p99=round(1000 * lat[min(len(lat) - 1, int(len(lat) * 0.99))], 3),
               bytes_per_frame=round(sum(r["bytes"] for r in good) / tot))
    if paced:
        out.update(late_frames=sum(r["late"] for r in good),
                   lag_end_s_max=round(max(r["lag_end_s"] for r in good), 4),
                   dropped_equiv=sum(max(0, round(r["lag_end_s"] * fps)) for r in good),
                   streams_keeping_up=sum(1 for r, f in zip(good, per)
                                          if f >= 0.98 * fps and r["lag_end_s"] < 1.0 / fps))
    return out


def run_threads(a, path, e, srcs, n_streams, paced, n_frames, adapters) -> dict:
    pairs, open_err = [], None
    for _ in range(n_streams):
        try:
            prep = B.Prepared(path, a.source, a.size, srcs)
            pairs.append((B.Encoder(path, prep.w, prep.h, e), B.Feed(prep)))
        except Exception as ex:  # noqa: BLE001
            open_err = f"{type(ex).__name__}: {ex}"[:200]
            break
    sess = B.nvidia_smi_now()
    res: list[dict] = []
    barrier = threading.Barrier(len(pairs) + 1)
    ths = [threading.Thread(target=_thread_worker, args=(enc, feed, n_frames, a.fps, paced, barrier, res))
           for enc, feed in pairs]
    proc = psutil.Process()
    for t in ths:
        t.start()
    with B.GpuSampler() as gs:
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        c0 = proc.cpu_times()
        t0 = time.perf_counter()
        for t in ths:
            t.join()
        wall = time.perf_counter() - t0
        c1 = proc.cpu_times()
    cpu = (c1.user - c0.user) + (c1.system - c0.system)
    out = {"requested": n_streams, "opened": len(pairs), "open_error": open_err, "nvidia_smi_after_open": sess,
           "wall_s": round(wall, 3), "process_cpu_s": round(cpu, 3), "gpu": gs.summary(adapters)}
    out.update(summarize_streams(res, wall, cpu, a.fps, paced))
    del pairs
    return out


def run_processes(a, path, n_streams, paced, n_frames, adapters) -> dict:
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(n_streams + 1)
    q = ctx.Queue()
    procs = [ctx.Process(target=_process_worker, args=(path, a.source, a.size, a.target, n_frames, a.fps, paced,
                                                       barrier, q)) for _ in range(n_streams)]
    for p in procs:
        p.start()
    opened, open_err = 0, None
    for _ in range(n_streams):
        m = q.get(timeout=300)
        if m.get("opened"):
            opened += 1
        else:
            open_err = m.get("open_error")
    ps = [psutil.Process(p.pid) for p in procs]
    sess = B.nvidia_smi_now()
    with B.GpuSampler(pids=[p.pid for p in procs]) as gs:
        try:
            barrier.wait(timeout=300)
        except Exception:  # noqa: BLE001
            pass
        c0 = sum(sum(x.cpu_times()[:2]) for x in ps)
        t0 = time.perf_counter()
        res = []
        for _ in range(opened):
            try:
                res.append(q.get(timeout=900))
            except Exception as ex:  # noqa: BLE001
                res.append({"error": f"result timeout {ex!r}"})
        wall = time.perf_counter() - t0
        c1 = 0.0
        for x in ps:
            try:
                c1 += sum(x.cpu_times()[:2])
            except psutil.NoSuchProcess:
                pass
    for p in procs:
        p.join(timeout=30)
    cpu = c1 - c0  # inferred lower bound if a child exited before the second read (its CPU is then lost)
    out = {"requested": n_streams, "opened": opened, "open_error": open_err, "nvidia_smi_after_open": sess,
           "wall_s": round(wall, 3), "children_cpu_s": round(cpu, 3), "gpu": gs.summary(adapters)}
    out.update(summarize_streams(res, wall, cpu, a.fps, paced))
    return out


def limit_probe(path, e, srcs, a, m: int) -> dict:
    encs, err = [], None
    before = B.nvidia_smi_now()
    for _ in range(m):
        try:
            prep = B.Prepared(path, a.source, a.size, srcs)
            enc, feed = B.Encoder(path, prep.w, prep.h, e), B.Feed(prep)
            for _ in range(2):
                enc.encode(feed.next())
            encs.append(enc)
        except Exception as ex:  # noqa: BLE001
            err = f"{type(ex).__name__}: {ex}"[:300]
            break
    peak = B.nvidia_smi_now()
    opened = len(encs)
    del encs
    return {"max_tried": m, "opened": opened, "first_error": err,
            "nvidia_smi_before": before, "nvidia_smi_at_peak": peak}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--size", default="1080p")
    ap.add_argument("--source", default="nv12", choices=["nv12", "yuy2", "mjpeg_cpu", "mjpeg_qsv", "rgb"])
    ap.add_argument("--target", default="A", choices=["A", "B"])
    ap.add_argument("--streams", default="1,4,8,16")
    ap.add_argument("--modes", default="paced,unpaced")
    ap.add_argument("--paced-frames", type=int, default=450)
    ap.add_argument("--unpaced-frames", type=int, default=300)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--workers", default="thread", choices=["thread", "process"])
    ap.add_argument("--limit-probe", type=int, default=0)
    ap.add_argument("--outdir", default="")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    if a.smoke:
        a.streams, a.paced_frames, a.unpaced_frames, a.reps, a.limit_probe = "1,2", 6, 6, 1, min(a.limit_probe, 2)
    ok, why = B.compatible(a.path, a.source)
    if not ok:
        sys.exit(f"incompatible path/source: {why}")
    ic = B.input_class(a.source, a.size)
    e = B.entry(B.load_matched(), a.path, ic, a.target)
    srcs = iclib.load_input(ic)
    try:
        adapters = B.dxgi_adapters()
    except Exception as ex:  # noqa: BLE001
        adapters = {"error": repr(ex)}
    out = {"bench": "matched_concurrent", "args": vars(a), "matched_settings": str(B.MATCHED), "entry": e,
           "system_before": B.snapshot(), "dxgi_adapters": adapters, "runs": []}
    if a.limit_probe and e["encoder"] not in ("simplejpeg", "nvjpeg"):
        lp = limit_probe(a.path, e, srcs, a, a.limit_probe)
        out["limit_probe"] = lp
        print("limit_probe", lp, flush=True)
    for rep in range(1, a.reps + 1):
        for mode in a.modes.split(","):
            paced = mode == "paced"
            nf = a.paced_frames if paced else a.unpaced_frames
            for n in map(int, a.streams.split(",")):
                if a.workers == "thread":
                    r = run_threads(a, a.path, e, srcs, n, paced, nf, adapters)
                else:
                    r = run_processes(a, a.path, n, paced, nf, adapters)
                r.update(path=a.path, size=a.size, source=a.source, workers=a.workers, mode=mode, rep=rep,
                         frames_per_stream=nf)
                print({k: r.get(k) for k in ("mode", "rep", "requested", "opened", "open_error", "streams_keeping_up",
                                             "stream_errors")}, flush=True)
                out["runs"].append(r)
    out["system_after"] = B.snapshot()
    B.write(Path(a.outdir) if a.outdir else B.BENCH,
            f"matched_concurrent_{a.path}_{a.size}_{a.source}_{a.workers}", out)


if __name__ == "__main__":
    main()
