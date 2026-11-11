# Linux plan input: versions, uvcvideo changes, and the test suite (2026-11-06)

Topic agent: **linux**. Read-only research; no camera was opened, streamed or listed.
Brief: G-ID, G-TS, G-MJPEG, G-CTRL on Ubuntu and Fedora KDE Plasma Edition, with **no driver change**
(no unbind/rebind, no detach, no driver replacement). Driver configuration such as module parameters is
reported separately as **tier 1 (one-time admin config)**; everything else is **tier 0 (zero-touch)**.

Labels: **measured** (repo result file), **doc** (vendor docs or source code, with URL and line), **web**
(forum, issue, news), **inferred** (my reasoning).

Kernel source used: torvalds/linux master at **v7.4-rc1** (fetched 2026-11-06 from
`https://raw.githubusercontent.com/torvalds/linux/master/drivers/media/usb/uvc/`), plus tag **v6.8** for
comparison. Line numbers below refer to master at that fetch. "First in vX" means the first mainline tag
containing the commit; I checked this with the GitHub compare API (`compare/<tag>...<sha>` returning
`behind`/`identical`). Distro kernels may carry backports, so a fix missing from the upstream version can
still be in a distro kernel, and the reverse.

---

## 0. Bottom line

- **No Linux route needs a driver change for any of the four goals.** The in-kernel `uvcvideo` driver,
  used through plain V4L2 ioctls, gives native MJPEG (G-MJPEG), the UVC PTS/SCR per payload through the
  metadata node (G-TS), stable sysfs/udev identities (G-ID) and UVC controls (G-CTRL). All of it works
  without root for a desktop user (logind `uaccess` ACL). **(doc + inferred; nothing measured on Linux
  yet.)**
- **The libusb/libuvc streaming route is out under the brief** (it detaches `uvcvideo`). The bandwidth
  draft `bandwidth/linux/uvc_bw_probe.py compare` **unbinds and rebinds `uvcvideo`**, which the brief
  forbids; it must use a physical replug instead.
- **The kernel versions in support span 6.8 → 7.3, and uvcvideo behaviour changed a lot in that range**
  (error frames, metadata, hardware timestamps, power management). So the test matrix is chosen by
  kernel, not by distro name: **6.8, 7.0, 7.2 (and 7.3)**.
- **Bandwidth on Linux behaves like Windows:** uvcvideo takes the camera's `dwMaxPayloadTransferSize` and
  picks the smallest alt setting that fits, so two of these cameras on one USB 2.0 hub get `ENOSPC` at
  `VIDIOC_STREAMON`. Without changing anything, the only fix is to pick another mode.
  `quirks=128` (tier 1) still does not touch MJPEG in v7.4-rc1, and it **replaces** every per-device quirk,
  including the C922's timestamp quirk.

---

## 1. Supported releases and kernels (as of 2026-11-06)

| Release | Released | Kernel (now) | Desktop | Support | Source |
|---|---|---|---|---|---|
| Ubuntu 24.04 LTS, GA kernel | 2024-04 | **6.8** | GNOME | standard to 2029 | web: [Phoronix 24.04.5](https://phoronix.com/news/Ubuntu-24.04.5-LTS) |
| Ubuntu 24.04.5 LTS, HWE (desktop default) | 2026-09-10 | **7.0** | GNOME | HWE 7.0 is the last 24.04 HWE kernel | web: [Phoronix](https://phoronix.com/news/Ubuntu-24.04.5-LTS), [OMG! Ubuntu](https://www.omgubuntu.co.uk/2026/09/ubuntu-24-04-5-lts-released-with-linux-kernel-7-0) |
| Ubuntu 26.04 LTS "Resolute Raccoon" | 2026-04-23 | **7.0** | GNOME 50 | LTS | web: [Ubuntu Discourse](https://discourse.ubuntu.com/t/26-04-lts-resolute-raccoon-shipping-with-the-final-7-0-linux-kernel/80838), [CNX](https://www.cnx-software.com/2026/04/24/ubuntu-26-04-lts-resolute-raccoon-released-with-linux-7-0/) |
| Ubuntu 26.10 "Stonking Stingray" | 2026-10-15 | **7.3** | GNOME 51 | 9 months, to Jul 2027 | web: [Phoronix](https://phoronix.com/news/Ubuntu-26.10-Released) |
| Ubuntu 25.10 | 2025-10 | 6.17 | — | **EOL Jul 2026** (9-month interim) | inferred |
| Ubuntu 22.04 LTS (HWE) | 2022-04 | 6.8 HWE | GNOME | standard support ends Apr 2027 | inferred; covered by the 6.8 leg |
| Fedora 43 KDE | 2025-10 | **7.2.10** (rebased) | Plasma 6.x | **EOL early Dec 2026** | web: [FEDORA-2026-bc7bd292d6](https://linuxsecurity.com/advisories/fedora/fedora-43-kernel-2026-bc7bd292d6) |
| Fedora 44 KDE | 2026-04-28 | shipped 6.19.14, now **7.2.13** | Plasma 6.6 | to ~mid 2027 | web: [Linuxiac](https://linuxiac.com/fedora-44-officially-released-this-is-whats-new/), [FEDORA-2026-e4c3989fea] |
| Fedora 45 KDE | **2026-11-03** | **7.2.15** | Plasma 6.8 | current | web: [Phoronix](https://phoronix.com/news/Fedora-45-Ships-Next-Week), [Warp2Search](https://www.warp2search.net/story/fedora-linux-45-officially-released-gnome-51-linux-72-kernel-and-breaking-changes/) |
| Mainline | 7.3 released 2026-10-18 | 7.4-rc1 | — | — | web: [LWN](https://lwn.net/Articles/1101143/) |

Fedora moves every supported release to the newest stable kernel series, newest release first
(doc: [Fedora KernelRebases wiki](https://fedoraproject.org/wiki/KernelRebases)). So Fedora 43, 44 and
45 all run 7.2.x now and will move to 7.3.x within weeks **(inferred)**. Kernel-wise, testing one Fedora
release covers all three; the releases differ only in Plasma, PipeWire and WirePlumber versions.

---

## 2. uvcvideo changes that matter, by kernel version

| First in | Commit | Change | Goal |
|---|---|---|---|
| ≤6.8 | 323666d1b323 | Picks the **first** smallest alt setting that is large enough (matches Windows 10 behaviour) | BW |
| 6.10 | 3de6df64f92d | Adds the `UVC_QUIRK_DISABLE_AUTOSUSPEND` mechanism (Insta360 Link) | CTRL/PM |
| **6.11** | 9183c6f1a21e | **`UVC_QUIRK_INVALID_DEVICE_SOF` for Logitech C922 (046d:085c)**: "C922 internal SOF does not increase at a stable rate of 1kHz"; the driver uses host SOF in its place | **TS** |
| 6.11 | 85fbe91a7c92 | Same quirk for C920 | TS |
| 6.11 | 53d7995383fa, 6243c83be6ee, 141270bd95d4, 8676a5e796fa | hwtimestamps: slow-fps rollover fix, updates before the clock buffer is full, integer overflow fix | TS |
| 6.11 | 9e3d55fbd160 | FIX_BANDWIDTH maths fixed for USB 3.x (still uncompressed formats only) | BW |
| **6.14** | 52fbe173baa4, 87ce177654e3 | **`nodrop` default inverted to 1, and the error is now propagated**: corrupt frames now reach userspace with `V4L2_BUF_FLAG_ERROR` (before: silently re-queued, leaving a sequence gap) | MJPEG |
| 6.14 | d6b874ff9ce2, d9fecd096f67 | Control cache flushed on a status event; async-control fh fixes | CTRL |
| **6.16** | a32d9c41bdb8, d1b618e79548 | **Granular power management**: the camera is powered per ioctl or while streaming, no longer just because an fd is open | CTRL/Kiyo |
| 6.16 | 9764401bf6f8 | Clamps a nonsense `dwMaxPayloadTransferSize` (Alcor) | BW |
| **6.17** | 2ab4019aa34d, 6cb786f040ad | New metadata format **`V4L2_META_FMT_UVC_MSXU_1_5`** (full payload header), turned on automatically when the device implements MSXU_CONTROL_METADATA | TS |
| 6.18 | 0aa0b0326cc5 | eUSB2 double-isochronous bandwidth support | BW |
| **7.0** | 27ccc44a511b + revert 17526c7e69d0 | Removing `nodrop` was reverted because Zoom cannot handle error frames; the parameter stays but is deprecated | MJPEG |
| 7.0 | 40d3ac25c113 | Off-by-one fix: URB allocation failed for frames ≤ one packet | MJPEG (small modes) |
| 7.0 | 4cf3b6fd54eb | Returns queued buffers when start_streaming fails. The commit cites `while :; do yavta -c3 /dev/video0; done` ending in "xHCI HC died" | **open/close reliability** |
| **7.0** | 8b7a42ecdcde (USB core) | **`USB_QUIRK_NO_LPM` for Razer Kiyo Pro 1532:0e05** (Cc stable) | **Kiyo** |
| **7.1** | 2ac27db04608 | Metadata buffer size can be raised through `S_FMT` (it was hard-coded at 10 KiB) | TS |
| **7.2** | edc1917599c5, 1719d78f832d, ede7de6e6b3d, ba649fff36c1, 0491c93a510c | hwtimestamps: dev_sof filtering fixed (it was broken under INVALID_DEVICE_SOF), relaxed interpolation window, no jumping between SW and HW timestamps, ignores small-SOF-delta samples | TS |
| 7.2 | a15b773fe4ff | **No partial metadata buffers** (the first meta buffer could be partial) | TS |
| 7.2 | f078966ca1fb, 2f24ac8dd879 | **Sequence numbers corrected** when there is no EOF and across frame gaps (so frame-drop detection from `sequence` was wrong before) | MJPEG/TS |
| 7.2 | 6d27f92c54ce | Deadlock fix when `uvc_status_stop` is called from async control work | CTRL |
| 7.3 | — | No uvcvideo commits | — |
| 7.4-rc | 40446ee73a65 etc. | INVALID_DEVICE_SOF for C925e; control parsing bounds | — |

Device quirks in master (`uvc_driver.c` device table):
- **C922 046d:085c**: `UVC_QUIRK_INVALID_DEVICE_SOF` (lines ~2713–2720).
- **C930e 046d:0843** and **generic 4C4A:4A55**: no entries.
- **Razer Kiyo Pro 1532:0e05**: no uvcvideo entry. Its only quirk is the USB-core `NO_LPM` entry in
  `drivers/usb/core/quirks.c`.

(doc: [uvc_driver.c](https://github.com/torvalds/linux/blob/master/drivers/media/usb/uvc/uvc_driver.c),
commit [8b7a42ecdcde](https://github.com/torvalds/linux/commit/8b7a42ecdcdeb55580d9345412f7f8fc5aca3f6c))

### Kiyo Pro on Linux

The NO_LPM commit message describes the Windows symptom almost exactly: "the device can enter a state
where it fails to respond to control transfers, producing EPIPE (-32) errors on UVC probe control SET_CUR
requests … [worst case] the host controller [is] declared dead and every USB device on the bus [is]
disconnected". It cites Launchpad bug 2061177 (Ubuntu 22.04, kernel 6.5; the log shows "Failed to set UVC
commit control : -110" and "xHCI host not responding to stop endpoint command") (doc + web:
[LP#2061177](https://bugs.launchpad.net/ubuntu/+source/linux/+bug/2061177)).
- **Kernels 7.0 and later have the fix:** Ubuntu 26.04, 24.04.5 HWE, 26.10 and every Fedora release.
- **Ubuntu's 6.8 GA kernel** has it only if Canonical picked up the stable backport. This is unknown, so
  test it.
- **Tier 1 on a kernel without it:** `usbcore.quirks=1532:0e05:k` on the kernel command line
  (`k` = NO_LPM), or write that value to `/sys/module/usbcore/parameters/quirks` as root and replug.
- **Tier 0 check:** read `/sys/bus/usb/devices/<kiyo>/power/usb3_hardware_lpm_u1` and `…_u2`, which
  show whether LPM is enabled.
- This is a strong lead for Windows too: the 0x8007001F failure may be the same LPM firmware bug.
  **(inferred)**

---

## 3. G-TS on Linux

**Default buffer timestamp (doc):**
- `uvc_queue.c:250-251` sets `V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC | V4L2_BUF_FLAG_TSTAMP_SRC_SOE`.
- `uvc_video.c` (`uvc_video_decode_start`, ~line 1271) stamps `ktime_get()` (CLOCK_MONOTONIC, or
  realtime with `clock=realtime`) when the FID toggles. That happens while processing the URB that
  carries the frame's **first payload**.
- **"SOE" means "first bytes processed", not start of exposure.**

**Expected granularity (inferred from source):**
- Isochronous URBs hold up to `UVC_MAX_PACKETS` = 32 packets (`uvcvideo.h:56`).
- At high speed that is 32 × 125 µs = **4 ms per URB completion**, so the SOE stamp should be quantised to
  about 4 ms (σ ≈ 1.15 ms if uniform) plus scheduling jitter.
- That beats the 16 ms grid measured on Windows (REPORT finding 7) but is still far from the PTS path.
  To be measured.

**`hwtimestamps=1` (tier 1) (doc):**
- The parameter is `module_param_named(hwtimestamps, …, 0644)` (`uvc_driver.c:2484`). Root can change it
  at runtime with no reload, and it is checked on every buffer (`uvc_video.c:829`).
- With it on, `uvc_buffer_finish` → `uvc_video_clock_update` **replaces** the video buffer timestamp with
  the PTS mapped to host time through the SCR.
- Quality depends on the kernel:
  - 6.8 lacks the C922 SOF quirk, so its SCR SOF breaks the conversion (commit 9183c6f1a21e shows 5–8 fps
    glitches).
  - 6.11 adds the quirk.
  - 7.2 fixes the quirk's dev_sof filtering and the SW/HW switching artefacts.

**Metadata node (tier 0) (doc):**
- Present since Linux 4.16 (`uvc_metadata.c`). It is a second `/dev/videoM` per streaming interface,
  `ATTR{index}==1`, with `V4L2_CAP_META_CAPTURE`.
- Format `V4L2_META_FMT_UVC` ('UVCH'). Each block is
  `struct uvc_meta_buf { __u64 ns; __u16 sof; __u8 length; __u8 flags; __u8 buf[]; }`.
- `ns` (`ktime_get`) and `sof` (`usb_get_current_frame_number`) are sampled together with IRQs off, and
  `buf` holds the PTS and SCR (`uvc_video_decode_meta`, `uvc_video.c:1462-1530`).
- For UVCH, payloads without SCR, or with an SCR identical to the last one, are **skipped**.
- The meta buffer gets the video buffer's `sequence` and timestamp (`uvc_video_next_buffers`, line
  1556-1558), so pairing by sequence works. The meta buffer keeps the SOE stamp even when hwtimestamps
  rewrites the video stamp (no `buf_finish` on the meta queue).
- Since 6.14, a video error is copied to the meta buffer as an error (line 1561-1562).
- **Permissions:** the same udev rules as the capture node (`SUBSYSTEM=="video4linux"` → `GROUP="video"`
  and `TAG+="uaccess"`). No root is needed.

**Limits of the metadata path:**
- **The buffer is fixed at 10 KiB before 7.1** (`UVC_METADATA_BUF_SIZE 10240`). On overflow the meta
  buffer is marked ERROR (line 1496-1499).
- Size estimate: at high speed every payload is one microframe, and each block is 10 + 12 = 22 B. That
  gives about 5.9 KB per frame at 30 fps and about 11.7 KB at 15 fps.
- **So metadata at 15 fps or slower should overflow on kernels before 7.1** (Ubuntu 24.04 GA and HWE,
  Ubuntu 26.04). On 7.1 and later, request a larger `buffersize` through `S_FMT` on the meta node.
  **(inferred; must be tested)**
- **MSXU_1_5** (6.17+) is offered only when the camera implements the Microsoft metadata XU. It is
  probably absent on these consumer cameras (to verify through `VIDIOC_ENUM_FMT` on the meta node).

**What follows for skellycam (inferred):**
- **Tier 0 on Linux:** compute capture time in user space from the UVCH blocks: PTS, then SCR (STC, SOF),
  then the (host SOF, ns) pairs. This is the same algorithm as on Windows, where MF metadata gives the
  same fields.
- **For the C922 (and C920/C925e), ignore the device SOF field and use host SOF**, as the kernel quirk
  does.
- Keep `hwtimestamps=1` only as a tier-1 comparison leg.

---

## 4. G-MJPEG on Linux

- **Raw V4L2 mmap:** `S_FMT` with `V4L2_PIX_FMT_MJPEG`, then mmap `REQBUFS`, `QBUF`/`DQBUF`. The buffer
  holds exactly the camera's payload bytes (headers stripped by uvcvideo), and `bytesused` is the frame
  length. Draft: `mjpeg/drafts/linux/v4l2_mmap_mjpeg.py` (only its self-test has run). **(doc + draft)**
- **Mode resolution:** `VIDIOC_ENUM_FMT` → `ENUM_FRAMESIZES` → `ENUM_FRAMEINTERVALS` come from the
  descriptors and cause **no USB traffic**.
- **`VIDIOC_TRY_FMT`/`S_FMT` do send PROBE requests to the camera** (`uvc_v4l2_try_format` →
  `uvc_probe_video`, `uvc_v4l2.c:347`). They also **pick the nearest frame size** rather than failing, so
  check the width and height that come back. **(doc)**
- **Error frames:**
  - Since 6.14 corrupt frames arrive with `V4L2_BUF_FLAG_ERROR` (`uvc_queue.c:359-366`); before 6.14 they
    were dropped silently.
  - The `nodrop` parameter (0644, deprecated) still switches between the two (`uvc_driver.c:2486-2503`).
  - Frame-drop detection from `v4l2_buffer.sequence` is only correct from 7.2 on (f078966ca1fb,
    2f24ac8dd879). **(doc)**
- **PyAV / FFmpeg v4l2** (`input_format=mjpeg`):
  - With `-ts default` it returns the kernel timestamp unchanged. `abs` and `mono2abs` convert to wall
    clock through a filter (`libavdevice/v4l2.c:60-82, 490-545`).
  - Buffers flagged `V4L2_BUF_FLAG_ERROR` become **zero-length packets** (line 584-590).
  - For MJPEG `frame_size` stays 0, so variable sizes are accepted. **(doc:
    [FFmpeg v4l2.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavdevice/v4l2.c))**
- **OpenCV CAP_V4L2:**
  - With `CAP_PROP_CONVERT_RGB=0` it returns a 1×N `CV_8U` Mat holding the raw buffer, so MJPEG passes
    through (`cap_v4l.cpp:2111-2135`).
  - It **does not check `V4L2_BUF_FLAG_ERROR`**, so on 6.14+ corrupt JPEGs pass through unflagged.
  - `CAP_PROP_POS_MSEC` gives the buffer timestamp (line 1849-1853). **(doc:
    [cap_v4l.cpp 4.x](https://github.com/opencv/opencv/blob/4.x/modules/videoio/src/cap_v4l.cpp))**
- **GStreamer v4l2src:** `image/jpeg` caps (prior_art/SURVEY.md, doc).
- **`UVC_QUIRK_MJPEG_NO_EOF` and the dual-stream quirk** (6.14) split frames on SOI for certain cameras.
  This is not relevant to the cameras in hand. **(doc)**

---

## 5. Desktop session interference (Fedora KDE Wayland, Ubuntu GNOME)

- **Permissions (doc):**
  - systemd `rules.d/50-udev-default.rules.in:56` sets `SUBSYSTEM=="video4linux", GROUP="video"`.
  - `rules.d/70-uaccess.rules.in:34` sets `SUBSYSTEM=="video4linux", TAG+="uaccess"`, so logind grants
    an ACL to the user of the **active local seat** session.
  - **Over SSH, or from a headless test runner, there is no ACL. The user must be in `video`**, which is
    a tier-1 one-time admin step (`usermod -aG video`). The drafts assume group `video`.
- **PipeWire / WirePlumber (doc, from
  [WirePlumber video config](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/video.html)):**
  - Both a V4L2 monitor and a libcamera monitor exist; WirePlumber arbitrates by `device.devids`.
  - For uvcvideo devices "V4L2 is preferred". Node creation waits `monitor.camera-discovery-timeout`
    (default 1 s).
  - Cameras are released when the logind session goes inactive.
  - `monitor.v4l2 = disabled` or `node.disabled` rules can hide devices (user-level config, tier 0 for
    that user).
- **How a busy device fails (inferred from V4L2 semantics; to be tested):**
  - V4L2 allows many opens, but only one file handle can own the vb2 queue. If a PipeWire client (a
    browser through the Camera portal, Snapshot, Plasma's camera applications) is streaming, our
    `S_FMT`/`REQBUFS` gets **EBUSY**.
  - Controls are per-device and global, so another process can change exposure under us.
  - Enumeration by the monitor (open + QUERYCAP/ENUM_FMT) should not block us. But **QUERYCTRL by any
    process makes uvcvideo issue GET_INFO/MIN/MAX/DEF** to the camera, which matters for the Kiyo Pro.
- **libcamera:** `pipewire-plugin-libcamera` appears **not to be installed by default on Fedora** (web:
  [Fedora Discussion](https://discussion.fedoraproject.org/t/help-me-set-up-pipewire-camera/125900)).
  Verify per image with `rpm -q` / `dpkg -l`.
- **Sandboxes:** a Flatpak app has no device nodes unless given `--device=all`; the Camera portal hands
  out a PipeWire remote instead (doc:
  [Flatpak sandbox permissions](https://docs.flatpak.org/en/latest/sandbox-permissions.html)). A direct
  V4L2 skellycam therefore cannot ship as a strict Flatpak. Snaps need the `camera` interface.
  **(doc + inferred)**
- **Anecdote:** a KDE report of the webcam LED staying on while plasmashell runs was closed WORKSFORME
  (web: [KDE #501792](https://bugs.kde.org/show_bug.cgi?id=501792)). Weak evidence, but include
  "Plasma idle" in the session tests.

---

## 6. G-ID on Linux

- **Stock udev links (doc:
  [60-persistent-v4l.rules](https://github.com/systemd/systemd/blob/main/rules.d/60-persistent-v4l.rules)):**
  - `/dev/v4l/by-id/usb-<ID_SERIAL>-video-index<N>`, where `ID_SERIAL` = vendor_model[_serial]. **Two
    identical cameras without a serial get the same by-id link** (last one wins).
  - `/dev/v4l/by-path/<ID_PATH>-video-index<N>`, plus a second link carrying the USB revision.
  - `index0` is the capture node and `index1` the metadata node.
- **USB revision in the path (doc:
  [udev-builtin-path_id.c](https://github.com/systemd/systemd/blob/main/src/udev/udev-builtin-path_id.c)
  ~520-545):**
  - Since **systemd v254** (commit 873be895ed, 2023-05-20; checked by compare), `path_id` writes
    `usbv2-0:`/`usbv3-0:` and exports `ID_PATH_WITH_USB_REVISION`.
  - It does this because the HS and SS root hubs of one xHCI controller can give the same plain
    `usb-0:<port>` (systemd issue #19406).
  - The plain `ID_PATH` is kept for compatibility. All target distros ship systemd ≥ 255.
- **Path stability (inferred):** by-path changes if the PCI address of the controller changes (a card is
  added), if a hub is moved, or if a USB 3 camera (Kiyo Pro) enumerates at high speed instead of
  SuperSpeed.
- **Serial:** the sysfs `serial` attribute is world-readable; only the C922 has one (REPORT finding 22).
  `/dev/videoN` numbers are not stable.
- **Key scheme (inferred):** the Windows key (serial if unique, else port path) maps cleanly. Use
  `ID_PATH` **without** the revision for the port part, and record the revision separately.
  `naming/linux_identity.py` already gathers these.
- **Untestable now:** identical serial-less cameras. Only one of each model is in hand, so a **second
  4C4A:4A55 is needed** (cheap) to test the by-id collision.

---

## 7. Bandwidth on Linux (ENOSPC)

- **What the driver does (doc, `uvc_video.c:2045-2104`):**
  - uvcvideo reads the camera's `dwMaxPayloadTransferSize` after PROBE/COMMIT and selects the first
    alt setting with `psize >= bandwidth`.
  - `usb_set_interface` then fails with **-ENOSPC**, which VIDIOC_STREAMON returns.
  - The xHCI driver maps the controller's `COMP_BANDWIDTH_ERROR` to `-ENOSPC` ("Not enough bandwidth for
    new device state", `drivers/usb/host/xhci.c:2135-2139`).
- **Who decides admission (doc, `xhci-pci.c:354-358`):** the software bandwidth checker
  (`XHCI_SW_BW_CHECKING`, `xhci_check_bw_table`) is enabled **only for Intel Panther Point** (7-series,
  2012). On every other Intel, AMD or ASMedia controller the **controller firmware** decides admission,
  so the limits can differ by vendor. **(doc; vendor difference inferred)**
- **Hubs:** all four cameras are high-speed (the Kiyo Pro too, when on a USB 2.0 hub). A
  transaction translator only matters for full- or low-speed devices, so single-TT vs multi-TT does
  not matter here. Two cameras on one USB 2.0 hub share that hub's one high-speed microframe budget.
  **(inferred)**
- **The arithmetic:** two max-alt cameras (3069–3072 B each, REPORT finding 16) exceed the ~6000 B
  (80 %) periodic budget, so **the second STREAMON should fail with ENOSPC**. **(inferred from measured
  Windows numbers)**
- **What an app can do with no driver change (tier 0):**
  1. Catch ENOSPC and step down a mode ladder: lower resolution or fps where the camera asks for a
     smaller payload (C930e 480p requested 2688 B on Windows), or YUYV at small sizes.
  2. After STREAMON, read the granted alt from sysfs (`/sys/bus/usb/devices/<intf>/bAlternateSetting`)
     and the endpoint size from the `descriptors` file. Both are world-readable.
  3. Stagger starts so that the losing camera is chosen deliberately, not by a race.
  4. Spread cameras over root ports or controllers when the user can.
- **The uvcvideo debug line** "Device requested N B/frame bandwidth" needs the `trace` parameter (root)
  and kernel-log access.
- **`quirks=128` (tier 1) (doc, `uvc_video.c:229-231`):**
  - In v7.4-rc1 it still applies only when `!(format->flags & UVC_FMT_FLAG_COMPRESSED)`, so REPORT
    finding 21 holds on current master.
  - `quirks=` **replaces** the device's table quirks (`uvc_driver.c:2214-2215`:
    `dev->quirks = uvc_quirks_param == -1 ? info->quirks : uvc_quirks_param`). So `quirks=128` drops the
    C922's `INVALID_DEVICE_SOF` (0x10000); use `quirks=0x10080` to keep it.
  - The value is read at probe, so it needs a **replug** (rebind is excluded by the brief).
- **A plausible reason Dom saw `quirks=128` help (web, inferred):** an OpenCV answer reports that
  `quirks=128` worked through libv4l but not plain V4L2. libv4l can pick YUYV and convert it, so the
  stream really was uncompressed. (web:
  [ROS answers](https://answers.ros.org/question/12582/usb_cam-vidioc_streamon-error-28))

---

## 8. G-CTRL on Linux

- **Control IDs:** `V4L2_CID_EXPOSURE_AUTO` (menu; 1 = manual, 3 = aperture priority),
  `EXPOSURE_ABSOLUTE` (100 µs units), `EXPOSURE_AUTO_PRIORITY` (dynamic framerate), `FOCUS_AUTO`,
  `FOCUS_ABSOLUTE`, `AUTO_WHITE_BALANCE`, `WHITE_BALANCE_TEMPERATURE`, `GAIN`, `POWER_LINE_FREQUENCY`.
  Use IDs, not the display names, which have changed between kernels. **(doc/inferred)**
- **Master/slave rule (doc, `uvc_ctrl.c:1640-1668`):** setting a slave such as exposure_time_absolute in
  `S_EXT_CTRLS` while its master is not manual returns **EACCES**. Setting both in one call works only if
  the master's value in that same call is manual.
- **Readback is cached (doc, `uvc_ctrl.c:1466-1500`):** `GET_CUR` is cached after the first read (`loaded`)
  unless the control has `AUTO_UPDATE` or a status event flushes it (6.14+). So **reading a control back
  does not prove the camera applied it** (compare REPORT finding 11 on the C930e). Verify on the image or
  the rig.
- **Restore:** controls are restored only on `reset_resume` (`uvc_driver.c:2416-2420`). Normal autosuspend
  resume does not restore them, and the restore function's own TODO notes that restore order (auto
  exposure before exposure time) is not handled (`uvc_ctrl.c:3205-3210`).
- **Power behaviour:** autosuspend is enabled unless `DISABLE_AUTOSUSPEND` is set (`uvc_driver.c:2350`).
  With granular PM (6.16+), an idle fd no longer keeps the camera awake. So test
  "set, then idle more than 2 s, then stream" on 6.8 and on ≥6.16. **(doc + inferred)**
- **Async controls:** fixes in 6.14 and 7.2 (6d27f92c54ce, a deadlock) matter for repeated open/close
  combined with focus or pan sets. **(doc)**
- **Logitech LXU and other XUs** are reachable through `UVCIOC_CTRL_QUERY`. The `UVCIOC_CTRL_MAP`
  deprecation was announced in 7.2 (85355f7268af). **(doc)**

---

## 9. Recommended minimum Linux test matrix

| Leg | OS image | Kernel | Desktop | Why |
|---|---|---|---|---|
| **L1** | Ubuntu 24.04.5, booted on the **GA 6.8** kernel (GRUB entry; same install as L2) | 6.8 | GNOME 46 | Oldest uvcvideo still supported (also 22.04 HWE): silent error-frame drops, no C922 SOF quirk, 10 KiB metadata, global PM, Kiyo NO_LPM status unknown |
| **L2** | **Ubuntu 26.04 LTS** | 7.0 | GNOME 50 | Main Ubuntu target. The kernel equals 24.04.5 HWE, so the HWE leg is covered. Has error flags, granular PM and Kiyo NO_LPM; still 10 KiB metadata and pre-7.2 hwts/sequence bugs |
| **L3** | **Fedora KDE Plasma 45** | 7.2.x (re-smoke after the 7.3 rebase) | Plasma 6.8, Wayland | Main Fedora target; covers F43/F44 kernels too. Has the metadata buffersize option and the 7.2 timestamp/sequence fixes |
| L4 (opt.) | Ubuntu 26.10 | 7.3 | GNOME 51 | Newest kernel; uvcvideo is identical to 7.2, so a smoke run only |
| L5 (opt.) | Fedora KDE 44 | 7.2.x | Plasma 6.6 | Only for desktop-session (S) tests, which depend on the Plasma/PipeWire version |

Hardware:
- Run every leg on **Gerald** (same Intel xHCI as the Windows data) from installs on an **external SSD**.
  A Fedora live USB has no clean persistence, and the tests need packages installed.
- Add **one AMD-chipset machine** for the bandwidth tests (controller firmware admission), at least for
  L2 and L3.
- Cameras: C922, C930e, 4C4A:4A55, **Kiyo Pro in every test**. Plus a **second 4C4A:4A55** for the
  identical-camera tests, and one **USB 2.0 hub** (the Genesys hub used on Windows).

---

## 10. Linux test suite (all tier 0 unless marked)

"Cycle" = open → `S_FMT` → `REQBUFS` → `STREAMON` → 30 frames → `STREAMOFF` → close.

**What every test logs:**
- The kernel version, and the PipeWire and WirePlumber versions.
- `fuser -v /dev/video*`.
- Every ioctl errno.
- `V4L2_BUF_FLAG_ERROR` counts, `sequence` gaps, and strict libjpeg-turbo decode results.
- `journalctl -k` over the window. The Ubuntu first user is in `adm` and Fedora `wheel` can read the
  journal (inferred).

| ID | Test | Goal | Decides |
|---|---|---|---|
| LX-ENV | Record the kernel, `modinfo uvcvideo`, all `/sys/module/uvcvideo/parameters/*` and `usbcore` quirks, `lsusb -t`, controller PCI IDs, the systemd version, which PipeWire/libcamera packages are installed, and `usb3_hardware_lpm_u1/u2` for the Kiyo | all | Baseline per leg |
| LX-ID1 | Snapshot with `naming/linux_identity.py`. Then reboot ×2, replug ×5 into the same port, move to another port, move behind the hub, and the Kiyo on a USB 2 vs a USB 3 port. Diff with `identity_diff.py` | G-ID | Key = serial or `ID_PATH` (no revision) stays stable; whether the `usbvN` link changes with link speed |
| LX-ID2 | Two identical 4C4A:4A55 cameras: by-id collision, by-path distinct, sysfs devpath distinct; index0 vs index1 mapping | G-ID | Fallback to port works for identical serial-less cameras |
| LX-MJ1 | For every camera, every MJPG frame size and every interval from ENUM_*: `S_FMT`, check the returned size, capture 3 s by raw mmap, strict-decode, SOF0 dims equal the request | G-MJPEG | "All resolutions" on uvcvideo; silent nearest-size substitution |
| LX-MJ2 | Same bytes through PyAV v4l2 (`input_format=mjpeg`), OpenCV CAP_V4L2 `CONVERT_RGB=0` and GStreamer `v4l2src ! image/jpeg`: SOI–SOS header SHA-1 equals raw mmap and equals the Windows MF hash for the same camera and mode | G-MJPEG | Which wrapper is byte-exact; whether wrappers expose the ERROR flag |
| LX-MJ3 | Error-frame handling: stress (screen noise, near-limit alt with the generic camera beside it), count ERROR-flagged vs silently missing frames; on L1 compare `nodrop=1` (tier 1) | G-MJPEG | Whether skellycam must filter ERROR frames itself (6.14+) or detect gaps (6.8) |
| LX-OC1 | **Open/close reliability:** 50 cycles per camera; 50 cycles with two cameras started together; 50 cycles alternating modes. Record failures, time to first frame, zero-frame starts, and any "HC died" | all | "Reliable" per Dom's definition; the 4cf3b6fd54eb hazard |
| LX-TS1 | Flash or ESP32 rig against CLOCK_MONOTONIC: score SOE buffer ts, DQBUF arrival, user-space PTS→host from UVCH (with host SOF used for the C922), frame-index fit | G-TS | The tier-0 Linux timestamp and its accuracy (expect a ~4 ms SOE grid) |
| LX-TS2 (tier 1) | Same run with `hwtimestamps=1` written via sysfs (no reload) | G-TS | Whether the kernel's mapping matches user space on 7.0 vs 7.2 |
| LX-TS3 | Metadata at 30/15/10/5 fps: count meta ERROR buffers; on 7.2 set a larger `buffersize` through `S_FMT`; check the partial first buffer | G-TS | Usable fps range for metadata per kernel |
| LX-TS4 | ENUM_FMT on the meta node: does MSXU_1_5 appear for any camera (6.17+)? | G-TS | Extra metadata available? |
| LX-CT1 | Control matrix per camera: query ranges and defaults (compare with Windows MF/DShow lists); exposure manual set **before vs after STREAMON**; auto→manual in one `S_EXT_CTRLS`; EACCES case; verify by image luminance (not readback) | G-CTRL | Order rules; cached readback trap |
| LX-CT2 | Focus (auto continuous/absolute with a Siemens star), WB temperature, gain, power line frequency, exposure_dynamic_framerate = 0 holds fps | G-CTRL | Full control coverage |
| LX-CT3 | Persistence: set, close, wait 5 s (autosuspend), reopen; set, then idle with fd open for 5 s, then stream. Compare L1 (global PM) with L2/L3 (granular PM) | G-CTRL | Whether skellycam must re-apply controls at every stream start |
| LX-BW1 | Two cameras on one USB 2.0 hub at their default MJPEG modes: expect ENOSPC on the second STREAMON; run the step-down ladder until both stream; log granted `bAlternateSetting`; check the start after a refusal for zero-frame or truncated frames (REPORT finding 19) | BW | The navigation algorithm works with no driver change |
| LX-BW2 | Same on the AMD machine | BW | Controller-firmware admission differences |
| LX-BW3 (tier 1) | `quirks=0x10080` (FIX_BANDWIDTH plus C922 SOF) via sysfs + **replug** (no rebind): MJPEG vs YUYV alt chosen | BW | Settles REPORT finding 21; whether quirks are worth recommending |
| LX-KP1 | Kiyo Pro: plug in, then every 30 s for 20 min run QUERYCTRL + G_CTRL + a 2 s stream; record -32/-110, any "HC died", LPM state. On L1, if it fails, repeat with `usbcore.quirks=1532:0e05:k` (tier 1) | all | Whether NO_LPM fixes the Kiyo on Linux (and hints at the Windows cause) |
| LX-S1 | Session interference: (a) idle desktop with PipeWire running; (b) a browser using the camera through the portal while we open it, expect EBUSY at S_FMT/REQBUFS; (c) we stream, then a portal client starts; (d) a hotplug while WirePlumber enumerates and we open; (e) the same over SSH (ACL absent); run on L2 and L3 (+L5) | G-ID/CTRL | Error handling and user guidance; whether to recommend a WirePlumber rule |

### Changes needed in the local drafts
- `bandwidth/linux/uvc_bw_probe.py compare`: replace `rebind()` (unbind/bind) with a prompted replug.
  Use `quirks=0x10080`, not 128.
- `mjpeg/drafts/linux/v4l2_mmap_mjpeg.py`, `timing/linux/v4l2_uvc_timing.py`:
  - Log `V4L2_BUF_FLAG_ERROR` separately. On kernels before 7.2, treat `sequence` gaps as approximate.
  - Add a meta `S_FMT` buffersize option for 7.1 and later.
  - Iterate every frame size (LX-MJ1).
- `timing/linux/v4l2_uvc_timing.py`: add the host-SOF substitution for C920/C922/C925e in the
  user-space SCR fit.
- `libusb/linux/run_libuvc_linux.sh` + `70-skellycam-uvc.rules`: **out of scope** under the brief
  (libuvc detaches uvcvideo).
- `naming/linux_identity.py`: record both `ID_PATH` and `ID_PATH_WITH_USB_REVISION`.

---

## Sources (primary)
- Linux master v7.4-rc1: `drivers/media/usb/uvc/{uvc_driver.c,uvc_video.c,uvc_queue.c,uvc_metadata.c,uvc_ctrl.c,uvc_v4l2.c,uvcvideo.h}`; tag v6.8 for comparison. https://github.com/torvalds/linux/tree/master/drivers/media/usb/uvc
- `drivers/usb/host/xhci.c`, `xhci-pci.c` (master). `drivers/usb/core/quirks.c` via commit 8b7a42ecdcde.
- Commits cited by SHA above, e.g. https://github.com/torvalds/linux/commit/9183c6f1a21e (C922 SOF), https://github.com/torvalds/linux/commit/2ac27db04608 (meta buffersize), https://github.com/torvalds/linux/commit/87ce177654e3 (ERROR flag), https://github.com/torvalds/linux/commit/a32d9c41bdb8 (granular PM), https://github.com/torvalds/linux/commit/17526c7e69d0 (nodrop revert), https://github.com/torvalds/linux/commit/4cf3b6fd54eb (start failure, xHCI died).
- systemd main: `rules.d/60-persistent-v4l.rules`, `rules.d/70-uaccess.rules.in`, `rules.d/50-udev-default.rules.in`, `src/udev/udev-builtin-path_id.c`; commit 873be895ed (v254).
- FFmpeg master `libavdevice/v4l2.c`; OpenCV 4.x `modules/videoio/src/cap_v4l.cpp`.
- WirePlumber video configuration docs; Flatpak sandbox-permissions docs; Fedora KernelRebases wiki.
- Distro dates and kernels: Phoronix, Ubuntu Discourse, OMG! Ubuntu, Linuxiac, Fedora advisories (URLs in section 1).
- Local: `REPORT.md` (findings 7, 11, 16, 19, 21, 22), `prior_art/SURVEY.md`, `docs/test_gap_plan.md` (LX1–LX6), drafts listed in section 10.

---

## Verifier notes

Adversarial check on 2026-11-06. Read-only: no camera was opened, streamed or listed. Kernel source was re-fetched
from `raw.githubusercontent.com/torvalds/linux/master` (Makefile says **7.4-rc1**) and tag `v6.8`. Commit-to-tag
containment was re-checked with `gh api repos/torvalds/linux/compare/<tag>...<sha>`. systemd, FFmpeg, OpenCV and
PyAV-ffmpeg sources were fetched from GitHub. Phoronix returned 403, so distro dates were cross-checked through
other outlets (Linuxiac, OMG! Ubuntu, CNX, Ubuntu Discourse, ubuntuhandbook, linuxsecurity.com).

### Verdict table

| ID | Verdict | Evidence / correction |
|---|---|---|
| L1 | confirmed | 26.04 ships final 7.0 (Ubuntu Discourse t/80838, CNX 2026-04-24). 24.04.5 HWE moved from 6.17 to 7.0, release dated 2026-09-10 (OMG! Ubuntu, Linuxiac). Desktop installs track HWE by default. **Server stays on GA 6.8**, so the 6.8 leg stands for server/GA installs and 22.04 HWE, not for a default 24.04 desktop. |
| L2 | confirmed | 26.10 released 2026-10-15 with Linux 7.3 (ubuntuhandbook, itsfoss). Note: it shipped **before** upstream 7.3 GA (2026-10-18), on a 7.3-rc based kernel at release time (web). 25.10 EOL Jul 2026 follows the 9-month policy. |
| L3 | confirmed | F45 shipped after a double NO-GO, two weeks after the 2026-10-20 target, on Linux 7.2 (Linuxiac, Warp2Search). F43 got 7.2.10 on 2026-10-13 (FEDORA-2026-bc7bd292d6). F44 shipped 6.19.14 (Linuxiac). The exact F45 point release (7.2.15) was not re-checked. |
| L4 | confirmed | `commits?path=drivers/media/usb/uvc` gives the same top commit (a3d78e74dd3e, 2026-05-21) for v7.2 and v7.3. 40446ee73a65 (C925e SOF) is in the v7.4-rc1 list. |
| L5 | confirmed | uvc_driver.c:2716 (`.idProduct = 0x085c`). 9183c6f1a21e is in v6.11 and not in v6.10. Its message is quoted correctly. |
| L6 | confirmed | `grep` of master uvc_driver.c finds no 0843, 4c4a or 1532 entries. |
| L7 | **weakened** | The quirk exists (quirks.c:503-504, first in v7.0) and the commit message is quoted correctly. But (a) LP#2061177 itself shows **-110** ("Failed to set UVC commit control : -110") and an HC death. It reports **no -32**, and nobody there tested LPM. The LPM link is the patch author's claim, not something tested in the bug. (b) It is Cc stable, and mirrors show it in **6.12.81, 6.18.34 and 6.19.12** (web), so "7.0 and later" undersells where it is. (c) The implication that "kernels 7.0+ should not show the Kiyo failure" is a hypothesis for LX-KP1 to test, not an expectation. |
| L8 | confirmed (with a gap) | master uvc_queue.c:359-367; v6.8 uvc_queue.c:479-486 requeues on error when DROP_CORRUPTED is set. **Missed:** on 6.8, `nodrop=1` delivers corrupt frames as `VB2_BUF_STATE_DONE`, i.e. **without** `V4L2_BUF_FLAG_ERROR` (87ce177654e3 "Propagate buf->error", which carries a Fixes tag), unless the distro backported it. |
| L9 | confirmed (master only) | 17526c7e69d0 reverts 27ccc44a511b (the Zoom report). The `nodrop` callback is 0644 and is read per buffer in master. **On v6.8 it is latched at registration** (`uvc_queue_init(queue, type, !uvc_no_drop_param)`, v6.8 uvc_driver.c:1941), so a sysfs write needs a **replug** on L1. |
| L10 | confirmed | f078966ca1fb ("Fix sequence number when no EOF": counted twice) and 2f24ac8dd879 ("Fix buffer sequence in frame gaps") are both in v7.2 and not in v7.1. |
| L11 | confirmed | uvc_queue.c:250-251; uvc_video.c:1256-1272 stamps `uvc_video_get_time()` on the FID flip. Decode runs in the URB completion handler (uvc_video.c:1735-1790); only the memcpy is deferred. |
| L12 | confirmed (as inference) | uvcvideo.h:56 sets UVC_MAX_PACKETS=32. uvc_video.c:1853-1855 sets npackets = min(ceil(dwMaxVideoFrameSize/psize), 32), which is 32 for MJPEG. URB giveback through the HCD BH adds further jitter. Still to be measured. |
| L13 | **weakened** | The block format and the sequence/timestamp copy are right (uvc_video.c:1462-1530, 1547-1562). But `ns` and `sof` are sampled **when the URB is processed** (one sample per ≤32-packet URB), not when each payload arrived. All blocks from one URB carry nearly the same host ns/SOF. So the host-SOF substitution for the C922 inherits up to ~4 ms (about 4 SOF counts) of error, and the meta format has no packet index to correct it. "Per-payload host timing" is overstated. |
| L14 | confirmed | 70-uaccess.rules.in:34 and 50-udev-default.rules.in:56, exactly as cited. |
| L15 | **weakened** | The 10240 B size on 6.8 (UVC_METADATA_BUF_SIZE) and the 7.1 S_FMT change (2ac27db04608, which shows cameras at 11.1-11.6 KB per frame) are confirmed. But "on overflow the meta buffer is marked ERROR" holds only from 6.14. On **6.8 with the default nodrop=0, overflowed meta buffers are silently requeued**, so LX-TS3 must count meta **sequence gaps** on L1, not ERROR flags. |
| L16 | confirmed | uvc_driver.c:2484 (0644); uvc_video.c:829 checks it on every update. Detail: buf_finish maps only `VB2_BUF_STATE_DONE` buffers (uvc_queue.c:164-165), so error frames keep the SOE stamp. |
| L17 | confirmed | 53d7995383fa (v6.11, slow-fps double rollover); edc1917599c5 (v7.2, dev_sof compare broken under INVALID_DEVICE_SOF); ede7de6e6b3d (v7.2, SW/HW jumping, Cc stable, so it may reach older stable trees). |
| L18 | confirmed | 2ab4019aa34d is in v6.17 and not in v6.16. uvc_metadata.c:163-260 probes the MSXU XU (GET_MAX/SET_CUR) at probe time and adds the format only if it succeeds. |
| L19 | confirmed | master uvc_video.c:229-231: `!(format->flags & UVC_FMT_FLAG_COMPRESSED) && quirks & FIX_BANDWIDTH`. |
| L20 | confirmed | uvc_driver.c:2214-2215, as quoted. The param is 0644 and is read in probe. |
| L21 | unverifiable | answers.ros.org now 301-redirects to robotics.stackexchange.com/questions/36945, which could not be fetched. It is a ROS usb_cam thread, not "an OpenCV answer". |
| L22 | **weakened** | uvc_video.c:2062-2083 picks the alt with the **smallest** `psize >= bandwidth` (the first one on ties), not the first one that fits. It returns **-EIO** if no alt is large enough (line 2085-2089). xhci.c:2129-2140 maps COMP_BANDWIDTH_ERROR/SECONDARY_BANDWIDTH_ERROR to -ENOSPC, but **COMP_RESOURCE_ERROR to -ENOMEM**. The ladder must handle ENOSPC, ENOMEM and EIO, plus probe failures (-EPIPE, -ETIMEDOUT). |
| L23 | confirmed (scope) | xhci-pci.c:354-358 (Panther Point only); xhci.c:2997. Out of scope for desktops: EHCI hosts and MediaTek xhci-mtk do software scheduling. |
| L24 | confirmed (as inference) | Consistent with REPORT findings 16-17 (C930e refused at alt 9 beside the generic camera on the Genesys hub). On Linux the admission limit is set by the controller firmware and is unmeasured. |
| L25 | confirmed | `bAlternateSetting` and `descriptors` are standard world-readable usbfs/sysfs attributes. The `trace` param is 0644 (root to set) at uvc_driver.c:2507. |
| L26 | confirmed (measured) | bandwidth/linux/uvc_bw_probe.py:333-345 writes `/sys/bus/usb/drivers/uvcvideo/unbind` and `bind`. run_libuvc_linux.sh:5-6 states "detach uvcvideo". |
| L27 | confirmed | uvc_v4l2.c:346-348 calls `uvc_probe_video()` in try_format. **Extra:** in S_FMT the probe is sent **before** the `vb2_is_busy` EBUSY check (uvc_v4l2.c:442-447), so our S_FMT while another process streams still sends PROBE SET_CUR to a streaming camera (relevant for the Kiyo). |
| L28 | confirmed | FFmpeg master v4l2.c: on the ERROR flag, `bytesused = 0` with a warning; `default` ts uses `buf.timestamp` unchanged. The frame_size check runs only if `frame_size > 0`. PyAV's FFmpeg build (pyav-ffmpeg scripts/build-ffmpeg.py) does not disable the v4l2 indev. Inferred risk: PyAV may confuse a zero-size packet with a flush packet. |
| L29 | confirmed | cap_v4l.cpp 4.x: no `V4L2_BUF_FLAG_ERROR` anywhere. Line 997 copies the timestamp; lines 1849-1853 give POS_MSEC. The default branch of initFrameNonBGR (around line 2077) builds a 1×bytesused CV_8UC1 Mat. |
| L30 | confirmed | WirePlumber video config page: "for these, V4L2 is preferred"; the 1 s `monitor.camera-discovery-timeout`; cameras are released when the session is inactive. The page does not say whether an idle node keeps the fd open. |
| L31 | confirmed (inference, refined) | EBUSY returns at uvc_v4l2.c:447, 517 and 742. `vb2_is_busy` is true once buffers are **allocated**, not only while streaming. See the L27 note about PROBE preceding EBUSY. |
| L32 | unverifiable | discussion.fedoraproject.org returned 403. |
| L33 | confirmed | Flatpak docs: "`--device=all` can be used to access devices like webcams"; there is no camera-specific device permission (`--device=usb` is raw USB, which is not useful for V4L2 nodes). |
| L34 | confirmed | 60-persistent-v4l.rules: by-id needs `ID_SERIAL`; by-path is emitted for both `ID_PATH` and `ID_PATH_WITH_USB_REVISION`. |
| L35 | confirmed | 873be895ed is in v254 and not in v253. Its message: "xHCI host controller may register two … root hubs … devices … may have same ID_PATH. Closes #19406." path_id.c:534-541, 632-643. |
| L36 | confirmed | uvc_ctrl.c:1650-1668: iterates the S_EXT_CTRLS array backwards for the master; otherwise reads the master's current value and returns -EACCES if it is not manual. |
| L37 | **weakened** | Caching is real (uvc_ctrl.c:1472-1479). But **EXPOSURE_TIME_ABSOLUTE, FOCUS_ABSOLUTE, WB_TEMPERATURE, WB_COMPONENT, ZOOM/PANTILT/IRIS and HUE carry `UVC_CTRL_FLAG_AUTO_UPDATE`**, and commit sets `loaded = 0` for them (uvc_ctrl.c:2430-2431). So the first read after setting exposure time **does** query the camera. Readback can still disagree with the image (the camera echoes the value but does not apply it, as REPORT finding 11 shows). "Verify on the image" stands, but the reason given is partly wrong. The restore TODO is at uvc_ctrl.c:3205-3210. |
| L38 | confirmed | a32d9c41bdb8 is in v6.16 and not in v6.15. uvcvideo calls `usb_enable_autosuspend()` at probe (master uvc_driver.c:2350-2351; v6.8 :2236), so autosuspend is active by default (the kernel default for non-hubs would be `on`). |
| L39 | **weakened** | The commit says only that the bug "**may be** responsible" and "I had no luck reproducing". It fixes 7dd56c47784a, which is **first in v6.17**, so 6.8 never had this bug and 7.0+ has the fix. It is not a reason to expect HC deaths on L1-L3, although watching the kernel log for them is still good practice. |
| L40 | confirmed (measured) | results/linux/ holds only Gerald/naming and docker-ubuntu24.04/{libuvc_build, py_libusb1_unit_test, run_libuvc_linux_smoke}. |

### Corrections to the direct answers
- **G-TS:** the metadata `ns`/`sof` pairs are per URB completion (≤32 payloads share one sample), not per payload. A userspace PTS/SCR fit should regress on device STC against these samples and accept a ~4 ms host-side step structure. For the C922's host-SOF substitution, quantify the error before relying on it. On 6.8, metadata overflow shows up as **missing meta buffers** (sequence gaps), not ERROR flags.
- **Bandwidth:** the alt is the **smallest** that fits, not the first. STREAMON can also fail with **ENOMEM** (xHCI resource error) or **EIO** (no alt large enough), and with EPIPE/ETIMEDOUT from PROBE/COMMIT. The ladder must treat all of these as "step down".
- **G-CTRL:** exposure time, focus and WB temperature are AUTO_UPDATE. The first read after a set re-queries the camera; later reads are cached. Image verification is still required.
- **uvcvideo changes:** 4cf3b6fd54eb fixes a bug that exists only in 6.17-6.19. Kiyo NO_LPM is also in stable 6.12.81, 6.18.34 and 6.19.12. Whether Ubuntu's 6.8 GA carries it remains open.
- **LX-MJ3 on L1:** `nodrop=1` needs a replug on 6.8, and there it yields corrupt frames **without** the ERROR flag (unless 87ce177654e3 was backported). Detect them with strict decode, not flags.
- **Desktop interference:** our S_FMT sends PROBE to the camera even when it then fails with EBUSY. Call TRY_FMT/S_FMT only after confirming nobody else owns the queue (`fuser`), or expect to disturb another app's stream.
- **Versions:** a default 24.04 desktop is on 7.0 (HWE) now. The 6.8 leg represents server/GA opt-outs and 22.04 HWE. Ubuntu's HWE policy suggests 26.04.2 (about Feb 2027) will move to the 26.10 kernel, 7.3 (inferred).

### Missed items
- Record each camera's **bcdDevice (firmware revision)** in LX-ENV. The Kiyo Pro has had firmware updates (shipped by a Windows-only updater), and results may depend on firmware (inferred; lsusb `-v` shows bcdDevice).
- The Kiyo Pro's extra features (HDR, FoV) are vendor XU controls, reachable on Linux through `UVCIOC_CTRL_QUERY` (web: https://github.com/soyersoyer/kiyoproctrls). G-CTRL parity with Windows should state whether XUs are in scope.
- The original Kiyo (not the Pro) has a Linux report of focus_absolute=0 leading to "Failed to set UVC probe control : -32" and USB disconnects (web: https://insider.razer.com/razer-support-45/razer-kiyo-crashing-after-changing-focus-settings-with-v4l2-ctl-under-linux-67440). Include focus sets in LX-KP1.
- LX-OC1 should also hit the **failed-start path** (STREAMON refused by bandwidth, then close and reopen), because the 7.0 fix 4cf3b6fd54eb concerns buffer return on a failed start.
- LX-ENV should also log `power/control`, `power/autosuspend_delay_ms` and `power/runtime_status` per camera. Distro tools (TLP, powertop, tuned) can override uvcvideo's autosuspend default.
