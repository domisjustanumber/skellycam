"""GIL, threading, time mapping, control privilege, stream knobs, errors, incomplete frames."""
import sys, threading, time, warnings
import numpy as np
import viva_genicam as vg
from viva_genicam.testing import FakeGigeCamera


def section(t):
    print(f"\n=== {t}", flush=True)


# ---------------- GIL ----------------
def spin_counts(seconds, work=None):
    """Count loop iterations in a pure-Python thread while `work` runs in this thread."""
    stop = threading.Event()
    cnt = [0]

    def spin():
        c = 0
        while not stop.is_set():
            c += 1
        cnt[0] = c

    th = threading.Thread(target=spin)
    th.start()
    t0 = time.perf_counter()
    if work:
        work(seconds)
    rest = seconds - (time.perf_counter() - t0)
    if rest > 0:
        time.sleep(rest)
    stop.set()
    th.join()
    return cnt[0]


with FakeGigeCamera(width=1280, height=1024, fps=30) as fake:
    cam = vg.connect_gige(fake.device_info())
    section("GIL: busy Python thread iterations over 3 s")
    base = spin_counts(3.0)

    def stream_work(seconds):
        n = 0
        t_block = 0.0
        with cam.stream() as frames:
            t_end = time.perf_counter() + seconds
            while time.perf_counter() < t_end:
                t = time.perf_counter()
                frames.next_frame(timeout_ms=2000)
                t_block += time.perf_counter() - t
                n += 1
        print(f"  stream thread got {n} frames, spent {t_block:.2f}s blocked in next_frame")

    with_stream = spin_counts(3.0, stream_work)

    def gvcp_work(seconds):
        n = 0
        t_end = time.perf_counter() + seconds
        while time.perf_counter() < t_end:
            cam.invalidate("Width")
            cam.get_integer("Width")
            n += 1
        print(f"  {n} uncached GVCP reads in {seconds}s ({n / seconds:.0f}/s)")

    with_gvcp = spin_counts(3.0, gvcp_work)
    print(
        f"  spin iterations: idle-main {base:,}  while-streaming {with_stream:,} ({with_stream / base:.0%})"
        f"  while-GVCP-reads {with_gvcp:,} ({with_gvcp / base:.0%})"
    )

    section("decode cost: to_numpy vs np.frombuffer(payload())  (1280x1024 Mono8)")
    with cam.stream() as frames:
        fr = frames.next_frame(timeout_ms=3000)
    for name, fn in [
        ("to_numpy()", lambda: fr.to_numpy()),
        ("np.frombuffer(payload()).reshape", lambda: np.frombuffer(fr.payload(), np.uint8).reshape(fr.height, fr.width)),
        ("to_rgb8()", lambda: fr.to_rgb8()),
    ]:
        t = time.perf_counter()
        for _ in range(50):
            a = fn()
        print(
            f"  {name:35s} {(time.perf_counter() - t) / 50 * 1e3:.3f} ms  shape {a.shape}"
            f" owndata {a.flags['OWNDATA']} writeable {a.flags['WRITEABLE']}"
        )
    assert np.array_equal(fr.to_numpy(), np.frombuffer(fr.payload(), np.uint8).reshape(fr.height, fr.width))

    section("threading: stream pulled in worker thread while main thread uses camera")
    got = []
    errs = []

    def worker(fs):
        try:
            for _ in range(30):
                got.append(fs.next_frame(timeout_ms=3000).block_id)
        except BaseException as e:
            errs.append(e)

    with cam.stream() as frames:
        th = threading.Thread(target=worker, args=(frames,))
        th.start()
        reads = 0
        while th.is_alive():
            cam.get("ExposureTime")
            cam.invalidate("Gain")
            cam.get_float("Gain")
            reads += 1
        th.join()
        print(f"  worker got {len(got)} frames (errors {errs}); main did {reads} feature reads meanwhile")
        res = []

        def both():
            try:
                res.append(frames.next_frame(timeout_ms=3000).block_id)
            except BaseException as e:
                res.append(f"{type(e).__name__}: {e}")

        ts = [threading.Thread(target=both) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        print("  two concurrent next_frame on one stream ->", res)
        try:
            cam.set("Width", "640")
            print("  set Width while streaming -> OK (Width now", cam.get("Width"), ")")
        except Exception as e:
            print("  set Width while streaming ->", type(e).__name__, e)
        try:
            s2 = cam.stream()
            print("  second stream() while first open -> OK?!")
            s2.close()
        except Exception as e:
            print("  second stream() while first open ->", type(e).__name__, e)

    section("time mapping")
    with cam.stream() as frames:
        fr = frames.next_frame(timeout_ms=3000)
    print("  before calibrate: ts_dev", fr.ts_dev, "ts_host", fr.ts_host, "map_dev_ts", cam.map_dev_ts(fr.ts_dev or 0))
    t = time.perf_counter()
    cam.time_calibrate(samples=8, interval_ms=20)
    print(f"  time_calibrate(8,20) took {time.perf_counter() - t:.3f}s")
    with cam.stream() as frames:
        rows = []
        for _ in range(5):
            fr = frames.next_frame(timeout_ms=3000)
            now = time.time()
            rows.append((fr.block_id, fr.ts_dev, fr.ts_host, now - fr.ts_host if fr.ts_host else None))
    for r in rows:
        print("  block %s ts_dev %s ts_host %.6f host_now-ts_host %.3f ms" % (r[0], r[1], r[2], r[3] * 1e3))
    print("  map_dev_ts(ts_dev) == ts_host:", cam.map_dev_ts(rows[-1][1]) == rows[-1][2])
    try:
        cam.time_calibrate(samples=1)
    except Exception as e:
        print("  time_calibrate(samples=1) ->", type(e).__name__, e)

    section("timeouts / trigger / end")
    cam.enable_trigger("FrameStart", "Software")
    print("  TriggerMode", cam.get("TriggerMode"), "TriggerSource", cam.get("TriggerSource"))
    with cam.stream() as frames:
        t = time.perf_counter()
        try:
            fr = frames.next_frame(timeout_ms=300)
            print("  next_frame in trigger mode ->", fr)
        except Exception as e:
            print(f"  next_frame(timeout_ms=300) in trigger mode -> {type(e).__name__}: {e} after {time.perf_counter() - t:.3f}s")
        cam.trigger_software()
        try:
            fr = frames.next_frame(timeout_ms=1000)
            print("  after trigger_software ->", fr.block_id, "fake.software_triggers", fake.software_triggers())
        except Exception as e:
            print("  after trigger_software ->", type(e).__name__, e)
    cam.disable_trigger("FrameStart")
    for src in ("Action1", "Action0"):
        try:
            cam.set_enum("TriggerSource", src)
        except Exception as e:
            print(f"  set TriggerSource={src} ->", type(e).__name__, e)
    frames = cam.stream()
    frames.__enter__()
    frames.close()
    try:
        frames.next_frame(timeout_ms=100)
    except Exception as e:
        print("  next_frame after close ->", type(e).__name__, e)
    cam.acquisition_stop()

    section("exceptions")
    for label, call in [
        ("get missing", lambda: cam.get("NoSuchFeature")),
        ("set_integer Width=3", lambda: cam.set_integer("Width", 3)),
        ("set_integer Width=1e6", lambda: cam.set_integer("Width", 10**6)),
        ("set command", lambda: cam.set("AcquisitionStart", "1")),
        ("get_integer on enum", lambda: cam.get_integer("PixelFormat")),
        ("set_enum bad entry", lambda: cam.set_enum("PixelFormat", "Nope")),
        ("read_register unmapped", lambda: cam.read_register(0x7FFFFFF0, 4)),
    ]:
        try:
            print(f"  {label}: ok ->", call())
        except Exception as e:
            print(f"  {label}: {type(e).__name__} | {e}")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        print("  execute(TimestampLatch) ->", cam.execute("TimestampLatch"), "warnings", [str(x.message) for x in w])

    section("control privilege / heartbeat")
    try:
        cam2 = vg.connect_gige(fake.device_info())
        print("  second controller connect -> OK?!", cam2.control_state)
    except Exception as e:
        print("  second controller connect ->", type(e).__name__, e)
    mon = vg.connect_gige(fake.device_info(), monitor=True)
    print("  monitor connect ->", mon.control_state, "Width", mon.get("Width"))
    try:
        mon.set("Width", "320")
    except Exception as e:
        print("  monitor set ->", type(e).__name__, e)
    mon.close()
    print("  heartbeat timeout reg 0x0938 =", int.from_bytes(cam.read_register(0x0938), "big"), "ms")
    fake.revoke_control()
    t = time.perf_counter()
    for _ in range(60):
        if cam.control_state != vg.ControlState.HELD:
            break
        time.sleep(0.05)
    print(f"  after fake.revoke_control(): control_state {cam.control_state} (noticed after {time.perf_counter() - t:.2f}s)")
    try:
        cam.set("Gain", "1.0")
        print("  set after revoke -> OK")
    except Exception as e:
        print("  set after revoke ->", type(e).__name__, e)
    cam.reclaim_control()
    print("  after reclaim_control:", cam.control_state, "fake.controller", fake.controller())
    cam.release_control()
    print("  after release_control:", cam.control_state, "fake.controller", fake.controller())
    try:
        cam.set("Gain", "1.0")
        print("  set after release -> OK")
    except Exception as e:
        print("  set after release ->", type(e).__name__, e)
    try:
        with cam.stream() as frames:
            print("  stream() after release ->", frames.next_frame(timeout_ms=2000).block_id, cam.control_state)
    except Exception as e:
        print("  stream() after release ->", type(e).__name__, e)
    cam.close()

section("stream knobs")
with FakeGigeCamera(width=640, height=480, fps=30) as fake:
    cam = vg.connect_gige(fake.device_info())
    for kw in [
        dict(packet_size=9000),
        dict(packet_size=576),
        dict(auto_packet_size=True),
        dict(packet_delay_ns=2000),
        dict(destination_port=50555),
        dict(resend=False),
        dict(iface="127.0.0.1"),
        dict(packet_size=1500, auto_packet_size=True),
    ]:
        try:
            with cam.stream(**kw) as frames:
                fr = frames.next_frame(timeout_ms=3000)
                st = frames.stats()
                print(
                    f"  {kw}: ok block {fr.block_id}; GevSCPSPacketSize={cam.get('GevSCPSPacketSize')}"
                    f" packets/frame={st.packets_received / max(1, st.frames_complete):.0f}"
                )
        except Exception as e:
            print(f"  {kw}: {type(e).__name__}: {e}")
    cam.close()

section("incomplete frames / resend")
for resend_cap in (True, False):
    for deliver in (False, True):
        # drop_packets block ids count from 1 at each acquisition start
        with FakeGigeCamera(width=640, height=480, fps=30, packet_resend=resend_cap, drop_packets=[(2, 5), (3, 7)]) as fake:
            cam = vg.connect_gige(fake.device_info())
            with cam.stream(deliver_incomplete=deliver) as frames:
                seen = []
                for _ in range(4):
                    fr = frames.next_frame(timeout_ms=3000)
                    seen.append((fr.block_id, fr.status.value, fr.missing_packets))
                st = frames.stats()
            print(
                f"  camera resend={resend_cap} deliver_incomplete={deliver}: {seen} | incomplete={st.frames_incomplete}"
                f" resend_req={st.resend_requested} recovered={st.resend_recovered} unavailable={st.resend_unavailable}"
            )
            cam.close()
