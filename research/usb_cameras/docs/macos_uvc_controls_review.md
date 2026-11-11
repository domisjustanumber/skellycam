# macOS UVC controls: is unopened IOKit endpoint-0 the best route?

Review date 2026-11-08. Desk research only, done on Windows. No camera or USB device was opened.

Labels:
- **doc**: Apple docs, SDK headers, or source code I read.
- **web**: an issue, forum post, README or third-party claim.
- **inferred**: my reasoning, not evidence.

Line numbers point at the commit named in the Sources section.

## 1. Short answer

**Recommended route.** Build a two-path control layer, both paths in pure ctypes, with AVFoundation kept in step.

1. **CoreMediaIO (CMIO) feature controls first, for each control where it works.** Read and write through `CMIOObjectGetPropertyData` / `CMIOObjectSetPropertyData` on the control objects that Apple's UVC extension publishes for the camera.
   - It is a public API.
   - It goes through Apple's own driver, so the driver's cached state stays coherent.
   - It needs no IOKit plug-in, no USB open and no USB entitlement.
   - It finds the device by `kCMIODevicePropertyDeviceUID` = `AVCaptureDevice.uniqueID`, so two identical cameras are told apart.
   - It can be driven from Python through ctypes or PyObjC.
2. **IOKit endpoint-0 class requests as the fallback**, for controls that CMIO does not publish or that a write does not change.
   - Keep the current helper's rule: no `USBInterfaceOpen`, no `USBDeviceOpen`.
   - Use the `...TO` (timeout) variants.
   - This route has the most field evidence: about ten independent apps, reported working through macOS 26, and one through 27.0.1.
3. **Keep AVFoundation and the CMIO auto/manual flag consistent** with any raw endpoint-0 write. Set CMIO `AutomaticManual = 0` and the AVFoundation mode to `.locked`, then re-assert after every session start. One shipped app found that AVFoundation "continuously re-applies its own auto modes" otherwise.

**Two findings change the current plan's wording.**

- **An unopened `DeviceRequest` is not outside Apple's documented contract any more.**
  - Since the macOS 10.15 SDK, `IOUSBLib.h` says: "The device does not have to be open to use this function, but standard requests that change the state of the device may require that the device is opened first" (**doc**, macOS 26.5 SDK `IOUSBLib.h` L1219–1222).
  - SDKs 10.8–10.14 said "The device must be open to issue this call". The libusb comment the plan quotes reflects that old wording.
  - UVC `GET_*` / `SET_CUR` are class requests, not standard requests.
  - `ControlRequest` on the interface has the same carve-out: open is required only "if the request is a standard request which will change the state of the device" (L2369–2372). However, its result text still lists `kIOReturnNotOpen`, so that one stays slightly ambiguous.
- **Chromium deliberately reverted its "ignore `kIOReturnExclusiveAccess`" workaround in May 2023.**
  - The revert reason: "Suspected to be breaking some external cameras (internal ref b/278279304)". Bug 1432129 is not public (**doc**: Gerrit change 4542980).
  - The earlier `macos.md` guessed the workaround was "probably lost in a refactor". It was not.
  - This is the only negative signal against the endpoint-0 route from a large deployment. What broke is not public.

**Best starting code.**

- IOKit path: [physiclaw/PhysiClaw `uvc.py`](https://github.com/physiclaw/PhysiClaw/blob/8404bb019c301c59048d4915f75c05b07461928d/src/physiclaw/port/backends/uvc.py).
  - MIT licence, pure ctypes, a port of uvc-util, 419 stars, active.
  - It is close to our own `iokit_usb.py`. Borrow its verification handshake, the `wLenDone` check and the locking.
- CMIO path in Python: [hamidzr/webcam-mods `cmio.py`](https://github.com/hamidzr/webcam-mods/blob/7adb514693fff35b5a3c10147bd70acd3fddcf3e/src/webcam_mods/macos/cmio.py), about 100 lines of ctypes. It is GPL-2.0 with no clear "or later" grant, so **read it, don't copy it**.
- Hybrid logic (CMIO plus IOKit plus AVFoundation sync): [brick-a-brack/toucan-camera-server `bridge.m`](https://github.com/brick-a-brack/toucan-camera-server/blob/d83818351f777d86cc19ed999e25f24c7a0181c0/src/backends/webcam_macos/bridge.m). It is GPL-3.0, so it **can** be reused in AGPL-3.0 skellycam, and it was updated 2026-10-23.

**Confidence.**

- Medium that CMIO covers exposure, AE, focus and AF on our four cameras.
  - Positive evidence comes from single cameras: a Logitech BRIO publishes nine settable controls, including exposure 3..2047 and focus 0..255, and a Microsoft LifeCam Studio's exposure, focus and WB writes work.
  - It is untested on the C922, C930e, 4C4A:4A55 and Kiyo Pro.
- High that unopened endpoint-0 requests still work on 15 and 26.
- Low to medium on 27: one README claim only.

## 2. Corrections to earlier claims

| Earlier claim | Status | Evidence |
| --- | --- | --- |
| "An unopened ControlRequest/DeviceRequest is outside Apple's documented contract" (plan §4.3, `iokit_usb.py` header, `mac_ep0.py` header) | **Wrong for DeviceRequest since the 10.15 SDK; ambiguous for ControlRequest** | `IOUSBLib.h` (26.5 SDK) L1219–1222 and L1317–1320 say the device does not have to be open except for state-changing standard requests. 10.8–10.14 SDKs said it must be open. ControlRequest L2369–2372 carves out only standard requests, but L2378 lists `kIOReturnNotOpen` as a result. (**doc**) |
| Chromium's 2023 exclusive-access workaround was "probably lost in a refactor" (`macos.md` correction 4) | **Wrong**: it was reverted on purpose | Gerrit 4542980 (main, 2023-05-17) and 4551249 (M114 merge, 2023-05-22): "Suspected to be breaking some external cameras". (**doc**) |
| Kiyo controls greyed on M4, working on M2 (plan §5, CameraController #138) | **Imprecise** | #138 is the **Razer Kiyo 1532:0E03**, not the Kiyo Pro (1532:0E05), on an M4 Mac mini through a USB-C to USB-A adapter. A commenter's **Kiyo Pro works** on an Intel iMac with macOS 15.2. Another commenter's Kiyo works on an M2. (**web**, see §6) |
| "Absolute values need UVC SET_CUR on endpoint 0" (plan §4.3) | **Too strong** | CMIO feature controls carry absolute and native values for exposure and focus on at least two third-party cameras on 13+ (§3.1). (**web**) |

## 3. Routes compared

Notes on the table:
- "Python?" means callable with ctypes or PyObjC and no compiled extension.
- "Coexists" means it works while AVFoundation streams the same camera.

| # | Route | Contract status | Under UVCAssistant (12.3+) | Coexists with streaming | Python? | Field evidence on 13–27 | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | **CMIO feature controls** (`CMIOObjectSetPropertyData` on the device's owned control objects: `AutomaticManual`, `NativeValue`, `NativeData`, `AbsoluteValue`) | Public API, not deprecated. `CMIOObjectSetPropertyData` macOS 10.7+. `kCMIOFeatureControlPropertyNativeData` / `NativeDataRange` **added in macOS 12.0** (**doc**). Some classes the extension publishes (`ucea`, `ucwt`, `ucfa`, `ucbt`, `ucza`) are **not in the SDK header** (**doc**: absent from the 26.5 `CMIOHardwareControl.h`; **web**: LifeCamWB) | Published by Apple's extension for USB cameras: BRIO, 9 controls; LifeCam Studio, generic plus `uc**` classes. Built-in FaceTime HD and Continuity cameras publish **zero** (**web**) | Expected yes, since it goes through the owning driver (**inferred**). Not reported with skellycam-style concurrent capture | **Yes.** ctypes (webcam-mods) or PyObjC CoreMediaIO ≥ 9.2, which fixed `CMIOObjectSetPropertyData` (pyobjc #554) (**doc**) | LifeCamWB (13+): exposure, focus and WB writes work, but **only via `NativeData` on `uc**` classes**; `NativeValue` on `xpsr` was ignored. tecgraf-im: BRIO controls "every one of them settable". linkcam and camera-control ship pan/tilt/zoom through CMIO in 2026 (**web**) | **Best if M-CTRL confirms coverage.** Lowest risk of fighting Apple's driver |
| R2 | **IOKit interface `ControlRequest(TO)` on pipe 0, no `USBInterfaceOpen`** (current `iokit-intf`) | The header carves out only state-changing standard requests, but lists `kIOReturnNotOpen` (**doc**) | Works: the request goes to the device's default pipe even though UVCService owns the interface (**web**, many) | Yes (**web**: PhysiClaw "works mid-stream"; toucan; CameraController) | **Yes**, ctypes vtable (PhysiClaw, HenryZhyyy, our helper) | CameraController since 12.0 (PR #26). uvc-util (tolerates exclusive). PhysiClaw (measured 2026-07). SilverFeit (tested through 27.0.1). toucan, with a counter-example: a Sony body in USB-streaming mode never completes `SET_CUR` (timeout) (**web**) | **Fallback.** Strongest field record |
| R3 | **IOKit device `DeviceRequest(TO)` with no `USBDeviceOpen`** (current `iokit-dev`; libusb's darwin path) | **Documented** for non-state-changing requests since the 10.15 SDK (**doc**) | Works (**web**) | Yes (**web**: uvc-avf idle and streaming on 26.4.1; camdeck) | **Yes**, ctypes | uvc-avf (via libusb, which falls through to this path). thevrus/camdeck. SilverFeit as fallback after R2 (**web/doc**) | **Equal to R2**; it has the cleaner doc basis. Run both in M-CTRL and keep the one that passes |
| R4 | **`USBDeviceOpen` (no seize) + `DeviceRequestTO`, close straight after** | Fully documented (open then request) | camtint: "The video driver owns the streaming interfaces, not the device, so a plain open normally succeeds" (**web**) | camtint: "works … while the camera is live in another app" (macOS 26, Apple silicon) (**web**) | **Yes**, ctypes (two more vtable slots, 8 and 9) | camtint (falls back to **seize**: never copy that), 1030/webcam_settings, Obedience-Corp/gaze, AprilNEA/OpenLogi (uses seize) (**doc**) | Possible, but it takes an **exclusive device-level open**, which could block LogiTune, a second skellycam process, or the system during re-configuration (**inferred**). Forbidden by the current helper; only worth it if R2 and R3 return `kIOReturnNotOpen` |
| R5 | **IOUSBHost `IOUSBHostDevice(ioService, options: [])` + `sendDeviceRequest`** | Documented: init "establishes exclusive ownership of the io_service_t" and returns nil if the object is already open exclusively. `.deviceCapture` needs root or an entitlement and terminates drivers (**doc**) | Device object: works (**web**: CaskLabs/MacWebcamController, macOS 26 Apple silicon; c920-control; petercorke/camera-control). Interface object: fails, because UVCService has the interface open, so init returns nil (**doc**, from the init contract; **inferred** for this case) | Yes for the device object (**web**: CaskLabs comment "`.deviceCapture` would terminate the camera's AVFoundation/USB drivers") | **Poorly.** No PyObjC wrapper; pyobjc lists IOUSBHost as "will not be wrapped" (**doc**). Possible via `objc.loadBundle` dynamic lookup or rubicon-objc (dlech/aio-usb does this) (**doc/inferred**) | Three small 2026 Swift/ObjC apps (**doc**) | Same exclusivity cost as R4, with worse Python access. Not recommended |
| R6 | `USBInterfaceOpen` must succeed (Chromium today) | Documented | Returns `0xe00002c5` while UVCAssistant owns the VC interface (**web**: forum 685707, 701566; LifeCamWB) | No, since the open fails | Yes | Chromium bails out (`uvc_control_mac.mm` L366–371). Its full exposure/focus path is also behind `kExposeAllUvcControls`, default off, added because the expanded controls "cause some crashes … with exotic camera devices" (**doc**) | **Not viable** |
| R7 | libusb control transfers | Underneath it is R3 (`darwin_open` tries `USBDeviceOpenSeize`, carries on if refused for exclusive access; ep0 via `DeviceRequestAsyncTO`, `darwin_usb.c` L1951–1962, L3200) (**doc**) | Same as R3 | Same as R3 | ctypes possible | uvc-avf (**web**) | **Excluded** (no libusb). Read as reference only. Also note: enumeration calls `USBDeviceOpenSeize` on every device (L1443) |
| R8 | AVFoundation | `setExposureModeCustom`, `exposureDuration`, `ISO`, `lensPosition`, `setFocusModeLocked(lensPosition:)`, `setWhiteBalanceModeLocked(with:)`, `videoZoomFactor`: iOS, iPadOS, **Mac Catalyst 14**, tvOS 17, **no macOS** (**doc**, current availability metadata, fetched 2026-11-08). macOS has only `exposureMode` / `focusMode` (auto/locked) | n/a | n/a | PyObjC | An iPadOS report says `isExposureModeSupported` is false for every mode on an external UVC camera (**web**). Mac Catalyst is not reachable from Python | **No absolute values.** Use only to keep modes in step |
| R9 | DriverKit codeless override + own CMIO extension; DAL plug-ins; private frameworks | Apple's sanctioned route for raw access is a driver replacement (**doc**). DAL plug-ins disabled from 14.1 (**web**) | n/a | n/a | No | n/a | **Out** (driver change / not shippable) |

### 3.1 What CMIO actually publishes (evidence so far)

**Generic classes in the public header** (26.5 SDK `CMIOHardwareControl.h` L188–226, **doc**):
- `xpsr` (exposure; absolute units are EV).
- `fcus` (focus; meters).
- `gain` (dB).
- `whbl` (white balance; kelvin).
- `temp`. Despite toucan's use of it for white balance, the header defines it as **device temperature**.
- `shtr` (shutter; seconds).
- `pwfq` (power-line frequency).
- The header also says a control supports **either** `NativeValue` **or** `NativeData`, not both (L291).

**LifeCam Studio on 13+** ([README L133–146](https://github.com/victor-hsu0618/LifeCamWB/blob/a06507486cec382ac6512049dd88493c6c3caa25/README.md), [UVCController.swift L52–54, L102–115](https://github.com/victor-hsu0618/LifeCamWB/blob/a06507486cec382ac6512049dd88493c6c3caa25/Sources/LifeCamWB/UVCController.swift)) (**web/doc**):
- Generic classes published: `xpsr`, `ctst`, `satu`, `shrp`, `bklt`, `fcus`, `pwfq`. No gain.
- UVC-specific classes published, holding raw UVC bytes in `NativeData`:
  - `ucea`: exposure absolute, uint32 LE.
  - `ucwt`: WB temperature, uint16.
  - `ucfa`: focus absolute, uint16.
  - `ucbt`: brightness.
  - `ucza`: zoom.
- `xpsr` `NativeValue` writes were ignored. `ucea` / `ucwt` / `ucfa` `NativeData` writes worked, and so did the `AutomaticManual` toggles.

**BRIO** ([tecgraf-im `im_capture_avf.mm` L282–301](https://github.com/lispnik/tecgraf-im/blob/b47712c4d703d07cfb3f635640c08226884f9638/src/im_capture_avf.mm#L282-L301)) (**web**):
- Nine controls with ranges, including exposure 3..2047. That is the BRIO's UVC `CT_EXPOSURE_TIME_ABSOLUTE` range, so **native values look like raw UVC units** (**inferred**).
- No camera (TCC) permission was needed to read them.
- Their writes use `AutomaticManual = 0`, then `NativeValue` Float32 (L1035–1053).
- "Settable" may mean only that `IsPropertySettable` returned true. An image change is not stated.

**Caveats.**
- toucan's comment: "CMIO's NativeValue is cached … and does NOT reflect our UVC SET_CUR writes" ([bridge.m L1001–1005](https://github.com/brick-a-brack/toucan-camera-server/blob/d83818351f777d86cc19ed999e25f24c7a0181c0/src/backends/webcam_macos/bridge.m#L1001-L1005)). So raw endpoint-0 writes leave the driver's view stale. That is a reason to prefer R1, or to keep both in step (**web**).
- WWDC22 session 10022: "In the CMIOExtension architecture, we don't offer a DAL control replacement. Instead, everything is a property" (**doc**). Apple's own UVC extension still publishes feature-control objects (evidence above). It could drop them, or the undocumented `uc**` classes, in a future release without notice (**inferred** risk). M-CTRL-LIST should run on every OS in the matrix.

### 3.2 IOUSBHost answer (question 1, second bullet)

- A user-space `IOUSBHostInterface` cannot be created on the VideoControl interface while UVCService has it open. Init "returns nil" if the kernel object "is already open for exclusive access" (**doc**). I found no field report of anyone trying it; LifeCamWB and forum 701566 report the IOUSBLib equivalent failing (**web**).
- An `IOUSBHostDevice` with `options: []` **can** be created while streaming. Requests on its default pipe addressed to the VC interface work (CaskLabs on macOS 26, **web**).
- But that object holds the device exclusively for as long as it lives (**doc**). It gives the same result as R3 with more side effects and worse Python access.

## 4. Open-source code

Licence compatibility rules for AGPL-3.0 skellycam (the repo `LICENSE` is GNU AGPL v3, checked):
- MIT, BSD and Apache-2.0: reusable with attribution.
- GPL-3.0: reusable (GPLv3 §13 and AGPLv3 §13 allow the combination).
- GPL-2.0-only, or no licence: read only.

| Project | Licence | Last activity | Route on macOS | macOS 13+/AS evidence | Use |
| --- | --- | --- | --- | --- | --- |
| [physiclaw/PhysiClaw](https://github.com/physiclaw/PhysiClaw) `src/physiclaw/port/backends/uvc.py` | MIT | pushed 2026-11-08, 419★ | R2 in **pure ctypes**. Tries `USBInterfaceOpen` best-effort and ignores exclusive access (L371–375). `ControlRequest` pipe 0 (L413), rejects short transfers (L398–414) | "ControlRequest on pipe 0 works even when USBInterfaceOpen is refused … no privileges and works mid-stream" (L27–30). Firmware quirks measured 2026-07: write-through-but-dead registers, AE mode flips on stream renegotiation (L37–56) (**doc/web**) | **Borrow**: vtable layout, single-camera handshake, `wLenDone` check, lock around I/O, the "trust pixels, not readbacks" rule. **Don't** copy the best-effort `USBInterfaceOpen`: if it ever succeeded it would hold the VC interface (**inferred**) |
| [jtfrey/uvc-util](https://github.com/jtfrey/uvc-util) | MIT | last push 2024-02-28; PRs to 2026-08 | R2 after `USBInterfaceOpen`; `kIOReturnExclusiveAccess` treated as open (`src/UVCController.m` L1311–1317), `ControlRequest` pipe 0 (L938) | #24 (2025-09) user lists controls on a recent Mac. #14 "no capabilities" on the 12 beta was 2021 (**web**) | **Borrow** the control tables and value types; reference for units |
| [Itaybre/CameraController](https://github.com/Itaybre/CameraController) | GPL-3.0 | last push 2025-04-13; last release v1.4.0 2022-05-05; 1764★ | R2, **no open on 12+** (`UVC/Controls/UVCControl.swift` L82–86). Device found by VID/PID, then locationID prefix of `uniqueID` (`UVC/Extensions/AVCaptureDevice+USB.swift` L15–66). `isCapable` = GET_INFO ≠ 0, so "greyed out" means GET_INFO failed or no interface (L60–62) | Mixed: greyed-out reports on M1/Ventura often cured by replug or restart (#81). #129 (14.2.1): macOS lighting effects unavailable after using it. #142 (2025-11): another app resets zoom (**web**) | Reference; reusable (GPL-3.0). Its sandbox entitlements include `com.apple.security.device.usb` |
| [brick-a-brack/toucan-camera-server](https://github.com/brick-a-brack/toucan-camera-server) `src/backends/webcam_macos/bridge.m` | GPL-3.0 | 2026-10-23 | **Hybrid.** CMIO for ranges (L595–650) and auto/manual (L653–672, L1192–1198). R2 `ControlRequestTO` with 250 ms timeouts (L139, L288–328) after tolerating exclusive access (L188–198, L278–280). AVFoundation mode sync after writes (L1202+). Finds the CMIO device by `DeviceUID == uniqueID` (L541–570) | Active 2026 product; documents a Sony-body `SET_CUR` timeout (**web**) | **Best reference for the overall design**; reusable |
| [hamidzr/webcam-mods](https://github.com/hamidzr/webcam-mods) `src/webcam_mods/macos/cmio.py` | GPL-2.0 (no "or later" grant found) | 2026-11-04, 71★ | R1 in **pure ctypes**: `fcam` and `fcnv` on `xpsr` / `fcus` / `pwfq` (L74–93) | No outcome evidence (**doc**) | **Read only**; rewrite our own (≈100 lines) |
| [victor-hsu0618/LifeCamWB](https://github.com/victor-hsu0618/LifeCamWB) | none | 2026-03-28 | R1 with `NativeData` on `uc**` classes | Works on LifeCam Studio, macOS 13+ (**web**) | **Read only.** Source for the `uc**` class codes |
| [lispnik/tecgraf-im](https://github.com/lispnik/tecgraf-im) | NOASSERTION | 2026-10-25 | R1 `NativeValue` | BRIO enumeration (**web**) | Read only until licence checked |
| Chromium [`media/capture/video/mac/uvc_control_mac.mm`](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/media/capture/video/mac/uvc_control_mac.mm) | BSD-3 | last change 2026-10-30 | R6: requires `USBInterfaceOpen` success (L366–371), then `ControlRequestTO` (header L154). Device by VID/PID only (L172–190) | Workaround reverted 2023 (see §2) (**doc**) | Reference for the request layout; **evidence that tolerating exclusive access broke some cameras** |
| [VimalMollyn/uvc-avf](https://github.com/VimalMollyn/uvc-avf) (PyPI `macuvc`, `uvc-avf` 0.1.0) | MIT | 2026-09-27, 0★ | R7 libusb via ctypes (`uvc_avf/__init__.py` L592–608), which runs as R3 underneath | README: macOS 26.4.1 Apple silicon, Arducam/Sonix: GET/SET work idle and streaming (**web**) | Read; its evidence counts for R3 |
| [libusb darwin_usb.c](https://github.com/libusb/libusb/blob/119604ccb22deade65551d3562c15c5b3a6d324e/libusb/os/darwin_usb.c) | LGPL-2.1+ | active | R3 / seize | — | Read only. L1440–1443 holds the outdated "must be open" comment |
| [libuvc](https://github.com/libuvc/libuvc) | BSD | v0.0.9 2026-10-29 | Claims and **detaches** the VC interface (`src/device.c` L350–352, L1007–1018) | #188 "Access denied" on 12; maintainer: use sudo, "not the right library … under macOS" (**web**) | **Not usable** under the constraints |
| [pupil-labs/pyuvc](https://github.com/pupil-labs/pyuvc) | MIT (setup.cfg) / CC BY-NC-SA (LICENSE file) | v1.0.8 2026-10-21 | libuvc fork | README: non-root "currently not possible" (L101–105); Pupil v3.5 needs sudo on Monterey (**doc**) | **Not usable** |
| [webcamoid](https://github.com/webcamoid/webcamoid) | GPL-3.0 | 2026-11-07 | Today Qt Multimedia; control hook is a stub (`captureqt.cpp` L735–740). An older AVFoundation backend used R1 (`AutomaticManual`, `AbsoluteValue`/`NativeValue`), archived in webcamoid/CodeVault `VideoCapture_avfoundation/src/captureavfoundation.mm` L1226–1247, L1432–1450 | No record of why it was dropped (**doc**) | Reference for R1 property handling |
| [OBS mac-avcapture](https://github.com/obsproject/obs-studio/tree/master/plugins/mac-avcapture) | GPL-2.0+ | 33.0.1 2026-10-29 | **No UVC controls.** Only CMIO use is `AllowScreenCaptureDevices` (`OBSAVCapture.m` L26–30) | — | Nothing to borrow |
| [lvsti/CMIOKit](https://github.com/lvsti/CMIOKit) + Cameo | MIT | last commit 2020 | R1 wrapper (`Property.swift` L441–450, `Control.swift`) | Pre-12.3; Cameo #3: `Tune` property fails on a real camera (**web**) | Reference for the property model |
| SilverFeit/MacOS-WebCam-Controller | MIT | 2026-11-07 | R2, then R3 fallback (`CUVCHardware.c` L855–878), 4 ms pacing between ep0 requests | README: macOS 14+ Apple silicon, "tested through macOS 27.0.1" (**web**) | Reference: R2 to R3 fallback order, request pacing |
| CaskLabs/MacWebcamController | MIT | 2026-09-09 | R5, device object with `options: []` (`UVCDeviceDiscovery.swift` L76–91) | macOS 26 Apple silicon (**web**) | Reference only |
| bornaware/camtint | MIT | 2026-08-06 | R4, with seize fallback (`src/uvcctl.c` L255–297) | macOS 26 Apple silicon, live in another app (**web**) | Evidence that a plain device open succeeds while streaming |
| HenryZhyyy/MAC-UVC-Camera-Controller | MIT | 2026-06-01 | R2 through a C helper compiled with clang at runtime | — | Not a model (needs a compiler at run time) |

**Python packages.** None on PyPI does CMIO feature controls.
- `macuvc` / `uvc-avf` use libusb.
- `pupil-labs-uvc` needs root.
- `uvc-py` (shiguredo) has no macOS control code.
- `duvc-ctl` is Windows-only.

**Closed-source apps** (iGlasses, Hand Mirror, Mac App Store "Webcam Settings"): no source to inspect. I found no public statement of the route they use.

**pyobjc details** (**doc**, `pyobjc-framework-CoreMediaIO/Lib/CoreMediaIO/_metadata.py` @902694c):
- `CMIOObjectGetPropertyData` returns the data as `bytes`.
- `CMIOObjectSetPropertyData` takes `bytes`.
- Set was broken before 9.2 (issue #554, fixed 2023-05). Latest release is 13.0 (2026-10-30).
- There is no IOKit or IOUSBHost wrapper; pyobjc docs list both as "will not be wrapped". So IOKit stays ctypes, as now.

## 5. Recommendation

**Ranking for skellycam** (constraints: no driver change, no libusb, native Python, set while streaming, macOS 15/26/27, Apple silicon first):

1. **R1 CMIO feature controls**, per control, when M-CTRL shows the control exists, is settable and changes the image.
   - Public API; coherent with Apple's driver; identity by `uniqueID`; no USB access at all; ctypes or PyObjC.
   - Risk: coverage varies by camera, and the `uc**` classes are undocumented.
2. **R3 / R2 IOKit endpoint 0, unopened**, for controls R1 lacks.
   - R3 has the cleaner documentation (header since 10.15).
   - R2 has the most field reports.
   - Keep both backends in the helper and let M-CTRL pick the default.
   - Always use the `TO` variants with a bounded timeout (toucan uses 250 ms; 1000 ms is safer for the Kiyo, **inferred**).
   - Pace requests (SilverFeit uses ≥ 4 ms).
   - Never `USBInterfaceOpen` and never seize.
3. **R4** (`USBDeviceOpen`, request, close at once), only if R2 and R3 return `kIOReturnNotOpen` (0xe00002cd) on some OS. It is an exclusive device open, so it needs Dom's sign-off and a hold-time limit.
4. Out: R5 (no benefit over R4, poor Python access), R6 (fails), R7 (libusb), R8 (no API), R9 (driver change).

**Rules for the production module**, whatever the route (**inferred** from toucan, PhysiClaw, CameraController and our Windows C930e result):
- Write controls **after** the session's first frame.
- **Re-assert** after every session start and after replug or wake.
- Verify on the image, not by readback.
- Pair every manual write with AVFoundation `exposureMode` / `focusMode = .locked`. Restore `.continuousAutoExposure` / `.continuousAutoFocus` when switching back.
- When using R2/R3, also set CMIO `AutomaticManual` so Apple's driver agrees about who is in charge.

**What to borrow, exactly:**
- From PhysiClaw `uvc.py`: the camera-terminal discovery handshake (GET_CUR must answer with the full length), the `wLenDone == len` rule, the lock around COM-pointer use, and the "measured firmware quirks" list as test cases.
- From toucan `bridge.m`:
  - the CMIO class-map walk over device **and stream** owned objects (L595–621);
  - `DeviceUID == uniqueID` matching (L541–570);
  - CMIO auto/manual before the raw write (L1192–1198);
  - the AVFoundation sync after it (L1202+);
  - IOReturn reporting that tells a stall apart from a timeout.
- From LifeCamWB: the `uc**` class codes and the `NativeData` byte layouts. Read only, reimplement.
- From uvc-util: the CT/PU control tables. Ours (`uvc_ctrl.py`) already follow UVC 1.1 tables A-12/A-13; cross-check sizes and signedness against it.

## 6. Kiyo specifics (CameraController #138)

- [#138](https://github.com/Itaybre/CameraController/issues/138), opened 2024-12-12, still open:
  - "Razer Kiyo", 1532:0E03, firmware 0x7913, Apple M4 Mac mini Pro, Thunderbolt 5 rear port, USB-C to USB-A adapter.
  - "It displays picture but all the control are greyed out."
- [Comment 2024-12-25](https://github.com/Itaybre/CameraController/issues/138): a Razer **Kiyo Pro** (`UVC Camera VendorID_5426 ProductID_3589` = 1532:0E05) works fully on a 27-inch late-2015 **Intel** iMac with macOS 15.2.
- Comment 2025-05-18: a Razer Kiyo works on an **M2** MacBook Pro.
- [#81 comment 2022-11-07](https://github.com/itaybre/CameraController/issues/81#issuecomment-1305486489): Kiyo Pro controls work in the release build but are all greyed when run from Xcode; "the interfaceRef is always nil".
- Route: R2, unopened `ControlRequest` on the VC interface found with `CreateInterfaceIterator` (code cited in §4). Greyed out means the VC interface was not found, or GET_INFO failed.
- **Inferred**: there is no evidence that M4 versus M2 is the cause. The reporter's device is a different camera (Kiyo, not Kiyo Pro) on an adapter. Our Kiyo Pro's Windows control fault (0x8007001F a few minutes after plug-in) is the more relevant risk. M-KIYO and MX9 already cover it. Add the CMIO path to them.

## 7. Hardware tests (Mac needed)

Existing IDs: M-CTRL-LIST and M-CTRL-EFFECT (`suite/macos/tests/`). Proposed additions:

**M-CTRL-LIST (add a CMIO listing; no stream; also run once without Camera permission):**

| ID | Call | Records | Decides |
| --- | --- | --- | --- |
| CL-CMIO-1 | `CMIOObjectGetPropertyData(kCMIOObjectSystemObject, kCMIOHardwarePropertyDevices)`, then each device's `kCMIODevicePropertyDeviceUID`, matched to `AVCaptureDevice.uniqueID` | match per camera; two identical cameras if available | CMIO identity is per-port (needed for multi-camera) |
| CL-CMIO-2 | Walk `kCMIOObjectPropertyOwnedObjects` on the device **and** on each stream. For each object: `kCMIOObjectPropertyClass` (fourcc) and `BaseClass`; `CMIOObjectHasProperty` / `IsPropertySettable` / value for `fcoo`, `fcam`, `fcna`, `fcav`, `fcnv`, `fcnd`, `fcdr`, `fcnr`, `fcar`, `fcun`; for `xpsr` also the exposure-control selectors from the header | full table per camera, including undocumented `uc**` classes | Which of exposure / AE / focus / AF / gain / WB CMIO covers per camera and OS |
| CL-CMIO-3 | Compare `NativeRange` / `NativeDataRange` with ep0 GET_MIN/MAX/RES/DEF (existing `--ep0` path) | equal or not | Whether CMIO native values are raw UVC units |
| CL-CMIO-4 | Repeat CL-CMIO-1..2 without Camera (TCC) permission | readable yes/no | Whether listing can run before the permission prompt |

**M-CTRL-EFFECT (add a CMIO write backend and the cross-path checks; stream in the same process):**

| ID | Call | Pass when | Decides |
| --- | --- | --- | --- |
| CE-CMIO-W | `fcam = 0`, then exposure ×3 via `fcnv` (Float32) on `xpsr`; separately via `fcnd` (raw LE bytes) on `ucea`. Same for focus (`fcus` / `ucfa`), WB (`whbl` / `temp` / `ucwt`) and gain. AE/AF back on via `fcam = 1` | image metric moves as in the ep0 run (luma ×, sharpness ×), ep0 GET_CUR shows the value, 3/3 runs | **R1 viability per control** (the key decision) |
| CE-COH-1 | ep0 SET_CUR exposure, then read CMIO `fcnv` / `fcnd` | CMIO value updated or stale | Whether raw writes leave Apple's driver stale (toucan says stale) |
| CE-COH-2 | After a manual write by each path: toggle AVFoundation `exposureMode` locked → continuous → locked; stop and start the session; second process opens and closes the camera | manual value survives, or the revert is logged with its trigger | The re-assert rule, and whether the AVFoundation mode must be synced |
| CE-EP0-BOTH | Same exposure/focus schedule with `--ep0-backend iokit-intf` (R2) and `iokit-dev` (R3) | both pass; record raw IOReturn per request, especially `kIOReturnNotOpen` 0xe00002cd and `kIOReturnExclusiveAccess` 0xe00002c5 | Default ep0 backend; whether R4 is ever needed |
| CE-STREAM-X | Writes from a **second process** while process 1 streams (both CMIO and ep0) | process 1 frame gaps unchanged vs baseline; values take effect | Coexistence with another app holding the camera |
| CE-OWN (opt-in, needs sign-off) | `ioreg -l -w0` subtree of the device and VC interface, idle versus streaming (who is the client: UVCService / user client). Then **only with a flag**: `USBDeviceOpen` (not seize) while streaming, hold ≤ 100 ms, close, measure frame gaps | open result code; no frame gap > 2× baseline | Whether R4 is available and harmless (device-level ownership) |
| CE-TIMEOUT | Every ep0 request through `DeviceRequestTO` / `ControlRequestTO` with 250 / 1000 ms | no request blocks beyond its bound; classify stall versus timeout | Timeout value for production |
| CE-FX | After manual exposure: read `AVCaptureDevice` system-effect availability (Studio Light, Portrait, Center Stage) and restore | unchanged after restore | CameraController #129 effect |

**M-KIYO / MX9 (Kiyo Pro):** add CL-CMIO-2 every 10 s alongside the ep0 GET_CUR. Log which path fails first after plug-in, and whether CMIO keeps working when ep0 faults. Run on Apple silicon and on Intel (macOS 26).

**Matrix:** run every test on 15, 26 and 27 (Apple silicon) and on 26 (Intel), all four cameras. A route counts as passing on an OS only if it passes on every camera that advertises the control.

## 8. Unknowns that only hardware can settle

1. Which CMIO controls Apple's extension publishes for the C922, C930e, 4C4A:4A55 and Kiyo Pro, and whether exposure writes need `NativeData` on `ucea` or work with `NativeValue` on `xpsr` (CL-CMIO-2, CE-CMIO-W).
2. Whether CMIO native values are UVC units, or EV, seconds or metres in `AbsoluteValue` (CL-CMIO-3).
3. Whether unopened R2/R3 requests ever return `kIOReturnNotOpen` on 15, 26 or 27 (CE-EP0-BOTH).
4. Whether Apple's extension or AVFoundation re-applies cached values at session start or on mode changes (CE-COH-2).
5. What broke for Chromium in 2023 (b/278279304 is internal). Watch for camera hangs or disconnects during CE runs, and log `kIOUSBTransactionTimeout` 0xe0004051 and `kIOUSBPipeStalled` 0xe000404f.
6. Whether CMIO controls are published on 26 Intel the same as on Apple silicon.

## 9. Sources

**Apple (doc):**
- `IOUSBLib.h`, macOS 26.5 SDK (mirror): https://raw.githubusercontent.com/alexey-lysiuk/macos-sdk/main/MacOSX26.5.sdk/System/Library/Frameworks/IOKit.framework/Versions/A/Headers/usb/IOUSBLib.h
  - USBDeviceOpen L1006–1014; DeviceRequest L1219–1229; USBDeviceOpenSeize L1301–1307; DeviceRequestTO L1317–1327; USBInterfaceOpen L2179–2192; ControlRequest L2369–2379; ControlRequestTO L2635–2645.
  - Same DeviceRequest wording in the 12.3 / 13.3 / 14.5 / 15.5 SDKs (same repo), and in the 10.15 / 11.3 SDKs at https://github.com/phracker/MacOSX-SDKs .
  - The old wording ("must be open") is in the 10.8–10.14 SDKs in the same repo.
- `CMIOHardwareControl.h`, 26.5 SDK (mirror, same repo): class IDs L188–226, NativeData docs L164–187 and L291, L315–335.
- `CMIOHardware.h`, 26.5 SDK: error codes L104–117.
- Availability metadata (fetched 2026-11-08 from `developer.apple.com/tutorials/data/documentation/...json`):
  - https://developer.apple.com/documentation/avfoundation/avcapturedevice/setexposuremodecustom(duration:iso:completionhandler:)
  - …/exposureduration, …/lensposition, …/setfocusmodelocked(lensposition:completionhandler:), …/iso, …/setwhitebalancemodelocked(with:completionhandler:), …/videozoomfactor, …/exposuremode-swift.property, …/focusmode-swift.property
  - https://developer.apple.com/documentation/coremediaio/kcmiofeaturecontrolpropertynativedata (macOS 12.0)
  - https://developer.apple.com/documentation/coremediaio/cmioobjectsetpropertydata(_:_:_:_:_:_:)
- IOUSBHost:
  - https://developer.apple.com/documentation/iousbhost/iousbhostobject/initwithioservice:options:queue:error:interesthandler:
  - https://developer.apple.com/documentation/iousbhost/iousbhostobjectinitoptions/devicecapture
  - https://developer.apple.com/documentation/iousbhost/iousbhostobject/senddevicerequest:data:bytestransferred:completiontimeout:error:
- Overriding the default UVC extension: https://developer.apple.com/documentation/coremediaio/overriding-the-default-usb-video-class-extension
- WWDC22 10022, "Create camera extensions with Core Media IO": https://developer.apple.com/videos/play/wwdc2022/10022/

**Chromium (doc):**
- `uvc_control_mac.mm` main, fetched 2026-11-08: https://chromium.googlesource.com/chromium/src/+/refs/heads/main/media/capture/video/mac/uvc_control_mac.mm (L25, L172–190, L280–371)
- Original workaround: https://chromium.googlesource.com/chromium/src/+/c00563c557bacf0ced5baf646e7da3a5e1729027
- Revert: https://chromium-review.googlesource.com/c/chromium/src/+/4542980 and M114 merge https://chromium-review.googlesource.com/c/chromium/src/+/4551249
- `kExposeAllUvcControls`: https://chromium.googlesource.com/chromium/src/+/a2dbd2045d6825aeb9e72c6d9dc8bbeae325cf05
- File history: Gerrit query `path:media/capture/video/mac/uvc_control_mac.mm`

**Projects (doc unless noted):**
- CameraController @5cc4a67:
  - `UVC/Controls/UVCControl.swift` L60–97
  - `UVC/Extensions/AVCaptureDevice+USB.swift` L15–108
  - `CameraController/Resources/CameraController.entitlements`
  - Issues (web): https://github.com/Itaybre/CameraController/issues/138 , /81 , /129 , /132 , /142 , /15 ; PR /26
- uvc-util @8110da7: `src/UVCController.m` L926–939, L1300–1320. Issues (web): https://github.com/jtfrey/uvc-util/issues/14 , /24
- toucan-camera-server @d838183: `src/backends/webcam_macos/bridge.m`, lines as cited; commits 17484afb, d8381835
- PhysiClaw @8404bb0: `src/physiclaw/port/backends/uvc.py` L1–56, L365–420
- LifeCamWB @a065074: README L133–146; `Sources/LifeCamWB/UVCController.swift` L40–120 (web/doc)
- tecgraf-im @b47712c: `src/im_capture_avf.mm` L270–301, L1035–1053 (web/doc)
- webcam-mods @7adb514: `src/webcam_mods/macos/cmio.py` L1–93
- libusb @119604c: `libusb/os/darwin_usb.c` L1440–1443, L1946–1962, L3200
- camtint @2952671: `src/uvcctl.c` L255–297; README L142–148 (web)
- SilverFeit/MacOS-WebCam-Controller @99f03a2: `Sources/CUVCHardware/CUVCHardware.c` L845–878; README L274–281 (web)
- CaskLabs/MacWebcamController @327136e: `MacWebcamController/UVC/UVCDeviceDiscovery.swift` L70–91
- pyobjc @902694c: `pyobjc-framework-CoreMediaIO/Lib/CoreMediaIO/_metadata.py`. Issue https://github.com/ronaldoussoren/pyobjc/issues/554 (web)
- libuvc #188: https://github.com/libuvc/libuvc/issues/188 (web)
- pyuvc README @4550664 L101–105

**Forums (web):**
- https://developer.apple.com/forums/thread/685707 (USBInterfaceOpen e00002c5 on 12; no Apple reply)
- https://developer.apple.com/forums/thread/701566 (AVCaptureSession plus interface open → exclusive; re-enumerate kills video; 0 replies)

**Not verified first-hand** (from a survey sub-agent, spot-checked only where cited above): the entries for petercorke/camera-control, PierreAndreis/c920-control, fmontes/linkcam, thevrus/camdeck, 1030/webcam_settings, Obedience-Corp/gaze, AprilNEA/OpenLogi, uvc-py, and the webcamoid CodeVault line numbers.
