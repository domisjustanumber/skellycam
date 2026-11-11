"""L-ENV: OS / kernel / uvcvideo / session / power / tier-1 state, the context for every rating (plan 6.2 ENV).

Opens no camera. Reads sysfs, /proc, and runs version commands (modinfo, udevadm, pipewire, ...) with timeouts.
Tier-1 items (hwtimestamps, quirks, nodrop, usbcore NO_LPM quirk, video group) are DETECTED only.
"""
from __future__ import annotations

import glob
import grp
import os
import re
from typing import Any

from common import results
import sysfs
from tutil import have, kernel_features, sh

TEST = "L-ENV"
INFO = {"goal": "context", "summary": "kernel, uvcvideo params, session, PipeWire, power, controllers, cameras, "
                                      "tier-1 state (detect only)", "opens_cameras": False}


def plan(ctx) -> dict[str, Any]:
    return {"child_runs": 0, "est_seconds": 15, "steps": ["version commands", "sysfs/proc reads"]}


def _session(ctx) -> dict[str, Any]:
    names = []
    for g in os.getgroups():
        try:
            names.append(grp.getgrgid(g).gr_name)
        except KeyError:
            names.append(str(g))
    out: dict[str, Any] = {"user": os.environ.get("USER"), "uid": os.getuid(), "groups": sorted(set(names)),
                           "in_video_group": "video" in names, "ssh": bool(os.environ.get("SSH_CONNECTION")),
                           "xdg_session_type": os.environ.get("XDG_SESSION_TYPE"),
                           "xdg_current_desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
                           "xdg_session_id": os.environ.get("XDG_SESSION_ID"),
                           "wayland": bool(os.environ.get("WAYLAND_DISPLAY")), "display": os.environ.get("DISPLAY")}
    if os.environ.get("XDG_SESSION_ID") and have("loginctl"):
        r = sh(ctx, ["loginctl", "show-session", os.environ["XDG_SESSION_ID"], "-p", "Active", "-p", "Remote", "-p",
                     "Type", "-p", "Seat", "-p", "Class", "-p", "State"])
        out["loginctl"] = dict(ln.split("=", 1) for ln in (r.get("out") or "").splitlines() if "=" in ln)
    return out


def _pkg_state(ctx) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if have("dpkg-query"):
        r = sh(ctx, ["dpkg-query", "-W", "-f", "${Package} ${Version} ${Status}\\n", "pipewire", "wireplumber",
                     "libspa-0.2-libcamera", "pipewire-libcamera", "libcamera0.3", "v4l-utils", "usbutils",
                     "gstreamer1.0-plugins-good", "psmisc", "tlp", "power-profiles-daemon"])
        out["dpkg"] = (r.get("out") or "").splitlines()
    if have("rpm"):
        r = sh(ctx, ["rpm", "-q", "pipewire", "wireplumber", "pipewire-plugin-libcamera", "libcamera", "v4l-utils",
                     "usbutils", "gstreamer1-plugins-good", "psmisc", "tlp", "tuned", "power-profiles-daemon"])
        out["rpm"] = (r.get("out") or "").splitlines()
    return out


def _versions(ctx) -> dict[str, Any]:
    cmds = {"udevadm": ["udevadm", "--version"], "systemd": ["systemctl", "--version"],
            "pipewire": ["pipewire", "--version"], "wireplumber": ["wireplumber", "--version"],
            "v4l2-ctl": ["v4l2-ctl", "--version"], "gst-launch": ["gst-launch-1.0", "--version"],
            "uv": ["uv", "--version"], "ffmpeg": ["ffmpeg", "-hide_banner", "-version"]}
    out = {}
    for k, argv in cmds.items():
        r = sh(ctx, argv)
        out[k] = (r.get("out") or "").splitlines()[:2] if r["available"] else None
    out["tools_present"] = {t: have(t) for t in ("fuser", "lsusb", "pw-dump", "wpctl", "journalctl", "dmesg",
                                                 "getfacl", "loginctl", "gst-launch-1.0", "v4l2-ctl")}
    return out


def _user_services(ctx) -> dict[str, Any]:
    out = {}
    if have("systemctl"):
        for unit in ("pipewire", "pipewire-pulse", "wireplumber", "xdg-desktop-portal"):
            r = sh(ctx, ["systemctl", "--user", "is-active", unit], 8)
            out[unit] = (r.get("out") or r.get("err") or "").strip()[:60]
        for unit in ("tlp", "tuned", "power-profiles-daemon"):
            r = sh(ctx, ["systemctl", "is-active", unit], 8)
            out["system:" + unit] = (r.get("out") or "").strip()[:60]
    return out


def _kernel_log_access(ctx) -> dict[str, Any]:
    out: dict[str, Any] = {"dmesg_restrict": sysfs.rd("/proc/sys/kernel/dmesg_restrict")}
    r = sh(ctx, ["journalctl", "-k", "-n", "1", "--no-pager", "-q"], 10)
    out["journalctl_k"] = {"available": r["available"], "rc": r.get("rc"),
                           "readable": bool(r["available"] and r.get("rc") == 0 and (r.get("out") or "").strip()),
                           "err": r.get("err")}
    d = sh(ctx, ["dmesg", "--ctime", "-l", "err"], 10)
    out["dmesg"] = {"available": d["available"], "rc": d.get("rc"), "readable": d.get("rc") == 0}
    return out


def _tier1(ctx, uvc: dict, usbcore: dict, cams: list[dict], session: dict) -> dict[str, Any]:
    cmdline = sysfs.rd("/proc/cmdline") or ""
    modprobe = {}
    for f in sorted(glob.glob("/etc/modprobe.d/*.conf") + glob.glob("/usr/lib/modprobe.d/*.conf")):
        try:
            txt = open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        hits = [ln.strip() for ln in txt.splitlines() if re.search(r"uvcvideo|usbcore", ln) and not
                ln.strip().startswith("#")]
        if hits:
            modprobe[f] = hits
    kiyo = [c for c in cams if c["is_kiyo"]]
    return {
        "uvcvideo_hwtimestamps": uvc.get("hwtimestamps"),
        "uvcvideo_quirks": uvc.get("quirks"),
        "uvcvideo_quirks_note": "-1 = per-device table; any other value REPLACES the table (drops the C922 SOF quirk)",
        "uvcvideo_nodrop": uvc.get("nodrop"),
        "uvcvideo_clock": uvc.get("clock"),
        "uvcvideo_trace": uvc.get("trace"),
        "usbcore_quirks": usbcore.get("quirks"),
        "usbcore_quirks_has_kiyo_no_lpm": "1532:0e05:k" in (usbcore.get("quirks") or "").lower(),
        "kernel_cmdline_usb_uvc": [t for t in cmdline.split() if t.startswith(("usbcore.", "uvcvideo."))],
        "modprobe_d": modprobe,
        "kiyo_no_lpm_quirk_active": [{"key": c["key"], "quirks": c["quirks"], "no_lpm": c["no_lpm_quirk"],
                                      "lpm_u1": c["power"].get("usb3_hardware_lpm_u1"),
                                      "lpm_u2": c["power"].get("usb3_hardware_lpm_u2")} for c in kiyo],
        "video_group_member": session.get("in_video_group"),
        "note": "tier-1 settings are detected only; the suite never writes them (plan 6.1)",
    }


def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST)
    errors: list[dict] = []
    kv = ctx.kernel()
    uvc = sysfs.uvc_params()
    usbcore = sysfs.usbcore_params()
    session = _session(ctx)
    cams = ctx.cameras
    modinfo = sh(ctx, ["modinfo", "uvcvideo"])
    mi = {}
    for ln in (modinfo.get("out") or "").splitlines():
        if ":" in ln:
            k, v = ln.split(":", 1)
            if k.strip() in ("filename", "version", "srcversion", "vermagic", "signer", "intree", "name"):
                mi[k.strip()] = v.strip()
            elif k.strip() == "parm":
                mi.setdefault("parm", []).append(v.strip()[:200])
    lsusb = sh(ctx, ["lsusb", "-t"])
    klog = _kernel_log_access(ctx)
    ctx.env_facts.update({"kernel": kv, "features": kernel_features(kv),
                          "journal_readable": klog["journalctl_k"]["readable"], "session": session,
                          "uvc_params": uvc})
    topo = ctx.topology or {}
    cam_health = []
    for c in cams:
        cam_health.append({**sysfs.camera_brief(c), "interface_driver": c.get("interface_driver"),
                           "bcd_device": c.get("bcd_device"), "version": c.get("version"),
                           "speed_downgraded": c.get("speed_downgraded"), "quirks": c.get("quirks"),
                           "no_lpm_quirk": c.get("no_lpm_quirk"), "power": c.get("power"),
                           "port_connect_type": c.get("port_connect_type"),
                           "vs_interfaces": c.get("vs_interfaces"), "bcdUVC": c["descriptors"].get("bcdUVC"),
                           "dwClockFrequency": c["descriptors"].get("dwClockFrequency"),
                           "descriptor_error": c["descriptors"].get("error"),
                           "extension_units": c["descriptors"].get("extension_units"),
                           "default_mode": c["modes"]["default"]})
        if c.get("interface_driver") != "uvcvideo":
            errors.append({"camera": c["key"], "stage": "env", "message": f"interface driver is "
                                                                           f"{c.get('interface_driver')!r}"})
    meas = {
        "kernel": {"release": sysfs.rd("/proc/sys/kernel/osrelease"), "version_tuple": kv,
                   "proc_version": sysfs.rd("/proc/version")},
        "expected_kernel_features": kernel_features(kv),
        "uvcvideo": {"loaded": bool(uvc), "modinfo": mi, "parameters": uvc},
        "usbcore_parameters": usbcore,
        "versions": _versions(ctx),
        "packages": _pkg_state(ctx),
        "user_services": _user_services(ctx),
        "session": session,
        "kernel_log_access": klog,
        "controllers": topo.get("controllers"),
        "buses": topo.get("buses"),
        "lsusb_t": (lsusb.get("out") or "").splitlines() if lsusb["available"] else None,
        "cameras": cam_health,
        "n_cameras": len(cams),
        "kiyo_present": any(c["is_kiyo"] for c in cams),
        "tier1_state": _tier1(ctx, uvc, usbcore, cams, session),
        "flash_ground_truth": "unavailable on Linux (no flash tool in the suite yet); --flash recorded only"
        if ctx.args.flash else None,
    }
    if not uvc:
        errors.append({"stage": "env", "message": "uvcvideo module not loaded (/sys/module/uvcvideo missing)"})
    results.finish_result(res, measurements=meas, verdicts={}, errors=errors)
    return res
