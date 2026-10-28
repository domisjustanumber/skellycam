"""
Micro-benchmarks for the "would C++ help?" study.
Run:  C:\\Users\\Dom\\GitHub\\freemocap\\skellycam\\.venv\\Scripts\\python.exe bench_python_hotpaths.py > bench_python_hotpaths.out.txt
Measures (on SkellyCam's own classes where relevant, no source modified):
  A memcpy bandwidth (np.copyto) for 720p/1080p BGR frames, cache-cold ring of slots
  B SharedMemoryRingBuffer.put_data (real FRAME dtype) vs raw np.copyto into a slot
  C SharedMemoryRingBuffer.get_data_by_index cost
  D SharedMemoryNumber.value get/set cost (pure Python per-call overhead)
  E nested recarray timestamp write cost (as in opencv_camera_loop.initialize_frame_recarray)
  F RGB->BGR swap as done in openpnp_capture.camera.capture_frame_into vs cv2.cvtColor
  G GIL scaling: N threads doing np.copyto / cv2.cvtColor / cv2.imencode / pure Python
  H cv2.imencode JPEG and cv2.VideoWriter MJPG per-frame cost
"""
import os
import sys
import time
import threading
import tempfile
import statistics as st

import numpy as np
import cv2

from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import SharedMemoryRingBuffer
from skellycam.core.ipc.shared_memory.shared_memory_number import SharedMemoryNumber
from skellycam.core.types.numpy_record_dtypes import FRAME_METADATA_DTYPE

SIZES = {"720p": (720, 1280, 3), "1080p": (1080, 1920, 3)}
N_SLOTS_COLD = 160  # 160 * 2.76MB = 442MB; 160*6.2MB = 995MB  -> far beyond 33MB L3


def frame_dtype(shape):
    return np.dtype([("frame_metadata", FRAME_METADATA_DTYPE), ("image", np.uint8, shape)], align=True)


def timeit(fn, n, warm=5):
    for _ in range(warm):
        fn()
    ts = []
    for _ in range(n):
        t0 = time.perf_counter_ns()
        fn()
        ts.append(time.perf_counter_ns() - t0)
    return ts


def summarize(name, ts_ns, nbytes=None):
    med = st.median(ts_ns) / 1e3
    p99 = sorted(ts_ns)[int(len(ts_ns) * 0.99) - 1] / 1e3
    s = f"{name:<70s} median {med:9.1f} us   p99 {p99:9.1f} us"
    if nbytes:
        s += f"   ~{nbytes / (st.median(ts_ns) / 1e9) / 1e9:6.2f} GB/s (bytes copied / time)"
    print(s, flush=True)
    return med


def section(t):
    print("\n=== " + t + " ===", flush=True)


def main():
    print(sys.version)
    print("numpy", np.__version__, "cv2", cv2.__version__, "cv2 threads", cv2.getNumThreads())
    print("cpu_count", os.cpu_count())

    section("A. memcpy bandwidth via np.copyto (cache-cold destination ring, hot source)")
    for label, shape in SIZES.items():
        nb = int(np.prod(shape))
        src = np.random.randint(0, 255, shape, dtype=np.uint8)
        ring = np.zeros((N_SLOTS_COLD,) + shape, dtype=np.uint8)
        i = [0]

        def f():
            np.copyto(ring[i[0] % N_SLOTS_COLD], src)
            i[0] += 1
        summarize(f"np.copyto {label} ({nb} B) into cold ring slot", timeit(f, 400), nb)
        # cold source AND cold dest (read from one ring, write to another region)
        half = N_SLOTS_COLD // 2

        def g():
            k = i[0] % half
            np.copyto(ring[k], ring[k + half])
            i[0] += 1
        summarize(f"np.copyto {label} cold src -> cold dst", timeit(g, 400), nb)
        hot_dst = np.empty_like(src)
        summarize(f"np.copyto {label} hot src -> hot dst (fits L3)", timeit(lambda: np.copyto(hot_dst, src), 400), nb)
        del ring

    big = np.ones(1024 ** 3, dtype=np.uint8)
    big2 = np.empty_like(big)
    summarize("np.copyto 1 GiB (single thread)", timeit(lambda: np.copyto(big2, big), 5, warm=1), big.nbytes)
    del big, big2

    section("B/C. SkellyCam SharedMemoryRingBuffer put_data / get_data_by_index (real frame dtype)")
    for label, shape in SIZES.items():
        dt = frame_dtype(shape)
        example = np.recarray(1, dtype=dt)
        example.image[0] = np.random.randint(0, 255, shape, dtype=np.uint8)
        ring = SharedMemoryRingBuffer.create(example_data=example, read_only=False)
        L = ring.ring_buffer_length
        print(f"{label}: itemsize {dt.itemsize} B, ring length {L} slots (1 GiB allocation)")
        summarize(f"ring.put_data {label} (copy(data) + slot assign + index update)",
                  timeit(lambda: ring.put_data(example, overwrite_allowed=True), 400), dt.itemsize)
        slot = [0]

        def raw():
            k = slot[0] % L
            np.copyto(ring.ring_shm.buffer[k:k + 1], example)
            slot[0] += 1
        summarize(f"raw np.copyto(record slice) into shm slot {label}", timeit(raw, 400), dt.itemsize)

        def assign_no_copy():
            ring.ring_shm.buffer[slot[0] % L] = example
            slot[0] += 1
        summarize(f"buffer[idx] = data (put_data line 132 minus copy()) {label}",
                  timeit(assign_no_copy, 400), dt.itemsize)

        def assign_record():
            ring.ring_shm.buffer[slot[0] % L] = example[0]
            slot[0] += 1
        summarize(f"buffer[idx] = data[0] (record scalar assign) {label}",
                  timeit(assign_record, 400), dt.itemsize)

        def raw_img():
            np.copyto(ring.ring_shm.buffer.image[slot[0] % L], example.image[0])
            slot[0] += 1
        summarize(f"raw np.copyto(image only) into shm slot {label}", timeit(raw_img, 400), int(np.prod(shape)))
        summarize(f"copy.copy(recarray) alone {label}",
                  timeit(lambda: __import__('copy').copy(example), 400), dt.itemsize)
        out = np.recarray(1, dtype=dt)
        head = ring.last_written_index.value
        summarize(f"ring.get_data_by_index {label} into preallocated recarray",
                  timeit(lambda: ring.get_data_by_index(head - 1, out), 400), dt.itemsize)
        summarize(f"zero-copy view ring.ring_shm.buffer[idx] (no copy) {label}",
                  timeit(lambda: ring.ring_shm.buffer[(head - 1) % L], 2000))
        ring.close_and_unlink()

    section("D. SharedMemoryNumber.value (index counters used on every put/get)")
    n = SharedMemoryNumber.create(read_only=False, initial_value=0)
    summarize("SharedMemoryNumber.value read", timeit(lambda: n.value, 20000))

    def setv():
        n.value = 5
    summarize("SharedMemoryNumber.value write", timeit(setv, 20000))
    raw_i64 = np.ndarray((1,), dtype=np.int64, buffer=n.shm.buf)
    summarize("raw int64 view read  raw_i64[0]", timeit(lambda: raw_i64[0], 20000))

    def rawset():
        raw_i64[0] = 5
    summarize("raw int64 view write raw_i64[0]=5", timeit(rawset, 20000))
    del raw_i64
    n.close_and_unlink() if hasattr(n, "close_and_unlink") else n.unlink_and_close()

    section("E. nested recarray field write (per-timestamp, as in camera loop)")
    fr = np.recarray(1, dtype=frame_dtype(SIZES["720p"]))

    def ts_write():
        fr.frame_metadata.timestamps.pre_frame_grab_ns[0] = 123
    summarize("frame_rec_array.frame_metadata.timestamps.X[0] = v", timeit(ts_write, 20000))
    ts_view = fr.frame_metadata.timestamps  # cached view

    def ts_write_cached():
        ts_view["pre_frame_grab_ns"][0] = 123
    summarize("cached timestamps view ['X'][0] = v", timeit(ts_write_cached, 20000))
    summarize("time.perf_counter_ns()", timeit(time.perf_counter_ns, 20000))

    section("F. RGB->BGR swap (openpnp_capture.camera.capture_frame_into lines 213-216) vs cv2")
    for label, shape in SIZES.items():
        buf = np.random.randint(0, 255, shape, dtype=np.uint8)

        def openpnp_swap():
            ch0 = buf[:, :, 0].copy()
            buf[:, :, 0] = buf[:, :, 2]
            buf[:, :, 2] = ch0
        summarize(f"openpnp-python numpy channel swap {label}", timeit(openpnp_swap, 200))
        summarize(f"cv2.cvtColor(dst=buf) in-place RGB2BGR {label}",
                  timeit(lambda: cv2.cvtColor(buf, cv2.COLOR_RGB2BGR, dst=buf), 200))

    section("G. GIL scaling: aggregate throughput with N threads (1 thread = 1.0x)")
    shape = SIZES["1080p"]

    def make_worker(kind):
        src = np.random.randint(0, 255, shape, dtype=np.uint8)
        dst = np.empty_like(src)
        if kind == "np.copyto 1080p":
            return lambda: np.copyto(dst, src)
        if kind == "cv2.cvtColor 1080p BGR2RGB":
            return lambda: cv2.cvtColor(src, cv2.COLOR_BGR2RGB, dst=dst)
        if kind == "cv2.imencode jpg 1080p":
            return lambda: cv2.imencode(".jpg", src, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if kind == "pure-Python loop (10k iters)":
            def py():
                s = 0
                for j in range(10000):
                    s += j
                return s
            return py
        if kind == "SharedMemoryNumber.value x100":
            num = SharedMemoryNumber.create(read_only=False, initial_value=0)
            def nv():
                for _ in range(100):
                    num.value
            return nv
        raise ValueError(kind)

    old = cv2.getNumThreads()
    cv2.setNumThreads(1)  # isolate GIL effect from OpenCV's internal parallelism
    for kind in ["np.copyto 1080p", "cv2.cvtColor 1080p BGR2RGB", "cv2.imencode jpg 1080p",
                 "pure-Python loop (10k iters)", "SharedMemoryNumber.value x100"]:
        base = None
        line = f"{kind:<34s}"
        for nthreads in (1, 2, 5):
            workers = [make_worker(kind) for _ in range(nthreads)]
            counts = [0] * nthreads
            stop = threading.Event()

            def run(k):
                w = workers[k]
                while not stop.is_set():
                    w()
                    counts[k] += 1
            ths = [threading.Thread(target=run, args=(k,)) for k in range(nthreads)]
            for t in ths:
                t.start()
            time.sleep(1.5)
            stop.set()
            for t in ths:
                t.join()
            rate = sum(counts) / 1.5
            if base is None:
                base = rate
            line += f"  {nthreads}T: {rate:9.1f} ops/s ({rate / base:4.2f}x)"
        print(line, flush=True)
    cv2.setNumThreads(old)

    section("H. encode cost per frame (cv2 default threads)")
    for label, shape in SIZES.items():
        img = np.random.randint(0, 255, shape, dtype=np.uint8)
        img = cv2.GaussianBlur(img, (15, 15), 5)  # make it a bit more natural / compressible
        summarize(f"cv2.imencode .jpg q95 {label}",
                  timeit(lambda: cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95]), 100))
        path = os.path.join(tempfile.gettempdir(), f"bench_{label}.avi")
        vw = cv2.VideoWriter(path, cv2.VideoWriter.fourcc(*"MJPG"), 60, (shape[1], shape[0]))
        if vw.isOpened():
            summarize(f"cv2.VideoWriter MJPG write {label}", timeit(lambda: vw.write(img), 100))
            vw.release()
            print(f"   file size for 105 frames: {os.path.getsize(path) / 1e6:.1f} MB")
            os.remove(path)
        else:
            print(f"   VideoWriter MJPG not available for {label}")


if __name__ == "__main__":
    main()
