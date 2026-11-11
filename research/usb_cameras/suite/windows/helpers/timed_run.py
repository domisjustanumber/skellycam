# /// script
# requires-python = ">=3.10"
# ///
"""Run one command with a hard timeout that kills its whole process tree, then exit with its exit code.

This is the INNER half of ``SuiteCtx.camcmd``: the runner starts

    uv run --script tools/camlock.py --timeout-s 600 -- <python.exe> helpers/timed_run.py --timeout-s T -- <argv...>

so the time spent waiting for the camera lock does NOT count against the camera command's timeout (local_inventory
section 3: "an outer timeout also counts the time spent waiting for the lock"; put the timeout inside, on the child).

Behaviour:
  * the child's stdout is passed through unchanged (it is usually one JSON object);
  * the child's stderr is passed through, followed by ONE final stderr line
        @@TIMED_RUN@@ {"rc": .., "timed_out": .., "killed": .., "elapsed_s": .., "kill_method": .., "t_start_unix": ..,
                       "spawn_error": ..}
    which camcmd parses and strips;
  * exit code: the child's exit code; 124 when the child timed out and was killed; 127 when it could not start.

Stdlib only (uses suite/common/procutil.run, which kills the whole tree via a Job Object on Windows).
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

SUITE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SUITE_DIR))
from common import procutil  # noqa: E402

MARK = "@@TIMED_RUN@@"


def main(argv: list[str]) -> int:
    timeout_s = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--timeout-s":
            timeout_s = float(argv[i + 1])
            i += 2
            continue
        if a == "--":
            i += 1
            break
        break
    cmd = argv[i:]
    if timeout_s is None or not cmd:
        print("usage: timed_run.py --timeout-s T -- <command...>", file=sys.stderr)
        return 2
    exe = cmd[0]
    if not Path(exe).is_absolute():
        found = shutil.which(exe)
        if found:
            cmd = [found] + cmd[1:]
    t_unix = time.time()
    r = procutil.run(cmd, timeout_s=timeout_s)
    if r["stdout"]:
        sys.stdout.write(r["stdout"])
        sys.stdout.flush()
    if r["stderr"]:
        sys.stderr.write(r["stderr"])
        if not r["stderr"].endswith("\n"):
            sys.stderr.write("\n")
    info = {k: r.get(k) for k in ("rc", "timed_out", "killed", "elapsed_s", "kill_method", "spawn_error", "pid")}
    info["t_start_unix"] = t_unix
    info["timeout_s"] = timeout_s
    sys.stderr.write(f"{MARK} {json.dumps(info)}\n")
    sys.stderr.flush()
    if r["timed_out"]:
        return 124
    if r["rc"] is None:
        return 127
    rc = int(r["rc"])
    # the exact code (e.g. 0xC0000005 crashes, negative POSIX signals) is in the @@TIMED_RUN@@ line
    return rc if 0 <= rc < 2 ** 31 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
