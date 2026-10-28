# Hand-back from an earlier MJPEG agent instance (compile-only, ~15:05 local, 2026-10-25)

> **Superseded (2026-10-28):** see `RESULTS.md` in this directory for the verified rerun (2026-10-27/28, C922 + C930e + generic camera; Kiyo excluded). Several numbers below differ there (e.g. OpenCV CAP_MSMF does deliver frames once the open wait exceeds its ~40 s open; OpenCV DSHOW CONVERT_RGB=0 negotiates MJPG at 30 fps with the size-first property order).

This is the final report of an MJPEG agent instance that was stood down. A fresh agent took over goal 1 at about 14:55 local. These findings come from result files on disk. They have **not** been adversarially verified, so the fresh agent's RESULTS.md and the verifier take precedence.

## Corrections
1. DN_NEED_RESTART is bit 0x100 (cfg.h), not 0x01000000. At 14:39 only the usbccgp parents had 0x100 set; the MI_00 interfaces did not. The parent flag does not block MF capture. `results/windows/Gerald/mjpeg_mf_blocked/devnode_status_1439.json` was corrected in place.
2. The MF_E_REBOOT_REQUIRED window ended without a reboot. MF `--list` was OK at 14:38 (`mjpeg_mf_blocked/mf_list_1438.json`).

## Invalid or misleading results
- Kiyo cells taken during its fault (~14:30 to at least 14:47; MF 0x8007001F, dshow "Could not RenderStream"):
  - `mjpeg_msmf/common_1280x720at30_kiyo`
  - `mjpeg_msmf/max_1920x1080at60_kiyo`
  - the Kiyo rows of the 3-cam 720p MF and PyAV runs
  - `mjpeg_pyav_dshow_format_probe/kiyo.json`

  The Kiyo had recovered by about 14:49 (`mjpeg_msmf/max_1920x1080at30_c922+kiyo+c930e` OK).
- MF summaries show frame-server CPU as 0.0 with `frameserver_open_error: 5` (access denied). Read it as null.
- `mjpeg_winrt/common_1280x720at30_c922` (0 frames) came from the old script. See `mjpeg_winrt_variants` instead.
- `mjpeg_opencv-dshow-raw` c922/C930e at 10.01 fps were YUY2 converted to BGR: the MJPG request did not stick. These are not raw-MJPEG results.
- `mjpeg_matrix/table.json` (14:50) is stale. Rerun `aggregate.py`.
- In `mjpeg_msmf/max_1920x1080at30_c922+kiyo+c930e` the C930e exposure read back −5 when −7 was set.

## Valid findings (from files)

**MF IMFSourceReader native MJPG (`mjpeg_msmf`).** 100% complete JPEGs (SOI, EOI, DHT; decode with Pillow and simplejpeg), 0 gaps.

| Run | fps | Process CPU, % of one core |
| --- | --- | --- |
| c922 720p30 | 30.0 | 0.77 |
| C930e 720p30 | 30.05 | 0.69 |
| c922 1080p30 | 30.0 | 0.93 |
| C930e 1080p30 | 30.1 | 1.74 |
| 3-cam 1080p30 | ~30 each | 2.67 total |

- 3-cam inter-arrival p50 ≈ 32 ms, p95 ≈ 48 ms (16 ms steps). First-frame latency 299 / 934 / 488 ms (c922 / Kiyo / C930e).
- `MFSampleExtension_DeviceTimestamp` equals the sample time. Host arrival minus sample time p50 16.25 ms (`mjpeg_devtest/mf_first`).

**PyAV dshow `vcodec=mjpeg` (`mjpeg_pyav-dshow`).** c922 and C930e give 100% valid JPEG.

| Run | Process CPU, % of one core |
| --- | --- |
| c922 720p | 0.57 |
| C930e 720p | 0.76 |
| c922 1080p | 1.17 |
| C930e 1080p | 0.78 |
| c922 + C930e 1080p | 1.77 total |

- The Kiyo comes back as rawvideo (YUY2 1280×720, 1843200-byte packets) even though its DirectShow pin advertises MJPG. Also seen in `prior_art_pyav_dshow-kiyo-720p`. Cause unexplained.

**DirectShow formats (`mjpeg_dshow_formats`).**
- c922: MJPG up to 1080p30 and 720p60.
- Kiyo: MJPG, H264, NV12 and YUY2, each at 640×480, 640×360, 720p and 1080p, all at 60 fps; every format listed as both VideoInfo and VideoInfo2.
- C930e: MJPG up to 1080p30.

**WinRT MediaFrameReader (`mjpeg_winrt_variants`, c922 720p30).**
- Subtype "MJPG": E_INVALIDARG on every acquire.
- Native subtype: decoded NV12 (CPU 11.1% with CPU memory, 7.4% with Auto memory).
- No compressed bytes in any configuration tried.

**Source reading only (untested).**
- FFmpeg dshow matches vcodec through biCompression and prefers VideoInfo2.
- OpenCV MSMF with CONVERT_RGB=0 returns the raw buffer as one row of bytes. CAP_PROP_FORMAT=-1 handling was not found.

## Open items left for the fresh agent
- Rerun the Kiyo format probe and the Kiyo MF cells.
- Explain the Kiyo rawvideo result under PyAV dshow.
- Rerun opencv-dshow with size-first set order.
- Run opencv-msmf raw/decode and msmf-decoded-nv12.
- Rerun `aggregate.py`.
