import sys
sys.path.insert(0, "/src")
from pyGigEVision import discover, GVCPClient
from pyGigEVision.genicam import parse_first_url
from pyGigEVision.standard import REG_FIRST_URL
cam = discover(timeout=1.0)[0]
with GVCPClient(cam["ip"]) as c:
    raw = c.read_mem(REG_FIRST_URL, 512)
    url = raw.split(b"\0")[0]
    print("FIRST_URL raw:", url)
    print("pyGigEVision parse_first_url ->", parse_first_url(raw))
    fn, a, s = url.decode().split(";")
    a, s = int(a, 16), int(s, 16)
    print("hex-parsed addr/size:", hex(a), s)
    xml = c.read_mem(a, s)
    open("/out/fake_camera.xml", "wb").write(xml)
    print("xml head:", xml[:120])
