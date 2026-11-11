"""camworker: argument parsers, JPEG quick check, exit codes and JSON-on-failure against fake (non-V4L2) nodes,
and the watchdog's exit-5 path. No camera is opened: the fake /dev nodes are regular files, so every V4L2 ioctl
fails with ENOTTY, which must come back as a JSON error, never a traceback."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import camworker
from test_jpegcheck import JPEG

WORKER = Path(camworker.__file__)


def test_parse_sets_schedule_save():
    assert camworker.parse_sets("exposure_time_absolute=100,0x00980913=5") == [(0x009A0902, 100), (0x00980913, 5)]
    sch = camworker.parse_schedule("3000:gain=1;1500:0x009a0902=300,auto_exposure=1")
    assert sch[0][0] == 1500.0 and sch[0][1] == [(0x009A0902, 300), (0x009A0901, 1)] and sch[1][0] == 3000.0
    assert camworker.parse_save("all") == ("all", 0) and camworker.parse_save("every:5") == ("every", 5)
    with pytest.raises(ValueError):
        camworker.parse_save("bogus:1")


def test_frame_quick_check():
    q = camworker.frame_quick_check(JPEG)
    assert q["soi"] and q["eoi"] and (q["sof0_w"], q["sof0_h"]) == (32, 16) and len(q["hdr_sha1"]) == 40
    bad = camworker.frame_quick_check(b"\x00" * 100)
    assert not bad["soi"] and bad["sof0_w"] is None


def run_worker(*args, env=None, timeout=60):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run([sys.executable, str(WORKER), *map(str, args)], capture_output=True, text=True,
                       timeout=timeout, env=e)
    lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
    return p.returncode, (json.loads(lines[-1]) if lines else None), p.stderr


def test_selftest_cli():
    rc, j, _ = run_worker("selftest")
    assert rc == 0 and j["ok"] and j["meta_parser_ok"]


def test_usage_error():
    rc, _, _ = run_worker("capture", "--device", "/dev/video0")
    assert rc == 2


@pytest.mark.linux_only
def test_missing_device_exit3(tmp_path):
    rc, j, _ = run_worker("info", "--device", "/dev/video_does_not_exist_42")
    assert rc == 3 and j["error"]["errno_name"] == "ENOENT"


@pytest.mark.linux_only
def test_fake_node_errors_are_json(fake_root, tmp_path):
    env = {"SKELLYCAM_LINUX_ROOT": str(fake_root)}
    node = str(fake_root / "dev/video0")
    rc, j, _ = run_worker("info", "--device", node, env=env)
    assert rc == 4 and j["error"]["stage"] == "querycap" and j["error"]["errno_name"] == "ENOTTY"
    rc, j, _ = run_worker("controls", "--device", node, env=env)
    assert rc in (0, 4) and j["controls"][0]["query_errno"] == "ENOTTY"
    out = tmp_path / "cap"
    rc, j, _ = run_worker("capture", "--device", node, "--width", 640, "--height", 480, "--fps", 30, "--frames", 5,
                          "--out-dir", out, env=env)
    assert rc == 4 and j["error"]["stage"] == "querycap"
    assert (out / "summary.json").exists() and (out / "frames.jsonl").exists()
    rc, j, _ = run_worker("cycle", "--device", node, "--width", 640, "--height", 480, "--fps", 30, "--cycles", 3,
                          "--frames", 5, "--out-dir", tmp_path / "cyc", env=env)
    rows = [json.loads(x) for x in (tmp_path / "cyc" / "cycles.jsonl").read_text().splitlines()]
    assert rc == 0 and j["rows"] == 3 and j["n_ok"] == 0
    assert all(r["stage_failed"] == "querycap" and r["errno_name"] == "ENOTTY" for r in rows)
    rc, j, _ = run_worker("desk_probe", "--device", node, env=env)
    assert rc == 0 and j["reqbufs_errno"] == "ENOTTY"
    rc, j, _ = run_worker("enum", "--repeat", 2, env=env)
    assert rc == 0 and len(j["runs"]) == 2 and j["runs"][0]["entries"]


@pytest.mark.linux_only
def test_watchdog_exits_5():
    code = ("import sys,time; sys.path.insert(0, %r); import camworker as c;"
            "c.Watchdog(lambda s: c.emit({'stage': s}, 5)).stage('stuck', 0.3); time.sleep(10)") % str(WORKER.parent)
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert p.returncode == 5 and json.loads(p.stdout.strip())["stage"] == "stuck"
    assert time.monotonic() - t0 < 5
