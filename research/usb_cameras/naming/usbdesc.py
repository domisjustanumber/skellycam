# /// script
# requires-python = ">=3.10"
# ///
"""Pure-python parser for USB device / configuration / BOS descriptors with UVC class detail.

Stdlib only, platform independent. Used by:
  - naming/win_identity_dump.py  (descriptors read through the parent hub with
    IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION)
  - naming/linux_identity.py     (sysfs `descriptors` file = device descriptor + all config descriptors)
  - any libusb/pyusb backend that can hand over the raw bytes.

Self-test:  uv run --script research/usb_cameras/naming/usbdesc.py --selftest

Output structure of parse_configuration() is documented in naming/README.md ("descriptors.json schema").
Units: frame intervals are in 100 ns units as on the wire; `fps` is derived (1e7 / interval).
Bandwidth: `bytes_per_interval` = payload bytes the endpoint may move per service interval,
`max_bytes_per_second` = bytes_per_interval * service intervals per second (derived from bInterval + speed).
"""
from __future__ import annotations

import struct
import sys
import uuid

# ---------------------------------------------------------------- constants
DT_DEVICE, DT_CONFIG, DT_STRING, DT_INTERFACE, DT_ENDPOINT = 1, 2, 3, 4, 5
DT_DEVICE_QUALIFIER, DT_OTHER_SPEED, DT_IAD, DT_BOS = 6, 7, 0x0B, 0x0F
DT_DEVICE_CAPABILITY, DT_SS_EP_COMPANION, DT_SSP_ISO_EP_COMPANION = 0x10, 0x30, 0x31
CS_INTERFACE, CS_ENDPOINT = 0x24, 0x25
CC_VIDEO, CC_AUDIO = 0x0E, 0x01
SC_VIDEOCONTROL, SC_VIDEOSTREAMING, SC_VIDEO_INTERFACE_COLLECTION = 1, 2, 3

VC_SUBTYPES = {1: "VC_HEADER", 2: "VC_INPUT_TERMINAL", 3: "VC_OUTPUT_TERMINAL", 4: "VC_SELECTOR_UNIT",
               5: "VC_PROCESSING_UNIT", 6: "VC_EXTENSION_UNIT", 7: "VC_ENCODING_UNIT"}
VS_SUBTYPES = {1: "VS_INPUT_HEADER", 2: "VS_OUTPUT_HEADER", 3: "VS_STILL_IMAGE_FRAME",
               4: "VS_FORMAT_UNCOMPRESSED", 5: "VS_FRAME_UNCOMPRESSED", 6: "VS_FORMAT_MJPEG",
               7: "VS_FRAME_MJPEG", 0x0A: "VS_FORMAT_MPEG2TS", 0x0C: "VS_FORMAT_DV", 0x0D: "VS_COLORFORMAT",
               0x10: "VS_FORMAT_FRAME_BASED", 0x11: "VS_FRAME_FRAME_BASED", 0x12: "VS_FORMAT_STREAM_BASED",
               0x13: "VS_FORMAT_H264", 0x14: "VS_FRAME_H264", 0x15: "VS_FORMAT_H264_SIMULCAST",
               0x16: "VS_FORMAT_VP8", 0x17: "VS_FRAME_VP8", 0x18: "VS_FORMAT_VP8_SIMULCAST"}
FORMAT_SUBTYPES = {4: "UNCOMPRESSED", 6: "MJPEG", 0x10: "FRAME_BASED", 0x13: "H264", 0x16: "VP8",
                   0x0A: "MPEG2TS", 0x0C: "DV", 0x12: "STREAM_BASED"}
FRAME_FOR_FORMAT = {4: 5, 6: 7, 0x10: 0x11, 0x13: 0x14, 0x16: 0x17}
TERMINAL_TYPES = {0x0100: "TT_VENDOR_SPECIFIC", 0x0101: "TT_STREAMING", 0x0200: "ITT_VENDOR_SPECIFIC",
                  0x0201: "ITT_CAMERA", 0x0202: "ITT_MEDIA_TRANSPORT_INPUT", 0x0300: "OTT_VENDOR_SPECIFIC",
                  0x0301: "OTT_DISPLAY", 0x0302: "OTT_MEDIA_TRANSPORT_OUTPUT"}
CAMERA_CONTROL_BITS = ["scanning_mode", "auto_exposure_mode", "auto_exposure_priority", "exposure_time_absolute",
                       "exposure_time_relative", "focus_absolute", "focus_relative", "iris_absolute",
                       "iris_relative", "zoom_absolute", "zoom_relative", "pantilt_absolute", "pantilt_relative",
                       "roll_absolute", "roll_relative", "reserved15", "reserved16", "focus_auto", "privacy",
                       "focus_simple", "window", "region_of_interest"]
PROCESSING_CONTROL_BITS = ["brightness", "contrast", "hue", "saturation", "sharpness", "gamma",
                           "white_balance_temperature", "white_balance_component", "backlight_compensation",
                           "gain", "power_line_frequency", "hue_auto", "white_balance_temperature_auto",
                           "white_balance_component_auto", "digital_multiplier", "digital_multiplier_limit",
                           "analog_video_standard", "analog_video_lock_status", "contrast_auto"]
SPEEDS = {0: "low", 1: "full", 2: "high", 3: "super", 4: "super_plus"}
EP_TYPES = {0: "control", 1: "isochronous", 2: "bulk", 3: "interrupt"}
ISO_SYNC = {0: "none", 1: "async", 2: "adaptive", 3: "sync"}
BOS_CAPS = {1: "WIRELESS_USB", 2: "USB_2_0_EXTENSION", 3: "SUPERSPEED_USB", 4: "CONTAINER_ID",
            5: "PLATFORM", 0x0A: "SUPERSPEED_PLUS", 0x0B: "PRECISION_TIME_MEASUREMENT", 0x0E: "CONFIGURATION_SUMMARY"}
# Well known extension-unit GUIDs (only used as labels; absence of a label means nothing)
KNOWN_XU = {
    "63610682-5070-49ab-b8cc-b3855e8d221d": "Logitech UVC extensions (video pipe v1)",
    "63610682-5070-49ab-b8cc-b3855e8d221e": "Logitech UVC extensions (video pipe v3)",
    "63610682-5070-49ab-b8cc-b3855e8d221f": "Logitech UVC extensions (video pipe v4)",
    "63610682-5070-49ab-b8cc-b3855e8d2250": "Logitech UVC extensions (peripheral)",
    "63610682-5070-49ab-b8cc-b3855e8d2256": "Logitech UVC extensions (user hw control)",
    "a917c75d-4119-11da-ae0e-000d56ac7b4c": "Microsoft XU / H.264 (UVC 1.1 extension, Logitech)",
    "0f3f95dc-2632-4c4e-92c9-a04782f43bc8": "Microsoft camera XU (MSXU 1.0)",
}


def _guid(b: bytes) -> str:
    return str(uuid.UUID(bytes_le=bytes(b)))


def _fourcc_from_guid(b: bytes) -> str | None:
    tail = bytes(b[4:])
    if tail == bytes.fromhex("000010008000 00aa00389b71".replace(" ", "")):
        cc = bytes(b[:4])
        if all(32 <= c < 127 for c in cc):
            return cc.decode("ascii")
    return None


def _bits(mask: int, names: list[str]) -> list[str]:
    return [n for i, n in enumerate(names) if mask >> i & 1]


def _le(data: bytes, off: int, n: int) -> int:
    return int.from_bytes(data[off:off + n], "little")


# ---------------------------------------------------------------- standard descriptors
def parse_device_descriptor(d: bytes) -> dict:
    if len(d) < 18 or d[1] != DT_DEVICE:
        raise ValueError(f"not a device descriptor: {bytes(d[:18]).hex()}")
    (bLength, bDescriptorType, bcdUSB, bDeviceClass, bDeviceSubClass, bDeviceProtocol, bMaxPacketSize0,
     idVendor, idProduct, bcdDevice, iManufacturer, iProduct, iSerialNumber,
     bNumConfigurations) = struct.unpack_from("<BBHBBBBHHHBBBB", d)
    return dict(bcdUSB=f"{bcdUSB >> 8:x}.{bcdUSB & 0xff:02x}", bcdUSB_raw=bcdUSB, bDeviceClass=bDeviceClass,
                bDeviceSubClass=bDeviceSubClass, bDeviceProtocol=bDeviceProtocol, bMaxPacketSize0=bMaxPacketSize0,
                idVendor=f"{idVendor:04x}", idProduct=f"{idProduct:04x}", bcdDevice=f"{bcdDevice:04x}",
                iManufacturer=iManufacturer, iProduct=iProduct, iSerialNumber=iSerialNumber,
                bNumConfigurations=bNumConfigurations)


def endpoint_bandwidth(ep: dict, speed: str | None) -> dict:
    """Bytes per service interval and per second for an isochronous/interrupt/bulk endpoint.

    High speed: wMaxPacketSize[10:0] bytes per transaction, [12:11] additional transactions per microframe,
    service interval = 2**(bInterval-1) microframes (125 us).  SuperSpeed: wBytesPerInterval from the
    endpoint companion, service interval 2**(bInterval-1) * 125 us.  Full speed iso: 2**(bInterval-1) ms.
    """
    raw = ep["wMaxPacketSize_raw"]
    size = raw & 0x7FF
    mult = ((raw >> 11) & 0x3) + 1
    out = dict(bytes_per_transaction=size, transactions_per_microframe=mult)
    t = ep["transfer_type"]
    if t not in ("isochronous", "interrupt"):
        out["bytes_per_interval"] = None
        out["max_bytes_per_second"] = None
        return out
    b_int = ep["bInterval"]
    comp = ep.get("ss_companion")
    if speed in ("super", "super_plus") and comp:
        bpi = comp["wBytesPerInterval"]
        if comp.get("ssp_iso_companion_dwBytesPerInterval"):
            bpi = comp["ssp_iso_companion_dwBytesPerInterval"]
        period_s = (2 ** (max(b_int, 1) - 1)) * 125e-6
    elif speed in ("high", None):
        bpi = size * mult
        period_s = (2 ** (max(b_int, 1) - 1)) * 125e-6
    elif speed == "full":
        bpi = size
        period_s = ((2 ** (max(b_int, 1) - 1)) if t == "isochronous" else max(b_int, 1)) * 1e-3
    else:
        bpi = size
        period_s = max(b_int, 1) * 1e-3
    out["bytes_per_interval"] = bpi
    out["service_interval_us"] = round(period_s * 1e6, 3)
    out["max_bytes_per_second"] = int(round(bpi / period_s))
    out["assumed_speed"] = speed or "high"
    return out


def _parse_endpoint(d: bytes) -> dict:
    bEndpointAddress, bmAttributes, wMaxPacketSize, bInterval = struct.unpack_from("<BBHB", d, 2)
    ttype = EP_TYPES[bmAttributes & 3]
    ep = dict(bEndpointAddress=f"0x{bEndpointAddress:02x}", direction="in" if bEndpointAddress & 0x80 else "out",
              number=bEndpointAddress & 0xF, transfer_type=ttype, bmAttributes=bmAttributes,
              wMaxPacketSize_raw=wMaxPacketSize, bInterval=bInterval)
    if ttype == "isochronous":
        ep["sync_type"] = ISO_SYNC[(bmAttributes >> 2) & 3]
        ep["usage_type"] = ["data", "feedback", "implicit_feedback", "reserved"][(bmAttributes >> 4) & 3]
    return ep


def _parse_vc(d: bytes) -> dict:
    sub = d[2]
    name = VC_SUBTYPES.get(sub, f"VC_0x{sub:02x}")
    out: dict = dict(subtype=name)
    try:
        if sub == 1:
            bcdUVC, wTotalLength, dwClockFrequency, bInCollection = struct.unpack_from("<HHIB", d, 3)
            out.update(bcdUVC=f"{bcdUVC >> 8:x}.{bcdUVC & 0xff:02x}", bcdUVC_raw=bcdUVC, wTotalLength=wTotalLength,
                       dwClockFrequency=dwClockFrequency, baInterfaceNr=list(d[12:12 + bInCollection]))
        elif sub == 2:
            bTerminalID, wTerminalType, bAssocTerminal, iTerminal = struct.unpack_from("<BHBB", d, 3)
            out.update(bTerminalID=bTerminalID, wTerminalType=TERMINAL_TYPES.get(wTerminalType, f"0x{wTerminalType:04x}"),
                       bAssocTerminal=bAssocTerminal, iTerminal=iTerminal)
            if wTerminalType == 0x0201 and len(d) >= 15:
                fmin, fmax, focal, bControlSize = struct.unpack_from("<HHHB", d, 8)
                mask = _le(d, 15, bControlSize)
                out.update(wObjectiveFocalLengthMin=fmin, wObjectiveFocalLengthMax=fmax, wOcularFocalLength=focal,
                           bmControls=f"0x{mask:0{bControlSize * 2}x}", controls=_bits(mask, CAMERA_CONTROL_BITS))
        elif sub == 3:
            bTerminalID, wTerminalType, bAssocTerminal, bSourceID, iTerminal = struct.unpack_from("<BHBBB", d, 3)
            out.update(bTerminalID=bTerminalID, wTerminalType=TERMINAL_TYPES.get(wTerminalType, f"0x{wTerminalType:04x}"),
                       bSourceID=bSourceID, iTerminal=iTerminal)
        elif sub == 4:
            bUnitID, bNrInPins = d[3], d[4]
            out.update(bUnitID=bUnitID, baSourceID=list(d[5:5 + bNrInPins]))
        elif sub == 5:
            bUnitID, bSourceID, wMaxMultiplier, bControlSize = struct.unpack_from("<BBHB", d, 3)
            mask = _le(d, 8, bControlSize)
            out.update(bUnitID=bUnitID, bSourceID=bSourceID, wMaxMultiplier=wMaxMultiplier,
                       bmControls=f"0x{mask:0{bControlSize * 2}x}", controls=_bits(mask, PROCESSING_CONTROL_BITS),
                       iProcessing=d[8 + bControlSize] if len(d) > 8 + bControlSize else None)
        elif sub == 6:
            bUnitID = d[3]
            g = _guid(d[4:20])
            bNumControls, bNrInPins = d[20], d[21]
            srcs = list(d[22:22 + bNrInPins])
            o = 22 + bNrInPins
            bControlSize = d[o]
            mask = _le(d, o + 1, bControlSize)
            out.update(bUnitID=bUnitID, guidExtensionCode=g, known_as=KNOWN_XU.get(g), bNumControls=bNumControls,
                       baSourceID=srcs, bmControls=f"0x{mask:0{max(bControlSize, 1) * 2}x}",
                       iExtension=d[o + 1 + bControlSize] if len(d) > o + 1 + bControlSize else None)
        elif sub == 7:
            out.update(bUnitID=d[3], bSourceID=d[4], iEncoding=d[5])
    except (struct.error, IndexError) as e:  # malformed descriptor, keep raw
        out["parse_error"] = str(e)
    out["raw"] = bytes(d).hex()
    return out


def _intervals(d: bytes, off: int, n: int) -> dict:
    if n == 0:
        mn, mx, step = struct.unpack_from("<III", d, off)
        return dict(interval_type="continuous", dwMinFrameInterval=mn, dwMaxFrameInterval=mx,
                    dwFrameIntervalStep=step, fps_max=round(1e7 / mn, 3) if mn else None,
                    fps_min=round(1e7 / mx, 3) if mx else None)
    vals = list(struct.unpack_from(f"<{n}I", d, off))
    return dict(interval_type="discrete", dwFrameInterval=vals, fps=[round(1e7 / v, 3) if v else None for v in vals])


def _parse_vs(d: bytes) -> dict:
    sub = d[2]
    name = VS_SUBTYPES.get(sub, f"VS_0x{sub:02x}")
    out: dict = dict(subtype=name)
    try:
        if sub == 1:
            bNumFormats, wTotalLength, bEndpointAddress, bmInfo, bTerminalLink, bStillCaptureMethod, \
                bTriggerSupport, bTriggerUsage, bControlSize = struct.unpack_from("<BHBBBBBBB", d, 3)
            ctrls = [_le(d, 13 + i * bControlSize, bControlSize) for i in range(bNumFormats)]
            out.update(bNumFormats=bNumFormats, bEndpointAddress=f"0x{bEndpointAddress:02x}", bmInfo=bmInfo,
                       bTerminalLink=bTerminalLink, bStillCaptureMethod=bStillCaptureMethod,
                       bTriggerSupport=bTriggerSupport, bTriggerUsage=bTriggerUsage, bmaControls=ctrls)
        elif sub in (4, 0x10):
            bFormatIndex, bNumFrameDescriptors = d[3], d[4]
            g = bytes(d[5:21])
            bBitsPerPixel, bDefaultFrameIndex, ax, ay, interlace, copyp = struct.unpack_from("<BBBBBB", d, 21)
            out.update(bFormatIndex=bFormatIndex, bNumFrameDescriptors=bNumFrameDescriptors, guidFormat=_guid(g),
                       fourcc=_fourcc_from_guid(g), bBitsPerPixel=bBitsPerPixel, bDefaultFrameIndex=bDefaultFrameIndex,
                       bAspectRatioX=ax, bAspectRatioY=ay, bmInterlaceFlags=interlace, bCopyProtect=copyp)
            if sub == 0x10 and len(d) > 27:
                out["bVariableSize"] = d[27]
        elif sub == 6:
            bFormatIndex, bNumFrameDescriptors, bmFlags, bDefaultFrameIndex, ax, ay, interlace, copyp = \
                struct.unpack_from("<BBBBBBBB", d, 3)
            out.update(bFormatIndex=bFormatIndex, bNumFrameDescriptors=bNumFrameDescriptors, fourcc="MJPG",
                       bmFlags=bmFlags, fixed_size_samples=bool(bmFlags & 1), bDefaultFrameIndex=bDefaultFrameIndex,
                       bAspectRatioX=ax, bAspectRatioY=ay, bmInterlaceFlags=interlace, bCopyProtect=copyp)
        elif sub in (5, 7):
            bFrameIndex, bmCapabilities, wWidth, wHeight, dwMinBitRate, dwMaxBitRate, dwMaxVideoFrameBufferSize, \
                dwDefaultFrameInterval, bFrameIntervalType = struct.unpack_from("<BBHHIIIIB", d, 3)
            out.update(bFrameIndex=bFrameIndex, bmCapabilities=bmCapabilities, wWidth=wWidth, wHeight=wHeight,
                       dwMinBitRate=dwMinBitRate, dwMaxBitRate=dwMaxBitRate,
                       dwMaxVideoFrameBufferSize=dwMaxVideoFrameBufferSize,
                       dwDefaultFrameInterval=dwDefaultFrameInterval, **_intervals(d, 26, bFrameIntervalType))
        elif sub == 0x11:
            bFrameIndex, bmCapabilities, wWidth, wHeight, dwMinBitRate, dwMaxBitRate, dwDefaultFrameInterval, \
                bFrameIntervalType, dwBytesPerLine = struct.unpack_from("<BBHHIIIBI", d, 3)
            out.update(bFrameIndex=bFrameIndex, bmCapabilities=bmCapabilities, wWidth=wWidth, wHeight=wHeight,
                       dwMinBitRate=dwMinBitRate, dwMaxBitRate=dwMaxBitRate,
                       dwDefaultFrameInterval=dwDefaultFrameInterval, dwBytesPerLine=dwBytesPerLine,
                       **_intervals(d, 26, bFrameIntervalType))
        elif sub == 0x13:
            out.update(bFormatIndex=d[3], bNumFrameDescriptors=d[4], fourcc="H264", bDefaultFrameIndex=d[5])
        elif sub == 0x14:
            bFrameIndex, wWidth, wHeight = struct.unpack_from("<BHH", d, 3)
            dwMinBitRate, dwMaxBitRate, dwDefaultFrameInterval, bNumFrameIntervals = struct.unpack_from("<IIIB", d, 31)
            out.update(bFrameIndex=bFrameIndex, wWidth=wWidth, wHeight=wHeight, dwMinBitRate=dwMinBitRate,
                       dwMaxBitRate=dwMaxBitRate, dwDefaultFrameInterval=dwDefaultFrameInterval,
                       **_intervals(d, 44, bNumFrameIntervals))
        elif sub == 3:
            bEndpointAddress, n = d[3], d[4]
            sizes = [struct.unpack_from("<HH", d, 5 + 4 * i) for i in range(n)]
            out.update(bEndpointAddress=f"0x{bEndpointAddress:02x}", sizes=[dict(wWidth=w, wHeight=h) for w, h in sizes])
        elif sub == 0x0D:
            out.update(bColorPrimaries=d[3], bTransferCharacteristics=d[4], bMatrixCoefficients=d[5])
    except (struct.error, IndexError) as e:
        out["parse_error"] = str(e)
    out["raw"] = bytes(d).hex()
    return out


def split_descriptors(blob: bytes) -> list[bytes]:
    out, i = [], 0
    while i + 2 <= len(blob):
        n = blob[i]
        if n < 2 or i + n > len(blob):
            break
        out.append(bytes(blob[i:i + n]))
        i += n
    return out


def parse_configuration(blob: bytes, speed: str | None = None) -> dict:
    """Parse a full configuration descriptor (wTotalLength bytes) into a structured dict with UVC detail."""
    descs = split_descriptors(blob)
    if not descs or descs[0][1] != DT_CONFIG:
        raise ValueError("not a configuration descriptor")
    c = descs[0]
    wTotalLength, bNumInterfaces, bConfigurationValue, iConfiguration, bmAttributes, bMaxPower = \
        struct.unpack_from("<HBBBBB", c, 2)
    cfg: dict = dict(wTotalLength=wTotalLength, bNumInterfaces=bNumInterfaces, bConfigurationValue=bConfigurationValue,
                     iConfiguration=iConfiguration, bmAttributes=f"0x{bmAttributes:02x}",
                     self_powered=bool(bmAttributes & 0x40), remote_wakeup=bool(bmAttributes & 0x20),
                     max_power_mA=bMaxPower * (8 if speed in ("super", "super_plus") else 2),
                     interface_associations=[], interfaces=[])
    cur_if: dict | None = None
    cur_ep: dict | None = None
    for d in descs[1:]:
        t = d[1]
        if t == DT_IAD:
            first, count, fcls, fsub, fproto, ifn = struct.unpack_from("<BBBBBB", d, 2)
            cfg["interface_associations"].append(dict(bFirstInterface=first, bInterfaceCount=count,
                                                      bFunctionClass=fcls, bFunctionSubClass=fsub,
                                                      bFunctionProtocol=fproto, iFunction=ifn))
        elif t == DT_INTERFACE:
            num, alt, neps, cls, sub, proto, iif = struct.unpack_from("<BBBBBBB", d, 2)
            kind = None
            if cls == CC_VIDEO:
                kind = {1: "video_control", 2: "video_streaming"}.get(sub, f"video_sub{sub}")
            elif cls == CC_AUDIO:
                kind = {1: "audio_control", 2: "audio_streaming"}.get(sub, f"audio_sub{sub}")
            cur_if = dict(bInterfaceNumber=num, bAlternateSetting=alt, bNumEndpoints=neps, bInterfaceClass=cls,
                          bInterfaceSubClass=sub, bInterfaceProtocol=proto, iInterface=iif, kind=kind,
                          class_specific=[], endpoints=[])
            cfg["interfaces"].append(cur_if)
            cur_ep = None
        elif t == DT_ENDPOINT and cur_if is not None:
            cur_ep = _parse_endpoint(d)
            cur_if["endpoints"].append(cur_ep)
        elif t == DT_SS_EP_COMPANION and cur_ep is not None:
            bMaxBurst, bmAttr, wBytesPerInterval = struct.unpack_from("<BBH", d, 2)
            cur_ep["ss_companion"] = dict(bMaxBurst=bMaxBurst, bmAttributes=bmAttr, wBytesPerInterval=wBytesPerInterval)
        elif t == DT_SSP_ISO_EP_COMPANION and cur_ep is not None and cur_ep.get("ss_companion") is not None:
            cur_ep["ss_companion"]["ssp_iso_companion_dwBytesPerInterval"] = struct.unpack_from("<I", d, 4)[0]
        elif t == CS_INTERFACE and cur_if is not None:
            if cur_if["kind"] == "video_control":
                cur_if["class_specific"].append(_parse_vc(d))
            elif cur_if["kind"] == "video_streaming":
                cur_if["class_specific"].append(_parse_vs(d))
            else:
                cur_if["class_specific"].append(dict(subtype=f"0x{d[2]:02x}", raw=d.hex()))
        elif t == CS_ENDPOINT and cur_ep is not None:
            cur_ep.setdefault("class_specific", []).append(dict(raw=d.hex()))
        else:
            cfg.setdefault("other_descriptors", []).append(dict(bDescriptorType=f"0x{t:02x}", raw=d.hex()))
    for itf in cfg["interfaces"]:
        for ep in itf["endpoints"]:
            ep["bandwidth"] = endpoint_bandwidth(ep, speed)
    cfg["uvc"] = summarize_uvc(cfg)
    return cfg


def summarize_uvc(cfg: dict) -> dict | None:
    """Flatten UVC-relevant info: VC header, units, and per streaming interface formats/frames/alt settings."""
    vc = [i for i in cfg["interfaces"] if i["kind"] == "video_control"]
    if not vc:
        return None
    header = next((cs for i in vc for cs in i["class_specific"] if cs["subtype"] == "VC_HEADER"), {})
    units = [cs for i in vc for cs in i["class_specific"] if cs["subtype"] != "VC_HEADER"]
    vc_ep = [ep for i in vc for ep in i["endpoints"]]
    streams = []
    vs_nums = sorted({i["bInterfaceNumber"] for i in cfg["interfaces"] if i["kind"] == "video_streaming"})
    for n in vs_nums:
        alts = [i for i in cfg["interfaces"] if i["bInterfaceNumber"] == n]
        alt0 = next(i for i in alts if i["bAlternateSetting"] == 0)
        hdr = next((cs for cs in alt0["class_specific"] if cs["subtype"] in ("VS_INPUT_HEADER", "VS_OUTPUT_HEADER")), {})
        formats, cur = [], None
        for cs in alt0["class_specific"]:
            st = cs["subtype"]
            if st.startswith("VS_FORMAT_"):
                cur = dict(cs)
                cur.pop("raw", None)
                cur["format"] = st[len("VS_FORMAT_"):]
                cur["frames"] = []
                formats.append(cur)
            elif st.startswith("VS_FRAME_") and cur is not None:
                f = dict(cs)
                f.pop("raw", None)
                cur["frames"].append(f)
            elif st == "VS_COLORFORMAT" and cur is not None:
                cur["color_matching"] = {k: v for k, v in cs.items() if k not in ("raw", "subtype")}
            elif st == "VS_STILL_IMAGE_FRAME" and cur is not None:
                cur["still_image_frame"] = {k: v for k, v in cs.items() if k not in ("raw", "subtype")}
        alt_list = []
        for a in alts:
            for ep in a["endpoints"]:
                alt_list.append(dict(bAlternateSetting=a["bAlternateSetting"], bEndpointAddress=ep["bEndpointAddress"],
                                     transfer_type=ep["transfer_type"], wMaxPacketSize_raw=ep["wMaxPacketSize_raw"],
                                     bInterval=ep["bInterval"], ss_companion=ep.get("ss_companion"), **ep["bandwidth"]))
            if not a["endpoints"]:
                alt_list.append(dict(bAlternateSetting=a["bAlternateSetting"], bEndpointAddress=None,
                                     transfer_type=None, max_bytes_per_second=0))
        bulk = any(x["transfer_type"] == "bulk" for x in alt_list)
        streams.append(dict(bInterfaceNumber=n, transport="bulk" if bulk else "isochronous",
                            input_header={k: v for k, v in hdr.items() if k != "raw"}, formats=formats,
                            alt_settings=alt_list))
    return dict(bcdUVC=header.get("bcdUVC"), dwClockFrequency=header.get("dwClockFrequency"),
                vc_interface=vc[0]["bInterfaceNumber"], vc_interrupt_endpoint=vc_ep[0]["bEndpointAddress"] if vc_ep else None,
                units=[{k: v for k, v in u.items() if k != "raw"} for u in units], streaming_interfaces=streams)


def parse_bos(blob: bytes) -> dict:
    descs = split_descriptors(blob)
    if not descs or descs[0][1] != DT_BOS:
        raise ValueError("not a BOS descriptor")
    caps = []
    for d in descs[1:]:
        if d[1] != DT_DEVICE_CAPABILITY:
            continue
        ct = d[2]
        cap: dict = dict(bDevCapabilityType=BOS_CAPS.get(ct, f"0x{ct:02x}"), raw=d.hex())
        if ct == 4 and len(d) >= 20:
            cap["ContainerID"] = _guid(d[4:20])
        elif ct == 2:
            cap["bmAttributes"] = f"0x{_le(d, 3, 4):08x}"
        elif ct == 3:
            bmAttributes, wSpeedsSupported, bFunctionalitySupport, u1, u2 = struct.unpack_from("<BHBBH", d, 3)
            cap.update(wSpeedsSupported=f"0x{wSpeedsSupported:04x}", bU1DevExitLat=u1, wU2DevExitLat=u2)
        elif ct == 5 and len(d) >= 20:
            cap["PlatformCapabilityUUID"] = _guid(d[4:20])
        caps.append(cap)
    return dict(capabilities=caps)


def decode_string_descriptor(d: bytes) -> str:
    if len(d) < 2 or d[1] != DT_STRING:
        raise ValueError("not a string descriptor")
    return bytes(d[2:d[0]]).decode("utf-16-le", errors="replace")


def parse_sysfs_descriptors(blob: bytes, speed: str | None = None) -> dict:
    """Linux /sys/bus/usb/devices/<dev>/descriptors: device descriptor followed by every config descriptor."""
    dev = parse_device_descriptor(blob[:18])
    rest, configs = blob[18:], []
    while len(rest) >= 9 and rest[1] == DT_CONFIG:
        total = _le(rest, 2, 2)
        configs.append(parse_configuration(rest[:total], speed))
        rest = rest[total:]
    return dict(device=dev, configurations=configs)


# ---------------------------------------------------------------- self test
def _selftest() -> int:
    # Synthetic UVC 1.0 config: IAD + VC(header, camera IT, PU, OT) + VS alt0(input hdr, MJPEG fmt, 1 frame) + alt1 iso ep
    vc_hdr = bytes([13, 0x24, 1]) + struct.pack("<HHIB", 0x0100, 0, 48_000_000, 1) + bytes([1])
    it = bytes([18, 0x24, 2, 1]) + struct.pack("<HBB", 0x0201, 0, 0) + struct.pack("<HHHB", 0, 0, 0, 3) + (0x0A).to_bytes(3, "little")
    pu = bytes([11, 0x24, 5, 2, 1]) + struct.pack("<HB", 0, 2) + (0x0001).to_bytes(2, "little") + bytes([0])
    ot = bytes([9, 0x24, 3, 3]) + struct.pack("<HBBB", 0x0101, 0, 2, 0)
    vc_if = bytes([9, 4, 0, 0, 0, 0x0E, 1, 0, 0])
    vs_hdr = bytes([14, 0x24, 1, 1]) + struct.pack("<HBBBBBBB", 0, 0x81, 0, 3, 0, 0, 0, 1) + bytes([0])
    fmt = bytes([11, 0x24, 6, 1, 1, 1, 1, 0, 0, 0, 0])
    frame = bytes([30, 0x24, 7, 1, 0]) + struct.pack("<HHIIII", 640, 480, 1, 2, 614400, 333333) + bytes([1]) + struct.pack("<I", 333333)
    vs0 = bytes([9, 4, 1, 0, 0, 0x0E, 2, 0, 0])
    vs1 = bytes([9, 4, 1, 1, 1, 0x0E, 2, 0, 0])
    ep = bytes([7, 5, 0x81, 0x05]) + struct.pack("<HB", 0x1000 | 0x3FC, 1)
    iad = bytes([8, 0x0B, 0, 2, 0x0E, 3, 0, 0])
    body = iad + vc_if + vc_hdr + it + pu + ot + vs0 + vs_hdr + fmt + frame + vs1 + ep
    cfg = bytes([9, 2]) + struct.pack("<HBBBBB", 9 + len(body), 2, 1, 0, 0x80, 250) + body
    p = parse_configuration(cfg, "high")
    u = p["uvc"]
    assert u["bcdUVC"] == "1.00" and u["dwClockFrequency"] == 48_000_000, u
    s = u["streaming_interfaces"][0]
    assert s["formats"][0]["format"] == "MJPEG" and s["formats"][0]["frames"][0]["wWidth"] == 640
    alt1 = [a for a in s["alt_settings"] if a["bAlternateSetting"] == 1][0]
    assert alt1["bytes_per_transaction"] == 0x3FC and alt1["transactions_per_microframe"] == 3, alt1
    assert alt1["max_bytes_per_second"] == 0x3FC * 3 * 8000, alt1
    assert "exposure_time_absolute" in u["units"][0]["controls"], u["units"][0]
    print("usbdesc selftest OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
