"""The context object passed to every macOS test module (tests/m_<name>.py: run(ctx) -> result dict), plus small
shared helpers (mode picking, child-result parsing, caches). Stdlib only; never imports PyObjC.

Camera work never runs in this process: ctx.avf(...) and ctx.ep0(...) start helpers/mac_avf.py and
helpers/mac_ep0.py as child processes through common.procutil (whole process group killed on timeout), and the
helpers arm their own deadline as well. A hang is a result.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

MACOS_DIR = Path(__file__).resolve().parent
SUITE_DIR = MACOS_DIR.parent
HELPERS_DIR = MACOS_DIR / "helpers"
for _p in (str(SUITE_DIR), str(HELPERS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from common import procutil, results  # noqa: E402

JPEG_SUBTYPES = {"dmb1", "jpeg", "mjpa", "mjpb"}


def slug(text: Any, maxlen: int = 80) -> str:
    """A path-safe name for a camera key / label ('046d:085c:sn=C922SN01' -> '046d_085c_sn-C922SN01')."""
    import re
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", str(text).replace("=", "-")).strip("_")
    return s[:maxlen] or "x"


def cam_tag(cam: dict) -> str:
    return slug(f"{cam.get('vid')}_{cam.get('pid')}_{cam.get('location_hex')}")


def parse_child_json(stdout: str) -> dict | None:
    """The helpers print one JSON object on the last non-empty stdout line."""
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


@dataclass
class SuiteCtx:
    out_dir: Path
    raw_dir: Path
    args: argparse.Namespace
    cameras: list[dict] = field(default_factory=list)
    snapshot: dict | None = None
    avf_devices: list[dict] = field(default_factory=list)
    prelude: dict = field(default_factory=dict)
    tcc: str | None = None
    reduced: bool = False
    python: list[str] = field(default_factory=lambda: [sys.executable])
    cache_dir: Path | None = None
    command: list[str] = field(default_factory=lambda: list(sys.argv))
    runner: Callable[..., dict] = procutil.run
    log_fn: Callable[[str], None] = print
    helpers_dir: Path = HELPERS_DIR
    suite_dir: Path = SUITE_DIR
    child_log: list[dict] = field(default_factory=list)
    store: dict = field(default_factory=dict)  # results one test hands to a later one (e.g. ctrl ranges)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ---------------------------------------------------------------- logging / output
    def log(self, msg: str) -> None:
        self.log_fn(f"[macos-suite] {msg}")

    def write(self, name: str, obj: Any) -> Path:
        return results.write_json(self.out_dir / (name if name.endswith(".json") else f"{name}.json"), obj)

    def subdir(self, *parts: str) -> Path:
        p = self.out_dir.joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def rawsub(self, *parts: str) -> Path:
        p = self.raw_dir.joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def scale(self) -> float:
        return float(getattr(self.args, "child_timeout_scale", 1.0) or 1.0)

    # ---------------------------------------------------------------- children
    def helper(self, script: str, args: list[Any], timeout_s: float, label: str | None = None) -> dict:
        """Run helpers/<script> with the suite interpreter; the child gets --deadline-s slightly below timeout_s.
        Returns {argv, rc, timed_out, killed, elapsed_s, json, stderr_tail, ok}."""
        timeout_s = float(timeout_s) * self.scale
        argv = [*self.python, str(self.helpers_dir / script), *[str(a) for a in args]]
        if "--deadline-s" not in argv:
            argv += ["--deadline-s", f"{max(5.0, timeout_s - 5.0):.0f}"]
        r = self.runner(argv, timeout_s + 5.0)
        j = parse_child_json(r.get("stdout", ""))
        out = {"argv": argv, "rc": r.get("rc"), "timed_out": bool(r.get("timed_out")), "killed": bool(r.get("killed")),
               "elapsed_s": r.get("elapsed_s"), "json": j, "stderr_tail": (r.get("stderr") or "")[-1500:],
               "spawn_error": r.get("spawn_error"), "label": label}
        out["ok"] = bool(j and j.get("ok")) and not out["timed_out"]
        out["hung"] = out["timed_out"] or bool(j and j.get("timed_out"))
        with self._lock:
            self.child_log.append({k: out[k] for k in ("label", "rc", "timed_out", "elapsed_s", "ok")} |
                                  {"argv": argv[1:]})
        return out

    def avf(self, args: list[Any], timeout_s: float, label: str | None = None) -> dict:
        return self.helper("mac_avf.py", args, timeout_s, label)

    def ep0(self, cam: dict, cmd: str, extra: list[Any] | None = None, timeout_s: float = 30.0) -> dict:
        """mac_ep0.py for one camera. Callers check ctx.ep0_enabled first (opt-in)."""
        args = [cmd, "--location", cam["location_hex"], "--vid", cam["vid"], "--pid", cam["pid"],
                "--backend", self.args.ep0_backend]
        if cam.get("vc_interface") is not None:
            args += ["--vc-if", cam["vc_interface"]]
        ent = self.entities_file(cam)
        if ent is not None and cmd != "descriptors":
            args += ["--entities", ent]
        if self.ep0_allow_seize:
            args += ["--allow-seize"]
        return self.helper("mac_ep0.py", args + list(extra or []), timeout_s, label=f"ep0 {cmd} {cam['key']}")

    @property
    def ep0_enabled(self) -> bool:
        return bool(getattr(self.args, "ep0", False))

    @property
    def ep0_allow_seize(self) -> bool:
        """Only the libusb backend seizes; it needs the operator's explicit --ep0-allow-seize (plan 6.1)."""
        return bool(getattr(self.args, "ep0_allow_seize", False)) and getattr(self.args, "ep0_backend", "") == "libusb"

    def ep0_capture_args(self, cam: dict) -> list[str]:
        """Arguments for mac_avf.py capture so it can run scheduled ep0 actions in-process."""
        if not self.ep0_enabled or not cam.get("location_hex"):
            return []
        out = ["--ep0-location", cam["location_hex"], "--ep0-backend", self.args.ep0_backend,
               "--vid", cam["vid"], "--pid", cam["pid"]]
        if cam.get("vc_interface") is not None:
            out += ["--vc-if", str(cam["vc_interface"])]
        ent = self.entities_file(cam)
        if ent:
            out += ["--ep0-entities", ent]
        if self.ep0_allow_seize:
            out += ["--ep0-allow-seize"]
        return out

    # ---------------------------------------------------------------- caches (outside the repo)
    def cache_path(self, name: str) -> Path | None:
        if self.cache_dir is None:
            return None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return self.cache_dir / name

    def desc_cache(self) -> dict:
        p = self.cache_path("uvc_descriptors.json")
        if p is None or not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return {}

    def save_desc(self, cam: dict, desc: dict) -> None:
        p = self.cache_path("uvc_descriptors.json")
        if p is None or not desc.get("config_hex"):
            return
        with self._lock:
            c = self.desc_cache()
            key = f"{cam['vid']}:{cam['pid']}:{cam.get('bcd_device')}"
            c[key] = {k: desc.get(k) for k in ("config_hex", "entities", "alt_table", "frames", "source")}
            results.write_json(p, c)
        # the bandwidth model needs the alt table now, not only on the next run
        for sc in (self.snapshot or {}).get("cameras", []):
            if (sc.get("vid"), sc.get("pid")) == (cam.get("vid"), cam.get("pid")) and not sc.get("alt_table"):
                sc["alt_table"] = desc.get("alt_table")
        cam["uvc"] = {k: desc.get(k) for k in ("entities", "alt_table", "frames", "source")}

    def cam_desc(self, cam: dict) -> dict | None:
        c = self.desc_cache()
        return c.get(f"{cam['vid']}:{cam['pid']}:{cam.get('bcd_device')}") or next(
            (v for k, v in c.items() if k.startswith(f"{cam['vid']}:{cam['pid']}:")), None)

    def entities_file(self, cam: dict) -> str | None:
        d = self.cam_desc(cam)
        if not d or not d.get("entities"):
            return None
        p = self.cache_path(f"entities_{cam['vid']}_{cam['pid']}_{cam.get('bcd_device')}.json")
        if p is None:
            return None
        results.write_json(p, {"entities": d["entities"]})
        return str(p)

    def mode_alt_cache(self):
        from common import topology_model
        p = self.cache_path("mode_alt_cache.json")
        return topology_model.ModeAltCache.load(p) if p is not None else topology_model.ModeAltCache()

    # ---------------------------------------------------------------- camera helpers
    def cameras_brief(self, cams: list[dict] | None = None) -> list[dict]:
        keep = ("key", "name", "vid", "pid", "serial", "is_kiyo", "unique_id", "location_hex", "port_path",
                "stable_port_path", "bcd_device", "speed", "avf_name", "model_id")
        return [{k: c.get(k) for k in keep} for c in (self.cameras if cams is None else cams)]

    def openable(self) -> list[dict]:
        """USB cameras that AVFoundation lists (only those can be opened). Never filters by model: the Kiyo is in."""
        return [c for c in self.cameras if c.get("unique_id")]

    def new_result(self, test: str, cams: list[dict] | None = None) -> dict:
        res = results.new_result(test, "macos", self.command, self.cameras_brief(cams))
        res["suite"] = {"reduced": self.reduced, "quick": bool(getattr(self.args, "quick", False)),
                        "ep0": self.ep0_enabled, "ep0_backend": getattr(self.args, "ep0_backend", None),
                        "tcc_video": self.tcc}
        return res


# ------------------------------------------------------------------------------------------------ mode helpers
def formats_of(cam: dict) -> list[dict]:
    return list(cam.get("avf_formats") or [])


def max_fps(fmt: dict) -> float | None:
    rs = fmt.get("ranges") or []
    return max((r["max_fps"] for r in rs), default=None)


def rates_of(fmt: dict) -> list[float]:
    """Distinct frame rates a format offers (both ends of each range)."""
    out = set()
    for r in fmt.get("ranges") or []:
        out.add(round(r["max_fps"], 3))
        out.add(round(r["min_fps"], 3))
    return sorted(out)


def mjpeg_formats(cam: dict) -> list[dict]:
    return [f for f in formats_of(cam) if f.get("subtype") in JPEG_SUBTYPES]


def pick_default_mode(cam: dict, prefer: tuple[tuple[int, int], ...] = ((1280, 720), (640, 480)),
                      fps: float = 30.0) -> dict | None:
    """The mode a test uses when it needs 'the camera's default mode': MJPEG at a preferred size and ~30 fps, else
    any subtype at a preferred size, else the largest format at <= 30 fps. Returns {format_index, fps, subtype,
    w, h, mode_text}."""
    fmts = formats_of(cam)
    if not fmts:
        return None

    def ok_rate(f):
        return any(r["min_fps"] - 0.01 <= fps <= r["max_fps"] + 0.01 for r in f.get("ranges") or [])

    for group in (mjpeg_formats(cam), fmts):
        for size in prefer:
            for f in group:
                if (f["w"], f["h"]) == size and ok_rate(f):
                    return _mode(f, fps)
    cands = [f for f in fmts if ok_rate(f)] or fmts
    f = max(cands, key=lambda f: (f["w"] * f["h"], f.get("subtype") in JPEG_SUBTYPES))
    return _mode(f, fps if ok_rate(f) else max_fps(f))


def pick_small_mode(cam: dict, fps: float = 30.0) -> dict | None:
    """Smallest MJPEG (else any) format that runs at fps: the 'predicted fits' mode of MULTI."""
    group = mjpeg_formats(cam) or formats_of(cam)
    cands = [f for f in group if any(r["min_fps"] - 0.01 <= fps <= r["max_fps"] + 0.01 for r in f.get("ranges") or [])]
    if not cands:
        return None
    f = min(cands, key=lambda f: f["w"] * f["h"])
    return _mode(f, fps)


def pick_large_mode(cam: dict, fps: float = 30.0) -> dict | None:
    """Largest MJPEG (else any) format that runs at fps: the 'predicted refused' mode of MULTI (the largest frame
    needs the largest alt; macOS is reported to pick the largest alt anyway)."""
    group = mjpeg_formats(cam) or formats_of(cam)
    cands = [f for f in group if any(r["min_fps"] - 0.01 <= fps <= r["max_fps"] + 0.01 for r in f.get("ranges") or [])]
    if not cands:
        return None
    f = max(cands, key=lambda f: f["w"] * f["h"])
    return _mode(f, fps)


# ------------------------------------------------------------------------------------------------ mode scope
# Plan section 6 'Mode scope': streaming tests use only modes with exactly 720 lines at >= 30 fps (Dom 2026-11-08;
# runner flags --min-fps, --min-height, --max-height (0 = no upper bound), --all-modes). The decision is mac_modescope (common/modescope.py when present). With --all-modes the
# pickers below fall back to the pre-scope choices (pick_default_mode etc.), so a full-mode run is unchanged.
DEFAULT_TARGET = (1280, 720, 30.0)


def scoped_mjpeg_formats(cam: dict) -> tuple[list[dict], str]:
    """The formats a streaming test treats as the camera's MJPEG modes, and why: the JPEG-subtype formats; when
    AVFoundation lists none, the formats at the descriptor's MJPEG sizes (one report saw MJPEG offered only
    decoded as 420v); else none."""
    mj = mjpeg_formats(cam)
    if mj:
        return mj, "JPEG subtypes listed by AVFoundation"
    desc_sizes = {(f["w"], f["h"]) for f in ((cam.get("uvc") or {}).get("frames") or []) if f.get("format") == "MJPEG"}
    if desc_sizes:
        fm = [f for f in formats_of(cam) if (f["w"], f["h"]) in desc_sizes]
        if fm:
            return fm, "no JPEG subtype listed: formats at the descriptor's MJPEG sizes"
    return [], "no JPEG subtype listed and no descriptor MJPEG sizes"


def scoped_mjpeg_modes(cam: dict, args: Any) -> list[dict]:
    """Every in-scope (MJPEG format, rate) pair as a mode dict, cheapest first (pixels, then fps)."""
    import mac_modescope as ms
    fmts, _ = scoped_mjpeg_formats(cam)
    out = []
    for f in fmts:
        for r in ms.scoped_rates(f, args):
            out.append(_mode(f, float(r)))
    out.sort(key=lambda m: (m["w"] * m["h"], m["fps"] or 0, m["format_index"]))
    return out


def camera_scope(cam: dict, args: Any) -> dict:
    """Scope record for one camera (common.modescope.record layout): advertised modes (every AVFoundation format x
    rate) vs in scope, plus the MJPEG subset the streaming tests draw from."""
    import mac_modescope as ms
    rec = ms.record_for_formats(args, formats_of(cam))
    mj, why = scoped_mjpeg_formats(cam)
    sub = ms.record_for_formats(args, mj)
    rec["mjpeg"] = {"selection": why, "n_advertised": sub["advertised"], "n_in_scope": sub["in_scope"],
                    "n_excluded": sub["excluded"], "in_scope_modes": sub.get("in_scope_modes")}
    return rec


def scope_for_test(cams: list[dict], args: Any) -> dict:
    """Test-level scope record (sums over cameras) with the per-camera records."""
    import mac_modescope as ms
    per = {c["key"]: camera_scope(c, args) for c in cams}
    tot = sum(p["n_advertised"] for p in per.values())
    kept = sum(p["n_in_scope"] for p in per.values())
    rec = ms.scope_record(args, tot, kept)
    rec["per_camera"] = per
    return rec


def _near(m: dict, target: tuple[int, int, float]) -> tuple:
    import math
    tw, th, tf = target
    px = max(1, m["w"] * m["h"])
    return (round(abs(math.log2(px / (tw * th))), 3), abs((m["fps"] or 0) - tf), m["format_index"])


def pick_scoped_default(cam: dict, args: Any, target: tuple[int, int, float] = DEFAULT_TARGET) -> tuple[dict | None, dict]:
    """The streaming tests' default mode under the scope: MJPEG 1280x720@30, else the nearest in-scope MJPEG mode
    (size first, then rate). Returns (mode | None, info). None means 'untested (scope)': no in-scope MJPEG mode.
    With --all-modes: pick_default_mode (the pre-scope choice)."""
    import mac_modescope as ms
    if ms.params(args)["all_modes"]:
        m = pick_default_mode(cam)
        return m, {"why": "--all-modes: pre-scope default (MJPEG 1280x720/640x480 @30, else largest)",
                   "scope": ms.text(args)}
    cands = scoped_mjpeg_modes(cam, args)
    _, sel = scoped_mjpeg_formats(cam)
    if not cands:
        return None, {"why": f"no in-scope MJPEG mode ({sel})", "untested": "scope", "scope": ms.text(args)}
    exact = [m for m in cands if (m["w"], m["h"]) == target[:2] and abs((m["fps"] or 0) - target[2]) < 0.05]
    m = exact[0] if exact else min(cands, key=lambda c: _near(c, target))
    return m, {"why": (("MJPEG %dx%d@%g" % target) + f" ({sel})") if exact else
               f"nearest in-scope MJPEG mode to {target[0]}x{target[1]}@{target[2]:g} ({sel})", "scope": ms.text(args)}


def pick_scoped_alt(cam: dict, args: Any, default: dict) -> tuple[dict | None, str]:
    """The second mode of M-CYC's mode-switch variant: another in-scope mode. Preference: 1920x1080@30 when the
    default is 1280x720@30 (and the reverse), then the default size at 60 fps, then the nearest other in-scope
    mode. With --all-modes: pick_small_mode (pre-scope behaviour). Returns (mode | None, why)."""
    import mac_modescope as ms
    if ms.params(args)["all_modes"]:
        s = pick_small_mode(cam)
        if s and s["format_index"] != default.get("format_index"):
            return s, "--all-modes: smallest MJPEG mode (pre-scope)"
        return None, "--all-modes: no smaller mode"
    cands = [m for m in scoped_mjpeg_modes(cam, args)
             if (m["format_index"], m["fps"]) != (default.get("format_index"), default.get("fps"))]
    if not cands:
        return None, "no second in-scope mode (mode switch not testable under mode scope)"
    size = (default["w"], default["h"])
    other = {(1280, 720): (1920, 1080), (1920, 1080): (1280, 720)}.get(size)
    for m in cands:
        if other and (m["w"], m["h"]) == other and abs((m["fps"] or 0) - (default.get("fps") or 0)) < 0.05:
            return m, f"other standard size at the same rate ({m['mode_text']})"
    for m in cands:
        if (m["w"], m["h"]) == size and (m["fps"] or 0) >= 59.9:
            return m, f"same size at 60 fps ({m['mode_text']})"
    m = min(cands, key=lambda c: _near(c, (default["w"], default["h"], default.get("fps") or 30.0)))
    return m, f"nearest other in-scope mode ({m['mode_text']})"


def _mode(f: dict, fps: float | None) -> dict:
    fmt = "MJPG" if f.get("subtype") in JPEG_SUBTYPES else str(f.get("subtype"))
    return {"format_index": f["index"], "fps": fps, "subtype": f.get("subtype"), "w": f["w"], "h": f["h"],
            "mode_text": f"{fmt} {f['w']}x{f['h']}@{fps:g}" if fps else f"{fmt} {f['w']}x{f['h']}"}


def avf_mode_args(mode: dict) -> list[str]:
    out = ["--format-index", str(mode["format_index"])]
    if mode.get("fps"):
        out += ["--fps", f"{mode['fps']:g}"]
    return out


def child_failure(res: dict) -> dict:
    """Normalise a helper result into {ok, error_class, code, stage, error} for classification."""
    j = res.get("json") or {}
    if res.get("timed_out") or j.get("timed_out"):
        return {"ok": False, "error_class": "timeout", "code": "timeout", "stage": j.get("in_progress"),
                "error": j.get("error") or "child timed out"}
    if j.get("ok"):
        return {"ok": True}
    code = None
    for e in (j.get("runtime_errors") or []):
        err = e.get("error") or {}
        if err.get("iokit_codes"):
            code = err["iokit_codes"][0]
            break
        if err.get("code") is not None:
            code = err["code"]
    err = j.get("error")
    if code is None and isinstance(err, dict):
        code = err.get("code")
    return {"ok": False, "error_class": j.get("error_class") or ("crash" if res.get("rc") not in (0, 4, 3, 5) else "other"),
            "code": code, "stage": j.get("stage_failed"), "error": err, "rc": res.get("rc")}
