# /// script
# requires-python = "==3.12.13"
# dependencies = [
#   "pyobjc-core==13.0; sys_platform == 'darwin'",
#   "pyobjc-framework-Cocoa==13.0; sys_platform == 'darwin'",
#   "pyobjc-framework-AVFoundation==13.0; sys_platform == 'darwin'",
#   "pyobjc-framework-CoreAudio==13.0; sys_platform == 'darwin'",
#   "pyobjc-framework-CoreMedia==13.0; sys_platform == 'darwin'",
#   "pyobjc-framework-Quartz==13.0; sys_platform == 'darwin'",
#   "pyobjc-framework-libdispatch==13.0; sys_platform == 'darwin'",
#   "libusb1==3.4.0; sys_platform == 'darwin'",
#   "numpy==2.2.6",
#   "pillow==12.0.0",
#   "simplejpeg==1.8.2",
# ]
# ///
"""macOS UVC test suite runner (docs/xplat_capture_plan.md sections 2.5 and 6; plan_20261106/macos.md).

Normally started by run_suite.sh (records sw_vers / arch / model first). Direct use:

    uv run --python 3.12.13 --script research/usb_cameras/suite/macos/run_suite.py [flags]
    uv run --python 3.12.13 --script research/usb_cameras/suite/macos/run_suite.py --dry-run
    bash research/usb_cameras/suite/macos/run_suite.sh --plan      # the capture-plan preset (RUNBOOK_PLAN.md)

--plan (2026-11-17): only what the native-MJPEG capture plan needs, ~20-30 min with four cameras: M-ENV, M-TCC,
M-TOPO, M-ID, M-FMT, M-CTRL-LIST, M-MJPEG (720-line modes at 30 and at the top rate, variants nil/{}/dmb1/chromium),
M-CYC (20 in-process cycles, nothing else), M-CTRL-EFFECT (AVFoundation locks only, one run), M-MULTI (all cameras
together for 90 s, once), M-TS (30 s, tier 0), all with endpoint 0 OFF. Then, after every one of their JSON files
and a first summary.md are written, the endpoint-0 phase (~1 min per camera; --no-ep0 skips it): M-CTRL-LIST and
M-CTRL-EFFECT again for their endpoint-0 halves only (advertised selectors; AE manual, exposure x3, gain x3, WB x3,
focus x3, readback, image effect, set before start, read after close, restore), backend iokit-intf only, into
m_ctrl_list_ep0.json / m_ctrl_effect_ep0.json; summary.md is then rewritten with that section. Asks for Camera
permission at the start. Results go to results/macos/plan/suite_<stamp>/ (no hostname), are scrubbed of
host/user/home names, and summary.md (also printed at the end) is the short pasteable digest.

This process imports only the standard library and suite/common. PyObjC is imported only inside the camera
child processes (helpers/mac_avf.py), which this runner starts with its own interpreter (the PEP 723
environment above has their dependencies), so ``--help`` and ``--dry-run`` work on any OS without PyObjC.

Tests, in run order (M- prefix; reduced suite for Intel Macs and macOS 15 marked *):
  M-ENV*  M-TCC*  M-TOPO*  M-ID*  M-FMT*  M-FMT-NOGRAB*  M-CTRL-LIST*  M-MJPEG*  M-CYC*  M-CTRL-EFFECT  M-MULTI  M-TS
  M-FX  M-KIYO

Mode scope (plan 6, Dom 2026-11-08): the streaming tests (M-MJPEG, M-CYC, M-MULTI, M-TS, M-CTRL-EFFECT) use only
modes with exactly 720 lines at >= 30 fps (--min-fps 30, --min-height 720, --max-height 720; --max-height 0 = no
upper bound); --all-modes disables the filter. Listing tests (M-FMT,
M-CTRL-LIST, M-FMT-NOGRAB) still list and compare every mode. Each streaming test records the scope and the number
of advertised modes it excluded (measurements.mode_scope).

Endpoint-0 UVC requests (descriptors, UVC control ranges, SET_CUR effects, GET_INTERFACE / VS_COMMIT) are OPT-IN
with --ep0, because they work outside Apple's documented contract (see helpers/mac_ep0.py). Without --ep0 the
CTRL tests use AVFoundation only and FMT has no descriptor side unless an earlier endpoint-0 run cached them.
--plan ignores --ep0 for its tests and runs its own endpoint-0 phase afterwards (above).

Rules (plan 6.1): no driver change (no claim, no detach, no seize unless --ep0-backend libusb is chosen, which
the operator opts into separately), all cameras as found including the Razer Kiyo Pro, every camera call in a
child process with a timeout, re-arrivals logged per test from the IORegistry entry IDs.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import sys
import time
import traceback
from pathlib import Path
from typing import Any

MACOS_DIR = Path(__file__).resolve().parent
SUITE_DIR = MACOS_DIR.parent
RESEARCH_DIR = SUITE_DIR.parent
for _p in (str(SUITE_DIR), str(MACOS_DIR), str(MACOS_DIR / "helpers")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from common import results  # noqa: E402
import suitectx  # noqa: E402

TESTS = [  # (name, module, in reduced suite, opens a camera)
    ("M-ENV", "m_env", True, False),
    ("M-TCC", "m_tcc", True, True),
    ("M-TOPO", "m_topo", True, False),
    ("M-ID", "m_id", True, False),
    ("M-FMT", "m_fmt", True, False),
    ("M-FMT-NOGRAB", "m_fmt_nograb", True, True),
    ("M-CTRL-LIST", "m_ctrl_list", True, False),
    ("M-MJPEG", "m_mjpeg", True, True),
    ("M-CYC", "m_cyc", True, True),
    ("M-CTRL-EFFECT", "m_ctrl_effect", False, True),
    ("M-MULTI", "m_multi", False, True),
    ("M-TS", "m_ts", False, True),
    ("M-FX", "m_fx", False, True),
    ("M-KIYO", "m_kiyo", False, True),
]
# camera-opening tests that handle missing Camera permission themselves (they still measure what needs no stream)
SELF_GATED = {"M-TCC", "M-FMT-NOGRAB"}
CAMLOCK_PATH = RESEARCH_DIR / ".camlock"
MJPEG_VARIANTS = ("nil", "empty", "dmb1", "chromium", "jpeg4cc", "dmb1_sized")  # = helpers/mac_avf.py VARIANTS


def load_test_module(mod: str):
    """Import tests/<mod>.py by path (a top-level package called 'tests' elsewhere on sys.path cannot shadow it)."""
    import importlib.util
    name = f"skellycam_macos_suite_{mod}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, MACOS_DIR / "tests" / f"{mod}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


# ================================================================================================ arguments
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="run_suite.py", description="macOS UVC capture test suite (plan section 6). Unattended tests only.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Test names for --only/--skip: " + ", ".join(t[0] for t in TESTS) + " (the M- prefix is optional).")
    g = ap.add_argument_group("selection")
    g.add_argument("--only", default="", help="comma list of tests to run")
    g.add_argument("--skip", default="", help="comma list of tests to skip")
    g.add_argument("--full", action="store_true", help="run the full suite even on Intel / macOS < 26")
    g.add_argument("--reduced", action="store_true", help="run the reduced suite (plan 2.5 legs M3/M4)")
    g.add_argument("--quick", action="store_true", help="fewer cycles, modes and seconds (a smoke run)")
    g.add_argument("--list-tests", action="store_true")
    g.add_argument("--plan", action="store_true", help="capture-plan preset: the tests and sizes the native-MJPEG "
                   "capture plan needs (~20-30 min), endpoint 0 off, then its endpoint-0 phase (--no-ep0 skips it); "
                   "results/macos/plan/suite_<stamp>/ + a pasteable summary.md")
    g.add_argument("--dry-run", action="store_true", help="print what would run; open nothing, write nothing")
    g.add_argument("--fake-ioreg", type=Path, default=None, help="dry-run: folder with ioreg_*.plist files")
    g.add_argument("--fake-avf", type=Path, default=None, help="dry-run: JSON {devices:[...]} as mac_avf list/formats")
    n = ap.add_argument_group("sizes")
    n.add_argument("--cycles", type=int, default=None, help="in-process open/close cycles per camera (20; quick 5)")
    n.add_argument("--proc-cycles", type=int, default=None, help="one-process-per-cycle cycles (10; quick 3)")
    n.add_argument("--frames", type=int, default=None, help="frames per cycle after the first (10; quick 5)")
    n.add_argument("--mjpeg-seconds", type=float, default=None, help="seconds per MJPEG cell (3; quick 1.5)")
    n.add_argument("--mjpeg-variants", default="nil,empty,dmb1,chromium",
                   help="videoSettings variants: nil, empty, dmb1, chromium (Chromium's exact dictionary: dmb1 + width "
                        "+ height + AVVideoScalingModeKey), jpeg4cc, dmb1_sized")
    n.add_argument("--mjpeg-modes", choices=["all", "ends"], default=None, help="every MJPEG format or only the "
                   "largest and smallest (all; quick ends)")
    n.add_argument("--ts-seconds", type=float, default=None, help="M-TS capture length (20; quick 8)")
    n.add_argument("--ctrl-runs", type=int, default=None, help="M-CTRL-EFFECT repetitions (3; quick 1)")
    n.add_argument("--multi-repeats", type=int, default=None, help="M-MULTI repetitions (3; quick 1)")
    n.add_argument("--multi-seconds", type=float, default=None, help="M-MULTI stream length (6; quick 4)")
    n.add_argument("--id-repeats", type=int, default=20, help="M-ID enumerations in one process (20)")
    n.add_argument("--id-proc-repeats", type=int, default=None, help="M-ID enumerations in new processes (5; quick 2)")
    n.add_argument("--kiyo-minutes", type=float, default=None, help="M-KIYO poll duration (5; quick 1)")
    n.add_argument("--kiyo-interval-s", type=float, default=10.0)
    n.add_argument("--child-timeout-scale", type=float, default=1.0, help="multiply every child timeout")
    import mac_modescope
    mac_modescope.add_args(ap)  # --min-fps 30, --min-height / --max-height 720, --all-modes: common.modescope
    ng = ap.add_argument_group("M-FMT-NOGRAB")
    ng.add_argument("--hold-ms", type=float, default=2000.0,
                   help="how long each listing method keeps its device object open for alt sampling (2000)")
    ng.add_argument("--nograb-baseline-s", type=float, default=2.0,
                   help="seconds of the other process's stream recorded as baseline before listing (2)")
    ng.add_argument("--no-nograb-block-probe", dest="nograb_block_probe", action="store_false",
                   help="skip the third-process 1-frame capture during each hold")
    ng.add_argument("--nograb-cond3", choices=["skip", "avf-dmb1"], default="skip",
                   help="condition (iii): skip (macOS has no second capture API) or a second AVFoundation process "
                        "with the dmb1 passthrough videoSettings")
    e = ap.add_argument_group("endpoint 0 (opt-in, except --plan's own endpoint-0 phase)")
    e.add_argument("--ep0", action="store_true", help="allow UVC class requests on endpoint 0 without a claim "
                   "(ignored with --plan: its tests always run with endpoint 0 off, then its endpoint-0 phase)")
    e.add_argument("--no-ep0", action="store_true", help="--plan without its endpoint-0 phase (the pre-2026-11-17 "
                   "plan run: no endpoint-0 request at all)")
    e.add_argument("--ep0-backend", choices=["iokit-intf", "iokit-dev", "libusb"], default="iokit-intf",
                   help="iokit-intf (default, no open/seize), iokit-dev (device request, no open), libusb (SEIZES)")
    e.add_argument("--ep0-allow-seize", action="store_true",
                   help="required with --ep0-backend libusb: acknowledges that libusb's darwin backend calls "
                        "USBDeviceOpenSeize on EVERY USB device while enumerating and on the camera in libusb_open "
                        "(breaks plan 6.1 'no seize'; never use on a shared machine or with the Kiyo attached)")
    o = ap.add_argument_group("other")
    o.add_argument("--flash", action="store_true", help="ground-truth rig hook (recorded; no rig driver yet)")
    o.add_argument("--edge-light-off", action="store_true", help="operator confirms Edge Light is off (recorded)")
    o.add_argument("--request-camera", action="store_true", help="ask for Camera permission (GUI prompt)")
    o.add_argument("--run-without-permission", action="store_true",
                   help="run the camera-opening tests even when Camera permission is denied / not determined "
                        "(they then record zero-frame sessions)")
    o.add_argument("--out-dir", type=Path, default=None)
    o.add_argument("--raw-dir", type=Path, default=None)
    o.add_argument("--no-camlock", action="store_true", help="do not take research/usb_cameras/.camlock")
    o.add_argument("--camlock-timeout-s", type=float, default=600.0)
    return ap


PLAN_TESTS = ("M-ENV", "M-TCC", "M-TOPO", "M-ID", "M-FMT", "M-CTRL-LIST", "M-MJPEG", "M-CYC", "M-CTRL-EFFECT",
              "M-MULTI", "M-TS")
#: --plan's endpoint-0 phase: the ep0 halves of these tests, after every phase-1 result file is written
EP0_PHASE_TESTS = ("M-CTRL-LIST", "M-CTRL-EFFECT")
EP0_PHASE = "endpoint-0 phase"
#: --plan sizes (an explicit flag still wins)
PLAN_DEFAULTS = {"cycles": 20, "proc_cycles": 0, "frames": 10, "mjpeg_seconds": 4.0, "mjpeg_modes": "all",
                 "ts_seconds": 30.0, "ctrl_runs": 1, "multi_repeats": 1, "multi_seconds": 90.0, "id_proc_repeats": 2,
                 "kiyo_minutes": 0.0}


def apply_defaults(a: argparse.Namespace) -> argparse.Namespace:
    if getattr(a, "plan", False):
        for k, v in PLAN_DEFAULTS.items():
            if getattr(a, k, None) is None:
                setattr(a, k, v)
        a.full, a.request_camera = True, True
        # isolation: every plan test runs with endpoint 0 off; the ep0 work is a separate phase afterwards
        a.ep0, a.plan_ep0 = False, not getattr(a, "no_ep0", False)
    q = a.quick
    defaults = {"cycles": (20, 5), "proc_cycles": (10, 3), "frames": (10, 5), "mjpeg_seconds": (3.0, 1.5),
                "mjpeg_modes": ("all", "ends"), "ts_seconds": (20.0, 8.0), "ctrl_runs": (3, 1),
                "multi_repeats": (3, 1), "multi_seconds": (6.0, 4.0), "id_proc_repeats": (5, 2),
                "kiyo_minutes": (5.0, 1.0)}
    for k, (full, quick) in defaults.items():
        if getattr(a, k, None) is None:
            setattr(a, k, quick if q else full)
    a.mjpeg_variant_list = [v.strip() for v in a.mjpeg_variants.split(",") if v.strip()]
    bad = [v for v in a.mjpeg_variant_list if v not in MJPEG_VARIANTS]
    if bad:
        raise SystemExit(f"unknown --mjpeg-variants {bad}; choose from {list(MJPEG_VARIANTS)}")
    return a


def norm_test(name: str) -> str:
    n = name.strip().upper().replace("_", "-")
    return n if n.startswith("M-") else f"M-{n}"


def select_tests(a: argparse.Namespace, reduced: bool) -> list[tuple]:
    only = {norm_test(x) for x in a.only.split(",") if x.strip()}
    skip = {norm_test(x) for x in a.skip.split(",") if x.strip()}
    unknown = (only | skip) - {t[0] for t in TESTS}
    if unknown:
        raise SystemExit(f"unknown test name(s): {sorted(unknown)}")
    out = []
    for t in TESTS:
        if only and t[0] not in only:
            continue
        if t[0] in skip:
            continue
        if reduced and not t[2] and not only:
            continue
        if getattr(a, "plan", False) and not only and t[0] not in PLAN_TESTS:
            continue
        out.append(t)
    return out


def ep0_phase_tests(a: argparse.Namespace, tests: list[tuple]) -> list[tuple]:
    """The tests of --plan's endpoint-0 phase (none with --no-ep0 or when neither CTRL test is selected)."""
    if not (getattr(a, "plan", False) and getattr(a, "plan_ep0", False)):
        return []
    return [t for t in tests if t[0] in EP0_PHASE_TESTS]


# ================================================================================================ machine facts
def mac_major(ver: str | None) -> int | None:
    try:
        return int(str(ver).split(".")[0])
    except (ValueError, AttributeError):
        return None


def decide_reduced(a: argparse.Namespace, prelude: dict) -> tuple[bool, str]:
    if a.full:
        return False, "--full"
    if a.reduced:
        return True, "--reduced"
    if sys.platform != "darwin" and not prelude.get("arch"):
        return False, "not macOS (dry run): the full plan is shown"
    arch = prelude.get("arch") or platform.machine()
    ver = prelude.get("product_version") or platform.mac_ver()[0]
    translated = str(prelude.get("proc_translated", "0")).strip() == "1"
    if translated:
        return False, "running under Rosetta on Apple silicon: full suite, but the Python is x86_64 (warning)"
    if arch == "x86_64":
        return True, "Intel Mac (plan leg M3: reduced)"
    m = mac_major(ver)
    if m is not None and m < 26:
        return True, f"macOS {ver} (plan leg M4: reduced)"
    return False, f"Apple silicon, macOS {ver}"


def load_prelude() -> dict:
    p = os.environ.get("SKELLYCAM_MAC_PRELUDE")
    if p and Path(p).exists():
        try:
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except ValueError:
            return {"error": f"unparsable prelude {p}"}
    return {}


# ================================================================================================ discovery
def join_cameras(snapshot: dict, avf_devices: list[dict], formats_by_uid: dict[str, dict] | None = None) -> list[dict]:
    """IORegistry cameras + AVFoundation devices -> ctx.cameras (pure; unit-tested).

    Join rule (macos.md G-ID): AVCaptureDevice.uniqueID parsed as locationID<<32|VID<<16|PID, matched to the
    IOUSBHostDevice with that locationID and VID/PID. USB cameras with no AVFoundation entry stay in the list
    (unique_id None) so tests record them; AVFoundation devices that are not USB (built-in, Continuity, Desk View,
    virtual cameras) are not cameras of this study and are kept only in ctx.avf_devices."""
    formats_by_uid = formats_by_uid or {}
    cams = []
    used = set()
    for c in snapshot.get("cameras", []):
        cam = dict(c)
        cam.update(unique_id=None, avf_name=None, model_id=None, avf_order=None, avf_formats=[],
                   uid_matches_location=None, model_matches_vidpid=None)
        for d in avf_devices:
            up = d.get("uid_parsed") or {}
            if up and up.get("location_id") == c.get("location_id") and up.get("vid") == c.get("vid") \
                    and up.get("pid") == c.get("pid"):
                cam.update(unique_id=d["unique_id"], avf_name=d.get("name"), model_id=d.get("model_id"),
                           avf_order=d.get("order"), uid_matches_location=True, transport=d.get("transport"),
                           in_use_by_other_app=d.get("in_use_by_other_app"))
                mp = d.get("model_parsed")
                cam["model_matches_vidpid"] = (mp == {"vid": c["vid"], "pid": c["pid"]}) if mp else None
                f = formats_by_uid.get(d["unique_id"]) or {}
                cam["avf_formats"] = f.get("formats") or d.get("formats") or []
                used.add(d["unique_id"])
                break
        cams.append(cam)
    # USB AVFoundation devices with no IORegistry camera (should not happen): keep them visible
    for d in avf_devices:
        if d.get("is_usb") and d["unique_id"] not in used:
            up = d.get("uid_parsed") or {}
            cams.append({"key": f"{up.get('vid')}:{up.get('pid')}:avf={d['unique_id']}", "device_id": None,
                         "name": d.get("name"), "is_kiyo": (up.get("vid"), up.get("pid")) == ("1532", "0e05"),
                         "vid": up.get("vid"), "pid": up.get("pid"), "serial": None, "unique_id": d["unique_id"],
                         "avf_name": d.get("name"), "model_id": d.get("model_id"), "location_id": up.get("location_id"),
                         "location_hex": up.get("location_hex"), "port_path": None, "avf_formats":
                             (formats_by_uid.get(d["unique_id"]) or {}).get("formats") or d.get("formats") or [],
                         "not_in_ioregistry": True, "uid_matches_location": False})
    return cams


def discover(ctx: suitectx.SuiteCtx, fake_ioreg: Path | None = None, fake_avf: Path | None = None) -> dict:
    """Fill ctx.snapshot, ctx.avf_devices, ctx.cameras, ctx.tcc. Returns discovery notes."""
    import mac_ioreg
    notes: dict[str, Any] = {}
    desc = ctx.desc_cache()
    alt_tables = {k: v.get("alt_table") for k, v in desc.items() if v.get("alt_table")}
    if fake_ioreg is not None:
        plists = {p.stem.replace("ioreg_", ""): mac_ioreg.load_plist(p.read_bytes()) for p in fake_ioreg.glob("ioreg_*.plist")}
        ctx.snapshot = mac_ioreg.build_snapshot(plists, alt_tables=alt_tables)
    else:
        def runner(argv, timeout):
            return ctx.runner(argv, timeout)
        ctx.snapshot = mac_ioreg.collect_snapshot(runner=runner, raw_dir=ctx.raw_dir / "ioreg", alt_tables=alt_tables)
    notes["snapshot_report"] = ctx.snapshot.get("schema_report")
    formats: dict[str, dict] = {}
    if fake_avf is not None:
        d = json.loads(fake_avf.read_text(encoding="utf-8"))
        ctx.avf_devices = d.get("devices", [])
        ctx.tcc = d.get("authorization", "unknown (fake)")
    elif fake_ioreg is not None:
        ctx.avf_devices = []
    else:
        r = ctx.avf(["list"], 60, label="discovery list")
        notes["avf_list"] = {k: r[k] for k in ("rc", "timed_out", "elapsed_s")}
        j = r.get("json") or {}
        ctx.avf_devices = j.get("devices") or []
        if not j:
            notes["avf_list_error"] = r.get("stderr_tail")
        for dv in ctx.avf_devices:
            if not dv.get("is_usb"):
                continue
            fr = ctx.avf(["formats", "--device", dv["unique_id"]], 60, label=f"formats {dv['unique_id']}")
            fj = fr.get("json") or {}
            formats[dv["unique_id"]] = (fj.get("device") or {})
            if not fj.get("ok"):
                notes.setdefault("formats_errors", {})[dv["unique_id"]] = fj.get("error") or fr.get("stderr_tail")
        t = ctx.avf(["tcc"] + (["--request"] if ctx.args.request_camera else []), 60, label="tcc")
        tj = t.get("json") or {}
        ctx.tcc = tj.get("video_after") or tj.get("video")
        notes["tcc"] = tj
    ctx.cameras = join_cameras(ctx.snapshot, ctx.avf_devices, formats)
    for cam in ctx.cameras:
        d = ctx.cam_desc(cam)
        if d:
            cam["uvc"] = {k: d.get(k) for k in ("entities", "alt_table", "frames", "source")}
    return notes


# ================================================================================================ camlock
class CamLock:
    """The same exclusive lock as tools/camlock.py (POSIX flock on research/usb_cameras/.camlock), held for the
    whole run because M-MULTI starts several camera children at once (per-command camlock would serialise them)."""

    def __init__(self, timeout_s: float):
        self.timeout_s, self.fd = timeout_s, None

    def acquire(self) -> float:
        import fcntl
        t0 = time.monotonic()
        self.fd = os.open(CAMLOCK_PATH, os.O_RDWR | os.O_CREAT)
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return time.monotonic() - t0
            except OSError:
                if time.monotonic() - t0 > self.timeout_s:
                    raise TimeoutError(f"camera lock not acquired within {self.timeout_s:.0f} s")
                time.sleep(0.5)

    def release(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


# ================================================================================================ run
def rearrival_check(ctx: suitectx.SuiteCtx, before: dict | None) -> tuple[dict, list[dict]]:
    import mac_ioreg
    rd = mac_ioreg.read_device_states(runner=lambda argv, t: ctx.runner(argv, t))
    st = rd.get("devices") or {}
    flagged = []
    if not st and before:
        # ioreg failed or timed out: no evidence either way; keep the previous state instead of flagging every
        # camera as gone
        return before, [{"camera": None, "event": "state_unavailable", "error": rd.get("error")}]
    if before:
        for cam in ctx.cameras:
            loc = cam.get("location_hex")
            if not loc:
                continue
            b, a = before.get(loc), st.get(loc)
            if b is None or a is None or b.get("registry_entry_id") != a.get("registry_entry_id"):
                flagged.append({"camera": cam["key"], "location": loc, "before": b, "after": a,
                                "event": "gone" if a is None else ("appeared" if b is None else "re-arrived")})
    return st, flagged


def summary_md(ctx: suitectx.SuiteCtx, rows: list[dict], notes: dict, started: str) -> str:
    lines = [f"# macOS suite run {ctx.out_dir.name}", "",
             f"Host {socket.gethostname()}, macOS {ctx.prelude.get('product_version') or platform.mac_ver()[0]} "
             f"({ctx.prelude.get('arch') or platform.machine()}, {ctx.prelude.get('hw_model', '?')}), started {started}.",
             f"Suite: {'reduced' if ctx.reduced else 'full'}{', quick' if ctx.args.quick else ''}; ep0 "
             f"{'on (' + ctx.args.ep0_backend + ')' if ctx.args.ep0 else 'off'}; camera permission: {ctx.tcc}.", "",
             "## Cameras", "", "| Key | Name | AVFoundation uniqueID | Speed | Formats |", "| --- | --- | --- | --- | --- |"]
    for c in ctx.cameras:
        lines.append(f"| {c['key']} | {c.get('name')} | {c.get('unique_id') or '(not listed)'} | {c.get('speed')} | "
                     f"{len(c.get('avf_formats') or [])} |")
    lines += ["", "## Tests", "", "| Test | Verdicts | Errors | Re-arrivals | Seconds |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        v = "; ".join(f"{g}: {x.get('rating')}" for g, x in (r.get("verdicts") or {}).items() if isinstance(x, dict)) or "-"
        lines.append(f"| {r['test']} | {v} | {r.get('n_errors', 0)} | {r.get('n_rearrivals', 0)} | {r.get('elapsed_s')} |")
    lines += ["", "Every verdict follows plan section 3; see each test's JSON for the criteria and the evidence.",
              "Untested on hardware before this run: the whole macOS suite (see suite/macos/README.md)."]
    return "\n".join(lines) + "\n"


# ================================================================================================ --plan
def plan_estimate_s(ctx: suitectx.SuiteCtx) -> dict:
    """Rough seconds per test for --plan (child start ~4 s each: Python + PyObjC import + session start)."""
    a = ctx.args
    cams = ctx.openable()
    mj = load_test_module("m_mjpeg")
    n_cells = sum(len(mj.cell_rates(ctx, f)) for c in cams for f in mj.formats_to_test(ctx, c)[0])
    est = {"M-ENV": 60, "M-TCC": 10, "M-TOPO": 10, "M-ID": 20 + 5 * a.id_proc_repeats, "M-FMT": 10,
           "M-CTRL-LIST": 6 * len(cams),
           "M-MJPEG": n_cells * len(a.mjpeg_variant_list) * (a.mjpeg_seconds + 5),
           "M-CYC": len(cams) * (8 + a.cycles * 2.0 + 6),
           "M-CTRL-EFFECT": len(cams) * (a.ctrl_runs * 16 + 12),
           "M-MULTI": a.multi_repeats * (a.multi_seconds + 10) if len(cams) > 1 else 0,
           "M-TS": len(cams) * (a.ts_seconds + 6)}
    if getattr(a, "plan_ep0", False):
        # per camera: descriptors + ctrl-list + GET_CUR (3 children), the ~27 s ep0 schedule capture, the 3 s
        # before-start capture, GET_CUR after close, restore SET_CUR (4 s child start each)
        est[EP0_PHASE] = len(cams) * (3 * 5 + 27 + 8 + 3 + 6 + 4 + 4)
    return {k: round(v) for k, v in est.items()}


def _serial_form(s: str | None) -> str:
    if not s:
        return "none"
    cls = ("digits" if s.isdigit() else "hex" if all(ch in "0123456789abcdefABCDEF" for ch in s) else
           "alnum" if s.isalnum() else "mixed")
    return f"{len(s)} chars, {cls}"


def _g(d: Any, *path, default=None):
    for p in path:
        if isinstance(d, list) and isinstance(p, int):
            d = d[p] if -len(d) <= p < len(d) else None
        elif isinstance(d, dict):
            d = d.get(p)
        else:
            return default
        if d is None:
            return default
    return d


def _n(x: Any) -> Any:
    return f"{x:.4g}" if isinstance(x, float) else x


def _on(d: dict | None) -> list:
    return [k for k, v in (d or {}).items() if v is True]


def _fmt_bytes(b: dict | None) -> str:
    if not b:
        return "-"
    return "/".join(f"{b[k] / 1000:.0f}" for k in ("min", "median", "p99", "max")) + f" kB (n={b['n']})"


def _yn(x: Any) -> str:
    return {True: "yes", False: "NO", None: "?"}.get(x, str(x))


def ep0_summary_lines(cl: dict | None, ce: dict | None, status: str | None) -> list[str]:
    """summary.md section 'Manual controls via endpoint 0 (IOKit, no seize)' for one camera, from
    m_ctrl_list_ep0.json (cl: this camera's record) and m_ctrl_effect_ep0.json (ce)."""
    L = ["", "### Manual controls via endpoint 0 (IOKit, no seize)"]
    if status != "done":
        why = {None: "--no-ep0 (or neither CTRL test selected)",
               "pending": "the endpoint-0 phase did not finish (this is the phase-1 summary)"}.get(status, status)
        return L + [f"- NOT TESTED: {why}"]
    e = (cl or {}).get("ep0")
    if not isinstance(e, dict):
        return L + [f"- NOT TESTED: {e or 'no endpoint-0 listing for this camera (see m_ctrl_list_ep0.json errors)'}"]
    setup = e.get("setup") or {}
    tr = setup.get("transport") or {}
    L.append(f"- backend {setup.get('backend') or tr.get('backend') or '?'} (control requests on pipe 0 of the "
             f"VideoControl interface {tr.get('interface')}; opened {tr.get('opened_interface')}, seize "
             f"{tr.get('seize')}); setup {'ok' if setup.get('ok') else 'FAILED'}"
             + (f": {e.get('error')}" if e.get("error") else "")
             + (f"; plug-in kr 0x{tr['create_plugin_kr']:08X}" if tr.get("create_plugin_kr") else "")
             + (f"; child timed out" if e.get("timed_out") else ""))
    rcs = [r for r in (cl.get("comparison") or {}).get("rc_names") or [] if r not in ("kIOReturnSuccess", "LIBUSB_SUCCESS")]
    if rcs:
        L.append(f"- request errors seen (any control): {', '.join(rcs)}")
    rows = {r["name"]: r for r in e.get("controls") or []}
    if not rows:
        return L + [f"- every control NOT TESTED: the control listing returned nothing ("
                    f"{e.get('error') or ('child timed out' if e.get('timed_out') else 'no CT/PU control found')})"]
    ce = ce or {}
    runs = ce.get("ep0_runs") or []
    groups = (runs[0].get("groups") if runs else None) or {}
    switches = (runs[0].get("switches") if runs else None) or {}
    bs = ce.get("before_start") or {}
    rest = (ce.get("restore") or {}).get("per_control") or {}
    not_run = ce.get("ep0_error") or ce.get("error") or ("no effect capture ran" if not runs else None)
    effect_key = {"exposure_time_absolute": ("exposure", "brightness"), "gain": ("gain", "brightness"),
                  "focus_absolute": ("focus", "sharpness"), "white_balance_temperature": ("white_balance", "R/B")}
    for n in ("exposure_time_absolute", "gain", "focus_absolute", "white_balance_temperature", "auto_exposure_mode",
              "focus_auto", "white_balance_temperature_auto"):
        r = rows.get(n)
        if r is None:
            L.append(f"- {n}: not advertised by the descriptor (not read)")
            continue
        bad = sorted({x.get("rc_name") for x in r.get("calls") or [] if x.get("rc") not in (0, None)})
        rng = ("/".join(str(r.get(k)) for k in ("min", "max", "res", "def")) if r.get("kind") == "range"
               else f"modes {r.get('modes_supported')}" if n == "auto_exposure_mode" else f"def {r.get('def')}")
        s = (f"- {n}: advertised {_yn(r.get('advertised_in_descriptor'))}; GET_INFO lists it "
             f"{_yn(r.get('listed_by_device'))}; every GET answered {_yn(r.get('ok'))}"
             + (f" ({', '.join(map(str, bad))})" if bad else "")
             + f"; {'min/max/res/def ' if r.get('kind') == 'range' else ''}{rng}; cur {r.get('cur')}")
        g = groups.get(effect_key[n][0]) if n in effect_key else None
        steps = (g or {}).get("steps") if g else switches.get(n)
        if steps:
            fails = sorted({x.get("rc_name") for x in steps if not x.get("set_ok")})
            s += (f"; set accepted {_yn(all(x.get('set_ok') for x in steps))}" + (f" ({', '.join(map(str, fails))})"
                                                                                  if fails else "")
                  + f"; readback matched {_yn(all(x.get('readback_matches') for x in steps))}")
            if g:
                eff = g.get("effect") or {}
                s += (f"; effect on image ({effect_key[n][1]}) {_yn(eff.get('effect_ok'))}"
                      + (f" ({eff.get('relative_change') if 'relative_change' in eff else eff.get('max_min_ratio')})"
                         if eff.get("effect_ok") is not None else f" ({eff.get('reason')})"))
        else:
            s += f"; set NOT TESTED: {not_run or 'not in the effect schedule'}"
        if n in ("exposure_time_absolute", "auto_exposure_mode") and not bs:
            s += f"; persisted across close NOT TESTED: {not_run or 'the set-before-start capture did not run'}"
        elif n in ("exposure_time_absolute", "auto_exposure_mode"):
            want = bs.get("target") if n == "exposure_time_absolute" else 1
            got = (bs.get("after_close") or {}).get(n)
            s += f"; kept from before stream start {_yn(bs.get('kept'))}" if n == "exposure_time_absolute" else ""
            s += "; persisted across close " + (_yn(got == want) if got is not None else
                                                "NOT TESTED: GET_CUR after close failed or timed out")
        else:
            s += "; persisted across close NOT TESTED: only exposure and AE mode are read back after close"
        if n in rest:
            s += f"; restored {_yn(rest[n].get('ok'))}" + (f" ({rest[n].get('rc_name')})" if not rest[n].get("ok") else "")
        else:
            s += "; restored NOT TESTED: " + ("not in the restore list (initial value unknown)" if ce.get("restore")
                                              else "no restore ran (nothing was set)")
        L.append(s)
    rs = ce.get("restore") or {}
    if rs and not rs.get("ok"):
        L.append(f"- restore of the initial values FAILED or incomplete: "
                 f"{rs.get('skipped') or rs.get('error') or ('child timed out' if rs.get('timed_out') else 'see above')}")
    return L


def plan_summary(ctx: suitectx.SuiteCtx, res: dict[str, dict], rows: list[dict], started: str, minutes: float,
                 ep0_status: str | None = None) -> str:
    """The short pasteable digest of a --plan run (summary.md and the end of the console output). No hostname, no
    home path, serials as their form only (the JSON files keep the exact strings). ep0_status: None (no
    endpoint-0 phase), 'pending' (phase-1 summary), 'done', or the phase's crash text."""
    env = results.env_info()
    pre = ctx.prelude
    app = pre.get("term_program") or pre.get("bundle_id") or "the app that launched the script"
    L = [f"# macOS capture-plan run {ctx.out_dir.name}", "",
         f"- macOS {pre.get('product_version') or platform.mac_ver()[0]} ({pre.get('build_version') or '?'}), "
         f"{pre.get('hw_model') or '?'} {pre.get('arch') or platform.machine()} {pre.get('cpu') or ''}".rstrip(),
         f"- Python {env['python']}; " + ", ".join(f"{k} {v}" for k, v in sorted(env["packages"].items())),
         f"- started {started}, {minutes:.1f} min; tests run: {len(rows)}; endpoint 0 off for every gating test; "
         f"{EP0_PHASE} (iokit-intf, nothing opened/seized/claimed/detached): "
         + {None: "not run (--no-ep0)", "pending": "NOT FINISHED (phase-1 summary)", "done": "done"}.get(
             ep0_status, str(ep0_status))]
    if ctx.tcc != "authorized":
        L.append(f"- **CAMERA PERMISSION MISSING ({ctx.tcc})**: grant Camera to {app} in System Settings > Privacy & "
                 "Security > Camera, quit and reopen it, run again. Camera results below are NOT measurements.")
    else:
        L.append(f"- camera permission: authorized (app: {app})")
    for k, d in ctx.dead.items():
        L.append(f"- **Kiyo Pro dead** since {d['since_test']} ({k}): stream starts {d['stream_starts_this_run']}; "
                 "not tested afterwards (diagnostics in kiyo_pro_dead.json)")
    mj = {c["key"]: c for c in _g(res, "M-MJPEG", "measurements", "cameras", default=[])}
    cyc = {c["key"]: c for c in _g(res, "M-CYC", "measurements", "cameras", default=[])}
    ts = {c["key"]: c for c in _g(res, "M-TS", "measurements", "cameras", default=[])}
    ce = {c["key"]: c for c in _g(res, "M-CTRL-EFFECT", "measurements", "cameras", default=[])}
    cl0 = {c["key"]: c for c in _g(res, "M-CTRL-LIST (ep0)", "measurements", "cameras", default=[])}
    ce0 = {c["key"]: c for c in _g(res, "M-CTRL-EFFECT (ep0)", "measurements", "cameras", default=[])}
    multi = {m["camera"]: m for m in _g(res, "M-MULTI", "measurements", "attempts", 0, "cameras", default=[])}
    doms = _g(res, "M-TOPO", "measurements", "camera_domains", default={}) or {}
    for c in ctx.cameras:
        k = c["key"]
        L += ["", f"## {c.get('name')} {c.get('vid')}:{c.get('pid')}" + (" (Kiyo Pro)" if c.get("is_kiyo") else ""),
              f"- identity: serial {_serial_form(c.get('serial'))} ({c.get('serial_reason') or c.get('key_kind')}); "
              f"locationID {c.get('location_hex')}; port_path {c.get('port_path')}; uniqueID {c.get('unique_id')}; "
              f"modelID {c.get('model_id')}; speed {c.get('speed')}; domain {doms.get(k)}"]
        for mo in _g(mj, k, "modes", default=[]) or []:
            row = mo.get("row") or {}
            L.append(f"- MJPEG {_g(mo, 'mode', 'mode_text')}: JPEG bytes from AVFoundation: "
                     f"{'YES' if row.get('is_jpeg') else 'no'} (best variant {row.get('best_variant')})")
            for var, cell in (mo.get("cells") or {}).items():
                hdr = cell.get("first_header") or {}
                L.append(f"  - {var}: {cell.get('delivered')} subtypes {cell.get('sample_subtypes')} cv "
                         f"{cell.get('cv_pixel_formats')}; frames {cell.get('frames')}/{cell.get('frames_expected')} "
                         f"fps {_n(cell.get('fps_measured'))}; strict {cell.get('strict_valid_fraction')}; headers "
                         f"{cell.get('n_header_sha1')} ({(cell.get('header_sha1') or '')[:10]}); APP0 {hdr.get('app0')} "
                         f"DHT {hdr.get('has_dht')}; bytes min/med/p99/max {_fmt_bytes(cell.get('bytes_stats'))}"
                         + (f"; settings error {str(cell.get('video_settings_error'))[:80]}"
                            if cell.get("video_settings_error") else "")
                         + (f"; {cell['skipped']}" if cell.get("skipped") else ""))
        if k in mj and not mj[k].get("modes"):
            L.append(f"- MJPEG: {_g(mj, k, 'rating', 'rating')} ({_g(mj, k, 'selection')})")
        for v in _g(cyc, k, "variants", default=[]) or []:
            s = v.get("summary") or {}
            ff = _g(s, "timings_ms", "first_frame_ms", default={}) or {}
            L.append(f"- cycles {v['variant']}: {s.get('n_ok')}/{s.get('n')} ok, first frame p50 {ff.get('p50')} "
                     f"p95 {ff.get('p95')} ms, hangs {s.get('hangs')}, failures "
                     f"{[(x.get('stage'), x.get('code'), x.get('count')) for x in s.get('failure_classes') or []][:3]}")
        an = _g(ts, k, "analysis", default=None)
        if an:
            fit = an.get("pts_fit_whole") or {}
            L.append(f"- timestamps: clock {an.get('clock_name') or 'undetermined'} {an.get('clock_name_basis')}; "
                     f"PTS grid {_g(an, 'pts_grid', 'step_ms') if _g(an, 'pts_grid', 'quantized') else 'none'}; "
                     f"interval sd {_n(_g(an, 'pts_interval_ms', 'std'))} ms; fit residual sd "
                     f"{_n(_g(fit, 'residual_stats_ms', 'std'))} ms (fps {_n(fit.get('fps'))}); arrival-PTS median "
                     f"{_n(_g(an, 'arrival_minus_pts_ms', 'median'))} ms; dropped callbacks {an.get('dropped_callbacks')}")
        cr = ce.get(k)
        if cr:
            fl = cr.get("avf_flags") or {}
            runs = cr.get("avf_runs") or []
            L.append(f"- controls (AVFoundation modes supported): exposure {_on(fl.get('exposure_modes_supported'))}, "
                     f"focus {_on(fl.get('focus_modes_supported'))}, wb {_on(fl.get('wb_modes_supported'))}; lock readback ok "
                     f"{[r.get('all_readback_ok') for r in runs]}; luma {[r.get('luma_median') for r in runs]}; "
                     f"restore ok {_g(cr, 'avf_restore', 'ok')}; absolute exposure/gain/focus: none in AVFoundation "
                     "on macOS (endpoint-0 section below)")
        mm = multi.get(k)
        if mm:
            L.append(f"- multi (all at once): frames {mm.get('frames')}/{mm.get('frames_expected')} fps {mm.get('fps')}, "
                     f"dropped {mm.get('dropped_callbacks')}, signal {_g(mm, 'signal', 'signal')} "
                     f"{_g(mm, 'signal', 'code') or ''}, alt {_g(mm, 'granted', 'ioreg_alt')}")
        st = ep0_status
        if st == "done" and k in ctx.dead and not str(ctx.dead[k].get("since_test")).endswith("(ep0)"):
            st = f"Kiyo Pro dead since {ctx.dead[k]['since_test']}: no endpoint-0 request sent"
        L += ep0_summary_lines(cl0.get(k), ce0.get(k), st)
    L += ["", "| Test | Verdicts | Errors | s |", "| --- | --- | --- | --- |"]
    for r in rows:
        v = "; ".join(f"{g}: {x.get('rating')}" for g, x in (r.get("verdicts") or {}).items() if isinstance(x, dict))
        L.append(f"| {r['test']} | {v or '-'} | {r.get('n_errors', 0)} | {r.get('elapsed_s')} |")
    L += ["", "Left out: endpoint-0 requests in the gating tests (only the separate endpoint-0 phase sends them), "
              "unadvertised UVC selectors, extension-unit controls, CoreMediaIO controls (not implemented), AVFoundation "
              "auto-mode toggling, UVC header/PTS/SCR, per-process cycles, mode switching, FMT-NOGRAB, FX, KIYO polling."]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None, runner=None) -> int:
    """``runner`` replaces common.procutil.run (unit tests inject a fake; never used in a real run)."""
    ap = build_parser()
    a = apply_defaults(ap.parse_args(argv))
    if a.list_tests:
        for name, mod, red, opens in TESTS:
            print(f"{name:15s} reduced={'yes' if red else 'no ':3s} opens_camera={'yes' if opens else 'no'}  tests/{mod}.py")
        return 0
    if a.ep0 and a.ep0_backend == "libusb" and not a.ep0_allow_seize:
        print("refused: --ep0-backend libusb seizes USB devices (libusb's darwin enumeration calls USBDeviceOpenSeize "
              "on every device, and libusb_open on the camera). Plan 6.1 forbids seizing. Use the default backend "
              "(iokit-intf), or add --ep0-allow-seize if you really accept the seize.", file=sys.stderr)
        return 2
    if a.plan and a.plan_ep0 and a.ep0_backend != "iokit-intf":
        print(f"refused: --plan's {EP0_PHASE} uses only the iokit-intf backend (nothing opened or seized); drop "
              "--ep0-backend, or add --no-ep0 to run the plan without endpoint-0 requests.", file=sys.stderr)
        return 2
    prelude = load_prelude()
    reduced, why = decide_reduced(a, prelude)
    tests = select_tests(a, reduced)
    ep0_tests = ep0_phase_tests(a, tests)
    stamp = results.utc_stamp()
    out_dir = a.out_dir or results.default_results_dir(stamp, hostname="plan" if a.plan else None)
    raw_dir = a.raw_dir or results.default_raw_dir(out_dir)
    cache_dir = results.raw_root() / "suite_cache" / socket.gethostname()
    ctx = suitectx.SuiteCtx(out_dir=Path(out_dir), raw_dir=Path(raw_dir), args=a, prelude=prelude, reduced=reduced,
                            cache_dir=cache_dir, command=[sys.executable, *sys.argv])
    if runner is not None:
        ctx.runner = runner

    if a.dry_run:
        import mac_modescope
        print(f"macOS suite DRY RUN ({'reduced' if reduced else 'full'}: {why}); nothing is opened or written.")
        print(f"{mac_modescope.text(a)} [{mac_modescope.source()}]; applies to M-MJPEG, M-CYC, M-MULTI, M-TS, "
              "M-CTRL-EFFECT (listing tests compare every mode)")
        print(f"results would go to {out_dir}\nraw data to {raw_dir}\ncaches in {cache_dir}")
        if a.fake_ioreg or a.fake_avf:
            ctx.cache_dir = None
            notes = discover(ctx, a.fake_ioreg, a.fake_avf)
            print(f"cameras (from fakes): {[c['key'] for c in ctx.cameras]}")
            print(f"snapshot: {json.dumps(notes.get('snapshot_report'), default=str)[:400]}")
        else:
            print("cameras: discovered at run time (ioreg + AVFoundation); none hard-coded")
        est = plan_estimate_s(ctx) if a.plan else {}
        for name, mod, _, opens in tests:
            m = load_test_module(mod)
            print(f"\n== {name} ({'opens cameras' if opens else 'no camera opened'})"
                  + (f" ~{est[name] / 60:.1f} min" if name in est else ""))
            for line in (m.plan(ctx) if hasattr(m, "plan") else [m.__doc__.splitlines()[0]]):
                print(f"   - {line}")
        if ep0_tests:
            print(f"\n== {EP0_PHASE} ~{est.get(EP0_PHASE, 0) / 60:.1f} min: starts only after every result file above "
                  "and a first summary.md are written; backend iokit-intf (UVC GET/SET_CUR on pipe 0 of the "
                  "VideoControl interface; nothing opened, seized, claimed or detached; no sudo); a dead Kiyo Pro "
                  "gets nothing; results in m_ctrl_list_ep0.json / m_ctrl_effect_ep0.json; --no-ep0 skips it")
            a.ep0, ctx.ep0_phase = True, True
            for name, mod, _, opens in ep0_tests:
                print(f"   {name}:")
                for line in load_test_module(mod).plan(ctx):
                    print(f"   - {line}")
            a.ep0, ctx.ep0_phase = False, False
        if a.plan:
            total = sum(est.get(t[0], 0) for t in tests) + (est.get(EP0_PHASE, 0) if ep0_tests else 0)
            print(f"\nestimated total: ~{total / 60:.0f} min with "
                  f"{len(ctx.openable())} camera(s) (plus the uv environment build on a first run)")
        if not a.ep0 and not ep0_tests:
            print("\nep0 is OFF: UVC descriptors/controls via endpoint 0 are skipped"
                  + (" (--no-ep0)." if a.plan else " (add --ep0 to opt in)."))
        return 0

    if sys.platform != "darwin":
        print("run_suite.py runs on macOS only (use --dry-run elsewhere)", file=sys.stderr)
        return 2
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    ctx.raw_dir.mkdir(parents=True, exist_ok=True)
    started = results.utc_now_iso()
    t_run = time.monotonic()
    lock = None
    if not a.no_camlock:
        lock = CamLock(a.camlock_timeout_s)
        try:
            waited = lock.acquire()
            ctx.log(f"camera lock acquired after {waited:.1f} s")
        except TimeoutError as e:
            print(str(e), file=sys.stderr)
            return 75
    try:
        ctx.log(f"suite: {'reduced' if reduced else 'full'} ({why}); tests: {[t[0] for t in tests]}")
        notes = discover(ctx)
        ctx.log(f"cameras: {[c['key'] for c in ctx.cameras]}; camera permission: {ctx.tcc}")
        results.write_json(ctx.out_dir / "discovery.json", {"notes": notes, "cameras": ctx.cameras,
                                                            "avf_devices": ctx.avf_devices, "prelude": prelude,
                                                            "reduced": reduced, "reduced_reason": why})
        results.write_json(ctx.out_dir / "topology_snapshot.json", ctx.snapshot)
        rows = []
        state, _ = rearrival_check(ctx, None)
        no_perm = ctx.tcc in ("denied", "restricted", "notDetermined") and not a.run_without_permission
        if no_perm:
            ctx.log(f"WARNING: camera permission is '{ctx.tcc}': camera-opening tests other than M-TCC are recorded "
                    "as untested (grant Camera to the terminal app, or pass --run-without-permission)")
        if a.ep0 and a.ep0_backend == "libusb":
            ctx.log("WARNING: --ep0-backend libusb with --ep0-allow-seize: libusb enumeration calls USBDeviceOpenSeize "
                    "on every USB device and libusb_open seizes the camera (it never claims or detaches). Starting in "
                    "10 s; press Ctrl-C to abort.")
            time.sleep(10)
        res_by_test: dict[str, dict] = {}

        def run_test(name: str, mod: str, opens: bool, file_name: str, key: str) -> None:
            nonlocal state
            ctx.log(f"== {key}")
            ctx.current_test = key
            t0 = time.monotonic()
            try:
                m = load_test_module(mod)
                if no_perm and opens and name not in SELF_GATED:
                    from common import rating
                    res = ctx.new_result(name)
                    results.finish_result(res, {"skipped": f"camera permission '{ctx.tcc}'"},
                                          {"all": rating.untested(f"camera permission is '{ctx.tcc}'")})
                else:
                    res = m.run(ctx)
            except Exception as e:
                res = ctx.new_result(name)
                results.finish_result(res, errors=[{"error": f"{type(e).__name__}: {e}",
                                                    "traceback": traceback.format_exc()[-3000:]}])
            state2, flagged_all = rearrival_check(ctx, state)
            state = state2
            flagged = [f for f in flagged_all if f.get("event") != "state_unavailable"]
            res["rearrivals"] = flagged
            if len(flagged) != len(flagged_all):
                res["rearrival_check_error"] = [f for f in flagged_all if f.get("event") == "state_unavailable"]
            if flagged:
                res.setdefault("errors", []).append({"warning": "unexplained re-arrival during this test",
                                                     "detail": flagged})
            ctx.write(file_name, res)
            res_by_test[key] = res
            rows.append({"test": key, "verdicts": res.get("verdicts"), "n_errors": len(res.get("errors") or []),
                         "n_rearrivals": len(flagged), "elapsed_s": round(time.monotonic() - t0, 1)})
            ctx.log(f"   {key}: " + ", ".join(f"{g}={v.get('rating')}" for g, v in (res.get("verdicts") or {}).items()
                                              if isinstance(v, dict)))

        def write_plan_outputs(ep0_status: str | None) -> None:
            results.write_json(ctx.out_dir / "children.json", ctx.child_log)
            if ctx.dead:
                results.write_json(ctx.out_dir / "kiyo_pro_dead.json", ctx.dead)
            text = plan_summary(ctx, res_by_test, rows, started, (time.monotonic() - t_run) / 60, ep0_status)
            (ctx.out_dir / "summary.md").write_text(text, encoding="utf-8")
            ctx.log(f"privacy scrub of {ctx.out_dir.name}: {results.scrub_private(ctx.out_dir)}")

        # phase 1: every selected test with endpoint 0 off (--plan forces a.ep0 False), each JSON written at once
        for name, mod, _, opens in tests:
            run_test(name, mod, opens, name.lower().replace("-", "_"), name)
        if a.plan:
            # a usable summary is on disk before the first endpoint-0 request (a crash or hang later keeps it)
            write_plan_outputs("pending" if ep0_tests else None)
            ep0_status = None
            if ep0_tests:
                ctx.log(f"== {EP0_PHASE}: iokit-intf, nothing opened/seized/claimed/detached; phase-1 results written")
                a.ep0, ctx.ep0_phase = True, True
                try:
                    for name, mod, _, opens in ep0_tests:
                        run_test(name, mod, opens, name.lower().replace("-", "_") + "_ep0", f"{name} (ep0)")
                    ep0_status = "done"
                except Exception as e:  # run_test catches test errors; this is the runner's own failure
                    ep0_status = f"CRASHED: {type(e).__name__}: {e}"
                    ctx.log(f"{EP0_PHASE} crashed: {traceback.format_exc()[-2000:]}")
                finally:
                    a.ep0, ctx.ep0_phase = False, False
                write_plan_outputs(ep0_status)
            print("\n" + (ctx.out_dir / "summary.md").read_text(encoding="utf-8"))
        else:
            results.write_json(ctx.out_dir / "children.json", ctx.child_log)
            if ctx.dead:
                results.write_json(ctx.out_dir / "kiyo_pro_dead.json", ctx.dead)
            (ctx.out_dir / "summary.md").write_text(summary_md(ctx, rows, notes, started), encoding="utf-8")
        ctx.log(f"wrote {ctx.out_dir}")
    finally:
        if lock is not None:
            lock.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
