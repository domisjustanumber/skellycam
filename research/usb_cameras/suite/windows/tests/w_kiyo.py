"""W-KIYO: does the Razer Kiyo Pro stop answering control requests, when, and how (plan section 6.2 KIYO).

For every camera flagged ``is_kiyo`` by discovery (VID:PID 1532:0E05; a label only: the Kiyo is in every other test
too), poll ``wincam controls --read-only`` through MF and through DirectShow every 10 s, each call with a short
timeout (``--timeout-ms 3000``, process bound 20 s, under camlock). Two ways to run it:

- **background** (the suite default, analysis cyc_kiyo B7): run_suite starts ``start_background(ctx)`` right after
  discovery and calls ``finish(ctx, poller)`` after the last test, so the polls cover the whole suite and the
  Kiyo's onset is caught with its plug-in age and the test that was running. Polls wait for the camera lock, so
  they never overlap another camera command (a poll may be late while a long command holds the lock;
  ``lock_wait_s`` and the scheduled time are recorded).
- **foreground** (``--only W-KIYO``): ``run(ctx)`` polls for ``--kiyo-minutes`` (10; quick 2).

Recorded per poll: time, scheduled time, plug-in age (LastArrivalDate re-read every round, so a replug shows as a
re-arrival), the test running at that moment, exit code, error HRESULT/class, number of supported controls,
exposure value, call time, lock wait, and for a failing poll EVERY failing control with its full HRESULT dict
(iam_get_range, iam_get, ks_basicsupport, ks_get) and path (B2/N2: wincam initialises a never-called HRESULT to
E_NOINTERFACE 0x80004002, so ``iam_get`` alone is misleading; ``not_called_codes`` marks that value). Raw wincam JSON
of the first poll, of every state change and of every 30th failing poll goes to <raw>/W-KIYO/. Each poll round
also records vendor software that may talk to the camera (RazerAppEngine / Synapse / LogiTune ... from
``tasklist``) and, per Kiyo, the processes that hold or stream it right now from ``wincam activity``
(IMFSensorActivityMonitor: pid, image name, streaming flag per camera symbolic link, plus the privacy ConsentStore's
apps in use; it opens NO camera and runs without the camera lock, so it also sees who holds the Kiyo while another
test streams). Changes are logged as ``activity_changes`` and every poll carries ``activity_processes`` (a trailing
``*`` = streaming). Also READ-ONLY: the power plan's USB selective suspend / USB 3 LPM settings and the
device's ``Device Parameters``. The suite never changes the power plan (attended item A4).

Onset record (also in ctx.kiyo_state -> run_suite.json ``kiyo_onset`` and summary.md): first failing poll per API
(utc, plug-in age, running test, codes, vendor processes), ``failed_from_first_poll`` (the onset predates the
window), and answering->failing / failing->answering transitions. A poll whose failing controls report
ERROR_GEN_FAILURE (0x8007001F) marks the camera faulted (ctx.mark_fault, source kiyo_poller) once per episode, so
the suite's device-fault gate skips its streaming work from the next test on (each test re-probes it first).

Fix N1: ``plug_in_age_at_start_s`` is the age at the FIRST poll (it used to be computed after the loop).
Fixes from windows_results_20261106 section 11 (2026-11-08):
- a poll's ``utc`` is when the query RAN (wincam's ``utc_started``, after the camera-lock wait; fallback request time
  + lock wait), with ``utc_requested`` kept; the plug-in age, LastArrivalDate, ``problem_code`` / ``present``
  (CfgMgr) and the activity / vendor-process reads are taken right after the round's polls, and the age is computed
  at the poll's run time (the 11-06 polls were stamped up to 456 s before they ran);
- a late round is not followed by back-to-back catch-up rounds: ``next_due = max(next_due + interval, now)``
  (``late_s`` per poll);
- tools/camlock.py serves waiters first come, first served (ticket lock), so the poller is no longer starved behind
  back-to-back test commands;
- a poll whose camera-lock wait timed out (camlock rc 75 behind a long command, e.g. a 400-cycle W-CYC variant that
  holds the lock for > 20 min) made no camera call: it is kept as ``lock_busy`` (``lock_busy_per_api``) and is never
  a first failure, a transition, a device fault or part of the verdict.
Offline re-analysis of a finished run's W-KIYO.json: ``python w_kiyo.py --reanalyse <run_dir>``.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
from common import rating, results  # noqa: E402

TEST = "W-KIYO"
USB_SUBGROUP = "2a737441-1930-4402-8d77-b2bebba308a3"
SETTINGS = {"48e6b7a6-50f5-4782-a5d4-53bb8f07e226": "usb_selective_suspend",
            "d4e98f31-5ffe-4ce1-be31-1b38b384c009": "usb3_link_power_management",
            "0853a681-27c8-4100-a2fd-82013e970683": "hub_selective_suspend_timeout_ms"}
INTERVAL_S = 10.0
POLL_TIMEOUT_MS = 3000
POLL_TIMEOUT_S = 20.0
BACKGROUND_MAX_H = 10.0          # safety bound for a background poller nobody stops
OK_HR = "0x00000000"
NOT_CALLED_HR = "0x80004002"     # wincam's initial value for a call that was never made (E_NOINTERFACE)
DEVICE_ERROR_HR = "0x8007001F"
VENDOR_PATTERNS = {"razer": r"razer|synapse", "logitech": r"logi|lghub|lvui"}
HR_FIELDS = ("iam_get_range", "iam_get", "ks_basicsupport", "ks_get")


def minutes(ctx) -> float:
    return float(ck.arg(ctx, "kiyo_minutes", 10.0, 2.0))


def estimate_s(ctx) -> float:
    if getattr(ctx, "kiyo_poller", None) is not None:
        return 5.0
    n = sum(1 for c in ctx.cameras if c.get("is_kiyo"))
    return n * minutes(ctx) * 60 + 5


def power_settings() -> dict:
    """powercfg /qh SCHEME_CURRENT <USB subgroup> (read-only)."""
    try:
        r = subprocess.run(["powercfg", "/qh", "SCHEME_CURRENT", USB_SUBGROUP], capture_output=True, text=True,
                           timeout=20)
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}
    out: dict = {"raw_rc": r.returncode}
    cur = None
    names: dict = {}
    for line in r.stdout.splitlines():
        s = line.strip()
        if s.startswith("Power Scheme GUID:"):
            out["scheme"] = s.split(":", 1)[1].strip()
        if s.startswith("Power Setting GUID:"):
            g = s.split(":", 1)[1].strip().split()[0]
            cur = SETTINGS.get(g, g)
            names = {}
        elif s.startswith("Possible Setting Index:") and cur:
            idx = int(s.split(":", 1)[1].strip())
            names["_last"] = idx
        elif s.startswith("Possible Setting Friendly Name:") and cur and "_last" in names:
            names[names.pop("_last")] = s.split(":", 1)[1].strip()
        elif s.startswith("Current AC Power Setting Index:") and cur:
            v = int(s.split(":", 1)[1].strip(), 16)
            out.setdefault(cur, {})["ac"] = {"index": v, "name": names.get(v)}
        elif s.startswith("Current DC Power Setting Index:") and cur:
            v = int(s.split(":", 1)[1].strip(), 16)
            out.setdefault(cur, {})["dc"] = {"index": v, "name": names.get(v)}
    return out


def _age_s(last_arrival) -> float | None:
    import suitectx  # noqa: PLC0415
    return suitectx.age_s(last_arrival)


def _age_s_at(last_arrival, utc: str | None) -> float | None:
    """Seconds between LastArrivalDate and ``utc`` (the time the poll ran); now when ``utc`` is unknown."""
    import suitectx  # noqa: PLC0415
    return suitectx.age_s(last_arrival, now=_parse_utc(utc))


def vendor_processes(ctx) -> dict:
    """{'razer': [{name, pid}], 'logitech': [...]} from tasklist (enumeration only, bounded)."""
    try:
        r = ctx.run(["tasklist", "/fo", "csv", "/nh"], timeout_s=20)
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}
    found: dict = {k: [] for k in VENDOR_PATTERNS}
    for row in csv.reader(io.StringIO(r.get("stdout") or "")):
        if len(row) < 2:
            continue
        for k, pat in VENDOR_PATTERNS.items():
            if re.search(pat, row[0], re.I):
                found[k].append({"name": row[0], "pid": int(row[1]) if row[1].isdigit() else row[1]})
    return {k: v for k, v in found.items() if v}


def _vendor_sig(v: dict) -> list[str]:
    return sorted(f"{p['name']}:{p['pid']}" for lst in (v or {}).values() if isinstance(lst, list) for p in lst)


# ============================================================================================================ one poll
def analyse_controls(j: dict | None, r: dict) -> dict:
    """The answer of one ``wincam controls --read-only``: ok, failing controls with their full HRESULT dicts."""
    tab = ck.control_table(j)
    err = (j or {}).get("error") or {}
    failing, answered = [], []
    for c in (j or {}).get("controls", []) or []:
        if not c.get("supported"):
            continue
        hr = c.get("hr") or {}
        # wincam >= 2026-11-06 emits get_ok / get_hr (the GET actually made) and null for calls never made;
        # older JSON: answered when the IAM or KS GET returned S_OK.
        got = c.get("get_ok") if isinstance(c.get("get_ok"), bool) else \
            (hr.get("iam_get") == OK_HR or hr.get("ks_get") == OK_HR)
        if got:
            answered.append(c.get("key") or c.get("name"))
        else:
            failing.append({"key": c.get("key"), "name": c.get("name"), "via": c.get("via"),
                            "get_hr": c.get("get_hr"), "get_hr_name": c.get("get_hr_name"),
                            "hr": {k: hr.get(k) for k in HR_FIELDS if k in hr} or hr})
    codes = sorted({str(v) for f in failing for v in [*(f["hr"] or {}).values(), f.get("get_hr")]
                    if v not in (None, OK_HR)})
    real = [c for c in codes if c != NOT_CALLED_HR]
    dna = bool((j or {}).get("device_not_answering"))
    ok = bool(j) and r.get("rc") == 0 and not err and len(tab) > 0 and not failing and not dna
    dev_err = DEVICE_ERROR_HR in codes or str(err.get("hr") or "").upper() == DEVICE_ERROR_HR.upper() or \
        err.get("class") == "device_error"
    return {"ok": ok, "supported": len(tab), "exposure": (tab.get("exposure") or {}).get("value"),
            "exposure_flags": (tab.get("exposure") or {}).get("flags_names"), "failing_controls": failing,
            "answered_controls": answered, "codes": codes, "real_codes": real,
            "not_called_codes": NOT_CALLED_HR in codes, "device_error": dev_err, "device_not_answering": dna,
            "get_ok_count": (j or {}).get("get_ok_count"), "get_failed_count": (j or {}).get("get_failed_count"),
            "error_hr": err.get("hr"), "error_name": err.get("hr_name"), "error_class": err.get("class"),
            "error_stage": err.get("stage")}


def _utc_plus(utc: str | None, seconds: Any) -> str | None:
    try:
        t = _dt.datetime.fromisoformat(str(utc).replace("Z", "+00:00"))
        return (t + _dt.timedelta(seconds=float(seconds or 0))).isoformat()
    except (TypeError, ValueError):
        return utc


def _parse_utc(utc: str | None) -> _dt.datetime | None:
    try:
        t = _dt.datetime.fromisoformat(str(utc).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)


def poll_once(ctx, cam: dict, api: str, raw_path: Path | None = None) -> dict:
    """One ``wincam controls --read-only`` under camlock. ``utc`` is when the query RAN: wincam's own
    ``utc_started`` (after the camera-lock wait), else the request time + the lock wait; ``utc_requested`` is when
    the poll asked for the lock (the 11-06 run stamped polls up to 456 s before they ran)."""
    t_req = results.utc_now_iso()
    t0 = time.monotonic()
    j, r = ck.get_controls(ctx, cam, api, timeout_ms=POLL_TIMEOUT_MS, timeout_s=POLL_TIMEOUT_S)
    a = analyse_controls(j, r)
    lock_busy = bool(r.get("lock_timed_out"))
    if lock_busy:
        # the camera-lock wait timed out behind another test's long command (a 400-cycle W-CYC variant holds the
        # lock for > 20 min): no camera call was made, so this is "not polled", never "the Kiyo did not answer"
        a["ok"] = None
    ran = (j or {}).get("utc_started") if isinstance(j, dict) else None
    utc = ran or _utc_plus(t_req, r.get("lock_wait_s"))
    p = {"utc": utc, "utc_requested": t_req,
         "time_basis": "wincam utc_started" if ran else "request time + camera-lock wait",
         "api": api, "rc": r.get("rc"), "timed_out": r.get("timed_out"),
         "elapsed_s": round(time.monotonic() - t0, 3), "lock_wait_s": r.get("lock_wait_s"),
         "activate_ms": (j or {}).get("activate_ms"), "no_json": j is None, "lock_busy": lock_busy,
         "camlock_rc": r.get("camlock_rc"),
         "stderr_tail": r.get("stderr_tail") if j is None else None, **a}
    if raw_path is not None and j is not None:
        p["_raw"] = j
    return p


def compact(p: dict) -> dict:
    """The poll row kept in the result JSON (failing-control detail only where it changes; see first_failure)."""
    return {k: p.get(k) for k in ("i", "api", "utc", "utc_requested", "t_s", "sched_t_s", "late_s", "ok", "rc",
                                  "timed_out", "lock_busy", "elapsed_s", "lock_wait_s", "plug_in_age_s", "test",
                                  "problem_code", "present", "supported", "exposure", "codes", "device_error",
                                  "error_hr", "error_class")} | \
        {"n_failing": len(p.get("failing_controls") or []), "n_answered": len(p.get("answered_controls") or [])}


# ============================================================================================================ poller
class KiyoPoller:
    """Polls every Kiyo's MF and DS controls every ``interval_s`` on its own thread until stop() (or max_s)."""

    def __init__(self, ctx, cams: list[dict], interval_s: float = INTERVAL_S, max_s: float | None = None,
                 mode: str = "background") -> None:
        self.ctx = ctx
        self.cams = cams
        self.interval_s = interval_s
        self.max_s = max_s if max_s is not None else BACKGROUND_MAX_H * 3600
        self.mode = mode
        self.stop_ev = threading.Event()
        self.th: threading.Thread | None = None
        self.t_start: float | None = None
        self.utc_started: str | None = None
        self.utc_stopped: str | None = None
        self.state: dict = {c["key"]: {"polls": [], "first_failure": {}, "transitions": [], "last_ok": {},
                                       "arrivals": [], "vendor_changes": [], "activity_changes": [],
                                       "fault_marked": False,
                                       "plug_in_age_at_start_s": None, "last_arrival_at_start": None,
                                       "first_poll_ok": {}} for c in cams}
        self.errors: list = []
        self.raw = Path(ctx.raw_dir) / TEST
        self._vendor_last: list | None = None
        self._activity_last: dict = {}

    # ---------------------------------------------------------------- lifecycle
    def start(self) -> "KiyoPoller":
        self.t_start = time.monotonic()
        self.utc_started = results.utc_now_iso()
        self.th = threading.Thread(target=self._loop, name="w-kiyo-poller", daemon=True)
        self.th.start()
        return self

    def stop(self, timeout_s: float = 2 * POLL_TIMEOUT_S + 60) -> None:
        self.stop_ev.set()
        if self.th is not None:
            self.th.join(timeout_s)
        self.utc_stopped = results.utc_now_iso()

    def running(self) -> bool:
        return self.th is not None and self.th.is_alive()

    def _loop(self) -> None:
        """One round every interval_s. A round that starts late (it waited for the camera lock) is NOT followed by
        back-to-back catch-up rounds: the next round is due interval_s after the previous due time, or now if that
        has passed (next_due = max(next_due + interval, now))."""
        i = 0
        t0 = self.t_start or time.monotonic()
        next_due = t0
        while not self.stop_ev.is_set():
            sched = next_due - t0
            if sched > self.max_s:
                self.ctx.log(f"{TEST}: poller reached its {self.max_s / 3600:.1f} h bound; stopping")
                break
            wait = next_due - time.monotonic()
            if wait > 0 and self.stop_ev.wait(wait):
                break
            try:
                self.poll_round(i, sched, late_s=max(0.0, time.monotonic() - next_due))
            except Exception as e:  # noqa: BLE001 - the poller must never kill the suite
                self.errors.append({"round": i, "exception": repr(e)})
                self.ctx.log(f"{TEST}: poll round {i} raised {e!r}")
            i += 1
            next_due = max(next_due + self.interval_s, time.monotonic())

    # ---------------------------------------------------------------- one round
    def _activity(self, i: int) -> tuple[dict, dict]:
        """({key: activity signature}, raw doc) for every Kiyo: who holds / streams it now (IMFSensorActivityMonitor +
        ConsentStore; opens no camera, no lock). Read right AFTER the round's polls (not before their lock wait)."""
        act = ck.wincam_activity(self.ctx)
        act_sig: dict = {}
        for cam in self.cams:
            e = ck.activity_entry(act, cam)
            asig = None if not act.get("ok") else sorted(
                f"{q.get('name') or '?'}:{q.get('pid')}{'*' if q.get('streaming') else ''}"
                for q in (e or {}).get("processes") or [] if not q.get("self"))
            act_sig[cam["key"]] = asig
            if asig != self._activity_last.get(cam["key"], "unset"):
                self.state[cam["key"]]["activity_changes"].append(
                    {"utc": results.utc_now_iso(), "i": i, "processes": asig, "in_use": (e or {}).get("in_use"),
                     "report_received": (act.get("monitor") or {}).get("report_received"),
                     "consent_in_use": act.get("consent_in_use"), "error": act.get("error")})
                self._activity_last[cam["key"]] = asig
        return act_sig, act

    def poll_round(self, i: int, sched: float, late_s: float = 0.0) -> None:
        """Polls first (each waits for the camera lock), then the context read right after them: LastArrivalDate /
        problem code (CfgMgr), who holds the Kiyo (wincam activity) and vendor processes. The plug-in age is computed
        at the time each poll ran."""
        ctx = self.ctx
        polls: list[tuple[dict, dict]] = []
        for cam in self.cams:
            for api in ("mf", "ds"):
                if (api == "mf" and not cam.get("mf_symlink")) or (api == "ds" and not cam.get("ds_path")):
                    continue
                p = poll_once(ctx, cam, api, raw_path=self.raw)
                p.update(i=i, sched_t_s=round(sched, 2), late_s=round(late_s, 2),
                         t_s=round(time.monotonic() - (self.t_start or 0), 2), test=getattr(ctx, "current_test", None))
                polls.append((cam, p))
        vend = vendor_processes(ctx)
        sig = _vendor_sig(vend)
        if sig != self._vendor_last:
            for cam in self.cams:
                self.state[cam["key"]]["vendor_changes"].append({"utc": results.utc_now_iso(), "i": i,
                                                                 "processes": sig})
            self._vendor_last = sig
        act_sig, _act = self._activity(i)
        arrivals = {}
        for cam in self.cams:
            st = self.state[cam["key"]]
            arr = ctx._arrival_for(cam) if hasattr(ctx, "_arrival_for") else {}
            arr = arr if isinstance(arr, dict) else {}
            la = arr.get("last_arrival") or cam.get("last_arrival")
            arrivals[cam["key"]] = (arr, la)
            if st["arrivals"] and st["arrivals"][-1].get("last_arrival") != la:
                ctx.log(f"{TEST}: {cam.get('name')} RE-ARRIVED ({st['arrivals'][-1].get('last_arrival')} -> {la})")
            if not st["arrivals"] or st["arrivals"][-1].get("last_arrival") != la:
                st["arrivals"].append({"utc": results.utc_now_iso(), "i": i, "last_arrival": la,
                                       "present": arr.get("present"), "problem_code": arr.get("problem_code")})
        for cam, p in polls:
            st = self.state[cam["key"]]
            arr, la = arrivals[cam["key"]]
            age = _age_s_at(la, p.get("utc"))
            if st["plug_in_age_at_start_s"] is None:
                st["plug_in_age_at_start_s"] = age
                st["last_arrival_at_start"] = la
            p.update(plug_in_age_s=age, last_arrival=la, problem_code=arr.get("problem_code"),
                     present=arr.get("present"), vendor_processes=sig, activity_processes=act_sig.get(cam["key"]))
            self._record(cam, st, p)

    def _save_raw(self, cam: dict, p: dict, tag: str) -> str | None:
        j = p.get("_raw")
        if j is None:
            return None
        f = self.raw / ck.cam_slug(cam) / f"poll_{p['i']:05d}_{p['api']}_{tag}.json"
        try:
            results.write_json(f, j)
            return str(f)
        except Exception:  # noqa: BLE001
            return None

    def _record(self, cam: dict, st: dict, p: dict) -> None:
        ctx = self.ctx
        api = p["api"]
        if p["ok"] is None:                 # camera lock busy: not polled (no onset, no transition, no fault)
            p.pop("_raw", None)
            st["polls"].append(compact(p))
            return
        prev = st["last_ok"].get(api)
        first = api not in st["first_poll_ok"]
        if first:
            st["first_poll_ok"][api] = p["ok"]
        changed = prev is not None and prev != p["ok"]
        nfail = sum(1 for q in st["polls"] if q["api"] == api and q["ok"] is False)
        if first or changed or (not p["ok"] and nfail % 30 == 0):
            p["raw_file"] = self._save_raw(cam, p, "first" if first else ("change" if changed else "fail"))
        detail = {k: p.get(k) for k in ("utc", "utc_requested", "time_basis", "i", "t_s", "plug_in_age_s",
                                         "last_arrival", "problem_code", "present", "test", "rc",
                                         "timed_out", "error_hr", "error_name", "error_class", "error_stage",
                                         "codes", "real_codes", "not_called_codes", "device_error",
                                         "failing_controls", "answered_controls", "vendor_processes",
                                         "activity_processes", "raw_file",
                                         "lock_wait_s", "stderr_tail")}
        if not p["ok"] and api not in st["first_failure"]:
            detail["failed_from_first_poll"] = first
            st["first_failure"][api] = detail
            ctx.log(f"{TEST}: {cam.get('name')} {api} control poll {p['i']} FAILED (plug-in age "
                    f"{None if p.get('plug_in_age_s') is None else round(p['plug_in_age_s'] / 60, 1)} min, during "
                    f"{p.get('test')}): codes {p.get('codes')} {p.get('error_name') or ''}")
            self._publish(cam, st)
        if changed:
            st["transitions"].append({"api": api, "to": "answering" if p["ok"] else "not_answering", **detail})
            ctx.log(f"{TEST}: {cam.get('name')} {api} controls {'answer again' if p['ok'] else 'STOPPED answering'}"
                    f" (poll {p['i']}, during {p.get('test')})")
            self._publish(cam, st)
        # a control plane answering ERROR_GEN_FAILURE is the device fault: mark it once per episode
        if not p["ok"] and p.get("device_error") and not st["fault_marked"] and hasattr(ctx, "mark_fault"):
            st["fault_marked"] = True
            ctx.mark_fault(cam, code=DEVICE_ERROR_HR, api=api, stage="control_get", cls="device_error",
                           source="kiyo_poller", detail={"poll": p["i"], "codes": p.get("codes")}, utc=p.get("utc"))
        if p["ok"]:
            st["fault_marked"] = False      # answering again: a later device error starts a new episode
        st["last_ok"][api] = p["ok"]
        p.pop("_raw", None)
        st["polls"].append(compact(p))

    def _publish(self, cam: dict, st: dict) -> None:
        """Copy the onset record to ctx.kiyo_state (read by run_suite for run_suite.json / summary.md)."""
        if not hasattr(self.ctx, "kiyo_state"):
            return
        rec = onset_record(cam, st, self)
        lock = getattr(self.ctx, "_lock", None)
        if lock is not None:
            with lock:
                self.ctx.kiyo_state[cam["key"]] = rec
        else:
            self.ctx.kiyo_state[cam["key"]] = rec

    # ---------------------------------------------------------------- result
    def result_for(self, cam: dict) -> dict:
        st = self.state[cam["key"]]
        polls = st["polls"]
        ran = [p for p in polls if p.get("ok") is not None]          # lock-busy polls made no camera call
        n = {api: sum(1 for p in ran if p["api"] == api) for api in ("mf", "ds")}
        nok = {api: sum(1 for p in ran if p["api"] == api and p["ok"]) for api in ("mf", "ds")}
        busy = {api: sum(1 for p in polls if p["api"] == api and p.get("ok") is None) for api in ("mf", "ds")}
        codes: dict = {}
        for p in ran:
            if not p["ok"]:
                why = (p.get("error_hr") or ("timeout" if p.get("timed_out") else None) or
                       ("get " + "/".join(p.get("codes") or []) if p.get("codes") else "rc " + str(p.get("rc"))))
                k = f"{p['api']}:{why}"
                codes[k] = codes.get(k, 0) + 1
        return {"name": cam.get("name"), "mode": self.mode, "last_arrival": st["last_arrival_at_start"],
                "plug_in_age_at_start_s": st["plug_in_age_at_start_s"], "speed": cam.get("speed"),
                "device_parameters": cam.get("device_parameters"),
                "function_device_parameters": cam.get("function_device_parameters"),
                "polls": polls, "polls_per_api": n, "lock_busy_per_api": busy,
                "ok_per_api": nok, "first_failure": st["first_failure"] or None, "failure_codes": codes,
                "stopped_answering": bool(st["first_failure"]),
                "failed_from_first_poll": {api: bool(f.get("failed_from_first_poll"))
                                           for api, f in st["first_failure"].items()} or None,
                "transitions": st["transitions"], "arrivals_seen": st["arrivals"],
                "vendor_process_changes": st["vendor_changes"], "activity_changes": st["activity_changes"],
                "onset": onset_record(cam, st, self)}


def onset_record(cam: dict, st: dict, poller: KiyoPoller | None = None) -> dict:
    """Compact onset summary for one Kiyo (first failing poll per API, whether it failed from the first poll)."""
    ff = st.get("first_failure") or {}
    first = min(ff.values(), key=lambda d: d.get("utc") or "") if ff else None
    return {"name": cam.get("name"), "poller_mode": getattr(poller, "mode", None),
            "poller_started_utc": getattr(poller, "utc_started", None),
            "plug_in_age_at_start_s": st.get("plug_in_age_at_start_s"),
            "last_arrival": st.get("last_arrival_at_start"),
            "stopped_answering": bool(ff),
            "failed_from_first_poll": bool(first and first.get("failed_from_first_poll")),
            "first_failure_utc": first.get("utc") if first else None,
            "first_failure_plug_in_age_s": first.get("plug_in_age_s") if first else None,
            "first_failure_test": first.get("test") if first else None,
            "first_failure_codes": first.get("codes") if first else None,
            "first_failure_vendor_processes": first.get("vendor_processes") if first else None,
            "first_failure_activity_processes": first.get("activity_processes") if first else None,
            "per_api": {api: {k: d.get(k) for k in ("utc", "plug_in_age_s", "test", "codes", "real_codes",
                                                    "error_hr", "failed_from_first_poll")} for api, d in ff.items()},
            "transitions": [{k: t.get(k) for k in ("api", "to", "utc", "plug_in_age_s", "test")}
                            for t in st.get("transitions") or []],
            "n_polls": len(st.get("polls") or [])}


def verdict_for(d: dict, dur_min: float) -> dict:
    polls = [p for p in d.get("polls") or [] if p.get("ok") is not None]    # lock-busy polls were not polls
    if not polls:
        why = "no control poll completed" + (" (camera lock busy every time)" if d.get("polls") else "")
        return rating.untested(why, {"onset": d.get("onset"), "lock_busy_per_api": d.get("lock_busy_per_api")})
    stopped = d["stopped_answering"]
    fffp = any((d.get("failed_from_first_poll") or {}).values())
    crit = [{"criterion": "answers every control poll (MF and DS) during the window", "met": not stopped,
             "detail": {"ok": d["ok_per_api"], "polls": d["polls_per_api"]}},
            {"criterion": "onset observed inside the window (the first poll answered)",
             "met": None if not stopped else not fffp, "detail": d.get("failed_from_first_poll")}]
    note = None
    if stopped and fffp:
        note = ("failed from the first poll: the Kiyo was already not answering when polling began, so this window "
                "does not show the onset")
    ev = {"first_failure": d["first_failure"], "codes": d["failure_codes"], "minutes": round(dur_min, 1),
          "failed_from_first_poll": d.get("failed_from_first_poll"), "onset": d.get("onset"),
          "plug_in_age_at_start_s": d.get("plug_in_age_at_start_s"), "mode": d.get("mode"),
          "lock_busy_per_api": d.get("lock_busy_per_api")}
    r = {"rating": "no" if stopped else "yes", "criteria": crit, "evidence": ev}
    if note:
        r["note"] = note
    return r


# ============================================================================================================ API
def start_background(ctx) -> KiyoPoller | None:
    """Start the whole-suite poller (None when no Kiyo is attached)."""
    kiyos = [c for c in ctx.cameras if c.get("is_kiyo")]
    if not kiyos:
        return None
    iv = float(getattr(getattr(ctx, "args", None), "kiyo_interval", None) or INTERVAL_S)
    p = KiyoPoller(ctx, kiyos, interval_s=iv, mode="background").start()
    try:
        ctx.kiyo_poller = p
    except Exception:  # noqa: BLE001
        pass
    ctx.log(f"{TEST}: background control poller started for {[c.get('name') for c in kiyos]} "
            f"(every {iv:.0f} s, MF + DS, under camlock)")
    return p


def finish(ctx, poller: KiyoPoller | None) -> dict:
    """Stop the poller and build the W-KIYO result."""
    kiyos = [c for c in ctx.cameras if c.get("is_kiyo")]
    res = ck.new_result(ctx, TEST, kiyos)
    pw = power_settings()
    if not kiyos or poller is None:
        return results.finish_result(res, measurements={"power": pw, "note": "no Razer Kiyo Pro (1532:0E05) present"},
                                     verdicts={"kiyo": rating.untested("no Kiyo attached")})
    poller.stop()
    dur_min = ((time.monotonic() - (poller.t_start or time.monotonic())) / 60.0)
    per = {c["key"]: poller.result_for(c) for c in poller.cams}
    for c in poller.cams:
        if hasattr(ctx, "kiyo_state"):
            ctx.kiyo_state[c["key"]] = per[c["key"]]["onset"]
    verdicts = {f"kiyo|{k}|all": verdict_for(d, dur_min) for k, d in per.items()}
    meas = {"interval_s": poller.interval_s, "mode": poller.mode, "minutes": round(dur_min, 2),
            "utc_started": poller.utc_started, "utc_stopped": poller.utc_stopped, "power": pw, "cameras": per,
            "poll_timeout_ms": POLL_TIMEOUT_MS, "poller_errors": poller.errors,
            "note": "read-only; the LPM-off arm (power plan change) is attended item A4. In background mode the "
                    "polls ran during the other tests (each under camlock, so never concurrently with another "
                    "camera command)."}
    return results.finish_result(res, measurements=meas, verdicts=verdicts)


def run(ctx) -> dict:
    """Foreground window (``--only W-KIYO``), or the finish of a background poller already on ctx."""
    bg = getattr(ctx, "kiyo_poller", None)
    if bg is not None:
        return finish(ctx, bg)
    kiyos = [c for c in ctx.cameras if c.get("is_kiyo")]
    if not kiyos:
        return finish(ctx, None)
    dur = minutes(ctx) * 60
    iv = float(getattr(getattr(ctx, "args", None), "kiyo_interval", None) or INTERVAL_S)
    p = KiyoPoller(ctx, kiyos, interval_s=iv, max_s=dur, mode="foreground")
    ctx.log(f"{TEST}: polling {[c.get('name') for c in kiyos]} every {iv:.0f} s for {dur / 60:.1f} min")
    p.start()
    p.th.join(dur + 4 * POLL_TIMEOUT_S + 120)
    return finish(ctx, p)


# ============================================================================================================ reanalysis
def reanalyse(run_dir: str | Path, out: str | Path | None = None) -> dict:
    """Re-rate an existing W-KIYO.json (no camera opened): N1 plug-in age at the FIRST poll, failed_from_first_poll,
    and the run's earlier device fault (scan of the tests before W-KIYO) as the onset the window could not see."""
    import suitectx  # noqa: PLC0415
    run_dir = Path(run_dir)
    orig = json.loads((run_dir / f"{TEST}.json").read_text(encoding="utf-8"))
    meta = json.loads((run_dir / "run_suite.json").read_text(encoding="utf-8")) \
        if (run_dir / "run_suite.json").exists() else {}
    cams_meta = meta.get("cameras") or orig.get("cameras") or []
    earlier: dict = {}
    for t in meta.get("tests") or []:
        if t == TEST:
            break
        p = run_dir / f"{t}.json"
        if p.exists():
            for k, rec in suitectx.scan_result_for_faults(t, json.loads(p.read_text(encoding="utf-8")),
                                                          cams_meta).items():
                earlier.setdefault(k, rec)
    verdicts, per = {}, {}
    m = orig.get("measurements") or {}
    for k, d in (m.get("cameras") or {}).items():
        polls = d.get("polls") or []
        first = {}
        for p in polls:
            if p.get("ok") is not None:                 # a lock-busy poll made no camera call
                first.setdefault(p["api"], p)
        ff = d.get("first_failure") or {}
        fffp = {api: bool(f.get("i") == 0 or (first.get(api) or {}).get("i") == f.get("i")) for api, f in ff.items()}
        age0 = min((p.get("plug_in_age_s") for p in polls if p.get("plug_in_age_s") is not None), default=None)
        onset = {"failed_from_first_poll": any(fffp.values()), "window_first_poll_utc": polls[0]["utc"] if polls
                 else None, "plug_in_age_at_start_s": age0,
                 "earlier_device_fault": earlier.get(k),
                 "earlier_device_fault_plug_in_age_s": None}
        ef = earlier.get(k)
        if ef and ef.get("utc") and d.get("last_arrival"):
            t1 = suitectx._dt.datetime.fromisoformat(str(ef["utc"]).replace("Z", "+00:00"))
            onset["earlier_device_fault_plug_in_age_s"] = suitectx.age_s(d["last_arrival"], now=t1)
        dd = dict(d, plug_in_age_at_start_s=age0, plug_in_age_at_end_s=d.get("plug_in_age_at_start_s"),
                  failed_from_first_poll=fffp or None, onset=onset, mode="foreground (original run order: last)")
        dd["polls"] = polls
        per[k] = {kk: dd[kk] for kk in ("plug_in_age_at_start_s", "plug_in_age_at_end_s", "failed_from_first_poll",
                                        "onset", "polls_per_api", "ok_per_api", "failure_codes")}
        verdicts[f"kiyo|{k}|all"] = verdict_for(dd, float(m.get("minutes") or 0))
    doc = {"test": TEST, "reanalysis_of": str(run_dir / f"{TEST}.json"), "utc": results.utc_now_iso(),
           "camera_opened": False,
           "fixes_applied": ["N1 plug_in_age_at_start_s = age at the first poll (the original field was the age at "
                             "the end of the loop; kept as plug_in_age_at_end_s)",
                             "B7 failed_from_first_poll + onset criterion; the run's earlier device fault (scan of "
                             "the tests that ran before W-KIYO) recorded as the onset the window could not see",
                             "B2/N2 not recoverable offline: the original polls kept only iam_get codes (first 5) "
                             "and the first 10 failing controls; the per-control HRESULT dicts were not saved"],
           "measurements": {"cameras": per}, "verdicts": verdicts,
           "verdict_changes": [{"verdict": vk, "old": ((orig.get("verdicts") or {}).get(vk) or {}).get("rating"),
                                "new": v["rating"]} for vk, v in verdicts.items()
                               if ((orig.get("verdicts") or {}).get(vk) or {}).get("rating") != v["rating"]]}
    results.write_json(Path(out) if out else run_dir / "reanalysis" / f"{TEST}.json", doc)
    return doc


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="W-KIYO offline re-analysis (no camera opened)")
    ap.add_argument("--reanalyse", required=True, metavar="RUN_DIR")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    d = reanalyse(a.reanalyse, a.out)
    print(json.dumps({"measurements": d["measurements"], "verdict_changes": d["verdict_changes"],
                      "notes": {k: v.get("note") for k, v in d["verdicts"].items()}}, indent=1, default=str))
