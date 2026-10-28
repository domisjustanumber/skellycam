# /// script
# requires-python = ">=3.10"
# ///
"""Collect every mjpeg_<backend>/<cell>/summary.json | failure.json under one results root into one table.

  uv run --script research/usb_cameras/mjpeg/aggregate.py --root research/usb_cameras/results/windows/Gerald/mjpeg_rerun_20261027 [--markdown]

--root is a run root written by run_matrix.py --root (layout <root>/mjpeg_<backend>/<cell>/). Writes <root>/table.json
(+ <root>/table.md with --markdown) and prints a fixed-width table. Without --root it reads the legacy 2026-10-25 layout
results/<platform>/<host>/mjpeg_<backend>/<cell>/ and writes results/<platform>/<host>/mjpeg_matrix/<UTC stamp>/ (an
earlier table is never overwritten). Cells containing INVALID.txt or SUPERSEDED.txt are listed separately, not tabled.

'native' column: per camera, the JPEG header fingerprint (DQT+SOF+DHT, mjpeg_common.jpeg_header) of the bytes this API
delivered is compared with the fingerprint the Media Foundation native-MJPG reader (MF_READWRITE_DISABLE_CONVERTERS,
reader output subtype verified MJPG) delivered for the same camera and mode in the same root. yes = same dominant tables
(same encoder: the camera's); partial = some fingerprints shared; NO = none shared (re-encoded somewhere); n/a = the API
delivered pixels, not JPEG. 'hdr==MF' additionally compares the full header bytes SOI..SOS (APPn/COM included).
"""
import argparse
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--platform", default={"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux"))
ap.add_argument("--host", default=socket.gethostname())
ap.add_argument("--root", action="append", default=None, help="repeatable; the table is written to the FIRST root")
ap.add_argument("--markdown", action="store_true")
ap.add_argument("--ref-test", default="mjpeg_msmf", help="test whose bytes are the camera-native reference (Linux: mjpeg_v4l2_mmap)")
a = ap.parse_args()
legacy = a.root is None
roots = [Path(r).resolve() for r in a.root] if a.root else [ROOT / "results" / a.platform / a.host]
base = roots[0]
SKIP_TESTS = {"mjpeg_matrix", "mjpeg_formats", "mjpeg_drafts_check"}
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mjpeg_common as _mc  # noqa: E402
CAMS = {k: v["vidpid"] for k, v in _mc.WINDOWS_CAMERAS.items()}


def relp(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO)).replace("\\", "/")
    except ValueError:
        return str(p)


def cam_of(text: str):
    t = text.lower()
    return next((k for k, v in CAMS.items() if v in t or v.replace("&", "_") in t), None)


def cam_by_name(name) -> str | None:
    """Older pyav cells addressed DirectShow devices by FriendlyName ('video=c922 Pro Stream Webcam')."""
    n = str(name or "").removeprefix("video=").strip().lower()
    return next((k for k, v in _mc.WINDOWS_CAMERAS.items() if v["dshow_name"].lower() == n), None)


rows, excluded = [], []
for d in sorted(d for r in roots for d in r.glob("mjpeg_*")):
    if d.name in SKIP_TESTS or not d.is_dir() or d.name.startswith(("mjpeg_run_", "mjpeg_rerun_")):
        continue
    for run in sorted(p for p in d.iterdir() if p.is_dir()):
        marks = [m for m in ("INVALID.txt", "SUPERSEDED.txt") if (run / m).exists()]
        if marks:
            excluded.append({"cell": relp(run), "mark": marks[0], "reason": (run / marks[0]).read_text(errors="replace").strip()[:400]})
            continue
        s, f = run / "summary.json", run / "failure.json"
        if s.exists():
            j = json.loads(s.read_text())
            cpu = j.get("cpu", {})
            ctl = (j.get("controls") or {}).get("readback_after_capture") or {}
            mcpu = j.get("machine_cpu") or {}
            dn = (j.get("devnode_status") or {})
            if not j.get("cameras"):  # every camera failed to open (errors[] says why)
                rows.append({"test": d.name, "label": run.name, "cam": None, "failed": True, "returncode": "0 (no camera opened)",
                             "log_tail": "; ".join(j.get("errors") or [])[-300:], "summary": relp(s)})
                continue
            for c in j.get("cameras", []):
                hdr = c.get("jpeg_header") or {}
                rm = c.get("requested_mode") or j.get("requested") or {}
                cam = c.get("cam") or cam_of(json.dumps(c)) or cam_by_name(c.get("name")) or c.get("device") or c.get("camera_key") or c.get("name")  # non-Windows: device path
                cc = ctl.get(cam) or next((v for k, v in ctl.items() if cam in _mc.WINDOWS_CAMERAS and _mc.WINDOWS_CAMERAS[cam]["dshow_name"].lower() in k.lower()), {}) or {}
                rows.append({
                    "test": d.name, "label": run.name, "cam": cam, "name": c.get("name") or c.get("camera_key"),
                    "req": f"{rm.get('width')}x{rm.get('height')}@{rm.get('fps'):g}" if rm.get("fps") else None,
                    "n_cams": len(j.get("cameras", [])),
                    "fps": round(c["fps_achieved_span"], 2) if c.get("fps_achieved_span") else None,
                    "fps_count_over_wall": round(c["fps_achieved_count_over_wall"], 2) if c.get("fps_achieved_count_over_wall") is not None else None,
                    "frames_in_window": c.get("frames_in_window"),
                    "gaps": c.get("gaps_over_1p5_period"),
                    "valid_jpeg_pct": c.get("pct_valid_jpeg_in_window"),
                    "valid_jpeg_strict_pct": c.get("pct_valid_jpeg_strict_all"),
                    "libjpeg_warnings": c.get("libjpeg_warnings_sample"),
                    "payload_p50": (c.get("payload_bytes") or {}).get("p50"),
                    "payload_min": (c.get("payload_bytes") or {}).get("min"),
                    "payload_max": (c.get("payload_bytes") or {}).get("max"),
                    "payload_mean": round((c.get("payload_bytes") or {}).get("mean") or 0) or None,
                    "fingerprints": hdr.get("fingerprints"), "header_sha1s": hdr.get("header_sha1s"), "has_dht": hdr.get("has_dht"),
                    "dqt_q0_first8": hdr.get("dqt_q0_first8"), "app": hdr.get("app"),
                    "codec": c.get("codec") or "/".join((c.get("frame_subtypes") or {}).keys()) or c.get("got_fourcc") or c.get("reader_output_subtype"),
                    "frame_shape": next(iter((c.get("frame_shapes") or {}).keys()), None),
                    "cpu_pct_process": round(cpu["process_cpu_pct_of_one_core"], 2) if cpu.get("process_cpu_pct_of_one_core") is not None else None,
                    "cpu_pct_per_cam": round(cpu["process_cpu_pct_per_camera"], 2) if cpu.get("process_cpu_pct_per_camera") is not None else None,
                    "frameserver_cpu_pct": cpu.get("frameserver_cpu_pct_of_one_core") if cpu.get("frameserver_ok", True) else None,
                    "machine_cpu_before": (mcpu.get("before") or {}).get("machine_cpu_pct"),
                    "machine_cpu_after": (mcpu.get("after") or {}).get("machine_cpu_pct"),
                    "luma_p50": (c.get("mean_luma") or {}).get("p50"),
                    "exposure": cc.get("exposure_log2s"), "exposure_mode": cc.get("exposure_log2s_mode"),
                    "ae_priority": cc.get("auto_exposure_priority"), "gain": cc.get("gain"),
                    "devnode_after": dn.get("after"),
                    "decoded_by_pipeline": j.get("decoded_by_pipeline"),
                    "silent_format_fallback": j.get("silent_format_fallback"),
                    "os_timestamp_source": c.get("os_timestamp_source"),
                    "timestamp_fields": sorted((c.get("timestamp_fields_present") or {}).keys()),
                    "os_timestamp_delta_ms": c.get("os_timestamp_delta_ms"),
                    "arrival_minus_os_ms_median": (c.get("arrival_minus_os_timestamp_ms") or {}).get("median"),
                    "first_frame_latency_ms": c.get("first_frame_latency_ms"),
                    "read_error": c.get("read_error"),
                    "errors": (j.get("errors") or [])[:2],
                    "utc_started": j.get("utc_started"),
                    "summary": relp(s),
                })
            for e in j.get("errors") or []:  # cameras that failed to open inside an otherwise working cell
                if "open failed" in e:
                    cam = cam_of(e)
                    if cam is None and run.name.count("_") >= 2:  # OpenCV errors name only the index: the cell's camera set minus those that opened
                        missing = set(run.name.split("_")[2].split("+")) - {c.get("cam") for c in j.get("cameras", [])}
                        cam = missing.pop() if len(missing) == 1 else None
                    rows.append({"test": d.name, "label": run.name, "cam": cam, "failed": True, "returncode": "0 (this camera did not open)",
                                 "log_tail": e[-300:], "summary": relp(s)})
        elif f.exists():
            j = json.loads(f.read_text())
            rows.append({"test": d.name, "label": run.name, "cam": None, "failed": True, "returncode": j.get("returncode"),
                         "log_tail": (j.get("capture_log_tail") or "")[-300:], "summary": relp(f)})


# native check against the MF reference (same cam + requested mode). Some cameras change DQT from frame to frame
# (adaptive quality), so compare the DOMINANT fingerprint, and report the overlap of the full sets too.
def dominant(fps_):
    return max(fps_.items(), key=lambda kv: kv[1])[0] if fps_ else None


ref = {}
for r in rows:
    if r.get("test") == a.ref_test and r.get("fingerprints") and (r.get("valid_jpeg_pct") or 0) > 0:
        e = ref.setdefault((r["cam"], r["req"]), {"dominant": set(), "all": set(), "hdr_all": set()})
        e["dominant"].add(dominant(r["fingerprints"]))
        e["all"] |= set(r["fingerprints"])
        e["hdr_all"] |= set(r.get("header_sha1s") or {})
for r in rows:
    if r.get("failed"):
        continue
    fps_ = r.get("fingerprints") or {}
    rset = ref.get((r["cam"], r["req"]))
    if not fps_:
        r["native"] = "n/a (pixels)" if r.get("decoded_by_pipeline") else "n/a (no frames)"
    elif rset is None:
        r["native"] = "no MF reference"
    elif dominant(fps_) in rset["dominant"]:
        r["native"] = "yes"
    else:
        r["native"] = "partial" if set(fps_) & rset["all"] else "NO"
    hs = set(r.get("header_sha1s") or {})
    r["header_bytes_shared_with_mf"] = (len(hs & rset["hdr_all"]), len(hs)) if (rset and hs) else None
    r["fingerprint_dominant"] = dominant(fps_)
    r["n_fingerprints"] = len(fps_)

out = base if not legacy else base / "mjpeg_matrix" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
out.mkdir(parents=True, exist_ok=True)
cmd = "uv run --script research/usb_cameras/mjpeg/aggregate.py" + "".join(f" --root {relp(r)}" for r in roots if not legacy) + (" --markdown" if a.markdown else "") + (f" --ref-test {a.ref_test}" if a.ref_test != "mjpeg_msmf" else "")
(out / "table.json").write_text(json.dumps({"test": "mjpeg_matrix", "platform": a.platform, "hostname": a.host, "root": relp(base), "roots": [relp(r) for r in roots],
                                            "utc": datetime.now(timezone.utc).isoformat(), "command": cmd, "native_reference_test": a.ref_test,
                                            "rows": rows, "excluded_cells": excluded}, indent=1))
print(f"{'test':24} {'label':40} {'cam':7} {'req':13} {'fps':>6} {'valid%':>6} {'p50B':>7} {'cpu%':>6} {'luma':>5} {'exp':>4} {'native':8} codec")
for r in rows:
    if r.get("failed"):
        print(f"{r['test']:24} {r['label']:40} FAILED rc={r['returncode']} {r['log_tail'][-100:]!r}")
        continue
    print(f"{r['test']:24} {r['label']:40} {str(r['cam']):7} {str(r['req']):13} {str(r['fps']):>6} {str(r['valid_jpeg_pct']):>6} {str(r['payload_p50']):>7} "
          f"{str(r['cpu_pct_process']):>6} {str(r['luma_p50']):>5} {str(r['exposure']):>4} {r['native']:8} {r['codec']} {r['frame_shape'] or ''}")
if a.markdown:
    md = ["| backend | cell | camera | requested | fps achieved | valid JPEG % | payload p50 (B) | process CPU % (1 core = 100) | machine CPU % before/after | luma p50 | exposure (log2 s, mode) | native bytes? | delivered | result |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        summary = Path(r["summary"]) if Path(r["summary"]).is_absolute() else REPO / r["summary"]
        link = os.path.relpath(summary, out).replace(os.sep, "/")  # relative to table.md's own folder
        if r.get("failed"):
            md.append(f"| {r['test'][6:]} | {r['label']} | {r.get('cam') or '-'} | - | FAILED ({r['returncode']}): {r['log_tail'][-120:].replace('|', '/')} | - | - | - | - | - | - | - | - | [result]({link}) |")
            continue
        md.append(f"| {r['test'][6:]} | {r['label']} | {r['cam']} | {r['req']} | {r['fps']} | {r['valid_jpeg_pct'] if r['valid_jpeg_pct'] is not None else 'n/a'} | "
                  f"{r['payload_p50']} | {r['cpu_pct_process']} | {r['machine_cpu_before']}/{r['machine_cpu_after']} | {r['luma_p50']} | {r['exposure']} {r['exposure_mode'] or ''} | "
                  f"{r['native']} | {r['codec']}{' ' + r['frame_shape'] if r['frame_shape'] else ''} | [summary]({link}) |")
    (out / "table.md").write_text("\n".join(md) + "\n")
    print("wrote", out / "table.md")
print("excluded (INVALID/SUPERSEDED):", len(excluded))
print("wrote", out / "table.json")
