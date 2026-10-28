# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pygrabber==0.2",
#   "numpy",
#   "comtypes",
# ]
# ///
"""pygrabber (DirectShow, Windows-only) probe: what identity it exposes, which formats, what a grab returns.

RUN (shared Windows machine):
  uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/pygrabber_probe.py

Checks:
  * FilterGraph.get_input_devices() return value (public identity API).
  * VideoInput.get_formats() per device (does it list MJPG?).
  * After set_format(<an MJPG format>) + add_sample_grabber, what the user callback receives
    (pygrabber forces the sample grabber media subtype to RGB24, so DirectShow inserts an MJPEG
    decoder; the callback gets an HxWx3 uint8 array, no JPEG bytes and no SampleTime).

OUTPUT results/windows/<hostname>/prior_art_pygrabber/result.json
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", action="append", default=[],
                    help="test only devices with exactly this FriendlyName (repeatable); others are never bound")
    args = ap.parse_args()
    if sys.platform != "win32":
        print("pygrabber is DirectShow-only (Windows)")
        return 2
    from importlib.metadata import version

    from pygrabber.dshow_graph import FilterGraph

    # USBCAM_RESULTS_DIR (optional) redirects output so a rerun does not overwrite cited results
    out = (Path(os.environ["USBCAM_RESULTS_DIR"]) if os.environ.get("USBCAM_RESULTS_DIR") else ROOT / "results" / "windows" / socket.gethostname()) / "prior_art_pygrabber"
    out.mkdir(parents=True, exist_ok=True)
    res = {"test": "prior_art_pygrabber_probe", "platform": "windows", "hostname": socket.gethostname(),
           "utc_started": dt.datetime.now(dt.timezone.utc).isoformat(),
           "command": "uv run --script research/usb_cameras/prior_art/pygrabber_probe.py " + " ".join(sys.argv[1:]),
           "environment": {"os": platform.platform(), "python": sys.version, "pygrabber": version("pygrabber")}}
    g = FilterGraph()
    devices = g.get_input_devices()
    res["get_input_devices"] = devices
    res["name_allowlist"] = args.name or None
    res["get_input_devices_types"] = sorted({type(d).__name__ for d in devices})
    res["cameras"] = []
    for idx, name in enumerate(devices):
        if any(v in name for v in ("NDI", "OBS", "Spout", "NVIDIA")):
            continue
        if args.name and name not in args.name:
            continue
        entry = {"index": idx, "name": name}
        try:
            g = FilterGraph()
            g.add_video_input_device(idx)
            vi = g.get_input_device()
            fmts = vi.get_formats()
            entry["n_formats"] = len(fmts)
            entry["media_types"] = sorted({f["media_type_str"] for f in fmts})
            mj = [f for f in fmts if f["media_type_str"] == "MJPG" and f["width"] == 1280 and f["height"] == 720]
            entry["chosen_format"] = mj[0] if mj else None
            if mj:
                vi.set_format(mj[0]["index"])
            got = {}
            ev = threading.Event()

            def cb(img, got=got, ev=ev):
                got["type"] = type(img).__name__
                got["shape"] = list(getattr(img, "shape", []))
                got["dtype"] = str(getattr(img, "dtype", ""))
                ev.set()

            g.add_sample_grabber(cb)
            g.add_null_render()
            g.prepare_preview_graph()
            g.run()
            time.sleep(1.5)
            g.grab_frame()
            t0 = time.time()
            while not ev.is_set() and time.time() - t0 < 5:
                time.sleep(0.05)  # callback arrives on a DirectShow streaming thread
            g.stop()
            entry["callback_result"] = got or "no callback within 5 s"
        except Exception as e:  # noqa: BLE001
            entry["error"] = repr(e)
        res["cameras"].append(entry)
    (out / "result.json").write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
