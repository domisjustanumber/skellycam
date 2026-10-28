# Fact-check of "frame-transport" findings (verified 2026-10-25)

Sources were cloned or downloaded into
`scratchpad/research/src/verify-frame-transport/`:
- Aravis at commit 482547a3d56e3aa8d22d7ffed33c9f1588bfe17a (`git describe`: 0.9.2-29-g482547a3d, committed 2026-10-22). The latest tags are 0.9.2 (2026-04-23) and 0.8.36.
  - The researcher's Docker tests used the **0.8.36** tag (commit 97ff5e33, 2026-04-23; see `scripts-ft/Dockerfile`), not 482547a. The code links and the test binary are different versions.
- pyGigEVision at 2de2531 (v0.2.2, committed 2026-07-08).
- Wireshark `packet-gvcp.c` and `packet-gvsp.c` at 98a6cfdb (raw files fetched from GitLab).
- A3 standard page and GEV 3.0 FAQ (curl, text extracted). Baumer, Teledyne FLIR, Basler, LUCID and Beckhoff pages (curl). The Kinovea file was fetched raw at commit 13d0236.

## Verdicts

| ID | Verdict | Note |
|---|---|---|
| C1 | supported | A3 standard page: GEV 2.0 (Nov 2011) "accurate synchronization of multi-camera systems"; GEV 2.1 (Aug 2018) "updated profile for IEEE1588"; GEV 3.0 TC-approved 17 Apr 2026, adds a streaming protocol as an alternative to GVSP. The LUCID PTP app note independently says PTP "has been integrated into GigE Vision 2.0". The claim omits GEV 2.2 (June 2022: GenDC streaming, multi event data). |
| C2 | supported | FAQ Q3, Q8 and Q9 quoted verbatim below. FAQ Q4: RDMA runs at 10G/25G/50G/100G+. GVRSP is therefore not relevant on 1 GbE. |
| C3 | supported | Wireshark tags register 0x96C and the 1588 capability/config bits `_v2_0`, and 0x974–0x97C `_v2_1`; the latter include PTP and 802.1AS profile bits (L416-436, L485-489, L1183-1201). ACTION_CMD 0x0100 is at L196. |
| C4 | supported | ARV_GVCP_PORT 3956 (arvgvcpprivate.h L36). CMD 0x42 (L151). 8-byte ArvGvcpHeader (L297-303). SCP/SCPS/SCPD/SCDA (L126-137). SCPS also has BIG_ENDIAN bit 29. Wireshark stride 0x40 (L148-160). Capture shows WRITEREG SCDA0 and SCP0. |
| C5 | supported | ArvGvspPacket{u16 status} + ArvGvspHeader{u16 frame_id, u32 packet_infos} = 8 bytes; extended header = 20 bytes (`pragma pack(push,1)`). Refinement: in extended-ID mode the 16-bit block-id field becomes a flags field (resend-range-error 0x04, previous-block-dropped 0x02, packet-resend 0x01), per Wireshark L2398-2408. |
| C6 | supported | Both lists match. Aravis also defines 0x000c GENDC_COMPONENT_DATA. 0x8000 (device-specific) and the "deprecated" annotations come from Wireshark only (L43-54; MULTIZONE is marked deprecated with GEV 2.2). Aravis masks with 0x3fff and tests 0x4000 (arvgvspprivate.h L436-443). |
| C7 | supported | Wireshark image leader returns 36 (L1287-1307). Trailer: payload type + size_y. JPEG leader: ts, u64 size, u64 tick freq, data format (L1523-1550). Capture frame sizes agree: leader 86 B = 14+20+8+8+36; trailer 58 B. |
| C8 | supported | Overhead macro (arvgvspprivate.h L257-280). Capture shows trailer packet id 194 with 1414-byte payload frames. 262144/1364 = 192.2, so 193 data packets plus leader (id 0) and trailer (id 194). |
| C9 | partially-supported | Resend command layout is correct (arvgvcp.c L405-441). Capability bit 0x934 bit 2 is correct (arvgvcpprivate.h L95-98, arvgvdevice.c L2071-2072, L1904-1905). Defaults are correct (arvgvstreamprivate.h L33-36). The 0x800C/0x8011/0x8012 handling (disable resend for that frame) is at arvgvstream.c L922-927, not cited. Caveat on "status 0x0100": Aravis documents 0x0100 as "resent packet (BlackFly PointGrey camera support)" (arvgvspprivate.h L42). Wireshark accepts 0x0100 as success only in extended-ID mode (packet-gvsp.c L1808); there the standard marks resends with the header flag bit 0x01. Aravis's fake camera never writes reg 0x934 (arvfakecamera.c L1082-1091), which explains 0 resend requests. |
| C10 | partially-supported | The run logs match the claim: jumbo default buffer 9 completed / 10 failed; auto 21/0. However, the default-buffer run at 1400 B with no simulated loss also had 1 failure and 82 missing packets (run_clean.txt), so the "2% loss → 19/20 failed" run is confounded with buffer drops. These are single runs over Docker loopback only. |
| C11 | supported (refined) | Aravis `_compute_n_expected_packets` returns 0 for any leader payload type other than IMAGE, CHUNK, EXT_CHUNK and MULTIPART. That includes **RAW 0x0002 and FILE 0x0003**, not only compressed types (arvgvstream.c L267-318, L384-393). MULTIPART is supported. pyGigEVision stores payload_type (gvsp.py L613) but never reads it again. pyGigEVision also has a hard 2048×2048 pixel cap (gvsp.py L140, L222). |
| C12 | supported | The Baumer page (fetched with a browser UA; the /ca/ path returned 403 to WebFetch) says "10 GigE", Mono8 or YCbCr422_8, "Image Compression Mode" = JPEG, quality 30–100 %, "based on the GigE Vision 2.0 standard per JPEG payload type", and "can be saved directly into a JPEG file". Kinovea BaumerHelper.cs confirms ImageCompressionMode=JPEG and the Mono8/YCbCr422_8 check. |
| C13 | supported | FLIR: "Teledyne FLIR proprietary format", Mono8/BayerRG8, Spinnaker 2.4.0.143+; it also adds chunk data (ChunkCompressionMode/Ratio). Basler: ImageCompressionMode=BaslerCompressionBeyond, Lossless/FixRatio, CImageDecompressor; the constructor reads the "compression descriptor … from the camera's node map". LUCID: QOI_Mono8, QOI_BayerRG8 etc. as PixelFormat; Arena DecompressImage uses qoi_decode (page updated 2025-10-28). |
| C14 | supported | Arithmetic reproduces: 1464/1538 × 125 MB/s = 118.98; 8964/9038 × 125 = 123.98; 138.24 MB/s; 51.6 fps; 1.72×; 2.15/4.3/8.6 (1500 B). The 2.5 GbE figure of 2.2 is the jumbo or rounded value. |
| C15 | supported | arvcamera.c L3521-3550: `value = tick_frequency * delay_ns / 1e9`. Beckhoff: GevSCPD "in device-specific hardware ticks"; DeviceLinkThroughputLimit "camera firmware calculates the required packet delay". |
| C16 | partially-supported | Literally true for `src/`. But at the same commit Aravis's GStreamer plugin has PTP-aware code: `gst/gstaravis.c` L563-567 and L631-640 add the `add-reference-timestamp-meta` property (timestamp/x-ptp caps), committed ee31d82f1 on 2026-10-03. Tick frequency is read from 0x93C/0x940 in arvgvdevice.c L570-592. |
| C17 | refuted | The heuristic is disabled by default (packet-gvsp.c L3640), but GVSP is **not** heuristic-only. It is registered for Decode-As on udp.port (L3639), and the GVCP dissector auto-registers GVSP on whatever port is written to SCP0–3 via WRITEREG (packet-gvcp.c L1728-1736). Test: tshark 4.2.2 on the researcher's gev_clean.pcap **without** `--enable-heuristic` decoded 4095 GVSP packets. On a stream-only capture (port 3956 filtered out) the packets show as UDP until `-d udp.port==35957,gvsp` is given. |

## Test run (Docker, existing image gev-ft-research = Ubuntu 24.04, tshark 4.2.2)

```
docker run --rm -v "<scratch>/scripts-ft/out:/out:ro" gev-ft-research bash -c '
 tshark -r /out/gev_clean.pcap -T fields -e _ws.col.Protocol | sort | uniq -c            # 261 GVCP, 4095 GVSP
 tshark -r /out/gev_clean.pcap --enable-heuristic gvsp_udp -T fields -e _ws.col.Protocol | sort | uniq -c  # same
 tshark -r /out/gev_clean.pcap -Y "!(udp.port==3956)" -w /tmp/s.pcap
 tshark -r /tmp/s.pcap -T fields -e _ws.col.Protocol | sort | uniq -c                    # 4095 UDP
 tshark -r /tmp/s.pcap -d udp.port==35957,gvsp -T fields -e _ws.col.Protocol | sort | uniq -c  # 4095 GVSP'
```

## Missed points (each opened)

- **Aravis GStreamer PTP reference timestamp.** `aravissrc add-reference-timestamp-meta` attaches the absolute device timestamp with `timestamp/x-ptp` caps. Code: https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L563-L567 and #L1203-L1209.
- **pyGigEVision skips large frames.** It drops any frame with width×height > 2048×2048 (4.19 MP). For example, 2448×2048 5 MP sensors are logged "invalid dimensions" and never delivered: https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L140-L145
- **pyGigEVision status names disagree with Aravis and Wireshark.** It labels 0x800C as PACKET_NOT_YET_AVAILABLE, 0x800D as PACKET_AND_PREV_REMOVED and 0x800E as PACKET_REMOVED. Aravis and Wireshark use 0x800C PACKET_UNAVAILABLE, 0x8010 NOT_YET_AVAILABLE, 0x8011 and 0x8012: https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L62-L71 vs https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L82-L88
- **LUCID GVRSP knowledge base (updated 2026-09-17).** GVRSP is available only on LUCID 10G+ cameras (Atlas10 fw ≥ 1.48, Triton10 fw ≥ 1.18, Atlas25). It needs specific LUCID/Broadcom NICs. In Arena, `DeviceStreamProtocol` is Automatic/GVRSP/GVSP/Legacy. GevSCPSPacketSize and GevSCPD become invisible in GVRSP mode, and resend is built into the transport. A GEV 3.0 device reports DeviceTLVersionMajor = 3: https://support.thinklucid.com/knowledgebase/using-gige-vision-rdma-streaming-protocol-in-gige-vision-3-0/
- **LUCID PTP app note** (https://support.thinklucid.com/app-note-multi-camera-synchronization-using-ptp-and-scheduled-action-commands/):
  - It states PTP "has been integrated into GigE Vision 2.0". This is direct vendor confirmation that single-cable sync is a 2.0 feature.
  - Nodes used: PtpEnable, PtpSlaveOnly, PtpStatus, PtpDataSetLatch/PtpDataSetLatchValue, ActionDeviceKey/GroupKey/GroupMask, ActionCommandExecuteTime, TriggerSource=Action0.
- **A3 standard page** also lists GEV 2.2 (June 2022, GenDC streaming): https://www.automate.org/vision/vision-standards/vision-standards-gige-vision
- **Version mismatch.** The researcher's Docker tests ran Aravis 0.8.36 (scripts-ft/Dockerfile, commit 97ff5e33). All code links point at 482547a (0.9.2+29).
- **Wireshark auto-learns the GVSP port** from GVCP WRITEREG to SCP0–3 (packet-gvcp.c L1728-1736). The stand-alone pcap test therefore only needs a heuristic or Decode-As when the capture starts after stream setup.
