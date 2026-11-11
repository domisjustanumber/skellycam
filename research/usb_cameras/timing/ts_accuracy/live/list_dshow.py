# /// script
# requires-python = "==3.12.*"
# dependencies = ["opencv-contrib-python==4.12.*", "cv2-enumerate-cameras>=1.2.2"]
# ///
"""List DirectShow camera indices with names and VID/PID (as skellycam's enumerator sees them). Opens no stream."""
import json
import sys

import cv2
from cv2_enumerate_cameras import enumerate_cameras

out = []
for c in enumerate_cameras(cv2.CAP_DSHOW):
    out.append({"index": c.index, "name": c.name, "vid": f"{c.vid:04X}" if c.vid else None,
                "pid": f"{c.pid:04X}" if c.pid else None, "path": c.path})
json.dump({"opencv": cv2.__version__, "cameras": out}, sys.stdout, indent=1)
print()
