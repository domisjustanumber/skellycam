"""W-TBUMP: release check T-BUMP, one real skellycam recording before and after the phase-1 package bump.

research/CAPTURE_AND_RECORDING_PLAN.md section 3.3 ("Release checks"): T-BUMP is "the full test suite plus one real
recording after each major package bump". This test is the real recording, done twice with the same cameras and
settings and compared:
  (a) baseline: commit 2992e64f9 (upstream main + the test-collection fix; Python 3.12, OpenCV 4.12, numpy 2.2,
      PyAV 18), in the detached worktree c:\\Users\\Dom\\GitHub\\freemocap\\skellycam-tbump-baseline;
  (b) head: the phase-1 branch dom/capture-recording-phase1 in c:\\Users\\Dom\\GitHub\\freemocap\\skellycam-phase1
      (Python 3.13, OpenCV 5, numpy 2.5, PyAV 19, exact pins).
The question: did the OpenCV 5 / numpy 2.5 / PyAV 19 / Python 3.13 bump change capture or recording behaviour?

Each recording is ONE ctx.camcmd call (so camlock serialises it) of helpers/skellycam_record.py, which starts that
checkout's server headless on a free port, resolves the suite's cameras to skellycam's DirectShow indices through
POST /skellycam/camera/detect (property bags only, no camera opened), connects exactly those cameras, records,
stops, shuts the server down and verifies the files (see the driver's docstring). Settings: 1280x720 at 30 fps, MJPG
capture fourcc (skellycam's DEFAULT_CAPTURE_FOURCC), lockstep (skellycam's only mode), skellycam's default exposure
(MANUAL -7) and writer codec; 60 s per recording (quick mode: 10 s).

Cameras: every camera in ctx.cameras except the ones ``ctx.camera_gated(cam)`` or ``ctx.camera_dead(cam)`` reports
(device-fault gate / dead rule), and the ones with neither a DirectShow DevicePath nor an MF symlink. The Razer Kiyo
Pro (1532:0E05) is included while it is alive. A Kiyo Pro fault in the driver output (a first-frame failure or
timeout, 0x8007001F, the camera failing to start or closing mid-stream) is reported in ``fault_reports`` /
``kiyo_pro_fault`` for the integrator to pass to ``ctx.mark_fault`` (``MARK_FAULTS = True`` makes this module do it),
and the Kiyo Pro is never streamed again in this test: the later recording runs without it, and a recording that
failed because of it is repeated ONCE without it so the two versions can still be compared.

Verdicts (common/rating.py layout):
  T-BUMP|recording   yes = both recordings verified and every comparison criterion met; partial = both verified but
                     something changed (per-camera fps > 2 %, frame count > 2 %, codec / container / size, CSV header,
                     > 35 % file size per frame, start time > 1.5x + 10 s, new server-log error kinds, more
                     tracebacks, unclean shutdown); no = the baseline recorded and verified, head did not;
                     untested = no reference (baseline failed), no camera, a checkout missing, or a device fault.
  T-BUMP|<camera key>  the same per camera (fps, frames, codec, size, readable video, CSV checks).
Tier 0 only: timing is skellycam's own perf-counter grab timestamps; no UVC metadata.

Recording output (videos show the room) goes to ctx.raw_test_dir("W-TBUMP"), outside the repo; the result JSON
keeps only metrics and paths.

Offline comparison of two driver summaries (no camera):
    python suite/windows/tests/w_tbump.py --compare <baseline summary.json> <head summary.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from common import rating, results  # noqa: E402

TEST = "W-TBUMP"
GOAL = "T-BUMP"
INFO = {"goal": GOAL, "opens_cameras": True,
        "claim": "CAPTURE_AND_RECORDING_PLAN.md 3.3 T-BUMP: one real recording after each major package bump",
        "summary": "real skellycam recording (1280x720@30 MJPG, lockstep, all live cameras) at the baseline commit "
                   "2992e64f9 and at the phase-1 head; compare fps, frame counts, start time, errors, size, codec"}
DRIVER = WIN / "helpers" / "skellycam_record.py"
FREEMOCAP_DIR = Path(r"c:\Users\Dom\GitHub\freemocap")
BASELINE_DIR = FREEMOCAP_DIR / "skellycam-tbump-baseline"
BASELINE_COMMIT = "2992e64f971f4c1b305de0e3912a3dd2cbe2a661"
HEAD_DIR = FREEMOCAP_DIR / "skellycam-phase1"
HEAD_BRANCH = "dom/capture-recording-phase1"
WIDTH, HEIGHT, FPS = 1280, 720, 30
SECONDS_FULL, SECONDS_QUICK = 60.0, 10.0
OVERHEAD_S = 100.0          # uv + server start, detect, connect, stop/finalise, close, shutdown, verify (per run)
PER_CAMERA_S = 5.0          # per camera per run (open, finalise, decode-all verification)
DEADLINE_EXTRA_S = 420.0    # driver deadline = seconds + this; camcmd timeout = deadline + CAMCMD_SLACK_S
CAMCMD_SLACK_S = 90.0
MARK_FAULTS = True         # True: call ctx.mark_fault for a Kiyo Pro fault here (else the integrator does)
TOL = {"fps_rel": 0.02, "frames_rel": 0.02, "bytes_per_frame_rel": 0.35, "connect_factor": 1.5,
       "connect_extra_s": 10.0}
#: driver fault_hints codes that are a camera fault on their own; grab / retrieve failures count only when the
#: recording failed (skellycam retries a failed grab, and a recording that verified is not a fault)
FAULT_CODES = {"0x8007001F", "open_failed", "first_frame_failed", "setup_failed", "connect_timeout", "start_failed",
               "camera_closed"}
SOFT_CODES = {"grab_failed", "retrieve_failed"}


# ============================================================================================================ setup
def seconds(ctx) -> float:
    a = getattr(ctx, "args", None)
    s = getattr(a, "tbump_seconds", None)
    if s:
        return float(s)
    return SECONDS_QUICK if getattr(a, "quick", False) else SECONDS_FULL


def checkouts(ctx) -> list[tuple[str, Path, str | None]]:
    a = getattr(ctx, "args", None)
    return [("baseline", Path(getattr(a, "tbump_baseline_dir", None) or BASELINE_DIR), BASELINE_COMMIT),
            ("head", Path(getattr(a, "tbump_head_dir", None) or HEAD_DIR), None)]


def exclusion(ctx, cam: dict) -> str | None:
    """Why this camera is left out (None = include). Dead rule and device-fault gate first."""
    dead = getattr(ctx, "camera_dead", lambda c: None)(cam)
    if dead:
        return f"dead since {dead.get('since_utc')} (dead rule: no command reaches it)"
    gate = getattr(ctx, "camera_gated", lambda c: None)(cam)
    if gate:
        return f"device-fault gate: faulted since {gate.get('since_utc')} ({gate.get('code') or gate.get('class')})"
    if not cam.get("ds_path") and not cam.get("mf_symlink"):
        return "no DirectShow DevicePath or MF symlink to resolve the skellycam index from"
    return None


def eligible(ctx) -> tuple[list[dict], dict[str, str]]:
    keep, out = [], {}
    for c in getattr(ctx, "cameras", []) or []:
        why = exclusion(ctx, c)
        if why:
            out[c["key"]] = why
        else:
            keep.append(c)
    return keep, out


def spec_for(cam: dict) -> str:
    return f"ds:{cam['ds_path']}" if cam.get("ds_path") else f"mf:{cam['mf_symlink']}"


def estimate_s(ctx) -> float:
    n = len(eligible(ctx)[0])
    return 2 * (seconds(ctx) + OVERHEAD_S + PER_CAMERA_S * n)


def driver_args(checkout: Path, cams: list[dict], secs: float, out_dir: Path, name: str) -> list[str]:
    args = ["--checkout", str(checkout)]
    for c in cams:
        args += ["--camera", spec_for(c)]
    args += ["--width", WIDTH, "--height", HEIGHT, "--fps", FPS, "--seconds", f"{secs:g}", "--out-dir", str(out_dir),
             "--recording-name", name, "--deadline-s", f"{secs + DEADLINE_EXTRA_S:g}", "--capture-fourcc", "MJPG"]
    return [str(a) for a in args]


def preflight(ctx, label: str, path: Path, commit: str | None) -> dict:
    """The checkout exists, has a synced .venv, and (baseline) sits at the expected commit. No camera command."""
    out: dict[str, Any] = {"label": label, "path": str(path), "ok": False}
    if not path.is_dir() or not (path / "pyproject.toml").is_file():
        out["error"] = f"{path} is not a skellycam checkout"
        return out
    if not (path / ".venv").is_dir():
        out["error"] = f"{path} has no .venv (run `uv sync` there)"
        return out
    run = getattr(ctx, "run", None)
    head = None
    if callable(run):
        r = run(["git", "-C", str(path), "rev-parse", "HEAD"], timeout_s=20)
        head = (r.get("stdout") or "").strip() or None
        b = run(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"], timeout_s=20)
        out["branch"] = (b.get("stdout") or "").strip() or None
    out["commit"] = head
    if commit and head and head != commit:
        out["error"] = f"{path} is at {head[:9]}, expected {commit[:9]}"
        return out
    out["ok"] = True
    return out


# ============================================================================================================ run
def _parse(r: dict) -> tuple[dict | None, str | None]:
    out = (r.get("stdout") or "").strip()
    if not out:
        return None, "empty stdout"
    try:
        return json.loads(out), None
    except ValueError:
        pass
    i, j = out.find("{"), out.rfind("}")
    if 0 <= i < j:
        try:
            return json.loads(out[i:j + 1]), None
        except ValueError as e:
            return None, f"JSON parse error: {e}"
    return None, "no JSON object in stdout"


def record_once(ctx, label: str, checkout: Path, cams: list[dict], secs: float, raw: Path) -> dict:
    """ONE camcmd call: the driver records with exactly ``cams``."""
    od = raw / label
    od.mkdir(parents=True, exist_ok=True)
    argv = [*ctx.helper_cmd(DRIVER), *driver_args(checkout, cams, secs, od, f"tbump_{label}")]
    timeout = secs + DEADLINE_EXTRA_S + CAMCMD_SLACK_S
    ctx.log(f"{TEST}: {label}: recording {secs:g} s with {len(cams)} camera(s) "
            f"({', '.join(str(c.get('name')) for c in cams)}) from {checkout}")
    r = ctx.camcmd(argv, timeout_s=timeout)
    obj, perr = _parse(r)
    run = {"label": label, "checkout": str(checkout), "cameras": [c["key"] for c in cams], "out_dir": str(od),
           "camcmd": {k: r.get(k) for k in ("rc", "timed_out", "killed", "elapsed_s", "lock_wait_s", "lock_timed_out",
                                            "gate_skipped", "dry_run", "spawn_error")},
           "timeout_s": timeout, "driver": obj, "parse_error": perr,
           "spec_to_key": {spec_for(c): c["key"] for c in cams}}
    if obj is None:
        run["stderr_tail"] = (r.get("stderr") or "")[-2000:]
    run["ok"] = bool(obj and obj.get("ok")) and not r.get("timed_out")
    ctx.log(f"{TEST}: {label}: {'ok' if run['ok'] else 'FAILED'} rc={r.get('rc')} "
            f"{'' if obj is None else (obj.get('stage_failed') or '')} in {r.get('elapsed_s')} s")
    return run


def fault_reports(run: dict, cams: list[dict]) -> list[dict]:
    """Camera faults in one recording: the driver's fault_hints mapped to suite cameras, plus a 'suspected' report
    for every Kiyo Pro in the set when the command hung (killed at its timeout or no JSON) with nothing attributed."""
    by_key = {c["key"]: c for c in cams}
    s2k = run.get("spec_to_key") or {}
    obj = run.get("driver") or {}
    out = []
    for h in obj.get("fault_hints") or []:
        key = s2k.get(h.get("spec"))
        if key is None:
            continue
        code = h.get("code")
        if code not in FAULT_CODES and not (code in SOFT_CODES and not run.get("ok")):
            continue
        c = by_key.get(key, {})
        out.append({"key": key, "name": c.get("name"), "is_kiyo": bool(c.get("is_kiyo")), "code": code,
                    "stage": h.get("stage"), "evidence": h.get("evidence"), "run": run["label"],
                    "source": "skellycam_record fault_hints", "suspected": False,
                    "camera_index": h.get("camera_index"), "skellycam_camera_id": h.get("camera_id")})
    cc = run.get("camcmd") or {}
    hung = (cc.get("timed_out") or (run.get("driver") is None and not cc.get("dry_run")
                                    and not cc.get("gate_skipped"))) and not cc.get("lock_timed_out")
    if hung and not out:
        for c in cams:
            if c.get("is_kiyo"):
                out.append({"key": c["key"], "name": c.get("name"), "is_kiyo": True,
                            "code": "timeout" if cc.get("timed_out") else "no_result", "stage": "process",
                            "evidence": f"skellycam_record {'killed at its timeout' if cc.get('timed_out') else 'gave no JSON'}"
                                        " with the Kiyo Pro in the camera set",
                            "run": run["label"], "source": "camcmd", "suspected": True})
    return out


# ---- as-found controls (integrated 2026-11-11): skellycam sets exposure to MANUAL -7 and leaves it there; the smoke
# run left three cameras in manual exposure. Snapshot each camera's controls before the recordings and restore them
# after, the way the control tests do (w_auto.restore_state), so later tests and the morning see the as-found state.
RESTORE_NAMES = ("exposure", "gain", "focus", "white_balance", "brightness", "contrast", "saturation", "sharpness",
                 "backlight_compensation", "auto_exposure_priority", "powerline_frequency")


def _snapshot(ctx, cams: list) -> dict:
    out = {}
    if getattr(ctx, "dry_run", False):
        return out
    try:
        import capkit as ck
        import w_auto as wa
        import w_ctrl_effect as ce
    except Exception as e:  # noqa: BLE001
        return {"_error": repr(e)}
    for cam in cams:
        try:
            j, _r = ck.get_controls(ctx, cam, "mf")
            tab = ck.control_table(j)
            names = [n for n in RESTORE_NAMES if n in tab and ce.control_answered(tab[n])]
            if names:
                out[cam["key"]] = {"state": wa.state_of(tab, names),
                                   "ranges": {n: {k: (tab.get(n) or {}).get(k) for k in ("min", "max", "step", "default")}
                                              for n in names}}
        except Exception as e:  # noqa: BLE001 - a snapshot problem must not stop the recordings
            out[cam["key"]] = {"error": repr(e)}
    return out


def _restore(ctx, cams: list, snaps: dict) -> dict:
    out = {}
    if not snaps or getattr(ctx, "dry_run", False):
        return out
    import w_auto as wa
    for cam in cams:
        sn = snaps.get(cam["key"]) or {}
        dead = getattr(ctx, "camera_dead", lambda c: None)(cam)
        if dead or "state" not in sn:
            out[cam["key"]] = {"skipped": "dead (Kiyo Pro dead rule)" if dead else (sn.get("error") or "no snapshot")}
            continue
        try:
            rs = wa.restore_state(ctx, cam, "mf", sn["state"], sn["ranges"])
            out[cam["key"]] = {"restored": rs.get("restored"), "after": rs.get("after")}
            ctx.log(f"{TEST}: {cam.get('name')}: as-found controls restored after the recordings: {rs.get('restored')}")
        except Exception as e:  # noqa: BLE001
            out[cam["key"]] = {"error": repr(e)}
    return out


def run(ctx) -> dict:
    res = results.new_result(TEST, platform="windows", command=sys.argv,
                             cameras=ctx.camera_summaries() if hasattr(ctx, "camera_summaries") else [])
    secs = seconds(ctx)
    raw = Path(ctx.raw_test_dir(TEST))
    cams, excluded = eligible(ctx)
    meas: dict[str, Any] = {"settings": {"width": WIDTH, "height": HEIGHT, "fps": FPS, "seconds": secs,
                                         "capture_fourcc": "MJPG", "exposure": "skellycam default (MANUAL -7)",
                                         "writer_fourcc": "skellycam default", "lockstep": True},
                            "excluded": excluded, "eligible": [c["key"] for c in cams], "raw_dir": str(raw),
                            "runs": {}, "preflight": {}}
    errors: list = []
    verdicts: dict = {}
    res["fault_reports"] = []
    res["kiyo_pro_fault"] = None
    for k, why in excluded.items():
        ctx.log(f"{TEST}: {(ctx.camera(k) or {}).get('name') if hasattr(ctx, 'camera') else k} excluded: {why}")

    pf = {label: preflight(ctx, label, path, commit) for label, path, commit in checkouts(ctx)}
    meas["preflight"] = pf
    bad = [p for p in pf.values() if not p["ok"]]
    if bad or not cams:
        why = "; ".join(p["error"] for p in bad) if bad else "no eligible camera (" + (
            "; ".join(f"{k}: {v}" for k, v in excluded.items()) or "none attached") + ")"
        ctx.log(f"{TEST}: untested: {why}")
        verdicts[f"{GOAL}|recording"] = rating.untested(why, {"preflight": pf, "excluded": excluded})
        return results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)

    kiyo_out: set[str] = set()     # Kiyo Pro keys never to be streamed again in this test
    snaps = _snapshot(ctx, cams)
    meas["as_found_controls"] = {k: (v.get("state") if isinstance(v, dict) else v) for k, v in snaps.items()}
    for label, path, _ in checkouts(ctx):
        use = [c for c in cams if c["key"] not in kiyo_out and not exclusion(ctx, c)]
        if not use:
            meas["runs"][label] = {"label": label, "ok": False, "skipped": "no camera left (after a Kiyo Pro fault "
                                                                            "or a device fault)"}
            continue
        r = record_once(ctx, label, path, use, secs, raw)
        if (r.get("camcmd") or {}).get("dry_run"):
            meas["runs"][label] = r
            continue
        rep = fault_reports(r, use)
        r["fault_reports"] = rep
        res["fault_reports"] += rep
        kiyo = [f for f in rep if f["is_kiyo"]]
        for f in kiyo:
            kiyo_out.add(f["key"])
            if res["kiyo_pro_fault"] is None:
                res["kiyo_pro_fault"] = f
            ctx.log(f"{TEST}: Kiyo Pro {'suspected ' if f['suspected'] else ''}fault in the {label} recording: "
                    f"{f['code']} at {f['stage']}: {str(f.get('evidence'))[:160]}"
                    + ("" if MARK_FAULTS else " (reported for ctx.mark_fault; not streamed again in this test)"))
            if MARK_FAULTS and hasattr(ctx, "mark_fault") and not f["suspected"]:
                ctx.mark_fault(f["key"], test=TEST, mode=f"MJPG {WIDTH}x{HEIGHT}@{FPS}", code=f["code"],
                               api="skellycam", stage=f["stage"], source="w_tbump", detail=f.get("evidence"))
        rest = [c for c in use if c["key"] not in kiyo_out]
        if not r["ok"] and kiyo and rest:
            # the recording failed because of the Kiyo Pro: repeat it ONCE without it (the Kiyo Pro is not retried)
            meas["runs"][f"{label}_with_kiyo_pro"] = r
            ctx.log(f"{TEST}: {label}: repeating once without the Kiyo Pro so the versions can be compared")
            r = record_once(ctx, label, path, rest, secs, raw / "rerun")
            r["rerun_without_kiyo_pro"] = True
            rep2 = fault_reports(r, rest)
            r["fault_reports"] = rep2
            res["fault_reports"] += rep2
        meas["runs"][label] = r

    meas["restore"] = _restore(ctx, [c for c in cams if c["key"] not in kiyo_out], snaps)
    base, head = meas["runs"].get("baseline") or {}, meas["runs"].get("head") or {}
    cmp_ = compare_runs(base, head, dropped=kiyo_out)
    meas["comparison"] = cmp_
    verdicts.update(rate(cmp_, base, head, res["fault_reports"]))
    for lab, r in meas["runs"].items():
        d = r.get("driver") or {}
        if r.get("ok") is False and d.get("error"):
            errors.append({"run": lab, "stage": d.get("stage_failed"), "error": d.get("error")})
        elif r.get("parse_error") and not (r.get("camcmd") or {}).get("dry_run"):
            errors.append({"run": lab, "parse_error": r["parse_error"], "camcmd": r.get("camcmd")})
    return results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)


# ============================================================================================================ compare
def _get(d: Any, *path, default=None):
    for p in path:
        if not isinstance(d, dict):
            return default
        d = d.get(p)
    return default if d is None else d


def metrics(run: dict) -> dict:
    """The comparable facts of one recording, per camera keyed by the suite camera key."""
    d = run.get("driver") or {}
    v = d.get("verify") or {}
    s2k = run.get("spec_to_key") or {}
    id2key = {str(r.get("camera_id")): s2k.get(r.get("spec"), r.get("spec")) for r in d.get("resolution") or []}
    extracted = _get(d, "group", "extracted_configs", default={}) or {}
    cams = {}
    for cid, c in (v.get("cameras") or {}).items():
        key = id2key.get(str(cid), f"skellycam:{cid}")
        vid = c.get("video") or {}
        pa = c.get("pyav") or {}
        ocv = c.get("opencv") or {}
        csvd = c.get("csv") or {}
        n = _get(c, "frames", "count")
        ex = extracted.get(cid) or {}
        cams[key] = {
            "skellycam_camera_id": cid, "camera_index": c.get("camera_index"), "ok": c.get("ok"),
            "problems": c.get("problems"), "frames": n, "fps_from_timestamps": c.get("fps_from_timestamps"),
            "interval_ms": _get(csvd, "timestamps", "interval_ms"),
            "long_intervals": _get(csvd, "timestamps", "long_intervals_gt_1p5x_median"),
            "connection_frames_skipped": csvd.get("connection_frames_skipped"),
            "first_frame_from_recording_start_s": csvd.get("first_frame_from_recording_start_s"),
            "csv_header_sha1": csvd.get("header_sha1"), "csv_columns": csvd.get("columns"),
            "ext": vid.get("ext"), "size_bytes": vid.get("size_bytes"),
            "bytes_per_frame": round(vid["size_bytes"] / n) if vid.get("size_bytes") and isinstance(n, int) and n else None,
            "codec": pa.get("codec"), "pix_fmt": pa.get("pix_fmt"), "container": pa.get("container"),
            "width": pa.get("width") or ocv.get("width"), "height": pa.get("height") or ocv.get("height"),
            "average_rate": pa.get("average_rate"), "keyframes": pa.get("keyframes"), "opencv_fourcc": ocv.get("fourcc"),
            "opencv_decoded": ocv.get("decoded_frames"),
            "extracted_resolution": ex.get("resolution"), "extracted_framerate": ex.get("framerate"),
            "extracted_exposure": ex.get("exposure"),
        }
    sl = d.get("server_log") or {}
    srv = d.get("server") or {}
    return {
        "ok": bool(run.get("ok")), "stage_failed": d.get("stage_failed"), "error": d.get("error"),
        "rerun_without_kiyo_pro": bool(run.get("rerun_without_kiyo_pro")),
        "commit": _get(d, "checkout", "commit"), "versions": _get(d, "checkout", "versions"),
        "phases_s": d.get("phases_s") or {}, "frames": v.get("frames"), "frame_counts_equal": v.get("frame_counts_equal"),
        "group_fps": _get(v, "multiframe_csv", "fps_from_timestamps"),
        "inter_camera_grab_range_ms": _get(v, "multiframe_csv", "inter_camera_grab_range_ms"),
        "multiframe_csv_header_sha1": _get(v, "multiframe_csv", "header_sha1"),
        "stop_response": d.get("stop_response"),
        "server_log": {"error_lines": sl.get("error_lines"), "error_kinds": sl.get("error_kinds") or {},
                       "tracebacks": sl.get("tracebacks"), "logging_errors": sl.get("logging_errors"),
                       "writer_codec_lines": sl.get("writer_codec_lines")},
        "clean_shutdown": srv.get("clean"), "leftover_processes": srv.get("leftover_processes"),
        "verify_problems": v.get("problems"), "cameras": cams,
    }


def _rel(a: Any, b: Any) -> float | None:
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or not b:
        return None
    return (a - b) / b


def _crit(name: str, met: bool | None, detail: Any = None) -> dict:
    return {"criterion": name, "met": met, "detail": detail}


def camera_criteria(b: dict, h: dict) -> list[dict]:
    out = []
    rf = _rel(h.get("fps_from_timestamps"), b.get("fps_from_timestamps"))
    out.append(_crit("fps within 2 %", None if rf is None else abs(rf) <= TOL["fps_rel"],
                     {"baseline": b.get("fps_from_timestamps"), "head": h.get("fps_from_timestamps"),
                      "rel": None if rf is None else round(rf, 4)}))
    rn = _rel(h.get("frames"), b.get("frames"))
    out.append(_crit("frame count within 2 %", None if rn is None else abs(rn) <= TOL["frames_rel"],
                     {"baseline": b.get("frames"), "head": h.get("frames")}))
    same = {k: (b.get(k), h.get(k)) for k in ("codec", "container", "ext", "pix_fmt", "width", "height")}
    out.append(_crit("same codec, container and frame size", all(x == y for x, y in same.values()),
                     {k: {"baseline": x, "head": y} for k, (x, y) in same.items()}))
    rb = _rel(h.get("bytes_per_frame"), b.get("bytes_per_frame"))
    out.append(_crit("bytes per frame within 35 % (scene-dependent)",
                     None if rb is None else abs(rb) <= TOL["bytes_per_frame_rel"],
                     {"baseline": b.get("bytes_per_frame"), "head": h.get("bytes_per_frame"),
                      "rel": None if rb is None else round(rb, 3)}))
    out.append(_crit("same timestamps CSV header", b.get("csv_header_sha1") == h.get("csv_header_sha1"),
                     {"baseline": b.get("csv_header_sha1"), "head": h.get("csv_header_sha1")}))
    out.append(_crit("head video readable and CSV checks pass", bool(h.get("ok")), h.get("problems") or None))
    return out


def compare_runs(base: dict, head: dict, dropped: set[str] | None = None) -> dict:
    """Side-by-side metrics and the comparison criteria (both runs present and verified), else the reason.
    ``dropped``: camera keys left out of a run after a fault in this test (not a bump difference)."""
    mb, mh = metrics(base or {}), metrics(head or {})
    out: dict[str, Any] = {"baseline": mb, "head": mh, "criteria": [], "per_camera": {}}
    vb, vh = mb.get("versions") or {}, mh.get("versions") or {}
    out["version_changes"] = {k: {"baseline": vb.get(k), "head": vh.get(k)} for k in sorted(set(vb) | set(vh))
                              if vb.get(k) != vh.get(k)}
    if not mb["ok"] or not mh["ok"]:
        out["comparable"] = False
        return out
    out["comparable"] = True
    common = sorted(set(mb["cameras"]) & set(mh["cameras"]))
    out["camera_sets"] = {"baseline": sorted(mb["cameras"]), "head": sorted(mh["cameras"]), "common": common}
    for k in common:
        out["per_camera"][k] = camera_criteria(mb["cameras"][k], mh["cameras"][k])
    crit = out["criteria"]
    drop = set(dropped or ())
    out["camera_sets"]["dropped_after_fault"] = sorted(drop)
    crit.append(_crit("same camera set (cameras dropped after a fault excluded)",
                      set(mb["cameras"]) - drop == set(mh["cameras"]) - drop, out["camera_sets"]))
    crit.append(_crit("lockstep: equal frame counts across cameras in both",
                      bool(mb["frame_counts_equal"]) and bool(mh["frame_counts_equal"]),
                      {"baseline": mb["frame_counts_equal"], "head": mh["frame_counts_equal"]}))
    rg = _rel(mh["group_fps"], mb["group_fps"])
    crit.append(_crit("group fps within 2 %", None if rg is None else abs(rg) <= TOL["fps_rel"],
                      {"baseline": mb["group_fps"], "head": mh["group_fps"]}))
    cb, ch = mb["phases_s"].get("connect"), mh["phases_s"].get("connect")
    ok_c = None if not isinstance(cb, (int, float)) or not isinstance(ch, (int, float)) else \
        ch <= cb * TOL["connect_factor"] + TOL["connect_extra_s"]
    crit.append(_crit("start time (camera connect) not > 1.5x + 10 s", ok_c,
                      {"baseline_s": cb, "head_s": ch,
                       "start_to_health_s": {"baseline": mb["phases_s"].get("start_to_health"),
                                             "head": mh["phases_s"].get("start_to_health")},
                       "first_frame_from_recording_start_s": {
                           k: {"baseline": mb["cameras"][k].get("first_frame_from_recording_start_s"),
                               "head": mh["cameras"][k].get("first_frame_from_recording_start_s")} for k in common}}))
    kb, kh = set(mb["server_log"]["error_kinds"]), set(mh["server_log"]["error_kinds"])
    crit.append(_crit("no new server-log error kinds", not (kh - kb),
                      {"new_in_head": sorted(kh - kb), "gone_in_head": sorted(kb - kh),
                       "error_lines": {"baseline": mb["server_log"]["error_lines"],
                                       "head": mh["server_log"]["error_lines"]}}))
    tb, th = mb["server_log"]["tracebacks"] or 0, mh["server_log"]["tracebacks"] or 0
    lb, lh = mb["server_log"]["logging_errors"] or 0, mh["server_log"]["logging_errors"] or 0
    crit.append(_crit("no more tracebacks / logging errors", th <= tb and lh <= lb,
                      {"tracebacks": {"baseline": tb, "head": th}, "logging_errors": {"baseline": lb, "head": lh}}))
    crit.append(_crit("same writer-codec resolution",
                      (mb["server_log"]["writer_codec_lines"] or []) == (mh["server_log"]["writer_codec_lines"] or []),
                      {"baseline": mb["server_log"]["writer_codec_lines"], "head": mh["server_log"]["writer_codec_lines"]}))
    crit.append(_crit("same multi-frame CSV header", mb["multiframe_csv_header_sha1"] == mh["multiframe_csv_header_sha1"],
                      {"baseline": mb["multiframe_csv_header_sha1"], "head": mh["multiframe_csv_header_sha1"]}))
    crit.append(_crit("head server shut down cleanly (no kill, no leftover process)",
                      bool(mh["clean_shutdown"]) if mh["clean_shutdown"] is not None else None,
                      {"baseline": {"clean": mb["clean_shutdown"], "leftover": mb["leftover_processes"]},
                       "head": {"clean": mh["clean_shutdown"], "leftover": mh["leftover_processes"]}}))
    return out


def _verdict(r: str, criteria: list[dict], evidence: Any, note: str | None = None) -> dict:
    v = {"rating": r, "criteria": criteria, "evidence": evidence}
    if note:
        v["note"] = note
    return v


def rate(cmp_: dict, base: dict, head: dict, faults: list[dict]) -> dict:
    """T-BUMP|recording and T-BUMP|<camera key> verdicts from the comparison."""
    out: dict[str, dict] = {}
    mb, mh = cmp_["baseline"], cmp_["head"]
    ev = {"version_changes": cmp_.get("version_changes"),
          "baseline": {k: mb.get(k) for k in ("ok", "stage_failed", "error", "commit", "frames", "group_fps",
                                              "rerun_without_kiyo_pro")},
          "head": {k: mh.get(k) for k in ("ok", "stage_failed", "error", "commit", "frames", "group_fps",
                                          "rerun_without_kiyo_pro")},
          "fault_reports": faults or None}
    dev = [f for f in faults or [] if f.get("code") in FAULT_CODES | {"timeout", "no_result"}]
    if not cmp_.get("comparable"):
        if not base or base.get("skipped") or not mb["ok"]:
            why = "no reference: the baseline recording " + (
                base.get("skipped") if base and base.get("skipped") else f"failed ({mb.get('stage_failed')})")
            out[f"{GOAL}|recording"] = rating.untested(why, ev)
        elif not head or head.get("skipped") or (head.get("camcmd") or {}).get("dry_run"):
            out[f"{GOAL}|recording"] = rating.untested("head recording not run: " + str(
                (head or {}).get("skipped") or "plan mode / missing"), ev)
        elif dev and any(f["run"] == "head" for f in dev):
            out[f"{GOAL}|recording"] = rating.untested("head recording ended in a device fault (never an API "
                                                       "result)", ev)
        else:
            out[f"{GOAL}|recording"] = _verdict(
                "no", [_crit("head records and verifies like the baseline", False,
                             {"stage_failed": mh.get("stage_failed"), "error": mh.get("error"),
                              "verify_problems": (mh.get("verify_problems") or [])[:10]})], ev,
                note=f"regression: baseline verified, head failed at {mh.get('stage_failed')}")
        return out
    crit = list(cmp_["criteria"])
    for k, cc in cmp_["per_camera"].items():
        unmet = [c for c in cc if c["met"] is False]
        r = "yes" if all(c["met"] is True for c in cc) else "partial"
        out[f"{GOAL}|{k}"] = _verdict(r, cc, {"baseline": mb["cameras"].get(k), "head": mh["cameras"].get(k)})
        crit.append(_crit(f"camera {k}: per-camera criteria met", not unmet,
                          [c["criterion"] for c in unmet] or None))
    unmet = [c for c in crit if c["met"] is False]
    unknown = [c for c in crit if c["met"] is None]
    r = "partial" if unmet or unknown else "yes"
    note = None
    if unmet:
        note = "changed: " + "; ".join(c["criterion"] for c in unmet)
    elif unknown:
        note = "not measured: " + "; ".join(c["criterion"] for c in unknown)
    out[f"{GOAL}|recording"] = _verdict(r, crit, ev, note)
    return out


# ============================================================================================================ CLI
def main(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(description="W-TBUMP offline comparison of two skellycam_record summaries")
    ap.add_argument("--compare", nargs=2, metavar=("BASELINE_SUMMARY", "HEAD_SUMMARY"), required=True)
    a = ap.parse_args(argv)
    runs = []
    for label, p in zip(("baseline", "head"), a.compare):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        runs.append({"label": label, "ok": bool(d.get("ok")), "driver": d,
                     "spec_to_key": {r.get("spec"): r.get("spec") for r in d.get("resolution") or []}})
    cmp_ = compare_runs(runs[0], runs[1])
    print(json.dumps({"comparison": cmp_, "verdicts": rate(cmp_, runs[0], runs[1], [])}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
