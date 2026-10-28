r"""Actual duration of time.sleep() calls used by SkellyCam wait_functions (wait_10us/100us/1ms) on this Windows box.
Run: C:\Users\Dom\GitHub\freemocap\skellycam\.venv\Scripts\python.exe bench_sleep.py > bench_sleep.out.txt"""
import time, statistics as st
for req in (1e-6, 1e-5, 1e-4, 1e-3):
    ts = []
    for _ in range(500):
        t0 = time.perf_counter_ns(); time.sleep(req); ts.append(time.perf_counter_ns() - t0)
    ts.sort()
    print(f"time.sleep({req:g}) -> median {st.median(ts)/1e3:8.1f} us  p10 {ts[50]/1e3:8.1f} us  p99 {ts[494]/1e3:8.1f} us")
