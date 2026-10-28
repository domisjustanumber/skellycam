"""GigE Vision GVSP bandwidth calculator (standard-header GVSP, IPv4, no VLAN).
Per-packet overhead from Aravis ARV_GVSP_PACKET_PROTOCOL_OVERHEAD: IP 20 + UDP 8 + GVSP 8 (16-bit block id) = 36 B
(extended-ID GVSP header = 20 B -> 48 B). SCPS (GevSCPSPacketSize) is the IP datagram size.
On-wire per Ethernet frame: + 14 MAC hdr + 4 FCS + 8 preamble/SFD + 12 inter-frame gap = 38 B.
Leader/trailer packets ignored (2 small packets per frame)."""
import math
WIRE = 38
def eff(scps, ext=False):
    data = scps - (48 if ext else 36)
    return data, data / (scps + WIRE)
def report(w, h, bpp, fps, name):
    frame = w * h * bpp
    rate = frame * fps
    print(f"{name}: {w}x{h} @ {bpp} B/px = {frame/1e6:.3f} MB/frame; @ {fps} fps = {rate/1e6:.2f} MB/s = {rate*8/1e6:.1f} Mbit/s payload")
    for scps in (1500, 9000):
        data, e = eff(scps)
        pkts = math.ceil(frame / data) + 2
        for link in (1e9, 2.5e9, 5e9, 10e9):
            cap = link / 8 * e
            print(f"   SCPS={scps:5d} ({data} B data/pkt, {pkts} pkts/frame, eff {e*100:.1f}%) link {link/1e9:>4} GbE: "
                  f"usable {cap/1e6:7.1f} MB/s -> {cap/rate:5.2f} cams/link, single-cam max {cap/frame:6.1f} fps")
for scps in (1500, 9000):
    d, e = eff(scps); print(f"SCPS {scps}: {d} B image data/packet, wire efficiency {e*100:.2f}%")
report(1920, 1200, 1, 60, "BayerRG8")
report(1920, 1200, 1, 30, "BayerRG8")
report(1920, 1200, 1.5, 60, "BayerRG12p")
report(1440, 1080, 1, 60, "BayerRG8 (1.6MP IMX273-class)")
report(1280, 1024, 1, 120, "Mono8 1.3MP")
# check against the Docker fake-camera run: SCPS 1400, 512x512 Mono8
d, _ = eff(1400); print(f"fake cam check: SCPS 1400 -> {d} B/pkt, 512*512/{d} -> {math.ceil(512*512/d)} payload pkts, trailer packet_id = {math.ceil(512*512/d)+1}")
