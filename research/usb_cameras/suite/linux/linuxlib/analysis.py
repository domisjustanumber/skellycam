"""Analysis helpers shared by the Linux test modules (run in the runner process, never touch a camera).

JPEG validation uses common.jpegcheck (strict decode via simplejpeg/PyTurboJPEG when importable); image metrics
use common.imgmetrics (Pillow + numpy, declared in run_suite.py's PEP 723 header). Frames are read back from the
raw dump (outside the repo) using the raw_off/raw_len columns of frames.jsonl.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable, Iterator

from common import jpegcheck, results

# descriptor control name (naming/usbdesc.py bmControls bits) -> V4L2 control ids uvcvideo maps it to
DESC_TO_CID: dict[str, list[int]] = {
    "auto_exposure_mode": [0x009A0901], "auto_exposure_priority": [0x009A0903],
    "exposure_time_absolute": [0x009A0902], "focus_absolute": [0x009A090A], "focus_relative": [0x009A090B],
    "focus_auto": [0x009A090C], "iris_absolute": [0x009A0911], "iris_relative": [0x009A0912],
    # uvcvideo maps CT_ZOOM_RELATIVE to V4L2_CID_ZOOM_CONTINUOUS and CT_PANTILT_RELATIVE to V4L2_CID_PAN_SPEED /
    # V4L2_CID_TILT_SPEED (uvc_ctrl.c uvc_ctrl_mappings), not to ZOOM_RELATIVE / PAN_RELATIVE / TILT_RELATIVE
    "zoom_absolute": [0x009A090D], "zoom_relative": [0x009A090F], "pantilt_absolute": [0x009A0908, 0x009A0909],
    "pantilt_relative": [0x009A0920, 0x009A0921], "privacy": [0x009A0910],
    "brightness": [0x00980900], "contrast": [0x00980901], "hue": [0x00980903], "saturation": [0x00980902],
    "sharpness": [0x0098091B], "gamma": [0x00980910], "white_balance_temperature": [0x0098091A],
    "white_balance_component": [0x0098090E, 0x0098090F], "backlight_compensation": [0x0098091C],
    "gain": [0x00980913], "power_line_frequency": [0x00980918], "hue_auto": [0x00980919],
    "white_balance_temperature_auto": [0x0098090C], "white_balance_component_auto": [0x0098090C],
}
#: descriptor bits uvcvideo has no standard V4L2 mapping for (absent from the walk is expected)
DESC_UNMAPPED = {"scanning_mode", "exposure_time_relative", "roll_absolute", "roll_relative", "focus_simple",
                 "window", "region_of_interest", "digital_multiplier", "digital_multiplier_limit",
                 "analog_video_standard", "analog_video_lock_status", "contrast_auto", "reserved15", "reserved16"}


#: L-CTRL-EFFECT experiment -> the descriptor control (bmControls name) it exercises
EXPERIMENT_DESC_CONTROL = {"exposure": "exposure_time_absolute", "gain": "gain",
                           "white_balance": "white_balance_temperature", "focus": "focus_absolute"}


def _range_check(c: dict[str, Any]) -> tuple[bool, str | None]:
    """(consistent, problem) for one QUERY_EXT_CTRL record: min <= default <= max, integer step >= 1."""
    lo, hi, st, d = c.get("min"), c.get("max"), c.get("step"), c.get("default")
    if not all(isinstance(x, int) for x in (lo, hi)):
        return False, "no min/max"
    if hi < lo:
        return False, f"max {hi} < min {lo}"
    if c.get("type") in ("integer", "integer64") and not (isinstance(st, int) and st >= 1):
        return False, f"step {st}"
    if isinstance(d, int) and not lo <= d <= hi:
        return False, f"default {d} outside [{lo}, {hi}]"
    if c.get("type") in ("menu", "integer_menu") and c.get("menu") is not None and not c.get("menu"):
        return False, "menu with no item"
    return True, ("degenerate range (min == max)" if hi == lo and c.get("type") != "boolean" else None)


def ctrl_per_control(walk: list[dict[str, Any]], desc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per descriptor control (CT/PU bmControls name): is it listed by the QUERY_EXT_CTRL walk, and did the camera
    answer a consistent range for it? This is G-CTRL criterion 1 on Linux ("listed with the descriptor's range"):
    UVC descriptors carry no ranges, so the range part is the camera's GET_MIN/MAX/RES/DEF answer (through
    QUERY_EXT_CTRL) being present and self-consistent; a failing query for the control (Kiyo EPIPE/ETIMEDOUT) makes
    it False. Controls without a standard uvcvideo mapping have listed/range_ok None."""
    by_id = {c["id"]: c for c in walk or [] if c.get("id") is not None}
    q_fail: dict[int, str] = {}
    for c in walk or []:
        if c.get("query_errno") and c.get("probe_id"):
            try:
                q_fail[int(c["probe_id"], 16)] = c["query_errno"]
            except (TypeError, ValueError):
                pass
    out: dict[str, dict[str, Any]] = {}
    for unit, names in (("CT", desc.get("ct_controls") or []), ("PU", desc.get("pu_controls") or [])):
        for n in names:
            cids = DESC_TO_CID.get(n)
            if cids is None:
                out[n] = {"unit": unit, "v4l2_ids": None, "listed": None, "range_ok": None,
                          "note": "no standard uvcvideo mapping" if n in DESC_UNMAPPED else "unknown mapping"}
                continue
            recs = [by_id.get(x) for x in cids]
            listed = all(r is not None for r in recs)
            probs, ranges = [], []
            for x, r in zip(cids, recs):
                if r is None:
                    probs.append(f"0x{x:08x} not listed" + (f" (query {q_fail[x]})" if x in q_fail else ""))
                    continue
                ok, why = _range_check(r)
                ranges.append({"id": f"0x{x:08x}", "type": r.get("type"), "min": r.get("min"), "max": r.get("max"),
                               "step": r.get("step"), "default": r.get("default"), "consistent": ok})
                if why:
                    probs.append(f"0x{x:08x}: {why}")
            out[n] = {"unit": unit, "v4l2_ids": [f"0x{x:08x}" for x in cids], "listed": listed,
                      "range_ok": bool(listed and all(r["consistent"] for r in ranges)), "ranges": ranges,
                      "problems": probs or None}
    return out


def ctrl_criterion1(per_control: dict[str, dict[str, Any]] | None, experiment: str,
                    source: str) -> dict[str, Any]:
    """{listed, range_matches_descriptor, source, detail} for one L-CTRL-EFFECT experiment (rating.rate_ctrl
    criterion 1). per_control None = no listing available (both None: not fed, which blocks 'yes')."""
    dn = EXPERIMENT_DESC_CONTROL.get(experiment)
    if per_control is None or dn is None:
        return {"listed": None, "range_matches_descriptor": None, "source": "no listing available",
                "descriptor_control": dn}
    pc = per_control.get(dn)
    if pc is None:
        return {"listed": False, "range_matches_descriptor": None, "source": source, "descriptor_control": dn,
                "detail": "not in the descriptors' bmControls (listed by the driver without descriptor support)"}
    return {"listed": pc.get("listed"), "range_matches_descriptor": pc.get("range_ok"), "source": source,
            "descriptor_control": dn, "detail": pc.get("problems"),
            "range_basis": "camera's GET_MIN/MAX/RES/DEF via QUERY_EXT_CTRL, consistent (descriptors carry no ranges)"}


def read_rows(path: Path | str) -> list[dict[str, Any]]:
    return results.read_jsonl(path)


def iter_frames(rows: list[dict[str, Any]], raw_file: Path | str | None) -> Iterator[tuple[dict, bytes]]:
    """(row, jpeg bytes) for every row that was saved to the raw dump."""
    if not raw_file or not Path(raw_file).exists():
        return
    with open(raw_file, "rb") as f:
        for r in rows:
            if r.get("raw_off") is None:
                continue
            f.seek(int(r["raw_off"]))
            yield r, f.read(int(r["raw_len"]))


def check_frames(rows: list[dict[str, Any]], raw_file: Path | str | None, want_w: int | None, want_h: int | None,
                 decode: bool = True, max_frames: int | None = None,
                 exclude_error_flag: bool = False) -> dict[str, Any]:
    """Strict/lenient JPEG check of every saved frame plus the per-row quick checks of all frames.

    exclude_error_flag: leave buffers flagged V4L2_BUF_FLAG_ERROR out of the valid-JPEG fractions (raw V4L2).
    From 6.14 uvcvideo's nodrop=1 default hands corrupt frames to the app flagged; up to 6.13 it drops them (they
    show only as sequence gaps). An app on the raw API discards flagged buffers, so excluding them keeps the
    G-MJPEG valid fraction comparable across L1 (6.8) and L2/L3 (7.0/7.2); the count is reported separately.
    Wrapper APIs that hide the flag (OpenCV) are checked on everything they deliver."""
    checks = []
    flagged = sum(1 for r in rows if r.get("error"))
    use_rows = [r for r in rows if not r.get("error")] if exclude_error_flag else rows
    for i, (_, data) in enumerate(iter_frames(use_rows, raw_file)):
        if max_frames and i >= max_frames:
            break
        checks.append(jpegcheck.check_jpeg(data, decode=decode))
    s = jpegcheck.summarize_checks(checks, want_w, want_h) if checks else {"n": 0}
    s["decoders"] = jpegcheck.decoders_available()
    s["rows"] = len(rows)
    s["rows_error_flag"] = flagged
    s["error_flagged_excluded_from_fractions"] = bool(exclude_error_flag and flagged)
    s["rows_bad_markers"] = sum(1 for r in rows if not (r.get("soi") and r.get("eoi")))
    s["rows_zero_len"] = sum(1 for r in rows if not r.get("bytes"))
    hdr: dict[str, int] = {}
    for r in rows:
        if r.get("hdr_sha1"):
            hdr[r["hdr_sha1"]] = hdr.get(r["hdr_sha1"], 0) + 1
    s["rows_header_sha1"] = hdr
    s["dominant_header_sha1"] = max(hdr, key=hdr.get) if hdr else None
    s["examples_failed"] = [{k: c.get(k) for k in ("bytes", "soi", "eoi", "marker_issues", "strict_error",
                                                   "extra_bytes_before_eoi")}
                            for c in checks if c.get("strict_ok") is False or not c.get("marker_ok")][:3]
    return s


def fps_from_rows(rows: list[dict[str, Any]], key: str = "host_ns", skip: int = 5) -> float | None:
    t = [r[key] for r in rows[skip:] if isinstance(r.get(key), (int, float))]
    if len(t) < 3 or t[-1] <= t[0]:
        return None
    return (len(t) - 1) / ((t[-1] - t[0]) / 1e9)


def step_windows(rows: list[dict[str, Any]], settle_ms: float = 400.0) -> dict[int, list[dict[str, Any]]]:
    """Group frame rows by control-schedule step, dropping frames within settle_ms after each step change
    (exposure/WB/focus take a few frames to take effect)."""
    out: dict[int, list[dict[str, Any]]] = {}
    step_start: dict[int, int] = {}
    for r in rows:
        s = int(r.get("step") or 0)
        if s not in step_start:
            step_start[s] = r["host_ns"]
        if (r["host_ns"] - step_start[s]) / 1e6 < settle_ms:
            continue
        out.setdefault(s, []).append(r)
    return out


def window_metrics(rows: list[dict[str, Any]], raw_file: Path | str | None, settle_ms: float = 400.0,
                   max_per_step: int = 8, roi=(0.2, 0.2, 0.8, 0.8)) -> dict[int, dict[str, Any]]:
    """Mean luma, R/B ratio and sharpness per schedule step (using up to max_per_step saved frames per step)."""
    try:
        from common import imgmetrics
        avail = all(imgmetrics.available().values())
    except Exception:
        avail = False
    out: dict[int, dict[str, Any]] = {}
    if not avail:
        return {-1: {"error": "Pillow/numpy not importable"}}
    wins = step_windows(rows, settle_ms)
    for s, rs in sorted(wins.items()):
        saved = [r for r in rs if r.get("raw_off") is not None]
        pick = saved[-max_per_step:]
        vals = {"luma": [], "rb": [], "sharp": []}
        for _, data in iter_frames(pick, raw_file):
            try:
                vals["luma"].append(imgmetrics.luma_mean(data, roi))
                vals["rb"].append(imgmetrics.rb_ratio(data, roi))
                vals["sharp"].append(imgmetrics.sharpness(data, roi))
            except Exception as e:  # corrupt frame
                vals.setdefault("errors", []).append(repr(e)[:120])
        out[s] = {"n": len(vals["luma"]), "luma": _mean(vals["luma"]), "rb_ratio": _mean(vals["rb"]),
                  "sharpness": _mean(vals["sharp"]), "luma_sd": _sd(vals["luma"]),
                  "errors": vals.get("errors")}
    return out


def _mean(v: Iterable[float]) -> float | None:
    v = [x for x in v if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return sum(v) / len(v) if v else None


def _sd(v: list[float]) -> float | None:
    v = [x for x in v if x is not None]
    if len(v) < 2:
        return None
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def v4l2_mode_set(formats: list[dict[str, Any]]) -> dict[tuple[str, int, int], dict[str, Any]]:
    """{(fourcc, w, h): {"fps": [..] | None, "continuous": bool}} from camworker 'formats' output."""
    out = {}
    for f in formats or []:
        for s in f.get("sizes") or []:
            if s.get("type") != "discrete":
                out[(f["fourcc"], -1, -1)] = {"fps": None, "continuous": True, "raw": s}
                continue
            ivs = s.get("intervals") or []
            disc = [iv["fps"] for iv in ivs if iv.get("type") == "discrete" and iv.get("fps")]
            out[(f["fourcc"], s["w"], s["h"])] = {"fps": sorted({round(x, 2) for x in disc}, reverse=True),
                                                  "continuous": any(iv.get("type") != "discrete" for iv in ivs)}
    return out


def desc_mode_set(desc: dict[str, Any]) -> dict[tuple[str, int, int], dict[str, Any]]:
    out = {}
    for st in desc.get("streams") or []:
        for m in st.get("modes") or []:
            k = (m["fourcc"], m["w"], m["h"])
            if m.get("interval_type") == "discrete":
                out[k] = {"fps": sorted({round(x, 2) for x in m.get("fps") or []}, reverse=True), "continuous": False}
            else:
                out[k] = {"fps": None, "continuous": True, "fps_min": m.get("fps_min"), "fps_max": m.get("fps_max")}
    return out


def diff_modes(v4l2_modes: dict, desc_modes: dict) -> dict[str, Any]:
    """Missing / extra sizes and frame rates per (fourcc, w, h). Rates compared to 0.05 fps."""
    missing_sizes = sorted(k for k in desc_modes if k not in v4l2_modes)
    extra_sizes = sorted(k for k in v4l2_modes if k not in desc_modes)
    rate_diffs = []
    for k in sorted(set(desc_modes) & set(v4l2_modes)):
        a, b = desc_modes[k].get("fps") or [], v4l2_modes[k].get("fps") or []
        miss = [x for x in a if not any(abs(x - y) < 0.05 for y in b)]
        extra = [y for y in b if not any(abs(x - y) < 0.05 for x in a)]
        if miss or extra or desc_modes[k].get("continuous") != v4l2_modes[k].get("continuous"):
            rate_diffs.append({"mode": "%s %dx%d" % k, "missing_fps": miss, "extra_fps": extra,
                               "continuous_desc": desc_modes[k].get("continuous"),
                               "continuous_v4l2": v4l2_modes[k].get("continuous")})
    n_desc = sum(len(v.get("fps") or [1]) for v in desc_modes.values())
    n_v4l2 = sum(len(v.get("fps") or [1]) for v in v4l2_modes.values())
    return {"missing_sizes": ["%s %dx%d" % k for k in missing_sizes], "extra_sizes": ["%s %dx%d" % k for k in extra_sizes],
            "rate_differences": rate_diffs, "n_modes_descriptors": n_desc, "n_modes_v4l2": n_v4l2,
            "identical": not missing_sizes and not extra_sizes and not rate_diffs}


def mode_list(modes: dict, fourcc: str = "MJPG") -> list[dict[str, Any]]:
    out = []
    for (f, w, h), v in sorted(modes.items(), key=lambda kv: (kv[0][1] * kv[0][2], kv[0])):
        if f != fourcc or w < 0:
            continue
        for fps in v.get("fps") or []:
            out.append({"fourcc": f, "w": w, "h": h, "fps": fps})
    return out
