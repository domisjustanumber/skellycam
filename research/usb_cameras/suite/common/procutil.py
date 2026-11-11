"""Run a child process with a hard timeout that kills the WHOLE process tree (stdlib only, any OS).

Every camera call in the suites goes through ``run()``: a camera that hangs (the Razer Kiyo Pro stops answering
control requests; a synchronous MF ReadSample has no timeout) must become a recorded result, never a hung runner.

    from common import procutil
    r = procutil.run([exe, "capture", ...], timeout_s=30)
    r -> {"argv", "rc", "stdout", "stderr", "elapsed_s", "timed_out", "killed", "pid", "spawn_error",
          "kill_method"}

Guarantees:
- never raises on child failure (non-zero exit, crash, missing executable, timeout); ``rc`` is None when the
  process could not be started.
- on timeout the whole tree is killed: on Windows the child is started suspended, put in a Job Object with
  JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, then resumed, and the job is terminated on timeout (``taskkill /T /F`` is
  used as a fallback). Grandchildren (e.g. ``camlock.py`` -> ``uv`` -> python -> camera exe) die with it, so no
  orphan keeps holding a camera. On POSIX the child gets its own session/process group, which receives SIGKILL.
- the Windows job also kills leftover grandchildren when the direct child exits normally (kill-on-close).
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

_IS_WIN = sys.platform == "win32"


# ---------------------------------------------------------------------------------------------------------- Windows
class _WinJob:
    """Minimal Job Object wrapper (ctypes). Any failure leaves ``ok`` False and the caller falls back to taskkill."""

    JobObjectExtendedLimitInformation = 9
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    PROCESS_ALL_ACCESS = 0x1F0FFF

    def __init__(self) -> None:
        self.ok = False
        self.handle = None
        try:
            import ctypes
            from ctypes import wintypes
            self._ct = ctypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._k32 = k32
            k32.CreateJobObjectW.restype = wintypes.HANDLE
            k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            k32.CloseHandle.argtypes = [wintypes.HANDLE]

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount",
                                                              "OtherOperationCount", "ReadTransferCount",
                                                              "WriteTransferCount", "OtherTransferCount")]

            class BASIC(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class EXTENDED(ctypes.Structure):
                _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS),
                            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

            h = k32.CreateJobObjectW(None, None)
            if not h:
                return
            info = EXTENDED()
            info.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(h, self.JobObjectExtendedLimitInformation, ctypes.byref(info),
                                               ctypes.sizeof(info)):
                k32.CloseHandle(h)
                return
            self.handle = h
            self.ok = True
        except Exception:
            self.ok = False

    def assign(self, proc_handle: int) -> bool:
        if not self.ok:
            return False
        try:
            from ctypes import wintypes
            return bool(self._k32.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(proc_handle))))
        except Exception:
            return False

    def terminate(self) -> bool:
        if not self.ok:
            return False
        try:
            return bool(self._k32.TerminateJobObject(self.handle, 1))
        except Exception:
            return False

    def close(self) -> None:
        if self.ok and self.handle:
            try:
                self._k32.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None
            self.ok = False


def _nt_resume(proc_handle: int) -> bool:
    """Resume a process created with CREATE_SUSPENDED (subprocess closes the thread handle, so use NtResumeProcess)."""
    try:
        import ctypes
        from ctypes import wintypes
        ntdll = ctypes.WinDLL("ntdll")
        ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
        ntdll.NtResumeProcess.restype = ctypes.c_long
        return ntdll.NtResumeProcess(wintypes.HANDLE(int(proc_handle))) == 0
    except Exception:
        return False


def _taskkill_tree(pid: int) -> bool:
    try:
        r = subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except Exception:
        return False


# ------------------------------------------------------------------------------------------------------------- API
def _decode(b: bytes | None) -> str:
    if not b:
        return ""
    for enc in ("utf-8",):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", errors="replace")


def run(argv: Sequence[str], timeout_s: float, cwd: str | os.PathLike | None = None,
        env: Mapping[str, str] | None = None, stdin_data: bytes | None = None) -> dict[str, Any]:
    """Run ``argv`` (no shell) with a timeout; kill the whole tree on timeout. Never raises on child failure.

    Returns {"argv", "rc", "stdout", "stderr", "elapsed_s", "timed_out", "killed", "pid", "spawn_error",
    "kill_method"}. ``rc`` is the exit code (None if the process never started). stdout/stderr are decoded
    as UTF-8 with replacement. ``env`` replaces the environment when given (merge with os.environ yourself).
    """
    argv = [str(a) for a in argv]
    out: dict[str, Any] = {"argv": argv, "rc": None, "stdout": "", "stderr": "", "elapsed_s": 0.0,
                           "timed_out": False, "killed": False, "pid": None, "spawn_error": None,
                           "kill_method": None}
    t0 = time.monotonic()
    job = None
    kwargs: dict[str, Any] = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                                  cwd=str(cwd) if cwd else None, env=dict(env) if env is not None else None)
    if _IS_WIN:
        job = _WinJob()
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
        if job.ok:
            flags |= 0x4  # CREATE_SUSPENDED: assign to the job before the child can spawn anything
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    try:
        p = subprocess.Popen(argv, **kwargs)
    except Exception as e:  # missing exe, bad cwd, permission ...
        out["spawn_error"] = f"{type(e).__name__}: {e}"
        out["stderr"] = out["spawn_error"]
        out["elapsed_s"] = round(time.monotonic() - t0, 4)
        if job:
            job.close()
        return out
    out["pid"] = p.pid
    if _IS_WIN and job is not None and job.ok:
        assigned = job.assign(p._handle)  # type: ignore[attr-defined]
        if not _nt_resume(p._handle):  # type: ignore[attr-defined]
            # Could not resume: kill it rather than leave a suspended process behind, then report.
            try:
                p.kill()
            except Exception:
                pass
            p.wait()
            out["spawn_error"] = "NtResumeProcess failed after CREATE_SUSPENDED"
            out["rc"] = p.returncode
            out["elapsed_s"] = round(time.monotonic() - t0, 4)
            job.close()
            return out
        if not assigned:
            job.close()
            job = None
    try:
        so, se = p.communicate(input=stdin_data, timeout=max(0.0, float(timeout_s)))
        out["stdout"], out["stderr"] = _decode(so), _decode(se)
    except subprocess.TimeoutExpired:
        out["timed_out"] = True
        out["kill_method"] = _kill_tree(p, job)
        out["killed"] = True
        try:
            so, se = p.communicate(timeout=10)
            out["stdout"], out["stderr"] = _decode(so), _decode(se)
        except Exception as e:  # pipes held open by something that survived: give up on output
            out["stderr"] = f"(output not collected after kill: {type(e).__name__})"
            try:
                p.kill()
            except Exception:
                pass
    except Exception as e:  # pragma: no cover - unexpected communicate failure
        out["stderr"] = f"{type(e).__name__}: {e}"
        out["kill_method"] = _kill_tree(p, job)
        out["killed"] = True
    finally:
        try:
            p.wait(timeout=10)
        except Exception:
            pass
        out["rc"] = p.returncode
        if job is not None:
            job.close()  # kill-on-close: reaps any grandchild left behind
    out["elapsed_s"] = round(time.monotonic() - t0, 4)
    return out


def _kill_tree(p: subprocess.Popen, job: _WinJob | None) -> str:
    """Kill the child and all its descendants. Returns the method that was used."""
    if _IS_WIN:
        methods = []
        if job is not None and job.ok and job.terminate():
            methods.append("job")
        if p.poll() is None or not methods:
            if _taskkill_tree(p.pid):
                methods.append("taskkill")
        if p.poll() is None:
            try:
                p.kill()
                methods.append("kill")
            except Exception:
                pass
        return "+".join(methods) or "none"
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        return "killpg"
    except Exception:
        try:
            p.kill()
            return "kill"
        except Exception:
            return "none"


class Background:
    """A child started in the background with the same whole-tree kill as ``run()`` (Job Object on Windows, own
    session on POSIX). stdout goes to a file (or DEVNULL); stderr goes to a file and, line by line, to an optional
    callback ``on_stderr(t_ns, line)`` (time.perf_counter_ns at receipt), so a caller can react to marker lines
    such as wincam's ``HOLD_BEGIN``. Never raises on child failure.

        bg = Background(argv, stdout_path=..., stderr_path=..., on_stderr=cb).start()
        bg.wait(timeout_s)        # -> rc or None (still running)
        bg.stop(timeout_s)        # wait, then kill the tree; -> result() dict
    """

    def __init__(self, argv: Sequence[str], stdout_path: str | os.PathLike | None = None,
                 stderr_path: str | os.PathLike | None = None, on_stderr=None,
                 cwd: str | os.PathLike | None = None, env: Mapping[str, str] | None = None) -> None:
        self.argv = [str(a) for a in argv]
        self.stdout_path = str(stdout_path) if stdout_path else None
        self.stderr_path = str(stderr_path) if stderr_path else None
        self.on_stderr = on_stderr
        self.cwd, self.env = cwd, env
        self.p: subprocess.Popen | None = None
        self.job: _WinJob | None = None
        self.spawn_error: str | None = None
        self.t_start_ns: int | None = None
        self.t_end_ns: int | None = None
        self.killed = False
        self.kill_method: str | None = None
        self.timed_out = False
        self.stderr_tail: list[str] = []
        self._out_f = None
        self._err_f = None
        self._th = None

    def start(self) -> "Background":
        import threading
        kwargs: dict[str, Any] = dict(stdin=subprocess.DEVNULL, cwd=str(self.cwd) if self.cwd else None,
                                      env=dict(self.env) if self.env is not None else None)
        try:
            self._out_f = open(self.stdout_path, "wb") if self.stdout_path else None
            kwargs["stdout"] = self._out_f if self._out_f else subprocess.DEVNULL
            kwargs["stderr"] = subprocess.PIPE
            if _IS_WIN:
                self.job = _WinJob()
                flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
                if self.job.ok:
                    flags |= 0x4
                kwargs["creationflags"] = flags
            else:
                kwargs["start_new_session"] = True
            self.t_start_ns = time.perf_counter_ns()
            self.p = subprocess.Popen(self.argv, **kwargs)
        except Exception as e:  # noqa: BLE001
            self.spawn_error = f"{type(e).__name__}: {e}"
            self.t_end_ns = time.perf_counter_ns()
            self._close_files()
            return self
        if _IS_WIN and self.job is not None and self.job.ok:
            assigned = self.job.assign(self.p._handle)  # type: ignore[attr-defined]
            if not _nt_resume(self.p._handle):  # type: ignore[attr-defined]
                try:
                    self.p.kill()
                except Exception:
                    pass
                self.spawn_error = "NtResumeProcess failed after CREATE_SUSPENDED"
            if not assigned:
                self.job.close()
                self.job = None
        self._err_f = open(self.stderr_path, "wb") if self.stderr_path else None

        def pump() -> None:
            assert self.p is not None and self.p.stderr is not None
            for raw in iter(self.p.stderr.readline, b""):
                t = time.perf_counter_ns()
                if self._err_f:
                    try:
                        self._err_f.write(raw)
                        self._err_f.flush()
                    except Exception:
                        pass
                line = _decode(raw).rstrip("\r\n")
                self.stderr_tail.append(line)
                if len(self.stderr_tail) > 200:
                    del self.stderr_tail[:100]
                if self.on_stderr is not None:
                    try:
                        self.on_stderr(t, line)
                    except Exception:
                        pass

        self._th = threading.Thread(target=pump, daemon=True)
        self._th.start()
        return self

    @property
    def pid(self) -> int | None:
        return self.p.pid if self.p is not None else None

    def poll(self) -> int | None:
        return None if self.p is None else self.p.poll()

    def running(self) -> bool:
        return self.p is not None and self.p.poll() is None

    def wait(self, timeout_s: float) -> int | None:
        if self.p is None:
            return None
        try:
            rc = self.p.wait(timeout=max(0.0, float(timeout_s)))
        except subprocess.TimeoutExpired:
            return None
        if self.t_end_ns is None:
            self.t_end_ns = time.perf_counter_ns()
        return rc

    def kill(self) -> str:
        if self.p is None or self.p.poll() is not None:
            return "not running"
        self.kill_method = _kill_tree(self.p, self.job)
        self.killed = True
        return self.kill_method

    def stop(self, timeout_s: float) -> dict[str, Any]:
        """Wait up to timeout_s for a normal exit; kill the tree if it is still running. Returns result()."""
        if self.p is not None and self.wait(timeout_s) is None:
            self.timed_out = True
            self.kill()
            try:
                self.p.wait(timeout=10)
            except Exception:
                pass
        if self.t_end_ns is None:
            self.t_end_ns = time.perf_counter_ns()
        if self._th is not None:
            self._th.join(timeout=5)
        self._close_files()
        if self.job is not None:
            self.job.close()
            self.job = None
        return self.result()

    def result(self) -> dict[str, Any]:
        return {"argv": self.argv, "rc": None if self.p is None else self.p.poll(), "pid": self.pid,
                "spawn_error": self.spawn_error, "timed_out": self.timed_out, "killed": self.killed,
                "kill_method": self.kill_method, "t_start_ns": self.t_start_ns, "t_end_ns": self.t_end_ns,
                "elapsed_s": None if not (self.t_start_ns and self.t_end_ns)
                else round((self.t_end_ns - self.t_start_ns) / 1e9, 4),
                "stdout_path": self.stdout_path, "stderr_path": self.stderr_path,
                "stderr_tail": "\n".join(self.stderr_tail[-40:])}

    def _close_files(self) -> None:
        for f in (self._out_f, self._err_f):
            try:
                if f:
                    f.close()
            except Exception:
                pass
        self._out_f = self._err_f = None


def python_cmd(script: str | os.PathLike, *args: str, python: str | None = None) -> list[str]:
    """argv for a PEP 723 script: ['uv', 'run', '--script', script, *args] (``python`` adds --python X)."""
    cmd = ["uv", "run"]
    if python:
        cmd += ["--python", python]
    return cmd + ["--script", str(script), *map(str, args)]
