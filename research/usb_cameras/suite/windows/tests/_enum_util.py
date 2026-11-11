"""Shared plumbing for the Windows enumeration tests (W-ENV, W-POLICY, W-TOPO, W-ID, W-FMT, W-CTRL-LIST).

Not a test module (no run()). Stdlib only. Puts suite/, suite/windows and suite/windows/helpers on sys.path.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path
from typing import Callable

WIN_DIR = Path(__file__).resolve().parents[1]
SUITE_DIR = WIN_DIR.parent
HELPERS_DIR = WIN_DIR / "helpers"
for _p in (str(SUITE_DIR), str(WIN_DIR), str(HELPERS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import suitectx  # noqa: E402
from common import results  # noqa: E402


def start(ctx, test_id: str) -> dict:
    """new_result + a before-arrival snapshot (plan 6.1: log LastArrivalDate before and after each test)."""
    res = results.new_result(test_id, platform="windows", command=list(sys.argv) + [f"(module {test_id})"],
                             cameras=ctx.camera_summaries())
    res["_arrivals_before"] = suitectx.arrival_snapshot(ctx.cameras)
    return res


def finish(ctx, res: dict, measurements: dict, verdicts: dict, errors: list, name: str | None = None) -> dict:
    after = suitectx.arrival_snapshot(ctx.cameras)
    before = res.pop("_arrivals_before", {})
    changes = suitectx.diff_arrivals(before, after)
    measurements = dict(measurements)
    measurements["arrivals"] = {"before": before, "after": after, "changes": changes,
                                "unexplained_re_arrival": [c["key"] for c in changes if c.get("re_arrival")]}
    if changes:
        errors = list(errors) + [f"camera state changed during the test: {changes}"]
    results.finish_result(res, measurements=measurements, verdicts=verdicts, errors=errors)
    ctx.write(name or res["test"], res)
    return res


def guarded(ctx, test_id: str, body: Callable[[dict, dict, dict, list], None]) -> dict:
    """Run body(res, measurements, verdicts, errors); any exception becomes an error entry (never crashes the run)."""
    res = start(ctx, test_id)
    m: dict = {}
    v: dict = {}
    e: list = []
    try:
        body(res, m, v, e)
    except Exception as ex:  # noqa: BLE001
        e.append({"exception": f"{type(ex).__name__}: {ex}", "traceback": traceback.format_exc()})
        ctx.log(f"{test_id}: exception {type(ex).__name__}: {ex}")
    return finish(ctx, res, m, v, e)


def run_json(ctx, argv: list, timeout_s: float, cam: bool) -> tuple[dict | None, dict]:
    """Run a command (under camlock if cam) and parse its single JSON stdout. Returns (obj, run_record)."""
    r = ctx.camcmd(argv, timeout_s) if cam else ctx.run(argv, timeout_s)
    obj, err = suitectx.parse_json_stdout(r)
    rec = {k: r.get(k) for k in ("argv", "rc", "elapsed_s", "timed_out", "killed", "lock_wait_s", "spawn_error")}
    rec["stderr_tail"] = (r.get("stderr") or "")[-1500:]
    if err:
        rec["parse_error"] = err
    return obj, rec


def save_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------------------------------- descriptors (cached)
def get_descriptors(ctx, timeout_s: float = 25.0, refresh: bool = False) -> dict:
    """Configuration/device descriptors of every camera, read ONCE per suite run and cached in
    <out_dir>/descriptors/descriptors.json (W-TOPO, W-FMT and W-CTRL-LIST share it, so the Kiyo gets one set of
    GET_DESCRIPTOR requests per run). Each camera is read in its own child under camlock with a timeout; a hang or
    error is recorded per camera. Returns {"devices": [...], "runs": [...]}."""
    cache = ctx.out_dir / "descriptors" / "descriptors.json"
    if cache.exists() and not refresh:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except ValueError:
            pass
    devs, runs = [], []
    for c in ctx.cameras:
        argv = [sys.executable, str(HELPERS_DIR / "win_descriptors.py"), "--instance", c["instance_id"]]
        obj, rec = run_json(ctx, argv, timeout_s, cam=True)
        rec["camera_key"] = c["key"]
        runs.append(rec)
        d = (obj or {}).get("devices", [None])[0] if obj else None
        if d is None:
            d = {"instance_id": c["instance_id"], "errors": [f"descriptor read failed: rc={rec['rc']} "
                                                             f"timed_out={rec['timed_out']} {rec.get('parse_error')}"],
                 "timed_out": rec["timed_out"]}
        d["camera_key"] = c["key"]
        devs.append(d)
    doc = {"utc": results.utc_now_iso(), "devices": devs, "runs": runs,
           "note": "helpers/win_descriptors.py per camera under camlock (standard GET_DESCRIPTOR on EP0)"}
    results.write_json(cache, doc)
    return doc


def descriptor_for(desc_doc: dict, cam: dict) -> dict | None:
    for d in desc_doc.get("devices", []):
        if d.get("camera_key") == cam["key"] or str(d.get("instance_id", "")).upper() == cam["instance_id"].upper():
            return d
    return None


# ------------------------------------------------------------------------------------------- topology (child)
def collect_topology(ctx, descriptor_file: Path | None = None, timeout_s: float = 60.0) -> tuple[dict | None, dict]:
    """Run helpers/win_topology.py in a child (cached hub state only; no camera lock needed)."""
    argv = [sys.executable, str(HELPERS_DIR / "win_topology.py")]
    if descriptor_file:
        argv += ["--descriptors", str(descriptor_file)]
    return run_json(ctx, argv, timeout_s, cam=False)


# ------------------------------------------------------------------------------------------- misc
def cam_label(c: dict) -> str:
    return f"{c.get('name')} [{c.get('key')}]"


def by_function_instance(ctx) -> dict[str, dict]:
    return {str(c.get("function_instance_id", "")).upper(): c for c in ctx.cameras}


def key_for_link(ctx, link: str | None) -> str | None:
    """Map an MF symlink / DS DevicePath / FFmpeg alternative name / OpenCV path to the camera key (None = not a
    discovered camera, e.g. a virtual camera)."""
    if not link:
        return None
    import winpnp as wp
    fid = wp.link_to_instance_id(link)
    c = by_function_instance(ctx).get((fid or "").upper())
    return c["key"] if c else None


def timer() -> Callable[[], float]:
    t0 = time.perf_counter()
    return lambda: round(time.perf_counter() - t0, 4)


def standalone(run_fn: Callable, test_id: str, argv: list[str] | None = None) -> int:
    """`python w_x.py [--out-dir D] [--quick] ...`: build a SuiteCtx (discovery) and run one test module.
    Reuses <out_dir>/discovery.json from an earlier module run when --reuse-discovery is given."""
    import argparse
    ap = suitectx.add_common_args(argparse.ArgumentParser(description=f"{test_id} standalone"))
    ap.add_argument("--reuse-discovery", action="store_true")
    a = ap.parse_args(argv)
    cams = None
    if a.reuse_discovery and a.out_dir and (Path(a.out_dir) / "discovery.json").exists():
        cams = json.loads((Path(a.out_dir) / "discovery.json").read_text(encoding="utf-8")).get("cameras")
    ctx = suitectx.build_ctx(a, cameras=cams)
    if cams is not None:
        ctx.discovery = json.loads((Path(a.out_dir) / "discovery.json").read_text(encoding="utf-8"))
    res = run_fn(ctx)
    print(json.dumps({"test": res.get("test"), "elapsed_s": res.get("elapsed_s"),
                      "verdicts": {k: (x or {}).get("rating") for k, x in (res.get("verdicts") or {}).items()},
                      "errors": len(res.get("errors") or []), "out": str(ctx.out_dir / f"{test_id}.json")}, indent=1))
    return 0
