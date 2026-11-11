"""W-FMT-NOGRAB: which method lists a camera's formats correctly WITHOUT grabbing it or starting a stream?

Plan section 6.2 (FMT-NOGRAB, Dom 2026-11-06); runs right after W-FMT. Per camera (the Kiyo included; a camera the
device-fault gate holds is recorded 'untested: device fault since <ts>'), every format-listing method runs under
three conditions, each condition one session of ``helpers/nograb_session.py`` under ONE camera lock:

| condition              | the camera is ...                                                                    |
| idle                   | not streamed by the suite (other apps may hold it: ``wincam activity`` is recorded)  |
| streaming_native       | streamed in another process through Media Foundation (``wincam capture``)            |
| streaming_second_api   | streamed in another process through DirectShow (``pyav_ds capture``, PyAV dshow)     |

The streams use the in-scope default mode (common/modescope.py: MJPG 1280x720@30 or the nearest in-scope mode).
A camera with no in-scope mode streams nothing: its two streaming conditions and the idle blocker are untested
(scope), and only the idle listing runs.

Methods (Windows):
- ``hub_ioctl``: USB descriptors through the parent hub (helpers/win_descriptors.py,
  IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION): no camera-driver involvement, no hold possible;
- ``mf``: ``wincam formats --api mf --hold-ms H``: ActivateObject + a converters-off source reader +
  GetNativeMediaType, never Start / ReadSample; the source and reader stay open H ms (HOLD_BEGIN / HOLD_END);
- ``ds``: ``wincam formats --api ds --hold-ms H``: BindToObject + IAMStreamConfig + GetFrameRateList, no graph,
  no Run; the filter stays bound H ms;
- ``ffmpeg``: ``ffmpeg -list_options true -f dshow -i video=@device_pnp_<path>`` (CLI; it prints only each caps
  entry's min and max rate, so discrete rates in between are expected to be missing);
- recorded, not implemented (rated 'no', camera "all"): ``opencv`` (no listing API; only set-and-try, which
  streams) and ``winrt`` (MediaCapture needs InitializeAsync, which grabs the camera).

Measured per method x condition: succeeded; completeness vs the USB descriptors (W-FMT's reference, every
format / size / rate, MJPEG and raw separately; common/nograb.compare); elapsed; disturbance of the other stream
(max frame interval and bad frames in the listing window vs the 2 s before; common/nograb.disturbance); stream /
bandwidth (idle: an open isochronous pipe of the camera in a win_topology sample while the method runs, before
the third-process open); blocking (idle: a 1-frame MF capture from a third process during the hold vs a control
capture without the method; a method without a hold is rerun with a concurrent capture). Rating per method and
camera: common.rating.rate_fmt_nograb (yes / partial / no), verdict key ``fmt_nograb|<camera>|<method>``.

Fixes from windows_results_20261106 section 11 (2026-11-08):
- reference: MF, DirectShow and ffmpeg are rated against the OS-exposed reference (the descriptor modes that MF or
  DirectShow list); descriptor modes no Windows API exposes are reported per camera as ``descriptor_only_modes``
  (the C930e's 2 YUY2 modes made MF and DS "no (incomplete)" for an OS deficit). The hub IOCTL is the reference
  method and stays rated against the descriptors (``reference_method``; its completeness is circular);
- hold coverage: before the main idle session (which starts the third-process open 0.6 s into the hold), the hold
  methods run once more with no third-process open, so the "starts no stream" sampler sees the whole hold;
  ``hold_coverage_fraction`` (blocker-free) and ``hold_coverage_fraction_with_blocker`` are reported, and an open
  pipe in either session counts as a started stream.

Standalone: ``uv run --python 3.12 --script tests/w_fmt_nograb.py --out-dir D [--reuse-discovery]`` (or through
run_suite.py --only W-FMT,W-FMT-NOGRAB).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _enum_util as U  # noqa: E402
import capkit as ck  # noqa: E402
import suitectx  # noqa: E402
import w_fmt  # noqa: E402
from common import nograb, rating, results  # noqa: E402

TEST_ID = "W-FMT-NOGRAB"
CONDITIONS = ("idle", "streaming_native", "streaming_second_api")
METHODS = ("hub_ioctl", "mf", "ds", "ffmpeg")
NOT_IMPLEMENTED = {
    "opencv": "cannot list without opening capture: OpenCV has no format-listing API; the only way is set-and-try "
              "(cap.set(W, H, FPS) then read back), which opens the device and starts a stream",
    "winrt": "cannot list without opening capture: Windows.Media.Capture.MediaCapture exposes "
             "VideoDeviceController.GetAvailableMediaStreamProperties only after InitializeAsync, which grabs the "
             "camera (MediaCaptureSharingMode.SharedReadOnly still activates the source through Frame Server)",
}
HOLD_MS = 2500
BLOCKER_DELAY_S = 0.6        # into the hold: after the pipe samples the third-process open would contaminate
DELAYED_OPEN_MS = 800.0      # a third-process first frame this much later than the control's, after the release
SESSION_TIMEOUT_S = 240.0


def hold_ms(ctx) -> int:
    return int(getattr(ctx.args, "nograb_hold_ms", None) or HOLD_MS)


def estimate_s(ctx) -> float:
    """Calibrated on Gerald 2026-11-06 (4 cameras, hold 2.5 s): 39-45 s per camera for the three sessions, plus the
    blocker-free idle hold session (two hold methods, ~hold + 2 s each)."""
    h = hold_ms(ctx) / 1000.0
    return 15 + (12 + 12 * h + 4 + 2 * (h + 2.0)) * len(ctx.cameras)


#: methods rated against the OS-exposed reference (descriptor modes that MF or DirectShow list): a descriptor mode
#: no Windows API exposes (the C930e's 2 YUY2 modes) is the OS's deficit, not the listing method's (11-06 B8)
OS_REFERENCE_METHODS = ("mf", "ds", "ffmpeg")
COVER_GAP_NS = 500_000_000      # pipe samples closer than this count as continuous coverage of the hold


def os_exposed_reference(ref: set, listed_by_os: set) -> tuple[set, set]:
    """(OS-exposed reference, descriptor-only modes): the descriptor modes that MF or DirectShow listed (matched with
    the W-FMT tolerance), and the rest."""
    r = nograb.normalize(ref)
    miss, _extra = nograb.match(r, nograb.normalize(listed_by_os), nograb.TOL_100NS, 0.0)
    return r - set(miss), set(miss)


def hold_coverage(rec: dict, samples: list[dict]) -> float | None:
    """Fraction of a method's hold (HOLD_BEGIN .. HOLD_END as seen) observed by pipe samples: sample windows merged
    when closer than COVER_GAP_NS, clipped to the hold. None without hold times."""
    hold = rec.get("hold") or {}
    a, b = hold.get("begin_seen_ns"), hold.get("end_seen_ns")
    if not a or not b or b <= a:
        return None
    iv = []
    for s in samples:
        ts = int(s.get("t_ns") or 0)
        te = int(s.get("t_end_ns") or 0) or ts + int(float(s.get("collect_ms") or 0) * 1e6)
        if te >= a and ts <= b:
            iv.append((max(ts, a), min(max(te, ts), b)))
    if not iv:
        return 0.0
    iv.sort()
    merged = [list(iv[0])]
    for s0, s1 in iv[1:]:
        if s0 - merged[-1][1] <= COVER_GAP_NS:
            merged[-1][1] = max(merged[-1][1], s1)
        else:
            merged.append([s0, s1])
    return round(sum(y - x for x, y in merged) / (b - a), 3)


def combine_started(*vals) -> bool | None:
    """stream_started over several sample sets: True if any is True, False if any is False, else None."""
    known = [v for v in vals if v is not None]
    if any(known):
        return True
    return False if known else None


# ============================================================================================================ parsing
OPT_RE = re.compile(r"(vcodec|pixel_format)=(\S+)\s+min s=(\d+)x(\d+) fps=([\d.]+)\s+max s=(\d+)x(\d+) fps=([\d.]+)")
PIN_RE = re.compile(r'Pin "([^"]*)"')


def parse_ffmpeg_list_options(text: str) -> tuple[set, dict]:
    """Modes from ``ffmpeg -list_options true -f dshow`` (each caps entry: min size+rate, max size+rate). Still pins
    are skipped. Returns (modes, info)."""
    modes, pins, cur = set(), {}, None
    n_lines = 0
    for line in (text or "").splitlines():
        pm = PIN_RE.search(line)
        if pm:
            cur = pm.group(1)
            pins.setdefault(cur, 0)
            continue
        m = OPT_RE.search(line)
        if not m:
            continue
        n_lines += 1
        if cur and re.search("still", cur, re.I):
            continue
        fcc = nograb.norm_fourcc(m.group(2))
        w1, h1, f1, w2, h2, f2 = int(m.group(3)), int(m.group(4)), float(m.group(5)), int(m.group(6)), \
            int(m.group(7)), float(m.group(8))
        for w, h, f in ((w1, h1, f1), (w2, h2, f2)):
            if f > 0:
                modes.add((fcc, w, h, nograb.interval_from_fps(f)))
        if cur is not None:
            pins[cur] += 1
    return modes, {"pins": pins, "option_lines": n_lines,
                   "note": "ffmpeg prints min and max rate per caps entry only (no IAMVideoControl rate list)"}


def _capture_modes(d: dict) -> set:
    return {x for r in d.values() if not re.search("STILL", str(r.get("category") or ""), re.I)
            for x in r.get("modes") or set()}


def reference_modes(desc_dev: dict | None) -> set:
    return w_fmt._union(w_fmt.descriptor_modes(desc_dev)) if desc_dev else set()


def _read(p: str | None) -> str:
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace") if p else ""
    except OSError:
        return ""


def _json_of(text: str):
    t = (text or "").strip()
    if not t:
        return None
    try:
        return json.loads(t)
    except ValueError:
        a, b = t.find("{"), t.rfind("}")
        if 0 <= a < b:
            try:
                return json.loads(t[a:b + 1])
            except ValueError:
                return None
    return None


def listed_modes(method: str, rec: dict) -> tuple[set | None, dict]:
    """(modes or None when the method produced no list, info)."""
    proc = rec.get("process") or {}
    out = _read(rec.get("stdout_file"))
    err = _read(rec.get("stderr_file"))
    info: dict = {"rc": proc.get("rc"), "timed_out": proc.get("timed_out"), "elapsed_s": proc.get("elapsed_s")}
    if method == "ffmpeg":
        modes, fi = parse_ffmpeg_list_options(err)
        info.update(fi)
        return (modes if modes else None), info
    obj = _json_of(out)
    if obj is None:
        info["error"] = "no JSON output"
        info["stderr_tail"] = err[-600:]
        return None, info
    if method == "hub_ioctl":
        dev = (obj.get("devices") or [None])[0]
        info["errors"] = (dev or {}).get("errors")
        info["requests"] = (dev or {}).get("requests")
        m = reference_modes(dev)
        return (m if m else None), info
    info["error"] = obj.get("error")
    info["stream_started_flag"] = obj.get("stream_started")
    info["hold"] = obj.get("hold")
    if method == "mf":
        m = _capture_modes(w_fmt.mf_modes(obj))
        info["synthesized_excluded"] = len(w_fmt._union(w_fmt.mf_modes(obj), "synthesized"))
    else:
        m = _capture_modes(w_fmt.ds_modes(obj))
    if obj.get("error") and not m:
        return None, info
    return (m if m else None), info


# ============================================================================================================ analysis
def _frames(path: str | None) -> list[dict]:
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
    except (OSError, TypeError):
        pass
    return rows


def _bad(row: dict) -> bool:
    if row.get("discontinuity"):
        return True
    if row.get("soi") is False:
        return True
    if row.get("eoi") is False:
        return True
    e = row.get("eoi_trailing_bytes")
    return isinstance(e, int) and e < 0


def method_disturbance(rec: dict, streamer: dict | None, nominal_fps: float | None) -> dict | None:
    if streamer is None:
        return None
    rows = _frames(streamer.get("frames_jsonl"))
    ts = [int(r["qpc_ns"]) for r in rows if r.get("qpc_ns") is not None]
    p = rec.get("process") or {}
    t0, t1 = p.get("t_start_ns"), p.get("t_end_ns")
    if not ts or t0 is None or t1 is None:
        return {"disturbed": None, "measured": False, "why": ["no streamer frames or method times"]}
    first = ts[0]
    b0 = max(first + 300_000_000, t0 - 2_000_000_000)
    base_rows = [r for r in rows if b0 <= int(r.get("qpc_ns") or 0) <= t0]
    jpeg_ok_base = [r for r in base_rows if not _bad(r)]
    check_jpeg = bool(base_rows) and len(jpeg_ok_base) >= 0.9 * len(base_rows)
    bad = [int(r["qpc_ns"]) for r in rows if check_jpeg and _bad(r) and r.get("qpc_ns") is not None]
    d = nograb.disturbance(ts, (int(t0), int(t1)), baseline=(b0, int(t0) - 50_000_000), bad_frame_ts_ns=bad,
                           nominal_fps=nominal_fps)
    d["jpeg_validity_checked"] = check_jpeg
    d["streamer_alive_after"] = rec.get("streamer_alive_after")
    if rec.get("streamer_alive_after") is False and d.get("disturbed") is False:
        d["disturbed"] = True
        d["why"] = list(d.get("why") or []) + ["streamer_exited"]
    return d


BLOCKER_TAIL_NS = 500_000_000   # the third-process open's pipe may close just after its process exits


def method_stream_samples(rec: dict) -> list[dict]:
    """Samples that overlap the method's run (snapshot start .. end of its collect) and do NOT overlap the
    third-process open (its process window plus BLOCKER_TAIL_NS: that open streams one frame and its pipe would be
    blamed on the method; live 2026-11-06, a 380 ms snapshot that started during the open was flagged clean because
    the flag was read after the collect). For hold methods the window ends at the hold end."""
    p = rec.get("process") or {}
    t0, t1 = p.get("t_start_ns") or 0, p.get("t_end_ns") or 0
    hold = rec.get("hold") or {}
    end = hold.get("end_seen_ns") or t1
    blk = rec.get("blocker") or {}
    b0, b1 = blk.get("t_start_ns"), blk.get("t_end_ns")
    out = []
    for s in rec.get("topology_samples") or []:
        ts = int(s.get("t_ns") or 0)
        te = int(s.get("t_end_ns") or 0) or ts + int(float(s.get("collect_ms") or 0) * 1e6)   # spans its collect
        if s.get("blocker_running"):
            continue
        if b0 is not None and b1 is not None and te >= int(b0) and ts <= int(b1) + BLOCKER_TAIL_NS:
            continue
        if te >= t0 and ts <= end:
            out.append(s)
    return out


def method_blocking(rec: dict, control: dict | None) -> dict:
    blk = rec.get("blocker")
    if not control:
        return {"blocked": None, "why": "no control open (not the idle condition, or the camera is gated)"}
    hold = rec.get("hold") or {}
    out = {"control_ok": control.get("ok"), "control_open_to_first_frame_ms": control.get("open_to_first_frame_ms"),
           "during_ok": None if blk is None else blk.get("ok"),
           "during_open_to_first_frame_ms": None if blk is None else blk.get("open_to_first_frame_ms"),
           "during_error": None if blk is None else blk.get("error")}
    after_release = None
    if blk is not None and hold.get("end_ns") and blk.get("first_frame_ns"):
        late = (blk.get("open_to_first_frame_ms") or 0) - (control.get("open_to_first_frame_ms") or 0)
        after_release = bool(blk["first_frame_ns"] > hold["end_ns"] and late > DELAYED_OPEN_MS)
        out["first_frame_after_hold_end"] = blk["first_frame_ns"] > hold["end_ns"]
        out["delay_vs_control_ms"] = round(late, 1)
        out["blocker_started_in_hold"] = bool(hold.get("begin_seen_ns") and blk.get("t_start_ns")
                                              and hold["begin_seen_ns"] <= blk["t_start_ns"] <= hold["end_seen_ns"])
    out["delayed_until_release"] = after_release
    out["blocked"] = nograb.blocked(control.get("ok"), None if blk is None else blk.get("ok"), after_release)
    if control.get("ok") is not True:
        out["why"] = "control open failed too (camera busy elsewhere?): blocking not testable"
    if not rec.get("hold"):
        out["note"] = "no hold: the third-process open ran concurrently with the method's whole run"
    return out


def _brief_samples(samples: list[dict]) -> list[dict]:
    return [{k: s.get(k) for k in ("t_ns", "active", "current_alt", "in_hold", "blocker_running", "error")}
            | {"iso_pipes": list(s.get("iso_pipes") or [])}
            for s in samples]


def analyse_session(doc: dict, ref: set, condition: str, nominal_fps: float | None) -> dict:
    """{method: condition record} for one session + session-level facts."""
    out: dict = {}
    streamers = {s.get("index"): s for s in doc.get("streamer_runs") or []}
    base_active = any(s.get("active") for s in doc.get("baseline_topology") or [])
    control = doc.get("control_blocker")
    by_id: dict = {}
    for rec in doc.get("methods") or []:
        by_id.setdefault(rec["id"], {})[rec.get("tag") or "main"] = rec
    for mid, recs in by_id.items():
        rec = recs.get("main") or {}
        if rec.get("skipped"):
            out[mid] = {"tested": False, "untested_reason": rec["skipped"]}
            continue
        modes, info = listed_modes(mid, rec)
        cmp = nograb.compare(ref, modes, rel_tol=nograb.REL_TOL if mid == "ffmpeg" else 0.0)
        samples = method_stream_samples(rec)
        st = streamers.get(rec.get("streamer_index"))
        dist = method_disturbance(rec, st, nominal_fps) if condition != "idle" else None
        blk_rec = recs.get("blocking") if not rec.get("hold") else rec
        blk = method_blocking(blk_rec or {}, control) if condition == "idle" else \
            {"blocked": None, "why": "not tested while another process streams the camera (a third open would test "
                                     "sharing, not the method)"}
        hold = rec.get("hold") or {}
        p = rec.get("process") or {}
        listing_ms = round((hold["begin_seen_ns"] - p["t_start_ns"]) / 1e6, 1) \
            if hold.get("begin_seen_ns") and p.get("t_start_ns") else None
        out[mid] = {
            "_listed": modes, "reference": "USB descriptors",
            "hold_coverage_fraction_with_blocker": hold_coverage(rec, samples) if rec.get("hold") else None,
            "tested": True, "succeeded": modes is not None and not p.get("timed_out"),
            "complete": cmp["complete"] if modes is not None else False, "exact": cmp["exact"],
            "elapsed_s": p.get("elapsed_s"), "listing_ms_before_hold": listing_ms,
            "disturbed": None if dist is None else dist.get("disturbed"),
            "stream_started": nograb.stream_started(samples, base_active) if condition == "idle" else None,
            "blocked": blk.get("blocked"),
            "comparison": cmp, "info": info, "disturbance": dist, "blocking": blk,
            "pipe_samples": {"n": len(samples), "active": sum(1 for s in samples if s.get("active")),
                             "baseline_active": base_active, "samples": _brief_samples(samples)[:20]},
            "hold": hold or None, "timed_out": p.get("timed_out"), "rc": p.get("rc"),
            "stdout_file": rec.get("stdout_file"), "stderr_file": rec.get("stderr_file")}
        if condition != "idle":
            # the camera already has an open pipe from the streamer: record whether the alt / pipe changed
            alts = sorted({s.get("current_alt") for s in samples if s.get("current_alt") is not None})
            balts = sorted({s.get("current_alt") for s in doc.get("baseline_topology") or []
                            if s.get("current_alt") is not None})
            out[mid]["pipe_change"] = {"baseline_alts": balts, "alts_during": alts,
                                       "changed": bool(alts and balts and alts != balts),
                                       "note": "stream_started is decided in the idle condition"}
    return out


def _streamer_ok(doc: dict) -> tuple[bool, str | None]:
    runs = doc.get("streamer_runs") or []
    if not runs:
        return False, "no streamer run"
    if not runs[0].get("started_ok"):
        s = runs[0].get("summary") or {}
        return False, f"the streaming process did not deliver a first frame ({(s.get('error') or {})})"[:300]
    return True, None


def session_fault(doc: dict | None) -> dict | None:
    """A device fault in the session's streamers / third-process opens (0x8007001F, unreleasable)."""
    for s in (doc or {}).get("streamer_runs") or []:
        f = suitectx.fault_signature(s.get("summary"), {"timed_out": (s.get("process") or {}).get("timed_out")},
                                     streaming=True)
        if f:
            return {**f, "where": f"streamer {s.get('index')}"}
    for b in [(doc or {}).get("control_blocker")] + [m.get("blocker") for m in (doc or {}).get("methods") or []]:
        if b and suitectx.fault_signature({"error": b.get("error"), "unreleasable": b.get("unreleasable")},
                                          {"timed_out": b.get("timed_out")}, streaming=True):
            f = suitectx.fault_signature({"error": b.get("error"), "unreleasable": b.get("unreleasable")},
                                         {"timed_out": b.get("timed_out")}, streaming=True)
            return {**f, "where": f"third-process open {b.get('tag')}"}
    return None


# ============================================================================================================ specs
def build_methods(ctx, cam: dict) -> tuple[list[dict], dict]:
    H = hold_ms(ctx)
    ms, skipped = [], {}
    if cam.get("instance_id"):
        ms.append({"id": "hub_ioctl", "argv": [sys.executable, str(U.HELPERS_DIR / "win_descriptors.py"), "--instance",
                                               cam["instance_id"]], "timeout_s": 25, "hold": False})
    else:
        skipped["hub_ioctl"] = "no USB instance id"
    for api, dev in (("mf", cam.get("mf_symlink")), ("ds", cam.get("ds_path"))):
        if dev:
            ms.append({"id": api, "argv": [str(ctx.wincam), "formats", "--api", api, "--device", dev, "--timeout-ms",
                                           8000, "--hold-ms", H], "timeout_s": 45 + H / 1000.0, "hold": True})
        else:
            skipped[api] = f"no {api} device link"
    ff = shutil.which("ffmpeg")
    if ff and cam.get("ds_path"):
        ms.append({"id": "ffmpeg", "argv": [ff, "-hide_banner", "-list_options", "true", "-f", "dshow", "-i",
                                            "video=" + (cam.get("ds_ffmpeg_name") or "@device_pnp_" + cam["ds_path"])],
                   "timeout_s": 30, "hold": False})
    else:
        skipped["ffmpeg"] = "ffmpeg CLI not on PATH" if not ff else "no DirectShow path"
    for m in ms:
        m["argv"] = [str(a) for a in m["argv"]]
    return ms, skipped


def streamer_spec(ctx, cam: dict, condition: str, mode: ck.Mode) -> dict | None:
    if condition == "idle":
        return None
    if condition == "streaming_native":
        if not cam.get("mf_symlink"):
            return None
        argv = [str(ctx.wincam), "capture", "--api", "mf", "--device", cam["mf_symlink"], "--width", mode.w,
                "--height", mode.h, "--fps", mode.fps_arg, "--subtype", "MJPG", "--seconds", 150, "--timeout-ms",
                5000, "--out-dir", "{out_dir}", "--save", "none", "--stop-file", "{stop_file}"]
    else:
        if not cam.get("ds_path"):
            return None
        argv = ck.helper_argv(ctx, ck.PYAV_DS, "capture", "--device", cam["ds_path"], "--width", mode.w, "--height",
                              mode.h, "--fps", mode.ds_fps, "--seconds", 150, "--timeout-ms", 5000, "--out-dir",
                              "{out_dir}", "--save", "none", "--stop-file", "{stop_file}")
    return {"argv": [str(a) for a in argv], "first_frame_timeout_s": 25, "stop_timeout_s": 20}


def blocker_spec(ctx, cam: dict, mode: ck.Mode) -> dict | None:
    if not cam.get("mf_symlink"):
        return None
    argv = [str(ctx.wincam), "capture", "--api", "mf", "--device", cam["mf_symlink"], "--width", mode.w, "--height",
            mode.h, "--fps", mode.fps_arg, "--subtype", "MJPG", "--frames", 1, "--timeout-ms", 4000, "--out-dir",
            "OUT_DIR", "--save", "none"]
    argv = [str(a) for a in argv]
    return {"argv": argv, "out_dir_arg_index": argv.index("OUT_DIR"), "timeout_s": 30,
            "delay_after_hold_s": BLOCKER_DELAY_S, "api": "mf", "mode": mode.text}


def idle_hold_session(ctx, cam: dict, slug: str, raw: Path, tdir: Path, desc_file: Path,
                      methods: list[dict]) -> tuple[dict, str | None]:
    """The idle condition's hold methods once more with NO third-process open, so the pipe sampler covers the whole
    hold. Returns ({method id: method record}, error)."""
    hold_methods = [m for m in methods if m.get("hold")]
    if not hold_methods:
        return {}, None
    sdir = raw / slug / "idle_no_blocker"
    spec = {"label": f"{slug}_idle_no_blocker", "condition": "idle",
            "camera": {k: cam.get(k) for k in ("key", "name", "mf_symlink", "ds_path", "instance_id")},
            "out_dir": str(sdir), "streamer": None, "baseline_s": 1.5, "settle_s": 1.0,
            "descriptor_file": str(desc_file) if desc_file.exists() else None, "methods": hold_methods,
            "blocker": None, "sample": {"interval_s": 0.12}}
    sp = tdir / f"{slug}_idle_no_blocker_spec.json"
    results.write_json(sp, spec)
    r = ctx.camcmd([sys.executable, str(U.HELPERS_DIR / "nograb_session.py"), str(sp)], timeout_s=SESSION_TIMEOUT_S)
    doc, perr = suitectx.parse_json_stdout(r)
    if doc is None:
        return {}, perr or f"session failed rc={r.get('rc')}"
    results.write_json(sdir / "session.json", doc)
    out = {}
    for rec in doc.get("methods") or []:
        if not rec.get("skipped") and (rec.get("tag") or "main") == "main":
            rec["_baseline_active"] = any(s.get("active") for s in doc.get("baseline_topology") or [])
            out[rec["id"]] = rec
    return out, None


def merge_idle_hold(ana: dict, nb_records: dict, doc: dict) -> None:
    """Idle results of the hold methods: stream_started over both sessions' samples (any open pipe counts) and the
    hold coverage of the blocker-free session (``hold_coverage_fraction``; the main session's is kept as
    ``hold_coverage_fraction_with_blocker``)."""
    base_active = any(s.get("active") for s in doc.get("baseline_topology") or [])
    for mid, rec in ana.items():
        nb = nb_records.get(mid)
        if not rec.get("tested") or nb is None:
            continue
        samples = method_stream_samples(nb)
        rec["hold_coverage_fraction"] = hold_coverage(nb, samples)
        started_nb = nograb.stream_started(samples, nb.get("_baseline_active"))
        rec["stream_started_no_blocker"] = started_nb
        rec["stream_started"] = combine_started(rec.get("stream_started"), started_nb)
        rec["pipe_samples_no_blocker"] = {"n": len(samples), "active": sum(1 for s in samples if s.get("active")),
                                          "baseline_active": nb.get("_baseline_active"),
                                          "samples": _brief_samples(samples)[:20]}
        if base_active and rec.get("stream_started") is False:
            rec["stream_started"] = None


def apply_os_reference(ref: set, results_by_method: dict) -> dict:
    """Re-rate MF / DS / ffmpeg completeness against the OS-exposed reference (descriptor modes MF or DS list) and
    report the descriptor-only modes; the hub IOCTL stays against the descriptors. Drops the transient listed sets."""
    listed_os: set = set()
    for mid in ("mf", "ds"):
        for r in (results_by_method.get(mid) or {}).values():
            if r.get("_listed"):
                listed_os |= set(r["_listed"])
    info: dict = {"applied": False}
    if listed_os and ref:
        os_ref, desc_only = os_exposed_reference(ref, listed_os)
        info = {"applied": True, "n_modes": len(os_ref), "n_descriptor_modes": len(nograb.normalize(ref)),
                "descriptor_only_modes": nograb.mode_texts(desc_only),
                "note": "descriptor modes that no Windows listing (MF or DirectShow) exposes are a camera / OS "
                        "finding; MF, DirectShow and ffmpeg completeness is rated against the modes Windows exposes"}
        for mid in OS_REFERENCE_METHODS:
            for r in (results_by_method.get(mid) or {}).values():
                if not r.get("tested"):
                    continue
                listed = r.get("_listed")
                cmp = nograb.compare(os_ref, listed, rel_tol=nograb.REL_TOL if mid == "ffmpeg" else 0.0)
                r["comparison_descriptors"] = r.get("comparison")
                r["comparison"] = cmp
                r["complete"] = cmp["complete"] if listed is not None else False
                r["exact"] = cmp["exact"]
                r["reference"] = "OS-exposed"
    for rs in results_by_method.values():
        for r in rs.values():
            r.pop("_listed", None)
    return info


# ============================================================================================================ run
def run(ctx) -> dict:
    def body(res, m, v, e):
        tdir = ctx.test_dir(TEST_ID)
        raw = Path(ctx.raw_dir) / TEST_ID
        desc = U.get_descriptors(ctx)
        desc_file = ctx.out_dir / "descriptors" / "descriptors.json"
        fcache: dict = {}
        per_cam: dict = {}
        m["hold_ms"] = hold_ms(ctx)
        m["mode_scope"] = ck.mode_scope(ctx).as_dict()
        m["activity_at_start"] = ck.wincam_activity(ctx)
        for cam in ctx.cameras:
            key = cam["key"]
            slug = ck.cam_slug(cam)
            crec: dict = {"name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"), "conditions": {}}
            per_cam[key] = crec
            ref = reference_modes(U.descriptor_for(desc, cam))
            crec["reference"] = {"source": "USB descriptors (W-FMT shared cache, hub IOCTL)", "n_modes": len(ref),
                                 "formats": sorted({x[0] for x in ref}),
                                 "per_class": {c: sum(1 for x in ref if nograb.fmt_class(x[0]) == c)
                                               for c in nograb.CLASSES}}
            methods, skipped = build_methods(ctx, cam)
            crec["methods"] = [mm["id"] for mm in methods]
            crec["methods_skipped"] = skipped
            gated = ctx.camera_gated(cam) if hasattr(ctx, "camera_gated") else None
            if gated:
                ut = ctx.fault_untested(cam)
                crec["gated"] = gated
                for mid in METHODS:
                    v[f"fmt_nograb|{key}|{mid}"] = ut
                ctx.log(f"{TEST_ID}: {cam.get('name')}: untested ({ctx.fault_reason(cam)})")
                continue
            if not ref:
                for mid in METHODS:
                    v[f"fmt_nograb|{key}|{mid}"] = rating.untested("no USB descriptor reference for this camera")
                e.append({"camera": key, "error": "no descriptor reference"})
                continue
            fm, _ = ck.get_formats(ctx, cam, fcache)
            advertised = ck.mjpeg_modes(fm)
            mode, scope = ck.scoped_default(ctx, advertised)
            no_scope = None
            if mode is None:
                # Dom 2026-11-08: only exactly-720-line >= 30 fps modes stream, no exception. Without one the two
                # streaming conditions and the idle condition's one-frame blocker are untested; the idle listing
                # (no stream) still runs.
                no_scope = scope.get("untested_reason") or "untested (scope): no MJPEG mode in the streaming scope"
                scope["note"] = ("no in-scope MJPEG mode: the streaming conditions and the idle blocker are untested; "
                                 "only the idle listing runs")
                crec["idle_blocker_untested"] = no_scope
            crec["stream_mode"] = mode.text if mode else None
            crec["mode_scope"] = scope
            crec["activity_before"] = ck.activity_for_camera(ctx, cam)
            blocker = blocker_spec(ctx, cam, mode) if mode else None
            results_by_method: dict = {mid: {} for mid in [mm["id"] for mm in methods]}
            fault_here = None
            nb_records: dict = {}
            for cond in CONDITIONS:
                if fault_here or ctx.camera_faulted(cam):
                    for mid in results_by_method:
                        results_by_method[mid][cond] = {"tested": False, "untested_reason":
                                                        "untested: " + (ctx.fault_reason(cam) or "device fault")}
                    continue
                if cond == "idle":
                    # a full blocker-free hold first: the main idle session's third-process open hides up to 1.9 s of
                    # the 2.5 s hold from the "starts no stream" pipe sampler (11-06 V3)
                    nb_records, nb_err = idle_hold_session(ctx, cam, slug, raw, tdir, desc_file, methods)
                    crec["conditions"]["idle_no_blocker"] = {"methods": sorted(nb_records), "error": nb_err}
                stream = streamer_spec(ctx, cam, cond, mode) if mode else None
                if cond != "idle" and stream is None:
                    for mid in results_by_method:
                        results_by_method[mid][cond] = {"tested": False,
                                                        "untested_reason": no_scope or "no streaming route"}
                    continue
                sdir = raw / slug / cond
                spec = {"label": f"{slug}_{cond}", "condition": cond,
                        "camera": {k: cam.get(k) for k in ("key", "name", "mf_symlink", "ds_path", "instance_id")},
                        "out_dir": str(sdir), "streamer": stream, "baseline_s": 1.5, "settle_s": 1.0,
                        "descriptor_file": str(desc_file) if desc_file.exists() else None, "methods": methods,
                        "blocker": blocker if cond == "idle" else None, "sample": {"interval_s": 0.12}}
                sp = tdir / f"{slug}_{cond}_spec.json"
                results.write_json(sp, spec)
                ctx.log(f"{TEST_ID}: {cam.get('name')}: {cond} ({len(methods)} methods)")
                r = ctx.camcmd([sys.executable, str(U.HELPERS_DIR / "nograb_session.py"), str(sp)],
                               timeout_s=SESSION_TIMEOUT_S)
                doc, perr = suitectx.parse_json_stdout(r)
                crec["conditions"][cond] = {"run": ck.run_brief(r), "parse_error": perr,
                                            "session_file": None}
                if doc is None:
                    e.append({"camera": key, "condition": cond, "error": perr, "rc": r.get("rc"),
                              "timed_out": r.get("timed_out")})
                    for mid in results_by_method:
                        results_by_method[mid][cond] = {"tested": False, "untested_reason": f"session failed: {perr}"}
                    continue
                results.write_json(sdir / "session.json", doc)
                crec["conditions"][cond]["session_file"] = str(sdir / "session.json")
                crec["conditions"][cond]["streamer_runs"] = [
                    {k: s.get(k) for k in ("index", "started_ok", "summary", "argv")} for s in doc.get("streamer_runs") or []]
                crec["conditions"][cond]["control_blocker"] = doc.get("control_blocker")
                crec["conditions"][cond]["events"] = doc.get("events")
                f = session_fault(doc)
                if f:
                    fault_here = f
                    ctx.mark_fault(cam, test=TEST_ID, mode=mode.text if mode else None, code=f.get("code"),
                                   api="mf" if cond != "streaming_second_api" else "ds", stage=f.get("stage"),
                                   cls=f.get("class"), source="w_fmt_nograb", detail={"where": f.get("where")})
                ok_stream, why = (True, None) if cond == "idle" else _streamer_ok(doc)
                if not ok_stream:
                    for mid in results_by_method:
                        results_by_method[mid][cond] = {"tested": False, "untested_reason": why}
                    continue
                crec["conditions"][cond]["baseline_pipe_active"] = any(
                    s.get("active") for s in doc.get("baseline_topology") or [])
                ana = analyse_session(doc, ref, cond, mode.fps if mode else None)
                if cond == "idle":
                    merge_idle_hold(ana, nb_records, doc)
                for mid, rec in ana.items():
                    results_by_method.setdefault(mid, {})[cond] = rec
            crec["os_exposed_reference"] = apply_os_reference(ref, results_by_method)
            crec["results"] = results_by_method
            # positive control for the pipe sampler: while the condition's streamer runs, the same win_topology
            # sample must show the camera's open isochronous pipe; if it never does, "no pipe while the method held
            # the device" (idle) proves nothing and stream_started becomes unmeasured
            seen = [crec["conditions"][c].get("baseline_pipe_active") for c in ("streaming_native",
                                                                               "streaming_second_api")
                    if c in crec["conditions"] and (crec["conditions"][c].get("streamer_runs") or [{}])[0].get(
                        "started_ok")]
            validated = True if any(seen) else (False if seen else None)
            crec["pipe_sampler_validated"] = validated
            if validated is False:
                for mid, conds_ in results_by_method.items():
                    idle_r = conds_.get("idle") or {}
                    if idle_r.get("stream_started") is False:
                        idle_r["stream_started"] = None
                        idle_r["stream_started_note"] = ("not determinable: the pipe sampler never saw this camera's "
                                                         "pipe while the condition streamer ran")
            for mid in METHODS:
                if mid not in results_by_method:
                    v[f"fmt_nograb|{key}|{mid}"] = rating.untested(skipped.get(mid) or "method not run")
                    continue
                conds = {c: {kk: r.get(kk) for kk in ("tested", "untested_reason", "succeeded", "complete",
                                                       "disturbed", "stream_started", "blocked", "elapsed_s")}
                         for c, r in results_by_method[mid].items()}
                vv = rating.rate_fmt_nograb(conds, method=mid)
                vv["evidence"]["completeness"] = {
                    c: {cls: {kk: (r.get("comparison") or {}).get("per_class", {}).get(cls, {}).get(kk)
                              for kk in ("n_reference", "n_listed", "n_missing", "n_extra", "missing")}
                        for cls in ("mjpeg", "raw")} for c, r in results_by_method[mid].items() if r.get("tested")}
                vv["evidence"]["pipe_sampler_validated"] = crec.get("pipe_sampler_validated")
                idle_r = results_by_method[mid].get("idle") or {}
                vv["evidence"]["hold_coverage_fraction"] = idle_r.get("hold_coverage_fraction")
                osr = crec.get("os_exposed_reference") or {}
                if mid in OS_REFERENCE_METHODS and osr.get("applied"):
                    vv["evidence"]["reference"] = "OS-exposed (descriptor modes that MF or DirectShow list)"
                    vv["evidence"]["descriptor_only_modes"] = osr.get("descriptor_only_modes")
                elif mid == "hub_ioctl":
                    vv["evidence"]["reference"] = "USB descriptors"
                    vv["evidence"]["reference_method"] = True
                    vv["evidence"]["reference_note"] = (
                        "the hub IOCTL is the reference method: its completeness repeats the W-FMT descriptor read "
                        "(circular); what it shows is that the read works while streaming, without disturbance or a "
                        "stream")
                if fault_here:
                    vv["evidence"]["device_fault_during_test"] = fault_here
                v[f"fmt_nograb|{key}|{mid}"] = vv
                ctx.log(f"{TEST_ID}: {cam.get('name')} {mid}: {vv['rating']}"
                        + (f" ({vv.get('note')})" if vv.get("note") else ""))
        for mid, why in NOT_IMPLEMENTED.items():
            v[f"fmt_nograb|all|{mid}"] = rating.rate_fmt_nograb({}, no_reason=why, method=mid)
        m["cameras"] = per_cam
        m["methods"] = {"hub_ioctl": "helpers/win_descriptors.py (IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION)",
                        "mf": "wincam formats --api mf --hold-ms (ActivateObject + GetNativeMediaType, no Start)",
                        "ds": "wincam formats --api ds --hold-ms (BindToObject + IAMStreamConfig + GetFrameRateList, "
                              "no Run)",
                        "ffmpeg": "ffmpeg -list_options true -f dshow -i video=@device_pnp_<path>",
                        **{k: "not implemented: " + x for k, x in NOT_IMPLEMENTED.items()}}
        m["conditions"] = {"idle": "no suite stream (blocking test: 1-frame MF capture from a third process during "
                                   "the hold vs a control capture)",
                           "streaming_native": "wincam capture (MF) in another process, in-scope default mode",
                           "streaming_second_api": "pyav_ds capture (DirectShow via PyAV) in another process"}
        m["thresholds"] = {"gap": f"> max({nograb.GAP_FACTOR_P50} x baseline p50, {nograb.GAP_FACTOR_MAX} x baseline "
                                  f"max, baseline max + {nograb.GAP_MIN_EXTRA_MS} ms)",
                           "delayed_open_ms": DELAYED_OPEN_MS, "interval_tolerance_100ns": nograb.TOL_100NS,
                           "ffmpeg_rel_tol": nograb.REL_TOL}
        m["activity_at_end"] = ck.wincam_activity(ctx)
    return U.guarded(ctx, TEST_ID, body)


if __name__ == "__main__":
    sys.exit(U.standalone(run, TEST_ID))
