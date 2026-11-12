# /// script
# requires-python = ">=3.10"
# ///
"""Shared context for the Windows suite (contract 3) and run-time camera discovery. Stdlib only.

    import sys; from pathlib import Path
    WIN = Path(__file__).resolve().parents[1]            # suite/windows (from suite/windows/tests/w_x.py)
    sys.path[:0] = [str(WIN.parent), str(WIN), str(WIN / "helpers")]
    import suitectx
    ctx = suitectx.build_ctx(args)                         # discovery runs here (no camera is opened)
    r = ctx.camcmd([str(ctx.wincam), "formats", "--api", "mf", "--device", cam["mf_symlink"],
                    "--timeout-ms", "8000"], timeout_s=30)  # under camlock, timeout on the CHILD
    ctx.write("W-FMT", result_dict)

SuiteCtx fields (contract 3; extra fields are additive):
    out_dir      results/windows/<host>/suite_<stamp>/ (or --out-dir)
    raw_dir      big raw data outside the repo (common.results.default_raw_dir(out_dir))
    args         argparse Namespace: quick, only, skip, cycles, proc_cycles, frames, mjpeg_seconds (+ extras)
    cameras      list of camera dicts (below), every USB camera found, the Kiyo included, never filtered
    wincam       absolute path of suite/windows/native/build/wincam.exe
    helpers_dir  suite/windows/helpers (the "python helpers dir"; alias property python_helpers_dir)
    log(msg)     timestamped line to stderr and <out_dir>/suite_log.txt
    camcmd(argv, timeout_s) -> procutil.run-style dict, executed under tools/camlock.py with the timeout INSIDE
    write(name, obj) -> Path of <out_dir>/<name>.json (strict JSON via common.results.write_json)

Camera dict (contract fields first):
    key                 camera_identity key: '<vid>:<pid>:sn=<serial>' or '<vid>:<pid>:port=<controller>/<chain>'
    name                friendly name (MF, else DS, else PnP FriendlyName / BusReportedDeviceDesc)
    vid, pid            lower-case 4-digit hex
    serial              USB serial as Windows used it (instance-ID suffix without '&'), else None
    is_kiyo             VID:PID == 1532:0e05 (label only; the Kiyo is never skipped)
    instance_id         the USB device (composite parent) instance ID, e.g. USB\\VID_046D&PID_085C\\C922SN01
    parent_instance_id  the hub the device is plugged into
    mf_symlink          MF symbolic link (KSCATEGORY_VIDEO_CAMERA) or None
    ds_name, ds_path    DirectShow FriendlyName and DevicePath (KSCATEGORY_CAPTURE) or None
    location_path       DEVPKEY_Device_LocationPaths[0] of the USB device
    metadata_tier1      True when MetadataBufferSizeInKB<n> > 0 on the CURRENT interface instance (read-only check;
                        environment context for W-ENV only: no test rates on it, tier 0 only since 2026-11-09)
  extras: function_instance_id (the &MI_xx video function), hub_port, port_path, key_kind, serial_source,
    serial_reason, i_serial, bcd_device, bcd_usb, speed (LS/FS/HS/SS/SS+), container_id, location_paths,
    location_info, mf_index, mf_name, ds_index, ds_ffmpeg_name ('@device_pnp_' + ds_path, the FFmpeg dshow
    alternative name), opencv_dshow_index (= ds_index), opencv_msmf_index (= mf_index), ds_clsid_is_ksproxy,
    metadata_registry, last_arrival, last_removal, first_install, problem_code, devnode_status, dn_flags, dn_warn,
    service, function_service, driver_version, driver_provider, device_parameters, function_device_parameters,
    sources (which enumerations saw it).

Device-fault gate and first-failure record (analysis cyc_kiyo B1/B7, ts B9; additive, thread-safe):
    ctx.begin_test(test)          runner: sets current_test, re-probes every faulted camera once (1-frame MF
                                  capture); a camera that answers is un-faulted (recovery recorded)
    ctx.camera_faulted(key|cam)   -> the fault record (truthy) while the camera is faulted, else None
    ctx.camera_gated(key|cam)     -> the record when the camera was faulted at the START of the current test
                                  (after its re-probe): its streaming work in this test is skipped
    ctx.mark_fault(key|cam, test=, mode=, code=, api=, stage=, cls=, source=, detail=)
    ctx.record_failure(...)       first DEVICE-LEVEL failure per camera (first_failure) and first failure of any
                                  kind (first_any_failure), suite-wide
    ctx.health_probe(key|cam, test=, mode=) -> {ok, fault_like, code, stage, class, recovered, faulted_after, ...}
    ctx.fault_untested(key|cam)   -> rating-style {"rating": "untested", ...} "device fault since <ts>"
    ctx.fault_report()            -> {faults, first_failure, first_any_failure, events, gated_by_test, probes_by_test, kiyo}
A fault is a stream/control command that returned ERROR_GEN_FAILURE (0x8007001F, class device_error), an
unreleasable/hung reader (``unreleasable`` true, or a release stage that timed out), or a streaming command killed
at its timeout. camcmd detects these itself for every single-camera command (the camera is found from the
MF symlink / DS DevicePath in argv) and, while a camera is gated, answers its STREAMING commands (wincam
capture/cycle, pyav_ds, opencv_ds) without running them: rc 4 and a JSON {"ok": false, "gate_skipped": true,
"device_fault": true, "error": {"class": "device_fault", "stage": "gate", ...}}. Control and format reads are never
gated (they fail fast and are the evidence). ``camcmd(..., gate=False)`` bypasses the gate (health probes, the
W-KIYO poller). Faults raised during a test gate only from the next test on.

First-failure record (``command_failed``): a command counts as failed when its JSON says ``ok`` false, carries a
non-empty ``error`` dict (the wincam ``controls`` JSON has no ``ok`` key), ``device_not_answering`` or a non-zero
``exit_code``, or when the process rc is not 0 / None or it was killed at its timeout; a format fallback and a
camera-lock timeout are not failures.

Plan mode (run_suite --plan): ``ctx.dry_run`` True makes ``camcmd`` run nothing (``dry_run_commands`` records what
would have run); capkit.get_formats then reads earlier runs' cached format lists.

USB link (``usb_link_report``): every camera's negotiated speed (hub IOCTL CONNECTION_INFORMATION_EX / _V2, the hub
driver's cached state), port protocols, bcdUSB, LastArrivalDate and plug-in age, from the discovery values or read
fresh; ``kiyo_link_warning`` is the runner's start-of-run warning when a Kiyo is not at SuperSpeed.

The MetadataBufferSizeInKB<n> value is only READ here (``metadata_tier1``, kept under that name for the result
contract) as environment context; nothing in the suite writes the registry, and no test uses UVC metadata (tier 0
only, Dom 2026-11-09).

Discovery opens NO camera: `wincam list` reads property bags only, PnP data comes from CfgMgr32, the port data
from the hub driver's cached connection info (IOCTL 274/279/278), and the metadata flag from a read-only registry
query. It runs in a child process with a timeout (python suitectx.py --discover).

Self-test / standalone:  python suite/windows/suitectx.py --discover [--wincam PATH] [--out FILE]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

WIN_DIR = Path(__file__).resolve().parent                 # suite/windows
SUITE_DIR = WIN_DIR.parent                                # suite
RESEARCH_ROOT = SUITE_DIR.parent                          # research/usb_cameras
HELPERS_DIR = WIN_DIR / "helpers"
TESTS_DIR = WIN_DIR / "tests"
CAMLOCK = RESEARCH_ROOT / "tools" / "camlock.py"
WINCAM_DEFAULT = WIN_DIR / "native" / "build" / "wincam.exe"
TIMED_RUN = HELPERS_DIR / "timed_run.py"
KIYO_VIDPID = ("1532", "0e05")

for _p in (str(SUITE_DIR), str(HELPERS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from common import identity, modescope, procutil, results  # noqa: E402

TIMED_MARK = "@@TIMED_RUN@@"

#: HRESULT_FROM_WIN32(ERROR_GEN_FAILURE): "a device attached to the system is not functioning" (the Kiyo signature)
DEVICE_ERROR_HR = "0x8007001F"
#: tools whose commands stream a camera (gated while the camera is faulted); controls/formats/list are not gated
#: (pyav_list.py is deliberately absent: W-PYAV-LIST must meet a faulted camera to rate "hangs on a faulted camera")
STREAM_TOOLS = ("pyav_ds.py", "opencv_ds.py", "raw_ds.py", "opencv_ctrl.py", "ffmpeg", "ffmpeg.exe")
STREAM_WINCAM_SUBCOMMANDS = ("capture", "cycle")


# ============================================================================================================ ctx
@dataclass
class SuiteCtx:
    out_dir: Path
    raw_dir: Path
    args: argparse.Namespace
    cameras: list[dict]
    wincam: Path
    helpers_dir: Path = HELPERS_DIR
    suite_dir: Path = SUITE_DIR
    windows_dir: Path = WIN_DIR
    research_root: Path = RESEARCH_ROOT
    camlock: Path = CAMLOCK
    camlock_timeout_s: float = 600.0
    python: str = "3.12"                      # uv --python pin for PEP 723 helper scripts
    discovery: dict = field(default_factory=dict)
    hostname: str = field(default_factory=socket.gethostname)
    stamp: str = field(default_factory=results.utc_stamp)
    log_file: Path | None = None
    # ---- device-fault gate / first-failure record (see module docstring)
    current_test: str | None = None
    fault_gate: bool = True
    faults: dict = field(default_factory=dict)            # key -> fault record (current state + history)
    first_failure: dict = field(default_factory=dict)     # key -> first device-level failed camera command
    first_any_failure: dict = field(default_factory=dict)  # key -> first failed camera command of any kind
    fault_events: list = field(default_factory=list)      # chronological fault / recovery / probe events
    gated_by_test: dict = field(default_factory=dict)     # test -> {key: fault since}
    probes_by_test: dict = field(default_factory=dict)    # test -> {key: [probe records]}
    kiyo_state: dict = field(default_factory=dict)        # key -> W-KIYO poller onset record (background poller)
    kiyo_poller: Any = None
    arrival_fn: Any = None                                # override for arrival_snapshot (offline tests)
    # ---- plan mode (run_suite --plan): camcmd runs nothing and records what it would have run
    dry_run: bool = False
    dry_run_commands: list = field(default_factory=list)
    plan_raw_root: Path | None = None                     # where plan mode looks for earlier runs' cached formats
    usb_link: dict = field(default_factory=dict)          # run-start USB link check (run_suite.start_link_check)
    # ---- Kiyo Pro dead rule (Dom 2026-11-11): once the Kiyo Pro faults it is dead for the rest of the run: every
    # later command addressed to it is skipped (streaming or not), it is never re-probed, re-opened, reset or
    # un-faulted, the poller stops polling it, and one diagnostics snapshot is recorded (CAPTURE_AND_RECORDING_PLAN
    # section 3.3 TP1, "Kiyo Pro wedge" row). Nothing further is done to diagnose it.
    dead: dict = field(default_factory=dict)              # key -> dead record (+ diagnostics)
    stream_starts: dict = field(default_factory=dict)     # key -> streaming commands started in this run
    last_cmd: dict = field(default_factory=dict)          # key -> last camera command (argv, times, rc, timeout)
    running_cmds: dict = field(default_factory=dict)      # id -> camera command running now (key, argv, utc)
    _gated: set = field(default_factory=set, repr=False)
    _lock: Any = field(default_factory=threading.RLock, repr=False)

    # ------------------------------------------------------------------ contract methods
    def log(self, msg: str) -> None:
        line = f"{_dt.datetime.now().strftime('%H:%M:%S')} {msg}"
        print(line, file=sys.stderr, flush=True)
        lf = self.log_file or (self.out_dir / "suite_log.txt")
        try:
            lf.parent.mkdir(parents=True, exist_ok=True)
            with open(lf, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def camcmd(self, argv: Sequence[Any], timeout_s: float, cwd: str | os.PathLike | None = None,
               env: dict | None = None, gate: bool = True, scan: bool = True,
               camlock_timeout_s: float | None = None) -> dict:
        """Run ``argv`` under the camera lock with the timeout on the child (see camcmd_run).

        Device-fault gate: a STREAMING command for a camera gated in the current test is not run (synthetic
        failure result, ``gate_skipped`` True). After a real run the output is scanned for a device fault
        (0x8007001F / unreleasable reader / killed streaming command) and the camera is marked faulted."""
        argv = [str(a) for a in argv]
        if self.dry_run:
            return self._dry_run_result(argv, timeout_s)
        cam = self.camera_for_argv(argv)
        streaming = is_streaming_argv(argv)
        if cam is not None and self.camera_dead(cam["key"]):
            # dead rule: NO command of any kind reaches a dead Kiyo Pro (gate=False does not override this)
            return self._gated_result(argv, cam, self.camera_dead(cam["key"]))
        if gate and cam is not None and streaming:
            rec = self.camera_gated(cam["key"])
            if rec:
                return self._gated_result(argv, cam, rec)
        cid = object()
        t_utc = results.utc_now_iso()
        with self._lock:
            if cam is not None:
                if streaming:
                    self.stream_starts[cam["key"]] = self.stream_starts.get(cam["key"], 0) + 1
                self.running_cmds[id(cid)] = {"key": cam["key"], "name": cam.get("name"), "argv": _short(argv, 400),
                                              "api": _argv_api(argv), "streaming": streaming, "utc_started": t_utc,
                                              "test": self.current_test}
        try:
            r = camcmd_run(argv, timeout_s, cwd=cwd, env=env,
                           camlock_timeout_s=self.camlock_timeout_s if camlock_timeout_s is None else camlock_timeout_s,
                           log=self.log)
        finally:
            with self._lock:
                self.running_cmds.pop(id(cid), None)
        if cam is not None:
            with self._lock:
                self.last_cmd[cam["key"]] = {"argv": _short(argv, 600), "utc_started": t_utc,
                                             "utc_ended": results.utc_now_iso(), "rc": r.get("rc"),
                                             "timed_out": r.get("timed_out"), "killed": r.get("killed"),
                                             "elapsed_s": r.get("elapsed_s"), "test": self.current_test,
                                             "stderr_tail": (r.get("stderr") or "")[-800:]}
        if scan and cam is not None:
            try:
                self._scan_camcmd(cam, argv, r, streaming)
            except Exception as e:  # noqa: BLE001 - the scan must never break a test
                self.log(f"fault scan error (ignored): {e!r}")
        return r

    def write(self, name: str, obj: Any) -> Path:
        name = name if name.endswith(".json") else name + ".json"
        return results.write_json(self.out_dir / name, obj)

    # ------------------------------------------------------------------ conveniences (additive)
    @property
    def python_helpers_dir(self) -> Path:
        return self.helpers_dir

    def run(self, argv: Sequence[Any], timeout_s: float, cwd=None, env=None) -> dict:
        """Enumeration-only command (opens no camera): procutil.run without the camera lock."""
        return procutil.run([str(a) for a in argv], timeout_s=timeout_s, cwd=cwd, env=env)

    def helper_cmd(self, script: str | os.PathLike, *args: Any, python: str | None = None) -> list[str]:
        """argv for a PEP 723 helper: uv run --python <pin> --script <helpers_dir/script> args..."""
        p = Path(script)
        if not p.is_absolute():
            p = self.helpers_dir / p
        return ["uv", "run", "--python", python or self.python, "--script", str(p), *map(str, args)]

    def test_dir(self, name: str) -> Path:
        d = self.out_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def raw_test_dir(self, name: str) -> Path:
        d = self.raw_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def camera(self, key: str) -> dict | None:
        return next((c for c in self.cameras if c.get("key") == key), None)

    def kiyo(self) -> list[dict]:
        return [c for c in self.cameras if c.get("is_kiyo")]

    def camera_summaries(self) -> list[dict]:
        """Compact camera list for result JSON 'cameras' fields."""
        return [camera_summary(c) for c in self.cameras]

    def arrivals(self) -> dict:
        return arrival_snapshot(self.cameras)

    def rediscover(self) -> list[dict]:
        d = discover(self.wincam, log=self.log)
        self.discovery = d
        self.cameras = d.get("cameras", [])
        return self.cameras

    # ------------------------------------------------------------------ device-fault gate
    def _cam(self, key_or_cam: Any) -> dict | None:
        if isinstance(key_or_cam, dict):
            return self.camera(key_or_cam.get("key")) or key_or_cam
        return self.camera(str(key_or_cam)) if key_or_cam is not None else None

    @staticmethod
    def _key(key_or_cam: Any) -> str | None:
        if isinstance(key_or_cam, dict):
            return key_or_cam.get("key")
        return None if key_or_cam is None else str(key_or_cam)

    def camera_for_argv(self, argv: Sequence[Any]) -> dict | None:
        """The ONE camera whose MF symlink or DS DevicePath appears in argv (None if none or ambiguous)."""
        return camera_for_argv(self.cameras, argv)

    def _arrival_for(self, cam: dict) -> dict:
        fn = self.arrival_fn or arrival_snapshot
        try:
            snap = fn([cam])
            return (snap.get("cameras") or {}).get(cam.get("key"), {}) or {}
        except Exception as e:  # noqa: BLE001
            return {"error": repr(e)}

    def plug_in_age_s(self, key_or_cam: Any, fresh: bool = True) -> tuple[float | None, str | None]:
        """(seconds since the camera's LastArrivalDate, that date). Fresh CfgMgr read unless fresh=False."""
        cam = self._cam(key_or_cam)
        if cam is None:
            return None, None
        la = (self._arrival_for(cam).get("last_arrival") if fresh else None) or cam.get("last_arrival")
        return age_s(la), la

    def camera_faulted(self, key_or_cam: Any) -> dict | None:
        k = self._key(key_or_cam)
        with self._lock:
            rec = self.faults.get(k)
            return dict(rec) if rec and rec.get("faulted") else None

    def camera_gated(self, key_or_cam: Any) -> dict | None:
        k = self._key(key_or_cam)
        d = self.camera_dead(k)
        if d:
            return d
        with self._lock:
            if not self.fault_gate or k not in self._gated:
                return None
        return self.camera_faulted(k)

    def camera_dead(self, key_or_cam: Any) -> dict | None:
        """The dead record when this camera (only ever the Kiyo Pro) is dead for the rest of the run, else None."""
        k = self._key(key_or_cam)
        with self._lock:
            rec = self.dead.get(k)
            return dict(rec) if rec else None

    def _declare_dead(self, cam: dict, fault_rec: dict) -> None:
        """Dead rule: mark the Kiyo Pro dead once, record the diagnostics snapshot, write it to the run folder."""
        with self._lock:
            if cam["key"] in self.dead:
                return
            self.dead[cam["key"]] = {"dead": True, "since_utc": fault_rec.get("since_utc"), "name": cam.get("name"),
                                     "code": fault_rec.get("code"), "test": fault_rec.get("test"),
                                     "rule": "Kiyo Pro dead for the rest of the run: no re-probe, re-open, reset "
                                             "or recovery; diagnostics recorded once (Dom 2026-11-11)"}
        self.log(f"KIYO PRO DEAD: {cam.get('name')} ({cam['key']}) faulted in {fault_rec.get('test')}: "
                 f"{fault_rec.get('code') or fault_rec.get('class')}. Marked dead for the rest of the run; no command "
                 "will reach it again. Recording diagnostics.")
        try:
            diag = self._dead_diagnostics(cam, fault_rec)
        except Exception as e:  # noqa: BLE001 - diagnostics must never break the run
            diag = {"error": repr(e)}
        with self._lock:
            self.dead[cam["key"]]["diagnostics"] = diag
        try:
            self.write(f"KIYO_PRO_DEAD_{results.utc_stamp()}", {"key": cam["key"], **self.dead[cam["key"]]})
        except Exception as e:  # noqa: BLE001
            self.log(f"could not write the Kiyo Pro dead record: {e!r}")

    def _dead_diagnostics(self, cam: dict, fault_rec: dict) -> dict:
        """The plan's list, read without touching the dead camera: time, plug-in age, run and test step, the last
        command and its arguments, every error code and timeout, the other cameras open at that moment and through
        which API, the Frame Server clients and camera-holding processes, the USB topology, stream starts since
        plug-in (counted from run start; earlier starts are unknown when it was plugged in before the run)."""
        age, la = self.plug_in_age_s(cam)
        with self._lock:
            hist = [e for e in self.fault_events if e.get("key") == cam["key"]]
            last = dict(self.last_cmd.get(cam["key"]) or {})
            running = [dict(v) for v in self.running_cmds.values()]
            starts = self.stream_starts.get(cam["key"], 0)
            failures = {"first_failure": self.first_failure.get(cam["key"]),
                        "first_any_failure": self.first_any_failure.get(cam["key"])}
        d = {"utc": results.utc_now_iso(), "run_dir": str(self.out_dir), "run_stamp": self.stamp,
             "test": self.current_test, "fault": {k: v for k, v in fault_rec.items() if k != "history"},
             "plug_in_age_s": age, "last_arrival": la, "last_command": last,
             "fault_and_failure_events": hist, **failures,
             "other_camera_commands_running": [r for r in running if r.get("key") != cam["key"]],
             "stream_starts_this_run": starts, "camera": camera_summary(cam),
             "usb_link": (self.usb_link or {}).get(cam["key"]) if isinstance(self.usb_link, dict) else None}
        try:
            d["arrival_now"] = self._arrival_for(cam)          # CfgMgr cached state; no device request
        except Exception as e:  # noqa: BLE001
            d["arrival_now"] = {"error": repr(e)}
        try:
            import capkit as _ck                               # IMFSensorActivityMonitor + ConsentStore; opens no camera
            d["camera_activity"] = _ck.wincam_activity(self)
        except Exception as e:  # noqa: BLE001
            d["camera_activity"] = {"error": repr(e)}
        for name, argv in (("frame_server", ["tasklist", "/svc", "/fo", "csv", "/fi", "SERVICES eq FrameServer"]),
                           ("processes", ["tasklist", "/fo", "csv", "/nh"])):
            try:
                r = self.run(argv, timeout_s=30)
                d[name] = (r.get("stdout") or "")[-20000:]
            except Exception as e:  # noqa: BLE001
                d[name] = {"error": repr(e)}
        return d

    def fault_reason(self, key_or_cam: Any) -> str | None:
        rec = self.camera_faulted(key_or_cam)
        if not rec:
            return None
        return (f"device fault since {rec.get('since_utc')} ({rec.get('test') or '?'}"
                f"{', ' + str(rec.get('mode')) if rec.get('mode') else ''}, {rec.get('code') or rec.get('class')})"
                "; replug needed")

    def fault_untested(self, key_or_cam: Any, extra: dict | None = None) -> dict:
        """A rating-shaped 'untested' verdict for a gated camera (common.rating.untested layout)."""
        rec = self.camera_faulted(key_or_cam) or {}
        reason = self.fault_reason(key_or_cam) or "device fault"
        ev = {"device_fault": True, "fault_code": rec.get("code"), "first_fault_utc": rec.get("since_utc"),
              "fault": {k: rec.get(k) for k in ("since_utc", "test", "mode", "code", "stage", "class", "source",
                                                 "plug_in_age_s")}, **(extra or {})}
        return {"rating": "untested", "criteria": [{"criterion": "measured", "met": None,
                                                    "detail": "untested: " + reason}],
                "evidence": ev, "note": "untested: " + reason}

    def record_failure(self, key_or_cam: Any, test: str | None = None, mode: Any = None, code: Any = None,
                       api: str | None = None, stage: str | None = None, cls: str | None = None,
                       source: str = "test", detail: Any = None, utc: str | None = None,
                       device_level: bool = True) -> dict | None:
        """Keep the FIRST failed camera command per camera for the whole suite: ``first_any_failure`` for any
        failure, ``first_failure`` only for a device-level one (``device_level``: an open / stream error, a timeout,
        0x8007001F; not a helper exit for a format / rate mismatch with every cycle streamed, see
        device_level_failure). Returns the device-level record (None when there is none yet)."""
        cam = self._cam(key_or_cam)
        if cam is None:
            return None
        with self._lock:
            have_any = cam["key"] in self.first_any_failure
            if cam["key"] in self.first_failure or (have_any and not device_level):
                return self.first_failure.get(cam["key"])
        age, la = self.plug_in_age_s(cam)
        rec = {"utc": utc or results.utc_now_iso(), "test": test or self.current_test,
               "mode": getattr(mode, "text", mode), "code": code, "api": api, "stage": stage, "class": cls,
               "source": source, "plug_in_age_s": age, "last_arrival": la, "detail": detail,
               "is_kiyo": cam.get("is_kiyo"), "name": cam.get("name"), "device_level": bool(device_level)}
        with self._lock:
            self.first_any_failure.setdefault(cam["key"], rec)
            if device_level:
                self.first_failure.setdefault(cam["key"], rec)
            return self.first_failure.get(cam["key"])

    def mark_fault(self, key_or_cam: Any, test: str | None = None, mode: Any = None, code: Any = None,
                   api: str | None = None, stage: str | None = None, cls: str | None = None,
                   source: str = "test", detail: Any = None, utc: str | None = None, **extra: Any) -> dict | None:
        """Mark a camera faulted (idempotent while it stays faulted: the first record is kept)."""
        cam = self._cam(key_or_cam)
        if cam is None:
            return None
        utc = utc or results.utc_now_iso()
        self.record_failure(cam, test=test, mode=mode, code=code, api=api, stage=stage, cls=cls or "device_error",
                            source=source, detail=detail, utc=utc)
        with self._lock:
            cur = self.faults.get(cam["key"])
            if cur and cur.get("faulted"):
                cur["repeats"] = cur.get("repeats", 0) + 1
                return dict(cur)
        age, la = self.plug_in_age_s(cam)
        ev = {"type": "fault", "utc": utc, "key": cam["key"], "name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"),
              "test": test or self.current_test, "mode": getattr(mode, "text", mode), "code": code, "api": api,
              "stage": stage, "class": cls or "device_error", "source": source, "plug_in_age_s": age,
              "last_arrival": la, "detail": detail, **extra}
        with self._lock:
            hist = (cur or {}).get("history", [])
            rec = {k: v for k, v in ev.items() if k != "type"}
            rec.update(faulted=True, since_utc=utc, history=hist + [ev], repeats=0)
            self.faults[cam["key"]] = rec
            self.fault_events.append(ev)
        self.log(f"FAULT: {cam.get('name')} ({cam['key']}) marked faulted by {source} in {ev['test']}: "
                 f"{code or cls} at {stage} (plug-in age {None if age is None else round(age / 60, 1)} min); "
                 + ("Kiyo Pro: dead rule applies" if cam.get("is_kiyo") else
                    "its streaming work is skipped from the next test on unless a health probe answers"))
        if cam.get("is_kiyo"):
            self._declare_dead(cam, rec)
        return dict(rec)

    def clear_fault(self, key_or_cam: Any, test: str | None = None, source: str = "health_probe",
                    detail: Any = None) -> dict | None:
        cam = self._cam(key_or_cam)
        if cam is None:
            return None
        if self.camera_dead(cam):
            self.log(f"clear_fault refused: {cam.get('name')} is dead for the rest of the run (Kiyo Pro dead rule)")
            return None
        with self._lock:
            cur = self.faults.get(cam["key"])
            if not cur or not cur.get("faulted"):
                return None
            ev = {"type": "recovered", "utc": results.utc_now_iso(), "key": cam["key"], "name": cam.get("name"),
                  "test": test or self.current_test, "source": source, "fault_since": cur.get("since_utc"),
                  "detail": detail}
            cur["faulted"] = False
            cur["recovered_utc"] = ev["utc"]
            cur.setdefault("history", []).append(ev)
            self.fault_events.append(ev)
            self._gated.discard(cam["key"])
        self.log(f"FAULT: {cam.get('name')} answered again ({source} in {ev['test']}); fault since "
                 f"{ev['fault_since']} cleared")
        return ev

    def health_probe(self, key_or_cam: Any, test: str | None = None, mode: Any = None, timeout_ms: int = 4000,
                     reason: str = "") -> dict:
        """One 1-frame MF capture (bounded, under camlock, never gated). Updates the fault state: a fault-like
        failure marks the camera faulted, success clears an existing fault (the recovery is recorded)."""
        cam = self._cam(key_or_cam)
        t = test or self.current_test
        if cam is None:
            return {"ok": None, "error": f"unknown camera {key_or_cam!r}"}
        dead = self.camera_dead(cam)
        if dead:
            out = {"ok": False, "dead": True, "skipped": "dead (Kiyo Pro dead rule): not probed", "key": cam["key"],
                   "name": cam.get("name"), "utc": results.utc_now_iso(), "test": t, "reason": reason,
                   "fault_like": True, "recovered": False, "faulted_after": True, "code": dead.get("code"),
                   "was_faulted": True}
            with self._lock:
                self.probes_by_test.setdefault(t or "-", {}).setdefault(cam["key"], []).append(dict(out))
            return out
        if not cam.get("mf_symlink"):
            return {"ok": None, "skipped": "camera has no MF symbolic link", "key": cam["key"]}
        pm = _probe_mode(self, cam, mode)
        if isinstance(pm, str):
            # nothing streamed: the fault state is left as it is (a faulted camera stays gated)
            out = {"ok": None, "skipped": pm, "key": cam["key"], "name": cam.get("name"), "utc": results.utc_now_iso(),
                   "test": t, "reason": reason, "fault_like": False, "recovered": False,
                   "faulted_after": bool(self.camera_faulted(cam))}
            with self._lock:
                self.probes_by_test.setdefault(t or "-", {}).setdefault(cam["key"], []).append(dict(out))
            self.log(f"health probe {cam.get('name')}: {pm}" + (f" [{reason}]" if reason else ""))
            return out
        w, h, fps = pm
        with self._lock:
            n = sum(len(v) for d in self.probes_by_test.values() for v in d.values())
        od = Path(self.raw_dir) / "_health" / _slug(cam) / f"{(t or 'probe').replace('/', '_')}_{n:04d}"
        od.mkdir(parents=True, exist_ok=True)
        argv = [str(self.wincam), "capture", "--api", "mf", "--device", cam["mf_symlink"], "--width", w,
                "--height", h, "--fps", f"{fps:.6g}", "--subtype", "MJPG", "--frames", 1, "--timeout-ms",
                int(timeout_ms), "--out-dir", od, "--save", "none"]
        was = self.camera_faulted(cam)
        r = self.camcmd(argv, timeout_s=4 * timeout_ms / 1000.0 + 25, gate=False, scan=False)
        obj, _ = parse_json_stdout(r)
        if obj is None and (od / "summary.json").exists():
            try:
                obj = json.loads((od / "summary.json").read_text(encoding="utf-8"))
            except ValueError:
                obj = None
        frames = ((obj or {}).get("frames") or {}).get("total") or 0
        ok = bool(obj) and bool(obj.get("ok")) and frames >= 1 and not r.get("timed_out")
        f = None if ok else fault_signature(obj, r, streaming=True)
        err = (obj or {}).get("error") or {}
        out = {"ok": ok, "key": cam["key"], "name": cam.get("name"), "utc": results.utc_now_iso(), "test": t,
               "reason": reason, "mode": f"MJPG {w}x{h}@{fps:g}", "frames": frames, "fault_like": bool(f),
               "code": (f or {}).get("code") or err.get("hr"), "stage": (f or {}).get("stage") or err.get("stage"),
               "class": (f or {}).get("class") or err.get("class"), "rc": r.get("rc"),
               "timed_out": r.get("timed_out"), "elapsed_s": r.get("elapsed_s"), "no_json": obj is None,
               "open_to_first_frame_ms": ((obj or {}).get("timings") or {}).get("open_to_first_frame_ms"),
               "was_faulted": bool(was), "recovered": False}
        if ok:
            if was:
                self.clear_fault(cam, test=t, source="health_probe", detail={"probe_utc": out["utc"]})
                out["recovered"] = True
        elif f:
            self.mark_fault(cam, test=t, mode=out["mode"], code=f.get("code"), api="mf", stage=f.get("stage"),
                            cls=f.get("class"), source="health_probe", detail={"reason": reason})
        else:
            self.record_failure(cam, test=t, mode=out["mode"], code=out["code"], api="mf", stage=out["stage"],
                                cls=out["class"], source="health_probe")
        out["faulted_after"] = bool(self.camera_faulted(cam))
        with self._lock:
            self.probes_by_test.setdefault(t or "-", {}).setdefault(cam["key"], []).append(dict(out))
            self.fault_events.append({"type": "probe_ok" if ok else "probe_failed", **{
                k: out[k] for k in ("utc", "key", "name", "test", "reason", "code", "stage", "class", "recovered")}})
        self.log(f"health probe {cam.get('name')}: {'ok' if ok else 'FAILED'} {out['code'] or out['class'] or ''}"
                 + (" -> recovered" if out["recovered"] else "") + (f" [{reason}]" if reason else ""))
        out["out_dir"] = str(od)
        return out

    def begin_test(self, test: str, probe: bool = True) -> dict:
        """Runner hook before each test: set current_test; re-probe each faulted camera ONCE (1-frame MF); the
        cameras still faulted are gated for this test. Returns {key: probe record} for the probes run."""
        self.current_test = test
        probes = {}
        with self._lock:
            faulted = [k for k, v in self.faults.items() if v.get("faulted")]
            self._gated = set()
        for k in faulted:
            if self.camera_dead(k):
                continue                                   # dead rule: never re-probed
            if probe and self.camera(k) is not None:
                probes[k] = self.health_probe(k, test=test, reason=f"re-probe at the start of {test}")
        with self._lock:
            self._gated = {k for k, v in self.faults.items() if v.get("faulted")}
            self.gated_by_test[test] = {k: self.faults[k].get("since_utc") for k in sorted(self._gated)}
        if self._gated:
            self.log(f"{test}: device-fault gate: streaming work skipped for "
                     f"{[(self.camera(k) or {}).get('name') or k for k in sorted(self._gated)]}")
        return probes

    def end_test(self, test: str | None = None) -> None:
        with self._lock:
            self._gated = set()
        self.current_test = None

    def fault_report(self) -> dict:
        with self._lock:
            return json.loads(json.dumps({
                "faults": self.faults,
                "currently_faulted": sorted(k for k, v in self.faults.items() if v.get("faulted")),
                "first_failure": self.first_failure, "first_any_failure": self.first_any_failure,
                "events": self.fault_events,
                "gated_by_test": self.gated_by_test, "probes_by_test": self.probes_by_test,
                "kiyo": self.kiyo_state,
                "dead": self.dead,
                "stream_starts": self.stream_starts,
                "rule": "fault = 0x8007001F (device_error) / unreleasable or hung reader / streaming command killed "
                        "at its timeout; its streaming commands are gated from the next test on; each later test "
                        "re-probes it once (1-frame MF capture) and un-faults it if it answers"}, default=str))

    def _gated_result(self, argv: list[str], cam: dict, rec: dict) -> dict:
        reason = self.fault_reason(cam) or "device fault"
        obj = {"tool": "suite_gate", "ok": False, "gate_skipped": True, "device_fault": True,
               "fault_code": rec.get("code"), "first_fault_utc": rec.get("since_utc"),
               "error": {"stage": "gate", "hr": None, "hr_name": "device_fault_gate", "class": "device_fault",
                         "message": "untested: " + reason, "reason": "untested: " + reason},
               "fault": {k: rec.get(k) for k in ("since_utc", "test", "mode", "code", "stage", "class", "source",
                                                  "plug_in_age_s")}}
        with self._lock:
            f = self.faults.get(cam["key"])
            if f is not None:
                f["gated_commands"] = f.get("gated_commands", 0) + 1
        self.log(f"gate: skipped streaming command for faulted {cam.get('name')}: {_short(argv)}")
        return {"argv": argv, "rc": 4, "stdout": json.dumps(obj), "stderr": "", "elapsed_s": 0.0, "timed_out": False,
                "killed": False, "kill_method": None, "spawn_error": None, "pid": None, "lock_wait_s": 0.0,
                "camlock_rc": None, "lock_timed_out": False, "outer": {}, "inner": None, "timeout_s": 0.0,
                "gate_skipped": True, "fault": obj["fault"]}

    def _dry_run_result(self, argv: list[str], timeout_s: float) -> dict:
        """Plan mode: nothing is executed; the command is recorded so the plan can show it."""
        with self._lock:
            self.dry_run_commands.append({"argv": _short(argv), "timeout_s": float(timeout_s),
                                          "test": self.current_test})
        return {"argv": argv, "rc": None, "stdout": "", "stderr": "plan mode: not executed", "elapsed_s": 0.0,
                "timed_out": False, "killed": False, "kill_method": None, "spawn_error": None, "pid": None,
                "lock_wait_s": 0.0, "camlock_rc": None, "lock_timed_out": False, "outer": {}, "inner": None,
                "timeout_s": float(timeout_s), "dry_run": True}

    def _scan_camcmd(self, cam: dict, argv: list[str], r: dict, streaming: bool) -> None:
        obj, _ = parse_json_stdout(r)
        f = fault_signature(obj, r, streaming=streaming)
        mode = _argv_mode(argv)
        api = _argv_api(argv)
        if f:
            self.mark_fault(cam, mode=mode, code=f.get("code"), api=api, stage=f.get("stage"), cls=f.get("class"),
                            source="camcmd_scan", detail={"argv": _short(argv), "why": f.get("why")},
                            command_utc_started=(obj or {}).get("utc_started") if isinstance(obj, dict) else None)
            return
        failed, err = command_failed(obj, r)
        if failed:
            self.record_failure(cam, mode=mode, code=err.get("hr") or err.get("errno") or r.get("rc") or
                                ("timeout" if r.get("timed_out") else None), api=api,
                                stage=err.get("stage"), cls=err.get("class") or ("timeout" if r.get("timed_out")
                                                                                  else None),
                                source="camcmd_scan", detail={"argv": _short(argv), "rc": r.get("rc"),
                                                              "timed_out": r.get("timed_out")},
                                utc=(obj or {}).get("utc_started") if isinstance(obj, dict) else None,
                                device_level=device_level_failure(obj, r, err))


CAMERA_SUMMARY_FIELDS = ("key", "name", "vid", "pid", "serial", "is_kiyo", "instance_id", "parent_instance_id",
                         "function_instance_id", "hub_port", "mf_symlink", "ds_name", "ds_path", "location_path",
                         "port_path", "speed", "bcd_device", "metadata_tier1", "last_arrival", "problem_code", "dn_warn",
                         "mf_index", "ds_index")


def camera_summary(c: dict) -> dict:
    return {k: c.get(k) for k in CAMERA_SUMMARY_FIELDS}


# ============================================================================================================ fault helpers
def age_s(last_arrival: Any, now: _dt.datetime | None = None) -> float | None:
    """Seconds since an ISO LastArrivalDate (None if missing or unparseable)."""
    if not last_arrival:
        return None
    try:
        t = _dt.datetime.fromisoformat(str(last_arrival).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return round(((now or _dt.datetime.now(_dt.timezone.utc)) - t).total_seconds(), 1)


def _norm_hr(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return f"0x{v & 0xFFFFFFFF:08X}"
    s = str(v).strip()
    return ("0x" + s[2:].upper()) if s.lower().startswith("0x") else s


def is_device_error(err: Any) -> bool:
    """ERROR_GEN_FAILURE (0x8007001F) or a classify_failure 'device_error' class."""
    if not isinstance(err, dict):
        return False
    return DEVICE_ERROR_HR in (_norm_hr(err.get("hr")), _norm_hr(err.get("code_hex"))) or \
        str(err.get("class") or "") == "device_error"


def is_release_hang(err: Any) -> bool:
    """A release/close/shutdown stage that did not return (the hung-reader signature)."""
    if not isinstance(err, dict):
        return False
    st = str(err.get("stage") or "").lower()
    return ("release" in st or "shutdown" in st or st == "close") and \
        (str(err.get("class") or "") == "timeout" or str(err.get("hr_name") or "") == "timeout")


def fault_signature(obj: Any, run: dict | None = None, streaming: bool = True) -> dict | None:
    """{code, stage, class, why} when a tool result shows a device fault, else None.

    Fault = ERROR_GEN_FAILURE / class device_error in the top-level error; an unreleasable reader (top-level or
    summary ``unreleasable``) or a release stage that timed out; a cycle run whose cycles failed with device_error
    and none succeeded; or (streaming commands only) the command killed at its timeout (not a lock timeout)."""
    run = run or {}
    if isinstance(obj, dict) and not obj.get("gate_skipped"):
        err = obj.get("error") if isinstance(obj.get("error"), dict) else {}
        if is_device_error(err):
            return {"code": _norm_hr(err.get("hr")) or DEVICE_ERROR_HR, "stage": err.get("stage"),
                    "class": "device_error", "why": "error 0x8007001F / device_error"}
        if obj.get("unreleasable") is True or is_release_hang(err):
            return {"code": _norm_hr(err.get("hr")) or "timeout", "stage": err.get("stage") or "release",
                    "class": "unreleasable", "why": "unreleasable / hung reader"}
        summ = obj.get("summary") if isinstance(obj.get("summary"), dict) else {}
        if summ.get("unreleasable") is True:
            return {"code": "timeout", "stage": "release", "class": "unreleasable",
                    "why": "cycle run ended with an unreleasable reader"}
        fbc = summ.get("failures_by_class") or {}
        if isinstance(fbc, dict) and fbc.get("device_error") and not summ.get("ok"):
            st = summ.get("failures_by_stage") or {}
            return {"code": DEVICE_ERROR_HR, "stage": next(iter(st), None) if isinstance(st, dict) else None,
                    "class": "device_error", "why": f"{fbc.get('device_error')} cycles device_error, none ok"}
    if streaming and run.get("timed_out") and not run.get("lock_timed_out"):
        return {"code": "timeout", "stage": "process", "class": "hung_process",
                "why": "streaming command killed at its timeout"}
    return None


def command_failed(obj: Any, run: dict | None = None) -> tuple[bool, dict]:
    """(failed, error dict) for one camera command's JSON + run record, for the suite-wide first-failure record.

    Failed = ``ok`` False; a non-empty ``error`` dict (the wincam ``controls`` JSON has no ``ok`` key: a timed-out
    query carries only ``error`` and ``exit_code`` 5); ``device_not_answering``; an ``exit_code`` or process rc not
    in {0, None}; or the command killed at its timeout. Not failed: a format fallback (PyAV / dshow negotiated raw
    video instead of MJPEG with frames delivered: a negotiation result the tests rate, not a camera failure) and a
    camera-lock timeout (no camera call was made)."""
    run = run or {}
    if run.get("lock_timed_out") or run.get("dry_run") or run.get("gate_skipped"):
        return False, {}
    err = obj.get("error") if isinstance(obj, dict) else None
    err = err if isinstance(err, dict) else {}
    if isinstance(obj, dict) and (obj.get("format_fallback") is True or err.get("stage") == "format"):
        return False, {}
    failed = bool(run.get("timed_out")) or run.get("rc") not in (0, None)
    if isinstance(obj, dict):
        failed = failed or obj.get("ok") is False or bool(err) or obj.get("device_not_answering") is True or \
            obj.get("exit_code") not in (0, None)
    return failed, err


def device_level_failure(obj: Any, run: dict | None = None, err: dict | None = None) -> bool:
    """Is a failed camera command (command_failed True) a DEVICE-level failure (open / stream error, timeout,
    0x8007001F, unanswered control GETs)? False only when the command streamed every time and failed on its own
    checks: no error detail (no hr / errno / class / stage), not timed out, and every cycle streamed
    (``summary.streamed_ok == summary.cycles_run``) or a single run delivered frames (``streamed_ok`` / frames).
    Smoke 2026-11-09: opencv_ds cycle exit 4 because the Kiyo negotiated YUY2 instead of MJPG (all cycles
    streamed) had become the Kiyo's 'first failure'."""
    run = run or {}
    err = err if isinstance(err, dict) else {}
    if run.get("timed_out") or run.get("killed") or not isinstance(obj, dict):
        return True
    if obj.get("device_not_answering") is True or obj.get("unreleasable") is True:
        return True
    if any(err.get(k) not in (None, "") for k in ("hr", "errno", "class", "stage", "code_hex")):
        return True
    summ = obj.get("summary") if isinstance(obj.get("summary"), dict) else {}
    n_run, n_streamed = summ.get("cycles_run"), summ.get("streamed_ok")
    if isinstance(n_run, int) and n_run > 0 and isinstance(n_streamed, int):
        return n_streamed < n_run
    fr = obj.get("frames")
    total = fr.get("total") if isinstance(fr, dict) else fr
    streamed = obj.get("streamed_ok") is True or (isinstance(total, int) and not isinstance(total, bool) and total > 0)
    return not streamed


def _is_pymf_cli(x: Any) -> bool:
    p = Path(str(x))
    return p.name.lower() == "cli.py" and p.parent.name.lower() == "pymf"


def is_streaming_argv(argv: Sequence[Any]) -> bool:
    """True for commands that stream a camera: wincam / pymf capture and cycle, and the STREAM_TOOLS helpers
    (pyav_ds.py, opencv_ds.py, raw_ds.py, opencv_ctrl.py, ffmpeg)."""
    a = [str(x) for x in argv]
    for i, x in enumerate(a):
        base = Path(x).name.lower()
        if base in ("wincam.exe", "wincam") or _is_pymf_cli(x):
            return i + 1 < len(a) and a[i + 1] in STREAM_WINCAM_SUBCOMMANDS
        if base in STREAM_TOOLS:
            return True
    return False


def camera_for_argv(cameras: Sequence[dict], argv: Sequence[Any]) -> dict | None:
    """The one camera whose MF symlink or DS DevicePath occurs in argv; None if none or several match."""
    text = "\n".join(str(a) for a in argv).lower()
    hits = [c for c in cameras
            if any(lk and str(lk).lower() in text for lk in (c.get("mf_symlink"), c.get("ds_path")))]
    return hits[0] if len(hits) == 1 else None


def _argv_value(argv: Sequence[str], flag: str) -> str | None:
    a = list(argv)
    if flag in a:
        i = a.index(flag)
        return a[i + 1] if i + 1 < len(a) else None
    return None


def _argv_mode(argv: Sequence[str]) -> str | None:
    """'<subtype> WxH@fps' from a capture argv: wincam/pymf --subtype, OpenCV --fourcc, FFmpeg --pixel-format,
    else MJPG (the suite's default streaming subtype)."""
    w, h, f = _argv_value(argv, "--width"), _argv_value(argv, "--height"), _argv_value(argv, "--fps")
    sub = (_argv_value(argv, "--subtype") or _argv_value(argv, "--fourcc") or _argv_value(argv, "--pixel-format")
           or "MJPG")
    return f"{sub} {w}x{h}@{f}" if w and h else None


def _argv_api(argv: Sequence[str]) -> str | None:
    names = " ".join(Path(str(x)).name.lower() for x in argv)
    if "pyav_ds.py" in names:
        return "ds"
    if "opencv_ds.py" in names or "opencv_ctrl.py" in names:
        return "opencv"
    if any(_is_pymf_cli(x) for x in argv):
        return "pymf"
    return _argv_value(argv, "--api")


def _slug(cam: dict) -> str:
    nm = re.sub(r"[^a-z0-9]+", "", str(cam.get("name") or "cam").lower())[:14] or "cam"
    return f"{nm}_{cam.get('vid')}-{cam.get('pid')}"


def _probe_mode(ctx: "SuiteCtx", cam: dict, mode: Any = None) -> tuple[int, int, float] | str:
    """(w, h, fps) for the 1-frame health probe: the given mode (the calling test's in-scope streaming mode), else
    the camera's in-scope default MJPEG mode from the run's cached format list (capkit.scoped_default: exactly 720
    lines at >= 30 fps by default, Dom 2026-11-08). A string (why) when there is no in-scope mode or no format list:
    the probe then streams nothing (never an out-of-scope fallback such as 640x480)."""
    if mode is not None and getattr(mode, "w", None):
        return int(mode.w), int(mode.h), float(mode.fps)
    try:
        import capkit as ck  # noqa: PLC0415 - lazy: capkit imports this module
        fm, _ = ck.get_formats(ctx, cam)
        if fm is None:
            return "probe untested (no format list for this camera)"
        m, rec = ck.scoped_default(ctx, ck.mjpeg_modes(fm))
        if m is not None:
            return m.w, m.h, m.fps
        return f"probe untested (no in-scope mode): {rec.get('untested_reason') or 'no MJPEG mode in scope'}"
    except Exception as e:  # noqa: BLE001
        return f"probe untested (format list failed: {e!r})"


def scan_result_for_faults(test: str, result: dict, cameras: Sequence[dict] = ()) -> dict:
    """Backstop / offline scan of one test result: {key: first fault-like record} under measurements.cameras.<key>
    (a dict whose ``error`` is device_error / a hung release, or with ``unreleasable`` true), in document order.
    The command time comes from a sibling ``utc``/``utc_started`` or from <out_dir>/summary.json when present."""
    out: dict = {}
    cams = ((result or {}).get("measurements") or {}).get("cameras") or {}
    if not isinstance(cams, dict):
        return out
    for k, sub in cams.items():
        if isinstance(sub, (dict, list)):
            hit = _walk_fault(sub, [], None)
            if hit:
                hit["test"] = test
                out[k] = hit
    return out


def _walk_fault(o: Any, path: list, mode: Any) -> dict | None:
    if isinstance(o, dict):
        mode = o.get("mode") if isinstance(o.get("mode"), str) else mode
        err = o.get("error") if isinstance(o.get("error"), dict) else None
        cls = None
        if err and is_device_error(err):
            cls = "device_error"
        elif (err and is_release_hang(err)) or o.get("unreleasable") is True:
            cls = "unreleasable"
        if cls:
            utc = o.get("utc") or o.get("utc_started")
            od = o.get("out_dir")
            if not utc and od:
                try:
                    utc = json.loads((Path(od) / "summary.json").read_text(encoding="utf-8")).get("utc_started")
                except (OSError, ValueError):
                    utc = None
            e = err or {}
            return {"class": cls, "code": _norm_hr(e.get("hr")) or ("timeout" if cls == "unreleasable" else None),
                    "stage": e.get("stage"), "api": o.get("api"), "mode": mode, "utc": utc,
                    "path": "/".join(map(str, path))}
        for kk, v in o.items():
            if kk in ("before", "after", "arrivals"):
                continue
            h = _walk_fault(v, path + [kk], mode)
            if h:
                return h
    elif isinstance(o, list):
        for i, v in enumerate(o):
            h = _walk_fault(v, path + [i], mode)
            if h:
                return h
    return None


# ============================================================================================================ camcmd
def camcmd_run(argv: Sequence[Any], timeout_s: float, cwd=None, env=None, camlock_timeout_s: float = 600.0,
               log=None) -> dict:
    """Run ``argv`` as
        uv run --script tools/camlock.py --timeout-s <camlock_timeout_s> -- <python.exe> helpers/timed_run.py
               --timeout-s <timeout_s> -- argv...
    The camera command is killed (whole tree) after ``timeout_s`` measured from when the LOCK WAS ACQUIRED; the
    outer process is killed only if lock wait + timeout + 90 s slack passes. Never raises.

    Returns the procutil.run fields describing the CAMERA COMMAND (rc, stdout, stderr, elapsed_s, timed_out,
    killed, kill_method, spawn_error) plus: lock_wait_s, camlock_rc, lock_timed_out, outer {rc, elapsed_s,
    timed_out, argv}, inner (the timed_run record) and argv (the camera command).
    """
    argv = [str(a) for a in argv]
    outer_argv = ["uv", "run", "--script", str(CAMLOCK), "--timeout-s", str(int(camlock_timeout_s)), "--",
                  sys.executable, str(TIMED_RUN), "--timeout-s", str(float(timeout_s)), "--", *argv]
    t0 = time.time()
    outer = procutil.run(outer_argv, timeout_s=camlock_timeout_s + float(timeout_s) + 90.0, cwd=cwd, env=env)
    inner = None
    kept = []
    for line in (outer.get("stderr") or "").splitlines():
        if line.startswith(TIMED_MARK):
            try:
                inner = json.loads(line[len(TIMED_MARK):].strip())
            except ValueError:
                inner = {"parse_error": line}
            continue
        kept.append(line)
    stderr = "\n".join(kept)
    m = re.search(r"\[camlock\] acquired after ([0-9.]+)s", stderr)
    lock_wait = float(m.group(1)) if m else (round(inner["t_start_unix"] - t0, 3) if inner and
                                             inner.get("t_start_unix") else None)
    camlock_rc = outer.get("rc")
    lock_timed_out = camlock_rc == 75 and inner is None
    res = {
        "argv": argv,
        "rc": inner.get("rc") if inner else (None if lock_timed_out or outer.get("timed_out") else camlock_rc),
        "stdout": outer.get("stdout") or "",
        "stderr": stderr,
        "elapsed_s": inner.get("elapsed_s") if inner else outer.get("elapsed_s"),
        "timed_out": bool(inner.get("timed_out")) if inner else bool(outer.get("timed_out")),
        "killed": bool(inner.get("killed")) if inner else bool(outer.get("killed")),
        "kill_method": inner.get("kill_method") if inner else outer.get("kill_method"),
        "spawn_error": (inner.get("spawn_error") if inner else None) or outer.get("spawn_error"),
        "pid": inner.get("pid") if inner else None,
        "lock_wait_s": lock_wait,
        "camlock_rc": camlock_rc,
        "lock_timed_out": lock_timed_out,
        "outer": {k: outer.get(k) for k in ("rc", "elapsed_s", "timed_out", "killed", "kill_method")},
        "inner": inner,
        "timeout_s": float(timeout_s),
    }
    if log:
        state = "TIMEOUT" if res["timed_out"] else f"rc={res['rc']}"
        log(f"camcmd {state} {res['elapsed_s']}s (lock wait {lock_wait}s): {_short(argv)}")
    return res


def _short(argv: Sequence[str], n: int = 160) -> str:
    s = " ".join(Path(a).name if i == 0 else a for i, a in enumerate(argv))
    return s if len(s) <= n else s[:n] + "..."


def parse_json_stdout(r: dict) -> tuple[dict | None, str | None]:
    """Parse one JSON object from a command's stdout (the last {...} block if there is noise). (obj, error)."""
    out = (r.get("stdout") or "").strip()
    if not out:
        return None, "empty stdout"
    try:
        return json.loads(out), None
    except ValueError:
        pass
    i = out.find("{")
    j = out.rfind("}")
    if 0 <= i < j:
        try:
            return json.loads(out[i:j + 1]), None
        except ValueError as e:
            return None, f"JSON parse error: {e}"
    return None, "no JSON object in stdout"


# ============================================================================================================ args/ctx
def add_common_args(ap: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """The contract's args (quick, only, skip, cycles, proc_cycles, frames, mjpeg_seconds) plus out/raw dirs.
    (``--flash`` was removed 2026-11-09: its W-TS route recorded UVC PTS/SCR metadata, out of the tier-0 scope.)
    run_suite.py may define its own parser instead; build_ctx only needs these attribute names to exist."""
    ap.add_argument("--quick", action="store_true", help="fewer repeats/modes (smoke run)")
    ap.add_argument("--only", default="", help="comma list of test ids to run, e.g. W-ENV,W-ID")
    ap.add_argument("--skip", default="", help="comma list of test ids to skip")
    ap.add_argument("--cycles", type=int, default=20, help="in-process open/close cycles per camera")
    ap.add_argument("--proc-cycles", dest="proc_cycles", type=int, default=10, help="process-per-cycle cycles")
    ap.add_argument("--frames", type=int, default=30, help="frames per cycle")
    ap.add_argument("--mjpeg-seconds", dest="mjpeg_seconds", type=float, default=3.0)
    ap.add_argument("--out-dir", dest="out_dir", default=None)
    ap.add_argument("--raw-dir", dest="raw_dir", default=None)
    ap.add_argument("--wincam", default=None)
    ap.add_argument("--repeats", type=int, default=20, help="W-ID enumeration repeats")
    ap.add_argument("--no-fault-gate", dest="no_fault_gate", action="store_true",
                    help="do not skip streaming work on cameras marked faulted (faults are still recorded)")
    modescope.add_args(ap)      # --min-fps 30 / --min-height 720 / --all-modes (streaming tests only)
    return ap


def default_args(**over) -> argparse.Namespace:
    ns = add_common_args(argparse.ArgumentParser()).parse_args([])
    for k, v in over.items():
        setattr(ns, k, v)
    return ns


def build_ctx(args: argparse.Namespace | None = None, out_dir: str | os.PathLike | None = None,
              raw_dir: str | os.PathLike | None = None, wincam: str | os.PathLike | None = None,
              cameras: list[dict] | None = None, log_to_stderr: bool = True) -> SuiteCtx:
    """Create the SuiteCtx: resolve folders, then discover cameras (child process, no camera opened) unless
    ``cameras`` is given. The discovery record is written to <out_dir>/discovery.json."""
    args = args or default_args()
    stamp = results.utc_stamp()
    od = Path(out_dir or getattr(args, "out_dir", None) or results.default_results_dir(stamp)).resolve()
    rd = Path(raw_dir or getattr(args, "raw_dir", None) or results.default_raw_dir(od)).resolve()
    wc = Path(wincam or getattr(args, "wincam", None) or WINCAM_DEFAULT).resolve()
    od.mkdir(parents=True, exist_ok=True)
    rd.mkdir(parents=True, exist_ok=True)
    ctx = SuiteCtx(out_dir=od, raw_dir=rd, args=args, cameras=[], wincam=wc, stamp=stamp)
    ctx.fault_gate = not bool(getattr(args, "no_fault_gate", False))
    if cameras is not None:
        ctx.cameras = cameras
    else:
        ctx.log(f"discovering cameras (wincam {wc}{'' if wc.exists() else ' MISSING'})")
        d = discover(wc, log=ctx.log)
        ctx.discovery = d
        ctx.cameras = d.get("cameras", [])
        ctx.write("discovery", d)
        for c in ctx.cameras:
            ctx.log(f"camera {c['key']} '{c.get('name')}' speed={c.get('speed')} kiyo={c.get('is_kiyo')} "
                    f"metadata_tier1={c.get('metadata_tier1')} dn_warn={c.get('dn_warn')}")
    return ctx


# ============================================================================================================ discovery
def discover(wincam: str | os.PathLike | None = None, timeout_s: float = 90.0, log=None) -> dict:
    """Camera discovery in a child process (bounded). Never raises; on failure returns {'cameras': [], 'errors'}."""
    wc = str(Path(wincam or WINCAM_DEFAULT))
    r = procutil.run([sys.executable, str(Path(__file__).resolve()), "--discover", "--wincam", wc],
                     timeout_s=timeout_s)
    obj, err = parse_json_stdout(r)
    if obj is None:
        msg = f"discovery child failed: rc={r['rc']} timed_out={r['timed_out']} {err}; stderr={r['stderr'][-800:]}"
        if log:
            log(msg)
        return {"cameras": [], "errors": [msg], "child": {k: r[k] for k in ("rc", "elapsed_s", "timed_out")}}
    obj["child"] = {k: r[k] for k in ("rc", "elapsed_s", "timed_out")}
    return obj


def _speed_label(conn: dict | None) -> str:
    if not conn:
        return "unknown"
    v2 = conn.get("v2_flags") or {}
    if v2.get("op_ssp"):
        return "SS+"
    if v2.get("op_ss"):
        return "SS"
    return {"low": "LS", "full": "FS", "high": "HS", "super": "SS"}.get(conn.get("legacy_speed"), "unknown")


def wincam_list(wincam: str | os.PathLike, timeout_s: float = 30.0) -> dict:
    """`wincam list` (enumeration only: no ActivateObject, no BindToObject; no camera lock needed)."""
    wc = Path(wincam)
    if not wc.exists():
        return {"error": f"wincam not found at {wc}", "mf": None, "ds": None}
    r = procutil.run([str(wc), "list"], timeout_s=timeout_s)
    obj, err = parse_json_stdout(r)
    if obj is None:
        return {"error": f"wincam list failed rc={r['rc']} timed_out={r['timed_out']}: {err}", "mf": None, "ds": None,
                "stderr": r["stderr"][-500:]}
    obj["_run"] = {k: r[k] for k in ("rc", "elapsed_s", "timed_out")}
    return obj


def _is_video_function(props: dict) -> bool:
    return any(str(c).upper().startswith(("USB\\CLASS_0E&SUBCLASS_01", "USB\\CLASS_0E&SUBCLASS_03"))
               for c in props.get("CompatibleIds", []) or [])


def _discover_inproc(wincam: str | os.PathLike | None) -> dict:
    """The discovery itself (run in the child). Uses winpnp (CfgMgr32 + cached hub IOCTLs + registry reads)."""
    import winpnp as wp
    t0 = time.perf_counter()
    errors: list[str] = []
    wl = wincam_list(wincam) if wincam else {"error": "no wincam given", "mf": None, "ds": None}
    if wl.get("error"):
        errors.append(wl["error"])
    funcs: dict[str, dict] = {}   # function instance id (upper) -> record

    def rec_for(fid: str) -> dict:
        return funcs.setdefault(fid.upper(), {"function_instance_id": fid, "sources": []})

    virtual = []
    for api, key_path in (("mf", "symlink"), ("ds", "device_path")):
        lst = (wl.get(api) or {}).get("devices") or []
        for d in lst:
            link = d.get(key_path)
            usb = d.get("usb") or {}
            if not link or not usb.get("vid"):
                virtual.append({"api": api, "index": d.get("index"), "friendly_name": d.get("friendly_name"),
                                "link": link})
                continue
            fid = wp.iface_instance(link) or wp.link_to_instance_id(link)
            r = rec_for(fid)
            r["sources"].append(f"wincam_{api}")
            if api == "mf":
                r.update(mf_index=d.get("index"), mf_name=d.get("friendly_name"), mf_symlink=link)
            else:
                r.update(ds_index=d.get("index"), ds_name=d.get("friendly_name"), ds_path=link,
                         ds_clsid_is_ksproxy=d.get("clsid_is_ksproxy"))
    # PnP interface lists (catch cameras wincam missed, or no wincam)
    for cat, fld in (("KSCATEGORY_VIDEO_CAMERA", "pnp_mf_symlink"), ("KSCATEGORY_CAPTURE", "pnp_ds_path")):
        for path in wp.iface_list(wp.GUIDS[cat]):
            fid = wp.iface_instance(path)
            if not fid or not fid.upper().startswith("USB\\"):
                continue
            dn = wp.locate(fid)
            if dn is None:
                continue
            p = wp.devnode_props(dn, ["CompatibleIds"], status=False)
            if not _is_video_function(p) and "&MI_" in fid.upper():
                # e.g. a USB audio function exposing KSCATEGORY_CAPTURE: not a camera
                continue
            if fid.upper() not in funcs and not _is_video_function(p):
                continue
            r = rec_for(fid)
            r["sources"].append(f"pnp_{cat}")
            r[fld] = path
    cams = []
    for fid_u, r in funcs.items():
        fid = r["function_instance_id"]
        fdn = wp.locate(fid)
        if fdn is None:
            errors.append(f"cannot locate devnode {fid}")
            continue
        fprops = wp.devnode_props(fdn, ["FriendlyName", "DeviceDesc", "Service", "CompatibleIds", "LastArrivalDate"])
        udn = wp.parent(fdn) if "&MI_" in fid.upper() else fdn
        uprops = wp.devnode_props(udn, ["InstanceId", "LocationPaths", "LocationInfo", "Address", "ContainerId",
                                        "BusReportedDeviceDesc", "Service", "DriverVersion", "DriverProvider",
                                        "DriverInfPath", "LastArrivalDate", "LastRemovalDate", "FirstInstallDate",
                                        "FriendlyName", "DeviceDesc"]) if udn else {}
        usb_iid = uprops.get("InstanceId") or fid
        hdn = wp.parent(udn) if udn else None
        hub_iid = wp.instance_id(hdn) if hdn else None
        vid, pid, _mi = wp.parse_usb_ids(usb_iid)
        port = uprops.get("Address")
        conn = None
        try:
            conn = wp.cached_port_info(hub_iid, port)
        except Exception as e:  # noqa: BLE001
            errors.append(f"cached_port_info {usb_iid}: {e!r}")
        suffix = usb_iid.split("\\")[-1]
        i_serial = (conn or {}).get("i_serial")
        if "&" not in suffix:
            serial, serial_source = suffix, "instance_id_suffix"
        elif i_serial == 0:
            serial, serial_source = None, "iSerialNumber=0"
        elif i_serial:
            serial, serial_source = None, "not_used_by_windows (iSerialNumber set, instance ID is generated)"
        else:
            serial, serial_source = None, "unknown"
        locs = uprops.get("LocationPaths") or []
        loc0 = locs[0] if locs else None
        md = wp.metadata_registry(fid)
        ds_path = r.get("ds_path") or r.get("pnp_ds_path")
        cam = {
            "key": None,
            "name": r.get("mf_name") or r.get("ds_name") or fprops.get("FriendlyName") or
            uprops.get("BusReportedDeviceDesc") or fprops.get("DeviceDesc"),
            "vid": vid, "pid": pid, "serial": serial,
            "is_kiyo": (vid, pid) == KIYO_VIDPID,
            "instance_id": usb_iid, "parent_instance_id": hub_iid,
            "mf_symlink": r.get("mf_symlink") or r.get("pnp_mf_symlink"),
            "ds_name": r.get("ds_name"), "ds_path": ds_path,
            "location_path": loc0, "metadata_tier1": bool(md.get("tier1")),
            # extras
            "function_instance_id": fid, "hub_port": port,
            "port_path": identity.port_path_from_windows_location_paths(loc0),
            "serial_source": serial_source, "i_serial": i_serial,
            "bcd_device": (conn or {}).get("bcd_device"), "bcd_usb": (conn or {}).get("bcd_usb"),
            "speed": _speed_label(conn), "container_id": uprops.get("ContainerId"),
            "location_paths": locs, "location_info": uprops.get("LocationInfo"),
            "mf_index": r.get("mf_index"), "mf_name": r.get("mf_name"),
            "ds_index": r.get("ds_index"),
            "ds_ffmpeg_name": ("@device_pnp_" + ds_path) if ds_path else None,
            "opencv_dshow_index": r.get("ds_index"), "opencv_msmf_index": r.get("mf_index"),
            "ds_clsid_is_ksproxy": r.get("ds_clsid_is_ksproxy"),
            "metadata_registry": md,
            "last_arrival": uprops.get("LastArrivalDate"), "last_removal": uprops.get("LastRemovalDate"),
            "first_install": uprops.get("FirstInstallDate"),
            "function_last_arrival": fprops.get("LastArrivalDate"),
            "problem_code": uprops.get("ProblemCode"), "devnode_status": uprops.get("DevNodeStatus"),
            "dn_flags": uprops.get("flags"), "dn_warn": sorted(set((uprops.get("warn") or []) +
                                                                  (fprops.get("warn") or []))),
            "function_problem_code": fprops.get("ProblemCode"), "function_devnode_status": fprops.get("DevNodeStatus"),
            "service": uprops.get("Service"), "function_service": fprops.get("Service"),
            "driver_version": uprops.get("DriverVersion"), "driver_provider": uprops.get("DriverProvider"),
            "device_parameters": wp.reg_values(f"SYSTEM\\CurrentControlSet\\Enum\\{usb_iid}\\Device Parameters"),
            "function_device_parameters": wp.reg_values(
                f"SYSTEM\\CurrentControlSet\\Enum\\{fid}\\Device Parameters"),
            "port_connection": {k: v for k, v in (conn or {}).items() if k not in ("driver_key",)},
            "sources": sorted(set(r["sources"])),
        }
        cams.append(cam)
    identity.assign_keys(cams)   # serial unique within VID:PID, else port path (naming/camera_identity.py rules)
    for c in cams:
        ident = identity.camera_identity(c["vid"], c["pid"], c["serial"], c["port_path"],
                                         [(x["vid"], x["pid"], x["serial"]) for x in cams])
        c["serial_reason"] = ident["reason"]
    cams.sort(key=lambda c: (c.get("mf_index") if c.get("mf_index") is not None else 999,
                             c.get("ds_index") if c.get("ds_index") is not None else 999, c["key"]))
    return {"utc": results.utc_now_iso(), "hostname": socket.gethostname(), "elevated": wp.is_elevated(),
            "elapsed_s": round(time.perf_counter() - t0, 4), "wincam": str(wincam) if wincam else None,
            "wincam_list": {k: v for k, v in wl.items() if k not in ()}, "cameras": cams, "virtual_devices": virtual,
            "errors": errors,
            "note": "no camera opened: wincam list reads property bags only; CfgMgr32 + cached hub IOCTLs + registry "
                    "reads"}


# ============================================================================================================ arrivals
def arrival_snapshot(cameras: list[dict]) -> dict:
    """{key: {instance_id, present, last_arrival, problem_code, devnode_status, dn_warn}} read now (CfgMgr only).
    Plan section 6.1: log LastArrivalDate per camera before and after each test; flag unexplained re-arrivals."""
    try:
        import winpnp as wp
    except ImportError as e:
        return {"error": repr(e)}
    snap = {"utc": results.utc_now_iso(), "cameras": {}}
    for c in cameras:
        iid = c.get("instance_id")
        dn = wp.locate(iid) if iid else None
        if dn is None:
            snap["cameras"][c["key"]] = {"instance_id": iid, "present": False}
            continue
        p = wp.devnode_props(dn, ["LastArrivalDate", "LastRemovalDate"])
        snap["cameras"][c["key"]] = {"instance_id": iid, "present": True, "last_arrival": p.get("LastArrivalDate"),
                                     "last_removal": p.get("LastRemovalDate"), "problem_code": p.get("ProblemCode"),
                                     "devnode_status": p.get("DevNodeStatus"), "dn_warn": p.get("warn")}
    return snap


SUPERSPEED = ("SS", "SS+")


def link_record(cam: dict, conn: dict | None, last_arrival: Any, now: _dt.datetime | None = None,
                source: str = "discovery") -> dict:
    """One camera's USB link: negotiated speed (hub IOCTL CONNECTION_INFORMATION_EX legacy speed + _V2 operating
    flags, cached hub state), bcdUSB, the port's protocols and SuperSpeed capability, LastArrivalDate, plug-in age."""
    conn = conn or {}
    v2 = conn.get("v2_flags") or {}
    speed = _speed_label(conn) if conn else (cam.get("speed") or "unknown")
    return {"key": cam.get("key"), "name": cam.get("name"), "vid": cam.get("vid"), "pid": cam.get("pid"),
            "is_kiyo": bool(cam.get("is_kiyo")), "speed": speed, "superspeed": speed in SUPERSPEED,
            "legacy_speed": conn.get("legacy_speed"), "operating_superspeed": v2.get("op_ss"),
            "operating_superspeed_plus": v2.get("op_ssp"), "port_superspeed_capable": v2.get("ss_capable"),
            "port_protocols": conn.get("port_protocols"),
            "bcd_usb": conn.get("bcd_usb") or cam.get("bcd_usb"),
            "device_usb3_capable": (str(conn.get("bcd_usb") or cam.get("bcd_usb") or "")[:2] in ("03", "3"))
            if (conn.get("bcd_usb") or cam.get("bcd_usb")) else None,
            "hub": cam.get("parent_instance_id"), "hub_port": cam.get("hub_port"), "port_path": cam.get("port_path"),
            "last_arrival": last_arrival, "plug_in_age_s": age_s(last_arrival, now=now), "source": source}


def kiyo_link_warning(rec: dict) -> str | None:
    """The runner's start-of-run warning for a Kiyo that is not at SuperSpeed (None when it is)."""
    if not rec.get("is_kiyo") or rec.get("superspeed"):
        return None
    age = rec.get("plug_in_age_s")
    return (f"WARNING: Razer Kiyo Pro {rec.get('key')} negotiated {rec.get('speed')} (not SuperSpeed) at port "
            f"{rec.get('port_path') or rec.get('hub_port')}: it is not on a USB 3 port (or the cable / hub limits it "
            f"to USB 2.0); its results describe USB 2.0 operation. bcdUSB {rec.get('bcd_usb')}, port protocols "
            f"{rec.get('port_protocols')}, plug-in age "
            f"{'unknown' if age is None else f'{age / 60:.1f} min'}. The run continues.")


def usb_link_report(cameras: Sequence[dict], fresh: bool = False, now: _dt.datetime | None = None) -> dict:
    """Per camera: negotiated USB speed, port capability, LastArrivalDate and plug-in age, plus the Kiyo check.

    ``fresh=False`` uses the discovery values (read at run start in the discovery child). ``fresh=True`` re-reads the
    hub's cached connection info (IOCTL 274/279: answered from hub-driver state, no device request) and the
    LastArrivalDate (CfgMgr) now; a camera whose re-read fails falls back to its discovery values. Opens no camera.
    Returns {"utc", "fresh", "cameras": {key: record}, "kiyo": {key: record}, "warnings": [...]}."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    wp = None
    if fresh:
        try:
            import winpnp as wp  # noqa: PLC0415
        except ImportError:
            wp = None
    out: dict = {"utc": now.isoformat(), "fresh": bool(fresh and wp is not None), "cameras": {}, "kiyo": {},
                 "warnings": []}
    for c in cameras:
        conn, la, src = c.get("port_connection"), c.get("last_arrival"), "discovery"
        if wp is not None:
            try:
                fc = wp.cached_port_info(c.get("parent_instance_id"), c.get("hub_port"))
                if isinstance(fc, dict) and not fc.get("error"):
                    conn, src = fc, "hub IOCTL now"
                dn = wp.locate(c["instance_id"]) if c.get("instance_id") else None
                if dn is not None:
                    la = wp.devnode_props(dn, ["LastArrivalDate"], status=False).get("LastArrivalDate") or la
            except Exception as e:  # noqa: BLE001 - fall back to the discovery values
                src = f"discovery (fresh read failed: {e!r})"
        rec = link_record(c, conn, la, now=now, source=src)
        out["cameras"][c.get("key")] = rec
        if rec["is_kiyo"]:
            out["kiyo"][c.get("key")] = rec
            w = kiyo_link_warning(rec)
            if w:
                out["warnings"].append(w)
    return out


def diff_arrivals(before: dict, after: dict) -> list[dict]:
    """Cameras whose presence, LastArrivalDate or problem state changed between two snapshots."""
    out = []
    b, a = before.get("cameras", {}), after.get("cameras", {})
    for k in sorted(set(b) | set(a)):
        x, y = b.get(k, {}), a.get(k, {})
        ch = {f: (x.get(f), y.get(f)) for f in ("present", "last_arrival", "problem_code", "dn_warn")
              if x.get(f) != y.get(f)}
        if ch:
            out.append({"key": k, "changes": ch, "re_arrival": "last_arrival" in ch})
    return out


# ============================================================================================================ CLI
def _main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--discover", action="store_true", help="print the discovery JSON (opens no camera)")
    ap.add_argument("--wincam", default=str(WINCAM_DEFAULT))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if not a.discover:
        ap.print_help()
        return 2
    d = _discover_inproc(a.wincam)
    text = results.to_json_text(d)
    if a.out:
        results.write_json(a.out, d)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
