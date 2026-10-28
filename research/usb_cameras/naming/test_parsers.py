# /// script
# requires-python = ">=3.10"
# ///
"""Offline tests (any OS, no cameras): parsers and identity scheme against REAL descriptor bytes captured on Windows.

    uv run --script research/usb_cameras/naming/test_parsers.py [path/to/descriptors.json]

1. usbdesc + camera_identity self tests.
2. For each camera in a Windows descriptors.json: concatenate raw device + configuration descriptor bytes into the
   Linux sysfs `descriptors` file layout and check usbdesc.parse_sysfs_descriptors() reproduces exactly the same
   UVC summary as the Windows path (so linux_identity.py's descriptor output is comparable across OSes).
3. Re-parse every raw configuration descriptor and check internal consistency (wTotalLength, bNumInterfaces,
   format.bNumFrameDescriptors == number of parsed frames, VS input header bNumFormats == number of formats).
Writes results/<platform>/<hostname>/naming/test_parsers.json
"""
from __future__ import annotations

import json
import platform
import socket
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import camera_identity  # noqa: E402
import usbdesc  # noqa: E402


def main() -> int:
    argv = sys.argv[1:]
    out_override = None
    if "--out-dir" in argv:  # optional: keep re-runs from overwriting the cited result file
        i = argv.index("--out-dir")
        out_override = Path(argv[i + 1])
        del argv[i:i + 2]
    src = Path(argv[0]) if argv else HERE.parent / "results/windows/Gerald/naming/descriptors.json"
    results = dict(test="naming.test_parsers", platform=sys.platform, hostname=socket.gethostname(),
                   command=" ".join(sys.argv), python=platform.python_version(), input=str(src), checks=[])
    ok_all = True

    def check(name, cond, detail=None):
        nonlocal ok_all
        ok_all &= bool(cond)
        results["checks"].append(dict(name=name, ok=bool(cond), detail=detail))
        print(("PASS " if cond else "FAIL ") + name + (f"  {detail}" if detail and not cond else ""))

    check("usbdesc selftest", usbdesc._selftest() == 0)
    check("camera_identity selftest", camera_identity._selftest() == 0)
    d = json.loads(src.read_text(encoding="utf-8"))
    for cam in d["cameras"]:
        name = f"{cam['camera']['vid']}:{cam['camera']['pid']} {cam['camera']['product']}"
        raw = cam.get("raw_hex") or {}
        if not raw.get("configuration"):
            check(f"{name}: raw descriptors present", False)
            continue
        dev_b, cfg_b = bytes.fromhex(raw["device"]), bytes.fromhex(raw["configuration"])
        sysfs = usbdesc.parse_sysfs_descriptors(dev_b + cfg_b, cam["speed"])
        check(f"{name}: sysfs-layout parse == windows parse (uvc summary)",
              json.dumps(sysfs["configurations"][0]["uvc"], sort_keys=True) == json.dumps(cam["uvc"], sort_keys=True))
        cfg = usbdesc.parse_configuration(cfg_b, cam["speed"])
        check(f"{name}: wTotalLength == bytes", cfg["wTotalLength"] == len(cfg_b), (cfg["wTotalLength"], len(cfg_b)))
        check(f"{name}: bNumInterfaces == distinct interface numbers",
              cfg["bNumInterfaces"] == len({i["bInterfaceNumber"] for i in cfg["interfaces"]}))
        for s in cfg["uvc"]["streaming_interfaces"]:
            check(f"{name}: VS{s['bInterfaceNumber']} bNumFormats == parsed formats",
                  s["input_header"].get("bNumFormats") == len(s["formats"]),
                  (s["input_header"].get("bNumFormats"), len(s["formats"])))
            for f in s["formats"]:
                check(f"{name}: VS{s['bInterfaceNumber']} fmt{f['bFormatIndex']} {f['format']} frame count",
                      f["bNumFrameDescriptors"] == len(f["frames"]), (f["bNumFrameDescriptors"], len(f["frames"])))
    results["all_ok"] = ok_all
    out = out_override or HERE.parent / "results" / {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux") / socket.gethostname() / "naming"
    out.mkdir(parents=True, exist_ok=True)
    (out / "test_parsers.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("all_ok =", ok_all, "->", out / "test_parsers.json")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
