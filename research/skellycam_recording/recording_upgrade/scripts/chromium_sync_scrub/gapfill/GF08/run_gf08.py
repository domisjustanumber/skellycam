# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""GF08 runner + offline check (FUNCTIONAL; no timing recorded).

1. Runs the copied harness (gapfill/GF08/harness, test=tssync) in Electron 35.7.5 and 45.2.3 at N=4 cameras.
   Raw page output -> temp step3/GF08/raw_e<ver>.json (then copied into the result JSON as compact rows).
2. Independently recomputes, in Python, the expected frame per camera per tick for rule PREV and rule NEAREST
   from the sidecars (media dir cam<i>.ts.json), and compares with what the page chose and what it read back.
3. Offline only (no browser): the same rules applied to the container pts (MKV 1/1000, MP4 1/90000) instead of the
   sidecar, and a frame-index sync rule (every camera shows cam0's index), against the timestamp truth.
Writes results/chromium_sync_scrub/gapfill/GF08_ts_sync.json and GF08_ts_sync_tables.md.

Run (repo root): uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/gapfill/GF08/run_gf08.py [--analyze-only]
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path("C:/Users/Dom/GitHub/freemocap/skellycam")
RU = REPO / "research/skellycam_recording/recording_upgrade"
HARNESS = Path(__file__).resolve().parent / "harness"
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/gapfill/GF08")
TEMP = Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/GF08")
RESULTS = RU / "results/chromium_sync_scrub/gapfill"
ELECTRON = {
    "35": REPO / "skellycam-ui/node_modules/electron/dist/electron.exe",
    "45": Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe"),
}


def run(ver: str) -> Path:
    out = TEMP / f"raw_e{ver}.json"
    env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}
    env["CSS_MEDIA_ROOT"] = str(MEDIA)
    env["CSS_USER_DATA"] = str(TEMP / f"electron_userdata_{ver}")
    cmd = [str(ELECTRON[ver]), str(HARNESS), "--test=tssync", f"--out={out}", "--timeout=2400", "--noocclusion=1"]
    if out.exists():
        out.unlink()
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=2600)
    if not out.exists():
        raise RuntimeError(f"no output for e{ver}\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    return out


# ---- expected (independent of the page code) ---------------------------------------------------------
def exp_prev(ts: list[int], T: int, P: int) -> tuple[int, str]:
    i = bisect.bisect_right(ts, T) - 1  # largest index with ts <= T
    if i < 0:
        return -1, "before_start"
    age = T - ts[i]
    if i == len(ts) - 1 and age > P:
        return -1, "after_end"
    return i, ("hold_stale" if age > P else "ok")


def exp_nearest(ts: list[int], T: int, P: int) -> tuple[int, str]:
    j = bisect.bisect_left(ts, T)  # first index with ts >= T
    cands = [x for x in (j - 1, j) if 0 <= x < len(ts)]
    k = min(cands, key=lambda x: (abs(ts[x] - T), x))  # tie -> earlier
    d2 = 2 * abs(ts[k] - T)
    if d2 > P and T < ts[0]:
        return -1, "before_start"
    if d2 > P and T > ts[-1]:
        return -1, "after_end"
    return k, ("hold_stale" if d2 > P else "ok")


RULES = {"PREV": exp_prev, "NEAREST": exp_nearest}


def analyze(raw_files: dict[str, Path]) -> None:
    man = json.loads((MEDIA / "manifest.json").read_text())
    P = man["P_ns"]
    cams = sorted(man["cams"])
    side = {c: json.loads((MEDIA / f"{c}.ts.json").read_text()) for c in cams}
    ticks = man["ticks"]
    exp = {}  # (rule, cam_i, T) -> (k, status)
    for ci, c in enumerate(cams):
        ts = side[c]["ts_ns"]
        assert ts == man["cams"][c]["ts_ns"]
        for t in ticks:
            for r, fn in RULES.items():
                exp[(r, ci, t["t_ns"])] = fn(ts, t["t_ns"], P)
    why = {t["t_ns"]: t["why"] for t in ticks}

    res = {"electron": {}, "mismatch_table": [], "status_counts": {}, "harness_helpers": {}, "offline": {}}
    for ver, f in raw_files.items():
        d = json.loads(f.read_text())
        r = d["result"]
        if "error" in r:
            raise RuntimeError(f"e{ver}: {r}")
        res["electron"][ver] = {"versions": d["versions"], "gpu_device": (d.get("gpu_info") or {}).get("gpuDevice"),
                                "isSecureContext": r["isSecureContext"], "tick_count": r["tick_count"], "per_path": r["per_path"],
                                "row_fields": r["row_fields"], "rows": r["rows"]}
        agg = defaultdict(lambda: Counter())
        examples = defaultdict(list)
        for row in r["rows"]:
            T, path, rule, ci, k, st, rid, rcam, dok, fl, nr = row
            ek, est = exp[(rule, ci, T)]
            key = (path, rule, ci)
            a = agg[key]
            a["ticks"] += 1
            sel_ok = (k == ek and st == est)
            if ek < 0:
                id_ok = (k < 0 and rid is None)
            else:
                id_ok = (rid == ek) and (path == "jpeg" or rcam == ci) and bool(dok)
            a["selection_mismatch"] += (not sel_ok)
            a["identity_mismatch"] += (not id_ok)
            a["decode_fail"] += (ek >= 0 and not dok)
            a[f"expected_{est}"] += 1
            if (not sel_ok or not id_ok) and len(examples[key]) < 10:
                examples[key].append({"t_ns": T, "why": why[T], "expected": [ek, est], "page": [k, st], "read": [rid, rcam, dok]})
        for (path, rule, ci), a in sorted(agg.items()):
            res["mismatch_table"].append({"electron": ver, "path": path, "rule": rule, "cam": cams[ci], "ticks": a["ticks"],
                                          "identity_mismatches": a["identity_mismatch"], "selection_mismatches": a["selection_mismatch"],
                                          "decode_failures": a["decode_fail"],
                                          "expected_status": {k[9:]: v for k, v in a.items() if k.startswith("expected_")},
                                          "examples": examples[(path, rule, ci)]})
        # existing harness helpers (seconds) vs the integer-ns rules (path-independent; use one path's rows)
        hh = defaultdict(Counter)
        hx = {}
        for row in r["rows"]:
            T, path, rule, ci, k, st, rid, rcam, dok, fl, nr = row
            if path != r["paths"][0]:
                continue
            ek, est = exp[(rule, ci, T)]
            h = hh[(rule, cams[ci])]
            h["ticks"] += 1
            helper = fl if rule == "PREV" else nr
            if ek >= 0:
                h["defined_ticks"] += 1
                h["helper_equals_rule_where_defined"] += (helper == ek)
                if helper != ek:
                    hx.setdefault(f"{rule}|{cams[ci]}", []).append({"t_ns": T, "why": why[T], "rule_k": ek, "helper_k": helper,
                                                                    "ts_rule_k": side[cams[ci]]["ts_ns"][ek], "ts_helper_k": side[cams[ci]]["ts_ns"][helper]})
            else:
                h[f"rule_none_{est}"] += 1
                h[f"helper_returned_frame_when_rule_none_{est}"] += 1  # helpers have no 'none' result
                h[f"helper_value_{est}_{helper}"] += 1
        res["harness_helpers"][ver] = {f"{rl}|{c}": dict(v) for (rl, c), v in sorted(hh.items())}
        res["harness_helpers"][ver]["mismatch_examples_where_defined"] = hx

    # status counts per rule/cam (from the expected answers)
    for (rule, ci, T), (k, st) in exp.items():
        res["status_counts"].setdefault(rule, {}).setdefault(cams[ci], Counter())[st] += 1
    res["status_counts"] = {r: {c: dict(v) for c, v in d.items()} for r, d in res["status_counts"].items()}

    # offline 1: rules on container pts instead of the sidecar
    cont = {}
    for kind in ("jpeg", "h264"):
        for ci, c in enumerate(cams):
            cts = man["cams"][c][kind]["container_pts_ns"]
            ts = side[c]["ts_ns"]
            for rule, fn in RULES.items():
                dif = [(t, fn(cts, t["t_ns"], P), exp[(rule, ci, t["t_ns"])]) for t in ticks]
                dif = [x for x in dif if x[1] != x[2]]
                whyh = Counter(w.split(":")[0] for t, _, _ in dif for w in t["why"])
                offh = Counter((str(a[0] - b[0]) if a[0] >= 0 and b[0] >= 0 else f"{a[1]}_vs_{b[1]}") for _, a, b in dif)
                # distance of each differing tick from the nearest sidecar timestamp or midpoint (rule boundary)
                # rule boundaries: timestamps, midpoints, ts + P (PREV hold limit), ts +- P/2 (NEAREST limit)
                bounds = sorted(set(ts) | {(x + y) // 2 for x, y in zip(ts, ts[1:])} | {x + P for x in ts}
                                | {x + P // 2 for x in ts} | {x - P // 2 for x in ts})
                def bd(T):
                    j = bisect.bisect_left(bounds, T)
                    return min(abs(bounds[i] - T) for i in (j - 1, j) if 0 <= i < len(bounds))
                cont[f"{kind}|{rule}|{c}"] = {"ticks": len(ticks), "differs_from_sidecar_rule": len(dif),
                                              "max_abs_pts_minus_ts_ns": max(abs(a - b) for a, b in zip(cts, ts)),
                                              "differing_tick_why_hist": dict(whyh), "k_container_minus_k_sidecar_hist": dict(offh),
                                              "max_distance_of_differing_tick_from_a_rule_boundary_ns": max((bd(t["t_ns"]) for t, _, _ in dif), default=None)}
    res["offline"]["container_pts_instead_of_sidecar"] = cont

    # offline 2: frame-index sync (every camera shows the index k0 that cam0 shows under PREV) vs timestamp PREV
    idx = {}
    ts0 = side[cams[0]]["ts_ns"]
    for ci, c in enumerate(cams[1:], start=1):
        ts = side[c]["ts_ns"]
        n_def = n_same = far_idx = far_ts = far_ts_stale = 0
        for t in ticks:
            T = t["t_ns"]
            k0, _ = exp_prev(ts0, T, P)
            kc, stc = exp_prev(ts, T, P)
            if k0 < 0 or k0 >= len(ts) or kc < 0:
                continue
            n_def += 1
            n_same += (k0 == kc)
            far_idx += (abs(ts[k0] - ts0[k0]) > P)  # index rule: shown frames captured > 1 nominal period apart
            far_ts += (abs(ts[kc] - ts0[k0]) > P)   # timestamp rule: same check
            far_ts_stale += (abs(ts[kc] - ts0[k0]) > P and stc == "hold_stale")
        idx[c] = {"ticks_where_both_rules_show_a_frame": n_def, "index_rule_equals_timestamp_PREV": n_same,
                  "index_rule_capture_time_vs_cam0_more_than_P": far_idx, "timestamp_PREV_capture_time_vs_cam0_more_than_P": far_ts,
                  "of_which_cam_status_hold_stale": far_ts_stale}
    res["offline"]["frame_index_sync_vs_timestamp"] = idx

    # content-timestamp distance of the chosen frame from the tick (data property of the rules, not a runtime timing)
    dist = {}
    for rule in RULES:
        for st_name in ("ok", "hold_stale"):
            vals = [abs(side[cams[ci]]["ts_ns"][k] - T) for (r, ci, T), (k, st) in exp.items() if r == rule and st == st_name]
            dist[f"{rule}|{st_name}"] = {"n": len(vals), "max_abs_ts_minus_tick_ns": max(vals) if vals else None}
    res["offline"]["chosen_frame_distance"] = dist

    # inter-frame intervals per camera (sidecar data): intervals over P that are NOT synthetic drops come from capture timing
    iv = {}
    for c in cams:
        ts, orig = side[c]["ts_ns"], side[c]["orig_index"]
        d_all = [b - a for a, b in zip(ts, ts[1:])]
        d_nodrop = [b - a for a, b, o1, o2 in zip(ts, ts[1:], orig, orig[1:]) if o2 - o1 == 1]
        srt = sorted(d_nodrop)
        iv[c] = {"intervals": len(d_all), "min_ns": min(d_all), "median_ns_consecutive": srt[len(srt) // 2], "max_ns_consecutive": max(d_nodrop),
                 "max_ns_all": max(d_all), "consecutive_intervals_over_P": sum(1 for x in d_nodrop if x > P),
                 "consecutive_intervals_over_1.5P": sum(1 for x in d_nodrop if x > 1.5 * P)}
    res["offline"]["intervals"] = iv
    gen = json.loads((RESULTS / "GF08_generation.json").read_text())
    out = {"what": "GF08: multi-camera sync by capture timestamp in a master-clock player (G9), exactness only; no timing fields",
           "date": "2026-11-10", "machine": "Gerald (Windows 11, RTX 3070, UHD 770)",
           "conventions": {
               "P_ns": P, "P_source": "nominal_fps 30 in corpus/index.json for both sets; P = 33,333,333 ns",
               "PREV": "k = largest i with ts[i] <= T. T < ts[0] -> none (before_start). k = last and T - ts[k] > P -> none (after_end). Else frame k; hold_stale if T - ts[k] > P.",
               "NEAREST": "k = argmin |ts[i] - T|, ties -> smaller i. If 2|ts[k]-T| > P: none (before_start / after_end) when T < ts[0] / T > ts[last], else hold_stale (in a gap). Else frame k.",
               "identity": {"jpeg": "SHA-256 of the Range-fetched bytes, looked up in that camera's own table; ImageDecoder decode complete + 1280x720",
                            "jpegbc": "16-bit pattern cam*4096 + k read from the ImageDecoder output",
                            "h264": "16-bit pattern cam*4096 + k read from the WebCodecs VideoFrame (flush after each chunk)"},
               "mismatch": "identity mismatch = expected none but page decoded something, or read id != expected k, or (barcode paths) read cam != cam, or decode failed"},
           "streams": {c: {k: v for k, v in gen["cameras"][c].items() if k != "files"} for c in cams},
           "offset_ns": gen["offset_ns"], "generator": gen["generator"],
           "tick_count": len(ticks), "tick_why_hist": gen["ticks"]["why_hist"],
           **res}
    (RESULTS / "GF08_ts_sync.json").write_text(json.dumps(out, separators=(",", ":")))
    # compact tables for the md
    lines = ["| Electron | path | rule | cam | identity mismatches / ticks | selection mismatches | decode failures |", "|---|---|---|---|---|---|---|"]
    for m in res["mismatch_table"]:
        lines.append(f"| E{m['electron']} | {m['path']} | {m['rule']} | {m['cam']} | {m['identity_mismatches']} / {m['ticks']} | {m['selection_mismatches']} | {m['decode_failures']} |")
    (TEMP / "GF08_ts_sync_tables.md").write_text("\n".join(lines) + "\n\n" + json.dumps({k: res[k] for k in ("status_counts", "harness_helpers", "offline")}, indent=1))
    print("\n".join(lines))
    print(json.dumps({k: res[k] for k in ("status_counts", "harness_helpers", "offline")}, indent=1))
    for ver in res["electron"]:
        print(ver, res["electron"][ver]["versions"], res["electron"][ver]["per_path"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyze-only", action="store_true")
    ap.add_argument("--electron", default="35,45")
    a = ap.parse_args()
    TEMP.mkdir(parents=True, exist_ok=True)
    vers = a.electron.split(",")
    files = {}
    for v in vers:
        files[v] = TEMP / f"raw_e{v}.json" if a.analyze_only else run(v)
        print("done", v, files[v], flush=True)
    analyze(files)


if __name__ == "__main__":
    main()
