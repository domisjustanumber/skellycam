# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Windows timer-resolution probe. Opens no camera and changes nothing outside this process.

Records, before and after this process calls timeBeginPeriod(1):
- NtQueryTimerResolution (coarsest / finest / current global timer interval)
- how often GetSystemTimeAsFileTime and GetSystemTimePreciseAsFileTime actually change (step sizes)
- how long kernel32 Sleep(1) really takes
- whether the GlobalTimerResolutionRequests registry value is set

RUN: uv run --script research/usb_cameras/tools/timer_probe.py [--out results/windows/<host>/timer_resolution_<date>/result.json]
"""
import argparse, ctypes, datetime, json, platform, socket, statistics, subprocess, sys, time
from pathlib import Path

nt, mm, k32 = ctypes.WinDLL("ntdll"), ctypes.WinDLL("winmm"), ctypes.WinDLL("kernel32")


def resolution():
    a, b, c = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_ulong()
    nt.NtQueryTimerResolution(ctypes.byref(a), ctypes.byref(b), ctypes.byref(c))
    return {"coarsest_ms": a.value / 1e4, "finest_ms": b.value / 1e4, "current_ms": c.value / 1e4}


def filetime(fn):
    v = ctypes.c_ulonglong()
    fn(ctypes.byref(v))
    return v.value  # 100 ns units


def step_sizes_ms(fn, n=40):
    # spin and record each change of the clock value: the update interval, not the nominal resolution
    steps, last, t_end = [], filetime(fn), time.perf_counter() + 3
    while len(steps) < n and time.perf_counter() < t_end:
        v = filetime(fn)
        if v != last:
            steps.append((v - last) / 1e4)
            last = v
    return steps


def sleep1_ms(n=200):
    d = []
    for _ in range(n):
        t = time.perf_counter_ns()
        k32.Sleep(1)
        d.append((time.perf_counter_ns() - t) / 1e6)
    return {"p50_ms": round(statistics.median(d), 3), "min_ms": round(min(d), 3), "max_ms": round(max(d), 3), "n": n}


def snapshot(label):
    coarse = step_sizes_ms(k32.GetSystemTimeAsFileTime)
    precise = step_sizes_ms(k32.GetSystemTimePreciseAsFileTime)
    return {
        "label": label,
        "timer_resolution": resolution(),
        "GetSystemTimeAsFileTime_step_ms": {
            "p50": round(statistics.median(coarse), 3) if coarse else None,
            "distinct": sorted(set(round(x, 1) for x in coarse))[:8],
        },
        "GetSystemTimePreciseAsFileTime_step_ms_p50": round(statistics.median(precise), 5) if precise else None,
        "Sleep(1)": sleep1_ms(),
    }


def registry_value():
    r = subprocess.run(
        ["reg", "query", r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\kernel", "/v", "GlobalTimerResolutionRequests"],
        capture_output=True, text=True)
    return r.stdout.strip() or "not set"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    rec = {
        "test": "timer_probe",
        "platform": "windows",
        "hostname": socket.gethostname(),
        "utc_started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "command": " ".join(sys.argv),
        "environment": {"os": platform.platform(), "os_version": platform.version(), "python": sys.version},
        "cameras": [],
    }
    rec["before"] = snapshot("this process has not called timeBeginPeriod")
    mm.timeBeginPeriod(1)
    try:
        rec["after"] = snapshot("after timeBeginPeriod(1) in this process")
    finally:
        mm.timeEndPeriod(1)
    rec["GlobalTimerResolutionRequests"] = registry_value()
    text = json.dumps(rec, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
