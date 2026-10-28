# /// script
# requires-python = ">=3.10"
# dependencies = ["pupil-labs-uvc==1.0.8"]
# ///
"""Check pupil-labs libuvc's host-clock helpers inside the shipped Windows wheel (no camera needed).

Source being tested (pupil-labs/libuvc @ 949cb4734ae91feb878f4c363db52cfe2c86d68f, the submodule
pinned by pyuvc v1.0.8), src/stream.c:

    void get_precise_timestamp_freq(int64_t *perf_freq)
    {
    #ifdef WIN32
      LARGE_INTEGER li;
      QueryPerformanceFrequency(&li);
      perf_freq = li.QuadPart;          // <- assigns the pointer, *perf_freq is never written
    ...
    extern inline int64_t get_host_time_us(int64_t ts)
    { int64_t freq; get_precise_timestamp_freq(&freq); int64_t time_us = (ts * MILLION) / freq; ...

get_host_time_us() converts the QPC tick taken when an isochronous transfer completed into
microseconds; pyuvc uses it to anchor frame.timestamp. The wheel's uvc.dll exports these helpers
(built with WINDOWS_EXPORT_ALL_SYMBOLS), so we call them directly with ctypes.

Run:  uv run --script research/usb_cameras/libusb/pyuvc/pyuvc_windows_clock_check.py
Writes: research/usb_cameras/results/windows/<hostname>/pyuvc_clock_check/result.json
"""
import ctypes
import datetime as dt
import importlib.metadata as md
import json
import os
import platform
import socket
import sys
from pathlib import Path


def main() -> int:
    if os.name != "nt":
        print("Windows-only check", file=sys.stderr)
        return 1
    import uvc  # loads the bundled libusb/pthreads DLLs

    # uvc/bin/uvc.dll (shipped in the wheel, same build as the statically-linked copy inside
    # uvc_bindings.pyd) imports the *unmangled* names pthreadVC2.dll / libusb-1.0.dll, while
    # delvewheel only ships mangled copies. Copy them under their plain names to a temp dir.
    import shutil
    import tempfile

    dll_path = Path(uvc.__file__).parent / "bin" / "uvc.dll"
    libs_dir = Path(uvc.__file__).parent.parent / "pupil_labs_uvc.libs"
    tmp = Path(tempfile.mkdtemp(prefix="pyuvc_clock_"))
    for f in libs_dir.glob("*.dll"):
        plain = f.name.split("-")[0] + ".dll" if f.name.startswith("pthreadVC2") else None
        if f.name.startswith("libusb-1.0-"):
            plain = "libusb-1.0.dll"
        if plain:
            shutil.copy2(f, tmp / plain)
    os.add_dll_directory(str(tmp))
    lib = ctypes.CDLL(str(dll_path))
    lib.get_precise_timestamp_freq.argtypes = [ctypes.POINTER(ctypes.c_int64)]
    lib.get_precise_timestamp.argtypes = [ctypes.POINTER(ctypes.c_int64)]
    lib.get_host_time_us.argtypes = [ctypes.c_int64]
    lib.get_host_time_us.restype = ctypes.c_int64

    k32 = ctypes.windll.kernel32
    qpf = ctypes.c_int64()
    k32.QueryPerformanceFrequency(ctypes.byref(qpf))

    sentinels = [0x1111, 123456789, -42]
    freq_results = []
    for s in sentinels:
        f = ctypes.c_int64(s)
        lib.get_precise_timestamp_freq(ctypes.byref(f))
        freq_results.append({"sentinel_in": s, "value_out": f.value, "unchanged": f.value == s})

    ts = ctypes.c_int64()
    lib.get_precise_timestamp(ctypes.byref(ts))
    expected_us = ts.value * 1_000_000 // qpf.value
    conv = []
    for _ in range(5):
        try:
            got = lib.get_host_time_us(ts.value)
            conv.append(got)
        except OSError as e:  # e.g. integer divide by zero if the stack slot happened to be 0
            conv.append(repr(e))

    res = {
        "test": "pyuvc_windows_clock_check",
        "platform": "windows",
        "hostname": socket.gethostname(),
        "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(),
        "command": "uv run --script research/usb_cameras/libusb/pyuvc/pyuvc_windows_clock_check.py",
        "environment": {"os": platform.platform(), "python": sys.version, "pupil-labs-uvc": md.version("pupil-labs-uvc"), "uvc_dll": str(dll_path)},
        "cameras": [],
        "QueryPerformanceFrequency": qpf.value,
        "get_precise_timestamp_freq": freq_results,
        "get_precise_timestamp_qpc_ticks": ts.value,
        "expected_host_time_us": expected_us,
        "get_host_time_us_results": conv,
        "get_host_time_us_correct": all(isinstance(c, int) and abs(c - expected_us) <= 1 for c in conv),
        "freq_never_written": all(r["unchanged"] for r in freq_results),
    }
    out = Path(__file__).resolve().parents[2] / "results" / "windows" / socket.gethostname() / "pyuvc_clock_check"
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
