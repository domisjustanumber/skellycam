"""W-PYMF: can the Windows capture backend be native Python? pymf (comtypes + ctypes, no compiled extension) vs the
C++ reference probe wincam.exe, per camera (Dom's build-language decision, docs/capture_stack_options_plan.md 8).

Per camera, the Kiyo included (every command under camlock through ``ctx.camcmd``, each with a child timeout and
pymf's / wincam's own bounded calls inside):

| Part | pymf | wincam | Compared |
| list | ``pymf list`` | ``wincam list`` | MF symlink and friendly name present in both (opens no camera; no lock) |
| formats | ``pymf formats`` | ``wincam formats --api mf`` | every native type (stream, index, subtype, size, rate, flags, range, sample size) |
| controls | ``pymf controls --read-only`` | ``wincam controls --api mf --read-only`` | per control: supported, via, range, default, caps, flags, value (an auto control's value may drift between reads: recorded, not a difference), KS range |
| set round trip | ``pymf controls --set exposure,focus,gain,white_balance --restore`` | ``wincam controls --read-only`` after | each set read back, restore read back, modes as found afterwards |
| capture | ``pymf capture`` MJPG 720p30 | ``wincam capture`` same mode | header SHA-1, valid-JPEG rate, fps, CPU % of one core, first-frame latency, tier-0 per-frame timing (arrival delay off the MF sample-time grid: p99 and std; frames lost in the sample-time slots) |
| cycles | ``pymf cycle`` (--pymf-cycles, 60) | ``wincam cycle`` same count | success rate, first-frame p50, hangs; pymf rated with rating.rate_reliability |

Mode scope (Dom 2026-11-08): only modes with exactly 720 lines at >= 30 fps stream (MJPG 1280x720@30, else the
in-scope 720-line MJPEG mode nearest to it). A camera without one gets its streaming parts rated 'untested
(scope)'. The listing parts (formats, controls) always run.

Tier 0 only (Dom 2026-11-09): UVC payload metadata (PTS/SCR) is not compared or rated. pymf may still parse it and
wincam may still emit it in frames.jsonl; this test reads neither.

Verdicts: ``pymf_equivalence|<camera>|pymf`` per camera and ``pymf_equivalence`` overall (yes = every measured
criterion met; partial = some differ or a part is untested; no = pymf could not open / capture / list where wincam
could; a pymf hang counts against pymf only when wincam's 1-frame probe right after it streams, otherwise the part
is 'untested (device fault)'). What a 'yes' does NOT cover (``NOT_COVERED``, in every verdict's evidence): several
cameras in one Python process, 60 fps modes, long runs, control sets on a STREAMING source (pymf capture has no
``--schedule`` / ``--controls-before`` yet; the C930e needs a set >= 1 s after the first frame), and in-use-by-other
detection (IMFSensorActivityMonitor, not ported). Until pymf streams with a control schedule, the overall
``pymf_equivalence`` is capped at 'partial' (``STREAMING_SET_CAP``). And ``reliability|<camera>|pymf_inproc``
(rating.rate_reliability over the pymf cycles; >= 381 failure-free cycles are needed for a ">= 99%" claim, so 60
cycles only bound it).

Offline re-analysis of a finished run (no camera opened):
    python suite/windows/tests/w_pymf.py --reanalyze <run_dir> [--out <file>]
Standalone (opens cameras; camlock): python suite/windows/tests/w_pymf.py [--quick] [--pymf-cycles N]
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
import w_cyc  # noqa: E402
from common import cycstats, modescope, rating, results, tsanalysis as tsa  # noqa: E402

TEST = "W-PYMF"
PYMF_CLI = WIN / "pymf" / "cli.py"
TIMEOUT_MS = 5000
UV_SLACK_S = 30.0                # uv start-up (environment resolve) inside the child timeout
DEFAULT_CYCLES = 60
QUICK_CYCLES = 6
#: equivalence tolerances (documented in the criteria texts)
FPS_TOL = 0.02
LAT_ABS_MS = 150.0
LAT_REL = 0.30
CPU_ABS_PP = 5.0
CPU_REL = 2.0
VALID_MIN = 0.99
SUCCESS_TOL = 0.02
CYC_FPS_TOL = 0.10          # per-cycle delivered rate p50: pymf >= wincam's x 0.9 (10-frame cycles are noisy)
#: tier-0 per-frame timing tolerances (frames.jsonl qpc_ns = callback-entry arrival, sample_time_100ns = MF sample
#: time): pymf's arrival delay off the sample-time grid (p99 and std, see timing_stats) may exceed wincam's by at
#: most max(TIMING_ABS_MS, TIMING_REL x wincam's); pymf may not lose more frames (sample-time slots) than wincam + 1.
#: Gerald's stored wincam captures (W-TS 2026-11-06, 5 s windows): p99 0.4-1.0 ms, std 0.13-0.37 ms in every
#: window; a 3 ms delay added to every 10th frame gives p99 3.2-3.9 ms
TIMING_ABS_MS = 2.0
TIMING_REL = 0.5
SKIP_FRAC = 0.15                 # start-up frames left out of the timing statistics (as capkit.fps_from_rows)
SET_CONTROLS = ("exposure", "focus", "gain", "white_balance")
CONTROL_FIELDS = ("supported", "via", "min", "max", "step", "default", "caps_flags", "flags", "value2", "get_ok")

INFO = {"id": TEST, "module": "tests.w_pymf", "goal": "pymf_equivalence", "opens_cameras": True,
        "tools": ["pymf/cli.py (uv, comtypes)", "native/build/wincam.exe"],
        "flags": {"--pymf-cycles": f"open/close cycles per camera and tool (default {DEFAULT_CYCLES}, quick "
                                   f"{QUICK_CYCLES}; env SKELLYCAM_PYMF_CYCLES)",
                  "--pymf-seconds": "capture length per tool (default 5 s, quick 2 s; env SKELLYCAM_PYMF_SECONDS)"},
        "description": "pure-Python Media Foundation probe vs wincam: list, formats, controls, set round trip, "
                       "720p30 MJPEG capture, open/close cycles"}


# ============================================================================================================ knobs
def _env_num(name: str) -> float | None:
    try:
        v = os.environ.get(name)
        return float(v) if v else None
    except ValueError:
        return None


def n_cycles(ctx) -> int:
    v = getattr(ctx.args, "pymf_cycles", None) or _env_num("SKELLYCAM_PYMF_CYCLES")
    return int(v) if v else (QUICK_CYCLES if ck.quick(ctx) else DEFAULT_CYCLES)


def capture_seconds(ctx) -> float:
    v = getattr(ctx.args, "pymf_seconds", None) or _env_num("SKELLYCAM_PYMF_SECONDS")
    return float(v) if v else (2.0 if ck.quick(ctx) else 5.0)


def estimate_s(ctx) -> float:
    """Per camera: 2 formats + 2 controls + set + verify (~6 x 4 s incl. uv start-up), 2 captures, and 2 x N cycles
    at ~1.6 s (Kiyo ~2.6 s, measured close ~1.2 s + first frame ~1 s on 2026-11-06)."""
    n, sec = n_cycles(ctx), capture_seconds(ctx)
    total = 0.0
    for c in ctx.cameras:
        per_cycle = 2.6 if c.get("is_kiyo") else 1.6
        total += 6 * 4.0 + 2 * (sec + 6.0) + 2 * n * per_cycle + 10
    return total + 15


# ============================================================================================================ commands
def pymf_argv(ctx, *args: Any) -> list[str]:
    return ck.helper_argv(ctx, PYMF_CLI, *args)


def _json(r: dict) -> dict | None:
    return ck.parse_json(r)


def _summary_file(out_dir: Path, obj: dict | None) -> dict | None:
    if obj is not None:
        return obj
    p = Path(out_dir) / "summary.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except ValueError:
        return None


def run_list(ctx) -> dict:
    """Both lists (opens no camera: property bags only; no camera lock, as discovery's wincam list)."""
    out = {}
    for tool, argv in (("wincam", ck.wincam_argv(ctx, "list")), ("pymf", pymf_argv(ctx, "list"))):
        r = ctx.run(argv, 60 + (UV_SLACK_S if tool == "pymf" else 0))
        out[tool] = {"doc": _json(r), "run": ck.run_brief(r)}
    return out


def mf_devices(doc: dict | None) -> list[dict]:
    return list(((doc or {}).get("mf") or {}).get("devices") or [])


def compare_lists(wdoc: dict | None, pdoc: dict | None, cams: list[dict]) -> dict:
    """MF device lists: per camera, symlink present in both and the same friendly name; plus the whole-set diff."""
    w = {d.get("symlink", "").lower(): d for d in mf_devices(wdoc)}
    p = {d.get("symlink", "").lower(): d for d in mf_devices(pdoc)}
    per = {}
    for c in cams:
        k = str(c.get("mf_symlink") or "").lower()
        wd, pd = w.get(k), p.get(k)
        per[c["key"]] = {"in_wincam": wd is not None, "in_pymf": pd is not None,
                         "name_equal": (wd or {}).get("friendly_name") == (pd or {}).get("friendly_name")
                         if wd and pd else None,
                         "order_equal": (wd or {}).get("index") == (pd or {}).get("index") if wd and pd else None}
    return {"wincam_n": len(w), "pymf_n": len(p), "only_wincam": sorted(set(w) - set(p)),
            "only_pymf": sorted(set(p) - set(w)), "sets_equal": set(w) == set(p) and bool(w),
            "order_equal": [d.get("symlink", "").lower() for d in mf_devices(wdoc)] ==
            [d.get("symlink", "").lower() for d in mf_devices(pdoc)],
            "per_camera": per, "wincam_ok": wdoc is not None, "pymf_ok": pdoc is not None}


# ------------------------------------------------------------------------------------------------- formats
TYPE_FIELDS = ("stream_index", "type_index", "subtype", "subtype_guid", "width", "height", "fps_num", "fps_den",
               "frame_rate_range_min", "frame_rate_range_max", "sample_size", "major_type")


def native_type_rows(doc: dict | None) -> list[tuple]:
    rows = []
    for s in (doc or {}).get("reader_streams") or []:
        for t in s.get("types") or []:
            rows.append(tuple(json.dumps(t.get(k)) for k in TYPE_FIELDS) + (json.dumps(sorted(t.get("flags") or [])),))
    return rows


def _row_text(r: tuple) -> str:
    v = [json.loads(x) for x in r]
    return f"s{v[0]}#{v[1]} {v[2]} {v[4]}x{v[5]}@{v[6]}/{v[7]} flags={v[-1]}"


def compare_formats(wdoc: dict | None, pdoc: dict | None) -> dict:
    """Native types equal, in order (type indices are what capture code selects by)."""
    if wdoc is None or pdoc is None:
        return {"compared": False, "equal": None, "wincam_ok": wdoc is not None, "pymf_ok": pdoc is not None}
    a, b = native_type_rows(wdoc), native_type_rows(pdoc)
    sa, sb = set(a), set(b)
    streams_w = [(s.get("stream_index"), s.get("stream_identifier"), s.get("major_type"), s.get("handler_type_count"))
                 for s in wdoc.get("streams") or []]
    streams_p = [(s.get("stream_index"), s.get("stream_identifier"), s.get("major_type"), s.get("handler_type_count"))
                 for s in pdoc.get("streams") or []]
    attr_diffs = []
    for sw, sp in zip(wdoc.get("streams") or [], pdoc.get("streams") or []):
        aw, ap = sw.get("attributes") or {}, sp.get("attributes") or {}
        for k in sorted(set(aw) | set(ap)):
            if json.dumps(aw.get(k), sort_keys=True) != json.dumps(ap.get(k), sort_keys=True):
                attr_diffs.append({"stream": sw.get("stream_index"), "attribute": k, "wincam": aw.get(k),
                                   "pymf": ap.get(k)})
    synth = sum(1 for r in b if "synthesized" in r[-1])
    return {"compared": True, "equal": a == b and bool(a), "same_set": sa == sb, "order_equal": a == b,
            "n_wincam": len(a), "n_pymf": len(b), "pymf_synthesized_flagged": synth,
            "only_wincam": [_row_text(r) for r in a if r not in sb][:20],
            "only_pymf": [_row_text(r) for r in b if r not in sa][:20],
            "streams_equal": streams_w == streams_p, "stream_attribute_diffs": attr_diffs[:20],
            "stream_started": {"wincam": wdoc.get("stream_started"), "pymf": pdoc.get("stream_started")}}


# ------------------------------------------------------------------------------------------------- controls
def control_map(doc: dict | None) -> dict[str, dict]:
    return {c.get("key") or c.get("name"): c for c in (doc or {}).get("controls") or [] if isinstance(c, dict)}


def compare_controls(wdoc: dict | None, pdoc: dict | None) -> dict:
    """Per control: CONTROL_FIELDS and the KS range equal; ``value`` equal unless a side is in auto mode (an auto
    control's value is the device's current choice and may change between the two reads: auto_drift)."""
    if wdoc is None or pdoc is None:
        return {"compared": False, "equal": None, "wincam_ok": wdoc is not None, "pymf_ok": pdoc is not None}
    w, p = control_map(wdoc), control_map(pdoc)
    diffs, drift, n = [], [], 0
    for k in sorted(set(w) | set(p)):
        cw, cp = w.get(k), p.get(k)
        if cw is None or cp is None:
            diffs.append({"key": k, "field": "listed", "wincam": cw is not None, "pymf": cp is not None})
            continue
        if not (cw.get("supported") or cp.get("supported")):
            continue
        n += 1
        for f in CONTROL_FIELDS:
            if cw.get(f) != cp.get(f):
                diffs.append({"key": k, "field": f, "wincam": cw.get(f), "pymf": cp.get(f)})
        kw, kp = cw.get("ks_basicsupport") or {}, cp.get("ks_basicsupport") or {}
        for f in ("min", "max", "step", "default"):
            if kw.get(f) != kp.get(f):
                diffs.append({"key": k, "field": f"ks_basicsupport.{f}", "wincam": kw.get(f), "pymf": kp.get(f)})
        if cw.get("value") != cp.get("value"):
            auto = bool((cw.get("flags") or 0) & 1 or (cp.get("flags") or 0) & 1)
            (drift if auto else diffs).append({"key": k, "field": "value", "wincam": cw.get("value"),
                                               "pymf": cp.get("value"), **({"auto_mode": True} if auto else {})})
    return {"compared": True, "equal": not diffs and n > 0, "n_supported_compared": n, "diffs": diffs[:40],
            "auto_drift": drift, "supported_count": {"wincam": wdoc.get("supported_count"),
                                                     "pymf": pdoc.get("supported_count")},
            "device_not_answering": {"wincam": wdoc.get("device_not_answering"),
                                     "pymf": pdoc.get("device_not_answering")},
            "interfaces": {"wincam": wdoc.get("interfaces"), "pymf": pdoc.get("interfaces")}}


def pick_set_values(wdoc: dict | None) -> dict[str, int]:
    """A valid manual value != the current one for each of exposure / focus / gain / white balance that supports
    manual mode: the default, else default +- one step (within the range)."""
    out = {}
    for name in SET_CONTROLS:
        c = next((x for x in (wdoc or {}).get("controls") or [] if x.get("name") == name), None)
        if not c or not c.get("supported") or not ((c.get("caps_flags") or 0) & 2):
            continue
        mn, mx, st, df, cur = c.get("min"), c.get("max"), c.get("step") or 1, c.get("default"), c.get("value")
        if None in (mn, mx, df):
            continue
        v = df
        if v == cur:
            v = df + st if df + st <= mx else df - st
        if mn <= v <= mx and v != cur:
            out[name] = int(v)
    return out


def check_roundtrip(set_doc: dict | None, before: dict | None, after: dict | None) -> dict:
    """pymf sets read back as set, restores read back as restored, and the modes (auto/manual flags) and manual
    values afterwards equal those before (read by wincam)."""
    if set_doc is None:
        return {"ran": False, "ok": None}
    sets = set_doc.get("sets") or []
    rest = set_doc.get("restore") or []
    rest_ok = [bool(r.get("readback_flags") == r.get("restore_flags") and
                    ((r.get("restore_flags") or 0) & 1 or r.get("readback_value") == r.get("restore_value")))
               for r in rest if not r.get("timed_out")]
    bw, aw = control_map(before), control_map(after)
    modes = []
    for s in sets:
        k = s.get("control")
        b, a = bw.get(k) or {}, aw.get(k) or {}
        same_mode = b.get("flags") == a.get("flags")
        same_val = True if (b.get("flags") or 0) & 1 else b.get("value") == a.get("value")
        modes.append({"control": k, "before_flags": b.get("flags"), "after_flags": a.get("flags"),
                      "before_value": b.get("value"), "after_value": a.get("value"), "as_found": same_mode and same_val})
    ok = bool(sets) and all(s.get("matches") for s in sets) and len(rest_ok) == len(sets) and all(rest_ok) and \
        all(m["as_found"] for m in modes) and set_doc.get("exit_code") == 0
    return {"ran": True, "ok": ok, "sets": [{k: s.get(k) for k in ("control", "requested", "via", "before_value",
                                                                  "before_flags", "set_value", "hr_set_name",
                                                                  "readback_value", "readback_flags", "matches",
                                                                  "timed_out")} for s in sets],
            "restore_ok": rest_ok, "as_found_after": modes, "exit_code": set_doc.get("exit_code"),
            "error": set_doc.get("error")}


# ------------------------------------------------------------------------------------------------- capture
def _pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    v = sorted(vals)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))]


def grid_offsets(lat_ms: list[float], grid_ms: float | None) -> list[float]:
    """Each arrival's offset (ms) from the sample-time grid point it belongs to. Arrival minus MF sample time is
    multimodal on Windows' 16 ms host grid (sub-ms or ~16 ms, with shares that change from run to run: Gerald C922
    58/42, C930e 80/20), so a spread over all frames measures the mode shares, not the delivery delay. Folding the
    values onto the grid (around their circular mean) leaves the delay a GIL wait / comtypes dispatch would add. A
    delay close to a whole grid step folds back to ~0 (a limitation; such delays show in the frame loss instead).
    Without a grid (fine sample times) the offsets are taken from the median."""
    if not lat_ms:
        return []
    if not grid_ms:
        med = _pct(lat_ms, 0.5)
        return [x - med for x in lat_ms]
    ang = [2.0 * math.pi * (x % grid_ms) / grid_ms for x in lat_ms]
    c = (math.atan2(sum(map(math.sin, ang)), sum(map(math.cos, ang))) % (2.0 * math.pi)) * grid_ms / (2.0 * math.pi)
    return [((x - c + grid_ms / 2.0) % grid_ms) - grid_ms / 2.0 for x in lat_ms]


def timing_stats(rows: list[dict]) -> dict:
    """Tier-0 per-frame timing of one capture (no device clock): what the GIL wait + comtypes dispatch in pymf's
    OnReadSample would show. ``arrival_minus_sample_ms``: qpc arrival minus MF sample time, per mode
    (tsanalysis.modes_report, as W-TS reports it; evidence only) and as offsets from the sample-time grid point
    (``grid_offsets``): ``offset_p99_ms`` = p99 of |offset - median offset| and ``offset_std_ms`` are rated.
    ``sample_time_drops``: frames missing in the sample-time slots (tsanalysis.slot_frames with the measured
    period; gaps count only where the grid can separate one period from two, W-TS's rule period > 2 x grid; None
    when it cannot). ``arrival_interval_ms``: evidence only (on a 16 ms grid its spread follows the 32/48 ms mix).
    The first SKIP_FRAC of frames (start-up) is left out."""
    pts = [(r.get("qpc_ns"), r.get("sample_time_100ns")) for r in rows
           if isinstance(r.get("qpc_ns"), (int, float)) and not isinstance(r.get("qpc_ns"), bool)]
    pts = pts[int(len(pts) * SKIP_FRAC):]
    out: dict[str, Any] = {"n": len(pts)}
    if len(pts) < 10:
        return out
    arr = [a / 1e6 for a, _ in pts]
    iv = [b - a for a, b in zip(arr, arr[1:])]
    mean = sum(iv) / len(iv)
    out["arrival_interval_ms"] = {"mean": round(mean, 3), "std": round((sum((x - mean) ** 2 for x in iv)
                                                                        / len(iv)) ** 0.5, 3),
                                  "p99": round(_pct(iv, 0.99), 3), "max": round(max(iv), 3)}
    st = [(a, s * 100.0) for a, s in pts if isinstance(s, (int, float)) and not isinstance(s, bool)]
    if len(st) < 10:
        return out
    st_ns = [s for _, s in st]
    try:
        sl = tsa.slot_frames(st_ns)             # grid auto-detected from the sample times; measured period
    except ValueError as e:                     # sample times that do not increase
        out["sample_time_error"] = str(e)
        return out
    grid = sl.get("grid_ms")
    lat = [(a - s) / 1e6 for a, s in st]
    off = grid_offsets(lat, grid)
    med = _pct(off, 0.5)
    dev = [abs(x - med) for x in off]
    om = sum(off) / len(off)
    modes = tsa.modes_report(lat)
    out["arrival_minus_sample_ms"] = {
        "grid_ms": grid, "offset_p99_ms": round(_pct(dev, 0.99), 3),
        "offset_std_ms": round((sum((x - om) ** 2 for x in off) / len(off)) ** 0.5, 3),
        "offset_max_ms": round(max(dev), 3),
        "modes": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()
                   if k in ("centre_ms", "share", "std_ms", "count")} for m in modes["modes"]]}
    per = sl.get("period_ns")
    out["sample_time_slots"] = {"period_ms": round(per / 1e6, 3) if per else None, "slotting": sl.get("slotting"),
                                "drops_detectable": sl.get("drops_detectable"), "grid_ms": grid}
    out["sample_time_drops"] = (sl["slots"][-1] - (len(st_ns) - 1)) if sl.get("drops_detectable") else None
    return out


def compare_timing(w: dict | None, p: dict | None) -> dict:
    """pymf's tier-0 timing against wincam's (TIMING_* tolerances). Each criterion is None when not measurable."""
    tw, tp = (w or {}).get("timing") or {}, (p or {}).get("timing") or {}

    def within(a, b) -> bool | None:
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return None
        return b <= a + max(TIMING_ABS_MS, TIMING_REL * a)
    lw, lp = tw.get("arrival_minus_sample_ms") or {}, tp.get("arrival_minus_sample_ms") or {}
    jw, jp = lw.get("offset_p99_ms"), lp.get("offset_p99_ms")
    sw, sp = lw.get("offset_std_ms"), lp.get("offset_std_ms")
    dw, dp = tw.get("sample_time_drops"), tp.get("sample_time_drops")
    return {"arrival_jitter_ok": within(jw, jp), "arrival_jitter_ms": {"wincam": jw, "pymf": jp},
            "offset_std_ok": within(sw, sp), "offset_std_ms": {"wincam": sw, "pymf": sp},
            "drops_ok": (dp <= dw + 1) if isinstance(dw, int) and isinstance(dp, int) else None,
            "sample_time_drops": {"wincam": dw, "pymf": dp}}


def capture_stats(summary: dict | None, rows: list[dict], check: dict | None, run: dict | None) -> dict:
    s = summary or {}
    fr = s.get("frames") or {}
    t = s.get("timings") or {}
    tot = fr.get("total") or 0
    chk = check or {}
    cs = chk.get("check_summary") or {}
    cpu = s.get("cpu") or {}
    return {"ok": bool(s.get("ok")), "exit_code": s.get("exit_code"), "error": s.get("error"),
            "negotiated": {k: (s.get("negotiated") or {}).get(k) for k in ("native_type_index", "subtype", "width",
                                                                           "height", "fps_num", "fps_den",
                                                                           "readback_ok")},
            "frames_total": tot, "frames_ok": fr.get("ok"), "valid_fraction": (fr.get("ok") or 0) / tot if tot else None,
            "fps_fit": ck.fps_from_rows(rows) if rows else None, "fps_measured": s.get("fps_measured"),
            "cpu_pct_of_one_core": cpu.get("pct_of_one_core"), "cpu": cpu,
            "first_frame_ms": t.get("first_frame_ms"), "open_to_first_frame_ms": t.get("open_to_first_frame_ms"),
            "close_ms": t.get("close_ms"), "process_elapsed_s": (run or {}).get("elapsed_s"),
            "header_sha1": chk.get("header_sha1"), "header_sha1_distinct": chk.get("header_sha1_distinct"),
            "strict_ok_fraction": cs.get("strict_ok_fraction"), "lenient_ok_fraction": cs.get("lenient_ok_fraction"),
            "checked": chk.get("checked"), "timing": timing_stats(rows),
            "unreleasable": s.get("unreleasable"), "abandoned_threads": s.get("abandoned_threads")}


def compare_capture(w: dict | None, p: dict | None) -> dict:
    """The capture criteria (None = not measurable). Tolerances: fps within 2 %; open-to-first-frame within
    max(150 ms, 30 %); CPU <= max(2x wincam, wincam + 5 points of one core); valid >= 99 % and >= wincam - 1 %."""
    if not w or not p:
        return {"compared": False}
    out: dict[str, Any] = {"compared": True}
    pv, wv = p.get("valid_fraction"), w.get("valid_fraction")
    out["valid_ok"] = (pv is not None and pv >= VALID_MIN and (wv is None or pv >= wv - 0.01)) if p["frames_total"] \
        else False
    hw, hp = w.get("header_sha1"), p.get("header_sha1")
    out["header_sha1_equal"] = (hw == hp) if hw and hp else None
    fw, fp = w.get("fps_fit") or w.get("fps_measured"), p.get("fps_fit") or p.get("fps_measured")
    out["fps_ratio"] = (fp / fw) if fw and fp else None
    out["fps_ok"] = abs(out["fps_ratio"] - 1.0) <= FPS_TOL if out["fps_ratio"] else None
    lw, lp = w.get("open_to_first_frame_ms"), p.get("open_to_first_frame_ms")
    if isinstance(lw, (int, float)) and isinstance(lp, (int, float)) and lw >= 0 and lp >= 0:
        out["latency_delta_ms"] = lp - lw
        out["latency_ok"] = lp <= lw + max(LAT_ABS_MS, LAT_REL * lw)
    else:
        out["latency_delta_ms"], out["latency_ok"] = None, None
    cw, cp = w.get("cpu_pct_of_one_core"), p.get("cpu_pct_of_one_core")
    if isinstance(cw, (int, float)) and isinstance(cp, (int, float)):
        out["cpu_delta_pp"] = cp - cw
        out["cpu_ok"] = cp <= max(CPU_REL * cw, cw + CPU_ABS_PP)
    else:
        out["cpu_delta_pp"], out["cpu_ok"] = None, None
    out["timing"] = compare_timing(w, p)
    return out


# ------------------------------------------------------------------------------------------------- cycles
def cycle_rows(out_dir: Path) -> list[dict]:
    rows = results.read_jsonl(Path(out_dir) / "cycles.jsonl")
    return [{k: v for k, v in r.items() if k != "steps"} for r in rows]


def cycle_fps_p50(rows: list[dict]) -> float | None:
    """Median per-cycle delivered rate (``fps_measured``, wincam 1.2 / pymf cycle rows) over the successful cycles;
    None when the rows carry no rate (older tool versions)."""
    v = sorted(float(r["fps_measured"]) for r in rows or []
               if r.get("ok") and isinstance(r.get("fps_measured"), (int, float)) and r["fps_measured"] > 0)
    if not v:
        return None
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2.0


def compare_cycles(wsum: dict | None, psum: dict | None, wfps: float | None = None,
                   pfps: float | None = None) -> dict:
    """``wfps`` / ``pfps``: per-cycle delivered rate p50 (cycle_fps_p50) of wincam / pymf; pymf must reach
    wincam's within CYC_FPS_TOL (both include the same start-up interval, so they compare like for like)."""
    if not wsum or not psum or not wsum.get("n") or not psum.get("n"):
        return {"compared": False, "ok": None}
    ws, ps = wsum.get("success_rate") or 0.0, psum.get("success_rate") or 0.0
    wl, pl = wsum.get("open_to_first_frame_ms_p50"), psum.get("open_to_first_frame_ms_p50")
    lat_ok = None
    if isinstance(wl, (int, float)) and isinstance(pl, (int, float)):
        lat_ok = pl <= wl + max(LAT_ABS_MS, LAT_REL * wl)
    hang_ok = (psum.get("hangs") or 0) <= (wsum.get("hangs") or 0) and \
        (psum.get("unreleasable") or 0) <= (wsum.get("unreleasable") or 0)
    succ_ok = ps >= ws - SUCCESS_TOL
    fps_ok = None
    if isinstance(wfps, (int, float)) and isinstance(pfps, (int, float)) and wfps > 0:
        fps_ok = pfps >= wfps * (1.0 - CYC_FPS_TOL)
    return {"compared": True, "success_rate": {"wincam": ws, "pymf": ps}, "success_ok": succ_ok,
            "open_to_first_frame_ms_p50": {"wincam": wl, "pymf": pl}, "latency_ok": lat_ok, "hang_ok": hang_ok,
            "fps_measured_p50": {"wincam": wfps, "pymf": pfps}, "fps_ok": fps_ok,
            "ok": bool(succ_ok and hang_ok and lat_ok is not False and fps_ok is not False)}


# ------------------------------------------------------------------------------------------------- rating
def rate_camera(m: dict) -> dict:
    """pymf equivalence for one camera from its measurements (pure: the run and --reanalyze use it)."""
    cap = m.get("capture_compare") or {}
    crit = []

    def add(text: str, met: Any, detail: Any = None) -> None:
        crit.append({"criterion": text, "met": met, "detail": detail})

    lst = (m.get("list") or {})
    add("listed by both (MF symlink, friendly name)", (lst.get("in_wincam") and lst.get("in_pymf") and
                                                        lst.get("name_equal") is not False) if lst else None, lst)
    fm = m.get("formats_compare") or {}
    add("native types equal (every stream, in order, synthesized NV12 flagged alike)", fm.get("equal"),
        {k: fm.get(k) for k in ("n_wincam", "n_pymf", "only_wincam", "only_pymf", "order_equal")})
    cc = m.get("controls_compare") or {}
    add("control readback equal (ranges, defaults, caps, modes; auto-mode value drift not counted)", cc.get("equal"),
        {"diffs": (cc.get("diffs") or [])[:8], "auto_drift": len(cc.get("auto_drift") or [])})
    rt = m.get("set_roundtrip") or {}
    add("pymf sets exposure/focus/gain/WB, reads back, restores; modes as found afterwards", rt.get("ok"),
        {"sets": len(rt.get("sets") or []), "error": rt.get("error")})
    unt = m.get("capture_untested")
    add(f"MJPG {m.get('mode') or '720p30'}: pymf valid-JPEG rate >= {VALID_MIN:.0%} and >= wincam's - 1 %",
        None if unt else cap.get("valid_ok"), {"pymf": (m.get("capture") or {}).get("pymf", {}).get("valid_fraction"),
                                              "wincam": (m.get("capture") or {}).get("wincam", {}).get("valid_fraction")})
    add("JPEG header SHA-1 equal to wincam's (same camera, same mode)", None if unt else cap.get("header_sha1_equal"))
    add(f"fps within {FPS_TOL:.0%} of wincam's", None if unt else cap.get("fps_ok"), cap.get("fps_ratio"))
    add(f"open-to-first-frame within max({LAT_ABS_MS:g} ms, {LAT_REL:.0%}) of wincam's",
        None if unt else cap.get("latency_ok"), cap.get("latency_delta_ms"))
    add(f"CPU % of one core <= max({CPU_REL:g}x wincam, wincam + {CPU_ABS_PP:g} points)",
        None if unt else cap.get("cpu_ok"), cap.get("cpu_delta_pp"))
    tm = cap.get("timing") or {}
    add(f"arrival jitter (arrival delay off the MF sample-time grid, p99 of |offset - median|) <= wincam's + "
        f"max({TIMING_ABS_MS:g} ms, {TIMING_REL:.0%})", None if unt else tm.get("arrival_jitter_ok"),
        tm.get("arrival_jitter_ms"))
    add(f"arrival delay std off the MF sample-time grid <= wincam's + max({TIMING_ABS_MS:g} ms, {TIMING_REL:.0%})",
        None if unt else tm.get("offset_std_ok"), tm.get("offset_std_ms"))
    add("frames lost (MF sample-time slots, measured period; only where the grid can show a drop) <= wincam's + 1",
        None if unt else tm.get("drops_ok"), tm.get("sample_time_drops"))
    hangs = m.get("hangs") or []
    ran = bool(m.get("capture") or m.get("cycles"))
    add("pymf never hung or left an unreleasable reader (wincam's own hangs are device evidence, not counted)",
        False if any(h.get("tool") == "pymf" for h in hangs) else (True if ran else None),
        hangs or None)
    cy = m.get("cycles_compare") or {}
    add(f"open/close cycles: success rate >= wincam's - 2 %, no extra hangs, first-frame p50 within tolerance, "
        f"per-cycle fps p50 >= {1 - CYC_FPS_TOL:.0%} of wincam's",
        None if m.get("cycles_untested") else cy.get("ok"), {k: cy.get(k) for k in ("success_rate",
                                                                                    "open_to_first_frame_ms_p50",
                                                                                    "fps_measured_p50")})
    measured = [c for c in crit if c["met"] is not None]
    failed = [c["criterion"] for c in crit if c["met"] is False]
    hard = (lst.get("in_wincam") and not lst.get("in_pymf")) or \
        (fm.get("compared") is False and fm.get("wincam_ok") and not fm.get("pymf_ok")) or \
        (not unt and (m.get("capture") or {}).get("wincam", {}).get("frames_total") and
         not (m.get("capture") or {}).get("pymf", {}).get("frames_total")) or         any(h.get("tool") == "pymf" for h in hangs)      # wincam ran the same part first without a fault
    untested_parts = [p for p, u in (("capture", unt), ("cycles", m.get("cycles_untested"))) if u]
    if not measured:
        r = rating.untested(m.get("untested_reason") or "nothing measured", {"criteria_failed": failed})
        r["criteria"] = crit
        return r
    if hard:
        rr, label = "no", "no (pymf failed where wincam worked)"
    elif failed:
        rr, label = "partial", "partial (" + str(len(failed)) + " difference" + ("s" if len(failed) > 1 else "") + ")"
    elif untested_parts:
        rr, label = "partial", "partial (" + ", ".join(untested_parts) + " untested)"
    else:
        rr, label = "yes", "yes"
    note = "; ".join(filter(None, [("differences: " + "; ".join(failed)) if failed else None,
                                   ("untested: " + ", ".join(f"{p} ({m.get(p + '_untested')})"
                                                             for p in untested_parts)) if untested_parts else None]))
    return {"rating": rr, "criteria": crit, "evidence": {"differences": failed, "untested_parts": untested_parts,
                                                         "is_kiyo": m.get("is_kiyo"), "not_covered": NOT_COVERED},
            "note": note or None, "summary_label": label}


#: what a W-PYMF 'yes' does not show (stated in every verdict): the build-language decision still needs these
NOT_COVERED = ("several cameras streaming at once in ONE Python process (skellycam's use: GIL contention between "
               "callbacks is not measured; each comparison is one camera alone)",
               "60 fps modes (the Kiyo's 1280x720@60): only the default 720p30 MJPEG mode is compared",
               "long runs: captures are --pymf-seconds (5 s) each",
               "control sets on a streaming source (needed for the C930e, whose exposure holds only when set >= 1 s "
               "after the first frame): pymf's set round trip runs on an idle camera; pymf capture has no "
               "--schedule / --controls-before yet, so IAMCameraControl calls from Python while a comtypes "
               "OnReadSample callback runs on MF work-queue threads are not exercised",
               "in-use-by-other detection (IMFSensorActivityMonitor): not ported to pymf")

#: overall cap while pymf cannot set controls on a streaming source (NOT_COVERED item 4): a 'yes' would read as
#: 'native Python MF is sufficient' although the C930e's set-after-first-frame path never ran through pymf
STREAMING_SET_CAP = "partial (control sets on a streaming source not tested through pymf)"


def aggregate(per: dict[str, dict]) -> dict:
    """The worst measured camera; a camera whose streaming parts are untested because of a device fault (the Kiyo
    wedge) caps a 'yes' at 'partial (<camera> untested: device fault)', never 'no' (the camera failed, not pymf)."""
    tested = {k: v for k, v in per.items() if v.get("rating") in ("yes", "partial", "no")}
    if not tested:
        return rating.untested("no camera measured", {"cameras": {k: v.get("note") for k, v in per.items()}})
    w = rating.worst(tested.values())
    faulted = [k for k, v in per.items() if "device fault" in str(v.get("note") or "")]
    label = w
    if faulted and w in ("yes", "partial"):
        w, label = "partial", f"partial ({', '.join(faulted)} untested: device fault)"
    if w == "yes":
        w, label = "partial", STREAMING_SET_CAP
    diffs: dict[str, list] = {}
    for k, v in per.items():
        for d in (v.get("evidence") or {}).get("differences") or []:
            diffs.setdefault(d, []).append(k)
    return {"rating": w, "criteria": [{"criterion": f"{k}: pymf equivalent to wincam", "met":
                                       None if v.get("rating") == "untested" else v.get("rating") == "yes",
                                       "detail": v.get("summary_label") or v.get("rating")} for k, v in per.items()],
            "evidence": {"differences_by_criterion": diffs, "device_fault_cameras": faulted,
                         "not_covered": NOT_COVERED,
                         "question": "can the Windows capture backend be native Python (comtypes/ctypes, no compiled "
                                     "extension) and match wincam?"},
            "summary_label": label}


# ============================================================================================================ run
def _in_scope(ctx, m) -> bool:
    """Dom 2026-11-08: exactly 720 lines at >= the min rate. common.modescope carries the upper bound
    (``--max-height``, default 720, 0 = none); an older modescope without it gets the 720 cap here."""
    sc = modescope.from_args(getattr(ctx, "args", None))
    if sc.all_modes:
        return True
    if hasattr(sc, "max_height"):
        return sc.contains(m.w, m.h, m.fps)
    return sc.contains(m.w, m.h, m.fps) and m.h <= 720


def choose_mode(ctx, wformats: dict | None) -> tuple[Any, dict]:
    modes = ck.mjpeg_modes(wformats)
    kept = [m for m in modes if _in_scope(ctx, m)]
    sc = modescope.from_args(getattr(ctx, "args", None))
    rec = {"advertised_mjpeg": len(modes), "in_scope": [m.text for m in kept],
           "scope": sc.as_dict() if hasattr(sc, "as_dict") else str(sc),
           "rule": "exactly 720 lines at >= 30 fps by default (Dom 2026-11-08)"}
    best = ck.default_mode(kept) if kept else None
    rec["mode"] = best.text if best else None
    return best, rec


def _gated(ctx, cam: dict) -> dict | None:
    try:
        return ck.device_gated(ctx, cam) or ck.device_fault(ctx, cam)
    except Exception:  # noqa: BLE001
        return None


def _note_fault(ctx, cam: dict, tool: str, summary: dict | None, run: dict, mode_text: str | None) -> dict | None:
    """pymf commands are not in camcmd's streaming list, so a pymf hang / 0x8007001F is recorded here."""
    api = "mf" if tool == "wincam" else "pymf"
    f = ck.fault_from_result("mf", summary, run)
    if f and f.get("kind") != "gated":
        try:
            ck.mark_device_fault(ctx, cam, TEST, mode_text, api, f)
        except Exception:  # noqa: BLE001
            pass
    return f


def record_fault(m: dict, part: str, tool: str, flt: dict | None, probe: dict | None = None) -> bool:
    """A fault in a streaming part. Shared rating contract: a device fault (0x8007001F, the Kiyo wedge) is never an
    API result, so the part becomes 'untested (device fault)'. A hang / unreleasable reader ends the part. A pymf
    hang counts against pymf only when wincam's 1-frame health probe right after it (``probe``) streamed normally;
    when the probe also failed (or did not run) the camera itself is faulted (the Kiyo wedges as a 35 s hang, not
    only as 0x8007001F), so the hang is kept as device evidence (``device_hangs``) and the part is 'untested (device
    fault)'. A wincam hang is device evidence too (``hangs``, tool wincam: never counted against pymf). Returns True
    when the part must stop."""
    if not flt or flt.get("kind") == "gated":
        return False
    if flt.get("kind") == "device_error":
        m[f"{part}_untested"] = (f"device fault ({flt.get('code')}) during the {tool} {part}; replug needed "
                                 "(a device fault is not an API result)")
    elif tool == "pymf" and not (probe or {}).get("ok"):
        m.setdefault("device_hangs", []).append({"part": part, "tool": tool, **flt, "probe_after": probe})
        m[f"{part}_untested"] = (f"device fault: the pymf {part} ended with {flt.get('kind')} ({flt.get('stage')}) "
                                 "and wincam's 1-frame MF probe right after it "
                                 f"{'failed too' if probe else 'could not run'}, so the camera, not pymf, is the "
                                 "suspect (a device fault is not an API result)")
    else:
        m.setdefault("hangs", []).append({"part": part, "tool": tool, **flt,
                                          **({"probe_after": probe} if probe is not None else {})})
        m[f"{part}_untested"] = f"{tool} {part} ended with {flt.get('kind')} ({flt.get('stage')}); camera gated"
    return True


def probe_after_hang(ctx, cam: dict, mode, out_dir: Path, part: str, flt: dict | None) -> dict | None:
    """wincam's 1-frame MF health probe after a pymf hang / timeout (W-MULTI's rule): tells a camera wedge from a
    pymf defect. None when there is nothing to probe (no fault, a device_error, or a gated result)."""
    if not flt or flt.get("kind") in ("gated", "device_error"):
        return None
    try:
        pr = ck.health_check(ctx, cam, mode, out_dir, test=TEST,
                             reason=f"{TEST}: after a pymf {part} {flt.get('kind')} ({flt.get('stage')})")
    except Exception as e:  # noqa: BLE001 - the probe must never break the test
        return {"ok": None, "error": repr(e)}
    return {k: pr.get(k) for k in ("ok", "frames", "code", "stage", "class", "utc", "error", "recovered")}


def run_camera(ctx, cam: dict, tdir: Path, rdir: Path, list_cmp: dict) -> dict:
    slug = ck.cam_slug(cam)
    m: dict[str, Any] = {"key": cam["key"], "name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"),
                         "slug": slug,      # the file names below; --reanalyze reads them back by this slug
                         "list": (list_cmp.get("per_camera") or {}).get(cam["key"])}
    dev = cam.get("mf_symlink")
    if not dev:
        m["untested_reason"] = "camera has no MF symbolic link"
        return m
    runs: dict[str, Any] = {}
    docs: dict[str, Any] = {}
    # ---- formats (listing: always runs, never gated)
    for tool, argv in (("wincam", ck.wincam_argv(ctx, "formats", "--api", "mf", "--device", dev, "--timeout-ms", 8000)),
                       ("pymf", pymf_argv(ctx, "formats", "--device", dev, "--timeout-ms", 8000))):
        r = ctx.camcmd(argv, timeout_s=45 + (UV_SLACK_S if tool == "pymf" else 0))
        docs[f"{tool}_formats"] = _json(r)
        runs[f"{tool}_formats"] = ck.run_brief(r)
        if docs[f"{tool}_formats"] is not None:
            results.write_json(tdir / f"{slug}_{tool}_formats.json", docs[f"{tool}_formats"])
    m["formats_compare"] = compare_formats(docs["wincam_formats"], docs["pymf_formats"])
    # ---- controls read-only
    for tool, argv in (("wincam", ck.wincam_argv(ctx, "controls", "--api", "mf", "--device", dev, "--read-only",
                                                 "--timeout-ms", TIMEOUT_MS)),
                       ("pymf", pymf_argv(ctx, "controls", "--device", dev, "--read-only", "--timeout-ms",
                                          TIMEOUT_MS))):
        r = ctx.camcmd(argv, timeout_s=40 + (UV_SLACK_S if tool == "pymf" else 0))
        docs[f"{tool}_controls"] = _json(r)
        runs[f"{tool}_controls"] = ck.run_brief(r)
        if docs[f"{tool}_controls"] is not None:
            results.write_json(tdir / f"{slug}_{tool}_controls.json", docs[f"{tool}_controls"])
    m["controls_compare"] = compare_controls(docs["wincam_controls"], docs["pymf_controls"])
    # ---- set round trip through pymf, verified by a wincam read afterwards
    sets = pick_set_values(docs["wincam_controls"])
    if sets and not (docs["wincam_controls"] or {}).get("device_not_answering"):
        spec = ",".join(f"{k}={v}" for k, v in sets.items())
        r = ctx.camcmd(pymf_argv(ctx, "controls", "--device", dev, "--set", spec, "--set-flags", "manual", "--restore",
                                 "--timeout-ms", TIMEOUT_MS), timeout_s=60 + UV_SLACK_S)
        docs["pymf_set"] = _json(r)
        runs["pymf_set"] = ck.run_brief(r)
        r2 = ctx.camcmd(ck.wincam_argv(ctx, "controls", "--api", "mf", "--device", dev, "--read-only", "--timeout-ms",
                                       TIMEOUT_MS), timeout_s=40)
        docs["wincam_controls_after"] = _json(r2)
        runs["wincam_controls_after"] = ck.run_brief(r2)
        m["set_roundtrip"] = check_roundtrip(docs["pymf_set"], docs["wincam_controls"], docs["wincam_controls_after"])
        m["set_roundtrip"]["requested"] = sets
        if docs["pymf_set"] is not None:
            results.write_json(tdir / f"{slug}_pymf_set.json", docs["pymf_set"])
        # safety net: a control that was in auto before and is not now goes back to auto (wincam, bounded)
        bad = [x["control"].split(".", 1)[-1] for x in m["set_roundtrip"].get("as_found_after") or []
               if not x["as_found"] and (x.get("before_flags") or 0) & 1]
        if bad:
            r3 = ctx.camcmd(ck.wincam_argv(ctx, "controls", "--api", "mf", "--device", dev, "--set",
                                           ",".join(f"{b}=auto" for b in bad), "--timeout-ms", TIMEOUT_MS),
                            timeout_s=40)
            m["set_roundtrip"]["safety_restore_to_auto"] = {"controls": bad, "run": ck.run_brief(r3)}
    else:
        m["set_roundtrip"] = {"ran": False, "ok": None, "reason": "no manual-capable exposure/focus/gain/WB control"
                              if not sets else "device not answering control GETs"}
    # ---- streaming parts
    mode, scope_rec = choose_mode(ctx, docs["wincam_formats"])
    m["mode_scope"] = scope_rec
    m["mode"] = mode.text if mode else None
    if mode is None:
        why = "untested (scope): no MJPEG mode with exactly 720 lines at >= 30 fps"
        m["capture_untested"] = m["cycles_untested"] = why
        m["runs"] = runs
        return m
    sec = capture_seconds(ctx)
    m["capture"] = {}
    for tool in ("wincam", "pymf"):
        g = _gated(ctx, cam)
        if g:
            m["capture_untested"] = f"device fault since {g.get('since_utc') or g.get('first_fault_utc')}"
            break
        od = rdir / slug / f"{tool}_capture_{mode.slug}"
        od.mkdir(parents=True, exist_ok=True)
        common = ["--device", dev, "--width", mode.w, "--height", mode.h, "--fps", mode.fps_arg, "--subtype", "MJPG",
                  "--seconds", sec, "--timeout-ms", TIMEOUT_MS, "--out-dir", od, "--save", "every:5"]
        argv = ck.wincam_argv(ctx, "capture", "--api", "mf", *common) if tool == "wincam" else \
            pymf_argv(ctx, "capture", *common)
        r = ctx.camcmd(argv, timeout_s=sec + 4 * TIMEOUT_MS / 1000 + 25 + (UV_SLACK_S if tool == "pymf" else 0))
        summ = _summary_file(od, _json(r))
        runs[f"{tool}_capture"] = ck.run_brief(r)
        flt = _note_fault(ctx, cam, tool, summ, r, mode.text)
        rows = ck.load_frames(od)
        chk = ck.check_saved(od, rows, mode.w, mode.h, limit=30)
        first = chk.pop("first_saved", None)
        if tool == "pymf":
            m["pymf_sample_jpeg"] = ck.save_sample(ctx, TEST, cam, f"pymf_{mode.slug}", first)
        m["capture"][tool] = capture_stats(summ, rows, chk, r)
        m["capture"][tool]["fault"] = flt
        m["capture"][tool]["raw_dir"] = str(od)
        probe = probe_after_hang(ctx, cam, mode, rdir / slug / f"_health_capture_{tool}", "capture", flt) \
            if tool == "pymf" else None
        if record_fault(m, "capture", tool, flt, probe):
            break
    if "wincam" in m["capture"] and "pymf" in m["capture"] and not m.get("capture_untested"):
        m["capture_compare"] = compare_capture(m["capture"]["wincam"], m["capture"]["pymf"])
    elif not m.get("capture_untested"):
        m["capture_untested"] = "a capture did not run"
    # ---- cycles
    n = n_cycles(ctx)
    m["cycles"] = {"requested": n}
    for tool in ("wincam", "pymf"):
        g = _gated(ctx, cam)
        if g:
            m["cycles_untested"] = f"device fault since {g.get('since_utc') or g.get('first_fault_utc')}"
            break
        od = rdir / slug / f"{tool}_cycle_{mode.slug}"
        od.mkdir(parents=True, exist_ok=True)
        common = ["--device", dev, "--width", mode.w, "--height", mode.h, "--fps", mode.fps_arg, "--subtype", "MJPG",
                  "--cycles", n, "--frames", 10, "--timeout-ms", TIMEOUT_MS, "--out", od]
        argv = ck.wincam_argv(ctx, "cycle", "--api", "mf", *common) if tool == "wincam" else \
            pymf_argv(ctx, "cycle", *common)
        per = 8.0 if cam.get("is_kiyo") else 5.0
        r = ctx.camcmd(argv, timeout_s=n * per + 60 + (UV_SLACK_S if tool == "pymf" else 0))
        summ = _summary_file(od, _json(r))
        runs[f"{tool}_cycle"] = ck.run_brief(r)
        flt = _note_fault(ctx, cam, tool, summ, r, mode.text)
        rows = cycle_rows(od)
        with open(tdir / f"{slug}_{tool}_cycles.jsonl", "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, default=str) + "\n")
        cs = cycstats.summarize_cycles(rows)
        m["cycles"][tool] = {"summary": cs, "tool_summary": (summ or {}).get("summary"), "fault": flt,
                             "exit_code": (summ or {}).get("exit_code"), "rows": len(rows),
                             "fps_measured_p50": cycle_fps_p50(rows)}
        probe = probe_after_hang(ctx, cam, mode, rdir / slug / f"_health_cycles_{tool}", "cycles", flt) \
            if tool == "pymf" else None
        if record_fault(m, "cycles", tool, flt, probe):
            break
    if "wincam" in m["cycles"] and "pymf" in m["cycles"] and not m.get("cycles_untested"):
        m["cycles_compare"] = compare_cycles(m["cycles"]["wincam"]["summary"], m["cycles"]["pymf"]["summary"],
                                             m["cycles"]["wincam"].get("fps_measured_p50"),
                                             m["cycles"]["pymf"].get("fps_measured_p50"))
    elif not m.get("cycles_untested"):
        m["cycles_untested"] = "a cycle run did not run"
    m["runs"] = runs
    return m


def verdicts_from(measure: dict) -> dict:
    v: dict[str, Any] = {}
    per = {}
    for k, m in (measure.get("cameras") or {}).items():
        per[k] = rate_camera(m)
        v[f"pymf_equivalence|{k}|pymf"] = per[k]
        cy = (m.get("cycles") or {}).get("pymf")
        hung = any(h.get("tool") == "pymf" and h.get("part") == "cycles" for h in m.get("hangs") or [])
        if cy and hung and not (cy.get("summary") or {}).get("n"):
            v[f"reliability|{k}|pymf_inproc"] = {
                "rating": "no", "criteria": [{"criterion": "no hang beyond the watchdog", "met": False,
                                              "detail": cy.get("fault")}],
                "evidence": {"hangs": m.get("hangs")}, "summary_label": "no (hang)",
                "note": "the pymf cycle process hung (killed at its timeout) before writing a cycle row"}
        elif cy and (not m.get("cycles_untested") or hung):
            summ = dict(cy["summary"])
            if hung:
                summ["hangs"] = max(1, summ.get("hangs") or 0)
            r = rating.rate_reliability(summ, replug_needed=None)
            r.setdefault("evidence", {})["note_381"] = ("a per-camera '>= 99 %' claim needs >= 381 failure-free "
                                                        f"cycles; this run had {cy['summary'].get('n')}")
            # W-CYC's labelling: a 'yes' below the Wilson bound reads 'yes (point estimate; n=..., Wilson lower ...)'
            w_cyc.apply_wilson_claim(r, summ, claim_99=False)
            v[f"reliability|{k}|pymf_inproc"] = r
        elif m.get("cycles_untested"):
            v[f"reliability|{k}|pymf_inproc"] = rating.untested(m["cycles_untested"])
    v["pymf_equivalence"] = aggregate(per)
    return v


def run(ctx) -> dict:
    res = ck.new_result(ctx, TEST)
    m: dict[str, Any] = {"info": INFO, "cycles_per_tool": n_cycles(ctx), "capture_seconds": capture_seconds(ctx),
                         "pymf_cli": str(PYMF_CLI), "wincam": str(ctx.wincam), "cameras": {}}
    errors: list = []
    tdir = ctx.test_dir(TEST)
    rdir = ctx.raw_test_dir(TEST)
    before = ck.arrivals_before(ctx)
    try:
        if not PYMF_CLI.exists():
            raise FileNotFoundError(f"pymf CLI missing at {PYMF_CLI}")
        warm = ctx.run(pymf_argv(ctx, "--version"), 180)       # resolves the uv environment (opens no camera)
        m["pymf_version"] = (warm.get("stdout") or "").strip() or None
        m["pymf_warmup"] = ck.run_brief(warm)
        lists = run_list(ctx)
        list_cmp = compare_lists(lists["wincam"]["doc"], lists["pymf"]["doc"], ctx.cameras)
        m["list"] = {**list_cmp, "runs": {k: v["run"] for k, v in lists.items()},
                     "elapsed_ms": {k: ((v["doc"] or {}).get("mf") or {}).get("elapsed_ms") for k, v in lists.items()}}
        for k, v in lists.items():
            if v["doc"] is not None:
                results.write_json(tdir / f"{k}_list.json", v["doc"])
        for cam in ctx.cameras:
            ctx.log(f"{TEST}: {ck.cam_label(cam)}")
            try:
                m["cameras"][cam["key"]] = run_camera(ctx, cam, tdir, rdir, list_cmp)
            except Exception as e:  # noqa: BLE001 - one camera never stops the test
                import traceback
                errors.append({"camera": cam["key"], "exception": f"{type(e).__name__}: {e}",
                               "traceback": traceback.format_exc()})
                m["cameras"][cam["key"]] = {"key": cam["key"], "name": cam.get("name"), "untested_reason":
                                            f"exception: {type(e).__name__}: {e}"}
    except Exception as e:  # noqa: BLE001
        import traceback
        errors.append({"exception": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()})
    m["arrivals"] = ck.arrivals_after(ctx, before)
    v = verdicts_from(m)
    return results.finish_result(res, measurements=m, verdicts=v, errors=errors)


# ============================================================================================================ offline
def reanalyze(run_dir: str | Path, out: str | Path | None = None) -> dict:
    """Recompute the comparisons and verdicts of a finished run from <run_dir>/W-PYMF.json and the per-camera tool
    JSONs in <run_dir>/W-PYMF/ (no camera opened). Writes <run_dir>/reanalysis/W-PYMF.json (or ``out``)."""
    run_dir = Path(run_dir)
    doc = json.loads((run_dir / f"{TEST}.json").read_text(encoding="utf-8"))
    meas = doc.get("measurements") or {}
    tdir = run_dir / TEST
    cams = doc.get("cameras") or []

    def load(p: Path) -> dict | None:
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        except ValueError:
            return None
    lw, lp = load(tdir / "wincam_list.json"), load(tdir / "pymf_list.json")
    if lw is not None or lp is not None:
        meas["list"] = {**(meas.get("list") or {}), **compare_lists(lw, lp, cams)}
    for c in cams:
        m = (meas.get("cameras") or {}).get(c.get("key"))
        if m is None:
            continue
        slug = m.get("slug") or ck.cam_slug(c)     # the run-time slug (serial or hub port), not the summary's
        m["list"] = ((meas.get("list") or {}).get("per_camera") or {}).get(c.get("key"), m.get("list"))
        fw, fp = load(tdir / f"{slug}_wincam_formats.json"), load(tdir / f"{slug}_pymf_formats.json")
        if fw is not None or fp is not None:
            m["formats_compare"] = compare_formats(fw, fp)
        cw, cp = load(tdir / f"{slug}_wincam_controls.json"), load(tdir / f"{slug}_pymf_controls.json")
        if cw is not None or cp is not None:
            m["controls_compare"] = compare_controls(cw, cp)
        cap = m.get("capture") or {}
        if "wincam" in cap and "pymf" in cap:
            m["capture_compare"] = compare_capture(cap["wincam"], cap["pymf"])
        cyc, cfps = {}, {}
        for tool in ("wincam", "pymf"):
            p = tdir / f"{slug}_{tool}_cycles.jsonl"
            if p.exists():
                rows = results.read_jsonl(p)
                cyc[tool] = cycstats.summarize_cycles(rows)
                cfps[tool] = cycle_fps_p50(rows)
                ent = m.setdefault("cycles", {}).setdefault(tool, {})
                ent["summary"], ent["fps_measured_p50"] = cyc[tool], cfps[tool]
        if len(cyc) == 2:
            m["cycles_compare"] = compare_cycles(cyc["wincam"], cyc["pymf"], cfps["wincam"], cfps["pymf"])
    new = {"reanalysis_of": str(run_dir), "utc": results.utc_now_iso(), "camera_opened": False,
           "measurements": meas, "verdicts": verdicts_from(meas)}
    results.write_json(Path(out) if out else run_dir / "reanalysis" / f"{TEST}.json", new)
    return new


def main(argv: list[str] | None = None) -> int:
    import argparse
    a0 = list(sys.argv[1:] if argv is None else argv)
    if "--reanalyze" in a0 or "--reanalyse" in a0:
        ap = argparse.ArgumentParser(description=f"{TEST} offline re-analysis (opens no camera)")
        ap.add_argument("--reanalyze", "--reanalyse", dest="run_dir", required=True)
        ap.add_argument("--out", default=None)
        a = ap.parse_args(a0)
        d = reanalyze(a.run_dir, a.out)
        print(json.dumps({k: (x or {}).get("summary_label") or (x or {}).get("rating")
                          for k, x in d["verdicts"].items()}, indent=1))
        return 0
    import suitectx
    ap = suitectx.add_common_args(argparse.ArgumentParser(description=f"{TEST} standalone (opens cameras)"))
    ap.add_argument("--pymf-cycles", dest="pymf_cycles", type=int, default=None)
    ap.add_argument("--pymf-seconds", dest="pymf_seconds", type=float, default=None)
    ap.add_argument("--camera", action="append", default=[], help="opt-in filter (key or name substring)")
    a = ap.parse_args(a0)
    ctx = suitectx.build_ctx(a)
    if a.camera:
        ctx.cameras = [c for c in ctx.cameras if any(f.lower() in f"{c['key']} {c.get('name')}".lower()
                                                     for f in a.camera)]
    res = run(ctx)
    p = ctx.write(TEST, res)
    print(json.dumps({"out": str(p), "verdicts": {k: (x or {}).get("summary_label") or (x or {}).get("rating")
                                                  for k, x in (res.get("verdicts") or {}).items()}}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
