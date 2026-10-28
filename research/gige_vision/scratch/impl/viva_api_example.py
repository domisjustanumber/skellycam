"""viva-genicam 0.10.0 reference example for a SkellyCam GigE Vision backend.

Tested with viva-genicam 0.10.0 (PyPI, tag py-v0.10.0 = d53a48f) on
Windows 11 / CPython 3.12 and in Docker (python:3.12-bookworm), against the
library's own in-process FakeGigeCamera. NOT tested against a real camera:
the PTP and action-trigger configuration paths below are written from the
SFNC / vendor feature names and are exercised only as far as the fake allows
(the fake has no PTP enable/status nodes and no Action trigger source).

Usage:
    # one or more in-process fake cameras, one per host IPv4 address
    python viva_api_example.py --fake 127.0.0.1 [--fake 172.30.224.1 ...]
    # real cameras (untested), selected by IP
    python viva_api_example.py --ip 192.168.6.20 --ip 192.168.6.21

Rules this script follows (each verified on the fake unless marked):
* A camera is opened only from a GigeDeviceInfo returned by discovery; there
  is no constructor from an IP in 0.10.0 (vg.discover_ip exists only on the
  unreleased main branch). Discovery skips loopback unless all=True.
* Every call that waits on the network releases the GIL; one Camera may be
  used from several threads (calls are serialised on a mutex).
* A FrameStream must be read by ONE thread at a time (a second concurrent
  next_frame raises RuntimeError "Already borrowed").
* The stream delivery queue holds only 4 frames: a reader that falls behind
  loses the OLDEST frames (counted in stats().frames_backpressure).
* Frame.ts_dev is the raw GVSP leader timestamp in device ticks
  (GevTimestampTickFrequency per second). Keep it, and block_id, apart from
  host lifecycle timestamps.
* PTP must be enabled BEFORE the stream is opened (untested here).
"""

from __future__ import annotations

import argparse
import logging
import threading
import time
from dataclasses import dataclass, field

import numpy as np
import viva_genicam as vg
from viva_genicam.testing import FakeGigeCamera  # not imported by `import viva_genicam`

logger = logging.getLogger(__name__)

# ── GigE Vision bootstrap registers (GigE Vision 2.x spec, also used by 3.0) ──
REG_VERSION = 0x0000  # major in the high 16 bits (3 for a GEV 3.0 device)
REG_GVCP_CAPABILITY = 0x0934
CAP_IEEE1588 = 0x0008_0000
CAP_SCHEDULED_ACTION = 0x0002_0000
CAP_ACTION = 0x0000_0040
REG_TICK_FREQ_HIGH = 0x093C
REG_TICK_FREQ_LOW = 0x0940

# PTP feature names, newest SFNC first, then deprecated / vendor spellings.
PTP_ENABLE_BOOLS = ("PtpEnable", "GevIEEE1588")
PTP_STATUS_ENUMS = ("PtpStatus", "GevIEEE1588Status")
PTP_LATCH_COMMANDS = ("PtpDataSetLatch", "GevIEEE1588DataSetLatch")
TIMESTAMP_LATCH_COMMANDS = ("TimestampLatch", "GevTimestampControlLatch", "TimestampControlLatch")
TIMESTAMP_VALUE_INTEGERS = ("TimestampLatchValue", "GevTimestampValue", "TimestampValue")

# Action keys. A real camera must be configured with the same values
# (ActionDeviceKey / ActionGroupKey / ActionGroupMask); the fake's are fixed.
FAKE_ACTION_KEYS = (FakeGigeCamera.DEVICE_KEY, FakeGigeCamera.GROUP_KEY, FakeGigeCamera.GROUP_MASK)  # 0x42, 1, 1

PREFERRED_PIXEL_FORMATS = ("BayerRG8", "BayerBG8", "BayerGR8", "BayerGB8", "Mono8", "RGB8")


def u32(data: bytes) -> int:
    return int.from_bytes(data, "big")


# ── discovery / opening ─────────────────────────────────────────────────────
def find_device(
    ip: str | None = None,
    mac: str | None = None,
    iface: str | None = None,
    timeout_ms: int = 1000,
) -> vg.GigeDeviceInfo:
    """Discover, then pick a camera by IP or MAC ("DE:AD:BE:EF:CA:FE").

    all=True also searches loopback, which is where FakeGigeCamera answers.
    discover() always waits the whole timeout. To select by serial number,
    connect and read DeviceSerialNumber: GigeDeviceInfo has no serial field
    in the Python binding (the discovery ACK's serial is dropped)."""
    devices = vg.discover(timeout_ms=timeout_ms, iface=iface, all=True)
    for dev in devices:
        if ip is not None and dev.ip == ip:
            return dev
        if mac is not None and dev.mac.upper() == mac.upper():
            return dev
    raise LookupError(f"no GigE Vision camera matching ip={ip} mac={mac}; discovered {[d.ip for d in devices]}")


# ── feature helpers ─────────────────────────────────────────────────────────
def has_feature(cam: vg.Camera, name: str) -> bool:
    """node_info returns None for a feature the XML does not declare."""
    return cam.node_info(name) is not None


def first_feature(cam: vg.Camera, names: tuple[str, ...]) -> str | None:
    return next((n for n in names if has_feature(cam, n)), None)


def set_enum_if_available(cam: vg.Camera, name: str, entry: str) -> bool:
    """Write an enumeration by entry NAME, only if the entry is selectable now."""
    if not has_feature(cam, name) or entry not in cam.available_enum_entries(name):
        return False
    cam.set_enum(name, entry)
    return True


def choose_pixel_format(cam: vg.Camera) -> str:
    """Keep the camera's format if it is 8-bit, else switch to the first 8-bit
    one it offers now (entries can be gated, e.g. by SensorType)."""
    current = cam.get_enum("PixelFormat")
    if current in PREFERRED_PIXEL_FORMATS:
        return current
    available = cam.available_enum_entries("PixelFormat")
    for pf in PREFERRED_PIXEL_FORMATS:
        if pf in available:
            cam.set_enum("PixelFormat", pf)
            return pf
    raise RuntimeError(f"no 8-bit pixel format among {available}")


def tick_frequency_hz(cam: vg.Camera) -> int:
    """Device timestamp ticks per second: GenApi node, else bootstrap 0x093C/0x0940."""
    if has_feature(cam, "GevTimestampTickFrequency"):
        return cam.get_integer("GevTimestampTickFrequency")
    return (u32(cam.read_register(REG_TICK_FREQ_HIGH)) << 32) | u32(cam.read_register(REG_TICK_FREQ_LOW))


def latch_device_ticks(cam: vg.Camera) -> int:
    """Latch the device clock and read it (GVCP round trip; ~ms uncertainty)."""
    latch = first_feature(cam, TIMESTAMP_LATCH_COMMANDS)
    value = first_feature(cam, TIMESTAMP_VALUE_INTEGERS)
    if latch is None or value is None:
        raise RuntimeError("camera has no timestamp latch feature")
    cam.execute(latch)
    cam.invalidate(value)  # the latch changes the value behind GenApi's cache
    return cam.get_integer(value)


@dataclass
class SyncCapabilities:
    gev_major: int
    ptp_bootstrap: bool
    action_bootstrap: bool
    scheduled_action_bootstrap: bool
    ptp_enable_feature: str | None
    ptp_status_feature: str | None
    action_trigger_source: str | None


def probe_sync_capabilities(cam: vg.Camera) -> SyncCapabilities:
    version = u32(cam.read_register(REG_VERSION))
    capability = u32(cam.read_register(REG_GVCP_CAPABILITY))
    trigger_sources = cam.enum_entries("TriggerSource") if has_feature(cam, "TriggerSource") else []
    return SyncCapabilities(
        gev_major=version >> 16,
        ptp_bootstrap=bool(capability & CAP_IEEE1588),
        action_bootstrap=bool(capability & CAP_ACTION),
        scheduled_action_bootstrap=bool(capability & CAP_SCHEDULED_ACTION),
        ptp_enable_feature=first_feature(cam, PTP_ENABLE_BOOLS),
        ptp_status_feature=first_feature(cam, PTP_STATUS_ENUMS),
        action_trigger_source=next((s for s in ("Action1", "Action0") if s in trigger_sources), None),
    )


def enable_ptp(cam: vg.Camera, caps: SyncCapabilities) -> str | None:
    """UNTESTED on hardware. Enable PTP by feature name and return its status.

    Must run before cam.stream(). Allied Vision (PtpMode) and LUCID
    (PtpSlaveOnly) spellings would need extra branches."""
    if caps.ptp_enable_feature is None:
        return None
    cam.set_bool(caps.ptp_enable_feature, True)
    latch = first_feature(cam, PTP_LATCH_COMMANDS)
    if latch is not None:
        cam.execute(latch)
    if caps.ptp_status_feature is None:
        return None
    cam.invalidate(caps.ptp_status_feature)
    return cam.get_enum(caps.ptp_status_feature)


def configure_action_trigger(cam: vg.Camera, caps: SyncCapabilities, keys: tuple[int, int, int]) -> bool:
    """UNTESTED on hardware. FrameStart triggered by action command `keys`."""
    if caps.action_trigger_source is None:
        return False
    device_key, group_key, group_mask = keys
    cam.set_integer("ActionDeviceKey", device_key)
    if has_feature(cam, "ActionSelector"):
        cam.set_integer("ActionSelector", int(caps.action_trigger_source[-1]))
    cam.set_integer("ActionGroupKey", group_key)
    cam.set_integer("ActionGroupMask", group_mask)
    cam.enable_trigger("FrameStart", caps.action_trigger_source)  # selector, source, mode On
    return True


# ── capture ─────────────────────────────────────────────────────────────────
@dataclass
class CapturedFrame:
    image: np.ndarray  # (H, W) uint8 mosaic/mono, or (H, W, 3) RGB
    pixel_format: str
    block_id: int  # 16-bit on GEV 1.x/2.x without extended ids: wraps 65535 -> 1
    device_ticks: int | None  # GVSP leader timestamp, device clock
    host_receive_ns: int  # time.perf_counter_ns() when next_frame returned


@dataclass
class CaptureResult:
    ip: str
    frames: list[CapturedFrame] = field(default_factory=list)
    stats: vg.StreamStats | None = None
    error: BaseException | None = None


def capture(cam: vg.Camera, ip: str, n_frames: int, result: CaptureResult, start: threading.Barrier) -> None:
    """Pull `n_frames` frames. Runs in its own thread; the GIL is released while
    next_frame waits, so several of these run in parallel."""
    try:
        # packet_size=None keeps the camera's GevSCPSPacketSize;
        # auto_packet_size=True sizes it from the NIC MTU (jumbo frames).
        with cam.stream(auto_packet_size=True) as frames:  # AcquisitionStart on enter
            start.wait()
            while len(result.frames) < n_frames:
                frame = frames.next_frame(timeout_ms=2000)  # raises TransportError on timeout
                if frame is None:  # clean end of stream
                    break
                received = time.perf_counter_ns()
                # to_numpy(): one copy into a writeable array; Bayer stays a
                # mosaic (demosaic with cv2: PFNC BayerRG8 -> cv2.COLOR_BayerBG2BGR).
                result.frames.append(
                    CapturedFrame(
                        image=frame.to_numpy(),
                        pixel_format=frame.pixel_format,
                        block_id=frame.block_id,
                        device_ticks=frame.ts_dev,
                        host_receive_ns=received,
                    )
                )
            result.stats = frames.stats()
        # AcquisitionStop + socket close on exit
    except BaseException as err:  # noqa: BLE001 - report every failure to the caller
        result.error = err


def run(ips: list[str], n_frames: int, action_keys: tuple[int, int, int]) -> None:
    cameras: dict[str, vg.Camera] = {}
    try:
        for ip in ips:
            cam = vg.connect_gige(find_device(ip=ip))  # claims control privilege + heartbeat
            cameras[ip] = cam
            caps = probe_sync_capabilities(cam)
            pixel_format = choose_pixel_format(cam)
            logger.info(
                "%s: %s %s serial=%s GEV %d.x pf=%s tick=%d Hz caps=%s",
                ip, cam.get("DeviceVendorName"), cam.get("DeviceModelName"),
                cam.get("DeviceSerialNumber") if has_feature(cam, "DeviceSerialNumber") else "?",
                caps.gev_major, pixel_format, tick_frequency_hz(cam), caps,
            )
            ptp_status = enable_ptp(cam, caps)  # before the stream opens
            logger.info("%s: PTP status %s; action trigger configured: %s",
                        ip, ptp_status, configure_action_trigger(cam, caps, action_keys))

        results = {ip: CaptureResult(ip=ip) for ip in ips}
        barrier = threading.Barrier(len(ips) + 1)
        threads = [
            threading.Thread(target=capture, args=(cameras[ip], ip, n_frames, results[ip], barrier), daemon=True)
            for ip in ips
        ]
        for t in threads:
            t.start()
        barrier.wait()  # every stream is open and acquiring

        # Scheduled action: fire FrameStart at device time now + 100 ms. With
        # PTP all cameras share the clock, so one command (broadcast, or one per
        # camera IP) triggers them together. Without PTP the time is in camera
        # 0's clock only. timeout_ms bounds how long acks are collected.
        reference = cameras[ips[0]]
        action_time = latch_device_ticks(reference) + tick_frequency_hz(reference) // 10
        for ip in ips:
            ack = vg.send_action(*action_keys, scheduled_time=action_time, destination=ip, timeout_ms=100)
            logger.info("scheduled action -> %s: %s", ip, ack)

        for t in threads:
            t.join(60)
        for ip, result in results.items():
            if result.error is not None:
                logger.error("%s: capture failed: %r", ip, result.error)
                continue
            frames = result.frames
            ticks = [f.device_ticks for f in frames if f.device_ticks is not None]
            logger.info(
                "%s: %d frames %s %s, block ids %d..%d, device tick span %s, lost=%d backpressure=%d resend_recovered=%d",
                ip, len(frames), frames[0].pixel_format, frames[0].image.shape,
                frames[0].block_id, frames[-1].block_id,
                (ticks[-1] - ticks[0]) if len(ticks) > 1 else None,
                result.stats.frames_lost, result.stats.frames_backpressure, result.stats.resend_recovered,
            )
    finally:
        for cam in cameras.values():
            cam.close()  # releases control privilege at once


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fake", action="append", default=[], help="start a FakeGigeCamera bound to this host IPv4")
    parser.add_argument("--ip", action="append", default=[], help="real camera IP (untested)")
    parser.add_argument("--frames", type=int, default=100)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # The fake streams in free-run (it counts action commands but has no Action
    # trigger source), discovery reaches it only at port 3956, so one fake per
    # host address: 127.0.0.1 plus each NIC address on Windows; on Linux add
    # loopback aliases (ip addr add 127.0.0.2/8 dev lo).
    fakes = [
        FakeGigeCamera(width=640, height=480, fps=30, bind_ip=ip, pixel_format=pf)
        for ip, pf in zip(args.fake, ("BayerRG8", "Mono8", "RGB8", "BayerRG8"))
    ]
    for fake in fakes:
        fake.start()
    try:
        keys = FAKE_ACTION_KEYS if fakes else (1, 1, 0xFFFFFFFF)
        run(args.fake + args.ip, args.frames, keys)
        for fake in fakes:
            logger.info("fake %s acted on %d action command(s)", fake.ip, fake.actions())
    finally:
        for fake in fakes:
            fake.stop()


if __name__ == "__main__":
    main()
