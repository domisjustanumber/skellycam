"""Mode scope for the macOS streaming tests (plan section 6, 'Mode scope', Dom 2026-11-06). Stdlib only.

Streaming tests (M-MJPEG, M-CYC, M-MULTI, M-TS, M-CTRL-EFFECT) use only modes at >= --min-fps (30) with
--min-height (720) to --max-height (720) lines, i.e. exactly 720 lines at >= 30 fps (Dom 2026-11-08; --max-height 0
= no upper bound, the old >= 720 rule); --all-modes disables the filter. Listing tests (M-FMT, M-CTRL-LIST, M-FMT-NOGRAB)
keep listing and comparing every mode.

The decision and the record layout live in suite/common/modescope.py (in_scope, from_args, record, add_args),
shared by every OS. This module uses it when it is importable and otherwise a local copy with the same rule and
the same record keys, so the macOS suite runs either way. On top it adds the AVFoundation view: a format is
(subtype, w, h, frame-rate ranges), and a "mode" counted in the scope record is one (format, rate) pair, where the
rates are both ends of every range (suitectx.rates_of), the same unit M-FMT lists."""
from __future__ import annotations

import argparse
from typing import Any, Iterable

try:  # the shared helper
    from common import modescope as _common  # type: ignore
except Exception:  # pragma: no cover - depends on the checkout
    _common = None

DEFAULT_MIN_FPS = 30.0
DEFAULT_MIN_HEIGHT = 720
DEFAULT_MAX_HEIGHT = 720  # Dom 2026-11-08: exactly 720 lines (as common.modescope); 0 / None = no upper bound
FPS_REL_TOL = 0.005  # as common.modescope: 29.97 fps (and 29.9999) count as 30; 25 fps does not
LIST_MAX = 60


def _has(name: str) -> bool:
    return _common is not None and hasattr(_common, name)


def source() -> str:
    return "common.modescope" if _has("in_scope") else "macos local shim"


def params(args: Any) -> dict:
    """{min_fps, min_height, max_height, all_modes} from the runner's argparse namespace (missing attributes ->
    defaults; max_height 0 = no upper bound)."""
    mf, mh, mx = getattr(args, "min_fps", None), getattr(args, "min_height", None), getattr(args, "max_height", None)
    return {"min_fps": DEFAULT_MIN_FPS if mf is None else float(mf),
            "min_height": DEFAULT_MIN_HEIGHT if mh is None else int(mh),
            "max_height": DEFAULT_MAX_HEIGHT if mx is None else int(mx),
            "all_modes": bool(getattr(args, "all_modes", False))}


def _top(min_height: int, max_height: int | None) -> int | None:
    """The upper bound in lines (None = none), as common.modescope.effective_max_height: a bound below min_height
    is raised to it."""
    return max(int(max_height), int(min_height)) if max_height else None


def in_scope(w: int, h: int, fps: float | None, min_fps: float = DEFAULT_MIN_FPS,
             min_height: int = DEFAULT_MIN_HEIGHT, max_height: int | None = DEFAULT_MAX_HEIGHT) -> bool:
    """True when a mode is in the streaming scope (fps >= min_fps, min_height <= height <= max_height)."""
    if _has("in_scope"):
        try:
            return bool(_common.in_scope(w, h, fps, min_fps=min_fps, min_height=min_height, max_height=max_height))
        except TypeError:
            pass
    try:
        top = _top(min_height, max_height)
        return (int(h) >= int(min_height) and (top is None or int(h) <= top)
                and float(fps) >= float(min_fps) * (1.0 - FPS_REL_TOL))
    except (TypeError, ValueError):
        return False


def mode_ok(w: int, h: int, fps: float | None, args: Any) -> bool:
    p = params(args)
    if p["all_modes"]:
        return True
    return in_scope(w, h, fps, min_fps=p["min_fps"], min_height=p["min_height"], max_height=p["max_height"])


def scope_dict(args: Any) -> dict:
    if _has("from_args"):
        try:
            return dict(_common.from_args(args).as_dict())
        except Exception:
            pass
    p = params(args)
    p["max_height"] = _top(p["min_height"], p["max_height"])
    return {**p, "text": "all modes (--all-modes)" if p["all_modes"] else _scope_text(p), "fps_rel_tol": FPS_REL_TOL}


def _scope_text(p: dict) -> str:
    """'exactly 720 lines at >= 30 fps' (common.modescope.scope_text when present, else the same wording)."""
    if _has("scope_text"):
        try:
            return str(_common.scope_text(p["min_fps"], p["min_height"], p["max_height"]))
        except Exception:
            pass
    top = _top(p["min_height"], p["max_height"])
    if top is None:
        return f">= {p['min_fps']:g} fps and >= {p['min_height']} lines"
    if top == p["min_height"]:
        return f"exactly {top} lines at >= {p['min_fps']:g} fps"
    return f">= {p['min_fps']:g} fps and {p['min_height']}-{top} lines"


def text(args: Any) -> str:
    p = params(args)
    if p["all_modes"]:
        return "mode scope: all modes (--all-modes)"
    return f"mode scope: {_scope_text(p)} (--all-modes disables)"


def add_args(ap: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """--min-fps, --min-height, --max-height, --all-modes: common.modescope.add_args (the same flags on every OS
    runner)."""
    if _has("add_args"):
        return _common.add_args(ap)
    g = ap.add_argument_group("mode scope (streaming tests only; listing tests use every mode)")
    g.add_argument("--min-fps", dest="min_fps", type=float, default=DEFAULT_MIN_FPS,
                   help=f"streaming tests use only modes at >= this rate (default {DEFAULT_MIN_FPS:g})")
    g.add_argument("--min-height", dest="min_height", type=int, default=DEFAULT_MIN_HEIGHT,
                   help=f"streaming tests use only modes with >= this many lines (default {DEFAULT_MIN_HEIGHT})")
    g.add_argument("--max-height", dest="max_height", type=int, default=DEFAULT_MAX_HEIGHT,
                   help=f"streaming tests use only modes with <= this many lines (default {DEFAULT_MAX_HEIGHT}: "
                        "exactly 720 lines; 0 = no upper bound)")
    g.add_argument("--all-modes", dest="all_modes", action="store_true",
                   help="disable the streaming mode scope (every advertised mode)")
    return ap


# ------------------------------------------------------------------------------------------- AVFoundation formats
def rates(fmt: dict) -> list[float]:
    """Distinct frame rates a format offers (both ends of each range), as suitectx.rates_of."""
    out = set()
    for r in fmt.get("ranges") or []:
        out.add(round(float(r["max_fps"]), 3))
        out.add(round(float(r["min_fps"]), 3))
    return sorted(out)


def supports(fmt: dict, fps: float) -> bool:
    return any(r["min_fps"] - 0.01 <= fps <= r["max_fps"] + 0.01 for r in fmt.get("ranges") or [])


def advertised_modes(formats: Iterable[dict]) -> list[dict]:
    """Every (format, rate) pair as a mode dict {w, h, fps, subtype, format_index} (fps None for a format that
    lists no rate)."""
    out = []
    for f in formats:
        for r in (rates(f) or [None]):
            out.append({"w": f["w"], "h": f["h"], "fps": r, "subtype": f.get("subtype"), "format_index": f.get("index")})
    return out


def mode_label(m: dict) -> str:
    return f"{m.get('subtype')} {m['w']}x{m['h']}" + (f"@{m['fps']:g}" if m.get("fps") is not None else "")


def count_modes(formats: Iterable[dict]) -> int:
    return len(advertised_modes(formats))


def count_scoped_modes(formats: Iterable[dict], args: Any) -> int:
    return sum(1 for m in advertised_modes(formats) if m["fps"] is not None and mode_ok(m["w"], m["h"], m["fps"], args)
               or (m["fps"] is None and params(args)["all_modes"]))


def scoped_rates(fmt: dict, args: Any) -> list[float]:
    """The format's rates that are in scope. A continuous range whose top end is in scope also offers min_fps
    itself (e.g. 1-60 fps offers 30), so min_fps is added when the range covers it."""
    p = params(args)
    out = [r for r in rates(fmt) if mode_ok(fmt["w"], fmt["h"], r, args)]
    if not p["all_modes"] and mode_ok(fmt["w"], fmt["h"], p["min_fps"], args) and supports(fmt, p["min_fps"]):
        out.append(round(p["min_fps"], 3))
    return sorted(set(out))


def scoped_formats(formats: Iterable[dict], args: Any) -> list[dict]:
    """Formats with at least one in-scope rate (order kept)."""
    return [f for f in formats if scoped_rates(f, args)]


# ------------------------------------------------------------------------------------------- records
def _finish(rec: dict, args: Any, unit: str) -> dict:
    rec["n_advertised"], rec["n_in_scope"], rec["n_excluded"] = rec["advertised"], rec["in_scope"], rec["excluded"]
    rec.update(unit=unit, scope_source=source(), text=text(args))
    return rec


def record_for_formats(args: Any, formats: Iterable[dict], unit: str = "AVFoundation format x frame rate") -> dict:
    """What a streaming test records per camera, in common.modescope.record's layout ({scope, advertised,
    in_scope, excluded, in_scope_modes, excluded_modes, ...}) plus n_* aliases, unit and scope_source."""
    adv = advertised_modes(formats)
    kept = [m for m in adv if (m["fps"] is not None and mode_ok(m["w"], m["h"], m["fps"], args))
            or (m["fps"] is None and params(args)["all_modes"])]
    if _has("record") and _has("from_args"):
        try:
            return _finish(dict(_common.record(_common.from_args(args), adv, kept, mode_text=mode_label)), args, unit)
        except Exception:
            pass
    kept_ids = {id(m) for m in kept}
    excl = [m for m in adv if id(m) not in kept_ids]
    rec = {"scope": scope_dict(args), "advertised": len(adv), "in_scope": len(kept), "excluded": len(excl),
           "in_scope_modes": [mode_label(m) for m in kept][:LIST_MAX],
           "excluded_modes": [mode_label(m) for m in excl][:LIST_MAX], "excluded_list_truncated": len(excl) > LIST_MAX}
    return _finish(rec, args, unit)


def scope_record(args: Any, n_total: int, n_kept: int, unit: str = "AVFoundation format x frame rate") -> dict:
    """Counts-only record (test-level totals): {scope, advertised, in_scope, excluded} + n_* aliases."""
    rec = {"scope": scope_dict(args), "advertised": int(n_total), "in_scope": int(n_kept),
           "excluded": int(n_total) - int(n_kept)}
    return _finish(rec, args, unit)
