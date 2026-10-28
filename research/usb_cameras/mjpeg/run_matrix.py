# /// script
# requires-python = ">=3.10"
# ///
"""Windows test matrix for goal 1 (native MJPEG). One camlock invocation per cell (<~30 s hold), then an
unlocked validate/summarize step.

  uv run --script research/usb_cameras/mjpeg/run_matrix.py --backend msmf [--backend pyav-dshow ...]
        [--modes common,max] [--sets single,all] [--cams c922,c930e,usbcam] [--seconds 10] [--root DIR] [--dry-run]

Backends:
  msmf                  IMFSourceReader, native MJPG media type, MF_READWRITE_DISABLE_CONVERTERS (C++ tool)
  msmf-decoded-nv12     same, but MF inserts its MJPEG decoder (CPU comparison only; payload not stored)
  pyav-dshow            FFmpeg dshow, vcodec=mjpeg, packets demuxed and never decoded
  winrt                 Windows.Media.Capture MediaFrameReader, MJPG source format + MJPG reader subtype
  opencv-dshow-decode   OpenCV CAP_DSHOW, FOURCC=MJPG, CONVERT_RGB default (BGR frames: the skellycam path)
  opencv-dshow-raw      ... CONVERT_RGB=0
  opencv-msmf-decode    OpenCV CAP_MSMF, FOURCC=MJPG
  opencv-msmf-raw       ... CAP_PROP_FORMAT=-1, CONVERT_RGB=0
Modes: common = 1280x720@30 MJPG on every camera; max = each camera's own max MJPEG mode (mjpeg_common.WINDOWS_CAMERAS,
       verified by list_formats.py) for singles; for the all-cameras set every camera at its own max mode as well
       (backends that take one size for all cameras -- every one here except msmf-per-camera -- use the common
       denominator 1920x1080@30 then; recorded in the label).
Results: <root>/mjpeg_<backend>/<label>/summary.json (+frames.jsonl, controls.json); failures: .../<label>/failure.json.
         <root> defaults to research/usb_cameras/results/windows/<host>/mjpeg_run_<UTC stamp>/ -- a NEW directory per
         invocation; an existing cell is never deleted or overwritten (it is skipped). Then: aggregate.py --root <root>.
Cameras: default mjpeg_common.DEFAULT_CAMS (the Razer Kiyo Pro is excluded; name it in --cams to include it).
Raw payloads stay in $MJPEG_SCRATCH/<root name>/mjpeg_<backend>/<label>/ (not in the repo).
Devices are always addressed by USB VID/PID-bearing identifiers (MF symbolic link, DirectShow device path via
FFmpeg's '@device_pnp_' alternative name, WinRT source-group id), never by FriendlyName: the Kiyo Pro's DirectShow
FriendlyName is the generic "USB Video Device".
"""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parent.parent
sys.path.insert(0, str(HERE))
import mjpeg_common as mc  # noqa: E402

CAMS = mc.WINDOWS_CAMERAS
MF = str(mc.MF_TOOL)
CAMLOCK = ["uv", "run", "--script", str(ROOT / "tools" / "camlock.py"), "--timeout-s", "3600", "--"]
SCRATCH = mc.scratch_root()

ap = argparse.ArgumentParser()
ap.add_argument("--backend", action="append", required=True)
ap.add_argument("--modes", default="common,max")
ap.add_argument("--sets", default="single,all")
ap.add_argument("--cams", default=",".join(mc.DEFAULT_CAMS))
ap.add_argument("--root", default=None, help="results root for this run (default results/<plat>/<host>/mjpeg_run_<UTC stamp>)")
ap.add_argument("--capture-timeout-s", type=float, default=120, help="run_one.py kills a capture after this long")
ap.add_argument("--seconds", type=float, default=10)
ap.add_argument("--warmup", type=float, default=2)
ap.add_argument("--keep-samples", type=int, default=1, help="per camera: JPEG HEADER bytes only (privacy), see mjpeg_common")
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--label-suffix", default="")
ap.add_argument("--opencv-order", default="size-first", help="opencv_capture.py --set-order (fourcc-first|size-first|skellycam)")
ap.add_argument("--no-controls", action="store_true", help="do not set manual exposure/WB before the capture")
ap.add_argument("--skip-done", action="store_true", help="(kept for compatibility: existing cells are always skipped)")
a = ap.parse_args()
RES_ROOT = Path(a.root) if a.root else (ROOT / "results" / mc.plat() / mc.HOST / f"mjpeg_run_{mc.utc_stamp()}")
SCRATCH = SCRATCH / RES_ROOT.name


def rel(p):
    try:
        return str(Path(p).resolve().relative_to(REPO)).replace("\\", "/")
    except (ValueError, OSError):
        return str(p)


def mode_for(mode: str, group: list[str], backend: str):
    if mode == "common":
        return [mc.COMMON_MODE] * len(group)
    if len(group) == 1 or backend == "msmf" or backend == "winrt":
        return [CAMS[c]["max_mjpeg"] for c in group]
    return [(1920, 1080, 30)] * len(group)


def capture_cmd(backend, cams, modes, run_dir):
    s, wu = str(a.seconds), str(a.warmup)
    w, h, fps = modes[0]
    if backend.startswith("msmf"):
        c = [MF]
        for x, (mw, mh, mf) in zip(cams, modes):
            c += ["--dev", CAMS[x]["vidpid"]]
        c += ["--width", str(w), "--height", str(h), "--fps", str(fps)]
        if len(set(modes)) > 1:  # per-camera modes
            c += sum((["--mode", f"{mw}x{mh}@{mf}"] for mw, mh, mf in modes), [])
        c += ["--seconds", s, "--warmup", wu, "--out", str(run_dir), "--attr-dump", "5"]
        if backend == "msmf-decoded-nv12":
            c += ["--decode-to", "NV12", "--no-payload"]
        return c
    if backend == "pyav-dshow":
        c = ["uv", "run", "--script", str(HERE / "pyav" / "pyav_capture.py"), "--input-format", "dshow"]
        c += sum((["--device", "video=" + mc.dshow_alt_name(x)] for x in cams), [])
        return c + ["--size", f"{w}x{h}", "--fps", str(fps), "--seconds", s, "--warmup", wu, "--run-dir", str(run_dir)]
    if backend.startswith("opencv-"):
        _, api, mode = backend.split("-")
        idx = [mc.dshow_index(x) if api == "dshow" else mc.msmf_index(x) for x in cams]
        c = ["uv", "run", "--script", str(HERE / "opencv" / "opencv_capture.py"), "--api", api, "--mode", mode, "--set-order", a.opencv_order]
        c += sum((["--index", str(i)] for i in idx), []) + sum((["--name", x] for x in cams), [])
        return c + ["--size", f"{w}x{h}", "--fps", str(fps), "--seconds", s, "--warmup", wu, "--run-dir", str(run_dir)]
    if backend == "winrt":
        c = ["uv", "run", "--script", str(HERE / "winrt" / "winrt_capture.py")] + sum((["--dev", CAMS[x]["vidpid"]] for x in cams), [])
        if len(set(modes)) > 1:
            c += sum((["--mode", f"{mw}x{mh}@{mf}"] for mw, mh, mf in modes), [])
        return c + ["--size", f"{w}x{h}", "--fps", str(fps), "--seconds", s, "--warmup", wu, "--run-dir", str(run_dir)]
    raise SystemExit(f"unknown backend {backend}")


cams_all = a.cams.split(",")
plan = []
for backend in a.backend:
    for mode in a.modes.split(","):
        for st in a.sets.split(","):
            groups = [[c] for c in cams_all] if st == "single" else [cams_all]
            for g in groups:
                modes = mode_for(mode, g, backend)
                if len(set(modes)) == 1:
                    w, h, fps = modes[0]
                    mstr = f"{w}x{h}at{fps}"
                else:
                    mstr = "own-max"
                label = f"{mode}_{mstr}_{'+'.join(g)}{a.label_suffix}"
                plan.append((backend, g, modes, label))

index = []
host = mc.HOST
for backend, g, modes, label in plan:
    out = RES_ROOT / f"mjpeg_{backend}" / label
    if out.exists():  # never delete or overwrite an earlier result
        print("skip (exists)", rel(out))
        continue
    run_dir = SCRATCH / f"mjpeg_{backend}" / label
    if run_dir.exists():
        shutil.rmtree(run_dir)
    inner = capture_cmd(backend, g, modes, run_dir)
    ctl = [] if not a.no_controls else ["--no-set"]
    cmd = CAMLOCK + ["uv", "run", "--script", str(HERE / "run_one.py"), "--cams", ",".join(g), "--run-dir", str(run_dir),
                     "--timeout-s", str(a.capture_timeout_s)] + ctl + ["--"] + inner
    printable = " ".join(shlex.quote(rel(x) if os.path.isabs(str(x)) and str(x).startswith(str(REPO)) else str(x)) for x in cmd)
    print(f"\n=== {backend} {label}\n{printable}", flush=True)
    if a.dry_run:
        continue
    t0 = time.time()
    try:
        rc = subprocess.call(cmd, timeout=3900)
    except subprocess.TimeoutExpired:
        rc = -999
    entry = {"backend": backend, "label": label, "rc": rc, "capture_command": printable, "s": round(time.time() - t0, 1)}
    if rc == 0 and (run_dir / "meta.json").exists():
        scmd = ["uv", "run", "--script", str(HERE / "summarize.py"), str(run_dir), "--test", f"mjpeg_{backend}", "--label", label,
                "--command", printable, "--keep-samples", str(a.keep_samples), "--root", str(RES_ROOT)]
        if "decoded" in backend or backend.endswith("-decode"):
            scmd.append("--not-jpeg")
        entry["summarize_rc"] = subprocess.call(scmd)
    else:
        out.mkdir(parents=True, exist_ok=True)
        (out / "failure.json").write_text(json.dumps({
            "test": f"mjpeg_{backend}", "platform": "windows", "hostname": host, "utc": mc.utc_now(), "command": printable, "returncode": rc,
            "devnode_status_now": mc.devnode_status(),
            "capture_log_tail": (run_dir / "capture_log.txt").read_text(errors="replace")[-3000:] if (run_dir / "capture_log.txt").exists() else None,
            "controls": json.loads((run_dir / "controls.json").read_text()) if (run_dir / "controls.json").exists() else None}, indent=1))
    index.append(entry)
RES_ROOT.mkdir(parents=True, exist_ok=True)
idx_path = RES_ROOT / f"index_{mc.utc_stamp()}.json"
idx_path.write_text(json.dumps({"command": " ".join(sys.argv), "root": rel(RES_ROOT), "cells": index}, indent=1))
print(json.dumps(index, indent=1))
print("wrote", idx_path)
