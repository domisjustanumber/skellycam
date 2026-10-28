"""
gev_common.py - shared, standard-library-only GigE Vision (GEV) helpers for the
stand-alone GigE Vision hardware tests in this folder.

Nothing here imports the rest of SkellyCam or any third-party package, so this
folder can be copied to any machine with Python >= 3.9 and the scripts run
directly (``python gev_probe.py --help``). Keep this file next to the scripts.

What is in here:
  * GVCP (control protocol, UDP 3956): DISCOVERY, READREG/WRITEREG,
    READMEM/WRITEMEM, PENDING_ACK, control channel privilege + heartbeat,
    ACTION_CMD (immediate and scheduled), PACKETRESEND (16- and 64-bit ids)
  * GVSP (stream protocol): standard and extended-ID (EI) headers, leaders,
    trailers, a frame-completeness analyser and a compressed/uncompressed verdict
  * pcap / pcapng reading and writing (no libpcap needed)
  * a deliberately tiny GenICam XML helper: fetch the XML, list feature names and
    enum entries, execute simple commands such as AcquisitionStart
  * IPv4 interface listing and multi-interface discovery
  * PASS / FAIL / SKIP / WARN / INFO reporting and a pure-unit selftest

Wire formats follow the Wireshark dissectors (epan/dissectors/packet-gvcp.c and
packet-gvsp.c) and Aravis (src/arvgvcpprivate.h, src/arvgvspprivate.h).
GigE Vision 2.x and 3.0 devices use the same GVCP/GVSP formats. The optional
GEV 3.0 RDMA streaming protocol (GVRSP over RoCEv2) is NOT supported here.

DRAFT: verified only against software-emulated cameras (Aravis
arv-fake-gv-camera-0.8 and viva-genicam's FakeGigeCamera). See README.md.
"""
from __future__ import annotations

import io
import ipaddress
import json
import os
import platform
import re
import select
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, deque
from dataclasses import dataclass
from collections.abc import Callable, Iterator  # noqa: TC003 - beartype resolves annotations at runtime
from typing import Any, Optional, Union

BytesLike = Union[bytes, bytearray, memoryview]
Number = Union[int, float]  # beartype (used by SkellyCam) does not accept int for a float hint

# =============================================================================
# Protocol constants
# =============================================================================
GVCP_PORT = 3956
GVCP_KEY = 0x42

# GVCP command / acknowledge codes (packet-gvcp.c "Command and acknowledge IDs")
CMD_DISCOVERY, ACK_DISCOVERY = 0x0002, 0x0003
CMD_PACKETRESEND = 0x0040
CMD_READREG, ACK_READREG = 0x0080, 0x0081
CMD_WRITEREG, ACK_WRITEREG = 0x0082, 0x0083
CMD_READMEM, ACK_READMEM = 0x0084, 0x0085
CMD_WRITEMEM, ACK_WRITEMEM = 0x0086, 0x0087
ACK_PENDING = 0x0089
CMD_ACTION, ACK_ACTION = 0x0100, 0x0101

FLAG_ACK_REQUIRED = 0x01
FLAG_DISCOVERY_ALLOW_BROADCAST_ACK = 0x10
FLAG_EXTENDED_IDS = 0x10  # PACKETRESEND carrying a 64-bit block id
FLAG_SCHEDULED_ACTION = 0x80

READMEM_MAX = 512  # bytes per READMEM (multiple of 4, below the 536-byte GVCP limit)

# Bootstrap registers (packet-gvcp.c #defines; Aravis arvgvcpprivate.h)
REG_VERSION = 0x0000
REG_DEVICE_MODE = 0x0004
REG_FIRST_URL = 0x0200
REG_LINK_SPEED_0 = 0x0670
REG_N_MESSAGE_CHANNELS = 0x0900
REG_N_STREAM_CHANNELS = 0x0904
REG_N_ACTION_SIGNALS = 0x0908
REG_ACTION_DEVICE_KEY = 0x090C
REG_SC_CAPS = 0x092C
REG_GVCP_CAPABILITY = 0x0934
REG_HEARTBEAT_TIMEOUT = 0x0938
REG_TICK_FREQ_HIGH = 0x093C
REG_TICK_FREQ_LOW = 0x0940
REG_TIMESTAMP_CONTROL = 0x0944  # write 2 = latch, 1 = reset
REG_TIMESTAMP_VALUE_HIGH = 0x0948
REG_TIMESTAMP_VALUE_LOW = 0x094C
REG_GVCP_CONFIGURATION = 0x0954
REG_GVSP_CONFIGURATION = 0x0960
REG_IEEE1588_STATUS = 0x096C
REG_SCHED_ACTION_QUEUE_SIZE = 0x0970
REG_IEEE1588_EXT_CAPABILITY = 0x0974
REG_IEEE1588_SUPPORTED_PROFILES = 0x0978
REG_IEEE1588_SELECTED_PROFILE = 0x097C
REG_CCP = 0x0A00
TIMESTAMP_CONTROL_LATCH = 2
CCP_EXCLUSIVE, CCP_CONTROL = 0x1, 0x2


def reg_sc_port(i: int) -> int:
    return 0x0D00 + 0x40 * i


def reg_sc_packet_size(i: int) -> int:
    return 0x0D04 + 0x40 * i


def reg_sc_packet_delay(i: int) -> int:
    return 0x0D08 + 0x40 * i


def reg_sc_dest_address(i: int) -> int:
    return 0x0D18 + 0x40 * i


def reg_sc_source_port(i: int) -> int:
    return 0x0D1C + 0x40 * i


def reg_sc_capability(i: int) -> int:
    return 0x0D20 + 0x40 * i


def reg_sc_configuration(i: int) -> int:
    return 0x0D24 + 0x40 * i


def reg_action_group_key(i: int) -> int:
    return 0x9800 + 0x10 * i


def reg_action_group_mask(i: int) -> int:
    return 0x9804 + 0x10 * i


SCPS_FIRE_TEST, SCPS_DO_NOT_FRAGMENT, SCPS_PACKET_SIZE_MASK = 0x80000000, 0x40000000, 0x0000FFFF

# (name, mask, GEV version that Wireshark tags the bit with, or "")
CAPABILITY_BITS: list[tuple[str, int, str]] = [
    ("user_defined_name", 0x80000000, ""), ("serial_number", 0x40000000, ""),
    ("heartbeat_disable", 0x20000000, ""), ("link_speed_registers", 0x10000000, ""),
    ("ccp_application_port_ip", 0x08000000, ""), ("manifest_table", 0x04000000, ""),
    ("test_data", 0x02000000, ""), ("discovery_ack_delay", 0x01000000, ""),
    ("writable_discovery_ack_delay", 0x00800000, ""), ("extended_status_codes_v1_1", 0x00400000, "1.1"),
    ("primary_application_switchover", 0x00200000, ""), ("unconditional_action", 0x00100000, ""),
    ("ieee1588", 0x00080000, "2.0"), ("extended_status_codes_v2_0", 0x00040000, "2.0"),
    ("scheduled_action", 0x00020000, "2.0"), ("ieee1588_extended_capabilities", 0x00010000, "2.1"),
    ("action", 0x00000040, ""), ("pending_ack", 0x00000020, ""), ("event_data", 0x00000010, ""),
    ("event", 0x00000008, ""), ("packet_resend", 0x00000004, ""), ("write_mem", 0x00000002, ""),
    ("concatenation", 0x00000001, ""),
]
CAP = {name: mask for name, mask, _ in CAPABILITY_BITS}

GVCP_CONFIG_BITS: list[tuple[str, int, str]] = [
    ("ieee1588_enable", 0x00080000, "2.0"), ("extended_status_codes_v2_0_enable", 0x00040000, "2.0"),
    ("unconditional_action_enable", 0x00000008, "2.0"), ("extended_status_codes_v1_1_enable", 0x00000004, "1.1"),
    ("pending_ack_enable", 0x00000002, ""), ("heartbeat_disable", 0x00000001, ""),
]
CFG_IEEE1588_ENABLE = 0x00080000

SC_CAPS_BITS: list[tuple[str, int, str]] = [
    ("scsp_registers", 0x80000000, ""), ("legacy_16bit_block_id", 0x40000000, "2.0"),
    ("scmbs_registers", 0x20000000, "2.2"), ("sceba_registers", 0x10000000, "2.2"),
]
STREAM_CHANNEL_CAP_BITS: list[tuple[str, int, str]] = [
    ("big_little_endian", 0x80000000, ""), ("ip_reassembly", 0x40000000, ""),
    ("scmpc_register", 0x00000100, "2.2"), ("gendc", 0x00000080, "2.2"), ("multi_part", 0x00000040, "2.1"),
    ("large_leader_trailer", 0x00000020, "2.1"), ("multizone", 0x00000010, "2.0"),
    ("packet_resend_destination", 0x00000008, "2.0"), ("packet_resend_all_in_transmission", 0x00000004, "2.0"),
    ("unconditional_streaming", 0x00000002, ""), ("extended_chunk_data", 0x00000001, ""),
]
GVSP_CONFIG_64BIT_BLOCK_ID = 0x40000000
IEEE1588_PROFILE_BITS: list[tuple[str, int, str]] = [
    ("ptp_profile", 0x80000000, "2.1"), ("ieee802_1as_profile", 0x40000000, "2.1"),
]

# IEEE 1588 clock status (0x096C, low 4 bits) - SFNC PtpStatus values 1..9
PTP_STATES: dict[int, str] = {
    1: "Initializing", 2: "Faulty", 3: "Disabled", 4: "Listening", 5: "PreMaster",
    6: "Master", 7: "Passive", 8: "Uncalibrated", 9: "Slave",
}

GEV_STATUS: dict[int, str] = {
    0x0000: "SUCCESS", 0x0100: "PACKET_RESEND", 0x8001: "NOT_IMPLEMENTED", 0x8002: "INVALID_PARAMETER",
    0x8003: "INVALID_ADDRESS", 0x8004: "WRITE_PROTECT", 0x8005: "BAD_ALIGNMENT", 0x8006: "ACCESS_DENIED",
    0x8007: "BUSY", 0x8008: "LOCAL_PROBLEM", 0x8009: "MSG_MISMATCH", 0x800A: "INVALID_PROTOCOL",
    0x800B: "NO_MSG", 0x800C: "PACKET_UNAVAILABLE", 0x800D: "DATA_OVERRUN", 0x800E: "INVALID_HEADER",
    0x800F: "WRONG_CONFIG", 0x8010: "PACKET_NOT_YET_AVAILABLE", 0x8011: "PACKET_AND_PREV_REMOVED_FROM_MEMORY",
    0x8012: "PACKET_REMOVED_FROM_MEMORY", 0x8013: "NO_REF_TIME", 0x8014: "PACKET_TEMPORARILY_UNAVAILABLE",
    0x8015: "OVERFLOW", 0x8016: "ACTION_LATE", 0x8017: "LEADER_TRAILER_OVERFLOW", 0x8FFF: "ERROR",
}
STATUS_ACCESS_DENIED = 0x8006
STATUS_ACTION_LATE = 0x8016

# GVSP payload types (packet-gvsp.c) and packet formats
PAYLOAD_TYPES: dict[int, str] = {
    0x0001: "IMAGE", 0x0002: "RAW_DATA", 0x0003: "FILE", 0x0004: "CHUNK_DATA",
    0x0005: "EXTENDED_CHUNK_DATA(deprecated)", 0x0006: "JPEG", 0x0007: "JPEG2000", 0x0008: "H264",
    0x0009: "MULTIZONE_IMAGE", 0x000A: "MULTIPART", 0x000B: "GENDC",
}
COMPRESSED_PAYLOAD_TYPES = {0x0006, 0x0007, 0x0008}
PAYLOAD_TYPE_CHUNK_BIT = 0x4000
PT_IMAGE, PT_JPEG, PT_JPEG2000, PT_H264, PT_MULTIZONE = 0x0001, 0x0006, 0x0007, 0x0008, 0x0009
FMT_LEADER, FMT_TRAILER, FMT_PAYLOAD, FMT_ALL_IN = 1, 2, 3, 4
PACKET_FORMATS: dict[int, str] = {
    1: "LEADER", 2: "TRAILER", 3: "PAYLOAD", 4: "ALL_IN", 5: "PAYLOAD_H264",
    6: "PAYLOAD_MULTIZONE", 7: "PAYLOAD_MULTIPART", 8: "PAYLOAD_GENDC",
}
GVSP_EI_BIT = 0x80
IP_UDP_OVERHEAD = 20 + 8

# PFNC pixel format codes -> names, generated from Wireshark packet-gvsp.c pixeltypenames[]
PFNC_NAMES: dict[int, str] = {
    0x01010037: "Mono1p", 0x010100C5: "Confidence1p", 0x01020038: "Mono2p", 0x01040039: "Mono4p",
    0x0104010D: "BayerGR4p", 0x0104010E: "BayerRG4p", 0x0104010F: "BayerGB4p", 0x01040110: "BayerBG4p",
    0x01080001: "Mono8", 0x01080002: "Mono8s", 0x01080008: "BayerGR8", 0x01080009: "BayerRG8",
    0x0108000A: "BayerGB8", 0x0108000B: "BayerBG8", 0x01080067: "SCF1WBWG8", 0x0108006E: "SCF1WGWB8",
    0x01080075: "SCF1WGWR8", 0x0108007C: "SCF1WRWG8", 0x010800AF: "Coord3D_A8", 0x010800B0: "Coord3D_B8",
    0x010800B1: "Coord3D_C8", 0x010800C4: "Confidence1", 0x010800C6: "Confidence8", 0x010800C9: "R8",
    0x010800CD: "G8", 0x010800D1: "B8", 0x01080116: "Data8", 0x01080117: "Data8s", 0x010A0046: "Mono10p",
    0x010A0052: "BayerBG10p", 0x010A0054: "BayerGB10p", 0x010A0056: "BayerGR10p", 0x010A0058: "BayerRG10p",
    0x010A0069: "SCF1WBWG10p", 0x010A0070: "SCF1WGWB10p", 0x010A0077: "SCF1WGWR10p",
    0x010A007E: "SCF1WRWG10p", 0x010A00CA: "R10_Deprecated", 0x010A00CE: "G10_Deprecated",
    0x010A00D2: "B10_Deprecated", 0x010A00D5: "Coord3D_A10p", 0x010A00D6: "Coord3D_B10p",
    0x010A00D7: "Coord3D_C10p", 0x010C0004: "GVSP_Mono10Packed", 0x010C0006: "GVSP_Mono12Packed",
    0x010C0026: "GVSP_BayerGR10Packed", 0x010C0027: "GVSP_BayerRG10Packed",
    0x010C0028: "GVSP_BayerGB10Packed", 0x010C0029: "GVSP_BayerBG10Packed",
    0x010C002A: "GVSP_BayerGR12Packed", 0x010C002B: "GVSP_BayerRG12Packed",
    0x010C002C: "GVSP_BayerGB12Packed", 0x010C002D: "GVSP_BayerBG12Packed", 0x010C0047: "Mono12p",
    0x010C0053: "BayerBG12p", 0x010C0055: "BayerGB12p", 0x010C0057: "BayerGR12p", 0x010C0059: "BayerRG12p",
    0x010C006B: "SCF1WBWG12p", 0x010C0072: "SCF1WGWB12p", 0x010C0079: "SCF1WGWR12p",
    0x010C0080: "SCF1WRWG12p", 0x010C00CB: "R12_Deprecated", 0x010C00CF: "G12_Deprecated",
    0x010C00D3: "B12_Deprecated", 0x010C00D8: "Coord3D_A12p", 0x010C00D9: "Coord3D_B12p",
    0x010C00DA: "Coord3D_C12p", 0x010E0104: "Mono14p", 0x010E0105: "BayerGR14p", 0x010E0106: "BayerRG14p",
    0x010E0107: "BayerGB14p", 0x010E0108: "BayerBG14p", 0x01100003: "Mono10", 0x01100005: "Mono12",
    0x01100007: "Mono16", 0x0110000C: "BayerGR10", 0x0110000D: "BayerRG10", 0x0110000E: "BayerGB10",
    0x0110000F: "BayerBG10", 0x01100010: "BayerGR12", 0x01100011: "BayerRG12", 0x01100012: "BayerGB12",
    0x01100013: "BayerBG12", 0x01100025: "Mono14", 0x0110002E: "BayerGR16", 0x0110002F: "BayerRG16",
    0x01100030: "BayerGB16", 0x01100031: "BayerBG16", 0x01100068: "SCF1WBWG10", 0x0110006A: "SCF1WBWG12",
    0x0110006C: "SCF1WBWG14", 0x0110006D: "SCF1WBWG16", 0x0110006F: "SCF1WGWB10", 0x01100071: "SCF1WGWB12",
    0x01100073: "SCF1WGWB14", 0x01100074: "SCF1WGWB16", 0x01100076: "SCF1WGWR10", 0x01100078: "SCF1WGWR12",
    0x0110007A: "SCF1WGWR14", 0x0110007B: "SCF1WGWR16", 0x0110007D: "SCF1WRWG10", 0x0110007F: "SCF1WRWG12",
    0x01100081: "SCF1WRWG14", 0x01100082: "SCF1WRWG16", 0x011000B6: "Coord3D_A16", 0x011000B7: "Coord3D_B16",
    0x011000B8: "Coord3D_C16", 0x011000C7: "Confidence16", 0x011000CC: "R16", 0x011000D0: "G16",
    0x011000D4: "B16", 0x01100109: "BayerGR14", 0x0110010A: "BayerRG14", 0x0110010B: "BayerGB14",
    0x0110010C: "BayerBG14", 0x01100118: "Data16", 0x01100119: "Data16s", 0x01100120: "R10",
    0x01100121: "R12", 0x01100122: "G10", 0x01100123: "G12", 0x01100124: "B10", 0x01100125: "B12",
    0x012000BD: "Coord3D_A32f", 0x012000BE: "Coord3D_B32f", 0x012000BF: "Coord3D_C32f",
    0x012000C8: "Confidence32f", 0x01200111: "Mono32", 0x0120011A: "Data32", 0x0120011B: "Data32s",
    0x0120011C: "Data32f", 0x0140011D: "Data64", 0x0140011E: "Data64s", 0x0140011F: "Data64f",
    0x020C001E: "YUV411_8_UYYVYY", 0x020C003C: "YCbCr411_8_CbYYCrYY", 0x020C003F: "YCbCr601_411_8_CbYYCrYY",
    0x020C0042: "YCbCr709_411_8_CbYYCrYY", 0x020C005A: "YCbCr411_8", 0x020C00F9: "YCbCr2020_411_8_CbYYCrYY",
    0x020C0112: "YCbCr420_8_YY_CbCr_Semiplanar", 0x020C0114: "YCbCr420_8_YY_CrCb_Semiplanar",
    0x0210001F: "YUV422_8_UYVY", 0x02100032: "YUV422_8", 0x02100035: "RGB565p", 0x02100036: "BGR565p",
    0x0210003B: "YCbCr422_8", 0x0210003E: "YCbCr601_422_8", 0x02100041: "YCbCr709_422_8",
    0x02100043: "YCbCr422_8_CbYCrY", 0x02100044: "YCbCr601_422_8_CbYCrY",
    0x02100045: "YCbCr709_422_8_CbYCrY", 0x021000A5: "BiColorRGBG8", 0x021000A6: "BiColorBGRG8",
    0x021000B4: "Coord3D_AC8", 0x021000B5: "Coord3D_AC8_Planar", 0x021000FA: "YCbCr2020_422_8",
    0x021000FB: "YCbCr2020_422_8_CbYCrY", 0x02100113: "YCbCr422_8_YY_CbCr_Semiplanar",
    0x02100115: "YCbCr422_8_YY_CrCb_Semiplanar", 0x02140087: "YCbCr422_10p", 0x0214008E: "YCbCr601_422_10p",
    0x02140096: "YCbCr709_422_10p", 0x0214009A: "YCbCr422_10p_CbYCrY", 0x0214009E: "YCbCr601_422_10p_CbYCrY",
    0x021400A2: "YCbCr709_422_10p_CbYCrY", 0x021400A8: "BiColorRGBG10p", 0x021400AA: "BiColorBGRG10p",
    0x021400F0: "Coord3D_AC10p", 0x021400F1: "Coord3D_AC10p_Planar", 0x021400FE: "YCbCr2020_422_10p",
    0x021400FF: "YCbCr2020_422_10p_CbYCrY", 0x02180014: "RGB8", 0x02180015: "BGR8", 0x02180020: "YUV8_UYV",
    0x02180021: "RGB8_Planar", 0x0218003A: "YCbCr8_CbYCr", 0x0218003D: "YCbCr601_8_CbYCr",
    0x02180040: "YCbCr709_8_CbYCr", 0x0218005B: "YCbCr8", 0x02180088: "YCbCr422_12p",
    0x02180090: "YCbCr601_422_12p", 0x02180098: "YCbCr709_422_12p", 0x0218009C: "YCbCr422_12p_CbYCrY",
    0x021800A0: "YCbCr601_422_12p_CbYCrY", 0x021800A4: "YCbCr709_422_12p_CbYCrY",
    0x021800AC: "BiColorRGBG12p", 0x021800AE: "BiColorBGRG12p", 0x021800B2: "Coord3D_ABC8",
    0x021800B3: "Coord3D_ABC8_Planar", 0x021800F2: "Coord3D_AC12p", 0x021800F3: "Coord3D_AC12p_Planar",
    0x021800F4: "YCbCr2020_8_CbYCr", 0x02180102: "YCbCr2020_422_12p", 0x02180103: "YCbCr2020_422_12p_CbYCrY",
    0x021E0048: "BGR10p", 0x021E005C: "RGB10p", 0x021E0084: "YCbCr10p_CbYCr",
    0x021E008A: "YCbCr601_10p_CbYCr", 0x021E0092: "YCbCr709_10p_CbYCr", 0x021E00DB: "Coord3D_ABC10p",
    0x021E00DC: "Coord3D_ABC10p_Planar", 0x021E00F6: "YCbCr2020_10p_CbYCr", 0x02200016: "RGBa8",
    0x02200017: "BGRa8", 0x0220001C: "GVSP_RGB10V1Packed", 0x0220001D: "RGB10p32", 0x02200065: "YCbCr422_10",
    0x02200066: "YCbCr422_12", 0x0220008D: "YCbCr601_422_10", 0x0220008F: "YCbCr601_422_12",
    0x02200095: "YCbCr709_422_10", 0x02200097: "YCbCr709_422_12", 0x02200099: "YCbCr422_10_CbYCrY",
    0x0220009B: "YCbCr422_12_CbYCrY", 0x0220009D: "YCbCr601_422_10_CbYCrY",
    0x0220009F: "YCbCr601_422_12_CbYCrY", 0x022000A1: "YCbCr709_422_10_CbYCrY",
    0x022000A3: "YCbCr709_422_12_CbYCrY", 0x022000A7: "BiColorRGBG10", 0x022000A9: "BiColorBGRG10",
    0x022000AB: "BiColorRGBG12", 0x022000AD: "BiColorBGRG12", 0x022000BB: "Coord3D_AC16",
    0x022000BC: "Coord3D_AC16_Planar", 0x022000FC: "YCbCr2020_422_10", 0x022000FD: "YCbCr2020_422_10_CbYCrY",
    0x02200100: "YCbCr2020_422_12", 0x02200101: "YCbCr2020_422_12_CbYCrY", 0x02240034: "GVSP_RGB12V1Packed",
    0x02240049: "BGR12p", 0x0224005D: "RGB12p", 0x02240086: "YCbCr12p_CbYCr",
    0x0224008C: "YCbCr601_12p_CbYCr", 0x02240094: "YCbCr709_12p_CbYCr", 0x022400DE: "Coord3D_ABC12p",
    0x022400DF: "Coord3D_ABC12p_Planar", 0x022400F8: "YCbCr2020_12p_CbYCr", 0x0228004D: "BGRa10p",
    0x02280060: "RGBa10p", 0x02300018: "RGB10", 0x02300019: "BGR10", 0x0230001A: "RGB12",
    0x0230001B: "BGR12", 0x02300022: "RGB10_Planar", 0x02300023: "RGB12_Planar", 0x02300024: "RGB16_Planar",
    0x02300033: "RGB16", 0x0230004A: "BGR14", 0x0230004B: "BGR16", 0x0230004F: "BGRa12p",
    0x0230005E: "RGB14", 0x02300062: "RGBa12p", 0x02300083: "YCbCr10_CbYCr", 0x02300085: "YCbCr12_CbYCr",
    0x02300089: "YCbCr601_10_CbYCr", 0x0230008B: "YCbCr601_12_CbYCr", 0x02300091: "YCbCr709_10_CbYCr",
    0x02300093: "YCbCr709_12_CbYCr", 0x023000B9: "Coord3D_ABC16", 0x023000BA: "Coord3D_ABC16_Planar",
    0x023000F5: "YCbCr2020_10_CbYCr", 0x023000F7: "YCbCr2020_12_CbYCr", 0x0240004C: "BGRa10",
    0x0240004E: "BGRa12", 0x02400050: "BGRa14", 0x02400051: "BGRa16", 0x0240005F: "RGBa10",
    0x02400061: "RGBa12", 0x02400063: "RGBa14", 0x02400064: "RGBa16", 0x024000C2: "Coord3D_AC32f",
    0x024000C3: "Coord3D_AC32f_Planar", 0x026000C0: "Coord3D_ABC32f", 0x026000C1: "Coord3D_ABC32f_Planar",
}
PFNC_CUSTOM_BIT = 0x80000000

# OpenCV names Bayer patterns by the 2x2 block starting at the 2nd row/col, so PFNC BayerRG
# (R at 0,0) decodes with COLOR_BayerBG2BGR (verified empirically for BayerRG8 in SkellyCam research).
OPENCV_BAYER_CODES: dict[str, str] = {
    "BayerRG": "cv2.COLOR_BayerBG2BGR", "BayerBG": "cv2.COLOR_BayerRG2BGR",
    "BayerGR": "cv2.COLOR_BayerGB2BGR", "BayerGB": "cv2.COLOR_BayerGR2BGR",
}


def pfnc_name(code: int) -> str:
    name = PFNC_NAMES.get(code)
    if name:
        return name
    if code & PFNC_CUSTOM_BIT:
        return f"custom(0x{code:08X})"
    return f"unknown(0x{code:08X})"


def pfnc_bits_per_pixel(code: int) -> int:
    """PFNC bits 16-23 hold the effective bits per pixel (e.g. 12 for Mono12p)."""
    return (code >> 16) & 0xFF


def opencv_bayer_hint(pixel_format_name: str) -> str:
    for prefix, code in OPENCV_BAYER_CODES.items():
        if pixel_format_name.startswith(prefix):
            return code
    return ""


def bits_set(value: int, table: list[tuple[str, int, str]]) -> list[str]:
    return [name for name, mask, _ in table if value & mask]


def gev_status_name(status: int) -> str:
    return GEV_STATUS.get(status, f"0x{status:04X}")


def ticks_to_ns(ticks: int, tick_hz: int) -> int:
    if tick_hz <= 0:
        return ticks
    return (ticks // tick_hz) * 1_000_000_000 + (ticks % tick_hz) * 1_000_000_000 // tick_hz


def ns_to_ticks(ns: int, tick_hz: int) -> int:
    if tick_hz <= 0:
        return ns
    return (ns // 1_000_000_000) * tick_hz + (ns % 1_000_000_000) * tick_hz // 1_000_000_000


def int_arg(text: str) -> int:
    """argparse type accepting 123, 0x7B, 0b1111011."""
    return int(text, 0)


# =============================================================================
# Reporting
# =============================================================================
PASS, FAIL, SKIP, WARN, INFO = "PASS", "FAIL", "SKIP", "WARN", "INFO"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""
    camera: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail, "camera": self.camera}


class Reporter:
    """Collects PASS/FAIL/SKIP/WARN/INFO results and prints them as they happen.

    Convention used by every script in this folder:
      PASS - the device supports the feature and it behaved as expected
      FAIL - the device claims support (or the test is mandatory) but it misbehaved
      SKIP - the device does not support / implement the feature, or a prerequisite failed
      WARN - works, but something looks off (e.g. capped socket buffer)
      INFO - a measurement or fact, no judgement
    """

    def __init__(self, title: str, quiet: bool = False) -> None:
        self.title = title
        self.quiet = quiet
        self.results: list[CheckResult] = []

    def add(self, name: str, status: str, detail: str = "", camera: str = "") -> CheckResult:
        res = CheckResult(name=name, status=status, detail=detail, camera=camera)
        self.results.append(res)
        if not self.quiet:
            where = f" [{camera}]" if camera else ""
            print(f"  [{status}]{where} {name}" + (f": {detail}" if detail else ""), flush=True)
        return res

    def check(self, name: str, ok: bool, detail: str = "", camera: str = "") -> bool:
        self.add(name, PASS if ok else FAIL, detail, camera)
        return ok

    def counts(self) -> dict[str, int]:
        c = Counter(r.status for r in self.results)
        return {s: c.get(s, 0) for s in (PASS, FAIL, SKIP, WARN, INFO)}

    def exit_code(self, strict: bool = False) -> int:
        c = self.counts()
        if c[FAIL] or (strict and c[SKIP]):
            return 1
        return 0

    def print_summary(self) -> None:
        c = self.counts()
        print(f"\n== {self.title}: {c[PASS]} passed, {c[FAIL]} failed, {c[SKIP]} skipped, "
              f"{c[WARN]} warnings, {c[INFO]} info")
        for r in self.results:
            if r.status in (FAIL, SKIP, WARN):
                where = f" [{r.camera}]" if r.camera else ""
                print(f"   {r.status}{where} {r.name}: {r.detail}")

    def as_list(self) -> list[dict[str, str]]:
        return [r.as_dict() for r in self.results]


def host_info() -> dict[str, str]:
    return {
        "python": sys.version.split()[0], "platform": platform.platform(), "machine": platform.machine(),
        "hostname": socket.gethostname(), "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def write_json(path: str, data: Any) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, default=str)
    print(f"wrote {path}")


# =============================================================================
# Small statistics helpers
# =============================================================================
def percentile(values: list[Number], p: Number) -> float:
    """Linear-interpolated percentile (p in 0..100) of a non-empty list."""
    xs = sorted(values)
    if not xs:
        raise ValueError("percentile of empty list")
    k = (len(xs) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return float(xs[lo] + (xs[hi] - xs[lo]) * (k - lo))


def linear_fit(xs: list[Number], ys: list[Number]) -> tuple[float, float]:
    """Least-squares (slope, intercept). Needs >= 2 distinct xs."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, float(my)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return float(slope), float(my - slope * mx)


def describe(values: list[Number]) -> dict[str, Number]:
    if not values:
        return {}
    return {"n": len(values), "min": min(values), "median": percentile(values, 50),
            "p95": percentile(values, 95), "max": max(values)}


# =============================================================================
# GVCP packet encode / decode (pure functions, covered by selftest)
# =============================================================================
def gvcp_command(command: int, payload: BytesLike = b"", req_id: int = 1, flags: int = FLAG_ACK_REQUIRED) -> bytes:
    """GVCP command header: key 0x42, flags, command, payload length, request id."""
    return struct.pack(">BBHHH", GVCP_KEY, flags & 0xFF, command, len(payload), req_id & 0xFFFF) + bytes(payload)


@dataclass
class GvcpAck:
    status: int
    answer: int
    length: int
    ack_id: int
    payload: bytes


def parse_gvcp_ack(data: BytesLike) -> GvcpAck:
    if len(data) < 8:
        raise ValueError(f"short GVCP ack ({len(data)} bytes)")
    status, answer, length, ack_id = struct.unpack_from(">HHHH", data, 0)
    return GvcpAck(status, answer, length, ack_id, bytes(data[8:8 + length]))


def build_discovery(req_id: int = 1, allow_broadcast_ack: bool = True) -> bytes:
    flags = FLAG_ACK_REQUIRED | (FLAG_DISCOVERY_ALLOW_BROADCAST_ACK if allow_broadcast_ack else 0)
    return gvcp_command(CMD_DISCOVERY, b"", req_id, flags)


def build_readreg(addresses: list[int], req_id: int = 1) -> bytes:
    return gvcp_command(CMD_READREG, b"".join(struct.pack(">I", a) for a in addresses), req_id)


def build_writereg(pairs: list[tuple[int, int]], req_id: int = 1) -> bytes:
    return gvcp_command(CMD_WRITEREG, b"".join(struct.pack(">II", a, v & 0xFFFFFFFF) for a, v in pairs), req_id)


def build_readmem(address: int, count: int, req_id: int = 1) -> bytes:
    return gvcp_command(CMD_READMEM, struct.pack(">IHH", address, 0, count), req_id)


def build_action_cmd(device_key: int, group_key: int, group_mask: int, action_time: Optional[int] = None,
                     req_id: int = 1, ack_required: bool = True) -> bytes:
    """ACTION_CMD 0x0100 (packet-gvcp.c dissect_action_cmd): device_key, group_key, group_mask
    [, u64 action_time in device timestamp ticks when flag 0x80 'scheduled' is set]."""
    flags = FLAG_ACK_REQUIRED if ack_required else 0
    payload = struct.pack(">III", device_key & 0xFFFFFFFF, group_key & 0xFFFFFFFF, group_mask & 0xFFFFFFFF)
    if action_time is not None:
        flags |= FLAG_SCHEDULED_ACTION
        payload += struct.pack(">Q", action_time & 0xFFFFFFFFFFFFFFFF)
    return gvcp_command(CMD_ACTION, payload, req_id, flags)


def build_packetresend(block_id: int, first_packet: int, last_packet: int, req_id: int = 1,
                       extended_ids: bool = False, channel: int = 0) -> bytes:
    """PACKETRESEND_CMD 0x0040. Standard ids: u16 channel, u16 block id, u32 first/last (24-bit ids).
    Extended ids (header flag 0x10): u16 channel, u16 reserved, u32 first, u32 last, u64 block id.
    Sent without ACK_REQUIRED (the camera answers with resent GVSP packets, like Aravis)."""
    if extended_ids:
        payload = struct.pack(">HHIIQ", channel, 0, first_packet, last_packet, block_id)
        return gvcp_command(CMD_PACKETRESEND, payload, req_id, FLAG_EXTENDED_IDS)
    payload = struct.pack(">HHII", channel, block_id & 0xFFFF, first_packet & 0xFFFFFF, last_packet & 0xFFFFFF)
    return gvcp_command(CMD_PACKETRESEND, payload, req_id, 0)


def _cstr(b: BytesLike) -> str:
    return bytes(b).split(b"\0", 1)[0].decode("ascii", "replace").strip()


def parse_discovery_ack(p: BytesLike, src: str = "") -> dict[str, Any]:
    """DISCOVERY_ACK payload (248 bytes), offsets per packet-gvcp.c dissect_discovery_ack."""
    if len(p) < 0xF8:
        raise ValueError(f"short DISCOVERY_ACK payload ({len(p)} bytes)")
    ver = struct.unpack_from(">I", p, 0)[0]
    mode = struct.unpack_from(">I", p, 4)[0]
    return {
        "src": src, "gev_version": f"{ver >> 16}.{ver & 0xFFFF}", "gev_major": ver >> 16, "gev_minor": ver & 0xFFFF,
        "device_mode": f"0x{mode:08X}", "mac": ":".join(f"{b:02X}" for b in bytes(p[10:16])),
        "ip_config_options": f"0x{struct.unpack_from('>I', p, 16)[0]:08X}",
        "ip_config_current": f"0x{struct.unpack_from('>I', p, 20)[0]:08X}",
        "ip": socket.inet_ntoa(bytes(p[36:40])), "subnet_mask": socket.inet_ntoa(bytes(p[52:56])),
        "gateway": socket.inet_ntoa(bytes(p[68:72])),
        "manufacturer": _cstr(p[72:104]), "model": _cstr(p[104:136]), "device_version": _cstr(p[136:168]),
        "manufacturer_info": _cstr(p[168:216]), "serial": _cstr(p[216:232]), "user_name": _cstr(p[232:248]),
    }


def build_discovery_ack_payload(ip: str, mac: bytes, manufacturer: str, model: str, serial: str,
                                gev_major: int = 2, gev_minor: int = 0) -> bytes:
    """Synthetic DISCOVERY_ACK payload, used by the selftest."""
    p = bytearray(0xF8)
    struct.pack_into(">HH", p, 0, gev_major, gev_minor)
    p[10:16] = mac
    p[36:40] = socket.inet_aton(ip)
    p[52:56] = socket.inet_aton("255.255.0.0")
    p[72:72 + len(manufacturer)] = manufacturer.encode()
    p[104:104 + len(model)] = model.encode()
    p[216:216 + len(serial)] = serial.encode()
    return bytes(p)


# =============================================================================
# GVSP encode / decode
# =============================================================================
def parse_gvsp_header(buf: BytesLike, n: int) -> Optional[tuple[int, int, int, int, bool, int, int]]:
    """Return (status, block_id, packet_format, packet_id, extended_ids, flags, header_len) or None.

    Standard header (8 B): status u16 | block_id u16 | EI(1)+res(3)+format(4) u8 | packet_id u24
    Extended-ID header (20 B, GEV 2.0+, used by GEV 3.0 'GVSP v2'):
        status u16 | flags u16 | EI=1 + format u8 | reserved u24 | block_id u64 | packet_id u32
    """
    if n < 8:
        return None
    status, word1, infos = struct.unpack_from(">HHI", buf, 0)
    fmt_byte = infos >> 24
    fmt = fmt_byte & 0x0F
    if fmt not in PACKET_FORMATS:
        return None
    if fmt_byte & GVSP_EI_BIT:
        if n < 20:
            return None
        block_id, packet_id = struct.unpack_from(">QI", buf, 8)
        return status, block_id, fmt, packet_id, True, word1, 20
    return status, word1, fmt, infos & 0x00FFFFFF, False, 0, 8


def parse_gvsp_leader(d: BytesLike) -> dict[str, Any]:
    """Leader body after the GVSP header. Image leader: reserved u16, payload type u16, timestamp u64,
    pixel format u32, size x/y u32, offset x/y u32, padding x/y u16 (36 bytes)."""
    info: dict[str, Any] = {}
    if len(d) < 4:
        return info
    ptype_raw = struct.unpack_from(">H", d, 2)[0]
    ptype = ptype_raw & 0x3FFF
    info.update(payload_type=ptype, payload_type_name=PAYLOAD_TYPES.get(ptype, f"0x{ptype:04X}"),
                chunk=bool(ptype_raw & PAYLOAD_TYPE_CHUNK_BIT))
    if ptype == PT_H264:
        if len(d) >= 12:
            info["payload_size"] = struct.unpack_from(">Q", d, 4)[0]
        return info  # the H.264 leader has no timestamp at offset 4
    if len(d) >= 12:
        info["timestamp"] = struct.unpack_from(">Q", d, 4)[0]
    if ptype in (PT_IMAGE, 0x0005, PT_MULTIZONE) and len(d) >= 32:
        pf, sx, sy, ox, oy = struct.unpack_from(">IIIII", d, 12)
        info.update(pixel_format=pf, pixel_format_name=pfnc_name(pf), size_x=sx, size_y=sy, offset_x=ox, offset_y=oy)
        if len(d) >= 36:
            info["padding_x"], info["padding_y"] = struct.unpack_from(">HH", d, 32)
    elif ptype in (PT_JPEG, PT_JPEG2000) and len(d) >= 32:
        info["payload_size"], info["tick_frequency"], info["data_format"] = struct.unpack_from(">QQI", d, 12)
    return info


def parse_gvsp_trailer(d: BytesLike) -> dict[str, Any]:
    info: dict[str, Any] = {}
    if len(d) >= 4:
        info["payload_type"] = struct.unpack_from(">H", d, 2)[0] & 0x3FFF
    if len(d) >= 8:
        info["size_y"] = struct.unpack_from(">I", d, 4)[0]
    return info


def build_gvsp_header(block_id: int, packet_format: int, packet_id: int, extended_ids: bool = False,
                      status: int = 0, flags: int = 0) -> bytes:
    if extended_ids:
        return struct.pack(">HHIQI", status, flags, (GVSP_EI_BIT | packet_format) << 24, block_id, packet_id)
    return struct.pack(">HHI", status, block_id & 0xFFFF, (packet_format << 24) | (packet_id & 0xFFFFFF))


def build_gvsp_image_leader(block_id: int, timestamp: int, pixel_format: int, width: int, height: int,
                            extended_ids: bool = False, payload_type: int = PT_IMAGE) -> bytes:
    body = struct.pack(">HHQIIIIIHH", 0, payload_type, timestamp, pixel_format, width, height, 0, 0, 0, 0)
    return build_gvsp_header(block_id, FMT_LEADER, 0, extended_ids) + body


def build_gvsp_payload(block_id: int, packet_id: int, data: bytes, extended_ids: bool = False,
                       status: int = 0, flags: int = 0) -> bytes:
    return build_gvsp_header(block_id, FMT_PAYLOAD, packet_id, extended_ids, status, flags) + data


def build_gvsp_trailer(block_id: int, packet_id: int, height: int, extended_ids: bool = False,
                       payload_type: int = PT_IMAGE) -> bytes:
    return build_gvsp_header(block_id, FMT_TRAILER, packet_id, extended_ids) + struct.pack(">HHI", 0, payload_type, height)


def synth_gvsp_frame(block_id: int, timestamp: int, pixel_format: int, width: int, height: int,
                     packet_payload: int, extended_ids: bool = False, drop: Optional[set[int]] = None,
                     payload_type: int = PT_IMAGE, payload_bytes: Optional[int] = None) -> list[bytes]:
    """Synthetic GVSP packets for one frame (leader, payload packets, trailer). Selftest helper."""
    total = payload_bytes if payload_bytes is not None else width * height * pfnc_bits_per_pixel(pixel_format) // 8
    n_data = (total + packet_payload - 1) // packet_payload
    pkts = [build_gvsp_image_leader(block_id, timestamp, pixel_format, width, height, extended_ids, payload_type)]
    for pid in range(1, n_data + 1):
        size = min(packet_payload, total - (pid - 1) * packet_payload)
        if drop and pid in drop:
            continue
        pkts.append(build_gvsp_payload(block_id, pid, bytes(size), extended_ids))
    pkts.append(build_gvsp_trailer(block_id, n_data + 1, height, extended_ids, payload_type))
    return pkts


# =============================================================================
# GVSP stream analyser (used for pcap files and live capture)
# =============================================================================
class _Block:
    __slots__ = ("block_id", "t_first", "t_last", "leader", "trailer", "trailer_pid", "pids", "data_bytes",
                 "resend_ranges", "resent_packets", "t_trailer", "requested", "recovered")

    def __init__(self, block_id: int, t: Number) -> None:
        self.block_id = block_id
        self.t_first = t
        self.t_last = t
        self.leader: Optional[dict[str, Any]] = None
        self.trailer: Optional[dict[str, Any]] = None
        self.trailer_pid: Optional[int] = None
        self.pids: set[int] = set()
        self.data_bytes = 0
        self.resend_ranges = 0
        self.resent_packets = 0
        self.t_trailer = 0.0
        self.requested: set[int] = set()  # packet ids asked for with PACKETRESEND
        self.recovered = 0  # requested packet ids that arrived afterwards


class GvspAnalyzer:
    """Accumulates the GVSP packets of ONE stream and summarises them.

    A block (frame) is complete when its leader, its trailer and every payload packet between them
    (packet ids 1 .. trailer_id-1) arrived, so PayloadSize / GenApi is not needed.
    """

    def __init__(self, extended_ids_expected: Optional[bool] = None) -> None:
        self.open: dict[int, _Block] = {}
        self.recently_closed: deque[int] = deque(maxlen=256)
        self.closed: list[dict[str, Any]] = []
        self.packets = 0
        self.bytes = 0
        self.formats: Counter[str] = Counter()
        self.statuses: Counter[int] = Counter()
        self.ei_packets = 0
        self.resent_packets = 0
        self.late_packets = 0
        self.packet_sizes: Counter[int] = Counter()  # IP datagram size of PAYLOAD packets (= SCPS packet size)
        self.max_packet_size = 0
        self.leaders: list[dict[str, Any]] = []
        self.not_gvsp = 0
        self.extended_ids_expected = extended_ids_expected

    def feed(self, buf: BytesLike, n: int, t: Number, ip_size: Optional[int] = None,
             wire_len: Optional[int] = None) -> Optional[tuple[int, int, int, int, bool, int, int]]:
        """Account one GVSP datagram. `n` = bytes available in `buf`; `wire_len` = true UDP payload length
        when a capture was truncated by its snaplen (headers are all that is needed)."""
        hdr = parse_gvsp_header(buf, n)
        if hdr is None:
            self.not_gvsp += 1
            return None
        status, block_id, fmt, pid, ei, flags, hlen = hdr
        n_true = wire_len if wire_len is not None else n
        self.packets += 1
        self.bytes += n_true
        self.formats[PACKET_FORMATS[fmt]] += 1
        self.statuses[status] += 1
        if ei:
            self.ei_packets += 1
        resent = status == 0x0100 or (ei and bool(flags & 0x0001))
        if resent:
            self.resent_packets += 1
        size = ip_size if ip_size is not None else n_true + IP_UDP_OVERHEAD
        if size > self.max_packet_size:
            self.max_packet_size = size
        blk = self.open.get(block_id)
        if blk is None:
            if block_id in self.recently_closed:
                self.late_packets += 1
                return hdr
            blk = self.open[block_id] = _Block(block_id, t)
        blk.t_last = t
        if resent:
            blk.resent_packets += 1
        if fmt == FMT_LEADER:
            blk.leader = parse_gvsp_leader(memoryview(buf)[hlen:n])
            blk.leader["t_host"] = t
            if len(self.leaders) < 500_000:
                self.leaders.append(dict(blk.leader, block_id=block_id))
        elif fmt == FMT_TRAILER:
            blk.trailer = parse_gvsp_trailer(memoryview(buf)[hlen:n])
            blk.trailer_pid = pid
            blk.t_trailer = t
        elif fmt == FMT_ALL_IN:  # leader + payload + trailer in one packet
            blk.leader = blk.leader or {"payload_type_name": "ALL_IN"}
            blk.trailer, blk.trailer_pid, blk.t_trailer = {}, 1, t
            blk.data_bytes += n_true - hlen
        else:
            if pid not in blk.pids:
                blk.pids.add(pid)
                blk.data_bytes += n_true - hlen
                if pid in blk.requested:
                    blk.recovered += 1
            self.packet_sizes[size] += 1
        return hdr

    def missing_ids(self, block_id: int) -> list[int]:
        blk = self.open.get(block_id)
        if blk is None or blk.trailer_pid is None:
            return []
        return [i for i in range(1, blk.trailer_pid) if i not in blk.pids]

    def mark_resend_requested(self, block_id: int, ranges: list[tuple[int, int]]) -> None:
        blk = self.open.get(block_id)
        if blk is not None:
            blk.resend_ranges += len(ranges)
            for first, last in ranges:
                blk.requested.update(range(first, last + 1))

    @staticmethod
    def ranges(ids: list[int]) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for i in sorted(ids):
            if out and i == out[-1][1] + 1:
                out[-1] = (out[-1][0], i)
            else:
                out.append((i, i))
        return out

    def close(self, block_id: int) -> dict[str, Any]:
        blk = self.open.pop(block_id)
        self.recently_closed.append(block_id)
        missing: Optional[int] = None
        if blk.trailer_pid is None:
            state = "trailer_missing"
        else:
            missing = len([i for i in range(1, blk.trailer_pid) if i not in blk.pids])
            if missing:
                state = "incomplete"
            else:
                state = "complete" if blk.leader is not None else "leader_missing"
        summary = {"block_id": block_id, "state": state, "missing_packets": missing,
                   "data_packets": len(blk.pids), "data_bytes": blk.data_bytes, "t_first": blk.t_first,
                   "t_last": blk.t_last, "resend_ranges": blk.resend_ranges, "resent_packets": blk.resent_packets,
                   "resend_packets_requested": len(blk.requested), "resend_packets_recovered": blk.recovered,
                   "leader": blk.leader}
        self.closed.append(summary)
        return summary

    def due_for_close(self, now: Number, trailer_grace_s: Number, no_trailer_timeout_s: Number) -> list[int]:
        out = []
        for bid, blk in self.open.items():
            if blk.trailer_pid is not None and now - blk.t_trailer >= trailer_grace_s:
                out.append(bid)
            elif blk.trailer_pid is None and now - blk.t_last >= no_trailer_timeout_s:
                out.append(bid)
        return out

    def finish(self) -> None:
        for bid in sorted(self.open, key=lambda b: self.open[b].t_first):
            self.close(bid)

    def block_gaps(self) -> int:
        """Blocks never seen at all (gaps in the block-id sequence of closed blocks, arrival order)."""
        ids = [c["block_id"] for c in sorted(self.closed, key=lambda c: c["t_first"])]
        gaps = 0
        for a, b in zip(ids, ids[1:]):
            if self.ei_packets:
                d = b - a - 1
            else:  # 16-bit ids wrap 65535 -> 1 (0 is not used)
                d = (b - a - 1) % 0xFFFF if b < a else b - a - 1
            if 0 < d < 10_000:
                gaps += d
        return gaps

    def summary(self, tick_hz: int = 0) -> dict[str, Any]:
        states = Counter(c["state"] for c in self.closed)
        complete = [c for c in self.closed if c["state"] == "complete"]
        gaps = self.block_gaps()
        n_frames = len(self.closed) + gaps  # frames never seen at all count as lost
        s: dict[str, Any] = {
            "packets": self.packets, "bytes": self.bytes, "packet_formats": dict(self.formats),
            "status_codes": {gev_status_name(k): v for k, v in self.statuses.items()},
            "extended_id_packets": self.ei_packets,
            "extended_ids_used": bool(self.packets and self.ei_packets == self.packets),
            "resent_packets_received": self.resent_packets, "late_packets_after_close": self.late_packets,
            "frames_seen": len(self.closed), "frames_complete": states.get("complete", 0),
            "frames_incomplete": states.get("incomplete", 0), "frames_trailer_missing": states.get("trailer_missing", 0),
            "frames_leader_missing": states.get("leader_missing", 0),
            "missing_packets_total": sum(c["missing_packets"] or 0 for c in self.closed),
            "block_id_gaps": gaps,
            "completeness": (states.get("complete", 0) / n_frames) if n_frames else 0.0,
            "resend_ranges_requested": sum(c["resend_ranges"] for c in self.closed),
            "resend_packets_requested": sum(c["resend_packets_requested"] for c in self.closed),
            "resend_packets_recovered": sum(c["resend_packets_recovered"] for c in self.closed),
            "max_ip_packet_size": self.max_packet_size,
            "payload_packet_ip_size_most_common": self.packet_sizes.most_common(1)[0][0] if self.packet_sizes else None,
            "non_gvsp_datagrams": self.not_gvsp,
        }
        common = s["payload_packet_ip_size_most_common"] or self.max_packet_size
        s["jumbo_frames"] = bool(common and common > 1500)
        ptypes = Counter(L.get("payload_type_name", "?") for L in self.leaders)
        s["payload_types"] = dict(ptypes)
        s["chunk_data"] = any(L.get("chunk") for L in self.leaders)
        fmts = Counter((L.get("pixel_format_name"), L.get("size_x"), L.get("size_y")) for L in self.leaders
                       if "pixel_format" in L)
        s["pixel_formats"] = [{"pixel_format": k[0], "width": k[1], "height": k[2], "frames": v,
                               "opencv_bayer_code": opencv_bayer_hint(k[0] or "")} for k, v in fmts.items()]
        if complete:
            sizes = [c["data_bytes"] for c in complete]
            s["data_bytes_per_complete_frame_median"] = percentile(sizes, 50)
        expected = None
        for L in self.leaders:
            if "pixel_format" in L and not (L["pixel_format"] & PFNC_CUSTOM_BIT):
                expected = (L["size_x"] * pfnc_bits_per_pixel(L["pixel_format"]) // 8 + L.get("padding_x", 0)) * L["size_y"]
                break
        s["uncompressed_frame_bytes_expected"] = expected
        ts = [L["timestamp"] for L in self.leaders if "timestamp" in L]
        if len(ts) >= 3:
            deltas = [b - a for a, b in zip(ts, ts[1:])]
            s["leader_timestamp_delta_ticks"] = describe([float(d) for d in deltas])
            s["leader_timestamp_first"] = ts[0]
            s["leader_timestamp_monotonic"] = all(d > 0 for d in deltas)
            if tick_hz:
                med = percentile([float(d) for d in deltas], 50)
                s["device_fps_from_timestamps"] = tick_hz / med if med > 0 else None
                s["leader_timestamp_delta_us"] = {k: (v * 1e6 / tick_hz if k != "n" else v)
                                                  for k, v in s["leader_timestamp_delta_ticks"].items()}
        if len(self.leaders) >= 2:
            th = [L["t_host"] for L in self.leaders]
            span = th[-1] - th[0]
            s["host_fps"] = (len(th) - 1) / span if span > 0 else None
        verdict, reasons = compression_verdict(s)
        s["compression_verdict"] = verdict
        s["compression_reasons"] = reasons
        return s


def compression_verdict(s: dict[str, Any]) -> tuple[str, list[str]]:
    """Answer 'raw or compressed?' from an analyser summary."""
    reasons: list[str] = []
    ptypes = set(s.get("payload_types", {}))
    if not ptypes:
        return "UNKNOWN", ["no GVSP leader packets were seen"]
    comp = [p for p in ptypes if p in ("JPEG", "JPEG2000", "H264")]
    if comp:
        return "COMPRESSED", [f"standard GVSP compressed payload type(s): {', '.join(sorted(comp))}"]
    vendor = [p for p in ptypes if p.startswith("0x")]
    if vendor:
        reasons.append(f"device-specific payload type(s) {', '.join(sorted(vendor))}: contents unknown, may be compressed")
        return "VENDOR-SPECIFIC", reasons
    if ptypes & {"MULTIPART", "GENDC"}:
        return "CONTAINER", ["multipart/GenDC container payload: parts not analysed (may hold JPEG parts)"]
    custom = [p["pixel_format"] for p in s.get("pixel_formats", []) if str(p["pixel_format"]).startswith("custom")]
    if custom:
        return "LIKELY-COMPRESSED", [f"IMAGE payload with vendor-specific (custom, bit 31) pixel format(s) {custom}: "
                                     "vendor compression formats such as LUCID QOI_* or packed vendor formats look like this"]
    expected = s.get("uncompressed_frame_bytes_expected")
    measured = s.get("data_bytes_per_complete_frame_median")
    fmts = ", ".join(sorted({str(p["pixel_format"]) for p in s.get("pixel_formats", [])}))
    if expected and measured:
        ratio = measured / expected
        reasons.append(f"payload bytes/frame {measured:.0f} vs uncompressed {fmts} size {expected} (ratio {ratio:.3f})")
        if ratio < 0.9:
            return "LIKELY-COMPRESSED", reasons + ["frames are smaller than the raw pixel format implies"]
        return "UNCOMPRESSED", reasons + ["IMAGE payload in a standard PFNC pixel format, full-size frames"]
    reasons.append(f"IMAGE payload in standard PFNC pixel format(s) {fmts} (no complete frame to size-check)")
    return "UNCOMPRESSED", reasons


# =============================================================================
# pcap / pcapng
# =============================================================================
LINKTYPE_NULL, LINKTYPE_ETHERNET, LINKTYPE_RAW, LINKTYPE_LOOP = 0, 1, 101, 108
LINKTYPE_LINUX_SLL, LINKTYPE_LINUX_SLL2 = 113, 276


def iter_capture(path: str) -> Iterator[tuple[float, int, bytes, int]]:
    """Yield (timestamp_s, linktype, captured_frame_bytes, original_length) from a pcap or pcapng file,
    streaming (captures of several GB are fine)."""
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d"):
            e = "<" if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
            nano = magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
            rest = f.read(20)
            linktype = struct.unpack(e + "I", rest[16:20])[0] & 0x0FFFFFFF
            while True:
                rec = f.read(16)
                if len(rec) < 16:
                    return
                sec, frac, incl, orig = struct.unpack(e + "IIII", rec)
                data = f.read(incl)
                if len(data) < incl:
                    return
                yield sec + frac / (1e9 if nano else 1e6), linktype, data, orig
        elif magic == b"\x0a\x0d\x0d\x0a":
            f.seek(0)
            e = "<"
            links: list[int] = []
            resol: list[float] = []
            while True:
                head = f.read(8)
                if len(head) < 8:
                    return
                btype = struct.unpack("<I", head[:4])[0]
                if btype == 0x0A0D0D0A:
                    bom = f.read(4)
                    e = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
                    blen = struct.unpack(e + "I", head[4:8])[0]
                    f.read(blen - 12)
                    links, resol = [], []
                    continue
                btype = struct.unpack(e + "I", head[:4])[0]
                blen = struct.unpack(e + "I", head[4:8])[0]
                if blen < 12:
                    return
                body = f.read(blen - 8)
                if len(body) < blen - 8:
                    return
                body = body[:-4]
                if btype == 1:  # Interface Description Block
                    links.append(struct.unpack(e + "H", body[0:2])[0])
                    res = 1e-6
                    o = 8
                    while o + 4 <= len(body):
                        code, ln = struct.unpack(e + "HH", body[o:o + 4])
                        if code == 0:
                            break
                        if code == 9 and ln >= 1:
                            v = body[o + 4]
                            res = 2.0 ** -(v & 0x7F) if v & 0x80 else 10.0 ** -v
                        o += 4 + ((ln + 3) & ~3)
                    resol.append(res)
                elif btype == 6 and links:  # Enhanced Packet Block
                    ifid, th, tl, cap, orig = struct.unpack(e + "IIIII", body[:20])
                    yield ((th << 32) | tl) * resol[ifid], links[ifid], body[20:20 + cap], orig
                elif btype == 3 and links:  # Simple Packet Block
                    orig = struct.unpack(e + "I", body[:4])[0]
                    yield 0.0, links[0], body[4:4 + orig], orig
        else:
            raise ValueError(f"{path}: not a pcap or pcapng file (magic {magic.hex()})")


@dataclass
class UdpDatagram:
    src: str
    sport: int
    dst: str
    dport: int
    payload: bytes  # as captured (may be truncated by the capture snaplen)
    udp_payload_len: int  # from the UDP header (true size even if truncated)
    ip_total_len: int
    fragment: bool


def extract_udp(linktype: int, frame: bytes) -> Optional[UdpDatagram]:
    if linktype == LINKTYPE_ETHERNET:
        if len(frame) < 14:
            return None
        etype, off = struct.unpack(">H", frame[12:14])[0], 14
        while etype in (0x8100, 0x88A8) and len(frame) >= off + 4:
            etype, off = struct.unpack(">H", frame[off + 2:off + 4])[0], off + 4
        if etype != 0x0800:
            return None
    elif linktype == LINKTYPE_LINUX_SLL:
        if len(frame) < 16 or struct.unpack(">H", frame[14:16])[0] != 0x0800:
            return None
        off = 16
    elif linktype == LINKTYPE_LINUX_SLL2:
        if len(frame) < 20 or struct.unpack(">H", frame[0:2])[0] != 0x0800:
            return None
        off = 20
    elif linktype in (LINKTYPE_NULL, LINKTYPE_LOOP):
        off = 4
    elif linktype in (LINKTYPE_RAW, 228):
        off = 0
    else:
        return None
    ip = frame[off:]
    if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 17:
        return None
    ihl = (ip[0] & 0x0F) * 4
    total_len = struct.unpack(">H", ip[2:4])[0]
    frag = struct.unpack(">H", ip[6:8])[0]
    fragment = bool(frag & 0x1FFF) or bool(frag & 0x2000)
    if frag & 0x1FFF:  # non-first fragment: no UDP header
        return UdpDatagram(socket.inet_ntoa(ip[12:16]), 0, socket.inet_ntoa(ip[16:20]), 0, b"", 0, total_len, True)
    if len(ip) < ihl + 8:
        return None
    sport, dport, ulen = struct.unpack(">HHH", ip[ihl:ihl + 6])
    return UdpDatagram(socket.inet_ntoa(ip[12:16]), sport, socket.inet_ntoa(ip[16:20]), dport,
                       bytes(ip[ihl + 8:ihl + ulen]), max(0, ulen - 8), total_len, fragment)


def _ipv4_udp_packet(src: str, sport: int, dst: str, dport: int, payload: bytes, ident: int) -> bytes:
    def csum(b: bytes) -> int:
        if len(b) % 2:
            b += b"\0"
        s = sum(struct.unpack(f">{len(b) // 2}H", b))
        while s >> 16:
            s = (s & 0xFFFF) + (s >> 16)
        return (~s) & 0xFFFF
    udp = struct.pack(">HHHH", sport, dport, 8 + len(payload), 0) + payload
    ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), ident & 0xFFFF, 0x4000, 64, 17, 0,
                     socket.inet_aton(src), socket.inet_aton(dst))
    return ip[:10] + struct.pack(">H", csum(ip)) + ip[12:] + udp


def write_pcap(path: str, datagrams: list[tuple[str, int, str, int, bytes]], t0: Number = 1_700_000_000.0,
               dt: Number = 0.0001) -> None:
    """Classic pcap, LINKTYPE_RAW (IPv4), microsecond timestamps."""
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, LINKTYPE_RAW))
        for i, (src, sport, dst, dport, payload) in enumerate(datagrams):
            pkt = _ipv4_udp_packet(src, sport, dst, dport, payload, i)
            t = t0 + i * dt
            f.write(struct.pack("<IIII", int(t), int(round((t - int(t)) * 1e6)) % 1_000_000, len(pkt), len(pkt)) + pkt)


def write_pcapng_ethernet(path: str, datagrams: list[tuple[str, int, str, int, bytes]], snaplen: int = 0) -> None:
    """Minimal pcapng (SHB + IDB + EPBs), Ethernet link type, optional snaplen truncation. Selftest helper."""
    def block(btype: int, body: bytes) -> bytes:
        body += b"\0" * ((4 - len(body) % 4) % 4)
        n = 12 + len(body)
        return struct.pack("<II", btype, n) + body + struct.pack("<I", n)
    with open(path, "wb") as f:
        f.write(block(0x0A0D0D0A, struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1)))
        f.write(block(1, struct.pack("<HHI", LINKTYPE_ETHERNET, 0, snaplen)))
        for i, (src, sport, dst, dport, payload) in enumerate(datagrams):
            frame = b"\x02" * 6 + b"\x04" * 6 + b"\x08\x00" + _ipv4_udp_packet(src, sport, dst, dport, payload, i)
            cap = frame[:snaplen] if snaplen else frame
            ts = 1_700_000_000_000_000 + i * 100
            f.write(block(6, struct.pack("<IIIII", 0, ts >> 32, ts & 0xFFFFFFFF, len(cap), len(frame)) + cap))


# =============================================================================
# Host network interfaces
# =============================================================================
@dataclass
class Ipv4Interface:
    name: str
    ip: str
    prefix_len: int

    @property
    def network(self) -> ipaddress.IPv4Network:
        return ipaddress.IPv4Network(f"{self.ip}/{self.prefix_len}", strict=False)

    @property
    def broadcast(self) -> str:
        return str(self.network.broadcast_address)

    def contains(self, ip: str) -> bool:
        try:
            return ipaddress.IPv4Address(ip) in self.network
        except ValueError:
            return False

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ip": self.ip, "prefix_len": self.prefix_len, "broadcast": self.broadcast}


def _run(cmd: list[str], timeout: Number = 10.0) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _mask_to_prefix(mask: str) -> int:
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
    except ValueError:
        return 24


def list_ipv4_interfaces(include_loopback: bool = False) -> list[Ipv4Interface]:
    """Best-effort list of the host's IPv4 interfaces, standard library only.
    Linux: ioctl(SIOCGIFADDR/SIOCGIFNETMASK); macOS/BSD: `ifconfig`; Windows: PowerShell Get-NetIPAddress.
    Falls back to the addresses of the host name (with a guessed /16 for 169.254.x.x, else /24)."""
    found: list[Ipv4Interface] = []
    system = platform.system()
    if system == "Linux":
        try:
            import fcntl  # noqa: PLC0415 - POSIX only
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                for _, name in socket.if_nameindex():
                    req = struct.pack("256s", name.encode()[:15])
                    try:
                        ip = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, req)[20:24])
                        mask = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x891B, req)[20:24])
                    except OSError:
                        continue
                    found.append(Ipv4Interface(name, ip, _mask_to_prefix(mask)))
            finally:
                s.close()
        except (ImportError, OSError):
            pass
    elif system == "Windows":
        out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias,IPAddress,PrefixLength "
                    "| ConvertTo-Json -Compress"], timeout=20.0)
        try:
            rows = json.loads(out) if out.strip() else []
            for row in rows if isinstance(rows, list) else [rows]:
                found.append(Ipv4Interface(str(row.get("InterfaceAlias", "")), str(row["IPAddress"]),
                                           int(row.get("PrefixLength", 24))))
        except (ValueError, KeyError, TypeError):
            pass
    else:
        name = ""
        for line in _run(["ifconfig"]).splitlines():
            m = re.match(r"^(\S+?):? ", line)
            if m and not line.startswith(("\t", " ")):
                name = m.group(1)
            m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)\s+netmask\s+(0x[0-9a-fA-F]+|\d+\.\d+\.\d+\.\d+)", line)
            if m:
                mask = m.group(2)
                if mask.startswith("0x"):
                    mask = socket.inet_ntoa(struct.pack(">I", int(mask, 16)))
                found.append(Ipv4Interface(name, m.group(1), _mask_to_prefix(mask)))
    if not found:
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = str(info[4][0])
                found.append(Ipv4Interface("?", ip, 16 if ip.startswith("169.254.") else 24))
        except OSError:
            pass
    out_list: list[Ipv4Interface] = []
    seen: set[str] = set()
    for itf in found:
        if itf.ip in seen or itf.ip.startswith("0."):
            continue
        if itf.ip.startswith("127.") and not include_loopback:
            continue
        seen.add(itf.ip)
        out_list.append(itf)
    if include_loopback and not any(i.ip.startswith("127.") for i in out_list):
        out_list.append(Ipv4Interface("loopback", "127.0.0.1", 8))
    return out_list


def interface_for_ip(ip: str, interfaces: list[Ipv4Interface]) -> Optional[Ipv4Interface]:
    for itf in interfaces:
        if itf.contains(ip):
            return itf
    return None


def broadcast_for(local_ip: str, camera_ip: str) -> str:
    """Subnet broadcast address of the host interface that owns `local_ip` (the NIC the OS routes camera
    traffic through), falling back to the interface whose subnet holds the camera, then 255.255.255.255.
    With several NICs on 169.254.0.0/16 only the first rule picks the right one."""
    interfaces = list_ipv4_interfaces(include_loopback=True)
    itf = next((i for i in interfaces if i.ip == local_ip), None) or interface_for_ip(camera_ip, interfaces)
    return itf.broadcast if itf else "255.255.255.255"


def local_ip_towards(ip: str) -> str:
    """The host IP the OS would use to reach `ip` (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((ip, GVCP_PORT))
        return str(s.getsockname()[0])
    except OSError:
        return ""
    finally:
        s.close()


# =============================================================================
# Discovery
# =============================================================================
def discover_devices(timeout: Number = 1.5, targets: Optional[list[str]] = None,
                     iface_ips: Optional[list[str]] = None, include_loopback: bool = False) -> list[dict[str, Any]]:
    """GVCP DISCOVERY. With `targets`, unicast to each IP. Otherwise broadcast on every IPv4 interface:
    to each interface's subnet broadcast and to 255.255.255.255, from a 0.0.0.0-bound socket (receives
    broadcast replies from cameras on a foreign subnet) and from one socket bound per interface."""
    interfaces = list_ipv4_interfaces(include_loopback=include_loopback)
    if iface_ips:
        interfaces = [i for i in interfaces if i.ip in iface_ips] or [Ipv4Interface("user", ip, 24) for ip in iface_ips]
    socks: list[tuple[socket.socket, str]] = []

    def new_sock(bind_ip: str) -> Optional[socket.socket]:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((bind_ip, 0))
        except OSError:
            s.close()
            return None
        s.setblocking(False)
        socks.append((s, bind_ip))
        return s

    pkt = build_discovery(req_id=0xFFFF)

    def send(s: socket.socket, dst: str) -> None:
        try:
            s.sendto(pkt, (dst, GVCP_PORT))
        except OSError:
            pass

    if targets:
        s_any = new_sock(iface_ips[0] if iface_ips else "")
        if s_any is not None:
            for t in targets:
                send(s_any, t)
    else:
        s_any = new_sock("")
        for itf in interfaces:
            if s_any is not None:
                send(s_any, itf.broadcast)
            s_if = new_sock(itf.ip)
            if s_if is not None:
                send(s_if, "255.255.255.255")
                send(s_if, itf.broadcast)
        if s_any is not None:
            send(s_any, "255.255.255.255")
    found: dict[str, dict[str, Any]] = {}
    end = time.monotonic() + timeout
    try:
        while time.monotonic() < end and socks:
            ready, _, _ = select.select([s for s, _ in socks], [], [], max(0.0, min(0.1, end - time.monotonic())))
            for s in ready:
                try:
                    data, (src, _) = s.recvfrom(2048)
                except OSError:
                    continue
                try:
                    ack = parse_gvcp_ack(data)
                    if ack.answer != ACK_DISCOVERY or ack.status != 0:
                        continue
                    dev = parse_discovery_ack(ack.payload, src)
                except (ValueError, struct.error, OSError):
                    continue
                key = f"{dev['mac']}/{dev['ip']}/{src}"  # not MAC alone: emulators share one MAC
                if key in found:
                    continue
                itf = interface_for_ip(dev["ip"], interfaces)
                dev["host_interface"] = itf.as_dict() if itf else None
                dev["same_subnet_as_host"] = itf is not None
                dev["control_ip"] = dev["ip"] if dev["ip"] != "0.0.0.0" else src
                found[key] = dev
    finally:
        for s, _ in socks:
            s.close()
    return sorted(found.values(), key=lambda d: tuple(int(x) for x in d["control_ip"].split(".")))


# =============================================================================
# GVCP client (unicast control channel)
# =============================================================================
class GvcpError(RuntimeError):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


class GvcpTimeout(GvcpError):
    pass


class GvcpClient:
    """One-command-in-flight GVCP client for a single camera.

    Reading never changes camera state. Writes that tests make are recorded with
    `write_reg(..., restore=True)` and undone by `restore()`; `close()` releases control.
    """

    def __init__(self, ip: str, local_ip: str = "", timeout: Number = 0.5, retries: int = 3) -> None:
        self.ip = ip
        self.timeout = timeout
        self.retries = retries
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((local_ip, 0))
        self.sock.connect((ip, GVCP_PORT))
        self.local_ip = str(self.sock.getsockname()[0])
        self._lock = threading.Lock()
        self._req_id = int.from_bytes(os.urandom(2), "big") % 0x7FFF + 1
        self._hb_stop = threading.Event()
        self._hb_thread: Optional[threading.Thread] = None
        self.have_control = False
        self.control_lost = False
        self._restore: list[tuple[int, int]] = []
        self._restored_addrs: set[int] = set()
        self.stats = {"commands": 0, "retries": 0, "pending_acks": 0}

    # -- low level ------------------------------------------------------------
    def _next_id(self) -> int:
        self._req_id = 1 if self._req_id >= 0xFFFF else self._req_id + 1
        return self._req_id

    def transact(self, command: int, payload: bytes, expect: int, timeout: Optional[Number] = None) -> bytes:
        tmo = self.timeout if timeout is None else timeout
        with self._lock:
            rid = self._next_id()
            pkt = gvcp_command(command, payload, rid)
            self.stats["commands"] += 1
            for attempt in range(self.retries):
                if attempt:
                    self.stats["retries"] += 1
                try:
                    self.sock.send(pkt)
                except OSError as e:
                    raise GvcpError(f"{self.ip}: send failed: {e}") from e
                deadline = time.monotonic() + tmo
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self.sock.settimeout(remaining)
                    try:
                        data = self.sock.recv(2048)
                    except socket.timeout:
                        break
                    except OSError:  # Windows: ICMP port unreachable -> ConnectionResetError on a connected UDP socket
                        time.sleep(min(remaining, 0.05))
                        break
                    if len(data) < 8:
                        continue
                    ack = parse_gvcp_ack(data)
                    if ack.ack_id != rid:
                        continue  # stale ack from an earlier retry
                    if ack.answer == ACK_PENDING and len(ack.payload) >= 4:
                        self.stats["pending_acks"] += 1
                        deadline = time.monotonic() + struct.unpack(">HH", ack.payload[:4])[1] / 1000.0 + tmo
                        continue
                    if ack.status != 0:
                        raise GvcpError(f"{self.ip}: command 0x{command:04X} -> {gev_status_name(ack.status)}",
                                        ack.status)
                    if ack.answer != expect:
                        raise GvcpError(f"{self.ip}: command 0x{command:04X} -> unexpected answer 0x{ack.answer:04X}")
                    return ack.payload
            raise GvcpTimeout(f"{self.ip}: no answer to command 0x{command:04X} after {self.retries} tries")

    # -- registers / memory -----------------------------------------------------
    def read_reg(self, address: int) -> int:
        body = self.transact(CMD_READREG, struct.pack(">I", address), ACK_READREG)
        if len(body) < 4:
            raise GvcpError(f"{self.ip}: short READREG answer for 0x{address:04X}")
        return int(struct.unpack(">I", body[:4])[0])

    def read_reg_opt(self, address: int) -> tuple[Optional[int], str]:
        """(value, "") or (None, reason) - for optional registers."""
        try:
            return self.read_reg(address), ""
        except GvcpError as e:
            return None, gev_status_name(e.status) if e.status else str(e)

    def read_u64(self, high: int, low: int) -> int:
        return (self.read_reg(high) << 32) | self.read_reg(low)

    def write_reg(self, address: int, value: int, restore: bool = False) -> None:
        if restore and address not in self._restored_addrs:
            old, _ = self.read_reg_opt(address)
            if old is not None:
                self._restore.append((address, old))
                self._restored_addrs.add(address)
        self.transact(CMD_WRITEREG, struct.pack(">II", address, value & 0xFFFFFFFF), ACK_WRITEREG)

    def read_mem(self, address: int, size: int) -> bytes:
        out = bytearray()
        while size > 0:
            n = min(READMEM_MAX, size)
            n4 = (n + 3) & ~3
            body = self.transact(CMD_READMEM, struct.pack(">IHH", address, 0, n4), ACK_READMEM)
            out += body[4:4 + n]
            address += n
            size -= n
        return bytes(out)

    def write_mem(self, address: int, data: bytes) -> None:
        for i in range(0, len(data), READMEM_MAX):
            chunk = data[i:i + READMEM_MAX]
            self.transact(CMD_WRITEMEM, struct.pack(">I", address + i) + chunk, ACK_WRITEMEM)

    def read_bytes(self, address: int, size: int) -> bytes:
        """Register bytes in device memory order: READMEM, falling back to READREG for aligned 4-byte reads."""
        try:
            return self.read_mem(address, size)
        except GvcpError:
            if size == 4 and address % 4 == 0:
                return struct.pack(">I", self.read_reg(address))
            raise

    def write_bytes(self, address: int, data: bytes) -> None:
        """WRITEREG for aligned 4-byte writes (mandatory command); WRITEMEM otherwise (optional command)."""
        if len(data) == 4 and address % 4 == 0:
            self.write_reg(address, struct.unpack(">I", data)[0])
        else:
            self.write_mem(address, data)

    # -- control channel ----------------------------------------------------------
    def take_control(self, exclusive: bool = False) -> None:
        try:
            self.write_reg(REG_CCP, CCP_CONTROL | (CCP_EXCLUSIVE if exclusive else 0))
        except GvcpError as e:
            if e.status == STATUS_ACCESS_DENIED:
                raise GvcpError(f"{self.ip}: control denied - another application (vendor viewer, SkellyCam, "
                                "another test) holds the camera; close it or wait for its heartbeat to expire",
                                e.status) from e
            raise
        self.have_control = True
        hb_ms, _ = self.read_reg_opt(REG_HEARTBEAT_TIMEOUT)
        period = max(0.1, min(1.0, (hb_ms or 3000) / 1000.0 / 3.0))

        def beat() -> None:
            while not self._hb_stop.wait(period):
                try:
                    if not self.read_reg(REG_CCP) & (CCP_CONTROL | CCP_EXCLUSIVE):
                        self.control_lost = True
                except (GvcpError, OSError):
                    pass

        self._hb_stop.clear()
        self._hb_thread = threading.Thread(target=beat, name=f"gvcp-heartbeat-{self.ip}", daemon=True)
        self._hb_thread.start()

    def restore(self) -> list[str]:
        problems = []
        retook = False
        for address, value in reversed(self._restore):
            try:
                self.write_reg(address, value)
            except GvcpError as e:
                if e.status == STATUS_ACCESS_DENIED and not retook:
                    retook = True  # control was lost (heartbeat timeout): take it back once and retry
                    try:
                        self.write_reg(REG_CCP, CCP_CONTROL)
                        self.write_reg(address, value)
                        continue
                    except GvcpError as e2:
                        e = e2
                problems.append(f"restore 0x{address:04X}: {e}")
        self._restore.clear()
        self._restored_addrs.clear()
        return problems

    def release_control(self) -> None:
        self._hb_stop.set()
        if self._hb_thread is not None:
            self._hb_thread.join(2.0)
            self._hb_thread = None
        if self.have_control:
            try:
                self.write_reg(REG_CCP, 0)
            except (GvcpError, OSError):
                pass
            self.have_control = False

    def close(self) -> list[str]:
        """Restore what this client changed, release control, close the socket. Returns restore problems."""
        problems = self.restore() if self.have_control else []
        self.release_control()
        self.sock.close()
        return problems

    # -- timestamps -------------------------------------------------------------
    def tick_frequency(self) -> int:
        return self.read_u64(REG_TICK_FREQ_HIGH, REG_TICK_FREQ_LOW)

    def latch_timestamp(self) -> tuple[int, int, int]:
        """Latch the device clock. Returns (host_perf_ns_before, host_perf_ns_after_latch_ack, device_ticks).
        Needs control privilege on most cameras."""
        t0 = time.perf_counter_ns()
        self.write_reg(REG_TIMESTAMP_CONTROL, TIMESTAMP_CONTROL_LATCH)
        t1 = time.perf_counter_ns()
        return t0, t1, self.read_u64(REG_TIMESTAMP_VALUE_HIGH, REG_TIMESTAMP_VALUE_LOW)


def send_action_cmd(dest: str, device_key: int, group_key: int, group_mask: int, action_time: Optional[int] = None,
                    bind_ip: str = "", wait_s: Number = 0.25, req_id: Optional[int] = None,
                    ack_required: bool = True) -> dict[str, int]:
    """Send one ACTION_CMD (broadcast or unicast) and collect ACTION_ACKs: {camera_ip: status}."""
    rid = req_id if req_id is not None else int.from_bytes(os.urandom(2), "big") % 0xFFFE + 1
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    acks: dict[str, int] = {}
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind((bind_ip, 0))
        s.sendto(build_action_cmd(device_key, group_key, group_mask, action_time, rid, ack_required), (dest, GVCP_PORT))
        end = time.monotonic() + wait_s
        while ack_required:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            s.settimeout(remaining)
            try:
                data, (src, _) = s.recvfrom(2048)
            except socket.timeout:
                break
            except OSError:
                continue
            try:
                ack = parse_gvcp_ack(data)
            except ValueError:
                continue
            if ack.answer == ACK_ACTION and ack.ack_id == rid:
                acks[src] = ack.status
    finally:
        s.close()
    return acks


# =============================================================================
# GenICam XML (fetch + tiny resolver)
# =============================================================================
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_local_url(url: str) -> Optional[tuple[str, int, int]]:
    """'Local:[///]name.xml;ADDRESS;SIZE' (hex, optional 0x)."""
    m = re.match(r"(?i)local:(?:///)?([^;]+);(?:0x)?([0-9a-f]+);(?:0x)?([0-9a-f]+)", url.strip())
    if not m:
        return None
    return m.group(1), int(m.group(2), 16), int(m.group(3), 16)


def fetch_genicam_xml(client: GvcpClient) -> dict[str, Any]:
    """Read the First URL register and download the XML over READMEM (read-only).
    Only 'Local:' URLs can be fetched; 'File:'/'http:' URLs are reported."""
    out: dict[str, Any] = {"url": None, "file_name": None, "xml": None, "error": ""}
    try:
        url = _cstr(client.read_mem(REG_FIRST_URL, 512))
    except GvcpError as e:
        out["error"] = f"cannot read XML URL register: {e}"
        return out
    out["url"] = url
    loc = parse_local_url(url)
    if not loc:
        out["error"] = f"XML URL scheme not supported by this script (only Local:): {url!r}"
        return out
    name, addr, size = loc
    out["file_name"] = name
    try:
        blob = client.read_mem(addr, size)
        if name.lower().endswith(".zip") or blob[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                inner = [n for n in z.namelist() if n.lower().endswith(".xml")] or z.namelist()
                blob = z.read(inner[0])
        out["xml"] = blob
    except (GvcpError, zipfile.BadZipFile, IndexError) as e:
        out["error"] = f"XML download failed: {e}"
    return out


class GenApiUnsupported(Exception):
    pass


class MiniGenApi:
    """A deliberately tiny GenICam resolver - NOT a GenApi implementation.

    Enough to execute AcquisitionStart/AcquisitionStop, set TLParamsLocked and read/write simple
    integer/enum/boolean features whose value chain ends in IntReg / MaskedIntReg / StructEntry
    registers with constant (or constant-pointer) addresses. Selectors, pIndex, SwissKnife-computed
    addresses, converters, float registers, chunk/event ports raise GenApiUnsupported.
    The `port` needs read_bytes(address, size) and write_bytes(address, data).
    """

    def __init__(self, xml: bytes, port: Any) -> None:
        self.port = port
        root = ET.fromstring(xml)
        self.nodes: dict[str, Any] = {}
        self.parents: dict[int, Any] = {}
        for parent in root.iter():
            for child in parent:
                self.parents[id(child)] = parent
                name = child.get("Name")
                if name and _local(child.tag) != "EnumEntry":
                    self.nodes.setdefault(name, child)

    def has(self, name: str) -> bool:
        return name in self.nodes

    def kind(self, name: str) -> str:
        return _local(self.nodes[name].tag) if name in self.nodes else ""

    @staticmethod
    def _child_texts(el: Any, tag: str) -> list[str]:
        return [(c.text or "").strip() for c in el if _local(c.tag) == tag]

    def _text(self, el: Any, tag: str) -> Optional[str]:
        vals = self._child_texts(el, tag)
        return vals[0] if vals else None

    @staticmethod
    def _literal(text: str) -> int:
        t = text.strip()
        return int(t, 16) if t.lower().startswith("0x") else int(t, 10)

    def _node(self, name: str) -> Any:
        if name not in self.nodes:
            raise GenApiUnsupported(f"no node {name!r} in the camera XML")
        return self.nodes[name]

    def enum_entries(self, name: str) -> list[str]:
        el = self._node(name)
        return [c.get("Name", "") for c in el if _local(c.tag) == "EnumEntry"]

    def _register(self, el: Any) -> tuple[int, int, bool]:
        tag = _local(el.tag)
        src = self.parents.get(id(el)) if tag == "StructEntry" else el
        if src is None:
            raise GenApiUnsupported("StructEntry without parent StructReg")
        if self._child_texts(src, "pIndex") or self._child_texts(src, "IntSwissKnife"):
            raise GenApiUnsupported(f"{src.get('Name')}: computed (pIndex/SwissKnife) address")
        port = self._text(src, "pPort")
        if port and port in self.nodes and self._child_texts(self.nodes[port], "ChunkID"):
            raise GenApiUnsupported(f"{src.get('Name')}: chunk port")
        addrs = [self._literal(a) for a in self._child_texts(src, "Address")]
        addrs += [self.get_int(p) for p in self._child_texts(src, "pAddress")]
        if not addrs:
            raise GenApiUnsupported(f"{src.get('Name')}: no constant address")
        length = self._literal(self._text(src, "Length") or "4")
        big = (self._text(src, "Endianess") or "LittleEndian") == "BigEndian"
        return sum(addrs), length, big

    def _bitfield(self, el: Any, nbits: int, big: bool) -> tuple[int, int]:
        """(shift, width) of a MaskedIntReg/StructEntry inside its register (GenApi bit numbering:
        BigEndian bit 0 is the MSB)."""
        bit = self._text(el, "Bit")
        if bit is not None:
            b = self._literal(bit)
            return (nbits - 1 - b if big else b), 1
        lsb = self._literal(self._text(el, "LSB") or "0")
        msb = self._literal(self._text(el, "MSB") or "0")
        if big:
            return nbits - 1 - lsb, lsb - msb + 1
        return lsb, msb - lsb + 1

    def get_int(self, name: str) -> int:
        el = self._node(name)
        tag = _local(el.tag)
        if tag in ("Integer", "Boolean", "Enumeration", "Command"):
            pv = self._text(el, "pValue")
            if pv:
                return self.get_int(pv)
            v = self._text(el, "Value")
            if v is not None:
                return self._literal(v)
            raise GenApiUnsupported(f"{name}: <{tag}> without pValue/Value")
        if tag in ("IntReg", "MaskedIntReg", "StructEntry"):
            address, length, big = self._register(el)
            raw = int.from_bytes(self.port.read_bytes(address, length), "big" if big else "little")
            if tag == "IntReg":
                if (self._text(el, "Sign") or "Unsigned") == "Signed" and raw >> (8 * length - 1):
                    raw -= 1 << (8 * length)
                return raw
            shift, width = self._bitfield(el, 8 * length, big)
            return (raw >> shift) & ((1 << width) - 1)
        raise GenApiUnsupported(f"{name}: <{tag}> not supported by the mini resolver")

    def set_int(self, name: str, value: int) -> None:
        el = self._node(name)
        tag = _local(el.tag)
        if tag in ("Integer", "Boolean", "Enumeration"):
            pv = self._text(el, "pValue")
            if not pv:
                raise GenApiUnsupported(f"{name}: <{tag}> without pValue")
            self.set_int(pv, value)
            return
        if tag in ("IntReg", "MaskedIntReg", "StructEntry"):
            address, length, big = self._register(el)
            order = "big" if big else "little"
            if tag == "IntReg":
                raw = value & ((1 << (8 * length)) - 1)
            else:
                cur = int.from_bytes(self.port.read_bytes(address, length), order)
                shift, width = self._bitfield(el, 8 * length, big)
                mask = ((1 << width) - 1) << shift
                raw = (cur & ~mask) | ((value << shift) & mask)
            self.port.write_bytes(address, raw.to_bytes(length, order))
            return
        raise GenApiUnsupported(f"{name}: cannot write <{tag}>")

    def execute(self, name: str) -> None:
        el = self._node(name)
        if _local(el.tag) != "Command":
            raise GenApiUnsupported(f"{name} is not a Command")
        pv = self._text(el, "pValue")
        cv = self._text(el, "CommandValue")
        pcv = self._text(el, "pCommandValue")
        if not pv or (cv is None and not pcv):
            raise GenApiUnsupported(f"{name}: Command without pValue/CommandValue")
        self.set_int(pv, self._literal(cv) if cv is not None else self.get_int(pcv or ""))

    def get_enum(self, name: str) -> str:
        v = self.get_int(name)
        for c in self._node(name):
            if _local(c.tag) == "EnumEntry" and self._text(c, "Value") is not None and self._literal(self._text(c, "Value") or "0") == v:
                return c.get("Name", str(v))
        return str(v)

    def set_enum(self, name: str, entry: str) -> None:
        for c in self._node(name):
            if _local(c.tag) == "EnumEntry" and c.get("Name") == entry:
                self.set_int(name, self._literal(self._text(c, "Value") or "0"))
                return
        raise GenApiUnsupported(f"{name} has no entry {entry!r}")

    def set_bool(self, name: str, value: bool) -> None:
        el = self._node(name)
        on = self._text(el, "OnValue")
        off = self._text(el, "OffValue")
        self.set_int(name, (self._literal(on) if on else 1) if value else (self._literal(off) if off else 0))


# Features whose presence in the XML tells us which sync method / feature names a camera uses.
FEATURES_OF_INTEREST: dict[str, list[str]] = {
    "ptp_sfnc": ["PtpEnable", "PtpStatus", "PtpServoStatus", "PtpDataSetLatch", "PtpOffsetFromMaster",
                 "PtpClockAccuracy", "PtpDataSetLatchValue"],
    "ptp_deprecated": ["GevIEEE1588", "GevIEEE1588Status", "GevIEEE1588StatusLatched", "GevIEEE1588DataSetLatch",
                       "GevIEEE1588OffsetFromMaster", "GevIEEE1588Mode"],
    "ptp_vendor": ["PtpMode", "PtpSlaveOnly", "BslPtpPriority1", "BslPtpServoStatus", "PtpAcquisitionGateTime"],
    "timestamp": ["TimestampLatch", "TimestampLatchValue", "TimestampReset", "GevTimestampControlLatch",
                  "GevTimestampControlReset", "GevTimestampValue", "GevTimestampTickFrequency"],
    "action": ["ActionDeviceKey", "ActionSelector", "ActionGroupKey", "ActionGroupMask", "ActionUnconditionalMode",
               "ActionQueueSize", "GevActionDestinationIPAddress", "ActionCommandExecuteTime"],
    "scheduled_action": ["GevSupportedOptionSelector", "GevScheduledActionCommandQueueSize"],
    "trigger": ["TriggerSelector", "TriggerMode", "TriggerSource", "TriggerActivation"],
    "sync_free_run": ["SyncFreeRunTimerEnable", "SyncFreeRunTimerStartTimeLow", "SyncFreeRunTimerTriggerRateAbs",
                      "AcquisitionStartMode", "PTPSyncFrameRate"],
    "transport_version": ["DeviceTLVersionMajor", "DeviceTLVersionMinor", "GevVersionMajor", "GevVersionMinor",
                          "DeviceTLType", "GevStreamingMode", "DeviceStreamProtocol"],
    "compression": ["ImageCompressionMode", "ImageCompressionRateOption", "ImageCompressionQuality",
                    "ImageCompressionJPEGFormatOption", "BslImageCompressionMode", "ChunkCompressionMode"],
    "frame_rate": ["AcquisitionFrameRate", "AcquisitionFrameRateAbs", "AcquisitionFrameRateEnable",
                   "DeviceLinkThroughputLimit", "GevSCPD"],
}
ENUMS_OF_INTEREST = ["TriggerSource", "TriggerSelector", "PixelFormat", "PtpStatus", "PtpMode", "GevIEEE1588Status",
                     "GevStreamingMode", "DeviceStreamProtocol", "ImageCompressionMode", "AcquisitionStartMode",
                     "DeviceTLType"]


def xml_feature_report(xml: bytes) -> dict[str, Any]:
    """Which features of interest exist in the XML, plus selected enum entries (read-only, no evaluation).
    Presence in the XML does not mean the feature is available in the current camera state."""
    root = ET.fromstring(xml)
    names: dict[str, Any] = {}
    for el in root.iter():
        n = el.get("Name")
        if n and _local(el.tag) != "EnumEntry":
            names.setdefault(n, el)
    present = {group: [f for f in feats if f in names] for group, feats in FEATURES_OF_INTEREST.items()}
    enums = {}
    for e in ENUMS_OF_INTEREST:
        if e in names:
            enums[e] = [c.get("Name", "") for c in names[e] if _local(c.tag) == "EnumEntry"]
    schema = {k: root.get(k) for k in ("ModelName", "VendorName", "SchemaMajorVersion", "SchemaMinorVersion",
                                       "MajorVersion", "MinorVersion") if root.get(k) is not None}
    return {"node_count": len(names), "root_attributes": schema, "present": present, "enum_entries": enums}


# =============================================================================
# Sockets
# =============================================================================
def rcvbuf_hint() -> str:
    system = platform.system()
    if system == "Linux":
        return ("raise the cap: sudo sysctl -w net.core.rmem_max=67108864 (or run with --force-rcvbuf as root/"
                "CAP_NET_ADMIN to use SO_RCVBUFFORCE)")
    if system == "Darwin":
        return "raise the cap: sudo sysctl -w kern.ipc.maxsockbuf=33554432 (macOS limits it to its boot-time maximum)"
    return "Windows normally honours large SO_RCVBUF requests; check NIC 'Receive Buffers' in the adapter settings too"


def open_udp_receiver(bind_ip: str, port: int, rcvbuf_request: int, force: bool = False) -> tuple[socket.socket, dict[str, Any]]:
    """UDP socket with a large receive buffer. Returns (socket, info) where info reports the requested and
    effective SO_RCVBUF and whether the OS capped it."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    info: dict[str, Any] = {"requested": rcvbuf_request, "method": "SO_RCVBUF", "errors": []}
    default = s.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    info["os_default"] = default
    if rcvbuf_request > 0:
        req = rcvbuf_request
        use_force = force and platform.system() == "Linux"
        while req >= 65536:
            opt_name = "SO_RCVBUFFORCE" if use_force else "SO_RCVBUF"
            try:
                if use_force:
                    s.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_RCVBUFFORCE", 33), req)
                else:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, req)
                info["method"] = opt_name
                break
            except OSError as e:  # macOS: ENOBUFS above kern.ipc.maxsockbuf; Linux FORCE without CAP_NET_ADMIN: EPERM
                info["errors"].append(f"{opt_name} {req}: {e}")
                if use_force:
                    use_force = False  # retry the same size with plain SO_RCVBUF (silently capped by rmem_max)
                    continue
                req //= 2
    eff = s.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    info["effective"] = eff
    # Linux reports twice the value it accepted (bookkeeping overhead); compare like for like.
    usable = eff // 2 if platform.system() == "Linux" else eff
    info["effective_usable_estimate"] = usable
    info["capped"] = rcvbuf_request > 0 and usable < 0.9 * rcvbuf_request
    s.bind((bind_ip, port))
    return s, info


def linux_udp_rcvbuf_errors() -> Optional[int]:
    """Linux: kernel count of UDP datagrams dropped because a socket receive buffer was full."""
    try:
        with open("/proc/net/snmp", encoding="ascii") as f:
            rows = [line.split() for line in f if line.startswith("Udp:")]
        return int(rows[1][rows[0].index("RcvbufErrors")])
    except (OSError, ValueError, IndexError):
        return None


# =============================================================================
# Selftest (pure unit, no network, runs anywhere)
# =============================================================================
class _DictPort:
    """In-memory register space for the MiniGenApi selftest."""

    def __init__(self) -> None:
        self.mem: dict[int, int] = {}

    def read_bytes(self, address: int, size: int) -> bytes:
        return bytes(self.mem.get(address + i, 0) for i in range(size))

    def write_bytes(self, address: int, data: bytes) -> None:
        for i, b in enumerate(data):
            self.mem[address + i] = b


_SELFTEST_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<RegisterDescription xmlns="http://www.genicam.org/GenApi/Version_1_1" ModelName="Selftest" VendorName="SkellyCam">
  <Command Name="AcquisitionStart"><pValue>AcquisitionCommandReg</pValue><CommandValue>1</CommandValue></Command>
  <Command Name="AcquisitionStop"><pValue>AcquisitionCommandReg</pValue><CommandValue>0</CommandValue></Command>
  <IntReg Name="AcquisitionCommandReg"><Address>0x20000</Address><Length>4</Length><AccessMode>WO</AccessMode>
    <pPort>Device</pPort><Endianess>BigEndian</Endianess></IntReg>
  <Integer Name="TLParamsLocked"><pValue>TLLockedReg</pValue></Integer>
  <MaskedIntReg Name="TLLockedReg"><Address>0x20004</Address><Length>4</Length><AccessMode>RW</AccessMode>
    <pPort>Device</pPort><Bit>31</Bit><Endianess>BigEndian</Endianess></MaskedIntReg>
  <Enumeration Name="TriggerSource"><EnumEntry Name="Line1"><Value>0</Value></EnumEntry>
    <EnumEntry Name="Action1"><Value>5</Value></EnumEntry><pValue>TriggerSourceEntry</pValue></Enumeration>
  <StructReg Comment="trigger"><Address>0x20010</Address><Length>4</Length><pPort>Device</pPort>
    <Endianess>BigEndian</Endianess>
    <StructEntry Name="TriggerSourceEntry"><LSB>23</LSB><MSB>20</MSB></StructEntry></StructReg>
  <Boolean Name="PtpEnable"><pValue>TLLockedReg</pValue></Boolean>
  <Integer Name="Width"><pValue>WidthReg</pValue></Integer>
  <IntReg Name="WidthReg"><pAddress>WidthAddr</pAddress><Length>4</Length><pPort>Device</pPort>
    <Endianess>LittleEndian</Endianess></IntReg>
  <Integer Name="WidthAddr"><Value>0x30000</Value></Integer>
</RegisterDescription>
"""


def run_selftest(rep: Reporter) -> None:
    """Pure-unit checks of every encoder/decoder in this module. No network access."""
    # ACTION_CMD - layout cross-checked with tshark 4.2.2 and with viva-genicam's encoder on the wire
    p = build_action_cmd(0x12345678, 0x1, 0xFFFFFFFF, None, req_id=0x0102)
    rep.check("ACTION_CMD immediate encoding", p == bytes.fromhex("42010100000c010212345678" "00000001ffffffff"), p.hex())
    p2 = build_action_cmd(0x12345678, 0x1, 0x1, 0x000001E23F5A1000, req_id=0x0103)
    rep.check("ACTION_CMD scheduled encoding (flags 0x81, length 20, u64 time)",
              p2 == bytes.fromhex("4281010000140103123456780000000100000001000001e23f5a1000"), p2.hex())
    p3 = build_action_cmd(1, 2, 3, None, req_id=7, ack_required=False)
    rep.check("ACTION_CMD without ACK_REQUIRED has flags 0x00", p3[1] == 0x00)
    # PACKETRESEND
    r1 = build_packetresend(0x1234, 5, 9, req_id=0x0A0B)
    rep.check("PACKETRESEND 16-bit block id encoding",
              r1 == bytes.fromhex("42000040000c0a0b" "00001234" "00000005" "00000009"), r1.hex())
    r2 = build_packetresend(0x0000000100000002, 5, 9, req_id=0x0A0C, extended_ids=True)
    rep.check("PACKETRESEND 64-bit block id encoding (flag 0x10, length 20)",
              r2 == bytes.fromhex("421000400014" "0a0c" "00000000" "00000005" "00000009" "0000000100000002"), r2.hex())
    # READREG / WRITEREG / READMEM / DISCOVERY
    rep.check("READREG encoding", build_readreg([0x0934, 0x096C], 3) == bytes.fromhex("420100800008000300000934" "0000096c"))
    rep.check("WRITEREG encoding", build_writereg([(0x0944, 2)], 4) == bytes.fromhex("42010082000800040000094400000002"))
    rep.check("READMEM encoding", build_readmem(0x0200, 512, 5) == bytes.fromhex("420100840008000500000200" "00000200"))
    rep.check("DISCOVERY encoding (ack required + broadcast ack allowed)",
              build_discovery(0xFFFF) == bytes.fromhex("421100020000ffff"))
    ack = parse_gvcp_ack(bytes.fromhex("0000008100040007" "00080000"))
    rep.check("GVCP ack decoding", (ack.status, ack.answer, ack.ack_id, ack.payload) == (0, ACK_READREG, 7, b"\x00\x08\x00\x00"))
    late = parse_gvcp_ack(bytes.fromhex("8016010100000009"))
    rep.check("ACTION_ACK ACTION_LATE status name", gev_status_name(late.status) == "ACTION_LATE")
    dpl = build_discovery_ack_payload("169.254.10.20", bytes.fromhex("0030531a2b3c"), "Acme", "Cam-3", "SN42", 3, 0)
    d = parse_discovery_ack(dpl, "169.254.10.20")
    rep.check("DISCOVERY_ACK decoding", (d["gev_version"], d["ip"], d["mac"], d["manufacturer"], d["model"], d["serial"])
              == ("3.0", "169.254.10.20", "00:30:53:1A:2B:3C", "Acme", "Cam-3", "SN42"), json.dumps(d)[:120])
    # Capability / config bits
    rep.check("capability bit decoding", bits_set(0x000A0044, CAPABILITY_BITS) == ["ieee1588", "scheduled_action", "action", "packet_resend"])
    rep.check("PFNC names", (pfnc_name(0x01080009), pfnc_name(0x010C0047), pfnc_name(0x81080001)) ==
              ("BayerRG8", "Mono12p", "custom(0x81080001)"))
    rep.check("PFNC bits per pixel", (pfnc_bits_per_pixel(0x01080009), pfnc_bits_per_pixel(0x010C0047)) == (8, 12))
    rep.check("OpenCV Bayer hint (PFNC BayerRG8 -> COLOR_BayerBG2BGR)", opencv_bayer_hint("BayerRG8") == "cv2.COLOR_BayerBG2BGR")
    rep.check("ticks_to_ns / ns_to_ticks", ticks_to_ns(125_000_000, 125_000_000) == 1_000_000_000
              and ticks_to_ns(3, 1_000_000_000) == 3 and ns_to_ticks(1_000_000_000, 125_000_000) == 125_000_000)
    # GVSP headers / leaders
    std = build_gvsp_image_leader(77, 0x0102030405060708, 0x01080001, 640, 480)
    h = parse_gvsp_header(std, len(std))
    lead = parse_gvsp_leader(std[8:])
    rep.check("GVSP standard leader decoding", h == (0, 77, FMT_LEADER, 0, False, 0, 8) and
              (lead["payload_type"], lead["timestamp"], lead["pixel_format_name"], lead["size_x"], lead["size_y"]) ==
              (PT_IMAGE, 0x0102030405060708, "Mono8", 640, 480), f"{h} {lead}")
    ei = build_gvsp_image_leader(0x1_0000_0001, 5, 0x01080009, 1920, 1200, extended_ids=True)
    h2 = parse_gvsp_header(ei, len(ei))
    lead2 = parse_gvsp_leader(ei[20:])
    rep.check("GVSP extended-ID leader decoding (64-bit block id)", h2 == (0, 0x1_0000_0001, FMT_LEADER, 0, True, 0, 20)
              and lead2["pixel_format_name"] == "BayerRG8", f"{h2}")
    tr = build_gvsp_trailer(77, 12, 480)
    rep.check("GVSP trailer decoding", parse_gvsp_header(tr, len(tr))[2:4] == (FMT_TRAILER, 12)
              and parse_gvsp_trailer(tr[8:]) == {"payload_type": PT_IMAGE, "size_y": 480})
    rsd = build_gvsp_payload(9, 3, b"xx", extended_ids=True, flags=0x0001)
    rep.check("GVSP extended-ID resend flag decoding", parse_gvsp_header(rsd, len(rsd))[5] == 0x0001)
    rep.check("non-GVSP datagram rejected", parse_gvsp_header(b"\x00\x00\x00\x01\x0f\x00\x00\x00", 8) is None)
    # Analyser on a synthetic stream: 3 complete, 1 missing a packet, 1 without trailer, 1 block id never sent
    a = GvspAnalyzer()
    t = 0.0
    frames = [synth_gvsp_frame(b, b * 33_333_333, 0x01080009, 64, 48, 1000) for b in (1, 2, 3)]
    frames.append(synth_gvsp_frame(4, 4 * 33_333_333, 0x01080009, 64, 48, 1000, drop={2}))
    frames.append(synth_gvsp_frame(6, 6 * 33_333_333, 0x01080009, 64, 48, 1000)[:-1])
    for fr in frames:
        for pkt in fr:
            t += 1e-4
            a.feed(pkt, len(pkt), t)
    a.finish()
    s = a.summary(tick_hz=1_000_000_000)
    rep.check("analyser frame completeness (3 complete, 1 incomplete, 1 trailer missing)",
              (s["frames_complete"], s["frames_incomplete"], s["frames_trailer_missing"], s["missing_packets_total"])
              == (3, 1, 1, 1), f"{s['frames_complete']}/{s['frames_incomplete']}/{s['frames_trailer_missing']}")
    rep.check("analyser block-id gap detection", s["block_id_gaps"] == 1, str(s["block_id_gaps"]))
    rep.check("analyser verdict UNCOMPRESSED for full-size BayerRG8", s["compression_verdict"] == "UNCOMPRESSED",
              "; ".join(s["compression_reasons"]))
    rep.check("analyser device fps from leader timestamps", abs((s.get("device_fps_from_timestamps") or 0) - 30.0) < 0.1,
              str(s.get("device_fps_from_timestamps")))
    a2 = GvspAnalyzer()
    for pkt in synth_gvsp_frame(1, 1, 0, 0, 0, 1000, payload_type=PT_JPEG, payload_bytes=3000):
        a2.feed(pkt, len(pkt), 0.0)
    a2.finish()
    rep.check("analyser verdict COMPRESSED for JPEG payload type", a2.summary()["compression_verdict"] == "COMPRESSED")
    a3 = GvspAnalyzer()
    for pkt in synth_gvsp_frame(1, 1, 0x81080001, 64, 48, 1000, payload_bytes=900):
        a3.feed(pkt, len(pkt), 0.0)
    a3.finish()
    rep.check("analyser verdict LIKELY-COMPRESSED for custom pixel format", a3.summary()["compression_verdict"] == "LIKELY-COMPRESSED")
    a4 = GvspAnalyzer()
    for pkt in synth_gvsp_frame(1, 1, 0x01080001, 64, 48, 1000, payload_bytes=1000):
        a4.feed(pkt, len(pkt), 0.0)
    a4.finish()
    rep.check("analyser verdict LIKELY-COMPRESSED for undersized Mono8 frames", a4.summary()["compression_verdict"] == "LIKELY-COMPRESSED")
    ae = GvspAnalyzer()
    for pkt in synth_gvsp_frame(2**40, 1, 0x01080001, 64, 48, 1400, extended_ids=True):
        ae.feed(pkt, len(pkt), 0.0)
    ae.finish()
    se = ae.summary()
    rep.check("analyser extended-ID stream", se["extended_ids_used"] and se["frames_complete"] == 1)
    # pcap round trips (classic pcap/raw IP and pcapng/Ethernet with a 128-byte snaplen)
    dgrams = [("169.254.1.2", 20202, "169.254.1.1", 50000, pkt) for fr in frames for pkt in fr]
    with tempfile.TemporaryDirectory() as tmp:
        for name, writer in (("rt.pcap", lambda pth: write_pcap(pth, dgrams)),
                             ("rt.pcapng", lambda pth: write_pcapng_ethernet(pth, dgrams, snaplen=128))):
            path = os.path.join(tmp, name)
            writer(path)
            a5 = GvspAnalyzer()
            for ts, lt, frame, _orig in iter_capture(path):
                u = extract_udp(lt, frame)
                if u is None:
                    continue
                a5.feed(u.payload, len(u.payload), ts, ip_size=u.ip_total_len, wire_len=u.udp_payload_len)
            a5.finish()
            s5 = a5.summary()
            rep.check(f"pcap round trip ({name})", (s5["frames_complete"], s5["frames_incomplete"], s5["block_id_gaps"])
                      == (3, 1, 1) and s5["max_ip_packet_size"] == 1000 + 8 + 28,
                      f"{s5['frames_complete']}/{s5['frames_incomplete']} max_ip={s5['max_ip_packet_size']}")
    # MiniGenApi
    port = _DictPort()
    g = MiniGenApi(_SELFTEST_XML, port)
    g.execute("AcquisitionStart")
    rep.check("mini GenApi Command -> BigEndian IntReg", port.read_bytes(0x20000, 4) == b"\x00\x00\x00\x01")
    g.set_int("TLParamsLocked", 1)
    rep.check("mini GenApi MaskedIntReg bit 31 (BigEndian = LSB)", port.read_bytes(0x20004, 4) == b"\x00\x00\x00\x01"
              and g.get_int("TLParamsLocked") == 1)
    g.set_enum("TriggerSource", "Action1")
    rep.check("mini GenApi enum via StructEntry LSB23/MSB20", port.read_bytes(0x20010, 4) == b"\x00\x00\x05\x00"
              and g.get_enum("TriggerSource") == "Action1", port.read_bytes(0x20010, 4).hex())
    port.write_bytes(0x30000, (1920).to_bytes(4, "little"))
    rep.check("mini GenApi pAddress + LittleEndian IntReg", g.get_int("Width") == 1920)
    rep.check("mini GenApi enum entries", g.enum_entries("TriggerSource") == ["Line1", "Action1"])
    fx = xml_feature_report(_SELFTEST_XML)
    rep.check("XML feature report", "PtpEnable" in fx["present"]["ptp_sfnc"] and fx["enum_entries"]["TriggerSource"] == ["Line1", "Action1"])
    rep.check("Local: URL parsing", parse_local_url("Local:///cam.zip;0x10000;0x2A3F") == ("cam.zip", 0x10000, 0x2A3F)
              and parse_local_url("local:x.xml;8000;100") == ("x.xml", 0x8000, 0x100))
    rep.check("percentile / linear fit", percentile([1, 2, 3, 4], 50) == 2.5 and abs(linear_fit([0, 1, 2], [1, 3, 5])[0] - 2.0) < 1e-12)


def selftest_main(extra: Optional[Callable[[Reporter], None]] = None, title: str = "selftest") -> int:
    rep = Reporter(title)
    print(f"== {title}: pure-unit checks (no network)")
    run_selftest(rep)
    if extra is not None:
        extra(rep)
    rep.print_summary()
    return rep.exit_code()


if __name__ == "__main__":
    sys.exit(selftest_main(title="gev_common selftest"))
