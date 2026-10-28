# spec-versions

## Bottom line
- **The premise needs correcting.** IEEE 1588 PTP and Scheduled Action Commands were added in **GigE Vision 2.0 (Nov 2011)**, not 3.0. GigE Vision 2.1 (Aug 2018) then added an "updated profile for IEEE1588".
- **GigE Vision 3.0 adds RDMA streaming.** The GigE Vision Technical Committee approved it on 17 Apr 2026 and A3 announced the release on 12–13 May 2026. It adds RDMA over RoCEv2 through a new **GVRSP** streaming protocol, and a larger control-channel packet size. None of the A3 3.0 pages I read (the press release, FAQ, standard page and Industry Insight article) mention PTP, IEEE 1588 or time sync.
- **"Single cable" is PoE plus PTP plus scheduled action commands.** PoE comes from IEEE 802.3af/at, a separate standard from GigE Vision.

## Timeline
Sources: the [A3 GigE Vision standard page](https://www.automate.org/vision/vision-standards/vision-standards-gige-vision) plus the dated press releases linked below.
- **1.0, May 2006.** Covers discovery, GVCP (control), GVSP (streaming) and the GenICam XML description ([A3 2006 press release](https://www.automate.org/news/gige-vision-interface-standard-has-strong-european-debut-at-vision-2006), [Control Design](https://www.controldesign.com/articles/2007/016)).
- **1.1, announced 23 Apr 2009.** Added new pixel and Bayer formats, better error handling, and "action commands … to multiple devices simultaneously as well as managing the execution time" ([A3 press release](https://www.automate.org/news/gige-vision-version-1-1-interface-standard-released)).
- **1.2, Jan 2010.** Added control of non-streaming devices ([A3 press release](https://www.automate.org/vision/news/gige-vision-camera-interface-standard-version-1-2-released)).
- **2.0, Nov 2011.** Added 10GigE, link aggregation, compressed images (JPEG, JPEG 2000, H.264), multi-camera sync and multi-tap sensor support. The EMVA SFNC change history (the GenICam standard feature names document) lists for 2.0: IEEE 1588, unconditional and scheduled action commands, the ActionLate event, PAUSE frames and extended IDs ([SFNC 2.8 PDF](https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_8.pdf), pp. 29-30). The Wireshark dissectors mark these as "2.0 support" ([packet-gvcp.c L416-L482](https://github.com/wireshark/wireshark/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L416-L482)). Payload types JPEG 0x6, JPEG2000 0x7 and H264 0x8 are marked "GEV 2.0" ([packet-gvsp.c L43-L54](https://github.com/wireshark/wireshark/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L43-L54)).
- **2.1, Aug 2018.** Added multi-part payload (0xA) and the updated IEEE1588 profile. New registers list the supported profiles (bits for a "PTP profile" and an "802.1AS profile") and the selected profile ([packet-gvcp.c L3380-L3398](https://github.com/wireshark/wireshark/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L3380-L3398)). The IEEE 1588 profile registry lists "GigE Vision 2.1" as a PTP profile document ([IEEE SA](https://sagroups.ieee.org/1588/ptp-profiles)).
- **2.2, Jun 2022.** Added GenDC streaming (payload 0xB), multi-event data, and deprecated MultiZone.
- **3.0, 2026.** Adds RoCEv2 and GVRSP as a supplement to GVSP v2. It drops legacy GVSP v1, RDMA is optional, and it needs a RoCEv2 NIC and a GVRSP-capable library ([A3 FAQ](https://www.automate.org/vision/blogs/gige-vision-3-0-standard-answers-to-frequently-asked-questions-faq), [A3 press release](https://www.automate.org/vision/news/a3-officially-releases-gige-vision-3-0-opening-new-possibilities-in-machine-vision)). GVCP is kept for discovery and configuration ([A3 RoCEv2 page](https://www.automate.org/vision/vision-standards/rocev2-integration-into-gige-vision-standard-a-leap-forward-in-imaging-technology)).

## PTP edition
- SFNC 2.8 (dated 2026-04-08) tells readers to "Refer to the IEEE 1588-2008 specification" for PtpStatus.
- Basler's PTP documentation says "IEEE 1588-2008, also known as PTP Version 2" ([Basler docs](https://docs.baslerweb.com/precision-time-protocol)).
- I found no source linking any GigE Vision version to IEEE 1588-2019.

## How a host tells which version a camera implements
- **Version register at 0x0000:** major version in the upper 16 bits, minor in the lower 16. It is also the first field of the DISCOVERY_ACK reply, so you can read it during discovery.
- **GVCP Capability register at 0x0934** (big-endian masks, from the Wireshark hf definitions at [L3468-L3502](https://github.com/wireshark/wireshark/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L3468-L3502)):
  - 0x00080000: IEEE1588
  - 0x00020000: Scheduled Action
  - 0x00100000: Unconditional Action
  - 0x00010000: IEEE1588 extended capabilities (2.1)
  - 0x00000040: Action
- **Other registers:**
  - 0x0954 bit 0x00080000: enables 1588
  - 0x096C: 1588 status
  - 0x0970: scheduled-action queue size
  - 0x0974 to 0x097C: profile registers (2.1)
  - 0x090C: action device key
  - 0x9800 + 0x10·n: action group key/mask n
- **ACTION_CMD** is command 0x0100. When header flag 0x80 is set it carries a 64-bit scheduled time ([L2092-L2114](https://github.com/wireshark/wireshark/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L2092-L2114)).
- **Aravis** (main @482547a3, 2026-10-22; latest release 0.8.36 from 2026-04-26) defines only a subset of the capability bits. It has no host-side ACTION_CMD and no PTP register code ([arvgvcpprivate.h L95-L113 and L267-L282](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L267-L282)).
- **RDMA/GVRSP:** neither Aravis nor Wireshark has any RDMA, RoCE or GVRSP code.

## Test I ran
I wrote a stdlib-only raw GVCP register-read probe (`probe.py`) and ran it in `ubuntu:24.04` against `arv-fake-gv-camera-0.8` (aravis 0.8.30) over loopback.
- **Stock fake camera:** Version=0 and Capability=0. The emulator doesn't fill these registers in, so **it cannot emulate PTP or scheduled actions**.
- **With test values written in:** I wrote 0x00020001 into 0x0000 and 0x001B0067 into 0x0934 with `arv-tool`. The probe then decoded "2.1" plus IEEE1588, ScheduledAction, UnconditionalAction and the other set bits. That confirms the read-and-decode path works end to end.
- **On a real camera:** `python3 -I probe.py <camera-ip>` reports its real version and capabilities.
- Exact commands and outputs are in `RUN.txt`.

## Open questions

- I could not read the GigE Vision 3.0 spec text because A3 puts it behind a HubSpot registration form. Does 3.0 change anything for PTP, for example by adding an IEEE 1588-2019 profile, changing timestamps, or defining how GVRSP carries timestamps?
- What enumeration values does the IEEE1588 Selected Profile register (0x097C) take? Does the 2.1 'PTP profile' mean the IEEE 1588-2008 Default Delay Request-Response profile? Wireshark shows only the raw 5-bit value.
- When did plain (non-scheduled) action commands first appear? The A3 1.1 press release from 2009 credits 1.1 with action commands, but Wireshark groups the Action capability bit under its 'Added for 2.0 support' comment. SFNC is consistent with scheduled and unconditional actions arriving in 2.0.
- What value does a GigE Vision 3.0 device report in the Version register, and is there a capability bit or register for GVRSP? None of the open-source code I checked defines these.
- Is there a sourced figure for real PTP sync accuracy over a PoE switch? Vendors give only network-dependent statements. The roughly 9 µs spread across 7 cameras in LUCID's sample output is my own calculation from their printed timestamps, not a figure they state.

## Verification: Counter({'supported': 11, 'refuted': 1, 'partially-supported': 1})

- [refuted] C8: The GenICam/SFNC PTP feature set (PtpEnable, PtpStatus, PtpOffsetFromMaster, etc.) references IEEE 1588-2008; the Ptp* features were added in SFNC 2.4 (June 2018) replacing deprecated GevIEEE1588*; SFNC 2.8 (2026-04-08) contains no RDMA/GVRSP features.
  REASON: The first parts check out:
- The Ptp* feature set was added in SFNC 2.4, which deprecated the Gev1588 features. The release row is dated 26.6.2018 (p.35).
- PtpStatus (27.3.5, p.532) says "Refer to the IEEE 1588-2008 specification".

The claim that SFNC 2.8 has no RDMA/GVRSP features is false:
- The 2.8 change history (p.37) says "Added GevStreamingMode, GevControlChannelMaxPacketSize and ControlChannelLargePacketSize".
- 27.4.57 GevStreamingMode (pp.560-561) is an IEnumeration with values GVSP and GVRSP: "Returns the currently used streaming protocol ... set by the receiver."
- 27.4.51 GevControlChannelMaxPacketSize (p.558) says the minimum is 576 B.
  CORRECTED: SFNC 2.4 (released 26 June 2018) added the Ptp* features (PtpEnable, PtpStatus, PtpOffsetFromMaster, etc.) and deprecated the GevIEEE1588* features. PtpStatus refers readers to IEEE 1588-2008. SFNC 2.8 (2026-04-08) already includes GigE Vision 3.0-related features: GevStreamingMode {GVSP, GVRSP}, GevControlChannelMaxPacketSize and ControlChannelLargePacketSize.
  BETTER: ['https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_8.pdf']

- [partially-supported] C12: Aravis (main @482547a3, 2026-10-22) has no host-side ACTION_CMD or PTP register support (GVCP command enum ends at PENDING_ACK 0x0089; only Action bit defined among action/PTP capability bits), and neither Aravis nor Wireshark contains any RDMA/RoCE/GVRSP code.
  REASON: The Aravis part is verified on a clone of 482547a3, committed 2026-10-22:
- The ArvGvcpCommand enum ends at PENDING_ACK 0x0089.
- Among action/PTP capability bits only ACTION (1<<6) is defined; ERROR_ACTION_LATE 0x16 is also defined.
- A word-boundary grep of src/ for ptp, 1588, rdma, roce and gvrsp finds nothing.

The claim is wrong for Wireshark as a whole. packet-infiniband.c at the same commit has DEFAULT_RROCE_UDP_PORT 4791 (L33-L34) and dissect_rroce/dissect_roce (L1760-L1799), so Wireshark does dissect RoCE/RoCEv2. The GVCP/GVSP dissectors have no RDMA or GVRSP code. Separately, the Aravis GStreamer element (gst/gstaravis.c L563-L567) does handle PTP-based timestamps (timestamp/x-ptp meta), though not PTP registers.
  CORRECTED: Aravis main @482547a3 (2026-10-22) has no host-side ACTION_CMD, no IEEE1588 bootstrap register code and no RDMA/RoCE/GVRSP code. Its GStreamer element can label buffer timestamps as PTP time. Wireshark's GVCP/GVSP dissectors have no GVRSP support, but Wireshark has a generic RoCE/RRoCE (RoCEv2, UDP 4791) dissector in packet-infiniband.c.
  BETTER: ['https://github.com/wireshark/wireshark/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-infiniband.c#L33-L34', 'https://github.com/wireshark/wireshark/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-infiniband.c#L1760-L1799', 'https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L563-L567']

## Missed points

- SFNC 2.8 (2026-04-08) already defines GenICam features for GigE Vision 3.0. GevStreamingMode (27.4.57, pp.560-561) takes the values GVSP or GVRSP and is set by the receiver. GevControlChannelMaxPacketSize (27.4.51, p.558) has a minimum of 576 B. ControlChannelLargePacketSize was added too, per the 2.8 history on p.37. A host can therefore detect GVRSP use and support via the GenICam XML: https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_8.pdf
- The SFNC 2.8 history (p.37) says "Set the unit to ns for all the Timestamp related features". This matters for interpreting PTP-based frame timestamps: https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_8.pdf
- IEEE 1588 is OPTIONAL in GigE Vision. Vision Systems Design (2017-10-18) calls it "the optional IEEE 1588 Precision Time Protocol". A 2.x or 3.0 camera need not support PTP, so the host must check capability bit 0x00080000 or whether PtpEnable/GevIEEE1588 exists: https://www.vision-systems.com/home/article/16737583/standards-update-gige-vision-standard-status-and-future-what-you-need-to-know
- Vendors use different PTP feature names. Basler's docs tell users to set GevIEEE1588, GevIEEE1588Status and GevIEEE1588OffsetFromMaster, the names SFNC 2.4 deprecated. LUCID uses PtpEnable, PtpSlaveOnly, PtpStatus, ActionDeviceKey, ActionGroupKey, ActionGroupMask and ActionCommandExecuteTime. Host code has to handle both sets: https://docs.baslerweb.com/precision-time-protocol and https://thinklucid.com/multi-camera-synchronization-using-ptp-and-scheduled-action-commands/
- Basler ace Classic/U/L cameras switch their timestamp tick from 125 MHz to 1 GHz when PTP is enabled; other Basler cameras always use 1 GHz. Basler recommends a 2 s ANNOUNCE and 0.5 s SYNC interval and says precision "depends to a large extent on your network hardware": https://docs.baslerweb.com/precision-time-protocol
- LUCID's procedure enables PtpEnable and waits for the PtpStatus Master/Slave state. It sets TriggerSource=Action0, ActionUnconditionalMode=On and the device/group keys and mask. It then reads PTP time from the master, adds a delta and sets ActionCommandExecuteTime before firing a scheduled action. It also uses TransferControlMode=UserControlled to avoid packet loss when all cameras transmit at once: https://thinklucid.com/multi-camera-synchronization-using-ptp-and-scheduled-action-commands/
- Wireshark has a generic RoCE/RRoCE (RoCEv2, UDP 4791) dissector. It can decode the transport GVRSP rides on, though not GVRSP semantics, which is useful for debugging 3.0 RDMA cameras: https://github.com/wireshark/wireshark/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-infiniband.c#L1760-L1799
- Aravis's GStreamer element attaches a timestamp/x-ptp reference meta, treating the device timestamp as PTP-timescale ns when the camera is PTP-synchronised. gstaravis.c was last changed 2026-10-03 (commit ee31d82f): https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L563-L567
- Aravis 0.9.2, a prerelease in the development series, was published on GitHub on the same day as stable 0.8.36 (2026-04-26T07:18Z vs 07:13Z). The researcher listed only 0.8.36: https://github.com/AravisProject/aravis/releases/tag/0.9.2
- The A3 Industry Insight (2026-08-04) quotes A3's Bob McCurrach: "I've got six camera companies who already have cameras out" for 3.0. It also says 3.0 arrived about four years after 2.2. 3.0 hardware exists, but which models support PTP is not stated: https://www.automate.org/vision/industry-insights/gige-vision-3-0-brings-fast-data-transfers-at-mass-market-prices
- The A3 standard page has a copy error: its 2.0 paragraph says "Version 2.0 included non-streaming device control". The A3 1.2 press release (2010-01-21) shows 1.2 introduced that feature, so the standard page should not be relied on alone for per-version features: https://www.automate.org/vision/news/gige-vision-camera-interface-standard-version-1-2-released