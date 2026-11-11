# Dependency audit: third-party libraries vs new code (plan 2026-11-06)

Topic `deps_audit` for the 2026-11-06 brief: G-ID, G-TS, G-MJPEG and G-CTRL on Windows, Linux (Ubuntu, Fedora KDE) and macOS, with no camera-driver changes.

The question: for each candidate approach, how much would be outsourced to third-party libraries that may be out of date or unmaintained, and how much would be new code written here?

No camera was opened or enumerated for this report. Everything below comes from web APIs, source code and the repo's own files.

**Labels:**
- **measured:** a repo result file supports the claim (path given).
- **doc:** vendor documentation or source code (URL plus line or section).
- **web:** forum, issue or blog.
- **inferred:** my reasoning.

**Snapshot data:** maintenance numbers come from [`deps_audit_data/snapshot_20261106.json`](deps_audit_data/snapshot_20261106.json), taken 2026-11-06T15:14Z through the GitHub REST API (`gh api`), the PyPI and crates.io JSON APIs, and the GitLab API for gitlab.gnome.org and gitlab.freedesktop.org. The script is [`deps_audit_data/deps_snapshot.py`](deps_audit_data/deps_snapshot.py), and rerunning it needs no camera. These numbers are labelled **doc (API snapshot)**.

How the snapshot columns are defined:
- **"Commits 12 mo / authors":** commits on the default branch since 2025-11-06, with bots excluded.
- **"bf50" (bus factor):** the smallest number of authors who together made at least 50% of those commits.
- **"Releases 2 y":** GitHub releases (or PyPI or crates.io versions) since 2024-11-06.

## 1. Short answer

- **No third-party library meets all four goals on any single OS without a driver change.** The parts that matter most are left to the integrator in every library surveyed:
  - UVC PTS/SCR timestamps;
  - a serial-else-port camera key;
  - exposure, focus and white-balance control on macOS;
  - handling of USB-bandwidth refusals.

  So most of the value has to be new code whatever architecture is chosen. **inferred** from §3.
- **The libraries that would carry the most risk are the small ones.** Each has one maintainer, and each is stale, beta, or covers only part of the brief:
  - nokhwa: 4 commits in 12 months, 1 author;
  - uvc-util: last commit 2024-02;
  - CameraController: last release 2022-05;
  - pygrabber: last commit 2023-10;
  - the `v4l` crate: last release 2023-05;
  - duvc-ctl: 1 author, wheels only for Python 3.8–3.12 on win_amd64;
  - PySDL3: beta.

  None of them should be a hard dependency. **doc (API snapshot)**
- **The large dependencies are healthy and should be used:**
  - the OS APIs themselves (Media Foundation, V4L2, AVFoundation/IOKit);
  - PyObjC 13.0, released 2026-10-30 with the macOS 27 SDK;
  - pybind11 or nanobind, which are build-time only;
  - PyAV 19.0.2, released 2026-10-21.

  The caveat is that PyObjC and PyAV each have one dominant maintainer (bf50 = 1). **doc (API snapshot)**
- **The recommended split is architecture A:** a Python package with per-OS native code.
  - New code: about 6–9 kLOC.
  - Third-party: pybind11 or nanobind at build time; PyObjC at run time on macOS; optional PyAV as a Windows DirectShow fallback.
  - Architecture B (PyAV everywhere) still needs about 60–70% of A's native code to close its gaps (no Windows timestamps, no macOS MJPEG, no controls anywhere).
  - Architecture C (Rust) is the same amount of new code, plus binding-churn risk in `windows`, `v4l` and `objc2`.

  **inferred** (§4).

## 2. Library-by-library maintenance and capability

### 2.1 Maintenance snapshot (2026-11-06)

| Library | Latest version (date) | Last commit on default branch | Releases 2 y | Open issues / PRs | Commits 12 mo / authors / bf50 | License | Wheels relevant to us |
|---|---|---|---|---|---|---|---|
| **PyAV** (`av`) | 19.0.2 (2026-10-21) | 2026-11-06 | 9 GH releases (18 PyPI versions) | 7 / 0 | 416 / 33 / **1** (WyattBlue 343) | BSD-3 | cp312-abi3 + cp314t: win_amd64, **win_arm64**, macOS x86_64 (11+), macOS arm64 (**14+**), manylinux_2_28 x86_64/aarch64. **No Python 3.11** (v19.0.0: "Drop support for Python 3.11") |
| FFmpeg `libavdevice/dshow.c` | in FFmpeg 8.x | **2024-10-17** (dshow_pin.c 2024-03-30) | — | — | 0 commits in 2 y | LGPL | (via PyAV) |
| FFmpeg `libavdevice/v4l2.c` | | 2026-10-20 | — | — | 6 in 2 y, 4 authors | LGPL | |
| FFmpeg `libavdevice/avfoundation.m` | | 2026-08-30 | — | — | 8 in 2 y, 6 authors | LGPL | |
| **OpenCV** | 5.1.0 (2026-11-06); `opencv-python` 5.0.0.93 (2026-07-02) | 2026-11-05 | 7 | 2554 / 352 | `cap_msmf.cpp` 11 in 2 y by 11 authors; `cap_dshow` 6; `cap_v4l` 7; `cap_avfoundation_mac` 6 (all drive-by single commits) | Apache-2.0 | cp37-abi3, all platforms; macOS arm64 13+, x86_64 14+ |
| cv2_enumerate_cameras | 1.4.0 (2026-09-26) | 2026-09-26 | 11 | 0 / 0 | 23 / 5 / 1 | MIT | win wheels + py3-none-any |
| **GStreamer** | 1.28.9 tag (2026-11-06) | 2026-11-06 | monthly | 1038 open MRs (whole monorepo) | `sys/mediafoundation`: **0 in 12 mo**, last 2025-10-30 (seungha-yang 7 of 10 in 2 y); `sys/v4l2`: 37; `sys/applemedia`: 88 | LGPL | `gstreamer-bundle` 1.28.8 = Windows + macOS universal2 only, **no Linux**. `gstreamer-plugins` 1.28.8 has **only cp313t/cp314t (free-threaded) Windows wheels** |
| PyGObject | 3.58.1 (2026-10-09) | 2026-11-06 | 20 | 8 MRs | — | LGPL | **sdist only** on PyPI (needs system GI on Linux) |
| **SDL3** | 3.4.20 (2026-11-03) | 2026-11-05 | 41 | 750 / 140 | `src/camera`: 25 in 12 mo, 23 authors in 2 y | Zlib | (C library) |
| PySDL3 | 0.9.12b1 (2026-09-03), **beta** | 2026-09-03 | 70 | 8 / 1 | 27 / 3 / 1 | MIT | py3-none-any (ctypes; needs SDL3 DLL) |
| **nokhwa** (Rust) | 0.10.11 (2026-05-15) | **2026-04-13** | 4 | 57 / 10 | **4 / 1 / 1** | Apache-2.0 | crate |
| Qt Multimedia / PySide6 | 6.12.0 (2026-10-08) | 2026-11-06 | 18 PyPI | (Qt JIRA) | 1000+ / 40 / 1 | LGPL-3/GPL | cp310-abi3; win amd64/arm64; macOS 14+ universal2; manylinux_2_34 x86_64, 2_39 aarch64 |
| comtypes | 1.4.17 (2026-09-21) | 2026-11-05 | 9 | 89 / 2 | 85 / 5 / 1 (junkmd 80) | MIT | pure Python |
| pywin32 | 312 (2026-06-04) | 2026-11-03 | 4 | 329 / 64 | 107 / 16 / 1 | PSF | cp39–cp315, win32/amd64/arm64 |
| pygrabber | 0.2 (2023-10-20) | **2023-10-20** | 0 | 12 / 2 | 0 | MIT | pure Python |
| **duvc-ctl** | 2.1.0 (2026-07-23) | 2026-07-23 (repo created 2025-08-11) | 19 GH | 1 / 1 | 51 / 3 / 1 (allanhanan 46) | MIT | **cp38–cp312 win_amd64 only** (no 3.13/3.14, no arm64) |
| windows-rs (`windows` crate) | `windows` **0.62.2 (2025-10-06)**; `windows-core` 0.100.0 (2026-09-03) | 2026-11-06 | 14 | 35 / 1 | 954 / 7 / 1 (kennykerr 643) | MIT/Apache | crate |
| microsoft/Windows-Camera samples | no releases | 2026-09-21 | — | 3 / 0 | 21 / 2 | MIT | (samples, mostly WinRT) |
| openpnp-capture | v0.0.30 (2025-06-13) | 2025-11-13 | 2 | 12 / 5 | 6 / 1 / 1 | MIT | DLLs |
| nanobind | v3.1.0 tag; PyPI 2026-09-18 | 2026-11-01 | 26 PyPI | 15 / 23 | 361 / 38 / 1 (wjakob 281) | BSD-3 | build-time only |
| pybind11 | 3.1.0 (2026-08-06) | 2026-11-03 | 10 | 569 / 162 | 165 / 46 / **2** | BSD-3 | build-time only |
| pywinrt (`winrt-*`) | 10.0.28000.2957 (2026-10-31) | 2026-11-05 | 33 | 7 / 0 | 641 / 2 / 1 (dlech 640) | MIT | py3 wheels |
| **linuxpy** | 0.25.0 (2026-08-20) | 2026-08-20 | 5 | 5 / 6 | 19 / 2 / 1 | **GPL-3.0-or-later** | pure Python |
| v4l2py | 3.0.0 (2024-03-11) | 2024-03-11 | 0 | 0 / 4 | 0 | GPL-3 | renamed to linuxpy (same author); dead |
| v4l2-python3 | 0.3.5 (2024-08-27) | — | 0 | — | — | **GPLv2** | pure Python |
| pyv4l2 | 1.0.2 (2016-08-29) | 2019-05-16 | 0 | 5 / 0 | 0 | LGPL-3 | sdist only; dead |
| cameractrls | v0.6.10 tag | 2026-07-16 | — | 50 / 11 | 13 / 3 | LGPL-3 (repo) | not on PyPI (an app) |
| v4l-utils (libv4l2, v4l2-ctl) | 1.32.0 | 2026-03-17 (GitHub mirror) | — | — | 34 / 14 / 2 (Hans Verkuil) | GPL-2/LGPL-2.1 | distro package |
| `v4l` crate (libv4l-rs) | **0.14.0 (2023-05-12)** | **2024-10-05** | 0 | 13 / 15 | 0 | MIT | crate |
| `v4l2r` crate | 0.0.8 (2026-07-30) | — | 3 | — | — | non-standard | crate (Google ChromeOS author) |
| **libcamera** | v0.8.0 (2026-11-01) | 2026-11-04 | 9 | — | — | LGPL | distro packages; Python bindings in-tree, not on PyPI |
| PipeWire | 1.6.11 (2026-10-29) | 2026-11-06 | 20+ | 62 MRs | — | MIT | distro |
| xdg-desktop-portal | 1.22.1 (2026-06-17) | 2026-11-06 | 14 | 204 / 52 | 422 / 57 / 1 | LGPL | distro |
| **PyObjC** (`pyobjc-framework-AVFoundation`, `-CoreMedia`, `-CoreMediaIO`) | 13.0 (2026-10-30) | 2026-10-30 | 9 | 89 / 3 | 309 / 3 / **1** (ronaldoussoren 307) | MIT | universal2, cp311–cp315. No `pyobjc-framework-IOKit` or `-IOUSBHost` on PyPI (404) |
| objc2 / objc2-av-foundation (Rust) | objc2 0.6.5 (2026-10-05); framework crates 0.3.2 (2025-10-04) | 2026-10-17 | 7 | 95 / 19 | 385 / 10 / 1 (madsmtm 372) | MIT / Zlib-Apache-MIT | crate |
| uvc-util (jtfrey) | v1.2 (2021-04-25) | **2024-02-26** | 0 | 5 / 1 | 0 | MIT | CLI tool, ObjC |
| CameraController (itaybre) | v1.4.0 (**2022-05-05**) | 2025-04-13 (README only) | 0 | 42 / 2 | 0 | **GPL-3.0** | GUI app |
| uvcc (joelpurra, Node) | v8.0.0 tag | 2026-08-25 | — | 5 / 0 | 17 / 1 / 1 | GPL-3.0 | npm, libusb-based |
| PyO3 / maturin | 0.30.1 (2026-10-14) / 1.16.0 (2026-10-29) | 2026-11-02 | 25 / 44 | 299 / 114 | 551 / 76 / **3** | MIT/Apache | build tooling |
| libuvc (context only, needs a driver swap on Windows) | v0.0.9 (2026-10-29) | 2026-10-29 | 2 | 95 / 22 | 85 / 5 / 1 | BSD | — |

Sources: the snapshot JSON; PyPI pages (`https://pypi.org/project/<name>/`); `https://crates.io/crates/<name>`; GitHub repos at `https://github.com/<owner>/<repo>`; https://gitlab.freedesktop.org/camera/libcamera; https://gitlab.freedesktop.org/gstreamer/gstreamer; https://gitlab.gnome.org/GNOME/pygobject; `git ls-remote https://git.linuxtv.org/v4l-utils.git` (tags up to `v4l-utils-1.32.0`).

### 2.2 What each library provides (doc unless marked measured)

The first table covers the Windows column of each goal; the second covers Linux and macOS for the same libraries. In both tables **m** = measured on Gerald and **d** = doc/source. Cells read "W" = Windows, "L" = Linux, "M" = macOS.

**Windows**

| Library | G-ID | G-TS | G-MJPEG | G-CTRL |
|---|---|---|---|---|
| PyAV / FFmpeg | dshow alternative name = device path, opens by it (m) | synthesized, constant 333,333 per frame (m) | yes (m); Kiyo fell back to raw YUY2 on 10-25 (m) | none (d) |
| OpenCV videoio | index only; MSMF opens take 39–41 s (m) | no (m) | **no**: always decodes, `CONVERT_RGB=0` still BGR (m) | some `CAP_PROP_*`, readback only (m) |
| GStreamer | `mfvideosrc` `device-path` (m) | arrival time, 16 ms grid (m) | yes (m) | none on `mfvideosrc` (d) |
| SDL3 | name only (m) | 16 ms grid (m) | yes, 4/4 cameras incl. Kiyo (m) | **no control API**: `SDL_camera.h` has no control functions (d) |
| nokhwa | symlink exposed, opens by index (m) | 16 ms grid (m) | yes, but its format list hides MJPEG (m) | AVF/MF properties (d) |
| Qt Multimedia | opaque `QCameraDevice::id()` (d) | — | untested | `QCamera` exposure/focus/WB API, support only discoverable at runtime via `supportedFeatures()` (d) |
| duvc-ctl | DS device `path` + name (`core/types.h` L147–149) (d) | — | — | DS camera/video-proc properties + KS properties + Logitech vendor (d) |
| pygrabber / openpnp-capture | names / name+path (m) | dropped / none (m) | **no**: RGB24 (m) | openpnp API untested |

**Linux and macOS**

| Library | G-ID | G-TS | G-MJPEG | G-CTRL |
|---|---|---|---|---|
| PyAV / FFmpeg | L: device node only | L: kernel buffer time, `-ts default/abs/mono2abs` (`v4l2.c` L1165–1169) | L: yes (`input_format mjpeg`). M: **no**: video `codec_id` only RAWVIDEO/DVVIDEO (`avfoundation.m` L708–714) | none on any OS (d) |
| OpenCV videoio | L: index or path | L: V4L2 buffer time (d) | L: **yes**: raw buffer returned when `CONVERT_RGB` is false (`cap_v4l.cpp` 4.x L2111–2135). M: no | some `CAP_PROP_*` (d) |
| GStreamer | L: `device.bus_path`, serial (d) | L: V4L2 buffer time (d) | L: `image/jpeg` (d). M: **no JPEG caps** in `avfvideosrc` (d, SURVEY) | L: `v4l2src extra-controls` (d, `gstv4l2object.c` L473–482). M: none |
| SDL3 | name only | backend time | L: MJPG mapped (d). M: no MJPG mapping in CoreMedia (d, SURVEY) | **no control API** (d) |
| nokhwa | — | — | M: maps `kCMVideoCodecType_JPEG_OpenDML` to MJPEG (`nokhwa-bindings-macos/src/lib.rs` L370) | AVF properties via the deprecated `objc` / `cocoa-foundation` crates (d) |
| linuxpy | L: `bus_info` | L: `v4l2_buffer` timestamp; `META_CAPTURE` buffers supported (`linuxpy/video/device.py` L132, L297, L485) | L: yes | L: full V4L2 `Controls` (device.py L1033+) |
| libcamera (UVC pipeline) | L: port-based ID (d) | L: V4L2 buffer time, "\todo Use the UVC metadata" (`uvcvideo.cpp` L897) | L: via V4L2 formats | L: only Brightness, Contrast, Saturation, ExposureTimeMode, ExposureTime, AnalogueGain, Gamma. **No focus, no WB** (`uvcvideo.cpp` L701–720) |
| PyObjC AVFoundation + IOKit | M: `uniqueID` / `modelID`; locationID via IOKit (d) | M: CMSampleBuffer PTS, host clock (d) | M: **probably yes**: Chromium sets `kCVPixelBufferPixelFormatTypeKey = 'dmb1'` and receives MJPEG CMBlockBuffers, with one camera (Logitech 4K Pro) blocklisted (`video_capture_device_avfoundation.mm` L515–548, L1185) | M: AVFoundation has **no manual exposure duration or lens position on macOS**. `setExposureModeCustom(duration:iso:)` and `setFocusModeLocked(lensPosition:)` list iOS/iPadOS/Mac Catalyst/tvOS only (Apple docs). UVC control requests through IOKit are needed |
| uvc-util / CameraController / Chromium `uvc_control_mac.mm` | M: locationID + VID:PID (d) | — | — | M: UVC GET/SET_CUR through `IOUSBInterfaceInterface::ControlRequest` on the VC interface; no driver change (`uvc-util/src/UVCController.m` L833–938; Chromium `uvc_control_mac.mm` L257–367, opens the VC interface with `USBInterfaceOpen`) |

Sources:
- PyAV/FFmpeg: [FFmpeg `libavdevice/avfoundation.m`](https://github.com/FFmpeg/FFmpeg/blob/master/libavdevice/avfoundation.m), [`libavdevice/v4l2.c`](https://github.com/FFmpeg/FFmpeg/blob/master/libavdevice/v4l2.c).
- OpenCV: [`cap_v4l.cpp` (4.x)](https://github.com/opencv/opencv/blob/4.x/modules/videoio/src/cap_v4l.cpp).
- SDL3: [`SDL_camera.h`](https://github.com/libsdl-org/SDL/blob/main/include/SDL3/SDL_camera.h).
- libcamera: [`uvcvideo.cpp`](https://gitlab.freedesktop.org/camera/libcamera/-/blob/master/src/libcamera/pipeline/uvcvideo/uvcvideo.cpp).
- Chromium: [`video_capture_device_avfoundation.mm`](https://github.com/chromium/chromium/blob/main/media/capture/video/apple/video_capture_device_avfoundation.mm), [`uvc_control_mac.mm`](https://github.com/chromium/chromium/blob/main/media/capture/video/mac/uvc_control_mac.mm).
- Apple: [setExposureModeCustom](https://developer.apple.com/documentation/avfoundation/avcapturedevice/setexposuremodecustom(duration:iso:completionhandler:)), [setFocusModeLocked](https://developer.apple.com/documentation/avfoundation/avcapturedevice/setfocusmodelocked(lensposition:completionhandler:)), [videoSettings](https://developer.apple.com/documentation/avfoundation/avcapturevideodataoutput/videosettings).
- [uvc-util `UVCController.m`](https://github.com/jtfrey/uvc-util/blob/master/src/UVCController.m), [linuxpy `device.py`](https://github.com/tiagocoutinho/linuxpy/blob/master/linuxpy/video/device.py), [duvc-ctl](https://github.com/allanhanan/duvc-ctl).
- Measured cells: [README.md method comparison](../../../README.md), [REPORT.md](../../../REPORT.md) findings 1–5, [prior_art/SURVEY.md](../../../prior_art/SURVEY.md).

### 2.3 Notable findings per library

**Windows**
1. **FFmpeg's DirectShow demuxer has had no commit since 2024-10-17** (`dshow_pin.c` since 2024-03-30). That reads as "stable or orphaned". PyAV's DS path is therefore frozen code: no fix should be expected for the Kiyo raw-YUY2 fallback or for the synthesized timestamps. **doc (API snapshot)** + **measured** (Kiyo: SURVEY `prior_art_pyav_dshow-kiyo-720p`).
2. **GStreamer `sys/mediafoundation` has had 0 commits in 12 months** (last 2025-10-30; 7 of 10 two-year commits by one author). The pip bundle 1.28.8 cannot install on regular (non-free-threaded) CPython: `gstreamer-plugins` 1.28.8 ships only cp313t/cp314t Windows wheels. That matches SURVEY's resolver error on 3.12. **doc (PyPI listing)** + **measured** (SURVEY).
3. **duvc-ctl is the only maintained Python UVC-control package for Windows.** It covers DirectShow IAMCameraControl/IAMVideoProcAmp, KS properties and Logitech vendor units, and keys devices by DS path. But it is one author (46 of 51 commits), its repo is 15 months old, and it has wheels only for cp38–cp312 on win_amd64. It is a reference, or at most an optional dependency, not a foundation. **doc**.
4. **No maintained Python package wraps Media Foundation capture.** A web search found only pylightcam (RGB output) and Rust crates. MF native-MJPG plus UVC metadata must be new C++ (or Rust). pywin32 and comtypes do not declare the MF interfaces (capture_backends_review §2). **web** + **inferred**.
5. **windows-rs is in an API transition.** The `windows` umbrella crate has not been released since 0.62.2 (2025-10-06). The August 2026 newsletter says 0.100.0 "may initially publish… without `windows` and `windows-sys`" and tells libraries to generate bindings with `windows-bindgen` instead ([issue #4867](https://github.com/microsoft/windows-rs/issues/4867)). **doc**.

**Linux**

6. **The Rust `v4l` crate is effectively unmaintained** (last release 2023-05-12, last commit 2024-10-05, 15 open PRs). nokhwa's Linux backend depends on it. A Rust core would write its own ioctls on `rustix`/`nix` or use `v4l2r` (0.0.x). **doc (API snapshot)**.
7. **linuxpy is the only maintained Python V4L2 library.** It has 2 authors and 19 commits in 12 months, and it supports controls and `META_CAPTURE` metadata buffers. It is GPL-3.0-or-later, which is compatible with skellycam's AGPL-3.0 (`LICENSE`; GPLv3 §13). v4l2-python3 is "GPLv2", which, if GPLv2-only, cannot be combined with AGPL-3.0. v4l2py and pyv4l2 are dead. **doc** + **inferred** (license compatibility).
8. **libcamera's UVC pipeline is not a fit.** It exposes no focus and no white-balance controls, uses the V4L2 buffer timestamp (UVC metadata is a `\todo`), is still 0.x (v0.8.0 on 2026-11-01), and its Python bindings come only from distro packages. **doc**.

**macOS**

9. **No maintained macOS UVC-control library exists:**
   - uvc-util: last commit 2024-02-26, last release 2021.
   - CameraController: GPL-3 GUI app, last release 2022-05-05; issue #132 (2024-11-06) "Webcam controls do not work at all - iMac M1 - Sonoma 14.6.1" is open.
   - uvcc: Node, libusb.

   Chromium's BSD-licensed `uvc_control_mac.mm` (705 lines, maintained by Google) is the best reference to port. **doc** + **web** (issue).
10. **FFmpeg avfoundation and GStreamer avfvideosrc cannot output MJPEG**, so PyAV/GStreamer-everywhere fails G-MJPEG on macOS. Chromium's source shows that AVFoundation itself can deliver 'dmb1' MJPEG block buffers, so PyObjC can do it. That is still unmeasured here (`mjpeg/drafts/macos/avf_mjpeg_probe.py` has not run). **doc** + **inferred**.
11. **PyObjC is one maintainer** (Ronald Oussoren, 307 of 309 commits in 12 months), but it has shipped every macOS SDK for years: 13.0 targets the macOS 27 SDK and wheels cover cp311–cp315 universal2. There is no PyPI IOKit binding, so IOKit UVC control from Python means ctypes over CFPlugIn vtables or a small ObjC/C extension. **doc**.

**Platform and wheel facts that affect the choice**

12. **macOS 27 (Sept 2026) requires Apple silicon**; Tahoe 26 is the last Intel release ([TechRadar](https://www.techradar.com/computing/mac-os/its-official-your-intel-mac-wont-get-macos-27-with-macos-tahoe-26-marking-the-end-of-an-era), [9to5Mac 2026-05-18](https://9to5mac.com/2026/05/18/macos-27-will-drop-support-for-these-four-mac-models/)). PyAV's arm64 wheels need **macOS 14+**, opencv-python's need 13+ (x86_64: 14+), and PySide6's need 14+. On an arm64 Mac running macOS 12/13, PyAV 19 builds from source. **web** + **doc (PyPI tags)**.
13. **Python 3.11** (skellycam declares `requires-python >=3.11`, `pyproject.toml` L5): PyAV 19 dropped it, while PyObjC 13, pywin32 312 and OpenCV support it. duvc-ctl stops at 3.12, pupil-labs-uvc at 3.13. **doc**.

## 3. What no library gives: new code in every architecture

These must be written here whatever is chosen. **inferred**, from the capability table plus REPORT findings.

| Need | Why no library covers it | Reference size in this repo |
|---|---|---|
| Serial-else-port camera key on 3 OSes, mapped to the open path | Libraries expose a path, name or `uniqueID` at best (SURVEY goal 4); none computes a stable key | `naming/camera_identity.py` 260, `linux_identity.py` 223, `macos_identity.py` 201, `win_identity_dump.py` 711, `usbdesc.py` 474 |
| UVC PTS/SCR to host-clock mapping (G-TS) | Only Media Foundation (with the registry value) and the Linux metadata node expose raw headers; no library fits the clock; libcamera has it as a `\todo` | `timing/src/mf_uvc_timing.cpp` 386; `timing/linux/v4l2_uvc_timing.py` 1335 |
| MF native-MJPG capture with metadata | No Python MF wrapper exists; GStreamer, SDL3 and nokhwa drop the metadata | `mjpeg/msmf/mf_mjpeg_capture.cpp` 683 |
| Bandwidth-refusal handling (two cameras on one USB 2.0 hub) | No library surfaces it. Media Foundation fails at the first `ReadSample` with `0x800718CF`; DirectShow fails at open (capture_backends_review §3) | none yet |
| Kiyo-style control timeouts (`0x8007001F`) and open/close cycling | Device fault; every API fails the same way (PROGRESS.md) | none yet |
| macOS UVC controls | See §2.3 item 9 | Chromium `uvc_control_mac.mm` 705 (external) |

## 4. Architectures: third-party vs new code

Repo reference sizes, counted 2026-11-06 with `wc -l`:

| Folder | Lines |
|---|---|
| `mjpeg/msmf/` | 683 (C++) |
| `timing/src/` | 931 (C++, 6 files; `mf_uvc_timing.cpp` 386) |
| `naming/` | 4,678 total, about 2,300 excluding tests, workflows and the `orig_20261025/` copies |
| `mjpeg/drafts/` | 1,992 (`v4l2_mmap_mjpeg.py` 839, `avf_mjpeg_probe.py` 639) |
| `timing/linux/` | 1,395 |
| `timing/macos/` | 226 |
| Rust in `rust/`, not vendored | 2,993 (`uvc_iso` about 1,800) |
| Current skellycam `core/camera/` | 1,746 |

LOC = lines of code. The estimates below are **inferred**: drafts scaled by about 1.3–2x for error handling, async reading, all-format enumeration and tests.

### A. Python + per-OS native APIs (recommended)

| OS | Third-party (run time) | Third-party (build) | New code |
|---|---|---|---|
| Windows | none required; optional PyAV DirectShow fallback | pybind11 (bf50 = 2) or nanobind (bf50 = 1); MSVC; Windows SDK | C++ extension 1,800–2,500 covering: MF enumerate/open by symlink, native-MJPG mode list, async `IMFSourceReaderCallback` + watchdog, UVC metadata parse, `IAMCameraControl`/`IAMVideoProcAmp` obtained from the MF source, error mapping. Python identity via ctypes cfgmgr32/SetupAPI 600–900 |
| Linux | none required (ctypes ioctls); optionally linuxpy (GPL-3) | — | V4L2 mmap capture + metadata node + controls 1,200–1,800 Python (drafts total 2,174); sysfs identity 250 |
| macOS | PyObjC (AVFoundation, CoreMedia) | clang for a small IOKit extension | AVFoundation 'dmb1' capture 600–900 PyObjC; IOKit UVC control 700–1,000 ObjC/C (port of Chromium's 705); identity 200 |
| Shared | — | cibuildwheel-style CI | Clock fit, frame model, open/close cycling, bandwidth and Kiyo handling 800–1,200 |
| **Total** | **1 run-time library (PyObjC, macOS only)** | 1 binding library | **about 6–9 kLOC**, of which about 4 kLOC already exists as drafts or harness code |

**Risk:** most of the code sits on the OS APIs (Microsoft, kernel, Apple), whose stability is best in class. The main third-party risk is PyObjC's bus factor of 1, mitigated by its 20-year track record and the option to drop to ctypes or ObjC for the few AVFoundation calls. **inferred**.

### B. PyAV/FFmpeg everywhere plus control side channels

| OS | PyAV covers | Gaps that need new code |
|---|---|---|
| Windows | G-MJPEG (DirectShow, measured), G-ID (DS path, measured) | G-TS: DS times are synthesized, so MF + UVC metadata is still needed (A's C++ minus about 30%). G-CTRL: comtypes IAMCameraControl 300–500, or duvc-ctl (Python ≤3.12 wheels). Kiyo: raw-YUY2 fallback |
| Linux | G-MJPEG, kernel timestamp | UVC metadata node (not in FFmpeg) 400–700; controls 200–400; identity 250 |
| macOS | nothing usable: the demuxer emits only RAWVIDEO/DVVIDEO | All of A's macOS code |

- **Total:** about 4.5–6.5 kLOC new code plus PyAV (bf50 = 1, drops Python versions quickly: 3.11 dropped in v19.0.0), riding on FFmpeg device code. On Windows that device code has been untouched for two years.
- **Net:** B saves only about 1.5–2.5 kLOC against A, adds a frozen dependency on the Windows data path, and still fails G-TS on Windows and G-MJPEG on macOS unless A's native pieces are added. **inferred**.

### C. Rust core (windows-rs MF, own V4L2 ioctls, objc2 AVFoundation + IOKit) with PyO3

| Part | Third-party | New code |
|---|---|---|
| Windows | `windows` crate (umbrella frozen at 0.62.2, being replaced by `windows-bindgen`) | MF + metadata + controls 2,000–3,000 Rust |
| Linux | `rustix`/`nix` (healthy); **not** the `v4l` crate (stale) | V4L2 + metadata + controls 1,500–2,000 |
| macOS | objc2, objc2-av-foundation, objc2-io-kit (bf50 = 1, madsmtm; framework crates last released 2025-10-04) | AVFoundation + IOKit UVC control 1,800–2,500 |
| Binding / build | PyO3 (bf50 = 3, 76 authors) and maturin, both very healthy | 400–600 PyO3 glue; CI for 6 wheel targets |
| **Total** | 4–6 crates | **about 7–10 kLOC Rust** (the repo's `uvc_iso` and `nokhwa_probe` are about 2.4 kLOC of prior Rust experience) |

- **Forking nokhwa instead** would mean adopting about 15 kLOC of Rust (548 KB, GitHub languages API) from a 1-author project with 4 commits in 12 months. Its macOS backend uses the deprecated `objc`/`cocoa-foundation`/`core-media-sys` crates, and on Windows it hides MJPEG and opens cameras by index. That is not recommended. **doc** + **measured** (README nokhwa row).
- **Net:** C has the same new-code volume as A, one language, and memory safety. It adds churn exposure (windows-rs 0.100 transition, objc2 0.x) and makes contributors learn Rust. Choose it only if a Rust capture core is wanted for other reasons. **inferred**.

### Summary

| | A (Python + native) | B (PyAV + side channels) | C (Rust + PyO3) |
|---|---|---|---|
| New code | 6–9 kLOC (about 4 k drafted) | 4.5–6.5 kLOC | 7–10 kLOC |
| Third-party on the data path | none (Windows, Linux); PyObjC (macOS) | PyAV + FFmpeg avdevice on Windows and Linux | windows-rs, objc2 |
| Single-maintainer run-time dependencies | PyObjC | PyAV (+ duvc-ctl if used) | objc2 (+ nokhwa if forked) |
| Meets all four goals without more native code | yes, by design | **no** (Windows G-TS, macOS G-MJPEG, G-CTRL everywhere) | yes, by design |
| Biggest dependency risk | PyObjC bus factor | frozen dshow demuxer; PyAV dropping Python versions | windows-rs API transition |

## 5. Implications for the test plan

These tests check the dependencies chosen above, not the goals themselves.
- **macOS:** run `mjpeg/drafts/macos/avf_mjpeg_probe.py` with `kCVPixelBufferPixelFormatTypeKey='dmb1'` (Chromium's method), not only an empty `videoSettings`, on all four cameras. That decides whether PyObjC alone meets G-MJPEG. Then exercise IOKit `ControlRequest` for exposure, focus and WB on Apple silicon (macOS 26 and 27). Issue #132 suggests it may fail on some Macs.
- **Windows:** check that `IAMCameraControl` QueryInterfaced from the `IMFMediaSource` sets (not just reads back) exposure and focus on each camera, so A needs no DirectShow side channel. Run the PyAV DirectShow Kiyo test again, since the raw-YUY2 fallback lives in a demuxer nobody is maintaining.
- **Linux:** compare linuxpy against the repo's ctypes drafts on Ubuntu and Fedora, both for capture plus the metadata node and for controls. That decides whether to take a GPL-3 single-maintainer dependency or keep the about 1.5 kLOC of ctypes.
- **Packaging smoke test (no camera):** install the chosen stack on Python 3.11–3.14 for win_amd64, win_arm64, macOS arm64 (14 and 12/13) and manylinux x86_64/aarch64. PyAV 19 has no 3.11 wheels and no macOS 12/13 arm64 wheels.

## Verifier notes

Adversarial check, 2026-11-06. No camera was opened or enumerated. I re-checked the claims with `gh api` (GitHub REST), the PyPI and crates.io JSON APIs, the GitLab API, Apple's documentation JSON (`developer.apple.com/tutorials/data/documentation/...json`), and source files fetched from upstream master/main. Where a verdict says "confirmed with a note", the facts hold but the note narrows the implication.

### Verdict table

| ID | Verdict | Evidence / correction |
|---|---|---|
| D1 | confirmed | `gh api repos/PyAV-Org/PyAV/commits?since=2025-11-06`: WyattBlue 343, lgeiger 20 (out of 416). |
| D2 | confirmed with a note | PyPI `av` 19.0.2 has `requires_python >=3.12` and the wheel list matches. CHANGELOG.rst L85 says "Drop support for Python 3.11". **Note:** on Python 3.11, pip and uv quietly resolve to PyAV 18.x (`requires_python >=3.11`, uploaded 2026-07-02), so 3.11 gets an older PyAV rather than a source build. The source-build case applies only to arm64 macOS 12/13 on 3.12+. |
| D3 | confirmed with a note | dshow.c last commit 2024-10-17 ("fix unused variable warning"); dshow_pin.c 2024-03-30; v4l2.c and avfoundation.m counts match. **Note:** nobody has shown that the Kiyo raw-YUY2 fallback is a demuxer bug (it could be device negotiation), so "no fix expected" is inferred. PyAV 19.0.2 bundles **FFmpeg 9.0.2** (`scripts/activate.sh` at v19.0.2: `PYAV_LIBRARY=ffmpeg-9.0.2`), not "8.x" as the §2.1 table says. |
| D4 | confirmed | avfoundation.m master L708 `AV_CODEC_ID_RAWVIDEO`, L714 `AV_CODEC_ID_DVVIDEO`; no other video codec_id. |
| D5 | confirmed | v4l2.c options include `ts default/abs/mono2abs`, and there is no `VIDIOC_S_CTRL`, `V4L2_CID_*` or META buffer handling in the file. |
| D6 | confirmed with a note | cap_v4l.cpp 4.x L2111–2138 plus `initFrameNonBGR` default case L2077–2093 (1×bytesused Mat). **Note:** cap_msmf.cpp also has a raw path: with `CONVERT_RGB=0` it copies the buffer as `Mat(1, cursize)` (L1971–1974). The repo measured NV12 from it, not JPEG (mjpeg/RESULTS.md L131), because OpenCV picks the native type by resolution and fps only (`VideoIsBetterThan`), never by subtype. "Always decodes" is therefore true in practice (measured), not by design. |
| D7 | confirmed with a note | OpenCV release 5.1.0 published 2026-11-06T09:58Z; cap_msmf.cpp has 11 commits by 11 distinct authors since 2024-11-06. **Note:** the 4.x line is still released (**4.14.0, 2026-07-19**), so skellycam's 4.12 pin is two minor versions behind. |
| D8 | **weakened** | The plugin facts are right: last mediafoundation commit 2025-10-30 (tbeloqui), and `gstreamer-plugins` 1.28.8 has only cp313t/cp314t win32/amd64 wheels. But this gap is **specific to 1.28.8**. 1.28.0, 1.28.6 and 1.28.7 all ship `cp39-abi3` win_amd64/win32 and macOS universal2 wheels, `gstreamer-libs` 1.28.8 still has abi3 wheels, and SURVEY L40–42 shows 1.28.7 installed and ran. "Broken pip install on regular CPython" should read "1.28.8 cannot install; pin 1.28.7". "No Linux wheels" is confirmed. |
| D9 | confirmed | SDL_camera.h main lists 17 functions (driver, list, formats, name, position, open, permission, ID, properties, acquire/release, close) and no control functions. The camera ID is a session `SDL_CameraID` plus a name. |
| D10 | confirmed | The repo now resolves as `l1npengfih/nokhwa` (renamed; the commit author is `l1npengtul`). 4 commits since 2025-11-06, last 2026-04-13; crates.io 0.10.11 on 2026-05-15. `nokhwa-bindings-macos/Cargo.toml` depends on `objc 0.2`, `cocoa-foundation 0.1` and `core-media-sys 0.1`. Open issues are 67 including PRs, which is consistent with 57/10. |
| D11 | confirmed | My own web search (2026-11-06) also found no PyPI wrapper for `IMFSourceReader`. The hits were Rust crates only: `moq-video`, `openlogi-camera`, `bevy_iroh`. This is an absence-of-evidence claim, so the "web" label is correct. |
| D12 | confirmed with a note | PyPI duvc-ctl 2.1.0 (2026-07-23, MIT): wheels for cp38–cp312 win_amd64 only. Repo created 2025-08-11; allanhanan 46 of 51 commits. **Note:** an sdist is also published, so 3.13+ can build it from source with MSVC. |
| D13 | confirmed with a note | pygrabber 0.2 uploaded 2023-10-20. openpnp-capture's "6 commits in 12 months" all landed 2025-11-11..13 (vonnieda), so it has been dormant for about 12 months. |
| D14 | confirmed | crates.io `windows` latest 0.62.2 (2025-10-06). Issue #4867 ("Rust for Windows - August 2026", 2026-09-02) says "We may initially publish the release without `windows` and `windows-sys`" and tells libraries to use `windows-bindgen`. **Note:** `windows-core` and `windows-bindgen` **0.100.0 were already published on 2026-09-03**, so the recommended bindgen path exists today. |
| D15 | confirmed | crates.io `v4l` 0.14.0 (2023-05-12); libv4l-rs last commit 2024-10-05; 15 open PRs (search API). |
| D16 | confirmed | madsmtm 372 commits since 2025-11-06; objc2-av-foundation and objc2-io-kit 0.3.2 (2025-10-04); objc2 0.6.5 (2026-10-05). |
| D17 | confirmed | changelog.rst "Version 13.0 … Framework bindings updated for macOS 27 SDK". PyPI pyobjc-framework-AVFoundation 13.0 (2026-10-30), `requires_python >=3.11`, universal2 cp311–cp315 (plus t variants). ronaldoussoren 307 of 309. |
| D18 | confirmed | `https://pypi.org/pypi/pyobjc-framework-IOKit/json` and `-IOUSBHost/json` both return HTTP 404. |
| D19 | confirmed with a note | Apple doc JSON platforms for `setExposureModeCustom(duration:iso:…)`, `setFocusModeLocked(lensPosition:…)` and also `setWhiteBalanceModeLocked(with:…)`: iOS, iPadOS, Mac Catalyst 14.0, tvOS 17.0; **no macOS**. **Note:** `exposureMode`, `focusMode` and `whiteBalanceMode` **are** available on macOS 10.7+, so tier 0 can lock or auto these without IOKit, but cannot set manual values. |
| D20 | **weakened** | The method is right (IOKit plug-in, then `USBInterfaceOpen` at uvc_control_mac.mm L367, then control requests), but the citations are off. L130–169 are only the control bit-index tables, and the actual `ControlRequestTO` calls are in **uvc_control_mac.h L154 and L195** (225 lines), not in the .mm. The template is therefore about 930 lines (705 + 225), not 705. The Chromium file is still maintained (last commit 2026-10-30, "Fix unsafe buffer usage in UvcControl"). uvc-util `ControlRequest` at UVCController.m L938 is confirmed. |
| D21 | **weakened** | The dates are right (uvc-util last commit 2024-02-26; CameraController v1.4.0 2022-05-05). But **issue #132 is about the built-in FaceTime HD camera** of an iMac ("The camera is built-in to the iMac, not an external"), and a commenter quotes the developer: "It is normal for built-in cameras to not work". It is **not** evidence that IOKit UVC control fails on Apple silicon/Sonoma for USB cameras. The relevant evidence is **issue #138** (2024-12-12): a Razer Kiyo (1532:0E03, the non-Pro) shows all controls greyed out on an M4 Mac mini, while another user reports the same Kiyo working on an M2 MacBook Pro. Issue #142 (2025-11-07) reports CameraController zoom working on a Dell WB7022. |
| D22 | confirmed | video_capture_device_avfoundation.mm: L60–62 `kModelIdLogitech4KPro` = "UVC Camera VendorID_1133 ProductID_2175"; L515–524 MJPEG workaround; L545 `kCVPixelBufferPixelFormatTypeKey : @(best_fourcc)`; L302–304 'dmb1' = `kCMVideoCodecType_JPEG_OpenDML`; L1185 MJPEG arrives as a block buffer. |
| D23 | confirmed | linuxpy device.py L132 `BufferType.META_CAPTURE`, L297 META format handling, L1033 `class Controls(dict)`. PyPI 0.25.0 (2026-08-20), `GPL-3.0-or-later`. Commits: tiagocoutinho 16, mgineer85 3. |
| D24 | confirmed | PyPI: v4l2py 3.0.0 (2024-03-11, GPL-3.0-or-later); pyv4l2 1.0.2 (2016-08-29; its metadata contradicts itself: LGPLv3 text with a BSD classifier); v4l2-python3 0.3.5 (2024-08-27), license field "GPLv2" with an unversioned GPL classifier. Whether it is GPLv2-only is still undetermined. |
| D25 | confirmed | uvcvideo.cpp master (907 lines): CIDs at L333–345 and L701–719 are BRIGHTNESS, CONTRAST, SATURATION, EXPOSURE_AUTO, EXPOSURE_ABSOLUTE, GAIN, GAMMA; L897 "\todo Use the UVC metadata to calculate a more precise timestamp". Tag v0.8.0 dated 2026-11-01. |
| D26 | confirmed | gstv4l2object.c L472–484 `extra-controls` (since 1.2). gstmfvideosrc.cpp properties are only device-path, device-name, device-index and dispatcher. |
| D27 | confirmed | REPORT.md finding 4 (E_INVALIDARG on every acquire with MJPG). The failure is in Windows' MediaFrameReader, not in pywinrt itself. |
| D28 | confirmed | Multiple outlets (TechRadar, MacRumors 2026-06-03/06-08, Tom's Hardware) say macOS 27 is Apple-silicon only and Tahoe 26 is the last Intel release. |
| D29 | confirmed | `wc -l`: mf_mjpeg_capture.cpp 683; timing/src 931 (mf_uvc_timing.cpp 386); v4l2_mmap_mjpeg.py 839 + v4l2_uvc_timing.py 1,335 = 2,174; avf_mjpeg_probe.py 639 + avf_timing.py 189 = 828; skellycam/core/camera 1,746; naming .py excluding orig/tests 2,462. |
| D30 | weakened | This is an inferred estimate. The "about 4 kLOC already exists" is mostly test harnesses and probes (for example, mf_mjpeg_capture.cpp is a CLI harness), not library-shaped code. The macOS IOKit port should be sized against about 930 lines of Chromium (see D20). The ranges are plausible but should not be read as drafted production code. |
| D31 | confirmed | The reasoning holds: B fails macOS G-MJPEG (D4) and Windows G-TS (measured). An extra point against B on Linux: FFmpeg master commit 2026-10-20 "avdevice/v4l2: copy compressed frames out of the mmap buffers" fixes an **out-of-bounds read on compressed (MJPEG) packets** (no input padding). It is not in FFmpeg 9.0.2, so PyAV 19.0.2's Linux MJPEG path carries it until the next release. |
| D32 | weakened | The dependency list is right, but "binding churn" is overstated. Microsoft's own guidance is to generate the needed MF bindings locally with `windows-bindgen`, which reached 0.100.0 on 2026-09-03. That route insulates a Rust core from the umbrella crate's transition. Rust MF capture references exist (`moq-video`, `openlogi-camera`, `bevy_iroh` on docs.rs). |
| D33 | confirmed with a note | It still holds for "all three OSes". But FFmpeg master commit c2802e52 (2026-08-02) adds avfoundation `-video_device_id serial:<USB serial>` / `uid:<uniqueID>`, resolving the serial to the current locationID through IOKit. It is **not in FFmpeg 9.0/9.0.2**, so PyAV 19.0.2 lacks it. Its commit message also says that AVFoundation's `uniqueID` embeds the locationID, "which can be reassigned on reboot or replug". That is relevant to the macOS G-ID key design. |

### Corrections to the direct answers

1. **macOS control (answer 3):** drop CameraController #132 as evidence against IOKit control; it concerns a built-in FaceTime camera. Cite #138 instead: Kiyo (non-Pro) controls are greyed out on an M4 Mac mini but work on an M2. That makes the Kiyo family a priority for MAC-CTRL-IOKIT on more than one Apple-silicon generation.
2. **GStreamer (answer 2 caveats):** only the 1.28.8 `gstreamer-plugins` release lacks regular-CPython wheels; 1.28.7 installs and ran (SURVEY). The core-dependency rejection still stands on other grounds (idle MF plugin, no Linux wheels, no MF or AVF control API).
3. **PyAV:** the bundled FFmpeg is 9.0.2. On Python 3.11, resolvers fall back to PyAV 18.x automatically, so the open question "must PyAV be pinned below 19" answers itself; the real question is whether 18.x (FFmpeg 8.x) behaves the same on the dshow path.
4. **Open question 2:** reword it. The real risk is that `USBInterfaceOpen` on the VC interface returns `kIOReturnExclusiveAccess` while the camera streams. uvc-util treats that as usable and still sends `ControlRequest` (UVCController.m L1309–1317), while Chromium aborts on any non-success (uvc_control_mac.mm L366–371). The macOS control test should record that return code and try both behaviours.
5. **OpenCV on Windows:** "always decodes" is a measured outcome (NV12 from MSMF's raw path), not a code-level impossibility. That does not change the rejection.

### Missed items

- FFmpeg avfoundation serial/uniqueID device selection (master c2802e52, 2026-08-02; not in 9.0.x). https://github.com/FFmpeg/FFmpeg/commit/c2802e520a08dbf0c939ec8b5653b29dfd886427
- PyAV 19.0.2 bundles FFmpeg 9.0.2. https://github.com/PyAV-Org/PyAV/blob/v19.0.2/scripts/activate.sh
- FFmpeg v4l2 MJPEG out-of-bounds read fix, post-9.0.2. https://github.com/FFmpeg/FFmpeg/commits/master/libavdevice/v4l2.c (2026-10-20)
- CameraController #138: Razer Kiyo controls greyed out on M4, working on M2. https://github.com/itaybre/CameraController/issues/138
- uvc-util `kIOReturnExclusiveAccess` tolerance versus Chromium's strict open. https://github.com/jtfrey/uvc-util/blob/master/src/UVCController.m L1309–1317 and https://github.com/chromium/chromium/blob/main/media/capture/video/mac/uvc_control_mac.mm L366–371
- Chromium `ControlRequestTO` lives in uvc_control_mac.h L154/L195. https://github.com/chromium/chromium/blob/main/media/capture/video/mac/uvc_control_mac.h
- AVFoundation macOS exposure, focus and WB *mode* properties (auto/lock) are available on macOS 10.7+. Apple doc JSON for `exposureMode`, `focusMode`, `whiteBalanceMode`.
- OpenCV MSMF raw `CONVERT_RGB=0` path chooses its native subtype by size and fps only. https://github.com/opencv/opencv/blob/4.x/modules/videoio/src/cap_msmf.cpp L1144–1175, L1971–1974
- gstreamer-plugins 1.28.7 has abi3 wheels; only 1.28.8 regressed. https://pypi.org/project/gstreamer-plugins/1.28.7/#files
- OpenCV 4.14.0 (2026-07-19) on the 4.x line. https://github.com/opencv/opencv/releases/tag/4.14.0
- windows-bindgen and windows-core 0.100.0 published 2026-09-03. https://crates.io/crates/windows-bindgen
