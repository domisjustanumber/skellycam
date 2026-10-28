# ptp-sync

## Summary

**The premise needs correcting: PTP did not arrive with GigE Vision 3.** IEEE 1588 PTP and scheduled action commands both date from **GigE Vision 2.0**. Wireshark's GVCP dissector tags every IEEE 1588 bootstrap field and the scheduled-action flag and time as `_v2_0`, and `GEV_STATUS_ACTION_LATE` carries the comment `/* GEV 2.0 */` ([packet-gvcp.c](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L204-229)). Aravis issue [#184](https://github.com/AravisProject/aravis/issues/184), opened in 2018, says the same: "GigEVision 2.0 introduces Action Commands…". So single-cable PTP sync works with ordinary GEV 2.x cameras, including PoE ones.

### 1. Turning PTP on in the camera
- **Standard features:** GenICam SFNC 2.8 (2026-04-08), §27.3, defines `PtpEnable`, `PtpDataSetLatch`, `PtpStatus`, `PtpServoStatus`, `PtpOffsetFromMaster` (ns), `PtpClockAccuracy` and the clock-ID features.
  - `PtpStatus` values are Initializing, Faulty, Disabled, Listening, PreMaster, Master, Passive, Uncalibrated, Slave (numbered 1-9).
  - The values are *latched*: execute `PtpDataSetLatch` first, then read them.
  - The older names `GevIEEE1588`, `GevIEEE1588Status`, `GevTimestampControlLatch` and `GevTimestampValue` are deprecated in favour of `PtpEnable`, `PtpStatus`, `TimestampLatch` and `TimestampLatchValue`.
- **Register level** ([Wireshark](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L3468-3500)):
  - capability register `0x0934`, bit `0x00080000`
  - enable bit in configuration register `0x0954`, bit `0x00080000`
  - status register `0x096C`
- **Vendor quirks:**
  - **Basler:** PTP is always off at power-up, and enabling it changes the tick from 125 MHz to 1 ns. Check the *maximum* offset over a time window, because it does not fall steadily.
  - **Allied Vision:** uses `PtpMode` Off/Slave/Master/Auto, and documents PtpStatus as 0-based. Read the enumeration by name, not by integer value.
  - **LUCID:** uses `PtpSlaveOnly` and supports end-to-end delay measurement only.

### 2. Who becomes grandmaster
- **No host master is needed.** The cameras run the Best Master Clock Algorithm among themselves (Basler: lowest Priority1 wins; Allied Vision: Auto; LUCID: BMC).
- **Linux host as master:** possible with `ptp4l` (linuxptp v4.4; defaults are UDPv4, E2E delay, hardware timestamping; `-S` for software timestamping, `serverOnly`, `priority1`; [man page](https://github.com/richardcochran/linuxptp/blob/f98cb5de87e63696599c59d0a9df7dc04d08d40d/ptp4l.8#L48-L62)). Allied Vision warns that host software masters gave "significant jitter".
- **Windows:** the built-in PTP is a *client* ("subordinate") only, available from Windows 10 1809 and Server 2019 ([W32Time README](https://github.com/microsoft/W32Time/blob/9795ef91dfe5a452266ffd8106ff2bcb17f33556/README.md#L25-L36)).
- **macOS:** I could not find a supported option.

### 3. Network requirements
- PTP runs over UDP 319/320, multicast to 224.0.1.129.
- **IGMP snooping blocks Basler camera PTP**, because the cameras don't join any group. Basler says the only fix is to disable snooping ([KB](https://docs.baslerweb.com/knowledge/ptp-synchronization-doesn't-work-when-igmp-snooping-is-enabled)).
- Allied Vision says all cameras should be on the same subnet behind one switch. Basler recommends PTP-capable switches.
- **Accuracy figures from vendors:**
  - Allied Vision: "within two microseconds"; under ±1 µs over 69 hours; about 125 ns on an oscilloscope.
  - Teledyne: "a few microseconds".
  - LUCID: the sample output in its app note implies about 9.2 µs across 7 cameras. That is my arithmetic; LUCID states no figure.

### 4. How exposures get aligned
Synced clocks alone don't align exposures. There are three methods:
- **(a) Scheduled Action Commands.**
  - Camera setup: `TriggerSource=Action1` plus `ActionDeviceKey`, `ActionGroupKey` and `ActionGroupMask` (SFNC §14).
  - The host sends GVCP `ACTION_CMD 0x0100` to UDP 3956. Header: `0x42`, flags (`0x80` = scheduled, `0x01` = ack required), command, length (12 or 20), request id. Payload: device_key, group_key, group_mask, then an optional u64 action_time ([dissector](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L2092-2114)).
  - The action time is a latched timestamp plus a delay (Basler procedure).
- **(b) Vendor firmware modes:**
  - Basler Synchronous Free Run (`SyncFreeRunTimerStartTimeLow/High`, `SyncFreeRunTimerTriggerRateAbs`)
  - LUCID `AcquisitionStartMode=PTPSync` + `PTPSyncFrameRate`, which "schedules 4 advance action commands in the firmware"
  - Allied Vision `PtpAcquisitionGateTime` + FixedRate
- **(c) Post-hoc matching:** use the 64-bit timestamp in every GVSP leader ([Aravis](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L452-L463)) or `ChunkTimestamp`.
  - Caveat: Aravis reads the tick frequency only once, when the stream is created ([L1617](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L1617)). Enable PTP before creating streams.

### 5. Mapping camera time to host time
- Execute `TimestampLatch` (bootstrap: write 2 to `0x0944`, read `0x0948`/`0x094C`) with host clock reads just before and after. The error is roughly half the round-trip time.
- Alternatively, on Linux, make the host the PTP grandmaster.

### Which software can send action commands
- **Aravis:** no API. There is no ACTION_CMD in the [command enum](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L267-L281), and the fake camera doesn't handle it ([source](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvfakecamera.c#L157-L216)). Issue #184 is still open.
- **pypylon:** has `ActionCommand` and `ScheduledActionCommand` ([GigETransportLayer.i](https://github.com/basler/pypylon/blob/079cd1c7b7a9222591c69f88e3001059eca50dfe/src/pylon/GigETransportLayer.i#L230-L365)).
- **GenTL producers:** the GenTL SFNC 1.2 interface features `ActionCommand`, `ActionScheduledTime` and `GevActionDestinationIPAddress` are reachable through harvesters' `ia.interface.node_map`. Whether each producer implements them is unverified.
- **pyGigEVision v0.2.2:** no action or PTP support, but it can write the registers above.
- **Raw UDP in about 10 lines of Python:** my packets decode correctly in tshark.

### Tests
**Run here in Docker** (ubuntu 24.04, tshark 4.2.2, aravis-tools 0.8.30):
1. Generated ACTION_CMD packets decode correctly in tshark (flags `0x81`, device key, group key, mask, scheduled time).
2. The Aravis fake GigE Vision camera reports capability `0x0` and returns 0 from the timestamp latch. It doesn't answer ACTION_CMD, and `arv-tool` finds no Ptp, Action or Timestamp features. **PTP cannot be emulated, so real cameras are required.**
3. The fake camera's GVSP leader timestamps fall inside the host's time window and equal `g_get_real_time()*1000`. This confirms how the leader timestamp field works.

**Drafted for your machines with cameras** (in `research/ptp-sync-tests/`):
- **`gev_ptp_sync_test.py`:** standard library only, cross-platform, needs no SDK. Subcommands: selftest, discover, probe, ptp --enable, latch, action. Only `selftest` has passed; the other subcommands could only be run against the fake camera, which supports none of these features.
- **`gentl_ptp_sync_test.py`:** uses harvesters with any vendor `.cti`. Does the full enable PTP, schedule action, grab and measure-spread cycle. **Not tested; no hardware available.**

## Open questions

- macOS: is there any supported PTP grandmaster/client usable with GigE cameras? Not verified (linuxptp is Linux-only).
- Windows: any free/third-party PTP master software (e.g. ptpd ports)? Not verified; Microsoft documents only a client.
- Do common GenTL producers (pylon GenTL, Arena, Spinnaker, Vimba X, mvGenTL) implement GenTL SFNC Interface ActionCommand/ActionScheduledTime? Not verified.
- Mapping of SFNC ActionSelector=1 / TriggerSource=Action1 to bootstrap action group register index (0x9800 = index 0) is vendor-XML-defined; not verified.
- Behaviour on late scheduled actions: ACK with ACTION_LATE (0x8016) and drop, or execute immediately (Basler doc says immediately)? Possibly vendor-specific; gev_ptp_sync_test.py 'action' measures it.
- Real-world PTP lock time and inter-camera exposure-start spread through cheap unmanaged PoE switches vs transparent-clock switches: no vendor numbers found.
- Which Teledyne FLIR Spinnaker GigE models support scheduled action commands / PTP-synced acquisition (BFS-GE page read shows only GevIEEE1588* features)?
- gentl_ptp_sync_test.py is untested against hardware; gev_ptp_sync_test.py ptp/latch/action subcommands were only exercised against the Aravis fake camera (which lacks those features).

## Verification: Counter({'supported': 14, 'partially-supported': 3})

- [partially-supported] C9: Grandmaster selection is by the IEEE 1588 Best Master Clock Algorithm among the cameras (Basler: lowest Priority1 wins; Allied Vision PtpMode=Auto; LUCID BMC + PtpSlaveOnly), so no host master is required; without a GPS/UTC grandmaster the shared timescale is arbitrary.
  REASON: Basler's page says 'The network device with the lowest Priority 1 setting is the master clock', but BslPtpPriority1 can be set only on ace 2 and dart M; it is fixed at 128 on other models. AV says PtpMode=Auto uses the IEEE 1588 BMC. AV FAQ 2 says real-world time needs a GPS master, which supports the 'arbitrary timescale' point. The cited LUCID page (?p=8070) states BMC and E2E-only but does NOT mention PtpSlaveOnly. PtpSlaveOnly appears in LUCID ?p=4184.
  CORRECTED: Cameras elect a grandmaster via the IEEE 1588 BMCA. Basler: lowest Priority1 wins, but BslPtpPriority1 is only configurable on ace 2/dart M (fixed 128 elsewhere). AV: PtpMode=Auto. LUCID: BMC, with PtpSlaveOnly per camera (app note p=4184). No host master is required, and without a GPS/UTC grandmaster the shared timescale is arbitrary.
  BETTER: ['https://support.thinklucid.com/?p=4184', 'https://docs.baslerweb.com/precision-time-protocol']

- [partially-supported] C13: Vendor sync accuracy figures: Allied Vision 'within two microseconds', <±1 µs max offset over 69 h, ~125 ns on scope between two cameras; Teledyne 'within a few microseconds'. Allied Vision found host software PTP masters on Windows/Linux gave 'significant jitter'.
  REASON: The AV app note is V1.3.1 (2025-02-18). Its 'within two microseconds' is the note's definition of when sync is achieved ('While all Slave clocks are within two microseconds of the master, PTP sync is achieved'), not a measured accuracy. The measured figures are: maximum offset 'less than ± 1 µs' over 69 hours (three slaves against the master), and about 125 ns on an oscilloscope between two cameras. The note covers only Prosilica GT/GC, Manta and Mako G. The Teledyne 'within a few microseconds' page is dated 2019-11-17. The 'significant jitter' quote for host software masters is verified.
  CORRECTED: AV defines PTP sync as achieved when all slaves are within 2 µs of the master. It measured a maximum slave-master offset under ±1 µs over 69 h and about 125 ns between two cameras on a scope (Prosilica GT/GC/Manta/Mako G). Teledyne (2019) says 'within a few microseconds'. AV found host software PTP masters on Windows/Linux gave 'significant jitter'.
  BETTER: 

- [partially-supported] C16: Every GVSP image leader carries a 64-bit device timestamp; Aravis converts it to ns using GevTimestampTickFrequency read once at stream creation, so PTP (which changes Basler tick from 125 MHz to 1 GHz) should be enabled before creating the stream. The Aravis fake camera stamps frames with host wall-clock time.
  REASON: Confirmed: the u64 leader timestamp (arvgvspprivate.h L452-463). The tick frequency is read once in stream construction (arvgvstream.c L1617, stored at L1644) and used at L482-526. The fake camera uses g_get_real_time()*1000 (arvfakecamera.c L795) and places it in the leader (arvgvfakecamera.c L358-360). I checked the researcher's log: leader 0x18e1d7223e835798 = 1792950668747823000 lies inside the host window 1792950666062933265 to 1792950670168411222. Corrections: (a) Aravis reads the tick frequency from bootstrap registers 0x93C/0x940 via arv_gv_device_get_timestamp_tick_frequency, not from the GenICam feature GevTimestampTickFrequency. (b) Basler's 125 MHz to 1 GHz change on enabling PTP applies only to ace Classic/U/L; Basler says other cameras are always 1 GHz.
  CORRECTED: Every GVSP image leader carries a 64-bit device timestamp. Aravis converts it to ns using the bootstrap tick-frequency registers (0x93C/0x940), read once when the GvStream is created, so a camera whose tick rate changes when PTP is enabled (Basler ace Classic/U/L: 125 MHz to 1 GHz; other Basler models are always 1 GHz) should have PTP enabled before the stream is created. The Aravis fake camera stamps frames with host wall-clock ns.
  BETTER: ['https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L571-L586', 'https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvfakecamera.c#L358-L360']

## Missed points

- GigE Vision 3.0 was released by A3 on 2026-05-12. It adds RDMA over RoCEv2 (the GigE Vision RDMA Streaming Protocol) and a larger control channel, and the press release does not mention PTP, IEEE 1588 or timing. This directly supports correcting the user's premise: PTP sync works on GEV 2.x cameras. https://www.vision-systems.com/directory/software/machine-vision-imaging-software/press-release/55377111/association-for-advancing-automation-a3-a3-officially-releases-gige-vision-30-opening-new-possibilities-in-machine-vision
- GEV 2.1 added IEEE 1588 profile registers: supported-profiles bit 0x80000000 = PTP profile, 0x40000000 = 802.1AS (gPTP) profile, at 0x974/0x978/0x97C. https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L3388-3398
- The Windows inbox PTP client syncs only to a grandmaster whose PTP_TIMESCALE and PTP_UTC_REASONABLE flags are non-zero. A free-running camera grandmaster likely fails this, so slaving a Windows host to the cameras with w32time is not a dependable way to map camera time to host time. https://github.com/microsoft/W32Time/blob/9795ef91dfe5a452266ffd8106ff2bcb17f33556/Precision%20Time%20Protocol/docs/Validation%20Guide%20-%20Precision%20Time%20Protocol.docx
- Aravis main (commit ee31d82, 2026-10-03; after release 0.9.2, so unreleased) added aravissrc 'add-reference-timestamp-meta'. It attaches the absolute device timestamp to GStreamer buffers as GstReferenceTimestampMeta with timestamp/x-ptp caps, which is relevant to PTP-timestamped recording. https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L563-L567
- LUCID's 'Multi Camera Synchronization using PTP and Scheduled Action Commands' app note is the real source of the 7-camera sample output. It uses PtpEnable/PtpSlaveOnly/PtpStatus, then PtpDataSetLatch + PtpDataSetLatchValue (not TimestampLatch), then ActionCommandFireCommand. The printed frame timestamps run from 2074000024760 to 2074000033912 ns against a scheduled 2074000000000: a spread of about 9.15 µs, with every frame 25-34 µs after the scheduled time. https://support.thinklucid.com/?p=4184
- Aravis issue #184 (scheduled action commands) was opened in 2018 by 'thecaptury' (The Captury, a markerless-mocap vendor), the same use case as SkellyCam. The only maintainer comment (2019-08-15) asks whether a contributor's work is usable; there is no reply and no PR. https://github.com/AravisProject/aravis/issues/184
- Basler's IGMP-snooping KB adds that after snooping is disabled, the cameras stay stuck as PTP master and must be power-cycled. https://docs.baslerweb.com/knowledge/ptp-synchronization-doesn't-work-when-igmp-snooping-is-enabled
- Basler: BslPtpPriority1 can be set only on ace 2/dart M (fixed at 128 elsewhere). The 125 MHz to 1 GHz tick change is ace Classic/U/L only. For an external master Basler recommends an ANNOUNCE interval of 2 s and SYNC of 0.5 s. Peer-to-peer delay needs every switch to be PTP-enabled. On ace 2 and dart M, PtpServoStatus=Locked can replace offset-window checks. https://docs.baslerweb.com/precision-time-protocol
- Allied Vision firmware older than 01.54.11026 used a different PtpStatus set [Off, Master, Syncing, Slave, Error]; newer firmware is 0-based Initializing(0)..Slave(8), Invalid(9), whereas SFNC is 1..9. Mixed old and new firmware prevents PtpMode=Auto. https://www.alliedvision.com/assets/support/Camera-Documentation/Allied-Vision/FAQs-Application-Notes/PTP_IEEE1588_with_Prosilica_GT_GC_Manta.pdf
- The GenTL SFNC 1.2.0 Interface action features (ActionCommand, ActionScheduledTime and the rest) are Level 'Recommended', not mandatory, so producers may legitimately omit them. https://www.emva.org/wp-content/uploads/GenICam_GenTL_SFNC_1_2.pdf
- Basler's scheduled-action page shows that many Basler GigE models do not support scheduled action commands at all; the action queue size is 1-4 where supported. Check per model before relying on approach (a). https://docs.baslerweb.com/scheduled-action-commands