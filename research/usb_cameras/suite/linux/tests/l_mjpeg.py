"""L-MJPEG: every advertised MJPEG mode through raw V4L2 mmap (the reference), and each frame size through PyAV
v4l2 (input_format=mjpeg), OpenCV CAP_V4L2 (CONVERT_RGB=0) and GStreamer v4l2src image/jpeg when installed
(plan 6.2 MJPEG, G-MJPEG).

Per capture: S_FMT readback (nearest-size substitution caught), SOI/EOI, strict libjpeg-turbo decode (simplejpeg),
SOF0 size = request, fps vs nominal, V4L2_BUF_FLAG_ERROR count (6.14+; on 6.8 errors are silent sequence gaps),
sequence gaps, CPU, and the JPEG header SHA-1 compared across APIs. The granted alt of each mode opened alone feeds
the ModeAltCache used by L-MULTI. Raw frames go to the raw dir and are pruned to 3 sample frames per capture after
analysis (--mjpeg-modes and --mjpeg-seconds bound the run time).

Mode scope (plan 6, Dom 2026-11-06): only MJPEG modes at >= --min-fps (30) and >= --min-height (720) are captured
(linuxlib/scope.py over common/modescope.py); --all-modes captures every advertised mode. Each camera records the
scope and how many advertised modes it excluded; a camera with no in-scope MJPEG mode is 'untested (scope)'.
"""
from __future__ import annotations

import re
from typing import Any

from common import rating, results
import apis
import scope
from suitectx import combine
from tutil import gate, mode_text

TEST = "L-MJPEG"
INFO = {"goal": "G-MJPEG", "summary": "every MJPEG mode via raw V4L2; each size via PyAV / OpenCV / GStreamer; "
                                      "header SHA-1 across APIs", "opens_cameras": True}
BREAKER = 3  # consecutive device-error failures before a health check decides to stop a camera's mode sweep


def select_modes(ctx, cam: dict[str, Any]) -> list[dict[str, Any]]:
    """The modes to capture: the in-scope advertised MJPEG modes, then --mjpeg-modes (all / sizes / common)."""
    modes = scope.filter_modes(ctx.shared.get("v4l2_modes", {}).get(cam["key"]) or cam["modes"]["all_mjpeg"],
                               ctx.args)
    if not modes:
        return []
    kind = ctx.args.mjpeg_modes
    if kind == "all":
        return list(modes)
    if kind == "sizes":
        best: dict[tuple, dict] = {}
        for m in modes:
            k = (m["w"], m["h"])
            if k not in best or m["fps"] > best[k]["fps"]:
                best[k] = m
        return sorted(best.values(), key=lambda m: m["w"] * m["h"])
    pk = scope.picks(ctx, cam)
    out = [m for m in (pk["default"], pk["low"], pk["large"]) if m]
    uniq = []
    for m in out:
        if all(mode_text(m) != mode_text(u) for u in uniq):
            uniq.append(m)
    return uniq


def wrapper_modes(modes: list[dict[str, Any]]) -> set[str]:
    """Wrappers run once per frame size, at its highest rate."""
    best: dict[tuple, dict] = {}
    for m in modes:
        k = (m["w"], m["h"])
        if k not in best or m["fps"] > best[k]["fps"]:
            best[k] = m
    return {mode_text(m) for m in best.values()}


def plan(ctx) -> dict[str, Any]:
    n_raw = sum(len(select_modes(ctx, c)) for c in ctx.cameras)
    n_wrap = sum(len(wrapper_modes(select_modes(ctx, c))) for c in ctx.cameras) * len(
        [w for w in ctx.args.wrapper_list if w in ("pyav", "opencv", "gst")])
    s = ctx.args.mjpeg_seconds
    return {"child_runs": n_raw + n_wrap, "est_seconds": round(n_raw * (s + 3) + n_wrap * (s + 5)),
            "steps": [f"raw V4L2: {n_raw} mode captures of {s}s ({ctx.args.mjpeg_modes})",
                      f"wrappers {ctx.args.wrapper_list}: {n_wrap} captures (one per frame size)"],
            "per_camera_modes": {c["key"]: len(select_modes(ctx, c)) for c in ctx.cameras},
            "mode_scope": {k: v for k, v in scope.settings(ctx.args).items()},
            "per_camera_excluded": {c["key"]: scope.picks(ctx, c)["record"]["n_excluded"] for c in ctx.cameras}}


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST)
    errors: list[dict] = []
    per_cam: dict[str, Any] = {}
    v_raw: dict[str, Any] = {}
    v_wrap: dict[str, dict[str, Any]] = {w: {} for w in ctx.args.wrapper_list}
    secs = ctx.args.mjpeg_seconds
    for cam in ctx.cameras:
        skip = gate(ctx, cam, TEST)
        if skip:
            per_cam[cam["key"]] = skip
            v_raw[cam["key"]] = rating.untested(skip["reason"])
            continue
        modes = select_modes(ctx, cam)
        sc = scope.picks(ctx, cam)["record"]
        if not modes:
            per_cam[cam["key"]] = {"skipped": True, "reason": "no in-scope MJPEG mode", "mode_scope": sc}
            v_raw[cam["key"]] = scope.untested_scope(sc)
            continue
        wm = wrapper_modes(modes)
        cs = ctx.slug(cam)
        rows_for_rating, wrap_rows = [], {w: [] for w in ctx.args.wrapper_list}
        entries = []
        consecutive_fail = 0
        stopped = None
        exposure_dynamic = None
        for wk in (ctx.shared.get("controls", {}).get(cam["key"]) or []):
            if wk.get("id") == 0x009A0903:
                exposure_dynamic = wk.get("value")
        for m in modes:
            if stopped:
                entries.append({"mode": mode_text(m), "skipped": stopped})
                continue
            ms = slug(mode_text(m))
            od = ctx.test_dir(TEST, cs, ms, "v4l2")
            rd = ctx.raw_test_dir(TEST, cs, ms, "v4l2")
            ctx.log(f"{cam['name']} {mode_text(m)} raw v4l2")
            ref = apis.capture(ctx, "v4l2", cam, m, secs, od, rd)
            ref["classification"] = apis.classify(ref.get("error"))
            if ref.get("ok") and ref.get("granted_alt") is not None:
                ctx.learn_alt(cam, m, ref["granted_alt"], "L-MJPEG raw V4L2, camera alone")
            hashes = {"v4l2": (ref.get("check") or {}).get("dominant_header_sha1")}
            ent: dict[str, Any] = {"mode": mode_text(m), "v4l2": _slim(ref)}
            if not getattr(ctx.args, "keep_raw", False):
                apis.prune_raw(rd, od / "frames.jsonl")
            if ref.get("ok"):
                consecutive_fail = 0
            else:
                cls = (ref.get("classification") or {}).get("class")
                consecutive_fail += 1 if cls in ("device_error", "timeout") else 0
                if consecutive_fail >= BREAKER:
                    hc = ctx.camcmd(ctx.worker_cmd("info", "--device", cam["node"]), timeout_s=20)
                    if (hc.get("json") or {}).get("error") or hc.get("timed_out"):
                        stopped = (f"camera stopped answering after {consecutive_fail} consecutive device errors "
                                   f"(health check failed); remaining modes not attempted")
                        errors.append({"camera": cam["key"], "stage": "mode sweep", "message": stopped,
                                       "is_kiyo": cam["is_kiyo"]})
                    consecutive_fail = 0
            if mode_text(m) in wm:
                for w in ctx.args.wrapper_list:
                    if w not in ("pyav", "opencv", "gst"):
                        continue
                    wod = ctx.test_dir(TEST, cs, ms, w)
                    wrd = ctx.raw_test_dir(TEST, cs, ms, w)
                    ctx.log(f"{cam['name']} {mode_text(m)} {w}")
                    wr = apis.capture(ctx, w, cam, m, secs, wod, wrd)
                    if wr.get("skipped"):
                        ent[w] = wr
                        continue
                    hashes[w] = (wr.get("check") or {}).get("dominant_header_sha1")
                    ent[w] = _slim(wr)
                    wrap_rows[w].append({"mode": mode_text(m), "negotiated": bool(wr.get("ok")),
                                         "frames": wr.get("frames"),
                                         "strict_valid_fraction": (wr.get("check") or {}).get("strict_ok_fraction"),
                                         "lenient_valid_fraction": (wr.get("check") or {}).get("lenient_ok_fraction"),
                                         "known_quirk": None,
                                         "sof_matches": (wr.get("check") or {}).get("sof_matches_request_fraction")
                                         == 1.0, "fps_measured": wr.get("fps_host"), "fps_expected": float(m["fps"]),
                                         "header_sha1_by_api": {"v4l2": hashes["v4l2"], w: hashes[w]}
                                         if hashes["v4l2"] and hashes[w] else None,
                                         "is_jpeg": ((wr.get("check") or {}).get("soi_fraction") or 0) > 0.5
                                         if (wr.get("check") or {}).get("n") else None})
                    if not getattr(ctx.args, "keep_raw", False):
                        apis.prune_raw(wrd, wod / "frames.jsonl")
            ent["header_sha1_by_api"] = hashes
            ent["header_equal_across_apis"] = (len({h for h in hashes.values() if h}) == 1) \
                if len([h for h in hashes.values() if h]) > 1 else None
            rows_for_rating.append(apis.mjpeg_mode_row(cam, m, ref, hashes))
            entries.append(ent)
        per_cam[cam["key"]] = {"modes": entries, "n_modes": len(modes), "mode_selection": ctx.args.mjpeg_modes,
                               "mode_scope": sc,
                               "exposure_dynamic_framerate": exposure_dynamic,
                               "fps_note": "exposure_dynamic_framerate=1 lets the camera lower fps in dim light"
                               if exposure_dynamic == 1 else None, "stopped": stopped}
        r = rating.rate_mjpeg(rows_for_rating)
        r["mode_scope"] = sc
        if sc.get("n_excluded"):
            r["note"] = ((r.get("note") or "") + f" rated on the {sc['n_in_scope']} in-scope MJPEG modes "
                         f"({sc['n_excluded']} of {sc['n_advertised']} advertised excluded by the mode scope)").strip()
        if exposure_dynamic == 1:
            r["note"] = (r.get("note") or "") + " fps may be limited by exposure_dynamic_framerate=1 (left as found)"
        v_raw[cam["key"]] = r
        for w, rows in wrap_rows.items():
            if rows:
                v_wrap[w][cam["key"]] = rating.rate_mjpeg(rows)
    verdicts = {"G-MJPEG:raw_v4l2": combine(v_raw, "raw V4L2 mmap") if v_raw else rating.untested("no camera")}
    for w, d in v_wrap.items():
        if d:
            verdicts[f"G-MJPEG:{w}"] = combine(d, w)
    results.finish_result(res, measurements={"cameras": per_cam, "seconds_per_mode": secs,
                                             "mode_scope": scope.settings(ctx.args),
                                             "mode_alt_cache_entries": len(ctx.mode_alt_cache)},
                          verdicts=verdicts, errors=errors)
    return res


def _slim(r: dict[str, Any]) -> dict[str, Any]:
    """Drop bulky bits (header hash histograms stay)."""
    out = dict(r)
    chk = dict(out.get("check") or {})
    chk.pop("rows_header_sha1", None)
    out["check"] = chk
    if isinstance(out.get("counts"), dict):
        c = dict(out["counts"])
        c.pop("hdr_sha1", None)
        out["counts"] = c
    return out
