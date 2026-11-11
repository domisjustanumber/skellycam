"""L-FMT: every format / frame size / frame interval V4L2 offers (ENUM_FMT, ENUM_FRAMESIZES,
ENUM_FRAMEINTERVALS) versus the USB descriptors parsed from sysfs 'descriptors' (plan 6.2 FMT, G-MJPEG coverage).

ENUM_* ioctls are answered from the parsed descriptors and cause no USB traffic. Also lists the metadata node's
formats (UVCH; UVCM = MSXU 1.5 on 6.17+ when the camera implements the Microsoft XU).
"""
from __future__ import annotations

from typing import Any

from common import rating, results
import analysis
from tutil import outcome, worker_error

TEST = "L-FMT"
INFO = {"goal": "G-MJPEG coverage", "summary": "V4L2 ENUM_* vs sysfs descriptors per camera; metadata formats",
        "opens_cameras": "read-only enumeration"}


def plan(ctx) -> dict[str, Any]:
    return {"child_runs": len(ctx.cameras), "est_seconds": 3 * len(ctx.cameras) + 1,
            "steps": ["camworker formats per camera", "diff with descriptors"]}


def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST)
    errors: list[dict] = []
    per_cam: dict[str, Any] = {}
    verdicts: dict[str, Any] = {}
    for c in ctx.cameras:
        args = ["formats", "--device", c["node"]] + (["--meta-node", c["meta_node"]] if c.get("meta_node") else [])
        r = ctx.camcmd(ctx.worker_cmd(*args), timeout_s=60)
        j = r.get("json") or {}
        err = worker_error(r)
        entry: dict[str, Any] = {"child": outcome(r)}
        if err or not j.get("formats"):
            entry["error"] = err
            errors.append({"camera": c["key"], "stage": "formats", "error": err})
            per_cam[c["key"]] = entry
            verdicts[c["key"]] = rating.untested("format listing failed", err)
            continue
        v4 = analysis.v4l2_mode_set(j["formats"])
        de = analysis.desc_mode_set(c["descriptors"])
        diff = analysis.diff_modes(v4, de)
        mj = analysis.mode_list(v4, "MJPG")
        entry.update({"v4l2_formats": [{"fourcc": f["fourcc"], "description": f["description"],
                                        "compressed": f["compressed"], "n_sizes": len(f.get("sizes") or [])}
                                       for f in j["formats"]],
                      "v4l2_formats_full": j["formats"], "descriptor_modes": {"%s %dx%d" % k: v for k, v in de.items()},
                      "diff": diff, "mjpeg_modes_v4l2": mj, "n_mjpeg_modes": len(mj),
                      "mjpeg_sizes": sorted({(m["w"], m["h"]) for m in mj}),
                      "meta_formats": j.get("meta_formats"),
                      "msxu_1_5_metadata": any((f.get("fourcc") == "UVCM") for f in (j.get("meta_formats") or [])),
                      "uvch_metadata": any((f.get("fourcc") == "UVCH") for f in (j.get("meta_formats") or [])),
                      "descriptor_error": c["descriptors"].get("error"), "enum_ms": j.get("elapsed_ms")})
        ctx.shared.setdefault("v4l2_modes", {})[c["key"]] = mj
        per_cam[c["key"]] = entry
        crit = [{"criterion": "V4L2 sizes and rates equal the descriptors", "met": diff["identical"],
                 "detail": {k: diff[k] for k in ("missing_sizes", "extra_sizes")} | {
                     "rate_differences": len(diff["rate_differences"])}},
                {"criterion": "at least one MJPEG mode", "met": bool(mj), "detail": len(mj)}]
        verdicts[c["key"]] = {"rating": "yes" if diff["identical"] and mj else "partial", "criteria": crit,
                              "evidence": {"n_modes_v4l2": diff["n_modes_v4l2"],
                                           "n_modes_descriptors": diff["n_modes_descriptors"]}}
    from suitectx import combine
    results.finish_result(res, measurements={"cameras": per_cam},
                          verdicts={"FMT": combine(verdicts, "V4L2 vs descriptors") if verdicts
                                    else rating.untested("no camera")}, errors=errors)
    return res
