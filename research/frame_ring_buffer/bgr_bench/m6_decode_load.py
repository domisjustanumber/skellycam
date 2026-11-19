"""M6 (specs/frame-ring.md 11.3): decode thread CPU and BGR skip rate under N camera processes.

The main process creates, per camera, a JPEG ring and a BGR ring (7.1), then starts one process per
camera. Each camera process calls `cv2.setNumThreads(1)`, attaches the writers, starts the real
`DecodeStage` and runs a feeder thread that, at a paced frame rate, does what capture does in 5.3:
JPEG ring write, then `DecodeInput(source="JPEG")` into the waiting place. Offered, committed and
skipped come from the ring counters (table 3.3). Writes `results/m6.json`.
"""
import json
import multiprocessing as mp
import os
import struct
import sys
import threading
import time

import psutil

import common

common.add_ring_path()
from skellycam.core.ipc.frame_ring import FrameRingCreator, PixelFormat  # noqa: E402
from skellycam.core.ipc.frame_ring.layout import COUNTERS_OFFSET  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DURATION_S = 20.0
CHILD_TIMEOUT_S = 180.0
CASES = [("720p", 60, 4), ("720p", 60, 8), ("1080p", 60, 4), ("1080p", 60, 8), ("720p", 30, 4)]


def thread_cpu_s(native_id):
    for t in psutil.Process().threads():
        if t.id == native_id:
            return t.user_time + t.system_time
    raise LookupError(native_id)


def camera(index, size, fps, jpeg_name, bgr_name, ready, go, results):
    """One camera process. Puts a dict of its numbers on `results`."""
    import cv2
    import numpy as np
    common.add_ring_path()
    from skellycam.core.ipc.frame_ring import DecodeInput, DecodeStage, FrameRingWriter, decode_jpeg
    cv2.setNumThreads(1)
    payloads = common.jpegs(size, 8)
    payloads = payloads[index % 8:] + payloads[:index % 8]  # the cameras are not in step on content
    jpeg_writer, bgr_writer = FrameRingWriter.attach(jpeg_name), FrameRingWriter.attach(bgr_name)
    decode_ns = []

    def timed_decode(payload):
        t0 = time.perf_counter_ns()
        out = decode_jpeg(payload)
        decode_ns.append(time.perf_counter_ns() - t0)
        return out

    stage = DecodeStage(bgr_writer, decode=timed_decode)
    timed_decode(payloads[0])  # first-call setup of OpenCV, outside the window
    decode_ns.clear()
    stage.start()
    decode_tid = stage._thread.native_id
    feeder = {}

    def feed():
        feeder["tid"] = threading.get_native_id()
        period = 1e9 / fps
        # The CPU snapshot takes milliseconds: take it before the clock starts, or the first ticks are late.
        feeder["cpu0"] = (thread_cpu_s(decode_tid), time.thread_time(), psutil.Process().cpu_times())
        start = time.perf_counter_ns()
        k = late_resync = 0
        late = []
        while True:
            deadline = start + k * period
            now = time.perf_counter_ns()
            if now - start >= DURATION_S * 1e9:
                break
            if deadline > now:
                time.sleep((deadline - now) / 1e9)
            elif now - deadline > period:  # more than one period late: a camera would not deliver a burst
                late_resync += 1
            payload = payloads[k % 8]
            t = time.perf_counter_ns()
            late.append(t - deadline)
            jpeg_writer.write(payload, frame_number=k, arrival_ns=t, sample_ns=t, source_frame_number=k, flags=0,
                              rotation_cw_deg=0)
            stage.waiting_place.put(DecodeInput(payload=payload, source="JPEG", frame_number=k, arrival_ns=t,
                                                sample_ns=t, source_frame_number=k, flags=0, rotation_cw_deg=0))
            k += 1
        elapsed = (time.perf_counter_ns() - start) / 1e9
        time.sleep(0.1)  # let the decode thread take the last frame, so that stop() drops none
        feeder.update(offered=k, elapsed_s=elapsed, late_resync=late_resync, lateness_ms=common.stats_ms(late),
                      cpu1=(thread_cpu_s(decode_tid), time.thread_time(), psutil.Process().cpu_times()))

    try:
        ready.put(index)
        if not go.wait(60):
            raise TimeoutError("no go signal")
        thread = threading.Thread(target=feed, name="feeder")
        thread.start()
        thread.join(DURATION_S + 30)
        if thread.is_alive():
            raise TimeoutError("feeder did not finish")
        stage.stop()
        (d0, f0, p0), (d1, f1, p1) = feeder["cpu0"], feeder["cpu1"]
        el = feeder["elapsed_s"]
        dec = np.asarray(decode_ns, dtype=np.float64) / 1e6
        results.put(dict(index=index, offered=feeder["offered"], elapsed_s=el, late_resync=feeder["late_resync"],
                         feeder_lateness_ms=feeder["lateness_ms"],
                         decode_thread_cpu_pct=100 * (d1 - d0) / el, feeder_thread_cpu_pct=100 * (f1 - f0) / el,
                         process_cpu_pct=100 * ((p1.user + p1.system) - (p0.user + p0.system)) / el,
                         decode_ms=dict(n=int(dec.size), median=float(np.median(dec)),
                                        p95=float(np.percentile(dec, 95)), p99=float(np.percentile(dec, 99)),
                                        max=float(dec.max()))))
    except Exception as error:
        results.put(dict(index=index, error=repr(error)))
        stage.stop()
    finally:
        jpeg_writer.close()
        bgr_writer.close()


def run_case(size, fps, n):
    w, h = common.SIZES[size]
    ctx = mp.get_context("spawn")
    ready, results, go = ctx.Queue(), ctx.Queue(), ctx.Event()
    creators, procs = [], []
    try:
        for i in range(n):
            j = FrameRingCreator.create(camera_id=f"m6c{i}", camera_index=i, pixel_format=PixelFormat.JPEG,
                                        width=w, height=h, fps_num=fps, fps_den=1)
            creators.append(j)
            j.bgr = FrameRingCreator.create(camera_id=f"m6c{i}", camera_index=i, pixel_format=PixelFormat.BGR24,
                                            width=w, height=h, fps_num=fps, fps_den=1)
        procs = [ctx.Process(target=camera, args=(i, size, fps, c.name, c.bgr.name, ready, go, results), daemon=True)
                 for i, c in enumerate(creators)]
        for p in procs:
            p.start()
        for _ in range(n):
            ready.get(timeout=120)
        time.sleep(0.5)
        psutil.cpu_percent(None)
        go.set()
        time.sleep(1.0)  # machine CPU over the middle of the window, without start and stop
        machine_pct = psutil.cpu_percent(interval=DURATION_S - 2.0)
        per = [results.get(timeout=CHILD_TIMEOUT_S) for _ in range(n)]
        for p in procs:
            p.join(30)
        errors = [r for r in per if "error" in r]
        if errors:
            raise RuntimeError(errors)
        rows = []
        for r in sorted(per, key=lambda r: r["index"]):
            counters = struct.unpack_from("<8Q", creators[r["index"]].bgr._shm.buf, COUNTERS_OFFSET)
            committed, skipped, decode_errors = counters[0], counters[5], counters[4]
            assert committed + skipped == r["offered"], (committed, skipped, r["offered"])
            rows.append(dict(r, committed=committed, skipped=skipped, decode_errors=decode_errors,
                             skip_rate=skipped / r["offered"]))
        return dict(size=size, fps=fps, processes=n, machine_cpu_pct_all_cores=machine_pct,
                    machine_cpu_cores_busy=machine_pct / 100 * os.cpu_count(),
                    camera_processes_cores=sum(r["process_cpu_pct"] for r in rows) / 100,
                    other_load_cores=machine_pct / 100 * os.cpu_count() - sum(r["process_cpu_pct"] for r in rows) / 100,
                    cameras=rows,
                    total_offered=sum(r["offered"] for r in rows), total_skipped=sum(r["skipped"] for r in rows),
                    skip_rate=sum(r["skipped"] for r in rows) / sum(r["offered"] for r in rows),
                    decode_thread_cpu_pct_median=sorted(r["decode_thread_cpu_pct"] for r in rows)[n // 2],
                    decode_thread_cpu_pct_max=max(r["decode_thread_cpu_pct"] for r in rows),
                    decode_ms_median_of_medians=sorted(r["decode_ms"]["median"] for r in rows)[n // 2],
                    decode_ms_p99_worst=max(r["decode_ms"]["p99"] for r in rows),
                    feeder_lateness_ms_p99_worst=max(r["feeder_lateness_ms"]["p99"] for r in rows),
                    feeder_lateness_ms_max=max(r["feeder_lateness_ms"]["max"] for r in rows))
    finally:
        for p in procs:
            if p.is_alive():
                p.terminate()
                p.join(10)
        for c in creators:
            c.close_and_unlink()


def main():
    out = dict(machine=common.machine_info(), duration_s=DURATION_S, cases=[])
    only = sys.argv[1:]  # optional case filter, e.g. "720p-60-4"
    for size, fps, n in CASES:
        if only and f"{size}-{fps}-{n}" not in only:
            continue
        case = run_case(size, fps, n)
        out["cases"].append(case)
        print(f"{size} {fps} fps x{n}: skip {case['skip_rate']:.4f} ({case['total_skipped']}/{case['total_offered']}), "
              f"decode thread {case['decode_thread_cpu_pct_median']:.1f} % (max {case['decode_thread_cpu_pct_max']:.1f}), "
              f"decode {case['decode_ms_median_of_medians']:.2f} ms med, {case['decode_ms_p99_worst']:.2f} p99 worst, "
              f"machine {case['machine_cpu_pct_all_cores']:.1f} % = {case['machine_cpu_cores_busy']:.2f} cores, "
              f"feeder late p99 {case['feeder_lateness_ms_p99_worst']:.2f} max {case['feeder_lateness_ms_max']:.2f} ms", flush=True)
        time.sleep(3)
    with open(os.path.join(HERE, "results", "m6.json" if not only else "m6_partial.json"), "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
