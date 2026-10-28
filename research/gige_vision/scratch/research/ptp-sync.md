# PTP (IEEE 1588) multi-camera sync on GigE Vision: how it works end to end

TOPIC_KEY: `ptp-sync`. Research date: 2026-10-25. Every claim below links to a source that was opened and read, or to a test that was run. Items that could not be verified are listed under *Open questions*.

## 0. Sources and versions

| Source | Version / date | How it was read |
|---|---|---|
| GenICam **SFNC 2.8** (latest on the EMVA downloads page) | 2026-04-08, 620 pp. https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_8.pdf | Downloaded, then `pdftotext` in Docker |
| GenICam SFNC 2.7.1 (for cross-check) | 2022-02-01. https://www.emva.org/wp-content/uploads/GenICam_SFNC_v2_7.pdf | Same |
| GenICam **GenTL SFNC 1.2.0** | 2020-07-08. https://www.emva.org/wp-content/uploads/GenICam_GenTL_SFNC_1_2.pdf | Same |
| EMVA downloads page (to confirm the latest versions) | https://www.emva.org/standards-technology/genicam/genicam-downloads/ (lists SFNC 2.8, GenTL SFNC 1.2, package 2026.07) | WebFetch |
| **Aravis** git HEAD `482547a3` | commit 2026-10-22. Latest tags are 0.9.2 and 0.8.36, both 2026-04-23 | `git clone`, grep/read |
| **Wireshark** `epan/dissectors/packet-gvcp.c` @ `02dbbdbf` | last change to that file 2026-06-24 | Raw download and read |
| **pypylon** HEAD `079cd1c7` (tag 26.9) | 2026-10-23 | `git clone`, then `git show` (Windows path-length limit) |
| **harvesters** HEAD `383494e3` (tag 1.4.3) | 2024-05-08 | `git clone` |
| **pyGigEVision** HEAD `2de25313` (tag v0.2.2) | 2026-07-08 | `git clone` |
| **linuxptp** HEAD `f98cb5de` (v4.4-60; v4.4 tagged 2024-09-07) | 2026-06-05 | `git clone` from sourceforge (GitHub mirror permalinks verified with HTTP 200) |
| Microsoft **W32Time** repo HEAD `9795ef91` | 2023-06-12 | `git clone`, plus the PTP validation guide .docx text-extracted |
| Allied Vision app note "IEEE 1588 PTP with Prosilica GT, GC, Manta, and Mako G" | V1.3.1, 2025-02-18 | PDF, `pdftotext` |
| Basler docs: PTP, Scheduled Action Commands, Action Commands, Synchronous Free Run, IGMP KB | IGMP KB: 19 Oct 2026 (v137). Other pages carry no date | WebFetch |
| LUCID: PTP KB (2023-09-19, updated 2023-11-17); app notes on PTP + scheduled action and on bandwidth sharing / PTPSync (undated) | | WebFetch |
| Teledyne Vision Solutions PTP article (2019-11-17); FLIR BFS-GE-16S2 Transport Layer page (v1808.1.1.0, 2018-08-13) | | WebFetch |
| IDS peak manual "PtpStatus" (IDS peak 26.06 / uEye+ fw 3.94) | | WebFetch |
| Juniper transparent-clock doc | | WebFetch |
| Microsoft Learn "Insider preview for Windows Time Service features in Windows Server 2019" (updated 2025-09-15) | | WebFetch |

## 1. The "GigE Vision 3 is needed for PTP" premise is wrong

* PTP was already in **GigE Vision 2.0**. Wireshark's GVCP dissector marks every IEEE 1588 bootstrap field as `_v2_0`: `hf_gvcp_capability_1588_v2_0` (cap bit 0x00080000), `hf_gvcp_configuration_1588_enable_v2_0` (0x0954 bit 0x00080000), `hf_gvcp_ieee1588_clock_status_v2_0` (0x096C). Scheduled action commands are also `_v2_0`: `hf_gvcp_scheduledactioncommand_flag_v2_0`, `hf_gvcp_actioncmd_time_v2_0`, and `GEV_STATUS_ACTION_LATE /* GEV 2.0 */`. GEV 2.1 added profile registers (`hf_gvcp_ieee1588_802dot1as_profile_supported_v2_1`). Code: [packet-gvcp.c L204-L229 (status codes, GEV 2.0 comments)](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L204-229), [L426-L489 (hf_*_v2_0 / v2_1)](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L426-489).
* Aravis issue #184 (opened 2018-08-09 and still open) says "GigEVision 2.0 introduces Action Commands that will be processed by the camera at a specified time": https://github.com/AravisProject/aravis/issues/184. It was opened by user `thecaptury`, which appears to be the markerless-mocap company The Captury.
* What GEV 3.0 adds is a different topic, and other agents cover it.

## 2. Turning PTP on in the camera (GenICam SFNC)

SFNC 2.8 §27.3 "PTP Control" (pp. 529-534) defines these features. Text checked in both 2.8 and 2.7.1:

| Feature | Type / access | Definition |
|---|---|---|
| `PtpEnable` | IBoolean R/W | "Enables the Precision Time Protocol (PTP)." |
| `PtpClockAccuracy` | IEnumeration R | `Within25ns` … `GreaterThan10s`, `AlternatePTPProfile`, `Unknown`, `Reserved`. "expected accuracy of the device PTP clock when it is the grandmaster, or in the event it becomes the grandmaster." |
| `PtpDataSetLatch` | ICommand W | "Latches the current values from the device's PTP clock data set." |
| `PtpStatus` | IEnumeration R | `Initializing, Faulty, Disabled, Listening, PreMaster, Master, Passive, Uncalibrated, Slave`. "indicated by values 1 to 9 … Refer to the IEEE 1588-2008 specification" |
| `PtpServoStatus` | IEnumeration R | `Unknown, Locked, Device-specific` |
| `PtpOffsetFromMaster` | IInteger R, ns | "latched offset from the PTP master clock in nanoseconds" |
| `PtpClockID`, `PtpParentClockID`, `PtpGrandmasterClockID` | IInteger R | latched clock IDs |
| `PtpMeanPropagationDelay` | IInteger R, ns | "valid only when the PtpStatus is Slave" |

* Deprecated names (SFNC 2.8 p. 85 summary and §27.4.38): `GevIEEE1588` → `PtpEnable`, `GevIEEE1588Status` → `PtpStatus`, `GevIEEE1588ClockAccuracy` → `PtpClockAccuracy`, `GevTimestampControlLatch` → `TimestampLatch`, `GevTimestampValue` → `TimestampLatchValue`, `GevTimestampTickFrequency` → "the increment of the TimestampLatchValue feature".
* `TimestampLatch` "Latches the current timestamp counter into TimestampLatchValue". `TimestampLatchValue` has unit ns (SFNC 2.8 §3.68-3.69, p. 118).
* The status values are **latched**: you execute `PtpDataSetLatch` first and then read them.
* At the bootstrap-register level, which is what the stand-alone test uses:
  * capability `0x0934`: bit `0x00080000` = IEEE1588 supported, `0x00020000` = scheduled action, `0x00000040` = action, `0x00100000` = unconditional action.
  * configuration `0x0954`: bit `0x00080000` = IEEE1588 enable, `0x00000008` = unconditional action enable.
  * `0x096C` = IEEE1588 status (low 4 bits).
  * `0x0970` = scheduled action queue size.
  * Sources: [packet-gvcp.c L113-L137](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L113-137), [L3468-L3500](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L3468-3500), [L3604-L3618](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L3604-3618), [L3692-L3702](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L3692-3702), and Aravis [arvgvcpprivate.h L95-L124](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L95-L124).

### Vendor specifics

* **Basler** ([docs.baslerweb.com/precision-time-protocol](https://docs.baslerweb.com/precision-time-protocol)):
  * "When powering on the camera, PTP is always disabled."
  * The general procedure uses `GevIEEE1588`, `GevIEEE1588DataSetLatch` and `GevIEEE1588StatusLatched`. ace 2 / dart M use `PtpEnable`, `PtpDataSetLatch` and `PtpServoStatus` ("If the state is Locked … successfully synchronized").
  * Enabling PTP "changes the camera's internal tick frequency from 125 MHz (= 8 ns tick duration)" to ns ticks.
  * Recommends checking the **maximum** `GevIEEE1588OffsetFromMaster` over a time window, because the value does not decrease monotonically.
  * `BslPtpPriority1` is settable 0-255 on ace 2 / dart M and fixed at 128 on other models. Also `BslPtpProfile` (DelayRequestResponseDefaultProfile / PeerToPeerDefaultProfile), `BslPtpNetworkMode` (multicast / unicast …) and two-step.
* **LUCID**:
  * PTP KB (2023): cameras use "PTP's Best Master Clock (BMC) algorithm". "LUCID cameras support the End-to-End method … but not the Peer-to-Peer method." https://support.thinklucid.com/?p=8070
  * App note: `PtpEnable`, plus `PtpSlaveOnly=false` on the camera meant to be master and `true` on the others. https://support.thinklucid.com/app-note-multi-camera-synchronization-using-ptp-and-scheduled-action-commands/
* **Allied Vision** app note V1.3.1, 2025-02-18 (local copy extracted):
  * `PtpMode = Off | Slave | Master | Auto`. Auto "uses the IEEE 1588 best master clock algorithm".
  * PtpStatus values are documented. With mixed old and new firmware, Auto cannot be used.
  * Events `EventPtpSyncLost` / `EventPtpSyncLocked`.
  * Its FAQ lists the enumeration as `Initializing(0) … Slave(8), Invalid(9)`. This is **0-based**, whereas SFNC says 1-9, so read the enumeration *symbolically* through GenICam and do not hard-code integer values.
* **IDS** (peak 26.06): PtpStatus values match SFNC. https://www.1stvision.com/cameras/IDS/IDS-manuals/en/ptp-status.html
* **Teledyne FLIR** Blackfly S GigE (BFS-GE-16S2, page v1808.1.1.0): exposes `GevIEEE1588`, `GevIEEE1588Status`, `GevIEEE1588Mode` and `GevIEEE1588ClockAccuracy`. The page has no Action/Ptp* features. https://softwareservices.flir.com/BFS-GE-16S2-BD2/latest/Model/public/TransportLayerControl.html

## 3. Who becomes grandmaster

* **BMCA among the cameras.**
  * Basler: "The network device with the **lowest** Priority 1 setting is the master clock", with reference to IEEE 1588-2008 clause 7.6.2.2.
  * Allied Vision: `PtpMode=Auto` uses BMCA, and Master/Slave can be forced.
  * LUCID: BMC, with `PtpSlaveOnly` available.
  * Conclusion: **no host master is required**. One camera becomes master, the others become slaves, and all of them share one timescale. That timescale is arbitrary unless a real grandmaster such as GPS is present (AV FAQ 2).
* **Host as grandmaster on Linux**: `ptp4l` from linuxptp.
  * Defaults: `network_transport UDPv4`, `delay_mechanism E2E`, `time_stamping hardware`, `priority1 128`, `domainNumber 0`, `clientOnly 0`, `serverOnly 0` ([configs/default.cfg](https://github.com/richardcochran/linuxptp/blob/f98cb5de87e63696599c59d0a9df7dc04d08d40d/configs/default.cfg)).
  * `-S` selects software timestamping and `-H` hardware ([ptp4l.8 L48-L62](https://github.com/richardcochran/linuxptp/blob/f98cb5de87e63696599c59d0a9df7dc04d08d40d/ptp4l.8#L48-L62)).
  * `priority1`: "lower values take precedence" ([ptp4l.8 L911-L914](https://github.com/richardcochran/linuxptp/blob/f98cb5de87e63696599c59d0a9df7dc04d08d40d/ptp4l.8#L911-L914)).
  * `serverOnly` "prevents the port from entering the client state" ([ptp4l.8 L507-L512](https://github.com/richardcochran/linuxptp/blob/f98cb5de87e63696599c59d0a9df7dc04d08d40d/ptp4l.8#L507-L512)).
  * Linux-only by design: "Supporting legacy APIs and other platforms is not a goal" ([README.org L1-L20](https://github.com/richardcochran/linuxptp/blob/f98cb5de87e63696599c59d0a9df7dc04d08d40d/README.org#L1-L20)).
  * Example: `sudo ptp4l -i eth0 -4 -H -m --priority1 1 --serverOnly 1`. Use `-S` if the NIC has no PHC.
  * Allied Vision warns that a host software master on Windows or Linux "generated very poor synchronization plagued by significant jitter" (AV app note FAQ 1). In their measurements the host master is a step down from a camera master or a hardware grandmaster.
* **Windows**: the built-in PTP is a **client (subordinate) only**.
  * Microsoft W32Time README: "Windows includes a PTPv2 (IEEE 1588v2) subordinate in … Windows 10 October 2018 Update (and later) / Windows Server 2019 (and later)" ([README.md L25-L36](https://github.com/microsoft/W32Time/blob/9795ef91dfe5a452266ffd8106ff2bcb17f33556/README.md#L25-L36)).
  * The Validation Guide describes "the Precision Time Protocol client"; multicast receive is off by default (`EnableMulticastRx`); masters are listed in `PtpMasters` ([PTPClientConfig.txt](https://github.com/microsoft/W32Time/blob/9795ef91dfe5a452266ffd8106ff2bcb17f33556/Precision%20Time%20Protocol/Windows%20Configuration%20Helpers/PTPClientConfig.txt)).
  * Microsoft Learn calls it "A new time provider … allows you to synchronize time using the Precision Time Protocol" ([learn.microsoft.com](https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/insider-preview)).
  * No Microsoft source describes a Windows PTP *master*.
  * For camera sync this does not matter, because the cameras elect their own master. It only matters if you want camera time = host time, which is covered in §6.
* **macOS**: no first-party PTP master or client was found (open question).

## 4. Network requirements

* **Transport**: PTP event messages use UDP 319 and general messages UDP 320, multicast to 224.0.1.129, with peer-delay messages to 224.0.0.107 (linuxptp [udp.c L40-L41](https://github.com/richardcochran/linuxptp/blob/f98cb5de87e63696599c59d0a9df7dc04d08d40d/udp.c#L40-L41), [config.c L327, L349](https://github.com/richardcochran/linuxptp/blob/f98cb5de87e63696599c59d0a9df7dc04d08d40d/config.c#L327-L349)). Basler cameras send PTP sync to 224.0.1.129 ([Basler KB](https://docs.baslerweb.com/knowledge/ptp-synchronization-doesn't-work-when-igmp-snooping-is-enabled)).
* **IGMP snooping breaks it** (Basler KB, 19 Oct 2026): Basler GigE cameras "do not join any IGMP group", so a snooping switch filters their PTP. "The only way to prevent this issue is to disable IGMP snooping." Cameras may also stay stuck as master until power-cycled.
* **Same L2 segment**: Allied Vision says "all devices [must] be on the same network or subnet … due to the current inability of any network card to forward PTP sync multicast packets between ports within the two microseconds requirement", so cameras are put on a switch behind a single host port. Basler says action commands also need the "same network segment".
* **Switch quality**: Basler: "use PTP-enabled network switches, and add an external PTP clock device with a GPS receiver" for maximum precision. A transparent clock "measures the residence time of PTP packets … added to the Correction Field" ([Juniper](https://juniper.net/documentation/us/en/software/junos/time-mgmt/topics/task/configure-ptp-transparent-clock.html)).
* **Delay mechanism**: LUCID supports End-to-End only. On Basler, use P2P only if "your entire network is set up for peer-to-peer delay measurement".
* **Bandwidth**: Allied Vision notes that a single GigE uplink is limited to about 125 MB/s for all cameras combined. The LUCID PTPSync app note staggers packets with `GevSCPD` / `GevSCFTD`. Its example uses 4 cameras with GevSCFTD of 0 / 80 / 160 / 240 µs ([support.thinklucid.com/?p=7267](https://support.thinklucid.com/?p=7267)). Because synchronized cameras all transmit at once, bursts collide unless they are staggered.
* **PoE (single cable)**: tested setups used PoE+ switches, for example LUCID's Netgear MS510TXPP. The point is that PTP needs no separate sync cable, because power, data and timing share one Ethernet cable per camera.
* **Achievable accuracy (vendor numbers)**:
  * Allied Vision:
    * "future software based triggers can be synchronized within two microseconds"
    * 69-hour test: "maximum offset recorded was less than ± 1 µs"
    * oscilloscope test between two cameras' SyncOut signals: "approximately 125 nanoseconds"
  * Teledyne: "synchronize PTP-enabled devices within a few microseconds" ([article, 2019](https://www.teledynevisionsolutions.com/learn/learning-center/machine-vision/precision-system-synchronization-with-the-ieee-1588-precision-time-protocol-ptp/)).
  * LUCID: the sample output in the scheduled-action app note shows FrameID 1 timestamps from 7 cameras spanning 2074000024760-2074000033912 ns. That is **about 9.2 µs**; this is my arithmetic and LUCID states no figure.
  * For motion capture at 30-240 fps (4-33 ms frame period), any of these is far below a frame period.

## 5. How frames actually get synchronized once clocks agree

Synced clocks alone do **not** synchronize exposures. Free-running cameras with synced clocks still expose at their own phase. That is why every vendor pairs PTP with a start-time mechanism: action time, start time, or gate time (AV Case 1, Basler Synchronous Free Run, LUCID PTPSync). There are three ways to align exposures.

### 5a. Scheduled Action Commands (standard, vendor-neutral)

* **Camera side** (SFNC 2.8 §14, pp. 297-300): `ActionDeviceKey` (write-only), `ActionSelector`, `ActionGroupKey[sel]`, `ActionGroupMask[sel]`, `ActionQueueSize` ("maximum number of scheduled action commands that can be pending") and `ActionUnconditionalMode`. The SFNC usage example is `TriggerSelector=FrameStart; TriggerMode=On; TriggerSource=Action1; ActionDeviceKey=0x12345678; ActionSelector=1; ActionGroupKey=0x1; ActionGroupMask=0x1`. The device fires when the device key matches, the group key matches and (mask & mask) ≠ 0 (§14.2.6-14.2.7). `ActionLate` event: "a valid scheduled action command is received and is scheduled to be executed at a time that is already past".
* **Bootstrap registers**: device key `0x090C`, group key / mask `0x9800 + 0x10*i` / `0x9804 + 0x10*i` ([packet-gvcp.c L113-L114, L169-L170](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L113-170)).
* **Packet** (`ACTION_CMD = 0x0100`, `ACTION_ACK = 0x0101`, UDP port 3956):

  ```
  byte 0      0x42                  key code
  byte 1      flags                 0x80 = scheduled action (action_time present), 0x01 = ack required
  bytes 2-3   0x0100                ACTION_CMD
  bytes 4-5   payload length        12 (unscheduled) or 20 (scheduled)
  bytes 6-7   req_id
  payload     device_key u32 | group_key u32 | group_mask u32 | [action_time u64]   (all big-endian)
  ```
  * Wireshark [dissect_action_cmd L2092-L2114](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L2092-2114), [flag 0x80 handling L2513-L2518](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L2513-2518), [field defs L2815-L2823, L3049-L3067](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L3049-3067).
  * The header layout matches Aravis `ArvGvcpHeader` ([arvgvcpprivate.h L298-L303](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L298-L303)).
  * Status `0x8016 GEV_STATUS_ACTION_LATE` ([L227](https://gitlab.com/wireshark/wireshark/-/blob/02dbbdbf41aecc1f2a4ba6c0db2546af5bb07d75/epan/dissectors/packet-gvcp.c#L227)).
* **Procedure** (Basler "Scheduled Action Commands"):
  1. Sync PTP.
  2. Execute `TimestampLatch` on one camera.
  3. Read `TimestampLatchValue`.
  4. Use action_time = value + delay; "If the value is 0 or in the past, the command runs immediately".
  * Queued commands run in ascending action-time order. "If the queue is full, additional commands will be ignored."
  * pylon: `IssueScheduledActionCommand(4711, 1, 0xFFFFFFFF, 20000000000, "192.168.1.255")`.
  * LUCID schedules via `PtpDataSetLatch` and the latched value, rounded to the next whole second.
* **Host side, by library**:
  * **Aravis: no API.** At `482547a3` there is no `ACTION_CMD` in the GVCP command enum ([arvgvcpprivate.h L267-L281](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L267-L281)). A grep for `action_c|ACTION_CMD|scheduled` over src/ finds only the capability bit (L102), the error code `ARV_GVCP_ERROR_ACTION_LATE` and the GVSP status. Issue #184 "Scheduled Action Commands" is open (last activity 2023-12-16). The fake GV camera does not handle ACTION_CMD: its switch covers only DISCOVERY / READ/WRITE_MEMORY / READ/WRITE_REGISTER and falls to `default: "Unknown command"` ([arvgvfakecamera.c L157-L216](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvfakecamera.c#L157-L216)). Configuring PTP features through Aravis is possible with the generic feature API; the maintainer said so when closing issue #258 ([#258](https://github.com/AravisProject/aravis/issues/258)).
  * **pypylon** (Basler pylon, which has a GigE TL that also works with non-Basler GEV cameras): `IGigETransportLayer.ActionCommand(...)` and `.ScheduledActionCommand(deviceKey, groupKey, groupMask, actionTimeNs, broadcastAddress)` with `IssueNoWait()` / `IssueWait(timeoutMs, expected_results)` ([GigETransportLayer.i L230-L365](https://github.com/basler/pypylon/blob/079cd1c7b7a9222591c69f88e3001059eca50dfe/src/pylon/GigETransportLayer.i#L230-L365)). Sample: [grab_using_action_command.py](https://github.com/basler/pypylon/blob/079cd1c7b7a9222591c69f88e3001059eca50dfe/samples/pylon/grab_using_action_command/grab_using_action_command.py#L60-L100).
  * **GenTL producers via harvesters**: GenTL SFNC 1.2 §3.2.3 defines Interface-module features `ActionCommand`, `ActionDeviceKey`, `ActionGroupKey`, `ActionGroupMask`, `ActionScheduledTimeEnable`, `ActionScheduledTime` and `GevActionDestinationIPAddress` (pp. 72-76, "Recommended" level). Harvesters exposes the Interface module and its `node_map` ([core.py L455-L460, L506-L510, L1990-L1997](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/core.py#L1990-L1997)). Whether a given producer implements these features is not verified (open question).
  * **pyGigEVision v0.2.2**: implements only DISCOVERY, FORCEIP, READ/WRITE REG/MEM and PACKETRESEND. It has no ACTION_CMD and no PTP features ([gvcp.py L50-L56](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L50-L56)). It can write the bootstrap registers above with `write_reg`.
  * **Raw UDP**: about 10 lines of stdlib Python. See `gev_ptp_sync_test.py` (§8), whose packet output Wireshark decodes correctly.

### 5b. Vendor firmware "synchronous free run" modes (no per-frame host traffic)

* **Basler Synchronous Free Run** ([docs](https://docs.baslerweb.com/synchronous-free-run)):
  * `SyncFreeRunTimerTriggerRateAbs` (same value on all cameras), `SyncFreeRunTimerStartTimeHigh/Low` (64-bit ns start; 0 = immediate), `SyncFreeRunTimerUpdate`, `SyncFreeRunTimerEnable`.
  * Needs PTP and free run.
  * Can also stagger cameras deliberately ("time-aligned intervals").
* **LUCID PTPSync**: "a built-in firmware feature that schedules 4 advance action commands in the firmware itself".
  * Settings: `AcquisitionStartMode = PTPSync` and `PTPSyncFrameRate`, which must be less than `AcquisitionFrameRate`; AcquisitionFrameRate no longer controls the rate ([app note](https://support.thinklucid.com/?p=7267)).
  * The KB says that with PTP Sync "you can't trigger cameras" ([KB](https://support.thinklucid.com/?p=8070)).
* **Allied Vision `PtpAcquisitionGateTime`**:
  * Suspends frame triggers "until GevTimestampValue ≥ PtpAcquisitionGateTime".
  * Combined with `TriggerSource=FixedRate` and an identical `AcquisitionFrameRateAbs`, "all cameras start imaging synchronously at the configured frame rate" (AV app note, Case 1).
  * It also works with a software trigger.
* **Teledyne FLIR**: no PTP-sync-acquisition feature appeared on the Blackfly S page that was read (open question).

### 5c. Post-hoc alignment by timestamp

* Every GVSP leader carries a **64-bit timestamp** (`timestamp_high` / `timestamp_low`) ([Aravis arvgvspprivate.h L152-L157, L452-L463](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L452-L463); pyGigEVision parses it at [gvsp.py L610-L617](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L610-L617)). Chunk `ChunkTimestamp` = "Timestamp of the image … at the time of the FrameStart internal event" (SFNC 2.8 §24.31, p. 488).
* With PTP on, that timestamp is in the shared PTP timescale, so frames can be matched across cameras (AV: "Reading the GevTimestampValue contained in the image header verifies this synchronization"). Aravis converts the tick value to ns using `GevTimestampTickFrequency` ([arvgvstream.c L460-L530](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L460-L530)).
* **Caveat (inference from code):** Aravis reads the tick frequency **once at stream creation** ([arvgvstream.c L1617](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L1617)), and Basler says enabling PTP changes the tick from 125 MHz. So **enable PTP before creating streams**.
* Aravis also records `system_timestamp_ns = g_get_real_time()*1000` at leader arrival ([L460](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L460)).
* The GStreamer `aravissrc` has `add-reference-timestamp-meta` → `timestamp/x-ptp` ("Only an absolute time if the device clock is PTP-synchronized") ([gstaravis.c L564-L567, L630-L640, L1203-L1209](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L1203-L1209)).
* Post-hoc alignment alone does not remove the phase offset between free-running cameras (up to ½ frame). It is needed **together with** 5a or 5b.

## 6. Mapping camera PTP time to host time

* Use `TimestampLatch` + `TimestampLatchValue` (or `GevTimestampControlLatch` + `GevTimestampValue`; bootstrap: write 2 to `0x0944`, read `0x0948/0x094C`; [arv-gev-bootstrap.xml L274-L300](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arv-gev-bootstrap.xml#L274-L300)). Bracket the latch with host clock reads before and after, then take offset = latched − midpoint. The uncertainty is about RTT/2; the loopback RTT measured here was about 30 µs, while real NICs and cameras are typically larger (unmeasured).
* Allied Vision: to get real-world time, use a GPS grandmaster, or "reference the latest GevTimestampValue to the PC clock; however, this can suffer from significant jitter".
* On Linux, an alternative is for the host to be the PTP grandmaster (`ptp4l` with HW timestamping plus `phc2sys`), so camera time equals host time by construction. On Windows the built-in client can only follow, not lead (see §3).
* The camera↔camera relationship comes from PTP, and only the host↔camera mapping needs latching. For SkellyCam, aligning frames needs only the shared camera timescale. Host mapping is needed only to align with non-GigE sensors (audio, UVC webcams).

## 7. Experiments run here (Docker, `ubuntu:24.04` with `tshark 4.2.2` and `aravis-tools 0.8.30`)

Image built with `apt-get install tshark aravis-tools aravis-tools-cli python3`. Harness: `ptp-sync-tests/run_in_docker.sh`. Command:
```
docker run --rm --cap-add NET_RAW --cap-add NET_ADMIN -v <ptp-sync-tests>:/t:ro -v <ptp-sync-tests>/out:/out gev-ptp-test bash /t/run_in_docker.sh
```
Full log: `ptp-sync-tests/out/docker_run_final.log` (plus `docker_run.log` / `docker_run2.log` from the earlier runs).

1. **Packet format test.** `gev_ptp_sync_test.py selftest --pcap` builds ACTION_CMD packets and tshark decodes them:
   ```
   Flags: 0x81  Scheduled Action Command: True  Acknowledge Required: True
   Command: ACTION_CMD (0x0100)  Payload Length: 0x0014 (20)
   Action Device Key: 0x12345678  Group Key: 0x00000001  Group Mask: 0x00000001
   Action Scheduled Time: 0x000001e23f5a1000 (2071237103616)
   ```
   This confirms the layout in §5a against Wireshark's dissector. The same packets, sent live, were decoded from the `lo` capture as `127.0.0.1 True 0x12345678 0x00000001 0x00000001 0x000000000bebc200`.
2. **Aravis fake GV camera has no PTP, latch or action support.**
   * `arv-tool-0.8 control GevTimestampTickFrequency GevIEEE1588 PtpEnable GevIEEE1588Status PtpStatus ActionDeviceKey TimestampLatch` → all "not found".
   * Bootstrap probe: `capability 0x00000000`, `GEV version 0.0`, `tick_frequency 1000000000` (set in [arvfakecamera.c L1083-L1084](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvfakecamera.c#L1083-L1084)).
   * The timestamp latch always reads 0.
   * ACTION_CMD gets **no ACTION_ACK**.
   * So PTP / action behaviour **cannot be emulated** with the Aravis fake camera. It needs real cameras, which is why the stand-alone tests exist.
   * Note: the fake camera answers a multi-address READREG with only one value, and the test script now falls back to single reads.
3. **GVSP leader timestamps.** While streaming from the fake camera, the leader timestamps (`0x18e1d7099b44c930` …) all fell between host `date +%s%N` taken before and after. They were 40 ms apart at 25 fps and end in `000`, i.e. `g_get_real_time()*1000` exactly as in [arvfakecamera.c L795](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvfakecamera.c#L795-L796). This confirms the 64-bit leader timestamp path. On a real PTP camera that field carries PTP time instead.

## 8. Stand-alone tests to run on machines with real PTP cameras

Folder: `C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/research/ptp-sync-tests/`

* **`gev_ptp_sync_test.py`**: stdlib only, Python 3.8+, works on Windows/macOS/Linux and needs no SDK. It uses bootstrap registers only.
  * `selftest`: offline packet check; verified passing.
  * `discover`
  * `probe IP...`: reports PTP, action and scheduled-action capability bits, tick frequency, PTP enable/status and queue size.
  * `ptp IP... --enable`: sets the IEEE1588 enable bit and polls until exactly one Master and the rest Slave.
  * `latch IP...`: compares camera clocks via latch against the host clock.
  * `action IP... --dest <subnet-broadcast>`: programs keys and sends scheduled, late and unscheduled ACTION_CMDs, then reports the ACTION_ACK status of each. It expects SUCCESS, and ACTION_LATE or immediate execution for the late one.
* **`gentl_ptp_sync_test.py`**: GenICam feature level through `harvesters==1.4.3` and any vendor GenTL `.cti`. **Untested; no hardware available.**
  * Enables `PtpEnable`/`GevIEEE1588` and waits for roles plus max |offset| < 1 µs for 10 s.
  * Sets `TriggerSource=Action1` (falling back to Action0) and fires N scheduled actions, through the GenTL Interface `ActionCommand` or raw UDP.
  * Grabs one frame per camera per trigger and reports the spread of the per-trigger device timestamps. It passes if p99 < 50 µs.
  * `--mode freerun` measures nearest-frame offsets for vendor synchronous-free-run modes.

Suggested run on a test rig (2+ PTP cameras on one PoE switch, IGMP snooping off):
```
python gev_ptp_sync_test.py discover
python gev_ptp_sync_test.py probe 192.168.1.11 192.168.1.12
python gev_ptp_sync_test.py ptp 192.168.1.11 192.168.1.12 --enable --timeout 60
python gev_ptp_sync_test.py latch 192.168.1.11 192.168.1.12 --rounds 50
python gev_ptp_sync_test.py action 192.168.1.11 192.168.1.12 --dest 192.168.1.255
pip install harvesters==1.4.3 numpy
python gentl_ptp_sync_test.py --cti "<path to producer .cti>" --frames 100 --delay-ms 200
```

## Open questions

* macOS: is there any supported PTP grandmaster or client that is usable for GigE cameras? Not researched to a verifiable source. linuxptp is Linux-only by design.
* Windows: is there a third-party or free PTP *master* (for example a Windows ptpd port or commercial tools)? Not verified. Microsoft documents only a client.
* Do common GenTL producers (pylon GenTL, Arena, Spinnaker, Vimba X, mvGenTL) implement the GenTL-SFNC Interface `ActionCommand` / `ActionScheduledTime` features? Not verified.
* How does `ActionSelector=1` / `TriggerSource=Action1` map to the bootstrap group-key register index (0x9800 = index 0)? SFNC history notes "ActionSelector now >0". The mapping is vendor-XML-defined and not verified.
* What does a camera do with a scheduled action whose time is in the past: ACK with `ACTION_LATE` (0x8016) and drop it, or execute it immediately (Basler doc)? Possibly vendor-specific; the `action` sub-command measures it.
* What are typical PTP lock times and achievable inter-camera exposure-start spread through a cheap unmanaged PoE switch versus a TC-capable switch? There are no vendor numbers for unmanaged switches.
* Which Teledyne FLIR (Spinnaker) GigE models offer scheduled action / PTP-synced acquisition? The page read had none.
