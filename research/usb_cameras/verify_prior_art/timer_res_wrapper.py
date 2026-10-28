# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "gstreamer-bundle==1.28.7; sys_platform != 'linux'",
#   "pillow>=10",
# ]
# ///
"""Verifier helper (Windows only): run prior_art/gst_probe.py in-process after timeBeginPeriod(1).

Purpose: test whether the ~16 ms quantization of frame arrival times seen by gst_probe is caused by
the Windows timer resolution of the capturing process. ksvideosrc runs the KS read loop in-process,
so a process-local timer-resolution change would affect it if the cause were a timer wait.

RUN (shared Windows machine, under camlock):
  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/verify_prior_art/timer_res_wrapper.py --period-ms 1 -- --capture --source ksvideosrc --seconds 6
Writes gst_probe's normal output dir plus results/windows/<host>/verify_prior_art/timer_res_<source>.json
(timer resolution before/after, in 100 ns units, via NtQueryTimerResolution).
"""
import ctypes, json, runpy, socket, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent / "prior_art" / "gst_probe.py"


def q():
    mn, mx, cur = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_ulong()
    ctypes.WinDLL("ntdll").NtQueryTimerResolution(ctypes.byref(mn), ctypes.byref(mx), ctypes.byref(cur))
    return {"coarsest_100ns": mn.value, "finest_100ns": mx.value, "current_100ns": cur.value}


def main():
    argv = sys.argv[1:]
    period = 1
    if argv[:1] == ["--period-ms"]:
        period = int(argv[1]); argv = argv[2:]
    if argv[:1] == ["--"]:
        argv = argv[1:]
    rec = {"before": q(), "period_ms_requested": period}
    rec["timeBeginPeriod_ret"] = ctypes.WinDLL("winmm").timeBeginPeriod(period)
    rec["after"] = q()
    src = argv[argv.index("--source") + 1] if "--source" in argv else "mfvideosrc"
    sys.argv = [str(PROBE)] + argv
    try:
        runpy.run_path(str(PROBE), run_name="__main__")
    except SystemExit:
        pass
    finally:
        rec["at_end"] = q()
        ctypes.WinDLL("winmm").timeEndPeriod(period)
        import os  # USBCAM_RESULTS_DIR (optional) redirects output so a rerun keeps cited results
        out = (Path(os.environ["USBCAM_RESULTS_DIR"]) if os.environ.get("USBCAM_RESULTS_DIR")
               else HERE.parent / "results" / "windows" / socket.gethostname()) / "verify_prior_art"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"timer_res_{src}.json").write_text(json.dumps(rec, indent=2))
        print(json.dumps(rec))


if __name__ == "__main__":
    main()
