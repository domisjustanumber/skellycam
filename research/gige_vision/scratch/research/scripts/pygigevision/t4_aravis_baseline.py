import sys, time, gi
gi.require_version("Aravis", "0.8")
from gi.repository import Aravis
fmt = sys.argv[1] if len(sys.argv) > 1 else "Mono16"
Aravis.update_device_list()
print("aravis devices:", [Aravis.get_device_id(i) for i in range(Aravis.get_n_devices())])
cam = Aravis.Camera.new(None)
cam.set_region(0, 0, 640, 480); cam.set_pixel_format_from_string(fmt); cam.set_frame_rate(30)
cam.gv_set_packet_size(1500)
payload = cam.get_payload()
st = cam.create_stream(None, None)
for _ in range(20): st.push_buffer(Aravis.Buffer.new_allocate(payload))
cam.start_acquisition()
t0 = time.time(); ok = bad = 0; ts = []
while time.time() - t0 < 3:
    b = st.timeout_pop_buffer(1000000)
    if b is None: continue
    if b.get_status() == Aravis.BufferStatus.SUCCESS: ok += 1; ts.append(b.get_timestamp())
    else: bad += 1
    st.push_buffer(b)
cam.stop_acquisition()
stats = st.get_statistics()
print(f"aravis fmt={fmt} ok={ok} bad={bad} get_statistics={stats}")
for name in ("n_resent_packets", "n_missing_packets", "n_ignored_bytes"):
    try: print(name, st.get_info_uint64_by_name(name))
    except Exception as e: print(name, "n/a", e)
print("payload bytes:", payload, " socket buffer setting:", st.get_property("socket-buffer"), st.get_property("socket-buffer-size"))
