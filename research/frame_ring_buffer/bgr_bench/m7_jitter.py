"""M7 (specs/frame-ring.md 11.3): timing jitter of a capture-like thread while the decode thread runs.

Part 1, GIL tests: for each operation, the wall time of 2 threads that each do it `GIL_CALLS` times
against 1 thread that does it `GIL_CALLS` times. A ratio near 1 means the operation releases the GIL;
near 2 means it holds the GIL.

Part 2, jitter: one process. A capture-like thread, paced at 60 fps by sleep to an absolute
deadline, does a fixed job per tick: a JPEG ring write of a 150,000-byte payload (5.4). It records
how late each tick starts and how long the job takes. Cases: decode stage off; decode stage on, fed
a 720p or 1080p JPEG per tick through the waiting place (the put is timed apart). Writes
`results/m7.json`.
"""
import json
import os
import threading
import time
import zlib

import cv2
import numpy as np

import common

common.add_ring_path()
from skellycam.core.ipc.frame_ring import (  # noqa: E402
    DecodeInput, DecodeStage, FrameRingCreator, FrameRingWriter, PixelFormat)
from skellycam.core.ipc.frame_ring.layout import COUNTERS_OFFSET  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GIL_CALLS = 200
TICKS = 2400  # 40 s at 60 fps
FPS = 60
JOB_BYTES = 150_000


def wall_s(fn, threads):
    workers = [threading.Thread(target=lambda: [fn() for _ in range(GIL_CALLS)]) for _ in range(threads)]
    t0 = time.perf_counter()
    for w in workers:
        w.start()
    for w in workers:
        w.join(120)
    assert not any(w.is_alive() for w in workers)
    return time.perf_counter() - t0


def gil_tests():
    cv2.setNumThreads(1)
    big = np.random.default_rng(0).integers(0, 256, 6_000_000, dtype=np.uint8).tobytes()
    jpeg_1080 = common.jpegs("1080p", 1)[0]
    frame = cv2.imdecode(np.frombuffer(jpeg_1080, np.uint8), cv2.IMREAD_COLOR)
    flat = frame.reshape(-1)
    targets = {}  # one 6.2 MB target per thread, as each camera has its own slot; made once, outside the timing

    def target(key, make):
        if key not in targets:
            targets[key] = make()
        return targets[key]

    def slot_copy():  # W3 of 5.5: memoryview slice assignment of the flat array
        t = target(threading.get_ident(), lambda: memoryview(bytearray(flat.nbytes)))
        t[:] = flat

    def read_copy():  # R11 of 6.2 for BGR: a new bytearray from a slice of the block
        t = target(threading.get_ident(), lambda: memoryview(bytearray(flat.nbytes)))
        bytearray(t)

    def numpy_copyto():
        t = target(-threading.get_ident(), lambda: np.empty_like(frame))
        np.copyto(t, frame)

    def pure_python():  # control: holds the GIL
        s = 0
        for i in range(60_000):
            s += i

    ops = {"zlib.crc32 6 MB bytes": lambda: zlib.crc32(big), "zlib.crc32 1080p BGR ndarray": lambda: zlib.crc32(frame),
           "cv2.imdecode 1080p JPEG": lambda: cv2.imdecode(np.frombuffer(jpeg_1080, np.uint8), cv2.IMREAD_COLOR),
           "writer slot copy (memoryview slice assignment) 6.2 MB": slot_copy,
           "reader copy (bytearray of a memoryview) 6.2 MB": read_copy,
           "np.copyto 1080p BGR": numpy_copyto, "pure Python loop (control)": pure_python}
    out = {}
    for name, fn in ops.items():
        fn()
        one, two = wall_s(fn, 1), wall_s(fn, 2)
        out[name] = dict(one_thread_s=one, two_threads_s=two, ratio=two / one,
                         releases_gil=two / one < 1.4)
        print(f"GIL {name}: 1 thread {one:.3f} s, 2 threads {two:.3f} s, ratio {two / one:.2f}", flush=True)
    return out


def jitter_case(decode_size):
    cv2.setNumThreads(1)
    payload = common.jpegs("720p", 1)[0][:JOB_BYTES]
    feed = common.jpegs(decode_size, 8) if decode_size else None
    jw, jh = common.SIZES["720p"]
    jring = FrameRingCreator.create(camera_id="m7j", camera_index=95, pixel_format=PixelFormat.JPEG,
                                    width=jw, height=jh, fps_num=FPS, fps_den=1)
    bring = writer = bgr_writer = stage = None
    try:
        writer = FrameRingWriter.attach(jring.name)
        if decode_size:
            bw, bh = common.SIZES[decode_size]
            bring = FrameRingCreator.create(camera_id="m7b", camera_index=96, pixel_format=PixelFormat.BGR24,
                                            width=bw, height=bh, fps_num=FPS, fps_den=1)
            bgr_writer = FrameRingWriter.attach(bring.name)
            stage = DecodeStage(bgr_writer)
            stage.start()
        late, job, put = (np.zeros(TICKS, np.int64) for _ in range(3))

        def capture():
            period = 1e9 / FPS
            start = time.perf_counter_ns() + 50_000_000
            for k in range(TICKS):
                deadline = start + int(k * period)
                now = time.perf_counter_ns()
                if deadline > now:
                    time.sleep((deadline - now) / 1e9)
                t0 = time.perf_counter_ns()
                writer.write(payload, frame_number=k, arrival_ns=t0, sample_ns=t0, source_frame_number=k, flags=0,
                             rotation_cw_deg=0)
                t1 = time.perf_counter_ns()
                if stage:
                    stage.waiting_place.put(DecodeInput(payload=feed[k % 8], source="JPEG", frame_number=k,
                                                        arrival_ns=t0, sample_ns=t0, source_frame_number=k, flags=0,
                                                        rotation_cw_deg=0))
                late[k], job[k], put[k] = t0 - deadline, t1 - t0, time.perf_counter_ns() - t1

        thread = threading.Thread(target=capture, name="capture")
        thread.start()
        thread.join(TICKS / FPS + 60)
        assert not thread.is_alive(), "capture thread did not finish"
        result = dict(decode=decode_size or "off", lateness=common.stats_ms(late), job=common.stats_ms(job),
                      ticks_late_over_1ms=int((late > 1_000_000).sum()), ticks_late_over_2ms=int((late > 2_000_000).sum()))
        if stage:
            stage.stop()
            counters = np.frombuffer(bytes(bring._shm.buf[COUNTERS_OFFSET:COUNTERS_OFFSET + 64]), "<u8")
            result.update(put=common.stats_ms(put), bgr_committed=int(counters[0]), bgr_skipped=int(counters[5]))
        return result
    finally:
        if stage and stage._thread.is_alive():  # a failure before the stop above
            stage.stop()
        for h in (bgr_writer, writer):
            if h is not None:
                h.close()
        for c in (bring, jring):
            if c is not None:
                c.close_and_unlink()


def main():
    out = dict(machine=common.machine_info(), switch_interval_s=__import__("sys").getswitchinterval(),
               gil=gil_tests(), jitter=[])
    for size in (None, "720p", "1080p"):
        r = jitter_case(size)
        out["jitter"].append(r)
        print(json.dumps(r), flush=True)
        time.sleep(2)
    with open(os.path.join(HERE, "results", "m7.json"), "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
