#!/usr/bin/env python3
"""
gentl_ptp_sync_test.py - END-TO-END multi-camera PTP synchronisation test
(GenICam feature level, via Harvesters + any vendor GenTL producer .cti).

UNTESTED against real hardware at time of writing (no PTP cameras were
available); it is a draft to run on a machine that has >=2 PTP-capable GigE
Vision cameras.  Requirements:
    pip install harvesters==1.4.3 numpy
    a GigE Vision GenTL producer (.cti) - e.g. from Basler pylon, LUCID Arena,
    Teledyne Spinnaker, Allied Vision Vimba X, MATRIX VISION mvGenTL, Euresys...

What it does
  1. opens every camera found by the producer (or --serial ...),
  2. enables PTP: PtpEnable (SFNC >= 2.x) or GevIEEE1588 (deprecated name),
  3. waits until PTP is settled: exactly one camera Master (or all Slave with
     --external-master), and max |PtpOffsetFromMaster| < --offset-ns for
     --stable-s consecutive seconds (Basler recommends checking the max offset
     in a window because it does not decrease monotonically),
  4. configures TriggerSelector=FrameStart, TriggerMode=On,
     TriggerSource=Action1 (falls back to Action0), ActionDeviceKey/Selector/
     GroupKey/GroupMask,
  5. N times: latches camera-0 timestamp (TimestampLatch/TimestampLatchValue
     or GevTimestampControlLatch/GevTimestampValue), schedules an action at
     latched+delay - via the GenTL *Interface* node map (GenTL SFNC 1.2
     ActionCommand / ActionScheduledTime ...) or, if the producer lacks those,
     via a raw GVCP ACTION_CMD built by gev_ptp_sync_test.py - and fetches one
     frame per camera,
  6. reports per-trigger spread (max-min) of the per-frame device timestamps and
     their offset from the scheduled action time. PASS if p99 spread
     < --max-spread-us.

Mode --mode freerun skips 4-5: it just grabs free-running frames (e.g. after
you enabled a vendor feature such as Basler Synchronous Free Run or LUCID
PTPSync in the vendor viewer) and reports nearest-timestamp pairing between
cameras (post-hoc alignment).
"""
from __future__ import annotations

import argparse
import os
import socket
import statistics
import sys
import time

try:
    from harvesters.core import Harvester
except ImportError:  # pragma: no cover
    sys.exit("pip install harvesters==1.4.3  (and point --cti at a GigE Vision GenTL producer)")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gev_ptp_sync_test as raw  # noqa: E402  (stdlib-only sibling script)


NAMES = {}  # id(ImageAcquirer) -> "model#serial"


# ---------------------------------------------------------------- helpers ---
def node(nm, *names):
    for n in names:
        try:
            nd = getattr(nm, n)
            _ = nd.node  # touch
            return n, nd
        except Exception:
            continue
    return None, None


def setv(nm, value, *names):
    n, nd = node(nm, *names)
    if nd is None:
        return None
    try:
        nd.value = value
        return n
    except Exception as e:
        print("   could not set %s=%r: %s" % (n, value, e))
        return None


def getv(nm, *names, default=None):
    n, nd = node(nm, *names)
    if nd is None:
        return default
    try:
        return nd.value
    except Exception:
        return default


def execute(nm, *names):
    n, nd = node(nm, *names)
    if nd is None:
        return None
    nd.execute()
    return n


def latch_ns(nm):
    if execute(nm, "TimestampLatch", "GevTimestampControlLatch") is None:
        raise RuntimeError("camera has neither TimestampLatch nor GevTimestampControlLatch")
    v = getv(nm, "TimestampLatchValue", "GevTimestampValue")
    f = getv(nm, "GevTimestampTickFrequency", default=1_000_000_000)
    return raw.ticks_to_ns(int(v), int(f)) if f else int(v)


def buffer_ts_ns(buf):
    try:
        return int(buf.timestamp_ns)
    except Exception:
        return raw.ticks_to_ns(int(buf.timestamp), int(buf.timestamp_frequency))


# ------------------------------------------------------------------ steps ---
def enable_ptp(ias, args):
    for ia in ias:
        nm = ia.remote_device.node_map
        n = setv(nm, True, "PtpEnable", "GevIEEE1588")
        print("%s: PTP enable via %s" % (NAMES[id(ia)], n))
        if n is None:
            raise RuntimeError("%s: no PtpEnable / GevIEEE1588 feature" % NAMES[id(ia)])
    t0 = time.monotonic()
    stable_since = None
    while True:
        states, offsets = {}, {}
        for ia in ias:
            nm = ia.remote_device.node_map
            execute(nm, "PtpDataSetLatch", "GevIEEE1588DataSetLatch")
            states[NAMES[id(ia)]] = str(getv(nm, "PtpStatus", "GevIEEE1588StatusLatched", "GevIEEE1588Status"))
            off = getv(nm, "PtpOffsetFromMaster", "GevIEEE1588OffsetFromMaster")
            if off is not None and states[NAMES[id(ia)]] == "Slave":
                offsets[NAMES[id(ia)]] = int(off)
        n_master = sum(1 for s in states.values() if s == "Master")
        roles_ok = all(s in ("Master", "Slave") for s in states.values()) and (
            n_master == 1 or (n_master == 0 and args.external_master))
        max_off = max((abs(o) for o in offsets.values()), default=0)
        el = time.monotonic() - t0
        print("t=%5.1fs states=%s offsets_ns=%s" % (el, states, offsets))
        if roles_ok and max_off < args.offset_ns:
            stable_since = stable_since or time.monotonic()
            if time.monotonic() - stable_since >= args.stable_s:
                print("PTP settled after %.1fs (max |offset| %d ns)" % (el, max_off))
                return
        else:
            stable_since = None
        if el > args.ptp_timeout:
            raise RuntimeError("PTP did not settle in %.0fs" % args.ptp_timeout)
        time.sleep(1)


def configure_action_trigger(ias, args):
    for ia in ias:
        nm = ia.remote_device.node_map
        setv(nm, "FrameStart", "TriggerSelector")
        setv(nm, "On", "TriggerMode")
        src = setv(nm, "Action1", "TriggerSource") and "Action1"
        if not src:
            src = setv(nm, "Action0", "TriggerSource") and "Action0"
        if not src:
            raise RuntimeError("%s: TriggerSource has no Action1/Action0 entry" % NAMES[id(ia)])
        setv(nm, args.device_key, "ActionDeviceKey")
        setv(nm, 1 if src == "Action1" else 0, "ActionSelector")
        setv(nm, args.group_key, "ActionGroupKey")
        setv(nm, args.group_mask, "ActionGroupMask")
        print("%s: TriggerSource=%s keys set" % (NAMES[id(ia)], src))


def fire_scheduled_action(ias, t_ns, args):
    inm = None
    try:
        inm = ias[0].interface.node_map
    except Exception:
        pass
    if inm is not None and node(inm, "ActionCommand")[1] is not None:
        setv(inm, args.device_key, "ActionDeviceKey")
        setv(inm, args.group_key, "ActionGroupKey")
        setv(inm, args.group_mask, "ActionGroupMask")
        setv(inm, True, "ActionScheduledTimeEnable")
        setv(inm, t_ns, "ActionScheduledTime")
        ip = struct_ip(args.action_dest)
        setv(inm, ip, "GevActionDestinationIPAddress")
        execute(inm, "ActionCommand")
        return "gentl-interface"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind((args.iface, 0))
    s.sendto(raw.build_action_cmd(args.device_key, args.group_key, args.group_mask, t_ns,
                                  req_id=1, ack_required=False), (args.action_dest, raw.GVCP_PORT))
    s.close()
    return "raw-gvcp"


def struct_ip(dotted):
    return int.from_bytes(socket.inet_aton(dotted), "big")


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def run_action_mode(ias, args):
    configure_action_trigger(ias, args)
    for ia in ias:
        ia.start()
    spreads, lags = [], []
    try:
        for k in range(args.frames):
            t_now = latch_ns(ias[0].remote_device.node_map)
            t_act = t_now + args.delay_ms * 1_000_000
            how = fire_scheduled_action(ias, t_act, args)
            ts = []
            for ia in ias:
                with ia.fetch(timeout=args.delay_ms / 1000 + 3) as buf:
                    ts.append(buffer_ts_ns(buf))
            spread = max(ts) - min(ts)
            spreads.append(spread)
            lags.extend(t - t_act for t in ts)
            print("trigger %3d via %s: action_time=%d spread=%7.3f us  ts-action=%s us" % (
                k, how, t_act, spread / 1e3, [round((t - t_act) / 1e3, 3) for t in ts]))
    finally:
        for ia in ias:
            ia.stop()
    print("\nSUMMARY spread us: median %.3f p99 %.3f max %.3f | (frame ts - action time) us: median %.3f" % (
        statistics.median(spreads) / 1e3, pct(spreads, 99) / 1e3, max(spreads) / 1e3,
        statistics.median(lags) / 1e3))
    ok = pct(spreads, 99) / 1e3 < args.max_spread_us
    print("RESULT:", "PASS" if ok else "FAIL", "(threshold %.1f us)" % args.max_spread_us)
    return 0 if ok else 1


def run_freerun_mode(ias, args):
    for ia in ias:
        ia.start()
    streams = {NAMES[id(ia)]: [] for ia in ias}
    try:
        for _ in range(args.frames):
            for ia in ias:
                with ia.fetch(timeout=3) as buf:
                    streams[NAMES[id(ia)]].append(buffer_ts_ns(buf))
    finally:
        for ia in ias:
            ia.stop()
    names = list(streams)
    ref = streams[names[0]]
    ok = True
    for n in names[1:]:
        diffs = [min((abs(t - r), t - r) for t in streams[n])[1] for r in ref]
        med = statistics.median(diffs)
        period = statistics.median([b - a for a, b in zip(ref, ref[1:])]) if len(ref) > 1 else 0
        print("%s vs %s: nearest-frame offset median %+.3f us, p99 |.| %.3f us, frame period %.3f ms" % (
            n, names[0], med / 1e3, pct([abs(d) for d in diffs], 99) / 1e3, period / 1e6))
        ok &= pct([abs(d) for d in diffs], 99) / 1e3 < args.max_spread_us
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cti", required=True, help="path to a GigE Vision GenTL producer (.cti)")
    ap.add_argument("--serial", action="append", help="restrict to these serial numbers")
    ap.add_argument("--mode", choices=["action", "freerun"], default="action")
    ap.add_argument("--frames", type=int, default=50)
    ap.add_argument("--delay-ms", type=int, default=200, help="schedule action this far ahead")
    ap.add_argument("--max-spread-us", type=float, default=50.0)
    ap.add_argument("--offset-ns", type=int, default=1000, help="max |PtpOffsetFromMaster| to accept")
    ap.add_argument("--stable-s", type=float, default=10.0)
    ap.add_argument("--ptp-timeout", type=float, default=120.0)
    ap.add_argument("--external-master", action="store_true", help="host/grandmaster is PTP master")
    ap.add_argument("--skip-ptp", action="store_true", help="do not touch PTP settings")
    ap.add_argument("--device-key", type=lambda x: int(x, 0), default=0x12345678)
    ap.add_argument("--group-key", type=lambda x: int(x, 0), default=1)
    ap.add_argument("--group-mask", type=lambda x: int(x, 0), default=1)
    ap.add_argument("--action-dest", default="255.255.255.255", help="subnet broadcast is safer on multi-NIC hosts")
    ap.add_argument("--iface", default="", help="local IP to send raw ACTION_CMD from")
    args = ap.parse_args()

    h = Harvester()
    h.add_file(args.cti)
    h.update()
    infos = h.device_info_list
    print("devices:", [(d.model, d.serial_number) for d in infos])
    idx = [i for i, d in enumerate(infos) if not args.serial or d.serial_number in args.serial]
    if len(idx) < 2:
        print("need >= 2 cameras, found %d" % len(idx))
    ias = []
    try:
        for i in idx:
            ia = h.create(i)
            NAMES[id(ia)] = "%s#%s" % (infos[i].model, infos[i].serial_number)
            ias.append(ia)
        if not args.skip_ptp:
            enable_ptp(ias, args)
        rc = run_action_mode(ias, args) if args.mode == "action" else run_freerun_mode(ias, args)
    finally:
        for ia in ias:
            ia.destroy()
        h.reset()
    return rc


if __name__ == "__main__":
    sys.exit(main())
