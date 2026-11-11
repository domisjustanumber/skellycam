"""Small helpers shared by the Linux test modules (tests/l_*.py). No camera access here."""
from __future__ import annotations

import shutil
from typing import Any

from common import rating
from suitectx import child_outcome


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def sh(ctx, argv: list[str], timeout_s: float = 15.0) -> dict[str, Any]:
    """Run a non-camera command (no lock). {available, rc, out, err}."""
    if not have(argv[0]):
        return {"available": False, "rc": None, "out": None, "err": f"{argv[0]} not installed"}
    r = ctx.run_child(argv, timeout_s)
    return {"available": True, "rc": r.get("rc"), "out": (r.get("stdout") or "").strip()[:20000],
            "err": (r.get("stderr") or "").strip()[-2000:], "timed_out": r.get("timed_out")}


def kernel_features(kv: tuple[int, int]) -> dict[str, Any]:
    """uvcvideo / USB behaviour expected from the kernel version (linux.md section 2 + verifier notes).
    Distro kernels may carry backports either way: these are expectations to compare with what is measured."""
    ge = lambda v: kv >= v  # noqa: E731
    return {
        "kernel": f"{kv[0]}.{kv[1]}",
        "c922_invalid_sof_quirk": ge((6, 11)),
        "error_frames_flagged_by_default": ge((6, 14)),
        "granular_power_management": ge((6, 16)),
        "debugfs_port_bandwidth (root only)": ge((6, 16)),
        "max_payload_clamped (EIO 'no fast enough alt' unreachable)": ge((6, 17)),
        "msxu_1_5_metadata_format": ge((6, 17)),
        "kiyo_no_lpm_quirk_mainline": ge((7, 0)),
        "kiyo_no_lpm_note": "also in stable 6.12.81, 6.18.34, 6.19.12; Ubuntu 6.8 GA unknown (check sysfs quirks)",
        "failed_start_buffer_return_fix": ge((7, 0)),
        "meta_buffersize_via_s_fmt": ge((7, 1)),
        "meta_buffer_fixed_10KiB": not ge((7, 1)),
        "hwtimestamp_sof_fixes_and_sequence_numbers_reliable": ge((7, 2)),
        "nodrop_latched_at_probe (sysfs write needs replug)": True if kv <= (6, 8) else
        "unknown for this version (6.8 latches it at probe; master reads it per buffer)",
    }


def gate(ctx, cam: dict[str, Any], test: str) -> dict[str, Any] | None:
    """Return a skip record if another process streams this camera (our S_FMT would send a PROBE to a camera
    someone else streams: linux.md verifier L27), or if the camera disappeared. None = go ahead."""
    if cam.get("missing"):
        return {"skipped": True, "reason": "camera no longer present (re-enumerated or unplugged)"}
    b = ctx.busy(cam)
    if b["streamed_by_other"]:
        return {"skipped": True, "reason": "another process is streaming this camera (VS alt != 0); not opened",
                "busy": b, "classification": {"class": "in_use", "reason": "streamed by another process"}}
    if b["other_holders"]:
        ctx.log(f"{cam['name']}: held open (not streaming) by {[h['comm'] for h in b['other_holders']]}; proceeding")
    return None


def worker_error(r: dict[str, Any]) -> dict[str, Any] | None:
    j = r.get("json") or {}
    if r.get("timed_out"):
        return {"stage": "timeout", "errno_name": "timeout", "message": f"child killed after {r.get('elapsed_s')}s"}
    if isinstance(j, dict) and j.get("error"):
        return j["error"]
    if r.get("rc") not in (0,) and not j:
        return {"stage": "child", "errno_name": None, "message": f"rc={r.get('rc')} no JSON",
                "stderr_tail": (r.get("stderr") or "")[-800:]}
    return None


def outcome(r: dict[str, Any]) -> dict[str, Any]:
    return child_outcome(r)


def untested(reason: str, evidence: Any = None) -> dict[str, Any]:
    return rating.untested(reason, evidence)


def mode_args(m: dict[str, Any]) -> list[str]:
    return ["--fourcc", m.get("fourcc", "MJPG"), "--width", str(m["w"]), "--height", str(m["h"]),
            "--fps", f"{float(m['fps']):g}"]


def mode_text(m: dict[str, Any] | None) -> str | None:
    if not m:
        return None
    return f"{m.get('fourcc', 'MJPG')} {m['w']}x{m['h']}@{float(m['fps']):g}"
