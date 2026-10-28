"""Verify: Aravis GvStream caches TimestampTickFrequency (bootstrap 0x093C/0x0940) at stream creation.
The fake GV camera sends leader timestamps in ns (raw ticks == ns) regardless of its tick register,
so changing the register changes only how Aravis converts ticks -> ns."""
import sys, gi
gi.require_version("Aravis", "0.8")
from gi.repository import Aravis

TICK_HI, TICK_LO = 0x093C, 0x0940

def grab(cam, stream, n=5):
    cam.start_acquisition(); out=[]
    while len(out) < n:
        b = stream.timeout_pop_buffer(2_000_000)
        if b is None: break
        if b.get_status() == Aravis.BufferStatus.SUCCESS:
            out.append((b.get_timestamp(), b.get_system_timestamp()))
        stream.push_buffer(b)
    cam.stop_acquisition(); return out

def run(label, set_before):
    cam = Aravis.Camera.new("127.0.0.1"); dev = cam.get_device()
    dev.write_register(TICK_HI, 0); dev.write_register(TICK_LO, 1_000_000_000)
    if set_before:
        dev.write_register(TICK_LO, 1_000_000)  # pretend 1 MHz tick clock
    stream = cam.create_stream(None, None)
    if not set_before:
        dev.write_register(TICK_LO, 1_000_000)  # change after stream creation
    print(label, "tick register now:", dev.get_timestamp_tick_frequency())
    for _ in range(5): stream.push_buffer(Aravis.Buffer.new_allocate(cam.get_payload()))
    ts = grab(cam, stream)
    for d, s in ts[:2]: print(f"  device_ts={d} system_ts={s} ratio={d/s:.1f}")
    dev.write_register(TICK_LO, 1_000_000_000)
    del stream, cam

run("[A] tick set to 1 MHz BEFORE create_stream:", True)
run("[B] tick set to 1 MHz AFTER create_stream:", False)
