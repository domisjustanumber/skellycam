"""L-TS: per-frame timestamps on Linux (plan 2.6 / 6.2 TS, G-TS).

One raw-V4L2 capture per camera at its default mode with the UVC metadata node (V4L2_META_FMT_UVC, tier 0, same
permissions as the video node) streamed in parallel, plus low-frame-rate runs that probe the metadata buffer
overflow (10 KiB before 7.1: ERROR flags on >= 6.14, silent sequence gaps on 6.8) and, on >= 7.1, a run with a
larger meta buffersize set through S_FMT on the meta node.

Measured: buffer timestamp flags/clock (MONOTONIC + SOE expected), quantisation grid of the SOE stamp and of the
DQBUF arrival (common.tsanalysis.grid_analysis), frame-index fits (causal and whole run), the device clock (SCR STC
vs the kernel's per-URB host ns) and each frame's PTS mapped to host time through it, PTS/sequence drops, meta
sequence gaps and ERROR flags. hwtimestamps is read only (tier 1: never written). No ground truth on Linux yet
(--flash records 'unavailable'), so the best rating possible here is 'partial' (self-consistent device timestamps).

Mode scope (plan 6, Dom 2026-11-06): the main run uses the in-scope default (MJPG 1280x720@30, else the nearest
in-scope MJPEG mode). The low-frame-rate overflow runs (15 and 5 fps) and the 64 KiB meta buffersize run that
depends on them are out of scope and recorded as excluded; --all-modes runs them. No in-scope MJPEG mode ->
'untested (scope)'.
"""
from __future__ import annotations

from typing import Any

from common import rating, results, tsanalysis as ts
import analysis
import apis
import scope
from suitectx import combine
from tutil import gate, mode_text

TEST = "L-TS"
INFO = {"goal": "G-TS", "summary": "SOE buffer ts grid, metadata node PTS/SCR -> host fit, drops, meta overflow at "
                                   "low fps", "opens_cameras": True}
INVALID_DEVICE_SOF = {("046d", "085c"), ("046d", "082d"), ("046d", "085b")}  # C922, C920, C925e (kernel quirk)


def excluded_runs(ctx, cam: dict[str, Any]) -> list[dict[str, Any]]:
    """The low-fps overflow runs (and the buffersize run that follows them) the mode scope leaves out; empty with
    --all-modes."""
    st = scope.settings(ctx.args)
    if st["all_modes"] or not scope.picks(ctx, cam)["default"]:
        return []
    have_ = {r["label"] for r in ts_runs(ctx, cam)}
    out = [{"label": f"lowfps_{fps:g}", "reason": f"{fps:g} fps is below the mode scope (>= {st['min_fps']:g} fps)"}
           for fps in ((15.0,) if ctx.args.quick else (15.0, 5.0)) if f"lowfps_{fps:g}" not in have_]
    if out and ctx.kernel() >= (7, 1) and not any(x.endswith("_bufsize64k") for x in have_):
        out.append({"label": out[-1]["label"] + "_bufsize64k", "reason": "depends on the excluded low-fps run"})
    return out


def ts_runs(ctx, cam: dict[str, Any]) -> list[dict[str, Any]]:
    pk = scope.picks(ctx, cam)
    d = pk["default"]
    if not d:
        return []
    runs = [{"label": "main", "mode": d, "seconds": ctx.args.ts_seconds}]
    if not scope.settings(ctx.args)["all_modes"]:
        # low-fps metadata overflow runs: only the ones still inside the scope (none at the default 30 fps floor)
        allm = scope.filter_modes(cam["modes"]["all_mjpeg"], ctx.args)
        small = d
        for fps in ((15.0,) if ctx.args.quick else (15.0, 5.0)):
            m = next((x for x in allm if (x["w"], x["h"]) == (small["w"], small["h"]) and abs(x["fps"] - fps) < 0.6),
                     None)
            if m:
                runs.append({"label": f"lowfps_{fps:g}", "mode": m, "seconds": min(6.0, ctx.args.ts_seconds)})
        if ctx.kernel() >= (7, 1) and len(runs) > 1:
            runs.append({**runs[-1], "label": runs[-1]["label"] + "_bufsize64k", "buffersize": 65536})
        return runs
    small = cam["modes"]["small"] or d
    allm = cam["modes"]["all_mjpeg"]
    for fps in ((15.0,) if ctx.args.quick else (15.0, 5.0)):
        m = next((x for x in allm if (x["w"], x["h"]) == (small["w"], small["h"]) and abs(x["fps"] - fps) < 0.6), None)
        if m:
            runs.append({"label": f"lowfps_{fps:g}", "mode": m, "seconds": min(6.0, ctx.args.ts_seconds)})
    if ctx.kernel() >= (7, 1) and len(runs) > 1:
        runs.append({**runs[-1], "label": runs[-1]["label"] + "_bufsize64k", "buffersize": 65536})
    return runs


def plan(ctx) -> dict[str, Any]:
    n = sum(len(ts_runs(ctx, c)) for c in ctx.cameras)
    secs = sum(r["seconds"] + 4 for c in ctx.cameras for r in ts_runs(ctx, c))
    return {"child_runs": n, "est_seconds": round(secs), "steps": ["main run with metadata", "low-fps overflow runs",
                                                                   "fits and drops"],
            "mode_scope": scope.settings(ctx.args),
            "per_camera_runs": {c["key"]: [f"{r['label']} {mode_text(r['mode'])}" for r in ts_runs(ctx, c)]
                                for c in ctx.cameras},
            "excluded_runs": {c["key"]: [x["label"] for x in excluded_runs(ctx, c)] for c in ctx.cameras}}


def device_clock(rows: list[dict], meta: list[dict], clock_hz: float | None, fps: float) -> dict[str, Any]:
    """STC -> host fit from (stc, kernel ns) pairs, then PTS of each frame -> host time."""
    pairs = []
    for m in meta:
        for p in m.get("scr_pairs") or []:
            if p[0] is not None and p[3]:
                pairs.append((int(p[0]), int(p[3])))
    out: dict[str, Any] = {"n_scr_pairs": len(pairs), "clock_hz": clock_hz}
    if len(pairs) < 20:
        out["error"] = "too few SCR samples"
        return out
    pairs.sort(key=lambda x: x[1])
    stc_u = ts.unwrap([p[0] for p in pairs], 32)
    host = [p[1] for p in pairs]
    a, b = ts.linfit([float(x - stc_u[0]) for x in stc_u], [float(h) for h in host])
    res = [h - (a + b * (x - stc_u[0])) for x, h in zip(stc_u, host)]
    out["fit"] = {"ns_per_tick": b, "freq_hz_est": 1e9 / b if b else None,
                  "ppm_vs_nominal": ((1e9 / b - clock_hz) / clock_hz * 1e6) if b and clock_hz else None,
                  "residual_ms": ts.stats(res, 1e-6)}
    whole = ts.fit_device_clock([p[0] for p in pairs], host, clock_hz, causal=False)
    causal = ts.fit_device_clock([p[0] for p in pairs], host, clock_hz, causal=True)
    out["fit_device_clock"] = {"whole_residual_ms": whole.get("residual_stats_ms"),
                               "causal_residual_ms": causal.get("residual_stats_ms"),
                               "ppm_vs_nominal": whole.get("ppm_vs_nominal")}
    by_seq = {m["meta_seq"]: m for m in meta}
    unwrapped = {(p[0], p[1]): u for p, u in zip(pairs, stc_u)}   # (stc raw, host ns) -> unwrapped STC
    pts_host, soe = [], []
    for r in rows:
        m = by_seq.get(r.get("v4l2_seq"))
        if not m or m.get("uvc_pts") is None or m.get("uvc_scr_stc") is None:
            continue
        stc_raw, pts_raw = int(m["uvc_scr_stc"]), int(m["uvc_pts"])
        stc_frame = unwrapped.get((stc_raw, int(m.get("uvc_host_sof_ns") or 0)))
        if stc_frame is None:
            continue
        # PTS (start of exposure) precedes this payload's STC on the same 32-bit device clock
        pts_u = stc_frame - ((stc_raw - pts_raw) & 0xFFFFFFFF)
        pts_host.append(a + b * (pts_u - stc_u[0]))
        soe.append(r.get("ts_ns"))
    out["frames_with_pts"] = len(pts_host)
    out["pts_present_fraction"] = len(pts_host) / len(rows) if rows else None
    if len(pts_host) >= 10:
        iv = [(y - x) / 1e6 for x, y in zip(pts_host, pts_host[1:])]
        period_ms = 1000.0 / fps
        clean = [x for x in iv if 0.5 * period_ms < x < 1.5 * period_ms]
        out["pts_interval_ms"] = ts.stats(clean)
        out["pts_monotonic"] = all(x > 0 for x in iv)
        out["soe_minus_pts_host_ms"] = ts.stats([(s - p) / 1e6 for s, p in zip(soe, pts_host) if s])
        out["pts_drops"] = ts.detect_drops(pts_host, period=1e9 / fps)
        out["self_consistent"] = bool(out["pts_monotonic"] and out["pts_present_fraction"] >= 0.9
                                      and (out["pts_interval_ms"].get("std") or 99) < 1.0)
    return out


def analyse(rows: list[dict], meta: list[dict], fps: float, clock_hz: float | None) -> dict[str, Any]:
    period = 1e9 / fps
    tsn = [r["ts_ns"] for r in rows if r.get("ts_ns")]
    host = [r["host_ns"] for r in rows if r.get("host_ns")]
    kinds: dict[str, int] = {}
    for r in rows:
        k = f"{r.get('ts_type')}/{r.get('ts_src')}"
        kinds[k] = kinds.get(k, 0) + 1
    out: dict[str, Any] = {"frames": len(rows), "ts_flag_kinds": kinds,
                           "grid_buffer_ts": ts.grid_analysis(tsn, nominal_period_ns=period),
                           "grid_arrival": ts.grid_analysis(host, nominal_period_ns=period),
                           "arrival_minus_soe_ms": ts.stats([(r["host_ns"] - r["ts_ns"]) / 1e6 for r in rows
                                                             if r.get("ts_ns") and r.get("host_ns")])}
    for name, series in (("soe", tsn), ("arrival", host)):
        for causal in (False, True):
            f = ts.fit_frame_index(series, causal=causal, nominal_period_ns=period)
            out[f"frame_index_fit_{name}_{'causal' if causal else 'whole'}"] = {
                k: f.get(k) for k in ("period_ns", "fps", "residual_stats_ms", "slots_skipped", "duplicate_slots",
                                      "n_estimated", "error")}
    out["seq_drops"] = ts.detect_drops([r["v4l2_seq"] for r in rows if r.get("v4l2_seq") is not None])
    out["error_flag_frames"] = sum(1 for r in rows if r.get("error"))
    out["meta"] = {"buffers": len(meta), "error_flag": sum(1 for m in meta if m.get("meta_error")),
                   "empty": sum(1 for m in meta if not m.get("meta_bytes")),
                   "seq_gaps": ts.detect_drops([m["meta_seq"] for m in meta])["drops"] if meta else None,
                   "frames_without_meta": (len(rows) - len({m["meta_seq"] for m in meta} &
                                                           {r.get("v4l2_seq") for r in rows})) if meta else None,
                   "max_bytes": max((m.get("meta_bytes") or 0) for m in meta) if meta else None,
                   "blocks_per_buffer": ts.stats([m.get("blocks") for m in meta]) if meta else None}
    out["device_clock"] = device_clock(rows, meta, clock_hz, fps) if meta else {"error": "no metadata"}
    return out


def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST)
    errors: list[dict] = []
    per_cam: dict[str, Any] = {}
    v_soe, v_meta = {}, {}
    hwts = (ctx.env_facts.get("uvc_params") or {}).get("hwtimestamps")
    for cam in ctx.cameras:
        skip = gate(ctx, cam, TEST)
        if skip:
            per_cam[cam["key"]] = skip
            continue
        sc = scope.picks(ctx, cam)["record"]
        if not ts_runs(ctx, cam):
            per_cam[cam["key"]] = {"skipped": True, "mode_scope": sc,
                                   "reason": "no in-scope MJPEG mode" if sc.get("no_in_scope_mjpeg_mode")
                                   else "no MJPEG mode"}
            v_soe[cam["key"]] = v_meta[cam["key"]] = (scope.untested_scope(sc) if sc.get("no_in_scope_mjpeg_mode")
                                                      else rating.untested("no MJPEG mode"))
            continue
        cs = ctx.slug(cam)
        clock = cam["descriptors"].get("dwClockFrequency")
        ent: dict[str, Any] = {"runs": {}, "clock_hz": clock, "meta_node": cam.get("meta_node"),
                               "host_sof_substitution_needed": (cam["vid"], cam["pid"]) in INVALID_DEVICE_SOF,
                               "mode_scope": sc, "excluded_runs": excluded_runs(ctx, cam)}
        for rr in ts_runs(ctx, cam):
            od = ctx.test_dir(TEST, cs, rr["label"])
            extra = ["--meta", "auto"] + (["--meta-node", cam["meta_node"]] if cam.get("meta_node") else [])
            if rr.get("buffersize"):
                extra += ["--meta-buffersize", str(rr["buffersize"])]
            ctx.log(f"{cam['name']} {rr['label']} {mode_text(rr['mode'])} {rr['seconds']}s")
            cap = apis.capture(ctx, "v4l2", cam, rr["mode"], rr["seconds"], od, None, save="none", extra=extra,
                               analyse=False)
            rows = analysis.read_rows(od / "frames.jsonl")
            meta = analysis.read_rows(od / "meta.jsonl")
            a = analyse(rows, meta, float(rr["mode"]["fps"]), clock) if rows else {"error": "no frames"}
            a.update({"mode": mode_text(rr["mode"]), "meta_info": cap.get("meta"), "error": cap.get("error"),
                      "child": cap.get("child"), "buffersize_requested": rr.get("buffersize")})
            ent["runs"][rr["label"]] = a
            if cap.get("error"):
                errors.append({"camera": cam["key"], "run": rr["label"], "error": cap["error"]})
        main = ent["runs"].get("main") or {}
        g = main.get("grid_buffer_ts") or {}
        dc = main.get("device_clock") or {}
        seq_ok = ctx.kernel() >= (7, 2)
        v_soe[cam["key"]] = rating.rate_ts(None, drops_detectable=seq_ok, ground_truth=False, tier=0,
                                           host_grid_ms=g.get("step_ms") if g.get("quantized") else None,
                                           device_ts_self_consistent=None) if main.get("frames") else \
            rating.untested("no frames", main.get("error"))
        if dc.get("frames_with_pts"):
            v_meta[cam["key"]] = rating.rate_ts(None, drops_detectable=bool(dc.get("pts_drops") is not None),
                                                ground_truth=False, tier=0,
                                                device_ts_self_consistent=dc.get("self_consistent"))
        else:
            v_meta[cam["key"]] = rating.untested("no UVC PTS from the metadata node", dc.get("error"))
        per_cam[cam["key"]] = ent
    meas = {"cameras": per_cam, "mode_scope": scope.settings(ctx.args), "hwtimestamps_param": hwts, "hwtimestamps_note": "tier 1, read only (never written)",
            "ground_truth": "unavailable (no Linux flash/LED rig yet; attended item A5)" if not ctx.args.flash
            else "--flash given but no Linux flash tool exists yet: not used"}
    verdicts = {"G-TS:soe_buffer_timestamp": combine(v_soe, "SOE buffer ts") if v_soe else rating.untested("none"),
                "G-TS:uvc_metadata_pts": combine(v_meta, "metadata PTS") if v_meta else rating.untested("none")}
    results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)
    return res
