import sys, time, os, gi
gi.require_version("Aravis", "0.8")
from gi.repository import Aravis
fmt, w, h, fps, pkt, secs = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5]), float(sys.argv[6])
cam = Aravis.Camera.new(None)
cam.set_region(0, 0, w, h); cam.set_pixel_format_from_string(fmt); cam.set_frame_rate(fps); cam.gv_set_packet_size(pkt)
payload = cam.get_payload(); st = cam.create_stream(None, None)
for _ in range(50): st.push_buffer(Aravis.Buffer.new_allocate(payload))
c0 = os.times(); t0 = time.time(); cam.start_acquisition(); ok = bad = 0
while time.time() - t0 < secs:
    b = st.timeout_pop_buffer(200000)
    if b is None: continue
    ok += b.get_status() == Aravis.BufferStatus.SUCCESS; bad += b.get_status() != Aravis.BufferStatus.SUCCESS
    st.push_buffer(b)
c1 = os.times(); cam.stop_acquisition()
cpu = (c1.user - c0.user) + (c1.system - c0.system)
print(f"ARAVIS fmt={fmt} {w}x{h} req_fps={fps} pkt={pkt} ok={ok} bad={bad} fps_ok={ok/secs:.1f} MB/s={ok*payload/secs/1e6:.1f} cpu={100*cpu/secs:.0f}% stats={st.get_statistics()}")
