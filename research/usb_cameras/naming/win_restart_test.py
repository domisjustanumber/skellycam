# /// script
# requires-python = ">=3.10"
# ///
"""Windows: are camera identifiers stable across a device restart (`pnputil /restart-device` on the composite parent)?

Run from repo root, NOT under camlock (this script takes the lock itself, only around the restart window):
    uv run --script research/usb_cameras/naming/win_restart_test.py [--only VID:PID ...]

Flow:
  1. finds every UVC camera's composite parent instance id (PnP read, no lock needed), writes ids.txt
  2. launches naming/win_restart_devices_admin.ps1 elevated (ONE UAC prompt), which writes ready.txt and waits
  3. once ready: re-invokes itself as `... locked --run-dir D` under tools/camlock.py, which
       a. snapshots all identifiers (win_identity_dump + MF/DirectShow names) -> snapshots/restart_before.json
       b. writes go.txt; the elevated script restarts each device in turn and writes done.txt
       c. polls until every camera is present again with ProblemCode 0 (records seconds to come back)
       d. snapshots again -> snapshots/restart_after.json, then diffs with identity_diff.py
Output dir: results/windows/<host>/naming/restart_test/<UTC timestamp>/
Revert (only if a camera is left stopped): elevated naming/win_restart_revert_admin.ps1 -RunDir <that dir>
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import win_identity_dump as wid  # noqa: E402
import identity_diff  # noqa: E402

REPO_TOOLS = HERE.parent / "tools"


def _snapshot(label: str, run_dir: Path) -> dict:
    import win_api_names
    cams = wid.collect(read_descriptors=True)
    flats = []
    api = win_api_names.api_identity_fields(cams)
    for c in cams:
        f = wid.flat_identity(c)
        f.update(api.get(c["usb_device"]["instance_id"], {}))
        try:
            from camera_identity import windows_key_for_flat
            f["camera_key"] = windows_key_for_flat(f, None)
        except ImportError:
            pass
        flats.append(f)
    for f in flats:
        try:
            from camera_identity import windows_key_for_flat
            f["camera_key"] = windows_key_for_flat(f, flats)
        except ImportError:
            pass
    snap = dict(test="naming.snapshot", label=label, platform="windows", hostname=wid.socket.gethostname(),
                utc_started=_dt.datetime.now(_dt.timezone.utc).isoformat(), command=" ".join(sys.argv),
                cameras=flats)
    (run_dir / "snapshots").mkdir(parents=True, exist_ok=True)
    (run_dir / "snapshots" / f"{label}.json").write_text(json.dumps(snap, indent=1), encoding="utf-8")
    return snap


def _present_ok(ids: list[str]) -> dict:
    present = {i.upper() for i in wid.list_device_ids("USB")}
    out = {}
    for i in ids:
        if i.upper() not in present:
            out[i] = "absent"
            continue
        p = wid.devnode_props(wid.locate(i))
        out[i] = "ok" if p.get("ProblemCode") == 0 and p.get("DevNodeStatus") else f"problem {p.get('ProblemCode')}"
    return out


def locked(run_dir: Path) -> int:
    ids = [l.strip() for l in (run_dir / "ids.txt").read_text().splitlines() if l.strip()]
    timeline = dict(lock_acquired=time.time())
    _snapshot("restart_before", run_dir)
    timeline["before_snapshot_done"] = time.time()
    (run_dir / "go.txt").write_text("go")
    t_go = time.time()
    while not (run_dir / "done.txt").exists():
        if time.time() - t_go > 120:
            print("elevated script did not finish within 120 s", file=sys.stderr)
            break
        time.sleep(0.2)
    timeline["admin_done"] = time.time()
    # pnputil exit 3010 = restart vetoed (reboot required). Kernel-PnP event 225 names the process holding the device.
    since = _dt.datetime.fromtimestamp(t_go - 5).strftime("%Y-%m-%dT%H:%M:%S")
    ps = (f"Get-WinEvent -FilterHashtable @{{LogName='System'; ProviderName='Microsoft-Windows-Kernel-PnP'; Id=225; "
          f"StartTime=[datetime]'{since}'}} -ErrorAction SilentlyContinue | Select-Object "
          "@{n='TimeCreatedUtc';e={$_.TimeCreated.ToUniversalTime().ToString('o')}},Id,Message | ConvertTo-Json -Depth 3")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    (run_dir / "pnp_veto_events_225.json").write_text(r.stdout or "[]", encoding="utf-8")
    t0 = time.time()
    states = {}
    while time.time() - t0 < 60:
        states = _present_ok(ids)
        if all(v == "ok" for v in states.values()):
            break
        time.sleep(0.5)
    timeline["all_present"] = time.time()
    timeline["seconds_until_present_after_admin_done"] = round(timeline["all_present"] - timeline["admin_done"], 2)
    time.sleep(2.0)  # let MF/DirectShow interface registration settle
    _snapshot("restart_after", run_dir)
    timeline["after_snapshot_done"] = time.time()
    (run_dir / "timeline.json").write_text(json.dumps(dict(timeline=timeline, final_states=states), indent=1))
    snaps = [json.loads((run_dir / "snapshots" / f"{l}.json").read_text(encoding="utf-8"))
             for l in ("restart_before", "restart_after")]
    res = identity_diff.diff(snaps)
    res["admin_log"] = (run_dir / "admin_log.txt").read_text(encoding="utf-8-sig", errors="replace").splitlines() \
        if (run_dir / "admin_log.txt").exists() else None
    res["timeline"] = timeline
    (run_dir / "stability_restart.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    identity_diff.print_table(res)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", nargs="?", default="start", choices=["start", "locked"])
    ap.add_argument("--run-dir", type=Path)
    ap.add_argument("--only", nargs="*", default=None, help="VID:PID filters, e.g. 046d:085c")
    a = ap.parse_args()
    if a.phase == "locked":
        return locked(a.run_dir)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = wid.default_out_dir() / "restart_test" / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    cams = wid.collect(read_descriptors=False)
    ids = []
    for c in cams:
        f = wid.flat_identity(c)
        if a.only and f"{f['vid']}:{f['pid']}" not in [x.lower() for x in a.only]:
            continue
        ids.append(c["usb_device"]["instance_id"])
    (run_dir / "ids.txt").write_text("\n".join(ids) + "\n")
    print("devices to restart:", ids)
    ps1 = HERE / "win_restart_devices_admin.ps1"
    arg = f"-NoProfile -ExecutionPolicy Bypass -File \"{ps1}\" -RunDir \"{run_dir}\""
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Start-Process powershell -Verb RunAs -WindowStyle Hidden -ArgumentList '{arg}'"], check=True)
    print("waiting up to 5 min for the UAC prompt to be accepted ...")
    t0 = time.time()
    while not (run_dir / "ready.txt").exists():
        if time.time() - t0 > 300:
            print("elevated helper never became ready (UAC declined?)", file=sys.stderr)
            return 3
        time.sleep(1)
    print(f"elevated helper ready after {time.time() - t0:.0f}s; taking camera lock")
    cmd = ["uv", "run", "--script", str(REPO_TOOLS / "camlock.py"), "--timeout-s", "1800", "--",
           "uv", "run", "--script", str(Path(__file__).resolve()), "locked", "--run-dir", str(run_dir)]
    rc = subprocess.call(cmd)
    print("run dir:", run_dir)
    return rc


if __name__ == "__main__":
    sys.exit(main())
