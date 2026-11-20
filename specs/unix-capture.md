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
exposure search ends.

The user moved this work up on 2026-11-20: "certify runs to validate assumptions about linux and mac
code. Ideally as much real code is implemented as possible now so a single test run provides as much
information as possible and can be used there and then if the tests pass." [U] Thus the native
sources are written now, without a Linux or macOS machine. Each fact that the code relies on is an
assumption of section 2. Each assumption has a run-time check, a diagnostic key and a certify check.
A certify run on a real system then confirms or refutes each one. When a camera model passes a full
certify run on a system, native capture is used for it there at once (section 4.9).

## 0. How to read this spec

Marks:

- **[U]**: a decision or ruling of the user ([ADR-22EJ](../decisions/entries/22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md)).
- **[A]**: a choice of the agent ([ADR-AT04](../decisions/entries/AT04-choices-of-the-linux-and-macos-capture-spec.md)). Section 8 lists each one.
- **[Q n]**: written to the recommendation of question n of section 9. It **waits for the user**.
- **[W x.y]**: section x.y of [`windows-capture.md`](windows-capture.md). **[W Dn]**, **[W Un]**,
  **[W Wn]**: a decision of that spec (its section 20). **[rec x.y]**: [`recorder.md`](recorder.md).
- **[cert x.y]**: section x.y of `specs/certify.md`, draft 3, as the file was on disk in the worktree
  of branch `dom/certify-spec` on 2026-11-20 (not committed then). The certify spec owns each check
  name, number key, value and reason code that certify reads. This spec uses them. Section 4.6.4 lists
  what certify must add.
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
| 7s (shared) | The failure code beside the failure text; `diagnostics()` on each source; the exposure rules of 4.5 on each source; the restore of the controls at the close; the generic bounded call; the exposure unit map; the local record of certify-checked camera models; the source selection; the evidence fields; the native detection dispatch; the USB link label (section 4). |
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
- Modes below 30 fps; any group rate other than one rate (30 or 60) for all cameras [U, W U11].
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
- Certify: `<label>:identity` (`id-unstable`, `id-collision`).

**A-3. Virtual cameras.** A v4l2loopback node has the driver name `v4l2 loopback` in `QUERYCAP` and no
USB parent in sysfs [NV]. Detection gives it `virtual: true` [W W5]. A name with "virtual" is virtual
too [W 7.1].
- Confidence: medium. If false: a virtual camera is selectable.
- Certify: `system:virtual-cameras`.

**A-4. Mode list.** `VIDIOC_ENUM_FMT`, `VIDIOC_ENUM_FRAMESIZES` and `VIDIOC_ENUM_FRAMEINTERVALS` give
the MJPG sizes and their frame intervals; for a UVC frame-based descriptor the types are discrete
[R linuxlib, xplat §2.6] [NV on our cameras]. A discrete interval `n/d` seconds gives `fps_num = d`,
`fps_den = n` [A]. A stepwise or continuous interval range gives only the rates 30000/1001, 30/1 and
60/1 that fall inside it [A].
- Confidence: high. If false: `supported_modes` is empty or wrong.
- Run-time check: the mode choice of [W 7.5]; the read-backs of A-5 and A-6.
- Diagnostics: `modes_listed`, `mjpg_sizes`, `interval_types` (`discrete`, `stepwise`, `mixed`).
- Certify: `<label>:detect`, `<label>:modes` (`mode-not-granted`).

**A-5. `S_FMT` can grant another size.** The driver adjusts a request and returns no error [K5]. The
source reads back width, height and pixel format. A difference is a failure, stage `set mode`, code
`no-mode`.
- Confidence: high.
- Diagnostics: `requested_fourcc`, `granted_fourcc`, `requested_w`, `requested_h`, `granted_w`,
  `granted_h` (D-1).
- Certify: `<label>:modes`, `<label>:native-jpeg`.

**A-6. `S_PARM` sets the rate.** With `V4L2_CAP_TIMEPERFRAME`, `VIDIOC_S_PARM` sets `timeperframe`,
and the driver returns the actual period [K7]. The source calls `S_FMT`, then `S_PARM`, then
`G_PARM`. A rate that is not equal to the chosen mode rate with the relative tolerance of 0.0001
[W D17] is a failure, stage `set mode`, code `no-mode`. 30000/1001 and 30/1 differ by 0.1 %, so a
read-back of one for the other is a failure.
- Confidence: high. The order `S_FMT` then `S_PARM` is the order of the research layer [NV].
- Diagnostics: `requested_fps_num`, `requested_fps_den`, `granted_fps_num`, `granted_fps_den` (D-1).
- Certify: `<label>:rate`, `<label>:modes`.

**A-7. MJPG buffers are the camera's JPEG.** uvcvideo copies the payloads of each frame into the
mmap buffer and sets `bytesused` [K8]; it does not decode or re-encode. The source copies
`bytesused` bytes into one `bytes` object and requeues the buffer at once.
- Source: [K8]; [R xplat §2.6 G-MJPEG: "Raw V4L2 mmap is the reference"]. Confidence: high.
- Run-time check: the capture check of the shared loop (`check_jpeg`) [W 5.1 step 5].
- Diagnostics: `delivered` (`jpeg`), `bytesused_equals_payload`, `sha256_00` to `sha256_29` (D-11).
- Certify: `<label>:native-jpeg`.

**A-8. Damaged frames carry `V4L2_BUF_FLAG_ERROR`.** With `nodrop=1` (the default [K10]), a frame
with the UVC error bit or a lost packet arrives with the error flag [K1, K8, K9]. On a kernel with
`nodrop=0` the driver drops it, and `sequence` has a gap (A-10). The source sets `driver_error = True`
for a flagged buffer and for `bytesused = 0`; the shared loop then flags the slot `CAPTURE_ERROR`
[W 5.1].
- Confidence: high. The kernel release that changed the default is 6.14 by the research [R xplat
  §2.6] [NV].
- Diagnostics: `error_flag_frames`, `zero_bytes`, `nodrop_param` (from
  `/sys/module/uvcvideo/parameters/nodrop`, or null).
- Certify: `<label>:native-jpeg` (`error_flag_frames`).

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
- Certify: `<label>:clock` (`clock-base-differs`, `sample-after-arrival`, `sample-too-early`).

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
- Certify: `self:hang-100ms` (the software rule); a real driver hang cannot be made [cert 7].

**A-14. "In use" is `EBUSY` at `REQBUFS` or `S_FMT`.** V4L2 allows more than one open, so `open()`
succeeds while another process streams. `REQBUFS` returns `EBUSY` for a file that does not own the
queue [K25]. `S_FMT` sends a PROBE request to the camera (`uvc_v4l2_try_format`) and returns `EBUSY` only
after it [K26]. Thus the source calls `VIDIOC_REQBUFS` with `count = 0` first [A]: it sends no USB
request and catches a holder that has buffers. A holder that set a format but has no buffers is not
caught there; `S_FMT` then returns `EBUSY` after its PROBE. `EBUSY` at any open step gives the code
`camera-in-use` and the reason "in use by another program" [W D13].
- Confidence: high.
- Diagnostics: `busy_call` (`reqbufs`, `s-fmt`, `s-parm`, `streamon`, or null).
- Certify: `<label>:in-use` (`outcome`, `call`); `probe:camera-holders`. A camera that another
  program holds is `skipped` with the reason `busy` in the certify format 1.3.0 [U].

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
- Certify: `<label>:controls`, `<label>:settings-stick`, `<label>:auto-off`.

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
- Certify: `<label>:controls` (`unit-mapping`), `<label>:settings-stick`, `<label>:exposure:<base>`.

**A-19. A read-back can come from the cache.** uvcvideo can answer `G_EXT_CTRLS` from its cache
[R xplat §2.6 G-CTRL]. A read-back proves that the driver took the value, not that the camera uses it.
- Confidence: medium. Run-time check: none.
- Certify: `<label>:settings-stick` (`no-image-effect`).

**A-20. Controls hold while the stream runs.** The source sets the controls after the first frame
[W D20] and keeps the node open and streaming. A camera can lose its controls after an autosuspend
when no file holds it [R xplat §2.6] [K24] [NV for the release]. The source never sets a control on a
camera that does not stream; the restore of 4.7 runs before `STREAMOFF` [A].
- Confidence: medium.
- Diagnostics: `<control>_before`, `<control>_value`.
- Certify: `<label>:settings-stick` (`setting-reverted`, `setting-lost-on-reopen`).

**A-21. Close and reopen.** `STREAMOFF`, `munmap` and `close()` release the camera in under 1 s, and a
reopen at once works [NV]. The Kiyo Pro needs the USB `NO_LPM` quirk of kernel 7.0 and of the stable
kernels 6.12.81, 6.18.34 and 6.19.12 [R xplat §2.6] [NV].
- Confidence: low.
- Diagnostics: `t_close_ms`, `kernel` (`major.minor`).
- Certify: `<label>:cycles`, `<label>:timings`, `probe:kernel`.

**A-22. The USB link and the alternate setting.** The sysfs `speed` of the USB device gives the link:
1.5 or 12 is `usb1`, 480 is `usb2`, 5000 or more is `usb3` [R naming/README.md] [NV]. The node's
`device` link is the VideoControl interface [K10], whose alternate setting is always 0. The granted
alternate setting is `bAlternateSetting` of the VideoStreaming interface: a sibling under the same USB
device with `bInterfaceClass` 0e and `bInterfaceSubClass` 02, read after `STREAMON` [A]. When the
function has two or more VideoStreaming interfaces, the source takes the one with a non-zero value;
with two non-zero values, `usb_alt` is null [A].
- Confidence: medium.
- Diagnostics: `usb_link`, `usb_alt` (D-9).
- Certify: `system:usb`, `group:open`.

**A-23. The binary layout is computed for the host.** `abi.py` builds each struct with
`ctypes.Structure` from the C types of `videodev2.h` (`c_uint32`, `c_int64`, `c_ulong`, `c_void_p`),
and each ioctl number with the `_IOC` arithmetic from `ctypes.sizeof` of its struct [U]. Thus the
layout and the numbers follow the C ABI of the system that runs the code [A]:
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
- Certify: `<label>:identity`.

**M-3. Virtual cameras.** A virtual camera has a `transportType` that is not USB, or a name with
"virtual" [W 7.1] [NV for the transport value]. A built-in or Continuity camera is real.
- Confidence: low. Certify: `system:virtual-cameras`.

**M-4. Mode list.** Each `AVCaptureDeviceFormat` has a media subtype, the dimensions and
`videoSupportedFrameRateRanges`. An MJPG mode of a UVC camera has the subtype `'dmb1'`
(`kCMVideoCodecType_JPEG_OpenDML`) [K18]. A range whose minimum and maximum rates are equal gives its
exact `minFrameDuration` `v/t` as `fps_num = t`, `fps_den = v` [A]. A range with a lower minimum than
maximum gives the rates 30000/1001, 30/1 and 60/1 that fall inside it, as A-4 does [A]; the source
then sets that exact frame duration. One third-party run saw the MJPG modes offered only as decoded
`'420v'` [R stack §4.3] [NV].
- Confidence: medium.
- Diagnostics: `modes_listed`, `mjpg_sizes`, `subtypes` (a fixed string of the FourCCs seen).
- Certify: `<label>:detect`, `<label>:modes`.

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
- Certify: `<label>:native-jpeg`. Byte-true is shown when `dqt_sha256` equals the value of the same
  camera model on Windows or Linux in the evidence file [cert 11.2] [A].
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
- Certify: `<label>:opens`, `<label>:rate`, `<label>:modes`.

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
- Certify: `self:hang-100ms`; T-UNX-84 checks the GIL release on the macOS runner.

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
- Certify: `<label>:clock`.

**M-10. Drops are visible.** `captureOutput:didDropSampleBuffer:fromConnection:` comes for each frame
that AVFoundation drops (`alwaysDiscardsLateVideoFrames` is true) [NV]. `CMIOSampleBufferGetSequenceNumber`
gives a sequence number for each sample [R mac_avf] [NV]. A drop or a sequence gap sets
`discontinuity = True` on the next frame [W D34].
- Confidence: low to medium.
- Diagnostics: `drops_reported`, `sequence_available`, `sequence_gaps`, `sequence_lost`,
  `discontinuity_flags` (D-3).
- Certify: `<label>:sequence` (`no-sequence` when `sequence_available` is false).

**M-11. Another app can use the camera at the same time.** macOS lets two processes stream one camera
[NV]. The other app can change the active format [NV]. The source never fails for sharing alone. It
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
cannot set an absolute exposure on macOS; it can lock the current exposure (`locked`, after
`isExposureModeSupported(.locked)`) [K19]. Absolute values are possible only through CoreMediaIO
feature controls (a public API, through Apple's own driver) or UVC requests on endpoint 0 (field
evidence only) [R macctl §1]. CoreMediaIO coverage on our four cameras is not known; one report
needed undocumented control classes [R macctl §1, §3 R1] [NV].
- The source uses the CoreMediaIO exposure control only when it has an absolute value in seconds:
  `kCMIOFeatureControlPropertyAbsoluteUnitName` names seconds, and
  `kCMIOFeatureControlPropertyAbsoluteValue` sets it [NV for the unit strings]. The source
  then sets `2^v` seconds directly. It never assumes the unit of `NativeValue` [A].
- A camera with no such control has no manual exposure: no Manual, no Auto and no exposure control in
  native capture; the camera keeps the exposure that macOS gives it; the warning `no-manual-exposure`
  says so [U]. "Auto by lock" of draft 1 is removed [U]. Certify tries every other approach for
  exposure as a probe (4.4.10) [U].
- Confidence: low.
- Diagnostics: `control_path` (`cmio`, `none`), `exposure_unit` (`seconds`, `none`), the set and get
  return codes (`native_domain` `osstatus`) (D-4).
- Certify: `<label>:controls`, `<label>:settings-stick` (`no-manual-exposure`), and the endpoint-0
  probe `probe:control-ep0` [U].

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

**M-18. The USB link.** The IORegistry entry of the USB device, found by the `locationID` of
`uniqueID`, has the link speed [R xplat §2.5] [NV for the property name]. The source reads it through
`ctypes` calls to IOKit [A]. When it cannot, the label is `unknown`.
- Confidence: low. Diagnostics: `usb_link`; `usb_alt` is null. Certify: `system:usb`.

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
| A-2 | Identity: serial, else port chain from sysfs; by-id not used | med | `<label>:identity` |
| A-3 | v4l2loopback: no USB parent, driver name | med | `system:virtual-cameras` |
| A-4 | ENUM ioctls give discrete MJPG sizes and intervals | high | `<label>:detect`, `<label>:modes` |
| A-5 | `S_FMT` can grant another size; read back | high | `<label>:modes`, `<label>:native-jpeg` |
| A-6 | `S_PARM` sets the rate; read back with tolerance 0.0001 | high | `<label>:rate`, `<label>:modes` |
| A-7 | mmap MJPG buffers are the camera's bytes | high | `<label>:native-jpeg` |
| A-8 | Damaged frames carry `V4L2_BUF_FLAG_ERROR` (nodrop) | high | `<label>:native-jpeg` |
| A-9 | Buffer time is `CLOCK_MONOTONIC`, the base of `perf_counter_ns` | high (grain NV) | `<label>:clock` |
| A-10 | `sequence` gaps show lost frames | high | `<label>:sequence` |
| A-11 | 4 mmap buffers; push source with the newest frame | high | `<label>:opens` |
| A-12 | `O_NONBLOCK` and `poll`: no unbounded wait for a frame | high | `<label>:cycles` |
| A-13 | Blocking ioctls bounded (11 s for probe and commit, else 5 s); GIL released | high / med | `self:hang-100ms` |
| A-14 | In use is `EBUSY` at `REQBUFS(0)` or after the PROBE of `S_FMT` | high | `<label>:in-use` |
| A-15 | Bandwidth refusal is `EIO` (or `ENOSPC`, `ENOMEM`, `EFBIG`) at `STREAMON` | med | `group:open` |
| A-16 | No access is `EACCES`; seat ACL, `video` group or root | high / med | `system:camera-access` |
| A-17 | Control ids; MANUAL in the same call; no absolute value in auto | high | `<label>:controls`, `<label>:auto-off` |
| A-18 | log2 s to 100 µs map; -7 gives 78 | high | `<label>:controls` |
| A-19 | Read-back can be cached | med | `<label>:settings-stick` |
| A-20 | Controls hold while streaming | med | `<label>:settings-stick` |
| A-21 | Close under 1 s; reopen works; Kiyo Pro quirk by kernel | low | `<label>:cycles`, `probe:kernel` |
| A-22 | USB link from sysfs; alternate setting of the VideoStreaming interface | med | `system:usb`, `group:open` |
| A-23 | Layout and ioctl numbers computed for the host; 64-bit time layout; x32 refused | high / med | `detect` |
| A-24 | `spawn` and `O_CLOEXEC` | high | — |
| M-1 | Discovery session lists cameras with no permission | med | `detect` |
| M-2 | `uniqueID` = locationID, VID, PID (holds the port) | med | `<label>:identity` |
| M-3 | Virtual by transport type or name | low | `system:virtual-cameras` |
| M-4 | MJPG modes have subtype `'dmb1'`; ranges give 29.97, 30, 60 inside them | med | `<label>:detect`, `<label>:modes` |
| M-5 | `'dmb1'` samples hold the camera JPEG in a block buffer | low–med | `<label>:native-jpeg` |
| M-6 | Session order; format and duration under the lock across `startRunning` | med | `<label>:rate`, `<label>:modes` |
| M-7 | Delegate queue and notifications with no run loop; CMIO run loop NULL | low–med | `<label>:opens` |
| M-8 | PyObjC releases the GIL | med | T-UNX-84, `self:hang-100ms` |
| M-9 | PTS converted to the host clock and the `perf_counter_ns` base | med / low | `<label>:clock` |
| M-10 | Drops and sequence numbers are visible | low–med | `<label>:sequence` |
| M-11 | Sharing allowed; a format change is detected | low | `<label>:in-use` |
| M-12 | Runtime errors and removal by notification | med | `<label>:in-use` |
| M-13 | No bandwidth error; first-frame timeout or low rate | low | `group:open` |
| M-14 | Permission status read; no permission gives zero frames | med | `system:camera-access` |
| M-15 | Absolute exposure only through CoreMediaIO in seconds, else no manual exposure | low | `<label>:controls`, `<label>:settings-stick`, `probe:control-ep0` |
| M-16 | Effect flags readable; Edge Light not | med | `system:video-effects` |
| M-17 | Close under 1 s | low | `<label>:cycles` |
| M-18 | USB link from the IORegistry | low | `system:usb` |
| M-19 | macOS 12.3 and later | high | `detect` |
| M-20 | PyObjC works in the frozen app | med | T-UNX-88, `detect` |

## 3. What stays and what is shared

- The capture interface of [W 4.1] stays: `open`, `read_frame`, `set_controls`, `close` and
  `replaced_count`. Section 4.2 adds `diagnostics()` and the failure code.
- The shared loop, the gate, the warm-up, the rate check, the recorder and the rings stay as
  [W 5] to [W 12] give them, with the changes of 4.2 and 4.5. The floor of 30 fps [W U11] and one
  rate (30 or 60) for all cameras [U] apply to each source.
- `CaptureWaitingPlace` of `source.py` serves both new sources (push sources).
- The OpenCV source stays as the fallback on Linux and macOS until a camera model is checked on the
  system (4.9) [U].

## 4. The design

### 4.1 Package layout

| Path | Content |
|---|---|
| `skellycam/core/camera/capture/bounded.py` | The bounded call of [W 6.6], moved out of `media_foundation/bounded.py` with no COM, with a limit argument (5 s default, 11 s for A-13). `media_foundation/bounded.py` keeps a wrapper that joins the MTA in each worker [A]. |
| `skellycam/core/camera/capture/failure_codes.py` | The failure codes of 4.6.3. Pure. |
| `skellycam/core/camera/capture/exposure_units.py` | The map of A-18 and the seconds map of M-15. Pure. |
| `skellycam/core/camera/capture/camera_checks.py` | The local record of certify-checked camera models (4.9). Pure file I/O. |
| `skellycam/core/camera/capture/v4l2/` | Linux only at run time. `abi.py` (ctypes structs and ioctl numbers computed for the host (A-23), and constants; ported from linuxlib, whose LP64 reference values become test values); `device.py` (the seam: `V4L2System`, with the real calls `os.open`, `fcntl.ioctl`, `mmap`, `select.poll`, `os.close`, and sysfs reads under a root path); `detect.py`; `controls.py`; `errors.py` (errno to code, pure); `source.py` (`V4L2Source`). |
| `skellycam/core/camera/capture/avfoundation/` | macOS only at run time. `layer.py` (the seam: `AVLayer`, and `PyObjCLayer`, the real calls); `detect.py`; `controls.py` (CoreMediaIO); `errors.py` (AVError name to code, pure); `iokit.py` (the USB link, `ctypes`); `source.py` (`AVFoundationSource`). |
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
   The OpenCV source gives `backend` and null for each other source key. The camera process writes the
   dict into the camera status at the end of `open`, at each control read (one time per second
   [W 11.4]), at a failure and at the close. `CameraStatus.serialize()` adds `"diagnostics"`.
3. The shared loop adds its own keys to the same dict: `decoded_by_skellycam`,
   `encoded_by_skellycam` (D-10), `dht_inserted`, and the frame hashes of D-11 (4.6.2).
4. The exposure rules of 4.5 apply to each source [U].
5. The restore of the controls at the close (4.7) is on by default on each source [U].
6. `select_capture_source()` of `camera_worker.py` covers Linux and macOS by 4.9.
7. `detect_available_cameras()` calls the native detection on Linux and macOS, also when OpenCV is
   chosen, as Windows does [W D11]. The OpenCV source then opens the node that detection names
   (Linux: `cv2.VideoCapture(<node>, cv2.CAP_V4L2)`); on macOS it takes the index of the device in the
   list of `AVCaptureDevice.devicesWithMediaType_` that OpenCV uses, found by `uniqueID` [A] [NV].
8. `CameraDeviceInfo` gets `backend` (`v4l2`, `avfoundation`, `media-foundation`), `usb_link`
   (`usb3`, `usb2`, `usb1`, `unknown`) [U], `id_source`, `has_serial`, `evidence` (`verified`,
   `known-bad`, `unknown`) and `checked` (true when the local record of 4.9 holds a passed full run
   for its model on this OS key). The status gets `system_evidence` [cert 11.3]. The app uses them
   for the prompt to run certify [cert 11.4].
9. The `camera_id` hash stays the function of today; its input changes on Linux and macOS (A-2,
   M-2). Each Linux and macOS camera gets a new ID one time, as on Windows [W D11] [U].

### 4.3 The V4L2 source (step 7a)

#### 4.3.1 Detection

In a short-lived `spawn` child, each call bounded, as on Windows [W 7.1, A]:

1. Refuse on the x32 ABI (A-23).
2. List `/dev/video*`. For each node: `open(O_RDWR | O_NONBLOCK | O_CLOEXEC)`, `VIDIOC_QUERYCAP`
   (A-1). Skip a node with no video capture in `device_caps`.
3. Read the sysfs data of A-2 and A-22. A node that cannot be opened (`EACCES`) is listed from sysfs
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
| `exposure` (`auto: true`) | Never sent: the camera's own auto exposure is never set (4.5) [U] | — |
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
   [W W6], `virtual` (M-3), `usb_link` (M-18).
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
   `'dmb1'` [K18]), take the device lock again, `startRunning`, unlock (M-6).
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

| skellycam control | Path | When absent |
|---|---|---|
| `exposure` (a value) | CoreMediaIO exposure feature control: `AutomaticManual = 0` (manual), then `AbsoluteValue` = `2^v` s; and AVFoundation `exposureMode = locked` when `isExposureModeSupported(.locked)`, so that AVFoundation does not apply its own auto mode again [R macctl §1 item 3] | `no-manual-exposure` [U] |
| `gain` | CoreMediaIO gain feature control, manual, `NativeValue` (raw, as UVC) [NV] | absent |
| `focus` | CoreMediaIO focus feature control; with `auto: true`, `AutomaticManual = 1` | absent |
| `white_balance`, `power_line` | CoreMediaIO read, if published | absent |

- The source finds the CoreMediaIO device whose `kCMIODevicePropertyDeviceUID` equals `uniqueID`
  [R macctl §1]. It reads the constants from `pyobjc-framework-CoreMediaIO`, never from FourCCs in
  the code [A].
- After each `startRunning`, the source sets the controls again [R macctl §1 item 3] [W D20].
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
one is found [U]. The product uses only the approaches that the rulings allow:

| Need | Product (allowed) | Certify only (probes) |
|---|---|---|
| The camera's JPEG | `videoSettings = {}`, then `kCVPixelBufferPixelFormatTypeKey = 'dmb1'` (4.4.3) | each other approach of the list |
| Exposure | CoreMediaIO exposure feature control with an absolute value in seconds (4.4.6) | each other approach of the list, endpoint 0 included (`probe:control-ep0`) [U] |

**Approaches to try: see the certify probes, to be filled from the approaches list.** A research job
writes that list with a certify check for each approach. It did not exist when this draft was written.
Candidates that the research already names, for that list to confirm or extend [R mac_avf, macctl]:
for the JPEG, the `videoSettings` variants `nil`, `jpeg4cc`, `dmb1_sized` (with the size, as
Chromium), `chromium`, and an `AVVideoCodecKey` from `availableVideoCodecTypes`; for exposure,
CoreMediaIO `NativeValue`, CoreMediaIO `NativeData` on the `uc**` classes, and endpoint-0 class
requests through the IOKit interface (`ControlRequest`) and device (`DeviceRequest`) with no open.
Each probe is record-only and runs in the risky phase of certify when it can change the camera.

### 4.5 Exposure on each source (the rulings of the user)

The user ruled on 2026-11-20 [U, R plan §14]. These rules apply to Media Foundation, V4L2 and
AVFoundation, through the shared loop and `set_controls`:

1. Two modes: Manual and Auto. Auto always means that SkellyCam finds a manual value by its one-shot
   search on the open stream. The camera's own auto exposure is never a mode, and no source ever sets
   it [U]. "I never want to allow the camera to set it's own exposure" [U].
2. Auto stays the stored mode (`exposure_mode: "AUTO"`). The value that the last search found is
   stored beside it, as `exposure_found` (log2 seconds, null before the first search) [U, A]. A config
   with `RECOMMEND` reads as Auto [A].
3. A camera in Auto searches at each open (also each reopen), when the user changes the frame rate
   (that is a reopen [W D31]), and when the user asks: an apply request with `exposure_search: true`
   for the camera [U, A]. A camera in Manual keeps the user's value and never searches [U].
4. A new camera starts in Auto [U].
5. The open of a camera in Auto runs the warm-up and the start-up rate check of [W 9, W 10.1] at -7
   (7.8 ms) [A]. Then the search runs.
6. During the search the state is `adjusting`: the camera is in the gate, the preview shows, and a
   record start is refused with 409 [U]. The apply or open request answers when the cameras are open
   and streaming; it does not wait for the search. The result of the search (`exposure_found`, or the
   `too_slow` failure) arrives through the camera status [U]. `adjusting` joins the states of [W 8.1] with the same rights
   as `checking` in [W 8.3].
7. The search: the range -12 to -5, 10 frames to settle at each value, the mean of the decoded image
   against 127.5, and one step darker than the nearest value [W 11.1]. Then the guard: the rate check
   of [W 10.2] at that value; when it fails, one step darker, and again, to -12 [U, A]. The first value
   that passes is kept. The search never keeps a value at which the frame rate falls [U].
8. When no value passes, the search restores the exposure that the camera had before the search, and
   the camera is `too_slow` with the reason "Camera is slow. Try adding more light" [U].
9. The slow-camera text is exactly "Camera is slow. Try adding more light" [U]. It replaces the text of
   [W 10.4] for each slow-camera failure; the failure object keeps `declared_fps` and `measured_fps`
   as numbers [A].
10. Exposure never changes during a take [U]: the search never starts in `recording`, and a change is
    refused [W D36].
11. Nothing below 30 fps; one frame rate (30 or 60) for all cameras [U].
12. A macOS camera with no manual exposure (M-15) has no Manual, no Auto and no exposure control in
    native capture. The apply response and the status carry a warning of the kind
    `no-manual-exposure` in the form of [W 11.3]; the camera does not fail [U].

Changes for Media Foundation: the same rules, in a separate commit [U]. Draft 2 adds a note to
[`windows-capture.md`](windows-capture.md) that names the sections and tests that change: D29, 8.1 to
8.3 (`adjusting`), 10.4, 11.1, 11.3 (no `auto_control` warning for exposure), and the tests T-CAP-12,
T-CAP-18, T-CAP-34, T-CAP-41, T-CAP-42, T-CAP-53, T-CAP-77, T-CAP-94 and T-CAP-104.

### 4.6 Diagnostics

#### 4.6.1 Rules

- `diagnostics()` returns one dict with fixed keys. Each value is an int, a float, a bool, null or a
  string of a fixed vocabulary, with one exception: `frame_log`, a list of at most 64 rows [A].
- Each key, value and code that certify reads has the name of [cert 10.2, 10.3, 15]. Section 4.6.4
  lists what certify must add.
- No value holds a serial number, a device path, a `uniqueID`, a `camera_id`, a camera name, a host
  name or a user name [cert 9.4]. A SHA-256 of frame bytes is allowed: it does not show the image.
- Every source gives every key; a key that a source cannot fill is null.
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
| D-3 | `frames`, `sequence_available`, `sequence_gaps`, `sequence_lost`, `discontinuity_flags`, `error_flag_frames`, `zero_bytes`, `drops_reported`, `poll_timeouts`, `format_changes` | yes | yes | yes |
| D-4 | For each control `c` of `exposure`, `gain`, `focus`, `white_balance`, `power_line`: `c_present`, `c_min`, `c_max`, `c_step`, `c_default`, `c_auto_supported`, `c_native_id`, `c_value` (native), `c_auto`, `c_set_rc`, `c_get_rc`, `c_before`, `c_before_auto`; and `exposure_unit` (`log2-s`, `100us`, `seconds`, `none`), `exposure_native_at_m7`, `control_path` (`v4l2`, `cmio`, `avf-lock`, `ep0`, `iam`, `ks`, `none`), `ae_off_ok`, `af_off_ok`, `ae_back_on_after_s` | yes | yes | yes |
| D-5 | `fail_code`, `native_code` (a number), `native_domain` (`errno`, `hresult`, `nserror`, `osstatus`, `ioreturn`), `call` (4.6.3), `fail_stage`, `failed_calls`, `busy_call` | yes | yes | yes |
| D-6 | `t_enumerate_ms`, `t_open_ms`, `t_set_mode_ms`, `t_buffers_ms`, `t_stream_on_ms`, `t_first_frame_ms`, `t_controls_ms`, `t_close_ms` | yes | yes | yes |
| D-7 | `id_source` (`serial`, `id-path`, `unique-id`, `mf-link`), `has_serial` | A-2 | M-2 | `mf-link` |
| D-8 | `access` (`seat-acl`, `video-group`, `root`, `none`); `tcc` (`granted`, `denied`, `restricted`, `not-determined`); `center_stage`, `portrait`, `studio_light`, `reactions`, `edge_light` | `access` | `tcc`, effects | null |
| D-9 | `usb_alt`, `usb_link` | sysfs (A-22) | `usb_alt` null | null; `usb_link` from the `sfn26` port |
| D-10 | `decoded_by_skellycam`, `encoded_by_skellycam` (the shared loop) | yes | yes | yes |
| D-11 | `sha256_00` to `sha256_29` and `sha256_frame_00` to `sha256_frame_29` (the `source_frame_number` of each hashed frame), `sha256_trigger` (`ready`, `recording`), `dht_inserted`, `dqt_sha256` (the shared loop) | yes | yes | yes |
| Linux | `kernel`, `driver`, `nodrop_param`, `clock_param`, `hwtimestamps_param`, `buffers_requested`, `buffers_granted`, `interval_types`, `nodes_seen`, `nodes_skipped_meta`, `modes_listed`, `mjpg_sizes` | yes | null | null |
| macOS | `macos`, `subtypes`, `notifications_seen`, `sync_clock_is_host`, `modes_listed`, `mjpg_sizes` | null | yes | null |

D-11 [A]: the shared loop hashes the bytes that it gives to the ring and the recorder (after a DHT
insertion), for the first 30 frames that it takes after each move to `ready` and after each record
start. Each new trigger replaces the set. Thus certify compares each hash with the ring slot and the
MKV block of the same `source_frame_number`. Warm-up frames are never hashed: they reach neither the
ring nor the recorder [W 9.2].

#### 4.6.3 Failure codes and call names

Codes [U, cert 15]: `not-found`, `no-access`, `no-permission`, `camera-in-use`, `usb-bandwidth`,
`no-mode`, `below-floor`, `open-failed`, `first-frame-timeout`, `no-native-jpeg`, `not-ready`,
`rate-low`, `rate-high`, `control-failed`, `device-removed`, `stalled`, `hung`, `disk-stall`. Codes
that certify must add (4.6.4): `previous-process-alive`, `stream-error`, `format-changed`,
`process-ended`, `no-manual-exposure`.

Call names (`call`, `busy_call`): the values of [cert 10.2] `open`, `s-fmt`, `reqbufs`, `streamon`,
`session-start`, `first-frame`, and these that certify must add: `querycap`, `s-parm`, `qbuf`, `dqbuf`,
`poll`, `streamoff`, `close`, `s-ext-ctrls`, `g-ext-ctrls`, `add-input`, `lock-config`,
`stop-running`, `cmio-set`, `cmio-get`, `activate`, `set-mode`, `read-sample`, `flush`, `shutdown`.

#### 4.6.4 What certify must add or change

| Item | This spec | Certify draft 3 | Change in certify |
|---|---|---|---|
| Codes | `previous-process-alive`, `stream-error`, `format-changed`, `process-ended`, `no-manual-exposure` | absent from 15 | add, each with one sentence |
| `call` values | 4.6.3 list | six values | add the others |
| `native_domain` | key and five values | D-5 asks a domain string, no key | adopt the key and values |
| `access` | adds `root` | `seat-acl`, `video-group`, `none` | add `root` |
| `control_path` | adds `cmio` | no `cmio` | add `cmio` |
| `exposure_unit` | adds `seconds` | `log2-s`, `100us`, `none` | add `seconds` |
| Control keys | `c_present`, `c_min`, ... | "present, min, max, step, default, auto_supported" without a key form | adopt the `c_` form |
| `<label>:auto-off` | `ae_off_ok`, `af_off_ok`, `ae_back_on_after_s` | also `awb_off_ok`, `set_while_auto_errno` | drop both, or move them to a probe: white balance is read only [W D43], and the source never sets an absolute value in auto (A-17) |
| D-11 | 30 frames after `ready` or a record start, after the DHT insertion, with `source_frame_number` | "the first 30 raw buffers" | change the text; compare by frame number |
| `grain_ms`, `jitter_p95_ms` | certify computes them from `frame_log` | listed as numbers of `<label>:clock` | compute from `frame_log` |
| `probe:usb-alt` | the source gives `usb_alt` (A-22) | probe when the source does not | keep only as a fallback, or drop |
| `<label>:control-ep0` and 10.1 | endpoint 0 only as a certify probe [U] | 10.1 puts endpoint-0 controls in the product; `control-ep0` is a camera check | rename to `probe:control-ep0`, owned and coded by certify; change 10.1 |
| macOS camera with no manual exposure | opens; warning `no-manual-exposure` [U] | `opens` at manual -7 | accept the warning in `opens`; `settings-stick` `fail` `no-manual-exposure`; camera item `partial` |
| A camera that another program holds | failure code `camera-in-use` | format 1.3.0: result `skipped`, reason `busy` [U] | map `camera-in-use` to `skipped` with `busy` |
| Evidence and local pass key | the ABI (`lp64`, `ilp32`) beside the OS key (A-23) | OS key and backend | add `abi` to the keys of 11.2 and 11.3 |
| macOS approaches | the product uses only the approaches of 4.4.10 that the rulings allow; certify tries each other one as a probe [U] | `native-jpeg` with three variants; `control-ep0` | one probe check for each approach of 4.4.10 |
| Local pass | per camera model (VID:PID), OS key and backend, full only [U] | per OS key (11.3) | key the local pass by model |
| Exposure at open | Auto searches; `adjusting` state; `exposure_found` [U] | `auto-exposure` reads the found value | read `exposure_found`; wait while `adjusting` |
| Slow text | "Camera is slow. Try adding more light" [U] | 10.4 text of cap | certify maps by `rate-low`; no text change needed |
| OpenCV fallback | never inside certify [U] | native only | none |

### 4.7 Restore of the controls at the close [U]

- At the first control read of each open, before any set, the source keeps each control value and
  its auto flag (`c_before`, `c_before_auto`).
- At the close, each source sets each changed control back to its "before" value and auto flag and
  reads it back, before `STREAMOFF`, `stopRunning` or the Media Foundation flush (A-20). A failed
  restore is logged and recorded; the close continues [A]. This is on by default on each system [U].
- The setting `SKELLYCAM_RESTORE_CONTROLS=0` turns it off, for a debug run only [A].
- A camera that failed, hung or was removed is not opened again to restore it [U]. The restore runs
  only inside the close of an open camera.

### 4.8 Threads

| Thread | Linux | macOS |
|---|---|---|
| Capture | `v4l2 capture` (4.3.3) | the serial dispatch queue (4.4.4) |
| Waiting place, camera loop, control thread | as [W 4.3] [W U16] | as [W 4.3] |
| Bounded-call workers | `capture/bounded.py` | the same |
| Notifications | none | the `NSOperationQueue` of M-7 |

No thread spins [W 4.3].

### 4.9 Source selection and the local record [U]

- Settings: `SKELLYCAM_LINUX_CAPTURE` (`opencv`, `v4l2`) and `SKELLYCAM_MACOS_CAPTURE` (`opencv`,
  `avfoundation`), on the model of `SKELLYCAM_WINDOWS_CAPTURE` [W 14.2] [A]. A wrong value gives an
  error that names the allowed values.
- The source of a camera is the first that applies [U]:
  1. The setting, when it is set.
  2. The local record: a passed full certify run on this machine for the model of the camera.
  3. A `verified` row of the shipped evidence file [cert 11.2] for the model, the backend and the OS,
     or for the OS key and the backend.
  4. Else OpenCV.
- The local record [U, A]: "A camera counts as certify-checked once per model (USB vendor id and
  product id) per system; skellycam keeps that record" [U].
  - File: `camera_checks.json` in the skellycam base folder (`get_default_skellycam_base_folder_path()`
    of `skellycam/system/default_paths.py`).
  - Format: `{"schema": 1, "checks": [{"device": "046d:085c", "backend": "v4l2", "os_key": "7.0",
    "abi": "lp64", "level": "full", "result": "pass", "skellycam": "2.0.0a6", "date": "2026-11-20"}]}`.
  - Certify writes one row for each camera model that a full run checked: `result` is the camera
    item of that model (`pass`, `partial`, `fail`, `record-only`, `skipped`) [U: certify format
    1.3.0]. A quick run writes no row [cert 11.3].
  - Rule 2 applies when a row with the camera's device, backend, ABI and current OS key has `pass` or
    `partial`. The evidence rows of rule 3 match the ABI too (4.6.4). A row with another OS key does not apply: on Linux a new kernel major or minor version
    is a new OS key [cert 11.2].
  - A newer row for the same key replaces the older one.
- A camera whose native open fails with `no-native-jpeg`, or whose evidence row is `known-bad` for the
  native backend, opens with OpenCV when the default (not the setting) chose native [U]. The status
  shows `backend: opencv`.
- Certify always uses the native source, and the per-camera OpenCV fallback never runs inside certify
  [U].
- Detection is always native (4.2 item 7).

### 4.10 Main-process stall watch [U]

The main process removes from the gate a camera in an open state whose status shows no new frame and
no report for 2 s, marks it `dead` with `stalled`, and ends its process. This guards the 100 ms rule
when a driver call or PyObjC holds the GIL of a camera process (M-8).

### 4.11 CI

- The capture workflow runs the new fake-layer tests in its three jobs, with no new job [A].
- The timing tests (T-UNX-18, T-UNX-45, T-UNX-79) have the marker `capture_timing`, which the macOS
  job runs in its own step (capture.yml) [A].
- `capture-linux` also runs `capture_linux_runner` tests (6.3). One step runs `sudo modprobe vivid ||
  true`; the `v4l2_vivid` tests skip without a vivid node. Whether a hosted runner can load vivid is
  not known [K23] [NV]; no done item depends on it.
- `capture-macos` also runs `capture_macos_runner` tests; `uv sync` installs PyObjC through its markers.
- The build workflow runs T-UNX-88 on its macOS jobs.

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
| D8, U1, T-CAP-43, T-CAP-76, T-CAP-88 | differs: `SKELLYCAM_LINUX_CAPTURE`; OpenCV until a model is checked [U] | differs: `SKELLYCAM_MACOS_CAPTURE` |
| D9 | n/a | n/a |
| D10, U12, U16 | same: A-13 | same if M-8 holds |
| D11, D12, D13, W6 | same: A-1, A-2, A-14 | same: M-1, M-2; in use differs (M-11) |
| D14, U11 | same | same |
| D15, D16, D17, D18, U7, U10, U15 | same | same |
| D20, D21, D22, D23, D24 | same | same |
| D25 (slow text) | differs: "Camera is slow. Try adding more light" on each source [U] | the same |
| D26, D27 | same | same |
| D28 | same; `sample_ns` from A-9 | same; `sample_ns` from M-9 (unknown until certified) |
| D29, D35 (exposure modes, unit) | differs: 4.5 on each source [U]; unit map A-18 | differs: 4.5 with CoreMediaIO seconds; no manual exposure without it [U] |
| D30, D31, D32, D33, D36 | same; `adjusting` added (4.5) | same |
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
| 11.1 search | differs: 4.5 (guard, `adjusting`, stays Auto) | the same, with CoreMediaIO |
| 12 stage names | same; adds codes | same |
| 13 uncompressed modes | n/a in this step | n/a in this step |
| 14.1 forced auto exposure on Linux | differs: ends for the native source [U] | n/a |
| 15 CI | same jobs, more tests | same |

### 5.3 Tests of the Windows spec

| T-CAP IDs | Linux | macOS |
|---|---|---|
| 01 to 11, 13 to 17, 19 to 21, 25 to 33, 35 to 40, 44, 61 to 67, 70 to 75, 80 to 87, 89 to 91, 99 to 103, 105 to 113 (fake source and OpenCV fake) | same: they run in CI today [W 16.7] | same |
| 12, 18, 34, 41, 42, 104 (exposure and slow text) | differs: change with 4.5; T-UNX-69 adds the new rules | the same |
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
| 52 | differs: certify `<label>:opens`, `<label>:native-jpeg` | differs: the same (M-5): unknown |
| 53, 94 | differs: certify `<label>:rate` | the same |
| 54, 93 | differs: certify `<label>:rate:<mode>` | the same |
| 55, 96 | differs: certify light rule [cert 4.6] | the same |
| 56 | differs: certify `<label>:in-use` | the same (M-11) |
| 57, 97 | differs: certify `<label>:exposure:<base>` | differs: the same, if M-15 holds |
| 58, 95 | n/a: no hot-unplug test [U] | n/a |
| 59 | differs: certify `<label>:clock` | the same |
| 60, 98 | differs: certify `group:take-30` | the same |
| 68, 69 | n/a in this step | n/a in this step |
| 77 | n/a: no camera auto mode (4.5) | n/a |
| 78 | differs: certify `<label>:control:*` | differs: the same, CoreMediaIO |
| 79 | differs: certify `<label>:detect`, `<label>:modes` | the same |
| 88 | n/a | n/a |
| 92 | retired: OpenCV needs no test [U] | retired |

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
  `abi()` (`lp64`, `ilp32`, `x32`), `getgroups()`, `geteuid()`, `kernel_release()`. Each real method is one
  standard-library call. Paths are under `dev_root` (default `/dev`) and `sys_root` (default `/sys`).
- `FakeV4L2System` scripts: nodes with `QUERYCAP` data; a sysfs tree with USB devices, VideoControl
  and VideoStreaming interfaces and module parameters; formats, sizes and intervals; `S_FMT` and
  `S_PARM` adjustments; buffers with bytes, `sequence`, timestamp and flags; an errno or a hang at a
  given call and count; `poll` events; a node that disappears. It checks each ioctl number and struct
  size that the source sends.
- `AVLayer` (`avfoundation/layer.py`): `macos_version()`, `authorization_status()`, `devices()`,
  `open_device(unique_id)`, `configure(format_index, duration, variant)` (the order of M-6),
  `start(callback)`, `stop()`, `close()`, `to_host_ns(pts)`, `sync_clock_is_host()`, `cmio_controls()`
  (list, get, set, unit name), `exposure_lock_supported()`, `effects()`, `usb_speed(location_id)`, and
  a notification callback.
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
| T-UNX-06 | USB link from sysfs `speed` 12, 480, 5000, 10000, missing. | `usb1`, `usb2`, `usb3`, `usb3`, `unknown`. |
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
| T-UNX-18 | `capture_timing`. `poll` times out for 6 s after 10 frames (virtual clock). | `dead` 2.0 to 2.25 s after the last arrival [W 9.5]; the capture thread uses under 2 % of one core while it waits. |
| T-UNX-19 | Removal: `ENODEV` at `DQBUF`; `ENODEV` at `QBUF`; `EIO` with the sysfs node gone; `EIO` three times with the node present. | `device-removed` (dead at once) for the first three; `stream-error` for the fourth. |
| T-UNX-20 | `DQBUF` raises `InterruptedError` once at each of 10 frames. | 10 frames delivered; no failure. |
| T-UNX-21 | Exposure: set -7; -12 with a minimum of 3; -5; a camera with only menu items 1 and 3. | One `S_EXT_CTRLS` per set with the menu item 1 first, then 78, 3 and 313; the read-back compares native values; status -7, -12, -5; `exposure_native_at_m7` 78. |
| T-UNX-22 | The fake returns `EACCES` for an absolute value sent alone while the menu is 3. | The source never triggers it; a forced lone absolute set gives `control-failed`, and the camera stays in its earlier state [W U14]. |
| T-UNX-23 | A camera in Auto through `V4L2Source` and the shared loop, with a brightness model in the fake. | The menu is MANUAL at each set; the search of 4.5 runs; the config keeps `AUTO` with `exposure_found`; `V4L2_CID_EXPOSURE_AUTO` is never set to 0 or 3. |
| T-UNX-24 | Gain, focus, focus auto; a camera with no focus; white balance and power line values; a gain control with the flag `inactive`. | Set and read back; focus absent gives `present: false` and the text of [W 11.5]; white balance and power line get no set call; the inactive control gives `control-failed`. |
| T-UNX-25 | A control ioctl hangs on the control thread while two fake cameras are `ready`. | As T-CAP-82: stage `streaming`, code `hung`, hard end; the other camera has no gap above 100 ms. |
| T-UNX-26 | `STREAMOFF` hangs at the close; `S_FMT` takes 8 s (a slow camera); `S_FMT` hangs. | `hung`, stage `close`, hard end within 5 s + 2 s; the slow `S_FMT` passes (limit 11 s); the hung `S_FMT` gives `hung` at 11 s. |
| T-UNX-27 | The close order; with the restore on (default) and with `SKELLYCAM_RESTORE_CONTROLS=0`; a restore set that fails. | Stop, join (under 1 s), restore (each changed control set back to its "before" value and auto flag, and read back), `STREAMOFF`, `munmap` x4, `REQBUFS(0)`, `close`; with the setting 0 no restore; a failed restore is logged and the close goes on. |
| T-UNX-28 | `diagnostics()` after 100 frames, with fake groups, euid and module parameters: (1) user in `video`; (2) not in `video`, access works; (3) euid 0; (4) `EACCES`. VideoStreaming sibling with alternate setting 3 after `STREAMON`. | Every key of 4.6.2 is present with its type; `access` `video-group`, `seat-acl`, `root`, `none`; `usb_alt` 3 (from the VideoStreaming interface, not the VideoControl one); `nodrop_param`, `clock_param`, `hwtimestamps_param` from the fake files; `frame_log` 64 rows; no value matches a path, a serial or a name of the fake. |
| T-UNX-29 | Three `V4L2Source` cameras over the fake through the shared loop, 30 s of virtual time at 30 fps. | Equal ring frame counts; payload bytes equal the fake bytes; the rules of T-CAP-05 on the gaps and `replaced_count`. |
| T-UNX-30 | `abi.py` built with ILP32 stand-in types (pointer and `long` of 4 bytes) and a 64-bit alignment of 8, then of 4; detection with `abi()` `x32`. | `v4l2_buffer` 80 and 76 bytes, `VIDIOC_DQBUF` 0xC0505611 and 0xC04C5611, `timestamp` two 64-bit integers; x32: `backend-missing` and the OpenCV source. |

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
| T-UNX-40 | T-UNX-21, T-UNX-22 | Controls: CoreMediaIO exposure in seconds; in another unit; absent; present but the set is ignored; lock supported and not supported. | Seconds: -7 sets `2^-7` s and reads back, the AVFoundation mode is locked when supported and left alone when not; another unit or absent: no exposure control, warning `no-manual-exposure`, the camera opens [U]; ignored: `control-failed`, the camera keeps its state. |
| T-UNX-41 | T-UNX-07 | `camera_id` inputs: `uniqueID` in mixed case; two identical cameras on two ports. | `avf:` plus the lower-case `uniqueID`; two IDs; the hash function of today. |
| T-UNX-42 | T-UNX-08 | A forced duplicate `camera_id`. | Refused with an error that names both devices [W D13]. |
| T-UNX-43 | T-UNX-09 | Detection where `devices()` hangs. | The detection child ends within 5 s + 2 s with `hung`; the main process runs on. |
| T-UNX-44 | T-UNX-17 | Samples 0 to 4 arrive before the first `read_frame`. | Frame 4; `replaced_count` 4. |
| T-UNX-45 | T-UNX-18 | `capture_timing`. No sample for 6 s after 10 samples (virtual clock). | `dead` 2.0 to 2.25 s after the last arrival. |
| T-UNX-46 | T-UNX-19 | The removal notification at sample 50; an `AVErrorDeviceNotConnected` runtime error. | `dead` at once, `device-removed`, both cases. |
| T-UNX-47 | T-UNX-23 | A camera in Auto through `AVFoundationSource`, CoreMediaIO in seconds, a brightness model. | The search of 4.5 runs with manual CoreMediaIO sets only; the config keeps `AUTO` with `exposure_found`; `AutomaticManual = 1` is never set for exposure. |
| T-UNX-48 | T-UNX-24 | Gain, focus, focus auto through CoreMediaIO; a camera with no focus; white balance and power line read. | Set and read back; focus absent gives `present: false` and the text of [W 11.5]; white balance and power line get no set call. |
| T-UNX-49 | T-UNX-25 | A CoreMediaIO call hangs on the control thread while two fake cameras are `ready`. | Stage `streaming`, `hung`, hard end; the other camera has no gap above 100 ms. |
| T-UNX-50 | T-UNX-26 | `stopRunning` hangs at the close; `startRunning` hangs at the open. | `hung`, stages `close` and `start stream`; hard end within 5 s + 2 s. |
| T-UNX-51 | T-UNX-27 | The close order with the restore on (default) and off; a failed restore. | Observers removed, delegate nil, restore (each changed control back, read back), `stopRunning`, input and output removed; setting 0: no restore; a failed restore is logged and the close goes on. |
| T-UNX-52 | T-UNX-28 | `diagnostics()` after 100 samples, with effect flags set. | Every key of 4.6.2 with its type; `tcc`, the effect keys, `edge_light` null, `sync_clock_is_host`; no value matches a `uniqueID` or a name. |
| T-UNX-53 | T-UNX-29 | Three `AVFoundationSource` cameras over the fake through the shared loop, 30 s of virtual time. | As T-UNX-29. |
| T-UNX-54 | T-UNX-06 | USB speed values from the fake IORegistry: full, high, super, missing. | `usb1`, `usb2`, `usb3`, `unknown`. |
| T-UNX-55 | — | The delegate raises inside the copy. | The error marker; `read_frame` raises `CaptureFailure` with `stream-error`; nothing raises into the layer. |
| T-UNX-56 | T-UNX-30 | Detection with `macos_version()` 12.2. | The native backend is missing; the OpenCV source is chosen [U]. |
| T-UNX-57 | — | `PyObjCLayer` construction order with a stand-in of the frameworks. | `kCMIOHardwarePropertyRunLoop` is set to NULL before any other CoreMediaIO call (M-7). |
| T-UNX-58 | T-UNX-20 | Permission `authorized`, but no sample ever arrives. | `first-frame-timeout`; `tcc` `granted`; the diagnostics show `t_first_frame_ms` null. |

Parity [U]: Linux has 30 fake tests and macOS 28. T-UNX-01 to T-UNX-03 (the binary layout) and
T-UNX-20 (`EINTR`) have no macOS counterpart: macOS has no ioctl layer. T-UNX-33, T-UNX-36, T-UNX-39,
T-UNX-55 and T-UNX-57 have no Linux counterpart: they test facts of macOS only.

### 6.5 Shared and Windows tests (step 7s)

| ID | Kind | What it does | Pass criterion |
|---|---|---|---|
| T-UNX-61 | fake | `select_capture_source()` for each `sys.platform` with the settings unset, valid and wrong; with a local record row `pass`, `partial`, `fail`, `skipped`, with another OS key, with another ABI, from a quick run; with an evidence row `verified` and `known-bad`; inside certify. | The order of 4.9; a wrong value names the allowed values; another OS key, another ABI or a quick run does not apply; certify always gets the native source; Windows unchanged. |
| T-UNX-62 | fake | Write and read `camera_checks.json` after a fake full run of two models and a quick run. | One row per model with the fields of 4.9, `abi` included; no row for the quick run; a newer run replaces the row of its key; a broken file reads as empty with a log line. |
| T-UNX-63 | fake | Read `pyproject.toml` and `uv.lock`. | The PyObjC pins of 7.2 with `==` and the marker `sys_platform == "darwin"` [U]; no new Linux dependency; locked at the same versions. |
| T-UNX-64 | fake | `CaptureFailure` across a process boundary; each code of 4.6.3; `_mark_ended`. | `code` survives pickling; the failure object has `code`; a process that ended gives `process-ended`. |
| T-UNX-65 | fake | `exposure_units` for each v from -14 to -2 with ranges (3, 2047, 1) and (1, 5000, 1); the seconds map. | The table of A-18; the clamp; the read-back; `floor(x + 0.5)`; seconds `2^v` exactly. |
| T-UNX-66 | fake | `no-native-jpeg` from a native open with the default selection, with the setting, and inside certify. | Default: the camera opens with OpenCV, `backend: opencv`, a log line [U]; setting: `failed` with `no-native-jpeg`; certify: `failed`, no OpenCV open. |
| T-UNX-67 | fake | An evidence row `known-bad` for a camera model and the native backend. | Default: that camera opens with OpenCV; the others native [U]. |
| T-UNX-68 | fake | "Apply again" for a camera whose old process is still alive. | `previous-process-alive`, stage `open`; no open of the camera. |
| T-UNX-69 | fake | The exposure rules of 4.5 with the fake source: a new camera; a camera in Auto at open; a rate change; an apply with `exposure_search: true`; a camera in Manual at open and at a rate change; a record start during `adjusting`; a search whose best value is too slow at 30 fps; a camera slow at every value; a search request during a take. | New camera in Auto; the apply response comes when the cameras stream, before the search ends, and the search result arrives in the status; the search runs at open, at the rate change and on request, never in Manual; state `adjusting` with preview, record start 409; the guard steps darker until the rate check passes; a camera slow at every value gets its old exposure back, `too_slow`, reason exactly "Camera is slow. Try adding more light"; the request during a take gets 409 and nothing changes; the config keeps `AUTO` with `exposure_found`. |
| T-UNX-70 | fake | `CameraStatus.serialize()` with a fake source and with the OpenCV fake. | `diagnostics` is present each second; the OpenCV status has `backend` `opencv` and null for every other source key. |
| T-UNX-71 | fake | MJPG passthrough with the fake source; the OpenCV fake (re-encode); a BGR ring on. | `encoded_by_skellycam` 0 and the frame count; `decoded_by_skellycam` counts the decode stage. |
| T-UNX-72 | fake | D-11: a camera reaches `ready`, then records; one camera sends no DHT. | 30 hashes after `ready` with their `source_frame_number`, then a new set at the record start; each hash equals the SHA-256 of the ring slot and of the MKV block of that frame; no warm-up frame is hashed; `dht_inserted` counts the DHT camera. |
| T-UNX-73 | fake | The OpenCV source on Linux with a native detection result; on macOS with a device order. | Linux: `cv2.VideoCapture('/dev/videoN', CAP_V4L2)` of the detected node; macOS: the index of the matching `uniqueID`. |
| T-UNX-74 | fake | Detection with an evidence file and a local record. | `evidence`, `checked`, `id_source`, `has_serial`, `backend`, `usb_link` in `CameraDeviceInfo`; `system_evidence` in the status. |
| T-UNX-75 | fake | Two fake cameras; one camera process stops giving frames and reports nothing (its source holds a lock in a stand-in for a GIL hold) [U]. | The main process removes it from the gate and ends it 2.0 to 2.5 s after its last frame; `stalled`; the other camera has no gap longer than 2.5 s. |
| T-UNX-76 | windows | `MediaFoundationSource.diagnostics()` with the stand-in interfaces of the Windows tests. | Every key of 4.6.2; `id_source` `mf-link`; `native_domain` `hresult`; `clock` `unknown`; `t_*_ms` filled. |
| T-UNX-77 | windows | Map the HRESULTs of [W 6.7] and `0x800718CF` to codes. | In-use codes give `camera-in-use`; removal codes give `device-removed`; `0x800718CF` gives `usb-bandwidth`; `0x80004005` gives `open-failed` at open and `stream-error` in streaming. |
| T-UNX-78 | windows | The restore of the Media Foundation source at the close, with stand-in control interfaces. | Each changed control is set back to its "before" value and flags before the flush, and read back; on by default. |
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
| T-UNX-87 | macos-runner | The CoreMediaIO constants of 4.4.6 and M-7, `CMIOObjectGetPropertyData`, `CMSyncConvertTime`, the IOKit `ctypes` calls. | Each name exists; setting `kCMIOHardwarePropertyRunLoop` to NULL returns no error; IOKit returns a speed or `unknown`. |
| T-UNX-88 | build | On the macOS build jobs: the frozen server runs the native detection only (no camera). | The layer loads; detection returns a list; no missing module. |

The IDs T-UNX-59 and T-UNX-60 are not used.

### 6.7 Certify checks: the hardware tests

The hardware validation is a certify run [U]. This table gives the parity with the Windows hardware
tests; it does not repeat the certify spec.

| Assumptions | Certify check [cert 4, 5, 8, 10.2] | Windows test it mirrors |
|---|---|---|
| A-1, A-4, M-1, M-4 | `detect`, `<label>:detect`, `<label>:modes` | T-CAP-51, T-CAP-79 |
| A-2, M-2 | `<label>:identity` | T-CAP-24, T-CAP-106 |
| A-3, M-3 | `system:virtual-cameras` | T-CAP-105 |
| A-5, A-6, A-11, A-12, M-6, M-7 | `<label>:opens`, `<label>:rate`, `<label>:modes` | T-CAP-52 |
| A-7, A-8, M-5 | `<label>:native-jpeg` | T-CAP-52 |
| A-9, M-9 | `<label>:clock` | T-CAP-59 |
| A-10, M-10 | `<label>:sequence` | none (new) |
| A-13, M-8 | `self:hang-100ms` | T-CAP-82 |
| A-14, M-11, M-12 | `<label>:in-use`, `probe:camera-holders` | T-CAP-56 |
| A-15, A-22, M-13 | `group:open`, `group:contention` | none (new) |
| A-16, M-14 | `system:camera-access` | none (new) |
| A-17, A-18, M-15 | `<label>:controls`, `<label>:auto-off`, `<label>:settings-stick`, `<label>:exposure:<base>`, `<label>:auto-exposure`, `<label>:control:*`, `probe:control-ep0` [U] | T-CAP-57, T-CAP-78 |
| A-19, A-20 | `<label>:settings-stick` | T-CAP-57 |
| A-21, M-17 | `<label>:cycles`, `<label>:timings`, `probe:kernel` | T-CAP-54 |
| A-22, M-18 | `system:usb` | none (new) |
| A-23, M-19, M-20 | `detect` (`backend-missing`) | T-CAP-46 |
| M-16 | `system:video-effects` | none |
| rates, the generic camera | `<label>:rate`, `<label>:rate:<mode>` | T-CAP-53, T-CAP-54 |
| the group take | `group:take-30` | T-CAP-60 |

### 6.8 Counts

| Kind | Linux | macOS | Each OS or Windows |
|---|---|---|---|
| fake | 30 (T-UNX-01 to 30) | 28 (T-UNX-31 to 58) | 16 shared (61 to 75, 79), on Windows, Linux and macOS |
| windows | — | — | 3 (76 to 78) |
| runner, vivid | 4 (80 to 83) | 4 (84 to 87) | — |
| build | — | 1 (88) | — |
| certify | 6.7 | 6.7 | — |

## 7. Dependencies, risks

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

IOKit (M-18) uses `ctypes` [R macctl §3 R5]. Whether PyInstaller 6.22.3 collects PyObjC is [NV];
T-UNX-88 finds a gap.

### 7.3 Risks, ranked

1. **No native JPEG through AVFoundation (M-5).** Plan: `no-native-jpeg`, and the camera opens with
   OpenCV outside certify [U]; after step 3b the source could encode the decoded samples; the plan of
   2026-11-17 already says "If it does not, macOS stays on decode then re-encode" [R plan §3].
2. **No manual exposure on macOS (M-15).** Plan: no exposure control and the warning
   `no-manual-exposure` [U]; certify shows the camera item `partial`; the endpoint-0 probe shows whether that route
   works [U].
3. **Timestamps not on a usable clock (A-9, M-9).** The 200 ms rule gives `NO_SAMPLE_NS`, and the
   recorder keeps `arrival_ns` [W D28]. Low on Linux, medium on macOS.
4. **PyObjC holds the GIL (M-8).** Plan: the stall watch of 4.10 [U]; T-UNX-84 shows it in CI.
5. **No real system before certify.** Each struct, ioctl number and PyObjC call comes from documents
   and research code. Plan: the reference-value tests; the first certify run gives every diagnostic;
   OpenCV stays until a model is checked [U].
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
9. The exposure map `floor(2^v × 10000 + 0.5)`, clamped; read-back in native units; CoreMediaIO only
   with an absolute value in seconds.
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
23. The settings `SKELLYCAM_LINUX_CAPTURE` and `SKELLYCAM_MACOS_CAPTURE`; the file, format and
    replacement rule of `camera_checks.json`.
24. `previous-process-alive`.
25. Detection in a short-lived child on Linux and macOS.
26. The OpenCV source on macOS finds its index by `uniqueID`.
27. Auto opens at -7 for the start-up check; `exposure_found`; `exposure_search: true`; `RECOMMEND`
    reads as Auto; `declared_fps` and `measured_fps` as numbers in the failure object.
28. The virtual clock seam of the sources.
29. No new CI job; the markers; the optional vivid step; T-UNX-88.
30. The pass thresholds of section 6.

## 9. Questions for the user

Each question waits for the user. Each is worded so that "yes" accepts the recommendation, and the
spec is written to that recommendation. The user accepted the seven other recommendations of draft 2
on 2026-11-20 ([ADR-22EJ](../decisions/entries/22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md), item 14).

1. The folders `v4l2/` and `avfoundation/` run only on their OS, but their modules import only the
   standard library at module level, so that their fake tests run on Windows, Linux and macOS. Yes?
2. The diagnostic keys of 4.6.2, with `frame_log` of 64 rows and the 30 frame hashes, go into the
   camera status each second. Yes?
3. CI adds no new job: the fake tests join the three capture jobs, the Linux job tries
   `modprobe vivid` without failing, and the macOS build jobs run T-UNX-88. Yes?
4. The x32 ABI of Linux keeps the OpenCV source, and 32-bit arm and i386 use the computed layout of
   A-23. Yes?
