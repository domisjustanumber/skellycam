import sys, socket, struct, time, collections
sys.path.insert(0, "/work/tests")
import gev_scratch_probe as P
g = P.Gvcp("127.0.0.1"); g.take_control()
_, _, xml = P.fetch_xml(g); toy = P.ToyNodeMap(xml, g)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16 << 20); s.bind(("127.0.0.1", 0))
g.write_reg(P.REG_SCP0_DEST, 0x7f000001); g.write_reg(P.REG_SCP0_PORT, s.getsockname()[1])
toy.set("AcquisitionStart", 1)
s.settimeout(0.5); seq = []
t = time.time()
while time.time() - t < 1.0:
    try: d = s.recv(65536)
    except socket.timeout: break
    st, bid, inf = struct.unpack_from(">HHI", d)
    seq.append(((inf >> 24) & 0x7F, bid, inf & 0xFFFFFF, len(d), st))
toy.set("AcquisitionStop", 0); g.release()
print("rcvbuf", s.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF))
print("ctype histogram", collections.Counter(x[0] for x in seq))
for x in seq[:3] + [y for y in seq if y[0] != 3][:8] + seq[-3:]:
    print(x)
