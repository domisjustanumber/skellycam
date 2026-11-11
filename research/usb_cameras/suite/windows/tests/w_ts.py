"""W-TS: per-frame timestamps per camera x API (G-TS), tier 0 only.

Plan section 6.2 (TS) and section 3 (G-TS thresholds). Per camera, at the default mode (MJPG 720p30, else the nearest mode in the streaming mode scope: exactly 720 lines at >= 30 fps,
common/modescope.py; a camera without one is rated 'untested (scope)'), one capture of --ts-seconds (30 s; quick
8 s) through MF (wincam), through DirectShow with PyAV as-is (``ds``; PyAV falls back to YUY2 where the camera offers
a raw format at that size and rate, e.g. the Kiyo) and through DirectShow with the ffmpeg CLI and -vcodec mjpeg
(``ds_ffmpeg``; MJPEG guaranteed; its packet time is the wall clock at demux, used as the arrival time).

Tier 0 only (Dom 2026-11-09): no registry changes and no UVC PTS/SCR testing (device timestamps are judged
unreliable from published work). wincam may still write its metadata fields into frames.jsonl (when the
MetadataBufferSizeInKB0 value is present); this test never reads, compares or rates them.

Timestamp sources (all host-side, tier 0):
- MF: QPC arrival (qpc_ns) and the MF sample time (sample_time_100ns);
- DS through PyAV: QPC arrival in Python (qpc_ns) and the FFmpeg packet pts (IMediaSample time);
- DS through the ffmpeg CLI: the packet pts (wall clock at demux), which stands in as the arrival time;
- every route: the frame-index model fitted to the arrival times.
Analysis (common.tsanalysis): grid/quantisation of each clock; frame-index fit to arrival (causal and whole-run;
slots from the measured period, never the nominal); synthesized-timestamp detection for DS pts (even intervals while
arrivals jitter, or drift vs arrival); drop detection on the MF sample time and the DS pts with the measured period
(only where the timestamp grid can separate one period from two and the intervals jitter by less than a quarter
period, else ``drops`` is None; per interval only on a steady clock, the whole-series slot count
``drops_cumulative`` on the ffmpeg CLI wall clock or a grid coarser than a quarter period); arrival-minus-
sample-time reported per mode (it is bimodal on a 16 ms grid), never as one median.

No ground truth is available unattended, so the frame-index model is 'untested' until the flash/rig run. The camera x API verdict is the best available route
INCLUDING untested ones (so an API whose designated tier-0 route, the frame-index model, is unscored stays
'untested' even when a native stamp is a measured 'no'; analysis ts.md verifier V3.1); every source also has its
own verdict column. The suite has no ground-truth route: the former ``--flash`` option ran timing/build/
mf_uvc_timing.exe, which records the UVC PTS/SCR payload metadata (out of scope since Dom's 2026-11-09 tier-0-only
decision) and bypassed this test's dead-device gate, so it was removed. A tier-0 ground-truth run is a separate,
attended step.

A camera that fails with a device fault (ERROR_GEN_FAILURE 0x8007001F, or a capture that hangs until the timeout)
is not opened again in this test: its remaining cells are 'untested' with evidence.device_fault. Cameras the suite
runner already marked faulted are skipped the same way.

Offline re-analysis of a finished run (no camera is opened):
    python suite/windows/tests/w_ts.py --reanalyse <run_dir> [--raw-dir <raw_dir>]
writes <run_dir>/reanalysis/W-TS.json (the original W-TS.json is not changed).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
from common import rating, results, tsanalysis as tsa  # noqa: E402

TEST = "W-TS"
# Ranking for the camera x API verdict. 'untested' outranks 'no' BY DESIGN: the API's designated tier-0 route (the
# frame-index model) is unscored until the flash/rig run, and a measured 'no' for one native stamp does not make
# the API 'no' (plan section 4; analysis ts.md verifier V3.1). Do not change.
_ORDER = {"yes": 3, "partial": 2, "untested": 1, "no": 0}
AGGREGATE_NOTE = ("best available route for this API, including untested ones (the frame-index model stays "
                  "untested until the flash/rig run); per-source verdicts are in the '<api>:<source>' columns")
DEVICE_FAULT_HR = "0x8007001F"
#: capture routes: MF (wincam), DirectShow through PyAV as-is (it falls back to YUY2 where the camera offers
#: a raw format at that size and rate: the Kiyo), DirectShow through the ffmpeg CLI with -vcodec mjpeg
APIS = ("mf", "ds", "ds_ffmpeg")


def seconds(ctx) -> float:
    return float(ck.arg(ctx, "ts_seconds", 30.0, 8.0))


def estimate_s(ctx) -> float:
    # three captures per camera (MF, PyAV DirectShow, ffmpeg-CLI DirectShow), ~6 s overhead each
    return len(ctx.cameras) * len(APIS) * (seconds(ctx) + 6)


def _strip(d: dict | None, keys=("mapped_ns", "residuals_ns", "fitted_ns", "slots")) -> dict | None:
    if not isinstance(d, dict):
        return d
    return {k: v for k, v in d.items() if k not in keys}


def _fits(times: list[float], period_ns: float, grid_ms: float | None = None) -> dict:
    out = {}
    for causal in (True, False):
        f = tsa.fit_frame_index(times, causal=causal, nominal_period_ns=period_ns, grid_ms=grid_ms)
        out["causal" if causal else "whole_run"] = _strip(f)
    return out


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _grid_ms(g: dict | None) -> float | None:
    if not g or not g.get("quantized"):
        return None
    return g.get("step_ms")


JITTER_FRAC = 0.25      # interval std above period x this: per-interval drop counting is unreliable (smoke 2026-11-09)


def _detectable(period_ns: float | None, grid_ms: float | None, interval_std_ns: float | None = None) -> bool | None:
    """A dropped frame is visible in a timestamp only if the grid is finer than half the period (ts.md B7) and the
    intervals do not jitter by more than a quarter period (a host wall clock: a long/short interval pair would
    round to a 'drop' plus a 'duplicate'; ds_ffmpeg showed 14-22 false drops per 8 s on 2026-11-09)."""
    if not period_ns:
        return None
    if interval_std_ns is not None and interval_std_ns > JITTER_FRAC * period_ns:
        return False
    return True if grid_ms is None else period_ns > 2.0 * grid_ms * 1e6


def _drops_measured(times: list[float], grid_ms: float | None, skip_startup: bool = True,
                    host_clock: bool = False) -> dict:
    """Drop count on a timestamp series with the MEASURED period (span / slots, never the nominal: the generic
    camera runs at 25.7 fps in its 30 fps mode; ts.md V4/B7). The first interval is start-up (the generic camera's
    first MF sample-time interval is 64 ms with frame 0 flagged as a discontinuity) and is reported separately.

    Per-interval rounding (tsanalysis.detect_drops) is used only on a steady clock. On a host wall clock
    (``host_clock``: the ffmpeg CLI packet time) or a grid coarser than a quarter period, one late frame gives a
    long/short interval pair that rounds to a 'drop' plus a 'duplicate' (smoke 2026-11-09: 14-22 false drops per
    8 s on ds_ffmpeg, and 8 false duplicates on the Kiyo's 16 ms MF sample-time grid); there ``drops`` is the
    whole-series count ``drops_cumulative`` (slot_frames keeps a gap only when it lowers the whole-run fit
    residual). An interval std above a quarter period makes drops undetectable (``drops`` None)."""
    out: dict = {"startup_interval_ms": None}
    t = list(times)
    if skip_startup and len(t) >= 3:
        out["startup_interval_ms"] = (t[1] - t[0]) / 1e6
        t = t[1:]
    if len(t) < 3:
        out["error"] = "too few timestamps"
        return out
    sl = tsa.slot_frames(t, grid_ms=grid_ms if grid_ms is not None else 0.0)
    per = sl["period_ns"]
    iv = [b - a for a, b in zip(t, t[1:])]
    std = tsa.stats(iv).get("std") if len(iv) >= 2 else None
    out.update(period_ms=per / 1e6 if per else None, slotting=sl["slotting"], grid_ms=grid_ms,
               interval_std_ms=None if std is None else std / 1e6,
               drops_detectable=_detectable(per, grid_ms, std),
               # whole-series count: slot_frames keeps gaps only when they lower the whole-run fit residual, so a
               # long/short pair from arrival jitter is not counted (unlike the per-interval rounding below)
               drops_cumulative=(sl["slots"][-1] - (len(t) - 1)) if sl.get("slots") else None)
    if not out["drops_detectable"]:
        out["drops"] = None
        if std is not None and per and std > JITTER_FRAC * per:
            out["note"] = (f"interval std {std / 1e6:.2f} ms is more than {JITTER_FRAC:g} x the period "
                           f"({out['period_ms']:.2f} ms): per-interval rounding would count a long/short pair as a "
                           "drop; drops_cumulative is the whole-series count")
        else:
            out["note"] = (f"grid {grid_ms} ms is not finer than half the period ({out['period_ms']:.2f} ms): one "
                           "and two periods cannot be told apart")
        return out
    coarse = grid_ms is not None and grid_ms * 1e6 > JITTER_FRAC * per
    if host_clock or coarse:
        out["drops"] = out["drops_cumulative"]
        out["drops_method"] = "cumulative (slot_frames)"
        out["note"] = ("host wall clock" if host_clock else f"grid {grid_ms} ms coarser than a quarter period") +             ": per-interval rounding would count a long/short pair as a drop; whole-series count"
        return out
    d = tsa.detect_drops(t, period=per)
    d["index_offset"] = 1 if skip_startup else 0
    out.update(d)
    out["drops_method"] = "per interval"
    return out


def analyse_mf(rows: list[dict], mode) -> dict:
    """MF rows (wincam): QPC arrival and MF sample time only (tier 0). Any UVC metadata fields in the rows are
    ignored."""
    period = 1e9 / mode.fps
    qpc = [r["qpc_ns"] for r in rows if _num(r.get("qpc_ns"))]
    st = [r["sample_time_100ns"] * 100.0 for r in rows if _num(r.get("sample_time_100ns"))]
    a: dict = {"frames": len(rows), "fields": {"qpc_ns": len(qpc), "sample_time_100ns": len(st)}}
    a["mf_discontinuity_flags_after_frame0"] = sum(1 for r in rows[1:] if r.get("discontinuity"))
    if len(qpc) >= 10:
        a["grid_qpc_arrival"] = tsa.grid_analysis(qpc, nominal_period_ns=period)
        a["frame_index_fit_arrival"] = _fits(qpc, period, _grid_ms(a["grid_qpc_arrival"]))
    if len(st) >= 10:
        a["grid_sample_time"] = tsa.grid_analysis(st, nominal_period_ns=period)
        a["drops_sample_time"] = _drops_measured(st, _grid_ms(a["grid_sample_time"]))
        if len(qpc) == len(st):
            lat = [(q - s) / 1e6 for q, s in zip(qpc, st)]
            # bimodal on a 16 ms grid: shares per mode, never one median (ts.md V5)
            a["arrival_minus_sample_time_ms"] = tsa.modes_report(lat)
    return a


def analyse_ds(rows: list[dict], mode, wallclock_pts: bool = False) -> dict:
    """DirectShow rows (pyav_ds). ``wallclock_pts``: the ffmpeg CLI engine, whose rows carry no QPC and whose
    ``pts_ns`` is the wall clock when FFmpeg read the packet; that time then stands in as the arrival time."""
    period = 1e9 / mode.fps
    qpc = [r["qpc_ns"] for r in rows if _num(r.get("qpc_ns"))]
    pts = [r["pts_ns"] for r in rows if _num(r.get("pts_ns"))]
    a: dict = {"frames": len(rows), "fields": {"qpc_ns": len(qpc), "pts_ns": len(pts)}}
    if wallclock_pts and not qpc and len(pts) >= 10:
        a["arrival_basis"] = "ffmpeg CLI wall clock at demux (pts_ns); no QPC in these rows"
        a["grid_qpc_arrival"] = tsa.grid_analysis(pts, nominal_period_ns=period)
        a["frame_index_fit_arrival"] = _fits(pts, period, _grid_ms(a["grid_qpc_arrival"]))
    if len(qpc) >= 10:
        a["grid_qpc_arrival"] = tsa.grid_analysis(qpc, nominal_period_ns=period)
        a["frame_index_fit_arrival"] = _fits(qpc, period, _grid_ms(a["grid_qpc_arrival"]))
    if len(pts) >= 10:
        a["grid_pts"] = tsa.grid_analysis(pts, nominal_period_ns=period)
        same = len(qpc) == len(pts)
        a["pts_synthesized"] = tsa.synthesized_check(pts, qpc if same else None)
        if a["pts_synthesized"].get("synthesized"):
            # counter-generated pts cannot show a gap: no drop count rather than a misleading 0 (ts.md B7)
            a["drops_pts"] = None
            a["drops_pts_note"] = "pts synthesized from a counter: drops cannot be seen in them"
        else:
            a["drops_pts"] = _drops_measured(pts, _grid_ms(a["grid_pts"]), skip_startup=False,
                                             host_clock=wallclock_pts)
        if same:
            lat = [(q - p) / 1e6 for q, p in zip(qpc, pts)]
            a["arrival_minus_pts_ms"] = tsa.modes_report(lat)
            a["arrival_minus_pts_drift_ms_per_s"] = a["pts_synthesized"].get("drift_ms_per_s")
    return a


# ------------------------------------------------------------------------------------------------ rating
def rate_sources(api: str, a: dict, cam: dict) -> dict:
    """One rating per tier-0 timestamp source; the camera x API verdict is the best of them (see _ORDER)."""
    out = {}
    if api == "mf":
        g = _grid_ms(a.get("grid_sample_time"))
        dst = a.get("drops_sample_time") or {}
        det = dst.get("drops_detectable")
        # host time (tier 0): no device-timestamp criterion; without ground truth a fine-grid source is 'untested'
        out["mf_sample_time"] = rating.rate_ts(causal_error_ms_1sigma=None, drops_detectable=det, ground_truth=False,
                                               host_grid_ms=g)
        out["mf_sample_time"]["detail"] = {"grid_step_ms": g, "measured_period_ms": dst.get("period_ms"),
                                           "drops": dst.get("drops"), "drops_cumulative": dst.get("drops_cumulative"),
                                           "interval_std_ms": dst.get("interval_std_ms"),
                                           "startup_interval_ms": dst.get("startup_interval_ms")}
    else:
        src = "ffmpeg_pts" if api == "ds_ffmpeg" else "pyav_pts"
        g = _grid_ms(a.get("grid_pts"))
        sc = a.get("pts_synthesized") or {}
        synth = bool(sc.get("synthesized"))
        dp = a.get("drops_pts")
        det = False if synth else (dp or {}).get("drops_detectable")
        out[src] = rating.rate_ts(causal_error_ms_1sigma=None, drops_detectable=det, ground_truth=False,
                                  synthesized=synth, host_grid_ms=g)
        out[src]["detail"] = {"grid_step_ms": g, "synthesized": synth,
                              "interval_std_ms": sc.get("interval_std_ms"),
                              "modal_share": sc.get("modal_share"), "distinct_intervals": sc.get("distinct_intervals"),
                              "drift_vs_arrival_ms_per_s": sc.get("drift_ms_per_s"), "reasons": sc.get("reasons"),
                              "drops": None if dp is None else dp.get("drops"),
                              "drops_cumulative": None if dp is None else dp.get("drops_cumulative"),
                              "note": ("ffmpeg CLI packet time: the wall clock when FFmpeg read the packet "
                                       "(use_wallclock_as_timestamps), host time" if api == "ds_ffmpeg" else
                                       "IMediaSample time from the DirectShow graph: host time, not the camera's")}
    fa = a.get("frame_index_fit_arrival") or {}
    fit = fa.get("causal") or {}
    whole = fa.get("whole_run") or {}
    out["frame_index_fit"] = rating.rate_ts(None, None, False)
    out["frame_index_fit"]["detail"] = {"causal_residual_ms": fit.get("residual_stats_ms"),
                                        "fps": whole.get("fps"), "slotting": whole.get("slotting"),
                                        "slots_skipped": whole.get("slots_skipped"),
                                        "drops_detectable": whole.get("drops_detectable"),
                                        "fit_unreliable": whole.get("fit_unreliable") or fit.get("fit_unreliable"),
                                        "unreliable_reasons": whole.get("unreliable_reasons"),
                                        "note": "arrival jitter only; error vs truth needs the flash/rig run"}
    return out


# ------------------------------------------------------------------------------------------------ device faults
def _fault_of(s: dict | None, r: dict | None, test_mode: str) -> dict | None:
    """A device fault record from one capture: ERROR_GEN_FAILURE (0x8007001F, class device_error), an
    unreleasable reader, a hung capture (timed out / killed by the harness), or the runner's gate answering for a
    faulted camera (gate_skipped / class device_fault). None otherwise (an EIO at DS open is ambiguous and not a
    fault by itself)."""
    s = s or {}
    err = s.get("error") or {}
    if not isinstance(err, dict):
        err = {}
    hung = bool((r or {}).get("timed_out") or (r or {}).get("killed"))
    gate = bool(s.get("gate_skipped") or (r or {}).get("gate_skipped"))
    unrel = bool(s.get("unreleasable") or err.get("unreleasable"))
    if str(err.get("hr", "")).upper() == DEVICE_FAULT_HR.upper() \
            or err.get("class") in ("device_error", "device_fault") \
            or s.get("device_fault") is True or hung or gate or unrel:
        prior = s.get("fault") if isinstance(s.get("fault"), dict) else {}
        code = err.get("hr") or s.get("fault_code") or prior.get("code") or \
            ("timeout" if hung else ("unreleasable" if unrel else err.get("class")))
        return {"device_fault": True, "fault_code": code,
                "first_fault_utc": s.get("first_fault_utc") or prior.get("since_utc") or results.utc_now_iso(),
                "scope": "suite gate (fault before this test)" if gate else f"first fault seen by {TEST}",
                "test": prior.get("test") if gate else TEST, "mode": prior.get("mode") if gate else test_mode,
                "stage": err.get("stage"),
                "reason": err.get("reason") or ("capture hung until the harness timeout" if hung else
                                                ("reader could not be released" if unrel else None))}
    return None


def _prior_fault(ctx, cam: dict) -> dict | None:
    """The runner's dead-device gate (suitectx): ``ctx.camera_gated(cam)`` is the fault record when the camera was
    faulted at the START of this test (after the runner's 1-frame health re-probe), else None. Without that API
    (older runner / unit tests) a ``ctx.faults`` mapping {key: record} is honoured, skipping records whose
    ``faulted`` flag is False (recovered)."""
    fn = getattr(ctx, "camera_gated", None)
    if callable(fn):
        try:
            rec = fn(cam)
        except Exception:  # noqa: BLE001
            rec = None
        return _norm_fault(rec) if rec else None
    m = getattr(ctx, "faults", None)
    if isinstance(m, dict):
        rec = m.get(cam.get("key"))
        if isinstance(rec, dict) and rec.get("faulted", True):
            return _norm_fault(rec)
    return None


def _norm_fault(rec: dict) -> dict:
    """Runner records use since_utc / code; the rating contract reads first_fault_utc / fault_code."""
    out = dict(rec)
    out.setdefault("device_fault", True)
    out.setdefault("first_fault_utc", rec.get("since_utc") or rec.get("utc") or rec.get("since"))
    out.setdefault("fault_code", rec.get("code"))
    out.pop("history", None)
    return out


def _report_fault(ctx, cam: dict, rec: dict, api: str) -> None:
    """Tell the runner's gate (``ctx.mark_fault``; idempotent, camcmd usually marked it already)."""
    fn = getattr(ctx, "mark_fault", None)
    if not callable(fn):
        return
    try:
        fn(cam, test=TEST, mode=rec.get("mode"), code=rec.get("fault_code"), api=api, stage=rec.get("stage"),
           cls="device_error", source="w_ts", detail=rec.get("reason"))
    except Exception:  # noqa: BLE001
        pass


def _fault_verdict(rec: dict) -> dict:
    if hasattr(rating, "device_fault_untested"):
        return rating.device_fault_untested(rec)
    since = rec.get("first_fault_utc") or rec.get("since") or rec.get("utc")
    ev = dict(rec)
    ev["device_fault"] = True
    return rating.untested(f"device fault, replug needed (since {since})" if since else
                           "device fault, replug needed", ev)


# ------------------------------------------------------------------------------------------------ verdicts
def verdicts_for(cam: dict, api: str, a: dict, n_rows: int, fault: dict | None = None) -> tuple[dict, dict]:
    """(aggregate verdict, {cell key suffix: verdict}) for one camera x API analysis (tier-0 sources only)."""
    cells: dict = {}
    srcs = rate_sources(api, a, cam) if n_rows else {}
    a["source_ratings"] = {k: x["rating"] for k, x in srcs.items()}
    if srcs:
        best_name = max(srcs, key=lambda k: _ORDER.get(srcs[k]["rating"], 0))
        v = dict(srcs[best_name])
        v.update(source=best_name, tier=0)
        v["source_ratings"] = {k: x["rating"] for k, x in srcs.items()}
        v["aggregate_note"] = AGGREGATE_NOTE
        # every source also gets its own column, so a 'no' (synthesized DS pts, 16 ms MF sample-time grid) is
        # visible in summary.md and not hidden behind the best source (review 2026-11-06)
        for sname, sv in srcs.items():
            sv = dict(sv)
            sv.update(source=sname, tier=0)
            cells[f"{api}:{sname}"] = sv
        if fault:
            v.setdefault("evidence", {})
            if isinstance(v["evidence"], dict):
                v["evidence"]["device_fault_during_capture"] = fault
    elif fault:
        v = _fault_verdict(fault)
        v["evidence"]["capture_error"] = a.get("capture_error")
    else:
        v = rating.untested("no frames captured", {"capture_error": a.get("capture_error")})
    return v, cells


def run(ctx) -> dict:
    res = ck.new_result(ctx, TEST)
    arr0 = ck.arrivals_before(ctx)
    secs = seconds(ctx)
    errors: list = []
    verdicts: dict = {}
    per_cam: dict = {}
    faults: dict = {}
    cache: dict = {}
    raw = Path(ctx.raw_dir) / TEST
    for cam in ctx.cameras:
        prior = _prior_fault(ctx, cam)
        cres: dict = {"name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"), "mode": None, "apis": {}}
        if prior:
            # the runner's dead-device gate: do not open a camera that stopped answering earlier in the suite
            cres["skipped"] = "device fault before this test"
            cres["device_fault"] = prior
            fu = getattr(ctx, "fault_untested", None)
            for api in APIS:
                v = None
                if callable(fu):
                    try:
                        v = fu(cam)
                    except Exception:  # noqa: BLE001
                        v = None
                verdicts[f"G-TS|{cam['key']}|{api}"] = v or _fault_verdict(prior)
            per_cam[cam["key"]] = cres
            faults[cam["key"]] = prior
            ctx.log(f"{TEST}: {cam.get('name')} skipped: device fault since "
                    f"{prior.get('first_fault_utc') or prior.get('since')}")
            continue
        fm, fread = ck.formats_checked(ctx, cam, cache, TEST)
        if fread:
            # the format read failed (e.g. the Kiyo hanging at activation): a recorded camera result, not a scope
            # exclusion; the health probe in formats_checked turns a hang / 0x8007001F into a device fault
            ctx.log(f"{TEST}: {cam.get('name')}: {fread['untested_reason']}")
            cres["skipped"] = fread["untested_reason"]
            cres["format_read"] = fread
            for api in APIS:
                verdicts[f"G-TS|{cam['key']}|{api}"] = ck.format_failed_untested(fread)
            if fread.get("fault"):
                faults[cam["key"]] = _norm_fault(fread["fault"])
            per_cam[cam["key"]] = cres
            continue
        advertised = ck.mjpeg_modes(fm)
        # mode scope (common/modescope.py): 1280x720@30 MJPEG, else the nearest in-scope MJPEG mode
        mode, scope = ck.scoped_default(ctx, advertised)
        cres["mode"] = mode.text if mode else None
        cres["mode_scope"] = scope
        if mode is None:
            # the list was read: no MJPEG mode in the streaming scope (or none at all)
            ctx.log(f"{TEST}: {cam.get('name')}: {scope.get('untested_reason')}")
            cres["skipped"] = scope.get("untested_reason")
            for api in APIS:
                verdicts[f"G-TS|{cam['key']}|{api}"] = ck.scope_untested(ctx, scope)
            per_cam[cam["key"]] = cres
            continue
        fault: dict | None = None
        for api in APIS:
            od = raw / ck.cam_slug(cam) / api
            try:
                if fault:
                    # one device fault per camera is enough: do not open a wedged camera again (dead-device gate)
                    cres["apis"][api] = {"skipped": "device fault earlier in this test", "device_fault": fault}
                    verdicts[f"G-TS|{cam['key']}|{api}"] = _fault_verdict(fault)
                    continue
                if api == "mf":
                    if not cam.get("mf_symlink"):
                        continue
                    s, r = ck.wincam_capture(ctx, cam, mode, od, seconds=secs, save="none")
                else:
                    if not cam.get("ds_path"):
                        continue
                    s, r = ck.pyav_capture(ctx, cam, mode, od, seconds=secs, save="none",
                                           engine="ffmpeg" if api == "ds_ffmpeg" else "pyav")
                rows = ck.load_frames(od)
                a = analyse_mf(rows, mode) if api == "mf" else analyse_ds(rows, mode, wallclock_pts=api == "ds_ffmpeg")
                a["capture_ok"] = bool((s or {}).get("ok"))
                a["capture_error"] = (s or {}).get("error")
                a["run"] = r
                a["frames_jsonl"] = str(od / "frames.jsonl")
                f = _fault_of(s, r, f"{api} {mode.text}")
                if f:
                    fault = f
                    a["device_fault"] = f
                    faults[cam["key"]] = f
                    _report_fault(ctx, cam, f, api)
                v, cells = verdicts_for(cam, api, a, len(rows), f)
                for suffix, sv in cells.items():
                    verdicts[f"G-TS|{cam['key']}|{suffix}"] = sv
                verdicts[f"G-TS|{cam['key']}|{api}"] = v
                cres["apis"][api] = a
                ctx.log(f"{TEST}: {cam.get('name')} {api}: {len(rows)} frames, "
                        f"verdict {v['rating']} ({v.get('source')})" + (f", DEVICE FAULT {f['fault_code']}" if f else ""))
            except Exception as e:  # noqa: BLE001
                errors.append({"camera": cam["key"], "api": api, "exception": repr(e)})
        per_cam[cam["key"]] = cres
    meas = {"seconds": secs, "quick": ck.quick(ctx), "cameras": per_cam, "arrivals": ck.arrivals_after(ctx, arr0),
            "ground_truth": None, "device_faults": faults,
            "timestamp_scope": "tier 0 only (Dom 2026-11-09): host-side sources; UVC PTS/SCR not read"}
    return results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)


# ------------------------------------------------------------------------------------------------ re-analysis
_CARRY = ("capture_ok", "capture_error", "run", "frames_jsonl")


def _mode_from_text(text: str | None) -> SimpleNamespace | None:
    m = re.search(r"(\d+)x(\d+)@([\d.]+)", text or "")
    if not m:
        return None
    return SimpleNamespace(w=int(m.group(1)), h=int(m.group(2)), fps=float(m.group(3)), text=text)


def reanalyse(run_dir: str | Path, raw_dir: str | Path | None = None, out_path: str | Path | None = None) -> dict:
    """Recompute W-TS measurements and verdicts from the saved frames.jsonl of a finished run (no camera is
    opened). Writes <run_dir>/reanalysis/W-TS.json (or ``out_path``) and returns it. The original W-TS.json is
    read only."""
    run_dir = Path(run_dir)
    src = run_dir / f"{TEST}.json"
    res = json.loads(src.read_text(encoding="utf-8"))
    raw_dir = Path(raw_dir) if raw_dir else Path(results.default_raw_dir(run_dir))
    cams = {c["key"]: c for c in res.get("cameras") or []}
    meas = res.get("measurements") or {}
    old_verdicts = res.get("verdicts") or {}
    new_verdicts: dict = {k: v for k, v in old_verdicts.items() if not k.startswith("G-TS|")}
    per_cam: dict = {}
    faults: dict = {}
    notes: list = []
    for key, cres0 in (meas.get("cameras") or {}).items():
        cam = cams.get(key) or {"key": key, "name": cres0.get("name"), "is_kiyo": cres0.get("is_kiyo")}
        cres = {k: v for k, v in cres0.items() if k not in ("apis", "metadata_tier1")}
        cres["apis"] = {}
        mode = _mode_from_text(cres0.get("mode"))
        if mode is None:
            per_cam[key] = cres
            continue
        fault: dict | None = None
        for api in APIS:
            a0 = (cres0.get("apis") or {}).get(api)
            if a0 is None:
                continue
            p = Path(a0.get("frames_jsonl") or "")
            if not p.exists():
                p = raw_dir / TEST / ck.cam_slug(cam) / api / "frames.jsonl"
            if not p.exists():
                notes.append(f"{key} {api}: frames.jsonl not found; kept the original analysis")
                cres["apis"][api] = a0
                continue
            if fault:
                # in the original run the next API was still opened after a device fault; the gate would have
                # skipped it, so it is rated as the fault (its own capture result is kept as evidence)
                cres["apis"][api] = dict(a0, device_fault=fault, skipped_by_gate_in_reanalysis=True)
                v = _fault_verdict(fault)
                v["evidence"]["capture_error"] = a0.get("capture_error")
                new_verdicts[f"G-TS|{key}|{api}"] = v
                continue
            rows = results.read_jsonl(p)
            a = analyse_mf(rows, mode) if api == "mf" else analyse_ds(rows, mode, wallclock_pts=api == "ds_ffmpeg")
            for k in _CARRY:
                if k in a0:
                    a[k] = a0[k]
            run_rec = a0.get("run") or {}
            started = None
            try:
                started = json.loads((p.parent / "summary.json").read_text(encoding="utf-8")).get("utc_started")
            except (OSError, ValueError):
                pass
            f = _fault_of({"error": a0.get("capture_error")}, run_rec, f"{api} {mode.text}")
            if f:
                f["first_fault_utc"] = started or res.get("utc_started")
                f["first_fault_utc_source"] = "capture summary utc_started" if started else "test start"
                fault = f
                a["device_fault"] = f
                faults[key] = f
            v, cells = verdicts_for(cam, api, a, len(rows), f)
            for suffix, sv in cells.items():
                new_verdicts[f"G-TS|{key}|{suffix}"] = sv
            new_verdicts[f"G-TS|{key}|{api}"] = v
            cres["apis"][api] = a
        per_cam[key] = cres
    changes = []
    for k in sorted(set(old_verdicts) | set(new_verdicts)):
        if not k.startswith("G-TS|"):
            continue
        b = (old_verdicts.get(k) or {}).get("rating")
        n = (new_verdicts.get(k) or {}).get("rating")
        if b != n:
            changes.append({"key": k, "before": b, "after": n})
    out = dict(res)
    out["measurements"] = dict(meas, cameras=per_cam, device_faults=faults)
    out["verdicts"] = new_verdicts
    tally: dict = {}
    for k, v in new_verdicts.items():
        if k.startswith("G-TS|"):
            tally[v.get("rating")] = tally.get(v.get("rating"), 0) + 1
    out["reanalysis"] = {
        "utc": results.utc_now_iso(), "source_result": str(src), "raw_dir": str(raw_dir),
        "code": ["suite/windows/tests/w_ts.py (reanalyse)", "suite/common/tsanalysis.py"],
        "fixes": ["frame-index slotting from the measured period (sequence / incremental), fit_unreliable",
                  "synthesized-pts detection (modal share / distinct values / drift)",
                  "None presence fields with 0 frames",
                  "drops_detectable = period > 2 x grid and interval std <= period/4; measured period",
                  "DS drop count None when pts synthesized", "ambiguous_with_period uses the nominal period",
                  "arrival-minus-sample-time per mode", "device fault -> untested 'device fault, replug needed'",
                  "G-TS contract: self_consistent False -> untested",
                  "tier 0 only (Dom 2026-11-09): UVC PTS / SCR sources, the mf:uvc_metadata cell and the "
                  "device-clock units / rate defect checks are gone (their old cells show as removed)"],
        "rating_changes": changes, "ratings": tally, "notes": notes}
    target = Path(out_path) if out_path else run_dir / "reanalysis" / f"{TEST}.json"
    results.write_json(target, out)
    return out


def _main(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(description="W-TS offline re-analysis (no camera is opened)")
    ap.add_argument("--reanalyse", "--reanalyze", dest="reanalyse", required=True, metavar="RUN_DIR",
                    help="finished run folder containing W-TS.json")
    ap.add_argument("--raw-dir", dest="raw_dir", default=None, help="raw folder (default: derived from RUN_DIR)")
    ap.add_argument("--out", default=None, help="output JSON (default: RUN_DIR/reanalysis/W-TS.json)")
    a = ap.parse_args(argv)
    out = reanalyse(a.reanalyse, a.raw_dir, a.out)
    r = out["reanalysis"]
    print(json.dumps({"written": str(Path(a.out) if a.out else Path(a.reanalyse) / "reanalysis" / f"{TEST}.json"),
                      "ratings": r["ratings"], "rating_changes": r["rating_changes"], "notes": r["notes"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
