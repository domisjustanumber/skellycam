# /// script
# requires-python = ">=3.10"
# dependencies = ["pyglet==2.0.17"]
# ///
"""Cross-platform (Linux/macOS/Windows) screen-flash light source -- Python fallback for flash_timecode.exe.

DRAFT for Linux/macOS -- NOT YET RUN there. Windows uses timing/src/flash_timecode.cpp (DXGI vblank statistics).

Full-screen window on --screen showing a black/white sequence identical in structure to flash_timecode.exe
(seeded PRNG, hold 2..6 refreshes), vsync on. pyglet gives no vblank timestamps, so each flip is logged with the host
monotonic time right after flip() returns (time.monotonic_ns: CLOCK_MONOTONIC on Linux, mach_absolute_time on macOS
-- the same clocks as the capture drafts). flash_analyze.py then fits a periodic vblank clock to those times
(t_on = a + P*n); any compositor latency is a constant that cancels between cameras but NOT in absolute offsets.
Missed vsyncs show up as gaps (> 1.5 P) and are reported.

Run:  uv run --script research/usb_cameras/timing/scripts/flash_timecode_py.py --out results/<platform>/<host>/timing/flash_display_<n> --screen 0 --seconds 30
      (--list prints screens). Writes display.jsonl + display.session.json in the flash_timecode format.
Needs: a desktop session; on Linux X11 or XWayland (Wayland compositors may ignore exclusive full-screen; note it).
"""
import argparse
import json
import platform
import random
import socket
import sys
import time
from pathlib import Path

import pyglet
from pyglet import gl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out"); ap.add_argument("--screen", type=int, default=0); ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--min-hold", type=int, default=2); ap.add_argument("--max-hold", type=int, default=6)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    screens = pyglet.canvas.get_display().get_screens()
    if a.list:
        print(json.dumps([{"screen": i, "x": s.x, "y": s.y, "w": s.width, "h": s.height} for i, s in enumerate(screens)], indent=2)); return 0
    if not a.out:
        print("--out required", file=sys.stderr); return 2
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    scr = screens[a.screen]
    win = pyglet.window.Window(fullscreen=True, screen=scr, vsync=True)
    win.set_mouse_visible(False)
    rng = random.Random(a.seed)
    state = {"level": 0, "rem": 0, "i": 0}
    fl = (out / "display.jsonl").open("w")
    t0 = time.monotonic_ns()
    while not win.has_exit and (time.monotonic_ns() - t0) / 1e9 < a.seconds:
        win.dispatch_events()
        if state["rem"] <= 0:
            state["level"] = 1 - state["level"]; state["rem"] = rng.randint(a.min_hold, a.max_hold)
        state["rem"] -= 1
        v = float(state["level"])
        gl.glClearColor(v, v, v, 1.0); win.clear()
        tc = time.monotonic_ns(); win.flip(); gl.glFinish(); tr = time.monotonic_ns()
        state["i"] += 1
        fl.write(json.dumps({"type": "present", "i": state["i"] - 1, "present_count": state["i"], "level": state["level"],
                             "present_call_ns": tc, "present_return_ns": tr}) + "\n")
    fl.close(); win.close()
    (out / "display.session.json").write_text(json.dumps({
        "tool": "flash_timecode_py", "output": f"screen{a.screen}", "size": [scr.width, scr.height], "seed": a.seed,
        "min_hold": a.min_hold, "max_hold": a.max_hold, "presents": state["i"], "hostname": socket.gethostname(),
        "platform": sys.platform, "os": platform.platform(), "pyglet": pyglet.version, "timing": "flip-return times (no vblank stats)"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
