# GigE Vision frame transport (GVCP / GVSP): how frames reach the host, raw vs compressed

Research date: 2026-10-25. Topic key: `frame-transport`.

## Sources used (versions / dates)

| Source | Version pinned | Date |
|---|---|---|
| Aravis (LGPL-2.1+, C) https://github.com/AravisProject/aravis | `main` @ `482547a3d56e3aa8d22d7ffed33c9f1588bfe17a` | commit 2026-10-22. Latest tags: 0.9.2 and 0.8.36 (both 2026-04-23) |
| Aravis built in Docker for the tests | tag `0.8.36` (`97ff5e33…`) | 2026-04-23 |
| Wireshark GVSP/GVCP dissectors https://gitlab.com/wireshark/wireshark | `master` @ `98a6cfdba1ab23f3c835b17df802004bc9429040` | 2026-10-25 |
| tshark used for decoding | 4.2.2 (Ubuntu 24.04 package) | — |
| pyGigEVision https://github.com/ladisk/pyGigEVision | `2de253135b8766c1eb752226539a16b810a1cf0f` (pyproject 0.2.2) | 2026-07-08 |
| A3 GigE Vision standard page https://www.automate.org/vision/vision-standards/vision-standards-gige-vision | — | read 2026-10-25 |
| A3 "GigE Vision 3.0 Standard: FAQ" https://www.automate.org/vision/blogs/gige-vision-3-0-standard-answers-to-frequently-asked-questions-faq | — | 2026-08-19 |
| A3 "GigE Vision 3.0 Brings Fast Data Transfers at Mass Market Prices" https://www.automate.org/vision/industry-insights/gige-vision-3-0-brings-fast-data-transfers-at-mass-market-prices | — | 2026-08-04 |
| Vendor docs (Teledyne FLIR, Basler, LUCID, Baumer, Beckhoff) | see section 7 | — |

Permalink bases used below:
- `AR` = https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/
- `WS` = https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/

---

## 0. Correction to the premise ("GigE Vision 3 = single-cable PTP sync")

The premise is wrong, and the A3 standards page says so directly:

- **GigE Vision 2.0 (November 2011)**: "introduces support for faster data transfer through 10 gigabit Ethernet and link aggregation. It also enables transmission of compressed images (JPEG, JPEG 2000 and H.264), accurate synchronization of multi-camera systems…". **GigE Vision 2.1 (August 2018)**: "multi-part transmission… also includes an updated profile for IEEE1588". **GigE Vision 2.2 (June 2022)**: "GenDC streaming and multi event data". Source: [A3 GigE Vision page](https://www.automate.org/vision/vision-standards/vision-standards-gige-vision) (page text saved locally as `src/web-ft/automate_gev.txt`, lines 283-291).
- **GigE Vision 3.0** (TC approval 17 April 2026) "leverages the Remote Direct Memory Access over Converged Ethernet technology (RoCEv2)… adds a new streaming protocol which can be used as an alternative to the current GigE Vision Streaming Protocol (GVSP)". The [A3 FAQ (2026-08-19)](https://www.automate.org/vision/blogs/gige-vision-3-0-standard-answers-to-frequently-asked-questions-faq) names it **GVRSP (GigE Vision RDMA Streaming Protocol)**. It also says: "GigE Vision 3.0 cameras support both GVSP v2 … and the new GVRSP protocol", "GigE Vision 3.0 does not support the legacy GVSP v1 protocol", "not all GigE Vision 3.0 cameras support RDMA", and RDMA needs "a compatible RDMA-capable NIC" (RoCEv2: Mellanox, Broadcom, Intel). FAQ Q4 lists RDMA speeds of "10G, 25G, 50G, 100G, and higher".
- The bootstrap registers for IEEE 1588 already sit in the GEV 2.x register map, as Wireshark's GVCP dissector shows: `GVCP_IEEE_1588_STATUS 0x096C`, `GVCP_SCHEDULED_ACTION_COMMAND_QUEUE_SIZE 0x0970`, `GVCP_IEEE_1588_EXTENDED_CAPABILITY 0x0974`, `…_SUPPORTED_PROFILES 0x0978`, `…_SELECTED_PROFILE 0x097C` ([WS packet-gvcp.c#L120-L136](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L120-L136)). `GVCP_ACTION_CMD 0x0100` is there too ([#L196-L197](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L196-L197)).

**Conclusion:** single-cable PTP sync needs a **GigE Vision 2.x camera that implements IEEE 1588** (PTP plus scheduled action commands). GEV 3.0 does not add it. GEV 3.0 adds RDMA streaming, which is aimed at 10G+ links with RoCEv2 NICs. Its frames still use the same GenICam and PFNC concepts. A camera sold as "GigE Vision 3.0" may still stream only through GVSP. Details of PTP management belong to the separate PTP topic.

---

## 1. Two protocols: GVCP (control) and GVSP (streaming)

- **GVCP** is a UDP request/ack protocol to **device port 3956**: `#define ARV_GVCP_PORT 3956` ([AR src/arvgvcpprivate.h#L36](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L36)). Wireshark uses the same default, `global_gvcp_port = 3956` ([WS packet-gvcp.c#L272](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L272)).
  - Header (8 bytes): `packet_type` (0x42 = CMD, 0x00 = ACK), `packet_flags`, `command` (16 bit), `size`, `id` ([AR arvgvcpprivate.h#L150-L153, #L297-L303](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L297-L303)).
  - Commands: DISCOVERY 0x0002, BYE 0x0004, PACKETRESEND 0x0040, READREG 0x0080, WRITEREG 0x0082, READMEM 0x0084, WRITEMEM 0x0086, PENDING_ACK 0x0089 ([AR arvgvcpprivate.h#L267-L281](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L267-L281)). Wireshark adds ACTION_CMD 0x0100 ([WS packet-gvcp.c#L181-L197](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L181-L197)).
  - The host reads the device's GenICam XML over GVCP (READMEM) and sets every feature (`Width`, `PixelFormat`, `GevSCPSPacketSize` …) as register reads and writes. The Docker capture (section 8) shows 71 READMEM, 41 READREG and 14 WRITEREG commands before streaming starts.
- **GVSP** is a one-way UDP stream **from the camera to a host IP and port that the host picks**. It has no fixed port, which is why Wireshark finds it only through a heuristic that is **disabled by default** (`heur_dissector_add("udp", dissect_gvsp_heur, …, "gvsp_udp", …, HEURISTIC_DISABLE)`, [WS packet-gvsp.c#L3640](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L3640)). Use `tshark --enable-heuristic gvsp_udp`.
  > **Correction (2026-10-28):** refuted by the verifier (C17). GVSP is not heuristic-only. Wireshark decodes it automatically when the capture includes the GVCP WRITEREG to the SCP register (packet-gvcp.c L1728-L1736), and it can also be selected with Decode-As (`-d udp.port==<port>,gvsp`). The heuristic flag is needed only for captures that start after stream setup. Without the flag, tshark 4.2.2 decoded all 4095 GVSP packets in `gev_clean.pcap`.

### Stream channel setup (SCx registers, stride 0x40 per channel)

From Wireshark ([WS packet-gvcp.c#L148-L160](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L148-L160)) and Aravis ([AR arvgvcpprivate.h#L126-L137](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L126-L137); stride `SEL * 0x40` at [arvgvdevice.c#L1586-L1590](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L1586-L1590)):

| Reg (ch0) | Name | Meaning |
|---|---|---|
| 0x0D00 | SCP0 (`GevSCPHostPort`) | host UDP port (bits 15..0). Writing non-zero starts the channel; Aravis writes 0 on stop |
| 0x0D04 | SCPS0 (`GevSCPSPacketSize`) | packet size (16 bit; includes IP+UDP+GVSP header), bit 31 = **fire test packet**, bit 30 = **do-not-fragment**, bit 29 = big-endian ([AR #L128-L133](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L128-L133)) |
| 0x0D08 | SCPD0 (`GevSCPD`) | inter-packet delay, in **timestamp ticks** |
| 0x0D18 | SCDA0 (`GevSCDA`) | destination IPv4 (unicast or multicast) |
| 0x0D1C | SCSP0 | camera's source port (GEV 2.x) |
| 0x0D20 / 0x0D24 | SCC / SCCFG | stream channel capability / configuration (e.g. extended-ID enable) |
| 0x0D30-0x0D3C | max packet count, max block size, extended bootstrap | GEV 2.2 additions |

Seen in the Docker capture (tshark output in `scripts-ft/out/decode_clean.txt`):
```
230 > WRITEREG_CMD [SCDA0 (Stream Channel #0 Destination Address)] Value=0xAC110003
234 > WRITEREG_CMD [SCP0 (Stream Channel #0 Port)] Value=0x00008C75
 96 < READREG_ACK [SCPS0 (Stream Channel #0 Packet Size)] Value=0x00000578   (=1400)
4351 > WRITEREG_CMD [SCP0 (Stream Channel #0 Port)] Value=0x00000000          (stop)
```

**Packet-size negotiation.** Aravis's `auto_packet_size()` ([AR arvgvdevice.c#L651-L784](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L651-L784)) sets do-not-fragment and runs a binary search with `GevSCPSFireTestPacket`. It keeps the largest size whose test packet arrives. When the stream starts with SCPS too small, it falls back to the default `ARV_GV_DEVICE_GVSP_PACKET_SIZE_DEFAULT 1500` ([arvgvdeviceprivate.h#L48](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdeviceprivate.h#L48); [arvgvstream.c#L1620-L1625](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L1620-L1625)). To use jumbo frames (SCPS of about 9000), **every NIC and switch on the path** needs a raised MTU. Beckhoff says the same: "the largest possible packet size supported by all components along the transmission path should be used" ([Beckhoff bandwidth management](https://infosys.beckhoff.com/content/1033/tf7xxx_tc3_vision/22185723659.html)).

**Inter-packet delay (SCPD).** Aravis turns nanoseconds into ticks with `value = tick_frequency * delay_ns / 1e9` and writes it to `GevSCPD` ([AR arvcamera.c#L3521-L3550](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvcamera.c#L3521-L3550)). Tick frequency comes from bootstrap registers 0x093C/0x0940 ([AR arvgvcpprivate.h#L116-L117](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L116-L117)). Beckhoff: SCPD inserts "a defined delay time between all consecutive packets… specified in device-specific hardware ticks", and many cameras also offer `DeviceLinkThroughputLimit`, where "the camera firmware calculates the required packet delay" ([Beckhoff](https://infosys.beckhoff.com/content/1033/tf7xxx_tc3_vision/22185723659.html)). This is how several cameras that share one switch uplink or NIC interleave their bursts instead of overflowing switch buffers.

---

## 2. GVSP packet format

All fields are big-endian. Struct definitions are in [AR src/arvgvspprivate.h#L132-L255](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L132-L255). Wireshark's parse is at [WS packet-gvsp.c#L2349-L2450](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L2349-L2450).

### Common header

**Standard (GEV 1.x style) header, 8 bytes:**
```
0  u16 status        (0x0000 success, 0x0100 = resent packet, 0x8xxx = error)
2  u16 block_id      (frame id, 16 bit, 0 invalid, wraps 65535 -> 1)
4  u8  EI|format     (bit7 = EI extended-ID flag; low 7 bits = packet format)
5  u24 packet_id
```
**Extended-ID header (GEV 2.0+, EI = 1), 20 bytes:**
```
0  u16 status
2  u16 flags         (bit0 packet-resend, bit1 previous-block-dropped, bit2 resend-range-error per Wireshark)
4  u8  EI|format, u24 reserved / n_parts (multipart) / additional zones (multizone)
8  u64 block_id
16 u32 packet_id
```
- Masks: `ARV_GVSP_PACKET_EXTENDED_ID_MODE_MASK 0x80000000`, `ARV_GVSP_PACKET_ID_MASK 0x00ffffff`, `CONTENT_TYPE_MASK 0x7f000000` ([AR #L32-L36](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L32-L36)). Wireshark: `GVSP_EXTENDED_ID_BIT 0x80`, `GVSP_V2_MIN_PACKET_SIZE 20` ([WS #L31-L34](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L31-L34)). The flag bits are parsed at [WS #L2400-L2405](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L2400-L2405).
- Block-id wrap handling: Aravis treats 16-bit ids as signed deltas and skips id 0 (`/* Frame id 0 is not a valid value */`) ([AR arvgvstream.c#L355-L366](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L355-L366)). The fake camera starts at 65400 "to trigger circular counter bugs sooner" and wraps from 65535 to 1 ([AR arvfakecamera.c#L786-L790, #L1110](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvfakecamera.c#L786-L790)). At 60 fps a 16-bit block id wraps about every 18 minutes. That is harmless for transport, but the **block id should not be used as a long-lived frame index for multi-camera alignment**. Use the leader timestamp instead.

### Packet formats (content type, low 7 bits of byte 4)

| code | format | source |
|---|---|---|
| 1 | LEADER | [AR #L109-L119](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L109-L119), [WS #L100-L108](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L100-L108) |
| 2 | TRAILER | ″ |
| 3 | PAYLOAD (generic data) | ″ |
| 4 | ALL_IN (leader + data + trailer in one packet) | ″ |
| 5 | H.264 payload | ″ |
| 6 | multi-zone payload | ″ |
| 7 | multi-part payload (GEV 2.1) | ″ |
| 8 | GenDC payload (GEV 2.2) | ″ |

### Payload types (16-bit field in the leader; bit 14 = 0x4000 means "chunk data appended")

Verified in **both** Aravis ([AR src/arvbuffer.h#L79-L92](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvbuffer.h#L79-L92); the 0x3fff mask and 0x4000 chunk bit are at [arvgvspprivate.h#L427-L449](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L427-L449)) and Wireshark ([WS packet-gvsp.c#L34, #L43-L54](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L43-L54)):

| code | type | note (Wireshark comment) |
|---|---|---|
| 0x0001 | IMAGE | uncompressed image (the normal case) |
| 0x0002 | RAW_DATA | |
| 0x0003 | FILE | |
| 0x0004 | CHUNK_DATA | |
| 0x0005 | EXTENDED_CHUNK_DATA | "Deprecated with GEV 2.0" |
| **0x0006** | **JPEG** | "GEV 2.0" |
| **0x0007** | **JPEG2000** | "GEV 2.0" |
| **0x0008** | **H.264** | "GEV 2.0" |
| 0x0009 | MULTIZONE_IMAGE | "GEV 2.0, deprecated with GEV 2.2" |
| 0x000A | MULTIPART | "GEV 2.1" |
| 0x000B | GENDC (Aravis: GENDC_CONTAINER; Aravis also defines 0x000C GENDC_COMPONENT_DATA) | "GEV 2.2" |
| ≥0x8000 | device-specific | `GVSP_PAYLOAD_DEVICE_SPECIFIC_START` |

Multi-part part data types also include JPEG 0x000B and JPEG2000 0x000C ([WS #L114-L126](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L114-L126)). GenDC has part header types for 2D JPEG 0x4201, JPEG2000 0x4202 and H.264 0x4203 ([WS #L73-L76](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L73-L76)).

### Image leader (payload type 0x0001), 36 bytes after the GVSP header

```
0  u16 field_info / flags
2  u16 payload_type        (0x0001)
4  u64 timestamp           (device ticks; Aravis converts with tick frequency)
12 u32 pixel_format        (PFNC code)
16 u32 size_x
20 u32 size_y
24 u32 offset_x
28 u32 offset_y
32 u16 padding_x
34 u16 padding_y
```
Sources: [AR ArvGvspImageLeader #L152-L193](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L152-L193) and [WS dissect_image_leader #L1287-L1310 (returns 36)](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L1287-L1310).

**Image trailer**: `u16 reserved, u16 payload_type, u32 size_y` (8 bytes). Sources: [WS #L1315-L1327](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L1315-L1327) and [AR ArvGvspTrailer #L238-L241](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L238-L241).

**JPEG / JPEG2000 leader** (32 bytes): field info, generic flags, payload type, **u64 timestamp**, **u64 payload_data_size**, **u64 timestamp_tick_frequency**, u32 data_format ([WS dissect_jpeg_leader #L1523-L1550](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L1523-L1550)). The compressed payload has a variable size, so the size travels in the leader.

**H.264 leader**: payload type, u64 payload_data_size, packetization_mode, packet_size, then profile_idc/level_idc/sprop fields as in RFC 6184. Wireshark parses no timestamp at offset 4 ([WS dissect_h264_leader #L1556-L1604](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L1556-L1604)).

### Pixel format codes (PFNC)

Layout: bits 31..24 = mono 0x01 / color 0x02 / bit 31 custom; bits 23..16 = **bits per pixel**; low 16 bits = id ([WS #L164-L166](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L164-L166); `ARV_PIXEL_FORMAT_BIT_PER_PIXEL(pf) = (pf >> 16) & 0xff` at [AR src/arvenums.h#L121](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvenums.h#L121)). Examples, checked in both repositories: Mono8 `0x01080001`, Mono12 `0x01100005` (16-bit container), Mono12p `0x010C0047`, BayerRG8 `0x01080009`, BayerRG12 `0x01100011`, BayerRG12p `0x010C0059`, RGB8 `0x02180014`, YCbCr422_8 `0x0210003B` ([AR arvenums.h#L125-L271](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvenums.h#L125-L271); [WS #L171-L219, #L371](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L171-L219)).

### Payload packets and per-packet overhead

Each PAYLOAD packet carries `SCPS − 20 (IP) − 8 (UDP) − 8 (GVSP)` bytes of image data, or `− 20` for the GVSP header with extended IDs ([AR ARV_GVSP_PACKET_PROTOCOL_OVERHEAD #L257-L280](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L257-L280)). Aravis works out the expected packet count as `ceil(buffer/block_size) + 2 (leader+trailer)` ([AR arvgvstream.c#L267-L318](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L267-L318)). The Docker test confirms the math: SCPS 1400 gives 1364 B per packet, a 512×512 Mono8 frame takes 193 payload packets, and the **trailer packet_id = 194**, which matches the capture exactly.

---

## 3. What happens on packet loss (PACKETRESEND)

GVSP runs over plain UDP with no flow control. The host finds gaps by packet_id and asks for retransmission over GVCP:

- PACKETRESEND_CMD (0x0040) payload: standard mode is `u32 stream_channel/block_id (16-bit), u32 first_packet_id (24 bit), u32 last_packet_id`. Extended mode is `u32 0, u32 first, u32 last, u64 block_id`, with the GVCP header flag EXTENDED_IDS set ([AR arvgvcp.c#L405-L441](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcp.c#L405-L441); [WS dissect_packetresend_cmd #L1555-L1620](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L1555-L1620)). Aravis sends it **from the stream socket** to the device's GVCP port ([AR arvgvstream.c#L198-L222](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L198-L222)). pyGigEVision does the same ([gvsp.py#L78-L82](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L78-L82)). The command is fire-and-forget: Aravis documents `PACKET_RESEND_ACK` as "(not used ?)" ([AR arvgvcpprivate.h#L254](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L254)).
- Resent packets come back with GVSP status 0x0100 (`ARV_GVSP_PACKET_STATUS_PACKET_RESEND`, "BlackFly PointGrey camera support"). If the camera no longer holds the data it answers with error statuses 0x800C PACKET_UNAVAILABLE, 0x8011 or 0x8012 "removed from memory", and Aravis then stops asking for that frame ([AR arvgvspprivate.h#L68-L95](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L68-L95); [arvgvstream.c#L913-L927](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L913-L927)). **Resend works only while the camera's on-board frame buffer still holds the frame.**
- Aravis's policy ([AR arvgvstream.c#L659-L745](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L659-L745)) uses these defaults: initial packet timeout 1 ms, per-resend packet timeout 20 ms, frame retention 100 ms, and a resend budget of 25% of the frame's packets ([AR arvgvstreamprivate.h#L33-L36](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstreamprivate.h#L33-L36)). A frame that is still incomplete when frame retention runs out is delivered with `ARV_BUFFER_STATUS_TIMEOUT`. With resend set to NEVER, an older incomplete frame is closed as `MISSING_PACKETS` as soon as a newer frame starts ([#L788-L880](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L788-L880)).
- **Resend is gated on a device capability.** Aravis reads GVCP capability register 0x0934 bit 2 (`ARV_GVBS_GVCP_CAPABILITY_PACKET_RESEND`) and forces `packet-resend = NEVER` when the bit is clear ([AR arvgvdevice.c#L2071-L2072](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L2071-L2072), [#L1904-L1905](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L1904-L1905); bit definitions at [arvgvcpprivate.h#L95-L113](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L95-L113)).
  - **Docker test:** the Aravis fake camera does not advertise resend. With 2% simulated loss (`arv-fake-gv-camera-0.8 -r 20`), the result was `n_resend_requests = 0`, `n_failures = 19`, `n_completed_buffers = 1` of 20, and `n_missing_packets = 2929` (`scripts-ft/out/run_lossy.txt`). Without resend, even 2% packet loss ruins almost every 193-packet frame.
- **Host receive buffer.** The other common cause of "loss" is the host's UDP socket buffer. **Docker test:** with SCPS 8000 and the default socket buffer, only 9 of 20 frames completed [**Correction (2026-10-28):** `run_jumbo.txt` shows 9 completed and 10 failed, i.e. 9 of 19] and 649 of 700 packets were received (`run_jumbo.txt`). The identical run with `-a`, Aravis's auto socket buffer, which sizes `SO_RCVBUF` to the frame size plus 1024 ([AR arvgvstream.c#L224-L262](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L224-L262)), completed **21 of 21 frames, 0 missing packets** (`run_jumbo_auto.txt`). Linux and Windows hosts need a large `SO_RCVBUF` (Linux `net.core.rmem_max`), or vendor filter drivers.

---

## 4. Raw or compressed? (Answer)

**Typical machine-vision GigE Vision cameras send uncompressed pixel data.** That means payload type `IMAGE (0x0001)` with a PFNC raw format such as Mono8, Mono12(p), BayerRG8 or BayerRG12p. Color cameras usually send the **raw Bayer mosaic**, and demosaicing happens on the host unless an on-camera RGB/YUV format is chosen, which costs 2–3× the bandwidth. Evidence:

1. Aravis, the main open-source GigE Vision stack, decodes leader geometry only for `IMAGE`/`EXTENDED_CHUNK` ([AR arvgvspprivate.h#L585-L633](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L585-L633)). It computes a packet count only for IMAGE, CHUNK, EXTENDED_CHUNK and MULTIPART. For any other payload type (**JPEG, JPEG2000, H.264, multizone, GenDC**) `_compute_n_expected_packets` returns 0 and the buffer is closed with `ARV_BUFFER_STATUS_PAYLOAD_NOT_SUPPORTED` ([AR arvgvstream.c#L278-L318, #L384-L393](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L384-L393)). The enum comments say the same: "JPEG data (not supported)", "h264 data (not supported)" ([AR arvbuffer.h#L64-L75](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvbuffer.h#L64-L75)).
2. pyGigEVision (the candidate library) defines only `PAYLOAD_IMAGE = 0x0001` and Mono8/10/12/14/16 pixel formats ([gvsp.py#L52-L76](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L52-L76)). Any other format falls back to 2 bytes per pixel and `uint16` (`PIXEL_BPP.get(pf, 2)`, [#L147, #L226-L227](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L226-L227)), and frames are capped at 2048×2048 ([#L140, #L222](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L222)). The leader's payload type is stored but never checked ([#L613](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L613)). In practice this means **BayerRG8 (1 B/px) would be sized wrongly, and compressed payloads would be treated as raw**. I did not test this against a camera; it is inferred from the code.
3. The Docker capture shows an `IMAGE` leader carrying `Mono8 (0x01080001)` 512×512 frames at 262 144 B/frame (section 8).

**Standard compressed GVSP exists (GEV 2.0+), but few cameras implement it, and vendors mostly use proprietary schemes:**

| Vendor / camera | Compression | How it is signalled / decoded | Source |
|---|---|---|---|
| **Baumer LX series VLXT.I.JP** (10GigE, 0.6–65 MP) | JPEG (lossy), on the camera, Mono8 or YCbCr422_8 input, quality 30–100% | "based on the GigE Vision 2.0 standard per JPEG payload type"; the stream "contains all headers and can be saved directly into a JPEG file"; enabled with `ImageCompressionMode = JPEG` | [Baumer JPEG page](https://www.baumer.com/ca/en/service-support/technology-highlights/industrial-cameras-with-integrated-jpeg-image-compression/a/JPEG-image-compression) (saved as `src/web-ft/baumer_jpeg.txt`, l.229-236). Kinovea's open-source integration toggles `ImageCompressionMode` "JPEG"/"Off" through Baumer's proprietary BGAPI2 SDK ([BaumerHelper.cs#L140-L182](https://github.com/Kinovea/Kinovea/blob/13d0236f65622501da5cb776ddb979629f468e71/Kinovea.Camera.Baumer/BaumerHelper.cs#L140-L182)) |
| **Teledyne FLIR Blackfly S GigE** (17 models, e.g. BFS-PGE-50S5, -161S7) | Lossless, Mono8 / BayerRG8 only, ISP must be off | "Compressed images can be streamed in a Teledyne FLIR **proprietary format** with Spinnaker"; Spinnaker ≥ 2.4.0.143 plus a firmware minimum | [TAN2021001 Using Lossless Compression](https://www.teledynevisionsolutions.com/support/support-center/application-note/iis/using-lossless-compression/) |
| **Basler ace 2 Pro GigE** ("Compression Beyond") | Lossless (default) or `FixRatio` lossy | `ImageCompressionMode = BaslerCompressionBeyond`, `ImageCompressionRateOption = Lossless/FixRatio`, `BslImageCompressionRatio`. Decoding needs pylon `CImageDecompressor` plus a **compression descriptor read from the camera's node map**; the grab buffer "must contain the entire camera payload, including chunk data" and "the payload type chunk" | [docs.baslerweb.com/compression-beyond](https://docs.baslerweb.com/compression-beyond) (v137, 2026-10-19); [pylon CImageDecompressor](https://docs.baslerweb.com/pylonapi/cpp/class_pylon_1_1_c_image_decompressor); [Basler FAQ](https://www.baslerweb.com/en/learning/compression-beyond-faq/) |
| **LUCID Phoenix (fw ≥1.78) / Triton (fw ≥1.127)** | QOI lossless | Selected as a **PixelFormat** (`QOI_Mono8`, `QOI_BayerRG8`, `QOI_RGB8`, …) and decoded with `Arena::ImageFactory::DecompressImage` (Arena ≥1.0.49.3) or the open-source QOI decoders | [LUCID KB "Using QOI with LUCID cameras"](https://support.thinklucid.com/knowledgebase/using_qoi_with_lucid_cameras/) (published 2025-03-21, updated 2025-10-28) |

None of the vendor compression schemes above, except Baumer JPEG, is documented as a standard GVSP compressed payload type, and the GVSP layout of the proprietary ones is not published (see open questions). For a generic open-source receiver such as Aravis, pyGigEVision, or a new Rust/Python implementation, assume **uncompressed IMAGE payloads**, and plan host bandwidth, CPU and disk for raw Bayer.

---

## 5. Bandwidth math (uncompressed)

Computed by `scripts-ft/bandwidth.py`, with output in `scripts-ft/out/bandwidth.txt`. Assumptions: standard 8-byte GVSP header, IPv4, no VLAN, and per-frame wire overhead of 38 B (MAC 14 + FCS 4 + preamble 8 + IFG 12). Leader and trailer packets are ignored.

- SCPS 1500: 1464 B of data per packet, 95.19% wire efficiency, about **119.0 MB/s** usable on 1 GbE.
- SCPS 9000 (jumbo): 8964 B per packet, 99.18% efficiency, about **124.0 MB/s** usable on 1 GbE.

| Stream | MB/s | Mbit/s | 1 GbE (1500 / 9000) | 2.5 GbE | 5 GbE | 10 GbE |
|---|---|---|---|---|---|---|
| 1920×1200 BayerRG8 @ 60 fps | 138.24 | **1105.9** | **0.86 / 0.90 cameras: one camera does not fit** (max 51.6 / 53.8 fps) | 2.2 | 4.3–4.5 | 8.6–9.0 |
| 1920×1200 BayerRG8 @ 30 fps | 69.12 | 553.0 | **1 camera** (1.72 / 1.79) | 4.3 | 8.6 | 17 |
| 1920×1200 BayerRG12p @ 60 fps | 207.36 | 1658.9 | 0.57 / 0.60 | 1.4 | 2.9 | 5.7–6.0 |
| 1440×1080 BayerRG8 @ 60 fps | 93.31 | 746.5 | 1 camera (1.28 / 1.33) | 3.2 | 6.4 | 12.8 |
| 1280×1024 Mono8 @ 120 fps | 157.29 | 1258.3 | 0.76 / 0.79 | 1.9 | 3.8 | 7.6 |

"Cameras per link" means cameras sharing one physical link, such as a NIC port or switch uplink. With one NIC port per camera, every camera gets the full link. Use SCPD or `DeviceLinkThroughputLimit` to spread bursts across cameras that share a link (section 1).

---

## 6. Timestamps in the leader (bridge to the PTP topic)

- The leader's u64 timestamp is in device ticks. Aravis converts it with the tick frequency from bootstrap registers 0x093C/0x0940 (`arv_gvsp_timestamp_to_ns`, [AR arvgvspprivate.h#L728-L743](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L728-L743); used at [arvgvstream.c#L479-L484](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L479-L484)). If the tick frequency is 0, Aravis falls back to the host's wall clock at leader arrival (`system_timestamp_ns = g_get_real_time()*1000`, [#L460](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L460)).
- The timestamp is the device's capture clock. With PTP enabled it is the PTP-disciplined clock, which is what lets frames from several cameras be matched on one host. The exact semantics (exposure start or end, 1 ns ticks under PTP) belong to the PTP topic and are not verified here.
- Docker test: the fake camera stamps `g_get_real_time()*1000` ns ([AR arvfakecamera.c#L795](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvfakecamera.c#L795)). The captured leader timestamps step by exactly 100 000 000 ticks (100 ms) at `-f 10`.
- Aravis has **no PTP-specific code**: `grep -rli "ptp\|ieee.\?1588" src/` returns nothing at commit 482547a. PTP has to be driven through the camera's GenICam features.

---

## 7. Vendor/other pages read (for traceability)

- Teledyne FLIR TAN2021001: https://www.teledynevisionsolutions.com/support/support-center/application-note/iis/using-lossless-compression/ (no date shown on the page)
- Basler Compression Beyond: https://docs.baslerweb.com/compression-beyond (Release date 19 October 2026, Version 137, marked "Draft Version")
- Basler pylon CImageDecompressor: https://docs.baslerweb.com/pylonapi/cpp/class_pylon_1_1_c_image_decompressor
- LUCID QOI KB: https://support.thinklucid.com/knowledgebase/using_qoi_with_lucid_cameras/
- Baumer JPEG: https://www.baumer.com/ca/en/service-support/technology-highlights/industrial-cameras-with-integrated-jpeg-image-compression/a/JPEG-image-compression (the www.baumer.com/us URL returned 403; the /ca, /tr and /it mirrors returned 200)
- Beckhoff GigE Vision bandwidth management: https://infosys.beckhoff.com/content/1033/tf7xxx_tc3_vision/22185723659.html
- A3 pages listed at the top.

---

## 8. Tests run (Docker, Aravis fake GigE Vision camera over loopback)

Scripts are in `C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/research/scripts-ft/`:
- `Dockerfile`: ubuntu:24.04, Aravis **0.8.36 built from source** (Ubuntu's `aravis-tools-cli 0.8.30` ships only `arv-tool-0.8`, without the fake camera or camera-test tools), plus tcpdump and tshark 4.2.2.
- `run_capture.sh`: starts `arv-fake-gv-camera-0.8 -i 127.0.0.1 -s GV01 -r $LOST`, runs `tcpdump -i lo udp`, then `arv-tool-0.8 control …` and `arv-camera-test-0.8 -n Aravis-Fake-GV01 -f 10 --duration 2 $EXTRA`.
- `decode.sh`: tshark decode with `--enable-heuristic gvsp_udp`.
- `gvsp_pcap_report.py`: **stand-alone, stdlib-only analyser for pcap and pcapng captures of real cameras** (Windows/macOS/Linux). It reports payload type (compressed or not), pixel format, SCPS/jumbo, EI mode, resend statuses, timestamp deltas and GVCP command counts.

Commands (from Git Bash):
```
docker build -t gev-ft-research scripts-ft
MSYS_NO_PATHCONV=1 docker run --rm -e EXTRA=--no-packet-socket -v "<scripts-ft>:/work" -v "<scripts-ft>/out:/out" gev-ft-research bash /work/run_capture.sh
MSYS_NO_PATHCONV=1 docker run --rm ... gev-ft-research bash /work/decode.sh
# lossy:   -e LOST=20 -e TAG=lossy
# jumbo:   -e TAG=jumbo -e "EXTRA=--no-packet-socket -i 8000"   (and with -a)
python -I scripts-ft/gvsp_pcap_report.py scripts-ft/out/gev_clean.pcap
```
Note: the first run without `--no-packet-socket` received 0 packets over loopback (Aravis's Linux packet-socket path), even though tcpdump saw 3900 GVSP packets. All later runs used `--no-packet-socket`.

Key output (clean run, `out/run_clean.txt`, `out/decode_clean.txt`):
```
PixelFormat = Mono8 ; Width = 512 ; Height = 512 ; PayloadSize = 262144
GevSCPSPacketSize = 1400 min:220 max:16404 inc:4 ; GevSCPD = 0 min:0 max:1000
n_completed_buffers = 20 ; n_received_packets = 4074 ; n_failures = 1 (in-flight frame at stop)
250  86 B  LEADER  [Block ID: 65401 Packet ID: 0] IMAGE
251 1414 B PAYLOAD [Block ID: 65401 Packet ID: 1]
444  58 B  TRAILER [Block ID: 65401 Packet ID: 194] IMAGE
```
Decoded image leader (tshark `-O gvsp`) and raw UDP payload:
```
Status: GEV_STATUS_SUCCESS (0x0000)   Block ID (16 bits): 65401   Format: LEADER (0x01)   Packet ID: 0
Field Info: 0x00   Payload Type: IMAGE (0x0001)   Timestamp: 0x18e1d68736273fd8 (=1792950002887639000 ns)
Pixel Format: Mono8 (0x01080001)  Size X: 512  Size Y: 512  Offset X: 0  Offset Y: 0  Padding X: 0  Padding Y: 0
raw: 0000 ff79 01 000000 | 0000 0001 18e1d68736273fd8 01080001 00000200 00000200 00000000 00000000 0000 0000
Trailer raw: 0000 ff79 02 0000c2 | 0000 0001 00000200   (payload type IMAGE, size_y 512)
Leader timestamp deltas: 12362000, 100002000, 100000000, 100000000 ticks (ns) at 10 fps
```
Lossy run (`-r 20`, i.e. 2%): `n_resend_requests 0`, `n_failures 19`, `n_missing_packets 2929`; 0 PACKETRESEND commands in the pcap (the device does not advertise the resend capability).
Jumbo run (SCPS 8000): default socket buffer gave 9 of 20 frames complete. With `-a` (auto SO_RCVBUF): 21 of 21 complete, 0 missing packets.

> **Correction (2026-10-28):** `scripts-ft/out/run_jumbo.txt` shows `n_completed_buffers = 9` and `n_failures = 10`, i.e. 9 of 19 frames complete, not 9 of 20.

`gvsp_pcap_report.py` on the clean pcap: `payload packet IP length (== GevSCPSPacketSize): 1400 -> jumbo frames: no; leader payload types: {'IMAGE': 21}; 21 x Mono8 512x512; compression verdict: no standard compressed payload type seen`.

### What to run on a machine with real cameras
1. Capture with Wireshark, dumpcap or tcpdump while streaming each pixel format and compression mode of interest.
2. Run `python3 gvsp_pcap_report.py capture.pcapng`.
3. Look at the `leader payload types` line (IMAGE vs JPEG/H264/GenDC/device-specific), the pixel format (bit 31 set means a vendor-custom format, as with QOI or compressed formats), `avg payload bytes per block` against the uncompressed size, status 0x0100 counts (resends), and the EI mode.

The output answers, per camera model, how a vendor's "compression" is actually carried over GVSP.

---

## Open questions

- How FLIR's lossless and Basler's Compression Beyond streams are framed in GVSP: payload type IMAGE with a custom pixel format, a device-specific payload type (≥0x8000), or chunk data? The vendor pages do not say. Running `gvsp_pcap_report.py` on a real camera would settle it.
- LUCID QOI pixel format numeric codes, and whether they set PFNC bit 31 (custom).
- Concrete GigE Vision cameras that send the **standard H.264 (0x0008) or JPEG2000 (0x0007)** payload. None was found with a doc link.
- Whether "GVSP v2" in the GEV 3.0 FAQ means extended-ID (EI) mode is mandatory for GEV 3.0 cameras. The spec text is not public and was not read.
- GVRSP (RDMA) packet/frame format: the GEV 3.0 spec was not read. The A3 pages state only RoCEv2 and NIC requirements.
- The exact SCPD tick semantics and the GEV spec text for SCPS bit fields. These are taken from Aravis/Wireshark code, not from the spec, which is behind an A3 download wall.
