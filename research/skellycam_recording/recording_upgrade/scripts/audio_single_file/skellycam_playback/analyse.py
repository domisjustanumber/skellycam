# /// script
# requires-python = "==3.12.*"
# dependencies = ["numpy==2.2.6"]
# ///
"""Analyses the raw harness output of run.py (raw/<id>.json) against truth.json.

Per play segment, every camera-0 flash draw (barcode-checked) is paired with the nearest tap click (within 250 ms):
  av_ms    = A - V: click output time (getOutputTimestamp mapping of the click's context frame) minus the rAF timestamp
             of the tick that drew the flash frame. < 0 = audio heard before the flash frame is drawn.
  clock_ms = A - P*: P* = when the player's master clock crossed the flash frame's sidecar time (linear between ticks).
             Removes the 0-1 vsync quantisation of the draw: it is the error of the audio content/schedule/clock itself.
Content check: click positions in the PCM each engine would schedule vs the true file sample (device sample + offset).
Writes results/audio_single_file/skellycam_playback/<set>.json and <set>.csv.

Usage: uv run --script analyse.py <set prefix, e.g. short> [more prefixes]
"""
import csv
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = (r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496"
           r"\scratchpad\audio_single_file\skellycam_playback")
RESULTS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "results", "audio_single_file", "skellycam_playback"))
SR = 48000
_truth = {}


def truth(take):
    if take not in _truth:
        t = json.load(open(os.path.join(SCRATCH, take, "truth.json")))
        t["flash_by_index"] = {f["cam0_index"]: f for f in t["flashes"]}
        _truth[take] = t
    return _truth[take]


def audio_map(path, mode):
    hdr, fit, first = {}, None, None
    for line in open(path):
        if line.startswith("# fit "):
            fit = {k: float(v) for k, v in (kv.split("=") for kv in line[6:].split())}
        elif line.startswith("# ") and "=" in line:
            k, v = line[2:].strip().split("=", 1)
            hdr[k] = v
        elif first is None and line[:1].isdigit():
            p = line.split(",")
            first = (int(p[1]), int(p[4]))
    off = int(hdr.get("file_sample_offset", 0))
    if mode == "fit":
        return (lambda n: (fit["t0_ns"] + (n - off - fit["n0"]) * 1e9 / fit["rate_hz"]) / 1e9), off
    return (lambda n: (first[1] + (n - off - first[0]) * 1e9 / SR) / 1e9), off


def stats(x):
    x = np.asarray(x, float)
    if not len(x):
        return None
    return dict(n=int(len(x)), mean=round(float(x.mean()), 2), sd=round(float(x.std()), 2), min=round(float(x.min()), 2),
                max=round(float(x.max()), 2), absmax=round(float(np.abs(x).max()), 2))


def analyse(path):
    j = json.load(open(path))
    cfg, page = j["cfg"], j["page"]
    r = cfg["run"]
    out = dict(id=r["id"], electron=j["electron"], chrome=j["chrome"], take=r["take"], fmt=r["fmt"], engine=r["engine"],
               clock=r["clock"], map=r["map"])
    if "error" in page or page.get("loadError"):
        out["error"] = page.get("error") or page.get("loadError")
        return out
    tr = truth(r["take"])
    tmap, off = audio_map(os.path.join(cfg["take_dir"], cfg["audio"] + ".csv"), r["map"])
    out.update(ctx=page["ctx"], calib=page["calib"], load=page["load"], cams=page["cams"], engine_stats=page["engine"],
               requests=j["requests"])
    # content check
    dev = np.array([f["device_sample"] for f in tr["flashes"]]) + off
    cerr = []
    for c in page.get("content") or []:
        for pk in c["peaks"]:
            cerr.append(int(pk - dev[np.argmin(np.abs(dev - pk))]))
    out["content_err_samples"] = sorted(set(cerr)) if cerr else None
    out["content_peaks"] = len(cerr)
    segs, all_av, all_clk, raf = [], [], [], []
    for s in page["segments"]:
        if s["op"] == "scrub":
            segs.append(dict(op="scrub", lat_ms=stats(s["lat"])))
            continue
        ticks = np.array(s["ticks"], float)
        P, th = ticks[:, 0], np.array([tmap(n) for n in ticks[:, 1]])
        raf += np.diff(P).tolist()
        clicks = np.array(s["clicks"], float).reshape(-1, 3)
        flashes = [d for d in s["draws"] if d[2]]
        av, clk, unpaired, binned = [], [], 0, {}
        for i, stamp, _, V in flashes:
            f = tr["flash_by_index"].get(i)
            if f is None or stamp != i or not len(clicks):
                unpaired += 1
                continue
            k = int(np.argmin(np.abs(clicks[:, 1] - V)))
            A = clicks[k, 1]
            if abs(A - V) > 250:
                unpaired += 1
                continue
            av.append(A - V)
            T = f["host_s"]
            jx = int(np.searchsorted(th, T))
            if 0 < jx < len(th) and th[jx] > th[jx - 1]:
                Pstar = P[jx - 1] + (T - th[jx - 1]) / (th[jx] - th[jx - 1]) * (P[jx] - P[jx - 1])
                clk.append(A - Pstar)
                binned.setdefault(int((V - P[0]) // 60000), []).append(A - Pstar)
        all_av += av
        all_clk += clk
        segs.append(dict(op="play", t=s["t"], prep_ms=s["prepMs"], flashes=len(flashes), clicks=len(clicks), unpaired=unpaired,
                         av_ms=stats(av), clock_ms=stats(clk),
                         audio_start_ms=round(s["whenPerf"] - s["playAt"], 1) if s.get("whenPerf") else None,
                         first_draw_ms=round(next((d[3] for d in s["draws"]), s["playAt"]) - s["playAt"], 1) if s["draws"] else None,
                         output_latency_ms=sorted({round(1000 * t[3], 1) for t in s["ts"]}),
                         clock_ms_by_minute=[round(float(np.mean(binned[k])), 2) for k in sorted(binned)] if len(binned) > 2 else None))
    out["segments"] = segs
    out["av_ms"], out["clock_ms"] = stats(all_av), stats(all_clk)
    play_segs = [g for g in segs if g["op"] == "play" and g["av_ms"]]
    out["av_seg_means"] = [g["av_ms"]["mean"] for g in play_segs]
    out["clock_seg_means"] = [g["clock_ms"]["mean"] for g in play_segs if g["clock_ms"]]
    out["raf_ms_median"] = round(float(np.median(raf)), 2) if raf else None
    # metrics: memory after load, peak, CPU cores while playing
    m = j["metrics"]
    loaded = [x for x in m if x[1] == "loaded"]
    out["ws_mb_after_load"] = round(loaded[-1][2], 0) if loaded else None
    out["tab_ws_mb_after_load"] = round(loaded[-1][4].get("Tab", {}).get("ws", 0), 0) if loaded else None
    out["ws_mb_peak"] = round(max(x[2] for x in m), 0) if m else None
    cpu = [(b[3] - a[3]) / ((b[0] - a[0]) / 1000) for a, b in zip(m, m[1:]) if a[1] == b[1] == "play" and b[0] > a[0]]
    out["cpu_cores_play"] = round(float(np.mean(cpu)), 3) if cpu else None
    return out


def main():
    rows = []
    for pre in sys.argv[1:]:
        for p in sorted(glob.glob(os.path.join(SCRATCH, "raw", pre + "_*.json"))):
            if p.endswith(".cfg.json"):
                continue
            rows.append(analyse(p))
    os.makedirs(RESULTS, exist_ok=True)
    name = "_".join(sys.argv[1:])
    json.dump(rows, open(os.path.join(RESULTS, name + ".json"), "w"), indent=1)
    cols = ["id", "electron", "fmt", "engine", "clock", "map", "content_err_samples", "av_mean", "av_sd", "av_min", "av_max",
            "clock_mean", "clock_absmax", "av_seg_means", "load_ms", "ws_mb_after_load", "ws_mb_peak", "cpu_cores_play",
            "raf_ms_median", "error"]
    with open(os.path.join(RESULTS, name + ".csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            a, c = r.get("av_ms") or {}, r.get("clock_ms") or {}
            w.writerow([r["id"], r["electron"], r["fmt"], r["engine"], r["clock"], r["map"], r.get("content_err_samples"),
                        a.get("mean"), a.get("sd"), a.get("min"), a.get("max"), c.get("mean"), c.get("absmax"),
                        r.get("av_seg_means"), (r.get("load") or {}).get("ms"), r.get("ws_mb_after_load"), r.get("ws_mb_peak"),
                        r.get("cpu_cores_play"), r.get("raf_ms_median"), r.get("error")])
    for r in rows:
        a, c = r.get("av_ms") or {}, r.get("clock_ms") or {}
        print(f'{r["id"]:28s} content={r.get("content_err_samples")} av mean {a.get("mean")} sd {a.get("sd")} [{a.get("min")},{a.get("max")}] '
              f'clock mean {c.get("mean")} absmax {c.get("absmax")} segs {r.get("av_seg_means")} load {(r.get("load") or {}).get("ms")} '
              f'ws {r.get("ws_mb_after_load")}/{r.get("ws_mb_peak")} cpu {r.get("cpu_cores_play")} {r.get("error") or ""}')


if __name__ == "__main__":
    main()
