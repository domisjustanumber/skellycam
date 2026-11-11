# macOS: test plan and current UVC stack (plan_20261106)

Author: macOS research agent, 2026-11-06. Read-only phase: no camera was opened, streamed or enumerated.

Labels: **measured** (a result file in this repo supports it; path given), **doc** (vendor docs or source code; URL given), **web** (forum, issue, blog or third-party README; URL given), **inferred** (my reasoning).

Nothing about macOS is **measured** in this repo. No macOS run exists, and `results/macos/` has no hardware data (REPORT.md "Limitations": "No Linux or macOS hardware run exists"). Every macOS cell below is doc, web or inferred until the MX tests run.

## 0. Bottom line for the brief

| Goal | Best tier-0 route on macOS (no driver change) | Confidence | What decides it |
|---|---|---|---|
| G-ID | `AVCaptureDevice.uniqueID` (= `locationID<<32 \| VID<<16 \| PID` as a hex string), joined to IORegistry `IOUSBHostDevice` by `locationID`. Then key on USB serial when present and unique, else on locationID (port path) | doc + web; untested | MX5 |
| G-TS | `CMSampleBufferGetPresentationTimeStamp`, a host-clock (mach) time stamped by Apple's UVC camera extension. Whether that time comes from UVC PTS/SCR or from arrival is unknown | doc (clock domain); unknown (origin, accuracy) | MX3 against the ESP32 rig |
| G-MJPEG | AVCaptureVideoDataOutput with `videoSettings = {kCVPixelBufferPixelFormatTypeKey: 'dmb1'}` on a format whose subtype is `dmb1` (Chromium's pattern). **Conflicting evidence:** a 2026-09 report saw MJPEG modes listed only as `420v` (decoded) on macOS 26.4.1. If MJPEG is not offered, no tier-0 route exists; the fallback is decode and re-encode | doc (Chromium source) vs web (uvc-avf); **this is the gating test** | MX1 |
| G-CTRL | UVC class requests (GET_*/SET_CUR) on endpoint 0 from user space, with no interface claim and no driver detach: IOKit `ControlRequest` / `DeviceRequest`, or libusb control transfers. AVFoundation's own exposure/focus/WB API is thin on macOS | web (uvc-avf: works idle and while streaming on 26.4.1) + doc (Chromium, CameraController, uvc-util source) | MX4 |
| Bandwidth | None. AVFoundation has no alt-setting control, and no tier-1 config knob (no registry or module-parameter equivalent) is known on macOS. You can only observe which alt macOS picked (standard GET_INTERFACE on ep0) and choose modes that request smaller alts | inferred + web | MX6 |

**Tier 1 (one-time admin config) on macOS:** none found. The routes that need root are libusb/libuvc *streaming*, which detach Apple's driver by re-enumerating ("capture") the device and so fall under the forbidden driver change. They are out (section 6).

## 1. Which macOS versions to test (Q1)

### Release status, 2026-11-06

| Release | Status | Hardware | Source |
|---|---|---|---|
| macOS 27 "Golden Gate" | Shipped 2026-09-14. 27.0.1 on 2026-09-28; 27.2 in developer beta (no confirmed 27.1 release found) | **Apple silicon only** | web: https://www.mactrast.com/2026/09/apple-announces-27-operating-systems-public-release-date/ , https://eclecticlight.co/2026/09/28/apple-has-just-released-updates-to-golden-gate-27-0-1-26-7-1-and-15-8-1/ , https://www.ithinkdiff.com/?p=346947 |
| macOS 26 Tahoe | 26.7.1 (2026-09-28). Last major release for Intel Macs, so Intel users stay here | Apple silicon + Intel | web: https://www.techradar.com/computing/mac-os/its-official-your-intel-mac-wont-get-macos-27-with-macos-tahoe-26-marking-the-end-of-an-era ; eclecticlight above |
| macOS 15 Sequoia | 15.8.1 (2026-09-28); still gets security updates | Apple silicon + Intel | web: eclecticlight above |
| macOS 14 Sonoma | Last security update 14.8.9 on 2026-08-06; none in the September rounds, so it is effectively out of support (Apple publishes no end date) | — | web: https://eclecticlight.co/2026/07/23/stand-by-for-macos-updates/ , https://macos-tahoe.com/blog/macos-sonoma-security-updates-ending-september-2026-what-to-do-by-mac-model/ |

### Camera-stack changes per release that matter here

- **macOS 12.0 (Monterey):** USB cameras moved to a user-space system extension, `UVCAssistant` (bundle `com.apple.cmio.uvcassistantextension`, under `CoreMediaIO.framework/.../UVCAssistant.systemextension`). It shows up in 12.0 crash logs. **web**: https://developer.apple.com/forums/thread/702849
  - From 12.0, `USBInterfaceOpen` on the VideoControl interface returns `0xe00002c5` (`kIOReturnExclusiveAccess`), where 10.x and 11 returned success. **web**: https://developer.apple.com/forums/thread/685707
  - Libusb capture (detach) needs root or `com.apple.vm.device-access`. **doc**: libusb `darwin_usb.c` line ~3529/3592, https://github.com/libusb/libusb/blob/master/libusb/os/darwin_usb.c
  - Logitech webcam regressions were widely reported at the 12.0 launch. **web**: https://community.zoom.com/t5/Zoom-Meetings/Anybody-else-having-problem-with-Logitech-webcam-with-the-new/m-p/157262
- **macOS 12.3:** Camera Extensions (CMIOExtension) introduced. `CMIOExtensionStream.send(_:discontinuity:hostTimeInNanoseconds:)` is "macOS 12.3+". **doc**: https://developer.apple.com/documentation/coremediaio/cmioextensionstream/send(_:discontinuity:hosttimeinnanoseconds:)
- **macOS 13 (Ventura):** Studio Light and Portrait in Control Center, Continuity Camera. **doc**: https://support.apple.com/en-us/105117
- **macOS 14.0/14.1 (Sonoma):** DAL plug-ins disabled in 14.1, so third-party virtual cameras must be CMIO extensions. **web**: https://eclecticlight.co/2023/10/27/how-sonoma-14-1-could-stop-your-camera-working/
  - Reactions and Presenter Overlay arrived, on Apple silicon. **doc**: https://support.apple.com/en-us/105117
  - `AVCaptureDeviceTypeExternal` replaced `ExternalUnknown`. **web**: https://github.com/opencv/opencv-python/issues/916
  - From 14.4, apps can set the `NSCameraReactionEffectGesturesEnabledDefault` Info.plist key. **web** (header text quoted): https://developer.apple.com/forums/thread/763369
- **macOS 15:** Background Replacement API (`isBackgroundReplacementActive`). **doc**: https://developer.apple.com/documentation/avfoundation/system-video-effects-and-microphone-modes
- **macOS 26.2:** Edge Light, which lights the face with the display. **web**: https://9to5mac.com/?p=1027547 . It matters to the screen-flash timing method (section 4).
- **macOS 27:** no camera-stack change found in the sources. **inferred:** treat it as unknown and test it first.

### Recommended matrix

| Priority | OS | Machine | Suite | Why |
|---|---|---|---|---|
| P0 | macOS 27.x (latest point release) | Apple silicon | **Full** (MX0–MX9) | Current release; most users will be on it |
| P0 | macOS 26.7.x | Apple silicon | **Full** | Previous release, large installed base |
| P1 | macOS 26.7.x | **Intel** (e.g. 2018–2020 Mac mini / MacBook Pro, T2) | Reduced: MX0, MX1, MX3, MX4, MX6 | Final Intel OS. Intel xHCI/T2 differs from Apple silicon USB (bandwidth, locationID). Drop it only if FreeMoCap stops supporting Intel |
| P1 | macOS 15.8.x | Apple silicon | Reduced: MX0, MX1, MX2, MX4, MX5 | Oldest release still receiving security updates |
| skip | macOS 14 and older | — | none | No security updates since 2026-08 (web). Pre-14.1 virtual-camera stack differs |

**Practical setup (inferred):** one Apple-silicon Mac that originally shipped with macOS 15 or earlier (M1–M4 era) can carry three APFS volumes (15.8, 26.7, 27.x) and boot each in turn. Apple silicon cannot run an OS older than the one it shipped with, so an M5 Mac would not do. Add one Intel Mac on 26.7 for P1. Use a **USB-A USB 2.0 hub** (the Genesys hub used on Gerald if possible) behind a USB-C adapter, and also a direct USB-C-to-A adapter, because the hub topology decides bandwidth sharing.

## 2. The macOS UVC stack today (Q2)

- **Path (inferred from the sources):** camera → AppleUSBHostCompositeDevice → `UVCAssistant` (an Apple system extension in CoreMediaIO that owns the VideoControl and VideoStreaming interfaces) → CMIO → AVFoundation (`AVCaptureDevice`, `AVCaptureVideoDataOutput`). **web**: https://developer.apple.com/forums/thread/702849 (bundle path); https://github.com/VimalMollyn/uvc-avf README ("macOS's own UVC driver holds that interface"; `libusb_kernel_driver_active` = True on interfaces 0 and 1).
  - Chromium's 2023 commit says "VDCAssistant takes ownership of the USB device" on macOS 12+. **doc**: https://chromium.googlesource.com/chromium/src/+/c00563c557bacf0ced5baf646e7da3a5e1729027
- **The camera extension supplies the frame time.** `hostTimeInNanoseconds` is "The host time in nanoseconds when the stream captured the buffer". **doc**: https://developer.apple.com/documentation/coremediaio/cmioextensionstream/send(_:discontinuity:hosttimeinnanoseconds:) . Whether Apple's built-in UVC path derives it from UVC PTS/SCR is not documented.
- **Virtual cameras and other sources:** the camera list also holds Continuity Camera (iPhone), Desk View and any third-party CMIO extension (e.g. OBS Virtual Camera). **inferred**: filter on `transportType == 'usb '` and device type External, then confirm against IORegistry.
- **System video effects:** the API exposes, read-only or user-controlled:
  - `isCenterStageActive`, plus the `centerStageControlMode` class property. With `.app` or `.cooperative` mode the app can set `isCenterStageEnabled`.
  - `isPortraitEffectActive`, `isStudioLightActive`, `isBackgroundReplacementActive`.
  - `reactionEffectsInProgress`, and the class properties `reactionEffectsEnabled` and `reactionEffectGesturesEnabled`.
  - **doc**: https://developer.apple.com/documentation/avfoundation/system-video-effects-and-microphone-modes
  - Portrait and Studio Light are documented only for the built-in camera of Apple-silicon laptops and for Continuity Camera. Manual framing needs a Studio Display or a 2024+ built-in camera. **doc**: https://support.apple.com/en-us/105117
  - Reactions: macOS "enables reaction effects for all apps by default". **doc**: https://developer.apple.com/documentation/avfoundation/avcapturedevice/reactioneffectsenabled
  - An app can default **gesture-triggered** reactions off with the Info.plist key `NSCameraReactionEffectGesturesEnabledDefault = false` (macOS 14.4+). Firefox does this. **web**: https://github.com/stdexception/gecko-dev/commit/8db6d8fd6aac1f39d87aa55f4d022cb60c33f2c9
  - One report says the key did not apply to a spawned child process. **web**: https://developer.apple.com/forums/thread/763369 . That is relevant if skellycam captures in a subprocess.
  - **inferred:** Python CLI tools have no Info.plist of their own; TCC and effects attribute to the launching app (Terminal). So a shipped skellycam needs a small signed helper `.app` that holds the camera session.
  - **Plan:** never assume effects are off. Log every `is*Active` flag and `reactionEffectsInProgress` once per second per camera, and flag the affected frames (MX7).

## 3. G-MJPEG (Q3)

Evidence for MJPEG passthrough:

- **Chromium (current main):** when the best format's subtype is `kCMVideoCodecType_JPEG_OpenDML` ('dmb1'), it sets `videoSettings = @{kCVPixelBufferPixelFormatTypeKey: @(best_fourcc)}` and treats the sample as compressed. **doc**: `media/capture/video/apple/video_capture_device_avfoundation.mm`, https://chromium.googlesource.com/chromium/src/+/refs/heads/main/media/capture/video/apple/video_capture_device_avfoundation.mm
  - It maps 'dmb1' to `PIXEL_FORMAT_MJPEG` (lines ~303–304, `FourCCToChromiumPixelFormat`).
  - It sets the video settings in `setCaptureHeight:width:frameRate:` (lines ~505–545).
  - Its comment says "For MJPEG, |sampleBuffer| is expected to always be a CVBlockBuffer" (line ~1185), and it reads the bytes with `media::ExtractDataSpan` in `processSample:` (line ~822).
  - It has one device workaround. `kModelIdLogitech4KPro = @"UVC Camera VendorID_1133 ProductID_2175"`, with the comment "Capturing MJPEG for the following camera does not work (frames not forwarded)" (crbug.com/40147585, lines ~61, 515–523).
  - **Inferred:** Chromium ships this, so at least some macOS versions and cameras do list 'dmb1' formats and deliver JPEG block buffers.
- **Apple:** "To receive samples in their device-native format, set [videoSettings] to an empty dictionary." Quoted in `prior_art/SURVEY.md` line 90 (**doc**, https://developer.apple.com/documentation/avfoundation/avcapturevideodataoutput/videosettings).

Evidence against:

- **uvc-avf / macuvc 0.1.0 (2026-09-27), macOS 26.4.1, Apple silicon, Arducam OV9281 with a Sonix bridge (0c45:6366).** "On the tested camera the MJPEG modes appear as `420v` and the YUY2 modes as `yuvs`"; output pixel formats were `2vuy, yuvs, 420v, 420f, BGRA`; "macOS decodes the MJPEG stream", so `frame.jpeg_buffer` raises AttributeError. The wire mode, read through libusb `VS_COMMIT GET_CUR` during streaming, was MJPEG 800x600@120 at alt 6. **web**: https://github.com/VimalMollyn/uvc-avf (README "Probes", "Differences from pyuvc"); https://pypi.org/project/macuvc/
  - Only one camera on one macOS version, and that bridge also has a YUY2 mode at some sizes.
  - **Inferred:** the system extension may now convert MJPEG to 420v for every camera, or only when it also has a raw format. MX1 must tell these apart.
- **The other libraries:**
  - OBS `mac-avcapture` resets `videoSettings = nil`, reads back the default pixel format, and falls back to BGRA when that format is unsupported. It only labels 'dmb1' formats as "MJPEG - JPEG OpenDML" in the format list. **doc**: `plugins/mac-avcapture/OBSAVCapture.m` lines ~274–306, 834–835, https://github.com/obsproject/obs-studio/blob/master/plugins/mac-avcapture/OBSAVCapture.m
  - FFmpeg `avfoundation.m` accepts only pixel formats from `availableVideoCVPixelFormatTypes` (lines ~540–602) and has no MJPEG path. **doc**: https://github.com/FFmpeg/FFmpeg/blob/master/libavdevice/avfoundation.m
  - GStreamer avfvideosrc and SDL3 CoreMedia have no JPEG caps (`prior_art/SURVEY.md` lines 84, 92, **doc**).
  - The nokhwa AVF backend copies the decoded CVPixelBuffer (`rust/platform/RUN_LINUX_MACOS.md`, **doc** source reading).
- **Resolutions:** a 1000x6000 MJPEG mode failed on macOS AVFoundation while lower resolutions worked; the same device worked on iPadOS with `AVCaptureSessionPresetInputPriority`. The poster used `AVCaptureSessionPresetHigh`, which may override `activeFormat`. **web**: https://developer.apple.com/forums/thread/791278
  - **Inferred:** "all resolutions" must be checked per mode. Compare the UVC descriptor list (readable without a claim) with `AVCaptureDevice.formats`.

**Draft harness gaps (inferred, from reading the drafts):**

- `mjpeg/drafts/macos/avf_mjpeg_probe.py` tests only `videoSettings = nil` and `{}`. **Add a third variant, `{kCVPixelBufferPixelFormatTypeKey: 'dmb1'}`** (Chromium's pattern), and record whether 'dmb1' appears in `availableVideoCVPixelFormatTypes` / `availableVideoCodecTypes`.
- To prove what went over the wire, read the UVC `VS_COMMIT_CONTROL` GET_CUR (bFormatIndex, bFrameIndex) and standard `GET_INTERFACE` on ep0 through libusb while streaming, as uvc-avf did. Do this without claiming any interface.
- `timing/macos/avf_timing.py` and `bandwidth/macos/avf_multi_open.py` unlock the configuration before `startRunning()`. uvc-avf reports that the session preset then replaces `activeFormat`, and that re-applying it is a stop/start that left its camera at 0 frames. Hold the lock across `startRunning()`, as `avf_mjpeg_probe.py` already does.
- `avf_multi_open.py` builds durations with `CMTimeMake(1000, fps*1000)`. uvc-avf says the exact advertised CMTime (e.g. `1000000/120000480`) is needed or `setActiveVideoMinFrameDuration` throws. Use the range's `minFrameDuration`.
- `avf_timing.py` pins pyobjc 10.3.1 and imports `libdispatch`. pyobjc is now 13.0 (PyPI, 2026-10-30), and the newer module is `dispatch`. Unpin it, or pin 13.0 for macOS 27 SDK symbols.

## 4. G-TS (Q4)

- **Clock domain:** the PTS is on the host-time clock (mach_absolute_time). Chromium converts it with `CMClockConvertHostTimeToSystemUnits(CMSampleBufferGetPresentationTimeStamp(...))` → `base::TimeTicks::FromMachAbsoluteTime` (`GetCMSampleBufferTimestamp`). **doc**: Chromium file above.
  - uvc-avf: "Times are `mach_absolute_time` seconds, the same clock as Python's `time.monotonic()` on macOS". **web**: uvc-avf README.
  - The extension API takes "host time … when the stream captured the buffer". **doc**: CMIOExtensionStream link above.
- **Origin and accuracy: unknown.** No source says whether UVCAssistant uses UVC PTS/SCR, the first-packet time, or the frame-complete time, and no accuracy figure was found (**web** search returned nothing).
  - On Windows the equivalent OS timestamps sit on a ~16 ms grid (REPORT finding 7, **measured**: `results/windows/Gerald/timing/rerun_20261027/compact_table_all_runs.txt`). **Inferred:** macOS may or may not share that, so it must be measured.
- **AVFoundation exposes no UVC PTS/SCR.** **inferred**: no API was found. `prior_art/SURVEY.md` line 119: "macOS: nothing found that exposes raw UVC headers, except libusb/libuvc running as root." Root streaming detaches the driver, so it is out under this brief.
  - Without a camera timestamp, the tier-0 fallback is the Windows plan's "frame index fitted to arrival envelope". **measured** on Windows only as a method: REPORT "Timestamp sources" table.
- **CMIO side data:** `CMIOSampleBufferGetSequenceNumber` exists (macOS 10.7+). **doc**: https://developer.apple.com/documentation/coremediaio/cmiosamplebuffergetsequencenumber
  - `kCMIOSampleBufferAttachmentKey_HostTime` exists. **web** (binding list): https://pkg.go.dev/github.com/tmc/apple@v0.6.5/coremediaio
  - **Inferred:** a sequence number could reveal drops the delegate never sees. uvc-avf notes macOS drops leave no index gap, so test whether this number has gaps.
- **Ground truth on a Mac:** use the ESP32 LED rig (`sync_rig/`), not the screen flash.
  - **Inferred:** ProMotion/variable refresh on MacBook Pro panels, and Edge Light (macOS 26.2+) changing the display's light output, both corrupt a screen-flash ground truth.
  - The rig's host ping must be logged in mach time (the plan already says so: `docs/test_gap_plan.md` MX2).

## 5. G-CTRL (Q5)

- **The AVFoundation API on macOS is limited** (**doc**: Apple platforms metadata):
  - `exposureMode` is listed for macOS 10.7+, but `setExposureModeCustom(duration:iso:)` lists iOS, iPadOS, Mac Catalyst and tvOS, **not macOS**: https://developer.apple.com/documentation/avfoundation/avcapturedevice/setexposuremodecustom(duration:iso:completionhandler:) and https://developer.apple.com/documentation/avfoundation/avcapturedevice/exposuremode-swift.property
  - **Inferred:** at best the macOS API toggles auto/locked. There is no absolute exposure, gain, WB temperature or focus position. Whether `isExposureModeSupported(.locked)` is even true for UVC cameras is untested.
  - Developers report `isFocusPointOfInterestSupported == false` on an external UVC camera. **web**: https://developer.apple.com/forums/thread/773352
- **UVC class requests from user space without a claim work, per four independent code bases:**
  - **uvc-avf** (libusb, macOS 26.4.1), with no interface claimed: `libusb_open` OK, `libusb_claim_interface(0)` → `LIBUSB_ERROR_ACCESS`. `GET_LEN/INFO/CUR/MIN/MAX` and `SET_CUR` on the camera terminal, processing unit and extension units "work, idle and while streaming". Exposure `SET_CUR` with read-back works while AVFoundation streams. **web**: https://github.com/VimalMollyn/uvc-avf
  - **libusb darwin backend:** `darwin_open` tries `USBDeviceOpenSeize`. On `kIOReturnExclusiveAccess` it keeps going with `is_open = false` ("it is possible to perform some actions on a device that is not open"). Endpoint-0 control transfers go through `DeviceRequestAsyncTO` on the device interface. **doc**: `libusb/os/darwin_usb.c` lines ~1945–1962 and ~3200
    - Its own comment: "According to Apple's documentation the device must be open for DeviceRequest but … Apple's USB Prober doesn't bother" (line ~1440). So this works in practice but **is not the documented contract** (doc + inferred risk).
  - **CameraController** PR #26 "Apply fix for macOS Monterey": on macOS 12+ it drops `USBInterfaceOpen` and calls `ControlRequest(interface, 0, &request)` directly. Before 12 it used `USBInterfaceOpenSeize`. **doc**: https://github.com/Itaybre/CameraController/pull/26 (diff of `UVCControl.swift`). Its last release is v1.4.0 (2022-05-05).
  - **uvc-util** treats `kIOReturnExclusiveAccess` from `USBInterfaceOpen` as "open" and sends `ControlRequest` on pipe 0. **doc**: `src/UVCController.m` lines ~1309–1317, ~926–939, https://github.com/jtfrey/uvc-util ; last push 2024-02-28.
  - **Chromium:** a 2023 commit ignored `kIOReturnExclusiveAccess` for PTZ and power-line on macOS 12+ (c00563c5, bug 1270335). **But current `uvc_control_mac.mm` returns failure when `USBInterfaceOpen != kIOReturnSuccess`** (lines ~366–371). Either the workaround regressed or newer macOS lets the open succeed (inferred; MX4 records the return code per OS).
    - Its all-controls path (exposure, focus, WB) is behind `kExposeAllUvcControls`, which defaults to off (line 25).
    - **doc**: https://chromium.googlesource.com/chromium/src/+/refs/heads/main/media/capture/video/mac/uvc_control_mac.mm
- **Identity pitfall in controls:** Chromium finds the IOKit device by **VID/PID only** and takes the first match (`FindDeviceWithVendorAndProductIds`). With two identical cameras it may control the wrong one. skellycam must match by `locationID` (doc: same file, lines ~172–190, 296–319).
- **Entitlements and TCC:**
  - Streaming needs Camera TCC, attributed to the launching app. An app without `NSCameraUsageDescription` is "denied silently" and the session runs with zero frames and no error. **web**: uvc-avf README "Gotchas".
  - User-space USB control needs no root (uvc-avf). **inferred/doc:** a sandboxed app would also need the `com.apple.security.device.usb` entitlement, and a hardened-runtime app needs `com.apple.security.device.camera`. Skellycam is not sandboxed today.
- **Control timing:** on Windows, C930e exposure set before streaming was not reliably applied (REPORT finding 11, **measured**). **Inferred:** UVCAssistant may also send its own controls at stream start, so MX4 must write controls *after* `startRunning()` and read them back, plus check them on the image.

## 6. What the hard constraint rules out on macOS

- **libusb/libuvc/pyuvc/Rust `uvc_iso` streaming:** these must claim the VideoStreaming interface. That fails as a normal user (`LIBUSB_ERROR_ACCESS`, web: uvc-avf), and with root it works only by re-enumerating ("capturing") the device away from Apple's driver.
  - libusb says "USB device capture requires either an entitlement (com.apple.vm.device-access) or root privilege". **doc**: darwin_usb.c line ~3592
  - INDIGO's UVC driver fails on Monterey+ because of `com.apple.UVCService`, and its only workaround is root plus auto-detach. **web**: https://github.com/indigo-astronomy/indigo/blob/master/indigo_drivers/ccd_uvc/README.md
  - This is a driver detach, so it is **out**. The MX6/MX6b rows of `docs/test_gap_plan.md` drop out of the plan.
- **Writing a DriverKit or CMIO extension of our own** that takes over the camera would replace Apple's driver. That is **out** too (inferred).

## 7. G-ID (Q6)

- **uniqueID format:** an Apple Media Engineer says to "extract the location / vendor / product id … We need to retain that pattern for backward compatibility". A DTS-forum regular adds that it "has changed in the past" and is undocumented (FB6146541). **web** (Apple engineer reply on Apple forums): https://developer.apple.com/forums/thread/803759
  - FFmpeg master (2026) parses it the same way: "USB video uniqueID = locationID<<32 | VID<<16 | PID; match on the locationID". It then reads the `USB Serial Number` from the IORegistry node with that `locationID` (`avf_usb_serial_for_location`, `avf_video_device_with_serial`). **doc**: libavdevice/avfoundation.m lines ~925–1050
  - openpnp-capture parses it the same way (`prior_art/SURVEY.md` line 82, doc).
- **modelID** for UVC cameras is "UVC Camera VendorID_<dec> ProductID_<dec>" (Chromium constant `kModelIdLogitech4KPro`, **doc**). It carries model information only, so it cannot tell identical cameras apart.
- **Stability:** `locationID` encodes the physical port path, so **inferred**:
  - stable across reboot and same-port replug;
  - changes on a port move or a hub change;
  - may differ in encoding between Apple silicon and Intel controllers.
  - The repo's draft `naming/macos_identity.py` already tests exactly this, and `naming/camera_identity.port_path_from_mac_location_id` decodes it (not run).
- **Serial:** IORegistry `USB Serial Number` / `kUSBSerialNumberString` on the `IOUSBHostDevice` (draft and FFmpeg both use it). On Windows only the C922 had one (C922SN01; REPORT finding 22, **measured**), so on macOS too the C930e, generic and Kiyo will need the locationID key (inferred).
- **Enumeration safety:** listing `AVCaptureDevice`s and reading IORegistry does not open a camera (inferred).
  - libusb's darwin enumeration calls `USBDeviceOpenSeize` on **every** device while caching descriptors (darwin_usb.c line ~1443, **doc**). By the brief's Windows experience (REPORT "Enumeration touches cameras") that may disturb a faulty camera such as the Kiyo.
  - **Prefer IOKit IORegistry reads** (`ioreg`, `IORegistryEntryCreateCFProperty`) for identity, and open a USB handle only to the one camera being controlled.

## 8. Bandwidth (Q7)

- **No app-level control.** AVFoundation has no alt-setting or bandwidth API; no surveyed library controls bandwidth through AVFoundation (`prior_art/SURVEY.md` lines 134–135, doc). macOS has no registry or module-parameter equivalent, so there is no tier 1 (inferred).
- **Observable state:** with no claim, standard `GET_INTERFACE` and UVC `VS_COMMIT GET_CUR` on ep0 show the alt macOS picked and the committed `dwMaxPayloadTransferSize`. uvc-avf read "alt setting: 6 … 3072 B per transfer" while streaming (**web**). That is enough to run the Windows "80% of a microframe" admission model on macOS (REPORT finding 17, **measured** on Windows).
- **Failure modes reported:**
  - A Qt AVFoundation app got a runtime error on the second camera on one hub; lowering the resolution let 2–3 cameras run. **web**: https://forum.qt.io/topic/41361/cannot-use-two-webcams-simultaneously-using-qtmultimedia-under-mac-os
  - In OBS on a Mac, two identical cameras showed one feed, and the advice was to use a different USB bus. **web**: https://obsproject.com/forum/threads/problem-with-two-identical-web-cameras.166768/
  - No error codes are documented. **Inferred:** expect (a) an `AVCaptureSessionRuntimeErrorNotification` with some NSError, (b) a running session that delivers 0 frames silently, or (c) reduced fps. MX6 records all three.
- **Inferred from Windows:** each MJPEG camera asks for its largest alt (≈24.5 MB/s, ~62% of the USB 2.0 periodic budget; REPORT finding 16, **measured** on Windows). Expect one MJPEG camera per USB 2.0 hub TT on macOS too, unless a lower resolution makes the camera request a smaller alt (the C930e asked for alt 10 at 480p on Windows).
  - On a USB 3 hub the USB 2.0 side is a single- or multi-TT hub, and that changes the result. Record the hub's TT type from its descriptor (`bDeviceProtocol` 1 = single TT, 2 = multi TT).

## 9. Known issues with the cameras in hand (Q8)

- **Razer Kiyo Pro (1532:0E05):**
  - No Razer Synapse control software works with it on macOS. Synapse for Mac on Sequoia 15.4.1 does not find it, though it streams in Photo Booth. **web**: https://insider.razer.com/general-discussion-6/can-i-adjust-my-kiyo-pro-in-synapse-on-mac-os-sequoia-78831
  - Users on 14.4.1 report it is not recognised on two MacBook Airs while it works on Windows. **web**: https://insider.razer.com/razer-support-45/my-kiyo-is-not-recognized-by-mac-or-windows-81813
  - A Razer Kiyo X lost autofocus after the Ventura upgrade (CameraController issues). **web**: https://github.com/Itaybre/CameraController/issues/81
  - **Inferred:** its Windows control fault (0x8007001F a few minutes after plug-in) should show on macOS as IOKit errors such as `kIOReturnNotResponding` (0xe00002ed), `kIOUSBPipeStalled` (0xe000404f) or `kIOUSBTransactionTimeout` (0xe0004051). Log raw IOReturn and libusb codes.
- **Logitech C922 / C930e:**
  - Monterey 12.0 broke many Logitech webcams in Zoom (web, link in section 1).
  - On Sonoma, Zoom picks "non-native" C922 resolutions, and Zoom ignores Logi Tune settings on Mac. **web**: https://community.zoom.com/t5/Meetings/Zoom-ignores-Logitech-LogiTune-camera-settings/m-p/167768
  - Chromium disables MJPEG on the Logitech 4K Pro (046D:087F) because frames are not forwarded (**doc**). **Inferred:** test MJPEG on each Logitech camera rather than assume.
  - **Inferred:** Logi Tune for Mac may also write controls; keep it closed during tests (on Windows LogiTune vetoed device restarts; see memory/PROGRESS).
- **Generic 4C4A:4A55:** nothing macOS-specific found. On Windows it runs at ~25.7 fps and its 1080p JPEGs fail strict decode (REPORT finding 6, **measured**). Re-check both on macOS if MJPEG bytes are reachable.
- **CameraController** controls go grey intermittently, more often when another app has the camera open; replug or reboot restores them. **web**: https://github.com/Itaybre/CameraController/issues/81 . **Inferred:** IOKit service lookup races. Test controls while streaming in another process.

## 10. macOS test suite (to build next phase)

All tests write `results/macos/<host>/<test>/<utc>/` with the repo's JSON schema and record `sw_vers`, `uname -m`, the Mac model, pyobjc version, USB topology (`ioreg -p IOUSB -l -w0`, hub TT type) and camera firmware (`bcdDevice`). Run order: MX0 → MX1 (gate) → the rest.

| ID | Test | Goal | Pass criterion | Needs human | OS rows |
|---|---|---|---|---|---|
| MX0 | Inventory without opening: IORegistry dump; `AVCaptureDevice.formats` per camera (subtype FourCC, size, fps ranges, exact min/max frame durations); `availableVideoCVPixelFormatTypes`/`availableVideoCodecTypes`; UVC descriptor list read from IORegistry (or one libusb descriptor read, no claim). **Diff UVC MJPEG frame sizes vs AVF formats** | G-MJPEG, G-ID | Report per camera which UVC MJPEG sizes are missing or relabelled (420v vs dmb1) | no | all |
| MX1 | MJPEG passthrough per camera × **every** UVC MJPEG size × 3 variants (`'dmb1'` explicit, `{}`, nil), 10 s each. Record CMBlockBuffer vs CVPixelBuffer, SOI/EOI, strict libjpeg-turbo decode, fps, CPU, and VS_COMMIT bFormatIndex via ep0 GET_CUR (no claim) to prove the wire format | G-MJPEG | Camera's own JPEG bytes = block buffer + SOI/EOI + commit says MJPEG + byte-stable JFIF header. Count sizes passing | no (Camera TCC prompt once) | all |
| MX2 | Open/close reliability: 50 cycles per camera with stop→start gaps 0, 0.1, 0.5, 2 s; then the same with two cameras alternating. Record time to first frame, zero-frame starts, runtime errors, format actually active after start | all (reliability) | ≥ 49/50 cycles deliver frames at the requested format within 3 s | no | all |
| MX3 | Timestamps vs ESP32 LED rig (`sync_rig/`), host ping in mach time: PTS, delegate arrival, CMIO sequence number and attachments, `synchronizationClock` vs host clock. Check for a quantization grid; check the PTS-to-exposure offset by sweeping exposure | G-TS | Report std/MAD vs rig per source; decide whether PTS beats arrival and whether any grid exists | yes (rig placement) | 27, 26 AS, 26 Intel |
| MX4 | Controls: (a) AVF `is*ModeSupported` dump + Locked modes; (b) ep0 class requests with no claim (IOKit `ControlRequest`/`DeviceRequest` and libusb): GET_INFO/MIN/MAX/RES/DEF/CUR, SET_CUR for AE mode, exposure abs, gain, WB auto/temp, focus auto/abs, power line. Write before start, after `startRunning()`, and after a restart; read back and verify on the image (luma step). Record the `USBInterfaceOpen` return code on each OS | G-CTRL | Each control: set value read back, image changes accordingly, survives a session restart (or a documented re-apply rule) | no | all |
| MX5 | Identity: uniqueID ↔ IORegistry (locationID, VID, PID) check; serial; AVF order. Baseline → reboot → same-port replug → port move → hub swap. Ideally with two identical cameras (buy a second C922 or generic) | G-ID | Key = serial or locationID unchanged on reboot and replug; changes predictably on port move; never collides | yes (replugs, reboot) | 27, 26 AS, 15 |
| MX6 | Bandwidth: 2 then 3 cameras on one USB 2.0 hub (single-TT and multi-TT), 1 s stagger, both orders, 720p30 and 1080p30 MJPEG plus a low-res mode. Read alt and `dwMaxPayloadTransferSize` per camera via ep0; record runtime errors, silent zero-frame sessions, fps; recovery when the winner closes | Bandwidth | Characterise the failure signal so skellycam can detect and report it (no silent 0-frame case left undetected) | yes (hub wiring) | 27, 26 AS, 26 Intel |
| MX7 | System effects: log `isCenterStageActive`, `isPortraitEffectActive`, `isStudioLightActive`, `isBackgroundReplacementActive`, `reactionEffectsInProgress` per UVC camera; turn Reactions on in the Video menu and do a gesture; repeat with a helper `.app` carrying `NSCameraReactionEffectGesturesEnabledDefault=false`, with capture in a child process | G-TS/G-MJPEG integrity | Know which effects can touch UVC frames and confirm the flags detect them | yes (gesture, menu) | 27, 26 AS |
| MX8 | TCC/packaging: run from Terminal, from a signed helper `.app` with `NSCameraUsageDescription`, and over SSH; confirm silent-denial behaviour and detection via `authorizationStatus` | all | Denied state always detected before streaming | yes | 27 |
| MX9 | Kiyo Pro: plug in, then every 10 s for 20 min run GET_CUR on 3 controls and one open/close cycle; log raw IOReturn/libusb codes, time to first control failure, and whether streaming still works after control failure. USB 3 port vs USB 2 hub | G-CTRL, reliability | Failure signature captured; app can keep streaming and mark controls unavailable | yes (plug-in timing) | 27, 26 AS |

Dropped from the earlier gap plan (`docs/test_gap_plan.md` MX6/MX6b): libusb claim and libuvc streaming. They need a driver detach.

## 11. Sources

Apple:
- https://developer.apple.com/documentation/avfoundation/system-video-effects-and-microphone-modes
- https://developer.apple.com/documentation/avfoundation/avcapturedevice/reactioneffectsenabled
- https://developer.apple.com/documentation/avfoundation/avcapturedevice/setexposuremodecustom(duration:iso:completionhandler:)
- https://developer.apple.com/documentation/avfoundation/avcapturedevice/exposuremode-swift.property
- https://developer.apple.com/documentation/coremediaio/cmioextensionstream/send(_:discontinuity:hosttimeinnanoseconds:)
- https://developer.apple.com/documentation/coremediaio/cmiosamplebuffergetsequencenumber
- https://support.apple.com/en-us/105117
- Forums: https://developer.apple.com/forums/thread/803759 (uniqueID), https://developer.apple.com/forums/thread/685707 (USBInterfaceOpen e00002c5), https://developer.apple.com/forums/thread/702849 (UVCAssistant), https://developer.apple.com/forums/thread/791278 (MJPEG resolution), https://developer.apple.com/forums/thread/763369 (gesture key), https://developer.apple.com/forums/thread/773352

Source code:
- Chromium: `media/capture/video/apple/video_capture_device_avfoundation.mm`, `media/capture/video/mac/uvc_control_mac.mm` (main, fetched 2026-11-06); commit c00563c5
- OBS: `plugins/mac-avcapture/OBSAVCapture.m` (master)
- FFmpeg: `libavdevice/avfoundation.m` (master; recent commits 2026-08)
- libusb: `libusb/os/darwin_usb.c` (master)
- CameraController PR #26; uvc-util `src/UVCController.m`; uvc-avf / macuvc 0.1.0 README

Release status: eclecticlight.co (2026-07-23, 2026-09-28), mactrast, techradar, ithinkdiff (links in section 1).

Local: `REPORT.md`, `prior_art/SURVEY.md`, `docs/test_gap_plan.md` (MX section), `rust/platform/RUN_LINUX_MACOS.md`, `mjpeg/drafts/macos/avf_mjpeg_probe.py`, `timing/macos/avf_timing.py`, `naming/macos_identity.py`, `bandwidth/macos/avf_multi_open.py`.


## Verifier notes

Adversarial verification, 2026-11-06. Read-only: no camera was opened or enumerated. Each claim was re-checked against its cited source (Apple doc `.md` endpoints, Chromium gitiles `?format=TEXT`, libusb/FFmpeg raw source, `gh api` for the GitHub repos and PR #26 diff, the PyPI JSON) and against newer sources.

### Corrections that change the plan

1. **Release status is out of date.** Apple's security releases page (https://support.apple.com/en-us/100100) lists **macOS Golden Gate 27.2, Tahoe 26.7.2 and Sequoia 15.8.2, all released 2026-10-26**. "27.0.1 is the latest" and "27.2 in developer beta" are wrong. Sonoma got nothing in the 2026-09-14 or 2026-10-26 rounds, which supports dropping macOS 14. Write the matrix as "latest point release of 27 / 26.7 / 15.8" instead of fixed numbers.
2. **The PTS is not documented as host time.** Apple's `CMIOExtensionStream.send` says "Specify sample buffer timestamps that are relative to the clock timebase specified by the `clockType` property". `hostTimeInNanoseconds` is a separate argument, and `clockType` can be `.custom`. `AVCaptureSession.synchronizationClock` (macOS 12.3+) says "All capture output sample buffer timestamps are on the synchronization clock's timebase", and gives `AVCaptureInput.Port.clock` as the device's original clock (https://developer.apple.com/documentation/avfoundation/avcapturesession/synchronizationclock). Chromium's `CMClockConvertHostTimeToSystemUnits` is an assumption in code, and uvc-avf's "same clock as time.monotonic()" is one measurement. Downgrade M14 to web + inferred. MX3 should log `CFEqual(synchronizationClock, CMClockGetHostTimeClock())`, plus the rate and offset of `port.clock` against the host clock: a port clock that drifts from host time would point to a camera-derived clock.
3. **uvc-avf is a single, unvetted source.** `VimalMollyn/uvc-avf` was created and last pushed on 2026-09-27 and has 0 stars (`gh api repos/VimalMollyn/uvc-avf`); macuvc 0.1.0 is its only PyPI release (2026-09-27). It was tested on one Sonix-bridge camera on one macOS version (26.4.1). Claims M9, M12, M13, M17 (no-gap part), M19, M28 and M35 all rest on it alone. The quotes are accurate, but treat each as one observation and not as established macOS behaviour.
4. **The 2023 Chromium commit is in a different file.** c00563c5 (François Beaufort, 2023-02-15, bug 1270335) changed `media/capture/video/mac/video_capture_device_mac.mm`, not `uvc_control_mac`. Its message reads: "on macOS 12+, VDCAssistant takes ownership of USB device". The current `uvc_control_mac` treats any `USBInterfaceOpen` result other than `kIOReturnSuccess` as failure and never mentions `kIOReturnExclusiveAccess`. So the workaround was probably lost in a refactor. "Newer macOS lets the open succeed" is the less likely reading.
5. **The macOS UVC driver became a CMIO extension in macOS 12.3, per Apple.** The doc "Overriding the default USB video class extension" says: "Starting in macOS 12.3, the operating system provides a class-compliant Core Media I/O (CMIO) extension that enables the use of USB cameras". The kernel-side matcher is `com.apple.UVCService` on `IOUSBHostInterface` (https://developer.apple.com/documentation/coremediaio/overriding-the-default-usb-video-class-extension). The 702849 forum thread shows only that UVCAssistant crashed on Monterey; the bundle ID comes from a crash-log attachment. The same doc gives the only Apple-sanctioned way to get raw camera access: a codeless DriverKit extension with `IOProbeScore` 9999 plus your own CMIO extension. That is a driver replacement, so it is **out** under the brief. The ruling is now backed by Apple documentation, not just inference.

### Verdict table

| ID | Verdict | Evidence / correction |
|---|---|---|
| M1 | weakened | Dates correct: eclecticlight 2026-09-28, mactrast 09-14, Apple silicon only. But newer releases exist: 27.2, 26.7.2 and 15.8.2 shipped 2026-10-26 (support.apple.com/en-us/100100) |
| M2 | confirmed | mactrast: Golden Gate "is not compatible with Intel-powered Macs" |
| M3 | confirmed | Apple security page: 14.8.9 on 2026-08-06, and no Sonoma entry on 09-14, 09-28 or 10-26. Apple has announced no end date, so "drop" is a judgment |
| M4 | weakened | 702849 mentions only a UVCAssistant crash on Monterey. Bundle ID is from the crash-log attachment. Apple doc dates the class-compliant CMIO extension to **12.3** |
| M5 | weakened | 685707 reports e00002c5 from `USBInterfaceOpen` "to get/set UVC properties" on 12 (10/11 fine) and does not name the VideoControl interface. The e00002c5 = kIOReturnExclusiveAccess mapping is IOReturn.h, not the thread. No Apple reply |
| M6 | confirmed | Apple doc: macOS 12.3+, quote exact. The 14.1 DAL change is from the eclecticlight web source |
| M7 | confirmed | Chromium main: `case kCMVideoCodecType_JPEG_OpenDML: return media::PIXEL_FORMAT_MJPEG`; `videoSettings = @{kCVPixelBufferPixelFormatTypeKey: @(best_fourcc)}`; comment "For MJPEG, \|sampleBuffer\| is expected to always be a CVBlockBuffer" |
| M8 | confirmed | `kModelIdLogitech4KPro = @"UVC Camera VendorID_1133 ProductID_2175"`, "frames not forwarded", crbug 40147585 |
| M9 | confirmed | README quotes match. Single camera, single OS, single new repo (see correction 3) |
| M10 | confirmed | FFmpeg checks `availableVideoCVPixelFormatTypes` and has no dmb1/MJPEG path. Its `capture_raw_data` option (empty videoSettings) exists only "for muxed devices" and was not considered |
| M11 | weakened | 791278: macOS version not stated; the poster's code sets `AVCaptureSessionPresetHigh` and requests 420v (so not passthrough); no Apple answer. It is weak evidence about resolution limits |
| M12 | confirmed | uvc-avf README quotes. Repo drafts confirmed: `avf_multi_open.py` unlocks at l.121 before `startRunning` at l.136; `avf_timing.py` unlocks at l.168 before l.174; both use `CMTimeMake(1000, fps*1000)` |
| M13 | confirmed | README: "at least 0.5 s" gap; quick restart "left the tested Sonix bridge delivering 0 frames". One camera |
| M14 | weakened | See correction 2: doc says PTS is on `synchronizationClock`/`clockType` timebase, not necessarily host time. Chromium's conversion is an assumption |
| M15 | confirmed | Absence claim; my searches also found nothing |
| M16 | weakened | Labelled doc, but it is absence of evidence (SURVEY l.119 "nothing found"). Reasonable, but inferred |
| M17 | weakened | The function exists (macOS 10.7+) but Apple gives no description at all. The "no gap" part comes from the uvc-avf README (web), not doc |
| M18 | confirmed | Apple metadata for `setExposureModeCustom`: iOS, iPadOS, macCatalyst 14, tvOS 17; no macOS |
| M19 | confirmed | README quotes exact. Single source |
| M20 | confirmed | PR #26 diff (`gh api`): `if #available(macOS 12.0, *) { ControlRequest(interface, 0, &request) }`, merged 2021-10-31. uvc-util l.1315: `else if (rc == kIOReturnExclusiveAccess) { _isInterfaceOpen = YES; }`. CameraController last push 2025-04-13 (release v1.4.0 2022-05-05); uvc-util last release v1.2 (2021), last push 2024-02-28 |
| M21 | confirmed | `darwin_open_locked` keeps going with `is_open = false`; ep0 goes through `DeviceRequestAsyncTO` on the device. The "must be open for DeviceRequest" comment is in `darwin_cache_device_descriptor` (enumeration), not the transfer path |
| M22 | weakened | The current-code facts are right: no special case for `kIOReturnExclusiveAccess`, and `kExposeAllUvcControls` is `FEATURE_DISABLED_BY_DEFAULT`. But the 2023 commit touched `video_capture_device_mac.mm` (correction 4) |
| M23 | confirmed | `FindDeviceWithVendorAndProductIds` matches on VID/PID only; first match with a usable VC interface; no locationID anywhere |
| M24 | confirmed | "Media Engineer", Apple Staff, Oct 2025: "We need to retain that pattern for backward compatibility". The accepted answer (ssmith_c, not Apple) says "it has changed in the past" (FB6146541) |
| M25 | confirmed | FFmpeg comment "USB video uniqueID = locationID<<32 \| VID<<16 \| PID; match on the locationID"; `avf_usb_serial_for_location` reads `CFSTR("USB Serial Number")` from `IOUSBHostDevice` |
| M26 | confirmed | RERUN_20261027.md l.99 |
| M27 | confirmed | `darwin_cache_device_descriptor` attempts `USBDeviceOpenSeize` on each newly cached device (failure tolerated) |
| M28 | confirmed | README: "alternate setting 6", "MJPEG 800x600 @ 120 fps with 3072 bytes per transfer". Single source |
| M29 | confirmed | Inference consistent with SURVEY l.134–135 and the Apple docs found |
| M30 | weakened | The Qt thread is from **May 2014, macOS 10.7–10.9** (pre-UVCAssistant) and does not say the cameras shared one hub. Of little use for macOS 15–27 |
| M31 | confirmed | REPORT finding 16 (24.48/24.576/24.552 MB/s, ~62%), phase2_bw_alt/summary.json |
| M32 | confirmed | Apple "System video effects" topic lists all the named properties. "enables reaction effects for all apps by default" is quoted from `reactionEffectsEnabled` (macOS 14+) |
| M33 | confirmed | support.apple.com/105117: Reactions need macOS 14+ on Apple silicon (camera type not restricted in the requirement line); Portrait/Studio Light need the built-in camera or Continuity Camera |
| M34 | weakened | The Firefox commit (bug 1886374) is confirmed. "macOS 14.4" comes from Mozilla/9to5mac, not Apple docs (the key is undocumented on Apple's site). The 763369 thread's child-process claim is the poster's **hypothesis** (the menu shows off, gestures still fire), with no Apple reply |
| M35 | confirmed | README: "denied silently … the session runs and delivers zero frames". Single source |
| M36 | confirmed | darwin_usb.c `darwin_detach_kernel_driver_locked` log text; INDIGO README: "doesn't work on macOS Monterey or later due to … com.apple.UVCService … only known workaround is to run … as root" |
| M37 | weakened | The 78831 thread (0 replies) says only "I can't detect it in Synapse" and that it "technically still works as a webcam". Photo Booth and 15.4.1 are not on the page as fetched |
| M38 | weakened | The pin (10.3.1) and the "NOT YET RUN" header are confirmed, and pyobjc 13.0 is from 2026-10-30. But `import libdispatch` still works: the pyobjc docs say "For backward compatibility `import libdispatch` works as well", and `pyobjc-framework-libdispatch==13.0` is still the package. Switching to `dispatch` is cosmetic; the pin is the real problem |
| M39 | confirmed | Edge Light shipped in 26.2 (Dec 2025) on Apple silicon (MacRumors, techradar). Inference holds |

### Missed items

- **Edge Light changes the scene lighting itself, not just a screen-flash ground truth.** On 2024+ Macs it can turn on automatically when a video call starts in low light. It is not among the AVCaptureDevice system-effect properties Apple lists, so it cannot be detected through that API. Every MX test (exposure, controls verified on the image, LED-rig timing) should record that Edge Light is off. Sources: https://www.macrumors.com/2025/11/12/apple-macos-tahoe-26-2-edge-light/ , https://developer.apple.com/documentation/avfoundation/system-video-effects-and-microphone-modes
- **Cheaper per-camera effect detection:** `AVCaptureDevice.canPerformReactionEffects`, `availableReactionTypes`, and `AVCaptureDevice.Format.reactionEffectsSupported` (the `reactionEffectsEnabled` doc: "The system only renders reaction effects when the device's active format supports the feature"). MX7 can read these on each UVC camera and format before trying any gesture.
- **Timestamp origin test via clocks:** compare `AVCaptureInput.Port.clock` against `synchronizationClock` and `CMClockGetHostTimeClock()` (correction 2). This is a no-rig first step for MX3.
- **Test-ID collision:** `docs/test_gap_plan.md` already uses MX1–MX6b with different meanings (there MX2 is timing, MX3 identity and MX4 bandwidth). Rename the new set, e.g. "MAC-0…9", or add a mapping table, so results folders do not mix.
- **PyAV avfoundation `vcodec=mjpeg`** was in the old MX1 and is silently dropped here. FFmpeg avfoundation has no MJPEG path (M10), so dropping it is right, but say so.
- **The DriverKit override route is out,** with Apple documentation behind that ruling (correction 5). The plan should record it so nobody proposes it later as a "no third-party driver" option.

### Corrections to direct answers

- **Q1:** "27.0.1 is the latest release" is wrong. The current releases are 27.2, 26.7.2 and 15.8.2 (2026-10-26).
- **Q2:** "Since macOS 12" should read "the class-compliant CMIO extension since 12.3 (Apple doc); the USB interface became exclusively owned from 12.0 (forum)".
- **Q3:** The "Against" side rests on one camera, from one 0-star repo created 2026-09-27. Present G-MJPEG on macOS as "untested; Chromium's code path implies dmb1 exists for at least some cameras".
- **Q4:** Replace "The PTS is on the host-time clock" with "The PTS is on the session's `synchronizationClock` (documented). Chromium assumes, and one third-party run reports, that this equals host time; verify it in MX3."
- **Q4, MX3 'decides':** it compares against "the Windows ~4.5 ms grid". Windows has a **16 ms** grid with ~4.4–4.6 ms std (REPORT finding 7). The open questions already say 16 ms.
- **Q5:** The 2023 Chromium workaround was in `video_capture_device_mac.mm`. Chromium is not evidence that `USBInterfaceOpen` now succeeds.
- **Q7:** The Qt runtime-error report is from 2014 (macOS 10.7–10.9). No macOS 12+ bandwidth-failure report is cited.
- **Q8:** The Kiyo Synapse thread does not mention Photo Booth or 15.4.1.
