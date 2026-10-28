"""Verifier v2: does importing skellycam.core.types.type_overloads fail in a spawned child
when multiprocessing.queues was not pre-imported? (checks mapper claim W30)

Run from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam:
    .venv\\Scripts\\python.exe <this file>
"""
import multiprocessing
import sys


def child(q, mpq):
    import sys as _s
    before = "multiprocessing.queues" in _s.modules
    try:
        import skellycam.core.types.type_overloads  # noqa
        q.send(("ok", before, "multiprocessing.queues" in _s.modules))
    except Exception as e:
        q.send((f"{type(e).__name__}: {e}", before, "multiprocessing.queues" in _s.modules))


if __name__ == "__main__":
    print("parent has multiprocessing.queues before child start:", "multiprocessing.queues" in sys.modules)
    ctx = multiprocessing.get_context("spawn")
    q, child_end = ctx.Pipe()
    p = ctx.Process(target=child, args=(child_end, ctx.Queue()))
    p.start()
    p.join()
    print("child result (status, queues_loaded_before_import, after):", q.recv())
