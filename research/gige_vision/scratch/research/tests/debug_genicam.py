import sys, traceback
sys.path.insert(0, "/work/tests")
import gev_scratch_probe as P
from genicam.genapi import NodeMap
g = P.Gvcp("127.0.0.1")
_, _, xml = P.fetch_xml(g)
nm = NodeMap()
try:
    nm.load_xml_from_string(xml.decode())
    print("loaded; device name:", nm.device_info.vendor_name if hasattr(nm, "device_info") else "?")
except Exception:
    traceback.print_exc()
try:
    nm2 = P.official_nodemap(xml, g)
except Exception:
    traceback.print_exc()
