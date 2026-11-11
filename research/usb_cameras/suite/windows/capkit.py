"""Shared capture helpers for the Windows capture tests (W-MJPEG, W-CYC, W-MULTI, W-TS, W-CTRL-EFFECT, W-KIYO).

Stdlib plus suite/common. Every camera command goes through ``ctx.camcmd`` (camlock + timeout on the child).
Nothing here hard-codes a camera: modes come from ``wincam formats`` read at run time, controls from
``wincam controls --read-only``, devices from the ctx camera dicts (mf_symlink / ds_path).

Mode selection rules (documented here because several tests rely on them):
- ``default_mode``: MJPG 1280x720@30 if advertised, else the MJPG mode nearest to 1280x720 (by pixel count) at the
  rate nearest 30 fps. This is skellycam's usual mode.
- ``alt_mode``: the mode-switch partner: MJPG 640x480@30 if advertised, else the nearest smaller size at ~30 fps.
- ``quick_modes``: smallest size, the default mode and the largest size (each at its highest rate).

Mode scope (Dom, 2026-11-06 / 2026-11-08): streaming tests pass the advertised modes through ``scoped(ctx, modes)``
/ ``scoped_default(ctx, modes)`` first (common/modescope.py: exactly 720 lines at >= 30 fps unless --all-modes /
--min-fps / --min-height / --max-height), so ``default_mode`` lands on 1280x720@30 and ``switch_mode`` on another
in-scope mode (960x720@30, or 720p60). A camera without an in-scope MJPEG mode is recorded and rated
``scope_untested``.

DirectShow engines (``pyav_capture(..., engine=)``): ``pyav`` is PyAV as-is (it silently gets YUY2/NV12 where the
camera offers a raw format at the requested size and rate, e.g. the Kiyo at every mode); ``ffmpeg`` is the ffmpeg CLI
with ``-vcodec mjpeg`` (MJPEG guaranteed; rows carry no QPC, ``pts_ns`` is the wall clock at demux).

Plan mode (``ctx.dry_run``): ``get_formats`` never runs a camera command; it reads the newest cached MF format list
of the same camera (same slug, else same VID:PID) from earlier runs' raw folders, so estimates stay honest.
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

WIN_DIR = Path(__file__).resolve().parent
SUITE_DIR = WIN_DIR.parent
for _p in (str(SUITE_DIR), str(WIN_DIR), str(WIN_DIR / "helpers")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from common import jpegcheck, modescope, procutil, rating, results, topology_model  # noqa: E402

import suitectx  # noqa: E402

PYAV_DS = WIN_DIR / "helpers" / "pyav_ds.py"
OPENCV_DS = WIN_DIR / "helpers" / "opencv_ds.py"
MULTI_LAUNCH = WIN_DIR / "helpers" / "multi_launch.py"


# ============================================================================================================ modes
@dataclass(frozen=True)
class Mode:
    w: int
    h: int
    fps_num: int
    fps_den: int
    subtype: str = "MJPG"

    @property
    def fps(self) -> float:
        return self.fps_num / self.fps_den if self.fps_den else float(self.fps_num)

    @property
    def fps_arg(self) -> str:
        """--fps for wincam (nearest rate within 0.5 fps wins)."""
        return f"{self.fps:.6g}"

    @property
    def ds_fps(self) -> str:
        """FFmpeg framerate string (exact rational)."""
        return f"{self.fps_num}/{self.fps_den}" if self.fps_den != 1 else str(self.fps_num)

    @property
    def text(self) -> str:
        return f"{self.subtype} {self.w}x{self.h}@{self.fps:.4g}"

    @property
    def slug(self) -> str:
        return f"{self.w}x{self.h}_{self.fps:.4g}".replace(".", "p")

    def as_dict(self) -> dict:
        return {"subtype": self.subtype, "width": self.w, "height": self.h, "fps_num": self.fps_num,
                "fps_den": self.fps_den, "fps": round(self.fps, 4), "text": self.text}


def mjpeg_modes(formats_mf: dict | None) -> list[Mode]:
    """Every MJPG native type of the capture stream (the first stream with MJPG types), de-duplicated."""
    if not formats_mf:
        return []
    streams = formats_mf.get("reader_streams") or []
    best = None
    for s in streams:
        types = [t for t in s.get("types", []) if str(t.get("subtype", "")).upper() == "MJPG"]
        if types:
            best = types
            break
    seen, out = set(), []
    for t in best or []:
        try:
            m = Mode(int(t["width"]), int(t["height"]), int(t["fps_num"]), int(t["fps_den"]))
        except (KeyError, TypeError, ValueError):
            continue
        if (m.w, m.h, m.fps_num, m.fps_den) in seen:
            continue
        seen.add((m.w, m.h, m.fps_num, m.fps_den))
        out.append(m)
    out.sort(key=lambda m: (m.w * m.h, m.w, m.fps))
    return out


def _nearest(modes: list[Mode], w: int, h: int, fps: float, smaller_than: Mode | None = None) -> Mode | None:
    cand = modes
    if smaller_than is not None:
        cand = [m for m in modes if m.w * m.h < smaller_than.w * smaller_than.h] or \
            [m for m in modes if (m.w, m.h) != (smaller_than.w, smaller_than.h)]
    if not cand:
        return None
    exact = [m for m in cand if m.w == w and m.h == h]
    if exact:
        return min(exact, key=lambda m: abs(m.fps - fps))
    px = w * h
    size_best = min(cand, key=lambda m: (abs(math.log((m.w * m.h) / px)), abs(m.fps - fps)))
    same = [m for m in cand if (m.w, m.h) == (size_best.w, size_best.h)]
    return min(same, key=lambda m: abs(m.fps - fps))


def default_mode(modes: list[Mode]) -> Mode | None:
    return _nearest(modes, 1280, 720, 30.0)


def alt_mode(modes: list[Mode], default: Mode | None) -> Mode | None:
    if not modes:
        return None
    m = _nearest(modes, 640, 480, 30.0, smaller_than=default)
    return m if m != default else None


def max_rate_per_size(modes: list[Mode]) -> list[Mode]:
    best: dict[tuple, Mode] = {}
    for m in modes:
        k = (m.w, m.h)
        if k not in best or m.fps > best[k].fps:
            best[k] = m
    return sorted(best.values(), key=lambda m: (m.w * m.h, m.w))


def quick_modes(modes: list[Mode]) -> list[Mode]:
    per = max_rate_per_size(modes)
    if not per:
        return []
    picks = [per[0], default_mode(modes), per[-1]]
    out = []
    for m in picks:
        if m is not None and m not in out:
            out.append(m)
    return out


#: modes below this rate run LAST in a sweep (the Kiyo's first stream of the 20261106 run was 640x360@5 and it
#: wedged there; cyc_kiyo.md B10)
LOW_FPS = 15.0


def sweep_order(modes: list[Mode], default: Mode | None = None, low_fps: float = LOW_FPS) -> list[Mode]:
    """Order for a full mode sweep, for every camera: the default mode first (skellycam's mode, and the first
    stream a freshly plugged camera sees), then every mode at >= ``low_fps`` (size, then rate), then the low-rate
    modes (size, then rate)."""
    if default is None:
        default = default_mode(modes)
    rest = [m for m in modes if m != default]
    hi = sorted((m for m in rest if m.fps >= low_fps), key=lambda m: (m.w * m.h, m.w, m.fps))
    lo = sorted((m for m in rest if m.fps < low_fps), key=lambda m: (m.w * m.h, m.w, m.fps))
    return ([default] if default is not None and default in modes else []) + hi + lo


def mode_scope(ctx) -> "modescope.Scope":
    """The streaming mode scope of this run (--min-fps / --min-height / --all-modes; default >= 30 fps, >= 720)."""
    return modescope.from_args(getattr(ctx, "args", None))


def scoped(ctx, modes: list[Mode]) -> tuple[list[Mode], dict]:
    """(in-scope modes, scope record) for a streaming test. The record (``mode_scope`` in each test's per-camera
    measurements) carries the scope, the advertised / in-scope / excluded counts and the excluded modes."""
    sc = mode_scope(ctx)
    kept, _excl = modescope.split(modes, sc)
    return kept, modescope.record(sc, modes, kept)


def scoped_default(ctx, modes: list[Mode]) -> tuple[Mode | None, dict]:
    """The default streaming mode within the scope: MJPG 1280x720@30, else the nearest in-scope MJPEG mode; None
    when the camera has no in-scope MJPEG mode (record it and rate 'untested (scope)')."""
    kept, rec = scoped(ctx, modes)
    d = default_mode(kept) if kept else None
    rec["default_mode"] = d.text if d else None
    if d is None:
        rec["untested_reason"] = modescope.no_scope_mode_reason(mode_scope(ctx), len(modes))
    return d, rec


def switch_mode(modes: list[Mode], default: Mode | None) -> Mode | None:
    """Mode-switch / pair partner within the in-scope modes: the largest other size at ~30 fps (1920x1080@30 vs
    1280x720@30), else the default's size at another rate (720p60), else None."""
    return modescope.partner(modes, default)


def scope_untested(ctx, rec: dict, extra: dict | None = None) -> dict:
    """'untested (scope)' verdict for a camera without an in-scope MJPEG mode."""
    why = rec.get("untested_reason") or modescope.no_scope_mode_reason(mode_scope(ctx), rec.get("advertised", 0))
    r = {"rating": "untested", "criteria": [{"criterion": "measured", "met": None, "detail": why}],
         "evidence": {"mode_scope": rec, "scope_excluded": True, **(extra or {})}, "note": why,
         "summary_label": "untested (scope)"}
    return r


def format_read_failure(fm: dict | None, run: dict | None = None) -> str | None:
    """Why the camera's MF format list could not be read, or None when it was read (it has reader streams). A camera
    whose list failed is not 'out of scope': a hanging Kiyo is a recorded result, never a scope exclusion."""
    if isinstance(fm, dict) and fm.get("reader_streams"):
        return None
    run = run or {}
    err = (fm or {}).get("error") if isinstance((fm or {}).get("error"), dict) else {}
    if err:
        hr = f" {err['hr']}" if err.get("hr") else ""
        return f"format list failed: {err.get('class') or 'error'} at stage {err.get('stage') or '?'}{hr}"
    if run.get("timed_out"):
        return "format list failed: wincam formats killed at its timeout"
    if run.get("error"):
        return f"format list failed: {run['error']}"
    if fm is None:
        return f"format list failed: no JSON from wincam formats (rc {run.get('rc')})"
    return "format list failed: no reader streams"


def formats_checked(ctx, cam: dict, cache: dict | None, test: str) -> tuple[dict | None, dict | None]:
    """(format JSON, None) when the camera's MF format list was read or lists an MJPEG mode; else (format JSON,
    failure record) when the read failed. On a failed read the camera is health-probed once (ctx.health_probe, as
    W-CYC does: the probe re-reads the list and streams one in-scope frame when it can), so a hang or 0x8007001F
    becomes a suite device fault (``fault`` in the record); when the probe succeeds the re-read list is used."""
    fm, run = get_formats(ctx, cam, cache)
    if mjpeg_modes(fm):
        return fm, None
    why = format_read_failure(fm, run)
    if why is None:
        return fm, None
    rec: dict = {"untested_reason": why, "formats_run": run, "formats_error": (fm or {}).get("error")}
    hp = getattr(ctx, "health_probe", None)
    if callable(hp) and not getattr(ctx, "dry_run", False):
        try:
            pr = hp(cam, test=test, mode=None, reason=f"{test} probe (format list failed)") or {}
        except Exception as e:  # noqa: BLE001
            pr = {"ok": None, "error": repr(e)}
        rec["probe"] = {k: pr.get(k) for k in ("ok", "utc", "code", "stage", "class", "fault_like", "skipped",
                                               "mode", "elapsed_s", "error")}
        if pr.get("ok"):
            fm2, run2 = get_formats(ctx, cam, cache)       # the probe's re-read cached the list
            if format_read_failure(fm2, run2) is None:
                return fm2, None
    rec["fault"] = device_fault(ctx, cam)
    return fm, rec


def format_failed_untested(rec: dict) -> dict:
    """Verdict for a camera whose format list could not be read: 'untested (device fault)' when the camera is faulted
    (the probe or the read itself found it), else 'untested (format read failed)'."""
    if rec.get("fault"):
        return rating.device_fault_untested(rec["fault"], evidence={"format_read": rec})
    v = rating.untested(rec.get("untested_reason") or "format list failed", {"format_read": rec})
    v["note"] = rec.get("untested_reason")
    v["summary_label"] = "untested (format read failed)"
    return v


def lowest_rate_largest(modes: list[Mode]) -> Mode | None:
    if not modes:
        return None
    big = max(m.w * m.h for m in modes)
    return min((m for m in modes if m.w * m.h == big), key=lambda m: m.fps)


# ============================================================================================================ naming
def cam_slug(cam: dict) -> str:
    nm = re.sub(r"[^a-z0-9]+", "", str(cam.get("name") or "cam").lower())[:14] or "cam"
    tail = re.sub(r"[^A-Za-z0-9]+", "", str(cam.get("serial") or cam.get("hub_port") or ""))[-8:]
    return f"{nm}_{cam.get('vid')}-{cam.get('pid')}" + (f"_{tail}" if tail else "")


def cam_label(cam: dict) -> str:
    return f"{cam.get('name')} ({cam.get('vid')}:{cam.get('pid')})"


# ============================================================================================================ commands
def parse_json(r: dict) -> dict | None:
    obj, _err = suitectx.parse_json_stdout(r)
    return obj


def run_brief(r: dict) -> dict:
    """Small record of a camcmd/procutil result for the result JSON."""
    return {k: r.get(k) for k in ("rc", "elapsed_s", "timed_out", "killed", "lock_wait_s", "lock_timed_out",
                                  "camlock_rc", "spawn_error")} | \
        {"stderr_tail": (r.get("stderr") or "")[-600:]}


def helper_argv(ctx, script: Path, *args: Any) -> list[str]:
    return ["uv", "run", "--python", getattr(ctx, "python", "3.12"), "--script", str(script), *map(str, args)]


def wincam_argv(ctx, *args: Any) -> list[str]:
    return [str(ctx.wincam), *map(str, args)]


def get_formats(ctx, cam: dict, cache: dict | None = None) -> tuple[dict | None, dict]:
    """``wincam formats --api mf`` for one camera (one camcmd; cached per run in <raw_dir>/_cache)."""
    # rebuildable per-run cache: kept in raw_dir (outside the repo), not in the results folder (W-FMT already keeps
    # the format lists as results; review 2026-11-06)
    cdir = Path(ctx.raw_dir) / "_cache"
    f = cdir / f"formats_mf_{cam_slug(cam)}.json"
    if cache is not None and cam["key"] in cache:
        return cache[cam["key"]], {"cached": True}
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if cache is not None:
                cache[cam["key"]] = d
            return d, {"cached_file": str(f)}
        except ValueError:
            pass
    if getattr(ctx, "dry_run", False):
        d, src = cached_formats_from_earlier_runs(ctx, cam)
        if d is not None and cache is not None:
            cache[cam["key"]] = d
        return d, {"dry_run": True, "source": src}
    if not cam.get("mf_symlink"):
        return None, {"error": "camera has no MF symlink"}
    r = ctx.camcmd(wincam_argv(ctx, "formats", "--api", "mf", "--device", cam["mf_symlink"], "--timeout-ms", 8000),
                   timeout_s=45)
    d = parse_json(r)
    if d is not None and d.get("reader_streams"):
        results.write_json(f, d)
        if cache is not None:
            cache[cam["key"]] = d
    return d, run_brief(r)


def cached_formats_from_earlier_runs(ctx, cam: dict) -> tuple[dict | None, str | None]:
    """(format JSON, source path) of the newest cached ``formats_mf_*`` file for this camera in any run folder of
    this host's raw folder (``ctx.plan_raw_root``, default raw_root()/results/windows/<host>; same slug first, else
    same VID:PID: a serial-less camera's slug changes with its port). Reads files only; used by plan mode."""
    root = getattr(ctx, "plan_raw_root", None)
    root = Path(root) if root else results.default_raw_dir(results.default_results_dir("x")).parent
    pats = [f"formats_mf_{cam_slug(cam)}.json", f"formats_mf_*_{cam.get('vid')}-{cam.get('pid')}*.json"]
    for pat in pats:
        try:
            hits = sorted(root.rglob(f"_cache/{pat}"), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            hits = []
        for p in hits:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if d.get("reader_streams"):
                return d, str(p)
    return None, None


def norm_link(s: str | None) -> str:
    """wincam's match key: lower case, no ``\\\\?\\`` prefix, no ``#{interface class guid}`` segment (MF symlink and DS
    DevicePath of one interface give the same key)."""
    t = str(s or "").lower()
    if t.startswith("\\\\?\\"):
        t = t[4:]
    return re.sub(r"#\{[^}]*\}", "", t)


def wincam_activity(ctx, wait_ms: int = 1500, timeout_s: float = 25.0) -> dict:
    """``wincam activity``: which processes use each camera (IMFSensorActivityMonitor + the privacy ConsentStore).
    Opens NO camera, so it runs without the camera lock (it must see other processes while a test holds the lock).
    Returns a compact record; never raises."""
    argv = [str(ctx.wincam), "activity", "--wait-ms", int(wait_ms)]
    try:
        runner = getattr(ctx, "run", None)
        r = runner(argv, timeout_s) if callable(runner) else procutil.run([str(a) for a in argv], timeout_s=timeout_s)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": repr(e), "utc": results.utc_now_iso()}
    obj = parse_json(r) if isinstance(r, dict) else None
    if not isinstance(obj, dict) or obj.get("subcommand") != "activity":
        return {"ok": False, "error": (obj or {}).get("error") if isinstance(obj, dict) else "no JSON",
                "utc": results.utc_now_iso(), "run": run_brief(r) if isinstance(r, dict) else None}
    devs = []
    for d in obj.get("devices") or []:
        devs.append({"friendly_name": d.get("friendly_name"), "match_key": d.get("match_key") or norm_link(d.get("symlink")),
                     "in_use": d.get("in_use"), "streaming": d.get("streaming"),
                     "processes": [{k: p.get(k) for k in ("pid", "name", "streaming", "self")}
                                   for p in d.get("processes") or []]})
    return {"ok": True, "utc": obj.get("utc_started"), "monitor": obj.get("monitor"), "devices": devs,
            "consent_in_use": ((obj.get("consent_store") or {}).get("in_use")),
            "camera_opened": False, "coverage_note": obj.get("coverage_note")}


def activity_entry(doc: dict | None, cam: dict) -> dict | None:
    keys = {norm_link(cam.get("mf_symlink")), norm_link(cam.get("ds_path"))} - {""}
    for d in (doc or {}).get("devices") or []:
        if d.get("match_key") in keys:
            return d
    return None


def activity_for_camera(ctx, cam: dict, doc: dict | None = None) -> dict:
    """One camera's activity (other processes holding / streaming it) for a result JSON."""
    doc = doc if doc is not None else wincam_activity(ctx)
    e = activity_entry(doc, cam)
    others = [p for p in (e or {}).get("processes") or [] if not p.get("self")]
    return {"utc": doc.get("utc"), "ok": doc.get("ok"), "error": doc.get("error"),
            "report_received": (doc.get("monitor") or {}).get("report_received"),
            "in_use": None if e is None else e.get("in_use"), "streaming_by_other": any(p.get("streaming") for p in others),
            "other_processes": others, "consent_in_use": doc.get("consent_in_use"),
            "source": "wincam activity (IMFSensorActivityMonitor: MF/Frame Server clients; ConsentStore: any app)"}


def get_controls(ctx, cam: dict, api: str = "mf", timeout_ms: int = 5000, timeout_s: float = 40) -> tuple[dict | None, dict]:
    dev = cam.get("mf_symlink") if api == "mf" else cam.get("ds_path")
    if not dev:
        return None, {"error": f"camera has no {api} device link"}
    r = ctx.camcmd(wincam_argv(ctx, "controls", "--api", api, "--device", dev, "--read-only", "--timeout-ms",
                               timeout_ms), timeout_s=timeout_s)
    return parse_json(r), run_brief(r)


def set_controls(ctx, cam: dict, api: str, sets: dict[str, Any], flags: str | None = None,
                 timeout_ms: int = 5000, timeout_s: float = 40) -> tuple[dict | None, dict]:
    dev = cam.get("mf_symlink") if api == "mf" else cam.get("ds_path")
    if not dev or not sets:
        return None, {"error": "no device or nothing to set"}
    spec = ",".join(f"{k}={v}" for k, v in sets.items())
    argv = ["controls", "--api", api, "--device", dev, "--set", spec, "--timeout-ms", timeout_ms]
    if flags:
        argv += ["--set-flags", flags]
    r = ctx.camcmd(wincam_argv(ctx, *argv), timeout_s=timeout_s)
    return parse_json(r), run_brief(r)


def control_table(controls_json: dict | None) -> dict[str, dict]:
    """{short name: control dict} for supported controls, e.g. 'exposure', 'white_balance', 'gain', 'focus'."""
    out = {}
    for c in (controls_json or {}).get("controls", []) or []:
        if c.get("supported"):
            out[c.get("name")] = c
    return out


def wincam_capture(ctx, cam: dict, mode: Mode, out_dir: Path, frames: int | None = None,
                   seconds: float | None = None, save: str = "none", timeout_ms: int = 5000,
                   extra: Iterable[Any] = (), timeout_s: float | None = None) -> tuple[dict | None, dict]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    argv = ["capture", "--api", "mf", "--device", cam["mf_symlink"], "--width", mode.w, "--height", mode.h,
            "--fps", mode.fps_arg, "--subtype", mode.subtype, "--timeout-ms", timeout_ms, "--out-dir", out_dir,
            "--save", save]
    argv += ["--frames", frames] if frames else ["--seconds", seconds or 3]
    argv += list(extra)
    if timeout_s is None:
        dur = (seconds or 0) + (frames or 0) / max(1.0, mode.fps)
        timeout_s = dur + 4 * timeout_ms / 1000.0 + 25
    r = ctx.camcmd(wincam_argv(ctx, *argv), timeout_s=timeout_s)
    d = parse_json(r)
    if d is None:
        p = out_dir / "summary.json"
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                d = None
    return d, run_brief(r)


def pyav_capture(ctx, cam: dict, mode: Mode, out_dir: Path, frames: int | None = None,
                 seconds: float | None = None, save: str = "none", timeout_ms: int = 5000,
                 extra: Iterable[Any] = (), timeout_s: float | None = None,
                 engine: str = "pyav") -> tuple[dict | None, dict]:
    """``pyav_ds capture``: ``engine`` 'pyav' (PyAV as-is) or 'ffmpeg' (the ffmpeg CLI with -vcodec mjpeg)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dev = cam.get("ds_path") or cam.get("ds_name")
    argv = ["capture", "--device", dev, "--width", mode.w, "--height", mode.h, "--fps", mode.ds_fps,
            "--timeout-ms", timeout_ms, "--out-dir", out_dir, "--save", save]
    argv += ["--frames", frames] if frames else ["--seconds", seconds or 3]
    extra = list(extra)
    if engine and engine != "pyav" and "--engine" not in [str(x) for x in extra]:
        argv += ["--engine", engine]
    argv += extra
    if timeout_s is None:
        dur = (seconds or 0) + (frames or 0) / max(1.0, mode.fps)
        timeout_s = dur + 4 * timeout_ms / 1000.0 + 40
    r = ctx.camcmd(helper_argv(ctx, PYAV_DS, *argv), timeout_s=timeout_s)
    d = parse_json(r)
    if d is None:
        p = out_dir / "summary.json"
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                d = None
    return d, run_brief(r)


def pyav_capture_argv(ctx, cam: dict, mode: Mode, out_dir: Path, seconds: float, save: str = "none",
                      timeout_ms: int = 5000, stop_file: Path | str | None = None) -> list[str]:
    """argv of a PyAV DirectShow capture; ``stop_file``: the capture ends cleanly as soon as that file exists
    (``seconds`` is then the upper bound)."""
    dev = cam.get("ds_path") or cam.get("ds_name")
    extra = ["--stop-file", str(stop_file)] if stop_file else []
    return helper_argv(ctx, PYAV_DS, "capture", "--device", dev, "--width", mode.w, "--height", mode.h, "--fps",
                       mode.ds_fps, "--timeout-ms", timeout_ms, "--out-dir", out_dir, "--save", save,
                       "--seconds", seconds, *extra)


def wincam_capture_argv(ctx, cam: dict, mode: Mode, out_dir: Path, seconds: float, save: str = "none",
                        timeout_ms: int = 5000, extra: Iterable[Any] = ()) -> list[str]:
    return wincam_argv(ctx, "capture", "--api", "mf", "--device", cam["mf_symlink"], "--width", mode.w,
                       "--height", mode.h, "--fps", mode.fps_arg, "--subtype", mode.subtype, "--timeout-ms",
                       timeout_ms, "--out-dir", out_dir, "--save", save, "--seconds", seconds, *extra)


def multi_launch(ctx, spec: dict, spec_path: Path, timeout_s: float) -> tuple[dict | None, dict]:
    """Run helpers/multi_launch.py under ONE camera lock. spec: see multi_launch.py."""
    results.write_json(spec_path, spec)
    r = ctx.camcmd([sys.executable, str(MULTI_LAUNCH), str(spec_path)], timeout_s=timeout_s)
    return parse_json(r), run_brief(r)


# ============================================================================================================ frames
def load_frames(out_dir: Path) -> list[dict]:
    return results.read_jsonl(Path(out_dir) / "frames.jsonl")


def spread_pick(items: list, limit: int | None) -> list:
    """``limit`` items evenly spaced over the whole list (first and last included), in order; all if fewer."""
    n = len(items)
    if not limit or n <= limit:
        return list(items)
    if limit == 1:
        return [items[0]]
    idx = sorted({round(i * (n - 1) / (limit - 1)) for i in range(limit)})
    return [items[i] for i in idx]


def saved_frame_bytes(out_dir: Path, rows: list[dict], limit: int | None = None,
                      spread: bool = False) -> list[tuple[dict, bytes]]:
    """(row, bytes) of the saved frames. ``spread``: pick ``limit`` frames evenly across ALL saved frames instead of
    the first ``limit`` (mjpeg_fmt.md H6: the first 8 saved frames covered only the first ~0.5 s when the camera ran
    faster than nominal, so the decode fractions were biased to start-up)."""
    p = Path(out_dir) / "frames.mjpeg"
    out = []
    if not p.exists():
        return out
    saved = [r for r in rows if r.get("mjpeg_offset") is not None and r.get("mjpeg_len")]
    pick = spread_pick(saved, limit) if spread else (saved[:limit] if limit else saved)
    with p.open("rb") as f:
        for r in pick:
            f.seek(int(r["mjpeg_offset"]))
            out.append((r, f.read(int(r["mjpeg_len"]))))
    return out


def check_saved(out_dir: Path, rows: list[dict], w: int, h: int, limit: int = 30, spread: bool = True) -> dict:
    """common.jpegcheck on ``limit`` saved frames (spread across the capture by default) + per-frame flags from
    frames.jsonl for all frames."""
    frames = saved_frame_bytes(out_dir, rows, limit, spread=spread)
    checks = [jpegcheck.check_jpeg(b) for _, b in frames]
    summ = jpegcheck.summarize_checks(checks, w, h) if checks else {"n": 0}
    n = len(rows)
    all_soi = sum(1 for r in rows if r.get("soi"))
    all_eoi = sum(1 for r in rows if r.get("eoi") or (isinstance(r.get("eoi_trailing_bytes"), int)
                                                      and r["eoi_trailing_bytes"] >= 0))
    all_sof = sum(1 for r in rows if r.get("sof0_w") == w and r.get("sof0_h") == h)
    hdr = {}
    for c in checks:
        if c.get("header_sha1"):
            hdr[c["header_sha1"]] = hdr.get(c["header_sha1"], 0) + 1
    strict_fail_reasons = {}
    for c in checks:
        if c.get("strict_ok") is False:
            k = "extraneous_bytes_before_eoi" if c.get("extra_bytes_before_eoi") else (c.get("strict_error") or "?")[:80]
            strict_fail_reasons[k] = strict_fail_reasons.get(k, 0) + 1
    return {"frames_total": n, "soi_fraction_all": (all_soi / n) if n else None,
            "eoi_fraction_all": (all_eoi / n) if n else None, "sof_match_fraction_all": (all_sof / n) if n else None,
            "checked": len(checks), "check_summary": summ, "header_sha1": max(hdr, key=hdr.get) if hdr else None,
            "header_sha1_distinct": len(hdr), "strict_fail_reasons": strict_fail_reasons,
            "checked_seq": [r.get("seq") for r, _ in frames],
            "saved_total": sum(1 for r in rows if r.get("mjpeg_offset") is not None and r.get("mjpeg_len")),
            "first_saved": frames[0][1] if frames else None}


def fps_from_rows(rows: list[dict], key: str = "qpc_ns", skip_frac: float = 0.15) -> float | None:
    """Steady fps: least-squares slope of time vs frame number (``seq``, so a dropped frame does not shorten the
    period) after skipping the first ``skip_frac`` of frames (start-up bursts). A fit, not first-to-last, because
    arrival times sit on a 16 ms host grid on Windows and short captures would otherwise be off by a few %."""
    pts = [(r.get("seq", i), r[key]) for i, r in enumerate(rows) if isinstance(r.get(key), (int, float))]
    if len(pts) < 5:
        return None
    pts = pts[int(len(pts) * skip_frac):]
    if len(pts) < 3:
        return None
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    if sxx <= 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in pts) / sxx   # ns per frame
    return 1e9 / slope if slope > 0 else None


def fps_tail(rows: list[dict], key: str = "qpc_ns", tail_s: float = 1.5) -> float | None:
    """Steady fps over the frames of the last ``tail_s`` seconds of the capture (H5: the C930e switched rate about
    2 s into a 3 s capture, so the full fit mixed two rates). Same least-squares fit as fps_from_rows, no skip."""
    pts = [r for r in rows if isinstance(r.get(key), (int, float))]
    if len(pts) < 5:
        return None
    t_end = pts[-1][key]
    tail = [r for r in pts if t_end - r[key] <= tail_s * 1e9]
    return fps_from_rows(tail, key=key, skip_frac=0.0) if len(tail) >= 5 else None


def fps_reference(fps_by_api: dict[str, float | None], nominal: float,
                  tol: float = 0.02) -> tuple[float, str, str | None]:
    """(reference fps, basis, note) for the G-MJPEG fps criterion, symmetric (mjpeg_fmt.md H1), tier 0 only (Dom
    2026-11-09: no device-clock rate). Same order as common.rating.fps_reference:

    - Both (all) measured APIs agree within ``tol`` of each other: their mean is the camera's real rate, whether
      it is below OR above nominal (the generic camera runs 25.7 at @25; the old rule accepted only below).
    - Otherwise nominal.
    Whether the camera honours the requested rate is a separate camera finding (``rate_honoured``)."""
    vals = [v for v in fps_by_api.values() if isinstance(v, (int, float)) and v > 0]
    if len(vals) >= 2 and (max(vals) - min(vals)) / max(vals) <= tol:
        ref = sum(vals) / len(vals)
        if abs(ref - nominal) / nominal > tol:
            return ref, "apis_agree", (f"both APIs deliver {ref:.2f} fps (nominal {nominal:.3g}); used as the "
                                       "camera's real rate")
        return ref, "apis_agree", None
    return nominal, "nominal", (f"APIs disagree ({', '.join(f'{v:.2f}' for v in vals)}); nominal used"
                                if len(vals) >= 2 else None)


def rate_honoured(fps_by_api: dict[str, float | None], nominal: float, tol: float = 0.02) -> dict:
    """Does the camera deliver the requested rate? A camera finding, not an API failure (verifier on H1: the C922
    streams MJPEG at 30 fps whatever lower rate is requested). ``honoured`` True/False when every measured API
    agrees on it, None when mixed or unmeasured."""
    by = {k: (abs(v - nominal) / nominal <= tol) for k, v in fps_by_api.items()
          if isinstance(v, (int, float)) and v > 0}
    vals = set(by.values())
    return {"honoured": (vals.pop() if len(vals) == 1 else None), "by_api": by, "nominal": nominal,
            "tolerance": tol}


# ============================================================================================================ errors
def failure_code(api: str, summary: dict | None, run: dict | None = None) -> tuple[Any, str | None, dict]:
    """(code for classify_failure, stage, raw error dict) from a wincam / pyav_ds / opencv_ds result."""
    err = (summary or {}).get("error") or {}
    stage = err.get("stage") or (summary or {}).get("stage_failed")
    if run and run.get("timed_out"):
        return "timeout", stage or "process", err
    if api == "mf":
        hr = err.get("hr")
        if err.get("class") == "timeout":
            return "timeout", stage, err
        return hr, stage, err
    eno = err.get("errno")
    if err.get("class") == "timeout":
        return "timeout", stage, err
    if eno is not None:
        return f"OSError({eno})", stage, err
    if summary and summary.get("format_fallback"):
        return None, "format", err
    return None, stage, err


def classify(api: str, code: Any, stage: str | None, frames: int | None = None, timed_out: bool = False,
             other_streaming_in_domain: bool | None = None, predicted_verdict: str | None = None,
             in_use_by_other: bool | None = None) -> dict:
    ctxd = {"api": {"mf": "mf", "ds": "pyav_ds", "opencv": "opencv"}.get(api, api), "stage": stage or "",
            "timed_out": timed_out, "frames": frames}
    if other_streaming_in_domain is not None:
        ctxd["other_streaming_in_domain"] = other_streaming_in_domain
    if predicted_verdict:
        ctxd["predicted_verdict"] = predicted_verdict
    if in_use_by_other is not None:
        ctxd["in_use_by_other"] = in_use_by_other
    try:
        return topology_model.classify_failure("windows", code, ctxd)
    except Exception as e:  # noqa: BLE001
        return {"class": "other", "reason": f"classify_failure raised {e!r}", "code": code}


# ============================================================================================================ faults
#: MF stages after streaming whose hang means the reader cannot be released (the Kiyo at 13:43:39: reader_release)
RELEASE_STAGES = {"flush", "reader_release", "control_interfaces_release", "source_shutdown",
                  "activate_shutdown_object", "close", "shutdown"}
DEVICE_ERROR_HR = "0x8007001F"


def fault_from_result(api: str, summary: dict | None, run: dict | None, cls: dict | None = None) -> dict | None:
    """A device fault that should stop all further work on the camera (task contract, dead-device gate), or None.

    Fault = ``device_error`` (HRESULT 0x8007001F ERROR_GEN_FAILURE, the Kiyo signature), or an unreleasable / hung
    reader: an MF release stage that timed out, a PyAV stage that never returned (``unreleasable``/``hung``), a
    wincam child with abandoned threads, or a child killed by the runner's timeout. A plain first-frame timeout or a
    bandwidth refusal is NOT a fault. Returns {kind, code, stage, reason}."""
    s = summary or {}
    err = s.get("error") or {}
    if s.get("gate_skipped") or s.get("device_fault") is True:
        return {"kind": "gated", "code": s.get("fault_code"), "stage": "gate",
                "reason": err.get("reason") or "skipped by the suite's device-fault gate"}
    hr = str(err.get("hr") or "").upper()
    code_hex = str((cls or {}).get("code_hex") or "").upper()
    if (cls or {}).get("class") == "device_error" or err.get("class") == "device_error" or \
            DEVICE_ERROR_HR.upper() in (hr, code_hex):
        return {"kind": "device_error", "code": DEVICE_ERROR_HR, "stage": err.get("stage") or s.get("stage_failed"),
                "reason": "ERROR_GEN_FAILURE: device attached but not functioning (needs a replug)"}
    stage = err.get("stage") or s.get("stage_failed")
    if api == "mf" and err.get("class") == "timeout" and stage in RELEASE_STAGES:
        return {"kind": "unreleasable", "code": "timeout", "stage": stage,
                "reason": f"MF {stage} did not return (reader cannot be released)"}
    if s.get("unreleasable") or s.get("hung"):
        return {"kind": "unreleasable", "code": "timeout", "stage": stage,
                "reason": f"{api} stage {stage!r} never returned (worker thread stuck)"}
    if isinstance(s.get("abandoned_threads"), int) and s["abandoned_threads"] > 0:
        return {"kind": "unreleasable", "code": "timeout", "stage": stage,
                "reason": f"wincam exited with {s['abandoned_threads']} abandoned thread(s) at stage {stage!r}"}
    if (run or {}).get("timed_out"):
        return {"kind": "hung_process", "code": "timeout", "stage": stage or "process",
                "reason": "camera command killed by the runner's timeout"}
    return None


def _fault_registry(ctx) -> dict:
    """Fallback registry (``ctx.device_faults``) for a ctx without suitectx's fault gate (unit tests, old ctx)."""
    reg = getattr(ctx, "device_faults", None)
    if not isinstance(reg, dict):
        reg = {}
        try:
            setattr(ctx, "device_faults", reg)
        except Exception:  # noqa: BLE001
            pass
    return reg


def _has_gate(ctx) -> bool:
    """True when the ctx is suitectx's SuiteCtx with the device-fault gate (camera_faulted, mark_fault, ...)."""
    return all(callable(getattr(ctx, n, None)) for n in ("camera_faulted", "mark_fault", "clear_fault"))


def _norm_fault(rec: dict | None) -> dict | None:
    """suitectx fault record (since_utc, class, faulted) or capkit fallback record -> one shape."""
    if not rec:
        return None
    if "faulted" in rec and not rec.get("faulted"):
        return None
    if "active" in rec and not rec.get("active"):
        return None
    det = rec.get("detail") if isinstance(rec.get("detail"), dict) else {}
    return {"active": True, "utc": rec.get("since_utc") or rec.get("utc"), "test": rec.get("test"),
            "mode": rec.get("mode"), "api": rec.get("api"), "code": rec.get("code"),
            "kind": rec.get("class") or rec.get("kind"), "stage": rec.get("stage"),
            "reason": rec.get("reason") or det.get("reason") or rec.get("why"),
            "source": rec.get("source"), "plug_in_age_s": rec.get("plug_in_age_s")}


def device_fault(ctx, cam: dict) -> dict | None:
    """The camera's active fault record (suitectx ``ctx.camera_faulted``; fallback ``ctx.device_faults``), or None."""
    if _has_gate(ctx):
        try:
            return _norm_fault(ctx.camera_faulted(cam["key"]))
        except Exception:  # noqa: BLE001
            return None
    return _norm_fault(_fault_registry(ctx).get(cam["key"]))


def device_gated(ctx, cam: dict) -> dict | None:
    """The fault record when the camera was faulted at the START of the current test (after the runner's re-probe),
    i.e. its streaming work in this test is skipped. Without the suitectx gate: same as device_fault."""
    fn = getattr(ctx, "camera_gated", None)
    if callable(fn) and _has_gate(ctx):
        try:
            return _norm_fault(fn(cam["key"]))
        except Exception:  # noqa: BLE001
            return None
    return device_fault(ctx, cam)


def mark_device_fault(ctx, cam: dict, test: str, mode: str | None, api: str | None, fault: dict) -> dict:
    """Record a device fault suite-wide: ``ctx.mark_fault`` (suitectx gate, idempotent: the first record is kept;
    ctx.camcmd's own scan has usually marked it already), else the fallback ``ctx.device_faults``."""
    if _has_gate(ctx):
        try:
            rec = ctx.mark_fault(cam["key"], test=test, mode=mode, code=fault.get("code"), api=api,
                                 stage=fault.get("stage"), cls=fault.get("kind"), source=test,
                                 detail={"reason": fault.get("reason")})
            if rec:
                return _norm_fault(rec) or {}
        except Exception:  # noqa: BLE001
            pass
    reg = _fault_registry(ctx)
    old = reg.get(cam["key"]) or {}
    act = bool(old.get("active"))
    rec = {"active": True, "utc": old.get("utc") if act else results.utc_now_iso(),
           "test": old.get("test") if act else test, "mode": old.get("mode") if act else mode,
           "api": old.get("api") if act else api,
           "code": fault.get("code"), "kind": fault.get("kind"), "stage": fault.get("stage"),
           "reason": fault.get("reason"), "camera": cam_label(cam), "history": old.get("history", [])}
    rec["history"] = rec["history"] + [{"utc": results.utc_now_iso(), "event": "fault", "test": test, "mode": mode,
                                        "api": api, **fault}]
    reg[cam["key"]] = rec
    note_first_failure(ctx, cam, test, mode, api, fault.get("code"), fault.get("reason"))
    try:
        ctx.log(f"{test}: DEVICE FAULT {cam_label(cam)}: {fault.get('reason')} ({mode} {api}); remaining work on "
                "this camera is skipped (needs a replug, never a programmatic restart)")
    except Exception:  # noqa: BLE001
        pass
    return _norm_fault(rec) or rec


def clear_device_fault(ctx, cam: dict, test: str, probe: dict | None = None) -> dict | None:
    """Un-fault a camera that answered a health check again; the recovery is recorded (suitectx ``clear_fault``)."""
    if _has_gate(ctx):
        try:
            return ctx.clear_fault(cam["key"], test=test, source="health_probe", detail=probe)
        except Exception:  # noqa: BLE001
            return None
    reg = _fault_registry(ctx)
    rec = reg.get(cam["key"])
    if not rec:
        return None
    rec["active"] = False
    rec["history"] = rec.get("history", []) + [{"utc": results.utc_now_iso(), "event": "recovered", "test": test,
                                                "probe": probe}]
    try:
        ctx.log(f"{test}: {cam_label(cam)} answered the health check again; fault since {rec.get('utc')} cleared")
    except Exception:  # noqa: BLE001
        pass
    return rec


def note_first_failure(ctx, cam: dict, test: str, mode: str | None, api: str | None, code: Any,
                       reason: str | None = None) -> None:
    """Suite-wide 'first failure per camera': suitectx ``ctx.record_failure`` (only the first call per camera
    counts), else the fallback ``ctx.first_failures``."""
    fn = getattr(ctx, "record_failure", None)
    if callable(fn) and _has_gate(ctx):
        try:
            fn(cam["key"], test=test, mode=mode, code=code, api=api, cls=reason, source=test)
            return
        except Exception:  # noqa: BLE001
            pass
    ff = getattr(ctx, "first_failures", None)
    if not isinstance(ff, dict):
        ff = {}
        try:
            setattr(ctx, "first_failures", ff)
        except Exception:  # noqa: BLE001
            return
    ff.setdefault(cam["key"], {"utc": results.utc_now_iso(), "test": test, "mode": mode, "api": api,
                               "code": code, "reason": reason})


def first_failure(ctx, cam: dict) -> dict | None:
    """The suite-wide first failure of the camera (suitectx ``first_failure`` or the fallback), or None."""
    for attr in ("first_failure", "first_failures"):
        d = getattr(ctx, attr, None)
        if isinstance(d, dict) and cam["key"] in d:
            return d[cam["key"]]
    return None


def health_check(ctx, cam: dict, mode: Mode | None, out_dir: Path, timeout_ms: int = 3000,
                 test: str | None = None, reason: str = "") -> dict:
    """One-frame MF capture (under camlock, bounded): does the camera answer? suitectx ``ctx.health_probe`` when
    present (it also updates the fault state: success clears a fault, a fault-like failure marks one), else a
    capkit wincam capture. Returns {ok, frames, code, stage, class, fault (dict|None), elapsed_s, ...}."""
    fn = getattr(ctx, "health_probe", None)
    if callable(fn) and _has_gate(ctx):
        try:
            pr = dict(fn(cam["key"], test=test, mode=mode, timeout_ms=max(timeout_ms, 3000), reason=reason))
        except Exception as e:  # noqa: BLE001
            return {"ok": None, "error": repr(e)}
        pr["fault"] = ({"kind": pr.get("class"), "code": pr.get("code"), "stage": pr.get("stage"),
                        "reason": f"health probe failed ({pr.get('code') or pr.get('class')})"}
                       if pr.get("fault_like") else None)
        return pr
    if not cam.get("mf_symlink") or mode is None:
        return {"ok": None, "reason": "no MF symlink or no mode to probe"}
    s, r = wincam_capture(ctx, cam, mode, out_dir, frames=1, save="none", timeout_ms=timeout_ms)
    s = s or {}
    frames = ((s.get("frames") or {}).get("total") if isinstance(s.get("frames"), dict) else s.get("frames")) or 0
    code, stage, _err = failure_code("mf", s, r)
    cls = None if s.get("ok") else classify("mf", code, stage, frames=frames, timed_out=bool(r.get("timed_out")))
    flt = None if (s.get("ok") and frames) else fault_from_result("mf", s, r, cls)
    out = {"ok": bool(s.get("ok") and frames), "frames": frames, "mode": mode.text, "code": code, "stage": stage,
           "class": (cls or {}).get("class"), "fault": flt, "rc": r.get("rc"), "elapsed_s": r.get("elapsed_s"),
           "utc": results.utc_now_iso()}
    if flt:
        mark_device_fault(ctx, cam, test or "health_check", mode.text, "mf", flt)
    return out


# ============================================================================================================ controls
CONTROL_STATE_NAMES = ("auto_exposure_priority", "exposure", "gain", "white_balance", "focus", "powerline_frequency",
                       "backlight_compensation", "brightness")


def control_state(controls_json: dict | None) -> dict:
    """Compact read-only control state of a camera (``wincam controls --read-only``): value and auto/manual mode of
    the controls that change frame timing or exposure (auto-exposure priority, exposure, gain, white balance,
    focus, power-line frequency ...). ``answering`` False when the controls are listed but every GET failed (the
    Kiyo's fault state: rc 0 with failed GETs)."""
    if not controls_json:
        return {"answering": None, "reason": "no controls JSON"}
    tab = control_table(controls_json)
    out: dict[str, Any] = {}
    for n in CONTROL_STATE_NAMES:
        c = tab.get(n)
        if not c:
            continue
        flags = c.get("flags_names") or []
        out[n] = {"value": c.get("value"), "mode": "auto" if "auto" in flags else ("manual" if "manual" in flags
                                                                                    else None),
                  "min": c.get("min"), "max": c.get("max")}
    got = [c for c in tab.values() if c.get("value") is not None]
    return {"answering": bool(got) if tab else None, "supported": len(tab), "with_value": len(got),
            "controls": out, "error": controls_json.get("error")}


# ============================================================================================================ misc
def arrivals_before(ctx) -> dict:
    try:
        return ctx.arrivals()
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}


def arrivals_after(ctx, before: dict) -> dict:
    try:
        after = ctx.arrivals()
        diff = suitectx.diff_arrivals(before, after) if "cameras" in before and "cameras" in after else None
    except Exception as e:  # noqa: BLE001
        return {"before": before, "error": repr(e)}
    return {"before": before, "after": after, "changes": diff,
            "unexplained_re_arrival": bool(diff and any(d.get("re_arrival") for d in diff))}


def new_result(ctx, test: str, cams: list[dict] | None = None) -> dict:
    cl = [suitectx.camera_summary(c) for c in (cams if cams is not None else ctx.cameras)]
    return results.new_result(test, platform="windows", command=sys.argv, cameras=cl)


def quick(ctx) -> bool:
    return bool(getattr(ctx.args, "quick", False))


def arg(ctx, name: str, full: Any, quick_value: Any) -> Any:
    v = getattr(ctx.args, name, None)
    if v is not None:
        return v
    return quick_value if quick(ctx) else full


def save_sample(ctx, test: str, cam: dict, tag: str, b: bytes | None) -> str | None:
    """Keep one small sample JPEG in the results folder (the rest stays in raw_dir). Only real JPEG bytes are kept:
    a raw YUY2/NV12 frame (PyAV's silent format fallback, e.g. 1.8 MB on the Kiyo at 720p) must not land in the
    repo, let alone named .jpg (review 2026-11-06)."""
    if not b or b[:2] != b"\xff\xd8":
        return None
    p = Path(ctx.out_dir) / test / "samples" / f"{cam_slug(cam)}_{tag}.jpg"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b)
    return str(p.relative_to(ctx.out_dir)).replace("\\", "/")


def wait_s(s: float) -> None:
    time.sleep(max(0.0, s))
