"""V5: cross-process contention on lock=True multiprocessing.Value reads in CameraOrchestrator.should_grab_by_id.
N spinner processes each call orchestrator.should_grab_by_id(own_id) in a tight loop for DURATION s
(the camera loop does should_grab_by_id + wait_10us when it cannot grab; here we measure both the no-sleep
worst case and the with-sleep case). Run from C:/Users/Dom/GitHub/freemocap/skellycam:
   .venv/Scripts/python.exe -u <this file>
"""
import multiprocessing as mp, multiprocessing.queues, os, sys, time  # queues import: type_overloads.py uses multiprocessing.queues without importing it

DURATION = 2.0

def spinner(orch, cam_id, sleep_s, out_q, start_evt):
    start_evt.wait()
    n = 0
    t0 = time.perf_counter_ns(); end = t0 + int(DURATION * 1e9)
    busy = 0
    while True:
        a = time.perf_counter_ns()
        if a >= end:
            break
        orch.should_grab_by_id(cam_id)
        busy += time.perf_counter_ns() - a
        n += 1
        if sleep_s:
            time.sleep(sleep_s)
    out_q.put((cam_id, n, busy / n))

def run(n_procs, sleep_s):
    from skellycam.core.camera_group.camera_status import CameraStatus
    from skellycam.core.camera_group.camera_orchestrator import CameraOrchestrator
    statuses = {f"cam{i}": CameraStatus() for i in range(5)}
    for s in statuses.values():
        s.connected.value = True; s.frame_count.value = 10
    orch = CameraOrchestrator.from_statuses(statuses)
    q = mp.Queue(); ev = mp.Event()
    ps = [mp.Process(target=spinner, args=(orch, f"cam{i}", sleep_s, q, ev)) for i in range(n_procs)]
    for p in ps: p.start()
    time.sleep(8.0)  # let spawn imports finish
    ev.set()
    res = [q.get(timeout=60) for _ in ps]
    for p in ps: p.join(10)
    mean_ns = sum(r[2] for r in res) / len(res)
    print(f"V5 procs={n_procs} sleep_between={sleep_s}: mean should_grab_by_id = {mean_ns/1e3:.1f} us "
          f"(per-proc: {', '.join(f'{r[2]/1e3:.1f}' for r in res)}) calls/proc ~{int(sum(r[1] for r in res)/len(res))}")

if __name__ == "__main__":
    for n, s in ((1, 0), (5, 0), (5, 1e-5)):
        run(n, s)
    sys.stdout.flush(); os._exit(0)
