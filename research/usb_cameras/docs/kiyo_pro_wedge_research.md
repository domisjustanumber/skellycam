# Razer Kiyo Pro wedge: what is known, what causes it, and how to test it

> **Decision (Dom, 2026-11-11):** the wedge is **not** diagnosed further. Tests handle a Kiyo Pro wedge, record information that may help diagnose it later, mark the camera dead for the rest of the run, and make no attempt to revive it. The tests proposed in §9 are not run. Kept for reference only. The handling rule is in [`../../CAPTURE_AND_RECORDING_PLAN.md`](../../CAPTURE_AND_RECORDING_PLAN.md) §3.3 TP1. The kernel commit in §3.1 was checked on the GitHub mirror (`8b7a42ecdcde`, authored 2026-03-31).

2026-11-11 · desk research only. No camera was touched, no test was run, and no driver, registry or power setting was changed. Paths are relative to `research/usb_cameras/`.

**Labels:** **[M]** our measured result (linked file) · **[S]** primary source: vendor page, kernel commit, Microsoft documentation, or a maintainer's own words on a mailing list (URL and access date in [Sources](#sources)) · **[W]** forum or user report, including a user's own GitHub project · **[I]** inferred by me.

All web sources were accessed on 2026-11-11.

## 1. Bottom line

- **Yes, the Kiyo Pro is known to stop responding until it is replugged or the host controller is reset.** This is reported widely on Windows and Linux.
  - Linux carries a USB-core quirk for exactly this device, 1532:0E05. The commit says the firmware "fails to respond to control transfers" **[S]**.
  - Razer's own forum has many threads since 2022 where a replug is the only recovery **[W]**.
- **Nobody has established the root cause.**
  - The Linux quirk blames USB Link Power Management (LPM) **[S]**.
  - The developer who wrote that quirk later found that turning LPM off is not enough. He also blames rapid UVC control requests, and above all the stream "commit" request at stream start **[W]**.
  - The xHCI maintainer and an active xHCI reviewer are not convinced the device alone is at fault. They also suspect the host controller **[S]**.
- **Our camera runs the firmware those reports are about.** Our Kiyo reports bcdDevice 0x0821 in every recorded run **[M]**. The Linux developer reports firmware 1.5.0.1 as "bcdDevice 8.21" **[W]**, and 1.5.0.1(_r1) is the newest updater Razer offers (§4). So there is no newer firmware to try **[I]**.
- **Our four wedges all began at a stream start or stop, never mid-stream and never during control polling alone** **[M]**. This matches the upstream picture of a failure during stream negotiation **[I]**.
- **Plug-in age is ruled out as the trigger.** Vendor software is not necessary for a wedge, and multi-camera DirectShow opens are not necessary either. In our conditions the wedge looks like a rare event per stream start, roughly 1 in 1,000, with some sign of a higher rate during simultaneous multi-camera opens (§6) **[I]**.

## 2. Which camera this is

| Model | USB ID | Source |
| --- | --- | --- |
| **Razer Kiyo Pro** (ours) | **1532:0E05** | **[M]** our descriptor reads `iProduct` "Razer Kiyo Pro", `idProduct` 0e05 ([descriptors.json](../results/windows/Gerald/suite_20261111T040003Z/descriptors/descriptors.json)); **[S]** the Linux quirk names "Razer Kiyo Pro Webcam" for 0x1532:0x0e05 |
| Razer Kiyo (original, 2018) | 1532:0E03 | **[W]** CameraController #138 (see [macos_uvc_controls_review.md](macos_uvc_controls_review.md) §6) |
| Razer Kiyo X | 1532:0E06 | **[W]** third-party driver database only; not verified |
| Razer Kiyo Pro Ultra | not verified | nothing found |

- In the sources below, I keep the models apart, and I say so where a source does not name its model.
- Two widely cited sources are **not** about the Kiyo Pro:
  - The Level1Techs thread from 2018 that the Linux developer cites as "same firmware family" is about the **original Kiyo**. It predates the Kiyo Pro, and it blamed a PCIe add-in card's power supply **[W]**.
  - The 2024 Raspberry Pi focus-crash post says only "Kiyo" **[W]**.

## 3. What others report

### 3.1 Linux kernel and mailing lists (Kiyo Pro, 1532:0E05)

**The USB-core quirk** **[S]**: commit [8b7a42ecdcde](https://github.com/torvalds/linux/commit/8b7a42ecdcdeb55580d9345412f7f8fc5aca3f6c), "USB: core: add NO_LPM quirk for Razer Kiyo Pro webcam".
- Authored by JP Hein on 2026-03-31 and committed by Greg Kroah-Hartman on 2026-04-02, Cc stable.
- The commit message says:
  - The firmware "does not handle USB Link Power Management transitions reliably".
  - "When LPM is active, the device can enter a state where it fails to respond to control transfers, producing EPIPE (-32) errors on UVC probe control SET_CUR requests."
  - "In the worst case … the host controller [is] declared dead and every USB device on the bus [is] disconnected."
- The entry is in mainline `drivers/usb/core/quirks.c`: `{ USB_DEVICE(0x1532, 0x0e05), .driver_info = USB_QUIRK_NO_LPM }` **[S]** ([quirks.c](https://raw.githubusercontent.com/torvalds/linux/master/drivers/usb/core/quirks.c)).
- It is the only 0E05 entry. Mainline 7.4-rc2 has no uvcvideo entry for 0E05 (`uvc_driver.c` has no 0x1532 match) **[S]**.
- Our earlier plan docs already cite it: [results/agent_reports/plan_20261106/linux.md](../results/agent_reports/plan_20261106/linux.md) §2.

**The Ubuntu bugs behind it** **[W]**, both from the same reporter on an Intel PCH xHCI (0000:00:14.0):
- [LP #2017148](https://bugs.launchpad.net/ubuntu/+source/linux-signed-hwe-5.19/+bug/2017148) (2023-04-20, Kiyo Pro named in comment #3), on an ASUS Z790-A board:
  - The whole USB bus froze during Google Meet in Chrome. Only a reboot recovered it, and "Replugging does not help".
  - The log includes "xHCI host not responding to stop endpoint command", "HC died", and **"Set SEL for device-initiated U1 failed"**. That last line is an LPM-setup message.
  - On 2023-08-01 the reporter updated the firmware from **1.3.0.3 to 1.5.0.1**. No result was reported.
- [LP #2061177](https://bugs.launchpad.net/ubuntu/+source/linux/+bug/2061177) (2024-04-12, "USB bus crashes when using Razer Kiyo Pro webcam"):
  - Same pattern, plus "Failed to set UVC commit control : -110".
  - The camera was at path 2-9.1, which is behind a hub.
  - The workaround was reloading `xhci_pci`.
  - It recurred in May 2024. If the camera still had the firmware installed in 2023, then 1.5.0.1 did not fix it **[I]**.

**The quirk author's follow-up work** **[W]**: [jphein/kiyo-xhci-fix](https://github.com/jphein/kiyo-xhci-fix) (README, `kernel-patches/upstream-report.md`, `firmware-analysis/README.md`). This is one developer testing on his own machines, so treat it as a strong user report, not a maintainer statement.
- **Device:** "Razer Kiyo Pro firmware 1.5.0.1 (bcdDevice 8.21)"; SoC "Sigmastar SAV630D"; AIT-family firmware.
- **Failure modes he names:**
  1. LPM/autosuspend resume.
  2. "~25 rapid consecutive UVC SET_CUR operations overwhelm the firmware".
  3. A descriptor error: the interrupt endpoint EP5 IN declares `wBytesPerInterval = 8` but `wMaxPacketSize = 64`.
- **"Testing shows NO_LPM alone is insufficient."** His table shows a synthetic SET_CUR flood crashing at about 25 rounds with NO_LPM, with autosuspend off, with reset avoidance, and with all three together. It passed 500+ rounds only with a 200 ms delay after every control message (`USB_QUIRK_DELAY_CTRL_MSG`).
- **The failing request in real calls is the stream commit:** "`Failed to set UVC commit control : -110` precedes every `HC died`".
  - His throttling patch (v8.1) still failed in real use on 2026-05-30 and 2026-06-06. The second failure came "post-resume with Google Meet holding the camera (no active call)".
- **"the firmware wedge is triggered by stop + reconfigure"** (README, `cam-measure`).
- **His cheapest mitigation is starting each call from a freshly enumerated camera** (`pre-call.sh`). He cites "accumulated firmware state" as a likely destabiliser, while noting the confound.
- **He calls the bug "Confirmed cross-platform".** But his Windows and macOS evidence is the Razer forum threads in §3.2, plus the Raspberry Pi post that does not name its model **[I]**.
- **A trap with the kernel parameter:** on a kernel that already has the quirk, `usbcore.quirks=1532:0e05:k` turns NO_LPM **off**, because the flags are XORed. He found this on 2026-11-06. That matters for our Linux plan item LX-KP1 **[W]**.

**Maintainer and reviewer replies on the patch series** **[S]**: linux-usb/linux-media, March–August 2026, read through the [ratatoskr.run mirror](https://ratatoskr.run/linux-usb/2026/03/8466719/t), because lore.kernel.org returned 403.
- **Ricardo Ribalda** (uvcvideo maintainer), 2026-04-09: "A usb device shall not be able crash the whole USB host."
- **Michal Pecio** (xHCI reviewer):
  - 2026-04-09: "Not sure if the LPM thing is the cause or a symptom of general EP 0" dysfunction. Also: "The initial cause of all that may really be the device getting locked up for no good reason, but not 100% sure yet."
  - 2026-04-10, on the 8-byte interval: "Technically it's a spec violation … It seems most host controllers ignore byte per interval on interrupt."
  - Later: "some HCs are reliably killed by stopping SuperSpeed UVC streams"; "Looks like a HW bug"; "reloading xhci-pci is usually enough to fix this".
- **Mathias Nyman** (xHCI maintainer), 2026-04-10: "One theory could be that xHC control endpoint refuses to restart when its dequeue pointer is moved to a no-op TD"; "It's possible that disabling LPM helps as it reduces the number of control transfers".
- **Status:** only patch 1 (NO_LPM) has landed. The uvcvideo throttle patches are not in mainline as of 7.4-rc2 **[S]**.

### 3.2 Windows (Razer Insider forum; Kiyo Pro unless noted)

All of these are **[W]**. Razer staff replies only point to the firmware updater or move the conversation to private messages.

| Thread | Dates | Symptom and trigger | Recovery and what helped |
| --- | --- | --- | --- |
| [Assistance with Kiyo Pro freezing/crashing usb inputs](https://insider.razer.com/razer-support-45/assistance-with-kiyo-pro-freezing-crashing-usb-inputs-56400) | 2024-02 to 2025-03, 27 replies | OP: "the camera will freeze picture" when changing white balance or focus. The USB input system crashes, then the controllers come back but the camera stays frozen. Others: HDR on, Meet, OBS, Teams, webinar apps; "after about 5-10 minutes"; "crashes USB ports on Windows and Mac" | "physically unplug and replug the camera". Reported helps: HDR off; reinstalling updater "v1.5.0.1_r1"; a better 10 Gbps hub instead of a cheap 4-port hub; uninstalling Synapse (unconfirmed); a replacement unit failed too |
| [Razer Kiyo Pro Keeps Crashing](https://insider.razer.com/razer-support-45/razer-kiyo-pro-keeps-crashing-35335) | 2022-03 | Freezes to black and "does not respond to any requests to change settings". It happens when the camera refocuses itself, with and without Synapse | Unplug, wait a minute, replug. HDR off "seems to help" |
| [Razer Kiyo Pro disconnects](https://insider.razer.com/razer-support-45/razer-kiyo-pro-disconnects-66374) | 2024-08 to 2025-02, 39 replies | Drops out during Zoom, Meet and Teams calls and vanishes from Windows; some say every 30 s to 3 min; OBS works "for hours". One reply is about a **Kiyo Pro Ultra** fleet | Returns after minutes or needs a replug. Ports, cables, drivers and firmware did not help |
| [Razer Kiyo Pro keeps disconnecting](https://insider.razer.com/razer-support-45/razer-kiyo-pro-keeps-disconnecting-61173) | 2024-04 | Freezes moments after OBS starts; linked to a Synapse update | Replug after a reboot. A Razer rep suggested the RZ19-0364 firmware updater |
| [Randomly disconnecting (have to unplug and replug)](https://insider.razer.com/razer-support-45/razer-kiyo-pro-webcam-randomly-disconnecting-have-to-unplug-and-replug-to-fix-40521) | 2022-10 | 3–5 times a day in Zoom | Replug |
| [FIXED My Razer Kiyo Pro Camera](https://insider.razer.com/razer-support-45/fixed-my-razer-kiyo-pro-camera-74720) and [My Fix…](https://insider.razer.com/razer-support-45/my-fix-for-razer-kiyo-pro-camera-74721) | 2025-03, **same author twice** | Freezing in Zoom and Teams | Uninstall the Razer software and the Razer camera driver, then reboot so Windows' own driver loads. Reinstalling brought it back "like clockwork" |
| [video turns black 45-50 minutes into a call](https://insider.razer.com/razer-support-45/razer-kiyo-pro-video-turns-black-45-50-minutes-into-a-call-71008) | 2024-12 | Consistent time to failure in Meet and Teams | Rejoin the call. No other data |

- The Linux developer's report describes the two "fix" threads as "two threads (both 2024)". They are one author posting twice in 2025 **[W]**.
- **Nothing found:**
  - Microsoft Q&A has no Kiyo Pro thread.
  - No Chromium, OBS GitHub or Zoom bug names 1532:0E05.
  - No source ties 0x8007001F to the Kiyo Pro.
- Most Windows reports are about Zoom, Teams and Meet, which renegotiate formats often. I found none about multi-camera rigs **[I]**.

### 3.3 Other projects

- [libuvc #282](https://github.com/libuvc/libuvc/issues/282) (2024-07) is about skipping a `dwMaxPayloadTransferSize` check. It has a Kiyo Pro mention but no wedge report **[W]**.
- The CameraController and kiyoproctrls issues are about greyed-out controls and HDR having no effect, not about wedges **[W]**.

## 4. Firmware

- **Versions mentioned anywhere:**
  - 1.0.3 / 1.0.3.2: early units, 2021 forum posts **[W]**.
  - 1.3.0.3: LP #2017148 **[W]**.
  - 1.5.0.0 **[W]**.
  - **1.5.0.1_r1**: the current updater, "RZ19-0364" ([Razer support a_id 4582](https://mysupport.razer.com/app/answers/detail/a_id/4582)).
- **The Razer page could not be loaded.** It is a JavaScript app, and both WebFetch and curl returned an empty shell. The version comes from search-result extracts of that page ("Firmware Updater v1.5.0.1_r1. Connect the Razer Kiyo Pro to your PC, then click on 'UPDATE'"). It is confirmed by forum posts.
- **No release notes were found for any Kiyo Pro firmware.** The only Razer release note seen is for the original Kiyo's updater v2.3.2_r2 (a Low Light Compensation fix), a different product **[S/W]**. A 2021 forum thread is titled "KIYO PRO Firmware Update to fix AutoFocus issues" **[W]**.
- **How to read the version without a driver change:**
  - **bcdDevice** in the device descriptor. The suite already records it.
    - Every recorded Kiyo descriptor on Gerald shows **bcdDevice 0x0821**: the R1/R2 suites on 11-06, two suites on 11-09, the 11-11 suite, and the 11-06 self-tests **[M]** (for example [suite_20261111T040003Z/descriptors/descriptors.json](../results/windows/Gerald/suite_20261111T040003Z/descriptors/descriptors.json); the function devnode's `RevisionId` is 2081 = 0x0821 in [W-KIYO.json](../results/windows/Gerald/suite_20261111T040003Z/W-KIYO.json)).
    - The only mapping from bcdDevice to a marketing version is the Linux developer's "1.5.0.1 (bcdDevice 8.21)" **[W]**. So our camera is very probably on 1.5.0.1, the newest **[I]**.
  - **Razer's updater** displays the current version. But it is Razer software and can flash the device, so it is outside our rules **[I]**.
  - **The vendor extension unit:** XU6 selector 1 SET_CUR `{0xC0,0x03,0x01}`, then selector 2 GET_CUR, returns the version **[W]**. That is a write to a vendor command channel that also handles ROM-boot and flashing. **Do not use it** **[I]**.
- **Our descriptor has the same defect the Linux developer reports.** EP 0x85 (interrupt) has `wMaxPacketSize` 64, `bInterval` 8, and its SuperSpeed companion has **`wBytesPerInterval` 8** **[M]** (decoded from `raw.configuration` in the descriptor file above).
  - The Kiyo's BOS descriptor advertises U1 exit latency 10 µs, U2 exit latency 256 µs, and USB 2.0 LPM support (`bmAttributes` 0x06) **[M]**. So Windows can put this link into U1/U2 **[I]**.

## 5. Proposed causes, and how well each is supported

| Cause | Support outside our lab | Our evidence |
| --- | --- | --- |
| **USB 3 LPM (U1/U2)** | The kernel quirk says so **[S]**. LP #2017148 logged "Set SEL for device-initiated U1 failed" **[W]**. But the quirk author found NO_LPM "insufficient" **[W]**, and Nyman thinks LPM-off may help only by reducing control transfers **[S]** | LPM is "Moderate" on AC and DC, and selective suspend is Enabled, in every run **[M]** ([W-ENV.json](../results/windows/Gerald/suite_20261111T040003Z/W-ENV.json) `power`). The function shows `DeviceSelectiveSuspended` 1 **[M]**. Never varied, so untested |
| **Rapid UVC control traffic** (SET_CUR floods, probe→commit sequences) | Linux synthetic reproducer; real-call failures at `commit control` **[W]**. Windows threads tie freezes to changing white balance, focus or HDR **[W]** | Read-only polling alone (MF + DS every 10 s, 3,602 polls over 5 h) never wedged it **[M]** ([kiyo_overnight README](../results/windows/Gerald/kiyo_overnight_20261106/README.md)). Before the 01:52 onset the poller made 4 queries in about 3 s, the last finishing 0.4–0.7 s before the open that hung **[M]** ([suite_log.txt](../results/windows/Gerald/suite_20261111T040003Z/suite_log.txt) lines 1861–1866). That pattern also preceded many opens that did not fail **[I]** |
| **Stream start/stop transitions** (alt-setting change, commit, stream stop) | "stop + reconfigure" **[W]**; Pecio: stopping SuperSpeed UVC streams kills some HCs **[S]** | **All four onsets were at a stream start or stop** **[M]** (§6) |
| **Firmware bug** (EP0 stops answering) | Kernel commit wording **[S]**; descriptor defect **[W]**; reports on all OSes **[W]** | Same bcdDevice and descriptor as the Linux reports **[M]**. Once wedged it stays wedged for hours with the devnode healthy **[M]**, which fits a device that has stopped answering rather than a Windows stack fault **[I]** |
| **Host controller** | Ribalda, Pecio and Nyman all leave room for an xHC fault **[S]**. The quirk author rates Intel "tolerant" and ASMedia "catastrophic" **[W]** | Ours is an Intel Thunderbolt xHCI (8086:1138, behind a PCIe switch) **[M]** ([W-ENV.json](../results/windows/Gerald/suite_20261111T040003Z/W-ENV.json) `controllers`). Windows never lost the controller or other devices **[M]**. Never varied |
| **USB 3 hub** | One user fixed it with a better hub **[W]**. Microsoft lists hubs with a faulty "deferred packet" implementation, which "leads to transfer failures", among common U1/U2 problems **[S]** | The Kiyo has always been on the same Genesys Logic USB 3 hub (05E3:0625, port 4) on the Thunderbolt controller **[M]** ([descriptors.json](../results/windows/Gerald/suite_20261111T040003Z/descriptors/descriptors.json) `hub_instance_id`). Never varied |
| **Vendor software** (Synapse/RazerAppEngine, LogiTune) | Uninstalling Razer software and its camera driver helped one user, twice **[W]**. Synapse sends vendor XU commands **[W]** | Our Kiyo uses Microsoft's inbox `usbvideo` (driver 10.0.26100.9711), with no Razer camera driver **[M]** ([discovery.json](../results/windows/Gerald/suite_20261111T040003Z/discovery.json)). The 01:52 wedge had no vendor camera client, only `razer_elevation_service` running **[M]**. 5 h with LogiTuneAgent and RazerAppEngine attached did not wedge it **[M]**. So vendor software is neither necessary nor sufficient |
| **Plug-in age** | Nothing found | Ruled out: wedges at about 4–5, 210.6, 200.6–224.3 and 525.2 min, and none in a 5 h polls-only run **[M]** |

## 6. Our four onsets, checked against the files

Detailed timelines are in [windows_results_20261106.md](windows_results_20261106.md) §8 and [windows_results_20261110.md](windows_results_20261110.md) §9. I re-checked the following against the raw files **[M]**:

| Onset | Plug-in age | First symptom | Concurrent activity |
| --- | --- | --- | --- |
| 11-06 R1 | 200.6–224.3 min | MF 640x360@5: one frame at 2,170 ms, then the **reader release (stream stop) hung** | Kiyo alone; LogiTuneAgent and RazerAppEngine attached; 23.7 min untouched before |
| 11-06 R2 | 210.6 min | DS (ffmpeg CLI) MJPG 720p30 open hung 35.3 s with the iso pipe open | W-MULTI staggered round, other cameras opening; vendor agents attached |
| 11-10 17:04 | about 4–5 min (per the scene-check note) | MF open of the Kiyo alone: activate and set_type S_OK, **no first sample in 20.26 s**, release 5.26 s. Retry 2 min later: `0x8007001F` at `first_sample` ([summary.json](../results/windows/Gerald/scene_check_20261110/vid_1532/summary.json), [retry](../results/windows/Gerald/scene_check_20261110/retry_after_signal_closed/vid_1532/summary.json)) | LogiTuneAgent a Frame Server client on all four cameras; Signal on the C930e ([note](../results/windows/Gerald/scene_check_20261110/NOTE_SCENE_CHECK_NOT_RESULTS.txt)) |
| 11-11 01:52:46 | 525.2 min at round start (summary.md gives 525.7 for the first failed command) | DS all-together round 7 (`ds_all_together_028`). The Kiyo's ffmpeg open timed out after 30.27 s with the iso pipe open at alt 1 ([W-MULTI.json](../results/windows/Gerald/suite_20261111T040003Z/W-MULTI.json) `runs[27]`) | Three other cameras opened at the same instant, on the other controller. The generic camera re-enumerated 0.35 s earlier. No vendor camera client |

Corrections and additions to the brief:
- **The 01:52 onset was mostly timeouts, not `0x8007001F`.**
  - After the onset, the poller's codes were rc 5 timeouts 385 times, `0x800703E3` 37 times and `0x8007001F` only 4 times **[M]** ([W-KIYO.json](../results/windows/Gerald/suite_20261111T040003Z/W-KIYO.json) `failure_codes`).
  - The health check timed out at `activate` and the DS poll at `bind_filter` **[M]**.
  - So "every call fails with 0x8007001F" holds for 11-06 and 11-10, but on 11-11 most calls hung until their timeout **[M]**.
- **The plug-in time for 11-10 17:04 comes from the note, not from `LastArrivalDate`** **[M]**.
- **All four wedges were on the same port and devnode instance** (`A&34494D13&0&0000`, Thunderbolt xHCI → Genesys hub port 4), with LPM Moderate and selective suspend on **[M]**. So the hub, the controller and LPM are confounded with every failure **[I]**.
- **PyAV over DirectShow delivered YUY2 (`rawvideo`), not MJPEG, on the Kiyo**, in 50/50, 15/15 and 25/25 cycles, at below 90 % of the requested rate **[M]** ([summary.md](../results/windows/Gerald/suite_20261111T040003Z/summary.md) G-REL row; [windows_results_20261110.md](windows_results_20261110.md) §2–3). This is a format negotiation issue in that route, not part of the wedge **[I]**.

**How rare is it?** In the 11-11 run the Kiyo completed at least 1,200 stream starts before the wedge **[M]** ([W-CYC-KIYO.json](../results/windows/Gerald/suite_20261111T040003Z/W-CYC-KIYO.json) `cycles_per_variant`: 1,060 cycles, including 50 mode switches; plus W-PYMF and W-MULTI).
- Of those starts, about 21–22 were multi-camera rounds, and the wedge came in one of them.
- If every start carried the same risk, the chance that the only failure would land in those 22 starts is about 22/1,222 ≈ 2 % **[I]**.
- That points at multi-camera opens, but:
  - The category was picked after the fact.
  - Two of the four wedges (R1 and 17:04) were single-camera MF opens, so multi-camera opens cannot be necessary **[I]**.

## 7. Workarounds others use, and which fit our rules

| Workaround | Who | Fits our rules? |
| --- | --- | --- |
| Physical replug | everyone **[W]** | Yes. It is our only recovery, because vendor software vetoes programmatic restarts |
| Start each session from a fresh enumeration | the quirk author's `pre-call.sh` **[W]** | Yes, as a human replug before long runs. It cannot be automated here **[I]** |
| Turn HDR off | 2022 and 2024 threads **[W]** | Maybe. HDR is a vendor XU control. Reading its state is untested, and writing it changes the camera. Needs Dom **[I]** |
| Uninstall Razer software and the Razer camera driver | one author **[W]** | Already effectively true for the driver (inbox `usbvideo` **[M]**). Removing software is a system change, so it needs Dom |
| Avoid rapid control bursts; space control requests about 100–200 ms apart; extra delay before the stream commit | kernel throttle patches **[W]**; `DELAY_CTRL_MSG` test **[W]** | Yes, in our own code (tier 0). Note that Windows' `usbvideo` issues the probe/commit itself **[I]** |
| Better hub, or a direct port | one user **[W]** | Yes (moving a cable). Needs Dom present |
| LPM off (Linux quirk; Windows power plan "USB 3 Link Power Management: Off"; or Microsoft's `usblpm /disable U1\|U2` tool **[S]**) | kernel **[S]** | **Needs Dom's approval:** it is a machine-wide system setting |
| Reload xhci / rebind the port | Linux users and maintainers **[S/W]** | No: it is the programmatic restart that vendor software vetoes here |
| Reflash firmware 1.5.0.1_r1 | one user **[W]** | No: a device change, and we already run 1.5.0.1 **[I]** |

## 8. What the evidence says about our hypotheses

| Hypothesis | Verdict |
| --- | --- |
| Plug-in age | **Ruled out** as a trigger **[M]** |
| Cumulative use | **Weakened**: the 17:04 wedge came at about the first stream after a replug **[M]**. "Accumulated firmware state" is still argued upstream **[W]** |
| Concurrent multi-camera opens / DirectShow | **Possible amplifier, not necessary.** 2 of 4 wedges; about 2 % chance-coincidence estimate in the 11-11 run **[I]**. Both multi-camera wedges were ffmpeg-CLI DirectShow opens, yet 400/400 single-camera ffmpeg-CLI cycles passed **[M]** |
| Vendor software contention | **Weakened**: neither necessary (01:52) nor sufficient (5 h attached) **[M]**. It may still raise the risk via XU traffic **[W/I]** |
| Hub / Thunderbolt controller | **Untested, fully confounded** **[M]**. Upstream links some controllers to stream-stop failures **[S]** |
| LPM / selective suspend | **Plausible, untested, confounded** **[M]**. Upstream is split: the quirk exists **[S]**, but NO_LPM alone was insufficient on Linux **[W]** |
| Stream negotiation in fragile firmware (probe/commit, alt change, stop) | **Best supported**: every onset was at a start or stop **[M]**, and this matches the upstream failure point **[W/S]**. It is a mechanism, and the hypotheses above may change how often it fires **[I]** |

## 9. Cheap tests that separate them (within our rules)

The wedge seems rare (on the order of 1 in 1,000 starts), so each arm needs hundreds to thousands of starts. Results are rates, not single runs. Every wedge costs one human replug.
- Run each arm from a fresh replug.
- Log `bcdDevice`, port and power settings.
- Record the exact command that hung, using the post-lock timestamps fixed in §11 of the 11-06 doc.

1. **Diagnose the next wedge before replugging** (tier 0, no new risk; do it whenever a wedge happens).
   - Read the device and configuration descriptors again with `helpers/win_descriptors.py`. That sends standard GET_DESCRIPTOR on EP0. Also read the hub's connection info.
   - If standard requests still answer, the firmware's UVC side is stuck while EP0 itself works. If they fail, EP0 or the link is dead.
   - Nothing in our files shows a descriptor read during a wedge **[M]**.

2. **Multi-camera vs single-camera open rate** (tier 0).
   - Arm A: W-MULTI "ds all-together" only, repeated (4 cameras, ffmpeg CLI), up to 300 rounds or a wedge.
   - Arm B: the same ffmpeg-CLI open/close of the Kiyo alone, the same number of starts, with the other cameras idle.
   - Then Arm C: MF all-together.
   - If A wedges within a few hundred rounds and B and C do not, simultaneous DirectShow opens raise the risk. The B-vs-C comparison also settles MF vs DS.
   - Run with the poller **off** in one repeat, to remove the "polls right before the open" factor.

3. **Control burst right before a stream start** (tier 0, read-only).
   - Kiyo alone, MF. Arm X: each open is preceded by a back-to-back burst of read-only MF and DS control queries (about 10 in 2 s). Arm Y: no queries within 5 s of an open.
   - 1,000 starts each.
   - This tests a read-only version of the upstream "rapid control traffic" trigger, without the SET_CUR floods that kill controllers on Linux.
   - A SET_CUR flood version would also be tier 0, but it can take the whole Thunderbolt controller down. **Needs Dom's approval.**

4. **Topology arm: a direct Intel PCH SuperSpeed port, no Genesys hub and no Thunderbolt controller** (tier 0; a cable move by Dom).
   - Repeat whichever of tests 2–3 wedged.
   - If the wedge disappears, the hub or controller is involved. LPM stays on, so this separates hub/controller from LPM.

5. **LPM arm** (**needs Dom's approval**: a power-plan change, reverted afterwards). Two routes:
   - USB 3 Link Power Management = Off.
   - Or, as a tier-0 alternative that avoids settings: the Kiyo on a **USB 2.0 port or cable**. There are no U1/U2 states at high speed, but USB 2.0 LPM L1 may still apply because the BOS advertises it, and the Kiyo's high-speed modes differ.
   - Repeat the wedging arm. If the wedge rate drops sharply with LPM off on the same port, LPM is a contributor. Upstream Linux data predicts it will not drop to zero **[W]**.

6. **Optional: USB ETW trace during the arms** (Microsoft's logman recipe with the USBXHCI, UCX and USBHUB3 providers **[S]**).
   - It records the failing transfer, its USB status (stall vs timeout), and power transitions, so the next wedge is pinned to a request.
   - It needs an elevated prompt and writes to `%SystemRoot%\Tracing`. It changes no settings, but **ask Dom first**.

**Order:** 1 (free) → 2 → 3 → 4 → 5. Tests 2 and 3 need no approval and decide whether the multi-camera result is real. Test 4 needs only a cable move.

## 10. What I could not determine

- **The real root cause.** Upstream has not settled whether the device firmware, the xHC, or both are at fault **[S]**.
- **Release notes for any Kiyo Pro firmware.** Razer's support page would not render, and no changelog was found.
- **An official mapping from bcdDevice to firmware version.** The only source for 0x0821 = 1.5.0.1 is the Linux developer **[W]**.
- **Whether Windows enables U1/U2 on this link in practice, and in what state the link is during a wedge.** There is no tier-0 read of link state without an ETW trace.
- **Whether HDR is on in our camera.**
- **Whether standard EP0 requests still work during a wedge** (test 1).
- **Which process `?:39608` was** at the 01:52 onset (also open in the 11-10 results doc).
- **The Kiyo Pro Ultra's USB ID**, and whether it shares the bug. One forum reply suggests so **[W]**.

## Sources

Accessed 2026-11-11.

**Primary [S]**
- Linux commit 8b7a42ecdcde, "USB: core: add NO_LPM quirk for Razer Kiyo Pro webcam": https://github.com/torvalds/linux/commit/8b7a42ecdcdeb55580d9345412f7f8fc5aca3f6c (message read via the GitHub API)
- Mainline quirks table: https://raw.githubusercontent.com/torvalds/linux/master/drivers/usb/core/quirks.c
- Mainline uvcvideo device table (no 0x1532 entry; Makefile 7.4-rc2): https://raw.githubusercontent.com/torvalds/linux/master/drivers/media/usb/uvc/uvc_driver.c
- Patch thread "[PATCH v5 0/3] USB/UVC: Add quirks to prevent Razer Kiyo Pro xHCI cascade failure", with replies from Ricardo Ribalda, Michal Pecio and Mathias Nyman (mirror): https://ratatoskr.run/linux-usb/2026/03/8466719/t ; lore: https://lore.kernel.org/20260331003806.212565-2-jp@jphein.com (403 to automated fetch)
- Related thread, "usb: core: Fix bandwidth for devices with invalid wBytesPerInterval" (Apr 2026): https://lkml.iu.edu/hypermail/linux/kernel/2604.0/02321.html
- Microsoft, Common hardware problems with U1 or U2 implementation: https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/common-hardware-problems-with-u1-or-u2-implementation
- Microsoft, U1 and U2 transitions: https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/u1-and-u2-transitions
- Microsoft, USBLPM tool: https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/usblpm-tool
- Microsoft, How to capture a USB event trace with Logman: https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/how-to-capture-a-usb-event-trace
- Razer, Kiyo Pro Firmware Updater RZ19-0364 (did not render; version from search extracts): https://mysupport.razer.com/app/answers/detail/a_id/4582
- Razer, Kiyo (original) Firmware Updater RZ19-02320 (different model): https://mysupport.razer.com/app/answers/detail/a_id/1664

**User reports and projects [W]**
- Launchpad #2061177: https://bugs.launchpad.net/ubuntu/+source/linux/+bug/2061177
- Launchpad #2017148: https://bugs.launchpad.net/ubuntu/+source/linux-signed-hwe-5.19/+bug/2017148
- jphein/kiyo-xhci-fix (README, kernel-patches/upstream-report.md, firmware-analysis/README.md): https://github.com/jphein/kiyo-xhci-fix ; issue #2: https://github.com/jphein/kiyo-xhci-fix/issues/2
- Razer Insider threads:
  - https://insider.razer.com/razer-support-45/assistance-with-kiyo-pro-freezing-crashing-usb-inputs-56400
  - https://insider.razer.com/razer-support-45/razer-kiyo-pro-keeps-crashing-35335
  - https://insider.razer.com/razer-support-45/razer-kiyo-pro-disconnects-66374
  - https://insider.razer.com/razer-support-45/razer-kiyo-pro-keeps-disconnecting-61173
  - https://insider.razer.com/razer-support-45/razer-kiyo-pro-webcam-randomly-disconnecting-have-to-unplug-and-replug-to-fix-40521
  - https://insider.razer.com/razer-support-45/fixed-my-razer-kiyo-pro-camera-74720
  - https://insider.razer.com/razer-support-45/my-fix-for-razer-kiyo-pro-camera-74721
  - https://insider.razer.com/razer-support-45/razer-kiyo-pro-video-turns-black-45-50-minutes-into-a-call-71008
  - https://insider.razer.com/razer-support-45/razer-kiyo-crashing-after-changing-focus-settings-with-v4l2-ctl-under-linux-67440 (model not stated)
  - https://insider.razer.com/razer-support-45/what-firmware-version-do-i-have-on-my-kiyo-pro-27167
  - https://insider.razer.com/razer-support-45/kiyo-pro-firmware-update-to-fix-autofocus-issues-25985 (title only)
- Level1Techs (original Kiyo, 2018): https://forum.level1techs.com/t/pci-e-usb-3-0-controller-loses-uvc-webcam-upon-changing-image-format/128780
- Kiyo X hardware ID (driver database): https://treexy.com/products/driver-fusion/database/imaging-and-cameras/razer/kiyo-x/
- libuvc #282: https://github.com/libuvc/libuvc/issues/282

**Our files [M]**
- [results/windows/Gerald/suite_20261111T040003Z/](../results/windows/Gerald/suite_20261111T040003Z/): `summary.md`, `suite_log.txt`, `W-KIYO.json`, `W-MULTI.json`, `W-CYC-KIYO.json`, `W-ENV.json`, `discovery.json`, `descriptors/descriptors.json`
- [results/windows/Gerald/scene_check_20261110/](../results/windows/Gerald/scene_check_20261110/)
- [results/windows/Gerald/kiyo_overnight_20261106/README.md](../results/windows/Gerald/kiyo_overnight_20261106/README.md)
- [windows_results_20261106.md](windows_results_20261106.md) §8, [windows_results_20261110.md](windows_results_20261110.md) §9, [kiyo_overnight_handoff.md](kiyo_overnight_handoff.md), [macos_uvc_controls_review.md](macos_uvc_controls_review.md) §6
