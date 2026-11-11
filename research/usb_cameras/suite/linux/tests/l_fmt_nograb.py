"""L-FMT-NOGRAB: which method lists a camera's formats correctly WITHOUT grabbing the camera or starting a stream
(plan 6.2 FMT-NOGRAB, Dom 2026-11-06; format discovery for the UI and the mode-alt cache without disturbing a camera
another app is using). Runs right after L-FMT.

Methods (every format-listing method on Linux):
  sysfs_descriptors      the kernel's cached copy of the USB descriptors (/sys/.../descriptors): no device handle,
                         no bus traffic. It is also the reference, so its completeness is by definition; what is
                         measured is whether it is readable at all times without touching the camera.
  v4l2_enum_no_streamon  VIDIOC_ENUM_FMT / ENUM_FRAMESIZES / ENUM_FRAMEINTERVALS on a read-only fd, no S_FMT, no
                         REQBUFS, no STREAMON (camworker formats --hold-ms: the fd stays open for the hold).
  v4l2_ctl               v4l2-ctl --list-formats-ext (if installed), repeated back to back for the hold.
  pipewire               EnumFormat params of the camera's PipeWire node from pw-dump (if present), repeated for
                         the hold. libcamera-API nodes are recorded too, mapped by VID:PID when unique.

Conditions (the shared names of common.rating.NOGRAB_CONDITIONS): idle; streaming_native = the camera streaming
in another process through raw V4L2 (camworker capture, the OS-native path); streaming_second_api = streaming in
another process through PyAV v4l2 when the pyav wrapper is available, else a second raw-V4L2 process (labelled).
Streams use the in-scope default mode (mode scope, plan 6).

Measured per method x condition: succeeded; completeness vs the USB descriptors (every format / size / rate; MJPEG
and raw separately, other compressed formats such as H264 reported apart); elapsed time of one listing; disturbance
of the other stream (max frame interval and ERROR-flagged / zero-length frames inside the listing window vs the
stream's own baseline before the first window); whether it starts a stream or reserves bandwidth (the VS interface
bAlternateSetting sampled from sysfs while the method holds the device; idle: any non-zero alt; streaming: any
change from the stream's alt); whether it blocks another process (idle only: a 1-frame capture from a third process
started halfway through the hold, compared with the same capture with no lister).

Rating per method (per camera, then the worst over cameras), common.rating.rate_fmt_nograb (shared with Windows
and macOS; a local copy of the same rule is used only if that function is missing):
  yes      complete vs descriptors in all conditions, no disturbance, no stream / bandwidth, no blocking
  partial  complete when idle only, or disturbs / blocks, or (provisional) a condition or measure untested
  no       incomplete when idle, fails when idle, or needs a stream (non-zero alt while listing)
Completeness and disturbance use common.nograb.compare / common.nograb.disturbance (same fallback rule).
The runner holds the camera lock across each camera's conditions; every child has a timeout. Kiyo included.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

from common import rating, results
import analysis
import apis
import scope
import sysfs
from suitectx import child_outcome, combine
from tutil import gate, have, mode_args, mode_text, worker_error

try:  # shared FMT-NOGRAB analysis (Windows agent); the local functions below implement the same rule
    from common import nograb as _ng  # type: ignore
except Exception:  # noqa: BLE001
    _ng = None

TEST = "L-FMT-NOGRAB"
INFO = {"goal": "format discovery", "summary": "list formats without grabbing: sysfs descriptors / V4L2 ENUM (no "
                                               "STREAMON) / v4l2-ctl / PipeWire, idle and while another process "
                                               "streams; completeness, disturbance, alt, blocking",
        "opens_cameras": "listing only; condition streams and 1-frame probes in other processes"}
METHODS = ("sysfs_descriptors", "v4l2_enum_no_streamon", "v4l2_ctl", "pipewire")
CONDITIONS = tuple(getattr(rating, "NOGRAB_CONDITIONS", ("idle", "streaming_native", "streaming_second_api")))
METHOD_INFO = {
    "sysfs_descriptors": {"how": "read /sys/bus/usb/devices/<dev>/descriptors (kernel's cached copy)",
                          "touches_device": False, "hold": "repeated reads (no handle)"},
    "v4l2_enum_no_streamon": {"how": "open read-only, VIDIOC_ENUM_FMT/FRAMESIZES/FRAMEINTERVALS, no STREAMON",
                              "touches_device": "no USB traffic (uvcvideo answers from parsed descriptors)",
                              "hold": "fd held open"},
    "v4l2_ctl": {"how": "v4l2-ctl -d <node> --list-formats-ext", "touches_device": "as v4l2_enum_no_streamon",
                 "hold": "repeated back to back"},
    "pipewire": {"how": "pw-dump -N: EnumFormat params of the camera's Video/Source node", "touches_device":
                 "PipeWire's own v4l2/libcamera plugin may open the node to enumerate", "hold": "repeated back to back"},
}
OTHER_COMPRESSED = {"H264", "HEVC", "H265", "VP8", "VP9", "AV1", "MPEG", "MPG1", "MPG2", "M2TS"}
PW_RAW = {"YUY2": "YUYV", "I420": "YU12", "GRAY8": "GREY", "RGB": "RGB3", "BGR": "BGR3", "NV12": "NV12",
          "UYVY": "UYVY", "YV12": "YV12", "NV21": "NV21", "RGBx": "XR24", "BGRx": "XB24"}
PW_SUBTYPE = {"mjpg": "MJPG", "jpeg": "MJPG", "h264": "H264", "h265": "HEVC", "hevc": "HEVC", "vp8": "VP8",
              "vp9": "VP9"}
#: V4L2 fourccs whose common.nograb spelling differs (so the class mjpeg / raw / other matches across OSes)
V4L2_TO_COMMON = {"YU12": "I420", "XR24": "RGB32", "XB24": "RGB32", "RGB3": "RGB24", "YV12": "YV12"}
REL_TOL = 0.0015   # fps printed / rounded to 2-3 digits (7.5, 29.97, 24.000)


def _now() -> int:
    return time.monotonic_ns()   # CLOCK_MONOTONIC on Linux: the children's host_ns clock


def _wait(seconds: float) -> None:
    threading.Event().wait(max(0.0, seconds))   # not time.sleep (unit tests stub it out)


def hold_s(ctx) -> float:
    return max(0.05, float(getattr(ctx.args, "hold_ms", None) or 2000.0) / 1000.0)


def baseline_s(ctx) -> float:
    return min(2.0, max(0.3, hold_s(ctx)))


def available_methods(ctx) -> dict[str, tuple[bool, str | None]]:
    return {"sysfs_descriptors": (True, None), "v4l2_enum_no_streamon": (True, None),
            "v4l2_ctl": (have("v4l2-ctl"), None if have("v4l2-ctl") else "v4l2-ctl not installed (v4l-utils)"),
            "pipewire": (have("pw-dump"), None if have("pw-dump") else "pw-dump not installed (no PipeWire tools)")}


def second_api(ctx) -> str:
    return "pyav" if "pyav" in (getattr(ctx.args, "wrapper_list", None) or []) else "v4l2_second_process"


def stream_seconds(ctx, n_methods: int) -> float:
    return round(baseline_s(ctx) + n_methods * (hold_s(ctx) + 4.0) + 3.0, 1)


def plan(ctx) -> dict[str, Any]:
    av = available_methods(ctx)
    n = sum(1 for ok, _ in av.values() if ok)
    per_cam = n * (hold_s(ctx) + 3) + 3 + 2 * (stream_seconds(ctx, n) + 8)
    return {"child_runs": len(ctx.cameras) * (2 + 3 * n + 2), "est_seconds": round(per_cam * len(ctx.cameras)),
            "methods": {m: ("available" if ok else f"unavailable: {why}") for m, (ok, why) in av.items()},
            "conditions": {"idle": "no stream", "streaming_native": "camworker capture (raw V4L2) in another process",
                           "streaming_second_api": second_api(ctx)},
            "hold_ms": hold_s(ctx) * 1000, "stream_seconds": stream_seconds(ctx, n),
            "mode_scope": {**scope.settings(ctx.args), "note": "listing compares every mode; only the condition "
                                                              "streams and 1-frame probes use the scoped mode"},
            "per_camera_stream_mode": {c["key"]: mode_text(scope.picks(ctx, c)["default"]) for c in ctx.cameras},
            "steps": ["baseline 1-frame capture", "idle: each method + hold + third-process capture",
                      "raw V4L2 stream: each method in its own window", f"{second_api(ctx)} stream: same"]}


# ------------------------------------------------------------------------------------------- mode sets
def _fourcc_cat(fcc: str) -> str:
    if _ng is not None:
        return _ng.fmt_class(V4L2_TO_COMMON.get(fcc, fcc))
    return "mjpeg" if fcc == "MJPG" else ("other" if fcc in OTHER_COMPRESSED else "raw")


def mode_tuples(modes: dict[tuple, dict[str, Any]] | None) -> set[tuple]:
    """{(fourcc, w, h, fps rounded to 0.1 | 'continuous')} from an analysis-style mode dict."""
    out: set[tuple] = set()
    for (fcc, w, h), v in (modes or {}).items():
        if v.get("continuous") or not v.get("fps"):
            out.add((fcc, w, h, "continuous"))
        for f in v.get("fps") or []:
            out.add((fcc, w, h, round(float(f), 1)))
    return out


def tuples_100ns(modes: dict[tuple, dict[str, Any]] | None) -> list[tuple]:
    """common.nograb mode tuples (fourcc, w, h, interval_100ns); a continuous rate range is interval 0."""
    out = []
    for (fcc, w, h), v in (modes or {}).items():
        f = V4L2_TO_COMMON.get(fcc, fcc)
        if v.get("continuous") or not v.get("fps"):
            out.append((f, w, h, 0))
        for fps in v.get("fps") or []:
            out.append((f, w, h, int(round(1e7 / float(fps)))))
    return out


def _txt(t: tuple) -> str:
    return f"{t[0]} {t[1]}x{t[2]}@{t[3] if isinstance(t[3], str) else format(t[3], 'g')}"


def completeness(found: dict | None, desc: dict) -> dict[str, Any]:
    """found: an analysis-style mode dict from a method (None = nothing listed); desc: the camera's descriptor
    summary (the reference). common.nograb.compare's shape: complete, exact, per_class {mjpeg, raw, other}."""
    ref_modes = analysis.desc_mode_set(desc)
    if _ng is not None:
        try:
            out = _ng.compare(tuples_100ns(ref_modes), None if found is None else tuples_100ns(found),
                              rel_tol=REL_TOL)
            out["source"] = "common.nograb.compare"
            return out
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
    else:
        err = None
    ref, got = mode_tuples(ref_modes), mode_tuples(found)
    per: dict[str, Any] = {}
    for cat in ("mjpeg", "raw", "other"):
        r = {t for t in ref if _fourcc_cat(t[0]) == cat}
        g = {t for t in got if _fourcc_cat(t[0]) == cat}
        miss, extra = sorted(r - g, key=str), sorted(g - r, key=str)
        per[cat] = {"n_reference": len(r), "n_listed": len(g), "n_missing": len(miss), "n_extra": len(extra),
                    "missing": [_txt(x) for x in miss[:24]], "extra": [_txt(x) for x in extra[:24]],
                    "complete": not miss}
    required = [c for c in ("mjpeg", "raw") if per[c]["n_reference"]]
    complete = found is not None and bool(ref) and all(per[c]["complete"] for c in required)
    return {"complete": complete, "exact": complete and all(per[c]["n_extra"] == 0 for c in required),
            "required_classes": required, "per_class": per, "n_reference": len(ref), "n_listed": len(got),
            "listed_none": found is None, "source": "linux fallback (same rule)", "common_error": err}


# ------------------------------------------------------------------------------------------- parsers
_V4L2CTL_FMT = re.compile(r"^\s*\[\d+\]:\s*'([^']*)'")
_V4L2CTL_SIZE_D = re.compile(r"^\s*Size:\s*Discrete\s+(\d+)x(\d+)")
_V4L2CTL_SIZE_S = re.compile(r"^\s*Size:\s*(Stepwise|Continuous)")
_V4L2CTL_IV_D = re.compile(r"^\s*Interval:\s*Discrete\s+[\d.]+s\s+\(([\d.]+)\s*fps\)")
_V4L2CTL_IV_S = re.compile(r"^\s*Interval:\s*(Stepwise|Continuous)")


def parse_v4l2_ctl(text: str) -> dict[tuple, dict[str, Any]]:
    """v4l2-ctl --list-formats-ext output -> {(fourcc, w, h): {"fps": [...], "continuous": bool}}."""
    out: dict[tuple, dict[str, Any]] = {}
    fcc, cur = None, None
    for ln in (text or "").splitlines():
        m = _V4L2CTL_FMT.match(ln)
        if m:
            fcc, cur = m.group(1).strip(), None
            continue
        if fcc is None:
            continue
        m = _V4L2CTL_SIZE_D.match(ln)
        if m:
            cur = (fcc, int(m.group(1)), int(m.group(2)))
            out.setdefault(cur, {"fps": [], "continuous": False})
            continue
        if _V4L2CTL_SIZE_S.match(ln):
            cur = (fcc, -1, -1)
            out.setdefault(cur, {"fps": None, "continuous": True})
            continue
        if cur is None:
            continue
        m = _V4L2CTL_IV_D.match(ln)
        if m and out[cur]["fps"] is not None:
            out[cur]["fps"].append(round(float(m.group(1)), 2))
        elif _V4L2CTL_IV_S.match(ln):
            out[cur]["continuous"] = True
    for v in out.values():
        if v["fps"]:
            v["fps"] = sorted(set(v["fps"]), reverse=True)
    return out


def _pw_values(x: Any, leaf: Callable[[Any], Any]) -> tuple[list[Any], bool]:
    """Values of a pw-dump SPA choice (plain value, {default, alt1..}, {default, min, max[, step]}, or a list).
    Returns (values, is_range)."""
    v = leaf(x)
    if v is not None:
        return [v], False
    if isinstance(x, list):
        vals = [leaf(i) for i in x]
        return [i for i in vals if i is not None], False
    if isinstance(x, dict):
        if "min" in x and "max" in x:
            return [i for i in (leaf(x.get("min")), leaf(x.get("max"))) if i is not None], True
        vals = [leaf(val) for k, val in x.items() if k == "default" or re.match(r"alt\d+$", str(k))
                or k in ("enum", "values")]
        flat = []
        for k, val in x.items():
            if k in ("enum", "values") and isinstance(val, list):
                flat += [leaf(i) for i in val]
        return [i for i in vals + flat if i is not None], False
    return [], False


def _pw_size(x: Any):
    if isinstance(x, dict) and "width" in x and "height" in x:
        return int(x["width"]), int(x["height"])
    return None


def _pw_rate(x: Any):
    if isinstance(x, dict) and "num" in x and "denom" in x:
        return round(float(x["num"]) / float(x["denom"]), 2) if x["denom"] else None
    return None


def parse_pw_formats(enum_formats: list[dict[str, Any]]) -> dict[tuple, dict[str, Any]]:
    out: dict[tuple, dict[str, Any]] = {}
    for f in enum_formats or []:
        if not isinstance(f, dict) or f.get("mediaType") not in (None, "video"):
            continue
        sub = str(f.get("mediaSubtype") or "").lower()
        if sub == "raw":
            fmts, _ = _pw_values(f.get("format"), lambda x: x if isinstance(x, str) else None)
            fccs = [PW_RAW.get(x, x) for x in fmts]
        else:
            fccs = [PW_SUBTYPE.get(sub, sub.upper())]
        sizes, srange = _pw_values(f.get("size"), _pw_size)
        rates, rrange = _pw_values(f.get("framerate"), _pw_rate)
        if srange:
            sizes = [(-1, -1)]
        for fcc in fccs:
            for w, h in sizes:
                ent = out.setdefault((fcc, w, h), {"fps": [], "continuous": False})
                if rrange or srange:
                    ent["continuous"] = True
                else:
                    ent["fps"] = sorted(set((ent["fps"] or []) + [r for r in rates if r]), reverse=True)
    return out


def pw_nodes_for(objs: list[dict[str, Any]], cam: dict[str, Any], cams: list[dict[str, Any]]) -> list[dict]:
    """Video nodes in a pw-dump that belong to this camera: v4l2 nodes by api.v4l2.path / object.path; libcamera
    nodes when the camera's VID:PID appears in the node's path and no other camera has the same VID:PID."""
    out = []
    vp = f"{cam['vid']}:{cam['pid']}".lower()
    unique_vp = sum(1 for c in cams if f"{c['vid']}:{c['pid']}".lower() == vp) == 1
    for o in objs or []:
        info = o.get("info") or {}
        props = info.get("props") or {}
        if not str(props.get("media.class", "")).startswith("Video/"):
            continue
        api = props.get("device.api") or ("v4l2" if props.get("api.v4l2.path") else None)
        path = props.get("api.v4l2.path") or ""
        objp = str(props.get("object.path") or "")
        mapped = None
        if path == cam["node"] or objp == f"v4l2:{cam['node']}":
            mapped = "api.v4l2.path"
        elif api == "libcamera" and unique_vp and vp in json.dumps(props).lower():
            mapped = "VID:PID in libcamera props (unique)"
        if not mapped:
            continue
        params = info.get("params") or {}
        out.append({"id": o.get("id"), "api": api, "node.name": props.get("node.name"), "mapped_by": mapped,
                    "state": info.get("state"), "has_enum_format": "EnumFormat" in params,
                    "enum_format": params.get("EnumFormat") or []})
    return out


# ------------------------------------------------------------------------------------------- methods
def _desc_of(cam: dict[str, Any]) -> dict[str, Any]:
    return cam.get("descriptors") or {}


def m_sysfs(ctx, cam, cams) -> dict[str, Any]:
    t0 = _now()
    try:
        raw = (sysfs.P(cam["sysfs_dir"]) / "descriptors").read_bytes() if cam.get("sysfs_dir") else None
        summ = sysfs.descriptor_summary(raw, cam.get("speed"))
        modes = analysis.desc_mode_set(summ) if summ.get("ok") else None
        err = None if summ.get("ok") else {"message": summ.get("error") or "descriptor parse failed"}
    except OSError as e:
        modes, err, raw = None, {"message": f"{type(e).__name__}: {e}", "errno": getattr(e, "errno", None)}, None
    return {"ok": modes is not None, "modes": modes, "error": err, "elapsed_ms": round((_now() - t0) / 1e6, 3),
            "bytes": len(raw) if raw else 0}


def m_v4l2ctl(ctx, cam, cams) -> dict[str, Any]:
    t0 = _now()
    r = ctx.run_child(["v4l2-ctl", "-d", cam["node"], "--list-formats-ext"], 15)
    el = round((_now() - t0) / 1e6, 3)
    if r.get("rc") != 0 or r.get("timed_out"):
        return {"ok": False, "modes": None, "elapsed_ms": el, "child": child_outcome(r),
                "error": {"message": (r.get("stderr") or "")[-400:] or f"rc={r.get('rc')}",
                          "timed_out": r.get("timed_out")}}
    modes = parse_v4l2_ctl(r.get("stdout") or "")
    return {"ok": bool(modes), "modes": modes, "elapsed_ms": el, "error": None if modes else
            {"message": "no format parsed from v4l2-ctl output", "stdout_head": (r.get("stdout") or "")[:400]}}


def m_pipewire(ctx, cam, cams) -> dict[str, Any]:
    t0 = _now()
    r = ctx.run_child(["pw-dump", "-N"], 15)
    el = round((_now() - t0) / 1e6, 3)
    if r.get("rc") != 0 or r.get("timed_out"):
        return {"ok": False, "modes": None, "elapsed_ms": el, "child": child_outcome(r),
                "error": {"message": (r.get("stderr") or "")[-400:] or f"rc={r.get('rc')}"}}
    try:
        objs = json.loads(r.get("stdout") or "[]")
    except ValueError as e:
        return {"ok": False, "modes": None, "elapsed_ms": el, "error": {"message": f"pw-dump JSON: {e}"}}
    nodes = pw_nodes_for(objs, cam, cams)
    v4 = [n for n in nodes if n["api"] != "libcamera"]
    lc = [n for n in nodes if n["api"] == "libcamera"]
    modes: dict[tuple, dict[str, Any]] = {}
    for n in v4:
        for k, v in parse_pw_formats(n["enum_format"]).items():
            e = modes.setdefault(k, {"fps": [], "continuous": False})
            e["continuous"] = e["continuous"] or v["continuous"]
            e["fps"] = sorted(set((e["fps"] or []) + (v["fps"] or [])), reverse=True)
    lc_out = [{"id": n["id"], "node.name": n["node.name"], "mapped_by": n["mapped_by"],
               "has_enum_format": n["has_enum_format"],
               "completeness": completeness(parse_pw_formats(n["enum_format"]), _desc_of(cam))} for n in lc]
    nodes_slim = [{k: v for k, v in n.items() if k != "enum_format"} | {"n_enum_format": len(n["enum_format"])}
                  for n in nodes]
    if not v4:
        why = "no PipeWire v4l2 node for this camera" if not nodes else "only libcamera nodes for this camera"
        return {"ok": False, "modes": None, "elapsed_ms": el, "nodes": nodes_slim, "libcamera_nodes": lc_out,
                "error": {"message": why}}
    if not modes:
        return {"ok": False, "modes": None, "elapsed_ms": el, "nodes": nodes_slim, "libcamera_nodes": lc_out,
                "error": {"message": "the node has no EnumFormat params in pw-dump"}}
    return {"ok": True, "modes": modes, "elapsed_ms": el, "nodes": nodes_slim, "libcamera_nodes": lc_out,
            "error": None}


ONCE = {"sysfs_descriptors": m_sysfs, "v4l2_ctl": m_v4l2ctl, "pipewire": m_pipewire}


class AltSampler:
    """VS-interface bAlternateSetting from sysfs every ~30 ms (world-readable; no device access)."""

    def __init__(self, cam: dict[str, Any], period_s: float = 0.03):
        self.ud = sysfs.P(cam["sysfs_dir"]) if cam.get("sysfs_dir") else None
        self.period = period_s
        self.samples: list[tuple[int, tuple]] = []
        self.stop_ev = threading.Event()
        self.th = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self.stop_ev.is_set():
            try:
                alts = tuple(v.get("alt") for v in sysfs.vs_interfaces(self.ud)) if self.ud else ()
            except OSError:
                alts = ()
            self.samples.append((_now(), alts))
            self.stop_ev.wait(self.period)

    def start(self) -> "AltSampler":
        self.th.start()
        return self

    def stop(self) -> None:
        self.stop_ev.set()
        self.th.join(timeout=2)

    def between(self, t0: int, t1: int) -> list[tuple]:
        return [a for t, a in self.samples if t0 <= t <= t1]


def probe_capture(ctx, cam, mode, od: Path) -> dict[str, Any]:
    """A 1-frame capture from another process (the 'third process' of the blocking check)."""
    t0 = _now()
    r = ctx.run_child(ctx.worker_cmd("capture", "--device", cam["node"], *mode_args(mode), "--frames", 1,
                                     "--out-dir", od, "--save", "none", "--first-frame-timeout-ms", 4000), 25)
    j = r.get("json") or {}
    n = ((j.get("stream") or {}).get("counts") or {}).get("frames", 0)
    return {"ok": bool(n), "frames": n, "error": worker_error(r), "t_start_ns": t0, "t_end_ns": _now(),
            "elapsed_ms": round((_now() - t0) / 1e6, 1), "classification": apis.classify(worker_error(r))}


def measure(ctx, cam, cams, method: str, cond: str, od: Path, probe_mode: dict | None,
            baseline_probe_ok: bool | None) -> dict[str, Any]:
    """One method under one condition: first listing, the hold (fd held or repeated), alt samples, and (idle) the
    third-process capture halfway through the hold."""
    H = hold_s(ctx)
    od.mkdir(parents=True, exist_ok=True)
    samp = AltSampler(cam).start()
    t0 = _now()
    rec: dict[str, Any] = {"method": method, "condition": cond, "hold_kind": METHOD_INFO[method]["hold"]}
    holder: dict[str, Any] = {}
    th = None
    if method == "v4l2_enum_no_streamon":
        sig = od / "hold_started"
        try:
            sig.unlink()
        except OSError:
            pass
        argv = ctx.worker_cmd("formats", "--device", cam["node"], "--hold-ms", int(H * 1000), "--hold-signal", sig)
        th = threading.Thread(target=lambda: holder.update(ctx.run_child(argv, 30 + H)), daemon=True)
        th.start()
        dl = time.monotonic() + 20
        while th.is_alive() and not sig.exists() and time.monotonic() < dl:
            _wait(0.01)
        t_hold = _now()
        rec["hold_signal_seen"] = sig.exists()
    else:
        first = ONCE[method](ctx, cam, cams)
        t_hold = _now()
        holder["first"] = first
        reps = {"n": 0, "failures": 0, "inconsistent": 0}
        ref = mode_tuples(first.get("modes"))

        def loop() -> None:
            end = t_hold + int(H * 1e9)
            while _now() < end:
                x = ONCE[method](ctx, cam, cams)
                reps["n"] += 1
                reps["failures"] += 0 if x.get("ok") else 1
                reps["inconsistent"] += 0 if mode_tuples(x.get("modes")) == ref else 1
                _wait(0.02)
        th = threading.Thread(target=loop, daemon=True)
        th.start()
        rec["repeats_during_hold"] = reps
    third = None
    if cond == "idle":
        _wait((t_hold + int(H * 0.5e9) - _now()) / 1e9)
        t_alt_end = _now()
        if probe_mode is None:
            third = {"untested": "no in-scope MJPEG mode for the 1-frame probe (mode scope)"}
        elif baseline_probe_ok is False:
            third = {"untested": "the same 1-frame capture fails with no lister (baseline): blocking not measurable"}
        else:
            third = probe_capture(ctx, cam, probe_mode, od / "third_process")
    if th is not None:
        th.join(timeout=40 + H)
    t1 = _now()
    if cond != "idle":
        t_alt_end = t1
    samp.stop()
    # ---- the listing result
    if method == "v4l2_enum_no_streamon":
        j = holder.get("json") or {}
        err = worker_error(holder) if holder else {"message": "child did not finish"}
        modes = analysis.v4l2_mode_set(j["formats"]) if j.get("formats") else None
        res = {"ok": bool(modes) and not err, "modes": modes, "error": err, "elapsed_ms": j.get("list_ms"),
               "child": child_outcome(holder) if holder else None, "worker_hold": j.get("hold")}
    else:
        res = holder["first"]
    rec.update({k: v for k, v in res.items() if k != "modes"})
    rec["completeness"] = completeness(res.get("modes"), _desc_of(cam)) if res.get("ok") else None
    alts = samp.between(t0, t_alt_end)
    flat = sorted({a for s in alts for a in s if a is not None})
    rec["alt"] = {"samples": len(alts), "alts_seen": flat, "window": "listing + first half of the hold"
                  if cond == "idle" else "listing + hold"}
    if method == "v4l2_enum_no_streamon" and isinstance(res.get("worker_hold"), dict):
        # the worker samples the whole hold, including the third-process probe's own stream (idle): info only
        rec["alt"]["worker_alts_seen_during_hold"] = res["worker_hold"].get("alts_seen")
    if cond == "idle":
        rec["alt"]["starts_stream"] = (any(a > 0 for a in flat) if alts else None)
    rec["window_ns"] = [t0, t1]
    if third is not None:
        if "untested" in third:
            rec["third_process"] = {**third, "blocked": None}
        else:
            blocked = not third["ok"]
            if method == "sysfs_descriptors":
                basis = "measured (the method holds no device handle)"
            else:
                basis = "measured: probe started halfway through the hold"
            rec["third_process"] = {**third, "blocked": blocked, "basis": basis,
                                    "overlapped_hold": third["t_start_ns"] < t_hold + int(H * 1e9)}
    return rec


# ------------------------------------------------------------------------------------------- streams
def _stream_argv(ctx, cam, api: str, mode: dict, seconds: float, od: Path) -> list[str]:
    fps = float(mode["fps"])
    if api == "pyav":
        return ctx.helper_cmd("pyav_v4l2.py", "capture", "--device", cam["node"], "--width", mode["w"],
                              "--height", mode["h"], "--fps", f"{fps:g}", "--seconds", seconds, "--out-dir", od,
                              "--save", "none")
    return ctx.worker_cmd("capture", "--device", cam["node"], *mode_args(mode), "--seconds", seconds,
                          "--out-dir", od, "--save", "none", "--timeout-ms", apis.frame_timeout_ms(fps),
                          "--first-frame-timeout-ms", 5000)


def disturbance(rows: list[dict[str, Any]], window: list[int], fps: float, baseline: tuple[int, int],
                stream_end_ns: int | None, stream_error_ns: int | None) -> dict[str, Any]:
    """Did the other process's stream suffer during the listing window? Frame arrival times (host_ns, the same
    CLOCK_MONOTONIC as the runner), ERROR-flagged / zero-length frames as bad frames. common.nograb.disturbance's
    shape; the fallback applies the same thresholds."""
    ts = sorted(int(r["host_ns"]) for r in rows if isinstance(r.get("host_ns"), (int, float)))
    bad = [int(r["host_ns"]) for r in rows if isinstance(r.get("host_ns"), (int, float))
           and (r.get("error") or r.get("zero_len"))]
    if _ng is not None:
        try:
            out = _ng.disturbance(ts, (int(window[0]), int(window[1])), baseline=baseline, bad_frame_ts_ns=bad,
                                  stream_error_ns=stream_error_ns, stream_end_ns=stream_end_ns, nominal_fps=fps)
            out["source"] = "common.nograb.disturbance"
            return out
        except Exception:  # noqa: BLE001
            pass
    t0, t1 = int(window[0]), int(window[1])
    base = [b - a for a, b in zip(ts, ts[1:]) if a >= baseline[0] and b <= baseline[1]]
    win = [(b - a) for a, b in zip(ts, ts[1:]) if (t0 <= b <= t1) or (t0 <= a <= t1 < b) or (a < t0 and b > t1)]
    p50 = (sorted(base)[len(base) // 2] / 1e6) if base else 1000.0 / max(fps, 1.0)
    bmax = (max(base) / 1e6) if base else p50
    thr = max(3.0 * p50, 1.5 * bmax, bmax + 25.0)
    wmax = (max(win) / 1e6) if win else None
    nbad = sum(1 for t in bad if t0 <= t <= t1)
    after = [t for t in ts if t > t1]
    stopped = bool(ts) and not after and (stream_end_ns is None or stream_end_ns > t1 + 300_000_000)
    err_in = stream_error_ns is not None and t0 - 100_000_000 <= stream_error_ns <= t1 + 1_000_000_000
    gap = wmax is not None and wmax > thr
    in_win = [t for t in ts if t0 <= t <= t1]
    no_frames = not in_win and (t1 - t0) > 3e6 * p50
    why = [x for x, c in (("gap", gap), ("bad_frames", bool(nbad)), ("stream_error", err_in),
                          ("stream_stopped", stopped), ("no_frames_in_window", no_frames)) if c]
    return {"disturbed": bool(why) if ts else None, "why": why, "window_ms": round((t1 - t0) / 1e6, 1),
            "frames_in_window": len(in_win), "frames_after_window": len(after), "baseline_frames": len(base) + 1,
            "baseline_p50_interval_ms": round(p50, 2), "baseline_max_interval_ms": round(bmax, 2),
            "window_max_interval_ms": None if wmax is None else round(wmax, 2), "gap_threshold_ms": round(thr, 2),
            "bad_frames_in_window": nbad, "stream_error_in_window": err_in, "stream_stopped_in_window": stopped,
            "measured": bool(ts), "source": "linux fallback (same rule)"}


def run_condition_stream(ctx, cam, cams, cond: str, api: str, mode: dict, methods: list[str], cs: str
                         ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    od = ctx.test_dir(TEST, cs, cond, "stream")
    secs = stream_seconds(ctx, len(methods))
    argv = _stream_argv(ctx, cam, api, mode, secs, od)
    holder: dict[str, Any] = {}
    to = apis.capture_timeout(secs, float(mode["fps"])) + (30 if api == "pyav" else 0)
    th = threading.Thread(target=lambda: holder.update(ctx.run_child(argv, to)), daemon=True)
    ctx.log(f"{cam['name']} {cond}: {api} stream {mode_text(mode)} for {secs}s")
    t_start = _now()
    th.start()
    frames_file = od / "frames.jsonl"
    dl = time.monotonic() + (25 if api == "pyav" else 8)
    while th.is_alive() and time.monotonic() < dl and not results.read_jsonl(frames_file):
        _wait(0.05)
    info: dict[str, Any] = {"api": api, "mode": mode_text(mode), "seconds": secs}
    first_rows = results.read_jsonl(frames_file)
    if not first_rows:
        th.join(timeout=to + 5)
        info.update(started=False, child=child_outcome(holder) if holder else None,
                    error=worker_error(holder) if holder else {"message": "stream child did not finish"})
        return info, {}
    info["started"] = True
    info["first_frame_after_ms"] = round((_now() - t_start) / 1e6, 1)
    first_ns = int(first_rows[0].get("host_ns") or _now())
    _wait(baseline_s(ctx))
    baseline_end = _now()
    st_alts = sorted({v.get("alt") for v in (sysfs.vs_interfaces(sysfs.P(cam["sysfs_dir"]))
                                             if cam.get("sysfs_dir") else [])} - {None})
    info["stream_alts"] = st_alts
    recs = {}
    for m in methods:
        ctx.log(f"{cam['name']} {cond}: {m}")
        recs[m] = measure(ctx, cam, cams, m, cond, ctx.test_dir(TEST, cs, cond, m), None, None)
        _wait(min(0.5, hold_s(ctx)))   # a gap between windows
    th.join(timeout=to + 5)
    rows = results.read_jsonl(frames_file)
    err = worker_error(holder) if holder else {"message": "stream child did not finish"}
    info.update(child=child_outcome(holder) if holder else None, error=err, frames=len(rows),
                fps_nominal=float(mode["fps"]))
    ts = sorted(int(r["host_ns"]) for r in rows if isinstance(r.get("host_ns"), (int, float)))
    planned_end = first_ns + int(secs * 1e9)
    # a stream that failed before its planned end: its last frame is the best estimate of when the error came
    err_ns = ts[-1] if (err and ts and ts[-1] < planned_end - 500_000_000) else None
    base_win = (first_ns + min(500_000_000, int(baseline_s(ctx) * 0.5e9)), baseline_end)
    info.update(planned_end_ns=planned_end, baseline_window_ns=list(base_win), stream_error_ns=err_ns)
    for m, rec in recs.items():
        ws, we = rec["window_ns"]
        if not ts or ts[-1] < ws:
            rec["disturbance"] = {"disturbed": None, "measured": False,
                                  "why": ["the stream had ended before this window" + (" (with an error)" if err
                                                                                      else " (planned length)")]}
        elif not err and planned_end < we:
            rec["disturbance"] = {"disturbed": None, "measured": False,
                                  "why": ["the stream's planned length ended inside this window"]}
        else:
            rec["disturbance"] = disturbance(rows, rec["window_ns"], float(mode["fps"]), base_win,
                                             planned_end if not err else ts[-1], err_ns)
        seen = rec["alt"]["alts_seen"]
        rec["alt"]["stream_alts"] = st_alts
        rec["alt"]["alt_changed"] = (bool(set(seen) - set(st_alts)) or (bool(st_alts) and not seen)) \
            if rec["alt"]["samples"] else None
    return info, recs


# ------------------------------------------------------------------------------------------- rating
def contract_conditions(conds: dict[str, dict[str, Any] | None], untested_why: dict[str, str]
                        ) -> dict[str, dict[str, Any]]:
    """Per-condition records -> common.rating.rate_fmt_nograb's input."""
    out: dict[str, dict[str, Any]] = {}
    for c in CONDITIONS:
        r = conds.get(c)
        if r is None:
            out[c] = {"tested": False, "untested_reason": untested_why.get(c) or "condition not run"}
            continue
        comp = r.get("completeness") or {}
        alt = r.get("alt") or {}
        out[c] = {"tested": True, "untested_reason": None, "succeeded": bool(r.get("ok")),
                  "complete": comp.get("complete") if r.get("ok") else False,
                  "disturbed": None if c == "idle" else (r.get("disturbance") or {}).get("disturbed"),
                  "stream_started": alt.get("starts_stream") if c == "idle" else None,
                  "blocked": (r.get("third_process") or {}).get("blocked") if c == "idle" else None,
                  "elapsed_s": None if r.get("elapsed_ms") is None else round(float(r["elapsed_ms"]) / 1000, 4),
                  "alt_changed": alt.get("alt_changed"), "alts_seen": alt.get("alts_seen")}
    return out


def rate_contract_local(conditions: dict[str, dict[str, Any]], method: str | None = None) -> dict[str, Any]:
    """The rate_fmt_nograb rule, used only when common.rating lacks it."""
    ev = {"method": method, "conditions": conditions}
    idle = conditions.get("idle") or {}
    if not idle.get("tested"):
        return rating.untested(idle.get("untested_reason") or "idle condition not run", ev)
    tested = {k: c for k, c in conditions.items() if c.get("tested")}
    untested_c = {k: c.get("untested_reason") for k, c in conditions.items() if not c.get("tested")}
    complete_all = all(c.get("succeeded") and c.get("complete") for c in tested.values())
    started = [k for k, c in tested.items() if c.get("stream_started") is True]
    disturbed = [k for k, c in tested.items() if c.get("disturbed") is True]
    blocked = [k for k, c in tested.items() if c.get("blocked") is True]
    dist_measured = [k for k, c in tested.items() if k != "idle" and c.get("disturbed") is not None]
    crit = [{"criterion": "complete vs the USB descriptors (MJPEG and raw) in every condition", "met": complete_all,
             "detail": None},
            {"criterion": "does not disturb another process's stream",
             "met": None if not dist_measured else not disturbed, "detail": disturbed},
            {"criterion": "starts no stream and reserves no bandwidth",
             "met": None if idle.get("stream_started") is None else not started, "detail": started},
            {"criterion": "does not block another process from opening the camera",
             "met": None if all(c.get("blocked") is None for c in tested.values()) else not blocked, "detail": blocked},
            {"criterion": "all three conditions measured", "met": not untested_c, "detail": untested_c or None}]
    if started:
        return {"rating": "no", "criteria": crit, "evidence": ev, "note": "needs a stream"}
    if not (idle.get("succeeded") and idle.get("complete")):
        return {"rating": "no", "criteria": crit, "evidence": ev,
                "note": "failed with the camera idle" if not idle.get("succeeded") else "incomplete when idle"}
    if not complete_all or disturbed or blocked:
        return {"rating": "partial", "criteria": crit, "evidence": ev,
                "note": "complete when idle only, or disturbs / blocks"}
    if all(c["met"] is True for c in crit):
        return {"rating": "yes", "criteria": crit, "evidence": ev}
    return {"rating": "partial", "criteria": crit, "evidence": ev, "provisional": True,
            "note": "provisional: a condition or measurement is missing", "summary_label": "partial (provisional)"}


def rate_method(method: str, conds: dict[str, dict[str, Any] | None], avail: tuple[bool, str | None],
                untested_why: dict[str, str] | None = None) -> dict[str, Any]:
    ok_, why = avail
    if not ok_:
        return rating.untested(why or "method unavailable")
    cc = contract_conditions(conds, untested_why or {})
    fn = getattr(rating, "rate_fmt_nograb", None)
    r = fn(cc, method=method) if fn is not None else rate_contract_local(cc, method)
    changed = [c for c, x in cc.items() if x.get("alt_changed") is True]
    if changed and r.get("rating") == "yes":   # a listing that changed a running stream's alt: Linux extra check
        r = {**r, "rating": "partial", "note": f"the stream's VS alt changed during the listing ({changed})",
             "summary_label": "partial (alt changed)"}
    r["rule"] = "common.rating.rate_fmt_nograb" if fn is not None else "linux fallback (same rule)"
    return r


# ------------------------------------------------------------------------------------------- run
def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST)
    errors: list[dict] = []
    av = available_methods(ctx)
    methods = [m for m in METHODS if av[m][0]]
    api2 = second_api(ctx)
    per_cam: dict[str, Any] = {}
    ratings: dict[str, dict[str, Any]] = {m: {} for m in METHODS}
    table: list[dict[str, Any]] = []
    cams = ctx.cameras
    for cam in cams:
        skip = gate(ctx, cam, TEST)
        if skip:
            per_cam[cam["key"]] = skip
            for m in METHODS:
                ratings[m][cam["key"]] = rating.untested(skip["reason"])
            continue
        cs = ctx.slug(cam)
        pk = scope.picks(ctx, cam)
        mode = pk["default"]
        ent: dict[str, Any] = {"is_kiyo": cam.get("is_kiyo"), "stream_mode": mode_text(mode),
                               "mode_scope": pk["record"], "conditions": {}}
        conds: dict[str, dict[str, dict[str, Any] | None]] = {m: {c: None for c in CONDITIONS} for m in methods}
        why_untested: dict[str, str] = {}
        with ctx.camera_lock() as locked:
            if not locked:
                per_cam[cam["key"]] = {"skipped": True, "reason": "camera lock not acquired"}
                for m in METHODS:
                    ratings[m][cam["key"]] = rating.untested("camera lock not acquired")
                continue
            base = None
            if mode is not None:
                base = probe_capture(ctx, cam, mode, ctx.test_dir(TEST, cs, "baseline_probe"))
                base = {k: v for k, v in base.items() if not k.startswith("t_")}
            ent["baseline_probe"] = base or {"untested": "no in-scope MJPEG mode (mode scope)"}
            ent["conditions"]["idle"] = {}
            for m in methods:
                ctx.log(f"{cam['name']} idle: {m}")
                rec = measure(ctx, cam, cams, m, "idle", ctx.test_dir(TEST, cs, "idle", m), mode,
                              None if base is None else base["ok"])
                conds[m]["idle"] = rec
                ent["conditions"]["idle"][m] = rec
                if not rec.get("ok"):
                    errors.append({"camera": cam["key"], "method": m, "condition": "idle", "error": rec.get("error"),
                                   "is_kiyo": cam.get("is_kiyo")})
            for cond, api in (("streaming_native", "v4l2"), ("streaming_second_api", api2)):
                if mode is None:
                    why_untested[cond] = ("no in-scope MJPEG mode for the condition stream (mode scope; --all-modes "
                                          "to use any mode)")
                    ent["conditions"][cond] = {"untested": why_untested[cond]}
                    continue
                b = ctx.busy(cam)
                if b["streamed_by_other"]:
                    why_untested[cond] = "camera already streamed by another process before the condition stream"
                    ent["conditions"][cond] = {"untested": why_untested[cond], "busy": b}
                    continue
                info, recs = run_condition_stream(ctx, cam, cams, cond, api, mode, methods, cs)
                ent["conditions"][cond] = {"stream": info, **recs}
                if not info.get("started"):
                    why_untested[cond] = "the condition stream did not start"
                    ent["conditions"][cond]["untested"] = why_untested[cond]
                    errors.append({"camera": cam["key"], "condition": cond, "stage": "condition stream",
                                   "error": info.get("error"), "is_kiyo": cam.get("is_kiyo")})
                for m, rec in recs.items():
                    conds[m][cond] = rec
        for m in METHODS:
            r = rate_method(m, conds.get(m) or {}, av[m], why_untested)
            ratings[m][cam["key"]] = r
        for m in methods:
            for c in CONDITIONS:
                rec = conds[m].get(c)
                if rec is None:
                    continue
                comp = (rec.get("completeness") or {}).get("per_class") or {}
                table.append({"camera": cam["name"], "key": cam["key"], "method": m, "condition": c,
                              "ok": rec.get("ok"), "complete": (rec.get("completeness") or {}).get("complete"),
                              "complete_mjpeg": (comp.get("mjpeg") or {}).get("complete"),
                              "complete_raw": (comp.get("raw") or {}).get("complete"),
                              "elapsed_ms": rec.get("elapsed_ms"),
                              "disturbed": (rec.get("disturbance") or {}).get("disturbed"),
                              "window_max_interval_ms": (rec.get("disturbance") or {}).get("window_max_interval_ms"),
                              "alts_seen": (rec.get("alt") or {}).get("alts_seen"),
                              "starts_stream": (rec.get("alt") or {}).get("starts_stream"),
                              "blocked": (rec.get("third_process") or {}).get("blocked")})
        ent["ratings"] = {m: ratings[m][cam["key"]]["rating"] for m in METHODS}
        per_cam[cam["key"]] = ent
    verdicts = {f"FMT-NOGRAB:{m}": (combine(ratings[m], m) if ratings[m] else rating.untested("no camera"))
                for m in METHODS}
    summary = {m: verdicts[f"FMT-NOGRAB:{m}"]["rating"] for m in METHODS}
    meas = {"methods": {m: {**METHOD_INFO[m], "available": av[m][0], "unavailable_reason": av[m][1]}
                        for m in METHODS},
            "conditions": {"idle": "no stream", "streaming_native": "raw V4L2 capture (camworker) in another process",
                           "streaming_second_api": ("PyAV v4l2 (input_format=mjpeg) in another process"
                                                    if api2 == "pyav" else
                                                    "a second raw-V4L2 process (PyAV unavailable)")},
            "hold_ms": hold_s(ctx) * 1000, "baseline_s": baseline_s(ctx),
            "mode_scope": {**scope.settings(ctx.args), "note": "listings compare every mode; the scope applies only "
                                                              "to the condition streams and 1-frame probes"},
            "cameras": per_cam, "table": table, "summary": summary,
            "methods_rated_yes": [m for m, r in summary.items() if r == "yes"],
            "reference": "the sysfs descriptors blob parsed by linuxlib/usbdesc.py (no independent ep0 read: that "
                         "needs usbfs access, which the suite never uses)",
            "shared_code": {"compare": "common.nograb" if _ng is not None else "linux fallback",
                            "rating": "common.rating.rate_fmt_nograb" if hasattr(rating, "rate_fmt_nograb")
                            else "linux fallback"}}
    results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)
    return res
