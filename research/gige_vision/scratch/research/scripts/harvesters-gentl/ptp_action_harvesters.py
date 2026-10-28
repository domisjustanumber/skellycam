"""Stand-alone multi-camera PTP + (scheduled) action-command test via Harvesters.

Run on a machine with >=2 PTP-capable GigE Vision cameras and a GenTL producer
(.cti) for GigE Vision. No SkellyCam code is needed.

    python -m venv .venv && .venv/bin/pip install harvesters==1.4.3 genicam numpy
    python ptp_action_harvesters.py /path/to/producer.cti --frames 20 \
        --schedule-ms 50 --out result.json

What it does (all via standard SFNC / GenTL-SFNC feature names, so it works
with any producer + camera that implement them; anything missing is reported,
not faked):
  1. opens every discovered camera once (dedup by vendor+serial);
  2. enables PTP on each camera (SFNC 2.x `PtpEnable`, falls back to the
     deprecated `GevIEEE1588`) and waits until one is Master and the rest are
     Slave, printing `PtpOffsetFromMaster` while waiting;
  3. latches every camera's timestamp back-to-back (`TimestampLatch` /
     `GevTimestampControlLatch`) to show the cameras share one clock;
  4. configures FrameStart trigger from Action1 (`TriggerSource=Action1`,
     `ActionSelector/ActionDeviceKey/ActionGroupKey/ActionGroupMask`) and
     enables the `Timestamp` chunk if available;
  5. fires action commands from the GenTL *Interface* module node map
     (GenTL SFNC 1.2 sec. 3.2.3: `ActionDeviceKey`, `ActionGroupKey`,
     `ActionGroupMask`, `ActionScheduledTimeEnable`, `ActionScheduledTime`,
     `ActionCommand`) on every distinct interface, optionally scheduled
     `--schedule-ms` in the future on the PTP timeline;
  6. fetches one frame per camera per action and reports the per-trigger
     spread of buffer timestamps (GenTL BUFFER_INFO_TIMESTAMP_NS) and of
     ChunkTimestamp values across cameras.
If the producer exposes no interface-level action features, the script says so
and falls back to `TriggerSoftware` per camera (NOT synchronised) so you can
still see the timestamp spread that PTP alone gives you.
"""
import argparse
import json
import sys
import time

from harvesters.core import Harvester


def node(nm, name):
    return getattr(nm, name, None)


def has(nm, name):
    return node(nm, name) is not None


def get(nm, name, default=None):
    n = node(nm, name)
    if n is None:
        return default
    try:
        return n.value
    except Exception:
        return default


def try_set(nm, name, value, log):
    n = node(nm, name)
    if n is None:
        log.append(f"absent: {name}")
        return False
    try:
        n.value = value
        return True
    except Exception as exc:
        log.append(f"failed: {name}={value!r}: {type(exc).__name__}: {exc}")
        return False


def execute(nm, name, log, wait_s=1.0):
    n = node(nm, name)
    if n is None:
        log.append(f"absent: {name}")
        return False
    try:
        n.execute()
        t0 = time.time()
        while hasattr(n, "is_done") and not n.is_done() and time.time() - t0 < wait_s:
            time.sleep(0.001)
        return True
    except Exception as exc:
        log.append(f"failed: {name}.execute(): {type(exc).__name__}: {exc}")
        return False


def latch_timestamp(nm, log):
    if has(nm, "TimestampLatch"):
        execute(nm, "TimestampLatch", log)
        return get(nm, "TimestampLatchValue")
    if has(nm, "GevTimestampControlLatch"):
        execute(nm, "GevTimestampControlLatch", log)
        return get(nm, "GevTimestampValue")
    return None


def ptp_state(nm, log):
    if has(nm, "PtpDataSetLatch"):
        execute(nm, "PtpDataSetLatch", log)
    status = get(nm, "PtpStatus", get(nm, "GevIEEE1588Status"))
    offset = get(nm, "PtpOffsetFromMaster")
    return status, offset


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cti")
    ap.add_argument("--frames", type=int, default=20)
    ap.add_argument("--device-key", type=lambda s: int(s, 0), default=0x1)
    ap.add_argument("--group-key", type=lambda s: int(s, 0), default=0x1)
    ap.add_argument("--group-mask", type=lambda s: int(s, 0), default=0xFFFFFFFF)
    ap.add_argument("--schedule-ms", type=float, default=0.0,
                    help="if >0, use scheduled action commands this far ahead of the master's PTP time")
    ap.add_argument("--ptp-timeout-s", type=float, default=30.0)
    ap.add_argument("--period-s", type=float, default=0.1)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    result = {"cti": args.cti, "cameras": [], "triggers": [], "log": []}
    log = result["log"]
    h = Harvester()
    h.add_file(args.cti)
    h.update()
    seen, acquirers = set(), []
    for i, info in enumerate(h.device_info_list):
        d = info.property_dict
        key = (d.get("vendor"), d.get("serial_number"))
        if key in seen:
            continue
        seen.add(key)
        ia = h.create(i)
        acquirers.append(ia)
        result["cameras"].append({k: str(d.get(k)) for k in ("vendor", "model", "serial_number", "id_")})
    print(f"opened {len(acquirers)} camera(s)")
    if not acquirers:
        raise SystemExit("no cameras")

    # 1-2. PTP
    ptp_capable = []
    for cam, ia in zip(result["cameras"], acquirers):
        nm = ia.remote_device.node_map
        ok = try_set(nm, "PtpEnable", True, log) or try_set(nm, "GevIEEE1588", True, log)
        cam["ptp_enable_ok"] = ok
        ptp_capable.append(ok)
    t0 = time.time()
    while any(ptp_capable) and time.time() - t0 < args.ptp_timeout_s:
        states = [ptp_state(ia.remote_device.node_map, log) for ia in acquirers]
        print("PTP:", [(str(s), o) for s, o in states])
        roles = [str(s) for s, _ in states]
        if roles.count("Master") == 1 and all(r in ("Master", "Slave") for r in roles):
            break
        if all(r == "Slave" for r in roles):  # external grandmaster (e.g. PTP switch / host ptp4l)
            break
        time.sleep(1.0)
    for cam, ia in zip(result["cameras"], acquirers):
        s, o = ptp_state(ia.remote_device.node_map, log)
        cam["ptp_status"], cam["ptp_offset_from_master"] = str(s), o

    # 3. back-to-back timestamp latch
    latched = [latch_timestamp(ia.remote_device.node_map, log) for ia in acquirers]
    result["latched_timestamps"] = latched
    nums = [v for v in latched if isinstance(v, int)]
    if len(nums) > 1:
        print(f"latched timestamps spread: {max(nums) - min(nums)} ticks (includes GVCP round-trip latency of sequential latches)")

    # 4. trigger config
    for ia in acquirers:
        nm = ia.remote_device.node_map
        try_set(nm, "TriggerSelector", "FrameStart", log)
        try_set(nm, "TriggerMode", "On", log)
        if not try_set(nm, "TriggerSource", "Action1", log):
            try_set(nm, "TriggerSource", "Software", log)
        try_set(nm, "ActionSelector", 1, log)
        try_set(nm, "ActionDeviceKey", args.device_key, log)
        try_set(nm, "ActionGroupKey", args.group_key, log)
        try_set(nm, "ActionGroupMask", args.group_mask, log)
        if try_set(nm, "ChunkModeActive", True, log):
            if try_set(nm, "ChunkSelector", "Timestamp", log):
                try_set(nm, "ChunkEnable", True, log)

    # 5. find interfaces that can send action commands
    interfaces = {}
    for ia in acquirers:
        inm = ia.interface.node_map
        iid = get(inm, "InterfaceID", id(inm))
        interfaces.setdefault(iid, inm)
    action_ifaces = {k: v for k, v in interfaces.items() if has(v, "ActionCommand")}
    result["interfaces"] = {str(k): has(v, "ActionCommand") for k, v in interfaces.items()}
    use_action = bool(action_ifaces)
    print(f"interfaces: {result['interfaces']} -> {'action commands' if use_action else 'FALLBACK TriggerSoftware (unsynchronised)'}")
    for inm in action_ifaces.values():
        try_set(inm, "ActionDeviceKey", args.device_key, log)
        try_set(inm, "ActionGroupKey", args.group_key, log)
        try_set(inm, "ActionGroupMask", args.group_mask, log)

    for ia in acquirers:
        ia.start()
    time.sleep(0.2)

    # 6. trigger + fetch
    for k in range(args.frames):
        if use_action:
            sched = None
            if args.schedule_ms > 0:
                now = latch_timestamp(acquirers[0].remote_device.node_map, log)
                if isinstance(now, int):
                    sched = now + int(args.schedule_ms * 1e6)  # assumes ns ticks (PTP)
            for inm in action_ifaces.values():
                if sched is not None and has(inm, "ActionScheduledTime"):
                    try_set(inm, "ActionScheduledTimeEnable", True, log)
                    try_set(inm, "ActionScheduledTime", sched, log)
                elif has(inm, "ActionScheduledTimeEnable"):
                    try_set(inm, "ActionScheduledTimeEnable", False, log)
                execute(inm, "ActionCommand", log)
        else:
            for ia in acquirers:
                execute(ia.remote_device.node_map, "TriggerSoftware", log)
        rec = {"k": k, "cams": []}
        for ia in acquirers:
            try:
                with ia.fetch(timeout=3) as buf:
                    ts = None
                    try:
                        ts = buf.timestamp_ns
                    except Exception:
                        ts = buf.timestamp
                    rec["cams"].append({
                        "frame_id": buf.module.frame_id,
                        "timestamp": ts,
                        "chunk_timestamp": get(ia.remote_device.node_map, "ChunkTimestamp"),
                    })
            except Exception as exc:
                rec["cams"].append({"error": f"{type(exc).__name__}: {exc}"})
        tss = [c.get("timestamp") for c in rec["cams"] if isinstance(c.get("timestamp"), int)]
        cts = [c.get("chunk_timestamp") for c in rec["cams"] if isinstance(c.get("chunk_timestamp"), int)]
        rec["spread_buffer_ts"] = (max(tss) - min(tss)) if len(tss) > 1 else None
        rec["spread_chunk_ts"] = (max(cts) - min(cts)) if len(cts) > 1 else None
        print(k, rec["spread_buffer_ts"], rec["spread_chunk_ts"], rec["cams"])
        result["triggers"].append(rec)
        time.sleep(args.period_s)

    for ia in acquirers:
        ia.stop()
        nm = ia.remote_device.node_map
        try_set(nm, "TriggerMode", "Off", log)
        ia.destroy()
    h.reset()
    spreads = [r["spread_buffer_ts"] for r in result["triggers"] if r["spread_buffer_ts"] is not None]
    if spreads:
        spreads.sort()
        result["summary"] = {"buffer_ts_spread_median": spreads[len(spreads) // 2],
                             "buffer_ts_spread_max": spreads[-1],
                             "mode": "action" if use_action else "software-trigger fallback"}
        print("summary:", result["summary"])
    print("log (absent/failed features):")
    for line in sorted(set(log)):
        print("   ", line)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2, default=str)


if __name__ == "__main__":
    sys.exit(main())
