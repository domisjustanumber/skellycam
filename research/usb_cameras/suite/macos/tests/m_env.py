"""M-ENV: machine, OS, controllers, cameras and their health, software that may hold or change cameras, tier-1
state (none known on macOS), Edge Light attestation. Opens no camera (plan 6.2 ENV)."""
from __future__ import annotations

import os
import re

import suitectx  # noqa: F401
from common import results

NAME = "M-ENV"

#: processes that can hold a camera or write its controls (plan 6.2: "software holding cameras")
HOLDERS = {
    "logitune": r"LogiTune|Logi Tune|logitune", "logi_options": r"Logi Options|logioptionsplus",
    "razer_synapse": r"Razer ?Synapse|RazerAppEngine", "zoom": r"zoom\.us|ZoomOpener", "facetime": r"FaceTime",
    "photo_booth": r"Photo Booth", "obs": r"\bobs\b|OBS", "teams": r"Microsoft Teams|MSTeams",
    "chrome": r"Google Chrome", "firefox": r"firefox", "safari": r"Safari", "camera_controller": r"CameraController",
    "quicktime": r"QuickTime Player", "camo": r"Camo", "ecamm": r"Ecamm",
    "uvc_assistant": r"UVCAssistant|VDCAssistant|AppleCameraAssistant", "cmio_extensions": r"com\.apple\.cmio|CMIOExtension",
}


def _run(ctx, argv, timeout=20.0) -> dict:
    r = ctx.runner(argv, timeout)
    return {"argv": argv, "rc": r.get("rc"), "out": (r.get("stdout") or "").strip()[:20000],
            "err": (r.get("stderr") or "").strip()[:500], "timed_out": r.get("timed_out")}


def plan(ctx) -> list[str]:
    return ["sw_vers, uname, sysctl hw.model / cpu / Rosetta, id -Gn (admin?), pmset -g, ps (camera holders)",
            "controllers + cameras from the IORegistry snapshot (bcdDevice, speed, busy state, AVF in-use flag)",
            "system_profiler SPUSBHostDataType (26+) / SPUSBDataType (<=15) -json for reference (skipped with --quick)",
            "tier-1 knobs: none known on macOS (recorded); Edge Light: operator attestation (--edge-light-off)"]


def run(ctx) -> dict:
    res = ctx.new_result(NAME)
    errors: list = []
    m: dict = {"prelude": ctx.prelude}
    cmds = {"sw_vers": ["sw_vers"], "uname": ["uname", "-a"],
            "hw_model": ["sysctl", "-n", "hw.model"], "cpu": ["sysctl", "-n", "machdep.cpu.brand_string"],
            "rosetta": ["sysctl", "-n", "sysctl.proc_translated"], "os_build": ["sysctl", "-n", "kern.osversion"],
            "memsize": ["sysctl", "-n", "hw.memsize"], "groups": ["id", "-Gn"], "pmset": ["pmset", "-g"],
            "uptime": ["uptime"]}
    m["commands"] = {k: _run(ctx, v) for k, v in cmds.items()}
    groups = m["commands"]["groups"]["out"].split()
    m["is_admin_user"] = "admin" in groups
    m["admin_note"] = ("an admin user can read UVCAssistant lines with `log show` (alt settings, error codes); "
                       "the suite never does it automatically")
    ps = _run(ctx, ["ps", "-axo", "pid,comm"], 20)
    found = {}
    for key, pat in HOLDERS.items():
        hits = [ln.strip() for ln in ps["out"].splitlines() if re.search(pat, ln)]
        if hits:
            found[key] = hits[:5]
    m["camera_related_processes"] = found
    m["controllers"] = [{k: c.get(k) for k in ("id", "name", "class", "kind", "vendor", "pci_id", "bus_byte", "label")}
                        for c in (ctx.snapshot or {}).get("controllers", [])]
    devs = {d["id"]: d for d in (ctx.snapshot or {}).get("devices", [])}
    cams = []
    for c in ctx.cameras:
        d = devs.get(c.get("device_id")) or {}
        cams.append({"key": c["key"], "name": c.get("name"), "vid": c.get("vid"), "pid": c.get("pid"),
                     "bcd_device": c.get("bcd_device"), "serial": c.get("serial"), "speed": c.get("speed"),
                     "location": c.get("location_hex"), "is_kiyo": c.get("is_kiyo"),
                     "avf_listed": bool(c.get("unique_id")), "avf_in_use_by_other_app": c.get("in_use_by_other_app"),
                     "busy_state": d.get("busy_state"), "current_configuration": d.get("current_configuration"),
                     "interfaces": d.get("interfaces"), "n_avf_formats": len(c.get("avf_formats") or [])})
    m["cameras"] = cams
    m["non_usb_avf_devices"] = [{k: d.get(k) for k in ("name", "unique_id", "model_id", "transport", "device_type")}
                                for d in ctx.avf_devices if not d.get("is_usb")]
    if not ctx.args.quick:
        ver = ctx.prelude.get("product_version") or ""
        major = int(ver.split(".")[0]) if ver.split(".")[0].isdigit() else 26
        typ = "SPUSBHostDataType" if major >= 26 else "SPUSBDataType"
        sp = _run(ctx, ["system_profiler", typ, "-json"], 90)
        m["system_profiler"] = {"type": typ, "rc": sp["rc"], "timed_out": sp["timed_out"], "bytes": len(sp["out"]),
                                "note": "reference only; the mapper uses the IORegistry (topology_macos 2.4)"}
        if sp["out"]:
            try:
                (ctx.rawsub("env") / f"system_profiler_{typ}.json").write_text(sp["out"], encoding="utf-8")
            except OSError as e:
                errors.append({"error": f"saving system_profiler output: {e!r}"})
    m["tier1"] = {"known_knobs": [], "note": "macOS has no registry or module-parameter equivalent; libusb/libuvc "
                  "streaming would need root AND a driver detach, which the brief forbids (macos.md 0, 6)"}
    m["camera_permission"] = {"video": ctx.tcc, "responsible_app": {k: os.environ.get(k) for k in
                              ("TERM_PROGRAM", "__CFBundleIdentifier", "SSH_CONNECTION") if os.environ.get(k)}}
    m["edge_light"] = {"operator_confirmed_off": bool(ctx.args.edge_light_off),
                       "note": "Edge Light (26.2+) changes the scene light and is not exposed by AVFoundation; every "
                               "image-based result assumes it is off"}
    m["flash_rig"] = {"requested": bool(ctx.args.flash), "note": "no rig driver in this suite yet (attended item A5)"}
    m["snapshot_warnings"] = (ctx.snapshot or {}).get("warnings")
    if found.get("logitune") or found.get("logi_options") or found.get("razer_synapse"):
        errors.append({"warning": "vendor camera software is running and may write controls", "detail": found})
    return results.finish_result(res, m, {}, errors)
