"""
Cost of SkellyCam's SharedMemoryRingBuffer.put_data (which does `buffer[slot] = copy(data)`, i.e. allocate+copy then
copy into shm) versus a single np.copyto into the slot, for one 1080p / 720p BGR frame record.
Uses the SkellyCam checkout's own class unmodified (imported from the repo path).

Run:
    cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam
    .venv\\Scripts\\python.exe -I <scratch>\\bp_bench\\bench_skellycam_put_data.py <out_dir>
"""
import json
import os
import statistics
import sys
import time

REPO = r"C:\Users\Dom\GitHub\freemocap\skellycam"
sys.path.insert(0, REPO)
import numpy as np  # noqa: E402
from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import SharedMemoryRingBuffer  # noqa: E402


def t(fn, n=300):
    for _ in range(10):
        fn()
    ts = []
    for _ in range(n):
        a = time.perf_counter(); fn(); ts.append(time.perf_counter() - a)
    return {"median_ms": statistics.median(ts) * 1e3, "p99_ms": sorted(ts)[int(0.99 * (n - 1))] * 1e3}


out = sys.argv[1] if len(sys.argv) > 1 else "."
res = {}
for name, (h, w) in {"720p": (720, 1280), "1080p": (1080, 1920)}.items():
    dt = np.dtype([("frame_number", np.int64), ("image", np.uint8, (h, w, 3))])
    rec = np.recarray(1, dtype=dt)
    rec.image[0] = np.random.default_rng(0).integers(0, 255, (h, w, 3), dtype=np.uint8)
    rb = SharedMemoryRingBuffer.create(example_data=rec, read_only=False, ring_buffer_length=64)
    try:
        buf = rb.ring_shm.buffer
        k = [0]

        def single_copyto():
            np.copyto(buf[k[0] % 64:k[0] % 64 + 1], rec)
            k[0] += 1

        dst = np.recarray(1, dtype=dt)
        res[name] = {
            "skellycam_put_data_overwrite": t(lambda: rb.put_data(rec, overwrite_allowed=True)),
            "single_np_copyto_into_slot": t(single_copyto),
            "skellycam_get_latest_data_into_prealloc": t(lambda: rb.get_latest_data(dst)),
            "ring_slots_if_default_1GiB": (1024 ** 3) // dt.itemsize,
            "seconds_of_history_at_60fps_default_1GiB": (1024 ** 3) // dt.itemsize / 60,
            "itemsize": dt.itemsize,
        }
    finally:
        rb.close_and_unlink()
print(json.dumps(res, indent=2))
with open(os.path.join(out, "skellycam_put_data.json"), "w") as f:
    json.dump(res, f, indent=2)
