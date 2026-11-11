"""W-ENV: environment and camera health context for every rating (plan section 6.2, windows_mf_vs_ds.md W-ENV).

Read-only. Opens no camera. Records:
  * OS build / UBR, elevation, Python and package versions (common.results.env_info);
  * USB controllers (from the topology collector, cached hub state only);
  * every camera with health: devnode status / problem code / DN_NEED_RESTART, service, driver version, firmware
    bcdDevice, speed, LastArrivalDate and minutes since arrival (Kiyo LPM hypothesis needs plug-in age);
  * every camera's negotiated USB speed and plug-in age read NOW (``usb_link``: hub IOCTL
    CONNECTION_INFORMATION_EX / _V2 from the hub driver's cached state, LastArrivalDate from CfgMgr; no device
    request), with a flag when the Razer Kiyo Pro is not at SuperSpeed;
  * power settings (read-only ``powercfg /qh`` of the USB subgroup): USB selective suspend, USB 3 Link Power
    Management, hub selective suspend timeout, IOC on all TDs; the global DisableSelectiveSuspend registry value;
  * software that holds or controls cameras: LogiTune/LogiTuneAgent/Updater (veto device restarts), Razer Synapse /
    Razer services, OBS, NVIDIA Broadcast, Camera app, Teams, Zoom ... (``tasklist``), with PIDs so W-CYC's
    IMFSensorActivityMonitor PIDs can be attributed;
  * Frame Server and Frame Server Monitor service state, PID and start type (``sc queryex`` / ``sc qc``);
  * the MetadataBufferSizeInKB<n> registry value (read only, never written, deleted or reverted): on each camera's
    CURRENT interface instance and on every other DeviceClasses instance of the same VID:PID (``metadata_registry``).
    Environment context only: present or not, it could change MF's per-sample work, so it is recorded here; no test
    reads UVC metadata or rates anything on it (tier 0 only, Dom 2026-11-09).
No rating (context only); flags list what can bias other tests, including (ctrl_id_env B11):
  * registered virtual cameras (NDI, OBS, NVIDIA Broadcast, SpoutCam ...) with the MF / DS index ranges they occupy:
    their DirectShow filters load into every process that enumerates DS and they shift index-based opens;
  * which cameras' current instances carry MetadataBufferSizeInKB<n> (environment note, not a defect).
Offline: ``python w_env.py --reanalyze <run_dir>`` recomputes the flags from a stored W-ENV.json into
<run_dir>/reanalysis/W-ENV.json.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _enum_util as U  # noqa: E402

TEST_ID = "W-ENV"
USB_SUBGROUP = "2a737441-1930-4402-8d77-b2bebba308a3"
SETTINGS = {"48e6b7a6-50f5-4782-a5d4-53bb8f07e226": "usb_selective_suspend",
            "d4e98f31-5ffe-4ce1-be31-1b38b384c009": "usb3_link_power_management",
            "0853a681-27c8-4100-a2fd-82013e970683": "hub_selective_suspend_timeout_ms",
            "498c044a-201b-4631-a522-5c744ed4e678": "ioc_on_all_tds"}
PROC_PATTERNS = {
    "logitech": r"logi|lghub|lvui|logioptions",
    "razer": r"razer|synapse",
    "obs": r"^obs(64|32)?\.exe$|obs-browser",
    "nvidia_broadcast": r"nvidia broadcast|nvbroadcast",
    "windows_camera_app": r"^windowscamera\.exe$",
    "conferencing": r"^(ms-)?teams|zoom|webex|skype|discord|slack",
    "virtual_camera": r"spout|ndi|virtualcam|xsplit|snap ?camera|mmhmm|camo",
    "browsers_may_hold_camera": r"^(chrome|msedge|firefox)\.exe$",
}


def _powercfg(ctx) -> dict:
    r = ctx.run(["powercfg", "/qh", "SCHEME_CURRENT", USB_SUBGROUP], timeout_s=20)
    out: dict = {"rc": r["rc"], "settings": {}}
    text = (r["stdout"] or "").replace("\r", "")
    m = re.search(r"Power Scheme GUID:\s*([0-9a-f-]+)\s*\(([^)]*)\)", text)
    if m:
        out["scheme_guid"], out["scheme_name"] = m.group(1), m.group(2)
    blocks = re.split(r"\n\s*Power Setting GUID:\s*", text)
    for b in blocks[1:]:
        g = re.match(r"([0-9a-f-]+)\s*\(([^)]*)\)", b)
        if not g:
            continue
        guid, fname = g.group(1), g.group(2)
        opts = dict(re.findall(r"Possible Setting Index:\s*(\d+)\s*\n\s*Possible Setting Friendly Name:\s*(.+)", b))
        ac = re.search(r"Current AC Power Setting Index:\s*0x([0-9a-f]+)", b)
        dc = re.search(r"Current DC Power Setting Index:\s*0x([0-9a-f]+)", b)
        acv = int(ac.group(1), 16) if ac else None
        dcv = int(dc.group(1), 16) if dc else None
        out["settings"][SETTINGS.get(guid, guid)] = {
            "guid": guid, "friendly": fname.strip(), "ac_index": acv, "dc_index": dcv,
            "ac_text": opts.get(f"{acv:03d}") if acv is not None and opts else None,
            "dc_text": opts.get(f"{dcv:03d}") if dcv is not None and opts else None,
            "options": opts or None}
    if r["rc"] != 0:
        out["stderr"] = r["stderr"][-400:]
    return out


def _services(ctx) -> dict:
    out = {}
    for svc in ("FrameServer", "FrameServerMonitor"):
        q = ctx.run(["sc", "queryex", svc], timeout_s=15)
        c = ctx.run(["sc", "qc", svc], timeout_s=15)
        st = re.search(r"STATE\s*:\s*(\d+)\s+(\w+)", q["stdout"])
        pid = re.search(r"PID\s*:\s*(\d+)", q["stdout"])
        start = re.search(r"START_TYPE\s*:\s*(\d+)\s+(\w+)", c["stdout"])
        out[svc] = {"state": st.group(2) if st else None, "pid": int(pid.group(1)) if pid else None,
                    "start_type": start.group(2) if start else None, "rc": q["rc"]}
    return out


def _processes(ctx) -> dict:
    r = ctx.run(["tasklist", "/fo", "csv", "/nh"], timeout_s=30)
    rows = list(csv.reader(io.StringIO(r["stdout"])))
    found: dict = {k: [] for k in PROC_PATTERNS}
    for row in rows:
        if len(row) < 2:
            continue
        name, pid = row[0], row[1]
        for k, pat in PROC_PATTERNS.items():
            if re.search(pat, name, re.I):
                found[k].append({"name": name, "pid": int(pid) if pid.isdigit() else pid,
                                 "session": row[2] if len(row) > 2 else None})
    return {"n_processes": len(rows), "matches": {k: v for k, v in found.items() if v}, "rc": r["rc"]}


def _metadata_instances(cams: list[dict]) -> list[dict]:
    """Every DeviceClasses interface instance of the cameras' VID:PIDs that carries MetadataBufferSizeInKB*."""
    import winpnp as wp
    vidpids = {(c["vid"], c["pid"]) for c in cams if c.get("vid")}
    current = {str(c.get("function_instance_id", "")).replace("\\", "#").upper() for c in cams}
    out = []
    for cat in ("KSCATEGORY_CAPTURE", "KSCATEGORY_VIDEO_CAMERA"):
        g = wp.GUIDS[cat].upper()
        base = f"SYSTEM\\CurrentControlSet\\Control\\DeviceClasses\\{g}"
        for sub in wp.reg_subkeys(base) or []:
            u = sub.upper()
            if not any(f"VID_{v.upper()}&PID_{p.upper()}" in u for v, p in vidpids):
                continue
            dp = wp.reg_values(f"{base}\\{sub}\\#GLOBAL\\Device Parameters") or {}
            md = {k: v for k, v in dp.items() if k.lower().startswith("metadatabuffersizeinkb")}
            inst = u.removeprefix("##?#").split("#{")[0]
            out.append({"category": cat, "interface_key": sub, "function_instance": inst.replace("#", "\\"),
                        "is_current_instance": inst in current, "metadata_values": md or None})
    return out


def metadata_registry_note(cams: list[dict], instances: list[dict] | None) -> dict:
    """Which cameras carry MetadataBufferSizeInKB<n> on their CURRENT interface instance, and which other (old)
    instances of the same VID:PID still hold a value. Environment context only (tier 0 only, Dom 2026-11-09): the
    registry is never written, and nothing downstream reads UVC metadata or rates on this."""
    inst = instances or []
    present = []
    for c in cams:
        cur = str(c.get("function_instance_id") or "").upper()
        vals = next((i.get("metadata_values") for i in inst
                     if i.get("metadata_values") and str(i.get("function_instance") or "").upper() == cur), None)
        if vals or c.get("metadata_tier1"):
            present.append({"key": c.get("key"), "name": c.get("name"),
                            "current_instance": c.get("function_instance_id"),
                            "values": vals or c.get("metadata_values_kb")})
    cur_all = {str(c.get("function_instance_id") or "").upper() for c in cams}
    other = sorted({i.get("function_instance") for i in inst if i.get("metadata_values")
                    and str(i.get("function_instance") or "").upper() not in cur_all
                    and not i.get("is_current_instance")})
    return {"present_on_current_instance": present, "other_instances_with_value": other,
            "note": "read-only environment context (the suite never writes, deletes or reverts the value); it may "
                    "change MF's per-sample work, and no test uses UVC metadata"}


def _ranges(idx: list[int]) -> str:
    idx = sorted(set(i for i in idx if isinstance(i, int)))
    out, start, prev = [], None, None
    for i in idx:
        if start is None:
            start = prev = i
        elif i == prev + 1:
            prev = i
        else:
            out.append(f"{start}-{prev}" if prev != start else f"{start}")
            start = prev = i
    if start is not None:
        out.append(f"{start}-{prev}" if prev != start else f"{start}")
    return ", ".join(out)


def virtual_camera_summary(virtual: list[dict] | None) -> dict | None:
    """Registered virtual cameras grouped by API with the indices they occupy (B11)."""
    if not virtual:
        return None
    out = {}
    for api in ("mf", "ds"):
        rows = [v for v in virtual if v.get("api") == api]
        if not rows:
            continue
        names: dict[str, int] = {}
        for v in rows:
            base = re.sub(r"\s*\d+$", "", str(v.get("friendly_name") or "?")).strip() or "?"
            names[base] = names.get(base, 0) + 1
        out[api] = {"count": len(rows), "indices": _ranges([v.get("index") for v in rows]), "names": names}
    return out


def env_flags(cams: list[dict], power: dict, processes: dict, virtual: list[dict] | None,
              instances: list[dict] | None, n_cameras: int) -> tuple[list[str], dict]:
    """The W-ENV flag list (and structured details) from the gathered measurements."""
    flags, details = [], {}
    for c in cams:
        sp = c.get("usb_speed_now") or c.get("speed")
        if c.get("is_kiyo") and sp and sp not in ("SS", "SS+"):
            age = c.get("plug_in_age_s")
            flags.append(f"{c['name']} (Razer Kiyo Pro) negotiated {sp}, not SuperSpeed: not on a USB 3 port (or the "
                         "cable / hub limits it to USB 2.0); its results describe USB 2.0 operation"
                         + (f"; plug-in age {age / 60:.1f} min" if isinstance(age, (int, float)) else ""))
        if c.get("dn_warn"):
            flags.append(f"{c['name']}: {c['dn_warn']} (MF may fail with MF_E_REBOOT_REQUIRED until a replug)")
        if c.get("problem_code"):
            flags.append(f"{c['name']}: problem code {c['problem_code']}")
    lpm = ((power or {}).get("settings") or {}).get("usb3_link_power_management") or {}
    if lpm.get("ac_index"):
        flags.append(f"USB 3 LPM is '{lpm.get('ac_text')}' on AC: the Kiyo control-transfer failure hypothesis "
                     "(Linux NO_LPM quirk) is in play; attended item A4 turns it off")
    ss = ((power or {}).get("settings") or {}).get("usb_selective_suspend") or {}
    if ss.get("ac_index"):
        flags.append("USB selective suspend enabled")
    pm = (processes or {}).get("matches") or {}
    if pm.get("logitech"):
        flags.append("Logitech software running (LogiTune vetoes device restarts; may write camera controls)")
    if pm.get("razer"):
        flags.append("Razer software running")
    vs = virtual_camera_summary(virtual)
    if vs:
        details["virtual_cameras"] = vs
        parts = [f"{api.upper()} {x['count']} at indices {x['indices']} ("
                 + ", ".join(f"{n} x{k}" if k > 1 else n for n, k in x["names"].items()) + ")" for api, x in vs.items()]
        flags.append("virtual cameras registered: " + "; ".join(parts) + ". Their DirectShow filters load into every "
                     "process that enumerates DS, and index-based opens (OpenCV VideoCapture(i)) can hit them")
    md = metadata_registry_note(cams, instances)
    details["metadata_registry"] = md
    if md["present_on_current_instance"]:
        flags.append("MetadataBufferSizeInKB<n> is set on the current instance of: "
                     + ", ".join(str(x["name"]) for x in md["present_on_current_instance"])
                     + " (environment note, read only: it may change MF's per-sample work; no test reads UVC "
                       "metadata)")
    if not n_cameras:
        flags.append("no USB camera discovered")
    return flags, details


def reanalyze(run_dir: Path) -> dict:
    """Recompute the W-ENV flags (B11 virtual cameras, the metadata registry note) from a stored W-ENV.json."""
    import json
    d = json.loads((Path(run_dir) / "W-ENV.json").read_text(encoding="utf-8"))
    m = d.get("measurements") or {}
    flags, details = env_flags(m.get("cameras_health") or [], m.get("power") or {}, m.get("processes") or {},
                               (m.get("discovery") or {}).get("virtual_devices"),
                               (m.get("metadata_registry") or m.get("tier1_metadata") or {}).get(
                                   "all_instances_with_keys"),
                               m.get("camera_count") or len(m.get("cameras_health") or []))
    old = m.get("flags") or []
    return {"test": TEST_ID, "reanalysis_of": str(Path(run_dir) / "W-ENV.json"), "verdicts": {},
            "flags": flags, "flag_details": details, "new_flags": [f for f in flags if f not in old],
            "fixes_applied": ["B11 virtual camera flag with index ranges",
                              "metadata registry value as a read-only environment note (tier 0 only, 2026-11-09)"]}


def run(ctx) -> dict:
    def body(res, m, v, e):
        import winpnp as wp
        now = _dt.datetime.now(_dt.timezone.utc)
        m["elevated"] = wp.is_elevated()
        topo, rec = U.collect_topology(ctx)
        m["topology_run"] = rec
        m["controllers"] = [{k: c.get(k) for k in ("id", "name", "pci_id", "kind", "location_info", "parent_desc",
                                                   "behind_pcie_switch")} for c in (topo or {}).get("controllers", [])]
        cams = []
        for c in ctx.cameras:
            age = None
            if c.get("last_arrival"):
                try:
                    age = round((now - _dt.datetime.fromisoformat(c["last_arrival"])).total_seconds() / 60, 1)
                except ValueError:
                    pass
            cams.append({k: c.get(k) for k in (
                "key", "name", "vid", "pid", "is_kiyo", "instance_id", "function_instance_id", "speed", "bcd_device",
                "bcd_usb", "service", "function_service", "driver_version", "driver_provider", "problem_code",
                "devnode_status", "dn_flags", "dn_warn", "function_problem_code", "function_devnode_status",
                "last_arrival", "last_removal", "first_install", "metadata_tier1", "location_path", "port_path",
                "serial_source", "device_parameters", "function_device_parameters", "sources")}
                | {"minutes_since_arrival": age, "metadata_values_kb": (c.get("metadata_registry") or {}).get(
                    "values_kb")})
        # negotiated USB speed + plug-in age, re-read now from the hub's cached connection info (no device request)
        link = U.suitectx.usb_link_report(ctx.cameras, fresh=True)
        m["usb_link"] = link
        for h in cams:
            lr = (link.get("cameras") or {}).get(h["key"]) or {}
            h.update(usb_speed_now=lr.get("speed"), superspeed=lr.get("superspeed"),
                     port_protocols=lr.get("port_protocols"), port_superspeed_capable=lr.get("port_superspeed_capable"),
                     last_arrival_now=lr.get("last_arrival"), plug_in_age_s=lr.get("plug_in_age_s"))
        m["cameras_health"] = cams
        m["power"] = _powercfg(ctx)
        m["usb_service_registry"] = {
            "HKLM\\SYSTEM\\CurrentControlSet\\Services\\USB": wp.reg_values("SYSTEM\\CurrentControlSet\\Services\\USB")}
        m["services"] = _services(ctx)
        m["processes"] = _processes(ctx)
        # environment context only (read-only registry; tier 0 only, Dom 2026-11-09)
        m["metadata_registry"] = {"current_instances": {c["key"]: c.get("metadata_tier1") for c in ctx.cameras},
                                  "all_instances_with_keys": _metadata_instances(ctx.cameras)}
        m["discovery"] = {"errors": ctx.discovery.get("errors"), "virtual_devices": ctx.discovery.get(
            "virtual_devices"), "elapsed_s": ctx.discovery.get("elapsed_s")}
        flags, details = env_flags(cams, m["power"], m["processes"], ctx.discovery.get("virtual_devices"),
                                   m["metadata_registry"]["all_instances_with_keys"], len(ctx.cameras))
        m["flags"] = flags
        m["flag_details"] = details
        m["camera_count"] = len(ctx.cameras)
        m["kiyo_present"] = any(c.get("is_kiyo") for c in ctx.cameras)
        # W-ENV is context for every rating: no goal is rated here (verdicts stay empty; see measurements.flags)
    return U.guarded(ctx, TEST_ID, body)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--reanalyze":
        from common import results as _r
        _out = reanalyze(Path(sys.argv[2]))
        print(_r.write_json(Path(sys.argv[2]) / "reanalysis" / f"{TEST_ID}.json", _out), _out["new_flags"])
        sys.exit(0)
    sys.exit(U.standalone(run, TEST_ID))
