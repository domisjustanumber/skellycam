"""Pure helpers of ``pymf multi`` (no COM, any OS): the compact per-frame record file and the fault classes.

The analysis side (tests/w_pymf_all.py, run inside run_suite's environment, which has no comtypes) imports this
module alone, so it must never import com / mf.

Per-frame record (``frames.bin``, one file per camera, little endian, no header; ``REC.size`` = 41 bytes):

| field | type | meaning |
| seq | u32 | frame index in this camera's stream (0 = first sample) |
| qpc_ns | i64 | arrival: time.perf_counter_ns() at OnReadSample entry (QPC; same point as wincam's qpc_ns) |
| sample_time_100ns | i64 | IMFSample::GetSampleTime (MF sample time), NO_TIME when the sample has none |
| sample_duration_100ns | i64 | IMFSample::GetSampleDuration |
| bytes | u32 | JPEG size (contiguous buffer length) |
| reader_flags | u32 | the source reader's flags for this sample |
| bits | u8 | BIT_* below |
| sof_w, sof_h | u16, u16 | SOFn width / height from the marker walk (0 when none) |

Tier 0 only (Dom 2026-11-09): no UVC PTS/SCR field exists here.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Iterable

REC = struct.Struct("<IqqqIIBHH")
FIELDS = ("seq", "qpc_ns", "sample_time_100ns", "sample_duration_100ns", "bytes", "reader_flags", "bits", "sof_w",
          "sof_h")
NO_TIME = -(1 << 63)
BIT_SOI = 0x01          # starts with FFD8
BIT_EOI = 0x02          # FFD9 at the end, or within the last 4 KB (trailing bytes after it)
BIT_SIZE = 0x04         # SOFn size == the requested size
BIT_DISC = 0x08         # MFSampleExtension_Discontinuity set
BIT_TRAIL = 0x10        # bytes after the last FFD9
BIT_SAVED = 0x20        # this frame was written as a sample / control-window JPEG
BITS = {"soi": BIT_SOI, "eoi": BIT_EOI, "size_ok": BIT_SIZE, "discontinuity": BIT_DISC, "eoi_trailing": BIT_TRAIL,
        "saved": BIT_SAVED}

#: fault kinds after which the session stops using a camera (its reader is closed at once and never re-opened);
#: for the Kiyo Pro each of these is a device fault the suite marks (ctx.mark_fault -> dead rule)
KIYO_FAULT_KINDS = ("device_error", "first_sample_timeout", "stream_stall", "unreleasable", "open_timeout")
#: fault kinds that mark ANY camera faulted (the suite's rule: 0x8007001F or an unreleasable / hung reader; a plain
#: first-frame timeout or a bandwidth refusal is not a fault for a camera other than the Kiyo Pro)
DEVICE_FAULT_KINDS = ("device_error", "unreleasable")
OPEN_STAGES = ("enumerate", "device_not_found", "activate", "reader_create", "set_type", "read_sample_issue",
               "resolve_url")
DEVICE_ERROR_HR = 0x8007001F


def pack(seq: int, qpc_ns: int, sample_time: int | None, duration: int, nbytes: int, flags: int, bits: int,
         sof_w: int, sof_h: int) -> bytes:
    return REC.pack(seq & 0xFFFFFFFF, int(qpc_ns), NO_TIME if sample_time is None else int(sample_time),
                    int(duration), nbytes & 0xFFFFFFFF, flags & 0xFFFFFFFF, bits & 0xFF, max(0, sof_w) & 0xFFFF,
                    max(0, sof_h) & 0xFFFF)


def unpack_all(blob: bytes) -> list[dict]:
    """Every whole record in ``blob`` as a dict (``sample_time_100ns`` None for NO_TIME; a torn tail is ignored)."""
    out = []
    n = len(blob) // REC.size
    for i in range(n):
        v = REC.unpack_from(blob, i * REC.size)
        r = dict(zip(FIELDS, v))
        if r["sample_time_100ns"] == NO_TIME:
            r["sample_time_100ns"] = None
        out.append(r)
    return out


def read_file(path: str | Path) -> list[dict]:
    p = Path(path)
    try:
        return unpack_all(p.read_bytes()) if p.exists() else []
    except OSError:
        return []


def write_file(path: str | Path, rows: Iterable[dict]) -> None:
    """Test helper: rows (dicts with FIELDS) -> frames.bin."""
    with open(path, "wb") as f:
        for r in rows:
            f.write(pack(r["seq"], r["qpc_ns"], r.get("sample_time_100ns"), r.get("sample_duration_100ns") or 0,
                         r.get("bytes") or 0, r.get("reader_flags") or 0, r.get("bits") or 0, r.get("sof_w") or 0,
                         r.get("sof_h") or 0))


def _hr_int(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v & 0xFFFFFFFF
    try:
        return int(str(v), 16) & 0xFFFFFFFF if str(v).lower().startswith("0x") else int(str(v)) & 0xFFFFFFFF
    except ValueError:
        return None


def fault_kind(err: dict | None, unreleasable: bool = False) -> str | None:
    """The fault kind of one camera's session from its error object (mf.error_obj shape: stage, hr, class) and the
    unreleasable flag. None when the camera has no error. 'error' = any other failure (e.g. a bandwidth refusal or
    an in-use error at open), which is NOT a fault for a camera other than the Kiyo Pro."""
    if unreleasable:
        return "unreleasable"
    if not err:
        return None
    hr = _hr_int(err.get("hr"))
    cls = str(err.get("class") or "")
    stage = str(err.get("stage") or "")
    timed_out = cls == "timeout" or err.get("hr_name") == "timeout"
    if hr == DEVICE_ERROR_HR or cls == "device_error":       # suitectx.is_device_error's rule
        return "device_error"
    if stage in ("flush", "reader_release", "control_interfaces_release", "shutdown", "wait_read_issue") and timed_out:
        return "unreleasable"
    if stage == "first_sample" and timed_out:
        return "first_sample_timeout"
    if stage == "streaming" and timed_out:
        return "stream_stall"
    if stage in OPEN_STAGES and timed_out:
        return "open_timeout"
    return "error"


def is_kiyo_fault(kind: str | None) -> bool:
    return kind in KIYO_FAULT_KINDS


def choose_control_value(item: dict, before: dict, start: tuple | None) -> tuple[int | None, str]:
    """The value for one scheduled set (pymf multi spec item) from the control read just before it (mf.read_ctl
    keys: mn, mx, step, def, val, has_range) and the camera's first-read (via, value, flags). Returns (value, rule);
    value None when no rule gives one. ``delta`` counts steps from the current value and flips direction when the
    result leaves the range; any value is clamped to the range when the range is known."""
    mn, mx = before.get("mn"), before.get("mx")
    step = before.get("step") or 1
    cur = before.get("val")
    has_range = bool(before.get("has_range")) and mn is not None and mx is not None and mx > mn
    if "value" in item:
        want = item["value"]
        if want == "start":
            if not start:
                return None, "start value unknown"
            v, why = int(start[1]), "start"
        elif want == "default":
            if before.get("def") is None:
                return None, "default unknown"
            v, why = int(before["def"]), "default"
        else:
            v, why = int(want), "explicit"
    elif "delta" in item:
        if cur is None:
            return None, "current value unknown"
        dv = int(item["delta"]) * int(step)
        v, why = int(cur) + dv, f"current {cur} {'+' if dv >= 0 else '-'} {abs(dv)}"
        if has_range and not (mn <= v <= mx):
            v, why = int(cur) - dv, f"current {cur} {'-' if dv >= 0 else '+'} {abs(dv)} (other direction: range)"
    else:
        return None, "no value / delta in the spec item"
    if has_range and not (mn <= v <= mx):
        v, why = max(mn, min(mx, v)), why + " (clamped)"
    return v, why


def watchdog_ms(spec: dict, timeout_ms: int) -> float:
    """Process watchdog for a ``pymf multi`` spec: part length + open phase + intruders + every camera's controls,
    restores and close (each bounded by timeout_ms) + 60 s. The suite's camcmd timeout goes on top of this."""
    cams = spec.get("cameras") or []
    n_ctl = max([len(c.get("controls") or []) for c in cams] or [0])
    intr = sum(float(i.get("timeout_s", 40)) for i in spec.get("intruders") or []) * 1000.0
    return float(spec.get("seconds", 0)) * 1000.0 + intr + timeout_ms * (16 + 2 * n_ctl) + 60000.0
