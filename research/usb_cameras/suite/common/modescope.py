"""Mode scope for the streaming tests (Dom, 2026-11-06 and 2026-11-08; plan docs/xplat_capture_plan.md section 6).

Streaming tests (MJPEG, CYC, MULTI, TS, CTRL-EFFECT, RAW ... on every OS) use ONLY modes with exactly 720 lines at
>= 30 fps by default (Dom 2026-11-08: "I only want 720 >= 30fps"; the 2026-11-06 rule was >= 720 lines). There is
no exception for raw formats: a camera with no in-scope raw mode is untested for that format. Listing tests (FMT,
CTRL-LIST, FMT-NOGRAB) keep listing and comparing every mode.
Runner flags (``add_args``): ``--min-fps`` (default 30), ``--min-height`` (default 720), ``--max-height`` (default
720; 0 = no upper bound), ``--all-modes`` (disables the filter). A ``--max-height`` below ``--min-height`` is raised
to it, so ``--min-height 1080`` alone selects exactly 1080 lines. Each streaming test records the scope it used and
how many advertised modes it excluded (``record``).

Stdlib only, OS-neutral. A "mode" may be any object with ``w``/``h``/``fps`` attributes (Windows capkit.Mode), with
``width``/``height``/``fps`` attributes, a dict with ``width``/``height``/``fps`` (or ``w``/``h``) keys, or a
``(w, h, fps)`` / ``(fourcc, w, h, fps)`` tuple.

    from common import modescope
    scope = modescope.from_args(ctx.args)
    kept, excluded = modescope.split(modes, scope)
    rec = modescope.record(scope, modes, kept)          # -> {"scope": {...}, "advertised": n, "excluded": n, ...}

Rate tolerance: a mode counts as ">= min_fps" when fps >= min_fps * (1 - FPS_REL_TOL) (0.5 %), so a camera's
29.97 fps or an interval of 333334 x 100 ns (29.9999 fps) is in scope at the default 30; 25 fps is not.

Callers that pass only ``min_fps`` / ``min_height`` to ``in_scope`` (the Linux and macOS shims) get the default upper
bound of 720 lines, so the 2026-11-08 rule applies on every OS without changing them.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

DEFAULT_MIN_FPS = 30.0
DEFAULT_MIN_HEIGHT = 720
DEFAULT_MAX_HEIGHT = 720             # Dom 2026-11-08: exactly 720 lines; 0 = no upper bound
FPS_REL_TOL = 0.005
EXCLUDED_LIST_MAX = 60
RAW_RULE = "no exception: raw modes use the same scope (Dom 2026-11-08)"


def effective_max_height(min_height: int, max_height: int | None) -> int | None:
    """The upper bound in lines, or None for no bound (max_height 0 / None). A bound below min_height is raised to
    min_height (``--min-height 1080`` alone means exactly 1080 lines)."""
    if not max_height:
        return None
    return max(int(max_height), int(min_height))


def scope_text(min_fps: float, min_height: int, max_height: int | None) -> str:
    top = effective_max_height(min_height, max_height)
    if top is None:
        return f">= {min_fps:g} fps and >= {min_height} lines"
    if top == int(min_height):
        return f"exactly {min_height} lines at >= {min_fps:g} fps"
    return f">= {min_fps:g} fps and {min_height}-{top} lines"


@dataclass(frozen=True)
class Scope:
    min_fps: float = DEFAULT_MIN_FPS
    min_height: int = DEFAULT_MIN_HEIGHT
    all_modes: bool = False
    max_height: int = DEFAULT_MAX_HEIGHT

    def contains(self, w: Any, h: Any, fps: Any) -> bool:
        return self.all_modes or in_scope(w, h, fps, self.min_fps, self.min_height, self.max_height)

    @property
    def text(self) -> str:
        if self.all_modes:
            return "all modes (--all-modes)"
        return scope_text(self.min_fps, self.min_height, self.max_height)

    def as_dict(self) -> dict[str, Any]:
        return {"min_fps": self.min_fps, "min_height": self.min_height,
                "max_height": effective_max_height(self.min_height, self.max_height), "all_modes": self.all_modes,
                "text": self.text, "fps_rel_tol": FPS_REL_TOL, "raw_formats": RAW_RULE}


DEFAULT = Scope()
ALL = Scope(all_modes=True)


def in_scope(w: Any, h: Any, fps: Any, min_fps: float = DEFAULT_MIN_FPS, min_height: int = DEFAULT_MIN_HEIGHT,
             max_height: int | None = DEFAULT_MAX_HEIGHT) -> bool:
    """True when the mode has min_height..max_height lines (max_height 0 / None: no upper bound; a bound below
    min_height is raised to it) and >= min_fps frames per second (0.5 % rate tolerance). ``w`` is accepted for
    symmetry with the listing APIs; only the height and rate decide."""
    try:
        hh = int(h)
        ff = float(fps)
    except (TypeError, ValueError):
        return False
    top = effective_max_height(min_height, max_height)
    return hh >= int(min_height) and (top is None or hh <= top) and ff >= float(min_fps) * (1.0 - FPS_REL_TOL)


# ------------------------------------------------------------------------------------------------ mode accessors
def whf(m: Any) -> tuple[int | None, int | None, float | None]:
    """(width, height, fps) of a mode object, dict or tuple (None for a field it does not carry)."""
    if isinstance(m, dict):
        w = m.get("width", m.get("w"))
        h = m.get("height", m.get("h"))
        f = m.get("fps")
        if f is None and m.get("interval_100ns"):
            f = 1e7 / float(m["interval_100ns"])
        return _i(w), _i(h), _f(f)
    if isinstance(m, (tuple, list)):
        t = list(m)
        if t and isinstance(t[0], str):
            t = t[1:]
        if len(t) >= 3:
            return _i(t[0]), _i(t[1]), _f(t[2])
        return None, None, None
    w = getattr(m, "w", getattr(m, "width", None))
    h = getattr(m, "h", getattr(m, "height", None))
    f = getattr(m, "fps", None)
    return _i(w), _i(h), _f(f)


def _i(x: Any) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _f(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def text(m: Any) -> str:
    t = getattr(m, "text", None)
    if isinstance(t, str):
        return t
    w, h, f = whf(m)
    return f"{w}x{h}@{f:.4g}" if f is not None else f"{w}x{h}"


# ------------------------------------------------------------------------------------------------ filter / sort
def mode_in(m: Any, scope: Scope = DEFAULT) -> bool:
    w, h, f = whf(m)
    return scope.contains(w, h, f)


def split(modes: Iterable[Any], scope: Scope = DEFAULT) -> tuple[list, list]:
    """(kept, excluded) in the input order."""
    kept, excl = [], []
    for m in modes:
        (kept if mode_in(m, scope) else excl).append(m)
    return kept, excl


def filter_modes(modes: Iterable[Any], scope: Scope = DEFAULT) -> list:
    return split(modes, scope)[0]


def sort_key(m: Any) -> tuple:
    """Largest first, then highest rate (pixel count, width, fps; all descending)."""
    w, h, f = whf(m)
    return (-(w or 0) * (h or 0), -(w or 0), -(f or 0.0))


def sort_modes(modes: Iterable[Any], largest_first: bool = True) -> list:
    out = sorted(modes, key=sort_key)
    return out if largest_first else list(reversed(out))


def nearest(modes: Sequence[Any], w: int, h: int, fps: float) -> Any | None:
    """The mode at exactly w x h with the rate nearest ``fps``; else the size nearest by pixel count (log ratio),
    then the rate nearest ``fps``. None for an empty list."""
    import math
    cand = [m for m in modes if whf(m)[0] and whf(m)[1]]
    if not cand:
        return None
    exact = [m for m in cand if whf(m)[:2] == (w, h)]
    rate = (lambda m: abs((whf(m)[2] or 0.0) - fps))
    if exact:
        return min(exact, key=rate)
    px = max(1, w * h)
    best = min(cand, key=lambda m: (abs(math.log((whf(m)[0] * whf(m)[1]) / px)), rate(m)))
    same = [m for m in cand if whf(m)[:2] == whf(best)[:2]]
    return min(same, key=rate)


def partner(modes: Sequence[Any], default: Any, prefer_fps: float = 30.0) -> Any | None:
    """A second in-scope mode for a mode switch / pair: the largest size other than the default's at the rate
    nearest ``prefer_fps`` (under the 720-line scope e.g. 960x720@30 vs 1280x720@30); else the default's size at
    its highest other rate (720p60); else None. ``modes`` should already be scope-filtered."""
    if default is None:
        return None
    dw, dh, df = whf(default)
    others = [m for m in modes if whf(m)[:2] != (dw, dh)]
    if others:
        big = max((whf(m)[0] or 0) * (whf(m)[1] or 0) for m in others)
        same = [m for m in others if (whf(m)[0] or 0) * (whf(m)[1] or 0) == big]
        return min(same, key=lambda m: (abs((whf(m)[2] or 0) - prefer_fps), -(whf(m)[2] or 0)))
    rates = [m for m in modes if whf(m)[:2] == (dw, dh) and abs((whf(m)[2] or 0) - (df or 0)) > 0.01]
    if rates:
        return max(rates, key=lambda m: whf(m)[2] or 0)
    return None


# ------------------------------------------------------------------------------------------------ record / args
def record(scope: Scope, advertised: Iterable[Any], kept: Iterable[Any] | None = None,
           mode_text: Callable[[Any], str] = text) -> dict[str, Any]:
    """What a streaming test stores per camera: the scope (min_fps, min_height, max_height, all_modes, text), the
    advertised / in-scope / excluded counts and the in-scope and excluded modes (first EXCLUDED_LIST_MAX each)."""
    adv = list(advertised)
    k = list(kept) if kept is not None else filter_modes(adv, scope)
    kept_ids = {id(m) for m in k}
    excl = [m for m in adv if id(m) not in kept_ids] if kept is not None else split(adv, scope)[1]
    return {"scope": scope.as_dict(), "advertised": len(adv), "in_scope": len(k), "excluded": len(excl),
            "in_scope_modes": [mode_text(m) for m in k][:EXCLUDED_LIST_MAX],
            "excluded_modes": [mode_text(m) for m in excl][:EXCLUDED_LIST_MAX],
            "excluded_list_truncated": len(excl) > EXCLUDED_LIST_MAX}


def no_scope_mode_reason(scope: Scope, advertised_n: int, fmt: str = "MJPEG") -> str:
    return (f"untested (scope): none of the camera's {advertised_n} advertised {fmt} modes is in the streaming "
            f"mode scope ({scope.text}); use --all-modes, --max-height 0 or lower --min-fps / --min-height")


def add_args(ap: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """--min-fps, --min-height, --max-height, --all-modes (the same flags on every OS runner)."""
    g = ap.add_argument_group("mode scope (streaming tests only; listing tests use every mode)")
    g.add_argument("--min-fps", dest="min_fps", type=float, default=DEFAULT_MIN_FPS,
                   help=f"streaming tests use only modes at >= this rate (default {DEFAULT_MIN_FPS:g})")
    g.add_argument("--min-height", dest="min_height", type=int, default=DEFAULT_MIN_HEIGHT,
                   help=f"streaming tests use only modes with >= this many lines (default {DEFAULT_MIN_HEIGHT})")
    g.add_argument("--max-height", dest="max_height", type=int, default=DEFAULT_MAX_HEIGHT,
                   help=f"streaming tests use only modes with <= this many lines (default {DEFAULT_MAX_HEIGHT}: the "
                        "default scope is exactly 720 lines at >= 30 fps; 0 = no upper bound; a value below "
                        "--min-height is raised to it)")
    g.add_argument("--all-modes", dest="all_modes", action="store_true",
                   help="disable the streaming mode scope (every advertised mode)")
    return ap


def from_args(args: Any) -> Scope:
    """The Scope from an argparse Namespace (missing attributes fall back to the defaults)."""
    if args is None:
        return DEFAULT
    mf = getattr(args, "min_fps", None)
    mh = getattr(args, "min_height", None)
    mx = getattr(args, "max_height", None)
    return Scope(min_fps=float(DEFAULT_MIN_FPS if mf is None else mf),
                 min_height=int(DEFAULT_MIN_HEIGHT if mh is None else mh),
                 all_modes=bool(getattr(args, "all_modes", False)),
                 max_height=int(DEFAULT_MAX_HEIGHT if mx is None else mx))
