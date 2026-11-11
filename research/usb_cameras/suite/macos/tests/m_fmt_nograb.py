"""M-FMT-NOGRAB (plan 6.2 FMT-NOGRAB, Dom 2026-11-06): which method identifies a camera's formats correctly
WITHOUT grabbing the camera or starting a stream. Runs right after M-FMT; every camera, the Kiyo included.

Methods (macOS):
  avf_formats      AVCaptureDevice.formats with no AVCaptureSession (helpers/mac_avf.py formats --hold-ms).
  ioreg            the IORegistry device subtree (ioreg -r -c IOUSBHostDevice): records what format information, if
                   any, is there (expected: none; a configuration-descriptor blob would be parsed and compared).
  ep0_descriptors  only with --ep0 (opt-in, as everywhere in this suite): mac_ep0.py descriptors, i.e. the device
                   plug-in's GetConfigurationDescriptorPtr (the OS's cached copy; no request is sent).

Conditions:
  idle             no process uses the camera.
  stream_avf       the camera streams in ANOTHER process through AVFoundation (mac_avf.py capture --stop-file), in
                   its scoped default mode (MJPEG 1280x720@30 or the nearest in-scope MJPEG mode).
  stream_api2      skipped by default: macOS has no second capture API (FFmpeg's avfoundation input is AVFoundation;
                   libuvc/libusb streaming needs a driver detach, which plan 6.1 forbids). --nograb-cond3 avf-dmb1
                   runs it as a second AVFoundation process with the 'dmb1' passthrough videoSettings instead.

Per method x condition: succeeded; completeness vs the USB descriptors (every format/size/rate, MJPEG and raw
separately; reference = the descriptor cache or the --ep0 read, else 'untested'); elapsed (child process and the
listing call itself); disturbance of the other stream (max frame interval and runtime errors in the listing
window vs that stream's baseline); whether it starts a stream / reserves bandwidth (the VS interface
bAlternateSetting from ioreg sampled while the method holds its device object for --hold-ms, default 2000 ms);
whether it blocks a third process from opening and streaming the camera during the hold (a 1-frame capture,
compared with the same probe in that condition without the method).

Rating per method (nograb.rate_method): yes = complete in every tested condition, no disturbance, no stream or
bandwidth, no blocking; partial = complete when idle only, or disturbs / blocks (or not measured); no = fails or
incomplete when idle, or needs a stream; untested = no descriptor reference. Verdict keys: 'fmt_nograb' (best
method), 'fmt_nograb:<method>' (worst camera per method)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import childutil
import mac_modescope
import nograb
import suitectx
from common import rating, results

NAME = "M-FMT-NOGRAB"
NO_PERMISSION = ("denied", "restricted", "notDetermined")


def methods(ctx) -> list[str]:
    return ["avf_formats", "ioreg"] + (["ep0_descriptors"] if ctx.ep0_enabled else [])


def conditions(ctx) -> list[tuple[str, dict]]:
    c3 = getattr(ctx.args, "nograb_cond3", "skip")
    out = [("idle", {"streaming": False}), ("stream_avf", {"streaming": True, "variant": "nil"})]
    if c3 == "avf-dmb1":
        out.append(("stream_api2", {"streaming": True, "variant": "dmb1", "note": "second AVFoundation process, "
                                                                                    "dmb1 passthrough"}))
    else:
        out.append(("stream_api2", {"skipped": "macOS has no second capture API (FFmpeg avfoundation is AVFoundation; "
                                               "libuvc streaming needs a driver detach); --nograb-cond3 avf-dmb1 runs "
                                               "a second AVFoundation process instead"}))
    return out


def plan(ctx) -> list[str]:
    a = ctx.args
    out = [f"methods: {', '.join(methods(ctx))}" + ("" if ctx.ep0_enabled else " (ep0_descriptors needs --ep0)"),
           "conditions: " + ", ".join(n + (f" (skipped: {c['skipped'].split('(')[0].strip()})" if c.get("skipped") else "")
                                      for n, c in conditions(ctx)),
           f"per method: hold {getattr(a, 'hold_ms', 2000):g} ms; VS alt sampled from ioreg during the hold; "
           + ("third-process 1-frame capture during the hold" if getattr(a, "nograb_block_probe", True)
              else "no third-process probe (--no-nograb-block-probe)"),
           "reference: USB descriptors (cache / --ep0); every advertised mode is compared (listing test: no mode "
           "scope); the background stream uses the scoped default mode (" + mac_modescope.text(a) + ")"]
    for cam in ctx.cameras:
        m, info = suitectx.pick_scoped_default(cam, a)
        ref = "descriptors cached" if _reference(ctx, cam)[0] else "no descriptor reference (completeness untested)"
        out.append(f"{cam['key']}{' (Kiyo)' if cam.get('is_kiyo') else ''}: stream mode "
                   f"{m['mode_text'] if m else 'none: ' + info['why']}; {ref}")
    return out


# --------------------------------------------------------------------------------------------- plumbing
def _reference(ctx, cam: dict) -> tuple[list[dict] | None, str]:
    d = ctx.cam_desc(cam)
    if d and d.get("frames"):
        return d["frames"], f"descriptor cache ({d.get('source')})"
    u = cam.get("uvc") or {}
    if u.get("frames"):
        return u["frames"], f"M-FMT descriptors ({u.get('source')})"
    return None, "none"


def _wait_file(path: Path, timeout_s: float, alive=None) -> dict | None:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8") or "{}")
            except ValueError:
                pass
        if alive is not None and not alive():
            return json.loads(path.read_text(encoding="utf-8") or "{}") if path.exists() else None
        time.sleep(0.02)
    return None


class _Bg:
    """Run fn(*args) in a thread and keep its result."""

    def __init__(self, fn, *args, **kw):
        self.result = None
        self.error = None

        def body():
            try:
                self.result = fn(*args, **kw)
            except Exception as e:  # a bug must show up as a result
                self.error = repr(e)
        self.t = threading.Thread(target=body, daemon=True)

    def start(self):
        self.t.start()
        return self

    def alive(self) -> bool:
        return self.t.is_alive()

    def join(self, timeout: float | None = None):
        self.t.join(timeout)
        return self.result


def _sample_alt(ctx, cam: dict) -> tuple[int | None, dict]:
    import mac_ioreg
    loc = cam.get("location_id")
    if loc is None and cam.get("location_hex"):
        loc = int(cam["location_hex"], 16)
    if loc is None:
        return None, {"error": "no locationID"}
    r = mac_ioreg.read_interface_alts(int(loc), timeout_s=10.0 * ctx.scale, runner=lambda argv, t: ctx.runner(argv, t))
    return nograb.vs_alt(r), {"error": r.get("error"), "source": r.get("source"), "elapsed_s": r.get("elapsed_s")}


def _probe(ctx, cam: dict, mode: dict | None, od: Path, label: str) -> dict:
    """Third-process 1-frame capture (bounded)."""
    if not cam.get("unique_id"):
        return {"ok": None, "skipped": "not listed by AVFoundation"}
    t0 = childutil.mach_ns()
    args = ["capture", "--device", cam["unique_id"], "--frames", 1, "--seconds-cap", 6, "--first-frame-timeout-s", 6,
            "--jpeg-check", "none", "--out-dir", od] + (suitectx.avf_mode_args(mode) if mode else [])
    r = ctx.avf(args, 40, label=label)
    j = r.get("json") or {}
    return {"ok": bool(j.get("frames")), "frames": j.get("frames"), "first_frame_ms": j.get("first_frame_ms"),
            "error": j.get("error"), "error_class": j.get("error_class"), "timed_out": r.get("timed_out"),
            "rc": r.get("rc"), "elapsed_s": r.get("elapsed_s"), "start_mach_ns": t0, "end_mach_ns": childutil.mach_ns()}


def _run_holding(ctx, cam: dict, method: str, od: Path, mode: dict | None, block_probe: bool, cond: str) -> dict:
    """Run a method that holds its device object (avf_formats, ep0_descriptors): start it, wait for its hold marker,
    sample the alt for hold_ms, run the third-process probe, release it, collect its JSON."""
    hold_ms = float(getattr(ctx.args, "hold_ms", 2000.0) or 2000.0)
    marker, release = od / "hold_marker.json", od / "release"
    for p in (marker, release):
        if p.exists():
            p.unlink()
    cap_ms = hold_ms + 90_000.0
    hold_args = ["--hold-ms", f"{hold_ms:g}", "--hold-marker", marker, "--release-file", release,
                 "--hold-cap-ms", f"{cap_ms:g}"]
    timeout = 40 + cap_ms / 1000.0
    if method == "avf_formats":
        bg = _Bg(ctx.avf, ["formats", "--device", cam["unique_id"]] + hold_args, timeout, label=f"nograb {cond} avf {cam['key']}")
    else:
        bg = _Bg(ctx.ep0, cam, "descriptors", hold_args, timeout)
    t0 = childutil.mach_ns()
    bg.start()
    hm, samples, sample_meta, probe, t_sampled = None, [], [], None, None
    try:
        hm = _wait_file(marker, 45.0 * ctx.scale, alive=bg.alive)
        if hm is not None:
            t_hold0 = int(hm.get("mach_ns") or childutil.mach_ns())
            end = t_hold0 + int(hold_ms * 1e6)
            while True:
                a, meta = _sample_alt(ctx, cam)
                samples.append(a)
                sample_meta.append(meta)
                if childutil.mach_ns() >= end or len(samples) >= 50:
                    break
                time.sleep(min(0.2, max(0.0, (end - childutil.mach_ns()) / 1e9)))
            t_sampled = childutil.mach_ns()
            if block_probe:
                probe = _probe(ctx, cam, mode, od / "probe", f"nograb {cond} probe during {method} {cam['key']}")
    finally:
        # always release the holding child (else it keeps the device object until its cap)
        childutil.touch(release, {"released_by": "runner", "mach_ns": childutil.mach_ns()})
    r = bg.join(timeout + 10) or {}
    t1 = childutil.mach_ns()
    j = r.get("json") or {}
    return {"ok": bool(j.get("ok")), "json": j, "rc": r.get("rc"), "timed_out": r.get("timed_out"),
            "elapsed_s": r.get("elapsed_s"), "thread_error": bg.error, "hold_marker": hm,
            "hold": j.get("hold"), "alt_samples": samples, "alt_sample_meta": sample_meta[:3],
            "probe": probe, "window": [t0, t_sampled or t1], "end_mach_ns": t1}


def _run_ioreg(ctx, cam: dict) -> dict:
    import mac_ioreg
    t0 = childutil.mach_ns()
    r = mac_ioreg.run_ioreg(mac_ioreg.QUERIES["devices"], 20.0 * ctx.scale, runner=lambda argv, t: ctx.runner(argv, t))
    t1 = childutil.mach_ns()
    roots = mac_ioreg.load_plist(r.get("stdout_bytes") or b"")
    node = None
    loc = cam.get("location_id") if cam.get("location_id") is not None else (
        int(cam["location_hex"], 16) if cam.get("location_hex") else None)
    for root in roots:
        for n in mac_ioreg._iter_nodes(root):
            if mac_ioreg.classify(n) == "device" and mac_ioreg.as_int(n.get("locationID")) == loc:
                node = n
                break
        if node is not None:
            break
    a, meta = _sample_alt(ctx, cam)
    out = {"ok": node is not None, "elapsed_s": r.get("elapsed_s"), "error": r.get("error") if node is not None
           else (r.get("error") or "camera's IOUSBHostDevice not found"), "alt_samples": [a],
           "alt_sample_meta": [meta], "window": [t0, t1], "end_mach_ns": t1,
           "probe": {"not_applicable": "registry read: no device object is held"}}
    if node is not None:
        info = nograb.ioreg_format_info(node)
        out["format_info"] = info
        if info.get("config_descriptor_hex"):
            import mac_ep0
            try:
                s = mac_ep0.summarize_config(bytes.fromhex(info["config_descriptor_hex"]))
                out["frames"] = s.get("frames")
            except Exception as e:
                out["parse_error"] = repr(e)
    return out


def _method_modes(method: str, rec: dict) -> list[dict] | None:
    if not rec.get("ok"):
        return None
    if method == "avf_formats":
        return nograb.modes_from_avf(((rec.get("json") or {}).get("device") or {}).get("formats"))
    if method == "ep0_descriptors":
        return nograb.modes_from_descriptor_frames((rec.get("json") or {}).get("frames"))
    return nograb.modes_from_descriptor_frames(rec.get("frames")) if rec.get("frames") else []


def _streamer(ctx, cam: dict, mode: dict, variant: str, od: Path) -> tuple[_Bg, Path, Path]:
    ready, stop = od / "ready.json", od / "stop"
    for p in (ready, stop):
        if p.exists():
            p.unlink()
    args = ["capture", "--device", cam["unique_id"], "--seconds", 300, "--variant", variant, "--jpeg-check", "none",
            "--first-frame-timeout-s", 8, "--out-dir", od, "--ready-file", ready, "--stop-file", stop] \
        + suitectx.avf_mode_args(mode)
    bg = _Bg(ctx.avf, args, 340, label=f"nograb streamer {variant} {cam['key']}").start()
    return bg, ready, stop


# --------------------------------------------------------------------------------------------- one camera
def run_camera(ctx, cam: dict, errors: list) -> dict:
    a = ctx.args
    tag = suitectx.cam_tag(cam)
    ref, ref_src = _reference(ctx, cam)
    mode, minfo = suitectx.pick_scoped_default(cam, a)
    no_perm = ctx.tcc in NO_PERMISSION and not getattr(a, "run_without_permission", False)
    block_probe = bool(getattr(a, "nograb_block_probe", True)) and not no_perm
    baseline_s = float(getattr(a, "nograb_baseline_s", 2.0))
    settle_s = min(0.5, baseline_s / 4)  # gap between the windows of consecutive steps on the other stream
    crec: dict = {"key": cam["key"], "is_kiyo": cam.get("is_kiyo"), "reference": ref_src,
                  "n_reference_frames": len(ref or []), "stream_mode": mode, "stream_mode_choice": minfo,
                  "conditions": {}, "methods": {}}
    meths = methods(ctx)
    for cname, cdef in conditions(ctx):
        cres: dict = {"definition": {k: v for k, v in cdef.items() if k != "skipped"}}
        crec["conditions"][cname] = cres
        if cdef.get("skipped"):
            cres["skipped"] = cdef["skipped"]
            continue
        streaming = bool(cdef.get("streaming"))
        if streaming:
            why = ("camera permission is " + str(ctx.tcc)) if no_perm else (
                "not listed by AVFoundation" if not cam.get("unique_id") else (
                    f"no in-scope MJPEG mode for the background stream ({minfo['why']}): untested (scope)"
                    if not mode else None))
            if why:
                cres["skipped"] = why
                continue
        od = ctx.subdir("fmt_nograb", tag, cname)
        bg = ready = stop = None
        if streaming:
            bg, ready, stop = _streamer(ctx, cam, mode, cdef.get("variant", "nil"), od / "stream")
            rd = _wait_file(ready, 40.0 * ctx.scale, alive=bg.alive)
            if not rd or not rd.get("first_frame"):
                childutil.touch(stop)
                bg.join(60)
                cres["skipped"] = "the background stream did not deliver a first frame"
                cres["streamer"] = {k: ((bg.result or {}).get("json") or {}).get(k) for k in ("error", "error_class",
                                                                                              "frames")}
                errors.append({"camera": cam["key"], "condition": cname, "warning": cres["skipped"]})
                continue
            t_ready = int(rd.get("mach_ns") or childutil.mach_ns())
            time.sleep(baseline_s)
            cres["baseline_window"] = [t_ready + int(min(0.3, baseline_s / 3) * 1e9), childutil.mach_ns()]
        try:
            base_alt, meta = _sample_alt(ctx, cam)
            cres["baseline_alt"], cres["baseline_alt_meta"] = base_alt, meta
            control = _probe(ctx, cam, mode, od / "control_probe", f"nograb {cname} control probe {cam['key']}") \
                if block_probe else None
            cres["control_probe"] = control
            if streaming:
                time.sleep(settle_s)
            recs = {}
            for meth in meths:
                if meth in ("avf_formats",) and not cam.get("unique_id"):
                    recs[meth] = {"ok": False, "error": "not listed by AVFoundation", "skipped": True}
                    continue
                if meth == "ep0_descriptors" and not cam.get("location_hex"):
                    recs[meth] = {"ok": False, "error": "no locationID", "skipped": True}
                    continue
                mdir = ctx.subdir("fmt_nograb", tag, cname, meth)
                recs[meth] = (_run_ioreg(ctx, cam) if meth == "ioreg" else
                              _run_holding(ctx, cam, meth, mdir, mode, block_probe, cname))
                if streaming:
                    time.sleep(settle_s)
        finally:
            if streaming:
                childutil.touch(stop)  # always end the background stream
        stream_info = None
        if streaming:
            r = bg.join(60) or {}
            j = r.get("json") or {}
            rows = results.read_jsonl(od / "stream" / "frames.jsonl")
            fns = [x.get("mach_ns") for x in rows if x.get("mach_ns") is not None]
            stream_info = {"frames": j.get("frames"), "fps": j.get("fps_measured"), "stopped_by": j.get("stopped_by"),
                           "runtime_errors": j.get("runtime_errors"), "timed_out": r.get("timed_out"),
                           "n_rows": len(rows)}
            cres["stream"] = stream_info
            notes = j.get("notifications") or []
            end_ns = fns[-1] if fns else None
            base_w = tuple(cres["baseline_window"])
            if control and control.get("start_mach_ns"):
                cres["control_probe_disturbance"] = nograb.stream_disturbance(
                    fns, (control["start_mach_ns"], control["end_mach_ns"]), base_w, notes, end_ns)
            for meth, rec in recs.items():
                if rec.get("window"):
                    rec["disturbance"] = nograb.stream_disturbance(fns, tuple(rec["window"]), base_w, notes, end_ns)
        # score each method in this condition
        for meth, rec in recs.items():
            comp = nograb.completeness(ref, _method_modes(meth, rec))
            if meth == "ioreg" and rec.get("ok") and not rec.get("frames") and ref:
                comp = {"complete": False, "reason": "IORegistry carries no format information "
                                                     "(no configuration descriptor in the device subtree)",
                        "format_hint_keys": (rec.get("format_info") or {}).get("format_hint_keys")}
            alt = nograb.alt_evidence(rec.get("alt_samples") or [], base_alt, streaming)
            blk = nograb.blocking(rec.get("probe"), control)
            j = rec.get("json") or {}
            row = {"ok": bool(rec.get("ok")), "error": rec.get("error") or j.get("error"),
                   "streaming_elsewhere": streaming, "complete": comp.get("complete"),
                   "completeness_reason": comp.get("reason"), "completeness": comp,
                   "starts_stream": alt.get("starts_stream"), "alt": alt,
                   "disturbed": (rec.get("disturbance") or {}).get("disturbed") if streaming else None,
                   "disturbance": rec.get("disturbance"), "blocks": blk["blocks"], "blocking": blk,
                   "probe": rec.get("probe"), "elapsed_s": rec.get("elapsed_s"),
                   "list_ms": j.get("list_ms"), "hold": rec.get("hold") or j.get("hold"),
                   "timed_out": rec.get("timed_out"), "in_use_by_other_app": (j.get("device") or {}).get(
                       "in_use_by_other_app")}
            if rec.get("format_info") is not None:
                row["ioreg_format_info"] = {k: v for k, v in rec["format_info"].items() if k != "config_descriptor_hex"}
            crec["methods"].setdefault(meth, {})[cname] = row
            if rec.get("timed_out"):
                errors.append({"camera": cam["key"], "condition": cname, "method": meth,
                               "warning": "method timed out (recorded)"})
    # skipped conditions appear in every method's condition table, so the rating sees them
    for meth in meths:
        tab = crec["methods"].setdefault(meth, {})
        for cname, cres in crec["conditions"].items():
            if cres.get("skipped") and cname not in tab:
                tab[cname] = {"skipped": cres["skipped"], "streaming_elsewhere": cname != "idle"}
        crec.setdefault("ratings", {})[meth] = nograb.rate_method(tab)
    return crec


def run(ctx) -> dict:
    res = ctx.new_result(NAME)
    errors: list = []
    per = []
    gate = getattr(ctx, "camera_gated", None)
    for cam in ctx.cameras:  # every camera, the Kiyo included; never filtered by model
        g = gate(cam) if callable(gate) else None
        if g:
            ft = getattr(ctx, "fault_untested", None)
            unt = ft(cam) if callable(ft) else rating.device_fault_untested(g)
            per.append({"key": cam["key"], "is_kiyo": cam.get("is_kiyo"), "untested": "device fault",
                        "ratings": {m: unt for m in methods(ctx)}})
            continue
        try:
            per.append(run_camera(ctx, cam, errors))
        except Exception as e:
            import traceback
            errors.append({"camera": cam["key"], "error": f"{type(e).__name__}: {e}",
                           "traceback": traceback.format_exc()[-2000:]})
    v: dict = {}
    by_method = {}
    for meth in methods(ctx):
        rs = [c["ratings"][meth] for c in per if meth in (c.get("ratings") or {})]
        w = rating.worst(rs)
        by_method[meth] = w
        v[f"fmt_nograb:{meth}"] = {"rating": w, "criteria": [{"criterion": "worst camera (nograb.rate_method)",
                                                              "met": w == "yes", "detail": w}],
                                   "evidence": {c["key"]: (c.get("ratings") or {}).get(meth, {}).get("rating")
                                                for c in per}}
    order = {"yes": 3, "partial": 2, "no": 1, "untested": 0}
    best = max(by_method.items(), key=lambda kv: order.get(kv[1], 0)) if by_method else (None, "untested")
    v["fmt_nograb"] = {"rating": best[1], "criteria": [{"criterion": "best method lists formats correctly without "
                                                                     "grabbing the camera", "met": best[1] == "yes",
                                                        "detail": best[0]}],
                       "evidence": {"per_method": by_method, "best_method": best[0]},
                       "not_tested_methods": {} if ctx.ep0_enabled else {"ep0_descriptors": "needs --ep0 (opt-in)"}}
    m = {"cameras": per, "methods": methods(ctx), "conditions": [n for n, _ in conditions(ctx)],
         "hold_ms": float(getattr(ctx.args, "hold_ms", 2000.0) or 2000.0),
         "baseline_s": float(getattr(ctx.args, "nograb_baseline_s", 2.0)),
         "block_probe": bool(getattr(ctx.args, "nograb_block_probe", True)),
         "stream_mode_scope": mac_modescope.text(ctx.args),
         "note": "listing test: every advertised mode is compared (no mode scope); the IOUSBHostInterface "
                 "bAlternateSetting as a live-alt signal is unverified (topology_macos MT4)"}
    return results.finish_result(res, m, v, errors)
