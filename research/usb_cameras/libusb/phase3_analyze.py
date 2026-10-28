# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy<2.3", "pillow==12.0.0", "simplejpeg==1.8.2"]
# ///
"""Phase 3 analyzer: C922 (046d:085c) and generic Jieli "USB Camera" (4c4a:4a55) on inbox WinUSB, every user-space
backend. Reads what libusb/phase3_windows.ps1 wrote; opens no camera (no camlock needed).

  uv run --script research/usb_cameras/libusb/phase3_analyze.py runs GROUP_DIR [GROUP_DIR...]
      every <GROUP_DIR>/<run>/run.json (written by the runner) -> <run>/analysis.json and <GROUP_DIR>/analysis.json
  uv run --script research/usb_cameras/libusb/phase3_analyze.py timing RUN_DIR [--hc-match dev_7a60] [--out FILE]
      SCR/SOF -> QPC analysis of one uvc_capture_test run (frames.jsonl + usb_frame_qpc.jsonl)
  uv run --script research/usb_cameras/libusb/phase3_analyze.py summary --results-root research/usb_cameras/results/windows/<host>
      every phase3_*/analysis.json + the C930e phase-2 baselines -> <root>/phase3_summary.json
  uv run --script research/usb_cameras/libusb/phase3_analyze.py selftest --results-root ...
      decoder/parsers on synthetic + real phase-2 C930e data (no camera) -> <root>/phase3_analyze_selftest.json

Per run (kinds libuvc | py_libusb1 | pyuvc | rust | mf):
  * frames, fps, chosen alt + bytes/interval, PROBE/COMMIT dwMaxPayloadTransferSize, errors;
  * STRICT decode of EVERY delivered frame with bandwidth/verify/strict_jpeg_check.py check(): marker walk (SOI, SOFn
    size, RSTn order/count, EOI) + libjpeg-turbo strict (simplejpeg strict=True: any libjpeg warning fails) + Pillow
    (reported separately; NOT used for the pass/fail). strict_ok = marker_ok AND libjpeg strict AND size == mode.
    Frames are read from the raw store (scratchpad): libuvc frame_*.jpg, py/pyuvc u32-LE-length dumps, uvc_iso
    concatenated --raw-mjpeg (offsets from frames_*.jsonl payload_bytes). A frame that never reached the raw store
    (libuvc saves only SOI/EOI-valid frames) counts as failed: pct_strict_ok = strict_ok / frames delivered;
  * the alt the HOST actually selected: bandwidth/win_usb_topology.py --pipes-only snapshot(s) taken while streaming
    (pipes*.json in the run dir; pyuvc embeds its own) -> VS alt settings whose endpoint descriptor equals an open
    pipe; alt_confirmed_by_pipes = chosen alt in that set;
  * libuvc runs with usb_frame_qpc.jsonl: the timing block below.
Timing (SCR/SOF -> QPC; the xHCI frame counter sampled by uvc_capture_test --frame-qpc):
  1. bus-frame clock: (usb_frame + uframe/8, QPC) samples of the host controller -> t_frame(F) = a + b F
     (LSQ slope, lower-envelope intercept);
  2. device SOF sanity: unwrapped 11-bit SCR SOF (first payload of each frame) vs host time -> counts per host
     second (a working device latches the bus SOF: 1000/s; Linux UVC_QUIRK_INVALID_DEVICE_SOF marks C920/C922);
     callback_minus_sof_frame_ms = first-payload callback time - t_frame(unwrapped SOF) (valid SOF: 0..~8 ms);
  3. STC -> QPC: LSQ line over (STC, t_frame(SOF)) of first+last SCR of every frame -> STC Hz vs the VC header
     dwClockFrequency, ppm, residual (meaningful only if 2. passes) and, independent of SOF, STC vs host first-payload
     time (arrival-based, upper bound on jitter);
  4. PTS: step in ticks, PTS - STC (ms), host arrival - PTS mapped through the STC line (latency).
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import socket
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent  # research/usb_cameras/libusb
UC = HERE.parent
_spec = importlib.util.spec_from_file_location("strict_jpeg_check", UC / "bandwidth" / "verify" / "strict_jpeg_check.py")
sjc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sjc)
U32 = 1 << 32


# ---------------------------------------------------------------- helpers
def load_json(p: Path):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return {"_error": f"{type(e).__name__}: {e}", "_path": str(p)}


def load_jsonl(p: Path) -> list[dict]:
    if not Path(p).exists():
        return []
    out = []
    for line in Path(p).read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def st(v, scale=1.0) -> dict | None:
    v = [float(x) * scale for x in v if x is not None and np.isfinite(x)]
    if not v:
        return None
    s = sorted(v)
    q = lambda p: s[min(len(s) - 1, int(round(p * (len(s) - 1))))]  # noqa: E731
    return {"n": len(s), "mean": statistics.fmean(s), "std": statistics.pstdev(s) if len(s) > 1 else 0.0, "min": s[0],
            "p02": q(0.02), "p50": q(0.5), "p98": q(0.98), "max": s[-1]}


def unwrap(v: np.ndarray, bits: int) -> np.ndarray:
    m = 1 << bits
    d = np.diff(v.astype(np.int64)) % m
    d = np.where(d >= m // 2, d - m, d)
    return np.concatenate([[v[0]], v[0] + np.cumsum(d)]).astype(np.float64)


def linfit(x: np.ndarray, y: np.ndarray):
    xm, ym = x.mean(), y.mean()
    b = float(((x - xm) * (y - ym)).sum() / ((x - xm) ** 2).sum())
    a = float(ym - b * xm)
    return a, b, y - (a + b * x)


# ---------------------------------------------------------------- frame sources
def iter_u32(path: Path):
    data = Path(path).read_bytes()
    i = 0
    while i + 4 <= len(data):
        n = int.from_bytes(data[i:i + 4], "little")
        yield data[i + 4:i + 4 + n]
        i += 4 + n


def iter_concat(path: Path, sizes: list[int]):
    data = Path(path).read_bytes()
    off = 0
    for n in sizes:
        yield data[off:off + n]
        off += n


def iter_jpg_dir(d: Path):
    for p in sorted(Path(d).glob("frame_*.jpg")):
        yield p.read_bytes()


def strict_frames(blobs, w: int | None, h: int | None) -> dict:
    r = {"checked": 0, "strict_ok": 0, "marker_ok": 0, "libjpeg_strict_ok": 0, "pillow_ok": 0, "size_ok": 0,
         "dims": {}, "fail_examples": [], "dri": set(), "trailing_after_eoi_nonzero": 0}
    for b in blobs:
        c = sjc.check(b)
        wk = c["walk"]
        size_ok = (w is None or (wk["w"] == w and wk["h"] == h))
        ok = bool(c["marker_ok"] and c["cv_ok"] and size_ok)
        r["checked"] += 1
        r["strict_ok"] += ok
        r["marker_ok"] += bool(c["marker_ok"])
        r["libjpeg_strict_ok"] += bool(c["cv_ok"])
        r["pillow_ok"] += bool(c["pil_ok"])
        r["size_ok"] += bool(size_ok)
        k = f'{wk["w"]}x{wk["h"]}'
        r["dims"][k] = r["dims"].get(k, 0) + 1
        r["dri"].add(wk["dri"])
        if wk.get("trailing_after_eoi"):
            r["trailing_after_eoi_nonzero"] += 1
        if not ok and len(r["fail_examples"]) < 3:
            r["fail_examples"].append({"index": r["checked"] - 1, "bytes": len(b), "marker_ok": c["marker_ok"], "libjpeg": c["cv_why"][:120],
                                       "pillow": c["pil_why"][:80], "w": wk["w"], "h": wk["h"], "rst": wk["rst"], "expected_rst": wk["expected_rst"]})
    r["dri"] = sorted(r["dri"])
    return r


# ---------------------------------------------------------------- pipes
def pipes_alts(paths: list[Path], vid: str, pid: str) -> dict:
    snaps = []
    for p in paths:
        j = load_json(p)
        if isinstance(j, dict) and "_error" in j:
            snaps.append({"file": Path(p).name, "error": j["_error"]})
            continue
        cams = [c for c in j if str(c.get("idVendor", "")).lower().endswith(vid) and str(c.get("idProduct", "")).lower().endswith(pid)]
        if not cams:
            snaps.append({"file": Path(p).name, "seen": False})
            continue
        c = cams[0]
        iso = [pp for pp in c.get("open_pipes", []) if pp.get("type") == "isochronous"]
        snaps.append({"file": Path(p).name, "seen": True, "hub": c.get("hub"), "port": c.get("port"),
                      "iso_pipes": [{k: pp.get(k) for k in ("bEndpointAddress", "wMaxPacketSize", "base_packet_bytes", "transactions_per_microframe")} for pp in iso],
                      "alts": sorted({m["bAlternateSetting"] for m in c.get("matched_alt_settings", [])}),
                      "bytes_per_interval": sorted({m["bytes_per_interval"] for m in c.get("matched_alt_settings", [])})})
    alts = sorted({a for s in snaps for a in s.get("alts", [])})
    return {"snapshots": snaps, "alts_seen": alts}


def confirm(chosen, pipes: dict):
    if chosen is None or not pipes.get("snapshots"):
        return None
    good = [s for s in pipes["snapshots"] if s.get("seen")]
    if not good:
        return None
    return all(chosen in s.get("alts", []) for s in good)


# ---------------------------------------------------------------- timing
def frame_clock(fq: Path, hc_match: str) -> dict | None:
    recs = load_jsonl(fq)
    hdr = [r for r in recs if "path" in r]
    hc = next((r["hc"] for r in hdr if hc_match in r["path"].lower()), None)
    if hc is None:
        return None
    s = [r for r in recs if r.get("hc") == hc and "usb_frame" in r]
    if len(s) < 3:
        return None
    x = np.array([r["usb_frame"] + r["uframe"] / 8.0 for r in s])
    y = np.array([r["frame_qpc_ns"] for r in s], float)
    a, b, res = linfit(x, y)
    a_env = float(np.min(y - b * x))
    return {"a": a_env, "b": b, "n": len(s), "ns_per_frame": b, "usb_frame_vs_qpc_ppm": (1e6 / b - 1) * 1e6,
            "lsq_residual_us": st(res, 1e-3), "hc": hc, "path": next(r["path"] for r in hdr if r["hc"] == hc)}


def timing(run: Path, hc_match: str = "dev_7a60", skip: int = 5) -> dict:
    rows = load_jsonl(run / "frames.jsonl")
    out: dict = {"run": str(run), "frames": len(rows)}
    rows = [r for r in rows if r.get("uvc_scr_stc_first") is not None and r.get("uvc_scr_sof_first") is not None and r.get("uvc_pts") is not None]
    rows = rows[skip:]
    out["frames_used"] = len(rows)
    if len(rows) < 20:
        out["error"] = "too few frames with PTS+SCR"
        return out
    g = lambda k: np.array([r[k] for r in rows], dtype=np.float64)  # noqa: E731
    nominal = float(rows[0].get("device_clock_hz") or 0)
    out["dwClockFrequency_nominal_hz"] = nominal
    hf, hl, host = g("host_first_payload_ns"), g("host_last_payload_ns"), g("host_arrival_ns")
    stc1 = unwrap(np.array([r["uvc_scr_stc_first"] for r in rows], np.int64), 32)
    stc2 = unwrap(np.array([r["uvc_scr_stc"] for r in rows], np.int64), 32)
    if abs(stc2[0] - stc1[0]) > U32 / 2:
        stc2 += np.round((stc1[0] - stc2[0]) / U32) * U32
    pts = unwrap(np.array([r["uvc_pts"] for r in rows], np.int64), 32)
    if abs(pts[0] - stc1[0]) > U32 / 2:
        pts += np.round((stc1[0] - pts[0]) / U32) * U32
    sof1 = np.array([r["uvc_scr_sof_first"] for r in rows], np.int64) & 0x7FF
    sof2 = np.array([r["uvc_scr_sof"] for r in rows], np.int64) & 0x7FF
    # 2. SOF counter rate vs host time (independent of the bus-frame samples)
    usof = unwrap(sof1, 11)
    a_s, b_s, r_s = linfit((hf - hf[0]) / 1e9, usof)
    out["device_sof_counts_per_host_s"] = b_s
    out["device_sof_vs_1000_per_s_pct"] = 100 * (b_s / 1000 - 1)
    out["device_sof_fit_residual_ms"] = st(r_s)
    # STC rate vs host arrival (SOF-independent)
    a_h, b_h, r_h = linfit(stc1, hf)
    out["stc_hz_vs_host_first_payload"] = 1e9 / b_h
    out["stc_vs_host_first_payload_residual_us"] = st(r_h, 1e-3)
    fc = frame_clock(run / "usb_frame_qpc.jsonl", hc_match)
    out["usb_frame_clock"] = {k: v for k, v in (fc or {}).items() if k not in ("a",)} if fc else None
    if fc:
        def unwrap_sof(sof, t_ref):
            fpred = (t_ref - fc["a"]) / fc["b"]
            return sof + 2048 * np.round((fpred - sof) / 2048.0)
        f1, f2 = unwrap_sof(sof1, hf), unwrap_sof(sof2, hl)
        t1, t2 = fc["a"] + fc["b"] * f1, fc["a"] + fc["b"] * f2
        d1 = (hf - t1) / 1e6
        out["callback_minus_sof_frame_ms"] = {"first": st(d1), "last": st((hl - t2) / 1e6)}
        out["sof_plausible_fraction"] = float(np.mean((d1 > 0) & (d1 < 8)))
        S, T = np.concatenate([stc1, stc2]), np.concatenate([t1, t2])
        c, d, res = linfit(S, T)
        out["stc_hz_vs_qpc_via_sof"] = 1e9 / d
        out["stc_ppm_vs_nominal_via_sof"] = (1e9 / d / nominal - 1) * 1e6 if nominal else None
        out["stc_line_residual_us"] = st(res, 1e-3)
        lat = (host - (c + d * pts + 0.5e6)) / 1e6
        out["arrival_minus_pts_via_sof_ms"] = st(lat)
    out["stc_ppm_vs_nominal_via_host"] = (out["stc_hz_vs_host_first_payload"] / nominal - 1) * 1e6 if nominal else None
    dp = np.diff(pts)
    med = float(np.median(dp)) if len(dp) else None
    out["pts_step_ticks_median"] = med
    out["pts_steps_not_1x"] = int(np.sum(np.abs(dp / med - 1) > 0.3)) if med else None
    out["stc_first_minus_pts_ms"] = st((stc1 - pts) / nominal * 1e3) if nominal else None
    out["stc_first_step_ms"] = st(np.diff(stc1) / nominal * 1e3) if nominal else None
    out["sof_valid"] = bool(abs(out["device_sof_vs_1000_per_s_pct"]) < 1.0 and out.get("sof_plausible_fraction", 0) > 0.95)
    return out


# ---------------------------------------------------------------- per-kind analysis
def mode_of(meta: dict):
    return meta.get("width"), meta.get("height"), meta.get("fps")


def analyse_run(rd: Path) -> dict:
    meta = load_json(rd / "run.json")
    vid, pid = (meta.get("vid") or "").lower(), (meta.get("pid") or "").lower()
    w, h, fps = mode_of(meta)
    kind = meta.get("kind")
    raw = Path(meta["raw"]) if meta.get("raw") else None
    out = {"run": rd.name, "kind": kind, "camera": meta.get("camera"), "mode": f"{w}x{h}@{fps}" if w else None,
           "requested": meta.get("requested"), "exit_code": meta.get("exit_code"), "timed_out": meta.get("timed_out"),
           "command": meta.get("command"), "raw": str(raw) if raw else None}
    pipes_files = sorted(rd.glob("pipes*.json"))
    try:
        if kind == "libuvc":
            res = load_json(rd / "result.json")
            if "_error" in res:
                out["error"] = "no result.json"
                return out
            iso, neg, m = res.get("iso", {}), res.get("negotiation", {}), res.get("measurements", {})
            out.update({"chosen_alt": iso.get("chosen_altsetting"), "bytes_per_interval": iso.get("bytes_per_packet"),
                        "stream_start_error": iso.get("stream_start_error"), "stream_start_error_name": iso.get("stream_start_error_name"),
                        "probe_dwMaxPayloadTransferSize": (neg.get("probe") or {}).get("dwMaxPayloadTransferSize"),
                        "commit_dwMaxPayloadTransferSize": (neg.get("commit") or {}).get("dwMaxPayloadTransferSize"),
                        "commit_dwMaxVideoFrameSize": (neg.get("commit") or {}).get("dwMaxVideoFrameSize"),
                        "commit_dwFrameInterval": (neg.get("commit") or {}).get("dwFrameInterval"),
                        "probe_only": m.get("probe_only"), "frames": m.get("frames"), "fps": m.get("fps_from_arrivals"),
                        "seq_gaps": m.get("seq_gaps"), "error_payloads": m.get("error_payloads"), "jpeg_soi_eoi_ok": m.get("jpeg_soi_eoi_ok"),
                        "controls": res.get("controls"),
                        "vs_altsettings": [(a["alt"], a["bytes_per_interval"]) for a in (res.get("cameras") or [{}])[0].get("vs_altsettings", [])]})
            frames = load_jsonl(rd / "frames.jsonl")
            if frames and fps:
                hz = frames[0].get("device_clock_hz") or 0
                per = hz / fps if hz else None
                sk = 0
                for a_, b_ in zip(frames[1:], frames[2:]):
                    if per and a_.get("uvc_scr_stc_first") is not None and b_.get("uvc_scr_stc_first") is not None:
                        k = round(((b_["uvc_scr_stc_first"] - a_["uvc_scr_stc_first"]) % U32) / per)
                        sk += max(0, k - 1)
                out["camera_skipped_frames_by_stc"] = sk
                arr = [f["host_arrival_ns"] for f in frames]
                gaps = [(q - p) / 1e6 for p, q in zip(arr, arr[1:])]
                out["host_gaps_gt_1p5_period"] = sum(1 for x in gaps if x > 1.5 * 1000 / fps)
                sizes = [f["payload_bytes"] for f in frames]
                out["payload_bytes"] = st(sizes)
                if out.get("bytes_per_interval"):
                    cap = out["bytes_per_interval"] * 8000 / fps
                    out["capacity_bytes_per_frame"] = round(cap)
                    out["median_payload_over_capacity"] = round(statistics.median(sizes) / cap, 3)
            if raw and raw.is_dir() and out.get("frames"):
                out["decode"] = strict_frames(iter_jpg_dir(raw), w, h)
            if (rd / "usb_frame_qpc.jsonl").exists() and out.get("frames", 0) and out["frames"] > 40:
                t = timing(rd)
                out["timing"] = {k: t.get(k) for k in ("device_sof_counts_per_host_s", "sof_plausible_fraction", "sof_valid",
                                                       "stc_hz_vs_qpc_via_sof", "stc_ppm_vs_nominal_via_sof", "stc_line_residual_us",
                                                       "stc_hz_vs_host_first_payload", "stc_ppm_vs_nominal_via_host",
                                                       "pts_step_ticks_median", "arrival_minus_pts_via_sof_ms", "error")}
        elif kind == "py_libusb1":
            res = load_json(rd / "result.json")
            if "_error" in res:
                out["error"] = "no result.json"
                return out
            iso, m, neg = res.get("iso", {}), res.get("measurements", {}), res.get("negotiation", {})
            out.update({"chosen_alt": iso.get("altsetting"), "bytes_per_interval": iso.get("bytes_per_packet"), "need_bytes": iso.get("need_bytes"),
                        "probe_dwMaxPayloadTransferSize": (neg.get("probe") or {}).get("dwMaxPayloadTransferSize"),
                        "commit": neg.get("commit"), "frames": m.get("frames"), "fps": m.get("fps_from_arrivals"),
                        "transfer_errors": m.get("transfer_errors"), "iso_packet_errors": m.get("iso_packet_errors"),
                        "uvc_error_payloads": m.get("uvc_error_payloads"), "cpu_fraction_of_one_core": m.get("cpu_fraction_of_one_core"),
                        "error": res.get("error")})
            if raw and raw.exists():
                out["decode"] = strict_frames(iter_u32(raw), w, h)
        elif kind == "pyuvc":
            res = load_json(rd / "result.json")
            if "_error" in res:
                out["error"] = "no result.json"
                return out
            out["error"] = res.get("error")
            out["streams"] = []
            for s in res.get("streams", []):
                ps = s.get("pipes_snapshot") or []
                cam = [c for c in ps if str(c.get("idVendor", "")).lower().endswith(vid) and str(c.get("idProduct", "")).lower().endswith(pid)]
                alts = sorted({mm["bAlternateSetting"] for c in cam for mm in c.get("matched_alt_settings", [])})
                bpi = sorted({mm["bytes_per_interval"] for c in cam for mm in c.get("matched_alt_settings", [])})
                e = {"bandwidth_factor": s.get("bandwidth_factor"), "mode": s.get("mode"), "frames": s.get("frames"),
                     "fps": s.get("fps_from_arrivals"), "pillow_full_decode_ok": s.get("pillow_full_decode_ok"),
                     "frame_index_gaps": s.get("frame_index_gaps"), "get_frame_errors": s.get("get_frame_errors"),
                     "pyuvc_expected_bytes_per_packet": s.get("pyuvc_expected_bytes_per_packet"),
                     "pipes_alts": alts, "pipes_bytes_per_interval": bpi, "error": s.get("error")}
                if s.get("raw_dump") and Path(s["raw_dump"]).exists():
                    e["decode"] = strict_frames(iter_u32(Path(s["raw_dump"])), w, h)
                out["streams"].append(e)
        elif kind == "rust":
            res = load_json(rd / "summary.json")
            if "_error" in res:
                out["error"] = "no summary.json"
                return out
            r_ = res.get("results") or {}
            al = res.get("alt_selected") or {}
            out.update({"chosen_alt": al.get("alt"), "bytes_per_interval": al.get("bytes_per_interval"),
                        "device_requested_payload": al.get("device_requested_payload"),
                        "frames": r_.get("frames"), "fps": r_.get("fps_host_after_skip30"), "valid_soi_eoi": r_.get("valid_jpeg"),
                        "pts_gaps_ge_1p5_period": r_.get("pts_gaps_ge_1p5_period"), "err_flag_payloads": r_.get("err_flag_payloads"),
                        "packets_with_error_status": r_.get("packets_with_error_status"), "overflows": r_.get("overflows"),
                        "latency_arrival_minus_pts_ms": r_.get("latency_arrival_minus_pts_ms"),
                        "device_clock_fit": res.get("device_clock_fit"), "backend": (res.get("environment") or {}).get("backend"),
                        "error": res.get("error"), "sof_calibration": bool(res.get("sof_calibration_before"))})
            fj = next(iter(sorted(rd.glob("frames_*.jsonl"))), None)
            if raw and raw.exists() and fj:
                sizes = [f["payload_bytes"] for f in load_jsonl(fj)]
                out["decode"] = strict_frames(iter_concat(raw, sizes), w, h)
            if (rd / "scr_sof_qpc_map.json").exists():
                out["scr_sof_qpc_map"] = load_json(rd / "scr_sof_qpc_map.json")
        elif kind == "mf":
            j = load_json(rd / "mf.json")
            out["mf_cameras"] = [{k: c.get(k) for k in ("spec", "chosen_native_type", "streamed", "failed_stage", "error_hr", "samples",
                                                         "steady_fps", "late_intervals_gt_1p5x", "max_gap_ms", "steady_mean_sample_bytes")}
                                 for c in (j.get("cameras") or [])] if isinstance(j, dict) else None
        elif kind == "group":  # multi-camera hold: sub-runs analysed separately
            pass
        else:
            out["error"] = f"unknown kind {kind}"
    except Exception as e:  # noqa: BLE001
        import traceback
        out["analysis_error"] = f"{type(e).__name__}: {e}"
        out["traceback"] = traceback.format_exc()[-1500:]
    if pipes_files and vid:
        out["pipes"] = pipes_alts(pipes_files, vid, pid)
        out["alt_confirmed_by_pipes"] = confirm(out.get("chosen_alt"), out["pipes"])
    dec = out.get("decode")
    if dec is not None and out.get("frames"):
        out["pct_strict_ok"] = round(100 * dec["strict_ok"] / out["frames"], 2)
    return out


def cmd_runs(a) -> int:
    for g in a.groups:
        gd = Path(g)
        runs = []
        for rd in sorted(p for p in gd.rglob("run.json")):
            r = analyse_run(rd.parent)
            r["path"] = str(rd.parent)
            (rd.parent / "analysis.json").write_text(json.dumps(r, indent=1, default=str))
            runs.append(r)
            line = f'{r["run"]:<34} {r.get("kind") or "":<10} alt={r.get("chosen_alt")} pipes={((r.get("pipes") or {}).get("alts_seen"))} ' \
                   f'fr={r.get("frames")} fps={r.get("fps")} strict%={r.get("pct_strict_ok")} err={r.get("error") or r.get("stream_start_error_name") or r.get("analysis_error")}'
            print(line, flush=True)
        doc = {"test": "phase3_analysis", "group": gd.name, "hostname": socket.gethostname(),
               "utc_analysed": dt.datetime.now(dt.timezone.utc).isoformat(), "command": " ".join(["uv run --script"] + sys.argv), "runs": runs}
        (gd / "analysis.json").write_text(json.dumps(doc, indent=1, default=str))
        print(f"wrote {gd / 'analysis.json'}")
    return 0


def cmd_timing(a) -> int:
    t = timing(Path(a.run), a.hc_match, a.skip)
    s = json.dumps(t, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(s)
    print(s)
    return 0


# ---------------------------------------------------------------- summary
def c930e_baseline(root: Path) -> dict:
    b: dict = {"source_note": "C930e 046d:0843 on inbox WinUSB, phase 2 (same host, same tools)"}
    bw = load_json(root / "phase2_bw_alt" / "summary.json")
    b["libuvc_alt_sweep"] = [{k: r.get(k) for k in ("run", "mode", "alt", "fps_delivered", "frames", "pct_valid_decoded", "camera_skipped_frames",
                                                     "median_over_capacity", "commit_dwMaxPayloadTransferSize")} for r in bw.get("runs", [])] if "runs" in bw else bw
    sj = load_json(root / "phase2_bw_alt_verify" / "strict_jpeg_check_sweep.json")
    b["libuvc_strict_check"] = [{k: r.get(k) for k in ("run", "frames_logged", "jpegs", "marker_ok", "cv_ok")} for r in sj.get("runs", [])] if "runs" in sj else sj
    py = load_json(root / "phase2_python_libusb" / "summary.json")
    b["py_libusb1"] = [{k: r.get(k) for k in ("run", "altsetting", "frames", "fps_from_arrivals", "pillow_full_decode_ok", "iso_packet_errors")} for r in py.get("runs", [])] if "runs" in py else py
    rs = load_json(root / "phase2_rust_uvc_iso" / "phase2_rust_uvc_iso_summary.json")
    b["rust_uvc_iso"] = [{"run": Path(r.get("run", "")).name, **{k: r.get(k) for k in ("backend", "alt", "bytes_per_interval", "frames", "fps", "percent_decoded", "pts_gaps_excluding_first_pair")}}
                         for r in rs.get("uvc_iso_runs", [])] if "uvc_iso_runs" in rs else rs
    pu = []
    for d in sorted((root / "phase2_pyuvc").glob("patched_*")):
        j = load_json(d / "result.json")
        for s in j.get("streams", []) if isinstance(j, dict) else []:
            pu.append({"run": d.name, "bandwidth_factor": s.get("bandwidth_factor"), "frames": s.get("frames"), "fps": s.get("fps_from_arrivals"),
                       "pillow_full_decode_ok": s.get("pillow_full_decode_ok"),
                       "pipes_alts": sorted({m["bAlternateSetting"] for c in (s.get("pipes_snapshot") or []) if str(c.get("idProduct", "")).endswith("0843")
                                             for m in c.get("matched_alt_settings", [])})})
    b["pyuvc_patched"] = pu
    tm = []
    for d in sorted((root / "phase2_libusb_scr_timing" / "raw").glob("run*_cas")):
        if (d / "c930e_libuvc" / "usb_frame_qpc.jsonl").exists():
            t = timing(d / "c930e_libuvc")
            tm.append({"run": d.name, **{k: t.get(k) for k in ("frames_used", "device_sof_counts_per_host_s", "sof_valid", "stc_hz_vs_qpc_via_sof",
                                                                "stc_ppm_vs_nominal_via_sof", "stc_line_residual_us", "pts_step_ticks_median",
                                                                "arrival_minus_pts_via_sof_ms")}})
    b["timing_same_analyzer"] = tm
    return b


def cmd_summary(a) -> int:
    root = Path(a.results_root)
    groups = {}
    for gd in sorted(root.glob("phase3_*")):
        if gd.is_dir() and (gd / "analysis.json").exists():
            groups[gd.name] = load_json(gd / "analysis.json").get("runs", [])
    keep = ("run", "kind", "camera", "mode", "requested", "chosen_alt", "bytes_per_interval", "alt_confirmed_by_pipes", "frames", "fps",
            "pct_strict_ok", "camera_skipped_frames_by_stc", "commit_dwMaxPayloadTransferSize", "stream_start_error_name", "error",
            "exit_code", "timed_out", "timing", "streams", "mf_cameras", "path")
    doc = {"test": "phase3_summary", "platform": "windows", "hostname": socket.gethostname(),
           "utc": dt.datetime.now(dt.timezone.utc).isoformat(), "command": " ".join(["uv run --script"] + sys.argv),
           "cameras": {"c922": "Logitech C922 046d:085c serial B76395EF, xHCI root port 1 (no hub)",
                       "generic": "Jieli 'USB Camera' 4c4a:4a55 (no serial), Genesys 05e3:0610 hub port 3 (shared with the C930e, port 4)",
                       "c930e": "Logitech C930e 046d:0843 - stays on usbvideo in phase 3; baseline below is its phase-2 WinUSB run"},
           "groups": {g: [{k: r.get(k) for k in keep if k in r} for r in rs] for g, rs in groups.items()},
           "c930e_baseline": c930e_baseline(root)}
    for g, rs in groups.items():
        for r in rs:
            for s in r.get("streams") or []:
                if s.get("decode"):
                    s["pct_strict_ok"] = round(100 * s["decode"]["strict_ok"] / s["frames"], 2) if s.get("frames") else None
                    s.pop("decode")
    out = Path(a.out) if a.out else root / "phase3_summary.json"
    out.write_text(json.dumps(doc, indent=1, default=str))
    print(f"wrote {out}")
    return 0


# ---------------------------------------------------------------- selftest
def cmd_selftest(a) -> int:
    root = Path(a.results_root)
    cases = []

    def case(name, ok, got):
        cases.append({"case": name, "pass": bool(ok), "got": got})
        print(f'{name:<44} {"PASS" if ok else "FAIL"}  {json.dumps(got, default=str)[:300]}')

    from PIL import Image
    import io
    im = Image.new("RGB", (64, 48), (90, 120, 150))
    bio = io.BytesIO(); im.save(bio, "JPEG", quality=80); good = bio.getvalue()
    mid = len(good) // 2
    bad = good[:mid] + good[mid + 64:]
    tmp = Path(os.environ.get("TEMP", ".")) / "phase3_selftest"
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "u32.bin").write_bytes(b"".join(len(x).to_bytes(4, "little") + x for x in (good, bad, good)))
    r = strict_frames(iter_u32(tmp / "u32.bin"), 64, 48)
    case("u32_dump_strict_good_bad_good", r["checked"] == 3 and r["strict_ok"] == 2, {k: r[k] for k in ("checked", "strict_ok", "libjpeg_strict_ok", "pillow_ok")})
    (tmp / "cat.mjpeg").write_bytes(good + bad + good)
    r = strict_frames(iter_concat(tmp / "cat.mjpeg", [len(good), len(bad), len(good)]), 64, 48)
    case("concat_dump_strict_good_bad_good", r["checked"] == 3 and r["strict_ok"] == 2, {k: r[k] for k in ("checked", "strict_ok")})
    r = strict_frames(iter([good]), 640, 480)
    case("size_mismatch_fails", r["strict_ok"] == 0 and r["size_ok"] == 0, {k: r[k] for k in ("strict_ok", "size_ok", "dims")})
    trunc = good[:mid] + b"\xff\xd9"
    r = strict_frames(iter([trunc]), 64, 48)
    case("truncated_plus_eoi_fails_strict", r["strict_ok"] == 0, {k: r[k] for k in ("strict_ok", "marker_ok", "libjpeg_strict_ok", "pillow_ok")})
    # real phase-2 pipes snapshot: C930e forced alt 4 at 720p -> pipes must show alt 4 (640 B)
    pf = root / "phase2_bw_alt_verify" / "sweep_pipes" / "1280x720_alt4_pipes.json"
    if pf.exists():
        p = pipes_alts([pf], "046d", "0843")
        case("pipes_c930e_alt4_real", p["alts_seen"] == [4], p["alts_seen"])
        p2 = pipes_alts([pf], "046d", "085c")
        case("pipes_c922_idle_no_iso_alt", p2["alts_seen"] == [] and p2["snapshots"][0]["seen"], p2)
        case("confirm_true_false", confirm(4, p) is True and confirm(5, p) is False and confirm(4, {"snapshots": []}) is None, None)
    # real phase-2 C930e timing data: the analyzer must reproduce flash_libuvc_scr.py's clock numbers (run4_cas:
    # stc_hz_vs_qpc 30001287.8, stc_line_residual std 286.1 us, callback-SOF first median 2.94 ms)
    rd = root / "phase2_libusb_scr_timing" / "raw" / "run4_cas" / "c930e_libuvc"
    if rd.exists():
        t = timing(rd, skip=30)
        ref = load_json(root / "phase2_libusb_scr_timing" / "run4_cas_analysis.json")["cameras"]["c930e_libuvc"]["clock"]
        got = {"stc_hz": t.get("stc_hz_vs_qpc_via_sof"), "ref_stc_hz": ref["stc_hz_vs_qpc"],
               "resid_std_us": (t.get("stc_line_residual_us") or {}).get("std"), "ref_resid_std_us": ref["stc_line_residual_us"]["std"],
               "cb_minus_sof_first_p50_ms": (t["callback_minus_sof_frame_ms"]["first"] or {}).get("p50"),
               "ref_p50": ref["callback_minus_sof_frame_ms"]["first"]["median"], "sof_per_s": t.get("device_sof_counts_per_host_s"),
               "sof_valid": t.get("sof_valid")}
        ok = (abs(got["stc_hz"] - got["ref_stc_hz"]) < 30 and abs(got["resid_std_us"] - got["ref_resid_std_us"]) < 15
              and abs(got["cb_minus_sof_first_p50_ms"] - got["ref_p50"]) < 0.2 and t["sof_valid"])
        case("timing_reproduces_phase2_c930e_run4_cas", ok, got)
        # broken-SOF detector: scale the SOF counter to 884/s (C922-like) -> sof_valid must become False
        rows = load_jsonl(rd / "frames.jsonl")
        t0 = rows[0]["host_first_payload_ns"]
        for rr in rows:
            f = int(round((rr["host_first_payload_ns"] - t0) / 1e6 * 0.8848))
            rr["uvc_scr_sof_first"] = f & 0x7FF
            rr["uvc_scr_sof"] = (f + 4) & 0x7FF
        fake = tmp / "fake_sof884"
        fake.mkdir(exist_ok=True)
        (fake / "frames.jsonl").write_text("\n".join(json.dumps(x) for x in rows))
        (fake / "usb_frame_qpc.jsonl").write_bytes((rd / "usb_frame_qpc.jsonl").read_bytes())
        tf = timing(fake, skip=30)
        case("timing_flags_884_per_s_sof_as_invalid", (not tf["sof_valid"]) and abs(tf["device_sof_counts_per_host_s"] - 884.8) < 2,
             {"sof_per_s": tf["device_sof_counts_per_host_s"], "sof_valid": tf["sof_valid"], "stc_hz_via_host": tf["stc_hz_vs_host_first_payload"]})
    doc = {"test": "phase3_analyze_selftest", "hostname": socket.gethostname(), "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
           "command": " ".join(["uv run --script"] + sys.argv), "cases": cases, "passed": sum(c["pass"] for c in cases), "total": len(cases)}
    out = root / "phase3_analyze_selftest.json"
    out.write_text(json.dumps(doc, indent=1, default=str))
    print(f'passed {doc["passed"]}/{doc["total"]} -> {out}')
    return 0 if doc["passed"] == doc["total"] else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("runs"); p.add_argument("groups", nargs="+"); p.set_defaults(fn=cmd_runs)
    p = sp.add_parser("timing"); p.add_argument("run"); p.add_argument("--hc-match", default="dev_7a60"); p.add_argument("--skip", type=int, default=5)
    p.add_argument("--out"); p.set_defaults(fn=cmd_timing)
    p = sp.add_parser("summary"); p.add_argument("--results-root", required=True); p.add_argument("--out"); p.set_defaults(fn=cmd_summary)
    p = sp.add_parser("selftest"); p.add_argument("--results-root", required=True); p.set_defaults(fn=cmd_selftest)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
