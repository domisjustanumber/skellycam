"""W-ID: does every API's device list map 1:1 to the camera_identity keys, stably? (plan G-ID, section 6.2)

Enumerations (none starts a stream), each repeated --repeats times (20; --quick 5):
  * Media Foundation and DirectShow: ``wincam list`` (property bags only: no ActivateObject / BindToObject);
  * PyAV 19.0.2 (FFmpeg 9.0.2) dshow ``list_devices`` and the FFmpeg 9.0.2 CLI: FFmpeg binds each capture filter to
    print its media type, so these run under camlock with a timeout;
  * OpenCV: cv2_enumerate_cameras 1.4.0 CAP_MSMF / CAP_DSHOW lists (MFEnumDeviceSources + property bags; the index
    is what VideoCapture(index, api) opens); cross-checked against the MF / DS order from wincam;
  * the suite's own key source (suitectx discovery: CfgMgr + cached hub data).
Each USB entry is mapped to a key through its link (MF symlink, DS DevicePath, FFmpeg alternative name, OpenCV
path) -> function instance -> discovered camera. Virtual cameras (NDI, OBS ...) are not USB and are ignored.
Records per API: list order of keys per run, 1:1 check, order stability, enumeration time (p50/p95/max).

Natural evidence (no new replug): compares today's keys / instance IDs / port paths / links with the 10-27 results
in results/windows/Gerald/naming_rerun_20261027/ (cameras have moved since). A serial-keyed camera whose port changed
but whose key did not is evidence for "serial cameras keep their key over a port move". Since 2026-11-08 also
against the previous suite run's discovery.json (``natural_replug_evidence``): a camera that re-arrived at the same
port path (LastArrivalDate changed) must keep its key (``same_port_replug``), a serial camera that moved must keep
its key (``port_move_serial``). Reboot persistence stays unmeasured, so the cell stays provisional until A1.
Rating: common.rating.rate_id (persistence: reboot / same-port replug are attended item A1 -> None). Unmeasured
persistence stays 'partial' with ``provisional`` True (verifier on ctrl_id_env B8: a yes needs the A1 steps, and the
10-27 comparison is reboot evidence for serial keys only). ``G-ID_per_api`` holds the full rate_id verdict per API
(criteria + evidence), not a bare string (B9). The OpenCV rows come from cv2_enumerate_cameras; no VideoCapture(i)
is opened to confirm which device an index opens (verifier V6), which the evidence says.

Offline: ``python w_id.py --reanalyze <run_dir>`` re-rates a stored W-ID.json into <run_dir>/reanalysis/W-ID.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _enum_util as U  # noqa: E402
from common import cycstats, rating  # noqa: E402

TEST_ID = "W-ID"
EARLIER = "results/windows/Gerald/naming_rerun_20261027"


def _is_usb_link(link: str | None) -> bool:
    return bool(link) and "usb#vid_" in link.lower()


def _map_list(ctx, entries: list[dict], path_key: str) -> tuple[list, list]:
    """(keys of the USB entries in list order (None = not mappable), raw rows)."""
    keys, rows = [], []
    for d in entries:
        link = d.get(path_key)
        if not _is_usb_link(link):
            continue
        k = U.key_for_link(ctx, link)
        keys.append(k)
        rows.append({"index": d.get("index"), "name": d.get("friendly_name") or d.get("name"), "link": link, "key": k})
    return keys, rows


def _timing(vals: list[float]) -> dict:
    return cycstats.percentiles([x for x in vals if x is not None])


def _boot_time_utc() -> str | None:
    try:
        import ctypes
        import datetime as dt
        ms = ctypes.windll.kernel32.GetTickCount64
        ms.restype = ctypes.c_ulonglong
        return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(milliseconds=ms())).isoformat()
    except Exception:  # noqa: BLE001
        return None


def previous_discovery(out_dir: Path) -> tuple[str | None, list[dict]]:
    """(run folder name, cameras) of the newest EARLIER run of this host that has a discovery.json."""
    here = Path(out_dir)
    try:
        prev = sorted((p for p in here.parent.iterdir() if p.is_dir() and p != here and p.name < here.name
                       and (p / "discovery.json").exists()), key=lambda p: p.name)
    except OSError:
        return None, []
    for p in reversed(prev):
        try:
            return p.name, list(json.loads((p / "discovery.json").read_text(encoding="utf-8")).get("cameras") or [])
        except (OSError, ValueError):
            continue
    return None, []


def compare_with_previous(cams: list[dict], prev: list[dict]) -> dict:
    """Natural replug evidence (no new replug): each camera now vs the previous run's discovery. A camera whose
    LastArrivalDate changed at the same port path re-arrived there (a replug or a re-enumeration): its key must not
    change. A camera found at another port (matched by key, else by VID:PID + serial, else a unique VID:PID) moved:
    a serial key must not change, a port key does by design. ``same_port_replug`` / ``port_move_serial``: True when
    every such case kept its key, False when one changed, None when there was no such case."""
    by_key = {c.get("key"): c for c in prev}
    out = []
    for c in cams:
        p = by_key.get(c.get("key"))
        how = "key"
        if p is None:
            same = [x for x in prev if (x.get("vid"), x.get("pid")) == (c.get("vid"), c.get("pid"))]
            ser = [x for x in same if c.get("serial") and x.get("serial") == c.get("serial")]
            p, how = (ser[0], "vid:pid:serial") if ser else ((same[0], "unique vid:pid") if len(same) == 1
                                                             else (None, None))
        rec = {"key_now": c.get("key"), "name": c.get("name"), "key_kind": c.get("key_kind"),
               "is_kiyo": c.get("is_kiyo"), "matched_by": how}
        if p is None:
            rec["kind"] = "not in the previous run"
            out.append(rec)
            continue
        same_port = (p.get("port_path") or "").upper() == (c.get("port_path") or "").upper()
        re_arr = bool(p.get("last_arrival")) and p.get("last_arrival") != c.get("last_arrival")
        rec.update(key_previous=p.get("key"), key_same=p.get("key") == c.get("key"), same_port=same_port,
                   last_arrival_previous=p.get("last_arrival"), last_arrival_now=c.get("last_arrival"),
                   re_arrived=re_arr,
                   kind=("port move" if not same_port else ("same-port re-arrival" if re_arr else "no re-arrival")))
        out.append(rec)
    spr = [r for r in out if r.get("kind") == "same-port re-arrival"]
    pms = [r for r in out if r.get("kind") == "port move" and r.get("key_kind") == "serial"]
    return {"cameras": out,
            "same_port_replug": (all(r["key_same"] for r in spr) if spr else None),
            "port_move_serial": (all(r["key_same"] for r in pms) if pms else None),
            "n_same_port_re_arrivals": len(spr), "n_port_moves": sum(1 for r in out if r.get("kind") == "port move"),
            "note": "natural evidence only (a re-arrival may be a replug or a re-enumeration); reboot persistence "
                    "and a deliberate replug / port move are the attended A1 steps, so G-ID stays provisional"}


def natural_replug_evidence(ctx) -> dict:
    name, prev = previous_discovery(Path(ctx.out_dir))
    if not prev:
        return {"previous_run": name, "same_port_replug": None, "port_move_serial": None,
                "note": "no earlier run with a discovery.json for this host"}
    all_cams = list((getattr(ctx, "discovery", None) or {}).get("cameras") or []) or list(ctx.cameras)
    return {"previous_run": name, **compare_with_previous(all_cams, prev)}


def natural_evidence(ctx) -> dict:
    root = ctx.research_root / EARLIER
    out: dict = {"earlier_dir": str(root), "cameras": [], "boot_time_utc": _boot_time_utc()}
    f = root / "camera_identity" / "camera_identity_run1.json"
    if not f.exists():
        out["error"] = f"{f} not found"
        return out
    earlier = json.loads(f.read_text(encoding="utf-8"))
    out["earlier_utc"] = earlier.get("utc_started")
    out["earlier_excluded_vidpid"] = earlier.get("excluded_vidpid")
    api = root / "win_api_names" / "api_names.json"
    api_doc = json.loads(api.read_text(encoding="utf-8")) if api.exists() else {}
    for c in ctx.cameras:
        prev = [e for e in earlier.get("cameras", []) if (e.get("vid"), e.get("pid")) == (c["vid"], c["pid"])]
        rec = {"key_now": c["key"], "name": c.get("name"), "vid": c["vid"], "pid": c["pid"]}
        if not prev:
            rec["earlier"] = None
            rec["note"] = ("not in the 10-27 identity runs (excluded: " + str(earlier.get("excluded_vidpid")) + ")"
                           if c.get("is_kiyo") else "no 10-27 record for this VID:PID")
            out["cameras"].append(rec)
            continue
        p = prev[0]
        nat = p.get("native") or {}
        rec["earlier"] = {"key": p.get("key"), "port_path": p.get("port_path"),
                          "composite_instance_id": nat.get("composite_instance_id"),
                          "video_function_instance_id": nat.get("video_function_instance_id"),
                          "msmf_symbolic_link": nat.get("msmf_symbolic_link")}
        moved = (p.get("port_path") or "").upper() != (c.get("port_path") or "").upper()
        rec.update(port_moved=moved, key_same=p.get("key") == c["key"],
                   composite_instance_same=(nat.get("composite_instance_id") or "").upper() == c["instance_id"].upper(),
                   function_instance_same=(nat.get("video_function_instance_id") or "").upper() ==
                   (c.get("function_instance_id") or "").upper(),
                   mf_symlink_same=(nat.get("msmf_symbolic_link") or "").lower() == (c.get("mf_symlink") or "").lower(),
                   key_kind=c.get("key_kind"))
        if c.get("key_kind") == "serial":
            rec["interpretation"] = ("serial key kept across a port move" if moved and rec["key_same"] else
                                     "serial key kept (same port)" if rec["key_same"] else "serial key CHANGED")
        else:
            rec["interpretation"] = ("port key changed with the port move (expected for a serial-less camera)"
                                     if moved else "same port; key " + ("kept" if rec["key_same"] else "CHANGED"))
        out["cameras"].append(rec)
    if api_doc:
        out["earlier_api_order"] = [{"product": r.get("product"), "mf_index": r.get("mf_index"),
                                     "dshow_index": r.get("dshow_index")} for r in api_doc.get("mapping", [])]
    return out


OPENCV_CAVEAT = ("index order from cv2_enumerate_cameras 1.4.0 (MFEnumDeviceSources / property bags); no "
                 "VideoCapture(index) was opened to confirm which device an index opens")


def per_api_verdicts(rate_runs: dict, expected: list, persistence: dict, min_runs: int) -> dict:
    """{api: full rate_id verdict} (B9: criteria and evidence, not a bare rating string)."""
    out = {}
    for a, r in rate_runs.items():
        vv = rating.rate_id({a: r}, expected, persistence, min_runs=min_runs)
        if a.startswith("opencv"):
            vv["evidence"]["caveat"] = OPENCV_CAVEAT
        out[a] = vv
    return out


def _runs_from_summary(pa: dict) -> list:
    """Rebuild per-run key lists from a stored per_api summary (exact when order_stable; otherwise the first run
    plus one differing run, which is what the summary can still say)."""
    n, first = pa.get("runs") or 0, pa.get("first_run_keys") or []
    if not n:
        return []
    if pa.get("order_stable"):
        return [list(first) for _ in range(n)]
    other = list(reversed(first)) if len(first) > 1 else list(first) + [None]
    return [list(first) for _ in range(n - 1)] + [other]


def reanalyze(run_dir: Path) -> dict:
    """Re-rate W-ID from the stored measurements (no enumeration): full per-API verdicts (B9), provisional flag."""
    d = json.loads((Path(run_dir) / "W-ID.json").read_text(encoding="utf-8"))
    m = d.get("measurements") or {}
    expected = m.get("expected_keys") or []
    n = m.get("repeats") or 20
    pi = m.get("persistence_inputs") or {}
    persistence = {k: pi.get(k) for k in ("reboot", "same_port_replug", "port_move_serial")}
    rate_runs = {a: _runs_from_summary(pa) for a, pa in (m.get("per_api") or {}).items() if a != "pnp_discovery"}
    v = {"G-ID": rating.rate_id(rate_runs, expected, persistence, min_runs=min(n, 20)),
         "G-ID_per_api": per_api_verdicts(rate_runs, expected, persistence, min(n, 20))}
    old = d.get("verdicts") or {}
    changes = []
    if (old.get("G-ID") or {}).get("rating") != v["G-ID"]["rating"]:
        changes.append({"cell": "G-ID", "from": (old.get("G-ID") or {}).get("rating"), "to": v["G-ID"]["rating"]})
    for a, vv in v["G-ID_per_api"].items():
        o = (old.get("G-ID_per_api") or {}).get(a)
        o = o.get("rating") if isinstance(o, dict) else o
        if o != vv["rating"]:
            changes.append({"cell": f"G-ID_per_api|{a}", "from": o, "to": vv["rating"]})
    return {"test": TEST_ID, "reanalysis_of": str(Path(run_dir) / "W-ID.json"), "verdicts": v, "changes": changes,
            "fixes_applied": ["B9 G-ID_per_api carries full verdicts", "provisional flag (B8 verifier: stays partial)"],
            "runs_rebuilt_from_summary": {a: bool((m.get("per_api") or {}).get(a, {}).get("order_stable"))
                                          for a in rate_runs}}


def run(ctx) -> dict:
    def body(res, m, v, e):
        n = int(getattr(ctx.args, "repeats", 20) or 20)
        if getattr(ctx.args, "quick", False):
            n = min(n, 5)
        m["repeats"] = n
        expected = [c["key"] for c in ctx.cameras]
        api_runs: dict[str, list] = {}
        api_times: dict[str, list] = {}
        api_first: dict[str, list] = {}
        api_errors: dict[str, list] = {}
        # ---- MF + DS via wincam list (no activation; no lock)
        for i in range(n):
            obj, rec = U.run_json(ctx, [str(ctx.wincam), "list"], 30, cam=False)
            if obj is None:
                api_errors.setdefault("mf", []).append(rec)
                api_errors.setdefault("ds", []).append(rec)
                continue
            for api, pk in (("mf", "symlink"), ("ds", "device_path")):
                lst = (obj.get(api) or {}).get("devices") or []
                keys, rows = _map_list(ctx, lst, pk)
                api_runs.setdefault(api, []).append(keys)
                api_times.setdefault(api, []).append((obj.get(api) or {}).get("elapsed_ms"))
                if i == 0:
                    api_first[api] = rows
        # ---- PyAV, FFmpeg CLI, OpenCV via helpers/enum_apis.py under camlock
        helper = ctx.helpers_dir / "enum_apis.py"
        for which, api_names in (("pyav", ["pyav_dshow"]), ("ffmpeg", ["ffmpeg_cli_dshow"]),
                                 ("opencv", ["opencv_msmf", "opencv_dshow"])):
            argv = ["uv", "run", "--python", ctx.python, "--script", str(helper), which, "--repeats", str(n)]
            obj, rec = U.run_json(ctx, argv, timeout_s=60 + 6 * n, cam=True)
            m.setdefault("helper_runs", {})[which] = rec
            if obj is None:
                for a in api_names:
                    api_errors.setdefault(a, []).append(rec)
                continue
            m.setdefault("versions", {})[which] = obj.get("versions")
            for r in obj.get("runs", []):
                if which == "opencv":
                    for a, sect in (("opencv_msmf", "CAP_MSMF"), ("opencv_dshow", "CAP_DSHOW")):
                        s = r.get(sect) or {}
                        keys, rows = _map_list(ctx, s.get("devices") or [], "path")
                        api_runs.setdefault(a, []).append(keys)
                        api_times.setdefault(a, []).append(s.get("elapsed_ms"))
                        api_first.setdefault(a, rows)
                        if s.get("error"):
                            api_errors.setdefault(a, []).append(s["error"])
                else:
                    a = api_names[0]
                    keys, rows = _map_list(ctx, r.get("devices") or [], "path")
                    api_runs.setdefault(a, []).append(keys)
                    api_times.setdefault(a, []).append(r.get("elapsed_ms"))
                    api_first.setdefault(a, rows)
                    if r.get("error"):
                        api_errors.setdefault(a, []).append(r["error"])
        # ---- the key source itself (discovery, CfgMgr only)
        disc_keys, disc_t = [], []
        for i in range(n):
            t0 = time.perf_counter()
            d = U.suitectx.discover(ctx.wincam)
            disc_t.append(round((time.perf_counter() - t0) * 1000, 2))
            disc_keys.append([c["key"] for c in d.get("cameras", [])])
            if d.get("errors"):
                api_errors.setdefault("pnp_discovery", []).append(d["errors"])
        api_runs["pnp_discovery"] = disc_keys
        api_times["pnp_discovery_incl_child_process"] = disc_t
        # ---- per API summary
        per_api = {}
        for api, runs in api_runs.items():
            per_api[api] = {
                "runs": len(runs),
                "first_run_keys": runs[0] if runs else None,
                "first_run_entries": api_first.get(api),
                "one_to_one_every_run": bool(runs) and all(len(r) == len(set(r)) and set(r) == set(expected)
                                                           for r in runs),
                "all_mappable": bool(runs) and all(all(k is not None for k in r) for r in runs),
                "order_stable": bool(runs) and all(r == runs[0] for r in runs),
                "distinct_orders": len({tuple(r) for r in runs}),
                "missing_keys_first_run": sorted(set(expected) - set(runs[0])) if runs else expected,
                "timing_ms": _timing(api_times.get(api) or api_times.get(api + "_incl_child_process") or []),
                "errors": api_errors.get(api)}
        m["per_api"] = per_api
        m["expected_keys"] = expected
        m["timing_ms"] = {a: _timing(t) for a, t in api_times.items()}
        # ---- OpenCV index == DS / MF enumeration order?
        idx_checks = {}
        for cv, wc, fld in (("opencv_dshow", "ds", "ds_index"), ("opencv_msmf", "mf", "mf_index")):
            rows = api_first.get(cv) or []
            idx_checks[cv] = {"opencv_index_by_key": {r["key"]: r["index"] for r in rows},
                              "wincam_index_by_key": {c["key"]: c.get(fld) for c in ctx.cameras},
                              "equal": bool(rows) and all(r["index"] == next((c.get(fld) for c in ctx.cameras
                                                                              if c["key"] == r["key"]), None)
                                                          for r in rows)}
        m["opencv_index_vs_enumeration_order"] = idx_checks
        # ---- natural evidence
        nat = natural_evidence(ctx)
        m["natural_evidence"] = nat
        serial_moves = [c for c in nat.get("cameras", []) if c.get("key_kind") == "serial" and c.get("port_moved")]
        rep = natural_replug_evidence(ctx)
        m["natural_replug_evidence"] = rep
        pms = all(c["key_same"] for c in serial_moves) if serial_moves else None
        if pms is None:
            pms = rep.get("port_move_serial")
        # reboot stays None: the cell remains provisional until the attended A1 steps
        persistence = {"reboot": None, "same_port_replug": rep.get("same_port_replug"), "port_move_serial": pms}
        boot = nat.get("boot_time_utc")
        rebooted = bool(boot and nat.get("earlier_utc") and boot > nat["earlier_utc"])
        m["persistence_inputs"] = {**persistence, "rebooted_since_earlier_run": rebooted, "boot_time_utc": boot,
                                   "serial_keys_kept_over_reboot": ([c["key_same"] for c in nat.get("cameras", [])
                                                                     if c.get("key_kind") == "serial"]
                                                                    if rebooted else None),
                                   "note": "reboot and same-port replug are attended item A1 (port-keyed cameras "
                                           "moved since 10-27, so a reboot comparison is only possible for serial "
                                           "keys); port_move_serial comes from the 10-27 comparison"}
        rate_runs = {a: r for a, r in api_runs.items() if a != "pnp_discovery"}
        v["G-ID"] = rating.rate_id(rate_runs, expected, persistence, min_runs=min(n, 20))
        v["G-ID_per_api"] = per_api_verdicts(rate_runs, expected, persistence, min(n, 20))
        v["key_source_stability"] = {
            "rating": "yes" if per_api["pnp_discovery"]["order_stable"] and
            per_api["pnp_discovery"]["one_to_one_every_run"] else "no",
            "criteria": [{"criterion": f"suitectx discovery returns the same keys in {n} runs",
                          "met": per_api["pnp_discovery"]["order_stable"], "detail": per_api["pnp_discovery"]}],
            "evidence": {"note": "the identity key source itself (CfgMgr + cached hub data)"}}
        if getattr(ctx.args, "quick", False):
            v["G-ID"]["note"] = (v["G-ID"].get("note") or "") + f" (quick run: {n} repeats)"
        if filtered:
            m["camera_filter"] = {"filtered_keys": filtered, "note": "W-ID opens no camera, so it maps every "
                                  "discovered camera (the run's --camera debugging filter does not apply here)"}

    # W-ID only enumerates (no camera is opened), and every API lists every attached camera; with the runner's
    # --camera debugging filter the identity map must still cover all discovered cameras, else the filtered-out
    # ones (e.g. the Kiyo) show up as unmapped entries and G-ID reads 'no'.
    all_cams = list((getattr(ctx, "discovery", None) or {}).get("cameras") or []) or list(ctx.cameras)
    kept = {c.get("key") for c in ctx.cameras}
    filtered = [c.get("key") for c in all_cams if c.get("key") not in kept]
    saved = ctx.cameras
    if filtered:
        ctx.cameras = all_cams
    try:
        return U.guarded(ctx, TEST_ID, body)
    finally:
        ctx.cameras = saved


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--reanalyze":
        from common import results as _r
        _out = reanalyze(Path(sys.argv[2]))
        print(_r.write_json(Path(sys.argv[2]) / "reanalysis" / f"{TEST_ID}.json", _out), _out["changes"])
        sys.exit(0)
    sys.exit(U.standalone(run, TEST_ID))
