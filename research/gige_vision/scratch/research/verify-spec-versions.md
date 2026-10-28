# Fact-check: topic "spec-versions" (verifier notes, 2026-10-25)

All sources were re-downloaded independently into
`scratchpad/research/src/verify-spec-versions/` (curl of raw GitHub files at the pinned commits, curl of web pages
-> text, pdftotext of SFNC 2.8). One Docker test was re-run independently (see bottom).

Pinned code:
- Wireshark @ 98a6cfdba1ab23f3c835b17df802004bc9429040 (packet-gvcp.c, packet-gvsp.c, packet-infiniband.c)
- Aravis @ 482547a3d56e3aa8d22d7ffed33c9f1588bfe17a (main, committed 2026-10-22 21:22 +0200 "gcport: add ClTenFull to legacy list").
  GitHub releases API: 0.8.36 (stable) published 2026-04-26T07:13Z; 0.9.2 (prerelease) published 2026-04-26T07:18Z.

## Verdicts

| id | verdict | notes |
|----|---------|-------|
| C1 | supported (minor date fix) | A3 PR page meta date is **05/13/2026**; text: "During the spring IVSM, held April 13–17 in Prague, the GigE Vision TC officially approved..." and "introduced the GigE Vision RDMA Streaming Protocol (GVRSP)" and "expansion of the control channel, allowing for more data per packet". A3 standard page: "approved ... on Friday, April 17, 2026". No source I opened shows "12 May". |
| C2 | supported | A3 FAQ (meta date 08/19/2026) Q1/Q3/Q8/Q9 say exactly this. |
| C3 | supported (negative result reproduced) | grep of extracted text of all 4 pages + standard page for ptp/1588/timestamp/synchron: no hits in article bodies. RoCEv2 pre-announcement: "The current GigE Vision control protocol will be retained as the mechanism for device discovery and configuration." |
| C4 | supported | SFNC 2.8 p.29 change history: "Added GigE Vision 2.0 support: ActionLate event, link aggregation, PAUSE frames, extended and standard IDs, IEEE 1588, unconditional and scheduled action commands, extended status codes, multi-zone, alternate packet resend destination". A3 standard page: 2.0 (Nov 2011) "10 gigabit Ethernet and link aggregation ... compressed images (JPEG, JPEG 2000 and H.264), accurate synchronization of multi-camera systems". The A3 page itself does not say "IEEE 1588"; LUCID app note does: "PTP (IEEE1588) ... integrated into GigE Vision 2.0". Wireshark gvsp L48-L50 JPEG/JPEG2000/H264 "GEV 2.0". Caveat: plain (non-scheduled) Action Command predates 2.0 (A3 1.1 PR, 2009). |
| C5 | supported | gvcp.c L134-L136 define 0x0974/0x0978/0x097C; L3378-L3398 masks (0x0974 bit 0x80000000 = "Profile Registers Present"; 0x0978 0x80000000 PTP, 0x40000000 802.1AS); L3326-L3329 selected profile is a 5-bit field (mask 0x1F). IEEE SA profile registry row: "GigE Vision / Test and Measurement / AIA / GigE Vision 2.1". Vision Systems Design (2017-10-18): "revision 2.1 will feature a new profile to the optional IEEE 1588". |
| C6 | supported | A3 page: "updated from 2.1 to 2.2 in June of 2022. Primary enhancements include GenDC streaming and multi event data." gvsp.c L51 "GEV 2.0, deprecated with GEV 2.2" (MULTIZONEIMAGE 0x9), L53 GENDC 0x000B "GEV 2.2". |
| C7 | supported | 2006 PR (11/16/2006): "ratified last May"; Control Design: "In May 2006 ... first version ... ratified". 1.1 PR meta 04/23/2009 lists pixel/Bayer formats, error handling, multiple GenICam schema/GenAPI versions, action commands. 1.2 PR meta 01/21/2010: "control of non-streaming devices". Note: the A3 standard page wrongly copies "non-streaming device control" into its 2.0 paragraph. |
| C8 | **partially refuted** | Ptp* set added in SFNC 2.4 (release row "26.6.2018"), deprecating Gev1588 equivalents (p.35) — OK. PtpStatus (27.3.5, p.532): "Refer to the IEEE 1588-2008 specification" — OK. **But SFNC 2.8 DOES contain GVRSP**: change history (p.37) "Added GevStreamingMode, GevControlChannelMaxPacketSize and ControlChannelLargePacketSize"; 27.4.57 GevStreamingMode (pp.560-561) values GVSP / GVRSP; 27.4.51 GevControlChannelMaxPacketSize (p.558, min 576 B). |
| C9 | supported | Basler PTP doc: "support IEEE 1588-2008, also known as PTP Version 2"; "PTP timestamps are mapped to the 64-bit timestamps of GigE Vision"; ace 2/dart M BslPtpProfile = DelayRequestResponseDefaultProfile (default) or PeerToPeerDefaultProfile; other cameras preset E2E. |
| C10 | supported | Vision Systems Design 2017-10-18: action command lets integrators "remove an I/O cable and use only the Ethernet cable to provide data, power, and trigger". Basler 4-port PoE card lists IEEE 802.3af/802.3at as separate standards. LUCID: "Instead of wiring up multiple cameras for hardware triggering, these cameras can now be trigger[ed] simultaneously over Ethernet". |
| C11 | supported | Aravis arvgvcpprivate.h L38-L42 version masks; Wireshark gvcp.c L56 GVCP_VERSION 0x0000, L2140-L2144 DISCOVERY_ACK first field = version, L3468-L3502 capability masks, L196 ACTION_CMD 0x0100, L2515-L2518 flag 0x80 => scheduled, L2108-L2112 8-byte time. Aravis arvgvfakecamera.c L158-L162 builds DISCOVERY_ACK from bootstrap memory at offset 0. |
| C12 | **partially refuted** | Aravis part verified (enum ends 0x0089; only ACTION bit 1<<6; no 1588/ptp/rdma/roce/gvrsp in src/). But **Wireshark does contain RoCE/RRoCE code**: packet-infiniband.c L33-L34 `DEFAULT_RROCE_UDP_PORT 4791`, dissect_rroce L1760-L1781, dissect_roce L1783-L1799. True only for GVCP/GVSP dissectors (no GVRSP). Also Aravis GStreamer element does reference PTP (gst/gstaravis.c L563-L567, timestamp/x-ptp meta). |
| C13 | supported (reproduced) | Independent run below: R[0x0000]=0, R[0x0934]=0, also 0x0954 and 0x096C = 0. The registers are plain writable memory in the emulator, so writing bits only fakes advertising, not behaviour. |

## Independent test (reproduced C13)

Script: `scratchpad/research/tools-verify/fakecam_regs.sh`, run as
`MSYS_NO_PATHCONV=1 docker run --rm -v "<tools-verify>:/t:ro" ubuntu:24.04 bash /t/fakecam_regs.sh`
(installs `aravis-tools aravis-tools-cli` 0.8.30-1build2, starts `arv-fake-gv-camera-0.8 -i 127.0.0.1`, uses `arv-tool-0.8 control`).
Note: `arv-tool-0.8` is in package `aravis-tools-cli`, not `aravis-tools`.

```
R[0x00000000] = 0x00000000   (Version)
R[0x00000934] = 0x00000000   (GVCP Capability)
R[0x00000954] = 0x00000000   (GVCP Configuration)
R[0x0000096c] = 0x00000000   (IEEE1588 status)
R[0x0000093c] = 0x00000000   (tick freq high)
R[0x00000940] = 0x3b9aca00   (tick freq low = 1 GHz)
--- write test
R[0x00000000] = 0x00020001
R[0x00000934] = 0x001b0067
```

## Missed points (with links)
1. SFNC 2.8 (2026-04-08) already standardises GigE Vision 3.0 GenICam features: GevStreamingMode {GVSP, GVRSP}, GevControlChannelMaxPacketSize, ControlChannelLargePacketSize (p.37 history; 27.4.51 p.558; 27.4.57 pp.560-561). https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_8.pdf
2. SFNC 2.8 history: "Set the unit to ns for all the Timestamp related features" (p.37). Same PDF.
3. PTP is *optional* in GigE Vision (VSD 2017: "the optional IEEE 1588 Precision Time Protocol"); a 2.x/3.0 camera need not support it -> must check capability bit 0x00080000 / PtpEnable presence. https://www.vision-systems.com/home/article/16737583/...
4. Feature naming differs by vendor: Basler doc instructs GevIEEE1588 / GevIEEE1588Status / GevIEEE1588OffsetFromMaster (deprecated names), LUCID uses PtpEnable/PtpStatus/PtpSlaveOnly + ActionDeviceKey/ActionGroupKey/ActionGroupMask/ActionCommandExecuteTime. Host code must handle both.
5. Basler: ace Classic/U/L switch tick from 125 MHz to 1 GHz on PTP enable; others always 1 GHz. Recommended ANNOUNCE 2 s / SYNC 0.5 s. https://docs.baslerweb.com/precision-time-protocol
6. Wireshark's generic RoCE/RRoCE dissector (UDP 4791) can decode the RoCEv2 transport GVRSP rides on, though not GVRSP semantics. packet-infiniband.c L33-L34, L1760-L1799.
7. Aravis gst plugin attaches `timestamp/x-ptp` reference meta assuming device timestamp is PTP ns (gstaravis.c L563-L567; file last changed 2026-10-03, commit ee31d82f).
8. A3 Industry Insight 2026-08-04: "I've got six camera companies who already have cameras out" (3.0). https://www.automate.org/vision/industry-insights/gige-vision-3-0-brings-fast-data-transfers-at-mass-market-prices
9. A3 standard page has a copy error: attributes "non-streaming device control" to 2.0, whereas the 1.2 PR (2010-01-21) introduced it.
10. Aravis 0.9.2 (prerelease, dev series) released the same day as 0.8.36 (2026-04-26).
