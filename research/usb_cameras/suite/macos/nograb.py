"""Pure analysis for M-FMT-NOGRAB (plan 6.2 FMT-NOGRAB, Dom 2026-11-06): which method lists a camera's formats
correctly without grabbing the camera or starting a stream. Stdlib only; no device access; unit-tested.

Normalised mode: {"kind": "mjpeg"|"raw"|"other", "w", "h", "ranges": [[lo_fps, hi_fps], ...], "label"}.
A descriptor "unit" is one (kind, size, rate) of the USB descriptors (a continuous-interval frame is one unit
for its whole range); a method covers a unit when it lists the same kind and size with a rate range that contains
the rate (or the whole continuous range)."""
from __future__ import annotations

import statistics
from typing import Any, Iterable

JPEG_SUBTYPES = {"dmb1", "jpeg", "mjpa", "mjpb"}
OTHER_SUBTYPES = {"avc1", "hvc1", "h264", "hevc"}
KINDS = ("mjpeg", "raw", "other")


def avf_kind(subtype: Any) -> str:
    s = str(subtype or "").strip().lower()
    if s in JPEG_SUBTYPES:
        return "mjpeg"
    if s in OTHER_SUBTYPES:
        return "other"
    return "raw"


def desc_kind(fmt: Any) -> str:
    f = str(fmt or "").upper()
    if f == "MJPEG":
        return "mjpeg"
    if f == "UNCOMPRESSED":
        return "raw"
    return "other"


def modes_from_descriptor_frames(frames: Iterable[dict] | None) -> list[dict]:
    """mac_ep0.frame_list_from_uvc rows -> normalised modes."""
    out = []
    for fr in frames or []:
        if fr.get("w") is None or fr.get("h") is None:
            continue
        if fr.get("fps"):
            ranges = [[float(r), float(r)] for r in fr["fps"] if r]
        elif fr.get("fps_range") and all(x is not None for x in fr["fps_range"]):
            lo, hi = sorted(float(x) for x in fr["fps_range"])
            ranges = [[lo, hi]]
        else:
            ranges = []
        out.append({"kind": desc_kind(fr.get("format")), "w": int(fr["w"]), "h": int(fr["h"]), "ranges": ranges,
                    "continuous": bool(fr.get("fps_range")) and not fr.get("fps"),
                    "label": f"{fr.get('format')} {fr['w']}x{fr['h']}"})
    return out


def modes_from_avf(formats: Iterable[dict] | None) -> list[dict]:
    """mac_avf.py formats -> normalised modes."""
    out = []
    for f in formats or []:
        ranges = [[float(r["min_fps"]), float(r["max_fps"])] for r in f.get("ranges") or []]
        out.append({"kind": avf_kind(f.get("subtype")), "w": int(f["w"]), "h": int(f["h"]), "ranges": ranges,
                    "label": f"{f.get('subtype')} {f['w']}x{f['h']}"})
    return out


def _tol(rate: float) -> float:
    return max(0.05, 0.005 * abs(rate))


def _units(desc_modes: list[dict]) -> list[dict]:
    units = []
    for m in desc_modes:
        if m.get("continuous") and m["ranges"]:
            lo, hi = m["ranges"][0]
            units.append({"kind": m["kind"], "w": m["w"], "h": m["h"], "lo": lo, "hi": hi,
                          "text": f"{m['kind']} {m['w']}x{m['h']}@{lo:g}-{hi:g}"})
        elif m["ranges"]:
            for lo, _ in m["ranges"]:
                units.append({"kind": m["kind"], "w": m["w"], "h": m["h"], "lo": lo, "hi": lo,
                              "text": f"{m['kind']} {m['w']}x{m['h']}@{lo:g}"})
        else:
            units.append({"kind": m["kind"], "w": m["w"], "h": m["h"], "lo": None, "hi": None,
                          "text": f"{m['kind']} {m['w']}x{m['h']} (no rate)"})
    return units


def _covered(u: dict, method_modes: list[dict]) -> bool:
    for m in method_modes:
        if (m["kind"], m["w"], m["h"]) != (u["kind"], u["w"], u["h"]):
            continue
        if u["lo"] is None:
            return True
        for lo, hi in m["ranges"]:
            if lo - _tol(u["lo"]) <= u["lo"] and u["hi"] <= hi + _tol(u["hi"]):
                return True
    return False


def completeness(desc_frames: Iterable[dict] | None, method_modes: list[dict] | None) -> dict:
    """Coverage of the USB descriptors by one method's listing, per kind (MJPEG and raw separately).
    complete: True/False over every kind the descriptor has; None when there is no descriptor reference or the
    method returned nothing to compare (method_modes None)."""
    desc = modes_from_descriptor_frames(desc_frames)
    if not desc:
        return {"complete": None, "reason": "no descriptor reference (run once with --ep0 to cache them)"}
    if method_modes is None:
        return {"complete": None, "reason": "method returned no listing"}
    units = _units(desc)
    per: dict[str, dict] = {}
    for k in KINDS:
        ku = [u for u in units if u["kind"] == k]
        if not ku:
            per[k] = {"n": 0, "n_covered": 0, "missing": [], "complete": None}
            continue
        miss = [u["text"] for u in ku if not _covered(u, method_modes)]
        per[k] = {"n": len(ku), "n_covered": len(ku) - len(miss), "missing": miss[:40], "n_missing": len(miss),
                  "complete": not miss}
    desc_sizes = {(m["kind"], m["w"], m["h"]) for m in desc}
    extra = sorted({m["label"] for m in method_modes if (m["kind"], m["w"], m["h"]) not in desc_sizes})
    tested = [v["complete"] for v in per.values() if v["complete"] is not None]
    return {"complete": all(tested) if tested else None, "per_kind": per, "n_units": len(units),
            "n_covered": sum(v["n_covered"] for v in per.values()), "extra_in_method": extra[:40],
            "n_method_modes": len(method_modes)}


# --------------------------------------------------------------------------------------------- other process
def _intervals(times_ns: list[int]) -> list[tuple[int, int]]:
    ts = sorted(t for t in times_ns if t is not None)
    return list(zip(ts, ts[1:]))


def stream_disturbance(frame_ns: list[int], window: tuple[int, int], baseline: tuple[int, int] | None,
                       notes: Iterable[dict] | None = None, stream_end_ns: int | None = None) -> dict:
    """Did the other process's stream suffer during ``window`` ([t0, t1] mach ns)?
    Baseline = frame intervals ending inside ``baseline``. In the window: the largest interval that overlaps it
    (a stall that spans the window counts; frames stopping before t1 count up to t1 or stream end). Disturbed when
    the window max > max(1.5 x baseline max, 3 x baseline median, baseline median + 50 ms), or a runtime error /
    interruption notification falls in the window. None when there is no baseline."""
    w0, w1 = window
    iv = _intervals(list(frame_ns))
    base = [(b - a) / 1e6 for a, b in iv if baseline and baseline[0] <= b <= baseline[1]]
    inwin = [(b - a) / 1e6 for a, b in iv if b > w0 and a < w1]
    ts = sorted(t for t in frame_ns if t is not None)
    last = ts[-1] if ts else None
    if last is not None and last < w1:
        end = min(w1, stream_end_ns) if stream_end_ns else w1
        inwin.append((end - last) / 1e6)  # the stream stopped (or stalled) inside the window
    n_frames = sum(1 for t in ts if w0 <= t <= w1)
    errs = [n for n in notes or [] if n.get("host_ns") is not None and w0 <= n["host_ns"] <= w1
            and ("RuntimeError" in str(n.get("name")) or "Interrupt" in str(n.get("name"))
                 or "Disconnected" in str(n.get("name")))]
    out = {"window_ms": round((w1 - w0) / 1e6, 1), "frames_in_window": n_frames,
           "window_max_interval_ms": round(max(inwin), 2) if inwin else None,
           "baseline_n": len(base), "baseline_p50_ms": round(statistics.median(base), 2) if base else None,
           "baseline_max_ms": round(max(base), 2) if base else None, "errors_in_window": errs}
    if not base:
        out["disturbed"] = True if errs else None
        out["reason"] = "no baseline frames" if not errs else "runtime error / interruption in the window"
        return out
    p50, bmax = statistics.median(base), max(base)
    thr = max(1.5 * bmax, 3 * p50, p50 + 50.0)
    out["threshold_ms"] = round(thr, 2)
    wmax = max(inwin) if inwin else (w1 - w0) / 1e6
    out["disturbed"] = bool(errs) or wmax > thr
    return out


def vs_alt(sample: dict | None) -> int | None:
    """Largest bAlternateSetting of the VideoStreaming interfaces in one mac_ioreg.read_interface_alts result."""
    if not sample or sample.get("error") and not sample.get("interfaces"):
        return None
    vs = [x for x in sample.get("interfaces") or [] if x.get("subclass") == 2]
    if not vs:
        return None
    vals = [x.get("alt") for x in vs if x.get("alt") is not None]
    return max(vals) if vals else None


def alt_evidence(samples: list[int | None], baseline_alt: int | None, streaming_elsewhere: bool) -> dict:
    """Does the method start a stream / reserve bandwidth? Idle: any VS alt > 0 during the hold -> True. While
    another process streams: any change from the baseline alt -> True. None without a valid sample."""
    vals = [s for s in samples if s is not None]
    out = {"samples": samples, "baseline_alt": baseline_alt, "max_alt": max(vals) if vals else None,
           "note": "IOUSBHostInterface bAlternateSetting tracking the live alt is unverified (topology_macos MT4)"}
    if not vals:
        out["starts_stream"] = None
        return out
    if streaming_elsewhere:
        out["starts_stream"] = None if baseline_alt is None else any(v != baseline_alt for v in vals)
        out["test"] = "alt changed from the other process's baseline"
    else:
        out["starts_stream"] = any(v > 0 for v in vals)
        out["test"] = "alt > 0 while idle"
    return out


def blocking(probe: dict | None, control: dict | None) -> dict:
    """Does the method block a third process's open during its hold? probe/control: {ok, ...} of a 1-frame capture
    during the hold / in the same condition without the method."""
    if probe is None:
        return {"blocks": None, "reason": "no probe during the hold"}
    if probe.get("not_applicable"):
        return {"blocks": False, "reason": probe["not_applicable"]}
    if probe.get("ok"):
        return {"blocks": False, "reason": "third-process 1-frame capture succeeded during the hold"}
    if control is None:
        return {"blocks": None, "reason": "probe failed and no control probe to compare"}
    if control.get("ok"):
        return {"blocks": True, "reason": "probe failed during the hold, control probe without the method succeeded"}
    return {"blocks": None, "reason": "third-process open fails in this condition even without the method"}


# --------------------------------------------------------------------------------------------- rating
def _crit(criterion: str, met: bool | None, detail: Any = None) -> dict:
    return {"criterion": criterion, "met": met, "detail": detail}


def _all(vals: list[bool | None]) -> bool | None:
    if not vals or any(v is None for v in vals):
        return None if not any(v is False for v in vals) else False
    return all(vals)


def _none_of(vals: list[bool | None]) -> bool | None:
    """True when every value is False (nothing happened), False when any is True, None when unknown."""
    if any(v is True for v in vals):
        return False
    if not vals or any(v is None for v in vals):
        return None
    return True


def rate_method(conditions: dict[str, dict], not_implementable: str | None = None) -> dict:
    """One method on one camera. conditions: {name: {streaming_elsewhere: bool, skipped: str|None, ok, complete,
    starts_stream, disturbed, blocks}}.
    yes = complete vs descriptors in every tested condition, no disturbance, no stream / bandwidth, no blocking;
    partial = complete when idle only, or disturbs / blocks (or one of those not measured);
    no = fails or incomplete when idle, or needs a stream; untested = no descriptor reference to compare."""
    if not_implementable:
        return {"rating": "no", "criteria": [_crit("can list without opening capture", False, not_implementable)],
                "evidence": {"reason": not_implementable}, "summary_label": "no (cannot list without opening capture)"}
    tested = {k: v for k, v in conditions.items() if not v.get("skipped")}
    idle = tested.get("idle")
    if idle is None:
        return {"rating": "untested", "criteria": [_crit("measured", None, "idle condition not run")],
                "evidence": {"conditions": conditions}}
    streams = {k: v for k, v in tested.items() if v.get("streaming_elsewhere")}
    c1 = _crit("lists formats with no stream (idle)", bool(idle.get("ok")), idle.get("error"))
    c2 = _crit("complete vs the USB descriptors when idle (MJPEG and raw)", idle.get("complete") if idle.get("ok")
               else False, idle.get("completeness_reason"))
    c3 = _crit("starts no stream and reserves no bandwidth (VS alt during the hold)",
               _none_of([v.get("starts_stream") for v in tested.values()]),
               {k: v.get("starts_stream") for k, v in tested.items()})
    c4 = _crit("complete in every condition (camera streaming in another process too)",
               _all([v.get("complete") if v.get("ok") else False for v in tested.values()]) if streams else None,
               {k: (v.get("complete") if v.get("ok") else "failed") for k, v in tested.items()})
    c5 = _crit("does not disturb the other process's stream", _none_of([v.get("disturbed") for v in streams.values()])
               if streams else None, {k: v.get("disturbed") for k, v in streams.items()})
    c6 = _crit("does not block a third process's open during the hold",
               _none_of([v.get("blocks") for v in tested.values()]), {k: v.get("blocks") for k, v in tested.items()})
    crit = [c1, c2, c3, c4, c5, c6]
    ev = {"conditions": conditions, "skipped_conditions": {k: v.get("skipped") for k, v in conditions.items()
                                                           if v.get("skipped")}}
    if c1["met"] is False or c2["met"] is False or c3["met"] is False:
        why = "fails when idle" if c1["met"] is False else ("incomplete vs descriptors" if c2["met"] is False
                                                             else "starts a stream / reserves bandwidth")
        return {"rating": "no", "criteria": crit, "evidence": ev, "note": why}
    if c2["met"] is None:
        return {"rating": "untested", "criteria": crit, "evidence": ev,
                "note": idle.get("completeness_reason") or "no descriptor reference"}
    if all(c["met"] is True for c in crit):
        return {"rating": "yes", "criteria": crit, "evidence": ev}
    return {"rating": "partial", "criteria": crit, "evidence": ev,
            "note": "complete when idle; " + ", ".join(c["criterion"] for c in crit if c["met"] is not True)
            + " not met or not measured"}


# --------------------------------------------------------------------------------------------- IORegistry
FORMAT_KEY_HINTS = ("format", "frame", "resolution", "width", "height", "fps", "interval", "descriptor", "mjpeg",
                    "yuv", "uvc")


def ioreg_format_info(node: dict, children_key: str = "IORegistryEntryChildren") -> dict:
    """What format information an IORegistry device subtree carries (expected: none). Returns {keys: [...],
    config_descriptor_hex: str | None, where}. Only property NAMES that hint at formats are listed, plus any
    bytes value that parses as a configuration descriptor (bDescriptorType 2)."""
    keys, cfg, where = [], None, None
    stack = [(node, node.get("IORegistryEntryName") or node.get("IOObjectClass"))]
    while stack:
        n, path = stack.pop()
        if not isinstance(n, dict):
            continue
        for k, v in n.items():
            if k == children_key:
                continue
            kl = k.lower()
            if any(h in kl for h in FORMAT_KEY_HINTS):
                keys.append(f"{path}:{k}")
            if cfg is None and isinstance(v, (bytes, bytearray)) and len(v) > 9 and v[1] == 2:
                cfg, where = bytes(v).hex(), f"{path}:{k}"
        for ch in n.get(children_key) or []:
            if isinstance(ch, dict):
                stack.append((ch, f"{path}/{ch.get('IORegistryEntryName') or ch.get('IOObjectClass')}"))
    return {"format_hint_keys": sorted(set(keys))[:60], "config_descriptor_hex": cfg, "config_descriptor_at": where}
