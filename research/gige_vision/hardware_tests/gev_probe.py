#!/usr/bin/env python3
"""
gev_probe.py - find GigE Vision cameras and report what they support. Read-only by default.

Standard library only (Python >= 3.9); keep gev_common.py next to this file.

For every camera found (broadcast discovery on all IPv4 interfaces, or --ip):
  * discovery data: IP/MAC, vendor, model, serial, user name, subnet check against the host NICs
  * bootstrap Version register -> GigE Vision major.minor (GEV 3.x is flagged)
  * GVCP capability bits (IEEE 1588, 1588 extended/2.1 profiles, scheduled action, unconditional
    action, action, packet resend, pending ack, write mem, ...), GVCP configuration bits
  * IEEE 1588 enable + clock status (Master/Slave/...), 1588 profile registers, scheduled-action queue size
  * timestamp tick frequency, stream channel 0 packet size (SCPS), packet delay, stream channel
    capabilities, 64-bit block id (extended ID) support and state
  * the camera's GenICam XML (downloaded over READMEM, read-only): which PTP / timestamp / action /
    trigger / compression / transport-version features exist and their enum entries (TriggerSource,
    PixelFormat, GevStreamingMode, ...). Use --save-xml DIR to keep the XML for the developers.

Changes camera state ONLY with --enable-ptp: takes control, sets the IEEE 1588 enable bit
(GVCP configuration register 0x0954 bit 0x00080000), watches the clock status, releases control.
The bit stays set until the camera is power-cycled or something clears it.

Examples:
  python gev_probe.py                              # all cameras on all interfaces
  python gev_probe.py --ip 169.254.1.10 --ip 169.254.1.11 --json probe.json --save-xml xml/
  python gev_probe.py --enable-ptp --ptp-wait 30   # turn PTP on and watch Master/Slave election
  python gev_probe.py --selftest                   # offline packet encode/decode checks

Exit code: 0 = at least one camera probed and nothing failed, 1 = a check failed,
2 = no camera found / bad arguments.

DRAFT: verified only against software-emulated cameras (Aravis arv-fake-gv-camera-0.8,
viva-genicam FakeGigeCamera). See README.md.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from typing import Any, Optional

try:
    from . import gev_common as gev  # imported as part of a package (e.g. hardware_tests.<script>)
except ImportError:  # run directly: python gev_probe.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gev_common as gev  # type: ignore[no-redef]


def _hex(v: Optional[int]) -> Optional[str]:
    return None if v is None else f"0x{v:08X}"


def _bits(v: Optional[int], table: list[tuple[str, int, str]]) -> dict[str, Any]:
    if v is None:
        return {"raw": None, "set": []}
    return {"raw": f"0x{v:08X}", "set": gev.bits_set(v, table)}


def probe_camera(dev: dict[str, Any], args: argparse.Namespace, rep: gev.Reporter) -> dict[str, Any]:
    ip = dev["control_ip"]
    cam = f"{ip} {dev.get('manufacturer', '')} {dev.get('model', '')}".strip()
    r: dict[str, Any] = {"ip": ip, "discovery": dev}
    if dev.get("discovery_answered", True):
        if not dev.get("same_subnet_as_host", True):
            rep.add("subnet", gev.WARN, f"camera {dev['ip']}/{dev.get('subnet_mask')} is not on the subnet of any host "
                    "NIC - give the NIC (or the camera, with the vendor IP tool / FORCEIP) an address on one subnet",
                    cam)
    try:
        client = gev.GvcpClient(ip, local_ip=args.iface or "", timeout=args.gvcp_timeout)
    except OSError as e:
        rep.add("open control socket", gev.FAIL, str(e), cam)
        return r
    try:
        ver, err = client.read_reg_opt(gev.REG_VERSION)
        if ver is None:
            rep.add("read bootstrap registers", gev.FAIL, f"READREG of the Version register failed: {err}", cam)
            return r
        rep.add("read bootstrap registers", gev.PASS, f"via local interface {client.local_ip}", cam)
        major, minor = ver >> 16, ver & 0xFFFF
        r["gev_version"] = f"{major}.{minor}"
        r["gev_major"] = major
        if major >= 3:
            rep.add("GigE Vision version", gev.INFO, f"{major}.{minor} - GEV 3.x: GVSP must use extended (64-bit) block "
                    "ids; the optional GVRSP/RDMA streaming of GEV 3.0 is NOT exercised by these tests", cam)
        elif major == 2:
            rep.add("GigE Vision version", gev.INFO, f"{major}.{minor} - PTP and scheduled actions exist since GEV 2.0 "
                    "(see capability bits)", cam)
        elif major == 1:
            rep.add("GigE Vision version", gev.WARN, f"{major}.{minor} - GEV 1.x has no IEEE 1588 / scheduled actions", cam)
        else:
            rep.add("GigE Vision version", gev.WARN, f"Version register reads {major}.{minor} (invalid; emulator?)", cam)
        if dev.get("gev_version") and dev["gev_version"] != r["gev_version"]:
            rep.add("version consistency", gev.WARN, f"DISCOVERY_ACK says {dev['gev_version']}, Version register says "
                    f"{r['gev_version']}", cam)

        regs: dict[str, Any] = {}
        errors: dict[str, str] = {}

        def rd(name: str, addr: int) -> Optional[int]:
            v, e = client.read_reg_opt(addr)
            regs[name] = v
            if v is None:
                errors[name] = e
            return v

        mode = rd("device_mode", gev.REG_DEVICE_MODE)
        cap = rd("gvcp_capability", gev.REG_GVCP_CAPABILITY)
        cfg = rd("gvcp_configuration", gev.REG_GVCP_CONFIGURATION)
        sc_caps = rd("sc_caps", gev.REG_SC_CAPS)
        rd("n_stream_channels", gev.REG_N_STREAM_CHANNELS)
        rd("n_message_channels", gev.REG_N_MESSAGE_CHANNELS)
        hb = rd("heartbeat_timeout_ms", gev.REG_HEARTBEAT_TIMEOUT)
        ccp = rd("ccp", gev.REG_CCP)
        hi = rd("tick_frequency_high", gev.REG_TICK_FREQ_HIGH)
        lo = rd("tick_frequency_low", gev.REG_TICK_FREQ_LOW)
        tick = (hi << 32) | lo if hi is not None and lo is not None else None
        capb = cap or 0
        r["capability"] = _bits(cap, gev.CAPABILITY_BITS)
        r["gvcp_configuration"] = _bits(cfg, gev.GVCP_CONFIG_BITS)
        r["sc_caps"] = _bits(sc_caps, gev.SC_CAPS_BITS)
        r["device_mode"] = _hex(mode)
        r["tick_frequency_hz"] = tick
        r["heartbeat_timeout_ms"] = hb
        r["ccp"] = _hex(ccp)
        if mode is not None:
            r["device_mode_decoded"] = {"big_endian": bool(mode & 0x80000000), "device_class": (mode >> 28) & 0x7,
                                        "current_link_configuration": (mode >> 24) & 0x3, "character_set": mode & 0xF}
        if capb & gev.CAP["link_speed_registers"]:
            r["link_speed_mbps"] = rd("link_speed_0", gev.REG_LINK_SPEED_0)
        rep.add("GVCP capabilities", gev.INFO, ", ".join(r["capability"]["set"]) or f"none ({_hex(cap)})", cam)
        if ccp:
            rep.add("control channel", gev.INFO, f"CCP reads 0x{ccp:X} (control bits set): another application may "
                    "control this camera (vendor viewer?) - tests that take control fail until it is closed", cam)

        # --- timestamps / PTP -------------------------------------------------------------------
        if tick is None:
            rep.add("timestamp tick frequency", gev.WARN, "unreadable", cam)
        elif tick == 0:
            rep.add("timestamp tick frequency", gev.WARN, "0 Hz - device timestamps unusable", cam)
        else:
            note = " (1 ns ticks, typical with PTP)" if tick == 1_000_000_000 else \
                " (Basler ace classic uses 125 MHz until PTP is enabled)" if tick == 125_000_000 else ""
            rep.add("timestamp tick frequency", gev.INFO, f"{tick} Hz{note}", cam)
        ptp: dict[str, Any] = {"supported": bool(capb & gev.CAP["ieee1588"])}
        if ptp["supported"]:
            ptp["enabled"] = bool((cfg or 0) & gev.CFG_IEEE1588_ENABLE)
            st = rd("ieee1588_status", gev.REG_IEEE1588_STATUS)
            ptp["status_raw"] = _hex(st)
            ptp["state"] = gev.PTP_STATES.get((st or 0) & 0xF, f"raw {_hex(st)}") if st is not None else None
            if capb & gev.CAP["ieee1588_extended_capabilities"]:
                ptp["extended_capability"] = _hex(rd("ieee1588_ext_capability", gev.REG_IEEE1588_EXT_CAPABILITY))
                ptp["supported_profiles"] = _bits(rd("ieee1588_supported_profiles", gev.REG_IEEE1588_SUPPORTED_PROFILES),
                                                  gev.IEEE1588_PROFILE_BITS)
                ptp["selected_profile"] = _hex(rd("ieee1588_selected_profile", gev.REG_IEEE1588_SELECTED_PROFILE))
            rep.add("IEEE 1588 (PTP)", gev.PASS, f"supported; enabled={ptp['enabled']}; clock state={ptp['state']}"
                    + (f"; profiles={ptp['supported_profiles']['set']}" if "supported_profiles" in ptp else ""), cam)
        else:
            rep.add("IEEE 1588 (PTP)", gev.SKIP, "not supported: capability bit 0x00080000 clear", cam)
        r["ptp"] = ptp
        act: dict[str, Any] = {"action": bool(capb & gev.CAP["action"]),
                               "scheduled_action": bool(capb & gev.CAP["scheduled_action"]),
                               "unconditional_action": bool(capb & gev.CAP["unconditional_action"])}
        if act["action"]:
            act["n_action_signals"] = rd("n_action_signals", gev.REG_N_ACTION_SIGNALS)
        if act["scheduled_action"]:
            act["scheduled_action_queue_size"] = rd("sched_action_queue_size", gev.REG_SCHED_ACTION_QUEUE_SIZE)
        r["action"] = act
        rep.add("action commands", gev.PASS if act["action"] else gev.SKIP,
                f"action={act['action']} scheduled={act['scheduled_action']} unconditional={act['unconditional_action']}"
                + (f" signals={act.get('n_action_signals')}" if act["action"] else "")
                + (f" queue={act.get('scheduled_action_queue_size')}" if act["scheduled_action"] else ""), cam)

        # --- stream channel 0 -------------------------------------------------------------------
        sc: dict[str, Any] = {}
        scps = rd("sc0_packet_size", gev.reg_sc_packet_size(0))
        if scps is not None:
            sc["packet_size"] = scps & gev.SCPS_PACKET_SIZE_MASK
            sc["do_not_fragment"] = bool(scps & gev.SCPS_DO_NOT_FRAGMENT)
            sc["big_endian_pixels"] = bool(scps & 0x20000000)
        sc["packet_delay_ticks"] = rd("sc0_packet_delay", gev.reg_sc_packet_delay(0))
        sc["host_port"] = rd("sc0_port", gev.reg_sc_port(0))
        dest = rd("sc0_dest", gev.reg_sc_dest_address(0))
        sc["destination"] = socket.inet_ntoa(dest.to_bytes(4, "big")) if dest is not None else None
        if (sc_caps or 0) & 0x80000000:
            sc["source_port"] = rd("sc0_source_port", gev.reg_sc_source_port(0))
        sc["capability"] = _bits(rd("sc0_capability", gev.reg_sc_capability(0)), gev.STREAM_CHANNEL_CAP_BITS)
        sc["configuration"] = _hex(rd("sc0_configuration", gev.reg_sc_configuration(0)))
        gvsp_cfg = rd("gvsp_configuration", gev.REG_GVSP_CONFIGURATION)
        sc["extended_ids_enabled"] = bool((gvsp_cfg or 0) & gev.GVSP_CONFIG_64BIT_BLOCK_ID) if gvsp_cfg is not None else None
        sc["legacy_16bit_block_id_supported"] = bool((sc_caps or 0) & 0x40000000) if sc_caps is not None else None
        r["stream_channel_0"] = sc
        ps = sc.get("packet_size")
        detail = f"SCPS packet size {ps} B ({'jumbo' if ps and ps > 1500 else 'standard MTU'})"
        if major >= 3:
            detail += "; GEV 3.x streams use extended (64-bit) block ids"
        elif sc_caps and sc["legacy_16bit_block_id_supported"] is False:
            detail += "; SC caps report legacy 16-bit block ids NOT supported -> streams need extended ids"
        detail += f"; extended ids enabled={sc['extended_ids_enabled']}"
        rep.add("stream channel 0", gev.INFO, detail, cam)
        r["register_errors"] = errors

        # --- GenICam XML ------------------------------------------------------------------------
        if not args.no_xml:
            t0 = time.monotonic()
            x = gev.fetch_genicam_xml(client)
            r["xml"] = {"url": x["url"], "file_name": x["file_name"], "error": x["error"]}
            if x["xml"] is None:
                rep.add("GenICam XML", gev.SKIP if "scheme" in x["error"] else gev.FAIL, x["error"], cam)
            else:
                try:
                    feats = gev.xml_feature_report(x["xml"])
                except gev.ET.ParseError as e:
                    feats = None
                    rep.add("GenICam XML", gev.FAIL, f"downloaded {len(x['xml'])} B but it does not parse: {e}", cam)
                if feats is not None:
                    r["xml"].update(bytes=len(x["xml"]), features=feats)
                    rep.add("GenICam XML", gev.PASS, f"{len(x['xml'])} B in {time.monotonic() - t0:.1f} s, "
                            f"{feats['node_count']} nodes, url {x['url']}", cam)
                    present = feats["present"]
                    for group in ("ptp_sfnc", "ptp_deprecated", "ptp_vendor", "timestamp", "action", "transport_version",
                                  "compression", "sync_free_run"):
                        if present.get(group):
                            rep.add(f"XML features: {group}", gev.INFO, ", ".join(present[group]), cam)
                    for e_name in ("TriggerSource", "GevStreamingMode", "DeviceStreamProtocol", "PixelFormat"):
                        if e_name in feats["enum_entries"]:
                            rep.add(f"XML enum {e_name}", gev.INFO, ", ".join(feats["enum_entries"][e_name]), cam)
                if args.save_xml:
                    os.makedirs(args.save_xml, exist_ok=True)
                    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in
                                   f"{dev.get('manufacturer', '')}_{dev.get('model', '')}_{dev.get('serial', '')}_{ip}")
                    path = os.path.join(args.save_xml, f"{safe}.xml")
                    with open(path, "wb") as f:
                        f.write(x["xml"])
                    r["xml"]["saved_to"] = path
                    print(f"  saved XML to {path}")

        # --- sync readiness verdict -------------------------------------------------------------
        trig = (r.get("xml", {}).get("features") or {}).get("enum_entries", {}).get("TriggerSource", [])
        has_action_trigger = any(t in ("Action0", "Action1") for t in trig)
        r["sync_readiness"] = {"ptp": ptp["supported"], "scheduled_action": act["scheduled_action"],
                               "action": act["action"], "action_trigger_source_in_xml": has_action_trigger if trig else None}
        missing = [k for k in ("ptp", "scheduled_action", "action") if not r["sync_readiness"][k]]
        if trig and not has_action_trigger:
            missing.append("TriggerSource Action0/Action1")
        if missing:
            rep.add("PTP + scheduled-action sync readiness", gev.WARN, f"missing: {', '.join(missing)}", cam)
        else:
            rep.add("PTP + scheduled-action sync readiness", gev.INFO, "bootstrap prerequisites present (PTP, action, "
                    "scheduled action)" + ("" if trig else "; TriggerSource not checked (no XML)"), cam)

        if args.enable_ptp:
            r["enable_ptp"] = enable_ptp(client, ptp["supported"], args.ptp_wait, rep, cam)
    except gev.GvcpError as e:
        rep.add("probe", gev.FAIL, str(e), cam)
    finally:
        client.close()
    return r


def enable_ptp(client: gev.GvcpClient, supported: bool, wait_s: gev.Number, rep: gev.Reporter, cam: str) -> dict[str, Any]:
    out: dict[str, Any] = {"timeline": []}
    if not supported:
        rep.add("enable PTP", gev.SKIP, "camera does not advertise IEEE 1588", cam)
        return out
    try:
        client.take_control()
        cfg = client.read_reg(gev.REG_GVCP_CONFIGURATION)
        client.write_reg(gev.REG_GVCP_CONFIGURATION, cfg | gev.CFG_IEEE1588_ENABLE)
        now_cfg = client.read_reg(gev.REG_GVCP_CONFIGURATION)
        if not now_cfg & gev.CFG_IEEE1588_ENABLE:
            rep.add("enable PTP", gev.FAIL, f"wrote the enable bit but configuration reads 0x{now_cfg:08X}", cam)
            return out
        t0 = time.monotonic()
        last = None
        while time.monotonic() - t0 < wait_s:
            st = client.read_reg(gev.REG_IEEE1588_STATUS) & 0xF
            name = gev.PTP_STATES.get(st, f"state {st}")
            if name != last:
                out["timeline"].append({"t_s": round(time.monotonic() - t0, 2), "state": name})
                print(f"    t={time.monotonic() - t0:5.1f}s PTP state {name}")
                last = name
            time.sleep(0.5)
        out["final_state"] = last
        settled = last in ("Master", "Slave")
        rep.add("enable PTP", gev.PASS if settled else gev.WARN,
                f"enabled; state after {wait_s:.0f} s: {last}" + ("" if settled else
                " (not Master/Slave yet - lock can take tens of seconds; run gev_ptp_sync_test.py for all cameras)"), cam)
    except gev.GvcpError as e:
        rep.add("enable PTP", gev.FAIL, str(e), cam)
    finally:
        client.release_control()
    return out


def print_table(cams: list[dict[str, Any]]) -> None:
    cols = [("IP", 15), ("MAC", 17), ("Vendor / model", 28), ("GEV", 4), ("1588", 4), ("PTP en/state", 16),
            ("Sched", 5), ("Act", 4), ("Resend", 6), ("Tick Hz", 11), ("SCPS", 5), ("EI", 3), ("Act1 trig", 9)]
    print("\n" + " ".join(f"{name:<{w}}" for name, w in cols))
    print(" ".join("-" * w for _, w in cols))
    for c in cams:
        d = c.get("discovery", {})
        capset = set(c.get("capability", {}).get("set", []))
        ptp = c.get("ptp", {})
        ptp_s = "-" if not ptp.get("supported") else f"{'on' if ptp.get('enabled') else 'off'}/{ptp.get('state')}"
        sc = c.get("stream_channel_0", {})
        trig = (c.get("xml", {}).get("features") or {}).get("enum_entries", {}).get("TriggerSource")
        act1 = "?" if trig is None else ("Action1" if "Action1" in trig else "Action0" if "Action0" in trig else "no")
        vals = [c.get("ip", ""), d.get("mac", ""), f"{d.get('manufacturer', '')} {d.get('model', '')}"[:28],
                c.get("gev_version", "?"), "yes" if "ieee1588" in capset else "no", ptp_s,
                "yes" if "scheduled_action" in capset else "no", "yes" if "action" in capset else "no",
                "yes" if "packet_resend" in capset else "no", str(c.get("tick_frequency_hz")), str(sc.get("packet_size")),
                {True: "on", False: "off", None: "?"}[sc.get("extended_ids_enabled")], act1]
        print(" ".join(f"{str(v):<{w}}" for v, (_, w) in zip(vals, cols)))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", action="append", default=[], help="camera IP (repeatable); default: discover all")
    ap.add_argument("--iface", default="", help="local IPv4 address of the NIC facing the cameras (default: all)")
    ap.add_argument("--timeout", type=float, default=1.5, help="discovery wait in seconds (default 1.5)")
    ap.add_argument("--gvcp-timeout", type=float, default=0.5, help="per-command GVCP timeout in seconds")
    ap.add_argument("--include-loopback", action="store_true", help="also discover on 127.0.0.0/8 (emulators)")
    ap.add_argument("--no-xml", action="store_true", help="skip downloading the GenICam XML")
    ap.add_argument("--save-xml", metavar="DIR", help="save each camera's GenICam XML into DIR")
    ap.add_argument("--json", metavar="PATH", help="write all results to this JSON file")
    ap.add_argument("--enable-ptp", action="store_true", help="CHANGES STATE: set the IEEE 1588 enable bit")
    ap.add_argument("--ptp-wait", type=float, default=15.0, help="seconds to watch the PTP state after enabling")
    ap.add_argument("--selftest", action="store_true", help="run offline encode/decode checks and exit")
    args = ap.parse_args(argv)
    if args.selftest:
        return gev.selftest_main(title="gev_probe selftest")

    print("== host")
    host = gev.host_info()
    print("  " + ", ".join(f"{k}={v}" for k, v in host.items()))
    interfaces = gev.list_ipv4_interfaces(include_loopback=args.include_loopback)
    for itf in interfaces:
        print(f"  interface {itf.name}: {itf.ip}/{itf.prefix_len} (broadcast {itf.broadcast})")
    rep = gev.Reporter("gev_probe")
    print("== discovery" + (f" (unicast to {', '.join(args.ip)})" if args.ip else " (broadcast on all interfaces)"))
    devices = gev.discover_devices(timeout=args.timeout, targets=args.ip or None,
                                   iface_ips=[args.iface] if args.iface else None,
                                   include_loopback=args.include_loopback or any(i.startswith("127.") for i in args.ip))
    for d in devices:
        print(f"  found {d['control_ip']}  {d['mac']}  {d['manufacturer']} {d['model']}  serial={d['serial']}  "
              f"GEV {d['gev_version']}  user_name={d['user_name']!r}")
    answered = {d["control_ip"] for d in devices}
    for ip in args.ip:
        if ip not in answered:
            rep.add("discovery", gev.WARN, "no DISCOVERY_ACK; trying register access anyway", ip)
            devices.append({"control_ip": ip, "ip": ip, "discovery_answered": False})
    if not devices:
        rep.add("discovery", gev.FAIL, "no GigE Vision camera answered. Check cabling/PoE, that the host NIC has an "
                "address on the cameras' subnet (link-local 169.254.x.x is common), firewall rules for UDP 3956, "
                "and try --iface <host NIC IP>")
        rep.print_summary()
        return 2
    rep.add("discovery", gev.PASS, f"{len(answered)} camera(s) answered")
    cams = []
    for d in devices:
        print(f"\n== camera {d['control_ip']}")
        cams.append(probe_camera(d, args, rep))
    print_table(cams)
    rep.print_summary()
    if args.json:
        gev.write_json(args.json, {"tool": "gev_probe", "host": host,
                                   "interfaces": [i.as_dict() for i in interfaces], "cameras": cams,
                                   "checks": rep.as_list()})
    return rep.exit_code()


if __name__ == "__main__":
    sys.exit(main())
