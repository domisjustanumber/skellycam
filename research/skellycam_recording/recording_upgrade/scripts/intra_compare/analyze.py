# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
"""Build rate-quality curves, matched settings and the refine plan from results/intra_compare/raw/*.json.

Targets (justified in NOTES.md):
  A  camera-equivalent: SSIM-Y = mean SSIM-Y that libjpeg-turbo reaches at the cameras' IJG-equivalent quality on the
     same camera models' raw YUY2 1080p frames (camera_jpeg_quality.json, camera_equivalent_on_yuy2).
  B  PSNR-Y 45 dB (the task's suggested second point; on this content it lies BELOW A, so it is the compact point).
Matching rule: the swept knob value whose mean metric is closest to the target (ties -> fewer bytes). Points count only
if ok, all frames decoded and every frame verified intra. bytes_at_target_interp = log-linear interpolation of
bytes/frame between the two swept points that bracket the target (labelled interpolated).
Writes curves.json, curves.md, matched_settings.json, refine_plan.json, verification.md in results/intra_compare/.
  uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_compare/analyze.py
"""
from __future__ import annotations

import glob
import json
import math
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parents[2] / "results/intra_compare"
INPUT_ORDER = ["yuy2_1080p", "yuy2_720p", "mjpeg_720p", "mjpeg_1080p"]
PSNR_B = 45.0
PT = {"0": "NONE", "1": "I", "2": "P", "3": "B", "4": "S", "5": "SI", "6": "SP", "7": "BI"}


def load() -> dict:
    d: dict = {}
    for f in sorted(glob.glob(str(R / "raw" / "*.json"))):
        doc = json.loads(Path(f).read_text())
        d.setdefault(doc["path"], {})[doc["input"]] = doc
    return d


def per_cam(pt: dict) -> dict:
    out: dict = {}
    for cam in sorted({x["cam"] for x in pt.get("per_frame", [])}):
        xs = [x for x in pt["per_frame"] if x["cam"] == cam]
        out[cam] = {"frames": len(xs), "bytes_per_frame": round(float(np.mean([x["bytes"] for x in xs])), 1),
                    "psnr_y": round(float(np.mean([x["psnr_y"] for x in xs])), 3),
                    "ssim_y": round(float(np.mean([x["ssim_y"] for x in xs])), 5)}
    return out


def valid(pt: dict) -> bool:
    return bool(pt.get("ok") and pt.get("frames_ok") and pt.get("all_intra"))


def nearest(points: list[dict], key: str, target: float) -> dict | None:
    c = [p for p in points if valid(p)]
    if not c:
        return None
    return min(c, key=lambda p: (round(abs(p[key] - target), 9), p["bytes_per_frame"]))


def bracket(points: list[dict], key: str, target: float):
    c = sorted([p for p in points if valid(p)], key=lambda p: p["bytes_per_frame"])
    for a, b in zip(c, c[1:]):
        if (a[key] - target) * (b[key] - target) <= 0 and a[key] != b[key]:
            return a, b
    return None


def interp_bytes(points, key, target):
    br = bracket(points, key, target)
    if not br:
        return None
    a, b = br
    t = (target - a[key]) / (b[key] - a[key])
    return round(math.exp(math.log(a["bytes_per_frame"]) + t * (math.log(b["bytes_per_frame"]) - math.log(a["bytes_per_frame"]))), 0)


def main() -> None:
    data = load()
    cam = json.loads((R / "camera_jpeg_quality.json").read_text())
    ce = cam["camera_equivalent_on_yuy2"]
    ssim_a = round(float(np.mean([r["ssim_y"] for r in ce])), 4)
    psnr_a_info = round(float(np.mean([r["psnr_y"] for r in ce])), 2)
    passthrough = {
        "mjpeg_720p": round((cam["sets"]["c930e_720p_flash"]["bytes_per_frame_mean"] * 120
                             + cam["sets"]["c922_720p_flash"]["bytes_per_frame_mean"] * 120) / 240, 1),
        "mjpeg_1080p": round((cam["sets"]["c930e_1080p"]["bytes_per_frame_mean"]
                              + cam["sets"]["c922_1080p"]["bytes_per_frame_mean"]) / 2, 1)}
    curves: dict = {"targets": {"A_ssim_y": ssim_a, "A_info_psnr_y_of_camera_equivalent": psnr_a_info, "B_psnr_y": PSNR_B},
                    "camera_passthrough_bytes_per_frame": passthrough, "paths": {}}
    matched: dict = {"_meta": {
        "generated_by": "scripts/intra_compare/analyze.py", "pyav": "19.0.2",
        "target_A": f"ssim_y closest to {ssim_a} (camera-equivalent: libjpeg-turbo at the cameras' IJG-equivalent q94 on "
                    f"the same camera models' raw YUY2 1080p frames; camera_jpeg_quality.json)",
        "target_B": f"psnr_y closest to {PSNR_B} dB, stored under key 'psnr45' (lower quality than A on this content)",
        "apply": "open the encoder with exactly 'options' (PyAV CodecContext.options / simplejpeg kwargs / nvimgcodec "
                 "EncodeParams), pix_fmt 'pix_fmt_fed', gop_size as given, max_b_frames=0; JPEG paths are fed full-range "
                 "samples, H.264/HEVC paths limited-range (NOTES.md section 2)",
        "input_classes": "yuy2_1080p, yuy2_720p (derived by swscale), mjpeg_720p, mjpeg_1080p (camera JPEG decoded)",
        "camera_passthrough_bytes_per_frame": passthrough,
        "metric_note": "for mjpeg_* classes the metrics are generation loss vs the decoded camera frame"}}
    refine: dict = {}
    verify_rows = []
    for pid in sorted(data):
        curves["paths"][pid] = {}
        for inp in INPUT_ORDER:
            doc = data[pid].get(inp)
            if not doc:
                continue
            pts = doc["points"]
            for p in pts:
                verify_rows.append((pid, inp, p))
            slim = []
            for p in pts:
                if not p.get("ok"):
                    slim.append({"value": p["value"], "ok": False, "error": p.get("error")})
                    continue
                slim.append({k: p.get(k) for k in ("value", "label", "bytes_per_frame", "psnr_y", "psnr_y_min", "ssim_y",
                                                   "ssim_y_min", "psnr_yuv_422", "psnr_yuv_fed", "all_intra", "frames_ok",
                                                   "decoded_frames", "frames_in")} | {"per_camera": per_cam(p)})
            first = next((p for p in pts if p.get("ok")), {})
            curves["paths"][pid][inp] = {"encoder": first.get("encoder"), "knob": first.get("knob"),
                                         "chroma": first.get("chroma"), "points": slim}
            okp = [p for p in pts if p.get("ok")]
            a = nearest(okp, "ssim_y", ssim_a)
            b = nearest(okp, "psnr_y", PSNR_B)

            def entry(p, target_key, target):
                return {"knob": p["knob"], "value": p["value"], "bytes_per_frame": p["bytes_per_frame"],
                        "psnr_y": p["psnr_y"], "ssim_y": p["ssim_y"], "psnr_yuv_422": p.get("psnr_yuv_422"),
                        "encoder": p["encoder"], "chroma": p["chroma"], "pix_fmt_fed": p.get("pix_fmt_fed"),
                        "gop_size": p.get("gop_size", 1), "options": p.get("options"),
                        "target": f"{target_key}={target}", "delta": round(p[target_key] - target, 5),
                        "bytes_at_target_interp": interp_bytes(okp, target_key, target)}
            if a:
                matched.setdefault(pid, {})[inp] = entry(a, "ssim_y", ssim_a)
                if b:
                    matched[pid][inp]["psnr45"] = entry(b, "psnr_y", PSNR_B)
            # refine plan: integer knob values strictly between the bracketing swept points (max 4, evenly spaced)
            vals = set()
            for key, tgt in (("ssim_y", ssim_a), ("psnr_y", PSNR_B)):
                br = bracket(okp, key, tgt)
                if br:
                    lo, hi = sorted([br[0]["value"], br[1]["value"]])
                    inner = list(range(lo + 1, hi))
                    if len(inner) > 4:
                        inner = sorted({inner[round(i * (len(inner) - 1) / 3)] for i in range(4)})
                    vals.update(inner)
                elif okp:
                    # target outside the swept range: extend the grid (JPEG q up = better; QP/qscale up = worse)
                    jpegq = "quality" in okp[0]["knob"]
                    need_worse = all(p[key] > tgt for p in okp)
                    vmin, vmax = min(p["value"] for p in okp), max(p["value"] for p in okp)
                    if jpegq:
                        ext = [v for v in (20, 30, 40, 45) if v < vmin] if need_worse else [v for v in (99, 100) if v > vmax]
                    elif "qscale" in okp[0]["knob"]:
                        ext = [v for v in (16, 20, 24, 31) if v > vmax] if need_worse else []
                    else:
                        ext = [v for v in (40, 44) if v > vmax] if need_worse else [v for v in (8, 10) if v < vmin]
                    vals.update(ext)
            have = {p["value"] for p in okp}
            vals -= have
            if vals:
                refine.setdefault(pid, {})[inp] = sorted(vals)
    (R / "curves.json").write_text(json.dumps(curves, indent=1))
    (R / "matched_settings.json").write_text(json.dumps(matched, indent=1))
    (R / "refine_plan.json").write_text(json.dumps(refine, indent=1))
    # ---------------- curves.md
    L = ["# intra_compare: rate-quality curves (PyAV 19.0.2, functional, no timing)", "",
         "Generated by `scripts/intra_compare/analyze.py` from `raw/*.json` (written by `sweep.py`). Means over all frames "
         "of the input class (per-camera values in `curves.json`). PSNR-Y / SSIM-Y: decoded Y vs source Y in the source "
         "domain. PSNR-YUV 4:2:2: vs the 4:2:2 source (4:2:0 output chroma upsampled). PSNR-YUV fed: vs the frame fed "
         "(codec-only loss; n/a for nvJPEG, fed RGB). For mjpeg_* classes the reference is the decoded camera frame "
         "(generation loss).", "",
         f"Targets: A = SSIM-Y {ssim_a} (camera-equivalent); B = PSNR-Y {PSNR_B} dB. Camera passthrough bytes/frame: "
         f"mjpeg_720p {passthrough['mjpeg_720p']}, mjpeg_1080p {passthrough['mjpeg_1080p']}.", ""]
    for inp in INPUT_ORDER:
        L += [f"## {inp}", "", "| path | knob | value | bytes/frame | PSNR-Y (min) | SSIM-Y (min) | PSNR-YUV 4:2:2 | PSNR-YUV fed | intra/frames ok |",
              "|---|---|---|---|---|---|---|---|---|"]
        for pid in sorted(curves["paths"]):
            c = curves["paths"][pid].get(inp)
            if not c:
                continue
            for p in c["points"]:
                if not p.get("ok", True) and "error" in p:
                    L.append(f"| {pid} | {c['knob']} | {p['value']} | FAILED: {p['error'][:80]} | | | | | |")
                    continue
                L.append(f"| {pid} | {c['knob']} | {p['value']} | {p['bytes_per_frame']:.0f} | {p['psnr_y']:.2f} ({p['psnr_y_min']:.2f}) | "
                         f"{p['ssim_y']:.4f} ({p['ssim_y_min']:.4f}) | {p['psnr_yuv_422']:.2f} | "
                         f"{'' if p.get('psnr_yuv_fed') is None else format(p['psnr_yuv_fed'], '.2f')} | "
                         f"{'yes' if p['all_intra'] and p['frames_ok'] else 'NO'} |")
        L.append("")
    (R / "curves.md").write_text("\n".join(L) + "\n")
    # ---------------- matched_summary.md (head to head at matched quality)
    M = ["# intra_compare: head to head at matched quality (PyAV 19.0.2, functional, no timing)", "",
         "Generated by `scripts/intra_compare/analyze.py`. 'chosen' = the swept knob value closest to the target "
         "(written to matched_settings.json); 'bytes@target' = log-linear interpolation between the two swept points "
         "that bracket the target (interpolated, not measured at that exact quality; '-' = target not bracketed, the "
         "chosen point's bytes are used for the ratios). Ratios are against jpeg_turbo_422 (libjpeg-turbo 4:2:2, the "
         "CPU JPEG baseline) and, for mjpeg_* classes, against the camera's own JPEG bytes (passthrough, no re-encode).", ""]
    for tkey, tname, tval, sub in (("ssim_y", "A: SSIM-Y", ssim_a, None), ("psnr_y", "B: PSNR-Y", PSNR_B, "psnr45")):
        M += [f"## Target {tname} = {tval}", ""]
        for inp in INPUT_ORDER:
            pt = passthrough.get(inp)
            M += [f"### {inp}" + (f" (camera passthrough {pt:.0f} B/frame)" if pt else ""), "",
                  "| path | knob = value | bytes/frame (chosen) | PSNR-Y | SSIM-Y | PSNR-YUV 4:2:2 | bytes@target (interp) | x jpeg_turbo_422 |" + (" x passthrough |" if pt else ""),
                  "|---|---|---|---|---|---|---|---|" + ("---|" if pt else "")]
            rows = []
            for pid in sorted(matched):
                if pid.startswith("_") or inp not in matched[pid]:
                    continue
                e = matched[pid][inp] if sub is None else matched[pid][inp].get(sub)
                if not e:
                    continue
                rows.append((pid, e))
            base = next((e for p, e in rows if p == "jpeg_turbo_422"), None)

            def bt(e):
                return e["bytes_at_target_interp"] or e["bytes_per_frame"]
            for pid, e in sorted(rows, key=lambda r: bt(r[1])):
                M.append(f"| {pid} | {e['value']} | {e['bytes_per_frame']:.0f} | {e['psnr_y']:.2f} | {e['ssim_y']:.4f} | "
                         f"{e['psnr_yuv_422']:.2f} | {'-' if e['bytes_at_target_interp'] is None else format(e['bytes_at_target_interp'], '.0f')} | "
                         f"{(bt(e) / bt(base)):.2f} |" + (f" {bt(e) / pt:.2f} |" if pt else "") if base else "")
            M.append("")
    (R / "matched_summary.md").write_text("\n".join(M) + "\n")
    # ---------------- verification.md
    V = ["# intra_compare: decode-back and intra-only verification (PyAV 19.0.2 software decode)", "",
         "One row per (path, input class), aggregated over all knob values. H.264/HEVC: NAL types parsed from every "
         "encoder packet (Annex B); decode-back from a raw elementary-stream file with av.open(format=h264|hevc); "
         "decoder has_b_frames; decoded pict_type / key_frame per frame. JPEG: each JPEG decoded on its own with "
         "PyAV 'mjpeg' (every JPEG is an independent intra image).", "",
         "| path | input | points | all ok | frames decoded == in | all intra | NAL types seen (IDR: H.264 5, HEVC 19/20) | param sets every packet | decoder has_b_frames | decoded pict types | decoded pix_fmt | profile | stats side data quality/118 per QP (nvenc = frameAvgQP-1) | ffprobe of saved sample (inspection) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    agg: dict = {}
    for pid, inp, p in verify_rows:
        agg.setdefault((pid, inp), []).append(p)
    for (pid, inp), ps in agg.items():
        ok = all(p.get("ok") for p in ps)
        fr = all(p.get("frames_ok") for p in ps if p.get("ok"))
        intra = all(p.get("all_intra") for p in ps if p.get("ok"))
        nal = sorted({t for p in ps for s in p.get("nal_type_sets", []) for t in s})
        pse = all(p.get("param_sets_every_packet", True) for p in ps if p.get("ok"))
        hb = sorted({p.get("decoder_has_b_frames") for p in ps if "decoder_has_b_frames" in p})
        # PyAV 19 returns pict_type as the AVPictureType int (0 NONE, 1 I, 2 P, 3 B)
        pt = sorted({PT.get(str(t), str(t)) for p in ps for t in p.get("decoded_pict_types", [])})
        pf = sorted({t for p in ps for t in p.get("decoded_pix_fmts", [])})
        prof = sorted({str(p.get("decoder_profile")) for p in ps if p.get("decoder_profile")})
        qps = "; ".join(f"{p['value']}:{p.get('stats_qp_values')}" for p in ps if p.get("stats_qp_values"))
        fp = "; ".join(f"{p['value']}: has_b_frames={p['ffprobe'].get('has_b_frames')} frames={p['ffprobe'].get('ffprobe_frames')} "
                       f"key={p['ffprobe'].get('ffprobe_key_frames')} {p['ffprobe'].get('pict_types')} {p['ffprobe'].get('profile')}"
                       for p in ps if p.get("ffprobe"))
        V.append(f"| {pid} | {inp} | {len(ps)} | {ok} | {fr} | {intra} | {nal if nal else 'n/a (JPEG)'} | "
                 f"{pse if nal else 'n/a'} | {hb if hb else 'n/a'} | {pt if pt else 'n/a'} | {pf} | {prof if prof else ''} | {qps} | {fp} |")
    fails = [(pid, inp, p["value"], p.get("error")) for pid, inp, p in verify_rows if not p.get("ok")]
    V += ["", f"Failed points: {len(fails)}", ""] + [f"- {f}" for f in fails]
    (R / "verification.md").write_text("\n".join(V) + "\n")
    print("targets", curves["targets"], "refine", json.dumps(refine))


if __name__ == "__main__":
    main()
