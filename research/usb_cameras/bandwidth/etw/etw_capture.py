# /// script
# requires-python = ">=3.10"
# ///
"""Goal 3, Windows: capture a USB ETW trace (one UAC prompt) while opening cameras, so the trace shows
(a) the UVC VS_PROBE/VS_COMMIT control transfers (=> the camera's dwMaxPayloadTransferSize as usbvideo.sys sees it)
and (b) the SELECT_INTERFACE / endpoint configuration (=> which alt setting usbvideo.sys picked, also for SuperSpeed
where the hub's open-pipe list is ambiguous), and (c) the failure status when bandwidth is insufficient.

  uv run --script research/usb_cameras/bandwidth/etw/etw_capture.py --name NAME -- --combo "..." [--combo ...] [run_concurrency args]

Steps: launches usb_etw_capture_elevated.ps1 with Start-Process -Verb RunAs (user clicks UAC), waits up to 5 min for
"STARTED", runs run_concurrency.py under camlock with the given args, signals the elevated script to stop, then converts
the ETL with tracerpt (no admin needed) to XML.
STATUS: the one allowed UAC prompt was declined on Gerald (results/windows/Gerald/bw_etw/etw01/console_output.txt), so no
trace exists yet and no parser has been written; decoding the XML (VS_PROBE GET_CUR data offset 22 = dwMaxPayloadTransferSize,
select-interface events) is still TODO.
Output: results/windows/<host>/bw_etw/<NAME>/ (elevated_log.txt, usbbw.etl, usbbw.xml, driver_log.json)
Revert (only if something went wrong): Start-Process powershell -Verb RunAs -ArgumentList '-File research\\usb_cameras\\bandwidth\\etw\\usb_etw_revert.ps1'
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
UC = HERE.parent.parent  # research/usb_cameras


def main() -> int:
    argv = sys.argv[1:]
    if "--name" not in argv or "--" not in argv:
        sys.exit(__doc__)
    name = argv[argv.index("--name") + 1]
    passthru = argv[argv.index("--") + 1:]
    out = UC / "results" / "windows" / socket.gethostname() / "bw_etw" / name
    out.mkdir(parents=True, exist_ok=True)
    flag = out / "stop.flag"
    flag.unlink(missing_ok=True)
    log = out / "elevated_log.txt"
    drv = {"name": name, "passthru": passthru, "steps": []}

    def step(msg, **kw):
        drv["steps"].append({"t": time.time(), "msg": msg, **kw})
        print(msg, flush=True)
        (out / "driver_log.json").write_text(json.dumps(drv, indent=1))

    ps1 = HERE / "usb_etw_capture_elevated.ps1"
    arglist = f"-NoProfile -ExecutionPolicy Bypass -File \"{ps1}\" -OutDir \"{out}\" -FlagFile \"{flag}\" -MaxMinutes 25"
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Start-Process powershell -Verb RunAs -ArgumentList '{arglist}'"], check=False)
    step("UAC requested; waiting up to 300 s for the elevated session to start")
    t0 = time.time()
    while time.time() - t0 < 300:
        if log.exists() and "STARTED" in log.read_text(encoding="utf-8", errors="replace"):
            break
        time.sleep(2)
    else:
        step("elevated script did not start (UAC not approved?) -- aborting")
        return 3
    step("ETW session started")
    time.sleep(2)
    cmd = ["uv", "run", "--script", str(UC / "tools" / "camlock.py"), "--timeout-s", "1200", "--",
           "uv", "run", "--script", str(HERE.parent / "run_concurrency.py")] + passthru
    r = subprocess.run(cmd, capture_output=True, text=True)
    step("camera batch finished", rc=r.returncode, stdout=r.stdout[-6000:], stderr=r.stderr[-3000:])
    time.sleep(2)
    flag.write_text("stop")
    t1 = time.time()
    while time.time() - t1 < 120:
        if "STOPPED" in log.read_text(encoding="utf-8", errors="replace"):
            break
        time.sleep(1)
    step("ETW session stopped" if "STOPPED" in log.read_text(encoding="utf-8", errors="replace") else "stop not confirmed!")
    etls = sorted(out.glob("usbbw*.etl"))
    if etls:
        x = subprocess.run(["tracerpt", str(etls[-1]), "-o", str(out / "usbbw.xml"), "-of", "XML", "-y"], capture_output=True, text=True)
        step("tracerpt done", rc=x.returncode, out=x.stdout[-1500:], etl=str(etls[-1]), etl_bytes=etls[-1].stat().st_size)
    else:
        step("no ETL produced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
