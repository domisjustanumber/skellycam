import socket, struct, sys, time
import viva_genicam as vg
from viva_genicam.testing import FakeGigeCamera
print("REGISTERS", dict(FakeGigeCamera.REGISTERS))
print("keys", hex(FakeGigeCamera.DEVICE_KEY), hex(FakeGigeCamera.GROUP_KEY), hex(FakeGigeCamera.GROUP_MASK))
with FakeGigeCamera(width=320, height=240, fps=20, pixel_format="BayerRG8") as fake:
    info = fake.device_info()
    print("info", info)
    cam = vg.connect_gige(info)
    names = cam.nodes()
    print("n nodes", len(names))
    interesting = [n for n in names if any(k in n for k in ("Ptp","1588","Action","Trigger","Timestamp","Gev","DeviceTL","Version","Streaming","PixelFormat","AcquisitionFrameRate"))]
    print("interesting nodes:", interesting)
    for n in interesting:
        try:
            ni = cam.node_info(n)
            v = cam.get(n) if ni and ni.kind not in ("Command",) else "<cmd>"
            print(f"  {n:45s} kind={getattr(ni,'kind',None)} val={v!r}")
        except Exception as e:
            print(f"  {n:45s} ERR {type(e).__name__}: {e}")
    try:
        print("TriggerSource entries", cam.enum_entries("TriggerSource"))
    except Exception as e: print("TriggerSource entries err", e)
    # raw GVCP read of bootstrap regs while viva holds control
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(0.5)
    for addr in (0x0000, 0x0934, 0x093C, 0x0940, 0x0954, 0x096C, 0x0D04, 0x0904, 0x0908, 0x0970, 0x090C):
        s.sendto(struct.pack(">BBHHHI", 0x42, 1, 0x80, 4, addr+1, addr), (fake.ip, 3956))
        try:
            d,_ = s.recvfrom(100); st, cmd, ln, rid = struct.unpack(">HHHH", d[:8]); print(f"  reg 0x{addr:04x} status=0x{st:04x} val=0x{d[8:12].hex()}")
        except socket.timeout: print(f"  reg 0x{addr:04x} timeout")
    # discovery ack
    s.sendto(struct.pack(">BBHHH", 0x42, 0x11, 2, 0, 7), (fake.ip, 3956))
    d,_ = s.recvfrom(1500); print("disc ack len", len(d), "ver", d[8:12].hex(), "manuf", d[8+72:8+104].split(b"\0")[0])
    # timestamp latch via raw write (we are not controller -> expect ACCESS_DENIED)
    s.sendto(struct.pack(">BBHHHII", 0x42, 1, 0x82, 8, 99, 0x0944, 2), (fake.ip, 3956))
    d,_ = s.recvfrom(100); print("latch write status", hex(struct.unpack(">H", d[:2])[0]))
    with cam.stream() as frames:
        for i, fr in enumerate(frames):
            print("frame", fr.block_id, fr.ts_dev, fr.ts_host, fr.pixel_format, hex(fr.pixel_format_code), fr.payload_type, fr.status)
            if i >= 2: break
    cam.time_calibrate()
    print("map", cam.map_dev_ts(1000000))
    print("send_action", vg.send_action(FakeGigeCamera.DEVICE_KEY, FakeGigeCamera.GROUP_KEY, FakeGigeCamera.GROUP_MASK, destination=fake.ip, timeout_ms=300), fake.actions())
    print("send_action sched", vg.send_action(FakeGigeCamera.DEVICE_KEY, FakeGigeCamera.GROUP_KEY, FakeGigeCamera.GROUP_MASK, scheduled_time=123, destination=fake.ip, timeout_ms=300), fake.actions())
    cam.close()
