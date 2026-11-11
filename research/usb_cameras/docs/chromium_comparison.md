# How our capture plan compares with Chromium's, and Chromium's known issues

2026-11-09 · Dom · status: **web research, nothing run.** Three research agents each read Chromium's current source
for one OS (pinned commits below) plus its commit history. Six adversarial checkers, two per OS, then tried to
refute every Chromium claim in this doc against the same source. Their 60 corrections are applied here. Many old
Chromium bugs are restricted, so bug evidence comes mostly from commit messages, code comments and the public JSON
titles and statuses on issues.chromium.org.

Our side is [capture_stack_options_plan.md](capture_stack_options_plan.md) (with the 11-08 decisions in its §8) and,
for macOS controls, [macos_uvc_controls_review.md](macos_uvc_controls_review.md).

Labels:
- **doc**: Chromium source or commit text read at the pinned commit;
- **web**: forum, blog or third-party issue text;
- **inferred**: reasoning from the code;
- **m**: measured on Gerald (our results).

Pinned source:
- Windows and Linux: chromium/chromium [`02af13ef00a3`](https://github.com/chromium/chromium/tree/02af13ef00a3c2152b03b5d01b61c6b335437e9a)
  (main, 2026-11-08).
- macOS: [`ff2945386c2c`](https://chromium.googlesource.com/chromium/src/+/ff2945386c2c5902010b7eb0e03caacba353d617)
  (main, 2026-11-08).
- ChromeOS camera HAL: chromiumos/platform2 `camera/hal/usb/` at main (2026-11-09).

Commit links have the form `github.com/chromium/chromium/commit/<sha>`.

## 1. Short answer

**Chromium solves a different problem.** It shows one camera in a video call: it decodes every frame for display,
cares about power and privacy, and can afford to lose a frame. We record several cameras for motion capture: we keep
the camera's own JPEG bytes, need exact frame accounting and stable camera identities, and have to handle USB
bandwidth contention. So Chromium is a good source of **reliability workarounds**, but its data path,
identities and control handling don't fit our goals.

| Requirement | Chromium, Windows | Chromium, Linux | Chromium, macOS | Ours |
| --- | --- | --- | --- | --- |
| 1 Raw JPEG | **No.** The MF capture engine always decodes; DirectShow MJPEG is decoded with libyuv on the CPU | **No.** libyuv decode in-process | **No.** Asks for `'dmb1'` only when an MJPEG mode wins format selection (MJPEG ranks last), then decodes it: to NV12 by default, or to I420 when GPU buffers are switched off. Raw JPEG never leaves the capture service | Pass the camera's bytes through on every OS |
| 2 List devices without opening | **No** by default: creates the media source and a source reader for every camera. A devices-only mode landed in 2026-10, off by default, with browser wiring left to follow-up changes | **No**: opens every `/dev/video*`, plus a test open | Lists without starting a session, but calls `USBInterfaceOpen` on the VideoControl interface of the first IOKit device matching each camera's VID:PID (expected to fail on macOS 12+) | No device opened on any OS |
| 3 Device ID | MF symbolic link; model = VID:PID | `/dev/videoN` (changes when the kernel renumbers nodes); model = VID:PID | `uniqueID`. Chromium uses only its last 8 hex digits (VID+PID); that the rest is the USB locationID is Apple behaviour. Control lookup is by **VID:PID only** | USB serial if unique, else physical port |
| 4 Formats without opening | Activate + `GetNativeMediaType`, no start (**same as ours**) | ioctls on an open fd | `device.formats`, max fps only | Same methods on Windows and macOS; sysfs or ioctls on Linux |
| 5–8 Exposure, AE, focus, AF | `IAMCameraControl` from the MF source (**same interfaces as ours**). Only while streaming; a write is never verified by reading it back | `VIDIOC_S_CTRL` one control at a time, mode before value; a best-effort reset of controls to defaults on every open | Exposure, focus and WB **off by default**. Every UVC control needs `USBInterfaceOpen`, which Chromium's own 2023 commits say fails on macOS 12+ | Windows as Chromium, plus readback and image check; Linux keeps settings; macOS CMIO first, then unopened endpoint 0 |
| 9a Uncompressed | Converted to I420/NV12 | **Preferred** at ≤ 640×480 | Converted to NV12 | Raw bytes, in scope only |
| 9b Timestamps | `TimeTicks::Now()` on arrival (reference) + MF sample time (frame timestamp) | `TimeTicks::Now()` after DQBUF (ignores the kernel stamp) | `TimeTicks::Now()` (reference) + PTS minus the first PTS (frame timestamp) | Device or OS stamp plus host arrival, both kept |
| 9c UVC PTS/SCR | None | None | None (AVFoundation PTS only) | Windows tier 1 (optional), Linux metadata node |
| Bandwidth contention | Not handled | Generic STREAMON error; ENOSPC not identified | Not handled | Classified, mapped and explained to the user |
| Frame accounting | Frames overwritten in the single handoff slot are not counted; other drops are reported with a reason | Drops reported with a reason | Late frames discarded | Every frame counted |

**Where Chromium validates our choices:**
- Getting `IAMCameraControl`/`IAMVideoProcAmp` from the MF source.
- Listing formats with no stream started.
- Treating a camera as started only when its first frame (or first frame drop) arrives.
- Keeping a per-model fallback table.

**Where Chromium is a warning:**
- Forwarding an OS or driver capture time as an absolute capture time was switched off on Windows and on macOS in 2024.
- ChromeOS uses user-space time for every external USB camera, because the kernel stamp "is not reliable and sometimes even jump backwards".
- Its macOS UVC-control workaround was reverted as "suspected to be breaking some external cameras".

## 2. Windows

**How it works** (all **doc**; files in `media/capture/video/win/` unless noted):
- **Backend.** `kMediaFoundationVideoCapture` has been on by default since 2019 ([c4f58b3](https://github.com/chromium/chromium/commit/c4f58b3898a92a0f7001f45415acf215b6481c65)).
  - **22** VID:PIDs are skipped by MF and land on DirectShow, which lists every device MF did not (`video_capture_device_factory_win.cc` L125-167, L1187-1254).
  - Two more VID:PIDs only lose the D3D11 path (L170-174).
  - An MF device with zero formats is replaced by its DirectShow twin, matched by **name + model**.
- **Capture.** `IMFCaptureEngine` with a preview sink whose type is always I420 (CPU) or NV12 (D3D11). The code says the engine "inevitably performs the video frame decoding itself" (`video_capture_device_mf_win.cc` L409-460).
- **Formats** (`capability_list_win.cc` L20-123):
  - Chosen by nearest height, then width, then fps.
  - The native subtype is only a tie-breaker: no conversion first, then I420↔NV12, then YUY2↔NV12.
  - MJPEG ranks last in the final pixel-format preference, so it is never preferred.
  - If NV12 is requested, an NV12 mode wins before size is compared.
- **"Fake NV12."** NV12 with nominal range 0–255 ("usually just an unpacked MJPG") is flagged. It loses to a real NV12 of the same size and fps, and to other subtypes only when NV12 is requested. With an I420 request it still beats YUY2 and MJPEG. This is the same MF trap we found (MF inserts a decoded NV12 before each MJPG type, **m**).
- **Timestamps.**
  - Reference time = `TimeTicks::Now()` in `OnSample`; frame timestamp = the MF sample time.
  - Forwarding `MFSampleExtension_DeviceReferenceSystemTime` as capture time was on by default from 2024-03-28 ([fd093cf](https://github.com/chromium/chromium/commit/fd093cf74999)) and switched off on 2024-08-29 ([800c81c](https://github.com/chromium/chromium/commit/800c81c3cab2)). The reason is not public (b/336472295).
  - That attribute is a host-clock (QPC) stamp from the driver, not the camera's clock.
  - Both reads in the code use the same attribute key, although the commit message speaks of two attributes (probable bug, **inferred**).
  - There is no UVC metadata, PTS or SCR use.
- **Controls.** `source_.As(&camera_control_)`, the same route as ours.
  - Applied only while streaming: `SetPhotoOptions` and `GetPhotoState` return early when not started.
  - A write is never verified by reading it back. Current values are read only in `GetPhotoState`, and by the control monitor to ignore Chromium's own writes.
  - Manual exposure is converted with a truncating `log2`, so 1/30 s becomes 1/16 s (**inferred** from the code).
  - "exposureCompensation" is mapped to Gain.
  - `IMFCameraControlMonitor` (Win11 22H2+) detects control writes by other apps.
- **Lifecycle.**
  - It waits for `MF_CAPTURE_ENGINE_INITIALIZED`, because calling methods earlier "can cause unstable behavior" ([1165c60](https://github.com/chromium/chromium/commit/1165c605487c)).
  - It reports "started" only on the first frame or the first frame-drop report, because "camera in use" errors arrive after preview-started.
  - It retries `MF_E_INVALIDREQUEST` 200 × 50 ms.
  - On `MF_E_HW_MFT_FAILED_START_STREAMING` it checks `IMFSensorActivityMonitor` for "in use by another app".
  - Event waits use **`INFINITE`**.
  - Engine destruction is deferred by 5 s (DLL unload cost).
  - The callback-to-owner link is cut on destruction (crash fix, [2eec73a](https://github.com/chromium/chromium/commit/2eec73ab6f29)).
- **Frame handoff.** A single slot; a new frame overwrites an undelivered one without a drop report. Other drops (null sample or buffer, lock failure, conversion failure) are reported through `OnFrameDropped` with a reason.
- **Hot-plug.** `RegisterDeviceNotification` on KSCATEGORY_VIDEO (`media/device_monitors/system_message_window_win.cc`). Enumeration "can take up to 5s when a USB camera is just connected", so it was moved off the frame thread ([b43405d](https://github.com/chromium/chromium/commit/b43405d55068), 2026-08).

**Known issues** (commit evidence; dates are commit dates):

| Date | Issue | What Chromium did |
| --- | --- | --- |
| 2018–2025 | Capture cards (Empia, Elgato HD60/Cam Link 4K, Hauppauge, Sensoray), several laptop cameras (Dell, Lenovo, HP, Acer, Toshiba) and Windows Hello RGB/IR fail under MF | VID:PID → DirectShow |
| 2018 | Capture cards list no formats in MF | Use the DS twin |
| 2020 | VMware virtual webcam hangs `getUserMedia` under MF | Name blocklist |
| 2020 | Calls before `INITIALIZED` unstable; callback outlived owner (crash) | Wait for INITIALIZED; shut down the callback |
| 2020–2023 | D3D11 capture reverted, then relanded; zero-copy fails with `MF_E_SAMPLEALLOCATOR_EMPTY` if the client holds > 10 buffers | Smaller pool, D3D11 blocklist |
| 2024 | Driver capture time forwarded, then switched off (reason not public) | Back to `Now()` as reference |
| 2024 | eBUS DirectShow source crashes enumeration | Name blocklist |
| **2026-07** | **Microsoft LifeCam Studio fails at 720p under MF; 360p works** ([8ee51ae](https://github.com/chromium/chromium/commit/8ee51aeab33e)) | Whole VID:PID → DirectShow |
| 2026-08 | Enumeration takes ~5 s after a USB camera is plugged in | Moved off the frame thread |
| 2026-10 | Enumeration activates every camera just to list them (bug 565332594; motivation not public) | Devices-only mode behind `kWinDeviceEnumerationWithoutActivation`, off by default ([4ebcfb5](https://github.com/chromium/chromium/commit/4ebcfb5643fb)) |

None of these involves the C922, C930e, generic or Kiyo Pro (no Logitech 046d or Razer 1532 entry). There is no USB
bandwidth handling, sleep/resume code or multi-camera coordination.

**Copy into our Windows backend:**
1. Count a camera as admitted only on its first frame (already in our design).
2. Retry `MF_E_INVALIDREQUEST`, but bounded to about 1 s, not 10 s.
3. `IMFSensorActivityMonitor` on `MF_E_HW_MFT_FAILED_START_STREAMING`, to tell "in use" from other start failures. pymf does not do this yet.
4. `IMFCameraControlMonitor` to flag another app changing exposure mid-recording.
5. A data-driven backend table. Chromium keys it by model only. The LifeCam case shows an MF failure can depend on the **mode**, so key ours by (VID:PID, mode). That goes beyond Chromium.
6. Fall back to DirectShow when MF lists zero formats.
7. Run enumeration on its own thread, and expect ~5 s after hot-plug.
8. Cut the callback-to-owner link on close, so a late callback can't touch freed state.

**Don't copy:** the capture engine (it decodes), `INFINITE` waits, the 10 s retry, the truncating exposure
conversion, Gain as "exposure compensation", name+model device matching, and the uncounted single-slot handoff.

## 3. Linux

**How it works** (all **doc**; files in `media/capture/video/linux/` unless noted):
- **Backends.** V4L2 by default. A PipeWire / camera-portal backend via WebRTC exists but is **off by default** (`kWebRtcPipeWireCamera`). When it is on, Chromium falls back to V4L2 if the portal is denied or missing, or lists no cameras ([4a185d9cbe](https://github.com/chromium/chromium/commit/4a185d9cbe), 2026-11-04).
- **Enumeration.** Globs `/dev/video*` and **opens every node**. A node is kept if QUERYCAP's device-wide `capabilities` or its `device_caps` show capture without output, and a capture `ENUM_FMT` finds a usable format. uvcvideo metadata nodes pass the capability test, because the device-wide field has VIDEO_CAPTURE set; they are dropped only because the capture `ENUM_FMT` finds nothing (**inferred**). The list is sorted lexicographically, so `/dev/video10` comes before `/dev/video2` (**inferred**).
- **Identity.** `device_id` = `/dev/videoN`; model = VID:PID from sysfs. No serial, no `ID_PATH`.
- **Formats and frame rate.**
  - Preference order: I420, NV12, Y16/Z16/INVZ, **YUYV, RGB24, then MJPEG** (JPEG last). MJPEG moves first only when the requested width is above 640 or the height above 480.
  - Frame rate is set with `S_PARM`, and the returned rate is **not checked** (TODO in the code); the requested rate is reported as the actual rate.
- **Frames.**
  - 4 mmap buffers.
  - `V4L2_BUF_FLAG_ERROR` frames are dropped (since 2016-11) and reported with a drop reason (since 2018-08).
  - The short-frame check does nothing for MJPEG, because its expected size is 0, so a truncated JPEG without the flag reaches the decoder (**inferred**).
  - MJPEG is decoded in-process with libyuv; hardware JPEG decode exists on ChromeOS only.
- **Timestamps.** `TimeTicks::Now()` after DQBUF. From 2016-05 to 2016-11 Chromium used the V4L2 kernel buffer timestamp (a host-clock stamp from the driver, not the camera's PTS). It reverted after a **Logitech C930 produced non-monotonic stamps** that froze video ([6b8877a5ac](https://github.com/chromium/chromium/commit/6b8877a5ac)). No metadata node use.
- **ChromeOS camera HAL** (`chromiumos/platform2 camera/hal/usb/`) agrees for external cameras.
  - `camera_hal.cc` sets `kQuirkUserSpaceTimestamp` for **every external, non-detachable USB camera**, with the comment that "the hardware timestamp is not reliable and sometimes even jump backwards".
  - The kernel stamp is used only for built-in and detachable modules.
  - An 8-entry VID:PID list and one board rule switch those to user-space time as well.
  - (One checker reported only the 8-entry list; the other found the external-camera rule in `camera_hal.cc`. Treat the external-camera rule as checked once.)
- **Controls.**
  - `VIDIOC_S_CTRL` one control at a time, mode before value.
  - Before writing a value it reads the mode and **silently skips** the value if the mode is auto. Errors are only logged, and success is always reported.
  - "Continuous" exposure maps to `APERTURE_PRIORITY`.
  - It subscribes to `V4L2_EVENT_CTRL` to catch other apps' changes.
- **Reset on open.** On every open it **tries to reset user and camera controls to their defaults** with batched `S_EXT_CTRLS` (a 2016 fix for zoom persisting between sessions). It is best effort:
  - it is skipped entirely if the camera rejects the auto-white-balance write;
  - it misses brightness;
  - it skips relative and speed PTZ controls;
  - a whole batch fails if any one control in it is unsupported.
- **Timeouts.** `poll()` 1 s. On the first timeout it restarts the stream once (STREAMOFF, REQBUFS 0, REQBUFS, STREAMON), a Huddly GO workaround; ten timeouts in a row is an error.
  - DQBUF and QBUF errors are fatal.
  - STREAMON failures are generic, with **ENOSPC not identified**.
  - There is no EBUSY handling.
  - Stop is synchronous.
- **PipeWire backend.** No camera controls. Frames reach Chromium with capture time 0, because WebRTC drops PipeWire's kernel timestamp (**inferred**). The frame rate is truncated to an integer (29.97 → 29).

**Known issues:**

| Date | Issue | Status |
| --- | --- | --- |
| 2016 | C930 non-monotonic kernel timestamps freeze video | Worked around with `Now()`, still in place |
| 2016 | Controls persisted across sessions | Best-effort reset on every open; overwrites `v4l2-ctl`/udev settings when it works (**inferred**) |
| 2019 | Huddly GO deadlocks at stream start | Restart on first timeout; the ChromeOS quirk list adds Logitech Tap, Magewell, Sunplus |
| 2023 | `S_EXT_CTRLS` misuse in the reset: deprecated `ctrl_class`; brightness skipped; one unsupported control fails the batch | Fix reverted (broke a bot); **still unfixed** |
| 2024–2025 | PipeWire camera broken in official builds twice by CFI (M131, fixed M132; PipeWire 1.4 inline functions, fixed about M137) | Fixed with CFI suppressions (**web**, Jan Grulich's blog; Chromium tools/cfi 9f7f71ba818d) |
| 2026-11 | No cameras when the portal is denied; GNOME refuses the portal dialog | Fixed 2026-11-04 / 2026-11-05 |
| — | ENOSPC (bandwidth), multi-camera, suspend/resume | No Chromium handling or bug found |

**Copy into our Linux backend:**
1. When an fd is opened anyway, filter capture nodes by `device_caps` (not the device-wide field) plus a successful capture `ENUM_FMT`.
2. Apply mode before value, and never put an unsupported control in an `S_EXT_CTRLS` batch.
   - Use `APERTURE_PRIORITY` as UVC "auto exposure".
3. Subscribe to `V4L2_EVENT_CTRL` and flag outside changes during a recording.
4. A 1 s poll, one automatic stream restart on the first timeout, then fail after N.
   - Synchronous, ordered teardown.
   - A VID:PID quirk table like ChromeOS's (restart on timeout, user-space timestamps).
5. **Timestamps** (this changes our Linux plan, which leaned on the kernel stamp):
   - Record both the kernel buffer timestamp and our own dequeue time for every frame.
   - Check the kernel stamp's monotonicity and jitter per camera; ChromeOS distrusts it for all external cameras.
   - The metadata node's PTS/SCR (which neither Chromium nor ChromeOS uses) becomes more important, not less.
6. From ChromeOS: force `EXPOSURE_AUTO_PRIORITY = 0`, so low light cannot silently lower the frame rate.
7. If we ever use PipeWire: fall back to V4L2 when the portal is denied or lists nothing.

**Don't copy:** opening every node to list devices, `/dev/videoN` as the ID, resetting controls on open,
YUYV preference at low resolution (it costs USB bandwidth), unchecked `S_PARM`, generic STREAMON errors, and fatal
DQBUF errors.

**Add to the Linux suite:**
- L-TS: compare kernel buffer timestamp, dequeue time and metadata-node PTS/SCR per camera; flag non-monotonic or jumping kernel stamps (the C930e first, given Chromium's 2016 C930 report).
- L-CTRL-EFFECT: check that `EXPOSURE_AUTO_PRIORITY = 0` holds the frame rate in low light.

## 4. macOS

**How it works** (all **doc**). File locations:
- capture: `media/capture/video/apple/`;
- enumeration: `media/base/mac/video_capture_device_avfoundation_helpers.mm`;
- hot-plug: `media/device_monitors/device_monitor_mac.mm`;
- UVC controls: `media/capture/video/mac/uvc_control_mac.mm`;
- power-line default: `media/capture/video/video_capture_device.cc`.

- **Enumeration.** `AVCaptureDeviceDiscoverySession` (built-in, External, Continuity) inside `@try/@catch`, because AVFoundation threw on macOS 13. `suspended` devices are skipped; virtual and Continuity cameras are kept. Formats come from `device.formats`, with the max fps only, and no session is started. For every USB or built-in camera it also calls `USBInterfaceOpen` on the VideoControl interface of the **first** IOKit device matching that camera's VID:PID, to probe PTZ support. Identical cameras therefore all hit the same physical device.
- **Identity.** `device_id` = `uniqueID`; model = its last 8 hex digits (VID+PID). Control lookup by **VID:PID only**, first match, so with two identical cameras it can control the wrong one (**inferred**).
- **Formats.** Exact size, then fps match, then the **lowest max fps** ("may have lower power consumption"), then pixel-format preference with **MJPEG last**. The frame rate is clamped to 1–60 fps.
- **MJPEG.** `'dmb1'` is requested only when an MJPEG mode wins that choice.
  - By default the block buffer is decoded with libyuv `MJPGToNV12` into IOSurfaces.
  - With `--disable-video-capture-use-gpu-memory-buffer` (Mac "zero-copy is always enabled unless the user explicitly asks to disable it"), the JPEG goes to `VideoCaptureDeviceClient`, which decodes it to I420 with libyuv.
  - **No mode passes raw JPEG on to consumers.**
  - The Logitech 4K Pro (046D:087F) is forced off MJPEG to NV12 because it delivers no frames.
  - Some webcams produce invalid MJPEG; those frames are dropped.
  - `ExtractDataSpan` returns nothing when the block buffer is not contiguous.
- **Timestamps.**
  - Chromium assumes the PTS is already on the host clock and only converts its units (`CMClockConvertHostTimeToSystemUnits`).
  - The frame timestamp has been the PTS (now minus the first PTS) almost continuously since 2015. Reference time = `TimeTicks::Now()`.
  - Forwarding the **absolute** PTS as capture time was added on 2024-03-05 ([7b8f1a48a8](https://github.com/chromium/chromium/commit/7b8f1a48a845)) and disabled on 2024-05-15 ([0b4cbe91d4](https://github.com/chromium/chromium/commit/0b4cbe91d41e)): crbug 340582193 "AVFoundationCaptureForwardSampleTimestamps is causing issues". The linked 340194451 "Audio/Video desync in webrtc on MacOS with the default webcam and Chrome >= 124" was closed as Fixed on 2024-05-16, after the disable.
  - In February 2016 Chromium briefly used system time because camera-vs-system clock drift caused A/V desync. That was reverted five weeks later, and from 2016-05 the camera PTS feeds the frame timestamp and system time the reference time.
- **Controls.**
  - Every UVC request needs `USBInterfaceOpen` to succeed, with a 1 s timeout per request and a `bmControls` pre-check.
  - Chromium's 2023 commits say that on macOS 12+ VDCAssistant owns the device and `USBInterfaceOpen` returns `kIOReturnExclusiveAccess`.
  - The workaround that ignored that error was **reverted** on 2023-05-17 ("Suspected to be breaking some external cameras", internal b/278279304) and is still reverted.
  - Exposure, focus, white balance and the image controls sit behind `kExposeAllUvcControls`, **off** since 2023-04 ("causes some crashes for users on macOS with exotic camera devices").
  - Exposure time is sent as 2 bytes, but `dwExposureTimeAbsolute` is 4 (probable bug, **inferred**).
  - Power-line anti-flicker is set from the timezone on every start.
  - **No CoreMediaIO controls** are used.
  - On macOS 12+ every UVC control, PTZ and anti-flicker included, probably does nothing (**inferred**).
- **Configuration.** `beginConfiguration` → lock → `activeFormat` → unlock → `commitConfiguration` → `startRunning`. Holding the lock across `startRunning` was tried and reverted in 2022.
- **Stall watchdog.** Restarts a session that stalls for 5 × 1 s, for example when Photo Booth takes the camera (crbug 1176568, still open). **The restart was disabled on macOS 14+ in 2024-04** because it broke Presenter Overlay (crbug 335210401, since Fixed); it only logs.
- **Hot-plug.** Connected/disconnected notifications plus KVO on `suspended` and `connected`. One `AVCaptureSession` per camera, no bandwidth logic.

**Known issues:**

| Date | Issue | Status |
| --- | --- | --- |
| 2020 | Chromium's own format code had silently always requested `yuv2`, and requesting MJPEG "doesn't work" (3dd6ed31bd); MJPEG re-enabled for BRIO 4K performance (d74187c10b); Logitech 4K Pro gives no frames in MJPEG | MJPEG requested, 4K Pro falls back to NV12 |
| 2021 | Session stalls silently when another app opens the camera (crbug 1176568) | Bug open; restart watchdog disabled on 14+ in 2024 |
| 2023 | UVC controls fail on 12+ (exclusive access); workaround broke external cameras | **Reverted**; controls probably non-functional |
| 2023 | Expanded UVC controls crash on "exotic" cameras | Gated off |
| 2024 | Forwarding the absolute PTS as capture time caused A/V desync | Disabled 2024-05-15; desync bug Fixed 2024-05-16 |
| 2025 | AVFoundation enumeration throws on macOS 13 | Caught |
| **2025-09** | **macOS 26 Tahoe: low fps from Logitech cameras**, because Chromium ignored `420f` formats | Fixed: accepts `420f` (default-on kill switch); bug Verified; colour-space follow-up Fixed |
| 2025-09 | Tahoe: external webcams laggy in all apps until Photo Booth is opened (**web**) | OS-level |
| 2025 | Continuity Camera missing for some users (436126054) | Open |

**Copy into our macOS backend:**
1. `@try/@catch` around DiscoverySession; skip `suspended` devices.
2. Set `activeFormat` inside `beginConfiguration`/`commitConfiguration` before `startRunning`. Never hold the lock across `startRunning`.
3. Accept `420f` as well as `420v` (the Tahoe fix), and check that frames arrive at the requested size.
4. Before reading a JPEG block buffer, check that it is contiguous, and fall back to `CMBlockBufferCopyDataBytes`. Tolerate invalid JPEGs, counting them instead of dropping them silently.
5. A per-model MJPEG exception table, starting with 046D:087F.
6. On the endpoint-0 fallback: a 1 s timeout per request, a `bmControls` pre-check, the `wIndex = unit << 8 | interface` layout, and a **4-byte** exposure value.
7. Hot-plug notifications plus KVO on `suspended`/`connected`, and a stall detector that **reports** instead of restarting.

**Don't copy:**
- Opening IOKit interfaces during enumeration.
- The VID:PID-only control lookup (it breaks rigs with identical cameras; match by locationID or CMIO `DeviceUID`).
- MJPEG-last and lowest-max-fps format choice.
- The 60 fps cap.
- Implicit anti-flicker by timezone.
- Subtracting the first PTS (we keep absolute times).

**Add to the macOS suite:**
- M-MJPEG: Chromium shows `'dmb1'` block buffers exist, but because it decodes them, it gives no evidence that raw passthrough works on macOS 26/27. Our gating test stays the deciding one.
- M-TS: measure the PTS offset and drift against host time per camera (Chromium simply assumes the PTS is host-clock).
- M-CTRL: confirm that no endpoint-0 write breaks streaming. Chromium's revert is the main warning against our fallback, and the review's CMIO-first order already reflects it.

## 5. Lessons across all three OSes

1. **Chromium never uses a camera's own clock (UVC PTS/SCR) on any OS, and it is cautious with OS and driver capture stamps.**
   - Windows: forwarding the driver's QPC capture stamp was switched off in 2024 for a non-public reason.
   - macOS: the AVFoundation PTS is the frame timestamp, but using it as absolute capture time caused A/V desync in 2024 and was switched off.
   - Linux: the kernel buffer stamp was abandoned in 2016 after a C930 went non-monotonic, and ChromeOS still distrusts it for all external cameras.

   This gives no evidence either way on UVC PTS/SCR. It does mean every timestamp source, kernel and OS stamps included, needs per-camera validation (units, monotonicity, jumps, drift, offset) before it is trusted. W-TS does this on Windows; the Linux and macOS suites must do the same, and the rig (A5) gives the offset. Our measured cases fit: the Kiyo's PTS ticks at 1 kHz, the C930e's PTS is synthetic, and the C922's SOF runs at 884/s (**m**).
2. **Model-specific failures are normal, and at least one is mode-specific.** Chromium keeps per-model tables on every OS (MF → DS, MJPEG → NV12, quirk tables), and blocked the whole LifeCam Studio for a 720p-only failure. A per-(VID:PID, mode) table goes beyond Chromium and avoids losing the working modes.
3. **Chromium has no answer for USB bandwidth contention on any OS.** Our topology mapper and refusal classification have no precedent to borrow from.
4. **Control handling is Chromium's weakest area**:
   - silent skips;
   - always-true success;
   - no verification after a write;
   - a best-effort reset on open (Linux);
   - probably non-functional on macOS 12+.

   Our "apply, read back, verify on the image" approach is the right one, and nothing in Chromium makes it unnecessary.
5. **Chromium's reliability plumbing is worth taking**:
   - first frame (or first drop) = started;
   - activity monitors;
   - control-change monitors;
   - one restart on stall;
   - synchronous teardown;
   - hot-plug off the frame thread.

## 6. Corrections to our earlier docs

| Doc | Earlier statement | Correction |
| --- | --- | --- |
| [macos.md](../results/agent_reports/plan_20261106/macos.md) G-MJPEG | Chromium "treats the sample as compressed" | It reads the block buffer and then **decodes it**: to NV12 by default, or to I420 in `VideoCaptureDeviceClient` with GPU buffers off. Raw JPEG never leaves the capture service |
| macos.md | Chromium's PTS is host time | Chromium **assumes** the PTS is on the host clock and only converts units. It uses PTS minus the first PTS as the frame timestamp, and forwarded the absolute PTS as capture time only from 2024-03-05 to 2024-05-15 |
| macos.md | crbug 40147585 = the Logitech 4K Pro MJPEG block | Essentially right. 40147585 is the migrated crbug 1124884 (public, "VideoCaptureDeviceMac: Output and capture formats don't match"), cited by the 2020 MJPEG commits and by the TODO on the 4K Pro workaround. 1035077 (= 40664107, "Sluggish camera preview with a USB device") is also public; only 1116241 is restricted |
| [windows_mf_vs_ds.md](../results/agent_reports/plan_20261106/windows_mf_vs_ds.md) §3.3 | Chromium "treats `MF_CAPTURE_ENGINE_ERROR` as no longer valid and rebuilds it" | It reports the error and does **not** rebuild; only `DXGI_ERROR_DEVICE_REMOVED` triggers a rebuild (the file's own Q3 note already said so) |
| windows_mf_vs_ds.md §3.3 | "an MF blocklist of ~25 VID:PIDs" | 22 VID:PIDs (plus 2 that only lose the D3D11 path) |
| [capture_stack_options_plan.md](capture_stack_options_plan.md) §5 C5 | "the Chromium pattern (MF with DS fallback)" | Correct, but Chromium's fallback is per model. Since 2026-07 it also covers a mode-specific failure on a plain webcam, handled by blocking the whole model |

## 7. Caveats

- No Chromium behaviour was run here; everything is from source at the pinned commits.
- Bug text was unreadable for most crbugs, so the cause of several workarounds (b/278279304, b/336472295, the
  activation-free enumeration) is unknown.
- Whether Finch field trials turn on the features that are off by default (PipeWire camera, activation-free Windows
  enumeration) was not checked.
- The three "probable bug" items (Windows duplicate attribute key, Windows truncating `log2`, macOS 2-byte exposure)
  are readings of the code, not confirmed by Chromium.
- The ChromeOS external-camera user-space-timestamp rule was confirmed by one of two checkers (the other looked only
  at `quirks.cc`).
