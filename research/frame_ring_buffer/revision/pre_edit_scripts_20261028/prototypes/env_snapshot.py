"""Writes results/environment_system.json and results/environment_python.json (copy of baseline/env_snapshot.py for the prototypes
stage; also records simplejpeg / turbojpeg and the NVIDIA driver; run it in each venv: the file name gets the venv tag). NOT SkellyCam code.

Run:  cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam && .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\baseline\\env_snapshot.py
"""
import json
import subprocess
import sys
from importlib import metadata
from pathlib import Path

R = Path(__file__).resolve().parent / "results"


def ps(cmd):
    out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd + " | ConvertTo-Json -Depth 3"],
                         capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except Exception:
        return out.strip()


system = {
    "cpu": ps("Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed"),
    "ram_bytes": ps("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"),
    "ram_modules": ps("Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity,Speed,ConfiguredClockSpeed,Manufacturer,PartNumber"),
    "disks": ps("Get-PhysicalDisk | Select-Object FriendlyName,MediaType,BusType,Size"),
    "gpu": ps("Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion"),
    "nvidia_smi": subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,encoder.stats.sessionCount", "--format=csv"], capture_output=True, text=True).stdout.strip(),
    "os": ps("Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber"),
    "power_plan": subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True).stdout.strip(),
    "temp_volume": ps("Get-Volume -DriveLetter C | Select-Object DriveLetter,FileSystem,Size,SizeRemaining"),
}
(R / "environment_system.json").write_text(json.dumps(system, indent=2))

import cv2  # noqa: E402

pk = {}
for name in ["numpy", "opencv-contrib-python", "psutil", "av", "beartype", "pydantic", "uvicorn", "websockets",
             "starlette", "fastapi", "polars", "skellylogs", "skellycam", "simplejpeg", "PyTurboJPEG"]:
    try:
        pk[name] = metadata.version(name)
    except Exception:
        pk[name] = None
bi = cv2.getBuildInformation().splitlines()
vio = [ln.strip() for ln in bi if ln.strip().startswith(("Video I/O", "FFMPEG:", "DirectShow:", "Media Foundation:"))]
pyenv = {"python": sys.version, "executable": sys.executable, "packages": pk,
         "cv2_num_threads": cv2.getNumThreads(), "cv2_videoio_build": vio}
(R / f"environment_python_{'skellycamvenv' if pk.get('skellycam') else 'benchvenv'}.json").write_text(json.dumps(pyenv, indent=2))
print(json.dumps(pyenv, indent=1))
