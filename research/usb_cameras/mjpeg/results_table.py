# /// script
# requires-python = ">=3.10"
# ///
"""Condensed goal-1 matrix (approach x camera x mode -> fps, valid %, CPU %, native?) as Markdown, from aggregate.py's
table.json. Links are relative to research/usb_cameras/mjpeg/ (where RESULTS.md lives).

  uv run --script research/usb_cameras/mjpeg/results_table.py --root research/usb_cameras/results/windows/Gerald/mjpeg_rerun_20261027

Prints the table; with --out writes it to a file. Opens no camera.
"""
import argparse
import json
import re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--root", required=True)
ap.add_argument("--out", default=None)
a = ap.parse_args()
t = json.loads((Path(a.root) / "table.json").read_text())
APPROACH = {
    "mjpeg_msmf": "(b) MF IMFSourceReader, native MJPG",
    "mjpeg_pyav-dshow": "(a) PyAV dshow vcodec=mjpeg",
    "mjpeg_winrt": "(c) WinRT MediaFrameReader, MJPG subtype",
    "mjpeg_winrt_variants": "(c) WinRT variants",
    "mjpeg_opencv-dshow-decode": "(d) OpenCV CAP_DSHOW decode",
    "mjpeg_opencv-dshow-raw": "(d) OpenCV CAP_DSHOW CONVERT_RGB=0",
    "mjpeg_opencv-msmf-decode": "(d) OpenCV CAP_MSMF decode",
    "mjpeg_opencv-msmf-raw": "(d) OpenCV CAP_MSMF FORMAT=-1, CONVERT_RGB=0",
    "mjpeg_msmf-decoded-nv12": "(ref) MF with its MJPEG decoder -> NV12",
}
ORDER = list(APPROACH)
CAM_ORDER = {"c922": 0, "c930e": 1, "usbcam": 2}


def link(r):
    s = r["summary"]
    return "../" + s.split("research/usb_cameras/", 1)[1] if "research/usb_cameras/" in s else s


def fmt(v, nd=1):
    return "-" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


rows = [r for r in t["rows"]]
rows.sort(key=lambda r: (ORDER.index(r["test"]) if r["test"] in ORDER else 99, r["label"].split("_")[0], "+" in r["label"], r["label"],
                         CAM_ORDER.get(r.get("cam") or "", 9)))
out = ["| approach | mode | set | camera | fps | valid JPEG % | payload p50 kB | process CPU % (cell) | luma p50 | native bytes? | delivered | cell |",
       "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
for r in rows:
    mode = r["label"].split("_")[1] if "_" in r["label"] else r["label"]
    cams = r["label"].split("_")[2] if r["label"].count("_") >= 2 else ""
    sset = "all 3" if "+" in cams else "single"
    suffix = "_".join(r["label"].split("_")[3:])
    if suffix:
        sset += f" ({suffix})"
    name = Path(r["summary"]).parent.name
    if r["test"] == "mjpeg_winrt_variants":  # labels are <reader subtype>_<memory>_<acquisition>_<vidpid>
        mode, sset = (r.get("req") or "").replace("@", "at"), "single, reader " + " ".join(r["label"].split("_")[:3])
    if r.get("failed"):
        why = (re.search(r"(open failed[^,]*,[^,]*|grab failed[^']*)", r["log_tail"]) or re.search(r".{0,60}$", r["log_tail"])).group(0).replace("|", "/")
        out.append(f"| {APPROACH.get(r['test'], r['test'])} | {mode} | {sset} | {r.get('cam') or '-'} | did not open | - | - | - | - | - | {why} | [{name}]({link(r)}) |")
        continue
    kb = fmt(r["payload_p50"] / 1000 if r.get("payload_p50") else None, 0)
    codec = r.get("codec") or ""
    if codec and not codec.isprintable():  # OpenCV CAP_MSMF reports CAP_PROP_FOURCC as a small number, not a FOURCC
        codec = f"fourcc={int.from_bytes(codec.encode('latin-1')[:4], 'little')}"
    deliv = codec + (" " + r["frame_shape"] if r.get("frame_shape") else "")
    if r.get("fps") is None and r.get("read_error") not in (None, "0x00000000"):
        deliv += f" ReadSample {r['read_error']}"
    out.append(f"| {APPROACH.get(r['test'], r['test'])} | {mode} | {sset} | {r['cam']} | {fmt(r['fps'], 2)} | {fmt(r['valid_jpeg_pct'])} | {kb} | "
               f"{fmt(r['cpu_pct_process'])} | {fmt(r['luma_p50'])} | {r['native']} | {deliv.strip()} | [{name}]({link(r)}) |")
md = "\n".join(out) + "\n"
print(md)
if a.out:
    Path(a.out).write_text(md)
