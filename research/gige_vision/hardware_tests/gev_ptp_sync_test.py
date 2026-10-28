#!/usr/bin/env python3
"""
gev_ptp_sync_test.py - multi-camera IEEE 1588 (PTP) clock sync + ACTION_CMD test over raw GVCP.

Standard library only (Python >= 3.9); keep gev_common.py next to this file. Uses only GigE Vision
BOOTSTRAP registers, so it needs no GenICam XML evaluation and no vendor SDK. The GenICam feature
path (PtpEnable / GevIEEE1588 / PtpMode, PtpDataSetLatch, PtpOffsetFromMaster, TriggerSource=Action1)
is exercised by viva_sync_capture_test.py instead.

Checks, each reported as PASS / FAIL / SKIP (SKIP = the camera does not support/implement it):
  1. cameras reachable, control privilege can be taken
  2. IEEE 1588 capability (GVCP capability register 0x0934 bit 0x00080000)
  3. PTP enabled - with --enable-ptp the enable bit (0x0954 bit 0x00080000) is set
  4. PTP roles settle within --ptp-timeout: exactly one Master and the rest Slave
     (or all Slave with --external-master, e.g. a ptp4l grandmaster)
  5. timestamp latch (write 2 to 0x0944, read 0x0948/0x094C) works and advances at the tick rate
  6. inter-camera clock offset and drift over --duration: every camera's clock is latched with the
     host clock read just before and after, so offsets are known to +-(round-trip/2). PTP-synced
     clocks agree to well under a millisecond and drift ~0 ppm against each other; free-running
     clocks typically differ by seconds and drift by 1-50 ppm.
  7. ACTION_CMD (UDP 3956, broadcast or unicast): action keys are written to the bootstrap action
     registers (0x090C device key, 0x9800/0x9804 group key/mask; undone at exit), then
       a. wrong device key       -> no camera may acknowledge
       b. immediate action       -> ACTION_ACK SUCCESS from every camera
       c. scheduled action (+delay, in camera-0 ticks) -> SUCCESS from every camera
       d. scheduled action 1 s in the past -> ACTION_LATE (0x8016) or SUCCESS (vendor-specific)
     An ACK only means the command was accepted. To make it trigger exposures the cameras also need
     TriggerSelector=FrameStart, TriggerMode=On, TriggerSource=Action1 (Action0 on some vendors) -
     viva_sync_capture_test.py --mode scheduled-action does that and measures exposure alignment.

State changes: takes control of each camera for the duration of the test; with --enable-ptp sets the
PTP enable bit (left ON at exit unless --restore-ptp); writes action keys (restored at exit).

Examples:
  python gev_ptp_sync_test.py --enable-ptp                         # all cameras found
  python gev_ptp_sync_test.py --ip 169.254.1.10 --ip 169.254.1.11 --enable-ptp --duration 60 --json ptp.json
  python gev_ptp_sync_test.py --no-program-keys --device-key 0x42 --group-key 1 --group-mask 1
  python gev_ptp_sync_test.py --selftest

Exit code: 0 = no FAIL (SKIPs allowed; --strict turns SKIP into failure), 1 = a check failed,
2 = no camera / bad arguments.

DRAFT: verified only against software-emulated cameras (Aravis arv-fake-gv-camera-0.8, viva-genicam
FakeGigeCamera), neither of which implements PTP. See README.md.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional

try:
    from . import gev_common as gev  # imported as part of a package (e.g. hardware_tests.<script>)
except ImportError:  # run directly: python gev_ptp_sync_test.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gev_common as gev  # type: ignore[no-redef]

STATUS_NOT_IMPLEMENTED = 0x8001
STATUS_INVALID_ADDRESS = 0x8003


@dataclass
class Cam:
    ip: str
    label: str
    client: gev.GvcpClient
    version: str = "?"
    cap: int = 0
    tick_hz: int = 0
    controlled: bool = False
    ptp_supported: bool = False
    ptp_enabled: bool = False
    ptp_state: str = ""
    latch_ok: bool = False
    action_keys_programmed: bool = False


def ptp_state(c: Cam) -> str:
    v = c.client.read_reg(gev.REG_IEEE1588_STATUS) & 0xF
    return gev.PTP_STATES.get(v, f"state{v}")


# --------------------------------------------------------------------------------------------- steps
def step_ptp(cams: list[Cam], args: argparse.Namespace, rep: gev.Reporter, out: dict[str, Any]) -> None:
    for c in cams:
        c.ptp_supported = bool(c.cap & gev.CAP["ieee1588"])
        rep.add("IEEE 1588 capability", gev.PASS if c.ptp_supported else gev.SKIP,
                "capability bit set" if c.ptp_supported else "capability bit 0x00080000 clear - camera does not "
                "advertise PTP (if its vendor tool shows Ptp*/GevIEEE1588 features, try viva_sync_capture_test.py)",
                c.label)
    ptp_cams = [c for c in cams if c.ptp_supported]
    if not ptp_cams:
        rep.add("PTP roles", gev.SKIP, "no camera supports IEEE 1588")
        return
    for c in ptp_cams:
        try:
            cfg = c.client.read_reg(gev.REG_GVCP_CONFIGURATION)
            c.ptp_enabled = bool(cfg & gev.CFG_IEEE1588_ENABLE)
            if c.ptp_enabled:
                rep.add("PTP enabled", gev.PASS, "IEEE 1588 enable bit already set", c.label)
            elif not args.enable_ptp:
                rep.add("PTP enabled", gev.SKIP, "PTP is disabled; rerun with --enable-ptp", c.label)
            elif not c.controlled:
                rep.add("PTP enabled", gev.SKIP, "cannot enable: no control privilege", c.label)
            else:
                c.client.write_reg(gev.REG_GVCP_CONFIGURATION, cfg | gev.CFG_IEEE1588_ENABLE, restore=args.restore_ptp)
                c.ptp_enabled = bool(c.client.read_reg(gev.REG_GVCP_CONFIGURATION) & gev.CFG_IEEE1588_ENABLE)
                rep.add("PTP enabled", gev.PASS if c.ptp_enabled else gev.FAIL,
                        "enable bit set via bootstrap register 0x0954" if c.ptp_enabled else
                        "wrote the enable bit but it reads back clear", c.label)
        except gev.GvcpError as e:
            rep.add("PTP enabled", gev.FAIL, str(e), c.label)
    on = [c for c in ptp_cams if c.ptp_enabled]
    if not on:
        rep.add("PTP roles", gev.SKIP, "no camera has PTP enabled")
        return
    print(f"  waiting up to {args.ptp_timeout:.0f} s for PTP roles (one Master + Slaves"
          f"{', or all Slave' if args.external_master else ''}) ...")
    t0 = time.monotonic()
    timeline: list[dict[str, Any]] = []
    last: dict[str, str] = {}
    stable_since: Optional[float] = None
    settled = False
    while True:
        now = time.monotonic() - t0
        states = {}
        for c in on:
            try:
                states[c.ip] = ptp_state(c)
            except gev.GvcpError as e:
                states[c.ip] = f"error({gev.gev_status_name(e.status)})"
        if states != last:
            timeline.append({"t_s": round(now, 2), "states": dict(states)})
            print(f"    t={now:5.1f}s {states}")
            last = states
        masters = [ip for ip, s in states.items() if s == "Master"]
        ok = all(s in ("Master", "Slave") for s in states.values()) and (
            len(masters) == 1 or (args.external_master and not masters))
        if ok:
            stable_since = now if stable_since is None else stable_since
            if now - stable_since >= args.settle_s:
                settled = True
                break
        else:
            stable_since = None
        if now > args.ptp_timeout:
            break
        time.sleep(0.5)
    for c in on:
        c.ptp_state = last.get(c.ip, "")
    out["ptp_timeline"] = timeline
    out["ptp_final_states"] = last
    if settled:
        rep.add("PTP roles", gev.PASS, f"settled after {stable_since:.1f} s: master={masters or 'external'}, "
                f"slaves={[ip for ip, s in last.items() if s == 'Slave']}")
    else:
        hint = ("two or more Masters: the cameras cannot see each other's PTP multicast (224.0.1.129, UDP 319/320) - "
                "disable IGMP snooping on the switch, use one switch/subnet, then power-cycle the cameras"
                if len([s for s in last.values() if s == "Master"]) > 1 else
                "check that every camera is on the same switch/subnet; Listening/Uncalibrated can take 30-60 s")
        rep.add("PTP roles", gev.FAIL, f"not settled within {args.ptp_timeout:.0f} s: {last}. {hint}")


def step_latch(cams: list[Cam], rep: gev.Reporter) -> None:
    for c in cams:
        if not c.controlled:
            rep.add("timestamp latch", gev.SKIP, "no control privilege", c.label)
            continue
        try:
            a0, a1, v1 = c.client.latch_timestamp()
            time.sleep(0.1)
            b0, b1, v2 = c.client.latch_timestamp()
        except gev.GvcpError as e:
            st = gev.SKIP if e.status in (STATUS_NOT_IMPLEMENTED, STATUS_INVALID_ADDRESS) else gev.FAIL
            rep.add("timestamp latch", st, str(e), c.label)
            continue
        if v1 == 0 and v2 == 0:
            rep.add("timestamp latch", gev.SKIP, "latched value is always 0 - timestamp latch not implemented", c.label)
            continue
        if v2 <= v1:
            rep.add("timestamp latch", gev.FAIL, f"timestamp did not advance ({v1} -> {v2})", c.label)
            continue
        host_ns = (b0 + b1) / 2 - (a0 + a1) / 2
        rate = (v2 - v1) / (host_ns / 1e9)
        detail = f"advances at {rate / 1e6:.3f} MHz vs tick-frequency register {c.tick_hz / 1e6:.3f} MHz; " \
                 f"round trip {(a1 - a0) / 1e3:.0f} us"
        if c.tick_hz and abs(rate / c.tick_hz - 1) > 0.05:
            rep.add("timestamp latch", gev.WARN, detail + " (tick frequency register disagrees with the clock rate)",
                    c.label)
        else:
            rep.add("timestamp latch", gev.PASS, detail, c.label)
        c.latch_ok = True


def step_clock(cams: list[Cam], args: argparse.Namespace, rep: gev.Reporter, out: dict[str, Any]) -> None:
    lc = [c for c in cams if c.latch_ok]
    if not lc:
        rep.add("clock offset / drift", gev.SKIP, "no camera with a working timestamp latch")
        return
    print(f"  latching all clocks every {args.interval:.2f} s for {args.duration:.0f} s ...")
    samples: dict[str, list[tuple[float, int, int]]] = {c.ip: [] for c in lc}  # (host_s, cam_minus_host_ns, rtt_ns)
    t_end = time.monotonic() + args.duration
    while time.monotonic() < t_end:
        for c in lc:
            try:
                t0, t1, ticks = c.client.latch_timestamp()
            except gev.GvcpError:
                continue
            mid = (t0 + t1) // 2
            samples[c.ip].append((mid / 1e9, gev.ticks_to_ns(ticks, c.tick_hz) - mid, t1 - t0))
        time.sleep(args.interval)
    out["clock_samples"] = {ip: [list(s) for s in v] for ip, v in samples.items()}
    per_cam: dict[str, Any] = {}
    for c in lc:
        s = samples[c.ip]
        if len(s) < 3:
            continue
        slope, _ = gev.linear_fit([x[0] for x in s], [x[1] for x in s])
        rtts = [x[2] / 1e3 for x in s]
        per_cam[c.ip] = {"drift_vs_host_ppm": slope / 1e3, "rtt_us": gev.describe(rtts), "n": len(s)}
        rep.add("clock vs host", gev.INFO, f"drift {slope / 1e3:+.3f} ppm against the (unsynchronised) host clock; "
                f"latch round trip median {gev.percentile(rtts, 50):.0f} us", c.label)
    out["per_camera"] = per_cam
    if len(lc) < 2:
        rep.add("inter-camera clock offset", gev.SKIP, "needs two cameras with a working timestamp latch")
        return
    ref = lc[0]
    pairs: dict[str, Any] = {}
    for c in lc[1:]:
        n = min(len(samples[c.ip]), len(samples[ref.ip]))
        rows = [(samples[c.ip][i], samples[ref.ip][i]) for i in range(n)]
        if n < 3:
            rep.add("inter-camera clock offset", gev.SKIP, "too few samples", f"{c.ip} vs {ref.ip}")
            continue
        # keep the rounds whose round trips were fastest: their brackets are tightest
        rtt_sum = sorted(a[2] + b[2] for a, b in rows)
        cut = rtt_sum[len(rtt_sum) // 2]
        best = [(a, b) for a, b in rows if a[2] + b[2] <= cut]
        diffs = [a[1] - b[1] for a, b in best]
        times = [a[0] for a, b in best]
        med = gev.percentile(diffs, 50)
        bound = gev.percentile([(a[2] + b[2]) / 2 for a, b in best], 50)
        slope, _ = gev.linear_fit(times, diffs)
        drift_ppm = slope / 1e3
        spread = gev.percentile([abs(d - med) for d in diffs], 95)
        pair = f"{c.ip} vs {ref.ip}"
        pairs[pair] = {"median_offset_ns": med, "resolution_ns": bound, "p95_abs_dev_ns": spread,
                       "drift_ppm": drift_ppm, "rounds_used": len(best)}
        detail = (f"median offset {med / 1e3:+.1f} us (resolution +-{bound / 1e3:.0f} us from latch round trips), "
                  f"drift {drift_ppm:+.3f} ppm, p95 |dev| {spread / 1e3:.1f} us over {len(best)} rounds")
        both_ptp = c.ptp_state in ("Master", "Slave") and ref.ptp_state in ("Master", "Slave")
        ok = abs(med) - bound <= args.max_offset_us * 1e3 and abs(drift_ppm) <= args.max_drift_ppm
        if not both_ptp:
            rep.add("inter-camera clock offset", gev.INFO, detail + " - PTP not active on both, agreement not expected",
                    pair)
        else:
            rep.add("inter-camera clock offset", gev.PASS if ok else gev.FAIL, detail +
                    f" (limits {args.max_offset_us:.0f} us, {args.max_drift_ppm} ppm)", pair)
    out["pairs"] = pairs
    if any(c.ptp_state in ("Master", "Slave") for c in lc):
        print("  note: the latch method resolves offsets only to about half a GVCP round trip (tens to hundreds of us);"
              " use viva_sync_capture_test.py --mode scheduled-action for microsecond-level exposure alignment")


def _send(dest_mode: str, cams: list[Cam], bind_ip: str, broadcast: str, args: argparse.Namespace, device_key: int,
          action_time: Optional[int]) -> dict[str, int]:
    if dest_mode == "unicast":
        acks: dict[str, int] = {}
        for c in cams:
            acks.update(gev.send_action_cmd(c.ip, device_key, args.group_key, args.group_mask, action_time,
                                            bind_ip=bind_ip, wait_s=args.ack_wait))
        return acks
    return gev.send_action_cmd(broadcast, device_key, args.group_key, args.group_mask, action_time,
                               bind_ip=bind_ip, wait_s=args.ack_wait)


def step_action(cams: list[Cam], args: argparse.Namespace, rep: gev.Reporter, out: dict[str, Any]) -> None:
    if args.no_action:
        rep.add("ACTION_CMD", gev.SKIP, "--no-action")
        return
    for c in cams:
        if not args.no_program_keys:
            if not c.cap & gev.CAP["action"]:
                rep.add("program action keys", gev.SKIP, "ACTION_CMD not supported (capability bit 0x40 clear)", c.label)
                continue
            if not c.controlled:
                rep.add("program action keys", gev.SKIP, "no control privilege", c.label)
                continue
            try:
                n_sig, _ = c.client.read_reg_opt(gev.REG_N_ACTION_SIGNALS)
                if n_sig is not None and n_sig <= args.action_index:
                    rep.add("program action keys", gev.SKIP, f"camera has {n_sig} action signal(s); "
                            f"--action-index {args.action_index} does not exist", c.label)
                    continue
                c.client.write_reg(gev.REG_ACTION_DEVICE_KEY, args.device_key, restore=True)
                c.client.write_reg(gev.reg_action_group_key(args.action_index), args.group_key, restore=True)
                c.client.write_reg(gev.reg_action_group_mask(args.action_index), args.group_mask, restore=True)
                c.action_keys_programmed = True
                rep.add("program action keys", gev.PASS, f"device key 0x{args.device_key:08X}, group key "
                        f"0x{args.group_key:08X}, mask 0x{args.group_mask:08X} at action index {args.action_index}",
                        c.label)
            except gev.GvcpError as e:
                rep.add("program action keys", gev.FAIL, str(e), c.label)
        else:
            c.action_keys_programmed = True  # configured elsewhere (vendor tool, viva script, emulator defaults)
    expected = [c for c in cams if c.action_keys_programmed]
    if not expected:
        rep.add("ACTION_CMD", gev.SKIP, "no camera supports / accepted action keys")
        return
    bind_ip = cams[0].client.local_ip
    if args.action_dest in ("auto", "broadcast"):
        if bind_ip.startswith("127."):
            dest_mode, broadcast = "unicast", ""
        elif args.action_dest == "broadcast":
            dest_mode, broadcast = "broadcast", "255.255.255.255"
        else:
            dest_mode, broadcast = "broadcast", gev.broadcast_for(bind_ip, cams[0].ip)
    elif args.action_dest == "unicast":
        dest_mode, broadcast = "unicast", ""
    else:
        dest_mode, broadcast = "broadcast", args.action_dest
    where = "unicast to each camera" if dest_mode == "unicast" else f"to {broadcast}"
    print(f"  sending ACTION_CMDs {where} from {bind_ip}")
    res: dict[str, Any] = {"destination": where}

    def judge(name: str, acks: dict[str, int], want_ok: bool, needs_cap: str = "action") -> None:
        res[name] = {ip: gev.gev_status_name(s) for ip, s in acks.items()}
        for c in expected:
            st = acks.get(c.ip)
            if st is None:
                capable = bool(c.cap & gev.CAP[needs_cap])
                rep.add(f"ACTION_CMD {name}", gev.FAIL if capable else gev.SKIP,
                        "no ACTION_ACK" + ("" if capable else f" (camera does not advertise {needs_cap})"), c.label)
            elif st == 0:
                rep.add(f"ACTION_CMD {name}", gev.PASS if want_ok else gev.INFO, "ACK SUCCESS", c.label)
            elif st == STATUS_NOT_IMPLEMENTED and not c.cap & gev.CAP[needs_cap]:
                rep.add(f"ACTION_CMD {name}", gev.SKIP, "NOT_IMPLEMENTED (capability not advertised)", c.label)
            else:
                rep.add(f"ACTION_CMD {name}", gev.FAIL if want_ok else gev.INFO, f"ACK {gev.gev_status_name(st)}",
                        c.label)

    # a. wrong key must not be acknowledged
    wrong = _send(dest_mode, expected, bind_ip, broadcast, args, args.device_key ^ 0xFFFFFFFF, None)
    res["wrong_key"] = {ip: gev.gev_status_name(s) for ip, s in wrong.items()}
    rep.add("ACTION_CMD wrong device key ignored", gev.PASS if not wrong else gev.FAIL,
            "no camera acknowledged" if not wrong else f"acknowledged by {sorted(wrong)} - key filtering broken")
    # b. immediate
    t0 = time.perf_counter()
    imm = _send(dest_mode, expected, bind_ip, broadcast, args, args.device_key, None)
    judge("immediate", imm, True)
    res["immediate_wall_s"] = time.perf_counter() - t0
    # c/d. scheduled - time base: camera 0's latched clock
    base = next((c for c in expected if c.latch_ok), None)
    if base is None:
        rep.add("ACTION_CMD scheduled", gev.SKIP, "no camera clock to schedule against (timestamp latch unavailable)")
    else:
        _, _, now_ticks = base.client.latch_timestamp()
        tick = base.tick_hz or 1_000_000_000
        future = now_ticks + args.delay_ms * tick // 1000
        if not all(c.ptp_state in ("Master", "Slave") for c in expected):
            print("  note: PTP is not active on every camera, so the scheduled time (camera "
                  f"{base.ip} ticks) means little to the others")
        sched = _send(dest_mode, expected, bind_ip, broadcast, args, args.device_key, future)
        judge(f"scheduled (+{args.delay_ms} ms)", sched, True, "scheduled_action")
        res["scheduled_time_ticks"] = future
        time.sleep(args.delay_ms / 1000 + 0.05)
        _, _, now2 = base.client.latch_timestamp()
        past = max(1, now2 - tick)
        late = _send(dest_mode, expected, bind_ip, broadcast, args, args.device_key, past)
        res["late_time_ticks"] = past
        res["late"] = {ip: gev.gev_status_name(s) for ip, s in late.items()}
        for c in expected:
            st = late.get(c.ip)
            if st == gev.STATUS_ACTION_LATE:
                rep.add("ACTION_CMD scheduled in the past", gev.PASS, "ACK ACTION_LATE (rejected late action)", c.label)
            elif st == 0:
                rep.add("ACTION_CMD scheduled in the past", gev.INFO, "ACK SUCCESS - camera executes late actions "
                        "immediately (vendor behaviour, e.g. Basler)", c.label)
            elif st is None:
                rep.add("ACTION_CMD scheduled in the past", gev.INFO, "no ACK", c.label)
            else:
                rep.add("ACTION_CMD scheduled in the past", gev.INFO, f"ACK {gev.gev_status_name(st)}", c.label)
    out["action"] = res


# --------------------------------------------------------------------------------------------- main
def selftest_extra(rep: gev.Reporter) -> None:
    import tempfile  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "actions.pcap")
        pk = [gev.build_action_cmd(0x12345678, 1, 0xFFFFFFFF, None, 1), gev.build_action_cmd(0x12345678, 1, 1, 5, 2)]
        gev.write_pcap(path, [("192.168.1.10", 50000, "192.168.1.255", gev.GVCP_PORT, p) for p in pk])
        got = [gev.extract_udp(lt, fr) for _, lt, fr, _ in gev.iter_capture(path)]
        rep.check("ACTION_CMD pcap round trip", [g.payload for g in got if g] == pk)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", action="append", default=[], help="camera IP (repeatable); default: discover all")
    ap.add_argument("--iface", default="", help="local IPv4 address of the NIC facing the cameras")
    ap.add_argument("--include-loopback", action="store_true", help="also discover on loopback (emulators)")
    ap.add_argument("--enable-ptp", action="store_true", help="set the IEEE 1588 enable bit (bootstrap 0x0954)")
    ap.add_argument("--restore-ptp", action="store_true", help="clear the PTP enable bit again at exit")
    ap.add_argument("--external-master", action="store_true", help="accept all cameras Slave (host/switch grandmaster)")
    ap.add_argument("--ptp-timeout", type=float, default=60.0, help="seconds to wait for Master/Slave (default 60)")
    ap.add_argument("--settle-s", type=float, default=2.0, help="roles must hold this long (default 2 s)")
    ap.add_argument("--duration", type=float, default=20.0, help="clock offset/drift measurement time (default 20 s)")
    ap.add_argument("--interval", type=float, default=0.25, help="latch interval in seconds (default 0.25)")
    ap.add_argument("--max-offset-us", type=float, default=1000.0,
                    help="inter-camera offset limit after subtracting latch resolution (default 1000 us)")
    ap.add_argument("--max-drift-ppm", type=float, default=2.0, help="inter-camera drift limit (default 2 ppm)")
    ap.add_argument("--no-action", action="store_true", help="skip the ACTION_CMD tests")
    ap.add_argument("--no-program-keys", action="store_true",
                    help="do not write action keys; the cameras were configured elsewhere")
    ap.add_argument("--device-key", type=gev.int_arg, default=0x12345678)
    ap.add_argument("--group-key", type=gev.int_arg, default=0x1)
    ap.add_argument("--group-mask", type=gev.int_arg, default=0xFFFFFFFF)
    ap.add_argument("--action-index", type=int, default=0, help="bootstrap action group index (0 = 0x9800/0x9804)")
    ap.add_argument("--action-dest", default="auto",
                    help="auto (subnet broadcast of the camera NIC), broadcast (255.255.255.255), unicast, or an IP")
    ap.add_argument("--delay-ms", type=int, default=500, help="scheduled action lead time (default 500 ms)")
    ap.add_argument("--ack-wait", type=float, default=0.3, help="seconds to collect ACTION_ACKs")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any check was skipped")
    ap.add_argument("--json", metavar="PATH", help="write all results (incl. raw clock samples) to JSON")
    ap.add_argument("--selftest", action="store_true", help="run offline encode/decode checks and exit")
    args = ap.parse_args(argv)
    if args.selftest:
        return gev.selftest_main(selftest_extra, title="gev_ptp_sync_test selftest")

    rep = gev.Reporter("gev_ptp_sync_test")
    out: dict[str, Any] = {"tool": "gev_ptp_sync_test", "host": gev.host_info(), "args": vars(args)}
    print("== cameras")
    devices = gev.discover_devices(targets=args.ip or None, iface_ips=[args.iface] if args.iface else None,
                                   include_loopback=args.include_loopback or any(i.startswith("127.") for i in args.ip))
    ips = [d["control_ip"] for d in devices]
    labels = {d["control_ip"]: f"{d['control_ip']} {d['model']}".strip() for d in devices}
    for ip in args.ip:
        if ip not in ips:
            ips.append(ip)
            labels[ip] = ip
            rep.add("discovery", gev.WARN, "no DISCOVERY_ACK; trying register access anyway", ip)
    if not ips:
        rep.add("discovery", gev.FAIL, "no camera found (see gev_probe.py for network troubleshooting)")
        rep.print_summary()
        return 2
    cams: list[Cam] = []
    try:
        for ip in ips:
            try:
                client = gev.GvcpClient(ip, local_ip=args.iface)
                c = Cam(ip=ip, label=labels[ip], client=client)
                ver = client.read_reg(gev.REG_VERSION)
                c.version = f"{ver >> 16}.{ver & 0xFFFF}"
                c.cap = client.read_reg(gev.REG_GVCP_CAPABILITY)
                c.tick_hz = client.tick_frequency()
                cams.append(c)
                rep.add("reachable", gev.PASS, f"GEV {c.version}, capabilities "
                        f"{', '.join(gev.bits_set(c.cap, gev.CAPABILITY_BITS)) or 'none'}, tick {c.tick_hz} Hz", c.label)
            except (gev.GvcpError, OSError) as e:
                rep.add("reachable", gev.FAIL, str(e), labels[ip])
        for c in cams:
            try:
                c.client.take_control()
                c.controlled = True
            except gev.GvcpError as e:
                rep.add("take control", gev.FAIL, str(e), c.label)
        out["cameras"] = [{"ip": c.ip, "label": c.label, "gev_version": c.version, "capability": f"0x{c.cap:08X}",
                           "tick_hz": c.tick_hz} for c in cams]
        print("== PTP")
        step_ptp(cams, args, rep, out)
        print("== timestamp latch")
        step_latch(cams, rep)
        print("== clock offset / drift")
        step_clock(cams, args, rep, out)
        print("== action commands")
        step_action(cams, args, rep, out)
    finally:
        for c in cams:
            lost = c.client.control_lost
            for p in c.client.close():
                rep.add("restore registers", gev.WARN, p, c.label)
            if lost:
                rep.add("camera control", gev.FAIL, "control was lost during the test (heartbeat timeout: network "
                        "glitch, another application, or the host was too busy)", c.label)

    ptp_ok = [r for r in rep.results if r.name == "PTP roles" and r.status == gev.PASS]
    off_ok = [r for r in rep.results if r.name == "inter-camera clock offset"]
    sched = [r for r in rep.results if r.name.startswith("ACTION_CMD scheduled (")]
    print("\n== verdict")
    print(f"  PTP clock sync: {'VERIFIED' if ptp_ok and off_ok and all(r.status == gev.PASS for r in off_ok) else 'NOT VERIFIED'}"
          f" ({len(cams)} camera(s))")
    print(f"  scheduled ACTION_CMD accepted by all: "
          f"{'YES' if sched and all(r.status == gev.PASS for r in sched) else 'NO / not tested'}")
    rep.print_summary()
    out["checks"] = rep.as_list()
    if args.json:
        gev.write_json(args.json, out)
    return rep.exit_code(strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
