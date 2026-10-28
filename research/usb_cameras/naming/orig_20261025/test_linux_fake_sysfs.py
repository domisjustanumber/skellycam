# /// script
# requires-python = ">=3.10"
# ///
"""Smoke test of linux_identity.py + camera_identity.py on a FAKE sysfs tree (Linux / WSL, no cameras needed).

    python3 research/usb_cameras/naming/test_linux_fake_sysfs.py [descriptors.json]

Builds <tmp>/sys/... and <tmp>/dev/... mimicking two uvcvideo cameras (real descriptor bytes from the Windows
descriptors.json: the C922 with serial on port 3-1, the serial-less C930e on 3-2.4 behind a hub), points
linux_identity at it via LINUX_IDENTITY_TEST_ROOT, and checks the parsed identity + keys. VIDIOC_QUERYCAP fails on
the fake nodes (regular files) - that path is exercised too. This validates the parsing/plumbing only; the real
kernel/udev behaviour is what linux_stability_workflow.sh measures.
Writes results/linux/<hostname>/naming/test_linux_fake_sysfs.json
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def build(root: Path, cams: list[dict]) -> None:
    ctrl = root / "sys/devices/pci0000:00/0000:00:14.0/usb3"
    (root / "sys/class/video4linux").mkdir(parents=True)
    (root / "dev/v4l/by-path").mkdir(parents=True)
    (root / "dev/v4l/by-id").mkdir(parents=True)
    vid_n = 0
    for c in cams:
        dev = ctrl
        name = c["kernel_name"]
        for hop in c["hub_chain"]:
            dev = dev / hop
            dev.mkdir(parents=True, exist_ok=True)
        dev = dev / name
        dev.mkdir(parents=True)
        attrs = dict(idVendor=c["vid"], idProduct=c["pid"], bcdDevice=c["bcd"], product=c["product"], busnum="3",
                     devnum=str(5 + vid_n), devpath=name.split("-", 1)[1], speed="480", version=" 2.00")
        if c["serial"]:
            attrs["serial"] = c["serial"]
        for k, v in attrs.items():
            (dev / k).write_text(v + "\n")
        (dev / "descriptors").write_bytes(bytes.fromhex(c["raw_dev"]) + bytes.fromhex(c["raw_cfg"]))
        itf = dev / f"{name}:1.0"
        for idx in (0, 1):  # capture node + metadata node, as uvcvideo creates
            v = itf / "video4linux" / f"video{vid_n}"
            v.mkdir(parents=True)
            (v / "name").write_text(c["product"] + "\n")
            (v / "index").write_text(f"{idx}\n")
            os.symlink(os.path.relpath(itf, v), v / "device")
            os.symlink(os.path.relpath(v, root / "sys/class/video4linux"), root / f"sys/class/video4linux/video{vid_n}")
            (root / f"dev/video{vid_n}").write_text("")
            port = name.split("-", 1)[1]
            os.symlink(f"../../video{vid_n}", root / f"dev/v4l/by-path/pci-0000:00:14.0-usb-0:{port}:1.0-video-index{idx}")
            sid = f"{c['product'].replace(' ', '_')}" + (f"_{c['serial']}" if c["serial"] else "")
            os.symlink(f"../../video{vid_n}", root / f"dev/v4l/by-id/usb-{sid}-video-index{idx}")
            vid_n += 1


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "results/windows/Gerald/naming/descriptors.json"
    d = json.loads(src.read_text(encoding="utf-8"))
    by = {c["camera"]["pid"]: c for c in d["cameras"]}
    cams = [
        dict(kernel_name="3-1", hub_chain=[], vid="046d", pid="085c", bcd="0016", product="C922 Pro Stream Webcam",
             serial="B76395EF", raw_dev=by["085c"]["raw_hex"]["device"], raw_cfg=by["085c"]["raw_hex"]["configuration"]),
        dict(kernel_name="3-2.4", hub_chain=["3-2"], vid="046d", pid="0843", bcd="0013", product="Logitech Webcam C930e",
             serial=None, raw_dev=by["0843"]["raw_hex"]["device"], raw_cfg=by["0843"]["raw_hex"]["configuration"]),
    ]
    checks, ok = [], True
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build(root, cams)
        os.environ["LINUX_IDENTITY_TEST_ROOT"] = str(root)
        sys.path.insert(0, str(HERE))
        import linux_identity
        import camera_identity
        flats = linux_identity.collect_flat()
        full = linux_identity.collect()
        for f in flats:
            f["port_path"] = camera_identity.port_path_from_linux(f["pci_controller"], f["sysfs_usb_name"])
        keys = {f["pid"]: camera_identity.derive(f, flats)[0] for f in flats}

        def check(n, c, detail=None):
            nonlocal ok
            ok &= bool(c)
            checks.append(dict(name=n, ok=bool(c), detail=detail))
            print(("PASS " if c else "FAIL ") + n, "" if c else detail)
        check("two cameras found", len(flats) == 2, [f["sysfs_usb_name"] for f in flats])
        check("C922 key uses serial", keys.get("085c") == "046d:085c:sn=B76395EF", keys.get("085c"))
        check("C930e key uses port", keys.get("0843") == "046d:0843:port=pci-0000:00:14.0/2.4", keys.get("0843"))
        check("controller detected", all(f["pci_controller"] == "0000:00:14.0" for f in flats))
        check("by-path symlink resolved", all(f["by_path"] for f in flats), [f["by_path"] for f in flats])
        check("descriptors parsed from sysfs layout",
              all(c.get("descriptors", {}).get("configurations") for c in full),
              [c.get("descriptors_error") for c in full])
        check("UVC clock parsed (C922 300 MHz)",
              next(c for c in full if c["sysfs_attrs"]["idProduct"] == "085c")["descriptors"]["configurations"][0]["uvc"]["dwClockFrequency"] == 300_000_000)
        check("querycap failure recorded, not raised", all("error" in n["querycap"] for c in full for n in c["video_nodes"]))
    out = HERE.parent / "results" / "linux" / socket.gethostname() / "naming"
    out.mkdir(parents=True, exist_ok=True)
    (out / "test_linux_fake_sysfs.json").write_text(json.dumps(dict(
        test="naming.test_linux_fake_sysfs", platform=sys.platform, hostname=socket.gethostname(),
        command=" ".join(sys.argv), input=str(src), keys=keys, checks=checks, all_ok=ok), indent=1))
    print("all_ok =", ok, "->", out / "test_linux_fake_sysfs.json")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
