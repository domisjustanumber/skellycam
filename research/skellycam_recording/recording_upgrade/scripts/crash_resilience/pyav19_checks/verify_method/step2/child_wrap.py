"""Run writer_child.py with the intra NVENC payloads (as bench_fragment_overhead.py:42-46) registered."""
import runpy, sys
SCR = "C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade/scripts/crash_resilience"
sys.path.insert(0, SCR)
import common_cr as cc
cc.PAYLOADS.setdefault("h264nv_intra", {"codec": "h264_nvenc", "pix_fmt": "yuv420p", "gop": 0, "options": {
    "preset": "p4", "tune": "ll", "rc": "constqp", "qp": "14", "i_qfactor": "1", "i_qoffset": "0", "bf": "0"}})
cc.PAYLOADS.setdefault("hevcnv_intra", {"codec": "hevc_nvenc", "pix_fmt": "yuv420p", "gop": 0, "options": {
    "preset": "p4", "tune": "ll", "rc": "constqp", "qp": "11", "i_qfactor": "1", "i_qoffset": "0", "bf": "0"}})
sys.argv = [SCR + "/writer_child.py"] + sys.argv[1:]
runpy.run_path(SCR + "/writer_child.py", run_name="__main__")
