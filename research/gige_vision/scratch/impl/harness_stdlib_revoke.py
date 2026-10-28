"""Scratch harness (not shipped): in-process viva fake revokes control mid-capture (camera-side heartbeat expiry);
gvsp_capture_report must report it, restore registers after re-taking control, and not crash.
usage: python harness_stdlib_revoke.py <gige_dir>"""
import sys, threading
sys.path.insert(0, sys.argv[1])
from viva_genicam.testing import FakeGigeCamera
import gvsp_capture_report as g
with FakeGigeCamera(width=320, height=240, fps=20) as fake:
    dest_before = fake.peek(0x0D18, 4).hex()
    threading.Timer(1.5, fake.revoke_control).start()
    rc = g.main(["--ip", "127.0.0.1", "--seconds", "4"])
    print("main() returned", rc, "| SCDA before", dest_before, "after", fake.peek(0x0D18, 4).hex(), "| controller after:", fake.controller())
