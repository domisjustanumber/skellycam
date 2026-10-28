# /// script
# requires-python = ">=3.10"
# ///
"""Sample which top-level window is visible at a grid of points on a monitor rect, every --period s for --seconds.

Usage: window_cover_check.py --rect L,T,R,B --seconds 40 --out cover.json [--expect flash_timecode.exe]
Writes per-sample owner process names at each point (WindowFromPoint -> GetAncestor(GA_ROOT)) plus the foreground window,
and a summary: fraction of samples where every point is owned by the expected process.
"""
import argparse, ctypes, ctypes.wintypes as wt, json, time

u32 = ctypes.windll.user32; k32 = ctypes.windll.kernel32
try:
    u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2, same as flash_timecode
except Exception:
    pass
u32.WindowFromPoint.restype = wt.HWND; u32.WindowFromPoint.argtypes = [wt.POINT]
u32.GetAncestor.restype = wt.HWND; u32.GetAncestor.argtypes = [wt.HWND, ctypes.c_uint]
u32.GetForegroundWindow.restype = wt.HWND


def owner(hwnd):
    if not hwnd:
        return None
    pid = wt.DWORD(); u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = k32.OpenProcess(0x1000, False, pid.value)
    name = None
    if h:
        buf = ctypes.create_unicode_buffer(520); n = wt.DWORD(520)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            name = buf.value.split("\\")[-1]
        k32.CloseHandle(h)
    cls = ctypes.create_unicode_buffer(256); u32.GetClassNameW(hwnd, cls, 256)
    return f"{name}|{cls.value}"


ap = argparse.ArgumentParser()
ap.add_argument("--rect", required=True); ap.add_argument("--seconds", type=float, default=40)
ap.add_argument("--period", type=float, default=0.5); ap.add_argument("--out", required=True)
ap.add_argument("--expect", default="flash_timecode.exe")
a = ap.parse_args()
L, T, R, B = [int(x) for x in a.rect.split(",")]
pts = [(L + (R - L) * fx // 10, T + (B - T) * fy // 10) for fx in (1, 3, 5, 7, 9) for fy in (1, 3, 5, 7, 9)]
samples = []
t0 = time.time()
while time.time() - t0 < a.seconds:
    owners = [owner(u32.GetAncestor(u32.WindowFromPoint(wt.POINT(x, y)), 2)) for x, y in pts]
    samples.append({"t": round(time.time() - t0, 2), "owners": owners, "foreground": owner(u32.GetForegroundWindow())})
    time.sleep(a.period)
ok = [all(o and o.startswith(a.expect + "|") for o in s["owners"]) for s in samples]
first_ok = next((s["t"] for s, k in zip(samples, ok) if k), None)
counts = {}
for s in samples:
    for o in s["owners"]:
        counts[o] = counts.get(o, 0) + 1
res = {"rect": [L, T, R, B], "points": pts, "n_samples": len(samples), "expect": a.expect,
       "fraction_all_points_expected": sum(ok) / max(1, len(samples)), "first_all_ok_t": first_ok,
       "all_ok_after_first": all(ok[ok.index(True):]) if True in ok else False,
       "owner_counts": counts, "samples": samples}
open(a.out, "w").write(json.dumps(res, indent=1))
print(json.dumps({k: v for k, v in res.items() if k not in ("samples", "points")}))
