"""
Grab frames from a GigE Vision camera through Aravis (via PyGObject / GObject Introspection).

Designed to be run against Aravis' software GigE Vision camera emulator:
    arv-fake-gv-camera-0.8 -i 127.0.0.1 &
    python3 aravis_fake_camera_capture.py [--device DEVICE_ID_OR_IP] [--frames 100]

Also works unmodified against a real GigE Vision camera (pass --device <ip or id>, or let it
pick the first GigE Vision device found).

Prints: discovered devices, timestamp tick frequency, pixel format, frame size,
per-frame device timestamp (arv_buffer_get_timestamp) and host system timestamp
(arv_buffer_get_system_timestamp), and measured fps.
"""
import argparse
import sys
import time

import gi

for api in ("0.8", "0.10"):
    try:
        gi.require_version("Aravis", api)
        break
    except ValueError:
        continue
from gi.repository import Aravis  # noqa: E402

import numpy as np  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default=None, help="device id or IP address (default: first GigE Vision device)")
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--n-buffers", type=int, default=10)
    ap.add_argument("--frame-rate", type=float, default=None)
    args = ap.parse_args()

    print(f"PyGObject {gi.version_info}, Aravis GIR namespace version {Aravis._version}")

    # --- discovery (arv_update_device_list) ---
    Aravis.update_device_list()
    n = Aravis.get_n_devices()
    print(f"Discovered {n} device(s):")
    first_gv = None
    for i in range(n):
        dev_id = Aravis.get_device_id(i)
        proto = Aravis.get_device_protocol(i)
        addr = Aravis.get_device_address(i)
        print(f"  [{i}] id={dev_id!r} protocol={proto!r} address={addr!r} "
              f"vendor={Aravis.get_device_vendor(i)!r} model={Aravis.get_device_model(i)!r} "
              f"serial={Aravis.get_device_serial_nbr(i)!r}")
        if first_gv is None and proto == "GigEVision":
            first_gv = dev_id

    device = args.device or first_gv
    print(f"Opening device: {device!r}")
    camera = Aravis.Camera.new(device)
    dev = camera.get_device()
    print(f"is_gv_device={camera.is_gv_device()} vendor={camera.get_vendor_name()!r} "
          f"model={camera.get_model_name()!r}")

    # --- feature access by name (GenICam node map) ---
    for feat in ("Width", "Height", "PixelFormat", "AcquisitionFrameRate", "GevTimestampTickFrequency",
                 "GevSCPSPacketSize", "PtpEnable", "GevIEEE1588", "ActionDeviceKey"):
        try:
            node = dev.get_feature(feat)
            if node is None:
                print(f"  feature {feat}: <not in GenICam XML>")
                continue
            # generic accessor that works on every 0.8.x: ask the GenICam node for its string form
            val = node.get_value_as_string()
            print(f"  feature {feat}: {val!r}")
        except Exception as e:  # noqa: BLE001
            print(f"  feature {feat}: error {e}")

    if args.frame_rate:
        camera.set_frame_rate(args.frame_rate)
    print(f"frame rate setting: {camera.get_frame_rate():.3f} Hz")

    if camera.is_gv_device():
        try:
            print(f"GV packet size: {camera.gv_get_packet_size()}")
        except Exception as e:  # noqa: BLE001
            print(f"GV packet size: error {e}")
        tick = dev.get_timestamp_tick_frequency()
        print(f"GevTimestampTickFrequency (bootstrap register): {tick} Hz")

    payload = camera.get_payload()
    pf_str = camera.get_pixel_format_as_string()
    x, y, w, h = camera.get_region()
    print(f"payload={payload} bytes, pixel_format={pf_str}, region=({x},{y},{w},{h})")

    # --- stream + buffer pool ---
    # 0.8 API: create_stream(callback, user_data); 0.10/0.9: create_stream works too.
    stream = camera.create_stream(None, None)
    if isinstance(stream, Aravis.GvStream):
        for prop in ("packet-resend", "socket-buffer", "socket-buffer-size", "packet-timeout", "frame-retention"):
            try:
                print(f"  GvStream property {prop} = {stream.get_property(prop)}")
            except Exception as e:  # noqa: BLE001
                print(f"  GvStream property {prop}: {e}")
    for _ in range(args.n_buffers):
        stream.push_buffer(Aravis.Buffer.new_allocate(payload))

    camera.start_acquisition()
    t0 = time.perf_counter()
    ok = 0
    bad = 0
    dev_ts = []
    sys_ts = []
    frame_ids = []
    copy_times = []
    first_shape = None
    try:
        while ok < args.frames:
            buf = stream.timeout_pop_buffer(2_000_000)  # 2 s, microseconds
            if buf is None:
                print("timeout waiting for buffer")
                bad += 1
                if bad > 5:
                    break
                continue
            status = buf.get_status()
            if status == Aravis.BufferStatus.SUCCESS:
                tc = time.perf_counter()
                data = buf.get_data()  # PyGObject marshals guint8[] -> Python bytes (a copy)
                copy_times.append(time.perf_counter() - tc)
                bw, bh = buf.get_image_width(), buf.get_image_height()
                pf = buf.get_image_pixel_format()
                arr = np.frombuffer(data, dtype=np.uint8)
                if first_shape is None:
                    first_shape = (bw, bh, hex(pf), arr.size, buf.get_payload_type())
                    img = arr[: bw * bh].reshape(bh, bw)
                    print(f"first frame: width={bw} height={bh} pixel_format=0x{pf:08x} "
                          f"({Aravis.pixel_format_to_gst_caps_string(pf) if hasattr(Aravis,'pixel_format_to_gst_caps_string') else ''}) "
                          f"bytes={arr.size} payload_type={buf.get_payload_type()} "
                          f"mean={img.mean():.1f} min={img.min()} max={img.max()}")
                dev_ts.append(buf.get_timestamp())
                sys_ts.append(buf.get_system_timestamp())
                frame_ids.append(buf.get_frame_id())
                ok += 1
            else:
                bad += 1
                print(f"buffer status {status}")
            stream.push_buffer(buf)
    finally:
        camera.stop_acquisition()
    elapsed = time.perf_counter() - t0

    print("\nframe_id, device_timestamp_ns, system_timestamp_ns, d_device_ms, d_system_ms")
    for i, (fid, d, s) in enumerate(zip(frame_ids, dev_ts, sys_ts)):
        dd = (d - dev_ts[i - 1]) / 1e6 if i else 0.0
        ds = (s - sys_ts[i - 1]) / 1e6 if i else 0.0
        if i < 10 or i >= len(frame_ids) - 3:
            print(f"{fid}, {d}, {s}, {dd:.3f}, {ds:.3f}")
        elif i == 10:
            print("...")

    if len(dev_ts) > 1:
        dd = np.diff(np.array(dev_ts, dtype=np.int64)) / 1e6
        ds = np.diff(np.array(sys_ts, dtype=np.int64)) / 1e6
        print(f"\ndevice-timestamp interval ms: mean={dd.mean():.3f} std={dd.std():.3f}")
        print(f"system-timestamp interval ms: mean={ds.mean():.3f} std={ds.std():.3f}")
        print(f"fps (device timestamps) = {1000.0 / dd.mean():.2f}")
        print(f"fps (system timestamps) = {1000.0 / ds.mean():.2f}")
    if copy_times:
        print(f"buffer.get_data() copy time: mean={1e3*np.mean(copy_times):.3f} ms for {payload} bytes")
    print(f"fps (wall clock incl. startup) = {ok / elapsed:.2f}  ok={ok} bad={bad} elapsed={elapsed:.3f}s")

    try:
        stats = stream.get_statistics()  # PyGObject returns the out-params as a tuple
        print(f"stream.get_statistics() raw: {stats!r}")
    except Exception as e:  # noqa: BLE001
        print(f"stream statistics: {e}")
    return 0 if ok == args.frames else 1


if __name__ == "__main__":
    sys.exit(main())
