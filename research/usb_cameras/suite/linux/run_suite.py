# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "numpy>=1.26", "simplejpeg>=1.7"]
# ///
"""Linux UVC test suite runner (docs/xplat_capture_plan.md sections 2.6 and 6; legs L1 Ubuntu 24.04.5 / 6.8,
L2 Ubuntu 26.04 / 7.0, L3 Fedora 45 KDE / 7.2).

    bash research/usb_cameras/suite/linux/run_suite.sh [flags]          # bootstraps uv, then runs this file
    uv run --python 3.12 --script research/usb_cameras/suite/linux/run_suite.py [flags]
    ... --dry-run          list the plan (tests, cameras found in sysfs, child runs, rough time); opens no /dev node
    ... --list-tests       test ids and what each answers
    ... --min-fps 30 --min-height 720 --max-height 720   mode scope of the streaming tests (default: exactly 720
                           lines at >= 30 fps; --max-height 0 = no upper bound); --all-modes turns it off

Mode scope (plan section 6, Dom 2026-11-06): L-MJPEG, L-CYC, L-MULTI, L-TS, L-CTRL-EFFECT (and the L-KIYO / L-FMT-NOGRAB
stream probes) use only modes at >= --min-fps and >= --min-height lines; listing tests (L-FMT, L-FMT-NOGRAB,
L-CTRL-LIST) list and compare every mode. Each streaming test records the scope and how many modes it excluded.

Every camera operation runs in a child process with a timeout (linuxlib/camworker.py for raw V4L2;
helpers/pyav_v4l2.py and helpers/opencv_v4l2.py through 'uv run --script'), under the research/usb_cameras/.camlock
lock (same file as tools/camlock.py). No sudo, no module-parameter writes, no unbind/rebind: tier-1 settings are
only detected and reported. All cameras are included (the Razer Kiyo Pro too); a hang or failure is a result.

Results: results/linux/<hostname>/suite_<UTC stamp>/<test>.json (+ per-test folders with frames.jsonl /
cycles.jsonl, summary.md, run.json, runner.log). Raw frames: ~/skellycam-raw/<same relative path>
($SKELLYCAM_RAW_ROOT overrides; --raw-dir too).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path
from types import ModuleType
from typing import Any

LINUX_DIR = Path(__file__).resolve().parent
SUITE_DIR = LINUX_DIR.parent
for _p in (str(SUITE_DIR), str(LINUX_DIR), str(LINUX_DIR / "linuxlib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from common import rating, results  # noqa: E402
from common.topology_model import ModeAltCache  # noqa: E402
import sysfs  # noqa: E402
from suitectx import CamLock, LinuxCtx  # noqa: E402

TESTS = ["L-ENV", "L-TOPO", "L-ID", "L-DESK", "L-FMT", "L-FMT-NOGRAB", "L-CTRL-LIST", "L-MJPEG", "L-CYC",
         "L-CTRL-EFFECT", "L-TS", "L-MULTI", "L-KIYO"]
DEFAULTS = {  # full, quick
    "cycles": (30, 5), "proc_cycles": (10, 3), "frames": (30, 10), "mjpeg_seconds": (3.0, 1.5),
    "mjpeg_modes": ("all", "sizes"), "ts_seconds": (10.0, 4.0), "multi_reps": (3, 1), "kiyo_minutes": (5.0, 1.0),
    "ctrl_runs": (3, 1), "id_repeats": (20, 5), "hold_ms": (2000.0, 1500.0),
}
KERNEL_LOG_RE = re.compile(r"usb|uvc|xhci|video|ehci|hub|bandwidth", re.I)


def module_file(test: str) -> Path:
    return LINUX_DIR / "tests" / ("l_" + test[2:].lower().replace("-", "_") + ".py")


def load_module(test: str) -> ModuleType:
    path = module_file(test)
    spec = importlib.util.spec_from_file_location(f"linux_suite_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def norm_tests(text: str | None) -> list[str]:
    if not text:
        return []
    out = []
    for t in text.split(","):
        t = t.strip().upper()
        if not t:
            continue
        t = t if t.startswith("L-") else "L-" + t
        if t not in TESTS:
            raise SystemExit(f"unknown test {t!r}; known: {', '.join(TESTS)}")
        out.append(t)
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("--quick", action="store_true", help="short run: fewer cycles/frames/modes/minutes")
    ap.add_argument("--only", default=None, help="comma list of tests (ENV,TOPO,... or L-ENV,...)")
    ap.add_argument("--skip", default=None, help="comma list of tests to skip")
    ap.add_argument("--cycles", type=int, default=None, help="in-process open/close cycles per camera x API (30)")
    ap.add_argument("--proc-cycles", type=int, default=None, help="new-process cycles per camera x API (10)")
    ap.add_argument("--frames", type=int, default=None, help="frames per cycle after the first (30)")
    ap.add_argument("--mjpeg-seconds", type=float, default=None, help="capture length per MJPEG mode (3)")
    ap.add_argument("--mjpeg-modes", choices=("all", "sizes", "common"), default=None,
                    help="raw V4L2 reference: every (size, rate) / every size at its top rate / default+small only")
    ap.add_argument("--wrappers", default="pyav,opencv,gst", help="wrapper APIs to compare in L-MJPEG/L-CYC")
    ap.add_argument("--ts-seconds", type=float, default=None, help="L-TS capture length per run (10)")
    ap.add_argument("--multi-reps", type=int, default=None, help="L-MULTI repetitions (3)")
    ap.add_argument("--kiyo-minutes", type=float, default=None, help="L-KIYO polling duration (5)")
    ap.add_argument("--kiyo-interval-s", type=float, default=10.0)
    ap.add_argument("--ctrl-runs", type=int, default=None, help="L-CTRL-EFFECT repeats (3)")
    ap.add_argument("--id-repeats", type=int, default=None, help="L-ID enumeration repeats (20)")
    ap.add_argument("--min-fps", type=float, default=30.0, help="mode scope of the streaming tests: lowest rate (30)")
    ap.add_argument("--min-height", type=int, default=720, help="mode scope of the streaming tests: fewest lines (720)")
    ap.add_argument("--max-height", type=int, default=720, help="mode scope of the streaming tests: most lines (720, "
                                                                "so exactly 720 lines; 0 = no upper bound)")
    ap.add_argument("--all-modes", action="store_true", help="no mode scope: streaming tests use every mode and the "
                                                             "earlier mode choices")
    ap.add_argument("--hold-ms", type=float, default=None, help="L-FMT-NOGRAB: how long each listing method keeps its "
                                                                "handle (or repeats) for alt sampling (2000)")
    ap.add_argument("--flash", action="store_true", help="ground-truth hook (no Linux flash tool yet: recorded as "
                                                         "unavailable)")
    ap.add_argument("--cameras", default=None, help="OPT-IN filter: comma list of key/name substrings "
                                                    "(default: every camera, the Kiyo included)")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--raw-dir", type=Path, default=None)
    ap.add_argument("--mode-alt-cache", type=Path, default=None, help="load/extend this ModeAltCache JSON")
    ap.add_argument("--keep-raw", action="store_true", help="keep every raw frame (default: 3 sample frames per "
                                                            "capture are kept after analysis)")
    ap.add_argument("--no-camlock", action="store_true")
    ap.add_argument("--lock-timeout-s", type=float, default=600.0)
    ap.add_argument("--helper-python", default="3.12", help="Python for the PyAV/OpenCV helpers (PyAV 19 needs 3.12+)")
    ap.add_argument("--no-prewarm", action="store_true", help="do not pre-build the helper environments")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit; opens no /dev node")
    ap.add_argument("--list-tests", action="store_true")
    return ap


def finalize_args(a: argparse.Namespace) -> argparse.Namespace:
    for k, (full, quick) in DEFAULTS.items():
        if getattr(a, k, None) is None:
            setattr(a, k, quick if a.quick else full)
    a.wrapper_list = [w.strip() for w in (a.wrappers or "").split(",") if w.strip()]
    sel = norm_tests(a.only) or list(TESTS)
    skip = set(norm_tests(a.skip))
    a.selected = [t for t in sel if t not in skip]
    return a


def select_cameras(cams: list[dict[str, Any]], filt: str | None) -> list[dict[str, Any]]:
    if not filt:
        return cams
    subs = [s.strip().lower() for s in filt.split(",") if s.strip()]
    return [c for c in cams if any(s in c["key"].lower() or s in (c["name"] or "").lower() for s in subs)]


def make_ctx(a: argparse.Namespace, out_dir: Path, raw_dir: Path, cams: list[dict[str, Any]],
             topo: dict[str, Any] | None) -> LinuxCtx:
    cache = ModeAltCache.load(a.mode_alt_cache) if a.mode_alt_cache else ModeAltCache()
    return LinuxCtx(out_dir=out_dir, raw_dir=raw_dir, args=a, cameras=cams,
                    worker=[sys.executable, str(LINUX_DIR / "linuxlib" / "camworker.py")],
                    helpers_dir=LINUX_DIR / "helpers", topology=topo, mode_alt_cache=cache,
                    lock=CamLock(timeout_s=a.lock_timeout_s, enabled=not a.no_camlock),
                    log_file=(out_dir / "runner.log") if not a.dry_run else None)


def list_tests() -> int:
    for t in TESTS:
        try:
            m = load_module(t)
            info = getattr(m, "INFO", {})
        except Exception as e:
            info = {"goal": f"(module failed to load: {e})"}
        print(f"{t:14s} {info.get('goal', ''):10s} {info.get('summary', '')}")
    return 0


def dry_run(ctx: LinuxCtx) -> int:
    import scope
    cams = []
    for c in ctx.cameras:
        pk = scope.picks(ctx, c)
        cams.append({**sysfs.camera_brief(c), "default_mode": c["modes"]["default"],
                     "n_mjpeg_modes": len(c["modes"]["all_mjpeg"]),
                     "mode_scope": {k: pk["record"].get(k) for k in ("n_advertised", "n_in_scope", "n_excluded",
                                                                       "no_in_scope_mjpeg_mode")},
                     "scoped_default": pk["default"], "scoped_alt": pk["alt"], "scoped_large": pk["large"]})
    plan: dict[str, Any] = {"dry_run": True, "note": "nothing was opened: cameras come from /sys only",
                            "out_dir_would_be": str(ctx.out_dir), "raw_dir_would_be": str(ctx.raw_dir),
                            "kernel": ".".join(map(str, ctx.kernel())),
                            "args": {k: v for k, v in vars(ctx.args).items() if not k.startswith("_")},
                            "mode_scope": {**scope.settings(ctx.args),
                                           "applies_to": "streaming tests (L-MJPEG, L-CYC, L-MULTI, L-TS, "
                                                         "L-CTRL-EFFECT, L-KIYO stream, L-FMT-NOGRAB condition "
                                                         "streams); listing tests list every mode"},
                            "cameras": cams, "tests": []}
    total = 0.0
    for t in ctx.args.selected:
        try:
            m = load_module(t)
            p = m.plan(ctx) if hasattr(m, "plan") else {}
            info = getattr(m, "INFO", {})
        except Exception as e:
            p, info = {"error": f"{type(e).__name__}: {e}"}, {}
        total += float(p.get("est_seconds") or 0)
        plan["tests"].append({"test": t, "module": str(module_file(t).relative_to(LINUX_DIR)), **info, **p})
    plan["est_total_minutes"] = round(total / 60, 1)
    print(json.dumps(plan, indent=1, default=str))
    return 0


def prewarm(ctx: LinuxCtx, build: bool = True) -> dict[str, Any]:
    """Build the helper environments once (downloads wheels), so environment resolution never eats a camera
    timeout later. Opens no camera."""
    out: dict[str, Any] = {}
    import shutil
    if shutil.which("uv") is None:
        dropped = [w for w in ctx.args.wrapper_list if w in ("pyav", "opencv")]
        ctx.args.wrapper_list = [w for w in ctx.args.wrapper_list if w not in ("pyav", "opencv")]
        ctx.log(f"uv not on PATH: wrapper APIs {dropped} unavailable (run through run_suite.sh to bootstrap uv)")
        return {"uv": None, "dropped_wrappers": dropped}
    if not build:
        return {"skipped": "--no-prewarm"}
    for name in ("pyav_v4l2.py", "opencv_v4l2.py"):
        if (name.startswith("pyav") and "pyav" not in ctx.args.wrapper_list) or \
                (name.startswith("opencv") and "opencv" not in ctx.args.wrapper_list):
            continue
        r = ctx.run_child(ctx.helper_cmd(name, "version"), 900)
        out[name] = {"rc": r["rc"], "json": r.get("json"), "elapsed_s": r["elapsed_s"],
                     "stderr_tail": (r.get("stderr") or "")[-600:] if r["rc"] != 0 else None}
        ctx.log(f"prewarm {name}: rc={r['rc']} {r['elapsed_s']}s")
    return out


def kernel_log(since: float, until: float) -> dict[str, Any]:
    try:
        p = subprocess.run(["journalctl", "-k", "--no-pager", "-q", "-o", "short-iso-precise",
                            "--since", f"@{since:.0f}", "--until", f"@{until + 1:.0f}"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"available": False, "error": repr(e)}
    if p.returncode != 0:
        return {"available": False, "error": p.stderr[-300:]}
    lines = [ln for ln in p.stdout.splitlines() if KERNEL_LOG_RE.search(ln)]
    return {"available": True, "n_lines": len(lines), "lines": lines[-300:],
            "bandwidth_lines": [ln for ln in lines if "bandwidth" in ln.lower()][-50:]}


def error_result(ctx: LinuxCtx, test: str, exc: BaseException) -> dict[str, Any]:
    res = ctx.new_result(test)
    results.finish_result(res, measurements={}, verdicts={"suite": rating.untested("test crashed in the runner")},
                          errors=[{"stage": "runner", "type": type(exc).__name__, "message": str(exc),
                                   "traceback": traceback.format_exc()[-4000:]}])
    return res


def verdict_line(res: dict[str, Any]) -> str:
    v = res.get("verdicts") or {}
    return "; ".join(f"{k}: {x.get('rating') if isinstance(x, dict) else x}" for k, x in v.items()) or "-"


def write_summary(ctx: LinuxCtx, rows: list[dict[str, Any]], run_info: dict[str, Any]) -> None:
    lines = [f"# Linux suite run {run_info['stamp']} on {socket.gethostname()}", "",
             f"Kernel {run_info['environment']['os'].get('kernel')}; "
             f"{(run_info['environment']['os'].get('os_release') or {}).get('PRETTY_NAME', '')}; "
             f"session {run_info['environment']['os'].get('session') or 'none'}", "",
             f"Cameras ({len(ctx.cameras)}): " + ", ".join(f"{c['name']} [{c['key']}]" for c in ctx.cameras), "",
             ("Mode scope: none (--all-modes)" if getattr(ctx.args, "all_modes", False) else
              f"Mode scope of the streaming tests: >= {ctx.args.min_fps:g} fps and >= {ctx.args.min_height} lines"
              + (f" and <= {max(ctx.args.max_height, ctx.args.min_height)} lines"
                 if getattr(ctx.args, "max_height", 0) else "") + " "
              "(listing tests list every mode; --all-modes turns it off)"), "",
             "| Test | Verdicts | Errors | Re-arrivals | Elapsed (s) |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['test']} | {r['verdicts']} | {r['errors']} | {r['rearrivals']} | {r['elapsed_s']} |")
    lines += ["", "Ratings follow docs/xplat_capture_plan.md section 3 (common/rating.py). Each test JSON has the "
                  "criteria and evidence behind every verdict.", ""]
    (ctx.out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    results.write_json(ctx.out_dir / "summary.json", {"run": run_info, "tests": rows})


def main(argv: list[str] | None = None) -> int:
    a = finalize_args(build_parser().parse_args(argv))
    if a.list_tests:
        return list_tests()
    stamp = results.utc_stamp()
    out_dir = (a.out_dir or results.default_results_dir(stamp)).resolve()
    raw_dir = (a.raw_dir or results.default_raw_dir(out_dir)).resolve()
    all_cams = sysfs.discover_cameras()
    cams = select_cameras(all_cams, a.cameras)
    try:
        import topology
        topo = topology.collect_snapshot(all_cams)
    except Exception as e:  # recorded by L-TOPO again; the runner must still work
        topo = {"error": f"{type(e).__name__}: {e}"}
    ctx = make_ctx(a, out_dir, raw_dir, cams, topo)
    if a.dry_run:
        return dry_run(ctx)
    if not sys.platform.startswith("linux"):
        print("run_suite.py runs on Linux only (use --dry-run elsewhere)", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    run_info = {"stamp": stamp, "argv": sys.argv, "args": {k: v for k, v in vars(a).items()},
                "out_dir": str(out_dir), "raw_dir": str(raw_dir), "environment": results.env_info(),
                "cameras_found": [sysfs.camera_brief(c) for c in all_cams],
                "cameras_selected": [c["key"] for c in cams], "utc_started": results.utc_now_iso()}
    results.write_json(out_dir / "run.json", run_info)
    ctx.log(f"out_dir {out_dir}; raw_dir {raw_dir}; {len(cams)} camera(s): "
            + ", ".join(f"{c['name']} {c['node']}" for c in cams))
    if not cams:
        ctx.log("no USB video4linux camera found in /sys/class/video4linux (tests still run and record that)")
    run_info["prewarm"] = prewarm(ctx, build=not a.no_prewarm)
    rows = []
    for t in a.selected:
        ctx.current_test = t
        ctx.refresh_cameras()
        before = sysfs.arrival_state(ctx.cameras)
        t0 = time.time()
        ctx.log("start")
        try:
            res = load_module(t).run(ctx)
        except KeyboardInterrupt:
            ctx.log("interrupted")
            break
        except BaseException as e:  # a crashing test is a recorded result, never the end of the run
            res = error_result(ctx, t, e)
        t1 = time.time()
        after = sysfs.arrival_state(sysfs.discover_cameras())
        ev = sysfs.compare_arrivals(before, after)
        res["rearrivals"] = ev
        res["rearrival_flagged"] = bool([e for e in ev if e["event"] in ("re-arrived", "disappeared")])
        if ctx.env_facts.get("journal_readable"):
            res["kernel_log"] = kernel_log(t0, t1)
        if ctx.lock.waits:
            res["camlock_waits_s"] = list(ctx.lock.waits)
            ctx.lock.waits.clear()
        path = ctx.write(t, res)
        rows.append({"test": t, "file": path.name, "verdicts": verdict_line(res), "errors": len(res.get("errors") or []),
                     "rearrivals": len(ev), "elapsed_s": res.get("elapsed_s")})
        ctx.log(f"done in {t1 - t0:.1f}s -> {path.name}: {verdict_line(res)}")
    ctx.current_test = None
    if len(ctx.mode_alt_cache):
        ctx.mode_alt_cache.save(out_dir / "mode_alt_cache.json")
    run_info["utc_finished"] = results.utc_now_iso()
    results.write_json(out_dir / "run.json", run_info)
    write_summary(ctx, rows, run_info)
    ctx.log(f"summary: {out_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
