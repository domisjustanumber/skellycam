"""M-CYC: open -> first frame -> N frames -> close, per camera: K cycles in one process, K' cycles in a new process
each time, plus (full suite) a 500 ms gap variant and a mode-switching variant. Timings and every failure code;
the next cycle after a failure records recovery (plan 6.2 CYC, Dom's open/close criterion; macos.md MX2).
Each cycle builds a fresh AVCaptureSession from a re-fetched AVCaptureDevice; a hung cycle is written and the
child exits; the runner moves on.

Mode scope (plan 6, Dom 2026-11-06): the default mode is MJPEG 1280x720@30 (else the nearest in-scope MJPEG mode);
the mode-switch variant alternates it with another in-scope mode (1920x1080@30 <-> 1280x720@30, else 720p60, else
the nearest other in-scope mode), never 640x480. A camera with no in-scope MJPEG mode is recorded as untested
(scope); --all-modes restores the pre-scope choices (default <-> smallest mode)."""
from __future__ import annotations

import suitectx
import mac_modescope
from common import cycstats, rating, results, topology_model

NAME = "M-CYC"


def plan(ctx) -> list[str]:
    a = ctx.args
    out = [mac_modescope.text(a),
           f"per camera: mac_avf.py cycle --cycles {a.cycles} --frames {a.frames} (in-process, default mode)",
           f"per camera: {a.proc_cycles} x mac_avf.py cycle --cycles 1 (one process per cycle)"]
    if not a.quick:
        out += ["per camera: --gap-ms 500 variant; mode-switching variant (default <-> another in-scope mode)"]
    for cam in ctx.openable():
        m, info = suitectx.pick_scoped_default(cam, a)
        if not m:
            out.append(f"{cam['key']}: untested (scope): {info['why']}")
            continue
        alt, why = suitectx.pick_scoped_alt(cam, a, m)
        out.append(f"{cam['key']}: default {m['mode_text']}; mode switch: {alt['mode_text'] if alt else why}")
    return out


def _classify(rows: list[dict]) -> None:
    for r in rows:
        if r.get("ok"):
            continue
        code = (r.get("iokit_codes") or [None])[0] or r.get("code")
        if r.get("timed_out"):
            code = "timeout"
        r["classification"] = topology_model.classify_failure(
            "macos", code, {"api": "avf", "stage": r.get("stage_failed"), "frames": r.get("frames"),
                            "timed_out": r.get("timed_out")})
        r["error_class"] = r["classification"]["class"]


def _variant(ctx, cam, name, args, timeout, cycles: int | None = None, max_restarts: int = 3) -> dict:
    """Run the in-process cycle child. A hung cycle cannot be abandoned inside AVFoundation, so the child writes it
    and exits 5; the remaining cycles then continue in a fresh child (at most max_restarts times), so one hang does
    not silently shorten the sample."""
    tag = f"{suitectx.cam_tag(cam)}/{name}"
    rows: list[dict] = []
    j: dict = {}
    r: dict = {}
    restarts = 0
    part = 0
    while True:
        od = ctx.subdir("cyc", tag) if part == 0 else ctx.subdir("cyc", tag, f"restart{part}")
        left = None if cycles is None else cycles - len(rows)
        a2 = list(args) + (["--cycles", left] if left is not None else [])
        r = ctx.avf(a2 + ["--out-dir", od], timeout, label=f"cyc {tag}" + (f" restart {part}" if part else ""))
        got = results.read_jsonl(od / "cycles.jsonl")
        j = r.get("json") or {}
        if not got and j.get("rows"):
            got = j["rows"]
        if r.get("timed_out") and not any(x.get("timed_out") for x in got):
            got.append({"i": len(got), "ok": False, "stage_failed": "timeout", "timed_out": True,
                        "note": "runner killed the child"})
        for x in got:
            x["child_part"] = part
        rows += got
        hung = r.get("timed_out") or j.get("timed_out") or r.get("rc") == 5
        if cycles is None or not hung or len(rows) >= cycles or restarts >= max_restarts or not got:
            break
        restarts += 1
        part += 1
    for k, x in enumerate(rows):
        x["i_in_child"] = x.get("i")
        x["i"] = k
    od = ctx.subdir("cyc", tag)
    _classify(rows)
    s = cycstats.summarize_cycles(rows)
    return {"variant": name, "summary": s, "rating": rating.rate_reliability(s), "rc": r.get("rc"),
            "child_error": j.get("error"), "rows_jsonl": str(od / "cycles.jsonl")}


def run(ctx) -> dict:
    res = ctx.new_result(NAME)
    errors: list = []
    per = []
    ratings = []
    a = ctx.args
    for cam in ctx.openable():
        mode, minfo = suitectx.pick_scoped_default(cam, a)
        if not mode:
            unt = rating.untested(f"{minfo['why']}: untested (scope)", {"mode_scope": suitectx.camera_scope(cam, a)})
            unt["summary_label"] = "untested (scope)"
            per.append({"key": cam["key"], "is_kiyo": cam.get("is_kiyo"), "untested": "scope", "mode_choice": minfo,
                        "mode_scope": suitectx.camera_scope(cam, a), "variants": [], "rating": unt})
            continue
        alt, alt_why = suitectx.pick_scoped_alt(cam, a, mode)
        base = ["cycle", "--device", cam["unique_id"], "--frames", a.frames, "--timeout-ms", 5000,
                "--cycle-timeout-s", 30] + suitectx.avf_mode_args(mode)
        crec = {"key": cam["key"], "is_kiyo": cam.get("is_kiyo"), "mode": mode, "mode_choice": minfo,
                "mode_scope": suitectx.camera_scope(cam, a), "variants": []}
        crec["variants"].append(_variant(ctx, cam, "in_process", base, 40 + 25 * a.cycles, cycles=a.cycles))
        if not a.quick:
            crec["variants"].append(_variant(ctx, cam, "in_process_gap500", base + ["--gap-ms", 500],
                                             40 + 26 * a.cycles, cycles=a.cycles))
            crec["alt_mode_choice"] = alt_why
            if alt:
                crec["variants"].append(_variant(ctx, cam, "mode_switch",
                                                 base + ["--alt-format-index", alt["format_index"],
                                                         "--alt-fps", f"{alt['fps']:g}"], 40 + 25 * a.cycles,
                                                 cycles=a.cycles))
                crec["alt_mode"] = alt
        # one process per cycle
        rows = []
        tag = f"{suitectx.cam_tag(cam)}/per_process"
        for i in range(a.proc_cycles):
            od = ctx.subdir("cyc", tag, f"p{i:03d}")
            r = ctx.avf(base + ["--cycles", 1, "--out-dir", od], 50, label=f"cyc {tag} {i}")
            rr = results.read_jsonl(od / "cycles.jsonl")
            row = dict(rr[0]) if rr else {"ok": False, "stage_failed": "timeout" if r.get("timed_out") else "child",
                                          "timed_out": r.get("timed_out"), "rc": r.get("rc")}
            row["i"] = i
            row["process_ms"] = round((r.get("elapsed_s") or 0) * 1000, 1)
            rows.append(row)
        _classify(rows)
        s = cycstats.summarize_cycles(rows)
        crec["variants"].append({"variant": "per_process", "summary": s, "rating": rating.rate_reliability(s),
                                 "rows": rows})
        # health probe after the variants: does the camera still stream? (replug-needed evidence)
        h = ctx.avf(base + ["--cycles", 1], 50, label=f"cyc health {cam['key']}")
        healthy = bool((h.get("json") or {}).get("ok"))
        crec["health_after"] = {"ok": healthy, "rc": h.get("rc"), "timed_out": h.get("timed_out")}
        for v in crec["variants"]:
            v["rating"] = rating.rate_reliability(v["summary"], replug_needed=None if healthy else True)
            ratings.append(v["rating"])
        if not healthy:
            errors.append({"camera": cam["key"], "warning": "camera did not stream after the cycle variants "
                                                             "(possible replug-needed state)"})
        per.append(crec)
    m = {"cameras": per, "mode_scope": suitectx.scope_for_test(ctx.openable(), a)}
    worst = rating.worst(ratings)
    v = {"Reliability": {"rating": worst, "criteria": [{"criterion": "worst camera x variant (plan 3 reliability)",
                                                        "met": worst == "yes", "detail": worst}],
                         "evidence": {c["key"]: ({v["variant"]: v["rating"]["rating"] for v in c.get("variants", [])}
                                                 if not c.get("untested") else "untested (scope)") for c in per},
                         "tier": 0, "mode_scope": mac_modescope.text(a)}}
    return results.finish_result(res, m, v, errors)
