# Why Chromium activates every camera when it lists them on Windows

Date: 2026-11-09. Read-only research. No cameras were opened.
Code references are to chromium/chromium `main` at **9fd83992cfc5** (2026-11-09) unless a commit is named. Line numbers are approximate (±5).

Labels: **doc** = code, commit text, Gerrit review text or official docs I read. **web** = forum, issue thread, news or blog. **inferred** = my reasoning, not stated anywhere.

---

## Short answer

- **Chromium did not always do this.** The first Media Foundation (MF) capture code (2012) listed cameras the cheap way: friendly name and symbolic link from `MFEnumDeviceSources`, and it activated a camera only when opening it (**doc**, `dce6ab4f3586`, `video_capture_device_mf_win.cc` L225-243, L60-63).
- **Activation at listing time came from the browser's API needs, not from MF.** From 2013-14, Chromium's device list carries each camera's **supported formats**. Blink uses them to pick a device and format for `getUserMedia` constraints *before* it opens anything (bug 309554, "Support video capture device capabilities enumeration on getUserMedia constraints negotiation"). On Windows that meant `MFCreateDeviceSource` + source reader + `GetNativeMediaType` for each new camera (**doc**, `b9bc933ef7d7` 2014-01, `1ac077eab944` / `9f8b9b47827f` 2013).
- **Three later changes made it apply to every camera on every listing.**
  - **2018:** the Pinnacle Dazzle fallback counts MF formats to decide whether to use the DirectShow twin instead (`3772661191b0`).
  - **2020-06:** pan/tilt/zoom (PTZ) support was added to each device descriptor. This needs the media source so Chromium can query `IAMCameraControl` (`797e7dd4c4c8`, bug 934063). The permission prompt depends on it: a PTZ-capable camera gets a "camera + PTZ" prompt, other cameras get the plain prompt.
  - **2020-07:** descriptors and formats were merged into one async `GetDevicesInfo()`. The stated reason was that synchronous calls "hasn't worked well on some platforms, particularly on Fuchsia". The change also deleted the per-device format cache, so each listing re-activates every camera (`86ee59bfe04e`, bug 1072932).
- **No public Chromium text argues that activating at listing time is good on Windows.** It is a side effect of a cross-platform interface that returns "devices with capabilities". In 2020 a reviewer asked whether it was OK to query camera controls during enumeration rather than later. No answer is recorded (**doc**, Gerrit 2245473 comment on `video_capture_device_win.cc` L291).
- **Microsoft engineers are now removing it (2026), mainly to avoid a Windows OS camera permission prompt.** The Microsoft author says in review: "This helps avoid a possible Windows permission prompt without changing the web-visible behavior" (**doc**, Gerrit 8163229). Windows Insider builds are adding per-app camera consent for desktop apps, with a prompt the first time an app accesses the camera (**web**).
  - Before this work, a page **without** camera permission still triggered a full activation of every camera. Chromium then threw the capabilities away (**doc**, same review).
  - Speed is a secondary concern. Listing "can take up to 5s when a USB camera is just connected" (`b43405d55068`). New duration histograms compare the two modes (`cd64d78505ca`).
- **Status of the new mode.** The feature `kWinDeviceEnumerationWithoutActivation` is **disabled by default**, with no entry in `fieldtrial_testing_config.json`.
  - The browser wiring has landed (Nov 2-6). With the flag on, Chromium lists without activation and "upgrades" to full listing only when the page has camera permission, asks for capabilities, and Windows will not prompt.
  - Bug 565332594 is open. Two telemetry CLs are still in review.
  - A matching microphone CL was abandoned.
- **For skellycam: nothing in Chromium's reasons argues for activating at listing time.** Every reason is web-platform specific: constraint resolution before open, the PTZ permission prompt, and a fixed cross-platform interface. Chromium's own new path keeps the DirectShow fallback without activation. Our plan matches where Chromium is heading: list from property bags, and read formats per camera on demand.
  - Pitfalls to avoid: don't hold `IMFActivate` objects, shut sources down explicitly, re-resolve by symbolic link, put a timeout on per-camera queries, and expect a Windows consent prompt or `E_ACCESSDENIED` at the first activation.

---

## 1. History: when and why listing started to activate cameras

### 1.1 Timeline

| Date | Commit / CL | What changed | Why (as stated) | Label |
| --- | --- | --- | --- | --- |
| 2012-12-04 | `dce6ab4f3586` | First MF capture. `GetDeviceNames` reads `MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME` and `..._VIDCAP_SYMBOLIC_LINK`. `MFCreateDeviceSource` is called from the symlink only when a device is created (`video_capture_device_mf_win.cc` L60-63, L225-243, L266) | – | doc |
| 2013-11-14 / 2013-12-12 | `1ac077eab944` (crrev 29423003), `9f8b9b47827f` (crrev 91343002) | `VideoCaptureManager` builds a cache of names **and capabilities** "in a codepath starting in EnumerateDevices". `GetAvailableDevicesInfoOnDeviceThread` calls `GetDeviceSupportedFormats` for every device not already cached (`video_capture_manager.cc` L369-437 at `9f8b9b47827f`) | Bug 309554, public title "Support video capture device capabilities enumeration on getUserMedia constraints negotiation". `6fc51a48eb77` adds: "send the device's capabilities and format in use to the renderer for JS getUserMedia internals and for JS getCapabilities calls" | doc |
| 2014-01-31 | `b9bc933ef7d7` | Windows MF `GetDeviceSupportedFormats` written: `MFCreateDeviceSource` → `MFCreateSourceReaderFromMediaSource` → `GetNativeMediaType` loop. From here, listing activates each **new** MF camera once (later listings use the cache) | Same bug 309554 | doc |
| 2017-08-12 | `8d5627c41dac` | One format list per device, used for "reporting … to JavaScript clients as well as device and format selection logic" | Bug 750431 | doc |
| 2017-09-06 | `95a2a30ba92d` | WebcamMax excluded from detailed frame-rate queries "when clients ask for supported formats", because the queries crashed 32-bit Windows | Bugs 757385, 759413. Early evidence that querying at list time can crash third-party drivers | doc |
| 2018-07-17 | `3772661191b0` | Dazzle fallback. `AugmentDescriptorListWithDirectShowOnlyDevices` calls `GetNumberOfSupportedFormats()` on the MF descriptor of every device that DirectShow also lists. Physical UVC cameras appear in both, so **every descriptor listing** now activates them (`video_capture_device_factory_win.cc` L640-665, L733-745 at `3772661191b0`) | "Devices like Pinnacle Dazzle are listed in DirectShow with their video formats while listed in MediaFoundation with no available video format at all" (bug 862395) | doc |
| 2020-06-26 | `797e7dd4c4c8` (Gerrit 2245473) | `GetDeviceDescriptorsMediaFoundation` creates the media source for each device and calls `IsPanTiltZoomSupported(source)` (L703-711 at `86ee59bfe04e~1`) | "advertise pan, tilt, or zoom support or no support depending on device capabilities" (bug 934063 "Ability to control connected camera pan / tilt / zoom") | doc |
| 2020-07-25 | `86ee59bfe04e` (Gerrit 2306918) | `GetDeviceDescriptors()` + `GetSupportedFormats()` replaced by async `GetDevicesInfo()`, which returns descriptors **and** formats. `VideoCaptureSystemImpl` loses its "do not query the factory for supported formats again" cache: formats are re-read on **every** listing | "Both were synchronous. That hasn't worked well on some platforms, particularly on Fuchsia" (bug 1072932 "Refactor VideoCaptureDeviceFactory to enumerate devices asynchronously"). Windows is not mentioned | doc |
| 2020-08-06 | `77f324ac9dbd` | Fix: after the refactor MF formats were read from a null source, so DirectShow was used instead | Bug 1112947 | doc |
| 2026-08-03 | `b43405d55068` | Listing moved off the main thread | "It can take up to 5s when a USB camera is just connected" and froze running streams | doc |
| 2026-10-20 → 11-06 | `4ebcfb5643fb`, `6581c2f839aa`, 8621541, `9f7f8bd087a4`, 8640669, `326cd9ddfc37`, 8688212, `de214cf242fd`, `cd64d78505ca` | Activation-free `kDevicesOnly` mode and browser wiring (section 3) | Bug 565332594 "Windows: Avoid camera activation during device enumeration" | doc |

### 1.2 What the current code does (feature off, the default)

- **Thread.** Listing runs on a dedicated MTA COM thread. A code comment says it "can take a long time in some cases" (`video_capture_device_factory_win.cc` L887-912) (**doc**).
- **Mode.** The full mode is forced unless the feature is on (L846-850, L857-860) (**doc**).
- **Per MF device** (`GetDevicesInfoMediaFoundation`, L1100-1185) (**doc**):
  - Read the friendly name and symlink from the `IMFActivate` attributes (L1125-1140).
  - Apply the VID:PID and name blocklists (L1145).
  - Create the source and query controls and formats (L1155-1166): `CreateDeviceSourceMediaFoundation(device_id …)` builds attributes from the **symlink** and calls `MFCreateDeviceSource` (L800-826). `E_ACCESSDENIED` maps to `MFSourceOutcome::kFailedSystemPermissions` (L825-826).
  - `VideoCaptureDeviceMFWin::GetControlSupport(source)` QIs `IAMCameraControl` / `IAMVideoProcAmp` and reads the pan/tilt/zoom ranges (`video_capture_device_mf_win.cc` L1036).
  - `GetSupportedFormatsMediaFoundation` creates a source reader, with DXGI attributes when D3D11 is allowed, and loops over `GetNativeMediaType` (L1356-1432).
  - Release the `IMFActivate` right away (L1177).
- **Sensor (IR/depth) cameras** are listed in a second pass with `KSCATEGORY_SENSOR_CAMERA` and de-duplicated by symlink (L1108-1112, crbug 807293). IR cameras have been excluded by default since `c10d6298da6e` (2021) (**doc**).
- **DirectShow fallback.** MF devices with zero formats are swapped for their DirectShow twin when DirectShow has formats (L1187-1252, the "Pinnacle Dazzle" comment at L1220). DirectShow-only devices (virtual cameras) are appended (**doc**).
- **Facing.** The WinRT `FindAllAsyncAqsFilter` call sets `facing` from the enclosure panel. Then the result is posted (L951, L1040-1050) (**doc**).

### 1.3 The cross-platform reason, in plain terms

- **Constraint selection needs formats before open.** Blink's `getUserMedia` constraint resolution scores every (device, format) pair before opening a camera: `SelectSettingsVideoDeviceCapture(const VideoDeviceCaptureCapabilities&, …)` in `third_party/blink/renderer/modules/mediastream/media_stream_constraints_util_video_device.cc` L1109-1160 (**doc**).
  - The data comes from `MediaDevicesDispatcherHost.GetVideoInputCapabilities()`. Its `VideoInputDeviceCapabilities` struct holds `device_id`, `control_support` (PTZ), `formats` and `facing_mode` (`third_party/blink/public/mojom/mediastream/media_devices.mojom` L41-48, L102-109) (**doc**).
  - The mojom comment says this data is "intended for the implementation details of algorithms such as settings selection for getUserMedia" (**doc**).
- **`enumerateDevices()` can return capabilities.** Pages with permission get `InputDeviceInfo.getCapabilities()`. `MediaDevicesManager` treats "video input capabilities requested" as the trigger for full listing (`content/browser/renderer_host/media/media_devices_manager.cc` L1222-1226) (**doc**).
- **The PTZ prompt depends on PTZ support.** A `getUserMedia` call with PTZ constraints shows a camera + PTZ prompt only if the camera supports PTZ. Otherwise the user gets a regular camera prompt (**doc**, web.dev "Control camera pan, tilt, and zoom"). Chromium has to know PTZ support per camera before opening, which needs the media source on Windows (`797e7dd4c4c8`) (**doc**).
- **The interface hard-wires it.** `VideoCaptureDeviceFactory::GetDevicesInfo` returns `VideoCaptureDeviceInfo` = descriptor + `supported_formats` on every platform (`86ee59bfe04e`). On Linux, macOS and Android, formats are cheap or need no "open". On Windows MF they need a media source (**doc** for the interface; the "cheap elsewhere" part is **inferred**).

**Not public / not found:** I found no Chromium text that weighs the Windows cost of activation against these needs, before 2026. The 2020 refactor review (Gerrit 2306918) has no comment about Windows activation or the removed cache. The 2020 PTZ review has a reviewer asking "Is it OK to call this at this point? … the other places are in GetPhotoState and SetOptions which happen way after the device enumeration", with no recorded answer (**doc**, Gerrit 2245473 inline comments).

---

## 2. Why not just an index or the symbolic link?

- **Chromium already uses the symlink as the device ID.** It never uses an MF index, and it re-creates the source from the symlink each time (`MFCreateDeviceSource` with `MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK`, L800-826). This has been true since 2012 (`dce6ab4f3586`). So the question is not "symlink vs activation". It is whether the list must carry formats and PTZ (**doc**).
- **What breaks without capabilities in the list** (from the code and the 2026 CLs):
  1. **Constraint selection and `getCapabilities()`** have no formats. The 2026 design fixes this by "upgrading" to a full listing when a page with permission asks for capabilities. When Windows permission is undetermined, the abandoned prototype used "existing fallback video formats" (**doc**, Gerrit 8163229 description, `9f7f8bd087a4`, `326cd9ddfc37`).
  2. **The PTZ permission prompt** cannot know PTZ support. The 2026 work adds a capability-only update of cached PTZ support "without reporting a device-list change" (**doc**, 8640669).
  3. **The Dazzle / zero-format fallback** needs MF formats to choose between MF and DirectShow. The 2026 code shows this does **not** need activation at listing time. In devices-only mode both lists are kept without binding. When capabilities are later read, the MF ID and list position are kept and mapped to the DirectShow ID needed to open the device (`mf_to_direct_show_device_ids_`, L1234-1250, header L154; `4ebcfb5643fb`). The stated aim: "This avoids a false device-list change when capabilities are added" (**doc**).
  4. **IR filtering** uses the MF category attributes (`KSCATEGORY_SENSOR_CAMERA`), not activation (**doc**, `c10d6298da6e`, L1108-1112).
  5. **Virtual cameras.** DirectShow-only virtual cameras are found by DirectShow listing, not by activation (**doc**, `8f68d00946dd` 2018, L1191-1196).
- **MF index stability:** I found no Chromium discussion of MF indices being unstable. Chromium simply never used them (**doc**: absence in the code paths read; **not found** in commits or reviews). The stability concern that does appear in 2026 is about **ID and list position across the two modes** (`4ebcfb5643fb`). It exists to avoid spurious `devicechange` events (**doc**).

---

## 3. The 2026 activation-free change

### 3.1 What it solves (stated)

- **The Windows OS camera permission prompt.**
  - Rahul Singh (Microsoft), in the prototype review: "Before this change, a page without browser permission still triggered a full Windows enumeration. Chromium then discarded the capabilities and returned a single videoinput device entry with empty fields. With this change on Windows, we'll do a `kDevicesOnly` enumeration instead. This helps avoid a possible Windows permission prompt without changing the web-visible behavior." (**doc**, Gerrit 8163229, /COMMIT_MSG L12, 2026-10-05)
  - The prototype description: use `kDevicesOnly` when "the webpage lacks browser camera permission, the request does not ask for video capabilities, or Windows system camera permission is undetermined and activation could display the system permission prompt" (**doc**).
  - `SystemMayPromptForVideoCapture()` returns true when the cached Windows camera permission is neither allowed nor denied (`chrome/browser/chrome_content_browser_client.cc` L3901-3909). The review explains why `CanPrompt()` was not used: it "always returns false for camera and microphone on Windows. It tells us whether Chrome can request permission, not whether Windows might show a dialog when we activate a camera" (**doc**, Gerrit 8163229).
- **Why activation can prompt.** Microsoft's docs say camera APIs return `E_ACCESSDENIED` when privacy settings deny access. They show this at `IMFActivate::ActivateObject` when "initializing an IMFMediaSource" (**doc**, "Handle the Windows camera privacy setting", 2026-09-08). Activation is the point where Windows checks camera privacy. Chromium maps that error at `MFCreateDeviceSource` (L825-826) (**doc**).
- **Why now: Windows is adding per-app camera consent for desktop apps.**
  - Insider builds (Experimental 26H1 build 28120.3302, release notes dated 2026-10-23; earlier 26340.x builds) add per-app camera, microphone and location toggles for desktop apps.
  - Reports say apps that have not yet accessed the camera are asked the first time.
  - The feature is under controlled rollout, Insider only (**web**: BleepingComputer 2026-08-26, Help Desk Geek 2026-10-28).
  - The Chromium work began 2026-07-29 (prototype 8163229), by Microsoft authors and reviewers. This fits the Windows change, but no CL names the Windows feature (**inferred**).
- **A third party shows the same failure.** DuckDuckGo's privacy test site has a repro page for "the Windows OS camera prompt issue". It describes the real `enumerateDevices()` as "what triggers the OS prompt on Windows MSIX" (**web**, privacy-test-pages.site "Device Enumeration Chaos").
- **Speed is secondary.** Separate duration histograms per mode were added "to compare the two modes" and "to detect performance regressions during feature rollout" (**doc**, `cd64d78505ca`). No CL claims a measured speed gain.
- **Not mentioned:** No 2026 CL or review comment mentions LEDs, the privacy indicator, Frame Server or `devicechange` storms as the motivation (**doc**, from reading the CL descriptions and inline comments of 8163229, 8564863, 8577359, 8628927, 8684468).

### 3.2 The CL chain (all bug 565332594)

| CL | Status | What it does | Label |
| --- | --- | --- | --- |
| 8163229 | Abandoned 11-03 (end-to-end prototype, split into the CLs below) | Whole design. Includes fallback formats when browser permission is granted but OS permission is undetermined | doc |
| 8564863 / `4ebcfb5643fb` | Merged 10-20 | Feature flag (off), `VideoCaptureDeviceEnumerationMode`, Windows `kDevicesOnly` path (no MF source, no DirectShow filter bind), stable IDs and positions across modes | doc |
| 8577359 / `6581c2f839aa` | Merged 10-27 | Mode passed through `VideoSourceProvider::GetSourceInfos()`. `DeviceFactoryImpl` triggers a full listing before `CreateDevice` if the cache lacks capabilities | doc |
| 8621541 | Merged 11-02 | Mode passed through `VideoCaptureManager` / `VideoCaptureProvider` | doc |
| 8628927 / `9f7f8bd087a4` | Merged 11-03 | `MediaDevicesManager` starts in `kDevicesOnly` and upgrades to full listing for good once capabilities are needed | doc |
| 8640669 | Merged 11-03 | Updates cached PTZ support without firing `devicechange` | doc |
| 8684468 / `326cd9ddfc37` | Merged 11-05 | Upgrade only if browser camera permission is granted, capabilities are requested, **and** there is no OS prompt risk | doc |
| 8688212, 8712184, 8713780 | Merged 11-06 | Metrics split by mode; WinRT (UWP) facing-lookup threading cleanup; listing duration histograms | doc |
| 8763725, 8762274 | Open | Telemetry: how often the OS permission cache is read before it is populated (the default "not determined" maps to devices-only) | doc |
| 8258230 | Abandoned | "Audio capture: Avoid microphone activation during Windows enumeration". The review says "We are not proceeding with that for now" | doc |

**Rollout:** `kWinDeviceEnumerationWithoutActivation` is `FEATURE_DISABLED_BY_DEFAULT` (`media/capture/capture_switches.cc` L67-69). It has no entry in `testing/variations/fieldtrial_testing_config.json` on `main` (**doc**). The issue tracker lists the bug as open with two pending CLs (**doc**, issues.chromium.org JSON). No intent-to-ship, blog post, discuss-webrtc or chromium-dev thread was found (**not found**).

---

## 4. Known user-visible side effects of activating at listing time

| Effect | Evidence | Label |
| --- | --- | --- |
| OS permission prompt shown by a page that only listed devices (packaged apps today; desktop apps on new Insider builds) | Gerrit 8163229 review quotes; DuckDuckGo repro page (MSIX); Windows Insider per-app consent coverage | doc (Chromium) / web (DDG, Windows) |
| Slow listing: up to 5 s just after hot-plug, blocking the utility thread that pumps frames ("5s freeze in the ongoing video stream when camera is plugged in") | `b43405d55068` | doc |
| Crashes in third-party drivers when queried at list time: WebcamMax on 32-bit (2017); eBUS DirectShow source (2024, `4547c21b81c2`, "Block eBUS DirectShow Source for DirectShow virtual device"); a long VID:PID blocklist for MF | commits listed | doc |
| Work and privacy cost with no benefit: pages without permission still activated every camera, and the result was thrown away | Gerrit 8163229 | doc |
| Camera LED blinking or Windows "camera on" display during Chrome's listing | **Not found.** I found no crbug, forum or Microsoft text tying Chrome's listing to LED blinks. Windows' software camera indicator is described as reacting to frames "streaming or not streaming" (**web**, ElevenForum and others on `NoPhysicalCameraLED`). Our own test of `ActivateObject` + `GetNativeMediaType` without `Start` saw no pipe opened (alt 0) and no disturbance (**measured**, [windows_results_20261106.md](windows_results_20261106.md) §1 FMT-NOGRAB). So activation alone probably does not light the LED on UVC cameras (**inferred**; drivers may differ) | web / inferred |
| Conflict with an app already holding the camera | Not reported for Chromium. Our measurement: MF activation and format listing worked while another process streamed and did not delay its open (**measured**, same section) | measured |

Microsoft docs on whether activation alone powers the sensor: **not found**. The docs say only that activation creates the media source, and that privacy is enforced there with `E_ACCESSDENIED` (**doc**, "Enumerating Video Capture Devices"; "Handle the Windows camera privacy setting").

---

## 5. How others do it (brief)

- **Microsoft's MF sample** lists with `MFEnumDeviceSources` and calls `ActivateObject` only on the chosen device. It notes the privacy check happens "when initializing the capture device" (**doc**, learn.microsoft.com "Enumerating Video Capture Devices").
- **libwebrtc (DirectShow)** reads `FriendlyName` / `DevicePath` from the property bag in `GetDeviceInfo` (`modules/video_capture/windows/device_info_ds.cc` L119-200). It binds the filter (`BindToObject`, L261) only in `GetCaptureFilter`, called from `CreateCapabilityMap` when capabilities are first asked for. Results are cached for the last device (`device_info_impl.cc` L40-52) (**doc**, webrtc `main`).
- **Firefox** builds libwebrtc's DirectShow capture on Windows (`third_party/libwebrtc/modules/video_capture/video_capture_internal_impl_gn/moz.build` L167-174 list `device_info_ds.cc`, `video_capture_ds.cc`), so it lists lazily the same way (**doc**). Whether Firefox's constraint scoring then binds every camera was not checked.
- **OBS (libdshowcapture)** binds **every** device and reads its caps while listing: `EnumDevices` → `BindToObject` (`source/dshow-enum.cpp` L477), then `EnumVideoDevice` → `EnumVideoCaps` (`source/dshowcapture.cpp` L222-254), at `c13d4b7b0c66` (**doc**). Chromium is not unique. Apps that show a resolution picker for every camera tend to open everything.

---

## 6. What this means for skellycam

**Does any Chromium reason apply to us?** Mostly no (**inferred**, from sections 1-3):

| Chromium reason | Applies to skellycam? |
| --- | --- |
| Blink must score (device, format) before opening, for `getUserMedia` constraints | No. We choose formats per camera when the user configures or opens it |
| PTZ permission prompt needs PTZ support up front | No. We have no web permission UI |
| One cross-platform `GetDevicesInfo` returns formats with the list | No. Our API can separate "list" from "describe camera" |
| Dazzle / zero-format → DirectShow fallback | Can be lazy. Chromium's own 2026 path keeps the fallback without activation (map the ID at describe time) |
| IR / sensor filtering, virtual cameras | No activation needed (category attributes; DirectShow list) |

The only case for activating every camera at listing time: if a screen must show every camera's modes at once, all cameras get activated anyway. Even then, do it per camera, in the background, with a timeout, and keep the plain list instant (**inferred**).

**Pitfalls to avoid** (each with its source):

1. **Don't keep `IMFActivate` objects from the list.** Chromium releases them right after reading the strings and re-creates the source from the **symlink** with `MFCreateDeviceSource` (L800-826, L1177). If you do call `ActivateObject`, the caller must call `ShutdownObject`, and a second `ActivateObject` creates a new instance (**doc**, `IMFActivate::ShutdownObject` remarks).
2. **Shut the source down explicitly.** "If the application creates the media source … the application is responsible for calling Shutdown to avoid memory or resource leaks" (**doc**, `IMFMediaSource::Shutdown`).
   - A source reader made from the source shuts it down when released, unless `MF_SOURCE_READER_DISCONNECT_MEDIASOURCE_ON_SHUTDOWN` is TRUE (**doc**).
   - Chromium's describe path relies on that implicitly. If reader creation fails, it just drops the `ComPtr` without `Shutdown` (L1378-1384) (**doc**; calling it a leak risk is **inferred**). Call `Shutdown()` yourself in a `finally`.
3. **Expect a consent prompt or `E_ACCESSDENIED` at the first activation, not at listing.** This is the reason Chromium is moving. Dom's machine runs build 26300, an Insider-series build (**inferred**), so the per-app desktop prompt may appear there.
   - Listing from property bags never prompts (**inferred** from the Chromium design and Microsoft docs).
   - Trigger the first activation only after a user action ("describe/open camera"), and map `E_ACCESSDENIED` to a "check camera privacy settings" message with `ms-settings:privacy-webcam` (**doc**, Microsoft privacy page).
4. **Stale symlinks.** A camera can vanish or re-enumerate between listing and describing. Our generic camera re-enumerates after DirectShow refusals, and MF once missed a camera that re-appeared ~150 ms later (**measured**, [capture_backends_review.md](capture_backends_review.md)). Treat "describe" failures as "re-list and retry once", and refresh on device-change notifications (**inferred**).
5. **Time-box per-camera describe calls.** Chromium has seen 5 s listings after hot-plug and driver crashes during queries (section 4). Our own `MF_E_REBOOT_REQUIRED` at `ActivateObject` after a vetoed restart would, under list-time activation, break the whole list instead of one camera (**measured**, capture_backends_review §3). Describe each camera separately, with a timeout. A subprocess is a possible way to contain driver crashes (**inferred**).
6. **Keep IDs and order stable** between the light list and the described list, as Chromium does across modes (`4ebcfb5643fb`). Key on the symlink and never on the MF index (**doc** / **inferred**).
7. **IR / depth cameras** need a second `MFEnumDeviceSources` with `KSCATEGORY_SENSOR_CAMERA`, de-duplicated by symlink (L1108-1112) (**doc**).
8. **Cache formats by symlink, and invalidate the cache on arrival or removal.** That is what Chromium's 2013-2020 cache did before the 2020 refactor removed it (**doc**, `86ee59bfe04e` diff of `video_capture_system_impl.cc`).

---

## Sources

### Chromium commits (github.com/chromium/chromium)
- `dce6ab4f3586` 2012-12-04 "Video capture implementation using the Media Foundation API."
- `1ac077eab944` 2013-11-14 "Added video capture capabilities retrieval and caching to VideoCaptureManager." (codereview 29423003)
- `9f8b9b47827f` 2013-12-12 "Added supported formats caching to VideoCaptureManager…" (codereview 91343002)
- `6fc51a48eb77` 2014-01-13 "VCManager: separate in-use and full list of video-capture-device capabilities"
- `b9bc933ef7d7` 2014-01-31 "Add GetDeviceSupportedFormats to VideoCaptureDeviceMFWin"
- `8d5627c41dac` 2017-08-12; `95a2a30ba92d` 2017-09-06 (WebcamMax)
- `3772661191b0` 2018-07-17 "Fallback to DirectShow when MediaFoundation offers no video format"
- `8f68d00946dd` 2018-04-10 "Append DirectShow virtual cameras to MediaFoundation"
- `797e7dd4c4c8` 2020-06-26 "[PTZ] Advertise PTZ support on Windows" (Gerrit 2245473)
- `86ee59bfe04e` 2020-07-25 "Make device enumeration in VideoCaptureDeviceFactory asynchronous." (Gerrit 2306918)
- `77f324ac9dbd` 2020-08-06 "Fix MediaFoundation format enumeration…"
- `c10d6298da6e` 2021-01-22 "Don't include IR cameras in device enumeration by default"
- `4547c21b81c2` 2024-12-13 "Block eBUS DirectShow Source…"
- `b43405d55068` 2026-08-03 "Move camera devices enumeration off the main thread on windows"
- `4ebcfb5643fb` 2026-10-20; `6581c2f839aa` 2026-10-27; `9f7f8bd087a4` 2026-11-03; `326cd9ddfc37` 2026-11-05; `de214cf242fd`, `cd64d78505ca` 2026-11-06
- Files at `main` 9fd83992cfc5: `media/capture/video/win/video_capture_device_factory_win.cc`, `media/capture/video/win/video_capture_device_mf_win.cc`, `media/capture/capture_switches.cc`, `content/browser/renderer_host/media/media_devices_manager.cc`, `chrome/browser/chrome_content_browser_client.cc`, `third_party/blink/public/mojom/mediastream/media_devices.mojom`, `third_party/blink/renderer/modules/mediastream/media_stream_constraints_util_video_device.cc`

### Gerrit (chromium-review.googlesource.com/c/chromium/src/+/N)
- 2245473 (PTZ; reviewer question on querying controls at enumeration), 2306918 (GetDevicesInfo)
- 8163229 (prototype, abandoned; permission-prompt rationale in inline replies), 8564863, 8577359, 8621541, 8628927, 8640669, 8684468, 8688212, 8712184, 8713780, 8763725 (open), 8762274 (open), 8258230 (audio, abandoned)

### Issues (issues.chromium.org; old crbug IDs map to the new IDs shown)
- 565332594 "Windows: Avoid camera activation during device enumeration" (open)
- 309554 → 40337692 "Support video capture device capabilities enumeration on getUserMedia constraints negotiation"
- 1072932 → 40127339 "Refactor VideoCaptureDeviceFactory to enumerate devices asynchronously"
- 934063 → 40614824 "Ability to control connected camera pan / tilt / zoom"
- 1112947 → 40709987 "VideoCaptureDeviceWin uses DSHOW when it should be using media foundation."
- 807293 → 40560541 "Windows (Hello) depth camera streams are not accessible anymore for some cameras (e.g. Realsense D435)"

### Microsoft docs
- Handle the Windows camera privacy setting: https://learn.microsoft.com/en-us/windows/apps/develop/camera/camera-privacy-setting
- Enumerating Video Capture Devices: https://learn.microsoft.com/en-us/windows/win32/medfound/enumerating-video-capture-devices
- IMFActivate::ShutdownObject: https://learn.microsoft.com/en-us/windows/win32/api/mfobjects/nf-mfobjects-imfactivate-shutdownobject
- IMFMediaSource::Shutdown: https://learn.microsoft.com/en-us/windows/win32/api/mfidl/nf-mfidl-imfmediasource-shutdown
- MF_SOURCE_READER_DISCONNECT_MEDIASOURCE_ON_SHUTDOWN: https://learn.microsoft.com/en-us/windows/win32/medfound/mf-source-reader-disconnect-mediasource-on-shutdown

### Other code
- libwebrtc `modules/video_capture/windows/device_info_ds.cc`, `modules/video_capture/device_info_impl.cc` (webrtc.googlesource.com, `main`)
- Firefox `third_party/libwebrtc/modules/video_capture/video_capture_internal_impl_gn/moz.build` (github.com/mozilla-firefox/firefox)
- OBS libdshowcapture `source/dshow-enum.cpp`, `source/dshowcapture.cpp` at `c13d4b7b0c66`

### Web
- web.dev, Control camera pan, tilt, and zoom: https://web.dev/articles/camera-pan-tilt-zoom
- DuckDuckGo privacy test pages, Device Enumeration Chaos: https://privacy-test-pages.site/features/device-enumeration-chaos/
- BleepingComputer, Microsoft tests new privacy controls for Windows 11 desktop apps (2026-08-26): https://www.bleepingcomputer.com/news/microsoft/microsoft-tests-new-privacy-controls-for-windows-11-desktop-apps/
- Help Desk Geek, Windows 11 Insider per-app privacy controls (2026-10-28): https://helpdeskgeek.com/windows-11-insider-per-app-privacy-controls-camera-microphone-location/
- ElevenForum, Camera On/Off OSD indicator: https://www.elevenforum.com/t/enable-or-disable-camera-on-off-osd-indicator-in-windows-11.10774/

### Local
- [windows_results_20261106.md](windows_results_20261106.md) §1 FMT-NOGRAB (activation + `GetNativeMediaType` without `Start`: 29-61 ms, no pipe, no disturbance, works while another process streams)
- [capture_backends_review.md](capture_backends_review.md) (`MF_E_REBOOT_REQUIRED` at `ActivateObject`; re-enumeration after refusals)
