r"""Repeat the pure-Python GIL control from bench_python_hotpaths.py section G, 3 trials, to characterise noise
(i7-14700K has P- and E-cores; a single thread may be scheduled on either).
Run: C:\Users\Dom\GitHub\freemocap\skellycam\.venv\Scripts\python.exe bench_gil_control.py > bench_gil_control.out.txt"""
import threading, time
def py():
    s = 0
    for j in range(10000):
        s += j
    return s
for trial in range(3):
    line = f"trial {trial}:"
    base = None
    for n in (1, 2, 5):
        counts = [0]*n; stop = threading.Event()
        def run(k):
            while not stop.is_set():
                py(); counts[k] += 1
        ths = [threading.Thread(target=run, args=(k,)) for k in range(n)]
        [t.start() for t in ths]; time.sleep(1.5); stop.set(); [t.join() for t in ths]
        r = sum(counts)/1.5; base = base or r
        line += f"  {n}T {r:8.1f} ops/s ({r/base:4.2f}x)"
    print(line, flush=True)
t0 = time.perf_counter(); [py() for _ in range(2000)]; print(f"single-thread reference: {2000/(time.perf_counter()-t0):.1f} ops/s")
