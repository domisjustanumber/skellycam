"""W-RAW: does Media Foundation deliver the camera's OWN uncompressed frames (YUY2, native NV12), not MF-decoded pixels?

Plan docs/capture_stack_options_plan.md section 4.1 row 9a and section 6.1 (W-RAW). Per camera:
- the native raw types come from the W-FMT listing of this run (``W-FMT/*<vid>-<pid>*_formats_mf.json``), else from
  ``wincam formats --api mf`` (capkit.get_formats, cached per run). Compressed subtypes (MJPG, H.264) are not raw.
  An NV12 type that MF lists right before a same-mode MJPG type (``likely_mf_synthesized``: MF's own decode of the
  MJPEG stream) is NOT a camera raw mode: it is counted and excluded, and wincam refuses it as well;
- mode scope (Dom 2026-11-08): streaming uses ONLY modes with exactly 720 lines at >= 30 fps (common/modescope:
  ``--min-height`` / ``--max-height`` / ``--min-fps``; ``--all-modes`` lifts it; against a modescope without
  ``max_height`` the exact-height bound is applied here). There is no exception for raw formats: a camera without
  an in-scope raw mode is rated ``untested (no raw mode in scope)``. Expected on Gerald: the USB 2.0 Logitech and
  generic cameras
  (their 720p YUY2 tops out at 10 fps); the Kiyo Pro at SuperSpeed lists YUY2 and NV12 at 720p30/60;
- each in-scope raw mode is captured for ``--raw-seconds`` (3 s; quick 1.5 s) through five routes, one at a time:
  ``mf`` (wincam capture, explicit native type, converters off, readback), ``pyav`` (PyAV dshow with the
  ``pixel_format`` option), ``ffmpeg`` (the ffmpeg CLI with ``-pixel_format``), ``ocv_dshow`` and ``ocv_msmf``
  (OpenCV with the FOURCC set and CONVERT_RGB=0; MSMF also FORMAT=-1). The DS/OpenCV routes run in
  ``helpers/raw_ds.py``;
- checks per (mode, route): the delivered format (MF readback subtype; FFmpeg codec rawvideo + pix_fmt; OpenCV FOURCC
  readback and frame size), every frame's byte length against the expected length (stride x height; 4:2:0 x 1.5:
  YUY2 1280x720 = 1,843,200 B, NV12 = 1,382,400 B), the delivered rate against the request (2 %), and on one saved
  frame a byte-layout plausibility check (luma bytes vary more than chroma bytes; chroma centred near 128). Raw
  frames from different captures are different images, so the cross-route comparison is of format, length and
  layout (``layout_agree``), never of bytes;
- rating per camera x route (``G-RAW|<camera key>|<route>``): yes = every in-scope raw mode delivered in the
  requested format, 100 % of frames at the expected length, rate within 2 % of the request (or of the camera's real
  rate when every route agrees on it: a camera finding, recorded in ``rate_honoured``); partial = some of that;
  no = no route-requested raw frame at all; untested = no raw mode in scope, device fault, or the route unavailable;
- tier 0 only (Dom 2026-11-09): UVC payload metadata (PTS/SCR) is neither counted nor rated; timing comes from
  QPC arrival (MF) or the packet time (DS);
- contention: one W-MULTI-style check (both cameras streaming their in-scope raw mode through MF at once) only when
  two cameras with an in-scope raw mode share one bandwidth domain (W-TOPO ``camera_domains`` of this run, else the
  live topology snapshot); otherwise ``contention`` records why it was not run;
- device faults (0x8007001F, an unreleasable reader, a killed child) stop work on that camera and rate it
  'untested (device fault)', as in W-MJPEG; a camera that arrives faulted (gated by the runner) is not streamed.
Raw frames (3 per capture) and per-frame JSONL stay in raw_dir; results keep the per-mode summary only.

Offline re-analysis of a stored run (no camera):

    uv run --python 3.12 python suite/windows/tests/w_raw.py --reanalyze <run dir> [--raw-dir <raw run dir>]

writes ``<run dir>/reanalysis/W-RAW.json``.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

WIN = Path(__file__).resolve().parents[1]
for _p in (str(WIN.parent), str(WIN), str(WIN / "helpers")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capkit as ck  # noqa: E402
from common import modescope, rating, results  # noqa: E402

TEST = "W-RAW"
GOAL = "G-RAW"
INFO = {"goal": GOAL, "claim": "capture_stack_options_plan.md 4.1 row 9a: MF delivers the camera's own YUY2 / NV12",
        "summary": "native raw modes (exactly 720 lines, >= 30 fps) via MF, PyAV/ffmpeg dshow pixel_format, OpenCV "
                   "DSHOW/MSMF CONVERT_RGB=0: delivered format, frame length, rate, layout",
        "opens_cameras": True}
RAW_DS = WIN / "helpers" / "raw_ds.py"
APIS = ("mf", "pyav", "ffmpeg", "ocv_dshow", "ocv_msmf")
#: run only with run_suite.py --with-opencv (2026-11-12); otherwise rated untested with capkit.OPENCV_OFF
OPENCV_APIS = ("ocv_dshow", "ocv_msmf")
FPS_TOL = 0.02
LEN_OK_MIN = 1.0            # plan: 100 % of frames at the expected length
TIMEOUT_MS = 5000
MSMF_OPEN_TIMEOUT_MS = 60000   # MSMF opens took 39-41 s on the Logitech cameras (REPORT finding 3)
DSHOW_OPEN_TIMEOUT_MS = 20000
SAVED_FRAMES = 3
NO_SCOPE_LABEL = "untested (no raw mode in scope)"

#: raw subtype -> FFmpeg pixel format, size factor (bytes per pixel as num/den), byte layout
RAW_FORMATS: dict[str, dict[str, Any]] = {
    "YUY2": {"pix_fmt": "yuyv422", "num": 2, "den": 1, "layout": "packed_y_first"},
    "YUYV": {"pix_fmt": "yuyv422", "num": 2, "den": 1, "layout": "packed_y_first"},
    "YVYU": {"pix_fmt": "yvyu422", "num": 2, "den": 1, "layout": "packed_y_first"},
    "UYVY": {"pix_fmt": "uyvy422", "num": 2, "den": 1, "layout": "packed_c_first"},
    "NV12": {"pix_fmt": "nv12", "num": 3, "den": 2, "layout": "planar420"},
    "NV21": {"pix_fmt": "nv21", "num": 3, "den": 2, "layout": "planar420"},
    "I420": {"pix_fmt": "yuv420p", "num": 3, "den": 2, "layout": "planar420"},
    "IYUV": {"pix_fmt": "yuv420p", "num": 3, "den": 2, "layout": "planar420"},
    "Y800": {"pix_fmt": "gray", "num": 1, "den": 1, "layout": "grey"},
    "GREY": {"pix_fmt": "gray", "num": 1, "den": 1, "layout": "grey"},
}
#: four-character subtypes that are compressed (never raw)
COMPRESSED_4CC = {"MJPG", "H264", "H265", "HEVC", "AVC1", "VP80", "VP90", "MP4V", "MPG2"}


# ============================================================================================================ modes
def is_raw_subtype(sub: str | None) -> bool:
    s = str(sub or "")
    if s.upper() in RAW_FORMATS:
        return True
    if s.startswith("D3DFMT_"):           # RGB24 / RGB32 etc. (non-FOURCC uncompressed subtypes)
        return True
    return len(s) == 4 and s.upper() not in COMPRESSED_4CC


def expected_bytes(sub: str, w: int, h: int) -> int | None:
    """Byte length of one frame of a raw format (minimum stride): YUY2 w*h*2, NV12 w*h*3/2; None if unknown."""
    f = RAW_FORMATS.get(str(sub).upper())
    if not f:
        return None
    return int(w) * int(h) * f["num"] // f["den"]


def raw_modes(formats_mf: dict | None) -> tuple[list[ck.Mode], dict]:
    """Native raw modes of the capture stream (the first reader stream with types), de-duplicated, without the
    NV12 types flagged likely_mf_synthesized. Returns (modes, info with the excluded counts)."""
    info: dict[str, Any] = {"stream_index": None, "synthesized_excluded": [], "compressed_types": 0, "types": 0}
    if not formats_mf:
        info["error"] = "no formats JSON"
        return [], info
    stream = next((s for s in formats_mf.get("reader_streams") or [] if s.get("types")), None)
    if stream is None:
        info["error"] = "no reader stream with native types"
        return [], info
    info["stream_index"] = stream.get("stream_index")
    seen: dict[tuple, ck.Mode] = {}
    synth = set()
    for t in stream.get("types") or []:
        info["types"] += 1
        sub = str(t.get("subtype") or "")
        if not is_raw_subtype(sub):
            info["compressed_types"] += 1
            continue
        try:
            m = ck.Mode(int(t["width"]), int(t["height"]), int(t["fps_num"]), int(t["fps_den"]), sub.upper())
        except (KeyError, TypeError, ValueError):
            continue
        k = (m.subtype, m.w, m.h, m.fps_num, m.fps_den)
        if any("likely_mf_synthesized" in str(f) for f in t.get("flags") or []):
            synth.add(k)
            continue
        seen[k] = m
    info["synthesized_excluded"] = sorted(f"{k[0]} {k[1]}x{k[2]}@{k[3] / k[4]:.4g}" for k in synth if k not in seen)
    modes = sorted(seen.values(), key=lambda m: (m.subtype, m.w * m.h, m.w, m.fps))
    info["subtypes"] = sorted({m.subtype for m in modes})
    return modes, info


def scope_raw(scope: modescope.Scope, modes: list[ck.Mode]) -> tuple[list[ck.Mode], dict]:
    """(in-scope raw modes, scope record). Rule (Dom 2026-11-08): the streaming scope of common/modescope (default
    exactly 720 lines at >= 30 fps), with no exception for raw formats; ``all_modes`` keeps everything. A modescope
    without ``max_height`` (the 2026-11-06 '>= 720 lines' version) gets the exact-height bound added here."""
    exact_here = not scope.all_modes and not hasattr(scope, "max_height")
    kept = [m for m in modescope.filter_modes(modes, scope) if not exact_here or m.h == scope.min_height]
    rec = modescope.record(scope, modes, kept)
    rule = f"exactly {scope.min_height} lines at >= {scope.min_fps:g} fps" if exact_here else scope.text
    rec["rule"] = rule + ("" if scope.all_modes else " (Dom 2026-11-08; no raw exception)")
    if not kept:
        lines = [m for m in modes if m.h == scope.min_height]
        best = max(lines, key=lambda m: m.fps) if lines else None
        rec["untested_reason"] = (
            f"{NO_SCOPE_LABEL}: none of the camera's {len(modes)} native raw modes is in the streaming scope ({rule})"
            + (f"; fastest {scope.min_height}-line raw mode: {best.text}" if best else
               f"; no {scope.min_height}-line raw mode at all"))
    return kept, rec


def load_formats(ctx, cam: dict, cache: dict) -> tuple[dict | None, dict]:
    """This run's W-FMT MF listing of the camera (no camera opened), else capkit.get_formats (cached per run)."""
    d = Path(ctx.out_dir) / "W-FMT"
    hits = sorted(d.glob(f"*{cam.get('vid')}-{cam.get('pid')}*_formats_mf.json")) if d.is_dir() else []
    if len(hits) == 1:
        try:
            return json.loads(hits[0].read_text(encoding="utf-8")), {"source": str(hits[0])}
        except (OSError, ValueError):
            pass
    fm, run = ck.get_formats(ctx, cam, cache)
    return fm, {"source": "capkit.get_formats", **(run or {})}


# ============================================================================================================ frames
def saved_frame(out_dir: Path | str, rows: list[dict]) -> bytes | None:
    """The first saved raw frame (frames.raw at raw_offset/raw_len), or None."""
    p = Path(out_dir) / "frames.raw"
    row = next((r for r in rows if r.get("raw_offset") is not None and r.get("raw_len")), None)
    if row is None or not p.exists():
        return None
    with p.open("rb") as f:
        f.seek(int(row["raw_offset"]))
        return f.read(int(row["raw_len"]))


def _stats(b: bytes, start: int, end: int, step: int, n: int = 20000) -> tuple[float, float]:
    vals = b[start:end:step]
    if len(vals) > n:
        vals = vals[:: max(1, len(vals) // n)]
    if len(vals) < 2:
        return float("nan"), float("nan")
    return statistics.fmean(vals), statistics.pstdev(vals)


def layout_check(sub: str, w: int, h: int, b: bytes | None) -> dict:
    """Plausibility of the byte layout of one frame (evidence, not a rating criterion): in a real image the luma
    bytes vary more than the chroma bytes, and chroma sits near 128. Packed 4:2:2 Y-first (YUY2): luma at even
    offsets; UYVY: at odd offsets; 4:2:0 planar: luma plane then chroma."""
    if not b:
        return {"checked": False, "reason": "no saved frame"}
    f = RAW_FORMATS.get(str(sub).upper())
    if not f:
        return {"checked": False, "reason": f"no layout rule for {sub}"}
    flat = len(set(b[:: max(1, len(b) // 4096)])) <= 1
    lay = f["layout"]
    if lay in ("packed_y_first", "packed_c_first"):
        ym, ys = _stats(b, 0 if lay == "packed_y_first" else 1, len(b), 2)
        cm, cs = _stats(b, 1 if lay == "packed_y_first" else 0, len(b), 2)
    elif lay == "planar420":
        ym, ys = _stats(b, 0, w * h, 1)
        cm, cs = _stats(b, w * h, len(b), 1)
    else:
        ym, ys = _stats(b, 0, len(b), 1)
        return {"checked": True, "layout": lay, "luma_mean": ym, "luma_std": ys, "flat": flat,
                "plausible": (not flat) or None}
    plausible = None if flat else bool(ys > cs and abs(cm - 128.0) < 48.0)
    return {"checked": True, "layout": lay, "luma_mean": round(ym, 2), "luma_std": round(ys, 2),
            "chroma_mean": round(cm, 2), "chroma_std": round(cs, 2), "flat": flat, "plausible": plausible,
            "rule": "luma std > chroma std and |chroma mean - 128| < 48 (None when the frame is flat)"}


# ============================================================================================================ per capture
def _wanted(api: str, mode: ck.Mode) -> str:
    if api in ("pyav", "ffmpeg"):
        return (RAW_FORMATS.get(mode.subtype) or {}).get("pix_fmt") or "?"
    return mode.subtype


def delivered_format(api: str, s: dict, rows: list[dict], mode: ck.Mode, exp: int | None) -> tuple[str | None, bool]:
    """(what the route delivered, whether it is the requested raw format)."""
    if api == "mf":
        neg = s.get("negotiated") or {}
        sub = neg.get("subtype")
        ok = (bool(neg.get("readback_ok")) and str(sub).upper() == mode.subtype
              and neg.get("likely_mf_synthesized") is not True and neg.get("raw") is not False)
        return sub, ok
    if api in ("pyav", "ffmpeg"):
        codec, pix = s.get("codec"), s.get("pix_fmt")
        return (f"{codec}/{pix}" if codec else None), (codec == "rawvideo" and pix == _wanted(api, mode))
    d = s.get("delivered") or {}
    fcc = str(d.get("fourcc_readback") or "").strip("\x00 ")
    shapes = d.get("shapes") or [r.get("shape") for r in rows[:1]]
    bgr = any(isinstance(sh, list) and len(sh) == 3 and sh[2] == 3 and sh[:2] == [mode.h, mode.w] for sh in shapes)
    lens = {r.get("bytes") for r in rows}
    label = f"{fcc or '?'} {shapes[0] if shapes else '?'}"
    ok = (not bgr) and fcc.upper() == mode.subtype and bool(rows) and (exp is None or lens == {exp})
    return label, ok


def analyse(api: str, s: dict | None, run: dict | None, rows: list[dict], mode: ck.Mode,
            out_dir: Path | str | None = None) -> dict:
    """One (mode, route) capture -> its record (pure on the tool's summary + frames.jsonl rows)."""
    s = s or {}
    run = run or {}
    exp = expected_bytes(mode.subtype, mode.w, mode.h)
    if api == "mf":
        rx = ((s.get("negotiated") or {}).get("raw_frame") or {}).get("expected_frame_bytes")
        exp = rx or exp
    lens = [r.get("bytes") for r in rows if isinstance(r.get("bytes"), int)]
    n = len(lens)
    n_ok = sum(1 for x in lens if exp is not None and x == exp)
    fmt, fmt_ok = delivered_format(api, s, rows, mode, exp)
    fmt_ok = fmt_ok and n > 0  # a negotiated/opened raw type that streams no frame did not deliver the format
    key = "qpc_ns" if any(isinstance(r.get("qpc_ns"), (int, float)) for r in rows) else "pts_ns"
    fps = ck.fps_from_rows(rows, key=key)
    tool_ok = bool(s.get("ok"))
    ck_api = "mf" if api == "mf" else "ds"
    code, stage, err = ck.failure_code(ck_api, s, run)
    cls = None if tool_ok else ck.classify("opencv" if api.startswith("ocv") else ck_api, code, stage, frames=n,
                                           timed_out=bool(run.get("timed_out")))
    fault = None if tool_ok else ck.fault_from_result(ck_api, s, run, cls)
    common_len = max(set(lens), key=lens.count) if lens else None
    rec = {"api": api, "ok": tool_ok, "rc": run.get("rc"), "timed_out": run.get("timed_out"),
           "requested": _wanted(api, mode), "delivered": fmt, "format_ok": fmt_ok, "frames": n,
           "expected_bytes": exp, "len_ok": n_ok, "len_ok_fraction": (n_ok / n) if n and exp is not None else None,
           "common_length": common_len, "distinct_lengths": len(set(lens)),
           "fps_measured": fps, "fps_tool": s.get("fps_measured"), "fps_basis": key,
           "fps_within_tol_of_request": (abs(fps - mode.fps) / mode.fps <= FPS_TOL) if fps else None,
           "timings": s.get("timings"), "error": err or None, "classification": cls, "fault": fault,
           "out_dir": str(out_dir) if out_dir else None, "utc_started": s.get("utc_started")}
    if api == "mf":
        neg = s.get("negotiated") or {}
        fr = s.get("frames") or {}
        rec.update(native_type_index=neg.get("native_type_index"), readback_ok=neg.get("readback_ok"),
                   likely_mf_synthesized=neg.get("likely_mf_synthesized"),
                   synthesized_refused=neg.get("synthesized_refused"), raw_frame=neg.get("raw_frame"),
                   readback_default_stride=neg.get("readback_default_stride"), buffer=fr.get("buffer"),
                   raw_flat_frames=fr.get("raw_flat"))
        if neg and "raw" not in neg:
            rec["note"] = "wincam older than 1.2: no raw frame checks in the tool (lengths judged here)"
    elif api.startswith("ocv"):
        rec.update(sets=s.get("sets"), opencv_delivered=s.get("delivered"))
    rec["layout"] = layout_check(mode.subtype, mode.w, mode.h, saved_frame(out_dir, rows)) if out_dir else \
        {"checked": False, "reason": "no out_dir"}
    return rec


def finish_mode(row: dict, mode: ck.Mode) -> dict:
    """Cross-route comparison of one mode: format / length / layout agreement (never bytes: different captures are
    different images), the fps reference and whether the camera honours the requested rate."""
    apis = {k: v for k, v in row["apis"].items() if isinstance(v, dict) and v.get("frames")}
    good = {k: v for k, v in apis.items() if v.get("format_ok")}
    lens = {k: v.get("common_length") for k, v in good.items()}
    row["lengths_by_api"] = {k: v.get("common_length") for k, v in apis.items()}
    row["delivered_by_api"] = {k: v.get("delivered") for k, v in row["apis"].items() if isinstance(v, dict)}
    row["layout_agree"] = (len(set(lens.values())) == 1) if len(lens) >= 2 else None
    row["layout_plausible_by_api"] = {k: (v.get("layout") or {}).get("plausible") for k, v in apis.items()}
    fba = {k: v.get("fps_measured") for k, v in good.items()}
    ref, basis, note = ck.fps_reference(fba, mode.fps, tol=FPS_TOL)
    row.update(fps_nominal=mode.fps, fps_reference=ref, fps_reference_basis=basis, fps_reference_note=note,
               rate_honoured=ck.rate_honoured(fba, mode.fps, tol=FPS_TOL))
    return row


# ============================================================================================================ rating
def _crit(criterion: str, met: bool | None, detail: Any = None) -> dict:
    return {"criterion": criterion, "met": met, "detail": detail}


def _result(r: str, criteria: list[dict], evidence: Any) -> dict:
    return {"rating": r, "criteria": criteria, "evidence": evidence}


def _mode_ok(a: dict, row: dict, mode_fps: float) -> dict:
    fps = a.get("fps_measured")
    ref = row.get("fps_reference") or mode_fps
    basis = row.get("fps_reference_basis")
    fps_ok = None
    if fps:
        fps_ok = abs(fps - mode_fps) / mode_fps <= FPS_TOL or (basis == "apis_agree" and abs(fps - ref) / ref <= FPS_TOL)
    len_ok = a.get("len_ok_fraction") is not None and a["len_ok_fraction"] >= LEN_OK_MIN
    return {"format": bool(a.get("format_ok")), "length": len_ok, "rate": fps_ok,
            "ok": bool(a.get("format_ok")) and len_ok and fps_ok is True}


def rate_api(mode_rows: list[dict], api: str, n_in_scope: int) -> dict:
    """G-RAW rating of one route on one camera (see the module docstring)."""
    tested, untested_why = [], []
    for row in mode_rows:
        a = row["apis"].get(api)
        if not isinstance(a, dict) or a.get("untested") or row.get("skipped"):
            untested_why.append(f"{row['mode']}: {(a or {}).get('untested') or row.get('skipped') or 'not run'}")
            continue
        tested.append((row, a, _mode_ok(a, row, row["fps_nominal"])))
    if not tested:
        return rating.untested("; ".join(untested_why) or "no mode run", {"modes": untested_why})
    per = [{"mode": r["mode"], "delivered": a.get("delivered"), "frames": a.get("frames"),
            "len_ok_fraction": a.get("len_ok_fraction"), "fps": a.get("fps_measured"),
            "fps_reference": r.get("fps_reference"), **chk} for r, a, chk in tested]
    n_fmt = sum(1 for p in per if p["format"])
    n_len = sum(1 for p in per if p["length"])
    n_rate = sum(1 for p in per if p["rate"])
    n_ok = sum(1 for p in per if p["ok"])
    crit = [_crit("delivers the requested raw format", n_fmt == len(per), f"{n_fmt}/{len(per)} modes"),
            _crit(f"{LEN_OK_MIN:.0%} of frames at the expected length", n_len == len(per),
                         f"{n_len}/{len(per)} modes"),
            _crit(f"rate within {FPS_TOL:.0%} of the request (or of the camera's real rate)",
                         n_rate == len(per), f"{n_rate}/{len(per)} modes"),
            _crit("every in-scope raw mode captured", len(per) >= n_in_scope, f"{len(per)}/{n_in_scope}")]
    if n_fmt == 0:
        r = "no"
        lab = "no (no raw frames in the requested format)"
    elif n_ok == len(per) and len(per) >= n_in_scope:
        r, lab = "yes", None
    else:
        r, lab = "partial", None
    v = _result(r, crit, {"modes": per, "untested_modes": untested_why})
    if lab:
        v["summary_label"] = lab
    v["tier"] = 0
    return v


def no_scope_verdict(rec: dict) -> dict:
    why = rec.get("untested_reason") or NO_SCOPE_LABEL
    v = rating.untested(why, {"mode_scope": rec, "scope_excluded": True})
    v["note"] = why
    v["summary_label"] = NO_SCOPE_LABEL
    return v


def fault_verdict(ctx, cam: dict, fault: dict | None, superseded: str | None = None) -> dict:
    f = fault or {}
    v = rating.device_fault_untested({"utc": f.get("utc"), "test": f.get("test"), "mode": f.get("mode"),
                                      "code": f.get("code")}, evidence={"fault": f})
    if superseded:
        v["superseded_rating"] = superseded
    return v


# ============================================================================================================ captures
def capture_mf(ctx, cam: dict, mode: ck.Mode, od: Path, secs: float) -> tuple[dict | None, dict, list[dict]]:
    every = max(1, int(mode.fps * secs / SAVED_FRAMES))
    s, run = ck.wincam_capture(ctx, cam, mode, od, seconds=secs, save=f"every:{every}", timeout_ms=TIMEOUT_MS)
    return s, run, ck.load_frames(od)


def helper_argv(ctx, cam: dict, mode: ck.Mode, api: str, od: Path, secs: float) -> tuple[list[str], float] | str:
    """argv + child timeout for a raw_ds.py route, or the reason the route cannot run on this camera."""
    common = ["--width", mode.w, "--height", mode.h, "--fps", mode.ds_fps, "--seconds", secs,
              "--timeout-ms", TIMEOUT_MS, "--out-dir", od, "--save-frames", SAVED_FRAMES, "--api", api]
    if api in ("pyav", "ffmpeg"):
        pix = (RAW_FORMATS.get(mode.subtype) or {}).get("pix_fmt")
        if not cam.get("ds_path"):
            return "camera has no DirectShow device path"
        if not pix:
            return f"no FFmpeg pixel format known for {mode.subtype}"
        return (ck.helper_argv(ctx, RAW_DS, api, "--device", cam["ds_path"], "--pixel-format", pix, *common),
                secs + 4 * TIMEOUT_MS / 1000.0 + 60)
    backend = "dshow" if api == "ocv_dshow" else "msmf"
    idx = cam.get("ds_index") if backend == "dshow" else cam.get("mf_index")
    link = cam.get("ds_path") if backend == "dshow" else cam.get("mf_symlink")
    if idx is None or not link:
        return f"camera has no {'DirectShow' if backend == 'dshow' else 'MF'} index / link for OpenCV"
    open_ms = DSHOW_OPEN_TIMEOUT_MS if backend == "dshow" else MSMF_OPEN_TIMEOUT_MS
    argv = ck.helper_argv(ctx, RAW_DS, "opencv", "--backend", backend, "--index", idx, "--expect-path", link,
                          "--fourcc", mode.subtype, "--open-timeout-ms", open_ms, *common)
    return argv, 2 * open_ms / 1000.0 + secs + 4 * TIMEOUT_MS / 1000.0 + 60


def capture_helper(ctx, cam: dict, mode: ck.Mode, api: str, od: Path, secs: float
                   ) -> tuple[dict | None, dict, list[dict]] | str:
    spec = helper_argv(ctx, cam, mode, api, od, secs)
    if isinstance(spec, str):
        return spec
    od.mkdir(parents=True, exist_ok=True)
    argv, to = spec
    r = ctx.camcmd(argv, timeout_s=to)
    s = ck.parse_json(r)
    if s is None and (od / "summary.json").exists():
        try:
            s = json.loads((od / "summary.json").read_text(encoding="utf-8"))
        except ValueError:
            s = None
    if isinstance(s, dict) and s.get("untested"):
        return str((s.get("error") or {}).get("reason") or "route unavailable")
    return s, ck.run_brief(r), ck.load_frames(od)


def run_capture(ctx, cam: dict, mode: ck.Mode, api: str, od: Path, secs: float):
    """(summary, run, rows) or a string: why the route could not run."""
    if api in OPENCV_APIS and not ck.opencv_enabled(ctx):
        return ck.OPENCV_OFF
    if api == "mf":
        if not cam.get("mf_symlink"):
            return "camera has no MF symbolic link"
        return capture_mf(ctx, cam, mode, od, secs)
    return capture_helper(ctx, cam, mode, api, od, secs)


# ============================================================================================================ contention
def camera_domains(ctx) -> tuple[dict, str]:
    """{camera key: bandwidth domain key} from this run's W-TOPO.json, else the live snapshot (no camera opened)."""
    p = Path(ctx.out_dir) / "W-TOPO.json"
    try:
        d = (json.loads(p.read_text(encoding="utf-8")).get("measurements") or {}).get("camera_domains") or {}
        if d:
            return d, str(p)
    except (OSError, ValueError):
        pass
    try:
        import win_topology as wt  # noqa: PLC0415
        from common import topology_model as tm  # noqa: PLC0415
        snap = wt.collect()
        dev_dom = {m: d["key"] for d in tm.compute_domains(snap) for m in d.get("members", [])}
        by_dev = {str(c.get("device_id") or "").upper(): c for c in snap.get("cameras", [])}
        out = {}
        for cam in ctx.cameras:
            sc = by_dev.get(str(cam.get("instance_id") or "").upper())
            if sc is not None:
                out[cam["key"]] = dev_dom.get(sc.get("device_id"))
        return out, "live win_topology snapshot"
    except Exception as e:  # noqa: BLE001
        return {}, f"no topology: {e!r}"


def contention_plan(in_scope: dict[str, list[ck.Mode]], domains: dict[str, str | None]) -> dict:
    """The camera pair to stream together, or why there is none."""
    have = {k: v for k, v in in_scope.items() if v}
    by_dom: dict[str, list[str]] = {}
    for k in have:
        dk = domains.get(k)
        if dk:
            by_dom.setdefault(dk, []).append(k)
    shared = {dk: ks for dk, ks in by_dom.items() if len(ks) >= 2}
    base = {"cameras_with_in_scope_raw": sorted(have), "domains": {k: domains.get(k) for k in have}}
    if not shared:
        if len(have) < 2:
            why = (f"not run: only {len(have)} camera(s) have an in-scope raw mode "
                   f"({', '.join(sorted(have)) or 'none'}), so no two raw streams can share a bandwidth domain")
        else:
            why = "not run: the cameras with an in-scope raw mode are in different bandwidth domains"
        return {"run": False, "reason": why, **base}
    dk, ks = sorted(shared.items())[0]
    a, b = sorted(ks)[:2]
    return {"run": True, "domain": dk, "pair": [a, b], "modes": {a: have[a][0].text, b: have[b][0].text}, **base}


def run_contention(ctx, plan: dict, in_scope: dict[str, list[ck.Mode]], raw: Path, secs: float) -> dict:
    """Both cameras of the pair stream their first in-scope raw mode through MF at the same moment (one camera
    lock, helpers/multi_launch.py); each outcome is classified with the domain context."""
    if not plan.get("run"):
        return plan
    cams = [ctx.camera(k) for k in plan["pair"]]
    items = []
    for c in cams:
        m = in_scope[c["key"]][0]
        od = raw / "contention" / ck.cam_slug(c)
        items.append({"label": c["key"], "argv": ck.wincam_capture_argv(ctx, c, m, od, secs, timeout_ms=TIMEOUT_MS),
                      "start_at_s": 0.0, "timeout_s": secs + 4 * TIMEOUT_MS / 1000.0 + 25})
    spec = {"commands": items, "snapshots_at_s": [min(1.5, secs / 2)], "descriptor_file": None, "snapshot_dir": None}
    doc, brief = ck.multi_launch(ctx, spec, raw / "contention" / "spec.json", timeout_s=secs + 120)
    outcomes = {}
    for cmd in (doc or {}).get("commands") or []:
        s = ck.parse_json({"stdout": cmd.get("stdout") or ""}) or {}
        n = (s.get("frames") or {}).get("total") or 0
        code, stage, _err = ck.failure_code("mf", s, {"timed_out": cmd.get("timed_out")})
        ok = bool(s.get("ok")) and not cmd.get("timed_out")
        outcomes[cmd.get("label")] = {
            "ok": ok, "frames": n, "fps": s.get("fps_measured"), "negotiated": (s.get("negotiated") or {}).get("subtype"),
            "code": code, "stage": stage, "classification": None if ok else ck.classify(
                "mf", code, stage, frames=n, timed_out=bool(cmd.get("timed_out")), other_streaming_in_domain=True)}
    return {**plan, "outcomes": outcomes, "launch": brief,
            "note": "observed only: a refusal here is bandwidth contention between two raw streams in one domain "
                    "(raw modes reserve more isochronous bandwidth than MJPEG)"}


# ============================================================================================================ estimate
def _cached_formats(ctx, cam: dict) -> dict | None:
    """A format listing already on disk (W-FMT of this run, or capkit's per-run cache); never opens a camera."""
    d = Path(ctx.out_dir) / "W-FMT"
    hits = sorted(d.glob(f"*{cam.get('vid')}-{cam.get('pid')}*_formats_mf.json")) if d.is_dir() else []
    hits += [Path(ctx.raw_dir) / "_cache" / f"formats_mf_{ck.cam_slug(cam)}.json"]
    for p in hits:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def estimate_s(ctx) -> float:
    """Seconds, from listings already on disk only (no camera opened here); unknown cameras count 4 raw modes
    if SuperSpeed, else 0 (USB 2.0 cameras have no 720p raw mode at >= 30 fps)."""
    secs = float(ck.arg(ctx, "raw_seconds", 3.0, 1.5))
    sc = modescope.from_args(getattr(ctx, "args", None))
    n = 0
    for cam in ctx.cameras:
        fm = _cached_formats(ctx, cam)
        if fm is not None:
            n += len(scope_raw(sc, raw_modes(fm)[0])[0])
        else:
            n += 4 if str(cam.get("speed") or "").startswith("SS") else 0
    per_mode = (secs + 2) + (secs + 5) + (secs + 5)                    # mf, pyav, ffmpeg
    if ck.opencv_enabled(ctx):
        per_mode += (secs + 10) + (secs + 45)                          # ocv_dshow, ocv_msmf
    return 15 + n * per_mode


# ============================================================================================================ run
def _summary_line(row: dict) -> str:
    parts = []
    for api in APIS:
        a = row["apis"].get(api)
        if not isinstance(a, dict):
            continue
        if a.get("untested"):
            parts.append(f"{api}: untested")
            continue
        parts.append(f"{api}: {a.get('delivered')} fmt_ok={a.get('format_ok')} len_ok={a.get('len_ok')}/"
                     f"{a.get('frames')} {a.get('fps_measured') or 0:.1f} fps")
    return " | ".join(parts)


def _camera(ctx, cam: dict, modes: list[ck.Mode], raw: Path, secs: float, events: list) -> tuple[list[dict], dict | None]:
    """Capture every in-scope raw mode on every route. Returns (mode rows, active fault or None)."""
    slug = ck.cam_slug(cam)
    rows: list[dict] = []
    fault = None
    for m in modes:
        if fault:
            rows.append({"mode": m.text, "mode_detail": m.as_dict(), "apis": {}, "fps_nominal": m.fps,
                         "skipped": f"untested: device fault since {fault.get('utc')}"})
            continue
        row = {"mode": m.text, "mode_detail": m.as_dict(), "apis": {}}
        for api in APIS:
            od = raw / slug / f"{api}_{m.subtype}_{m.slug}"
            try:
                got = run_capture(ctx, cam, m, api, od, secs)
            except Exception as e:  # noqa: BLE001 - one route failing must not stop the others
                row["apis"][api] = {"api": api, "untested": f"harness exception: {e!r}",   # not a route result
                                    "error": {"exception": repr(e)}}
                continue
            if isinstance(got, str):
                row["apis"][api] = {"api": api, "untested": got}
                continue
            s, run, frs = got
            a = analyse(api, s, run, frs, m, od)
            row["apis"][api] = a
            if a.get("fault"):
                rec = ck.mark_device_fault(ctx, cam, TEST, m.text, api, a["fault"])
                events.append({"event": "fault", "mode": m.text, "api": api, **a["fault"],
                               "utc": results.utc_now_iso()})
                if a["fault"].get("kind") != "device_error":
                    pr = ck.health_check(ctx, cam, None, raw / slug / f"_health_{m.slug}_{api}", test=TEST,
                                         reason=f"{TEST}: after a hang ({a['fault'].get('stage')}, {m.text} {api})")
                    events.append({"event": "health_check_after_hang", **pr})
                    if pr.get("ok"):
                        ck.clear_device_fault(ctx, cam, TEST, pr)
                        continue
                fault = ck.device_fault(ctx, cam) or rec
                row["device_fault_here"] = True
                break
        finish_mode(row, m)
        rows.append(row)
        ctx.log(f"{TEST}: {cam.get('name')} {m.text}: {_summary_line(row)} | layout_agree={row.get('layout_agree')}")
    return rows, fault


def rate_camera(ctx, cam: dict, rows: list[dict], n_in_scope: int, fault: dict | None) -> dict:
    out = {}
    for api in APIS:
        v = rate_api(rows, api, n_in_scope)
        if fault:
            v = fault_verdict(ctx, cam, fault, superseded=v.get("rating"))
        out[f"{GOAL}|{cam['key']}|{api}"] = v
    return out


def run(ctx) -> dict:
    res = ck.new_result(ctx, TEST)
    arr0 = ck.arrivals_before(ctx)
    secs = float(ck.arg(ctx, "raw_seconds", 3.0, 1.5))
    scope = modescope.from_args(getattr(ctx, "args", None))
    raw = Path(ctx.raw_dir) / TEST
    errors: list = []
    per_cam: dict = {}
    verdicts: dict = {}
    cache: dict = {}
    in_scope: dict[str, list[ck.Mode]] = {}
    ctx.log(f"{TEST}: {len(ctx.cameras)} cameras, {secs:g} s per mode and route, scope {scope.text}")
    for cam in ctx.cameras:
        try:
            fm, src = load_formats(ctx, cam, cache)
        except Exception as e:  # noqa: BLE001
            fm, src = None, {"error": repr(e)}
        modes, minfo = raw_modes(fm)
        kept, srec = scope_raw(scope, modes)
        in_scope[cam["key"]] = kept
        base = {"name": cam.get("name"), "is_kiyo": cam.get("is_kiyo"), "speed": cam.get("speed"),
                "formats_source": src, "raw_modes_advertised": [m.text for m in modes], "raw_mode_info": minfo,
                "mode_scope": srec}
        if fm is None:
            for api in APIS:
                verdicts[f"{GOAL}|{cam['key']}|{api}"] = rating.untested("no MF format listing for this camera",
                                                                         {"formats_source": src})
            per_cam[cam["key"]] = {**base, "skipped": "no format listing"}
            continue
        if not kept:
            for api in APIS:
                verdicts[f"{GOAL}|{cam['key']}|{api}"] = no_scope_verdict(srec)
            per_cam[cam["key"]] = {**base, "skipped": srec.get("untested_reason"), "modes": []}
            ctx.log(f"{TEST}: {ck.cam_label(cam)}: {srec.get('untested_reason')}")
            continue
        gated = ck.device_gated(ctx, cam)
        if gated:
            for api in APIS:
                verdicts[f"{GOAL}|{cam['key']}|{api}"] = fault_verdict(ctx, cam, gated)
            per_cam[cam["key"]] = {**base, "skipped": f"untested: device fault since {gated.get('utc')}",
                                   "device_fault": gated, "modes": []}
            ctx.log(f"{TEST}: {ck.cam_label(cam)}: gated (device fault since {gated.get('utc')})")
            continue
        ctx.log(f"{TEST}: {ck.cam_label(cam)}: {len(kept)} in-scope raw mode(s): {[m.text for m in kept]}")
        activity = ck.activity_for_camera(ctx, cam)
        events: list = []
        try:
            rows, fault = _camera(ctx, cam, kept, raw, secs, events)
        except Exception as e:  # noqa: BLE001
            errors.append({"camera": cam["key"], "exception": repr(e)})
            rows, fault = [], None
        verdicts.update(rate_camera(ctx, cam, rows, len(kept), fault))
        per_cam[cam["key"]] = {**base, "modes": rows, "device_fault": fault, "events": events,
                               "activity_at_first_stream": activity,
                               "first_failure": ck.first_failure(ctx, cam)}
    domains, dsrc = camera_domains(ctx)
    plan = contention_plan(in_scope, domains)
    plan["domains_source"] = dsrc
    try:
        contention = run_contention(ctx, plan, in_scope, raw, secs)
    except Exception as e:  # noqa: BLE001
        contention = {**plan, "error": repr(e)}
        errors.append({"contention": repr(e)})
    ctx.log(f"{TEST}: contention: {contention.get('reason') or contention.get('outcomes')}")
    meas = {"mode_scope": {**scope.as_dict(), "rule": "common/modescope streaming scope (default exactly 720 lines at "
                                                      ">= 30 fps, Dom 2026-11-08); no raw exception"},
            "seconds_per_mode": secs, "routes": list(APIS), "length_rule": "YUY2 w*h*2, NV12 w*h*3/2 (MF: the "
            "expected_frame_bytes wincam derived from MF_MT_DEFAULT_STRIDE)", "len_ok_min": LEN_OK_MIN,
            "fps_tol": FPS_TOL, "raw_dir": str(raw), "cameras": per_cam, "contention": contention,
            "arrivals": ck.arrivals_after(ctx, arr0),
            "device_faults": ctx.fault_report() if callable(getattr(ctx, "fault_report", None)) else None,
            "note": "raw frames from different captures are different images: the cross-route comparison is of "
                    "format, length and layout, not bytes"}
    return results.finish_result(res, measurements=meas, verdicts=verdicts, errors=errors)


# ============================================================================================================ offline
def _mode_of(row: dict) -> ck.Mode:
    d = row["mode_detail"]
    return ck.Mode(int(d["width"]), int(d["height"]), int(d["fps_num"]), int(d["fps_den"]), d.get("subtype", "YUY2"))


def reanalyze(run_dir: str | Path, raw_dir: str | Path | None = None, out: str | Path | None = None) -> dict:
    """Re-rate a stored W-RAW run from its JSON and the raw capture folders (summary.json + frames.jsonl), no
    camera. Stored per-route records are kept where the raw folder is missing."""
    run_dir = Path(run_dir)
    src = json.loads((run_dir / f"{TEST}.json").read_text(encoding="utf-8"))
    meas = src.get("measurements") or {}
    old_raw = Path(meas.get("raw_dir") or "")
    new_raw = Path(raw_dir) / TEST if raw_dir else None
    verdicts, per_cam, missing = {}, {}, []
    for key, c in (meas.get("cameras") or {}).items():
        rows = []
        cam = {"key": key, "name": c.get("name")}
        for old in c.get("modes") or []:
            m = _mode_of(old)
            row = {"mode": old["mode"], "mode_detail": old["mode_detail"], "apis": {}}
            if old.get("skipped"):
                row.update(skipped=old["skipped"], fps_nominal=m.fps)
                rows.append(row)
                continue
            for api, a in (old.get("apis") or {}).items():
                if not isinstance(a, dict) or a.get("untested") or not a.get("out_dir"):
                    row["apis"][api] = a
                    continue
                od = Path(a["out_dir"])
                if new_raw is not None:
                    try:
                        od = new_raw / od.relative_to(old_raw)
                    except ValueError:
                        od = new_raw / od.parent.name / od.name
                try:
                    s = json.loads((od / "summary.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    missing.append(str(od))
                    row["apis"][api] = dict(a, reanalysis_note="raw summary missing: stored values kept")
                    continue
                row["apis"][api] = analyse(api, s, {"rc": a.get("rc"), "timed_out": a.get("timed_out")},
                                           results.read_jsonl(od / "frames.jsonl"), m, od)
            finish_mode(row, m)
            rows.append(row)
        if c.get("modes") is None or (not rows and c.get("skipped")):
            for api in APIS:
                k = f"{GOAL}|{key}|{api}"
                if k in (src.get("verdicts") or {}):
                    verdicts[k] = src["verdicts"][k]
            per_cam[key] = c
            continue
        n_scope = int((c.get("mode_scope") or {}).get("in_scope") or len(rows))
        fault = c.get("device_fault")
        for api in APIS:
            v = rate_api(rows, api, n_scope)
            verdicts[f"{GOAL}|{key}|{api}"] = fault_verdict(None, cam, fault, v.get("rating")) if fault else v
        per_cam[key] = {**{k: v for k, v in c.items() if k != "modes"}, "modes": rows}
    changes = [{"cell": k, "original": ((src.get("verdicts") or {}).get(k) or {}).get("rating"),
                "reanalysed": v.get("rating")} for k, v in verdicts.items()]
    for ch in changes:
        ch["changed"] = ch["original"] != ch["reanalysed"]
    doc = {"test": TEST, "kind": "offline re-analysis (no camera opened)", "utc": results.utc_now_iso(),
           "source": str(run_dir / f"{TEST}.json"), "rating_changes": changes, "missing_raw": missing[:50],
           "measurements": {"cameras": per_cam, "contention": meas.get("contention")}, "verdicts": verdicts}
    results.write_json(Path(out) if out else run_dir / "reanalysis" / f"{TEST}.json", doc)
    return doc


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="W-RAW offline re-analysis (no camera)")
    ap.add_argument("--reanalyze", "--reanalyse", dest="reanalyze", required=True, help="run folder with W-RAW.json")
    ap.add_argument("--raw-dir", help="raw run folder (default: measurements.raw_dir of the run)")
    ap.add_argument("--out", help="output file (default <run>/reanalysis/W-RAW.json)")
    a = ap.parse_args(argv)
    doc = reanalyze(a.reanalyze, a.raw_dir, a.out)
    for ch in doc["rating_changes"]:
        print(f"{ch['cell']}: {ch['original']} -> {ch['reanalysed']}" + ("  (changed)" if ch["changed"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
