# RocSync: what it is and how it could help the skellycam USB camera research

2026-10-30. Written by the `research:rocsync` agent of workflow `wf_30cb7742-77f`; web research only, nothing built or measured. Paths are relative to `research/usb_cameras/` unless noted.

Goals and must-haves are numbered as in the current brief (2026-10-30): G1 sync (exposure alignment, i.e. when light hits the sensor), G2 timestamp, G3 MJPEG, G4 ID, G5 bandwidth; M1 exposure, M2 format, M3 focus. REPORT.md uses 1 MJPEG, 2 timing, 3 bandwidth, 4 naming, 5 cross-platform.

Terms used below (as in REPORT.md): **PTS/SCR** = timestamps in each UVC payload header, on the camera's own clock (SCR pairs the camera clock with the USB frame counter, SOF). **QPC** = the Windows high-resolution host clock. **MF** = Media Foundation; **DShow** = DirectShow. **FSIN** = the sensor's frame-sync input pin, used for hardware triggering (`../arduino_sync/PLAN.md`). **TCXO** = temperature-compensated crystal oscillator; **HSE** = the MCU's high-speed external clock (crystal, or an oscillator in bypass mode). **RMSE** = root-mean-square error. **Line time** = the row-to-row readout delay of a rolling shutter. **Auto-ROI** = the region of interest the flash analyzer picks automatically (the 3x6 decoded-pixel block that flickers most, `timing/VERIFY_method.md` §1).

Sources: the BAL-ROCS-BUT-COOL/RocSync repo (cloned at HEAD `7d1f73c`, 2026-02-23, with full history), the arXiv preprint, and the published Sensors paper. I read the paper through PMC because MDPI returned 403. The clone was a temporary scratchpad copy and was not kept; re-clone the repo at the commits named below to check anything here. Anything marked **unconfirmed** is not backed by a primary source I read. All RocSync facts are *web* (repo, preprint, paper); my own estimates are marked *est.*

**Bottom line:** RocSync does not align exposures. It records when each frame was exposed on a visible LED clock and lines the videos up afterwards. As a measurement tool it fills the gap the flash method (monitor-flash ground truth, `timing/VERIFY_method.md`) cannot: no display scan-out, no gamma model, and it reads exposure start and end directly. There are two problems with using the stock device on our cameras:
- **Resolution.** It steps every 1 ms; the paper reports 1.34 ms RMSE (mean of five Azure Kinect runs, 0.38–1.94 ms; Section 2). That is coarser than the ~0.5 ms flash floor (the limit of the monitor-flash ground truth).
- **Rolling shutter.** Its decoder assumes a global shutter, but our webcams take about 30 ms to read out a frame.

The best fit is probably an ESP32 rig with an LED bar (Section 6; now specified in `sync_rig/DESIGN.md`) built for USB webcams, reusing RocSync's ideas and, where it suits, its decoding code (MPL-2.0, which skellycam's AGPL can include).

---

## 1. What RocSync is and how it works

**Origin.** Jaro Meyer (ETH Zurich), Frédéric Giraud (Balgrist/UZH), Joschua Wüthrich (ETH), Marc Pollefeys (ETH), Philipp Fürnstahl (Balgrist/UZH) and Lilian Calvet (Balgrist/UZH, corresponding author). Published as "RocSync: Millisecond-Accurate Temporal Synchronization for Heterogeneous Camera Systems", *Sensors* 26(3):1036, 5 Feb 2026, DOI 10.3390/s26031036. The arXiv preprint is 2511.14948 (18 Nov 2025). The original repo, jaromeyer/RocSync, now says it is deprecated in favor of the BAL-ROCS-BUT-COOL fork.

**Hardware (from the repo's KiCad files and JLCPCB parts database `hw/jlcpcb/project.db`):**
- **Board.** 25 x 25 cm PCB with a central ArUco marker. The decoder uses `DICT_4X4_50`, id 21.
- **LED ring.** 100 dual LEDs in a circle. Each pairs a red LED (HL-A-3528, LCSC C516141) with an IR LED (XYC-HIR76C-LX4, C2988728).
- **Binary counter.** 16 dual LEDs.
- **Corner LEDs.** Four, used to refine the homography. The PCB has 120 dual LEDs in total (100 + 16 + 4).
- **LED drivers.** 8 x TI TLC59283, a 16-channel constant-current shift-register driver (C485815). The corner LEDs use BCR420 drivers.
- **Microcontroller.** WCH CH32V003, a 32-bit RISC-V part (C5299908). Firmware is in `fw/src/main.cpp`.
- **Power.** BQ24075 charger, MT3608 boost converter, USB-C for power only, 604050 LiPo cell.
- **Enclosure.** 3D-printed handle and cover, plus matte smoked film over the LEDs.

**How it encodes time (firmware):**
- Timer1 interrupts at 2 kHz and toggles the shift clock, so one lit bit moves one ring position every 1 ms. One rotation takes 100 ms.
- The counter is shifted out and latched once per rotation, so its resolution is 100 ms.
- 16 bits x 100 ms gives about 109 minutes of unique time. The paper states the same.
- In a frame, the lit LEDs form an arc. The first lit LED marks exposure start and the last marks exposure end, in device milliseconds. The paper's Fig. 2 example decodes as counter 12, LEDs 40–57, meaning 1240–1257 ms.

**Analysis software (`sw/rocsync/vision.py`, `video.py`):**
1. Detect the ArUco marker. The frame is rejected if the marker covers less than 0.2% of the image.
2. Warp the board coarsely to 640 x 640 px.
3. Find the corner LEDs and warp again more precisely.
4. Read each of the 100 ring positions as LED intensity minus a background patch, then apply an Otsu threshold. The frame is rejected unless the lit LEDs form exactly one segment, and also if the segment touches positions 0–1 or 98–99 (the counter may have changed during the exposure).
5. Read the counter the same way.
6. For video, fit a RANSAC line of exposure start against frame index (residual threshold of one frame). Every frame then gets a timestamp in device time, with offset and drift.
- Optional extras export ffmpeg `setpts` commands to resample the videos into sync.
- `process_frame(image, ...)` works on a single image, so it could be called on our own decoded MJPEG frames.

**How cameras are synchronized.** Only after the fact. You show the board to each camera, typically at the start and end of a recording. The cameras do not need overlapping views. Each video gets a line mapping frame index to device time, and videos are aligned or resampled from those lines.

## 2. Claimed accuracy and validation

- **Headline claim:** "residual error of 1.34 ms RMSE across multiple recordings" (both arXiv and PMC).
- **Direct validation, against hardware sync.** Two Azure Kinect DK cameras joined by their sync cable, 1080p30 with 8.33 ms exposure, board about 150 cm away. Five 14-minute runs gave RMSE of 0.38, 1.30, 1.94, 1.73 and 1.37 ms (mean 1.34 ms). The Kinect hardware sync is assumed to be perfect; its own error is not measured.
- **Other experiments are indirect.** They score stereo reprojection error rather than time:
  - GoPro 12 + GoPro 10, 4K60 and 30 fps: mean reprojection error of 1.02 px (30 fps) and 0.95 px (60 fps) with interpolation. Without interpolation, RocSync only ties the light-switch method at 60 fps (1.11 vs 1.11 px).
  - GoPro + fusionTrack IR tracker: 1.81 ± 0.17 px.
  - Four-GoPro hand pose: 4.40 vs 8.80 px.
  - A surgical deployment of 73 recordings from more than 25 cameras, checked by eye.
- **Rolling shutter is not modeled.** PMC quotes: "our current decoding pipeline assumes a global-shutter imaging model". The paper blames most of the Kinect residual on rolling shutter, and its Fig. 7 shows uneven sector spacing. The suggested mitigations are holding the board farther away and relying on redundancy across frames.
- **Exposure range.** "Exposure times of up to 100 ms." Frames whose arc crosses the counter boundary are rejected, so long exposures lose many frames. For example, at E ≈ 31 ms roughly a third of frames are rejected (*est.*, from the decoder's rejection rule). No minimum exposure is stated. The tested exposures were 8.33 ms, 1/240 s and 1/480 s.
- **Frame rate.** "10 to 1000 fps" is a design claim; only cameras up to 60 fps were tested.
- **Resolution.** Each LED step is 1 ms, so a single frame is quantized to 1 ms. Sub-millisecond reading from partial LED brightness appears only as future work in `sw/README.md`.

## 3. What a build needs

- **Cost.** The paper says "approximately US$20 per unit". The volume and whether that includes the 25 x 25 cm PCB are **unconfirmed**.
- **Fabrication.** The KiCad design targets JLCPCB assembly, with Gerbers and a parts database in `hw/jlcpcb/`. The mechanical parts list is in `hw/README.md`.
- **Firmware toolchain.** PlatformIO with the community `platform-ch32v` (WCH Arduino core), flashed through a WCH-LinkE programmer over SWDIO.
- **Discrepancies I found in the repo:**
  - **The oscillator is not a TCXO.** The paper says TCXO, but the BOM's oscillator part C271645 is a TKD SX25Y024000BC1T, a plain 24 MHz ±10 ppm crystal. `hw/README.md` still lists "Use TCXO for better accuracy" as a TODO.
    - In the paper-era firmware (commit `5d82ddc`, which the paper cites), the only clock setting is `-DSYSCLK_FREQ_24MHz_HSE` in `platformio.ini`.
    - At HEAD, the explicit `SetSysClockTo_24MHz_HSE()` call is commented out. It also uses HSE bypass mode, which suits an oscillator, not a crystal. Whether HEAD actually runs from the crystal is **unconfirmed**.
  - **HEAD firmware and decoder do not match the PCB in the repo.** The KiCad PCB has not changed since the initial commit in 2024-09. HEAD's `vision.py` and firmware expect a newer layout with 20 counter LEDs and a 5th corner LED (commit notes say "RGB tested, IR not tested"). That PCB is not in the repo.
  - **HEAD firmware appears not to compile.** It uses `BUTTON_LADDER_PIN`, which is not defined anywhere; the commit message says "analogRead for the buttons still broken".
  - **What to build from.** For the in-repo PCB, use commit `5d82ddc` for both firmware and software.
- **Using Dom's ESP32 instead.** It cannot be dropped in, because the board has its own CH32V003 soldered on. In principle an ESP32 could drive the same TLC59283 chain (clock, data, latch and blank lines), but 3.3 V logic against the board's driver supply is **unconfirmed**. A small ESP32 design of our own is the more practical route (Section 6 and `sync_rig/DESIGN.md`).

## 4. License

- **Repo: MPL-2.0** (root `LICENSE`, confirmed in both repos). No source file carries the Exhibit B "Incompatible With Secondary Licenses" notice; the Exhibit B text in `LICENSE` is only the standard template. There are no per-file headers, and the hardware files are covered only by that root LICENSE.
- **Effect for skellycam (AGPL-3.0-or-later).** MPL-2.0 §3.3 allows MPL files to be combined into a larger work under a "Secondary License", and §1.12 names the GNU AGPL 3.0 or later as one. So skellycam can include or import RocSync code. The MPL files themselves stay MPL: changes to those files must be shared as source under MPL. A separate research tool that just pip-installs it is simpler still.
- **Paper: CC BY** (PMC states this). The version, presumably 4.0, is **unconfirmed**. Figures and text can be reused with attribution.
- Using the ideas (moving dot, counter, start/end decoding) in our own design raises no license issue.

## 5. How it could fill the gaps in this research

**(a) G1 sync: measuring real exposure alignment between cameras.**
- **What it can and cannot do.** RocSync measures alignment; it does not improve it. That supports Dom's assumption: only a hardware trigger (FSIN, `../arduino_sync/PLAN.md`) can align exposures.
- **What it fixes.** The flash method (`timing/VERIFY_method.md` §1 and §6) cannot measure alignment, for three reasons: display scan-out, a ~35 ms change in ground-truth offset across image blocks, and the two auto-ROIs sitting at different rows. An LED clock has no scan-out. If each camera sees the board on the same sensor rows, or rows are corrected using a measured line time, the difference between per-frame exposure-start series is the real misalignment.
- **What it would show.** With free-running C922 and C930e, the phase between them should slide through a whole frame about every 14 min (derived, not measured: the PTS-vs-ground-truth rates, C930e +35 ppm and C922 −3.9 ppm, `timing/VERIFY_method.md` §5, differ by ~39 ppm). The 10 s delivered-fps figures (30.00 vs 30.05 fps, REPORT finding 1) would imply a frame every ~20 s, but that gap is within their counting error. With FSIN, the same setup gives the residual skew.
- **Precision.** Stock RocSync gives 1 ms per frame. Fitting many frames gives a better average offset.

**(b) G2 timestamp: scoring timestamp sources without a monitor.**
- **What it fixes.** Each frame gets its exposure start and end in device time, with no gamma or brightness model, which `timing/VERIFY_method.md` §1 identifies as what limits the flash method.
- **Limits of stock RocSync:**
  - **1 ms quantization** (about 0.29 ms std per edge) plus rolling-shutter bias. That is coarser than both the ~0.5 ms flash floor and the 46–66 µs robust sigma between the SCR-derived frame time and back-dated first-payload arrival (C930e on libusb, REPORT finding 13).
  - **No host clock link.** The device clock (±10 ppm crystal) must be mapped to QPC independently, or the slope gets fitted to the source being judged and the test becomes circular again. A slope error of 10 ppm is 0.3 ms over 30 s.
  - **The regularity caveat in `timing/VERIFY_method.md` §3 still applies.** If exposures are truly periodic, a frame counter will score as well as PTS. Only sub-millisecond resolution can show per-frame jitter and whether a source follows it.
- **Still useful as is:** it can settle whether C922 PTS sits at exposure start or end (REPORT finding 12, provisional). Change the exposure and see which decoded edge PTS follows.

**(c) Rolling-shutter timing, exposure duration, and checking M1 exposure control.** This is the strongest fit.
- **Exposure duration per frame.** The number of lit LEDs gives the actual exposure of each frame, to 1 ms, independently of the API.
  - This directly tests REPORT finding 11 (C930e manual exposure set through MF before streaming, or through libusb before stream commit, was not reliably applied) and extends it to DShow and to setting exposure after stream commit: does C930e manual exposure really give about 8 LEDs at exposure −7 (2^-7 s = 7.8 ms), or about 31 at −5 (2^-5 s = 31 ms)?
  - It also catches exposure changing mid-stream and shows whether auto-exposure is really off.
  - The flash method had to assume the exposure and could not check it (the 2026-10-28 caveat at the top of `timing/VERIFY_method.md`).
- **Rolling-shutter line time.** The decoded start shifts as the board moves up or down the frame. Per-LED image rows inside one frame also hold this information, but only a custom decoder can use it.

**(d) Long-run drift between free-running cameras.**
- RocSync can measure it. The device clock is common to all cameras, so its ±10 ppm error cancels between them.
- Showing the board at the start and end (the paper's method) gives mean drift. Leaving it in view of all cameras for the whole run gives the drift profile, for example with temperature.
- Range is 109 minutes with 16 counter bits.

## 6. Limitations, and a better fit for this research

**Why the stock device fits our webcams poorly:**
- **Rolling shutter conflicts with decoding.** Our cameras take about 30 ms to read out a 33 ms frame (REPORT finding 12). If the board covers 20–25% of the frame height, the ring spans about 6–7 ms of readout. That biases the start/end decode or splits the lit arc, and split arcs are rejected. Shrinking the board makes detection fail instead.
- **Quantization.** 1 ms steps against a sub-millisecond question.
- **IR is useless here.** The IR half of each LED is irrelevant to webcams with IR-cut filters (*est.*, not tested). The decoder only uses the red channel, which is quarter resolution on a Bayer sensor.
- **Brightness.** At very short exposures the 8 kHz PWM on the counter LEDs (50% brightness) could matter. LED brightness at short exposures in a dark room is **unconfirmed**.
- **Other gaps.** No link to the host clock. The repo HEAD is inconsistent with its own PCB (Section 3). The device is a 25 cm battery board with no FSIN output.
- **Not a limitation.** It does not need global shutter or IR to work; global shutter only affects accuracy, and IR only affects which light band it works in.

**Suggested ESP32 rig with an LED bar (a proposal here; nothing built or measured). It is now specified as the ESP32 sync rig in `sync_rig/DESIGN.md` §A–§D and planned in `docs/test_gap_plan.md` §3.1. DESIGN differs from this sketch in two places: its coarse counter is a 20-bit Gray code (one bit changes per step, range 2^20 × 10 ms ≈ 2.9 h), not binary, and its host link is serial pings timestamped on a capture-timer loopback, with an ESP32-S3 SOF-lock option (§C), not a lower-envelope fit:**
- **Lay the LEDs in one horizontal line,** so every timing LED falls on the same sensor rows. This removes rolling-shutter skew from decoding.
  - Put a second bar higher or lower in the frame, or move the board, to measure line time.
  - Use red or white LEDs, not IR.
- **Fine bar (F in DESIGN §A):** a one-hot chaser, one lit LED stepping every 100 µs. For example, 100 LEDs give a 10 ms rotation, which suits our 2^-7 s (7.8 ms) test exposure.
  - Drive them from shift registers (74HC595, TPIC6B595 or TLC5916) using the ESP32's hardware timer, or SPI/RMT with DMA for low jitter.
  - Add a slow coarse counter (C in DESIGN §A; binary here, Gray code in DESIGN) that changes only once per rotation. 16 bits x 10 ms is about 11 minutes; use 20 or more bits for long drift runs.
  - Optionally read sub-step timing from the brightness of the two end LEDs. Fully lit and fully dark LEDs in the same frame calibrate the tone curve, avoiding our gamma guess.
- **Host link:** send the device's microsecond clock over USB serial and timestamp it in QPC on the host. A lower-envelope fit gives a device-to-QPC mapping that does not depend on any camera, so G2 scoring stays non-circular. The jitter of USB serial on Windows is **unconfirmed**; the envelope fit tolerates it.
- **Shared timer:** drive the FSIN output from the same timer. That measures FSIN-to-exposure skew and the camera's re-trigger lockout (~18–20 ms on the InnoMaker OV9281) directly, replacing the swept-flash part of arduino_sync milestone M0 in `../arduino_sync/PLAN.md`.
- **Software:** reuse RocSync's homography approach and `process_frame` structure (MPL), but write our own decoder for the linear layout. It should output start and end per frame, per row band.

Full RocSync remains the right reference if other heterogeneous cameras (GoPros, phones) enter skellycam's scope. Its value there is post-hoc alignment at about 1 ms, which beats audio and timecode by the paper's figures.

## Sources

- https://github.com/BAL-ROCS-BUT-COOL/RocSync (HEAD 7d1f73c): `README.md`, `LICENSE`, `hw/README.md`, `hw/jlcpcb/project.db`, `hw/*.kicad_*`, `fw/platformio.ini`, `fw/src/main.cpp` (also at 5d82ddc), `sw/README.md`, `sw/rocsync/vision.py`, `sw/rocsync/video.py`
- https://github.com/jaromeyer/RocSync (deprecated original, MPL-2.0)
- https://arxiv.org/html/2511.14948v1 (preprint)
- https://pmc.ncbi.nlm.nih.gov/articles/PMC12900090/ (published Sensors version, CC BY; https://www.mdpi.com/1424-8220/26/3/1036 returned 403)
- https://www.lcsc.com/product-detail/C271645.html (the BOM part is a ±10 ppm crystal, not a TCXO)
- Local: `C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/timing/VERIFY_method.md`, `C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/REPORT.md` (findings 1 and 11–14, further-investigation item 7), `C:/Users/Dom/GitHub/freemocap/skellycam/research/arduino_sync/PLAN.md`