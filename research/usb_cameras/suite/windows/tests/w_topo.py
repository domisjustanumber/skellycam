"""W-TOPO: USB topology map, bandwidth domains, free ports and predicted conflicts (plan sections 5 and 6.2).

Opens no camera. Steps:
  1. Camera descriptors (alt tables), read once per run by helpers/win_descriptors.py in a child under camlock with a
     timeout, one camera at a time, the Kiyo included (shared cache <out_dir>/descriptors/descriptors.json).
  2. Topology snapshot by helpers/win_topology.py (cached hub-driver state + CfgMgr only, no admin, no request to a
     device) -> common.topology_model snapshot; saved as W-TOPO/snapshot.json.
  3. common.topology_model: compute_domains (observed load from OPEN periodic pipes, calibrated accounting), each
     camera's domain, every empty connectable port with its best label and domain.
  4. A ModeAltCache seeded from the alts measured on 10-27 (bandwidth_domain_model.md section 3, files
     results/windows/Gerald/bw_concurrency_rerun_20261027/r02,r03,r04,r06; same firmware as today), written to
     <out_dir>/mode_alt_cache.json for W-MULTI to extend with observed alts.
  5. Predictions (predict + suggest_ports + stay_here_alternatives + build_message via explain):
       a) every camera at its descriptor default MJPEG mode at once (the skellycam pattern);
       b) every camera at MJPG 1280x720@30 where offered;
       c) the plan's Gerald pairs, found at run time by VID:PID label (C922 046d:085c + generic 4c4a:4a55),
          wherever they are plugged: C922 720p30 / 640x480@30 / 1080p@5 next to the generic camera. Whether they
          share a domain comes from the topology, never assumed.
Verdict: "mapper" pseudo-rating (the G-BW rating itself needs W-MULTI's observed refusals): mapped without admin or
device requests, every camera in a domain, the predictions agree with the 10-27 measurements of the same model, and
label quality via topology_model.label_tier, the rule shared with W-MULTI and rate_bw: raw = bare ACPI names /
location paths only; 'controller + port number' labels are a legitimate fallback tier, not raw (=> partial only
when every free root-port label is raw).

Offline re-analysis (no camera, no device request, original files untouched):
    python w_topo.py --reanalyze RUN_DIR      # writes RUN_DIR/reanalysis/W-TOPO.json
re-runs the analysis on RUN_DIR/W-TOPO/snapshot.json + discovery.json + descriptors/descriptors.json with the
current topology_model (labels, socket evidence ranking, stay-here scoring, message wording).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _enum_util as U  # noqa: E402
from common import rating, results, topology_model as tm  # noqa: E402

TEST_ID = "W-TOPO"

# Measured mode -> alt on Gerald, 2026-10-27 (bandwidth_domain_model.md section 3 table; r02/r03/r04/r06 of
# results/windows/Gerald/bw_concurrency_rerun_20261027/). Packet sizes from the cameras' alt tables (same files).
# VID:PID:bcdDevice are labels of the measured firmware; lookups for other firmware are flagged by ModeAltCache.
SEED_SOURCE = ("results/agent_reports/plan_20261106/bandwidth_domain_model.md section 3; "
               "results/windows/Gerald/bw_concurrency_rerun_20261027/r02_c922_alt_by_mode.json, "
               "r03_c930e_alt_by_mode.json, r04_generic_alt_by_mode.json, r06_c930e_small_modes.json")
SEED = {
    ("046d", "085c", "0016"): {"MJPG 640x480@30": (4, 640, 1), "MJPG 1280x720@30": (9, 992, 2),
                               "MJPG 1920x1080@30": (11, 1020, 3), "MJPG 1920x1080@5": (5, 800, 1),
                               "YUY2 640x480@30": (10, 896, 3)},
    ("046d", "0843", "0013"): {"MJPG 640x480@30": (10, 896, 3), "MJPG 1280x720@30": (11, 1024, 3),
                               "MJPG 1920x1080@30": (11, 1024, 3), "MJPG 640x480@15": (8, 800, 2),
                               "MJPG 640x480@5": (3, 512, 1), "MJPG 640x360@30": (9, 992, 2),
                               "MJPG 480x270@30": (7, 640, 2), "MJPG 352x288@30": (6, 944, 1),
                               "MJPG 320x240@30": (5, 800, 1), "YUY2 640x480@30": (10, 896, 3)},
    ("4c4a", "4a55", "0100"): {"MJPG 640x480@30": (1, 1023, 3), "MJPG 1280x720@30": (1, 1023, 3),
                               "MJPG 1920x1080@30": (1, 1023, 3), "YUY2 640x480@30": (1, 1023, 3)},
}
# Observed during the 2026-11-06 suite run (not 10-27): PyAV-as-is negotiated YUY2 1920x1080@5 on the C922 and the
# open pipe read 1020x3 (alt 11 by packet size); needed to predict pyav_ds at the C922 1080p@5 pair (verifier, B3).
SEED_OBSERVED_SOURCE = ("results/windows/Gerald/suite_20261106T181941Z W-MULTI.json runs[61] (pyav_ds pair, C922 "
                        "format_fallback, observed_pipe 1020x3)")
SEED_OBSERVED = {
    ("046d", "085c", "0016"): {"YUY2 1920x1080@5": (11, 1020, 3)},
}
GERALD_PAIRS = [  # (label, C922 mode, expected verdict from the plan section 5 table)
    ("C922 MJPEG 720p30 (alt 9) + generic", "MJPG 1280x720@30", "over"),
    ("C922 MJPEG 640x480@30 (alt 4) + generic", "MJPG 640x480@30", "fits"),
    ("C922 MJPEG 1080p@5 (alt 5) + generic", "MJPG 1920x1080@5", "fits"),
]


def seed_cache(path: Path | None, save: bool = True, base: tm.ModeAltCache | None = None) -> tm.ModeAltCache:
    """Load ``path`` (or start from ``base`` / empty) and add the seed entries that are missing; never overwrites
    an existing (observed) entry. ``save`` False keeps everything in memory (offline re-analysis)."""
    if base is not None:
        cache = base
    else:
        cache = tm.ModeAltCache.load(path) if (path is not None and Path(path).exists()) else tm.ModeAltCache(path=path)
    for seed, source, note in ((SEED, "seed_measured_20261027", SEED_SOURCE),
                               (SEED_OBSERVED, "seed_observed_20261106", SEED_OBSERVED_SOURCE)):
        for (vid, pid, bcd), modes in seed.items():
            for mode, (alt, mp, mult) in modes.items():
                p = tm.parse_mode(mode)
                k = cache.make_key(vid, pid, bcd, p["format"], p["width"], p["height"], p["fps"])
                if k not in cache.entries:  # never overwrite an observed entry with the seed
                    cache.put(vid, pid, bcd, p["format"], p["width"], p["height"], p["fps"], alt, mp, mult,
                              source=source, note=note)
    if save and path is not None:
        cache.save(path)
    return cache


def mjpeg_modes(desc: dict | None) -> tuple[dict | None, list[dict]]:
    """(default MJPEG mode, all MJPEG modes) from a parsed configuration descriptor."""
    cfg = (desc or {}).get("configuration") or {}
    default, modes = None, []
    for s in ((cfg.get("uvc") or {}).get("streaming_interfaces") or []):
        for f in s.get("formats") or []:
            if f.get("format") != "MJPEG":
                continue
            for fr in f.get("frames") or []:
                rates = fr.get("fps") or ([fr.get("fps_max")] if fr.get("fps_max") else [])
                for r in rates:
                    modes.append({"format": "MJPG", "width": fr["wWidth"], "height": fr["wHeight"], "fps": r})
                if fr.get("bFrameIndex") == f.get("bDefaultFrameIndex") and default is None:
                    di = fr.get("dwDefaultFrameInterval")
                    default = {"format": "MJPG", "width": fr["wWidth"], "height": fr["wHeight"],
                               "fps": round(1e7 / di, 3) if di else (rates[0] if rates else None)}
    return default, modes


def _offers(modes: list[dict], mode: str) -> bool:
    p = tm.parse_mode(mode)
    return any(m["width"] == p["width"] and m["height"] == p["height"] and abs((m["fps"] or 0) - p["fps"]) < 0.5
               for m in modes)


def run(ctx) -> dict:
    def body(res, m, v, e):
        tdir = ctx.test_dir(TEST_ID)
        desc = U.get_descriptors(ctx)
        m["descriptor_reads"] = [{k: r.get(k) for k in ("camera_key", "rc", "elapsed_s", "timed_out", "lock_wait_s")}
                                 for r in desc.get("runs", [])]
        for d in desc.get("devices", []):
            if d.get("errors"):
                e.append({"camera": d.get("camera_key"), "descriptor_errors": d["errors"]})
        dfile = ctx.out_dir / "descriptors" / "descriptors.json"
        snap, rec = U.collect_topology(ctx, descriptor_file=dfile if dfile.exists() else None)
        m["collector_run"] = rec
        if snap is None:
            e.append("topology collector failed")
            v["mapper"] = rating.untested("no topology snapshot", rec)
            return
        results.write_json(tdir / "snapshot.json", snap)
        cache = seed_cache(ctx.out_dir / "mode_alt_cache.json")
        faulted = {}
        for c in ctx.cameras:   # suite dead-device gate (a wedged Kiyo cannot answer the descriptor read)
            f = getattr(ctx, "camera_faulted", None)
            rec = f(c["key"]) if callable(f) else None
            if rec:
                faulted[c["key"]] = f"device fault since {rec.get('since_utc')} ({rec.get('code') or rec.get('class')})"
        mm, vv, ee = analyze(snap, ctx.cameras, desc, cache, snapshot_file=str(tdir / "snapshot.json"),
                             cache_file=str(ctx.out_dir / "mode_alt_cache.json"), faulted=faulted)
        m.update(mm)
        v.update(vv)
        e.extend(ee)
    return U.guarded(ctx, TEST_ID, body)


def free_ports(snap: dict) -> list[dict]:
    """Every empty USB 2.0-capable connectable port with its label, label tier, domain and socket evidence."""
    idx = tm._Index(snap)
    pols = tm._policies_lookup(idx, None)
    free = []
    for p in snap["ports"]:
        if p.get("occupant_device_id") is not None or p.get("half") not in ("usb2", "unknown", None) \
                or p.get("connectable") in ("internal", "not_used"):
            continue
        comp = idx.ports.get(p.get("companion_id"))
        key, ctrl, rp = tm._hs_domain_for_port(idx, p, pols)
        lb = tm.port_label(snap, p["id"])
        ev = tm.socket_evidence(p)
        free.append({"port_id": p["id"], "label": lb, "label_tier": tm.label_tier(lb), "hs_domain": key,
                     "controller": tm._controller_display(idx, ctrl), "is_root_port": p["is_root_port"],
                     "acpi_name": p["label_parts"].get("acpi_name"),
                     "acpi_name_inferred": p["label_parts"].get("acpi_name_inferred"),
                     "connector": p.get("connector"), "usb3_companion_occupied":
                         bool(comp and comp.get("occupant_device_id")),
                     "socket_evidence": p["label_parts"].get("socket_evidence"),
                     "socket_evidence_level": ev["level"], "socket_evidence_detail": ev})
    return free


def analyze(snap: dict, cameras: list[dict], desc: dict, cache: tm.ModeAltCache, snapshot_file: str | None = None,
            cache_file: str | None = None, faulted: dict | None = None) -> tuple[dict, dict, list]:
    """The W-TOPO analysis on a snapshot (no device access): (measurements, verdicts, errors).
    ``faulted``: {camera key: reason} of cameras under the suite's dead-device gate; their missing alt table is
    reported as untested, not as a mapper failure. Cameras in the snapshot but not under test (a --camera filter)
    are listed, not judged."""
    faulted = dict(faulted or {})
    tested = {c["key"] for c in cameras}
    m: dict = {}
    v: dict = {}
    e: list = []
    m["snapshot_file"] = snapshot_file
    m["collector"] = snap.get("collector")
    doms = tm.compute_domains(snap)
    m["domains"] = [{k: d.get(k) for k in ("key", "kind", "controller_id", "root_port_id", "cameras", "load_us",
                                           "budget_us", "pct_budget", "pct_microframe", "verdict", "uncertain",
                                           "active_tts")} | {"members": len(d["members"]),
                                                             "policy_basis": d["policy"].get("basis")}
                    for d in doms]
    devs = {d["id"]: d for d in snap["devices"]}
    cam_dom = {}
    for c in snap["cameras"]:
        try:
            cam_dom[c["key"]] = tm.domain_key(snap, c["device_id"])
        except KeyError as ex:
            cam_dom[c["key"]] = None
            e.append(f"no domain for {c['key']}: {ex}")
    m["camera_domains"] = cam_dom
    m["cameras_in_snapshot"] = [{"key": c["key"], "name": c.get("name"), "speed": devs[c["device_id"]]["speed"],
                                 "current_alt": c.get("current_alt"), "alt_table_len": len(c.get("alt_table") or []),
                                 "domain": cam_dom.get(c["key"]),
                                 "root_port": devs[c["device_id"]].get("root_port_id")} for c in snap["cameras"]]
    missing = sorted({c["key"] for c in cameras} - {c["key"] for c in snap["cameras"]})
    if missing:
        e.append(f"cameras discovered but not in the topology snapshot: {missing}")
    # ---- free ports with labels
    free = free_ports(snap)
    m["free_ports"] = free
    m["free_port_count"] = len(free)
    # ---- mode-alt cache
    m["mode_alt_cache"] = {"file": cache_file, "entries": len(cache), "seed_source": SEED_SOURCE,
                           "seed_observed_source": SEED_OBSERVED_SOURCE}
    # ---- predictions
    by_key = {c["key"]: c for c in cameras}
    defaults, offered = {}, {}
    for c in cameras:
        dflt, modes = mjpeg_modes(U.descriptor_for(desc, c))
        defaults[c["key"]], offered[c["key"]] = dflt, modes
    m["default_modes"] = {k: tm.mode_text(x) if x else None for k, x in defaults.items()}
    scenarios = {}

    def scenario(name, reqs):
        ex = tm.explain(snap, reqs, cache)
        pred = ex["prediction"]
        scenarios[name] = {
            "requests": [{"camera_key": r["camera_key"], "mode": tm.mode_text(r["mode"])} for r in reqs],
            "domains": [{k: d.get(k) for k in ("key", "predicted_load_us", "other_load_us", "pct_budget",
                                               "pct_microframe", "verdict", "members", "incomplete")}
                        for d in pred["domains"]],
            "resolved": pred.get("resolved") or pred.get("requests"),
            "conflicts": [{k: c.get(k) for k in ("domain_key", "cameras", "pct_total", "pct_microframe", "verdict",
                                                 "shared_hop", "other_load_us", "other_devices")}
                          for c in pred["conflicts"]],
            "warnings": [{k: c.get(k) for k in ("domain_key", "cameras", "pct_total", "verdict")}
                         for c in pred.get("warnings", [])],
            "messages": ex["messages"]}
        return scenarios[name]

    reqs = [{"camera_key": k, "mode": defaults[k]} for k in by_key if defaults.get(k)]
    if reqs:
        scenario("all_cameras_default_mode", reqs)
    reqs = [{"camera_key": k, "mode": "MJPG 1280x720@30" if _offers(offered[k], "MJPG 1280x720@30")
             else defaults[k]} for k in by_key if defaults.get(k) or _offers(offered[k], "MJPG 1280x720@30")]
    if reqs:
        scenario("all_cameras_720p30", reqs)
    c922 = [c for c in cameras if (c["vid"], c["pid"]) == ("046d", "085c")]
    gen = [c for c in cameras if (c["vid"], c["pid"]) == ("4c4a", "4a55")]
    pair_checks = []
    if c922 and gen:
        for label, mode, expected in GERALD_PAIRS:
            gmode = "MJPG 1280x720@30" if _offers(offered[gen[0]["key"]], "MJPG 1280x720@30") \
                else defaults[gen[0]["key"]]
            s = scenario(f"pair: {label}", [{"camera_key": c922[0]["key"], "mode": mode},
                                            {"camera_key": gen[0]["key"], "mode": gmode}])
            same = cam_dom.get(c922[0]["key"]) == cam_dom.get(gen[0]["key"])
            dom = next((d for d in s["domains"] if c922[0]["key"] in d["members"]), {})
            # plan's prediction counts the two cameras only; the model adds other open iso pipes in the domain
            pair_only = round(100 * (dom.get("predicted_load_us", 0) - (dom.get("other_load_us") or 0)) / 125, 1) \
                if dom else None
            pair_checks.append({"pair": label, "same_domain": same, "expected_if_same_domain": expected,
                                "predicted_verdict": dom.get("verdict"), "pair_only_pct_microframe": pair_only,
                                "with_other_load_pct_microframe": dom.get("pct_microframe"),
                                "other_load_us": dom.get("other_load_us"),
                                "agrees": (dom.get("verdict") == expected) if same else None,
                                "has_required_sentence": any(tm.MESSAGE_SUGGEST_LINE in x["message"] and
                                                             "share USB bandwidth" in x["message"]
                                                             for x in s["messages"]) if s["messages"] else None})
    else:
        pair_checks.append({"pair": "Gerald pairs", "skipped": "C922 (046d:085c) or generic (4c4a:4a55) "
                                                                "not present"})
    m["gerald_pairs"] = pair_checks
    m["scenarios"] = scenarios
    # ---- suggestion sanity for every message: never the conflict domain, never an occupied SS twin
    sugg_checks = []
    for name, s in scenarios.items():
        for msg in s["messages"]:
            bad = []
            for g in msg["suggestions"]:
                for p in g["ports"]:
                    if p["domain_key"] == msg["domain_key"]:
                        bad.append(p["port_id"])
            sugg_checks.append({"scenario": name, "domain": msg["domain_key"], "n_ports":
                                sum(len(g["ports"]) for g in msg["suggestions"]), "ports_in_conflict_domain": bad})
    m["suggestion_checks"] = sugg_checks
    # ---- labels: shared rule (topology_model.label_tier): raw only if every free root-port label is a bare ACPI
    # name / location path; 'port N (HSnn, ...)' is the 'controller + port number' tier, which is not raw
    labels = [f["label"] for f in free if f["is_root_port"]]
    labels_raw = bool(tm.labels_raw(labels))
    m["labels_raw"] = labels_raw
    m["label_tiers"] = {lb: tm.label_tier(lb) for lb in labels}
    m["label_rule"] = ("topology_model.label_tier: raw = acpi_or_location_path / location_unknown only (shared with W-MULTI "
                       "and rate_bw)")
    crit = [
        {"criterion": "snapshot built without admin and without requests to devices",
         "met": (snap.get("collector") or {}).get("requests_to_devices") == 0 and not
         (snap.get("collector") or {}).get("elevated"), "detail": snap.get("collector")},
        {"criterion": "every discovered camera is in the snapshot with a bandwidth domain",
         "met": not missing and all(cam_dom.get(c["key"]) for c in cameras),
         "detail": {"missing": missing, "domains": cam_dom}},
        {"criterion": "camera alt tables available (descriptor read worked for every camera)",
         "met": all(c.get("alt_table") for c in snap["cameras"] if c["key"] in tested and c["key"] not in faulted),
         "detail": {c["key"]: (bool(c.get("alt_table")) if c["key"] in tested and c["key"] not in faulted else
                               ("untested: " + faulted[c["key"]] if c["key"] in faulted else "not under test"))
                    for c in snap["cameras"]}},
        {"criterion": "Gerald pairs predicted as measured on 10-27 (720p30 over; 640x480@30 and 1080p@5 fit)",
         "met": (all(p.get("agrees") for p in pair_checks if p.get("agrees") is not None)
                 if any(p.get("agrees") is not None for p in pair_checks) else None), "detail": pair_checks},
        {"criterion": "suggested ports never in the conflicting domain",
         "met": all(not s["ports_in_conflict_domain"] for s in sugg_checks) if sugg_checks else None,
         "detail": sugg_checks},
        {"criterion": "port labels better than raw ACPI names / location paths (shared label_tier rule)",
         "met": not labels_raw, "detail": {lb: tm.label_tier(lb) for lb in labels[:12]}},
    ]
    failed = [c for c in crit if c["met"] is False]
    core_failed = [c for c in failed if not c["criterion"].startswith("port labels")]
    v["mapper"] = {"rating": "no" if core_failed else ("partial" if failed else "yes"), "criteria": crit,
                   "evidence": {"note": "pseudo-rating of the mapper only; G-BW needs W-MULTI's observed refusals",
                                "snapshot": snapshot_file, "label_tiers": m["label_tiers"],
                                "device_faults": faulted or None}}
    v["G-BW"] = rating.untested("W-TOPO predicts only; W-MULTI observes refusals and rates G-BW",
                                {"predicted_conflicts": {k: len(s["conflicts"]) for k, s in scenarios.items()}})
    return m, v, e


def reanalyze(run_dir: str | Path, write: bool = True) -> dict:
    """Offline W-TOPO re-analysis of a finished run (see the module docstring). Writes reanalysis/W-TOPO.json."""
    rd = Path(run_dir)
    snap = json.loads((rd / TEST_ID / "snapshot.json").read_text(encoding="utf-8"))
    cams = json.loads((rd / "discovery.json").read_text(encoding="utf-8")).get("cameras", [])
    dfile = rd / "descriptors" / "descriptors.json"
    desc = json.loads(dfile.read_text(encoding="utf-8")) if dfile.exists() else {"devices": []}
    base = tm.ModeAltCache.load(rd / "mode_alt_cache.json")
    base.path = None  # never written back
    cache = seed_cache(None, save=False, base=base)
    m, v, e = analyze(snap, cams, desc, cache, snapshot_file=str(rd / TEST_ID / "snapshot.json"),
                      cache_file=f"{rd / 'mode_alt_cache.json'} (in memory + seeds; not written)")
    orig = {}
    try:
        orig = json.loads((rd / f"{TEST_ID}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    out = {"test": TEST_ID, "kind": "offline_reanalysis", "utc": results.utc_now_iso(), "source_run": str(rd),
           "inputs": [f"{TEST_ID}/snapshot.json", "discovery.json", "descriptors/descriptors.json",
                      "mode_alt_cache.json (read only)"],
           "original_ratings": {k: (x or {}).get("rating") for k, x in (orig.get("verdicts") or {}).items()},
           "ratings": {k: (x or {}).get("rating") for k, x in v.items()},
           "changes_applied": ["shared label_tier rule (controller + port number is not raw)",
                               "socket evidence: internal-header phantoms last, 'user-accessible' only with evidence "
                               "beyond _UPC", "stay-here keeps format and fps, then maximises w*h",
                               "seed: C922 YUY2 1920x1080@5 observed 1020x3"],
           "measurements": m, "verdicts": v, "errors": e}
    if write:
        results.write_json(rd / "reanalysis" / f"{TEST_ID}.json", out)
    return out


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--reanalyze":
        r = reanalyze(sys.argv[2])
        print(json.dumps({"original": r["original_ratings"], "reanalysis": r["ratings"]}, indent=1))
        sys.exit(0)
    sys.exit(U.standalone(run, TEST_ID))
