"""results.py (standard fields, strict JSON, paths) and procutil.run (tree kill on timeout, never raises)."""
import json
import math
import os
import sys
import time
from pathlib import Path


from common import procutil, results


def test_result_lifecycle(tmp_path):
    res = results.new_result("W-TEST", command=["x", "--y"], cameras=[{"key": "k"}])
    for k in ("test", "platform", "hostname", "utc_started", "command", "environment", "cameras", "measurements",
              "verdicts", "errors"):
        assert k in res
    results.finish_result(res, {"nan": math.nan, "p": Path("a/b"), "s": {3, 1}}, {"g": {"rating": "yes"}},
                          [{"msg": "e"}])
    assert res["utc_finished"] and res["elapsed_s"] is not None and "_t0" not in res
    p = results.write_json(tmp_path / "sub" / "r.json", res)
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["measurements"]["nan"] is None and d["measurements"]["s"] == [1, 3]
    assert d["command"] == "x --y" and d["argv"] == ["x", "--y"]
    assert d["environment"]["python"]
    results.append_jsonl(tmp_path / "f.jsonl", {"a": 1})
    (tmp_path / "f.jsonl").open("a").write('{"partial": ')
    assert results.read_jsonl(tmp_path / "f.jsonl") == [{"a": 1}]


def test_paths(tmp_path, monkeypatch):
    out = results.default_results_dir("20261106T000000Z", "HOST")
    assert out.parts[-4:] == ("results", results.platform_name(), "HOST", "suite_20261106T000000Z")
    monkeypatch.setenv("SKELLYCAM_RAW_ROOT", str(tmp_path / "raw"))
    raw = results.default_raw_dir(out)
    assert raw == tmp_path / "raw" / "results" / results.platform_name() / "HOST" / "suite_20261106T000000Z"
    assert results.default_raw_dir(tmp_path / "elsewhere") == tmp_path / "raw" / "elsewhere"
    assert len(results.utc_stamp()) == 16


def test_run_ok_and_failure():
    r = procutil.run([sys.executable, "-c", "import sys; print('hi'); sys.stderr.write('err'); sys.exit(3)"], 30)
    assert r["rc"] == 3 and r["stdout"].strip() == "hi" and r["stderr"] == "err" and not r["timed_out"]
    r2 = procutil.run(["definitely-not-a-real-exe-xyz"], 5)
    assert r2["rc"] is None and r2["spawn_error"]


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        k32 = ctypes.WinDLL("kernel32")
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # a reparented zombie counts as dead
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split()[2] != "Z"
    except OSError:
        return True


def test_timeout_kills_grandchild(tmp_path):
    pidfile = tmp_path / "gc.pid"
    child = (
        "import subprocess, sys, time\n"
        f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        f"open(r'{pidfile}', 'w').write(str(p.pid))\n"
        "time.sleep(120)\n"
    )
    t0 = time.monotonic()
    r = procutil.run([sys.executable, "-c", child], timeout_s=3)
    assert r["timed_out"] and r["killed"] and time.monotonic() - t0 < 30
    gc = int(pidfile.read_text())
    for _ in range(50):
        if not _alive(gc):
            break
        time.sleep(0.1)
    assert not _alive(gc), f"grandchild {gc} survived (kill_method={r['kill_method']})"


def test_python_cmd():
    assert procutil.python_cmd("a.py", "--x", python="3.12") == ["uv", "run", "--python", "3.12", "--script", "a.py",
                                                                 "--x"]
