# /// script
# requires-python = ">=3.10"
# ///
"""Enumerate every test camera's MJPEG modes as DirectShow and Media Foundation report them (Windows).

  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/mjpeg/list_formats.py [--cams c922,c930e,usbcam]

(--dshow-formats binds each named DirectShow filter and --list --dev activates each named MF source, so it runs under
camlock. Only the named cameras are touched; the default is mjpeg_common.DEFAULT_CAMS, which leaves out the Kiyo.)
Writes results/windows/<host>/mjpeg_formats/<UTC stamp>/{summary.json, dshow_formats_raw.json, mf_list_raw.json}
(a new directory each run; earlier listings are kept).
summary.json: per camera, MJPG modes per API, max MJPEG mode (largest area, then highest fps), whether
1280x720@30 MJPG exists, and the enumeration orders (DirectShow index = OpenCV CAP_DSHOW index, MF order =
OpenCV CAP_MSMF index).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mjpeg_common as mc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--cams", default=",".join(mc.DEFAULT_CAMS))
a = ap.parse_args()
cams = a.cams.split(",")
started = mc.utc_now()
exe = str(mc.MF_TOOL)
devs = [mc.WINDOWS_CAMERAS[c]["vidpid"] for c in cams]
cmd_ds = [exe, "--dshow-formats"] + sum((["--dev", d] for d in devs), [])
p = subprocess.run(cmd_ds, capture_output=True, text=True, timeout=120)
ds = json.loads(p.stdout[p.stdout.find("{"):]) if "{" in p.stdout else {"error": p.stderr}
cmd_mf = [exe, "--list"] + sum((["--dev", d] for d in devs), [])
p2 = subprocess.run(cmd_mf, capture_output=True, text=True, timeout=180)
mf = json.loads(p2.stdout[p2.stdout.find("{"):]) if "{" in p2.stdout else {"error": p2.stderr}
out = mc.results_dir("mjpeg_formats", mc.utc_stamp())
(out / "dshow_formats_raw.json").write_text(json.dumps(ds, indent=1))
(out / "mf_list_raw.json").write_text(json.dumps(mf, indent=1))


def modes_key(m):
    w, h, f = m
    return (w * h, f)


per = {}
for d in ds.get("dshow_formats", []):
    cam = mc.cam_from_vidpid(d["device_path"])
    if not cam:
        continue
    mj = sorted({(c["w"], c["h"], round(c["max_fps"], 2)) for c in d["caps"] if c["biCompression"] == "MJPG"}, key=modes_key)
    per.setdefault(cam, {})["dshow"] = {"name": d["name"], "device_path": d["device_path"], "hr": d["hr"],
                                        "subtypes": sorted({c["biCompression"] for c in d["caps"]}),
                                        "mjpg_modes": [f"{w}x{h}@{f:g}" for w, h, f in mj],
                                        "max_mjpeg": f"{mj[-1][0]}x{mj[-1][1]}@{mj[-1][2]:g}" if mj else None,
                                        "mjpg_fps_ranges": sorted({f"{c['w']}x{c['h']}@{c['min_fps']:g}-{c['max_fps']:g}" for c in d["caps"] if c["biCompression"] == "MJPG"}),
                                        "_has720p30": any(c["biCompression"] == "MJPG" and (c["w"], c["h"]) == (1280, 720) and c["min_fps"] - 0.01 <= 30 <= c["max_fps"] + 0.01 for c in d["caps"])}
for d in mf.get("devices", []):
    cam = mc.cam_from_vidpid(d["symbolic_link"])
    if not cam:
        continue
    mj = sorted({(t["width"], t["height"], round(t["fps_num"] / t["fps_den"], 2)) for t in d["native_types"] if t["subtype"] == "MJPG" and t["fps_den"]}, key=modes_key)
    per.setdefault(cam, {})["mf"] = {"name": d["name"], "symbolic_link": d["symbolic_link"], "activate_error": d["error"],
                                     "n_native_types": len(d["native_types"]), "subtypes": sorted({t["subtype"] for t in d["native_types"]}),
                                     "mjpg_modes": [f"{w}x{h}@{f:g}" for w, h, f in mj],
                                     "max_mjpeg": f"{mj[-1][0]}x{mj[-1][1]}@{mj[-1][2]:g}" if mj else None}
for cam, v in per.items():
    v["has_1280x720at30_mjpg"] = {"dshow": v["dshow"].pop("_has720p30") if "dshow" in v else None,
                                  "mf": ("1280x720@30" in v["mf"]["mjpg_modes"]) if "mf" in v else None}
    v["registry_max_mjpeg"] = "{}x{}@{}".format(*mc.WINDOWS_CAMERAS[cam]["max_mjpeg"])
summary = {"test": "mjpeg_formats", "platform": "windows", "hostname": mc.HOST, "utc_started": started,
           "command": "uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/mjpeg/list_formats.py --cams " + a.cams,
           "cams": cams, "excluded": {k: v for k, v in mc.EXCLUDED_CAMS.items() if k not in cams},
           "environment": mc.environment(), "tool_commands": [cmd_ds, cmd_mf],
           "dshow_order": mc.dshow_devices(), "mf_order": mc.mf_devices_enum_only(), "cameras": per}
(out / "summary.json").write_text(json.dumps(summary, indent=1))
for cam, v in per.items():
    print(cam, {api: (v[api].get("max_mjpeg"), v[api].get("subtypes")) for api in ("dshow", "mf") if api in v}, v["has_1280x720at30_mjpg"])
print("wrote", out / "summary.json")
