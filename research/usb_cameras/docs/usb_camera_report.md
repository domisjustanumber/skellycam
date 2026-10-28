# Low-cost USB cameras: MJPEG, timing, bandwidth, naming, cross-platform

Oct 25, 2026 · Dom

> Exported on 2026-10-28 from the online doc this study was first written in. This file is now the canonical copy; corrections made after export are marked "(corrected 2026-10-28; was ...)".

## Test environment and harness

Every result here comes from scripts under `research/usb_cameras/` in the skellycam repo (committed on branch `dom/research`; corrected 2026-10-28, was "uncommitted, branch `development`"). Each one writes JSON to `results/<platform>/<hostname>/<test>/`.

**Windows test machine (results measured here)**

| Item | Value |
| --- | --- |
| OS | Windows 11 Home 10.0.26300 |
| USB controllers | Intel USB 3.20 xHCI (8086:7A60), Intel USB 3.10 xHCI (8086:1138) |
| Camera 1 | Razer Kiyo Pro, 1532:0E05, usbvideo.sys |
| Camera 2 | Logitech C922 Pro Stream, 046D:085C, usbvideo.sys |
| Camera 3 | Logitech C930e, 046D:0843, usbvideo.sys (later moved to WinUSB for the libuvc tests) |
| Toolchains | Python 3.12 via uv, Rust stable (MSVC), Visual Studio 2022 MSVC 14.42, Windows SDK 10.0.22621 |

**How to reproduce**

- Python tests are single-file PEP 723 scripts: `uv run --script <file>`. They don't depend on the skellycam package.
- On a shared machine, wrap any command that opens a camera in `uv run --script research/usb_cameras/tools/camlock.py -- <command>`. Only one test then holds the cameras at a time.
- Per-frame logs share one schema: host arrival time, OS timestamp, raw UVC PTS/SCR and payload size. So `tools/analyze_frames.py` can compare any backend against any other.
- Linux and macOS tests are drafted to run as-is. Their results count as unverified until run on those machines; see the last section.

## Goal 2 — Timing of when light hits the sensor

On Windows, the OS timestamps are an order of magnitude coarser than the camera can do. Host-arrival and Media Foundation timestamps land within about 4–5 ms of a screen-flash ground truth on the C922, and 8–12 ms on the C930e (in the one valid rerun of the C930e's other frame-period mode it was 4.7 ms, so that error is probably tied to the mode; corrected 2026-10-28). A per-frame clock model gets the C922 to about 0.4–0.5 ms, which is the floor of the test method. Rolling shutter adds a bigger effect: a frame's capture time varies about 31 ms from its top row to its bottom row.

**Error against screen-flash ground truth** (std after removing a fixed offset; 1280×720@30 MJPEG; ranges over repeated 30 s runs)

| Timestamp source | C922 (6 runs) | C930e |
| --- | --- | --- |
| Host arrival time | 3.9–5.3 ms | 4.5 ms (run 1); 8.9–11.9 ms (5 later runs) |
| Media Foundation sample time | 4.0–4.8 ms | 4.6 ms (run 1); 8.1–11.4 ms (5 later runs) |
| UVC PTS, whole-run fit to arrival envelope | 0.39–0.54 ms | 0.52 ms (run 1); 4.8–10.3 ms (5 later runs) |
| UVC PTS mapped through the camera's STC clock | — | 0.4–1.8 ms (4.3 ms at 15.6 ms exposure) |
| Frame index fitted to arrival envelope (no metadata) | 0.41–0.51 ms | 0.52 ms (run 1) |

**What the tests show**

- **Windows delivers frames in 16 ms steps.** At 30 fps, arrival intervals are 32 or 48 ms. Uniform 16 ms quantisation alone predicts 16/√12 = 4.62 ms, matching the measured error. The Media Foundation sample time (equal to `MFSampleExtension_DeviceTimestamp`) is no better.
- **Windows can expose raw UVC timestamps.** Setting `MetadataBufferSizeInKB0` (admin, once per camera, then a replug) attaches `MF_CAPTURE_METADATA_FRAME_RAWSTREAM` to 100% of samples. Every sample then carries PTS and SCR. Frame delivery was unchanged on all three cameras.
- **PTS quality depends on the camera.** The C922's PTS is periodic to 125–137 µs rms. The C930e's PTS is a synthetic counter that advances a fixed 997,222 ticks per frame. It drifts about 0.1% against the real frame clock. In the 10-25 runs it jumped one extra period every \~24 s; in the 10-27/28 rerun that step appeared in only 1 of 6 runs, and it follows one of two frame-period modes (998,400 vs about 997,230 STC ticks per frame) whose trigger is unknown (corrected 2026-10-28; was "jumps one extra period every \~24 s"). C930e manual exposure set through MF before streaming was applied in only 1 of 5 valid rerun runs, so the C930e rows below may not be at the requested exposure.
- **Sub-millisecond accuracy is an upper bound, not a measurement.** The method floor on real data is \~0.4–0.5 ms. A frame index fitted to arrival times scores the same as PTS, so these runs can't separate PTS from a perfectly periodic sensor.
- **The best numbers need hindsight.** The whole-run fit is non-causal. Causal (live) versions give 0.59–1.1 ms on the C922 and 0.6–3.6 ms on the C930e, depending on start-up handling.
- **C922 PTS marks readout, not exposure start.** With a fixed region of interest, the offset moved −1.1 to −1.3× the exposure change (−50.97 / −58.83 / −67.64 ms at 1.95 / 7.81 / 15.63 ms exposure). That contradicts the UVC spec's "start of capture". It rests on one run per exposure.
- **Rolling shutter dominates.** The offset changes 30.4–31.1 ms per frame height on both cameras. Readout spans nearly the whole 33 ms frame period, so a marker's capture time needs a per-row correction.
- **Cross-camera sync is not yet established.** With an auto-selected region, the C930e−C922 offset ranged −14.7 to +7.4 ms across runs. A fixed region is required before this test can measure sync.

**With libusb on WinUSB (phase 2, C930e)**

- **The USB bus clock reaches the host clock without admin.** Unprivileged xHCI IOCTLs (`IOCTL_USB_GET_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC`) map USB frame numbers to QPC with 2.4–8 µs residual, −0.2 to +0.3 ppm, but only for about 2–3.5 s. Over 20 s the mapping shifted by up to −641 µs and QPC was non-causal in up to 208 of 396 samples, so the phase-2 agreement below needs a longer re-check (corrected 2026-10-28; was stated without the time limit). The camera's SCR SOF is the bus frame number mod 2048. So each frame's SCR timestamp (STC plus SOF) lands on QPC with no arrival-latency fitting.
- **Two independent routes agree.** The SCR-mapped time and the host first-payload callback time (back-dated by packet index) agree to a median absolute deviation (MAD) of 46–66 µs, with a median offset of +0.30 to +0.35 ms.
- **libusb arrival is far less quantised than Media Foundation.** The grid is 4 ms at 32 packets per transfer and 1 ms at 8, against MF's 16 ms. The pure-Python streamer with 8 transfers of 8 packets had \~0.4 ms host-arrival jitter.
- **The camera clock is linear within a run but drifts between runs.** The C930e's STC fits a line within the 1 ms SOF quantisation. Its rate against QPC moved between sessions (+42.3 to +49.5 ppm), so it must be refitted per session.
- **Exposure must be re-applied after the stream starts.** Set only before COMMIT, it isn't applied: the flash step rise was \~32 ms instead of \~12 ms.
- **Measured multi-camera agreement.** With a fixed region of interest, the C930e (libusb SCR) minus C922 (MF PTS) offset spread 0.5–0.8 ms across runs. The ground-truth floor was 0.47–0.80 ms per run, so this is the best sync figure measured, not a tight bound.
- **Rolling shutter was confirmed at \~29–30 ms per frame height.**

**Reproduce:** `timing/scripts/run_flash_test.ps1` (display `timing/build/flash_timecode.exe` plus capture `timing/build/mf_uvc_timing.exe`), then `timing/scripts/flash_analyze.py`. Verification runs and tools are in `results/windows/Gerald/timing/flash_verify_*/` and `flash_verify_tools/`. Linux (V4L2 buffer timestamps plus the UVC metadata node) and macOS (AVFoundation) versions are drafted in `timing/linux/run_linux_timing.sh` and `timing/macos/run_macos_timing.sh` but not yet run.

## Goal 3 — USB bandwidth allocation control

Only the host can fix this; the camera won't. The C930e asks for the largest isochronous slot (3072 B per microframe) at 720p and 1080p MJPEG, whatever quality or payload size the host requests. Windows' usbvideo honours that, so one camera takes about 62% of a USB 2.0 link. With libuvc on WinUSB, the app picks a smaller alt setting itself. The C930e then streamed 720p30 at 30 fps in 800–1280 B and shared a hub with a second camera that usbvideo had locked out.

**Smallest alt setting that kept 30 fps** (C930e, MJPEG, libuvc on WinUSB, 20 s per alt, alt confirmed from the hub's open-pipe list)

| Mode | Camera requests | Static scene | Worst case: noise on screen | Est. cameras per USB 2.0 link\* |
| --- | --- | --- | --- | --- |
| 640×480@30 | alt 10 (2688 B) | alt 3 (512 B) | not tested | 7–8 |
| 1280×720@30 | alt 11 (3072 B) | alt 5 (800 B) | alt 7 (1280 B) | 3–4 |
| 1920×1080@30 | alt 11 (3072 B) | alt 8 (1600 B) | alt 8 dropped to 19 fps | 1–2 |

\*Estimates from the USB 2.0 budget model and measured frame sizes. No link has yet carried three or more cameras. At the camera's own request it is 1 per link in every mode.

**What the tests show**

- **usbvideo over-reserves by 4–12× for MJPEG.** The C930e at 720p30 reserves 24.6 MB/s and uses about 4 MB/s. The generic 4C4A:4A55 camera reserves 24.55 MB/s for 0.35 MB/s (55–67×). Its only alt is 3069 B, so no driver can reduce it.
- **Asking the camera doesn't work.** `dwMaxPayloadTransferSize` stayed at 3072 B (2688 B at 480p) across `wCompQuality` 2–61 and every payload size the host proposed in PROBE. JPEG sizes didn't change either.
- **Too small an alt drops whole frames; it doesn't corrupt them.** Delivered fps ≈ 30 / ceil(frame size / alt capacity); 47 of 48 runs matched within 6%. Strict libjpeg-turbo decoding found 0 corrupt frames in 15,821 (Rust runs) and 2,135 (bandwidth re-runs). Pillow can't detect truncated frames from this camera, so the check matters. The first frame after a zero-frame start can be partial, so apps must check EOI and the error bit.
- **Frame size swings with autofocus.** At 720p, starts seconds apart gave 76 KB and 176 KB frames, and sizes ramp over the first 1–2 s. Choose the alt from the measured worst-case size plus margin: alt 6–7 at 720p and alt 8–10 at 1080p, depending on the scene.
- **Admission control belongs to the USB controller, not the driver.** With the generic camera streaming via Media Foundation on the same hub, the C930e ran at alt ≤ 8; alt 9 was refused with an I/O error. usbvideo showed the same threshold in phase 1. While an audio interface on that link had isochronous pipes open, the threshold fell to alt 6 / alt 7.
- **A refused start poisons the next one.** After a bandwidth refusal, the next start delivers zero frames (5 of 5 cases); the one after works. An app stepping down one alt must expect a silent stream and restart again.
- **Windows' cost is a driver swap.** Microsoft's inbox WinUSB driver installed without a certificate (one UAC prompt, then a replug). The camera then vanishes from normal apps and its microphone disappears. Rolling back gave its functions new instance IDs (`&0&` to `&1&`).

**Linux and macOS (from source and docs, untested):**

- **Linux kernel:** mainline uvcvideo has applied `UVC_QUIRK_FIX_BANDWIDTH` (quirks=128) only to uncompressed formats since v2.6.32 (commit a2e35af6c756, 2009). That conflicts with quirks=128 helping MJPEG for you. `bandwidth/linux/uvc_bw_probe.py` compares the alt chosen and the concurrency limit with and without it.
- **Linux user space:** libuvc with a forced alt needs only a one-time udev rule giving usbfs access (`libusb/linux/70-skellycam-uvc.rules`), because `USBDEVFS_DISCONNECT` has no capability check. Test: `libusb/linux/run_libuvc_linux.sh`.
- **macOS:** libusb can't detach the camera's kernel driver without root or the `com.apple.vm.device-access` entitlement, so in-app alt control isn't available. Test: `libusb/macos/run_libusb_macos.sh`.

**Reproduce:** `libusb/winusb/run_elevated.ps1 -Action install` (then replug), `bandwidth/alt_sweep_run.sh` plus `alt_sweep_analyze.py`, and `bandwidth/verify/*.sh`. Roll back with `run_elevated.ps1 -Action rollback`. Results are in `results/windows/Gerald/phase2_bw_alt/` and `phase2_bw_alt_verify/`.

## Goal 4 — Consistent device naming

Use the USB serial number when a camera has a usable, unique one; otherwise use the physical port path. Only 1 of the 4 cameras tested has a serial, so the port path is the real identity for most cheap cameras. Two identical serial-less cameras can only be told apart by port, and swapping their cables is undetectable. `naming/camera_identity.py` implements the scheme. A full Windows listing takes 0.095–0.102 s in-process, no admin needed (corrected 2026-10-28; was "0.29–0.37 s", which included `uv` start-up).

| Camera | USB serial | Key produced on Windows |
| --- | --- | --- |
| Logitech C922 (046D:085C) | B76395EF | `046d:085c:sn=B76395EF` |
| Logitech C930e (046D:0843) | none | `046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.4` |
| Razer Kiyo Pro (1532:0E05) | none | `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` |
| Generic "USB Camera" (4C4A:4A55) | none | `4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.3` |

**What the tests show (Windows)**

- **All descriptors are readable without admin**, whatever the driver. The parent hub's IOCTLs return every descriptor: serial, alt settings, formats and the clock frequency.
- **Windows only builds stable IDs from serials.** The C922's instance ID is its serial. Serial-less cameras get `<parent-hash>&0&<port>` IDs, and a new instance plus a new ContainerId for every port they've used. PnP history shows 3 for the Kiyo and 2 for the C930e.
- **ContainerId adds nothing.** It is a v5 hash of the serial for the C922 and a generated v1 UUID for the others.
- **Port-based identity survives re-enumeration on the same port.** Two unplanned re-arrivals of all four cameras changed only the USB address. Instance IDs, LocationPaths, ContainerIds, MF/DirectShow paths, FFmpeg names and the key were all unchanged. MF/DirectShow indices are not stable, though: by the 10-27 rerun the C930e had moved from MF 7 to 6 and DirectShow 7 to 2, and the Kiyo from MF 6 to 7 and DirectShow 2 to 3. After its WinUSB rollback the C930e also got new KS/MF/DirectShow paths and a new ContainerId at the same port (corrected 2026-10-28; was "paths and indices ... were all unchanged").
- **Capture-API names map back to USB.** The Media Foundation link is the `KSCATEGORY_VIDEO_CAMERA` interface; the DirectShow/FFmpeg path is the `KSCATEGORY_CAPTURE` interface. These are open handles derived from the instance ID, not identities.
- **Indices and friendly names are useless for identity.** The C922 is MF index 4 but DirectShow index 0, and both lists include virtual cameras. The Kiyo shows up as "USB Video Device" and the generic camera as "USB Camera".

**Not yet tested:** a reboot, a physical replug, a move to another port, and two identical cameras. A programmatic restart test was vetoed by LogiTune. `naming/win_stability_workflow.ps1` runs the baseline / after-reboot / after-replug / after-move snapshots and diff. Linux (`linux_stability_workflow.sh`: `/dev/v4l/by-path`, udev `ID_PATH`, sysfs serial) and macOS (`macos_stability_workflow.sh`: AVFoundation `uniqueID` versus IOKit `locationID`) versions are drafted. They have been checked only against a fake sysfs tree and a synthetic ioreg dump.

**From documentation, untested:** Linux `/dev/v4l/by-id` collides for identical serial-less cameras, so use `by-path`. On macOS, AVFoundation's `uniqueID` for UVC cameras is reported to encode `locationID<<32 | VID<<16 | PID`, which is a port identity.
