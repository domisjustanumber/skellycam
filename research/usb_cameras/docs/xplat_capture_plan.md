# Cross-platform UVC capture without driver changes: plan and test suites

2026-11-06 · Dom · status: plan written. Windows suite built and run twice on Gerald (results in §9 and [windows_results_20261106.md](windows_results_20261106.md)). Linux and macOS suites built and unit-tested, not yet run on hardware.

Paths are relative to `research/usb_cameras/` unless noted. Confidence labels as in [REPORT.md](../REPORT.md): **measured** (a result file supports it), **doc** (vendor docs or source code), **web** (forum, issue or blog), **inferred** (reasoning, not run). The research behind this plan is in `results/agent_reports/plan_20261106/` (one report per topic, each with an adversarial verifier's notes appended):

| Topic | Report |
| --- | --- |
| MF vs DirectShow, the metadata registry value, open/close reliability | [windows_mf_vs_ds.md](../results/agent_reports/plan_20261106/windows_mf_vs_ds.md) |
| Third-party libraries vs new code | [deps_audit.md](../results/agent_reports/plan_20261106/deps_audit.md) |
| macOS versions and camera stack | [macos.md](../results/agent_reports/plan_20261106/macos.md) |
| Linux versions, kernels and uvcvideo | [linux.md](../results/agent_reports/plan_20261106/linux.md) |
| Reusable harness code | [local_inventory.md](../results/agent_reports/plan_20261106/local_inventory.md) |
| Which cameras share bandwidth, and which ports to suggest | [bandwidth_domain_model.md](../results/agent_reports/plan_20261106/bandwidth_domain_model.md) |
| Topology mapping per OS | [topology_windows.md](../results/agent_reports/plan_20261106/topology_windows.md), [topology_linux.md](../results/agent_reports/plan_20261106/topology_linux.md), [topology_macos.md](../results/agent_reports/plan_20261106/topology_macos.md) |

## 1. The brief

Find the capture approach for skellycam that meets, on Windows, Linux (Ubuntu and Fedora KDE Plasma) and macOS:

| ID | Goal |
| --- | --- |
| **G-ID** | Reliable camera indexing: a stable identity per physical camera, and every API's device list maps to it |
| **G-TS** | Reliable, accurate per-frame timestamps |
| **G-MJPEG** | Reliable native MJPEG (the camera's own JPEG bytes, no decode or re-encode) at **every** resolution the camera offers |
| **G-CTRL** | Reliable camera control: exposure, gain, white balance, focus and the rest the camera offers |
| **G-BW** | (added 2026-11-06) Map the USB topology, tell which cameras share bandwidth, and when a concurrent open fails, tell the user which cameras collided and which ports to move one to |

**Hard constraint: no change to the camera drivers.** That rules out the WinUSB swap on Windows, and detaching or replacing the kernel/system driver on Linux and macOS. Every libusb or libuvc **streaming** route from the earlier study is therefore out, and so is app-chosen alt setting (REPORT finding 18).

Rules Dom added on 2026-11-06:
- **Reliable means open/close/open/close works every time.** It does not mean long soaks.
- **Bandwidth contention is a test case**, because users hit it. Gerald's current layout has the C922 and the generic camera on one hub by design.
- **The Razer Kiyo Pro is in every test.** It is temperamental, not excluded: it can stop answering control requests, after which every API fails with `0x8007001F`. Every test uses per-call timeouts and records Kiyo failures instead of skipping it.

**Two tiers.** Driver *configuration* is not a driver change, but it still needs admin rights and touches the device. Every result is therefore reported in two tiers:
- **Tier 0, zero-touch:** works on a user's machine as found.
- **Tier 1, one-time admin configuration:** for example the Windows `MetadataBufferSizeInKB0` registry value (§2.2), or Linux `hwtimestamps` / `quirks` module parameters or video-group membership for headless use.

Dom has not yet decided whether tier 1 is acceptable. The suites measure both, so that decision can be made on data.

## 2. Answers to the questions asked

### 2.1 Do the same controls and resolutions appear in DirectShow and Media Foundation?

**Resolutions: yes, the same sizes. Measured** on all four cameras from the 10-25 listing (`results/windows/Gerald/mjpeg_formats/summary.json`): MJPEG frame sizes are identical in the USB descriptors, the MF native types and DirectShow's `GetStreamCaps` (C922 17, C930e 17, generic 5, Kiyo 4). The windows suite re-checks this today, mode by mode and rate by rate (test W-FMT).

The lists have different shapes, and two of the differences can catch out capture code:
- **MF lists one native type per (size, frame interval)**, matching the descriptors exactly: 120 MJPG types on the C922, 119 C930e, 10 generic, 28 Kiyo.
- **DirectShow lists each frame descriptor twice** (one VIDEOINFOHEADER and one VIDEOINFOHEADER2 entry), each with a min–max frame-rate range, e.g. C922 1280x720 at 5–60 fps. The real discrete rates need `IAMVideoControl::GetFrameRateList`. So "120 vs 17" is presentation, not capability.
- **Trap 1: MF inserts a decoded NV12 type immediately before every MJPG type** on cameras with no native NV12 (C922, C930e, generic; not the Kiyo). Code that takes the first type matching W×H@fps gets decoded pixels. Select MJPG by subtype and assert `GetCurrentMediaType` is MJPG with converters disabled. **Measured.**
- **Trap 2: OS policy acts only on the MF / Frame Server path.**
  - A Windows 11 Settings video rotation other than "No rotation" removes compressed types (doc).
  - The multi-app camera mode forces one media type (doc).
  - A share-mode source cannot change type or extended controls (doc).
  - Settings-page defaults are applied at stream start (doc).
  - On Gerald, DirectShow bypasses Frame Server (ksproxy CLSID, no `EnableDshowRedirection`). **Measured** (registry read).

**Controls: the same driver property sets through both.** Both paths reach usbvideo's KS property sets (`PROPSETID_VIDCAP_CAMERACONTROL`, `…VIDEOPROCAMP`). The C922's ranges read through the MF source equal those read through the DirectShow filter: exposure −11..−2, WB 2000–6500 K, gain 0–255, focus 0–250 step 5. **Measured** for the C922 only. The Kiyo's ranges differ from the Logitech ones (WB 2000–7500 step 10, exposure default −6), so control code needs per-camera range tables. All four cameras are UVC 1.0 (`bcdUVC 1.00`), so no UVC 1.5 or Microsoft-XU controls are expected. W-CTRL-LIST now covers every camera, every CAMERACONTROL id and VIDEOPROCAMP ids 0–13, both APIs, diffed against the descriptors' `bmControls`.

### 2.2 What `MetadataBufferSizeInKB0` does, and what it costs other applications

- **What it is.** A per-pin `REG_DWORD` (`MetadataBufferSizeInKB<pin>`, documented in Microsoft's "UVC 1.5 extensions" §2.2.3). When it is present and nonzero, `usbvideo.sys` allocates a metadata buffer of that many KB per frame.
- **What usbvideo writes into it.** One `KSCAMERA_METADATA_ITEMHEADER` with `MetadataId_UsbVideoHeader` (=2), followed by `KSSTREAM_UVC_METADATA`. That is the PTS, SCR and SOF token of the **first and last** USB payload of each frame, about 40 bytes. MF exposes it to an app as `MFSampleExtension_CaptureMetadata` → `MF_CAPTURE_METADATA_FRAME_RAWSTREAM`. **Doc + measured.**
- **Where it is set.** Microsoft intends vendors to set it in a custom INF, which would be a driver change and is out. The working route, also used by librealsense, writes it under the camera's device-interface keys:

  ```text
  HKLM\SYSTEM\CurrentControlSet\Control\DeviceClasses\{65E8773D-…}
  HKLM\SYSTEM\CurrentControlSet\Control\DeviceClasses\{E5323777-…}
    \##?#USB#…#{guid}\#GLOBAL\Device Parameters
  ```

  This needs admin.
- **It belongs to one device instance.** The C922 has a serial, so it kept the value through today's replug. The C930e and generic camera moved ports this morning, got new instance IDs and lost it; the old instances keep stale values. **Measured 2026-11-06.** Any tier-1 tool must therefore re-apply it whenever a serial-less camera appears on a new port, as librealsense says.
- **It takes effect only after the device restarts.** The 10-25 hazard came from the restart, not from the value: a `pnputil /restart-device` vetoed by LogiTune left `DN_NEED_RESTART`, and every MF app then failed with `MF_E_REBOOT_REQUIRED` until a replug, while DirectShow kept working. That happened even on a run that wrote no value. **Measured.** A tier-1 tool must never restart devices; it should ask for a replug. Whether a fresh write applies without any restart is untested.
- **Cost to other applications: expected negligible, not measured.** A few KB per frame are allocated. Apps that don't read the attribute never see it, and DirectShow apps are unaffected (inferred). The one side effect seen on Gerald: the C922's MF arrival-minus-sample latency median moved from ~16 ms to ~1 ms after it was set (a beat-phase effect, REPORT "areas of interest"). Frame delivery, fps and JPEG bytes were unchanged.
- **Today's cameras give a natural A/B without new UAC:**

  | Camera | Value on its current instance |
  | --- | --- |
  | C922 | set |
  | Kiyo Pro | set |
  | C930e (new port) | not set |
  | generic | not set |

  The Windows run compares frame rate, CPU and open/close behaviour across the two groups (W-TS, W-CYC). Group membership is confounded with camera model, so a clean A/B on one camera needs one UAC write plus a replug; that is listed as attended item A3.
- **There is no zero-touch PTS route on Windows for these cameras.** None has the Microsoft XU or an MS OS 2.0 descriptor, and DirectShow has no documented metadata consumer. The tier-0 fallback is a frame-index model fitted to arrival times. It scored like PTS (~0.5 ms, the flash-method floor) only for the C922 and only with a whole-run fit. Causal (live) fits scored 0.59–3.6 ms, and it cannot see dropped frames the way PTS can. **Measured** (REPORT findings 7–9).

### 2.3 How reliable is frame extraction, DirectShow vs MF?

**What is known.** Frame data is equivalent: byte-identical JPEG headers, the same fps, and about 1–2% of one core each (REPORT findings 1–2). The failure modes differ (**measured** on Gerald, short runs):
- A bandwidth refusal fails DirectShow at open (`OSError(5)` in PyAV), but MF only at the first `ReadSample` (`0x800718CF`). An MF health check must therefore read one frame.
- Synchronous `ReadSample` has no timeout. One MF batch stalled for ~94 s.
- After a refusal, the generic camera once went `DeviceNotFound` or re-enumerated.
- `MF_E_REBOOT_REQUIRED` locked out MF but not DirectShow.

**Documented MF failure modes** (doc / web), each of which the cycle test classifies:

| Code | Meaning |
| --- | --- |
| `0xC00D3704` `MF_E_HW_MFT_FAILED_START_STREAMING` | camera in use; Chromium uses `IMFSensorActivityMonitor` to confirm |
| `0xC00D3EA2` | device invalidated |
| `0xC00D3EA3` | preempted |
| `MF_E_INVALIDREQUEST` | transient; Chromium retries 200 × 50 ms |
| `MF_E_SHUTDOWN` | a cached `IMFActivate` was re-activated without `ShutdownObject` |

There are also reports of `ActivateObject` freezing for 5–10 minutes and of Frame Server crash loops.

The safe pattern:
- async reader, or a watchdog;
- a one-frame health check;
- release in the order reader → `IMFMediaSource::Shutdown` → `IMFActivate::ShutdownObject`;
- per-camera DirectShow fallback, as Chromium does.

OBS still uses DirectShow for webcams; its MF pull request has been unmerged since 2024.

**What was missing is what Dom asked for: repeated open/close.** W-CYC runs it (§6.2). For each camera, it runs MF in-process, MF in a new process each cycle, PyAV DirectShow in both modes, and OpenCV `CAP_DSHOW` as the status-quo baseline. It also runs mode-switching cycles and all-cameras-at-once cycles (W-MULTI). Every failure is classified by code and time, and the test records whether the next cycle recovered.

### 2.4 How much is outsourced to third-party libraries vs new code?

**No library meets all four goals on any OS without a driver change** (doc/web, `deps_audit.md`). The parts that matter most must be written here in every architecture:
- the serial-else-port identity key;
- UVC PTS/SCR clock mapping;
- macOS UVC controls;
- bandwidth-refusal handling and the topology mapper;
- Kiyo-style failure handling.

| Architecture | New code (est.) | Third-party at run time | Gaps it leaves |
| --- | --- | --- | --- |
| **A. Python + per-OS native code** (small C++ MF extension on Windows; ctypes V4L2 on Linux; PyObjC AVFoundation + an endpoint-0 UVC control path on macOS) | ~6–9 kLOC, of which ~4 kLOC exists as harness or prototype code here | PyObjC (macOS); pybind11/nanobind at build time only | none known; macOS MJPEG unproven (§2.5) |
| B. PyAV/FFmpeg everywhere + control side channels | ~4.5–6.5 kLOC | PyAV (one dominant maintainer); FFmpeg's dshow demuxer (no commit since 2024-10-17) | Windows G-TS (synthesized timestamps); macOS G-MJPEG (the avfoundation demuxer emits decoded video only); G-CTRL everywhere unless A's native code is added; an unfixed FFmpeg v4l2 out-of-bounds read on MJPEG mmap packets in PyAV 19.0.2 |
| C. Rust core + PyO3 | ~7–10 kLOC | windows-rs (mid 0.62 → 0.100 transition), objc2 (one maintainer); own V4L2 ioctls (the `v4l` crate is stale) | same as A, plus a Rust build for every platform |

Healthy enough to depend on (verified 2026-11-06):

| Library | Version, date, notes |
| --- | --- |
| PyAV | 19.0.2, 2026-10-21; bundles FFmpeg 9.0.2; bus factor 1; dropped Python 3.11 |
| PyObjC | 13.0, 2026-10-30; built with the macOS 27 SDK |
| pybind11 / nanobind | 3.1, build-time only |
| PyO3 / maturin | 0.30.1 / 1.16.0 |
| pywin32, comtypes | 312, 1.4.17 |
| v4l-utils | 1.32, for tests |

**Do not take as hard dependencies:** nokhwa, uvc-util, CameraController, pygrabber, duvc-ctl, PySDL3, the `v4l` crate, v4l2py, pyv4l2, and GStreamer's mediafoundation plugin (0 commits in 12 months).

**Recommendation: A.** Keep PyAV DirectShow as a Windows fallback path, never as the only path. The suites therefore test exactly A's building blocks plus the PyAV and OpenCV baselines.

### 2.5 What tests are needed for macOS, and on which versions?

**Versions** (doc/web, Apple security-release page, 2026-10-26):

| Release | Latest point release | Hardware |
| --- | --- | --- |
| macOS 27 Golden Gate | 27.2 | Apple silicon only |
| macOS 26 Tahoe | 26.7.2 | last release for Intel |
| macOS 15 Sequoia | 15.8.2 | |
| macOS 14 Sonoma | no update in the October round | |

| Leg | Machine | Suite |
| --- | --- | --- |
| M1 | Apple silicon, macOS 27.x latest | full |
| M2 | Apple silicon, macOS 26.7.x latest | full |
| M3 | Intel Mac, macOS 26.7.x | reduced: ENV, ID, FMT, MJPEG, CYC, CTRL-LIST |
| M4 | Apple silicon, macOS 15.8.x | reduced, as M3 |
| — | macOS 14 and older | skip |

One M1–M4 Mac that shipped with macOS 15 or earlier can multi-boot 15, 26 and 27. Run the Kiyo on two Apple silicon generations if possible: CameraController issue #138 has a Kiyo whose controls were greyed out on an M4 but worked on an M2.

**What the macOS tests must settle:**
1. **G-MJPEG is unproven and gates the macOS design (M-MJPEG).** Since macOS 12.3, cameras are owned by Apple's UVC camera extension (UVCAssistant). Chromium's current code asks AVFoundation for `'dmb1'` (`kCMVideoCodecType_JPEG_OpenDML`) when the device format is MJPEG, and reads the JPEG from the block buffer. One third-party run on a Sonix camera saw MJPEG modes offered only as decoded `420v`. FFmpeg, OBS, GStreamer, SDL3 and nokhwa all deliver decoded pixels on macOS. M-MJPEG tries every advertised format with three `videoSettings` variants (nil, `{}`, `'dmb1'`) and checks the bytes. If no camera passes, macOS has no tier-0 MJPEG route.
2. **G-CTRL.** AVFoundation on macOS offers only auto/locked exposure, focus and white balance, with no absolute values. UVC class requests on endpoint 0 work without claiming the interface: one measured third-party run, plus three code bases (uvc-util, CameraController, libusb's DeviceRequest path). That works in practice but is outside Apple's documented contract. M-CTRL tests both routes and records the IOKit return codes. It never claims an interface and never detaches a driver.
3. **G-TS.** Apple documents only that the sample-buffer PTS is on the session's `synchronizationClock`. Whether that is host time stamped at arrival or derived from the camera's PTS/SCR is unknown, and no accuracy figure exists anywhere. M-TS compares the input port's clock with the host clock, checks the frame-interval grid, and uses `CMIOSampleBufferGetSequenceNumber` to count drops. It needs the ESP32 LED rig for an absolute score; a screen flash is corrupted by ProMotion and Edge Light.
4. **G-ID.** `AVCaptureDevice.uniqueID` for USB cameras is the hex of `locationID<<32 | VID<<16 | PID`: port-stable, and it changes on a port move. The serial comes from the IORegistry (`USB Serial Number`). Read identity from the IORegistry, not libusb.
5. **Effects and permissions (M-FX, M-TCC).**
   - Log `isCenterStageActive`, `isPortraitEffectActive`, `isStudioLightActive`, `reactionEffectsInProgress` and `canPerformReactionEffects` per camera.
   - Record that Edge Light (macOS 26.2+) is off. It changes the scene light itself and is not exposed as a device property.
   - Record that camera permission (TCC) goes to the launching app. A process without permission gets zero frames and no error.
6. **G-BW (M-TOPO, M-MULTI).** No error code for a refused reservation is documented. M-MULTI must catch three possible signals: an error, a silent zero-frame session, or reduced fps. It reads the alt macOS picked, with no claim, through `GET_INTERFACE` on endpoint 0.

### 2.6 What tests are needed for Linux, and on which versions?

**Versions** (doc, kernel and distro release data, checked 2026-11-06):

| Leg | Distro | Kernel | Why |
| --- | --- | --- | --- |
| L1 | Ubuntu 24.04.5, GA kernel | 6.8 | server and GA installs; also covers 22.04 HWE; pre-6.14 error-frame behaviour, 10 KiB metadata buffer |
| L2 | Ubuntu 26.04 LTS (and 24.04.5 desktops on HWE) | 7.0 | the current LTS kernel; Kiyo NO_LPM quirk present |
| L3 | Fedora 45 KDE Plasma (shipped 2026-11-03) | 7.2 | newest uvcvideo (hw-timestamp, metadata and sequence fixes); Wayland + PipeWire session |
| opt | Fedora KDE 44, Ubuntu 26.10 (7.3) | — | desktop-session tests only; uvcvideo is unchanged 7.2 → 7.3 |

Run every leg on Gerald from an external SSD (the same Intel xHCI as the Windows results, Windows untouched). Add one AMD-chipset PC for the bandwidth-domain test (L-TOPO-VENDOR), because per-root-port domains are only measured on Intel.

uvcvideo changes that affect the tests (doc, commit-checked):

| Kernel | Change |
| --- | --- |
| 6.11 | C922 invalid-device-SOF quirk; hw-timestamp fixes |
| 6.14 | `nodrop` on by default: corrupt frames reach the app flagged `V4L2_BUF_FLAG_ERROR` instead of being dropped |
| 6.16 | granular power management: an idle fd lets the camera autosuspend, so controls may not survive idle |
| 6.17 | MSXU 1.5 metadata format |
| 7.0 | fix for buffer return on a failed start; USB-core NO_LPM quirk for the Kiyo Pro (1532:0E05). It was added because the Kiyo stops answering control transfers with LPM active, which matches its Windows symptom. Also backported to stable 6.12.81, 6.18.34 and 6.19.12 |
| 7.1 | the app can enlarge the metadata buffer through `S_FMT` |
| 7.2 | hw-timestamp SOF, partial-metadata and sequence-number fixes |

**What the Linux tests must settle:**
- **G-TS.** The buffer timestamp is `CLOCK_MONOTONIC` taken when the frame's first payload is processed, quantized to URB completions (up to ~4 ms). The metadata node (`V4L2_META_FMT_UVC`, `/dev/videoN+1`) gives the camera's PTS/SCR with the same permissions as the video node: **tier 0**. Its host timestamp is per URB, not per payload. `hwtimestamps=1` is root-only (tier 1). On 6.8, metadata overflow shows up only as sequence gaps.
- **G-MJPEG.** Raw V4L2 mmap is the reference. Also test PyAV v4l2 (`input_format=mjpeg`), OpenCV `CAP_V4L2` with `CONVERT_RGB=0` (raw buffer, but it ignores the error flag) and GStreamer `v4l2src` `image/jpeg`. `S_FMT` silently picks the nearest size, so the suite checks the size that comes back.
- **Desktop session (L-DESK).**
  - The active-seat user gets a `uaccess` ACL; SSH/headless needs the video group (tier 1).
  - WirePlumber's V4L2 monitor is preferred for UVC devices.
  - A streaming PipeWire client should make our `S_FMT`/`REQBUFS` fail with `EBUSY`. But `S_FMT` sends a PROBE to the camera before returning `EBUSY`, so the suite checks `fuser` first.
- **G-ID.** Use the sysfs serial when present and unique, else `ID_PATH` without the USB revision. `/dev/v4l/by-id` collides for identical serial-less cameras. systemd v254+ adds `usbv2`/`usbv3` by-path links.
- **G-BW.** uvcvideo picks the smallest alt that fits the camera's request. A refusal shows at `STREAMON` as `ENOSPC`, but the step-down logic must also handle `ENOMEM`, `EIO` and `EPIPE`/`ETIMEDOUT`. The granted alt is world-readable in sysfs. `quirks=128` is tier 1 and still skips compressed formats (REPORT finding 21).
- **G-CTRL.**
  - Setting `exposure_time_absolute` while auto exposure is on returns `EACCES`, so set manual mode first.
  - Readback after the first read can be cached, so verify on the image.
  - Kiyo HDR and FoV are vendor XU controls; record them, but don't set them blind.

## 3. Candidate approaches and how the suites decide between them

| Platform | Candidate (tier 0 unless noted) | Decided by |
| --- | --- | --- |
| Windows | **MF native** (`IMFSourceReader`, native MJPG, converters off, async reads, watchdog), controls through `IAMCameraControl`/`IAMVideoProcAmp` queried from the MF source; timestamps from a frame-index fit to arrival (tier 0) or UVC PTS (tier 1) | W-CYC ≥ the DirectShow success rate; W-MJPEG all modes; W-CTRL-EFFECT; W-TS |
| Windows | **PyAV DirectShow** `vcodec=mjpeg` as per-camera fallback; controls through a DirectShow side channel | same tests; chosen as primary only if MF fails W-CYC where DirectShow passes |
| Windows | OpenCV `CAP_DSHOW` (skellycam today) | baseline in W-CYC only (no JPEG bytes; REPORT finding 3) |
| Linux | **V4L2 direct** (own ctypes ioctls, mmap), controls via `VIDIOC_S_EXT_CTRLS`, timestamps from the metadata node's PTS/SCR fit (tier 0) | L-MJPEG, L-CYC, L-TS, L-CTRL-EFFECT, L-DESK |
| Linux | PyAV v4l2 / OpenCV `CAP_V4L2` raw | L-MJPEG / L-CYC comparison only |
| macOS | **AVFoundation** with `'dmb1'` if M-MJPEG passes, controls through AVFoundation lock modes plus endpoint-0 UVC requests | M-MJPEG gates; M-CTRL; M-CYC; M-TS |
| All | **Topology mapper + bandwidth navigator** (§5) | *-TOPO, *-MULTI |

**Rating thresholds** (proposed; Dom to confirm):

| Goal | Yes | Partial | No |
| --- | --- | --- | --- |
| G-ID | every API's list maps 1:1 to `camera_identity` keys, identical over 20 repeated enumerations; key unchanged over reboot and same-port replug (serial cameras also over a port move) | maps 1:1 but changes on reboot or replug, or only some APIs expose a mappable path | index or name only |
| G-TS | causal per-frame error ≤ 0.5 ms (1σ) against a ground truth, and drops detectable | ≤ 2 ms, or tier 1 only, or no ground truth yet but self-consistent device timestamps | > 2 ms, synthesized, or a host-time grid (Windows 16 ms) |
| G-MJPEG | every advertised MJPEG mode negotiates, delivers ≥ 99% valid JPEG (strict decode, or lenient with a known camera quirk noted), SOF0 size = request, fps within 2% of the camera's real rate, header SHA-1 equal across APIs | some modes fail, or decode is lenient-only without a known quirk | no JPEG bytes |
| G-CTRL | every control in the descriptors is listed with the descriptor's range; set + readback agree; the effect shows in the image (exposure, gain, WB, focus); works before and after stream start; 3/3 runs | needs a workaround (e.g. re-apply after start), or works on some cameras only | cannot set |
| Reliability (cycles) | ≥ 99% of cycles deliver a first frame within 2 s; no hang beyond the watchdog; no state that needs a replug | 95–99%, or recoverable hangs | < 95%, or a replug needed |
| G-BW | the mapper predicts every observed refusal (no false "fits" verdicts); refusal classified correctly; the message lists only ports in other domains; retry after a refusal works | predictions right but labels raw, or classification ambiguous on one API | refusals not detected or misattributed |

## 4. What changed from the earlier gap plan

[test_gap_plan.md](test_gap_plan.md) (10-30) assumed a WinUSB swap was allowed and is organised around the older goals (G1 sync … G5 bandwidth control). Under the new brief:
- **Dropped:**
  - the B1–B4 WinUSB tests;
  - every libusb streaming row;
  - the app-chosen alt (G5 "yes");
  - the libusb legs of C1–C3, T1 and T2;
  - Linux libuvc via udev and macOS MX6/MX6b streaming.
- **Kept as is:** the ESP32 sync rig (R0–R2) as the ground truth for G-TS and the exposure effect, and the FSIN track for exposure alignment. Both are hardware projects outside this suite. The suites accept a `--flash` / rig hook.
- **Folded in:**
  - C1–C3 (controls) → *-CTRL-EFFECT;
  - C2 (formats) → *-FMT and *-MJPEG;
  - X1 (soak) → *-CYC (cycles, not duration, per Dom);
  - I1–I3 (identity) → *-ID;
  - LX/MX → the Linux and macOS suites.
- **New:** *-TOPO and *-MULTI (topology mapper, user message), *-CYC, *-CTRL-LIST across APIs, Kiyo in every test.
- Test IDs here use the prefixes `W-`, `L-` and `M-` so they never collide with the old LX1–6 and MX1–6b.

## 5. USB topology mapper and bandwidth navigation

Source: [bandwidth_domain_model.md](../results/agent_reports/plan_20261106/bandwidth_domain_model.md) and the three per-OS topology reports (each adversarially verified).

**Which cameras share bandwidth.**
- For a USB 2.0 (high-speed) camera, the unit that runs out is the **USB 2.0 link from one xHCI root port**. Everything below that root port, through any hubs, shares one 480 Mb/s bus, of which at most 80% of each 125 µs microframe can be reserved for isochronous and interrupt transfers.
- **On Gerald's Intel controller each root port is its own domain.** Two max-alt cameras on different root ports both streamed at 98.4% of one microframe combined. Behind one root port, the threshold lies between 75.2% and 80.9%. **Measured** (10-27 rerun).
- Per-root-port domains are an **Intel implementation choice, not an xHCI rule**. xHCI 1.2 lets several root ports share one "bus instance". Intel also has a controller-wide DMI ceiling over all domains (inferred from Linux `xhci.h`).
- **AMD looks controller-wide.** A 2025 Linux patch's test log (commit 59d50e53e070) shows one high-speed video device on AMD Raven cutting the available HS bandwidth on all four HS root ports from 79% to 39% (doc; one machine; whether the camera was streaming is not stated).
- ASMedia, Renesas, VIA, Fresco and Etron are **unknown**. The mapper's policy table:

  | Controller | Default domain |
  | --- | --- |
  | Intel 8086:7A60 | per root port (measured) |
  | other Intel parts | per root port (assumed) |
  | AMD (1022:*) | controller-wide |
  | unknown vendors | controller-wide, but ports on the same controller are still listed, marked "may share bandwidth (unverified)", so the list is never empty |

  A learned escalation to controller-wide needs two consistent refusals below 75% of the root-port budget, or one root-only debugfs `port_bandwidth` reading on Linux 6.16+. A single refusal can come from hidden periodic load, such as an audio device starting later.
- A USB 3 hub is two hubs: a USB 2.0 camera behind it uses the USB 2.0 half, which can sit on a different controller from the USB 3 half. Gerald's Genesys GL3523 does exactly that. **Measured.**
- USB 2.0 and USB 3 traffic do not compete, so the Kiyo Pro, at SuperSpeed on the Thunderbolt controller, is in a separate domain.

**The mapper, per OS** (no admin, no camera open, no libusb enumeration):

| Step | Windows | Linux | macOS |
| --- | --- | --- | --- |
| Tree | CfgMgr parent walk + hub IOCTLs (`IOCTL_USB_GET_NODE_INFORMATION`, `…CONNECTION_INFORMATION_EX(_V2)` for speed and empty ports, `…PORT_CONNECTOR_PROPERTIES` for user-visible and companion ports); extends `bandwidth/win_usb_topology.py` | sysfs `/sys/bus/usb/devices`: buses grouped by their PCI parent (an xHCI has a USB 2.0 and a USB 3 bus); `portN/connect_type`, `portN/peer`, `portN/location`, `physical_location` | IORegistry: `AppleUSBXHCI*` → `IOUSBHostDevice` (`locationID`, `USB Serial Number`, speed) and port objects for empty ports |
| Camera → device | MF symlink / DirectShow path → device instance → parent chain | `/dev/videoN` → sysfs interface → device | `uniqueID` → `locationID` → IORegistry node |
| Domain key | (controller, USB 2.0 root port) | (PCI parent, root port on the 480 Mb/s bus) | (controller, top nibble of `locationID`) |
| Observed load | open isochronous pipes from the hub IOCTL (no admin) | each interface's `bAlternateSetting` + `ep_XX/wMaxPacketSize` | IORegistry interface properties (unverified) |
| Labels | `DEVPKEY_Device_PhysicalDeviceLocation` (_PLD), friendly names, connector properties | `physical_location` (panel, position), PCI names | port and connector properties |

**Mode cost.**
- **Before a mode is opened, only the camera's largest alt is a safe upper bound.** The camera chooses its alt from its own PROBE answer, which a non-owning app cannot send.
- **Learn each camera-mode's real alt by opening it once alone and reading the granted alt.** Cache it per (VID, PID, bcdDevice, format, size, fps). Measured examples on Gerald:
  - C922 MJPEG: 640x480@30 = alt 4 (640 B), 1280x720@30 = alt 9, 1080p@5 = alt 5;
  - C930e: 720p30 = alt 11 (3072 B);
  - generic: always 3069 B.

**Runtime algorithm.**
1. **Map:** domains and current loads.
2. **Plan:** predicted load per domain for the requested modes; warn early when a domain is "over".
3. **Open:** in priority order with a stagger. A camera counts as admitted only after its **first frame**, because MF fails at the first read.
4. **Classify a failure:**
   - bandwidth (certain): Windows MF `0x800718CF`; Linux `ENOSPC`;
   - bandwidth (probable): DirectShow `OSError(5)` / `E_ACCESSDENIED`, or Linux `ENOMEM`, when another camera in the same domain is streaming and the predicted load is over;
   - not bandwidth: in use, `0x8007001F`, a privacy denial.
   - Retry once, because a refused start can be followed by one zero-frame start (REPORT finding 19).
5. **Report** with the template below, plus the "stay where you are" alternative: the highest cached mode that makes the domain fit.

**Message template** (labels fall back from _PLD panel and position → OS friendly name → controller and port number → "a different USB port directly on the computer"):

```text
{A} and {B} share USB bandwidth: both connect through {shared_hop}.
When I tried to open them both at the same time, {loser} failed with a USB bandwidth error ({code}).
At these settings they need about {pct_total}% of what that USB 2.0 link allows ({A} {mode_A}: {pct_A}%, {B} {mode_B}: {pct_B}%).
Suggest moving one of those cameras to any of the following controller ports:
  {controller_or_panel_group}: {port_label}, {port_label}, ...
Or, to keep both where they are, lower {B} to {alt_mode_B} (about {pct_alt_B}%).
```

Rules for the port list:
- Never suggest a port on the same hub or dock, or the SuperSpeed twin of the conflicting connector.
- Prefer empty, user-visible ports on a controller known to have per-root-port domains.
- On an "uncertain" controller, also suggest a different controller.

Corrections from the topology verifiers (they apply to every suite's TOPO and MULTI, and to the shared model):
- **Group and rank ports by the controller of the port's USB 2.0 half, not by the connector's SuperSpeed controller.** On Thunderbolt and Intel TCSS USB-C ports, the USB 2.0 pins sit on the chipset (PCH) xHCI. On Gerald, the TB USB-C ports' USB 2.0 halves are PCH HS12/HS13. So "try a different controller" could send a USB 2.0 camera back to the same one. Linux never peers ports across controllers, so connectors are merged by equal `location` in userspace.
- **Count load the way the threshold was calibrated:** isochronous endpoints only (cameras and audio). The 75.2–80.9% bracket was measured with interrupt pipes and a TT present but not counted. Use the 90% SuperSpeed periodic budget for SS cameras (the Kiyo).
- **Linux:** compute a camera's current bytes per microframe from the sysfs `descriptors` blob at the alt given by `bAlternateSetting`. The `ep_XX/wMaxPacketSize` attribute drops the multiplier bits (a 3×1024 alt reads 1024), and `interval` is a decoded string; use `bInterval`.
- **Do not pair USB 3 hub halves by ContainerId alone.** Gerald's Genesys hubs all report the same fixed 2011 GUID. Use the companion IOCTL (Windows), `portN/peer` (Linux) or companion port numbers (macOS), with topology position as a tie-break.
- **Candidate ports include empty ports on hard-wired internal hubs** (rear clusters, front-panel headers), labelled with that hub's root-port domain.
- **BIOS `_UPC` "connectable" over-reports.** Rank ports by evidence of a real socket: USB-C geometry in `_PLD`, an ACPI HSnn/SSnn name, past phantom devnodes. Put likely header ports last, and offer a "plug something in to identify this port" step. Don't call TypeC=0 ports "Type-A": say "USB 3 port (not USB-C)" or "USB 2.0 port".
- **macOS:**
  - enumerate controllers via `AppleUSBHostController`;
  - label Apple-silicon ports from AppleHPM `port-location`/`port-number`;
  - key domains on the `locationID` root, because the M4 Mac mini's two front ports share one root port behind a hub tier;
  - a USB-C port holding a charger or display has no USB child but is not free, so word suggestions as "if nothing is plugged in";
  - read the live alt from the IOUSBHostInterface `bAlternateSetting` key (untested).
- **Detecting a refusal without an error code:**
  - **PyAV DirectShow** gives an ambiguous `EIO`, which slow graph transitions also produce.
  - **OpenCV** hides the code in a log line.
  - **openpnp-capture** (skellycam's `dom/openpnp-capture` branch) discards the DirectShow `Run` HRESULT, so a refusal looks like a successful open with no frames.
  - **Use instead:** a first-frame watchdog, plus the prediction, plus (Linux) the camera's VS interface still at alt 0 while another device in the domain holds an isochronous alt.
  - **Linux 6.17+:** the camera gets its max alt with a "Reducing max payload transfer size" warning, instead of `EIO` "No fast enough alt setting".
- **The "retry once after a refusal" rule was verified only on libusb.** W-MULTI measures it on MF and DirectShow.
- **When every free port shares the colliding domain** (e.g. Raspberry Pi 4's single integrated hub, or a laptop with one controller), say so, and offer the lower mode or a one-controller-per-port PCIe card instead of a useless port list.

**Prediction for Gerald's layout today** (computed from measured alts):

| Pair on root port HS13 | Load | Prediction |
| --- | --- | --- |
| C922 MJPEG 720p30 (alt 9) + generic | 81.1% of a microframe | refused |
| C922 640x480@30 (alt 4) + generic | 59.7% | fits |
| C922 1080p@5 (alt 5) + generic | 62.2% | fits |

W-MULTI tests exactly these.

Gerald's topology, from the non-admin probe of 2026-11-06 (`results/agent_reports/plan_20261106/topology_windows_run/probe_20261106.json`):
- **Intel 8086:7A60 xHCI:** HS01–16 and SS01–09.
  - Empty, user-connectable high-speed ports: HS01, 02, 04, 05, 06, 09 (USB-C), 12 (the USB 2.0 half of Thunderbolt USB-C #1), 15 and 16 (likely headers).
  - HS10 is an internal 4-port hub, all empty.
- **Thunderbolt 4 xHCI 8086:1138:** SuperSpeed only for the two USB-C ports.

So for the C922 + generic conflict, the message should list HS01/02/04/05/06/09/12 on the Intel controller (HS15/16 last). It must never list HS13's dock ports, or HS07, which already holds the C930e at near max alt. Labels on this ASUS board are weak: its `_PLD` gives only generic positions, apart from the USB-C geometry.

## 6. Test suites

Each suite lives in `suite/<os>/`. Each has one entry point that runs every unattended test in order and writes `results/<os>/<host>/suite_<UTC stamp>/`: one JSON per test with the standard fields (`test`, `platform`, `hostname`, `utc_started`, `command`, `environment`, `cameras`, measurements, `verdicts`), plus `summary.md`. Shared, OS-neutral code (JPEG checks, identity key, topology domain model and message builder, cycle statistics, rating) is in `suite/common/`. Large raw frames stay outside the repo.

**Mode scope (Dom, 2026-11-06), applied to speed up testing:**
- Streaming tests (MJPEG, CYC, MULTI, TS, CTRL-EFFECT) use only modes at **≥ 30 fps and ≥ 720 lines** (1280x720 and up). Listing tests (FMT, FMT-NOGRAB) still list and compare every mode.
- Consequence: on Gerald's shared hub every C922 + generic pair is over budget, so MULTI tests only the "refused" side there. The "fits" side is covered by cameras in different domains.
- A `--all-modes` flag restores the full set.

### 6.1 Rules for every suite

- **No driver change, ever.**
  - No WinUSB or libusbK.
  - No `libusb_detach_kernel_driver`, `libusb_claim_interface` or set-configuration.
  - No unbind/rebind.
  - No device restarts (`pnputil /restart-device`, `/remove-device`): on Gerald LogiTune vetoes them and leaves MF locked out.
  - Tier-1 steps (registry value, module parameters, power-plan changes) are never automatic. They are listed as attended items with an announced UAC or sudo prompt.
- **All cameras attached as found, including the Kiyo.** Every camera call runs with a timeout, usually in a child process that the runner kills on hang. A hang or `0x8007001F` is a result, not a crash.
- **Windows:** every camera-opening command goes through `tools/camlock.py`.
- **Re-arrivals:** log `LastArrivalDate` (Windows), the sysfs `devnum` (Linux) or the IORegistry entry ID (macOS) per camera before and after each test. Steps with an unexplained re-arrival are flagged.

### 6.2 Test catalogue

The same IDs on every OS, prefixed `W-`, `L-`, `M-`:

| Test | What it does | Answers |
| --- | --- | --- |
| **ENV** | OS/kernel build, controller list, camera list with health (problem codes, driver/service, firmware bcdDevice), power settings (USB selective suspend and LPM on Windows; autosuspend on Linux), software holding cameras (LogiTune, Razer, PipeWire), tier-1 state (metadata registry per current instance; module parameters) | context for every rating |
| **TOPO** | Build the topology map and domains, list free ports with the best available labels, compute each camera's domain and predicted conflicts for its default mode; dump everything as JSON | G-BW mapper |
| **ID** | Enumerate cameras through every API (Windows: MF, DirectShow, PyAV/FFmpeg dshow, OpenCV index; Linux: V4L2 nodes, by-id/by-path, PipeWire; macOS: AVFoundation, IORegistry); map each entry to its `camera_identity` key; repeat 20 times; check 1:1 mapping, stable order and enumeration time. Attended extension: reboot, same-port replug, port move | G-ID |
| **FMT** | Every format/size/rate per API vs the USB descriptors (Windows: MF native types; DirectShow caps de-duplicated + `GetFrameRateList`). Flag synthesized types (MF NV12), missing or extra modes, continuous vs discrete rates | Q "same resolutions?", G-MJPEG coverage |
| **CTRL-LIST** | Every control and range per API vs the descriptors' `bmControls` (Windows: all CAMERACONTROL ids and VIDEOPROCAMP 0–13 through the MF source and through the DirectShow filter; Linux: full `QUERY_EXT_CTRL` walk; macOS: AVFoundation flags + endpoint-0 GET_MIN/MAX/RES/DEF/CUR) | Q "same controls?", G-CTRL |
| **CTRL-EFFECT** | Per camera × control path, set → readback → effect in the image, before vs after stream start, and persistence across close/reopen: exposure (2–3 in-range values → luma ratio), gain (luma), WB temperature (R/B ratio), focus with AF off (Laplacian sharpness vs focus value). Autofocus and auto-exposure restored at the end | G-CTRL |
| **MJPEG** | Every advertised MJPEG mode, every candidate API: negotiate, capture ~3 s, check SOI/EOI, strict decode, SOF0 size, fps vs nominal, CPU; JPEG header SHA-1 compared across APIs | G-MJPEG |
| **CYC** | Per camera × API: K open → first frame → N frames → close cycles in one process, and K' cycles in a new process each time; a mode-switching variant (alternate two modes); timings (open, first frame, close) and every failure code; the next cycle after a failure records recovery | Q "reliability", Dom's open/close criterion |
| **MULTI** | The skellycam pattern, all cameras at once (one process per camera, started together, then staggered), repeated K times; the predicted conflicting pairs from TOPO in the predicted-refused and predicted-fits modes; classify every refusal; record which camera loses; run the mapper's message builder on each real refusal; retry once; read granted alts from the OS | G-BW, reliability under contention |
| **FMT-NOGRAB** | (added 2026-11-06) Which method lists a camera's formats correctly **without grabbing the camera or starting a stream**. Every format-listing method on the OS is run under three conditions: camera idle; camera streaming in another process via MF; camera streaming via DirectShow. Each is scored on: completeness vs the USB descriptors; whether it works while the camera is in use; whether it disturbs the other process's stream (frame gap, error); whether it reserves bandwidth or starts a stream (granted alt during the listing); whether it blocks another process's open during the listing; and time. Methods per OS:<br>- **Windows:** hub-IOCTL descriptors (no driver involvement); MF activate + `GetNativeMediaType` with no `Start`; DirectShow filter + `IAMStreamConfig`; `ffmpeg -list_options`. WinRT and OpenCV are noted: neither can list formats without initializing capture.<br>- **Linux:** sysfs `descriptors` (cached, no bus traffic); `VIDIOC_ENUM_FMT/FRAMESIZES/FRAMEINTERVALS` on an fd with no `STREAMON`; `v4l2-ctl`; PipeWire node properties.<br>- **macOS:** `AVCaptureDevice.formats` with no session; IORegistry. macOS has no second capture API, so the third condition is skipped there by default, and completeness needs descriptors cached by an opt-in `--ep0` run. | format discovery for the UI and the mode-alt cache without disturbing cameras in use |
| **TS** | Per camera × API: which timestamp fields exist; grid/quantization of each; device PTS/SCR presence (tier 0 or 1) and self-consistency; clock fit (PTS→host) and frame-index fit (arrival → index) with causal and whole-run errors; drop detection (PTS gaps, sequence numbers). Optional `--flash`/rig ground truth when a rig is in view | G-TS |
| **KIYO** | Kiyo control requests polled every 10 s from plug-in age X for N minutes, recording when and how it stops answering; the same from every API in use. Attended arm: USB 3 LPM off (power plan), or Kiyo on a USB 2.0 port | Kiyo failure signature and the LPM hypothesis |
| Windows only: **POLICY** | Settings-page rotation and effects, multi-app camera mode, Studio Effects presence, DshowBridge/EnableDshowRedirection values, Frame Server service state | traps from §2.1 |
| Linux only: **DESK** | Who holds `/dev/video*` (`fuser`), PipeWire/WirePlumber nodes, a direct V4L2 open while PipeWire streams (expect `EBUSY`) and while it only monitors (expect success), and permissions in the session vs over SSH | Fedora KDE / Ubuntu desktop interference |
| macOS only: **FX**, **TCC** | Video-effect flags per camera; Edge Light state; permission state and behaviour without permission | macOS frame alteration, packaging |

**Attended items** (need Dom; not in the unattended run):

| ID | Item |
| --- | --- |
| A1 | Reboot, same-port replug and port move for ID |
| A2 | Move a camera to a suggested port and confirm the conflict clears (MULTI) |
| A3 | Clean metadata A/B on one camera (one announced UAC write + replug) |
| A4 | Kiyo with USB 3 LPM off, or on a USB 2.0 port |
| A5 | Ground-truth timing with the ESP32 rig (when built) |
| A6 | MF and DirectShow cycles while another app holds the camera |

### 6.3 Where each suite runs

| Suite | Machine(s) | Status |
| --- | --- | --- |
| `suite/windows` | Gerald (Windows 11 build 26300); a Windows 10 22H2 machine later | run 1 2026-11-06 (all modes; Kiyo wedged early). Then harness fixes from a verified analysis, the mode scope and FMT-NOGRAB. Run 2 2026-11-06 (§9) |
| `suite/linux` | L1–L3 on Gerald from an external SSD; an AMD PC for TOPO/MULTI | built and reviewed; 54 unit tests (fake sysfs + simulator) in Docker; never run on a camera |
| `suite/macos` | M1–M4 (§2.5) | built and reviewed; 55 unit tests (fake ioreg/AVFoundation); never run on a Mac |

## 7. Order of work

1. Windows suite on Gerald, unattended (this session).
2. Attended Windows items A1–A4, A6 in one sitting (~1 h of Dom's time).
3. Linux L3 (Fedora KDE 45), then L2, then L1, on Gerald from an SSD; then the AMD PC for TOPO/MULTI.
4. macOS M1 first: M-MJPEG decides whether the rest of the macOS design stands.
5. Rig-based G-TS scoring (A5) on all three OSes when the ESP32 rig exists.
6. Re-rate §3's table and pick the architecture per OS.

## 8. Open questions for Dom

- Is tier 1 (the metadata registry value; Linux video group or module parameters) acceptable for skellycam users?
- Are the rating thresholds in §3 right?
- Should vendor extension-unit controls (Kiyo HDR and FoV, Logitech XUs) count toward G-CTRL, or only the standard UVC controls?

## 9. Windows results (Gerald, 2026-11-06)

Full results, with every number tied to its JSON: [windows_results_20261106.md](windows_results_20261106.md). The two runs were:
- **Run 1:** all modes, `results/windows/Gerald/suite_20261106T181941Z/`.
- **Run 2:** after about 30 harness fixes, with the mode scope and FMT-NOGRAB added, `…/suite_20261106T224912Z/`.

Each run's results were analysed per test group and checked by an adversarial verifier (`analysis/` in each folder).

**Answers to the questions asked:**

| Question | Answer (Windows, measured unless noted) |
| --- | --- |
| Same controls and resolutions in DirectShow and MF? | **Yes.** MF, DirectShow and the USB descriptors list the same MJPEG modes on all four cameras, and identical controls and ranges, with 0 differences. The traps are presentation: MF slips a decoded NV12 type in front of every MJPG type, and DirectShow lists each mode twice with min–max rates. Two C930e YUY2 2 fps modes reach no API. |
| DShow vs MF reliability (open/close)? | **Equal.** 630/630 cycles per API on the healthy cameras over both runs, with no hangs or resets. MF reaches the first frame 260–290 ms sooner, always delivers the requested MJPEG, and reports bandwidth refusals as a certain HRESULT. **PyAV-DirectShow silently falls back to YUY2** wherever a raw format matches, so a DirectShow fallback must use the ffmpeg CLI (`-vcodec mjpeg`) or native code. skellycam's current OpenCV `CAP_DSHOW` sequence opens every time but takes 2.7–11.5 s to its first configured frame. |
| List formats without grabbing the camera? | **MF activation + `GetNativeMediaType` with no `Start`** (or a bound DirectShow filter): complete for every mode Windows can open, 29–61 ms, works while another process streams, starts no stream and disturbs nothing. The hub-IOCTL descriptor read gives descriptor-level data without touching the camera driver. `ffmpeg -list_options` prints only min/max rates and hides 720p30 MJPEG on two cameras. OpenCV and WinRT cannot list without opening capture. |
| Native MJPEG at all resolutions? | **Yes through MF and DirectShow:** run 1 negotiated MJPEG in all 249 advertised modes on the three working cameras, with byte-identical headers on MF and DS. The camera-side limits are the C922's MJPEG ignoring rates below 30 (and tearing at @5), and 720p60 delivering ~30.5 fps under auto exposure. Request ≥ 30 fps and decimate. |
| Timestamps? | **Tier 0** (no admin): every Windows host timestamp sits on a 16 ms grid, and DirectShow pts are synthesized. Only a frame-index fit remains, and it cannot be scored without the rig. **Tier 1** (registry value): UVC PTS/SCR arrives on every frame where the value is set on the current instance. It is self-consistent only on the C922 (SCR regular to ~2 µs); the Kiyo's PTS ticks at 1 kHz. Undecided until A5. |
| Camera control? | Through `IAMCameraControl`/`IAMVideoProcAmp` from the MF source. The C922 passes everything. The C930e resets exposure and gain at stream start (re-apply ≥ 1 s after the first frame). The generic's gain and WB have no effect. Kiyo: exposure, WB and focus work. |
| Bandwidth / topology mapper? | The mapper predicted every refusal (63/63, 0 false fits), and predicted cost matched the open pipe 149/149. MF says `0x800718CF`; DirectShow gives an ambiguous EIO, separable via the FFmpeg log. **The generic camera re-enumerates ~10 s after every DirectShow refusal**, never after MF. User messages name the shared hub and list only ports in other domains (example in §7 of the results doc). |
| Kiyo Pro? | **It wedges about 210–224 min after plug-in** in both runs, under completely different workloads. A stream start hangs, then every call fails with `0x8007001F`. The devnode stays "healthy", and only a replug recovers it. Hypotheses (time since plug-in, USB 3 LPM, vendor agents) and the tests that separate them are in §8 of the results doc. |

**Decision for Windows (pending A1–A6 and the rig):**
- MF native is the primary path.
- DirectShow via the ffmpeg CLI is a per-camera fallback.
- Replace OpenCV.
- MF no-`Start` listing gives format discovery; the hub IOCTL feeds the mode-alt cache.
- Controls are applied after the first frame and verified.
- Fault handling covers a first-frame watchdog, per-call timeouts and a "replug needed" state.

The harness bugs still open, and the attended items, are in §11 of the results doc.
