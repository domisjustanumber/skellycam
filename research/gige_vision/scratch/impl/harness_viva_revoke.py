"""Scratch harness (not shipped): revoke control mid-stream (as a camera does after a heartbeat timeout) and check
viva_sync_capture_test reports it and still writes its outputs. usage: python harness_viva_revoke.py <gige_dir> <outdir>"""
import sys, threading
sys.path.insert(0, sys.argv[1])
import viva_sync_capture_test as v
orig_open = v.open_cameras
def open_cameras(vg, args, rep, fakes):
    cams = orig_open(vg, args, rep, fakes)
    threading.Timer(1.5, fakes[0].revoke_control).start()
    return cams
v.open_cameras = open_cameras
rc = v.main(["--fake-cameras", "1", "--skip-ptp", "--duration", "3", "--out", sys.argv[2]])
print("main() returned", rc)
