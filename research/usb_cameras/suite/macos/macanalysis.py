"""Pure analysis used by the macOS test modules (stdlib + suite/common; no PyObjC, no devices). Unit-tested on
Windows/Linux with synthetic frames.jsonl rows (unittests/test_macanalysis.py)."""
from __future__ import annotations

import statistics
from typing import Any, Iterable

import suitectx  # noqa: F401  (puts suite/common on sys.path)
from common import tsanalysis

JPEG_SUBTYPES = suitectx.JPEG_SUBTYPES


# ------------------------------------------------------------------------------------------------ MJPEG cells
def eval_cell(summary: dict | None, want: dict) -> dict:
    """One capture cell (format x variant) -> the facts rate_mjpeg needs plus what the samples were.
    want: {w, h, fps, subtype}."""
    s = summary or {}
    st = s.get("stream") or {}
    jp = s.get("jpeg") or {}
    frames = s.get("frames") or 0
    kinds = s.get("sample_kinds") or {}
    is_jpeg = s.get("is_jpeg")
    delivered = "jpeg_block" if is_jpeg else ("pixel_buffer" if kinds.get("image") else
                                             ("block_non_jpeg" if kinds.get("block") else "nothing"))
    return {
        "frames": frames, "negotiated": bool(frames) and st.get("active_format_matches") is not False,
        "active_format_matches": st.get("active_format_matches"),
        "video_settings_accepted": st.get("video_settings_accepted"), "video_settings_error": st.get("video_settings_error"),
        "delivered": delivered, "sample_subtypes": s.get("sample_subtypes"), "cv_pixel_formats": s.get("cv_pixel_formats"),
        "is_jpeg": is_jpeg, "strict_valid_fraction": jp.get("strict_valid_fraction"),
        "lenient_valid_fraction": jp.get("lenient_valid_fraction"),
        "sof_matches": (jp.get("sof_match_fraction") == 1.0) if jp.get("sof_match_fraction") is not None else None,
        "fps_measured": s.get("fps_measured"), "fps_expected": want.get("fps"),
        "header_sha1": (jp.get("header_sha1_set") or [None])[0] if jp.get("n_header_sha1") == 1 else
        (jp.get("header_sha1_set") or [None])[0],
        "n_header_sha1": jp.get("n_header_sha1"), "first_frame_ms": s.get("first_frame_ms"),
        "cpu_pct_one_core": (s.get("cpu") or {}).get("pct_one_core"),
        "runtime_errors": s.get("runtime_errors"), "available_codec_types": st.get("available_codec_types"),
        "available_cv_formats": st.get("available_cv_formats"),
    }


def mode_row(mode: dict, cells: dict[str, dict], known_quirk: str | None = None) -> dict:
    """Combine the variants of one format into one rate_mjpeg mode row. The 'best' variant is the first that
    delivered JPEG blocks; header SHA-1s of every JPEG-delivering variant are compared ('APIs' = variants)."""
    jpeg_cells = {v: c for v, c in cells.items() if c.get("is_jpeg")}
    best_v, best = (next(iter(jpeg_cells.items())) if jpeg_cells else
                    (next(iter(cells.items())) if cells else (None, {})))
    return {"mode": mode.get("mode_text"), "format_index": mode.get("format_index"), "best_variant": best_v,
            "negotiated": bool(best.get("negotiated")), "frames": best.get("frames"),
            "strict_valid_fraction": best.get("strict_valid_fraction"),
            "lenient_valid_fraction": best.get("lenient_valid_fraction"), "known_quirk": known_quirk,
            "sof_matches": best.get("sof_matches"), "fps_measured": best.get("fps_measured"),
            "fps_expected": mode.get("fps"),
            "header_sha1_by_api": {v: c.get("header_sha1") for v, c in jpeg_cells.items() if c.get("header_sha1")} or None,
            "is_jpeg": bool(jpeg_cells) if cells else None,
            "delivered_by_variant": {v: c.get("delivered") for v, c in cells.items()}}


# ------------------------------------------------------------------------------------------------ control effects
def window_values(rows: list[dict], t0_ns: int, t1_ns: int, key: str) -> list[float]:
    out = []
    for r in rows:
        t = r.get("host_ns")
        m = r.get("metrics") or {}
        if t is None or not (t0_ns <= t < t1_ns):
            continue
        v = m.get(key)
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


def step_medians(rows: list[dict], events: list[dict], name: str, key: str, settle_ms: float = 600.0,
                 end_ns: int | None = None) -> list[dict]:
    """For every schedule event that set ``name``: median of metric ``key`` from settle after the event to the next
    event. Returns [{value, n, median, readback, rc_name}]."""
    evs = sorted([e for e in events if e.get("host_ns_after")], key=lambda e: e["host_ns_after"])
    last_t = max((r.get("host_ns") or 0 for r in rows), default=0)
    out = []
    for i, e in enumerate(evs):
        if e.get("name") != name or e.get("kind") != "ep0":
            continue
        t0 = e["host_ns_after"] + int(settle_ms * 1e6)
        t1 = evs[i + 1]["host_ns_before"] if i + 1 < len(evs) else (end_ns or last_t + 1)
        vals = window_values(rows, t0, t1, key)
        res = e.get("result") or {}
        out.append({"value": int(e["value"], 0) if isinstance(e.get("value"), str) else e.get("value"),
                    "n": len(vals), "median": statistics.median(vals) if vals else None,
                    "readback": res.get("readback"), "readback_matches": res.get("readback_matches"),
                    "rc_name": res.get("rc_name"), "set_ok": res.get("ok")})
    return out


def effect_verdict(steps: list[dict], kind: str) -> dict:
    """Does the image follow the control? exposure/gain: luma rises with the value by >15% / >10%;
    white_balance: R/B moves monotonically by >5%; focus: sharpness max/min > 1.2."""
    pts = [(s["value"], s["median"]) for s in steps if s.get("median") is not None and s.get("value") is not None]
    pts.sort()
    if len(pts) < 2:
        return {"effect_ok": None, "reason": "fewer than two measured steps", "points": pts}
    vals = [m for _, m in pts]
    if kind in ("exposure", "gain"):
        rising = all(b > a for a, b in zip(vals, vals[1:]))
        rel = (vals[-1] - vals[0]) / max(abs(vals[0]), 1.0)
        thr = 0.15 if kind == "exposure" else 0.10
        return {"effect_ok": bool(rising and rel > thr), "relative_change": round(rel, 4), "monotonic": rising,
                "threshold": thr, "points": pts}
    if kind == "white_balance":
        up = all(b > a for a, b in zip(vals, vals[1:]))
        down = all(b < a for a, b in zip(vals, vals[1:]))
        rel = abs(vals[-1] - vals[0]) / max(abs(vals[0]), 1e-6)
        return {"effect_ok": bool((up or down) and rel > 0.05), "relative_change": round(rel, 4),
                "direction": "up" if up else ("down" if down else "mixed"), "points": pts}
    if kind == "focus":
        lo, hi = min(vals), max(vals)
        ratio = hi / lo if lo > 0 else None
        return {"effect_ok": bool(ratio and ratio > 1.2), "max_min_ratio": round(ratio, 3) if ratio else None,
                "points": pts}
    return {"effect_ok": None, "reason": f"no effect rule for {kind}", "points": pts}


def build_effect_schedule(ranges: dict[str, dict], initial: dict[str, int], start_ms: float = 1000.0,
                          step_ms: float = 1500.0) -> tuple[str, list[tuple[str, str]], float]:
    """The ep0 SET_CUR schedule for CTRL-EFFECT from GET_MIN/MAX/RES/DEF results.
    ranges: {control name: {min,max,res,def,modes_supported?}}; initial: GET_CUR values before the test.
    Returns (schedule text for mac_avf --schedule, [(group, control)], total ms)."""
    from uvc_ctrl import exposure_values, pick_values  # helpers dir on sys.path via suitectx
    t = start_ms
    parts: list[str] = []
    groups: list[tuple[str, str]] = []

    def add(name: str, value: int, dt: float = step_ms):
        nonlocal t
        parts.append(f"{int(t)}:ep0:{name}={int(value)}")
        t += dt

    ae = ranges.get("auto_exposure_mode")
    if ae is not None and "exposure_time_absolute" in ranges and "manual" in (ae.get("modes_supported") or ["manual"]):
        add("auto_exposure_mode", 1, 800)
        for v in exposure_values(ranges["exposure_time_absolute"]):
            add("exposure_time_absolute", v)
        groups.append(("exposure", "exposure_time_absolute"))
        if "gain" in ranges:
            for v in pick_values(ranges["gain"], 3):
                add("gain", v)
            groups.append(("gain", "gain"))
        if initial.get("gain") is not None and "gain" in ranges:
            add("gain", initial["gain"], 300)
        if initial.get("exposure_time_absolute") is not None:
            add("exposure_time_absolute", initial["exposure_time_absolute"], 300)
        add("auto_exposure_mode", initial.get("auto_exposure_mode", ae.get("def") or 8), 800)
    if "white_balance_temperature" in ranges:
        if "white_balance_temperature_auto" in ranges:
            add("white_balance_temperature_auto", 0, 800)
        for v in pick_values(ranges["white_balance_temperature"], 3):
            add("white_balance_temperature", v)
        groups.append(("white_balance", "white_balance_temperature"))
        if "white_balance_temperature_auto" in ranges:
            add("white_balance_temperature_auto", initial.get("white_balance_temperature_auto", 1), 800)
    if "focus_absolute" in ranges:
        if "focus_auto" in ranges:
            add("focus_auto", 0, 800)
        for v in pick_values(ranges["focus_absolute"], 3):
            add("focus_absolute", v, step_ms + 500)
        groups.append(("focus", "focus_absolute"))
        if "focus_auto" in ranges:
            add("focus_auto", initial.get("focus_auto", 1), 800)
    return ";".join(parts), groups, t


# ------------------------------------------------------------------------------------------------ timestamps
def ts_analysis(rows: list[dict], fps: float | None, clocks: dict | None = None) -> dict:
    """Everything M-TS reports from one capture's frames.jsonl rows."""
    rows = [r for r in rows if r.get("host_ns")]
    n = len(rows)
    out: dict[str, Any] = {"n": n}
    if n < 5:
        out["error"] = "too few frames"
        return out
    period = 1e9 / fps if fps else None
    fields = {k: sum(1 for r in rows if r.get(k) is not None) / n
              for k in ("pts_ns", "pts_host_ns", "dur_ns", "cmio_seq", "mach_ns", "attachments")}
    out["field_presence"] = fields
    arrival = [float(r["host_ns"]) for r in rows]
    pts = [float(r["pts_host_ns"] if r.get("pts_host_ns") is not None else r["pts_ns"]) for r in rows
           if (r.get("pts_host_ns") if r.get("pts_host_ns") is not None else r.get("pts_ns")) is not None]
    out["arrival_grid"] = tsanalysis.grid_analysis(arrival, nominal_period_ns=period)
    if len(pts) >= 5:
        out["pts_grid"] = tsanalysis.grid_analysis(pts, nominal_period_ns=period)
        ivals = [b - a for a, b in zip(pts, pts[1:])]
        out["pts_interval_ms"] = tsanalysis.stats(ivals, 1e-6)
        out["pts_monotonic"] = all(i > 0 for i in ivals)
        lat = [float(r["host_ns"]) - float(r.get("pts_host_ns") if r.get("pts_host_ns") is not None else r["pts_ns"])
               for r in rows if (r.get("pts_host_ns") if r.get("pts_host_ns") is not None else r.get("pts_ns")) is not None]
        out["arrival_minus_pts_ms"] = tsanalysis.stats(lat, 1e-6)
        out["pts_fit_whole"] = _strip(tsanalysis.fit_frame_index(pts, causal=False, nominal_period_ns=period))
        if period:
            out["pts_drops"] = tsanalysis.detect_drops(pts, period=period)
    out["arrival_fit_whole"] = _strip(tsanalysis.fit_frame_index(arrival, causal=False, nominal_period_ns=period))
    out["arrival_fit_causal"] = _strip(tsanalysis.fit_frame_index(arrival, causal=True, nominal_period_ns=period))
    seq = [r["cmio_seq"] for r in rows if r.get("cmio_seq") is not None]
    if len(seq) >= 5 and len(set(seq)) > 1:
        out["cmio_seq_drops"] = tsanalysis.detect_drops(seq)
    elif seq:
        out["cmio_seq_note"] = "sequence number present but constant (not usable for drops)"
    c = clocks or {}
    rate = c.get("port_rate_vs_host")
    out["clocks"] = {k: c.get(k) for k in ("sync_api", "sync_is_host_clock", "port_clock_is_host_clock",
                                           "port_rate_vs_host", "port_minus_host_ns_start", "port_minus_host_ns_end")}
    out["port_clock_ppm_vs_host"] = round((rate - 1.0) * 1e6, 3) if isinstance(rate, (int, float)) else None
    pts_grid = (out.get("pts_grid") or {})
    pi = out.get("pts_interval_ms") or {}
    out["pts_self_consistent"] = bool(out.get("pts_monotonic") and pi.get("std") is not None and pi["std"] < 0.2
                                      and not (pts_grid.get("quantized") and (pts_grid.get("step_ms") or 0) >= 4.0))
    out["drops_detectable"] = bool(out.get("cmio_seq_drops") is not None or (out.get("pts_drops") is not None
                                                                              and out.get("pts_self_consistent")))
    return out


def _strip(fit: dict) -> dict:
    return {k: v for k, v in (fit or {}).items() if k not in ("slots", "fitted_ns", "residuals_ns")}


# ------------------------------------------------------------------------------------------------ multi
def refusal_signal(summary: dict | None, nominal_fps: float | None, timed_out: bool = False) -> dict:
    """The three possible macOS bandwidth signals (macos.md 2.5 item 6): an error, a silent zero-frame session,
    or reduced fps. Returns {refused, signal, code, frames, fps}."""
    s = summary or {}
    frames = s.get("frames") or 0
    errs = s.get("runtime_errors") or []
    code = None
    for e in errs:
        err = e.get("error") or {}
        if err.get("iokit_codes"):
            code = err["iokit_codes"][0]
            break
        if err.get("code") is not None:
            code = err["code"]
    fps = s.get("fps_measured")
    if timed_out or s.get("timed_out"):
        return {"refused": True, "signal": "hang", "code": "timeout", "frames": frames, "fps": fps}
    if errs:
        return {"refused": True, "signal": "runtime_error", "code": code, "frames": frames, "fps": fps}
    # the session never started (deviceInputWithDevice / lockForConfiguration / canAddInput failed): keep its
    # NSError code (AVError, or an IOKit code underneath) instead of calling it a silent zero-frame session
    err = s.get("error")
    if frames == 0 and s.get("stage_failed") and s.get("stage_failed") != "first_frame" and err:
        ecode = None
        cands = [err] if isinstance(err, dict) else []
        if isinstance(err, dict):
            cands += [v for v in err.values() if isinstance(v, dict)]
        for e in cands:
            if e.get("iokit_codes"):
                ecode = e["iokit_codes"][0]
                break
            if e.get("code") is not None:
                ecode = e["code"]
                break
        return {"refused": True, "signal": "open_error", "code": ecode if ecode is not None else str(err)[:200],
                "frames": 0, "fps": None, "stage": s.get("stage_failed")}
    if frames == 0:
        return {"refused": True, "signal": "zero_frames", "code": None, "frames": 0, "fps": None}
    if nominal_fps and fps and fps < 0.8 * nominal_fps:
        return {"refused": True, "signal": "reduced_fps", "code": None, "frames": frames, "fps": fps}
    return {"refused": False, "signal": None, "code": None, "frames": frames, "fps": fps}


def ports_in_other_domains(snapshot: dict, suggestions: Iterable[dict], conflict_domain: str) -> bool | None:
    groups = list(suggestions or [])
    if not groups:
        return None
    return all(p.get("domain_key") != conflict_domain for g in groups for p in g.get("ports") or [])
