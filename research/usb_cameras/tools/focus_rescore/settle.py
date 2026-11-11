"""Focus step settle time from W-CTRL-EFFECT MF focus runs: for each in-stream focus set, time from the set (QPC)
to the first saved frame whose sharpness is within 15% (log-space) of the settled level of that segment
(median of the last 40% of the segment). Read-only on result files."""
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sharp_timeline import sharp  # noqa: E402

SUITE = Path(r"C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_20261111T040003Z")
RAW = Path(r"C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261111T040003Z\W-CTRL-EFFECT")
FOLD = {"1532": "usbvideodevice_1532-0e05_4", "046d:0843": "logitechwebcam_046d-0843_8",
        "046d:085c": "c922prostreamw_046d-085c_C922SN01"}

d = json.load(open(SUITE / "W-CTRL-EFFECT.json"))
for key, cam in d["measurements"]["cameras"].items():
    folder = next((v for k, v in FOLD.items() if key.startswith(k)), None)
    if not folder:
        continue
    f = cam["paths"]["mf"]["controls"]["focus"]
    lat = []
    for i, run in enumerate(f["runs"]):
        rd = RAW / folder / f"mf_focus_r{i}"
        rows = [json.loads(x) for x in (rd / "frames.jsonl").read_text().splitlines() if x.strip()]
        data = (rd / "frames.mjpeg").read_bytes()
        pts = []
        for r in rows:
            off, ln = r.get("mjpeg_offset"), r.get("mjpeg_len")
            if off is None or ln is None or off < 0 or ln <= 0:
                continue
            pts.append((r["qpc_ns"], sharp(data[off:off + ln])))
        sets = [e for e in run["schedule"] if e.get("at_ms", 0) > 0]
        bounds = [e["applied_qpc_ns"] for e in sets] + [pts[-1][0] + 1]
        for j, e in enumerate(sets):
            seg = [(t, s) for t, s in pts if bounds[j] <= t < bounds[j + 1]]
            if len(seg) < 4:
                continue
            tail = [s for _, s in seg[int(len(seg) * 0.6):]]
            target = statistics.median(tail)
            prev = [s for t, s in pts if t < bounds[j]][-1]
            if abs(math.log(prev / target)) < math.log(1.3):
                continue  # step too small to time
            hit = next((t for t, s in seg if abs(math.log(s / target)) < math.log(1.15)), None)
            if hit is not None:
                lat.append(round((hit - e["applied_qpc_ns"]) / 1e6))
    print(folder, "n", len(lat), "settle ms", sorted(lat),
          "median", statistics.median(lat) if lat else None, "max", max(lat) if lat else None)
