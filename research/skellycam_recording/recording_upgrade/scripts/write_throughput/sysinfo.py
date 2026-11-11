"""Read-only machine snapshot for the write_throughput benches (run before and after a bench session).

Records: physical disk model / media / bus, C: volume file system / cluster size / free space, Defender status
(Get-MpComputerStatus, read-only - nothing is changed), active power plan, CPU count, top CPU consumers,
nvidia-smi encoder sessions (other agents / Parsec / Sunshine), Windows Search service state.
Output: results/write_throughput/bench/sysinfo/sysinfo_<timestamp>.json (or --out).
Run (repo root): .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/sysinfo.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wt_common as W  # noqa: E402

PS = r"""
$o=[ordered]@{}
$o.physical_disks=@(Get-PhysicalDisk | Select-Object DeviceId,FriendlyName,Model,MediaType,BusType,Size,FirmwareVersion,HealthStatus)
$o.volume_C=Get-Volume -DriveLetter C | Select-Object DriveLetter,FileSystem,AllocationUnitSize,Size,SizeRemaining,HealthStatus
try { $o.defender=Get-MpComputerStatus | Select-Object AMServiceEnabled,AntivirusEnabled,RealTimeProtectionEnabled,OnAccessProtectionEnabled,IoavProtectionEnabled,BehaviorMonitorEnabled,AMRunningMode,AMProductVersion,AntivirusSignatureVersion } catch { $o.defender_error=$_.Exception.Message }
try { $o.windows_search_service=(Get-Service WSearch | Select-Object Status,StartType) } catch { $o.windows_search_service_error=$_.Exception.Message }
$o.power_plan=(powercfg /getactivescheme | Out-String).Trim()
try { $p=Get-MpPreference; $o.defender_exclusion_path=@($p.ExclusionPath); $o.defender_exclusion_process=@($p.ExclusionProcess) } catch { $o.defender_pref_error=$_.Exception.Message }
$o.fsutil_8dot3_C=(fsutil 8dot3name query C: 2>&1 | Out-String).Trim()
$o.last_access=(fsutil behavior query disablelastaccess 2>&1 | Out-String).Trim()
$o | ConvertTo-Json -Depth 4
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    import psutil
    p = subprocess.run(["pwsh", "-NoProfile", "-Command", PS], capture_output=True, text=True)
    try:
        ps = json.loads(p.stdout)
    except Exception:  # noqa: BLE001
        ps = dict(raw=p.stdout[-4000:], err=p.stderr[-2000:])
    procs = []
    for pr in psutil.process_iter(["name"]):
        try:
            pr.cpu_percent(None)
            procs.append(pr)
        except Exception:  # noqa: BLE001
            pass
    time.sleep(2.0)
    top = []
    for pr in procs:
        try:
            top.append((pr.cpu_percent(None), pr.info["name"]))
        except Exception:  # noqa: BLE001
            pass
    top.sort(reverse=True)
    nv = subprocess.run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu", "--format=csv"],
                        capture_output=True, text=True).stdout
    res = dict(timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"), env=W.env_versions(), powershell=ps,
               logical_cpus=psutil.cpu_count(), physical_cpus=psutil.cpu_count(logical=False),
               ram_total=psutil.virtual_memory().total, system_cpu_pct_2s=psutil.cpu_percent(None),
               top_cpu_processes_2s=top[:15], nvidia_smi=nv,
               media_dir=str(W.MEDIA), media_free_bytes=__import__("shutil").disk_usage(W.RAW).free)
    out = Path(a.out) if a.out else W.BENCH_RESULTS / "sysinfo" / f"sysinfo_{time.strftime('%Y%m%dT%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, default=str))
    print("wrote", out)


if __name__ == "__main__":
    main()
