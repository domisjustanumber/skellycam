"""Pickling and use from a spawned child process (SkellyCam runs one process per camera group)."""
import multiprocessing as mp
import pickle
import time


def child(ip: str, n: int, q) -> None:
    import viva_genicam as vg
    info = next(i for i in vg.discover(timeout_ms=600, all=True) if i.ip == ip)
    with vg.connect_gige(info) as cam:
        with cam.stream() as frames:
            ids = [frames.next_frame(timeout_ms=3000).block_id for _ in range(n)]
    q.put((ip, ids))


if __name__ == "__main__":
    import viva_genicam as vg
    from viva_genicam.testing import FakeGigeCamera

    with FakeGigeCamera(width=320, height=240, fps=30) as fake:
        info = fake.device_info()
        for obj, label in [(info, "GigeDeviceInfo"), (vg.AckSummary(1, 1), "AckSummary")]:
            try:
                pickle.dumps(obj)
                print(label, "pickles OK")
            except Exception as e:
                print(label, "pickle ->", type(e).__name__, e)
        cam = vg.connect_gige(info)
        with cam.stream() as frames:
            fr = frames.next_frame(timeout_ms=3000)
        for obj, label in [(cam, "Camera"), (fr, "Frame")]:
            try:
                pickle.dumps(obj)
                print(label, "pickles OK")
            except Exception as e:
                print(label, "pickle ->", type(e).__name__, e)
        cam.close()
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        t = time.perf_counter()
        p = ctx.Process(target=child, args=(fake.ip, 10, q))
        p.start()
        print("child result:", q.get(timeout=60), f"in {time.perf_counter() - t:.2f}s")
        p.join(30)
        print("child exitcode", p.exitcode)
