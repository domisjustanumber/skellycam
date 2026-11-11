"""W-MJPEG: every advertised MJPEG mode through Media Foundation (wincam capture) and DirectShow (pyav_ds).

Plan section 6.2 (MJPEG) and section 3 (G-MJPEG thresholds). Per camera:
- the MJPEG modes come from ``wincam formats --api mf`` read now (never a built-in table);
- mode scope (common/modescope.py, Dom 2026-11-08): only modes with exactly 720 lines at >= 30 fps are streamed
  unless ``--all-modes`` (or ``--min-fps`` / ``--min-height`` / ``--max-height``); the scope and the number of advertised modes excluded are
  recorded per camera (``mode_scope``); a camera without an in-scope MJPEG mode is rated 'untested (scope)';
- full run: every in-scope (size, rate); ``--quick``: smallest size, the default mode (720p30 or nearest) and the
  largest size, each at its highest rate (all within the scope);
- ``activity_at_first_stream``: ``wincam activity`` (IMFSensorActivityMonitor, opens no camera) right before each
  camera's first stream: which other processes use the camera;
- sweep order for EVERY camera (``capkit.sweep_order``): the default mode first, then the modes at >= 15 fps, the
  low-rate modes last (the Kiyo wedged on its first stream, 640x360@5, in the 20261106 run; cyc_kiyo.md B10);
- each mode is captured for ``--mjpeg-seconds`` (default 3 s; quick 1.5 s; the default mode for 10 s in a full run
  so its CPU figure has 10 s resolution, H10) through MF (native MJPG, converters off, explicit subtype,
  GetCurrentMediaType readback) and through PyAV DirectShow (``pyav_ds``). PyAV cannot make FFmpeg's dshow demuxer
  pick MJPEG when a raw format exists at the same size and rate (measured: it delivers YUY2/NV12), so for those modes
  the mode is also captured with the ffmpeg CLI (``-vcodec mjpeg -c copy``, ``ffmpeg_ds``, CPU via GetProcessTimes).
  Ratings: ``mf``; ``ds`` = DirectShow through PyAV, or through the ffmpeg CLI where PyAV fell back; ``pyav_ds`` =
  PyAV alone;
- checks: SOI/EOI on every frame (tool flags), common.jpegcheck (marker walk, strict libjpeg-turbo decode when
  simplejpeg is importable, SOF0 size) on 8 frames spread across the capture (H6), fps vs the camera's real rate,
  JPEG header SHA-1 MF == DS per mode, process CPU (with its tick resolution);
- fps reference, symmetric (H1): the rate both APIs agree on (above OR below nominal), else nominal. Tier 0 only
  (Dom 2026-11-09): no device-clock (UVC PTS) rate. Whether the camera honours the requested rate is recorded
  separately per mode (``rate_honoured``: a camera finding, not an API failure), with PyAV's raw-fallback rate as a
  control experiment (verifier M3). Any mode whose MF or DS rate misses the reference by > 2 % is recaptured for
  10 s (H5) and the 10 s rates are used; the rate over the last 1.5 s is reported next to every fit;
- the camera's control state (auto-exposure priority, exposure mode, ...) is READ before and after its sweep and
  recorded; nothing is changed (H4);
- device faults (HRESULT 0x8007001F, or an unreleasable/hung reader) stop all further work on that camera at once
  (H3): the fault goes to ``ctx.device_faults`` (capkit), the remaining modes are recorded as skipped and the three
  verdicts rate 'untested' with ``evidence.device_fault`` True. A camera that arrives with a fault from an earlier
  test is health-checked once (1-frame MF); it is worked on only if it answers. A hang that is not
  ERROR_GEN_FAILURE gets one immediate health check; if the camera answers, the sweep continues and the recovery
  is recorded;
- cameras run one at a time and one mode at a time, so cameras that share a bandwidth domain never stream together
  in this test (W-MULTI covers contention).
Saved frames and per-frame JSONL go to raw_dir (outside the repo); results keep the per-mode summary and one sample
JPEG per camera and API (default mode).

Offline re-analysis of an earlier run (no camera; reads the run's W-MJPEG.json and the raw folders):

    uv run --python 3.12 --with simplejpeg --with pillow python suite/windows/tests/w_mjpeg.py \
        --reanalyse <run dir> [--raw-dir <raw run dir>] [--out <file>]

writes ``<run dir>/reanalysis/W-MJPEG.json`` (the original files are not touched).
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
from common import jpegcheck, rating, results  # noqa: E402

TEST = "W-MJPEG"
SAVED_TARGET = 18          # frames saved per mode at the nominal rate (``every`` from nominal; all when slow)
CHECK_PER_MODE = 8         # frames decoded per mode, spread across all saved frames (H6)
FPS_TOL = 0.02
CPU_WINDOW_S = 10.0        # the default mode is captured this long in a full run (H10)
RECAPTURE_S = 10.0         # H5
RECAPTURE_MAX_PER_CAMERA = 40
KNOWN_QUIRK_EXTRA = "extraneous bytes before EOI (libjpeg warning; REPORT finding 6, generic camera at large sizes)"
FAULT_REASON = "device fault, replug needed"


# ============================================================================================================ planning
def plan_modes(ctx, cam, cache) -> tuple[list, dict]:
    fm, run = ck.get_formats(ctx, cam, cache)
    advertised = ck.mjpeg_modes(fm)
    # mode scope (common/modescope.py): exactly 720 lines at >= 30 fps unless --all-modes
    modes, scope = ck.scoped(ctx, advertised)
    dflt = ck.default_mode(modes) if modes else None
    scope["default_mode"] = dflt.text if dflt else None
    if advertised and not modes:
        scope["untested_reason"] = ck.modescope.no_scope_mode_reason(ck.mode_scope(ctx), len(advertised))
    sel = ck.quick_modes(modes) if ck.quick(ctx) else modes
    sel = ck.sweep_order(sel, dflt if dflt in sel else None)
    return sel, {"advertised": len(advertised), "in_scope": len(modes), "selected": len(sel), "mode_scope": scope,
                 "formats_run": run,
                 "formats_error": (fm or {}).get("error") if fm else "no formats JSON",
                 "default_mode": dflt.text if dflt else None, "_default": dflt,
                 "order": "default first, then >= %g fps by size, low-rate modes last" % ck.LOW_FPS}


def estimate_s(ctx) -> float:
    """Seconds: reads the MF format lists now (one short camcmd per camera, cached for run())."""
    secs = float(ck.arg(ctx, "mjpeg_seconds", 3.0, 1.5))
    rec = float(ck.arg(ctx, "mjpeg_recapture_s", RECAPTURE_S, 0.0))
    n = 0
    for c in ctx.cameras:
        try:
            modes, _ = plan_modes(ctx, c, None)
            n += len(modes)
        except Exception:  # noqa: BLE001
            n += 3 if ck.quick(ctx) else 40
    # MF ~secs+1.5 s, PyAV ~secs+2.5 s, plus the ffmpeg CLI where PyAV falls back (~half the modes); the default
    # mode runs CPU_WINDOW_S; ~10 % of the modes are recaptured for 10 s on two APIs
    per = (secs + 1.5) + (secs + 2.5) + 0.5 * (secs + 3.0)
    extra = 0 if ck.quick(ctx) else len(ctx.cameras) * 3 * (CPU_WINDOW_S - secs)
    return n * per + extra + 0.1 * n * 2 * (rec + 2.5) + 10


def save_every(mode, secs: float) -> int:
    """every:N so that ~SAVED_TARGET frames are saved at the NOMINAL rate; a camera that runs faster than nominal
    (C922 at 30 at nominal 5) then saves more, never fewer, and the decode sample spreads over all of them."""
    return max(1, int(round(max(1.0, mode.fps * secs) / SAVED_TARGET)))


# ============================================================================================================ per API
def _api_summary(api: str, summary: dict | None, run: dict, mode, out_dir: Path) -> dict:
    """One (mode, API) capture -> the per-API record. ``api`` is 'mf' or 'ds' (any DirectShow route)."""
    rows = ck.load_frames(out_dir)
    chk = ck.check_saved(out_dir, rows, mode.w, mode.h, limit=CHECK_PER_MODE, spread=True)
    first = chk.pop("first_saved", None)
    s = summary or {}
    neg = s.get("negotiated") or {}
    ok_tool = bool(s.get("ok"))
    if api == "mf":
        negotiated = ok_tool and bool(neg.get("readback_ok")) and str(neg.get("subtype", "")).upper() == "MJPG"
    else:
        negotiated = ok_tool and (s.get("codec_is_mjpeg") is True) and not s.get("format_fallback")
    cpu_d = s.get("cpu") or {}
    cpu = cpu_d.get("pct_of_one_core")
    code, stage, err = ck.failure_code(api, s, run)
    cls = None if ok_tool else ck.classify(api, code, stage, frames=len(rows), timed_out=bool(run.get("timed_out")))
    fault = None if ok_tool else ck.fault_from_result(api, s, run, cls)
    cs = chk.get("check_summary") or {}
    strict = cs.get("strict_ok_fraction")
    lenient = cs.get("lenient_ok_fraction")
    quirk = None
    reasons = chk.get("strict_fail_reasons") or {}
    if strict is not None and strict < 0.99 and reasons and set(reasons) == {"extraneous_bytes_before_eoi"}:
        quirk = KNOWN_QUIRK_EXTRA
    has_qpc = any(isinstance(r.get("qpc_ns"), (int, float)) for r in rows)
    key = "qpc_ns" if has_qpc else "pts_ns"
    fps_steady = ck.fps_from_rows(rows, key=key)
    dur = s.get("duration_s")
    cpu_res = cpu_d.get("resolution_pct")
    if cpu_res is None and isinstance(dur, (int, float)) and dur > 0:
        cpu_res = 100.0 * 0.015625 / dur
    timings = s.get("timings") or {}
    return {"api": api, "ok": ok_tool, "negotiated": negotiated, "rc": run.get("rc"), "timed_out": run.get("timed_out"),
            "backend": s.get("backend") or ("wincam-mf" if api == "mf" else None),
            "frames": len(rows), "fps_measured_tool": s.get("fps_measured"), "fps_steady": fps_steady,
            "fps_tail_1p5s": ck.fps_tail(rows, key=key),
            "fps_basis": "qpc arrival" if has_qpc else "packet pts",
            "soi_fraction": chk.get("soi_fraction_all"), "eoi_fraction": chk.get("eoi_fraction_all"),
            "sof_match_fraction": chk.get("sof_match_fraction_all"), "checked": chk.get("checked"),
            "checked_seq": chk.get("checked_seq"), "saved_total": chk.get("saved_total"),
            "strict_ok_fraction": strict, "lenient_ok_fraction": lenient, "strict_fail_reasons": reasons,
            "extra_bytes_before_eoi": cs.get("extra_bytes_before_eoi"), "known_quirk": quirk,
            "header_sha1": chk.get("header_sha1"), "header_sha1_distinct": chk.get("header_sha1_distinct"),
            "cpu_pct_one_core": cpu, "cpu_resolution_pct": cpu_res, "cpu_method": cpu_d.get("method"),
            "timings": timings,
            "open_duration_ms": timings.get("open_duration_ms"), "negotiated_detail": neg,
            "format_fallback": s.get("format_fallback"), "pix_fmt": s.get("pix_fmt") or neg.get("pix_fmt"),
            "unreleasable": s.get("unreleasable"), "abandoned_threads": s.get("abandoned_threads"),
            "error": err or None, "classification": cls, "fault": fault,
            "utc_started": s.get("utc_started"), "utc_finished": s.get("utc_finished"),
            "out_dir": str(out_dir), "_first": first}


def _fps_by_api(row: dict) -> dict:
    return {k: (row["apis"].get(k) or {}).get("fps_steady") for k in ("mf", "ds")}


def finish_mode_row(row: dict, mode, tol: float = FPS_TOL) -> dict:
    """DS route, cross-API header equality, symmetric fps reference, rate_honoured, raw-fallback control rate."""
    apis = row["apis"]
    pv = apis.get("pyav_ds") or {}
    use_cli = bool(pv.get("format_fallback") and apis.get("ffmpeg_ds"))
    if apis.get("pyav_ds") or apis.get("ffmpeg_ds"):
        apis["ds"] = dict(apis["ffmpeg_ds"] if use_cli else pv)
        apis["ds"]["route"] = "ffmpeg_ds" if use_cli else "pyav_ds"
    mf, ds = apis.get("mf") or {}, apis.get("ds") or {}
    row["header_sha1_equal"] = (mf.get("header_sha1") == ds.get("header_sha1")) \
        if mf.get("header_sha1") and ds.get("header_sha1") else None
    fba = _fps_by_api(row)
    ref, basis, note = ck.fps_reference(fba, mode.fps, tol=tol)
    row["fps_nominal"] = mode.fps
    row["fps_reference"] = ref
    row["fps_reference_basis"] = basis
    row["fps_reference_note"] = note
    row["rate_honoured"] = ck.rate_honoured(fba, mode.fps, tol=tol)
    if pv.get("format_fallback") and pv.get("fps_steady"):
        f = pv["fps_steady"]
        row["raw_fallback_rate"] = {"pix_fmt": pv.get("pix_fmt"), "fps": f,
                                    "honoured": abs(f - mode.fps) / mode.fps <= tol,
                                    "note": "PyAV's silent raw fallback, same session: the camera's raw-format rate "
                                            "at this request (control experiment for the MJPEG rate)"}
    row["fps_misses"] = [k for k, v in fba.items() if isinstance(v, (int, float)) and v > 0
                         and abs(v - ref) / ref > tol]
    return row


# ============================================================================================================ rating
def _rate_rows(mode_rows: list[dict], api: str) -> list[dict]:
    rm = []
    for row in mode_rows:
        a = row["apis"].get(api) or {}
        strict = a.get("strict_ok_fraction")
        lenient = a.get("lenient_ok_fraction")
        soi, eoi = a.get("soi_fraction"), a.get("eoi_fraction")
        # every frame's SOI/EOI flags cap the sample-based decode fractions
        frame_flag = min(x for x in (soi, eoi) if x is not None) if (soi is not None or eoi is not None) else None
        if strict is not None and frame_flag is not None:
            strict = min(strict, frame_flag)
        if lenient is not None and frame_flag is not None:
            lenient = min(lenient, frame_flag)
        hashes = {}
        for k in ("mf", "ds" if api != "pyav_ds" else "pyav_ds"):
            h = (row["apis"].get(k) or {}).get("header_sha1")
            if h:
                hashes[k] = h
        frames = a.get("frames") or 0
        other = "mf" if api != "mf" else "ds"
        rm.append({"mode": row["mode"], "negotiated": bool(a.get("negotiated")), "frames": frames,
                   "fps_other_api": (row["apis"].get(other) or {}).get("fps_steady"),
                   "strict_valid_fraction": strict, "lenient_valid_fraction": lenient,
                   "known_quirk": a.get("known_quirk"),
                   "sof_matches": (a.get("sof_match_fraction") is not None and a["sof_match_fraction"] >= 0.99),
                   "fps_measured": a.get("fps_steady"), "fps_expected": row.get("fps_reference"),
                   "fps_nominal": row.get("fps_nominal"), "fps_reference_basis": row.get("fps_reference_basis"),
                   "rate_honoured": (row.get("rate_honoured") or {}).get("honoured"),
                   "header_sha1_by_api": hashes if len(hashes) == 2 else None,
                   # 0 frames = no JPEG bytes from this API in this mode (H2); a device fault is handled per camera
                   "is_jpeg": (soi or 0) > 0.5 if frames else False,
                   "skipped": row.get("skipped")})
    return rm


def _call_rate_mjpeg(rm: list[dict], fault_ev: dict | None) -> dict:
    """common.rating.rate_mjpeg plus the shared contract on this side: ``evidence.device_fault`` True -> untested
    ('device fault, replug needed'), whatever the rating function returned. Passes the fault fields as keyword
    arguments when the rating function accepts them (the rating owner may add them)."""
    try:
        params = inspect.signature(rating.rate_mjpeg).parameters
    except (TypeError, ValueError):
        params = {}
    kw = {}
    if fault_ev:
        for k in ("device_fault", "fault_code", "first_fault_utc"):
            if k in params:
                kw[k] = fault_ev.get(k)
        if "evidence" in params:
            kw["evidence"] = dict(fault_ev)
    v = rating.rate_mjpeg(rm, **kw)
    ev = v.get("evidence")
    ev = dict(ev) if isinstance(ev, dict) else {"modes": ev}
    if fault_ev:
        ev.update(fault_ev)
        if v.get("rating") != "untested":
            before = v.get("rating")
            v = rating.untested(FAULT_REASON, ev)
            v["superseded_rating"] = before
        why = fault_ev.get("fault_reason") or f"{fault_ev.get('fault_kind') or 'fault'} at {fault_ev.get('fault_stage')}"
        v["note"] = (f"{FAULT_REASON}: {why} since {fault_ev.get('first_fault_utc')} "
                     f"({fault_ev.get('fault_test')}, {fault_ev.get('fault_mode')}, {fault_ev.get('fault_api')}, "
                     f"{fault_ev.get('fault_code')}); {fault_ev.get('modes_measured_before_fault')} mode(s) measured "
                     "before the fault")
    v["evidence"] = ev
    return v


def fault_evidence(fault: dict | None, mode_rows: list[dict]) -> dict | None:
    if not fault:
        return None
    n_before = sum(1 for r in mode_rows if not r.get("skipped") and not r.get("after_device_fault")
                   and r.get("mode") != fault.get("mode"))
    return {"device_fault": True, "fault_code": fault.get("code"), "first_fault_utc": fault.get("utc"),
            "fault_test": fault.get("test"), "fault_mode": fault.get("mode"), "fault_api": fault.get("api"),
            "fault_kind": fault.get("kind"), "fault_stage": fault.get("stage"), "fault_reason": fault.get("reason"),
            "fault_capture_started_utc": fault.get("capture_started_utc"),
            "codes_after_fault": fault.get("codes_after_fault"), "modes_measured_before_fault": n_before}


def captured_modes(mode_rows: list[dict], api: str) -> int:
    """Modes that were not skipped and delivered frames through ``api`` (the ds route counts its chosen engine)."""
    return sum(1 for r in mode_rows if not r.get("skipped") and ((r.get("apis") or {}).get(api) or {}).get("frames"))


def rate_camera(cam_key: str, mode_rows: list[dict], info: dict, fault: dict | None) -> dict:
    """The three G-MJPEG verdicts (mf, ds, pyav_ds) of one camera."""
    verdicts = {}
    fev = fault_evidence(fault, mode_rows)
    for api in ("mf", "ds", "pyav_ds"):
        rm = _rate_rows(mode_rows, api)
        v = _call_rate_mjpeg(rm, fev)
        v["tier"] = 0
        # plan section 3: "every advertised MJPEG mode". A quick run captures 3 modes, so it cannot rate yes
        # (review 2026-11-06: the quick self-test reported 'yes' from 3 of 17 C922 modes). Under the mode scope
        # (Dom 2026-11-06) the target is every IN-SCOPE mode; the excluded count is recorded and labelled.
        target = int(info.get("in_scope", info["advertised"]) or 0)
        sc = info.get("mode_scope") or {}
        n_excl = int(sc.get("excluded") or 0)
        scope_txt = ((sc.get("scope") or {}).get("text")) or "all modes"
        # captured = not skipped (gate / device fault) and frames > 0 through this API (11-06: the gated Kiyo
        # showed "4/4 modes" with nothing captured)
        n_cap = captured_modes(mode_rows, api)
        all_modes = n_cap >= target > 0
        v.setdefault("criteria", []).append({"criterion": "every in-scope MJPEG mode was captured"
                                                          if n_excl else "every advertised MJPEG mode was captured",
                                             "met": all_modes, "detail": f"{n_cap}/{target} modes captured "
                                                                         f"({info['selected']} planned; scope "
                                                                         f"{scope_txt}; {n_excl} of "
                                                                         f"{info['advertised']} advertised modes "
                                                                         "excluded)"})
        if not all_modes and v["rating"] == "yes":
            v["rating"] = "partial"
            v["note"] = ((v.get("note") or "") + f" capped at partial: only {n_cap} of "
                         f"{target} in-scope modes captured").strip()
        labels = []
        if n_excl:
            v.setdefault("evidence", {})["mode_scope"] = sc
            v["note"] = ((v.get("note") or "") + f" mode scope {scope_txt}: {n_excl} of {info['advertised']} "
                         "advertised modes not streamed (--all-modes restores them)").strip()
            labels.append("in-scope modes")
        not_hon = [row["mode"] for row in mode_rows if not row.get("skipped")
                   and (row.get("rate_honoured") or {}).get("honoured") is False]
        if not_hon:
            labels.append(f"rate not honoured in {len(not_hon)}")
        if labels and v["rating"] in ("yes", "partial"):
            v["summary_label"] = f"{v['rating']} ({'; '.join(labels)})"
        if api == "pyav_ds":
            nfb = sum(1 for row in mode_rows if (row["apis"].get("pyav_ds") or {}).get("format_fallback"))
            if nfb:
                v["note"] = ((v.get("note") or "") + f" {nfb} mode(s) delivered raw video, not MJPEG: PyAV "
                             "cannot set FFmpeg's video_codec_id, so dshow takes the first caps entry matching "
                             "size and rate").strip()
        if api == "ds":
            v["routes"] = sorted({(row["apis"].get("ds") or {}).get("route") for row in mode_rows} - {None})
        modes_ev = (v.get("evidence") or {}).get("modes") or []
        ev = v["evidence"]
        skipped = {row["mode"] for row in mode_rows if row.get("skipped")}
        ev["rating_failed_modes"] = [m.get("mode") for m in modes_ev if isinstance(m, dict) and not m.get("ok")
                                     and m.get("mode") not in skipped]
        ev["skipped_modes"] = sorted(skipped)
        ev["modes_captured"] = n_cap
        rh = [row.get("rate_honoured") or {} for row in mode_rows if not row.get("skipped")]
        ev["rate_honoured_camera"] = {"honoured": sum(1 for x in rh if x.get("honoured") is True),
                               "not_honoured": [row["mode"] for row in mode_rows
                                                if (row.get("rate_honoured") or {}).get("honoured") is False],
                               "mixed_or_unmeasured": sum(1 for x in rh if x.get("honoured") is None),
                               "note": "camera behaviour: requested rate delivered within 2 % by every measured "
                                       "API (MF and DS); not an API failure, not part of the rating"}
        if not fev:
            ev["device_fault"] = False
        verdicts[f"G-MJPEG|{cam_key}|{api}"] = v
    return verdicts


def camera_summary(cam: dict, info: dict, mode_rows: list[dict], verdicts: dict, **extra) -> dict:
    rf = {api: ((verdicts.get(f"G-MJPEG|{cam['key']}|{api}") or {}).get("evidence") or {}).get("rating_failed_modes", [])
          for api in ("mf", "ds", "pyav_ds")}
    exp = [{"mode": r["mode"], "nominal": r.get("fps_nominal"),
            "mjpeg_mf_fps": (r["apis"].get("mf") or {}).get("fps_steady"),
            "raw_fps": r["raw_fallback_rate"]["fps"], "raw_pix_fmt": r["raw_fallback_rate"]["pix_fmt"],
            "raw_honoured": r["raw_fallback_rate"]["honoured"],
            "mjpeg_honoured": (r.get("rate_honoured") or {}).get("honoured")}
           for r in mode_rows if r.get("raw_fallback_rate")]
    return {"name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"),
            "modes_info": {k: v for k, v in info.items() if not k.startswith("_")},
            "default_mode": info.get("default_mode"), "modes": mode_rows,
            "tool_failed_modes": {api: [r["mode"] for r in mode_rows if not r.get("skipped")
                                        and not (r["apis"].get(api) or {}).get("ok")]
                                  for api in ("mf", "ds", "pyav_ds")},
            "skipped_modes": [r["mode"] for r in mode_rows if r.get("skipped")],
            "rating_failed_modes": rf,
            "pyav_format_fallback_modes": [r["mode"] for r in mode_rows
                                           if (r["apis"].get("pyav_ds") or {}).get("format_fallback")],
            "rate_control_experiment": {"rows": exp,
                                        "raw_honoured": sum(1 for x in exp if x["raw_honoured"]),
                                        "mjpeg_honoured_same_modes": sum(1 for x in exp if x["mjpeg_honoured"]),
                                        "n": len(exp)},
            **extra}


# ============================================================================================================ live run
def _capture(ctx, cam, m, api, od, secs, save):
    if api == "mf":
        if not cam.get("mf_symlink"):
            return None, None, {"api": api, "ok": False, "error": "no MF symlink"}
        s, r = ck.wincam_capture(ctx, cam, m, od, seconds=secs, save=save)
    else:
        if not cam.get("ds_path"):
            return None, None, {"api": api, "ok": False, "error": "no DS device path"}
        extra = ["--engine", "ffmpeg"] if api == "ffmpeg_ds" else []
        s, r = ck.pyav_capture(ctx, cam, m, od, seconds=secs, save=save, extra=extra)
    return s, r, None


def _on_fault(ctx, cam, m, api, a, dflt, raw, slug, events, tag):
    """Record a fault; one immediate health check for a hang that is not ERROR_GEN_FAILURE. Returns the active
    fault record, or None if the camera answered again."""
    rec = ck.mark_device_fault(ctx, cam, TEST, m.text, api, a["fault"])
    events.append({"event": "fault", "mode": m.text, "api": api, **a["fault"], "utc": results.utc_now_iso()})
    if a["fault"].get("kind") == "device_error":
        return rec
    pr = ck.health_check(ctx, cam, dflt, raw / slug / f"_health_{tag}", test=TEST,
                         reason=f"{TEST}: after a hang ({a['fault'].get('stage')}, {m.text} {api})")
    events.append({"event": "health_check_after_hang", **pr})
    if pr.get("ok"):
        ck.clear_device_fault(ctx, cam, TEST, pr)
        return None
    return ck.device_fault(ctx, cam) or rec


def _recapture(ctx, cam, m, row, raw, slug, rec_s, dflt, events) -> dict | None:
    """H5: recapture MF and the DS route for ``rec_s`` and use those rates. Returns a fault record or None."""
    route = (row["apis"].get("ds") or {}).get("route")
    out = {}
    for api in ("mf", route):
        if not api:
            continue
        od = raw / slug / f"{api}_{m.slug}_{int(rec_s)}s"
        try:
            s, r, skip = _capture(ctx, cam, m, api, od, rec_s, "none")
            if skip:
                continue
            a = _api_summary("mf" if api == "mf" else "ds", s, r, m, od)
            a.pop("_first", None)
        except Exception as e:  # noqa: BLE001
            out[api] = {"error": repr(e)}
            continue
        out[api] = {k: a.get(k) for k in ("ok", "frames", "fps_steady", "fps_tail_1p5s", "fps_basis",
                                          "cpu_pct_one_core", "cpu_resolution_pct", "error", "out_dir")}
        if a.get("fault"):
            flt = _on_fault(ctx, cam, m, api, a, dflt, raw, slug, events, f"recap_{m.slug}_{api}")
            if flt:
                row["recapture"] = {"seconds": rec_s, "apis": out}
                return flt
    row["recapture"] = {"seconds": rec_s, "apis": out,
                        "reason": f"fps outside {FPS_TOL:.0%} of the reference on {row.get('fps_misses')}"}
    for api, a10 in out.items():
        if not a10.get("ok") or not a10.get("fps_steady"):
            continue
        targets = [api] + (["ds"] if (row["apis"].get("ds") or {}).get("route") == api else [])
        for k in targets:
            a = row["apis"].get(k)
            if a is None:
                continue
            a["fps_steady_short"] = a.get("fps_steady")
            a["fps_tail_short"] = a.get("fps_tail_1p5s")
            a["fps_steady"] = a10["fps_steady"]
            a["fps_tail_1p5s"] = a10.get("fps_tail_1p5s")
            a["fps_source"] = f"{rec_s:g} s recapture"
    return None


def _read_controls(ctx, cam) -> dict:
    try:
        cj, run = ck.get_controls(ctx, cam, "mf")
    except Exception as e:  # noqa: BLE001
        return {"answering": None, "error": repr(e), "utc": results.utc_now_iso()}
    st = ck.control_state(cj)
    st.update(utc=results.utc_now_iso(), rc=run.get("rc"), timed_out=run.get("timed_out"),
              method="wincam controls --api mf --read-only (nothing set)")
    return st


def run(ctx) -> dict:
    res = ck.new_result(ctx, TEST)
    arr0 = ck.arrivals_before(ctx)
    secs = float(ck.arg(ctx, "mjpeg_seconds", 3.0, 1.5))
    rec_s = float(ck.arg(ctx, "mjpeg_recapture_s", RECAPTURE_S, 0.0))
    errors: list = []
    per_cam: dict = {}
    verdicts: dict = {}
    cache: dict = {}
    raw = Path(ctx.raw_dir) / TEST
    ctx.log(f"{TEST}: {len(ctx.cameras)} cameras, {secs:.1f} s per mode and API, recapture {rec_s:g} s, "
            f"quick={ck.quick(ctx)}")
    for cam in ctx.cameras:
        slug = ck.cam_slug(cam)
        modes, info = plan_modes(ctx, cam, cache)
        dflt = info.get("_default")
        ctx.log(f"{TEST}: {ck.cam_label(cam)}: {info['selected']}/{info['advertised']} MJPEG modes "
                f"({info['in_scope']} in scope {info['mode_scope']['scope']['text']}; default "
                f"{info.get('default_mode')} first, low-rate last)")
        if info["advertised"] and not info["in_scope"]:
            # no in-scope MJPEG mode: recorded, rated untested (scope), nothing streamed
            why = info["mode_scope"].get("untested_reason") or "no in-scope MJPEG mode"
            for api in ("mf", "ds", "pyav_ds"):
                verdicts[f"G-MJPEG|{cam['key']}|{api}"] = ck.scope_untested(ctx, info["mode_scope"])
            per_cam[cam["key"]] = {"name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"),
                                   "modes_info": {k: v for k, v in info.items() if not k.startswith("_")},
                                   "mode_scope": info["mode_scope"], "skipped": why, "modes": []}
            ctx.log(f"{TEST}: {ck.cam_label(cam)}: {why}")
            continue
        activity = None
        events: list = []
        fault = ck.device_fault(ctx, cam)
        start_probe = None
        if fault and ck._has_gate(ctx) and ck.device_gated(ctx, cam):
            # the runner re-probed this camera once at the start of the test (ctx.begin_test) and it did not answer
            events.append({"event": "gated_at_start", "fault_since": fault.get("utc"),
                           "fault_test": fault.get("test")})
            ctx.log(f"{TEST}: {ck.cam_label(cam)}: untested, device fault since {fault.get('utc')} "
                    f"({fault.get('test')}); the start-of-test re-probe did not answer")
        elif fault:
            start_probe = ck.health_check(ctx, cam, dflt, raw / slug / "_health_start", test=TEST,
                                          reason=f"{TEST}: camera carries a fault from {fault.get('test')}")
            events.append({"event": "health_check_at_start", "fault_since": fault.get("utc"), **start_probe})
            if start_probe.get("ok"):
                ck.clear_device_fault(ctx, cam, TEST, start_probe)
                fault = None
            else:
                fault = ck.device_fault(ctx, cam) or fault
                ctx.log(f"{TEST}: {ck.cam_label(cam)}: untested, device fault since {fault.get('utc')} "
                        f"({fault.get('test')}); health check did not answer")
        controls_before = _read_controls(ctx, cam) if not fault and cam.get("mf_symlink") else None
        mode_rows: list = []
        n_recap = 0
        for idx, m in enumerate(modes):
            if fault:
                mode_rows.append({"mode": m.text, "mode_detail": m.as_dict(), "apis": {},
                                  "skipped": f"untested: device fault since {fault.get('utc')}"})
                continue
            if activity is None:
                # who else uses this camera right before its first stream (IMFSensorActivityMonitor; opens nothing)
                activity = ck.activity_for_camera(ctx, cam)
            row = {"mode": m.text, "mode_detail": m.as_dict(), "apis": {}, "order_index": idx}
            secs_m = max(secs, CPU_WINDOW_S) if (m == dflt and not ck.quick(ctx)) else secs
            if secs_m != secs:
                row["seconds"] = secs_m
            every = save_every(m, secs_m)
            for api in ("mf", "pyav_ds", "ffmpeg_ds"):
                if api == "ffmpeg_ds" and not (row["apis"].get("pyav_ds") or {}).get("format_fallback"):
                    continue  # the ffmpeg CLI route runs only where PyAV could not get MJPEG
                od = raw / slug / f"{api}_{m.slug}"
                try:
                    s, r, skip = _capture(ctx, cam, m, api, od, secs_m, f"every:{every}")
                    if skip:
                        row["apis"][api] = skip
                        continue
                    a = _api_summary("mf" if api == "mf" else "ds", s, r, m, od)
                    a["api"] = api
                except Exception as e:  # noqa: BLE001
                    errors.append({"camera": cam["key"], "mode": m.text, "api": api, "exception": repr(e)})
                    a = {"api": api, "ok": False, "error": repr(e)}
                first = a.pop("_first", None)
                if dflt is not None and m == dflt and first and api != "ffmpeg_ds":
                    a["sample"] = ck.save_sample(ctx, TEST, cam, f"{api}_{m.slug}", first)
                row["apis"][api] = a
                if not a.get("ok") and not a.get("format_fallback"):
                    ck.note_first_failure(ctx, cam, TEST, m.text, api, (a.get("classification") or {}).get("code_hex")
                                          or (a.get("classification") or {}).get("code"),
                                          (a.get("classification") or {}).get("class"))
                if a.get("fault"):
                    fault = _on_fault(ctx, cam, m, api, a, dflt, raw, slug, events, f"{m.slug}_{api}")
                    if fault:
                        break
            finish_mode_row(row, m)
            if fault:
                row["device_fault_here"] = True
            elif row["fps_misses"] and rec_s > 0 and n_recap < RECAPTURE_MAX_PER_CAMERA:
                n_recap += 1
                fault = _recapture(ctx, cam, m, row, raw, slug, rec_s, dflt, events)
                finish_mode_row(row, m)
            elif row["fps_misses"] and rec_s > 0:
                row["recapture"] = {"skipped": f"recapture budget ({RECAPTURE_MAX_PER_CAMERA}) used"}
            mode_rows.append(row)
            mf, ds = row["apis"].get("mf", {}), row["apis"].get("ds", {})
            ctx.log(f"{TEST}: {cam.get('name')} {m.text}: MF ok={mf.get('ok')} {mf.get('fps_steady') or 0:.1f} fps"
                    f" strict={mf.get('strict_ok_fraction')} | DS ok={ds.get('ok')} {ds.get('fps_steady') or 0:.1f} "
                    f"fps strict={ds.get('strict_ok_fraction')} | ref {row['fps_reference']:.2f} "
                    f"({row['fps_reference_basis']}) | hdr_eq={row['header_sha1_equal']}"
                    + (" | RECAPTURED" if row.get("recapture", {}).get("apis") else ""))
        controls_after = _read_controls(ctx, cam) if not fault and cam.get("mf_symlink") else None
        cam_verdicts = rate_camera(cam["key"], mode_rows, info, fault)
        verdicts.update(cam_verdicts)
        per_cam[cam["key"]] = camera_summary(
            cam, info, mode_rows, cam_verdicts, events=events, health_check_at_start=start_probe,
            device_fault=fault, recaptured=n_recap, mode_scope=info.get("mode_scope"),
            activity_at_first_stream=activity,
            control_state={"before": controls_before, "after": controls_after,
                           "note": "read only; W-MJPEG never sets a control (mjpeg_fmt.md H4)"},
            first_failure=ck.first_failure(ctx, cam))
    meas = {"mode_scope": ck.mode_scope(ctx).as_dict(),
            "seconds_per_mode": secs, "default_mode_seconds": None if ck.quick(ctx) else max(secs, CPU_WINDOW_S),
            "recapture_seconds": rec_s, "quick": ck.quick(ctx), "decoders": jpegcheck.decoders_available(),
            "raw_dir": str(raw), "cameras": per_cam, "arrivals": ck.arrivals_after(ctx, arr0),
            "device_faults": (ctx.fault_report() if callable(getattr(ctx, "fault_report", None))
                              else getattr(ctx, "device_faults", None)),
            "note": ("cameras and modes run one at a time; default mode first, low-rate modes last; fps_steady skips "
                     "the first 15% of frames; 8 frames decoded per mode, spread across the capture")}
    return results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)


# ============================================================================================================ offline
def _mode_of(row: dict) -> ck.Mode:
    d = row["mode_detail"]
    return ck.Mode(int(d["width"]), int(d["height"]), int(d["fps_num"]), int(d["fps_den"]), d.get("subtype", "MJPG"))


def _ctrl_list_state(run_dir: Path, cam: dict) -> dict | None:
    """Run-start control state from W-CTRL-LIST's raw MF controls JSON (the 20261106 W-MJPEG recorded none)."""
    d = run_dir / "W-CTRL-LIST"
    if not d.is_dir():
        return None
    tag = f"{cam.get('vid')}-{cam.get('pid')}"
    for f in sorted(d.glob(f"*{tag}*_controls_mf.json")):
        try:
            st = ck.control_state(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        st["source"] = f"{f.relative_to(run_dir)} (W-CTRL-LIST at run start, not read by W-MJPEG)"
        return st
    return None


def reanalyse(run_dir: str | Path, raw_dir: str | Path | None = None, out: str | Path | None = None) -> dict:
    """Re-rate a stored W-MJPEG run with the fixed rules, no camera: symmetric tier-0 fps reference (H1), 0
    frames = no JPEG (H2), device fault -> untested and modes after it flagged (H3), decode sample spread over the
    saved frames (H6, re-decoded from raw_dir), rate_honoured and the raw-fallback control rates (M3), rating_failed_modes (H9). Not recoverable offline: 10 s recaptures (H5), ffmpeg-route CPU
    (H8), the control state at W-MJPEG time (H4; W-CTRL-LIST's run-start state is attached instead)."""
    run_dir = Path(run_dir)
    src = json.loads((run_dir / f"{TEST}.json").read_text(encoding="utf-8"))
    meas = src.get("measurements") or {}
    raw = Path(raw_dir) / TEST if raw_dir else Path(meas.get("raw_dir") or "")
    cams_meta = {c.get("key"): c for c in src.get("cameras") or []}
    per_cam, verdicts, missing = {}, {}, []
    for key, c in (meas.get("cameras") or {}).items():
        cam = dict(cams_meta.get(key) or {}, key=key, name=c.get("name"), is_kiyo=c.get("is_kiyo"))
        info = dict(c.get("modes_info") or {})
        info["default_mode"] = c.get("default_mode")
        rows, fault = [], None
        stored_fault = c.get("device_fault") if isinstance(c.get("device_fault"), dict) else None
        for old_row in c.get("modes") or []:
            m = _mode_of(old_row)
            row = {"mode": old_row["mode"], "mode_detail": old_row["mode_detail"], "apis": {}}
            if old_row.get("skipped"):
                # gated / after a device fault in the original run: nothing to re-analyse, still not "captured"
                row["skipped"] = old_row["skipped"]
                if fault is None and stored_fault:
                    fault = dict(stored_fault)
            for api in ("mf", "pyav_ds", "ffmpeg_ds"):
                old = (old_row.get("apis") or {}).get(api)
                if not old:
                    continue
                od = Path(old.get("out_dir") or (raw / ck.cam_slug(cam) / f"{api}_{m.slug}"))
                if raw_dir and old.get("out_dir"):
                    od = raw / Path(old["out_dir"]).parent.name / Path(old["out_dir"]).name
                summ = None
                try:
                    summ = json.loads((od / "summary.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    missing.append(str(od))
                if summ is None:
                    a = {k: v for k, v in old.items()}
                    a["reanalysis_note"] = "raw summary missing: stored values kept"
                else:
                    a = _api_summary("mf" if api == "mf" else "ds", summ,
                                     {"rc": old.get("rc"), "timed_out": old.get("timed_out")}, m, od)
                    a.pop("_first", None)
                    if old.get("sample"):
                        a["sample"] = old["sample"]
                a["api"] = api
                row["apis"][api] = a
                if fault is None and a.get("fault"):
                    fault = {"utc": a.get("utc_finished") or a.get("utc_started"), "test": TEST, "mode": m.text,
                             "api": api, "capture_started_utc": a.get("utc_started"), **a["fault"]}
                    row["device_fault_here"] = True
                elif fault is not None and not row.get("device_fault_here"):
                    row["after_device_fault"] = True
            finish_mode_row(row, m)
            rows.append(row)
        if fault:
            codes: dict = {}
            for r_ in rows:
                if r_.get("after_device_fault"):
                    for a_ in r_["apis"].values():
                        c_ = (a_.get("classification") or {})
                        k_ = f"{a_.get('api')}:{c_.get('code_hex') or c_.get('code')}"
                        codes[k_] = codes.get(k_, 0) + 1
            fault["codes_after_fault"] = codes
        cv = rate_camera(key, rows, info, fault)
        verdicts.update(cv)
        per_cam[key] = camera_summary(cam, info, rows, cv, device_fault=fault,
                                      control_state={"before": None, "after": None,
                                                     "run_start_from_w_ctrl_list": _ctrl_list_state(run_dir, cam),
                                                     "note": "W-MJPEG 20261106 did not read controls; nothing was "
                                                             "ever set"})
    changes = []
    for k, v in verdicts.items():
        o = (src.get("verdicts") or {}).get(k) or {}
        changes.append({"cell": k, "original": o.get("rating"), "reanalysed": v.get("rating"),
                        "changed": o.get("rating") != v.get("rating"), "note": v.get("note")})
    doc = {"test": TEST, "kind": "offline re-analysis (no camera opened)", "utc": results.utc_now_iso(),
           "source": str(run_dir / f"{TEST}.json"), "raw_dir": str(raw),
           "fixes_applied": ["H1 symmetric tier-0 fps reference (APIs agree, else nominal), rate_honoured separate",
                             "H2 0 frames = no JPEG bytes (rates 'no' only without a device fault)",
                             "H3 device fault -> untested 'device fault, replug needed'; modes after it flagged",
                             "H6 decode sample spread across all saved frames (re-decoded from raw)",
                             "H9 rating_failed_modes / tool_failed_modes",
                             "M3 PyAV raw-fallback rate as a control experiment"],
           "not_recoverable_offline": ["H5 10 s recaptures (needs cameras)", "H8 ffmpeg-route CPU",
                                       "H4 control state at W-MJPEG time (W-CTRL-LIST run-start state attached)",
                                       "low-rate-last sweep order (the run swept by size)"],
           "rating_changes": changes, "missing_raw": missing[:50],
           "decoders": jpegcheck.decoders_available(),
           "measurements": {"cameras": per_cam}, "verdicts": verdicts}
    out = Path(out) if out else run_dir / "reanalysis" / f"{TEST}.json"
    results.write_json(out, doc)
    return doc


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="W-MJPEG offline re-analysis (no camera)")
    ap.add_argument("--reanalyse", required=True, help="run folder holding W-MJPEG.json")
    ap.add_argument("--raw-dir", help="raw run folder (default: measurements.raw_dir of the run)")
    ap.add_argument("--out", help="output file (default <run>/reanalysis/W-MJPEG.json)")
    a = ap.parse_args(argv)
    doc = reanalyse(a.reanalyse, a.raw_dir, a.out)
    for ch in doc["rating_changes"]:
        print(f"{ch['cell']}: {ch['original']} -> {ch['reanalysed']}" + ("  (changed)" if ch["changed"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
