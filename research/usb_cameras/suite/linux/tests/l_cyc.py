"""L-CYC: open -> S_FMT -> REQBUFS -> STREAMON -> first frame -> N frames -> STREAMOFF -> close, repeated
(plan 6.2 CYC; Dom's criterion: open/close/open/close works every time).

Per camera: raw V4L2 in one process (--cycles), raw V4L2 in a new process each cycle (--proc-cycles), raw V4L2
alternating two modes, PyAV v4l2 in-process and per-process, OpenCV CAP_V4L2 in-process (status-quo baseline).
Every failure keeps its stage and errno (classified with common.topology_model.classify_failure); the next cycle
shows recovery. After each batch a short health capture decides whether the camera needs a replug.

Mode scope (plan 6, Dom 2026-11-06): the cycle mode is the in-scope default (MJPG 1280x720@30, else the nearest
in-scope MJPEG mode) and the mode-switch variant alternates it with a second in-scope mode (1920x1080@30, else
1280x720@60, else the nearest other in-scope mode; linuxlib/scope.py). --all-modes restores the earlier pair
(640x480@30 <-> 1280x720@30). No in-scope MJPEG mode -> 'untested (scope)'.
"""
from __future__ import annotations

from typing import Any

from common import cycstats, rating, results
import apis
import scope
from suitectx import child_outcome, combine
from tutil import gate, mode_args, mode_text, worker_error

TEST = "L-CYC"
INFO = {"goal": "reliability", "summary": "in-process / per-process / mode-switch cycles: raw V4L2, PyAV, OpenCV",
        "opens_cameras": True}


def plan(ctx) -> dict[str, Any]:
    a = ctx.args
    per = (3 * a.cycles + a.proc_cycles) * (a.frames / 30 + 1.0)
    if "pyav" in a.wrapper_list:
        per += a.cycles * (a.frames / 30 + 1.5) + a.proc_cycles * (a.frames / 30 + 4)
    if "opencv" in a.wrapper_list:
        per += a.cycles * (a.frames / 30 + 1.5)
    return {"child_runs": len(ctx.cameras) * (4 + a.proc_cycles * 2), "est_seconds": round(per * len(ctx.cameras)),
            "steps": [f"v4l2 in-process x{a.cycles}", f"v4l2 per-process x{a.proc_cycles}",
                      f"v4l2 mode switch x{a.cycles}", "pyav in/per-process", "opencv in-process", "health check"],
            "mode_scope": scope.settings(a),
            "per_camera_modes": {c["key"]: [mode_text(m) for m in modes_for(ctx, c)] for c in ctx.cameras}}


def modes_for(ctx, cam: dict[str, Any]) -> tuple[dict | None, dict | None]:
    """(cycle mode, second mode for the mode-switch variant), in scope (see the module docstring)."""
    a, b = scope.picks(ctx, cam)["cyc_pair"]
    if b is not None and mode_text(b) == mode_text(a):
        b = None
    return a, b


def _classify_rows(rows: list[dict[str, Any]]) -> None:
    for r in rows:
        if r.get("ok"):
            continue
        err = {"stage": r.get("stage_failed"), "errno": r.get("errno"), "errno_name": r.get("errno_name")}
        if r.get("timed_out") or r.get("stage_failed") == "timeout":
            err["errno_name"] = "timeout"
        c = apis.classify(err)
        r["error_class"] = (c or {}).get("class")


def _batch(ctx, cam, label: str, argv: list[str], timeout_s: float, out_dir, env=None) -> dict[str, Any]:
    r = ctx.camcmd(argv, timeout_s=timeout_s, env=env)
    rows = results.read_jsonl(out_dir / "cycles.jsonl")
    if r.get("timed_out"):
        rows.append({"i": len(rows), "ok": False, "stage_failed": "timeout", "timed_out": True, "hung": True,
                     "note": "runner killed the child"})
    _classify_rows(rows)
    s = cycstats.summarize_cycles(rows)
    return {"label": label, "rows": len(rows), "summary": s, "child": child_outcome(r), "error": worker_error(r),
            "_rows": rows}


def _per_process(ctx, cam, api: str, mode: dict, n: int, frames: int, out_root) -> dict[str, Any]:
    rows = []
    for i in range(n):
        od = out_root / f"proc_{i:03d}"
        od.mkdir(parents=True, exist_ok=True)
        if api == "v4l2":
            argv = ctx.worker_cmd("capture", "--device", cam["node"], *mode_args(mode), "--frames", frames,
                                  "--out-dir", od, "--save", "none")
        else:
            argv = ctx.helper_cmd("pyav_v4l2.py", "capture", "--device", cam["node"], "--width", mode["w"],
                                  "--height", mode["h"], "--fps", f"{float(mode['fps']):g}", "--frames", frames,
                                  "--out-dir", od)
        r = ctx.camcmd(argv, timeout_s=30 + frames / max(float(mode["fps"]), 1) * 2)
        j = r.get("json") or {}
        err = worker_error(r)
        if api == "v4l2":
            t = j.get("timings") or {}
            st = j.get("stream") or {}
            n_fr = (st.get("counts") or {}).get("frames", 0)
            row = {"i": i, "mode": mode_text(mode), "ok": bool(n_fr >= frames and not err), **t, "frames": n_fr,
                   "process_ms": round((r.get("elapsed_s") or 0) * 1000, 1)}
        else:
            row = {"i": i, "mode": mode_text(mode), "ok": bool(j.get("ok")), "frames": j.get("frames"),
                   "open_ms": j.get("open_ms"), "first_frame_ms": j.get("first_frame_ms"),
                   "close_ms": j.get("close_ms"), "process_ms": round((r.get("elapsed_s") or 0) * 1000, 1)}
        if err:
            row.update(stage_failed=err.get("stage"), errno=err.get("errno"), errno_name=err.get("errno_name"),
                       timed_out=bool(r.get("timed_out")))
        elif not row["ok"]:
            row["stage_failed"] = j.get("stage_failed") or "frames"
        rows.append(row)
        results.append_jsonl(out_root / "cycles.jsonl", row)
    _classify_rows(rows)
    return {"label": f"{api} per-process", "rows": len(rows), "summary": cycstats.summarize_cycles(rows),
            "_rows": rows}


def health(ctx, cam, mode) -> dict[str, Any]:
    od = ctx.test_dir(TEST, ctx.slug(cam), "health")
    r = ctx.camcmd(ctx.worker_cmd("capture", "--device", cam["node"], *mode_args(mode), "--frames", 5,
                                  "--out-dir", od), timeout_s=30)
    j = r.get("json") or {}
    n = ((j.get("stream") or {}).get("counts") or {}).get("frames", 0)
    return {"ok": n >= 5, "frames": n, "error": worker_error(r)}


def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST)
    a = ctx.args
    errors: list[dict] = []
    per_cam: dict[str, Any] = {}
    verdict_by_api: dict[str, dict[str, Any]] = {}
    for cam in ctx.cameras:
        skip = gate(ctx, cam, TEST)
        sc = scope.picks(ctx, cam)["record"]
        if not skip and not modes_for(ctx, cam)[0]:
            skip = {"skipped": True, "reason": "no in-scope MJPEG mode" if sc.get("no_in_scope_mjpeg_mode")
                    else "no MJPEG mode", "mode_scope": sc}
        if skip:
            per_cam[cam["key"]] = skip
            # visible in the verdict as 'untested' for this camera (a skipped camera is never silently dropped)
            verdict_by_api.setdefault("v4l2_inprocess", {})[cam["key"]] = (
                scope.untested_scope(sc) if sc.get("no_in_scope_mjpeg_mode") else rating.untested(skip["reason"]))
            continue
        ma, mb = modes_for(ctx, cam)
        cs = ctx.slug(cam)
        fps = float(ma["fps"])
        t_cycle = a.frames / max(fps, 1) + 3.0
        batches = []
        od = ctx.test_dir(TEST, cs, "v4l2_inproc")
        ctx.log(f"{cam['name']} v4l2 in-process x{a.cycles} {mode_text(ma)}")
        batches.append(("v4l2_inprocess", _batch(ctx, cam, "v4l2 in-process", ctx.worker_cmd(
            "cycle", "--device", cam["node"], *mode_args(ma), "--cycles", a.cycles, "--frames", a.frames,
            "--out-dir", od), 30 + a.cycles * t_cycle * 1.5, od)))
        ctx.log(f"{cam['name']} v4l2 per-process x{a.proc_cycles}")
        batches.append(("v4l2_perprocess", _per_process(ctx, cam, "v4l2", ma, a.proc_cycles, a.frames,
                                                        ctx.test_dir(TEST, cs, "v4l2_perproc"))))
        if mb:
            od = ctx.test_dir(TEST, cs, "v4l2_modeswitch")
            ctx.log(f"{cam['name']} v4l2 mode switch {mode_text(ma)} <-> {mode_text(mb)}")
            batches.append(("v4l2_modeswitch", _batch(ctx, cam, "v4l2 mode switch", ctx.worker_cmd(
                "cycle", "--device", cam["node"], *mode_args(ma), "--alt-width", mb["w"], "--alt-height", mb["h"],
                "--alt-fps", f"{float(mb['fps']):g}", "--cycles", a.cycles, "--frames", a.frames, "--out-dir", od),
                30 + a.cycles * t_cycle * 2, od)))
        if "pyav" in a.wrapper_list:
            od = ctx.test_dir(TEST, cs, "pyav_inproc")
            ctx.log(f"{cam['name']} pyav in-process")
            batches.append(("pyav_inprocess", _batch(ctx, cam, "pyav in-process", ctx.helper_cmd(
                "pyav_v4l2.py", "cycle", "--device", cam["node"], "--width", ma["w"], "--height", ma["h"],
                "--fps", f"{fps:g}", "--cycles", a.cycles, "--frames", a.frames, "--out-dir", od),
                60 + a.cycles * (t_cycle + 2) * 1.5, od)))
            batches.append(("pyav_perprocess", _per_process(ctx, cam, "pyav", ma, a.proc_cycles, a.frames,
                                                            ctx.test_dir(TEST, cs, "pyav_perproc"))))
        if "opencv" in a.wrapper_list:
            od = ctx.test_dir(TEST, cs, "opencv_inproc")
            ctx.log(f"{cam['name']} opencv in-process")
            batches.append(("opencv_inprocess", _batch(ctx, cam, "opencv in-process", ctx.helper_cmd(
                "opencv_v4l2.py", "cycle", "--device", cam["node"], "--width", ma["w"], "--height", ma["h"],
                "--fps", f"{fps:g}", "--cycles", a.cycles, "--frames", a.frames, "--out-dir", od),
                60 + a.cycles * (t_cycle + 2) * 1.5, od, env={"OPENCV_LOG_LEVEL": "DEBUG"})))
        hc = health(ctx, cam, ma)
        ent = {"modes": [mode_text(ma), mode_text(mb)], "health_after": hc, "batches": {}, "mode_scope": sc,
               "mode_switch": ({"from": mode_text(ma), "to": mode_text(mb)} if mb else
                               {"skipped": "no second in-scope mode" if not sc.get("all_modes") else "no second mode"})}
        for name, b in batches:
            rows = b.pop("_rows", [])
            s = b["summary"]
            # the health capture runs after all batches: a camera that cannot deliver 5 frames then needs a replug
            r = rating.rate_reliability(s, replug_needed=not hc["ok"])
            b["rating"] = r
            b["failed_rows"] = [x for x in rows if not x.get("ok")][:20]
            b["granted_alts"] = sorted({x.get("granted_alt") for x in rows if x.get("granted_alt") is not None})
            b["rearrivals_in_batch"] = sum(1 for x in rows if x.get("devnum_before") and x.get("devnum_after")
                                           and x["devnum_before"] != x["devnum_after"])
            ent["batches"][name] = b
            verdict_by_api.setdefault(name, {})[cam["key"]] = r
            if b.get("error"):
                errors.append({"camera": cam["key"], "batch": name, "error": b["error"]})
        if ma and (ent["batches"].get("v4l2_inprocess") or {}).get("granted_alts"):
            ctx.learn_alt(cam, ma, ent["batches"]["v4l2_inprocess"]["granted_alts"][0], "L-CYC raw V4L2 alone")
        per_cam[cam["key"]] = ent
    verdicts = {f"reliability:{api}": combine(d, api) for api, d in verdict_by_api.items()}
    if not verdicts:
        verdicts = {"reliability": rating.untested("no camera cycled")}
    results.finish_result(res, measurements={"cameras": per_cam, "cycles": a.cycles, "proc_cycles": a.proc_cycles,
                                             "frames": a.frames, "mode_scope": scope.settings(a)},
                          verdicts=verdicts, errors=errors)
    return res
