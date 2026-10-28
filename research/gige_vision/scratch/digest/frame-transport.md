# frame-transport

## Key findings

**1. The premise is wrong.** Single-cable PTP sync arrived with **GigE Vision 2.0, not 3.0**. A3's standard page says GEV 2.0 (Nov 2011) "enables transmission of compressed images (JPEG, JPEG 2000 and H.264), accurate synchronization of multi-camera systems". GEV 2.1 (Aug 2018) "includes an updated profile for IEEE1588". GEV 3.0 (TC-approved 17 Apr 2026) adds **GVRSP, RDMA streaming over RoCEv2**, as an optional alternative to GVSP ([A3 standard page](https://www.automate.org/vision/vision-standards/vision-standards-gige-vision), [A3 GEV 3.0 FAQ, 2026-08-19](https://www.automate.org/vision/blogs/gige-vision-3-0-standard-answers-to-frequently-asked-questions-faq)). The FAQ also says:
- "not all GigE Vision 3.0 cameras support RDMA"
- GEV 3.0 cameras support "GVSP v2" and GVRSP, but not legacy GVSP v1
- GVRSP needs a RoCEv2 NIC

The 1588 and scheduled-action bootstrap registers (0x096C to 0x097C) and ACTION_CMD 0x0100 are already in the 2.x register map ([Wireshark packet-gvcp.c#L120-L136](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L120-L136)). What you need is a GEV 2.x camera that implements IEEE 1588.

**2. How frames travel.**
- **GVCP** is the control channel: UDP requests to device port 3956 ([Aravis arvgvcpprivate.h#L36](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L36)). The host reads the GenICam XML and sets registers over it.
- **GVSP** is a one-way UDP stream to whatever host IP and port the host writes into the stream channel registers ([packet-gvcp.c#L148-L160](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L148-L160)):

| Register | Name | Purpose |
|---|---|---|
| 0x0D00 | SCP | host port |
| 0x0D04 | SCPS | packet size, plus fire-test and do-not-fragment bits |
| 0x0D08 | SCPD | inter-packet delay, in timestamp ticks |
| 0x0D18 | SCDA | destination IP |

- **Packets per frame:** one leader, N payload packets, one trailer.
- **Header:** the standard 8-byte header has a 16-bit block id (frame id) and a 24-bit packet id. GEV 2.0 adds an extended-ID header (the EI bit, 0x80 in byte 4) with a 64-bit block id and 32-bit packet id ([Aravis arvgvspprivate.h#L132-L144](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L132-L144), [packet-gvsp.c#L2349-L2450](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L2349-L2450)).
- **Payload type codes,** confirmed in both [Aravis arvbuffer.h#L79-L92](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvbuffer.h#L79-L92) and [Wireshark packet-gvsp.c#L43-L54](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L43-L54):

| Code | Payload type |
|---|---|
| 0x0001 | IMAGE |
| 0x0002 | RAW |
| 0x0003 | FILE |
| 0x0004 | CHUNK |
| 0x0005 | EXT_CHUNK (deprecated) |
| 0x0006 | JPEG |
| 0x0007 | JPEG2000 |
| 0x0008 | H.264 |
| 0x0009 | MULTIZONE |
| 0x000A | MULTIPART |
| 0x000B | GenDC |
| 0x8000 and up | device-specific |

  Bit 0x4000 in the payload type means chunk data is appended.
- **Image leader** (36 bytes): flags, payload type, u64 timestamp, PFNC pixel format, size x/y, offset x/y, padding x/y. The trailer carries payload type and size y.

**Tested in Docker** with the Aravis 0.8.36 fake GigE Vision camera, tcpdump and tshark. The decoded leader was:
```
status 0, block 65401, LEADER, IMAGE, ts 0x18e1d68736273fd8, Mono8 0x01080001, 512x512
```
With SCPS 1400 a packet carries 1364 bytes of image data, so the trailer's packet_id is 194, exactly as predicted from the overhead formula in [arvgvspprivate.h#L257-L280](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L257-L280).

**3. Packet loss.** The host sends PACKETRESEND_CMD 0x0040 over GVCP for packets it is missing ([arvgvcp.c#L405-L441](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcp.c#L405-L441)). Resent packets come back with status 0x0100. "Packet unavailable / removed from memory" errors (0x800C, 0x8011, 0x8012) stop further requests for that frame.
> **Correction (2026-10-28):** status 0x0100 as the resend marker is not shown to be universal. Aravis documents it for FLIR/PointGrey Blackfly cameras, and in extended-ID mode the standard marks resent packets with header flag 0x01 (verifier C9, packet-gvsp.c L1808).
- **Resend depends on the camera.** Aravis turns resend off unless capability register 0x0934 bit 2 is set ([arvgvdevice.c#L2071-L2072](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L2071-L2072), [#L1904-L1905](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L1904-L1905)).
- **Docker, 2% simulated loss** (the fake camera has no resend): 0 resend requests and 19 of 20 frames failed.
- **Docker, 8000-byte packets:** with the default socket buffer 9 of 20 frames completed; with Aravis's auto `SO_RCVBUF` ([arvgvstream.c#L224-L262](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L224-L262)) 21 of 21 completed. The host's socket buffer size matters.
  > **Correction (2026-10-28):** `scripts-ft/out/run_jumbo.txt` shows 9 completed and 10 failed, so 9 of 19 frames, not 9 of 20. The verifier (C10) also found that the default-buffer 1400-byte run with no simulated loss failed too (1 failure, 82 missing packets, `run_clean.txt`). The 2% simulated-loss result above (19 of 20 failed) is therefore confounded with socket-buffer drops. All are single runs on Docker loopback with Aravis 0.8.36.

**4. Raw or compressed?** Typical GigE Vision cameras send **uncompressed IMAGE payloads**: raw Bayer or Mono in PFNC formats.
- Aravis, the main open-source stack, gives JPEG, JPEG2000, H.264, multizone and GenDC payloads 0 expected packets and returns `PAYLOAD_NOT_SUPPORTED` ([arvgvstream.c#L278-L318, #L384-L393](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L384-L393)).
- pyGigEVision only knows payload 0x0001 and Mono8 to Mono16 ([gvsp.py#L52-L76](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L52-L76)). Any other pixel format falls back to 2 bytes per pixel ([#L226-L227](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L226-L227)). From reading the code (not tested), it would mis-size BayerRG8 frames.

Compressed examples exist, but only one uses a standard GVSP payload type:

| Vendor / camera | Compression | How it is carried and decoded |
|---|---|---|
| [Baumer VLXT.I.JP](https://www.baumer.com/ca/en/service-support/technology-highlights/industrial-cameras-with-integrated-jpeg-image-compression/a/JPEG-image-compression) | JPEG | "based on the GigE Vision 2.0 standard per JPEG payload type"; Mono8 or YCbCr422_8 input; `ImageCompressionMode=JPEG` |
| [Teledyne FLIR Blackfly S GigE](https://www.teledynevisionsolutions.com/support/support-center/application-note/iis/using-lossless-compression/) | Lossless | "proprietary format", needs Spinnaker 2.4.0.143 or later |
| [Basler Compression Beyond](https://docs.baslerweb.com/compression-beyond) | Lossless or fixed-ratio lossy | Needs pylon `CImageDecompressor` plus a compression descriptor read from the camera |
| [LUCID QOI](https://support.thinklucid.com/knowledgebase/using_qoi_with_lucid_cameras/) | Lossless | Chosen as a `QOI_*` PixelFormat, decoded by Arena |

**5. Bandwidth** ([scripts-ft/bandwidth.py](file:///C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/research/scripts-ft/bandwidth.py)). Usable on 1 GbE: about 119.0 MB/s with 1500-byte packets, about 124.0 MB/s with jumbo frames.

| Stream | Payload | 1 GbE result |
|---|---|---|
| 1920x1200 BayerRG8 @ 60 fps | 138.24 MB/s = 1106 Mbit/s | **Not even one camera fits** (max about 51.6 fps, or 53.8 fps jumbo) |
| Same @ 30 fps | 553 Mbit/s | 1 camera per link (1.7) |
| Same @ 60 fps on other links | — | 2.5 GbE: 2.2 cameras; 5 GbE: 4.3; 10 GbE: 8.6 |

Multiple cameras sharing one link need SCPD or `DeviceLinkThroughputLimit` ([Beckhoff](https://infosys.beckhoff.com/content/1033/tf7xxx_tc3_vision/22185723659.html)).

**Stand-alone test for real cameras:** `scripts-ft/gvsp_pcap_report.py` (stdlib only, reads pcap and pcapng, runs on Windows, macOS and Linux). Capture with Wireshark while streaming, then run it. It reports payload type, pixel format, packet size and jumbo use, extended-ID mode, resends, timestamp deltas, and a compressed/not-compressed verdict. I validated it against the Docker captures.

## Open questions

- How FLIR lossless and Basler Compression Beyond frames are carried in GVSP (IMAGE payload with a custom pixel format, a device-specific payload type >=0x8000, or chunk data). Vendor docs do not say; running scripts-ft/gvsp_pcap_report.py on a real camera would settle it.
- LUCID QOI_* pixel format numeric codes, and whether they set PFNC bit 31 (custom).
- No concrete GigE Vision camera found with doc links that streams the standard H.264 (0x0008) or JPEG2000 (0x0007) payload types.
- Whether 'GVSP v2' in the GEV 3.0 FAQ means the extended-ID (EI) header is mandatory for GEV 3.0 devices; the spec text (A3 download) was not read.
- GVRSP (RDMA/RoCEv2) frame and buffer format and its open-source receiver support; not covered by any code read here.
- Exact GEV spec semantics for SCPD ticks and SCPS bit fields are taken from Aravis/Wireshark code, not the spec itself.
- Aravis's Linux packet-socket receive path delivered 0 frames over Docker loopback while tcpdump saw the packets; probably a loopback/container artifact, not investigated further (--no-packet-socket worked).

## Verification: Counter({'supported': 13, 'partially-supported': 3, 'refuted': 1})

- [partially-supported] C9: Packet loss recovery uses GVCP PACKETRESEND_CMD 0x0040 with a block id and first/last packet ids (24- or 32-bit), sent from the stream socket. Resent packets come back with status 0x0100. Aravis disables resend when GVCP capability register 0x0934 bit 2 is clear. Defaults: 1 ms initial timeout, 20 ms resend timeout, 100 ms frame retention, 25% resend budget.
  REASON: Several parts check out:
- The resend command layout is right: block id plus 24-bit or 32-bit first/last ids, with the 64-bit block id at the end for extended IDs (arvgvcp.c L405-441). It is sent from the stream socket (arvgvstream.c L218).
- Capability bit 0x934 bit 2 is right (arvgvcpprivate.h L95-98, arvgvdevice.c L2071-2072, L1904-1905).
- The defaults 1 ms, 20 ms, 100 ms and 0.25 are right (arvgvstreamprivate.h L33-36).
- The fake camera never writes 0x934 (arvfakecamera.c L1082-1091), which explains the 0 resend requests.

Two caveats:
- Aravis documents status 0x0100 as 'resent packet (BlackFly PointGrey camera support)'. Wireshark treats 0x0100 as success only in extended-ID mode (packet-gvsp.c L1808), where the standard resend marker is header flag bit 0x01. 'Resent packets come back with status 0x0100' is therefore not shown to be universal.
- The 0x800C/0x8011/0x8012 handling is real but sits at arvgvstream.c L922-927, which the claim does not cite.
  CORRECTED: Resend uses PACKETRESEND_CMD 0x0040, and Aravis only sends it if GVCP capability 0x934 bit 2 is set. Resent packets may carry status 0x0100 (Aravis notes this for FLIR/PointGrey Blackfly) and/or, in extended-ID mode, header flag 0x01. A status of 0x800C, 0x8011 or 0x8012 disables further resends for that frame (arvgvstream.c L922-927).
  BETTER: ['https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L40-L70', 'https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L922-L927', 'https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L1808']

- [partially-supported] C10: Host UDP receive buffer size decides frame completeness. With SCPS 8000 the default socket buffer completed 9 of 20 frames; Aravis's auto SO_RCVBUF (frame size + 1024) completed 21 of 21 with 0 missing packets.
  REASON: run_jumbo.txt shows 9 completed and 10 failed. run_jumbo_auto.txt shows 21 completed with 0 missing packets. The AUTO buffer is allocated_size + 1024 with a 20 KiB minimum (arvgvstream.c L62-63, L224-262). But these are single runs on Docker loopback with Aravis 0.8.36, not the 482547a code that is linked. The default-buffer 1400 B run with no simulated loss also failed 1 frame with 82 missing packets (run_clean.txt). So the '2% loss → 19/20 failed' result is confounded with socket-buffer drops.
  CORRECTED: On Docker loopback (Aravis 0.8.36), the default socket buffer dropped packets even without simulated loss: 1/20 frames failed at 1400 B and 10/19 failed at 8000 B. Aravis's AUTO SO_RCVBUF (payload + 1024 B) removed the drops. This shows the receive buffer is a key factor; it has not been measured on real NICs.
  BETTER: ['https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L62-L63']

- [partially-supported] C16: Aravis converts the leader timestamp to ns using bootstrap tick-frequency registers 0x093C/0x0940 and falls back to host wall-clock time when the tick frequency is 0. Aravis src contains no PTP/IEEE 1588-specific code (grep finds none at 482547a).
  REASON: The tick frequency is read from 0x93C/0x940 (arvgvdevice.c L570-592; arvgvcpprivate.h L116-117). Conversion is at arvgvspprivate.h L728-743, the host-time fallback at arvgvstream.c L460 and L479-484, and a grep of src/ finds no PTP or 1588 code. That is all literally correct. However, at the same commit Aravis's GStreamer element gst/gstaravis.c (L563-567, L631-640, L1203-1209; commit ee31d82f1 of 2026-10-03) adds an 'add-reference-timestamp-meta' property. It attaches the device timestamp as a timestamp/x-ptp GstReferenceTimestampMeta, documented as 'Only an absolute time if the device clock is PTP-synchronized'.
  CORRECTED: The Aravis core library (src/) has no PTP-specific code and passes the device timestamp through tick-to-ns conversion, falling back to host time when the tick frequency is 0. Aravis's gst plugin can tag buffers with the absolute device timestamp as a timestamp/x-ptp reference meta (added 2026-10-03). PtpEnable and similar features are reachable only as generic GenICam nodes.
  BETTER: ['https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L563-L567', 'https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L1203-L1209', 'https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L570-L592']

- [refuted] C17: Wireshark's GVSP dissector is heuristic-only and disabled by default (no fixed GVSP port); captures must be decoded with --enable-heuristic gvsp_udp.
  REASON: The heuristic is registered with HEURISTIC_DISABLE (L3640), but GVSP is not heuristic-only. L3639 registers it for Decode-As on udp.port. packet-gvcp.c L1728-1736 automatically adds the GVSP dissector on any port written to SCP0-3 via WRITEREG. Test in Docker (gev-ft-research image, tshark 4.2.2) on the researcher's gev_clean.pcap:
- Without --enable-heuristic: 261 GVCP and 4095 GVSP packets, the same as with the flag.
- Stream-only capture (port 3956 filtered out): 4095 UDP until '-d udp.port==35957,gvsp' is given, which decodes all 4095 as GVSP.
  CORRECTED: Wireshark decodes GVSP automatically when the capture includes the GVCP WRITEREG to the SCP register. For captures that start after stream setup, use Decode-As (-d udp.port==<port>,gvsp) or --enable-heuristic gvsp_udp.
  BETTER: ['https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L1728-L1736', 'https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L3637-L3641']

## Missed points

- The LUCID PTP app note independently says PTP 'has been integrated into GigE Vision 2.0'. It also gives the vendor node workflow for single-cable sync: PtpEnable, PtpSlaveOnly, PtpStatus, PtpDataSetLatch/PtpDataSetLatchValue, ActionDeviceKey/ActionGroupKey/ActionGroupMask, ActionCommandExecuteTime, TriggerSource=Action0. https://support.thinklucid.com/app-note-multi-camera-synchronization-using-ptp-and-scheduled-action-commands/
- LUCID GVRSP knowledge base (updated 2026-09-17):
- GVRSP is available only on LUCID 10G+ cameras (Atlas10 fw >= 1.48, Triton10 fw >= 1.18, Atlas25) and needs specific NICs.
- Arena selects the stream protocol with TLDevice DeviceStreamProtocol: Automatic, GVRSP, GVSP or Legacy.
- GevSCPSPacketSize and GevSCPD disappear in GVRSP mode, and packet resend is built into the transport.
- A GEV 3.0 device reports DeviceTLVersionMajor = 3.
https://support.thinklucid.com/knowledgebase/using-gige-vision-rdma-streaming-protocol-in-gige-vision-3-0/
- The A3 GEV 3.0 FAQ (Q4) says RDMA/GVRSP runs at 10G, 25G, 50G, 100G and above, so GEV 3.0's new transport does not help 1 GbE motion-capture rigs. https://www.automate.org/vision/blogs/gige-vision-3-0-standard-answers-to-frequently-asked-questions-faq
- Aravis's GStreamer element (gst/gstaravis.c, commit ee31d82f1, 2026-10-03) adds 'add-reference-timestamp-meta'. It exposes the absolute device timestamp as a timestamp/x-ptp reference, which is meaningful when the camera is PTP-synchronized. https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L563-L567
- pyGigEVision skips any frame where width*height > 2048*2048 (logged as 'invalid dimensions'), so common 5 MP and larger sensors (e.g. 2448x2048) never deliver frames. https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L140-L145
- pyGigEVision's GVCP status-name table differs from Aravis and Wireshark. It maps 0x800C to PACKET_NOT_YET_AVAILABLE, 0x800D to PACKET_AND_PREV_REMOVED and 0x800E to PACKET_REMOVED. Aravis uses 0x800C PACKET_UNAVAILABLE, 0x8010 NOT_YET_AVAILABLE, 0x8011 and 0x8012 REMOVED. https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L62-L71 vs https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L82-L88
- The researcher's Docker tests ran Aravis tag 0.8.36 (commit 97ff5e33, 2026-04-23, per scripts-ft/Dockerfile), but every code link points at 482547a (0.9.2-29, 2026-10-22). The tested and the linked code are different versions. https://github.com/AravisProject/aravis/tree/0.8.36
- Aravis's fake GV camera never sets the GVCP capability register 0x934, so it can never exercise packet resend. A real camera, or a patched emulator, is needed to test resend. https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvfakecamera.c#L1082-L1091
- Wireshark auto-learns the GVSP port from a GVCP WRITEREG to SCP0-3 and decodes those packets with no heuristic flag. Users of the stand-alone pcap test should start the capture before the stream starts. https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L1728-L1736
- The A3 standard page also records GEV 2.2 (June 2022: GenDC streaming, multi event data), which the version history in the claims omits. https://www.automate.org/vision/vision-standards/vision-standards-gige-vision