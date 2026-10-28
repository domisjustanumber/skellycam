#!/usr/bin/env python3
"""Minimal raw-GVCP probe: reads GigE Vision bootstrap registers and decodes
version + capability bits. Pure stdlib; works against any GigE Vision device.
Usage: python3 probe.py <device-ip> [<bind-ip>]
Register addresses/bit masks cross-checked against:
  Aravis src/arvgvcpprivate.h and Wireshark epan/dissectors/packet-gvcp.c
"""
import socket, struct, sys

GVCP_PORT = 3956
READREG_CMD = 0x0080
REGS = {
    "Version": 0x0000,
    "DeviceMode": 0x0004,
    "NumMessageChannels": 0x0900,
    "NumStreamChannels": 0x0904,
    "NumActionSignals": 0x0908,
    "GVCPCapability": 0x0934,
    "TimestampTickFreqHigh": 0x093C,
    "TimestampTickFreqLow": 0x0940,
    "GVCPConfiguration": 0x0954,
    "IEEE1588Status": 0x096C,
    "ScheduledActionQueueSize": 0x0970,
    "IEEE1588ExtendedCapability": 0x0974,
    "IEEE1588SupportedProfiles": 0x0978,
    "IEEE1588SelectedProfile": 0x097C,
}
# GVCP Capability (0x0934) masks (LSB-0 integer masks, from Wireshark hf_ defs)
CAP_BITS = [
    (0x80000000, "UserDefinedName"), (0x40000000, "SerialNumber"),
    (0x20000000, "HeartbeatDisable"), (0x10000000, "LinkSpeed"),
    (0x08000000, "CCPApplicationPortIP"), (0x04000000, "ManifestTable"),
    (0x02000000, "TestData"), (0x01000000, "DiscoveryAckDelay"),
    (0x00800000, "WritableDiscoveryAckDelay"), (0x00400000, "ExtendedStatusCodes(v1.1)"),
    (0x00200000, "PrimaryApplicationSwitchover"), (0x00100000, "UnconditionalAction(v2.0)"),
    (0x00080000, "IEEE1588(v2.0)"), (0x00040000, "ExtendedStatusCodes(v2.0)"),
    (0x00020000, "ScheduledAction(v2.0)"), (0x00010000, "IEEE1588ExtendedCapabilities(v2.1)"),
    (0x00000040, "Action"), (0x00000020, "PendingAck"), (0x00000010, "EventData"),
    (0x00000008, "Event"), (0x00000004, "PacketResend"), (0x00000002, "WriteMem"),
    (0x00000001, "Concatenation"),
]

def readreg(sock, ip, addr, req_id):
    pkt = struct.pack(">BBHHHI", 0x42, 0x01, READREG_CMD, 4, req_id, addr)
    sock.sendto(pkt, (ip, GVCP_PORT))
    data, _ = sock.recvfrom(1024)
    status, ack, length, ack_id = struct.unpack(">HHHH", data[:8])
    if status != 0:
        return None, status
    return struct.unpack(">I", data[8:12])[0], status

def main():
    ip = sys.argv[1]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if len(sys.argv) > 2:
        s.bind((sys.argv[2], 0))
    s.settimeout(1.0)
    vals = {}
    for i, (name, addr) in enumerate(REGS.items(), start=1):
        try:
            v, st = readreg(s, ip, addr, i)
        except socket.timeout:
            v, st = None, "timeout"
        vals[name] = v
        print(f"{name:28s} @0x{addr:04X} = " + (f"0x{v:08X}" if v is not None else f"<error {st if isinstance(st,str) else hex(st)}>"))
    v = vals.get("Version")
    if v is not None:
        print(f"\nGigE Vision spec version implemented: {v >> 16}.{v & 0xFFFF}")
    cap = vals.get("GVCPCapability")
    if cap is not None:
        print("GVCP capabilities set:", ", ".join(n for m, n in CAP_BITS if cap & m) or "(none)")
    if cap is not None and cap & 0x00080000:
        print("-> device advertises IEEE 1588 PTP")
    if cap is not None and cap & 0x00020000:
        print("-> device advertises Scheduled Action Commands")
    tf_h, tf_l = vals.get("TimestampTickFreqHigh"), vals.get("TimestampTickFreqLow")
    if tf_h is not None and tf_l is not None:
        print(f"Timestamp tick frequency: {(tf_h << 32) | tf_l} Hz")

if __name__ == "__main__":
    main()
