# /// script
# requires-python = ">=3.12"
# dependencies = ["comtypes>=1.4"]
# ///
"""pymf: pure-Python Media Foundation probe (comtypes + ctypes, no compiled extension). CLI mirroring wincam.exe.

    uv run --script research/usb_cameras/suite/windows/pymf/cli.py <subcommand> [options]

    list                                                   MF device list (no ActivateObject)
    formats  --device X [--timeout-ms T] [--out F]         every native MF type on every stream (no stream started)
    controls --device X [--read-only | --set id=v,... [--set-flags auto|manual] [--restore]] [--timeout-ms T]
    capture  --device X --width W --height H --fps F [--subtype MJPG] (--frames N | --seconds S) --timeout-ms T
             --out-dir D [--save none|all|every:K] [--stop-file F]
    cycle    --device X --width W --height H --fps F --cycles K --frames N --timeout-ms T --out D
             [--alt-width W2 --alt-height H2 --alt-fps F2] [--gap-ms G]
    common:  --watchdog-ms MS (default derived from the request, as wincam), --api mf (accepted; MF only)
    offline: --url FILE_URL instead of --device (formats / capture / controls on a local media file; opens no
             camera; used by tests/test_pymf_offline.py)

JSON field names follow wincam (README "Subcommands"): same header (tool "pymf"), same per-step records, same
frames.jsonl / cycles.jsonl / summary.json fields. Exit codes: 0 ok, 2 usage, 3 device not found, 4 camera
failure, 5 timeout (a bounded call, unreleasable, or the watchdog). Not ported: DirectShow (``--api ds``),
``activity``, ``formats --hold-ms``, ``capture --schedule / --controls-before``, and cycle's
IMFSensorActivityMonitor (``in_use_by_other`` is always null).

Safety (plan 6.1): never restarts / disables a device, never writes the registry, never touches a driver. Every
blocking camera call is bounded (pymf/bounded.py); the watchdog prints what it has and exits 5; a process with an
abandoned (hung) thread ends with os._exit, skipping MFShutdown / CoUninitialize like wincam's TerminateProcess.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if sys.path and Path(sys.path[0] or ".").resolve() == HERE:
    sys.path.pop(0)                       # do not let pymf's module names shadow anything
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from pymf import VERSION, bounded  # noqa: E402
from pymf import com as C  # noqa: E402
from pymf import mf  # noqa: E402
from pymf import parse as P  # noqa: E402


class G:
    subcommand = ""
    argv: list[str] = []
    utc_started = ""
    timeout_ms = 5000
    out_file = ""
    partial_file = ""


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def wlog(msg: str) -> None:
    print(f"[pymf] {msg}", file=sys.stderr, flush=True)


def header(sub: str) -> dict:
    return {"tool": "pymf", "version": VERSION, "subcommand": sub, "utc_started": G.utc_started, "pid": os.getpid(),
            "argv": G.argv, "timeout_ms": G.timeout_ms}


def dumps(j: dict) -> str:
    return json.dumps(j, indent=1, default=str, allow_nan=False) if _finite(j) else json.dumps(_clean(j), indent=1,
                                                                                                default=str)


def _finite(o) -> bool:
    try:
        json.dumps(o, allow_nan=False, default=str)
        return True
    except ValueError:
        return False


def _clean(o):
    if isinstance(o, float):
        return o if o == o and o not in (float("inf"), float("-inf")) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def write_text(path: str, text: str) -> bool:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return True
    except OSError:
        return False


def emit(j: dict, rc: int) -> int:
    """wincam emit(): finish the header, write to --out (list/formats/controls) or stdout."""
    j["utc_finished"] = utc_now()
    j["exit_code"] = rc
    j["abandoned_threads"] = bounded.abandoned_threads()
    s = dumps(j) + "\n"
    if G.out_file:
        if write_text(G.out_file, s):
            wlog(f"wrote {G.out_file}")
        else:
            wlog(f"cannot write {G.out_file}; printing to stdout")
            sys.stdout.write(s)
    else:
        sys.stdout.write(s)
    sys.stdout.flush()
    return rc


def finish(rc: int) -> None:
    """End the process. With an abandoned (hung) camera thread, exit at once (no MFShutdown / CoUninitialize, which
    could block on the hung object); otherwise shut MF down first. os._exit in both cases, so interpreter
    finalisation never runs comtypes __del__ against objects MF threads may still use."""
    sys.stdout.flush()
    sys.stderr.flush()
    if bounded.abandoned_threads() == 0:
        try:
            C.MFShutdown()
        except Exception:  # noqa: BLE001
            pass
    os._exit(rc)


def start_watchdog(ms: float) -> None:
    def fire() -> None:
        time.sleep(ms / 1000.0)
        j = header(G.subcommand)
        j.update(watchdog_fired=True, watchdog_ms=ms, stage=mf.STAGE["stage"])
        j["error"] = {"class": "timeout", "reason": "process watchdog expired; a camera call hung beyond every "
                      "per-call timeout", "stage": mf.STAGE["stage"]}
        with mf.PARTIAL_LOCK:
            j["partial"] = json.loads(json.dumps(mf.PARTIAL, default=str))
        j["utc_finished"] = utc_now()
        j["exit_code"] = 5
        s = dumps(j) + "\n"
        if G.partial_file:
            write_text(G.partial_file, s)
        elif G.out_file:
            write_text(G.out_file, s)
        sys.stdout.write(s)
        wlog(f"watchdog fired after {ms:.0f} ms in stage {mf.STAGE['stage']}; exit 5")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(5)
    threading.Thread(target=fire, name="pymf-watchdog", daemon=True).start()


def set_partial(**kw) -> None:
    with mf.PARTIAL_LOCK:
        mf.PARTIAL.update(kw)


# ============================================================================================================ list
def cmd_list() -> int:
    j = header("list")
    j["note"] = "enumeration only: no IMFActivate::ActivateObject"
    t0 = time.perf_counter_ns()
    mf.set_stage("enumerate")
    r = bounded.call(G.timeout_ms, lambda ctl: mf.enum_mf())
    t1 = time.perf_counter_ns()
    if r.timed_out or r.value is None:
        j["mf"] = {"hr": None, "hr_name": "timeout" if r.timed_out else "exception", "elapsed_ms": (t1 - t0) / 1e6,
                   "devices": []}
        j["error"] = mf.error_obj("enumerate", P.E_FAIL, r.timed_out)
        return emit(j, 5 if r.timed_out else 4)
    hr, devs = r.value
    j["mf"] = {"hr": P.hr_hex(hr), "hr_name": P.hr_name(hr), "elapsed_ms": (t1 - t0) / 1e6,
               "devices": [{"index": d["index"], "friendly_name": d["name"], "symlink": d["symlink"],
                            "usb": P.parse_usb_ids(d["symlink"]), "match_key": P.norm_link(d["symlink"])}
                           for d in devs]}
    mf.release_devices(devs)
    j["ds"] = None
    j["ds_note"] = "pymf has no DirectShow path (wincam list --api ds covers it)"
    j["elapsed_ms"] = (time.perf_counter_ns() - t0) / 1e6
    j["error"] = None
    return emit(j, 0 if not P.failed(hr) else 4)


# ============================================================================================================ source
def open_source(a, j: dict, steps: list) -> tuple[int, dict | None]:
    """Resolve --device (or --url) and activate it. Returns (rc, holder {src, act}); rc != 0 means emit now."""
    if a.url:
        mf.set_stage("resolve_url")
        r = mf.resolve_url(a.url, G.timeout_ms)
        hr, src = r.value if r.value else (P.E_FAIL, None)
        steps.append(mf.step_rec("resolve_url", hr, r.ms, r.timed_out, r.exc))
        j["device"] = {"url": a.url}
        if r.timed_out or P.failed(hr) or src is None:
            j["error"] = mf.error_obj("resolve_url", hr, r.timed_out)
            return (5 if r.timed_out else 4), None
        return 0, {"src": src, "act": None}
    rc, dev = mf.resolve_mf(a.device, G.timeout_ms, j)
    if rc:
        return rc, None
    mf.set_stage("activate")
    r = mf.activate(dev["act"], G.timeout_ms)
    hr, src = r.value if r.value else (P.E_FAIL, None)
    steps.append(mf.step_rec("activate", hr, r.ms, r.timed_out, r.exc))
    j["activate_ms"] = r.ms
    if r.timed_out or P.failed(hr) or src is None:
        j["error"] = mf.error_obj("activate", hr, r.timed_out)
        return (5 if r.timed_out else 4), None
    return 0, {"src": src, "act": dev["act"]}


# ============================================================================================================ formats
def cmd_formats(a) -> int:
    j = header("formats")
    j["api"] = "mf"
    steps: list = []
    rc, holder = open_source(a, j, steps)
    if rc:
        j["steps"] = steps
        return emit(j, rc)
    src = holder["src"]
    mf.set_stage("presentation_descriptor")
    pd = bounded.call(G.timeout_ms, lambda ctl: mf.presentation_streams(src))
    phr, streams = pd.value if pd.value else (P.E_FAIL, [])
    steps.append(mf.step_rec("create_presentation_descriptor", phr, pd.ms, pd.timed_out, pd.exc))
    if pd.timed_out:
        j["error"] = mf.error_obj("create_presentation_descriptor", P.E_FAIL, True)
        j["steps"] = steps
        return emit(j, 5)
    j["streams"] = streams
    mf.set_stage("native_types")

    def nt(ctl):
        hr, rd = mf.make_reader(src)
        if P.failed(hr) or rd is None:
            return hr, []
        try:
            return 0, mf.native_types(rd)
        finally:
            C.release(rd)
    r = bounded.call(G.timeout_ms, nt)
    nhr, rs = r.value if r.value else (P.E_FAIL, [])
    steps.append(mf.step_rec("reader_native_types", nhr, r.ms, r.timed_out, r.exc))
    if r.timed_out:
        j["error"] = mf.error_obj("reader_native_types", P.E_FAIL, True)
        j["steps"] = steps
        return emit(j, 5)
    j["reader_streams"] = rs
    j["stream_started"] = False
    src = None
    sh, hung = mf.shutdown_mf(holder, G.timeout_ms)
    steps += sh
    j["steps"] = steps
    if P.failed(nhr):
        j["error"] = mf.error_obj("reader_native_types", nhr, False)
        return emit(j, 4)
    if hung:
        j["error"] = mf.error_obj("shutdown", P.E_FAIL, True)
        return emit(j, 5)
    j["error"] = None
    return emit(j, 0)


# ============================================================================================================ controls
def cmd_controls(a) -> int:
    j = header("controls")
    j["api"] = "mf"
    j["read_only"] = bool(a.read_only or not a.set)
    steps: list = []
    t0 = time.perf_counter_ns()
    rc, holder = open_source(a, j, steps)
    if rc:
        j["steps"] = steps
        return emit(j, rc)
    mf.set_stage("controls")
    flags = 1 if a.set_flags == "auto" else 2
    rc = mf.run_controls(holder["src"], j, bool(a.read_only), a.set or "", flags, bool(a.restore), G.timeout_ms)
    if rc == 5:                                   # never touch a hung source again
        j["steps"] = steps
        j["elapsed_ms"] = (time.perf_counter_ns() - t0) / 1e6
        return emit(j, 5)
    sh, hung = mf.shutdown_mf(holder, G.timeout_ms)
    steps += sh
    if hung:
        j["error"] = mf.error_obj("shutdown", P.E_FAIL, True)
        rc = 5
    j["steps"] = steps
    j["elapsed_ms"] = (time.perf_counter_ns() - t0) / 1e6
    j.setdefault("error", None)
    return emit(j, rc)


# ============================================================================================================ capture
def timings(s: mf.Session) -> dict:
    return {"enumerate_ms": s.enumerate_ms, "activate_ms": s.activate_ms, "reader_ms": s.reader_ms,
            "settype_ms": s.settype_ms, "first_frame_ms": s.first_frame_ms,
            "open_to_first_frame_ms": s.open_to_first_ms, "flush_ms": s.flush_ms,
            "reader_release_ms": s.reader_release_ms, "shutdown_ms": s.shutdown_ms,
            "shutdown_object_ms": s.shutdown_object_ms, "close_ms": s.close_ms}


def cmd_capture(a) -> int:
    j = header("capture")
    j["api"] = "mf"
    od = Path(a.out_dir)
    od.mkdir(parents=True, exist_ok=True)
    G.partial_file = str(od / "summary.json")
    mode = {"subtype": a.subtype, "w": a.width, "h": a.height, "fps": a.fps}
    save = a.save
    j["requested"] = {"subtype": a.subtype, "width": a.width, "height": a.height, "fps": a.fps,
                      "frames": a.frames or None, "seconds": a.seconds if a.seconds else None, "save": save}
    j["out_dir"] = str(od)
    target = a.url
    if not a.url:
        rc, dev = mf.resolve_mf(a.device, G.timeout_ms, j)
        if rc:
            write_text(G.partial_file, dumps(j))
            return emit(j, rc)
        target = dev["symlink"]
        C.release(dev["act"])
    else:
        j["device"] = {"url": a.url}
    st = mf.StreamState(a.width, a.height, a.frames or 0)
    st.jsonl = open(od / "frames.jsonl", "w", encoding="utf-8", newline="\n")
    if save != "none":
        st.mjpeg = open(od / "frames.mjpeg", "wb")
        st.save_mode = 1 if save == "all" else 2
        st.save_every = 1 if save == "all" else max(1, int(save.split(":", 1)[1]))
    s = mf.Session()
    set_partial(stage="opening", device=target)
    opened = mf.open_session(s, target, mode, st, G.timeout_ms, url=bool(a.url))
    ok = opened and mf.wait_first(s, G.timeout_ms)
    cu0, ck0 = C.proc_cpu_s()
    cpu_t0 = time.perf_counter_ns()
    cb0 = st.callback_ns_total
    stream_timeout = stopped_by_file = False
    if ok:
        mf.set_stage("streaming")
        while True:
            now = time.perf_counter_ns()
            with st.mu:
                first_ns, progress_ns, frames, err, eos = st.first_ns, st.progress_ns, st.frames, st.err, st.eos
            since_first_ms = (now - first_ns) / 1e6
            if err is not None or eos:
                ok = False
                s.fail("streaming", err if err is not None else P.MF_E_END_OF_STREAM, False)
                break
            if a.frames and frames >= a.frames:
                break
            if a.seconds and since_first_ms >= a.seconds * 1000.0:
                break
            if a.stop_file and os.path.exists(a.stop_file):
                stopped_by_file = True
                break
            if (now - progress_ns) / 1e6 > G.timeout_ms:
                ok = False
                stream_timeout = True
                s.fail("streaming", P.E_FAIL, True)
                break
            st.ev_sample.wait(0.05)
            st.ev_sample.clear()
            if (frames & 31) == 0:
                set_partial(stage="streaming", frames=frames)
    cu1, ck1 = C.proc_cpu_s()
    cpu_t1 = time.perf_counter_ns()
    cb1 = st.callback_ns_total
    mf.close_session(s, G.timeout_ms)
    st.jsonl.close()
    st.jsonl = None
    if st.mjpeg is not None:
        st.mjpeg.close()
        st.mjpeg = None
    with st.mu:
        j.setdefault("device", {})
        if not a.url:
            j["device"]["friendly_name"] = s.name or j["device"].get("friendly_name")
        j["negotiated"] = s.negotiated
        j["steps"] = s.steps
        j["timings"] = timings(s)
        j["frames"] = {"total": st.frames, "ok": st.ok_frames, "soi_eoi_ok": st.soi_eoi, "sof0_size_match": st.sof_match,
                       "with_uvc_metadata": st.with_meta, "with_capture_metadata_attr": st.with_capmeta,
                       "stream_ticks": st.ticks, "null_samples": st.nulls, "discontinuities": st.discont,
                       "bytes_total": st.bytes, "saved": st.saved, "reader_flag_counts": dict(st.flag_counts)}
        span = (st.last_ns - st.first_ns) / 1e9 if st.frames > 1 else 0.0
        j["duration_s"] = span
        j["fps_measured"] = (st.frames - 1) / span if span > 0 else 0.0
        j["metadata"] = {"uvc_pts_present": st.with_meta > 0,
                         "note": "UVC PTS/SCR appear only when MetadataBufferSizeInKB0 is set on this device instance "
                                 "(tier 1, optional); absence is normal"}
        win = (cpu_t1 - cpu_t0) / 1e9
        cpu = {"user_s": cu1 - cu0, "kernel_s": ck1 - ck0, "window_s": win,
               "pct_of_one_core": 100.0 * ((cu1 - cu0) + (ck1 - ck0)) / win if win > 0 else 0.0,
               "method": "GetProcessTimes over the streaming window",
               "callback_s": (cb1 - cb0) / 1e9,
               "callback_note": "wall time spent inside the Python OnReadSample (GIL held), streaming window"}
        tu, tk = C.proc_cpu_s()
        cpu["process_total_s"] = tu + tk
        j["cpu"] = cpu
        if st.err_exc:
            j["callback_exception"] = st.err_exc
    j["schedule"] = []
    if a.stop_file:
        j["stop_file"] = a.stop_file
        j["stopped_by_stop_file"] = stopped_by_file
    j["unreleasable"] = s.unreleasable
    j["ok"] = bool(ok and not s.stage_failed)
    j["error"] = s.error()
    out_rc = 0
    if s.stage_failed:
        out_rc = 5 if (s.timed_out or stream_timeout or s.unreleasable) else (4 if s.found else 3)
    j["files"] = {"frames_jsonl": str(od / "frames.jsonl"),
                  "frames_mjpeg": str(od / "frames.mjpeg") if save != "none" else None}
    copy = dict(j, utc_finished=utc_now(), exit_code=out_rc, abandoned_threads=bounded.abandoned_threads())
    write_text(G.partial_file, dumps(copy) + "\n")
    return emit(j, out_rc)


# ============================================================================================================ cycle
def cmd_cycle(a) -> int:
    j = header("cycle")
    j["api"] = "mf"
    od = Path(a.out)
    od.mkdir(parents=True, exist_ok=True)
    G.partial_file = str(od / "summary.json")
    mode = {"subtype": a.subtype, "w": a.width, "h": a.height, "fps": a.fps}
    alt = None
    if a.alt_width or a.alt_height or a.alt_fps:
        alt = {"subtype": a.subtype, "w": a.alt_width, "h": a.alt_height, "fps": a.alt_fps}
    ms = (lambda m: P.mode_str(m["subtype"], m["w"], m["h"], m["fps"]))
    j["requested"] = {"mode": ms(mode), "alt_mode": ms(alt) if alt else None, "cycles": a.cycles,
                      "frames_per_cycle": a.frames, "gap_ms": a.gap_ms}
    j["out_dir"] = str(od)
    j["release_order"] = ("stop reads -> IMFSourceReader::Flush (wait OnFlush) -> reader Release -> "
                          "IMFMediaSource::Shutdown -> IMFActivate::ShutdownObject; device re-enumerated every cycle")
    target = a.url
    if not a.url:
        rc, dev = mf.resolve_mf(a.device, G.timeout_ms, j)
        if rc:
            write_text(G.partial_file, dumps(j))
            return emit(j, rc)
        target = dev["symlink"]
        C.release(dev["act"])
    j["activity_monitor"] = {"available": False, "note": "IMFSensorActivityMonitor is not ported to pymf; "
                                                         "in_use_by_other is null"}
    ok_n = fail_n = timeouts = hung_setup = 0
    unreleasable = False
    ff, act_ms, close_ms, o2f, fps_v = [], [], [], [], []
    by_stage: dict[str, int] = {}
    by_class: dict[str, int] = {}
    run = longest = after_fail = recovered = 0
    prev_fail = False
    with open(od / "cycles.jsonl", "w", encoding="utf-8", newline="\n") as cj:
        for i in range(a.cycles):
            m = alt if (alt and i % 2 == 1) else mode
            st = mf.StreamState(m["w"], m["h"], a.frames)
            s = mf.Session()
            c0 = time.perf_counter_ns()
            good = mf.open_session(s, target, m, st, G.timeout_ms, url=bool(a.url)) and mf.wait_first(s, G.timeout_ms)
            if good:
                mf.set_stage("cycle_frames")
                while True:
                    st.ev_sample.wait(0.02)
                    st.ev_sample.clear()
                    with st.mu:
                        if st.frames >= a.frames:
                            break
                        if st.err is not None:
                            good = False
                            s.fail("streaming", st.err, False)
                            break
                        if st.eos:
                            good = False
                            s.fail("streaming", P.MF_E_END_OF_STREAM, False)
                            break
                        if (time.perf_counter_ns() - st.progress_ns) / 1e6 > G.timeout_ms:
                            good = False
                            s.fail("streaming", P.E_FAIL, True)
                            break
            mf.close_session(s, G.timeout_ms)
            err = s.error()
            cyc_ok = good and not s.stage_failed
            with st.mu:
                frames, frames_ok, with_meta = st.frames, st.ok_frames, st.with_meta
                # delivered rate of this cycle, as wincam 1.2: (frames - 1) / (last - first arrival), QPC at
                # callback entry
                span = (st.last_ns - st.first_ns) / 1e9 if frames > 1 else 0.0
            cyc_fps = (frames - 1) / span if span > 0 else None
            r = {"i": i, "mode": ms(m), "ok": cyc_ok, "stage_failed": s.stage_failed or None,
                 "hr": None if not s.stage_failed or s.timed_out or s.hr is None else P.hr_hex(s.hr),
                 "hr_name": None if not s.stage_failed else ("timeout" if s.timed_out else P.hr_name(s.hr or 0)),
                 "error_class": err["class"] if err else None, "timed_out": s.timed_out,
                 "enumerate_ms": s.enumerate_ms, "activate_ms": s.activate_ms, "reader_ms": s.reader_ms,
                 "settype_ms": s.settype_ms, "first_frame_ms": s.first_frame_ms,
                 "open_to_first_frame_ms": s.open_to_first_ms, "frames": frames, "frames_ok": frames_ok,
                 "with_uvc_metadata": with_meta, "fps_measured": cyc_fps, "duration_s": span if span > 0 else None,
                 "raw": str(m["subtype"]).upper() != "MJPG",
                 "negotiated_subtype": (s.negotiated or {}).get("subtype"),
                 "likely_mf_synthesized": (s.negotiated or {}).get("likely_mf_synthesized"),
                 "close_ms": s.close_ms, "flush_ms": s.flush_ms,
                 "reader_release_ms": s.reader_release_ms, "shutdown_ms": s.shutdown_ms,
                 "shutdown_object_ms": s.shutdown_object_ms, "in_use_by_other": None, "unreleasable": s.unreleasable,
                 "negotiated_ok": s.negotiated.get("readback_ok"), "t_start_qpc_ns": c0, "utc": utc_now(),
                 "steps": s.steps}
            cj.write(json.dumps(_clean(r), separators=(",", ":"), default=str) + "\n")
            cj.flush()
            if cyc_ok:
                ok_n += 1
                ff.append(s.first_frame_ms)
                o2f.append(s.open_to_first_ms)
                if cyc_fps is not None:
                    fps_v.append(cyc_fps)
                if prev_fail:
                    recovered += 1
                run = 0
            else:
                fail_n += 1
                run += 1
                longest = max(longest, run)
                by_stage[s.stage_failed] = by_stage.get(s.stage_failed, 0) + 1
                if err:
                    by_class[err["class"]] = by_class.get(err["class"], 0) + 1
                if s.timed_out:
                    timeouts += 1
                if s.timed_out and s.stage_failed in ("enumerate", "activate", "reader_create", "set_type",
                                                      "read_sample_issue", "resolve_url"):
                    hung_setup += 1
            if prev_fail:
                after_fail += 1
            prev_fail = not cyc_ok
            if s.activate_ms >= 0:
                act_ms.append(s.activate_ms)
            if s.close_ms >= 0:
                close_ms.append(s.close_ms)
            set_partial(cycles_done=i + 1, ok=ok_n, failed=fail_n)
            wlog(f"cycle {i + 1}/{a.cycles} {ms(m)}: " + ("ok" if cyc_ok else
                 f"FAIL {s.stage_failed} {'timeout' if s.timed_out else P.hr_name(s.hr or 0)}"))
            if s.unreleasable:
                unreleasable = True
                break
            if hung_setup >= 2:
                break
            if a.gap_ms and i + 1 < a.cycles:
                time.sleep(a.gap_ms / 1000.0)
    done = ok_n + fail_n
    j["summary"] = {"cycles_requested": a.cycles, "cycles_run": done, "ok": ok_n, "failed": fail_n,
                    "timeouts": timeouts, "success_rate": ok_n / done if done else 0.0,
                    "longest_failure_run": longest, "cycles_after_a_failure": after_fail,
                    "recovered_after_failure": recovered, "first_frame_ms_p50": P.pct(ff, 50),
                    "first_frame_ms_p95": P.pct(ff, 95), "first_frame_ms_max": max(ff) if ff else None,
                    "first_frame_within_2s": sum(1 for v in ff if v <= 2000.0),
                    "fps_measured_p50": P.pct(fps_v, 50), "fps_measured_min": min(fps_v) if fps_v else None,
                    "open_to_first_frame_ms_p50": P.pct(o2f, 50), "activate_ms_p50": P.pct(act_ms, 50),
                    "close_ms_p50": P.pct(close_ms, 50), "close_ms_max": max(close_ms) if close_ms else None,
                    "failures_by_stage": by_stage, "failures_by_class": by_class, "unreleasable": unreleasable,
                    "stopped_after_hung_setups": hung_setup >= 2}
    j["files"] = {"cycles_jsonl": str(od / "cycles.jsonl")}
    out_rc = 5 if (unreleasable or hung_setup >= 2) else (4 if fail_n else 0)
    j["error"] = None
    if out_rc == 5:
        j["error"] = {"class": "timeout", "reason": "a reader or source could not be released (unreleasable)"
                      if unreleasable else "two setup steps hung; stopped"}
    copy = dict(j, utc_finished=utc_now(), exit_code=out_rc, abandoned_threads=bounded.abandoned_threads())
    write_text(G.partial_file, dumps(copy) + "\n")
    return emit(j, out_rc)


# ============================================================================================================ main
class _Parser(argparse.ArgumentParser):
    def error(self, message):  # noqa: D102 - argparse hook
        raise ValueError(message)


def build_parser() -> argparse.ArgumentParser:
    ap = _Parser(prog="pymf", description=__doc__.split("\n")[0], add_help=True)
    ap.add_argument("subcommand", choices=["list", "formats", "controls", "capture", "cycle"])
    ap.add_argument("--api", default="mf", choices=["mf"])
    ap.add_argument("--device", default="")
    ap.add_argument("--url", default="", help="offline self-test: a local media file URL instead of --device")
    ap.add_argument("--out", default="")
    ap.add_argument("--out-dir", dest="out_dir", default="")
    ap.add_argument("--timeout-ms", dest="timeout_ms", type=float, default=None)
    ap.add_argument("--watchdog-ms", dest="watchdog_ms", type=float, default=0)
    ap.add_argument("--read-only", dest="read_only", action="store_true")
    ap.add_argument("--set", default="")
    ap.add_argument("--set-flags", dest="set_flags", default="manual", choices=["auto", "manual"])
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--width", type=int, default=0)
    ap.add_argument("--height", type=int, default=0)
    ap.add_argument("--fps", type=float, default=0.0)
    ap.add_argument("--subtype", default="MJPG")
    ap.add_argument("--frames", type=int, default=0)
    ap.add_argument("--seconds", type=float, default=0.0)
    ap.add_argument("--save", default="none")
    ap.add_argument("--stop-file", dest="stop_file", default="")
    ap.add_argument("--cycles", type=int, default=10)
    ap.add_argument("--alt-width", dest="alt_width", type=int, default=0)
    ap.add_argument("--alt-height", dest="alt_height", type=int, default=0)
    ap.add_argument("--alt-fps", dest="alt_fps", type=float, default=0.0)
    ap.add_argument("--gap-ms", dest="gap_ms", type=int, default=0)
    return ap


def usage_error(msg: str) -> int:
    j = header(G.subcommand or "?")
    j["error"] = {"class": "usage", "reason": msg}
    wlog(f"usage error: {msg}")
    return emit(j, 2)


def validate(a) -> str | None:
    """wincam main()'s argument checks. Returns the usage error text or None."""
    sc = a.subcommand
    if sc != "list" and not (a.device or a.url):
        return "--device required"
    if a.set:
        try:
            P.parse_sets(a.set, 1 if a.set_flags == "auto" else 2)
        except ValueError as e:
            return str(e)
    if sc in ("capture", "cycle"):
        if not a.width or not a.height or a.fps <= 0:
            return "--width --height --fps required"
        if a.timeout_ms is None:
            return "--timeout-ms required"
        if not P.subtype_guid_text(a.subtype):
            return "bad --subtype"
    if sc == "capture":
        if bool(a.frames) == bool(a.seconds):
            return "give exactly one of --frames / --seconds"
        if not a.out_dir:
            return "--out-dir required"
        if not (a.save in ("none", "all") or (a.save.startswith("every:") and a.save[6:].isdigit()
                                              and int(a.save[6:]) > 0)):
            return "--save none|all|every:K"
    if sc == "cycle":
        if not a.out:
            return "--out DIR required"
        if a.cycles <= 0 or a.frames <= 0:
            return "--cycles K and --frames N required"
        if (a.alt_width or a.alt_height or a.alt_fps) and not (a.alt_width and a.alt_height and a.alt_fps > 0):
            return "--alt-width --alt-height --alt-fps go together"
    return None


def main(argv: list[str] | None = None) -> int:
    G.utc_started = utc_now()
    G.argv = [sys.argv[0]] + list(sys.argv[1:] if argv is None else argv)
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0 if args else 2
    if args[0] == "--version":
        print(VERSION)
        return 0
    G.subcommand = args[0]
    try:
        a = build_parser().parse_args(args)
    except ValueError as e:
        return usage_error(str(e))
    G.timeout_ms = int(a.timeout_ms) if a.timeout_ms is not None else 5000
    msg = validate(a)
    if msg:
        return usage_error(msg)
    if a.subcommand in ("list", "formats", "controls"):
        G.out_file = a.out
    hr = C.MFStartup(C.MF_VERSION, C.MFSTARTUP_FULL) & 0xFFFFFFFF
    if hr:
        wlog(f"MFStartup failed {P.hr_hex(hr)}")
    wd = a.watchdog_ms
    sc = a.subcommand
    if sc == "list":
        start_watchdog(wd or 60000)
        return cmd_list()
    if sc == "formats":
        start_watchdog(wd or G.timeout_ms * 10 + 30000)
        return cmd_formats(a)
    if sc == "controls":
        start_watchdog(wd or G.timeout_ms * 12 + 60000)
        return cmd_controls(a)
    if sc == "capture":
        dur_ms = (a.frames / a.fps * 1000.0 * 3) if a.frames else a.seconds * 1000.0
        start_watchdog(wd or dur_ms + G.timeout_ms * 12.0 + 30000)
        return cmd_capture(a)
    per = a.frames / min(a.fps, a.alt_fps if a.alt_fps else a.fps) * 1000.0 * 2 + G.timeout_ms * 10.0 + a.gap_ms
    start_watchdog(wd or min(per * a.cycles + 30000, 4.0e9))
    return cmd_cycle(a)


if __name__ == "__main__":
    rc = 4
    try:
        rc = main()
    except Exception as e:  # noqa: BLE001 - mirror wincam's crash filter: one JSON line, exit 4
        import traceback
        print(json.dumps({"tool": "pymf", "crash": True, "exception": f"{type(e).__name__}: {e}",
                          "traceback": traceback.format_exc()[-2000:], "stage": mf.STAGE["stage"], "exit_code": 4}))
        rc = 4
    finish(rc)
