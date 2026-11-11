"""M-ID: every macOS device list (AVFoundation discovery session, the deprecated devicesWithMediaType, AVFoundation
in a new process each time, the IORegistry) mapped to the camera_identity key, repeated; 1:1 mapping, stable
order, enumeration time; the uniqueID format check (locationID<<32|VID<<16|PID) and modelID check per camera.
Opens no camera (plan 6.2 ID; macos.md G-ID). Attended extension A1 (reboot, replug, port move) is not run here."""
from __future__ import annotations

import suitectx  # noqa: F401
from common import rating, results, tsanalysis

NAME = "M-ID"


def plan(ctx) -> list[str]:
    a = ctx.args
    return [f"mac_avf.py list --repeat {a.id_repeats} (discovery session + legacy list, one process)",
            f"{a.id_proc_repeats} x mac_avf.py list in a new process each",
            f"{a.id_repeats} x ioreg -r -c IOUSBHostDevice (order of the UVC devices)",
            "map: uniqueID -> locationID/VID/PID -> IORegistry camera -> serial-else-port key; rate_id (persistence: A1)"]


def key_of(dev: dict, by_loc: dict) -> str | None:
    up = dev.get("uid_parsed") or {}
    c = by_loc.get((up.get("location_id"), up.get("vid"), up.get("pid")))
    return c["key"] if c else None


def run(ctx) -> dict:
    import mac_ioreg
    res = ctx.new_result(NAME)
    errors: list = []
    snap_cams = (ctx.snapshot or {}).get("cameras", [])
    by_loc = {(c.get("location_id"), c.get("vid"), c.get("pid")): c for c in snap_cams}
    expected = [c["key"] for c in snap_cams]
    api_runs: dict[str, list[list]] = {"avf_discovery": [], "avf_legacy": [], "avf_new_process": [], "ioregistry": []}
    times: dict[str, list[float]] = {k: [] for k in api_runs}
    m: dict = {}
    r = ctx.avf(["list", "--repeat", ctx.args.id_repeats], 60 + 3 * ctx.args.id_repeats, label="id list repeat")
    j = r.get("json") or {}
    if not j:
        errors.append({"error": "mac_avf list failed", "rc": r.get("rc"), "stderr": r.get("stderr_tail")})
    for run_ in j.get("runs") or []:
        usb = [d for d in run_.get("devices") or [] if d.get("is_usb")]
        api_runs["avf_discovery"].append([key_of(d, by_loc) for d in usb])
        times["avf_discovery"].append(run_.get("elapsed_ms"))
    leg = j.get("legacy") or {}
    if leg.get("devices") is not None:
        api_runs["avf_legacy"].append([key_of(d, by_loc) for d in leg["devices"] if d.get("is_usb")])
        times["avf_legacy"].append(leg.get("elapsed_ms"))
    for i in range(ctx.args.id_proc_repeats):
        rr = ctx.avf(["list"], 60, label=f"id list process {i}")
        jj = rr.get("json") or {}
        if jj.get("runs"):
            usb = [d for d in jj["runs"][0].get("devices") or [] if d.get("is_usb")]
            api_runs["avf_new_process"].append([key_of(d, by_loc) for d in usb])
            times["avf_new_process"].append(jj["runs"][0].get("elapsed_ms"))
        else:
            errors.append({"error": f"list in new process {i} failed", "rc": rr.get("rc")})
    key_by_loc_hex = {c.get("location_hex"): c["key"] for c in snap_cams}
    for i in range(ctx.args.id_repeats):
        st = mac_ioreg.read_device_states(runner=lambda argv, t: ctx.runner(argv, t))
        order = [key_by_loc_hex[loc] for loc in st.get("devices") or {} if loc in key_by_loc_hex]
        api_runs["ioregistry"].append(order)
        times["ioregistry"].append((st.get("elapsed_s") or 0) * 1000)
    api_runs = {k: v for k, v in api_runs.items() if v}
    m["api_runs_first"] = {k: v[0] for k, v in api_runs.items()}
    m["enumeration_ms"] = {k: tsanalysis.stats([x for x in v if x is not None]) for k, v in times.items() if v}
    per_cam = []
    for c in ctx.cameras:
        per_cam.append({"key": c["key"], "key_kind": c.get("key_kind"), "serial": c.get("serial"),
                        "serial_reason": c.get("serial_reason"), "unique_id": c.get("unique_id"),
                        "uid_matches_location": c.get("uid_matches_location"), "model_id": c.get("model_id"),
                        "model_matches_vidpid": c.get("model_matches_vidpid"), "port_path": c.get("port_path"),
                        "stable_port_path": c.get("stable_port_path"),
                        "note": None if c.get("unique_id") else "USB camera in the IORegistry with no AVFoundation entry"})
    m["cameras"] = per_cam
    m["non_usb_devices"] = [d.get("name") for d in (j.get("devices") or []) if not d.get("is_usb")]
    m["bus_byte_caveat"] = ("the port key uses the locationID bus byte (common identity format); it is not stable for "
                            "PCIe/Thunderbolt-attached controllers across reboots (topology_macos pitfall 3): "
                            "stable_port_path names the controller instead; attended item A1 decides")
    v = {"G-ID": rating.rate_id(api_runs, expected, persistence=None, min_runs=min(20, ctx.args.id_repeats))}
    v["G-ID"]["tier"] = 0
    return results.finish_result(res, m, v, errors)
