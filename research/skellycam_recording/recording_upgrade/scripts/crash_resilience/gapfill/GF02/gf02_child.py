# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""GF02 Part B writer child (functional; the pacing sleep only shapes the feed, nothing is timed or reported).

usage: gf02_child.py <stem> <container> <pts_mode> <kill_at> <method>
  Writes c930e_720p_flash frames looped through GF02Writer (recwriter sidecar), frame i fed at t0 + i/30 s.
  Capture timestamps = real c930e intervals looped (jp_common.jitter_timestamps_ns) + 1e12 ns, so pts are deterministic.
  stdout: "PID <pid>" first, then "M <n>" after every write() returns (mux [+ empty packet] + sidecar record flushed).
  method "exit": os._exit(1) right after "M <kill_at>" (no close, no finally).
  method "term": keeps writing; the parent TerminateProcess()es it after seeing "M <kill_at>".
  Safety stop: after kill_at + 300 frames it prints NOKILL and calls os._exit(2) (still no close).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gf02_common as G  # noqa: E402


def say(s: str) -> None:
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


def main() -> None:
    say(f"PID {os.getpid()}")
    stem, cont, mode, kill_at, method = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
    frames = G.C.load_set("c930e_720p_flash")
    n_max = kill_at + 300
    ts = G.C.jitter_timestamps_ns(n_max)
    w = G.GF02Writer(stem, 1280, 720, cont, pts_mode=mode)
    t0 = time.perf_counter()
    for i in range(n_max):
        dt = t0 + i / 30 - time.perf_counter()
        if dt > 0:
            time.sleep(dt)
        w.write(frames[i % len(frames)], i, 1_000_000_000_000 + ts[i])
        say(f"M {i + 1}")
        if method == "exit" and i + 1 == kill_at:
            os._exit(1)
    say("NOKILL")
    os._exit(2)


if __name__ == "__main__":
    main()
