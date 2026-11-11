"""W-PYAV-LIST: does PyAV / FFmpeg dshow ``list_devices`` (and ``list_options``) disturb the cameras?

Plan docs/capture_stack_options_plan.md section 6.1 (W-PYAV-LIST; row 2 "list devices without opening", extends
W-ID and W-FMT-NOGRAB). FFmpeg's dshow ``list_devices`` binds every capture filter to print its media types (a KS
filter open per camera; FFmpeg source, *inferred*), and ``list_options`` binds the named one. This test measures
what that does, per method:

| method                 | call                                                                        |
| pyav_list_devices      | PyAV 19.0.2 ``av.open("dummy", format="dshow", options={"list_devices": "true"})`` |
| ffmpeg_list_devices    | ``ffmpeg -list_devices true -f dshow -i dummy``                             |
| pyav_list_options      | PyAV ``av.open("video=@device_pnp_<path>", ..., {"list_options": "true"})`` per camera |
| ffmpeg_list_options    | ``ffmpeg -list_options true -f dshow -i video=@device_pnp_<path>`` per camera |

Conditions (each one ``helpers/pyav_list_session.py`` under ONE camera lock; every call bounded,
helpers/pyav_list.py):
- ``idle``: no suite stream; list_devices, then list_options for every camera;
- ``streaming:<camera>``: that camera streams through MF in another process (``wincam capture``, the in-scope mode:
  exactly 720 lines at >= 30 fps) while list_devices and list_options for that camera run; every camera in turn;
- the Kiyo as found: before the sessions its state is recorded (suite fault gate, plus a bounded
  ``wincam controls --api ds --read-only``). If it is wedged, the idle session's calls are the "faulted camera"
  case: their duration and any hang are the result. A wedged camera's own streaming condition is skipped (gate).

Measured per call: duration (QPC stamps inside the helper), hang (call bound 20 s; the PyAV helper exits without
waiting), FFmpeg's log, the listed devices / option lines. Per method and condition: disturbance of the streaming
process (frame gaps, a stop, or bad frames in each call window vs the frames before it; common/nograb.disturbance,
W-FMT-NOGRAB's thresholds), whether the streamer died, and pipe samples of EVERY camera during the call
(helpers/win_topology: an isochronous pipe opening on an idle camera = the listing started a stream / reserved
bandwidth).

Rating (verdict ``list_touch|all|<list_devices method>`` and ``list_touch|<camera>|<list_options method>``; a rating
text, not pass/fail):
- ``partial (touches but harmless)``: every call returned, no disturbance, no pipe opened (it still binds filters);
- ``no (disturbs)``: a gap / stop in the streaming process, the streamer died, or a pipe opened on an idle camera;
- ``no (hangs on a faulted camera)``: a call hung while a camera was faulted / not answering; ``no (hangs)``
  otherwise;
- ``untested``: no condition measured (e.g. ffmpeg CLI missing).
Listing only (tier 0).

Offline: ``python w_pyav_list.py --reanalyze <run_dir>`` re-analyses the stored session files.
"""
from __future__ import annotations

import json
import shutil
import statistics
import sys
from pathlib import Path

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
import suitectx  # noqa: E402
import w_auto as wa  # noqa: E402
import w_ctrl_effect as ce  # noqa: E402
from common import nograb, rating, results  # noqa: E402

TEST = "W-PYAV-LIST"
GOAL = "list_touch"
PYAV_LIST = WIN / "helpers" / "pyav_list.py"
SESSION = WIN / "helpers" / "pyav_list_session.py"
DEVICE_METHODS = ("pyav_list_devices", "ffmpeg_list_devices")
OPTION_METHODS = ("pyav_list_options", "ffmpeg_list_options")
CALL_TIMEOUT_S = 20.0
GAP_S = 1.5
BASELINE_S = 2.0
SETTLE_S = 1.0


def repeats(ctx) -> int:
    return int(ck.arg(ctx, "list_repeats", 3, 1))


def method_timeout(n: int) -> float:
    return n * (CALL_TIMEOUT_S + GAP_S) + 40        # + uv start-up


def estimate_s(ctx) -> float:
    """~2 s per PyAV call process (uv start-up + 0.2-1 s per call), ~1 s per CLI call, per condition + the stream."""
    n, c = repeats(ctx), len(ctx.cameras)
    per_method = 2.5 + n * (GAP_S + 0.8)
    idle = 4 + (2 + 2 * c) * per_method
    streaming = c * (8 + 4 * per_method)
    return idle + streaming + 10 * c


# ------------------------------------------------------------------------------------------------------- specs
def methods_for(ctx, cams: list[dict], ff: str | None, n: int, with_devices: bool = True) -> tuple[list, dict]:
    ms, skipped = [], {}
    devs = list(DEVICE_METHODS) if with_devices else []
    for mid in devs:
        if mid.startswith("ffmpeg") and not ff:
            skipped[mid] = "ffmpeg CLI not on PATH"
            continue
        ms.append({"id": mid, "camera_key": None, "camera_slug": None,
                   "argv": ck.helper_argv(ctx, PYAV_LIST, mid, "--repeats", n, "--gap-s", GAP_S, "--timeout-s",
                                          CALL_TIMEOUT_S, *(["--ffmpeg", ff] if mid.startswith("ffmpeg") else [])),
                   "timeout_s": method_timeout(n)})
    for cam in cams:
        if not cam.get("ds_path"):
            continue
        for mid in OPTION_METHODS:
            if mid.startswith("ffmpeg") and not ff:
                skipped[mid] = "ffmpeg CLI not on PATH"
                continue
            ms.append({"id": mid, "camera_key": cam["key"], "camera_slug": ck.cam_slug(cam),
                       "argv": ck.helper_argv(ctx, PYAV_LIST, mid, "--device", cam["ds_path"], "--repeats", n,
                                              "--gap-s", GAP_S, "--timeout-s", CALL_TIMEOUT_S,
                                              *(["--ffmpeg", ff] if mid.startswith("ffmpeg") else [])),
                       "timeout_s": method_timeout(n)})
    for m in ms:
        m["argv"] = [str(a) for a in m["argv"]]
    return ms, skipped


def streamer_spec(ctx, cam: dict, mode) -> dict:
    argv = [str(ctx.wincam), "capture", "--api", "mf", "--device", cam["mf_symlink"], "--width", mode.w, "--height",
            mode.h, "--fps", mode.fps_arg, "--subtype", "MJPG", "--seconds", 240, "--timeout-ms", 5000, "--out-dir",
            "{out_dir}", "--save", "none", "--stop-file", "{stop_file}"]
    return {"argv": [str(a) for a in argv], "first_frame_timeout_s": 25, "stop_timeout_s": 20}


def streamer_fault(doc: dict | None) -> dict | None:
    """The first device fault in a session's streamer runs (0x8007001F, an unreleasable reader, or a streamer killed
    at its stop timeout), whether or not it delivered a first frame; None otherwise. The session's argv names no
    device and the result has no measurements.cameras, so neither camcmd's fault scan nor the runner's backstop scan
    can see these: the test reports them to the fault gate itself."""
    for s in (doc or {}).get("streamer_runs") or []:
        f = suitectx.fault_signature(s.get("summary"), {"timed_out": (s.get("process") or {}).get("timed_out")},
                                     streaming=True)
        if f:
            return {**f, "streamer_index": s.get("index"), "started_ok": s.get("started_ok")}
    return None


# ------------------------------------------------------------------------------------------------------- analysis
def _read(p: str | None) -> str:
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace") if p else ""
    except OSError:
        return ""


def helper_doc(rec: dict) -> dict | None:
    obj, _ = suitectx.parse_json_stdout({"stdout": _read(rec.get("stdout_file"))})
    return obj


def _frames(path: str | None) -> list[dict]:
    return results.read_jsonl(Path(path)) if path else []


def call_disturbance(calls: list[dict], frames: list[dict], nominal_fps: float | None) -> list[dict]:
    """nograb.disturbance per call window; the baseline is the 2 s before the call, after the previous call ended
    (+200 ms) and after the stream's first 300 ms."""
    ts = [int(r["qpc_ns"]) for r in frames if r.get("qpc_ns") is not None]
    if not ts:
        return [{"disturbed": None, "measured": False, "why": ["no streamer frames"]} for _ in calls]
    bad = [int(r["qpc_ns"]) for r in frames if r.get("qpc_ns") is not None and (
        r.get("discontinuity") or r.get("soi") is False or r.get("eoi") is False)]
    out, prev_end = [], None
    for c in calls:
        t0, t1 = c.get("t_start_ns"), c.get("t_end_ns")
        if t0 is None or t1 is None:
            out.append({"disturbed": None, "measured": False, "why": ["no call times"]})
            continue
        b0 = max(ts[0] + 300_000_000, int(t0) - 2_000_000_000, (prev_end + 200_000_000) if prev_end else 0)
        d = nograb.disturbance(ts, (int(t0), int(t1)), baseline=(b0, int(t0) - 50_000_000), bad_frame_ts_ns=bad,
                               nominal_fps=nominal_fps)
        d["call"] = c.get("i")
        out.append(d)
        prev_end = int(t1)
    return out


def pipes_opened(samples: list[dict], t0: int, t1: int, baseline: list[dict], skip_key: str | None) -> dict:
    """Cameras (other than the streamed one) with an open isochronous pipe in a sample overlapping [t0, t1] that
    had none in the baseline samples."""
    base_active = {k for s in baseline for k, v in (s.get("cameras") or {}).items() if v.get("active")}
    opened: dict = {}
    n = 0
    for s in samples:
        ts, te = int(s.get("t_ns") or 0), int(s.get("t_end_ns") or s.get("t_ns") or 0)
        if te < t0 or ts > t1:
            continue
        n += 1
        for k, v in (s.get("cameras") or {}).items():
            if k == skip_key or k in base_active:
                continue
            if v.get("active"):
                opened.setdefault(k, []).append({"t_ns": ts, "alt": v.get("current_alt")})
    return {"samples_in_window": n, "opened": {k: len(v) for k, v in opened.items()},
            "baseline_active": sorted(base_active)}


def analyse_method(rec: dict, doc: dict, cond: str, nominal_fps: float | None, faulted_keys: list[str]) -> dict:
    p = rec.get("process") or {}
    h = helper_doc(rec) or {}
    calls = h.get("calls") or []
    hung = bool(h.get("hung")) or bool(p.get("timed_out"))
    el = [c.get("elapsed_ms") for c in calls if c.get("elapsed_ms") is not None]
    st = next((s for s in doc.get("streamer_runs") or []), None)
    dist = call_disturbance(calls, _frames((st or {}).get("frames_jsonl")), nominal_fps) if st else []
    t0 = min((c["t_start_ns"] for c in calls if c.get("t_start_ns")), default=p.get("t_start_ns"))
    t1 = max((c["t_end_ns"] for c in calls if c.get("t_end_ns")), default=p.get("t_end_ns"))
    pipes = pipes_opened(rec.get("topology_samples") or [], int(t0 or 0), int(t1 or 0),
                         doc.get("baseline_topology") or [], doc.get("stream_key"))
    disturbed = any(d.get("disturbed") for d in dist) or (rec.get("streamer_alive_after") is False)
    listed = [c.get("n_devices") if "n_devices" in c else c.get("option_lines") for c in calls]
    return {"condition": cond, "tested": True, "calls": len(calls), "hung": hung,
            "hung_call": next((c.get("i") for c in calls if c.get("hung")), None),
            "process_timed_out": p.get("timed_out"), "rc": p.get("rc"),
            "elapsed_ms": {"p50": statistics.median(el) if el else None, "max": max(el) if el else None,
                           "all": el},
            "listed": listed, "errors": [c.get("returned") or c.get("error") for c in calls][:3],
            "log_tail": (calls[-1].get("log_tail") or "")[-1500:] if calls else (rec.get("process") or {}).get(
                "stderr_tail"),
            "disturbance": dist if st else None, "disturbed": disturbed if st else None,
            "streamer_alive_after": rec.get("streamer_alive_after"),
            "pipes": pipes, "stream_started_on_idle_camera": bool(pipes["opened"]),
            "faulted_cameras_present": faulted_keys}


def analyse_session(doc: dict, cond: str, nominal_fps: float | None, faulted_keys: list[str]) -> list[dict]:
    out = []
    for rec in doc.get("methods") or []:
        if rec.get("skipped"):
            out.append({"id": rec["id"], "camera_key": rec.get("camera_key"), "condition": cond, "tested": False,
                        "untested_reason": rec["skipped"]})
            continue
        a = analyse_method(rec, doc, cond, nominal_fps, faulted_keys)
        a.update(id=rec["id"], camera_key=rec.get("camera_key"))
        out.append(a)
    return out


def rate_list(conds: list[dict], method: str) -> dict:
    """Rating text: touches but harmless / disturbs / hangs on a faulted camera (see the module docstring)."""
    meas = [c for c in conds if c.get("tested")]
    ev = {"method": method, "conditions": [{k: c.get(k) for k in ("condition", "camera_key", "tested", "hung",
                                                                   "disturbed", "stream_started_on_idle_camera",
                                                                   "elapsed_ms", "faulted_cameras_present",
                                                                   "untested_reason", "listed")} for c in conds],
          "touch": "FFmpeg dshow binds the capture filter (IMoniker::BindToObject) of every device to list its media "
                   "types (list_devices) / of the named device (list_options): inferred from FFmpeg's source, not "
                   "observable from user mode"}
    if not meas:
        return rating.untested("no condition measured: " + "; ".join(sorted({str(c.get('untested_reason'))
                                                                             for c in conds}))[:200], ev)
    hung = [c for c in meas if c.get("hung")]
    dist = [c for c in meas if c.get("disturbed")]
    pipes = [c for c in meas if c.get("stream_started_on_idle_camera")]
    crit = [rating._crit("every call returned within the bound", not hung,
                         [{"condition": c["condition"], "hung_call": c.get("hung_call")} for c in hung]),
            rating._crit("no frame gap, stop or bad frame in the streaming process during a call",
                         None if not any(c.get("disturbed") is not None for c in meas) else not dist,
                         [c["condition"] for c in dist]),
            rating._crit("no isochronous pipe opened on an idle camera during a call", not pipes,
                         [{"condition": c["condition"], "opened": c["pipes"]["opened"]} for c in pipes]),
            rating._crit("idle and streaming conditions measured",
                         # by prefix: the idle session is "idle_kiyo_wedged" when the Kiyo is wedged
                         any(str(c["condition"]).startswith("idle") for c in meas)
                         and any(str(c["condition"]).startswith("streaming:") for c in meas),
                         sorted({c["condition"] for c in meas}))]
    if hung:
        # list_devices (camera_key None) binds every device, so any faulted camera counts; list_options binds only
        # the named device, so its hang is "on a faulted camera" only when that camera is the faulted one
        on_fault = any(c.get("camera_key") in (c.get("faulted_cameras_present") or []) if c.get("camera_key")
                       else bool(c.get("faulted_cameras_present")) for c in hung)
        r = rating._result("no", crit, ev, "a call hung" + (" while a camera was faulted" if on_fault else ""))
        r["summary_label"] = "no (hangs on a faulted camera)" if on_fault else "no (hangs)"
        return r
    if dist or pipes:
        r = rating._result("no", crit, ev, "the listing disturbed a stream or opened a pipe")
        r["summary_label"] = "no (disturbs)"
        return r
    r = rating._result("partial", crit, ev, "touches but harmless: every call returned, nothing disturbed (it still "
                                            "binds every capture filter, a wedged camera included)")
    r["summary_label"] = "partial (touches but harmless)"
    return r


def verdicts_from(results_rows: list[dict], cameras: list[dict], skipped: dict) -> dict:
    v = {}
    for mid in DEVICE_METHODS:
        rows = [r for r in results_rows if r["id"] == mid]
        v[f"{GOAL}|all|{mid}"] = rate_list(rows, mid) if rows else rating.untested(skipped.get(mid) or "not run")
    for cam in cameras:
        for mid in OPTION_METHODS:
            rows = [r for r in results_rows if r["id"] == mid and r.get("camera_key") == cam["key"]]
            v[f"{GOAL}|{cam['key']}|{mid}"] = rate_list(rows, mid) if rows else \
                rating.untested(skipped.get(mid) or "not run")
    return v


# ------------------------------------------------------------------------------------------------------- run
def kiyo_state(ctx) -> dict:
    out = {}
    for cam in ctx.cameras:
        if not cam.get("is_kiyo"):
            continue
        f = ctx.camera_faulted(cam) if hasattr(ctx, "camera_faulted") else None
        j, r = ck.get_controls(ctx, cam, "ds", timeout_ms=3000, timeout_s=30) if cam.get("ds_path") else (None, {})
        na, hr = ce.not_answering(j, r)
        age, la = ctx.plug_in_age_s(cam) if hasattr(ctx, "plug_in_age_s") else (None, None)
        out[cam["key"]] = {"faulted": bool(f), "fault": f, "answering": not na, "hr": hr, "read": r,
                           "plug_in_age_s": age, "last_arrival": la,
                           "w_kiyo_onset": (getattr(ctx, "kiyo_state", {}) or {}).get(cam["key"]),
                           "wedged": bool(f) or na}
    return out


def run(ctx) -> dict:
    res = ck.new_result(ctx, TEST)
    arr0 = ck.arrivals_before(ctx)
    n = repeats(ctx)
    errors: list = []
    tdir = ctx.test_dir(TEST)
    raw = Path(ctx.raw_dir) / TEST
    desc_file = Path(ctx.out_dir) / "descriptors" / "descriptors.json"
    ff = shutil.which("ffmpeg")
    fcache: dict = {}
    cams = [{k: c.get(k) for k in ("key", "name", "instance_id")} for c in ctx.cameras]
    kst = kiyo_state(ctx)
    for k, s in kst.items():
        ctx.log(f"{TEST}: Kiyo {k}: wedged={s['wedged']} answering={s['answering']} hr={s['hr']} "
                f"age={s['plug_in_age_s']}")
    faulted_keys = [k for k, s in kst.items() if s["wedged"]] + [
        c["key"] for c in ctx.cameras if not c.get("is_kiyo") and hasattr(ctx, "camera_faulted")
        and ctx.camera_faulted(c)]
    sessions: dict = {}
    rows: list[dict] = []
    m_all, skipped = methods_for(ctx, ctx.cameras, ff, n)

    def run_session(label: str, cond: str, methods: list, stream_cam: dict | None, mode) -> dict | None:
        sdir = raw / label
        spec = {"label": label, "condition": cond, "cameras": cams, "stream_key": (stream_cam or {}).get("key"),
                "out_dir": str(sdir), "streamer": streamer_spec(ctx, stream_cam, mode) if stream_cam else None,
                "baseline_s": BASELINE_S, "settle_s": SETTLE_S,
                "descriptor_file": str(desc_file) if desc_file.exists() else None, "methods": methods,
                "sample": {"interval_s": 0.15}}
        sp = results.write_json(tdir / f"{label}_spec.json", spec)
        tmo = sum(m["timeout_s"] for m in methods) + (60 if stream_cam else 20) + len(methods) * (SETTLE_S + 2)
        ctx.log(f"{TEST}: session {label} ({len(methods)} methods, timeout {tmo:.0f} s)")
        r = ctx.camcmd([sys.executable, str(SESSION), str(sp)], timeout_s=tmo)
        doc, perr = suitectx.parse_json_stdout(r)
        sessions[label] = {"condition": cond, "stream_key": spec["stream_key"], "run": ck.run_brief(r),
                           "parse_error": perr, "session_file": None,
                           "mode": mode.text if mode else None}
        if doc is None:
            errors.append({"session": label, "error": perr, "rc": r.get("rc"), "timed_out": r.get("timed_out")})
            return None
        p = results.write_json(sdir / "session.json", doc)
        sessions[label]["session_file"] = str(p)
        sessions[label]["streamer_runs"] = [{k: s.get(k) for k in ("index", "started_ok", "summary")}
                                            for s in doc.get("streamer_runs") or []]
        return doc

    # idle (the Kiyo as found: if it is wedged, these calls are the faulted-camera case)
    cond_idle = "idle" + ("_kiyo_wedged" if any(s["wedged"] for s in kst.values()) else "")
    doc = run_session("idle", cond_idle, m_all, None, None)
    if doc is not None:
        rows += analyse_session(doc, cond_idle, None, faulted_keys)
    # one camera streaming at a time
    for cam in ctx.cameras:
        label = f"streaming_{ck.cam_slug(cam)}"
        cond = f"streaming:{cam['key']}"
        ms, _ = methods_for(ctx, [cam], ff, n)
        gated = ctx.camera_gated(cam) if hasattr(ctx, "camera_gated") else None
        if gated or (kst.get(cam["key"]) or {}).get("wedged") or not cam.get("mf_symlink"):
            why = ("untested: " + (ctx.fault_reason(cam) or "device fault")) if gated else \
                ("camera wedged (as found): its own stream cannot start" if cam["key"] in kst else "no MF symlink")
            sessions[label] = {"condition": cond, "skipped": why}
            rows += [{"id": m["id"], "camera_key": m.get("camera_key"), "condition": cond, "tested": False,
                      "untested_reason": why} for m in ms]
            continue
        fm, fread = ck.formats_checked(ctx, cam, fcache, TEST)
        if fread:
            # format read failed (not a scope exclusion); a hang / 0x8007001F is a device fault via the probe
            if fread.get("fault") and hasattr(ctx, "fault_reason"):
                why = "untested: " + (ctx.fault_reason(cam) or "device fault")
            else:
                why = f"untested ({fread['untested_reason']})"
            sessions[label] = {"condition": cond, "skipped": why, "format_read": fread}
            rows += [{"id": m["id"], "camera_key": m.get("camera_key"), "condition": cond, "tested": False,
                      "untested_reason": why} for m in ms]
            continue
        mode, scope = wa.scoped_720(ctx, ck.mjpeg_modes(fm))
        if mode is None:
            why = scope.get("untested_reason") or "no in-scope mode"
            sessions[label] = {"condition": cond, "skipped": why, "mode_scope": scope}
            rows += [{"id": m["id"], "camera_key": m.get("camera_key"), "condition": cond, "tested": False,
                      "untested_reason": why} for m in ms]
            continue
        doc = run_session(label, cond, ms, cam, mode)
        if doc is None:
            continue
        # also after a good start: a streamer that fails later (0x8007001F, a hang at reader release) is a fault too
        f = streamer_fault(doc)
        if f:
            sessions[label]["streamer_fault"] = f
            ctx.mark_fault(cam, test=TEST, mode=mode.text, code=f.get("code"), api="mf", stage=f.get("stage"),
                           cls=f.get("class"), source="w_pyav_list",
                           detail={"where": "streamer", "streamer_index": f.get("streamer_index"),
                                   "started_ok": f.get("started_ok")})
        if doc.get("streamer_failed"):
            s0 = (doc.get("streamer_runs") or [{}])[0].get("summary") or {}
            why = f"the streaming process did not deliver a first frame ({s0.get('error')})"[:300]
            rows += [{"id": m["id"], "camera_key": m.get("camera_key"), "condition": cond, "tested": False,
                      "untested_reason": why} for m in ms]
            continue
        rows += analyse_session(doc, cond, mode.fps, faulted_keys)
    v = verdicts_from(rows, ctx.cameras, skipped)
    for vk, vv in v.items():
        ctx.log(f"{TEST}: {vk}: {vv.get('summary_label') or vv.get('rating')}")
    meas = {"repeats_per_method": n, "call_timeout_s": CALL_TIMEOUT_S, "gap_s": GAP_S, "kiyo_as_found": kst,
            "faulted_cameras": faulted_keys, "sessions": sessions, "results": rows, "methods_skipped": skipped,
            "ffmpeg": ff, "arrivals": ck.arrivals_after(ctx, arr0),
            "thresholds": {"gap": f"> max({nograb.GAP_FACTOR_P50} x baseline p50, {nograb.GAP_FACTOR_MAX} x baseline "
                                  f"max, baseline max + {nograb.GAP_MIN_EXTRA_MS} ms)"}}
    return results.finish_result(res, measurements=meas, verdicts=v, errors=errors)


# ------------------------------------------------------------------------------------------------------- offline
def reanalyze(run_dir: Path) -> dict:
    """Re-analyse the stored sessions (session.json + method stdout files + streamer frames) with today's rules."""
    run_dir = Path(run_dir)
    d = json.loads((run_dir / f"{TEST}.json").read_text(encoding="utf-8"))
    m = d.get("measurements") or {}
    faulted = m.get("faulted_cameras") or []
    rows = [r for r in m.get("results") or [] if not r.get("tested")]
    for label, s in (m.get("sessions") or {}).items():
        if not s.get("session_file"):
            continue
        try:
            doc = json.loads(Path(s["session_file"]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        fps = None
        mt = s.get("mode")
        if mt and "@" in mt:
            try:
                fps = float(mt.split("@")[-1])
            except ValueError:
                fps = None
        rows += analyse_session(doc, s.get("condition"), fps, faulted)
    cams = [{"key": c.get("key")} for c in d.get("cameras") or []]
    v = verdicts_from(rows, cams, m.get("methods_skipped") or {})
    changes = [{"cell": k, "from": ((d.get("verdicts") or {}).get(k) or {}).get("rating"), "to": x["rating"]}
               for k, x in v.items() if ((d.get("verdicts") or {}).get(k) or {}).get("rating") != x["rating"]]
    return {"test": TEST, "reanalysis_of": str(run_dir / f"{TEST}.json"), "utc": results.utc_now_iso(),
            "verdicts": v, "changes": changes}


def _main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "--reanalyze":
        rd = Path(argv[1])
        out = reanalyze(rd)
        p = results.write_json(rd / "reanalysis" / f"{TEST}.json", out)
        print(json.dumps({"written": str(p), "changes": out["changes"]}, indent=1))
        return 0
    print("usage: w_pyav_list.py --reanalyze <run_dir>   (live runs go through run_suite.py)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
