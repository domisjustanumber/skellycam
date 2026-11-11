# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "opencv-python-headless==4.10.0.84"]
# ///
"""Synthetic end-to-end self-test of the timestamp-anchor pipeline (test plan V3; the gate before real data).

Run (from the repo root):
  uv run --script research/usb_cameras/timing/rig/selftest_anchor.py [--quick] [--keep] [--work-dir DIR] [--out FILE]

Generates, with known truth, everything a real run produces, then runs the REAL analysis (analyze_anchor.py) on it:
  * rig_events.log / rig_pings.csv / rig_session.json: strobe EV S events on an ESP32 clock that runs 20 ppm fast
    against the host clock, plus PING/PONG samples with random path delays (the clock fit is the real one from
    sync_rig/host/esp32_clock_sync.py);
  * MJPEG frames rendered from a rolling-shutter model: row r integrates [s0 + r*L, s0 + r*L + E]; strobe overlap
    integrated exactly; vertical vignetting; ambient; one-tap temporal-noise-reduction echo (camera A, 8 %);
    vertical sharpening (camera A); tone curve v = 255*lin^(1/2.2); per-pixel noise; colour (green LED) frame encoded
    as JPEG quality 80 (4:2:0); fixed-readout sensor (x = s0 + E advances by T, longer E starts earlier);
  * exposure schedule switching every 5 s, applied 2 frames after the logged set call, with APPLIED != REQUESTED
    (camera A integrates 3 % short and both cameras quantize E to whole lines);
  * camera B: different size, line time, phase, clock drift and two dropped frames;
  * frames.jsonl sources with known anchors:
        syn_alpha1_ns   alpha = 1,   K_alpha1   = +2.000 ms (A) / +3.100 ms (B), 0.3 ms jitter
        syn_alpha05_ns  alpha = 0.5, K_alphafit = +5.000 ms (A) / +4.200 ms (B), 0.3 ms jitter
        os_timestamp_ns MF-sample-time-like: alpha = 1 then quantized to a 15.625 ms grid
        host_arrival_ns readout end + transfer + jitter, quantized to the 15.625 ms grid (used to pick strobes)
        uvc_pts         camera clock 30 MHz +37 ppm (A) / -52 ppm (B), alpha = 1, 50 us jitter
        uvc_scr_stc     same clock, end of readout + 1.2 ms, alpha = 1, 150 us jitter
  * runs: one double-strobe L run (gap 10 ms) and one single-strobe anchor run with two stream (re)starts.

Pass criteria (asserted): per full-band frame |s0 err| and |E err| <= 20 us (max over frames), no misassigned
frame; L within 0.1 %; alpha within +-0.03 and K within 50 us for the clean sources (K_rel between cameras; K_abs
within asymmetry bound + 50 us); the grid source has jitter > 3 ms, an alpha CI >= 5x wider than the clean source's
and containing the truth; echo detected on A (ratio 0.08 +- 0.03) and not on B; blanking gap where expected.
The synthetic frames go to a temp folder (deleted unless --keep); the result JSON goes to
results/<platform>/<hostname>/rig_anchor_selftest/selftest_<utc>.json unless --out is given.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_anchor  # noqa: E402

AREA_ROOT = HERE.parents[1]
GRID_NS = 15_625_000
BAUD = 921600


class World:
    """True time = ESP32 time. host(esp) maps to QPC; ESP runs 20 ppm fast against the host."""
    ESP0 = 50_000_000_000          # esp ns at the reference
    QPC0 = 123_456_789_000_000     # host ns at the reference
    PPM = 20.0

    def host(self, esp):
        return self.QPC0 + (np.asarray(esp, dtype=np.float64) - self.ESP0) / (1 + self.PPM * 1e-6)

    def esp(self, host):
        return self.ESP0 + (np.asarray(host, dtype=np.float64) - self.QPC0) * (1 + self.PPM * 1e-6)


def write_rig(run: Path, w: World, rng, epochs: list[tuple[float, float]], period_us: int, gap_us: int,
              width_us: int = 50, phase_us: int = 1000) -> dict:
    """epochs: (START, STOP) ESP times; k restarts at 0 at every START, as in the firmware."""
    run.mkdir(parents=True, exist_ok=True)
    lines = []
    rises_all = []
    for t_start, t_end in epochs:
        rises = []
        j = 0
        while True:
            t = t_start + phase_us * 1000 + j * period_us * 1000
            if t > t_end:
                break
            rises.append(t)
            if gap_us:
                rises.append(t + gap_us * 1000)
            j += 1
        for k, r in enumerate(rises):
            rr = int(round(r + rng.normal(0, 5)))
            ff = int(round(r + width_us * 1000 + rng.normal(0, 5)))
            h = int(w.host(ff + 0.8e6 + rng.exponential(0.2e6)))
            lines.append((h, f"{h}\t{h + 400_000}\tEV S {k} {rr} {ff}"))
        rises_all += rises
    rises = np.array(rises_all)
    t_start, t_end = epochs[0][0], epochs[-1][1]
    for s in np.arange(t_start, t_end, 1e9):
        h = int(w.host(s + 0.5e6))
        lines.append((h, f"{h}\t{h + 400_000}\tEV K {int(s / 12.5)} {int(s)} 3 400"))
    hs = int(w.host(t_start - 0.2e9))
    lines.append((hs, f"{hs}\t{hs + 300_000}\tOK START step_us=100 bar=DARK strobe=1 fsin=0"))
    lines.append((hs - 1, f"{hs - 1}\t{hs + 300_000}\tEV X 1 2 3 (unknown type, must be ignored)"))
    lines.sort()
    (run / "rig_events.log").write_text("\n".join(l for _, l in lines) + "\n")
    # pings: symmetric base delays + exponential jitter (native USB CDC-like)
    rows = []
    h = float(w.host(t_start - 0.5e9))
    h_end = float(w.host(t_end))
    seq = 0
    while h < h_end:
        h += 50e6 * (0.5 + rng.random())
        fwd = 150_000 + rng.exponential(60_000)
        back = 150_000 + rng.exponential(60_000)
        turn = 40_000 + rng.random() * 20_000
        rx = w.esp(h + fwd)
        tx = rx + turn
        t4 = w.host(tx) + back
        seq += 1
        rows.append({"seq": seq, "host_tx_ns": int(h), "host_write_done_ns": int(h + 15_000), "host_rx_ns": int(t4),
                     "host_rx_last_ns": int(t4 + 20_000), "esp_rx_us": int(rx // 1000), "esp_tx_us": int(tx // 1000),
                     "rx_src": "B", "extra": "sof=123 456" if seq % 2 else ""})
    with (run / "rig_pings.csv").open("w", newline="") as f:
        import csv  # noqa: PLC0415
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    ses = {"test": "rig_session", "platform": "synthetic", "hostname": "synthetic", "utc_started": "synthetic",
           "command": "selftest_anchor.py", "environment": {}, "cameras": [],
           "device": {"port": "SYN", "vid": "303A", "pid": "1001", "baud": BAUD},
           "parameters": {"strobe": {"period_us": period_us, "width_us": width_us, "phase_us": phase_us, "gap_us": gap_us}},
           "measurements": {"reply_bytes": 40.0}}
    (run / "rig_session.json").write_text(json.dumps(ses, indent=1))
    return {"rises": rises, "width_ns": width_us * 1000}


CAMS = {
    "A": dict(key="synA_vid_046d_pid_085c_mi_00", name="synthetic C922-like", W=1280, H=720, L=42_800.0,
              ppm_esp=25.0, x0_off=7.3e6, echo=0.08, sharpen=0.3, noise=1.5, amp=0.30, short=0.97,
              sched=[-9, -7, -6], K1=2.000e6, K05=5.000e6, pts_ppm=37.0, drops=()),
    "B": dict(key="synB_vid_4c4a_pid_4a55_mi_00", name="synthetic generic-like", W=640, H=480, L=64_100.0,
              ppm_esp=-15.0, x0_off=21.1e6, echo=0.0, sharpen=0.0, noise=2.0, amp=0.25, short=1.0,
              sched=[-8, -7, -6], K1=3.100e6, K05=4.200e6, pts_ppm=-52.0, drops=(400, 401)),
}


def applied_E(v: int, c: dict) -> float:
    return round(c["short"] * (2.0 ** v) * 1e9 / c["L"]) * c["L"]


def render_capture(cap_dir: Path, raw_dir: Path, w: World, rng, c: dict, rig: dict, t_cap0: float, seconds: float,
                   fixed_log2: int | None, noise_bank: np.ndarray) -> dict:
    """Render one camera stream; returns truth per seq."""
    T = 1e9 / 30.0 * (1 + c["ppm_esp"] * 1e-6)
    H, W, L = c["H"], c["W"], c["L"]
    nslots = int(seconds * 1e9 / T)
    x = t_cap0 + c["x0_off"] + rng.random() * 1e6 + T * np.arange(nslots)  # row-0 readout start per slot
    lat = H * L + 3e6 + np.abs(rng.normal(0, 0.7e6, nslots))
    gphase = rng.random() * GRID_NS
    arr = np.ceil((w.host(x + lat) - gphase) / GRID_NS) * GRID_NS + gphase + rng.random(nslots) * 0.2e6
    # exposure per slot
    if fixed_log2 is not None:
        E = np.full(nslots, applied_E(fixed_log2, c))
        sets = []
    else:
        E = np.empty(nslots)
        sets = []
        t_first = arr[0]
        i = 0
        while True:
            t_set = t_first + 1.0e9 + i * 5e9
            if t_set > arr[-1]:
                break
            sets.append((i, c["sched"][i % len(c["sched"])], t_set))
            i += 1
        E[:] = applied_E(-5, c)  # whatever the camera ran at before the first set
        for i, v, t_set in sets:
            n_eff = int(np.searchsorted(x, w.esp(t_set) + 2 * T))  # 2-frame latency
            E[n_eff:] = applied_E(v, c)
    s0 = x - E
    rows = np.arange(H, dtype=np.float64)
    vign = 1.0 - 0.25 * ((rows - H / 2) / (H / 2)) ** 2
    rises = rig["rises"]
    wns = rig["width_ns"]
    delivered = [n for n in range(nslots) if n not in c["drops"]]
    cap_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    f_mj = (raw_dir / f"{c['key']}.mjpeg").open("wb")
    f_fr = (cap_dir / f"{c['key']}.frames.jsonl").open("w")
    off = 0
    prev_band = np.zeros(H)
    fcam = 30e6 * (1 + c["pts_ppm"] * 1e-6)
    pts0 = int(rng.integers(0, 2 ** 32))
    truth = {}
    lin_prev_band = np.zeros(H)
    for seq, n in enumerate(delivered):
        a = s0[n] + rows * L
        band = np.zeros(H)
        lo = np.searchsorted(rises, s0[n] - wns - 1e6)
        hi = np.searchsorted(rises, s0[n] + H * L + E[n] + 1e6)
        for r in rises[lo:hi]:
            ov = np.minimum(a + E[n], r + wns) - np.maximum(a, r)
            band += np.clip(ov, 0, None) / wns
        band *= c["amp"] * vign
        bg = 0.010 + 0.002 * E[n] / 16e6
        lin = bg + band + c["echo"] * lin_prev_band
        lin_prev_band = band
        if c["sharpen"]:
            blur = np.convolve(np.pad(lin, 1, mode="edge"), np.ones(3) / 3, mode="valid")
            lin = lin + c["sharpen"] * (lin - blur)
        v = 255.0 * np.clip(lin, 0, 1) ** (1 / 2.2)
        img_g = v[:, None] + noise_bank[rng.integers(0, len(noise_bank))][:H, :W] * c["noise"]
        img = np.empty((H, W, 3), np.uint8)
        img[:, :, 1] = np.clip(img_g, 0, 255)
        img[:, :, 2] = np.clip(img_g * 0.35, 0, 255)
        img[:, :, 0] = np.clip(img_g * 0.30, 0, 255)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b = buf.tobytes()
        f_mj.write(b)
        xr = x[n]
        sources = {
            "host_arrival_ns": int(arr[n]),
            "os_timestamp_ns": int(np.floor((w.host(xr + 30e6) - 0.37 * GRID_NS) / GRID_NS) * GRID_NS + 0.37 * GRID_NS),
            "syn_alpha1_ns": int(w.host(xr) + c["K1"] + rng.normal(0, 0.3e6)),
            "syn_alpha05_ns": int(w.host(s0[n] + 0.5 * E[n]) + c["K05"] + rng.normal(0, 0.3e6)),
        }
        pts = (pts0 + int(round((xr + 1.5e6 - t_cap0) * fcam / 1e9 + rng.normal(0, 50e3) * fcam / 1e9))) % 2 ** 32
        stc = (pts0 + int(round((xr + H * L + 1.2e6 - t_cap0) * fcam / 1e9 + rng.normal(0, 150e3) * fcam / 1e9))) % 2 ** 32
        rec = {"camera_key": c["key"], "backend": "synthetic", "seq": seq, **sources,
               "readsample_call_ns": int(arr[n] - 30e6), "payload_bytes": len(b), "jpeg_soi": True, "jpeg_eoi": True,
               "mjpeg_offset": off, "os_timestamp_source": "synthetic 15.625 ms grid",
               "meta_items": [{"id": 2, "size": 40, "_top": {"uvc_pts": pts, "uvc_scr_stc": stc, "uvc_scr_sof": seq % 2048,
                                                               "uvc_eof_pts": pts, "uvc_eof_scr_stc": stc, "uvc_eof_scr_sof": seq % 2048}}]}
        f_fr.write(json.dumps(rec) + "\n")
        off += len(b)
        truth[seq] = (s0[n], E[n])
    f_mj.close()
    f_fr.close()
    ses = {"camera_key": c["key"], "friendly_name": c["name"], "symbolic_link": "synthetic",
           "requested": {"w": W, "h": H, "fps": 30}, "frames": len(delivered), "errors": 0,
           "controls": {"exposure_log2": {"requested": str(fixed_log2) if fixed_log2 is not None else "auto"}}}
    if sets:
        ses["exposure_schedule"] = {"values_log2": c["sched"], "dwell_s": 5.0, "first_s": 1.0, "sets": len(sets)}
        with (cap_dir / f"{c['key']}.controls.jsonl").open("w") as f:
            f.write(json.dumps({"camera_key": c["key"], "event": "schedule_start", "values_log2": c["sched"]}) + "\n")
            for i, v, t_set in sets:
                f.write(json.dumps({"camera_key": c["key"], "event": "exposure_set", "i": i, "value_log2": v,
                                    "qpc_before_ns": int(t_set), "qpc_after_ns": int(t_set + 2e6), "hr": "0x00000000",
                                    "readback_value": v, "readback_flags": 2}) + "\n")
    (cap_dir / f"{c['key']}.session.json").write_text(json.dumps(ses))
    return {"truth": truth, "T": T, "L": L, "H": H,
            "applied_E_ms": {v: applied_E(v, c) / 1e6 for v in c["sched"]}}


def check(name: str, ok: bool, detail: str, checks: list) -> None:
    checks.append({"check": name, "pass": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="shorter captures (one anchor capture of 45 s)")
    ap.add_argument("--keep", action="store_true", help="keep the synthetic run folders")
    ap.add_argument("--work-dir", type=Path, help="where to write synthetic runs (default: a new temp folder)")
    ap.add_argument("--out", type=Path, help="result JSON path")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    t_wall = time.perf_counter()
    utc = dt.datetime.now(dt.timezone.utc)
    rng = np.random.default_rng(a.seed)
    w = World()
    work = a.work_dir or Path(tempfile.mkdtemp(prefix="rig_anchor_selftest_"))
    work.mkdir(parents=True, exist_ok=True)
    noise_bank = rng.normal(0, 1, (6, 720, 1280)).astype(np.float32)
    cap_s = 45.0 if a.quick else 60.0
    n_caps = 1 if a.quick else 2
    truth: dict = {}
    run_dirs = {}

    def simple_run(tag: str, t_cap0: float, seconds: float, period_us: int, gap_us: int, fixed: int | None, n: int = 1):
        """n captures (stream restarts); the strobe is STARTed 2 s after each capture starts (deferred START) and
        STOPped at its end, as run_anchor_test.py does."""
        rd = work / f"rig_anchor_{tag}"
        caps = [t_cap0 + r * (seconds + 4) * 1e9 for r in range(n)]
        rig = write_rig(rd, w, rng, [(t + 2e9, t + seconds * 1e9) for t in caps], period_us, gap_us)
        for r, t in enumerate(caps):
            cap = f"capture_r{r + 1:02d}"
            for c in CAMS.values():
                truth[(tag, cap, c["key"])] = render_capture(rd / cap, rd / cap, w, rng, c, rig, t, seconds, fixed, noise_bank)
        run_dirs[tag] = rd
        return rd

    t0 = w.ESP0 + 10e9
    # L run: double strobe (gap 10 ms), fixed short exposure (-9)
    simple_run("L", t0, 12.0, 33366, 10000, -9)
    # echo run: strobe every 1.5 frames, so frame k+1 leaves frame k's band rows free
    simple_run("E", t0 + 20e9, 8.0, round(1.5 * 1e6 / 30) + 33, 0, -7)
    # blanking run: fast sweep (T + 333 us) at the shortest exposure, maps the no-band phases in a few seconds
    simple_run("B", t0 + 35e9, 10.0, 33333 + 333, 0, -9)
    # anchor run: single strobe T + 33 us, exposure schedule, n_caps stream (re)starts
    simple_run("A", t0 + 55e9, cap_s, 33366, 0, None, n_caps)
    lrun, arun = run_dirs["L"], run_dirs["A"]
    t_gen = time.perf_counter() - t_wall
    print(f"generated synthetic runs in {t_gen:.1f} s under {work}", flush=True)
    # ---- real analysis
    order = [run_dirs[k] for k in ("A", "E", "B", "L")]  # L deliberately last: the analysis must order it first itself
    opts = analyze_anchor.parse_args([str(p) for p in order] + ["--out-dir", str(work / "analysis"), "--no-cache"])
    opts.out_dir.mkdir(parents=True, exist_ok=True)
    result, internals = analyze_anchor.analyze_runs(order, opts)
    (opts.out_dir / "anchor_analysis.json").write_text(json.dumps(result, indent=1))
    (opts.out_dir / "anchor_summary.md").write_text(analyze_anchor.summary_md(result), encoding="utf-8")
    checks: list = []
    runs = {Path(r["run_dir"]).name: r for r in result["measurements"]["runs"]}
    # ---- per-frame s0 / E (every run, every capture, every camera)
    frame_stats = {}
    for (rk, cap, key), tr in truth.items():
        intr = internals.get((str(run_dirs[rk]), cap, key), {})
        if not intr:
            check(f"{rk}/{cap}/{key[:4]} analysed", False, "no internals (analysis error)", checks)
            continue
        seq, s0, E = intr["seq"], intr["s0"], intr["E"]
        es0, eE = [], []
        mis = 0
        for i, q in enumerate(seq):
            if not np.isfinite(s0[i]) or int(q) not in tr["truth"]:
                continue
            ts0, tE = tr["truth"][int(q)]
            d = s0[i] - ts0
            if abs(d) > 1e6:
                mis += 1
                continue
            es0.append(d)
            eE.append(E[i] - tE)
        es0, eE = np.abs(np.array(es0)), np.abs(np.array(eE))
        nfr = len(tr["truth"])
        if not len(es0):
            check(f"{rk}/{cap}/{key[:4]} s0,E per frame <= 20 us", False, f"no frame scored, misassigned {mis}", checks)
            continue
        st = {"frames": nfr, "full_band_frames_scored": int(len(es0)), "misassigned": mis,
              "s0_err_us_p50": float(np.median(es0) / 1e3), "s0_err_us_p99": float(np.percentile(es0, 99) / 1e3),
              "s0_err_us_max": float(es0.max() / 1e3), "E_err_us_p50": float(np.median(eE) / 1e3),
              "E_err_us_p99": float(np.percentile(eE, 99) / 1e3), "E_err_us_max": float(eE.max() / 1e3)}
        frame_stats[f"{rk}/{cap}/{key}"] = st
        check(f"{rk}/{cap}/{key[:4]} s0,E per frame <= 20 us",
              st["s0_err_us_max"] <= 20 and st["E_err_us_max"] <= 20 and mis == 0 and len(es0) > 0.25 * nfr,
              f"n={len(es0)}/{nfr} s0 max {st['s0_err_us_max']:.2f} us (p99 {st['s0_err_us_p99']:.2f}), "
              f"E max {st['E_err_us_max']:.2f} us (p99 {st['E_err_us_p99']:.2f}), misassigned {mis}", checks)

    def cams_of(tag):
        return runs[run_dirs[tag].name]["cameras"]

    def cid_of(c):
        return "A" if c["camera_key"].startswith("synA") else "B"

    # ---- strobe identity: epoch check (deferred START) in every single-strobe run
    for tag in ("E", "B", "A"):
        for c in cams_of(tag):
            ep = c.get("bands", {}).get("assignment", {}).get("epoch_check", {})
            check(f"epoch check {tag}/{c['capture']} {cid_of(c)}", bool(ep.get("available") and ep.get("consistent")),
                  json.dumps(ep.get("epochs")), checks)
    # ---- L
    for c in cams_of("L"):
        cdef = CAMS[cid_of(c)]
        Ld = c.get("bands", {}).get("L_double", {})
        err = (Ld.get("L_ns", np.nan) - cdef["L"]) / cdef["L"] * 100
        check(f"L double strobe {cid_of(c)}", abs(err) <= 0.1,
              f"L {Ld.get('L_ns', float('nan')):.3f} ns vs {cdef['L']} ({err:+.4f} %), CV {Ld.get('L_cv_pct')} %, n={Ld.get('n')}", checks)
    sweep_err = {}
    for tag in ("E", "B", "A"):
        for c in cams_of(tag):
            cdef = CAMS[cid_of(c)]
            sw = c.get("bands", {}).get("L_sweep", {})
            if sw.get("L_ns"):
                sweep_err[f"{tag}/{c['capture']}/{cid_of(c)}"] = {"err_pct": (sw["L_ns"] - cdef["L"]) / cdef["L"] * 100,
                                                                  "se_pct": 100 * sw["L_se_ns"] / cdef["L"], "wraps": sw.get("wraps_seen")}
            check(f"{tag}/{c['capture']} {cid_of(c)} uses L from the L run", c.get("bands", {}).get("L_source") == "given",
                  f"L_source={c.get('bands', {}).get('L_source')}", checks)
    for k, v in sweep_err.items():
        if k.startswith("B/"):
            check(f"sweep L cross-check {k} (fast sweep) within 0.3 %", abs(v["err_pct"]) <= 0.3, json.dumps(v), checks)
    print("sweep L cross-check (B asserted, others informational):", json.dumps(sweep_err), flush=True)
    # ---- echo (dedicated run, strobe every 1.5 frames)
    for c in cams_of("E"):
        echo = c["bands"]["echo"]
        if cid_of(c) == "A":
            check("echo detected on A (truth 0.08)", echo.get("n_frames", 0) >= 20 and abs(echo["echo_ratio_median"] - 0.08) <= 0.03,
                  f"ratio {echo.get('echo_ratio_median')} n={echo.get('n_frames')}", checks)
        else:
            check("no echo on B (truth 0)", echo.get("n_frames", 0) >= 20 and abs(echo["echo_ratio_median"]) < 0.02,
                  f"ratio {echo.get('echo_ratio_median')} n={echo.get('n_frames')}", checks)
    # ---- blanking (dedicated fast-sweep run at the shortest exposure)
    for c in cams_of("B"):
        bl = c["bands"]["blanking"].get("by_exposure", [])
        short = min(bl, key=lambda g: g["E_ms"]) if bl else None
        og = (short or {}).get("observed_gap") or {}
        check(f"blanking gap {cid_of(c)}", bool(short) and bool(og) and abs(og["start_ms"] - short["expected_gap_start_ms"]) <= 0.3
              and abs(og["width_ms"] - short["expected_gap_ms"]) <= 0.4,
              f"observed {og} expected start {short and round(short['expected_gap_start_ms'], 3)} ms width {short and round(short['expected_gap_ms'], 3)} ms", checks)
    # ---- alpha / K / grid / exposure (anchor run)
    clean = {"syn_alpha1_ns": 1.0, "syn_alpha05_ns": 0.5, "uvc_pts": 1.0, "uvc_scr_stc": 1.0}
    kA = {}
    bound = runs[arun.name]["clock"]["asymmetry_bound_us"]
    for c in cams_of("A"):
        cid = cid_of(c)
        cdef = CAMS[cid]
        S = c.get("sources", {})
        for sname, at in clean.items():
            s = S.get(sname, {})
            check(f"alpha {c['capture']} {cid} {sname}", "alpha" in s and abs(s["alpha"] - at) <= 0.03,
                  f"alpha {s.get('alpha', float('nan')):.4f} CI {s.get('alpha_ci95')} (truth {at}), jitter std {s.get('residual_std_us', float('nan')):.1f} us", checks)
        if "syn_alpha1_ns" not in S or "K" not in S["syn_alpha1_ns"]:
            check(f"K {c['capture']} {cid}", False, "no K computed", checks)
            continue
        s1, s05 = S["syn_alpha1_ns"], S["syn_alpha05_ns"]
        k1 = s1["K"]["first_byte"]["K_alpha1_us"]
        k05 = s05["K"]["first_byte"]["K_alphafit_us"]
        check(f"K_abs {c['capture']} {cid} syn_alpha1 (est.)", abs(k1 - cdef["K1"] / 1e3) <= bound + 50,
              f"{k1:.1f} us vs {cdef['K1'] / 1e3:.1f} (bound {bound} us); last-byte variant {s1['K']['last_byte']['K_alpha1_us']:.1f}", checks)
        check(f"K_abs {c['capture']} {cid} syn_alpha05 alpha-fit (est.)", abs(k05 - cdef["K05"] / 1e3) <= bound + 50,
              f"{k05:.1f} us vs {cdef['K05'] / 1e3:.1f}", checks)
        kA[(c["capture"], cid)] = (k1, k05)
        g = S["os_timestamp_ns"]
        hw_clean = s1["alpha_ci95_halfwidth"]
        check(f"grid source {c['capture']} {cid} honest", g["residual_std_us"] > 3000 and g["alpha_ci95_halfwidth"] >= 5 * hw_clean
              and g["alpha_ci95"][0] <= 1.0 <= g["alpha_ci95"][1],
              f"jitter {g['residual_std_us']:.0f} us, alpha {g['alpha']:.3f} CI {[round(v, 3) for v in g['alpha_ci95']]} "
              f"(half {g['alpha_ci95_halfwidth']:.3f} vs clean {hw_clean:.4f})", checks)
        ex = c.get("exposure_schedule", {}).get("by_value", [])
        tr = truth[("A", c["capture"], c["camera_key"])]["applied_E_ms"]
        worst = max((abs(d["measured_E_ms_median"] - tr[d["requested_log2"]]) * 1e3 for d in ex), default=np.inf)
        check(f"exposure per dwell {c['capture']} {cid} = applied (not requested)", worst <= 20,
              "; ".join(f"{d['requested_log2']}: {d['measured_E_ms_median']:.4f} ms (applied {tr[d['requested_log2']]:.4f})" for d in ex), checks)
    for cap in sorted({k[0] for k in kA}):
        if (cap, "A") in kA and (cap, "B") in kA:
            rel = kA[(cap, "B")][0] - kA[(cap, "A")][0]
            check(f"K_rel {cap} B-A syn_alpha1", abs(rel - 1100.0) <= 50, f"{rel:.1f} us vs 1100.0", checks)
            rel05 = kA[(cap, "B")][1] - kA[(cap, "A")][1]
            check(f"K_rel {cap} B-A syn_alpha05", abs(rel05 - (-800.0)) <= 50, f"{rel05:.1f} us vs -800.0", checks)
    if n_caps > 1:
        for cid in ("A", "B"):
            ks = [v[0] for (cap, c2), v in kA.items() if c2 == cid]
            if len(ks) > 1:
                check(f"K repeatable across restarts {cid} (truth identical)", max(ks) - min(ks) <= 50,
                      f"K_alpha1 per capture {[round(k, 1) for k in ks]} us", checks)
    ok_all = all(c["pass"] for c in checks)
    out = {
        "test": "rig_anchor_selftest", "platform": analyze_anchor.platform_name(), "hostname": socket.gethostname(),
        "utc_started": utc.isoformat(), "command": " ".join(sys.argv),
        "environment": {"os": platform.platform(), "python": sys.version, "numpy": np.__version__, "opencv": cv2.__version__},
        "cameras": [], "parameters": {"seed": a.seed, "quick": a.quick, "capture_s": cap_s, "captures": n_caps,
                                      "cameras": {k: {kk: vv for kk, vv in v.items() if kk != "drops"} | {"drops": list(v["drops"])} for k, v in CAMS.items()}},
        "measurements": {"verdict": "pass" if ok_all else "FAIL", "checks": checks, "frame_errors": frame_stats,
                         "sweep_L_cross_check": sweep_err, "generation_s": t_gen, "total_s": time.perf_counter() - t_wall,
                         "analysis_summary_md": analyze_anchor.summary_md(result)},
        "notes": ["Synthetic only: no camera, no ESP32. Passing this is the V3 gate, not evidence about real cameras.",
                  "Truth anchors are chosen by the generator; see the docstring for the model."],
    }
    outp = a.out or (AREA_ROOT / "results" / analyze_anchor.platform_name() / socket.gethostname() / "rig_anchor_selftest"
                     / f"selftest_{utc.strftime('%Y%m%dT%H%M%SZ')}.json")
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(analyze_anchor.clean(out), indent=1))
    print(f"\nSELF-TEST {'PASS' if ok_all else 'FAIL'}: {sum(c['pass'] for c in checks)}/{len(checks)} checks; wrote {outp}")
    if not a.keep and a.work_dir is None:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"synthetic runs kept in {work}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
