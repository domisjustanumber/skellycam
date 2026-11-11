"""M-FX: system video-effect flags per camera and format (isCenterStageActive, isPortraitEffectActive,
isStudioLightActive, isBackgroundReplacementActive, reactionEffectsInProgress, canPerformReactionEffects, plus the
class properties), sampled idle and while streaming; Edge Light (26.2+) is not exposed, so the operator's
--edge-light-off attestation is recorded (plan 6.2 FX; macos.md MX7 + verifier missed items). Gestures and the
Video menu are attended (not here)."""
from __future__ import annotations

import suitectx  # noqa: F401
from common import results

NAME = "M-FX"
ACTIVE = ("isCenterStageActive", "isPortraitEffectActive", "isStudioLightActive", "isBackgroundReplacementActive",
          "reactionEffectsInProgress")


def plan(ctx) -> list[str]:
    return ["per camera: mac_avf.py fx --stream-seconds 3 (flags idle, every 0.5 s while streaming, per-format support)"]


def run(ctx) -> dict:
    res = ctx.new_result(NAME)
    errors: list = []
    per = []
    class_props = None
    for cam in ctx.openable():
        r = ctx.avf(["fx", "--device", cam["unique_id"], "--stream-seconds", 3], 45, label=f"fx {cam['key']}")
        j = r.get("json") or {}
        class_props = class_props or j.get("class_properties")
        d = (j.get("devices") or [{}])[0]
        active = set()
        for snap in [d.get("flags_idle") or {}] + list(d.get("flags_streaming") or []):
            for k in ACTIVE:
                v = snap.get(k)
                if v not in (None, False, 0, [], "") and not (isinstance(v, str) and v.startswith("error")):
                    active.add(k)
        per.append({"key": cam["key"], "flags_idle": d.get("flags_idle"), "flags_streaming": d.get("flags_streaming"),
                    "frames_while_sampling": d.get("frames_while_sampling"), "format_support": d.get("format_support"),
                    "effects_seen_active": sorted(active), "timed_out": r.get("timed_out"), "error": j.get("error")})
        if active:
            errors.append({"camera": cam["key"], "warning": f"system video effects active: {sorted(active)}; "
                                                             "image-based results for this camera are suspect"})
    m = {"cameras": per, "class_properties": class_props,
         "edge_light": {"operator_confirmed_off": bool(ctx.args.edge_light_off),
                        "note": "not exposed by any device property; turn it off in Control Center > Video Effects"}}
    if not ctx.args.edge_light_off:
        errors.append({"warning": "Edge Light state not confirmed (pass --edge-light-off after checking Control Center)"})
    return results.finish_result(res, m, {}, errors)
