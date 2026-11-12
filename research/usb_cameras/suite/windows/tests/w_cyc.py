"""W-CYC: repeated open -> first frame -> N frames -> close, per camera x API (Dom's reliability criterion).

Plan section 6.2 (CYC), section 2.3 and section 3 (reliability: >= 99% of cycles deliver a first frame within 2 s,
no hang beyond the watchdog, no state that needs a replug). A per-camera ">= 99 %" claim needs >= 381 failure-free
cycles (Wilson lower bound), hence the ``reliability`` profile. Variants per camera, all at the default mode
(MJPG 1280x720@30 or the nearest in-scope mode) unless noted:

| variant               | how                                                             | cycles: reliability / standard / quick |
| mf_inproc             | ``wincam cycle`` (one process; safe release order; re-enumerate) | R (400) / K (50) / 4                  |
| mf_newproc            | ``wincam capture --frames N`` once per process                   | 100 / K' (15) / 2                     |
| ds_ffmpeg_inproc      | ``pyav_ds cycle --engine ffmpeg``: DirectShow through the ffmpeg | R (400) / K (50) / 4                  |
|                       | CLI with -vcodec mjpeg (MJPEG guaranteed; one ffmpeg.exe per     |                                       |
|                       | cycle inside one helper process)                                 |                                       |
| ds_inproc             | ``pyav_ds cycle`` (PyAV as-is; it falls back to YUY2 where the   | K (50) / K (50) / 4                   |
|                       | camera offers a raw format at that size and rate: the Kiyo)      |                                       |
| ds_newproc            | ``pyav_ds capture --frames N`` once per process                  | K' (15) / K' / 2                      |
| opencv_inproc         | ``opencv_ds cycle`` (CAP_DSHOW by index, skellycam's create-step | K' / K' / 2                           |
|                       | sets only: FOURCC, W, H, FPS)                                    |                                       |
| opencv_skellycam      | ``opencv_ds cycle --set-order skellycam-full                     | K' / K' / 2                           |
|                       | --skellycam-framerate -1``: skellycam's real open with its       |                                       |
|                       | DEFAULT_FRAMERATE -1 (the create-step FPS set is skipped; create |                                       |
|                       | sets + BUFFERSIZE + read, then apply: exposure, W, H, FOURCC     |                                       |
|                       | last); final format / fps / latency reported                     |                                       |
| opencv_skellycam_fps30| the same with a configured framerate of 30 (the FPS set is made) | K' / K' / 2                           |
| mf_modeswitch         | ``wincam cycle --alt-*``: default mode alternating with another  | K/2 (25) / K/2 / 2                    |
|                       | in-scope mode (960x720@30, else 720p60; ``capkit.switch_mode``)  |                                       |
| ds_modeswitch         | ``pyav_ds cycle --alt-*``                                        | K/2 (25) / K/2 / 2                    |

R = --reliability-cycles (400), K = --cycles (50), K' = --proc-cycles (15). Profile: --cyc-profile (a full run
defaults to ``reliability``, --quick to ``quick``).

W-CYC-381 (plan 6.1): in the reliability profile mf_inproc, ds_ffmpeg_inproc and mf_newproc rate 'yes' only when the
Wilson 95 % lower bound of first-frame-within-2-s is >= 0.99 (>= 381 failure-free cycles); below it they are
'partial (n too small for a 99 % claim ...)' or 'partial (99 % not shown ...)'. mf_newproc runs 400 cycles (Dom 2026-11-11), enough to
back the claim like the other two. Every other 'yes' is labelled
'yes (point estimate; n=..., Wilson lower ...)'. XP section 3's point-rate rule stays as its own criterion.

Segments: the Razer Kiyo Pro tends to wedge ~210 min after plug-in once it has streamed, so the runner cycles it in
its own early test, W-CYC-KIYO (tests/w_cyc_kiyo.py, right after W-RAW), and this test, last in the run, then cycles
the other cameras (``ctx.cyc_kiyo_first``). Run alone (``--only W-CYC``) it cycles every camera, the Kiyo first.
Each camera records its plug-in age when its variants start. ``<out>/<test>.partial.json`` is rewritten after every
variant, and a Ctrl-C returns the finished cameras and variants (result flag ``interrupted``), so an overrunning
overnight run keeps what it measured; --reanalyse falls back to the partial file, then to the rows on disk.

Mode scope (common/modescope.py, Dom 2026-11-08): the default mode and the mode-switch partner are chosen from the
modes with exactly 720 lines at >= 30 fps (``--all-modes`` / ``--min-fps`` / ``--min-height`` / ``--max-height``);
each camera records ``mode_scope`` (scope, advertised / in-scope / excluded counts) and ``activity_at_first_stream``
(``wincam activity``: other processes holding or streaming the camera, read without opening it). A camera without an
in-scope MJPEG mode is rated 'untested (scope)'.

Frame rate per cycle (all APIs, windows_results_20261106 section 11): ``fps_mismatch`` = the cycle's measured rate
(``fps_measured``: wincam cycle rows (wincam 1.2 and later; 1.1 rows lack it and count as not judged),
wincam/pyav_ds capture summaries, pyav_ds/opencv cycle rows) below 0.9 x the requested rate; ``n_fps_judged`` counts the cycles where it could be judged
(not judged under FPS_MIN_FRAMES = 20 frames per cycle: the rate then includes the start-up interval, so the quick
profile's 10-frame cycles are 'not judged (N too small)'). A low rate is
camera behaviour (e.g. auto-exposure in low light), shown in the evidence and the summary label; it does not change
the open/close reliability rating.

The OpenCV variants use the process-cycle count because each OpenCV cycle takes ~5 s (its property sets restart
the graph). Every failed cycle is classified with common.topology_model.classify_failure (HRESULT, errno, timeout).
The reliability criterion uses ``open_to_first_frame_ms`` (what a user waits for: enumerate/activate/open to the
first frame; for opencv_skellycam the first frame AFTER skellycam's apply step) for every API, so MF, PyAV and
OpenCV are compared on the same span; the tool's own first_frame_ms is kept as ``first_frame_ms_tool``.

Fixes from the 2026-11-06 run analysis (results/.../suite_20261106T181941Z/analysis/cyc_kiyo.md):
- B1: each camera gets a 1-frame MF health probe (``ctx.health_probe``) BEFORE its variants. A camera that fails it
  with a device fault (or that the suite's device-fault gate already marks faulted) is not cycled: every variant
  is rated with ``pre_existing_fault`` (untested: device fault since <ts>), not "no".
- B3/B6: ``ok`` in the rows is the open/first-frame/close outcome; the format is checked separately per row:
  ``format_mismatch`` (PyAV YUY2 fallback, OpenCV FOURCC readback not MJPG, MF readback not ok),
  ``size_mismatch``, ``fps_mismatch`` (OpenCV measured < 0.9 x requested). cycstats counts them and the verdict
  evidence carries the counts (common/rating.py caps a mismatch at "partial": "negotiated the requested format").
- B5: arrivals (LastArrivalDate) are snapshotted before and after EACH variant; a re-arrival of the camera is
  attributed to the cycle whose time window contains it (row ``utc``) and that cycle becomes a failure
  (``device_reset``); an unattributable re-arrival caps the variant at "partial".
- V2.4/N5: the opencv_skellycam variant. It changes the camera's exposure control (skellycam's apply step), so the
  exposure is read through DirectShow before the variant and restored after it.
- A camera that becomes faulted DURING this test (ctx.camera_faulted, set by the camcmd fault scan) gets one more
  health probe; if it still fails, its remaining variants are rated untested (device fault since <ts>).
After a variant that ended in failures the old same-API health capture still decides ``replug_suspected``.

Offline re-analysis of a finished run (no camera opened):
    python suite/windows/tests/w_cyc.py --reanalyse <run_dir> [--test W-CYC|W-CYC-KIYO] [--out <file>]
"""
from __future__ import annotations

import datetime as _dt
import inspect
import json
import sys
import time
from pathlib import Path

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
from common import cycstats, rating, results  # noqa: E402

TEST = "W-CYC"
#: the Kiyo Pro's segment of this test, run early (right after W-RAW) while the freshly plugged Kiyo is healthy
KIYO_TEST = "W-CYC-KIYO"
TIMEOUT_MS = 5000
#: OpenCV's property sets rebuild the DirectShow graph (3-4 s each cycle on the Logitech cameras; the Kiyo's did not
#: return within 5 s in the first self-test), so its calls get a longer bound; slow is then measured, not killed
OPENCV_TIMEOUT_MS = 15000
FPS_TOL = 0.9
#: a cycle's rate is judged only over >= this many frames: the tools' fps_measured = (frames - 1) / span includes the
#: start-up interval, which dominates a 10-frame quick cycle (smoke 2026-11-09: Kiyo 25.6 fps over 10 frames, 28.8
#: over 30, 29.6 steady)
FPS_MIN_FRAMES = 20
#: evidence fields the shared rating contract asks for (copied from the summary when rating.py does not add them)
CONTRACT_EVIDENCE = ("n", "n_ok", "success_rate", "wilson95", "open_to_first_frame_ms_p50", "format_mismatch_count",
                     "fps_mismatch_count", "size_mismatch_count", "device_reset_count", "n_ok_as_requested")
FORMAT_CRITERION = "negotiated the requested format"
#: where each tool stamps a cycle row's utc: True = at the END of the cycle (wincam), False = at its start
UTC_IS_END = {"mf": True, "ds": False, "opencv": False}


PROFILES = ("quick", "standard", "reliability")
RELIABILITY_CYCLES = 400        # >= 381 failure-free cycles bound success >= 99 % at the Wilson 95 % lower bound
RELIABILITY_NEWPROC = 400     # Dom 2026-11-11: >= 381 failure-free cycles for every camera and API in scope
#: plan 6.1 W-CYC-381: ">= 99 % per camera at the Wilson lower bound" per API (MF in-process and new-process; the
#: reliability profile adds DirectShow through the ffmpeg CLI). In the reliability profile these variants rate 'yes'
#: only when the Wilson 95 % lower bound of first-frame-within-2-s is >= 0.99 (in practice >= 381 failure-free
#: cycles); mf_newproc runs RELIABILITY_NEWPROC cycles, so it cannot back the claim and says so in its label
CLAIM_VARIANTS = ("mf_inproc", "ds_ffmpeg_inproc", "mf_newproc")
#: run only with run_suite.py --with-opencv (2026-11-12; capkit.opencv_enabled)
OPENCV_VARIANTS = ("opencv_inproc", "opencv_skellycam", "opencv_skellycam_fps30")
WILSON_CLAIM = 0.99
#: seconds per cycle on top of the N frames (calibrated on Gerald 2026-11-06; the ffmpeg CLI starts a process per
#: cycle: the 11-06 W-MULTI ds runs opened in ~1.4-2.0 s); the Kiyo takes ~1.5x
SECS_PER_CYCLE = {"mf_inproc": 1.5, "mf_newproc": 1.8, "ds_ffmpeg_inproc": 2.4, "ds_inproc": 1.8, "ds_newproc": 2.2,
                  "opencv_inproc": 6.0, "opencv_skellycam": 9.0, "opencv_skellycam_fps30": 9.0, "mf_modeswitch": 1.5,
                  "ds_modeswitch": 1.8}


def profile(ctx) -> str:
    p = getattr(getattr(ctx, "args", None), "cyc_profile", None)
    if p in PROFILES:
        return p
    return "quick" if ck.quick(ctx) else "reliability"


def counts(ctx) -> tuple[int, int, int]:
    k = int(ck.arg(ctx, "cycles", 50, 4))
    kp = int(ck.arg(ctx, "proc_cycles", 15, 2))
    n = int(ck.arg(ctx, "frames", 30, 10))
    return k, kp, n


def variant_counts(ctx) -> dict[str, int]:
    """Cycles per variant for the run's profile (module docstring table)."""
    k, kp, _n = counts(ctx)
    prof = profile(ctx)
    if prof == "quick":
        k, kp = min(k, 4), min(kp, 2)
    rel = int(getattr(getattr(ctx, "args", None), "reliability_cycles", None) or RELIABILITY_CYCLES)
    big = max(rel, k) if prof == "reliability" else k
    vc = {"mf_inproc": big, "mf_newproc": max(RELIABILITY_NEWPROC, kp) if prof == "reliability" else kp,
          "ds_ffmpeg_inproc": big, "ds_inproc": k, "ds_newproc": kp, "opencv_inproc": kp, "opencv_skellycam": kp,
          "opencv_skellycam_fps30": kp, "mf_modeswitch": max(2, k // 2), "ds_modeswitch": max(2, k // 2)}
    if not ck.opencv_enabled(ctx):   # 2026-11-12: OpenCV variants only with --with-opencv
        vc = {v: c for v, c in vc.items() if v not in OPENCV_VARIANTS}
    return vc


def estimate_s(ctx, segment: str | None = None) -> float:
    """Sum over cameras and variants of cycles x (per-cycle cost + N frames at 30 fps), the Kiyo x1.5, plus the
    per-camera probes and reads (~20 s). Calibrated on Gerald 2026-11-06 (C930e quick run). Only the cameras of
    this segment (W-CYC-KIYO: the Kiyo; W-CYC after it: the others)."""
    _k, _kp, n = counts(ctx)
    f = n / 30.0
    per_cam = sum(c * (SECS_PER_CYCLE[v] + f) for v, c in variant_counts(ctx).items()) + 20
    cams, _other = _segment_cameras(ctx, _resolve_segment(ctx, segment))
    return per_cam * sum(1.5 if c.get("is_kiyo") else 1.0 for c in cams)


def reliability_note(prof: str, vc: dict) -> str:
    return (f"a per-camera '>= 99 %' claim needs >= 381 failure-free cycles (Wilson 95 % lower bound); profile "
            f"{prof} runs {vc['mf_inproc']} mf_inproc, {vc['ds_ffmpeg_inproc']} ds_ffmpeg_inproc and "
            f"{vc['mf_newproc']} mf_newproc cycles per camera"
            + (f"; mf_newproc's {vc['mf_newproc']} cycles are a smaller sample that cannot back a 99 % claim "
               "(plan 6.1 asks for >= 381 per API; raise it with a longer run if that claim is needed)"
               if vc["mf_newproc"] < 381 else "")
            + ("; in the reliability profile mf_inproc / ds_ffmpeg_inproc / mf_newproc rate 'yes' only at a Wilson "
               "lower bound >= 0.99, the other variants carry 'point estimate' in their label"
               if prof == "reliability" else "; outside the reliability profile no variant backs a 99 % claim "
               "(labels say 'point estimate')"))


def apply_wilson_claim(rv: dict, summ: dict, claim_99: bool) -> None:
    """Plan 6.1 W-CYC-381 on top of XP section 3's point-rate rule (kept as its own criterion): the Wilson 95 % lower
    bound of first-frame-within-2-s must reach 0.99 for a '>= 99 %' claim. A claim variant (reliability profile)
    below it becomes 'partial' with the reason in its label; any other 'yes' below it is labelled a point estimate,
    so summary.md keeps the cells that back the claim apart from the rest."""
    n = summ.get("n") or 0
    lo = (summ.get("first_frame_within_wilson95") or [None])[0]
    if not n or not isinstance(lo, (int, float)):
        return
    met = lo >= WILSON_CLAIM
    rv.setdefault("criteria", []).append(
        {"criterion": f">= 99 % at the Wilson 95 % lower bound (W-CYC-381; needs >= 381 failure-free cycles)",
         "met": met if claim_99 else None,
         "detail": {"wilson95_lower": round(lo, 4), "n": n, "n_first_frame_within": summ.get("n_first_frame_within"),
                    "required_for_this_variant": claim_99}})
    ev = rv.setdefault("evidence", {})
    if isinstance(ev, dict):
        ev["wilson95_lower_first_frame_within"] = round(lo, 4)
        ev["claim_99_variant"] = claim_99
    if met or rv.get("rating") != "yes":
        return
    within = summ.get("n_first_frame_within")
    if claim_99:
        rv["rating"] = "partial"
        why = (f"n too small for a 99 % claim: {n} cycles" if within == n and n < 381 else
               f"99 % not shown at the Wilson lower bound over {n} cycles")
        rv["summary_label"] = f"partial ({why}; Wilson lower {lo:.3f})"
        rv["note"] = ("every point-rate criterion met, but the Wilson 95 % lower bound is below 0.99, so this "
                      "variant does not back a '>= 99 %' claim (plan 6.1 W-CYC-381)")
    else:
        rv["summary_label"] = f"yes (point estimate; n={n}, Wilson lower {lo:.3f})"


def camera_order(cams: list[dict]) -> list[dict]:
    """The Kiyo first (its healthy window after plug-in), then the others in discovery order."""
    return sorted(cams, key=lambda c: 0 if c.get("is_kiyo") else 1)


# ============================================================================================================ rows
def _mode_fps(mode_text: str | None) -> float | None:
    """The requested rate from a row's mode text ('MJPG 1280x720@30', '...@30000/1001')."""
    try:
        f = str(mode_text).rsplit("@", 1)[1].strip()
        if "/" in f:
            a, b = f.split("/", 1)
            return float(a) / float(b) if float(b) else None
        return float(f)
    except (IndexError, ValueError, TypeError):
        return None


def _too_few_frames(r: dict) -> bool:
    """The cycle delivered fewer than FPS_MIN_FRAMES frames (count known): its rate is not judged."""
    n = r.get("frames")
    return isinstance(n, int) and not isinstance(n, bool) and n < FPS_MIN_FRAMES


def fps_mismatch(r: dict, requested: float | None, streamed: bool) -> bool | None:
    """True when a streamed cycle's measured rate is below FPS_TOL x the requested rate; None when it cannot be
    judged (not streamed, no measured rate, no requested rate, fewer than FPS_MIN_FRAMES frames)."""
    fm = r.get("fps_measured")
    if not streamed or not requested or not isinstance(fm, (int, float)) or isinstance(fm, bool) or fm <= 0:
        return None
    if _too_few_frames(r):
        return None
    return fm < FPS_TOL * requested


def _mode_wh(mode_text: str | None) -> tuple[int, int] | None:
    try:
        wh = str(mode_text).split()[-1].split("@")[0]
        w, h = wh.split("x")
        return int(w), int(h)
    except (IndexError, ValueError):
        return None


def format_flags(r: dict, api: str) -> dict:
    """Per-row format checks (B3/B6). Returns {streamed_ok, format_mismatch, size_mismatch, fps_mismatch}; a flag is
    None when it cannot be judged (cycle failed, no readback)."""
    if api == "opencv":
        wh = _mode_wh(r.get("mode")) or (0, 0)
        fps = _mode_fps(r.get("mode")) or r.get("fps_requested") or 0
        tmp = dict(r)
        try:
            import opencv_ds  # noqa: PLC0415 - stdlib-only at import time (cv2 is imported inside main())
            tmp = opencv_ds.evaluate_row(tmp, wh[0], wh[1], fps)
        except Exception:  # noqa: BLE001
            tmp["streamed_ok"] = r.get("stage_failed") is None and (r.get("frames") or 0) >= 1
        if _too_few_frames(r):
            tmp["fps_mismatch"] = None
        return {k: tmp.get(k) for k in ("streamed_ok", "format_mismatch", "size_mismatch", "fps_mismatch",
                                        "final_fourcc", "final_size")}
    streamed = bool(r.get("ok"))
    fmt = None
    if streamed:
        if api == "ds":
            codec = r.get("codec")
            fmt = bool(r.get("format_fallback")) or (codec is not None and str(codec).lower() != "mjpeg")
        elif api == "mf":
            neg = r.get("negotiated_ok")
            fmt = None if neg is None else neg is False
    req = _mode_fps(r.get("mode")) or r.get("fps_requested")
    return {"streamed_ok": streamed, "format_mismatch": fmt, "size_mismatch": None,
            "fps_mismatch": fps_mismatch(r, req, streamed)}


def _norm_rows(rows: list[dict], api: str) -> list[dict]:
    """Normalise rows for cycstats: ok := streamed (open, first frame, close); format flags; first_frame_ms :=
    open_to_first_frame_ms; classify failures."""
    out = []
    for i, r in enumerate(rows):
        r = dict(r)
        r.setdefault("i", i)
        if "tool_ok" not in r:
            r["tool_ok"] = r.get("ok")
        if "first_frame_ms_tool" not in r:
            r["first_frame_ms_tool"] = r.get("first_frame_ms")
        if r.get("open_to_first_frame_ms") is not None:
            r["first_frame_ms"] = r["open_to_first_frame_ms"]
        fl = format_flags(r, api)
        r.update(fl)
        if not r.get("device_reset"):
            r["ok"] = bool(fl["streamed_ok"])
        r["ok_as_requested"] = bool(r["ok"]) and not any(r.get(k) is True for k in (
            "format_mismatch", "size_mismatch", "fps_mismatch"))
        if not r.get("ok") and "classification" not in r:
            if r.get("timed_out"):
                code = "timeout"
            elif api == "mf":
                code = r.get("hr")
            elif r.get("errno") is not None:
                code = f"OSError({r['errno']})"
            else:
                code = None
            r["classification"] = ck.classify(api, code, r.get("stage_failed"), frames=r.get("frames"),
                                              timed_out=bool(r.get("timed_out")),
                                              in_use_by_other=r.get("in_use_by_other"))
            r["error_class"] = r.get("error_class") or r["classification"].get("class")
        r.pop("steps", None)
        r.pop("ffmpeg_log", None)
        out.append(r)
    return out


def _newproc_row(i: int, api: str, mode, s: dict | None, run: dict, n: int, utc: str | None = None) -> dict:
    s = s or {}
    t = s.get("timings") or {}
    fr = s.get("frames") or {}
    err = s.get("error") or {}
    code, stage, _ = ck.failure_code(api, s, run)
    ok = bool(s.get("ok")) and not run.get("timed_out")
    if api == "ds" and s.get("format_fallback"):
        ok = bool((fr.get("total") or 0) > 0) and not run.get("timed_out")
    row = {"i": i, "mode": mode.text, "ok": ok, "stage_failed": None if ok else (stage or "process"),
           "timed_out": bool(run.get("timed_out")) or bool(s.get("timed_out")),
           "frames": fr.get("total"), "frames_ok": fr.get("ok"),
           "first_frame_ms": t.get("first_frame_ms"), "open_to_first_frame_ms": t.get("open_to_first_frame_ms"),
           "close_ms": t.get("close_ms"), "activate_ms": t.get("activate_ms"), "open_ms": t.get("open_ms"),
           "process_elapsed_s": run.get("elapsed_s"), "rc": run.get("rc"),
           "unreleasable": bool(s.get("unreleasable")), "format_fallback": s.get("format_fallback"),
           "codec": ((s.get("stream") or s.get("negotiated") or {}).get("codec")) if api == "ds" else None,
           "fps_measured": s.get("fps_measured"), "utc": utc, "gate_skipped": bool(run.get("gate_skipped")) or None}
    if api == "mf":
        row["hr"] = err.get("hr")
        row["hr_name"] = err.get("hr_name")
        row["negotiated_ok"] = (s.get("negotiated") or {}).get("readback_ok")
    else:
        row["errno"] = err.get("errno")
        row["error"] = err.get("message") or err.get("reason")
    if not s:
        row["error"] = "no JSON from the tool" + (" (process timed out)" if run.get("timed_out") else "")
    return row


# ============================================================================================================ runs
def _inproc(ctx, cam, api: str, mode, alt, k: int, n: int, out: Path, set_order: str = "skellycam",
            engine: str = "pyav", sk_fps: float | None = None) -> tuple[list[dict], dict]:
    out.mkdir(parents=True, exist_ok=True)
    per_cycle_s = 4 * TIMEOUT_MS / 1000.0 + 3
    timeout_s = k * per_cycle_s + 60
    extra = []
    idx = how = None
    if api == "mf":
        argv = ck.wincam_argv(ctx, "cycle", "--api", "mf", "--device", cam["mf_symlink"], "--width", mode.w,
                              "--height", mode.h, "--fps", mode.fps_arg, "--cycles", k, "--frames", n,
                              "--timeout-ms", TIMEOUT_MS, "--out", out, "--gap-ms", 100)
        if alt:
            extra = ["--alt-width", alt.w, "--alt-height", alt.h, "--alt-fps", alt.fps_arg]
    elif api == "ds":
        argv = ck.helper_argv(ctx, ck.PYAV_DS, "cycle", "--device", cam.get("ds_path") or cam.get("ds_name"),
                              "--width", mode.w, "--height", mode.h, "--fps", mode.ds_fps, "--cycles", k,
                              "--frames", n, "--timeout-ms", TIMEOUT_MS, "--out", out, "--gap-ms", 100)
        if engine == "ffmpeg":
            argv += ["--engine", "ffmpeg"]
            timeout_s = k * (per_cycle_s + 2.0) + 60          # one ffmpeg.exe start per cycle
        if alt:
            extra = ["--alt-width", alt.w, "--alt-height", alt.h, "--alt-fps", alt.ds_fps]
    else:  # opencv: resolve the DirectShow index now (indices change between runs)
        idx, how = _opencv_index(ctx, cam)
        if idx is None:
            return [], {"error": f"no DirectShow index for this camera ({how})"}
        argv = ck.helper_argv(ctx, ck.OPENCV_DS, "cycle", "--index", idx, "--expect-path", cam.get("ds_path") or "",
                              "--width", mode.w, "--height", mode.h, "--fps", f"{mode.fps:.6g}", "--cycles", k,
                              "--frames", n, "--timeout-ms", OPENCV_TIMEOUT_MS, "--out", out, "--gap-ms", 100,
                              "--set-order", set_order)
        if set_order == "skellycam-full" and sk_fps is not None:
            argv += ["--skellycam-framerate", f"{sk_fps:g}"]
        nsteps = 7 if set_order == "skellycam-full" else 4
        timeout_s = k * (nsteps * OPENCV_TIMEOUT_MS / 1000.0 + 6) + 60
    # a stale cycles.jsonl from an earlier run in the same folder must not be read back as this run's rows
    try:
        (out / "cycles.jsonl").unlink()
    except OSError:
        pass
    r = ctx.camcmd(argv + extra, timeout_s=timeout_s)
    s = ck.parse_json(r)
    rows = results.read_jsonl(out / "cycles.jsonl")
    info = {"run": ck.run_brief(r), "tool_summary": (s or {}).get("summary"), "cycles_requested": k,
            "cycles_recorded": len(rows), "gate_skipped": bool(r.get("gate_skipped")) or None}
    if api == "ds":
        info["engine"] = engine
    if api == "opencv":
        info["opencv_index"] = idx
        info["index_resolution"] = how
        info["set_order"] = set_order
        if set_order == "skellycam-full":
            info["skellycam_framerate"] = sk_fps
    if len(rows) < k and not r.get("gate_skipped"):
        info["note"] = ("fewer cycles recorded than requested: the tool stopped (hung call -> exit 5) or the "
                        "process was killed at the timeout")
    return rows, info


def _opencv_index(ctx, cam) -> tuple[int | None, str]:
    """DirectShow enumeration index of this camera right now (wincam list: enumeration only, no lock needed)."""
    try:
        import suitectx  # noqa: PLC0415
        wl = suitectx.wincam_list(ctx.wincam)
        for d in (wl.get("ds") or {}).get("devices") or []:
            if cam.get("ds_path") and (d.get("device_path") or "").lower() == cam["ds_path"].lower():
                return d.get("index"), "wincam list DS order matched by DevicePath (OpenCV CAP_DSHOW uses this order)"
    except Exception as e:  # noqa: BLE001
        return cam.get("ds_index"), f"wincam list failed ({e!r}); using discovery ds_index"
    return cam.get("ds_index"), "not found in a fresh wincam list; using discovery ds_index"


def _newproc(ctx, cam, api: str, mode, kp: int, n: int, out: Path) -> tuple[list[dict], dict]:
    rows = []
    for i in range(kp):
        od = out / f"p{i:03d}"
        utc = results.utc_now_iso()
        if api == "mf":
            s, r = ck.wincam_capture(ctx, cam, mode, od, frames=n, save="none", timeout_ms=TIMEOUT_MS)
        else:
            s, r = ck.pyav_capture(ctx, cam, mode, od, frames=n, save="none", timeout_ms=TIMEOUT_MS)
        # the tool's own start time is after the camera-lock wait (the W-KIYO poller can hold the lock)
        rows.append(_newproc_row(i, api, mode, s, r, n, (s or {}).get("utc_started") or utc))
        if (s or {}).get("gate_skipped"):
            break
        time.sleep(0.1)
    return rows, {"cycles_requested": kp, "cycles_recorded": len(rows)}


def _health(ctx, cam, mode, out: Path, api: str = "mf", engine: str = "pyav") -> dict:
    """One 10-frame capture through the same API family as the variant that ended in failures (MF for mf_*,
    DirectShow via pyav_ds for ds_* and opencv_*, the ffmpeg CLI for ds_ffmpeg_*), so an MF-only lockout
    (MF_E_REBOOT_REQUIRED) is not blamed on DirectShow and vice versa."""
    if api == "mf":
        s, r = ck.wincam_capture(ctx, cam, mode, out, frames=10, save="none", timeout_ms=TIMEOUT_MS)
        ok = bool((s or {}).get("ok"))
    else:
        s, r = ck.pyav_capture(ctx, cam, mode, out, frames=10, save="none", timeout_ms=TIMEOUT_MS, engine=engine)
        ok = bool((s or {}).get("ok")) or (bool((s or {}).get("format_fallback"))
                                           and ((s or {}).get("frames") or {}).get("total", 0) > 0)
    return {"ok": ok, "api": "mf" if api == "mf" else "ds", "run": r, "error": (s or {}).get("error")}


# ------------------------------------------------------------------------------------------------ exposure save/restore
def _read_exposure(ctx, cam) -> dict | None:
    """The exposure control as read through DirectShow (wincam controls --read-only), or None."""
    if not cam.get("ds_path"):
        return None
    j, r = ck.get_controls(ctx, cam, "ds", timeout_ms=3000, timeout_s=30)
    c = ck.control_table(j).get("exposure")
    if not c:
        return None
    return {"value": c.get("value"), "flags": c.get("flags_names") or [], "run": r}


def _restore_exposure(ctx, cam, orig: dict | None) -> dict:
    """Put the exposure control back as it was before opencv_skellycam (auto stays auto, manual gets its value)."""
    if not orig:
        return {"restored": None, "note": "exposure not readable before the variant; nothing to restore"}
    auto = "auto" in (orig.get("flags") or [])
    if auto:
        j, r = ck.set_controls(ctx, cam, "ds", {"exposure": "auto"})
    elif orig.get("value") is not None:
        j, r = ck.set_controls(ctx, cam, "ds", {"exposure": orig["value"]}, flags="manual")
    else:
        return {"restored": None, "note": "no original value"}
    now = _read_exposure(ctx, cam) or {}
    ok = ("auto" in (now.get("flags") or [])) if auto else now.get("value") == orig.get("value")
    return {"restored": bool(ok), "original": {k: orig.get(k) for k in ("value", "flags")},
            "after": {k: now.get(k) for k in ("value", "flags")}, "set_run": r}


# ============================================================================================================ arrivals
def _parse_utc(s) -> _dt.datetime | None:
    if not s:
        return None
    try:
        t = _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)


def _row_duration_s(r: dict) -> float:
    o2f = r.get("open_to_first_frame_ms") or r.get("first_frame_ms") or r.get("open_ms") or 0
    o2f = o2f if isinstance(o2f, (int, float)) and o2f > 0 else 0
    fr = (r.get("frames") or 0) / 30.0
    cl = r.get("close_ms") if isinstance(r.get("close_ms"), (int, float)) and r["close_ms"] > 0 else 0
    return o2f / 1000.0 + fr + cl / 1000.0 + 2.0


def attribute_re_arrival(rows: list[dict], arrival_utc: str | None, utc_is_end: bool) -> int | None:
    """Index of the row whose time window contains ``arrival_utc``. A row's ``utc`` is its start (pyav_ds,
    opencv_ds, new-process rows) or its end (wincam cycle); windows run start->next start or prev end->end, and
    the outermost rows get start/end +- an estimated cycle duration. None when outside every window."""
    t = _parse_utc(arrival_utc)
    if t is None:
        return None
    ts = [(i, _parse_utc(r.get("utc"))) for i, r in enumerate(rows)]
    ts = [(i, x) for i, x in ts if x is not None]
    for j, (i, x) in enumerate(ts):
        if utc_is_end:
            lo = ts[j - 1][1] if j > 0 else x - _dt.timedelta(seconds=_row_duration_s(rows[i]))
            hi = x
            if lo < t <= hi:
                return i
        else:
            lo = x
            hi = ts[j + 1][1] if j + 1 < len(ts) else x + _dt.timedelta(seconds=_row_duration_s(rows[i]))
            if lo <= t < hi:
                return i
    return None


def apply_re_arrival(rows: list[dict], arrival_utc: str | None, api: str) -> int | None:
    """Mark the cycle that contains the re-arrival as a failed 'device_reset' cycle; returns its index."""
    idx = attribute_re_arrival(rows, arrival_utc, UTC_IS_END.get(api, False))
    if idx is not None:
        r = rows[idx]
        r["device_reset"] = True
        r["device_reset_arrival_utc"] = arrival_utc
        r["ok_before_reset"] = r.get("ok")
        r["ok"] = False
        r["ok_as_requested"] = False
        r["stage_failed_before_reset"] = r.get("stage_failed")
        r["stage_failed"] = r.get("stage_failed") or "device_reset"
        r["error_class"] = "device_reset"
    return idx


def _camera_re_arrival(before: dict, after: dict, key: str) -> dict | None:
    b = ((before or {}).get("cameras") or {}).get(key) or {}
    a = ((after or {}).get("cameras") or {}).get(key) or {}
    if not b or not a:
        return None
    if b.get("last_arrival") != a.get("last_arrival") or b.get("present") != a.get("present"):
        return {"before": b.get("last_arrival"), "after": a.get("last_arrival"), "present_before": b.get("present"),
                "present_after": a.get("present"), "problem_code_after": a.get("problem_code")}
    return None


# ============================================================================================================ rating
def rate_variant(summ: dict, replug: bool | None, pre_existing_fault: bool = False, fault: dict | None = None,
                 device_reset_unattributed: bool = False, claim_99: bool = False) -> dict:
    """common.rating.rate_reliability plus the contract evidence; compatible with rating.py versions that do not
    know ``pre_existing_fault`` or the format criterion yet (then they are applied here, the same way)."""
    params = inspect.signature(rating.rate_reliability).parameters
    kw = {"replug_needed": replug}
    if "pre_existing_fault" in params:
        kw["pre_existing_fault"] = pre_existing_fault
    if "fault" in params and fault:
        kw["fault"] = {k: fault.get(k) for k in ("since_utc", "test", "mode", "code", "stage", "class", "source",
                                                 "plug_in_age_s")} | {"first_fault_utc": fault.get("since_utc")}
    if pre_existing_fault and "pre_existing_fault" not in params:
        reason = "camera faulted before the test (pre-existing device fault, replug needed)"
        if fault:
            reason = (f"device fault since {fault.get('since_utc')} ({fault.get('test')}, {fault.get('code')}); "
                      "camera faulted before the test, replug needed")
        rv = rating.untested(reason, {"pre_existing_fault": True})
    else:
        rv = rating.rate_reliability(summ, **kw)
    ev = rv.get("evidence")
    if not isinstance(ev, dict):
        ev = {} if ev is None else {"rating_evidence": ev}
        rv["evidence"] = ev
    if not pre_existing_fault:
        apply_wilson_claim(rv, summ, claim_99)
    for k in CONTRACT_EVIDENCE:
        ev.setdefault(k, summ.get(k))
    ev.setdefault("success_wilson95", summ.get("wilson95"))
    ev["pre_existing_fault"] = bool(pre_existing_fault)
    if fault:
        ev["fault"] = {k: fault.get(k) for k in ("since_utc", "test", "mode", "code", "stage", "class",
                                                 "source", "plug_in_age_s")}
        ev.setdefault("device_fault", True)
        ev.setdefault("first_fault_utc", fault.get("since_utc"))
    crit = rv.setdefault("criteria", [])
    mism = (summ.get("format_mismatch_count") or 0) + (summ.get("size_mismatch_count") or 0)
    if not any(FORMAT_CRITERION in str(c.get("criterion", "")) for c in crit) and summ.get("n"):
        crit.append({"criterion": FORMAT_CRITERION, "met": mism == 0,
                     "detail": {k: summ.get(k) for k in ("format_mismatch_count", "size_mismatch_count",
                                                          "fps_mismatch_count")}})
        if mism and rv.get("rating") == "yes":
            rv["rating"] = "partial"
            rv["note"] = "opened and streamed, but not in the requested format/size"
    if summ.get("n"):
        resets = (summ.get("device_reset_count") or 0) + (1 if device_reset_unattributed else 0)
        crit.append({"criterion": "no device reset (re-enumeration) during the variant", "met": resets == 0,
                     "detail": {"device_reset_count": summ.get("device_reset_count"),
                                "unattributed_re_arrival": device_reset_unattributed}})
        if resets and rv.get("rating") == "yes":
            rv["rating"] = "partial"
            rv["note"] = "the device re-enumerated during the variant"
    if summ.get("n"):
        judged, slow = summ.get("n_fps_judged"), summ.get("fps_mismatch_count") or 0
        ev["n_fps_judged"] = judged
        ev["fps_rule"] = (f"fps_mismatch = measured rate < {FPS_TOL:g} x requested; camera behaviour, reported, not "
                          "part of the open/close reliability rating; cycles with fewer than "
                          f"{FPS_MIN_FRAMES} frames are not judged (the start-up interval dominates their rate)")
        if not judged and summ.get("n_ok"):
            ev["fps_not_judged"] = f"N too small: fewer than {FPS_MIN_FRAMES} frames per cycle (quick profile)"
        if slow and rv.get("rating") in ("yes", "partial"):
            lab = rv.get("summary_label") or rv["rating"]
            tag = f"rate < {FPS_TOL:.0%} of requested in {slow}/{judged}"
            rv["summary_label"] = f"{lab[:-1]}; {tag})" if lab.endswith(")") else f"{lab} ({tag})"
    if rv.get("rating") == "no":
        sr = summ.get("success_rate")
        # B8: "no (latency)" = it opened (>= 95%) but the first frame came too late; "no (failures)" otherwise
        rv.setdefault("no_reason", "latency" if sr is not None and sr >= 0.95 else "failures")
    return rv


# ============================================================================================================ run
#: skellycam's DEFAULT_FRAMERATE: -1 skips the create-step FPS set (create_cv2_video_capture.py)
SKELLYCAM_DEFAULT_FRAMERATE = -1.0


def _plan(counts_by: dict[str, int], alt) -> list[tuple]:
    """[(variant, api, kind, alt mode, cycles, options)] in run order: the reliability variants first."""
    c = counts_by
    plan = [("mf_inproc", "mf", "in", None, c["mf_inproc"], {}),
            ("ds_ffmpeg_inproc", "ds", "in", None, c["ds_ffmpeg_inproc"], {"engine": "ffmpeg"}),
            ("mf_newproc", "mf", "new", None, c["mf_newproc"], {}),
            ("ds_inproc", "ds", "in", None, c["ds_inproc"], {"engine": "pyav"}),
            ("ds_newproc", "ds", "new", None, c["ds_newproc"], {"engine": "pyav"})]
    if all(v in c for v in OPENCV_VARIANTS):   # only with --with-opencv (variant_counts leaves them out otherwise)
        plan += [("opencv_inproc", "opencv", "in", None, c["opencv_inproc"], {"set_order": "skellycam"}),
                 ("opencv_skellycam", "opencv", "in", None, c["opencv_skellycam"],
                  {"set_order": "skellycam-full", "sk_fps": SKELLYCAM_DEFAULT_FRAMERATE}),
                 ("opencv_skellycam_fps30", "opencv", "in", None, c["opencv_skellycam_fps30"],
                  {"set_order": "skellycam-full", "sk_fps": 30.0})]
    if alt is not None:
        plan += [("mf_modeswitch", "mf", "in", alt, c["mf_modeswitch"], {}),
                 ("ds_modeswitch", "ds", "in", alt, c["ds_modeswitch"], {"engine": "pyav"})]
    return plan


def _has(ctx, name: str) -> bool:
    return callable(getattr(ctx, name, None))


def _skip_all(ctx, cam, plan, cres, verdicts, why: str, fault: dict | None, pre: bool, start: int = 0) -> None:
    for name, *_ in plan[start:]:
        if name in cres["variants"]:
            continue
        cres["variants"][name] = {"skipped": why}
        if pre:
            rv = rate_variant({"n": 0}, None, pre_existing_fault=True, fault=fault)
        else:
            rv = rating.untested(why, {"device_fault": True, "fault_during_test": True, "pre_existing_fault": False,
                                       "fault": fault, "first_fault_utc": (fault or {}).get("since_utc")})
        rv["note"] = "untested: " + why
        rv["variant"] = name
        verdicts[f"reliability|{cam['key']}|{name}"] = rv


def _segment_cameras(ctx, segment: str | None) -> tuple[list[dict], list[dict]]:
    """(cameras this run cycles, cameras left to another segment). segment None: every camera (Kiyo first);
    "kiyo": only the Kiyo Pro (W-CYC-KIYO, run early in its healthy window); "rest": every camera but the Kiyo."""
    order = camera_order(list(ctx.cameras))
    if segment == "kiyo":
        return [c for c in order if c.get("is_kiyo")], [c for c in order if not c.get("is_kiyo")]
    if segment == "rest":
        return [c for c in order if not c.get("is_kiyo")], [c for c in order if c.get("is_kiyo")]
    return order, []


def _resolve_segment(ctx, segment: str | None) -> str | None:
    """The main W-CYC leaves the Kiyo to W-CYC-KIYO when the runner planned that segment (ctx.cyc_kiyo_first)."""
    if segment is None and getattr(ctx, "cyc_kiyo_first", False):
        return "rest"
    return segment


def _write_partial(ctx, tid: str, res: dict, meas: dict, verdicts: dict, errors: list) -> None:
    """<out>/<tid>.partial.json with everything finished so far (after each variant): a Ctrl-C, an exception or a
    crash late in the ~4 h test keeps the finished cameras' verdicts, and --reanalyse can rebuild from it."""
    try:
        part = {k: v for k, v in res.items() if k != "_t0"}
        part.update(partial=True, utc_written=results.utc_now_iso(), measurements=meas, verdicts=verdicts,
                    errors=errors)
        results.write_json(Path(ctx.out_dir) / f"{tid}.partial.json", part)
    except Exception as e:  # noqa: BLE001 - the partial file must never break the test
        try:
            ctx.log(f"{tid}: could not write the partial result: {e!r}")
        except Exception:  # noqa: BLE001
            pass


def run(ctx, segment: str | None = None) -> dict:
    segment = _resolve_segment(ctx, segment)
    tid = KIYO_TEST if segment == "kiyo" else TEST
    order, elsewhere = _segment_cameras(ctx, segment)
    res = ck.new_result(ctx, tid, order)
    arr0 = ck.arrivals_before(ctx)
    k, kp, n = counts(ctx)
    prof = profile(ctx)
    vc = variant_counts(ctx)
    errors: list = []
    verdicts: dict = {}
    per_cam: dict = {}
    cache: dict = {}
    raw = Path(ctx.raw_dir) / tid
    small = Path(ctx.out_dir) / tid

    def meas_now() -> dict:
        return {"cycles": k, "proc_cycles": kp, "frames": n, "timeout_ms": TIMEOUT_MS, "quick": ck.quick(ctx),
                "profile": prof, "cycles_per_variant": vc, "camera_order": [c["key"] for c in order],
                "segment": segment or "all",
                "cameras_in_other_segment": {c["key"]: (TEST if segment == "kiyo" else KIYO_TEST) for c in elsewhere},
                "reliability_note": reliability_note(prof, vc),
                "cameras": per_cam,
                "criterion_note": "first frame within 2 s is measured from the start of the open "
                                  "(open_to_first_frame_ms); ok = opened, first frame, closed; format checked "
                                  "separately (format_mismatch)"}

    def save_partial() -> None:
        _write_partial(ctx, tid, res, meas_now(), verdicts, errors)

    ctx.log(f"{tid}: profile {prof}: cycles per variant {vc}, N={n} frames, {len(order)} cameras in order "
            f"{[c.get('name') for c in order]}"
            + (f"; {[c.get('name') for c in elsewhere]} cycled in {TEST if segment == 'kiyo' else KIYO_TEST}"
               if elsewhere else ""))
    interrupted = False
    try:
        for cam in order:
            slug = ck.cam_slug(cam)
            fm, _ = ck.get_formats(ctx, cam, cache)
            advertised = ck.mjpeg_modes(fm)
            # mode scope (common/modescope.py): default + mode-switch partner both in scope (>= 30 fps, >= 720 lines)
            modes, scope = ck.scoped(ctx, advertised)
            mode = ck.default_mode(modes) if modes else None
            alt = ck.switch_mode(modes, mode)
            scope.update(default_mode=mode.text if mode else None, switch_mode=alt.text if alt else None)
            cres: dict = {"name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"), "mode": mode.text if mode else None,
                          "alt_mode": alt.text if alt else None, "mode_scope": scope, "variants": {}}
            if mode is not None and alt is None:
                cres["alt_mode_note"] = "only one in-scope MJPEG mode: no mode-switch variants (--all-modes widens it)"
            if _has(ctx, "plug_in_age_s"):
                age, la = ctx.plug_in_age_s(cam)
                cres["plug_in_age_at_start_s"], cres["last_arrival_at_start"] = age, la
            per_cam[cam["key"]] = cres
            plan = _plan(vc, alt)
            if advertised and not modes:
                scope["untested_reason"] = ck.modescope.no_scope_mode_reason(ck.mode_scope(ctx), len(advertised))
                ctx.log(f"{tid}: {cam.get('name')}: {scope['untested_reason']}")
                for name, *_ in plan:
                    cres["variants"][name] = {"skipped": scope["untested_reason"]}
                    rv = ck.scope_untested(ctx, scope)
                    rv["variant"] = name
                    verdicts[f"reliability|{cam['key']}|{name}"] = rv
                continue
            # ---- B1: is the camera already faulted (suite gate) or does it fail a 1-frame probe now? (checked before
            # the no-mode bail-out: a wedged camera whose format read fails must still be recorded as faulted)
            gated = ctx.camera_gated(cam) if _has(ctx, "camera_gated") else None
            if mode is None and not gated:
                if _has(ctx, "health_probe"):
                    pre = ctx.health_probe(cam, test=tid, mode=None, reason="W-CYC probe (no MJPEG mode listed)")
                    cres["pre_probe"] = {kk: pre.get(kk) for kk in ("ok", "utc", "code", "stage", "class", "fault_like",
                                                                     "frames", "mode", "elapsed_s")}
                    if not pre.get("ok") and (pre.get("fault_like") or ctx.camera_faulted(cam)):
                        f = ctx.camera_faulted(cam) or {}
                        why = ctx.fault_reason(cam) or f"device fault at the pre-test probe ({pre.get('code')})"
                        cres["pre_existing_fault"] = f
                        ctx.log(f"{tid}: {cam.get('name')}: no MJPEG mode listed and the probe failed "
                                f"({pre.get('code')}); variants skipped")
                        _skip_all(ctx, cam, plan, cres, verdicts, why, f, pre=True)
                        continue
                cres["error"] = "no MJPEG mode found (formats failed?)"
                errors.append({"camera": cam["key"], "error": cres["error"]})
                continue
            if gated:
                why = ctx.fault_reason(cam) or "device fault"
                cres["pre_existing_fault"] = gated
                ctx.log(f"{tid}: {cam.get('name')} skipped: {why}")
                _skip_all(ctx, cam, plan, cres, verdicts, why, gated, pre=True)
                continue
            # who else uses this camera right before its first stream (wincam activity: opens no camera)
            cres["activity_at_first_stream"] = ck.activity_for_camera(ctx, cam)
            if _has(ctx, "health_probe"):
                pre = ctx.health_probe(cam, test=tid, mode=mode, reason="W-CYC probe before the camera's variants")
                cres["pre_probe"] = {kk: pre.get(kk) for kk in ("ok", "utc", "code", "stage", "class", "fault_like",
                                                                 "frames", "open_to_first_frame_ms", "elapsed_s")}
                if not pre.get("ok") and (pre.get("fault_like") or ctx.camera_faulted(cam)):
                    f = ctx.camera_faulted(cam) or {}
                    why = ctx.fault_reason(cam) or f"device fault at the pre-test probe ({pre.get('code')})"
                    cres["pre_existing_fault"] = f
                    ctx.log(f"{tid}: {cam.get('name')} failed its pre-test probe ({pre.get('code')}); variants skipped")
                    _skip_all(ctx, cam, plan, cres, verdicts, why, f, pre=True)
                    continue
            probed_after_fault = False
            for vi, (name, api, kind, altm, cycles, opts) in enumerate(plan):
                if api == "mf" and not cam.get("mf_symlink") or api in ("ds", "opencv") and not cam.get("ds_path"):
                    cres["variants"][name] = {"skipped": f"no {api} device link"}
                    continue
                # ---- a fault raised during this test (camcmd scan / health capture): probe once, then stop
                if _has(ctx, "camera_faulted") and ctx.camera_faulted(cam):
                    if not probed_after_fault:
                        probed_after_fault = True
                        hp = ctx.health_probe(cam, test=tid, mode=mode, reason=f"fault during {tid}, before {name}")
                        cres.setdefault("probes_during_test", []).append(
                            {kk: hp.get(kk) for kk in ("ok", "utc", "code", "class", "recovered")})
                    if ctx.camera_faulted(cam):
                        f = ctx.camera_faulted(cam)
                        why = ctx.fault_reason(cam) or "device fault"
                        ctx.log(f"{tid}: {cam.get('name')}: remaining variants skipped ({why})")
                        _skip_all(ctx, cam, plan, cres, verdicts, why, f, pre=False, start=vi)
                        break
                t0 = time.monotonic()
                a_before = ck.arrivals_before(ctx)
                exp_orig = None
                skellycam_apply = opts.get("set_order") == "skellycam-full"
                try:
                    if skellycam_apply:
                        exp_orig = _read_exposure(ctx, cam)
                    if kind == "in":
                        rows, info = _inproc(ctx, cam, api, mode, altm, cycles, n, raw / slug / name,
                                             set_order=opts.get("set_order") or "skellycam",
                                             engine=opts.get("engine") or "pyav", sk_fps=opts.get("sk_fps"))
                    else:
                        rows, info = _newproc(ctx, cam, api, mode, cycles, n, raw / slug / name)
                except Exception as e:  # noqa: BLE001
                    errors.append({"camera": cam["key"], "variant": name, "exception": repr(e)})
                    cres["variants"][name] = {"exception": repr(e)}
                    continue
                finally:
                    if skellycam_apply:
                        try:
                            cres.setdefault("exposure_restore", {})[name] = _restore_exposure(ctx, cam, exp_orig)
                            if cres["exposure_restore"][name].get("restored") is False:
                                errors.append({"camera": cam["key"], "variant": name,
                                               "exposure_restore_not_verified": cres["exposure_restore"][name]})
                        except Exception as e:  # noqa: BLE001
                            errors.append({"camera": cam["key"], "variant": name,
                                           "exposure_restore_exception": repr(e)})
                a_after = ck.arrivals_before(ctx)
                rows = _norm_rows(rows, api)
                # ---- B5: a re-arrival of THIS camera during the variant is a device-reset failure
                rearr = _camera_re_arrival(a_before, a_after, cam["key"])
                unattributed = False
                if rearr:
                    idx = apply_re_arrival(rows, rearr.get("after"), api)
                    rearr["cycle"] = idx
                    unattributed = idx is None
                    ctx.log(f"{tid}: {cam.get('name')} {name}: RE-ARRIVAL {rearr.get('before')} -> {rearr.get('after')}"
                            f" (cycle {idx})")
                results.write_json(small / slug / f"{name}_cycles.json", rows)
                summ = cycstats.summarize_cycles(rows)
                v = {"rows_file": f"{tid}/{slug}/{name}_cycles.json", "info": info, "summary": summ,
                     "elapsed_s": round(time.monotonic() - t0, 1),
                     "format_fallbacks": sum(1 for r in rows if r.get("format_fallback")),
                     "re_arrival": rearr, "arrivals_changed": suitectx_diff(a_before, a_after)}
                if api == "opencv":
                    v["fourccs"] = sorted({str((r.get("sets") or {}).get("got_fourcc")) for r in rows})
                    v["final"] = opencv_final(rows)
                # health probe right after a variant that ended in failures, through the same API family; the
                # replug verdict belongs to THAT variant only
                if summ.get("trailing_failures", 0) and not info.get("gate_skipped"):
                    h = _health(ctx, cam, mode, raw / slug / f"health_after_{name}", api, opts.get("engine") or "pyav")
                    v["health_after"] = {"ok": h["ok"], "api": h["api"], "error": h.get("error"), "run": h["run"]}
                    v["replug_suspected"] = not h["ok"]
                else:
                    v["replug_suspected"] = False
                cres["variants"][name] = v
                rv = rate_variant(summ, v.get("replug_suspected"), device_reset_unattributed=unattributed,
                              claim_99=prof == "reliability" and name in CLAIM_VARIANTS)
                rv["variant"] = name
                verdicts[f"reliability|{cam['key']}|{name}"] = rv
                save_partial()
                ctx.log(f"{tid}: {cam.get('name')} {name}: {summ['n_ok']}/{summ['n']} ok, "
                        f"first frame within 2 s {summ['n_first_frame_within']}/{summ['n']}, hangs {summ['hangs']}, "
                        f"format mismatch {summ.get('format_mismatch_count')}, rate < {FPS_TOL:g} x requested "
                        f"{summ.get('fps_mismatch_count')}/{summ.get('n_fps_judged')} judged"
                        + (f", final {v['final'].get('fourccs')} {v['final'].get('fps_measured_p50')} fps"
                           if api == "opencv" else "")
                        + (f", health after: {'ok' if v['health_after']['ok'] else 'FAILED'}"
                           if "health_after" in v else "") + f" -> {rv['rating']}")
            cres["replug_suspected"] = any(v.get("replug_suspected") for v in cres["variants"].values())
            save_partial()
    except KeyboardInterrupt:
        # Ctrl-C (e.g. stopping an overrunning overnight run): keep every finished camera and variant
        interrupted = True
        errors.append({"interrupted": f"Ctrl-C during {tid}; the cameras and variants finished so far are kept"})
        ctx.log(f"{tid}: interrupted (Ctrl-C); returning the finished cameras and variants")
    meas = meas_now()
    meas["arrivals"] = ck.arrivals_after(ctx, arr0)
    out = results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)
    if interrupted:
        out["interrupted"] = True       # run_suite.run_one treats this as a Ctrl-C after writing the result
    return out


def suitectx_diff(before: dict, after: dict) -> list | None:
    try:
        import suitectx  # noqa: PLC0415
        if "cameras" in (before or {}) and "cameras" in (after or {}):
            return suitectx.diff_arrivals(before, after)
    except Exception:  # noqa: BLE001
        pass
    return None


def opencv_final(rows: list[dict]) -> dict:
    """What the OpenCV open ended in: final FOURCCs / sizes, measured fps, latency (streamed cycles)."""
    st = [r for r in rows if r.get("ok") or r.get("streamed_ok")]
    fps = cycstats.percentiles((r.get("fps_measured") for r in st), drop_negative=True)
    o2f = cycstats.percentiles((r.get("open_to_first_frame_ms") for r in st), drop_negative=True)
    cff = cycstats.percentiles((r.get("create_first_frame_ms") for r in st), drop_negative=True)
    return {"fourccs": sorted({str(r.get("final_fourcc")) for r in st}),
            "sizes": sorted({str(r.get("final_size")) for r in st}),
            "fps_measured_p50": fps.get("p50"), "open_to_first_frame_ms_p50": o2f.get("p50"),
            "create_first_frame_ms_p50": cff.get("p50"),
            "n_as_requested": sum(1 for r in rows if r.get("ok_as_requested")), "n_streamed": len(st)}


# ============================================================================================================ reanalysis
def _rows_on_disk(run_dir: Path, tid: str, cams: list[dict]) -> dict:
    """{camera key: {"name", "variants": {name: {"rows_file"}}}} from <run_dir>/<tid>/<slug>/*_cycles.json: the
    fallback when the result has no cameras (an interrupted or crashed run whose result is an error stub)."""
    out: dict = {}
    base = run_dir / tid
    if not base.is_dir():
        return out
    by_slug = {ck.cam_slug(c): c for c in cams}
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        c = by_slug.get(d.name) or {"key": d.name, "name": d.name}
        vs = {f.name[:-len("_cycles.json")]: {"rows_file": f"{tid}/{d.name}/{f.name}"}
              for f in sorted(d.glob("*_cycles.json"))}
        if vs:
            out[c["key"]] = {"name": c.get("name"), "variants": vs}
    return out


def reanalyse(run_dir: str | Path, out: str | Path | None = None, test: str = TEST) -> dict:
    """Re-rate a finished run's W-CYC (or W-CYC-KIYO, ``test``) from its saved rows (no camera opened). Applies: -1
    sentinels dropped (N4), format/size/fps flags (B3/B6), the test-level re-arrival attributed to a cycle (B5), a
    pre-existing fault found in the tests that ran before it (B1; suitectx.scan_result_for_faults) and the Wilson
    claim (W-CYC-381). When the result has no cameras (interrupted run: an error stub), the cameras come from
    <test>.partial.json, else from the rows files on disk. Writes reanalysis/<test>.json."""
    import suitectx  # noqa: PLC0415
    run_dir = Path(run_dir)
    p_main, p_part = run_dir / f"{test}.json", run_dir / f"{test}.partial.json"
    orig = json.loads(p_main.read_text(encoding="utf-8")) if p_main.exists() else {}
    meta = {}
    if (run_dir / "run_suite.json").exists():
        meta = json.loads((run_dir / "run_suite.json").read_text(encoding="utf-8"))
    cams = meta.get("cameras") or orig.get("cameras") or []
    source = f"{test}.json"
    if not ((orig.get("measurements") or {}).get("cameras")):
        part = json.loads(p_part.read_text(encoding="utf-8")) if p_part.exists() else {}
        if (part.get("measurements") or {}).get("cameras"):
            orig = {**part, "verdicts": orig.get("verdicts") or part.get("verdicts") or {},
                    "utc_started": orig.get("utc_started") or part.get("utc_started")}
            source = p_part.name
        else:
            disk = _rows_on_disk(run_dir, test, cams)
            orig = {**orig, "measurements": {**(orig.get("measurements") or {}), "cameras": disk}}
            source = f"rows files under {test}/" if disk else source
    # a result without a profile predates the reliability profile (no variant aimed at the 381-cycle claim)
    prof = (orig.get("measurements") or {}).get("profile") or "standard"
    order = meta.get("tests") or []
    t_cyc = _parse_utc(orig.get("utc_started"))
    # suite-wide faults BEFORE this test started, from the earlier tests' results
    pre_faults: dict = {}
    for t in order:
        if t == test:
            break
        p = run_dir / f"{t}.json"
        if not p.exists():
            continue
        found = suitectx.scan_result_for_faults(t, json.loads(p.read_text(encoding="utf-8")), cams)
        for kk, rec in found.items():
            tu = _parse_utc(rec.get("utc"))
            if kk not in pre_faults and (tu is None or t_cyc is None or tu < t_cyc):
                pre_faults[kk] = {"since_utc": rec.get("utc"), "test": t, "mode": rec.get("mode"),
                                  "code": rec.get("code"), "stage": rec.get("stage"), "class": rec.get("class"),
                                  "api": rec.get("api"), "source": "reanalysis scan of " + t, "path": rec.get("path")}
    arr = (orig.get("measurements") or {}).get("arrivals") or {}
    changes = {c["key"]: c for c in (arr.get("changes") or []) if c.get("re_arrival")}
    verdicts: dict = {}
    per_cam: dict = {}
    vchanges = []
    for key, cm in ((orig.get("measurements") or {}).get("cameras") or {}).items():
        pc = {"name": cm.get("name"), "variants": {}}
        per_cam[key] = pc
        ch = changes.get(key)
        arrival_after = ((ch or {}).get("changes") or {}).get("last_arrival", [None, None])[1] if ch else None
        attributed = False
        fault = pre_faults.get(key)
        if fault:
            pc["pre_existing_fault"] = fault
        for name, v in (cm.get("variants") or {}).items():
            if "rows_file" not in v:
                continue
            api = "mf" if name.startswith("mf") else ("ds" if name.startswith("ds") else "opencv")
            rows = json.loads((run_dir / v["rows_file"]).read_text(encoding="utf-8"))
            rows = _norm_rows(rows, api)
            idx = None
            if arrival_after and not attributed:
                idx = apply_re_arrival(rows, arrival_after, api)
                attributed = idx is not None
            summ = cycstats.summarize_cycles(rows)
            replug = v.get("replug_suspected")
            rv = rate_variant(summ, replug, pre_existing_fault=bool(fault), fault=fault,
                              claim_99=prof == "reliability" and name in CLAIM_VARIANTS)
            if fault and rv.get("rating") != "untested":
                # an old rating.py without pre_existing_fault support: rate as the contract says
                rv = rate_variant({"n": 0}, None, pre_existing_fault=True, fault=fault)
                rv["evidence"].update({kk: summ.get(kk) for kk in CONTRACT_EVIDENCE})
            rv["variant"] = name
            vk = f"reliability|{key}|{name}"
            verdicts[vk] = rv
            old = ((orig.get("verdicts") or {}).get(vk) or {}).get("rating")
            if old != rv["rating"]:
                vchanges.append({"verdict": vk, "old": old, "new": rv["rating"], "note": rv.get("note"),
                                 "no_reason": rv.get("no_reason")})
            pc["variants"][name] = {"summary": summ, "re_arrival_cycle": idx,
                                    "final": opencv_final(rows) if api == "opencv" else None,
                                    "format_fallbacks": v.get("format_fallbacks"),
                                    "replug_suspected": replug}
        if arrival_after and not attributed:
            pc["re_arrival_unattributed"] = arrival_after
    doc = {"test": test, "reanalysis_of": str(run_dir / source), "utc": results.utc_now_iso(),
           "camera_opened": False,
           "fixes_applied": ["N4 -1 sentinels dropped from timing percentiles",
                             "B3/B6 format_mismatch / size_mismatch / fps_mismatch per row (ok = streamed); counts "
                             "in the evidence; a mismatch caps the rating at partial",
                             "B5 the test-level re-arrival attributed to the cycle whose window contains it "
                             "(device_reset failure)",
                             "B1 a device fault found in an earlier test of the run makes the camera's variants "
                             "untested (pre_existing_fault) instead of no",
                             "B8 evidence carries n_ok / success_rate / wilson95 / p50; no_reason latency|failures",
                             "W-CYC-381: in the reliability profile mf_inproc / ds_ffmpeg_inproc / mf_newproc rate "
                             "'yes' only at a Wilson 95 % lower bound >= 0.99; other 'yes' cells are labelled point "
                             "estimates"],
           "pre_existing_faults": pre_faults, "measurements": {"cameras": per_cam},
           "verdicts": verdicts, "verdict_changes": vchanges,
           "ratings": _count(verdicts), "ratings_original": _count(orig.get("verdicts") or {})}
    outp = Path(out) if out else run_dir / "reanalysis" / f"{test}.json"
    results.write_json(outp, doc)
    return doc


def _count(verdicts: dict) -> dict:
    c: dict = {}
    for v in verdicts.values():
        if isinstance(v, dict) and "rating" in v:
            lab = v["rating"] + (f" ({v['no_reason']})" if v.get("no_reason") else "")
            c[lab] = c.get(lab, 0) + 1
    return c


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="W-CYC offline re-analysis (no camera opened)")
    ap.add_argument("--reanalyse", required=True, metavar="RUN_DIR")
    ap.add_argument("--out", default=None)
    ap.add_argument("--test", default=TEST, choices=(TEST, KIYO_TEST), help="which segment's result to re-rate")
    a = ap.parse_args()
    d = reanalyse(a.reanalyse, a.out, test=a.test)
    print(json.dumps({"ratings": d["ratings"], "ratings_original": d["ratings_original"],
                      "verdict_changes": d["verdict_changes"], "pre_existing_faults": d["pre_existing_faults"]},
                     indent=1, default=str))
