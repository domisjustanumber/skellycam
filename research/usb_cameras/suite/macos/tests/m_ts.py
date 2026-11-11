"""M-TS: which timestamp fields exist (PTS, duration, CMIO sequence number, attachments), the quantisation grid of
each, the session synchronizationClock vs the host clock and the input port's clock rate against host time (a
drifting port clock would point to a camera-derived clock; verifier correction 2), frame-index fits of arrival
(causal and whole-run), drops from the CMIO sequence number / PTS gaps / drop callbacks (plan 6.2 TS; macos.md G-TS).
No ground truth here: the ESP32 rig (attended A5) is required for an absolute score; --flash is only recorded.
Mode scope (plan 6): MJPEG 1280x720@30, else the nearest in-scope MJPEG mode; none -> untested (scope)."""
from __future__ import annotations

import suitectx
import macanalysis
import mac_modescope
from common import rating, results

NAME = "M-TS"


def plan(ctx) -> list[str]:
    return [mac_modescope.text(ctx.args),
            f"per camera: mac_avf.py capture --seconds {ctx.args.ts_seconds} (default mode MJPEG 1280x720@30 or nearest "
            "in-scope MJPEG mode, no JPEG decode)",
            "grid_analysis on PTS and arrival; fit_frame_index (causal / whole); detect_drops on CMIO seq and PTS",
            "clocks: CFEqual(synchronizationClock, host clock), port clock CMSyncGetRelativeRate vs host"]


def run(ctx) -> dict:
    res = ctx.new_result(NAME)
    errors: list = []
    per = []
    ratings = []
    for cam in ctx.openable():
        mode, minfo = suitectx.pick_scoped_default(cam, ctx.args)
        if not mode:
            unt = rating.untested(f"{minfo['why']}: untested (scope)")
            unt["summary_label"] = "untested (scope)"
            per.append({"key": cam["key"], "is_kiyo": cam.get("is_kiyo"), "untested": "scope", "mode_choice": minfo,
                        "rating": unt})
            continue
        od = ctx.subdir("ts", f"{suitectx.cam_tag(cam)}")
        r = ctx.avf(["capture", "--device", cam["unique_id"], "--seconds", ctx.args.ts_seconds, "--jpeg-check", "none",
                     "--out-dir", od] + suitectx.avf_mode_args(mode), ctx.args.ts_seconds + 40, label=f"ts {cam['key']}")
        j = r.get("json") or {}
        rows = results.read_jsonl(od / "frames.jsonl")
        clocks = ((j.get("stream") or {}).get("clocks") or {}) | {k: (j.get("stream") or {}).get(k)
                                                                  for k in ("port_minus_host_ns_end", "port_rate_vs_host_end")}
        an = macanalysis.ts_analysis(rows, mode.get("fps"), clocks)
        an["dropped_callbacks"] = j.get("dropped_callbacks")
        grid = an.get("pts_grid") or {}
        rt = rating.rate_ts(None, an.get("drops_detectable"), ground_truth=False, tier=0, synthesized=False,
                            host_grid_ms=grid.get("step_ms") if grid.get("quantized") else None,
                            device_ts_self_consistent=an.get("pts_self_consistent") or None)
        ratings.append(rt)
        per.append({"key": cam["key"], "is_kiyo": cam.get("is_kiyo"), "mode": mode, "mode_choice": minfo,
                    "frames": j.get("frames"),
                    "timed_out": r.get("timed_out"), "analysis": an, "rating": rt})
        if r.get("timed_out"):
            errors.append({"camera": cam["key"], "warning": "TS capture timed out"})
    m = {"cameras": per, "ground_truth": "none (ESP32 rig not attached; --flash recorded only)" if not ctx.args.flash
         else "requested, but this suite has no rig driver yet", "flash_requested": bool(ctx.args.flash),
         "mode_scope": suitectx.scope_for_test(ctx.openable(), ctx.args)}
    worst = rating.worst(ratings)
    v = {"G-TS": {"rating": worst, "criteria": [{"criterion": "worst camera (plan 3 G-TS; no ground truth)",
                                                 "met": None, "detail": worst}],
                  "evidence": {p["key"]: p["rating"]["rating"] for p in per}, "tier": 0,
                  "mode_scope": mac_modescope.text(ctx.args)}}
    return results.finish_result(res, m, v, errors)
