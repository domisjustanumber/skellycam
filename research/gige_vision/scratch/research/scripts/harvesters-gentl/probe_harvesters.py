"""Probe a GenTL producer (.cti) with Harvesters against whatever GigE Vision
devices it discovers (real or emulated, e.g. arv-fake-gv-camera-0.8).

Usage: python probe_harvesters.py <path/to/producer.cti> [n_frames]

Prints: producer/system info, per-device info, which GenTL-SFNC interface
ActionControl features exist, which SFNC PTP / timestamp / chunk features the
camera exposes, then acquires n frames from every device and reports shape,
dtype, pixel format, payload type, frame_id, timestamp_ns / timestamp /
timestamp_frequency, and measured fps.
"""
import sys
import time

import numpy
from harvesters.core import Harvester

ACTION_FEATURES = [
    "ActionControl", "ActionCommand", "ActionDeviceKey", "ActionGroupKey",
    "ActionGroupMask", "ActionScheduledTimeEnable", "ActionScheduledTime",
    "GevActionDestinationIPAddress",
]
REMOTE_FEATURES = [
    # SFNC PTP (GEV 2.x+ cameras) and legacy GEV IEEE1588 names
    "PtpEnable", "PtpStatus", "PtpDataSetLatch", "PtpOffsetFromMaster",
    "GevIEEE1588", "GevIEEE1588Status",
    # timestamps
    "TimestampLatch", "TimestampLatchValue", "GevTimestampTickFrequency",
    "GevTimestampControlLatch", "GevTimestampValue",
    # action / scheduled action on the device side
    "ActionDeviceKey", "ActionGroupKey", "ActionGroupMask", "ActionSelector",
    "ActionUnconditionalMode",
    # trigger, chunk
    "TriggerSelector", "TriggerMode", "TriggerSource",
    "ChunkModeActive", "ChunkSelector", "ChunkEnable",
    # image format
    "PixelFormat", "Width", "Height", "AcquisitionFrameRate",
    "GevSCPSPacketSize",
]


def feature_value(node_map, name):
    node = getattr(node_map, name, None)
    if node is None:
        return "<absent>"
    try:
        return repr(node.value)
    except Exception as exc:  # command nodes, unreadable nodes
        return f"<present, {type(node).__name__}: {type(exc).__name__}>"


def main():
    cti = sys.argv[1]
    n_frames = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    h = Harvester()
    h.add_file(cti)
    h.update()
    print(f"cti={cti}")
    print(f"devices found: {len(h.device_info_list)}")
    for i, info in enumerate(h.device_info_list):
        print(f"  [{i}] {info.property_dict}")
    if not h.device_info_list:
        h.reset()
        raise SystemExit("FAIL: no devices discovered")

    # A camera reachable through several host interfaces (e.g. lo + eth0) is
    # listed once per interface; open each physical camera (serial) once.
    seen, indices = set(), []
    for i, info in enumerate(h.device_info_list):
        key = (info.property_dict.get("vendor"), info.property_dict.get("serial_number"))
        if key not in seen:
            seen.add(key)
            indices.append(i)
    print(f"opening device indices {indices}")
    acquirers = [h.create(i) for i in indices]
    ia0 = acquirers[0]
    sysnm = ia0.system.node_map
    for name in ["TLVendorName", "TLModelName", "TLVersion", "TLType",
                 "GenTLVersionMajor", "GenTLVersionMinor"]:
        print(f"system.{name} = {feature_value(sysnm, name)}")

    for k, ia in enumerate(acquirers):
        print(f"--- device {k}")
        ifnm = ia.interface.node_map
        print(f"interface.InterfaceID = {feature_value(ifnm, 'InterfaceID')}")
        for name in ACTION_FEATURES:
            print(f"interface.{name} = {feature_value(ifnm, name)}")
        rnm = ia.remote_device.node_map
        for name in REMOTE_FEATURES:
            print(f"remote.{name} = {feature_value(rnm, name)}")

    for ia in acquirers:
        ia.start()
    stats = [[] for _ in acquirers]
    t0 = time.perf_counter()
    for _ in range(n_frames):
        for k, ia in enumerate(acquirers):
            with ia.fetch(timeout=5) as buf:
                comp = buf.payload.components[0]
                ncomp = int(comp.num_components_per_pixel) or 1
                img = comp.data.reshape(comp.height, comp.width, ncomp) if ncomp > 1                     else comp.data.reshape(comp.height, comp.width)
                chunks = {}
                if len(stats[k]) == 0:
                    # Harvesters auto-attaches chunk data to the remote node map
                    # (ParameterKey.ENABLE_AUTO_CHUNK_DATA_UPDATE, default True)
                    rnm = ia.remote_device.node_map
                    for n in getattr(rnm, "nodes", []):
                        name = n.node.name
                        if name.startswith("Chunk") and name not in ("ChunkModeActive", "ChunkSelector", "ChunkEnable"):
                            chunks[name] = _safe(lambda: getattr(rnm, name).value)
                rec = dict(
                    frame_id=buf.module.frame_id,
                    timestamp_ns=_safe(lambda: buf.timestamp_ns),
                    timestamp=buf.timestamp,
                    timestamp_frequency=_safe(lambda: buf.timestamp_frequency),  # raises AttributeError in 1.4.3 if producer lacks TIMESTAMP_NS
                    payload_type=str(buf.payload_type),
                    data_format=comp.data_format,
                    shape=img.shape, dtype=str(img.dtype),
                    mean=float(numpy.mean(img)),
                    is_data_owned_by_numpy=img.base is not None,
                )
                if chunks:
                    rec["chunks"] = chunks
                stats[k].append(rec)
    dt = time.perf_counter() - t0
    for ia in acquirers:
        ia.stop()
    for k, recs in enumerate(stats):
        print(f"--- device {k}: {len(recs)} frames in {dt:.2f}s "
              f"(~{len(recs)/dt:.1f} fps each)")
        for r in recs[:3] + recs[-2:]:
            print("   ", r)
        ts = [r["timestamp_ns"] for r in recs if isinstance(r["timestamp_ns"], int)]
        if len(ts) > 1:
            d = numpy.diff(numpy.array(ts, dtype=numpy.int64))
            print(f"    timestamp_ns deltas: min={d.min()} median={int(numpy.median(d))} max={d.max()}")
    for ia in acquirers:
        ia.destroy()
    h.reset()
    print("OK")


def _safe(fn):
    try:
        return fn()
    except Exception as exc:
        return f"<{type(exc).__name__}: {exc}>"


if __name__ == "__main__":
    main()
