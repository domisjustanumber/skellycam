"""Scratch harness (not shipped): viva_sync_capture_test.main() with --fake-cameras 1 and SIMULATED GenICam PTP
nodes (PtpEnable/PtpDataSetLatch/PtpStatus/PtpOffsetFromMaster) to exercise the PTP-lock path.
usage: python harness_viva_ptp_sim.py <gige_dir> lock|nolock <outdir>"""
import sys
sys.path.insert(0, sys.argv[1])
import viva_sync_capture_test as v

MODE, OUT = sys.argv[2], sys.argv[3]
state = {"PtpEnable": "false", "n": 0}
orig_open, orig_get, orig_set, orig_exec = v.open_cameras, v.VCam.get, v.VCam.set, v.VCam.execute

def open_cameras(*a, **k):
    cams = orig_open(*a, **k)
    for c in cams:
        c.nodes |= {"PtpEnable", "PtpDataSetLatch", "PtpStatus", "PtpOffsetFromMaster"}
    return cams

def get(self, name):
    if name == "PtpEnable":
        return state["PtpEnable"]
    if name == "PtpStatus":
        if state["PtpEnable"] != "true":
            return "Disabled"
        return "Master" if MODE == "lock" and state["n"] > 2 else "Listening"
    if name == "PtpOffsetFromMaster":
        return "0"
    return orig_get(self, name)

def set_(self, name, value, remember=True):
    if name == "PtpEnable":
        if remember: self.changed.append((name, state["PtpEnable"]))
        state["PtpEnable"] = value
        return
    return orig_set(self, name, value, remember)

def execute(self, name):
    if name == "PtpDataSetLatch":
        state["n"] += 1
        return
    return orig_exec(self, name)

v.open_cameras, v.VCam.get, v.VCam.set, v.VCam.execute = open_cameras, get, set_, execute
rc = v.main(["--fake-cameras", "1", "--duration", "2", "--ptp-timeout", "6", "--stable-s", "1", "--restore-ptp", "--out", OUT])
print("main() returned", rc, "PtpEnable after restore:", state["PtpEnable"])
