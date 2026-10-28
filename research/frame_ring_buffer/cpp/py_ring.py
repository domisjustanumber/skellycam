"""Python twin of build/ringbench.exe: the SAME ring workloads, configs and frame counts, in Python.

  python py_ring.py write <64x64|720p|1080p> <ncams> <impl> <run_s> <out.json>
  python py_ring.py spsc  <64x64|720p|1080p> <ncams> <impl> <paced_fps|0> <run_s> <out.json>

impl:
  sk_head        the REAL SkellyCam ring (HEAD 23ccbf20): CameraGroupSharedMemory.create(read_only=True) in the parent,
                 CameraSharedMemoryRingBuffer.recreate(read_only=False) in each spawned process, put_frame() (copy.copy +
                 slot assignment, ring_buffer_shared_memory.py L118-133). write mode: put_frame(overwrite=True), exactly
                 baseline/bench_a_write.py "production". spsc mode: put_frame(overwrite=False), retried after the real
                 overwrite check raises (lossless "block" policy), and the reader process calls get_next_data(reused
                 recarray) when new_frame_available (L135-158).
  py_seq         pure numpy seqlock ring with the byte-identical layout of ring.hpp (4 KiB-aligned slots, seq[] array,
                 header head/cursor/done): one np.copyto per publish / read. This is "Python with the copy and control-plane
                 fixes", the prototypes' SeqRing design.
  hybrid         the C++ ring from build/cppring.cp312-win_amd64.pyd (pybind11): Python loop, native publish/read
                 (GIL released around the memcpy). Must run with the .venv-bench interpreter (pybind11 lives there).
  hybrid_ctypes  write mode only: the same native publish called through ctypes (cr_publish C export).

Rules identical to the C++ side (see ringbench.cpp): one ring per camera with L = 1 GiB // record bytes; the record is
632 B metadata + HxWx3 image; stamps metadata[0:8]=k, metadata[8:16]=publish perf_counter_ns, image[0:8]=image[-8:]=k
(written outside the timed region in write mode); write mode: one timed first lap then run_s unthrottled; spsc mode:
untimed warm-up lap in writer (touch every slot) and reader (copy every slot out), then paced (run_s*fps frames) or
unthrottled for run_s; the reader copies EVERY frame into a private buffer and verifies the stamps; a failed poll /
blocked writer does time.sleep(0) (CPython 3.12 calls Sleep(0) for that on Windows; C++ calls Sleep(0)).
Multi-process: multiprocessing spawn, as SkellyCam on Windows.

Run from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam:
  .venv\\Scripts\\python.exe research\\frame_ring_buffer\\cpp\\py_ring.py write 1080p 5 sk_head 10 -
  research\\frame_ring_buffer\\.venv-bench\\Scripts\\python.exe research\\frame_ring_buffer\\cpp\\py_ring.py spsc 1080p 5 hybrid 60 10 -
"""
from __future__ import annotations

import json
import multiprocessing as mp
import multiprocessing.queues  # noqa: F401  skellycam type_overloads.py L23 workaround (baseline README "Incidental reproduction")
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASELINE = HERE.parent / "baseline"
BUILD = HERE / "build"
META = 632
HDR = 4096
ONE_GIB = 1 << 30


def round4k(n: int) -> int:
    return (n + 4095) // 4096 * 4096


def parse_size(s: str):
    if s == "720p":
        return 720, 1280
    if s == "1080p":
        return 1080, 1920
    w, h = s.split("x")
    return int(h), int(w)


def stats_ms(samples_ns) -> dict:
    a = np.asarray(samples_ns, dtype=np.float64) / 1e6
    if a.size == 0:
        return {"n": 0, "median_ms": None, "mean_ms": None, "p99_ms": None, "min_ms": None, "max_ms": None}
    return {"n": int(a.size), "median_ms": float(np.median(a)), "mean_ms": float(a.mean()),
            "p99_ms": float(np.percentile(a, 99)), "min_ms": float(a.min()), "max_ms": float(a.max())}


def sleep_until(t_ns: int):
    """Same pacing primitive as proto_common.sleep_until / ring.hpp sleep_until_ns: coarse sleep, then spin."""
    pc = time.perf_counter_ns
    while True:
        rem = t_ns - pc()
        if rem <= 0:
            return
        if rem > 2_000_000:
            time.sleep((rem - 1_500_000) / 1e9)


# ------------------------------------------------------------------------------------------------ numpy seqlock ring
class NpRing:
    """Byte-identical layout to ring.hpp (aligned variant)."""

    def __init__(self, shm, h, w):
        self.shm = shm
        self.rb = META + h * w * 3
        self.L = ONE_GIB // self.rb
        self.stride = round4k(self.rb)
        buf = shm.buf
        self.hdr = np.ndarray((HDR // 8,), np.int64, buf, 0)
        self.seq = np.ndarray((self.L,), np.int64, buf, HDR)
        self.payload = np.ndarray((self.L, self.stride), np.uint8, buf, HDR + round4k(self.L * 8))
        self.slots = self.payload[:, :self.rb]

    @staticmethod
    def total(h, w):
        rb = META + h * w * 3
        L = ONE_GIB // rb
        return HDR + round4k(L * 8) + L * round4k(rb)

    def init(self):
        self.hdr[0] = -1   # head
        self.hdr[8] = -1   # cursor (byte 64)
        self.hdr[16] = -1  # done (byte 128)
        self.seq[:] = 0

    def close(self):
        self.hdr = self.seq = self.payload = self.slots = None
        self.shm.close()


# ------------------------------------------------------------------------------------------------ helpers
def make_record_u8(h, w, cam):
    rb = META + h * w * 3
    r = np.full(rb, cam, np.uint8)
    r[:META] = 0
    return r


class Stamper:
    def __init__(self, raw_u8: np.ndarray):
        rb = raw_u8.size
        self.k0 = raw_u8[0:8].view(np.int64)
        self.t = raw_u8[8:16].view(np.int64)
        self.k1 = raw_u8[META:META + 8].view(np.int64)
        self.k2 = raw_u8[rb - 8:rb].view(np.int64)

    def stamp(self, k, t_ns):
        self.k0[0] = k
        self.t[0] = t_ns
        self.k1[0] = k
        self.k2[0] = k


def check_stamp(raw_u8, k) -> bool:
    rb = raw_u8.size
    return (int(raw_u8[0:8].view(np.int64)[0]) == k and int(raw_u8[META:META + 8].view(np.int64)[0]) == k
            and int(raw_u8[rb - 8:rb].view(np.int64)[0]) == k)


def pub_ns_of(raw_u8) -> int:
    return int(raw_u8[8:16].view(np.int64)[0])


def import_cppring():
    sys.path.insert(0, str(BUILD))
    import cppring  # noqa: E402
    return cppring


# ------------------------------------------------------------------------------------------------ write-only (a_write shape)
def write_child(impl, cam, h, w, handle, run_s, ready_q, start_evt, result_q):
    pc = time.perf_counter_ns
    if impl == "sk_head":
        sys.path.insert(0, str(BASELINE))
        import bench_common as bc
        from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
        ring = CameraSharedMemoryRingBuffer.recreate(dto=handle, read_only=False)
        fr = bc.make_frame_recarray(bc.make_config(cam, h, w))
        raw = fr.view(np.uint8).reshape(-1)
        L = ring.ring_buffer_length

        def put(k):
            ring.put_frame(frame_rec_array=fr, overwrite=True)

        def last_ok(k):
            last = ring.last_written_index.value
            return check_stamp(ring.ring_shm.buffer[last % L:last % L + 1].view(np.uint8).reshape(-1), k)
    elif impl == "py_seq":
        from multiprocessing import shared_memory
        shm = shared_memory.SharedMemory(name=handle)
        ring = NpRing(shm, h, w)
        raw = make_record_u8(h, w, cam)
        L, seq, hdr, slots = ring.L, ring.seq, ring.hdr, ring.slots

        def put(k):
            s = k % L
            seq[s] = 2 * k + 1
            np.copyto(slots[s], raw)
            seq[s] = 2 * k + 2
            hdr[0] = k

        def last_ok(k):
            return check_stamp(slots[int(hdr[0]) % L], k)
    else:  # hybrid / hybrid_ctypes
        cppring = import_cppring()
        ring = cppring.Ring(handle, h, w, True, False)
        raw = make_record_u8(h, w, cam)
        L = ring.L
        if impl == "hybrid":
            put = lambda k: ring.publish(k, raw)  # noqa: E731
        else:
            import ctypes
            dll = ctypes.CDLL(str(BUILD / "cppring.cp312-win_amd64.pyd"))
            f = dll.cr_publish
            f.argtypes = [ctypes.c_void_p, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_void_p]
            f.restype = None
            base, rb, stride, src = ring.base_addr, ring.record_bytes, ring.stride, raw.ctypes.data
            put = lambda k: f(base, L, rb, stride, k, src)  # noqa: E731

        def last_ok(k):
            return check_stamp(np.frombuffer(ring.slot_view(ring.head()), np.uint8), k)
    st = Stamper(raw)
    first = []
    k = -1
    for _ in range(L):
        k += 1
        st.stamp(k, pc())
        t0 = pc(); put(k); first.append(pc() - t0)
    ready_q.put(cam)
    start_evt.wait()
    lat = []
    cpu0 = time.process_time()
    t_start = pc()
    deadline = t_start + int(run_s * 1e9)
    n = 0
    while True:
        k += 1
        st.stamp(k, pc())
        t0 = pc(); put(k); t1 = pc()
        lat.append(t1 - t0)
        n += 1
        if t1 >= deadline:
            break
    elapsed = (pc() - t_start) / 1e9
    cpu = time.process_time() - cpu0
    result_q.put(dict(role="writer", cam=cam, n=n, elapsed_s=elapsed, fps=n / elapsed, cpu_s=cpu, cpu_ms_per_frame=1e3 * cpu / n,
                      verified=int(last_ok(k)), first_lap=stats_ms(first), op=stats_ms(lat), e2e=stats_ms([]),
                      blocked_ns=0, blocked_events=0, torn=0, gaps=0, seq_rejects=0))


# ------------------------------------------------------------------------------------------------ SPSC
def spsc_writer(impl, cam, h, w, handle, paced, run_s, ready_q, start_evt, start_ns, done_val, result_q):
    pc = time.perf_counter_ns
    sleep0 = time.sleep
    if impl == "sk_head":
        sys.path.insert(0, str(BASELINE))
        import bench_common as bc
        from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
        ring = CameraSharedMemoryRingBuffer.recreate(dto=handle, read_only=False)
        fr = bc.make_frame_recarray(bc.make_config(cam, h, w))
        raw = fr.view(np.uint8).reshape(-1)
        L = ring.ring_buffer_length
        buf = ring.ring_shm.buffer
        for i in range(L):  # warm-up lap: touch every slot (no index change)
            buf[i] = fr[0]

        def try_put(k):
            try:
                ring.put_frame(frame_rec_array=fr, overwrite=False)
                return True
            except ValueError:
                return False

        def publish(k):
            return try_put(k)
    elif impl == "py_seq":
        from multiprocessing import shared_memory
        shm = shared_memory.SharedMemory(name=handle)
        ring = NpRing(shm, h, w)
        raw = make_record_u8(h, w, cam)
        L, seq, hdr, slots = ring.L, ring.seq, ring.hdr, ring.slots
        for i in range(L):
            np.copyto(slots[i], raw)

        def publish(k):
            if hdr[8] < k - L:  # gating: read_cursor >= k - L
                return False
            s = k % L
            seq[s] = 2 * k + 1
            np.copyto(slots[s], raw)
            seq[s] = 2 * k + 2
            hdr[0] = k
            return True
    else:
        cppring = import_cppring()
        ring = cppring.Ring(handle, h, w, True, False)
        raw = make_record_u8(h, w, cam)
        L = ring.L
        for i in range(L):  # warm-up lap: touch every slot through a writable zero-copy view (no publish)
            np.copyto(np.frombuffer(ring.slot_view(i), np.uint8), raw)

        def publish(k):
            if not ring.can_write(k):
                return False
            ring.publish(k, raw)
            return True
    st = Stamper(raw)
    lat = []
    ready_q.put(("w", cam))
    start_evt.wait()
    cpu0 = time.process_time()
    t_start = start_ns.value
    period = int(1e9 / paced) if paced > 0 else 0
    n_target = int(run_s * paced) if paced > 0 else 1 << 62
    deadline = (1 << 62) if paced > 0 else t_start + int(run_s * 1e9)
    blocked_ns = blocked_events = 0
    k = 0
    while k < n_target:
        if period:
            sleep_until(t_start + (k + 1) * period)
        t0 = pc()
        st.stamp(k, t0)
        if not publish(k):
            b0 = t0
            blocked_events += 1
            while True:
                sleep0(0)
                t0 = pc()
                st.stamp(k, t0)
                if publish(k):
                    break
            blocked_ns += t0 - b0
        t1 = pc()
        lat.append(t1 - t0)
        k += 1
        if t1 >= deadline:
            break
    elapsed = (pc() - t_start) / 1e9
    cpu = time.process_time() - cpu0
    done_val.value = k
    if impl in ("py_seq",):
        ring.hdr[16] = k
    elif impl in ("hybrid",):
        ring.set_done(k)
    result_q.put(dict(role="writer", cam=cam, n=k, elapsed_s=elapsed, fps=k / elapsed, cpu_s=cpu, cpu_ms_per_frame=1e3 * cpu / max(k, 1),
                      op=stats_ms(lat), e2e=stats_ms([]), first_lap=stats_ms([]), blocked_ns=blocked_ns, blocked_events=blocked_events,
                      torn=0, gaps=0, seq_rejects=0, verified=1))


def spsc_reader(impl, cam, h, w, handle, ready_q, start_evt, start_ns, done_val, result_q):
    pc = time.perf_counter_ns
    sleep0 = time.sleep
    rb = META + h * w * 3
    if impl == "sk_head":
        sys.path.insert(0, str(BASELINE))
        import bench_common as bc
        from skellycam.core.ipc.shared_memory.camera_shared_memory_ring_buffer import CameraSharedMemoryRingBuffer
        ring = CameraSharedMemoryRingBuffer.recreate(dto=handle, read_only=False)
        rec = bc.make_frame_recarray(bc.make_config(cam, h, w))
        dst = rec.view(np.uint8).reshape(-1)
        L = ring.ring_buffer_length
        buf = ring.ring_shm.buffer
        for i in range(L):  # warm-up lap: copy every slot out (page faults in this process)
            np.copyto(rec, buf[i:i + 1])

        def available(k):
            return ring.new_frame_available

        def read(k):
            ring.get_next_data(rec)
            return 0
    elif impl == "py_seq":
        from multiprocessing import shared_memory
        shm = shared_memory.SharedMemory(name=handle)
        ring = NpRing(shm, h, w)
        L, seq, hdr, slots = ring.L, ring.seq, ring.hdr, ring.slots
        dst = np.zeros(rb, np.uint8)
        for i in range(L):
            np.copyto(dst, slots[i])

        def available(k):
            return hdr[0] >= k

        def read(k):
            s = k % L
            s1 = seq[s]
            if s1 != 2 * k + 2:
                return 1
            np.copyto(dst, slots[s])
            if seq[s] != s1:
                return 1
            hdr[8] = k
            return 0
    else:
        cppring = import_cppring()
        ring = cppring.Ring(handle, h, w, True, False)
        L = ring.L
        dst = np.zeros(rb, np.uint8)
        for i in range(L):
            np.copyto(dst, np.frombuffer(ring.slot_view(i), np.uint8))

        def available(k):
            return ring.head() >= k

        def read(k):
            rc = ring.read(k, dst)
            if rc == 0:
                ring.set_cursor(k)
            return rc
    lat, e2e = [], []
    ready_q.put(("r", cam))
    start_evt.wait()
    cpu0 = time.process_time()
    t_start = start_ns.value
    k = torn = rejects = 0
    while True:
        if available(k):
            t0 = pc()
            rc = read(k)
            t1 = pc()
            if rc:
                rejects += 1
                continue
            if not check_stamp(dst, k):
                torn += 1
            lat.append(t1 - t0)
            e2e.append(t1 - pub_ns_of(dst))
            k += 1
        else:
            d = done_val.value
            if d >= 0 and k >= d:
                break
            sleep0(0)
    elapsed = (pc() - t_start) / 1e9
    cpu = time.process_time() - cpu0
    result_q.put(dict(role="reader", cam=cam, n=k, elapsed_s=elapsed, fps=k / elapsed, cpu_s=cpu, cpu_ms_per_frame=1e3 * cpu / max(k, 1),
                      op=stats_ms(lat), e2e=stats_ms(e2e), first_lap=stats_ms([]), blocked_ns=0, blocked_events=0, torn=torn, gaps=0,
                      seq_rejects=rejects, verified=1))


# ------------------------------------------------------------------------------------------------ parent
def main():
    mode, size, ncams, impl = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    if mode == "write":
        paced, run_s, out = 0.0, float(sys.argv[5]), sys.argv[6]
    else:
        paced, run_s, out = float(sys.argv[5]), float(sys.argv[6]), sys.argv[7]
    h, w = parse_size(size)
    ctx = mp.get_context("spawn")
    cleanup = []
    if impl == "sk_head":
        sys.path.insert(0, str(BASELINE))
        import bench_common as bc
        from skellycam.core.ipc.shared_memory.camera_group_shared_memory import CameraGroupSharedMemory
        from skellycam.core.timestamps.timebase_mapping import TimebaseMapping
        configs = {str(i): bc.make_config(i, h, w) for i in range(ncams)}
        gshm = CameraGroupSharedMemory.create(camera_configs=configs, timebase_mapping=TimebaseMapping(), read_only=True)
        handles = [gshm.camera_shm_dtos[str(i)] for i in range(ncams)]
        cleanup.append(gshm.unlink_and_close)
        rb = int(bc.make_frame_recarray(configs["0"]).dtype.itemsize)
        L = ONE_GIB // rb
        stride = rb
    elif impl == "py_seq":
        from multiprocessing import shared_memory
        handles, rings = [], []
        for i in range(ncams):
            shm = shared_memory.SharedMemory(create=True, size=NpRing.total(h, w))
            r = NpRing(shm, h, w)
            r.init()
            rings.append(r)
            handles.append(shm.name)

        def _c():
            for r in rings:
                s = r.shm
                r.close()
                s.unlink()
        cleanup.append(_c)
        rb, L, stride = rings[0].rb, rings[0].L, rings[0].stride
    else:
        cppring = import_cppring()
        handles = [f"Local\\crpy_{os.getpid()}_{i}" for i in range(ncams)]
        rings = [cppring.Ring(n, h, w, True, True) for n in handles]
        cleanup.append(lambda: [r.close() for r in rings])
        rb, L, stride = rings[0].record_bytes, rings[0].L, rings[0].stride
    ready_q, result_q, start_evt = ctx.Queue(), ctx.Queue(), ctx.Event()
    start_ns = ctx.Value("q", 0, lock=False)
    procs = []
    if mode == "write":
        for i in range(ncams):
            procs.append(ctx.Process(target=write_child, args=(impl, i, h, w, handles[i], run_s, ready_q, start_evt, result_q)))
    else:
        dones = [ctx.Value("q", -1, lock=False) for _ in range(ncams)]
        for i in range(ncams):
            procs.append(ctx.Process(target=spsc_writer, args=(impl, i, h, w, handles[i], paced, run_s, ready_q, start_evt, start_ns,
                                                               dones[i], result_q)))
            procs.append(ctx.Process(target=spsc_reader, args=(impl, i, h, w, handles[i], ready_q, start_evt, start_ns, dones[i], result_q)))
    for p in procs:
        p.start()
    for _ in procs:
        ready_q.get(timeout=600)
    start_ns.value = time.perf_counter_ns() + 1_000_000
    start_evt.set()
    roles = [result_q.get(timeout=900) for _ in procs]
    for p in procs:
        p.join(60)
        if p.is_alive():
            p.kill()
    for c in cleanup:
        try:
            c()
        except Exception as e:  # noqa: BLE001
            print("cleanup error", e, file=sys.stderr)
    roles.sort(key=lambda r: (r["cam"], r["role"] != "writer"))
    res = dict(tool="py_ring", mode=mode, impl=impl, topology="process", h=h, w=w, ncams=ncams, paced_fps=paced, run_s=run_s,
               ring_len=L, record_bytes=rb, slot_stride=stride, python=sys.version.split()[0], executable=sys.executable,
               numpy=np.__version__, roles=roles)
    js = json.dumps(res)
    print(js)
    if out != "-":
        Path(out).write_text(js)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
