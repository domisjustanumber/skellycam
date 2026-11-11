# Capture stack options: PyAV vs OpenCV vs custom native code

2026-11-08 · Dom · status: **proposed plan.** Windows claims rest on the Gerald results. The Linux and macOS
claims come from docs and source code only, and §6 lists the tests that would back them.

*2026-11-11:* the §6.1 Windows unattended tests ran on 11-10/11. §9 summarises the results; the full write-up is
[windows_results_20261110.md](windows_results_20261110.md). The tables in §1–§5 are not yet updated.

Paths are relative to `research/usb_cameras/docs/`. Confidence labels follow [REPORT.md](../REPORT.md) and
[xplat_capture_plan.md](xplat_capture_plan.md):
- **m** (measured: a result file on Gerald supports it);
- **d** (vendor docs or library source read by an earlier agent and checked by a verifier);
- **d?** (docs or source, not checked in this study: treat as a hypothesis; §6 has a test for each one);
- **w** (web: a forum post, issue or third-party run);
- **i** (inferred).

All "m" results come from one Windows 11 machine (Gerald, build 26300, Intel xHCI) and four cameras: C922, C930e,
generic 4C4A:4A55 and Razer Kiyo Pro. **No Linux or macOS hardware run exists.**

## 1. Answer in brief

| Requirement | Best route on Windows | Best route on Linux | Best route on macOS |
| --- | --- | --- | --- |
| 1 Raw JPEG | custom C++ (MF) **m** | custom V4L2 mmap **d** | custom ObjC++ (AVFoundation `'dmb1'`) **unproven, gating** |
| 2 List devices, no open | custom (MF/DS property bags) **m** | custom (sysfs/udev) **d** | custom (AVFoundation discovery + IORegistry) **d** |
| 3 Device ID | custom (MF symlink → serial-else-port key) **m** | custom (sysfs serial, else `ID_PATH`) **d** | custom (`uniqueID` → IORegistry serial, else locationID) **d + w** |
| 4 Formats, no open | custom (MF activate, no `Start`; hub IOCTL for descriptors) **m** | custom (sysfs descriptors / `VIDIOC_ENUM_*`) **d** | custom (`AVCaptureDevice.formats`) **d** |
| 5–8 Exposure, AE, focus, AF | custom (`IAMCameraControl` from the MF source) **m**, with per-camera rules | custom (`VIDIOC_S_EXT_CTRLS`) **d**; OpenCV also possible **d** | custom: **CoreMediaIO feature controls first**, unopened IOKit endpoint-0 UVC requests as the fallback, AVFoundation lock modes kept in step **d + w** (see [macos_uvc_controls_review.md](macos_uvc_controls_review.md)) |
| 9a Uncompressed | custom (MF native YUY2/NV12) **i**; PyAV gets YUY2 **m** | custom V4L2 YUYV **d** | AVFoundation `yuvs`/`2vuy` **w**: camera-native or converted is unknown |
| 9b Host clock (QPC) | custom: MF sample time + QPC at callback **m** | V4L2 buffer time (`CLOCK_MONOTONIC`) **d** | sample-buffer PTS on the session clock **d** (its origin is unknown) |
| 9c UVC PTS/SCR | custom MF metadata, **tier 1 only** (admin registry value) **m** | custom metadata node, tier 0 **d** | **no known route** **i** |

**Recommendation: write custom native code on all three OSes, and use neither PyAV nor OpenCV on the capture
path.** The only realistic alternative, PyAV for frames plus native code for the rest, still needs about 60–70%
of the native code (deps audit, **i**). On top of that it would:
- add a measured silent MJPEG→YUY2 fallback on Windows;
- add a Linux MJPEG out-of-bounds read in PyAV 19.0.2;
- deliver no raw JPEG on macOS.

OpenCV is ruled out on Windows (it never returns JPEG bytes, **m**) and on macOS (**d**). PyAV and OpenCV each
stay useful in one place: PyAV as a test oracle, and OpenCV for decoding and display downstream (§4).

Things no option can deliver:
- **macOS raw JPEG** is unproven for every option. PyAV and OpenCV cannot deliver it by design (**d**), so test
  M-MJPEG decides whether requirement 1 is possible on macOS at all, not which option wins.
- **macOS PTS/SCR** has no known API in any option.
- **Windows PTS/SCR** needs a one-time admin registry value per camera in every option.

## 2. What "reliably" means here

Dom's rules (2026-11-06), applied to every claim and test below:
- **Reliability means open/close/open/close works every time**, not long soaks. Threshold (plan §3): ≥ 99% of
  cycles reach a first frame within 2 s, no hang beyond the watchdog, and no state that needs a replug. A per-camera
  "≥ 99%" claim needs at least 381 failure-free cycles; the 90 cycles per camera and API run so far bound it only
  at about 0.96 (Wilson lower bound; [windows_results_20261106.md](windows_results_20261106.md) §2, §11).
- **No driver changes**, so no libusb streaming or claiming. libusb stays out of tests even where it would not
  claim the camera.
- **Every test includes the Kiyo Pro.** Every call gets a timeout, and a Kiyo failure is recorded as a result.
- **Bandwidth contention is a test case.**
- **Streaming tests use only modes at ≥ 30 fps and ≥ 720 lines.** Listing tests cover every mode.
- **Tier 0** works as found. **Tier 1** needs a one-time admin step. Dom approved the Windows metadata value for
  testing on Gerald (set on all four cameras 2026-11-08). Whether skellycam users may be asked to set it is
  still open (plan §8).

## 3. The options

| Option | Windows | Linux | macOS |
| --- | --- | --- | --- |
| **PyAV 19.0.2** (FFmpeg 9.0.2 libavdevice) | `dshow` demuxer, `vcodec=mjpeg` | `v4l2` demuxer, `input_format=mjpeg` | `avfoundation` demuxer |
| **OpenCV 4.12** (skellycam today) | `CAP_DSHOW` (current), `CAP_MSMF` | `CAP_V4L2` with `CONVERT_RGB=0` | `CAP_AVFOUNDATION` |
| **Custom native** | C++17: Media Foundation `IMFSourceReader` (async, native type, converters off), `IAMCameraControl`/`IAMVideoProcAmp`/`IKsControl` queried from the MF source, KS capture metadata. Measured as `suite/windows/native/wincam.exe` and the earlier `mf_mjpeg_capture` / `mf_uvc_timing` probes | C++ or ctypes: V4L2 mmap, metadata node, `VIDIOC_*_EXT_CTRLS`, sysfs. Drafted as the Python suite helpers, unit-tested only | ObjC++: AVFoundation capture plus IOKit endpoint-0 UVC requests without opening the device. Drafted as PyObjC + ctypes suite helpers (`suite/macos/helpers/iokit_usb.py`), unit-tested only |

## 4. Comparison, requirement by requirement

Rating per cell: **Yes**, **Part.** (works with a caveat that matters), **No**, **?** (not known). Sources:
- [WR] = [windows_results_20261106.md](windows_results_20261106.md);
- [XP] = [xplat_capture_plan.md](xplat_capture_plan.md);
- [R] = [REPORT.md](../REPORT.md) finding number;
- [DEPS] / [LNX] / [MAC] = the verified agent reports
  [deps_audit.md](../results/agent_reports/plan_20261106/deps_audit.md),
  [linux.md](../results/agent_reports/plan_20261106/linux.md) and
  [macos.md](../results/agent_reports/plan_20261106/macos.md).

### 4.1 Windows

| # | PyAV (DirectShow) | OpenCV (`CAP_DSHOW` / `CAP_MSMF`) | Custom C++ (MF) |
| --- | --- | --- | --- |
| 1 Raw JPEG | **Part.**: when it gets MJPEG, the header bytes equal MF's (10/10 modes, R2). But it **silently falls back to YUY2** whenever a raw mode has the same size and rate: Kiyo 720p30 in 90/90 cycles (R2), 95/120 C922 and 96/119 C930e modes (R1). PyAV cannot force the codec. The ffmpeg CLI with `-vcodec mjpeg` can (MJPEG in every mode). **m** [WR §2, §3] | **No**: DSHOW always gives BGR (`CONVERT_RGB=0` gives BGR or YUY2). MSMF's raw path gives NV12, because it picks the type by size and fps, never by subtype. **m** [R 3], [DEPS D6] | **Yes**: MJPG with a verified readback in 249/249 advertised modes (R1), 360/360 cycles (R2), 0.9–2.5% of one core. One trap: MF puts a decoded NV12 type before every MJPG type, so pick the type by subtype. **m** [WR §1–3] |
| 2 List devices without opening | **Part.**: `list_devices` maps 1:1 to camera keys, stable over 20 runs, 157 ms p50. But FFmpeg binds every capture filter to print its media types, so it touches every camera, a wedged one included. The suite had to run it under a timeout. **m** (mapping) [WR §6]; **d** (binding) [`w_id.py`](../suite/windows/tests/w_id.py) docstring | **No API in OpenCV.** The third-party `cv2_enumerate_cameras` 1.4.0 uses MF enumeration and property bags: 1:1, 2.2–3.0 ms. **m** [WR §6] | **Yes**: `MFEnumDeviceSources` and DirectShow property bags, with no `ActivateObject` or `BindToObject`. MF 2.19 ms, DS 4.81 ms, 1:1 over 20 runs. **m** [WR §6], [wincam README](../suite/windows/native/README.md) |
| 3 Device ID | **Yes**: opens by the `@device_pnp_` path, which maps to the serial-else-port key. **m** [R 22], README matrix | **Part.**: opens by **index** only. The index order matched MF/DS order over 20 runs, but no `VideoCapture(i)` was opened to confirm it, and a hot-plug between listing and open would shift indices (**i**). **m** [WR §6] | **Yes**: open by MF symlink → device instance → serial-else-port key. Only the C922 has a serial. After the C930e's driver swap and rollback its symlink and instance ID changed, but its port key did not. Persistence over reboot and replug is still untested (A1). **m** [R 22–23], [WR §6] |
| 4 Formats without opening | **No**: `-list_options` binds the filter, prints only the min and max rate per caps entry (complete on 1 of 4 cameras), and **hides 720p30 MJPEG** on the C922 and Kiyo. **m** [WR §1] | **No**: no listing API. **m** (rated by assertion in W-FMT-NOGRAB) | **Yes**: MF `ActivateObject` + `GetNativeMediaType` with no `Start`: every mode Windows can open, in 29–61 ms. It opened no pipe, disturbed no stream, and worked while another process was streaming. It does create the media source, so it is "no grab", not "no handle". Truly handle-free: the hub-IOCTL descriptor read (70–87 ms). That also lists modes Windows cannot open (C930e 2304-wide YUY2) and misses the C930e's H.264 pin. **m** [WR §1] |
| 5 Exposure | **No API.** **d** [DEPS §2.2] | **Part.**: `CAP_PROP_EXPOSURE` −7 on the C930e read back −5 in 14/15 cycles, because the camera resets at stream start. The effect on the image was not measured through OpenCV; MSMF was not tested. **m** [WR §2] | **Yes, with per-camera rules**: image luma changed ×17.7 (C922), ×9.3 (generic), ×3.6 (Kiyo). The C930e works only when set ≥ 1 s after the first frame, since it resets exposure at 14/14 starts. MF = DS. 3 runs each. **m** [WR §5] |
| 6 AE on/off | **No API.** | **?**: `CAP_PROP_AUTO_EXPOSURE` exists, but its effect was not tested. The harness's OpenCV restore step reset only the auto flag, leaving the C922 and Kiyo at exposure −7. **m** (restore) / **d?** | **Part.**: turning AE **off** is proven by the manual exposure taking effect. Turning it back **on** was checked only by flag readback (the restore compares flags, not values). **m** [WR §5] → test W-AUTO |
| 7 Focus | **No API.** | **?**: `CAP_PROP_FOCUS` exists, untested. **d?** | **Yes** on cameras with a focus motor: sharpness ×58 (C922), ×11 (Kiyo, MF JPEG); C930e holds. The generic has no focus control. **m** [WR §5] |
| 8 AF on/off | **No API.** | **?**: `CAP_PROP_AUTOFOCUS` exists, untested. **d?** | **Part.**: AF **off** proven (the focus sweep works); AF **on** only by flag readback. **m** → W-AUTO |
| 9a Uncompressed | **Yes in practice**: it delivered YUY2 (via the unwanted fallback), and YUY2 follows the requested rate (C922 6/7.5/10/15 fps). Requesting it explicitly with the dshow `pixel_format` option was not tested. **m** [WR §3] / **d?** | **Part.**: DSHOW gives BGR or YUY2 depending on property order (**m**, [R 3]). MSMF NV12 is MF-decoded from MJPEG on cameras with no native NV12 (**m** + **d**). | **Likely**: MF lists native YUY2 on all four cameras and native NV12 on the Kiyo (**m**, [WR §1]). wincam can request any subtype, but its frame checks are JPEG-only, so raw capture was never validated (**i**). → W-RAW |
| 9b QPC timestamps | **Part.**: the pts are **synthesized** (a 33.333 ms counter). The only real time is the app's own `perf_counter_ns()` on arrival, which sits on the 16 ms grid. **m** [WR §4] | **Part.**: host time after `read()` only. **m** README matrix | **Yes**: per-sample MF sample time (100 ns units, QPC timebase) plus QPC at callback entry. Both sit on the 16 ms grid (4.4–4.5 ms std against the flash ground truth). Arrival minus sample time is bimodal (~0.3–1 ms or ~16 ms), which fits one shared timebase. **m** [WR §4], [R 7], REPORT "areas of interest" |
| 9c PTS/SCR | **No**: DirectShow has no documented metadata consumer. **d** [XP §2.2] | **No.** | **Yes at tier 1 only**: `MFSampleExtension_CaptureMetadata` once `MetadataBufferSizeInKB0` is set (admin, once per device instance, then a replug; never a device restart). Present on 901/902 frames for the C922 and Kiyo. The generic sends none. Each camera's clock needs validating: C922 PTS/SCR regular (SOF 884/s, not 1000/s); Kiyo PTS ticks at 1 kHz; C930e PTS is synthetic, so use its SCR. The C930e has had the value only since 11-08, and nothing has measured it since. **m** [WR §4], [R 8–10] |

Reliability on Windows (open/close, [WR §2]):
- **MF:** 630/630 cycles on the healthy cameras over both runs.
- **PyAV DirectShow:** also 630/630 opens, but it delivered the wrong format in 90/360 R2 cycles.
- **OpenCV `CAP_DSHOW`** (skellycam's real sequence): 120/120 opens, but 2.7–11.5 s to the first configured frame,
  and `BUFFERSIZE=1` is refused on every camera.
- **OpenCV `CAP_MSMF`:** 39–41 s to open on the Logitech cameras ([R 3]).

### 4.2 Linux (no hardware run: every cell is d unless marked)

| # | PyAV (v4l2) | OpenCV (`CAP_V4L2`) | Custom V4L2 |
| --- | --- | --- | --- |
| 1 Raw JPEG | **Part.**: `input_format=mjpeg` passes the packets through. But FFmpeg 9.0.2, bundled in PyAV 19.0.2, has an **out-of-bounds read on MJPEG mmap packets**, fixed in FFmpeg master 2026-10-20 and not yet released. Error-flagged frames become zero-length packets. [DEPS D31], [LNX §4] | **Part.**: with `CONVERT_RGB=0` it returns the raw buffer as a 1×N Mat. It **ignores `V4L2_BUF_FLAG_ERROR`**, so on kernel 6.14+ corrupt JPEGs pass through unflagged. [LNX §4] | **Yes by construction**: the mmap buffer holds the camera's payload, and the error flag is visible. `S_FMT` picks the nearest size, so check what comes back. Draft only. [LNX §4] |
| 2 List devices without opening | **?**: FFmpeg's v4l2 device list opens each `/dev/video*` node to query it. **d?** | **No API.** **d?** | **Yes**: sysfs and udev, no node opened. [XP §5], [LNX] |
| 3 Device ID | **Yes**: opens by a path, e.g. `/dev/v4l/by-path/…`; the key comes from sysfs (shared code) | **Yes**: same, opens by path | **Yes**: sysfs serial if present and unique, else `ID_PATH` without the USB revision. `/dev/v4l/by-id` **collides** for identical serial-less cameras. [LNX §5] |
| 4 Formats without opening | **?**: the `list_formats` option lists formats and sizes; whether it lists frame intervals is unchecked. **d?** | **No API.** **d?** | **Yes**: the sysfs `descriptors` blob (no device handle, no USB traffic), or `VIDIOC_ENUM_FMT/FRAMESIZES/FRAMEINTERVALS` on an fd with no `S_FMT` (no USB traffic). `TRY_FMT`/`S_FMT` do send PROBE requests, so avoid them. [LNX §4] |
| 5–8 Controls | **No API.** [DEPS] | **Part.**: `CAP_PROP_EXPOSURE`, `AUTO_EXPOSURE`, `FOCUS` and `AUTOFOCUS` map to V4L2 controls, with value conventions that vary by backend. **d?** | **Yes**: `VIDIOC_S_EXT_CTRLS` with `EXPOSURE_AUTO` (1 = manual), `EXPOSURE_ABSOLUTE` (100 µs units), `FOCUS_AUTO` and `FOCUS_ABSOLUTE`. Setting exposure while AE is on returns `EACCES`, and readback can be cached, so verify on the image. [LNX §7] |
| 9a Uncompressed | **Yes**: `input_format=yuyv422`. **d?** | **Yes**: `CONVERT_RGB=0` raw buffer. [LNX §4] | **Yes**: YUYV through the same mmap path. **d** |
| 9b Host clock (QPC equivalent) | **Yes**: `-ts default` passes the kernel buffer time through. [LNX §4] | **Yes**: `CAP_PROP_POS_MSEC` is the buffer timestamp. [LNX §4] | **Yes**: `CLOCK_MONOTONIC` at the frame's first payload, quantized to URB completions (up to ~4 ms). [XP §2.6] Also record our own dequeue time and check the kernel stamp per camera: ChromeOS uses user-space time for every external USB camera because the kernel stamp "sometimes even jump[s] backwards", and Chromium dropped it in 2016 after a C930 went non-monotonic ([chromium_comparison.md](chromium_comparison.md) §3) |
| 9c PTS/SCR | **No**: FFmpeg does not read the metadata node. [DEPS] | **No.** | **Yes, tier 0**: the metadata node (`V4L2_META_FMT_UVC`, the second `/dev/videoN`, same permissions) carries PTS, SCR and a host (ns, SOF) pair per payload. Its buffer is fixed at 10 KiB before kernel 7.1, so it should overflow at ≤ 15 fps there (**i**). [LNX §3] |

### 4.3 macOS (no hardware run: every cell is d unless marked)

| # | PyAV (avfoundation) | OpenCV (`CAP_AVFOUNDATION`) | Custom ObjC++ (AVFoundation + IOKit) |
| --- | --- | --- | --- |
| 1 Raw JPEG | **No**: the demuxer emits only RAWVIDEO/DVVIDEO. [DEPS D4], [MAC] | **No.** [DEPS] | **?, gating**: Chromium asks for `'dmb1'` (`kCMVideoCodecType_JPEG_OpenDML`) and reads JPEG block buffers (**d**). One 2026 third-party run on macOS 26.4.1 saw the MJPEG modes offered only as decoded `420v` (**w**). → M-MJPEG |
| 2 List devices without opening | **?**: `list_devices` enumerates `AVCaptureDevice`s. **d?** | **No API.** | **Yes**: `AVCaptureDevice.DiscoverySession` plus IORegistry, no session started. [MAC], [XP §5] |
| 3 Device ID | **Part.**: in 9.0.2 it opens by index or name. FFmpeg master adds `serial:` / `uid:` selectors, not in PyAV 19.0.2. [DEPS D33] | **Part.**: index only. **d?** | **Yes**: `uniqueID` = hex(`locationID<<32 \| VID<<16 \| PID`), joined to the IORegistry `USB Serial Number`, else locationID. The `uniqueID` format is undocumented but held for backward compatibility per an Apple engineer (**w**). [MAC] |
| 4 Formats without opening | **No** listing option. **d?** | **No API.** | **Yes**: `AVCaptureDevice.formats` without a session. A completeness check against the descriptors needs them read from the IORegistry. [MAC MX0] |
| 5–8 Controls | **No API.** | **?**: probably nothing beyond size and fps. **d?** | **Part., OS-specific shim** (superseded by [macos_uvc_controls_review.md](macos_uvc_controls_review.md): CoreMediaIO feature controls first, the endpoint-0 route below as the fallback, and the "outside the contract" point corrected by the macOS 10.15+ SDK text): on macOS, AVFoundation offers only auto and locked exposure and focus. There is no absolute exposure duration or lens position: `setExposureModeCustom` and `setFocusModeLocked(lensPosition:)` are not available on macOS (**d**). Absolute values need UVC `SET_CUR` on endpoint 0 from user space, with no driver change. That worked idle and while streaming in one third-party run on macOS 26.4.1 (**w**). uvc-util, CameraController and Chromium send these requests through IOKit; Chromium opens the VC interface with `USBInterfaceOpen` (**d**). The suite's helper sends them **without opening the device or interface**, which is **outside Apple's documented contract**. [MAC], [DEPS §2.2] |
| 9a Uncompressed | **Part.**: delivers raw pixel formats, but maybe after macOS conversion. | **No** (BGR). | **?**: `yuvs`/`2vuy` are offered (**w**). Whether that is the camera's YUY2 or a conversion needs the committed format read over endpoint 0 (`VS_COMMIT` GET_CUR). → M-RAW |
| 9b Host clock | **?** | **?** | **Part.**: sample-buffer PTS on the session's `synchronizationClock` (**d**). Whether that is host time at arrival or derived from the camera clock is unknown. `mach_absolute_time` at the callback is always available. [MAC correction 2] |
| 9c PTS/SCR | **No.** | **No.** | **No known route** (**i**). `CMIOSampleBufferGetSequenceNumber` gives drop detection at best (**d**). → M-TS checks the sample attachments |

### 4.4 Cross-platform roll-up

| # | PyAV everywhere | OpenCV everywhere | Custom native everywhere |
| --- | --- | --- | --- |
| 1 | fails macOS; Windows needs the ffmpeg CLI, not PyAV | fails Windows and macOS | Windows **m**; Linux **d**; macOS gating |
| 2 | touches every camera on Windows | no API | all three OSes |
| 3 | yes (path) | index only on Windows and macOS | all three OSes |
| 4 | incomplete on Windows; none on macOS | no API | all three OSes |
| 5–8 | none | partial, untested | Windows **m**; Linux **d**; macOS needs the IOKit shim |
| 9a | yes | partial | Windows to verify; Linux **d**; macOS unknown |
| 9b | synthesized on Windows | host time only on Windows | all three OSes |
| 9c | none | none | Windows tier 1; Linux tier 0; macOS none |

## 5. Combinations considered

| Combination | What it buys | What it costs | Verdict |
| --- | --- | --- | --- |
| **C1. Custom native everywhere** (C++ MF / C++ V4L2 / ObjC++ AVFoundation + IOKit), Python bindings via nanobind or pybind11 (build time only) | Every requirement reachable on Windows (measured) and Linux (documented). One API, one watchdog and timeout design (wincam's bounded calls), one timestamp-fit and drop-detection module, no per-frame Python on the capture thread. | Most new code: about 6–9 kLOC for the deps audit's A, which used ctypes and PyObjC on Linux and macOS. C++/ObjC++ there is a similar size (**i**). Plus wheel builds for win_amd64/arm64, macOS arm64/x86_64 and manylinux. | **Recommended** |
| C2. PyAV for frames (Windows dshow, Linux v4l2) + native side channels for listing, controls and PTS | Less frame-loop code on Windows and Linux | Windows: silent YUY2 fallback (**m**), synthesized pts, and MF still needed for PTS/SCR. Linux: the 9.0.2 MJPEG out-of-bounds read, no metadata node. macOS: nothing usable. PyAV has one dominant maintainer and dropped Python 3.11, which skellycam still declares (3.11 resolves to PyAV 18.x). FFmpeg's dshow code has had no commit since 2024-10-17. Saves only ~1.5–2.5 kLOC against C1 [DEPS §3] | Rejected |
| C3. OpenCV for frames + side channels | Nothing for requirement 1 on Windows or macOS | Fails requirement 1 on two of three OSes (**m** / **d**); no listing; 2.7–11.5 s configured opens on Windows (**m**) | Rejected for capture. Keep OpenCV for decode and display |
| C4. Custom on Windows and macOS, PyAV or OpenCV frames on Linux | Skips a V4L2 mmap loop (~300–500 LOC, **i**) | Linux still needs custom code for the metadata node, identity and (for PyAV) controls. The OpenCV route hides corrupt frames on 6.14+. Two frame paths to maintain | Fallback only if L-MJPEG shows custom V4L2 failing where a wrapper passes |
| C5. Windows fallback: ffmpeg CLI DirectShow (`-vcodec mjpeg`) per camera when MF fails | A second stack, as Chromium does (MF with DS fallback). Measured MJPEG in every mode where PyAV fell back | A subprocess, ambiguous EIO for bandwidth refusals (needs the FFmpeg log), and the generic camera re-enumerates ~10 s after every DS refusal (**m**, [WR §7]). MF never failed where DS passed (**m**) | Optional. Build only if CORE-W-CYC shows an MF-only failure |

**OS-specific shims in C1 (called out as the brief asks):**

| OS | Shim | Why it is needed | Cost / risk |
| --- | --- | --- | --- |
| Windows | `MetadataBufferSizeInKB0` registry value per camera device instance (tier 1) | the only route to PTS/SCR without a driver change (**m**) | Admin plus a replug; must be re-applied when a serial-less camera gets a new instance (moves port); never restart the device (LogiTune veto → `MF_E_REBOOT_REQUIRED`, **m**) |
| Windows | Hub IOCTL descriptor reader (no admin) | descriptor-level mode data and the mode-alt cache for the topology mapper (**m**) | already in `bandwidth/win_usb_topology.py` and the suite |
| macOS | CoreMediaIO feature controls (public API, through Apple's UVC driver), with unopened IOKit endpoint-0 UVC `GET_*`/`SET_CUR` as the fallback; both via ctypes | AVFoundation has no absolute exposure or focus on macOS (**d**) | CMIO coverage on our cameras is unknown: one BRIO and one LifeCam report, the LifeCam only through undocumented control classes (**w**). Since the macOS 10.15 SDK, `IOUSBLib.h` says an unopened device may take class requests (**d**, per the review). Chromium dropped its endpoint-0 workaround in 2023 as "suspected to be breaking some external cameras" (**d**). Endpoint-0 writes may leave CMIO/AVFoundation values stale (**w**). The "Kiyo greyed out on M4" report is the original Kiyo, not the Pro (**w**) |
| macOS | TCC camera permission tied to the launching app | without it a process gets zero frames and no error (**d**) | packaging |
| Linux | `video` group for headless or SSH use (tier 1) | desktop sessions get `uaccess`; SSH does not (**d**) | one-time admin |

Identity keys, the topology mapper and bandwidth messages stay in Python (`suite/common/identity.py`,
`topology_model.py`), fed by each backend's link/path. They are OS-neutral and already measured on Windows.

## 6. Test plan

Every claim in §4 that is not **m** has a test here. Existing suite tests are named by their IDs
([XP §6.2](xplat_capture_plan.md)); new tests are marked **new**. Every test runs with all cameras attached as
found, the Kiyo included, with per-call timeouts and camera-lock wrapping on Windows. Pass thresholds are the ones
in [XP §3](xplat_capture_plan.md) unless stated.

### 6.1 Windows, unattended on Gerald

| ID | Claim it checks | What it does | Pass |
| --- | --- | --- | --- |
| **W-RAW** (new) | 9a: MF delivers the camera's own YUY2 and NV12 | Extend wincam frame checks to raw subtypes: buffer length = stride × height, readback subtype equals request, rate follows request (C922 YUY2 is known to), and refuse any NV12 type flagged `likely_mf_synthesized`. Cameras: all 4 YUY2 modes; Kiyo native NV12 too. Compare against PyAV with dshow `pixel_format=yuyv422` (**d?**) and OpenCV `CAP_DSHOW`/`CAP_MSMF` with `CONVERT_RGB=0`. **Needs a mode-scope exception:** high-speed USB cameras offer YUY2 at 720p only below 30 fps, so test each camera's largest YUY2 mode at ≥ 30 fps plus 720p at its maximum rate (Dom to approve). Include one W-MULTI pair in YUY2, since raw modes reserve more bandwidth | MF: 100% frames with correct length and subtype; rate within 2% of the request where the camera honours it; header-free raw bytes equal across MF and PyAV for the same mode |
| **W-AUTO** (new; extends W-CTRL-EFFECT) | 6, 8: AE and AF can be turned back **on**, verified on the image | For each camera × MF/DS: (a) record the auto baseline (luma, sharpness); (b) set manual exposure to an extreme, then auto → luma must return within 3 s to ±15% of baseline; (c) AF off, focus at 0 (defocus), then AF on → sharpness must recover to ≥ 80% of the AF baseline within 5 s on a textured target; (d) toggle 3× per run, 3 runs; (e) the C930e also after stream start | All four transitions verified on the image, 3/3 runs, per camera with that control |
| **W-OCV-CTRL** (new) | 5–8 OpenCV column | OpenCV `CAP_DSHOW` and `CAP_MSMF`: `CAP_PROP_AUTO_EXPOSURE`, `EXPOSURE`, `AUTOFOCUS`, `FOCUS`, set → readback → image metric (`suite/common/imgmetrics.py`), before and after the first frame | Same as W-CTRL-EFFECT; fills the "?" cells |
| **W-PYAV-LIST** (new; extends W-ID and W-FMT-NOGRAB) | 2: PyAV `list_devices` touches every camera | Run `list_devices` (PyAV and ffmpeg CLI) while (a) all cameras are idle, (b) one camera streams through MF in another process, (c) the Kiyo is wedged (opportunistic). Record frame gaps in the streaming process, the pipe state, the call duration and hangs | Rating, not pass/fail: "touches but harmless", or "disturbs / hangs on a faulted camera" |
| **W-TS re-run** (existing) | 9c: tier-1 PTS/SCR on the C930e and Kiyo now that all four instances have the value (2026-11-08); the generic sends none | Re-run W-TS. Save the generic's empty-metadata result to `results/`: the 11-08 check lives only in a scratchpad | Fields present per camera; clock units, step regularity and SOF rate validated per camera ([WR §4] rule) |
| **W-CYC-381** (existing W-CYC, more cycles) | "reliably" | ≥ 381 cycles per camera per API (MF in-process and new-process), Kiyo within its healthy window. Fix the `fps_measured` harness bug first ([WR §11]) | ≥ 99% per camera at the Wilson lower bound |
| **W-MJPEG Kiyo** (existing) | 1 for the Kiyo, including 60 fps modes | Run W-MJPEG on the Kiyo alone within 2 h of a replug | XP §3 G-MJPEG "yes" |

### 6.2 Windows, attended

| ID | Claim | Note |
| --- | --- | --- |
| A1 (existing) | 3: keys persist over reboot, same-port replug and port move | `naming/win_stability_workflow.ps1`; needs Dom |
| A5 (existing; [timing/rig/README.md](../timing/rig/README.md)) | 9b/9c accuracy, not just extraction: where QPC, MF sample time and PTS sit relative to exposure | needs the AtomS3 strobe rig flashed; only synthetic self-tests so far |

### 6.3 macOS (order: M-MJPEG first)

| ID | Claim | What it does | Pass |
| --- | --- | --- | --- |
| **M-MJPEG** (existing, gating) | 1: AVFoundation delivers the camera's own JPEG via `'dmb1'` | Every advertised MJPEG mode × `videoSettings` = nil, `{}` and `'dmb1'`; record block buffer vs pixel buffer, SOI/EOI, strict decode, and `VS_COMMIT` GET_CUR over endpoint 0 through IOKit (no claim, no libusb) to prove the wire format; header SHA-1 vs Windows MF for the same camera and mode | XP §3 G-MJPEG. **If no camera passes, requirement 1 is unattainable on macOS without a driver change, whichever option is chosen** |
| M-FMT-NOGRAB (existing) | 4 | `AVCaptureDevice.formats` with no session vs descriptors from the IORegistry | complete for every mode AVFoundation can open |
| M-ID (existing) | 2, 3 | discovery session + IORegistry, `uniqueID` ↔ locationID ↔ serial, 20 repeats; attended reboot/replug/port move | XP §3 G-ID |
| M-CTRL-LIST / M-CTRL-EFFECT (existing, `--ep0`) | 5–8 via the IOKit shim; AVFoundation lock modes | exposure ×3, gain, WB, focus ×3 with AF off, AE and AF toggles verified on the image (add the W-AUTO steps); record IOKit return codes; before and after `startRunning()` | XP §3 G-CTRL |
| **M-RAW** (new) | 9a: `yuvs`/`2vuy` are camera-native | capture each raw mode; read `VS_COMMIT` (bFormatIndex) over endpoint 0 during streaming; compare the format the camera sends with the pixel format delivered | wire format is YUY2 and the bytes are the same length as the frame |
| M-TS (existing) | 9b, 9c | log `synchronizationClock` vs `CMClockGetHostTimeClock()`, port clock rate vs host, grid, CMIO sequence gaps; dump every sample attachment looking for UVC header data | documents the clock origin; 9c expected "no" |
| **M-WRAP** (new) | PyAV/OpenCV columns of §4.3 | PyAV avfoundation `list_devices`, open by index/name, delivered pixel format; OpenCV `CAP_AVFOUNDATION` control properties honoured or not | fills the "?" cells |
| M-CYC (existing) | reliability | as W-CYC, ≥ 381 cycles for a 99% claim | XP §3 |

Run on M1 (Apple silicon, macOS 27) first, then M2–M4 as in [XP §2.5](xplat_capture_plan.md). The Kiyo goes on two
Apple silicon generations if possible.

### 6.4 Linux (L3 Fedora 45, then L2 Ubuntu 26.04, then L1 Ubuntu 24.04 GA; Gerald from an external SSD)

| ID | Claim | What it does | Pass |
| --- | --- | --- | --- |
| L-MJPEG (existing; includes PyAV and OpenCV legs) | 1 per option | raw mmap vs PyAV `input_format=mjpeg` vs OpenCV `CONVERT_RGB=0`; header SHA-1 vs Windows MF; count error-flagged frames each one surfaces; run PyAV under ASan or valgrind once for the 9.0.2 out-of-bounds read | XP §3 G-MJPEG; the wrapper legs decide C4 |
| L-FMT-NOGRAB (existing) + **PyAV `list_formats` leg** (new) | 4 | sysfs descriptors, `ENUM_*` with no `S_FMT`, `v4l2-ctl`, PipeWire; add PyAV `list_formats` and check whether it gives frame intervals | complete vs descriptors, no PROBE sent |
| L-ID (existing) + **PyAV device-list leg** (new) | 2, 3 | sysfs/udev listing with no open; does FFmpeg's v4l2 device list open each node? (`fuser`/strace) | 1:1 keys, 20 repeats |
| **L-RAW** (new) | 9a | YUYV via mmap, PyAV `input_format=yuyv422` and OpenCV raw; length and rate checks as W-RAW, same scope exception | as W-RAW |
| L-CTRL-EFFECT (existing) + W-AUTO steps + **OpenCV leg** (new) | 5–8 | `S_EXT_CTRLS` incl. the `EACCES` ordering case; verify on the image, not readback; OpenCV `CAP_PROP_*` leg | XP §3 G-CTRL |
| L-TS (existing) | 9b, 9c | buffer time vs metadata node PTS/SCR; overflow at ≤ 15 fps on kernels before 7.1 (L1, L2) vs 7.2 (L3) | fields present; sequence pairing works; overflow behaviour documented |
| L-CYC, L-MULTI, L-DESK (existing) | reliability, contention, PipeWire interference | as specified | XP §3 |

### 6.5 The production module itself

wincam.exe is a probe, not the module skellycam would ship. Once C1's module exists:

| ID | What it does | Pass |
| --- | --- | --- |
| **CORE-W/L/M** (new) | Re-run W-/L-/M-CYC, -MJPEG, -CTRL-EFFECT, -TS and -MULTI through the module's Python API instead of the probes | Results match the probe results within run-to-run noise; no new failure class |
| **CORE-PKG** (new, no camera) | Install wheels on Python 3.11–3.14 for win_amd64, win_arm64, macOS arm64 (14+, and 12/13 if supported), manylinux x86_64/aarch64; import and enumerate | All targets install and enumerate |

### 6.6 Order of work

1. **Windows unattended** (no new hardware): W-RAW, W-AUTO, W-OCV-CTRL, W-PYAV-LIST, W-TS re-run, Kiyo W-MJPEG,
   then W-CYC-381 overnight. Fixes the remaining "?" and "Part." cells in §4.1.
2. **macOS M-MJPEG** on one Apple silicon Mac. Decides whether requirement 1 can be met on macOS at all.
3. **Linux L3**, then L2 and L1. Decides C1 vs C4 on Linux.
4. Rest of macOS (CTRL with the IOKit shim, RAW, TS, WRAP).
5. A1 and A5 (attended; A5 needs the rig).
6. Build the C1 module behind the same API, then CORE-*.

## 7. What would change the recommendation

| Result | Effect |
| --- | --- |
| M-MJPEG fails on every camera | Requirement 1 is out of reach on macOS for every option. C1 still wins on macOS for 2–4 and the controls; macOS capture becomes decoded pixels, re-encoded if skellycam needs JPEG files |
| L-MJPEG: a wrapper is byte-exact and surfaces error frames, and custom V4L2 shows a failure | Consider C4 for Linux frames only; the metadata node, identity and controls stay custom |
| The IOKit endpoint-0 shim fails on a macOS version (M-CTRL) | Exposure and focus on macOS shrink to auto/locked (AVFoundation); requirements 5 and 7 become "Part." there |
| W-CYC-381 or CORE-W-CYC shows MF-only failures | Build C5 (ffmpeg CLI DirectShow fallback) |
| Dom rules out tier 1 for users | 9c on Windows drops to "No"; the tier-0 frame-index fit (unscored until A5) is all that remains |

## 8. Decisions (Dom, 2026-11-08)

- **Mode scope:** streaming tests use only 720-line modes at ≥ 30 fps, with no exception for raw formats. A camera
  with no raw mode in that scope is reported "untested (no raw mode in scope)". The runner's `--max-height` flag
  (default 720) widens it again.
- **Build language: native Python where possible.** C1 becomes Python calling the OS APIs directly: ctypes or
  comtypes for Media Foundation on Windows, ctypes for V4L2, PyObjC plus ctypes IOKit on macOS. There is no
  compiled extension. C++ is used only for a piece a native-Python version cannot match. The new test W-PYMF
  compares a pure-Python MF probe with the C++ wincam probe to decide this for Windows.
- ~~**The admin step is optional.**~~ Superseded 2026-11-09: **testing is tier 0 only.** No registry changes and no
  UVC PTS/SCR testing. Device timestamps are judged unreliable from others' work (see
  [chromium_comparison.md](chromium_comparison.md) §5), and Dom does not want them re-tested. Requirement 9c is out
  of scope. The `MetadataBufferSizeInKB0` value set on 2026-11-08 is left in place, because removing it would be
  another registry change, and every test ignores it. The W-TS tier-1 re-run in §6.1 is cancelled.
  *(2026-11-11: the value was in fact removed on 2026-11-09, at Dom's request, so tier-0 runs see the machine as
  found ([metadata_revert_20261109/README.md](../results/windows/Gerald/metadata_revert_20261109/README.md)). The
  11-10/11 run's W-ENV finds it on none of the current camera instances.)*
- macOS controls: the IOKit route is under review in [macos_uvc_controls_review.md](macos_uvc_controls_review.md).

## 9. Windows results, 2026-11-10/11

Added 2026-11-11. One full unattended run on Gerald, tier 0, streaming at exactly 720 lines and ≥ 30 fps. Details,
per camera and with evidence links: [windows_results_20261110.md](windows_results_20261110.md) ([WR2] below). All
"m".

**By requirement (Windows):**

| # | What the run showed | [WR2] |
| --- | --- | --- |
| 1 Raw JPEG | MF: camera MJPEG with equal header SHA-1 on all 4 cameras. PyAV: still YUY2 on the Kiyo (0 JPEG frames); the ffmpeg CLI gets MJPEG there. First Kiyo MJPEG rating: its 720p60 delivers 30.3 fps. The C922 delivered 59.4 fps at 720p60 | §2 |
| 2 List devices | 6 APIs map 1:1 to keys over 20 runs. PyAV/ffmpeg `list_devices` "touches but harmless", but took 8.4–9.3 s with the wedged Kiyo attached (134–172 ms when healthy) | §1 |
| 3 Device ID | G-ID partial (provisional): reboot persistence of port keys still unmeasured (A1) | §1 |
| 4 Formats, no open | MF activate without `Start`, DS and the hub IOCTL: complete on all 4. `ffmpeg -list_options`: complete on 1 of 4. OpenCV, WinRT: no | §1 |
| 5–8 Controls | MF = DS. Effect in the image: Kiyo and C922 yes; C930e partial (resets exposure at stream start); generic partial (gain and WB have no visible effect). AE and AF back on: verified on the image wherever the test was conclusive, 0 failed transitions (W-AUTO) | §6 |
| 9a Uncompressed | Only the Kiyo has a raw mode in scope: MF, PyAV and the ffmpeg CLI deliver NV12 and YUY2 at the right length; 720p60 runs at 30 fps. OpenCV DSHOW returns BGR | §2 |
| 9b Host clock | MF sample time on the 16 ms grid ("no"); PyAV pts synthesized ("no"); ffmpeg CLI pts and the frame-index fits untested until A5 | §7 |
| Reliability | MF in-process 400/400 and ffmpeg-DS in-process 400/400 on each camera (Wilson lower bound 0.9905, meets the ≥ 381-cycle bar). MF new process 100/100 (0.963). OpenCV 0/180 cycles within 2 s | §3 |

**By option:**
- **Custom MF:** best on every measured axis, as before.
- **pymf (pure-Python MF), new in this run:** equivalent to the C++ probe on the Kiyo, C930e and C922 (formats,
  controls, header bytes, fps, latency, 60/60 cycles). CPU 2.8–4.4 % vs 1.9–2.8 % of one core. The generic's
  cycles are untested after the camera fell off the bus during both tools' cycles. This supports §8 "native Python
  where possible" on Windows.
- **PyAV:** rejected for capture, unchanged (silent YUY2 fallback on the Kiyo in W-MJPEG, W-CYC and W-TS).
- **OpenCV:** rejected for capture, now on measured latency, raw output and control behaviour as well as JPEG.
- **ffmpeg CLI DirectShow (C5):** 400/400 cycles per camera, but both Kiyo wedges in a DS route began on an ffmpeg
  CLI open in W-MULTI.

**§7 conditions:**
- "W-CYC-381 or CORE-W-CYC shows MF-only failures → build C5": **not triggered.** 0 MF failures in 1,600 in-process
  and 400 new-process cycles. The only MF failures in the run (W-PYMF, generic camera) hit wincam and pymf alike
  while the camera dropped off the bus; no DS route ran then (i).
- "Dom rules out tier 1": decided on 11-09 (§8). 9c stays out of scope; G-TS rests on the frame-index fit, untested
  until A5.
- The macOS and Linux rows were not tested (no hardware run).

**Kiyo:** wedged at about 4–5 min (11-10 17:04, MF open of the Kiyo alone) and at 525.2 min (11-11 01:52, DS
all-at-once round in W-MULTI) after plug-in. This rules out the "about 210–224 min" theory. A multi-camera
DirectShow open fits 2 of the 4 recorded onsets (i) ([WR2] §9).

**Next:** W-MULTI repeated on its own (DS all-at-once vs MF all-at-once); `--only W-PYMF` for the generic camera;
the A5 strobe rig ([WR2] §14).
