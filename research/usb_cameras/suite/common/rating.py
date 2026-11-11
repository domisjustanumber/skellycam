"""Rating thresholds of docs/xplat_capture_plan.md section 3 (proposed; Dom to confirm). Stdlib only.

Every function returns {"rating": "yes"|"partial"|"no"|"untested", "criteria": [{"criterion", "met", "detail"}],
"evidence": {...}} so a result JSON carries the criterion AND the evidence behind each verdict. ``met`` is True,
False or None (not measured). Inputs are plain measurements; the tests compute them.

| Goal | Yes | Partial | No |
| G-ID | every API's list maps 1:1 to camera_identity keys, identical over 20 repeated enumerations; key unchanged over
         reboot and same-port replug (serial cameras also over a port move) | maps 1:1 but changes on reboot or
         replug, or only some APIs expose a mappable path | index or name only |
| G-TS | causal per-frame error <= 0.5 ms (1 sigma) against a ground truth, and drops detectable | <= 2 ms, or tier 1
         only, or no ground truth yet but self-consistent device timestamps | > 2 ms, synthesized, or a host-time
         grid (Windows 16 ms) |
| G-MJPEG | every advertised MJPEG mode negotiates, delivers >= 99% valid JPEG (strict decode, or lenient with a known
         camera quirk noted), SOF0 size = request, fps within 2% of the camera's real rate, header SHA-1 equal
         across APIs | some modes fail, or decode is lenient-only without a known quirk | no JPEG bytes |
| G-CTRL | every control in the descriptors is listed with the descriptor's range; set + readback agree; the effect
         shows in the image (exposure, gain, WB, focus); works before and after stream start; 3/3 runs | needs a
         workaround (e.g. re-apply after start), or works on some cameras only | cannot set |
| Reliability | >= 99% of cycles deliver a first frame within 2 s; no hang beyond the watchdog; no state that needs a
         replug | 95-99%, or recoverable hangs | < 95%, or a replug needed |
| G-BW | the mapper predicts every observed refusal (no false "fits" verdicts); refusal classified correctly; the
         message lists only ports in other domains; retry after a refusal works | predictions right but labels raw,
         or classification ambiguous on one API | refusals not detected or misattributed |
| FMT-NOGRAB (per format-listing method, 2026-11-06) | complete vs the USB descriptors (MJPEG and raw) in all three
         conditions (idle, streaming in another process via the native API, via the second API), no disturbance of
         the other stream, no stream / bandwidth, no blocking | complete when idle only, or disturbs / blocks (or a
         condition / measurement missing: provisional) | incomplete when idle, or needs a stream |

Shared rating contract (2026-11-06, after the suite_20261106T181941Z analyses and their verifiers):
  * a device fault (0x8007001F / unreleasable reader, "replug needed") is never an API result: G-MJPEG with
    ``device_fault`` and reliability with ``pre_existing_fault`` rate 'untested'; ``device_fault_untested`` builds
    the "untested: device fault since <ts>" verdict the dead-device gate uses;
  * G-MJPEG 'no' = no JPEG frame in any mode without a device fault; the fps criterion uses a symmetric tier-0
    reference (the rate both APIs agree on, else nominal; no device-clock rate since Dom's tier-0-only decision of
    2026-11-09) and ``rate_honoured`` (measured vs nominal) is recorded per mode as camera behaviour, outside the
    rating;
  * reliability evidence carries n / n_ok / success_rate / wilson95 / p50 open_to_first_frame_ms and the format,
    fps and size mismatch counts; a format or size mismatch caps the rating at partial; ``summary_label``
    distinguishes 'no (latency)' from 'no (failures)';
  * G-TS: device timestamps that are not self-consistent -> 'untested', non-monotonic -> 'no';
  * G-BW: ``device_not_ready`` events are excluded from false fits / misattribution and counted separately;
    ``retry_ok`` is the final try; "predicted over but every camera streamed" is a criterion (false over); raw labels
    follow ``topology_model.label_tier`` (only ACPI names / location paths are raw);
  * G-CTRL: ``device_not_answering`` -> 'no' (cannot set) with the HRESULT; criterion 1 needs ``listed`` and
    ``range_matches_descriptor`` from W-CTRL-LIST (None = not fed, which blocks 'yes').
"""
from __future__ import annotations

import re
from typing import Any, Iterable

RATINGS = ("yes", "partial", "no", "untested")
_ORDER = {"no": 0, "partial": 1, "yes": 2}


def _crit(criterion: str, met: bool | None, detail: Any = None) -> dict[str, Any]:
    return {"criterion": criterion, "met": met, "detail": detail}


def _result(rating: str, criteria: list[dict], evidence: Any, note: str | None = None) -> dict[str, Any]:
    r = {"rating": rating, "criteria": criteria, "evidence": evidence}
    if note:
        r["note"] = note
    return r


def untested(reason: str, evidence: Any = None) -> dict[str, Any]:
    """A verdict for a goal the run could not measure."""
    return _result("untested", [_crit("measured", None, reason)], evidence)


def device_fault_untested(fault: dict[str, Any] | None = None, reason: str | None = None,
                          evidence: Any = None) -> dict[str, Any]:
    """'untested: device fault since <ts>' for camera work skipped (or invalidated) by a device fault.
    fault: {"first_fault_utc"|"utc", "test", "mode", "code"|"fault_code", ...} as the dead-device gate records it."""
    f = dict(fault or {})
    ts = f.get("first_fault_utc") or f.get("utc") or f.get("since")
    code = f.get("fault_code") or f.get("code")
    why = reason or (f"device fault since {ts}" if ts else "device fault") + ", replug needed"
    where = ", ".join(str(x) for x in (f.get("test"), f.get("mode"), code) if x)
    ev = {"device_fault": True, "fault_code": code, "first_fault_utc": ts, "fault": f or None}
    if isinstance(evidence, dict):
        ev.update({k: v for k, v in evidence.items() if k not in ev or ev[k] is None})
    elif evidence is not None:
        ev["detail"] = evidence
    r = _result("untested", [_crit("measured", None, why + (f" ({where})" if where else ""))], ev,
                why + (f" ({where})" if where else ""))
    r["summary_label"] = "untested (device fault)"
    return r


def worst(ratings: Iterable[dict | str]) -> str:
    """Worst rating among tested ones ('untested' only if none was tested)."""
    vals = [r["rating"] if isinstance(r, dict) else r for r in ratings]
    tested = [v for v in vals if v in _ORDER]
    if not tested:
        return "untested"
    return min(tested, key=lambda v: _ORDER[v])


# ---------------------------------------------------------------------------------------------------- G-ID
def rate_id(api_runs: dict[str, list[list[str | None]]], expected_keys: Iterable[str],
            persistence: dict[str, bool | None] | None = None, min_runs: int = 20) -> dict[str, Any]:
    """api_runs: {api: [run1_keys_in_list_order, run2, ...]} where each entry is the camera_identity key that API
    entry maps to (None = not mappable: index/name only). expected_keys: keys of the USB cameras present.
    persistence: {"reboot": bool|None, "same_port_replug": bool|None, "port_move_serial": bool|None} from the
    attended steps (A1); None = not run yet. Unmeasured persistence stays 'partial' with ``provisional`` True (the
    plan's yes needs the persistence steps; ctrl_id_env B8 verifier)."""
    exp = set(expected_keys)
    per_api = {}
    for api, runs in api_runs.items():
        mappable = bool(runs) and all(all(k is not None for k in run) for run in runs)
        one_to_one = bool(runs) and all(len(run) == len(set(run)) and set(run) == exp for run in runs)
        stable = bool(runs) and all(run == runs[0] for run in runs)
        per_api[api] = {"runs": len(runs), "mappable": mappable, "one_to_one": one_to_one, "stable_order": stable,
                        "first_run": runs[0] if runs else None}
    n_map = sum(1 for a in per_api.values() if a["mappable"] and a["one_to_one"])
    all_ok = bool(per_api) and n_map == len(per_api)
    enough = bool(per_api) and all(a["runs"] >= min_runs for a in per_api.values())
    all_stable = bool(per_api) and all(a["stable_order"] for a in per_api.values())
    pers = persistence or {}
    pers_vals = [pers.get(k) for k in ("reboot", "same_port_replug", "port_move_serial")]
    pers_ok = all(v is True for v in pers_vals)
    pers_bad = any(v is False for v in pers_vals)
    crit = [_crit("every API's list maps 1:1 to identity keys", all_ok, f"{n_map}/{len(per_api)} APIs"),
            _crit(f"identical over >= {min_runs} repeated enumerations", (all_stable and enough) if per_api else None,
                  {a: v["runs"] for a, v in per_api.items()}),
            _crit("key unchanged over reboot / same-port replug / port move (serial cameras)",
                  True if pers_ok else (False if pers_bad else None), pers)]
    ev = {"per_api": per_api, "expected_keys": sorted(exp)}
    if not per_api:
        return untested("no API enumeration recorded", ev)
    if n_map == 0:
        return _result("no", crit, ev, "no API exposes a mappable path (index or name only)")
    if all_ok and all_stable and enough and pers_ok:
        return _result("yes", crit, ev)
    note = None
    provisional = False
    if all_ok and all_stable and enough and not pers_bad:
        note = "provisional yes: attended persistence steps (A1: reboot, replug, port move) not run yet"
        provisional = True
    r = _result("partial", crit, ev, note)
    r["provisional"] = provisional
    if provisional:
        r["summary_label"] = "partial (provisional: persistence not measured)"
    return r


# ---------------------------------------------------------------------------------------------------- G-TS
def rate_ts(causal_error_ms_1sigma: float | None, drops_detectable: bool | None, ground_truth: bool,
            tier: int = 0, synthesized: bool = False, host_grid_ms: float | None = None,
            device_ts_self_consistent: bool | None = None,
            device_ts_monotonic: bool | None = None) -> dict[str, Any]:
    """causal_error_ms_1sigma: causal per-frame error std vs ground truth (None without ground truth).
    synthesized: timestamps made up by the API (e.g. DirectShow/PyAV synthesized pts). host_grid_ms: quantisation
    step found by tsanalysis.grid_analysis on the timestamp (>= ~1 ms at video rates means a host-time grid).
    device_ts_self_consistent: device PTS present, monotonic, fits the host clock with low residual; False ->
    'untested' (plan: partial needs self-consistent device timestamps). device_ts_monotonic: False -> 'no'."""
    ev = {"causal_error_ms_1sigma": causal_error_ms_1sigma, "drops_detectable": drops_detectable,
          "ground_truth": ground_truth, "tier": tier, "synthesized": synthesized, "host_grid_ms": host_grid_ms,
          "device_ts_self_consistent": device_ts_self_consistent, "device_ts_monotonic": device_ts_monotonic}
    grid_bad = host_grid_ms is not None and host_grid_ms >= 4.0
    crit = [_crit("causal per-frame error <= 0.5 ms (1 sigma) vs ground truth",
                  None if causal_error_ms_1sigma is None else causal_error_ms_1sigma <= 0.5, causal_error_ms_1sigma),
            _crit("drops detectable", drops_detectable, None),
            _crit("tier 0 (no admin configuration)", tier == 0, tier),
            _crit("not synthesized and not on a host-time grid", not (synthesized or grid_bad),
                  {"synthesized": synthesized, "host_grid_ms": host_grid_ms})]
    if device_ts_monotonic is not None or device_ts_self_consistent is not None:
        crit.append(_crit("device timestamps monotonic and self-consistent",
                          False if (device_ts_monotonic is False or device_ts_self_consistent is False)
                          else (True if device_ts_self_consistent else None),
                          {"monotonic": device_ts_monotonic, "self_consistent": device_ts_self_consistent}))
    if synthesized or grid_bad or (causal_error_ms_1sigma is not None and causal_error_ms_1sigma > 2.0):
        return _result("no", crit, ev)
    if device_ts_monotonic is False:
        return _result("no", crit, ev, "device timestamps not monotonic")
    if ground_truth and causal_error_ms_1sigma is not None:
        if causal_error_ms_1sigma <= 0.5 and drops_detectable and tier == 0:
            return _result("yes", crit, ev)
        return _result("partial", crit, ev)
    if device_ts_self_consistent is False:
        return _result("untested", crit, ev, "device timestamps not self-consistent")
    if device_ts_self_consistent:
        return _result("partial", crit, ev, "no ground truth yet; device timestamps self-consistent")
    if causal_error_ms_1sigma is None and device_ts_self_consistent is None:
        return untested("no ground truth and no device timestamps evaluated", ev)
    return _result("partial", crit, ev, "no ground truth; self-consistency not shown")


# ---------------------------------------------------------------------------------------------------- G-MJPEG
_MODE_FPS = re.compile(r"@\s*([0-9]+(?:\.[0-9]+)?)")


def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 else None


def _nominal_fps(m: dict[str, Any]) -> float | None:
    v = _num(m.get("fps_nominal"))
    if v is None:
        mm = _MODE_FPS.search(str(m.get("mode") or ""))
        v = float(mm.group(1)) if mm else None
    return v


def fps_reference(m: dict[str, Any], fps_tol: float = 0.02) -> tuple[float | None, str | None]:
    """(reference fps, source) for one G-MJPEG mode row, symmetric in direction, tier 0 only (Dom 2026-11-09: no
    device-clock rate; a ``fps_uvc_pts`` / ``fps_pts`` field is ignored):
    1. ``fps_other_api``: the rate measured through the other API; when it agrees with ``fps_measured`` within
       ``fps_tol`` (either direction) the camera's real rate is their mean;
    2. ``fps_expected``: a caller-supplied reference (legacy);
    3. the nominal rate (``fps_nominal`` or the '@<fps>' in ``mode``)."""
    fm, fo = _num(m.get("fps_measured")), _num(m.get("fps_other_api"))
    if fm is not None and fo is not None and abs(fm - fo) / max(fm, fo) <= fps_tol:
        return (fm + fo) / 2.0, "both_apis_agree"
    fe = _num(m.get("fps_expected"))
    if fe is not None:
        return fe, "caller"
    nom = _nominal_fps(m)
    return (nom, "nominal") if nom is not None else (None, None)


def _no_frames(m: dict[str, Any]) -> bool:
    """True when the row says the mode delivered no frame (frames 0 / None given explicitly)."""
    return "frames" in m and not m.get("frames")


def rate_mjpeg(modes: list[dict[str, Any]], jpeg_bytes: bool | None = None,
               min_valid: float = 0.99, fps_tol: float = 0.02, device_fault: bool | None = None,
               fault_code: Any = None, first_fault_utc: str | None = None) -> dict[str, Any]:
    """modes: one dict per advertised MJPEG mode: {mode, negotiated (bool), frames, strict_valid_fraction,
    lenient_valid_fraction, known_quirk (str|None), sof_matches (bool), fps_measured, fps_other_api (the same mode's
    rate through the other API), fps_nominal, fps_expected (legacy explicit reference), header_sha1_by_api ({api: sha1}|None), is_jpeg (bool)} (see ``fps_reference``).
    jpeg_bytes: False if the path delivered decoded pixels (no JPEG bytes at all).
    device_fault: the camera hit a device fault (0x8007001F, unreleasable reader) in this test -> 'untested'
    ('device fault, replug needed'): a dead camera says nothing about the API. Without a fault, no JPEG frame in
    any mode -> 'no'. ``rate_honoured`` (measured within fps_tol of nominal) is recorded per mode as camera
    behaviour and does not change the rating."""
    rows = []
    for m in modes:
        neg = bool(m.get("negotiated"))
        strict = m.get("strict_valid_fraction")
        lenient = m.get("lenient_valid_fraction")
        quirk = m.get("known_quirk")
        valid_ok = (strict is not None and strict >= min_valid) or \
                   (quirk and lenient is not None and lenient >= min_valid)
        lenient_only = (not (strict is not None and strict >= min_valid)) and lenient is not None \
            and lenient >= min_valid
        fm = _num(m.get("fps_measured"))
        ref, src = fps_reference(m, fps_tol)
        fps_ok = None if (fm is None or not ref) else abs(fm - ref) / ref <= fps_tol
        nom = _nominal_fps(m)
        honoured = None if (fm is None or nom is None) else abs(fm - nom) / nom <= fps_tol
        # a measured reference (the rate the APIs agree on) cannot fail the fps criterion by construction; flag it
        # when it sits > fps_tol off nominal (camera behaviour or a host cause common to both APIs)
        tier0_ref = src in ("both_apis_agree", "caller")
        ref_off = None if (not tier0_ref or not ref or nom is None) else abs(ref - nom) / nom > fps_tol
        hashes = m.get("header_sha1_by_api") or {}
        hash_ok = None if len(hashes) < 2 else len(set(hashes.values())) == 1
        ok = neg and valid_ok and m.get("sof_matches") is True and fps_ok is not False and hash_ok is not False
        rows.append({"mode": m.get("mode"), "negotiated": neg, "valid_ok": bool(valid_ok),
                     "lenient_only": lenient_only, "known_quirk": quirk, "sof_matches": m.get("sof_matches"),
                     "fps_ok": fps_ok, "fps_reference": ref, "fps_reference_source": src,
                     "tier0_reference_off_nominal": ref_off,
                     "rate_honoured": honoured, "header_equal_across_apis": hash_ok, "ok": bool(ok),
                     "frames": m.get("frames"), "is_jpeg": m.get("is_jpeg")})
    srcs: dict[str, int] = {}
    for r in rows:
        srcs[str(r["fps_reference_source"])] = srcs.get(str(r["fps_reference_source"]), 0) + 1
    ev = {"modes": rows, "fps_reference_sources": srcs,
          "rate_honoured": {"true": sum(r["rate_honoured"] is True for r in rows),
                            "false": sum(r["rate_honoured"] is False for r in rows),
                            "unknown": sum(r["rate_honoured"] is None for r in rows),
                            "not_honoured_modes": [r["mode"] for r in rows if r["rate_honoured"] is False],
                            "note": "camera behaviour (requested rate not delivered), not an API failure; "
                                    "not part of the G-MJPEG rating"},
          "tier0_reference_off_nominal_modes": [r["mode"] for r in rows if r["tier0_reference_off_nominal"]]}
    if device_fault:
        ev.update(device_fault=True, fault_code=fault_code, first_fault_utc=first_fault_utc)
        r = _result("untested", [_crit("measured", None, "device fault, replug needed"),
                                 _crit("camera answered (no device fault)", False,
                                       {"fault_code": fault_code, "first_fault_utc": first_fault_utc})],
                    ev, "device fault, replug needed" + (f" ({fault_code} since {first_fault_utc})"
                                                         if fault_code or first_fault_utc else ""))
        r["summary_label"] = "untested (device fault)"
        return r
    any_jpeg = any(m.get("is_jpeg") is True for m in modes)
    no_jpeg_anywhere = bool(modes) and not any_jpeg and all(m.get("is_jpeg") is False or _no_frames(m)
                                                            for m in modes)
    if jpeg_bytes is False or no_jpeg_anywhere:
        detail = ("path delivers decoded pixels" if jpeg_bytes is False else
                  f"0 JPEG frames in {len(modes)}/{len(modes)} modes "
                  f"({sum(_no_frames(m) for m in modes)} with no frame at all)")
        return _result("no", [_crit("delivers JPEG bytes", False, detail)], ev)
    if not modes:
        return untested("no MJPEG mode captured", ev)
    n_ok = sum(r["ok"] for r in rows)
    crit = [_crit("every advertised mode negotiates", all(r["negotiated"] for r in rows),
                  f"{sum(r['negotiated'] for r in rows)}/{len(rows)}"),
            _crit(f">= {min_valid:.0%} valid JPEG (strict, or lenient with a known quirk)",
                  all(r["valid_ok"] for r in rows), f"{sum(r['valid_ok'] for r in rows)}/{len(rows)}"),
            _crit("SOF0 size = request", all(r["sof_matches"] is True for r in rows), None),
            _crit(f"fps within {fps_tol:.0%} of the camera's real rate (symmetric reference: the rate both APIs "
                  "agree on, else nominal)",
                  None if all(r["fps_ok"] is None for r in rows) else all(r["fps_ok"] is not False for r in rows),
                  {"failing_modes": [r["mode"] for r in rows if r["fps_ok"] is False], "reference_sources": srcs}),
            _crit("JPEG header SHA-1 equal across APIs",
                  None if all(r["header_equal_across_apis"] is None for r in rows)
                  else all(r["header_equal_across_apis"] is not False for r in rows), None)]
    n_not_hon = sum(r["rate_honoured"] is False for r in rows)
    off = ev["tier0_reference_off_nominal_modes"]
    off_note = (f"tier-0 fps reference (the rate both APIs agree on) is > {fps_tol:.0%} off nominal in {len(off)} "
                "mode(s): camera behaviour (e.g. auto-exposure) or a host cause common to both APIs") if off else None
    label = f" (rate not honoured in {n_not_hon})" if n_not_hon else ""
    if n_ok == len(rows) and all(r["fps_ok"] is not None for r in rows) \
            and all(r["header_equal_across_apis"] is not None for r in rows):
        r = _result("yes", crit, ev, off_note)
        r["summary_label"] = "yes" + label
        return r
    note = None
    if n_ok == len(rows):
        note = "all modes pass what was measured; fps reference or cross-API header comparison missing"
    r = _result("partial", crit, ev, "; ".join(x for x in (note, off_note) if x) or None)
    r["summary_label"] = "partial" + label
    return r


# ---------------------------------------------------------------------------------------------------- G-CTRL
EFFECT_CONTROLS = ("exposure", "gain", "white_balance", "focus")


def rate_ctrl(controls: list[dict[str, Any]], can_set_any: bool | None = None,
              runs_required: int = 3, device_not_answering: bool | None = None,
              not_answering_hr: Any = None) -> dict[str, Any]:
    """controls: one dict per (camera, control path, control): {name, listed (bool|None: W-CTRL-LIST listed it with
    descriptor support), range_matches_descriptor (bool|None: W-CTRL-LIST MF and DS ranges equal), set_readback_ok
    (bool|None), effect_ok (bool|None; required for exposure/gain/white_balance/focus), before_start_ok,
    after_start_ok (bool|None), runs_ok (int), runs_total (int), workaround (str|None)}.
    device_not_answering: every control GET failed (the camera is in a fault state) -> 'no' (cannot set) with
    ``not_answering_hr`` as evidence; the plan rates a Kiyo failure as a result, not as untested."""
    ev: dict[str, Any] = {"controls": controls}
    if device_not_answering:
        ev.update(device_not_answering=True, not_answering_hr=not_answering_hr)
        r = _result("no", [_crit("can set a control", False,
                                 {"device_not_answering": True, "hr": not_answering_hr})], ev,
                    f"cannot set: device not answering ({not_answering_hr})" if not_answering_hr
                    else "cannot set: device not answering")
        r["summary_label"] = "no (device not answering)"
        return r
    if not controls:
        return untested("no control measured", ev)
    any_set = can_set_any if can_set_any is not None else any(c.get("set_readback_ok") for c in controls)
    if not any_set:
        return _result("no", [_crit("can set a control", False)], ev)

    def all_true(key: str, subset=None) -> bool | None:
        vals = [c.get(key) for c in (subset if subset is not None else controls)]
        if all(v is None for v in vals):
            return None
        return all(v is True for v in vals)

    eff = [c for c in controls if any(e in str(c.get("name", "")).lower().replace(" ", "_")
                                      for e in EFFECT_CONTROLS)]
    runs_ok = all((c.get("runs_ok") or 0) >= runs_required and (c.get("runs_total") or 0) >= runs_required
                  and c.get("runs_ok") == c.get("runs_total") for c in controls)
    listed, ranges = all_true("listed"), all_true("range_matches_descriptor")
    crit1 = None if (listed is None or ranges is None) else bool(listed and ranges)
    crit = [_crit("every control listed with descriptor support (CTRL-LIST: listed, and the range check passed: "
                  "Windows MF and DS ranges equal; Linux / macOS a consistent GET_MIN/MAX/RES/DEF range)",
                  crit1, {"listed": listed, "ranges_equal": ranges}),
            _crit("set + readback agree", all_true("set_readback_ok"), None),
            _crit("effect shows in the image (exposure, gain, WB, focus)", all_true("effect_ok", eff) if eff else None,
                  [c.get("name") for c in eff]),
            _crit("works before and after stream start",
                  None if all_true("before_start_ok") is None and all_true("after_start_ok") is None
                  else bool(all_true("before_start_ok") and all_true("after_start_ok")), None),
            _crit(f"{runs_required}/{runs_required} runs", runs_ok, None),
            _crit("no workaround needed", not any(c.get("workaround") for c in controls),
                  [c.get("workaround") for c in controls if c.get("workaround")])]
    if all(c["met"] is True for c in crit):
        return _result("yes", crit, ev)
    return _result("partial", crit, ev)


# ---------------------------------------------------------------------------------------------------- reliability
def _p50(timings: dict | None, *keys: str) -> float | None:
    for k in keys:
        v = ((timings or {}).get(k) or {}).get("p50")
        if isinstance(v, (int, float)) and v >= 0:
            return v
    return None


def _count(summary: dict, explicit: int | None, *keys: str) -> int | None:
    if explicit is not None:
        return int(explicit)
    for k in keys:
        v = summary.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return int(v)
    return None


def rate_reliability(summary: dict[str, Any], replug_needed: bool | None = None,
                     pre_existing_fault: bool | None = None, fault: dict[str, Any] | None = None,
                     format_mismatch_count: int | None = None, fps_mismatch_count: int | None = None,
                     size_mismatch_count: int | None = None) -> dict[str, Any]:
    """summary: cycstats.summarize_cycles() output. replug_needed: the camera stayed broken after the run
    (e.g. trailing failures that never recovered and a health probe failing) - True/False/None.
    pre_existing_fault: the camera was already faulted before this test's first cycle (health probe before the
    variants failed) -> 'untested', so per-API cells do not blame the API for an earlier fault; ``fault`` = the
    fault record (first_fault_utc, test, mode, code). *_mismatch_count: cycles that delivered frames but not what
    was asked (format / fps / size; falls back to the same keys in ``summary``); a format or size mismatch caps the
    rating at partial. ``summary_label``: 'no (latency)' (cycles opened but the first frame came too late) vs
    'no (failures)' (cycles failed) vs 'no (replug needed)'."""
    n = summary.get("n") or 0
    rate = summary.get("first_frame_within_rate")
    hangs = summary.get("hangs") or 0
    unrel = summary.get("unreleasable") or 0
    rec = (summary.get("recovery_after_failure") or {})
    n_ok = summary.get("n_ok")
    succ = summary.get("success_rate", (n_ok / n) if (n and n_ok is not None) else None)
    fmt_n = _count(summary, format_mismatch_count, "format_mismatch_count", "format_mismatches")
    fps_n = _count(summary, fps_mismatch_count, "fps_mismatch_count", "fps_mismatches")
    size_n = _count(summary, size_mismatch_count, "size_mismatch_count", "size_mismatches")
    # A long trailing failure run that never recovered is suspicious but not proof: the caller decides
    # replug_needed with a health probe after the run; it is surfaced here as evidence.
    suspicious = bool(n and summary.get("trailing_failures", 0) >= max(3, n // 10))
    ev = {"n": n, "n_ok": n_ok, "success_rate": succ, "wilson95": summary.get("wilson95"),
          "first_frame_within_rate": rate, "first_frame_within_wilson95": summary.get("first_frame_within_wilson95"),
          "p50_open_to_first_frame_ms": _p50(summary.get("timings_ms"), "open_to_first_frame_ms", "first_frame_ms"),
          "format_mismatch_count": fmt_n, "fps_mismatch_count": fps_n, "size_mismatch_count": size_n,
          "hangs": hangs, "unreleasable": unrel, "recovery_rate": rec.get("rate"),
          "longest_failure_run": summary.get("longest_failure_run"), "replug_needed": replug_needed,
          "pre_existing_fault": pre_existing_fault, "trailing_failures_suspicious": suspicious}
    if fault:
        ev["fault"] = fault
    mism = (fmt_n or 0) + (size_n or 0)
    crit = [_crit(">= 99% of cycles deliver a first frame within 2 s", None if rate is None else rate >= 0.99, rate),
            _crit("no hang beyond the watchdog", hangs == 0 and unrel == 0, {"hangs": hangs, "unreleasable": unrel}),
            _crit("no state that needs a replug", None if replug_needed is None else not replug_needed, None),
            _crit("negotiated the requested format", None if fmt_n is None and size_n is None else mism == 0,
                  {"format_mismatch": fmt_n, "size_mismatch": size_n, "fps_mismatch": fps_n})]
    if pre_existing_fault:
        r = _result("untested", [_crit("camera healthy before the test", False, fault)] + crit, ev,
                    "camera already faulted before this test (pre-existing device fault); cycles not attributable "
                    "to the API")
        r["summary_label"] = "untested (pre-existing fault)"
        return r
    if n == 0 or rate is None:
        return untested("no cycles ran", ev)
    if rate < 0.95 or replug_needed:
        if replug_needed:
            label = "no (replug needed)"
        elif succ is not None and succ >= 0.95:
            label = "no (latency)"
        else:
            label = "no (failures)"
        detail = (f"{n_ok}/{n} opened and delivered a frame, {summary.get('n_first_frame_within')}/{n} within "
                  f"{summary.get('first_frame_within_s', 2.0):g} s")
        r = _result("no", crit, ev, f"{label}: {detail}")
        r["summary_label"] = label
        return r
    if rate >= 0.99 and hangs == 0 and unrel == 0:
        if mism:
            r = _result("partial", crit, ev, f"capped at partial: {mism} cycle(s) did not negotiate the requested "
                                             "format/size")
            r["summary_label"] = "partial (format mismatch)"
            return r
        r = _result("yes", crit, ev, None if replug_needed is False else "replug state not probed")
        r["summary_label"] = "yes"
        return r
    r = _result("partial", crit, ev, f"{mism} cycle(s) did not negotiate the requested format/size" if mism else None)
    r["summary_label"] = "partial (format mismatch)" if mism else "partial"
    return r


# ---------------------------------------------------------------------------------------------------- G-BW
_RAW_LABEL = re.compile(r"PCIROOT\(|ACPI\(|USBROOT\(|^\\?_SB[._]|^#?USB#|^(HS|SS|PRT|USB)\d{1,2}$", re.I)


def label_is_raw(label: Any) -> bool:
    """Shared raw-label rule: only ACPI names / location paths are raw; 'controller + port number' and better tiers
    are not. Uses ``common.topology_model.label_tier`` when it exists (dict with "raw", or a tier name containing
    'acpi' / 'location' / 'raw'); otherwise this module's fallback pattern."""
    try:
        from common import topology_model as _tm  # noqa: PLC0415
        lt = getattr(_tm, "label_tier", None)
        lr = getattr(_tm, "label_is_raw", None)
    except Exception:  # noqa: BLE001
        lt = lr = None
    if lr is not None:      # the shared rule itself (RAW_LABEL_TIERS)
        try:
            return bool(lr(label))
        except Exception:  # noqa: BLE001
            pass
    if lt is not None:
        try:
            t = lt(label)
            if isinstance(t, dict):
                if "raw" in t:
                    return bool(t["raw"])
                t = t.get("tier") or t.get("name")
            if isinstance(t, str):
                tl = t.lower()
                return "acpi" in tl or "location" in tl or tl == "raw"
            if isinstance(t, bool):
                return t
        except Exception:  # noqa: BLE001
            pass
    return bool(_RAW_LABEL.search(str(label or "").strip()))


def _is_dnr(e: dict) -> bool:
    return e.get("classified_class") == "device_not_ready" or e.get("device_not_ready") is True


def _try_ok(t: Any) -> bool | None:
    if isinstance(t, dict):
        v = t.get("ok")
        return None if v is None else bool(v)
    return None if t is None else bool(t)


def _retry_final(e: dict) -> tuple[bool | None, bool | None]:
    """(final try ok, first try ok) of an event's retry; ``retry_tries`` (list of bool / {"ok"}) wins over
    ``retry_ok``. The final try decides (a retry that works on its second attempt still works)."""
    tries = e.get("retry_tries")
    if isinstance(tries, list) and tries:
        return _try_ok(tries[-1]), _try_ok(tries[0])
    return e.get("retry_ok"), e.get("retry_first_try_ok", e.get("retry_ok"))


def rate_bw(events: list[dict[str, Any]], labels_raw: bool | None = None,
            ambiguous_apis: Iterable[str] = (), labels: Iterable[Any] | None = None) -> dict[str, Any]:
    """events: one dict per MULTI attempt: {pair/label, predicted_verdict ('fits'|'marginal'|'over'),
    observed_refused (bool), classified_class (classify_failure class, 'device_not_ready', or None),
    device_not_ready (bool, optional), expected_bandwidth (bool: the refusal is a bandwidth refusal by ground truth /
    test design), message_ports_other_domains (bool|None), retry_ok (bool|None) or retry_tries ([bool|{"ok"}]: the
    final try decides), api}. Events whose failure is device_not_ready (slow failure, RenderStream, re-arrival) are
    excluded from false fits and misattribution and counted separately. labels_raw: message used only raw labels
    (ACPI names / location paths); when None and ``labels`` is given, it is computed with ``label_is_raw`` (all raw
    = raw). ambiguous_apis: APIs whose refusal could only be classified bandwidth_probable."""
    labels_list = list(labels) if labels is not None else None
    if labels_raw is None and labels_list:
        labels_raw = all(label_is_raw(x) for x in labels_list)
    dnr = [e for e in events if _is_dnr(e)]
    considered = [e for e in events if not _is_dnr(e)]
    ev = {"events": events, "labels_raw": labels_raw, "labels": labels_list, "ambiguous_apis": list(ambiguous_apis),
          "device_not_ready": {"count": len(dnr),
                               "events": [e.get("label") or e.get("pair") or e.get("event") for e in dnr],
                               "note": "failures from a camera that was not ready (slow failure, RenderStream, "
                                       "re-arrival): excluded from false fits and misattribution"}}
    refusals = [e for e in considered if e.get("observed_refused")]
    if not events:
        return untested("no multi-camera attempt", ev)
    false_fits = [e for e in refusals if e.get("predicted_verdict") == "fits"]
    false_over = [e for e in considered if e.get("predicted_verdict") == "over" and e.get("observed_refused") is False]
    detected = [e for e in refusals if e.get("classified_class") is not None]
    misattrib = [e for e in refusals if e.get("expected_bandwidth", True)
                 and e.get("classified_class") not in ("bandwidth_certain", "bandwidth_probable")]
    msg_bad = [e for e in refusals if e.get("message_ports_other_domains") is False]
    retries = [(e, *_retry_final(e)) for e in refusals]
    retry_bad = [e for e, fin, _ in retries if fin is False]
    retry_first_bad = [e for e, fin, first in retries if first is False and fin is True]
    ev["retry"] = {"final_try_failed": len(retry_bad), "first_try_failed_final_ok": len(retry_first_bad)}
    ev["false_over"] = [e.get("label") or e.get("pair") or e.get("event") for e in false_over]
    crit = [_crit("no false 'fits' prediction for an observed refusal", not false_fits, len(false_fits)),
            _crit("every refusal detected and classified as bandwidth", bool(refusals) and not misattrib
                  and len(detected) == len(refusals), {"refusals": len(refusals), "misattributed": len(misattrib),
                                                      "device_not_ready_excluded": len(dnr)}),
            _crit("message lists only ports in other domains", None if not refusals else not msg_bad, len(msg_bad)),
            _crit("retry after a refusal works (final try)",
                  None if not refusals or all(fin is None for _, fin, _ in retries) else not retry_bad,
                  {"final_try_failed": len(retry_bad), "first_try_failed_final_ok": len(retry_first_bad)}),
            _crit("no false 'over' prediction (predicted over but every camera streamed)",
                  None if not any(e.get("predicted_verdict") == "over" for e in considered) else not false_over,
                  len(false_over)),
            _crit("labels better than raw (only ACPI names / location paths are raw)",
                  None if labels_raw is None else not labels_raw, labels_raw),
            _crit("classification unambiguous on every API", not list(ambiguous_apis), list(ambiguous_apis))]
    if not refusals:
        return _result("untested", crit, ev, "no refusal was observed, so prediction of refusals is untested")
    if misattrib or len(detected) < len(refusals) or false_fits:
        return _result("no", crit, ev)
    if msg_bad or retry_bad or false_over:
        return _result("partial", crit, ev)
    if labels_raw or list(ambiguous_apis):
        return _result("partial", crit, ev)
    return _result("yes", crit, ev)


# ---------------------------------------------------------------------------------------------------- FMT-NOGRAB
NOGRAB_CONDITIONS = ("idle", "streaming_native", "streaming_second_api")


def rate_fmt_nograb(conditions: dict[str, dict[str, Any]], no_reason: str | None = None,
                    method: str | None = None) -> dict[str, Any]:
    """Can a format-listing method identify a camera's formats without grabbing it (plan 6.2 FMT-NOGRAB)?

    conditions: {"idle" | "streaming_native" | "streaming_second_api": {
        "tested": bool, "untested_reason": str|None,
        "succeeded": bool,              # the method returned a format list
        "complete": bool|None,          # every descriptor format/size/rate listed (MJPEG and raw separately)
        "disturbed": bool|None,         # the other process's stream suffered during the listing window (streaming
                                        # conditions only; None = not measured / not applicable)
        "stream_started": bool|None,    # an isochronous pipe / non-zero alt appeared while the method held the
                                        # device (idle only; None = not determinable)
        "blocked": bool|None,           # a third process's 1-frame open failed or was delayed during the hold while
                                        # the control attempt worked (None = not testable)
        "elapsed_s": float|None}}
    no_reason: the method cannot list without opening a capture (OpenCV, WinRT MediaCapture): rated 'no'.

    yes = complete vs descriptors in all three conditions, no disturbance, no stream / bandwidth, no blocking;
    partial = complete when idle only, or it disturbs / blocks (or a condition / measurement is missing);
    no = incomplete when idle, or it needs a stream (starts one / reserves bandwidth)."""
    ev = {"method": method, "conditions": conditions}
    if no_reason:
        r = _result("no", [_crit("can list without opening a capture", False, no_reason)], ev, no_reason)
        r["summary_label"] = "no (cannot list without opening capture)"
        r["no_reason"] = no_reason
        return r
    idle = conditions.get("idle") or {}
    if not idle.get("tested"):
        return untested(idle.get("untested_reason") or "idle condition not run", ev)
    tested = {k: c for k, c in conditions.items() if c.get("tested")}
    untested_c = {k: c.get("untested_reason") for k, c in conditions.items() if not c.get("tested")}
    for k in NOGRAB_CONDITIONS:
        if k not in conditions:
            untested_c[k] = "condition not run"
    complete_all = all(c.get("succeeded") and c.get("complete") for c in tested.values())
    idle_ok = bool(idle.get("succeeded") and idle.get("complete"))
    started = [k for k, c in tested.items() if c.get("stream_started") is True]
    disturbed = [k for k, c in tested.items() if c.get("disturbed") is True]
    blocked = [k for k, c in tested.items() if c.get("blocked") is True]
    stream_measured = idle.get("stream_started") is not None
    dist_measured = [k for k, c in tested.items() if k != "idle" and c.get("disturbed") is not None]
    block_measured = any(c.get("blocked") is not None for c in tested.values())
    crit = [_crit("complete vs the USB descriptors (MJPEG and raw) in every condition",
                  complete_all if tested else None,
                  {k: {"succeeded": c.get("succeeded"), "complete": c.get("complete")} for k, c in tested.items()}),
            _crit("does not disturb another process's stream", None if not dist_measured else not disturbed,
                  {"disturbed_in": disturbed, "measured_in": dist_measured}),
            _crit("starts no stream and reserves no bandwidth", None if not stream_measured else not started,
                  {"stream_started_in": started}),
            _crit("does not block another process from opening the camera", None if not block_measured else not blocked,
                  {"blocked_in": blocked}),
            _crit("all three conditions measured", not untested_c, untested_c or None)]
    if started:
        r = _result("no", crit, ev, f"starts a stream / reserves bandwidth ({', '.join(started)})")
        r["summary_label"] = "no (needs a stream)"
        r["no_reason"] = "needs a stream"
        return r
    if not idle_ok:
        why = "failed" if not idle.get("succeeded") else "incomplete vs descriptors"
        r = _result("no", crit, ev, f"{why} with the camera idle")
        r["summary_label"] = f"no ({'failed' if not idle.get('succeeded') else 'incomplete'})"
        r["no_reason"] = why
        return r
    notes, label = [], None
    if not complete_all:
        bad = [k for k, c in tested.items() if not (c.get("succeeded") and c.get("complete"))]
        notes.append(f"complete when idle only (not in {', '.join(bad)})")
        label = "partial (idle only)"
    if disturbed:
        notes.append(f"disturbs the other stream ({', '.join(disturbed)})")
        label = label or "partial (disturbs)"
    if blocked:
        notes.append(f"blocks another process's open ({', '.join(blocked)})")
        label = label or "partial (blocks)"
    if notes:
        r = _result("partial", crit, ev, "; ".join(notes))
        r["summary_label"] = label
        return r
    missing = []
    if untested_c:
        missing.append("conditions not run: " + ", ".join(f"{k} ({v})" for k, v in untested_c.items()))
    if not stream_measured:
        missing.append("stream / bandwidth not measured")
    if not dist_measured:
        missing.append("disturbance not measured")
    if not block_measured:
        missing.append("blocking not testable")
    if missing:
        r = _result("partial", crit, ev, "provisional: " + "; ".join(missing))
        r["provisional"] = True
        r["summary_label"] = "partial (provisional)"
        return r
    return _result("yes", crit, ev)
