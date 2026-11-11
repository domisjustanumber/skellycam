"""Mode scope for the Linux streaming tests (docs/xplat_capture_plan.md section 6, "Mode scope", Dom 2026-11-06/08).

Streaming tests (L-MJPEG, L-CYC, L-MULTI, L-TS, L-CTRL-EFFECT, the L-KIYO stream probe and the condition streams
of L-FMT-NOGRAB) use only modes with --min-height (720) to --max-height (720) lines at >= --min-fps (30), i.e.
exactly 720 lines by default (Dom 2026-11-08; --max-height 0 restores the >= 720 rule); --all-modes turns the
filter off and restores the earlier mode choices. Listing tests (L-FMT, L-FMT-NOGRAB's listings, L-CTRL-LIST) still
list and compare every mode.

The rule itself lives in common/modescope.py (shared with Windows and macOS): ``in_scope(w, h, fps, min_fps,
min_height, max_height)`` (min..max lines and >= min_fps with a 0.5 % rate tolerance, so 29.97 counts as 30) and
``record(Scope, advertised, kept)``. This module calls them when importable and falls back to the same rule
otherwise (``SOURCE`` says which; ``scope_record(args, n_total, n_kept)`` is used too if a later common version
offers it). Mode dicts here are the Linux suite's {"fourcc", "w", "h", "fps"}.

Picks per camera (``picks``), all in scope unless --all-modes:
    default  MJPG 1280x720@30 if offered, else the nearest in-scope MJPEG mode (area, then rate)
    alt      a second in-scope mode for mode switching: 1920x1080@30, else 1280x720@60, else the in-scope mode
             nearest in area with a different size, else a different rate
    low      the cheapest in-scope mode (smallest area, then lowest rate)
    large    the largest in-scope mode at its highest rate
    modes    every in-scope MJPEG mode (smallest first)
With --all-modes the earlier choices come back: default/small/large from sysfs.pick_modes and alt = the old
L-CYC second mode.
"""
from __future__ import annotations

from typing import Any, Iterable

try:  # the shared rule (created by the Windows agent in parallel); the shim below is the same rule
    from common import modescope as _common  # type: ignore
except Exception:  # noqa: BLE001
    _common = None

DEFAULT_MIN_FPS = 30.0
DEFAULT_MIN_HEIGHT = 720
DEFAULT_MAX_HEIGHT = 720  # Dom 2026-11-08: exactly 720 lines at >= 30 fps; --max-height 0 = no upper bound
FPS_REL_TOL = 0.005     # common.modescope's tolerance: 29.97 and 1e7/333334 count as 30, 25 does not
SOURCE = "common.modescope" if _common is not None and hasattr(_common, "in_scope") else "linux shim (same rule)"


def settings(args: Any) -> dict[str, Any]:
    """{"min_fps", "min_height", "max_height", "all_modes", "source"} from the runner args (defaults when absent;
    max_height 0 = no upper bound, Dom 2026-11-08 default 720 = exactly 720 lines)."""
    mf = getattr(args, "min_fps", None)
    mh = getattr(args, "min_height", None)
    mx = getattr(args, "max_height", None)
    return {"min_fps": float(DEFAULT_MIN_FPS if mf is None else mf),
            "min_height": int(DEFAULT_MIN_HEIGHT if mh is None else mh),
            "max_height": int(DEFAULT_MAX_HEIGHT if mx is None else mx),
            "all_modes": bool(getattr(args, "all_modes", False)), "source": SOURCE}


def _shim_in_scope(w: int, h: int, fps: float, min_fps: float, min_height: int,
                   max_height: int = DEFAULT_MAX_HEIGHT) -> bool:
    top = max(int(max_height), int(min_height)) if max_height else None
    return int(h) >= int(min_height) and (top is None or int(h) <= top) and \
        float(fps) >= float(min_fps) * (1.0 - FPS_REL_TOL)


def in_scope_whf(w: int, h: int, fps: float, min_fps: float = DEFAULT_MIN_FPS,
                 min_height: int = DEFAULT_MIN_HEIGHT, max_height: int = DEFAULT_MAX_HEIGHT) -> bool:
    if _common is not None and hasattr(_common, "in_scope"):
        try:
            return bool(_common.in_scope(int(w), int(h), float(fps), min_fps=min_fps, min_height=min_height,
                                         max_height=max_height))
        except Exception:  # noqa: BLE001  (signature drift: the shim is the same rule)
            pass
    return _shim_in_scope(w, h, fps, min_fps, min_height, max_height)


def in_scope(m: dict[str, Any] | None, args: Any) -> bool:
    if not m:
        return False
    s = settings(args)
    if s["all_modes"]:
        return True
    try:
        return in_scope_whf(int(m["w"]), int(m["h"]), float(m["fps"]), s["min_fps"], s["min_height"],
                            s["max_height"])
    except (KeyError, TypeError, ValueError):
        return False


def filter_modes(modes: Iterable[dict[str, Any]], args: Any) -> list[dict[str, Any]]:
    return [m for m in modes or [] if in_scope(m, args)]


def _mode_text(m: Any) -> str:
    try:
        return f"{m.get('fourcc', 'MJPG')} {int(m['w'])}x{int(m['h'])}@{float(m['fps']):g}"
    except (AttributeError, KeyError, TypeError, ValueError):
        return str(m)


def record(args: Any, n_total: int, n_kept: int, advertised: list | None = None, kept: list | None = None,
           **extra: Any) -> dict[str, Any]:
    """What a streaming test records about the scope it used: the settings and n_advertised / n_in_scope /
    n_excluded, plus the shared common.modescope.record fields (scope, advertised, in_scope, excluded and the mode
    lists) when the module and the mode lists are available."""
    s = settings(args)
    out: dict[str, Any] = {**s, "n_advertised": int(n_total), "n_in_scope": int(n_kept),
                           "n_excluded": int(n_total) - int(n_kept)}
    if _common is not None:
        try:
            if hasattr(_common, "scope_record"):
                r = _common.scope_record(args, n_total, n_kept)
            elif hasattr(_common, "record") and hasattr(_common, "from_args") and advertised is not None:
                r = _common.record(_common.from_args(args), advertised, kept, mode_text=_mode_text)
            else:
                r = None
            if isinstance(r, dict):
                out = {**r, **out}
        except Exception as e:  # noqa: BLE001
            out["common_record_error"] = f"{type(e).__name__}: {e}"
    out.update(extra)
    return out


def advertised(ctx, cam: dict[str, Any]) -> list[dict[str, Any]]:
    """Every advertised MJPEG mode of a camera: L-FMT's V4L2 list when it ran, else the descriptors."""
    shared = (getattr(ctx, "shared", None) or {}).get("v4l2_modes", {}).get(cam["key"])
    return list(shared or (cam.get("modes") or {}).get("all_mjpeg") or [])


def _key(m: dict[str, Any] | None) -> tuple | None:
    return None if not m else (int(m["w"]), int(m["h"]), round(float(m["fps"]), 2))


def _fmt(m: dict[str, Any]) -> dict[str, Any]:
    return {"fourcc": m.get("fourcc", "MJPG"), "w": int(m["w"]), "h": int(m["h"]), "fps": float(m["fps"])}


def _dedupe(modes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for m in modes:
        k = _key(m)
        if k not in seen:
            seen.add(k)
            out.append(_fmt(m))
    return sorted(out, key=lambda m: (m["w"] * m["h"], m["fps"]))


def picks(ctx, cam: dict[str, Any]) -> dict[str, Any]:
    """Scoped mode picks for one camera (see the module docstring) plus its scope ``record``."""
    args = ctx.args
    adv = _dedupe(advertised(ctx, cam))
    s = settings(args)
    cm = cam.get("modes") or {}
    if s["all_modes"]:
        a = cm.get("small") or cm.get("default")
        b = cm.get("default") if _key(cm.get("default")) != _key(a) else cm.get("large")
        return {"default": cm.get("default"), "alt": b, "low": cm.get("small"), "large": cm.get("large"),
                "cyc_pair": (a, b), "ctrl_mode": cm.get("small") or cm.get("default"), "modes": adv,
                "record": record(args, len(adv), len(adv), adv, adv,
                                 note="--all-modes: no filter, earlier mode choices")}
    inn = [m for m in adv if in_scope(m, args)]
    rec = record(args, len(adv), len(inn), adv, inn)
    if not inn:
        rec["no_in_scope_mjpeg_mode"] = True
        return {"default": None, "alt": None, "low": None, "large": None, "cyc_pair": (None, None),
                "ctrl_mode": None, "modes": [], "record": rec}
    target = next((m for m in inn if (m["w"], m["h"]) == (1280, 720) and abs(m["fps"] - 30) < 0.5), None)
    default = target or min(inn, key=lambda m: (abs(m["w"] * m["h"] - 1280 * 720), abs(m["fps"] - 30), -m["fps"]))
    rec["default_is_1280x720_30"] = target is not None

    def find(w, h, fps):
        return next((m for m in inn if (m["w"], m["h"]) == (w, h) and abs(m["fps"] - fps) < 0.5
                     and _key(m) != _key(default)), None)
    alt = find(1920, 1080, 30) or find(1280, 720, 60)
    if alt is None:
        others = [m for m in inn if _key(m) != _key(default)]
        diff_size = [m for m in others if (m["w"], m["h"]) != (default["w"], default["h"])]
        pool = diff_size or others
        alt = min(pool, key=lambda m: (abs(m["w"] * m["h"] - default["w"] * default["h"]),
                                       abs(m["fps"] - default["fps"]))) if pool else None
    low = min(inn, key=lambda m: (m["w"] * m["h"], m["fps"]))
    big_area = max(m["w"] * m["h"] for m in inn)
    large = max((m for m in inn if m["w"] * m["h"] == big_area), key=lambda m: m["fps"])
    if alt is None:
        rec["alt_note"] = "only one in-scope mode: no second mode for mode switching"
    return {"default": default, "alt": alt, "low": low, "large": large, "cyc_pair": (default, alt),
            "ctrl_mode": default, "modes": inn, "record": rec}


def test_record(ctx, cams: Iterable[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    """measurements['mode_scope'] for a streaming test: the settings and each camera's record + picks."""
    per = {}
    for c in cams:
        p = picks(ctx, c)
        per[c["key"]] = {**p["record"], "default": p["default"], "alt": p["alt"], "low": p["low"],
                         "large": p["large"]}
    return {**settings(ctx.args), "per_camera": per, **extra}


def untested_scope(rec: dict[str, Any]) -> dict[str, Any]:
    """A rating-shaped 'untested (scope)' verdict for a camera with no in-scope MJPEG mode."""
    lines = f">= {rec.get('min_height')} lines"
    if rec.get("max_height"):
        top = max(int(rec["max_height"]), int(rec.get("min_height") or 0))
        lines = f"{rec.get('min_height')} lines" if top == rec.get("min_height") else \
            f"{rec.get('min_height')}-{top} lines"
    why = (f"untested (scope): no MJPEG mode at >= {rec.get('min_fps'):g} fps and {lines} "
           f"({rec.get('n_advertised')} advertised, all excluded); --all-modes or --max-height 0 to include them")
    return {"rating": "untested", "criteria": [{"criterion": "measured", "met": None, "detail": why}],
            "evidence": {"mode_scope": rec}, "note": why, "summary_label": "untested (scope)"}
