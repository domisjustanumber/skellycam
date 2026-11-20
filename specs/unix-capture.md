# Linux and macOS native capture specification (V4L2 and AVFoundation)

Status: draft 1 for the user, 2026-11-20. Spec and test list only: no product code and no test code
exist for it. The decisions of the user that bind it are in
[ADR-22EJ](../decisions/entries/22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md).
The choices of the agent are in
[ADR-AT04](../decisions/entries/AT04-choices-of-the-linux-and-macos-capture-spec.md). Section 9
holds the questions for the user.

The user moved this work up on 2026-11-20: "certify runs to validate assumptions about linux and mac
code. Ideally as much real code is implemented as possible now so a single test run provides as much
information as possible and can be used there and then if the tests pass." [U] Thus the native
sources are written now, without a Linux or macOS machine. Each fact that the code relies on is an
assumption of section 2. Each assumption has a run-time check, a diagnostic field and a certify check.
A certify run on a real system then confirms or refutes each one. When a system passes, native capture
can be used there at once (section 4.9).

## 0. How to read this spec

Marks:

- **[U]**: a decision of the user ([ADR-22EJ](../decisions/entries/22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md)).
- **[A]**: a choice of the agent ([ADR-AT04](../decisions/entries/AT04-choices-of-the-linux-and-macos-capture-spec.md)). Section 8 lists each one.
- **[W x.y]**: section x.y of [`windows-capture.md`](windows-capture.md). **[W Dn]**, **[W Un]**,
  **[W Wn]**: a decision of that spec (its section 20). **[rec x.y]**: [`recorder.md`](recorder.md).
- **[cert x.y]**: section x.y of `specs/certify.md`, draft 2 of 2026-11-20, on branch
  `dom/certify-spec` (not committed when this spec was written). **[X-n]**: unknown n of its section
  10.2. Check names such as `<label>:native-jpeg` are the certify check names of its section 3.1.
- **[R file]**: a research file on branch `dom/research` (commit 56d2b907d). These files are not on
  this branch. "xplat" is `research/usb_cameras/docs/xplat_capture_plan.md`; "stack" is
  `research/usb_cameras/docs/capture_stack_options_plan.md`; "macctl" is
  `research/usb_cameras/docs/macos_uvc_controls_review.md`; "linuxlib" is
  `research/usb_cameras/suite/linux/linuxlib/v4l2.py`; "mac_avf" is
  `research/usb_cameras/suite/macos/helpers/mac_avf.py`. Each research file is written on Windows and
  never ran on Linux or macOS hardware [R xplat §2.4, stack §4.2, §4.3].
- **[K n]**: a primary source of section 0.1, read on the date given there.
- **[NV]**: not verified. No primary source or measurement proves it. A certify check must observe it.

This spec uses British spelling. Code names are from branch `dom/recorder-connection` at commit
72b939fbb, read on 2026-11-20. "This step" means the work that this spec specifies.

### 0.1 Primary sources

Each source was read on 2026-11-20.

| ID | Source | What this spec takes from it |
|---|---|---|
| K1 | https://docs.kernel.org/userspace-api/media/v4l/buffer.html | `V4L2_BUF_FLAG_ERROR` (0x40); timestamp types (mask 0xE000, MONOTONIC 0x2000 is `CLOCK_MONOTONIC`); sources (mask 0x70000, EOF 0, SOE 0x10000); `sequence` counts dropped frames; `bytesused`. |
| K2 | https://docs.kernel.org/userspace-api/media/v4l/ext-ctrls-camera.html | The order of the `V4L2_CID_EXPOSURE_AUTO` menu; `V4L2_CID_EXPOSURE_ABSOLUTE` in 100 µs units; `V4L2_CID_EXPOSURE_AUTO_PRIORITY` acts only in the auto and aperture-priority modes; focus controls. |
| K3 | https://docs.kernel.org/userspace-api/media/v4l/vidioc-qbuf.html | `VIDIOC_DQBUF` blocks unless `O_NONBLOCK`; then `EAGAIN`; `EIO`. |
| K4 | https://docs.kernel.org/userspace-api/media/v4l/vidioc-streamon.html | Error codes of `STREAMON` (no `ENOSPC` listed); `STREAMOFF` removes all buffers. |
| K5 | https://docs.kernel.org/userspace-api/media/v4l/vidioc-g-fmt.html | `S_FMT` adjusts the values and does not return an error for them; `EBUSY` while another queue streams or holds buffers. |
| K6 | https://docs.kernel.org/userspace-api/media/v4l/vidioc-reqbufs.html | The granted count can differ from the requested count; `count = 0` frees the buffers. |
| K7 | https://docs.kernel.org/userspace-api/media/v4l/vidioc-g-parm.html | `timeperframe`: the driver returns the actual period; `V4L2_CAP_TIMEPERFRAME`. |
| K8 | https://raw.githubusercontent.com/torvalds/linux/master/drivers/media/usb/uvc/uvc_video.c | No fast enough alternate setting gives `-EIO`; a failure of `usb_set_interface` is returned as is; timestamp from `ktime_get()` (monotonic clock parameter) at the frame start; `sequence` increments on each frame start "so that discontinuous sequence numbers always indicate lost frames"; `UVC_STREAM_ERR` marks the buffer bad. |
| K9 | https://raw.githubusercontent.com/torvalds/linux/master/drivers/media/usb/uvc/uvc_queue.c | `timestamp_flags = MONOTONIC | TSTAMP_SRC_SOE` (fixed); a bad buffer is requeued unless `nodrop`; else returned with the error state. |
| K10 | https://raw.githubusercontent.com/torvalds/linux/master/drivers/media/usb/uvc/uvc_driver.c | `clock` parameter default `CLOCK_MONOTONIC`; `nodrop` default 1; `hwtimestamps` default 0; the metadata node has `V4L2_CAP_META_CAPTURE | V4L2_CAP_STREAMING` only; the card name comes from the USB product string. |
| K11 | https://raw.githubusercontent.com/python/cpython/3.13/Modules/fcntlmodule.c | `fcntl.ioctl` releases the GIL for an integer argument and for a mutable buffer of 1024 bytes or less; it does not retry `EINTR`. |
| K12 | https://docs.python.org/3.13/library/time.html | `perf_counter` uses the clock of `monotonic` (3.13); macOS: `mach_absolute_time()`; else `clock_gettime(CLOCK_MONOTONIC)` (Linux by the order of the list). |
| K13 | https://developer.apple.com/tutorials/data/documentation/coremedia/cmclockgethosttimeclock().json | "In macOS, the host time clock uses `mach_absolute_time`". |
| K14 | https://developer.apple.com/tutorials/data/documentation/avfoundation/avcapturesession/synchronizationclock.json | All sample buffer timestamps are on `synchronizationClock`; macOS 12.3 and later. |
| K15 | https://developer.apple.com/tutorials/data/documentation/avfoundation/avcapturevideodataoutput/videosettings.json | "To receive samples in their device-native format, set this value to an empty dictionary"; `nil` gives a default uncompressed format. |
| K16 | https://developer.apple.com/tutorials/data/documentation/avfoundation/avcapturevideodataoutput/availablevideocodectypes.json | `availableVideoCodecTypes`, set through `AVVideoCodecKey`; macOS 10.7 and later. |
| K17 | https://developer.apple.com/tutorials/data/documentation/avfoundation/avcapturevideodataoutput.md | "This object supports compressed video data output for macOS only." |
| K18 | https://developer.apple.com/tutorials/data/documentation/avfoundation/requesting-authorization-to-capture-and-save-media.json | `NSCameraUsageDescription` and the entitlement `com.apple.security.device.camera`; without them "the system terminates your app"; `authorizationStatus(for:)`. |
| K19 | https://chromium.googlesource.com/chromium/src/+/main/media/capture/video/apple/video_capture_device_avfoundation.mm | Chromium asks for `kCMVideoCodecType_JPEG_OpenDML` through `kCVPixelBufferPixelFormatTypeKey`, maps it to MJPEG, extracts the bytes of the sample, converts the PTS with `CMClockConvertHostTimeToSystemUnits` to mach time, and has a Logitech 4K Pro exception that falls back to a decoded format. |
| K20 | https://developer.apple.com/forums/thread/791278 | One unanswered report: a UVC MJPEG mode of 1000x6000 does not stream on macOS. No reply from Apple. |
| K21 | https://pypi.org/pypi/pyobjc-framework-AVFoundation/json | 13.0 is the latest (2026-10-30); it requires pyobjc-core, CoreMedia, CoreAudio, Cocoa and Quartz. |
| K22 | https://pypi.org/pypi/pyobjc-core/13.0/json | cp313 universal2 wheel, 6,734,122 bytes. |
| K23 | https://pypi.org/pypi/pyobjc-framework-CoreMediaIO/13.0/json, https://pypi.org/pypi/pyobjc-framework-Quartz/13.0/json, https://pypi.org/pypi/pyobjc-framework-Cocoa/13.0/json | cp313 universal2 wheels: CoreMediaIO 17,217 bytes; Quartz 215,890 bytes; Cocoa 391,670 bytes. |
| K24 | https://pypi.org/pypi/linuxpy/json | linuxpy 0.25.0 (2026-08-20), GPL-3.0-or-later, Python 3.10 and later. |
| K25 | https://github.com/orgs/community/discussions/63910 | On a hosted ubuntu-22.04 runner, `linux-modules-extra-$(uname -r)` for the Azure kernel had no installation candidate. Nothing found for ubuntu-24.04. |
| K26 | https://lkml.iu.edu/hypermail/linux/kernel/2503.3/06002.html | The uvcvideo series "Implement Granular Power Saving" (v6, 2025-03). Which kernel release holds it is not shown. |

## 1. Purpose, scope, method

### 1.1 Purpose

This step replaces OpenCV capture on Linux with V4L2 through the standard library, and on macOS with
AVFoundation through PyObjC [U, A]. The camera JPEG goes byte-true to the recorder and the JPEG ring;
the shared loop inserts a DHT when the camera sends none [U, rec 4.1]. The sources plug into the
shared loop of [W 5] through the capture interface of [W 4]. Nothing in the shared loop changes for
them except the items of section 4.2.

The user stated the aim of the certify runs: "the aim of this is to use certify to test out the native
capture features and see if they work. OpenCV is already fairly proven to work, so no need to test
here." [U] Thus the hardware tests of this spec are certify checks of the native sources (section 6.5).

### 1.2 Scope

| Step | Delivers |
|---|---|
| 7s (shared) | The failure code beside the failure text; `diagnostics()` on each source; the generic bounded call; the exposure unit map; the source selection for Linux and macOS; the native detection dispatch; the USB link label (section 4). |
| 7a (Linux) | `skellycam/core/camera/capture/v4l2/`: detection, `camera_id`, `supported_modes`, `V4L2Source` (MJPG, mmap streaming), manual exposure, gain, focus, white balance and power line read (section 4.3). |
| 7b (macOS) | `skellycam/core/camera/capture/avfoundation/`: detection, `camera_id`, `supported_modes`, `AVFoundationSource` (MJPG block buffers if M-5 holds), exposure through CoreMediaIO controls or the AVFoundation lock, permission state (section 4.4). |

Each step has its own fake-layer tests (section 6). Each step is complete when its tests pass in CI.
Its hardware validation is a certify run (section 6.5) [U].

### 1.3 Non-goals

- A compiled extension of our own, Rust, libusb or libuvc [U, R xplat §1]. A driver change, a kernel
  module parameter change or a udev rule [R xplat §1].
- UVC PTS/SCR timestamps and the uvcvideo metadata node. The rule "tier 0 only, no PTS testing" of
  2026-11-09 stays [R NATIVE_JPEG_CAPTURE_PLAN §2].
- Uncompressed modes (YUY2, NV12) on Linux. They follow step 3b of Windows [W 13]. The macOS
  fallback of M-5 needs the encoder of 3b (section 7.3, risk 1).
- UVC requests on endpoint 0 on macOS in the product (question 3). Certify can run them as a probe in
  its risky phase [cert 10.2 X-6].
- Hot-unplug tests [U]. The source still maps a removal to `dead` (sections 4.3.8, 4.4.9).
- Modes below 30 fps [U, W U11]. H.264 modes [W D4].
- The removal of the lockstep gate (phase 8).

### 1.4 Method

For each fact that the code needs, this spec gives:

1. The **assumption**: the fact, its source and its confidence (section 2).
2. The **run-time check** in the source: the code checks the fact on each open, where it can.
3. The **diagnostic**: a fixed key of `diagnostics()` that records what the source saw (section 4.6).
4. The **certify check** that reads the diagnostic on a real system [cert 10.2].
5. The **fallback** when the fact is false: a failure with a fixed code, a reduced feature, or the
   OpenCV source (section 4.9).

A false assumption must give a clear failure code and a diagnostic, never a wrong frame, a wrong
timestamp or a silent hang [A].

## 2. Assumptions

Each item has: the statement; the source; what breaks if it is false; the run-time check; the
diagnostic fields (section 4.6); the certify check; the confidence (high: a primary source; medium: a
primary source for part, or strong field evidence; low: little evidence).

### 2.1 Linux (V4L2, uvcvideo)

**A-1. The video nodes.** A capture node is a `/dev/videoN` whose `VIDIOC_QUERYCAP` has
`V4L2_CAP_DEVICE_CAPS` in `capabilities` and `V4L2_CAP_VIDEO_CAPTURE` and `V4L2_CAP_STREAMING` in
`device_caps`. uvcvideo makes a second node for each stream with only `V4L2_CAP_META_CAPTURE |
V4L2_CAP_STREAMING`; detection skips it.
- Source: [K10] (metadata node caps). Confidence: high.
- If false: a camera shows twice, or a metadata node fails at `S_FMT`.
- Run-time check: detection reads `device_caps` of each node.
- Diagnostics: `nodes_seen`, `nodes_skipped_meta`.
- Certify: `detect` (`cameras` against the USB devices that sysfs shows) [X-13].

**A-2. Identity from sysfs.** `/sys/class/video4linux/videoN/device` is the USB interface of the
camera; its parent is the USB device with `idVendor`, `idProduct`, `busnum`, `devpath` (the port
chain, for example `2.3`), `speed` and, if the camera has one, `serial`. The `camera_id` input is
`v4l2:serial:<vid>:<pid>:<serial>:<interface>` when the serial is present and unique among the
detected cameras, else `v4l2:port:<busnum>-<devpath>:<interface>` [A]. The `/dev/v4l/by-id` names
collide for two identical cameras with no serial; this spec does not use them [R xplat §2.6 G-ID].
- Source: the sysfs layout [R naming/README.md, linux_identity.py, unit-tested on a fake tree only]
  [NV on hardware]. Confidence: medium.
- If false: no USB IDs (label `nousb-nousb`), or two cameras get one `camera_id` (refused [W D13]).
- Run-time check: detection refuses two equal `camera_id` values, as on Windows [W 7.1]. A node with
  no USB parent is virtual or a platform camera (A-3).
- Diagnostics: `identity_kind` (`serial`, `usb-path`, `none`). No serial, path or port is in the
  diagnostics [cert 9.4].
- Certify: `<label>:detect` [X-13].

**A-3. Virtual cameras.** A v4l2loopback node has the driver name `v4l2 loopback` in `QUERYCAP` and no
USB parent in sysfs. Detection gives it `virtual: true` [W W5]. A name that holds "virtual" is virtual
too [W 7.1].
- Source: v4l2loopback behaviour [NV]. Confidence: medium.
- If false: a virtual camera is selectable.
- Run-time check: the driver name and the sysfs parent, at detection.
- Diagnostics: none per camera; `virtual` in the detection result.
- Certify: `system:virtual-cameras`.

**A-4. Mode list.** `VIDIOC_ENUM_FMT`, `VIDIOC_ENUM_FRAMESIZES` and `VIDIOC_ENUM_FRAMEINTERVALS` give
the MJPG sizes and their frame intervals. For a UVC frame-based descriptor the types are discrete. A
discrete interval `n/d` seconds gives `fps_num = d`, `fps_den = n` [A]. A stepwise or continuous
interval range gives only the rates 30000/1001, 30/1 and 60/1 that fall inside it [A].
- Source: [R linuxlib, xplat §2.6] [NV on our cameras]. Confidence: high.
- If false: `supported_modes` is empty or wrong; `modes_read` is false.
- Run-time check: the mode choice of [W 7.5] uses the list; the open reads back the mode (A-5, A-6).
- Diagnostics: `modes_listed`, `mjpg_sizes`, `interval_types` (`discrete`, `stepwise`, `mixed`).
- Certify: `<label>:detect` (`mjpg_sizes`, `has_720p30`, `max_fps`).

**A-5. `S_FMT` can grant another size.** The driver adjusts a request and returns no error [K5]. The
source reads back `width`, `height` and `pixelformat` after `S_FMT`. A difference is a failure, stage
`set mode`, code `no-mode`.
- Source: [K5]. Confidence: high.
- If false: nothing breaks; the check costs nothing.
- Diagnostics: `req_width`, `req_height`, `req_format`, `got_width`, `got_height`, `got_format` (D-1).
- Certify: `<label>:opens`, `<label>:native-jpeg` (`sof_matches_mode`) [X-1].

**A-6. `S_PARM` sets the rate.** With `V4L2_CAP_TIMEPERFRAME`, `VIDIOC_S_PARM` sets `timeperframe`,
and the driver returns the actual period [K7]. The source calls `S_FMT`, then `S_PARM`, then reads
back `G_PARM`. A rate that is not equal to the chosen mode rate (relative tolerance 0.0001 [W D17])
is a failure, stage `set mode`, code `no-mode`.
- Source: [K7]. Confidence: high. The order `S_FMT` then `S_PARM` is the order of the research layer
  [R linuxlib] [NV].
- If false: the mode rate is wrong, and the rate check fails each camera.
- Diagnostics: `req_fps_num`, `req_fps_den`, `got_fps_num`, `got_fps_den` (D-1).
- Certify: `<label>:rate`.

**A-7. MJPG buffers are the camera's JPEG.** uvcvideo copies the payload of each frame into the mmap
buffer and sets `bytesused`. It does not decode or re-encode it. The source copies
`bytesused` bytes into one `bytes` object and requeues the buffer at once.
- Source: [K8] (the driver assembles payloads); [R xplat §2.6 G-MJPEG: "Raw V4L2 mmap is the
  reference"]. Confidence: high.
- If false: frames are not the camera's bytes, or they are damaged.
- Run-time check: the capture check of the shared loop (`check_jpeg`) on each frame [W 5.1 step 5].
- Diagnostics: `delivered_kind` (`jpeg`), `sha256_00` to `sha256_29` (D-11), `frames`,
  `zero_bytes`.
- Certify: `<label>:native-jpeg` (SOI and EOI, strict decode, distinct quantization tables) [X-1].

**A-8. Damaged frames carry `V4L2_BUF_FLAG_ERROR`.** With `nodrop=1` (the default in the kernel of
[K10]; the research gives kernel 6.14 for the change [R xplat §2.6]), a frame with the UVC error bit
or a lost packet arrives with the error flag [K1, K8, K9]. On an older kernel the driver drops it; the
`sequence` then has a gap (A-10). The source sets `driver_error = True` for a flagged buffer and for
`bytesused = 0`. The shared loop then flags the slot `CAPTURE_ERROR` [W 5.1].
- Confidence: high.
- If false: a damaged JPEG reaches the recorder unflagged. The strict decode of certify finds it.
- Diagnostics: `error_flags` (count), `zero_bytes` (count), `nodrop_param` (from
  `/sys/module/uvcvideo/parameters/nodrop`, or null when not readable).
- Certify: `<label>:native-jpeg` (`V4L2_BUF_FLAG_ERROR` count) [X-1].

**A-9. The buffer time is on the clock of `perf_counter_ns`.** uvcvideo stamps each buffer with
`ktime_get()` when the clock parameter is `CLOCK_MONOTONIC`, the default, at the first payload of the
frame [K8, K10]. Its flags always say `TIMESTAMP_MONOTONIC | TSTAMP_SRC_SOE` [K9]. "SOE" is a label
only: the time is the arrival of the first USB payload of the frame, not the start of exposure [K8].
CPython 3.13 `perf_counter_ns` on Linux reads `clock_gettime(CLOCK_MONOTONIC)` [K12]. Thus
`sample_ns = tv_sec × 10^9 + tv_usec × 1000` is on the base of `arrival_ns` with no offset.
- Confidence: high for the base; [NV] for the grain (URB completions, up to about 4 ms
  [R xplat §2.6 G-TS]).
- If false: a root user set the clock parameter to realtime. The flags still say monotonic [K9], so
  the flags cannot show it.
- Run-time check: the rule of [W 4.2]: the source writes `NO_SAMPLE_NS` for the rest of the open when
  a sample time is later than its arrival time or more than 200 ms earlier. A realtime stamp is
  decades away from the monotonic clock, so the rule catches it. The flags must also have the
  monotonic type; else `NO_SAMPLE_NS`.
- Diagnostics: `clock` (`monotonic`, `unknown`, `copy`), `tstamp_src` (`soe`, `eof`), `ts_conversion`
  (`timeval-to-ns`), `sample_time_kept`, `arrival_minus_sample_p50_us`, `arrival_minus_sample_p95_us`,
  `raw_ts_step_min_us`, `clock_param` (from sysfs, or null) (D-2).
- Certify: `<label>:timestamps` (`clock`, `tstamp_src`, `grain_ms`, `jitter_p95_ms`) [X-3].

**A-10. `sequence` shows lost frames.** uvcvideo increments `sequence` at each frame start, also for
a frame that it drops [K8, K1]. The source compares the `sequence` of each dequeued buffer with the
last one. A gap sets `discontinuity = True` on that frame [W D34]. `source_frame_number` stays the
count of dequeued buffers since the open [W D27].
- Confidence: high.
- If false: a lost frame does not set `DISCONTINUITY`.
- Diagnostics: `sequence_gaps` (count of gaps), `sequence_lost` (sum of the gap sizes), and the
  `sequence` column of `frame_log` (D-3).
- Certify: `<label>:timestamps` (`sequence_gaps`) [X-3].

**A-11. Buffers and the newest frame.** `VIDIOC_REQBUFS` with `count = 4` [A]. The driver can grant
another count [K6]; the source accepts 2 or more. A capture thread of the source dequeues each
buffer, copies it, requeues it and puts the frame into the waiting place of [W 4.3]. Thus the source
is a push source, with `replaced_count` as on Windows [W D26].
- Confidence: high.
- If false (fewer than 2 granted): failure, stage `open`, code `open-failed`.
- Diagnostics: `buffers_requested`, `buffers_granted`.
- Certify: `<label>:opens`.

**A-12. No call waits for a frame without a limit.** The source opens the node with `O_RDWR |
O_NONBLOCK | O_CLOEXEC`. The capture thread waits in `select.poll` with a timeout of 100 ms [A], then
calls `VIDIOC_DQBUF`. `EAGAIN` means no buffer [K3].
- Confidence: high.
- Diagnostics: `poll_timeouts` (count).
- Certify: `<label>:opens`, `<label>:cycles`.

**A-13. Blocking ioctls, the GIL and a stuck kernel wait.** `S_FMT`, `S_PARM`, `STREAMON`, `STREAMOFF`,
the control ioctls and `close()` send USB control requests or stop USB transfers. They can block in
the driver [NV for each call]. Each such call is a bounded call with the limit of 5 s [W 6.6].
`fcntl.ioctl` releases the GIL during the call when the argument is 1024 bytes or less [K11]. Each
V4L2 struct of this step is 232 bytes or less [R linuxlib `REF_SIZES`]. Thus a blocked ioctl does not
stop the other threads of the camera process. `fcntl.ioctl` does not retry `EINTR` [K11]; the source
retries an `InterruptedError` at once.
- A thread in an uninterruptible kernel wait cannot be killed until the wait ends. The camera
  process reports the hang, then calls `os._exit` [W 6.6]. The process can stay alive until the
  kernel call returns. The USB request timeouts of uvcvideo bound that wait [NV for the value].
- The main process does not wait for the exit. A camera process that reported a failure is that
  camera's failure at once [W 6.6]. "Apply again" for that camera while the old process lives gets
  the failure code `previous-process-alive`, stage `open`, with no open of the node [A]. The wait of
  ADR-6EKB item 84 (10 s, then a kill) stays.
- Confidence: high for the GIL; medium for the stuck wait.
- Diagnostics: `t_<step>_ms` of each open step (D-6); on a hang `fail_call`, `fail_code` `hung`.
- Certify: `self:hang-100ms` proves the software rule; a real driver hang is not testable [cert 7].

**A-14. "In use" is `EBUSY` at `REQBUFS` or `S_FMT`.** V4L2 allows more than one open of a node, so
`open()` succeeds while another process streams. The refusal comes at `S_FMT` or `REQBUFS` with
`EBUSY` [K5, K6]. The research found that `S_FMT` sends a PROBE request to the camera before it
returns `EBUSY` [R xplat §2.6 L-DESK] [NV]. Thus the source calls `VIDIOC_REQBUFS` with `count = 0`
first [A]: that call frees buffers of this file only and does not send a USB request [K6] [NV that
it returns `EBUSY` for a queue of another file]. `EBUSY` at any open step gives the code
`camera-in-use` and the reason "in use by another program" [W D13].
- Confidence: medium.
- If false: a held camera gets another code, or a PROBE disturbs the stream of the other program.
- Diagnostics: `busy_call` (the call that returned `EBUSY`, or null).
- Certify: `<label>:in-use` (`outcome`, `stage`) and `system:camera-holders` [X-9].

**A-15. A USB bandwidth refusal fails `STREAMON`.** uvcvideo returns `EIO` when no alternate setting
is fast enough [K8]. A refusal of the host controller comes back from `usb_set_interface` as is [K8];
the research names `ENOSPC`, and also `ENOMEM`, `EPIPE` and `ETIMEDOUT` [R xplat §2.6 G-BW] [NV for
each]. The source maps `EIO`, `ENOSPC` and `ENOMEM` at `STREAMON` to the code `usb-bandwidth` with the
reason "USB bandwidth refused, or a device error (errno <name>)" [A].
- Confidence: medium (`EIO` from the source; the others [NV]).
- If false: a refusal gets the code `open-failed`, and certify cannot tell bandwidth from a fault.
- Diagnostics: `fail_native` (the errno number), `fail_call` `VIDIOC_STREAMON`; `usb_alt` (A-22).
- Certify: `group:open` (`refusal_signal`, `errno`) [X-8].

**A-16. Access to the node.** A desktop seat gives the user an ACL on `/dev/videoN`; an SSH session
needs the `video` group [R xplat §2.6 L-DESK]. `open()` fails with `EACCES` without access. The
source gives the code `no-access`, stage `open`. Detection still lists the camera from sysfs, with
`modes_read: false` [A].
- Confidence: high for `EACCES`; medium for the seat ACL.
- Diagnostics: `access_path` (`seat-acl`, `video-group`, `root`, `none`) (D-8). `video-group` means
  that `os.getgroups()` holds the group id of `video`; `seat-acl` means access without that group.
- Certify: `system:camera-access` [X-10].

**A-17. The controls and their ids.** The source uses the control ids of `videodev2.h`, never the
names (names changed between kernels) [R linuxlib]: `V4L2_CID_EXPOSURE_AUTO` (menu),
`V4L2_CID_EXPOSURE_ABSOLUTE` (`exposure_time_absolute`), `V4L2_CID_GAIN`, `V4L2_CID_FOCUS_ABSOLUTE`,
`V4L2_CID_FOCUS_AUTO` (`focus_automatic_continuous`), `V4L2_CID_AUTO_WHITE_BALANCE`,
`V4L2_CID_WHITE_BALANCE_TEMPERATURE`, `V4L2_CID_POWER_LINE_FREQUENCY` and
`V4L2_CID_EXPOSURE_AUTO_PRIORITY`. The menu order is AUTO, MANUAL, SHUTTER_PRIORITY,
APERTURE_PRIORITY [K2], that is 0, 1, 2, 3 in `videodev2.h` [R linuxlib]. UVC cameras often offer
only MANUAL (1) and APERTURE_PRIORITY (3) [NV]. `VIDIOC_QUERY_EXT_CTRL` gives the range, the step,
the default and the flags; `VIDIOC_QUERYMENU` gives the menu items.
- Manual exposure: the source sets the menu to MANUAL (1), then the absolute value, in one
  `VIDIOC_S_EXT_CTRLS` call with the menu item first [A]. A set of the absolute value while the menu
  is in an auto mode returns `EACCES` [R xplat §2.6 G-CTRL] [NV]; the source never does it.
- `V4L2_CID_EXPOSURE_AUTO_PRIORITY` acts only in the auto and aperture-priority modes [K2]. The
  source reads it and never sets it [A].
- Power line frequency and white balance: read only, as on Windows [W D44, W 11.5].
- Confidence: high for the ids; medium for the menu items of our cameras.
- If false: `control-failed` with the errno; the camera keeps its earlier values [W U14].
- Diagnostics: the control fields of D-4 for each control (section 4.6).
- Certify: `<label>:settings-stick`, `<label>:controls` [X-5].

**A-18. The exposure unit map.** skellycam keeps the unit of today: a power of two in seconds
[W D35]. `exposure_time_absolute` is in units of 100 µs [K2]. The map is:
`native = clamp(floor(2^v × 10000 + 0.5), min, max)`, rounded to the step of the control from its
minimum; the read-back is `v = round(log2(native / 10000))` [A]. Examples:

| v (log2 s) | Exposure | Native (100 µs) | Error |
|---|---|---|---|
| -12 | 0.244 ms | 2 | -18 % (below a minimum of 3: then 3, +23 %) |
| -11 | 0.488 ms | 5 | +2.4 % |
| -10 | 0.977 ms | 10 | +2.4 % |
| -9 | 1.95 ms | 20 | +2.4 % |
| -8 | 3.91 ms | 39 | -0.2 % |
| -7 | 7.81 ms | 78 | -0.16 % |
| -6 | 15.6 ms | 156 | -0.16 % |
| -5 | 31.25 ms | 313 | +0.16 % |

The check of the coordinator holds: -7 gives 78. The read-back of each set compares the native
values (the value sent after the clamp, against the value read), not the log2 values [A]. The
status reports the log2 value (an int, as on Windows [W 8.4]); the diagnostics hold the native value.
- Source: [K2]; the minimum of 3 is the C922 value of the research [NV]. Confidence: high.
- If false: the exposure differs from the request. The settings check of certify sees the image.
- Diagnostics: `ctl_exposure_value`, `ctl_exposure_unit` (`100us`), `ctl_exposure_min`, `_max`,
  `_step`.
- Certify: `<label>:settings-stick` (`luma_ratio` of -8 against -7), `<label>:exposure:<base>` [X-5].

**A-19. A read-back can come from the cache.** uvcvideo can answer `G_EXT_CTRLS` from its cache [R
xplat §2.6 G-CTRL]. Thus a read-back proves that the driver took the value, not that the camera
uses it.
- Confidence: medium.
- Run-time check: none. The image effect check of certify closes the gap.
- Certify: `<label>:settings-stick` (`no-image-effect`) [X-5].

**A-20. Controls hold while the stream runs.** The source sets the controls after the first frame
[W D20] and keeps the node open and streaming. A camera can lose its controls after an autosuspend
when no file holds it [R xplat §2.6 (kernel 6.16)] [K26] [NV for the release that holds it]. This
spec never sets a control on a camera that does not stream, except the restore of section 4.7, which
runs before `STREAMOFF` [A].
- Confidence: medium.
- If false: controls revert after an idle period.
- Diagnostics: `ctl_<name>_before`, `ctl_<name>_value`.
- Certify: `<label>:settings-stick` (`setting-reverted`, `kept_after_reopen`) [X-5].

**A-21. Close and reopen.** `STREAMOFF`, `munmap` of each buffer and `close()` release the camera in
under 1 s, and a reopen at once works [NV]. The Kiyo Pro needs the USB `NO_LPM` quirk of kernel 7.0
and of the stable kernels 6.12.81, 6.18.34 and 6.19.12 [R xplat §2.6] [NV].
- Confidence: low.
- Diagnostics: `t_close_ms`, `kernel` (`major.minor`, from `os.uname().release`).
- Certify: `<label>:cycles`, `system:kernel` [X-7, X-14].

**A-22. The USB link and the alternate setting.** The sysfs `speed` of the USB device gives the link:
1.5 or 12 is `usb1`, 480 is `usb2`, 5000 or more is `usb3` [R naming/README.md] [NV]. After
`STREAMON`, `bAlternateSetting` of the streaming interface in sysfs gives the granted alternate
setting; it is world-readable [R xplat §2.6 G-BW] [NV].
- Confidence: medium.
- Diagnostics: `usb_link`, `usb_alt` (D-9).
- Certify: `system:usb`, `group:open` [X-19, X-8].

**A-23. Spawned processes and file handles.** Camera processes use `spawn` [U]. The node is opened
with `O_CLOEXEC`, so no child inherits it.
- Confidence: high.

### 2.2 macOS (AVFoundation, CoreMediaIO)

**M-1. Enumeration.** `AVCaptureDeviceDiscoverySession` with the device types `external` and
`builtInWideAngleCamera` (and `continuityCamera` where present) and the media type video lists the
cameras. Enumeration needs no camera permission [R mac_avf `list`] [NV].
- Confidence: medium.
- If false: detection is empty until permission is granted.
- Diagnostics: `tcc` at detection; `nodes_seen`.
- Certify: `detect`, `system:camera-access` [X-11].

**M-2. Identity.** For a USB camera, `uniqueID` is the hex form of `locationID << 32 | VID << 16 |
PID`. It holds the port: it changes when the camera moves to another port, and it differs for two
identical cameras on two ports [R xplat §2.5 item 4] [NV]. The `camera_id` input is `avf:` plus the
lower-case `uniqueID` [A]. VID and PID come from `uniqueID`; when it does not parse, from `modelID`
[R mac_avf `parse_model_id`] [NV]. A built-in or Continuity camera has no USB IDs.
- Confidence: medium.
- If false: two cameras collide (refused [W D13]) or have no USB IDs.
- Diagnostics: `identity_kind` (`unique-id-usb`, `unique-id-other`).
- Certify: `<label>:detect` [X-13].

**M-3. Virtual cameras.** A virtual camera has a `transportType` that is not USB, or a name with
"virtual" [W 7.1] [NV for the transport value]. Detection gives it `virtual: true`. A built-in or
Continuity camera is real.
- Confidence: low.
- Certify: `system:virtual-cameras`.

**M-4. Mode list.** Each `AVCaptureDeviceFormat` has a media subtype (`CMFormatDescriptionGetMediaSubType`),
the dimensions and `videoSupportedFrameRateRanges`. An MJPG mode of a UVC camera has the subtype
`'dmb1'` (`kCMVideoCodecType_JPEG_OpenDML`) [K19]. A rate range with `minFrameDuration` `v/t` gives
`fps_num = t`, `fps_den = v`, exactly, with no float [A]. One third-party run saw the MJPG modes
offered only as decoded `'420v'` [R stack §4.3] [NV].
- Confidence: medium.
- If false: `supported_modes` (MJPG only [W 7.3]) is empty.
- Diagnostics: `modes_listed`, `mjpg_sizes`, `subtypes` (a fixed string of the FourCCs seen, for
  example `dmb1,420v,yuvs`).
- Certify: `<label>:detect` [X-2].

**M-5. The camera JPEG arrives in a block buffer (the gating question).** With `videoSettings = {}`,
the output gives "samples in their device-native format" [K15]; compressed output exists on macOS
only [K17]. Chromium asks for `'dmb1'` through `kCVPixelBufferPixelFormatTypeKey` and reads the bytes
of each sample as MJPEG [K19]. Thus a sample of a `'dmb1'` format has a `CMBlockBuffer` with the JPEG
and no `CVPixelBuffer` [NV]. Whether these are the camera's bytes, or a JPEG that Apple's UVC camera
extension made again, no source shows [NV]. FFmpeg, OBS, GStreamer, SDL3 and nokhwa give decoded
pixels on macOS [R xplat §2.5 item 1].
- Confidence: low to medium. This is the largest risk (section 7.3, risk 1).
- If false: no JPEG passthrough on macOS (section 4.4.3 gives the fallback).
- Run-time check, on the first sample of each open: `CMSampleBufferGetImageBuffer` is null,
  `CMSampleBufferGetDataBuffer` is not null, the subtype is `'dmb1'` and the bytes start with
  `FF D8`: `delivered_kind = jpeg`. A pixel buffer: `delivered_kind = decoded`. The source tries the
  variants `{}` and then `'dmb1'` (section 4.4.3).
- Diagnostics: `delivered_kind`, `video_settings_variant` (`empty`, `dmb1`), `sha256_00` to
  `sha256_29`, `dqt_sha256` (a hash of the quantization tables of the first frame) (D-11).
- Certify: `<label>:native-jpeg` with `delivered`; byte-true is shown when `dqt_sha256` equals the
  value of the same camera model on Windows or Linux in the evidence file [cert 11.2] [X-2] [A].

**M-6. Setting the mode and the rate.** The source takes `lockForConfiguration`, sets `activeFormat`,
and sets `activeVideoMinFrameDuration` and `activeVideoMaxFrameDuration` to the exact
`minFrameDuration` of the chosen range. It keeps the lock across `startRunning`, so that a session
preset does not replace the format [R mac_avf header] [NV]. It reads back `activeFormat` and
`activeVideoMinFrameDuration`; a difference is a failure, stage `set mode`, code `no-mode`.
- Confidence: medium.
- Diagnostics: the fields of D-1.
- Certify: `<label>:opens`, `<label>:rate`.

**M-7. Threads and the run loop.** The sample delegate runs on a serial dispatch queue that the
source makes (`dispatch_queue_create`). Sample delivery needs no main run loop. Notifications come
through `addObserverForName:object:queue:usingBlock:` with an `NSOperationQueue`, also with no run
loop. All of this works in a spawned child with no `NSApplication` [NV for each].
- Confidence: low to medium.
- If false: no frame arrives (`first-frame-timeout`), or no removal event (then the 2 s stall rule
  makes the camera dead [W 9.5]).
- Diagnostics: `t_first_frame_ms`, `notifications_seen`.
- Certify: `<label>:opens` proves it on each run.

**M-8. PyObjC releases the GIL during an Objective-C call.** A blocked `startRunning`,
`stopRunning` or `lockForConfiguration` must not stop the other threads of the camera process, or
the bounded calls and the 100 ms rule fail [U, W 6.6] [NV].
- Confidence: medium.
- If false: a hung call stops the camera process, and its camera holds the gate until the 2 s stall
  rule of the main process (question 13).
- Run-time check: none in the product.
- Certify: `self:hang-100ms` covers the rule; T-UNX-55 checks the GIL release on the macOS runner.

**M-9. The sample time is host time on the clock of `perf_counter_ns`.** Each sample time is on
`synchronizationClock` (macOS 12.3 and later) [K14]. The host time clock uses `mach_absolute_time`
[K13], and so does `perf_counter` [K12]. When `CFEqual(session.synchronizationClock,
CMClockGetHostTimeClock())` is true, the source converts the PTS with
`CMClockConvertHostTimeToSystemUnits` to mach units and multiplies by the timebase
(`mach_timebase_info`) to nanoseconds, as Chromium does [K19]. That is the base of `perf_counter_ns`
[A]. Whether the PTS is the host time at arrival or a time from the camera clock is not known
[R xplat §2.5 item 3] [NV].
- Confidence: medium for the base; low for its meaning.
- If false: the 200 ms rule of [W 4.2] gives `NO_SAMPLE_NS`.
- Diagnostics: `clock` (`host`, `other`), `ts_conversion` (`host-to-mach-to-ns`),
  `sample_time_kept`, `arrival_minus_sample_p50_us`, `_p95_us`, `raw_ts_step_min_us` (D-2).
- Certify: `<label>:timestamps` (`clock_is_host`, `grid_ms`) [X-4].

**M-10. Drops are visible.** `captureOutput:didDropSampleBuffer:fromConnection:` comes for each frame
that AVFoundation drops (`alwaysDiscardsLateVideoFrames` is true) [NV]. `CMIOSampleBufferGetSequenceNumber`
gives a sequence number for each sample [R mac_avf] [NV]. A drop or a sequence gap sets
`discontinuity = True` on the next frame [W D34].
- Confidence: low to medium.
- Diagnostics: `drops_reported`, `sequence_gaps`, `sequence_lost`, `seq_available` (D-3).
- Certify: `<label>:timestamps` (`sequence_gaps`) [X-4].

**M-11. Another app can use the camera at the same time.** macOS lets two processes stream one camera
[NV]. The other app can change the active format [NV]. The source never fails for sharing alone. It
checks the dimensions of the format description of each sample against the opened mode; a change
gives the failure code `format-changed`, stage `streaming` [A]. An `AVErrorDeviceInUseByAnotherApplication`
gives `camera-in-use` [NV that macOS returns it].
- Confidence: low.
- Diagnostics: `format_changes` (count).
- Certify: `<label>:in-use` (`outcome` `shared` or `refused`) [cert 8.2].

**M-12. Errors and removal.** `AVCaptureSessionRuntimeErrorNotification` carries an `NSError` in
`AVCaptureSessionErrorKey`. `AVCaptureDeviceWasDisconnectedNotification` reports a removal. The
source maps an error by its `AVError` name, which it reads from the PyObjC constants, never from a
number in the code [A] [NV for which names exist on macOS].
- Confidence: medium.
- Diagnostics: `fail_code`, `fail_native` (the `NSError` code), `fail_call`.
- Certify: no unplug test [U]; the in-use check sees the error path.

**M-13. A USB bandwidth refusal has no documented signal.** It can be a runtime error, a session with
no frame, or a low rate [R xplat §2.5 item 6]. The source gives `first-frame-timeout` or the rate
check fails; it cannot tell bandwidth from another cause [A].
- Confidence: low.
- Diagnostics: `t_first_frame_ms`, `measured_fps` (status).
- Certify: `group:open` (`refusal_signal`) [X-8].

**M-14. Camera permission.** `AVCaptureDevice.authorizationStatus(for: .video)` gives
`notDetermined`, `restricted`, `denied` or `authorized` [K18] (the values 0 to 3 of the
`AVAuthorizationStatus` header [NV against a page]). A process without permission gets zero frames
and no error [R xplat §2.5 item 5] [NV]. Thus the source reads the status before each open. Any value
other than `authorized` gives the code `no-permission`, stage `open`, and the reason "camera
permission is <status>". The source never calls `requestAccess`: the app that starts the process asks
[A]. The permission belongs to the app that starts the process [R xplat §2.5 item 5] [NV]: the
SkellyCam app when it starts the server, the terminal when a person starts it from a shell. The
packaged app already has `NSCameraUsageDescription` and `com.apple.security.device.camera`
(`skellycam-ui/electron-builder.json`, `skellycam-ui/entitlements.mac.plist`), which Apple requires
[K18].
- Confidence: medium.
- If false: a camera with no permission gives `first-frame-timeout` instead of `no-permission`.
- Diagnostics: `tcc` (`authorized`, `denied`, `restricted`, `not-determined`) (D-8).
- Certify: `system:camera-access` (`tcc`) [X-11].

**M-15. Controls.** On macOS, AVFoundation has only the exposure modes locked and continuous auto,
with no absolute duration; `setExposureModeCustom` is not available there [R macctl §3 R8]. Absolute
values are possible only through CoreMediaIO feature controls (a public API, through Apple's own
driver) or UVC requests on endpoint 0 (field evidence only) [R macctl §1]. CoreMediaIO coverage on our
four cameras is not known; one report needed undocumented control classes [R macctl §1, §3 R1] [NV].
The source uses CoreMediaIO controls through `pyobjc-framework-CoreMediaIO` (section 4.4.6). When the
camera has a settable exposure control there, Manual and Auto work as on Linux. Else exposure is
"Auto by lock" only (section 4.5).
- Confidence: low.
- If false: no Manual exposure on macOS for that camera (section 7.3, risk 2).
- Diagnostics: `ctl_<name>_path` (`cmio`, `avf-lock`, `none`), `ctl_<name>_unit`, the set and get
  return codes (`OSStatus`) (D-4).
- Certify: `<label>:settings-stick` (through the product path), `<label>:control-ep0` (probe, risky
  phase) [X-6].

**M-16. Video effects.** Center Stage, Portrait, Studio Light and Reactions change the frames, and
AVFoundation reports them; Edge Light (macOS 26.2 and later) is not reported [R xplat §2.5 item 5].
The source reads the flags at the open. It does not change them [A].
- Confidence: medium.
- Diagnostics: `fx_center_stage`, `fx_portrait`, `fx_studio_light`, `fx_reactions` (booleans or
  null), `fx_edge_light` (always null) (D-8).
- Certify: `system:video-effects` [X-12].

**M-17. Close.** `stopRunning`, then the delegate is set to nil, the input and the output are removed,
and the objects are released. Each step is bounded. The close takes under 1 s [NV].
- Confidence: low.
- Diagnostics: `t_close_ms`.
- Certify: `<label>:cycles` [X-7].

**M-18. The USB link.** The IORegistry entry of the USB device, found by the `locationID` of
`uniqueID`, has the link speed [R xplat §2.5, cert X-19] [NV for the property name]. The source reads
it through `ctypes` calls to IOKit [A]. When it cannot, the label is `unknown`.
- Confidence: low.
- Diagnostics: `usb_link`; `usb_alt` is null on macOS.
- Certify: `system:usb` [X-19].

**M-19. PyObjC in the frozen app.** PyInstaller 6.22.3 collects the PyObjC frameworks that the source
imports [NV]. The build adds hidden imports when a test shows a gap (T-UNX-60).
- Confidence: medium.
- Certify: `detect` with `backend-missing` shows a frozen app that cannot load the layer.

### 2.3 Assumption summary

| ID | Short statement | Confidence | Observed by |
|---|---|---|---|
| A-1 | Capture nodes by `device_caps`; metadata nodes skipped | high | `detect` |
| A-2 | Identity from sysfs: serial, else port chain; by-id not used | medium | `<label>:detect` |
| A-3 | v4l2loopback: no USB parent, driver name | medium | `system:virtual-cameras` |
| A-4 | ENUM ioctls give discrete MJPG sizes and intervals | high | `<label>:detect` |
| A-5 | `S_FMT` can grant another size; read back | high | `<label>:opens`, `native-jpeg` |
| A-6 | `S_PARM` sets the rate; read back | high | `<label>:rate` |
| A-7 | mmap MJPG buffers are the camera's bytes | high | `<label>:native-jpeg` |
| A-8 | Damaged frames carry `V4L2_BUF_FLAG_ERROR` (nodrop) | high | `<label>:native-jpeg` |
| A-9 | Buffer time is `CLOCK_MONOTONIC` = `perf_counter_ns` base | high (grain NV) | `<label>:timestamps` |
| A-10 | `sequence` gaps show lost frames | high | `<label>:timestamps` |
| A-11 | 4 mmap buffers; push source with newest frame | high | `<label>:opens` |
| A-12 | `O_NONBLOCK` and `poll`: no unbounded wait for a frame | high | `<label>:cycles` |
| A-13 | Blocking ioctls bounded; GIL released; stuck kernel wait handled | high / medium | `self:hang-100ms` |
| A-14 | In use is `EBUSY` at `REQBUFS(0)` or `S_FMT` | medium | `<label>:in-use` |
| A-15 | Bandwidth refusal is `EIO` (or `ENOSPC`, `ENOMEM`) at `STREAMON` | medium | `group:open` |
| A-16 | No access is `EACCES`; seat ACL or `video` group | high | `system:camera-access` |
| A-17 | Control ids; menu MANUAL first; no absolute set in auto | high / medium | `<label>:settings-stick` |
| A-18 | log2 s to 100 µs map; -7 gives 78 | high | `<label>:settings-stick` |
| A-19 | Read-back can be cached | medium | `<label>:settings-stick` |
| A-20 | Controls hold while streaming; autosuspend loss [NV] | medium | `<label>:settings-stick` |
| A-21 | Close under 1 s; reopen works; Kiyo Pro quirk by kernel | low | `<label>:cycles` |
| A-22 | USB link and alternate setting in sysfs | medium | `system:usb`, `group:open` |
| A-23 | `spawn` and `O_CLOEXEC` | high | none needed |
| M-1 | Discovery session lists cameras with no permission | medium | `detect` |
| M-2 | `uniqueID` = locationID, VID, PID (holds the port) | medium | `<label>:detect` |
| M-3 | Virtual by transport type or name | low | `system:virtual-cameras` |
| M-4 | MJPG modes have subtype `'dmb1'`; exact frame durations | medium | `<label>:detect` |
| M-5 | `'dmb1'` samples hold the camera JPEG in a block buffer | low to medium | `<label>:native-jpeg` |
| M-6 | Format and duration set under the configuration lock | medium | `<label>:rate` |
| M-7 | Delegate queue and notifications work with no run loop | low to medium | `<label>:opens` |
| M-8 | PyObjC releases the GIL | medium | T-UNX-55, `self:hang-100ms` |
| M-9 | PTS on the host clock = `perf_counter_ns` base | medium / low | `<label>:timestamps` |
| M-10 | Drops and sequence numbers are visible | low to medium | `<label>:timestamps` |
| M-11 | Sharing allowed; a format change is detected | low | `<label>:in-use` |
| M-12 | Runtime errors and removal by notification | medium | `<label>:in-use` |
| M-13 | No bandwidth error; first-frame timeout or low rate | low | `group:open` |
| M-14 | Permission status read; no permission gives zero frames | medium | `system:camera-access` |
| M-15 | Absolute exposure only through CoreMediaIO (or endpoint 0) | low | `<label>:settings-stick`, `control-ep0` |
| M-16 | Effect flags readable; Edge Light not | medium | `system:video-effects` |
| M-17 | Close under 1 s | low | `<label>:cycles` |
| M-18 | USB link from the IORegistry | low | `system:usb` |
| M-19 | PyObjC works in the frozen app | medium | T-UNX-60, `detect` |

## 3. What stays and what is shared

- The capture interface of [W 4.1] stays: `open`, `read_frame`, `set_controls`, `close` and
  `replaced_count`. Section 4.2 adds `diagnostics()` and the failure code.
- The shared loop, the gate, the warm-up, the rate check, the states, the recorder and the rings stay
  as [W 5] to [W 12] give them. The floor of 30 fps [W U11], one rate for the group [W D18] and the
  rule "60 only when proven" [U] apply to each source through `modes.py` and `rate_check.py`.
- `CaptureWaitingPlace` of `source.py` serves both new sources (push sources).
- The OpenCV source stays as the fallback on Linux and macOS until a system is verified [U] (section
  4.9).

## 4. The design

### 4.1 Package layout

| Path | Content |
|---|---|
| `skellycam/core/camera/capture/bounded.py` | The bounded call of [W 6.6], moved out of `media_foundation/bounded.py` with no COM. `media_foundation/bounded.py` keeps a wrapper that joins the MTA in each worker [A]. |
| `skellycam/core/camera/capture/failure_codes.py` | The fixed failure codes of section 4.6.3 and the map from the stage and reason of today [A]. Pure. |
| `skellycam/core/camera/capture/exposure_units.py` | The map of A-18 between log2 seconds and 100 µs units. Pure. |
| `skellycam/core/camera/capture/v4l2/` | Linux only at run time. `abi.py` (ctypes structs, ioctl numbers, constants: ported from linuxlib with its reference sizes, offsets and numbers); `device.py` (the seam: `V4L2System` with the real calls `os.open`, `fcntl.ioctl`, `mmap`, `select.poll`, `os.close`, and sysfs reads under a root path); `detect.py`; `controls.py`; `errors.py` (errno to code, pure); `source.py` (`V4L2Source`). |
| `skellycam/core/camera/capture/avfoundation/` | macOS only at run time. `layer.py` (the seam: `AVLayer`, and `PyObjCLayer`, the real calls); `detect.py`; `controls.py` (CoreMediaIO and the AVFoundation lock); `errors.py` (AVError name to code, pure); `iokit.py` (the USB link, `ctypes`); `source.py` (`AVFoundationSource`). |
| `skellycam/tests/capture/fake_v4l2.py`, `fake_avfoundation.py` | The fake layers of section 6.2. |

Import rule [A, question 2]. The user decided that "everything in that folder is Windows only"
(`media_foundation/`) [U], and that Linux and macOS each get their own folder [U]. Thus `v4l2/` runs
only on Linux and `avfoundation/` only on macOS. But each of their modules imports only the standard
library at module level. `fcntl`, `mmap` and `select.poll` load inside `V4L2System` methods; `objc`,
`AVFoundation`, `CoreMedia`, `CoreMediaIO` and `libdispatch` load inside `PyObjCLayer.__init__`. Thus
the fake-layer tests run on Windows, Linux and macOS, as the user asked for parity tests
[U]. This differs from [W U18], where the Media Foundation tests run on Windows only.

### 4.2 Shared changes (step 7s)

1. `CaptureFailure` gets `code: str`, a value of section 4.6.3. The failure object of [W 12] gets
   `"code"` beside `stage` and `reason` [U]. The Media Foundation `errors.py` and `_mark_ended` of
   `camera_group.py` set codes too (parity). The text form stays `Camera {id} failed during {stage}:
   {reason}` [W D40].
2. Each source has `diagnostics() -> dict`: the fixed keys of section 4.6. The camera process writes
   the dict into the camera status at the end of `open`, at each control read of the control thread
   (one time per second [W 11.4]), at a failure and at the close. `CameraStatus.serialize()` adds
   `"diagnostics"`. The OpenCV source gives `backend` and the loop counters only.
3. The shared loop adds its own counters to the status beside the diagnostics: `decoded_by_skellycam`
   (frames that the decode stage decoded) and `encoded_by_skellycam` (frames that skellycam encoded:
   the OpenCV re-encode, or 3b) (D-10).
4. `select_capture_source()` of `camera_worker.py` covers Linux and macOS (section 4.9).
5. `detect_available_cameras()` calls the native detection on Linux and macOS, also when OpenCV is
   the chosen source, as Windows does [W D11]. The OpenCV source then opens the node that detection
   names (Linux: `cv2.VideoCapture(<node>, cv2.CAP_V4L2)`); on macOS it finds its index by the order
   of `uniqueID` in the device list that OpenCV uses [A] [NV].
6. `CameraDeviceInfo` gets `backend` (`v4l2`, `avfoundation`, `media-foundation`) and `usb_link`
   (`usb3`, `usb2`, `usb1`, `unknown`) [U]. The `camera_id` hash stays the function of today; its
   input changes on Linux and macOS (A-2, M-2). Each Linux and macOS camera gets a new ID one time, as
   on Windows [W D11].
7. Exposure modes: on the native Linux and macOS sources, a config with the camera's own auto exposure
   (`AUTO`) runs SkellyCam Auto (`RECOMMEND`) instead. "I never want to allow the camera to set it's
   own exposure" [U]. Question 4 asks whether Windows changes the same way in this step.
8. An optional restore of the controls at the close (section 4.7). It is off until the user answers
   question 6.

### 4.3 The V4L2 source (step 7a)

#### 4.3.1 Detection

Detection runs in a short-lived `spawn` child with each call bounded, as on Windows [W 7.1, A]:

1. List `/dev/video*`. For each node: `open(O_RDWR | O_NONBLOCK | O_CLOEXEC)`, `VIDIOC_QUERYCAP`
   (A-1). Skip a node with no video capture in `device_caps`.
2. Read the sysfs data of A-2 and A-22: USB IDs, serial presence, `busnum`, `devpath`, `speed`,
   interface number, the card name. A node that cannot be opened (`EACCES`) is still listed from
   sysfs, with `modes_read: false` (A-16).
3. List the modes (A-4). Close the node.
4. Build `CameraDeviceInfo`: `index` (detection order, display only), `name` (the card name of
   `QUERYCAP`), `path` (`/dev/videoN`, as the OS gives it [W W6]), `vendor_id`, `product_id`,
   `supported_modes` [W 7.3], `modes_read`, `virtual` (A-3), `backend`, `usb_link`.
5. Refuse two equal `camera_id` values [W D13].

#### 4.3.2 Open

Each step is a bounded call (A-13). The 15 s ready limit of [W 9.3] applies.

1. Detection again in the camera process (no child), and the match by `camera_id`, as Windows
   enumerates at each open [W 6.2]. No match: `not-found`. Two: `open-failed` [W D13].
2. `open()` the node (`EACCES`: `no-access`; `ENOENT` or `ENODEV`: `not-found`).
3. `VIDIOC_REQBUFS` with `count = 0` (A-14: `EBUSY` gives `camera-in-use`).
4. Choose the mode by [W 7.5] from the mode list (A-4). `S_FMT` with MJPG, read back (A-5).
5. `S_PARM`, `G_PARM`, read back (A-6).
6. `REQBUFS` with `count = 4`, `QUERYBUF` and `mmap` of each buffer, `QBUF` of each (A-11).
7. `STREAMON` (A-15).
8. Start the capture thread. Wait for the first frame, at most 5 s [W 6.4]: else
   `first-frame-timeout`, then the close with its bounded steps.
9. `open` returns `OpenedMode` with the read-back mode and `device_path` = the node.

A failure at steps 2 to 8 runs the close of 4.3.7 for the steps that ran.

#### 4.3.3 The capture thread

One thread for each source, named `v4l2 capture`:

1. `poll` the file with a timeout of 100 ms (A-12). A timeout: check the stop flag, then poll again.
   `POLLERR`: `VIDIOC_DQBUF` gives the errno.
2. `VIDIOC_DQBUF`. Take `arrival_ns = perf_counter_ns()` first, after the call returns [W D28].
   `EAGAIN`: poll again. `ENODEV`: the error marker with `device-removed` (dead [W D38]). `EIO`:
   count it; three `EIO` in a row give the error marker with `stream-error` [A].
3. Copy `bytesused` bytes of the mapped buffer into one `bytes` object. `QBUF` the buffer at once.
4. Build `CapturedFrame`: `payload`, `format` `MJPG`, `arrival_ns`, `sample_ns` (A-9),
   `delivered_len = bytesused`, `driver_error` (A-8), `source_frame_number` (the count of dequeued
   buffers since the open), `discontinuity` (A-10).
5. Put the frame into the waiting place. Update the counters of the diagnostics.

The thread does no file I/O, no logging per frame and no decode [W 4.3]. It never spins: each pass
waits in `poll` [W 4.3].

#### 4.3.4 `read_frame`

`read_frame(timeout_s)` takes from the waiting place, as `MediaFoundationSource` does [W 4.2].

#### 4.3.5 Controls

`set_controls(changes)` is one bounded call. For each change: read before, set, then read every
control back [W D20, W 6.8]. The map:

| skellycam control | V4L2 | Unit |
|---|---|---|
| `exposure` (manual) | `V4L2_CID_EXPOSURE_AUTO` = 1 (MANUAL), then `V4L2_CID_EXPOSURE_ABSOLUTE` = A-18 value, in one `S_EXT_CTRLS` | log2 s outside, 100 µs inside |
| `exposure` (`auto: true`) | Not set on the camera: the shared loop runs SkellyCam Auto (4.2 item 7) | — |
| `gain` | `V4L2_CID_GAIN` (and `V4L2_CID_AUTOGAIN` = 0 when present) | raw, as UVC |
| `focus` | `V4L2_CID_FOCUS_AUTO` = 0, then `V4L2_CID_FOCUS_ABSOLUTE`; with `auto: true`, `V4L2_CID_FOCUS_AUTO` = 1 | raw, as UVC |
| `white_balance`, `power_line` | read only (`V4L2_CID_AUTO_WHITE_BALANCE`, `V4L2_CID_WHITE_BALANCE_TEMPERATURE`, `V4L2_CID_POWER_LINE_FREQUENCY`) | raw, menu |

- A control that `QUERY_EXT_CTRL` does not list is absent (`present: false`) [W D43].
- A control with the flag `inactive` or `disabled` at the set gives `control-failed` [A].
- The status reports the read-back value; for exposure, the log2 value of A-18.
- Focus auto is a mode of the camera. The user's rule is about exposure only [U]; focus follows
  [W 11.5].

#### 4.3.6 Errors

| errno | Call | Code | Stage | Reason |
|---|---|---|---|---|
| `EACCES` | `open` | `no-access` | `open` | "no access to the video device" |
| `ENOENT`, `ENODEV`, `ENXIO` | `open` | `not-found` | `open` | "camera not found" |
| `EBUSY` | `REQBUFS`, `S_FMT`, `S_PARM`, `STREAMON` | `camera-in-use` | the stage of the call | "in use by another program" [W D13] |
| `EIO`, `ENOSPC`, `ENOMEM` | `STREAMON` | `usb-bandwidth` | `start stream` | "USB bandwidth refused, or a device error (errno <name>)" |
| `EINVAL` | `S_FMT`, `S_PARM` | `no-mode` | `set mode` | "the camera refused <mode>" |
| `EACCES`, `EINVAL`, `ERANGE` | `S_EXT_CTRLS` | `control-failed` | `set controls` | "<control>: <errno name>" |
| `ENODEV` | `DQBUF`, `poll` | `device-removed` | `streaming` | "device removed" |
| `EIO` three times | `DQBUF` | `stream-error` | `streaming` | "stream error (EIO)" |
| any other | any | `open-failed` or `stream-error` | the stage of the call | "<call>: <errno name>" |
| (hang) | any bounded call | `hung` | the stage of the call | "<call> did not return in 5 s" |

#### 4.3.7 Close

Each step is bounded; a hung step stops the close and the process ends hard [W 6.6]:

1. Set the stop flag; join the capture thread (at most 1 s: it waits at most 100 ms in `poll`).
2. The restore of 4.7, when it is on.
3. `STREAMOFF`.
4. `munmap` each buffer; `REQBUFS` with `count = 0`.
5. `close()` the file.

#### 4.3.8 Removal

`ENODEV` at `DQBUF` or `POLLERR` with `ENODEV` makes the camera dead at once [W D38]. Without an
error, the stall rule of 2 s applies [W 9.5]. No unplug test runs [U].

### 4.4 The AVFoundation source (step 7b)

#### 4.4.1 Detection

In a short-lived `spawn` child with each call bounded [A]:

1. Read the permission status (M-14). Detection runs also without permission.
2. The discovery session of M-1. For each device: `uniqueID`, `modelID`, `localizedName`,
   `transportType`, `deviceType`, the formats (M-4).
3. Build `CameraDeviceInfo` as in 4.3.1, with `path` = `uniqueID` as the OS gives it [W W6],
   `virtual` (M-3), `usb_link` (M-18).

#### 4.4.2 Open

Each step is bounded:

1. Permission (M-14): not `authorized` gives `no-permission`.
2. Find the device by `camera_id` (detection again, as in 4.3.2).
3. `AVCaptureDeviceInput.deviceInputWithDevice_error_`; an `NSError` gives its code (4.4.8).
4. `AVCaptureSession`, `AVCaptureVideoDataOutput` with `alwaysDiscardsLateVideoFrames = True`, the
   delegate on a serial dispatch queue (M-7), the observers of M-12.
5. Choose the mode by [W 7.5] from the MJPG (`'dmb1'`) formats. Set it under the lock (M-6).
6. Set `videoSettings` to the variant of 4.4.3. `startRunning` while the lock is held, then unlock.
7. Wait for the first frame, at most 5 s [W 6.4]. Check `delivered_kind` (M-5). Read the effect
   flags (M-16).
8. Return `OpenedMode`.

#### 4.4.3 The JPEG variants and the fallback (M-5)

1. Variant `empty`: `videoSettings = {}` [K15]. The first sample decides `delivered_kind`.
2. When the first sample is decoded: stop, set variant `dmb1` (`kCVPixelBufferPixelFormatTypeKey` =
   `'dmb1'`, as Chromium [K19]), start again.
3. When the second variant is decoded too, or the output refuses it, the source fails with the code
   `no-native-jpeg`, stage `start stream` [A]. The camera process then opens the OpenCV source for
   this camera when the selection rule allows a fallback (4.9). After step 3b, a decoded NV12 or YUY2
   sample can go to the encoder of [W 13] instead; that is a later choice (question 1).

`video_settings_variant` and `delivered_kind` record the result.

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

| skellycam control | First path | Second path | Never |
|---|---|---|---|
| `exposure` | CoreMediaIO exposure feature control: `AutomaticManual = 0` (manual), then `NativeValue` [NV for units: UVC 100 µs assumed, A-18 map]; also the AVFoundation `exposureMode = locked`, so that AVFoundation does not apply its own auto mode again [R macctl §1 item 3] | `avf-lock` (4.5) | endpoint 0 (question 3) |
| `gain` | CoreMediaIO gain feature control, manual | absent | endpoint 0 |
| `focus` | CoreMediaIO focus feature control; with `auto: true`, `AutomaticManual = 1` | AVFoundation `focusMode` locked or continuous auto | endpoint 0 |
| `white_balance`, `power_line` | CoreMediaIO read, if published | absent | — |

- The source finds the CoreMediaIO device whose `kCMIODevicePropertyDeviceUID` equals `uniqueID`
  [R macctl §1]. It reads the constants from `pyobjc-framework-CoreMediaIO`, never from FourCCs in
  the code [A].
- After each `startRunning`, the source sets the controls again [R macctl §1 item 3] [W D20].
- Each set and get records its `OSStatus` in the diagnostics (D-4).

#### 4.4.7 Close (M-17)

1. Remove the observers; set the delegate to nil.
2. The restore of 4.7, when it is on.
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

### 4.5 Exposure on each source

- Modes: Manual (a value in log2 seconds) and Auto. Auto is SkellyCam's one-shot search on the open
  stream with a frame-rate guard [U]: `RECOMMEND` of [W 11.1] (-12 to -5, 10 frames to settle, one
  step darker), then the rate check of [W 10.2] guards the result. The camera's own auto exposure is
  never a mode [U].
- Linux: Manual and Auto through A-18. Each open sets the menu to MANUAL, also when the config asks
  for Auto: the search then sets each value in manual mode [A]. This ends the forced auto exposure of
  the OpenCV source on Linux for the native source [U].
- macOS with a CoreMediaIO exposure control: as Linux.
- macOS without it ("Auto by lock") [A]: Manual is not offered (`present: false` for a manual value;
  a request for a manual value gets HTTP 422 with "Camera {id} has no manual exposure control"
  [W 11.5]). Auto runs the camera's continuous auto exposure for at most 2 s after the first frame,
  then sets `exposureMode = locked` and runs the rate check. The user allows the camera's auto only
  for a moment at start-up to find a start value [R NATIVE_JPEG_CAPTURE_PLAN §14]. A failed rate
  check gives the text "Add light" of [W 10.4].
- Gain and focus follow [W 11.5]; on macOS through CoreMediaIO when present.

### 4.6 Diagnostics

#### 4.6.1 Rules

- `diagnostics()` returns one dict with fixed keys. Each value is an int, a float, a bool, null or a
  string of a fixed vocabulary, with one exception: `frame_log`, a list of at most 64 rows [A].
- No value holds a serial number, a device path, a `uniqueID`, a `camera_id`, a camera name, a host
  name or a user name [cert 9.4]. A SHA-256 of frame bytes is allowed: it does not show the image.
- A key that a source cannot fill is null. Each source gives every key, so that certify reads one
  form on each system.
- Cost [A]: the counters cost a few integer operations per frame. `frame_log` is a ring of 64 rows of
  five integers (under 4 KiB). The 30 SHA-256 values cost one hash per frame for the first 30 frames
  after the first frame: about 0.2 ms each for a 200 kB JPEG at 1 GB/s [NV], in the capture thread,
  then nothing. The percentiles use the last 256 differences (a ring of ints) and run only when
  `diagnostics()` is called, one time per second.

#### 4.6.2 Keys

| Requirement | Keys | Linux | macOS | Windows (parity) |
|---|---|---|---|---|
| — | `backend` | `v4l2` | `avfoundation` | `media-foundation` |
| D-1 | `req_width`, `req_height`, `req_fps_num`, `req_fps_den`, `req_format`; `got_width`, `got_height`, `got_fps_num`, `got_fps_den`, `got_format`; `delivered_kind` (`jpeg`, `decoded`, `none`); `video_settings_variant` (`empty`, `dmb1`, null) | `G_FMT`, `G_PARM` | `activeFormat`, durations | read-back type |
| D-2 | `clock` (`monotonic`, `host`, `mf-sample-time`, `copy`, `unknown`, `other`); `tstamp_src` (`soe`, `eof`, null); `ts_conversion` (`timeval-to-ns`, `host-to-mach-to-ns`, `100ns-units`); `sample_time_kept`; `arrival_minus_sample_p50_us`, `_p95_us`; `raw_ts_step_min_us` | flags | sync clock | `GetSampleTime` |
| D-2, D-3 | `frame_log`: rows `[source_frame_number, sequence, raw_ts_ns, arrival_ns, bytesused_or_flags]` where the last item is `bytesused`, negative when the error flag is set [A] | yes | sequence null when absent | sequence null |
| D-3 | `frames`, `sequence_gaps`, `sequence_lost`, `seq_available`, `error_flags`, `zero_bytes`, `drops_reported`, `discontinuities`, `poll_timeouts`, `format_changes` | yes | yes | yes (counts that apply) |
| D-4 | For each control `c` of `exposure`, `gain`, `focus`, `focus_auto`, `white_balance`, `power_line`, `exposure_priority`: `ctl_<c>_id` (native id: V4L2 CID, IAM property id, CoreMediaIO class id as an int), `ctl_<c>_value` (native), `ctl_<c>_unit` (`100us`, `log2s`, `raw`, `menu`, `bool`, `seconds`), `ctl_<c>_min`, `_max`, `_step`, `_default`, `ctl_<c>_auto`, `ctl_<c>_path` (`v4l2`, `iam`, `ks`, `cmio`, `avf-lock`, `ep0`, `none`), `ctl_<c>_set_rc`, `ctl_<c>_get_rc` (errno, HRESULT or `OSStatus` of the last call), `ctl_<c>_before`, `ctl_<c>_before_auto` | yes | yes | yes |
| D-5 | `fail_code`, `fail_native` (errno, HRESULT, `NSError` code or `OSStatus`, as a number), `fail_call` (a fixed call name, for example `VIDIOC_STREAMON`, `startRunning`, `ActivateObject`), `fail_stage`, `failed_calls` (count), `busy_call` | yes | yes | yes |
| D-6 | `t_enumerate_ms`, `t_open_ms`, `t_set_mode_ms`, `t_buffers_ms`, `t_stream_on_ms`, `t_first_frame_ms`, `t_controls_ms`, `t_close_ms` | yes | yes | yes |
| D-7 | `identity_kind` (`serial`, `usb-path`, `unique-id-usb`, `unique-id-other`, `symbolic-link`, `none`) | A-2 | M-2 | `symbolic-link` |
| D-8 | `access_path` (Linux: `seat-acl`, `video-group`, `root`, `none`); `tcc` (macOS); `fx_center_stage`, `fx_portrait`, `fx_studio_light`, `fx_reactions`, `fx_edge_light` | `access_path` | `tcc`, `fx_*` | null |
| D-9 | `usb_alt`, `usb_link` | sysfs | `usb_alt` null | null, `usb_link` from the sfn26 port |
| D-10 | `decoded_by_skellycam`, `encoded_by_skellycam` (the shared loop, 4.2 item 3) | yes | yes | yes |
| D-11 | `sha256_00` to `sha256_29` (hex of the payload as the OS gave it, before a DHT insertion), `dqt_sha256` | yes | yes | yes |
| Linux | `kernel`, `driver`, `nodrop_param`, `clock_param`, `buffers_requested`, `buffers_granted`, `interval_types`, `nodes_seen`, `nodes_skipped_meta` | yes | null | null |
| macOS | `macos`, `subtypes`, `notifications_seen`, `sync_clock_is_host` | null | yes | null |

#### 4.6.3 Failure codes

The failure codes are the reason codes of [cert 15] where one exists [A]: `not-found`, `no-access`,
`no-permission`, `camera-in-use`, `previous-process-alive`, `usb-bandwidth`, `no-mode`,
`below-floor`, `open-failed`, `first-frame-timeout`, `no-native-jpeg`, `not-ready`, `rate-low`,
`rate-high`, `control-failed`, `device-removed`, `stalled`, `stream-error`, `format-changed`, `hung`,
`process-ended`, `disk-stall`. `skellycam/REASON_CODES.md` of [cert 15] gives one sentence for each
(certify step). The Media Foundation map: the in-use HRESULTs give `camera-in-use`, the removal
HRESULTs give `device-removed`, the rest `open-failed` or `stream-error` [W 6.7].

### 4.7 Restore of the controls at the close (option) [A]

- At the first control read of each open (before any set), the source keeps each control value and
  its auto flag (`ctl_<c>_before`, `ctl_<c>_before_auto`).
- When the option is on, the close sets each changed control back to its "before" value and auto
  flag, and reads it back, before `STREAMOFF` or `stopRunning` (A-20). A failed restore is logged and
  recorded in the diagnostics; the close continues.
- The option is a parameter of the source, set by the camera process from the setting
  `SKELLYCAM_RESTORE_CONTROLS` (`1` or `0`) [A]. Its default waits for question 6.
- A camera that failed, hung or was removed is not opened again to restore it in the same certify run
  [U]. The restore runs only inside a close of an open camera.

### 4.8 Threads

| Thread | Linux | macOS |
|---|---|---|
| Capture | `v4l2 capture` (4.3.3) | the serial dispatch queue of AVFoundation (4.4.4) |
| Waiting place | as [W 4.3] | as [W 4.3] |
| Camera loop | as [W 4.3] | as [W 4.3] |
| Control | as [W 4.3] [W U16] | as [W 4.3] |
| Bounded-call workers | `capture/bounded.py`, one thread per call | the same |
| Notifications | none | the `NSOperationQueue` of M-7 |

No thread spins [W 4.3].

### 4.9 Source selection [U, A]

- Settings: `SKELLYCAM_LINUX_CAPTURE` (`opencv`, `v4l2`) and `SKELLYCAM_MACOS_CAPTURE` (`opencv`,
  `avfoundation`), on the model of `SKELLYCAM_WINDOWS_CAPTURE` [W 14.2] [A]. A wrong value gives an
  error that names the allowed values.
- Default, proposed (question 5): the first source that applies of this list:
  1. The setting, when it is set.
  2. A local pass record: certify writes it after a passing run on this machine, for the OS key and
     the backend [cert 11.2]. Then native capture is used "there and then" [U].
  3. The shipped evidence file `camera_evidence.json` [cert 11.2]: `verified` for the OS key and the
     backend gives native.
  4. Else OpenCV.
- A camera whose native open fails with `no-native-jpeg`, or that the evidence file marks `known-bad`
  for the native backend, opens with OpenCV instead, when the default (not the setting) chose native
  [A, question 7]. The status shows `backend: opencv` for it.
- Certify always uses the native source [cert 2.1].
- Detection is always native (4.2 item 5).

### 4.10 CI

- The capture workflow (`.github/workflows/capture.yml`) runs the new fake-layer tests in its three
  jobs, with no new job [A].
- `capture-linux` (`ubuntu-24.04`) also runs the tests with the marker `capture_linux_runner`
  (section 6.3). One step runs `sudo modprobe vivid || true` [A]. The tests with the marker
  `v4l2_vivid` skip when no vivid node exists. Whether the hosted runner can load vivid or
  v4l2loopback is not known [K25] [NV]; no done item depends on it.
- `capture-macos` (`macos-15`) also runs the tests with the marker `capture_macos_runner` (section
  6.4). `uv sync` installs PyObjC there through its markers.
- The build workflow (`build-installers-pyinstaller.yml`) runs T-UNX-60 on its macOS jobs [A].

## 5. Parity with the Windows spec

States: **same** (the rule or test applies unchanged); **differs** (how); **n/a** (why); **unknown**
(certify must show it). A row can hold several IDs with one state.

### 5.1 Decisions and answers of the Windows spec

| IDs | Linux | macOS |
|---|---|---|
| D1 (pure Python, no compiled extension, no Rust) | same: standard library | same: PyObjC (no own compiled code) |
| D2, D19 (steps 3a, 3b, 3c; YUY2 and NV12) | differs: MJPG only in 7a; uncompressed modes after 3b | differs: MJPG only; decoded fallback after 3b (4.4.3) |
| D3, D47, D48 (spec first; fake tests in CI; done list) | same: section 6 | same |
| D4, U8 (no H.264) | same | same |
| D5 (phase order) | differs: phase 7 moves before phase 0 [U] | differs, the same |
| D6 (one loop, interface, sources) | same: `V4L2Source` | same: `AVFoundationSource` |
| D7 (comtypes) | n/a: no dependency | differs: PyObjC (section 7.2, question 8) |
| D8, U1, T-CAP-43, T-CAP-76, T-CAP-88 (Windows setting, deletion, DirectShow path) | differs: `SKELLYCAM_LINUX_CAPTURE`; OpenCV stays until verified [U] | differs: `SKELLYCAM_MACOS_CAPTURE` |
| D9 (old recorder) | n/a: removed by step 5a | n/a |
| D10, U12, U16 (bounded calls, hard end, control thread) | same: A-13 | same if M-8 holds; unknown until certified |
| D11, D12, D13, W6 (native detection, open by path, in use, duplicates, path as the OS gives it) | same: A-1, A-2, A-14 | same: M-1, M-2; in use differs (M-11) |
| D14, U11 (`supported_modes`, floor) | same | same |
| D15, D16, D17, D18, U7, U10, U15 (mode choice, auto rate, tolerance, one rate) | same | same |
| D20, D21, D22, D23, D24, D25 (start-up order, warm-up, rate check, failed camera) | same | same |
| D26, D27 (newest frame, `source_frame_number`) | same | same |
| D28 (`arrival_ns`, `sample_ns`) | same; `sample_ns` from A-9 | same; `sample_ns` from M-9 (unknown until certified) |
| D29, D35 (exposure modes and unit) | differs: camera auto is never a mode (4.5) [U]; unit map A-18 | differs: as Linux, or Auto by lock (4.5) |
| D30, D31, D32, D33, D36, D37 (current values, live changes, checks, auto at record start) | same; D37 never fires for exposure, because no auto mode is set | same, except Auto by lock: the control is locked, not auto |
| D34 (discontinuity) | differs: also from `sequence` gaps (A-10) | differs: from drops and sequence numbers (M-10) |
| D38, D39, U6 (dead camera, slow camera) | same: `ENODEV` (4.3.8) | same: removal notification (4.4.9) |
| D40, U9 (failure object) | differs: adds `code` (4.2) [U] | the same |
| D41 (camera ID check) | same | same |
| D42, T-CAP-50 (libjpeg pipe on Windows) | n/a: works in the camera process [W 16.7 (g)] | n/a |
| D43, D44 (gain, focus, white balance, power line) | same: 4.3.5 | differs: only through CoreMediaIO; else absent |
| D45 (USB link not in phase 3) | differs: the USB link is in this step [U] | the same |
| D46, W2, U23 (OpenCV rules) | same while OpenCV is the fallback | same |
| D49 (hardware tests of 3a) | differs: certify checks (6.5) | differs, the same |
| U2 (no stamp, no reopen) | same | same |
| U3 (comparison run) | differs: certify `group:take-30` replaces it | the same |
| U4, U5 (removed interim rules) | n/a | n/a |
| U13 (interim relay) | same | same |
| U14 (failed live change) | same | same |
| U17 (warm-up count, detection data) | same | same |
| U18 (Windows-only package and its tests) | differs: the package runs on Linux only, but its tests run on each OS (4.1, question 2) | the same |
| U19, U20, U21, U22 (API entry, CI, hardware counterparts, parity table) | same: section 6 and this section | same |
| W1, W3, W4, W5, W7, W8 | same | same |

### 5.2 Rules of the body of the Windows spec

| Rule | Linux | macOS |
|---|---|---|
| 4.2 `CapturedFrame` fields | same | same |
| 4.2 `NO_SAMPLE_NS` rule (200 ms) | same | same |
| 4.3 threads, waiting place, error marker | same | same |
| 6.1 process set-up (COM, MFStartup) | n/a | differs: `PyObjCLayer` loads the frameworks in the camera process |
| 6.2 enumerate at each open, match by `camera_id` | same | same |
| 6.3 read-back of the mode | same (A-5, A-6) | same (M-6) |
| 6.4 first frame in 5 s | same | same |
| 6.5 callback steps | same as 4.3.3 | same as 4.4.4 |
| 6.6 bounded calls, 5 s, hard end, main process cleans up only that camera | same (A-13) | same if M-8 holds |
| 6.7 in use, removed, stall | differs: errno table 4.3.6 | differs: table 4.4.8 |
| 6.8 controls: read before, set, read back in one bounded call | same | same |
| 6.9 close order | differs: 4.3.7 | differs: 4.4.7 |
| 7.1 detection in a child process, bounded | same | same |
| 7.2 `camera_id` hash of the lower-case input | same function, new input (A-2) | same function, new input (M-2) |
| 7.4 `capture_modes` (3c) | same when 3c lands | same |
| 9.5 stall watch | same | same |
| 11.1 `RECOMMEND` range -12 to -5 | same, through A-18 | same with CoreMediaIO; Auto by lock otherwise |
| 12 stage names | same; adds codes | same |
| 13 uncompressed modes | n/a in this step | n/a in this step |
| 14.1 forced auto exposure on Linux | differs: ends for the native source [U] | n/a |
| 15 CI | same jobs, more tests (4.10) | same |

### 5.3 Tests of the Windows spec

| T-CAP IDs | Linux | macOS |
|---|---|---|
| 01 to 21, 25 to 42, 44, 61 to 67, 70 to 75, 80 to 87, 89 to 91, 99 to 113 (fake source and OpenCV fake) | same: they run in CI today [W 16.7] | same |
| 22 (HRESULT map) | differs: T-UNX-12 (errno map) | differs: T-UNX-32 (AVError map) |
| 23 (duplicate links refused) | differs: T-UNX-08 | differs: T-UNX-28 |
| 24, 106 (`camera_id` of the link) | differs: T-UNX-07 | differs: T-UNX-27 |
| 43, 76 (Windows setting) | differs: T-UNX-45 | differs: T-UNX-45 |
| 45 (pin of comtypes) | differs: T-UNX-46 (no Linux dependency) | differs: T-UNX-46 (PyObjC pins) |
| 46 (load the module on the runner) | differs: T-UNX-50, T-UNX-51 | differs: T-UNX-55 to T-UNX-58 |
| 47 (no compiled extension) | same | same |
| 48 (detection child with a hang) | differs: T-UNX-09 | differs: T-UNX-29 |
| 49 (idle CPU, local) | differs: T-UNX-40 on the runner (not calibrated) | differs: T-UNX-40 |
| 51 (detection with streaming cameras) | differs: certify `detect` while a session streams: unknown | the same |
| 52 (open, byte-equal payload) | differs: certify `<label>:opens`, `<label>:native-jpeg` (A-7) | differs: the same (M-5): unknown until certified |
| 53, 94 (generic camera fails the rate check) | differs: certify `<label>:rate` (X-16) | the same |
| 54, 93 (each rate) | differs: certify `<label>:rate:<mode>` (X-15) | the same |
| 55, 96 (dark room) | differs: certify light rule [cert 4.6] (X-17) | the same |
| 56 (in use) | differs: certify `<label>:in-use` (A-14) | differs: certify `<label>:in-use` (M-11) |
| 57, 97 (exposure steps) | differs: certify `<label>:exposure:<base>` (A-18) | differs: the same, if M-15 holds |
| 58, 95 (unplug) | n/a: no hot-unplug test [U] | n/a |
| 59 (`sample_ns` against `arrival_ns`) | differs: certify `<label>:timestamps` (A-9) | differs: the same (M-9) |
| 60, 98 (comparison run) | differs: certify `group:take-30` (X-18) | the same |
| 68, 69 (3b hardware) | n/a in this step | n/a in this step |
| 77 (auto values then manual) | n/a: no camera auto mode (4.5) | differs: Auto by lock: certify `<label>:auto-exposure` |
| 78 (gain, focus, white balance, power line) | differs: certify `<label>:control:*` | differs: the same, CoreMediaIO |
| 79 (`capture_modes` against the descriptors) | differs: certify `<label>:detect` against the USB descriptors in sysfs (unknown) | differs: `<label>:detect` only |
| 88 (DirectShow device of the link) | n/a | n/a |
| 92 (OpenCV open on Linux and macOS) | n/a: "no need to test" OpenCV [U]; certify checks native instead | n/a |

## 6. Test list

### 6.1 Kinds and markers

- **fake**: a test with `FakeV4L2System` or `FakeAVLayer`. It runs on Windows, Linux and macOS, and
  in the three CI jobs [U].
- **linux-runner**: needs a real Linux kernel and no camera. Marker `capture_linux_runner`; skipped
  on other systems.
- **macos-runner**: needs real macOS and PyObjC and no camera. Marker `capture_macos_runner`.
- **vivid**: needs a vivid node. Marker `v4l2_vivid`; skipped without one (4.10).
- **build**: runs in the build workflow on the frozen app.
- **certify**: a check of a certify run on a real system [cert 10.2]. These replace the hardware
  tests T-CAP-92 to T-CAP-98 for the native sources [cert 10.1]. Section 6.5 maps them.

The pass thresholds that this list adds are [A]. They can change when the tests are written.

### 6.2 The seams

- `V4L2System` (`v4l2/device.py`): `open(path, flags) -> handle`, `ioctl(handle, request, struct)`
  (mutates the struct, raises `OSError` with an errno), `mmap(handle, length, offset) -> buffer`,
  `poll(handle, timeout_ms) -> events`, `close(handle)`, `listdir(path)`, `read_text(path)`,
  `realpath(path)`. Each real method is one standard-library call. Paths are under the roots
  `dev_root` (default `/dev`) and `sys_root` (default `/sys`).
- `FakeV4L2System` scripts: nodes with `QUERYCAP` data; a sysfs tree; formats, sizes and intervals;
  `S_FMT` and `S_PARM` adjustments; buffers with bytes, `sequence`, timestamp, flags; an errno or a
  hang at a given call and count; `poll` timeouts. It checks each ioctl number and struct size that
  the source sends.
- `AVLayer` (`avfoundation/layer.py`): `authorization_status()`, `devices()`, `open_device(unique_id)`,
  `configure(format_index, duration, variant)`, `start(callback)`, `stop()`, `close()`,
  `host_ns(pts)`, `sync_clock_is_host()`, `controls()` (CoreMediaIO list, get, set; AVFoundation lock
  modes), `effects()`, `usb_speed(location_id)`, and a notification callback.
- `FakeAVLayer` scripts: devices with `uniqueID`, `modelID`, transport and formats; a permission
  status; samples (a JPEG block, a decoded array, or none), PTS, sequence numbers, drops; errors and
  notifications at a given time; a hang at a given call; CoreMediaIO controls that are present,
  absent, ignored or failing.

### 6.3 Linux tests

| ID | Step | Kind | What it does | Pass criterion |
|---|---|---|---|---|
| T-UNX-01 | 7a | fake | Size, offset and alignment of each struct of `abi.py`. | Each equals the reference values of linuxlib (`REF_SIZES`, `REF_OFFSETS`), for example `v4l2_buffer` 88 bytes, `timestamp` at 24, `sequence` at 56; each struct is 1024 bytes or less (A-13). |
| T-UNX-02 | 7a | fake | Compute each ioctl number. | Each equals `REF_IOCTLS` of linuxlib, for example `VIDIOC_DQBUF` 0xC0585611, `VIDIOC_S_EXT_CTRLS` 0xC0205648. |
| T-UNX-03 | 7a | fake | Pack a `v4l2_buffer`, a `v4l2_format` with MJPG 1280x720 and a `v4l2_ext_controls` with two controls. | The bytes equal golden bytes in the test (hand-built from `videodev2.h`). |
| T-UNX-04 | 7a | fake | Detection on a fake tree: a C922 (serial), two identical cameras with no serial on two ports, a metadata node per camera, a v4l2loopback node, a node with `EACCES`. | Five cameras; metadata nodes skipped; the loopback `virtual: true`; the `EACCES` camera with `modes_read: false`; `identity_kind` `serial` and `usb-path`; no serial or path in `diagnostics()`. |
| T-UNX-05 | 7a | fake | Mode lists: discrete intervals 1/30, 1/60, 1/15, 1001/30000, a stepwise range 1/60 to 1/5, YUYV formats, and a size with only 15 fps. | `supported_modes` is the JSON of [W 7.3]: MJPG only, 29.97, 30.0 and 60.0, no 15; the stepwise range gives 29.97, 30 and 60 only (A-4). |
| T-UNX-06 | 7a | fake | USB link from sysfs `speed` 12, 480, 5000, 10000, missing. | `usb1`, `usb2`, `usb3`, `usb3`, `unknown`. |
| T-UNX-07 | 7a | fake | `camera_id` inputs for a serial camera, a serial-less camera, and the same serial-less model on two ports. | The inputs of A-2; three different IDs; the hash function is that of today. |
| T-UNX-08 | 7a | fake | Two cameras with the same serial (a firmware fault). | Each falls back to the port input; no collision. A forced collision is refused with an error that names both nodes [W D13]. |
| T-UNX-09 | 7a | fake | Detection where `QUERYCAP` of one node hangs. | The detection child ends; the call returns within 5 s + 2 s with `hung`; the main process runs on. |
| T-UNX-10 | 7a | fake | Open steps against the fake, and spy the call order. | `open`, `REQBUFS(0)`, `S_FMT`, `G_FMT`, `S_PARM`, `G_PARM`, `REQBUFS(4)`, `QUERYBUF`, `mmap`, `QBUF` x4, `STREAMON`; the node has `O_NONBLOCK` and `O_CLOEXEC`. |
| T-UNX-11 | 7a | fake | `S_FMT` returns 640x480 for 1280x720; `G_PARM` returns 1/15 for 1/30. | Failure `no-mode`, stage `set mode`, both cases; the close runs; `got_*` diagnostics hold the granted values. |
| T-UNX-12 | 7a | fake | Each errno and call of table 4.3.6. | The code, the stage and the reason of the table; `fail_native` is the errno; `fail_call` the ioctl name. |
| T-UNX-13 | 7a | fake | `EBUSY` at `REQBUFS(0)`; then at `S_FMT`. | `camera-in-use`, "in use by another program"; `busy_call` names the call; in the first case no `S_FMT` was sent. |
| T-UNX-14 | 7a | fake | `STREAMON` gives `EIO`, `ENOSPC`, `ENOMEM`, `EINVAL`. | `usb-bandwidth` for the first three with the errno name in the reason; `open-failed` for `EINVAL`. |
| T-UNX-15 | 7a | fake | 300 frames with `sequence` 0, 1, 2, 4, 5 ...; one with `V4L2_BUF_FLAG_ERROR`; one with `bytesused` 0. | `source_frame_number` has no gap; the frame after the gap has `discontinuity`; `sequence_gaps` 1, `sequence_lost` 1; the flagged and the empty frames have `driver_error`; the shared loop flags their slots `CAPTURE_ERROR`. |
| T-UNX-16 | 7a | fake | Timestamps: monotonic flags with times 5 ms before arrival; then one 300 ms before; a second open with the timestamp type `UNKNOWN`. | `sample_ns = tv_sec × 10^9 + tv_usec × 1000` while valid; `NO_SAMPLE_NS` for the rest of the open after the 300 ms frame; `NO_SAMPLE_NS` from the start with `UNKNOWN`; `clock` and `tstamp_src` set. |
| T-UNX-17 | 7a | fake | The fake delivers frames 0 to 4 before the first `read_frame`. | As T-CAP-02: frame 4, `replaced_count` 4. |
| T-UNX-18 | 7a | fake | `poll` times out for 6 s after 10 frames. | The loop marks the camera dead between 2.0 and 2.25 s after the last arrival [W 9.5]; the capture thread uses under 2 % of one core while it waits. |
| T-UNX-19 | 7a | fake | `DQBUF` gives `ENODEV` at frame 50. | `dead` at once, code `device-removed`. |
| T-UNX-20 | 7a | fake | `DQBUF` gives `EINTR` (the fake raises `InterruptedError`) once at each of 10 frames. | 10 frames delivered; no failure. |
| T-UNX-21 | 7a | fake | Exposure: set `MANUAL -7`, `-12` with a minimum of 3, `-5`; a camera with only menu items 1 and 3. | One `S_EXT_CTRLS` per set with the menu item 1 first, then 78, 3 and 313; read-back compared in native units; status values -7, -12, -5; never a set of the absolute value with the menu at 3. |
| T-UNX-22 | 7a | fake | The fake returns `EACCES` for a set of the absolute value when the menu is not 1. | The source never gets `EACCES` in T-UNX-21; a forced order gives `control-failed` and the camera stays in its earlier state [W U14]. |
| T-UNX-23 | 7a | fake | Config `AUTO` (the camera's own auto) on the native source. | The menu is set to MANUAL; the search of `RECOMMEND` runs; the config ends with `MANUAL` and the found value (4.5) [U]. |
| T-UNX-24 | 7a | fake | Gain, focus, focus auto; a camera with no focus; white balance and power line values. | Set and read back; focus absent gives `present: false` and the text of [W 11.5]; white balance and power line get no set call. |
| T-UNX-25 | 7a | fake | A control ioctl hangs on the control thread while two fake cameras are `ready`. | As T-CAP-82: stage `streaming`, code `hung`, hard end, the other camera has no gap above 100 ms. |
| T-UNX-26 | 7a | fake | `STREAMOFF` hangs at the close. | `hung`, stage `close`; the process ends hard within 5 s + 2 s. |
| T-UNX-27 | 7a | fake | The close order, with the restore on and off. | Stop, join (under 1 s), restore (when on: each changed control set back and read back), `STREAMOFF`, `munmap` x4, `REQBUFS(0)`, `close`. |
| T-UNX-28 | 7a | fake | "Apply again" for a camera whose old process is still alive (the fake process does not exit). | Failure `previous-process-alive`, stage `open`; no `open()` of the node. |
| T-UNX-29 | 7a | fake | `diagnostics()` after 100 frames. | Every key of 4.6.2 is present; each value has its type; `frame_log` has 64 rows; `sha256_00` to `sha256_29` are the hashes of frames 0 to 29; no value matches a path, a serial or a name of the fake. |
| T-UNX-30 | 7a | fake | A three-camera group with `V4L2Source` over the fake (not `FakeSource`) through the shared loop, 30 s of fake time at 30 fps. | Equal ring frame counts; payload bytes equal the fake bytes; T-CAP-05 rules on the gaps and `replaced_count`. |

### 6.4 macOS tests

| ID | Step | Kind | What it does | Pass criterion |
|---|---|---|---|---|
| T-UNX-31 | 7b | fake | Detection: a C922 (`uniqueID` with a location, VID, PID), two identical cameras on two ports, a built-in camera, a virtual camera, a camera with `'420v'` formats only. | Five cameras; the virtual one `virtual: true`; VID and PID parsed; two different `camera_id` values for the identical cameras; the `'420v'` camera with `supported_modes = []` and `modes_read: true`. |
| T-UNX-32 | 7b | fake | Each event of table 4.4.8 (by AVError name). | The code, the stage and the reason of the table; `fail_native` is the `NSError` code. |
| T-UNX-33 | 7b | fake | Permission `notDetermined`, `denied`, `restricted`, `authorized`. | `no-permission` with the status in the reason for the first three, before any device call; `tcc` set; no `requestAccess` call. |
| T-UNX-34 | 7b | fake | Mode set: frame-rate ranges with `minFrameDuration` 1/30, 1001/30000, 1/60; the read-back of the duration differs. | Exact `fps_num`/`fps_den`; the lock is held across `start`; the second case fails `no-mode`. |
| T-UNX-35 | 7b | fake | Variants: (1) `empty` gives JPEG blocks; (2) `empty` gives decoded, `dmb1` gives JPEG; (3) both decoded. | (1) `delivered_kind` `jpeg`, `video_settings_variant` `empty`; (2) `jpeg`, `dmb1`; (3) `no-native-jpeg`, stage `start stream`. |
| T-UNX-36 | 7b | fake | 300 samples with PTS on a host clock 3 ms before arrival; then a sync clock that is not the host clock. | `sample_ns` from `host_ns`; with the other clock `NO_SAMPLE_NS` and `clock` `other`. |
| T-UNX-37 | 7b | fake | A drop callback at sample 100; a sequence gap at sample 200. | The next frames have `discontinuity`; `drops_reported` 1; `sequence_gaps` 1. |
| T-UNX-38 | 7b | fake | The format of the samples changes to 640x480 at sample 50. | `format-changed`, stage `streaming`; `format_changes` 1. |
| T-UNX-39 | 7b | fake | Controls: CoreMediaIO exposure present; absent; present but the set is ignored (read-back differs). | Present: Manual -7 sends native 78 and locks the AVFoundation mode; absent: Manual gets 422 text, Auto runs "Auto by lock" (2 s, then locked, then the rate check); ignored: `control-failed`, the camera keeps its state. |
| T-UNX-40 | 7a, 7b | fake | A paused camera process with `V4L2Source` and with `AVFoundationSource` over the fakes, 10 s. | Process CPU under 2 % of one core (the rule of T-CAP-49) on each CI runner. Not calibrated: the result is recorded when it fails on a runner, and the user decides [A]. |
| T-UNX-41 | 7b | fake | `stopRunning` hangs at the close; `startRunning` hangs at the open. | `hung`, stages `close` and `start stream`; the process ends hard within 5 s + 2 s. |
| T-UNX-42 | 7b | fake | A three-camera group with `AVFoundationSource` over the fake through the shared loop. | As T-UNX-30. |
| T-UNX-43 | 7b | fake | `diagnostics()` after 100 samples, with effect flags set. | As T-UNX-29, with `tcc`, `fx_*` and `fx_edge_light` null. |
| T-UNX-44 | 7b | fake | The delegate raises inside the copy. | The error marker; `read_frame` raises `CaptureFailure` with `stream-error`; nothing raises into the layer. |

### 6.5 Shared tests

| ID | Step | Kind | What it does | Pass criterion |
|---|---|---|---|---|
| T-UNX-45 | 7s | fake | `select_capture_source()` on each `sys.platform` value with the settings unset, valid, wrong; with a local pass record; with an evidence row `verified`; with none. | The order of 4.9; a wrong value gives an error that names the allowed values; Windows unchanged. |
| T-UNX-46 | 7s | fake | Read `pyproject.toml` and `uv.lock`. | The PyObjC pins of section 7.2 with `==` and the marker `sys_platform == "darwin"`; no new dependency for Linux; locked at the same versions. |
| T-UNX-47 | 7s | fake | `CaptureFailure` and the failure object across a process boundary; each code of 4.6.3. | `code` survives pickling; the failure object has `code`; each code is in the list; Media Foundation HRESULTs map to codes. |
| T-UNX-48 | 7s | fake | `exposure_units` for each v from -14 to -2, with ranges (3, 2047, step 1) and (1, 5000, step 1). | The table of A-18; the clamp; the read-back; `floor(x + 0.5)` (not round-half-even). |
| T-UNX-49 | 7s | fake | `no-native-jpeg` from a native open, with the default selection, then with the setting. | Default: the camera opens with OpenCV, status `backend: opencv`, a log line; setting: the camera is `failed` with `no-native-jpeg`. |
| T-UNX-50 | 7a | linux-runner | Import `v4l2`; detection with the real `V4L2System`. | It returns a list (empty with no camera); no exception. |
| T-UNX-51 | 7a | linux-runner | `ioctl` `VIDIOC_QUERYCAP` on a file that is not a V4L2 node (`/dev/null`). | `OSError` with `ENOTTY`; the map gives `open-failed` with "VIDIOC_QUERYCAP: ENOTTY". |
| T-UNX-52 | 7a | linux-runner | `perf_counter_ns()` against `time.clock_gettime_ns(time.CLOCK_MONOTONIC)`, 1,000 pairs. | The difference is under 1 ms each time (A-9: one base). |
| T-UNX-53 | 7a | vivid | Open the first vivid capture node with the real system, 60 frames of a format that vivid offers, through the source with the MJPG check off [A]. | Frames arrive; flags monotonic; `sequence` increments by 1; T-UNX-52 base holds for `sample_ns`; the close returns. Skipped without vivid. |
| T-UNX-55 | 7b | macos-runner | A worker thread calls `NSThread.sleepForTimeInterval_(0.5)` through PyObjC; the main thread counts. | The main thread counts on during the sleep (M-8: PyObjC releases the GIL). |
| T-UNX-56 | 7b | macos-runner | `PyObjCLayer()`: load the frameworks; `authorization_status()`; `devices()`. | The status is one of the four values; the list is empty or holds no USB camera; no exception. |
| T-UNX-57 | 7b | macos-runner | `CMClockGetTime(CMClockGetHostTimeClock())` through `host_ns`, against `perf_counter_ns()`, 1,000 pairs. | The difference is under 1 ms each time (M-9: one base). |
| T-UNX-58 | 7b | macos-runner | The CoreMediaIO constants and `CMIOObjectGetPropertyData` exist in PyObjC; the IOKit `ctypes` calls load. | Each name exists; the IOKit calls return a speed or `unknown` for no device. |
| T-UNX-60 | 7b | build | On the macOS build jobs: run the frozen server with the native detection only (no camera). | The layer loads in the frozen app; detection returns a list; no missing module. |

### 6.6 Certify checks of each assumption

The hardware validation is a certify run on a real system [U]. This table gives the parity with the
Windows hardware tests. It does not repeat the certify spec.

| Assumptions | Certify check [cert] | Windows test it mirrors |
|---|---|---|
| A-1, A-2, A-3, A-4, M-1, M-2, M-3, M-4 | `detect`, `<label>:detect`, `system:virtual-cameras` | T-CAP-51, T-CAP-79, T-CAP-105 |
| A-5, A-6, A-11, A-12, M-6, M-7 | `<label>:opens`, `<label>:rate` | T-CAP-52 |
| A-7, A-8, M-5 | `<label>:native-jpeg` (`delivered`, `dqt_sha256`) | T-CAP-52 (byte-equal) |
| A-9, A-10, M-9, M-10 | `<label>:timestamps` | T-CAP-59 |
| A-13, M-8 | `self:hang-100ms` | T-CAP-82 |
| A-14, M-11, M-12 | `<label>:in-use`, `system:camera-holders` | T-CAP-56 |
| A-15, A-22, M-13 | `group:open`, `group:contention` | none (new) |
| A-16, M-14 | `system:camera-access` | none (new) |
| A-17, A-18, A-19, A-20, M-15 | `<label>:settings-stick`, `<label>:exposure:<base>`, `<label>:auto-exposure`, `<label>:controls`, `<label>:control:*`, `<label>:control-ep0` (macOS probe) | T-CAP-57, T-CAP-77, T-CAP-78 |
| A-21, M-17 | `<label>:cycles`, `<label>:timings`, `system:kernel` | T-CAP-54 (open times) |
| A-22, M-18 | `system:usb` | none (new) |
| M-16 | `system:video-effects` | none |
| M-19 | `detect` (`backend-missing`) | T-CAP-46 |
| rates and the generic camera | `<label>:rate:<mode>`, `<label>:rate` | T-CAP-53, T-CAP-54 |
| the group take | `group:take-30` | T-CAP-60 |

### 6.7 Counts

| Kind | Linux | macOS | Each OS |
|---|---|---|---|
| fake | 30 (T-UNX-01 to 30) | 14 (T-UNX-31 to 44) | 5 shared (45 to 49); all 49 run on Windows, Linux and macOS |
| linux-runner, vivid | 4 (50 to 53) | — | — |
| macos-runner, build | — | 5 (55 to 58, 60) | — |
| certify | section 6.6 | section 6.6 | — |

The IDs T-UNX-54 and T-UNX-59 are not used.

## 7. Dependencies, risks

### 7.1 Linux: no new dependency [A]

| Option | Cost | Choice |
|---|---|---|
| Standard library: `fcntl.ioctl`, `mmap`, `select.poll`, `ctypes` structs (port of linuxlib, 723 lines, with its self-test reference values) | No install, no PyInstaller change, no CI time. We own about 400 lines of ABI code [NV estimate]. | **Chosen** |
| linuxpy 0.25.0 (GPL-3.0-or-later, Python 3.10 and later [K24]) | A dependency with one maintainer [NV]; GPL-3.0-or-later is compatible with AGPL-3.0; its own device abstraction to learn; the research never tested it. | Rejected |
| v4l2py, pyv4l2 | Listed as "do not take" by the research [R xplat §2.4] | Rejected |

### 7.2 macOS: PyObjC, pinned exactly [A]

Proposed lines in `pyproject.toml` (13.0 is the latest release on 2026-11-20 [K21]):

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

Quartz and CoreAudio are listed because AVFoundation 13.0 requires them [K21]; each line pins them
exactly.

| Option | Cost | Choice |
|---|---|---|
| PyObjC 13.0 | Wheels for cp313 universal2: pyobjc-core 6.7 MB [K22], Cocoa 0.39 MB, Quartz 0.22 MB, CoreMediaIO 17 kB [K23]; AVFoundation, CoreMedia, CoreAudio and libdispatch [NV sizes]. The frozen app grows by about 8 to 12 MB [NV]. CI install: seconds from the uv cache [NV]. The research helpers use it [R mac_avf]. The delegate and the notification blocks are plain Python. | **Chosen** |
| `ctypes` to the Objective-C runtime | No dependency, but a delegate class made at run time (`objc_allocateClassPair`, `class_addMethod`), blocks for the notifications by hand, and struct returns of `objc_msgSend` per architecture. Several hundred lines that nobody tested [NV]. | Rejected |
| rubicon-objc | A dependency too, with less coverage of CoreMedia and CoreMediaIO [NV] | Rejected |

IOKit (M-18) uses `ctypes`, because PyObjC does not wrap IOKit fully [R macctl §3 R5] [NV].

PyInstaller: whether the hooks of PyInstaller 6.22.3 collect the PyObjC frameworks is [NV]. T-UNX-60
finds a gap; then `skellycam.spec` adds `collect_submodules` for each framework of the list, on macOS
only.

### 7.3 Risks, ranked

1. **No native JPEG through AVFoundation (M-5).** If false, the macOS native source cannot pass
   through the camera's JPEG. Plan: (a) the source fails with `no-native-jpeg`, and the camera opens
   with OpenCV (4.9), so macOS works as today; (b) after step 3b, the source can take the decoded
   samples and encode them with the 3b encoder, and still gives the timestamps, the controls and the
   diagnostics of the native path (question 1); (c) the plan of 2026-11-17 already says "If it does not,
   macOS stays on decode then re-encode" [R NATIVE_JPEG_CAPTURE_PLAN §3].
2. **No manual exposure on macOS (M-15).** If CoreMediaIO does not publish a settable exposure control
   on a camera: that camera gets only "Auto by lock" (4.5). The certify probe of endpoint-0 requests
   then shows whether that route works; the product uses it only on the user's word (question 3).
3. **Timestamps not on a usable clock (A-9, M-9).** If the sample time is not on the base of
   `perf_counter_ns`, the 200 ms rule gives `NO_SAMPLE_NS`, and the recorder keeps `arrival_ns` as the
   frame time [W D28]. Nothing else changes. On Linux the risk is low (one clock by the sources); on
   macOS medium.
4. **PyObjC holds the GIL in a call (M-8).** A hung AVFoundation call then stops the camera process and
   its camera holds the gate. Plan: a stall watch in the main process that removes a camera from the
   gate after 2 s with no frame (question 13). T-UNX-55 shows the fact in CI before any camera run.
5. **The source runs on no real system before certify.** Each struct, each ioctl number and each PyObjC
   call is written from documents and research code. Plan: the fake tests check each number against
   reference values; the first certify run on each OS gives every diagnostic at once, and the OpenCV
   fallback stays until a system passes [U].
6. **A stuck kernel wait on Linux (A-13).** The camera process cannot end until the driver returns.
   Plan: the main process does not wait; "apply again" refuses with `previous-process-alive`.
7. **Bandwidth refusal codes (A-15, M-13).** Plan: the reason names the errno; certify records it.
8. **Identity (A-2, M-2).** A port move gives a serial-less camera a new `camera_id` on Linux and each
   camera a new one on macOS. This is the behaviour of Windows for serial-less cameras [W 7.2].

## 8. Choices of the agent

Each item fills a gap that the decisions of the user do not fix. The body marks each one [A].
[ADR-AT04](../decisions/entries/AT04-choices-of-the-linux-and-macos-capture-spec.md) holds them.

1. The `camera_id` inputs of A-2 and M-2 (serial, else port chain; `uniqueID`).
2. Discrete intervals give exact fractions; a stepwise range gives only 29.97, 30 and 60.
3. Four mmap buffers; two or more accepted.
4. `O_NONBLOCK` with a `poll` timeout of 100 ms; three `EIO` in a row end the stream.
5. `REQBUFS(0)` before `S_FMT` to find "in use" without a USB request.
6. `EIO`, `ENOSPC` and `ENOMEM` at `STREAMON` give `usb-bandwidth`.
7. A node without access is listed from sysfs with `modes_read: false`.
8. One `S_EXT_CTRLS` with the menu item MANUAL first; `V4L2_CID_EXPOSURE_AUTO_PRIORITY` is read, never set.
9. The exposure map `floor(2^v × 10000 + 0.5)`, clamped to the range and the step; read-back
   compared in native units.
10. The native sources run SkellyCam Auto for a config that asks for the camera's auto exposure.
11. "Auto by lock" on macOS without a CoreMediaIO exposure control; Manual not offered there.
12. CoreMediaIO first for the macOS controls; endpoint 0 never in the product without the user's word.
13. The macOS JPEG variants `empty`, then `dmb1`; `no-native-jpeg` after both.
14. `dqt_sha256` to show byte-true JPEG against the same model on another OS.
15. The source never calls `requestAccess`; the app asks.
16. A format change during streaming gives `format-changed`.
17. The AVError map by PyObjC names, not by numbers.
18. The modules of `v4l2/` and `avfoundation/` import only the standard library at module level, so
    that the fake tests run on each OS.
19. The generic bounded call moves to `capture/bounded.py`.
20. The failure codes of 4.6.3, taken from the certify reason codes.
21. The diagnostic keys of 4.6.2, `frame_log` with 64 rows, the hashes of the first 30 frames.
22. The restore option with the setting `SKELLYCAM_RESTORE_CONTROLS`.
23. The settings `SKELLYCAM_LINUX_CAPTURE` and `SKELLYCAM_MACOS_CAPTURE`, and the default order of 4.9.
24. The per-camera OpenCV fallback after `no-native-jpeg` or a `known-bad` row.
25. `previous-process-alive` for "apply again" while the old process lives.
26. Detection in a short-lived child on Linux and macOS.
27. The OpenCV source on macOS finds its index by the `uniqueID` order.
28. No new CI job; the optional vivid step; the markers of 6.1; the build test T-UNX-60.
29. linuxpy rejected; PyObjC 13.0 with the eight pins of 7.2; IOKit through `ctypes`.
30. The pass thresholds of section 6.

## 9. Questions for the user

Each question is worded so that "yes" accepts the recommendation. The most important is first.

1. If AVFoundation gives no camera JPEG (M-5), the macOS camera opens with OpenCV, as today, and after
   step 3b the native source can instead encode the decoded samples (with native timestamps and
   controls). Until then a `no-native-jpeg` camera uses OpenCV. Yes?
2. The folders `v4l2/` and `avfoundation/` run only on their OS, but their modules import only the
   standard library at module level, so that their fake tests run on Windows, Linux and macOS (unlike
   the Windows-only tests of `media_foundation/`, U18). Yes?
3. On macOS the product uses CoreMediaIO feature controls only. UVC requests on endpoint 0 run only as
   a certify probe in its risky phase, and enter the product only after a run shows that they work and
   you say so. Yes?
4. The native Linux and macOS sources run SkellyCam Auto when a config asks for the camera's auto
   exposure. Should the Windows source change the same way in this step (it changes T-CAP-34, T-CAP-41
   and T-CAP-104)? Yes means: change Windows too, in a separate commit.
5. The default source on Linux and macOS: the setting first; then a local pass record of a certify run
   on this machine; then a `verified` row of the shipped evidence file; else OpenCV. Native capture is
   then used on a machine as soon as its certify run passes. Yes?
6. The product restores each camera's controls to their values before the open at its own close. Yes
   means the option is on by default, for the native sources on all three systems.
7. A camera that fails with `no-native-jpeg`, or that the evidence file marks `known-bad` for native
   capture, opens with OpenCV in the same group, when the default (not the setting) chose native.
   Yes?
8. The macOS dependencies are the eight PyObjC 13.0 packages of section 7.2, pinned with `==` and
   marked `darwin`; Linux gets no new dependency (no linuxpy). Yes?
9. The `camera_id` on Linux hashes the USB serial when it is present and unique, else the USB port
   chain; on macOS it hashes `uniqueID` (which holds the port). Each Linux and macOS camera gets a new
   ID one time. Yes?
10. The failure object gets the fixed codes of section 4.6.3 (the certify reason codes), also for
    Media Foundation, in step 7s. Yes?
11. The diagnostic keys of section 4.6.2, with `frame_log` of 64 rows and the hashes of the first 30
    frames, go into the camera status each second. Yes?
12. macOS cameras with no CoreMediaIO exposure control offer only "Auto by lock": the camera's own
    auto exposure for at most 2 s after the first frame, then locked, then the rate check. Yes?
13. A main-process stall watch removes from the gate a camera whose process gives no frame and no
    report for 2 s, and ends that process, as a guard if PyObjC or a driver holds the GIL. Yes?
14. CI adds no new job: the fake tests join the three capture jobs, the Linux job tries `modprobe
    vivid` without failing, and the macOS build jobs run the frozen detection test. Yes?
15. The certify checks of section 6.6 are the hardware tests of the Linux and macOS sources, and
    T-CAP-92 to T-CAP-98 (OpenCV on Linux and macOS) are retired, since OpenCV needs no test. Yes?
