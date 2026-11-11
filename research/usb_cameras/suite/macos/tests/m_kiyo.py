"""M-KIYO: the Razer Kiyo Pro (1532:0E05) polled every --kiyo-interval-s for --kiyo-minutes: IORegistry presence
(entry ID, sessionID), AVFoundation flags (no session), endpoint-0 GET_CUR of three controls (only with --ep0),
and one open/close cycle per poll. Records when and how it stops answering and whether streaming still works
after a control failure (plan 6.2 KIYO; macos.md MX9 and section 9). Expected macOS signatures (inferred):
kIOReturnNotResponding 0xE00002ED, kIOUSBPipeStalled 0xE000404F, kIOUSBTransactionTimeout 0xE0004051.
Attended arm (A4: USB 3 LPM off is not a macOS setting; a USB 2.0 port) is not run here."""
from __future__ import annotations

import time

import suitectx
from common import results

NAME = "M-KIYO"
POLL_CONTROLS = ("auto_exposure_mode", "brightness", "white_balance_temperature", "gain", "contrast")


def plan(ctx) -> list[str]:
    n = int(ctx.args.kiyo_minutes * 60 / ctx.args.kiyo_interval_s)
    return [f"each Kiyo: {n} polls every {ctx.args.kiyo_interval_s:g} s: ioreg state, mac_avf.py ctrl-avf, "
            + ("mac_ep0.py get (3 controls), " if ctx.ep0_enabled else "") + "mac_avf.py cycle --cycles 1 --frames 5"]


def run(ctx) -> dict:
    import mac_ioreg
    res = ctx.new_result(NAME, [c for c in ctx.cameras if c.get("is_kiyo")])
    errors: list = []
    kiyos = [c for c in ctx.cameras if c.get("is_kiyo")]
    if not kiyos:
        return results.finish_result(res, {"note": "no Razer Kiyo Pro attached"}, {}, errors)
    per = []
    for cam in kiyos:
        pu = ((cam.get("uvc") or {}).get("entities") or {}).get("processing_unit")
        ranges = ctx.store.get("ctrl_list", {}).get(cam["key"]) or {}
        names = [n for n in POLL_CONTROLS if n in ranges][:3] or list(POLL_CONTROLS[:3])
        mode = suitectx.pick_small_mode(cam) or suitectx.pick_default_mode(cam)
        polls = []
        t_end = time.monotonic() + ctx.args.kiyo_minutes * 60
        first_ctrl_fail = first_stream_fail = None
        i = 0
        while time.monotonic() < t_end:
            t0 = time.monotonic()
            p: dict = {"i": i, "utc": results.utc_now_iso()}
            st = mac_ioreg.read_device_states(runner=lambda argv, t: ctx.runner(argv, t))
            p["ioreg"] = (st.get("devices") or {}).get(cam.get("location_hex"))
            if cam.get("unique_id"):
                a = ctx.avf(["ctrl-avf", "--device", cam["unique_id"]], 20, label=f"kiyo avf {i}")
                aj = a.get("json") or {}
                p["avf_flags_ok"] = bool(aj.get("ok"))
                p["avf_error"] = aj.get("error") if not aj.get("ok") else None
            if ctx.ep0_enabled and cam.get("location_hex"):
                e = ctx.ep0(cam, "get", ["--controls", ",".join(names)], timeout_s=20)
                ej = e.get("json") or {}
                p["ep0"] = {"ok": ej.get("ok"), "timed_out": e.get("timed_out"),
                            "values": [{k: v.get(k) for k in ("name", "value", "rc_name", "ms")} for v in ej.get("values") or []],
                            "setup_error": (ej.get("setup") or {}).get("error") if ej.get("setup") else ej.get("error")}
                if not ej.get("ok") and first_ctrl_fail is None:
                    first_ctrl_fail = {"poll": i, "utc": p["utc"], "signature": p["ep0"]}
            if cam.get("unique_id") and mode:
                c = ctx.avf(["cycle", "--device", cam["unique_id"], "--cycles", 1, "--frames", 5, "--timeout-ms", 5000,
                             "--cycle-timeout-s", 20] + suitectx.avf_mode_args(mode), 35, label=f"kiyo cycle {i}")
                cj = c.get("json") or {}
                row = (cj.get("rows") or [{}])[0] if cj.get("rows") else {}
                p["cycle"] = {"ok": bool(cj.get("ok")), "first_frame_ms": row.get("first_frame_ms"),
                              "frames": row.get("frames"), "stage_failed": row.get("stage_failed"),
                              "timed_out": c.get("timed_out"), "code": row.get("code")}
                if not cj.get("ok") and first_stream_fail is None:
                    first_stream_fail = {"poll": i, "utc": p["utc"], "signature": p["cycle"]}
            polls.append(p)
            i += 1
            time.sleep(max(0.0, ctx.args.kiyo_interval_s - (time.monotonic() - t0)))
        after_ctrl_fail = [p for p in polls if first_ctrl_fail and p["i"] > first_ctrl_fail["poll"]]
        per.append({"key": cam["key"], "controls_polled": names if ctx.ep0_enabled else None, "polls": polls,
                    "first_control_failure": first_ctrl_fail, "first_stream_failure": first_stream_fail,
                    "streaming_after_control_failure": (all((p.get("cycle") or {}).get("ok") for p in after_ctrl_fail)
                                                        if after_ctrl_fail else None),
                    "session_id": cam.get("session_id"),
                    "plug_in_age_note": "sessionID is recorded raw; whether it encodes the attach time is unverified",
                    "speed": cam.get("speed"), "port_path": cam.get("port_path"), "pu_entity": pu})
    return results.finish_result(res, {"cameras": per, "interval_s": ctx.args.kiyo_interval_s,
                                       "minutes": ctx.args.kiyo_minutes}, {}, errors)
