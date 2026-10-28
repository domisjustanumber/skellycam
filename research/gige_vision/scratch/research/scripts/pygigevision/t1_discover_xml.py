import sys, time, logging
sys.path.insert(0, "/src")
import pyGigEVision
from pyGigEVision import discover, bootstrap
print("pyGigEVision", pyGigEVision.__version__)
t=time.time(); cams = discover(timeout=1.5); print(f"discover() {time.time()-t:.2f}s ->", cams)
if not cams: sys.exit(2)
t=time.time(); client, xml = bootstrap(cams[0]["ip"]); print(f"bootstrap() {time.time()-t:.2f}s xml bytes={len(xml)}")
open("/out/fake_camera.xml","wb").write(xml)
client.disconnect()
