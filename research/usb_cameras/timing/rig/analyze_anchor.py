# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Timestamp-anchor analysis: where does each camera timestamp sit relative to when light hit the sensor?

Usage (from the repo root):
  uv run --script research/usb_cameras/timing/rig/analyze_anchor.py RUN_DIR [RUN_DIR ...]
      [--raw-dir RAW_RUN_DIR ...] [--line-time-ns KEY=NS ...] [--gamma 2.2] [--channel luma|green]
      [--cols 0.2,0.8] [--out-dir DIR] [--no-cache]

RUN_DIR = a run_anchor_test.py results folder: rig_session.json, rig_events.log, rig_pings.csv and one
capture_rNN/ folder per stream (re)start holding <key>.frames.jsonl, <key>.session.json, <key>.controls.jsonl.
The MJPEG is looked up next to the frames.jsonl, then under --raw-dir (same capture_rNN/ layout), then in the raw
mirror %USERPROFILE%/Documents/skellycam-raw/<path of RUN_DIR relative to research/usb_cameras>.
Double-strobe runs (gap_us > 0 in rig_session.json) are analysed first and their line time L is used for
single-strobe runs of the same camera and mode; --line-time-ns overrides (KEY may be a camera_key substring or 'all').

Conventions: time unit ns (reports in us/ms as labelled); ESP32 time = esp_timer ns; host time = QPC ns; row 0 =
top of the decoded image = read out first; s0 = row-0 exposure start; E = measured exposure; L = line time;
H = rows; T_ro = H*L. Model ts = a + b*s0 + alpha*b*E (score.py). For alpha ~ 1 the downstream formula is
    t_light(row y) = ts - K_alpha1 - E/2 + (y/H) * T_ro       (QPC ns, mid-exposure of row y)
K_abs is ESTIMATED (ping-path asymmetry; both ping offsets reported); K_rel (same run, other camera/source) is not.

Writes <out-dir>/anchor_analysis.json (standard result fields), anchor_summary.md and bands/<capture>__<key>.csv.
Default out-dir: <first RUN_DIR>/analysis. Profile caches go next to the MJPEG (raw tree, outside the repo).
Real data must not be scored until selftest_anchor.py passes (test plan V3).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import platform
import socket
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import frameio  # noqa: E402
import rigio  # noqa: E402
import score  # noqa: E402
import solve  # noqa: E402

AREA_ROOT = HERE.parents[1]  # research/usb_cameras


def platform_name() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux" if sys.platform.startswith("linux") else sys.platform)


def raw_root() -> Path:
    env = os.environ.get("SKELLYCAM_RAW_ROOT")
    if env:
        return Path(env)
    return Path.home() / "Documents" / "skellycam-raw" if sys.platform == "win32" else Path.home() / "skellycam-raw"


def raw_mirror(path: Path) -> Path | None:
    try:
        return raw_root() / Path(path).resolve().relative_to(AREA_ROOT)
    except ValueError:
        return None


def discover(run_dir: Path, raw_dir: Path | None) -> list[dict]:
    caps = sorted([p for p in run_dir.iterdir() if p.is_dir() and p.name.startswith("capture")])
    out = []
    for cap in caps:
        for fp in sorted(cap.glob("*.frames.jsonl")):
            key = fp.name[: -len(".frames.jsonl")]
            cands = [cap / f"{key}.mjpeg"]
            if raw_dir:
                cands.append(raw_dir / cap.name / f"{key}.mjpeg")
            m = raw_mirror(cap)
            if m:
                cands.append(m / f"{key}.mjpeg")
            mj = next((c for c in cands if c.exists()), None)
            out.append({"run_dir": run_dir, "capture": cap.name, "key": key, "frames_path": fp, "mjpeg": mj,
                        "mjpeg_candidates": [str(c) for c in cands],
                        "session": frameio.load_json(cap / f"{key}.session.json") or {},
                        "controls": frameio.load_jsonl(cap / f"{key}.controls.jsonl")})
    return out


def mode_key(session: dict) -> str:
    r = session.get("requested") or {}
    return f"{r.get('w', '?')}x{r.get('h', '?')}@{r.get('fps', '?')}"


def exposure_table(controls: list[dict], arrival: np.ndarray, E: np.ndarray) -> dict:
    sets = [c for c in controls if c.get("event") == "exposure_set"]
    if not sets:
        return {"sets": 0}
    t_sets = [int(c["qpc_before_ns"]) for c in sets]
    order = np.argsort(arrival)
    dwells = []
    prev_med = None
    for i, c in enumerate(sets):
        t0 = t_sets[i]
        t1 = t_sets[i + 1] if i + 1 < len(sets) else np.inf
        idx = order[(arrival[order] >= t0) & (arrival[order] < t1)]
        e = E[idx]
        fin = np.isfinite(e)
        med = float(np.median(e[fin][10:])) if fin.sum() > 15 else None
        lat = None
        if med is not None and prev_med is not None and abs(med - prev_med) > 0.03 * prev_med:
            for j, v in enumerate(e):
                if np.isfinite(v) and abs(v - med) < 0.03 * med:
                    lat = j
                    break
        dwells.append({"i": c.get("i"), "requested_log2": c.get("value_log2"), "readback_log2": c.get("readback_value"),
                       "requested_ms": 1e3 * 2.0 ** float(c.get("value_log2")), "measured_E_ms": med / 1e6 if med else None,
                       "frames": int(len(idx)), "effect_latency_frames": lat})
        if med is not None:
            prev_med = med
    by_val: dict = {}
    for d in dwells:
        if d["measured_E_ms"] is not None:
            by_val.setdefault(d["requested_log2"], []).append(d["measured_E_ms"])
    summary = [{"requested_log2": v, "requested_ms": 1e3 * 2.0 ** float(v), "measured_E_ms_median": float(np.median(m)),
                "measured_over_requested": float(np.median(m) / (1e3 * 2.0 ** float(v))), "dwells": len(m)}
               for v, m in sorted(by_val.items())]
    lats = [d["effect_latency_frames"] for d in dwells if d["effect_latency_frames"] is not None]
    return {"sets": len(sets), "by_value": summary,
            "effect_latency_frames_median": float(np.median(lats)) if lats else None,
            "effect_latency_note": "frames counted from the first frame ARRIVING after the set call (QPC before Set) to the first frame whose measured E is within 3 % of the new dwell's median",
            "dwells": dwells}


def analyze_camera_run(cr: dict, rig: dict, opts, L_known: float | None) -> tuple[dict, dict]:
    frames = frameio.load_frames(cr["frames_path"])
    res = {"capture": cr["capture"], "camera_key": cr["key"], "friendly_name": cr["session"].get("friendly_name"),
           "mode": mode_key(cr["session"]), "backend": frames[0].get("backend") if frames else None,
           "frames": len(frames), "mjpeg": str(cr["mjpeg"]) if cr["mjpeg"] else None}
    if cr["mjpeg"] is None:
        res["error"] = "MJPEG not found; looked in " + "; ".join(cr["mjpeg_candidates"])
        return res, {}
    if rig["clock"] is None:
        res["error"] = "no usable ping clock fit (needed to pick strobes)"
        return res, {}
    seq = np.array([f.get("seq", i) for i, f in enumerate(frames)], dtype=np.int64)
    arrival = np.array([f["host_arrival_ns"] for f in frames], dtype=np.int64)
    a_esp = rig["clock"].host_to_esp(arrival)
    fps = (cr["session"].get("requested") or {}).get("fps")
    T_nom = 1e9 / float(fps) if fps else float(np.median(np.diff(arrival)))
    cache = None if opts.no_cache else Path(cr["mjpeg"]).parent / "_profile_cache"
    prof, pinfo = frameio.decode_profiles(Path(cr["mjpeg"]), frames, opts.channel, opts.cols, opts.gamma, cache)
    b = solve.analyze_bands(prof.astype(np.float64), seq, a_esp, rig["strobes"], gap_ns=rig["gap_ns"], T_nom=T_nom,
                            L_known=L_known, thr_frac=opts.thr_frac, sigma=opts.sigma)
    res["decode"] = pinfo
    if "error" in b:
        res["error"] = b["error"]
        res["bands"] = {k: v for k, v in b.items() if k != "error"}
        return res, {}
    T_cam = b["frame_period_ns"]
    s0, E = b["s0"], b["E"]
    H = b["rows"]
    res["bands"] = {k: b[k] for k in ("n_frames", "rows", "amplitude_ref", "threshold", "frames_with_segments", "assignment",
                                      "L_source", "L_double", "L_sweep", "frames_full_band", "frames_s0_only",
                                      "frame_conflicts", "blanking", "echo")}
    res["L_us"] = b["L_ns"] / 1e3
    res["T_ro_ms"] = H * b["L_ns"] / 1e6
    res["rows_H"] = H
    res["frame_period_ms_esp"] = T_cam / 1e6
    fin = np.isfinite(E)
    res["exposure_measured_ms"] = {"min": float(np.nanmin(E) / 1e6), "max": float(np.nanmax(E) / 1e6)} if fin.any() else None
    res["exposure_schedule"] = exposure_table(cr["controls"], arrival, E)
    # ---- sources
    srcs = frameio.timestamp_sources(frames)
    for name in [n for n, s in srcs.items() if s["kind"] == "camera"]:
        s = srcs[name]
        ok = s["valid"]
        mapped, info = score.lower_envelope_map(s["values"][ok], arrival[ok])
        v = np.zeros(len(frames), dtype=np.int64)
        v[ok] = np.round(mapped).astype(np.int64)
        srcs[f"{name}->qpc_env"] = {"kind": "host", "values": v, "valid": ok.copy(), "derived": info}
    sres = {}
    for name, s in srcs.items():
        m = s["valid"] & np.isfinite(s0) & np.isfinite(E)
        f = score.fit_anchor(s["values"][m], s0[m], E[m], frame_period_ns=T_cam)
        entry = {"kind": s["kind"], **({"derived": s["derived"]} if "derived" in s else {})}
        if "error" not in f and s["kind"] == "host":
            entry["K"] = score.k_values(s["values"][m], s0[m], E[m], f["alpha"], rig["clock"], f["_keep"], T_cam)
        entry.update({k: v for k, v in f.items() if not k.startswith("_")})
        sres[name] = entry
    res["sources"] = sres
    internals = {"seq": seq, "s0": s0, "E": E, "band_table": b["band_table"], "slots": b["slots"]}
    return res, internals


def add_k_rel(cam_results: list[dict]) -> dict | None:
    """K_rel within one capture: relative to the first camera's host_arrival_ns (else its first host source)."""
    ok = [c for c in cam_results if "sources" in c]
    if not ok:
        return None
    ref_cam = ok[0]
    ref_name = "host_arrival_ns" if "K" in ref_cam["sources"].get("host_arrival_ns", {}) else \
        next((n for n, s in ref_cam["sources"].items() if "K" in s), None)
    if ref_name is None:
        return None
    ref = ref_cam["sources"][ref_name]["K"]["first_byte"]
    for c in ok:
        for n, s in c["sources"].items():
            if "K" in s:
                k = s["K"]["first_byte"]
                s["K_rel"] = {"reference": f"{ref_cam['camera_key']}:{ref_name}",
                              "K_alpha1_rel_us": k["K_alpha1_us"] - ref["K_alpha1_us"],
                              "K_alphafit_rel_us": k["K_alphafit_us"] - ref["K_alphafit_us"]}
    return {"camera_key": ref_cam["camera_key"], "source": ref_name}


def write_band_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def cross_run_summary(all_cams: list[dict]) -> list[dict]:
    groups: dict = {}
    for c in all_cams:
        for n, s in c.get("sources", {}).items():
            if "alpha" not in s:
                continue
            groups.setdefault((c["camera_key"], c["mode"], c.get("backend"), n), []).append((c, s))
    out = []
    for (key, mode, backend, n), lst in sorted(groups.items()):
        al = [s["alpha"] for _, s in lst]
        hw = [s["alpha_ci95_halfwidth"] for _, s in lst]
        row = {"camera_key": key, "mode": mode, "api": backend, "source": n, "runs": len(lst),
               "alpha_per_run": al, "alpha_ci95_halfwidth_max": max(hw),
               "jitter_std_us_median": float(np.median([s["residual_std_us"] for _, s in lst])),
               "jitter_mad_us_median": float(np.median([s["residual_mad_us"] for _, s in lst])),
               "L_us": float(np.median([c["L_us"] for c, _ in lst])), "T_ro_ms": float(np.median([c["T_ro_ms"] for c, _ in lst]))}
        ks = [s["K"]["first_byte"]["K_alpha1_us"] for _, s in lst if "K" in s]
        if ks:
            row["K_alpha1_abs_first_byte_us_per_run"] = ks
            row["K_alpha1_range_us"] = float(max(ks) - min(ks))
            row["K_alpha1_std_us"] = float(np.std(ks, ddof=1)) if len(ks) > 1 else None
        row["pass_alpha_ci_within_0p05"] = bool(max(hw) <= 0.05)
        if len(ks) > 1:
            row["pass_K_repeatable_0p2ms"] = bool(row["K_alpha1_range_us"] <= 200)
        out.append(row)
    return out


def fmt(v, nd=3):
    return "n/a" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def summary_md(result: dict) -> str:
    m = result["measurements"]
    L = ["# Timestamp anchor analysis", "", f"Runs: {', '.join(result['parameters']['run_dirs'])}", "",
         "Conventions: row 0 = top = read first; s0 = row-0 exposure start; E measured from band height; "
         "alpha 0 = exposure start, 0.5 = mid-exposure, 1 = row-0 readout start. K_abs is **estimated** "
         "(ping-path asymmetry, both offsets shown); K_rel (same run) is offset-free.", ""]
    for run in m["runs"]:
        L += [f"## {run['run_dir']}", "",
              f"Strobe: {json.dumps(run['strobe'])}; clock fit: drift {fmt(run['clock'].get('drift_ppm_esp_vs_host'))} ppm, "
              f"residual {fmt(run['clock'].get('residual_std_us'))} us, asymmetry bound {fmt(run['clock'].get('asymmetry_bound_us'))} us "
              f"({run['asymmetry_source']}).", ""]
        for c in run["cameras"]:
            L.append(f"### {c['capture']} / {c['camera_key']} ({c.get('friendly_name')}, {c['mode']}, {c.get('backend')})")
            if "error" in c:
                L += ["", f"ERROR: {c['error']}", ""]
                continue
            b = c["bands"]
            L += ["", f"L = {c['L_us']:.4f} us ({b['L_source']}), T_ro = {c['T_ro_ms']:.3f} ms, H = {c['rows_H']}; "
                      f"full bands {b['frames_full_band']}/{b['n_frames']} frames; assignment rejected {b['assignment']['rejected_units']}, "
                      f"continuity fixed/dropped {b['assignment']['continuity_fixed']}/{b['assignment']['continuity_dropped']}; "
                      f"echo ratio {fmt(b['echo'].get('echo_ratio_median'))} (n={b['echo'].get('n_frames')}); "
                      "blanking gap by E: " + ("; ".join(
                          f"E {g['E_ms']:.2f} ms: observed {fmt((g['observed_gap'] or {}).get('width_ms'))} ms at "
                          f"{fmt((g['observed_gap'] or {}).get('start_ms'))} (expected {g['expected_gap_ms']:.2f} ms at {g['expected_gap_start_ms']:.2f})"
                          for g in b['blanking'].get('by_exposure', [])) or b['blanking'].get('note', 'n/a')) + ".", ""]
            ex = c.get("exposure_schedule", {})
            if ex.get("by_value"):
                L.append("Exposure: " + "; ".join(f"{d['requested_log2']} -> {d['measured_E_ms_median']:.3f} ms "
                                                  f"(x{d['measured_over_requested']:.3f} of {d['requested_ms']:.3f})" for d in ex["by_value"]))
                L.append("")
            L += ["| source | kind | n | alpha | 95% CI | jitter std us | MAD us | K_rel us (a=1) | K_abs us first/last (a=1, est.) |",
                  "|---|---|---|---|---|---|---|---|---|"]
            for n, s in c["sources"].items():
                if "alpha" not in s:
                    L.append(f"| {n} | {s['kind']} | {s.get('n')} | {s.get('error')} | | | | | |")
                    continue
                kr = s.get("K_rel", {}).get("K_alpha1_rel_us")
                ka = s.get("K", {})
                kab = f"{ka['first_byte']['K_alpha1_us']:.1f} / {ka['last_byte']['K_alpha1_us']:.1f}" if ka else "n/a (camera clock)"
                L.append(f"| {n} | {s['kind']} | {s['n']} | {s['alpha']:.4f} | {s['alpha_ci95'][0]:.4f} .. {s['alpha_ci95'][1]:.4f} | "
                         f"{s['residual_std_us']:.1f} | {s['residual_mad_us']:.1f} | {fmt(kr, 1)} | {kab} |")
            L.append("")
    if m.get("cross_run"):
        L += ["## Across stream restarts", "", "| camera | mode | source | runs | alpha per run | max CI half | K_a1 range us | pass alpha | pass K |",
              "|---|---|---|---|---|---|---|---|---|"]
        for r in m["cross_run"]:
            L.append(f"| {r['camera_key']} | {r['mode']} | {r['source']} | {r['runs']} | {', '.join(f'{a:.3f}' for a in r['alpha_per_run'])} | "
                     f"{r['alpha_ci95_halfwidth_max']:.3f} | {fmt(r.get('K_alpha1_range_us'), 1)} | {r['pass_alpha_ci_within_0p05']} | {r.get('pass_K_repeatable_0p2ms', 'n/a')} |")
        L.append("")
    return "\n".join(L) + "\n"


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return None
    if isinstance(o, (np.floating,)):
        o = float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def analyze_runs(run_dirs: list[Path], opts) -> tuple[dict, dict]:
    utc = dt.datetime.now(dt.timezone.utc)
    raw_dirs = list(opts.raw_dir or [])
    Lgiven: dict[str, float] = {}
    for item in opts.line_time_ns or []:
        k, v = item.split("=", 1)
        Lgiven[k] = float(v)

    def given_L(key: str):
        for k, v in Lgiven.items():
            if k == "all" or k.lower() in key.lower():
                return v
        return None

    rigs = []
    for i, rd in enumerate(run_dirs):
        rig = rigio.load_rig_run(rd)
        rigs.append((rd, rig, discover(rd, raw_dirs[i] if i < len(raw_dirs) else None)))
    # double-strobe runs first -> L per (key, mode)
    Lmap: dict[tuple[str, str], list[float]] = {}
    runs_out, internals, all_cams = [], {}, []
    ordered = sorted(rigs, key=lambda t: 0 if t[1]["gap_ns"] > 0 else 1)
    for rd, rig, crs in ordered:
        cams_by_capture: dict[str, list[dict]] = {}
        for cr in crs:
            mk = mode_key(cr["session"])
            Lk = given_L(cr["key"])
            if Lk is None and rig["gap_ns"] == 0 and Lmap.get((cr["key"], mk)):
                Lk = float(np.median(Lmap[(cr["key"], mk)]))
            res, intr = analyze_camera_run(cr, rig, opts, Lk)
            if rig["gap_ns"] > 0 and res.get("bands", {}).get("L_double", {}).get("n", 0) >= 5:
                Lmap.setdefault((cr["key"], mk), []).append(res["bands"]["L_double"]["L_ns"])
            cams_by_capture.setdefault(cr["capture"], []).append(res)
            internals[(str(rd), cr["capture"], cr["key"])] = intr
            if intr.get("band_table"):
                write_band_csv(opts.out_dir / "bands" / f"{rd.name}__{cr['capture']}__{cr['key']}.csv", intr["band_table"])
        refs = {cap: add_k_rel(lst) for cap, lst in cams_by_capture.items()}
        cams = [c for lst in cams_by_capture.values() for c in lst]
        all_cams += [c for c in cams if rig["gap_ns"] == 0]
        fit = rig["clock_fit"].get("fit", {})
        runs_out.append({"run_dir": str(rd), "strobe": rig["strobe_cfg"], "double_strobe": rig["gap_ns"] > 0,
                         "strobes_logged": int(len(rig["strobes"]["t_c"])), "strobe_k_lost": rig["strobe_k_lost"],
                         "rig_errors": rig["events"].errors[:20], "boots": rig["events"].boots,
                         "clock": {k: fit.get(k) for k in ("drift_ppm_esp_vs_host", "residual_std_us", "asymmetry_bound_us",
                                                           "offset_ns_at_ref", "offset_ns_at_ref_if_reply_seen_after_last_byte",
                                                           "min_delay_us", "n_windows", "error")},
                         "asymmetry_source": rig["asymmetry_source"], "ping_rx_src_counts": rig["rx_src_counts"],
                         "k_rel_reference": refs, "cameras": cams})
    result = {
        "test": "rig_anchor_analysis", "platform": platform_name(), "hostname": socket.gethostname(),
        "utc_started": utc.isoformat(), "command": " ".join(sys.argv),
        "environment": {"os": platform.platform(), "python": sys.version, "numpy": np.__version__},
        "cameras": sorted({(c["camera_key"], c.get("friendly_name") or "") for r in runs_out for c in r["cameras"]}),
        "parameters": {"run_dirs": [str(r) for r in run_dirs], "gamma": opts.gamma, "channel": opts.channel,
                       "cols_frac": list(opts.cols), "threshold_frac": opts.thr_frac, "smoothing_sigma_rows": opts.sigma,
                       "line_time_given_ns": Lgiven,
                       "line_time_from_double_strobe_runs_ns": {f"{k[0]}|{k[1]}": v for k, v in Lmap.items()}},
        "measurements": {"runs": runs_out, "cross_run": cross_run_summary(all_cams)},
        "notes": ["Synthetic-tested only until the first hardware run; see timing/rig/README.md.",
                  "K_abs = estimated: ping-path asymmetry (|bias| <= asymmetry_bound_us) and the first/last-byte question are unresolved until test plan V7.",
                  "alpha needs exposure to vary inside one capture (exposure schedule)."],
    }
    result["cameras"] = [{"camera_key": k, "friendly_name": n} for k, n in result["cameras"]]
    return clean(result), internals


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dirs", nargs="+", type=Path)
    ap.add_argument("--raw-dir", type=Path, action="append", help="raw run folder for the RUN_DIR at the same position")
    ap.add_argument("--line-time-ns", action="append", metavar="KEY=NS")
    ap.add_argument("--gamma", type=float, default=2.2, help="tone-curve exponent used to linearize (1 = none)")
    ap.add_argument("--channel", choices=("luma", "green"), default="luma")
    ap.add_argument("--cols", type=lambda s: tuple(float(x) for x in s.split(",")), default=(0.2, 0.8),
                    help="column ROI as fractions of the width, e.g. 0.2,0.8")
    ap.add_argument("--thr-frac", type=float, default=0.35, help="segment threshold, fraction of the band amplitude")
    ap.add_argument("--sigma", type=float, default=1.0, help="profile smoothing sigma in rows")
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args(argv)
    if a.out_dir is None:
        a.out_dir = a.run_dirs[0] / "analysis"
    return a


def main(argv=None) -> int:
    a = parse_args(argv)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    result, _ = analyze_runs(a.run_dirs, a)
    (a.out_dir / "anchor_analysis.json").write_text(json.dumps(result, indent=1))
    md = summary_md(result)
    (a.out_dir / "anchor_summary.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"wrote {a.out_dir / 'anchor_analysis.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
