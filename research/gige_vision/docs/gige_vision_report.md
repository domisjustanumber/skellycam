# GigE Vision Support for SkellyCam — Research Report

Oct 25, 2026 · Dom

> Exported on 2026-10-28 from the online doc this study was first written in. This file is now the canonical copy; corrections made after export are marked "(corrected 2026-10-28; was ...)".

## GigE Vision versions: PTP came in 2.0, not 3.0

Single-cable PTP sync does not need GigE Vision 3. IEEE 1588 PTP and Scheduled Action Commands were added in **GigE Vision 2.0 (Nov 2011)**. GigE Vision 3.0 (May 2026) adds RDMA streaming. The "single cable" is PoE (IEEE 802.3af/at, a separate standard) carrying power, data and PTP packets together.

| Version | Released | What it added that matters here |
| --- | --- | --- |
| 3.0 | TC-approved 17 Apr 2026, released 12 May 2026 | Optional RDMA streaming over RoCEv2 (new GVRSP protocol) at 10G and up, a larger control-channel packet, and drops legacy GVSP v1. A RoCEv2 NIC is needed for RDMA. No PTP changes found in A3's 3.0 press release, FAQ or standard page ([press release](https://www.automate.org/vision/news/a3-officially-releases-gige-vision-3-0-opening-new-possibilities-in-machine-vision), [FAQ](https://www.automate.org/vision/blogs/gige-vision-3-0-standard-answers-to-frequently-asked-questions-faq)) |
| 2.2 | Jun 2022 | GenDC streaming payload (0x000B), multi-event data |
| 2.1 | Aug 2018 | Multi-part payload (0x000A); updated IEEE 1588 profile registers at 0x0974–0x097C, with bits for the PTP and 802.1AS profiles ([Wireshark packet-gvcp.c](https://github.com/wireshark/wireshark/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L3380-L3398)) |
| 2.0 | Nov 2011 | **IEEE 1588 PTP, scheduled and unconditional action commands**, compressed payloads (JPEG 0x6, JPEG 2000 0x7, H.264 0x8), 10GigE, link aggregation, 64-bit extended block IDs ([SFNC 2.8 change history, pp. 29–30](https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_8.pdf); [packet-gvsp.c L43–54](https://github.com/wireshark/wireshark/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L43-L54)) |
| 1.0–1.2 | 2006–2010 | Discovery, GVCP control, GVSP streaming, GenICam XML; 1.1 introduced action commands with no time synchronisation ([A3 1.1 release](https://www.automate.org/news/gige-vision-version-1-1-interface-standard-released)) |

**PTP is optional in every version.** A 2.x or 3.0 camera may lack it, so check before you buy:

- The Version register (0x0000, also returned in the discovery reply) gives major.minor. A GEV 3.0 device reports major 3.
- The GVCP Capability register (0x0934) must have bit 0x00080000 (IEEE 1588) and bit 0x00020000 (scheduled action) set ([Wireshark L3468–3502](https://github.com/wireshark/wireshark/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L3468-L3502)).
- Our `gev_probe.py` reads both registers (see Tests).

**SFNC 2.8 (Apr 2026) has GenICam features for 3.0** ([SFNC 2.8](https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_8.pdf)):

- `GevStreamingMode` takes the values `GVSP` or `GVRSP`.
- `GevControlChannelMaxPacketSize` sets the larger control packet.

PTP feature text still refers to IEEE 1588-2008. No GEV version is tied to 1588-2019 in anything we found.

No open-source library implements GVRSP. We checked Aravis, viva-genicam, telegenic and rc\_genicam\_api. **A GEV 3.0 camera on 1 GbE or 2.5 GbE uses ordinary GVSP UDP streaming**, which every library here supports.

## How frames arrive: raw, uncompressed, over UDP

GigE Vision cameras normally send **uncompressed raw pixels**: Bayer or Mono in a standard PFNC pixel format, such as `BayerRG8`, `Mono8` or `BayerRG12p`. The host does the debayering. Compression exists in the standard but is rare, and none of the open-source stacks checked (Aravis, Harvesters, pyGigEVision, viva-genicam) decodes it (corrected 2026-10-28; was "no open-source receiver decodes it").

**Two UDP channels:**

- **GVCP (control).** The host sends request/ack commands to camera UDP port 3956 ([Aravis arvgvcpprivate.h L36](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L36)). It covers:
  - discovery
  - register reads and writes
  - GenICam XML download
  - packet-resend requests
  - action commands
- **GVSP (stream).** A one-way UDP flow to the host IP and port that the host writes into stream-channel registers ([Wireshark packet-gvcp.c L148–160](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L148-L160)):
  - `0x0D00` host port
  - `0x0D04` packet size
  - `0x0D08` inter-packet delay
  - `0x0D18` destination IP

**One frame is one block:** a leader packet, N payload packets, and a trailer packet.

- The **leader** carries the payload type, a **64-bit device timestamp**, the PFNC pixel format, width and height, and offsets ([Aravis arvgvspprivate.h L452–463](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L452-L463)).
- Block IDs are 16-bit, or 64-bit in GEV 2.0+ extended-ID mode ([arvgvspprivate.h L132–144](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L132-L144)).
- **Lost packets:** the host sends `PACKETRESEND` (0x0040) over GVCP. Resend works only if the camera advertises capability bit 2 in 0x0934 ([Aravis arvgvdevice.c L2071–2072](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L2071-L2072)).

**Tested in Docker:** Aravis's software camera, captured with tcpdump and decoded with tshark, produced the leader `IMAGE, Mono8 0x01080001, 512x512`. With a 1400-byte packet size, the trailer arrived at exactly the predicted `packet_id` 194.

| Payload type | Code | Compressed? | Who decodes it |
| --- | --- | --- | --- |
| Image | 0x0001 | No (raw PFNC) | Everyone. This is what cameras send by default |
| Chunk data appended | flag 0x4000 | n/a | Carries per-frame metadata such as `ChunkTimestamp` |
| JPEG | 0x0006 | Lossy | Example: [Baumer VLXT.I.JP](https://www.baumer.com/ca/en/service-support/technology-highlights/industrial-cameras-with-integrated-jpeg-image-compression/a/JPEG-image-compression). Aravis marks it not supported ([arvbuffer.h L64–92](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvbuffer.h#L64-L92)) |
| JPEG 2000 / H.264 | 0x0007 / 0x0008 | Yes | Defined in GEV 2.0. We found no shipping camera that documents using them |
| Multi-part / GenDC | 0x000A / 0x000B | Varies | 2.1 / 2.2 features |
| Vendor lossless | proprietary | Lossless | [Teledyne FLIR](https://www.teledynevisionsolutions.com/support/support-center/application-note/iis/using-lossless-compression/), [Basler Compression Beyond](https://docs.baslerweb.com/compression-beyond), [LUCID QOI](https://support.thinklucid.com/knowledgebase/using_qoi_with_lucid_cameras/). Each needs its vendor SDK to decode |

**Bandwidth is the real constraint.** 1920×1200 BayerRG8 at 60 fps is 138 MB/s, or 1106 Mbit/s. That does not fit on one 1 GbE link: usable throughput is about 119 MB/s at MTU 1500 and about 124 MB/s with jumbo frames. The same stream at 30 fps fits one camera per link. Several cameras behind one switch uplink need the per-camera bandwidth limit `DeviceLinkThroughputLimit`, or a packet delay ([Beckhoff](https://infosys.beckhoff.com/content/1033/tf7xxx_tc3_vision/22185723659.html)).

**The host socket buffer decides whether frames arrive complete.** Each frame lands in one burst.

- **Default Linux buffer:** in our tests against the emulated camera, most frames lost their tail, even at 50 Mbit/s.
- **Buffer forced to 32 MiB:** 75 of 75 frames were complete.
- **OS caps on buffer size:**
  - Linux: `net.core.rmem_max`
  - macOS: `kern.ipc.maxsockbuf`, 8 MiB by default ([xnu socketvar.h L193](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/sys/socketvar.h#L193))
  - Windows: 64 KiB by default on the test machine

## How PTP sync timing is managed

PTP sync has two layers.

1. **Clock sync.** PTP gives every camera the same clock to within about 1 µs.
2. **Trigger sync.** A separate mechanism uses that shared clock to start exposures at the same instant: scheduled action commands or a vendor sync mode.

Clock sync alone only gives matching timestamps, not matching exposures.

### 1. Clocks: PTP on the camera

**Turn it on with GenICam features** ([SFNC 2.8 §27.3](https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_8.pdf)):

- Set `PtpEnable`.
- Execute `PtpDataSetLatch`, then read `PtpStatus` and `PtpOffsetFromMaster`.
- `PtpStatus` values: Initializing, Faulty, Disabled, Listening, PreMaster, Master, Passive, Uncalibrated, Slave.

**Older and vendor firmware uses different names**, so software must try both sets and read enumerations by name:

- Older firmware uses the deprecated `GevIEEE1588`, `GevIEEE1588Status` and `GevTimestampControlLatch` ([Basler](https://docs.baslerweb.com/precision-time-protocol)).
- Allied Vision uses `PtpMode` Off, Slave, Master or Auto, and numbers `PtpStatus` from 0 ([AV app note](https://www.alliedvision.com/assets/support/Camera-Documentation/Allied-Vision/FAQs-Application-Notes/PTP_IEEE1588_with_Prosilica_GT_GC_Manta.pdf)).
- LUCID adds `PtpSlaveOnly` ([LUCID](https://support.thinklucid.com/?p=4184)).

**The grandmaster is elected.** The cameras run the IEEE 1588 Best Master Clock Algorithm, and one camera becomes Master with no host involvement. The shared timescale is then arbitrary, not UTC.

- **Linux host as grandmaster:** run `ptp4l` from linuxptp ([man page](https://github.com/richardcochran/linuxptp/blob/f98cb5de87e63696599c59d0a9df7dc04d08d40d/ptp4l.8#L48-L62)). Allied Vision measured "significant jitter" with host software masters.
- **Windows:** the built-in PTP is a client only (Windows 10 1809 and later, [W32Time](https://github.com/microsoft/W32Time/blob/9795ef91dfe5a452266ffd8106ff2bcb17f33556/README.md#L25-L36)). It also refuses grandmasters without valid UTC flags, so it is not a reliable way to slave the PC to the cameras.
- **macOS:** we found no supported PTP option.

**Network:**

- PTP uses UDP 319/320, multicast to 224.0.1.129.
- **IGMP snooping on the switch breaks PTP on Basler cameras.** Disable it, then power-cycle the cameras ([Basler KB](https://docs.baslerweb.com/knowledge/ptp-synchronization-doesn't-work-when-igmp-snooping-is-enabled)).
- Vendors recommend one subnet behind one switch, ideally a PTP-aware switch with transparent clock support.
- A PoE switch makes it one cable per camera.

**Accuracy figures from vendors:**

| Source | Figure |
| --- | --- |
| Allied Vision | Defines sync as all slaves within 2 µs. Measured under ±1 µs over 69 h, and about 125 ns between two cameras on a scope |
| Teledyne | "Within a few microseconds" |
| LUCID | Sample output implies about 9 µs spread across 7 cameras (our arithmetic from their printout) |

### 2. Exposures: three ways to line them up

**(a) Scheduled Action Commands.** This is the standard method and works with any vendor.

- **Camera setup:** `TriggerSelector=FrameStart`, `TriggerMode=On`, `TriggerSource=Action1`, plus `ActionDeviceKey`, `ActionGroupKey` and `ActionGroupMask`.
- **Each frame:** the host broadcasts one GVCP `ACTION_CMD` (0x0100). Flag 0x80 marks it scheduled, and the payload carries a 64-bit PTP execution time, for example the latched camera time plus 20 ms ([Wireshark L2092–2114](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L2092-2114)).
- Each camera queues the command and fires when its PTP clock reaches that time, so network latency doesn't matter.
- Not every camera supports it. Many Basler models don't ([Basler](https://docs.baslerweb.com/scheduled-action-commands)), and an Allied Vision Manta answered NOT\_IMPLEMENTED ([viva-genicam action.rs](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-gige/src/action.rs#L57-L68)).

**(b) Vendor PTP free-run modes.** Every camera starts at the same PTP time, then runs at the same rate with no per-frame host traffic. These are vendor-specific:

- Basler Synchronous Free Run: `SyncFreeRunTimerStartTimeLow/High`
- LUCID: `AcquisitionStartMode=PTPSync` with `PTPSyncFrameRate`
- Allied Vision: `PtpAcquisitionGateTime`

**(c) Free-run and match afterwards.** Cameras run unsynchronised, and frames are paired by the PTP timestamp in each GVSP leader or `ChunkTimestamp`. This is the simplest method, but pairing error can be up to half a frame period.

**Mapping camera time to PC time:**

1. Read the host clock.
2. Execute `TimestampLatch` (bootstrap: write 2 to 0x0944, read 0x0948/0x094C).
3. Read the host clock again.

The error is about half the round trip, typically well under 1 ms. Enable PTP *before* creating streams: some stacks cache the tick frequency when the stream is created ([Aravis arvgvstream.c L1617](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L1617)), and Basler ace Classic cameras change tick rate when PTP is enabled.

**Emulators can't test any of this.** Aravis's emulator has no PTP, action or timestamp-latch support (tested). viva-genicam's emulator acknowledges action commands only when the keys match (tested). Real accuracy needs real cameras: see the Tests section.

## Library options compared

viva-genicam is the best fit, and the only open-source library found that sends scheduled action commands (corrected 2026-10-28; was "the only open-source library"). pyGigEVision, the suggested candidate, is not a usable base. All candidates enable PTP the same way, through generic GenICam feature writes. They differ in action-command support, packaging, and vendor lock-in.

| Option | Language / license | Win / mac / Linux | Any vendor's camera | Scheduled action cmds | Last release | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| [viva-genicam](https://github.com/VitalyVorobyev/viva-genicam) | Rust + Python wheels, MIT | Yes / arm64 only / x86\_64 | Yes (own GVCP/GVSP) | **Yes**: `send_action` ([gige.rs](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/gige.rs#L40-L66)); wire format checked in tshark | 0.10.0, 2026-10-17 | **Chosen.** Pip-installable and has a fake camera for CI. Young (first release Apr 2026), single maintainer, no PTP helpers ([backlog](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/docs/backlog.md#L41-L44)) |
| [telegenic](https://github.com/valstad-shipworks/telegenic) (`telegenicam`) | Rust + Python wheels, Apache-2.0 | Yes / arm64 / x64 + aarch64 | Yes | No | 2.1.0, 2026-10-20 | Good fallback. Streamed from the Aravis emulator in our test |
| [Aravis](https://github.com/AravisProject/aravis) | C, LGPL-2.1+ | Linux first; macOS via Homebrew; Windows via MSYS2, lagging | Yes | No ([issue #184](https://github.com/AravisProject/aravis/issues/184), open since 2018) | 0.8.36, Apr 2026 | Mature, but not on PyPI or conda-forge, and PyGObject has no wheels. Windows throughput issue [#752](https://github.com/AravisProject/aravis/issues/752) is open |
| Harvesters + GenTL producer | Python, Apache-2.0, plus a vendor .cti | Depends on the producer | Depends on the producer | Only if the producer has interface `ActionCommand` ([GenTL SFNC 1.2](https://www.emva.org/wp-content/uploads/GenICam_GenTL_SFNC_1_2.pdf)) | 1.4.3, May 2024 | Stale. `fetch()` holds the GIL ([#508](https://github.com/genicam/harvesters/issues/508), reproduced). No free vendor-neutral producer covers all three OSes |
| [pyGigEVision](https://github.com/ladisk/pyGigEVision) | Pure Python, MIT | CI on Win + Linux | Yes | No, and no PTP | 0.2.2, 2026-07-08 | **Not suitable** (details below). Useful as reference code |
| Basler pypylon | Python wrapper + proprietary SDK | Yes / Yes / Yes | **No**: the EULA restricts use to Basler cameras ([EULA](https://docs.baslerweb.com/pylon-end-user-license-agreement)) | Yes | 26.9, 2026-10-23 | Basler-only |
| Allied Vision Vimba X / VmbPy | Python, BSD-2 + free SDK | Yes / no wheel / Yes | Third-party GenTL producers are allowed ([compat](https://docs.alliedvision.com/compatibility.html)) | Yes | vmbpy 1.2.3, 2026-10-06 | Vendor SDK install required |
| Spinnaker, Arena, eBUS | Proprietary | Varies | No, or watermarked | Varies | — | Vendor-locked |
| [cameleon](https://github.com/cameleon-rs/cameleon) | Rust, MPL-2.0 | — | **USB3 Vision only** ([README](https://github.com/cameleon-rs/cameleon/blob/1ab3fbf82a11f94da56e35a62893a6042054df4b/README.md#L28)) | — | 0.1.14, Dec 2024 | Not applicable |
| [rc\_genicam\_api](https://github.com/roboception/rc_genicam_api) | C++, BSD-3 + bundled Baumer producer | Yes / **No** / Yes | GEV 2.0 cameras | Not in its tools | v2.8.9, 2026-10-06 | No macOS |

**pyGigEVision, tested in Docker against the emulated camera:**

- **No feature access by name.** It only downloads the XML ([genicam.py L15–19](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/genicam.py#L15-L19)), so you cannot set `PtpEnable` or `PixelFormat`.
- **XML download fails.** It parses the hex XML address as decimal and downloads zeros. The GenTL 1.6 standard requires hex.
- **Colour frames are wrong.** Only Mono formats are known. BayerRG8 never completes, and RGB8 comes back truncated but flagged complete ([gvsp.py L164–197](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L164-L197)).
- **Large frames are dropped.** Anything over 2048×2048 pixels never arrives ([gvsp.py L140–145](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L140-L145)).
- **Too many resend requests.** On a lossless 1 GbE-rate stream it requested resends for 82.6% of packets.
- **The receiver thread can die silently.** On extended-ID cameras this happens once block IDs pass 65535.
- **It has no PTP or action-command code.**

**Writing from scratch is feasible but slow.** We wrote a stdlib-only Python client of about 830 lines that discovered the emulated camera, fetched its XML and streamed 75 of 75 complete frames. The hard part is GenApi, evaluating the camera's XML into named features: a Hikrobot XML has 2,165 nodes and 283 formulas.

| Approach | Estimated effort |
| --- | --- |
| Python + EMVA `genicam` wheel | 6–9 person-weeks |
| Rust + PyO3 | 10–16 person-weeks |
| C++ | 9–14 person-weeks |
| Adopt viva-genicam or telegenic | 1–3 person-weeks |

**Python receive throughput (measured):**

- One Python receiver kept up with 1 Gbit/s at 21–34% of a core.
- Four cameras' receiver threads in one process dropped 39–75% because of the GIL.
- One process per camera works, and that is SkellyCam's default worker mode.
