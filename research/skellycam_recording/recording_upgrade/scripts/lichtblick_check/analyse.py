"""Summarise check_lichtblick.py JSON logs: frame checks and audio click-to-playhead offsets.

  python -I analyse.py <t0_ns> <run.json> [<run.json> ...]  > summary.json

Audio offset: for each scheduled AudioBufferSourceNode whose buffer holds a click, the context time the
click plays (when + (click/sr - offset)/rate) is mapped to performance.now() with the (perf, currentTime)
pair taken at start(); the playhead at that moment is interpolated from the logged playhead text.
offset = playhead - nearest whole second (the click's true time). Positive = audio late vs the playhead.
"""
import gzip, json, statistics, sys
from decimal import Decimal

T0 = int(sys.argv[1])


def series(ph):
    out = []
    for perf, txt in ph:
        try:
            out.append((perf, (int(Decimal(txt) * 10**9) - T0) / 1e9))
        except Exception:
            pass
    return out


def at(ser, p):
    for (p0, v0), (p1, v1) in zip(ser, ser[1:]):
        if p0 <= p < p1:
            return v0 + (v1 - v0) * (p - p0) / (p1 - p0) if p1 - p0 < 100 else v0
    return None


def stats(xs):
    if not xs:
        return None
    return {"n": len(xs), "mean": round(statistics.mean(xs), 2), "sd": round(statistics.pstdev(xs), 2),
            "min": round(min(xs), 2), "max": round(max(xs), 2), "median": round(statistics.median(xs), 2)}


def segments(steps):
    """(start_perf, label) for each control action, to tag audio events."""
    return [(s["perf"], s["label"]) for s in steps if "perf" in s]


summary = {}
for path in sys.argv[2:]:
    R = json.load((gzip.open if path.endswith(".gz") else open)(path, "rt", encoding="utf8"))
    checks = [s for s in R["steps"] if "ok" in s]
    res = {"frame_checks": f"{sum(bool(s['ok']) for s in checks)}/{len(checks)}",
           "frame_check_failures": [s for s in checks if not s["ok"]],
           "console_errors": sorted({c[2][:160] for c in R["console"] if c[1] == "error"}),
           "console_warnings": sorted({c[2][:120] for c in R["console"] if c[1] == "warning" and "GL Driver" not in c[2]}),
           "pageerrors": R["pageerrors"], "blocked": sorted(set(R["blocked"]))}
    I = R.get("instr") or {}
    ser = series(I.get("ph", []))
    stops = {}
    for s in I.get("stops", []):
        stops.setdefault(s["id"], s["when"] or s["ctxNow"])
    seg = segments(R["steps"])
    speed, rows = 1.0, []
    sp_at = []
    for p, lab in seg:
        if lab.startswith("speed "):
            speed = float(lab.split()[1])
        sp_at.append((p, lab, speed))
    for s in I.get("starts", []):
        lab, spd = "before", 1.0
        for p, l, sp in sp_at:
            if p <= s["perf"]:
                lab, spd = l, sp
        row = {"seg": lab, "speed": spd, "sr": s["sr"], "len": s["len"], "rate": s["rate"],
               "lead_ms": round((s["when"] - s["ctxNow"]) * 1000, 2), "skip_ms": round(s["offset"] * 1000, 2)}
        if s["click"] >= 0 and s["click"] / s["sr"] >= s["offset"]:
            heard = s["when"] + (s["click"] / s["sr"] - s["offset"]) / s["rate"]
            cut = s["id"] in stops and stops[s["id"]] <= heard
            hp = s["perf"] + (heard - s["ctxNow"]) * 1000
            ph = at(ser, hp)
            if ph is not None and not cut:
                n = round(ph)
                row.update(_hp=hp, click_media_s=n, offset_media_ms=round((ph - n) * 1000, 1), offset_wall_ms=round((ph - n) * 1000 / spd, 1))
                if s.get("outPerf"):
                    ph2 = at(ser, s["outPerf"] + (heard - s["outCtx"]) * 1000)
                    if ph2 is not None:
                        row["offset_media_ms_outts"] = round((ph2 - n) * 1000, 1)
            row["cut_before_click"] = cut
        rows.append(row)
    res["audio_ctx"] = I.get("ctx", [])[:6]
    res["audio_decoder_configs"] = I.get("dec", [])
    res["audio_starts"] = len(rows)
    res["audio_buffer_rates"] = sorted({(r["sr"], r["len"]) for r in rows})
    res["audio_stops"] = len(I.get("stops", []))
    by = {}
    for r in rows:
        if "offset_media_ms" in r:
            by.setdefault(r["seg"], []).append(r)
    res["offset_by_segment"] = {k: {"speed": v[0]["speed"], "media_ms": stats([r["offset_media_ms"] for r in v]),
                                    "wall_ms": stats([r["offset_wall_ms"] for r in v]),
                                    "media_ms_outts": stats([r["offset_media_ms_outts"] for r in v if "offset_media_ms_outts" in r]),
                                    "clicks": [r["click_media_s"] for r in v]} for k, v in by.items()}
    res["lead_ms"] = stats([r["lead_ms"] for r in rows])
    # Image: when the cam0 canvas turns white (flash frame at each whole second) vs the playhead
    flashes = []
    for p, on in I.get("flash", []):
        ph = at(ser, p)
        if on and ph is not None:
            n = round(ph)
            seg_l = [l for q, l, _ in sp_at if q <= p]
            flashes.append({"perf": p, "sec": n, "img_offset_ms": round((ph - n) * 1000, 1), "seg": seg_l[-1] if seg_l else "before"})
    fb = {}
    for f in flashes:
        fb.setdefault(f["seg"], []).append(f["img_offset_ms"])
    res["image_flash_offset_by_segment_ms"] = {k: stats(v) for k, v in fb.items()}
    # A/V: click play time minus flash display time, same whole second, same segment, wall ms
    av = {}
    for r in rows:
        if "click_media_s" not in r:
            continue
        m = [f for f in flashes if f["sec"] == r["click_media_s"] and f["seg"] == r["seg"]]
        if m:
            av.setdefault(r["seg"], []).append(round(r["_hp"] - m[-1]["perf"], 1))
    res["av_click_minus_flash_wall_ms"] = {k: stats(v) for k, v in av.items()}
    # Decoder: input vs output timestamp steps (us); the app passes its schedule time through the timestamp
    di, do = I.get("decIn", []), I.get("decOut", [])
    def seg_of(p):
        l = [lab for q, lab, _ in sp_at if q <= p]
        return l[-1] if l else "before"

    def steps(xs):
        """Median timestamp step (us) per segment, ignoring jumps (re-syncs)."""
        g = {}
        for a_, b_ in zip(xs, xs[1:]):
            if seg_of(a_[0]) == seg_of(b_[0]) and 0 < b_[1] - a_[1] < 100000:
                g.setdefault(seg_of(a_[0]), []).append(b_[1] - a_[1])
        return {k: {"n": len(v), "median": statistics.median(v)} for k, v in g.items()}
    if di:
        res["decoder_in_out"] = {"inputs": len(di), "outputs": len(do), "in_step_us": steps(di), "out_step_us": steps(do),
                                 "out_frames": sorted({o[2] for o in do}), "out_rates": sorted({o[3] for o in do})}
    res["skipped_or_cut_clicks"] = sum(1 for r in rows if r.get("cut_before_click"))
    summary[R["name"]] = res
print(json.dumps(summary, indent=1, ensure_ascii=False))
