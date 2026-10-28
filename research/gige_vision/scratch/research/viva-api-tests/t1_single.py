"""Single fake: discovery, features, registers, stream 100 frames."""
import sys, time, platform
import viva_genicam as vg
from viva_genicam.testing import FakeGigeCamera

print("python", sys.version.split()[0], platform.platform(), "viva", vg.__version__)
t0 = time.perf_counter()
with FakeGigeCamera(width=640, height=480, fps=60, pixel_format="Mono8") as fake:
    print("fake:", fake, "ip", fake.ip, "port", fake.port, "start s", round(time.perf_counter()-t0, 3))
    for kw in ({}, {"all": True}, {"iface": "127.0.0.1"}, {"iface": "127.0.0.1", "all": True}):
        t = time.perf_counter()
        try:
            r = vg.discover(timeout_ms=500, **kw)
            print("discover", kw, "->", r, round(time.perf_counter()-t, 3), "s")
        except Exception as e:
            print("discover", kw, "ERR", type(e).__name__, e)
    info = fake.device_info()
    print("device_info:", info, info.to_dict())
    cam = vg.connect_gige(info)
    print("control_state", cam.control_state, "controller per fake:", fake.controller())
    print("transport", cam.transport, "xml len", len(cam.xml))
    names = cam.nodes()
    print("n nodes", len(names))
    print("nodes:", names)
    for f in ["DeviceVendorName", "DeviceModelName", "DeviceSerialNumber", "DeviceID", "DeviceFirmwareVersion",
              "Width", "Height", "PixelFormat", "SensorType", "AcquisitionFrameRate", "ExposureTime", "Gain",
              "GevTimestampTickFrequency", "GevSCPSPacketSize", "GevSCPD", "PayloadSize", "TLParamsLocked",
              "TriggerSelector", "TriggerMode", "TriggerSource", "PtpEnable", "GevIEEE1588", "ActionDeviceKey",
              "GevIEEE1588OffsetFromMasterLatched_Val"]:
        try:
            print(f"  get {f!r} = {cam.get(f)!r}")
        except Exception as e:
            print(f"  get {f!r} ERR {type(e).__name__}: {e}")
    print("PixelFormat enum_entries", cam.enum_entries("PixelFormat"), "available", cam.available_enum_entries("PixelFormat"))
    print("TriggerSource entries", cam.enum_entries("TriggerSource"))
    print("feature_state(PixelFormat)", cam.feature_state("PixelFormat"))
    print("feature_state(Width)", cam.feature_state("Width"))
    for nm in ("PtpEnable", "Nope"):
        print("node_info", nm, cam.node_info(nm))
    print("node_info Width", cam.node_info("Width"))
    try:
        cam.feature_state("PtpEnable")
    except Exception as e:
        print("feature_state(PtpEnable) ERR", type(e).__name__, e, "| mro", [c.__name__ for c in type(e).__mro__])
    # bootstrap registers
    def u32(b): return int.from_bytes(b, "big")
    ver = u32(cam.read_register(0x0000))
    cap = u32(cam.read_register(0x0934))
    tf = (u32(cam.read_register(0x093C)) << 32) | u32(cam.read_register(0x0940))
    print(f"Version reg 0x0000 = 0x{ver:08x} (major {ver>>16}, minor {ver&0xffff})")
    print(f"GVCP capability 0x0934 = 0x{cap:08x}; 1588={bool(cap&0x00080000)} sched_action={bool(cap&0x00020000)} action={bool(cap&0x40)}")
    print("tick freq bootstrap", tf)
    try:
        print("GVCP config 0x0954 =", hex(u32(cam.read_register(0x0954))))
    except Exception as e:
        print("0x0954 ERR", type(e).__name__, e)
    try:
        cam.write_register(0x0944, (2).to_bytes(4, "big"))
        hi, lo = u32(cam.read_register(0x0948)), u32(cam.read_register(0x094C))
        print("bootstrap timestamp latch value", (hi << 32) | lo)
    except Exception as e:
        print("bootstrap latch ERR", type(e).__name__, e)
    print("read 8 bytes at 0x0948:", cam.read_register(0x0948, 8).hex())
    # set by enum name
    cam.set_enum("PixelFormat", "Mono8"); cam.set_integer("Width", 640)
    try:
        cam.set("PixelFormat", "BayerRG8")
    except Exception as e:
        print("set PixelFormat BayerRG8 on mono sensor ERR", type(e).__name__, e)
    # stream 100 frames
    n = 0; t = time.perf_counter(); bids = []; tsd = []
    with cam.stream() as frames:
        print("GevSCPSPacketSize during stream", cam.get("GevSCPSPacketSize"))
        for fr in frames:
            if n == 0:
                print("first frame:", fr, "status", fr.status, "complete", fr.is_complete, "ptype", hex(fr.payload_type),
                      "pf", fr.pixel_format, hex(fr.pixel_format_code), "padding_x", fr.padding_x, "ts_dev", fr.ts_dev,
                      "ts_host", fr.ts_host, "chunks", fr.chunks, "missing", fr.missing_packets)
                a = fr.to_numpy(); print("to_numpy", a.shape, a.dtype, a.flags["OWNDATA"], a.flags["WRITEABLE"])
            bids.append(fr.block_id); tsd.append(fr.ts_dev)
            n += 1
            if n >= 100:
                break
        st = frames.stats()
    dt = time.perf_counter() - t
    print(f"100 frames in {dt:.2f}s = {n/dt:.1f} fps; block ids {bids[:3]}..{bids[-1]}; ts_dev deltas(ns?) {[tsd[i+1]-tsd[i] for i in range(4)]}")
    print("stats:", st)
    print("after stream control_state", cam.control_state)
    cam.close()
    print("closed", cam.closed, "fake controller after close", fake.controller())
    try:
        cam.get("Width")
    except Exception as e:
        print("after close get ERR", type(e).__name__, e)
