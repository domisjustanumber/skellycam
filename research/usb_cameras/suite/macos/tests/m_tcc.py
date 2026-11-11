"""M-TCC: camera permission (TCC) state and what a stream does without it (plan 6.2 macOS-only TCC; macos.md
MX8). Permission belongs to the app that launched the suite (Terminal, iTerm2, VS Code...); a process without it
is documented by one third-party run to get zero frames and NO error, so the suite checks the state first."""
from __future__ import annotations

import os

import suitectx
from common import results

NAME = "M-TCC"


def plan(ctx) -> list[str]:
    return ["mac_avf.py tcc (authorizationStatusForMediaType video/audio; --request-camera asks)",
            "if not authorized: one 2 s capture of the first camera to record the zero-frame / no-error behaviour"]


def run(ctx) -> dict:
    res = ctx.new_result(NAME)
    errors: list = []
    r = ctx.avf(["tcc"], 30, label="tcc")
    j = r.get("json") or {}
    m: dict = {"status": j, "ssh_session": bool(os.environ.get("SSH_CONNECTION")),
               "note": "over SSH there is no permission prompt; grant Camera to the terminal app locally first"}
    status = j.get("video_after") or j.get("video") or ctx.tcc
    m["video"] = status
    cams = ctx.openable()
    if status != "authorized" and cams:
        cam = cams[0]
        mode = suitectx.pick_default_mode(cam)
        args = ["capture", "--device", cam["unique_id"], "--seconds", "2", "--jpeg-check", "none",
                "--first-frame-timeout-s", "3"] + (suitectx.avf_mode_args(mode) if mode else [])
        c = ctx.avf(args, 30, label="tcc no-permission capture")
        cj = c.get("json") or {}
        m["unauthorized_capture"] = {"camera": cam["key"], "frames": cj.get("frames"),
                                     "runtime_errors": cj.get("runtime_errors"), "error": cj.get("error"),
                                     "timed_out": c.get("timed_out"), "rc": c.get("rc")}
        m["silent_zero_frames"] = (cj.get("frames") == 0 and not cj.get("runtime_errors") and not cj.get("error"))
        errors.append({"warning": f"camera permission is '{status}': every capture test will see zero frames. Grant "
                                  "Camera to the terminal app (System Settings > Privacy & Security > Camera), quit "
                                  "and reopen it, then re-run (or pass --request-camera from a local terminal)."})
    else:
        m["unauthorized_capture"] = "not run (authorized or no camera)"
    detected = status in ("authorized", "denied", "restricted", "notDetermined")
    v = {"permission_detected_before_streaming": {
        "rating": "yes" if detected else "no",
        "criteria": [{"criterion": "authorization state readable before any stream", "met": detected, "detail": status}],
        "evidence": {"video": status}}}
    return results.finish_result(res, m, v, errors)
