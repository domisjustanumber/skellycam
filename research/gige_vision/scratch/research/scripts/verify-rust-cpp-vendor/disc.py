import socket, struct
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1); s.settimeout(2)
s.sendto(struct.pack(">BBHHH", 0x42, 0x11, 0x0002, 0, 1), ("255.255.255.255", 3956))
try:
    while True:
        d, a = s.recvfrom(1500); print("DISCOVERY_ACK from", a, "opcode=0x%04x" % struct.unpack(">H", d[2:4])[0], d[0x48:0x68].split(b"\0")[0])
except socket.timeout: print("done")
