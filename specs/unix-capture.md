# Linux and macOS native capture specification (V4L2 and AVFoundation)

Status: draft 2 for the user, 2026-11-20. Spec and test list only: no product code and no test code
exist for it. The decisions and rulings of the user that bind it are in
[ADR-22EJ](../decisions/entries/22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md).
The choices of the agent are in
[ADR-AT04](../decisions/entries/AT04-choices-of-the-linux-and-macos-capture-spec.md). Section 9
holds the questions that wait for the user. Draft 2 fixes the 16 findings of an independent review of
draft 1, applies the rulings of the user of 2026-11-20, and takes the names and values of the certify
spec for each key, value, check name and code that certify reads. A later ruling of the same day
accepts seven recommendations of draft 2, computes the V4L2 layout for 32-bit systems too, makes
certify try each macOS approach for exposure and JPEG, and lets the apply request answer before the
exposure search ends. A cross-spec review then made the camera requests spec the owner of the exposure
search, the 60 fps fall back and the USB link lookup, and the certify spec the owner of the check names
and of the record of checked models; this spec now points to them and keeps only what is specific to
V4L2 and AVFoundation. The macOS controls follow the widest working route (4.4.6) [U].

Note of 2026-11-25: section 4.13 and its tests in 6.9 (exclusive access of a camera, the RECORD priority, control
events, the macOS configuration lock and in-use flag) are accepted by the user (Q813, [ADR-5PAR](../decisions/entries/5PAR-decisions-of-the-user-on-the-control-read-the-holder-and-the-exclusive-access-drafts.md)),
[ADR-AA4X](../decisions/entries/AA4X-decisions-of-the-user-on-exclusive-access-of-a-camera.md). They land with
phase 7. Section 4.13.2 reverses M-11.

The user moved this work up on 2026-11-20: "certify runs to validate assumptions about linux and mac
code. Ideally as much real code is implemented as possible now so a single test run provides as much
information as possible and can be used there and then if the tests pass." [U] Thus the native
sources are written now, without a Linux or macOS machine. Each fact that the code relies on is an
assumption of section 2. Each assumption has a run-time check, a diagnostic key and a certify check.
A certify run on a real system then confirms or refutes each one. When a camera model passes the gate
of [cert 11.3] on a system (named checks of a full certify run at the base mode, item 2 of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)),
native capture is used for that model there at once (section 4.9).

## 0. How to read this spec

Marks:

- **[U]**: a decision or ruling of the user ([ADR-22EJ](../decisions/entries/22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md),
  [ADR-SC3Y](../decisions/entries/SC3Y-later-rulings-of-the-user-for-native-capture-on-linux-and-macos.md)).
- **[A]**: a choice of the agent ([ADR-AT04](../decisions/entries/AT04-choices-of-the-linux-and-macos-capture-spec.md)). Section 8 lists each one.
- **[Q n]**: written to the recommendation of question n of section 9. It **waits for the user**.
- **[W x.y]**: section x.y of [`windows-capture.md`](windows-capture.md). **[W Dn]**, **[W Un]**,
  **[W Wn]**: a decision of that spec (its section 20). **[rec x.y]**: [`recorder.md`](recorder.md).
- **[cert x.y]**: section x.y of [`certify.md`](certify.md). The certify spec owns each check name,
  number key, value and reason code that
  certify reads, and the record of checked models `camera_checks.json` [U]. This spec uses them.
  Section 4.6.4 lists what certify must still add.
- **[req x.y]**: section x.y of [`camera-requests.md`](camera-requests.md) (the camera requests spec).
  It owns the exposure search (its
  algorithm, its states and their order, its field and endpoint names, its time limit), the slow-camera
  texts, the 60 fps fall back and the USB link lookup [U]. This spec points to it.
- **[R file]**: a research file on branch `dom/research` (commit 56d2b907d). These files are not on
  this branch. "xplat" is `research/usb_cameras/docs/xplat_capture_plan.md`; "stack" is
  `research/usb_cameras/docs/capture_stack_options_plan.md`; "macctl" is
  `research/usb_cameras/docs/macos_uvc_controls_review.md`; "linuxlib" is
  `research/usb_cameras/suite/linux/linuxlib/v4l2.py`; "mac_avf" is
  `research/usb_cameras/suite/macos/helpers/mac_avf.py`; "plan" is
  `research/NATIVE_JPEG_CAPTURE_PLAN.md`. Each research helper was written on Windows and never ran on
  Linux or macOS hardware [R xplat §2.4, stack §4.2, §4.3].
- **[K n]**: a primary source of section 0.1.
- **[NV]**: not verified. No primary source or measurement proves it. A certify check must observe it.

This spec uses British spelling. Code names are from branch `dom/recorder-connection` at commit
72b939fbb, read on 2026-11-20. "This step" means the work that this spec specifies.

### 0.1 Primary sources

Each source was read on 2026-11-20. The kernel sources are `torvalds/linux` master of that date.

| ID | Source | What this spec takes from it |
|---|---|---|
| K1 | https://docs.kernel.org/userspace-api/media/v4l/buffer.html | `V4L2_BUF_FLAG_ERROR` (0x40); timestamp types (mask 0xE000, MONOTONIC 0x2000 is `CLOCK_MONOTONIC`); sources (mask 0x70000, EOF 0, SOE 0x10000); `sequence` counts dropped frames; `bytesused`. |
| K2 | https://docs.kernel.org/userspace-api/media/v4l/ext-ctrls-camera.html | The order of the `V4L2_CID_EXPOSURE_AUTO` menu; `V4L2_CID_EXPOSURE_ABSOLUTE` in 100 µs units; `V4L2_CID_EXPOSURE_AUTO_PRIORITY` acts only in the auto and aperture-priority modes; focus controls. |
| K3 | https://docs.kernel.org/userspace-api/media/v4l/vidioc-qbuf.html | `VIDIOC_DQBUF` blocks unless `O_NONBLOCK`; then `EAGAIN`; `EIO`. |
| K4 | https://docs.kernel.org/userspace-api/media/v4l/vidioc-streamon.html | Error codes of `STREAMON`; `STREAMOFF` removes all buffers. |
| K5 | https://docs.kernel.org/userspace-api/media/v4l/vidioc-g-fmt.html | `S_FMT` adjusts the values and returns no error for them; `EBUSY` while the device streams or holds buffers. |
| K6 | https://docs.kernel.org/userspace-api/media/v4l/vidioc-reqbufs.html | The granted count can differ; `count = 0` frees the buffers. |
| K7 | https://docs.kernel.org/userspace-api/media/v4l/vidioc-g-parm.html | `timeperframe`: the driver returns the actual period; `V4L2_CAP_TIMEPERFRAME`. |
| K8 | https://raw.githubusercontent.com/torvalds/linux/master/drivers/media/usb/uvc/uvc_video.c | No fast enough alternate setting gives `-EIO`; errors of `usb_set_interface` and of the URB submit come back as they are; the buffer time is `ktime_get()` (monotonic clock parameter) at the frame start; `sequence` increments on each frame start; `UVC_STREAM_ERR` marks the buffer bad; `hwtimestamps` replaces the time with a value from the camera clock on the same base. |
| K9 | https://raw.githubusercontent.com/torvalds/linux/master/drivers/media/usb/uvc/uvc_queue.c | `timestamp_flags = MONOTONIC | TSTAMP_SRC_SOE` (fixed); a bad buffer is requeued unless `nodrop`; after a disconnect a queued buffer comes back with the error state and "the next QBUF call will fail with -ENODEV". |
| K10 | https://raw.githubusercontent.com/torvalds/linux/master/drivers/media/usb/uvc/uvc_driver.c | `clock` default `CLOCK_MONOTONIC`; `nodrop` default 1; `hwtimestamps` default 0; the metadata node has `V4L2_CAP_META_CAPTURE | V4L2_CAP_STREAMING` only; the card name comes from the USB product string; `v4l2_device_register` uses the VideoControl interface. |
| K11 | https://raw.githubusercontent.com/python/cpython/3.13/Modules/fcntlmodule.c | `fcntl.ioctl` releases the GIL for an integer, for a mutable buffer of 1024 bytes or less and for a read-only buffer; it does not retry `EINTR`. |
| K12 | https://docs.python.org/3.13/library/time.html | `perf_counter` uses the clock of `monotonic` (3.13); macOS: `mach_absolute_time()`; else `clock_gettime(CLOCK_MONOTONIC)`. |
| K13 | https://developer.apple.com/tutorials/data/documentation/coremedia/cmclockgethosttimeclock().json | "In macOS, the host time clock uses `mach_absolute_time`". |
| K14 | https://developer.apple.com/tutorials/data/documentation/avfoundation/avcapturesession/synchronizationclock.json | All sample buffer times are on `synchronizationClock`; macOS 12.3 and later. |
| K15 | https://developer.apple.com/tutorials/data/documentation/avfoundation/avcapturevideodataoutput/videosettings.json | "To receive samples in their device-native format, set this value to an empty dictionary"; `nil` gives a default uncompressed format. |
| K16 | https://developer.apple.com/tutorials/data/documentation/avfoundation/avcapturevideodataoutput.md | "This object supports compressed video data output for macOS only." |
| K17 | https://developer.apple.com/tutorials/data/documentation/avfoundation/requesting-authorization-to-capture-and-save-media.json | `NSCameraUsageDescription` and `com.apple.security.device.camera`; without them "the system terminates your app"; `authorizationStatus(for:)`. |
| K18 | https://chromium.googlesource.com/chromium/src/+/main/media/capture/video/apple/video_capture_device_avfoundation.mm | Chromium asks for `kCMVideoCodecType_JPEG_OpenDML` through `kCVPixelBufferPixelFormatTypeKey`, maps it to MJPEG, extracts the sample bytes, converts the PTS with `CMClockConvertHostTimeToSystemUnits`, and falls back to a decoded format for one Logitech model. (Read through a summary of the decoded file; the review could not read it.) |
| K19 | Apple documentation JSON of `AVCaptureDevice`: `exposureMode`, `ExposureMode.custom`, `ExposureMode.locked`, `isExposureModeSupported(_:)`, `setExposureModeCustom(duration:iso:completionHandler:)`, `exposureDuration` | `custom` is listed for macOS 10.15 and later; `setExposureModeCustom` and `exposureDuration` exist only on iOS, iPadOS, Mac Catalyst and tvOS; `locked` and `isExposureModeSupported` exist on macOS. |
| K20 | https://developer.apple.com/forums/thread/791278 | One unanswered report: a UVC MJPEG mode of 1000x6000 does not stream on macOS. |
| K21 | https://pypi.org/pypi/pyobjc-framework-AVFoundation/json and the JSON of `pyobjc-core`, `-Cocoa`, `-Quartz`, `-CoreAudio`, `-CoreMedia`, `-CoreMediaIO`, `-libdispatch` | Each is at 13.0 (2026-10-30, the latest); Python 3.11 and later; cp313 universal2 wheels for macOS 10.13 and later; AVFoundation requires pyobjc-core, CoreMedia, CoreAudio, Cocoa and Quartz. Wheel sizes: core 6.73 MB, Cocoa 392 kB, Quartz 216 kB, AVFoundation 87 kB, CoreAudio 35 kB, CoreMedia 29 kB, CoreMediaIO 17 kB, libdispatch 16 kB. |
| K22 | https://pypi.org/pypi/linuxpy/json | linuxpy 0.25.0 (2026-08-20), GPL-3.0-or-later. |
| K23 | https://github.com/orgs/community/discussions/63910 | On a hosted ubuntu-22.04 runner, `linux-modules-extra-$(uname -r)` for the Azure kernel had no installation candidate. Nothing found for ubuntu-24.04. |
| K24 | https://lkml.iu.edu/hypermail/linux/kernel/2503.3/06002.html | The uvcvideo series "Implement Granular Power Saving" (v6, 2025-03). The kernel release that holds it is not shown. |
| K25 | `uvcvideo.h` and `videobuf2-v4l2.c`, `videobuf2-core.c` of the same tree | `UVC_CTRL_CONTROL_TIMEOUT` and `UVC_CTRL_STREAMING_TIMEOUT` are 5000 ms; `REQBUFS` returns `EBUSY` for a file that does not own the queue; after a queue error `DQBUF` returns `EIO`. |
| K26 | `uvc_v4l2.c` and `uvc_ctrl.c` of the same tree | `S_FMT` runs the probe of `uvc_v4l2_try_format`, then returns `EBUSY` when the queue is busy; inside one `S_EXT_CTRLS` the value of the master (auto) control in the same call decides, and an absolute value with the master not manual gives `EACCES`. |
| K27 | https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/linux/videodev2.h | `v4l2_buffer` holds `struct timeval timestamp` for user space and `struct __kernel_v4l2_timeval` (two `long long`) in the kernel, "the user space version of timeval for 64-bit time_t"; `m.userptr` is `unsigned long`, `m.planes` a pointer; `v4l2_format.fmt` holds `v4l2_window` with pointers; `v4l2_ext_controls.controls` is a pointer; `v4l2_ext_control` and its union are packed. |
| K28 | https://raw.githubusercontent.com/torvalds/linux/master/drivers/media/v4l2-core/v4l2-compat-ioctl32.c and `v4l2-ioctl.c` of the same tree | A 64-bit kernel takes `v4l2_buffer32` (timestamp of two `compat_s64`), "correct for all architectures including i386, but not x32", and `v4l2_buffer32_time32` with `old_timeval32` only with `CONFIG_COMPAT_32BIT_TIME`; a 32-bit kernel translates the `VIDIOC_*_TIME32` numbers only when `!CONFIG_64BIT && CONFIG_COMPAT_32BIT_TIME`. |
| K29 | The macOS approaches list of 2026-11-20 (a research note of this work, not in the repository), with the macOS 26.5 SDK headers that it read (mirror https://github.com/alexey-lysiuk/macos-sdk): `CMIOHardwareControl.h`, `CMIOHardwareStream.h`, `CMIOHardwareDevice.h`, `AVCaptureVideoDataOutput.h`, `AVCaptureFileOutput.h`, `AVCaptureDevice.h`, `IOUSBLib.h` | The approaches A1 to A10 and B1 to B7, their certify checks, the proof rules, the order and the drop rules. `IOUSBLib.h` L1221: "The device does not have to be open to use this function, but standard requests that change the state of the device may require that the device is opened first". The exposure absolute unit of the `xpsr` class is EV in one report; the `shtr` class carries seconds. |

## 1. Purpose, scope, method

### 1.1 Purpose

This step replaces OpenCV capture on Linux with V4L2 through the standard library, and on macOS with
AVFoundation through PyObjC [A, U]. The camera JPEG goes byte-true to the recorder and the JPEG
ring; the shared loop inserts a DHT when the camera sends none [U, rec 4.1]. The sources plug into the
shared loop of [W 5] through the capture interface of [W 4]. The shared changes of section 4.2 apply
to each source, Media Foundation included.

The user stated the aim of the certify runs: "the aim of this is to use certify to test out the native
capture features and see if they work. OpenCV is already fairly proven to work, so no need to test
here." [U] Certify tests the native capture only. The per-camera OpenCV fallback never runs inside
certify [U].

### 1.2 Scope

| Step | Delivers |
|---|---|
| 7s (shared) | The failure code beside the failure text; `diagnostics()` on each source; the source side of the exposure rules of [req 1] (4.5); the restore of the controls at the close; the generic bounded call; the exposure scales; the source selection, which reads the record of checked models [cert 2.5]; the evidence fields; the native detection dispatch (section 4). |
| 7a (Linux) | `skellycam/core/camera/capture/v4l2/`: detection, `camera_id`, `supported_modes`, `V4L2Source` (MJPG, mmap streaming), manual exposure, gain, focus, white balance and power line read (section 4.3). 64-bit and 32-bit userspace: the layout is computed for the host (A-23) [U]. |
| 7b (macOS) | `skellycam/core/camera/capture/avfoundation/`: detection, `camera_id`, `supported_modes`, `AVFoundationSource` (MJPG block buffers if M-5 holds), exposure through CoreMediaIO controls, permission state (section 4.4). macOS 12.3 and later [U]. |

Each step has its own fake-layer tests (section 6). Its hardware validation is a certify run (6.7) [U].

### 1.3 Non-goals

- A compiled extension of our own, Rust, libusb or libuvc [U, R xplat §1]. A driver change, a kernel
  module parameter change or a udev rule [R xplat §1].
- UVC PTS/SCR timestamps and the uvcvideo metadata node: "tier 0 only, no PTS testing" of 2026-11-09
  stays [R plan §2].
- Uncompressed modes (YUY2, NV12) on Linux and macOS. They follow step 3b of Windows [W 13].
- UVC requests on endpoint 0 on macOS in the product [U].
- Hot-unplug tests [U]. The source still maps a removal to `dead` (4.3.8, 4.4.9).
- Modes below 30 fps and modes below the size floor (640 wide and 360 high); any group rate other than one rate
  (30 or 60) for all cameras [U, W U11, W 22.2 U Q887 to Q889].
- H.264 modes [W D4]. The removal of the lockstep gate (phase 8).
- macOS before 12.3 and the x32 ABI of Linux: these systems keep the OpenCV source [U, A].

### 1.4 Method

For each fact that the code needs, this spec gives:

1. The **assumption**: the fact, its source and its confidence (section 2).
2. The **run-time check** in the source: the code checks the fact on each open, where it can.
3. The **diagnostic**: a fixed key of `diagnostics()` that records what the source saw (4.6).
4. The **certify check** that reads the key on a real system [cert 10.2].
5. The **fallback** when the fact is false: a failure with a fixed code, a reduced feature, or the
   OpenCV source outside certify (4.9).

A false assumption must give a clear failure code and a diagnostic, never a wrong frame, a wrong
timestamp or a silent hang [A].

## 2. Assumptions

Each item has: the statement; the source; what breaks if it is false; the run-time check; the
diagnostic keys (4.6); the certify check [cert 10.2] and its reason codes; the confidence (high: a
primary source; medium: a primary source for part, or strong field evidence; low: little evidence).

### 2.1 Linux (V4L2, uvcvideo)

**A-1. The video nodes.** A capture node is a `/dev/videoN` whose `VIDIOC_QUERYCAP` has
`V4L2_CAP_DEVICE_CAPS` in `capabilities` and `V4L2_CAP_VIDEO_CAPTURE` and `V4L2_CAP_STREAMING` in
`device_caps`. uvcvideo makes a second node for each stream with only `V4L2_CAP_META_CAPTURE |
V4L2_CAP_STREAMING` [K10]; detection skips it.
- Confidence: high. If false: a camera shows twice, or a metadata node fails at `S_FMT`.
- Run-time check: detection reads `device_caps` of each node.
- Diagnostics: `nodes_seen`, `nodes_skipped_meta`.
- Certify: `detect`.

**A-2. Identity from sysfs.** `/sys/class/video4linux/videoN/device` is the VideoControl interface
of the camera [K10]; its parent is the USB device with `idVendor`, `idProduct`, `busnum`, `devpath`
(the port chain, for example `2.3`), `speed` and, if the camera has one, `serial`. The `camera_id`
input is `v4l2:serial:<vid>:<pid>:<serial>:<interface>` when the camera has a serial, else
`v4l2:port:<busnum>-<devpath>:<interface>` [A, U]. When two detected cameras give the same serial
input (a firmware fault), both use the port input, and detection logs it; only in that fault case
does the input of one camera depend on the other cameras [A]. The `/dev/v4l/by-id` names collide for
identical cameras with no serial [R xplat §2.6 G-ID]; this spec does not use them.
- Source: sysfs layout [R naming/README.md, unit-tested on a fake tree only] [NV on hardware].
  Confidence: medium.
- If false: no USB IDs (label `nousb-nousb`), or two cameras collide (refused [W D13]).
- Run-time check: detection refuses two equal `camera_id` values [W 7.1].
- Diagnostics: `id_source` (`serial`, `id-path`), `has_serial`. No serial, path or port is in the
  diagnostics [cert 9.4].
- Certify: `<label>:identity:stable` (`id-unstable`), `<label>:identity:unique` (`id-collision`).

**A-3. Virtual cameras.** A v4l2loopback node has the driver name `v4l2 loopback` in `QUERYCAP` and no
USB parent in sysfs [NV]. Detection gives it `virtual: true` [W W5]. A name with "virtual" is virtual
too [W 7.1].
- Confidence: medium. If false: a virtual camera is selectable.
- Certify: `detect` (its count `virtual`).

**A-4. Mode list.** `VIDIOC_ENUM_FMT`, `VIDIOC_ENUM_FRAMESIZES` and `VIDIOC_ENUM_FRAMEINTERVALS` give
the MJPG sizes and their frame intervals; for a UVC frame-based descriptor the types are discrete
[R linuxlib, xplat §2.6] [NV on our cameras]. A discrete interval `n/d` seconds gives `fps_num = d`,
`fps_den = n` [A]. A stepwise or continuous interval range gives only the rates 30000/1001, 30/1 and
60/1 that fall inside it [A].
- Confidence: high. If false: `supported_modes` is empty or wrong.
- Run-time check: the mode choice of [W 7.5]; the read-backs of A-5 and A-6.
- Diagnostics: `modes_listed`, `mjpg_sizes`, `interval_types` (`discrete`, `stepwise`, `mixed`).
- Certify: `<label>:detect`, `<label>:modes:granted:<mode>` (`mode-not-granted`).

**A-5. `S_FMT` can grant another size.** The driver adjusts a request and returns no error [K5]. The
source reads back width, height and pixel format. A difference is a failure, stage `set mode`, code
`no-mode`.
- Confidence: high.
- Diagnostics: `requested_fourcc`, `granted_fourcc`, `requested_w`, `requested_h`, `granted_w`,
  `granted_h` (D-1).
- Certify: `<label>:modes:granted:<mode>`, `<label>:native-jpeg:*`.

**A-6. `S_PARM` sets the rate.** With `V4L2_CAP_TIMEPERFRAME`, `VIDIOC_S_PARM` sets `timeperframe`,
and the driver returns the actual period [K7]. The source calls `S_FMT`, then `S_PARM`, then
`G_PARM`. A rate that is not equal to the chosen mode rate with the relative tolerance of 0.0001
[W D17] is a failure, stage `set mode`, code `no-mode`. 30000/1001 and 30/1 differ by 0.1 %, so a
read-back of one for the other is a failure.
- Confidence: high. The order `S_FMT` then `S_PARM` is the order of the research layer [NV].
- Diagnostics: `requested_fps_num`, `requested_fps_den`, `granted_fps_num`, `granted_fps_den` (D-1).
- Certify: `<label>:rate`, `<label>:modes:granted:<mode>`.

**A-7. MJPG buffers are the camera's JPEG.** uvcvideo copies the payloads of each frame into the
mmap buffer and sets `bytesused` [K8]; it does not decode or re-encode. The source copies
`bytesused` bytes into one `bytes` object and requeues the buffer at once.
- Source: [K8]; [R xplat §2.6 G-MJPEG: "Raw V4L2 mmap is the reference"]. Confidence: high.
- Run-time check: the capture check of the shared loop (`check_jpeg`) [W 5.1 step 5].
- Diagnostics: `delivered` (`jpeg`), `bytesused_equals_payload`, `sha256_00` to `sha256_29` (D-11).
- Certify: `<label>:native-jpeg:*`.

**A-8. Damaged frames carry `V4L2_BUF_FLAG_ERROR`.** With `nodrop=1` (the default [K10]), a frame
with the UVC error bit or a lost packet arrives with the error flag [K1, K8, K9]. On a kernel with
`nodrop=0` the driver drops it, and `sequence` has a gap (A-10). The source sets `driver_error = True`
for a flagged buffer and for `bytesused = 0`; the shared loop then flags the slot `CAPTURE_ERROR`
[W 5.1].
- Confidence: high. The kernel release that changed the default is 6.14 by the research [R xplat
  §2.6] [NV].
- Diagnostics: `error_flag_frames`, `zero_bytes`, `nodrop_param` (from
  `/sys/module/uvcvideo/parameters/nodrop`, or null).
- Certify: `<label>:native-jpeg:*` (`error_flag_frames`).

**A-9. The buffer time is on the clock of `perf_counter_ns`.** uvcvideo stamps each buffer with
`ktime_get()` when the `clock` parameter is `CLOCK_MONOTONIC`, the default, at the first payload of the
frame [K8, K10]. Its flags always say `TIMESTAMP_MONOTONIC | TSTAMP_SRC_SOE` [K9]; "SOE" is a label
only: the time is the arrival of the first payload, not the start of exposure [K8]. CPython 3.13
`perf_counter_ns` on Linux reads `clock_gettime(CLOCK_MONOTONIC)` [K12]. Thus
`sample_ns = tv_sec × 10^9 + tv_usec × 1000` is on the base of `arrival_ns`. With `hwtimestamps=1`
the time comes from the camera clock, mapped to the same base [K8].
- Confidence: high for the base; [NV] for the grain (URB completions, up to about 4 ms
  [R xplat §2.6 G-TS]).
- If false: a root user set `clock` to realtime. The flags still say monotonic [K9].
- Run-time check: the 200 ms rule of [W 4.2] (`NO_SAMPLE_NS` for the rest of the open after a sample
  time later than its arrival or more than 200 ms earlier). A realtime stamp is decades away from the
  monotonic clock, so the rule catches it. The source then sets `clock` to `realtime` when the stamp
  is within 1 s of `time.time_ns()`, else `unknown`.
- Diagnostics: `clock` (`monotonic`, `realtime`, `unknown`), `tstamp_src` (`soe`, `eof`, `unknown`),
  `ts_conversion`, `sample_time_kept`, `sample_minus_arrival_p5_ms`, `_p50_ms`, `_p95_ms`,
  `later_than_arrival`, `clock_param`, `hwtimestamps_param`, `frame_log` (D-2).
- Certify: `<label>:clock:base` (`clock-base-differs`), `<label>:clock:before-arrival`
  (`sample-after-arrival`), `<label>:clock:near-arrival` (`sample-too-early`).

**A-10. `sequence` shows lost frames.** uvcvideo increments `sequence` at each frame start, also for
a frame that it drops [K8, K1]. A gap sets `discontinuity = True` on that frame [W D34].
`source_frame_number` stays the count of dequeued buffers since the open [W D27].
- Confidence: high.
- Diagnostics: `sequence_available` (true), `sequence_gaps`, `sequence_lost`, `discontinuity_flags`,
  the `sequence` column of `frame_log` (D-3).
- Certify: `<label>:sequence` (`sequence-unreliable`).

**A-11. Buffers and the newest frame.** `VIDIOC_REQBUFS` with `count = 4` [A]; the driver can grant
another count [K6]; the source accepts 2 or more. A capture thread dequeues each buffer, copies it,
requeues it and puts the frame into the waiting place of [W 4.3]. Thus the source is a push source,
with `replaced_count` as on Windows [W D26].
- Confidence: high. If fewer than 2 are granted: stage `open`, code `open-failed`.
- Diagnostics: `buffers_requested`, `buffers_granted`.
- Certify: `<label>:opens`.

**A-12. No call waits for a frame without a limit.** The node opens with `O_RDWR | O_NONBLOCK |
O_CLOEXEC`. The capture thread waits in `select.poll` with a timeout of 100 ms [A], then calls
`VIDIOC_DQBUF`; `EAGAIN` means no buffer [K3].
- Confidence: high.
- Diagnostics: `poll_timeouts`.
- Certify: `<label>:opens`, `<label>:cycles`.

**A-13. Blocking ioctls, the GIL and a stuck kernel wait.** `S_FMT`, `S_PARM`, `STREAMON`, `STREAMOFF`,
the control ioctls and `close()` send USB control requests or stop USB transfers, and they can block.
Each such call is a bounded call. uvcvideo gives each control request a timeout of 5000 ms [K25].
`S_FMT`, `S_PARM` and `STREAMON` send two or more requests (probe, then commit). Thus their limit is
11 s; the limit of every other call is 5 s [W 6.6] [A]. A call that runs at the 15 s ready deadline is
not cut short [W 9.3]. `fcntl.ioctl` releases the GIL during the call for a buffer of 1024 bytes or
less [K11]; each struct of this step is 232 bytes or less [R linuxlib]. `fcntl.ioctl` does not retry
`EINTR` [K11]; the source retries an `InterruptedError` at once.
- A thread in an uninterruptible kernel wait cannot be killed until the wait ends. The camera process
  reports the hang, then calls `os._exit` [W 6.6]. The process can stay alive until the kernel call
  returns; the control request timeouts of 5000 ms bound one request [K25].
- The main process does not wait for that exit. "Apply again" for that camera while the old process
  lives gets the failure code `previous-process-alive`, stage `open`, with no open of the node [A].
  The wait of 10 s then a kill of ADR-6EKB item 84 stays.
- Confidence: high for the GIL; medium for the stuck wait.
- Diagnostics: `t_*_ms` (D-6); on a hang `fail_code` `hung` and `call`.
- Certify: `self:hang-100ms:gap` and `self:hang-100ms:hard-end` (the software rule); a real driver hang cannot be made [cert 7].

**A-14. "In use" is `EBUSY` at `REQBUFS` or `S_FMT`.** V4L2 allows more than one open, so `open()`
succeeds while another process streams. `REQBUFS` returns `EBUSY` for a file that does not own the
queue [K25]. `S_FMT` sends a PROBE request to the camera (`uvc_v4l2_try_format`) and returns `EBUSY` only
after it [K26]. Thus the source calls `VIDIOC_REQBUFS` with `count = 0` first [A]: it sends no USB
request and catches a holder that has buffers. A holder that set a format but has no buffers is not
caught there; `S_FMT` then returns `EBUSY` after its PROBE. `EBUSY` at any open step gives the code
`camera-in-use` and the reason "in use by another program" [W D13]. From phase 7 the source also holds the
RECORD priority and watches control events (4.13.1, accepted on 2026-11-25).
- Confidence: high.
- Diagnostics: `busy_call` (`reqbufs`, `s-fmt`, `s-parm`, `streamon`, or null).
- Certify: `<label>:in-use` (`outcome`, `call`); `probe:camera-holders`. The summary item of a model
  whose every unit another program holds is `skipped` with the reason `busy` in the certify format
  1.4.0 [U] [cert 3.4].

**A-15. A USB bandwidth refusal fails `STREAMON`.** uvcvideo returns `EIO` when no alternate setting is
fast enough [K8]. A refusal of the host controller at `usb_set_interface` or at the URB submit comes
back as it is [K8]; the research names `ENOSPC` and `ENOMEM` [R xplat §2.6 G-BW], and `EFBIG` is
possible at the submit [NV for each]. `EIO` also comes from a broken bulk descriptor [K8]. The source
maps `EIO`, `ENOSPC`, `ENOMEM` and `EFBIG` at `STREAMON` to the code `usb-bandwidth` with the reason
"USB bandwidth refused, or a device error (errno <name>)" [A].
- Confidence: medium.
- Diagnostics: `native_code`, `native_domain` (`errno`), `call` (`streamon`); `usb_alt` (A-22).
- Certify: `group:open` (`refusal_signal`, `native_code`, `call`).

**A-16. Access to the node.** A desktop seat gives the user an ACL on `/dev/videoN`; an SSH session
needs the `video` group [R xplat §2.6 L-DESK]. `open()` fails with `EACCES` without access: code
`no-access`, stage `open`. Detection still lists the camera from sysfs, with `modes_read: false` [A].
- Confidence: high for `EACCES`; medium for the seat ACL.
- Diagnostics: `access` (`seat-acl`: access with no `video` group; `video-group`: `os.getgroups()`
  holds the group id of `video`; `root`: effective user id 0; `none`) (D-8).
- Certify: `system:camera-access`.

**A-17. The controls and their ids.** The source uses the control ids of `videodev2.h`, never the
names [R linuxlib]: `V4L2_CID_EXPOSURE_AUTO` (menu), `V4L2_CID_EXPOSURE_ABSOLUTE`, `V4L2_CID_GAIN`,
`V4L2_CID_AUTOGAIN`, `V4L2_CID_FOCUS_ABSOLUTE`, `V4L2_CID_FOCUS_AUTO`, `V4L2_CID_AUTO_WHITE_BALANCE`,
`V4L2_CID_WHITE_BALANCE_TEMPERATURE`, `V4L2_CID_POWER_LINE_FREQUENCY` and
`V4L2_CID_EXPOSURE_AUTO_PRIORITY`. The menu order is AUTO, MANUAL, SHUTTER_PRIORITY,
APERTURE_PRIORITY [K2], that is 0 to 3. UVC cameras often offer only MANUAL (1) and
APERTURE_PRIORITY (3) [NV]. `VIDIOC_QUERY_EXT_CTRL` gives the range, the step, the default and the
flags.
- Manual exposure: one `VIDIOC_S_EXT_CTRLS` with the menu set to MANUAL (1) and the absolute value.
  uvcvideo honours the menu value inside one call whatever the order, and returns `EACCES` for an
  absolute value while the menu is in an auto mode [K26]. The source puts the menu
  first and never sends an absolute value alone in an auto mode.
- `V4L2_CID_EXPOSURE_AUTO_PRIORITY` acts only in the auto modes [K2]. The source reads it and never
  sets it.
- White balance and power line frequency: read only [W D43, D44]. Gain and focus: set (4.3.5).
- Confidence: high.
- If false: `control-failed` with the errno; the camera keeps its earlier values [W U14].
- Diagnostics: the control keys of D-4 (4.6.2); `ae_off_ok`, `af_off_ok`, `ae_back_on_after_s`.
- Certify: `<label>:controls`, `<label>:settings-stick:*`, `<label>:auto-off:*`.

**A-18. The exposure unit map.** skellycam keeps the unit of today: a power of two in seconds
[W D35]. `exposure_time_absolute` is in units of 100 µs [K2]. The map is
`native = clamp(floor(2^v × 10000 + 0.5), min, max)`, rounded to the step of the control from its
minimum; the read-back is `v = round(log2(native / 10000))` [A].

| v (log2 s) | Exposure | Native (100 µs) | Error |
|---|---|---|---|
| -12 | 0.244 ms | 2 (3 when the minimum is 3) | -18 % (+23 %) |
| -11 | 0.488 ms | 5 | +2.4 % |
| -10 | 0.977 ms | 10 | +2.4 % |
| -9 | 1.95 ms | 20 | +2.4 % |
| -8 | 3.91 ms | 39 | -0.16 % |
| -7 | 7.81 ms | 78 | -0.16 % |
| -6 | 15.6 ms | 156 | -0.16 % |
| -5 | 31.25 ms | 313 | +0.16 % |

The read-back of each set compares the native value that was sent after the clamp with the value
read. The status reports the log2 value (an int [W 8.4]); the diagnostics hold the native value.
- Source: [K2]; the minimum of 3 is the C922 value of the research [NV]. Confidence: high.
- Diagnostics: `exposure_unit` (`100us`), `exposure_native_at_m7` (78), `exposure_value`,
  `exposure_min`, `exposure_max`, `exposure_step`.
- Certify: `<label>:controls:exposure-scale` (`unit-mapping`), `<label>:settings-stick:*`,
  `<label>:exposure:<base>`.

**A-19. A read-back can come from the cache.** uvcvideo can answer `G_EXT_CTRLS` from its cache
[R xplat §2.6 G-CTRL]. A read-back proves that the driver took the value, not that the camera uses it.
- Confidence: medium. Run-time check: none.
- Certify: `<label>:settings-stick:image-effect` (`no-image-effect`).

**A-20. Controls hold while the stream runs.** The source sets the controls after the first frame
[W D20] and keeps the node open and streaming. A camera can lose its controls after an autosuspend
when no file holds it [R xplat §2.6] [K24] [NV for the release]. The source never sets a control on a
camera that does not stream; the restore of 4.7 runs before `STREAMOFF` [A].
- Confidence: medium.
- Diagnostics: `<control>_before`, `<control>_value`.
- Certify: `<label>:settings-stick:holds` (`setting-reverted`), `<label>:settings-stick:each-open`
  (`setting-lost-on-reopen`).

**A-21. Close and reopen.** `STREAMOFF`, `munmap` and `close()` release the camera in under 1 s, and a
reopen at once works [NV]. The Kiyo Pro needs the USB `NO_LPM` quirk of kernel 7.0 and of the stable
kernels 6.12.81, 6.18.34 and 6.19.12 [R xplat §2.6] [NV].
- Confidence: low.
- Diagnostics: `t_close_ms`, `kernel` (`major.minor`).
- Certify: `<label>:cycles` (it holds the open and close times), `system:kernel`.

**A-22. The alternate setting.** The USB link label comes from the lookup of [req 3.4] with the
values of [req 3.2] (`"USB 1"`, `"USB 2"`, `"USB 3"`, `"unknown"`) [U]; this spec has no second lookup.
The source reads only the granted alternate setting. The node's `device` link is the VideoControl
interface [K10], whose alternate setting is always 0. The granted alternate setting is
`bAlternateSetting` of the VideoStreaming interface: a sibling under the same USB device with
`bInterfaceClass` 0e and `bInterfaceSubClass` 02, read after `STREAMON` [A]. When the function has two
or more VideoStreaming interfaces, the source takes the one with a non-zero value; with two non-zero
values, `usb_alt` is null [A].
- Confidence: medium.
- Diagnostics: `usb_alt` (D-9).
- Certify: `group:open`, `system:usb`.

**A-23. The binary layout is computed for the host.** `abi.py` builds each struct with
`ctypes.Structure` from the C types of `videodev2.h`, and each ioctl number with the `_IOC` arithmetic
from `ctypes.sizeof` of its struct [U]. The builder takes an ABI description: the size of a pointer,
the size of a `long` and the alignment of a 64-bit integer [A]. At run time the description is that of
the host, measured with `ctypes` (`sizeof(c_void_p)`, `sizeof(c_long)`, `alignment(c_int64)`); a test
passes the descriptions of other systems. For a pointer or `long` of 4 bytes the builder uses
`c_uint32` stand-ins, and for a 64-bit alignment of 4 it sets `_pack_ = 4`. Thus the layout and the
numbers follow the C ABI of the system that runs the code [A]:
- `v4l2_buffer.timestamp` has the 64-bit time layout: two 64-bit integers, as
  `__kernel_v4l2_timeval` "for 64-bit time_t" [K27]. On LP64 this is the `struct timeval` of today.
  On a 32-bit userspace it is the layout of a program built with a 64-bit `time_t`, which uses the
  standard ioctl numbers [K27]. The source never uses the old 32-bit `timeval` layout and its
  `_TIME32` numbers: a 32-bit kernel translates those only with `CONFIG_COMPAT_32BIT_TIME`, and a
  64-bit kernel takes the 64-bit time layout of a 32-bit program as `v4l2_buffer32` (two
  `compat_s64`), "correct for all architectures including i386, but not x32" [K28].
- `m.userptr` is an `unsigned long` and `m.planes` a pointer [K27]: 4 bytes on a 32-bit userspace.
- `v4l2_format.fmt` holds `struct v4l2_window`, which has pointers [K27]; the ctypes union holds a
  `c_void_p` member, so that `fmt` gets the alignment of a pointer (offset 8 on LP64, 4 on ILP32).
- `v4l2_ext_controls.controls` is a pointer (`c_void_p`); `v4l2_ext_control` and its union are
  packed [K27, K28].
- The alignment of a 64-bit integer differs: 8 on 32-bit arm (EABI), 4 on i386. `ctypes` takes it from
  the host [A]. By this arithmetic `v4l2_buffer` is 88 bytes on LP64 (`VIDIOC_DQBUF` 0xC0585611), 80
  bytes on 32-bit arm (0xC0505611) and 76 bytes on i386 (0xC04C5611) [NV for the 32-bit values].
- The research layer (linuxlib) fixes LP64 with `u64` stand-ins for the pointers; the port replaces
  them with `c_void_p` and `c_ulong` [A].
- The x32 ABI of x86_64 has other alignment rules [K28]. Native detection refuses there (a 4-byte
  pointer on an x86_64 machine): the native backend is missing, and the OpenCV source is used [A].
- A 32-bit userspace needs kernel 5.6 or later: the 64-bit time layout of `v4l2_buffer` for a 32-bit
  program and the `_TIME32` translation came with that release [R cross-spec review §5 item 4] [NV
  against the kernel history]. On ILP32 with an older kernel, native detection refuses
  (`backend-missing`) [A].
- A 32-bit system is unverified, as any system: it keeps the OpenCV source until a certify run passes
  there (4.9) [U]. The local record and the evidence key hold the ABI (`lp64`, `ilp32`) [A].
- Confidence: high for LP64; medium for 32-bit.
- Certify: `detect` (`backend-missing` on x32), and the camera checks on a 32-bit system.

**A-24. Spawned processes and file handles.** Camera processes use `spawn` [U]. The node opens with
`O_CLOEXEC`, so no child inherits it. Confidence: high.

### 2.2 macOS (AVFoundation, CoreMediaIO)

**M-1. Enumeration.** `AVCaptureDeviceDiscoverySession` with the device types `external` and
`builtInWideAngleCamera` (and `continuityCamera` where present) and the media type video lists the
cameras, with no camera permission [R mac_avf] [NV].
- Confidence: medium. If false: detection is empty until permission is granted.
- Diagnostics: `tcc`; `nodes_seen`.
- Certify: `detect`, `system:camera-access`.

**M-2. Identity.** For a USB camera, `uniqueID` is the hex form of `locationID << 32 | VID << 16 |
PID`; it holds the port [R xplat §2.5 item 4] [NV]. The `camera_id` input is `avf:` plus the
lower-case `uniqueID` [A, U]. VID and PID come from `uniqueID`, else from `modelID` [R mac_avf]
[NV]. A built-in or Continuity camera has no USB IDs.
- Confidence: medium.
- Diagnostics: `id_source` (`unique-id`), `has_serial` (false: AVFoundation gives no serial).
- Certify: `<label>:identity:stable`, `<label>:identity:unique`.

**M-3. Virtual cameras.** A virtual camera has a `transportType` that is not USB, or a name with
"virtual" [W 7.1] [NV for the transport value]. A built-in or Continuity camera is real.
- Confidence: low. Certify: `detect` (its count `virtual`).

**M-4. Mode list.** Each `AVCaptureDeviceFormat` has a media subtype, the dimensions and
`videoSupportedFrameRateRanges`. An MJPG mode of a UVC camera has the subtype `'dmb1'`
(`kCMVideoCodecType_JPEG_OpenDML`) [K18]. A range whose minimum and maximum rates are equal gives its
exact `minFrameDuration` `v/t` as `fps_num = t`, `fps_den = v` [A]. A range with a lower minimum than
maximum gives the rates 30000/1001, 30/1 and 60/1 that fall inside it, as A-4 does [A]; the source
then sets that exact frame duration. One third-party run saw the MJPG modes offered only as decoded
`'420v'` [R stack §4.3] [NV].
- Confidence: medium.
- Diagnostics: `modes_listed`, `mjpg_sizes`, `subtypes` (a fixed string of the FourCCs seen).
- Certify: `<label>:detect`, `<label>:modes:granted:<mode>`.

**M-5. The camera JPEG arrives in a block buffer (the gating question).** With `videoSettings = {}`
the output gives "samples in their device-native format" [K15]; compressed output exists on macOS
only [K16]. Chromium asks for `'dmb1'` through `kCVPixelBufferPixelFormatTypeKey` and reads the bytes
of each sample as MJPEG [K18]. Thus a sample of a `'dmb1'` format has a `CMBlockBuffer` with the JPEG
and no `CVPixelBuffer` [NV]. Whether these are the camera's bytes, or a JPEG that Apple's UVC camera
extension made again, no source shows [NV].
- Confidence: low to medium. This is the largest risk (7.3, risk 1).
- Run-time check on the first sample of each open: `CMSampleBufferGetImageBuffer` is null,
  `CMSampleBufferGetDataBuffer` is not null, the subtype is `'dmb1'`, and the bytes start with
  `FF D8`: `delivered = jpeg`. A pixel buffer: `delivered = decoded`. The source tries the variants
  `empty` and `dmb1` (4.4.3).
- Diagnostics: `delivered`, `video_settings` (`empty`, `dmb1`), `bytesused_equals_payload`,
  `sha256_00` to `sha256_29`, `dqt_sha256` (D-1, D-11).
- Certify: `<label>:native-jpeg:*`. Byte-true is shown only by the DQT and DHT proof rules of 4.4.10:
  `dqt_sha256` equals the value of the same model on Windows or Linux in the evidence file
  [cert 11.2], or `dht_present` is false for a model with no DHT, and the DQT differs from Apple's
  encoder (B4) [A, K29].
- Certify also tries each other approach of 4.4.10 as a probe [U].

**M-6. Session order, mode and rate.** The session preset is applied when the input is added [NV]. Thus the order is: `beginConfiguration`; `addInput`; `addOutput`;
`lockForConfiguration` of the device; `activeFormat`; `activeVideoMinFrameDuration` and
`activeVideoMaxFrameDuration` set to the chosen exact duration; `commitConfiguration`; `startRunning`
while the device lock is held; then `unlockForConfiguration` [R mac_avf header] [A]. Each later
`startRunning` (the variant restart of 4.4.3) takes the lock again in the same way. The source reads
back `activeFormat` and `activeVideoMinFrameDuration`; a difference is stage `set mode`, code
`no-mode`.
- Confidence: medium.
- Diagnostics: the keys of D-1.
- Certify: `<label>:opens`, `<label>:rate`, `<label>:modes:granted:<mode>`.

**M-7. Threads and the run loop.** The sample delegate runs on a serial dispatch queue that the
source makes (`dispatch_queue_create`). Sample delivery needs no main run loop. AVFoundation
notifications come through `addObserverForName:object:queue:usingBlock:` with an
`NSOperationQueue`. CoreMediaIO sends its notifications on the main run loop unless
`kCMIOHardwarePropertyRunLoop` is set to NULL [NV]. A spawned child runs no main run loop,
so `PyObjCLayer.__init__` sets that property to NULL before any other CoreMediaIO call [A]. Each of
these facts is [NV] in a spawned child with no `NSApplication`.
- Confidence: low to medium.
- If false: no frame (`first-frame-timeout`), or no removal event (then the 2 s stall rule [W 9.5]).
- Diagnostics: `t_first_frame_ms`, `notifications_seen`.
- Certify: `<label>:opens`.

**M-8. PyObjC releases the GIL during an Objective-C call.** A blocked `startRunning`, `stopRunning`
or `lockForConfiguration` must not stop the other threads of the camera process, or the bounded calls
and the 100 ms rule fail [U, W 6.6] [NV].
- Confidence: medium.
- If false: a hung call stops the camera process, and its camera holds the gate until the stall watch
  of the main process [U].
- Certify: `self:hang-100ms:gap` and `self:hang-100ms:hard-end`; T-UNX-84 checks the GIL release on the macOS runner.

**M-9. The sample time is host time on the clock of `perf_counter_ns`.** Each sample time is on
`synchronizationClock` [K14]. The host time clock uses `mach_absolute_time` [K13], and so does
`perf_counter` [K12]. The source converts each PTS: when the sync clock is not the host clock, first
`CMSyncConvertTime(pts, syncClock, CMClockGetHostTimeClock())`; then
`CMClockConvertHostTimeToSystemUnits` to mach units, as Chromium does [K18]; then the timebase of
`mach_timebase_info` to nanoseconds, the base of `perf_counter_ns` [A]. Whether the PTS is the host
time at arrival or a time from the camera clock is not known [R xplat §2.5 item 3] [NV].
- Confidence: medium for the base; low for its meaning.
- If false: the 200 ms rule of [W 4.2] gives `NO_SAMPLE_NS`.
- Diagnostics: `clock` (`host` when the sync clock is the host clock, else `device`), `tstamp_src`
  (`unknown`), `ts_conversion`, `sync_clock_is_host`, `sample_time_kept`,
  `sample_minus_arrival_p5_ms`, `_p50_ms`, `_p95_ms`, `later_than_arrival`, `frame_log` (D-2).
- Certify: `<label>:clock:*`.

**M-10. Drops are visible.** `captureOutput:didDropSampleBuffer:fromConnection:` comes for each frame
that AVFoundation drops (`alwaysDiscardsLateVideoFrames` is true) [NV]. `CMIOSampleBufferGetSequenceNumber`
gives a sequence number for each sample [R mac_avf] [NV]. A drop or a sequence gap sets
`discontinuity = True` on the next frame [W D34].
- Confidence: low to medium.
- Diagnostics: `drops_reported`, `sequence_available`, `sequence_gaps`, `sequence_lost`,
  `discontinuity_flags` (D-3).
- Certify: `<label>:sequence` (`not-run` with `no-sequence` when `sequence_available` is false). Then
  the sequence check does not block the gate: `<label>:time-gaps` judges the gaps from the arrival
  times [cert 10.2, 11.3] [ADR-H0BQ](../decisions/entries/H0BQ-user-rulings-of-the-spec-integration.md).

**M-11. Another app can use the camera at the same time.** Reversed on 2026-11-25 (Q787 of
[ADR-AA4X](../decisions/entries/AA4X-decisions-of-the-user-on-exclusive-access-of-a-camera.md)): 4.13.2 replaces
the rule "the source never fails for sharing alone" below. The text of the draft stays for the record. macOS lets
two processes stream one camera [NV]. The other app can change the active format [NV]. The source never fails for sharing alone. It
checks the dimensions of the format description of each sample against the opened mode; a change
gives the failure code `format-changed`, stage `streaming` [A]. `AVErrorDeviceInUseByAnotherApplication`
gives `camera-in-use` [NV that macOS returns it].
- Confidence: low.
- Diagnostics: `format_changes`.
- Certify: `<label>:in-use` (`outcome` `shared` or `refused`).

**M-12. Errors and removal.** `AVCaptureSessionRuntimeErrorNotification` carries an `NSError` in
`AVCaptureSessionErrorKey`. `AVCaptureDeviceWasDisconnectedNotification` reports a removal. The source
maps an error by its `AVError` name, read from the PyObjC constants, never from a number in the code
[A] [NV for which names exist on macOS].
- Confidence: medium.
- Diagnostics: `fail_code`, `native_code`, `native_domain` (`nserror`), `call`.
- Certify: the in-use check sees the error path; no unplug test [U].

**M-13. A USB bandwidth refusal has no documented signal.** It can be a runtime error, a session with
no frame, or a low rate [R xplat §2.5 item 6]. The source gives `first-frame-timeout`, or the rate
check fails; it cannot tell bandwidth from another cause [A].
- Confidence: low.
- Certify: `group:open` (`refusal_signal` `zero-frames` or `low-rate`).

**M-14. Camera permission.** `AVCaptureDevice.authorizationStatus(for: .video)` gives `notDetermined`,
`restricted`, `denied` or `authorized` [K17] (0 to 3 in the header [NV against a page]). A process
without permission gets zero frames and no error [R xplat §2.5 item 5] [NV]. The source reads the
status before each open. Any value other than `authorized` gives the code `no-permission`, stage
`open`, reason "camera permission is <status>". The source never calls `requestAccess`; the app asks
(`askForMediaAccess('camera')` in `skellycam-ui/electron/main/index.ts`). The packaged app already has
`NSCameraUsageDescription` and `com.apple.security.device.camera` (`skellycam-ui/electron-builder.json`,
`skellycam-ui/entitlements.mac.plist`), which Apple requires [K17]. The permission belongs to the app
that starts the process [R xplat §2.5 item 5] [NV].
- Confidence: medium.
- Diagnostics: `tcc` (`granted`, `denied`, `restricted`, `not-determined`) (D-8).
- Certify: `system:camera-access`.

**M-15. Controls.** On macOS, `AVCaptureDevice.ExposureMode.custom` is listed (macOS 10.15 and
later), but `setExposureModeCustom` and `exposureDuration` do not exist there [K19]. Thus AVFoundation
cannot set an exposure value on macOS; it can lock the current exposure (`locked`, after
`isExposureModeSupported(.locked)`) [K19]. Values are possible only through CoreMediaIO feature
controls (a public API, through Apple's own driver) or UVC class requests on endpoint 0 [R macctl §1,
K29]. A device request with no open is documented for requests that do not change the state of the
device as a standard request does (`IOUSBLib.h`, [K29]). CoreMediaIO coverage on our four cameras is
not known; one report needed undocumented control classes [R macctl §1, §3 R1] [NV].
- The user ruled: "I want to use the widest/best supported route for camera control and prefer that
  over the measurement units for exposure. So if the method that uses EV is better than the one that
  uses seconds, I'd take that." [U] This replaces the rule of the earlier commits "exposure only where
  the control gives seconds".
- Thus A1 (`NativeValue`), A2 (`AbsoluteValue`, in any unit, EV included) and A3 (`NativeData` on the
  `uc**` classes) are the candidate product routes for exposure, gain and focus [U]. The route of each
  control of a model is chosen by 4.4.6. Endpoint 0 (A5, A6) and the exclusive opens (A7, A8) stay
  certify probes [U].
- A camera with no working route for exposure has no manual exposure: no Manual, no Auto and no
  exposure control in native capture; the camera keeps the exposure that macOS gives it; the warning
  `no_manual_exposure` says so (4.5) [U].
- Confidence: low.
- Diagnostics: `control_path` (`cmio-native`, `cmio-absolute`, `cmio-native-data`, `none`),
  `exposure_unit` (`seconds`, `ev`, `native`, `native-data`, `none`), `<c>_route_proven`, the set and
  get return codes (`native_domain` `osstatus`) (D-4).
- Certify: `<label>:controls`, `<label>:settings-stick:*`, and the probes
  `probe:<model>:a1-cmio-native:<control>`, `a2-cmio-absolute:<control>`,
  `a3-cmio-native-data:<control>`, `a5-ep0-interface:<control>`, `a6-ep0-device:<control>`
  [cert 10.7].

**M-16. Video effects.** Center Stage, Portrait, Studio Light and Reactions change the frames, and
AVFoundation reports them; Edge Light (macOS 26.2 and later) is not reported [R xplat §2.5 item 5].
The source reads the flags at the open and does not change them [A].
- Confidence: medium.
- Diagnostics: `center_stage`, `portrait`, `studio_light`, `reactions` (booleans or null),
  `edge_light` (always null) (D-8).
- Certify: `system:video-effects`.

**M-17. Close.** The observers are removed, the delegate is set to nil, the restore of 4.7 runs,
`stopRunning`, then the input and the output are removed and the objects released. Each step is
bounded. The close takes under 1 s [NV].
- Confidence: low. Diagnostics: `t_close_ms`. Certify: `<label>:cycles`.

**M-18. The USB link.** The label comes from the lookup of [req 3.4] [U]. `usb_alt` is null on
macOS.

**M-19. macOS 12.3 and later.** `synchronizationClock` needs macOS 12.3 [K14]; the PyObjC wheels allow
macOS 10.13 [K21]. Native detection refuses on an older macOS: the native backend is missing, and the
OpenCV source is used [U]. No `masterClock` fallback is written [A].
- Confidence: high. Certify: `detect` (`backend-missing`).

**M-20. PyObjC in the frozen app.** PyInstaller 6.22.3 collects the PyObjC frameworks that the source
imports [NV]. T-UNX-88 finds a gap; then `skellycam.spec` adds hidden imports on macOS only.
- Confidence: medium. Certify: `detect` (`backend-missing`).

### 2.3 Assumption summary

| ID | Short statement | Conf. | Certify check |
|---|---|---|---|
| A-1 | Capture nodes by `device_caps`; metadata nodes skipped | high | `detect` |
| A-2 | Identity: serial, else port chain from sysfs; by-id not used | med | `<label>:identity:*` |
| A-3 | v4l2loopback: no USB parent, driver name | med | `detect` (its count `virtual`) |
| A-4 | ENUM ioctls give discrete MJPG sizes and intervals | high | `<label>:detect`, `<label>:modes:granted:*` |
| A-5 | `S_FMT` can grant another size; read back | high | `<label>:modes:granted:*`, `<label>:native-jpeg:*` |
| A-6 | `S_PARM` sets the rate; read back with tolerance 0.0001 | high | `<label>:rate`, `<label>:modes:granted:*` |
| A-7 | mmap MJPG buffers are the camera's bytes | high | `<label>:native-jpeg:*` |
| A-8 | Damaged frames carry `V4L2_BUF_FLAG_ERROR` (nodrop) | high | `<label>:native-jpeg:*` |
| A-9 | Buffer time is `CLOCK_MONOTONIC`, the base of `perf_counter_ns` | high (grain NV) | `<label>:clock:*` |
| A-10 | `sequence` gaps show lost frames | high | `<label>:sequence` |
| A-11 | 4 mmap buffers; push source with the newest frame | high | `<label>:opens` |
| A-12 | `O_NONBLOCK` and `poll`: no unbounded wait for a frame | high | `<label>:cycles` |
| A-13 | Blocking ioctls bounded (11 s for probe and commit, else 5 s); GIL released | high / med | `self:hang-100ms:gap` and `self:hang-100ms:hard-end` |
| A-14 | In use is `EBUSY` at `REQBUFS(0)` or after the PROBE of `S_FMT`; the RECORD priority and control events (4.13.1) | high | `<label>:in-use`, `<label>:in-use-mid-take` |
| A-15 | Bandwidth refusal is `EIO` (or `ENOSPC`, `ENOMEM`, `EFBIG`) at `STREAMON` | med | `group:open` |
| A-16 | No access is `EACCES`; seat ACL, `video` group or root | high / med | `system:camera-access` |
| A-17 | Control ids; MANUAL in the same call; no absolute value in auto | high | `<label>:controls`, `<label>:auto-off:*` |
| A-18 | log2 s to 100 µs map; -7 gives 78 | high | `<label>:controls:exposure-scale` |
| A-19 | Read-back can be cached | med | `<label>:settings-stick:image-effect` |
| A-20 | Controls hold while streaming | med | `<label>:settings-stick:holds`, `<label>:settings-stick:each-open` |
| A-21 | Close under 1 s; reopen works; Kiyo Pro quirk by kernel | low | `<label>:cycles`, `system:kernel` |
| A-22 | Alternate setting of the VideoStreaming interface; USB link from [req 3.4] | med | `group:open`, `system:usb` |
| A-23 | Layout and ioctl numbers from an ABI description; 64-bit time layout; x32 and ILP32 before kernel 5.6 refused | high / med | `detect` |
| A-24 | `spawn` and `O_CLOEXEC` | high | — |
| M-1 | Discovery session lists cameras with no permission | med | `detect` |
| M-2 | `uniqueID` = locationID, VID, PID (holds the port) | med | `<label>:identity:*` |
| M-3 | Virtual by transport type or name | low | `detect` (its count `virtual`) |
| M-4 | MJPG modes have subtype `'dmb1'`; ranges give 29.97, 30, 60 inside them | med | `<label>:detect`, `<label>:modes:granted:*` |
| M-5 | `'dmb1'` samples hold the camera JPEG in a block buffer | low–med | `<label>:native-jpeg:*` |
| M-6 | Session order; format and duration under the lock across `startRunning` | med | `<label>:rate`, `<label>:modes:granted:*` |
| M-7 | Delegate queue and notifications with no run loop; CMIO run loop NULL | low–med | `<label>:opens` |
| M-8 | PyObjC releases the GIL | med | T-UNX-84, `self:hang-100ms:gap` and `self:hang-100ms:hard-end` |
| M-9 | PTS converted to the host clock and the `perf_counter_ns` base | med / low | `<label>:clock:*` |
| M-10 | Drops and sequence numbers are visible | low–med | `<label>:sequence`, `<label>:time-gaps` |
| M-11 | Reversed (4.13.2): a camera in use is refused, the configuration lock is held, the in-use flag is watched | low | `<label>:in-use`, `<label>:in-use-mid-take`, `probe:<model>:hog-mode` |
| M-12 | Runtime errors and removal by notification | med | `<label>:in-use` |
| M-13 | No bandwidth error; first-frame timeout or low rate | low | `group:open` |
| M-14 | Permission status read; no permission gives zero frames | med | `system:camera-access` |
| M-15 | Controls through the widest working CoreMediaIO route (A1, A2, A3), any unit; else no manual exposure | low | `<label>:controls`, `<label>:settings-stick:*`, `probe:<model>:a1-cmio-native:<control>` and the other probes of [cert 10.7] |
| M-16 | Effect flags readable; Edge Light not | med | `system:video-effects` |
| M-17 | Close under 1 s | low | `<label>:cycles` |
| M-18 | USB link from [req 3.4] | — | `system:usb` |
| M-19 | macOS 12.3 and later | high | `detect` |
| M-20 | PyObjC works in the frozen app | med | T-UNX-88, `detect` |

## 3. What stays and what is shared

- The capture interface of [W 4.1] stays: `open`, `read_frame`, `set_controls`, `close` and
  `replaced_count`. Section 4.2 adds `diagnostics()` and the failure code.
- The shared loop, the gate, the warm-up, the rate check, the recorder and the rings stay as
  [W 5] to [W 12] give them, with the changes of 4.2 and 4.5. The floor of 30 fps [W U11], the size
  floor (640 wide and 360 high) [W 22.2, U Q887 to Q889] and one rate (30 or 60) for all cameras [U] apply to each source. The
  size floor is in the shared code (`modes.py`, the whole-request check, the shared loop); it is [NV] on
  Linux and macOS until a certify report.
- `CaptureWaitingPlace` of `source.py` serves both new sources (push sources).
- The OpenCV source stays as the fallback on Linux and macOS until a camera model passes the gate of
  [cert 11.3] on the system (4.9) [U].

## 4. The design

### 4.1 Package layout

| Path | Content |
|---|---|
| `skellycam/core/camera/capture/bounded.py` | The bounded call of [W 6.6], moved out of `media_foundation/bounded.py` with no COM, with a limit argument (5 s default, 11 s for A-13). `media_foundation/bounded.py` keeps a wrapper that joins the MTA in each worker [A]. |
| `skellycam/core/camera/capture/failure_codes.py` | The failure codes of 4.6.3. Pure. |
| `skellycam/core/camera/capture/exposure_units.py` | The map of A-18, and the macOS route scales of 4.4.6. Pure. |
| `skellycam/core/camera/capture/camera_checks.py` | The reader of the record of checked models of [cert 2.5] (4.9). It never writes the file. Pure file I/O. |
| `skellycam/core/camera/capture/v4l2/` | Linux only at run time. `abi.py` (ctypes structs and ioctl numbers computed for the host (A-23), and constants; ported from linuxlib, whose LP64 reference values become test values); `device.py` (the seam: `V4L2System`, with the real calls `os.open`, `fcntl.ioctl`, `mmap`, `select.poll`, `os.close`, and sysfs reads under a root path); `detect.py`; `controls.py`; `errors.py` (errno to code, pure); `source.py` (`V4L2Source`). |
| `skellycam/core/camera/capture/avfoundation/` | macOS only at run time. `layer.py` (the seam: `AVLayer`, and `PyObjCLayer`, the real calls); `detect.py`; `controls.py` (CoreMediaIO); `errors.py` (AVError name to code, pure); `source.py` (`AVFoundationSource`). |
| `skellycam/tests/capture/fake_v4l2.py`, `fake_avfoundation.py` | The fake layers of 6.2. |

Import rule [A, Q 1]. `media_foundation/` is Windows only [U]; Linux and macOS each get their own
folder [U]. `v4l2/` runs only on Linux and `avfoundation/` only on macOS. Each of their modules imports
only the standard library at module level: `fcntl`, `mmap` and `select.poll` load inside
`V4L2System` methods; `objc` and the PyObjC frameworks load inside `PyObjCLayer.__init__`. Thus the
fake-layer tests run on Windows, Linux and macOS, as the parity ruling asks [U]. This differs from
[W U18].

### 4.2 Shared changes (step 7s)

1. `CaptureFailure` gets `code: str`, a value of 4.6.3. The failure object of [W 12] gets `"code"`
   beside `stage` and `reason` [U]. Media Foundation sets codes too: the in-use HRESULTs give
   `camera-in-use`, the removal HRESULTs give `device-removed`, `0x800718CF`
   (`USB_INSUFFICIENT_BANDWIDTH`, in `errors.py`) gives `usb-bandwidth`, others `open-failed` or
   `stream-error` [W 6.7]. `_mark_ended` of `camera_group.py` gives `process-ended`. The text form
   stays `Camera {id} failed during {stage}: {reason}` [W D40].
2. Each source has `diagnostics() -> dict` with every key of 4.6.2 (null where it cannot fill one).
   The OpenCV source gives `backend` and null for each other source key. The diagnostics do not go
   into `CameraStatus.info`: that array holds 16,384 bytes, and `update_info` cuts a longer JSON text,
   so the JSON breaks (`camera_status.py`). The path [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md):
   - The camera process sends the full dict (the source keys and the keys of the shared loop, item 3)
     to the main process one time per second, and at the end of `open`, at a failure and at the
     close. It uses its own topic, `TopicTypes.DIAGNOSTICS`, with the message `DiagnosticsMessage`
     (`camera_id`, `diagnostics: dict`), through the same pubsub mechanism as a take error. The main
     process reads it from `CameraGroupIPC.diagnostics_subscription` by `CameraGroup._take_diagnostics`
     in the watch thread (`_watch_workers`). Thus no diagnostics message goes into `finished`
     [ADR-Q2NY](../decisions/entries/Q2NY-choices-of-code-step-2.md). The main process reads this topic also during the close of
     the group, and a camera process waits at most 1 s for its close dict to reach the pipe; then it exits
     anyway. A closed group keeps its last dicts in `CameraGroupManager.diagnostics()`. A failure that
     the main process sets (the stall watch, `_mark_ended`, a disk stall, `_give_up`) also sets
     `fail_code` in the dict that it keeps. "Apply again" clears the counter subset of the status.
   - The pickled message is at most 32 KiB. The largest dict (about 150 keys, 64 `frame_log` rows and
     60 hash keys) is about 14 kB. A dict over the limit is not sent, and the camera process logs it
     one time.
   - The main process keeps only the newest dict of each camera. `CameraGroup.diagnostics(camera_id)
     -> dict` returns it (`{}` before the first message). `CameraGroupManager.diagnostics() -> dict`
     returns `{camera_id: dict}` for each camera of each group. Certify reads these.
   - `CameraStatus.serialize()` (thus `app_state` and `GET /camera/group/state`) adds `"diagnostics"`
     with only the counter subset: `backend`, `frames`, `sequence_gaps`, `sequence_lost`,
     `discontinuity_flags`, `error_flag_frames`, `zero_bytes`, `drops_reported`, `poll_timeouts`,
     `format_changes`, `long_intervals`, `long_intervals_with_seq_gap`, `later_than_arrival`,
     `decoded_by_skellycam`, `encoded_by_skellycam`, `dht_inserted`, `restore_ok`, `restore_failed`
     and `fail_code`. It never holds `frame_log` or a hash key of D-11.
3. The shared loop adds its own keys to the same dict: `decoded_by_skellycam`,
   `encoded_by_skellycam` (D-10), `dht_inserted`, and the frame hashes of D-11 (4.6.2).
4. The exposure rules of [req 1] apply to each source, with the source parts of 4.5 [U].
5. The restore of the controls at the close (4.7) is on by default on each native source and on the
   fake source [U]. The OpenCV source has none: it cannot read the auto flag [ADR-Q2NY](../decisions/entries/Q2NY-choices-of-code-step-2.md).
6. `select_capture_source()` of `camera_worker.py` covers Linux and macOS by 4.9.
7. `detect_available_cameras()` calls the native detection on Linux and macOS, also when OpenCV is
   chosen, as Windows does [W D11]. The OpenCV source then opens the node that detection names
   (Linux: `cv2.VideoCapture(<node>, cv2.CAP_V4L2)`); on macOS it takes the index of the device in the
   list of `AVCaptureDevice.devicesWithMediaType_` that OpenCV uses, found by `uniqueID` [A] [NV].
8. `CameraDeviceInfo` gets `backend` (`v4l2`, `avfoundation`, `media-foundation`), `id_source`,
   `has_serial`, `evidence` (`verified`, `known-bad`, `unknown`) and `checked` (from the record of
   [cert 2.5] for its model on this OS key). `usb_link` comes from [req 3.2, 3.4]. The status gets `system_evidence` [cert 11.3]. The app uses them
   for the prompt to run certify [cert 11.4].
9. The `camera_id` hash stays the function of today; its input changes on Linux and macOS (A-2,
   M-2). Each Linux and macOS camera gets a new ID one time, as on Windows [W D11] [U].

### 4.3 The V4L2 source (step 7a)

#### 4.3.1 Detection

In a short-lived `spawn` child, each call bounded, as on Windows [W 7.1, A]:

1. Refuse on the x32 ABI (A-23).
2. List `/dev/video*`. For each node: `open(O_RDWR | O_NONBLOCK | O_CLOEXEC)`, `VIDIOC_QUERYCAP`
   (A-1). Skip a node with no video capture in `device_caps`.
3. Read the sysfs data of A-2, and `usb_link` from the lookup of [req 3.4]. A node that cannot be opened (`EACCES`) is listed from sysfs
   with `modes_read: false` (A-16).
4. List the modes (A-4). Close the node.
5. Build `CameraDeviceInfo` with the fields of 4.2 item 8, `name` (the card name of `QUERYCAP`) and
   `path` (`/dev/videoN`, as the OS gives it [W W6]).
6. Refuse two equal `camera_id` values [W D13].

#### 4.3.2 Open

Each step is a bounded call (A-13). The 15 s ready limit of [W 9.3] applies.

1. Detection again in the camera process (no child), and the match by `camera_id` [W 6.2]. No match:
   `not-found`. Two: `open-failed` [W D13].
2. `open()` the node (`EACCES`: `no-access`; `ENOENT`, `ENODEV`, `ENXIO`: `not-found`).
3. `VIDIOC_REQBUFS` with `count = 0` (A-14).
4. Choose the mode by [W 7.5]. `S_FMT` with MJPG, then `G_FMT` (A-5).
5. `S_PARM`, then `G_PARM` (A-6).
6. `REQBUFS` with `count = 4`, `QUERYBUF` and `mmap` of each buffer, `QBUF` of each (A-11).
7. `STREAMON` (A-15). Read `usb_alt` (A-22).
8. Start the capture thread. Wait for the first frame, at most 5 s [W 6.4]: else
   `first-frame-timeout`, then the close with its bounded steps.
9. Read each control (the "before" values of 4.7). Return `OpenedMode`.

A failure at steps 2 to 8 runs the close of 4.3.7 for the steps that ran.

#### 4.3.3 The capture thread

One thread for each source, named `v4l2 capture`:

1. `poll` with a timeout of 100 ms (A-12). A timeout: check the stop flag, poll again.
2. `VIDIOC_DQBUF`; `arrival_ns = perf_counter_ns()` first after it returns [W D28]. `EAGAIN`: poll
   again. `ENODEV`: the error marker with `device-removed`. `EIO`, or `POLLERR`: the source checks
   whether `/sys/class/video4linux/videoN` still exists. Gone: `device-removed`. Present: count it;
   three in a row give `stream-error` [A].
3. Copy `bytesused` bytes into one `bytes` object. `QBUF` the buffer at once. `ENODEV` at `QBUF`
   gives `device-removed` [K9].
4. Build `CapturedFrame`: `payload`, `format` `MJPG`, `arrival_ns`, `sample_ns` (A-9),
   `delivered_len = bytesused`, `driver_error` (A-8), `source_frame_number`, `discontinuity` (A-10).
5. Put the frame into the waiting place. Update the counters of the diagnostics.

The thread does no file I/O, no logging per frame and no decode [W 4.3]. Each pass waits in `poll`.
The source reads the time through a module name `perf_counter_ns`, so that a test can give it a
virtual clock, as `camera_loop.py` does [A].

#### 4.3.4 `read_frame`

`read_frame(timeout_s)` takes from the waiting place, as `MediaFoundationSource` does [W 4.2].

#### 4.3.5 Controls

`set_controls(changes)` is one bounded call: for each change read before, set, then read every control
back [W D20, W 6.8].

| skellycam control | V4L2 | Unit |
|---|---|---|
| `exposure` (a value) | `V4L2_CID_EXPOSURE_AUTO` = 1 and `V4L2_CID_EXPOSURE_ABSOLUTE` = A-18 value, in one `S_EXT_CTRLS`, menu first | log2 s outside, 100 µs inside |
| `exposure` (`auto: true`) | Never sent: the camera's own auto exposure is never set (4.5) [U], except by the restore at the close (4.7) [U] | — |
| `gain` | `V4L2_CID_AUTOGAIN` = 0 when present, then `V4L2_CID_GAIN` | raw |
| `focus` | `V4L2_CID_FOCUS_AUTO` = 0, then `V4L2_CID_FOCUS_ABSOLUTE`; with `auto: true`, `V4L2_CID_FOCUS_AUTO` = 1 | raw |
| `white_balance`, `power_line` | read only | raw, menu |

- A control that `QUERY_EXT_CTRL` does not list is absent (`present: false`) [W D43].
- A control with the flag `inactive` or `disabled` at a set gives `control-failed` [A].

#### 4.3.6 Errors

| errno | Call | Code | Stage | Reason |
|---|---|---|---|---|
| `EACCES` | `open` | `no-access` | `open` | "no access to the video device" |
| `ENOENT`, `ENODEV`, `ENXIO` | `open` | `not-found` | `open` | "camera not found" |
| `EBUSY` | `reqbufs`, `s-fmt`, `s-parm`, `streamon` | `camera-in-use` | the stage of the call | "in use by another program" [W D13] |
| `EIO`, `ENOSPC`, `ENOMEM`, `EFBIG` | `streamon` | `usb-bandwidth` | `start stream` | "USB bandwidth refused, or a device error (errno <name>)" |
| `EINVAL` | `s-fmt`, `s-parm` | `no-mode` | `set mode` | "the camera refused <mode>" |
| `EACCES`, `EINVAL`, `ERANGE` | `s-ext-ctrls` | `control-failed` | `set controls` | "<control>: <errno name>" |
| `ENODEV` | `dqbuf`, `qbuf`, `poll`, `streamoff` | `device-removed` | `streaming` | "device removed" |
| `EIO` or `POLLERR`, node gone | `dqbuf`, `poll` | `device-removed` | `streaming` | "device removed" |
| `EIO` three times, node present | `dqbuf` | `stream-error` | `streaming` | "stream error (EIO)" |
| any other | any | `open-failed` or `stream-error` | the stage of the call | "<call>: <errno name>" |
| (hang) | any bounded call | `hung` | the stage of the call | "<call> did not return in <limit> s" |

#### 4.3.7 Close

Each step is bounded; a hung step stops the close and the process ends hard [W 6.6]:

1. Set the stop flag; join the capture thread (at most 1 s).
2. The restore of 4.7.
3. `STREAMOFF`.
4. `munmap` each buffer; `REQBUFS` with `count = 0`.
5. `close()` the file.

#### 4.3.8 Removal

A removal makes the camera dead at once [W D38] (table 4.3.6). Without an error, the stall rule of
2 s applies [W 9.5]. No unplug test runs [U].

### 4.4 The AVFoundation source (step 7b)

#### 4.4.1 Detection

In a short-lived `spawn` child, each call bounded [A]:

1. Refuse before macOS 12.3 (M-19).
2. Read the permission status (M-14). Detection runs also without permission.
3. The discovery session of M-1. For each device: `uniqueID`, `modelID`, `localizedName`,
   `transportType`, `deviceType`, the formats (M-4).
4. Build `CameraDeviceInfo` with the fields of 4.2 item 8, `path` = `uniqueID` as the OS gives it
   [W W6], `virtual` (M-3), and `usb_link` from the lookup of [req 3.4].
5. Refuse two equal `camera_id` values [W D13].

#### 4.4.2 Open

Each step is bounded:

1. Permission (M-14): not `authorized` gives `no-permission`.
2. Find the device by `camera_id` (detection again).
3. `AVCaptureDeviceInput.deviceInputWithDevice_error_`; an `NSError` gives its code (4.4.8).
4. `AVCaptureVideoDataOutput` with `alwaysDiscardsLateVideoFrames = True`, the delegate on a serial
   dispatch queue, the observers of M-12 (M-7).
5. Choose the mode by [W 7.5] from the `'dmb1'` formats (M-4). Configure in the order of M-6 with the
   `videoSettings` variant of 4.4.3, and `startRunning` under the device lock.
6. Wait for the first frame, at most 5 s [W 6.4]. Check `delivered` (M-5). Read the effect flags
   (M-16) and each control (the "before" values of 4.7).
7. Return `OpenedMode`.

#### 4.4.3 The JPEG variants (M-5)

1. Variant `empty`: `videoSettings = {}` [K15]. The first sample decides `delivered`.
2. When it is decoded: `stopRunning`, set variant `dmb1` (`kCVPixelBufferPixelFormatTypeKey` =
   `'dmb1'` [K18]), take the device lock again, `startRunning`, unlock (M-6). From phase 7 the source holds the lock
   from the first `startRunning` to the close (4.13.2 item 2): it keeps the lock through this restart and does not
   unlock here.
3. When the second variant is decoded too, or the output refuses it: failure `no-native-jpeg`, stage
   `start stream` [A]. Outside certify, the camera process then opens the OpenCV source for this
   camera [U]. Inside certify it does not [U].

#### 4.4.4 The delegate

`captureOutput:didOutputSampleBuffer:fromConnection:` on the serial queue:

1. `arrival_ns = perf_counter_ns()` first [W D28].
2. Check the dimensions of the format description (M-11).
3. Copy the block buffer into one `bytes` object (`CMBlockBufferCopyDataBytes` [R mac_avf]).
4. `sample_ns` from the PTS (M-9), with the 200 ms rule of [W 4.2].
5. The sequence number and the drop flag (M-10). `driver_error` is `False` [A].
6. Put the frame into the waiting place.

`captureOutput:didDropSampleBuffer:fromConnection:` counts a drop and marks the next frame with
`discontinuity`. The delegate never raises into Objective-C: an exception becomes the error marker
[W 4.3].

#### 4.4.5 `read_frame`

As in 4.3.4.

#### 4.4.6 Controls (M-15)

**The route of each control of a model** [U]. The candidate routes are A1 (`fcnv` on the generic
classes `xpsr`, `gain`, `fcus`), A3 (`fcnd` on the `uc**` classes) and A2 (`fcav`, in its unit) of
4.4.10. For exposure, gain and focus each, the source chooses:

1. With evidence: the local `full` row of the model in the record of checked models [cert 2.5], then
   the shipped row of the model [cert 11.2]. Each row holds, for each control, the result of each route
   that was tried, keyed by its `control_path` value (`cmio-native`, `cmio-absolute`,
   `cmio-native-data`): `works`, `unproven` or `no`. The source uses a route whose result is `works`.
   When several routes work, it uses the one that works on the most models of the shipped file. With
   no `works` route, it uses an `unproven` route by the same rule, and the control is offered in the
   UI. When each route of the control is `no`, the control is absent (the UI hides it) [U] [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).
2. With no evidence, inside certify (certify never applies the record to itself [cert 2.5]), or with
   the setting `SKELLYCAM_MACOS_CAPTURE=avfoundation`: the fixed order A1, then A3, then A2, by the
   number of field reports [K29]. The source takes the first route that the listing shows present and
   settable and whose set reads back. The control is then "unproven" (`<c>_route_proven` false)
   [U, A].

**The scale of exposure** [U, A]. The search of [req 1.3] tries the 8 values -12 to -5, and Manual
holds one value. The source maps each value onto the ordered scale of the route:

- A route with a time unit maps exactly: `2^v` s for A2 in seconds; the map of A-18 for a native
  value that the evidence proves to be in UVC units of 100 µs (the 62.5 ms frame-rate proof: native
  625 halves the frame rate) or for A3 on `ucea` (UVC `CT_EXPOSURE_TIME_ABSOLUTE`, 100 µs [K29]). Such
  a route reports `exposure_unit` `100us` (A2 in seconds: `seconds`) [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).
- A route in EV: 8 evenly spaced points over the EV range, -12 at the shortest exposure (EV is
  already a log scale).
- Any other route: 8 log-spaced points over the native range, -12 at the low end [NV that the low end
  is the shortest exposure].
- A route in EV or another native value has no time unit (`exposure_unit` `ev`, `native` or
  `native-data`). Manual then shows eight plain steps from darkest to brightest, with no time label,
  for now (item 10 of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)). `exposure` holds the step index 0 to 7, and the step k is the k-th point
  of the scale above, -12 + k of the search [req 1.1, 1.3].

**The calls:**

| skellycam control | Path | When absent |
|---|---|---|
| `exposure` (a value) | The chosen route: `fcam` = 0, then `fcnv` (A1), `fcnd` (A3) or `fcna` = 1 and `fcav` (A2); and AVFoundation `exposureMode = locked` when `isExposureModeSupported(.locked)`, so that AVFoundation does not apply its own auto mode again [R macctl §1 item 3] | `no_manual_exposure` [U] |
| `gain` | The chosen route, `fcam` = 0 | absent |
| `focus` | The chosen route, `fcam` = 0; with `auto: true`, `fcam` = 1 | absent |
| `white_balance`, `power_line` | CoreMediaIO read, if published | absent |

- The source finds the CoreMediaIO device whose `kCMIODevicePropertyDeviceUID` equals `uniqueID`
  [R macctl §1]. It reads the constants from `pyobjc-framework-CoreMediaIO`, never from FourCCs in
  the code [A].
- After each `startRunning`, also after the variant restart of 4.4.3, the source sets the controls
  again [R macctl §1 item 3] [W D20].
- `fcam` = 1 for exposure is never set, except by the restore at the close (4.7) [U].
- Each set and get records its `OSStatus` (D-4).

#### 4.4.7 Close (M-17)

1. Remove the observers; set the delegate to nil.
2. The restore of 4.7.
3. `stopRunning` (bounded).
4. Remove the input and the output; release.

#### 4.4.8 Errors

| Event | Code | Stage | Reason |
|---|---|---|---|
| Permission not `authorized` | `no-permission` | `open` | "camera permission is <status>" |
| No device with the `camera_id` | `not-found` | `open` | "camera not found" |
| `AVErrorDeviceInUseByAnotherApplication` | `camera-in-use` | the current stage | "in use by another program" |
| `AVErrorDeviceNotConnected`, `AVCaptureDeviceWasDisconnectedNotification` | `device-removed` | the current stage | "device removed" |
| Format refused, read-back differs | `no-mode` | `set mode` | as on Windows |
| No JPEG after both variants | `no-native-jpeg` | `start stream` | "the camera gives no JPEG through AVFoundation" |
| No first frame in 5 s | `first-frame-timeout` | `first frame` | "no frame in 5 s" |
| A runtime error with another code | `stream-error` | `streaming` | "<AVError name or code>" |
| The format changed while streaming | `format-changed` | `streaming` | "another program changed the camera mode" |
| A control call fails | `control-failed` | `set controls` | "<control>: OSStatus <n>" |
| A hang | `hung` | the stage | "<call> did not return in 5 s" |

#### 4.4.9 Removal

The removal notification makes the camera dead at once [W D38]. Else the stall rule applies.

#### 4.4.10 Approaches for exposure and for the camera's JPEG [U]

The user ruled that, for now, a certify run on macOS tries every approach that might work for
exposure control and for the delivery of the camera's own JPEG; the test is trimmed once a working
one is found [U]. The one exception: the exclusive opens A7 and A8 run only when A5 and A6 both
failed (item 7 of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)). The probes run once per camera model (USB vendor id and product id), not per unit,
and the longer macOS full run is accepted until one approach is proven [U]. The product uses only the
approaches that the rulings allow. The names A1 to A10 and B1 to B7 are those of the approaches list
[K29]. The certify spec owns the probe names, their steps, their order, the proof rules and the drop
rules [cert 10.7] [U].

**Proof rules** [cert 10.7]. A control works only when the image changes; a read-back alone
"appears" to work. A JPEG is the camera's own only by the DQT and DHT rules: the DQT of the same model
(VID:PID) from a Media Foundation or V4L2 passthrough run, or no DHT for a model whose reference frames
have none, and a DQT that differs from Apple's encoder (B4). The key of the reference is VID:PID only:
the diagnostics carry no `bcdDevice` [A]. A firmware change can then give a false "appears", never a
false "works".

**Exposure and other controls (Table A of the list):**

| ID | Approach | Product | Certify |
|---|---|---|---|
| A1 | CoreMediaIO feature control, `NativeValue` (`fcnv`) on the generic classes | Candidate route for exposure, gain and focus (4.4.6) [U] | `probe:<model>:a1-cmio-native:<control>`, through the product layer |
| A2 | CoreMediaIO feature control, `AbsoluteValue` (`fcna` = 1, `fcun`, `fcar`, `fcav`), any unit | Candidate route for exposure, gain and focus (4.4.6) [U] | `a2-cmio-absolute:<control>`, through the product layer |
| A3 | CoreMediaIO `NativeData` (`fcnd`, `fcdr`) on the undocumented `uc**` classes | Candidate route for exposure, gain and focus (4.4.6) [U] | `a3-cmio-native-data:<control>`, through the product layer |
| A4 | CoreMediaIO Tune (`fctn` = 1), one shot | No: it runs the camera's own auto [U] | `a4-cmio-tune:exposure`, through the product layer |
| A5 | IOKit interface `ControlRequestTO` on pipe 0, no `USBInterfaceOpen` | No [U: endpoint 0 only as a certify probe] | `a5-ep0-interface:<control>`, certify code, risky phase |
| A6 | IOKit device `DeviceRequestTO`, no `USBDeviceOpen` | No [U] | `a6-ep0-device:<control>`, certify code, risky phase |
| A7 | `USBDeviceOpen` (no seize), request, close within 100 ms | No: an exclusive device open | `a7-device-open:exposure`, certify code, only when A5 and A6 both fail |
| A8 | `IOUSBHostDevice` with no options, `sendDeviceRequest` | No: exclusive ownership | `a8-iousbhost:exposure`, certify code, only when A5 and A6 both fail (as A7) |
| A9 | AVFoundation continuous auto, then locked | No: "Auto by lock" is removed [U] | `a9-avf-lock:exposure`, through the product layer |
| A10 | The iOS-only AVFoundation selectors at run time (`respondsToSelector:`) | No | `a10-avf-custom:exposure`, through the product layer, only with a selector |

**The camera's JPEG (Table B of the list):**

| ID | Approach | Product | Certify |
|---|---|---|---|
| B1 | `AVCaptureVideoDataOutput`, `videoSettings = {}` on a `'dmb1'` format | Yes, the first variant (4.4.3) [U] | `b1-empty`, through the product layer |
| B2 | `videoSettings` with `kCVPixelBufferPixelFormatTypeKey`: variants `dmb1`, `jpeg4cc`, `dmb1_sized`, `chromium` | Variant `dmb1` only, the second try (4.4.3) [U] | `b2-dmb1`, `b2-jpeg4cc`, `b2-dmb1-sized`, `b2-chromium`, through the product layer |
| B3 | `videoSettings = nil` (the decoded control) | No | `b3-nil`, through the product layer |
| B4 | `AVVideoCodecKey` = JPEG at `AVVideoQualityKey` 0.5 and 0.9: Apple's encoder, the re-encode reference | No: a re-encode | `b4-apple-jpeg`, through the product layer |
| B5 | `AVCaptureMovieFileOutput` with output settings `{}` and the file-output delegate | No | `b5-movie-file`, certify code; the `.mov` is a camera recording, deleted at the end and never in the report |
| B6 | CoreMediaIO stream direct (`CMIOStreamCopyBufferQueue`, `CMIODeviceStartStream`) | No | `b6-cmio-stream`, certify code |
| B7 | Decode, then a SkellyCam re-encode | The OpenCV fallback of a `no-native-jpeg` camera, outside certify [U] | none: it is the floor, not a passthrough |

**What the product layer exposes for the probes** [A]. `PyObjCLayer` (6.2) takes these parameters;
the source uses only the allowed values, and certify passes the others:

- `configure(..., variant)` with `variant` one of `nil`, `empty`, `dmb1`, `jpeg4cc`, `dmb1_sized`,
  `chromium`, `codec-jpeg-q50`, `codec-jpeg-q90` (B1 to B4). The source passes only `empty` and
  `dmb1`.
- Each sample gives `has_block_buffer`, `has_image_buffer`, the subtype and `cv_pixel_format` (S0 and
  B1 to B4).
- `formats()`, `available_pixel_formats()` and `available_codec_types()` of an output that is not in a
  session (S0).
- `cmio_objects()`: the owned control objects of the device and of each stream, with class and base
  class, and for each property of the list (`fcoo`, `fcam`, `fcna`, `fctn`, `fcnv`, `fcav`, `fcnr`,
  `fcar`, `fcun`, `fcnd`, `fcdr`, and `eroi`, `etgt`, `eint`, `emax` for reading only) whether it
  exists, whether it is settable, and its value (S0).
- `cmio_set(object, form, value)` with `form` one of `native` (A1), `absolute` (A2), `native-data`
  (A3), `tune` (A4) and `mode` (`fcam`), and `cmio_get(object, form)`. The source uses the form of
  the chosen route of each control (4.4.6), and never `tune`.
- `avf_modes()` and `set_avf_mode(control, mode)` for the exposure, focus and white balance modes,
  `isExposureModeSupported` for 0 to 3, and `responds_to(selector)` with a guarded `call_selector`
  (A9, A10). The source uses only `locked` for exposure (4.4.6).
- Each call records its `OSStatus` or `NSError` code and its time (D-5).

**What certify codes itself** [A]: the endpoint-0 requests A5 and A6 (and the `VS_COMMIT` `GET_CUR`
read and the IORegistry descriptor read of S0, which use the same IOKit code), the exclusive opens A7
and A8, the movie file output B5, and the CoreMediaIO direct stream B6. These need no product code
path; the product ships none of them [U].

**Order and drop rules.** The order and the drop rules are those of [cert 10.7]. For the
controls, a route stays in the run while it works on any model; the product prefers the route that
works on the most models of the shipped file (4.4.6) [U]. A probe that proves an approach the product
does not use (for example B5 for the JPEG) needs a ruling of the user before the product uses it [U].

### 4.5 Exposure: the source parts

The camera requests spec owns the exposure rules: the modes, the search (its algorithm, the states
and their order, the field and endpoint names, the time limit of 20 s), the slow-camera texts and the
60 fps fall back [req 1.1 to 1.5a, 1.9, 2.4] [U]. This spec does not repeat them. In short: Auto is
SkellyCam's search, and it stays the stored mode; the held value is in `exposure`, beside
`exposure_found_at_fps`; a search runs at each open, at a frame-rate change and on request
(`POST /camera/group/exposure/auto`, or an apply that switches `MANUAL` to `AUTO`); its status is
`exposure_search`; the order of an open in Auto is `starting`, `waiting`, `adjusting`, `checking`,
then `ready` or `too_slow` [req 1.3b]. The apply request answers when the cameras stream, and the
search result arrives through the status [U].

What is specific to V4L2 and AVFoundation:

1. Each source sets each value of the search and each Manual value as a manual value: Linux with the
   menu MANUAL in the same `S_EXT_CTRLS` (4.3.5); macOS on the chosen route of 4.4.6, with its scale.
   No source ever sets the camera's own auto exposure, except the restore at the close, which is the
   one allowed call that may turn it back on (4.7) [U].
2. The search runs on the native sources of Linux and macOS [U]. The refusal of [req 1.5] and the
   text "Exposure is set by the camera on this system" of [req 1.7] apply only to a camera whose
   source is OpenCV, for now (item 9 of [ADR-BVK7](../decisions/entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md)).
3. A camera with no manual exposure has no Manual, no Auto and no exposure control in native capture,
   and the search never runs for it (no `adjusting`) [U]. It opens; the warning of the kind
   `no_manual_exposure` (the snake_case form of [W 11.3]) is in the apply response and the status; the
   certify reason code is `no-manual-exposure`. This applies to a macOS camera with no working route
   (4.4.6), and, outside certify, on Linux and macOS to a model whose evidence gives each exposure
   route the result `no` (4.4.6, 4.9) [U]. An `unproven` route keeps the control [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).
4. `adjusting` refuses a changed config, as [req 1.4] says [U].
5. The reason of a camera that fails the start-up rate check is the form of [req 1.5a]
   (`declared 30.00 fps, measured 25.76 fps. Camera is slow. Try adding more light`); the failure
   object may also carry `declared_fps` and `measured_fps` as numbers [A]. A `too_slow` camera has
   `failure: null` [W 8.4]; its row text is the sentence of [req 1.5a].
6. The 60 fps fall back of the group is that of [req 2.4] on each source.

Changes for Media Foundation: the same rules [U], applied in
[`windows-capture.md`](windows-capture.md); the note of 2026-11-20 at its top names the sections and
tests that change.

### 4.6 Diagnostics

#### 4.6.1 Rules

- `diagnostics()` returns one dict with fixed keys. Each value is an int, a float, a bool, null or a
  string of a fixed vocabulary, with one exception: `frame_log`, a list of at most 64 rows [A].
- Each key, value and code that certify reads has the name of [cert 10.2, 10.3, 15]. Section 4.6.4
  lists what certify must add.
- No value holds a serial number, a device path, a `uniqueID`, a `camera_id`, a camera name, a host
  name or a user name [cert 9.4]. A SHA-256 of frame bytes is allowed: it does not show the image.
- Every source gives every key; a key that a source cannot fill is null.
- The `app_state` message of the websocket carries only the counter subset of 4.2 item 2, not
  `frame_log` and not the hash keys of D-11 (about 6 kB per camera per second) [A, cross-spec review
  §4 Q2]. Certify reads the full dict through `CameraGroupManager.diagnostics()` in its own process
  (4.2 item 2).
- Cost [A]: a few integer operations per frame for the counters; `frame_log` is a ring of 64 rows of
  five integers (under 4 KiB); the 30 hashes cost one SHA-256 per frame for 30 frames after each
  trigger (about 0.2 ms for a 200 kB JPEG at 1 GB/s [NV]); the percentiles use the last 256
  differences and run only when `diagnostics()` is called, one time per second.

#### 4.6.2 Keys

| D | Keys | Linux | macOS | Windows |
|---|---|---|---|---|
| — | `backend` (`v4l2`, `avfoundation`, `media-foundation`, `opencv`) | yes | yes | yes |
| D-1 | `requested_fourcc`, `granted_fourcc`, `requested_w`, `requested_h`, `granted_w`, `granted_h`, `requested_fps_num`, `requested_fps_den`, `granted_fps_num`, `granted_fps_den`, `delivered` (`jpeg`, `decoded`, `none`), `video_settings` (`nil`, `empty`, `dmb1`, null), `bytesused_equals_payload` | `G_FMT`, `G_PARM` | active format, durations | read-back type |
| D-2 | `clock` (`monotonic`, `realtime`, `host`, `device`, `unknown`), `tstamp_src` (`soe`, `eof`, `unknown`), `ts_conversion` (`timeval-to-ns`, `host-to-mach-to-ns`, `sync-to-host-to-mach-to-ns`, `100ns-units`), `sample_time_kept`, `sample_minus_arrival_p5_ms`, `sample_minus_arrival_p50_ms`, `sample_minus_arrival_p95_ms`, `later_than_arrival` (count since the open, counted before the 200 ms rule) | yes | yes | yes (`clock` `unknown`) |
| D-2, D-3 | `frame_log`: rows `[source_frame_number, sequence, raw_ts_ns, arrival_ns, bytesused]`, `bytesused` negative when the error flag is set; certify computes `grain_ms` and `jitter_p95_ms` from it | yes | sequence null when absent | sequence null |
| D-3 | `frames`, `sequence_available`, `sequence_gaps`, `sequence_lost`, `discontinuity_flags`, `error_flag_frames`, `zero_bytes`, `drops_reported`, `poll_timeouts`, `format_changes`, `long_intervals` (intervals over 1.5 periods of the mode rate since the open), `long_intervals_with_seq_gap` (those with a sequence gap); for the last start-up rate check of the open (not built, [cert 3.5.6]): `rate_window_frames`, `rate_interval_p95_ms`, `rate_interval_max_ms`, `rate_interval_max_end_ns` (`perf_counter_ns`), `rate_long_intervals`, `rate_luma_mean` (the mean grey value of the last frame of the window at 1/8 size) | yes | yes | yes; null: `sequence_gaps`, `sequence_lost`, `long_intervals_with_seq_gap` (no sequence number), `error_flag_frames` (no error flag), `drops_reported` (no drop report; a drop gives `discontinuity_flags`) |
| D-4 | For each control `c` of `exposure`, `gain`, `focus`, `white_balance`, `power_line`: `c_present`, `c_min`, `c_max`, `c_step`, `c_default`, `c_auto_supported`, `c_native_id`, `c_value` (native), `c_auto`, `c_set_rc`, `c_get_rc`, `c_before`, `c_before_auto`; `c_route_proven`; and `exposure_unit` (`log2-s`, `100us`, `seconds`, `ev`, `native`, `native-data`, `none`), `exposure_native_at_m7`, `control_path` (`v4l2`, `cmio-native`, `cmio-absolute`, `cmio-native-data`, `avf-lock`, `ep0`, `iam`, `ks`, `none`), `ae_off_ok`, `af_off_ok`, `ae_back_on_after_s`, `restore_ok`, `restore_failed` (4.7) | yes | yes | yes; `c_min` to `c_auto_supported` from `GetRange` on the IAM route, null on the KS route; null: `c_set_rc`, `c_get_rc`, `c_route_proven`, `exposure_native_at_m7`, `ae_off_ok`, `af_off_ok`, `ae_back_on_after_s` (step 3c and certify) |
| D-5 | `fail_code`, `native_code` (a number), `native_domain` (`errno`, `hresult`, `nserror`, `osstatus`, `ioreturn`), `call` (4.6.3), `fail_stage`, `failed_calls`, `busy_call`; not built [cert 3.5.3]: `first_fail_code` (the code of the first failure of the open, kept when a later hang gives `hung`; the source also keeps the native code of the first failure that had one), `exit_code` (the main process fills it when the camera process ended, as it fills `fail_code`; null while the process runs) | yes | yes | yes |
| D-6 | `t_enumerate_ms`, `t_open_ms`, `t_set_mode_ms`, `t_buffers_ms`, `t_stream_on_ms`, `t_first_frame_ms`, `t_controls_ms`, `t_close_ms` | yes | yes | yes |
| D-7 | `id_source` (`serial`, `id-path`, `unique-id`, `mf-link`), `has_serial` | A-2 | M-2 | `mf-link` |
| D-8 | `access` (`seat-acl`, `video-group`, `root`, `none`); `tcc` (`granted`, `denied`, `restricted`, `not-determined`); `center_stage`, `portrait`, `studio_light`, `reactions`, `edge_light` | `access` | `tcc`, effects | null |
| D-9 | `usb_alt` (`usb_link` is in the detection result, [req 3.2]) | sysfs (A-22) | null | null |
| D-10 | `decoded_by_skellycam`, `encoded_by_skellycam` (the shared loop) | yes | yes | yes |
| D-11 | `sha256_00` to `sha256_29` and `sha256_frame_00` to `sha256_frame_29` (the `source_frame_number` of each hashed frame), `sha256_trigger` (`ready`, `recording`), `dht_inserted`, `dqt_sha256`, `dqt_distinct` (distinct DQT hashes over the 30 frames), `dht_present` (a DHT in the camera's bytes) (the shared loop) | yes | yes | yes |
| Linux | `kernel`, `driver`, `nodrop_param`, `clock_param`, `hwtimestamps_param`, `buffers_requested`, `buffers_granted`, `interval_types`, `nodes_seen`, `nodes_skipped_meta`, `modes_listed`, `mjpg_sizes` | yes | null | null |
| macOS | `macos`, `subtypes`, `notifications_seen`, `sync_clock_is_host`, `modes_listed`, `mjpg_sizes` | null | yes | null |

D-2 on Media Foundation [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md): the source reads only `IMFSample::GetSampleTime` (`sample_ns` = 100 x
its value, [W 4.2]) and no other attribute of the sample. No value that it reads names the base of that
time, so `clock` is `unknown` (the source cannot tell) and `tstamp_src` is `unknown`. Certify then gives
`clock:base` `not-run` with `clock-unknown` [cert 10.2]. The values themselves still go to
`frame_log`, `later_than_arrival` and the percentiles, so `clock:before-arrival` and
`clock:near-arrival` judge them. `long_intervals` counts with the period of the granted mode, set at the
mode set of each open. Whether a sample time is on the QPC clock of `perf_counter_ns` is [NV].

D-11 [A]: the shared loop hashes the bytes that it gives to the ring and the recorder (after a DHT
insertion), for the first 30 frames that it takes after the first move to `ready` of each open and
after each record start. A live change, which ends in `ready` again, does not re-arm the set. Each new
trigger replaces the set; certify reads the ring slots of those frames before the ring laps. Thus certify compares each hash with the ring slot and the
MKV block of the same `source_frame_number`. Warm-up frames are never hashed: they reach neither the
ring nor the recorder [W 9.2].

#### 4.6.3 Failure codes and call names

Codes [U, cert 15]: `not-found`, `no-access`, `no-permission`, `camera-in-use`, `usb-bandwidth`,
`no-mode`, `below-floor`, `open-failed`, `first-frame-timeout`, `no-native-jpeg`, `not-ready`,
`rate-low`, `rate-high`, `control-failed`, `device-removed`, `stalled`, `hung`, `disk-stall`,
`previous-process-alive`, `stream-error`, `format-changed`, `process-ended` (certify added the last
four [cert 18.1]), `start-method-fork` (the start of a camera process refuses the method `fork`, 4.12)
[ADR-HQE5](../decisions/entries/HQE5-choices-of-fix-lane-4.md). `no-manual-exposure` is not a failure code of `CaptureFailure`: a camera with no
manual exposure opens, with the warning kind `no_manual_exposure` (4.5) [req 1.5]. `no-manual-exposure`
is only a certify reason code [cert 15] [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).

The code of each existing failure [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md).
`CaptureFailure(stage, reason, *, hung=False, code=None)` gets the keyword `code`. When a site gives
no code, the default is `open-failed` at the stages before streaming (`open`, `set mode`,
`set controls`, `first frame`, `warm-up`, `rate check`, `detection`) and `stream-error` after
(`streaming`, `recording`, `close`). `failure_codes.py` holds the list and the default.

| Site (file:line on this branch) | Reason text | Code |
|---|---|---|
| `camera_loop.py:154` (any other exception of the loop) | `<type>: <text>` | the default |
| `camera_loop.py:169` (`_lost_heartbeat`) | `lost the server's heartbeat` | the default |
| `camera_loop.py:204` (`_read`, W 9.5) | `no frame for 2 s` | `stalled` |
| `camera_loop.py:231`; `modes.py:84`, `:88`, `:95` | `no mode at 30 fps or more` | `below-floor` |
| `modes.py:91` | `no <fourcc> mode at <w>x<h> ...` | `no-mode` |
| `camera_loop.py:265` (start-up rate check) | the text of [req 1.5a] | `rate-low` below the limit, `rate-high` above it |
| `camera_loop.py:275` | `not ready in 15 s` | `not-ready` |
| `media_foundation/bounded.py:69`; `media_foundation/source.py:97`, `:107`, `:135` (`hung=True`) | `... did not return in 5 s` and the others | `hung` |
| `media_foundation/errors.py:39` (`check`), `source.py:237`, `:284` (an HRESULT) | `hresult_reason` | `camera-in-use` for `IN_USE`, `device-removed` for `REMOVED`, `usb-bandwidth` for `0x800718CF`; else the default |
| `media_foundation/source.py:52`, `:239`, `:241` | `<type>: <text>`, `E_FAIL`, `end of stream` | `stream-error` |
| `media_foundation/source.py:172`; `media_foundation/detect.py:59` | `camera not found` | `not-found` |
| `media_foundation/source.py:174` | `<n> devices have the camera_id ...` | `open-failed` |
| `media_foundation/source.py:220` | `no frame in 5 s` | `first-frame-timeout` |
| `media_foundation/source.py:222` | the reason of the stored stream error | the code of that error |
| `media_foundation/source.py:315` | `the camera set <got> instead of <chosen>` | `no-mode` |
| `media_foundation/source.py:363`, `:366`; `opencv_source.py:94` | `no <name> control` | `control-failed` |
| `opencv_source.py:57` | `<type>: <text>` | `open-failed` |
| `media_foundation/detect.py:118`, `:128`, `:132` (detection, not a camera status) | `<type>: <text>`; `... did not answer in 7 s`; `... ended with code <n>` | `open-failed`; `hung`; `process-ended` |

The failure dicts that the main process writes get a code too:

| Main-process site | Stage, reason | Code |
|---|---|---|
| `CameraGroup._give_up` (`camera_group.py:292`) | `open` or `warm-up`, `no answer from the camera process in 30 s` | `open-failed` at `open`; `not-ready` at `warm-up` |
| `CameraGroup._mark_ended` (`camera_group.py:348`) | `open` or `streaming`, `camera process ended (exit code <n>)` | `process-ended` |
| `CameraGroup._end_stuck_camera` and the stuck writer of `_collect_results` ([recorder.md](recorder.md) 5.3) | `recording`, `disk stall` | `disk-stall` |
| The stall watch of 4.10 | `streaming`, `no loop pass for 2.5 s` | `stalled` |
| `CameraWorker.start` when the start method is `fork` (4.12) | `open`, the text of 4.12 | `start-method-fork` |

The new sources set their own codes (4.3.6, 4.4.8): `not-found`, `no-access`, `no-permission`,
`camera-in-use`, `no-native-jpeg`, `previous-process-alive`, `format-changed` and the others above.

Call names (`call`, `busy_call`): the values of [cert 10.2] `open`, `s-fmt`, `reqbufs`, `streamon`,
`session-start`, `first-frame`, and these that certify must add: `querycap`, `s-parm`, `qbuf`, `dqbuf`,
`poll`, `streamoff`, `close`, `s-ext-ctrls`, `g-ext-ctrls`, `add-input`, `lock-config`,
`stop-running`, `cmio-set`, `cmio-get`, `activate`, `set-mode`, `read-sample`, `flush`, `shutdown`.
Not built [cert 3.5.15 P1]: `reader-release` and `control-release` (the release of the source reader
and of the control interfaces in the close of Media Foundation), and `set-controls` (a control call
that hangs; a control call that returns an error records no call).

#### 4.6.4 What certify must still add or change

[cert 18.1] applied the earlier list of this section. These items remain:

| # | Item | This spec | Change in certify |
|---|---|---|---|
| 1 | macOS control routes | A1, A2, A3 are product candidates in any unit (4.4.6) [U] | `exposure_unit` adds `ev`, `native`, `native-data`; `control_path` splits `cmio` into `cmio-native`, `cmio-absolute`, `cmio-native-data`; the -7 pass rule of `<label>:controls` and the `unit-mapping` failure apply only to a route with a time unit; 10.1 and 10.7 drop the seconds sentence |
| 2 | Drop rules of the control probes | per control, a route stays while it works on any model | 10.7 drop rows per control; 11.2 `approaches` per control (for example `a1-cmio-native:exposure`) |
| 3 | The record of checked models [cert 2.5] | 4.9 reads it | each `full` row holds the result of each turn-on check of 11.3, and for each of exposure, gain and focus the result of each route tried, keyed by `control_path` (`works`, `unproven`, `no`), so that 4.4.6 and 4.9 can read them |
| 4 | Turn-on rule | named checks of a full run [U] | the list of named turn-on checks in 11.3 (4.9 points to it); a failed exposure, gain or focus check does not block |
| 5 | Exposure fields | the names of [req 1.3a, 1.5]: `exposure`, `exposure_found_at_fps`, `exposure_search` | 5.3 reads them, not `exposure_found`; it waits while a camera is `adjusting` or `checking` |
| 6 | Restore keys | `restore_ok`, `restore_failed` in D-4 (4.7) | read them (18.2 item 4) |
| 7 | Long intervals | `long_intervals`, `long_intervals_with_seq_gap` in D-3 | read them (18.2 item 5) |
| 8 | No manual exposure | warning kind `no_manual_exposure`; code `no-manual-exposure` | use the snake_case kind where it reads a warning |
| 9 | USB link values | `"USB 1"`, `"USB 2"`, `"USB 3"`, `"unknown"` [req 3.2] | copy the product value into `usb_link` |
| 10 | JPEG reference key | VID:PID, no `bcdDevice` | 10.7 proof 1 keys by VID:PID |
| 11 | Citation | one repository state | each spec cites sections, not commit ids |

[cert 18.2] items 1 (`system:kernel`), 2 (the probe names of 10.7), 3 (the quick rows: certify owns
the record), 6 (the citation of 0) and 7 (4.4.10 filled) are applied here.

### 4.7 Restore of the controls at the close [U]

- At the first control read of each open, before any set, the source keeps each control value and
  its auto flag (`c_before`, `c_before_auto`).
- At the close, each source sets each changed control back to its "before" value and auto flag and
  reads it back, before `STREAMOFF`, `stopRunning` or the Media Foundation flush (A-20). A failed
  restore is logged and recorded (`restore_ok` false, `restore_failed` the count of controls); the
  close continues [A]. This is on by default on each system [U], for each native source and the fake
  source; the OpenCV source has no restore, because it cannot read the auto flag [ADR-Q2NY](../decisions/entries/Q2NY-choices-of-code-step-2.md).
- The restore is the one allowed call that may turn the camera's own auto exposure back on, when it
  was on before the open: the camera is then closed, so auto exposure is not a mode [U].
- The setting `SKELLYCAM_RESTORE_CONTROLS=0` turns it off, for a debug run only [A].
- A camera that failed, hung or was removed is not opened again to restore it [U]. The restore runs
  only inside the close of an open camera. It is skipped when the failure of the shared loop is a
  wedge: the code `hung`, `stalled` (for example the stall rule of [W 9.5], which sets no error of the
  source) or `device-removed` (the wedge of [cert 10.7] item 5; `WEDGE_CODES` of `failure_codes.py`,
  which also holds `process-ended`, a code that never reaches a close).
  The loop then calls `close(restore=False)`, so a camera that can be wedged gets no set and no
  read-back [ADR-Q2NY](../decisions/entries/Q2NY-choices-of-code-step-2.md). A restore call that
  hangs ends the close as hung, within the bound of one call [W 6.6].
- Each other failure of the loop gets the restore at its close: for example `rate-low`, `not-ready`,
  `open-failed` and a lost heartbeat of the server ([`recorder.md`](recorder.md) section 9), which is
  not a camera fault (a decision of the user of 2026-11-21) [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md). A source that holds a stream error
  of its own (the Media Foundation source after an error of `OnReadSample`, the fake after its removal)
  restores too, unless the code of that error is a wedge code (for example `device-removed`); a
  `stream-error` or a `usb-bandwidth` error restores.
- The "before" values survive the camera process [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md).
  The source keeps the shared record `controls_before` of `CameraStatus` (a JSON array that the main
  process makes with the status). For each control that this app changed, it holds the name, the
  "before" value and auto flag, and the value and auto flag that this app set last. Before each set,
  the source writes the value that it asks for; after the set, the value that the camera read back.
  A restore with no failure clears the record. A camera process that ends with no restore (a kill, a
  hang, a failed loop) leaves the record. At the first read of a later open, a control of the record
  whose current read still holds the value that this app set last (the same auto flag, and with auto
  off a value not more than one step from that value) takes its "before" value from the record, in
  place of the value that the camera reads then; the record drops each other control. The step is the
  `step` of the range of that control at this open (`c_step`). A control with no range, or with a step
  that is not above 0, needs the same value [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md).
  Reason: a camera can round a value at a new open. A Logitech C930e read back manual exposure -8 in
  the open that set it, and -7 at the next open; a Logitech C922 read back -8 in both. The user decided
  on 2026-11-23 (Q584): "as long as the frame rate still passes, a one step exposure tolerance is fine
  for all cameras". The tolerance changes only which value the close restores [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md). It does not change
  the exposure that the app sets or the rate of the camera while the app has it. No rate check judges
  the restored value. The rate of each open is judged as before: the start-up rate check of [W 10.2]
  for a manual value, the check after the search in `AUTO` [req 1.3b]. T-UNX-91 shows that an open
  that used the record one step away still runs the normal rate check. Thus the "before"
  values stay the values of the
  first open, the close of the next open restores them, and a value that another program set meanwhile
  stays. What is left: another unit of the same model in the same USB port (a camera with no serial
  number has the same `camera_id` there), or a value that another program set to not more than one step
  from the value that this app set last, takes the "before" values of the record. A record that a kill tore during its
  write reads as no record. "Apply again" keeps the record (`reset_for_start`), and
  `CameraGroupManager` keeps it from a group close to the next group, for the life of the app, also
  when the close raises for a process that cannot be killed. A group close does not restore a camera
  whose process ended: the rule above forbids an open only to restore. The camera process finds the
  record through `RESTORE_RECORDS` of `capture/source.py` [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md).
  The record is also on disk (4.7.1), so that a restart of the app keeps it.

#### 4.7.1 The restore record on disk [U Q608]

The user decided on 2026-11-23 (Q608) that the restore record stays on disk, so that a restore survives
a kill of the whole server [ADR-81RE](../decisions/entries/81RE-decisions-of-the-user-on-the-restore-file-the-take-rate-and-pace-tests.md).
Before, the record was only in the memory of the server: after a kill, a new server read the manual
value of this app as the camera's own value, and three cameras stayed in manual exposure (a real-camera
run of 2026-11-23). The agent chose the details [ADR-HQE5](../decisions/entries/HQE5-choices-of-fix-lane-4.md).

- **Place.** One file for each camera in the folder `camera_restore` of the data folder of the app
  (`get_default_skellycam_base_folder_path()`, the folder of `camera_checks.json`). Never in a
  recording folder. The functions of `skellycam/core/camera/capture/restore_store.py` take the folder
  as an argument. Only the server of the app (`get_or_create_camera_group_manager`) gives the default
  folder. Each other `CameraGroupManager` (certify, the tests) has no folder unless its caller gives
  one; with no folder it reads and writes no file.
- **Identity input.** The input of the key is the stable identity of the camera that the product has:
  the lower-case Media Foundation link on Windows ([W 7.2]: it holds the USB port, or the serial
  number), the AVFoundation unique ID on macOS (it begins with the USB location ID), and on Linux
  `v4l2:port:<name>`, where `<name>` is the name of the USB interface folder in sysfs above
  `/sys/class/video4linux/video<n>/device` (for example `1-2.3:1.0`: the bus, the port chain and the
  interface, A-2). A `/dev/video<n>` path alone is never an input: its number can change. A camera
  with no stable input (the index alone, the USB IDs with the index, a Linux path with no sysfs
  folder) has no file, and no entry is used for it. Thus on Linux the key is the USB port, not the
  camera unit: a replug into the same port keeps the key, and the file of a port that is not used again
  stays until the salt changes.
- **Key.** The key is the HMAC-SHA-256 (64 hex digits) of the identity input with the salt of the
  folder. The salt is 32 random bytes in the file `.salt` of the folder (hex). Thus the name of a file
  differs on each machine, and a serial number cannot be found from it by a search. The main process
  computes each key and gives it to the camera process; a camera process never reads the salt.
- **The salt.** A salt that is missing (`FileNotFoundError`) or damaged (not 32 bytes of hex) means
  that no entry is used: the main process makes a new salt, and only after the new salt is in place
  it removes each entry file, which no key can match now. A missing salt is created with no replace
  (a hard link of a temporary file, or an exclusive create): when another server made a salt first,
  this server reads that salt back and removes nothing. A damaged salt is replaced (temporary file,
  then `os.replace`). A salt that exists and cannot be read (another `OSError`, for example a sharing
  violation or a folder in its place) means that no entry is used this time, and nothing is removed
  or written.
- **Mode.** On POSIX, `.salt` and each entry file have the mode 0600 (the user only).
- **Name and form.** `<key>.json`, UTF-8 JSON:
  `{"version": 1, "key": "<64 hex>", "vendor_id": <int or null>, "product_id": <int or null>,
  "written_utc": "<ISO 8601>", "record": {"before": ..., "names": [...], "set": ...}}`. The record is
  the record of 4.7.
- **Write (the camera process).** Each write of a record with names also writes the file: the first
  set of a control, each later set and each read-back that changes the record. The camera process
  writes it, in the call that writes `controls_before`. The write goes to a temporary file
  `.<key>.<pid>.tmp` in the same folder, then `os.replace` gives it its name: a reader sees the old
  file or the new file, never a part of one. A failed write is logged one time for each file and kind
  of fault in each process. A write error never fails an open or a set: the camera opens as with no
  file.
- **Removal.** The camera process removes the file when its record becomes empty: a restore with no
  failure, or a first read that drops each control of the record. The main process removes the file
  of each entry that it drops at a read, and each temporary file whose process does not run (a kill
  between the write and the replace).
- **Read (the main process).** At each group creation, the main process reads the file of each camera
  of the request that has no record in memory. It uses the entry only when the camera of the
  detection result with that key has the `vendor_id` and the `product_id` of the entry (detection
  refuses two equal `camera_id` values). Else it drops the entry. A camera that is not in the
  detection result keeps its file. The source then uses the entry under the rule above: a control
  whose current read holds the value that this app set last (within one step) takes its "before"
  value, and the record drops each other control
  [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md).
- **A valid record.** `names` is a list of names of `CONTROL_NAMES` (4.2); `before[name]` is
  `[present, auto, value]` with two booleans and an integer or null; `set[name]` is `[auto, value]`
  with a boolean and an integer or null. A boolean is not an integer here. Each other form is a
  damaged file. At the first read of an open, a "before" value with auto off that is outside the range
  of that control at this open (when the source knows the range) drops that control from the record.
  A fault in the use of the record at the first read drops the whole record; it never fails the open.
- **Two cameras of one model.** The identity input tells them apart: each input above holds the USB
  port or the serial number. What is left is the case of 4.7: two cameras of one model with no serial
  number that change ports between two servers. A replug resets most cameras to their own values;
  then the value rule drops the entry.
- **A damaged file.** A file that cannot be read, that is not JSON, or that has no valid record of
  version 1 is dropped: one log line, and the file is removed. A file of a later `version` is left as
  it is and not used (a later version of the app wrote it). A damaged file never fails a group
  creation or an open.
- **Age.** No age limit. The value rule is the guard: an old entry applies only when the camera still
  holds the value that this app set last.
- **Two servers.** One file for each camera, and a camera is open in one server at a time. The atomic
  replace keeps each file whole. The last writer wins.
- **Privacy.** The file holds the key (an HMAC with a salt of this machine), the USB IDs, the time and
  the control values. It holds no path, no link, no user name, no host name, no camera name and no
  serial number, although it is a local file. A tracked file never holds the path of the folder: the
  code finds it with its own function.
- **Tests.** T-UNX-96 to T-UNX-101 (`skellycam/tests/capture/test_restore_store.py`).

### 4.8 Threads

| Thread | Linux | macOS |
|---|---|---|
| Capture | `v4l2 capture` (4.3.3) | the serial dispatch queue (4.4.4) |
| Waiting place, camera loop, control thread | as [W 4.3] [W U16] | as [W 4.3] |
| Bounded-call workers | `capture/bounded.py` | the same |
| Notifications | none | the `NSOperationQueue` of M-7 |

No thread spins [W 4.3].

### 4.9 Source selection [U]

- Settings: `SKELLYCAM_LINUX_CAPTURE` (`opencv`, `v4l2`) and `SKELLYCAM_MACOS_CAPTURE` (`opencv`,
  `avfoundation`), on the model of `SKELLYCAM_WINDOWS_CAPTURE` [W 14.2] [A]. A wrong value gives an
  error that names the allowed values.
- The source of a camera is the first that applies [U]:
  1. The setting, when it is set.
  2. The record of checked models of [cert 2.5]: a `full` row of the model with the camera's backend,
     ABI and current OS key, in which each turn-on check that [cert 11.3] names passed [U]. The
     summary result of the row does not decide.
  3. A `verified` row of the shipped evidence file [cert 11.2] for the model, the backend, the OS key
     and the ABI.
  4. Else OpenCV.

  Native capture turns on for each camera model only. A `verified` OS key in `systems` of the
  evidence file turns on nothing by itself [ADR-F2KY](../decisions/entries/F2KY-rulings-of-the-user-after-the-third-consistency-check.md).
- A failed exposure, gain or focus check in that row does not block native capture. A control whose
  routes all have the result `no` is absent in the UI, and on Linux a camera whose exposure routes are
  all `no` gets the warning `no_manual_exposure` (4.5) [U]. A control with an `unproven` route is
  offered [cert 2.5] [ADR-FC1C](../decisions/entries/FC1C-choices-of-the-spec-integration.md).
- A new OS version is a new OS key: each model is unchecked again [U].
- Certify writes the record; the source only reads it (`camera_checks.py`). The certify spec owns its
  file, rows, key and levels [cert 2.5] [U]. A missing file, a file that cannot be read and a file
  that does not parse count as no rows; `camera_checks.py` logs that one time [cert 2.5].
- A camera whose native open fails with `no-native-jpeg`, or whose evidence row is `known-bad` for the
  native backend, opens with OpenCV when the default (not the setting) chose native [U]. The status
  shows `backend: opencv`.
- Certify always uses the native source, and the per-camera OpenCV fallback never runs inside certify
  [U]. Inside certify the source does not read the record: it tries each control again [cert 2.5].
- Detection is always native (4.2 item 7).

### 4.10 Main-process stall watch [U]

The signal and the watch [ADR-AC5B](../decisions/entries/AC5B-choices-of-the-third-consistency-check.md):

- The signal: a shared counter `alive_count` (`multiprocessing.Value("q", 0, lock=False)`) in `CameraStatus`.
  The main process creates it with the status. The shared camera loop adds one at the start of each
  loop pass (`CameraLoop._pass`). While frames arrive, a pass takes at most about 50 ms, also when the
  camera is paused (a sleep of 50 ms), waits at the gate (1 ms) or is `waiting`. Thus the counter
  works for each source (OpenCV, the fake source, Media Foundation, V4L2, AVFoundation) with no change
  to a source. The capture thread or the callback of a push source MAY also add one.
- No step of the loop in a watched state runs longer than the trip of the watch (2.5 s, below) outside a pass
  ([ADR-N2VE](../decisions/entries/N2VE-decisions-of-the-user-on-the-ci-triage-and-the-stall-watch-code.md) item 5, Q891):
  - The exposure search [req 1.3] and the check of [W 10.2] run inside the passes.
  - A wait of the loop in the recorder (`CameraTakeWriter.give` with a full queue, `end`, `abandon`)
    adds one to `alive_count` at least each 0.5 s: each blocking attempt of its wait is at most
    0.5 s. The stall rule of [recorder.md](recorder.md) 5.3 owns that wait (`disk-stall`), not this
    watch.
  - A reopen ([W 11.2]) sets `starting` before it stops the control thread, and again after it, before
    it closes the source, so the watch is off during that close.
  - The record start opens the files of the take on the loop thread while the group is paused; the
    loop adds one before and after that open, and the watch is off while `should_pause` is set.
  - The loop sets `closing` at the start of each close (also a close that the group flags start), so
    the watch is off during the close.
- When a driver call or PyObjC holds the GIL of a camera process, the counter stops: that is the
  signal (M-8).
- The watch: `CameraGroup._watch_camera`, in the watch thread (each 0.1 s). It trips when
  `alive_count` did not change for 2.5 s while the camera process is alive, the state is `waiting`,
  `adjusting`, `checking`, `too_slow` or `ready` (also `ready` with a recording), the camera reported
  no failure, and none of `should_pause`, `should_close` and `closing` is set. It is off in `starting`
  (the ready limit of [W 9.3] applies) and during the close (the bounded steps of [W 6.6, 6.9] apply).
  The limit is 2 s, the limit of the in-process rule of [W 9.5] (item 14 of
  [ADR-22EJ](../decisions/entries/22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md); Q850 of
  [ADR-88HQ](../decisions/entries/88HQ-decisions-of-the-user-on-q842-to-q856.md) replaces the 3 s of ADR-Q2NY
  item 1), plus a head start of 0.5 s for the in-process rule.
- The order of the two rules (Q863 of [ADR-3RJJ](../decisions/entries/3RJJ-decision-of-the-user-on-the-order-of-the-two-stall-rules.md)): when frames stop, the in-process rule decides, not
  the watch. The watch counts from the later of the last loop pass and the last frame arrival. The last loop pass
  is never the earlier one: the loop adds to the counter at the start of each pass, after the arrival and the waits
  of the pass before. The first pass in `waiting` after an open (also the open of a reopen, which runs inside a
  pass) attaches the rings and starts the clock of the in-process rule at that attach (`last_arrival`); the loop
  then adds one more to the counter, before its read, so this path keeps the order too ([ADR-N2VE](../decisions/entries/N2VE-decisions-of-the-user-on-the-ci-triage-and-the-stall-watch-code.md) item 5, Q891).
  Thus the watch counts from the first round (each 0.1 s) that sees the last change of the counter. The in-process rule ends a read 2 s after the later of the last arrival and the last wait of the loop,
  thus at most 2 s after that change. The watch waits 0.5 s more, the head start (Q874 of
  [ADR-EQ3K](../decisions/entries/EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md)). In the head start
  the camera process wakes from its read and reports the failure in this order: one write of `failure` into
  `info` (from then on the watch is off), one put on the queue of the setup failures (the main process reads that
  queue only to empty it), then the state `dead` ([ADR-N2VE](../decisions/entries/N2VE-decisions-of-the-user-on-the-ci-triage-and-the-stall-watch-code.md) item 5, Q891). The `info` lock waits no more than one read or one
  write of another holder, because each holder of a live camera holds it only that long. A camera process that
  cannot do this in 0.5 s is a stalled camera for the watch.
- In a take, one pass can hold the first lock wait of a frame decision (1.5 s), the read (one frame period) and
  the first attempt of `give` with a full queue (0.5 s; the next attempts add to the counter): about 2.03 s at
  30 fps with no new count, about 0.47 s before the trip. A first wait of 0.5 s for the lock of a status array on
  top would pass the trip. It is not expected in a live camera process: each camera process gets new arrays, and
  the main process holds such a lock only for one read or one write ([ADR-N2VE](../decisions/entries/N2VE-decisions-of-the-user-on-the-ci-triage-and-the-stall-watch-code.md) item 5, Q891, which corrects item 5 of
  ADR-EQ3K).
- A loop that makes no pass (a hung call, a suspended process) is `stalled` at most 2.6 s after its last pass:
  at most 0.1 s until a round of the watch sees the change, then 2.5 s. Its process ends at most 1 s later (the
  `kill`).
- The two rules give `dead` with the code `stalled`, and neither restores the controls: `stalled` is a wedge
  code (4.7). Only the reason text differs. When the watch trips, it also ends the process: on Windows `terminate` ends it at once, so the
  camera does not finish its take files (the take level completes them, [recorder.md](recorder.md) 7.4) and its
  close diagnostics are lost; on POSIX the SIGTERM handler only sets the stop flag, so the loop can still fail and
  end as usual, and the `kill` after 1 s cuts off only an end that takes longer. The counter has no lock: a process
  stopped inside its add keeps the lock. Each other scalar of `CameraStatus` has no lock too. A process
  that ends while it holds a lock keeps it for ever. Thus, for the lock of each JSON array of
  `CameraStatus`, the first call of a stretch with no lock waits at most 0.5 s and logs one line; the
  next calls try with no wait until the lock comes again. A later call of that stretch that finds the
  camera process ended logs one more line [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md). A call with no lock goes on with no lock. The
  main process stops the tries for a status only when the camera process of that status has ended.
  "Apply again" always gives the new camera process new arrays. The arrays go by name, not by object.
  Each read tolerates torn JSON: it reads again up to 3 times, then gives the last good value. A
  main-process write of `info` with no lock stays in the main process until a write with the lock. The
  heartbeat value (its one writer: the heartbeat thread), the global kill flag, the shutdown flag of the
  group and the first frame of a take (their writers: the main process only) have no lock either. The
  last frame of a take is read and written with no lock (one aligned 8-byte value), except in three
  places. The read of each frame decision keeps the lock, because the end of a take holds it from its
  read of the gate count to its write: its first wait in a stretch with no lock is at most 1.5 s, and
  the next reads try with no wait until the lock comes again. A frame decision outside a take (the first
  frame of the take is -1) reads no last frame and takes no lock, so a new camera process does not wait
  at its first frame [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md). After a camera
  process is killed while it holds that lock, each later take of the group ends with the error below
  until the cameras are closed and opened again. The two check-then-set blocks wait at most
  0.5 s for the lock: the end of a take then ends with the `take_error` "no lock of the last frame of the
  take in 0.5 s", and a camera that ends with no take level ends its part of the take alone with the
  error "camera `<id>`: no lock of the last frame of the take in 0.5 s"; a write error that `abandon()`
  gives replaces that text [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md). A failed read of the app state is
  logged, and the websocket sends the state at the next tick; it sets no kill flag
  [ADR-QJH6](../decisions/entries/QJH6-choices-of-the-fix-lane.md).
- The setting `SKELLYCAM_STALL_WATCH=0` turns the watch off. The group reads it when it is made, and logs
  at its start that the watch is off [ADR-Q2NY](../decisions/entries/Q2NY-choices-of-code-step-2.md).
- When it trips, the main process removes the camera from the gate, marks it `dead` with the failure
  `{stage: "streaming", reason: "no loop pass for 2.5 s", code: "stalled"}` (Q875: the text stays; the stable key
  is the code `stalled`), clears
  `recording_in_progress` and marks the stop as intended (so the end of the process waits for no save of
  a take, and the registry logs no crash), and ends its process (`terminate`, then `kill` after 1 s) [U].
  The `camera_dead` warning of a take gives that reason ([recorder.md](recorder.md) 7.4).
- A pull source whose `read_frame` blocks for more than 2.5 s in a watched state is a stalled camera.
  This is by design: the OpenCV source holds one lock across `grab()`, `retrieve()` and `set_controls`,
  so a read or a control call that blocks longer than the limit ends the camera [ADR-Q2NY](../decisions/entries/Q2NY-choices-of-code-step-2.md).
  When `read_frame` returns, the in-process stall rule of [W 9.5] (`no frame for 2 s`) comes first, by the
  head start above (Q863). The camera is then `dead`, and the watch is off. This watch also catches a
  `read_frame` that never returns (for example an OpenCV `grab()` that blocks), which the in-process
  rule cannot see.

### 4.11 CI

- The capture workflow runs the new fake-layer tests in its three jobs, with no new job [A].
- The timing tests (T-UNX-18, T-UNX-45, T-UNX-75, T-UNX-79) have the marker `capture_timing`, which the macOS
  job runs in its own step (capture.yml) [A].
- `capture-linux` also runs `capture_linux_runner` tests (6.3). One step runs `sudo modprobe vivid ||
  true`; the `v4l2_vivid` tests skip without a vivid node. Whether a hosted runner can load vivid is
  not known [K23] [NV]; no done item depends on it.
- `capture-macos` also runs `capture_macos_runner` tests; `uv sync` installs PyObjC through its markers.
- The build workflow runs T-UNX-88 on its macOS jobs.
- The recorder workflow sets `SKELLYCAM_NO_SKIP` to `skellycam/tests/take_recorder/test_connection.py`:
  a skipped test of that file fails the run (`skellycam/tests/conftest.py`). The guard reads the run
  reports and the collect reports, so it also catches a skip of the whole module (`pytestmark`,
  `pytest.skip(..., allow_module_level=True)`, `pytest.importorskip`). Before, a module skip of
  that file (the connection tests before the connection commit) made the run green on each system,
  and the first run of these tests on Linux came three days after the code [ADR-HQE5](../decisions/entries/HQE5-choices-of-fix-lane-4.md).
  The capture and recorder workflows also run on each push to `dom/integration`.

### 4.12 The start method of a camera process [A]

- The user decided the route on 2026-11-23 (Q651) [ADR-T34M](../decisions/entries/T34M-decision-of-the-user-on-the-start-method-of-camera-processes.md); the agent chose the details
  [ADR-HQE5](../decisions/entries/HQE5-choices-of-fix-lane-4.md).
- The library does not set the start method: `import skellycam` changes nothing, and a host program can
  call `set_start_method` after the import.
- The program entry point of skellycam (`skellycam/__main__.py`, also the entry of the frozen app and of
  `entry_point`) sets the start method `spawn` as its first action, before any `multiprocessing`
  object exists, on each system. Where `spawn` is the default (Windows, macOS) this changes nothing.
  The test session does the same in the root `conftest.py`, so the tests run as the app runs.
- A host program owns the start method of its process. Nothing is decided for FreeMoCap: a change there
  is a candidate of a wider review of FreeMoCap on Linux ([`open-work.md`](../decisions/open-work.md)).
- The start of a camera process refuses the method `fork`. The user decided the refusal on Linux; the
  agent applies it on each system (with `fork` on macOS a fork of a process with threads is not safe
  either). The camera does not start:
  it becomes `failed` with the code `start-method-fork`, the stage `open` and the reason "the host
  program must call multiprocessing.set_start_method('spawn') before it creates a multiprocessing
  object". The apply request answers at once with that failure, not after the limit of 30 s. Reason:
  with `fork` the known result is a camera process that never answers (below). `spawn` and
  `forkserver` start. The server of `forkserver` is a new interpreter that `multiprocessing` starts by
  exec (at the first start, whenever that comes), not a fork of the main process: it holds no PyAV
  object and no thread of the main process, and each argument goes to its child by pickle, as with
  `spawn` (a check under Linux: 43 threads in the main process after PyAV, 1 in the server, and the
  child ran). The limit: the server imports the main module of the host (`__main__` is loaded first by
  default), so a main module that starts threads at its import gives those threads to the server. The
  default of Python 3.14 on Linux is `forkserver`.
- Not chosen: a `spawn` context object inside skellycam for each object that it shares with a camera
  process. The host makes some of these objects in its own context and gives them to skellycam: the
  kill flag (a `Value` with a lock, through `WorkerRegistry` and `CameraGroupIPC`), the log queue of
  `skellylogs` (`LogsTopic.publication`), and the queues, values, events and pipes of the workers of
  FreeMoCap that start through `ManagedWorker`. A lock of the `fork` context cannot go to a `spawn`
  child (`RuntimeError`), so this needs a change of the API across the two repositories.
- Not chosen: the method `spawn` set at `import skellycam`. A host that made a `multiprocessing` object
  before the import (FreeMoCap makes its log queue first) has `fork` already, and a host can no longer
  set the method after the import.
- Reason (CI run 45214740615, reproduced on Linux): a forked camera process of a main process that
  had decoded a video with PyAV (T-REC-31 before T-REC-44; in the app, the player) freed a PyAV
  `VideoReformatter` right after the fork. `sws_freeContext` waited for the FFmpeg slice threads,
  which the fork does not copy. The camera process never answered, and the group gave it
  `open-failed` after 30 s. A fork of a process with threads can deadlock in this way in each library
  with threads; Python 3.13 warns about it.
- skellycam needs the start method `spawn` or `forkserver` for its camera processes on each system. A
  host that sets `fork` gets `start-method-fork` for each camera.
- What `spawn` asks: each argument of a camera process pickles (Windows asks the same today); each
  shared object comes from the default context, which is then `spawn`; the `parent_process()` guards
  work as on Windows. A camera process opens each shared lock and array by its name while it starts,
  so the main process keeps the arrays of the last two replacements (`CameraStatus.retired`): another
  camera process can still start with an old array. Older ones are freed.
- Cost: on Linux each camera process imports the package again (as on Windows), so its start takes
  longer. The stagger of the starts stays a Windows rule (`_SPAWN_STAGGER_SECONDS`).
- Certify on Linux: before, its session child (a `spawn` child) got the kill flag of the fork
  context, and each run stopped with a `RuntimeError` at its start. With `spawn` as the default it
  runs. Its session object tells a live child by the sentinel of the process, not by `is_alive()`:
  `kill_tree` reaps the child with psutil, and on POSIX `is_alive()` of a child that another call
  reaped stays true, so the run never ended after a cancel.

### 4.13 Exclusive access of a camera (lands with phase 7)

Status: accepted by the user on 2026-11-25, with the choices of the agent (Q813, [ADR-5PAR](../decisions/entries/5PAR-decisions-of-the-user-on-the-control-read-the-holder-and-the-exclusive-access-drafts.md)). It lands with phase 7. The rules
come from the decisions of the user of 2026-11-25
([ADR-AA4X](../decisions/entries/AA4X-decisions-of-the-user-on-exclusive-access-of-a-camera.md)). The details
that the user did not decide are choices of the agent
([ADR-FR2J](../decisions/entries/FR2J-choices-of-the-exclusive-access-and-overlap-specs.md)). Marks:
**[Qn]** is decision Qn of ADR-AA4X; **[X n]** is item n of ADR-FR2J; **[S n]** is a source of the research in
[the evidence of ADR-AA4X](../decisions/evidence/AA4X-exclusive-access-research.md).

The rule is [W 21.1] and [W 21.2]: skellycam needs exclusive control of each camera (Q771); it holds the strongest
lock of the OS (Q781); only the processes of the same camera group are own processes (Q796); a camera that it
does not hold so is `camera-in-use` and is not used for a take; a loss during a take keeps the take, warns, and
marks the interval and the control changes (Q783) with the take marks of [W 21.7]; the warnings and the line
before a take are those of [W 21.8].

#### 4.13.1 Linux [Q786]

1. **Buffer ownership.** It stays as A-14: the first file handle that allocates buffers owns the stream, and each
   other handle gets `EBUSY` at `REQBUFS`, `CREATE_BUFS`, `STREAMON`, `S_FMT` or `S_PARM` [S9, S10].
2. **The RECORD priority.** Right after `open()` (step 2 of 4.3.2), the source calls `VIDIOC_S_PRIORITY` with
   `V4L2_PRIORITY_RECORD` (Q786). "Only one file descriptor can have this priority, it blocks any other fd from
   changing device properties" [S11]. The V4L2 core then returns `EBUSY` to each other handle for `S_CTRL`,
   `S_EXT_CTRLS`, `S_FMT`, `S_PARM`, `REQBUFS` and `STREAMON` [S12]. An `EBUSY` from `S_PRIORITY` means that
   another handle holds RECORD: code `camera-in-use`, stage `open`, `busy_call` `s-priority`. The priority goes
   with the `close()` of the file.
3. **Control events.** After `STREAMON`, the source subscribes to `V4L2_EVENT_CTRL` for each control that
   `QUERY_EXT_CTRL` lists, one `VIDIOC_SUBSCRIBE_EVENT` for each control id (Q786) [X 32]. The capture thread also
   waits for `POLLPRI` in its `poll` (4.3.3 step 1) and reads each event with `VIDIOC_DQEVENT`. uvcvideo sends more
   events than the changes of other handles [S14, `uvc_ctrl.c`]: an event that only changes the flags also reaches
   the handle that made the change; a change of a master control (for example `V4L2_CID_EXPOSURE_AUTO`) sends events
   with the flags and the value of its dependent controls (it sets the flag `inactive` of
   `V4L2_CID_EXPOSURE_ABSOLUTE`); and a change that the device makes itself (auto update, an asynchronous status
   event) reaches each subscriber. Thus the source counts an event as a change by another process only when:
   - its `changes` field has `V4L2_EVENT_CTRL_CH_VALUE` (an event with only the flags change is ignored);
   - the control is not in auto (a value event of a control in auto is the camera at work);
   - it is not a dependent control within 1 s of an own set of its master [X 31].

   Such an event gives the warning `control_changed_by_other` and, during a take, a take mark
   `camera_control_changed` at the row of the next frame [W 21.6, 21.7]. Under the RECORD priority each other handle
   gets `EBUSY` at `S_CTRL` and `S_EXT_CTRLS` [S12], so such events are expected to be zero. The ones that remain come
   from the gap of item 5, or from a fact that is not verified [NV]. The source does not set
   `V4L2_EVENT_SUB_FL_ALLOW_FEEDBACK` [S15, NV: the meaning of the flag is cited from memory].
4. **Names.** At an in-use failure, the source names the holder (Q786, Q768): it reads the links of
   `/proc/*/fd` that point to the node of the camera, and `/proc/<pid>/comm` of each such process. This works only
   for the processes of the same user: the links of other users need a `PTRACE_MODE_READ_FSCREDS` check [S13].
   With no name, the reason is "in use by another program". The source reads `/proc` only after an in-use failure,
   never before an open (Q768) [X 14].
5. **The gap** (Q786). The raw extension-unit call `UVCIOC_CTRL_QUERY` gets no priority check [S10], and it gives no
   `V4L2_EVENT_CTRL` event [NV: inferred]. Thus a vendor tool can change an extension-unit control during a take,
   and skellycam does not see it.
6. **Mid-take.** No other handle can start a second stream while the source owns the queue [S9]. Thus on Linux only
   a control change can happen during a take.
7. Diagnostics keys [X 15]: `priority_record` (true when `S_PRIORITY` RECORD succeeded), `ctrl_events_other` (the
   count of control events from other handles), `holder_names` (the count of named holders; never the names).

#### 4.13.2 macOS [Q787] (this reverses M-11)

M-11 allowed sharing: "the source never fails for sharing alone". Q787 reverses it:

1. **Refuse a camera in use.** Before step 3 of 4.4.2, the source reads `isInUseByAnotherApplication` of the
   device [S17]. True: code `camera-in-use`, stage `open`, reason "in use by another program". macOS does not name
   the other program [S17, S18].
2. **Hold the configuration lock.** The source takes `lockForConfiguration` before `startRunning` (4.4.2 step 5)
   and holds it to the close (Q787) [X 16], also through the variant restart of 4.4.3 item 2. Apple's docs advise to hold it only when needed [S16]. skellycam needs
   settings that do not change. Another process then gets
   `AVErrorDeviceLockedForConfigurationByAnotherProcess` (-11817) [S20]. When the source itself cannot take the
   lock for that reason, the code is `camera-in-use`, stage `open`, `busy_call` `lock-config` [X 33]. The close
   (4.4.7) unlocks after the restore of 4.7.
3. **Watch the flag.** The source observes `isInUseByAnotherApplication` with key-value observing from the first
   frame to the close [S17]. A change to true gives the warning `camera_shared` (with no name) and, during a take,
   starts the take mark `camera_shared` [W 21.5, 21.7] (Q783). A change to false ends the interval. `by=` is
   `another program`.
4. `format-changed` stays: another app can change the active format [NV]. It is a failure, stage `streaming`, as
   in 4.4.8.
5. **Hog mode** (Q787). CoreMediaIO has `kCMIODevicePropertyHogMode`: "the process that currently owns exclusive
   access" [S18]. [NV] whether a UVC camera lets a client set it. The certify probe `probe:<model>:hog-mode`
   ([cert 20.4]) checks it. If the probe passes on the models of the shipped file, phase 7 sets hog mode at the
   open, and an open whose hog mode another process holds is `camera-in-use`. Until then the source does not set
   it.
6. **The gap.** Neither lock covers raw UVC requests on endpoint 0 through IOKit [NV: inferred]. Vendor tools and the
   probes A5 and A6 of [cert 10.7] use them.
7. Diagnostics keys [X 15]: `config_locked` (true while the source holds the lock), `in_use_flag_changes` (a
   count).

#### 4.13.3 What changes in the sections above

- A-14 and 4.3.2: the `S_PRIORITY` call is a new step 2a; `s-priority` is a new call name of 4.6.3 [X 15].
- M-11 is replaced by 4.13.2. Its certify line becomes `<label>:in-use` with `refused` as the only pass [cert 20.2].
- 4.4.2 step 5 and 4.4.7: the configuration lock is held from the start to the close.
- Table 4.4.8: `AVErrorDeviceLockedForConfigurationByAnotherProcess` at the open gives `camera-in-use`.

## 5. Parity with the Windows spec

States: **same**; **differs** (how); **n/a** (why); **unknown** (certify must show it).

### 5.1 Decisions and answers of the Windows spec

| IDs | Linux | macOS |
|---|---|---|
| D1 (pure Python, no compiled extension, no Rust) | same: standard library | same: PyObjC |
| D2, D19 (3a, 3b, 3c; YUY2 and NV12) | differs: MJPG only in 7a | differs: MJPG only in 7b |
| D3, D47, D48 | same: section 6 | same |
| D4, U8 (no H.264) | same | same |
| D5 (phase order) | differs: phase 7 moves before phase 0 [U] | the same |
| D6 | same: `V4L2Source` | same: `AVFoundationSource` |
| D7 (comtypes) | n/a: no dependency | differs: PyObjC (7.2) [U] |
| D8, U1, T-CAP-43, T-CAP-76, T-CAP-88 | differs: `SKELLYCAM_LINUX_CAPTURE`; OpenCV until a model passes the gate of [cert 11.3] [U] | differs: `SKELLYCAM_MACOS_CAPTURE` |
| D9 | n/a | n/a |
| D10, U12, U16 | same: A-13 | same if M-8 holds |
| D11, D12, D13, W6 | same: A-1, A-2, A-14 | same: M-1, M-2; in use differs (M-11) |
| D14, U11 | same | same |
| D15, D16, D17, D18, U7, U10, U15 | same | same |
| D20, D21, D22, D23, D24 | same | same |
| D25 (slow text) | differs: the texts of [req 1.5a] on each source [U] | the same |
| D26, D27 | same | same |
| D28 | same; `sample_ns` from A-9 | same; `sample_ns` from M-9 (unknown until certified) |
| D29, D35 (exposure modes, unit) | differs: [req 1] on each source [U]; unit map A-18 | differs: [req 1]; the chosen CoreMediaIO route and its scale (4.4.6) [U] |
| D30, D31, D32, D33, D36 | same; `adjusting` added [req 1.3b] | same |
| D37 | differs: never fires for exposure (no camera auto) | the same |
| D34 | differs: also from `sequence` gaps (A-10) | differs: from drops and sequence numbers (M-10) |
| D38, D39, U6 | same (4.3.8) | same (4.4.9) |
| D40, U9 | differs: adds `code` [U] | the same |
| D41 | same | same |
| D42, T-CAP-50 | n/a [W 16.7 (g)] | n/a |
| D43, D44 | same: 4.3.5 | differs: through CoreMediaIO only; else absent |
| D45 | differs: the USB link is in this step [U] | the same |
| D46, W2, U23 | same while OpenCV is the fallback | same |
| D49 | differs: certify checks (6.7) | the same |
| U2, U13, U14, U17 | same | same |
| U3 | differs: certify `group:take-30` | the same |
| U4, U5 | n/a | n/a |
| U18 | differs: the package runs on Linux only; its tests run on each OS [Q 1] | the same |
| U19 to U22, W1, W3 to W5, W7, W8 | same | same |

### 5.2 Rules of the body of the Windows spec

| Rule | Linux | macOS |
|---|---|---|
| 4.2 `CapturedFrame`; `NO_SAMPLE_NS` rule | same | same |
| 4.3 threads, waiting place, error marker | same | same |
| 6.1 process set-up | n/a | differs: `PyObjCLayer` loads the frameworks and sets the CMIO run loop |
| 6.2 enumerate at each open, match by `camera_id` | same | same |
| 6.3 read-back of the mode | same (A-5, A-6) | same (M-6) |
| 6.4 first frame in 5 s | same | same |
| 6.5 callback steps | same as 4.3.3 | same as 4.4.4 |
| 6.6 bounded calls, hard end | differs: 11 s for probe-and-commit ioctls (A-13) | same if M-8 holds |
| 6.7 in use, removed, stall | differs: table 4.3.6 | differs: table 4.4.8 |
| 6.8 controls in one bounded call | same | same |
| 6.9 close order | differs: 4.3.7 | differs: 4.4.7 |
| 7.1 detection child | same | same |
| 7.2 `camera_id` hash | same function, new input (A-2) | same function, new input (M-2) |
| 9.5 stall watch | same | same |
| 11.1 search | differs: replaced by [req 1.3] | the same, on the chosen route |
| 12 stage names | same; adds codes | same |
| 13 uncompressed modes | n/a in this step | n/a in this step |
| 14.1 forced auto exposure on Linux | differs: ends for the native source [U] | n/a |
| 15 CI | same jobs, more tests | same |

### 5.3 Tests of the Windows spec

| T-CAP IDs | Linux | macOS |
|---|---|---|
| 01 to 17, 19 to 21, 25 to 33, 35 to 40, 44, 61 to 67, 70 to 75, 80 to 87, 89 to 91, 99 to 103, 105 to 113 (fake source and OpenCV fake) | same: they run in CI today [W 16.7] | same |
| 18, 34, 41, 42, 104 (exposure and slow text) | differs: changed by [req 1]; the camera requests spec owns the list of edits, applied in [W 16.2] | the same |
| 22 (HRESULT map) | differs: T-UNX-12 | differs: T-UNX-32 |
| 23 (duplicates refused) | differs: T-UNX-08 | differs: T-UNX-42 |
| 24, 106 (`camera_id` input) | differs: T-UNX-07 | differs: T-UNX-41 |
| 43, 76 (Windows setting) | differs: T-UNX-61 | differs: T-UNX-61 |
| 45 (pin of comtypes) | differs: T-UNX-63 | differs: T-UNX-63 |
| 46 (module on the runner) | differs: T-UNX-80, T-UNX-81 | differs: T-UNX-84 to T-UNX-87 |
| 47 (no compiled extension) | same | same |
| 48 (detection hang) | differs: T-UNX-09 | differs: T-UNX-43 |
| 49 (idle CPU, local) | differs: T-UNX-79 on the runners (not calibrated) | the same |
| 51 | differs: certify `detect` while a session streams: unknown | the same |
| 52 | differs: certify `<label>:opens`, `<label>:native-jpeg:*` | differs: the same (M-5): unknown |
| 53, 94 | differs: certify `<label>:rate` | the same |
| 54, 93 | differs: certify `<label>:rate:<mode>` | the same |
| 55, 96 | differs: certify light rule [cert 4.6] | the same |
| 56 | differs: certify `<label>:in-use` | the same (M-11) |
| 57, 97 | differs: certify `<label>:exposure:<base>` | differs: the same, if M-15 holds |
| 58, 95 | n/a: no hot-unplug test [U] | n/a |
| 59 | differs: certify `<label>:clock:*` | the same |
| 60, 98 | differs: certify `group:take-30` | the same |
| 68, 69 | n/a in this step | n/a in this step |
| 77 | n/a: no camera auto mode (4.5) | n/a |
| 78 | differs: certify `<label>:control:*` | differs: the same, CoreMediaIO |
| 79 | differs: certify `<label>:detect`, `<label>:modes:granted:*` | the same |
| 88 | n/a | n/a |
| 92 to 98 | retired: OpenCV needs no test [U] (item 10 of ADR-22EJ) | retired |

## 6. Test list

### 6.1 Kinds and markers

- **fake**: a test with `FakeV4L2System`, `FakeAVLayer` or the fake source. It runs on Windows, Linux
  and macOS, and in the three CI jobs [U].
- **windows**: a Windows-only test of `media_foundation/` [W U18], for what this spec adds there.
- **linux-runner**: real Linux kernel, no camera. Marker `capture_linux_runner`.
- **macos-runner**: real macOS and PyObjC, no camera. Marker `capture_macos_runner`.
- **vivid**: needs a vivid node. Marker `v4l2_vivid`.
- **build**: the build workflow on the frozen app.
- **certify**: a check of a certify run on a real system [cert 10.2]. These are the hardware tests of
  the Linux and macOS sources [U], and T-CAP-92 to T-CAP-98 are retired [U]. Section 6.7 maps them.
- Timing tests carry `capture_timing` (4.11).

The pass thresholds that this list adds are [A]. They can change when the tests are written.

### 6.2 The seams

- `V4L2System` (`v4l2/device.py`): `open(path, flags)`, `ioctl(handle, request, struct)` (mutates the
  struct, raises `OSError` with an errno), `mmap(handle, length, offset)`, `poll(handle, timeout_ms)`,
  `close(handle)`, `listdir(path)`, `read_text(path)`, `exists(path)`, `realpath(path)`,
  `abi()` (an ABI description: pointer size, `long` size, 64-bit alignment, and `x32`), `getgroups()`, `geteuid()`, `kernel_release()`. Each real method is one
  standard-library call. Paths are under `dev_root` (default `/dev`) and `sys_root` (default `/sys`).
- `FakeV4L2System` scripts: nodes with `QUERYCAP` data; a sysfs tree with USB devices, VideoControl
  and VideoStreaming interfaces and module parameters; formats, sizes and intervals; `S_FMT` and
  `S_PARM` adjustments; buffers with bytes, `sequence`, timestamp and flags; an errno or a hang at a
  given call and count; `poll` events; a node that disappears. It checks each ioctl number and struct
  size that the source sends.
- `AVLayer` (`avfoundation/layer.py`): `macos_version()`, `authorization_status()`, `devices()`,
  `open_device(unique_id)`, `configure(format_index, duration, variant)` (the order of M-6),
  `start(callback)`, `stop()`, `close()`, `to_host_ns(pts)`, `sync_clock_is_host()`, `cmio_objects()`,
  `cmio_get(object, form)`, `cmio_set(object, form, value)`, `avf_modes()`, `set_avf_mode()`,
  `responds_to(selector)`, `formats()`, `available_pixel_formats()`, `available_codec_types()`,
  `effects()`, and a notification callback (4.4.10).
- `FakeAVLayer` scripts: devices with `uniqueID`, `modelID`, transport and formats (fixed and ranged
  rates); a permission status; samples (a JPEG block, a decoded array, or none), PTS, a sync clock that
  is or is not the host clock, sequence numbers, drops; errors and notifications at a given time; a
  hang at a given call; CoreMediaIO controls that are present, absent, in seconds or in another unit,
  ignored or failing. It records the call order.
- Clock: each source and fake reads the time through the module name `perf_counter_ns`; a test gives
  a virtual clock, as `camera_loop.py` allows today (ADR-HP7D item 12) [A].

### 6.3 Linux fake tests (step 7a)

| ID | What it does | Pass criterion |
|---|---|---|
| T-UNX-01 | Size, offset and alignment of each struct of `abi.py`, built with LP64 types. | Each equals the reference values of linuxlib, for example `v4l2_buffer` 88 bytes, `timestamp` at 24, `sequence` at 56; each struct is 1024 bytes or less (A-13). |
| T-UNX-02 | Compute each ioctl number with `_IOC` from the LP64 struct sizes. | Each equals the reference of linuxlib, for example `VIDIOC_DQBUF` 0xC0585611, `VIDIOC_S_EXT_CTRLS` 0xC0205648. |
| T-UNX-03 | Pack a `v4l2_buffer`, a `v4l2_format` with MJPG 1280x720 and a `v4l2_ext_controls` with two controls. | The bytes equal golden bytes in the test. |
| T-UNX-04 | Detection on a fake tree: a C922 (serial), two identical cameras with no serial on two ports, a metadata node per camera, a v4l2loopback node, a node with `EACCES`. | Five cameras; metadata nodes skipped; the loopback `virtual: true`; the `EACCES` camera with `modes_read: false`; `id_source` `serial` and `id-path`; `has_serial` set; no serial or path in `diagnostics()`. |
| T-UNX-05 | Mode lists: discrete 1/30, 1/60, 1/15, 1001/30000; a stepwise range 1/60 to 1/5; YUYV formats; a size with only 15 fps. | `supported_modes` is the JSON of [W 7.3]: MJPG only, 29.97, 30.0 and 60.0, no 15; the stepwise range gives 29.97, 30 and 60 only. |
| T-UNX-06 | Detection with a fake USB link lookup of [req 3.4] (the lookup has its own tests, T-REQ-50). | `CameraDeviceInfo.usb_link` is the lookup value (`"USB 2"`); the source gives only `usb_alt`. |
| T-UNX-07 | `camera_id` inputs: a serial camera; a serial-less camera; the same serial-less model on two ports; the serial camera detected alone and with others. | The inputs of A-2; three different IDs; the serial camera has one ID alone and with others; the hash function is that of today. |
| T-UNX-08 | Two cameras with the same serial; then a forced collision. | Both fall back to the port input, with a log line; the forced collision is refused with an error that names both nodes [W D13]. |
| T-UNX-09 | Detection where `QUERYCAP` of one node hangs. | The detection child ends; the call returns within 5 s + 2 s with `hung`; the main process runs on. |
| T-UNX-10 | Open steps against the fake; spy the call order. | `open`, `REQBUFS(0)`, `S_FMT`, `G_FMT`, `S_PARM`, `G_PARM`, `REQBUFS(4)`, `QUERYBUF`, `mmap`, `QBUF` x4, `STREAMON`; the flags hold `O_NONBLOCK` and `O_CLOEXEC`; the controls are read before any set. |
| T-UNX-11 | `S_FMT` returns 640x480 for 1280x720; `G_PARM` returns 1/15 for 1/30; `G_PARM` returns 1001/30000 for a chosen 30000/1001; `G_PARM` returns 1/30 for a chosen 30000/1001. | `no-mode` for the first two and the fourth; the third opens; the close runs after each failure; the `granted_*` keys hold the granted values. |
| T-UNX-12 | Each errno and call of table 4.3.6. | The code, the stage and the reason of the table; `native_code` is the errno, `native_domain` `errno`, `call` the name of 4.6.3. |
| T-UNX-13 | `EBUSY` at `REQBUFS(0)`; then at `S_FMT`. | `camera-in-use`, "in use by another program"; `busy_call` `reqbufs`, then `s-fmt`; in the first case no `S_FMT` was sent. |
| T-UNX-14 | `STREAMON` gives `EIO`, `ENOSPC`, `ENOMEM`, `EFBIG`, `EINVAL`. | `usb-bandwidth` for the first four with the errno name in the reason; `open-failed` for `EINVAL`. |
| T-UNX-15 | 300 frames with `sequence` 0, 1, 2, 4, 5 ...; one with `V4L2_BUF_FLAG_ERROR`; one with `bytesused` 0. | `source_frame_number` has no gap; the frame after the gap has `discontinuity`; `sequence_gaps` 1, `sequence_lost` 1; the flagged and the empty frames have `driver_error`; the shared loop flags their slots `CAPTURE_ERROR`; `error_flag_frames` 1, `zero_bytes` 1. |
| T-UNX-16 | Timestamps: monotonic flags with times 5 ms before arrival; then one 1 ms after arrival; then one 300 ms before; a second open with stamps near `time.time_ns()`; a third with the type `UNKNOWN`. | `sample_ns = tv_sec × 10^9 + tv_usec × 1000` while valid; `NO_SAMPLE_NS` for the rest of the open after the late frame; `later_than_arrival` 1 and still counted after the rule switched; the percentiles from the raw differences; `clock` `monotonic`, `realtime`, `unknown`. |
| T-UNX-17 | Frames 0 to 4 arrive before the first `read_frame`. | As T-CAP-02: frame 4, `replaced_count` 4. |
| T-UNX-18 | `capture_timing`. `poll` times out for 6 s after 10 frames (virtual clock). | `dead` 2.0 to 2.25 s after the last arrival [W 9.5]. (The CPU rule is T-UNX-79, on a real clock.) |
| T-UNX-19 | Removal: `ENODEV` at `DQBUF`; `ENODEV` at `QBUF`; `EIO` with the sysfs node gone; `EIO` three times with the node present. | `device-removed` (dead at once) for the first three; `stream-error` for the fourth. |
| T-UNX-20 | `DQBUF` raises `InterruptedError` once at each of 10 frames. | 10 frames delivered; no failure. |
| T-UNX-21 | Exposure: set -7; -12 with a minimum of 3; -5; a camera with only menu items 1 and 3. | One `S_EXT_CTRLS` per set with the menu item 1 first, then 78, 3 and 313; the read-back compares native values; status -7, -12, -5; `exposure_native_at_m7` 78. |
| T-UNX-22 | The fake returns `EACCES` for an absolute value sent alone while the menu is 3. | The source never triggers it; a forced lone absolute set gives `control-failed`, and the camera stays in its earlier state [W U14]. |
| T-UNX-23 | A camera in Auto through `V4L2Source` and the search of [req 1.3] (the camera requests spec owns the tests of the search), with a brightness model in the fake; then a close with the camera in aperture priority (3) before the open. | Each value of the search is one `S_EXT_CTRLS` with the menu MANUAL first; `V4L2_CID_EXPOSURE_AUTO` is never set to 0 or 3 during the open; the restore at the close sets 3 again. |
| T-UNX-24 | Gain, focus, focus auto; a camera with no focus; white balance and power line values; a gain control with the flag `inactive`. | Set and read back; focus absent gives `present: false` and the text of [W 11.5]; white balance and power line get no set call; the inactive control gives `control-failed`. |
| T-UNX-25 | A control ioctl hangs on the control thread while two fake cameras are `ready`. | As T-CAP-82: stage `streaming`, code `hung`, hard end; the other camera has no gap above 100 ms. |
| T-UNX-26 | `STREAMOFF` hangs at the close; `S_FMT` takes 8 s (a slow camera); `S_FMT` hangs. | `hung`, stage `close`, hard end within 5 s + 2 s; the slow `S_FMT` passes (limit 11 s); the hung `S_FMT` gives `hung` at 11 s. |
| T-UNX-27 | The close order; with the restore on (default) and with `SKELLYCAM_RESTORE_CONTROLS=0`; a restore set that fails. | Stop, join (under 1 s), restore (each changed control set back to its "before" value and auto flag, and read back; the exposure menu back to an auto mode when it was so before the open), `STREAMOFF`, `munmap` x4, `REQBUFS(0)`, `close`; with the setting 0 no restore; a failed restore gives `restore_ok` false and `restore_failed` 1, is logged, and the close goes on. |
| T-UNX-28 | `diagnostics()` after 100 frames, with fake groups, euid and module parameters: (1) user in `video`; (2) not in `video`, access works; (3) euid 0; (4) `EACCES`. VideoStreaming sibling with alternate setting 3 after `STREAMON`. | Every key of 4.6.2 is present with its type; `access` `video-group`, `seat-acl`, `root`, `none`; `usb_alt` 3 (from the VideoStreaming interface, not the VideoControl one); `nodrop_param`, `clock_param`, `hwtimestamps_param` from the fake files; `frame_log` 64 rows; no value matches a path, a serial or a name of the fake. |
| T-UNX-29 | Three `V4L2Source` cameras over the fake through the shared loop, 30 s of virtual time at 30 fps. | Equal ring frame counts; payload bytes equal the fake bytes; the rules of T-CAP-05 on the gaps and `replaced_count`. |
| T-UNX-30 | `abi.py` built from the ABI descriptions of 32-bit arm (pointer and `long` 4 bytes, 64-bit alignment 8) and i386 (alignment 4); detection with `abi()` `x32`; ILP32 with `kernel_release()` 5.4 and 5.6. | `v4l2_buffer` 80 and 76 bytes, `VIDIOC_DQBUF` 0xC0505611 and 0xC04C5611, `timestamp` two 64-bit integers; x32 and ILP32 on 5.4: `backend-missing` and the OpenCV source; ILP32 on 5.6: native. |

### 6.4 macOS fake tests (step 7b)

| ID | Counterpart | What it does | Pass criterion |
|---|---|---|---|
| T-UNX-31 | T-UNX-04 | Detection: a C922, two identical cameras on two ports, a built-in camera, a virtual camera, a camera with `'420v'` formats only. | Five cameras; the virtual one `virtual: true`; VID and PID parsed; two different `camera_id` values for the identical cameras; the `'420v'` camera with `supported_modes = []` and `modes_read: true`; `id_source` `unique-id`. |
| T-UNX-32 | T-UNX-12 | Each event of table 4.4.8, by AVError name. | The code, the stage and the reason of the table; `native_code` the `NSError` code, `native_domain` `nserror`. |
| T-UNX-33 | — | Permission `notDetermined`, `denied`, `restricted`, `authorized`. | `no-permission` with the status for the first three, before any device call; `tcc` `not-determined`, `denied`, `restricted`, `granted`; no `requestAccess` call. |
| T-UNX-34 | T-UNX-10 | Open: spy the call order. | `beginConfiguration`, `addInput`, `addOutput`, lock, `activeFormat`, both durations, `commitConfiguration`, `startRunning`, unlock; controls read before any set. |
| T-UNX-35 | T-UNX-05, T-UNX-11 | Mode lists and read-backs: fixed ranges 1/30, 1001/30000, 1/60; a range 1 to 60 fps; a read-back of the duration that differs. | Exact `fps_num`/`fps_den`; the 1 to 60 fps range offers 29.97, 30 and 60, and a 30 request sets the duration 1/30; the differing read-back gives `no-mode`. |
| T-UNX-36 | — | Variants: (1) `empty` gives JPEG blocks; (2) `empty` gives decoded, `dmb1` gives JPEG; (3) both decoded. | (1) `delivered` `jpeg`, `video_settings` `empty`; (2) `jpeg`, `dmb1`, and the restart takes the lock again across `startRunning`; (3) `no-native-jpeg`, stage `start stream`. |
| T-UNX-37 | T-UNX-16 | 300 samples with PTS on the host clock 3 ms before arrival; then a sync clock that is not the host clock; then one sample 1 ms after arrival. | `sample_ns` from `to_host_ns`; with the other clock the PTS goes through `CMSyncConvertTime` and is kept, `clock` `device`; `later_than_arrival` 1, then `NO_SAMPLE_NS`. |
| T-UNX-38 | T-UNX-15 | A drop callback at sample 100; a sequence gap at sample 200; a layer with no sequence numbers. | The next frames have `discontinuity`; `drops_reported` 1; `sequence_gaps` 1; with no numbers `sequence_available` false. |
| T-UNX-39 | — | The format of the samples changes to 640x480 at sample 50. | `format-changed`, stage `streaming`; `format_changes` 1. |
| T-UNX-40 | T-UNX-21, T-UNX-22 | Routes with no evidence: A1 present and settable; A1 absent, A3 present; only A2 in EV; only A2 in seconds; none; a set that is ignored; lock supported and not supported. | A1, A3 and A2 used in that order, each marked unproven; EV: 8 evenly spaced points, -7 sets the sixth; seconds: -7 sets `2^-7` s; none: no exposure control, warning `no_manual_exposure`, no search, the camera opens [U]; ignored: `control-failed`, the camera keeps its state; the AVFoundation mode is locked only when supported. |
| T-UNX-41 | T-UNX-07 | `camera_id` inputs: `uniqueID` in mixed case; two identical cameras on two ports. | `avf:` plus the lower-case `uniqueID`; two IDs; the hash function of today. |
| T-UNX-42 | T-UNX-08 | A forced duplicate `camera_id`. | Refused with an error that names both devices [W D13]. |
| T-UNX-43 | T-UNX-09 | Detection where `devices()` hangs. | The detection child ends within 5 s + 2 s with `hung`; the main process runs on. |
| T-UNX-44 | T-UNX-17 | Samples 0 to 4 arrive before the first `read_frame`. | Frame 4; `replaced_count` 4. |
| T-UNX-45 | T-UNX-18 | `capture_timing`. No sample for 6 s after 10 samples (virtual clock). | `dead` 2.0 to 2.25 s after the last arrival. |
| T-UNX-46 | T-UNX-19 | The removal notification at sample 50; an `AVErrorDeviceNotConnected` runtime error. | `dead` at once, `device-removed`, both cases. |
| T-UNX-47 | T-UNX-23 | A camera in Auto through `AVFoundationSource` and the search of [req 1.3], on route A1 and on route A2 in EV, a brightness model; then a close with exposure `fcam` 1 before the open. | Each value of the search is a manual set on the route, on its scale; `fcam` = 1 for exposure is never set during the open; the restore at the close sets it again. |
| T-UNX-48 | T-UNX-24 | Gain, focus, focus auto through CoreMediaIO; a camera with no focus; white balance and power line read. | Set and read back; focus absent gives `present: false` and the text of [W 11.5]; white balance and power line get no set call. |
| T-UNX-49 | T-UNX-25 | A CoreMediaIO call hangs on the control thread while two fake cameras are `ready`. | Stage `streaming`, `hung`, hard end; the other camera has no gap above 100 ms. |
| T-UNX-50 | T-UNX-26 | `stopRunning` hangs at the close; `startRunning` hangs at the open. | `hung`, stages `close` and `start stream`; hard end within 5 s + 2 s. |
| T-UNX-51 | T-UNX-27 | The close order with the restore on (default) and off; a failed restore. | Observers removed, delegate nil, restore (each changed control back on its route, read back), `stopRunning`, input and output removed; setting 0: no restore; a failed restore gives `restore_ok` false and `restore_failed` 1, is logged, and the close goes on. |
| T-UNX-52 | T-UNX-28 | `diagnostics()` after 100 samples, with effect flags set. | Every key of 4.6.2 with its type; `tcc`, the effect keys, `edge_light` null, `sync_clock_is_host`; no value matches a `uniqueID` or a name. |
| T-UNX-53 | T-UNX-29 | Three `AVFoundationSource` cameras over the fake through the shared loop, 30 s of virtual time. | As T-UNX-29. |
| T-UNX-54 | T-UNX-06 | Detection with a fake USB link lookup of [req 3.4] (its own tests: T-REQ-51). | `CameraDeviceInfo.usb_link` is the lookup value; `usb_alt` is null. |
| T-UNX-55 | — | The delegate raises inside the copy. | The error marker; `read_frame` raises `CaptureFailure` with `stream-error`; nothing raises into the layer. |
| T-UNX-56 | T-UNX-30 | Detection with `macos_version()` 12.2. | The native backend is missing; the OpenCV source is chosen [U]. |
| T-UNX-57 | — | `PyObjCLayer` construction order with a stand-in of the frameworks. | `kCMIOHardwarePropertyRunLoop` is set to NULL before any other CoreMediaIO call (M-7). |
| T-UNX-58 | T-UNX-20 | Permission `authorized`, but no sample ever arrives. | `first-frame-timeout`; `tcc` `granted`; the diagnostics show `t_first_frame_ms` null. |
| T-UNX-59 | — | `PyObjCLayer` parameters with the fake: each `videoSettings` variant of 4.4.10 and each CoreMediaIO form (`native`, `absolute`, `native-data`, `tune`, `mode`). | The layer accepts each one and records its call; `AVFoundationSource` passes only `empty`, `dmb1`, the form of the chosen route of each control, `mode` and the lock; never `tune`. |
| T-UNX-60 | T-UNX-21 | Routes with evidence: a local full row says `cmio-native-data` `works` for exposure while the shipped file says `cmio-native` works on three models; only shipped rows where `cmio-native` works on three models and `cmio-absolute` on one; a row where each route of exposure is `no`; a row where the only route is `unproven`; a row whose native values are proven 100 µs; inside certify with the same rows. | The local row wins (`cmio-native-data`); else the route of most models (`cmio-native`); each route `no`: the control is absent; `unproven` only: the control is offered on that route; proven 100 µs: the map of A-18 (-7 sets 78) and `exposure_unit` `100us`; inside certify: the fixed order A1, A3, A2, whatever the rows say. |

Parity [U]: Linux has 30 fake tests and macOS 31 (with T-UNX-90 of 6.6). T-UNX-01 to T-UNX-03 (the
binary layout) and T-UNX-20 (`EINTR`) have no macOS counterpart: macOS has no ioctl layer. T-UNX-33,
T-UNX-36, T-UNX-39, T-UNX-55, T-UNX-57, T-UNX-59 and T-UNX-90 have no Linux counterpart: they test
facts of macOS only.

### 6.5 Shared and Windows tests (step 7s)

| ID | Kind | What it does | Pass criterion |
|---|---|---|---|
| T-UNX-61 | fake | `select_capture_source()` for each `sys.platform` with the settings unset, valid and wrong; with fake rows of the form of [cert 2.5]: a `full` row whose turn-on checks all passed; one with a failed turn-on check; one whose exposure route is `no` only; one whose exposure route is `unproven`; a `quick` row; another OS key; another ABI; an evidence row `verified` and `known-bad`; an evidence file whose OS key is `verified` with no row for the model; inside certify. | The order of 4.9; the first row gives native; the second OpenCV; the third native with no exposure control, and on Linux the warning `no_manual_exposure`; the fourth native with the exposure control; a quick row, another OS key, another ABI or a `verified` OS key alone gives OpenCV; certify always gets the native source; Windows unchanged. |
| T-UNX-62 | fake | `camera_checks.py` with a fake file of the form of [cert 2.5] (certify owns the writer and its tests, T-CERT-41); a broken file; a file with an unknown field. | The source reads the turn-on checks and the routes of each model; a broken file reads as no row with a log line; the source never writes the file. |
| T-UNX-63 | fake | Read `pyproject.toml` and `uv.lock`. | The PyObjC pins of 7.2 with `==` and the marker `sys_platform == "darwin"` [U]; no new Linux dependency; locked at the same versions. |
| T-UNX-64 | fake | `CaptureFailure` across a process boundary; each code of 4.6.3; each row of the two code tables of 4.6.3 that a fake can reach (the loop sites, `modes.py`, `opencv_source.py`, `_give_up`, `_mark_ended`, the stuck writer); a failure with no code at each stage. | `code` survives pickling; the failure object has `code`; each site gives the code of its row; no code gives `open-failed` before streaming and `stream-error` after. |
| T-UNX-65 | fake | `exposure_units` for each v from -14 to -2 with ranges (3, 2047, 1) and (1, 5000, 1); the macOS scales of 4.4.6: seconds, proven 100 µs, EV over (-4, 4), native over (1, 1000). | The table of A-18; the clamp; the read-back; `floor(x + 0.5)`; seconds `2^v`; EV and native: 8 ordered points, -12 at the low end. |
| T-UNX-66 | fake | `no-native-jpeg` from a native open with the default selection, with the setting, and inside certify. | Default: the camera opens with OpenCV, `backend: opencv`, a log line [U]; setting: `failed` with `no-native-jpeg`; certify: `failed`, no OpenCV open. |
| T-UNX-67 | fake | An evidence row `known-bad` for a camera model and the native backend. | Default: that camera opens with OpenCV; the others native [U]. |
| T-UNX-68 | fake | "Apply again" for a camera whose old process is still alive. | `previous-process-alive`, stage `open`; no open of the camera. |
| T-UNX-69 | fake | The source parts of 4.5 (the camera requests spec owns the tests of the search, T-REQ-01, 06, 12, 19, 41): a native camera with no manual exposure at open; a changed config for a camera in `adjusting`; a start-up rate failure of a camera in Manual. | The camera with no manual exposure opens with the warning `no_manual_exposure` and never enters `adjusting`; the changed config gets 409; the reason has the form of [req 1.5a], with `declared_fps` and `measured_fps`. |
| T-UNX-70 | fake | A fake source and the OpenCV fake in real camera processes: `CameraStatus.serialize()`, the `app_state` message, `CameraGroup.diagnostics(camera_id)` and `CameraGroupManager.diagnostics()`; a fake whose dict has 64 `frame_log` rows and 60 hash keys; a fake whose dict is over 32 KiB. | A new dict comes each second through the topic `TopicTypes.DIAGNOSTICS` (4.2 item 2); `serialize()` and `app_state` hold only the counter subset, with no `frame_log` and no hash key; the accessors return the full newest dict; the 64-row dict is under 32 KiB and arrives whole; the dict over the limit is not sent and gives one log line; `CameraStatus.info` holds no diagnostics; no diagnostics message goes into `finished`; the OpenCV dict has `backend` `opencv` and null for every other source key. |
| T-UNX-71 | fake | MJPG passthrough with the fake source; the OpenCV fake (re-encode); a BGR ring on. | `encoded_by_skellycam` 0 and the frame count; `decoded_by_skellycam` counts the decode stage. |
| T-UNX-72 | fake | D-11: a camera reaches `ready`, gets a live change that ends in `ready` again, then records; one camera sends no DHT. | 30 hashes after the first `ready` with their `source_frame_number`; the live change does not replace them; a new set at the record start; each hash equals the SHA-256 of the ring slot and of the MKV block of that frame; no warm-up frame is hashed; `dht_inserted` counts the DHT camera. |
| T-UNX-73 | fake | The OpenCV source on Linux with a native detection result; on macOS with a device order. | Linux: `cv2.VideoCapture('/dev/videoN', CAP_V4L2)` of the detected node; macOS: the index of the matching `uniqueID`. |
| T-UNX-74 | fake | Detection with an evidence file and a local record. | `evidence`, `checked`, `id_source`, `has_serial`, `backend`, `usb_link` in `CameraDeviceInfo`; `system_evidence` in the status. |
| T-UNX-75 | fake | `capture_timing`. Three fake cameras (pull sources, as the OpenCV source) in real camera processes: the process of one is suspended with `psutil` `suspend()` (it cannot run a loop pass then); a second camera is `waiting`; then the group is in the internal pause of a record start; then a take whose writer of one camera is held for 4 s with progress and then for 4 s with no progress (scaled stall limit); then a reopen by a size change whose close takes 3 s; then the OpenCV fake streams for 10 s. | The main process removes the suspended camera from the gate and ends it 2.5 to 3.0 s after its last loop pass, `dead` with `stalled`; the `waiting` camera, the internal pause, the writer waits, the slow close of the reopen and the OpenCV fake trip nothing; the held writer ends by the rule of recorder.md 5.3, not by this watch; the third camera has no gap longer than 3.0 s (4.10). |
| T-UNX-76 | windows | `MediaFoundationSource.diagnostics()` with the stand-in interfaces of the Windows tests; a second case with one interval of 150 ms at 30 fps. | Every key of 4.6.2; `id_source` `mf-link`; `native_domain` `hresult`; `clock` `unknown`; `t_*_ms` filled; the second case counts at least one `long_intervals` [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md). |
| T-UNX-77 | windows | Map the HRESULTs of [W 6.7] and `0x800718CF` to codes. | In-use codes give `camera-in-use`; removal codes give `device-removed`; `0x800718CF` gives `usb-bandwidth`; `0x80004005` gives `open-failed` at open and `stream-error` in streaming. |
| T-UNX-78 | windows | The restore of the Media Foundation source at the close, with stand-in control interfaces. | Each changed control is set back to its "before" value and flags before the flush, and read back; on by default. |
| T-UNX-91 | fake | A fake camera that keeps its controls between opens, auto -6 before the first open; it opens in `MANUAL -7`, and its loop fails (no restore); then "apply again", and in a second case a group close and a new group; in a third case the camera rounds: after a reopen it reads manual -6 (one step from -7). | The camera holds manual -7 after the failure and after the group close; the next open has `exposure_before` auto -6, and its close restores auto -6, `restore_ok` true (4.7) [ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md); the camera that rounds also gets auto -6 back; a fourth case: the camera that rounds is slow (25 fps) at that open, which still runs the normal rate check, fails with `rate-low` and restores auto -6 [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md). |
| T-UNX-92 | fake | `ControlRestore` with a record: open 1 sets manual -7 and gets no restore; (a) the camera still holds -7; (b) another program set manual -3; (c) a record whose `before` has a control that is not in `names`; (d) the camera reads one step from -7 (-6 or -8) with the step 1, and with no step; (e) it reads two steps from -7. | (a) The close of open 2 restores auto -6; (b) it restores -3; the record is empty after each; (c) that control keeps the value that the camera reads; (d) with the step: auto -6, with no step: the value that the camera reads; (e) the value that the camera reads (4.7) [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md). |
| T-UNX-93 | fake | A frame decision with no take (first frame -1) while another thread holds the lock of the last frame. | It returns "no record, no finish" in under 0.2 s and starts no stretch with no lock (4.10). |
| T-UNX-94 | fake | `CameraManager.close()` with a camera process that cannot be killed and a camera with a restore record. | The close raises; `restore_records` holds the record of that camera (4.7). |
| T-UNX-95 | fake | A camera whose exposure the open set and whose loop then fails: with `rate-low` (the start-up rate check), with `not-ready`, and with `stalled` (the stall rule of [W 9.5]). | `rate-low` and `not-ready`: the close restores the "before" values, `restore_ok` true; `stalled`: no set at the close, `restore_ok` null (4.7) [ADR-Z7F3](../decisions/entries/Z7F3-choices-of-fix-lane-3.md). |
| T-UNX-96 | fake | A camera in auto -6 opens in MANUAL -7 with a restore folder; it stalls (no restore); its server goes (a new `CameraGroupManager` with the same folder and the same camera); the new server opens it and closes it. | The file `<key>.json` exists after the first set, with `version` 1, the USB IDs and no path; the second close restores auto -6; the file is gone (4.7.1) [ADR-HQE5](../decisions/entries/HQE5-choices-of-fix-lane-4.md). |
| T-UNX-97 | fake | The file of a camera holds bytes that are not JSON; JSON of another `version`; a record of the right shape with a wrong type (`"set": {"exposure": [false, "-4"]}`), an unknown control name, and a "before" value outside the range of the camera; a file of a later `version`. | The open and the close have no error, and the camera is `ready`; one log line; a damaged file is removed and a later version stays; no restore of a value of the file (4.7.1). |
| T-UNX-98 | fake | Two cameras of one model (the same USB IDs), each with its own entry of other "before" values; a new server opens both and closes them. An entry whose USB IDs differ from the camera with its key. The identity input of a Linux camera from a fake sysfs tree, and of a camera with no stable input. | Each camera restores its own "before" values; the entry with other USB IDs is dropped; the Linux input is the port of the USB interface, never `/dev/video<n>`; a camera with no stable input has no file (4.7.1). |
| T-UNX-99 | fake | A camera whose entry is used; its close restores with no failure. | The file is gone after the close; a later group creates no file before a set (4.7.1). |
| T-UNX-100 | fake | The camera reads a manual value two steps from the value of the entry at the open of the new server. | The entry is dropped: the file is gone, and the close does not set the "before" value of the entry (4.7, 4.7.1). |
| T-UNX-101 | fake | The salt, the folder and the camera process: a salt that is missing or damaged; a temporary file of a process that does not run; a folder that cannot be written; the folder that the server of the app gets; a camera process (PROCESS workers) that writes its file and is then killed. | A new salt and no old entry used; the temporary file is removed; the open is `ready` with one log line; `get_or_create_camera_group_manager` gives `default_folder()`; the file of the killed process stays with the values of before (4.7.1). |
| T-UNX-79 | fake | `capture_timing`. A paused camera process with `V4L2Source` and with `AVFoundationSource` over the fakes, 10 s. | Process CPU under 2 % of one core (the rule of T-CAP-49). Not calibrated on a hosted runner: a failure is recorded and the user decides [A]. |

### 6.6 Runner and build tests

| ID | Kind | What it does | Pass criterion |
|---|---|---|---|
| T-UNX-80 | linux-runner | Import `v4l2`; detection with the real `V4L2System`. | A list (empty with no camera); no exception. |
| T-UNX-81 | linux-runner | `VIDIOC_QUERYCAP` on `/dev/null`. | `OSError` with `ENOTTY`; the map gives `open-failed` with "querycap: ENOTTY". |
| T-UNX-82 | linux-runner | `perf_counter_ns()` against `time.clock_gettime_ns(time.CLOCK_MONOTONIC)`, 1,000 pairs. | Each difference under 1 ms (A-9). |
| T-UNX-83 | vivid | The first vivid capture node with the real system: 60 frames of a format that vivid offers, with the MJPG check off [A]. | Frames arrive; flags monotonic; `sequence` increments by 1; `sample_ns` on the base of T-UNX-82; the close returns. Skipped without vivid. |
| T-UNX-84 | macos-runner | A worker thread calls `NSThread.sleepForTimeInterval_(0.5)`; the main thread counts. | The main thread counts on during the sleep (M-8). |
| T-UNX-85 | macos-runner | `PyObjCLayer()`: frameworks, `macos_version()`, `authorization_status()`, `devices()`. | The status is one of the four values; the list is empty or has no USB camera; no exception. |
| T-UNX-86 | macos-runner | `CMClockGetTime(CMClockGetHostTimeClock())` through `to_host_ns`, against `perf_counter_ns()`, 1,000 pairs. | Each difference under 1 ms (M-9). |
| T-UNX-87 | macos-runner | The CoreMediaIO constants of 4.4.6 and M-7, `CMIOObjectGetPropertyData`, `CMSyncConvertTime`. | Each name exists; setting `kCMIOHardwarePropertyRunLoop` to NULL returns no error. |
| T-UNX-88 | build | On the macOS build jobs: the frozen server runs the native detection only (no camera). | The layer loads; detection returns a list; no missing module. |
| T-UNX-89 | fake | Import each module of `v4l2/` and `avfoundation/` on Windows, Linux and macOS. | Each import passes; no module imports `fcntl`, `mmap`, `objc` or a PyObjC framework at module level (Q 1). |
| T-UNX-90 | fake | macOS: the variant restart of 4.4.3 (`empty` decoded, then `dmb1`), with gain and exposure set before the restart. | After the second `startRunning`, the source sets each control again, in the order of the first start; the read-back follows. |


### 6.7 Certify checks: the hardware tests

The certify spec owns these names; a split of a check there (one row for each test) changes only the
names here.

The hardware validation is a certify run [U]. This table gives the parity with the Windows hardware
tests; it does not repeat the certify spec.

| Assumptions | Certify check [cert 4, 5, 8, 10.2] | Windows test it mirrors |
|---|---|---|
| A-1, A-4, M-1, M-4 | `detect`, `<label>:detect`, `<label>:modes:granted:*` | T-CAP-51, T-CAP-79 |
| A-2, M-2 | `<label>:identity:*` | T-CAP-24, T-CAP-106 |
| A-3, M-3 | `detect` (its count `virtual`) | T-CAP-105 |
| A-5, A-6, A-11, A-12, M-6, M-7 | `<label>:opens`, `<label>:rate`, `<label>:modes:granted:*` | T-CAP-52 |
| A-7, A-8, M-5 | `<label>:native-jpeg:*` | T-CAP-52 |
| A-9, M-9 | `<label>:clock:*` | T-CAP-59 |
| A-10, M-10 | `<label>:sequence`, `<label>:time-gaps` | none (new) |
| A-13, M-8 | `self:hang-100ms:gap` and `self:hang-100ms:hard-end` | T-CAP-82 |
| A-14, M-11, M-12, 4.13 | `<label>:in-use`, `<label>:in-use:other-program`, `<label>:in-use-mid-take`, `probe:camera-holders`, `probe:<model>:hog-mode` (macOS) [cert 20] | T-CAP-56, T-CAP-130 to T-CAP-145 |
| A-15, A-22, M-13 | `group:open`, `group:contention` | none (new) |
| A-16, M-14 | `system:camera-access` | none (new) |
| A-17, A-18, M-15 | `<label>:controls`, `<label>:controls:exposure-scale`, `<label>:auto-off:*`, `<label>:settings-stick:*`, `<label>:exposure:<base>`, `<label>:auto-exposure:*`, `<label>:control:*`, and on macOS the probes `probe:<model>:a1-cmio-native:<control>` to `a10-avf-custom:exposure` [cert 10.7] | T-CAP-57, T-CAP-78 |
| A-19, A-20 | `<label>:settings-stick:*` | T-CAP-57 |
| A-21, M-17 | `<label>:cycles` (it holds the open and close times), `system:kernel` | T-CAP-54 |
| A-22, M-18 | `system:usb` | none (new) |
| A-23, M-19, M-20 | `detect` (`backend-missing`) | T-CAP-46 |
| M-16 | `system:video-effects` | none |
| rates, the generic camera | `<label>:rate`, `<label>:rate:<mode>` | T-CAP-53, T-CAP-54 |
| the group take | `group:take-30` | T-CAP-60 |

### 6.8 Counts

| Kind | Linux | macOS | Each OS or Windows |
|---|---|---|---|
| fake | 30 (T-UNX-01 to 30) | 31 (T-UNX-31 to 60, 90) | 22 shared (61 to 75, 79, 89, 91 to 95), on Windows, Linux and macOS |
| windows | — | — | 3 (76 to 78) |
| runner, vivid | 4 (80 to 83) | 4 (84 to 87) | — |
| build | — | 1 (88) | — |
| certify | 6.7 | 6.7 | — |

### 6.9 Tests of exclusive access (4.13, lands with phase 7)

Accepted on 2026-11-25, with 4.13 (Q813). The counts of 6.8 do not hold these tests yet.

| ID | Kind | What it does | Pass criterion |
|---|---|---|---|
| T-UNX-102 | fake | Linux: `S_PRIORITY` RECORD succeeds; then a fake where it returns `EBUSY`. | The source calls `S_PRIORITY` with RECORD right after `open()` and before `REQBUFS(0)`; `priority_record` true. With `EBUSY`: `camera-in-use`, stage `open`, `busy_call` `s-priority`; no `S_FMT` was sent. |
| T-UNX-103 | fake | Linux: a take of 10 s. At 4 s the fake gives a value event of `V4L2_CID_EXPOSURE_ABSOLUTE` (manual) as from another handle. Also: a flags-only event of gain after an own set of gain; an own set of `V4L2_CID_EXPOSURE_AUTO`, with the value and flags event on `V4L2_CID_EXPOSURE_ABSOLUTE` 50 ms later; a value event of focus while focus is in auto (a device auto update). | One subscription for each listed control, after `STREAMON`, with no `ALLOW_FEEDBACK` flag; one `control_changed_by_other` warning and one `camera_control_changed` mark at the row after 4 s; the other three events give no warning and no mark; `ctrl_events_other` is 1. |
| T-UNX-104 | fake | Linux: `EBUSY` at `REQBUFS(0)`, with a fake `/proc`: (1) one process of the same user holds the node, `comm` `obs`; (2) the link cannot be read (another user). | (1) the reason "in use by obs. Quit it and try again"; (2) "in use by another program". In both cases `/proc` is read only after the failure, never before the open. |
| T-UNX-105 | fake | macOS: `isInUseByAnotherApplication` is true before the open. | `camera-in-use`, stage `open`; no `deviceInputWithDevice_error_` call. |
| T-UNX-106 | fake | macOS: the configuration lock: (1) the source opens, streams 5 s and closes; (2) `lockForConfiguration` fails with -11817. | (1) one `lockForConfiguration` before `startRunning`, no `unlockForConfiguration` until the close, then the unlock after the restore; `config_locked` true while open. (2) `camera-in-use`, `busy_call` `lock-config`. |
| T-UNX-107 | fake | macOS: a take of 10 s; the in-use flag goes true at 3 s and false at 6 s. | The take records to the stop; one `camera_shared` warning; one `camera_shared` mark with the rows of 3 s to 6 s and `by=another program`; `in_use_flag_changes` is 2. |
| T-UNX-108 | fake | macOS: the source with no hog-mode evidence, and with a shipped row that says hog mode works for the model. | With no evidence: no set of `kCMIODevicePropertyHogMode`. With the row: the set at the open; a hog mode that another process id holds gives `camera-in-use`. |

The certify checks of [cert 20] are the hardware tests of these rules.

## 7. Dependencies, risks

Each new dependency must be justified [U]. Sections 7.1 and 7.2 justify the dependencies of Linux and macOS.

### 7.1 Linux: no new dependency [A]

| Option | Cost | Choice |
|---|---|---|
| Standard library: `fcntl.ioctl`, `mmap`, `select.poll`, `ctypes` structs (port of linuxlib, 723 lines, with its reference values) | No install, no PyInstaller change, no CI time. About 400 lines of ABI code [NV estimate]. | **Chosen** |
| linuxpy 0.25.0 (GPL-3.0-or-later [K22]) | A dependency that the research never tested, for code the research already has | Rejected |
| v4l2py, pyv4l2 | "Do not take" [R xplat §2.4] | Rejected |

### 7.2 macOS: PyObjC, pinned exactly [U]

```toml
"pyobjc-core==13.0; sys_platform == \"darwin\"",
"pyobjc-framework-Cocoa==13.0; sys_platform == \"darwin\"",
"pyobjc-framework-Quartz==13.0; sys_platform == \"darwin\"",
"pyobjc-framework-CoreAudio==13.0; sys_platform == \"darwin\"",
"pyobjc-framework-CoreMedia==13.0; sys_platform == \"darwin\"",
"pyobjc-framework-AVFoundation==13.0; sys_platform == \"darwin\"",
"pyobjc-framework-CoreMediaIO==13.0; sys_platform == \"darwin\"",
"pyobjc-framework-libdispatch==13.0; sys_platform == \"darwin\"",
```

Quartz and CoreAudio are listed because AVFoundation 13.0 requires them [K21].

| Option | Cost | Choice |
|---|---|---|
| PyObjC 13.0 | cp313 universal2 wheels, about 7.5 MB together [K21]. The frozen app grows by about 8 to 12 MB [NV]. CI install: seconds from the uv cache [NV]. | **Chosen** [U] |
| `ctypes` to the Objective-C runtime | No dependency, but a delegate class made at run time, blocks by hand, and struct returns of `objc_msgSend` per architecture: several hundred lines that nobody tested | Rejected |
| rubicon-objc | A dependency too, with less coverage of CoreMedia and CoreMediaIO [NV] | Rejected |

Whether PyInstaller 6.22.3 collects PyObjC is [NV]; T-UNX-88 finds a gap.

### 7.3 Risks, ranked

1. **No native JPEG through AVFoundation (M-5).** Plan: `no-native-jpeg`, and the camera opens with
   OpenCV outside certify [U]; after step 3b the source could encode the decoded samples; the plan of
   2026-11-17 already says "If it does not, macOS stays on decode then re-encode" [R plan §3].
2. **No working control route on macOS (M-15).** Plan: the widest working route of A1, A2 and A3 in
   any unit (4.4.6) [U]; with none, no exposure control and the warning `no_manual_exposure` [U];
   certify shows the camera item `partial`; the endpoint-0 probes show whether that route works.
3. **Timestamps not on a usable clock (A-9, M-9).** The 200 ms rule gives `NO_SAMPLE_NS`, and the
   recorder keeps `arrival_ns` [W D28]. Low on Linux, medium on macOS.
4. **PyObjC holds the GIL (M-8).** Plan: the stall watch of 4.10 [U]; T-UNX-84 shows it in CI.
5. **No real system before certify.** Each struct, ioctl number and PyObjC call comes from documents
   and research code. Plan: the reference-value tests; the first certify run gives every diagnostic;
   OpenCV stays until a model passes the gate of [cert 11.3] [U].
6. **A stuck kernel wait on Linux (A-13).** Plan: the main process does not wait;
   `previous-process-alive`.
7. **A slow camera at the 5 s control timeout (A-13).** Plan: 11 s for the probe-and-commit ioctls.
8. **Bandwidth codes (A-15, M-13).** The reason names the errno; certify records it.
9. **Identity (A-2, M-2).** A port move gives a serial-less camera a new `camera_id` on Linux and each
   camera a new one on macOS, as Windows does for serial-less cameras [W 7.2].

## 8. Choices of the agent

[ADR-AT04](../decisions/entries/AT04-choices-of-the-linux-and-macos-capture-spec.md) holds them.

1. The `camera_id` inputs of A-2 and M-2; the port fallback only for duplicate serials.
2. Discrete intervals and fixed ranges give exact fractions; a stepwise interval or a rate range gives
   only 29.97, 30 and 60.
3. Four mmap buffers; two or more accepted.
4. `O_NONBLOCK` with a `poll` timeout of 100 ms; `EIO` or `POLLERR` checks the sysfs node; three `EIO`
   with the node present end the stream.
5. `REQBUFS(0)` before `S_FMT`.
6. `EIO`, `ENOSPC`, `ENOMEM` and `EFBIG` at `STREAMON` give `usb-bandwidth`.
7. A node without access is listed from sysfs with `modes_read: false`; `access` adds `root`.
8. The menu MANUAL in the same `S_EXT_CTRLS`; `V4L2_CID_EXPOSURE_AUTO_PRIORITY` read, never set.
9. The exposure map `floor(2^v × 10000 + 0.5)`, clamped; read-back in native units; the macOS route
   scales of 4.4.6 (EV evenly spaced, other native values log-spaced).
10. A bounded-call limit of 11 s for `S_FMT`, `S_PARM` and `STREAMON`.
11. The usb_alt read from the VideoStreaming sibling interface.
12. The macOS JPEG variants `empty`, then `dmb1`, with the lock taken again.
13. `dqt_sha256` to show byte-true JPEG against the same model on another OS.
14. The source never calls `requestAccess`.
15. `format-changed` for a format change during streaming.
16. The AVError map by PyObjC names.
17. `CMSyncConvertTime` for a sync clock that is not the host clock; no `masterClock` fallback.
18. The CoreMediaIO run loop set to NULL at the layer start.
19. Fake-testable modules that import only the standard library at module level [Q 1].
20. The generic bounded call in `capture/bounded.py`.
21. The diagnostic keys that certify does not name (4.6.2), `frame_log` of 64 rows, and the D-11
    trigger and frame numbers.
22. The setting `SKELLYCAM_RESTORE_CONTROLS=0` for debug runs.
23. The settings `SKELLYCAM_LINUX_CAPTURE` and `SKELLYCAM_MACOS_CAPTURE`; the source only reads
    `camera_checks.json`.
24. `previous-process-alive`.
25. Detection in a short-lived child on Linux and macOS.
26. The OpenCV source on macOS finds its index by `uniqueID`.
27. `declared_fps` and `measured_fps` as numbers in the failure object, beside the reason of
    [req 1.5a]; the shared counter `alive_count` of the stall watch.
28. The virtual clock seam of the sources.
29. No new CI job; the markers; the optional vivid step; T-UNX-88.
30. The pass thresholds of section 6.
31. The ABI description of A-23 and the kernel 5.6 floor on ILP32.
32. The D-11 hashes re-armed only at the first `ready` of an open and at a record start; `frame_log`
    and the hashes kept out of the `app_state` message.

## 9. Questions for the user

Each question waits for the user. Each is worded so that "yes" accepts the recommendation, and the
spec is written to that recommendation. The user accepted the seven other recommendations of draft 2
on 2026-11-20 ([ADR-22EJ](../decisions/entries/22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md), item 14).
Question 5 of the earlier commit is superseded by the route ruling
([ADR-SC3Y](../decisions/entries/SC3Y-later-rulings-of-the-user-for-native-capture-on-linux-and-macos.md)).

1. The folders `v4l2/` and `avfoundation/` run only on their OS, but their modules import only the
   standard library at module level, so that their fake tests run on Windows, Linux and macOS
   (T-UNX-89 checks it). Yes?
2. The counters of 4.6.2 go into the camera status each second, also in the `app_state` message;
   `frame_log` and the 30 frame hashes stay only in the status that certify reads in its own process.
   Yes?
3. CI adds no new job: the fake tests join the three capture jobs, the Linux job tries
   `modprobe vivid` without failing, and the macOS build jobs run T-UNX-88. Yes?
4. Decided: item 15 of ADR-22EJ computes the layout for the host, 32-bit included (A-23). The x32 ABI
   and a 32-bit userspace on a kernel older than 5.6 keep the OpenCV source (choice 31).
