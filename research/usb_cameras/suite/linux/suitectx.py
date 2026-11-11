"""The ``ctx`` passed to every Linux test module (suite/linux/tests/l_<name>.py: ``run(ctx) -> dict``).

Same field names as the Windows suite's ctx where they apply (out_dir, raw_dir, args, cameras, log, camcmd,
write); Linux-specific fields replace wincam with ``worker`` (linuxlib/camworker.py run by this interpreter) and
``helpers_dir`` (PEP 723 helpers run with ``uv run --script``).

Camera lock: the runner takes the same OS lock file as research/usb_cameras/tools/camlock.py
(research/usb_cameras/.camlock, fcntl.flock) IN-PROCESS, so the time spent waiting for the lock never counts
against a child's timeout (local_inventory.md camlock gotcha). ``camcmd`` = lock + child with timeout;
``camera_lock()`` holds it across several concurrent children (MULTI); ``run_child`` runs without the lock (for
commands that open no camera).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

LINUX_DIR = Path(__file__).resolve().parent
SUITE_DIR = LINUX_DIR.parent
RESEARCH_DIR = SUITE_DIR.parent
for _p in (str(SUITE_DIR), str(LINUX_DIR / "linuxlib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from common import procutil, rating, results  # noqa: E402
from common.topology_model import ModeAltCache  # noqa: E402
import sysfs  # noqa: E402

LOCK_PATH = RESEARCH_DIR / ".camlock"


class CamLock:
    """Re-entrant (per process) exclusive flock on research/usb_cameras/.camlock, compatible with camlock.py."""

    def __init__(self, path: Path = LOCK_PATH, timeout_s: float = 600.0, enabled: bool = True):
        self.path, self.timeout_s, self.enabled = path, timeout_s, enabled
        self.fd: int | None = None
        self.depth = 0
        self.mutex = threading.RLock()
        self.waits: list[float] = []

    def acquire(self) -> bool:
        if not self.enabled:
            return True
        with self.mutex:
            if self.depth:
                self.depth += 1
                return True
            import fcntl
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o666)
            t0 = time.monotonic()
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() - t0 > self.timeout_s:
                        os.close(fd)
                        return False
                    time.sleep(0.5)
            self.waits.append(round(time.monotonic() - t0, 3))
            self.fd, self.depth = fd, 1
            return True

    def release(self) -> None:
        if not self.enabled:
            return
        with self.mutex:
            if self.depth == 0:
                return
            self.depth -= 1
            if self.depth == 0 and self.fd is not None:
                os.close(self.fd)  # closing the fd drops the flock
                self.fd = None


@dataclass
class LinuxCtx:
    out_dir: Path
    raw_dir: Path
    args: argparse.Namespace
    cameras: list[dict[str, Any]]
    worker: list[str]                    # [python, .../camworker.py]
    helpers_dir: Path
    topology: dict[str, Any] | None = None
    mode_alt_cache: ModeAltCache = field(default_factory=ModeAltCache)
    lock: CamLock = field(default_factory=CamLock)
    log_file: Path | None = None
    env_facts: dict[str, Any] = field(default_factory=dict)   # filled by L-ENV (kernel features, journal access)
    shared: dict[str, Any] = field(default_factory=dict)      # results earlier tests leave for later ones
    _log_lock: threading.Lock = field(default_factory=threading.Lock)
    current_test: str | None = None

    # ------------------------------------------------------------------------------------------- basics
    @property
    def python_helpers_dir(self) -> Path:   # contract name used by the Windows ctx
        return self.helpers_dir

    def log(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}]" + (f" {self.current_test}:" if self.current_test else "") + f" {msg}"
        with self._log_lock:
            print(line, flush=True)
            if self.log_file:
                with self.log_file.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")

    def write(self, name: str, obj: Any) -> Path:
        """Write JSON into out_dir (name may contain sub folders; '.json' added if missing)."""
        if not name.endswith(".json"):
            name += ".json"
        return results.write_json(self.out_dir / name, obj)

    def new_result(self, test: str, cameras: list[dict] | None = None) -> dict[str, Any]:
        return results.new_result(test, platform="linux", command=sys.argv,
                                  cameras=[sysfs.camera_brief(c) for c in (cameras if cameras is not None
                                                                           else self.cameras)])

    @staticmethod
    def slug(cam: dict[str, Any] | str) -> str:
        key = cam if isinstance(cam, str) else cam["key"]
        return re.sub(r"[^A-Za-z0-9._-]+", "_", key)[:80]

    def test_dir(self, test: str, *parts: str) -> Path:
        p = self.out_dir / test.replace("-", "_").lower()
        for x in parts:
            p = p / x
        p.mkdir(parents=True, exist_ok=True)
        return p

    def raw_test_dir(self, test: str, *parts: str) -> Path:
        p = self.raw_dir / test.replace("-", "_").lower()
        for x in parts:
            p = p / x
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ------------------------------------------------------------------------------------------- children
    def run_child(self, argv: list[str], timeout_s: float, env: dict[str, str] | None = None) -> dict[str, Any]:
        full_env = None
        if env:
            full_env = dict(os.environ)
            full_env.update(env)
        r = procutil.run(argv, timeout_s, env=full_env)
        r["json"] = parse_json_stdout(r.get("stdout") or "")
        return r

    def camcmd(self, argv: list[str], timeout_s: float, env: dict[str, str] | None = None) -> dict[str, Any]:
        """Run a camera-opening child under the camera lock; the timeout applies to the child only."""
        if not self.lock.acquire():
            return {"argv": argv, "rc": 75, "stdout": "", "stderr": "camera lock not acquired",
                    "elapsed_s": 0, "timed_out": False, "killed": False, "spawn_error": "camlock timeout",
                    "json": None}
        try:
            return self.run_child(argv, timeout_s, env)
        finally:
            self.lock.release()

    @contextlib.contextmanager
    def camera_lock(self) -> Iterator[bool]:
        ok = self.lock.acquire()
        try:
            yield ok
        finally:
            if ok:
                self.lock.release()

    def camcmd_parallel(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Run several camera children concurrently under ONE lock hold. jobs: [{argv, timeout_s, delay_s, env}].
        Returns the procutil results in job order, each with 'started_at_s' (relative to the batch start)."""
        out: list[dict[str, Any] | None] = [None] * len(jobs)
        t0 = time.monotonic()

        def one(i: int, j: dict[str, Any]) -> None:
            if j.get("delay_s"):
                time.sleep(j["delay_s"])
            st = time.monotonic() - t0
            r = self.run_child(j["argv"], j["timeout_s"], j.get("env"))
            r["started_at_s"] = round(st, 3)
            out[i] = r

        with self.camera_lock() as ok:
            if not ok:
                return [{"argv": j["argv"], "rc": 75, "spawn_error": "camlock timeout", "json": None} for j in jobs]
            ths = [threading.Thread(target=one, args=(i, j), daemon=True) for i, j in enumerate(jobs)]
            for t in ths:
                t.start()
            for t in ths:
                t.join()
        return [r if r is not None else {"rc": None, "json": None, "spawn_error": "thread died"} for r in out]

    def worker_cmd(self, *args: Any) -> list[str]:
        return [*self.worker, *map(str, args)]

    def helper_cmd(self, name: str, *args: Any) -> list[str]:
        py = getattr(self.args, "helper_python", None) or "3.12"
        return ["uv", "run", "--quiet", "--python", py, "--script", str(self.helpers_dir / name), *map(str, args)]

    # ------------------------------------------------------------------------------------------- state
    def refresh_cameras(self) -> list[dict[str, Any]]:
        """Re-discover (sysfs only) and keep the selection; node paths change when a camera re-enumerates."""
        fresh = {c["key"]: c for c in sysfs.discover_cameras()}
        keep = []
        for c in self.cameras:
            n = fresh.get(c["key"])
            keep.append(n if n is not None else {**c, "missing": True})
        self.cameras = keep
        return keep

    def busy(self, cam: dict[str, Any]) -> dict[str, Any]:
        """Is another process holding or streaming this camera? holders from /proc (this user's processes) and the
        VS interface alt (non-zero = streaming isochronous right now, by anyone)."""
        nodes = [n for n in (cam.get("node"), cam.get("meta_node")) if n]
        h = sysfs.holders(nodes, exclude_pids=sysfs.ancestors_and_self())
        vs = sysfs.vs_interfaces(sysfs.P(cam["sysfs_dir"])) if cam.get("sysfs_dir") else []
        streaming = any((v.get("alt") or 0) > 0 for v in vs)
        others = [x for lst in h.values() for x in lst]
        return {"holders": h, "other_holders": others, "streaming_alt": [v.get("alt") for v in vs],
                "streamed_by_other": streaming, "in_use": streaming or bool(others)}

    def learn_alt(self, cam: dict[str, Any], mode: dict[str, Any], alt: int | None, source: str) -> None:
        """Record the granted alt of a mode opened ALONE (bandwidth_domain_model.md 5: the only way to learn it)."""
        if alt is None or not mode:
            return
        tab = {}
        for s in (cam.get("descriptors") or {}).get("streams") or []:
            for a in s.get("alt_table") or []:
                tab[a["alt"]] = a
        ent = tab.get(alt) or {}
        self.mode_alt_cache.put(cam["vid"], cam["pid"], cam.get("bcd_device"), mode.get("fourcc", "MJPG"),
                                int(mode["w"]), int(mode["h"]), float(mode["fps"]), int(alt),
                                ent.get("max_packet"), ent.get("mult"), source=source,
                                utc=results.utc_now_iso())

    def kernel(self) -> tuple[int, int]:
        return sysfs.kernel_version()

    def scaled(self, full: Any, quick: Any) -> Any:
        return quick if getattr(self.args, "quick", False) else full


def parse_json_stdout(text: str) -> dict[str, Any] | None:
    """The child's single JSON object (last parsable line of stdout)."""
    for line in reversed([x for x in text.strip().splitlines() if x.strip()]):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def child_outcome(r: dict[str, Any]) -> dict[str, Any]:
    """Compact, JSON-safe record of a child run (no big stdout)."""
    j = r.get("json") or {}
    return {"rc": r.get("rc"), "timed_out": r.get("timed_out"), "killed": r.get("killed"),
            "elapsed_s": r.get("elapsed_s"), "spawn_error": r.get("spawn_error"),
            "error": j.get("error") if isinstance(j, dict) else None,
            "stderr_tail": (r.get("stderr") or "")[-1500:] if (r.get("rc") not in (0,) or r.get("timed_out"))
            else None, "argv": r.get("argv")}


def combine(per_camera: dict[str, dict[str, Any]], label: str) -> dict[str, Any]:
    """One verdict from per-camera ratings: worst tested rating; criteria = one line per camera."""
    crit = [{"criterion": f"{label}: {k}", "met": (None if v.get("rating") == "untested" else v.get("rating") == "yes"),
             "detail": v.get("rating") + (f" ({v['note']})" if v.get("note") else "")} for k, v in per_camera.items()]
    r = rating.worst(per_camera.values()) if per_camera else "untested"
    return {"rating": r, "criteria": crit, "evidence": {"per_camera": per_camera}}


def errno_from_text(text: str) -> int | None:
    """errno from an OpenCV DEBUG log line ('... VIDIOC_STREAMON: errno=28 ...')."""
    m = re.search(r"STREAMON[^\n]*?errno=(\d+)", text or "")
    return int(m.group(1)) if m else None


Callback = Callable[[str], None]
