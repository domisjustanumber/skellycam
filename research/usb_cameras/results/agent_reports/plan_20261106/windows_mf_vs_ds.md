# Windows: Media Foundation vs DirectShow for UVC cameras on usbvideo.sys

2026-11-06 · topic `windows_mf_vs_ds` · plan_20261106

Brief: find the best Windows approach for G-ID, G-TS, G-MJPEG and G-CTRL with **no driver change** (no WinUSB/libusbK). Driver *configuration* is reported separately as **tier 1 (one-time admin config)**, against **tier 0 (zero-touch)**.

**Method.** Read-only. No camera was opened, streamed or enumerated through MF, DirectShow (DS), OpenCV, FFmpeg or libusb. The new local evidence is (a) a re-analysis of existing result files and (b) a read-only registry snapshot ([`windows_mf_vs_ds_registry_20261106.txt`](windows_mf_vs_ds_registry_20261106.txt), written by this agent via `Get-ItemProperty` / `Get-PnpDevice -PresentOnly`).

**Labels.** **measured** = a result file in the repo (path given). **doc** = vendor documentation or source code (URL and section). **web** = forum, issue or blog. **inferred** = my reasoning.

---

## 0. Bottom line

1. **Same resolutions. Different list shapes. MF adds decoded types.** For every MJPEG frame descriptor on all four cameras, the frame sizes are identical in the USB descriptors, MF native types and DS `GetStreamCaps` (**measured**).
   - MF lists one native type per (size, discrete interval): C922 120 MJPG = 17 sizes × their intervals, exactly the descriptor set.
   - DS lists one caps entry per frame descriptor, collapsing the discrete intervals into a min–max range (C922 `1280x720@5-60`).
   - MF also inserts a **synthesized NV12 type immediately before every MJPG type** on cameras without native NV12. These are decoded frames, not camera bytes.
2. **Same controls.** Both paths end in the same usbvideo KS property sets (`PROPSETID_VIDCAP_CAMERACONTROL`, `PROPSETID_VIDCAP_VIDEOPROCAMP`, extension-unit nodes). C922 ranges read through the MF source and through the DS filter are identical (**measured**). Where they differ, the cause is OS policy layered on the MF/Frame Server path:
   - Windows 11 Settings default values;
   - multi-app camera mode;
   - share-mode sources;
   - Studio Effects extended controls.
3. **Frame data is equivalent. Failure modes differ** (REPORT finding 28). MF depends on the Frame Server service and blocks in synchronous `ReadSample`. DS bypasses Frame Server on these cameras: the interface CLSID is ksproxy `{17CCA71B-…}`, there is no `EnableDshowRedirection`, and the DShow Bridge app list holds only `Launcher_Main.exe` (**measured**, registry).
4. **UVC PTS/SCR on Windows needs `MetadataBufferSizeInKB0` (tier 1).** No zero-touch route was found. None of the four cameras has the MS-XU or an MS OS 2.0 descriptor, and DS has no documented consumer for the metadata.
   - The value lives on the per-instance **device-interface** key. A serial-less camera that moves port gets a new instance and loses it (**measured** today: the present C930e and generic instances have no value; old instances still carry it).
   - Tier-0 fallback: fit the frame index to the arrival envelope. It scored the same as PTS on the flash floor (REPORT, timestamp table).
5. **The Kiyo Pro problem is probably USB 3 Link Power Management.** Linux added `USB_QUIRK_NO_LPM` for 1532:0E05 in April 2026, because the firmware "fails to respond to control transfers" when LPM is active (**doc**). That matches "stops answering EP0 minutes after plug-in, then 0x8007001F (ERROR_GEN_FAILURE)". On Windows, test it on a USB 2.0 port or cable (no U1/U2), and with the hidden power-plan setting "USB 3 Link Power Management" = Off (tier 1, machine-wide, not a driver change).
6. **Recommendation for the test plan.** Keep MF (`IMFSourceReader`, native type, converters off) as primary, because it is the only route to PTS. Keep DS (PyAV, or a small C++ DS graph) as the per-camera fallback. Decide between them with the open/close-cycle and format/control diff tests in §5, not with soaks.

---

## 1. Do the same controls and formats appear through DS and MF?

### 1.1 Architecture

| Layer | DirectShow | Media Foundation |
| --- | --- | --- |
| Device object | KS proxy filter created from the interface key `CLSID` = `{17CCA71B-ECD7-11D0-B908-00A0C9223196}` (ksproxy.ax). On all 4 cameras on Gerald, in both `KSCATEGORY_CAPTURE {65E8773D…}` and `KSCATEGORY_VIDEO_CAMERA {e5323777…}` (**measured**, registry file). With DShow Bridge opt-in (`EnableDshowRedirection` bit 0x1, Win10 1607+), DS apps get a Frame Server-backed filter instead ([DShow Bridge guidance](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/dshow-bridge-implementation-guidance-for-usb-video-class-devices), "Overview"; **doc**). | `MFEnumDeviceSources` → `IMFActivate::ActivateObject` → `IMFMediaSource`. On Windows 10+ the source is a proxy to the **Windows Camera Frame Server** service, which owns the KS filter (devproxy). Frame Server lets several clients share pins ([DShow Bridge guidance](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/dshow-bridge-implementation-guidance-for-usb-video-class-devices): "FrameServer is a service virtualizing a camera device… Pins from the device to be shared between multiple clients"; **doc**). |
| Format list | Capture pin (plus a still pin when the camera has Method 2/3 still). `IAMStreamConfig::GetNumberOfCapabilities` / `GetStreamCaps` returns one `AM_MEDIA_TYPE` + `VIDEO_STREAM_CONFIG_CAPS` per KS data range. usbvideo makes one data range per UVC frame descriptor, with `MinFrameInterval`/`MaxFrameInterval`. The discrete list comes from `IAMVideoControl::GetFrameRateList(pin, iIndex, size)` ([doc](https://learn.microsoft.com/en-us/windows/win32/api/strmif/nf-strmif-iamvideocontrol-getframeratelist)). | `IMFSourceReader::GetNativeMediaType(stream, i)` or `IMFMediaTypeHandler::GetMediaTypeByIndex`: one `IMFMediaType` per (subtype, size, discrete rate), plus pipeline-added types (below). |
| Controls | `IAMCameraControl`, `IAMVideoProcAmp`, `IKsControl` on the filter. Extension units through `IKsTopologyInfo::CreateNodeInstance` + `IKsControl` with `KSPROPERTY_EXTENSION_UNIT` ([XU plug-in architecture](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/extension-unit-plug-in-architecture); **doc**). | `QueryInterface` the `IMFMediaSource` for the same `IAMCameraControl` / `IAMVideoProcAmp` / `IKsControl`. Chromium does exactly this (`source_.As(&camera_control_)`, [video_capture_device_mf_win.cc](https://raw.githubusercontent.com/chromium/chromium/main/media/capture/video/win/video_capture_device_mf_win.cc) `Init()`; **doc**), and so do this repo's `mf_uvc_timing.cpp:230-231` and `mf_mjpeg_capture.cpp:259-274`. Extended controls (`KSPROPERTYSETID_ExtendedCameraControl`) go through `IMFExtendedCameraController::GetExtendedCameraControl`. usbvideo maps those only from MS-XU controls (UVC 1.5 ext §2.2.2), which none of the four cameras has (**measured**: XU GUIDs in [`naming/descriptors.json`](../../windows/Gerald/naming/descriptors.json) are Logitech/vendor GUIDs only). |

### 1.2 Formats: what the existing data shows

Source files:
- [`results/windows/Gerald/mjpeg_formats/summary.json`](../../windows/Gerald/mjpeg_formats/summary.json) and `mf_list_raw.json` (10-25 run, all 4 cameras incl. Kiyo);
- [`naming/descriptors.json`](../../windows/Gerald/naming/descriptors.json) (descriptor dump via the hub IOCTL).

Re-analysed by this agent:

| Camera | Descriptor MJPEG (sizes × intervals) | MF native MJPG | DS MJPG caps | MF extra types | Sizes MF vs DS |
| --- | --- | --- | --- | --- | --- |
| C922 046D:085C | 17 sizes; 16×7 rates + 1280x720×8 (incl. 60) = 120 | 120 | 17, ranges `5-30` (`1280x720@5-60`) | NV12 ×120, each placed just before its MJPG twin | identical |
| C930e 046D:0843 | 17 sizes × 7 = 119 | 119 | 17, `5-30` | NV12 ×119 | identical |
| Generic 4C4A:4A55 | 5 sizes × {30, 25} = 10 | 10 | 5, `25-30` | NV12 ×10 (camera has no NV12) | identical |
| Kiyo Pro 1532:0E05 | 4 sizes × 7 (5–60) per format; formats YUY2, MJPG, H264, NV12 | 28 | 4, `5-60` | none synthesized (native NV12 exists); H264 listed twice (56, 28 duplicate keys) | identical |

So:
- **The resolution/rate sets agree.** The "120 vs 17" difference is presentation: DS collapses discrete intervals into a range (the local inventory flags this as a `list_formats.py` artefact).
- **DS can be asked for a rate the camera does not offer** (e.g. 45 fps inside `5-60`). What usbvideo then commits is untested (**inferred**; test W-FMT-1c).
- **MF's synthesized NV12 is MJPEG decoded inside the MF capture pipeline** (Frame Server since Windows 10 1607). Reports from 2016 onward describe the effect (**web**: Windows 10 Anniversary Update MJPEG/Frame Server reports, e.g. [Kinovea forum](https://www.kinovea.org/en/forum/viewtopic.php?id=814), [Windows Central](https://www.windowscentral.com/how-fix-webcam-freezing-issue-windows-10-anniversary-update)); no Microsoft page documents it. Because NV12 precedes MJPG at each mode, **a client that takes "first type matching WxH@fps" gets decoded NV12**. skellycam must match the subtype explicitly and verify `GetCurrentMediaType` = MJPG with converters disabled, as `mf_mjpeg_capture.cpp` does (**measured**: [`mjpeg/RESULTS.md`](../../../mjpeg/RESULTS.md) finding 1).
- **Still pin.** The generic camera declares `bStillCaptureMethod 2` with still sizes 1280x720/640x480/320x240; the Logitech cameras and the Kiyo declare 0 (**measured**, descriptors.json). usbvideo exposes a DS still pin for Method 2/3. For MF, a Method 2 camera needs `EnableDependentStillPinCapture` in a *custom INF* ([UVC camera implementation guide](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/uvc-camera-implementation-guide) "Method 2 or Method 3 still capture support"; **doc**), which is a driver-package change. Irrelevant to skellycam's video use, but the stream/pin counts differ between APIs on that camera (**inferred**).

### 1.3 What can make the lists differ (and how to detect it)

| Cause | Effect | Path affected | Source |
| --- | --- | --- | --- |
| Windows 11 Settings › Cameras › **Video rotation** ≠ "No rotation" (external cameras only) | "Windows removes all compressed data types, for example, MJPEG, and H.264, from the camera" | MF/Frame Server. DS untested (**inferred**: DS via ksproxy talks to KS directly, so probably unaffected) | [Camera settings page](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/camera-settings-page) "Adjust video rotation" (**doc**, page dated 2025-10-23) |
| **Multi-app camera** ("Allow multiple apps to use camera", Settings › Cameras › Advanced; Windows 11 26100.3321+, March 2025) | Forces a single media type; basic controls must be set in OS Settings | MF clients | [Windows-Camera #72](https://github.com/microsoft/Windows-Camera/issues/72), Microsoft contributor 2026-02-05 (**web**, first-party staff); [pureinfotech](https://pureinfotech.com/allow-multiple-apps-use-camera-windows-11/) (**web**) |
| **Share-mode source** `MF_DEVSOURCE_ATTRIBUTE_FRAMESERVER_SHARE_MODE=1` (Win11 26100+) | "Sharing mode instances cannot change media types and must use the current media type in use", and cannot change extended controls. Legacy CAMERACONTROL/VIDEOPROCAMP *can* still be changed. | MF | [MF_DEVSOURCE_ATTRIBUTE_FRAMESERVER_SHARE_MODE](https://learn.microsoft.com/en-us/windows/win32/medfound/mf-devsource-attribute-frameserver-share-mode) Remarks (**doc**) |
| `EnableDshowRedirection` bit 0x2 (from device firmware MS OS descriptor or the hardware-key registry) | Frame Server decodes MJPEG once and offers YUY2. Bit 0x1 routes DS apps through Frame Server. | Both (DS only when bridged) | [DShow Bridge guidance](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/dshow-bridge-implementation-guidance-for-usb-video-class-devices) table (**doc**). Not set on any camera here (**measured**, registry file) |
| DShow Bridge per-app list `HKLM\SOFTWARE\Microsoft\OEM\DshowBridge\1` | Bridges named apps only (`Launcher_Main.exe`, Logitech) | DS, those apps | **measured** (registry file); undocumented |
| `HKLM\SOFTWARE\Microsoft\Windows Media Foundation\Platform\EnableFrameServerMode=0` (2016 workaround) | Reportedly makes MF bypass Frame Server | MF, machine-wide | **web** ([Windows Central 2016](https://www.windowscentral.com/how-fix-webcam-freezing-issue-windows-10-anniversary-update)); absent on Gerald (**measured**); effect on current builds unknown |
| Windows Studio Effects (NPU PCs, opt-in, "currently supports front-facing camera") | Composite camera adds extended KS controls (blur, eye contact, framing) | MF and KS clients of that camera | [Studio Effects overview](https://learn.microsoft.com/en-us/windows/apps/develop/windows-integration/studio-effects) "Architecture" (**doc**). Not applicable to external USB webcams today |
| Platform DMFT / OEM Device MFTs (`EnablePlatformDmft`, `CameraDeviceMftCLSIDChain`) | Can add/alter types and controls in MF only | MF | [UVC implementation guide](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/uvc-camera-implementation-guide) "Device MFT Chaining" (**doc**). The Kiyo interface keys carry empty `CameraDeviceMftClsidChain=` / `CameraPostProcessingPluginCLSID=` values (**measured**, registry), so no chain is active |
| MF virtual cameras (`MFCreateVirtualCamera`) vs DS-only virtual cameras | MF lists 8 sources and DS 15 here (OBS, NVIDIA Broadcast, SpoutCam are DS-only); NDI appears in both | Enumeration | **measured** ([mjpeg_formats/summary.json](../../windows/Gerald/mjpeg_formats/summary.json) `dshow_order`/`mf_order`) |

### 1.4 Controls

- **Same values through both paths (measured).** C922 through the **MF source** ([`timing/baseline_nometa_auto/vid_046d_pid_085c_…session.json`](../../windows/Gerald/timing/baseline_nometa_auto/)) and through the **DS filter** ([`mjpeg_msmf/common_1280x720at30_c922/controls.json`](../../windows/Gerald/mjpeg_msmf/common_1280x720at30_c922/controls.json), `--via-dshow`) agree exactly:
  - exposure −11..−2 (default −5);
  - WB 2000–6500 K (default 4000);
  - gain 0–255;
  - focus 0–250 step 5;
  - backlight 0–1.

  The descriptors give the expected control sets: C922/C930e/Kiyo CT 7 + PU 9; generic CT 2 (AE mode, exposure abs) + PU 9 (**measured**, descriptors.json).
- **Windows 11 default-value framework (MF/Frame Server path).** When an app starts the stream, Windows applies the user's Settings defaults for Brightness/Contrast/Sharpness/Saturation/(HDR, effects), unless the app wrote that control after opening but before starting ([Camera settings page](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/camera-settings-page) "How default values apply"; **doc**). Exposure/WB/focus are not in the list. Implication: write every control skellycam cares about after `ActivateObject` and before the first `ReadSample`, then re-read it after the first frame. `IMFCameraControlMonitor` (Win11 22H2+) can catch external writes, and Chromium uses it (**doc**).
- **UVC control persistence.** "UVC controls stick on a device when frame server shuts down"; a later app inherits them unless it writes them ([UVC control cache](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/camera-device-uvc-control-cache); **doc**). Gerald's cameras were left at manual exposure −7 / WB 4500 K by earlier runs (PROGRESS.md), so tests must set and read back every control, never assume defaults.
- **C930e exposure is unreliable on every API** (REPORT finding 11, **measured**), with LogiTuneAgent running throughout. Untested cause candidates: LogiTune writes, AE re-arming at stream start, or firmware.

### 1.5 Concrete ways to compare in a test

See §5, W-FMT-1 and W-CTRL-1. In short: diff three lists per camera (descriptor ↔ MF native ↔ DS caps + `GetFrameRateList`), tagging MF types without a descriptor twin as `synthesized`. Then diff the controls read through MF-source QI, DS-filter QI and raw `IOCTL_KS_PROPERTY` against the descriptor `bmControls`. Repeat under each OS state in §1.3 that can be toggled reversibly (rotation, multi-app, share mode).

---

## 2. `MetadataBufferSizeInKB0`, explained precisely

**What it is.** A REG_DWORD that usbvideo.sys/DevProxy read per video pin: `MetadataBufferSizeInKB<PinIndex>`, PinIndex = 0-based video pin index.

> "If `MetadataBufferSizeInKB<PinIndex>` registry entry is present and nonzero, then custom metadata is supported for that pin and the value indicates the buffer size used for the metadata." ([Microsoft extensions to UVC 1.5](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/uvc-extensions-1-5) §2.2.3; **doc**)

The same section says the Windows 10 design expected "a custom INF for the camera driver… a custom INF is required for the given hardware for metadata to come through". The INF route is a driver-package change, so it is out under the brief. Writing the same value directly into the registry is the tier-1 configuration route that librealsense uses.

**What usbvideo does when it is set.**
- It allocates a per-frame metadata buffer, size = value × 1024 bytes.
- It fills a `KSCAMERA_METADATA_ITEMHEADER { MetadataId = MetadataId_UsbVideoHeader (2), Size }` followed by `KSSTREAM_UVC_METADATA`. That struct holds two `KSSTREAM_UVC_METADATATYPE_TIMESTAMP` records, **StartOfFrameTimestamp** and **EndOfFrameTimestamp**. Each record is `{ULONG PresentationTimeStamp; ULONG SourceClockReference; USHORT SCRToken (11-bit USB SOF counter); …}` (Windows SDK 10.0.22621 `shared/ks.h`; **doc**).
- So usbvideo keeps the PTS/SCR of the **first and last payload headers of each frame**, not every payload. It does not pass through the rest of the header (§2.2.3.3, "a metadata item for the UVC timestamps (generated by UVC driver) followed by firmware-generated metadata items"; **doc**).
- Per-frame size: 8 (item header) + 32 (SDK struct) = 40 B. The doc says "24 bytes" (§2.2.2.9), which disagrees with the SDK header (**doc** vs **doc**; inferred the SDK is authoritative). Any value ≥ 1 is therefore enough for UVC timestamps alone. librealsense and this repo use 5.
- The KS transport is `KSSTREAM_HEADER` with `KSSTREAM_HEADER_OPTIONSF_METADATA` (0x1000) plus a `KSSTREAM_METADATA_INFO { BufferSize, UsedSize, Data, SystemVa, Flags }` (ks.h; **doc**).
- DevProxy turns it into `MFSampleExtension_CaptureMetadata` → `MF_CAPTURE_METADATA_FRAME_RAWSTREAM` on each `IMFSample`, which `mf_uvc_timing.cpp:314-326` parses (**measured**: every C922/C930e frame carried it, REPORT finding 8).
- With `StandardFormatMetadata<PinIndex>=1` (an AddReg value) and a camera whose payload header has HLE > 12, usbvideo also passes firmware MS-standard metadata (§2.2.3.2; **doc**).

**Value meaning and limits.**
- 0 or absent = no metadata. Nonzero = buffer size in KB.
- No maximum is documented (**doc**: none found).
- Firmware metadata must fit within value × 1024 minus the UsbVideoHeader item (§2.2.2.9, for the MS-XU metadata control; **doc**).

**Where it can be set.**

| Location | Used by | Notes |
| --- | --- | --- |
| Device-interface key: `HKLM\SYSTEM\CurrentControlSet\Control\DeviceClasses\{KSCATEGORY_CAPTURE 65E8773D…}` and `\{KSCATEGORY_VIDEO_CAMERA e5323777…}` → `##?#USB#VID_…&MI_00#<instance>#{guid}\#GLOBAL\Device Parameters` | librealsense [`realsense_metadata_win10.ps1`](https://raw.githubusercontent.com/IntelRealSense/librealsense/master/scripts/realsense_metadata_win10.ps1) L47-52, L133, L160-163 (**doc**); this repo `timing/scripts/enable_uvc_metadata.ps1` | Works (**measured**). This is where an INF `[*.Interface.AddReg] HKR,,…` lands (implementation guide INF examples; **inferred**). |
| Hardware key `HKLM\SYSTEM\CurrentControlSet\Enum\USB\<VID&PID>\<inst>\Device Parameters` | Where `EnableDshowRedirection` and `CacheUVCControl` live (**doc**) | Not the documented place for MetadataBufferSize. Untested. |
| Device firmware MS OS 2.0 registry-property descriptor | Works for `EnableDshowRedirection`, `CacheUVCControl`, `UVC-EnablePlatformDmft` (**doc**) | Whether usbvideo copies a metadata value from the BOS is undocumented. Moot: no camera here has an MS OS 2.0 platform capability (Kiyo BOS = USB 2.0 ext + SuperSpeed only; others none; **measured**, descriptors.json). |

**Persistence (measured).**
- The value is per device-interface instance.
- A serial camera keeps its instance across ports: the C922 `8&268DA596&0&0000` still has `=5`.
- Serial-less cameras get a new instance per port. Today's present instances are C930e `6&2206973F&0&0000`, generic `8&232E60D4&0&0000` and Kiyo `A&34494D13&0&0000`. The C930e and generic **lack the value**. Their old instances `8&39DEC205&1&0000` (C930e) and `8&35e81179` (generic, never set) keep stale keys. The Kiyo has three interface instances in the registry, only one with `=5` ([registry file](windows_mf_vs_ds_registry_20261106.txt)).
- Consequence: tier-1 setup must either run "for all registered instances of VID:PID" at install time and again whenever a new instance appears (librealsense: "the script must be executed each time a new RealSense device is attached", [installation_windows.md](https://raw.githubusercontent.com/IntelRealSense/librealsense/master/doc/installation_windows.md); **doc**), or ask users to keep serial-less cameras on fixed ports.

**Restart/replug.**
- Measured procedure: set, then replug (REPORT finding 8).
- A programmatic restart (`pnputil /restart-device`) was vetoed by LogiTune/Razer and left `DN_NEED_RESTART`. MF then failed `ActivateObject` with `MF_E_REBOOT_REQUIRED` (0xC00D7167) for the C922, C930e and Kiyo, while PyAV DS still captured (**measured**: `results/windows/Gerald/timing/registry_enable_metadata.log` shows pnputil exit 50 "Device is pending system reboot"; capture_backends_review §3).
- **Untested:** whether a fresh write takes effect at the next stream start without any restart, e.g. a newly arrived instance written before its first open. This decides whether a background "arm on arrival" helper could make tier 1 near zero-touch after a single install (test W-TS-1b).

**Impact on other apps and on performance.**
- *Memory/CPU.* One extra 1–5 KB buffer per in-flight frame plus a 40 B copy (**inferred**: negligible beside 100–250 kB JPEG frames). librealsense sets 5 KB on every RealSense pin by default (**doc**).
- *Latency.* No documented effect. Not measured here (the C922 metadata-on vs metadata-off rows in the timing data could answer it: **inferred** test W-TS-1d).
- *Frame Server / sharing / DS / browsers / Teams / Zoom.*
  - The metadata is an `IMFSample` attribute; MF clients that do not ask for it ignore it.
  - DS clients get ordinary ksproxy samples.
  - No app in the 10-25 → 11-06 period reported problems with the value set on three cameras (**inferred**; no structured check).
  - The only measured harm is the restart-veto side effect above, which comes from how it was applied, not from the value.
- *Windows Hello / Studio Effects.* Hello uses IR sensor cameras and Studio Effects targets front-facing integrated cameras. Neither applies to these USB webcams (**doc**, Studio Effects overview).

**Is there a zero-touch way to get PTS/SCR on Windows?** None found.

| Candidate | Verdict |
| --- | --- |
| MS-XU metadata control (UVC 1.5 ext §2.2.2.9, mapped to `KSPROPERTY_CAMERACONTROL_EXTENDED_METADATA`) | Needs firmware with the MS-XU (GUID `0F3F95DC-2632-4C4E-92C9-A04782F43BC8`). None of the four cameras has it (**measured**). Even then the docs still describe the registry value for the buffer (**doc**). |
| `MFSampleExtension_DeviceReferenceSystemTime` / sample time | A host QPC time, on the 16 ms grid (REPORT finding 7, **measured**). Chromium reads it (**doc**). |
| `IMFCapturePhotoConfirmation`, `MetadataId_PhotoConfirmation` | Photo stream only; not UVC PTS (**doc**, enum in §2.2.3.1). |
| DS capture pin | ksproxy allocates stream headers without `KSSTREAM_METADATA_INFO`, so no documented route (**inferred**). The existing T5 test in `docs/test_gap_plan.md` should confirm it. A raw KS client (`IOCTL_KS_READ_STREAM` with the metadata option, as DevProxy does) is theoretically possible but needs the same registry value. |
| Windows 11 changes | Nothing found for 24H2/25H2 (web search, 2026-11-06). |
| Tier-0 alternative | Frame-index model fitted to arrival times: same score as PTS at the flash floor (REPORT timestamp table, **measured** on C922/C930e), with start-up handling. The generic camera's accuracy is unmeasured. |

---

## 3. Open/close/open/close reliability: MF vs DS

### 3.1 Local evidence (short runs only)
- **Bandwidth refusal surfaces at different steps (measured).**
  - MF: activate + reader + `SetCurrentMediaType` succeed in 26–71 ms; the first `ReadSample` fails `0x800718CF` (Win32 6351, "camera interface doesn't have the desired bandwidth").
  - DS (PyAV): `OSError(5)` at open ([RERUN_20261027.md](../../windows/Gerald/RERUN_20261027.md) goal 3).
  - A refused start is followed by a zero-frame start, and the next start works (REPORT finding 19, libusb path).
  - After an MF refusal the generic camera was twice transiently `DeviceNotFound` and once re-enumerated ~150 ms after MF released it (**measured**, rerun).
- **Stall (measured).** One MF multi-open batch stalled ~94 s with no progress and was killed. The cause is unknown; synchronous `ReadSample` "blocks until the next sample is available" and has no timeout ([ReadSample](https://learn.microsoft.com/en-us/windows/win32/api/mfreadwrite/nf-mfreadwrite-imfsourcereader-readsample) Remarks; **doc**).
- **Lockout asymmetry (measured).** `MF_E_REBOOT_REQUIRED` blocked MF on three cameras while DS kept working.
- **Camera health (measured).** In 106 MF timing sessions (50,894 frames), errors appeared only in 4 Kiyo sessions. The Kiyo failed on every API with 0x8007001F; `mjpeg_msmf/common_1280x720at30_kiyo/` is INVALID (0 frames).
- **Never tested.** Repeated in-process open/close cycles, cross-API contention (DS holds while MF opens and vice versa), share mode, hot-unplug mid-stream.

### 3.2 Documented / known failure modes

| HRESULT / symptom | Meaning | Where | Source |
| --- | --- | --- | --- |
| `MF_E_HW_MFT_FAILED_START_STREAMING` 0xC00D3704 | "Hardware MFT failed to start streaming due to lack of hardware resources". Chromium: "may indicate that the camera is in use by another application" | MF start | SDK `mferror.h` L820; Chromium `ProcessEventError()` (**doc**) |
| `MF_E_VIDEO_RECORDING_DEVICE_INVALIDATED` 0xC00D3EA2 | "The video recording device is no longer present" (unplug / re-enumeration) | MF mid-stream | `mferror.h` L1210 (**doc**) |
| `MF_E_VIDEO_RECORDING_DEVICE_PREEMPTED` 0xC00D3EA3 | Preempted by another (immersive) app | MF mid-stream | `mferror.h` L1219 (**doc**) |
| `MF_E_REBOOT_REQUIRED` 0xC00D7167 | Devnode has `DN_NEED_RESTART` | MF activate | `mferror.h` L2666; **measured** on Gerald |
| `MF_E_INVALIDREQUEST` 0xC00D36B2 | Undocumented transient on `GetDeviceStreamCount` etc. Chromium retries up to 200 × 50 ms | MF setup | Chromium `ExecuteHresultCallbackWithRetries` (**doc**) |
| `MF_E_SHUTDOWN` 0xC00D3E85 | Using a source after Shutdown. `IMFActivate` caches the source, so a second `ActivateObject` without `ShutdownObject`/`DetachObject` returns the old, possibly shut-down object | MF re-open | [share-mode doc](https://learn.microsoft.com/en-us/windows/win32/medfound/mf-devsource-attribute-frameserver-share-mode) "IMFActivate… will internally cache" (**doc**) |
| Sharing violation | A second *controlling* source becomes active while one is active; any number of share-mode sources may run | MF | share-mode doc (**doc**) |
| `0x800705AA` (ERROR_NO_SYSTEM_RESOURCES) "Run failed" | DS graph Run when the camera is busy or bandwidth is short | DS | [OBS forum 2020](https://obsproject.com/forum/threads/run-failed-0x800705aa-insufficient-system-resources-exist-to-complete-the-requested-service.124531/) (**web**) |
| `ActivateObject` frozen 5–10 min after frequent plug/unplug | Unresolved | MF (Frame Server) | [MS Q&A 2024-07](https://learn.microsoft.com/en-us/answers/questions/1819830/why-does-the-interface-get-stuck-for-5-10-minutes) (**web**) |
| Frame Server (Monitor) crash loops with a C920 | Unresolved (22H2) | MF | [MS Q&A](https://learn.microsoft.com/en-us/answers/questions/4102987/windows-camera-frame-server-monitor-continually-cr) (**web**) |
| 0x8007001F ERROR_GEN_FAILURE "device attached… not functioning" | Kiyo after minutes; matches an EP0 control-transfer stall | all APIs | **measured** (PROGRESS.md); mechanism: Linux commit 8b7a42ec "add NO_LPM quirk for Razer Kiyo Pro webcam" (2026-04-02, Cc stable, Launchpad #2061177): with LPM active the device "fails to respond to control transfers", and the worst case kills the xHCI controller ([mirror](https://tangled.org/tjh.dev/kernel/commit/8b7a42ecdcdeb55580d9345412f7f8fc5aca3f6c); quirk line in [torvalds/linux quirks.c](https://raw.githubusercontent.com/torvalds/linux/master/drivers/usb/core/quirks.c); **doc**) |
| Logitech C922/C930e on Linux | `USB_QUIRK_DELAY_INIT` (slow to initialise after enumeration) | — | quirks.c (**doc**). On Windows, open right after arrival may need a retry (**inferred**) |

### 3.3 Release ordering
- **MF source reader.** By default, releasing a reader created with `MFCreateSourceReaderFromMediaSource` calls `IMFMediaSource::Shutdown`. With `MF_SOURCE_READER_DISCONNECT_MEDIASOURCE_ON_SHUTDOWN=TRUE` the app must call it ([doc](https://learn.microsoft.com/en-us/windows/win32/medfound/mf-source-reader-disconnect-mediasource-on-shutdown)). For the open → close → open cycle, call `IMFActivate::ShutdownObject` (or enumerate afresh), because the activate object caches the source (**doc**). The repo tool already does reader release → `src->Shutdown()` → `act->ShutdownObject()` (`mf_mjpeg_capture.cpp:524-525`).
- **Chromium (IMFCaptureEngine).**
  - Retries `MF_E_INVALIDREQUEST`.
  - Treats `MF_CAPTURE_ENGINE_ERROR` as "capture engine object is no longer valid" and rebuilds it.
  - Defers engine destruction by 5 s (DLL unload cost).
  - Does not wait for `PREVIEW_STOPPED` on stop.
  - Notes that preview-started can be followed by an error when another app holds the device.
  - Has an MF blocklist of ~25 VID:PIDs and appends DS-only devices; no Logitech (046d) or Razer (1532) entry ([factory_win.cc](https://raw.githubusercontent.com/chromium/chromium/main/media/capture/video/win/video_capture_device_factory_win.cc); **doc**).
- **OBS.** Ships DirectShow (`libdshowcapture`) for webcams. Intel's MF source PR [#10471](https://github.com/obsproject/obs-studio/pull/10471) has been open since 2024-04, now milestone 32.2, with changes requested in Aug–Sep 2026 and a crash with Elgato Virtual Camera reported in Oct 2026. A second MF PR, [#12816](https://github.com/obsproject/obs-studio/pull/12816), was closed in Nov 2025 (**web**). So the most-used capture app still trusts DS for webcams.
- **DS teardown.** `IMediaControl::Stop` → release the graph. In this study DS failures appear at open, not mid-stream (**measured**, short runs).

### 3.4 Razer Kiyo Pro and Logitech notes (Windows)
- **Kiyo.** Community threads describe mid-call dropouts fixed only by a replug, firmware updates making it worse or better (1.5.0, 2.3.2 R2), and a USB 2-only bundled cable ([Razer Insider threads](https://insider.razer.com/razer-support-45/razer-kiyo-pro-disconnects-66374); **web**). The Linux LPM quirk gives a testable hypothesis.
  - Run Kiyo tests in two arms: (a) USB 3 port; (b) USB 2.0 port or cable, where U1/U2 cannot occur. Optionally add (c) USB 3 with power plan "USB 3 Link Power Management" = Off (powercfg subgroup `2a737441-1930-4402-8d77-b2bebba308a3`, setting `d4e98f31-5ffe-4ce1-be31-1b38b384c009`, hidden by default; **web**, [Framework KB](https://knowledgebase.frame.work/en_us/my-usb-3-0-device-is-disconnecting-and-reconnecting-ryS3VSvYF)). Tier 1, machine-wide.
  - Record minutes-to-failure from plug-in in each arm.
- **Logitech.**
  - LogiTuneAgent/Updater respawns and vetoes device restarts (**measured**).
  - The C930e PTS is synthetic, with two period modes (REPORT finding 10, provisional).
  - C930e exposure is unreliable (finding 11).
  - Logitech's camera software is on the DShow Bridge list (**measured**, registry).

---

## 4. Third-party dependency picture (Windows capture)

| Route | Maintained by | Status 2026-11 | Risk |
| --- | --- | --- | --- |
| Own C++ MF reader (≈700 lines in repo) via nanobind/pybind11 | us | n/a | Our code; MF is Microsoft's supported path |
| PyAV → FFmpeg `dshow` | PyAV/FFmpeg | PyAV 19.0.2 used here; FFmpeg dshow maintained | DS is "legacy… maintenance mode" (**doc**), no removal date |
| OpenCV `CAP_MSMF` / `CAP_DSHOW` | OpenCV | never returns JPEG bytes (**measured**) | rejected |
| openpnp-capture | upstream v0.0.30 | DS + RGB24 only (**measured**) | rejected |
| GStreamer `mfvideosrc` / SDL3 / nokhwa | third party | native JPEG delivered (**measured**) | heavy deps or format-list quirks |

---

## 5. Windows tests this topic adds to the suite

All tests run under `tools/camlock.py`, with the Kiyo included and health-gated (`timing/src/usb_ep0_probe.cpp` + `kiyo_ks_mf_probe --ks-only` before and after each Kiyo step). Each test logs the `camera_identity.py` key, the devnode status, LastArrivalDate and the §5.0 environment snapshot.

**W-ENV (every run).**
- Windows build/UBR.
- `FrameServer` and `FrameServerMonitor` service state/PID, and restarts during the run.
- Settings: video rotation per camera, the multi-app camera toggle.
- `EnableFrameServerMode`, the DshowBridge list, `EnableDshowRedirection`, `MetadataBufferSizeInKB*` per present instance (the registry dump used for this report).
- LogiTune/Razer Synapse processes.
- USB 3 LPM power setting.
- Port/hub per camera (`win_usb_topology.py --pipes-only --exclude` as needed).

**W-FMT-1. Format-list diff, descriptor ↔ MF ↔ DS.**
- (a) Baseline: descriptor frames × intervals vs `GetNativeMediaType` (tag synthesized types) vs `GetStreamCaps` + `IAMVideoControl::GetFrameRateList` per caps index. Also record stream count/categories (MF) and pin categories (DS, still pin).
- (b) Repeat under: rotation 90° (human, Settings; revert after), multi-app ON, an MF share-mode second instance (Win11 26100+).
- (c) DS: request a non-listed rate inside the range (e.g. 1280x720@45 on the C922) and record the committed `AvgTimePerFrame` and the delivered fps.
- Decides: whether DS and MF expose the same modes, and which OS states silently strip MJPEG. This sets the G-MJPEG health check: "assert subtype MJPG after SetCurrentMediaType and after first frame".

**W-FMT-2. MJPEG at every mode.**
- For every descriptor MJPEG (size, interval), on MF (native, converters off) and PyAV DS (`vcodec=mjpeg`), one camera at a time: 3 s capture.
- Check SOI/EOI, strict libjpeg-turbo decode, SOF dimensions = requested, delivered fps vs requested, MF-vs-DS JPEG-header SHA-1.
- Kiyo: 28 modes; also H264 presence.
- Decides: G-MJPEG "all resolutions", and whether either API fails specific modes (e.g. C922 1280x720@60, Kiyo @60).

**W-CTRL-1. Control-list diff.**
- Every `KSPROPERTY_CAMERACONTROL_*` (0–19) and `KSPROPERTY_VIDEOPROCAMP_*` (0–10): GetRange/Get/caps flags through (i) MF source QI, (ii) DS filter QI, (iii) raw KS IOCTL.
- XU `KSPROPERTY_EXTENSION_UNIT_INFO` through MF-source `IKsControl` and DS node.
- `IMFExtendedCameraController` presence.
- Diff against descriptor `bmControls`. Repeat with multi-app ON and in a share-mode instance.
- Decides: G-CTRL equivalence, and whether MF-only control access is complete.

**W-CTRL-2. Control effect and persistence.**
- Set exposure/WB/focus/gain at three times: (i) after activate before start, (ii) after first frame, (iii) mid-stream. Read back after 1 s and after close/reopen; verify the effect from luma and the flash/step response.
- Arms: Settings defaults changed vs factory; LogiTune running vs stopped (stopping it is tier 1, human-approved).
- Decides: the reliable control-write recipe per API; whether the C930e problem is LogiTune, AE or firmware.

**W-CYC-1. Open/close cycles (core reliability test).**
- K = 50 per camera per API, in-process and process-per-cycle.
- Each cycle: filtered enumerate → activate/bind → set type → first frame (hard 5 s watchdog: async reader or watchdog thread) → 60 frames → close.
- Record per-step HRESULT and latency, re-arrivals, Frame Server PID.
- Variants:
  - (a) MF close order: reader-release-only / +`Shutdown` / +`ShutdownObject` / reuse without `ShutdownObject` (expect `MF_E_SHUTDOWN`);
  - (b) 0 ms vs 500 ms gaps;
  - (c) two cameras on one USB 2.0 hub, staggered and simultaneous, alternating which closes first; expect 0x800718CF / OSError 5, then measure recovery: does the next open of the loser work, zero-frame, or DeviceNotFound;
  - (d) cross-API contention: DS holds, MF opens (expect 0xC00D3704) and vice versa;
  - (e) controlling + share-mode instances;
  - (f) Kiyo in the USB 3 / USB 2 / LPM-off arms, with minutes-since-plug logged.
- Decides: MF-primary vs DS-primary and the fallback triggers; the reliability definition Dom gave (cycles, not soaks).

**W-TS-1. Metadata matrix (tier 1).**
- (a) For each camera: value set/unset × MF/DS → metadata present? PTS/SCR flags? Generic and Kiyo included.
- (b) **Fresh write without restart**: write the value for a present, never-opened instance, then open MF with no replug. Metadata present? Then repeat after a replug.
- (c) Port move of a serial-less camera: confirm the loss and re-arm.
- (d) CPU/latency with metadata on vs off (same camera, same mode).
- Decides: whether tier-1 G-TS can be a one-time install plus arm-on-arrival, and the documented cost to other apps.

**W-TS-2. Tier-0 timestamp quality.**
- With metadata absent: OS sample time vs QPC arrival vs frame-index-fitted envelope, using `analyze_frames.py`/`quantization_check.py`, and the flash ground truth when available.
- Decides: whether tier 0 is acceptable for G-TS on Windows.

**W-TS-3 (= T5 in test_gap_plan).** Can a DS capture-pin client read KS metadata? Decides whether the DS fallback is arrival-time-only.

**Platforms/versions.**
- Windows 11 24H2 (26100) or 25H2 (26200) GA: the share-mode attribute needs 26100 and multi-app needs 26100.3321+.
- Gerald's build 26300 is above 25H2 GA, so results must be reproduced on a GA build (**inferred**).
- Windows 10 22H2 (19045): no Settings camera page, no multi-app or share mode; Frame Server and DShow Bridge since 1607. Consumer ESU was reportedly extended to 2027-10-12 (**web**, [Help Net Security 2026-06-26](https://www.helpnetsecurity.com/2026/06/26/microsoft-windows-10-free-security-updates-esu-program/)).

---

## 6. Open questions
- Does a newly written `MetadataBufferSizeInKB0` apply without a device restart (W-TS-1b)?
- Is the Kiyo failure LPM? USB 2 vs USB 3 vs LPM-off arms (W-CYC-1f).
- Do DS apps see MJPEG when the Settings rotation is set (W-FMT-1b)?
- What does usbvideo commit when DS requests a rate inside the range but not in the discrete list (W-FMT-1c)?
- What caused the ~94 s MF stall: the harness or MF/Frame Server (W-CYC-1 watchdog)?
- Frame Server CPU cost (needs elevation).


---

## Verifier notes

2026-11-06 · adversarial verifier. Read-only: no camera was opened, streamed or enumerated. New local reads: result files, a read-only `DeviceClasses` registry query, and `powercfg /qh` for the USB subgroup. Web: Microsoft Learn pages, Chromium `main` sources, torvalds/linux `quirks.c` plus the commit via the GitHub API, librealsense `master`, OBS PRs via `gh`. Downloads went to the session scratchpad and are not kept in the repo.

### Verdict table

| ID | Verdict | Evidence / correction |
| --- | --- | --- |
| C1 | confirmed | Re-derived from `mjpeg_formats/mf_list_raw.json` and `naming/descriptors.json`: MJPEG (size, interval) sets match exactly (120/119/10/28); the only differences are 1-unit interval rounding (416666 vs 416667). |
| C2 | weakened | MF counts are right. DS is **not** one caps entry per frame descriptor. `dshow_formats_raw.json` has a VideoInfo **and** a VideoInfo2 entry per descriptor: C922 34 MJPG caps (17+17), C930e 34, generic 10, Kiyo 8. `summary.json` dedups them. |
| C3 | confirmed | 120/120, 119/119 and 10/10 MJPG types have an NV12 twin (same size and rate) immediately before them; Kiyo 0/28. On the generic camera NV12 is index 0, so first-match picks decoded NV12. |
| C4 | confirmed | `controls.json` (`--via-dshow`) and the MF `session.json` agree field for field. Note: the Kiyo differs (WB 2000-7500 step 10, exposure default -6; `baseline_nometa_auto` Kiyo session). |
| C5 | confirmed | Camera settings page, "Adjust video rotation" note (ms.date 2025-10-23). The doc says "removes ... from the camera" and does **not** restrict this to MF, so the DS effect really is open. |
| C6 | confirmed | Share-mode doc Remarks (min client Windows 11 build 26100). Add: a controlling source becomes "active" only after `Start` or an extended-control set, so activate/enumerate alone cannot cause a sharing violation. |
| C7 | confirmed (web) | Windows-Camera #72, LPBourret 2026-02-05: "forcing a single MediaType", "OS Settings page for basic camera controls". No build named there, and nothing about DS. 26100.3321 rests only on pureinfotech. |
| C8 | confirmed | "How default values apply to camera applications". This applies only to the basic settings (brightness/EV, contrast, sharpness, saturation, HDR) plus effects and rotation, not exposure/WB/focus. Windows 11 only. |
| C9 | confirmed | UVC control cache page. The same page documents `CacheUVCControl` (HW key; set by MS OS 2.0 descriptor or INF), which persists VIDEOPROCAMP values across reboot/S3. |
| C10 | confirmed | `windows_mf_vs_ds_registry_20261106.txt`. |
| C11 | weakened | Doc bit meanings are right. The implication "lose MJPEG on both APIs" holds only when bits 0x1 **and** 0x2 are both set: DS is bridged only with 0x1. The doc also tells host software to create the value under `Enum\USB\...\Device Parameters`, so an opt-out override there is a tier-1 lever (untested). |
| C12 | weakened | The Windows Central article body could not be retrieved, so its EnableFrameServerMode claim is unverified here. A better source is Stack Overflow a/38936657, which quotes a Microsoft employee: MJPEG/H.264 "decoded / filtered out" was intended. It is still not official documentation. |
| C13 | confirmed | UVC 1.5 ext §2.2.3, plus the opening line "UVC metadata is opt-in ... must be enabled through a custom INF file". |
| C14 | confirmed | The struct is printed in the doc itself (§2.2.3.4.5 MetadataId_USBVideoHeader, not §2.2.3.3). 8+2x16 = 40 B, which matches measured `meta_len` 40. The "24 bytes" figure in §2.2.2.9 is wrong. In the C930e sample frame the SOF and end-of-frame records are identical. |
| C15 | confirmed | SDK 10.0.22621 `shared/ks.h` L2047 `0x00001000`. Frames show `MFSampleExtension_CaptureMetadata`/`MF_CAPTURE_METADATA_FRAME_RAWSTREAM`. |
| C16 | weakened (implication) | Measured: meta_check1 142/142 (C922) and 138/138 (C930e); PROGRESS row. But the C930e PTS is synthetic (REPORT finding 10) and the Kiyo with the value set has 0 frames on record (meta_check1). So "tier-1 G-TS works" is shown for **one** real-PTS camera only. |
| C17 | confirmed | Registry file plus my re-query (only the C922 8&268DA596, Kiyo A&34494D13 and C930e 8&39DEC205&1 carry =5). Caveat: the C930e `&0&` to `&1&` change came from the WinUSB rollback (PROGRESS L16), not a port move. Its current `6&2206973F` is a new parent, which is consistent with a port move. |
| C18 | weakened | `realsense_metadata_win10.ps1` writes KB0 for every device, and KB1-KB3 **only for listed multi-pin devices** (L54-70, L170-186). `install_all` and the "executed each time a new RealSense device is attached" rule are confirmed. The install doc says nothing about a replug or restart after the write. |
| C19 | weakened | The logs give a different sequence. At 14:04:28-44 (`registry_enable_metadata_run1_noop.log`) the script wrote **nothing** to the cameras (it matched ROOT#MEDIA/BTHHFENUM keys and every after= was empty), yet `pnputil /restart-device` returned **3010** ("System reboot is needed") for all three cameras. The exit-50 lines at 14:09 ("pending ... previous operation") show a state that already existed. The LogiTune veto events are logged at 14:11:20-30 (`registry_recover_restart.log`). MF_E_REBOOT_REQUIRED began ~14:04 (`mjpeg_msmf/common_1280x720at30_kiyo/INVALID.txt`). So the restart attempt alone caused DN_NEED_RESTART, independent of the value. |
| C20 | confirmed | `descriptors.json`: no 0F3F95DC XU; BOS null except Kiyo (USB2 ext + SuperSpeed). Add: all four declare **bcdUVC 1.00**. |
| C21 | confirmed | Still untested. The 10-25 C930e re-arm (22:30:17Z write, `metadata_check_c930e_after_rollback` 22:31:56Z, 138/138 with metadata) is **not** evidence for it: the C930e re-arrived at 22:31:14Z (`driver_swap/inspect/20261025T224540Z_baseline_readonly.json`), i.e. there was a replug in between. |
| C22 | weakened | The flash-floor equality is shown for the C922 (REPORT findings 7, 9). The C930e PTS is synthetic. These best scores use a whole-run non-causal fit; causal scores are 0.59-1.13 ms (C922) and 0.61-3.6 ms (C930e). The generic camera is unmeasured. |
| C23 | confirmed | `capture_backends_review.md` L92-93; RERUN L41. |
| C24 | confirmed | RERUN L41, L49, L182; review L96. The 94 s hang was a `run_concurrency` combo, and the harness is a co-suspect. |
| C25 | confirmed | Standard ReadSample remarks: in synchronous mode it blocks until the next sample. |
| C26 | confirmed | The share-mode doc says the cache persists "before a call to DetachObject" (ShutdownObject is not named there). Disconnect-on-shutdown doc as cited. |
| C27 | confirmed | Local SDK `um/mferror.h` L172/820/1210/1219/2666, all values match. |
| C28 | weakened | Confirmed: retry 200x50 ms (L1338-1339, L1119-1133); HW_MFT treated as "in use" (L2617); 5 s deferred destroy (L1368); QI for IAMCameraControl/IAMVideoProcAmp (L1040-1045). **Not** confirmed: "rebuilds after MF_CAPTURE_ENGINE_ERROR". `OnEvent` (L2582) posts `ProcessEventError`, which reports `OnError`; it recreates only the D3D device on DXGI_ERROR_DEVICE_REMOVED. For HW_MFT it starts an `IMFSensorActivityMonitor` to decide whether the camera is in use (L2617-2645). |
| C29 | weakened | `kModelIdsBlockedForMediaFoundation` has 22 VID:PID entries, plus a D3D11 list (2) and a display-name list. It includes a USB webcam (Microsoft LifeCam Studio 045e:0772), so it is not only capture cards and laptops. No 046d or 1532 entry: confirmed. |
| C30 | confirmed (web) | `gh pr view 10471`: OPEN, created 2024-04-02, CHANGES_REQUESTED, Elgato crash comments 2026-10-09. The report body's "milestone 32.2" is wrong: the milestone is now null. #12816 was created and closed on 2025-11-13. |
| C31 | confirmed | Kiyo entry in torvalds master `quirks.c` (L503-504). Commit 8b7a42ec: author date 2026-03-31, committed 2026-04-02, Cc stable, LP #2061177. The mechanism is EPIPE on UVC probe SET_CUR, then an xHCI stop-endpoint timeout. "Minutes after plug-in" is **not** in the commit, so linking it to Gerald's symptom remains inference. |
| C32 | confirmed (now measured) | `powercfg /qh` on Gerald: subgroup 2a737441... "USB settings", setting d4e98f31... "USB 3 Link Power Mangement" [sic], options 0-3. **Current AC and DC index 2 = Moderate power savings.** USB selective suspend is enabled. |
| C33 | refuted (first half) | `timing/baseline_nometa_auto/vid_1532_pid_0e05_mi_00_a_34494d13_0_0000.session.json`: **275 MF frames, 0 errors, 10.0 s at 1280x720@30**. The Kiyo *has* a valid MF capture. The capture_backends_review also records SDL3-over-MF delivering Kiyo MJPEG once. The "errors only in Kiyo sessions" half is confirmed (review L97). |
| C34 | confirmed | `summary.json` dshow_order 15, mf_order 8. |
| C35 | confirmed | `descriptors.json` bStillCaptureMethod 2/0/0/0; the implementation guide is cited. |
| C36 | confirmed | ESU to 2027-10-12 (Help Net Security 2026-06-26, 22H2 Home/Pro/Pro Edu/Workstations). Share-mode min build 26100 per doc. |

### Missed items
- DS caps come in VIH/VIH2 pairs. Format diffs and caps-index selection must dedupe and choose the VIH2 entry deliberately (`dshow_formats_raw.json`).
- Gerald's USB3 LPM is currently **Moderate** on AC and DC. The Kiyo LPM-off arm is therefore a real change on this machine (powercfg, measured 2026-11-06).
- Kiyo control ranges differ from the Logitech ranges (WB to 7500 K step 10). A per-camera range table is needed for G-CTRL (Kiyo baseline session).
- `IMFSensorActivityMonitor` (Chromium L2617-2645) separates "in use by another app" from other start failures. It belongs in the MF error-class mapping and in W-CYC-1(d).
- Share-mode "active" semantics (Start or extended-control write). A cycle test that only activates never collides, so cross-process tests must actually start streams.
- `CacheUVCControl` and an `EnableDshowRedirection` override under `Enum\USB\...\Device Parameters` are further tier-1 registry levers to list beside MetadataBufferSizeInKB (both doc).
- The DN_NEED_RESTART hazard is caused by the restart call itself even when no value changes (run1_noop log). Any tier-1 helper must never call `pnputil /restart-device` or `CM_Query_And_Remove_SubTree`.
- All four cameras are UVC 1.0 (bcdUVC 1.00). Any UVC 1.5-only path (MS-XU, standard metadata) is moot for the whole fleet in hand.

### Corrections to direct answers
- **Q1:** "DS has one caps entry per frame descriptor" becomes two (VideoInfo + VideoInfo2), e.g. C922 34 MJPG caps.
- **Q2:** "A vetoed pnputil restart left DN_NEED_RESTART (exit 50)": the first restart (14:04, before any camera value was written) returned 3010, and the later exit-50 runs reflect that existing state. librealsense writes KB1-3 only for multi-pin devices. The metadata struct is defined in UVC 1.5 ext §2.2.3.4.5 itself.
- **Q3:** Chromium does not rebuild the capture engine on MF_CAPTURE_ENGINE_ERROR; it reports the error, and uses `IMFSensorActivityMonitor` for HW_MFT failures. The Kiyo does have one valid MF capture (275 frames). The Kiyo LPM link is a hypothesis: the commit describes EPIPE on probe SET_CUR, not a delayed onset.
