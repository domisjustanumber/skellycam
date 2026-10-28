import sys, time, gi
gi.require_version("Aravis", "0.8")
from gi.repository import Aravis
fmt, w, h, fps, secs = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
Aravis.update_device_list()
cam = Aravis.Camera.new(Aravis.get_device_id(0))
dev = cam.get_device()
print("XML via Aravis, first bytes:", dev.get_genicam_xml()[:40] if hasattr(dev, "get_genicam_xml") else "n/a")
cam.set_region(0, 0, w, h); cam.set_pixel_format_from_string(fmt); cam.set_frame_rate(fps)
cam.gv_set_packet_size(1500)
st = cam.create_stream(None, None)
for _ in range(20): st.push_buffer(Aravis.Buffer.new_allocate(cam.get_payload()))
cam.start_acquisition()
t0 = time.time(); ok = bad = 0
while time.time() - t0 < secs:
    b = st.timeout_pop_buffer(500000)
    if b is None: continue
    if b.get_status() == Aravis.BufferStatus.SUCCESS: ok += 1
    else: bad += 1
    st.push_buffer(b)
cam.stop_acquisition()
print(f"Aravis {fmt} {w}x{h}@{fps}: success={ok} other={bad}")
