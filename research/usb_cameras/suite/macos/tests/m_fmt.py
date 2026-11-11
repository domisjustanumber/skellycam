"""M-FMT: AVCaptureDevice.formats (mediaSubType FourCC, size, frame-rate ranges with exact CMTimes) against the
camera's UVC descriptors: missing or extra modes, MJPEG sizes offered only as decoded subtypes (420v/yuvs/2vuy),
discrete vs continuous rates (plan 6.2 FMT; macos.md MX0).

Descriptor source, in order: an IORegistry property holding a configuration descriptor (none expected), the
suite's descriptor cache (written by an earlier --ep0 run), or, with --ep0, the device plug-in's
GetConfigurationDescriptorPtr (the OS's cached copy; no request is sent). Without any: 'descriptors unavailable'."""
from __future__ import annotations

import suitectx
from common import rating, results

NAME = "M-FMT"


def plan(ctx) -> list[str]:
    return ["AVF formats per camera (collected at discovery by mac_avf.py formats; nothing opened)",
            "descriptors: IORegistry property scan -> cache -> " + ("mac_ep0.py descriptors (GetConfigurationDescriptorPtr)"
                                                                  if ctx.ep0_enabled else "(ep0 off: cache only)"),
            "diff: descriptor (format, size, rates) vs AVF (subtype, size, ranges)"]


def get_descriptors(ctx, cam: dict, errors: list) -> tuple[dict | None, str]:
    import mac_ep0
    devs = {d["id"]: d for d in (ctx.snapshot or {}).get("devices", [])}
    d = devs.get(cam.get("device_id")) or {}
    for k, hexv in (d.get("descriptor_props") or {}).items():
        try:
            b = bytes.fromhex(hexv)
            if len(b) > 9 and b[1] == 2:
                s = mac_ep0.summarize_config(b)
                s["config_hex"], s["source"] = hexv, f"IORegistry property {k}"
                return s, s["source"]
        except Exception:
            continue
    cached = ctx.cam_desc(cam)
    if cached and cached.get("frames") is not None:
        return cached, f"cache ({cached.get('source')})"
    if ctx.ep0_enabled and cam.get("location_hex"):
        r = ctx.ep0(cam, "descriptors", timeout_s=30)
        j = r.get("json") or {}
        if j.get("ok"):
            ctx.save_desc(cam, j)
            return j, j.get("source") or "ep0"
        errors.append({"camera": cam["key"], "error": "descriptor read failed",
                       "detail": {"rc": r.get("rc"), "timed_out": r.get("timed_out"), "error": j.get("error"),
                                  "device_transport": j.get("device_transport")}})
        return None, "ep0 failed"
    return None, "unavailable (no cache; ep0 off)"


def diff(desc_frames: list[dict], avf: list[dict]) -> dict:
    by_size: dict[tuple, list[dict]] = {}
    for f in avf:
        by_size.setdefault((f["w"], f["h"]), []).append(f)
    rows = []
    for fr in desc_frames:
        size = (fr["w"], fr["h"])
        cands = by_size.get(size, [])
        subs = sorted({f["subtype"] for f in cands})
        rates = fr.get("fps") or ([x for x in fr.get("fps_range") or [] if x])
        covered = []
        for r in rates:
            covered.append(any(rg["min_fps"] - 0.05 <= r <= rg["max_fps"] + 0.05 for f in cands for rg in f.get("ranges") or []))
        rows.append({"format": fr.get("format"), "fourcc": fr.get("fourcc"), "w": fr["w"], "h": fr["h"],
                     "descriptor_rates": rates, "avf_subtypes": subs, "in_avf": bool(cands),
                     "rates_covered": covered, "all_rates_covered": all(covered) if covered else None,
                     "mjpeg_offered_as_jpeg": (bool(set(subs) & suitectx.JPEG_SUBTYPES) if fr.get("format") == "MJPEG"
                                               else None)})
    desc_sizes = {(fr["w"], fr["h"]) for fr in desc_frames}
    extra = [{"index": f["index"], "subtype": f["subtype"], "w": f["w"], "h": f["h"]} for f in avf
             if (f["w"], f["h"]) not in desc_sizes]
    mj = [r for r in rows if r["format"] == "MJPEG"]
    return {"rows": rows, "missing_in_avf": [r for r in rows if not r["in_avf"]], "extra_in_avf": extra,
            "mjpeg_sizes": len(mj), "mjpeg_sizes_offered_as_jpeg": sum(1 for r in mj if r["mjpeg_offered_as_jpeg"]),
            "mjpeg_sizes_hidden_as": sorted({s for r in mj if not r["mjpeg_offered_as_jpeg"] for s in r["avf_subtypes"]})}


def run(ctx) -> dict:
    res = ctx.new_result(NAME)
    errors: list = []
    per = []
    for cam in ctx.cameras:
        avf = cam.get("avf_formats") or []
        rec = {"key": cam["key"], "name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"), "n_avf_formats": len(avf),
               "avf_subtypes": sorted({f["subtype"] for f in avf}),
               "avf_formats": [{"index": f["index"], "subtype": f["subtype"], "w": f["w"], "h": f["h"],
                                "ranges": [[r["min_fps"], r["max_fps"]] for r in f.get("ranges") or []],
                                "discrete": f.get("discrete")} for f in avf],
               "continuous_rate_formats": sum(1 for f in avf if f.get("discrete") is False)}
        if not cam.get("unique_id"):
            rec["note"] = "not listed by AVFoundation"
        desc, src = get_descriptors(ctx, cam, errors)
        rec["descriptor_source"] = src
        if desc:
            rec["uvc_entities"] = desc.get("entities")
            rec["alt_table"] = desc.get("alt_table")
            rec["diff"] = diff(desc.get("frames") or [], avf)
            cam["uvc"] = {k: desc.get(k) for k in ("entities", "alt_table", "frames", "source")}
        per.append(rec)
    m = {"cameras": per, "jpeg_subtypes": sorted(suitectx.JPEG_SUBTYPES)}
    n_jpeg = sum(1 for p in per if set(p["avf_subtypes"]) & suitectx.JPEG_SUBTYPES)
    v = {"G-MJPEG": rating.untested("listing only; M-MJPEG captures every mode",
                                    {"cameras_with_jpeg_subtype": n_jpeg, "cameras": len(per)})}
    return results.finish_result(res, m, v, errors)
