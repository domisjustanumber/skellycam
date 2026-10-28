# Prior-art survey: cross-platform UVC capture libraries (skellycam USB-camera investigation)

Survey date 2026-10-25. Local tests ran on the Windows 11 machine `Gerald` (build 26300). Cameras under
`usbvideo.sys`: Razer Kiyo Pro 1532:0E05, Logitech C922 046D:085C, Logitech C930e 046D:0843, and from
about 18:15 UTC a fourth camera, "USB Camera" 4C4A:4A55. That fourth camera was not in the brief.

Status labels:
- **verified-here**: a result file under `results/windows/Gerald/` supports the claim. Each claim cites
  the command that produced it.
- **documented-untested**: read in the cited source or docs only. Use it as a claim for later phases to
  verify, not as a result.

Every drafted non-Windows test stays unverified until someone runs it.

## Reproduce

Each command below that opens a camera runs under `camlock`.

```
uv run --script research/usb_cameras/prior_art/repo_metadata.py                         # maintenance snapshot (no camera)
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/gst_probe.py --list
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/gst_probe.py --capture --source mfvideosrc --seconds 6
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/gst_probe.py --capture --source ksvideosrc --seconds 6
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/pyav_dshow_probe.py --seconds 6
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/pyav_dshow_probe.py --seconds 6 --wallclock
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/pyav_dshow_probe.py --list-options --tag listopts
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/pygrabber_probe.py
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/openpnp_capture_probe.py --lib <libopenpnp-capture-windows-latest-x86_64.dll v0.0.30>
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/sdl3_camera_probe.py --lib <SDL3.dll 3.4.18>
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/prior_art/cv2_enumerate_probe.py
```

Settings for every capture: 1280x720 MJPEG at a nominal 30 fps for 6 s. Exposure was not controlled
(camera auto), so fps values describe the delivered rate only. They do not measure camera capability.

Third-party binaries were downloaded to the scratchpad. Their hashes:
- openpnp-capture v0.0.30 DLL: sha256 3280266977f6ee70687d997455cd7463507ed5077d5de1235c4ef5d8f8e77b21
- SDL3 3.4.18 x64 DLL: sha256 2b4b128d8d510cc2d442693cf848c050d700d43dc667afe9e5fd82b0570d667e

The GStreamer wheels are `gstreamer-bundle==1.28.7` from PyPI. At runtime the library reports version
1.28.8. The 1.28.8 bundle cannot install on CPython 3.12 because its `gstreamer-plugins` package has no
cp39-abi3 `win_amd64` wheel (the uv resolver error is reproducible).

## Results measured on this Windows machine

| Library / path | MJPEG bytes untouched? | Timestamp it attaches | Identity it exposes | Result dir |
|---|---|---|---|---|
| GStreamer 1.28 `mfvideosrc` (IMFSourceReader) | **Yes**: 172/172, 155/155 and 168/168 frames were valid JPEG (SOI/EOI + Pillow decode); `image/jpeg` caps | PTS is the pipeline running time when the frame arrived in the reader thread. arrival−PTS median 0.11–0.13 ms; *20261027 rerun (C922, C930e, generic): 0.10–0.31 ms* (source: `gstmfsourcereader.cpp` sets `clock_time = get_running_time()`) | `device.path` = MF symbolic link `\\?\usb#vid_..&pid_..&mi_00#<instance>#{e5323777-...}\global`, plus `device.name` | `prior_art_gst_list`, `prior_art_gst_capture-mfvideosrc` |
| GStreamer `ksvideosrc` (kernel streaming) | **Yes**: 148/148, 173/173 and 168/168 frames valid | PTS = arrival − one frame duration. arrival−PTS was 33.35–33.83 ms on every camera | Device provider gives **no properties**; the element is opened by `device-name` only | `prior_art_gst_capture-ksvideosrc` |
| PyAV 19.0.2 / FFmpeg dshow (`vcodec=mjpeg`) | **Yes for C922 and C930e**: codec `mjpeg`, 182/182 and 183/183 packets valid JPEG, no decode. **No for Kiyo Pro**: codec `rawvideo`, 1843200-byte (YUY2) packets at both 720p and 1080p | Default: `IMediaSample::GetTime` + graph start, in 100 ns units. The intervals are *constant to 100 ns* (333333 on C922, 333383 on Kiyo, 333283/333333 on C930e). On the C930e, arrival−PTS drifted −4.5 ms/s. *20261027 rerun: C930e drift +1.20 ms/s, with one 17.27 ms PTS step (deltas 333333×166, 333283×8), so neither the drift nor exact constancy is stable; the generic camera's PTS stays at 333383 while it delivers 25.75 fps (+141 ms/s drift).* `use_video_device_timestamps=0` gives graph-clock time at 1 ms resolution, with arrival−PTS ≈30 ms ±1 (*20261027 rerun: ≈36.2 ms on all three cameras, so this is a cross-clock offset, not a latency*) | dshow "Alternative name" `@device_pnp_\\?\usb#vid_...{65e8773d-...}\global`. **Opening by this path works** | `prior_art_pyav_dshow`, `prior_art_pyav_dshow-wallclock`, `prior_art_pyav_dshow-kiyo-720p`, `prior_art_pyav_dshow-listopts` |
| pygrabber 0.2 | **No**. The sample grabber is forced to RGB24, so the callback gets a 720×1280×3 uint8 array. Kiyo Pro lists only 1 format (YUY2) because pygrabber keeps only FORMAT_VideoInfo | `SampleTime` is received by `BufferCB` and then dropped (not passed on) | `get_input_devices()` returns a list of FriendlyName `str` only | `prior_art_pygrabber` |
| openpnp-capture 0.0.30 (DirectShow) | **No**. The only frame API is `Cap_captureFrame(RGB buf, w*h*3)` and the sample grabber is set to RGB24 | None in the API | `Cap_getDeviceUniqueID` = `"<name> <DirectShow DevicePath>"`; virtual cameras get `"<name> <index>"` | `prior_art_openpnp_capture` |
| SDL3 3.4.18 camera API (Media Foundation) | **Yes**: `SDL_PIXELFORMAT_MJPG` surfaces hold JPEG bytes (`pitch` = byte length). 170/170, 153/153, 151/151 and 167/167 frames valid on all 4 USB cameras, Kiyo included | `IMFSample::GetSampleTime`, rebased by SDL to `SDL_GetTicksNS` at the first frame. Interval median 32.0 ms, max 48 ms | **Name only**. `SDL_GetCameraProperties` is empty. The MF symbolic link is held internally and not exposed | `prior_art_sdl3_camera` |
| cv2_enumerate_cameras 1.4.0 (helper for OpenCV) | n/a | n/a | For MSMF and DSHOW indices: symbolic-link `path`, `vid` and `pid` | `prior_art_cv2_enumerate` |

### Cross-library observation: arrival times arrive in ~16 ms steps

Every frame timestamp available on this machine that tracks real arrival falls on multiples of about
16 ms (32 ms and 48 ms intervals at 30 fps). These sources are the GStreamer mfvideosrc and ksvideosrc
PTS, the MF `IMFSample` sample time seen through SDL3, and FFmpeg's graph-clock mode. The only
exception is the DirectShow device sample time, which is constant to 100 ns and so is synthesized or
regularized; it carries no per-frame measurement. The quantization appears on the KS path too, so it
happens below Media Foundation, in `usbvideo.sys` or the USB stack.

*Hypothesis, not verified:* frames complete only at isochronous URB-completion boundaries.

Evidence is in the `frames_*.jsonl` files of `prior_art_gst_capture-*` and `prior_art_sdl3_camera`. To
recompute the histogram, bucket `host_arrival_ns` differences by 4 ms. **Consequence:** on Windows,
host arrival time and MF sample time alone cannot do better than about ±8 ms. UVC PTS/SCR is needed for
better timing (see Goal 2).

## Library-by-library survey

The maintenance snapshot is in `results/windows/Gerald/prior_art_repo_metadata/result.json` (GitHub API
via `gh`, PyPI and crates.io JSON, run 2026-10-25T18:38Z; refreshed 20261027 in `results/windows/Gerald/prior_art_rerun_20261027/`prior_art_repo_metadata/result.json, where the commit counts below changed as marked). The "commits" column counts commits on the
default branch since 2025-01-01.

| Candidate | Lang / license | Platforms | MJPEG passthrough | Timestamps | Device identity | Bandwidth control | Maintenance (2026-10-25) | Python |
|---|---|---|---|---|---|---|---|---|
| **libuvc** upstream | C / BSD-3 | Linux; macOS needs root; Windows only with a WinUSB or libusbK driver swap | Yes: raw `uvc_frame_t.data` | PTS and SCR are parsed (`hold_pts`, `hold_last_scr`) but **not copied into `uvc_frame_t`**. `capture_time` is never filled; only `capture_time_finished` (CLOCK_MONOTONIC at frame end) is set (src/stream.c @v0.0.8) [doc] | bus number and address, serial, VID:PID | Picks the smallest altsetting ≥ the camera's `dwMaxPayloadTransferSize`. No API, but the caller can edit the ctrl before start [doc] | v0.0.8 released 2026-09-13; 63 commits (*20261027: 81, after a burst of PR merges on 2026-10-26; no new release*) | no official binding |
| **Pupil Labs libuvc fork + pyuvc** (`pupil-labs-uvc` 1.0.8) | C + Cython / MIT on PyPI | Wheels for win_amd64, manylinux, musllinux and macOS arm64 | Yes: `MJPEGFrame.jpeg_buffer` | **PTS→host clock mapping** (QPC / CLOCK_MONOTONIC / mach) using SCR and isochronous-transfer timing; `frame.timestamp` [doc: `_uvc_populate_frame_ts_us`] | `uid = bus:address`, serialNumber, VID/PID | **`bandwidth_factor`** (default 2.0) recomputes the MJPEG packet size as w·h/8·factor·fps; "1.5 is needed to run 3 high speed cameras on one bus" [doc: stream.c @949cb47] | v1.0.8 released 2026-10-21; 29 commits | yes |
| openpnp-capture | C++ / MIT | Win (DirectShow), Linux (V4L2), macOS (AVFoundation) | **No**: decodes to RGB (verified on Windows; Linux decodes MJPG with libjpeg-turbo [doc]) | none | Win: name + DevicePath. Linux: name + `bus_info`. macOS: name + uniqueID, and it parses uniqueID as `0x<locationID 8 hex><VID><PID>` [doc] | no | v0.0.30 released 2025-06-13; 36 commits | ctypes (no package) |
| nokhwa (other phases test it) | Rust / Apache-2.0 | Win MSMF, Linux V4L2, macOS AVF | Yes: `FrameFormat::MJPEG` raw `Buffer` | 0.10.11 adds `Buffer.capture_timestamp` = wall-clock epoch at stream start + MF sample time [doc] | `CameraInfo.misc()` = MF symbolic link on Windows | no | 0.10.11 released 2026-05-15; 30 commits | no |
| **GStreamer** 1.28 | C / LGPL | All three platforms; official PyPI wheels for Windows and macOS | Win: **yes** (mfvideosrc and ksvideosrc verified). Linux v4l2src: `image/jpeg` [doc]. macOS avfvideosrc: **no JPEG caps** in the source | mf: arrival running time. ks: arrival − duration. v4l2src: the V4L2 buffer timestamp, with fallback when it is bad. avf: CMSampleBuffer PTS mapped to running time [doc] | mf: `device.path`. ks: nothing. v4l2: `device.path`, `device.bus_path` (ID_PATH), `sysfs.path`, vendor/product id, `device.serial`. avf: `unique-id` [doc] | no | very active; 5110 commits (*20261027: 5139*) | PyGObject (bundled in the wheels) |
| **FFmpeg / PyAV** 19.0.2 | C / LGPL; PyAV BSD-3 | All three | dshow: **yes** on 2 of 3 cameras (Kiyo falls back to raw). v4l2: `-input_format mjpeg` [doc]. avfoundation: pixel formats only, **no MJPEG** [doc] | dshow: regularized sample time, or graph clock. v4l2: kernel timestamp with `-ts` modes [doc] | dshow alternative name = device path (verified) | no | very active | PyAV wheels for all OSes |
| linuxpy 0.25.0 | Python / GPL-3.0 | Linux | Yes: raw V4L2 buffers [doc] | `Frame.timestamp` = v4l2_buffer timestamp [doc] | `info.bus_info`, card, driver [doc] | no | 0.25.0 released 2026-08-20; 141 commits | native |
| v4l2-python3 0.3.5 | Python / GPLv2 | Linux | ctypes ioctl bindings only | — | — | — | last PyPI upload 2024-08-27 | native |
| pygrabber 0.2 | Python / MIT | Windows | **No** (verified) | dropped | names only (verified) | no | last commit 2023-10-20; 0 commits since 2025 | native |
| WinRT MediaCapture (pywinrt) | C++ / Python, MIT | Windows | MJPG subtype in MediaFrameFormat; the mjpeg phase tests capture | `MediaFrameReference.SystemRelativeTime`: "100ns interval QPC time" [doc] | `MediaFrameSourceGroup.Id` (symbolic link) [doc] | no | pywinrt very active | yes |
| AVFoundation via pyobjc 12.2.2 | ObjC / Python, MIT | macOS | **Unknown**. Apple: "To receive samples in their device-native format, set [videoSettings] to an empty dictionary" [doc]. Whether this yields 'dmb1' JPEG bytes from UVC cameras is untested: see the macOS draft | CMSampleBuffer PTS (host time clock) | `uniqueID`, `modelID` (see the naming phase) | no | active | yes |
| **libcamera** UVC pipeline handler v0.7.2 | C++ / LGPL | Linux | MJPEG through the V4L2 formats [doc] | `SensorTimestamp` = V4L2 buffer timestamp; the source has "\todo Use the UVC metadata to calculate a more precise timestamp" [doc] | **ID = firmware (ACPI) node of the controller + USB port path (bus stripped) + VID:PID**: port-stable, identical models are distinguishable [doc] | no | v0.7.2; 1239 commits (*20261027: 1249*) | `libcamera` python bindings |
| **SDL3** camera 3.4.18 | C / zlib | Win MF, Linux V4L2, macOS CoreMedia, Android, Emscripten | Win: **yes** (verified, 4/4 cameras). V4L2: MJPG mapped [doc]. CoreMedia: no MJPG mapping in the source [doc] | backend timestamp rebased to SDL ticks | **name only** (verified) | no | 3.4.18 released 2026-10-02; 4510 commits (*20261027: 4534*) | PySDL3 (beta) |
| Qt Multimedia 6.12 | C++ / LGPL | All three | `QVideoFrameFormat::Format_Jpeg` exists [doc]; delivery from cameras untested | QVideoFrame start time [doc not opened] | `QCameraDevice::id()` "unique ID ... may not be human-readable"; stability not documented [doc] | no | active | PySide6 |
| OBS Studio 33.0.0 capture plugins | C/C++ / GPL-2 | All three | win-dshow takes compressed MJPEG from DirectShow and decodes with ffmpeg [doc] | win-dshow: `IMediaSample::GetTime` start time (libdshowcapture device.cpp). linux-v4l2: `buf.timestamp` relative to the first frame. mac: AVF [doc] | win: "name:path". mac: `uniqueID`. linux: device path + udev hotplug [doc] | no | 33.0.0 released 2026-10-23 | no |
| librealsense v2.59.1 | C++ / Apache-2.0 | All three | (RealSense-specific) | **Windows: reads UVC PTS/SCR through `MFSampleExtension_CaptureMetadata` → `MF_CAPTURE_METADATA_FRAME_RAWSTREAM` → `MetadataId_UsbVideoHeader`**, after `realsense_metadata_win10.ps1` sets the `MetadataBufferSizeInKB0` registry value per device interface (admin) [doc] | serial | n/a | active | pyrealsense2 |
| DepthAI (Luxonis) | C++ / MIT | All three | XLink, not UVC; vendor hardware | Device clock synced to host every ~5 s; "below 200µs" for USB (1σ) [doc]. FSYNC hardware sync [doc] | MxID | n/a | v3.11.0 | yes |
| Arducam / ELP vendor SDKs | — | — | — | The Arducam "hardware timestamping USB3" page was blocked (Cloudflare 403) and **not read** | — | — | ArduCAM_USB_Camera_Shield last commit 2023-11-10 | — |
| saki4510t/UVCCamera (Android libuvc fork) | C/Java | Android | Yes | — | — | `uvc_start_streaming_bandwidth(..., bandwidth_factor ∈ (0,1))` scales `dwMaxPayloadTransferSize` [doc] | last commit 2018-10-02 | — |
| nusb (Rust USB) | Rust / Apache-2.0 | Win, mac, Linux, WebUSB | — | — | — | **no isochronous transfers** (issue #47 still open, updated 2026-09-21) | v0.2.9 released 2026-10-24 | — |
| libusb 1.0.30 | C / LGPL | All three | — | — | — | WinUSB isochronous support since v1.0.23 (2019-08-28 ChangeLog) [doc]. On macOS 12+, detaching the UVC driver needs root; Apple will not grant the `com.apple.vm.device-access` entitlement to non-VM apps (libusb issue #1014) [doc] | v1.0.30 released 2026-05-17 | libusb1, pyusb |

## Goal-specific prior art

**Goal 2: timing**
- *Linux (documented-untested):* uvcvideo stamps each buffer with CLOCK_MONOTONIC when the first payload
  of the frame arrives (`uvc_video_decode_start`), flagged `TIMESTAMP_MONOTONIC | TSTAMP_SRC_SOE`.
  - PTS/SCR clock recovery (`uvc_video_clock_update`) runs only when the module parameter
    `hwtimestamps` is nonzero. The parameter is mode 0644 (root) and is checked per buffer.
  - The metadata node (`V4L2_META_FMT_UVC`) gives, per payload, the host ns timestamp, the USB SOF
    number and a copy of the 2–12 byte payload header (PTS and SCR).
  - Source: torvalds/linux @21a7f44, drivers/media/usb/uvc.
- *Windows (documented-untested):* the "Microsoft extensions to UVC 1.5" page says that if the
  `MetadataBufferSizeInKB<PinIndex>` registry value is present and nonzero, usbvideo.sys prepends a
  `MetadataId_UsbVideoHeader` item with the PTS, SCR and SOF token of the first and last payloads of
  each frame. librealsense uses exactly this path. The timing phase's `enable_uvc_metadata.ps1` should
  verify it.
- *Cross-platform user space (documented-untested):* the Pupil libuvc fork maps PTS to host time.
  Upstream libuvc discards PTS/SCR from the frame struct.
- *macOS:* nothing found that exposes raw UVC headers, except libusb/libuvc running as root.

**Goal 3: bandwidth**
- *Linux: correction to the brief's premise (documented-untested).* In uvcvideo, `UVC_QUIRK_FIX_BANDWIDTH`
  (0x80) applies **only to uncompressed formats**: `if (!(format->flags & UVC_FMT_FLAG_COMPRESSED) && quirks & FIX_BANDWIDTH ...)`.
  - The same condition is present in v3.2, v4.4, v5.15, v6.1 and master @21a7f44.
  - So `quirks=128` should not change the MJPEG altsetting. If it helps the user, the stream is probably
    YUYV, or the effect comes from something else. The bandwidth phase should test MJPEG vs YUYV with
    and without the quirk.
  - `quirks` is read at probe time (`dev->quirks = uvc_quirks_param == -1 ? info->quirks : uvc_quirks_param`),
    so changing it needs a rebind or replug as root.
- *User-space overrides that already exist (documented-untested):*
  - pyuvc `bandwidth_factor`: the MJPEG packet size is computed rather than taken from the camera.
  - UVCCamera `bandwidth_factor ∈ (0,1)`: scales the camera's `dwMaxPayloadTransferSize`.
  - Both require libusb access: a udev rule on Linux, root on macOS, a WinUSB/libusbK driver on Windows.
- No Windows or macOS native API for this was found. None of the libraries surveyed exposes a
  bandwidth knob through MF, DirectShow, KS or AVFoundation.

**Goal 4: naming**
- On Windows, the symbolic link or device path is exposed by GStreamer mf (`device.path`), FFmpeg dshow
  (alternative name, which also opens the device), openpnp (unique ID), cv2_enumerate_cameras (`path`)
  and nokhwa (`misc`). All verified, except nokhwa.
- Not exposed by pygrabber, SDL3 or GStreamer ks (names only, verified).
- Prior art for port-based IDs: the libcamera UVC camera ID (controller firmware node + port chain +
  VID:PID), GStreamer v4l2 `device.bus_path`, and openpnp's parsing of macOS uniqueID (locationID+VID+PID).

**Goal 1 / 5: cross-platform MJPEG passthrough**
- The best single-codebase options found: GStreamer (Windows mf/ks and Linux v4l2, but **not macOS
  avfvideosrc**), FFmpeg/PyAV (Windows dshow and Linux v4l2, but **not macOS avfoundation**, and the
  Kiyo falls back to raw), SDL3 (Windows MF and Linux V4L2, but not macOS CoreMedia) and libuvc/pyuvc
  (all three, but driver swap or root needed).
- macOS is the common gap. The only untested route is AVFoundation with an empty `videoSettings`
  (`drafts/macos/avf_native_mjpeg_probe.py`).

**Multi-camera mocap projects**
- SkellyCam/FreeMoCap: host perf_counter timestamps from OpenCV. Its own docs give "±half a frame" as
  the uncontrolled spread.
- Caliscope (mprib, BSD-2): wall-clock timestamps per frame, assembled into synchronized packets
  (`recording/frame_timestamps.py`).
- Pose2Sim: post-hoc sync by cross-correlating keypoint vertical speed (`synchronization.py` header).
- Kinovea author, 2015: sub-frame sync of two C920s with a flash and the rolling-shutter row delay;
  <1 ms in one run and 10–12 ms in another, at 100 µs exposure.
- DepthAI: hardware FSYNC plus host clock sync.
- Pupil Core: pyuvc PTS mapping.
- None of these controls USB bandwidth or exposure start on generic UVC webcams.
- The anipose, OpenPose, EasyMocap, Theia and Captury docs were not opened in detail. They are listed in
  the maintenance snapshot only.

## Drafted tests for other platforms (unverified until run)

- `prior_art/drafts/macos/avf_native_mjpeg_probe.py`: AVFoundation with `videoSettings={}`. Records the
  delivered media subtype, JPEG validity, and PTS vs host-time arrival.
- `prior_art/drafts/linux/linux_prior_art_probe.py`: uvcvideo parameter values and writability; linuxpy
  MJPEG capture with the V4L2 timestamp vs CLOCK_MONOTONIC arrival; the metadata node format; an
  optional `--try-hwtimestamps` run as root; `cam -l` and `gst-device-monitor-1.0` dumps.
- `prior_art/gst_probe.py` and `prior_art/pyav_dshow_probe.py` also run on Linux and macOS. GStreamer on
  Linux needs the system python3-gi.

## Sources opened (2026-10-25)

GitHub sources were fetched at the pinned tag or SHA through raw.githubusercontent.com or `gh api`:
- GStreamer @1.28.7 (070125524a): sys/mediafoundation/gstmfsourcereader.cpp, gstmfvideosrc.cpp,
  gstmfsourceobject.cpp, gstmfcapturewinrt.cpp; sys/winks/gstksvideosrc.c, gstksvideodevice.c;
  applemedia/avfvideosrc.m, avfdeviceprovider.m; v4l2/gstv4l2deviceprovider.c, gstv4l2src.c.
- FFmpeg master @46f23be8: libavdevice/dshow_pin.c, dshow.c, v4l2.c.
- Linux @21a7f44 and tags v3.2/v4.4/v5.15/v6.1: drivers/media/usb/uvc/uvc_video.c, uvc_driver.c,
  uvcvideo.h, uvc_queue.c.
- libuvc @v0.0.8: include/libuvc/libuvc.h, src/stream.c, README.md, plus the release notes.
- pyuvc @v1.0.8: uvc_bindings.pyx, README.rst, WINDOWS_USER.md.
- pupil-labs/libuvc @949cb47: src/stream.c.
- openpnp-capture @v0.0.30: win/, linux/, mac/ platform files and include/openpnp-capture.h.
- pygrabber @f0090e0: pygrabber/dshow_graph.py.
- SDL @release-3.4.18: src/camera/{mediafoundation,v4l2,coremedia}, SDL_camera.c, SDL_camera.h,
  SDL_pixels.h.
- nokhwa @0.10.11: nokhwa-core/src/buffer.rs, nokhwa-bindings-windows/src/lib.rs.
- libcamera @v0.7.2: src/libcamera/pipeline/uvcvideo/uvcvideo.cpp.
- OBS @33.0.0: plugins/win-dshow/win-dshow.cpp, linux-v4l2/v4l2-input.c, mac-avcapture/OBSAVCapture.m;
  libdshowcapture master source/device.cpp.
- librealsense @v2.59.1: scripts/realsense_metadata_win10.ps1, src/mf/mf-uvc.cpp.
- UVCCamera master: UVCPreview.cpp, libuvc/src/stream.c.
- linuxpy @v0.25.0: linuxpy/video/device.py.
- Caliscope main: src/caliscope/recording/frame_timestamps.py.
- Pose2Sim main: Pose2Sim/synchronization.py.
- libusb @v1.0.30: ChangeLog.
- nusb main: README.md; issue #47.
- libusb issue #1014.

Web pages:
- https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/uvc-extensions-1-5 (git commit 81d06fd)
- https://learn.microsoft.com/en-us/uwp/api/windows.media.capture.frames.mediaframereference.systemrelativetime
- https://developer.apple.com/documentation/avfoundation/avcapturevideodataoutput/videosettings (read through the JSON endpoint)
- https://docs.kernel.org/userspace-api/media/v4l/metafmt-uvc.html
- https://docs.luxonis.com/software/depthai-components/device/
- https://joancharmant.com/blog/sub-frame-accurate-synchronization-of-two-usb-cameras/
- https://doc.qt.io/qt-6/qcameradevice.html
- https://doc.qt.io/qt-6/qvideoframeformat.html
