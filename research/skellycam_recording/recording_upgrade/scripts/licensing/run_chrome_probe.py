"""Run electron_codec_probe/probe.html in headless Google Chrome and capture the JSON it logs.

Chrome prints console messages to stderr with --enable-logging=stderr; the page logs one line
RESULT_JSON_BEGIN{...}RESULT_JSON_END when done. No timing data is recorded.

Usage:
  python run_chrome_probe.py --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe" \
      --samples C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/licensing/samples \
      --profile <empty temp dir> --out <result.json>
"""
import argparse
import json
import pathlib
import re
import subprocess
import threading
import urllib.parse

ap = argparse.ArgumentParser()
ap.add_argument("--chrome", required=True)
ap.add_argument("--samples", required=True)
ap.add_argument("--profile", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--timeout", type=float, default=180)
a = ap.parse_args()

page = (pathlib.Path(__file__).parent / "electron_codec_probe" / "probe.html").resolve().as_uri()
samples = pathlib.Path(a.samples).resolve().as_uri() + "/"
url = page + "?samples=" + urllib.parse.quote(samples, safe="")
cmd = [a.chrome, "--headless=new", f"--user-data-dir={a.profile}", "--allow-file-access-from-files",
       "--autoplay-policy=no-user-gesture-required", "--enable-logging=stderr", "--v=0", url]
p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
found = {}


def reader():
    for line in p.stderr:
        m = re.search(r"RESULT_JSON_BEGIN(.*)RESULT_JSON_END", line)
        if m:
            found["json"] = m.group(1)
            p.terminate()
            return


t = threading.Thread(target=reader, daemon=True)
t.start()
t.join(a.timeout)
if p.poll() is None:
    p.kill()
if "json" not in found:
    raise SystemExit("no result captured")
d = json.loads(found["json"])
pathlib.Path(a.out).write_text(json.dumps(d, indent=1), encoding="utf-8")
print("wrote", a.out, d["userAgent"])
