# MJPEG passthrough summary

2026-10-28 · Dom

> Exported on 2026-10-28 from the online doc this study was first written in. This file is now the canonical copy; corrections made after export are marked "(corrected 2026-10-28; was ...)".

## Summary

Yes: Windows can hand skellycam the camera's own JPEG bytes, with no decode or re-encode, at about 1-2% of one core per camera. Media Foundation's IMFSourceReader, set to the native MJPG type with converters disabled, gave 100% valid JPEG on all three cameras tested. It ran at 30.00 fps (C922), 30.05 fps (C930e) and 25.76-25.78 fps (generic 4C4A:4A55), at 1280x720 and 1920x1080.

PyAV / FFmpeg dshow with `vcodec=mjpeg` (demux only) is a second native path. Its JPEG headers are byte-identical to MF's for every camera and mode. OpenCV 4.12, skellycam's current baseline, never returns JPEG bytes: it returns BGR pixels at 24.6-155.8% of one core, or MF-decoded NV12 at 4.8-13.4%. WinRT MediaFrameReader with an MJPG subtype delivered no frames at all.

The matrix was re-run overnight 2026-10-27/28 on the test machine Gerald (Windows 11, i7-14700K). The Razer Kiyo Pro was left out on purpose as known flaky. Linux and macOS harnesses exist as drafts but have never run.

## What was tested

Six capture APIs were run on three cameras, at 1280x720@30 and 1920x1080@30, one camera at a time and all three together. Each cell was a 2 s warm-up plus a 10 s measured window, one cell per camera lock, with manual exposure (2^-7 s requested), 4500 K white balance and auto-exposure priority 0 set first and read back after.

| Camera | USB id | Notes |
|----|----|----|
| Logitech C922 | 046D:085C | Own controller path |
| Logitech C930e | 046D:0843 | Shares a hub with the generic camera; accepts exposure -5 at most |
| Generic "USB Camera" | 4C4A:4A55 | Shares a hub with the C930e |
| Razer Kiyo Pro | 1532:0E05 | Excluded: stops answering EP0 minutes after plug-in, then every API fails with 0x8007001F |

The APIs: (a) PyAV / FFmpeg dshow `vcodec=mjpeg`, demux only; (b) Media Foundation IMFSourceReader with the native MJPG type and MF_READWRITE_DISABLE_CONVERTERS; (c) WinRT MediaFrameReader; (d) OpenCV 4.12 CAP_DSHOW and CAP_MSMF, with and without CONVERT_RGB; and MF with its own MJPEG decoder as a reference.

Every payload was checked for SOI, EOI, a full Pillow decode and a libjpeg-turbo decode at the requested size. "Native" means the SHA-1 of the frame's DQT+SOF+DHT tables matches what the MF reader delivered for that camera and mode. A host decode and re-encode would emit different tables. Process CPU is the capture process only, as % of one core; Frame Server CPU needs elevation and is excluded.

## Results matrix

Only the two native paths (MF and PyAV) return the camera's JPEG bytes, and they cost 0.7-2.1% of one core; every decoding path costs 3.2-154.7%. Single-camera cells from the 2026-10-27/28 rerun; each value is one 10 s window.

| Approach | Mode | fps (C922 / C930e / generic) | Valid JPEG % | Process CPU, % of one core (C922 / C930e / generic) | Camera's own bytes? |
|----|----|----|----|----|----|
| \(b\) MF IMFSourceReader, native MJPG | 720p30 | 30.00 / 30.05 / 25.78 | 100 | 1.8 / 0.7 / 1.7 | Yes (reference) |
| \(b\) MF IMFSourceReader, native MJPG | 1080p30 | 30.00 / 30.05 / 25.76 | 100 | 0.9 / 2.1 / 1.1 | Yes (reference) |
| \(a\) PyAV dshow `vcodec=mjpeg` | 720p30 | 30.04 / 30.04 / 25.74 | 100 | 0.9 / 1.3 / 1.3 | Yes |
| \(a\) PyAV dshow `vcodec=mjpeg` | 1080p30 | 30.00 / 30.05 / 25.74 | 100 | 1.6 / 1.5 / 1.1 | Yes |
| (ref) MF with its decoder, NV12 out | 720p30 | 30.00 / 30.04 / 25.78 | pixels | 3.7 / 3.3 / 3.2 | No |
| \(d\) OpenCV CAP_MSMF, FORMAT=-1, CONVERT_RGB=0 | 720p30 | 29.99 / 30.05 / 17.13 | pixels (NV12) | 13.4 / 12.2 / 4.8 | No |
| \(d\) OpenCV CAP_DSHOW, MJPG, decode | 720p30 | 30.00 / 30.04 / 25.77 | pixels (BGR) | 27.4 / 28.2 / 24.6 | No |
| \(d\) OpenCV CAP_DSHOW, CONVERT_RGB=0 | 720p30 | 30.00 / 29.92 / 25.71 | pixels (BGR) | 27.8 / 28.7 / 28.2 | No |
| \(d\) OpenCV CAP_DSHOW, MJPG, decode | 1080p30 | 30.00 / 30.04 / 25.76 | pixels (BGR) | 39.1 / 39.6 / 37.4 | No |
| \(d\) OpenCV CAP_MSMF, decode | 720p30 | 30.02 / 29.93 / 30.02\* | pixels (BGR) | 48.8 / 46.3 / 50.7 | No |
| \(d\) OpenCV CAP_MSMF, decode | 1080p30 | 30.04 / 29.93 / 29.97\* | pixels (BGR) | 148.0 / 142.6 / 154.7 | No |
| \(c\) WinRT MediaFrameReader, MJPG subtype | 720p30 | 0 frames on all three | none | 20.1 / 0.0 / 10.7 | No frames |
| \(c\) WinRT MediaFrameReader, MJPG subtype | 1080p30 | 0 frames on all three | none | 32.3 / 34.0 / 24.6 | No frames |

\* Padded: 48 of about 300 frames repeat the previous one; the unique rate is 25.3-25.4 fps. Valid JPEG % uses the lenient libjpeg-turbo decode; the generic camera's 1080p frames fail the strict decode on every frame, on MF and PyAV alike. With all three cameras open, MF and PyAV process CPU was 1.7-3.0% for the whole process. Whole-machine CPU was 2-11% around almost every cell while other agents ran; the one exception was 60% before the MF C930e 720p cell (0.7% process CPU), so read sub-2% gaps as noise.

## Per-camera findings and quirks

The C930e and the generic camera cannot both stream MJPG at 720p or 1080p while all three cameras are open: they share a hub and run out of USB bandwidth (inferred from the error text and topology; a two-camera set was never run). Which of the two loses varies between runs. The C922, on its own controller path, always streamed.

| Camera | Native MJPG rate | Payload p50, 720p / 1080p | Quirks |
|----|----|----|----|
| Logitech C922 | 30.00 fps | 100 / 182 kB | One fixed JPEG header per mode. Same DQT/SOF/DHT tables as the C930e (Logitech encoder); APP0/COM differ. OpenCV CAP_MSMF takes 39-41 s to open it. |
| Logitech C930e | 30.05 fps | 122 / 208 kB | Reads back exposure -5 (2^-5 s) when 2^-7 s is asked. Lost the bandwidth race at 720p under MF (ReadSample 0x800718CF). OpenCV CAP_MSMF takes 39-41 s to open it. |
| Generic "USB Camera" 4C4A:4A55 | 25.74-25.78 fps when 30 is asked | 66 / 118 kB | Changes quantisation tables between frames: 11-14 distinct headers per 10 s, all seen across MF cells (only 11 of 14 in the single MF cell). Lost the bandwidth race at 1080p under MF, and fails to open last under DirectShow (FFmpeg OSError 5). OpenCV CAP_MSMF pads it to 30 fps with repeated frames. No UVC capture metadata (registry value not set). |

The generic camera's 25.7 fps is not a low-light effect. Exposure was manual and fixed (2^-7 s, AE priority 0), so auto-exposure cannot lower the rate, and every native path agrees. It was never tested in a bright scene: its luma was 14-22 in every run, 25 Oct included. The bandwidth error 0x800718CF is HRESULT_FROM_WIN32(6351), "A camera interface doesn't have the desired bandwidth". DevNodeStatus stayed 0x0180200A before and after every cell, so no camera needed a restart.

## What changed since the 25 Oct run, and verifier verdicts

The core finding held: an adversarial verifier re-ran 7 cells at 04:44-04:50 UTC on 28 Oct and confirmed MF and PyAV native passthrough, with the rerun's header SHA-1s and the 25 Oct table fingerprints. Four earlier claims changed, and the verifier weakened three of the rerun's own claims.

| Claim | 25 Oct | 27-28 Oct rerun | Verifier | Final |
|----|----|----|----|----|
| MF native MJPG = camera's bytes, about 1-2% CPU | Yes | Reconfirmed, 100% valid on all three | Confirmed | Holds, but generic 1080p frames are 0% valid under strict libjpeg on MF and PyAV; "100%" is the lenient decode |
| PyAV dshow passthrough = same bytes as MF | Yes | Reconfirmed, header SHA-1 identical | Confirmed; 11 of 14 generic headers match the single MF cell, not 14 of 14 | Holds |
| Generic camera about 25.7 fps, not light-limited | Yes | Reconfirmed, 25.71-25.78 fps | Weakened: never measured in a bright scene; the real reason is fixed manual exposure | Holds; the reason is fixed exposure, not a light test |
| OpenCV MSMF gives 0 frames on the C922 | Yes | Refuted: harness waited 30 s for a 39-41 s open | Confirmed | Harness artifact |
| OpenCV DSHOW CONVERT_RGB=0 gives YUY2 at 10 fps | Yes | Changed: size-first order gives MJPG at 30 fps, still BGR | Weakened: fourcc-first reproduces YUY2 at 9.99 fps | Depends on property order; neither returns JPEG |
| MF CaptureMetadata absent | Yes | Changed: 32-byte UVC header on every C922 and C930e sample | Confirmed | Registry value set after 25 Oct |
| Generic 1080p MF "0% valid" | Yes | Changed: 100% lenient, 0% strict | Agreed; asks for a strict-decode footnote | Camera bitstream property |
| PyAV generic arrival-minus-pts reaches 1.06-1.09 s | \- | Claimed | Weakened: that is the median; drift grows 1.42 s in 10 s, to 1.76-1.80 s | Corrected |
| Process CPU same as 25 Oct | \- | Inconclusive: several cells 1.3-2.3x higher | Confirmed persistent at 2.5-5% machine CPU | Real, unexplained; ranking unchanged |

None of the changes trace to light or machine load. The darker scene cut C922 720p payloads from 134-139 kB to 100 kB but did not change any frame rate.

Two other areas back the native result. nokhwa 0.10.11 over MSMF captured native MJPEG at 720p30 (C922 593/593 valid, 30.00 fps; C930e 588/588, 30.06 fps; generic 515/515, 25.74 fps), though its format list hides MJPEG on both Logitech cameras. GStreamer 1.28.8 `mfvideosrc` delivered 172/172, 167/167 and 154/154 valid JPEG; the verifier did not repeat the check that the bytes are not re-encoded. GStreamer `ksvideosrc` opened the excluded Kiyo on every run while sorting devices, so it is not a safe probe on that machine.

## Recommendation, limits and open questions

On Windows, skellycam should take MJPEG from Media Foundation's IMFSourceReader with the native MJPG type and converters disabled, and keep OpenCV only where pixels are needed. That cuts capture cost from 24.6-155.8% of one core (OpenCV to BGR) to 0.7-2.1% per camera and keeps the camera's own bytes. This is our reading of the results; the sources state no decision.

MF is preferred over PyAV dshow because it also carries usable timestamps: llTimestamp equals the device timestamp on 100% of frames, and the 32-byte UVC payload header arrives on the C922 and C930e. PyAV's pts are nominal 33.333 ms steps, so on the generic camera they drift 1.42 s from arrival in 10 s. PyAV remains a working fallback with byte-identical output.

Limits to design for:

- One MJPEG camera per shared USB 2.0 hub at 720p or 1080p. The second camera fails (MF 0x800718CF, DirectShow OSError 5); with a 2.5 s stagger the second always loses.

- The generic 4C4A:4A55 runs 25.7 fps when 30 is asked, and its 1080p frames need a lenient JPEG decoder.

- Decode is still needed for preview or analysis: MF's own decoder to NV12 cost 3.2-3.7% of one core at 720p.

- Windows only. The Linux and macOS harnesses pass static checks but have never run; the Kiyo Pro is unmeasured.

Open questions:

- Why does the capture process now use 1.3-2.3x the 25 Oct CPU at low machine load?

- How much CPU does the Windows Frame Server add per camera? It needs an elevated run.

- Why does OpenCV CAP_MSMF take 39-41 s to open the Logitech cameras and 3.4-3.7 s for the generic one?

- Why does OpenCV CAP_MSMF raw NV12 run the generic camera at 17.1 fps?

- Does the C922's MF-listed 1280x720@60 MJPEG mode deliver? It has never been captured.

- Do MF NV12 decode and DSHOW raw hold at 1080p and with three cameras? Those cells were dropped.

## Evidence

All runs were on Gerald (Windows 11, i7-14700K, 28 logical CPUs, not elevated), 2026-10-28 03:03-04:50 UTC, with five other rerun agents and then six verifiers sharing the machine and the camera lock. Paths are relative to the skellycam repo.

- Matrix, method and findings: `research/usb_cameras/mjpeg/RESULTS.md`

- Rerun cells (87 rows): `research/usb_cameras/results/windows/Gerald/mjpeg_rerun_20261027/` (`table.md`, `table.json`, per-cell `summary.json`)

- Comparison with 25 Oct: `research/usb_cameras/results/windows/Gerald/mjpeg_rerun_20261027/compare_vs_20261025.json`; 25 Oct captures re-validated in `mjpeg_resummarized_20261025_data/` and `_data_b/`

- Verifier re-runs: `research/usb_cameras/results/windows/Gerald/mjpeg_adversarial_verify_20261028/`

- Rerun reports and adversarial verdicts (areas mjpeg, libusb_rust, prior_art): `research/usb_cameras/results/agent_reports/rerun_20261027_reports_and_verifications.json`

- Consolidated rerun notes: `research/usb_cameras/results/windows/Gerald/RERUN_20261027.md`

- nokhwa verifier re-run: `research/usb_cameras/results/windows/Gerald/verify_rust/20261028T034322Z_adversarial_rerun20261027/`

- GStreamer and PyAV prior-art re-run: `research/usb_cameras/results/windows/Gerald/prior_art_rerun_20261027_adversarial_verify/`

- Mode listing: `research/usb_cameras/results/windows/Gerald/mjpeg_formats/20261028T030920Z/`; Linux/macOS draft checks: `mjpeg_drafts_check/20261028T044052Z/summary.json`

- Status and resume notes: `research/usb_cameras/PROGRESS.md`

- Earlier runs marked bad carry `INVALID.txt` or `SUPERSEDED.txt` in their cell (Kiyo-fault cells, the old 4-camera cells, the old WinRT C922 cell, `mjpeg_matrix/`); none are used here.

The full investigation report, covering timing, bandwidth, naming and libraries: [USB camera investigation](usb_camera_report.md).
