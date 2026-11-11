"""L-KIYO: Razer Kiyo Pro control requests polled over time (plan 6.2 KIYO; linux.md Kiyo section, LX-KP1).

Every --kiyo-interval-s (10 s) for --kiyo-minutes (5): QUERY_EXT_CTRL + G_EXT_CTRLS of a few controls (camworker
'controls', per-call watchdog), the USB power/LPM state from sysfs (power/runtime_status,
usb3_hardware_lpm_u1/u2, the port's usb3_lpm_permit), plug-in age (power/connected_duration), devnum (re-arrival)
and the kernel's USB_QUIRK_NO_LPM bit in the device 'quirks' attribute (mainline 7.0, stable 6.12.81 / 6.18.34 /
6.19.12; unknown on Ubuntu's 6.8 GA). Every third poll adds a 1 s stream and a focus set to its current value with
autofocus off (an original-Kiyo report crashed on focus sets); autofocus is restored at the end. When it stops
answering (EPIPE / ETIMEDOUT / EPROTO) is the result. The LPM-off arm (usbcore.quirks=1532:0e05:k) is attended
item A4: detected here, never written.
"""
from __future__ import annotations

import time
from typing import Any

from common import rating, results
import sysfs
import v4l2
import scope
from tutil import gate, mode_args, mode_text, worker_error

TEST = "L-KIYO"
INFO = {"goal": "Kiyo failure signature", "summary": "control poll over time + LPM state + NO_LPM quirk; stream and "
                                                     "focus set every third poll", "opens_cameras": True}
IDS = ("exposure_time_absolute", "brightness", "focus_absolute", "auto_exposure", "focus_automatic_continuous")


def plan(ctx) -> dict[str, Any]:
    k = [c for c in ctx.cameras if c["is_kiyo"]]
    polls = int(ctx.args.kiyo_minutes * 60 / ctx.args.kiyo_interval_s) + 1
    return {"child_runs": len(k) * polls * 2, "est_seconds": round(len(k) * ctx.args.kiyo_minutes * 60 + 10),
            "steps": [f"{polls} polls per Kiyo every {ctx.args.kiyo_interval_s}s"] if k else
            ["no Kiyo Pro attached: test records 'untested'"]}


def power_state(cam: dict[str, Any]) -> dict[str, Any]:
    ud = sysfs.P(cam["sysfs_dir"])
    q = sysfs.rd(ud / "quirks")
    try:
        qv = int(q, 16) if q else None
    except ValueError:
        qv = None
    port_permit = sysfs.rd(ud / "port" / "usb3_lpm_permit")
    return {"runtime_status": sysfs.rd(ud / "power/runtime_status"), "control": sysfs.rd(ud / "power/control"),
            "lpm_u1": sysfs.rd(ud / "power/usb3_hardware_lpm_u1"), "lpm_u2": sysfs.rd(ud / "power/usb3_hardware_lpm_u2"),
            "port_usb3_lpm_permit": port_permit, "connected_duration_ms": sysfs.rd_int(ud / "power/connected_duration"),
            "devnum": sysfs.rd(ud / "devnum"), "speed": sysfs.rd(ud / "speed"), "quirks": q,
            "no_lpm_quirk": bool(qv & sysfs.USB_QUIRK_NO_LPM) if qv is not None else None}


def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST, [c for c in ctx.cameras if c["is_kiyo"]])
    kiyos = [c for c in ctx.cameras if c["is_kiyo"]]
    if not kiyos:
        results.finish_result(res, measurements={"kiyo_present": False},
                              verdicts={"KIYO": rating.untested("no Razer Kiyo Pro (1532:0E05) attached")})
        return res
    errors: list[dict] = []
    per: dict[str, Any] = {}
    verdicts = {}
    ids = ",".join(f"0x{v4l2.CID[n]:08x}" for n in IDS)
    for cam in kiyos:
        skip = gate(ctx, cam, TEST)
        if skip:
            per[cam["key"]] = skip
            verdicts[cam["key"]] = rating.untested(skip["reason"])
            continue
        # mode scope (plan 6): the 1 s stream probe uses the in-scope default (earlier: 640x480@30 with --all-modes)
        pk = scope.picks(ctx, cam)
        mode = pk["ctrl_mode"]
        per.setdefault(cam["key"], {})["stream_probe_mode_scope"] = {
            **pk["record"], "mode": mode_text(mode) if mode else None,
            "note": None if mode else "no in-scope MJPEG mode: stream probe skipped (scope), control polls still run"}
        polls = []
        t_end = time.monotonic() + ctx.args.kiyo_minutes * 60
        i = 0
        af_id = f"0x{v4l2.CID['focus_automatic_continuous']:08x}"
        af_orig = None
        af_touched = False
        cur = cam
        try:
            while True:
                t0 = time.monotonic()
                ctx.refresh_cameras()
                cur = next((c for c in ctx.cameras if c["key"] == cam["key"]), cam)
                p: dict[str, Any] = {"i": i, "utc": results.utc_now_iso(), "power": power_state(cur),
                                     "node": cur["node"]}
                r = ctx.camcmd(ctx.worker_cmd("controls", "--device", cur["node"], "--ids", ids, "--no-menus",
                                              "--op-timeout-s", "8", "--walk-timeout-s", "40",
                                              "--total-timeout-s", "50"), timeout_s=60)
                j = r.get("json") or {}
                ctrls = j.get("controls") or []
                errs = [{"id": c.get("id_hex") or c.get("probe_id") or c.get("after_id"), "name": c.get("name"),
                         "errno": c.get("get_errno") or c.get("query_errno"), "ms": c.get("get_ms")}
                        for c in ctrls if c.get("get_errno") or c.get("query_errno")]
                p["controls"] = {"ok": bool(ctrls) and not errs and not worker_error(r), "n": len(ctrls),
                                 "errors": errs, "error": worker_error(r), "elapsed_ms": j.get("elapsed_ms"),
                                 "walk_partial": j.get("walk_partial"),
                                 "values": {c["id_hex"]: c.get("value") for c in ctrls if c.get("id_hex")}}
                if af_orig is None:
                    af_orig = p["controls"]["values"].get(af_id)
                if i % 3 == 2 and mode:
                    od = ctx.test_dir(TEST, ctx.slug(cam), f"poll_{i:03d}")
                    rs = ctx.camcmd(ctx.worker_cmd("capture", "--device", cur["node"], *mode_args(mode),
                                                   "--seconds", 1.0, "--out-dir", od), timeout_s=30)
                    js = rs.get("json") or {}
                    p["stream"] = {"frames": ((js.get("stream") or {}).get("counts") or {}).get("frames", 0),
                                   "error": worker_error(rs),
                                   "first_frame_ms": (js.get("timings") or {}).get("first_frame_ms")}
                    fa = p["controls"]["values"].get(f"0x{v4l2.CID['focus_absolute']:08x}")
                    if fa is not None:
                        af_touched = True
                        rf = ctx.camcmd(ctx.worker_cmd(
                            "controls", "--device", cur["node"], "--no-walk", "--total-timeout-s", "35", "--set",
                            f"{af_id}=0,0x{v4l2.CID['focus_absolute']:08x}={fa}"), timeout_s=40)
                        p["focus_set"] = {"sets": (rf.get("json") or {}).get("sets"), "error": worker_error(rf)}
                p["poll_s"] = round(time.monotonic() - t0, 2)
                polls.append(p)
                ctx.log(f"Kiyo poll {i}: controls ok={p['controls']['ok']} lpm={p['power'].get('lpm_u1')}/"
                        f"{p['power'].get('lpm_u2')} age={p['power'].get('connected_duration_ms')}")
                i += 1
                if time.monotonic() + ctx.args.kiyo_interval_s > t_end:
                    break
                time.sleep(max(0.0, ctx.args.kiyo_interval_s - (time.monotonic() - t0)))
        finally:
            # autofocus back on whenever this test turned it off: the original value if it was read, else the
            # control's default from the L-CTRL-LIST walk, else 1 (on)
            if af_touched:
                val = af_orig
                if val is None:
                    walk = ctx.shared.get("controls", {}).get(cam["key"]) or []
                    val = next((c.get("default") for c in walk if c.get("id") == v4l2.CID["focus_automatic_continuous"]),
                               None)
                val = 1 if val is None else val
                rr = ctx.camcmd(ctx.worker_cmd("controls", "--device", cur["node"], "--no-walk",
                                               "--total-timeout-s", "35", "--set", f"{af_id}={val}"), timeout_s=40)
                rsets = (rr.get("json") or {}).get("sets") or []
                per.setdefault(cam["key"], {})["af_restore"] = {"value": val, "from_original": af_orig is not None,
                                                               "sets": rsets, "error": worker_error(rr)}
                if worker_error(rr) or any(s.get("errno") for s in rsets):
                    errors.append({"camera": cam["key"], "stage": "restore autofocus", "error": worker_error(rr),
                                   "sets": rsets})
        fails = [p for p in polls if not p["controls"]["ok"] or (p.get("stream") and not p["stream"]["frames"])]
        first_fail = fails[0] if fails else None
        rec = None
        if first_fail:
            later = [p for p in polls if p["i"] > first_fail["i"]]
            rec = any(p["controls"]["ok"] for p in later) if later else None
        errnos = sorted({e["errno"] for p in polls for e in p["controls"]["errors"]} |
                        {(p["controls"]["error"] or {}).get("errno_name") for p in polls if p["controls"]["error"]}
                        - {None})
        summ = {"polls": len(polls), "failed_polls": len(fails),
                "first_failure": {"i": first_fail["i"], "utc": first_fail["utc"],
                                  "age_ms": first_fail["power"].get("connected_duration_ms")} if first_fail else None,
                "recovered_later": rec, "errnos": errnos,
                "lpm_states_seen": sorted({f"{p['power'].get('lpm_u1')}/{p['power'].get('lpm_u2')}" for p in polls}),
                "no_lpm_quirk": polls[0]["power"].get("no_lpm_quirk") if polls else None,
                "rearrivals": len({p["power"].get("devnum") for p in polls}) - 1 if polls else 0}
        per.setdefault(cam["key"], {}).update({"summary": summ, "polls": polls})
        crit = [{"criterion": "every control poll answered", "met": not [p for p in polls if not p["controls"]["ok"]],
                 "detail": summ}, {"criterion": "streams on every third poll",
                                   "met": all(p["stream"]["frames"] for p in polls if p.get("stream")) or None,
                                   "detail": None}]
        verdicts[cam["key"]] = {"rating": "yes" if not fails else ("partial" if rec else "no"), "criteria": crit,
                                "evidence": summ}
    from suitectx import combine
    results.finish_result(res, measurements={"cameras": per, "interval_s": ctx.args.kiyo_interval_s,
                                             "minutes": ctx.args.kiyo_minutes},
                          verdicts={"KIYO": combine(verdicts, "Kiyo control poll")}, errors=errors)
    return res
