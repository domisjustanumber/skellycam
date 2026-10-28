"""Repro: a spawned child that receives a SkellyCam SharedMemoryRingBufferDTO BEFORE any multiprocessing.Queue
in its args crashes while unpickling, because skellycam/core/types/type_overloads.py L23 evaluates
multiprocessing.queues.Queue at import but only imports multiprocessing.sharedctypes (L1-3).
This hit the first run of bench_a_write.py (args order: ..., dto, ..., Queue). The benchmarks work around it
with a top-level `import multiprocessing.queues` in the main script (re-imported as __mp_main__ in children).

Run:  cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam && .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\baseline\\repro_type_overloads_spawn.py
"""
import multiprocessing as mp
import sys


def child(dto, q):
    q.put("child ok")


if __name__ == "__main__":
    import numpy as np
    from skellycam.core.ipc.shared_memory.ring_buffer_shared_memory import SharedMemoryRingBuffer
    ring = SharedMemoryRingBuffer.create(example_data=np.recarray(1, dtype=[("x", "f8")]), read_only=False,
                                         ring_buffer_length=4)
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=child, args=(ring.to_dto(), q))
    p.start()
    p.join(60)
    print(f"child exitcode={p.exitcode} (0 = ok, 1 = crashed while unpickling args)")
    ring.close_and_unlink()
    sys.exit(0)
