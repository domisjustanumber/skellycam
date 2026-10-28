r"""Verifier v5: (a) does np.rec.array(ndarray, dtype=...) copy (as used by SharedMemoryElement.retrieve_data)?
(b) time.sleep(1e-5) / time.sleep(1e-3) resolution on this machine (wait_10us / wait_1ms).
Run: C:\Users\Dom\GitHub\freemocap\skellycam\.venv\Scripts\python.exe <this file>
"""
import time
import numpy as np
dt = np.dtype([("value", np.int64)])
a = np.recarray((1,), dtype=dt)
r = np.rec.array(a, dtype=dt)
print("np.rec.array(ndarray) shares memory with input?", np.shares_memory(a, r))
for name, s, n in (("sleep(1e-5)", 1e-5, 2000), ("sleep(1e-3)", 1e-3, 500)):
    ts = []
    for _ in range(n):
        t0 = time.perf_counter_ns(); time.sleep(s); ts.append(time.perf_counter_ns() - t0)
    x = np.array(ts) / 1e3
    print(f"{name}: median {np.median(x):.1f} us, p95 {np.percentile(x, 95):.1f} us")
