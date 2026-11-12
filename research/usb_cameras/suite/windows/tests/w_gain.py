"""W-GAIN: gain vs noise / detail / JPEG size, the in-step gain-limit rule, and the frame-rate ceiling (TP1 T1, T2, T4).

Plan: ``research/usb_cameras/docs/exposure_gain_tradeoff.md`` section 6 (T1, T2, T4) and section 5.2 + 5.2a (the
measured gain limit, Dom D9 2026-11-11). This is the part of those tests that runs unattended on the static scene
the cameras see overnight: a desk under steady room light, no grey card, no dark frames, no chart. The "card" is the
flat, low-gradient part of the scene (the 5.2a flat mask); detail is gradient energy on the textured part.

Per camera, sequentially (Kiyo Pro first, as ``ctx.cameras`` is ordered), in the suite's mode scope (MJPEG with
exactly 720 lines: the ~30 fps default mode, plus a ~60 fps 720-line mode where the camera has one):

1. Read the as-found control state (``wincam controls --read-only``, MF). Lock AE off (exposure manual at its current
   value), AF off at its current focus, AWB off holding its current value, AE priority 0 (one ``wincam controls
   --set ... --set-flags manual``); read the flags back. Everything else stays as found.
2. T4 (frame-rate ceiling): one MF capture per mode; ``--schedule`` steps exposure through -11..-2 (the camera's
   range where it is not log2 seconds: the generic 4c4a:4a55's -7..3) every T4_STEP_S s at gain minimum; delivered
   fps per step from the frames' QPC arrival times after a 1 s settle (least-squares, capkit.fps_from_rows). The
   measured ceiling is the highest step whose rate (and that of every shorter step) is within 1 % of the camera's
   own short-exposure rate; the doc expects -5 at 30 fps and -6 at 60 fps.
3. Grid (T1 + T2): ONE MF capture per exposure row (``wincam capture --save all --controls-before ... --schedule
   ...``). Every cell sets exposure and gain on the streaming IMFMediaSource (in-stream sets; the first cell is set
   FIRST_SET_MS >= 1 s after the first frame, so the C930e's stream-start reset of exposure and gain is behind it),
   wincam reads each set back, the cell waits SETTLE_S, then the next GRID_FRAMES consecutive frames (the camera's
   JPEG bytes) are the cell. The next cell's set reads the values before it changes them, so "held through the
   cell" is checked too (a final ``=manual`` keep-read closes the last cell). A cell whose set did not read back,
   whose value changed during the cell, or that got too few frames is re-applied in one more capture (generic
   handling of the C930e reset). Exposure rows -11..-5 (generic: its 7 lowest steps) x gain at 0/10/25/50/75/90/100 %
   of the read range (generic: every value). If a camera's planned grid exceeds GRID_BUDGET_S (~12 min), or the
   measured rows project past it, only -11, -9, -7, -5 are kept (recorded as ``reduced``).
   Per cell (central 80 % ROI): ROI mean / median luma, flat-mask mean luma, per-pixel temporal sigma over the cell's
   frames, rho = median sigma/mu over the flat mask, the row-mean (flicker) part (row-mean sigma, per-pixel sigma with
   row means removed, the share of variance it removed), the EMVA two-frame sigma, detail D = mean Sobel magnitude
   on textured pixels / their mean luma, motion fraction, clip fraction, JPEG bytes mean / p95 / max, delivered fps,
   strict-decode failures (simplejpeg strict=True). The flat and textured masks of an exposure row come from its
   gain-minimum cell (5.2a), so every gain at that exposure is measured on the same pixels.
   After analysis only the cell frames are kept (``cells.mjpeg`` + ``cells.jsonl`` in raw_dir); the full stream
   file is deleted (KEEP_FULL_STREAMS) because it is rebuildable bulk.
4. Reference cap per camera and exposure (6 T1 "Checking the in-step rule", with the 5.2a thresholds): the highest
   gain where rho <= 1.5 x rho(g_min) and D >= 0.85 x D(g_min), with every lower gain passing too; a cell above gain
   minimum must also raise the flat-mask luma by >= 3 % over gain minimum at its exposure (5.2a's third condition,
   added so the comparison with the rule is like for like: without it the generic camera, whose gain does nothing,
   would get a reference cap at its range maximum while the rule correctly stops at gain minimum). Two references:
   ``matched_luma`` (the task's definition: rho_ref and D_ref interpolated in log luma between the gain-minimum cells
   of all exposures, so each cell is compared with long exposure + no gain at the same brightness) and
   ``same_exposure`` (gain minimum at the same exposure: exactly what the 5.2a rule measures live). Plus whether rho
   rises monotonically with gain on every exposure row (3 % tolerance).
5. The 5.2a in-step rule, live, RULE_RUNS times per mode, in ONE MF stream (the rule leg: this module's
   ``--rule-leg`` child under one camera lock, like W-CTRL-EFFECT's DS leg): ``wincam capture --save all`` streams;
   each probe sets exposure / gain through the DirectShow filter in a concurrent ``wincam controls --api ds --set``
   (the W-AUTO "ds" path; MF schedules cannot react to frames), re-applies once when the readback differs, discards
   DISCARD_S of frames after the set returned, then reads the next frames live from frames.jsonl / frames.mjpeg.
   The algorithm is run as written: ceiling, exposure first (longest step <= band top with <= 1 % clipped, 3-frame
   luma probes), the 8-frame gain-minimum reference (flat + textured masks), then binary search on gain with
   8-frame probes, each probe valid when rho <= 1.5 rho_ref, D >= 0.85 D_ref and luma still rises (>= 3 % over gain
   minimum and not below the last valid probe), the motion guard (> 5 % of mask pixels changing > 10 levels -> retry,
   3 times, then ``gain_limit_unverified``), g_lim = the highest valid probe. One run ``as_written`` (ceiling = the
   frame period: -5 at 30 fps, -6 at 60 fps; for a camera whose exposure is not log2 seconds, T4's measured
   ceiling) records whether the night scene needs gain at all. The validation runs (RULE_RUNS = 10 in the ~30 fps
   mode, RULE_RUNS_EXTRA_MODE = 3 in the extra ~60 fps mode, to stay inside the hour) are ``forced``: the ceiling is
   set to the SHORTEST grid exposure whose gain-minimum cell still has a flat mask and is below the band (-9 / -10
   when the light allows), so gain is needed and the limit is exercised; when no exposure is below the band, the
   target band is raised instead. Pass: every forced run's g_lim lies within one probe step of the reference cap's
   grid bracket [cap, first failing grid gain] at that exposure, and rho is monotonic on the grid.
6. Restore the as-found state (manual controls: value + manual flag; auto controls: value + auto flag; w_auto's
   restore_state, verified by a read-only read, retried once) and record whether it worked.

Device faults: before each camera and before every capture / leg / control command the camera is checked with
``ctx.camera_gated(cam)``, ``ctx.camera_dead(cam)`` and the in-test fault record (capkit.device_fault). Any record
stops that camera's work for good (no retry, no re-probe, no re-open, no restore) and its verdicts become "untested:
device fault/dead". A capture whose result shows a device fault is reported to the gate (capkit.mark_device_fault).
The rule leg checks the gate before it starts; inside it, a set that reports ``device_not_answering`` or a capture
that dies ends the leg.

Every camera command goes through ``ctx.camcmd``. Tier 0 only (frame content and QPC arrival times; no UVC metadata,
no registry). Raw frames go to ``ctx.raw_test_dir(TEST)`` (outside the repo).

Verdict keys: ``gain_grid|<camera>|<mode>``, ``gain_rule|<camera>|<mode>``, ``fps_ceiling|<camera>|<mode>``.

Quick mode (``--quick``, read as the other tests do: ``capkit.quick``): 2 exposures x 3 gains, 16 frames per cell,
2 forced rule runs (no as-written run), 3 T4 steps around the expected ceiling. Optional overrides (``capkit.arg``):
``ctx.args.gain_frames``, ``gain_rule_runs``.

Offline tests: ``tests/test_w_gain_offline.py`` (synthetic frames, a fake ctx; no camera).
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
import suitectx  # noqa: E402
import w_auto as wa  # noqa: E402
import w_ctrl_effect as ce  # noqa: E402
from common import rating, results  # noqa: E402

TEST = "W-GAIN"

# ------------------------------------------------------------------------------------------------------- plan values
GAIN_FRACS = (0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0)
GAIN_FRACS_QUICK = (0.0, 0.50, 1.0)
EXP_GRID = tuple(range(-11, -4))               # -11 .. -5
EXP_REDUCED = (-11, -9, -7, -5)
EXP_QUICK = (-7, -5)
T4_EXP = tuple(range(-11, -1))                 # -11 .. -2
GRID_FRAMES, GRID_FRAMES_QUICK = 64, 16
RULE_RUNS, RULE_RUNS_QUICK = 10, 2
RULE_RUNS_EXTRA_MODE = 3                       # forced runs in the extra (~60 fps) mode: the 10x validation is per camera, at ~30 fps
T4_STEP_S, T4_SETTLE_S = 5.0, 1.0
FIRST_SET_MS = 1200                            # first in-stream set >= 1 s after the first frame (C930e rule)
LOCK_REAPPLY_MS = 600                          # in-stream re-apply of the AWB / AF / AE-priority locks
SETTLE_S = 0.5                                 # wait after a cell's set before its frames
CELL_MARGIN_S = 0.25
GRID_BUDGET_S = 12 * 60.0                      # per camera (all modes); beyond it: EXP_REDUCED rows only
KEEP_FULL_STREAMS = False                      # keep only the cell / probe frames in raw_dir

# ------------------------------------------------------------------------------------------------------- analysis
ROI = (0.1, 0.1, 0.9, 0.9)                     # central 80 % (l, t, r, b)
FLAT_GRAD = 6.0                                # Appendix A: Sobel magnitude of the mean frame, 9x9 box blur, < 6
BLUR_K = 9
MASK_LUMA = (30.0, 220.0)                      # 5.2a: luma 30-220 at gain minimum
MIN_MASK_PX = 2000
TEX_PCT = 90.0                                 # textured = top 10 % of the blurred gradient (unclipped pixels)
MIN_TEX_PX = 500
CLIP_LEVEL = 250.0
MASK_CLIPPED = 0.10                            # > 10 % of mask pixels at >= 250: rho of that cell is not usable
RHO_MAX_RATIO = 1.5
D_MIN_RATIO = 0.85
RISE_MIN = 1.03
MONO_TOL = 0.97
MATCH_EXTRAP = 0.05                            # matched-luma reference: up to 5 % beyond the gain-minimum span

# ------------------------------------------------------------------------------------------------------- the rule
BAND = (95.0, 125.0)
TARGET = 110.0
CLIP_MAX = 0.01
ACCEPT_DARK = 60.0
MOTION_DELTA, MOTION_FRAC, MOTION_RETRIES = 10, 0.05, 3
PROBE_FRAMES, LUMA_FRAMES, DISCARD_S = 8, 3, 0.2
MAX_EXP_PROBES, MAX_GAIN_PROBES = 7, 10
RULE_RUN_BUDGET_S = 45.0                       # per rule run (~11 probes x ~2 s expected)
LEG_BUDGET_MAX_S = 540.0                       # whole rule leg (one MF stream per mode)
DS_SET_TIMEOUT_S = 20.0

# ------------------------------------------------------------------------------------------------------- estimate
CAP_OVERHEAD_S = 7.0                           # camcmd (uv + camlock) + MF open / release per capture
CMD_S = 4.0                                    # one control read / set command
DS_SET_S = 1.5                                 # one DS side-channel set inside the rule leg
ANALYSE_CELL_S = 0.6
FPS_TOL = 0.01

STATE_NAMES = ("exposure", "gain", "white_balance", "focus", "auto_exposure_priority")
UNTESTED_DEAD = "untested: device fault/dead"


# ================================================================================================== small helpers
def frames_per_cell(ctx) -> int:
    return int(ck.arg(ctx, "gain_frames", GRID_FRAMES, GRID_FRAMES_QUICK))


def rule_runs(ctx) -> int:
    return int(ck.arg(ctx, "gain_rule_runs", RULE_RUNS, RULE_RUNS_QUICK))


def cam_text(cam: dict) -> str:
    return ck.cam_label(cam) + (" [Kiyo Pro]" if cam.get("is_kiyo") else "")


def rng_of(c: dict | None) -> dict:
    c = c or {}
    return {k: c.get(k) for k in ("min", "max", "step", "default")}


def log2_units(r: dict) -> bool:
    """Exposure in log2 seconds (MF / DirectShow convention, -7 = 1/128 s). The generic 4c4a's -7..3 is not
    ("-2" and "1" still ran at 25.7 fps), so a range that reaches 0 or above is treated as unknown units."""
    lo, hi = r.get("min"), r.get("max")
    return isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and -16 <= lo and hi <= -1


def snap(v: float, r: dict) -> int:
    lo, hi, st = r["min"], r["max"], r.get("step") or 1
    v = max(lo, min(hi, v))
    return int(lo + round((v - lo) / st) * st)


def grid_gains(r: dict, quick: bool) -> list[int]:
    lo, hi, st = r["min"], r["max"], r.get("step") or 1
    n = int((hi - lo) // st) + 1
    if n <= 8:
        vals = [lo + i * st for i in range(n)]
        return [vals[0], vals[len(vals) // 2], vals[-1]] if quick and len(vals) > 3 else vals
    out: list[int] = []
    for f in (GAIN_FRACS_QUICK if quick else GAIN_FRACS):
        g = snap(lo + f * (hi - lo), r)
        if g not in out:
            out.append(g)
    return out


def grid_exposures(r: dict, quick: bool) -> list[int]:
    lo, hi, st = r["min"], r["max"], r.get("step") or 1
    if log2_units(r):
        want = EXP_QUICK if quick else EXP_GRID
        vals = [v for v in want if lo <= v <= hi]
        return vals or [lo + i * st for i in range(7 if not quick else 2) if lo + i * st <= hi]
    vals = [lo + i * st for i in range(7) if lo + i * st <= hi]
    return [vals[0], vals[min(2, len(vals) - 1)]] if quick else vals


def reduced_exposures(exps: list[int], r: dict) -> list[int]:
    if log2_units(r):
        red = [v for v in exps if v in EXP_REDUCED]
        return red or exps[::2]
    return exps[::2]


def expected_ceiling(fps: float) -> int:
    """Frame-period ceiling: the largest 2^v <= 1/fps (-5 at 30 fps, -6 at 60 fps)."""
    return int(math.floor(math.log2(1.0 / fps) + 1e-9))


def t4_exposures(r: dict, fps: float, quick: bool) -> list[int]:
    lo, hi, st = r["min"], r["max"], r.get("step") or 1
    if log2_units(r):
        if quick:
            c = expected_ceiling(fps)
            return [v for v in (c - 1, c, c + 1) if lo <= v <= hi]
        return [v for v in T4_EXP if lo <= v <= hi]
    vals = [lo + i * st for i in range(int((hi - lo) // st) + 1)]
    return [vals[0], vals[len(vals) // 2], vals[-1]] if quick else vals


def expected_fps(mode, exp: int, r: dict) -> float:
    """The rate a cell is planned with (conservative): the mode rate, or 1/exposure when that is lower."""
    f = mode.fps
    if log2_units(r):
        f = min(f, 1.0 / (2.0 ** exp))
        return 0.9 * f
    return 0.75 * f


def halt(ctx, cam: dict) -> dict | None:
    """The record that stops this camera's work: gated at test start, dead (Kiyo Pro dead rule), or faulted during
    this test. None = the camera may be used."""
    checks = (("camera_gated", getattr(ctx, "camera_gated", None)),
              ("camera_dead", getattr(ctx, "camera_dead", lambda c: None)))
    for name, fn in checks:
        if not callable(fn):
            continue
        try:
            rec = fn(cam)
        except Exception:  # noqa: BLE001
            rec = None
        if rec:
            return {"source": name, **(rec if isinstance(rec, dict) else {"detail": rec})}
    f = ck.device_fault(ctx, cam)
    if f:
        return {"source": "camera_faulted", **f}
    return None


def dead_verdict(ctx, cam: dict, rec: dict | None, evidence: dict | None = None) -> dict:
    rec = rec or {}
    v = rating.device_fault_untested({"utc": rec.get("since_utc") or rec.get("utc"), "test": rec.get("test"),
                                      "mode": rec.get("mode"), "code": rec.get("code"), **rec},
                                     evidence=evidence)
    why = ctx.fault_reason(cam) if callable(getattr(ctx, "fault_reason", None)) else None
    v["note"] = f"{UNTESTED_DEAD} ({why or rec.get('reason') or rec.get('source') or 'device fault'})"
    v["summary_label"] = "untested (device fault/dead)"
    return v


def verdict(r: str, criteria: list, evidence, note: str | None = None, label: str | None = None) -> dict:
    v = {"rating": r, "criteria": criteria, "evidence": evidence}
    if note:
        v["note"] = note
    if label:
        v["summary_label"] = label
    return v


def crit(name: str, met, detail=None) -> dict:
    return {"criterion": name, "met": met, "detail": detail}


def _rel(ctx, p: Path) -> str:
    try:
        return str(Path(p).relative_to(ctx.out_dir)).replace("\\", "/")
    except ValueError:
        return str(p)


# ================================================================================================== image analysis
def decode_y(data: bytes):
    """(Y uint8 HxW or None, strict_ok, error). The camera's JPEG decoded to luma with simplejpeg (libjpeg-turbo);
    strict=True first (any libjpeg warning fails), lenient on failure so the frame is still measured."""
    import numpy as np  # noqa: PLC0415
    import simplejpeg  # noqa: PLC0415
    try:
        y = simplejpeg.decode_jpeg(data, colorspace="GRAY", strict=True)
        return np.ascontiguousarray(y[..., 0]), True, None
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {str(e)[:120]}"
    try:
        y = simplejpeg.decode_jpeg(data, colorspace="GRAY", strict=False)
        return np.ascontiguousarray(y[..., 0]), False, err
    except Exception as e2:  # noqa: BLE001
        return None, False, f"{err}; lenient: {type(e2).__name__}: {str(e2)[:120]}"


def roi_crop(y):
    h, w = y.shape[:2]
    l, t, r, b = ROI
    return y[int(t * h):max(int(t * h) + 1, int(b * h)), int(l * w):max(int(l * w) + 1, int(r * w))]


def sobel_mag(m):
    """3x3 Sobel gradient magnitude (cv2.Sobel ksize=3 kernels), edge padding."""
    import numpy as np  # noqa: PLC0415
    p = np.pad(m.astype(np.float32), 1, mode="edge")
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    return np.hypot(gx, gy)


def box_blur(a, k: int = BLUR_K):
    """k x k mean filter (reflect padding), via an integral image."""
    import numpy as np  # noqa: PLC0415
    r = k // 2
    p = np.pad(a.astype(np.float64), r, mode="reflect")
    c = np.cumsum(np.cumsum(p, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    h, w = a.shape
    s = c[k:k + h, k:k + w] - c[:h, k:k + w] - c[k:k + h, :w] + c[:h, :w]
    return (s / (k * k)).astype(np.float32)


def make_masks(mean) -> dict:
    """5.2a masks from a (gain-minimum) mean frame of the ROI: flat = blurred Sobel < FLAT_GRAD and luma 30-220;
    textured = blurred Sobel in the top 10 % and luma 8-247."""
    import numpy as np  # noqa: PLC0415
    g = box_blur(sobel_mag(mean))
    flat = (g < FLAT_GRAD) & (mean >= MASK_LUMA[0]) & (mean <= MASK_LUMA[1])
    unclipped = (mean >= 8) & (mean <= 247)
    thr = float(np.percentile(g[unclipped], TEX_PCT)) if unclipped.any() else float("inf")
    tex = (g >= thr) & unclipped
    return {"flat": flat, "tex": tex, "flat_px": int(flat.sum()), "tex_px": int(tex.sum()),
            "tex_threshold": round(thr, 3) if math.isfinite(thr) else None,
            "flat_ok": int(flat.sum()) >= MIN_MASK_PX, "tex_ok": int(tex.sum()) >= MIN_TEX_PX}


def _r(x, n=5):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


def stack_stats(ys: list, masks: dict | None = None) -> dict:
    """Noise / detail / luma of consecutive frames (each a full-frame Y array; the central 80 % ROI is used).
    ``masks`` = the gain-minimum masks of this exposure (5.2a); None = derive them from these frames."""
    import numpy as np  # noqa: PLC0415
    n = len(ys)
    if n < 2:
        return {"n_frames": n, "error": "need >= 2 frames"}
    stack = np.stack([roi_crop(y) for y in ys]).astype(np.uint8)
    _, h, w = stack.shape
    rows = stack.mean(axis=2, dtype=np.float64)               # (n, h) row means
    dev = (rows - rows.mean(axis=0)).astype(np.float32)
    mean = np.empty((h, w), np.float32)
    sd = np.empty((h, w), np.float32)
    sd_rr = np.empty((h, w), np.float32)
    for r0 in range(0, h, 64):
        blk = stack[:, r0:r0 + 64, :].astype(np.float32)
        mean[r0:r0 + 64] = blk.mean(axis=0)
        sd[r0:r0 + 64] = blk.std(axis=0, ddof=1)
        blk -= dev[:, r0:r0 + 64, None]
        sd_rr[r0:r0 + 64] = blk.std(axis=0, ddof=1)
    own = masks is None
    if own:
        masks = make_masks(mean)
    flat, tex = masks["flat"], masks["tex"]
    out: dict = {"n_frames": n, "roi_shape": [int(h), int(w)], "own_masks": own,
                 "mask_px": masks["flat_px"], "tex_px": masks["tex_px"],
                 "roi_luma_mean": _r(mean.mean(), 3), "roi_luma_median": _r(np.median(mean), 3),
                 "clip_frac": _r((mean >= CLIP_LEVEL).mean(), 6)}
    win = flat if masks["flat_ok"] else ((mean >= MASK_LUMA[0]) & (mean <= MASK_LUMA[1]))
    if win.any():
        d = np.abs(np.diff(stack[:, win].astype(np.int16), axis=0)) > MOTION_DELTA
        fr = d.mean(axis=1)
        out["motion_frac_max"], out["motion_frac_mean"] = _r(fr.max(), 6), _r(fr.mean(), 6)
    else:
        out["motion_frac_max"] = out["motion_frac_mean"] = None
    fmeans = stack.reshape(n, -1).mean(axis=1)
    out["frame_mean_sigma"] = _r(fmeans.std(ddof=1), 5)
    out["rowmean_sigma"] = _r(np.median(dev.std(axis=0, ddof=1)), 5)
    if masks["flat_ok"]:
        mu = mean[flat]
        s = sd[flat]
        ok = mu > 0
        out["mu_mask"] = _r(mu.mean(), 4)
        out["mask_clip_frac"] = _r((mu >= CLIP_LEVEL).mean(), 6)
        out["sigma_flat"] = _r(np.median(s), 5)
        out["sigma_flat_row_removed"] = _r(np.median(sd_rr[flat]), 5)
        sf, srr = out["sigma_flat"], out["sigma_flat_row_removed"]
        out["flicker_variance_share"] = _r(max(0.0, 1.0 - (srr / sf) ** 2), 4) if sf else None
        out["rho"] = _r(np.median(s[ok] / mu[ok]), 7) if ok.any() else None
        two = [float((stack[i + 1][flat].astype(np.float32) - stack[i][flat]).std()) / math.sqrt(2)
               for i in range(min(n - 1, 16))]
        out["sigma_two_frame"] = _r(sum(two) / len(two), 5)
    else:
        out.update(mu_mask=None, mask_clip_frac=None, sigma_flat=None, sigma_flat_row_removed=None,
                   flicker_variance_share=None, rho=None, sigma_two_frame=None,
                   mask_note=f"flat mask has {masks['flat_px']} px (< {MIN_MASK_PX}): too dark / bright / textured")
    if masks["tex_ok"]:
        lt = float(mean[tex].mean())
        out["D"] = _r(float(sobel_mag(mean)[tex].mean()) / lt, 6) if lt > 0 else None
    else:
        out["D"] = None
    out["_masks"] = masks
    return out


def luma_stats(ys: list) -> dict:
    """Exposure probe: median luma of the central 80 % of the mean frame, and its clipped fraction."""
    import numpy as np  # noqa: PLC0415
    m = np.mean(np.stack([roi_crop(y).astype(np.float32) for y in ys]), axis=0)
    return {"n_frames": len(ys), "roi_luma_median": _r(np.median(m), 3), "roi_luma_mean": _r(m.mean(), 3),
            "clip_frac": _r((m >= CLIP_LEVEL).mean(), 6)}


def public(st: dict) -> dict:
    return {k: v for k, v in st.items() if not k.startswith("_")}


# ================================================================================================== grid
def lock_items(locks: dict) -> list[str]:
    return [f"{k}={v}" for k, v in locks.items()]


def row_plan(mode, exp: int, gains: list[int], locks: dict, nframes: int, r_exp: dict, slot_mult: float = 1.0) -> dict:
    """MF schedule of one exposure row: locks re-applied at LOCK_REAPPLY_MS, then per cell exposure + gain at its
    set time, SETTLE_S, the cell's frames, a margin; a final keep-read closes the last cell."""
    fps = expected_fps(mode, exp, r_exp)
    slot_ms = int(round((SETTLE_S + nframes / fps + CELL_MARGIN_S) * slot_mult * 1000))
    items = [f"{LOCK_REAPPLY_MS}:{x}" for x in lock_items(locks)]
    cells, t = [], FIRST_SET_MS
    for g in gains:
        items += [f"{t}:exposure={exp}", f"{t}:gain={g}"]
        cells.append({"exposure": exp, "gain": g, "set_ms": t})
        t += slot_ms
    items += [f"{t}:exposure=manual", f"{t}:gain=manual"]
    before = ",".join(lock_items(locks) + [f"exposure={exp}", f"gain={gains[0]}"])
    return {"exposure": exp, "gains": list(gains), "cells": cells, "end_ms": t, "slot_ms": slot_ms,
            "seconds": round(t / 1000.0 + 0.3, 3), "controls_before": before, "schedule": ";".join(items),
            "expected_fps": round(fps, 3)}


def _ev_for(events: list, name: str, at_ms: float) -> dict | None:
    for e in events:
        if str(e.get("control", "")).endswith(name) and abs(float(e.get("at_ms") or -1e9) - at_ms) < 0.5:
            return e
    return None


def read_frames_bytes(od: Path, rows: list[dict]) -> list[bytes]:
    p = Path(od) / "frames.mjpeg"
    out = []
    if not p.exists():
        return out
    with p.open("rb") as f:
        for r in rows:
            f.seek(int(r["mjpeg_offset"]))
            out.append(f.read(int(r["mjpeg_len"])))
    return out


def analyse_row(od: Path, summary: dict, plan: dict, nframes: int, ranges: dict, ref_masks: dict | None) -> list[dict]:
    """Per-cell records of one row capture (frames, readbacks, held, metrics). The first cell is gain minimum; its
    masks are used for the whole row (``ref_masks`` given = a re-applied row reuses the original masks)."""
    import numpy as np  # noqa: PLC0415
    rows = [r for r in ck.load_frames(od) if isinstance(r.get("qpc_ns"), (int, float))]
    events = (summary or {}).get("schedule") or []
    out, masks = [], ref_masks
    cells = plan["cells"]
    for i, c in enumerate(cells):
        ee, eg = _ev_for(events, "exposure", c["set_ms"]), _ev_for(events, "gain", c["set_ms"])
        nxt_ms = cells[i + 1]["set_ms"] if i + 1 < len(cells) else plan["end_ms"]
        ne, ng = _ev_for(events, "exposure", nxt_ms), _ev_for(events, "gain", nxt_ms)
        rec: dict = {"exposure": c["exposure"], "gain": c["gain"], "set_ms": c["set_ms"]}
        rb_e = ce.held((ee or {}).get("readback_value"), (ee or {}).get("readback_flags"), c["exposure"],
                       ranges["exposure"]) if ee else None
        rb_g = ce.held((eg or {}).get("readback_value"), (eg or {}).get("readback_flags"), c["gain"],
                       ranges["gain"]) if eg else None
        h_e = ce.held((ne or {}).get("before_value"), (ne or {}).get("before_flags"), c["exposure"],
                      ranges["exposure"]) if ne else None
        h_g = ce.held((ng or {}).get("before_value"), (ng or {}).get("before_flags"), c["gain"],
                      ranges["gain"]) if ng else None
        rec["readback"] = {"exposure": (ee or {}).get("readback_value"), "gain": (eg or {}).get("readback_value"),
                           "exposure_ok": rb_e, "gain_ok": rb_g,
                           "before_set": {"exposure": (ee or {}).get("before_value"),
                                          "gain": (eg or {}).get("before_value")}}
        rec["held_through_cell"] = {"exposure": h_e, "gain": h_g,
                                    "value_at_end": {"exposure": (ne or {}).get("before_value"),
                                                     "gain": (ng or {}).get("before_value")}}
        rec["readback_ok"] = bool(rb_e) and bool(rb_g)
        rec["held"] = None if (h_e is None and h_g is None) else bool(h_e is not False and h_g is not False)
        done = max([e.get("done_qpc_ns") or e.get("applied_qpc_ns") or 0 for e in (ee, eg) if e] or [0])
        nxt_t = min([e.get("applied_qpc_ns") for e in (ne, ng) if e and e.get("applied_qpc_ns")] or [float("inf")])
        if not done:
            rec.update(n_frames=0, valid=False, why="set event missing (capture failed before this cell?)")
            out.append(rec)
            continue
        start = done + SETTLE_S * 1e9
        win = [r for r in rows if start <= r["qpc_ns"] < nxt_t][:nframes]
        win = [r for r in win if r.get("mjpeg_offset") is not None and r.get("mjpeg_len")]
        rec["frames"] = [{"seq": r.get("seq"), "qpc_ns": r["qpc_ns"], "mjpeg_offset": r["mjpeg_offset"],
                          "mjpeg_len": r["mjpeg_len"], "bytes": r.get("bytes")} for r in win]
        rec["n_frames"] = len(win)
        rec["settle_ms"] = round((win[0]["qpc_ns"] - done) / 1e6, 1) if win else None
        bys = [int(r.get("bytes") or r.get("mjpeg_len") or 0) for r in win]
        if bys:
            a = np.asarray(bys, dtype=np.float64)
            rec["bytes"] = {"mean": round(float(a.mean()), 1), "p95": round(float(np.percentile(a, 95)), 1),
                            "max": int(a.max())}
        rec["fps"] = _r(ck.fps_from_rows(win, skip_frac=0.0), 3) if len(win) >= 5 else None
        ys, strict_fail, decode_fail, errs = [], 0, 0, []
        for data in read_frames_bytes(od, win):
            y, sok, err = decode_y(data)
            if not sok:
                strict_fail += 1
                if err and len(errs) < 3:
                    errs.append(err)
            if y is None:
                decode_fail += 1
                continue
            ys.append(y)
        rec["strict_decode_failures"], rec["decode_failures"] = strict_fail, decode_fail
        if errs:
            rec["decode_errors"] = errs
        st = stack_stats(ys, masks) if len(ys) >= 2 else {"error": "fewer than 2 decodable frames"}
        if i == 0 and masks is None and st.get("_masks") is not None:
            masks = st["_masks"]
        rec["metrics"] = public(st)
        rec["valid"] = bool(rec["readback_ok"] and rec["held"] is not False and len(win) >= nframes
                            and decode_fail == 0 and "error" not in st)
        if not rec["valid"]:
            rec["why"] = ", ".join(w for w, bad in (("set did not read back", not rec["readback_ok"]),
                                                     ("value changed during the cell", rec["held"] is False),
                                                     (f"{len(win)}/{nframes} frames", len(win) < nframes),
                                                     ("undecodable frames", decode_fail > 0)) if bad) or st.get("error")
        out.append(rec)
    if out:
        out[0]["_masks"] = masks
    return out


def compact_cells(od: Path, cells: list[dict]) -> dict:
    """Keep the cell frames only: cells.mjpeg + cells.jsonl; the full stream file is deleted (KEEP_FULL_STREAMS)."""
    src = Path(od) / "frames.mjpeg"
    if not src.exists():
        return {"kept": None, "reason": "no frames.mjpeg"}
    n = 0
    with src.open("rb") as f, (Path(od) / "cells.mjpeg").open("wb") as fo, \
            (Path(od) / "cells.jsonl").open("w", encoding="utf-8") as fj:
        for ci, c in enumerate(cells):
            for fr in c.get("frames") or []:
                f.seek(int(fr["mjpeg_offset"]))
                b = f.read(int(fr["mjpeg_len"]))
                fj.write(json.dumps({"cell": ci, "exposure": c.get("exposure"), "gain": c.get("gain"),
                                     "seq": fr.get("seq"), "qpc_ns": fr.get("qpc_ns"), "bytes": fr.get("bytes"),
                                     "mjpeg_offset": fo.tell(), "mjpeg_len": len(b)}) + "\n")
                fo.write(b)
                n += 1
    deleted = False
    if not KEEP_FULL_STREAMS:
        try:
            src.unlink()
            deleted = True
        except OSError:
            pass
    return {"kept": n, "file": "cells.mjpeg", "full_stream_deleted": deleted}


def capture_row(ctx, cam, mode, plan: dict, od: Path, timeout_ms: int = 5000) -> tuple[dict, dict]:
    extra = ["--controls-before", plan["controls_before"], "--schedule", plan["schedule"]]
    s, r = ck.wincam_capture(ctx, cam, mode, od, seconds=plan["seconds"], save="all", timeout_ms=timeout_ms,
                             extra=extra)
    return s or {}, r


def capture_fault(ctx, cam, mode, s: dict, r: dict) -> dict | None:
    flt = ck.fault_from_result("mf", s, r)
    if flt and flt.get("kind") != "gated":
        ck.mark_device_fault(ctx, cam, TEST, mode.text if mode else None, "mf", flt)
    return flt


# ================================================================================================== caps
def _rows_by_exp(cells: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for c in cells:
        out.setdefault(c["exposure"], []).append(c)
    for v in out.values():
        v.sort(key=lambda c: c["gain"])
    return out


def _usable(c: dict) -> bool:
    m = c.get("metrics") or {}
    return bool(c.get("valid")) and m.get("rho") is not None and m.get("D") is not None and \
        (m.get("mask_clip_frac") or 0) <= MASK_CLIPPED


def _cap_walk(cells: list[dict], judge) -> dict:
    """Highest gain from gain minimum upward with every cell passing ``judge`` (True / False / None=unknown)."""
    steps, cap, next_fail, stop = [], None, None, None
    for c in cells:
        ok, det = judge(c)
        steps.append({"gain": c["gain"], "pass": ok, **det})
        if stop:
            continue
        if ok is True:
            cap = c["gain"]
        elif ok is False:
            next_fail, stop = c["gain"], "fail"
        else:
            stop = "unknown"
    return {"cap": cap, "next_fail": next_fail, "stopped_by": stop, "cells": steps,
            "status": "ok" if cap is not None else "unknown"}


def same_exposure_caps(cells: list[dict]) -> dict:
    """Per exposure: ratios against the gain-minimum cell of the SAME exposure (the 5.2a measurement)."""
    out = {}
    for e, row in sorted(_rows_by_exp(cells).items()):
        ref = row[0]
        if not _usable(ref):
            out[str(e)] = {"cap": None, "status": "unknown", "reason": "gain-minimum cell has no usable rho / D "
                                                                       f"({ref.get('why') or (ref.get('metrics') or {}).get('mask_note')})"}
            continue
        r0, d0, m0 = ref["metrics"]["rho"], ref["metrics"]["D"], ref["metrics"]["mu_mask"]

        def judge(c, r0=r0, d0=d0, m0=m0, g0=ref["gain"]):
            if not _usable(c):
                return None, {"why": c.get("why") or "no usable rho / D"}
            m = c["metrics"]
            rr, dr = m["rho"] / r0 if r0 else None, m["D"] / d0 if d0 else None
            resp = m["mu_mask"] / m0 if m0 else None
            ok = rr is not None and dr is not None and rr <= RHO_MAX_RATIO and dr >= D_MIN_RATIO and \
                (c["gain"] == g0 or (resp is not None and resp >= RISE_MIN))
            return ok, {"rho_ratio": _r(rr, 4), "d_ratio": _r(dr, 4), "gain_response": _r(resp, 4)}
        out[str(e)] = _cap_walk(row, judge)
        out[str(e)]["reference"] = {"gain": ref["gain"], "rho": r0, "D": d0, "mu_mask": m0}
    return out


def matched_luma_refs(cells: list[dict]) -> list[tuple[float, float, float, int]]:
    """(log luma, rho, D, exposure) of every usable gain-minimum cell, sorted by luma."""
    refs = []
    for e, row in _rows_by_exp(cells).items():
        c = row[0]
        if _usable(c) and (c["metrics"].get("mu_mask") or 0) > 0:
            refs.append((math.log(c["metrics"]["mu_mask"]), c["metrics"]["rho"], c["metrics"]["D"], e))
    refs.sort()
    return refs


def interp_ref(refs: list, mu: float) -> tuple[float | None, float | None, str]:
    if not refs or mu is None or mu <= 0:
        return None, None, "no reference"
    x = math.log(mu)
    lo, hi = refs[0][0], refs[-1][0]
    tol = math.log(1 + MATCH_EXTRAP)
    if x < lo - tol or x > hi + tol:
        return None, None, f"luma {mu:.1f} outside the gain-minimum span {math.exp(lo):.1f}-{math.exp(hi):.1f}"
    if x <= lo:
        return refs[0][1], refs[0][2], f"nearest (exposure {refs[0][3]})"
    if x >= hi:
        return refs[-1][1], refs[-1][2], f"nearest (exposure {refs[-1][3]})"
    for a, b in zip(refs, refs[1:]):
        if a[0] <= x <= b[0]:
            f = (x - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
            return a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), f"interpolated (exposures {a[3]}, {b[3]})"
    return None, None, "no bracket"


def matched_luma_caps(cells: list[dict]) -> dict:
    """Per exposure: ratios against long exposure + gain minimum at the same flat-mask luma (6 T1, at matched luma)."""
    refs = matched_luma_refs(cells)
    out = {}
    for e, row in sorted(_rows_by_exp(cells).items()):
        m_min = (row[0].get("metrics") or {}).get("mu_mask") if _usable(row[0]) else None

        def judge(c, m_min=m_min, g0=row[0]["gain"]):
            if not _usable(c):
                return None, {"why": c.get("why") or "no usable rho / D"}
            m = c["metrics"]
            r0, d0, how = interp_ref(refs, m.get("mu_mask"))
            if r0 is None:
                return None, {"why": how}
            rr, dr = m["rho"] / r0, m["D"] / d0
            resp = m["mu_mask"] / m_min if m_min else None
            ok = rr <= RHO_MAX_RATIO and dr >= D_MIN_RATIO and (c["gain"] == g0 or (resp is not None and
                                                                                   resp >= RISE_MIN))
            return bool(ok), {"rho_ratio": _r(rr, 4), "d_ratio": _r(dr, 4), "gain_response": _r(resp, 4),
                              "reference": how}
        out[str(e)] = _cap_walk(row, judge)
    return {"per_exposure": out, "references": [{"exposure": e, "mu_mask": _r(math.exp(x), 3), "rho": r, "D": d}
                                                for x, r, d, e in refs]}


def rho_monotonic(cells: list[dict]) -> dict:
    per, all_ok, n = {}, True, 0
    for e, row in sorted(_rows_by_exp(cells).items()):
        vals = [(c["gain"], c["metrics"]["rho"]) for c in row if _usable(c)]
        if len(vals) < 3 or row[0]["gain"] != vals[0][0]:
            per[str(e)] = {"monotonic": None, "points": vals, "why": "fewer than 3 usable cells from gain minimum"}
            continue
        dips = [(g2, round(b / a, 4)) for (g1, a), (g2, b) in zip(vals, vals[1:]) if b < a * MONO_TOL]
        ok = not dips
        per[str(e)] = {"monotonic": ok, "points": vals, "dips": dips}
        all_ok = all_ok and ok
        n += 1
    return {"monotonic": all_ok if n else None, "rows_checked": n, "tolerance": MONO_TOL, "per_exposure": per}


# ================================================================================================== the rule (pure)
def _snap_gain(v: float, lo: int, st: int) -> int:
    return int(lo + round((v - lo) / st) * st)


def run_rule(cam, p: dict, clock=time.perf_counter) -> dict:
    """The exposure-step algorithm of 5.2 + 5.2a, run once against ``cam`` (``probe(exposure, gain, n, discard_s)`` /
    ``more(n)``, each returning {"ok", "ys", "set", "error", ...}). Returns the run record."""
    t0 = clock()
    g_min, g_max, g_st = int(p["g_min"]), int(p["g_max"]), int(p.get("g_step") or 1)
    band_lo, band_hi = p.get("band") or BAND
    v_min, v_max = int(p["v_min"]), int(p["v_max"])
    probes: list[dict] = []
    flags: list[str] = []
    warnings: list[str] = []
    res: dict = {"label": p.get("label"), "params": {k: p.get(k) for k in ("v_ceil", "band", "g_min", "g_max",
                                                                          "g_step", "v_min", "v_max", "label",
                                                                          "forced_by")},
                 "probes": probes, "flags": flags, "warnings": warnings}
    deadline = p.get("deadline")

    def over() -> bool:
        return bool(deadline) and clock() > deadline

    def finish(**kw) -> dict:
        res.update(kw)
        res["time_s"] = round(clock() - t0, 3)
        res["n_probes"] = len(probes)
        res["n_exposure_probes"] = sum(1 for x in probes if x["phase"] == "exposure")
        res["n_gain_probes"] = sum(1 for x in probes if x["phase"] == "gain")
        res["n_motion_retries"] = sum(x.get("retries", 0) for x in probes)
        return res

    def measure(phase: str, v: int, g: int, n: int, masks=None, luma_only=False) -> dict:
        """One probe with the motion guard (retry up to MOTION_RETRIES on the next frames)."""
        rec: dict = {"phase": phase, "exposure": v, "gain": g, "retries": 0, "attempts": []}
        pr = cam.probe(v, g, n, p.get("discard_s", DISCARD_S))
        for attempt in range(MOTION_RETRIES + 1):
            if attempt:
                pr = cam.more(n)
                rec["retries"] = attempt
            if not pr.get("ok"):
                rec.update(ok=False, error=pr.get("error"), set=pr.get("set"))
                return rec
            if attempt == 0:
                rec["set"] = pr.get("set")
            st = luma_stats(pr["ys"]) if luma_only else stack_stats(pr["ys"], masks)
            rec["attempts"].append({k: pr.get(k) for k in ("seqs", "frames", "t_frames_s")})
            mf = st.get("motion_frac_max") if not luma_only else None
            if luma_only or mf is None or mf <= MOTION_FRAC:
                rec.update(ok=True, stats=st, motion=False)
                return rec
            rec["motion_frac_max"] = mf
        rec.update(ok=True, stats=st, motion=True)
        return rec

    def keep(rec: dict) -> dict:
        r2 = dict(rec)
        if "stats" in r2:
            r2["stats"] = public(r2["stats"])
        probes.append(r2)
        return rec

    # 2. ceiling
    v_ceil = int(p["v_ceil"])
    if v_ceil > v_max:
        v_ceil = v_max
    if v_ceil < v_min:
        flags.append("ceiling_below_device_min")
        warnings.append(f"camera cannot expose short enough: ceiling {p['v_ceil']} < device minimum {v_min}")
        v_ceil = v_min
    res["v_ceil_used"] = v_ceil
    # 4. exposure first: from the ceiling downwards, the longest step not above the band top and <= 1 % clipped
    v, chosen_v = v_ceil, None
    while v >= v_min and sum(1 for x in probes if x["phase"] == "exposure") < MAX_EXP_PROBES:
        if over():
            flags.append("run_deadline")
            return finish(error="run deadline", g_lim=None, gain=None, exposure=None)
        m = keep(measure("exposure", v, g_min, int(p.get("luma_frames", LUMA_FRAMES)), luma_only=True))
        if not m.get("ok"):
            return finish(error=m.get("error") or "probe failed", g_lim=None, gain=None, exposure=None)
        s = m["stats"]
        if s["roi_luma_median"] <= band_hi and s["clip_frac"] <= CLIP_MAX:
            chosen_v = v
            break
        v -= 1
    if chosen_v is None:
        chosen_v = max(v_min, v + 1)
        flags.append("too_bright_at_shortest_exposure")
        warnings.append(f"too bright even at exposure {chosen_v}")
    res["exposure"] = chosen_v
    # gain minimum reference (8 frames): flat + textured masks fixed for the step
    ref = measure("gain_ref", chosen_v, g_min, int(p.get("probe_frames", PROBE_FRAMES)))
    keep(ref)
    if not ref.get("ok"):
        return finish(error=ref.get("error") or "reference probe failed", g_lim=None, gain=g_min)
    rs = ref["stats"]
    if rs.get("error") or "_masks" not in rs:
        return finish(error=f"reference probe: {rs.get('error')}", g_lim=None, gain=g_min)
    res["luma_at_gain_min"] = rs.get("roi_luma_median")
    if ref.get("motion"):
        flags.append("gain_limit_unverified")
        warnings.append("hold still / clear the view: the gain-minimum reference moved")
        return finish(g_lim=g_min, gain=g_min, gain_needed=None, limit_reached=False, luma=rs.get("roi_luma_median"))
    if not rs["_masks"]["flat_ok"] or rs.get("rho") is None or rs.get("D") is None:
        flags.append("no_flat_mask" if not rs["_masks"]["flat_ok"] else "no_detail_mask")
        return finish(g_lim=g_min, gain=g_min, limit_reached=False, luma=rs.get("roi_luma_median"),
                      gain_needed=bool(rs.get("roi_luma_median", 0) < band_lo), rho_ref=rs.get("rho"),
                      d_ref=rs.get("D"))
    rho0, d0, mu0 = rs["rho"], rs["D"], rs["mu_mask"]
    res.update(rho_ref=rho0, d_ref=d0, mu_ref=mu0)
    if rs["roi_luma_median"] >= band_lo:
        return finish(gain_needed=False, gain=g_min, g_lim=None, limit_reached=False, luma=rs["roi_luma_median"],
                      note="luma in or above the band at gain minimum: no gain needed")
    res["gain_needed"] = True
    masks = rs["_masks"]
    lo, hi = g_min, g_max + g_st
    g_lim, glim_probe, last_mu, limit_hit, chosen_g = g_min, None, mu0, False, None
    valid_probes: list[dict] = []
    rise_fail = 0
    while hi - lo > g_st and sum(1 for x in probes if x["phase"] == "gain") < MAX_GAIN_PROBES:
        if over():
            flags.append("run_deadline")
            break
        g = _snap_gain(lo + (hi - lo) / 2.0, g_min, g_st)
        if g <= lo:
            g = lo + g_st
        if g >= hi:
            break
        m = measure("gain", chosen_v, g, int(p.get("probe_frames", PROBE_FRAMES)), masks=masks)
        if not m.get("ok"):
            keep(m)
            return finish(error=m.get("error") or "probe failed", g_lim=g_lim, gain=g_min)
        s = m["stats"]
        if m.get("motion"):
            keep(m)
            flags.append("gain_limit_unverified")
            warnings.append("hold still / clear the view: motion in every retry of a gain probe")
            break
        rr = s["rho"] / rho0 if s.get("rho") is not None else None
        dr = s["D"] / d0 if s.get("D") is not None else None
        rise = s["mu_mask"] / mu0 if s.get("mu_mask") else None
        chk = {"rho_ratio": _r(rr, 4), "d_ratio": _r(dr, 4), "gain_response": _r(rise, 4),
               "rho_ok": rr is not None and rr <= RHO_MAX_RATIO, "detail_ok": dr is not None and dr >= D_MIN_RATIO,
               "rise_ok": rise is not None and rise >= RISE_MIN and s["mu_mask"] >= last_mu * 0.99}
        m["checks"] = chk
        m["valid"] = bool(chk["rho_ok"] and chk["detail_ok"] and chk["rise_ok"])
        keep(m)
        if not m["valid"]:
            hi = g
            limit_hit = True
            rise_fail += 0 if chk["rise_ok"] else 1
            continue
        valid_probes.append(m)
        if g > g_lim:
            g_lim, glim_probe = g, m
        last_mu = s["mu_mask"]
        lum = s["roi_luma_median"]
        if lum > band_hi or s["clip_frac"] > CLIP_MAX:
            hi = g
        elif lum >= band_lo:
            chosen_g = g
            break
        else:
            lo = g
    if not valid_probes and rise_fail:
        flags.append("gain_ineffective")
    best = None
    for m in valid_probes:
        lum = m["stats"]["roi_luma_median"]
        if lum <= band_hi and (best is None or abs(lum - TARGET) < abs(best["stats"]["roi_luma_median"] - TARGET)):
            best = m
    gain = chosen_g if chosen_g is not None else (best["gain"] if best else g_min)
    luma = (best["stats"]["roi_luma_median"] if best else rs["roi_luma_median"]) if chosen_g is None else \
        next(m["stats"]["roi_luma_median"] for m in valid_probes if m["gain"] == chosen_g)
    converged_max = g_lim + g_st > g_max and not limit_hit
    out = {"gain": gain, "g_lim": g_lim, "luma": luma, "target_reached": chosen_g is not None,
           "limit_reached": bool(limit_hit or converged_max) and chosen_g is None and
                            "gain_limit_unverified" not in flags,
           "limit_is_range_max": bool(converged_max), "probe_step": max(g_st, hi - lo),
           "rho_at_glim": (glim_probe or {}).get("stats", {}).get("rho") if glim_probe else rho0,
           "rho_ratio": (glim_probe or {}).get("checks", {}).get("rho_ratio") if glim_probe else 1.0,
           "d_ratio": (glim_probe or {}).get("checks", {}).get("d_ratio") if glim_probe else 1.0,
           "gain_response": (glim_probe or {}).get("checks", {}).get("gain_response") if glim_probe else 1.0}
    if luma is not None and luma < band_lo:
        out["too_dark_factor"] = _r(TARGET / max(luma, 1e-6), 3)
        warnings.append(f"about {out['too_dark_factor']}x too dark at the ceiling: add light, or choose a slower "
                        "motion setting" + (" (luma >= 60: usable)" if luma >= ACCEPT_DARK else ""))
    return finish(**out)


# ================================================================================================== the rule leg (child)
class LiveCam:
    """The live camera inside the rule leg: an MF ``wincam capture --save all`` in the background, DirectShow
    side-channel sets in concurrent ``wincam controls --api ds --set`` processes, frames read live from
    frames.jsonl (flushed per frame) and frames.mjpeg (a frame is read once the NEXT frame's row exists, so its
    bytes are on disk)."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.od = Path(spec["out_dir"])
        self.t0 = time.perf_counter_ns()
        self.bg = None
        self.rows: list[dict] = []
        self._pos = 0
        self._tail = b""
        self.last_set: dict = {}
        self.next_idx = 0               # index into rows of the next unused frame
        self.fault: dict | None = None
        self.sets: list[dict] = []
        self.clock_mode = "qpc"

    # ---- process
    def start(self) -> None:
        from common import procutil  # noqa: PLC0415
        self.od.mkdir(parents=True, exist_ok=True)
        stop = Path(self.spec["stop_file"])
        try:
            stop.unlink()
        except OSError:
            pass
        argv = [str(a) for a in self.spec["capture_argv"]]
        import shutil  # noqa: PLC0415
        if argv and not Path(argv[0]).is_absolute():
            argv[0] = shutil.which(argv[0]) or argv[0]
        self.bg = procutil.Background(argv, stdout_path=self.od / "capture_stdout.json",
                                      stderr_path=self.od / "capture_stderr.txt").start()

    def alive(self) -> bool:
        return self.bg is not None and self.bg.running() and self.fault is None

    def stop(self) -> dict:
        Path(self.spec["stop_file"]).write_text("stop", encoding="ascii")
        cr = self.bg.stop(25.0) if self.bg else {}
        try:
            txt = (self.od / "capture_stdout.json").read_text(encoding="utf-8", errors="replace")
        except OSError:
            txt = ""
        s, _ = suitectx.parse_json_stdout({"stdout": txt})
        if s is None and (self.od / "summary.json").exists():
            try:
                s = json.loads((self.od / "summary.json").read_text(encoding="utf-8"))
            except ValueError:
                s = None
        return {"summary": s, "run": {k: cr.get(k) for k in ("rc", "timed_out", "killed", "elapsed_s",
                                                               "spawn_error", "stderr_tail")}}

    # ---- frames
    def _poll(self) -> None:
        p = self.od / "frames.jsonl"
        try:
            with p.open("rb") as f:
                f.seek(self._pos)
                data = f.read()
        except OSError:
            return
        if not data:
            return
        self._pos += len(data)
        buf = self._tail + data
        lines = buf.split(b"\n")
        self._tail = lines.pop()
        for ln in lines:
            ln = ln.strip()
            if ln:
                try:
                    self.rows.append(json.loads(ln))
                except ValueError:
                    pass

    def wait_first(self, timeout_s: float) -> bool:
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            self._poll()
            if self.rows:
                q = self.rows[0].get("qpc_ns")
                if not isinstance(q, (int, float)) or abs(q - time.perf_counter_ns()) > 60e9:
                    self.clock_mode = "arrival"     # QPC of the frames not comparable: use read order
                return True
            if self.bg is not None and not self.bg.running():
                return False
            time.sleep(0.02)
        return False

    def first_qpc(self):
        return self.rows[0].get("qpc_ns") if self.rows else None

    def _take(self, start_idx: int, n: int, timeout_s: float) -> dict:
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            self._poll()
            if len(self.rows) >= start_idx + n + 1:
                break
            if not self.alive():
                break
            time.sleep(0.01)
        if len(self.rows) < start_idx + n + 1:
            return {"ok": False, "error": f"frames did not arrive ({len(self.rows) - start_idx} of {n + 1} after "
                                          f"{timeout_s:.1f} s; capture alive {self.alive()})"}
        win = self.rows[start_idx:start_idx + n]
        bys = read_frames_bytes(self.od, [r for r in win if r.get("mjpeg_len")])
        ys = []
        for b in bys:
            y, _, _ = decode_y(b)
            if y is not None:
                ys.append(y)
        self.next_idx = start_idx + n
        if len(ys) < n:
            return {"ok": False, "error": f"{n - len(ys)} undecodable / unsaved frame(s)"}
        return {"ok": True, "ys": ys, "seqs": [r.get("seq") for r in win],
                "frames": [[r.get("mjpeg_offset"), r.get("mjpeg_len")] for r in win],
                "t_frames_s": round((time.perf_counter_ns() - self.t0) / 1e9, 3)}

    def _idx_after(self, t_ns: int, timeout_s: float) -> int | None:
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            self._poll()
            if self.clock_mode == "qpc":
                for i in range(self.next_idx, len(self.rows)):
                    q = self.rows[i].get("qpc_ns")
                    if isinstance(q, (int, float)) and q >= t_ns:
                        return i
            elif time.perf_counter_ns() >= t_ns:
                return len(self.rows)
            if not self.alive():
                return None
            time.sleep(0.01)
        return None

    # ---- sets
    def set(self, items: dict, label: str = "") -> dict:
        from common import procutil  # noqa: PLC0415
        spec = ",".join(f"{k}={v}" for k, v in items.items())
        argv = [str(self.spec["wincam"]), "controls", "--api", "ds", "--device", self.spec["ds_path"], "--set", spec,
                "--timeout-ms", "4000"]
        ts = time.perf_counter_ns()
        r = procutil.run(argv, timeout_s=DS_SET_TIMEOUT_S)
        te = time.perf_counter_ns()
        j, _ = suitectx.parse_json_stdout(r)
        j = j or {}
        per = {}
        for k, v in items.items():
            mine = [x for x in j.get("sets") or [] if str(x.get("control", "")).endswith(k)]
            x = mine[0] if mine else {}
            rng = (self.spec.get("ranges") or {}).get(k) or 1
            per[k] = {"want": v, "before": x.get("before_value"), "readback": x.get("readback_value"),
                      "ok": ce.held(x.get("readback_value"), x.get("readback_flags"), v, rng) if mine else False}
        rec = {"label": label, "items": items, "t_start_s": round((ts - self.t0) / 1e9, 3),
               "t_end_s": round((te - self.t0) / 1e9, 3), "call_s": round((te - ts) / 1e9, 3), "rc": r.get("rc"),
               "timed_out": r.get("timed_out"), "per": per, "device_not_answering": j.get("device_not_answering"),
               "error": j.get("error") or (None if j else f"no JSON (rc {r.get('rc')})"), "_t_end_ns": te}
        err = j.get("error") if isinstance(j.get("error"), dict) else {}
        if j.get("device_not_answering") or suitectx.is_device_error(err):
            self.fault = {"kind": "device_error", "code": err.get("hr") or suitectx.DEVICE_ERROR_HR,
                          "stage": err.get("stage") or "control_set",
                          "reason": "DirectShow side-channel set: device not answering"}
        self.sets.append({k2: v2 for k2, v2 in rec.items() if not k2.startswith("_")})
        if all(v2.get("ok") for v2 in per.values()):
            self.last_set.update(items)
        return rec

    def set_checked(self, items: dict, label: str = "") -> dict:
        """Set, read back, and re-apply once when the readback differs (5.3: re-apply anything that changed)."""
        rec = self.set(items, label)
        if self.fault is None and not all(v.get("ok") for v in rec["per"].values()):
            again = {k: v for k, v in items.items() if not rec["per"][k].get("ok")}
            rec2 = self.set(again, label + " re-apply")
            rec = {**rec, "reapplied": {k2: v2 for k2, v2 in rec2.items() if not k2.startswith("_")},
                   "_t_end_ns": rec2["_t_end_ns"]}
        return rec

    def probe(self, exposure: int, gain: int, n: int, discard_s: float) -> dict:
        if not self.alive():
            return {"ok": False, "error": "capture not running" if self.fault is None else "device fault"}
        items = {k: v for k, v in (("exposure", exposure), ("gain", gain)) if self.last_set.get(k) != v}
        srec = None
        t_ref = time.perf_counter_ns()
        if items:
            srec = self.set_checked(items, f"e{exposure} g{gain}")
            if self.fault:
                return {"ok": False, "error": "device fault on set", "set": _pub(srec)}
            t_ref = srec["_t_end_ns"]
        idx = self._idx_after(int(t_ref + discard_s * 1e9), timeout_s=discard_s + 8.0)
        if idx is None:
            return {"ok": False, "error": "no frame after the set", "set": _pub(srec)}
        fps = float(self.spec.get("fps") or 30.0)
        out = self._take(idx, n, timeout_s=5.0 + 3.0 * n / max(fps * 0.5, 1.0))
        out["set"] = _pub(srec)
        return out

    def more(self, n: int) -> dict:
        fps = float(self.spec.get("fps") or 30.0)
        return self._take(self.next_idx, n, timeout_s=5.0 + 3.0 * n / max(fps * 0.5, 1.0))


def _pub(rec):
    return None if rec is None else {k: v for k, v in rec.items() if not k.startswith("_")}


def rule_leg_run(spec: dict, live=None) -> dict:
    """Body of the rule leg (``--rule-leg``): start the stream, wait FIRST_SET_MS after the first frame, re-apply the
    locks through DirectShow, then run every requested rule run. ``live``: an injected camera (offline tests)."""
    cam = live or LiveCam(spec)
    doc: dict = {"tool": "w_gain rule-leg", "utc_started": results.utc_now_iso(), "runs": [], "ok": False}
    t_leg = time.perf_counter()
    deadline = t_leg + float(spec.get("deadline_s") or 900)
    cam.start()
    try:
        if not cam.wait_first(float(spec.get("first_frame_timeout_s") or 15.0)):
            doc["leg_error"] = "no first frame"
        else:
            t_first = time.perf_counter()      # frames.jsonl is flushed per frame: ~ the first frame's arrival
            while time.perf_counter() - t_first < FIRST_SET_MS / 1000.0:
                time.sleep(0.02)
            if spec.get("locks") and spec.get("ds_path") is not None:
                doc["lock_reapply"] = _pub(cam.set_checked(dict(spec["locks"]), "locks"))
            for rp in spec.get("runs") or []:
                if time.perf_counter() > deadline:
                    doc["runs"].append({"label": rp.get("label"), "skipped": "rule leg time budget"})
                    continue
                if not cam.alive():
                    doc["runs"].append({"label": rp.get("label"), "skipped": "capture not running / device fault"})
                    continue
                p = dict(rp)
                p["deadline"] = min(deadline, time.perf_counter() + float(spec.get("run_budget_s") or RULE_RUN_BUDGET_S))
                try:
                    doc["runs"].append(run_rule(cam, p))
                except Exception as e:  # noqa: BLE001
                    doc["runs"].append({"label": rp.get("label"), "exception": repr(e)})
            doc["ok"] = True
    finally:
        cap = cam.stop()
    s = cap.get("summary") or {}
    doc["capture"] = {"run": cap.get("run"), "ok": s.get("ok"), "error": s.get("error"),
                      "frames": (s.get("frames") or {}).get("total"), "fps_measured": s.get("fps_measured"),
                      "unreleasable": s.get("unreleasable"), "exit_code": s.get("exit_code"),
                      "controls_before": s.get("controls_before")}
    doc["sets"] = getattr(cam, "sets", [])
    doc["clock_mode"] = getattr(cam, "clock_mode", None)
    flt = getattr(cam, "fault", None)
    err = s.get("error") if isinstance(s.get("error"), dict) else {}
    # surface a capture / set fault at the top level, where ctx.camcmd's fault scan looks
    if suitectx.is_device_error(err) or s.get("unreleasable") or suitectx.is_release_hang(err):
        doc["error"], doc["unreleasable"] = err, s.get("unreleasable")
    elif flt:
        doc["error"] = {"class": "device_error", "hr": flt.get("code"), "stage": flt.get("stage"),
                        "reason": flt.get("reason")}
    doc["fault"] = flt
    doc["elapsed_s"] = round(time.perf_counter() - t_leg, 3)
    return doc


def rule_leg_main(spec_path: str) -> int:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    doc = rule_leg_run(spec)
    sys.stdout.write(json.dumps(doc, default=str) + "\n")
    return 0


def compact_probes(od: Path, doc: dict) -> dict:
    """Keep the rule's probe frames only (probes.mjpeg + probes.jsonl); delete the full stream file."""
    src = Path(od) / "frames.mjpeg"
    if not src.exists():
        return {"kept": None, "reason": "no frames.mjpeg"}
    n = 0
    with src.open("rb") as f, (Path(od) / "probes.mjpeg").open("wb") as fo, \
            (Path(od) / "probes.jsonl").open("w", encoding="utf-8") as fj:
        for ri, run in enumerate(doc.get("runs") or []):
            for pi, pr in enumerate(run.get("probes") or []):
                for ai, at in enumerate(pr.get("attempts") or []):
                    for (off, ln), seq in zip(at.get("frames") or [], at.get("seqs") or []):
                        if off is None or not ln:
                            continue
                        f.seek(int(off))
                        b = f.read(int(ln))
                        fj.write(json.dumps({"run": ri, "probe": pi, "attempt": ai, "phase": pr.get("phase"),
                                             "exposure": pr.get("exposure"), "gain": pr.get("gain"), "seq": seq,
                                             "mjpeg_offset": fo.tell(), "mjpeg_len": len(b)}) + "\n")
                        fo.write(b)
                        n += 1
    deleted = False
    if not KEEP_FULL_STREAMS:
        try:
            src.unlink()
            deleted = True
        except OSError:
            pass
    return {"kept": n, "file": "probes.mjpeg", "full_stream_deleted": deleted}


# ================================================================================================== rule (parent side)
def choose_forced(cells: list[dict], v_ceil: int, rng_e: dict) -> dict:
    """Forced ceiling for the validation runs: the SHORTEST grid exposure <= the as-written ceiling whose
    gain-minimum cell has a usable flat mask and sits below the band (gain is then needed and the limit is
    exercised). No such exposure: the shortest usable one with the band raised above its luma."""
    rows = _rows_by_exp(cells)
    usable = [(e, row[0]) for e, row in sorted(rows.items()) if _usable(row[0]) and
              (not log2_units(rng_e) or e <= v_ceil)]
    dark = [(e, c) for e, c in usable if (c["metrics"].get("roi_luma_median") or 0) < BAND[0]]
    if dark:
        e, c = dark[0]
        return {"v_ceil": e, "band": list(BAND), "forced_by": "ceiling",
                "why": f"shortest grid exposure with a flat mask and luma below {BAND[0]:g} at gain minimum "
                       f"(luma {c['metrics'].get('roi_luma_median')})"}
    if usable:
        e, c = usable[0]
        lum = float(c["metrics"].get("roi_luma_median") or 100.0)
        lo = min(235.0, lum * 1.6)
        return {"v_ceil": e, "band": [round(lo, 1), round(min(245.0, lo * 1.3), 1)], "forced_by": "band",
                "why": f"every usable exposure is in or above the band at gain minimum; band raised above luma "
                       f"{lum:.1f} at exposure {e}"}
    e = -9 if log2_units(rng_e) and rng_e["min"] <= -9 <= rng_e["max"] else rng_e["min"]
    return {"v_ceil": e, "band": list(BAND), "forced_by": "ceiling",
            "why": "no grid exposure had a usable flat mask; nominal -9 (or the device minimum) used"}


def compare_run(run: dict, caps: dict, g_step: int) -> dict:
    """g_lim vs the reference cap's grid bracket [cap, first failing grid gain] at the run's exposure."""
    e = run.get("exposure")
    out = {"label": run.get("label"), "exposure": e, "g_lim": run.get("g_lim"), "comparable": False}
    if run.get("g_lim") is None or not run.get("limit_reached"):
        out["why"] = ("the luma target was reached below the limit" if run.get("target_reached") else
                      "no gain needed" if run.get("gain_needed") is False else
                      f"limit not measured ({', '.join(run.get('flags') or []) or run.get('error') or 'n/a'})")
        return out
    c = caps.get(str(e))
    if not c or c.get("cap") is None:
        out["why"] = f"no reference cap at exposure {e} ({(c or {}).get('reason') or (c or {}).get('stopped_by')})"
        return out
    ps = max(int(g_step), int(run.get("probe_step") or g_step))
    lo = c["cap"]
    hi = c["next_fail"] if c.get("next_fail") is not None else c["cap"]
    if c.get("stopped_by") == "unknown":
        out["why"] = f"reference cap at exposure {e} known only up to {lo} (cells above unknown)"
        return out
    g = run["g_lim"]
    out.update(comparable=True, bracket=[lo, hi], probe_step=ps, distance_to_cap=g - lo,
               within=bool(lo - ps <= g <= hi + ps))
    return out


def rate_rule(cmp_matched: list[dict], cmp_same: list[dict], mono: dict, n_runs: int, ev: dict) -> dict:
    basis, cmp_ = ("matched_luma", cmp_matched) if any(c["comparable"] for c in cmp_matched) else \
        ("same_exposure", cmp_same)
    comp = [c for c in cmp_ if c["comparable"]]
    within = [c for c in comp if c["within"]]
    ev = {**ev, "rating_basis": basis}
    crits = [crit(f"g_lim within one probe step of the {basis.replace('_', '-')} reference cap on every forced run",
                  (len(within) == n_runs) if comp else None, f"{len(within)}/{len(comp)} comparable of {n_runs} runs"),
             crit("rho rises monotonically with gain on the grid", mono.get("monotonic"),
                  f"{mono.get('rows_checked')} exposure rows checked")]
    if not comp:
        why = "; ".join(sorted({c.get("why") or "" for c in cmp_})) or "no forced run"
        return verdict("untested", crits, ev, f"untested (inconclusive): {why}", "untested (inconclusive)")
    if len(within) == n_runs and mono.get("monotonic"):
        return verdict("yes", crits, ev)
    if len(within) == n_runs or len(within) * 2 >= n_runs:
        note = "rho not monotonic in gain on the grid" if len(within) == n_runs else \
            f"g_lim outside the reference bracket in {n_runs - len(within)} of {n_runs} runs"
        return verdict("partial", crits, ev, note)
    return verdict("no", crits, ev, f"g_lim outside the reference bracket in {n_runs - len(within)} of {n_runs} runs")


# ================================================================================================== T4
def t4_plan(exps: list[int], g_min: int, locks: dict) -> dict:
    items = [f"{LOCK_REAPPLY_MS}:{x}" for x in lock_items(locks)] + [f"{FIRST_SET_MS}:gain={g_min}"]
    steps = []
    for i, v in enumerate(exps):
        t = FIRST_SET_MS + int(i * T4_STEP_S * 1000)
        items.append(f"{t}:exposure={v}")
        steps.append({"exposure": v, "set_ms": t})
    end = FIRST_SET_MS + int(len(exps) * T4_STEP_S * 1000)
    items.append(f"{end}:exposure=manual")
    before = ",".join(lock_items(locks) + [f"exposure={exps[0]}", f"gain={g_min}"])
    return {"steps": steps, "end_ms": end, "seconds": round(end / 1000.0 + 0.2, 3), "controls_before": before,
            "schedule": ";".join(items)}


def analyse_t4(rows: list[dict], summary: dict, plan: dict, nominal: float, r_exp: dict) -> dict:
    events = (summary or {}).get("schedule") or []
    rows = [r for r in rows if isinstance(r.get("qpc_ns"), (int, float))]
    out = []
    steps = plan["steps"]
    for i, st in enumerate(steps):
        ev = _ev_for(events, "exposure", st["set_ms"])
        nxt_ms = steps[i + 1]["set_ms"] if i + 1 < len(steps) else plan["end_ms"]
        nev = _ev_for(events, "exposure", nxt_ms)
        rec = {"exposure": st["exposure"], "readback": (ev or {}).get("readback_value"),
               "readback_ok": ce.held((ev or {}).get("readback_value"), (ev or {}).get("readback_flags"),
                                      st["exposure"], r_exp) if ev else None}
        if not ev or not (ev.get("done_qpc_ns") or ev.get("applied_qpc_ns")):
            rec.update(fps=None, why="set event missing")
            out.append(rec)
            continue
        a = (ev.get("done_qpc_ns") or ev["applied_qpc_ns"]) + T4_SETTLE_S * 1e9
        b = (nev or {}).get("applied_qpc_ns") or float("inf")
        win = [r for r in rows if a <= r["qpc_ns"] < b]
        rec["frames"] = len(win)
        rec["window_s"] = round((min(b, win[-1]["qpc_ns"]) - a) / 1e9, 3) if win else None
        rec["fps"] = _r(ck.fps_from_rows(win, skip_frac=0.0), 3) if len(win) >= 5 else None
        if len(win) >= 2 and rec["fps"] is None:
            rec["fps"] = _r((len(win) - 1) / ((win[-1]["qpc_ns"] - win[0]["qpc_ns"]) / 1e9), 3)
        out.append(rec)
    fps = [x["fps"] for x in out if x.get("fps")]
    short = sorted([x for x in out if x.get("fps")], key=lambda x: x["exposure"])[:3]
    own = sorted(x["fps"] for x in short)[len(short) // 2] if short else None
    exp_c = expected_ceiling(nominal) if log2_units(r_exp) else None

    def ceiling(ref):
        if ref is None:
            return None, None
        c, first_drop = None, None
        for x in sorted(out, key=lambda x: x["exposure"]):
            if x.get("fps") is None:
                continue
            if abs(x["fps"] - ref) / ref <= FPS_TOL:
                if first_drop is None:
                    c = x["exposure"]
            elif first_drop is None:
                first_drop = x
        return c, first_drop
    c_own, drop_own = ceiling(own)
    c_nom, drop_nom = ceiling(nominal)
    return {"steps": out, "nominal_fps": nominal, "own_rate_fps": own, "expected_ceiling": exp_c,
            "measured_ceiling": c_own, "measured_ceiling_vs_nominal": c_nom,
            "first_step_lowering_rate": ({"exposure": drop_own["exposure"], "fps": drop_own["fps"]}
                                         if drop_own else None),
            "first_step_off_nominal": ({"exposure": drop_nom["exposure"], "fps": drop_nom["fps"]}
                                       if drop_nom else None),
            "n_steps_measured": len(fps), "tolerance": FPS_TOL,
            "units": "log2 seconds" if log2_units(r_exp) else "unknown (not log2 seconds)"}


def rate_t4(t4: dict) -> dict:
    if not t4 or not t4.get("n_steps_measured"):
        return rating.untested("no T4 step measured", t4)
    exp_c, c = t4.get("expected_ceiling"), t4.get("measured_ceiling")
    crits = [crit("delivered fps within 1 % of the camera's own short-exposure rate for every step up to the "
                  "frame-period ceiling", None if exp_c is None else (c is not None and c >= exp_c),
                  f"measured ceiling {c}, expected {exp_c}; first step lowering the rate "
                  f"{t4.get('first_step_lowering_rate')}"),
             crit("within 1 % of nominal", None if exp_c is None else (t4.get("measured_ceiling_vs_nominal")
                                                                          or -99) >= exp_c,
                  f"nominal {t4.get('nominal_fps')}, own rate {t4.get('own_rate_fps')}")]
    if exp_c is None:
        return verdict("untested", crits, t4, f"exposure units unknown; measured ceiling {c} (rate held through it)",
                       "untested (units unknown)")
    if c is not None and c >= exp_c:
        return verdict("yes", crits, t4, None if crits[1]["met"] else "holds the camera's own rate, which is "
                                                                      "more than 1 % off nominal")
    return verdict("no", crits, t4, f"the rate drops at or below the expected ceiling {exp_c} (measured {c})")


# ================================================================================================== modes
def modes_for(ctx, advertised: list) -> tuple[list, dict]:
    """The ~30 fps default 720-line MJPEG mode and a ~60 fps 720-line mode where the camera has one."""
    kept, rec = ck.scoped(ctx, advertised)
    k720 = [m for m in kept if m.h == 720] if not ck.mode_scope(ctx).all_modes else kept
    out = []
    d30 = ck._nearest([m for m in k720 if m.fps < 45], 1280, 720, 30.0) if k720 else None
    d60 = ck._nearest([m for m in k720 if m.fps >= 55], 1280, 720, 60.0) if k720 else None
    for m in (d30, d60):
        if m is not None and m not in out:
            out.append(m)
    rec["w_gain_modes"] = [m.text for m in out]
    if not out:
        rec["untested_reason"] = rec.get("untested_reason") or \
            f"no 720-line MJPEG mode in scope ({len(advertised)} advertised)"
    return out, rec


def _cached_modes(ctx, cam: dict) -> list | None:
    """Modes from files only (no camera command): this run's format cache, W-FMT's listing, or (plan mode) an
    earlier run's cache."""
    for p in (Path(ctx.raw_dir) / "_cache" / f"formats_mf_{ck.cam_slug(cam)}.json",):
        try:
            return ck.mjpeg_modes(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    if getattr(ctx, "dry_run", False):
        d, _ = ck.cached_formats_from_earlier_runs(ctx, cam)
        if d:
            return ck.mjpeg_modes(d)
    return None


# ================================================================================================== estimate
def mode_estimate_s(fps: float, quick: bool, nf: int, n_exp: int, n_gain: int, n_t4: int, runs: int) -> float:
    cell = SETTLE_S + nf / (0.9 * fps) + CELL_MARGIN_S
    grid = n_exp * (CAP_OVERHEAD_S + FIRST_SET_MS / 1000.0 + n_gain * cell) + n_exp * n_gain * \
        (ANALYSE_CELL_S * nf / GRID_FRAMES)
    probe = DS_SET_S + DISCARD_S + PROBE_FRAMES / fps + 0.15
    rule = CAP_OVERHEAD_S + 3 + (runs + (0 if quick else 1)) * 11 * probe
    t4 = CAP_OVERHEAD_S + FIRST_SET_MS / 1000.0 + n_t4 * T4_STEP_S
    return grid + rule + t4


def estimate_s(ctx) -> float:
    q = ck.quick(ctx)
    nf, runs = frames_per_cell(ctx), rule_runs(ctx)
    n_exp, n_gain, n_t4 = (2, 3, 3) if q else (7, 7, 10)
    total = 0.0
    for cam in ctx.cameras:
        modes = _cached_modes(ctx, cam)
        fps_list = [30.0]
        if modes:
            try:
                ms, _ = modes_for(ctx, modes)
                fps_list = [m.fps for m in ms] or [30.0]
            except Exception:  # noqa: BLE001
                pass
        total += 7 * CMD_S + sum(mode_estimate_s(f, q, nf, n_exp, n_gain, n_t4,
                                                 runs if i == 0 else min(runs, RULE_RUNS_EXTRA_MODE))
                                 for i, f in enumerate(fps_list))
    return total


# ================================================================================================== per camera
def camera_work(ctx, cam: dict, cres: dict, verdicts: dict, errors: list, fcache: dict) -> None:
    key, slug = cam["key"], ck.cam_slug(cam)
    raw = Path(ctx.raw_test_dir(TEST)) / slug
    tdir = ctx.test_dir(TEST)
    q = ck.quick(ctx)
    nf = frames_per_cell(ctx)
    t_cam = time.monotonic()
    stop = {"rec": None}

    def dead() -> dict | None:
        if stop["rec"] is None:
            stop["rec"] = halt(ctx, cam)
            if stop["rec"]:
                ctx.log(f"{TEST}: {cam_text(cam)}: device fault / dead ({stop['rec'].get('source')}); no further "
                        "command to this camera")
        return stop["rec"]

    def untested_all(modes_txt: list[str], rec: dict, keep_done: bool = False) -> None:
        """'untested: device fault/dead' for every verdict of this camera (``keep_done``: keep the verdicts of work
        that finished before the fault)."""
        for mt in modes_txt or ["mf"]:
            for g in ("gain_grid", "gain_rule", "fps_ceiling"):
                k = f"{g}|{key}|{mt}"
                if not (keep_done and k in verdicts):
                    verdicts[k] = dead_verdict(ctx, cam, rec, {"partial_results_in": "measurements.cameras[key]"}
                                               if keep_done else None)

    if dead():
        cres["device_fault"] = stop["rec"]
        untested_all([], stop["rec"])
        return
    if not cam.get("mf_symlink"):
        why = "no MF symlink (the grid, T4 and the rule stream through MF)"
        for g in ("gain_grid", "gain_rule", "fps_ceiling"):
            verdicts[f"{g}|{key}|mf"] = rating.untested(why)
        cres["skipped"] = why
        return
    fm, fread = ck.formats_checked(ctx, cam, fcache, TEST)
    if fread:
        cres["format_read"] = fread
        for g in ("gain_grid", "gain_rule", "fps_ceiling"):
            verdicts[f"{g}|{key}|mf"] = ck.format_failed_untested(fread)
        return
    modes, scope = modes_for(ctx, ck.mjpeg_modes(fm))
    cres["mode_scope"] = scope
    cres["modes"] = [m.text for m in modes]
    if not modes:
        for g in ("gain_grid", "gain_rule", "fps_ceiling"):
            verdicts[f"{g}|{key}|mf"] = ck.scope_untested(ctx, scope)
        return
    mslugs = [m.slug for m in modes]
    if dead():
        untested_all(mslugs, stop["rec"])
        return
    initial, run0 = ck.get_controls(ctx, cam, "mf")
    cres["initial_read"] = run0
    na, hr = ce.not_answering(initial, run0)
    if na:
        dna = {"hr": hr, "utc": results.utc_now_iso(), "at": "initial_read"}
        cres["device_not_answering"] = dna
        ce.gate_report(ctx, cam, modes[0].text, hr, "mf control GETs failed", "mf")
        untested_all(mslugs, {"utc": dna["utc"], "code": hr, "reason": f"device not answering ({hr})"})
        return
    if initial is not None:
        cres["initial_read_file"] = _rel(ctx, results.write_json(tdir / f"{slug}_as_found_mf.json", initial))
    tab = ck.control_table(initial)
    for need in ("exposure", "gain"):
        c = tab.get(need)
        if c is None or not ce.manual_capable(c) or c.get("max") is None or c["max"] <= c["min"]:
            why = f"no manual {need} control with a range ({(c or {}).get('min')}..{(c or {}).get('max')})"
            for g in ("gain_grid", "gain_rule", "fps_ceiling"):
                verdicts[f"{g}|{key}|mf"] = rating.untested(why)
            cres["skipped"] = why
            return
    names = [n for n in STATE_NAMES if n in tab and ce.control_answered(tab[n])]
    as_found = wa.state_of(tab, names)
    ranges = {n: rng_of(tab.get(n)) for n in names}
    cres["as_found"] = as_found
    cres["as_found_context"] = ck.control_state(initial)
    cres["ranges"] = ranges
    r_e, r_g = ranges["exposure"], ranges["gain"]
    g_min = int(r_g["min"])
    # 1. locks: AE off at the current exposure, AF off at the current focus, AWB off holding its value, AE priority 0
    locks: dict = {}
    for n in ("white_balance", "focus"):
        c = tab.get(n)
        if c is not None and ce.manual_capable(c) and c.get("value") is not None:
            locks[n] = int(c["value"])
    if "auto_exposure_priority" in tab and tab["auto_exposure_priority"].get("value") is not None:
        locks["auto_exposure_priority"] = 0
    lock_sets = {**locks, "exposure": int(tab["exposure"]["value"] if tab["exposure"].get("value") is not None
                                          else r_e["max"])}
    cres["locks"] = {"requested": lock_sets, "note": "every other control left as found"}
    touched = True
    try:
        if dead():
            raise _Halt()
        js, rs = ck.set_controls(ctx, cam, "mf", lock_sets, flags="manual")
        if dead():
            raise _Halt()
        chk, rc_ = ck.get_controls(ctx, cam, "mf")
        ct = ck.control_table(chk)
        cres["locks"].update(set_run=rs, sets=(js or {}).get("sets"), readback={
            n: {"value": (ct.get(n) or {}).get("value"), "flags": (ct.get(n) or {}).get("flags_names"),
                # a control with no mode flag (AE priority) is locked when its value matches
                "manual": ("manual" in ((ct.get(n) or {}).get("flags_names") or [])) or
                          (not ((ct.get(n) or {}).get("flags_names") or [])
                           and (ct.get(n) or {}).get("value") == lock_sets[n])} for n in lock_sets})
        cres["locks"]["locked"] = all(v["manual"] for v in cres["locks"]["readback"].values()) if chk else None
        ctx.log(f"{TEST}: {cam_text(cam)}: locks {lock_sets} -> manual flags read back "
                f"{cres['locks'].get('locked')}")
        grid_spent = 0.0
        exps_by_mode = {m.slug: grid_exposures(r_e, q) for m in modes}
        gains = grid_gains(r_g, q)
        plan_s = sum(len(exps_by_mode[m.slug]) * (CAP_OVERHEAD_S + FIRST_SET_MS / 1000.0 + len(gains) *
                                                   (SETTLE_S + nf / (0.9 * m.fps) + CELL_MARGIN_S) +
                                                   len(gains) * ANALYSE_CELL_S * nf / GRID_FRAMES) for m in modes)
        reduced_reason = None
        if plan_s > GRID_BUDGET_S:
            reduced_reason = f"planned grid {plan_s:.0f} s > budget {GRID_BUDGET_S:.0f} s"
            exps_by_mode = {k: reduced_exposures(v, r_e) for k, v in exps_by_mode.items()}
        cres["grid_plan"] = {"gains": gains, "exposures": exps_by_mode, "frames_per_cell": nf,
                             "planned_s": round(plan_s, 1), "reduced": reduced_reason}
        cres["per_mode"] = {}
        row_times: list[float] = []
        for mi, m in enumerate(modes):
            mres: dict = {"mode": m.as_dict()}
            cres["per_mode"][m.slug] = mres
            mode_t0 = time.monotonic()
            # ---------------------------------------------------------------------------- T4
            if dead():
                raise _Halt()
            t4e = t4_exposures(r_e, m.fps, q)
            tp = t4_plan(t4e, g_min, locks)
            od = raw / f"{m.slug}_t4"
            s, r = ck.wincam_capture(ctx, cam, m, od, seconds=tp["seconds"], save="none",
                                     extra=["--controls-before", tp["controls_before"], "--schedule", tp["schedule"]])
            s = s or {}
            if capture_fault(ctx, cam, m, s, r) or dead():
                mres["t4"] = {"error": s.get("error"), "run": r}
                raise _Halt()
            t4 = analyse_t4(ck.load_frames(od), s, tp, m.fps, r_e)
            t4.update(capture_ok=bool(s.get("ok")), run=r, error=s.get("error"))
            mres["t4"] = t4
            verdicts[f"fps_ceiling|{key}|{m.slug}"] = rate_t4(t4)
            ctx.log(f"{TEST}: {cam_text(cam)} {m.text} T4: fps per step "
                    f"{[(x['exposure'], x.get('fps')) for x in t4['steps']]} -> ceiling {t4.get('measured_ceiling')} "
                    f"(expected {t4.get('expected_ceiling')})")
            # ---------------------------------------------------------------------------- grid
            cells: list[dict] = []
            exps = list(exps_by_mode[m.slug])
            keep_rows = reduced_exposures(exps, r_e)
            grid_t0 = time.monotonic()
            skipped_rows: list[int] = []
            failed_rows = 0
            for ei, e in enumerate(exps):
                if dead():
                    raise _Halt()
                if failed_rows >= 2:
                    # two row captures in a row delivered nothing (not a device fault): do not keep hammering;
                    # the rows stay planned, so the grid rates partial / no
                    mres.setdefault("grid_stopped", {"why": "two consecutive row captures delivered no frames",
                                                     "rows_not_run": []})["rows_not_run"].append(e)
                    continue
                if row_times and not reduced_reason and e not in keep_rows:
                    # project this camera's whole grid (this mode's rows left + later modes) from the measured rows
                    left = len(exps) - ei + sum(len(exps_by_mode[m2.slug]) for m2 in modes[mi + 1:])
                    proj = grid_spent + (time.monotonic() - grid_t0) + left * (sum(row_times) / len(row_times))
                    if proj > GRID_BUDGET_S:
                        skipped_rows.append(e)
                        continue
                t_row = time.monotonic()
                plan = row_plan(m, e, gains, locks, nf, r_e)
                od = raw / f"{m.slug}_e{e}"
                s, r = capture_row(ctx, cam, m, plan, od)
                if capture_fault(ctx, cam, m, s, r) or dead():
                    errors.append({"camera": key, "mode": m.text, "exposure": e, "capture_error": s.get("error")})
                    raise _Halt()
                row = analyse_row(od, s, plan, nf, ranges, None)
                masks = row[0].pop("_masks", None) if row else None
                compacted = compact_cells(od, row)          # offsets refer to this capture's stream file
                bad = [c["gain"] for c in row if not c.get("valid")]
                no_frames = not any(c.get("n_frames") for c in row)
                failed_rows = failed_rows + 1 if no_frames else 0
                if bad and not no_frames and not dead():
                    plan2 = row_plan(m, e, bad, locks, nf, r_e, slot_mult=1.5)
                    od2 = raw / f"{m.slug}_e{e}_reapply"
                    s2, r2 = capture_row(ctx, cam, m, plan2, od2)
                    if capture_fault(ctx, cam, m, s2, r2) or dead():
                        raise _Halt()
                    keep_masks = masks if (row and row[0].get("valid")) else None
                    row2 = analyse_row(od2, s2, plan2, nf, ranges, keep_masks)
                    if row2:
                        row2[0].pop("_masks", None)
                    by_g = {c["gain"]: c for c in row2}
                    for i, c in enumerate(row):
                        c2 = by_g.get(c["gain"])
                        if c2 is not None and (c2.get("valid") or not c.get("valid")):
                            c2["reapplied"] = True
                            c2["first_attempt"] = {k: c.get(k) for k in ("why", "readback", "held_through_cell",
                                                                          "n_frames")}
                            row[i] = c2
                    mres.setdefault("reapply", []).append({"exposure": e, "gains": bad, "capture_ok": s2.get("ok"),
                                                           "run": r2, "compacted": compact_cells(od2, row2)})
                mres.setdefault("row_runs", []).append({"exposure": e, "capture_ok": s.get("ok"), "run": r,
                                                        "frames_total": (s.get("frames") or {}).get("total"),
                                                        "plan": {k: plan[k] for k in ("slot_ms", "seconds",
                                                                                      "expected_fps")},
                                                        "compacted": compacted})
                cells += row
                row_times.append(time.monotonic() - t_row)
                ctx.log(f"{TEST}: {cam_text(cam)} {m.text} grid exposure {e}: "
                        f"{[(c['gain'], (c.get('metrics') or {}).get('roi_luma_median'), (c.get('metrics') or {}).get('rho')) for c in row]}")
            grid_spent += time.monotonic() - grid_t0
            for c in cells:
                c.pop("frames", None)           # per-frame offsets live in raw_dir (cells.jsonl)
            mres["grid"] = {"exposures": [e for e in exps if e not in skipped_rows], "gains": gains,
                            "frames_per_cell": nf, "cells": cells, "rows_skipped_for_budget": skipped_rows,
                            "time_s": round(time.monotonic() - grid_t0, 1),
                            "reduced": reduced_reason or (f"projected past the {GRID_BUDGET_S:.0f} s budget: rows "
                                                          f"{skipped_rows} skipped, kept {keep_rows}"
                                                          if skipped_rows else None)}
            n_cells = len(exps) * len(gains) - len(skipped_rows) * len(gains)
            n_valid = sum(1 for c in cells if c.get("valid"))
            gv = [crit("every planned cell measured (set read back, value held, all frames, decodable)",
                       n_valid == n_cells, f"{n_valid}/{n_cells} cells valid")]
            verdicts[f"gain_grid|{key}|{m.slug}"] = verdict(
                "yes" if n_valid == n_cells and n_cells else ("partial" if n_valid else "no"), gv,
                {"valid": n_valid, "planned": n_cells, "reduced": mres["grid"]["reduced"]},
                f"grid reduced: {mres['grid']['reduced']}" if mres["grid"]["reduced"] else None)
            # ---------------------------------------------------------------------------- caps
            same = same_exposure_caps(cells)
            matched = matched_luma_caps(cells)
            mono = rho_monotonic(cells)
            mres["reference_cap"] = {"same_exposure": same, "matched_luma": matched,
                                     "thresholds": {"rho_ratio_max": RHO_MAX_RATIO, "d_ratio_min": D_MIN_RATIO}}
            mres["rho_monotonic"] = mono
            # ---------------------------------------------------------------------------- the rule
            v_asw = expected_ceiling(m.fps) if log2_units(r_e) else \
                (t4["measured_ceiling"] if t4.get("measured_ceiling") is not None else r_e["max"])
            forced = choose_forced(cells, v_asw, r_e)
            mres["rule_plan"] = {"as_written_ceiling": v_asw, "forced": forced,
                                 "as_written_ceiling_basis": "frame period (largest 2^v <= 1/fps)" if log2_units(r_e)
                                 else "T4 measured ceiling (exposure units unknown)"}
            n_runs = rule_runs(ctx) if mi == 0 else min(rule_runs(ctx), RULE_RUNS_EXTRA_MODE)
            if not cam.get("ds_path"):
                mres["rule"] = {"skipped": "no DirectShow path: the live rule needs side-channel sets"}
                verdicts[f"gain_rule|{key}|{m.slug}"] = rating.untested(mres["rule"]["skipped"])
            else:
                if dead():
                    raise _Halt()
                base = {"v_min": int(r_e["min"]), "v_max": int(r_e["max"]), "g_min": g_min, "g_max": int(r_g["max"]),
                        "g_step": int(r_g.get("step") or 1), "probe_frames": PROBE_FRAMES, "luma_frames": LUMA_FRAMES,
                        "discard_s": DISCARD_S}
                runs = [] if q else [{**base, "label": "as_written", "v_ceil": v_asw, "band": list(BAND)}]
                runs += [{**base, "label": f"forced_{i + 1}", "v_ceil": forced["v_ceil"], "band": forced["band"],
                          "forced_by": forced["forced_by"]} for i in range(n_runs)]
                od = raw / f"{m.slug}_rule"
                doc, rr = run_leg(ctx, cam, m, runs, locks, ranges, od)
                flt = None
                if doc is not None:
                    flt = doc.get("fault") or ck.fault_from_result("mf", doc.get("capture") or {}, None)
                    if flt and flt.get("kind") != "gated":
                        ck.mark_device_fault(ctx, cam, TEST, m.text, "mf", flt)
                elif rr.get("timed_out"):
                    flt = {"kind": "hung_process", "code": "timeout", "stage": "rule leg",
                           "reason": "rule leg killed at its timeout"}
                    ck.mark_device_fault(ctx, cam, TEST, m.text, "mf", flt)
                g_st = int(r_g.get("step") or 1)
                all_runs = (doc or {}).get("runs") or []
                fr = [x for x in all_runs if str(x.get("label", "")).startswith("forced")]
                cm = [compare_run(x, matched["per_exposure"], g_st) for x in fr]
                cs = [compare_run(x, same, g_st) for x in fr]
                asw = next((x for x in all_runs if x.get("label") == "as_written"), None)
                mres["rule"] = {"leg_run": rr, "leg_ok": (doc or {}).get("ok"), "leg_error": (doc or {}).get("leg_error"),
                                "capture": (doc or {}).get("capture"), "lock_reapply": (doc or {}).get("lock_reapply"),
                                "clock_mode": (doc or {}).get("clock_mode"),
                                "as_written": _run_summary(asw) if asw else None,
                                "as_written_gain_needed": (asw or {}).get("gain_needed"),
                                "forced_runs": [_run_summary(x) for x in fr],
                                "compare_matched_luma": cm, "compare_same_exposure": cs,
                                "compacted": compact_probes(od, doc or {})}
                det = results.write_json(tdir / f"{slug}_{m.slug}_rule.json", doc or {"error": "no leg output"})
                mres["rule"]["detail_file"] = _rel(ctx, det)
                if flt or dead():
                    mres["rule"]["fault"] = flt
                    raise _Halt()               # the partial runs stay in measurements; the verdict is untested
                ev = {"forced": forced, "runs": len(fr), "g_lim": [x.get("g_lim") for x in fr],
                      "time_s": [x.get("time_s") for x in fr], "as_written": mres["rule"]["as_written"],
                      "matched_luma": cm, "same_exposure": cs,
                      "pass_matched_luma": bool(cm) and all(c.get("within") for c in cm),
                      "pass_same_exposure": bool(cs) and all(c.get("within") for c in cs)}
                v = rate_rule(cm, cs, mono, n_runs, ev)
                if len(fr) < n_runs:
                    v["note"] = ((v.get("note") or "") + f"; only {len(fr)} of {n_runs} runs ran").strip("; ")
                verdicts[f"gain_rule|{key}|{m.slug}"] = v
                ctx.log(f"{TEST}: {cam_text(cam)} {m.text} rule: as-written gain needed "
                        f"{mres['rule']['as_written_gain_needed']}; forced ({forced['forced_by']} "
                        f"{forced['v_ceil']}) g_lim {ev['g_lim']} -> {v['rating']}")
            mres["time_s"] = round(time.monotonic() - mode_t0, 1)
            results.write_json(tdir / f"{slug}_{m.slug}_grid.json", {"camera": key, "mode": m.text,
                                                                     "grid": mres.get("grid"),
                                                                     "reference_cap": mres.get("reference_cap")})
    except _Halt:
        cres["device_fault"] = stop["rec"] or halt(ctx, cam) or {"source": "capture fault"}
        untested_all(mslugs, cres["device_fault"], keep_done=True)
        touched = False
        ctx.log(f"{TEST}: {cam_text(cam)}: stopped (device fault / dead); no restore, no further command")
    finally:
        if touched and not dead():
            cres["restore"] = restore_verified(ctx, cam, as_found, ranges, errors)
        elif touched or cres.get("device_fault"):
            cres["restore"] = {"skipped": "device fault / dead: no further command", "restored": None}
        cres["time_s"] = round(time.monotonic() - t_cam, 1)


class _Halt(Exception):
    """The camera faulted / died: stop its work, send it nothing more."""


def _run_summary(x: dict | None) -> dict | None:
    if not x:
        return None
    keys = ("label", "exposure", "gain", "g_lim", "luma", "luma_at_gain_min", "gain_needed", "target_reached",
            "limit_reached", "limit_is_range_max", "probe_step", "rho_ref", "rho_at_glim", "rho_ratio", "d_ratio",
            "gain_response", "n_probes", "n_exposure_probes", "n_gain_probes", "n_motion_retries", "time_s", "flags",
            "warnings", "error", "skipped", "exception", "too_dark_factor", "v_ceil_used")
    out = {k: x.get(k) for k in keys if k in x}
    out["gain_probes"] = [(pr.get("gain"), (pr.get("stats") or {}).get("roi_luma_median"), pr.get("valid"),
                           (pr.get("checks") or {}).get("rho_ratio"), (pr.get("checks") or {}).get("d_ratio"))
                          for pr in x.get("probes") or [] if pr.get("phase") == "gain"]
    return out


def run_leg(ctx, cam, mode, runs: list[dict], locks: dict, ranges: dict, od: Path) -> tuple[dict | None, dict]:
    od = Path(od)
    od.mkdir(parents=True, exist_ok=True)
    stop = od / "stop_capture.flag"
    budget = min(LEG_BUDGET_MAX_S, 30.0 + len(runs) * RULE_RUN_BUDGET_S)
    before = ",".join(lock_items(locks) + [f"exposure={runs[0]['v_ceil'] if runs else ranges['exposure']['min']}",
                                           f"gain={ranges['gain']['min']}"])
    cap = ck.wincam_capture_argv(ctx, cam, mode, od, seconds=budget + 60, save="all",
                                 extra=["--stop-file", str(stop), "--controls-before", before])
    spec = {"out_dir": str(od), "stop_file": str(stop), "capture_argv": [str(a) for a in cap],
            "wincam": str(ctx.wincam), "ds_path": cam.get("ds_path"), "fps": mode.fps, "locks": locks,
            "ranges": ranges, "runs": runs, "deadline_s": budget, "run_budget_s": RULE_RUN_BUDGET_S,
            "first_frame_timeout_s": 15.0}
    sp = od.parent / f"{od.name}_leg.json"
    results.write_json(sp, spec)
    # the MF symlink in argv lets ctx.camcmd attribute the command to the camera (dead rule, fault scan)
    r = ctx.camcmd([sys.executable, str(Path(__file__).resolve()), "--rule-leg", str(sp), "--device",
                    cam["mf_symlink"]], timeout_s=budget + 120)
    return ck.parse_json(r), ck.run_brief(r)


def restore_verified(ctx, cam, as_found: dict, ranges: dict, errors: list) -> dict:
    rs = wa.restore_state(ctx, cam, "mf", as_found, ranges)
    if rs.get("restored") is not True and not halt(ctx, cam):
        ctx.log(f"{TEST}: {cam_text(cam)}: restore not verified; retrying once")
        time.sleep(2.0)
        rs2 = wa.restore_state(ctx, cam, "mf", as_found, ranges)
        rs2["first_attempt"] = rs
        rs = rs2
    if rs.get("restored") is not True:
        errors.append({"camera": cam["key"], "restore_not_verified": rs.get("after"),
                       "wanted": {"auto": rs.get("auto"), "manual": rs.get("manual")}})
    ctx.log(f"{TEST}: {cam_text(cam)}: as-found state restored: {rs.get('restored')}")
    return rs


# ================================================================================================== run
def run(ctx) -> dict:
    res = ck.new_result(ctx, TEST)
    arr0 = ck.arrivals_before(ctx)
    errors: list = []
    verdicts: dict = {}
    per_cam: dict = {}
    fcache: dict = {}
    t0 = time.monotonic()
    for cam in ctx.cameras:
        cres: dict = {"name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"),
                      "vid_pid": f"{cam.get('vid')}:{cam.get('pid')}"}
        per_cam[cam["key"]] = cres
        try:
            camera_work(ctx, cam, cres, verdicts, errors, fcache)
        except Exception as e:  # noqa: BLE001
            import traceback  # noqa: PLC0415
            errors.append({"camera": cam["key"], "exception": repr(e), "traceback": traceback.format_exc()[-3000:]})
            ctx.log(f"{TEST}: {cam_text(cam)}: exception {e!r}")
    meas = {"quick": ck.quick(ctx), "frames_per_cell": frames_per_cell(ctx), "rule_runs": rule_runs(ctx),
            "elapsed_s": round(time.monotonic() - t0, 1), "cameras": per_cam,
            "arrivals": ck.arrivals_after(ctx, arr0),
            "parameters": {"gain_fracs": GAIN_FRACS_QUICK if ck.quick(ctx) else GAIN_FRACS,
                           "exposures": EXP_QUICK if ck.quick(ctx) else EXP_GRID, "reduced_exposures": EXP_REDUCED,
                           "t4_exposures": T4_EXP, "t4_step_s": T4_STEP_S, "t4_settle_s": T4_SETTLE_S,
                           "first_set_ms": FIRST_SET_MS, "settle_s": SETTLE_S, "roi": ROI, "flat_grad": FLAT_GRAD,
                           "blur_k": BLUR_K, "mask_luma": MASK_LUMA, "min_mask_px": MIN_MASK_PX,
                           "texture_percentile": TEX_PCT, "rho_ratio_max": RHO_MAX_RATIO,
                           "d_ratio_min": D_MIN_RATIO, "rise_min": RISE_MIN, "band": BAND, "target": TARGET,
                           "clip_max": CLIP_MAX, "motion": [MOTION_DELTA, MOTION_FRAC, MOTION_RETRIES],
                           "probe_frames": PROBE_FRAMES, "luma_frames": LUMA_FRAMES, "discard_s": DISCARD_S,
                           "grid_budget_s": GRID_BUDGET_S, "keep_full_streams": KEEP_FULL_STREAMS},
            "methods": {
                "controls": "grid / T4: wincam capture --controls-before + --schedule (in-stream sets on the MF "
                            "source, readback per set, the next set's before_value = held through the cell); rule: "
                            "wincam controls --api ds --set in concurrent processes while wincam capture streams "
                            "(W-AUTO ds path), re-applied once when the readback differs",
                "frames": "the camera's JPEG bytes (wincam --save all), decoded to Y with simplejpeg; strict=True "
                          "failures counted",
                "noise": "per-pixel temporal sigma over the cell's frames; rho = median sigma/mu over the flat mask "
                         "(5.2a; Appendix A's Sobel + 9x9 box blur < 6 and luma 30-220 at gain minimum); row-mean "
                         "part and EMVA two-frame sigma alongside",
                "detail": "mean Sobel magnitude of the cell's mean frame over the textured mask (top 10 % blurred "
                          "gradient at gain minimum) / their mean luma",
                "scene": "static desk scene at night under steady room light; no grey card, chart or dark frames: "
                         "flat scene regions stand in for the card, gradient energy for MTF50"},
            "kiyo_pro_note": "the Razer Kiyo Pro (1532:0e05) runs first; a fault / dead record stops all its work"}
    return results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)


def _main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "--rule-leg":
        return rule_leg_main(argv[1])
    print("usage: w_gain.py --rule-leg <spec.json> [--device <mf symlink>]   (live runs go through run_suite.py)",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
