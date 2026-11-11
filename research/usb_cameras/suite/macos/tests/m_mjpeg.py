"""M-MJPEG (the gating test for macOS): every format whose mediaSubType is a JPEG type ('dmb1'/'jpeg'/'mjpa'/
'mjpb') x the videoSettings variants nil, {}, {kCVPixelBufferPixelFormatTypeKey: 'dmb1'} and Chromium's exact
dictionary ('chromium': 'dmb1' + Width + Height + AVVideoScalingModeKey ResizeAspectFill), ~3 s each: what the sample buffers carry (CMBlockBuffer JPEG vs CVPixelBuffer), SOI/EOI, strict decode,
SOF0 size, fps, CPU, the JPEG header SHA-1 per variant (plan 6.2 MJPEG; macos.md section 3 and MX1).

If a camera lists no JPEG subtype at all (one 2026-09 report saw MJPEG modes offered only as decoded 420v), the
test captures the formats at the descriptor's MJPEG sizes (or the largest and smallest formats) with the same
variants, to record whether any variant gets compressed bytes back. With --ep0 a VS_COMMIT GET_CUR at +1.2 s
proves the wire format (bFormatIndex), and the IOUSBHostInterface bAlternateSetting at +1 s (no touch) feeds the
mode->alt cache used by the bandwidth model.

Mode scope (plan 6, Dom 2026-11-06): only formats with an in-scope rate (>= --min-fps 30, >= --min-height 720) are
captured, each at its highest rate; --all-modes restores every format. The scope and the number of advertised
modes it excluded are recorded per camera (measurements.mode_scope). A camera with no in-scope MJPEG format is
recorded and rated 'untested (scope)'; G-MJPEG then means "every in-scope MJPEG mode"."""
from __future__ import annotations

import suitectx
import macanalysis
import mac_modescope
from common import rating, results

NAME = "M-MJPEG"
KNOWN_QUIRKS = {("4c4a", "4a55"): "generic camera: 1080p JPEGs fail strict decode on Windows (REPORT finding 6)"}


def formats_to_test(ctx, cam: dict) -> tuple[list[dict], str]:
    fmts, why = suitectx.scoped_mjpeg_formats(cam)
    if not fmts:
        fmts = cam.get("avf_formats") or []
        why = "no JPEG subtype listed and no descriptors: largest and smallest formats"
        fmts = sorted(fmts, key=lambda f: f["w"] * f["h"])
        fmts = [fmts[0], fmts[-1]] if len(fmts) > 1 else fmts
    n_before = len(fmts)
    fmts = mac_modescope.scoped_formats(fmts, ctx.args)
    if len(fmts) < n_before:
        why += f"; {n_before - len(fmts)} format(s) outside the mode scope skipped"
    if ctx.args.mjpeg_modes == "ends" and len(fmts) > 2:
        s = sorted(fmts, key=lambda f: f["w"] * f["h"])
        fmts = [s[0], s[-1]]
    return fmts, why


def cell_fps(ctx, f: dict) -> float | None:
    """The rate a format is captured at: its highest rate (in scope by construction unless --all-modes)."""
    rs = mac_modescope.scoped_rates(f, ctx.args)
    return max(rs) if rs else suitectx.max_fps(f)


def plan(ctx) -> list[str]:
    v = ",".join(ctx.args.mjpeg_variant_list)
    out = [mac_modescope.text(ctx.args) + " (listing tests still compare every mode)",
           f"per camera x in-scope JPEG format ({ctx.args.mjpeg_modes}) x variants [{v}]: mac_avf.py capture --seconds "
           f"{ctx.args.mjpeg_seconds} --jpeg-check all --save first:2 (raw dir)",
           "schedule: 1000:probe:ioreg_alt" + (", 1200:probe:ep0_commit" if ctx.ep0_enabled else ""),
           "rate_mjpeg per camera; jpeg_bytes=False when no cell delivered JPEG block buffers; no in-scope MJPEG "
           "format -> untested (scope)"]
    for cam in ctx.openable():
        fm, why = formats_to_test(ctx, cam)
        sc = suitectx.camera_scope(cam, ctx.args)
        out.append(f"{cam['key']}: {len(fm)} format(s) to capture ({why}); advertised modes {sc['n_advertised']}, "
                   f"excluded by scope {sc['n_excluded']}")
    return out


def run(ctx) -> dict:
    res = ctx.new_result(NAME)
    errors: list = []
    cache = ctx.mode_alt_cache()
    per_cam = []
    all_modes = []
    any_jpeg = False
    for cam in ctx.openable():
        fmts, why = formats_to_test(ctx, cam)
        crec: dict = {"key": cam["key"], "is_kiyo": cam.get("is_kiyo"), "selection": why, "modes": [],
                      "mode_scope": suitectx.camera_scope(cam, ctx.args)}
        rows = []
        if not fmts:
            crec["rating"] = rating.untested(f"no in-scope MJPEG mode ({mac_modescope.text(ctx.args)}): untested (scope)",
                                             {"mode_scope": crec["mode_scope"]})
            crec["rating"]["summary_label"] = "untested (scope)"
            per_cam.append(crec)
            errors.append({"camera": cam["key"], "warning": "no in-scope MJPEG mode: untested (scope)"})
            continue
        for f in fmts:
            fps = cell_fps(ctx, f)
            mode = suitectx._mode(f, fps)
            cells: dict[str, dict] = {}
            raw_cells = {}
            for var in ctx.args.mjpeg_variant_list:
                tag = f"{suitectx.cam_tag(cam)}/{f['index']:02d}_{f['subtype']}_{f['w']}x{f['h']}_{var}"
                od, rd = ctx.subdir("mjpeg", tag), ctx.rawsub("mjpeg", tag)
                sched = ["1000:probe:ioreg_alt"] + (["1200:probe:ep0_commit"] if ctx.ep0_enabled else [])
                args = ["capture", "--device", cam["unique_id"], "--variant", var, "--seconds", ctx.args.mjpeg_seconds,
                        "--jpeg-check", "all", "--save", "first:2", "--out-dir", od, "--raw-dir", rd,
                        "--location", cam.get("location_hex") or "", "--vs-if",
                        ",".join(map(str, cam.get("vs_interfaces") or [])), "--schedule", ";".join(sched),
                        "--first-frame-timeout-s", 5] + suitectx.avf_mode_args(mode) + ctx.ep0_capture_args(cam)
                r = ctx.avf(args, ctx.args.mjpeg_seconds + 40, label=f"mjpeg {tag}")
                j = r.get("json") or {}
                cell = macanalysis.eval_cell(j, mode)
                cell.update(timed_out=r.get("timed_out"), rc=r.get("rc"), error=j.get("error"))
                for ev in j.get("schedule_events") or []:
                    if ev.get("name") == "ioreg_alt":
                        vs = [x for x in ((ev.get("result") or {}).get("interfaces") or [])
                              if x.get("subclass") == 2 and x.get("alt")]
                        cell["ioreg_alt"] = max((x["alt"] for x in vs), default=None) if vs else None
                    if ev.get("name") == "ep0_commit":
                        cell["commit"] = [s.get("commit") for s in (ev.get("result") or {}).get("streams") or []]
                cells[var] = cell
                raw_cells[var] = {k: j.get(k) for k in ("stream", "copy", "jpeg", "dropped_callbacks")}
                if cell.get("ioreg_alt") and j.get("frames"):
                    tbl = (cam.get("uvc") or {}).get("alt_table") or []
                    ent = next((a for a in tbl if a.get("alt") == cell["ioreg_alt"]), {})
                    cache.put(cam["vid"], cam["pid"], cam.get("bcd_device"),
                              "MJPG" if f["subtype"] in suitectx.JPEG_SUBTYPES else f["subtype"], f["w"], f["h"],
                              fps, cell["ioreg_alt"], ent.get("max_packet"), ent.get("mult"),
                              source="macOS IOUSBHostInterface bAlternateSetting (live-alt meaning untested)")
                if r.get("timed_out"):
                    errors.append({"camera": cam["key"], "cell": tag, "warning": "capture timed out (recorded)"})
            row = macanalysis.mode_row(mode, cells, KNOWN_QUIRKS.get((cam["vid"], cam["pid"])))
            any_jpeg |= bool(row.get("is_jpeg"))
            crec["modes"].append({"mode": mode, "cells": cells, "row": row, "details": raw_cells})
            rows.append(row)
        crec["rating"] = rating.rate_mjpeg(rows, jpeg_bytes=None if not rows else any(r.get("is_jpeg") for r in rows))
        per_cam.append(crec)
        all_modes += [dict(r, camera=cam["key"]) for r in rows]
    try:
        cache.save()
    except Exception as e:
        errors.append({"warning": f"mode-alt cache not saved: {e!r}"})
    m = {"cameras": per_cam, "variants": ctx.args.mjpeg_variant_list,
         "mode_scope": suitectx.scope_for_test(ctx.openable(), ctx.args),
         "pyav_avfoundation": "not tested: FFmpeg's avfoundation demuxer has no MJPEG path (macos.md M10)"}
    v = {"G-MJPEG": rating.rate_mjpeg(all_modes, jpeg_bytes=(any_jpeg if all_modes else None))}
    v["G-MJPEG"]["tier"] = 0
    v["G-MJPEG"]["per_camera"] = {c["key"]: c["rating"]["rating"] for c in per_cam}
    v["G-MJPEG"]["mode_scope"] = mac_modescope.text(ctx.args)
    return results.finish_result(res, m, v, errors)
