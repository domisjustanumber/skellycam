# /// script
# requires-python = "==3.12.13"
# dependencies = ["simplejpeg==1.9.0", "pillow==13.0.0", "numpy==2.5.4"]
# ///
"""Windows UVC test suite runner (plan docs/xplat_capture_plan.md section 6; contract 3).

    uv run --python 3.12 --script research/usb_cameras/suite/windows/run_suite.py [--quick] [--only W-MJPEG,W-CYC]
        [--skip W-KIYO] [--cyc-profile quick|standard|reliability] [--cycles 50] [--proc-cycles 15] [--frames 30]
        [--mjpeg-seconds 3] [--out-dir DIR] [--list] [--plan [--plan-cameras discovery.json]]

``--plan`` (alias ``--dry-run``) prints the test order, each test's estimate and the total and exits: no camera
command runs (ctx.dry_run), estimates read earlier runs' cached format lists, the cameras come from live discovery
(enumeration only) or ``--plan-cameras``, and nothing is written into results/.

What it does:
1. builds the SuiteCtx (``suitectx.build_ctx``): resolves results/raw folders and discovers every USB camera at
   run time (no camera opened; the Razer Kiyo Pro included; nothing filtered); then logs every camera's negotiated
   USB speed and plug-in age (``suitectx.usb_link_report``, run_suite.json ``usb_link_check``) with a prominent
   warning, not an abort, when a Kiyo is not at SuperSpeed;
2. starts W-KIYO as a BACKGROUND control poller right after discovery (when a Kiyo is attached and W-KIYO is
   selected; ``tests/w_kiyo.start_background``), so the Kiyo's onset is caught with its plug-in age and the test
   that was running; it is stopped and written (W-KIYO.json) after the last test, also on Ctrl-C. ``--only W-KIYO``
   (alone) or ``--kiyo-foreground`` runs the old fixed foreground window instead;
3. runs the test modules in this order (integrated 2026-11-09: enumeration first, then the Kiyo-sensitive
   captures while the freshly plugged Kiyo is healthy, W-PYAV-LIST late so it meets a wedged Kiyo, and the long W-CYC
   reliability test last): W-ENV, W-POLICY, W-TOPO, W-ID, W-FMT, W-FMT-NOGRAB, W-CTRL-LIST, W-MJPEG, W-RAW, W-TS,
   W-PYMF, W-CYC-KIYO, W-CTRL-EFFECT, W-AUTO, W-OCV-CTRL, W-MULTI, W-PYAV-LIST, W-CYC (``--only`` / ``--skip`` take
   comma lists of ids, case-insensitive, the ``W-`` prefix optional). The cameras are put Kiyo first (then discovery
   order), so every per-camera test does its Kiyo share at its start. Each module is ``tests/w_<name>.py`` exposing
   ``run(ctx) -> dict``. The five tests added on 2026-11-08 (W-AUTO, W-OCV-CTRL, W-RAW, W-PYAV-LIST, W-PYMF) are left
   out with a log line while their module is not present. An exception, a missing module or a module returning nothing becomes a result JSON with the error
   recorded; the run continues;
4. device-fault gate (suitectx): before each test ``ctx.begin_test`` re-probes every faulted camera once (1-frame
   MF capture) and gates the ones still faulted (their streaming commands are skipped, "untested: device fault
   since <ts>"); faults come from ctx.camcmd's own scan of every single-camera command (0x8007001F, unreleasable
   reader, killed streaming command), from tests calling ctx.mark_fault, from the W-KIYO poller, and from a
   backstop scan of each finished test's result. The suite-wide first failure per camera, every fault/recovery
   event and the Kiyo onset go into run_suite.json (``faults``, ``kiyo_onset``) and a summary.md section;
5. writes ``<TEST>.json`` per test (the dict returned by run()) and ``summary.md`` (ratings per goal x camera x API,
   links to each JSON, test status and timing) into the run folder, refreshing summary.md after every test;
6. prints an ETA before each test from each module's ``estimate_s(ctx)`` (or a default).

Mode scope (common/modescope.py, Dom 2026-11-08): the streaming tests (W-MJPEG, W-CYC, W-MULTI, W-TS,
W-CTRL-EFFECT, W-RAW ...) use only modes with exactly 720 lines at >= 30 fps (--min-fps 30, --min-height 720,
--max-height 720; ``--max-height 0`` = no upper bound; ``--all-modes`` disables the filter; no exception for raw
formats). The listing tests (W-FMT, W-CTRL-LIST, W-FMT-NOGRAB) list and compare every mode. Each streaming test
records the scope and the number of advertised modes it excluded.

W-FMT-NOGRAB (right after W-FMT): which format-listing method works without grabbing the camera (idle / while MF
streams / while DirectShow streams); ``--nograb-hold-ms`` (2500) is how long wincam formats keeps the device open.

Tier 0 only (Dom 2026-11-09): every test runs and rates on the cameras as found. The suite never writes the
registry, and no test reads, compares or rates UVC PTS/SCR (device timestamps are judged unreliable from published
work). W-ENV records whether the MetadataBufferSizeInKB0 value is present (read only) as environment context; the
suite never sets, removes or reverts it.

Defaults: full run --cyc-profile reliability (W-CYC: --reliability-cycles 400 in-process cycles per camera through MF
and through DirectShow via the ffmpeg CLI, 100 MF new-process cycles, the other variants at --cycles 50 /
--proc-cycles 15), --frames 30 --mjpeg-seconds 3 (``--plan`` prints the estimate; the reliability profile is an
overnight run); ``--quick`` uses --cyc-profile quick and 4 / 2 / 10 / 1.5, fewer MJPEG modes, 2 W-MULTI reps, 8 s
W-TS, 1 W-CTRL-EFFECT run and a 2 min W-KIYO window. Explicit flags override the quick values.

Verdict keys understood by summary.md (a test may use any of them):
- ``"<goal>|<camera key>|<api or variant>": rating`` (the capture tests);
- ``"<goal>": rating`` (camera "all", API "all");
- ``"<goal>": {"<api>": "<rating string>", ...}`` (a per-API map of plain ratings).
A rating is ``{"rating": "yes"|"partial"|"no"|"untested", "criteria": [...], "evidence": ...}``
(common/rating.py).

Safety: the runner itself never opens a camera; every camera command in the modules goes through ``ctx.camcmd``
(tools/camlock.py with the timeout on the child). No driver, registry, power-plan or device-state changes.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path

WIN_DIR = Path(__file__).resolve().parent
SUITE_DIR = WIN_DIR.parent
for _p in (str(SUITE_DIR), str(WIN_DIR), str(WIN_DIR / "helpers")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import suitectx  # noqa: E402
from common import results  # noqa: E402

#: Run order (integrated 2026-11-09; W-CYC-KIYO moved after the control tests in review round 3): enumeration and
#: listing first; then the Kiyo-sensitive captures early, while the freshly plugged Kiyo Pro is healthy. Two wedge
#: hypotheses are guarded: plug-in age (it wedged ~210 min after plug-in on 11-06) and, the leading one in
#: docs/windows_results_20261106.md section 8, cumulative stream starts (run 3 polled 5 h without streaming and saw no
#: failure; ~270 Kiyo starts preceded the R2 onset). So the short Kiyo captures and the control tests run first
#: (W-MJPEG Kiyo within 2 h of a replug; W-RAW, the only camera with in-scope raw modes; W-TS and W-PYMF, which answer
#: G-TS and the build-language question; then W-CTRL-EFFECT, W-AUTO and W-OCV-CTRL with their Kiyo share first: the
#: cameras are ordered Kiyo first), all within ~200 Kiyo stream starts; then W-CYC-KIYO, the Kiyo's ~1,060 W-CYC
#: reliability cycles, the last Kiyo-early work: it may end in a fault (a recorded result) and is the most likely
#: test to meet the age window too; then W-MULTI (the bandwidth contention test that wedged the Kiyo on 11-06) and
#: W-PYAV-LIST (late on purpose: it is meant to meet a wedged Kiyo); the other cameras' W-CYC reliability cycles last,
#: so an overnight run that overruns loses only cycles (W-CYC keeps a partial result after every variant). --plan
#: prints the Kiyo's projected plug-in age and cumulative stream starts per test, fails when a KIYO_EARLY test is
#: projected past the age window, and warns when Kiyo control work comes after KIYO_STARTS_WARN starts.
#: Dependencies: W-RAW reads this run's W-FMT listing (W-TOPO domains); W-MJPEG,
#: W-CTRL-EFFECT and W-OCV-CTRL read W-CTRL-LIST.json; all of them come after those. W-KIYO runs as a background
#: poller for the whole suite.
#: 2026-11-11 (overnight run for the phase-1 path, CAPTURE_AND_RECORDING_PLAN rev 3.3): W-AUTO leaves the order
#: (auto-mode recovery is no longer a product test; W-NODRIFT replaces it); the product-path tests (W-PYMF-ALL,
#: W-TBUMP, W-NODRIFT, W-GAIN) run right after W-PYMF while the Kiyo Pro is most likely alive; W-CYC-KIYO (~1,360
#: Kiyo Pro stream starts, the test most likely to end in a wedge) moves to second-last, after W-MULTI and
#: W-PYAV-LIST, so a wedge there costs only the other cameras' W-CYC nothing. Under the dead rule (suitectx) a dead
#: Kiyo Pro is never touched again; W-PYAV-LIST is skipped whole when a Kiyo Pro is dead (listing would reach it).
TESTS = [("W-ENV", "w_env"), ("W-POLICY", "w_policy"), ("W-TOPO", "w_topo"), ("W-ID", "w_id"),
         ("W-FMT", "w_fmt"), ("W-FMT-NOGRAB", "w_fmt_nograb"), ("W-CTRL-LIST", "w_ctrl_list"),
         ("W-MJPEG", "w_mjpeg"), ("W-RAW", "w_raw"), ("W-TS", "w_ts"), ("W-PYMF", "w_pymf"),
         ("W-PYMF-ALL", "w_pymf_all"), ("W-TBUMP", "w_tbump"), ("W-NODRIFT", "w_nodrift"), ("W-GAIN", "w_gain"),
         ("W-CTRL-EFFECT", "w_ctrl_effect"), ("W-OCV-CTRL", "w_ocv_ctrl"), ("W-MULTI", "w_multi"),
         ("W-PYAV-LIST", "w_pyav_list"), ("W-CYC-KIYO", "w_cyc_kiyo"), ("W-CYC", "w_cyc"), ("W-KIYO", "w_kiyo")]
#: not in the default order any more; still runnable with --only W-AUTO
EXTRA_TESTS = [("W-AUTO", "w_auto")]
#: skipped whole (rated untested) when any Kiyo Pro is dead: the test would reach the dead camera
SKIP_IF_KIYO_PRO_DEAD = ("W-PYAV-LIST",)
#: runs as a background poller for the whole suite (not in the sequential order) unless it is the only test
BACKGROUND_TESTS = ("W-KIYO",)
#: tests added 2026-11-08 (docs/capture_stack_options_plan.md section 6.1, and the native-Python backend check)
#: whose modules other owners write: when the module file is not there the test is left out of the plan with a log
#: line (named in --only: an error result)
OPTIONAL_TESTS = ("W-AUTO", "W-OCV-CTRL", "W-RAW", "W-PYAV-LIST", "W-PYMF", "W-PYMF-ALL", "W-TBUMP", "W-NODRIFT",
                  "W-GAIN")

#: fallback ETA (seconds) for modules without estimate_s: (fixed, per camera)
DEFAULT_ETA = {"W-ENV": (20, 0), "W-POLICY": (10, 0), "W-TOPO": (30, 8), "W-ID": (40, 10), "W-FMT": (10, 6),
               "W-FMT-NOGRAB": (20, 80), "W-CTRL-LIST": (10, 6), "W-AUTO": (30, 240), "W-OCV-CTRL": (30, 240),
               "W-RAW": (30, 120), "W-PYAV-LIST": (60, 30), "W-PYMF": (30, 300), "W-PYMF-ALL": (1200, 0),
               "W-TBUMP": (360, 0), "W-NODRIFT": (60, 720), "W-GAIN": (120, 900)}

#: --plan warns when a camera-opening test is projected to END past this Kiyo plug-in age (the Kiyo wedged 210-224
#: min after plug-in on 11-06); W-PYAV-LIST is late on purpose (it is meant to meet a wedged Kiyo)
KIYO_WEDGE_WARN_S = 200 * 60
KIYO_LATE_BY_DESIGN = ("W-PYAV-LIST",)
#: the Kiyo-sensitive captures the order exists for: --plan exits 3 when one of them is projected to end its Kiyo work
#: past KIYO_WEDGE_WARN_S for a Kiyo plugged in at the run start (an order error, independent of the Kiyo's real age)
KIYO_EARLY = ("W-MJPEG", "W-RAW", "W-TS", "W-PYMF", "W-PYMF-ALL", "W-TBUMP", "W-NODRIFT", "W-GAIN",
              "W-CTRL-EFFECT", "W-OCV-CTRL")
#: the stream-start hypothesis (docs/windows_results_20261106.md section 8: ~270 Kiyo stream starts preceded the R2
#: onset): --plan warns when a Kiyo control test starts after more than KIYO_STARTS_WARN projected Kiyo stream starts
KIYO_STARTS_WARN = 250
KIYO_CONTROL_TESTS = ("W-NODRIFT", "W-GAIN", "W-CTRL-EFFECT", "W-OCV-CTRL")
#: approximate Kiyo stream starts per test in a full run (each capture, open/close cycle or OpenCV open that streams
#: the Kiyo counts one; listing tests stream nothing). W-PYMF and W-CYC-KIYO are computed from the run's settings
#: (kiyo_stream_starts); a quick run starts fewer, so the projection then over-counts
KIYO_STARTS_FULL = {"W-MJPEG": 8, "W-RAW": 22, "W-TS": 3, "W-CTRL-EFFECT": 30, "W-AUTO": 16, "W-OCV-CTRL": 16,
                    "W-MULTI": 20, "W-PYAV-LIST": 2, "W-PYMF-ALL": 4, "W-TBUMP": 2, "W-NODRIFT": 5, "W-GAIN": 60}
#: per-camera tests that loop over ctx.cameras (Kiyo first): the Kiyo's work ends after ~1/n of the test. Every other
#: camera-opening test is counted as Kiyo work for its whole length (W-RAW, W-CYC-KIYO, W-MULTI ...)
KIYO_SHARE_FIRST = ("W-FMT", "W-CTRL-LIST", "W-MJPEG", "W-TS", "W-PYMF", "W-NODRIFT", "W-GAIN", "W-CTRL-EFFECT",
                    "W-AUTO", "W-OCV-CTRL")

QUICK = {"cycles": 4, "proc_cycles": 2, "frames": 10, "mjpeg_seconds": 1.5, "repeats": 5, "cyc_profile": "quick"}
FULL = {"cycles": 50, "proc_cycles": 15, "frames": 30, "mjpeg_seconds": 3.0, "repeats": 20,
        "cyc_profile": "reliability"}

GOAL_ORDER = ["G-ID", "G-TS", "G-MJPEG", "G-RAW", "G-CTRL", "G-CTRL-AUTO", "reliability", "pymf_equivalence", "G-BW",
              "fmt_equivalence", "fmt_nograb", "list_touch", "kiyo"]
SYMBOL = {"yes": "yes", "partial": "partial", "no": "**no**", "untested": "untested"}


# ============================================================================================================ args
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Windows UVC test suite runner (see module docstring)")
    suitectx.add_common_args(ap)
    # None = "not given": resolved to the FULL or QUICK value below
    ap.set_defaults(cycles=None, proc_cycles=None, frames=None, mjpeg_seconds=None, repeats=None)
    ap.add_argument("--cyc-profile", dest="cyc_profile", choices=("quick", "standard", "reliability"), default=None,
                    help="W-CYC volume: quick (4 / 2 cycles), standard (--cycles / --proc-cycles for every variant) "
                         "or reliability (>= 381 in-process cycles per camera through MF and through DirectShow via "
                         "the ffmpeg CLI, --reliability-cycles; a smaller MF new-process variant; the default of a "
                         "full run; --quick defaults to quick)")
    ap.add_argument("--reliability-cycles", dest="reliability_cycles", type=int, default=None,
                    help="W-CYC reliability profile: in-process cycles per camera for mf_inproc and ds_ffmpeg_inproc "
                         "(default 400; at least 381 are needed for a >= 99%% claim at the Wilson lower bound)")
    g = ap.add_argument_group("tests added 2026-11-08 (default: each module's own value)")
    g.add_argument("--auto-toggles", dest="auto_toggles", type=int, default=None, help="W-AUTO toggles per run")
    g.add_argument("--raw-seconds", dest="raw_seconds", type=float, default=None, help="W-RAW capture length")
    g.add_argument("--list-repeats", dest="list_repeats", type=int, default=None, help="W-PYAV-LIST repeats")
    g.add_argument("--pymf-cycles", dest="pymf_cycles", type=int, default=None, help="W-PYMF cycles per probe")
    g.add_argument("--pymf-seconds", dest="pymf_seconds", type=float, default=None, help="W-PYMF capture length")
    ap.add_argument("--plan", "--dry-run", dest="plan", action="store_true",
                    help="print the test order, per-test estimates and the total, then exit; opens no camera and runs "
                         "no camera command (cameras from live discovery, which only enumerates, or --plan-cameras)")
    ap.add_argument("--plan-cameras", dest="plan_cameras", default=None, metavar="JSON",
                    help="plan mode: take the cameras from a stored discovery.json / run_suite.json instead of live "
                         "discovery")
    ap.add_argument("--multi-reps", dest="multi_reps", type=int, default=None, help="W-MULTI all-at-once reps")
    ap.add_argument("--ts-seconds", dest="ts_seconds", type=float, default=None, help="W-TS capture length")
    ap.add_argument("--ctrl-runs", dest="ctrl_runs", type=int, default=None, help="W-CTRL-EFFECT runs per control")
    ap.add_argument("--kiyo-minutes", dest="kiyo_minutes", type=float, default=None, help="W-KIYO poll window")
    ap.add_argument("--mjpeg-recapture-s", dest="mjpeg_recapture_s", type=float, default=None,
                    help="W-MJPEG: re-capture length (s) for modes whose rate misses the reference by > 2%% "
                         "(default 10 s in a full run, off in --quick; 0 disables)")
    ap.add_argument("--camera", action="append", default=[],
                    help="OPT-IN debugging filter: keep only cameras whose key or name contains this text "
                         "(repeatable). Default: every discovered camera, the Kiyo included")
    ap.add_argument("--kiyo-pro-dead", dest="kiyo_pro_dead", default=None, metavar="UTC",
                    help="restart after a Kiyo Pro wedge: mark every Kiyo Pro dead from the start (dead rule: no "
                         "command reaches it; its cells rate untested). Value: the UTC time it died (from the earlier "
                         "run's KIYO_PRO_DEAD_*.json)")
    ap.add_argument("--kiyo-interval", dest="kiyo_interval", type=float, default=10.0,
                    help="W-KIYO poll interval in seconds (background and foreground)")
    ap.add_argument("--kiyo-foreground", dest="kiyo_foreground", action="store_true",
                    help="run W-KIYO as a fixed foreground window at the end instead of the whole-suite background "
                         "poller")
    ap.add_argument("--probe-at-start", dest="probe_at_start", action="store_true",
                    help="1-frame MF health probe of every camera right after discovery (records pre-existing "
                         "faults before any test; off by default because it streams every camera once)")
    ap.add_argument("--nograb-hold-ms", dest="nograb_hold_ms", type=int, default=2500,
                    help="W-FMT-NOGRAB: how long each wincam formats call keeps the device open (pipe sampling and "
                         "the third-process open run during this hold)")
    ap.add_argument("--list", action="store_true", help="list the tests and exit")
    ap.add_argument("--reanalyse", metavar="RUN_DIR", default=None,
                    help="offline: rebuild the fault record of a finished run into RUN_DIR/reanalysis/run_suite.json "
                         "(no camera opened)")
    return ap


def resolve_args(a: argparse.Namespace) -> argparse.Namespace:
    base = QUICK if a.quick else FULL
    for k, v in base.items():
        if getattr(a, k, None) is None:
            setattr(a, k, v)
    return a


def plan_cameras(path: str | Path) -> list[dict]:
    """Cameras from a stored discovery.json (``cameras``) or run_suite.json (``cameras``, compact summaries)."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    cams = d.get("cameras") if isinstance(d, dict) else d
    return [c for c in cams or [] if isinstance(c, dict) and c.get("key")]


def norm_id(s: str) -> str:
    s = s.strip().upper()
    if not s:
        return ""
    return s if s.startswith("W-") else "W-" + s


def selected(a: argparse.Namespace) -> list[tuple[str, str]]:
    only = {norm_id(x) for x in (a.only or "").split(",") if x.strip()}
    skip = {norm_id(x) for x in (a.skip or "").split(",") if x.strip()}
    known = TESTS + EXTRA_TESTS
    unknown = (only | skip) - {t for t, _ in known}
    if unknown:
        raise SystemExit(f"unknown test id(s): {sorted(unknown)}; known: {[t for t, _ in known]}")
    return ([(t, m) for t, m in TESTS if (not only or t in only) and t not in skip]
            + [(t, m) for t, m in EXTRA_TESTS if t in only and t not in skip])


def module_exists(name: str) -> bool:
    return (WIN_DIR / "tests" / f"{name}.py").exists()


def drop_missing_optional(a: argparse.Namespace, plan: list[tuple[str, str]]) -> tuple[list, list]:
    """(plan, left out): optional tests whose module is not there yet are left out unless named in --only."""
    only = {norm_id(x) for x in (a.only or "").split(",") if x.strip()}
    keep, out = [], []
    for t, m in plan:
        if t in OPTIONAL_TESTS and t not in only and not module_exists(m):
            out.append((t, m))
        else:
            keep.append((t, m))
    return keep, out


# ============================================================================================================ modules
def load_module(name: str):
    p = WIN_DIR / "tests" / f"{name}.py"
    if not p.exists():
        return None, f"module {p.name} not found"
    try:
        spec = importlib.util.spec_from_file_location(f"wsuite_{name}", p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        if not hasattr(mod, "run"):
            return None, f"module {p.name} has no run(ctx)"
        return mod, None
    except Exception as e:  # noqa: BLE001
        return None, f"import of {p.name} failed: {type(e).__name__}: {e}\n{traceback.format_exc()}"


def estimate(test: str, mod, ctx) -> float:
    if mod is not None and hasattr(mod, "estimate_s"):
        try:
            return float(mod.estimate_s(ctx))
        except Exception:  # noqa: BLE001
            pass
    fixed, per = DEFAULT_ETA.get(test, (60, 0))
    return fixed + per * len(ctx.cameras)


def error_result(ctx, test: str, msg: str, tb: str | None = None) -> dict:
    res = results.new_result(test, platform="windows", command=sys.argv, cameras=ctx.camera_summaries())
    errs = [{"runner_error": msg}]
    if tb:
        errs[0]["traceback"] = tb
    return results.finish_result(res, measurements={}, verdicts={}, errors=errs)


# ============================================================================================================ summary
def rating_label(goal: str, v: dict) -> str:
    """The cell text: the rating, with the reason for a 'no' where the verdict gives one (B8): rating.py's
    ``summary_label`` ('no (latency)' / 'no (failures)' / ...), else ``no_reason``, else for reliability the
    open-success rate (>= 95% opened -> latency)."""
    r = str(v.get("rating"))
    lab = v.get("summary_label")
    if isinstance(lab, str) and lab.startswith(r):
        return lab
    if r == "no":
        if v.get("no_reason"):
            return f"no ({v['no_reason']})"
        ev = v.get("evidence") if isinstance(v.get("evidence"), dict) else {}
        if goal == "reliability" and ev.get("success_rate") is not None:
            return "no (latency)" if ev["success_rate"] >= 0.95 else "no (failures)"
    return r


def flatten_verdicts(test: str, verdicts: dict) -> list[dict]:
    rows = []
    for k, v in (verdicts or {}).items():
        if isinstance(v, dict) and "rating" in v:
            parts = str(k).split("|")
            rows.append({"test": test, "goal": parts[0], "camera": parts[1] if len(parts) > 1 else "all",
                         "api": parts[2] if len(parts) > 2 else "all", "rating": v.get("rating"),
                         "label": rating_label(parts[0], v), "note": v.get("note"), "tier": v.get("tier")})
        elif isinstance(v, dict) and v and all(isinstance(x, str) for x in v.values()):
            for api, r in v.items():
                rows.append({"test": test, "goal": str(k), "camera": "all", "api": api, "rating": r, "label": r,
                             "note": None, "tier": None})
    return rows


def _cell(h: dict, gated: dict) -> str:
    lab = h.get("label") or h["rating"]
    txt = f"**{lab}**" if h["rating"] == "no" else SYMBOL.get(lab, lab)
    s = f"[{txt}]({h['test']}.json)"
    if h["camera"] in (gated.get(h["test"]) or {}):
        s += " (gated)"
    return s


def _age_txt(s) -> str:
    return "-" if s is None else f"{float(s) / 60:.1f} min"


def fault_section(ctx, short: dict) -> list[str]:
    """summary.md lines: device faults, first failure per camera, and the Kiyo onset."""
    try:
        rep = ctx.fault_report()
    except Exception:  # noqa: BLE001
        return []
    L = ["## Device faults, first failures and the Kiyo onset", ""]
    if not rep["faults"] and not rep["first_failure"] and not rep.get("first_any_failure") and not rep["kiyo"]:
        L += ["No device fault or failed camera command recorded.", ""]
        return L
    L.append("Faults (0x8007001F / unreleasable reader / killed streaming command) gate a camera's streaming work "
             "from the next test on; each later test re-probes it once with a 1-frame MF capture. "
             "\"(gated)\" in a rating cell = the camera was faulted when that test started.")
    L.append("")
    if rep["faults"]:
        L.append("| Camera | Faulted since (UTC) | Test | Mode | Code / class | Plug-in age | Source | Now |")
        L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for k, f in rep["faults"].items():
            now = "faulted" if f.get("faulted") else f"recovered {f.get('recovered_utc')}"
            L.append(f"| {short.get(k, k)} | {f.get('since_utc')} | {f.get('test')} | {f.get('mode') or '-'} | "
                     f"{f.get('code') or '-'} / {f.get('class')} | {_age_txt(f.get('plug_in_age_s'))} | "
                     f"{f.get('source')} | {now} |")
        L.append("")
    if rep["first_failure"]:
        L.append("First device-level failed camera command per camera (open / stream error, timeout, 0x8007001F; a "
                 "helper exit for a format / rate mismatch with every cycle streamed is not one):")
        L.append("")
        for k, f in rep["first_failure"].items():
            L.append(f"- {short.get(k, k)}: {f.get('utc')} in {f.get('test')}, {f.get('api') or '-'} "
                     f"{f.get('mode') or ''} at {f.get('stage')}: {f.get('code')} ({f.get('class')}), plug-in age "
                     f"{_age_txt(f.get('plug_in_age_s'))}")
        L.append("")
    other = {k: f for k, f in (rep.get("first_any_failure") or {}).items()
             if not f.get("device_level") and (rep["first_failure"].get(k) or {}).get("utc") != f.get("utc")}
    if other:
        L.append("Earlier non-device failures (the command streamed; its own format / rate checks failed):")
        L.append("")
        for k, f in other.items():
            L.append(f"- {short.get(k, k)}: {f.get('utc')} in {f.get('test')}, {f.get('api') or '-'} "
                     f"{f.get('mode') or ''}: exit {f.get('code')}")
        L.append("")
    for k, o in (rep.get("kiyo") or {}).items():
        L.append(f"Kiyo onset, {short.get(k, k)} (W-KIYO {o.get('poller_mode')} poller from "
                 f"{o.get('poller_started_utc')}, plug-in age at start {_age_txt(o.get('plug_in_age_at_start_s'))}):")
        L.append("")
        if not o.get("stopped_answering"):
            L.append(f"- answered every control poll so far ({o.get('n_polls')} polls)")
        else:
            L.append(f"- first unanswered control poll {o.get('first_failure_utc')} during "
                     f"{o.get('first_failure_test')}, plug-in age {_age_txt(o.get('first_failure_plug_in_age_s'))}, "
                     f"codes {o.get('first_failure_codes')}"
                     + (" (failed from the FIRST poll: the onset predates the poller)"
                        if o.get("failed_from_first_poll") else ""))
            if o.get("first_failure_vendor_processes"):
                L.append(f"- vendor processes at that poll: {', '.join(o['first_failure_vendor_processes'])}")
            for t in o.get("transitions") or []:
                L.append(f"- {t.get('utc')} {t.get('api')} -> {t.get('to')} (during {t.get('test')}, plug-in age "
                         f"{_age_txt(t.get('plug_in_age_s'))})")
        f = (rep.get("faults") or {}).get(k)
        if f:
            L.append(f"- first device fault: {f.get('since_utc')} in {f.get('test')} {f.get('mode') or ''} "
                     f"({f.get('code')}, {f.get('class')}), plug-in age {_age_txt(f.get('plug_in_age_s'))}")
        L.append("")
    return L


def usb_link_section(rep: dict | None) -> list[str]:
    """summary.md lines: negotiated USB speed and plug-in age per camera at run start, and the Kiyo check."""
    if not rep:
        return []
    L = ["## USB link at run start", ""]
    for w in rep.get("warnings") or []:
        L += [f"**{w}**", ""]
    L.append("| Camera | Speed | bcdUSB | Port protocols | Plug-in age at start | Last arrival |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for r in (rep.get("cameras") or {}).values():
        L.append(f"| {r.get('name')}{' (Kiyo)' if r.get('is_kiyo') else ''} | {r.get('speed')} | {r.get('bcd_usb')} | "
                 f"{', '.join(r.get('port_protocols') or []) or '-'} | {_age_txt(r.get('plug_in_age_s'))} | "
                 f"{r.get('last_arrival')} |")
    L.append("")
    return L


def _fmt_s(s: float | None) -> str:
    if s is None:
        return "-"
    s = int(s)
    return f"{s // 3600}h{(s % 3600) // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def write_summary(ctx, status: list[dict], t_start: float, planned: list[str]) -> Path:
    cams = {c["key"]: c for c in ctx.cameras}
    short = {}
    for c in ctx.cameras:
        nm = str(c.get("name") or c["key"])
        short[c["key"]] = f"{nm} ({c.get('vid')}:{c.get('pid')})" + (" Kiyo" if c.get("is_kiyo") else "")
    vrows = []
    for st in status:
        vrows += flatten_verdicts(st["test"], st.get("verdicts") or {})
    L = []
    L.append(f"# Windows UVC suite run, {ctx.hostname}, {ctx.stamp}")
    L.append("")
    a = ctx.args
    L.append(f"Mode: {'quick' if a.quick else 'full'} (W-CYC profile {getattr(a, 'cyc_profile', None)}, cycles "
             f"{a.cycles}, process cycles {a.proc_cycles}, frames "
             f"{a.frames}, MJPEG {a.mjpeg_seconds} s per mode; streaming mode scope "
             f"{suitectx.modescope.from_args(a).text}). Elapsed {_fmt_s(time.monotonic() - t_start)}. "
             f"Results folder: `{ctx.out_dir}`. Raw frames: `{ctx.raw_dir}`.")
    L.append("")
    L.append("Ratings use the plan section 3 thresholds (common/rating.py), on tier-0 data only (the cameras as "
             "found; no UVC PTS/SCR, Dom 2026-11-09). Each cell links to the JSON with the criteria and evidence. A "
             "camera x API aggregate cell (e.g. G-TS without a route suffix) shows the best available route, and "
             "'untested' ranks above 'no' there by design (an unscored route may still work); the per-route cells "
             "hold the measured ratings. '(gated)' = skipped by the device-fault gate.")
    L.append("")
    L.append("## Cameras")
    L.append("")
    L.append("| Key | Name | VID:PID | Speed | Last arrival (discovery) | Last arrival (latest check) |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    latest = (getattr(ctx, "latest_arrivals", None) or {}).get("cameras") or {}
    for c in ctx.cameras:
        la = (latest.get(c["key"]) or {}).get("last_arrival")
        la_txt = "-" if la is None else (la if la == c.get("last_arrival") else f"**{la}** (re-arrived)")
        L.append(f"| `{c['key']}` | {c.get('name')}{' (Kiyo)' if c.get('is_kiyo') else ''} | {c.get('vid')}:{c.get('pid')} "
                 f"| {c.get('speed')} | {c.get('last_arrival')} | {la_txt} |")
    L.append("")
    L += usb_link_section(getattr(ctx, "usb_link", None))
    gated = {st["test"]: st.get("gated") or {} for st in status}
    L.append("## Ratings per goal, camera and API")
    L.append("")
    goals = sorted({r["goal"] for r in vrows}, key=lambda g: (GOAL_ORDER.index(g) if g in GOAL_ORDER else 99, g))
    if not vrows:
        L.append("(no ratings yet)")
    for g in goals:
        rows = [r for r in vrows if r["goal"] == g]
        apis = sorted({r["api"] for r in rows})
        camkeys = [k for k in cams if any(r["camera"] == k for r in rows)] + \
            sorted({r["camera"] for r in rows if r["camera"] not in cams})
        L.append(f"### {g}")
        L.append("")
        L.append("| Camera | " + " | ".join(apis) + " |")
        L.append("| --- | " + " | ".join("---" for _ in apis) + " |")
        for ck_ in camkeys:
            cells = []
            for api in apis:
                hit = [r for r in rows if r["camera"] == ck_ and r["api"] == api]
                if not hit:
                    cells.append("")
                    continue
                cells.append(", ".join(_cell(h, gated) for h in hit))
            L.append(f"| {short.get(ck_, ck_)} | " + " | ".join(cells) + " |")
        L.append("")
    L += fault_section(ctx, short)
    L.append("## Tests")
    L.append("")
    L.append("| Test | Status | Elapsed | ETA was | Errors | Gated (faulted at start) | JSON |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    done = {st["test"] for st in status}
    for st in status:
        g = ", ".join(short.get(k, k) for k in (st.get("gated") or {})) or "-"
        L.append(f"| {st['test']} | {st['status']} | {_fmt_s(st.get('elapsed_s'))} | {_fmt_s(st.get('eta_s'))} | "
                 f"{st.get('n_errors', 0)} | {g} | [{st['test']}.json]({st['test']}.json) |")
    for t in planned:
        if t not in done:
            L.append(f"| {t} | {'running (background)' if t in BACKGROUND_TESTS and getattr(ctx, 'kiyo_poller', None) is not None else 'not run yet'} | - | - | - | - "
                     "| - |")
    errs = [(st["test"], e) for st in status for e in (st.get("errors_head") or [])]
    if errs:
        L.append("")
        L.append("## First errors per test")
        L.append("")
        for t, e in errs:
            txt = json.dumps(e, default=str)
            L.append(f"- {t}: `{txt[:300]}`")
    L.append("")
    p = Path(ctx.out_dir) / "summary.md"
    p.write_text("\n".join(L), encoding="utf-8")
    return p


# ============================================================================================================ faults
def backstop_scan(ctx, test: str, res: dict) -> list[dict]:
    """Mark cameras whose result shows a device fault the camcmd scan could not see (e.g. multi-camera launches).
    A camera already faulted, or one that recovered during this test, is left alone."""
    marked = []
    try:
        found = suitectx.scan_result_for_faults(test, res, ctx.cameras)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"run_suite: result fault scan of {test} failed: {e!r}")
        return marked
    rep_events = getattr(ctx, "fault_events", [])
    for k, rec in found.items():
        if ctx.camera(k) is None or ctx.camera_faulted(k):
            continue
        if any(e.get("type") == "recovered" and e.get("key") == k and e.get("test") == test for e in rep_events):
            continue
        ctx.mark_fault(k, test=test, mode=rec.get("mode"), code=rec.get("code"), api=rec.get("api"),
                       stage=rec.get("stage"), cls=rec.get("class"), source="result_scan",
                       detail={"path": rec.get("path"), "command_utc": rec.get("utc")})
        marked.append({"key": k, **rec})
    return marked


def previous_run_arrivals(ctx) -> dict | None:
    """LastArrivalDate per camera now vs the newest earlier run folder of this host (analysis cyc_kiyo B5: a
    re-arrival between runs, e.g. the generic camera at 18:17:09Z, was invisible)."""
    here = Path(ctx.out_dir)
    try:
        prev = sorted((p for p in here.parent.iterdir() if p.is_dir() and p != here and
                       (p / "discovery.json").exists() and p.name < here.name), key=lambda p: p.name)
    except OSError:
        return None
    if not prev:
        return None
    p = prev[-1]
    try:
        old = {c.get("key"): c for c in json.loads((p / "discovery.json").read_text(encoding="utf-8")).get("cameras")
               or []}
    except (OSError, ValueError):
        return None
    out = {"previous_run": p.name, "cameras": {}}
    for c in ctx.cameras:
        o = old.get(c["key"])
        out["cameras"][c["key"]] = {"previous": (o or {}).get("last_arrival"), "now": c.get("last_arrival"),
                                    "re_arrived_since": bool(o) and o.get("last_arrival") != c.get("last_arrival"),
                                    "in_previous_run": o is not None}
    return out


def kiyo_onset(ctx) -> dict:
    """run_suite.json ``kiyo_onset``: per Kiyo, the poller's onset record plus the gate's fault / first failure."""
    out = {}
    rep = ctx.fault_report()
    for c in ctx.cameras:
        if not c.get("is_kiyo"):
            continue
        k = c["key"]
        f = (rep.get("faults") or {}).get(k)
        out[k] = {"control_polls": (rep.get("kiyo") or {}).get(k),
                  "first_device_fault": {kk: f.get(kk) for kk in ("since_utc", "test", "mode", "code", "class",
                                                                  "stage", "api", "source", "plug_in_age_s")}
                  if f else None,
                  "first_failure": (rep.get("first_failure") or {}).get(k),
                  "first_any_failure": (rep.get("first_any_failure") or {}).get(k),
                  "faulted_at_end": bool(f and f.get("faulted"))}
    return out


def _fault_meta(ctx) -> dict:
    try:
        return {"faults": ctx.fault_report(), "kiyo_onset": kiyo_onset(ctx)}
    except Exception as e:  # noqa: BLE001
        return {"faults_error": repr(e)}


def _utc_sort(s) -> str:
    """Sortable UTC text ('Z' and '+00:00' forms compare alike; unknown sorts last)."""
    try:
        return _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(_dt.timezone.utc).isoformat()
    except (TypeError, ValueError):
        return "~"


def _extra_result_faults(t: str, res: dict, keys=None) -> dict:
    """{key: first fault-like record} in result shapes suitectx.scan_result_for_faults does not walk: W-MULTI's
    ``measurements.device_faults`` (its own records and the suite gate's) and W-KIYO's poll rows with
    ``device_error`` true (the earliest per camera; its ``test`` is the test running at the poll). ``keys``: the
    run's camera keys (other tests keep a fault REPORT under the same name: its keys are not cameras)."""
    out: dict = {}
    meas = (res or {}).get("measurements") or {}
    df = meas.get("device_faults")
    if isinstance(df, dict):
        for k, f in df.items():
            if isinstance(f, dict) and (keys is None or k in keys) and (f.get("class") or f.get("code")):
                out[k] = {"class": f.get("class"), "code": f.get("code"), "stage": f.get("where") or f.get("stage"),
                          "api": f.get("api"), "mode": f.get("mode"), "utc": f.get("since_utc") or f.get("utc"),
                          "test": f.get("test") or t, "path": f"measurements.device_faults.{k}"}
    if t == "W-KIYO":
        for k, c in (meas.get("cameras") or {}).items():
            polls = [r for r in ((c or {}).get("polls") or []) if isinstance(r, dict) and r.get("device_error")] \
                if isinstance(c, dict) else []
            if polls:
                r = min(polls, key=lambda x: _utc_sort(x.get("utc")))
                out.setdefault(k, {"class": r.get("error_class") or "device_error", "code": r.get("error_hr"),
                                   "stage": "control_poll", "api": r.get("api"), "mode": None, "utc": r.get("utc"),
                                   "test": r.get("test") or t, "path": f"measurements.cameras.{k}.polls[{r.get('i')}]"})
    return out


def reanalyse(run_dir: str | Path, out: str | Path | None = None) -> dict:
    """Offline (no camera): the suite-wide fault record of a finished run and the later tests the device-fault gate
    gated (or would have gated: analysis ts B9 / cyc_kiyo B7). A run that recorded its gate (run_suite.json
    ``faults``: the fault report) starts from that record; the result scan (suitectx.scan_result_for_faults, plus
    W-MULTI's device_faults and W-KIYO's poll rows) fills cameras missing from it and is the whole source for an old
    run without one. Writes <run_dir>/reanalysis/run_suite.json."""
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "run_suite.json").read_text(encoding="utf-8"))
    cams = meta.get("cameras") or []
    by_key = {c.get("key"): c for c in cams}
    order = meta.get("tests") or [t for t, _ in TESTS]
    report = meta.get("faults") if isinstance(meta.get("faults"), dict) else {}
    recorded = report.get("faults") if isinstance(report.get("faults"), dict) else {}
    rec_gated = report.get("gated_by_test") if isinstance(report.get("gated_by_test"), dict) else {}
    if not rec_gated:
        rec_gated = {s.get("test"): s.get("gated") for s in meta.get("status") or []
                     if isinstance(s, dict) and s.get("gated")}

    def age_at(c: dict, utc) -> float | None:
        if not (utc and c.get("last_arrival")):
            return None
        try:
            return suitectx.age_s(c["last_arrival"], now=_dt.datetime.fromisoformat(str(utc).replace("Z", "+00:00")))
        except ValueError:
            return None

    # result scan: the first fault-like record per camera, in run order
    scanned: dict = {}
    for t in order:
        p = run_dir / f"{t}.json"
        if not p.exists():
            continue
        res = json.loads(p.read_text(encoding="utf-8"))
        hits = {k: dict(rec, test=t) for k, rec in suitectx.scan_result_for_faults(t, res, cams).items()}
        for k, rec in _extra_result_faults(t, res, set(by_key)).items():
            hits.setdefault(k, rec)
        for k, rec in hits.items():
            if k in scanned:
                continue
            c = by_key.get(k) or {}
            scanned[k] = {"since_utc": rec.get("utc") or res.get("utc_started"), "test": rec.get("test") or t,
                          "mode": rec.get("mode"), "code": rec.get("code"), "class": rec.get("class"),
                          "stage": rec.get("stage"), "api": rec.get("api"), "path": rec.get("path"),
                          "plug_in_age_s": age_at(c, rec.get("utc")), "name": c.get("name"),
                          "is_kiyo": c.get("is_kiyo"), "source": "reanalysis result scan",
                          "time_basis": "command utc_started" if rec.get("utc") else "test utc_started"}
    faults: dict = {}
    for k, f in recorded.items():
        if not isinstance(f, dict):     # a recovered fault (faulted False) still was the first fault
            continue
        c = by_key.get(k) or {}
        since = f.get("since_utc") or f.get("utc")
        faults[k] = {"since_utc": since, "test": f.get("test"), "mode": f.get("mode"), "code": f.get("code"),
                     "class": f.get("class"), "stage": f.get("stage"), "api": f.get("api"), "path": None,
                     "plug_in_age_s": f.get("plug_in_age_s") if f.get("plug_in_age_s") is not None
                     else age_at(c, since), "name": f.get("name") or c.get("name"),
                     "is_kiyo": f.get("is_kiyo", c.get("is_kiyo")),
                     "source": f"run_suite.json fault record ({f.get('source')})", "time_basis": "recorded"}
        s = scanned.get(k)
        if s and _utc_sort(s.get("since_utc")) < _utc_sort(since):
            faults[k]["earlier_evidence"] = s     # e.g. a W-KIYO poll that failed before the gate marked the camera
    for k, s in scanned.items():
        faults.setdefault(k, s)
    # tests after each camera's fault test (in run order) are the ones the gate skipped / would have skipped
    pos = {t: i for i, t in enumerate(order)}
    gated: dict = {}
    for t in order:
        gated[t] = {k: f["since_utc"] for k, f in faults.items()
                    if f.get("test") in pos and pos[f["test"]] < pos[t]}
    background = "W-KIYO" in (meta.get("background") or []) or any(
        isinstance(s, dict) and s.get("test") == "W-KIYO" and s.get("mode") == "background"
        for s in meta.get("status") or [])
    kiyo_src = next((p for p in (run_dir / "reanalysis" / "W-KIYO.json", run_dir / "W-KIYO.json") if p.exists()),
                    None)
    kiyo_doc = json.loads(kiyo_src.read_text(encoding="utf-8")) if kiyo_src else None
    onset = {}
    for k, c in by_key.items():
        if c.get("is_kiyo"):
            kc = (((kiyo_doc or {}).get("measurements") or {}).get("cameras") or {}).get(k) or {}
            onset[k] = {"first_device_fault": faults.get(k), "control_polls_source": str(kiyo_src) if kiyo_src else None,
                        "control_polls": {kk: kc.get(kk) for kk in ("first_failure", "stopped_answering",
                                                                  "failed_from_first_poll", "failure_codes", "onset")
                                          if kk in kc} or None,
                        "note": ("W-KIYO polled the Kiyo's controls in the background for the whole run: "
                                 "control_polls holds its first failure and onset") if background else
                                ("the original run had no background poller (W-KIYO ran last), so the control-plane "
                                 "onset is unknown; the first device fault is the first stream failure found in the "
                                 "results")}
    doc = {"reanalysis_of": str(run_dir), "utc": results.utc_now_iso(), "camera_opened": False,
           "test_order_original": order, "test_order_now": [t for t, _ in TESTS if t not in BACKGROUND_TESTS],
           "fault_source": "run_suite.json fault record + result scan" if recorded else "result scan",
           "faults": faults, "kiyo_onset": onset,
           "gated_by_test_recorded": {t: g for t, g in rec_gated.items() if g},
           "would_have_been_gated": {t: g for t, g in gated.items() if g},
           "note": "fault = the run's own gate record when present, else 0x8007001F / an unreleasable or hung reader "
                   "found in the results (measurements.cameras.<key>, W-MULTI device_faults, W-KIYO poll rows); the "
                   "cameras listed per test had (gated_by_test_recorded) or would have had their streaming work "
                   "skipped after a failed 1-frame re-probe"}
    results.write_json(Path(out) if out else run_dir / "reanalysis" / "run_suite.json", doc)
    return doc


# ============================================================================================================ main
def run_one(ctx, t: str, mod, err: str | None, eta: float) -> tuple[dict, dict, bool]:
    """Run one test module with the fault-gate hooks around it. Returns (status, result, interrupted)."""
    t0 = time.monotonic()
    st = {"test": t, "eta_s": eta}
    interrupted = False
    try:
        probes = ctx.begin_test(t)
    except Exception as e:  # noqa: BLE001
        probes = {"error": repr(e)}
        ctx.log(f"run_suite: begin_test({t}) failed: {e!r}")
    st["gated"] = dict((getattr(ctx, "gated_by_test", {}) or {}).get(t) or {})
    st["probes"] = {k: {kk: p.get(kk) for kk in ("ok", "code", "class", "recovered", "utc")}
                    for k, p in probes.items() if isinstance(p, dict)} if isinstance(probes, dict) else probes
    dead = [k for k in (getattr(ctx, "dead", {}) or {})]
    try:
        if t in SKIP_IF_KIYO_PRO_DEAD and dead:
            res = error_result(ctx, t, "untested: a Kiyo Pro is dead (dead rule: this test would reach it)")
            res["skipped_dead_rule"] = dead
            st["status"] = "skipped (Kiyo Pro dead)"
        elif mod is None:
            res = error_result(ctx, t, err or "module missing")
            st["status"] = "missing"
        else:
            res = mod.run(ctx)
            if not isinstance(res, dict):
                res = error_result(ctx, t, f"run() returned {type(res).__name__}, not a dict")
                st["status"] = "error"
            elif res.get("interrupted"):
                # the module caught Ctrl-C itself and returned what it finished (W-CYC): keep it, then stop the run
                st["status"] = "interrupted"
                interrupted = True
            else:
                st["status"] = "ok"
    except KeyboardInterrupt:
        res = error_result(ctx, t, "interrupted (Ctrl-C)")
        st["status"] = "interrupted"
        interrupted = True
    except Exception as e:  # noqa: BLE001
        res = error_result(ctx, t, f"{type(e).__name__}: {e}", traceback.format_exc())
        st["status"] = "exception"
        ctx.log(f"run_suite: {t} raised {type(e).__name__}: {e}")
    res.setdefault("test", t)
    st["faults_marked_by_result_scan"] = backstop_scan(ctx, t, res)
    if st["gated"]:
        res.setdefault("device_fault_gate", {"gated_at_start": st["gated"],
                                             "note": "streaming commands for these cameras were skipped by the "
                                                     "suite's device-fault gate (untested: device fault)"})
    # analysis ts B9: every result says which cameras were dead (and since when) at its start and end
    try:
        rep = ctx.fault_report()
        res.setdefault("device_faults", {
            "faulted_at_start": st["gated"],
            "faulted_at_end": {k: rep["faults"][k].get("since_utc") for k in rep.get("currently_faulted") or []},
            "kiyo_dead_since": next((rep["faults"][k].get("since_utc") for k in rep.get("currently_faulted") or []
                                     if (ctx.camera(k) or {}).get("is_kiyo")), None)})
    except Exception:  # noqa: BLE001
        pass
    try:
        ctx.end_test(t)
    except Exception:  # noqa: BLE001
        pass
    try:
        ctx.write(t, res)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"run_suite: could not write {t}.json: {e!r}")
        try:
            ctx.write(t, {"test": t, "write_error": repr(e), "repr": repr(res)[:20000]})
        except Exception:  # noqa: BLE001
            pass
    st["elapsed_s"] = round(time.monotonic() - t0, 1)
    st["verdicts"] = res.get("verdicts") or {}
    errs = res.get("errors") or []
    st["n_errors"] = len(errs)
    st["errors_head"] = errs[:2]
    if errs and st["status"] == "ok":
        st["status"] = "ok (with errors)"
    try:
        ctx.latest_arrivals = ctx.arrivals()
    except Exception:  # noqa: BLE001
        pass
    return st, res, interrupted


def rerate_policy_after_fmt(ctx, mods: dict, status: list[dict]) -> dict | None:
    """W-POLICY runs before W-FMT (enumeration order), so its rotation / multi-app criteria cannot be corroborated
    by W-FMT at run time. Once W-FMT has finished in this run, re-rate policy_traps with w_policy.reanalyze (reads
    this run's W-POLICY.json + W-FMT.json, no registry read) and write it back into W-POLICY.json, keeping the
    run-time verdict as policy_traps_at_run_time."""
    st = next((s for s in status if s.get("test") == "W-POLICY"), None)
    mod = (mods.get("W-POLICY") or (None, None))[0]
    p = Path(ctx.out_dir) / "W-POLICY.json"
    if st is None or mod is None or not hasattr(mod, "reanalyze") or not p.exists() or \
            not (Path(ctx.out_dir) / "W-FMT.json").exists():
        return None
    try:
        rr = mod.reanalyze(Path(ctx.out_dir))
        doc = json.loads(p.read_text(encoding="utf-8"))
        v = doc.setdefault("verdicts", {})
        new = (rr.get("verdicts") or {}).get("policy_traps")
        if not new:
            return None
        v["policy_traps_at_run_time"] = v.get("policy_traps")
        new["note"] = ((new.get("note") + "; ") if new.get("note") else "") + \
            "re-rated after W-FMT finished in this run (rotation / multi-app corroboration)"
        v["policy_traps"] = new
        doc["rerated_after"] = {"test": "W-FMT", "utc": results.utc_now_iso(), "changes": rr.get("changes")}
        ctx.write("W-POLICY", doc)
        st["verdicts"] = {k: x for k, x in v.items() if k != "policy_traps_at_run_time"}
        ctx.log(f"run_suite: W-POLICY policy_traps re-rated after W-FMT: {rr.get('changes') or 'unchanged'}")
        return rr
    except Exception as e:  # noqa: BLE001 - never break the run
        ctx.log(f"run_suite: W-POLICY re-rate after W-FMT failed (ignored): {e!r}")
        return None


def apply_camera_filter(ctx, a: argparse.Namespace) -> None:
    if a.camera:
        keep = [c for c in ctx.cameras if any(f.lower() in (str(c.get("key")) + " " + str(c.get("name"))).lower()
                                             for f in a.camera)]
        ctx.log(f"run_suite: --camera filter {a.camera}: {len(keep)}/{len(ctx.cameras)} cameras kept (opt-in)")
        ctx.cameras = keep
    if getattr(a, "kiyo_pro_dead", None):
        for c in ctx.cameras:
            if c.get("is_kiyo"):
                rec = {"dead": True, "since_utc": a.kiyo_pro_dead, "name": c.get("name"), "code": None,
                       "test": "(earlier run)", "rule": "marked dead at start with --kiyo-pro-dead (restart after a "
                                                        "Kiyo Pro wedge); no command reaches it"}
                ctx.dead[c["key"]] = rec
                ctx.faults[c["key"]] = {"faulted": True, "since_utc": a.kiyo_pro_dead, "test": "(earlier run)",
                                        "code": None, "class": "device_error", "source": "--kiyo-pro-dead",
                                        "history": [], "repeats": 0}
                ctx.log(f"run_suite: {c.get('name')} ({c['key']}) marked DEAD from the start (--kiyo-pro-dead "
                        f"{a.kiyo_pro_dead}); no command will reach it")
    # the Kiyo first, then discovery order (w_cyc.camera_order's rule): every per-camera test loops over ctx.cameras,
    # so the Kiyo's share of each test runs at its start, while the Kiyo is youngest
    ctx.cameras = sorted(ctx.cameras, key=lambda c: 0 if c.get("is_kiyo") else 1)


def start_link_check(ctx) -> dict:
    """Negotiated USB speed and plug-in age of every camera at run start (discovery values, read moments ago; opens
    no camera). A Kiyo that is not at SuperSpeed gets a prominent warning; the run is NOT aborted."""
    try:
        rep = suitectx.usb_link_report(ctx.cameras, fresh=False)
    except Exception as e:  # noqa: BLE001 - never break the run
        ctx.log(f"run_suite: USB link check failed (ignored): {e!r}")
        return {"error": repr(e)}
    for r in rep["cameras"].values():
        ctx.log(f"run_suite: USB link {r.get('name')}{' (Kiyo)' if r.get('is_kiyo') else ''}: {r.get('speed')}, "
                f"bcdUSB {r.get('bcd_usb')}, plug-in age {_age_txt(r.get('plug_in_age_s'))}")
    for w in rep["warnings"]:
        bar = "!" * 100
        ctx.log(bar)
        ctx.log(w)
        ctx.log(bar)
    if not rep["kiyo"]:
        ctx.log("run_suite: no Razer Kiyo Pro discovered (every test includes it when it is attached)")
    return rep


def kiyo_stream_starts(t: str, mod, ctx) -> int:
    """Projected Kiyo stream starts of one test (--plan): W-CYC-KIYO = the sum of its W-CYC variant cycles (mode-switch
    variants only when the Kiyo has a second in-scope mode, assumed: 720p30 + 720p60); W-PYMF = wincam and pymf
    cycles plus ~4 captures; W-CYC = 0 when W-CYC-KIYO ran the Kiyo's share; others KIYO_STARTS_FULL."""
    try:
        if t == "W-CYC-KIYO" and mod is not None:
            return int(sum(mod.w_cyc.variant_counts(ctx).values()))
        if t == "W-PYMF" and mod is not None:
            return 2 * int(mod.n_cycles(ctx)) + 4
    except Exception:  # noqa: BLE001 - a projection only
        pass
    if t == "W-CYC":
        return 0 if getattr(ctx, "cyc_kiyo_first", False) else KIYO_STARTS_FULL.get("W-CYC-KIYO", 1060)
    return int(KIYO_STARTS_FULL.get(t, 0))


def plan_main(a: argparse.Namespace, plan: list[tuple[str, str]], left_out: list[tuple[str, str]]) -> int:
    """--plan: the test order, per-test estimates and the total. No camera command runs: the ctx is in dry-run mode
    (ctx.camcmd records instead of running; capkit.get_formats reads earlier runs' cached format lists), and the
    cameras come from live discovery (enumeration only) or --plan-cameras. Writes nothing into results/."""
    import tempfile  # noqa: PLC0415
    work = Path(a.out_dir) if a.out_dir else Path(tempfile.mkdtemp(prefix="wsuite_plan_"))
    cams = plan_cameras(a.plan_cameras) if a.plan_cameras else None
    ctx = suitectx.build_ctx(a, out_dir=work, raw_dir=work / "raw", cameras=cams)
    ctx.dry_run = True
    apply_camera_filter(ctx, a)
    link = suitectx.usb_link_report(ctx.cameras, fresh=False)
    bg = [(t, m) for t, m in plan if t in BACKGROUND_TESTS and len(plan) > 1 and not a.kiyo_foreground]
    seq = [(t, m) for t, m in plan if (t, m) not in bg]
    if bg and not any(c.get("is_kiyo") for c in ctx.cameras):
        seq += bg
        bg = []
    ctx.cyc_kiyo_first = any(t == "W-CYC-KIYO" for t, _ in seq)
    rows, total, starts = [], 0.0, 0
    for t, m in seq:
        mod, err = load_module(m)
        ctx.current_test = t
        eta = estimate(t, mod, ctx)
        opens = bool((getattr(mod, "INFO", None) or {}).get("opens_cameras", t not in ("W-ENV", "W-POLICY")))
        n_st = kiyo_stream_starts(t, mod, ctx) if opens else 0
        rows.append((t, m, eta, total + eta, err, total, opens, starts))
        total += eta
        starts += n_st
    ctx.current_test = None
    now = _dt.datetime.now()
    out = [f"Windows UVC suite plan ({'quick' if a.quick else 'full'} run; nothing is opened or executed)", "",
           f"Streaming mode scope: {suitectx.modescope.from_args(a).text}; listing tests use every mode",
           f"W-CYC profile: {a.cyc_profile} (reliability cycles {getattr(a, 'reliability_cycles', None) or 400}); "
           f"cycles {a.cycles}, process cycles {a.proc_cycles}, frames {a.frames}",
           f"Cameras ({len(ctx.cameras)}; source: {'--plan-cameras ' + str(a.plan_cameras) if cams is not None else 'live discovery (enumeration only)'}):"]
    for r in link["cameras"].values():
        out.append(f"  {r.get('name')}{' (Kiyo)' if r.get('is_kiyo') else ''} {r.get('vid')}:{r.get('pid')}  speed "
                   f"{r.get('speed')}  plug-in age {_age_txt(r.get('plug_in_age_s'))}  key {r.get('key')}")
    out += [f"  {w}" for w in link["warnings"]]
    # the Kiyo's projected plug-in age at each test's start: its age now (LastArrivalDate; 0 when unknown, i.e.
    # replugged just before the run) plus the cumulative estimate
    kiyo = [r for r in link["cameras"].values() if r.get("is_kiyo")]
    k_age0 = 0.0
    if kiyo:
        ages = [r.get("plug_in_age_s") for r in kiyo if isinstance(r.get("plug_in_age_s"), (int, float))]
        k_age0 = float(max(ages)) if ages else 0.0
    out += ["", f"{'#':>2}  {'test':14s} {'estimate':>9s} {'cumulative':>10s}  done at   "
                + ("Kiyo age  Kiyo starts  " if kiyo else "") + "module"]
    late, order_errors, start_warn = [], [], []
    n_cams = max(1, len(ctx.cameras))
    for i, (t, m, eta, cum, err, start, opens, st0) in enumerate(rows, 1):
        at = (now + _dt.timedelta(seconds=cum)).strftime("%H:%M")
        age_txt = ""
        if kiyo:
            age_txt = f"{_fmt_s(k_age0 + start):>8s}  {st0:>11d}  "
            if t in KIYO_CONTROL_TESTS and st0 > KIYO_STARTS_WARN:
                start_warn.append(f"  {t}: its Kiyo control work starts after ~{st0} projected Kiyo stream starts "
                                  f"(> {KIYO_STARTS_WARN}): move it before W-CYC-KIYO")
            no_kiyo_work = t in KIYO_LATE_BY_DESIGN or (t == "W-CYC" and ctx.cyc_kiyo_first)
            # end of the test's Kiyo work: the Kiyo goes first in the per-camera tests (apply_camera_filter)
            k_end = start + (eta / n_cams if t in KIYO_SHARE_FIRST else eta)
            if opens and not no_kiyo_work and k_age0 < KIYO_WEDGE_WARN_S < k_age0 + k_end:
                late.append(f"  {t}: its Kiyo work ends at a Kiyo plug-in age of {_fmt_s(k_age0 + k_end)} (> "
                            f"{KIYO_WEDGE_WARN_S / 60:.0f} min) and may meet a wedged Kiyo")
            if t in KIYO_EARLY and k_end > KIYO_WEDGE_WARN_S:
                order_errors.append(f"  {t} (Kiyo-sensitive) ends its Kiyo work at {_fmt_s(k_end)} after the run "
                                    f"start, past {KIYO_WEDGE_WARN_S / 60:.0f} min even for a Kiyo replugged just "
                                    "before the run: move it earlier in TESTS")
        out.append(f"{i:>2}  {t:14s} {_fmt_s(eta):>9s} {_fmt_s(cum):>10s}  {at}     {age_txt}tests/{m}.py"
                   + (f"  [{err.splitlines()[0]}]" if err else ""))
    if kiyo and k_age0 >= KIYO_WEDGE_WARN_S:
        late = [f"  the Kiyo is already {_fmt_s(k_age0)} past its plug-in (> {KIYO_WEDGE_WARN_S / 60:.0f} min): "
                "replug it just before the run, or every Kiyo result may meet a wedged Kiyo"]
    if late:
        out += ["", "Kiyo wedge window (~210 min after plug-in once it has streamed; replug the Kiyo just before "
                    "the run to start at age 0):"] + late
    if start_warn:
        out += ["", "Kiyo stream starts (the leading wedge hypothesis: ~270 starts preceded the 11-06 R2 onset; "
                    "starts counted from the run start, projected):"] + start_warn
    for t, m in bg:
        out.append(f" -  {t:14s} {'(background poller for the whole run)':>21s}  tests/{m}.py")
    for t, m in left_out:
        out.append(f" -  {t:14s} left out: tests/{m}.py is not present yet")
    out += ["", f"Total estimate: {_fmt_s(total)} (done ~{(now + _dt.timedelta(seconds=total)).strftime('%H:%M')} if "
                f"started now)",
            f"Camera commands that would have run during the estimates: {len(ctx.dry_run_commands)} (none executed)",
            f"Plan workspace (temporary): {work}"]
    if order_errors:
        out += ["", "ORDER ERROR (exit 3): a Kiyo-sensitive test is projected past the Kiyo wedge window:"] + order_errors
    print("\n".join(out))
    return 3 if order_errors else 0


def _write_progress(ctx, run_meta: dict, status: list[dict], t_start: float, planned: list[str],
                    after: str) -> Path | None:
    """run_suite.json and summary.md after a test (and at the end). Each write is guarded on its own: an OSError (a
    file briefly locked by an indexer or antivirus, disk full) or a formatting error is logged, never raised, so the
    remaining tests of an unattended run still run. Returns the summary path (None when it could not be written)."""
    try:
        run_meta.update(_fault_meta(ctx))
        run_meta["status"] = [{k: v for k, v in s.items() if k != "verdicts"} for s in status]
        ctx.write("run_suite", run_meta)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"run_suite: could not write run_suite.json after {after} (run continues): {e!r}")
    try:
        return write_summary(ctx, status, t_start, planned)
    except Exception as e:  # noqa: BLE001
        ctx.log(f"run_suite: could not write summary.md after {after} (run continues): {e!r}")
        return None


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = resolve_args(ap.parse_args(argv))
    plan = selected(a)
    if a.reanalyse:
        d = reanalyse(a.reanalyse)
        print(json.dumps({"faults": d["faults"], "would_have_been_gated": d["would_have_been_gated"]}, indent=1,
                         default=str))
        return 0
    if a.list:
        for t, m in TESTS:
            bg = " (background poller for the whole suite)" if t in BACKGROUND_TESTS else ""
            miss = "  (module not present yet)" if not module_exists(m) else ""
            print(f"{t:14s} tests/{m}.py{'' if (t, m) in plan else '  (not selected)'}{bg}{miss}")
        return 0
    plan, left_out = drop_missing_optional(a, plan)
    if a.plan:
        return plan_main(a, plan, left_out)
    t_start = time.monotonic()
    ctx = suitectx.build_ctx(a)
    apply_camera_filter(ctx, a)
    ctx.log(f"run_suite: {'quick' if a.quick else 'full'} run of {[t for t, _ in plan]} on {len(ctx.cameras)} "
            f"cameras -> {ctx.out_dir}")
    for t, m in left_out:
        ctx.log(f"run_suite: {t} left out: tests/{m}.py is not present yet")
    ctx.log(f"run_suite: streaming mode scope: {suitectx.modescope.from_args(a).text}; W-CYC profile "
            f"{a.cyc_profile}")
    if not ctx.cameras:
        ctx.log("run_suite: WARNING no USB camera discovered; tests will record that")
    ctx.usb_link = start_link_check(ctx)
    # W-KIYO: background poller for the whole suite unless it is the only test or --kiyo-foreground
    bg_plan = [(t, m) for t, m in plan if t in BACKGROUND_TESTS and len(plan) > 1 and not a.kiyo_foreground]
    seq_plan = [(t, m) for t, m in plan if (t, m) not in bg_plan]
    # the Kiyo's W-CYC cycles run early in W-CYC-KIYO; W-CYC then cycles the other cameras
    ctx.cyc_kiyo_first = any(t == "W-CYC-KIYO" for t, _ in seq_plan)
    mods = {}
    etas = {}
    for t, m in plan:
        mod, err = load_module(m)
        mods[t] = (mod, err)
    poller = None
    for t, m in bg_plan:
        mod, err = mods[t]
        if mod is not None and hasattr(mod, "start_background"):
            try:
                poller = mod.start_background(ctx)
            except Exception as e:  # noqa: BLE001
                ctx.log(f"run_suite: could not start the {t} background poller: {e!r}")
        if poller is None:
            # no Kiyo (or no poller support): run it as a normal test at the end
            seq_plan.append((t, m))
    for t, _m in plan:
        etas[t] = 0.0 if (poller is not None and t in BACKGROUND_TESTS) else estimate(t, mods[t][0], ctx)
    total_eta = sum(etas.values())
    ctx.log(f"run_suite: estimated total {_fmt_s(total_eta)} "
            f"({', '.join(f'{t} {_fmt_s(etas[t])}' for t, _ in plan)})")
    status: list[dict] = []
    planned = [t for t, _ in seq_plan] + ([t for t, _ in bg_plan] if poller is not None else [])
    run_meta = {"argv": sys.argv, "args": vars(a), "utc_started": results.utc_now_iso(), "out_dir": str(ctx.out_dir),
                "raw_dir": str(ctx.raw_dir), "tests": planned, "test_order": [t for t, _ in seq_plan],
                "background": [t for t, _ in bg_plan] if poller is not None else [], "eta_s": etas,
                "cameras": ctx.camera_summaries(), "fault_gate": bool(getattr(ctx, "fault_gate", True)),
                "arrivals_since_previous_run": previous_run_arrivals(ctx), "usb_link_check": ctx.usb_link,
                "left_out_tests": [{"test": t, "module": m, "reason": "module not present yet"} for t, m in left_out],
                "timestamp_scope": "tier 0 only (Dom 2026-11-09): no registry writes, no UVC PTS/SCR testing; "
                                   "W-ENV records the MetadataBufferSizeInKB0 value read-only as environment context"}
    ctx.write("run_suite", run_meta)
    if a.probe_at_start:
        for c in ctx.cameras:
            ctx.health_probe(c, test="start", reason="--probe-at-start")
    interrupted = False
    try:
        for i, (t, m) in enumerate(seq_plan):
            mod, err = mods[t]
            remaining = sum(etas[x] for x, _ in seq_plan[i:])
            eta_clock = (_dt.datetime.now() + _dt.timedelta(seconds=remaining)).strftime("%H:%M")
            ctx.log(f"run_suite: [{i + 1}/{len(seq_plan)}] {t} (est. {_fmt_s(etas[t])}; remaining "
                    f"{_fmt_s(remaining)}, done ~{eta_clock})")
            st, res, interrupted = run_one(ctx, t, mod, err, etas[t])
            status.append(st)
            # bookkeeping after each test: a failure here (summary.md / run_suite.json briefly locked, a formatting
            # error in the summary) is logged and the run goes on; it must never cost the remaining tests
            try:
                if t == "W-FMT":
                    rerate_policy_after_fmt(ctx, mods, status)
                ratings = {}
                for r in flatten_verdicts(t, st["verdicts"]):
                    ratings[r["rating"]] = ratings.get(r["rating"], 0) + 1
                ctx.log(f"run_suite: {t} {st['status']} in {_fmt_s(st['elapsed_s'])} (est. {_fmt_s(etas[t])}); "
                        f"ratings {ratings}; errors {st['n_errors']}"
                        + (f"; gated {list(st['gated'])}" if st.get("gated") else ""))
            except Exception as e:  # noqa: BLE001
                ctx.log(f"run_suite: bookkeeping after {t} failed (run continues): {e!r}")
            _write_progress(ctx, run_meta, status, t_start, planned, after=t)
            if interrupted:
                break
    except KeyboardInterrupt:
        interrupted = True
        ctx.log("run_suite: interrupted (Ctrl-C) between tests")
    finally:
        # stop the background poller and write its result, also after Ctrl-C
        if poller is not None:
            for t, m in bg_plan:
                mod, _err = mods[t]
                t0 = time.monotonic()
                st = {"test": t, "eta_s": 0.0, "mode": "background"}
                try:
                    res = mod.finish(ctx, poller)
                    st["status"] = "ok (background)"
                except Exception as e:  # noqa: BLE001
                    res = error_result(ctx, t, f"{type(e).__name__}: {e}", traceback.format_exc())
                    st["status"] = "exception"
                res.setdefault("test", t)
                try:
                    ctx.write(t, res)
                except Exception as e:  # noqa: BLE001
                    ctx.log(f"run_suite: could not write {t}.json: {e!r}")
                st["elapsed_s"] = round(time.monotonic() - t0, 1)
                st["verdicts"] = res.get("verdicts") or {}
                st["n_errors"] = len(res.get("errors") or [])
                st["errors_head"] = (res.get("errors") or [])[:2]
                status.append(st)
    run_meta.update({"utc_finished": results.utc_now_iso(), "elapsed_s": round(time.monotonic() - t_start, 1),
                     "interrupted": interrupted})
    p = _write_progress(ctx, run_meta, status, t_start, planned, after="the run")
    ctx.log(f"run_suite: done in {_fmt_s(time.monotonic() - t_start)}; summary {p}")
    return 130 if interrupted else 0


if __name__ == "__main__":
    sys.exit(main())
