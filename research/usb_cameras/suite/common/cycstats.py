"""Open -> first frame -> N frames -> close cycle statistics (stdlib only).

    from common import cycstats
    s = cycstats.summarize_cycles(rows)    # rows: wincam / pyav_ds / opencv_ds cycles.jsonl dicts

Each row (one cycle) may contain: ok (bool), stage_failed (str|None), hr / hr_name / errno / error_class
(classify_failure class), timed_out / hung (bool), unreleasable (bool), frames (int), and timing fields named
``*_ms`` (activate_ms, reader_ms, settype_ms, first_frame_ms, close_ms, open_ms ...). Missing fields are fine.

Returns {"n", "n_ok", "success_rate", "wilson95": [lo, hi], "first_frame_within_s", "n_first_frame_within",
         "first_frame_within_rate", "first_frame_within_wilson95", "timings_ms": {field: {n,p50,p90,p95,p99,max,
         mean}}, "failure_classes": [{"stage", "code", "name", "class", "count", "first_index"}],
         "hangs", "unreleasable", "recovery_after_failure": {"failures_followed", "recovered", "rate"},
         "longest_failure_run", "failure_indices", "trailing_failures", "open_to_first_frame_ms_p50",
         "format_mismatch_count", "size_mismatch_count", "fps_mismatch_count", "device_reset_count",
         "n_ok_as_requested"}

Timing percentiles drop negative values: wincam writes -1 for a stage that never ran (first_frame_ms of a failed
cycle, shutdown_ms after a hung release), and those sentinels must not become a p50 (analysis cyc_kiyo N4).
Row flags counted (True only): ``format_mismatch`` (the stream was not the requested format, e.g. PyAV's YUY2
fallback or OpenCV's FOURCC readback), ``size_mismatch``, ``fps_mismatch`` (measured rate < 0.9 x requested),
``device_reset`` (the device re-enumerated during the cycle). ``ok`` itself is the open/first-frame/close outcome;
the mismatch counts are reported separately so a rating can tell "opened but not as requested" from a failure.
"""
from __future__ import annotations

import math
from typing import Any, Iterable


def wilson_interval(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score 95% interval for k successes out of n (0..1). (0, 1) when n == 0."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def _pct(sorted_vals: list[float], q: float) -> float:
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def percentiles(values: Iterable[float], drop_negative: bool = False) -> dict[str, Any]:
    """n/min/p50/p90/p95/p99/max/mean of the finite numbers in ``values``; ``drop_negative`` also drops values
    < 0 (tool sentinels such as wincam's -1 for "stage not reached")."""
    v = sorted(float(x) for x in values if isinstance(x, (int, float)) and not isinstance(x, bool)
               and math.isfinite(float(x)) and not (drop_negative and float(x) < 0))
    if not v:
        return {"n": 0}
    return {"n": len(v), "min": v[0], "p50": _pct(v, 0.5), "p90": _pct(v, 0.9), "p95": _pct(v, 0.95),
            "p99": _pct(v, 0.99), "max": v[-1], "mean": sum(v) / len(v)}


def _code(row: dict) -> Any:
    for k in ("hr", "errno", "code", "error_code"):
        if row.get(k) not in (None, 0, "0x00000000"):
            return row[k]
    return None


def summarize_cycles(rows: list[dict[str, Any]], first_frame_within_s: float = 2.0) -> dict[str, Any]:
    """Summarise per-cycle rows; see the module docstring for the output fields. A cycle counts as within the
    reliability criterion when ok and first_frame_ms <= first_frame_within_s * 1000 (plan section 3)."""
    n = len(rows)
    oks = [bool(r.get("ok")) for r in rows]
    n_ok = sum(oks)
    lo, hi = wilson_interval(n_ok, n)
    within = [bool(r.get("ok")) and isinstance(r.get("first_frame_ms"), (int, float))
              and r["first_frame_ms"] <= first_frame_within_s * 1000.0 for r in rows]
    n_within = sum(within)
    wlo, whi = wilson_interval(n_within, n)
    timing_keys = sorted({k for r in rows for k, v in r.items() if k.endswith("_ms")
                          and isinstance(v, (int, float)) and not isinstance(v, bool)})
    timings = {k: percentiles((r.get(k) for r in rows if r.get("ok") or k in ("close_ms",)), drop_negative=True)
               for k in timing_keys}
    timings_all = {k: percentiles((r.get(k) for r in rows), drop_negative=True) for k in timing_keys}
    classes: dict[tuple, dict] = {}
    fail_idx = []
    for i, r in enumerate(rows):
        if r.get("ok"):
            continue
        fail_idx.append(r.get("i", i))
        key = (r.get("stage_failed"), str(_code(r)), r.get("hr_name") or r.get("errno_name"),
               r.get("error_class") or (r.get("classification") or {}).get("class"))
        c = classes.setdefault(key, {"stage": key[0], "code": _code(r), "name": key[2], "class": key[3],
                                     "count": 0, "first_index": r.get("i", i)})
        c["count"] += 1
    followed = recovered = 0
    for a, b in zip(rows, rows[1:]):
        if not a.get("ok"):
            followed += 1
            if b.get("ok"):
                recovered += 1
    run = best = 0
    for ok in oks:
        run = 0 if ok else run + 1
        best = max(best, run)
    hangs = sum(1 for r in rows if r.get("timed_out") or r.get("hung") or r.get("stage_failed") == "timeout")
    unrel = sum(1 for r in rows if r.get("unreleasable") or r.get("stage_failed") == "unreleasable")
    def _flag(name: str) -> int:
        return sum(1 for r in rows if r.get(name) is True)

    o2f = timings.get("open_to_first_frame_ms") or timings.get("first_frame_ms") or {}
    n_asreq = sum(1 for r in rows if r.get("ok") and not any(r.get(f) is True for f in (
        "format_mismatch", "size_mismatch", "fps_mismatch", "device_reset")))
    return {"n": n, "n_ok": n_ok, "success_rate": (n_ok / n) if n else None, "wilson95": [lo, hi],
            "open_to_first_frame_ms_p50": o2f.get("p50"),
            "format_mismatch_count": _flag("format_mismatch"), "size_mismatch_count": _flag("size_mismatch"),
            "fps_mismatch_count": _flag("fps_mismatch"), "device_reset_count": _flag("device_reset"),
            "n_fps_judged": sum(1 for r in rows if r.get("fps_mismatch") is not None),
            "n_ok_as_requested": n_asreq,
            "first_frame_within_s": first_frame_within_s, "n_first_frame_within": n_within,
            "first_frame_within_rate": (n_within / n) if n else None, "first_frame_within_wilson95": [wlo, whi],
            "timings_ms": timings, "timings_ms_all_cycles": timings_all,
            "failure_classes": sorted(classes.values(), key=lambda c: -c["count"]),
            "hangs": hangs, "unreleasable": unrel,
            "recovery_after_failure": {"failures_followed": followed, "recovered": recovered,
                                       "rate": (recovered / followed) if followed else None},
            "longest_failure_run": best, "failure_indices": fail_idx[:500],
            "trailing_failures": len(oks) - (max((i for i, o in enumerate(oks) if o), default=-1) + 1)}
