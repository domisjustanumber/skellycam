"""W-NODRIFT: with the controls locked the way the product locks them, nothing drifts (TP1 "Auto stays off").

Plan research/CAPTURE_AND_RECORDING_PLAN.md section 3.3 TP1, row "Auto stays off (no drift)": AE, auto gain and AF
are switched off and verified off by reading back the auto flags; during a 10-minute stream, and across stop/start,
the exposure, gain and focus readbacks and the image must stay constant. This test replaces W-AUTO's product role
(W-AUTO's auto-mode on/off recovery is no longer a product test). The lock follows
usb_cameras/docs/exposure_gain_tradeoff.md section 5.2 step 1 and the re-apply rule of section 5.3.

Per camera, one camera at a time, in the suite's mode scope (MJPEG, exactly 720 lines, >= 30 fps; the first
in-scope 30 fps mode, 1280x720@30 where offered, which is what skellycam uses):

1. ``as_found``: one ``wincam controls --read-only`` (MF): every control's value, flags and range. Kept for the
   final restore.
2. ``lock`` (one ``wincam controls --set ... --set-flags manual``, camera not streaming): AE off at the current
   exposure, gain manual at its current value (auto gain off where the camera has it), AF off at the current
   focus, AWB off holding the current white-balance value, AE priority 0 and power-line frequency 60 Hz (value 2)
   where present and in range, and zoom, pan, tilt, brightness, contrast, saturation, sharpness, gamma and
   backlight compensation re-set to their start values. Requested vs read back is recorded per control.
3. ``re-apply``: every stream (the soak and each restart) re-applies EVERY locked value REAPPLY_MS (1.2 s) after
   the first frame on the streaming MF source (``wincam capture --schedule``), because the C930e resets exposure
   and gain at stream start (sets >= 1 s after the first frame stick). The set's ``before_value`` / ``before_flags``
   is the value the stream start left, so the result names the controls that changed at stream start
   (``needed_reapply``) generically, for every camera; re-applying an unchanged value is a no-op.
4. ``soak``: SOAK_S (600 s) of continuous streaming. Every SAMPLE_EVERY_S (30 s, first sample 3 s after the first
   frame) exposure, gain, focus and white balance are read back with their auto flags, and the saved frames of the
   next METRIC_WIN_MS give the image: median luma of the central 80 % ROI, mean R/G/B over the same ROI (R/B
   ratio) and the normalised Laplacian sharpness of the centre 50 % (the W-CTRL-EFFECT / W-AUTO metrics). Delivered
   fps and drops come from every frame's arrival time.
5. ``restart1..N`` (3): stop/start: a new capture process each, re-applied as in step 3, read back and measured
   every 5 s for 20 s.
6. Rating (verdict key ``G-CTRL-NODRIFT|<camera key>|mf``), thresholds provisional (constants below):
   - yes: every auto flag stays off, every exposure / gain / focus / WB readback stays within one step of the
     locked value (``w_ctrl_effect.step_tol``: one range step, >= 1, or 1 % of the span), the re-apply reads back
     in every stream, the ROI luma stays within +/-LUMA_TOL and the R/B ratio within +/-RB_TOL of the first soak
     sample, across the soak and every restart; the lock read back for every control and every sample was read;
   - no: an auto flag came back on, a readback left its tolerance, the re-apply of exposure / gain / focus / WB did
     not read back, a drift control could not be switched to manual, or the luma / R/B left the band;
   - partial: nothing failed, but something was not shown: a lock or re-apply of AE priority, power-line frequency
     or a start-value control did not read back, the image check was inconclusive (dark or bright scene), or some
     samples / restarts are missing;
   - untested: device fault or dead camera (``ctx.camera_gated`` / ``ctx.camera_dead`` / a fault during the test;
     the camera's remaining work is skipped, never retried, re-probed or re-opened), no in-scope mode, the format
     list could not be read, or a capture failed.
   The worst deviations (per control, luma, R/B, sharpness for information, fps, drops) are reported.
7. ``restore`` (housekeeping, as W-AUTO does it): every control the lock touched gets its as-found value and flag
   back (manual controls: value + manual flag; controls found in auto: their as-found value + the auto flag),
   verified by a read-only read (retried once). Not done on a gated, dead or faulted camera, nor on a Kiyo Pro
   whose capture failed (a first-sample timeout is how a Kiyo Pro wedge starts: no further command is sent).

How the in-stream readback works: ``wincam capture`` has no read-only schedule item, so each sample is a
``<control>=manual`` item: wincam reads the control (``before_value`` / ``before_flags``, the readback used here)
and re-sets the SAME value with the manual flag. It cannot hide a value drift (the drifted value is kept and keeps
showing); it can only switch an auto flag that came back on to manual again, which has already been recorded as a
failure at that sample.

Scene assumptions: a static scene under steady light. The image criteria are inconclusive (never a failure) when
the first soak sample is dark (luma < DARK_LUMA) or bright (> BRIGHT_LUMA). A light change in the room moves luma
while every readback holds; the result says so.

Tier 0 only: frame content and control readbacks; no UVC PTS/SCR, no registry. Every camera command goes through
``ctx.camcmd`` (capkit.get_formats / get_controls / set_controls / wincam_capture). Raw frames go to
``ctx.raw_test_dir("W-NODRIFT")/<camera slug>/<segment>/`` (outside the repo); the JSON is the dict ``run(ctx)``
returns. Quick (``ctx.args.quick``): a 60 s soak and 1 restart; ``ctx.args.nodrift_soak_s`` and
``ctx.args.nodrift_restarts`` override both when set.

Offline: ``python w_nodrift.py --rerate <run_dir>`` re-rates <run_dir>/W-NODRIFT.json with the current thresholds
into <run_dir>/reanalysis/W-NODRIFT.json (no camera).
"""
from __future__ import annotations

import io
import json
import statistics
import sys
import time
from pathlib import Path

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
import w_ctrl_effect as ce  # noqa: E402
from common import rating, results  # noqa: E402

TEST = "W-NODRIFT"
GOAL = "G-CTRL-NODRIFT"

#: the controls whose auto mode is switched off and whose readback and flags are sampled through the soak
DRIFT_CONTROLS = ("exposure", "gain", "focus", "white_balance")
#: fixed targets: AE priority 0 (D12) and power-line frequency 60 Hz (UVC / KS value 2; Gerald's mains)
POWERLINE_60HZ = 2
FIXED_TARGETS = {"auto_exposure_priority": 0, "powerline_frequency": POWERLINE_60HZ}
#: locked at the values the camera starts with (D11)
START_VALUE_CONTROLS = ("zoom", "pan", "tilt", "brightness", "contrast", "saturation", "sharpness", "gamma",
                        "backlight_compensation")
LOCK_ORDER = DRIFT_CONTROLS + tuple(FIXED_TARGETS) + START_VALUE_CONTROLS

SOAK_S_FULL, SOAK_S_QUICK = 600, 60
RESTARTS_FULL, RESTARTS_QUICK = 3, 1
SAMPLE_EVERY_S = 30
RESTART_MEASURE_S = 20
RESTART_SAMPLE_EVERY_S = 5
REAPPLY_MS = 1200            # >= 1 s after the first frame (C930e: sets made then stick)
FIRST_SAMPLE_MS = 3000       # first sample of every stream, after the re-apply
SETTLE_MS = 300              # image window starts at least this long after the last re-apply set returned
METRIC_WIN_MS = 3000         # saved frames in [sample, sample + this) give the sample's image metrics
SAVE_EVERY = 20              # every 20th frame saved (~1.5 per second at 30 fps; ~4 frames per metric window)
CAPTURE_TIMEOUT_MS = 5000

# thresholds (provisional, Dom 2026-11-11 task: "put them in constants")
LUMA_TOL = 0.05              # ROI median luma within +/-5 % of the first soak sample
RB_TOL = 0.03                # R/B ratio within +/-3 % of the first soak sample
SHARP_INFO_TOL = 0.25        # sharpness: reported only (focus drift is judged by its readback; the metric is noisy)
DARK_LUMA, BRIGHT_LUMA = 30.0, 225.0
RB_MIN_CHANNEL = 10.0        # a mean R or B below this makes the R/B check inconclusive
LUMA_ROI = (0.1, 0.1, 0.9, 0.9)
SHARP_ROI = (0.25, 0.25, 0.75, 0.75)
GAP_FACTOR = 1.5             # an MF sample-time step > 1.5 x the fitted frame period counts as a drop event
STALL_FACTOR = 3.0           # an arrival (QPC) gap > 3 x the median interval is an arrival stall (late, not lost)

# estimate (seconds)
CTRL_SESSION_S = 4.0         # one wincam controls run (read / set)
CTRL_SESSIONS = 5            # as-found read, lock, restore manual, restore auto, verify read
OPEN_CLOSE_S = 8.0           # capture process start, open to first frame, release
ANALYSIS_S = 6.0             # decoding the window frames, per camera

_sleep = time.sleep          # patched by the offline tests


# ------------------------------------------------------------------------------------------------------- plan
def soak_s(ctx) -> float:
    return float(ck.arg(ctx, "nodrift_soak_s", SOAK_S_FULL, SOAK_S_QUICK))


def n_restarts(ctx) -> int:
    return int(ck.arg(ctx, "nodrift_restarts", RESTARTS_FULL, RESTARTS_QUICK))


def soak_sample_ms(soak: float) -> list[int]:
    """Sample times (ms after the first frame): 3 s, then every 30 s to the end of the soak (21 samples at 600 s)."""
    n = int(soak // SAMPLE_EVERY_S)
    return [FIRST_SAMPLE_MS + k * SAMPLE_EVERY_S * 1000 for k in range(n + 1)]


def restart_sample_ms() -> list[int]:
    """3 s, 8 s, 13 s, 18 s after the first frame of a restart (measured for 20 s)."""
    n = int((RESTART_MEASURE_S - FIRST_SAMPLE_MS / 1000.0) // RESTART_SAMPLE_EVERY_S)
    return [FIRST_SAMPLE_MS + k * RESTART_SAMPLE_EVERY_S * 1000 for k in range(n + 1)]


def capture_seconds(sample_ms: list[int]) -> float:
    return (max(sample_ms) + METRIC_WIN_MS) / 1000.0 + 0.5


def estimate_s(ctx) -> float:
    """~12 min per camera for a full run (600 s soak + 3 x ~22 s restarts + control sessions)."""
    soak = capture_seconds(soak_sample_ms(soak_s(ctx))) + OPEN_CLOSE_S
    rs = n_restarts(ctx) * (capture_seconds(restart_sample_ms()) + OPEN_CLOSE_S)
    per_cam = CTRL_SESSIONS * CTRL_SESSION_S + soak + rs + ANALYSIS_S
    return len(ctx.cameras) * per_cam


def kiyo_stream_starts(ctx) -> int:
    """Stream starts per camera (the Kiyo Pro included): the soak plus each restart (for run_suite --plan)."""
    return 1 + n_restarts(ctx)


def label(cam: dict) -> str:
    """Camera name for messages; the Razer Kiyo Pro (1532:0E05) is always named 'Kiyo Pro'."""
    base = f"{cam.get('name')} ({cam.get('vid')}:{cam.get('pid')})"
    return f"Razer Kiyo Pro {base}" if cam.get("is_kiyo") else base


def pick_mode(ctx, advertised: list) -> tuple:
    """The first in-scope 30 fps MJPEG mode (1280x720@30 preferred: skellycam's mode), else the default in-scope
    mode; (None, record with untested_reason) when the camera has no in-scope MJPEG mode."""
    kept, scope = ck.scoped(ctx, advertised)
    if not kept:
        return ck.scoped_default(ctx, advertised)
    thirty = [m for m in kept if abs(m.fps - 30.0) <= 30.0 * 0.005]
    mode = ck.default_mode(thirty or kept)
    scope["rule"] = "first in-scope 30 fps MJPEG mode (1280x720@30 where offered: skellycam's mode)"
    scope["in_scope_streaming"] = [m.text for m in kept]
    scope["default_mode"] = mode.text if mode else None
    return mode, scope


# ------------------------------------------------------------------------------------------------------- controls
def _isint(f) -> bool:
    return isinstance(f, int) and not isinstance(f, bool)


def _auto(f) -> bool | None:
    return bool(f & 1) if _isint(f) else None


def _manual(f) -> bool | None:
    return bool(f & 2) if _isint(f) else None


def _fnames(f) -> list[str] | None:
    if not _isint(f):
        return None
    return [n for bit, n in ((1, "auto"), (2, "manual")) if f & bit]


def control_info(c: dict) -> dict:
    return {k: c.get(k) for k in ("value", "flags", "flags_names", "caps_flags_names", "min", "max", "step",
                                  "default", "get_ok", "via")}


def plan_lock(tab: dict) -> tuple[dict, dict]:
    """({control: lock entry}, {control: why not locked}) from the as-found control table. Entry: group (auto_off /
    fixed / start_value), requested value, as-found value and flags, tolerance (one step for auto_off and
    start_value, exact for the fixed targets), auto_capable / manual_capable from the caps."""
    lock, skipped = {}, {}

    def entry(n: str, c: dict, group: str, want: int) -> dict:
        caps = c.get("caps_flags_names") or []
        rng = {k: c.get(k) for k in ("min", "max", "step")}
        return {"group": group, "requested": int(want), "as_found_value": c.get("value"),
                "as_found_flags_names": c.get("flags_names"), "caps_flags_names": caps,
                "auto_capable": "auto" in caps, "manual_capable": "manual" in caps, "range": rng,
                "tolerance": 0 if group == "fixed" else ce.step_tol(rng)}

    for n in LOCK_ORDER:
        c = tab.get(n)
        if c is None:
            skipped[n] = "n/a: not supported"
            continue
        if not ce.control_answered(c) or not isinstance(c.get("value"), (int, float)):
            skipped[n] = f"not locked: the as-found GET failed ({ce._get_hr(c)})"
            continue
        caps = c.get("caps_flags_names") or []
        if n in DRIFT_CONTROLS:
            if "manual" not in caps:
                skipped[n] = f"cannot lock: no manual mode (caps {caps})"
                continue
            lock[n] = entry(n, c, "auto_off", c["value"])
        elif n in FIXED_TARGETS:
            want = FIXED_TARGETS[n]
            lo, hi = c.get("min"), c.get("max")
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and not lo <= want <= hi:
                skipped[n] = f"left as found: target {want} is outside the range {lo}..{hi}"
                continue
            lock[n] = entry(n, c, "fixed", want)
        else:
            lock[n] = entry(n, c, "start_value", c["value"])
    return lock, skipped


def readback_ok(lk: dict, value, flags) -> bool | None:
    """Within the lock's tolerance of the requested value, auto flag off (auto-capable controls), manual flag set
    (manual-capable controls); None when nothing was read."""
    if not isinstance(value, (int, float)):
        return None
    ok = abs(value - lk["requested"]) <= lk["tolerance"]
    if lk.get("auto_capable") and _auto(flags):
        ok = False
    if lk.get("manual_capable") and _isint(flags) and not _manual(flags):
        ok = False
    return bool(ok)


def _short(control) -> str:
    return str(control or "").split(".")[-1]


def do_lock(ctx, cam: dict, lock: dict) -> dict:
    """Step 2: one ``wincam controls --set`` with every lock value (manual flag), requested vs read back."""
    sets = {n: lk["requested"] for n, lk in lock.items()}
    j, r = ck.set_controls(ctx, cam, "mf", sets, flags="manual")
    per = {}
    got = {_short(x.get("control")): x for x in (j or {}).get("sets") or []}
    for n, lk in lock.items():
        x = got.get(n)
        if x is None:
            per[n] = {"requested": lk["requested"], "ok": None, "missing": True}
            continue
        rv, rf = x.get("readback_value"), x.get("readback_flags")
        per[n] = {"group": lk["group"], "requested": lk["requested"], "before_value": x.get("before_value"),
                  "before_flags_names": _fnames(x.get("before_flags")), "readback_value": rv,
                  "readback_flags_names": x.get("readback_flags_names") or _fnames(rf),
                  "hr_set_name": x.get("hr_set_name"), "wincam_matches": x.get("matches"),
                  "timed_out": x.get("timed_out"), "tolerance": lk["tolerance"], "ok": readback_ok(lk, rv, rf)}
    return {"run": r, "error": (j or {}).get("error"), "device_not_answering": (j or {}).get("device_not_answering"),
            "no_json": j is None, "controls": per,
            "all_ok": bool(per) and all(x.get("ok") is True for x in per.values())}


# ------------------------------------------------------------------------------------------------------- frames
def _crop(img, roi):
    w, h = img.size
    l, t, r, b = roi
    return img.crop((int(round(l * w)), int(round(t * h)), max(int(round(l * w)) + 1, int(round(r * w))),
                     max(int(round(t * h)) + 1, int(round(b * h)))))


def frame_metrics(data: bytes, w: int, h: int) -> dict | None:
    """Median luma and mean luma / R / G / B over the central 80 % (Pillow 'L' = ITU-R 601 Y', JPEG DCT-scaled to
    1/4), R/B ratio, and the normalised Laplacian sharpness of the centre 50 % at full resolution
    (common.imgmetrics.sharpness). None for a frame that is not a JPEG."""
    if not data or data[:2] != b"\xff\xd8":
        return None
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    from common import imgmetrics as im  # noqa: PLC0415
    img = Image.open(io.BytesIO(data))
    img.draft("RGB", (max(1, img.width // 4), max(1, img.height // 4)))
    roi = _crop(img.convert("RGB"), LUMA_ROI)
    a = np.asarray(roi, dtype=np.float64)
    y = np.asarray(roi.convert("L"), dtype=np.float64)
    r, g, b = float(a[..., 0].mean()), float(a[..., 1].mean()), float(a[..., 2].mean())
    return {"luma_median": float(np.median(y)), "luma_mean": float(y.mean()), "r": r, "g": g, "b": b,
            "rb_ratio": r / max(b, 1e-6), "sharpness": float(im.sharpness(data, SHARP_ROI))}


def window_image(od: Path, rows: list, first_ns: int | None, a_ms: float, b_ms: float, mode) -> dict:
    """Median of each frame metric over the saved frames in [a_ms, b_ms) after the first frame."""
    if first_ns is None:
        return {"n": 0}
    sel = [r for r in rows if r.get("mjpeg_offset") is not None and isinstance(r.get("qpc_ns"), (int, float))
           and a_ms <= (r["qpc_ns"] - first_ns) / 1e6 < b_ms]
    mets, err = [], None
    for _r, data in ck.saved_frame_bytes(od, sel):
        try:
            m = frame_metrics(data, mode.w, mode.h)
        except Exception as e:  # noqa: BLE001 - an undecodable frame is skipped
            err = repr(e)[:160]
            m = None
        if m:
            mets.append(m)
    out: dict = {"n": len(mets)}
    if err:
        out["decode_error"] = err
    for k in ("luma_median", "luma_mean", "r", "g", "b", "rb_ratio", "sharpness"):
        vals = [m[k] for m in mets if isinstance(m.get(k), (int, float))]
        out[k] = round(float(statistics.median(vals)), 6) if vals else None
    return out


def _fps_window(rows: list, first_ns: int | None, a_ms: float, b_ms: float) -> float | None:
    if first_ns is None:
        return None
    sel = [r for r in rows if isinstance(r.get("qpc_ns"), (int, float)) and a_ms <= (r["qpc_ns"] - first_ns) / 1e6 < b_ms]
    v = ck.fps_from_rows(sel, skip_frac=0.0)
    return round(v, 3) if v else None


def stream_stats(rows: list, summary: dict, mode) -> dict:
    """Delivered fps (least-squares fit over every frame's arrival time), drops and arrival stalls.

    Drops come from the MF sample time (``sample_time_100ns``): a step > GAP_FACTOR x the frame period (from the
    fitted delivered fps) holds round(step / period) - 1 missing frames. Host arrival times (QPC) are quantised by the timer tick (16 ms on
    Gerald: intervals read 32 or 48 ms at 30 fps), so they are NOT used for drops (smoke run 2026-11-11 counted 50-88
    false "drops" per minute that way at a delivered 30.0 fps). Arrival gaps > STALL_FACTOR x the median interval are
    reported separately as ``arrival_stalls`` (late delivery, frames not lost)."""
    ts = [r["qpc_ns"] for r in rows if isinstance(r.get("qpc_ns"), (int, float))]
    st = [r["sample_time_100ns"] for r in rows if isinstance(r.get("sample_time_100ns"), (int, float))]
    fr = (summary or {}).get("frames") if isinstance((summary or {}).get("frames"), dict) else {}
    out = {"frames": len(rows), "nominal_fps": mode.fps if mode else None,
           "fps_measured": None, "fps_wincam": (summary or {}).get("fps_measured"),
           "discontinuities": fr.get("discontinuities"), "null_samples": fr.get("null_samples")}
    if len(ts) < 3:
        return out
    iv = [(b - a) / 1e6 for a, b in zip(ts, ts[1:])]
    med = statistics.median(iv)
    stalls = [d for d in iv if med > 0 and d > STALL_FACTOR * med]
    fps = ck.fps_from_rows(rows, skip_frac=0.0)
    out.update(fps_measured=round(fps, 3) if fps else None, duration_s=round((ts[-1] - ts[0]) / 1e9, 3),
               median_interval_ms=round(med, 3), max_interval_ms=round(max(iv), 3),
               arrival_stalls=len(stalls), max_arrival_stall_ms=round(max(stalls), 1) if stalls else None,
               drop_basis=None, drop_events=None, est_dropped_frames=None)
    # both clocks step in 16 ms ticks on Gerald (median step reads 32.0 ms at 30 fps), so a gap is judged against the
    # true frame period from the fitted delivered fps (fallback: nominal), never against the quantised median
    period = 1000.0 / fps if fps else (1000.0 / mode.fps if mode and mode.fps else None)
    basis = st if len(st) >= 3 else None
    if basis and period:
        sv = [(b - a) / 1e4 for a, b in zip(st, st[1:])]
        sg = [d for d in sv if d > GAP_FACTOR * period]
        out.update(drop_basis="mf_sample_time vs fitted frame period", frame_period_ms=round(period, 3),
                   median_sample_step_ms=round(statistics.median(sv), 3), drop_events=len(sg),
                   est_dropped_frames=int(sum(max(0, round(d / period) - 1) for d in sg)),
                   max_sample_step_ms=round(max(sv), 1), backward_sample_steps=sum(1 for d in sv if d <= 0))
    return out


def _ms(t_ns, first_ns) -> float | None:
    return None if t_ns is None or first_ns is None else round((int(t_ns) - int(first_ns)) / 1e6, 1)


# ------------------------------------------------------------------------------------------------------- streams
def in_stream(lock: dict) -> list[str]:
    """The locked controls set while streaming: those whose pre-stream lock read back (``in_stream`` not False). A
    control set that times out makes wincam skip every later schedule item, so a control that already failed its
    lock is not risked in the stream (it is reported as not re-applied)."""
    return [n for n, lk in lock.items() if lk.get("in_stream", True)]


def schedule_spec(lock: dict, sample_ms: list[int]) -> list[str]:
    """Re-apply every locked value at REAPPLY_MS, then a manual-keep read of each drift control at each sample."""
    names = in_stream(lock)
    drift = [n for n in DRIFT_CONTROLS if n in names]
    items = [f"{REAPPLY_MS}:{n}={lock[n]['requested']}" for n in names]
    items += [f"{t}:{n}=manual" for t in sample_ms for n in drift]
    return items


def analyse_segment(summary: dict, rows: list, od: Path, mode, lock: dict, sample_ms: list[int], seg_label: str) -> dict:
    """Pure analysis of one stream (the soak or a restart) from wincam's summary (schedule events) and frames."""
    s = summary or {}
    first_ns = rows[0].get("qpc_ns") if rows else None
    evs: dict = {}
    for e in s.get("schedule") or []:
        try:
            evs[(int(round(float(e.get("at_ms")))), _short(e.get("control")))] = e
        except (TypeError, ValueError):
            continue
    reapply, done = {}, []
    names = in_stream(lock)
    for n, lk in lock.items():
        if n not in names:
            reapply[n] = {"excluded": "not set in the stream: its pre-stream lock did not read back", "ok": None,
                          "changed_at_stream_start": None}
            continue
        e = evs.get((REAPPLY_MS, n))
        if e is None:
            reapply[n] = {"missing": True, "ok": None, "changed_at_stream_start": None}
            continue
        bv, bf = e.get("before_value"), e.get("before_flags")
        changed = None
        if isinstance(bv, (int, float)):
            # any change counts here (not the one-step tolerance): the C930e's -6 -> -5 reset is one step
            changed = bool(bv != lk["requested"] or (lk.get("auto_capable") and _auto(bf))
                           or (lk.get("manual_capable") and _isint(bf) and not _manual(bf)))
        rv, rf = e.get("readback_value"), e.get("readback_flags")
        reapply[n] = {"before_value": bv, "before_flags_names": _fnames(bf), "readback_value": rv,
                      "readback_flags_names": e.get("readback_flags_names") or _fnames(rf),
                      "hr_set_name": e.get("hr_set_name"), "timed_out": e.get("timed_out"),
                      "skipped": e.get("skipped"), "t_ms": _ms(e.get("applied_qpc_ns"), first_ns),
                      "changed_at_stream_start": changed, "ok": readback_ok(lk, rv, rf)}
        dm = _ms(e.get("done_qpc_ns"), first_ns)
        if dm is not None:
            done.append(dm)
    drift = [n for n in DRIFT_CONTROLS if n in names]
    t_end = (rows[-1]["qpc_ns"] - first_ns) / 1e6 if rows and first_ns is not None else None
    samples = []
    for k, t in enumerate(sample_ms):
        ctrl, read_ms = {}, []
        for n in drift:
            e = evs.get((t, n))
            if e is None:
                ctrl[n] = {"value": None, "missing": True}
                continue
            bf = e.get("before_flags")
            ctrl[n] = {"value": e.get("before_value"), "flags_names": _fnames(bf), "auto": _auto(bf),
                       "manual": _manual(bf)}
            if e.get("timed_out") or e.get("skipped"):
                ctrl[n].update(value=None, timed_out=e.get("timed_out"), skipped=e.get("skipped"))
            m = _ms(e.get("applied_qpc_ns"), first_ns)
            if m is not None:
                read_ms.append(m)
        w0 = float(max(t, (max(done) + SETTLE_MS) if done else 0))
        w1 = w0 + METRIC_WIN_MS
        nxt = sample_ms[k + 1] if k + 1 < len(sample_ms) else (t_end if t_end is not None else t + METRIC_WIN_MS)
        samples.append({"k": k, "t_ms": t, "read_ms": min(read_ms) if read_ms else None, "controls": ctrl,
                        "image_window_ms": [w0, w1], "image": window_image(od, rows, first_ns, w0, w1, mode),
                        "fps_to_next_sample": _fps_window(rows, first_ns, t, nxt)})
    return {"label": seg_label, "frames": len(rows), "first_frame_ns": first_ns, "reapply": reapply,
            "needed_reapply": [n for n, x in reapply.items() if x.get("changed_at_stream_start")],
            "samples": samples, "stream": stream_stats(rows, s, mode),
            "schedule_events": len(s.get("schedule") or []),
            "schedule_timed_out": any(e.get("timed_out") for e in s.get("schedule") or []),
            "schedule_skipped": sum(1 for e in s.get("schedule") or [] if e.get("skipped"))}


def run_segment(ctx, cam: dict, mode, lock: dict, od: Path, seg_label: str, sample_ms: list[int]) -> dict:
    items = schedule_spec(lock, sample_ms)
    secs = capture_seconds(sample_ms)
    s, r = ck.wincam_capture(ctx, cam, mode, od, seconds=secs, save=f"every:{SAVE_EVERY}",
                             timeout_ms=CAPTURE_TIMEOUT_MS, extra=["--schedule", ";".join(items)],
                             timeout_s=secs + 60 + 0.5 * len(items))
    s = s or {}
    rows = ck.load_frames(od)
    seg = analyse_segment(s, rows, od, mode, lock, sample_ms, seg_label)
    fr = s.get("frames") if isinstance(s.get("frames"), dict) else {}
    seg.update(planned_seconds=secs, capture_ok=bool(s.get("ok")) and bool(rows), wincam_ok=s.get("ok"),
               frames_total=fr.get("total"), error=s.get("error"), run=r, raw_dir=str(od),
               capture_fault=ck.fault_from_result("mf", s, r))
    return seg


# ------------------------------------------------------------------------------------------------------- halt
def _call(fn, cam: dict):
    if not callable(fn):
        return None
    try:
        return fn(cam)
    except TypeError:
        return fn(cam.get("key"))


def halt_reason(ctx, cam: dict) -> dict | None:
    """Why the camera's remaining work must be skipped, or None: gated at the start of this test
    (``ctx.camera_gated``), declared dead (``ctx.camera_dead``, when the ctx has it), or faulted during this test
    (capkit.device_fault -> ``ctx.camera_faulted``)."""
    checks = (("camera_gated", getattr(ctx, "camera_gated", None)),
              ("camera_dead", getattr(ctx, "camera_dead", lambda c: None)),
              ("camera_faulted", lambda c: ck.device_fault(ctx, c)))
    for name, fn in checks:
        try:
            rec = _call(fn, cam)
        except Exception as e:  # noqa: BLE001 - a broken check must not run commands on a maybe-dead camera
            return {"by": name, "record": {"check_error": repr(e)}}
        if rec:
            return {"by": name, "record": rec if isinstance(rec, dict) else {"detail": rec}}
    return None


def halted_verdict(cam: dict, h: dict, step: str, evidence: dict | None = None) -> dict:
    rec = dict(h.get("record") or {})
    ts = rec.get("since_utc") or rec.get("utc") or rec.get("first_fault_utc")
    why = (f"untested: device fault/dead: {label(cam)} ({h.get('by')}{', since ' + str(ts) if ts else ''}); "
           f"remaining work skipped from step '{step}', never retried or re-opened")
    v = rating.device_fault_untested({"utc": ts, "code": rec.get("code"), "test": rec.get("test"),
                                      "mode": rec.get("mode")}, reason=why,
                                     evidence={"halted_at_step": step, "halt_source": h.get("by"),
                                               "halt_record": rec, **(evidence or {})})
    v["summary_label"] = "untested (device fault/dead)"
    return v


def capture_fault(ctx, cam: dict, seg: dict, mode_text: str | None) -> dict | None:
    """The camera's fault after a capture: already faulted (ctx.camcmd's scan marks it), else a fault in the
    capture itself (0x8007001F, unreleasable reader, killed capture), which is reported to the suite gate."""
    f = ck.device_fault(ctx, cam)
    if f:
        return f
    flt = seg.get("capture_fault")
    err = seg.get("error") or {}
    if not flt and isinstance(err, dict) and err.get("class") == "device_error":
        flt = {"kind": "device_error", "code": err.get("hr"), "stage": err.get("stage"),
               "reason": "capture reported device_error"}
    if not flt:
        return None
    marked = ck.mark_device_fault(ctx, cam, TEST, mode_text, "mf", flt) or {}
    return {"utc": marked.get("utc") or results.utc_now_iso(), "test": marked.get("test") or TEST,
            "mode": marked.get("mode") or mode_text, "code": marked.get("code") or flt.get("code"),
            "kind": marked.get("kind") or flt.get("kind"), "stage": flt.get("stage"), "reason": flt.get("reason")}


# ------------------------------------------------------------------------------------------------------- restore
def restore_state(ctx, cam: dict, as_found: dict, lock: dict) -> dict:
    """W-AUTO's restore: manual controls -> as-found value + manual flag; controls found in auto -> as-found value +
    the auto flag. Verified by a read-only read: auto ones by the auto flag, the others by value (the lock's
    tolerance) and, where the caps have it, the manual flag."""
    orig = {n: as_found[n] for n in lock if isinstance((as_found.get(n) or {}).get("value"), (int, float))}
    auto = {n: int(o["value"]) for n, o in orig.items() if "auto" in (o.get("flags_names") or [])}
    manual = {n: int(o["value"]) for n, o in orig.items() if n not in auto}
    out: dict = {"auto": auto, "manual": manual, "steps": []}
    for sets, flags in ((manual, "manual"), (auto, "auto")):
        if not sets:
            continue
        j, r = ck.set_controls(ctx, cam, "mf", sets, flags=flags)
        out["steps"].append({"sets": sets, "flags": flags, "run": r,
                             "detail": [{k: x.get(k) for k in ("control", "requested", "readback_value",
                                                               "readback_flags", "matches", "hr_set_name")}
                                        for x in (j or {}).get("sets") or []]})
    chk, r = ck.get_controls(ctx, cam, "mf")
    tab = ck.control_table(chk)
    after, ok = {}, {}
    for n in orig:
        a = tab.get(n) or {}
        names = a.get("flags_names") or []
        after[n] = {"value": a.get("value"), "flags_names": names}
        if n in auto:
            ok[n] = "auto" in names
        elif isinstance(a.get("value"), (int, float)):
            caps = (orig[n].get("caps_flags_names") or [])
            ok[n] = bool(abs(a["value"] - manual[n]) <= lock[n]["tolerance"]
                         and ("manual" in names or "manual" not in caps))
        else:
            ok[n] = False
    out.update(after=after, verified=ok, read=r,
               restored=(all(ok.values()) if chk and ok else (None if not chk else True)),
               note="as-found value + manual flag for manual controls; as-found value + auto flag for controls "
                    "found in auto (verified by the auto flag: the camera owns the value under auto)")
    return out


def restore_verified(ctx, cam: dict, as_found: dict, lock: dict, errors: list) -> dict:
    rs = restore_state(ctx, cam, as_found, lock)
    if rs.get("restored") is not True and halt_reason(ctx, cam) is None:
        ctx.log(f"{TEST}: {label(cam)}: restore not verified; retrying once")
        _sleep(2.0)
        rs2 = restore_state(ctx, cam, as_found, lock)
        rs2["first_attempt"] = rs
        rs = rs2
    if rs.get("restored") is not True:
        errors.append({"camera": cam.get("key"), "camera_label": label(cam), "restore_not_verified": rs.get("after"),
                       "wanted": {"auto": rs.get("auto"), "manual": rs.get("manual")}})
    return rs


# ------------------------------------------------------------------------------------------------------- rating
def _ratio_dev(v, ref) -> float | None:
    if not isinstance(v, (int, float)) or not isinstance(ref, (int, float)) or not ref:
        return None
    return v / ref - 1.0


def evaluate(cres: dict) -> dict:
    """Pure evaluation of one camera record (live or stored): criteria inputs and the worst deviations."""
    lock = cres.get("lock_plan") or {}
    plan = cres.get("plan") or {}
    segs = cres.get("segments") or []
    drift_all = [n for n in DRIFT_CONTROLS if n in lock]
    drift = [n for n in drift_all if lock[n].get("in_stream", True)]
    cannot = {n: why for n, why in (cres.get("lock_skipped") or {}).items()
              if n in DRIFT_CONTROLS and str(why).startswith("cannot lock")}
    lres = ((cres.get("lock_result") or {}).get("controls")) or {}
    lock_bad = {n: x for n, x in lres.items() if x.get("ok") is not True}
    lock_bad.update({n: {"missing": True} for n in lock if lres and n not in lres})
    re_core, re_other = [], []
    for sg in segs:
        for n, x in (sg.get("reapply") or {}).items():
            if x.get("ok") is not True:
                (re_core if n in drift_all else re_other).append({"segment": sg.get("label"), "control": n,
                                                              "excluded": x.get("excluded"),
                                                              "readback_value": x.get("readback_value"),
                                                              "readback_flags_names": x.get("readback_flags_names"),
                                                              "requested": (lock.get(n) or {}).get("requested"),
                                                              "missing": x.get("missing")})
    ref = None
    for sg in segs:
        if sg.get("label") == "soak":
            ref = next((s["image"] for s in sg.get("samples") or []
                        if isinstance((s.get("image") or {}).get("luma_median"), (int, float))), None)
    flag_events, value_out, missing_reads, missing_img, measured = [], [], 0, 0, 0
    worst_ctrl = {n: {"max_abs_dev": None, "max_steps": None, "at": None, "tolerance": lock[n]["tolerance"],
                      "locked": lock[n]["requested"]} for n in drift}
    worst = {"luma": {"max_rel_dev": None, "at": None}, "rb_ratio": {"max_rel_dev": None, "at": None},
             "sharpness_info": {"max_rel_dev": None, "at": None}}
    luma_out, rb_out = [], []
    for sg in segs:
        for s in sg.get("samples") or []:
            at = f"{sg.get('label')} sample {s.get('k')} ({s.get('t_ms')} ms)"
            for n in drift:
                c = (s.get("controls") or {}).get(n) or {}
                v = c.get("value")
                if not isinstance(v, (int, float)):
                    missing_reads += 1
                    continue
                measured += 1
                lk = lock[n]
                if lk.get("auto_capable") and c.get("auto"):
                    flag_events.append({"at": at, "control": n, "value": v, "flags_names": c.get("flags_names")})
                d = abs(v - lk["requested"])
                st = (lk.get("range") or {}).get("step") or 1
                w = worst_ctrl[n]
                if w["max_abs_dev"] is None or d > w["max_abs_dev"]:
                    w.update(max_abs_dev=d, max_steps=round(d / st, 3) if st else None, at=at, value=v)
                if d > lk["tolerance"]:
                    value_out.append({"at": at, "control": n, "value": v, "locked": lk["requested"],
                                      "tolerance": lk["tolerance"]})
            img = s.get("image") or {}
            if not isinstance(img.get("luma_median"), (int, float)):
                missing_img += 1
                continue
            measured += 1
            if ref is None:
                continue
            for key, wk, tol, sink in (("luma_median", "luma", LUMA_TOL, luma_out), ("rb_ratio", "rb_ratio", RB_TOL, rb_out),
                                       ("sharpness", "sharpness_info", SHARP_INFO_TOL, None)):
                dv = _ratio_dev(img.get(key), ref.get(key))
                if dv is None:
                    continue
                if worst[wk]["max_rel_dev"] is None or abs(dv) > abs(worst[wk]["max_rel_dev"]):
                    worst[wk].update(max_rel_dev=round(dv, 5), at=at, value=img.get(key), reference=ref.get(key))
                if sink is not None and abs(dv) > tol:
                    sink.append({"at": at, "value": img.get(key), "reference": ref.get(key), "rel_dev": round(dv, 5)})
    scene = None
    if ref is None:
        scene = "no reference image (first soak sample has no decodable frame)"
    elif ref["luma_median"] < DARK_LUMA:
        scene = f"dark scene (reference luma {ref['luma_median']:.1f} < {DARK_LUMA:g})"
    elif ref["luma_median"] > BRIGHT_LUMA:
        scene = f"bright scene (reference luma {ref['luma_median']:.1f} > {BRIGHT_LUMA:g})"
    rb_scene = scene
    if scene is None and min(ref.get("r") or 0.0, ref.get("b") or 0.0) < RB_MIN_CHANNEL:
        rb_scene = f"mean R or B below {RB_MIN_CHANNEL:g} in the reference"
    fps = [sg.get("stream", {}).get("fps_measured") for sg in segs if sg.get("stream", {}).get("fps_measured")]
    win_fps = [s.get("fps_to_next_sample") for sg in segs for s in sg.get("samples") or []
               if s.get("fps_to_next_sample")]
    planned_segs = 1 + int(plan.get("restarts") or 0)
    want_samples = {"soak": int(plan.get("soak_samples") or 0)}
    complete_detail = {"segments_planned": planned_segs, "segments_run": len(segs),
                       "captures_ok": sum(1 for sg in segs if sg.get("capture_ok")),
                       "missing_control_reads": missing_reads, "missing_images": missing_img,
                       "schedule_timed_out": [sg.get("label") for sg in segs if sg.get("schedule_timed_out")]}
    complete = (len(segs) == planned_segs and all(sg.get("capture_ok") for sg in segs) and missing_reads == 0
                and missing_img == 0 and not complete_detail["schedule_timed_out"]
                and all(len(sg.get("samples") or []) == want_samples.get(sg.get("label"),
                                                                         int(plan.get("restart_samples") or 0))
                        for sg in segs))
    return {
        "measured": measured > 0, "reference_image": ref, "scene_note": scene, "rb_scene_note": rb_scene,
        "cannot_lock": cannot, "lock_not_read_back": lock_bad,
        "lock_not_read_back_core": sorted(n for n in lock_bad if n in drift_all),
        "reapply_not_read_back_core": re_core, "reapply_not_read_back_other": re_other,
        "auto_flag_events": flag_events, "readback_out_of_tolerance": value_out,
        "luma_out_of_band": luma_out, "rb_out_of_band": rb_out,
        "luma_ok": None if scene or ref is None else not luma_out,
        "rb_ok": None if rb_scene or ref is None else not rb_out,
        "complete": complete, "complete_detail": complete_detail,
        "needed_reapply": {sg.get("label"): sg.get("needed_reapply") for sg in segs},
        "worst_deviations": {"controls": worst_ctrl, **worst,
                             "fps": {"per_stream": fps, "min_window": min(win_fps) if win_fps else None,
                                     "max_window": max(win_fps) if win_fps else None},
                             "drop_events": sum(int(sg.get("stream", {}).get("drop_events") or 0) for sg in segs),
                             "est_dropped_frames": sum(int(sg.get("stream", {}).get("est_dropped_frames") or 0)
                                                       for sg in segs)},
    }


def rate(ev: dict, cam_label: str) -> dict:
    """G-CTRL-NODRIFT rating of one camera from ``evaluate``'s output (see the module docstring)."""
    flags_ok = None if not ev["measured"] else not ev["auto_flag_events"]
    values_ok = None if not ev["measured"] else not ev["readback_out_of_tolerance"]
    lock_ok = not ev["lock_not_read_back"] and not ev["cannot_lock"]
    reapply_core_ok = not ev["reapply_not_read_back_core"]
    crit = [
        rating._crit("lock (AE / auto gain / AF / AWB off, AE priority 0, 60 Hz, start values) read back before the "
                     "stream", lock_ok, {"not_read_back": ev["lock_not_read_back"], "cannot_lock": ev["cannot_lock"]}),
        rating._crit(f"re-applied {REAPPLY_MS} ms after the first frame and read back in every stream "
                     "(exposure / gain / focus / WB required)", reapply_core_ok and not ev["reapply_not_read_back_other"],
                     {"core": ev["reapply_not_read_back_core"], "other": ev["reapply_not_read_back_other"],
                      "needed_reapply": ev["needed_reapply"]}),
        rating._crit("auto flags stay off (AE, AF, AWB and auto gain where present) through the soak and every restart",
                     flags_ok, {"events": ev["auto_flag_events"][:20], "n": len(ev["auto_flag_events"])}),
        rating._crit("exposure, gain, focus and WB readbacks stay within one step of the locked value", values_ok,
                     {"out": ev["readback_out_of_tolerance"][:20], "n": len(ev["readback_out_of_tolerance"])}),
        rating._crit(f"ROI median luma within +/-{LUMA_TOL:.0%} of the first soak sample", ev["luma_ok"],
                     {"out": ev["luma_out_of_band"][:20], "scene": ev["scene_note"]}),
        rating._crit(f"R/B ratio within +/-{RB_TOL:.0%} of the first soak sample", ev["rb_ok"],
                     {"out": ev["rb_out_of_band"][:20], "scene": ev["rb_scene_note"]}),
        rating._crit("soak and every planned restart completed, every sample read", ev["complete"],
                     ev["complete_detail"]),
    ]
    evid = {"camera": cam_label, "worst_deviations": ev["worst_deviations"], "needed_reapply": ev["needed_reapply"],
            "reference_image": ev["reference_image"]}
    fails = []
    if ev["cannot_lock"]:
        fails.append(f"cannot switch {sorted(ev['cannot_lock'])} to manual")
    if not reapply_core_ok:
        fails.append("the re-apply of " + ", ".join(sorted({x['control'] for x in ev['reapply_not_read_back_core']}))
                     + " did not read back")
    if flags_ok is False:
        fails.append("auto flag came back on (" + ", ".join(sorted({x['control'] for x in ev['auto_flag_events']})) + ")")
    if values_ok is False:
        fails.append("readback left its tolerance (" + ", ".join(sorted({x['control'] for x in ev['readback_out_of_tolerance']})) + ")")
    if ev["luma_ok"] is False:
        fails.append(f"luma left +/-{LUMA_TOL:.0%} (worst {ev['worst_deviations']['luma']['max_rel_dev']:+.1%})")
    if ev["rb_ok"] is False:
        fails.append(f"R/B left +/-{RB_TOL:.0%} (worst {ev['worst_deviations']['rb_ratio']['max_rel_dev']:+.1%})")
    if fails:
        note = f"{cam_label}: drift: " + "; ".join(fails)
        if (ev["luma_ok"] is False or ev["rb_ok"] is False) and flags_ok and values_ok:
            note += " (every readback held: a light change in the room, or drift the readback does not show)"
        r = rating._result("no", crit, evid, note)
        r["summary_label"] = "no (drift)"
        return r
    if not ev["measured"]:
        r = rating.untested(f"{cam_label}: nothing measured", evid)
        r["criteria"] = crit
        return r
    if all(c["met"] is True for c in crit):
        return rating._result("yes", crit, evid)
    open_ = [c["criterion"] for c in crit if c["met"] is not True]
    r = rating._result("partial", crit, evid, f"{cam_label}: no drift seen, but not shown in full: " + "; ".join(open_))
    return r


# ------------------------------------------------------------------------------------------------------- run
def run_camera(ctx, cam: dict, cres: dict, raw: Path, soak: float, nrs: int, fcache: dict, errors: list) -> dict:
    lab = label(cam)
    if getattr(ctx, "dry_run", False):
        cres["skipped"] = "plan mode: nothing run"
        return rating.untested(f"{lab}: plan mode, nothing run")
    h = halt_reason(ctx, cam)
    if h:
        ctx.log(f"{TEST}: {lab}: skipped ({h['by']}): untested, device fault/dead")
        cres["halted"] = {"step": "start", **h}
        return halted_verdict(cam, h, "start")
    if not cam.get("mf_symlink"):
        cres["skipped"] = "no MF symbolic link"
        return rating.untested(f"{lab}: no MF symbolic link")
    fm, frun = ck.get_formats(ctx, cam, fcache)
    advertised = ck.mjpeg_modes(fm)
    if not advertised:
        why = ck.format_read_failure(fm, frun)
        h = halt_reason(ctx, cam)
        if h:
            cres["halted"] = {"step": "formats", **h}
            return halted_verdict(cam, h, "formats")
        if why:          # the list could not be read: no probe, no retry (a failing Kiyo Pro is left alone)
            cres["format_read"] = {"untested_reason": why, "run": frun}
            v = rating.untested(f"{lab}: {why}", {"format_read": frun})
            v["summary_label"] = "untested (format read failed)"
            return v
    mode, scope = pick_mode(ctx, advertised)
    cres["mode"], cres["mode_scope"] = (mode.text if mode else None), scope
    if mode is None:
        return ck.scope_untested(ctx, scope)
    sms_soak, sms_rs = soak_sample_ms(soak), restart_sample_ms()
    cres["plan"] = {"soak_s": soak, "soak_samples": len(sms_soak), "restarts": nrs, "restart_samples": len(sms_rs),
                    "reapply_ms": REAPPLY_MS, "sample_every_s": SAMPLE_EVERY_S, "save_every": SAVE_EVERY,
                    "metric_window_ms": METRIC_WIN_MS}
    od_base = Path(raw) / ck.cam_slug(cam)

    # step 1: as found
    h = halt_reason(ctx, cam)
    if h:
        cres["halted"] = {"step": "as_found", **h}
        return halted_verdict(cam, h, "as_found")
    j0, r0 = ck.get_controls(ctx, cam, "mf")
    cres["as_found_read"] = r0
    na, hr = ce.not_answering(j0, r0)
    if na:
        dna = {"hr": hr, "utc": results.utc_now_iso(), "at": "as_found"}
        cres["device_not_answering"] = dna
        f = ck.mark_device_fault(ctx, cam, TEST, mode.text, "mf", {"kind": "device_error", "code": hr,
                                                                   "stage": "control_get",
                                                                   "reason": f"device not answering ({hr})"})
        ctx.log(f"{TEST}: {lab}: control GETs failed ({hr}); camera marked faulted, remaining work skipped")
        h = {"by": "device_not_answering", "record": f or dna}
        cres["halted"] = {"step": "as_found", **h}
        return halted_verdict(cam, h, "as_found", {"device_not_answering": dna})
    tab = ck.control_table(j0)
    cres["as_found"] = {n: control_info(tab[n]) for n in LOCK_ORDER if n in tab}
    lock, skipped = plan_lock(tab)
    cres["lock_plan"], cres["lock_skipped"] = lock, skipped
    if not any(n in lock for n in DRIFT_CONTROLS):
        return rating.untested(f"{lab}: no exposure / gain / focus / white-balance control with a manual mode",
                               {"lock_skipped": skipped})

    segs: list = []
    cres["segments"] = segs
    touched, halted, capture_failed, no_more = False, None, None, False
    try:
        # step 2: lock
        h = halt_reason(ctx, cam)
        if h:
            halted = (h, "lock")
        else:
            touched = True
            lr = do_lock(ctx, cam, lock)
            cres["lock_result"] = lr
            for n, lk in lock.items():
                lk["in_stream"] = (lr["controls"].get(n) or {}).get("ok") is True
            ctx.log(f"{TEST}: {lab}: locked {len(lock)} controls; read back ok: "
                    f"{sorted(n for n, x in lr['controls'].items() if x.get('ok'))}; not: "
                    f"{sorted(n for n, x in lr['controls'].items() if not x.get('ok'))}")
            if lr.get("device_not_answering"):
                f = ck.mark_device_fault(ctx, cam, TEST, mode.text, "mf", {
                    "kind": "device_error", "code": (lr.get("error") or {}).get("hr"), "stage": "control_get",
                    "reason": "device not answering at the lock"})
                halted = ({"by": "device_not_answering", "record": f or {}}, "lock")
        # steps 3-5: soak, then the restarts
        plans = [("soak", sms_soak)] + [(f"restart{i + 1}", sms_rs) for i in range(nrs)]
        for lbl, sms in plans:
            if halted:
                break
            h = halt_reason(ctx, cam)
            if h:
                halted = (h, lbl)
                break
            ctx.log(f"{TEST}: {lab}: {lbl}: {capture_seconds(sms):.0f} s stream, {len(sms)} samples")
            seg = run_segment(ctx, cam, mode, lock, od_base / lbl, lbl, sms)
            segs.append(seg)
            st = seg.get("stream") or {}
            ctx.log(f"{TEST}: {lab}: {lbl}: frames {seg.get('frames')}, fps {st.get('fps_measured')}, drop events "
                    f"{st.get('drop_events')}, re-applied {seg.get('needed_reapply') or 'nothing changed'} at start")
            f = capture_fault(ctx, cam, seg, mode.text)
            if f:
                halted = ({"by": "capture_fault", "record": f}, lbl)
                ctx.log(f"{TEST}: {lab}: device fault in {lbl}; remaining work skipped (no restore)")
                break
            if not seg.get("capture_ok"):
                capture_failed = f"{lbl}: capture failed ({(seg.get('error') or {}).get('stage') if isinstance(seg.get('error'), dict) else seg.get('error')})"
                if cam.get("is_kiyo"):
                    no_more = True     # a first-sample timeout is how a Kiyo Pro wedge starts: send nothing more
                ctx.log(f"{TEST}: {lab}: {capture_failed}; streaming stopped"
                        + ("; Kiyo Pro: no further command (no restore)" if no_more else ""))
                break
    finally:
        # step 7: restore (housekeeping)
        if touched:
            if halted or no_more:
                why = (f"skipped: {halted[0]['by']} at step '{halted[1]}'" if halted
                       else "skipped: Kiyo Pro capture failed (possible wedge), no further command")
                cres["restore"] = {"skipped": why, "restored": None}
            else:
                h = halt_reason(ctx, cam)
                if h:
                    halted = (h, "restore")
                    cres["restore"] = {"skipped": f"skipped: {h['by']} before the restore", "restored": None}
                else:
                    cres["restore"] = restore_verified(ctx, cam, cres["as_found"], lock, errors)
                    ctx.log(f"{TEST}: {lab}: restore {'verified' if cres['restore'].get('restored') else 'NOT verified'}")
    ev = evaluate(cres)
    cres["evaluation"] = ev
    if halted:
        cres["halted"] = {"step": halted[1], **halted[0]}
        v = halted_verdict(cam, halted[0], halted[1], {"partial_evaluation": {
            "worst_deviations": ev["worst_deviations"], "needed_reapply": ev["needed_reapply"],
            "auto_flag_events": ev["auto_flag_events"][:20]}})
    elif capture_failed:
        cres["capture_failed"] = capture_failed
        v = rating.untested(f"{lab}: {capture_failed}", {"partial_evaluation": ev["worst_deviations"]})
        v["note"] = f"untested: {lab}: {capture_failed}"
        v["summary_label"] = "untested (capture failed)"
    else:
        v = rate(ev, lab)
    v["restore"] = (cres.get("restore") or {}).get("restored")
    return v


def run(ctx) -> dict:
    res = ck.new_result(ctx, TEST)
    arr0 = ck.arrivals_before(ctx)
    soak, nrs = soak_s(ctx), n_restarts(ctx)
    raw = ctx.raw_test_dir(TEST) if not getattr(ctx, "dry_run", False) else Path(ctx.raw_dir) / TEST
    errors: list = []
    verdicts: dict = {}
    per_cam: dict = {}
    fcache: dict = {}
    for cam in ctx.cameras:
        cres: dict = {"name": cam.get("name"), "label": label(cam), "kiyo_pro": bool(cam.get("is_kiyo"))}
        per_cam[cam["key"]] = cres
        vk = f"{GOAL}|{cam['key']}|mf"
        try:
            verdicts[vk] = run_camera(ctx, cam, cres, raw, soak, nrs, fcache, errors)
        except Exception as e:  # noqa: BLE001 - one camera's exception must not stop the others
            cres["exception"] = repr(e)
            errors.append({"camera": cam["key"], "camera_label": label(cam), "exception": repr(e)})
            ctx.log(f"{TEST}: {label(cam)}: exception {e!r}")
            v = rating.untested(f"{label(cam)}: exception {e!r}")
            v["restore"] = (cres.get("restore") or {}).get("restored")
            verdicts[vk] = v
    meas = {"quick": ck.quick(ctx), "soak_s": soak, "restarts": nrs, "cameras": per_cam,
            "arrivals": ck.arrivals_after(ctx, arr0),
            "thresholds": {"luma_tol": LUMA_TOL, "rb_tol": RB_TOL, "sharpness_info_tol": SHARP_INFO_TOL,
                           "readback_tolerance": "w_ctrl_effect.step_tol: one range step (>= 1) or 1 % of the span; "
                                                 "AE priority and power-line frequency exact",
                           "dark_luma": DARK_LUMA, "bright_luma": BRIGHT_LUMA, "rb_min_channel": RB_MIN_CHANNEL,
                           "gap_factor": GAP_FACTOR, "provisional": True},
            "timeline": {"reapply_ms": REAPPLY_MS, "first_sample_ms": FIRST_SAMPLE_MS,
                         "sample_every_s": SAMPLE_EVERY_S, "restart_measure_s": RESTART_MEASURE_S,
                         "restart_sample_every_s": RESTART_SAMPLE_EVERY_S, "metric_window_ms": METRIC_WIN_MS,
                         "save_every": SAVE_EVERY},
            "metrics": {"luma": "median of Pillow 'L' over the central 80 % (JPEG decoded at 1/4)",
                        "rgb": "channel means over the central 80 %", "rb_ratio": "mean R / mean B",
                        "sharpness": "common.imgmetrics.sharpness over the centre 50 % (informational)"},
            "readback_method": "in-stream samples are wincam schedule items '<control>=manual': before_value / "
                               "before_flags are the readback; the same value is re-set with the manual flag, so a "
                               "value drift stays visible",
            "c930e_note": "every stream re-applies every locked value 1.2 s after the first frame (C930e: sets made "
                          ">= 1 s after the first frame stick); needed_reapply names what the stream start changed",
            "lock": {"auto_off": list(DRIFT_CONTROLS), "fixed": FIXED_TARGETS,
                     "start_value": list(START_VALUE_CONTROLS)}}
    return results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)


# ------------------------------------------------------------------------------------------------------- offline
def rerate(doc: dict) -> dict:
    """Re-rate a stored W-NODRIFT result with the current thresholds (cameras that ran to a rating only; halted or
    skipped cameras keep their verdict)."""
    m = doc.get("measurements") or {}
    out_v, changes = {}, []
    for key, cres in (m.get("cameras") or {}).items():
        vk = f"{GOAL}|{key}|mf"
        old = (doc.get("verdicts") or {}).get(vk) or {}
        if cres.get("halted") or cres.get("capture_failed") or not cres.get("segments"):
            out_v[vk] = old
            continue
        v = rate(evaluate(cres), cres.get("label") or key)
        v["restore"] = (cres.get("restore") or {}).get("restored")
        out_v[vk] = v
        if old.get("rating") != v["rating"]:
            changes.append({"cell": vk, "from": old.get("rating"), "to": v["rating"]})
    return {"test": TEST, "utc": results.utc_now_iso(), "verdicts": out_v, "changes": changes,
            "thresholds": {"luma_tol": LUMA_TOL, "rb_tol": RB_TOL}}


def _main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "--rerate":
        rd = Path(argv[1])
        out = rerate(json.loads((rd / f"{TEST}.json").read_text(encoding="utf-8")))
        p = results.write_json(rd / "reanalysis" / f"{TEST}.json", out)
        print(json.dumps({"written": str(p), "changes": out["changes"]}, indent=1))
        return 0
    print("usage: w_nodrift.py --rerate <run_dir>   (live runs go through run_suite.py)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
